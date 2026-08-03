"""Transactional helpers for user-guide images and distribution entries."""

from __future__ import annotations

from collections.abc import Callable, Iterable
import os
from pathlib import Path
import shutil
import tempfile

from PySide6.QtGui import QImageReader


class GuideArtifactError(RuntimeError):
    """Raised when a guide artifact cannot be validated or published safely."""


ReplaceOperation = Callable[[Path, Path], None]


def validate_png_file(
    path: Path,
    *,
    expected_size: tuple[int, int],
) -> None:
    """Fully decode one PNG and validate its exact dimensions."""

    reader = QImageReader(str(path))
    reader.setDecideFormatFromContent(True)
    if bytes(reader.format()).lower() != b"png" or not reader.canRead():
        raise GuideArtifactError(f"完全なPNGとして読み込めません: {path.name}")
    image = reader.read()
    if image.isNull():
        raise GuideArtifactError(
            f"PNGの完全デコードに失敗しました: {path.name}: {reader.errorString()}"
        )
    actual_size = (image.width(), image.height())
    if actual_size != expected_size:
        raise GuideArtifactError(
            f"PNGサイズが不正です: {path.name}: "
            f"{actual_size[0]}x{actual_size[1]}"
        )


def validate_screenshot_directory(
    directory: Path,
    *,
    expected_names: Iterable[str],
    expected_size: tuple[int, int],
) -> None:
    """Require one exact, fully decodable screenshot set and no extra entries."""

    expected = tuple(sorted(expected_names))
    if not directory.is_dir():
        raise GuideArtifactError(f"画像ディレクトリがありません: {directory}")
    entries = tuple(sorted(path.name for path in directory.iterdir()))
    if entries != expected:
        raise GuideArtifactError(
            "正式スクリーンショットのファイル集合が一致しません"
        )
    for name in expected:
        path = directory / name
        if not path.is_file():
            raise GuideArtifactError(f"画像ファイルではありません: {name}")
        validate_png_file(path, expected_size=expected_size)


def replace_directory_atomically(
    staged: Path,
    target: Path,
    *,
    replace_operation: ReplaceOperation = os.replace,
) -> None:
    """Publish a staged directory, restoring the previous target on failure."""

    staged = staged.resolve()
    target = target.resolve()
    if not staged.is_dir():
        raise GuideArtifactError(f"一時ディレクトリがありません: {staged}")
    if staged.parent != target.parent:
        raise GuideArtifactError("一時画像と公開先は同じ親ディレクトリが必要です")
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = Path(
        tempfile.mkdtemp(prefix=f".{target.name}-backup-", dir=target.parent)
    )
    backup.rmdir()
    had_target = target.exists()
    try:
        if had_target:
            os.replace(target, backup)
        replace_operation(staged, target)
    except OSError as exc:
        try:
            _remove_path(target)
            if backup.exists():
                os.replace(backup, target)
        except OSError as restore_exc:  # pragma: no cover - catastrophic OS failure
            raise GuideArtifactError(
                f"公開失敗後の復元にも失敗しました: {restore_exc}"
            ) from exc
        raise GuideArtifactError(f"公開前の画像集合を保持しました: {exc}") from exc
    finally:
        if backup.exists():
            _remove_path(backup)


def publish_entries_atomically(
    staged_root: Path,
    destination: Path,
    *,
    entry_names: Iterable[str],
    remove_names: Iterable[str] = (),
    replace_operation: ReplaceOperation = os.replace,
) -> None:
    """Publish entries and remove obsolete siblings as one transaction."""

    staged_root = staged_root.resolve()
    destination = destination.resolve()
    names = tuple(entry_names)
    obsolete = tuple(remove_names)
    managed_names = names + obsolete
    if (
        not names
        or len(set(managed_names)) != len(managed_names)
        or any(Path(name).name != name for name in managed_names)
    ):
        raise GuideArtifactError("Distribution entry names are invalid")
    if not staged_root.is_dir() or any(
        not (staged_root / name).exists() for name in names
    ):
        raise GuideArtifactError("配布用の一時成果物が揃っていません")
    destination.mkdir(parents=True, exist_ok=True)
    backup_root = Path(
        tempfile.mkdtemp(prefix=".user-guide-backup-", dir=destination.parent)
    )
    moved_old: list[str] = []
    placed_new: list[str] = []
    try:
        for name in managed_names:
            target = destination / name
            if target.exists():
                os.replace(target, backup_root / name)
                moved_old.append(name)
        for name in names:
            replace_operation(staged_root / name, destination / name)
            placed_new.append(name)
    except OSError as exc:
        try:
            for name in reversed(placed_new):
                _remove_path(destination / name)
            for name in reversed(moved_old):
                os.replace(backup_root / name, destination / name)
        except OSError as restore_exc:  # pragma: no cover - catastrophic OS failure
            raise GuideArtifactError(
                f"配布失敗後の復元にも失敗しました: {restore_exc}"
            ) from exc
        raise GuideArtifactError(f"以前の正常な配布物を保持しました: {exc}") from exc
    finally:
        _remove_path(backup_root)


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()
