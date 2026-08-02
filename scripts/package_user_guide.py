"""Copy the canonical offline user guide into a distribution directory."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import tempfile

try:
    from user_guide_artifacts import (
        GuideArtifactError,
        publish_entries_atomically,
        validate_screenshot_directory,
    )
except ModuleNotFoundError:  # Imported as scripts.package_user_guide in tests/tools.
    from scripts.user_guide_artifacts import (
        GuideArtifactError,
        publish_entries_atomically,
        validate_screenshot_directory,
    )


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_DIR = ROOT / "docs" / "user-guide"
CANONICAL_HTML = CANONICAL_DIR / "index.html"
CANONICAL_ASSETS = CANONICAL_DIR / "user-guide-assets"
DISTRIBUTED_HTML_NAME = "使い方.html"


class UserGuidePackagingError(RuntimeError):
    """Raised when the canonical guide cannot be copied safely."""


def package_user_guide(destination: Path) -> tuple[Path, Path]:
    """Copy exact guide bytes and replace only its dedicated asset directory."""

    destination = destination.resolve()
    canonical_dir = CANONICAL_DIR.resolve()
    canonical_html = CANONICAL_HTML.resolve()
    canonical_assets = CANONICAL_ASSETS.resolve()
    distributed_html = destination / DISTRIBUTED_HTML_NAME
    distributed_assets = destination / CANONICAL_ASSETS.name
    if _paths_overlap(destination, canonical_dir):
        raise UserGuidePackagingError(
            "正本ディレクトリまたはその親子を配布先にできません"
        )
    if any(
        _paths_overlap(target, source)
        for target in (distributed_html, distributed_assets)
        for source in (canonical_html, canonical_assets)
    ):
        raise UserGuidePackagingError("配布先が正本HTMLまたは正本画像と重なります")
    if not CANONICAL_HTML.is_file():
        raise UserGuidePackagingError(f"正本HTMLがありません: {CANONICAL_HTML}")
    if not CANONICAL_ASSETS.is_dir():
        raise UserGuidePackagingError(
            f"正本画像ディレクトリがありません: {CANONICAL_ASSETS}"
        )

    png_sources = sorted(CANONICAL_ASSETS.glob("*.png"))
    if len(png_sources) != 20:
        raise UserGuidePackagingError(
            f"正式スクリーンショットは20枚必要です（現在 {len(png_sources)} 枚）"
        )
    expected_names = tuple(source.name for source in png_sources)
    try:
        validate_screenshot_directory(
            CANONICAL_ASSETS,
            expected_names=expected_names,
            expected_size=(1440, 900),
        )
    except GuideArtifactError as exc:
        raise UserGuidePackagingError(str(exc)) from exc

    destination.parent.mkdir(parents=True, exist_ok=True)
    staged_root = Path(
        tempfile.mkdtemp(prefix=".user-guide-package-", dir=destination.parent)
    )
    try:
        staged_html = staged_root / DISTRIBUTED_HTML_NAME
        staged_assets = staged_root / CANONICAL_ASSETS.name
        staged_html.write_bytes(CANONICAL_HTML.read_bytes())
        staged_assets.mkdir()
        for source in png_sources:
            (staged_assets / source.name).write_bytes(source.read_bytes())
        validate_screenshot_directory(
            staged_assets,
            expected_names=expected_names,
            expected_size=(1440, 900),
        )
        publish_entries_atomically(
            staged_root,
            destination,
            entry_names=(DISTRIBUTED_HTML_NAME, CANONICAL_ASSETS.name),
        )
    except (OSError, GuideArtifactError) as exc:
        raise UserGuidePackagingError(str(exc)) from exc
    finally:
        if staged_root.exists():
            shutil.rmtree(staged_root)

    return distributed_html, distributed_assets


def _paths_overlap(first: Path, second: Path) -> bool:
    first = first.resolve()
    second = second.resolve()
    return first == second or first in second.parents or second in first.parents


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    html_path, assets_path = package_user_guide(args.destination)
    print(f"HTML guide: {html_path}")
    print(f"Assets: {assets_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
