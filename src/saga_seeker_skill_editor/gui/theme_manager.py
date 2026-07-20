"""Validated, persistent appearance themes for the Qt application."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from collections.abc import Mapping
import re

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from saga_seeker_skill_editor.resources import package_resource_path


ORGANIZATION_NAME = "shirogitsune-lab"
APPLICATION_NAME = "SagaSeekerSkillEditor"
SETTINGS_KEY = "appearance/theme"


class ThemeId(str, Enum):
    LIGHT = "light"
    DARK = "dark"
    HIGH_CONTRAST = "high_contrast"


DEFAULT_THEME = ThemeId.LIGHT


@dataclass(frozen=True)
class ThemeTokens:
    background: str
    panel: str
    input: str
    border: str
    text: str
    muted_text: str
    accent: str
    success: str
    warning: str
    danger: str
    disabled: str
    focus: str
    alternate: str
    selection: str
    selection_text: str
    button: str
    button_hover: str
    button_pressed: str
    disabled_background: str
    heading: str
    badge_background: str
    badge_text: str
    accent_hover: str
    accent_pressed: str
    accent_text: str
    danger_background: str
    danger_text: str
    splitter: str
    border_width: str
    focus_width: str
    selection_border_width: str

    def qss_values(self) -> dict[str, str]:
        return {name.upper(): value for name, value in asdict(self).items()}


THEME_TOKENS: dict[ThemeId, ThemeTokens] = {
    ThemeId.LIGHT: ThemeTokens(
        background="#e7ebef",
        panel="#f7f9fa",
        input="#ffffff",
        border="#6f7d88",
        text="#17212b",
        muted_text="#4d5a66",
        accent="#006f89",
        success="#176b3a",
        warning="#835600",
        danger="#a32135",
        disabled="#56616b",
        focus="#005fcc",
        alternate="#edf1f4",
        selection="#006f89",
        selection_text="#ffffff",
        button="#eef2f5",
        button_hover="#dde5ea",
        button_pressed="#ccd7de",
        disabled_background="#dfe4e8",
        heading="#111a22",
        badge_background="#e2e8ec",
        badge_text="#26333e",
        accent_hover="#005c72",
        accent_pressed="#00495b",
        accent_text="#ffffff",
        danger_background="#f6dde1",
        danger_text="#7f1527",
        splitter="#7b8994",
        border_width="1px",
        focus_width="2px",
        selection_border_width="0px",
    ),
    ThemeId.DARK: ThemeTokens(
        background="#11161a",
        panel="#20282e",
        input="#080e12",
        border="#647681",
        text="#edf2f5",
        muted_text="#b7c1c9",
        accent="#2697b1",
        success="#82d19d",
        warning="#edc05d",
        danger="#ff8291",
        disabled="#909ca5",
        focus="#58c9e2",
        alternate="#192126",
        selection="#1f6878",
        selection_text="#ffffff",
        button="#2b343b",
        button_hover="#39454e",
        button_pressed="#1e272d",
        disabled_background="#252c31",
        heading="#f6f8fa",
        badge_background="#303a42",
        badge_text="#e2e8ec",
        accent_hover="#32a9c2",
        accent_pressed="#1b7186",
        accent_text="#ffffff",
        danger_background="#5a2d35",
        danger_text="#ffe2e6",
        splitter="#4b5963",
        border_width="1px",
        focus_width="2px",
        selection_border_width="0px",
    ),
    ThemeId.HIGH_CONTRAST: ThemeTokens(
        background="#030303",
        panel="#0c0c0c",
        input="#000000",
        border="#f5f5f5",
        text="#ffffff",
        muted_text="#dedede",
        accent="#00d7ff",
        success="#67ff91",
        warning="#ffdd67",
        danger="#ff6f87",
        disabled="#c2c2c2",
        focus="#fff200",
        alternate="#151515",
        selection="#005a70",
        selection_text="#ffffff",
        button="#151515",
        button_hover="#252525",
        button_pressed="#000000",
        disabled_background="#202020",
        heading="#ffffff",
        badge_background="#000000",
        badge_text="#ffffff",
        accent_hover="#70eaff",
        accent_pressed="#00a7c7",
        accent_text="#000000",
        danger_background="#300009",
        danger_text="#ffffff",
        splitter="#ffffff",
        border_width="2px",
        focus_width="3px",
        selection_border_width="2px",
    ),
}


REQUIRED_TOKENS = {
    "BACKGROUND",
    "PANEL",
    "INPUT",
    "BORDER",
    "TEXT",
    "MUTED_TEXT",
    "ACCENT",
    "SUCCESS",
    "WARNING",
    "DANGER",
    "DISABLED",
    "FOCUS",
}
TOKEN_PATTERN = re.compile(r"@([A-Z][A-Z0-9_]*)@")


class ThemeError(RuntimeError):
    """Raised when a theme resource cannot be validated safely."""


@dataclass(frozen=True)
class ThemeApplyResult:
    requested: ThemeId
    applied: ThemeId
    used_fallback: bool
    used_standard_style: bool
    error: str = ""


def refresh_widget_style(widget: QWidget) -> None:
    """Force QSS to reevaluate after a dynamic property changes."""

    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def render_qss(template: str, token_values: Mapping[str, str]) -> str:
    keys = set(token_values)
    missing_definitions = REQUIRED_TOKENS - keys
    if missing_definitions:
        raise ThemeError(f"required theme tokens are undefined: {sorted(missing_definitions)}")

    used = set(TOKEN_PATTERN.findall(template))
    unknown = used - keys
    if unknown:
        raise ThemeError(f"QSS uses unknown theme tokens: {sorted(unknown)}")

    rendered = TOKEN_PATTERN.sub(lambda match: token_values[match.group(1)], template)
    unresolved = set(TOKEN_PATTERN.findall(rendered))
    if unresolved:
        raise ThemeError(f"QSS contains unresolved theme tokens: {sorted(unresolved)}")
    return rendered


class ThemeManager:
    def __init__(
        self,
        app: QApplication,
        *,
        settings: QSettings | None = None,
        styles_dir: Path | None = None,
    ) -> None:
        self.app = app
        self.settings = settings if settings is not None else QSettings(ORGANIZATION_NAME, APPLICATION_NAME)
        self.styles_dir = styles_dir if styles_dir is not None else package_resource_path("gui/styles")
        self.current_theme = DEFAULT_THEME
        self.last_result: ThemeApplyResult | None = None

    def restore_theme(self) -> ThemeApplyResult:
        stored = self.settings.value(SETTINGS_KEY, None)
        if stored is None or str(stored).strip() == "":
            requested = DEFAULT_THEME
        else:
            try:
                requested = ThemeId(str(stored))
            except ValueError:
                requested = DEFAULT_THEME
                self.settings.setValue(SETTINGS_KEY, DEFAULT_THEME.value)
                self.settings.sync()
        return self.apply_theme(requested, persist=False)

    def apply_theme(self, requested: ThemeId, *, persist: bool = True) -> ThemeApplyResult:
        try:
            qss = self._load_qss(requested)
        except ThemeError as exc:
            result = self._apply_available_fallback(requested, str(exc))
            self.last_result = result
            return result

        self._commit_theme(requested, qss)
        if persist:
            self.settings.setValue(SETTINGS_KEY, requested.value)
            self.settings.sync()
        result = ThemeApplyResult(requested, requested, False, False)
        self.last_result = result
        return result

    def _apply_available_fallback(self, requested: ThemeId, first_error: str) -> ThemeApplyResult:
        errors = [first_error]
        for candidate in (ThemeId.LIGHT, ThemeId.DARK, ThemeId.HIGH_CONTRAST):
            if candidate == requested:
                continue
            try:
                qss = self._load_qss(candidate)
            except ThemeError as exc:
                errors.append(str(exc))
                continue
            self._commit_theme(candidate, qss)
            return ThemeApplyResult(requested, candidate, True, False, " | ".join(errors))

        self.app.setStyle("Fusion")
        self.app.setPalette(self._palette(THEME_TOKENS[DEFAULT_THEME]))
        self.app.setStyleSheet("")
        self.current_theme = DEFAULT_THEME
        self._refresh_top_level_widgets()
        return ThemeApplyResult(requested, DEFAULT_THEME, True, True, " | ".join(errors))

    def _load_qss(self, theme: ThemeId) -> str:
        path = self.styles_dir / f"{theme.value}.qss"
        try:
            template = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ThemeError(f"failed to read theme QSS {path}: {exc}") from exc
        return render_qss(template, THEME_TOKENS[theme].qss_values())

    def _commit_theme(self, theme: ThemeId, qss: str) -> None:
        self.app.setStyle("Fusion")
        self.app.setPalette(self._palette(THEME_TOKENS[theme]))
        self.app.setStyleSheet(qss)
        self.current_theme = theme
        self._refresh_top_level_widgets()

    def _refresh_top_level_widgets(self) -> None:
        for widget in self.app.topLevelWidgets():
            refresh_widget_style(widget)

    @staticmethod
    def _palette(tokens: ThemeTokens) -> QPalette:
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(tokens.background))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(tokens.text))
        palette.setColor(QPalette.ColorRole.Base, QColor(tokens.input))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(tokens.alternate))
        palette.setColor(QPalette.ColorRole.Text, QColor(tokens.text))
        palette.setColor(QPalette.ColorRole.Button, QColor(tokens.button))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(tokens.text))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(tokens.selection))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(tokens.selection_text))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(tokens.muted_text))
        palette.setColor(QPalette.ColorRole.Link, QColor(tokens.accent))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(tokens.disabled))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(tokens.disabled))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(tokens.disabled))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor(tokens.disabled_background))
        return palette


def apply_theme(app: QApplication) -> ThemeManager:
    """Compatibility helper for callers that previously applied one fixed theme."""

    manager = ThemeManager(app)
    manager.restore_theme()
    return manager
