from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QKeySequence  # noqa: E402
from PySide6.QtWidgets import QApplication, QAbstractItemView, QHeaderView  # noqa: E402

from saga_seeker_skill_editor.core.file_writer import SaveError  # noqa: E402
from saga_seeker_skill_editor.gui.main_window import LeaveChoice, MainState, MainWindow  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _sheet_bytes(*, character: str, skill_name: str = "Original") -> bytes:
    skill = {
        "id": "skill_unique",
        "name": skill_name,
        "description": f"Description for {skill_name}",
        "type": "",
        "key": "",
    }
    data = {
        "formatVersion": "1.0.0",
        "exportedAt": "2026-07-20T00:00:00Z",
        "data": {
            "name": character,
            "profile": {},
            "status": {},
            "skills": [skill],
            "personalities": [],
            "memories": [],
            "icon": {},
        },
    }
    li = (
        f'<li data-skill-id="skill_unique" data-skill-name="{skill_name}" '
        f'data-skill-type="" data-skill-description="Description for {skill_name}">{skill_name}</li>'
    )
    return (
        f'<ul id="skills-value">{li}</ul>'
        f'<script id="character-sheet-data" type="application/json">{json.dumps(data, ensure_ascii=False)}</script>'
    ).encode("utf-8")


class FakeCloseEvent:
    def __init__(self) -> None:
        self.accepted = False
        self.ignored = False

    def accept(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.ignored = True


def _loaded_window(tmp_path: Path) -> tuple[MainWindow, Path]:
    _app()
    path = tmp_path / "first.html"
    path.write_bytes(_sheet_bytes(character="First"))
    window = MainWindow()
    assert window.load_path(path)
    return window, path


def _make_dirty(window: MainWindow, value: str = "Changed") -> None:
    window.skill_widgets[0].name_edit.setText(value)
    assert window.main_state == MainState.DIRTY


def test_initial_and_comparison_based_change_states(tmp_path: Path) -> None:
    _app()
    window = MainWindow()
    assert window.main_state == MainState.UNLOADED
    assert not window.save_button.isEnabled()

    path = tmp_path / "sheet.html"
    path.write_bytes(_sheet_bytes(character="State Test"))
    assert window.load_path(path)
    assert window.main_state == MainState.NORMAL
    assert window.changed_indices == set()

    editor = window.skill_widgets[0]
    editor.name_edit.setText("Changed")
    assert window.main_state == MainState.DIRTY
    assert window.changed_indices == {0}
    assert window.save_button.isEnabled()
    assert window.skill_list.topLevelItem(0).text(window.skill_list.CHANGE_COLUMN) == "変更あり"

    editor.name_edit.setText("Original")
    assert window.main_state == MainState.NORMAL
    assert window.changed_indices == set()
    assert not window.save_button.isEnabled()
    assert window.skill_list.topLevelItem(0).text(window.skill_list.CHANGE_COLUMN) == "変更なし"


def test_skill_list_is_read_only_single_selection_with_responsive_columns(tmp_path: Path) -> None:
    window, _ = _loaded_window(tmp_path)
    header = window.skill_list.header()
    assert window.skill_list.selectionMode() == QAbstractItemView.SelectionMode.SingleSelection
    assert window.skill_list.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    assert window.skill_list.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert header.sectionResizeMode(window.skill_list.SLOT_COLUMN) == QHeaderView.ResizeMode.Fixed
    assert header.sectionResizeMode(window.skill_list.NAME_COLUMN) == QHeaderView.ResizeMode.Stretch
    assert header.sectionResizeMode(window.skill_list.KIND_COLUMN) == QHeaderView.ResizeMode.ResizeToContents
    assert header.sectionResizeMode(window.skill_list.PROTECTION_COLUMN) == QHeaderView.ResizeMode.ResizeToContents
    assert header.sectionResizeMode(window.skill_list.CHANGE_COLUMN) == QHeaderView.ResizeMode.ResizeToContents
    assert window.skill_list.topLevelItem(0).toolTip(window.skill_list.NAME_COLUMN) == "Original"


def test_standard_shortcuts_and_ctrl_w_use_close_confirmation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    window, _ = _loaded_window(tmp_path)
    _make_dirty(window)
    assert window.open_action.shortcut().toString() == QKeySequence(QKeySequence.StandardKey.Open).toString()
    assert window.save_action.shortcut().toString() == QKeySequence(QKeySequence.StandardKey.SaveAs).toString()
    assert window.close_action.shortcut().toString() == QKeySequence(QKeySequence.StandardKey.Close).toString()

    monkeypatch.setattr(window, "_ask_unsaved_action", lambda: LeaveChoice.CANCEL)
    window.show()
    _app().processEvents()
    window.close_action.trigger()
    _app().processEvents()
    assert window.isVisible()
    assert window.skill_widgets[0].name_edit.text() == "Changed"
    window.hide()


def test_close_with_changes_prompts_and_cancel_preserves_editor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    window, _ = _loaded_window(tmp_path)
    _make_dirty(window)
    calls = 0

    def choose_cancel() -> LeaveChoice:
        nonlocal calls
        calls += 1
        return LeaveChoice.CANCEL

    monkeypatch.setattr(window, "_ask_unsaved_action", choose_cancel)
    event = FakeCloseEvent()
    window.closeEvent(event)  # type: ignore[arg-type]

    assert calls == 1
    assert event.ignored
    assert not event.accepted
    assert window.skill_widgets[0].name_edit.text() == "Changed"
    assert window.main_state == MainState.DIRTY


def test_close_with_discard_continues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    window, _ = _loaded_window(tmp_path)
    _make_dirty(window)
    monkeypatch.setattr(window, "_ask_unsaved_action", lambda: LeaveChoice.DISCARD)
    event = FakeCloseEvent()
    window.closeEvent(event)  # type: ignore[arg-type]
    assert event.accepted
    assert not event.ignored


def test_discard_then_open_another_file_continues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    window, _ = _loaded_window(tmp_path)
    _make_dirty(window)
    second = tmp_path / "second.html"
    second.write_bytes(_sheet_bytes(character="Second", skill_name="Second Skill"))
    monkeypatch.setattr(window, "_ask_unsaved_action", lambda: LeaveChoice.DISCARD)

    assert window.load_path(second)
    assert window.sheet is not None
    assert window.sheet.character_name == "Second"
    assert window.skill_widgets[0].name_edit.text() == "Second Skill"
    assert window.main_state == MainState.NORMAL


def test_save_success_then_open_another_file_continues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    window, _ = _loaded_window(tmp_path)
    _make_dirty(window, "Saved Change")
    saved = tmp_path / "saved.html"
    second = tmp_path / "second.html"
    second.write_bytes(_sheet_bytes(character="Second"))
    monkeypatch.setattr(window, "_ask_unsaved_action", lambda: LeaveChoice.SAVE_AS)
    monkeypatch.setattr(window, "_choose_save_path", lambda: saved)

    assert window.load_path(second)
    assert saved.exists()
    assert window.sheet is not None
    assert window.sheet.character_name == "Second"
    assert window.main_state == MainState.NORMAL


def test_save_success_establishes_new_comparison_baseline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    window, _ = _loaded_window(tmp_path)
    _make_dirty(window, "New Baseline")
    destination = tmp_path / "saved.html"
    monkeypatch.setattr(window, "_choose_save_path", lambda: destination)

    assert window.save_as()
    assert window.current_path == destination
    assert window.skill_widgets[0].name_edit.text() == "New Baseline"
    assert window.changed_indices == set()
    assert window.main_state == MainState.NORMAL


def test_vacant_slot_addition_saves_atomically_and_becomes_new_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    source = tmp_path / "vacant-source.html"
    source.write_bytes(
        _sheet_bytes(character="Vacant Save").replace(b"</ul>", b"<li>&nbsp;</li></ul>")
    )
    destination = tmp_path / "vacant-saved.html"
    window = MainWindow()
    assert window.load_path(source)
    window.skill_widgets[1].name_edit.setText("Added")
    window.skill_widgets[1].description_edit.setPlainText("Created in the first vacant slot")
    monkeypatch.setattr(window, "_choose_save_path", lambda: destination)

    assert window.save_as()

    assert destination.exists()
    assert window.sheet is not None
    assert len(window.sheet.entries) == 2
    assert window.sheet.entries[1].skill["name"] == "Added"
    assert window.changed_indices == set()
    assert window.main_state == MainState.NORMAL
    assert not window.save_button.isEnabled()


def test_structure_mismatch_is_normal_with_read_only_badge(tmp_path: Path) -> None:
    _app()
    data = json.loads(
        _sheet_bytes(character="Read Only").decode("utf-8").split(
            '<script id="character-sheet-data" type="application/json">', 1
        )[1].split("</script>", 1)[0]
    )
    path = tmp_path / "mismatch.html"
    path.write_bytes(
        (
            '<ul id="skills-value"></ul>'
            f'<script id="character-sheet-data" type="application/json">{json.dumps(data, ensure_ascii=False)}</script>'
        ).encode("utf-8")
    )
    window = MainWindow()
    assert window.load_path(path)
    assert window.sheet is not None and window.sheet.read_only
    assert window.main_state == MainState.NORMAL
    assert not window.read_only_badge.isHidden()
    assert not window.save_button.isEnabled()
    assert "読み取り専用" in window.save_button.toolTip()


def test_save_failure_stops_navigation_and_preserves_editor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, first = _loaded_window(tmp_path)
    _make_dirty(window, "Unsaved After Failure")
    second = tmp_path / "second.html"
    second.write_bytes(_sheet_bytes(character="Second"))
    monkeypatch.setattr(window, "_ask_unsaved_action", lambda: LeaveChoice.SAVE_AS)
    monkeypatch.setattr(window, "_choose_save_path", lambda: tmp_path / "unwritable" / "saved.html")
    monkeypatch.setattr(window, "_present_error_dialog", lambda _error: None)

    def fail_save(*_args, **_kwargs) -> None:
        raise SaveError("permission denied")

    monkeypatch.setattr("saga_seeker_skill_editor.gui.main_window.atomic_save_bytes", fail_save)

    assert not window.load_path(second)
    assert window.current_path == first
    assert window.skill_widgets[0].name_edit.text() == "Unsaved After Failure"
    assert window.changed_indices == {0}
    assert window.main_state == MainState.ERROR
    assert window.save_button.isEnabled()
    assert "別の保存先" in window.status_detail_label.text()
