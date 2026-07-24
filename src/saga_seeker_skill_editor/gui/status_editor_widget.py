"""Six visible character-status controls."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QWidget

from saga_seeker_skill_editor.core.character_sheet import (
    CharacterSheet,
    CharacterSheetDraft,
    STATUS_HTML_FIELDS,
    STATUS_RANKS,
)


STATUS_LABELS = {
    "strength": "筋力",
    "endurance": "耐久力",
    "intelligence": "知力",
    "mentalStrength": "精神力",
    "agility": "素早さ",
    "luck": "運",
}


class StatusEditorWidget(QWidget):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._draft: CharacterSheetDraft | None = None
        self._loading = False
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setObjectName("mutedText")
        self.rank_boxes: dict[str, QComboBox] = {}
        form = QFormLayout(self)
        form.addRow(self.message)
        for key, _english_label in STATUS_HTML_FIELDS:
            box = QComboBox()
            box.addItems(("E", "D", "C", "B", "A", "S"))
            box.setAccessibleName(STATUS_LABELS[key])
            box.currentTextChanged.connect(
                lambda value, key=key: self._rank_changed(key, value)
            )
            self.rank_boxes[key] = box
            form.addRow(STATUS_LABELS[key], box)

    def set_sheet(
        self,
        sheet: CharacterSheet,
        draft: CharacterSheetDraft,
    ) -> None:
        self._draft = draft
        data = sheet.data.get("data")
        status = data.get("status") if isinstance(data, dict) else {}
        section = sheet.diagnostic_baseline.for_section("status")
        self._loading = True
        blockers = [QSignalBlocker(box) for box in self.rank_boxes.values()]
        for key, box in self.rank_boxes.items():
            value = status.get(key, "E") if isinstance(status, dict) else "E"
            box.setCurrentText(value if value in STATUS_RANKS else "E")
            box.setEnabled(section.editable)
            box.setToolTip(
                "S〜Eから選択します"
                if section.editable
                else section.read_only_reason
            )
        del blockers
        self._loading = False
        self.message.setText(
            ""
            if section.editable
            else f"読み取り専用: {section.read_only_reason}"
        )

    def _rank_changed(self, key: str, value: str) -> None:
        if self._loading or self._draft is None:
            return
        self._draft.set_status(key, value)
        self.changed.emit()
