"""Bounded square-crop dialog for replacement character icons."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from saga_seeker_skill_editor.gui.image_pipeline import (
    ImageInspection,
    ImageSafetyError,
    crop_and_encode_webp,
    inspect_image_bytes,
)


class ImageCropDialog(QDialog):
    def __init__(self, encoded: bytes, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("キャラクター画像を正方形に切り抜く")
        self._encoded = encoded
        self.inspection: ImageInspection = inspect_image_bytes(encoded)
        self._source = QImage.fromData(encoded)
        if self._source.isNull():
            raise ImageSafetyError("画像をデコードできません")

        maximum_square = min(
            self.inspection.width,
            self.inspection.height,
        )
        self.x_spin = QSpinBox()
        self.y_spin = QSpinBox()
        self.size_spin = QSpinBox()
        self.size_spin.setRange(1, maximum_square)
        self.size_spin.setValue(maximum_square)
        self.x_spin.setRange(0, self.inspection.width - maximum_square)
        self.y_spin.setRange(0, self.inspection.height - maximum_square)
        self.x_spin.setValue((self.inspection.width - maximum_square) // 2)
        self.y_spin.setValue((self.inspection.height - maximum_square) // 2)
        self.x_spin.setAccessibleName("切抜き開始位置X")
        self.y_spin.setAccessibleName("切抜き開始位置Y")
        self.size_spin.setAccessibleName("切抜き正方形サイズ")

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(320, 320)
        self.preview.setAccessibleName("切抜き後の画像プレビュー")
        self.description = QLabel(
            f"{self.inspection.width} × {self.inspection.height} px / "
            "保存時に512 × 512 px・WebP品質90へ変換します"
        )
        self.description.setWordWrap(True)
        self.description.setObjectName("mutedText")

        controls = QFormLayout()
        controls.addRow("左端 X", self.x_spin)
        controls.addRow("上端 Y", self.y_spin)
        controls.addRow("正方形サイズ", self.size_spin)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(
            "この切抜きを使用"
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.description)
        layout.addWidget(self.preview)
        layout.addLayout(controls)
        layout.addWidget(buttons)

        self.size_spin.valueChanged.connect(self._crop_size_changed)
        self.x_spin.valueChanged.connect(self._update_preview)
        self.y_spin.valueChanged.connect(self._update_preview)
        self._update_preview()

    def crop_box(self) -> tuple[int, int, int, int]:
        size = self.size_spin.value()
        return (self.x_spin.value(), self.y_spin.value(), size, size)

    def processed_webp(self) -> bytes:
        return crop_and_encode_webp(self._encoded, crop=self.crop_box())

    def _crop_size_changed(self, size: int) -> None:
        self.x_spin.setMaximum(self.inspection.width - size)
        self.y_spin.setMaximum(self.inspection.height - size)
        self._update_preview()

    def _update_preview(self) -> None:
        x, y, width, height = self.crop_box()
        cropped = self._source.copy(x, y, width, height)
        self.preview.setPixmap(
            QPixmap.fromImage(cropped).scaled(
                320,
                320,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
