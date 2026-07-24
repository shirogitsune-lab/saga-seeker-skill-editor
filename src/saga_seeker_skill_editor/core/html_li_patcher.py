"""Patch simple skill ``li`` elements while preserving unrelated bytes."""

from __future__ import annotations

from dataclasses import dataclass
import html
import json
import re

from saga_seeker_skill_editor.core.html_locator import LiSpan, StartTagSpan


class LiPatchError(ValueError):
    """Raised when an li cannot be safely patched without full reserialization."""


@dataclass(frozen=True)
class LiTextPatch:
    name: str
    description: str


@dataclass(frozen=True)
class LiSkillPatch:
    skill_id: str
    name: str
    skill_type: str
    description: str


def escape_attr_value(value: str) -> str:
    return html.escape(value, quote=True).replace("'", "&#x27;")


def escape_text(value: str) -> str:
    return html.escape(value, quote=False)


def patch_simple_skill_li(raw_html: bytes, li: LiSpan, patch: LiTextPatch) -> bytes:
    """Patch data-skill-name, data-skill-description, and simple text content."""

    patched_li = build_patched_simple_skill_li(raw_html, li, patch)
    return raw_html[: li.start] + patched_li + raw_html[li.end :]


def build_patched_simple_skill_li(raw_html: bytes, li: LiSpan, patch: LiTextPatch) -> bytes:
    """Build patched bytes for a single simple li element."""

    return build_patched_skill_li(
        raw_html,
        li,
        LiSkillPatch(
            skill_id=li.attrs.get("data-skill-id", ""),
            name=patch.name,
            skill_type=li.attrs.get("data-skill-type", ""),
            description=patch.description,
        ),
    )


def build_patched_skill_li(raw_html: bytes, li: LiSpan, patch: LiSkillPatch) -> bytes:
    """Build patched bytes for a skill li element while preserving unknown attrs."""

    raw_li = raw_html[li.start : li.end]
    start_tag = raw_html[li.start_tag_start : li.start_tag_end]
    inner = raw_html[li.content_start : li.content_end]
    end_tag = raw_html[li.content_end : li.end]

    if b"<" in inner or b">" in inner:
        raise LiPatchError("skill li has nested or complex HTML content")

    patched_start = _replace_attr(start_tag, "data-skill-id", escape_attr_value(patch.skill_id))
    patched_start = _replace_attr(patched_start, "data-skill-name", escape_attr_value(patch.name))
    patched_start = _replace_attr(patched_start, "data-skill-type", escape_attr_value(patch.skill_type))
    patched_start = _replace_attr(
        patched_start,
        "data-skill-description",
        escape_attr_value(patch.description),
    )
    patched_inner = escape_text(patch.name).encode("utf-8")
    return patched_start + patched_inner + end_tag


def build_new_skill_li(patch: LiSkillPatch) -> bytes:
    return (
        b'<li data-skill-id="'
        + escape_attr_value(patch.skill_id).encode("utf-8")
        + b'" data-skill-name="'
        + escape_attr_value(patch.name).encode("utf-8")
        + b'" data-skill-type="'
        + escape_attr_value(patch.skill_type).encode("utf-8")
        + b'" data-skill-description="'
        + escape_attr_value(patch.description).encode("utf-8")
        + b'">'
        + escape_text(patch.name).encode("utf-8")
        + b"</li>"
    )


def build_vacant_skill_li() -> bytes:
    """Build the canonical attribute-free visual slot used by official sheets."""

    return b"<li>&nbsp;</li>"


def build_patched_memory_li(
    raw_html: bytes,
    li: LiSpan,
    *,
    field: str,
    value: str,
) -> bytes:
    """Patch one known memory attribute while retaining unknown attributes."""

    return build_patched_memory_li_fields(
        raw_html,
        li,
        replacements={field: value},
    )


def build_patched_memory_li_fields(
    raw_html: bytes,
    li: LiSpan,
    *,
    replacements: dict[str, str | list[str]],
) -> bytes:
    """Patch selected memory attributes while retaining every other byte."""

    attr_names = {
        "title": "data-memory-title",
        "summary": "data-memory-summary",
        "location": "data-memory-location",
        "intent": "data-memory-intent",
        "outcome": "data-memory-outcome",
        "tags": "data-memory-tags",
    }
    start_tag = raw_html[li.start_tag_start : li.start_tag_end]
    inner = raw_html[li.content_start : li.content_end]
    end_tag = raw_html[li.content_end : li.end]
    if b"<" in inner or b">" in inner:
        raise LiPatchError("memory li has nested or complex HTML content")
    patched_start = start_tag
    for field, value in replacements.items():
        attr_name = attr_names.get(field)
        if attr_name is None:
            raise LiPatchError(f"unsupported memory field: {field}")
        if field == "tags":
            if not isinstance(value, list) or not all(
                isinstance(tag, str) for tag in value
            ):
                raise LiPatchError("memory tags must be a list of strings")
            encoded_value = json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        elif isinstance(value, str):
            encoded_value = value
        else:
            raise LiPatchError(f"memory field {field} must be a string")
        patched_start = _replace_attr(
            patched_start,
            attr_name,
            escape_attr_value(encoded_value),
        )
    title = replacements.get("title")
    patched_inner = (
        escape_text(title).encode("utf-8") if isinstance(title, str) else inner
    )
    return patched_start + patched_inner + end_tag


def build_new_memory_li(memory: dict[str, object]) -> bytes:
    """Build the canonical visual slot for a validated memory object."""

    if memory.get("isPlaceholder") is True:
        return b"<li>&nbsp;</li>"
    string_fields = ("id", "title", "summary", "location", "intent", "outcome")
    if any(not isinstance(memory.get(field), str) for field in string_fields):
        raise LiPatchError("memory text fields must be strings")
    tags = memory.get("tags")
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise LiPatchError("memory tags must be a list of strings")
    attrs = (
        ("data-memory-id", memory["id"]),
        ("data-memory-title", memory["title"]),
        ("data-memory-summary", memory["summary"]),
        ("data-memory-location", memory["location"]),
        ("data-memory-intent", memory["intent"]),
        ("data-memory-outcome", memory["outcome"]),
        (
            "data-memory-tags",
            json.dumps(tags, ensure_ascii=False, separators=(",", ":")),
        ),
    )
    start = "<li " + " ".join(
        f'{name}="{escape_attr_value(value)}"' for name, value in attrs
    ) + ">"
    return (
        start.encode("utf-8")
        + escape_text(memory["title"]).encode("utf-8")
        + b"</li>"
    )


def build_patched_start_tag_attr(
    raw_html: bytes,
    span: StartTagSpan,
    *,
    attr_name: str,
    value: str,
) -> bytes:
    """Patch one double-quoted attribute while preserving the rest of the tag."""

    start_tag = raw_html[span.start : span.end]
    return _replace_attr(start_tag, attr_name, escape_attr_value(value))


def _replace_attr(start_tag: bytes, attr_name: str, escaped_value: str) -> bytes:
    pattern = re.compile(
        rb"(" + re.escape(attr_name.encode("ascii")) + rb"\s*=\s*)([\"'])(.*?)(\2)",
        re.S,
    )
    matches = list(pattern.finditer(start_tag))
    if len(matches) != 1:
        raise LiPatchError(f"expected exactly one {attr_name} attribute")
    match = matches[0]
    quote = match.group(2)
    if quote != b'"':
        raise LiPatchError(f"{attr_name} must use double quotes for safe patching")
    return start_tag[: match.start(3)] + escaped_value.encode("utf-8") + start_tag[match.end(3) :]
