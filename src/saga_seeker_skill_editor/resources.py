"""Runtime resource path helpers."""

from __future__ import annotations

from pathlib import Path
import sys


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / relative


def package_resource_path(relative: str) -> Path:
    """Resolve a resource stored beside the Python package in every build mode."""

    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS) / "saga_seeker_skill_editor"  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent
    return base / relative
