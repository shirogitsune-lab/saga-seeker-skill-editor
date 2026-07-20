"""Main application window."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QStyle,
    QTabWidget,
    QApplication,
    QVBoxLayout,
    QWidget,
)

from saga_seeker_skill_editor.core.character_sheet import CharacterSheet, CharacterSheetError, load_character_sheet
from saga_seeker_skill_editor.core.file_writer import SaveError, atomic_save_bytes
from saga_seeker_skill_editor.core.personality_catalog import (
    PersonalityCatalogError,
    load_personality_catalog,
)
from saga_seeker_skill_editor.core.personality_editor import (
    render_personality_selections,
)
from saga_seeker_skill_editor.core.sheet_editor import (
    SheetEditError,
    render_empty_slot_creation,
    render_name_description_edit,
    render_protected_skill_replacement,
    render_skill_deletion,
    render_vacant_slot_creation,
)
from saga_seeker_skill_editor.core.skill_classifier import SkillKind
from saga_seeker_skill_editor.gui.collapsible_section import CollapsibleSection
from saga_seeker_skill_editor.gui.personality_editor_widget import PersonalityEditorWidget
from saga_seeker_skill_editor.gui.skill_editor_widget import SkillEditorWidget
from saga_seeker_skill_editor.gui.skill_list_widget import SkillListWidget
from saga_seeker_skill_editor.gui.theme_manager import DEFAULT_THEME, ThemeId, ThemeManager, refresh_widget_style
from saga_seeker_skill_editor.gui.vacant_slot_editor_widget import VacantSlotEditorWidget


class MainState(Enum):
    UNLOADED = "unloaded"
    NORMAL = "normal"
    DIRTY = "dirty"
    ERROR = "error"


class LeaveChoice(Enum):
    SAVE_AS = "save_as"
    DISCARD = "discard"
    CANCEL = "cancel"


@dataclass(frozen=True)
class UiError:
    title: str
    cause: str
    impact: str
    remedy: str
    details: str


class MainWindow(QMainWindow):
    def __init__(self, *, theme_manager: ThemeManager | None = None) -> None:
        super().__init__()
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("QApplication must exist before MainWindow")
        if theme_manager is None:
            theme_manager = ThemeManager(app)
            theme_manager.apply_theme(DEFAULT_THEME, persist=False)
        self.theme_manager = theme_manager
        self.setWindowTitle("Saga & Seeker スキルエディター")
        self.resize(1100, 760)
        self.setMinimumSize(860, 600)
        self.current_path: Path | None = None
        self.sheet: CharacterSheet | None = None
        self.skill_widgets: list[SkillEditorWidget | VacantSlotEditorWidget] = []
        try:
            self.personality_catalog = load_personality_catalog()
            self.personality_catalog_error = ""
        except PersonalityCatalogError as exc:
            self.personality_catalog = ()
            self.personality_catalog_error = str(exc)
        self.active_error: UiError | None = None
        self.validation_error: str | None = None
        self.changed_indices: set[int] = set()
        self.personality_changed_indices: set[int] = set()
        self.main_state = MainState.UNLOADED

        self._create_actions()
        self._create_summary()
        self._create_content()
        self._create_status_bar()
        self._create_menu()

        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)
        root_layout.addWidget(self.summary_panel)
        root_layout.addWidget(self.content_stack, 1)
        root_layout.addWidget(self.status_bar)
        root = QWidget()
        root.setLayout(root_layout)
        self.setCentralWidget(root)
        self.setAcceptDrops(True)
        self._sync_ui_state()

    @property
    def unsaved_changes(self) -> bool:
        return self._has_changes()

    def _has_changes(self) -> bool:
        return bool(self.changed_indices or self.personality_changed_indices)

    def _change_count(self) -> int:
        return len(self.changed_indices) + len(self.personality_changed_indices)

    def _create_actions(self) -> None:
        self.open_action = QAction("HTMLファイルを開く", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.open_file)

        self.save_action = QAction("別名で保存", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.save_action.triggered.connect(self.save_as)

        self.reload_action = QAction("現在のファイルを再読込", self)
        self.reload_action.setShortcut(QKeySequence("F5"))
        self.reload_action.triggered.connect(self.reload_current_file)

        self.close_action = QAction("終了", self)
        self.close_action.setShortcut(QKeySequence.StandardKey.Close)
        self.close_action.triggered.connect(self.close)

        self.focus_action = QAction("一覧と編集フォームのフォーカスを切り替える", self)
        self.focus_action.setShortcut(QKeySequence("F6"))
        self.focus_action.triggered.connect(self._toggle_pane_focus)

        self.find_personality_action = QAction("性格キーワードを検索", self)
        self.find_personality_action.setShortcut(QKeySequence.StandardKey.Find)
        self.find_personality_action.triggered.connect(self._focus_personality_search)

        for action in (
            self.open_action,
            self.save_action,
            self.reload_action,
            self.close_action,
            self.focus_action,
            self.find_personality_action,
        ):
            self.addAction(action)

    def _create_summary(self) -> None:
        self.summary_panel = QFrame()
        self.summary_panel.setObjectName("summaryPanel")
        self.character_label = QLabel("キャラクター未読込")
        self.character_label.setObjectName("characterName")
        self.file_label = QLabel("HTMLファイルが選択されていません")
        self.file_label.setObjectName("mutedText")
        self.slot_summary_label = QLabel("スキル欄は未読込です")
        self.slot_summary_label.setObjectName("mutedText")

        self.open_button = QPushButton("HTMLファイルを開く")
        self.open_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.open_button.clicked.connect(self.open_action.trigger)
        self.reload_button = QPushButton("再読込")
        self.reload_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.reload_button.clicked.connect(self.reload_action.trigger)

        heading = QVBoxLayout()
        heading.setSpacing(2)
        heading.addWidget(self.character_label)
        heading.addWidget(self.file_label)
        heading.addWidget(self.slot_summary_label)

        commands = QHBoxLayout()
        commands.addWidget(self.open_button)
        commands.addWidget(self.reload_button)

        top = QHBoxLayout()
        top.addLayout(heading, 1)
        top.addLayout(commands)

        self.path_value = QLabel("-")
        self.path_value.setObjectName("technicalValue")
        self.path_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path_value.setWordWrap(True)
        details_content = QWidget()
        details_form = QFormLayout(details_content)
        details_form.setContentsMargins(16, 2, 8, 8)
        details_form.addRow("完全なファイルパス", self.path_value)
        self.sheet_details = CollapsibleSection("キャラクターシートの詳細情報", details_content)

        layout = QVBoxLayout(self.summary_panel)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.addLayout(top)
        layout.addWidget(self.sheet_details)

    def _create_content(self) -> None:
        self.content_stack = QStackedWidget()
        self.empty_page = QWidget()
        empty_title = QLabel("Saga & Seeker キャラクターシート")
        empty_title.setObjectName("characterName")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_note = QLabel("編集するHTMLファイルを選択してください")
        empty_note.setObjectName("mutedText")
        empty_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_open_button = QPushButton("HTMLファイルを開く")
        self.empty_open_button.setProperty("role", "primary")
        self.empty_open_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.empty_open_button.clicked.connect(self.open_action.trigger)
        empty_layout = QVBoxLayout(self.empty_page)
        empty_layout.addStretch(2)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_note)
        empty_layout.addWidget(self.empty_open_button, 0, Qt.AlignmentFlag.AlignCenter)
        empty_layout.addStretch(3)

        self.skill_list = SkillListWidget()
        self.skill_list.setMinimumWidth(470)
        self.skill_list.currentItemChanged.connect(self._on_skill_selected)

        self.editor_stack = QStackedWidget()
        no_selection = QLabel("左の一覧からスキルを選択してください")
        no_selection.setAlignment(Qt.AlignmentFlag.AlignCenter)
        no_selection.setObjectName("mutedText")
        self.editor_stack.addWidget(no_selection)
        editor_scroll = QScrollArea()
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setFrameShape(QFrame.Shape.NoFrame)
        editor_scroll.setWidget(self.editor_stack)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.skill_list)
        splitter.addWidget(editor_scroll)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([500, 600])

        skill_page = QWidget()
        skill_layout = QVBoxLayout(skill_page)
        skill_layout.setContentsMargins(0, 0, 0, 0)
        skill_layout.addWidget(splitter)

        self.personality_editor = PersonalityEditorWidget(self.personality_catalog)
        self.personality_editor.changed.connect(self._recalculate_changes)
        personality_scroll = QScrollArea()
        personality_scroll.setWidgetResizable(True)
        personality_scroll.setFrameShape(QFrame.Shape.NoFrame)
        personality_scroll.setWidget(self.personality_editor)

        self.edit_tabs = QTabWidget()
        self.edit_tabs.addTab(skill_page, "スキル")
        self.edit_tabs.addTab(personality_scroll, "性格キーワード")

        self.loaded_page = QWidget()
        loaded_layout = QVBoxLayout(self.loaded_page)
        loaded_layout.setContentsMargins(0, 0, 0, 0)
        loaded_layout.addWidget(self.edit_tabs)

        self.content_stack.addWidget(self.empty_page)
        self.content_stack.addWidget(self.loaded_page)

    def _create_status_bar(self) -> None:
        self.status_bar = QFrame()
        self.status_bar.setObjectName("statusBar")
        self.status_label = QLabel("○ 未読込")
        self.status_detail_label = QLabel("HTMLファイルを開いてください")
        self.status_detail_label.setObjectName("mutedText")
        self.read_only_badge = QLabel("読み取り専用")
        self.personality_read_only_badge = QLabel("性格キーワード読み取り専用")
        self.protected_badge = QLabel("一部保護中")
        self.id_repair_badge = QLabel("ID修復が必要")
        self.changed_count_label = QLabel("変更 0件")
        for badge in (
            self.read_only_badge,
            self.personality_read_only_badge,
            self.protected_badge,
            self.id_repair_badge,
            self.changed_count_label,
        ):
            badge.setProperty("badge", True)

        self.reset_button = QPushButton("変更を破棄")
        self.reset_button.clicked.connect(self.reset_edits)
        self.save_button = QPushButton("別名で保存")
        self.save_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.save_button.clicked.connect(self.save_action.trigger)

        state_text = QVBoxLayout()
        state_text.setSpacing(1)
        state_text.addWidget(self.status_label)
        state_text.addWidget(self.status_detail_label)

        badges = QHBoxLayout()
        badges.addWidget(self.read_only_badge)
        badges.addWidget(self.personality_read_only_badge)
        badges.addWidget(self.protected_badge)
        badges.addWidget(self.id_repair_badge)
        badges.addWidget(self.changed_count_label)
        badges.addStretch(1)

        layout = QHBoxLayout(self.status_bar)
        layout.setContentsMargins(12, 8, 10, 8)
        layout.addLayout(state_text)
        layout.addSpacing(12)
        layout.addLayout(badges, 1)
        layout.addWidget(self.reset_button)
        layout.addWidget(self.save_button)

    def _create_menu(self) -> None:
        file_menu = self.menuBar().addMenu("ファイル(&F)")
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.reload_action)
        file_menu.addSeparator()
        file_menu.addAction(self.save_action)
        file_menu.addSeparator()
        file_menu.addAction(self.close_action)

        view_menu = self.menuBar().addMenu("表示(&V)")
        appearance_menu = view_menu.addMenu("外観(&A)")
        self.appearance_action_group = QActionGroup(self)
        self.appearance_action_group.setExclusive(True)
        self.appearance_actions: dict[ThemeId, QAction] = {}
        labels = {
            ThemeId.LIGHT: "ライト",
            ThemeId.DARK: "ダーク",
            ThemeId.HIGH_CONTRAST: "ハイコントラスト",
        }
        for theme in (ThemeId.LIGHT, ThemeId.DARK, ThemeId.HIGH_CONTRAST):
            action = QAction(labels[theme], self)
            action.setCheckable(True)
            action.setData(theme.value)
            self.appearance_action_group.addAction(action)
            appearance_menu.addAction(action)
            self.appearance_actions[theme] = action
        self.appearance_action_group.triggered.connect(self._apply_selected_theme)
        self._sync_theme_actions()
        view_menu.addSeparator()
        view_menu.addAction(self.find_personality_action)
        view_menu.addAction(self.focus_action)

    def _apply_selected_theme(self, action: QAction) -> None:
        theme = ThemeId(str(action.data()))
        result = self.theme_manager.apply_theme(theme)
        self._sync_theme_actions(result.applied)

    def _sync_theme_actions(self, theme: ThemeId | None = None) -> None:
        selected = theme or self.theme_manager.current_theme
        for action_theme, action in self.appearance_actions.items():
            action.setChecked(action_theme == selected)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls() and len(event.mimeData().urls()) == 1:
            path = Path(event.mimeData().urls()[0].toLocalFile())
            if path.suffix.lower() == ".html":
                event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if urls:
            self.load_path(Path(urls[0].toLocalFile()))

    def open_file(self) -> None:
        path = self._choose_open_path()
        if path is not None:
            self.load_path(path)

    def _choose_open_path(self) -> Path | None:
        path, _ = QFileDialog.getOpenFileName(self, "キャラクターシートを開く", "", "HTML Files (*.html)")
        return Path(path) if path else None

    def reload_current_file(self) -> None:
        if self.current_path is not None:
            self.load_path(self.current_path)

    def load_path(self, path: Path) -> bool:
        if not self._resolve_unsaved_changes():
            return False
        try:
            sheet = load_character_sheet(path.read_bytes())
        except (OSError, CharacterSheetError) as exc:
            impact = (
                "現在開いているシートと編集中の内容は保持されています。"
                if self.sheet is not None
                else "このファイルの編集は開始されていません。"
            )
            self._record_error(
                title="読み込みエラー",
                cause="選択したHTMLを安全なキャラクターシートとして読み込めませんでした。",
                impact=impact,
                remedy="別のHTMLを選択するか、元のゲームからシートを再出力してください。",
                details=str(exc),
            )
            return False
        self._apply_sheet(path, sheet)
        return True

    def _apply_sheet(self, path: Path, sheet: CharacterSheet) -> None:
        self.current_path = path
        self.sheet = sheet
        self.active_error = None
        self.validation_error = None
        self.character_label.setText(sheet.character_name or "名称未設定のキャラクター")
        self.file_label.setText(path.name)
        self.file_label.setToolTip(str(path))
        self.slot_summary_label.setText(
            f"スキル欄: 登録済み {len(sheet.entries)} / 全{sheet.slot_count}枠 | "
            f"未使用枠 {sheet.vacant_slot_count} | "
            f"性格キーワード {len(sheet.personality_entries)} / {sheet.personality_slot_count or 6}件"
        )
        self.path_value.setText(str(path))
        self._rebuild_skill_widgets()
        self.personality_editor.set_sheet(sheet)
        if self.personality_catalog_error:
            self.personality_editor.set_validation_error(self.personality_catalog_error)
        self.content_stack.setCurrentWidget(self.loaded_page)
        self._recalculate_changes()
        if self.skill_list.topLevelItemCount():
            self.skill_list.setCurrentItem(self.skill_list.topLevelItem(0))

    def save_as(self) -> bool:
        self._recalculate_changes()
        if self.sheet is None or not self._has_changes() or self.sheet.read_only:
            return False
        if self.validation_error is not None:
            self._present_validation_error(self.validation_error)
            return False
        for widget in self.skill_widgets:
            if widget.state().changed and not widget.prepare_for_save():
                return False

        destination = self._choose_save_path()
        if destination is None:
            return False
        overwrite_confirmed = False
        if destination.exists():
            result = QMessageBox.warning(
                self,
                "上書き確認",
                "保存先に既存ファイルがあります。置き換えてよろしいですか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if result != QMessageBox.StandardButton.Yes:
                return False
            overwrite_confirmed = True

        try:
            rendered = self._render_current_edits()

            def validate_temp(temp_path: Path) -> None:
                load_character_sheet(temp_path.read_bytes())

            atomic_save_bytes(
                destination,
                rendered,
                overwrite_confirmed=overwrite_confirmed,
                validate_temp_path=validate_temp,
            )
            saved_sheet = load_character_sheet(rendered)
        except (SaveError, SheetEditError, CharacterSheetError, OSError) as exc:
            self._record_error(
                title="保存エラー",
                cause="編集内容を指定した保存先へ書き込めませんでした。",
                impact="読み込み済みデータと編集中の内容は保持されています。",
                remedy="保存先やアクセス権を確認し、別の保存先でもう一度保存してください。",
                details=str(exc),
            )
            return False

        self._apply_sheet(destination, saved_sheet)
        self.status_detail_label.setText(f"保存しました: {destination.name}")
        return True

    def _choose_save_path(self) -> Path | None:
        if self.sheet is None:
            return None
        default_name = f"{self.sheet.character_name or 'character'}_編集済み.html"
        path, _ = QFileDialog.getSaveFileName(self, "別名で保存", default_name, "HTML Files (*.html)")
        return Path(path) if path else None

    def reset_edits(self) -> None:
        for widget in self.skill_widgets:
            widget.reset()
        self.personality_editor.reset()
        self.active_error = None
        self.validation_error = None
        self._recalculate_changes()
        self.status_detail_label.setText("読み込み時または保存成功時の状態に戻しました")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._resolve_unsaved_changes():
            event.accept()
        else:
            event.ignore()

    def _resolve_unsaved_changes(self) -> bool:
        self._recalculate_changes()
        if not self._has_changes():
            return True
        choice = self._ask_unsaved_action()
        if choice == LeaveChoice.CANCEL:
            return False
        if choice == LeaveChoice.DISCARD:
            return True
        return self.save_as()

    def _ask_unsaved_action(self) -> LeaveChoice:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("未保存の変更")
        box.setText(f"{self._change_count()}件の未保存変更があります。")
        box.setInformativeText("別のHTMLを開く前または終了する前に、変更の扱いを選択してください。")
        save_button = box.addButton("別名で保存", QMessageBox.ButtonRole.AcceptRole)
        discard_button = box.addButton("変更を破棄", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = box.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save_button)
        box.setEscapeButton(cancel_button)
        box.exec()
        if box.clickedButton() is save_button:
            return LeaveChoice.SAVE_AS
        if box.clickedButton() is discard_button:
            return LeaveChoice.DISCARD
        return LeaveChoice.CANCEL

    def _render_current_edits(self) -> bytes:
        if self.sheet is None:
            raise SheetEditError("sheet is not loaded")
        states = [widget.state() for widget in self.skill_widgets]
        has_deletion = any(state.changed and state.deletion_requested for state in states)
        has_creation = any(state.changed and state.vacant_creation for state in states)
        if has_deletion and has_creation:
            raise SheetEditError("skill creation and deletion cannot be saved in the same operation")

        current = self.sheet.raw_html
        for state in states:
            if not state.changed or state.deletion_requested or state.vacant_creation:
                continue
            current_sheet = load_character_sheet(current)
            if state.replacement_confirmed:
                current = render_protected_skill_replacement(
                    current_sheet,
                    index=state.index,
                    name=state.name,
                    description=state.description,
                    first_confirmation=True,
                    second_confirmation=True,
                )
            elif current_sheet.entries[state.index].classification.kind == SkillKind.EMPTY_SLOT:
                current = render_empty_slot_creation(
                    current_sheet,
                    index=state.index,
                    name=state.name,
                    description=state.description,
                )
            else:
                current = render_name_description_edit(
                    current_sheet,
                    index=state.index,
                    name=state.name,
                    description=state.description,
                    repair_id_confirmed=state.repair_id_confirmed,
                )
        for state in states:
            if state.changed and state.deletion_requested:
                current = render_skill_deletion(load_character_sheet(current), index=state.index)
        for state in states:
            if state.changed and state.vacant_creation:
                current_sheet = load_character_sheet(current)
                if state.index != len(current_sheet.entries):
                    raise SheetEditError("skills must be added to vacant slots from the beginning")
                current = render_vacant_slot_creation(
                    current_sheet,
                    name=state.name,
                    description=state.description,
                )
        if self.personality_changed_indices:
            current = render_personality_selections(
                load_character_sheet(current),
                keyword_ids=self.personality_editor.selected_ids(),
                catalog=self.personality_catalog,
            )
        return current

    def _rebuild_skill_widgets(self) -> None:
        while self.editor_stack.count() > 1:
            widget = self.editor_stack.widget(1)
            self.editor_stack.removeWidget(widget)
            widget.deleteLater()
        self.skill_widgets = []
        self.skill_list.clear()
        if self.sheet is None:
            return
        safe_slot_count = len(self.sheet.entries) + len(self.sheet.vacant_lis)
        self.skill_list.populate(self.sheet.entries, slot_count=safe_slot_count)
        for entry in self.sheet.entries:
            widget = SkillEditorWidget(
                entry,
                is_last_entry=entry.index == len(self.sheet.entries) - 1,
                read_only_reason=self.sheet.read_only_reason if self.sheet.read_only else None,
            )
            widget.changed.connect(self._recalculate_changes)
            self.skill_widgets.append(widget)
            self.editor_stack.addWidget(widget)
        for slot_index in range(len(self.sheet.entries), safe_slot_count):
            widget = VacantSlotEditorWidget(
                slot_index,
                creation_enabled=not self.sheet.read_only,
                read_only_reason=self.sheet.read_only_reason if self.sheet.read_only else None,
            )
            widget.changed.connect(self._recalculate_changes)
            self.skill_widgets.append(widget)
            self.editor_stack.addWidget(widget)

    def _recalculate_changes(self) -> None:
        changed: set[int] = set()
        states = [widget.state() for widget in self.skill_widgets]
        has_deletion = any(state.changed and state.deletion_requested for state in states)
        has_creation = any(state.changed and state.vacant_creation for state in states)
        vacant_states = {state.index: state for state in states if state.vacant_creation}
        validation_errors: dict[int, str] = {}
        changed_vacant_indices = [
            state.index for state in vacant_states.values() if state.changed
        ]
        if changed_vacant_indices and self.sheet is not None:
            last_requested = max(changed_vacant_indices)
            for index in range(len(self.sheet.entries), last_requested + 1):
                state = vacant_states.get(index)
                if state is None or state.name == "":
                    validation_errors[index] = (
                        f"スロット {index + 1} が空欄です。"
                        "スキルは前の枠から連続するように名前を入力してください。"
                    )
        skill_validation_error = next(iter(validation_errors.values()), None)
        for widget, state in zip(self.skill_widgets, states, strict=True):
            if state.changed:
                changed.add(state.index)
            widget.set_change_indicator(state.changed)
            self.skill_list.set_changed(state.index, state.changed)
            if state.vacant_creation:
                self.skill_list.update_vacant_name(state.index, state.name)
                widget.set_creation_available(
                    (not has_deletion or state.changed)
                    and self.sheet is not None
                    and not self.sheet.read_only
                )
                widget.set_validation_error(validation_errors.get(state.index))
            else:
                self.skill_list.update_name(state.index, state.name)
                widget.set_delete_available(not has_creation or state.deletion_requested)
        self.changed_indices = changed
        self.personality_changed_indices = self.personality_editor.changed_indices()
        personality_validation_error = None
        personality_ids = self.personality_editor.selected_ids()
        first_empty = next(
            (index for index, keyword_id in enumerate(personality_ids) if keyword_id is None),
            len(personality_ids),
        )
        if any(keyword_id is not None for keyword_id in personality_ids[first_empty:]):
            personality_validation_error = (
                f"性格キーワードの{first_empty + 1}枠目が未設定です。"
                "後ろの枠を使う場合は、手前の枠から連続して選択してください。"
            )
        assigned_personality_ids = [keyword_id for keyword_id in personality_ids if keyword_id is not None]
        if len(assigned_personality_ids) != len(set(assigned_personality_ids)):
            personality_validation_error = "同じ性格キーワードを複数の枠へ設定することはできません。"
        if self.personality_changed_indices and self.sheet is not None:
            if self.sheet.personality_read_only:
                personality_validation_error = self.sheet.personality_read_only_reason
            elif self.personality_catalog_error:
                personality_validation_error = self.personality_catalog_error
        personality_display_error = personality_validation_error
        if personality_display_error is None and self.sheet is not None and self.sheet.personality_read_only:
            personality_display_error = (
                f"性格キーワードは読み取り専用です: {self.sheet.personality_read_only_reason}"
            )
        self.personality_editor.set_validation_error(personality_display_error)
        self.validation_error = skill_validation_error or personality_validation_error
        self._sync_ui_state()

    def _on_skill_selected(self, current, _previous) -> None:
        if current is None:
            self.editor_stack.setCurrentIndex(0)
            return
        index = self.skill_list.selected_skill_index()
        self.editor_stack.setCurrentIndex(0 if index is None else index + 1)

    def _toggle_pane_focus(self) -> None:
        if self.edit_tabs.currentIndex() == 1:
            self.personality_editor.focus_first_slot()
            return
        if self.skill_list.hasFocus():
            index = self.skill_list.selected_skill_index()
            if index is not None:
                self.skill_widgets[index].name_edit.setFocus()
        else:
            self.skill_list.setFocus()

    def _focus_personality_search(self) -> None:
        if self.sheet is None:
            return
        self.edit_tabs.setCurrentIndex(1)
        self.personality_editor.search_edit.setFocus()

    def _record_error(self, *, title: str, cause: str, impact: str, remedy: str, details: str) -> None:
        self.active_error = UiError(title=title, cause=cause, impact=impact, remedy=remedy, details=details)
        self._sync_ui_state()
        self._present_error_dialog(self.active_error)

    def _present_validation_error(self, message: str) -> None:
        QMessageBox.warning(
            self,
            "入力内容を確認してください",
            message + "\n内容を修正してから、もう一度保存してください。",
        )

    def _present_error_dialog(self, error: UiError) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(error.title)
        box.setText(f"原因\n{error.cause}\n\n影響\n{error.impact}\n\n対処\n{error.remedy}")
        box.setDetailedText(error.details)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()

    def _sync_ui_state(self) -> None:
        if self.active_error is not None or self.validation_error is not None:
            state = MainState.ERROR
        elif self.sheet is None:
            state = MainState.UNLOADED
        elif self._has_changes():
            state = MainState.DIRTY
        else:
            state = MainState.NORMAL
        self.main_state = state

        labels = {
            MainState.UNLOADED: "○ 未読込",
            MainState.NORMAL: "● 正常",
            MainState.DIRTY: "◆ 変更あり",
            MainState.ERROR: "! エラー発生",
        }
        self.status_label.setText(labels[state])
        style_states = {
            MainState.UNLOADED: "unloaded",
            MainState.NORMAL: "normal",
            MainState.DIRTY: "modified",
            MainState.ERROR: "error",
        }
        self.status_label.setProperty("state", style_states[state])
        refresh_widget_style(self.status_label)

        if self.active_error is not None:
            self.status_detail_label.setText(f"{self.active_error.cause} {self.active_error.remedy}")
        elif self.validation_error is not None:
            self.status_detail_label.setText(self.validation_error)
        elif self.sheet is None:
            self.status_detail_label.setText("HTMLファイルを開いてください")
        elif self._has_changes():
            self.status_detail_label.setText("編集内容はまだファイルへ保存されていません")
        elif self.sheet.read_only:
            self.status_detail_label.setText("安全に分類できない箇所があるため編集機能を制限しています")
        elif self.sheet.personality_read_only:
            self.status_detail_label.setText("スキルは編集できますが、性格キーワード欄は読み取り専用です")
        else:
            self.status_detail_label.setText("キャラクターシートを安全に編集できます")

        default_count = 0
        id_repair_count = 0
        if self.sheet is not None:
            default_count = sum(1 for entry in self.sheet.entries if entry.classification.kind == SkillKind.DEFAULT)
            id_repair_count = sum(
                1 for entry in self.sheet.entries if entry.classification.kind == SkillKind.ORIGINAL_NEEDS_ID_REPAIR
            )
        self.read_only_badge.setVisible(bool(self.sheet and self.sheet.read_only))
        self.personality_read_only_badge.setVisible(
            bool(self.sheet and self.sheet.personality_read_only)
        )
        self.protected_badge.setVisible(default_count > 0)
        self.protected_badge.setText(f"一部保護中 {default_count}件")
        self.id_repair_badge.setVisible(id_repair_count > 0)
        self.id_repair_badge.setText(f"ID修復が必要 {id_repair_count}件")
        self.changed_count_label.setVisible(bool(self.sheet))
        self.changed_count_label.setText(f"変更 {self._change_count()}件")

        can_save = bool(self.sheet and self._has_changes() and not self.sheet.read_only)
        self.save_action.setEnabled(can_save)
        self.save_button.setEnabled(can_save)
        self.save_button.setProperty("role", "primary" if can_save else "secondary")
        refresh_widget_style(self.save_button)
        if self.sheet is None:
            save_tooltip = "HTMLファイルが未読込のため保存できません"
        elif self.sheet.read_only:
            save_tooltip = f"読み取り専用のため保存できません: {self.sheet.read_only_reason}"
        elif not self._has_changes():
            save_tooltip = "変更がないため保存できません"
        elif self.validation_error is not None:
            save_tooltip = "保存前に、途中の空欄を修正してください"
        else:
            save_tooltip = "編集内容を新しいHTMLファイルへ保存します"
        self.save_button.setToolTip(save_tooltip)
        self.save_action.setToolTip(save_tooltip)

        self.reset_button.setEnabled(self._has_changes())
        self.reset_button.setToolTip(
            "すべての変更を基準状態へ戻します" if self._has_changes() else "破棄する変更はありません"
        )
        self.reload_action.setEnabled(self.current_path is not None)
        self.reload_button.setEnabled(self.current_path is not None)
        self.content_stack.setCurrentWidget(self.empty_page if self.sheet is None else self.loaded_page)
        self.open_button.setProperty("role", "primary" if self.sheet is None else "secondary")
        refresh_widget_style(self.open_button)
        suffix = " *" if self._has_changes() else ""
        self.setWindowTitle(f"Saga & Seeker スキルエディター{suffix}")
