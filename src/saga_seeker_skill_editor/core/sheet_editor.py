"""High-level sheet edit rendering."""

from __future__ import annotations

from dataclasses import dataclass

from saga_seeker_skill_editor.core.character_sheet import CharacterSheet, load_character_sheet
from saga_seeker_skill_editor.core.html_li_patcher import (
    LiSkillPatch,
    LiTextPatch,
    build_new_skill_li,
    build_patched_simple_skill_li,
    build_patched_skill_li,
    build_vacant_skill_li,
)
from saga_seeker_skill_editor.core.json_span import SkillsArraySpans, locate_skills_array
from saga_seeker_skill_editor.core.json_token_patcher import replace_string_fields_in_object
from saga_seeker_skill_editor.core.script_safe_json import dumps_script_safe
from saga_seeker_skill_editor.core.skill_classifier import SkillKind, next_unused_sk_id


class SheetEditError(ValueError):
    """Raised when an edit cannot be safely rendered."""


@dataclass(frozen=True)
class Replacement:
    start: int
    end: int
    value: bytes


def render_name_description_edit(
    sheet: CharacterSheet,
    *,
    index: int,
    name: str,
    description: str,
    repair_id_confirmed: bool = False,
) -> bytes:
    """Render a safe edit of an existing original skill's name/description."""

    if sheet.read_only:
        raise SheetEditError(f"sheet is read-only: {sheet.read_only_reason}")
    if index < 0 or index >= len(sheet.entries):
        raise SheetEditError("skill index is out of range")

    entry = sheet.entries[index]
    if entry.classification.kind not in (SkillKind.ORIGINAL, SkillKind.ORIGINAL_NEEDS_ID_REPAIR):
        raise SheetEditError("only original skills can be edited with this operation")
    if entry.classification.needs_id_repair and not repair_id_confirmed:
        raise SheetEditError("this skill requires explicit id repair consent before editing")

    json_bytes = sheet.raw_html[sheet.script_span.content_start : sheet.script_span.content_end]
    spans = locate_skills_array(json_bytes)
    if len(spans.skill_objects) != len(sheet.entries):
        raise SheetEditError("located JSON skill object count does not match loaded entries")

    object_span = spans.skill_objects[index]
    object_bytes = json_bytes[object_span.start : object_span.end]
    replacements_for_json = {"name": name, "description": description}
    repaired_id = None
    if entry.classification.needs_id_repair:
        repaired_id = next_unused_sk_id([loaded_entry.skill for loaded_entry in sheet.entries])
        replacements_for_json["id"] = repaired_id

    patched_object = replace_string_fields_in_object(object_bytes, replacements_for_json)
    if repaired_id is None:
        patched_li = build_patched_simple_skill_li(
            sheet.raw_html,
            entry.li,
            LiTextPatch(name=name, description=description),
        )
    else:
        patched_li = build_patched_skill_li(
            sheet.raw_html,
            entry.li,
            LiSkillPatch(skill_id=repaired_id, name=name, skill_type="", description=description),
        )

    replacements = [
        Replacement(
            sheet.script_span.content_start + object_span.start,
            sheet.script_span.content_start + object_span.end,
            patched_object,
        ),
        Replacement(entry.li.start, entry.li.end, patched_li),
    ]
    updated = apply_replacements(sheet.raw_html, replacements)
    _validate_rendered(updated, index=index, expected_name=name, expected_description=description)
    return updated


def render_protected_skill_replacement(
    sheet: CharacterSheet,
    *,
    index: int,
    name: str,
    description: str,
    first_confirmation: bool,
    second_confirmation: bool,
) -> bytes:
    """Render an advanced replacement of a protected default skill with an original skill."""

    if sheet.read_only:
        raise SheetEditError(f"sheet is read-only: {sheet.read_only_reason}")
    if not (first_confirmation and second_confirmation):
        raise SheetEditError("protected skill replacement requires two confirmations")
    if index < 0 or index >= len(sheet.entries):
        raise SheetEditError("skill index is out of range")
    entry = sheet.entries[index]
    if entry.classification.kind != SkillKind.DEFAULT:
        raise SheetEditError("only default skills can be replaced with this operation")

    json_bytes = sheet.raw_html[sheet.script_span.content_start : sheet.script_span.content_end]
    spans = locate_skills_array(json_bytes)
    if len(spans.skill_objects) != len(sheet.entries):
        raise SheetEditError("located JSON skill object count does not match loaded entries")

    new_id = next_unused_sk_id([loaded_entry.skill for loaded_entry in sheet.entries])
    replacement_object = {
        "id": new_id,
        "name": name,
        "description": description,
        "type": "",
        "key": "",
    }
    patched_object = dumps_script_safe(replacement_object, indent=8)
    object_span = spans.skill_objects[index]
    patched_li = build_patched_skill_li(
        sheet.raw_html,
        entry.li,
        LiSkillPatch(skill_id=new_id, name=name, skill_type="", description=description),
    )
    replacements = [
        Replacement(
            sheet.script_span.content_start + object_span.start,
            sheet.script_span.content_start + object_span.end,
            patched_object,
        ),
        Replacement(entry.li.start, entry.li.end, patched_li),
    ]
    updated = apply_replacements(sheet.raw_html, replacements)
    _validate_rendered(updated, index=index, expected_name=name, expected_description=description)
    return updated


def render_empty_slot_creation(
    sheet: CharacterSheet,
    *,
    index: int,
    name: str,
    description: str,
) -> bytes:
    """Render creation of a manual original skill in an empty slot."""

    if sheet.read_only:
        raise SheetEditError(f"sheet is read-only: {sheet.read_only_reason}")
    if index < 0 or index >= len(sheet.entries):
        raise SheetEditError("skill index is out of range")
    if name == "":
        raise SheetEditError("skill name is required for an empty slot")
    entry = sheet.entries[index]
    if entry.classification.kind != SkillKind.EMPTY_SLOT:
        raise SheetEditError("only empty slots can be created with this operation")

    json_bytes = sheet.raw_html[sheet.script_span.content_start : sheet.script_span.content_end]
    spans = locate_skills_array(json_bytes)
    if len(spans.skill_objects) != len(sheet.entries):
        raise SheetEditError("located JSON skill object count does not match loaded entries")

    existing_id = entry.skill.get("id")
    skill_id = existing_id if isinstance(existing_id, str) and existing_id != "" else next_unused_sk_id(
        [loaded_entry.skill for loaded_entry in sheet.entries]
    )
    object_span = spans.skill_objects[index]
    object_bytes = json_bytes[object_span.start : object_span.end]
    patched_object = replace_string_fields_in_object(
        object_bytes,
        {
            "id": skill_id,
            "name": name,
            "description": description,
            "type": "",
            "key": "",
        },
    )
    patched_li = build_new_skill_li(
        LiSkillPatch(skill_id=skill_id, name=name, skill_type="", description=description)
    )
    replacements = [
        Replacement(
            sheet.script_span.content_start + object_span.start,
            sheet.script_span.content_start + object_span.end,
            patched_object,
        ),
        Replacement(entry.li.start, entry.li.end, patched_li),
    ]
    updated = apply_replacements(sheet.raw_html, replacements)
    _validate_rendered(updated, index=index, expected_name=name, expected_description=description)
    return updated


def render_vacant_slot_creation(
    sheet: CharacterSheet,
    *,
    name: str,
    description: str,
) -> bytes:
    """Append one original skill into the first unassigned visual slot."""

    if sheet.read_only:
        raise SheetEditError(f"sheet is read-only: {sheet.read_only_reason}")
    if name == "":
        raise SheetEditError("skill name is required for a vacant slot")
    if not sheet.vacant_lis:
        raise SheetEditError("sheet has no vacant skill slot")

    json_bytes = sheet.raw_html[sheet.script_span.content_start : sheet.script_span.content_end]
    spans = locate_skills_array(json_bytes)
    if len(spans.skill_objects) != len(sheet.entries):
        raise SheetEditError("located JSON skill object count does not match loaded entries")

    new_id = next_unused_sk_id([loaded_entry.skill for loaded_entry in sheet.entries])
    new_object = dumps_script_safe(
        {
            "id": new_id,
            "name": name,
            "description": description,
            "type": "",
            "key": "",
        }
    )
    json_replacement = _append_skill_object_replacement(sheet, json_bytes, spans, new_object)
    vacant_li = sheet.vacant_lis[0]
    patched_li = build_new_skill_li(
        LiSkillPatch(skill_id=new_id, name=name, skill_type="", description=description)
    )
    updated = apply_replacements(
        sheet.raw_html,
        [
            json_replacement,
            Replacement(vacant_li.start, vacant_li.end, patched_li),
        ],
    )
    _validate_rendered(
        updated,
        index=len(sheet.entries),
        expected_name=name,
        expected_description=description,
    )
    rendered = load_character_sheet(updated)
    if len(rendered.entries) != len(sheet.entries) + 1:
        raise SheetEditError("rendered sheet did not gain exactly one skill")
    if rendered.vacant_slot_count != sheet.vacant_slot_count - 1:
        raise SheetEditError("rendered sheet vacant slot count is inconsistent")
    return updated


def render_skill_deletion(sheet: CharacterSheet, *, index: int) -> bytes:
    """Delete one skill, using an explicit empty skill when it is not the tail."""

    if sheet.read_only:
        raise SheetEditError(f"sheet is read-only: {sheet.read_only_reason}")
    if index < 0 or index >= len(sheet.entries):
        raise SheetEditError("skill index is out of range")
    entry = sheet.entries[index]
    if entry.classification.kind == SkillKind.UNKNOWN:
        raise SheetEditError("unrecognized skills cannot be deleted")

    json_bytes = sheet.raw_html[sheet.script_span.content_start : sheet.script_span.content_end]
    spans = locate_skills_array(json_bytes)
    if len(spans.skill_objects) != len(sheet.entries):
        raise SheetEditError("located JSON skill object count does not match loaded entries")

    if index == len(sheet.entries) - 1:
        json_replacement = _remove_tail_skill_object_replacement(sheet, json_bytes, spans, index)
    else:
        empty_object = dumps_script_safe(
            {
                "id": "",
                "name": "",
                "description": "",
                "type": "",
                "key": "__ce2_empty_slot__",
            }
        )
        object_span = spans.skill_objects[index]
        json_replacement = Replacement(
            sheet.script_span.content_start + object_span.start,
            sheet.script_span.content_start + object_span.end,
            empty_object,
        )

    updated = apply_replacements(
        sheet.raw_html,
        [
            json_replacement,
            Replacement(entry.li.start, entry.li.end, build_vacant_skill_li()),
        ],
    )
    rendered = load_character_sheet(updated)
    if rendered.read_only:
        raise SheetEditError(f"rendered sheet is read-only: {rendered.read_only_reason}")
    if index == len(sheet.entries) - 1:
        if len(rendered.entries) != len(sheet.entries) - 1:
            raise SheetEditError("tail deletion did not remove exactly one JSON skill")
        if rendered.vacant_slot_count != sheet.vacant_slot_count + 1:
            raise SheetEditError("tail deletion did not create exactly one vacant slot")
    elif rendered.entries[index].classification.kind != SkillKind.EMPTY_SLOT:
        raise SheetEditError("middle deletion did not create an explicit empty skill")
    return updated


def apply_replacements(raw: bytes, replacements: list[Replacement]) -> bytes:
    ordered = sorted(replacements, key=lambda replacement: replacement.start, reverse=True)
    updated = raw
    previous_start = len(raw) + 1
    for replacement in ordered:
        if replacement.end > previous_start:
            raise SheetEditError("replacement ranges overlap")
        if replacement.start < 0 or replacement.end < replacement.start or replacement.end > len(raw):
            raise SheetEditError("replacement range is invalid")
        updated = updated[: replacement.start] + replacement.value + updated[replacement.end :]
        previous_start = replacement.start
    return updated


def _append_skill_object_replacement(
    sheet: CharacterSheet,
    json_bytes: bytes,
    spans: SkillsArraySpans,
    new_object: bytes,
) -> Replacement:
    array_close = spans.skills_array.end - 1
    if spans.skill_objects:
        last_object = spans.skill_objects[-1]
        trailing_ws = json_bytes[last_object.end : array_close]
        if trailing_ws.strip():
            raise SheetEditError("skills array has unexpected bytes before its closing bracket")
        separator = trailing_ws if trailing_ws else b" "
        return Replacement(
            sheet.script_span.content_start + last_object.end,
            sheet.script_span.content_start + last_object.end,
            b"," + separator + new_object,
        )

    array_body_start = spans.skills_array.start + 1
    body = json_bytes[array_body_start:array_close]
    if body.strip():
        raise SheetEditError("empty skills array contains unexpected bytes")
    value = body + new_object + body if body else new_object
    return Replacement(
        sheet.script_span.content_start + array_body_start,
        sheet.script_span.content_start + array_close,
        value,
    )


def _remove_tail_skill_object_replacement(
    sheet: CharacterSheet,
    json_bytes: bytes,
    spans: SkillsArraySpans,
    index: int,
) -> Replacement:
    object_span = spans.skill_objects[index]
    start = object_span.start
    if index > 0:
        previous = spans.skill_objects[index - 1]
        between = json_bytes[previous.end : object_span.start]
        if between.count(b",") != 1 or between.replace(b",", b"").strip():
            raise SheetEditError("cannot safely locate the separator before the last skill")
        start = previous.end
    return Replacement(
        sheet.script_span.content_start + start,
        sheet.script_span.content_start + object_span.end,
        b"",
    )


def _validate_rendered(updated: bytes, *, index: int, expected_name: str, expected_description: str) -> None:
    rendered_sheet = load_character_sheet(updated)
    if rendered_sheet.read_only:
        raise SheetEditError(f"rendered sheet is read-only: {rendered_sheet.read_only_reason}")
    rendered_skill = rendered_sheet.entries[index].skill
    if rendered_skill.get("name") != expected_name:
        raise SheetEditError("rendered JSON name does not match input")
    if rendered_skill.get("description") != expected_description:
        raise SheetEditError("rendered JSON description does not match input")
    rendered_li = rendered_sheet.entries[index].li
    if rendered_li.attrs.get("data-skill-name") != expected_name:
        raise SheetEditError("rendered HTML skill name does not match input")
    if rendered_li.attrs.get("data-skill-description") != expected_description:
        raise SheetEditError("rendered HTML skill description does not match input")
