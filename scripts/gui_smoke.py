"""Launch the GUI briefly for smoke testing."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from saga_seeker_skill_editor.gui.main_window import MainWindow
from saga_seeker_skill_editor.gui.theme_manager import (
    ThemeId,
    ThemeManager,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offscreen", action="store_true")
    parser.add_argument("--file", type=Path)
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--scale", type=float)
    parser.add_argument("--theme", choices=[theme.value for theme in ThemeId])
    parser.add_argument("--select-slot", type=int)
    parser.add_argument("--duration", type=int, default=1500)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.offscreen:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if args.scale is not None:
        os.environ["QT_SCALE_FACTOR"] = str(args.scale)
    app = QApplication([sys.argv[0]])
    smoke_settings = QSettings(str(Path("work") / "gui-smoke-settings.ini"), QSettings.Format.IniFormat)
    manager = ThemeManager(app, settings=smoke_settings)
    manager.restore_theme()
    if args.theme is not None:
        result = manager.apply_theme(ThemeId(args.theme), persist=False)
        if result.applied != ThemeId(args.theme) or result.used_fallback:
            raise RuntimeError(result.error or f"failed to apply theme: {args.theme}")
    window = MainWindow(theme_manager=manager)
    window.resize(980, 720)
    if args.file is not None:
        window.load_path(args.file)
    if args.select_slot is not None:
        item = window.skill_list.topLevelItem(args.select_slot - 1)
        if item is None:
            raise ValueError(f"slot is out of range: {args.select_slot}")
        window.skill_list.setCurrentItem(item)
    window.show()

    def finish() -> None:
        if args.screenshot is not None:
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            window.grab().save(str(args.screenshot))
        app.quit()

    QTimer.singleShot(args.duration, finish)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
