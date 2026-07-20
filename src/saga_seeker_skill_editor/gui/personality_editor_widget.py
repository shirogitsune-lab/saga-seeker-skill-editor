"""Fixed-catalog personality keyword editor."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from saga_seeker_skill_editor.core.character_sheet import CharacterSheet
from saga_seeker_skill_editor.core.personality_catalog import PersonalityKeyword


class PersonalityEditorWidget(QWidget):
    changed = Signal()
    SLOT_COUNT = 6

    def __init__(self, catalog: tuple[PersonalityKeyword, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.catalog = catalog
        self.catalog_by_id = {keyword.id: keyword for keyword in catalog}
        self.baseline_ids: tuple[int | None, ...] = (None,) * self.SLOT_COUNT
        self.combos: list[QComboBox] = []
        self.type_labels: list[QLabel] = []
        self.karma_labels: list[QLabel] = []
        self.id_labels: list[QLabel] = []
        self.change_labels: list[QLabel] = []

        heading = QLabel("性格キーワード")
        heading.setObjectName("characterName")
        self.summary_label = QLabel("ゲーム内キーワードから最大6件を選択できます")
        self.summary_label.setObjectName("mutedText")
        self.error_label = QLabel("")
        self.error_label.setProperty("state", "error")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        panel = QFrame()
        panel.setObjectName("editorPanel")
        grid = QGridLayout(panel)
        grid.setContentsMargins(14, 12, 14, 14)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        headers = ("枠", "性格キーワード", "系統", "カルマ", "ID", "変更")
        for column, text in enumerate(headers):
            label = QLabel(text)
            label.setObjectName("mutedText")
            grid.addWidget(label, 0, column)

        for slot in range(self.SLOT_COUNT):
            slot_label = QLabel(str(slot + 1))
            combo = QComboBox()
            combo.setAccessibleName(f"性格キーワード {slot + 1}")
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            combo.setMaxVisibleItems(20)
            combo.addItem("（未設定）", None)
            for keyword in catalog:
                combo.addItem(f"{keyword.name}  [{keyword.type} / {keyword.karma}]", keyword.id)
            type_label = QLabel("-")
            karma_label = QLabel("-")
            id_label = QLabel("-")
            id_label.setObjectName("technicalValue")
            change_label = QLabel("変更なし")

            grid.addWidget(slot_label, slot + 1, 0)
            grid.addWidget(combo, slot + 1, 1)
            grid.addWidget(type_label, slot + 1, 2)
            grid.addWidget(karma_label, slot + 1, 3)
            grid.addWidget(id_label, slot + 1, 4)
            grid.addWidget(change_label, slot + 1, 5)
            self.combos.append(combo)
            self.type_labels.append(type_label)
            self.karma_labels.append(karma_label)
            self.id_labels.append(id_label)
            self.change_labels.append(change_label)
            combo.currentIndexChanged.connect(lambda _value, index=slot: self._selection_changed(index))

        grid.setColumnStretch(1, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(heading)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.error_label)
        layout.addWidget(panel)
        layout.addStretch(1)

    def set_sheet(self, sheet: CharacterSheet) -> None:
        ids = [int(entry.keyword["id"]) for entry in sheet.personality_entries]
        ids.extend([None] * (self.SLOT_COUNT - len(ids)))
        self.baseline_ids = tuple(ids[: self.SLOT_COUNT])
        for slot, (combo, keyword_id) in enumerate(zip(self.combos, self.baseline_ids, strict=True)):
            combo.blockSignals(True)
            combo.setCurrentIndex(combo.findData(keyword_id))
            combo.blockSignals(False)
            combo.setEnabled(not sheet.read_only and not sheet.personality_read_only)
            self._sync_row(slot)

        if sheet.personality_read_only:
            self.set_validation_error(f"性格キーワードは読み取り専用です: {sheet.personality_read_only_reason}")
        elif sheet.read_only:
            self.set_validation_error(f"シートは読み取り専用です: {sheet.read_only_reason}")
        else:
            self.set_validation_error(None)
        self._sync_summary()

    def selected_ids(self) -> tuple[int | None, ...]:
        return tuple(combo.currentData() for combo in self.combos)

    def changed_indices(self) -> set[int]:
        return {
            index
            for index, (current, baseline) in enumerate(
                zip(self.selected_ids(), self.baseline_ids, strict=True)
            )
            if current != baseline
        }

    def reset(self) -> None:
        for slot, (combo, keyword_id) in enumerate(zip(self.combos, self.baseline_ids, strict=True)):
            combo.blockSignals(True)
            combo.setCurrentIndex(combo.findData(keyword_id))
            combo.blockSignals(False)
            self._sync_row(slot)
        self.set_validation_error(None)
        self._sync_summary()
        self.changed.emit()

    def set_validation_error(self, message: str | None) -> None:
        self.error_label.setText(message or "")
        self.error_label.setVisible(bool(message))

    def focus_first_slot(self) -> None:
        self.combos[0].setFocus()

    def _selection_changed(self, slot: int) -> None:
        self._sync_row(slot)
        self._sync_summary()
        self.changed.emit()

    def _sync_row(self, slot: int) -> None:
        keyword_id = self.combos[slot].currentData()
        keyword = self.catalog_by_id.get(keyword_id)
        self.type_labels[slot].setText(keyword.type if keyword else "-")
        self.karma_labels[slot].setText(keyword.karma if keyword else "-")
        self.id_labels[slot].setText(str(keyword.id) if keyword else "-")
        changed = keyword_id != self.baseline_ids[slot]
        self.change_labels[slot].setText("変更あり" if changed else "変更なし")

    def _sync_summary(self) -> None:
        assigned = sum(keyword_id is not None for keyword_id in self.selected_ids())
        changed = len(self.changed_indices())
        self.summary_label.setText(f"設定済み {assigned} / 6件 | 変更 {changed}件")
