from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402

from saga_seeker_skill_editor.gui.main_window import MainWindow  # noqa: E402
from saga_seeker_skill_editor.gui.theme_manager import ThemeManager  # noqa: E402
from saga_seeker_skill_editor.gui.window_preferences import (  # noqa: E402
    DEFAULT_STARTUP_DISPLAY,
    STARTUP_DISPLAY_KEY,
    StartupDisplayMode,
    restore_startup_display,
    show_with_startup_display,
)


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _settings(path: Path) -> QSettings:
    return QSettings(str(path), QSettings.Format.IniFormat)


def test_unset_and_invalid_startup_display_use_safe_windowed_default(tmp_path: Path) -> None:
    settings = _settings(tmp_path / "settings.ini")
    assert DEFAULT_STARTUP_DISPLAY == StartupDisplayMode.WINDOWED
    assert restore_startup_display(settings) == StartupDisplayMode.WINDOWED
    assert not settings.contains(STARTUP_DISPLAY_KEY)

    settings.setValue(STARTUP_DISPLAY_KEY, "invalid")
    assert restore_startup_display(settings) == StartupDisplayMode.WINDOWED
    assert settings.value(STARTUP_DISPLAY_KEY) == StartupDisplayMode.WINDOWED.value


def test_startup_display_actions_are_exclusive_saved_and_restored(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.ini"
    first_manager = ThemeManager(_app(), settings=_settings(settings_path))
    first_manager.restore_theme()
    first = MainWindow(theme_manager=first_manager)

    assert first.startup_display_action_group.isExclusive()
    assert set(first.startup_display_actions) == set(StartupDisplayMode)
    assert first.startup_display_actions[StartupDisplayMode.WINDOWED].isChecked()

    first.startup_display_actions[StartupDisplayMode.MAXIMIZED].trigger()

    assert first.startup_display_mode == StartupDisplayMode.MAXIMIZED
    assert first_manager.settings.value(STARTUP_DISPLAY_KEY) == "maximized"
    assert sum(action.isChecked() for action in first.startup_display_actions.values()) == 1

    second_manager = ThemeManager(_app(), settings=_settings(settings_path))
    second_manager.restore_theme()
    second = MainWindow(theme_manager=second_manager)
    assert second.startup_display_mode == StartupDisplayMode.MAXIMIZED
    assert second.startup_display_actions[StartupDisplayMode.MAXIMIZED].isChecked()


class _RecordingWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.presentation = ""

    def show(self) -> None:
        self.presentation = "windowed"

    def showMaximized(self) -> None:  # noqa: N802
        self.presentation = "maximized"


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (StartupDisplayMode.WINDOWED, "windowed"),
        (StartupDisplayMode.MAXIMIZED, "maximized"),
    ],
)
def test_startup_display_controls_how_window_is_shown(
    mode: StartupDisplayMode,
    expected: str,
) -> None:
    _app()
    window = _RecordingWindow()
    show_with_startup_display(window, mode)
    assert window.presentation == expected
