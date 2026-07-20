"""Patch simple skill ``li`` elements while preserving unrelated bytes."""

from __future__ import annotations

from dataclasses import dataclass
import html
import re

from saga_seeker_skill_editor.core.html_locator import LiSpan


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
