from __future__ import annotations

import json

import pytest

from saga_seeker_skill_editor.core.character_sheet import CharacterSheetError, load_character_sheet
from saga_seeker_skill_editor.core.html_locator import find_direct_skill_lis, find_unique_skills_ul
from saga_seeker_skill_editor.core.skill_classifier import SkillKind, next_unused_sk_id


def sheet_bytes(skills: list[dict[str, object]], li_html: str) -> bytes:
    data = {
        "formatVersion": "1.0.0",
        "exportedAt": "2026-07-20T00:00:00Z",
        "data": {
            "name": "Synthetic",
            "profile": {},
            "status": {},
            "skills": skills,
            "personalities": [],
            "memories": [],
            "icon": {},
        },
    }
    json_text = json.dumps(data, ensure_ascii=False, indent=2)
    html = f"""<!doctype html>
<html>
<body>
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


def test_position_mapping_supports_mixed_and_ai_generated_original_ids() -> None:
    ai_skill = {
        "id": "skill_no01_2025-12-30-05-02",
        "name": "AI Original",
        "description": "Generated skill",
        "type": "",
        "key": "",
    }
    default_skill = {
        "id": "42",
        "name": "Default",
        "description": "Protected skill",
        "type": "精神",
        "key": "Default_Key",
    }
    raw = sheet_bytes([ai_skill, default_skill], skill_li(ai_skill) + "\n" + skill_li(default_skill))

    sheet = load_character_sheet(raw)

    assert sheet.read_only is False
    assert sheet.entries[0].classification.kind == SkillKind.ORIGINAL
    assert sheet.entries[0].classification.editable is True
    assert sheet.entries[1].classification.kind == SkillKind.DEFAULT
    assert sheet.entries[1].classification.editable is False


def test_direct_child_li_only_are_counted() -> None:
    skill = {
        "id": "nested-ok",
        "name": "Direct",
        "description": "Only direct li counts",
        "type": "",
        "key": "",
    }
    raw = sheet_bytes(
        [skill],
        skill_li(skill) + '\n<div><ul><li data-skill-id="not-a-skill">Nested</li></ul></div>',
    )

    ul_span = find_unique_skills_ul(raw)
    lis = find_direct_skill_lis(raw, ul_span)

    assert len(lis) == 1
    assert lis[0].attrs["data-skill-id"] == "nested-ok"


def test_count_mismatch_makes_sheet_read_only() -> None:
    skill = {
        "id": "sk1",
        "name": "One",
        "description": "Only JSON",
        "type": "",
        "key": "",
    }

    sheet = load_character_sheet(sheet_bytes([skill], ""))

    assert sheet.read_only is True
    assert sheet.entries[0].classification.kind == SkillKind.UNKNOWN


def test_fixed_six_slot_sheet_allows_trailing_vacant_html_slots() -> None:
    defaults = [
        {
            "id": "21",
            "name": "Sword Mastery",
            "description": "Default skill one",
            "type": "physical",
            "key": "Weapon_Mastery",
        },
        {
            "id": "48",
            "name": "Great Fortune",
            "description": "Default skill two",
            "type": "mental",
            "key": "Fortune",
        },
    ]
    vacant_lis = "\n".join("<li>&nbsp;</li>" for _ in range(4))
    raw = sheet_bytes(defaults, "\n".join(skill_li(skill) for skill in defaults) + "\n" + vacant_lis)

    sheet = load_character_sheet(raw)

    assert sheet.read_only is False
    assert sheet.slot_count == 6
    assert sheet.vacant_slot_count == 4
    assert [entry.classification.kind for entry in sheet.entries] == [SkillKind.DEFAULT, SkillKind.DEFAULT]


@pytest.mark.parametrize(
    "unsafe_extra",
    [
        '<li data-placeholder="true">&nbsp;</li>',
        "<li>unexpected</li>",
        "<li><span>&nbsp;</span></li>",
    ],
)
def test_extra_html_entries_must_be_plain_vacant_slots(unsafe_extra: str) -> None:
    skill = {
        "id": "21",
        "name": "Default",
        "description": "Protected",
        "type": "physical",
        "key": "Default_Key",
    }

    sheet = load_character_sheet(sheet_bytes([skill], skill_li(skill) + "\n" + unsafe_extra))

    assert sheet.read_only is True
    assert sheet.vacant_slot_count == 0
    assert sheet.entries[0].classification.kind == SkillKind.UNKNOWN


def test_empty_slot_is_classified_before_original() -> None:
    empty = {"id": "", "name": "", "description": "", "type": "", "key": ""}

    sheet = load_character_sheet(sheet_bytes([empty], "<li>&nbsp;</li>"))

    assert sheet.read_only is False
    assert sheet.entries[0].classification.kind == SkillKind.EMPTY_SLOT


def test_empty_id_original_requires_repair_but_keeps_existing_until_edited() -> None:
    needs_repair = {
        "id": "",
        "name": "Needs Repair",
        "description": "Editable only with repair consent",
        "type": "",
        "key": "",
    }

    sheet = load_character_sheet(sheet_bytes([needs_repair], skill_li(needs_repair)))

    assert sheet.read_only is False
    assert sheet.entries[0].classification.kind == SkillKind.ORIGINAL_NEEDS_ID_REPAIR
    assert sheet.entries[0].classification.needs_id_repair is True


def test_next_unused_sk_id_ignores_non_skn_ids_and_preserves_arbitrary_existing_ids() -> None:
    skills = [
        {"id": "sk1"},
        {"id": "日本語ID"},
        {"id": "skill_no01_2025-12-30-05-02"},
        {"id": "sk3"},
    ]

    assert next_unused_sk_id(skills) == "sk2"


def test_missing_script_is_rejected() -> None:
    with pytest.raises(CharacterSheetError):
        load_character_sheet(b"<html><body></body></html>")
