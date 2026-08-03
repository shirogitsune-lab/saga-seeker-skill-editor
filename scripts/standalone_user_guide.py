"""Generate a self-contained distribution guide without changing its source."""

from __future__ import annotations

import argparse
import base64
from collections.abc import Callable
import os
from pathlib import Path, PurePosixPath
import re
import tempfile


class StandaloneGuideError(RuntimeError):
    """Raised when a standalone guide cannot be generated safely."""


ReplaceOperation = Callable[[Path, Path], None]
_IMAGE_SRC_PATTERN = re.compile(
    r"(?P<prefix><img\b[^>]*?\bsrc\s*=\s*)(?P<quote>[\"'])(?P<src>[^\"']+)(?P=quote)",
    re.IGNORECASE,
)
_IMAGE_MIME_TYPES = {
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def generate_standalone_user_guide(
    source_html: Path,
    asset_directory: Path,
    output_html: Path,
    *,
    replace_operation: ReplaceOperation = os.replace,
) -> Path:
    """Embed every local guide image and atomically publish UTF-8 HTML."""

    source_html = source_html.resolve()
    asset_directory = asset_directory.resolve()
    output_html = output_html.resolve()
    if source_html == output_html:
        raise StandaloneGuideError("Source and output HTML must be different files")
    if not source_html.is_file():
        raise StandaloneGuideError(f"Source HTML does not exist: {source_html}")
    if not asset_directory.is_dir():
        raise StandaloneGuideError(f"Asset directory does not exist: {asset_directory}")
    try:
        source_text = source_html.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise StandaloneGuideError(f"Source HTML is not readable UTF-8: {exc}") from exc

    image_count = 0

    def embed_image(match: re.Match[str]) -> str:
        nonlocal image_count
        image_count += 1
        source = match.group("src")
        relative = PurePosixPath(source)
        if (
            relative.is_absolute()
            or len(relative.parts) != 2
            or relative.parts[0] != asset_directory.name
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise StandaloneGuideError(f"Unsupported image reference: {source}")
        candidate = asset_directory.joinpath(relative.parts[1]).resolve()
        if candidate.parent != asset_directory or not candidate.is_file():
            raise StandaloneGuideError(f"Referenced image does not exist: {source}")
        mime_type = _IMAGE_MIME_TYPES.get(candidate.suffix.lower())
        if mime_type is None:
            raise StandaloneGuideError(f"Unsupported image format: {source}")
        try:
            encoded = base64.b64encode(candidate.read_bytes()).decode("ascii")
        except OSError as exc:
            raise StandaloneGuideError(f"Referenced image is not readable: {source}") from exc
        return (
            match.group("prefix")
            + match.group("quote")
            + f"data:{mime_type};base64,{encoded}"
            + match.group("quote")
        )

    rendered_text = _IMAGE_SRC_PATTERN.sub(embed_image, source_text)
    if image_count == 0:
        raise StandaloneGuideError("Source guide contains no image references")
    remaining_sources = [
        match.group("src") for match in _IMAGE_SRC_PATTERN.finditer(rendered_text)
    ]
    if any(not source.startswith("data:image/") for source in remaining_sources):
        raise StandaloneGuideError("Distribution guide contains a non-embedded image")

    output_html.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{output_html.name}.",
            suffix=".tmp",
            dir=output_html.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(rendered_text.encode("utf-8"))
            temporary.flush()
            os.fsync(temporary.fileno())
        replace_operation(temporary_path, output_html)
        temporary_path = None
    except OSError as exc:
        raise StandaloneGuideError(f"Could not publish standalone guide: {exc}") from exc
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return output_html


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_html", type=Path)
    parser.add_argument("asset_directory", type=Path)
    parser.add_argument("output_html", type=Path)
    args = parser.parse_args()
    path = generate_standalone_user_guide(
        args.source_html,
        args.asset_directory,
        args.output_html,
    )
    print(f"Standalone HTML guide: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
