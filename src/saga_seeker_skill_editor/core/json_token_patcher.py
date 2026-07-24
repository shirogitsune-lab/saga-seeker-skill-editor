"""Small JSON token patching helpers.

These helpers operate on one JSON object at a time. They intentionally do not
serialize enclosing arrays or unrelated objects.
"""

from __future__ import annotations

from dataclasses import dataclass

from saga_seeker_skill_editor.core.script_safe_json import dumps_script_safe_string
from saga_seeker_skill_editor.core.json_span import (
    JsonSpanError,
    find_object_key_value,
)


class JsonPatchError(ValueError):
    """Raised when a JSON token cannot be safely patched."""


@dataclass(frozen=True)
class TokenSpan:
    start: int
    end: int


def replace_string_fields_in_object(object_bytes: bytes, replacements: dict[str, str]) -> bytes:
    """Replace top-level string value tokens in a JSON object byte slice."""

    spans = {field: find_top_level_string_value(object_bytes, field) for field in replacements}
    chunks: list[bytes] = []
    cursor = 0
    for field, span in sorted(spans.items(), key=lambda item: item[1].start):
        chunks.append(object_bytes[cursor : span.start])
        chunks.append(dumps_script_safe_string(replacements[field]))
        cursor = span.end
    chunks.append(object_bytes[cursor:])
    return b"".join(chunks)


def replace_value_fields_in_object(
    object_bytes: bytes,
    replacements: dict[str, bytes],
) -> bytes:
    """Replace selected top-level JSON value tokens with pre-encoded safe tokens."""

    spans: dict[str, TokenSpan] = {}
    for field in replacements:
        try:
            span = find_object_key_value(object_bytes, field)
        except JsonSpanError as exc:
            raise JsonPatchError(str(exc)) from exc
        spans[field] = TokenSpan(span.start, span.end)
    chunks: list[bytes] = []
    cursor = 0
    for field, span in sorted(spans.items(), key=lambda item: item[1].start):
        chunks.append(object_bytes[cursor : span.start])
        chunks.append(replacements[field])
        cursor = span.end
    chunks.append(object_bytes[cursor:])
    return b"".join(chunks)


def find_top_level_string_value(object_bytes: bytes, field_name: str) -> TokenSpan:
    if not object_bytes.lstrip().startswith(b"{"):
        raise JsonPatchError("target is not a JSON object")

    i = 0
    depth = 0
    while i < len(object_bytes):
        byte = object_bytes[i]
        if byte == 0x22:
            string_start = i
            string_end = _skip_string(object_bytes, i)
            if depth == 1:
                key = _decode_string_token(object_bytes[string_start:string_end])
                j = _skip_ws(object_bytes, string_end)
                if key == field_name and j < len(object_bytes) and object_bytes[j] == 0x3A:
                    value_start = _skip_ws(object_bytes, j + 1)
                    if value_start >= len(object_bytes) or object_bytes[value_start] != 0x22:
                        raise JsonPatchError(f"field {field_name!r} is not a JSON string token")
                    value_end = _skip_string(object_bytes, value_start)
                    return TokenSpan(value_start, value_end)
            i = string_end
            continue
        if byte == 0x7B or byte == 0x5B:
            depth += 1
        elif byte == 0x7D or byte == 0x5D:
            depth -= 1
        i += 1
    raise JsonPatchError(f"field {field_name!r} was not found")


def _skip_string(data: bytes, start: int) -> int:
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
    raise JsonPatchError("unterminated JSON string")


def _decode_string_token(token: bytes) -> str:
    import json

    return json.loads(token.decode("utf-8"))


def _skip_ws(data: bytes, start: int) -> int:
    i = start
    while i < len(data) and data[i] in b" \r\n\t":
        i += 1
    return i
