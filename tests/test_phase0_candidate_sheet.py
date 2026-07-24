from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json
import re
from uuid import UUID

import pytest

from saga_seeker_skill_editor.core.character_sheet import load_character_sheet
from saga_seeker_skill_editor.core.html_locator import (
    find_direct_personality_lis,
    find_direct_skill_lis,
    find_unique_personality_ul,
    find_unique_skills_ul,
)
from saga_seeker_skill_editor.core.phase0_candidate_sheet import (
    CandidateSheetError,
    GenerationInputs,
    build_candidate_golden_document,
    build_full_probe_document,
    format_exported_at,
    make_empty_placeholder_memory,
    render_candidate_html,
)


FIXED_CHARACTER_UUID = UUID("123e4567-e89b-42d3-a456-426614174000")
FIXED_MEMORY_UUIDS = (
    UUID("223e4567-e89b-42d3-a456-426614174000"),
    UUID("323e4567-e89b-42d3-a456-426614174000"),
    UUID("423e4567-e89b-42d3-a456-426614174000"),
    UUID("523e4567-e89b-42d3-a456-426614174000"),
    UUID("623e4567-e89b-42d3-a456-426614174000"),
)
FIXED_NOW = datetime(2026, 7, 24, 3, 4, 5, 123456, tzinfo=timezone.utc)
JST = timezone(timedelta(hours=9))
ICON_BYTES = b"provisional-webp-bytes"

DEFAULT_SKILL = {
    "id": "42",
    "name": "Phase 0 Default",
    "description": "Recognized default skill supplied by the private generator",
    "type": "physical",
    "key": "Default_Key",
}
PERSONALITY = {
    "id": 1,
    "name": "Phase 0 Personality",
    "type": "positive",
    "karma": "virtue",
}


def _generation(*uuids: UUID) -> GenerationInputs:
    iterator = iter(uuids)
    return GenerationInputs(
        uuid_factory=lambda: next(iterator),
        clock=lambda: FIXED_NOW,
        local_timezone=JST,
    )


def _script_json(raw: bytes) -> dict[str, object]:
    match = re.search(
        rb'<script id="character-sheet-data" type="application/json">(.*?)</script>',
        raw,
        re.S,
    )
    assert match is not None
    return json.loads(match.group(1).decode("utf-8"))


def test_candidate_golden_document_has_exact_schema_order_and_formats() -> None:
    document = build_candidate_golden_document(
        icon_webp=ICON_BYTES,
        generation=_generation(FIXED_CHARACTER_UUID),
    )

    assert list(document) == ["formatVersion", "exportedAt", "data"]
    assert document["formatVersion"] == "1.0.0"
    assert document["exportedAt"] == "2026-07-24T03:04:05.1234560Z"
    data = document["data"]
    assert isinstance(data, dict)
    assert list(data) == [
        "characterId",
        "name",
        "profile",
        "status",
        "skills",
        "personalities",
        "memories",
        "icon",
    ]
    assert data["characterId"] == "123e4567-e89b-42d3-a456-426614174000_2026-07-24"
    assert data["profile"] == {
        "basicSettings": "",
        "appearance": "",
        "personality": "",
        "speechStyle": "",
        "background": "",
        "talentsAndRole": "",
        "otherFeatures": "",
    }
    assert data["status"] == {
        "strength": "E",
        "endurance": "E",
        "intelligence": "E",
        "mentalStrength": "E",
        "agility": "E",
        "charm": "E",
        "luck": "E",
    }
    assert data["skills"] == []
    assert data["personalities"] == []
    assert data["memories"] == []
    assert data["icon"] == {
        "mime": "image/webp",
        "dataUri": "data:image/webp;base64,"
        + base64.b64encode(ICON_BYTES).decode("ascii"),
    }


def test_exported_at_requires_aware_clock_and_appends_seventh_zero() -> None:
    assert format_exported_at(FIXED_NOW) == "2026-07-24T03:04:05.1234560Z"
    with pytest.raises(CandidateSheetError):
        format_exported_at(FIXED_NOW.replace(tzinfo=None))


def test_empty_placeholder_is_complete_and_does_not_share_tags() -> None:
    first = make_empty_placeholder_memory()
    second = make_empty_placeholder_memory()

    assert first == {
        "id": "",
        "title": "",
        "summary": "",
        "location": "",
        "intent": "",
        "outcome": "",
        "tags": [],
        "isPlaceholder": True,
    }
    assert list(first) == [
        "id",
        "title",
        "summary",
        "location",
        "intent",
        "outcome",
        "tags",
        "isPlaceholder",
    ]
    assert first["tags"] is not second["tags"]


def test_blank_candidate_html_is_self_contained_and_loads_in_existing_core() -> None:
    document = build_candidate_golden_document(
        icon_webp=ICON_BYTES,
        generation=_generation(FIXED_CHARACTER_UUID),
    )

    raw = render_candidate_html(document)
    sheet = load_character_sheet(raw)

    assert sheet.read_only is False
    assert sheet.character_name == ""
    assert len(find_direct_skill_lis(raw, find_unique_skills_ul(raw))) == 6
    assert len(find_direct_personality_lis(raw, find_unique_personality_ul(raw))) == 6
    assert _script_json(raw) == document
    assert b"<script" in raw
    assert raw.count(b"<script") == 1
    assert b"http://" not in raw
    assert b"https://" not in raw
    assert b"default-src 'none'" in raw
    assert b"img-src data:" in raw


def test_full_probe_contains_all_sections_and_only_first_six_memories_in_html() -> None:
    document = build_full_probe_document(
        icon_webp=ICON_BYTES,
        generation=_generation(FIXED_CHARACTER_UUID, *FIXED_MEMORY_UUIDS),
        default_skill=DEFAULT_SKILL,
        personality_keyword=PERSONALITY,
    )

    raw = render_candidate_html(document)
    parsed = _script_json(raw)
    data = parsed["data"]
    assert isinstance(data, dict)
    assert data["skills"] == [
        DEFAULT_SKILL,
        {
            "id": "sk999",
            "name": "Phase 0 オリジナルスキル",
            "description": "Phase 0 オリジナルスキル説明",
            "type": "",
            "key": "",
        },
    ]
    assert data["personalities"] == [PERSONALITY]
    memories = data["memories"]
    assert isinstance(memories, list)
    assert len(memories) == 8
    assert [memory["isPlaceholder"] for memory in memories] == [
        False,
        True,
        False,
        True,
        False,
        True,
        False,
        False,
    ]
    assert memories[0]["id"] == (
        "memory_223e4567-e89b-42d3-a456-426614174000_2026-07-24-12-04"
    )

    skills_ul = find_unique_skills_ul(raw)
    skill_lis = find_direct_skill_lis(raw, skills_ul)
    assert len(skill_lis) == 6
    assert skill_lis[0].attrs["data-skill-id"] == "42"
    assert skill_lis[1].attrs["data-skill-id"] == "sk999"
    assert all(li.attrs == {} for li in skill_lis[2:])

    personality_lis = find_direct_personality_lis(raw, find_unique_personality_ul(raw))
    assert len(personality_lis) == 6
    assert personality_lis[0].inner.decode("utf-8") == PERSONALITY["name"]
    assert all(li.inner == b"&nbsp;" for li in personality_lis[1:])

    memories_match = re.search(
        rb'<ul id="memories-value"[^>]*>(.*?)</ul>',
        raw,
        re.S,
    )
    assert memories_match is not None
    memory_html = memories_match.group(1)
    assert len(re.findall(rb"<li\b", memory_html)) == 6
    assert b"Phase 0 \xe6\x80\x9d\xe3\x81\x84\xe5\x87\xba 7" not in memory_html
    assert b"Phase 0 \xe6\x80\x9d\xe3\x81\x84\xe5\x87\xba 8" not in memory_html


def test_user_strings_are_escaped_in_html_and_safe_in_json_script() -> None:
    document = build_candidate_golden_document(
        icon_webp=ICON_BYTES,
        generation=_generation(FIXED_CHARACTER_UUID),
    )
    data = document["data"]
    assert isinstance(data, dict)
    hostile = '</script><img src="https://example.invalid/x" onerror="alert(1)">'
    data["name"] = hostile
    profile = data["profile"]
    assert isinstance(profile, dict)
    profile["basicSettings"] = hostile

    raw = render_candidate_html(document)
    parsed = _script_json(raw)

    assert parsed["data"]["name"] == hostile
    assert raw.count(b"<script") == 1
    assert b"</script><img" not in raw
    assert re.search(rb'<img\s+[^>]*src="https?://', raw, re.I) is None
    assert re.search(rb"<img\s+[^>]*onerror\s*=", raw, re.I) is None
    assert b"\\u003c/script\\u003e" in raw
