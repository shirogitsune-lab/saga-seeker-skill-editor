"""Character sheet loading and position-based skill mapping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import json

from saga_seeker_skill_editor.core.html_locator import (
    ElementSpan,
    HtmlStructureError,
    LiSpan,
    find_direct_skill_lis,
    find_direct_personality_lis,
    find_unique_script_json,
    find_unique_personality_ul,
    find_unique_skills_ul,
    text_content,
)
from saga_seeker_skill_editor.core.personality_catalog import (
    PersonalityCatalogError,
    catalog_by_id,
    load_personality_catalog,
)
from saga_seeker_skill_editor.core.skill_classifier import (
    SkillClassification,
    classify_skill,
    duplicate_string_ids,
)


class CharacterSheetError(ValueError):
    """Raised when a character sheet cannot be safely interpreted."""


@dataclass(frozen=True)
class SkillEntry:
    index: int
    skill: dict[str, Any]
    li: LiSpan
    position_consistent: bool
    classification: SkillClassification


@dataclass(frozen=True)
class PersonalityEntry:
    index: int
    keyword: dict[str, Any]
    li: LiSpan


@dataclass(frozen=True)
class CharacterSheet:
    raw_html: bytes
    data: dict[str, Any]
    script_span: ElementSpan
    skills_ul_span: ElementSpan
    entries: list[SkillEntry]
    vacant_lis: list[LiSpan]
    slot_count: int
    vacant_slot_count: int
    read_only: bool
    read_only_reason: str = ""
    personality_ul_span: ElementSpan | None = None
    personality_entries: tuple[PersonalityEntry, ...] = ()
    personality_lis: tuple[LiSpan, ...] = ()
    personality_slot_count: int = 0
    personality_read_only: bool = True
    personality_read_only_reason: str = "性格キーワード欄を確認できません"

    @property
    def character_name(self) -> str:
        data = self.data.get("data")
        if isinstance(data, dict) and isinstance(data.get("name"), str):
            return data["name"]
        return ""


def load_character_sheet(raw_html: bytes) -> CharacterSheet:
    try:
        script_span = find_unique_script_json(raw_html)
        ul_span = find_unique_skills_ul(raw_html)
    except HtmlStructureError as exc:
        raise CharacterSheetError(str(exc)) from exc

    try:
        parsed = json.loads(raw_html[script_span.content_start : script_span.content_end].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CharacterSheetError(f"failed to parse character-sheet-data JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise CharacterSheetError("character-sheet-data JSON root is not an object")
    data = parsed.get("data")
    if not isinstance(data, dict):
        raise CharacterSheetError("character-sheet-data.data is not an object")
    skills = data.get("skills")
    if not isinstance(skills, list) or not all(isinstance(skill, dict) for skill in skills):
        raise CharacterSheetError("character-sheet-data.data.skills is not a list of objects")

    personalities = data.get("personalities")
    if not isinstance(personalities, list) or not all(isinstance(item, dict) for item in personalities):
        personalities = []
        personality_data_error = "character-sheet-data.data.personalities is not a list of objects"
    else:
        personality_data_error = ""

    lis = find_direct_skill_lis(raw_html, ul_span)
    trailing_lis = lis[len(skills) :] if len(lis) >= len(skills) else []
    trailing_slots_are_vacant = all(_is_vacant_html_slot(li) for li in trailing_lis)
    counts_are_compatible = len(lis) >= len(skills) and trailing_slots_are_vacant
    read_only = not counts_are_compatible
    reason = ""
    if read_only:
        reason = f"skill count mismatch: JSON has {len(skills)}, HTML has {len(lis)} direct li elements"
        if len(lis) > len(skills):
            reason += "; trailing HTML entries are not safe vacant slots"

    duplicate_ids = duplicate_string_ids(skills)
    entries: list[SkillEntry] = []
    for index, skill in enumerate(skills):
        if index < len(lis):
            li = lis[index]
            position_consistent = (not read_only) and _position_consistent(skill, li)
        else:
            li = _missing_li()
            position_consistent = False
        classification = classify_skill(
            skill,
            position_consistent=position_consistent,
            duplicate_ids=duplicate_ids,
        )
        entries.append(
            SkillEntry(
                index=index,
                skill=skill,
                li=li,
                position_consistent=position_consistent,
                classification=classification,
            )
        )

    if any(not entry.position_consistent for entry in entries):
        read_only = True
        if not reason:
            reason = "JSON and HTML skill entries do not safely match by position"

    (
        personality_ul_span,
        personality_entries,
        personality_lis,
        personality_slot_count,
        personality_read_only,
        personality_reason,
    ) = _load_personalities(raw_html, personalities, personality_data_error)

    return CharacterSheet(
        raw_html=raw_html,
        data=parsed,
        script_span=script_span,
        skills_ul_span=ul_span,
        entries=entries,
        vacant_lis=trailing_lis if counts_are_compatible else [],
        slot_count=len(lis),
        vacant_slot_count=len(trailing_lis) if counts_are_compatible else 0,
        read_only=read_only,
        read_only_reason=reason,
        personality_ul_span=personality_ul_span,
        personality_entries=personality_entries,
        personality_lis=personality_lis,
        personality_slot_count=personality_slot_count,
        personality_read_only=personality_read_only,
        personality_read_only_reason=personality_reason,
    )


def _load_personalities(
    raw_html: bytes,
    personalities: list[dict[str, Any]],
    data_error: str,
) -> tuple[ElementSpan | None, tuple[PersonalityEntry, ...], tuple[LiSpan, ...], int, bool, str]:
    if data_error:
        return None, (), (), 0, True, data_error
    try:
        ul_span = find_unique_personality_ul(raw_html)
        lis = find_direct_personality_lis(raw_html, ul_span)
    except HtmlStructureError as exc:
        return None, (), (), 0, True, str(exc)

    if len(lis) != 6:
        return ul_span, (), tuple(lis), len(lis), True, (
            f"personality slot count mismatch: expected 6 direct li elements, found {len(lis)}"
        )
    if len(personalities) > len(lis):
        return ul_span, (), tuple(lis), len(lis), True, (
            f"personality count mismatch: JSON has {len(personalities)}, HTML has {len(lis)} direct li elements"
        )

    try:
        catalog = catalog_by_id(load_personality_catalog())
    except PersonalityCatalogError as exc:
        return ul_span, (), tuple(lis), len(lis), True, str(exc)
    entries: list[PersonalityEntry] = []
    seen_ids: set[int] = set()
    for index, keyword in enumerate(personalities):
        keyword_id = keyword.get("id")
        catalog_keyword = catalog.get(keyword_id) if isinstance(keyword_id, int) and not isinstance(keyword_id, bool) else None
        if catalog_keyword is None or keyword != catalog_keyword.as_dict():
            return ul_span, tuple(entries), tuple(lis), len(lis), True, (
                f"personality {index + 1} does not exactly match the bundled catalog"
            )
        if keyword_id in seen_ids:
            return ul_span, tuple(entries), tuple(lis), len(lis), True, (
                f"personality {index + 1} duplicates an earlier keyword"
            )
        seen_ids.add(keyword_id)
        li = lis[index]
        if li.attrs or text_content(li.inner) != catalog_keyword.name:
            return ul_span, tuple(entries), tuple(lis), len(lis), True, (
                f"JSON and HTML personality entries do not safely match at position {index + 1}"
            )
        entries.append(PersonalityEntry(index=index, keyword=keyword, li=li))

    for index, li in enumerate(lis[len(personalities) :], start=len(personalities)):
        if li.attrs or b"<" in li.inner or text_content(li.inner) != "":
            return ul_span, tuple(entries), tuple(lis), len(lis), True, (
                f"personality slot {index + 1} is not a safe empty slot"
            )
    return ul_span, tuple(entries), tuple(lis), len(lis), False, ""


def _position_consistent(skill: dict[str, Any], li: LiSpan) -> bool:
    if _json_empty_slot(skill):
        return li.attrs == {} and text_content(li.inner) in ("", "\xa0")

    checks = {
        "id": "data-skill-id",
        "name": "data-skill-name",
        "type": "data-skill-type",
        "description": "data-skill-description",
    }
    for json_key, attr_name in checks.items():
        json_value = skill.get(json_key, "")
        if json_value is None:
            json_value = ""
        if not isinstance(json_value, str):
            json_value = str(json_value)
        if li.attrs.get(attr_name, "") != json_value:
            return False
    return text_content(li.inner) == skill.get("name", "")


def _json_empty_slot(skill: dict[str, Any]) -> bool:
    return (
        skill.get("id") in ("", None)
        and skill.get("name") in ("", None)
        and skill.get("description") in ("", None)
        and skill.get("type") in ("", None)
        and skill.get("key") in ("", None)
    )


def _is_vacant_html_slot(li: LiSpan) -> bool:
    """Recognize an unassigned visual slot that has no JSON skill object."""

    return li.attrs == {} and b"<" not in li.inner and text_content(li.inner) == ""


def _missing_li() -> LiSpan:
    return LiSpan(0, 0, 0, 0, 0, 0, {}, b"", b"")
