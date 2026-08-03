from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QMimeData, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QColor, QImage, QKeySequence  # noqa: E402
from PySide6.QtWidgets import QApplication, QAbstractItemView, QHeaderView  # noqa: E402

from saga_seeker_skill_editor.core.file_writer import SaveError  # noqa: E402
from saga_seeker_skill_editor.core.phase0_candidate_sheet import (  # noqa: E402
    GenerationInputs,
    build_full_probe_document,
    render_candidate_html,
)
from saga_seeker_skill_editor.core.personality_catalog import (  # noqa: E402
    load_personality_catalog,
)
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


def _webp_icon_bytes() -> bytes:
    image = QImage(2, 2, QImage.Format.Format_RGB32)
    image.fill(QColor("#6b7280"))
    output = QByteArray()
    buffer = QBuffer(output)
    assert buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "WEBP")
    buffer.close()
    return bytes(output)


def _editable_sheet_bytes() -> bytes:
    uuids = iter(
        UUID(f"{index}23e4567-e89b-42d3-a456-426614174000")
        for index in range(1, 7)
    )
    generation = GenerationInputs(
        uuid_factory=lambda: next(uuids),
        clock=lambda: datetime(
            2026,
            7,
            24,
            3,
            4,
            5,
            123456,
            tzinfo=timezone.utc,
        ),
        local_timezone=timezone(timedelta(hours=9)),
    )
    return render_candidate_html(
        build_full_probe_document(
            icon_webp=_webp_icon_bytes(),
            generation=generation,
            default_skill={
                "id": "default-skill",
                "name": "Synthetic protected skill",
                "description": "Synthetic protected description",
                "type": "physical",
                "key": "synthetic-default",
            },
            personality_keyword=load_personality_catalog()[0].as_dict(),
        )
    )


def _editable_window(tmp_path: Path) -> tuple[MainWindow, Path]:
    _app()
    path = tmp_path / "editable.html"
    path.write_bytes(_editable_sheet_bytes())
    window = MainWindow()
    assert window.load_path(path)
    return window, path


class FakeCloseEvent:
    def __init__(self) -> None:
        self.accepted = False
        self.ignored = False

    def accept(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.ignored = True


class FakeDropEvent:
    def __init__(self, path: Path) -> None:
        self._mime = QMimeData()
        self._mime.setUrls([QUrl.fromLocalFile(str(path))])

    def mimeData(self) -> QMimeData:  # noqa: N802
        return self._mime


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


def test_invalid_html_keeps_unloaded_state_and_reports_transient_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    invalid = tmp_path / "scenario.html"
    invalid.write_bytes(b"<html><body>not a character sheet</body></html>")
    window = MainWindow()
    presented_errors = []
    monkeypatch.setattr(window, "_present_error_dialog", presented_errors.append)

    assert not window.load_path(invalid)

    assert window.current_path is None
    assert window.sheet is None
    assert window.character_draft is None
    assert window.active_error is None
    assert window.main_state == MainState.UNLOADED
    assert not window.save_button.isEnabled()
    assert len(presented_errors) == 1


def test_invalid_html_keeps_normal_editable_session_and_selection_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, current_path = _editable_window(tmp_path)
    invalid = tmp_path / "scenario.html"
    invalid.write_bytes(b"<html><body>not a character sheet</body></html>")
    window.edit_tabs.setCurrentIndex(window.memory_tab_index)
    window.skill_list.setCurrentItem(window.skill_list.topLevelItem(1))
    window.memory_editor.memory_list.setCurrentRow(2)
    window.personality_editor.slot_tree.setCurrentItem(
        window.personality_editor.slot_tree.topLevelItem(0)
    )
    original_sheet = window.sheet
    original_draft = window.character_draft
    original_widgets = list(window.skill_widgets)
    presented_errors = []
    monkeypatch.setattr(window, "_present_error_dialog", presented_errors.append)

    assert not window.load_path(invalid)

    assert len(presented_errors) == 1
    assert window.current_path == current_path
    assert window.sheet is original_sheet
    assert window.character_draft is original_draft
    assert window.skill_widgets == original_widgets
    assert window.changed_indices == set()
    assert window.personality_changed_indices == set()
    assert window.validation_error is None
    assert window.active_error is None
    assert window.main_state == MainState.NORMAL
    assert window.edit_tabs.currentIndex() == window.memory_tab_index
    assert window.skill_list.selected_skill_index() == 1
    assert window.memory_editor.memory_list.currentRow() == 2
    assert (
        window.personality_editor.slot_tree.currentItem()
        is window.personality_editor.slot_tree.topLevelItem(0)
    )

    details = window.character_details_editor
    assert not details.name_edit.isReadOnly()
    assert all(not edit.isReadOnly() for edit in details.profile_edits.values())
    assert all(box.isEnabled() for box in window.status_editor.rank_boxes.values())
    assert window.skill_widgets[1].name_edit.isEnabled()
    assert window.skill_widgets[1].description_edit.isEnabled()
    assert window.personality_editor.search_edit.isEnabled()
    assert window.personality_editor.result_tree.isEnabled()
    assert window.memory_editor.field_edits["title"].isEnabled()
    assert window.memory_editor.add_button.isEnabled()
    assert details.replace_icon_button.isEnabled()
    assert window.save_button.isEnabled()
    assert not window.reset_button.isEnabled()


def test_invalid_html_keeps_dirty_session_without_unsaved_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, current_path = _loaded_window(tmp_path)
    _make_dirty(window, "Unsaved value must remain")
    invalid = tmp_path / "scenario.html"
    invalid.write_bytes(b"<html><body>not a character sheet</body></html>")
    original_sheet = window.sheet
    original_draft = window.character_draft
    original_widgets = list(window.skill_widgets)
    original_tab = window.edit_tabs.currentIndex()
    original_selection = window.skill_list.selected_skill_index()
    prompt_calls = 0
    presented_errors = []

    def choose_cancel() -> LeaveChoice:
        nonlocal prompt_calls
        prompt_calls += 1
        return LeaveChoice.CANCEL

    monkeypatch.setattr(window, "_ask_unsaved_action", choose_cancel)
    monkeypatch.setattr(window, "_present_error_dialog", presented_errors.append)

    assert not window.load_path(invalid)

    assert prompt_calls == 0
    assert len(presented_errors) == 1
    assert window.current_path == current_path
    assert window.sheet is original_sheet
    assert window.character_draft is original_draft
    assert window.skill_widgets == original_widgets
    assert window.skill_widgets[0].name_edit.text() == "Unsaved value must remain"
    assert window.changed_indices == {0}
    assert window._change_count() == 1
    assert window.edit_tabs.currentIndex() == original_tab
    assert window.skill_list.selected_skill_index() == original_selection
    assert window.active_error is None
    assert window.validation_error is None
    assert window.main_state == MainState.DIRTY
    assert window.save_button.isEnabled()


def test_invalid_html_keeps_all_unsaved_inputs_and_change_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, current_path = _editable_window(tmp_path)
    details = window.character_details_editor
    details.name_edit.insert(" edited")
    details.profile_edits["background"].insertPlainText(" edited profile")
    window.status_editor.rank_boxes["luck"].setCurrentText("A")
    window.skill_widgets[1].name_edit.setText("Edited original skill")
    added_keyword_id = window.personality_catalog[1].id
    window.personality_editor.slot_tree.dropRequested.emit(
        "catalog", added_keyword_id, 1
    )
    window.memory_editor.memory_list.setCurrentRow(0)
    window.memory_editor.field_edits["title"].insert(" edited memory")
    window.edit_tabs.setCurrentIndex(window.memory_tab_index)
    window.skill_list.setCurrentItem(window.skill_list.topLevelItem(1))
    window.memory_editor.memory_list.setCurrentRow(2)
    invalid = tmp_path / "scenario.html"
    invalid.write_bytes(b"<html><body>not a character sheet</body></html>")
    original_sheet = window.sheet
    original_draft = window.character_draft
    original_widgets = list(window.skill_widgets)
    original_name = details.name_edit.text()
    original_profile = details.profile_edits["background"].toPlainText()
    original_status = window.status_editor.rank_boxes["luck"].currentText()
    original_skill_name = window.skill_widgets[1].name_edit.text()
    original_personalities = window.personality_editor.selected_ids()
    original_memory_title = original_draft.memory_value(0)["title"]
    original_changed_indices = set(window.changed_indices)
    original_personality_changes = set(window.personality_changed_indices)
    original_change_count = window._change_count()
    prompt_calls = 0
    presented_errors = []

    def choose_cancel() -> LeaveChoice:
        nonlocal prompt_calls
        prompt_calls += 1
        return LeaveChoice.CANCEL

    monkeypatch.setattr(window, "_ask_unsaved_action", choose_cancel)
    monkeypatch.setattr(window, "_present_error_dialog", presented_errors.append)

    assert not window.load_path(invalid)

    assert prompt_calls == 0
    assert len(presented_errors) == 1
    assert window.current_path == current_path
    assert window.sheet is original_sheet
    assert window.character_draft is original_draft
    assert window.skill_widgets == original_widgets
    assert details.name_edit.text() == original_name
    assert details.profile_edits["background"].toPlainText() == original_profile
    assert window.status_editor.rank_boxes["luck"].currentText() == original_status
    assert window.skill_widgets[1].name_edit.text() == original_skill_name
    assert window.personality_editor.selected_ids() == original_personalities
    assert window.character_draft.memory_value(0)["title"] == original_memory_title
    assert window.changed_indices == original_changed_indices == {1}
    assert window.personality_changed_indices == original_personality_changes == {1}
    assert window._change_count() == original_change_count == 3
    assert window.validation_error is None
    assert window.active_error is None
    assert window.edit_tabs.currentIndex() == window.memory_tab_index
    assert window.skill_list.selected_skill_index() == 1
    assert window.memory_editor.memory_list.currentRow() == 2
    assert window.main_state == MainState.DIRTY
    assert window.save_button.isEnabled()
    assert window.reset_button.isEnabled()
    assert details.replace_icon_button.isEnabled()


def test_file_read_failure_keeps_current_normal_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, current_path = _loaded_window(tmp_path)
    missing = tmp_path / "missing.html"
    original_sheet = window.sheet
    original_draft = window.character_draft
    presented_errors = []
    monkeypatch.setattr(window, "_present_error_dialog", presented_errors.append)

    assert not window.load_path(missing)

    assert len(presented_errors) == 1
    assert window.current_path == current_path
    assert window.sheet is original_sheet
    assert window.character_draft is original_draft
    assert window.active_error is None
    assert window.main_state == MainState.NORMAL
    assert window.save_button.isEnabled()


def test_valid_candidate_prompts_only_after_it_parses_successfully(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, current_path = _loaded_window(tmp_path)
    _make_dirty(window, "Unsaved value must remain")
    candidate = tmp_path / "candidate.html"
    candidate.write_bytes(_sheet_bytes(character="Candidate"))
    original_sheet = window.sheet
    prompt_calls = 0

    def choose_cancel() -> LeaveChoice:
        nonlocal prompt_calls
        prompt_calls += 1
        return LeaveChoice.CANCEL

    monkeypatch.setattr(window, "_ask_unsaved_action", choose_cancel)

    assert not window.load_path(candidate)

    assert prompt_calls == 1
    assert window.current_path == current_path
    assert window.sheet is original_sheet
    assert window.skill_widgets[0].name_edit.text() == "Unsaved value must remain"
    assert window.main_state == MainState.DIRTY


def test_invalid_html_drop_keeps_dirty_session_without_unsaved_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, current_path = _loaded_window(tmp_path)
    _make_dirty(window, "Dropped invalid candidate must not replace this")
    invalid = tmp_path / "scenario.html"
    invalid.write_bytes(b"<html><body>not a character sheet</body></html>")
    original_sheet = window.sheet
    original_draft = window.character_draft
    prompt_calls = 0
    presented_errors = []

    def choose_cancel() -> LeaveChoice:
        nonlocal prompt_calls
        prompt_calls += 1
        return LeaveChoice.CANCEL

    monkeypatch.setattr(window, "_ask_unsaved_action", choose_cancel)
    monkeypatch.setattr(window, "_present_error_dialog", presented_errors.append)

    window.dropEvent(FakeDropEvent(invalid))  # type: ignore[arg-type]

    assert prompt_calls == 0
    assert len(presented_errors) == 1
    assert window.current_path == current_path
    assert window.sheet is original_sheet
    assert window.character_draft is original_draft
    assert window.skill_widgets[0].name_edit.text() == (
        "Dropped invalid candidate must not replace this"
    )
    assert window.changed_indices == {0}
    assert window.main_state == MainState.DIRTY
    assert window.save_button.isEnabled()


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
    assert window.save_button.isEnabled()
    assert "元のバイトを変更せず" in window.save_button.toolTip()
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
    assert window.save_button.isEnabled()


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
    assert window.save_button.isEnabled()
    assert "元のバイトを変更せず" in window.save_button.toolTip()


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
