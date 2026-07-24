from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from saga_seeker_skill_editor.gui.main_window import MainWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_profile_comparison_edits_the_shared_character_draft() -> None:
    _app()
    window = MainWindow()
    assert window.create_new_sheet()
    editor = window.character_details_editor

    assert editor.left_profile_selector.currentData() == "basicSettings"
    assert editor.right_profile_selector.currentData() == "personality"
    assert editor.comparison_host.isHidden()

    editor.show_profile_comparison()
    editor.left_comparison_edit.setPlainText("同時参照しながら編集")

    assert editor.profile_edits["basicSettings"].toPlainText() == (
        "同時参照しながら編集"
    )
    assert window.character_draft is not None
    assert window.character_draft.has_changes
    assert window.unsaved_changes


def test_profile_comparison_is_shown_only_when_requested() -> None:
    _app()
    window = MainWindow()
    assert window.create_new_sheet()
    editor = window.character_details_editor

    assert editor.comparison_host.isHidden()
    assert editor.show_comparison_button.isEnabled()

    editor.show_comparison_button.click()

    assert not editor.comparison_host.isHidden()
    assert not editor.show_comparison_button.isEnabled()
    assert not window.unsaved_changes

    editor.hide_profile_comparison()

    assert editor.comparison_host.isHidden()
    assert editor.show_comparison_button.isEnabled()
    assert not window.unsaved_changes


def test_profile_comparison_uses_three_resizable_panes() -> None:
    _app()
    window = MainWindow()
    assert window.create_new_sheet()
    editor = window.character_details_editor

    assert editor.comparison_splitter.orientation() == Qt.Orientation.Horizontal
    assert editor.comparison_splitter.count() == 3
    assert all(
        editor.comparison_splitter.isCollapsible(index) is False
        for index in range(editor.comparison_splitter.count())
    )


def test_profile_comparison_shows_live_personality_keyword_reference() -> None:
    _app()
    window = MainWindow()
    assert window.create_new_sheet()
    editor = window.character_details_editor

    editor.set_personality_keywords(["勇敢", "論理的"])

    assert "勇敢" in editor.personality_reference.text()
    assert "論理的" in editor.personality_reference.text()


def test_detached_profile_comparison_returns_to_main_editor_on_close() -> None:
    app = _app()
    window = MainWindow()
    assert window.create_new_sheet()
    editor = window.character_details_editor

    editor.open_profile_comparison()
    app.processEvents()

    assert editor.comparison_window is not None
    assert editor.comparison_panel.window() is editor.comparison_window

    editor.comparison_window.close()
    app.processEvents()

    assert editor.comparison_panel.parentWidget() is editor.comparison_host
    assert editor.comparison_host.isHidden()
    assert editor.show_comparison_button.isEnabled()
