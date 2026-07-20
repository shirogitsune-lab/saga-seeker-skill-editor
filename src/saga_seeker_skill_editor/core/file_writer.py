"""Atomic file writing helpers."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import os
import tempfile


class SaveError(OSError):
    """Raised when a save operation cannot be completed safely."""


ValidatePath = Callable[[Path], None]


def atomic_save_bytes(
    destination: Path,
    content: bytes,
    *,
    overwrite_confirmed: bool = False,
    validate_temp_path: ValidatePath | None = None,
) -> None:
    """Write bytes through a same-directory temporary file and replace atomically.

    The caller must perform any user-facing overwrite confirmation before
    setting ``overwrite_confirmed``.
    """

    destination = destination.resolve()
    if destination.exists() and not overwrite_confirmed:
        raise SaveError(f"destination already exists: {destination}")

    directory = destination.parent
    tmp_path: Path | None = None
    fd = -1
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=directory,
        )
        tmp_path = Path(tmp_name)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        if validate_temp_path is not None:
            validate_temp_path(tmp_path)

        os.replace(tmp_path, destination)
        tmp_path = None
    except Exception as exc:
        if fd != -1:
            os.close(fd)
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass
        if isinstance(exc, SaveError):
            raise
        raise SaveError(str(exc)) from exc
