"""Single-selection, read-only skill overview."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from saga_seeker_skill_editor.core.character_sheet import SkillEntry
from saga_seeker_skill_editor.core.skill_classifier import SkillKind


class SkillListWidget(QTreeWidget):
    SLOT_COLUMN = 0
    NAME_COLUMN = 1
    KIND_COLUMN = 2
    PROTECTION_COLUMN = 3
    CHANGE_COLUMN = 4

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("skillList")
        self.setHeaderLabels(["No.", "スキル名", "種別", "保護", "変更"])
        self.setRootIsDecorated(False)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSortingEnabled(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAccessibleName("スキル一覧")

        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(self.SLOT_COLUMN, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(self.SLOT_COLUMN, 44)
        header.setSectionResizeMode(self.NAME_COLUMN, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.KIND_COLUMN, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.PROTECTION_COLUMN, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.CHANGE_COLUMN, QHeaderView.ResizeMode.ResizeToContents)

    def populate(self, entries: tuple[SkillEntry, ...] | list[SkillEntry], *, slot_count: int) -> None:
        self.clear()
        for entry in entries:
            name = str(entry.skill.get("name", "") or "")
            display_name = name or "（未設定）"
            item = QTreeWidgetItem(
                [
                    str(entry.index + 1),
                    display_name,
                    self._kind_label(entry.classification.kind),
                    self._protection_label(entry.classification.kind),
                    "変更なし",
                ]
            )
            item.setData(self.SLOT_COLUMN, Qt.ItemDataRole.UserRole, entry.index)
            item.setToolTip(self.NAME_COLUMN, name or "スキル名は未設定です")
            item.setTextAlignment(self.SLOT_COLUMN, Qt.AlignmentFlag.AlignCenter)
            item.setTextAlignment(self.PROTECTION_COLUMN, Qt.AlignmentFlag.AlignCenter)
            item.setTextAlignment(self.CHANGE_COLUMN, Qt.AlignmentFlag.AlignCenter)
            item.setIcon(self.KIND_COLUMN, self._kind_icon(entry.classification.kind))
            if entry.classification.kind == SkillKind.DEFAULT:
                item.setIcon(self.PROTECTION_COLUMN, self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning))
            self.addTopLevelItem(item)
        for slot_index in range(len(entries), slot_count):
            item = QTreeWidgetItem(
                [
                    str(slot_index + 1),
                    "（未使用）",
                    "未使用枠",
                    "自動追加可",
                    "変更なし",
                ]
            )
            item.setData(self.SLOT_COLUMN, Qt.ItemDataRole.UserRole, slot_index)
            item.setToolTip(self.NAME_COLUMN, "JSONにスキルが登録されていない未使用枠です")
            item.setTextAlignment(self.SLOT_COLUMN, Qt.AlignmentFlag.AlignCenter)
            item.setTextAlignment(self.PROTECTION_COLUMN, Qt.AlignmentFlag.AlignCenter)
            item.setTextAlignment(self.CHANGE_COLUMN, Qt.AlignmentFlag.AlignCenter)
            item.setIcon(self.KIND_COLUMN, self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder))
            self.addTopLevelItem(item)

    def selected_skill_index(self) -> int | None:
        item = self.currentItem()
        if item is None:
            return None
        value = item.data(self.SLOT_COLUMN, Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None

    def set_changed(self, index: int, changed: bool) -> None:
        item = self.topLevelItem(index)
        if item is None:
            return
        item.setText(self.CHANGE_COLUMN, "変更あり" if changed else "変更なし")
        item.setIcon(
            self.CHANGE_COLUMN,
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton) if changed else QIcon(),
        )

    def update_name(self, index: int, name: str) -> None:
        item = self.topLevelItem(index)
        if item is None:
            return
        item.setText(self.NAME_COLUMN, name or "（未設定）")
        item.setToolTip(self.NAME_COLUMN, name or "スキル名は未設定です")

    def update_vacant_name(self, index: int, name: str) -> None:
        item = self.topLevelItem(index)
        if item is None:
            return
        item.setText(self.NAME_COLUMN, name or "（未使用）")
        item.setToolTip(self.NAME_COLUMN, name or "JSONにスキルが登録されていない未使用枠です")

    def _kind_icon(self, kind: SkillKind):
        icon_by_kind = {
            SkillKind.DEFAULT: QStyle.StandardPixmap.SP_FileIcon,
            SkillKind.ORIGINAL: QStyle.StandardPixmap.SP_DialogApplyButton,
            SkillKind.ORIGINAL_NEEDS_ID_REPAIR: QStyle.StandardPixmap.SP_MessageBoxWarning,
            SkillKind.EMPTY_SLOT: QStyle.StandardPixmap.SP_FileDialogNewFolder,
            SkillKind.UNKNOWN: QStyle.StandardPixmap.SP_MessageBoxCritical,
        }
        return self.style().standardIcon(icon_by_kind.get(kind, QStyle.StandardPixmap.SP_FileIcon))

    @staticmethod
    def _kind_label(kind: SkillKind) -> str:
        labels = {
            SkillKind.DEFAULT: "デフォルト",
            SkillKind.ORIGINAL: "オリジナル",
            SkillKind.ORIGINAL_NEEDS_ID_REPAIR: "要ID修復",
            SkillKind.EMPTY_SLOT: "空スロット",
            SkillKind.UNKNOWN: "形式不明",
        }
        return labels.get(kind, "形式不明")

    @staticmethod
    def _protection_label(kind: SkillKind) -> str:
        if kind == SkillKind.DEFAULT:
            return "保護中"
        if kind == SkillKind.UNKNOWN:
            return "編集不可"
        return "なし"
