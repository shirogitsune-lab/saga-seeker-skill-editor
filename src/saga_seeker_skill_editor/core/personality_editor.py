"""Byte-preserving personality keyword edits."""

from __future__ import annotations

import html

from saga_seeker_skill_editor.core.character_sheet import CharacterSheet, load_character_sheet
from saga_seeker_skill_editor.core.json_span import ObjectArraySpans, locate_personalities_array
from saga_seeker_skill_editor.core.personality_catalog import PersonalityKeyword
from saga_seeker_skill_editor.core.script_safe_json import dumps_script_safe
from saga_seeker_skill_editor.core.sheet_editor import Replacement, SheetEditError, apply_replacements


def render_personality_assignment(
    sheet: CharacterSheet,
    *,
    index: int,
    keyword: PersonalityKeyword,
) -> bytes:
    """Replace one keyword or append it to the first available personality slot."""

    _require_editable(sheet)
    if index < 0 or index >= sheet.personality_slot_count:
        raise SheetEditError("personality slot index is out of range")
    if index > len(sheet.personality_entries):
        raise SheetEditError("personality keywords must be assigned without an empty middle slot")

    existing_ids = [entry.keyword["id"] for entry in sheet.personality_entries]
    if keyword.id in existing_ids and not (
        index < len(existing_ids) and existing_ids[index] == keyword.id
    ):
        raise SheetEditError("the selected personality keyword is already assigned")

    json_bytes = sheet.raw_html[sheet.script_span.content_start : sheet.script_span.content_end]
    spans = locate_personalities_array(json_bytes)
    if len(spans.objects) != len(sheet.personality_entries):
        raise SheetEditError("located personality object count does not match loaded entries")

    serialized = dumps_script_safe(keyword.as_dict())
    if index < len(spans.objects):
        object_span = spans.objects[index]
        json_replacement = Replacement(
            sheet.script_span.content_start + object_span.start,
            sheet.script_span.content_start + object_span.end,
            serialized,
        )
    else:
        json_replacement = _append_object_replacement(sheet, json_bytes, spans, serialized)

    li = sheet.personality_lis[index]
    html_name = html.escape(keyword.name, quote=False).encode("utf-8")
    updated = apply_replacements(
        sheet.raw_html,
        [
            json_replacement,
            Replacement(li.content_start, li.content_end, html_name),
        ],
    )
    _validate_personality(updated, index=index, keyword=keyword)
    return updated


def render_personality_tail_removal(sheet: CharacterSheet, *, index: int) -> bytes:
    """Remove the final assigned keyword and return its HTML slot to empty."""

    _require_editable(sheet)
    if index != len(sheet.personality_entries) - 1:
        raise SheetEditError("only the last assigned personality keyword can be removed")

    json_bytes = sheet.raw_html[sheet.script_span.content_start : sheet.script_span.content_end]
    spans = locate_personalities_array(json_bytes)
    if len(spans.objects) != len(sheet.personality_entries):
        raise SheetEditError("located personality object count does not match loaded entries")

    object_span = spans.objects[index]
    remove_start = object_span.start
    if index > 0:
        previous = spans.objects[index - 1]
        between = json_bytes[previous.end : object_span.start]
        if between.count(b",") != 1 or between.replace(b",", b"").strip():
            raise SheetEditError("cannot safely locate the personality array separator")
        remove_start = previous.end

    li = sheet.personality_lis[index]
    updated = apply_replacements(
        sheet.raw_html,
        [
            Replacement(
                sheet.script_span.content_start + remove_start,
                sheet.script_span.content_start + object_span.end,
                b"",
            ),
            Replacement(li.content_start, li.content_end, b"&nbsp;"),
        ],
    )
    rendered = load_character_sheet(updated)
    if rendered.personality_read_only:
        raise SheetEditError(
            f"rendered personality section is read-only: {rendered.personality_read_only_reason}"
        )
    if len(rendered.personality_entries) != len(sheet.personality_entries) - 1:
        raise SheetEditError("rendered personality array did not lose exactly one item")
    return updated


def render_personality_selections(
    sheet: CharacterSheet,
    *,
    keyword_ids: tuple[int | None, ...],
    catalog: tuple[PersonalityKeyword, ...],
) -> bytes:
    """Render a complete six-slot selection while retaining every unchanged object and li."""

    _require_editable(sheet)
    if len(keyword_ids) != sheet.personality_slot_count:
        raise SheetEditError("personality selection count does not match the HTML slot count")
    first_empty = next((index for index, value in enumerate(keyword_ids) if value is None), len(keyword_ids))
    if any(value is not None for value in keyword_ids[first_empty:]):
        raise SheetEditError("personality keywords must be assigned without an empty middle slot")
    selected_ids = tuple(value for value in keyword_ids[:first_empty] if value is not None)
    if len(selected_ids) != len(set(selected_ids)):
        raise SheetEditError("the same personality keyword cannot be assigned more than once")

    by_id = {keyword.id: keyword for keyword in catalog}
    try:
        selected = tuple(by_id[keyword_id] for keyword_id in selected_ids)
    except KeyError as exc:
        raise SheetEditError(f"personality keyword id is not in the catalog: {exc.args[0]}") from exc

    json_bytes = sheet.raw_html[sheet.script_span.content_start : sheet.script_span.content_end]
    spans = locate_personalities_array(json_bytes)
    if len(spans.objects) != len(sheet.personality_entries):
        raise SheetEditError("located personality object count does not match loaded entries")

    replacements: list[Replacement] = []
    common_count = min(len(spans.objects), len(selected))
    for index in range(common_count):
        keyword = selected[index]
        if sheet.personality_entries[index].keyword == keyword.as_dict():
            continue
        object_span = spans.objects[index]
        replacements.append(
            Replacement(
                sheet.script_span.content_start + object_span.start,
                sheet.script_span.content_start + object_span.end,
                dumps_script_safe(keyword.as_dict()),
            )
        )
        li = sheet.personality_lis[index]
        replacements.append(
            Replacement(li.content_start, li.content_end, html.escape(keyword.name, quote=False).encode("utf-8"))
        )

    if len(selected) > len(spans.objects):
        serialized = [dumps_script_safe(keyword.as_dict()) for keyword in selected[len(spans.objects) :]]
        replacements.append(_append_objects_replacement(sheet, json_bytes, spans, serialized))
        for index in range(len(spans.objects), len(selected)):
            li = sheet.personality_lis[index]
            replacements.append(
                Replacement(
                    li.content_start,
                    li.content_end,
                    html.escape(selected[index].name, quote=False).encode("utf-8"),
                )
            )
    elif len(selected) < len(spans.objects):
        replacements.append(_remove_trailing_objects_replacement(sheet, json_bytes, spans, len(selected)))
        for index in range(len(selected), len(spans.objects)):
            li = sheet.personality_lis[index]
            replacements.append(Replacement(li.content_start, li.content_end, b"&nbsp;"))

    if not replacements:
        return sheet.raw_html
    updated = apply_replacements(sheet.raw_html, replacements)
    rendered = load_character_sheet(updated)
    if rendered.personality_read_only:
        raise SheetEditError(
            f"rendered personality section is read-only: {rendered.personality_read_only_reason}"
        )
    if tuple(entry.keyword for entry in rendered.personality_entries) != tuple(
        keyword.as_dict() for keyword in selected
    ):
        raise SheetEditError("rendered personality selections do not match the requested catalog entries")
    return updated


def _append_object_replacement(
    sheet: CharacterSheet,
    json_bytes: bytes,
    spans: ObjectArraySpans,
    serialized: bytes,
) -> Replacement:
    array_close = spans.array.end - 1
    if spans.objects:
        last = spans.objects[-1]
        trailing_ws = json_bytes[last.end : array_close]
        if trailing_ws.strip():
            raise SheetEditError("personality array has unexpected bytes before its closing bracket")
        separator = trailing_ws if trailing_ws else b" "
        return Replacement(
            sheet.script_span.content_start + last.end,
            sheet.script_span.content_start + last.end,
            b"," + separator + serialized,
        )

    body_start = spans.array.start + 1
    body = json_bytes[body_start:array_close]
    if body.strip():
        raise SheetEditError("empty personality array contains unexpected bytes")
    value = body + serialized + body if body else serialized
    return Replacement(
        sheet.script_span.content_start + body_start,
        sheet.script_span.content_start + array_close,
        value,
    )


def _append_objects_replacement(
    sheet: CharacterSheet,
    json_bytes: bytes,
    spans: ObjectArraySpans,
    serialized: list[bytes],
) -> Replacement:
    if not serialized:
        raise SheetEditError("no personality objects were supplied for insertion")
    array_close = spans.array.end - 1
    if spans.objects:
        last = spans.objects[-1]
        trailing_ws = json_bytes[last.end : array_close]
        if trailing_ws.strip():
            raise SheetEditError("personality array has unexpected bytes before its closing bracket")
        separator = trailing_ws if trailing_ws else b" "
        value = b"".join(b"," + separator + item for item in serialized)
        return Replacement(
            sheet.script_span.content_start + last.end,
            sheet.script_span.content_start + last.end,
            value,
        )

    body_start = spans.array.start + 1
    body = json_bytes[body_start:array_close]
    if body.strip():
        raise SheetEditError("empty personality array contains unexpected bytes")
    separator = body if body else b" "
    joined = (b"," + separator).join(serialized)
    value = body + joined + body if body else joined
    return Replacement(
        sheet.script_span.content_start + body_start,
        sheet.script_span.content_start + array_close,
        value,
    )


def _remove_trailing_objects_replacement(
    sheet: CharacterSheet,
    json_bytes: bytes,
    spans: ObjectArraySpans,
    keep_count: int,
) -> Replacement:
    if keep_count < 0 or keep_count >= len(spans.objects):
        raise SheetEditError("invalid personality object removal count")
    if keep_count == 0:
        start = spans.objects[0].start
    else:
        previous = spans.objects[keep_count - 1]
        first_removed = spans.objects[keep_count]
        between = json_bytes[previous.end : first_removed.start]
        if between.count(b",") != 1 or between.replace(b",", b"").strip():
            raise SheetEditError("cannot safely locate the personality array separator")
        start = previous.end
    return Replacement(
        sheet.script_span.content_start + start,
        sheet.script_span.content_start + spans.objects[-1].end,
        b"",
    )


def _require_editable(sheet: CharacterSheet) -> None:
    if sheet.read_only:
        raise SheetEditError(f"sheet is read-only: {sheet.read_only_reason}")
    if sheet.personality_read_only:
        raise SheetEditError(
            f"personality section is read-only: {sheet.personality_read_only_reason}"
        )


def _validate_personality(updated: bytes, *, index: int, keyword: PersonalityKeyword) -> None:
    rendered = load_character_sheet(updated)
    if rendered.personality_read_only:
        raise SheetEditError(
            f"rendered personality section is read-only: {rendered.personality_read_only_reason}"
        )
    if rendered.personality_entries[index].keyword != keyword.as_dict():
        raise SheetEditError("rendered personality JSON does not match the selected keyword")
    if rendered.personality_entries[index].li.inner.decode("utf-8") != html.escape(keyword.name, quote=False):
        raise SheetEditError("rendered personality HTML does not match the selected keyword")
