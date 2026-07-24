"""Application entry point."""

from __future__ import annotations

import argparse
import sys

from saga_seeker_skill_editor import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="saga-seeker-skill-editor",
        description="Saga & Seeker Skill Editor",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--theme-smoke",
        choices=("light", "dark", "high_contrast"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--smoke-exit-ms",
        type=int,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--image-smoke",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    options = parser.parse_args(argv)
    if options.image_smoke:
        from saga_seeker_skill_editor.gui.image_smoke import run_image_smoke

        return run_image_smoke()
    try:
        from saga_seeker_skill_editor.gui.app import run_gui
    except ModuleNotFoundError as exc:
        if exc.name == "PySide6":
            print(
                "PySide6 is not installed in this Python environment. "
                "Install the runtime dependency before launching the GUI.",
                file=sys.stderr,
            )
            return 2
        raise
    return run_gui(
        [sys.argv[0]],
        startup_theme=options.theme_smoke,
        exit_after_ms=options.smoke_exit_ms,
    )


if __name__ == "__main__":
    raise SystemExit(main())
