from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from uuid import UUID

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QKeySequence

from saga_seeker_skill_editor.core.character_sheet import (
    CharacterSheetDraft,
    create_character_sheet,
    load_character_sheet,
    render_character_sheet,
)
from saga_seeker_skill_editor.core.phase0_candidate_sheet import GenerationInputs
from saga_seeker_skill_editor.gui.character_details_widget import (
    CharacterDetailsWidget,
)
from saga_seeker_skill_editor.gui.memory_editor_widget import MemoryEditorWidget
from saga_seeker_skill_editor.gui.status_editor_widget import StatusEditorWidget


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _generation() -> GenerationInputs:
    return GenerationInputs(
        uuid_factory=lambda: UUID("123e4567-e89b-42d3-a456-426614174000"),
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


def _blank_sheet():
    return load_character_sheet(
        create_character_sheet(icon_webp=b"synthetic-webp", generation=_generation())
    )


def test_basic_info_display_does_not_write_qt_newline_conversion_to_draft() -> None:
    _app()
    initial = _blank_sheet()
    initial_draft = CharacterSheetDraft.from_sheet(initial)
    initial_draft.set_profile("basicSettings", "LF\nCRLF\r\nCR\rEND")
    sheet = load_character_sheet(render_character_sheet(initial, initial_draft))
    draft = CharacterSheetDraft.from_sheet(sheet)
    widget = CharacterDetailsWidget()

    widget.set_sheet(sheet, draft)

    assert not draft.has_changes
    assert render_character_sheet(sheet, draft) is sheet.raw_html
    assert "15 / 1000" in widget.profile_counters["basicSettings"].text()


def test_basic_info_and_status_controls_update_only_explicit_fields() -> None:
    _app()
    sheet = _blank_sheet()
    draft = CharacterSheetDraft.from_sheet(sheet)
    details = CharacterDetailsWidget()
    statuses = StatusEditorWidget()
    details.set_sheet(sheet, draft)
    statuses.set_sheet(sheet, draft)

    details.name_edit.insert("識別名")
    details.profile_edits["appearance"].insertPlainText("外見")
    statuses.rank_boxes["strength"].setCurrentText("S")

    reloaded = load_character_sheet(render_character_sheet(sheet, draft))
    data = reloaded.data["data"]
    assert data["name"] == "識別名"
    assert data["profile"]["appearance"] == "外見"
    assert data["profile"]["basicSettings"] == ""
    assert data["status"]["strength"] == "S"
    assert data["status"]["charm"] == "E"


def test_profile_accordion_toggles_without_changing_the_draft() -> None:
    app = _app()
    initial = _blank_sheet()
    initial_draft = CharacterSheetDraft.from_sheet(initial)
    initial_draft.set_profile("appearance", "cursor")
    sheet = load_character_sheet(render_character_sheet(initial, initial_draft))
    draft = CharacterSheetDraft.from_sheet(sheet)
    details = CharacterDetailsWidget()
    details.set_sheet(sheet, draft)

    assert list(details.profile_toggles) == [
        "basicSettings",
        "appearance",
        "personality",
        "speechStyle",
        "background",
        "talentsAndRole",
        "otherFeatures",
    ]
    assert details.profile_toggles["basicSettings"].isChecked()
    assert not details.profile_bodies["basicSettings"].isHidden()
    assert details.profile_bodies["appearance"].isHidden()
    assert [
        toggle.text().removeprefix("▼ ").removeprefix("▶ ")
        for toggle in details.profile_toggles.values()
    ] == [
        "基本設定",
        "外見",
        "性格",
        "口調",
        "経歴",
        "特技と役割",
        "その他の特徴",
    ]
    assert details.content_splitter.orientation() == Qt.Orientation.Horizontal

    appearance = details.profile_edits["appearance"]
    cursor = appearance.textCursor()
    cursor.setPosition(3)
    appearance.setTextCursor(cursor)

    details.profile_toggles["appearance"].click()
    assert not details.profile_bodies["basicSettings"].isHidden()
    assert not details.profile_bodies["appearance"].isHidden()
    details.profile_toggles["basicSettings"].click()
    app.processEvents()

    assert not details.profile_bodies["appearance"].isHidden()
    assert details.profile_bodies["basicSettings"].isHidden()
    assert appearance.textCursor().position() == 3
    assert not draft.has_changes


def test_memory_widget_add_edit_move_and_placeholder_fill() -> None:
    _app()
    sheet = _blank_sheet()
    draft = CharacterSheetDraft.from_sheet(sheet)
    widget = MemoryEditorWidget(_generation)
    widget.set_sheet(sheet, draft)

    assert widget.move_up_shortcut.key().toString() == QKeySequence(
        "Alt+Up"
    ).toString()
    assert widget.move_down_shortcut.key().toString() == QKeySequence(
        "Alt+Down"
    ).toString()
    widget.add_normal_memory()
    widget.field_edits["title"].insert("新しい思い出")
    widget.fill_placeholders()

    assert len(draft.memory_order) == 15
    assert widget.add_button.isEnabled() is False
    reloaded = load_character_sheet(render_character_sheet(sheet, draft))
    assert reloaded.memory_entries[0].memory["title"] == "新しい思い出"
    assert all(entry.is_placeholder for entry in reloaded.memory_entries[1:])


def test_memory_display_counts_original_newline_code_points_without_editing() -> None:
    _app()
    initial = _blank_sheet()
    initial_draft = CharacterSheetDraft.from_sheet(initial)
    token = initial_draft.add_normal_memory(generation=_generation())
    initial_draft.set_memory_field(token, "summary", "LF\nCRLF\r\nCR\rEND")
    sheet = load_character_sheet(render_character_sheet(initial, initial_draft))
    draft = CharacterSheetDraft.from_sheet(sheet)
    widget = MemoryEditorWidget(_generation)

    widget.set_sheet(sheet, draft)

    assert widget.field_counters["summary"].text() == "15 / 1000"
    assert not draft.has_changes
