"""Skill classification rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from collections import Counter
from typing import Any


class SkillKind(str, Enum):
    UNKNOWN = "unknown"
    EMPTY_SLOT = "empty_slot"
    DEFAULT = "default"
    ORIGINAL = "original"
    ORIGINAL_NEEDS_ID_REPAIR = "original_needs_id_repair"


@dataclass(frozen=True)
class SkillClassification:
    kind: SkillKind
    editable: bool
    needs_id_repair: bool = False
    reason: str = ""


def classify_skill(
    skill: dict[str, Any],
    *,
    position_consistent: bool,
    duplicate_ids: set[str],
) -> SkillClassification:
    """Classify a skill using the fixed safe order from the implementation plan."""

    if not position_consistent:
        return SkillClassification(SkillKind.UNKNOWN, editable=False, reason="json/html mismatch")

    name = skill.get("name")
    description = skill.get("description")
    skill_id = skill.get("id")
    skill_type = skill.get("type")
    key = skill.get("key")

    if _is_empty_slot(name, description, skill_type, key):
        return SkillClassification(SkillKind.EMPTY_SLOT, editable=True, reason="empty slot")

    if _is_default(name, description, skill_type, key):
        return SkillClassification(SkillKind.DEFAULT, editable=False, reason="protected default skill")

    if _looks_like_original(name, description, skill_type, key):
        if not isinstance(skill_id, str) or skill_id == "" or skill_id in duplicate_ids:
            return SkillClassification(
                SkillKind.ORIGINAL_NEEDS_ID_REPAIR,
                editable=True,
                needs_id_repair=True,
                reason="original skill requires id repair before saving edits",
            )
        return SkillClassification(SkillKind.ORIGINAL, editable=True, reason="original skill")

    return SkillClassification(SkillKind.UNKNOWN, editable=False, reason="unrecognized field combination")


def duplicate_string_ids(skills: list[dict[str, Any]]) -> set[str]:
    ids = [skill.get("id") for skill in skills if isinstance(skill.get("id"), str) and skill.get("id") != ""]
    counts = Counter(ids)
    return {skill_id for skill_id, count in counts.items() if count > 1}


def next_unused_sk_id(skills: list[dict[str, Any]]) -> str:
    used = {skill.get("id") for skill in skills if isinstance(skill.get("id"), str)}
    number = 1
    while f"sk{number}" in used:
        number += 1
    return f"sk{number}"


def _is_empty_slot(name: Any, description: Any, skill_type: Any, key: Any) -> bool:
    return (
        name in ("", None)
        and description in ("", None)
        and skill_type in ("", None)
        and key in ("", None, "__ce2_empty_slot__")
    )


def _is_default(name: Any, description: Any, skill_type: Any, key: Any) -> bool:
    if not isinstance(name, str) or not isinstance(description, str):
        return False
    return (isinstance(skill_type, str) and skill_type != "") or (isinstance(key, str) and key != "")


def _looks_like_original(name: Any, description: Any, skill_type: Any, key: Any) -> bool:
    return (
        isinstance(name, str)
        and name != ""
        and isinstance(description, str)
        and skill_type in ("", None)
        and key in ("", None)
    )
