"""JSON byte-span location helpers for the character sheet payload."""

from __future__ import annotations

from dataclasses import dataclass
import json


class JsonSpanError(ValueError):
    """Raised when a JSON byte span cannot be safely located."""


@dataclass(frozen=True)
class JsonValueSpan:
    start: int
    end: int


@dataclass(frozen=True)
class SkillsArraySpans:
    data_object: JsonValueSpan
    skills_array: JsonValueSpan
    skill_objects: list[JsonValueSpan]


@dataclass(frozen=True)
class ObjectArraySpans:
    data_object: JsonValueSpan
    array: JsonValueSpan
    objects: list[JsonValueSpan]


def locate_skills_array(json_bytes: bytes) -> SkillsArraySpans:
    located = locate_data_object_array(json_bytes, "skills")
    return SkillsArraySpans(
        data_object=located.data_object,
        skills_array=located.array,
        skill_objects=located.objects,
    )


def locate_personalities_array(json_bytes: bytes) -> ObjectArraySpans:
    return locate_data_object_array(json_bytes, "personalities")


def locate_data_object_array(json_bytes: bytes, key: str) -> ObjectArraySpans:
    data_span = find_object_key_value(json_bytes, "data", expected_start=b"{")
    array_span = find_object_key_value(
        json_bytes[data_span.start : data_span.end],
        key,
        expected_start=b"[",
    )
    absolute_array = JsonValueSpan(data_span.start + array_span.start, data_span.start + array_span.end)
    objects = [
        JsonValueSpan(absolute_array.start + span.start, absolute_array.start + span.end)
        for span in direct_array_object_spans(json_bytes[absolute_array.start : absolute_array.end])
    ]
    return ObjectArraySpans(data_object=data_span, array=absolute_array, objects=objects)


def find_object_key_value(object_bytes: bytes, key: str, *, expected_start: bytes | None = None) -> JsonValueSpan:
    if not object_bytes.lstrip().startswith(b"{"):
        raise JsonSpanError("target JSON value is not an object")

    i = 0
    depth = 0
    while i < len(object_bytes):
        byte = object_bytes[i]
        if byte == 0x22:
            string_start = i
            string_end = skip_string(object_bytes, i)
            if depth == 1:
                parsed_key = json.loads(object_bytes[string_start:string_end].decode("utf-8"))
                j = skip_ws(object_bytes, string_end)
                if parsed_key == key and j < len(object_bytes) and object_bytes[j] == 0x3A:
                    value_start = skip_ws(object_bytes, j + 1)
                    if expected_start is not None and object_bytes[value_start : value_start + 1] != expected_start:
                        raise JsonSpanError(f"field {key!r} does not start with {expected_start!r}")
                    value_end = skip_value(object_bytes, value_start)
                    return JsonValueSpan(value_start, value_end)
            i = string_end
            continue
        if byte in (0x7B, 0x5B):
            depth += 1
        elif byte in (0x7D, 0x5D):
            depth -= 1
        i += 1
    raise JsonSpanError(f"field {key!r} was not found")


def direct_array_object_spans(array_bytes: bytes) -> list[JsonValueSpan]:
    if not array_bytes.lstrip().startswith(b"["):
        raise JsonSpanError("target JSON value is not an array")

    start = array_bytes.find(b"[")
    end = matching_closer(array_bytes, start)
    spans: list[JsonValueSpan] = []
    i = start + 1
    while i < end - 1:
        i = skip_ws(array_bytes, i)
        if i >= end - 1:
            break
        if array_bytes[i] == 0x2C:
            i += 1
            continue
        if array_bytes[i] != 0x7B:
            raise JsonSpanError("array contains a non-object item")
        object_end = skip_value(array_bytes, i)
        spans.append(JsonValueSpan(i, object_end))
        i = skip_ws(array_bytes, object_end)
        if i < end - 1 and array_bytes[i] not in (0x2C,):
            raise JsonSpanError("expected comma after array item")
    return spans


def skip_value(data: bytes, start: int) -> int:
    if start >= len(data):
        raise JsonSpanError("missing JSON value")
    byte = data[start]
    if byte == 0x22:
        return skip_string(data, start)
    if byte in (0x7B, 0x5B):
        return matching_closer(data, start)
    i = start
    while i < len(data) and data[i] not in b",]} \r\n\t":
        i += 1
    if i == start:
        raise JsonSpanError("invalid JSON value")
    return i


def matching_closer(data: bytes, start: int) -> int:
    opener = data[start]
    closer = {0x7B: 0x7D, 0x5B: 0x5D}.get(opener)
    if closer is None:
        raise JsonSpanError("value is not an object or array")
    depth = 0
    i = start
    while i < len(data):
        byte = data[i]
        if byte == 0x22:
            i = skip_string(data, i)
            continue
        if byte == opener:
            depth += 1
        elif byte == closer:
            depth -= 1
            if depth == 0:
                return i + 1
        elif byte in (0x7B, 0x5B) and byte != opener:
            i = matching_closer(data, i)
            continue
        i += 1
    raise JsonSpanError("unterminated JSON container")


def skip_string(data: bytes, start: int) -> int:
    i = start + 1
    escaped = False
    while i < len(data):
        byte = data[i]
        if escaped:
            escaped = False
        elif byte == 0x5C:
            escaped = True
        elif byte == 0x22:
            return i + 1
        i += 1
    raise JsonSpanError("unterminated JSON string")


def skip_ws(data: bytes, start: int) -> int:
    i = start
    while i < len(data) and data[i] in b" \r\n\t":
        i += 1
    return i
