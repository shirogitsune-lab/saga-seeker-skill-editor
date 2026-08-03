from __future__ import annotations

import base64
import json
import html
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from saga_seeker_skill_editor.core.character_sheet import (
    CharacterSheetDraft,
    CharacterSheetRenderError,
    create_character_sheet,
    load_character_sheet,
    render_character_sheet,
    validate_rendered_character_sheet,
)
from saga_seeker_skill_editor.core.phase0_candidate_sheet import GenerationInputs
from saga_seeker_skill_editor.core.json_span import locate_data_object_array


PROFILE_TABS = (
    ("basicSettings", "Basic Settings"),
    ("appearance", "Appearance"),
    ("personality", "Personality"),
    ("speechStyle", "Speaking Style"),
    ("background", "Background"),
    ("talentsAndRole", "Special Skills & Role"),
    ("otherFeatures", "Other Traits"),
)
STATUS_FIELDS = (
    ("strength", "Strength"),
    ("endurance", "Endurance"),
    ("intelligence", "Intelligence"),
    ("mentalStrength", "Willpower"),
    ("agility", "Agility"),
    ("luck", "Luck"),
)


def _sheet_bytes(*, format_version: object = "1.0.0", name: str = "Synthetic") -> bytes:
    document = {
        "formatVersion": format_version,
        "exportedAt": "2026-07-24T03:04:05.1234560Z",
        "data": {
            "name": name,
            "profile": {},
            "status": {},
            "skills": [],
            "personalities": [],
            "memories": [],
            "icon": {},
        },
    }
    payload = json.dumps(document, ensure_ascii=False, indent=2)
    slots = "\n".join("<li>&nbsp;</li>" for _ in range(6))
    return (
        "<!doctype html><html><body>"
        f'<div id="name-value">{name}</div>'
        f'<ul id="skills-value">{slots}</ul>'
        '<ul id="personality-value">'
        f"{slots}</ul>"
        f'<script id="character-sheet-data" type="application/json">{payload}</script>'
        "</body></html>"
    ).encode("utf-8")


def _profile_sheet_bytes() -> bytes:
    profile = {key: f"{key}-original" for key, _tab in PROFILE_TABS}
    document = {
        "formatVersion": "1.0.0",
        "exportedAt": "2026-07-24T03:04:05.1234560Z",
        "data": {
            "name": "Profile Test",
            "profile": profile,
            "status": {},
            "skills": [],
            "personalities": [],
            "memories": [],
            "icon": {},
        },
    }
    payload = json.dumps(document, ensure_ascii=False, indent=2)
    slots = "\n".join("<li>&nbsp;</li>" for _ in range(6))
    fields = "".join(
        f'<div class="tab-content" data-tab-key="{tab}">{profile[key]}</div>'
        for key, tab in PROFILE_TABS
    )
    return (
        "<!doctype html><html><body>"
        '<div id="name-value">Profile Test</div>'
        f'<div id="detail">{fields}</div>'
        f'<ul id="skills-value">{slots}</ul>'
        f'<ul id="personality-value">{slots}</ul>'
        f'<script id="character-sheet-data" type="application/json">{payload}</script>'
        "</body></html>"
    ).encode("utf-8")


def _profile_sheet_with_basic_settings(
    *,
    json_value: str,
    html_value: str,
) -> bytes:
    raw = _profile_sheet_bytes()
    return raw.replace(
        b'"basicSettings": "basicSettings-original"',
        b'"basicSettings": ' + json.dumps(json_value, ensure_ascii=False).encode("utf-8"),
    ).replace(
        b'data-tab-key="Basic Settings">basicSettings-original</div>',
        b'data-tab-key="Basic Settings">'
        + html_value.encode("utf-8")
        + b"</div>",
    )


def _status_sheet_bytes() -> bytes:
    status = {
        "strength": "E",
        "endurance": "D",
        "intelligence": "C",
        "mentalStrength": "B",
        "agility": "A",
        "charm": "E",
        "luck": "S",
    }
    document = {
        "formatVersion": "1.0.0",
        "exportedAt": "2026-07-24T03:04:05.1234560Z",
        "data": {
            "name": "Status Test",
            "profile": {},
            "status": status,
            "skills": [],
            "personalities": [],
            "memories": [],
            "icon": {},
        },
    }
    payload = json.dumps(document, ensure_ascii=False, indent=2)
    slots = "\n".join("<li>&nbsp;</li>" for _ in range(6))
    rows = []
    for index, (_key, label) in enumerate(STATUS_FIELDS, start=1):
        blocks = "".join(
            '<li class="active"></li>' if block < index else "<li></li>"
            for block in range(6)
        )
        rank = "EDCBAS"[index - 1]
        rows.append(
            '<li class="parameter">'
            f'<span class="ability-label" data-i18n-key="{label}">{label}</span>'
            f'<ul class="parameter-block">{blocks}</ul>'
            f'<span class="parameter-rank">{rank}</span></li>'
        )
    return (
        "<!doctype html><html><body>"
        '<div id="name-value">Status Test</div>'
        f'<ul id="abilities-value">{"".join(rows)}</ul>'
        f'<ul id="skills-value">{slots}</ul>'
        f'<ul id="personality-value">{slots}</ul>'
        f'<script id="character-sheet-data" type="application/json">{payload}</script>'
        "</body></html>"
    ).encode("utf-8")


def _memory_sheet_bytes(
    memory_count: int = 8,
    *,
    tag_encoding: str = "json",
) -> bytes:
    memories = []
    for index in range(memory_count):
        if index in {1, 3, 5}:
            memories.append(
                {
                    "id": "",
                    "title": "",
                    "summary": "",
                    "location": "",
                    "intent": "",
                    "outcome": "",
                    "tags": [],
                    "isPlaceholder": True,
                }
            )
        else:
            memory = {
                "id": f"memory-id-{index}",
                "title": f"title-{index}",
                "summary": f"summary-{index}",
                "location": f"location-{index}",
                "intent": f"intent-{index}",
                "outcome": f"outcome-{index}",
                "tags": [f"tag-{index}", "", f" tag-{index} "],
                "isPlaceholder": False,
            }
            if index == 0:
                memory["futureExtension"] = {"preserve": ["exact", 7]}
            memories.append(memory)
    document = {
        "formatVersion": "1.0.0",
        "exportedAt": "2026-07-24T03:04:05.1234560Z",
        "data": {
            "name": "Memory Test",
            "profile": {},
            "status": {},
            "skills": [],
            "personalities": [],
            "memories": memories,
            "icon": {},
        },
    }
    payload = json.dumps(document, ensure_ascii=False, indent=2)
    slots = "\n".join("<li>&nbsp;</li>" for _ in range(6))
    memory_lis = []
    for memory in memories[:6]:
        if memory["isPlaceholder"]:
            memory_lis.append("<li>&nbsp;</li>")
            continue
        if tag_encoding == "json":
            encoded_tags = json.dumps(
                memory["tags"],
                ensure_ascii=False,
                separators=(",", ":"),
            )
        elif tag_encoding == "pipe":
            encoded_tags = "|".join(memory["tags"])
        else:
            raise ValueError(f"unsupported tag encoding: {tag_encoding}")
        attrs = {
            "data-memory-id": memory["id"],
            "data-memory-title": memory["title"],
            "data-memory-summary": memory["summary"],
            "data-memory-location": memory["location"],
            "data-memory-intent": memory["intent"],
            "data-memory-outcome": memory["outcome"],
            "data-memory-tags": encoded_tags,
        }
        rendered_attrs = " ".join(
            f'{key}="{html.escape(value, quote=True)}"' for key, value in attrs.items()
        )
        if memory["id"] == "memory-id-0":
            rendered_attrs += ' data-future-attribute="keep-exact"'
        memory_lis.append(
            f'<li {rendered_attrs}>{html.escape(memory["title"], quote=False)}</li>'
        )
    memory_lis.extend("<li>&nbsp;</li>" for _ in range(6 - len(memory_lis)))
    return (
        "<!doctype html><html><body>"
        '<div id="name-value">Memory Test</div>'
        f'<ul id="skills-value">{slots}</ul>'
        f'<ul id="personality-value">{slots}</ul>'
        f'<ul id="memories-value">{"".join(memory_lis)}</ul>'
        f'<script id="character-sheet-data" type="application/json">{payload}</script>'
        "</body></html>"
    ).encode("utf-8")


def _replace_memory_json(
    raw: bytes,
    index: int,
    replacement: dict[str, object],
) -> bytes:
    marker = b'<script id="character-sheet-data" type="application/json">'
    prefix, remainder = raw.split(marker, 1)
    payload, suffix = remainder.split(b"</script>", 1)
    document = json.loads(payload.decode("utf-8"))
    document["data"]["memories"][index] = replacement
    return (
        prefix
        + marker
        + json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
        + b"</script>"
        + suffix
    )


def _placeholder_memory() -> dict[str, object]:
    return {
        "id": "",
        "title": "",
        "summary": "",
        "location": "",
        "intent": "",
        "outcome": "",
        "tags": [],
        "isPlaceholder": True,
    }


def _placeholder_memory_sheet_bytes(count: int) -> bytes:
    raw = _memory_sheet_bytes(0)
    marker = b'<script id="character-sheet-data" type="application/json">'
    prefix, remainder = raw.split(marker, 1)
    payload, suffix = remainder.split(b"</script>", 1)
    document = json.loads(payload.decode("utf-8"))
    document["data"]["memories"] = [_placeholder_memory() for _ in range(count)]
    return (
        prefix
        + marker
        + json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
        + b"</script>"
        + suffix
    )


def _icon_sheet_bytes() -> bytes:
    data_uri = "data:image/webp;base64,not-decoded-during-load"
    document = {
        "formatVersion": "1.0.0",
        "exportedAt": "2026-07-24T03:04:05.1234560Z",
        "data": {
            "name": "Icon Test",
            "profile": {},
            "status": {},
            "skills": [],
            "personalities": [],
            "memories": [],
            "icon": {
                "mime": "image/webp",
                "dataUri": data_uri,
                "futureIconKey": {"keep": True},
            },
        },
    }
    payload = json.dumps(document, ensure_ascii=False, indent=2)
    slots = "\n".join("<li>&nbsp;</li>" for _ in range(6))
    return (
        "<!doctype html><html><body>"
        '<div id="name-value">Icon Test</div>'
        f'<img id="icon-value" class="icon" src="{data_uri}" '
        'data-future-icon="keep" alt="">'
        f'<ul id="skills-value">{slots}</ul>'
        f'<ul id="personality-value">{slots}</ul>'
        f'<ul id="memories-value">{slots}</ul>'
        f'<script id="character-sheet-data" type="application/json">{payload}</script>'
        "</body></html>"
    ).encode("utf-8")


def test_unchanged_draft_renders_the_exact_input_bytes() -> None:
    raw = _sheet_bytes()

    sheet = load_character_sheet(raw)
    draft = CharacterSheetDraft.from_sheet(sheet)

    assert draft.has_changes is False
    assert render_character_sheet(sheet, draft) is sheet.raw_html
    assert render_character_sheet(sheet, draft) == raw


def test_editing_then_restoring_name_returns_to_exact_input_bytes() -> None:
    raw = _sheet_bytes(name="Original")
    sheet = load_character_sheet(raw)
    draft = CharacterSheetDraft.from_sheet(sheet)

    draft.set_name("Changed")
    assert draft.has_changes is True

    draft.set_name("Original")

    assert draft.has_changes is False
    assert render_character_sheet(sheet, draft) == raw


def test_unknown_format_version_makes_every_section_read_only() -> None:
    sheet = load_character_sheet(_sheet_bytes(format_version="9.9.9"))

    assert sheet.format_version == "9.9.9"
    assert sheet.whole_sheet_read_only is True
    assert sheet.read_only is True
    assert sheet.personality_read_only is True
    assert sheet.diagnostic_baseline.section_names == (
        "name",
        "profile",
        "status",
        "icon",
        "skills",
        "personalities",
        "memories",
    )
    assert all(
        not sheet.diagnostic_baseline.for_section(name).editable
        for name in sheet.diagnostic_baseline.section_names
    )
    assert all(
        "unknown-format-version"
        in sheet.diagnostic_baseline.for_section(name).diagnostic_codes
        for name in sheet.diagnostic_baseline.section_names
    )


def test_name_edit_patches_only_name_json_token_and_name_html_content() -> None:
    raw = _sheet_bytes(name="Original")
    sheet = load_character_sheet(raw)
    draft = CharacterSheetDraft.from_sheet(sheet)

    draft.set_name("</script>& changed")
    rendered = render_character_sheet(sheet, draft)

    assert rendered != raw
    assert b'"name": "\\u003c/script\\u003e\\u0026 changed"' in rendered
    assert b'<div id="name-value">&lt;/script&gt;&amp; changed</div>' in rendered
    assert rendered.replace(
        b'"name": "\\u003c/script\\u003e\\u0026 changed"',
        b'"name": "Original"',
    ).replace(
        b'<div id="name-value">&lt;/script&gt;&amp; changed</div>',
        b'<div id="name-value">Original</div>',
    ) == raw


def test_read_only_section_may_be_preserved_while_editable_section_changes() -> None:
    raw = _profile_sheet_bytes().replace(
        b"basicSettings-original</div>",
        b"existing-mismatch</div>",
        1,
    )
    sheet = load_character_sheet(raw)
    assert not sheet.diagnostic_baseline.for_section("profile").editable
    assert sheet.diagnostic_baseline.for_section("name").editable
    draft = CharacterSheetDraft.from_sheet(sheet)
    draft.set_name("Allowed edit")

    rendered = render_character_sheet(sheet, draft)
    validated = validate_rendered_character_sheet(sheet, rendered)

    assert validated.character_name == "Allowed edit"
    assert (
        validated.diagnostic_baseline.for_section("profile").json_bytes
        == sheet.diagnostic_baseline.for_section("profile").json_bytes
    )
    assert (
        validated.diagnostic_baseline.for_section("profile").html_bytes
        == sheet.diagnostic_baseline.for_section("profile").html_bytes
    )


def test_save_validation_rejects_read_only_bytes_changed_or_new_mismatch() -> None:
    profile_mismatch = _profile_sheet_bytes().replace(
        b"basicSettings-original</div>",
        b"existing-mismatch</div>",
        1,
    )
    profile_sheet = load_character_sheet(profile_mismatch)
    with pytest.raises(CharacterSheetRenderError, match="read-only profile"):
        validate_rendered_character_sheet(
            profile_sheet,
            profile_mismatch.replace(
                b"existing-mismatch",
                b"worsened-mismatch",
                1,
            ),
        )

    editable_sheet = load_character_sheet(_profile_sheet_bytes())
    with pytest.raises(CharacterSheetRenderError, match="name.*validation"):
        validate_rendered_character_sheet(
            editable_sheet,
            editable_sheet.raw_html.replace(
                b">Profile Test</div>",
                b">new-mismatch</div>",
                1,
            ),
        )


def test_create_character_sheet_uses_the_validated_golden_contract() -> None:
    raw = create_character_sheet(
        icon_webp=b"test-webp",
        generation=GenerationInputs(
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
        ),
    )

    sheet = load_character_sheet(raw)

    assert sheet.format_version == "1.0.0"
    assert sheet.data["exportedAt"] == "2026-07-24T03:04:05.1234560Z"
    assert (
        sheet.data["data"]["characterId"]
        == "123e4567-e89b-42d3-a456-426614174000_2026-07-24"
    )
    assert sheet.whole_sheet_read_only is False
    assert b"http://" not in raw
    assert b"https://" not in raw


def test_profile_edit_patches_only_one_json_token_and_matching_html_content() -> None:
    raw = _profile_sheet_bytes()
    sheet = load_character_sheet(raw)
    draft = CharacterSheetDraft.from_sheet(sheet)

    draft.set_profile("basicSettings", "</script>& changed")
    rendered = render_character_sheet(sheet, draft)

    assert b'"basicSettings": "\\u003c/script\\u003e\\u0026 changed"' in rendered
    assert (
        b'data-tab-key="Basic Settings">&lt;/script&gt;&amp; changed</div>'
        in rendered
    )
    assert rendered.replace(
        b'"basicSettings": "\\u003c/script\\u003e\\u0026 changed"',
        b'"basicSettings": "basicSettings-original"',
    ).replace(
        b'data-tab-key="Basic Settings">&lt;/script&gt;&amp; changed</div>',
        b'data-tab-key="Basic Settings">basicSettings-original</div>',
    ) == raw


@pytest.mark.parametrize("break_tag", ["<br>", "<br/>", "<br />", "<BR>"])
def test_profile_load_treats_supported_br_tags_as_semantic_newlines(
    break_tag: str,
) -> None:
    raw = _profile_sheet_with_basic_settings(
        json_value="first\r\nsecond\rthird",
        html_value=f"first{break_tag}second{break_tag}third",
    )

    sheet = load_character_sheet(raw)
    draft = CharacterSheetDraft.from_sheet(sheet)

    assert sheet.diagnostic_baseline.for_section("profile").editable is True
    assert sheet.raw_html is raw
    assert draft.has_changes is False
    assert render_character_sheet(sheet, draft) is raw


@pytest.mark.parametrize(
    "html_value",
    [
        "first<br >second",
        "first<br class=\"unexpected\">second",
        "first<strong>second</strong>",
        "first<!-- unexpected -->second",
    ],
)
def test_profile_load_rejects_markup_other_than_supported_br_tags(
    html_value: str,
) -> None:
    raw = _profile_sheet_with_basic_settings(
        json_value="first\nsecond",
        html_value=html_value,
    )

    sheet = load_character_sheet(raw)

    assert sheet.diagnostic_baseline.for_section("profile").editable is False


def test_profile_edit_preserves_json_newlines_and_renders_semantic_html_breaks() -> None:
    raw = _profile_sheet_bytes()
    sheet = load_character_sheet(raw)
    draft = CharacterSheetDraft.from_sheet(sheet)

    draft.set_profile("basicSettings", "first\r\nsecond\rthird<&")
    rendered = render_character_sheet(sheet, draft)
    reloaded = load_character_sheet(rendered)

    assert (
        reloaded.data["data"]["profile"]["basicSettings"]
        == "first\r\nsecond\rthird<&"
    )
    assert (
        b'data-tab-key="Basic Settings">'
        b"first<br>second<br>third&lt;&amp;</div>"
    ) in rendered
    assert reloaded.diagnostic_baseline.for_section("profile").editable is True


def test_status_edit_updates_json_rank_and_exactly_six_gauge_segments() -> None:
    raw = _status_sheet_bytes()
    sheet = load_character_sheet(raw)
    draft = CharacterSheetDraft.from_sheet(sheet)

    draft.set_status("strength", "S")
    rendered = render_character_sheet(sheet, draft)

    rendered_sheet = load_character_sheet(rendered)
    strength = dict(rendered_sheet.status_entries)["strength"]
    assert rendered_sheet.data["data"]["status"]["strength"] == "S"
    assert strength.rank == "S"
    assert sum("active" in li.attrs.get("class", "").split() for li in strength.gauge_lis) == 6
    assert rendered.replace(b'"strength": "S"', b'"strength": "E"').replace(
        strength.li.raw,
        dict(sheet.status_entries)["strength"].li.raw,
    ) == raw


def test_memory_boundary_keeps_eight_json_objects_and_six_html_slots_consistent() -> None:
    sheet = load_character_sheet(_memory_sheet_bytes())

    baseline = sheet.diagnostic_baseline.for_section("memories")
    assert baseline.editable is True
    assert baseline.json_count == 8
    assert baseline.html_count == 6
    assert baseline.position_consistent is True
    assert len(sheet.memory_entries) == 8
    assert [entry.html_li is None for entry in sheet.memory_entries] == [
        False,
        False,
        False,
        False,
        False,
        False,
        True,
        True,
    ]


def test_game_pipe_memory_tags_load_as_editable_when_json_tags_match() -> None:
    sheet = load_character_sheet(_memory_sheet_bytes(tag_encoding="pipe"))

    section = sheet.diagnostic_baseline.for_section("memories")
    assert section.editable is True
    assert section.position_consistent is True
    assert len(sheet.memory_entries) == 8


def test_editing_game_pipe_memory_tags_preserves_pipe_encoding() -> None:
    sheet = load_character_sheet(_memory_sheet_bytes(tag_encoding="pipe"))
    draft = CharacterSheetDraft.from_sheet(sheet)
    edited_tags = ["first", "contains|pipe", ""]

    draft.set_memory_tags(0, edited_tags)
    rendered = render_character_sheet(sheet, draft)
    reloaded = load_character_sheet(rendered)
    memory = reloaded.memory_entries[0]

    assert memory.memory["tags"] == edited_tags
    assert memory.memory["futureExtension"] == {"preserve": ["exact", 7]}
    assert memory.html_li is not None
    assert memory.html_li.attrs["data-memory-tags"] == "first|contains|pipe|"
    assert reloaded.diagnostic_baseline.for_section("memories").editable is True


def test_non_tag_edit_keeps_game_pipe_attribute_bytes_unchanged() -> None:
    raw = _memory_sheet_bytes(tag_encoding="pipe")
    sheet = load_character_sheet(raw)
    draft = CharacterSheetDraft.from_sheet(sheet)
    original_attribute = b'data-memory-tags="tag-0|| tag-0 "'

    draft.set_memory_field(0, "summary", "changed summary")
    rendered = render_character_sheet(sheet, draft)

    assert rendered.count(original_attribute) == raw.count(original_attribute)
    assert rendered.replace(
        b'"summary": "changed summary"', b'"summary": "summary-0"', 1
    ).replace(
        b'data-memory-summary="changed summary"',
        b'data-memory-summary="summary-0"',
        1,
    ) == raw


@pytest.mark.parametrize("count", [0, 1, 6, 15])
def test_empty_and_placeholder_only_memory_states_remain_editable(count: int) -> None:
    raw = (
        _memory_sheet_bytes(0)
        if count == 0
        else _placeholder_memory_sheet_bytes(count)
    )

    sheet = load_character_sheet(raw)
    section = sheet.diagnostic_baseline.for_section("memories")

    assert section.editable is True
    assert section.html_count == 6
    assert len(sheet.memory_entries) == count
    assert all(entry.is_placeholder for entry in sheet.memory_entries)
    assert render_character_sheet(sheet, CharacterSheetDraft.from_sheet(sheet)) == raw


@pytest.mark.parametrize("tag_encoding", ["json", "pipe"])
def test_empty_tag_array_matches_both_supported_html_encodings(
    tag_encoding: str,
) -> None:
    raw = _memory_sheet_bytes(tag_encoding=tag_encoding)
    first = dict(load_character_sheet(raw).data["data"]["memories"][0])
    first["tags"] = []
    raw = _replace_memory_json(raw, 0, first)
    old_value = (
        b'[&quot;tag-0&quot;,&quot;&quot;,&quot; tag-0 &quot;]'
        if tag_encoding == "json"
        else b"tag-0|| tag-0 "
    )
    new_value = b"[]" if tag_encoding == "json" else b""
    raw = raw.replace(
        b'data-memory-tags="' + old_value + b'"',
        b'data-memory-tags="' + new_value + b'"',
        1,
    )

    sheet = load_character_sheet(raw)

    assert sheet.diagnostic_baseline.for_section("memories").editable is True
    assert sheet.memory_entries[0].memory["tags"] == []


@pytest.mark.parametrize(
    ("tag_encoding", "old", "new"),
    [
        ("json", b'data-memory-id="memory-id-0"', b'data-memory-id="different"'),
        ("json", b'data-memory-title="title-0"', b'data-memory-title="different"'),
        (
            "json",
            b'data-memory-summary="summary-0"',
            b'data-memory-summary="different"',
        ),
        ("json", b">title-0</li>", b">different</li>"),
        (
            "pipe",
            b'data-memory-tags="tag-0|| tag-0 "',
            b'data-memory-tags="tag-0|different"',
        ),
        (
            "json",
            b'data-memory-tags="[&quot;tag-0&quot;,&quot;&quot;,&quot; tag-0 &quot;]"',
            b'data-memory-tags="[&quot;different&quot;]"',
        ),
        (
            "json",
            b'data-memory-tags="[&quot;tag-0&quot;,&quot;&quot;,&quot; tag-0 &quot;]"',
            b'data-memory-tags="[broken"',
        ),
    ],
)
def test_real_memory_mismatches_keep_memories_read_only(
    tag_encoding: str,
    old: bytes,
    new: bytes,
) -> None:
    raw = _memory_sheet_bytes(tag_encoding=tag_encoding).replace(old, new, 1)

    sheet = load_character_sheet(raw)

    assert sheet.diagnostic_baseline.for_section("memories").editable is False
    assert sheet.diagnostic_baseline.for_section("name").editable is True


def test_non_string_json_tag_keeps_memories_read_only() -> None:
    raw = _memory_sheet_bytes()
    first = dict(load_character_sheet(raw).data["data"]["memories"][0])
    first["tags"] = ["tag-0", 7]

    sheet = load_character_sheet(_replace_memory_json(raw, 0, first))

    section = sheet.diagnostic_baseline.for_section("memories")
    assert section.editable is False
    assert "tags must be an array of strings" in section.read_only_reason


def test_placeholder_with_known_value_keeps_memories_read_only() -> None:
    raw = _placeholder_memory_sheet_bytes(1)
    invalid = _placeholder_memory()
    invalid["summary"] = "not empty"

    sheet = load_character_sheet(_replace_memory_json(raw, 0, invalid))

    section = sheet.diagnostic_baseline.for_section("memories")
    assert section.editable is False
    assert "placeholder fields must use the complete empty structure" in (
        section.read_only_reason
    )


def test_memory_html_slot_count_other_than_six_keeps_memories_read_only() -> None:
    raw = _memory_sheet_bytes(0).replace(
        b'<ul id="memories-value"><li>&nbsp;</li>',
        b'<ul id="memories-value">',
        1,
    )

    sheet = load_character_sheet(raw)

    section = sheet.diagnostic_baseline.for_section("memories")
    assert section.editable is False
    assert section.html_count == 5


def test_existing_icon_is_matched_by_raw_uri_without_decoding_image_bytes() -> None:
    raw = _icon_sheet_bytes()

    sheet = load_character_sheet(raw)

    baseline = sheet.diagnostic_baseline.for_section("icon")
    assert baseline.editable is True
    assert baseline.position_consistent is True
    assert baseline.html_bytes == (
        b'<img id="icon-value" class="icon" '
        b'src="data:image/webp;base64,not-decoded-during-load" '
        b'data-future-icon="keep" alt="">'
    )
    assert sheet.whole_sheet_read_only is False


def test_editing_one_memory_field_preserves_unknown_keys_and_all_other_bytes() -> None:
    raw = _memory_sheet_bytes()
    sheet = load_character_sheet(raw)
    draft = CharacterSheetDraft.from_sheet(sheet)

    draft.set_memory_field(0, "summary", "</script>& changed")
    rendered = render_character_sheet(sheet, draft)

    assert b'"futureExtension": {' in rendered
    assert b'data-future-attribute="keep-exact"' in rendered
    assert b'"summary": "\\u003c/script\\u003e\\u0026 changed"' in rendered
    assert b'data-memory-summary="&lt;/script&gt;&amp; changed"' in rendered
    assert rendered.replace(
        b'"summary": "\\u003c/script\\u003e\\u0026 changed"',
        b'"summary": "summary-0"',
        1,
    ).replace(
        b'data-memory-summary="&lt;/script&gt;&amp; changed"',
        b'data-memory-summary="summary-0"',
        1,
    ) == raw


def test_multiple_memory_fields_and_tags_keep_exact_user_tag_values() -> None:
    sheet = load_character_sheet(_memory_sheet_bytes())
    draft = CharacterSheetDraft.from_sheet(sheet)
    tags = [" duplicate ", "", "duplicate", "e\u0301", "é"]

    draft.set_memory_field(0, "title", "new title")
    draft.set_memory_field(0, "summary", "new summary")
    draft.set_memory_tags(0, tags)
    rendered = render_character_sheet(sheet, draft)
    reloaded = load_character_sheet(rendered)
    memory = reloaded.memory_entries[0]

    assert memory.memory["title"] == "new title"
    assert memory.memory["summary"] == "new summary"
    assert memory.memory["tags"] == tags
    assert memory.memory["futureExtension"] == {"preserve": ["exact", 7]}
    assert memory.html_li is not None
    assert json.loads(memory.html_li.attrs["data-memory-tags"]) == tags
    assert memory.html_li.attrs["data-future-attribute"] == "keep-exact"


def test_memory_reorder_across_six_slot_boundary_moves_exact_json_objects() -> None:
    sheet = load_character_sheet(_memory_sheet_bytes())
    json_bytes = sheet.raw_html[
        sheet.script_span.content_start : sheet.script_span.content_end
    ]
    spans = locate_data_object_array(json_bytes, "memories")
    original_objects = [
        json_bytes[span.start : span.end] for span in spans.objects
    ]
    draft = CharacterSheetDraft.from_sheet(sheet)

    draft.move_memory(6, 4)
    rendered = render_character_sheet(sheet, draft)
    reloaded = load_character_sheet(rendered)
    rendered_json = rendered[
        reloaded.script_span.content_start : reloaded.script_span.content_end
    ]
    rendered_spans = locate_data_object_array(rendered_json, "memories")
    rendered_objects = [
        rendered_json[span.start : span.end] for span in rendered_spans.objects
    ]

    assert rendered_objects == [
        original_objects[index] for index in (0, 1, 2, 3, 6, 4, 5, 7)
    ]
    assert [entry.memory["id"] for entry in reloaded.memory_entries] == [
        "memory-id-0",
        "",
        "memory-id-2",
        "",
        "memory-id-6",
        "memory-id-4",
        "",
        "memory-id-7",
    ]
    assert reloaded.memory_entries[4].html_li is not None
    assert (
        reloaded.memory_entries[4].html_li.attrs["data-memory-id"]
        == "memory-id-6"
    )


def test_memory_edit_and_reorder_are_rendered_as_one_consistent_draft() -> None:
    sheet = load_character_sheet(_memory_sheet_bytes())
    draft = CharacterSheetDraft.from_sheet(sheet)

    draft.set_memory_field(0, "summary", "edited before move")
    draft.move_memory(0, 6)
    rendered = render_character_sheet(sheet, draft)
    reloaded = load_character_sheet(rendered)

    moved = reloaded.memory_entries[6]
    assert moved.memory["id"] == "memory-id-0"
    assert moved.memory["summary"] == "edited before move"
    assert moved.memory["futureExtension"] == {"preserve": ["exact", 7]}
    assert moved.html_li is None
    assert [
        entry.memory["id"] for entry in reloaded.memory_entries[:6]
    ] == ["", "memory-id-2", "", "memory-id-4", "", "memory-id-6"]


def test_placeholder_conversion_keeps_count_and_generates_exact_memory_id() -> None:
    sheet = load_character_sheet(_memory_sheet_bytes())
    draft = CharacterSheetDraft.from_sheet(sheet)
    generation = GenerationInputs(
        uuid_factory=lambda: UUID("723e4567-e89b-42d3-a456-426614174000"),
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

    draft.convert_placeholder_to_normal(1, generation=generation)
    rendered = render_character_sheet(sheet, draft)
    reloaded = load_character_sheet(rendered)
    converted = reloaded.memory_entries[1]

    assert len(reloaded.memory_entries) == 8
    assert converted.is_placeholder is False
    assert converted.memory == {
        "id": "memory_723e4567-e89b-42d3-a456-426614174000_2026-07-24-12-04",
        "title": "",
        "summary": "",
        "location": "",
        "intent": "",
        "outcome": "",
        "tags": [],
        "isPlaceholder": False,
    }
    assert converted.html_li is not None
    assert converted.html_li.attrs["data-memory-id"] == converted.memory["id"]


def test_normal_memory_replacement_uses_complete_placeholder_without_count_change() -> None:
    sheet = load_character_sheet(_memory_sheet_bytes())
    draft = CharacterSheetDraft.from_sheet(sheet)

    draft.replace_memory_with_placeholder(0)
    rendered = render_character_sheet(sheet, draft)
    reloaded = load_character_sheet(rendered)

    assert len(reloaded.memory_entries) == 8
    assert reloaded.memory_entries[0].memory == {
        "id": "",
        "title": "",
        "summary": "",
        "location": "",
        "intent": "",
        "outcome": "",
        "tags": [],
        "isPlaceholder": True,
    }
    assert reloaded.memory_entries[0].html_li is not None
    assert reloaded.memory_entries[0].html_li.attrs == {}


def test_placeholder_conversion_then_replacement_returns_to_unchanged_bytes() -> None:
    raw = _memory_sheet_bytes()
    sheet = load_character_sheet(raw)
    draft = CharacterSheetDraft.from_sheet(sheet)
    generation = GenerationInputs(
        uuid_factory=lambda: UUID("723e4567-e89b-42d3-a456-426614174000"),
        clock=lambda: datetime(2026, 7, 24, 3, 4, 5, tzinfo=timezone.utc),
        local_timezone=timezone(timedelta(hours=9)),
    )

    draft.convert_placeholder_to_normal(1, generation=generation)
    draft.replace_memory_with_placeholder(1)

    assert not draft.has_changes
    assert render_character_sheet(sheet, draft) == raw


def test_remove_memory_decreases_count_and_promotes_seventh_item_into_html() -> None:
    sheet = load_character_sheet(_memory_sheet_bytes())
    draft = CharacterSheetDraft.from_sheet(sheet)

    draft.remove_memory(0)
    rendered = render_character_sheet(sheet, draft)
    reloaded = load_character_sheet(rendered)

    assert len(reloaded.memory_entries) == 7
    assert [entry.memory["id"] for entry in reloaded.memory_entries] == [
        "",
        "memory-id-2",
        "",
        "memory-id-4",
        "",
        "memory-id-6",
        "memory-id-7",
    ]
    promoted = reloaded.memory_entries[5]
    assert promoted.html_li is not None
    assert promoted.html_li.attrs["data-memory-id"] == "memory-id-6"


def test_add_normal_memory_below_limit_generates_id_and_keeps_html_at_six_slots() -> None:
    sheet = load_character_sheet(_memory_sheet_bytes())
    draft = CharacterSheetDraft.from_sheet(sheet)
    generation = GenerationInputs(
        uuid_factory=lambda: UUID("823e4567-e89b-42d3-a456-426614174000"),
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

    draft.add_normal_memory(generation=generation)
    rendered = render_character_sheet(sheet, draft)
    reloaded = load_character_sheet(rendered)

    assert len(reloaded.memory_entries) == 9
    added = reloaded.memory_entries[8]
    assert added.memory["id"] == (
        "memory_823e4567-e89b-42d3-a456-426614174000_2026-07-24-12-04"
    )
    assert added.is_placeholder is False
    assert added.html_li is None
    assert reloaded.diagnostic_baseline.for_section("memories").html_count == 6


def test_new_and_converted_memories_can_be_edited_before_render() -> None:
    sheet = load_character_sheet(_memory_sheet_bytes())
    draft = CharacterSheetDraft.from_sheet(sheet)
    uuids = iter(
        (
            UUID("823e4567-e89b-42d3-a456-426614174000"),
            UUID("923e4567-e89b-42d3-a456-426614174000"),
        )
    )
    generation = GenerationInputs(
        uuid_factory=lambda: next(uuids),
        clock=lambda: datetime(2026, 7, 24, 3, 4, 5, tzinfo=timezone.utc),
        local_timezone=timezone(timedelta(hours=9)),
    )

    draft.convert_placeholder_to_normal(1, generation=generation)
    draft.set_memory_field(1, "title", "変換後")
    draft.set_memory_tags(1, [" そのまま ", "", "同一", "同一"])
    new_token = draft.add_normal_memory(generation=generation)
    draft.set_memory_field(new_token, "summary", "追加直後")

    reloaded = load_character_sheet(render_character_sheet(sheet, draft))

    assert reloaded.memory_entries[1].memory["title"] == "変換後"
    assert reloaded.memory_entries[1].memory["tags"] == [
        " そのまま ",
        "",
        "同一",
        "同一",
    ]
    assert reloaded.memory_entries[-1].memory["summary"] == "追加直後"


def test_fill_placeholder_memories_stops_at_total_count_fifteen() -> None:
    sheet = load_character_sheet(_memory_sheet_bytes())
    draft = CharacterSheetDraft.from_sheet(sheet)

    added_count = draft.fill_placeholder_memories()
    rendered = render_character_sheet(sheet, draft)
    reloaded = load_character_sheet(rendered)

    assert added_count == 7
    assert len(reloaded.memory_entries) == 15
    assert all(
        entry.is_placeholder for entry in reloaded.memory_entries[8:]
    )
    assert all(entry.memory["id"] == "" for entry in reloaded.memory_entries[8:])


def test_existing_over_limit_sheet_allows_conversion_but_blocks_count_growth() -> None:
    sheet = load_character_sheet(_memory_sheet_bytes(memory_count=16))
    draft = CharacterSheetDraft.from_sheet(sheet)
    uuids = iter(
        (
            UUID("923e4567-e89b-42d3-a456-426614174000"),
            UUID("a23e4567-e89b-42d3-a456-426614174000"),
        )
    )
    generation = GenerationInputs(
        uuid_factory=lambda: next(uuids),
        clock=lambda: datetime(2026, 7, 24, 3, 4, 5, tzinfo=timezone.utc),
        local_timezone=timezone(timedelta(hours=9)),
    )

    draft.convert_placeholder_to_normal(1, generation=generation)
    with pytest.raises(CharacterSheetRenderError, match="limit"):
        draft.add_normal_memory(generation=generation)
    assert draft.fill_placeholder_memories() == 0

    reloaded = load_character_sheet(render_character_sheet(sheet, draft))
    assert len(reloaded.memory_entries) == 16
    assert reloaded.memory_entries[1].is_placeholder is False


def test_processed_webp_replacement_patches_only_icon_tokens_and_src_attribute() -> None:
    raw = _icon_sheet_bytes()
    sheet = load_character_sheet(raw)
    draft = CharacterSheetDraft.from_sheet(sheet)
    webp_bytes = b"validated-512-webp"

    draft.set_icon_webp(webp_bytes)
    rendered = render_character_sheet(sheet, draft)
    reloaded = load_character_sheet(rendered)
    expected_uri = (
        "data:image/webp;base64,"
        + base64.b64encode(webp_bytes).decode("ascii")
    )

    assert reloaded.data["data"]["icon"]["mime"] == "image/webp"
    assert reloaded.data["data"]["icon"]["dataUri"] == expected_uri
    assert reloaded.data["data"]["icon"]["futureIconKey"] == {"keep": True}
    assert reloaded.icon_span is not None
    assert reloaded.icon_span.attrs["src"] == expected_uri
    assert reloaded.icon_span.attrs["data-future-icon"] == "keep"
