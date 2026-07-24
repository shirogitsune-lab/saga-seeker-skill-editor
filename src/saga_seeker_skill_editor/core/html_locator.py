"""Byte-oriented HTML locators for the limited Saga & Seeker sheet surface."""

from __future__ import annotations

from dataclasses import dataclass
import html
import re


class HtmlStructureError(ValueError):
    """Raised when the target HTML structure is missing or ambiguous."""


@dataclass(frozen=True)
class ElementSpan:
    start: int
    end: int
    start_tag_start: int
    start_tag_end: int
    content_start: int
    content_end: int
    end_tag_start: int
    end_tag_end: int


@dataclass(frozen=True)
class LiSpan:
    start: int
    end: int
    start_tag_start: int
    start_tag_end: int
    content_start: int
    content_end: int
    attrs: dict[str, str]
    raw: bytes
    inner: bytes


@dataclass(frozen=True)
class StartTagSpan:
    start: int
    end: int
    attrs: dict[str, str]
    raw: bytes


_TAG_RE = re.compile(rb"<\s*(/)?\s*([A-Za-z][A-Za-z0-9:-]*)([^<>]*)>")
_ATTR_RE = re.compile(
    rb"""([^\s"'<>/=]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))""",
    re.S,
)


def parse_attrs(raw_attrs: bytes) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in _ATTR_RE.finditer(raw_attrs):
        name = match.group(1).decode("ascii", errors="ignore").lower()
        value = match.group(2) if match.group(2) is not None else match.group(3)
        if value is None:
            value = match.group(4) or b""
        attrs[name] = html.unescape(value.decode("utf-8"))
    return attrs


def _tag_name_at(html_bytes: bytes, pos: int) -> tuple[str, bool, int] | None:
    match = _TAG_RE.match(html_bytes, pos)
    if not match:
        return None
    return match.group(2).decode("ascii", errors="ignore").lower(), bool(match.group(1)), match.end()


def find_unique_script_json(html_bytes: bytes) -> ElementSpan:
    candidates: list[ElementSpan] = []
    for match in _TAG_RE.finditer(html_bytes):
        is_close, tag_name, raw_attrs = match.group(1), match.group(2).lower(), match.group(3)
        if is_close or tag_name != b"script":
            continue
        attrs = parse_attrs(raw_attrs)
        if attrs.get("id") != "character-sheet-data":
            continue
        if attrs.get("type") != "application/json":
            continue
        close = re.search(rb"</\s*script\s*>", html_bytes[match.end() :], re.I)
        if close is None:
            raise HtmlStructureError("character-sheet-data script has no closing tag")
        end_tag_start = match.end() + close.start()
        end_tag_end = match.end() + close.end()
        candidates.append(
            ElementSpan(
                start=match.start(),
                end=end_tag_end,
                start_tag_start=match.start(),
                start_tag_end=match.end(),
                content_start=match.end(),
                content_end=end_tag_start,
                end_tag_start=end_tag_start,
                end_tag_end=end_tag_end,
            )
        )
    if len(candidates) != 1:
        raise HtmlStructureError(f"expected one character-sheet-data script, found {len(candidates)}")
    return candidates[0]


def find_unique_start_tag_by_id(
    html_bytes: bytes,
    element_id: str,
    *,
    tag_name: str | None = None,
) -> StartTagSpan:
    candidates: list[StartTagSpan] = []
    wanted_tag = tag_name.lower() if tag_name is not None else None
    for match in _TAG_RE.finditer(html_bytes):
        if match.group(1):
            continue
        found_tag = match.group(2).decode("ascii", errors="ignore").lower()
        if wanted_tag is not None and found_tag != wanted_tag:
            continue
        attrs = parse_attrs(match.group(3))
        if attrs.get("id") != element_id:
            continue
        candidates.append(
            StartTagSpan(
                start=match.start(),
                end=match.end(),
                attrs=attrs,
                raw=html_bytes[match.start() : match.end()],
            )
        )
    if len(candidates) != 1:
        raise HtmlStructureError(
            f"expected one {element_id} start tag, found {len(candidates)}"
        )
    return candidates[0]


def find_unique_skills_ul(html_bytes: bytes) -> ElementSpan:
    return _find_unique_ul_by_id(html_bytes, "skills-value")


def find_unique_personality_ul(html_bytes: bytes) -> ElementSpan:
    return _find_unique_ul_by_id(html_bytes, "personality-value")


def find_unique_abilities_ul(html_bytes: bytes) -> ElementSpan:
    return _find_unique_ul_by_id(html_bytes, "abilities-value")


def find_unique_memories_ul(html_bytes: bytes) -> ElementSpan:
    return _find_unique_ul_by_id(html_bytes, "memories-value")


def find_unique_element_by_id(html_bytes: bytes, element_id: str) -> ElementSpan:
    """Locate one non-void element by ID without parsing or normalizing HTML."""

    candidates: list[ElementSpan] = []
    for match in _TAG_RE.finditer(html_bytes):
        is_close, tag_name_bytes, raw_attrs = match.group(1), match.group(2), match.group(3)
        if is_close:
            continue
        attrs = parse_attrs(raw_attrs)
        if attrs.get("id") != element_id:
            continue
        tag_name = tag_name_bytes.decode("ascii", errors="ignore").lower()
        end_tag_start, end_tag_end = _find_matching_end(html_bytes, match.end(), tag_name)
        candidates.append(
            ElementSpan(
                start=match.start(),
                end=end_tag_end,
                start_tag_start=match.start(),
                start_tag_end=match.end(),
                content_start=match.end(),
                content_end=end_tag_start,
                end_tag_start=end_tag_start,
                end_tag_end=end_tag_end,
            )
        )
    if len(candidates) != 1:
        raise HtmlStructureError(f"expected one {element_id} element, found {len(candidates)}")
    return candidates[0]


def find_unique_descendant_by_attrs(
    html_bytes: bytes,
    container: ElementSpan,
    *,
    tag_name: str,
    required_attrs: dict[str, str],
) -> ElementSpan:
    """Locate one matching descendant element within an established container."""

    wanted_tag = tag_name.lower()
    candidates: list[ElementSpan] = []
    for match in _TAG_RE.finditer(
        html_bytes,
        container.content_start,
        container.content_end,
    ):
        if match.group(1):
            continue
        found_tag = match.group(2).decode("ascii", errors="ignore").lower()
        if found_tag != wanted_tag:
            continue
        attrs = parse_attrs(match.group(3))
        if any(
            (
                required not in attrs.get(name, "").split()
                if name == "class"
                else attrs.get(name) != required
            )
            for name, required in required_attrs.items()
        ):
            continue
        end_tag_start, end_tag_end = _find_matching_end(
            html_bytes,
            match.end(),
            wanted_tag,
        )
        if end_tag_end > container.content_end:
            continue
        candidates.append(
            ElementSpan(
                start=match.start(),
                end=end_tag_end,
                start_tag_start=match.start(),
                start_tag_end=match.end(),
                content_start=match.end(),
                content_end=end_tag_start,
                end_tag_start=end_tag_start,
                end_tag_end=end_tag_end,
            )
        )
    if len(candidates) != 1:
        description = ", ".join(f"{key}={value!r}" for key, value in required_attrs.items())
        raise HtmlStructureError(
            f"expected one {tag_name} descendant with {description}, found {len(candidates)}"
        )
    return candidates[0]


def _find_unique_ul_by_id(html_bytes: bytes, element_id: str) -> ElementSpan:
    candidates: list[ElementSpan] = []
    for match in _TAG_RE.finditer(html_bytes):
        is_close, tag_name, raw_attrs = match.group(1), match.group(2).lower(), match.group(3)
        if is_close or tag_name != b"ul":
            continue
        attrs = parse_attrs(raw_attrs)
        if attrs.get("id") != element_id:
            continue
        end_tag_start, end_tag_end = _find_matching_end(html_bytes, match.end(), "ul")
        candidates.append(
            ElementSpan(
                start=match.start(),
                end=end_tag_end,
                start_tag_start=match.start(),
                start_tag_end=match.end(),
                content_start=match.end(),
                content_end=end_tag_start,
                end_tag_start=end_tag_start,
                end_tag_end=end_tag_end,
            )
        )
    if len(candidates) != 1:
        raise HtmlStructureError(f"expected one {element_id} ul, found {len(candidates)}")
    return candidates[0]


def _find_matching_end(html_bytes: bytes, search_from: int, tag_name: str) -> tuple[int, int]:
    depth = 1
    wanted = tag_name.lower()
    for match in _TAG_RE.finditer(html_bytes, search_from):
        name = match.group(2).decode("ascii", errors="ignore").lower()
        if name != wanted:
            continue
        if match.group(1):
            depth -= 1
            if depth == 0:
                return match.start(), match.end()
        else:
            raw_attrs = match.group(3).strip()
            if not raw_attrs.endswith(b"/"):
                depth += 1
    raise HtmlStructureError(f"{tag_name} element has no matching end tag")


def find_direct_skill_lis(html_bytes: bytes, ul_span: ElementSpan) -> list[LiSpan]:
    return find_direct_lis(html_bytes, ul_span)


def find_direct_personality_lis(html_bytes: bytes, ul_span: ElementSpan) -> list[LiSpan]:
    return find_direct_lis(html_bytes, ul_span)


def find_direct_lis(html_bytes: bytes, ul_span: ElementSpan) -> list[LiSpan]:
    lis: list[LiSpan] = []
    depth = 0
    pos = ul_span.content_start
    while pos < ul_span.content_end:
        match = _TAG_RE.search(html_bytes, pos, ul_span.content_end)
        if match is None:
            break
        is_close = bool(match.group(1))
        name = match.group(2).decode("ascii", errors="ignore").lower()
        if not is_close and name == "li" and depth == 0:
            li = _read_li(html_bytes, match)
            if li.end > ul_span.content_end:
                raise HtmlStructureError("li extends past skills-value ul")
            lis.append(li)
            pos = li.end
            continue
        if not is_close and not match.group(3).strip().endswith(b"/"):
            depth += 1
        elif is_close and depth > 0:
            depth -= 1
        pos = match.end()
    return lis


def _read_li(html_bytes: bytes, start_match: re.Match[bytes]) -> LiSpan:
    end_tag_start, end_tag_end = _find_matching_end(html_bytes, start_match.end(), "li")
    attrs = parse_attrs(start_match.group(3))
    return LiSpan(
        start=start_match.start(),
        end=end_tag_end,
        start_tag_start=start_match.start(),
        start_tag_end=start_match.end(),
        content_start=start_match.end(),
        content_end=end_tag_start,
        attrs=attrs,
        raw=html_bytes[start_match.start() : end_tag_end],
        inner=html_bytes[start_match.end() : end_tag_start],
    )


def text_content(inner: bytes) -> str:
    stripped = re.sub(rb"<[^<>]*>", b"", inner)
    return html.unescape(stripped.decode("utf-8")).strip()
