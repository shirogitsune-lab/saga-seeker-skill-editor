"""Convert the canary WebP asset into a multi-size Windows ICO."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "カナリア.webp"
DESTINATION = ROOT / "assets" / "kanaria.ico"
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> int:
    with Image.open(SOURCE) as image:
        rgba = image.convert("RGBA")
        rgba.save(DESTINATION, sizes=SIZES)
    print(f"wrote {DESTINATION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
