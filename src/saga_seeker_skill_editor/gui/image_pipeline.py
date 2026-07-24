"""Bounded Qt image loading and 512px WebP icon preparation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRect, Qt
from PySide6.QtGui import QImage, QImageReader, QImageWriter


MAX_ENCODED_BYTES = 64 * 1024 * 1024
MAX_DIMENSION = 16384
MAX_PIXELS = 64_000_000
MAX_ESTIMATED_PEAK_BYTES = 256 * 1024 * 1024
ICON_SIZE = 512
WEBP_QUALITY = 90
WEBP_OUTPUT_RESERVE = 16 * 1024 * 1024
SUPPORTED_FORMATS = {b"png", b"jpeg", b"jpg", b"webp"}


class ImageSafetyError(ValueError):
    """Raised before an unsafe or unsupported image can replace the draft."""


@dataclass(frozen=True)
class ImageInspection:
    encoded_bytes: int
    width: int
    height: int
    pixel_count: int
    estimated_peak_bytes: int
    format_name: str


def inspect_image_path(path: Path) -> ImageInspection:
    """Reject oversized files by metadata before allocating an encoded buffer."""

    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ImageSafetyError(f"could not inspect image file: {exc}") from exc
    if size < 1:
        raise ImageSafetyError("image file is empty")
    if size > MAX_ENCODED_BYTES:
        raise ImageSafetyError("encoded image exceeds 64 MiB")
    try:
        encoded = path.read_bytes()
    except OSError as exc:
        raise ImageSafetyError(f"could not read image file: {exc}") from exc
    return inspect_image_bytes(encoded)


def inspect_image_bytes(encoded: bytes) -> ImageInspection:
    """Read image metadata only and enforce every fixed pre-decode bound."""

    if not isinstance(encoded, bytes) or not encoded:
        raise ImageSafetyError("image file is empty")
    if len(encoded) > MAX_ENCODED_BYTES:
        raise ImageSafetyError("encoded image exceeds 64 MiB")

    buffer, reader = _reader_for(encoded)
    try:
        format_name = bytes(reader.format()).lower()
        if format_name not in SUPPORTED_FORMATS:
            raise ImageSafetyError("image format is unsupported")
        size = reader.size()
        if not size.isValid():
            raise ImageSafetyError(
                f"image header is invalid: {reader.errorString()}"
            )
        width = size.width()
        height = size.height()
    finally:
        buffer.close()

    if width < 1 or width > MAX_DIMENSION:
        raise ImageSafetyError(f"image width must be between 1 and {MAX_DIMENSION}")
    if height < 1 or height > MAX_DIMENSION:
        raise ImageSafetyError(f"image height must be between 1 and {MAX_DIMENSION}")
    pixel_count = width * height
    if pixel_count > MAX_PIXELS:
        raise ImageSafetyError("image exceeds the 64 megapixel limit")
    estimated_peak = (
        len(encoded)
        + pixel_count * 4 * 2
        + ICON_SIZE * ICON_SIZE * 4 * 2
        + WEBP_OUTPUT_RESERVE
    )
    if estimated_peak > MAX_ESTIMATED_PEAK_BYTES:
        raise ImageSafetyError("estimated image processing memory exceeds 256 MiB")
    return ImageInspection(
        encoded_bytes=len(encoded),
        width=width,
        height=height,
        pixel_count=pixel_count,
        estimated_peak_bytes=estimated_peak,
        format_name=format_name.decode("ascii"),
    )


def crop_and_encode_webp(
    encoded: bytes,
    *,
    crop: tuple[int, int, int, int],
) -> bytes:
    """Decode only after inspection, crop a square, and encode 512px WebP."""

    inspection = inspect_image_bytes(encoded)
    x, y, width, height = crop
    if width < 1 or height < 1 or width != height:
        raise ImageSafetyError("icon crop must be a non-empty square")
    if (
        x < 0
        or y < 0
        or x + width > inspection.width
        or y + height > inspection.height
    ):
        raise ImageSafetyError("icon crop is outside the source image")

    input_buffer, reader = _reader_for(encoded)
    reader.setAutoTransform(True)
    try:
        image = reader.read()
        if image.isNull():
            raise ImageSafetyError(f"image decode failed: {reader.errorString()}")
    finally:
        input_buffer.close()
    cropped = image.copy(QRect(x, y, width, height))
    if cropped.isNull():
        raise ImageSafetyError("image crop failed")
    scaled = cropped.scaled(
        ICON_SIZE,
        ICON_SIZE,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    if scaled.isNull():
        raise ImageSafetyError("image resize failed")

    output = QByteArray()
    output_buffer = QBuffer(output)
    if not output_buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise ImageSafetyError("could not open the WebP output buffer")
    writer = QImageWriter(output_buffer, b"webp")
    writer.setQuality(WEBP_QUALITY)
    try:
        if not writer.write(scaled):
            raise ImageSafetyError(f"WebP encode failed: {writer.errorString()}")
    finally:
        output_buffer.close()
    result = bytes(output)
    if not result or len(result) > MAX_ENCODED_BYTES:
        raise ImageSafetyError("WebP output is empty or exceeds 64 MiB")
    return result


def _reader_for(encoded: bytes) -> tuple[QBuffer, QImageReader]:
    buffer = QBuffer()
    buffer.setData(QByteArray(encoded))
    if not buffer.open(QIODevice.OpenModeFlag.ReadOnly):
        raise ImageSafetyError("could not open the image input buffer")
    reader = QImageReader(buffer)
    reader.setDecideFormatFromContent(True)
    return buffer, reader
