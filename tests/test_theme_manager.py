from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from saga_seeker_skill_editor.gui.main_window import MainState, MainWindow  # noqa: E402
from saga_seeker_skill_editor.main import build_parser  # noqa: E402
from saga_seeker_skill_editor.gui.theme_manager import (  # noqa: E402
    APPLICATION_NAME,
    DEFAULT_THEME,
    ORGANIZATION_NAME,
    REQUIRED_TOKENS,
    SETTINGS_KEY,
    THEME_TOKENS,
    ThemeError,
    ThemeId,
    ThemeManager,
    render_qss,
)
from saga_seeker_skill_editor.resources import package_resource_path  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _settings(path: Path) -> QSettings:
    return QSettings(str(path), QSettings.Format.IniFormat)


def _manager(tmp_path: Path, *, styles_dir: Path | None = None) -> ThemeManager:
    return ThemeManager(
        _app(),
        settings=_settings(tmp_path / "settings.ini"),
        styles_dir=styles_dir,
    )


def _two_skill_sheet() -> bytes:
    skills = [
        {"id": "skill_a", "name": "Alpha", "description": "First", "type": "", "key": ""},
        {"id": "skill_b", "name": "Beta", "description": "Second", "type": "", "key": ""},
    ]
    data = {
        "formatVersion": "1.0.0",
        "exportedAt": "2026-07-20T00:00:00Z",
        "data": {
            "name": "Theme Test",
            "profile": {},
            "status": {},
            "skills": skills,
            "personalities": [],
            "memories": [],
            "icon": {},
        },
    }
    lis = "".join(
        f'<li data-skill-id="{skill["id"]}" data-skill-name="{skill["name"]}" '
        f'data-skill-type="" data-skill-description="{skill["description"]}">{skill["name"]}</li>'
        for skill in skills
    )
    return (
        f'<ul id="skills-value">{lis}</ul>'
        f'<script id="character-sheet-data" type="application/json">{json.dumps(data)}</script>'
    ).encode("utf-8")


def test_theme_constants_and_unset_default_to_light(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    assert ORGANIZATION_NAME == "shirogitsune-lab"
    assert APPLICATION_NAME == "SagaSeekerSkillEditor"
    assert SETTINGS_KEY == "appearance/theme"
    assert DEFAULT_THEME == ThemeId.LIGHT
    assert not manager.settings.contains(SETTINGS_KEY)

    result = manager.restore_theme()

    assert result.applied == ThemeId.LIGHT
    assert not result.used_fallback
    assert manager.current_theme == ThemeId.LIGHT
    assert not manager.settings.contains(SETTINGS_KEY)


def test_three_exclusive_actions_exist_and_theme_change_is_saved(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.restore_theme()
    window = MainWindow(theme_manager=manager)

    assert window.appearance_action_group.isExclusive()
    assert set(window.appearance_actions) == {ThemeId.LIGHT, ThemeId.DARK, ThemeId.HIGH_CONTRAST}
    assert sum(action.isChecked() for action in window.appearance_actions.values()) == 1
    assert window.appearance_actions[ThemeId.LIGHT].isChecked()

    window.appearance_actions[ThemeId.DARK].trigger()

    assert manager.current_theme == ThemeId.DARK
    assert manager.settings.value(SETTINGS_KEY) == ThemeId.DARK.value
    assert window.appearance_actions[ThemeId.DARK].isChecked()
    assert sum(action.isChecked() for action in window.appearance_actions.values()) == 1


def test_saved_theme_is_restored_by_next_manager(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.ini"
    first = ThemeManager(_app(), settings=_settings(settings_path))
    assert first.apply_theme(ThemeId.HIGH_CONTRAST).applied == ThemeId.HIGH_CONTRAST

    second = ThemeManager(_app(), settings=_settings(settings_path))
    result = second.restore_theme()

    assert result.applied == ThemeId.HIGH_CONTRAST
    assert not result.used_fallback


def test_invalid_setting_is_repaired_to_light(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.settings.setValue(SETTINGS_KEY, "not-a-theme")
    manager.settings.sync()

    result = manager.restore_theme()

    assert result.applied == ThemeId.LIGHT
    assert manager.settings.value(SETTINGS_KEY) == ThemeId.LIGHT.value


def test_temporarily_missing_saved_qss_falls_back_without_overwriting_setting(tmp_path: Path) -> None:
    styles = tmp_path / "styles"
    styles.mkdir()
    shutil.copy(package_resource_path("gui/styles/light.qss"), styles / "light.qss")
    manager = _manager(tmp_path, styles_dir=styles)
    manager.settings.setValue(SETTINGS_KEY, ThemeId.DARK.value)
    manager.settings.sync()

    result = manager.restore_theme()

    assert result.requested == ThemeId.DARK
    assert result.applied == ThemeId.LIGHT
    assert result.used_fallback
    assert not result.used_standard_style
    assert manager.settings.value(SETTINGS_KEY) == ThemeId.DARK.value


def test_all_missing_qss_uses_standard_style_without_overwriting_setting(tmp_path: Path) -> None:
    styles = tmp_path / "missing-styles"
    styles.mkdir()
    manager = _manager(tmp_path, styles_dir=styles)
    manager.settings.setValue(SETTINGS_KEY, ThemeId.HIGH_CONTRAST.value)
    manager.settings.sync()

    result = manager.restore_theme()

    assert result.applied == ThemeId.LIGHT
    assert result.used_fallback
    assert result.used_standard_style
    assert manager.settings.value(SETTINGS_KEY) == ThemeId.HIGH_CONTRAST.value
    assert _app().styleSheet() == ""


def test_qss_token_validation_rejects_missing_unknown_and_unresolved_tokens() -> None:
    valid = THEME_TOKENS[ThemeId.LIGHT].qss_values()
    with pytest.raises(ThemeError, match="undefined"):
        render_qss("QWidget { color: @TEXT@; }", {"TEXT": "#000000"})
    with pytest.raises(ThemeError, match="unknown"):
        render_qss("QWidget { color: @UNKNOWN_TOKEN@; }", valid)
    unresolved_values = dict(valid)
    unresolved_values["BACKGROUND"] = "@TEXT@"
    with pytest.raises(ThemeError, match="unresolved"):
        render_qss("QWidget { background: @BACKGROUND@; }", unresolved_values)


def test_every_theme_qss_has_complete_resolved_tokens(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    for theme, tokens in THEME_TOKENS.items():
        assert REQUIRED_TOKENS <= set(tokens.qss_values())
        rendered = manager._load_qss(theme)
        assert "@" not in rendered
        assert f"semantic theme: {theme.value}" in rendered


def test_theme_change_preserves_input_selection_and_modified_state(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.restore_theme()
    path = tmp_path / "sheet.html"
    path.write_bytes(_two_skill_sheet())
    window = MainWindow(theme_manager=manager)
    assert window.load_path(path)
    second_item = window.skill_list.topLevelItem(1)
    window.skill_list.setCurrentItem(second_item)
    editor = window.skill_widgets[1]
    editor.name_edit.setText("Beta Modified")
    selected_before = window.skill_list.currentItem()
    editor_before = editor

    window.appearance_actions[ThemeId.HIGH_CONTRAST].trigger()

    assert manager.current_theme == ThemeId.HIGH_CONTRAST
    assert window.skill_list.currentItem() is selected_before
    assert window.skill_widgets[1] is editor_before
    assert editor.name_edit.text() == "Beta Modified"
    assert window.changed_indices == {1}
    assert window.main_state == MainState.DIRTY
    assert window.status_label.property("state") == "modified"
    assert window.save_button.isEnabled()

    editor.name_edit.setText("Beta")
    assert window.main_state == MainState.NORMAL
    assert window.status_label.property("state") == "normal"


def test_labeled_qt_icons_remain_available_in_all_theme_states(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.restore_theme()
    window = MainWindow(theme_manager=manager)
    assert window.open_button.text() == "HTMLファイルを開く"
    assert not window.open_button.icon().isNull()
    assert window.reload_button.text() == "再読込"
    assert not window.reload_button.icon().isNull()
    assert not window.reload_button.isEnabled()

    path = tmp_path / "sheet.html"
    path.write_bytes(_two_skill_sheet())
    assert window.load_path(path)
    assert not window.save_button.isEnabled()
    assert window.save_button.text() == "別名で保存"
    assert not window.save_button.icon().isNull()

    for theme in ThemeId:
        result = manager.apply_theme(theme, persist=False)
        assert result.applied == theme
        assert not result.used_fallback
        window.skill_list.setCurrentItem(window.skill_list.topLevelItem(1))
        assert window.skill_list.currentItem() is window.skill_list.topLevelItem(1)
        assert not window.skill_list.topLevelItem(0).icon(window.skill_list.KIND_COLUMN).isNull()
        assert not window.open_button.icon().isNull()
        assert not window.reload_button.icon().isNull()
        assert not window.save_button.icon().isNull()
        assert window.save_button.text() == "別名で保存"
        assert not window.save_button.isEnabled()

    window.skill_widgets[1].name_edit.setText("Changed")
    assert window.save_button.isEnabled()
    assert window.save_button.text() == "別名で保存"


def _relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    values = sorted((_relative_luminance(first), _relative_luminance(second)), reverse=True)
    return (values[0] + 0.05) / (values[1] + 0.05)


@pytest.mark.parametrize("theme", list(ThemeId))
def test_theme_contrast_targets(theme: ThemeId) -> None:
    tokens = THEME_TOKENS[theme]
    normal_pairs = [
        (tokens.text, tokens.background),
        (tokens.text, tokens.panel),
        (tokens.text, tokens.input),
        (tokens.muted_text, tokens.panel),
        (tokens.selection_text, tokens.selection),
        (tokens.success, tokens.panel),
        (tokens.warning, tokens.panel),
        (tokens.danger, tokens.panel),
        (tokens.disabled, tokens.disabled_background),
    ]
    ui_pairs = [
        (tokens.border, tokens.panel),
        (tokens.focus, tokens.panel),
    ]
    assert all(_contrast(foreground, background) >= 4.5 for foreground, background in normal_pairs)
    assert all(_contrast(foreground, background) >= 3.0 for foreground, background in ui_pairs)


def test_packaging_configuration_includes_theme_resources() -> None:
    root = Path(__file__).resolve().parents[1]
    spec = (root / "SagaSeekerSkillEditor.spec").read_text(encoding="utf-8")
    build = (root / "build.ps1").read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert "saga_seeker_skill_editor/gui/styles" in spec
    assert "saga_seeker_skill_editor/gui/styles" in build
    assert '"gui/styles/*.qss"' in pyproject


def test_packaged_theme_smoke_options_are_hidden_and_parseable() -> None:
    parser = build_parser()
    options = parser.parse_args(["--theme-smoke=high_contrast", "--smoke-exit-ms=100"])
    assert options.theme_smoke == "high_contrast"
    assert options.smoke_exit_ms == 100
    help_text = parser.format_help()
    assert "theme-smoke" not in help_text
    assert "smoke-exit-ms" not in help_text


def test_theme_compatibility_module_is_not_used_by_application_code() -> None:
    root = Path(__file__).resolve().parents[1]
    offenders = []
    for path in (root / "src").rglob("*.py"):
        if path.name == "theme.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "saga_seeker_skill_editor.gui.theme import" in text:
            offenders.append(path)
    assert offenders == []
