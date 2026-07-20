"""GUI application bootstrap."""

from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication, QSettings, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from saga_seeker_skill_editor.gui.main_window import MainWindow
from saga_seeker_skill_editor.gui.theme_manager import (
    APPLICATION_NAME,
    ORGANIZATION_NAME,
    ThemeId,
    ThemeManager,
)
from saga_seeker_skill_editor.resources import resource_path


def run_gui(
    argv: list[str] | None = None,
    *,
    startup_theme: str | None = None,
    exit_after_ms: int | None = None,
) -> int:
    QCoreApplication.setOrganizationName(ORGANIZATION_NAME)
    QCoreApplication.setApplicationName(APPLICATION_NAME)
    app = QApplication(sys.argv if argv is None else argv)
    theme_manager = ThemeManager(app, settings=QSettings(ORGANIZATION_NAME, APPLICATION_NAME))
    theme_manager.restore_theme()
    if startup_theme is not None:
        requested_theme = ThemeId(startup_theme)
        result = theme_manager.apply_theme(requested_theme, persist=False)
        if result.applied != requested_theme or result.used_fallback:
            return 3
    icon_path = resource_path("assets/kanaria.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow(theme_manager=theme_manager)
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.show()
    if exit_after_ms is not None:
        QTimer.singleShot(max(0, exit_after_ms), app.quit)
    return app.exec()
