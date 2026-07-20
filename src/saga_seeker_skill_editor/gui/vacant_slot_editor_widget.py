"""Editor for an HTML skill slot that has no JSON skill object yet."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from saga_seeker_skill_editor.gui.skill_editor_widget import SkillEditState
from saga_seeker_skill_editor.gui.theme_manager import refresh_widget_style


class VacantSlotEditorWidget(QFrame):
    changed = Signal()

    def __init__(
        self,
        slot_index: int,
        *,
        creation_enabled: bool,
        read_only_reason: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.slot_index = slot_index
        self.read_only_reason = read_only_reason
        self.validation_error: str | None = None
        self.creation_enabled = creation_enabled
        self.setObjectName("editorPanel")

        self.title = QLabel("未使用枠")
        self.title.setObjectName("characterName")
        self.slot_label = QLabel(f"スロット {slot_index + 1}")
        self.slot_label.setObjectName("mutedText")
        self.kind_label = QLabel("未使用枠")
        self.kind_label.setProperty("badge", True)
        self.protection_label = QLabel("自動追加可")
        self.protection_label.setProperty("badge", True)
        self.change_label = QLabel("変更なし")
        self.change_label.setProperty("badge", True)

        heading = QVBoxLayout()
        heading.setSpacing(2)
        heading.addWidget(self.slot_label)
        heading.addWidget(self.title)

        badges = QHBoxLayout()
        badges.addWidget(self.kind_label)
        badges.addWidget(self.protection_label)
        badges.addWidget(self.change_label)
        badges.addStretch(1)

        self.reason_label = QLabel()
        self.reason_label.setObjectName("mutedText")
        self.reason_label.setWordWrap(True)
        self.name_edit = QLineEdit()
        self.name_edit.setAccessibleName("追加するスキル名")
        self.description_edit = QTextEdit()
        self.description_edit.setAccessibleName("追加するスキルの説明")
        self.description_edit.setMinimumHeight(180)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.addRow("スキル名", self.name_edit)
        form.addRow("スキルの説明", self.description_edit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        layout.addLayout(heading)
        layout.addLayout(badges)
        layout.addWidget(self.reason_label)
        layout.addSpacing(4)
        layout.addLayout(form)
        layout.addStretch(1)

        self.name_edit.textChanged.connect(self._on_value_changed)
        self.description_edit.textChanged.connect(self._on_value_changed)
        self.set_creation_available(creation_enabled)

    def state(self) -> SkillEditState:
        name = self.name_edit.text()
        description = self.description_edit.toPlainText()
        return SkillEditState(
            index=self.slot_index,
            name=name,
            description=description,
            changed=name != "" or description != "",
            repair_id_confirmed=False,
            replacement_confirmed=False,
            deletion_requested=False,
            vacant_creation=True,
        )

    def prepare_for_save(self) -> bool:
        state = self.state()
        if not state.changed or state.name != "":
            return True
        QMessageBox.warning(
            self,
            "スキル名が必要です",
            "未使用枠へ追加するオリジナルスキルの名前を入力してください。",
        )
        self.name_edit.setFocus()
        return False

    def reset(self) -> None:
        self.name_edit.clear()
        self.description_edit.clear()
        self._on_value_changed()

    def set_change_indicator(self, changed: bool) -> None:
        self.change_label.setText("追加予定" if changed else "変更なし")
        self.change_label.setProperty("state", "modified" if changed else "normal")
        refresh_widget_style(self.change_label)

    def set_creation_available(self, available: bool) -> None:
        if self.read_only_reason is not None:
            available = False
        self.creation_enabled = available
        self.name_edit.setEnabled(available)
        self.description_edit.setEnabled(available)
        self._refresh_reason()

    def set_validation_error(self, message: str | None) -> None:
        self.validation_error = message
        self._refresh_reason()

    def _refresh_reason(self) -> None:
        if self.validation_error is not None:
            self.reason_label.setText(self.validation_error)
            self.reason_label.setProperty("state", "error")
        elif self.read_only_reason is not None:
            self.reason_label.setText(f"読み取り専用: {self.read_only_reason}")
            self.reason_label.setProperty("state", None)
        elif self.creation_enabled:
            self.reason_label.setText(
                "この未使用枠へオリジナルスキルを追加できます。"
                "保存時は前の枠から連続して入力されている必要があります。"
            )
            self.reason_label.setProperty("state", None)
        else:
            self.reason_label.setText("別の編集操作中のため、現在はこの枠へ追加できません。")
            self.reason_label.setProperty("state", None)
        refresh_widget_style(self.reason_label)

    def _on_value_changed(self) -> None:
        self.title.setText(self.name_edit.text() or "未使用枠")
        self.changed.emit()
