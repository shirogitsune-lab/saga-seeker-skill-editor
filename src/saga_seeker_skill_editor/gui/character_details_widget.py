"""Basic character information and lazy icon controls."""

from __future__ import annotations

import base64
import binascii

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from saga_seeker_skill_editor.core.character_sheet import (
    CharacterSheet,
    CharacterSheetDraft,
    PROFILE_TABS,
)
from saga_seeker_skill_editor.gui.image_pipeline import (
    ImageSafetyError,
    inspect_image_bytes,
)


PROFILE_LABELS = {
    "basicSettings": "基本設定",
    "appearance": "外見",
    "personality": "性格",
    "speechStyle": "口調",
    "background": "経歴",
    "talentsAndRole": "特技と役割",
    "otherFeatures": "その他の特徴",
}


class CharacterDetailsWidget(QWidget):
    changed = Signal()
    replace_icon_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._sheet: CharacterSheet | None = None
        self._draft: CharacterSheetDraft | None = None
        self._loading = False
        self._baseline_profiles: dict[str, str] = {}
        self._untouched_profile_keys: set[str] = set()
        self._comparison_loading = False
        self.comparison_window: QDialog | None = None

        self.name_edit = QLineEdit()
        self.name_edit.setAccessibleName("キャラクター名")
        self.name_counter = QLabel("0 / 20")
        self.name_counter.setObjectName("mutedText")
        name_row = QHBoxLayout()
        name_row.addWidget(self.name_edit, 1)
        name_row.addWidget(self.name_counter)

        self.section_message = QLabel()
        self.section_message.setWordWrap(True)
        self.section_message.setObjectName("mutedText")

        self.profile_edits: dict[str, QPlainTextEdit] = {}
        self.profile_counters: dict[str, QLabel] = {}
        self.profile_change_labels: dict[str, QLabel] = {}
        self.profile_toggles: dict[str, QPushButton] = {}
        self.profile_bodies: dict[str, QWidget] = {}
        self.profile_accordion = QWidget()
        profile_accordion_layout = QVBoxLayout(self.profile_accordion)
        profile_accordion_layout.setContentsMargins(0, 0, 0, 0)
        profile_accordion_layout.setSpacing(6)
        for index, (key, _english_label) in enumerate(PROFILE_TABS):
            edit = QPlainTextEdit()
            edit.setAccessibleName(PROFILE_LABELS[key])
            edit.setMinimumHeight(180)
            counter = QLabel("0 / 1000")
            counter.setObjectName("mutedText")
            change_label = QLabel("変更なし")
            change_label.setObjectName("mutedText")

            footer = QHBoxLayout()
            footer.setContentsMargins(0, 0, 0, 0)
            footer.addWidget(change_label)
            footer.addStretch(1)
            footer.addWidget(counter)

            body = QWidget()
            body_layout = QVBoxLayout(body)
            body_layout.setContentsMargins(8, 0, 8, 6)
            body_layout.setSpacing(4)
            body_layout.addWidget(edit, 1)
            body_layout.addLayout(footer)

            toggle = QPushButton()
            toggle.setCheckable(True)
            toggle.setProperty("accordion", True)
            toggle.setMinimumHeight(40)
            toggle.setToolTip(
                f"{PROFILE_LABELS[key]}の編集欄を展開または折り畳みます"
            )
            toggle.toggled.connect(
                lambda expanded, key=key: self._set_profile_expanded(
                    key,
                    expanded,
                )
            )
            profile_accordion_layout.addWidget(toggle)
            profile_accordion_layout.addWidget(body)

            self.profile_edits[key] = edit
            self.profile_counters[key] = counter
            self.profile_change_labels[key] = change_label
            self.profile_toggles[key] = toggle
            self.profile_bodies[key] = body
            toggle.setChecked(index == 0)
            self._set_profile_expanded(key, index == 0)

        self.comparison_panel = self._create_comparison_panel()
        self.comparison_host = QWidget()
        self.comparison_host_layout = QVBoxLayout(self.comparison_host)
        self.comparison_host_layout.setContentsMargins(0, 0, 0, 0)
        self.comparison_host_layout.addWidget(self.comparison_panel)
        self.comparison_host.hide()

        self.show_comparison_button = QPushButton("プロフィール比較を表示")
        self.show_comparison_button.setAccessibleName("プロフィール比較を表示")
        self.show_comparison_button.setToolTip(
            "2つのプロフィール項目と性格キーワードを並べて表示します"
        )
        self.show_comparison_button.clicked.connect(
            self.show_profile_comparison
        )
        comparison_command_row = QHBoxLayout()
        comparison_command_row.addWidget(self.show_comparison_button)
        comparison_command_row.addStretch(1)

        self.icon_preview = QLabel("プレビューは未読込です")
        self.icon_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_preview.setMinimumSize(160, 160)
        self.icon_preview.setFrameShape(QFrame.Shape.StyledPanel)
        self.icon_preview.setAccessibleName("キャラクター画像プレビュー")
        self.preview_button = QPushButton("プレビューを表示")
        self.preview_button.clicked.connect(self.show_icon_preview)
        self.replace_icon_button = QPushButton("画像を差し替える")
        self.replace_icon_button.clicked.connect(self.replace_icon_requested)
        icon_buttons = QHBoxLayout()
        icon_buttons.addWidget(self.preview_button)
        icon_buttons.addWidget(self.replace_icon_button)

        icon_layout = QVBoxLayout()
        icon_layout.addWidget(self.icon_preview)
        icon_layout.addLayout(icon_buttons)
        icon_layout.addStretch(1)

        details = QVBoxLayout()
        details.addWidget(self.section_message)
        details.addLayout(name_row)
        details.addLayout(comparison_command_row)
        details.addWidget(self.comparison_host)
        details.addWidget(self.profile_accordion, 1)

        details_widget = QWidget()
        details_widget.setLayout(details)
        icon_widget = QWidget()
        icon_widget.setLayout(icon_layout)

        self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.addWidget(details_widget)
        self.content_splitter.addWidget(icon_widget)
        self.content_splitter.setCollapsible(0, False)
        self.content_splitter.setCollapsible(1, False)
        self.content_splitter.setStretchFactor(0, 3)
        self.content_splitter.setStretchFactor(1, 1)
        self.content_splitter.setSizes([900, 300])

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self.content_splitter)

        self.name_edit.textEdited.connect(self._name_edited)
        for key, edit in self.profile_edits.items():
            edit.textChanged.connect(
                lambda key=key: self._profile_edited(key)
            )

    def _set_profile_expanded(self, key: str, expanded: bool) -> None:
        body = self.profile_bodies.get(key)
        toggle = self.profile_toggles.get(key)
        if body is None or toggle is None:
            return
        body.setVisible(expanded)
        label = PROFILE_LABELS[key]
        toggle.setText(f"{'▼' if expanded else '▶'} {label}")
        toggle.setAccessibleName(
            f"{label}を{'折り畳む' if expanded else '展開する'}"
        )

    def _create_comparison_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("editorPanel")

        heading = QLabel("プロフィール比較")
        heading.setObjectName("sectionHeading")
        note = QLabel(
            "2項目を同時に編集できます。性格キーワードは右端へ常時表示します。"
        )
        note.setObjectName("mutedText")
        note.setWordWrap(True)
        self.detach_comparison_button = QPushButton("別ウィンドウで開く")
        self.detach_comparison_button.clicked.connect(self.open_profile_comparison)
        self.close_comparison_button = QPushButton("比較表示を閉じる")
        self.close_comparison_button.clicked.connect(
            self.hide_profile_comparison
        )

        heading_row = QHBoxLayout()
        heading_row.addWidget(heading)
        heading_row.addWidget(note, 1)
        heading_row.addWidget(self.detach_comparison_button)
        heading_row.addWidget(self.close_comparison_button)

        self.left_profile_selector = self._profile_selector("比較する左側の項目")
        self.right_profile_selector = self._profile_selector("比較する右側の項目")
        self.left_profile_selector.setCurrentIndex(0)
        personality_index = self.right_profile_selector.findData("personality")
        self.right_profile_selector.setCurrentIndex(personality_index)

        self.left_comparison_edit = self._comparison_edit("左側のプロフィール編集欄")
        self.right_comparison_edit = self._comparison_edit("右側のプロフィール編集欄")
        self.left_comparison_counter = QLabel("0 / 1000")
        self.right_comparison_counter = QLabel("0 / 1000")
        for counter in (
            self.left_comparison_counter,
            self.right_comparison_counter,
        ):
            counter.setObjectName("mutedText")

        self.personality_reference = QLabel("未設定")
        self.personality_reference.setAccessibleName("選択中の性格キーワード")
        self.personality_reference.setWordWrap(True)
        self.personality_reference.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        reference_heading = QLabel("選択中の性格キーワード")
        reference_heading.setObjectName("sectionHeading")
        reference_note = QLabel("性格キーワードタブの現在値を参照表示します")
        reference_note.setObjectName("mutedText")
        reference_note.setWordWrap(True)
        reference_panel = QFrame()
        reference_panel.setFrameShape(QFrame.Shape.StyledPanel)
        reference_layout = QVBoxLayout(reference_panel)
        reference_layout.addWidget(reference_heading)
        reference_layout.addWidget(reference_note)
        reference_layout.addWidget(self.personality_reference)
        reference_layout.addStretch(1)

        left_panel = self._comparison_field_panel(
            "左側の項目",
            self.left_profile_selector,
            self.left_comparison_edit,
            self.left_comparison_counter,
        )
        right_panel = self._comparison_field_panel(
            "右側の項目",
            self.right_profile_selector,
            self.right_comparison_edit,
            self.right_comparison_counter,
        )

        self.comparison_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.comparison_splitter.setChildrenCollapsible(False)
        self.comparison_splitter.addWidget(left_panel)
        self.comparison_splitter.addWidget(right_panel)
        self.comparison_splitter.addWidget(reference_panel)
        for index in range(self.comparison_splitter.count()):
            self.comparison_splitter.setCollapsible(index, False)
        self.comparison_splitter.setStretchFactor(0, 2)
        self.comparison_splitter.setStretchFactor(1, 2)
        self.comparison_splitter.setStretchFactor(2, 1)
        self.comparison_splitter.setSizes([360, 360, 240])

        layout = QVBoxLayout(panel)
        layout.addLayout(heading_row)
        layout.addWidget(self.comparison_splitter, 1)

        self.left_profile_selector.currentIndexChanged.connect(
            lambda: self._comparison_selection_changed("left")
        )
        self.right_profile_selector.currentIndexChanged.connect(
            lambda: self._comparison_selection_changed("right")
        )
        self.left_comparison_edit.textChanged.connect(
            lambda: self._comparison_edited("left")
        )
        self.right_comparison_edit.textChanged.connect(
            lambda: self._comparison_edited("right")
        )
        return panel

    @staticmethod
    def _comparison_field_panel(
        label_text: str,
        selector: QComboBox,
        edit: QPlainTextEdit,
        counter: QLabel,
    ) -> QWidget:
        panel = QWidget()
        label = QLabel(label_text)
        label.setBuddy(selector)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label)
        layout.addWidget(selector)
        layout.addWidget(edit, 1)
        layout.addWidget(counter, 0, Qt.AlignmentFlag.AlignRight)
        return panel

    @staticmethod
    def _comparison_edit(accessible_name: str) -> QPlainTextEdit:
        edit = QPlainTextEdit()
        edit.setAccessibleName(accessible_name)
        edit.setMinimumHeight(150)
        return edit

    @staticmethod
    def _profile_selector(accessible_name: str) -> QComboBox:
        selector = QComboBox()
        selector.setAccessibleName(accessible_name)
        for key, _english_label in PROFILE_TABS:
            selector.addItem(PROFILE_LABELS[key], key)
        return selector

    def set_sheet(
        self,
        sheet: CharacterSheet,
        draft: CharacterSheetDraft,
    ) -> None:
        self._sheet = sheet
        self._draft = draft
        data = sheet.data.get("data")
        profile = data.get("profile") if isinstance(data, dict) else {}
        self._baseline_profiles = {
            key: (
                profile.get(key, "")
                if isinstance(profile, dict)
                and isinstance(profile.get(key, ""), str)
                else ""
            )
            for key in self.profile_edits
        }
        self._untouched_profile_keys = set(self.profile_edits)
        profile_section = sheet.diagnostic_baseline.for_section("profile")
        name_section = sheet.diagnostic_baseline.for_section("name")

        self._loading = True
        blockers = [QSignalBlocker(self.name_edit)]
        blockers.extend(QSignalBlocker(edit) for edit in self.profile_edits.values())
        self.name_edit.setText(sheet.character_name)
        for key, edit in self.profile_edits.items():
            value = profile.get(key, "") if isinstance(profile, dict) else ""
            edit.setPlainText(value if isinstance(value, str) else "")
        del blockers
        self._loading = False

        self.name_edit.setReadOnly(not name_section.editable)
        for edit in self.profile_edits.values():
            edit.setReadOnly(not profile_section.editable)
        self.left_comparison_edit.setReadOnly(not profile_section.editable)
        self.right_comparison_edit.setReadOnly(not profile_section.editable)
        reasons = [
            section.read_only_reason
            for section in (name_section, profile_section)
            if not section.editable and section.read_only_reason
        ]
        self.section_message.setText(
            "読み取り専用: " + " / ".join(reasons) if reasons else ""
        )
        icon_section = sheet.diagnostic_baseline.for_section("icon")
        self.replace_icon_button.setEnabled(icon_section.editable)
        self.replace_icon_button.setToolTip(
            "PNG・JPEG・WebPを正方形に切り抜いて差し替えます"
            if icon_section.editable
            else f"画像は読み取り専用です: {icon_section.read_only_reason}"
        )
        self.icon_preview.setPixmap(QPixmap())
        self.icon_preview.setText("プレビューは未読込です")
        self._reload_comparison_views()
        self._refresh_counters()

    def current_name(self) -> str:
        return self.name_edit.text()

    def current_profiles(self) -> dict[str, str]:
        return {
            key: edit.toPlainText()
            for key, edit in self.profile_edits.items()
        }

    def set_personality_keywords(self, names: list[str]) -> None:
        self.personality_reference.setText(
            "\n".join(f"・{name}" for name in names) if names else "未設定"
        )

    def show_profile_comparison(self) -> None:
        if self.comparison_window is not None:
            self.comparison_window.show()
            self.comparison_window.raise_()
            self.comparison_window.activateWindow()
            return
        self.comparison_host.show()
        self.show_comparison_button.setEnabled(False)
        self.left_profile_selector.setFocus()

    def hide_profile_comparison(self) -> None:
        if self.comparison_window is not None:
            self.comparison_window.close()
            return
        self.comparison_host.hide()
        self.show_comparison_button.setEnabled(True)

    def open_profile_comparison(self) -> None:
        if self.comparison_window is not None:
            self.comparison_window.show()
            self.comparison_window.raise_()
            self.comparison_window.activateWindow()
            return
        dialog = QDialog(self.window())
        dialog.setWindowTitle("プロフィール比較")
        dialog.setModal(False)
        dialog.resize(980, 460)
        dialog_layout = QVBoxLayout(dialog)
        self.comparison_host.hide()
        self.comparison_host_layout.removeWidget(self.comparison_panel)
        self.comparison_panel.setParent(dialog)
        dialog_layout.addWidget(self.comparison_panel)
        self.detach_comparison_button.setEnabled(False)
        self.show_comparison_button.setEnabled(False)
        dialog.finished.connect(self._restore_profile_comparison)
        self.comparison_window = dialog
        dialog.show()

    def _restore_profile_comparison(self) -> None:
        dialog = self.comparison_window
        if dialog is None:
            return
        layout = dialog.layout()
        if layout is not None:
            layout.removeWidget(self.comparison_panel)
        self.comparison_panel.setParent(self.comparison_host)
        self.comparison_host_layout.addWidget(self.comparison_panel)
        self.detach_comparison_button.setEnabled(True)
        self.comparison_host.hide()
        self.show_comparison_button.setEnabled(True)
        self.comparison_window = None
        dialog.deleteLater()

    def show_icon_preview(self) -> None:
        if self._sheet is None:
            return
        data = self._sheet.data.get("data")
        icon = data.get("icon") if isinstance(data, dict) else None
        uri = icon.get("dataUri") if isinstance(icon, dict) else None
        try:
            if not isinstance(uri, str) or not uri.startswith("data:image/"):
                raise ImageSafetyError("埋込画像URIを確認できません")
            _header, encoded = uri.split(",", 1)
            if len(encoded) > ((64 * 1024 * 1024 + 2) // 3) * 4:
                raise ImageSafetyError("埋込画像が64 MiB上限を超えています")
            image_bytes = base64.b64decode(encoded, validate=True)
            inspect_image_bytes(image_bytes)
            pixmap = QPixmap()
            if not pixmap.loadFromData(image_bytes):
                raise ImageSafetyError("画像プレビューを生成できません")
        except (ValueError, binascii.Error, ImageSafetyError) as exc:
            self.icon_preview.setPixmap(QPixmap())
            self.icon_preview.setText(f"プレビューできません\n{exc}")
            return
        self.icon_preview.setText("")
        self.icon_preview.setPixmap(
            pixmap.scaled(
                160,
                160,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def set_replacement_preview(self, webp_bytes: bytes) -> None:
        pixmap = QPixmap()
        if pixmap.loadFromData(webp_bytes):
            self.icon_preview.setText("")
            self.icon_preview.setPixmap(
                pixmap.scaled(
                    160,
                    160,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def _name_edited(self, value: str) -> None:
        if self._loading or self._draft is None:
            return
        self._draft.set_name(value)
        self._refresh_counters()
        self.changed.emit()

    def _profile_edited(self, key: str) -> None:
        if self._loading or self._draft is None:
            return
        self._untouched_profile_keys.discard(key)
        self._draft.set_profile(key, self.profile_edits[key].toPlainText())
        self._sync_comparison_key(key)
        self._refresh_counters()
        self.changed.emit()

    def _comparison_selection_changed(self, side: str) -> None:
        if self._comparison_loading:
            return
        selector = (
            self.left_profile_selector
            if side == "left"
            else self.right_profile_selector
        )
        other_selector = (
            self.right_profile_selector
            if side == "left"
            else self.left_profile_selector
        )
        if selector.currentData() == other_selector.currentData():
            fallback = next(
                index
                for index in range(other_selector.count())
                if other_selector.itemData(index) != selector.currentData()
            )
            blocker = QSignalBlocker(other_selector)
            other_selector.setCurrentIndex(fallback)
            del blocker
        self._reload_comparison_views()

    def _comparison_edited(self, side: str) -> None:
        if self._comparison_loading or self._loading or self._draft is None:
            return
        selector = (
            self.left_profile_selector
            if side == "left"
            else self.right_profile_selector
        )
        comparison_edit = (
            self.left_comparison_edit
            if side == "left"
            else self.right_comparison_edit
        )
        key = str(selector.currentData())
        value = comparison_edit.toPlainText()
        original = self.profile_edits[key]
        blocker = QSignalBlocker(original)
        original.setPlainText(value)
        del blocker
        self._untouched_profile_keys.discard(key)
        self._draft.set_profile(key, value)
        self._sync_comparison_key(key, source=comparison_edit)
        self._refresh_counters()
        self.changed.emit()

    def _reload_comparison_views(self) -> None:
        self._comparison_loading = True
        try:
            for selector, edit in (
                (self.left_profile_selector, self.left_comparison_edit),
                (self.right_profile_selector, self.right_comparison_edit),
            ):
                key = str(selector.currentData())
                source = self.profile_edits.get(key)
                edit.setPlainText(source.toPlainText() if source is not None else "")
        finally:
            self._comparison_loading = False
        self._refresh_comparison_counters()

    def _sync_comparison_key(
        self,
        key: str,
        *,
        source: QPlainTextEdit | None = None,
    ) -> None:
        value = self.profile_edits[key].toPlainText()
        for selector, edit in (
            (self.left_profile_selector, self.left_comparison_edit),
            (self.right_profile_selector, self.right_comparison_edit),
        ):
            if selector.currentData() != key or edit is source:
                continue
            blocker = QSignalBlocker(edit)
            edit.setPlainText(value)
            del blocker
        self._refresh_comparison_counters()

    def _refresh_comparison_counters(self) -> None:
        self._set_counter(
            self.left_comparison_counter,
            len(self.left_comparison_edit.toPlainText()),
            1000,
        )
        self._set_counter(
            self.right_comparison_counter,
            len(self.right_comparison_edit.toPlainText()),
            1000,
        )

    def _refresh_counters(self) -> None:
        self._set_counter(self.name_counter, len(self.name_edit.text()), 20)
        for key, edit in self.profile_edits.items():
            changed = (
                key not in self._untouched_profile_keys
                and edit.toPlainText() != self._baseline_profiles[key]
            )
            self.profile_change_labels[key].setText(
                "変更あり" if changed else "変更なし"
            )
            value = (
                self._baseline_profiles[key]
                if key in self._untouched_profile_keys
                else edit.toPlainText()
            )
            self._set_counter(
                self.profile_counters[key],
                len(value),
                1000,
            )
        self._refresh_comparison_counters()

    @staticmethod
    def _set_counter(label: QLabel, count: int, limit: int) -> None:
        label.setText(f"{count} / {limit}")
        label.setProperty("state", "error" if count > limit else "normal")
