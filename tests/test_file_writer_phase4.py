from __future__ import annotations

from pathlib import Path

import pytest

from saga_seeker_skill_editor.core.file_writer import SaveError, atomic_save_bytes


def test_atomic_save_requires_overwrite_confirmation(tmp_path: Path) -> None:
    target = tmp_path / "sheet.html"
    target.write_bytes(b"old")

    with pytest.raises(SaveError):
        atomic_save_bytes(target, b"new")

    assert target.read_bytes() == b"old"


def test_atomic_save_validates_temp_file_before_replace(tmp_path: Path) -> None:
    target = tmp_path / "sheet.html"

    def validate(path: Path) -> None:
        assert path.parent == tmp_path
        assert path.read_bytes() == b"new"

    atomic_save_bytes(target, b"new", validate_temp_path=validate)

    assert target.read_bytes() == b"new"


def test_atomic_save_removes_temp_on_validation_failure(tmp_path: Path) -> None:
    target = tmp_path / "sheet.html"

    def validate(_: Path) -> None:
        raise ValueError("nope")

    with pytest.raises(SaveError):
        atomic_save_bytes(target, b"new", validate_temp_path=validate)

    assert not target.exists()
    assert list(tmp_path.iterdir()) == []
