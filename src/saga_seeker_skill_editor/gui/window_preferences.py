"""Persistent window display preferences."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMainWindow


STARTUP_DISPLAY_KEY = "window/startup_display"


class StartupDisplayMode(str, Enum):
    WINDOWED = "windowed"
    MAXIMIZED = "maximized"


DEFAULT_STARTUP_DISPLAY = StartupDisplayMode.WINDOWED


def restore_startup_display(settings: QSettings) -> StartupDisplayMode:
    value = settings.value(STARTUP_DISPLAY_KEY)
    if value is None:
        return DEFAULT_STARTUP_DISPLAY
    try:
        return StartupDisplayMode(str(value))
    except ValueError:
        settings.setValue(STARTUP_DISPLAY_KEY, DEFAULT_STARTUP_DISPLAY.value)
        settings.sync()
        return DEFAULT_STARTUP_DISPLAY


def save_startup_display(settings: QSettings, mode: StartupDisplayMode) -> None:
    settings.setValue(STARTUP_DISPLAY_KEY, mode.value)
    settings.sync()


def show_with_startup_display(window: QMainWindow, mode: StartupDisplayMode) -> None:
    if mode == StartupDisplayMode.MAXIMIZED:
        window.showMaximized()
    else:
        window.show()
