from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtWidgets import QAbstractItemView, QApplication  # noqa: E402

from saga_seeker_skill_editor.core.character_sheet import load_character_sheet  # noqa: E402
from saga_seeker_skill_editor.core.personality_catalog import load_personality_catalog  # noqa: E402
from saga_seeker_skill_editor.gui.main_window import MainState, MainWindow  # noqa: E402
from saga_seeker_skill_editor.gui import personality_editor_widget  # noqa: E402
from saga_seeker_skill_editor.gui.personality_editor_widget import _create_drag_mime  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _sheet_bytes(personality_ids: list[int]) -> bytes:
    catalog = {keyword.id: keyword for keyword in load_personality_catalog()}
    personalities = [catalog[keyword_id].as_dict() for keyword_id in personality_ids]
    names = [item["name"] for item in personalities] + [""] * (6 - len(personalities))
    personality_lis = "".join(f"<li>{name if name else '&nbsp;'}</li>" for name in names)
    skill = {"id": "sk1", "name": "Original", "description": "Keep", "type": "", "key": ""}
    data = {"data": {"name": "Personality GUI", "skills": [skill], "personalities": personalities}}
    return (
        '<ul id="skills-value"><li data-skill-id="sk1" data-skill-name="Original" '
        'data-skill-type="" data-skill-description="Keep">Original</li></ul>'
        f'<ul id="personality-value">{personality_lis}</ul>'
        f'<script id="character-sheet-data" type="application/json">'
        f'{json.dumps(data, ensure_ascii=False, indent=2)}</script>'
    ).encode("utf-8")


def _window(tmp_path: Path, personality_ids: list[int]) -> MainWindow:
    _app()
    path = tmp_path / "personality.html"
    path.write_bytes(_sheet_bytes(personality_ids))
    window = MainWindow()
    assert window.load_path(path)
    return window


def _select_slot(window: MainWindow, slot: int) -> None:
    window.personality_editor.slot_tree.setCurrentItem(
        window.personality_editor.slot_tree.topLevelItem(slot)
    )


def _select_result(window: MainWindow, keyword_id: int) -> None:
    tree = window.personality_editor.result_tree
    for group_index in range(tree.topLevelItemCount()):
        group = tree.topLevelItem(group_index)
        for child_index in range(group.childCount()):
            child = group.child(child_index)
            if child.data(0, Qt.ItemDataRole.UserRole) == keyword_id:
                tree.setCurrentItem(child)
                return
    raise AssertionError(f"keyword {keyword_id} is not visible")


def _assign(window: MainWindow, slot: int, keyword_id: int) -> None:
    _select_slot(window, slot)
    keyword = window.personality_editor.catalog_by_id[keyword_id]
    if not window.personality_editor.search_edit.text():
        window.personality_editor.category_buttons[keyword.type].click()
    _select_result(window, keyword_id)
    assert window.personality_editor.apply_button.isEnabled()
    window.personality_editor.apply_button.click()


def test_personality_tab_has_six_slots_and_browsable_catalog(tmp_path: Path) -> None:
    window = _window(tmp_path, [1])
    editor = window.personality_editor

    assert (
        window.edit_tabs.tabText(window.personality_tab_index)
        == "性格キーワード"
    )
    assert editor.slot_tree.topLevelItemCount() == 6
    first = editor.slot_tree.topLevelItem(0)
    assert first.text(editor.SLOT_NAME_COLUMN) == "勇敢"
    assert first.text(editor.SLOT_TYPE_COLUMN) == "力"
    assert first.text(editor.SLOT_KARMA_COLUMN) == "美徳"
    assert first.text(editor.SLOT_ID_COLUMN) == "1"
    assert tuple(editor.category_buttons) == ("すべて", "力", "知恵", "富", "愛", "法")
    assert tuple(editor.karma_buttons) == ("すべて", "美徳", "中庸", "悪徳")
    assert editor.category_buttons["力"].isChecked()
    assert editor.karma_buttons["すべて"].isChecked()
    assert editor.category_buttons["力"].sizePolicy().verticalPolicy().name == "Fixed"
    assert editor.category_buttons["力"].font().pointSizeF() >= 10
    assert editor.visible_result_ids() == tuple(range(1, 31))
    assert editor.slot_tree.dragDropMode() == QAbstractItemView.DragDropMode.DragDrop
    assert editor.result_tree.dragDropMode() == QAbstractItemView.DragDropMode.DragOnly
    assert editor.move_up_button.text() == "上へ移動"
    assert editor.move_down_button.text() == "下へ移動"
    assert not editor.move_up_button.icon().isNull()
    assert not editor.move_down_button.icon().isNull()
    assert [editor.result_tree.topLevelItem(index).text(0) for index in range(3)] == [
        "美徳 (12件)",
        "中庸 (9件)",
        "悪徳 (9件)",
    ]


def test_personality_change_and_revert_are_comparison_based(tmp_path: Path) -> None:
    window = _window(tmp_path, [1])

    _assign(window, 0, 31)
    assert window.personality_changed_indices == {0}
    assert window.main_state == MainState.DIRTY
    assert window.save_button.isEnabled()

    _assign(window, 0, 1)
    assert window.personality_changed_indices == set()
    assert window.main_state == MainState.NORMAL
    assert window.save_button.isEnabled()


def test_personality_gap_and_duplicate_errors_clear_after_correction(tmp_path: Path) -> None:
    window = _window(tmp_path, [1])

    _assign(window, 2, 32)
    assert window.main_state == MainState.ERROR
    assert window.validation_error is not None and "2枠目が未設定" in window.validation_error

    _assign(window, 1, 2)
    assert window.validation_error is None
    assert window.main_state == MainState.DIRTY

    _select_slot(window, 2)
    window.personality_editor.category_buttons["力"].click()
    _select_result(window, 2)
    assert not window.personality_editor.apply_button.isEnabled()
    assert "すでに枠 2" in window.personality_editor.selection_detail_label.text()
    assert window.validation_error is None


def test_partial_search_crosses_categories_and_keeps_karma_order(tmp_path: Path) -> None:
    window = _window(tmp_path, [])
    editor = window.personality_editor

    editor.search_edit.setText("無")
    visible = [editor.catalog_by_id[keyword_id] for keyword_id in editor.visible_result_ids()]

    assert visible
    assert all("無" in keyword.name for keyword in visible)
    assert len({keyword.type for keyword in visible}) > 1
    assert editor.category_buttons["すべて"].isChecked()
    assert editor.scope_label.text().startswith("系統: すべて / 傾向: すべて")
    shown_karma = [
        editor.result_tree.topLevelItem(index).text(0).split(" ", 1)[0]
        for index in range(editor.result_tree.topLevelItemCount())
    ]
    assert shown_karma == [karma for karma in editor.KARMA_ORDER if any(k.karma == karma for k in visible)]


def test_category_filter_combines_with_existing_partial_search(tmp_path: Path) -> None:
    window = _window(tmp_path, [])
    editor = window.personality_editor
    editor.search_edit.setText("気")

    editor.category_buttons["愛"].click()

    assert editor.search_edit.text() == "気"
    assert editor.category_buttons["愛"].isChecked()
    visible = [editor.catalog_by_id[keyword_id] for keyword_id in editor.visible_result_ids()]
    assert visible
    assert all(keyword.type == "愛" and "気" in keyword.name for keyword in visible)


def test_karma_filter_combines_with_category_and_preserves_order(tmp_path: Path) -> None:
    window = _window(tmp_path, [])
    editor = window.personality_editor

    editor.category_buttons["力"].click()
    editor.karma_buttons["中庸"].click()

    visible = [editor.catalog_by_id[keyword_id] for keyword_id in editor.visible_result_ids()]
    assert len(visible) == 9
    assert all(keyword.type == "力" and keyword.karma == "中庸" for keyword in visible)
    assert editor.result_tree.topLevelItemCount() == 1
    assert editor.result_tree.topLevelItem(0).text(0) == "中庸 (9件)"
    assert "系統: 力 / 傾向: 中庸" in editor.scope_label.text()


def test_find_shortcut_focuses_search_and_enter_assigns_first_match(tmp_path: Path) -> None:
    window = _window(tmp_path, [])
    editor = window.personality_editor

    window.show()
    _app().processEvents()
    window.find_personality_action.trigger()
    _app().processEvents()
    assert window.edit_tabs.currentIndex() == window.personality_tab_index
    assert editor.search_edit.hasFocus()

    editor.search_edit.setText("論理")
    assert editor.visible_result_ids() == (31,)
    editor.search_edit.returnPressed.emit()

    assert editor.selected_ids()[0] == 31
    assert window.main_state == MainState.DIRTY


def test_search_with_no_matches_disables_assignment(tmp_path: Path) -> None:
    window = _window(tmp_path, [])
    editor = window.personality_editor

    editor.search_edit.setText("一致しない検索語")

    assert editor.visible_result_ids() == ()
    assert editor.scope_label.text().endswith("/ 0件")
    assert not editor.apply_button.isEnabled()


def test_personality_only_save_roundtrips_all_catalog_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    window = _window(tmp_path, [1, 2])
    _assign(window, 1, 31)
    _assign(window, 0, 2)
    destination = tmp_path / "saved.html"
    monkeypatch.setattr(window, "_choose_save_path", lambda: destination)

    assert window.save_as()
    saved = load_character_sheet(destination.read_bytes())

    assert [entry.keyword for entry in saved.personality_entries] == [
        {"id": 2, "name": "大胆", "type": "力", "karma": "美徳"},
        {"id": 31, "name": "論理的", "type": "知恵", "karma": "美徳"},
    ]
    assert saved.entries[0].skill["name"] == "Original"
    assert window.personality_changed_indices == set()
    assert window.main_state == MainState.NORMAL


def test_personality_change_participates_in_unsaved_state(tmp_path: Path) -> None:
    window = _window(tmp_path, [])
    _assign(window, 0, 1)

    assert window.unsaved_changes
    assert window._change_count() == 1
    window.reset_edits()
    assert not window.unsaved_changes


def test_middle_deletion_compacts_following_keywords_without_gap_error(tmp_path: Path) -> None:
    window = _window(tmp_path, [1, 2, 31, 32, 33])
    editor = window.personality_editor
    _select_slot(window, 2)

    editor.clear_button.click()

    assert editor.selected_ids() == (1, 2, 32, 33, None, None)
    assert editor.slot_tree.currentItem() is editor.slot_tree.topLevelItem(2)
    assert "前へ詰めました" in editor.operation_label.text()
    assert window.validation_error is None
    assert window.main_state == MainState.DIRTY


def test_move_buttons_reorder_and_reverting_restores_clean_state(tmp_path: Path) -> None:
    window = _window(tmp_path, [1, 2, 31])
    editor = window.personality_editor
    _select_slot(window, 1)

    editor.move_down_button.click()
    assert editor.selected_ids() == (1, 31, 2, None, None, None)
    assert editor._active_slot() == 2
    assert window.main_state == MainState.DIRTY

    editor.move_up_button.click()
    assert editor.selected_ids() == (1, 2, 31, None, None, None)
    assert editor._active_slot() == 1
    assert window.main_state == MainState.NORMAL


def test_catalog_drop_inserts_and_assigned_drop_moves_without_duplicates(tmp_path: Path) -> None:
    window = _window(tmp_path, [1, 2, 3])
    editor = window.personality_editor

    editor.slot_tree.dropRequested.emit("catalog", 31, 1)
    assert editor.selected_ids() == (1, 31, 2, 3, None, None)
    assert "追加しました" in editor.operation_label.text()

    editor.slot_tree.dropRequested.emit("catalog", 2, 3)
    assert editor.selected_ids() == (1, 31, 3, 2, None, None)
    assert editor.selected_ids().count(2) == 1
    assert "移動しました" in editor.operation_label.text()
    assert window.validation_error is None


class _DropEventStub:
    def __init__(self, position: QPointF, keyword_id: int) -> None:
        self._position = position
        self._mime = _create_drag_mime("catalog", keyword_id)
        self.accepted = False

    def position(self) -> QPointF:
        return self._position

    def mimeData(self):  # noqa: N802
        return self._mime

    def acceptProposedAction(self) -> None:  # noqa: N802
        self.accepted = True

    def ignore(self) -> None:
        self.accepted = False


def test_drop_event_routes_catalog_payload_to_target_slot(tmp_path: Path) -> None:
    window = _window(tmp_path, [1, 2])
    editor = window.personality_editor
    window.edit_tabs.setCurrentIndex(1)
    window.show()
    _app().processEvents()
    target = editor.slot_tree.topLevelItem(1)
    position = QPointF(editor.slot_tree.visualItemRect(target).center())
    event = _DropEventStub(position, 31)

    editor.slot_tree.dropEvent(event)  # type: ignore[arg-type]

    assert event.accepted
    assert editor.selected_ids() == (1, 31, 2, None, None, None)
    window.hide()


def test_drag_uses_neutral_ignore_cursor_and_highlights_valid_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(tmp_path, [])
    editor = window.personality_editor
    _select_result(window, 1)
    recorded: dict[str, object] = {}

    class FakeDrag:
        def __init__(self, _source) -> None:
            pass

        def setMimeData(self, mime) -> None:  # noqa: N802
            recorded["mime"] = mime

        def setDragCursor(self, _pixmap, action) -> None:  # noqa: N802
            recorded["cursor_action"] = action

        def exec(self, action):
            recorded["exec_action"] = action
            assert editor.slot_panel.property("dragActive") is True
            assert not editor.drop_hint_label.isHidden()
            return Qt.DropAction.IgnoreAction

    monkeypatch.setattr(personality_editor_widget, "QDrag", FakeDrag)

    editor.result_tree.startDrag(Qt.DropAction.CopyAction)

    assert recorded["cursor_action"] == Qt.DropAction.IgnoreAction
    assert recorded["exec_action"] == Qt.DropAction.CopyAction
    assert editor.slot_panel.property("dragActive") is False
    assert not editor.drop_hint_label.isVisible()


def test_wrong_drop_location_shows_specific_error_message(tmp_path: Path) -> None:
    window = _window(tmp_path, [1])
    editor = window.personality_editor
    event = _DropEventStub(QPointF(), 31)

    editor.dropEvent(event)  # type: ignore[arg-type]

    assert event.accepted
    assert editor.selected_ids() == (1, None, None, None, None, None)
    assert editor.operation_label.property("state") == "error"
    assert "設定済みのキーワード" in editor.operation_label.text()
    assert "ドロップしてください" in editor.operation_label.text()


def test_drop_on_later_blank_appends_to_first_available_position(tmp_path: Path) -> None:
    window = _window(tmp_path, [1, 2])
    editor = window.personality_editor

    editor.slot_tree.dropRequested.emit("catalog", 31, 5)

    assert editor.selected_ids() == (1, 2, 31, None, None, None)
    assert editor._active_slot() == 2
    assert window.validation_error is None


def test_new_catalog_drop_is_rejected_when_all_six_slots_are_filled(tmp_path: Path) -> None:
    window = _window(tmp_path, [1, 2, 3, 4, 5, 6])
    editor = window.personality_editor
    before = editor.selected_ids()

    editor.slot_tree.dropRequested.emit("catalog", 31, 2)

    assert editor.selected_ids() == before
    assert "6枠すべてが設定済み" in editor.operation_label.text()
    assert editor.operation_label.property("state") == "error"
    assert window.main_state == MainState.NORMAL


def test_reordered_personalities_save_in_visible_slot_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(tmp_path, [1, 2, 31])
    editor = window.personality_editor
    editor.slot_tree.dropRequested.emit("slot", 2, 0)
    destination = tmp_path / "reordered.html"
    monkeypatch.setattr(window, "_choose_save_path", lambda: destination)

    assert window.save_as()
    saved = load_character_sheet(destination.read_bytes())

    assert [entry.keyword["id"] for entry in saved.personality_entries] == [31, 1, 2]
    assert editor.selected_ids() == (31, 1, 2, None, None, None)
    assert window.main_state == MainState.NORMAL
