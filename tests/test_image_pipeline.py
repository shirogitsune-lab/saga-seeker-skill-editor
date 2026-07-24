from __future__ import annotations

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication
import pytest

from saga_seeker_skill_editor.gui.image_pipeline import (
    ImageSafetyError,
    inspect_image_bytes,
    inspect_image_path,
    crop_and_encode_webp,
)
from saga_seeker_skill_editor.gui.image_crop_dialog import ImageCropDialog
from saga_seeker_skill_editor.gui.image_smoke import run_image_smoke
from saga_seeker_skill_editor.main import build_parser


def _encoded_image(width: int, height: int, format_name: bytes) -> bytes:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#6b7280"))
    output = QByteArray()
    buffer = QBuffer(output)
    assert buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, format_name.decode("ascii"))
    buffer.close()
    return bytes(output)


def test_png_crop_is_encoded_as_512_square_webp() -> None:
    encoded = _encoded_image(40, 20, b"PNG")

    inspection = inspect_image_bytes(encoded)
    webp = crop_and_encode_webp(encoded, crop=(10, 0, 20, 20))
    webp_inspection = inspect_image_bytes(webp)
    rendered = QImage.fromData(webp)

    assert inspection.width == 40
    assert inspection.height == 20
    assert inspection.estimated_peak_bytes <= 256 * 1024 * 1024
    assert webp_inspection.format_name == "webp"
    assert rendered.width() == 512
    assert rendered.height() == 512


def test_jpeg_crop_is_encoded_as_512_square_webp() -> None:
    encoded = _encoded_image(24, 40, b"JPEG")

    inspection = inspect_image_bytes(encoded)
    webp = crop_and_encode_webp(encoded, crop=(0, 8, 24, 24))

    assert inspection.format_name == "jpeg"
    assert inspect_image_bytes(webp).format_name == "webp"


def test_crop_dialog_defaults_to_centered_largest_square() -> None:
    QApplication.instance() or QApplication([])
    encoded = _encoded_image(40, 20, b"PNG")

    dialog = ImageCropDialog(encoded)

    assert dialog.crop_box() == (10, 0, 20, 20)
    assert inspect_image_bytes(dialog.processed_webp()).format_name == "webp"


def test_hidden_packaged_image_smoke_covers_both_source_formats() -> None:
    assert run_image_smoke() == 0
    parser = build_parser()
    assert parser.parse_args(["--image-smoke"]).image_smoke is True
    assert "image-smoke" not in parser.format_help()


@pytest.mark.parametrize(
    "encoded",
    [
        b"not an image",
        b"\x89PNG\r\n\x1a\nbroken",
    ],
)
def test_corrupt_or_unsupported_image_is_reported_without_qt_crash(encoded: bytes) -> None:
    with pytest.raises(ImageSafetyError):
        inspect_image_bytes(encoded)


def test_extreme_slender_image_is_rejected_before_decode() -> None:
    encoded = _encoded_image(1, 17000, b"PNG")

    with pytest.raises(ImageSafetyError, match="height"):
        inspect_image_bytes(encoded)


def test_oversized_file_is_rejected_by_size_before_reading(tmp_path) -> None:
    source = tmp_path / "oversized.png"
    with source.open("wb") as handle:
        handle.truncate(64 * 1024 * 1024 + 1)

    with pytest.raises(ImageSafetyError, match="64 MiB"):
        inspect_image_path(source)
