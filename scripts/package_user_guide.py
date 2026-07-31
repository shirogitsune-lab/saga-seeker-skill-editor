"""Copy the canonical offline user guide into a distribution directory."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil


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

    destination.mkdir(parents=True, exist_ok=True)
    distributed_html = destination / DISTRIBUTED_HTML_NAME
    distributed_assets = destination / CANONICAL_ASSETS.name

    distributed_html.write_bytes(CANONICAL_HTML.read_bytes())
    if distributed_assets.exists():
        if not distributed_assets.is_dir():
            raise UserGuidePackagingError(
                f"画像配布先がディレクトリではありません: {distributed_assets}"
            )
        shutil.rmtree(distributed_assets)
    distributed_assets.mkdir()
    for source in png_sources:
        (distributed_assets / source.name).write_bytes(source.read_bytes())

    return distributed_html, distributed_assets


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
