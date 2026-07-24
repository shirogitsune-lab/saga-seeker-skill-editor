"""Validated character-sheet generator established by the Phase 0 game gate.

The 2026-07-24 game import/export round trip promoted this module's candidate
JSON to the definitive v2 new-sheet contract recorded in ADR 0007.  The module
remains separate from the production editor model until Phase 1 adopts it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
import base64
import html
import json
from typing import Any
from uuid import UUID

from saga_seeker_skill_editor.core.script_safe_json import dumps_script_safe


FORMAT_VERSION = "1.0.0"
VISIBLE_SLOT_COUNT = 6

PROFILE_FIELDS = (
    ("basicSettings", "Basic Settings", "基本設定"),
    ("appearance", "Appearance", "外見"),
    ("personality", "Personality", "性格"),
    ("speechStyle", "Speaking Style", "口調"),
    ("background", "Background", "経歴"),
    ("talentsAndRole", "Special Skills & Role", "特技と役割"),
    ("otherFeatures", "Other Traits", "その他の特徴"),
)

VISIBLE_STATUS_FIELDS = (
    ("strength", "Strength", "筋力"),
    ("endurance", "Endurance", "耐久力"),
    ("intelligence", "Intelligence", "知力"),
    ("mentalStrength", "Willpower", "精神力"),
    ("agility", "Agility", "素早さ"),
    ("luck", "Luck", "運"),
)

RANK_ACTIVE_COUNT = {"E": 1, "D": 2, "C": 3, "B": 4, "A": 5, "S": 6}

EMPTY_PLACEHOLDER_MEMORY: dict[str, object] = {
    "id": "",
    "title": "",
    "summary": "",
    "location": "",
    "intent": "",
    "outcome": "",
    "tags": [],
    "isPlaceholder": True,
}


class CandidateSheetError(ValueError):
    """Raised when provisional output cannot be generated safely."""


@dataclass(frozen=True)
class GenerationInputs:
    """Injectable identity and time sources for deterministic generation."""

    uuid_factory: Callable[[], UUID]
    clock: Callable[[], datetime]
    local_timezone: tzinfo


def format_exported_at(value: datetime) -> str:
    """Format UTC time as Python microseconds plus a trailing seventh zero."""

    if value.tzinfo is None:
        raise CandidateSheetError("clock must return a timezone-aware datetime")
    utc_value = value.astimezone(timezone.utc)
    return utc_value.strftime("%Y-%m-%dT%H:%M:%S.%f") + "0Z"


def format_character_id(value: UUID, *, local_date: datetime) -> str:
    _require_uuid4(value)
    return f"{str(value).lower()}_{local_date:%Y-%m-%d}"


def format_memory_id(value: UUID, *, local_date: datetime) -> str:
    _require_uuid4(value)
    return f"memory_{str(value).lower()}_{local_date:%Y-%m-%d-%H-%M}"


def make_empty_placeholder_memory() -> dict[str, object]:
    """Return a new placeholder object without sharing its tags list."""

    return deepcopy(EMPTY_PLACEHOLDER_MEMORY)


def build_candidate_golden_document(
    *,
    icon_webp: bytes,
    generation: GenerationInputs,
) -> dict[str, object]:
    """Build the Phase 0 blank candidate using injected identity and time."""

    if not icon_webp:
        raise CandidateSheetError("default icon bytes must not be empty")
    now = generation.clock()
    if now.tzinfo is None:
        raise CandidateSheetError("clock must return a timezone-aware datetime")
    local_now = now.astimezone(generation.local_timezone)
    character_uuid = generation.uuid_factory()
    return {
        "formatVersion": FORMAT_VERSION,
        "exportedAt": format_exported_at(now),
        "data": {
            "characterId": format_character_id(character_uuid, local_date=local_now),
            "name": "",
            "profile": {field: "" for field, _tab, _label in PROFILE_FIELDS},
            "status": {
                "strength": "E",
                "endurance": "E",
                "intelligence": "E",
                "mentalStrength": "E",
                "agility": "E",
                "charm": "E",
                "luck": "E",
            },
            "skills": [],
            "personalities": [],
            "memories": [],
            "icon": {
                "mime": "image/webp",
                "dataUri": _icon_data_uri(icon_webp),
            },
        },
    }


def build_full_probe_document(
    *,
    icon_webp: bytes,
    generation: GenerationInputs,
    default_skill: Mapping[str, object],
    personality_keyword: Mapping[str, object],
) -> dict[str, object]:
    """Build the all-section Phase 0 probe document."""

    document = build_candidate_golden_document(icon_webp=icon_webp, generation=generation)
    data = _require_dict(document["data"], "data")
    data["name"] = "Phase 0 互換検証"
    data["profile"] = {
        "basicSettings": "Phase 0 基本設定",
        "appearance": "Phase 0 外見",
        "personality": "Phase 0 性格",
        "speechStyle": "Phase 0 口調",
        "background": "Phase 0 経歴",
        "talentsAndRole": "Phase 0 特技と役割",
        "otherFeatures": "Phase 0 その他の特徴",
    }
    data["status"] = {
        "strength": "S",
        "endurance": "A",
        "intelligence": "B",
        "mentalStrength": "C",
        "agility": "D",
        "charm": "E",
        "luck": "E",
    }
    data["skills"] = [
        _copy_exact_keys(
            default_skill,
            ("id", "name", "description", "type", "key"),
            label="default skill",
        ),
        {
            "id": "sk999",
            "name": "Phase 0 オリジナルスキル",
            "description": "Phase 0 オリジナルスキル説明",
            "type": "",
            "key": "",
        },
    ]
    data["personalities"] = [
        _copy_exact_keys(
            personality_keyword,
            ("id", "name", "type", "karma"),
            label="personality keyword",
        )
    ]

    local_now = generation.clock().astimezone(generation.local_timezone)
    memories: list[dict[str, object]] = []
    for index in range(8):
        if index in {1, 3, 5}:
            memories.append(make_empty_placeholder_memory())
            continue
        memory_uuid = generation.uuid_factory()
        memories.append(
            {
                "id": format_memory_id(memory_uuid, local_date=local_now),
                "title": f"Phase 0 思い出 {index + 1}",
                "summary": f"Phase 0 概要 {index + 1}",
                "location": f"Phase 0 場所 {index + 1}",
                "intent": f"Phase 0 意図 {index + 1}",
                "outcome": f"Phase 0 結果 {index + 1}",
                "tags": [f"phase0-{index + 1}", "重複可", " 重複可 "],
                "isPlaceholder": False,
            }
        )
    data["memories"] = memories
    return document


def render_candidate_html(document: Mapping[str, object]) -> bytes:
    """Render a self-contained, no-network Phase 0 candidate HTML."""

    data = _require_dict(document.get("data"), "data")
    profile = _require_dict(data.get("profile"), "data.profile")
    status = _require_dict(data.get("status"), "data.status")
    icon = _require_dict(data.get("icon"), "data.icon")
    skills = _require_list(data.get("skills"), "data.skills")
    personalities = _require_list(data.get("personalities"), "data.personalities")
    memories = _require_list(data.get("memories"), "data.memories")

    name = _require_string(data.get("name"), "data.name")
    icon_uri = _require_string(icon.get("dataUri"), "data.icon.dataUri")
    _validate_data_uri(icon_uri)

    profile_html = "\n".join(
        "        "
        + f'<section class="profile-field"><h3>{_text(label)}</h3>'
        + f'<div class="tab-content" data-tab-key="{_attr(tab_key)}">'
        + _display_text(_require_string(profile.get(field), f"data.profile.{field}"))
        + "</div></section>"
        for field, tab_key, label in PROFILE_FIELDS
    )
    status_html = "\n".join(
        _status_li(
            json_key=field,
            i18n_key=i18n_key,
            label=label,
            rank=_require_rank(status.get(field), f"data.status.{field}"),
        )
        for field, i18n_key, label in VISIBLE_STATUS_FIELDS
    )
    skills_html = _six_slots(skills, _skill_li)
    personalities_html = _six_slots(personalities, _personality_li)
    memories_html = _six_slots(memories, _memory_li)

    json_bytes = dumps_script_safe(dict(document), indent=2)
    json_text = json_bytes.decode("utf-8")
    output = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'">
  <title>Saga &amp; Seeker Phase 0 Candidate</title>
  <style>
    :root {{ color-scheme: dark; font-family: system-ui, sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #16181d; color: #f6f1e7; }}
    main {{ width: min(1100px, 100%); margin: auto; padding: 24px; }}
    .panel {{ border: 1px solid #8b7448; background: #22252b; padding: 18px; margin: 0 0 18px; }}
    h1, h2, h3 {{ color: #e5bf6a; }}
    h1 {{ margin-top: 0; }}
    h3 {{ font-size: 0.95rem; margin-bottom: 6px; }}
    #identity {{ display: grid; grid-template-columns: 160px 1fr; gap: 20px; align-items: center; }}
    #icon-value {{ width: 144px; height: 144px; object-fit: cover; border: 1px solid #aa8c50; }}
    #name-value {{ font-size: 1.5rem; overflow-wrap: anywhere; }}
    #profile-value {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }}
    .profile-field {{ border-top: 1px solid #555; }}
    .tab-content {{ white-space: pre-wrap; overflow-wrap: anywhere; }}
    #abilities-value, .item-list {{ list-style: none; margin: 0; padding: 0; }}
    #abilities-value {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }}
    .parameter {{ display: grid; grid-template-columns: 6em 1fr 2em; align-items: center; gap: 8px; }}
    .parameter-block {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 3px; list-style: none; padding: 0; }}
    .parameter-block li {{ height: 7px; background: #555; }}
    .parameter-block li.active {{ background: #d8ae51; }}
    .item-list {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}
    .item-list > li {{ min-height: 2.5em; padding: 8px; border-bottom: 1px solid #555; white-space: pre-wrap; overflow-wrap: anywhere; }}
    @media (max-width: 700px) {{
      #identity {{ grid-template-columns: 1fr; }}
      .item-list {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
<main>
  <h1>Phase 0 独自互換シート候補</h1>
  <section id="identity" class="panel">
    <img id="icon-value" src="{_attr(icon_uri)}" alt="キャラクターアイコン">
    <div><h2>キャラクター名</h2><div id="name-value" class="contents">{_display_text(name)}</div></div>
  </section>
  <section id="detail" class="panel">
    <h2>プロフィール</h2>
    <div id="profile-value">
{profile_html}
    </div>
  </section>
  <section id="abilities" class="panel">
    <h2>ステータス</h2>
    <ul id="abilities-value">
{status_html}
    </ul>
  </section>
  <section id="skills" class="panel">
    <h2>スキル</h2>
    <ul id="skills-value" class="item-list grid">
{skills_html}
    </ul>
  </section>
  <section id="personality" class="panel">
    <h2>性格キーワード</h2>
    <ul id="personality-value" class="item-list grid">
{personalities_html}
    </ul>
  </section>
  <section id="memories" class="panel">
    <h2>思い出</h2>
    <ul id="memories-value" class="item-list grid">
{memories_html}
    </ul>
  </section>
</main>
<script id="character-sheet-data" type="application/json">{json_text}</script>
</body>
</html>
"""
    return output.encode("utf-8")


def _status_li(*, json_key: str, i18n_key: str, label: str, rank: str) -> str:
    del json_key
    active_count = RANK_ACTIVE_COUNT[rank]
    blocks = "\n".join(
        '          <li class="active"></li>' if index < active_count else "          <li></li>"
        for index in range(6)
    )
    return (
        '      <li class="parameter">\n'
        f'        <span class="ability-label" data-i18n-key="{_attr(i18n_key)}">{_text(label)}</span>\n'
        '        <ul class="parameter-block">\n'
        f"{blocks}\n"
        "        </ul>\n"
        f'        <span class="parameter-rank">{_text(rank)}</span>\n'
        "      </li>"
    )


def _six_slots(values: Sequence[object], renderer: Callable[[Mapping[str, object]], str]) -> str:
    rendered: list[str] = []
    for index in range(VISIBLE_SLOT_COUNT):
        if index >= len(values):
            rendered.append("      <li>&nbsp;</li>")
            continue
        value = _require_dict(values[index], f"slot {index}")
        rendered.append("      " + renderer(value))
    return "\n".join(rendered)


def _skill_li(skill: Mapping[str, object]) -> str:
    skill_id = _require_string(skill.get("id"), "skill.id")
    name = _require_string(skill.get("name"), "skill.name")
    skill_type = _require_string(skill.get("type"), "skill.type")
    description = _require_string(skill.get("description"), "skill.description")
    return (
        f'<li data-skill-id="{_attr(skill_id)}" '
        f'data-skill-name="{_attr(name)}" '
        f'data-skill-type="{_attr(skill_type)}" '
        f'data-skill-description="{_attr(description)}">{_text(name)}</li>'
    )


def _personality_li(keyword: Mapping[str, object]) -> str:
    return f"<li>{_text(_require_string(keyword.get('name'), 'personality.name'))}</li>"


def _memory_li(memory: Mapping[str, object]) -> str:
    placeholder = memory.get("isPlaceholder")
    if placeholder is True:
        return "<li>&nbsp;</li>"
    if placeholder is not False:
        raise CandidateSheetError("memory.isPlaceholder must be a boolean")
    memory_id = _require_string(memory.get("id"), "memory.id")
    title = _require_string(memory.get("title"), "memory.title")
    summary = _require_string(memory.get("summary"), "memory.summary")
    location = _require_string(memory.get("location"), "memory.location")
    intent = _require_string(memory.get("intent"), "memory.intent")
    outcome = _require_string(memory.get("outcome"), "memory.outcome")
    tags = _require_list(memory.get("tags"), "memory.tags")
    tag_values = [_require_string(value, "memory.tags[]") for value in tags]
    tags_json = json.dumps(tag_values, ensure_ascii=False, separators=(",", ":"))
    return (
        f'<li data-memory-id="{_attr(memory_id)}" '
        f'data-memory-title="{_attr(title)}" '
        f'data-memory-summary="{_attr(summary)}" '
        f'data-memory-location="{_attr(location)}" '
        f'data-memory-intent="{_attr(intent)}" '
        f'data-memory-outcome="{_attr(outcome)}" '
        f'data-memory-tags="{_attr(tags_json)}">{_text(title)}</li>'
    )


def _display_text(value: str) -> str:
    return _text(value) if value else "（未入力）"


def _text(value: str) -> str:
    return html.escape(value, quote=False)


def _attr(value: str) -> str:
    return html.escape(value, quote=True).replace("'", "&#x27;")


def _icon_data_uri(icon_webp: bytes) -> str:
    return "data:image/webp;base64," + base64.b64encode(icon_webp).decode("ascii")


def _validate_data_uri(value: str) -> None:
    prefix = "data:image/webp;base64,"
    if not value.startswith(prefix):
        raise CandidateSheetError("candidate icon must be a WebP data URI")
    try:
        decoded = base64.b64decode(value[len(prefix) :], validate=True)
    except ValueError as error:
        raise CandidateSheetError("candidate icon data URI is invalid") from error
    if not decoded:
        raise CandidateSheetError("candidate icon data URI is empty")


def _copy_exact_keys(
    source: Mapping[str, object],
    keys: Sequence[str],
    *,
    label: str,
) -> dict[str, object]:
    missing = [key for key in keys if key not in source]
    if missing:
        raise CandidateSheetError(f"{label} is missing keys: {missing}")
    return {key: deepcopy(source[key]) for key in keys}


def _require_uuid4(value: UUID) -> None:
    if value.version != 4:
        raise CandidateSheetError("generated UUID must be version 4")


def _require_dict(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CandidateSheetError(f"{label} must be an object")
    return value


def _require_list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise CandidateSheetError(f"{label} must be an array")
    return value


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise CandidateSheetError(f"{label} must be a string")
    return value


def _require_rank(value: object, label: str) -> str:
    rank = _require_string(value, label)
    if rank not in RANK_ACTIVE_COUNT:
        raise CandidateSheetError(f"{label} has unsupported rank {rank!r}")
    return rank
