from __future__ import annotations

import json

import pytest

from saga_seeker_skill_editor.core.character_sheet import load_character_sheet
from saga_seeker_skill_editor.core.json_span import locate_personalities_array
from saga_seeker_skill_editor.core.personality_catalog import load_personality_catalog
from saga_seeker_skill_editor.core.personality_editor import (
    render_personality_assignment,
    render_personality_selections,
    render_personality_tail_removal,
)
from saga_seeker_skill_editor.core.sheet_editor import SheetEditError


def personality_sheet(personalities: list[dict[str, object]], *, newline: str = "\n") -> bytes:
    data = {
        "formatVersion": "1.0.0",
        "data": {
            "name": "Personality Test",
            "skills": [],
            "personalities": personalities,
        },
    }
    names = [str(item["name"]) for item in personalities] + [""] * (6 - len(personalities))
    lis = newline.join(f"  <li>{name if name else '&nbsp;'}</li>" for name in names)
    script = json.dumps(data, ensure_ascii=False, indent=2).replace("\n", newline)
    return (
        f'<ul id="skills-value"></ul>{newline}'
        f'<ul id="personality-value">{newline}{lis}{newline}</ul>{newline}'
        f'<script id="character-sheet-data" type="application/json">{script}</script>'
    ).encode("utf-8")


def test_catalog_registers_all_four_fields_for_150_unique_keywords() -> None:
    catalog = load_personality_catalog()

    assert len(catalog) == 150
    assert len({keyword.id for keyword in catalog}) == 150
    assert len({keyword.name for keyword in catalog}) == 150
    assert catalog[0].as_dict() == {"id": 1, "name": "勇敢", "type": "力", "karma": "美徳"}
    assert catalog[-1].as_dict() == {
        "id": 150,
        "name": "無責任",
        "type": "法",
        "karma": "悪徳",
    }


def test_personality_position_mapping_supports_trailing_empty_slots() -> None:
    catalog = load_personality_catalog()
    raw = personality_sheet([catalog[0].as_dict(), catalog[31].as_dict()])

    sheet = load_character_sheet(raw)

    assert sheet.personality_read_only is False
    assert sheet.personality_slot_count == 6
    assert [entry.keyword for entry in sheet.personality_entries] == [
        catalog[0].as_dict(),
        catalog[31].as_dict(),
    ]


def test_assignment_replaces_only_target_object_and_li() -> None:
    catalog = load_personality_catalog()
    raw = personality_sheet([catalog[0].as_dict(), catalog[1].as_dict()])
    original_sheet = load_character_sheet(raw)
    original_json = raw[original_sheet.script_span.content_start : original_sheet.script_span.content_end]
    original_span = locate_personalities_array(original_json).objects[0]
    untouched_object = original_json[original_span.start : original_span.end]
    untouched_li = b"<li>\xe5\x8b\x87\xe6\x95\xa2</li>"

    updated = render_personality_assignment(
        original_sheet,
        index=1,
        keyword=catalog[30],
    )
    rendered = load_character_sheet(updated)

    assert rendered.personality_entries[0].keyword == catalog[0].as_dict()
    assert rendered.personality_entries[1].keyword == catalog[30].as_dict()
    assert untouched_object in updated
    assert untouched_li in updated


def test_assignment_appends_to_first_available_slot_and_preserves_crlf() -> None:
    catalog = load_personality_catalog()
    raw = personality_sheet([catalog[0].as_dict()], newline="\r\n")

    updated = render_personality_assignment(
        load_character_sheet(raw),
        index=1,
        keyword=catalog[90],
    )
    rendered = load_character_sheet(updated)

    assert len(rendered.personality_entries) == 2
    assert rendered.personality_entries[1].keyword == catalog[90].as_dict()
    assert b"\r\n" in updated[rendered.script_span.content_start : rendered.script_span.content_end]


def test_assignment_rejects_gap_and_duplicate() -> None:
    catalog = load_personality_catalog()
    sheet = load_character_sheet(personality_sheet([catalog[0].as_dict()]))

    with pytest.raises(SheetEditError):
        render_personality_assignment(sheet, index=2, keyword=catalog[1])
    with pytest.raises(SheetEditError):
        render_personality_assignment(sheet, index=1, keyword=catalog[0])


def test_tail_removal_preserves_earlier_keyword_and_empties_html_slot() -> None:
    catalog = load_personality_catalog()
    raw = personality_sheet([catalog[0].as_dict(), catalog[1].as_dict()])

    updated = render_personality_tail_removal(load_character_sheet(raw), index=1)
    rendered = load_character_sheet(updated)

    assert [entry.keyword for entry in rendered.personality_entries] == [catalog[0].as_dict()]
    assert rendered.personality_lis[1].inner == b"&nbsp;"


def test_non_tail_removal_is_rejected() -> None:
    catalog = load_personality_catalog()
    sheet = load_character_sheet(personality_sheet([catalog[0].as_dict(), catalog[1].as_dict()]))

    with pytest.raises(SheetEditError):
        render_personality_tail_removal(sheet, index=0)


def test_catalog_or_html_mismatch_makes_only_personality_section_read_only() -> None:
    catalog = load_personality_catalog()
    invalid = catalog[0].as_dict() | {"karma": "不明"}
    sheet = load_character_sheet(personality_sheet([invalid]))

    assert sheet.read_only is False
    assert sheet.personality_read_only is True
    assert "catalog" in sheet.personality_read_only_reason


def test_batch_selection_supports_swapping_existing_keywords() -> None:
    catalog = load_personality_catalog()
    sheet = load_character_sheet(personality_sheet([catalog[0].as_dict(), catalog[1].as_dict()]))

    updated = render_personality_selections(
        sheet,
        keyword_ids=(2, 1, None, None, None, None),
        catalog=catalog,
    )
    rendered = load_character_sheet(updated)

    assert [entry.keyword["id"] for entry in rendered.personality_entries] == [2, 1]


def test_batch_selection_adds_and_removes_multiple_trailing_keywords() -> None:
    catalog = load_personality_catalog()
    empty = load_character_sheet(personality_sheet([]))

    added = render_personality_selections(
        empty,
        keyword_ids=(1, 32, 67, None, None, None),
        catalog=catalog,
    )
    added_sheet = load_character_sheet(added)
    assert [entry.keyword["id"] for entry in added_sheet.personality_entries] == [1, 32, 67]

    removed = render_personality_selections(
        added_sheet,
        keyword_ids=(1, None, None, None, None, None),
        catalog=catalog,
    )
    removed_sheet = load_character_sheet(removed)
    assert [entry.keyword["id"] for entry in removed_sheet.personality_entries] == [1]
    assert [li.inner for li in removed_sheet.personality_lis[1:3]] == [b"&nbsp;", b"&nbsp;"]
