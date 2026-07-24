"""Packaged Qt image-plugin smoke used by release verification."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QColor, QImage

from saga_seeker_skill_editor.gui.image_pipeline import (
    ICON_SIZE,
    crop_and_encode_webp,
    inspect_image_bytes,
    inspect_image_path,
)
from saga_seeker_skill_editor.resources import resource_path


def run_image_smoke() -> int:
    """Exercise PNG/JPEG decode, crop, WebP encode, and WebP decode."""

    try:
        default_icon = resource_path("assets/カナリア.webp")
        if inspect_image_path(default_icon).format_name != "webp":
            return 3
        for format_name in ("PNG", "JPEG"):
            source = QImage(48, 32, QImage.Format.Format_RGB32)
            source.fill(QColor("#6b7280"))
            output = QByteArray()
            buffer = QBuffer(output)
            if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
                return 3
            try:
                if not source.save(buffer, format_name):
                    return 3
            finally:
                buffer.close()
            encoded = bytes(output)
            inspection = inspect_image_bytes(encoded)
            if inspection.width != 48 or inspection.height != 32:
                return 3
            webp = crop_and_encode_webp(
                encoded,
                crop=(8, 0, 32, 32),
            )
            webp_inspection = inspect_image_bytes(webp)
            reloaded = QImage.fromData(webp)
            if (
                webp_inspection.format_name != "webp"
                or reloaded.isNull()
                or reloaded.width() != ICON_SIZE
                or reloaded.height() != ICON_SIZE
            ):
                return 3
    except Exception:
        return 3
    return 0
