from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import os
from uuid import UUID

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QImage, QKeySequence

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
from saga_seeker_skill_editor.gui.vacant_slot_editor_widget import (
    VacantSlotEditorWidget,
)


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


def _png_icon(color: str = "#6b7280") -> bytes:
    image = QImage(2, 2, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    output = QByteArray()
    buffer = QBuffer(output)
    assert buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")
    buffer.close()
    return bytes(output)


def _sheet_with_icon(icon_bytes: bytes):
    return load_character_sheet(
        create_character_sheet(icon_webp=icon_bytes, generation=_generation())
    )


def _sheet_without_icon():
    raw = create_character_sheet(
        icon_webp=_png_icon(),
        generation=_generation(),
    )
    return load_character_sheet(
        raw.replace(
            b'"icon": {',
            b'"icon": null,\n    "removedIconFixture": {',
            1,
        )
    )


def _sheet_with_read_only_valid_icon():
    raw = create_character_sheet(
        icon_webp=_png_icon(),
        generation=_generation(),
    )
    return load_character_sheet(
        raw.replace(
            b"data:image/webp;base64,",
            b"data:image/png;base64,",
            1,
        )
    )


def _sheet_with_corrupt_base64():
    icon = _png_icon()
    raw = create_character_sheet(icon_webp=icon, generation=_generation())
    return load_character_sheet(
        raw.replace(base64.b64encode(icon), b"%%%")
    )


def _sheet_with_invalid_icon_uri():
    raw = create_character_sheet(
        icon_webp=_png_icon(),
        generation=_generation(),
    )
    return load_character_sheet(
        raw.replace(
            b"data:image/webp;base64,",
            b"invalid:image;base64,",
        )
    )


def _pipe_memory_sheet(*, matching: bool = True):
    initial = _blank_sheet()
    draft = CharacterSheetDraft.from_sheet(initial)
    token = draft.add_normal_memory(generation=_generation())
    draft.set_memory_field(token, "title", "Synthetic memory")
    draft.set_memory_tags(token, ["first", "second"])
    raw = render_character_sheet(initial, draft)
    pipe_value = b"first|second" if matching else b"first|different"
    raw = raw.replace(
        b'data-memory-tags="[&quot;first&quot;,&quot;second&quot;]"',
        b'data-memory-tags="' + pipe_value + b'"',
        1,
    )
    return load_character_sheet(raw)


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


def test_set_sheet_automatically_displays_embedded_icon_without_button_click() -> None:
    _app()
    sheet = _sheet_with_icon(_png_icon())
    draft = CharacterSheetDraft.from_sheet(sheet)
    widget = CharacterDetailsWidget()

    widget.set_sheet(sheet, draft)

    assert widget.preview_button.text() == "プレビューを再読込"
    assert widget.icon_preview.text() == ""
    assert not widget.icon_preview.pixmap().isNull()
    assert not draft.has_changes


def test_set_sheet_clears_previous_icon_before_showing_missing_icon_guidance() -> None:
    _app()
    first = _sheet_with_icon(_png_icon())
    second = _sheet_without_icon()
    widget = CharacterDetailsWidget()
    widget.set_sheet(first, CharacterSheetDraft.from_sheet(first))
    assert not widget.icon_preview.pixmap().isNull()

    widget.set_sheet(second, CharacterSheetDraft.from_sheet(second))

    assert widget.icon_preview.pixmap().isNull()
    assert widget.icon_preview.text() == "埋込画像はありません"


def test_corrupt_or_invalid_embedded_icon_does_not_raise_or_leave_a_pixmap() -> None:
    _app()
    sheets = (
        _sheet_with_corrupt_base64(),
        _sheet_with_icon(b"not an image"),
        _sheet_with_invalid_icon_uri(),
    )

    for sheet in sheets:
        widget = CharacterDetailsWidget()
        widget.set_sheet(sheet, CharacterSheetDraft.from_sheet(sheet))
        assert widget.icon_preview.pixmap().isNull()
        assert widget.icon_preview.text().startswith("プレビューできません\n")


def test_read_only_icon_section_still_automatically_displays_valid_icon() -> None:
    _app()
    sheet = _sheet_with_read_only_valid_icon()
    widget = CharacterDetailsWidget()

    widget.set_sheet(sheet, CharacterSheetDraft.from_sheet(sheet))

    assert not sheet.diagnostic_baseline.for_section("icon").editable
    assert not widget.replace_icon_button.isEnabled()
    assert widget.icon_preview.text() == ""
    assert not widget.icon_preview.pixmap().isNull()


def test_manual_icon_reload_reuses_safe_error_handling() -> None:
    _app()
    sheet = _sheet_with_icon(_png_icon())
    widget = CharacterDetailsWidget()
    widget.set_sheet(sheet, CharacterSheetDraft.from_sheet(sheet))
    sheet.data["data"]["icon"]["dataUri"] = "invalid:image;base64,%%%"

    widget.preview_button.click()

    assert widget.icon_preview.pixmap().isNull()
    assert widget.icon_preview.text().startswith("プレビューできません\n")


def test_replacement_icon_preview_remains_immediate() -> None:
    _app()
    sheet = _sheet_with_icon(_png_icon("#6b7280"))
    widget = CharacterDetailsWidget()
    widget.set_sheet(sheet, CharacterSheetDraft.from_sheet(sheet))
    original_key = widget.icon_preview.pixmap().cacheKey()

    widget.set_replacement_preview(_png_icon("#ef4444"))

    assert widget.icon_preview.text() == ""
    assert not widget.icon_preview.pixmap().isNull()
    assert widget.icon_preview.pixmap().cacheKey() != original_key


def test_corrupt_icon_does_not_block_load_or_disable_other_editors() -> None:
    _app()
    sheet = _sheet_with_icon(b"not an image")
    draft = CharacterSheetDraft.from_sheet(sheet)
    details = CharacterDetailsWidget()
    statuses = StatusEditorWidget()
    memories = MemoryEditorWidget(_generation)
    skill_section = sheet.diagnostic_baseline.for_section("skills")
    vacant_skill = VacantSlotEditorWidget(
        0,
        creation_enabled=skill_section.editable,
        read_only_reason=(
            None if skill_section.editable else skill_section.read_only_reason
        ),
    )

    details.set_sheet(sheet, draft)
    statuses.set_sheet(sheet, draft)
    memories.set_sheet(sheet, draft)

    assert details.icon_preview.text().startswith("プレビューできません\n")
    assert not details.name_edit.isReadOnly()
    assert all(not edit.isReadOnly() for edit in details.profile_edits.values())
    assert all(box.isEnabled() for box in statuses.rank_boxes.values())
    assert vacant_skill.name_edit.isEnabled()
    assert memories.add_button.isEnabled()


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

    assert widget.memory_list.count() == 0
    assert widget.add_button.isEnabled() is True
    assert widget.fill_button.isEnabled() is True
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


def test_game_pipe_memory_is_listed_with_enabled_edit_controls() -> None:
    _app()
    sheet = _pipe_memory_sheet()
    draft = CharacterSheetDraft.from_sheet(sheet)
    widget = MemoryEditorWidget(_generation)

    widget.set_sheet(sheet, draft)

    assert widget.memory_list.count() == 1
    assert widget.field_edits["title"].isEnabled() is True
    assert widget.add_tag_button.isEnabled() is True
    assert widget.message.text() == ""


def test_mismatched_pipe_memory_is_read_only_without_disabling_basic_info() -> None:
    _app()
    sheet = _pipe_memory_sheet(matching=False)
    draft = CharacterSheetDraft.from_sheet(sheet)
    memories = MemoryEditorWidget(_generation)
    details = CharacterDetailsWidget()

    memories.set_sheet(sheet, draft)
    details.set_sheet(sheet, draft)

    assert memories.message.text().startswith("読み取り専用:")
    assert memories.field_edits["title"].isEnabled() is False
    assert memories.add_button.isEnabled() is False
    assert details.name_edit.isEnabled() is True


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
