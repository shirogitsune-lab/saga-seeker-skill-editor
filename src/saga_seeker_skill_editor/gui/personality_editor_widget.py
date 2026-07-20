"""Browsable, searchable personality keyword editor."""

from __future__ import annotations

import json

from PySide6.QtCore import QByteArray, QMimeData, Qt, Signal
from PySide6.QtGui import QDrag, QDragEnterEvent, QDragMoveEvent, QDropEvent, QFont, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from saga_seeker_skill_editor.core.character_sheet import CharacterSheet
from saga_seeker_skill_editor.core.personality_catalog import PersonalityKeyword


PERSONALITY_DRAG_MIME = "application/x-saga-seeker-personality-keyword"
KEYWORD_ID_ROLE = Qt.ItemDataRole.UserRole + 1


def _create_drag_mime(source: str, value: int) -> QMimeData:
    mime = QMimeData()
    payload = json.dumps({"source": source, "value": value}, separators=(",", ":"))
    mime.setData(PERSONALITY_DRAG_MIME, QByteArray(payload.encode("utf-8")))
    return mime


def _read_drag_mime(mime: QMimeData) -> tuple[str, int] | None:
    if not mime.hasFormat(PERSONALITY_DRAG_MIME):
        return None
    try:
        payload = json.loads(bytes(mime.data(PERSONALITY_DRAG_MIME)).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    source = payload.get("source")
    value = payload.get("value")
    if source not in {"catalog", "slot"} or not isinstance(value, int) or isinstance(value, bool):
        return None
    return source, value


class PersonalityResultTree(QTreeWidget):
    def startDrag(self, _supported_actions: Qt.DropAction) -> None:  # noqa: N802
        item = self.currentItem()
        if item is None:
            return
        keyword_id = item.data(0, Qt.ItemDataRole.UserRole)
        if keyword_id is None:
            return
        drag = QDrag(self)
        drag.setMimeData(_create_drag_mime("catalog", int(keyword_id)))
        drag.exec(Qt.DropAction.CopyAction)


class PersonalitySlotTree(QTreeWidget):
    dropRequested = Signal(str, int, int)

    def startDrag(self, _supported_actions: Qt.DropAction) -> None:  # noqa: N802
        item = self.currentItem()
        if item is None:
            return
        slot = item.data(0, Qt.ItemDataRole.UserRole)
        keyword_id = item.data(0, KEYWORD_ID_ROLE)
        if slot is None or keyword_id is None:
            return
        drag = QDrag(self)
        drag.setMimeData(_create_drag_mime("slot", int(slot)))
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if _read_drag_mime(event.mimeData()) is not None:
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        if _read_drag_mime(event.mimeData()) is not None and self.itemAt(event.position().toPoint()):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        payload = _read_drag_mime(event.mimeData())
        item = self.itemAt(event.position().toPoint())
        if payload is None or item is None:
            event.ignore()
            return
        target_slot = item.data(0, Qt.ItemDataRole.UserRole)
        if target_slot is None:
            event.ignore()
            return
        source, value = payload
        self.dropRequested.emit(source, value, int(target_slot))
        event.acceptProposedAction()


class PersonalityEditorWidget(QWidget):
    changed = Signal()
    SLOT_COUNT = 6
    FILTER_ALL = "すべて"
    CATEGORY_ORDER = ("力", "知恵", "富", "愛", "法")
    KARMA_ORDER = ("美徳", "中庸", "悪徳")

    SLOT_COLUMN = 0
    SLOT_NAME_COLUMN = 1
    SLOT_TYPE_COLUMN = 2
    SLOT_KARMA_COLUMN = 3
    SLOT_ID_COLUMN = 4
    SLOT_CHANGE_COLUMN = 5

    def __init__(self, catalog: tuple[PersonalityKeyword, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.catalog = catalog
        self.catalog_by_id = {keyword.id: keyword for keyword in catalog}
        self.baseline_ids: tuple[int | None, ...] = (None,) * self.SLOT_COUNT
        self._selected_ids: list[int | None] = [None] * self.SLOT_COUNT
        self._editable = True
        self._category = self.CATEGORY_ORDER[0]
        self._karma: str | None = None
        self._search_active = False

        heading = QLabel("性格キーワード")
        heading.setObjectName("characterName")
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("mutedText")
        self.error_label = QLabel("")
        self.error_label.setProperty("state", "error")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        self.operation_label = QLabel("")
        self.operation_label.setObjectName("operationFeedback")
        self.operation_label.setWordWrap(True)
        self.operation_label.hide()

        self.slot_tree = self._create_slot_tree()
        slot_panel = QFrame()
        slot_panel.setObjectName("editorPanel")
        slot_layout = QVBoxLayout(slot_panel)
        slot_layout.setContentsMargins(12, 10, 12, 12)
        slot_layout.setSpacing(7)
        slot_heading = QLabel("設定済みのキーワード")
        slot_heading.setObjectName("sectionHeading")
        self.move_up_button = QPushButton("上へ移動")
        self.move_up_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
        self.move_up_button.setToolTip("選択中のキーワードを一つ上の枠へ移動します")
        self.move_up_button.clicked.connect(lambda: self._move_active_slot(-1))
        self.move_down_button = QPushButton("下へ移動")
        self.move_down_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        self.move_down_button.setToolTip("選択中のキーワードを一つ下の枠へ移動します")
        self.move_down_button.clicked.connect(lambda: self._move_active_slot(1))
        slot_heading_layout = QHBoxLayout()
        slot_heading_layout.setContentsMargins(0, 0, 0, 0)
        slot_heading_layout.addWidget(slot_heading, 1)
        slot_heading_layout.addWidget(self.move_up_button)
        slot_heading_layout.addWidget(self.move_down_button)
        slot_layout.addLayout(slot_heading_layout)
        slot_layout.addWidget(self.slot_tree, 1)

        self.search_edit = QLineEdit()
        self.search_edit.setAccessibleName("性格キーワードを検索")
        self.search_edit.setPlaceholderText("キーワード名を部分一致で検索")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._search_changed)
        self.search_edit.returnPressed.connect(self._apply_result)
        search_label = QLabel("検索")
        search_label.setBuddy(self.search_edit)
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_edit, 1)
        self.category_group = QButtonGroup(self)
        self.category_group.setExclusive(True)
        self.category_buttons: dict[str, QPushButton] = {}
        self._category_filters: tuple[str | None, ...] = (None, *self.CATEGORY_ORDER)
        category_layout = QVBoxLayout()
        category_layout.setContentsMargins(0, 0, 0, 0)
        category_layout.setSpacing(6)
        for button_id, category in enumerate(self._category_filters):
            label = self.FILTER_ALL if category is None else category
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("category", True)
            button.setAccessibleName(f"系統: {label}")
            button.setMinimumWidth(82)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.category_group.addButton(button, button_id)
            self.category_buttons[label] = button
            category_layout.addWidget(button)
        self.category_buttons[self._category].setChecked(True)
        self.category_group.idClicked.connect(self._category_clicked)
        category_layout.addStretch(1)

        self.karma_group = QButtonGroup(self)
        self.karma_group.setExclusive(True)
        self.karma_buttons: dict[str, QPushButton] = {}
        self._karma_filters: tuple[str | None, ...] = (None, *self.KARMA_ORDER)
        karma_layout = QHBoxLayout()
        karma_layout.setContentsMargins(0, 0, 0, 0)
        karma_layout.setSpacing(6)
        karma_label = QLabel("傾向")
        karma_label.setObjectName("filterLabel")
        karma_layout.addWidget(karma_label)
        for button_id, karma in enumerate(self._karma_filters):
            label = self.FILTER_ALL if karma is None else karma
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("filterOption", True)
            button.setAccessibleName(f"傾向: {label}")
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.karma_group.addButton(button, button_id)
            self.karma_buttons[label] = button
            karma_layout.addWidget(button)
        self.karma_buttons[self.FILTER_ALL].setChecked(True)
        self.karma_group.idClicked.connect(self._karma_clicked)
        karma_layout.addStretch(1)

        self.result_tree = self._create_result_tree()
        self.result_tree.currentItemChanged.connect(self._result_selected)
        self.result_tree.itemDoubleClicked.connect(self._result_activated)

        category_widget = QWidget()
        category_widget.setLayout(category_layout)
        browser_layout = QHBoxLayout()
        browser_layout.setContentsMargins(0, 0, 0, 0)
        browser_layout.setSpacing(8)
        browser_layout.addWidget(category_widget)
        browser_layout.addWidget(self.result_tree, 1)

        self.picker_heading = QLabel("枠 1 に設定")
        self.picker_heading.setObjectName("sectionHeading")
        self.scope_label = QLabel("")
        self.scope_label.setObjectName("mutedText")
        self.selection_detail_label = QLabel("候補を選択してください")
        self.selection_detail_label.setObjectName("mutedText")
        self.selection_detail_label.setWordWrap(True)
        self.apply_button = QPushButton("この枠に設定")
        self.apply_button.setProperty("role", "primary")
        self.apply_button.clicked.connect(self._apply_result)
        self.clear_button = QPushButton("未設定にする")
        self.clear_button.clicked.connect(self._clear_active_slot)

        action_layout = QHBoxLayout()
        action_layout.addWidget(self.selection_detail_label, 1)
        action_layout.addWidget(self.clear_button)
        action_layout.addWidget(self.apply_button)

        picker_panel = QFrame()
        picker_panel.setObjectName("pickerPanel")
        picker_layout = QVBoxLayout(picker_panel)
        picker_layout.setContentsMargins(12, 10, 12, 12)
        picker_layout.setSpacing(7)
        picker_layout.addWidget(self.picker_heading)
        picker_layout.addLayout(search_layout)
        picker_layout.addLayout(karma_layout)
        picker_layout.addWidget(self.scope_label)
        picker_layout.addLayout(browser_layout, 1)
        picker_layout.addLayout(action_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(slot_panel)
        splitter.addWidget(picker_panel)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([390, 650])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(heading)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.error_label)
        layout.addWidget(self.operation_label)
        layout.addWidget(splitter, 1)

        self._populate_empty_slots()
        self.slot_tree.setCurrentItem(self.slot_tree.topLevelItem(0))
        self._rebuild_results()
        self._sync_summary()

    def set_sheet(self, sheet: CharacterSheet) -> None:
        ids = [int(entry.keyword["id"]) for entry in sheet.personality_entries]
        ids.extend([None] * (self.SLOT_COUNT - len(ids)))
        self.baseline_ids = tuple(ids[: self.SLOT_COUNT])
        self._selected_ids = list(self.baseline_ids)
        self._editable = not sheet.read_only and not sheet.personality_read_only
        self.search_edit.setEnabled(self._editable)
        self.result_tree.setEnabled(self._editable)
        for button in self.category_buttons.values():
            button.setEnabled(self._editable)
        for button in self.karma_buttons.values():
            button.setEnabled(self._editable)
        self.apply_button.setEnabled(False)
        self.clear_button.setEnabled(self._editable)
        self._set_operation_feedback(None)
        self._sync_all_slot_rows()
        self._sync_active_slot()

        if sheet.personality_read_only:
            self.set_validation_error(f"性格キーワードは読み取り専用です: {sheet.personality_read_only_reason}")
        elif sheet.read_only:
            self.set_validation_error(f"シートは読み取り専用です: {sheet.read_only_reason}")
        else:
            self.set_validation_error(None)
        self._rebuild_results()
        self._sync_summary()

    def selected_ids(self) -> tuple[int | None, ...]:
        return tuple(self._selected_ids)

    def changed_indices(self) -> set[int]:
        return {
            index
            for index, (current, baseline) in enumerate(
                zip(self.selected_ids(), self.baseline_ids, strict=True)
            )
            if current != baseline
        }

    def reset(self) -> None:
        self._selected_ids = list(self.baseline_ids)
        self.search_edit.clear()
        self._set_operation_feedback(None)
        self._sync_all_slot_rows()
        self._sync_active_slot()
        self.set_validation_error(None)
        self._rebuild_results()
        self._sync_summary()
        self.changed.emit()

    def set_validation_error(self, message: str | None) -> None:
        self.error_label.setText(message or "")
        self.error_label.setVisible(bool(message))

    def focus_first_slot(self) -> None:
        self.slot_tree.setFocus()
        self.slot_tree.setCurrentItem(self.slot_tree.topLevelItem(0))

    def visible_result_ids(self) -> tuple[int, ...]:
        ids: list[int] = []
        for group_index in range(self.result_tree.topLevelItemCount()):
            group = self.result_tree.topLevelItem(group_index)
            for child_index in range(group.childCount()):
                keyword_id = group.child(child_index).data(0, Qt.ItemDataRole.UserRole)
                if keyword_id is not None:
                    ids.append(int(keyword_id))
        return tuple(ids)

    def _create_slot_tree(self) -> PersonalitySlotTree:
        tree = PersonalitySlotTree()
        tree.setObjectName("personalitySlots")
        tree.setHeaderLabels(["枠", "性格キーワード", "系統", "カルマ", "ID", "変更"])
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tree.setAccessibleName("設定済み性格キーワード一覧")
        tree.setAccessibleDescription(
            "設定済みキーワードをドラッグして並び替えできます。候補をここへドロップして追加できます。"
        )
        tree.setDragEnabled(True)
        tree.setAcceptDrops(True)
        tree.setDropIndicatorShown(True)
        tree.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        tree.setDragDropOverwriteMode(False)
        header = tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(self.SLOT_COLUMN, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(self.SLOT_COLUMN, 34)
        header.setSectionResizeMode(self.SLOT_NAME_COLUMN, QHeaderView.ResizeMode.Stretch)
        for column in (
            self.SLOT_TYPE_COLUMN,
            self.SLOT_KARMA_COLUMN,
            self.SLOT_ID_COLUMN,
            self.SLOT_CHANGE_COLUMN,
        ):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        tree.currentItemChanged.connect(self._slot_selected)
        tree.dropRequested.connect(self._handle_drop)
        return tree

    def _create_result_tree(self) -> PersonalityResultTree:
        tree = PersonalityResultTree()
        tree.setObjectName("personalityResults")
        tree.setHeaderLabels(["性格キーワード", "系統", "カルマ", "ID", "設定"])
        tree.setRootIsDecorated(True)
        tree.setAlternatingRowColors(True)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tree.setAccessibleName("性格キーワード候補")
        tree.setAccessibleDescription("候補を設定済みキーワード一覧へドラッグして追加できます")
        tree.setDragEnabled(True)
        tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        tree.setDefaultDropAction(Qt.DropAction.CopyAction)
        header = tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 5):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        return tree

    def _populate_empty_slots(self) -> None:
        self.slot_tree.clear()
        for slot in range(self.SLOT_COUNT):
            item = QTreeWidgetItem([str(slot + 1), "（未設定）", "-", "-", "-", "変更なし"])
            item.setData(self.SLOT_COLUMN, Qt.ItemDataRole.UserRole, slot)
            item.setTextAlignment(self.SLOT_COLUMN, Qt.AlignmentFlag.AlignCenter)
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsDragEnabled
                | Qt.ItemFlag.ItemIsDropEnabled
            )
            self.slot_tree.addTopLevelItem(item)

    def _slot_selected(self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None) -> None:
        if current is None:
            return
        self._sync_active_slot()
        self._rebuild_results()

    def _sync_active_slot(self) -> None:
        slot = self._active_slot()
        self.picker_heading.setText(f"枠 {slot + 1} に設定")
        keyword_id = self._selected_ids[slot]
        self.clear_button.setEnabled(self._editable and keyword_id is not None)
        assigned_count = len(self._ordered_keyword_ids())
        self.move_up_button.setEnabled(self._editable and keyword_id is not None and slot > 0)
        self.move_down_button.setEnabled(
            self._editable and keyword_id is not None and slot < assigned_count - 1
        )

    def _category_clicked(self, button_id: int) -> None:
        self._category = self._category_filters[button_id]
        self._rebuild_results()

    def _karma_clicked(self, button_id: int) -> None:
        self._karma = self._karma_filters[button_id]
        self._rebuild_results()

    def _set_category(self, category: str | None) -> None:
        label = self.FILTER_ALL if category is None else category
        if label not in self.category_buttons:
            return
        self._category = category
        self.category_buttons[label].setChecked(True)

    def _search_changed(self, text: str) -> None:
        query_active = bool(text.strip())
        if query_active and not self._search_active:
            self._set_category(None)
        self._search_active = query_active
        self._rebuild_results()

    def _rebuild_results(self, _text: str = "") -> None:
        query = self.search_edit.text().strip().casefold()
        current_id = self._current_result_id()
        active_id = self._selected_ids[self._active_slot()]
        candidates = [
            keyword
            for keyword in self.catalog
            if (self._category is None or keyword.type == self._category)
            and (self._karma is None or keyword.karma == self._karma)
            and (not query or query in keyword.name.casefold())
        ]
        category_text = self.FILTER_ALL if self._category is None else self._category
        karma_text = self.FILTER_ALL if self._karma is None else self._karma
        scope = f"系統: {category_text} / 傾向: {karma_text}"
        if query:
            scope += f" / 部分一致検索: {self.search_edit.text().strip()}"
        self.scope_label.setText(f"{scope} / {len(candidates)}件")

        self.result_tree.blockSignals(True)
        self.result_tree.clear()
        first_result: QTreeWidgetItem | None = None
        restore_result: QTreeWidgetItem | None = None
        for karma in self.KARMA_ORDER:
            keywords = [keyword for keyword in candidates if keyword.karma == karma]
            if not keywords:
                continue
            group = QTreeWidgetItem([f"{karma} ({len(keywords)}件)"])
            group.setFlags(Qt.ItemFlag.ItemIsEnabled)
            group.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
            font = QFont(group.font(0))
            font.setBold(True)
            group.setFont(0, font)
            self.result_tree.addTopLevelItem(group)
            group.setFirstColumnSpanned(True)
            for keyword in keywords:
                assigned_slot = self._slot_for_keyword(keyword.id)
                if assigned_slot is None:
                    assigned_text = "-"
                elif assigned_slot == self._active_slot():
                    assigned_text = "この枠"
                else:
                    assigned_text = f"枠 {assigned_slot + 1}"
                item = QTreeWidgetItem(
                    [keyword.name, keyword.type, keyword.karma, str(keyword.id), assigned_text]
                )
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsDragEnabled
                )
                item.setData(0, Qt.ItemDataRole.UserRole, keyword.id)
                item.setToolTip(0, f"{keyword.name} / {keyword.type} / {keyword.karma} / ID {keyword.id}")
                group.addChild(item)
                if first_result is None:
                    first_result = item
                if keyword.id == current_id or (current_id is None and keyword.id == active_id):
                    restore_result = item
            group.setExpanded(True)
        self.result_tree.blockSignals(False)
        self.result_tree.setCurrentItem(restore_result or first_result)
        self._result_selected(self.result_tree.currentItem(), None)

    def _result_selected(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        keyword_id = self._keyword_id_from_item(current)
        keyword = self.catalog_by_id.get(keyword_id)
        if keyword is None:
            self.selection_detail_label.setText("候補を選択してください")
            self.apply_button.setEnabled(False)
            return
        assigned_slot = self._slot_for_keyword(keyword.id)
        active_slot = self._active_slot()
        details = f"{keyword.name} / {keyword.type} / {keyword.karma} / ID {keyword.id}"
        if assigned_slot is not None and assigned_slot != active_slot:
            self.selection_detail_label.setText(f"{details}　すでに枠 {assigned_slot + 1} へ設定されています")
            self.apply_button.setText("別の枠で使用中")
            self.apply_button.setEnabled(False)
        elif assigned_slot == active_slot:
            self.selection_detail_label.setText(f"{details}　現在この枠に設定されています")
            self.apply_button.setText("設定済み")
            self.apply_button.setEnabled(False)
        else:
            self.selection_detail_label.setText(details)
            self.apply_button.setText("この枠に設定")
            self.apply_button.setEnabled(self._editable)

    def _result_activated(self, item: QTreeWidgetItem, _column: int) -> None:
        if self._keyword_id_from_item(item) is not None and self.apply_button.isEnabled():
            self._apply_result()

    def _handle_drop(self, source: str, value: int, target_slot: int) -> None:
        if not self._editable:
            self._set_operation_feedback("読み取り専用のため並び替えできません", error=True)
            return
        if source == "slot":
            if value < 0 or value >= self.SLOT_COUNT:
                return
            keyword_id = self._selected_ids[value]
            if keyword_id is None:
                return
        elif source == "catalog":
            keyword_id = value
            if keyword_id not in self.catalog_by_id:
                return
        else:
            return
        self._insert_keyword(keyword_id, target_slot)

    def _insert_keyword(self, keyword_id: int, target_slot: int) -> bool:
        ordered = self._ordered_keyword_ids()
        already_assigned = keyword_id in ordered
        if not already_assigned and len(ordered) >= self.SLOT_COUNT:
            self._set_operation_feedback(
                "6枠すべてが設定済みです。新しいキーワードを挿入するには、先に一つ削除してください。",
                error=True,
            )
            return False

        if already_assigned:
            ordered.remove(keyword_id)
        insert_at = min(max(target_slot, 0), len(ordered))
        ordered.insert(insert_at, keyword_id)
        keyword = self.catalog_by_id[keyword_id]
        action = "移動" if already_assigned else "追加"
        return self._apply_order(
            ordered,
            selected_slot=insert_at,
            message=f"「{keyword.name}」を枠 {insert_at + 1} へ{action}しました。",
        )

    def _move_active_slot(self, offset: int) -> None:
        slot = self._active_slot()
        keyword_id = self._selected_ids[slot]
        if not self._editable or keyword_id is None:
            return
        target_slot = slot + offset
        assigned_count = len(self._ordered_keyword_ids())
        if target_slot < 0 or target_slot >= assigned_count:
            return
        self._insert_keyword(keyword_id, target_slot)

    def _apply_result(self) -> None:
        keyword_id = self._current_result_id()
        if keyword_id is None or not self.apply_button.isEnabled():
            return
        slot = self._active_slot()
        self._selected_ids[slot] = keyword_id
        keyword = self.catalog_by_id[keyword_id]
        self._set_operation_feedback(f"「{keyword.name}」を枠 {slot + 1} へ設定しました。")
        self._sync_slot_row(slot)
        self._sync_active_slot()
        self._sync_summary()
        self._rebuild_results()
        self.changed.emit()

    def _clear_active_slot(self) -> None:
        if not self._editable:
            return
        slot = self._active_slot()
        keyword_id = self._selected_ids[slot]
        if keyword_id is None:
            return
        keyword = self.catalog_by_id.get(keyword_id)
        had_following = any(value is not None for value in self._selected_ids[slot + 1 :])
        ordered = self._ordered_keyword_ids()
        ordered.remove(keyword_id)
        name = keyword.name if keyword is not None else str(keyword_id)
        if had_following:
            message = f"「{name}」を削除し、後ろのキーワードを前へ詰めました。"
        else:
            message = f"「{name}」を削除しました。"
        self._apply_order(ordered, selected_slot=slot, message=message)

    def _ordered_keyword_ids(self) -> list[int]:
        return [keyword_id for keyword_id in self._selected_ids if keyword_id is not None]

    def _apply_order(self, ordered: list[int], *, selected_slot: int, message: str) -> bool:
        padded: list[int | None] = ordered[: self.SLOT_COUNT]
        padded.extend([None] * (self.SLOT_COUNT - len(padded)))
        if padded == self._selected_ids:
            self._set_operation_feedback("並び順は変更されていません。")
            return False

        self._selected_ids = padded
        selected_slot = min(max(selected_slot, 0), self.SLOT_COUNT - 1)
        self.slot_tree.blockSignals(True)
        self._sync_all_slot_rows()
        self.slot_tree.setCurrentItem(self.slot_tree.topLevelItem(selected_slot))
        self.slot_tree.blockSignals(False)
        self._set_operation_feedback(message)
        self._sync_active_slot()
        self._sync_summary()
        self._rebuild_results()
        self.changed.emit()
        return True

    def _set_operation_feedback(self, message: str | None, *, error: bool = False) -> None:
        self.operation_label.setText(message or "")
        self.operation_label.setProperty("state", "error" if error else "normal")
        self.operation_label.setVisible(bool(message))
        self.operation_label.style().unpolish(self.operation_label)
        self.operation_label.style().polish(self.operation_label)
        self.operation_label.update()

    def _sync_all_slot_rows(self) -> None:
        for slot in range(self.SLOT_COUNT):
            self._sync_slot_row(slot)

    def _sync_slot_row(self, slot: int) -> None:
        item = self.slot_tree.topLevelItem(slot)
        keyword_id = self._selected_ids[slot]
        keyword = self.catalog_by_id.get(keyword_id)
        if keyword is None:
            values = ("（未設定）", "-", "-", "-")
        else:
            values = (keyword.name, keyword.type, keyword.karma, str(keyword.id))
        item.setText(self.SLOT_NAME_COLUMN, values[0])
        item.setText(self.SLOT_TYPE_COLUMN, values[1])
        item.setText(self.SLOT_KARMA_COLUMN, values[2])
        item.setText(self.SLOT_ID_COLUMN, values[3])
        item.setData(self.SLOT_COLUMN, KEYWORD_ID_ROLE, keyword_id)
        item.setToolTip(self.SLOT_NAME_COLUMN, values[0])
        changed = keyword_id != self.baseline_ids[slot]
        item.setText(self.SLOT_CHANGE_COLUMN, "変更あり" if changed else "変更なし")
        item.setIcon(
            self.SLOT_CHANGE_COLUMN,
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton) if changed else QIcon(),
        )

    def _sync_summary(self) -> None:
        assigned = sum(keyword_id is not None for keyword_id in self.selected_ids())
        changed = len(self.changed_indices())
        self.summary_label.setText(f"設定済み {assigned} / 6件 | 変更 {changed}件")

    def _active_slot(self) -> int:
        current = self.slot_tree.currentItem()
        if current is None:
            return 0
        value = current.data(self.SLOT_COLUMN, Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else 0

    def _slot_for_keyword(self, keyword_id: int) -> int | None:
        try:
            return self._selected_ids.index(keyword_id)
        except ValueError:
            return None

    def _current_result_id(self) -> int | None:
        return self._keyword_id_from_item(self.result_tree.currentItem())

    @staticmethod
    def _keyword_id_from_item(item: QTreeWidgetItem | None) -> int | None:
        if item is None:
            return None
        value = item.data(0, Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None
