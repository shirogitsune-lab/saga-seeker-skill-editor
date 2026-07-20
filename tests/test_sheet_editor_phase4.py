from __future__ import annotations

import json

import pytest

from saga_seeker_skill_editor.core.character_sheet import load_character_sheet
from saga_seeker_skill_editor.core.sheet_editor import (
    SheetEditError,
    render_empty_slot_creation,
    render_name_description_edit,
    render_protected_skill_replacement,
    render_skill_deletion,
    render_vacant_slot_creation,
)


def sheet_bytes(skills: list[dict[str, object]], li_html: str) -> bytes:
    data = {
        "formatVersion": "1.0.0",
        "exportedAt": "2026-07-20T00:00:00Z",
        "data": {
            "name": "Synthetic",
            "profile": {"mustStay": "profile"},
            "status": {},
            "skills": skills,
            "personalities": [],
            "memories": [],
            "icon": {"base64": "BASE64_MUST_STAY"},
        },
    }
    json_text = json.dumps(data, ensure_ascii=False, indent=2)
    html = f"""<!doctype html>
<html>
<body>
<div id="profile">must stay</div>
<ul id="skills-value" class="item-list grid">
{li_html}
</ul>
<script id="character-sheet-data" type="application/json">{json_text}</script>
</body>
</html>"""
    return html.encode("utf-8")


def skill_li(skill: dict[str, object]) -> str:
    return (
        f'<li data-skill-id="{skill.get("id", "")}" '
        f'data-skill-name="{skill.get("name", "")}" '
        f'data-skill-type="{skill.get("type", "")}" '
        f'data-skill-description="{skill.get("description", "")}">'
        f'{skill.get("name", "")}</li>'
    )


def test_render_name_description_edit_changes_only_target_original_skill() -> None:
    original = {
        "id": "skill_no01_2025-12-30-05-02",
        "name": "Old",
        "description": "Old desc",
        "type": "",
        "key": "",
        "unknown": {"must": "stay"},
    }
    default = {
        "id": "42",
        "name": "Default",
        "description": "Protected",
        "type": "精神",
        "key": "Default_Key",
    }
    default_li = skill_li(default)
    raw = sheet_bytes([original, default], skill_li(original) + "\n" + default_li)
    sheet = load_character_sheet(raw)

    updated = render_name_description_edit(
        sheet,
        index=0,
        name="New",
        description="New desc",
    )
    rendered = load_character_sheet(updated)

    assert rendered.entries[0].skill["id"] == "skill_no01_2025-12-30-05-02"
    assert rendered.entries[0].skill["unknown"] == {"must": "stay"}
    assert rendered.entries[0].skill["name"] == "New"
    assert rendered.entries[0].skill["description"] == "New desc"
    assert rendered.entries[1].skill == default
    assert default_li.encode("utf-8") in updated
    assert b"BASE64_MUST_STAY" in updated
    assert b'<div id="profile">must stay</div>' in updated


def test_render_name_description_edit_roundtrips_special_characters() -> None:
    original = {
        "id": "jp-symbol-id",
        "name": "Old",
        "description": "Old desc",
        "type": "",
        "key": "",
    }
    raw = sheet_bytes([original], skill_li(original))
    sheet = load_character_sheet(raw)
    name = 'Name "double" \'single\' & <tag>\n\t\\ 日本語 😀'
    description = 'Desc </script> "double" \'single\' & <tag>\n\t\\ 日本語 😀'

    updated = render_name_description_edit(
        sheet,
        index=0,
        name=name,
        description=description,
    )
    rendered = load_character_sheet(updated)

    assert b"</script>" not in updated[rendered.script_span.content_start : rendered.script_span.content_end].lower()
    assert rendered.entries[0].skill["name"] == name
    assert rendered.entries[0].skill["description"] == description
    assert rendered.entries[0].li.attrs["data-skill-name"] == name
    assert rendered.entries[0].li.attrs["data-skill-description"] == description


def test_render_name_description_edit_rejects_default_skill() -> None:
    default = {
        "id": "42",
        "name": "Default",
        "description": "Protected",
        "type": "精神",
        "key": "Default_Key",
    }
    sheet = load_character_sheet(sheet_bytes([default], skill_li(default)))

    with pytest.raises(SheetEditError):
        render_name_description_edit(sheet, index=0, name="No", description="No")


def test_render_name_description_edit_rejects_id_repair_state_without_consent() -> None:
    needs_repair = {
        "id": "",
        "name": "Needs Repair",
        "description": "Editable with repair consent later",
        "type": "",
        "key": "",
    }
    sheet = load_character_sheet(sheet_bytes([needs_repair], skill_li(needs_repair)))

    with pytest.raises(SheetEditError):
        render_name_description_edit(sheet, index=0, name="No", description="No")


def test_render_name_description_edit_repairs_empty_id_only_with_consent() -> None:
    needs_repair = {
        "id": "",
        "name": "Needs Repair",
        "description": "Editable with repair consent",
        "type": "",
        "key": "",
    }
    existing = {
        "id": "sk1",
        "name": "Existing",
        "description": "Existing id forces sk2",
        "type": "",
        "key": "",
    }
    sheet = load_character_sheet(sheet_bytes([needs_repair, existing], skill_li(needs_repair) + "\n" + skill_li(existing)))

    updated = render_name_description_edit(
        sheet,
        index=0,
        name="Repaired",
        description="Repaired desc",
        repair_id_confirmed=True,
    )
    rendered = load_character_sheet(updated)

    assert rendered.entries[0].skill["id"] == "sk2"
    assert rendered.entries[0].li.attrs["data-skill-id"] == "sk2"
    assert rendered.entries[1].skill == existing


def test_render_name_description_edit_repairs_duplicate_id_without_touching_other_duplicate() -> None:
    first = {
        "id": "dup",
        "name": "First",
        "description": "First duplicate",
        "type": "",
        "key": "",
    }
    second = {
        "id": "dup",
        "name": "Second",
        "description": "Second duplicate",
        "type": "",
        "key": "",
    }
    sheet = load_character_sheet(sheet_bytes([first, second], skill_li(first) + "\n" + skill_li(second)))

    updated = render_name_description_edit(
        sheet,
        index=0,
        name="First repaired",
        description="First repaired desc",
        repair_id_confirmed=True,
    )
    rendered = load_character_sheet(updated)

    assert rendered.entries[0].skill["id"] == "sk1"
    assert rendered.entries[1].skill == second


def test_render_protected_skill_replacement_requires_two_confirmations() -> None:
    default = {
        "id": "42",
        "name": "Default",
        "description": "Protected",
        "type": "精神",
        "key": "Default_Key",
    }
    sheet = load_character_sheet(sheet_bytes([default], skill_li(default)))

    with pytest.raises(SheetEditError):
        render_protected_skill_replacement(
            sheet,
            index=0,
            name="Original",
            description="Replacement",
            first_confirmation=True,
            second_confirmation=False,
        )


def test_render_protected_skill_replacement_generates_unused_skn_and_loses_default_identity() -> None:
    existing = {
        "id": "sk1",
        "name": "Existing",
        "description": "Existing id forces sk2",
        "type": "",
        "key": "",
    }
    default = {
        "id": "42",
        "name": "Default",
        "description": "Protected",
        "type": "精神",
        "key": "Default_Key",
    }
    sheet = load_character_sheet(sheet_bytes([existing, default], skill_li(existing) + "\n" + skill_li(default)))

    updated = render_protected_skill_replacement(
        sheet,
        index=1,
        name="New Original",
        description="Replacement desc",
        first_confirmation=True,
        second_confirmation=True,
    )
    rendered = load_character_sheet(updated)

    assert rendered.entries[0].skill == existing
    assert rendered.entries[1].skill == {
        "id": "sk2",
        "name": "New Original",
        "description": "Replacement desc",
        "type": "",
        "key": "",
    }
    assert rendered.entries[1].li.attrs["data-skill-id"] == "sk2"
    assert rendered.entries[1].li.attrs["data-skill-type"] == ""


def test_default_replacement_preserves_unrepresented_vacant_slots_byte_for_byte() -> None:
    default = {
        "id": "21",
        "name": "Default",
        "description": "Protected",
        "type": "physical",
        "key": "Default_Key",
    }
    vacant_tail = "\n  <li>&nbsp;</li>\n\t<li>\u00a0</li>\n<li>   </li>\n<li>&#160;</li>"
    raw = sheet_bytes([default], skill_li(default) + vacant_tail)
    sheet = load_character_sheet(raw)

    updated = render_protected_skill_replacement(
        sheet,
        index=0,
        name="Original",
        description="Replacement",
        first_confirmation=True,
        second_confirmation=True,
    )
    rendered = load_character_sheet(updated)

    assert vacant_tail.encode("utf-8") in updated
    assert rendered.read_only is False
    assert rendered.slot_count == 5
    assert rendered.vacant_slot_count == 4


def test_render_empty_slot_creation_generates_unused_skn_and_replaces_blank_li() -> None:
    empty = {"id": "", "name": "", "description": "", "type": "", "key": ""}
    existing = {
        "id": "sk1",
        "name": "Existing",
        "description": "Existing id forces sk2",
        "type": "",
        "key": "",
    }
    sheet = load_character_sheet(sheet_bytes([empty, existing], "<li>&nbsp;</li>\n" + skill_li(existing)))

    updated = render_empty_slot_creation(
        sheet,
        index=0,
        name="New From Empty",
        description="Created from empty slot",
    )
    rendered = load_character_sheet(updated)

    assert rendered.entries[0].skill == {
        "id": "sk2",
        "name": "New From Empty",
        "description": "Created from empty slot",
        "type": "",
        "key": "",
    }
    assert rendered.entries[0].li.attrs["data-skill-id"] == "sk2"
    assert rendered.entries[1].skill == existing


def test_render_empty_slot_creation_preserves_existing_li_indentation() -> None:
    empty = {"id": "", "name": "", "description": "", "type": "", "key": ""}
    raw = sheet_bytes([empty], "  <li>&nbsp;</li>")

    updated = render_empty_slot_creation(
        load_character_sheet(raw),
        index=0,
        name="Created",
        description="Description",
    )

    assert b'\n  <li data-skill-id="sk1"' in updated
    assert b'\n    <li data-skill-id="sk1"' not in updated


def test_render_vacant_slot_creation_appends_first_and_preserves_later_slots() -> None:
    existing = {
        "id": "sk1",
        "name": "Existing",
        "description": "Must stay",
        "type": "",
        "key": "",
        "unknown": {"keep": True},
    }
    later_vacant = b"\n\t<li>&nbsp;</li>\n  <li>&#160;</li>"
    raw = sheet_bytes([existing], skill_li(existing) + later_vacant.decode("ascii"))
    sheet = load_character_sheet(raw)

    updated = render_vacant_slot_creation(
        sheet,
        name='Added </script> "quoted" & <tag>',
        description="Line 1\nLine 2\t\\ 日本語 😀",
    )
    rendered = load_character_sheet(updated)

    assert rendered.entries[0].skill == existing
    assert rendered.entries[1].skill == {
        "id": "sk2",
        "name": 'Added </script> "quoted" & <tag>',
        "description": "Line 1\nLine 2\t\\ 日本語 😀",
        "type": "",
        "key": "",
    }
    assert rendered.slot_count == 3
    assert rendered.vacant_slot_count == 1
    assert b"</script>" not in updated[rendered.script_span.content_start : rendered.script_span.content_end].lower()
    assert later_vacant.splitlines()[-1] in updated


def test_render_vacant_slot_creation_supports_empty_crlf_skills_array() -> None:
    raw = sheet_bytes([], "<li>&nbsp;</li>").replace(b'"skills": []', b'"skills": [\r\n      ]')
    sheet = load_character_sheet(raw)

    updated = render_vacant_slot_creation(sheet, name="First", description="Created")
    rendered = load_character_sheet(updated)

    assert rendered.entries[0].skill["id"] == "sk1"
    assert rendered.entries[0].skill["name"] == "First"
    assert b"\r\n" in updated[rendered.script_span.content_start : rendered.script_span.content_end]


def test_render_middle_skill_deletion_replaces_only_target_with_explicit_empty_skill() -> None:
    skills = [
        {"id": "sk1", "name": "First", "description": "One", "type": "", "key": ""},
        {"id": "sk2", "name": "Middle", "description": "Two", "type": "", "key": ""},
        {"id": "sk3", "name": "Last", "description": "Three", "type": "", "key": ""},
    ]
    last_li = skill_li(skills[2]).encode("utf-8")
    raw = sheet_bytes(skills, "\n".join(skill_li(skill) for skill in skills))

    updated = render_skill_deletion(load_character_sheet(raw), index=1)
    rendered = load_character_sheet(updated)

    assert len(rendered.entries) == 3
    assert rendered.entries[0].skill == skills[0]
    assert rendered.entries[1].skill == {
        "id": "",
        "name": "",
        "description": "",
        "type": "",
        "key": "__ce2_empty_slot__",
    }
    assert rendered.entries[1].classification.kind.value == "empty_slot"
    assert rendered.entries[2].skill == skills[2]
    assert last_li in updated


def test_render_tail_skill_deletion_removes_json_object_and_creates_vacant_slot() -> None:
    skills = [
        {"id": "sk1", "name": "First", "description": "One", "type": "", "key": ""},
        {"id": "sk2", "name": "Last", "description": "Two", "type": "", "key": ""},
    ]
    raw = sheet_bytes(skills, "\n".join(skill_li(skill) for skill in skills) + "\n<li>&nbsp;</li>")
    sheet = load_character_sheet(raw)

    updated = render_skill_deletion(sheet, index=1)
    rendered = load_character_sheet(updated)

    assert [entry.skill for entry in rendered.entries] == [skills[0]]
    assert rendered.slot_count == 3
    assert rendered.vacant_slot_count == 2
    assert rendered.read_only is False


def test_render_only_skill_deletion_leaves_valid_empty_array() -> None:
    skill = {"id": "sk1", "name": "Only", "description": "One", "type": "", "key": ""}
    sheet = load_character_sheet(sheet_bytes([skill], skill_li(skill)))

    updated = render_skill_deletion(sheet, index=0)
    rendered = load_character_sheet(updated)

    assert rendered.entries == []
    assert rendered.slot_count == 1
    assert rendered.vacant_slot_count == 1
