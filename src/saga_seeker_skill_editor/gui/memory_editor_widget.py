"""Ordered normal and placeholder memory editor."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from saga_seeker_skill_editor.core.character_sheet import (
    CharacterSheet,
    CharacterSheetDraft,
    CharacterSheetRenderError,
)
from saga_seeker_skill_editor.core.phase0_candidate_sheet import GenerationInputs


MEMORY_FIELDS = (
    ("title", "タイトル"),
    ("summary", "概要"),
    ("location", "場所"),
    ("intent", "意図"),
    ("outcome", "結果"),
)


class MemoryEditorWidget(QWidget):
    changed = Signal()

    def __init__(
        self,
        generation_factory: Callable[[], GenerationInputs],
    ) -> None:
        super().__init__()
        self._generation_factory = generation_factory
        self._sheet: CharacterSheet | None = None
        self._draft: CharacterSheetDraft | None = None
        self._loading = False
        self._editable = False
        self._display_source_values: dict[str, str] = {}
        self._edited_field_keys: set[str] = set()

        self.memory_list = QListWidget()
        self.memory_list.setAccessibleName("思い出一覧")
        self.memory_list.currentRowChanged.connect(self._selection_changed)

        self.add_button = QPushButton("通常思い出を追加")
        self.fill_button = QPushButton("空白保持枠を15件まで補充")
        self.up_button = QPushButton("上へ")
        self.down_button = QPushButton("下へ")
        self.remove_button = QPushButton("一覧から削除")
        self.replace_button = QPushButton("空白保持枠へ置換")
        self.convert_button = QPushButton("通常思い出へ変換")
        self.add_button.clicked.connect(self.add_normal_memory)
        self.fill_button.clicked.connect(self.fill_placeholders)
        self.up_button.clicked.connect(lambda: self.move_selected(-1))
        self.down_button.clicked.connect(lambda: self.move_selected(1))
        self.remove_button.clicked.connect(self.remove_selected)
        self.replace_button.clicked.connect(self.replace_selected)
        self.convert_button.clicked.connect(self.convert_selected)
        self.move_up_shortcut = QShortcut(QKeySequence("Alt+Up"), self)
        self.move_down_shortcut = QShortcut(QKeySequence("Alt+Down"), self)
        self.move_up_shortcut.setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        self.move_down_shortcut.setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        self.move_up_shortcut.activated.connect(lambda: self.move_selected(-1))
        self.move_down_shortcut.activated.connect(lambda: self.move_selected(1))

        list_actions = QHBoxLayout()
        for button in (
            self.add_button,
            self.fill_button,
            self.up_button,
            self.down_button,
        ):
            list_actions.addWidget(button)
        destructive_actions = QHBoxLayout()
        destructive_actions.addWidget(self.convert_button)
        destructive_actions.addWidget(self.replace_button)
        destructive_actions.addWidget(self.remove_button)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.memory_list, 1)
        left_layout.addLayout(list_actions)
        left_layout.addLayout(destructive_actions)

        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setObjectName("mutedText")
        self.field_edits: dict[str, QLineEdit | QPlainTextEdit] = {}
        self.field_counters: dict[str, QLabel] = {}
        form = QFormLayout()
        for key, label in MEMORY_FIELDS:
            edit: QLineEdit | QPlainTextEdit
            if key == "title":
                edit = QLineEdit()
                edit.textEdited.connect(
                    lambda _value, key=key: self._field_edited(key)
                )
            else:
                edit = QPlainTextEdit()
                edit.setMinimumHeight(72)
                edit.textChanged.connect(
                    lambda key=key: self._field_edited(key)
                )
            edit.setAccessibleName(f"思い出の{label}")
            counter = QLabel("0 / 1000")
            counter.setObjectName("mutedText")
            column = QVBoxLayout()
            column.setSpacing(2)
            column.addWidget(edit)
            column.addWidget(counter, 0, Qt.AlignmentFlag.AlignRight)
            form.addRow(label, column)
            self.field_edits[key] = edit
            self.field_counters[key] = counter

        self.tag_list = QListWidget()
        self.tag_list.setAccessibleName("思い出タグ")
        self.add_tag_button = QPushButton("タグ追加")
        self.edit_tag_button = QPushButton("タグ編集")
        self.remove_tag_button = QPushButton("タグ削除")
        self.tag_up_button = QPushButton("タグを上へ")
        self.tag_down_button = QPushButton("タグを下へ")
        self.add_tag_button.clicked.connect(self.add_tag)
        self.edit_tag_button.clicked.connect(self.edit_tag)
        self.remove_tag_button.clicked.connect(self.remove_tag)
        self.tag_up_button.clicked.connect(lambda: self.move_tag(-1))
        self.tag_down_button.clicked.connect(lambda: self.move_tag(1))
        tag_actions = QHBoxLayout()
        for button in (
            self.add_tag_button,
            self.edit_tag_button,
            self.remove_tag_button,
            self.tag_up_button,
            self.tag_down_button,
        ):
            tag_actions.addWidget(button)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.message)
        right_layout.addLayout(form)
        right_layout.addWidget(QLabel("タグ（順序・重複・空文字を保持）"))
        right_layout.addWidget(self.tag_list)
        right_layout.addLayout(tag_actions)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

    def set_sheet(
        self,
        sheet: CharacterSheet,
        draft: CharacterSheetDraft,
    ) -> None:
        self._sheet = sheet
        self._draft = draft
        section = sheet.diagnostic_baseline.for_section("memories")
        self._editable = section.editable and not sheet.whole_sheet_read_only
        self.message.setText(
            ""
            if self._editable
            else f"読み取り専用: {section.read_only_reason or sheet.read_only_reason}"
        )
        self._rebuild_list(selected_row=0)

    def current_token(self) -> int | None:
        if self._draft is None:
            return None
        row = self.memory_list.currentRow()
        if not 0 <= row < len(self._draft.memory_order):
            return None
        return self._draft.memory_order[row]

    def add_normal_memory(self) -> None:
        if self._draft is None or not self._editable:
            return
        try:
            self._draft.add_normal_memory(
                generation=self._generation_factory()
            )
        except CharacterSheetRenderError as exc:
            self.message.setText(str(exc))
            return
        self._rebuild_list(selected_row=len(self._draft.memory_order) - 1)
        self.changed.emit()

    def fill_placeholders(self) -> None:
        if self._draft is None or not self._editable:
            return
        added = self._draft.fill_placeholder_memories()
        self._rebuild_list(selected_row=self.memory_list.currentRow())
        if added:
            self.changed.emit()

    def move_selected(self, offset: int) -> None:
        if self._draft is None or not self._editable:
            return
        row = self.memory_list.currentRow()
        target = row + offset
        if not 0 <= row < len(self._draft.memory_order):
            return
        if not 0 <= target < len(self._draft.memory_order):
            return
        self._draft.move_memory(row, target)
        self._rebuild_list(selected_row=target)
        self.changed.emit()

    def remove_selected(self) -> None:
        if self._draft is None or not self._editable:
            return
        row = self.memory_list.currentRow()
        if row < 0:
            return
        result = QMessageBox.question(
            self,
            "思い出を一覧から削除",
            "この思い出を一覧から削除し、件数を1件減らしますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        self._draft.remove_memory(row)
        self._rebuild_list(selected_row=min(row, len(self._draft.memory_order) - 1))
        self.changed.emit()

    def replace_selected(self) -> None:
        token = self.current_token()
        if token is None or self._draft is None or not self._editable:
            return
        result = QMessageBox.question(
            self,
            "空白保持枠へ置換",
            "内容を破棄し、この位置を空白保持枠へ置き換えますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        try:
            self._draft.replace_memory_with_placeholder(token)
        except CharacterSheetRenderError as exc:
            self.message.setText(str(exc))
            return
        self._rebuild_list(selected_row=self.memory_list.currentRow())
        self.changed.emit()

    def convert_selected(self) -> None:
        token = self.current_token()
        if token is None or self._draft is None or not self._editable:
            return
        try:
            self._draft.convert_placeholder_to_normal(
                token,
                generation=self._generation_factory(),
            )
        except CharacterSheetRenderError as exc:
            self.message.setText(str(exc))
            return
        self._rebuild_list(selected_row=self.memory_list.currentRow())
        self.changed.emit()

    def add_tag(self) -> None:
        value, accepted = QInputDialog.getText(self, "タグ追加", "タグ")
        if accepted:
            tags = self._current_tags()
            tags.append(value)
            self._set_tags(tags, selected_row=len(tags) - 1)

    def edit_tag(self) -> None:
        row = self.tag_list.currentRow()
        tags = self._current_tags()
        if not 0 <= row < len(tags):
            return
        value, accepted = QInputDialog.getText(
            self,
            "タグ編集",
            "タグ",
            text=tags[row],
        )
        if accepted:
            tags[row] = value
            self._set_tags(tags, selected_row=row)

    def remove_tag(self) -> None:
        row = self.tag_list.currentRow()
        tags = self._current_tags()
        if not 0 <= row < len(tags):
            return
        tags.pop(row)
        self._set_tags(tags, selected_row=min(row, len(tags) - 1))

    def move_tag(self, offset: int) -> None:
        row = self.tag_list.currentRow()
        target = row + offset
        tags = self._current_tags()
        if not 0 <= row < len(tags) or not 0 <= target < len(tags):
            return
        value = tags.pop(row)
        tags.insert(target, value)
        self._set_tags(tags, selected_row=target)

    def _selection_changed(self, _row: int) -> None:
        self._load_current_memory()

    def _load_current_memory(self) -> None:
        token = self.current_token()
        memory = self._draft.memory_value(token) if self._draft is not None and token is not None else None
        self._loading = True
        blockers = [
            QSignalBlocker(edit)
            for edit in self.field_edits.values()
        ]
        self.tag_list.clear()
        if memory is None:
            for edit in self.field_edits.values():
                self._set_edit_text(edit, "")
            tags: list[str] = []
            is_placeholder = False
            self._display_source_values = {
                key: "" for key in self.field_edits
            }
        else:
            self._display_source_values = {}
            for key, edit in self.field_edits.items():
                value = memory.get(key, "")
                source_value = value if isinstance(value, str) else ""
                self._display_source_values[key] = source_value
                self._set_edit_text(edit, source_value)
            raw_tags = memory.get("tags")
            tags = list(raw_tags) if isinstance(raw_tags, list) else []
            self.tag_list.addItems(tags)
            is_placeholder = memory.get("isPlaceholder") is True
        self._edited_field_keys = set()
        del blockers
        self._loading = False

        can_edit_fields = self._editable and memory is not None and not is_placeholder
        for edit in self.field_edits.values():
            edit.setEnabled(can_edit_fields)
        for button in (
            self.add_tag_button,
            self.edit_tag_button,
            self.remove_tag_button,
            self.tag_up_button,
            self.tag_down_button,
        ):
            button.setEnabled(can_edit_fields)
        self.convert_button.setEnabled(self._editable and is_placeholder)
        self.replace_button.setEnabled(
            self._editable and memory is not None and not is_placeholder
        )
        self.remove_button.setEnabled(self._editable and memory is not None)
        self._refresh_controls()
        self._refresh_counters()

    def _field_edited(self, key: str) -> None:
        token = self.current_token()
        if (
            self._loading
            or self._draft is None
            or token is None
            or not self._editable
        ):
            return
        self._draft.set_memory_field(
            token,
            key,
            self._edit_text(self.field_edits[key]),
        )
        self._edited_field_keys.add(key)
        self._refresh_counters()
        self._refresh_current_label()
        self.changed.emit()

    def _set_tags(self, tags: list[str], *, selected_row: int) -> None:
        token = self.current_token()
        if self._draft is None or token is None or not self._editable:
            return
        self._draft.set_memory_tags(token, tags)
        self.tag_list.clear()
        self.tag_list.addItems(tags)
        if tags:
            self.tag_list.setCurrentRow(selected_row)
        self.changed.emit()

    def _current_tags(self) -> list[str]:
        return [
            self.tag_list.item(index).text()
            for index in range(self.tag_list.count())
        ]

    def _rebuild_list(self, *, selected_row: int) -> None:
        self._loading = True
        self.memory_list.clear()
        if self._draft is not None:
            for position, token in enumerate(self._draft.memory_order):
                memory = self._draft.memory_value(token)
                self.memory_list.addItem(
                    self._memory_label(position, memory)
                )
        self._loading = False
        if self.memory_list.count():
            self.memory_list.setCurrentRow(
                max(0, min(selected_row, self.memory_list.count() - 1))
            )
        else:
            self._load_current_memory()
        self._refresh_controls()

    def _refresh_current_label(self) -> None:
        row = self.memory_list.currentRow()
        token = self.current_token()
        if self._draft is None or token is None or row < 0:
            return
        self.memory_list.item(row).setText(
            self._memory_label(row, self._draft.memory_value(token))
        )

    def _refresh_controls(self) -> None:
        count = len(self._draft.memory_order) if self._draft is not None else 0
        row = self.memory_list.currentRow()
        can_grow = self._editable and count < 15
        self.add_button.setEnabled(can_grow)
        self.fill_button.setEnabled(can_grow)
        self.up_button.setEnabled(self._editable and row > 0)
        self.down_button.setEnabled(
            self._editable and 0 <= row < count - 1
        )
        if count >= 15:
            tooltip = "通常思い出と空白保持枠の合計が15件以上のため追加できません"
            self.add_button.setToolTip(tooltip)
            self.fill_button.setToolTip(tooltip)
        else:
            self.add_button.setToolTip("")
            self.fill_button.setToolTip("")

    def _refresh_counters(self) -> None:
        for key, edit in self.field_edits.items():
            value = (
                self._edit_text(edit)
                if key in self._edited_field_keys
                else self._display_source_values.get(key, "")
            )
            count = len(value)
            label = self.field_counters[key]
            label.setText(f"{count} / 1000")
            label.setProperty("state", "error" if count > 1000 else "normal")

    @staticmethod
    def _memory_label(position: int, memory: dict[str, object]) -> str:
        if memory.get("isPlaceholder") is True:
            return f"{position + 1}. ［空白保持枠］"
        title = memory.get("title")
        return f"{position + 1}. {title or '（タイトル未設定）'}"

    @staticmethod
    def _edit_text(edit: QLineEdit | QPlainTextEdit) -> str:
        return edit.text() if isinstance(edit, QLineEdit) else edit.toPlainText()

    @staticmethod
    def _set_edit_text(
        edit: QLineEdit | QPlainTextEdit,
        value: str,
    ) -> None:
        if isinstance(edit, QLineEdit):
            edit.setText(value)
        else:
            edit.setPlainText(value)
