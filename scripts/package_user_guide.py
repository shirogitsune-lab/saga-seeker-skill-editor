"""Build the self-contained user guide in a distribution directory."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import tempfile

try:
    from standalone_user_guide import StandaloneGuideError, generate_standalone_user_guide
    from user_guide_artifacts import (
        GuideArtifactError,
        publish_entries_atomically,
        validate_screenshot_directory,
    )
except ModuleNotFoundError:  # Imported as scripts.package_user_guide.
    from scripts.standalone_user_guide import (
        StandaloneGuideError,
        generate_standalone_user_guide,
    )
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
    """Raised when the canonical guide cannot be packaged safely."""


def package_user_guide(destination: Path) -> Path:
    """Atomically publish one self-contained guide and remove stale assets."""

    destination = destination.resolve()
    canonical_dir = CANONICAL_DIR.resolve()
    canonical_html = CANONICAL_HTML.resolve()
    canonical_assets = CANONICAL_ASSETS.resolve()
    distributed_html = destination / DISTRIBUTED_HTML_NAME
    if _paths_overlap(destination, canonical_dir):
        raise UserGuidePackagingError(
            "The canonical guide directory and distribution must not overlap"
        )
    if _paths_overlap(distributed_html, canonical_html):
        raise UserGuidePackagingError("Distribution must not replace canonical HTML")
    if not canonical_html.is_file():
        raise UserGuidePackagingError(f"Canonical HTML does not exist: {canonical_html}")
    if not canonical_assets.is_dir():
        raise UserGuidePackagingError(
            f"Canonical asset directory does not exist: {canonical_assets}"
        )

    png_sources = sorted(canonical_assets.glob("*.png"))
    if len(png_sources) != 20:
        raise UserGuidePackagingError(
            f"Exactly 20 canonical screenshots are required; found {len(png_sources)}"
        )
    expected_names = tuple(source.name for source in png_sources)
    try:
        validate_screenshot_directory(
            canonical_assets,
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
        generate_standalone_user_guide(
            canonical_html,
            canonical_assets,
            staged_html,
        )
        publish_entries_atomically(
            staged_root,
            destination,
            entry_names=(DISTRIBUTED_HTML_NAME,),
            remove_names=(CANONICAL_ASSETS.name,),
        )
    except (OSError, GuideArtifactError, StandaloneGuideError) as exc:
        raise UserGuidePackagingError(str(exc)) from exc
    finally:
        if staged_root.exists():
            shutil.rmtree(staged_root)

    return distributed_html


def _paths_overlap(first: Path, second: Path) -> bool:
    first = first.resolve()
    second = second.resolve()
    return first == second or first in second.parents or second in first.parents


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    html_path = package_user_guide(args.destination)
    print(f"HTML guide: {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
