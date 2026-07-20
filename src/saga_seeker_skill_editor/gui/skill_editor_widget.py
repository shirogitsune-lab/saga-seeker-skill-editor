"""Editor for one selected skill."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from saga_seeker_skill_editor.core.character_sheet import SkillEntry
from saga_seeker_skill_editor.core.skill_classifier import SkillKind
from saga_seeker_skill_editor.gui.collapsible_section import CollapsibleSection
from saga_seeker_skill_editor.gui.theme_manager import refresh_widget_style


@dataclass(frozen=True)
class SkillEditState:
    index: int
    name: str
    description: str
    changed: bool
    repair_id_confirmed: bool
    replacement_confirmed: bool
    deletion_requested: bool
    vacant_creation: bool


class SkillEditorWidget(QFrame):
    changed = Signal()

    def __init__(
        self,
        entry: SkillEntry,
        *,
        is_last_entry: bool = False,
        read_only_reason: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.entry = entry
        self.is_last_entry = is_last_entry
        self.read_only_reason = read_only_reason
        self.repair_id_confirmed = False
        self.replacement_confirmed = False
        self.replacement_keep_text = False
        self.deletion_requested = False
        self.deletion_available = True
        self.setObjectName("editorPanel")

        self.original_name = str(entry.skill.get("name", "") or "")
        self.original_description = str(entry.skill.get("description", "") or "")

        self.title = QLabel(self.original_name or "未設定のスキル")
        self.title.setObjectName("characterName")
        self.slot_label = QLabel(f"スロット {entry.index + 1}")
        self.slot_label.setObjectName("mutedText")
        self.kind_label = QLabel(self._kind_label())
        self.kind_label.setProperty("badge", True)
        self.protection_label = QLabel(self._protection_status())
        self.protection_label.setProperty("badge", True)
        self.change_label = QLabel("変更なし")
        self.change_label.setProperty("badge", True)

        heading_text = QVBoxLayout()
        heading_text.setSpacing(2)
        heading_text.addWidget(self.slot_label)
        heading_text.addWidget(self.title)

        badges = QHBoxLayout()
        badges.addWidget(self.kind_label)
        badges.addWidget(self.protection_label)
        badges.addWidget(self.change_label)
        badges.addStretch(1)

        self.reason_label = QLabel(self._reason_text())
        self.reason_label.setWordWrap(True)
        self.reason_label.setObjectName("mutedText")

        self.name_edit = QLineEdit(self.original_name)
        self.name_edit.setAccessibleName("スキル名")
        self.description_edit = QTextEdit(self.original_description)
        self.description_edit.setAccessibleName("スキルの説明")
        self.description_edit.setMinimumHeight(180)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.addRow("スキル名", self.name_edit)
        form.addRow("スキルの説明", self.description_edit)

        self.technical_section = CollapsibleSection("技術情報", self._build_technical_content())
        self.advanced_section = CollapsibleSection("高度な操作", self._build_advanced_content())
        self.advanced_section.setVisible(
            read_only_reason is None and entry.classification.kind != SkillKind.UNKNOWN
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        layout.addLayout(heading_text)
        layout.addLayout(badges)
        layout.addWidget(self.reason_label)
        layout.addSpacing(4)
        layout.addLayout(form)
        layout.addStretch(1)
        layout.addWidget(self.technical_section)
        layout.addWidget(self.advanced_section)

        editable = self._normally_editable()
        self.name_edit.setEnabled(editable)
        self.description_edit.setEnabled(editable)

        self.name_edit.textChanged.connect(self._on_value_changed)
        self.description_edit.textChanged.connect(self._on_value_changed)
        self.action_button.clicked.connect(self._handle_action_button)

    def _build_technical_content(self) -> QWidget:
        content = QWidget()
        form = QFormLayout(content)
        form.setContentsMargins(16, 4, 8, 8)
        values = {
            "id": self.entry.skill.get("id", ""),
            "type": self.entry.skill.get("type", ""),
            "key": self.entry.skill.get("key", ""),
            "分類理由": self.entry.classification.reason,
            "読み取り専用理由": self.read_only_reason or "なし",
        }
        for label, value in values.items():
            value_label = QLabel(repr(value) if label in {"id", "type", "key"} else str(value))
            value_label.setObjectName("technicalValue")
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value_label.setWordWrap(True)
            form.addRow(label, value_label)
        return content

    def _build_advanced_content(self) -> QWidget:
        content = QWidget()
        self.advanced_explanation = QLabel()
        self.advanced_explanation.setWordWrap(True)
        self.action_button = QPushButton()
        self.action_button.setProperty("role", "danger")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 4, 8, 8)
        layout.addWidget(self.advanced_explanation)
        layout.addWidget(self.action_button, 0)
        self._update_action_control()
        return content

    def state(self) -> SkillEditState:
        name = self.name_edit.text()
        description = self.description_edit.toPlainText()
        changed = (
            name != self.original_name
            or description != self.original_description
            or self.replacement_confirmed
            or self.deletion_requested
        )
        return SkillEditState(
            index=self.entry.index,
            name=name,
            description=description,
            changed=changed,
            repair_id_confirmed=self.repair_id_confirmed,
            replacement_confirmed=self.replacement_confirmed,
            deletion_requested=self.deletion_requested,
            vacant_creation=False,
        )

    def prepare_for_save(self) -> bool:
        state = self.state()
        if not state.changed:
            return True
        if state.deletion_requested:
            return True
        if self.entry.classification.kind == SkillKind.ORIGINAL_NEEDS_ID_REPAIR and not self.repair_id_confirmed:
            result = QMessageBox.warning(
                self,
                "ID修復の確認",
                "このスキルはIDが空または重複しています。保存するには未使用のskN IDを生成します。"
                "元の正常なIDは変更しません。続行しますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if result != QMessageBox.StandardButton.Yes:
                return False
            self.repair_id_confirmed = True
        return True

    def reset(self) -> None:
        self.repair_id_confirmed = False
        self.replacement_confirmed = False
        self.replacement_keep_text = False
        self.deletion_requested = False
        self.name_edit.setText(self.original_name)
        self.description_edit.setPlainText(self.original_description)
        self.name_edit.setEnabled(self._normally_editable())
        self.description_edit.setEnabled(self._normally_editable())
        self.reason_label.setText(self._reason_text())
        self._update_action_control()
        self._on_value_changed()

    def set_change_indicator(self, changed: bool) -> None:
        self.change_label.setText("変更あり" if changed else "変更なし")
        self.change_label.setProperty("state", "modified" if changed else "normal")
        refresh_widget_style(self.change_label)

    def _on_value_changed(self) -> None:
        current_name = self.name_edit.text()
        self.title.setText(current_name or "未設定のスキル")
        self.changed.emit()

    def _handle_action_button(self) -> None:
        if self.deletion_requested:
            self._cancel_deletion()
            return
        if self.replacement_confirmed:
            self.reset()
            return

        if self.entry.classification.kind == SkillKind.DEFAULT:
            if self.deletion_available:
                action = SkillActionDialog.ask(self, is_last_entry=self.is_last_entry)
                if action is None:
                    return
                if action == "delete":
                    self._begin_deletion()
                    return
            self._begin_replacement()
            return
        self._begin_deletion()

    def _begin_replacement(self) -> None:
        mode = ReplacementModeDialog.ask(self)
        if mode is None:
            return
        self.replacement_confirmed = True
        self.replacement_keep_text = mode == "keep"
        self.name_edit.setEnabled(True)
        self.description_edit.setEnabled(True)
        if self.replacement_keep_text:
            self.name_edit.setText(self.original_name)
            self.description_edit.setPlainText(self.original_description)
            self.reason_label.setText(
                "置き換え予定です。名前と説明を引き継ぎ、保存時に未使用のskN IDを生成します。"
            )
        else:
            self.name_edit.setText("")
            self.description_edit.setPlainText("")
            self.reason_label.setText(
                "置き換え予定です。空欄のオリジナルスキルとして、保存時に未使用のskN IDを生成します。"
            )
        self._update_action_control()
        self.changed.emit()

    def _begin_deletion(self) -> None:
        if not self.deletion_available:
            return
        if not DeletionConfirmationDialog.ask(
            self,
            skill_name=self.original_name or f"スロット {self.entry.index + 1}",
            becomes_vacant=self.is_last_entry,
        ):
            return
        self.deletion_requested = True
        self.name_edit.setEnabled(False)
        self.description_edit.setEnabled(False)
        if self.is_last_entry:
            self.reason_label.setText(
                "削除予定です。末尾のスキルなので、保存後はゲームが自動追加に使用できる未使用枠へ戻ります。"
            )
        else:
            self.reason_label.setText(
                "削除予定です。位置対応を維持するため、保存後は自動追加を防ぐ空スキルへ置き換わります。"
            )
        self._update_action_control()
        self.changed.emit()

    def _cancel_deletion(self) -> None:
        self.deletion_requested = False
        self.name_edit.setEnabled(self.replacement_confirmed or self._normally_editable())
        self.description_edit.setEnabled(self.replacement_confirmed or self._normally_editable())
        self.reason_label.setText(self._reason_text())
        self._update_action_control()
        self.changed.emit()

    def set_delete_available(self, available: bool) -> None:
        self.deletion_available = available
        self._update_action_control()

    def _update_action_control(self) -> None:
        if not hasattr(self, "action_button"):
            return
        if self.deletion_requested:
            text = "削除予定を取り消す"
            explanation = (
                "保存前であれば、この削除予定を取り消して元のスキルへ戻せます。"
            )
            visible = True
        elif self.replacement_confirmed:
            text = "置き換え予定を取り消す"
            explanation = (
                "保存前であれば、オリジナルスキルへの置き換え予定を取り消せます。"
            )
            visible = True
        elif self.entry.classification.kind == SkillKind.DEFAULT:
            if self.deletion_available:
                text = "このスキルの操作を選ぶ..."
                explanation = (
                    "オリジナルスキルへの置き換え、または現在位置に適した削除方法を選択します。"
                )
            else:
                text = "オリジナルスキルへ置き換える..."
                explanation = (
                    "空き枠への追加を編集中のため、現在はオリジナルスキルへの置き換えだけ実行できます。"
                )
            visible = True
        elif self.deletion_available:
            if self.is_last_entry:
                text = "削除して未使用枠へ戻す..."
                explanation = (
                    "末尾のスキルを削除し、ゲームが自動追加に使用できる未使用枠へ戻します。"
                )
            else:
                text = "空スキルへ置き換える..."
                explanation = (
                    "リスト途中のため、位置対応を維持しながら自動追加を防ぐ空スキルへ置き換えます。"
                )
            visible = True
        else:
            text = ""
            explanation = (
                "空き枠への追加を編集中です。削除操作は、追加内容を保存するか元に戻すと利用できます。"
            )
            visible = False

        self.action_button.setText(text)
        self.action_button.setAccessibleName(text)
        self.action_button.setVisible(visible)
        self.action_button.setEnabled(
            visible
            and self.read_only_reason is None
            and self.entry.classification.kind != SkillKind.UNKNOWN
        )
        self.advanced_explanation.setText(explanation)

    def _normally_editable(self) -> bool:
        return bool(
            self.entry.classification.editable
            and self.read_only_reason is None
            and self.entry.classification.kind
            in (SkillKind.EMPTY_SLOT, SkillKind.ORIGINAL, SkillKind.ORIGINAL_NEEDS_ID_REPAIR)
        )

    def _kind_label(self) -> str:
        labels = {
            SkillKind.UNKNOWN: "形式不明",
            SkillKind.EMPTY_SLOT: "空スロット",
            SkillKind.DEFAULT: "ゲーム内デフォルト",
            SkillKind.ORIGINAL: "オリジナル",
            SkillKind.ORIGINAL_NEEDS_ID_REPAIR: "オリジナル（ID修復が必要）",
        }
        return labels.get(self.entry.classification.kind, str(self.entry.classification.kind))

    def _protection_status(self) -> str:
        if self.read_only_reason:
            return "読み取り専用"
        if self.entry.classification.kind == SkillKind.DEFAULT:
            return "保護中"
        if self.entry.classification.kind == SkillKind.UNKNOWN:
            return "編集不可"
        return "保護なし"

    def _reason_text(self) -> str:
        if self.read_only_reason:
            return f"読み取り専用: {self.read_only_reason}"
        if self.entry.classification.kind == SkillKind.DEFAULT:
            return "保護理由: ゲーム内で用意されたデフォルトスキルのため、通常編集から保護されています。"
        if self.entry.classification.kind == SkillKind.UNKNOWN:
            return f"編集できません: {self.entry.classification.reason}"
        if self.entry.classification.kind == SkillKind.ORIGINAL_NEEDS_ID_REPAIR:
            return f"保存時に確認が必要です: {self.entry.classification.reason}"
        return "保護されていません。名前と説明を編集できます。"


class SkillActionDialog(QDialog):
    def __init__(self, parent: QWidget | None, *, is_last_entry: bool) -> None:
        super().__init__(parent)
        self.setWindowTitle("デフォルトスキルの操作")
        self.setMinimumWidth(520)
        self.action_group = QButtonGroup(self)
        self.replace_radio = QRadioButton("オリジナルスキルへ置き換える")
        deletion_label = (
            "削除して未使用枠へ戻す"
            if is_last_entry
            else "空スキルへ置き換える"
        )
        self.delete_radio = QRadioButton(deletion_label)
        self.replace_radio.setChecked(True)
        self.action_group.addButton(self.replace_radio)
        self.action_group.addButton(self.delete_radio)

        replace_detail = QLabel(
            "名前と説明を引き継ぐか空欄にするかを次の画面で選びます。"
            "元のid/type/keyは保存時に失われます。"
        )
        replace_detail.setWordWrap(True)
        delete_detail = QLabel(deletion_effect_text(becomes_vacant=is_last_entry))
        delete_detail.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("次へ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("実行する操作を選択してください。"))
        layout.addSpacing(8)
        layout.addWidget(self.replace_radio)
        layout.addWidget(replace_detail)
        layout.addSpacing(8)
        layout.addWidget(self.delete_radio)
        layout.addWidget(delete_detail)
        layout.addSpacing(8)
        layout.addWidget(buttons)

    @classmethod
    def ask(cls, parent: QWidget | None, *, is_last_entry: bool) -> str | None:
        dialog = cls(parent, is_last_entry=is_last_entry)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return "replace" if dialog.replace_radio.isChecked() else "delete"


class DeletionConfirmationDialog:
    @staticmethod
    def ask(parent: QWidget | None, *, skill_name: str, becomes_vacant: bool) -> bool:
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("スキル削除の確認")
        box.setText(f"「{skill_name}」を削除しますか？")
        box.setInformativeText(deletion_effect_text(becomes_vacant=becomes_vacant))
        delete_button = box.addButton("削除する", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = box.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel_button)
        box.setEscapeButton(cancel_button)
        box.exec()
        return box.clickedButton() is delete_button


def deletion_effect_text(*, becomes_vacant: bool) -> str:
    if becomes_vacant:
        return (
            "このスキルはリスト末尾にあるため、削除後は未使用枠へ戻ります。"
            "ゲーム内条件を満たした場合、この枠へスキルが自動追加される可能性があります。"
        )
    return (
        "データの位置対応を維持するため、リスト途中のスキルは完全には取り除かず、"
        "空スキルへ置き換えます。空スキルは枠を占有し、ゲームによるスキルの自動追加を防ぎます。"
    )


class ReplacementModeDialog(QDialog):
    def __init__(self, parent: QWidget | None) -> None:
        super().__init__(parent)
        self.setWindowTitle("デフォルトスキルの置き換え")
        self.setMinimumWidth(480)
        self.mode_group = QButtonGroup(self)
        self.keep_radio = QRadioButton("名前と説明を引き継ぐ")
        self.blank_radio = QRadioButton("名前と説明を空欄にする")
        self.keep_radio.setChecked(True)
        self.mode_group.addButton(self.keep_radio)
        self.mode_group.addButton(self.blank_radio)

        message = QLabel(
            "デフォルトスキルをオリジナルスキルへ置き換えます。\n"
            "保存すると元のid/type/keyは失われ、未使用のskN IDが生成されます。"
        )
        message.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("内容を確認する")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(message)
        layout.addSpacing(8)
        layout.addWidget(self.keep_radio)
        layout.addWidget(self.blank_radio)
        layout.addSpacing(8)
        layout.addWidget(buttons)

    @classmethod
    def ask(cls, parent: QWidget | None) -> str | None:
        dialog = cls(parent)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        mode_text = "名前と説明を引き継ぎます" if dialog.keep_radio.isChecked() else "名前と説明を空欄にします"
        second = QMessageBox.warning(
            parent,
            "置き換えの最終確認",
            f"{mode_text}。元のid/type/keyは保存時に失われます。\n"
            "このスキルを置き換え予定にしますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if second != QMessageBox.StandardButton.Yes:
            return None
        return "keep" if dialog.keep_radio.isChecked() else "blank"
