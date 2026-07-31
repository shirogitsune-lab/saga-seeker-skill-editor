"""Lossy, AI-oriented Markdown export and conservative partial import.

Markdown is deliberately not treated as a character-sheet archive.  Export
omits images and internal identifiers.  Import builds a new sheet from only
the small set of headings this module owns and validates every catalog-backed
or bounded value before generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import re
from typing import Iterable, Sequence

from saga_seeker_skill_editor.core.character_sheet import CharacterSheet
from saga_seeker_skill_editor.core.personality_catalog import PersonalityKeyword
from saga_seeker_skill_editor.core.phase0_candidate_sheet import (
    GenerationInputs,
    build_candidate_golden_document,
    render_candidate_html,
)


V2_MARKER = "<!-- saga-seeker-ai-markdown:2 -->"
V1_MARKER = "<!-- saga-seeker-ai-markdown:1 -->"
TEXT_START = "<!-- saga-seeker-text:start -->"
TEXT_END = "<!-- saga-seeker-text:end -->"
CANONICAL_H1 = "# Saga & Seeker キャラクター"
MEMORY_NOTICE = (
    "> このセクションはAI参照用です。"
    "Markdownから新規作成しても思い出は復元されません。"
)
_FORMAT_MARKER_PATTERN = re.compile(
    r"<!-- saga-seeker-ai-markdown:([^\s]+) -->"
)
_MARKER_LIKE_PATTERN = re.compile(
    r"<!-- saga-seeker-ai-markdown:(.*?)-->"
)
MAX_MARKDOWN_BYTES = 8 * 1024 * 1024
EMPTY_DISPLAY = "（未入力）"

PROFILE_FIELDS = (
    ("basicSettings", "基本設定"),
    ("appearance", "外見"),
    ("personality", "性格"),
    ("speechStyle", "口調"),
    ("background", "経歴"),
    ("talentsAndRole", "特技と役割"),
    ("otherFeatures", "その他の特徴"),
)
STATUS_FIELDS = (
    ("strength", "筋力"),
    ("endurance", "耐久力"),
    ("intelligence", "知力"),
    ("mentalStrength", "精神力"),
    ("agility", "素早さ"),
    ("luck", "運"),
)
RANKS = frozenset({"E", "D", "C", "B", "A", "S"})


class MarkdownImportError(ValueError):
    """Raised when Markdown cannot safely become a new character sheet."""


class MarkdownFormatKind(str, Enum):
    """Lexical classifications that precede Markdown interpretation."""

    CANONICAL_V2 = "canonical-v2"
    LEGACY_MARKED_V1 = "legacy-marked-v1"
    LEGACY_UNMARKED = "legacy-unmarked"
    INVALID_MARKER_POSITION = "invalid-marker-position"
    UNKNOWN_VERSION = "unknown-version"
    DUPLICATE_MARKER = "duplicate-marker"
    MIXED_VERSION_MARKERS = "mixed-version-markers"
    MALFORMED_TEXT_BLOCK = "malformed-text-block"


@dataclass(frozen=True)
class MarkdownFormatDetection:
    kind: MarkdownFormatKind
    version: str | None = None
    marker_line: int | None = None


@dataclass(frozen=True)
class MarkdownSkill:
    name: str
    description: str


@dataclass(frozen=True)
class MarkdownImportIssue:
    code: str
    message: str
    severity: str


@dataclass(frozen=True)
class MarkdownImportPlan:
    name: str
    profile: dict[str, str]
    status: dict[str, str]
    personalities: tuple[PersonalityKeyword, ...]
    skills: tuple[MarkdownSkill, ...]
    issues: tuple[MarkdownImportIssue, ...]
    format_kind: MarkdownFormatKind
    memory_count: int = 0

    @property
    def can_create(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    @property
    def legacy_format(self) -> bool:
        return self.format_kind in {
            MarkdownFormatKind.LEGACY_MARKED_V1,
            MarkdownFormatKind.LEGACY_UNMARKED,
        }


def detect_markdown_format(raw: bytes) -> MarkdownFormatDetection:
    """Classify format markers without interpreting character data."""

    lines = _decode_markdown(raw).split("\n")
    in_text_block = False
    malformed_block = False
    markers: list[tuple[str, int]] = []
    for line_number, line in enumerate(lines, start=1):
        if in_text_block:
            if line == TEXT_END:
                in_text_block = False
            continue
        if line == TEXT_START:
            in_text_block = True
            continue
        if line == TEXT_END:
            malformed_block = True
            continue
        marker = _FORMAT_MARKER_PATTERN.fullmatch(line)
        if marker is not None:
            markers.append((marker.group(1), line_number))
            continue
        marker_like = _MARKER_LIKE_PATTERN.fullmatch(line)
        if marker_like is not None:
            markers.append((f"invalid:{marker_like.group(1)}", line_number))

    if in_text_block or malformed_block:
        return MarkdownFormatDetection(MarkdownFormatKind.MALFORMED_TEXT_BLOCK)
    versions = {version for version, _line in markers}
    if len(versions) > 1:
        return MarkdownFormatDetection(MarkdownFormatKind.MIXED_VERSION_MARKERS)
    if len(markers) > 1:
        version, line = markers[0]
        return MarkdownFormatDetection(
            MarkdownFormatKind.DUPLICATE_MARKER,
            version=version,
            marker_line=line,
        )
    if not markers:
        return MarkdownFormatDetection(MarkdownFormatKind.LEGACY_UNMARKED)

    version, line = markers[0]
    if version not in {"1", "2"}:
        return MarkdownFormatDetection(
            MarkdownFormatKind.UNKNOWN_VERSION,
            version=version,
            marker_line=line,
        )
    if line != 1:
        return MarkdownFormatDetection(
            MarkdownFormatKind.INVALID_MARKER_POSITION,
            version=version,
            marker_line=line,
        )
    return MarkdownFormatDetection(
        (
            MarkdownFormatKind.CANONICAL_V2
            if version == "2"
            else MarkdownFormatKind.LEGACY_MARKED_V1
        ),
        version=version,
        marker_line=line,
    )


def render_ai_markdown(sheet: CharacterSheet) -> bytes:
    """Render the sheet's current semantic data as UTF-8 AI-readable Markdown."""

    data = sheet.data.get("data")
    if not isinstance(data, dict):
        raise ValueError("character sheet data must be an object")
    profile = data.get("profile")
    status = data.get("status")
    skills = data.get("skills")
    personalities = data.get("personalities")
    memories = data.get("memories")

    lines: list[str] = [
        V2_MARKER,
        CANONICAL_H1,
        "",
        "## キャラクター名",
    ]
    _append_text_block(lines, _string(data.get("name")))
    lines.extend(["", "## キャラクター詳細", ""])
    profile_object = profile if isinstance(profile, dict) else {}
    for key, label in PROFILE_FIELDS:
        lines.append(f"### {label}")
        _append_text_block(lines, _string(profile_object.get(key)))
        lines.append("")

    lines.extend(["## 性格キーワード", ""])
    if isinstance(personalities, list):
        exported_personalities = [
            item.get("name")
            for item in personalities
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]
    else:
        exported_personalities = []
    if exported_personalities:
        lines.extend(
            f"- 枠{index}: {name}"
            for index, name in enumerate(exported_personalities, start=1)
        )
    lines.append("")

    lines.extend(["## ステータス", ""])
    status_object = status if isinstance(status, dict) else {}
    for key, label in STATUS_FIELDS:
        lines.append(f"- {label}: {_string(status_object.get(key)) or 'E'}")
    lines.append("")

    lines.extend(["## スキル", ""])
    exported_skill_count = 0
    if isinstance(skills, list):
        for skill in skills:
            if not isinstance(skill, dict):
                continue
            name = _string(skill.get("name"))
            if not name:
                continue
            description = _string(skill.get("description"))
            exported_skill_count += 1
            lines.extend(
                [
                    f"### スキル {exported_skill_count}",
                    "#### 名前",
                ]
            )
            _append_text_block(lines, name)
            lines.extend(["", "#### 説明"])
            _append_text_block(lines, description)
            lines.append("")

    lines.extend(["## 思い出", MEMORY_NOTICE, ""])
    exported_memory_count = 0
    if isinstance(memories, list):
        for memory in memories:
            if not isinstance(memory, dict) or memory.get("isPlaceholder") is True:
                continue
            title = _string(memory.get("title"))
            exported_memory_count += 1
            lines.extend(
                [
                    f"### 思い出 {exported_memory_count}",
                    "#### タイトル",
                ]
            )
            _append_text_block(lines, title)
            for heading, field in (
                ("概要", "summary"),
                ("場所", "location"),
                ("意図", "intent"),
                ("結果", "outcome"),
            ):
                lines.extend(["", f"#### {heading}"])
                _append_text_block(lines, _string(memory.get(field)))
            tags = memory.get("tags")
            tag_values = (
                [value for value in tags if isinstance(value, str)]
                if isinstance(tags, list)
                else []
            )
            lines.extend(
                [
                    "",
                    "#### タグ（JSON）",
                    json.dumps(tag_values, ensure_ascii=False, separators=(",", ":")),
                    "",
                ]
            )

    if lines[-1] != "":
        lines.append("")
    return "\n".join(lines).encode("utf-8")


def parse_character_markdown(
    raw: bytes,
    *,
    catalog: Sequence[PersonalityKeyword],
    allow_legacy: bool = False,
) -> MarkdownImportPlan:
    """Parse canonical v2 or an explicitly allowed legacy dialect."""

    detection = detect_markdown_format(raw)
    text = _decode_markdown(raw)
    if detection.kind is MarkdownFormatKind.CANONICAL_V2:
        return _parse_canonical_v2(text, catalog=catalog)
    if detection.kind in {
        MarkdownFormatKind.LEGACY_MARKED_V1,
        MarkdownFormatKind.LEGACY_UNMARKED,
    }:
        if not allow_legacy:
            raise MarkdownImportError(
                "旧形式Markdownです。内容を解析する前に"
                "「旧形式として解析する」を明示してください"
            )
        return _parse_legacy_markdown(
            text,
            catalog=catalog,
            format_kind=detection.kind,
        )

    messages = {
        MarkdownFormatKind.INVALID_MARKER_POSITION: (
            "AI向けMarkdown形式マーカーの位置が不正です"
        ),
        MarkdownFormatKind.UNKNOWN_VERSION: (
            "未知のAI向けMarkdown形式バージョンです"
        ),
        MarkdownFormatKind.DUPLICATE_MARKER: (
            "AI向けMarkdown形式マーカーが重複しています"
        ),
        MarkdownFormatKind.MIXED_VERSION_MARKERS: (
            "異なるAI向けMarkdown形式マーカーが混在しています"
        ),
        MarkdownFormatKind.MALFORMED_TEXT_BLOCK: (
            "Markdownテキストブロックが不正または未閉鎖です"
        ),
    }
    raise MarkdownImportError(messages[detection.kind])


def _parse_legacy_markdown(
    text: str,
    *,
    catalog: Sequence[PersonalityKeyword],
    format_kind: MarkdownFormatKind,
) -> MarkdownImportPlan:
    lines = text.split("\n")
    sections, section_issues = _split_h2_sections(lines)
    issues = list(section_issues)

    name = _field_value(_section_body(sections, "キャラクター名"))
    if "\n" in name:
        issues.append(
            _error(
                "legacy-multiline-name",
                "旧形式のキャラクター名を一意な単一行として解釈できません",
            )
        )
    profile = {key: "" for key, _label in PROFILE_FIELDS}
    detail_lines = _section_body(sections, "キャラクター詳細")
    detail_fields, detail_issues = _split_h3_fields(
        detail_lines,
        {label for _key, label in PROFILE_FIELDS},
        "profile",
    )
    issues.extend(detail_issues)
    for key, label in PROFILE_FIELDS:
        field_lines = detail_fields.get(label)
        value = _field_value(field_lines or [])
        profile[key] = value
        if field_lines is None:
            issues.append(
                _warning(
                    "legacy-missing-profile",
                    f"旧形式の{label}がないため空欄になります",
                )
            )
        elif value == "" and _contains_empty_marker(field_lines):
            issues.append(
                _warning(
                    "legacy-empty-marker",
                    f"{label}の「{EMPTY_DISPLAY}」を空欄として取り込みます",
                )
            )

    status = {key: "E" for key, _label in STATUS_FIELDS}
    status_by_label = {label: key for key, label in STATUS_FIELDS}
    seen_statuses: set[str] = set()
    for line in _section_body(sections, "ステータス"):
        if line.strip() == "":
            continue
        match = re.fullmatch(r"\s*-\s*([^:：]+)\s*[:：]\s*(.*?)\s*", line)
        if match is None:
            issues.append(
                _error(
                    "invalid-status-line",
                    "旧形式のステータス行を一意に解釈できません",
                )
            )
            continue
        label, rank = match.groups()
        key = status_by_label.get(label.strip())
        if key is None:
            issues.append(
                _error(
                    "unknown-status",
                    f"未知のステータス項目です: {label.strip()}",
                )
            )
            continue
        if key in seen_statuses:
            issues.append(_error("duplicate-status", f"ステータス「{label}」が重複しています"))
            continue
        seen_statuses.add(key)
        if rank not in RANKS:
            issues.append(
                _error(
                    "invalid-status-rank",
                    f"ステータス「{label}」はE～Sの値ではありません: {rank!r}",
                )
            )
            continue
        status[key] = rank
    for key, label in STATUS_FIELDS:
        if key not in seen_statuses:
            issues.append(
                _warning(
                    "legacy-missing-status",
                    f"旧形式の{label}がないためEになります",
                )
            )

    personalities, personality_issues = _parse_personalities(
        _section_body(sections, "性格キーワード"),
        catalog,
    )
    issues.extend(personality_issues)
    if not personalities:
        issues.append(
            _warning(
                "legacy-missing-personality",
                "旧形式に性格キーワードが指定されていません",
            )
        )

    skills, skill_issues = _parse_skills(
        _section_body(sections, "スキル"),
        legacy_format=True,
    )
    issues.extend(skill_issues)

    if _contains_empty_marker(_section_body(sections, "キャラクター名")):
        issues.append(
            _warning(
                "legacy-empty-marker",
                f"キャラクター名の「{EMPTY_DISPLAY}」を空欄として取り込みます",
            )
        )
    issues.extend(
        (
            _warning(
                "legacy-image-not-restored",
                "旧形式から画像は復元されません",
            ),
            _warning(
                "legacy-memories-not-restored",
                "旧形式から思い出は復元されません",
            ),
        )
    )

    _append_length_issues(issues, name=name, profile=profile, skills=skills)
    return MarkdownImportPlan(
        name=name,
        profile=profile,
        status=status,
        personalities=personalities,
        skills=skills,
        issues=tuple(issues),
        format_kind=format_kind,
        memory_count=_legacy_memory_count(_section_body(sections, "思い出")),
    )


@dataclass
class _LineCursor:
    lines: list[str]
    index: int = 0

    def current(self) -> str | None:
        return self.lines[self.index] if self.index < len(self.lines) else None

    def expect(self, expected: str) -> None:
        actual = self.current()
        if actual != expected:
            raise MarkdownImportError(
                f"AI向けMarkdown形式 v2の構造が不正です。"
                f"{expected!r}が必要ですが{actual!r}でした"
            )
        self.index += 1

    def skip_blank_lines(self) -> None:
        while self.current() == "":
            self.index += 1


def _parse_canonical_v2(
    text: str,
    *,
    catalog: Sequence[PersonalityKeyword],
) -> MarkdownImportPlan:
    cursor = _LineCursor(text.split("\n"))
    cursor.expect(V2_MARKER)
    cursor.expect(CANONICAL_H1)
    cursor.skip_blank_lines()

    cursor.expect("## キャラクター名")
    name = _parse_text_block(cursor)
    _require_single_line(name, "キャラクター名")
    cursor.skip_blank_lines()

    cursor.expect("## キャラクター詳細")
    cursor.skip_blank_lines()
    profile: dict[str, str] = {}
    for key, label in PROFILE_FIELDS:
        cursor.expect(f"### {label}")
        profile[key] = _parse_text_block(cursor)
        cursor.skip_blank_lines()

    cursor.expect("## 性格キーワード")
    cursor.skip_blank_lines()
    personalities = _parse_canonical_personalities(cursor, catalog=catalog)

    cursor.expect("## ステータス")
    cursor.skip_blank_lines()
    status: dict[str, str] = {}
    for key, label in STATUS_FIELDS:
        current = cursor.current()
        match = re.fullmatch(rf"- {re.escape(label)}: ([EDCBAS])", current or "")
        if match is None:
            raise MarkdownImportError(
                f"AI向けMarkdown形式 v2のステータス「{label}」が"
                "欠落しているか不正です"
            )
        status[key] = match.group(1)
        cursor.index += 1
    cursor.skip_blank_lines()

    cursor.expect("## スキル")
    cursor.skip_blank_lines()
    skills: list[MarkdownSkill] = []
    while cursor.current() != "## 思い出":
        if cursor.current() is None:
            raise MarkdownImportError(
                "AI向けMarkdown形式 v2の「思い出」セクションがありません"
            )
        index = len(skills) + 1
        if index > 6:
            raise MarkdownImportError(
                "AI向けMarkdown形式 v2のスキルは6件までです"
            )
        cursor.expect(f"### スキル {index}")
        cursor.expect("#### 名前")
        skill_name = _parse_text_block(cursor)
        _require_single_line(skill_name, f"スキル{index}の名前")
        if skill_name == "":
            raise MarkdownImportError(f"スキル{index}の名前が空欄です")
        cursor.skip_blank_lines()
        cursor.expect("#### 説明")
        description = _parse_text_block(cursor)
        cursor.skip_blank_lines()
        skills.append(MarkdownSkill(skill_name, description))

    cursor.expect("## 思い出")
    cursor.expect(MEMORY_NOTICE)
    cursor.skip_blank_lines()
    memory_count = _parse_canonical_memories(cursor)
    cursor.skip_blank_lines()
    if cursor.current() is not None:
        raise MarkdownImportError(
            "AI向けMarkdown形式 v2の末尾に未知の構造があります"
        )

    issues: list[MarkdownImportIssue] = []
    _append_length_issues(
        issues,
        name=name,
        profile=profile,
        skills=skills,
    )
    return MarkdownImportPlan(
        name=name,
        profile=profile,
        status=status,
        personalities=personalities,
        skills=tuple(skills),
        issues=tuple(issues),
        format_kind=MarkdownFormatKind.CANONICAL_V2,
        memory_count=memory_count,
    )


def _parse_canonical_personalities(
    cursor: _LineCursor,
    *,
    catalog: Sequence[PersonalityKeyword],
) -> tuple[PersonalityKeyword, ...]:
    by_name = {keyword.name: keyword for keyword in catalog}
    personalities: list[PersonalityKeyword] = []
    while cursor.current() != "## ステータス":
        if cursor.current() is None:
            raise MarkdownImportError(
                "AI向けMarkdown形式 v2の「ステータス」セクションがありません"
            )
        if cursor.current() == "":
            cursor.skip_blank_lines()
            continue
        if (cursor.current() or "").startswith("## "):
            raise MarkdownImportError(
                "AI向けMarkdown形式 v2では"
                "「## ステータス」が次のセクションです"
            )
        expected_slot = len(personalities) + 1
        match = re.fullmatch(r"- 枠([1-6]): (.+)", cursor.current() or "")
        if match is None or int(match.group(1)) != expected_slot:
            raise MarkdownImportError(
                "AI向けMarkdown形式 v2の性格キーワード枠が"
                "1から連続していません"
            )
        keyword = by_name.get(match.group(2))
        if keyword is None:
            raise MarkdownImportError(
                f"性格キーワード「{match.group(2)}」は既存カタログにありません"
            )
        if keyword.id in {item.id for item in personalities}:
            raise MarkdownImportError(
                "同じ性格キーワードを複数回取り込めません"
            )
        personalities.append(keyword)
        cursor.index += 1
    return tuple(personalities)


def _parse_canonical_memories(cursor: _LineCursor) -> int:
    memory_count = 0
    fields = ("タイトル", "概要", "場所", "意図", "結果")
    while cursor.current() is not None:
        if cursor.current() == "":
            cursor.skip_blank_lines()
            if cursor.current() is None:
                break
        memory_count += 1
        cursor.expect(f"### 思い出 {memory_count}")
        for heading in fields:
            cursor.expect(f"#### {heading}")
            _parse_text_block(cursor)
            cursor.skip_blank_lines()
        cursor.expect("#### タグ（JSON）")
        tags_line = cursor.current()
        if tags_line is None:
            raise MarkdownImportError(
                f"思い出{memory_count}のタグ配列がありません"
            )
        try:
            tags = json.loads(tags_line)
        except json.JSONDecodeError as exc:
            raise MarkdownImportError(
                f"思い出{memory_count}のタグ配列が不正です"
            ) from exc
        if not isinstance(tags, list) or not all(
            isinstance(tag, str) for tag in tags
        ):
            raise MarkdownImportError(
                f"思い出{memory_count}のタグは文字列配列ではありません"
            )
        cursor.index += 1
        cursor.skip_blank_lines()
    return memory_count


def _require_single_line(value: str, label: str) -> None:
    if "\n" in value:
        raise MarkdownImportError(f"{label}は単一行で指定してください")


def _parse_text_block(cursor: _LineCursor) -> str:
    cursor.expect(TEXT_START)
    encoded_lines: list[str] = []
    while True:
        line = cursor.current()
        if line is None:
            raise MarkdownImportError("Markdownテキストブロックが未閉鎖です")
        if line == TEXT_END:
            cursor.index += 1
            break
        if line == TEXT_START:
            raise MarkdownImportError(
                "Markdownテキストブロック内の開始マーカーは"
                "エスケープしてください"
            )
        encoded_lines.append(line)
        cursor.index += 1
    if not encoded_lines:
        raise MarkdownImportError(
            "空文字はMarkdownテキストブロック内の空行で表現してください"
        )
    return "\n".join(_decode_text_line(line) for line in encoded_lines)


def _decode_text_line(line: str) -> str:
    if line in {f"\\{TEXT_START}", f"\\{TEXT_END}"}:
        return line[1:]
    decoded: list[str] = []
    index = 0
    while index < len(line):
        character = line[index]
        if character != "\\":
            decoded.append(character)
            index += 1
            continue
        if index + 1 >= len(line) or line[index + 1] != "\\":
            raise MarkdownImportError(
                "Markdownテキストブロックに未知のエスケープがあります"
            )
        decoded.append("\\")
        index += 2
    return "".join(decoded)


def _append_text_block(lines: list[str], value: str) -> None:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    lines.append(TEXT_START)
    for line in normalized.split("\n"):
        if line in {TEXT_START, TEXT_END}:
            lines.append(f"\\{line}")
        else:
            lines.append(line.replace("\\", "\\\\"))
    lines.append(TEXT_END)


def _legacy_memory_count(lines: Sequence[str]) -> int:
    return sum(
        re.fullmatch(r"###\s+.+?\s*", line) is not None
        for line in lines
    )


def create_character_sheet_from_markdown(
    plan: MarkdownImportPlan,
    *,
    icon_webp: bytes,
    generation: GenerationInputs,
) -> bytes:
    """Create a new compatible HTML sheet from a validated import plan."""

    if not plan.can_create:
        errors = "; ".join(
            issue.message for issue in plan.issues if issue.severity == "error"
        )
        raise MarkdownImportError(errors or "Markdownの取り込み条件を満たしていません")

    document = build_candidate_golden_document(
        icon_webp=icon_webp,
        generation=generation,
    )
    data = document["data"]
    if not isinstance(data, dict):  # pragma: no cover - generator contract
        raise MarkdownImportError("新規シートの基準データが不正です")
    data["name"] = plan.name
    data["profile"] = dict(plan.profile)
    status = data["status"]
    if not isinstance(status, dict):  # pragma: no cover - generator contract
        raise MarkdownImportError("新規シートのステータス基準が不正です")
    status.update(plan.status)
    status["charm"] = "E"
    data["personalities"] = [keyword.as_dict() for keyword in plan.personalities]
    data["skills"] = [
        {
            "id": f"sk{index}",
            "name": skill.name,
            "description": skill.description,
            "type": "",
            "key": "",
        }
        for index, skill in enumerate(plan.skills, start=1)
    ]
    data["memories"] = []
    return render_candidate_html(document)


def _split_h2_sections(
    lines: Sequence[str],
) -> tuple[dict[str, list[str]], tuple[MarkdownImportIssue, ...]]:
    sections: dict[str, list[str]] = {}
    issues: list[MarkdownImportIssue] = []
    current: str | None = None
    for line in lines:
        match = re.fullmatch(r"##\s+(.+?)\s*", line)
        if match is not None:
            heading = match.group(1)
            if heading in sections:
                issues.append(
                    _error("duplicate-section", f"セクション「{heading}」が重複しています")
                )
                current = None
            else:
                current = heading
                sections[current] = []
            continue
        if current is not None:
            sections[current].append(line)
    return sections, tuple(issues)


def _split_h3_fields(
    lines: Sequence[str],
    recognized: set[str],
    code_prefix: str,
) -> tuple[dict[str, list[str]], tuple[MarkdownImportIssue, ...]]:
    fields: dict[str, list[str]] = {}
    issues: list[MarkdownImportIssue] = []
    current: str | None = None
    for line in lines:
        match = re.fullmatch(r"###\s+(.+?)\s*", line)
        if match is not None:
            heading = match.group(1)
            if heading not in recognized:
                current = None
            elif heading in fields:
                issues.append(
                    _error(
                        f"duplicate-{code_prefix}-field",
                        f"項目「{heading}」が重複しています",
                    )
                )
                current = None
            else:
                current = heading
                fields[current] = []
            continue
        if current is not None:
            fields[current].append(line)
    return fields, tuple(issues)


def _parse_personalities(
    lines: Sequence[str],
    catalog: Sequence[PersonalityKeyword],
) -> tuple[tuple[PersonalityKeyword, ...], tuple[MarkdownImportIssue, ...]]:
    by_name = {keyword.name: keyword for keyword in catalog}
    slots: dict[int, PersonalityKeyword] = {}
    sequential_slot = 1
    issues: list[MarkdownImportIssue] = []
    for line in lines:
        if line.strip() in {"", EMPTY_DISPLAY}:
            continue
        match = re.fullmatch(r"\s*-\s*(?:枠([0-9]+)\s*[:：]\s*)?(.+?)\s*", line)
        if match is None:
            issues.append(
                _error(
                    "ambiguous-personality-line",
                    "性格キーワード行を一意に解釈できません",
                )
            )
            continue
        explicit_slot, name = match.groups()
        if name == EMPTY_DISPLAY:
            continue
        keyword = by_name.get(name)
        if keyword is None:
            issues.append(
                _error(
                    "unknown-personality",
                    f"性格キーワード「{name}」は既存カタログにありません",
                )
            )
            continue
        slot = int(explicit_slot) if explicit_slot is not None else sequential_slot
        if explicit_slot is None:
            sequential_slot += 1
        if not 1 <= slot <= 6:
            issues.append(
                _error(
                    "personality-slot-range",
                    f"性格キーワードの枠番号は1～6です: {slot}",
                )
            )
            continue
        if slot in slots:
            issues.append(
                _error("duplicate-personality-slot", f"性格キーワード枠{slot}が重複しています")
            )
            continue
        slots[slot] = keyword

    ids = [keyword.id for keyword in slots.values()]
    if len(ids) != len(set(ids)):
        issues.append(
            _error("duplicate-personality", "同じ性格キーワードを複数回取り込めません")
        )
    if slots:
        expected = set(range(1, max(slots) + 1))
        if set(slots) != expected:
            issues.append(
                _error(
                    "personality-gap",
                    "性格キーワードは枠1から空欄を作らず連続して指定してください",
                )
            )
    return tuple(slots[index] for index in sorted(slots)), tuple(issues)


def _parse_skills(
    lines: Sequence[str],
    *,
    legacy_format: bool,
) -> tuple[tuple[MarkdownSkill, ...], tuple[MarkdownImportIssue, ...]]:
    if legacy_format and not any(
        re.fullmatch(r"###\s+(.+?)\s*", line) is not None
        for line in lines
    ):
        meaningful = [
            line
            for line in lines
            if line.strip() not in {"", EMPTY_DISPLAY}
        ]
        if meaningful:
            return (), (
                _error(
                    "ambiguous-legacy-skill",
                    "旧形式の箇条書きスキルは説明との区別ができません",
                ),
            )
        return (), ()

    skills: list[MarkdownSkill] = []
    issues: list[MarkdownImportIssue] = []
    current_name: str | None = None
    current_description: list[str] = []

    def finish() -> None:
        nonlocal current_name, current_description
        if current_name is None:
            return
        description = _field_value(current_description)
        skills.append(MarkdownSkill(current_name, description))
        current_name = None
        current_description = []

    for line in lines:
        heading = re.fullmatch(r"###\s+(.+?)\s*", line)
        if heading is not None:
            finish()
            current_name = heading.group(1)
            continue
        if current_name is not None:
            current_description.append(line)
        elif line.strip() not in {"", EMPTY_DISPLAY}:
            issues.append(
                _error(
                    "ambiguous-legacy-skill",
                    "旧形式のスキル見出しより前に解釈できない本文があります",
                )
            )
    finish()

    if len(skills) > 6:
        issues.append(
            _error(
                "too-many-skills",
                f"スキルは6件まで取り込めます（{len(skills)}件あります）",
            )
        )
    for index, skill in enumerate(skills, start=1):
        if not skill.name:
            issues.append(_error("empty-skill-name", f"スキル{index}の名前が空欄です"))
    return tuple(skills), tuple(issues)


def _append_length_issues(
    issues: list[MarkdownImportIssue],
    *,
    name: str,
    profile: dict[str, str],
    skills: Sequence[MarkdownSkill],
) -> None:
    if len(name) > 20:
        issues.append(
            _warning("name-length", f"キャラクター名が20文字を超えています（{len(name)}文字）")
        )
    for key, label in PROFILE_FIELDS:
        if len(profile[key]) > 1000:
            issues.append(
                _warning(
                    "profile-length",
                    f"{label}が1000文字を超えています（{len(profile[key])}文字）",
                )
            )
    for index, skill in enumerate(skills, start=1):
        for value, label in ((skill.name, "名前"), (skill.description, "説明")):
            if len(value) > 1000:
                issues.append(
                    _warning(
                        "skill-length",
                        f"スキル{index}の{label}が1000文字を超えています（{len(value)}文字）",
                    )
                )


def _section_body(sections: dict[str, list[str]], heading: str) -> list[str]:
    return sections.get(heading, [])


def _field_value(lines: Iterable[str]) -> str:
    values = list(lines)
    while values and values[0].strip() == "":
        values.pop(0)
    while values and values[-1].strip() == "":
        values.pop()
    value = "\n".join(values)
    return "" if value == EMPTY_DISPLAY else value


def _contains_empty_marker(lines: Iterable[str]) -> bool:
    return _field_value(lines) == "" and any(
        line.strip() == EMPTY_DISPLAY for line in lines
    )


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _warning(code: str, message: str) -> MarkdownImportIssue:
    return MarkdownImportIssue(code=code, message=message, severity="warning")


def _error(code: str, message: str) -> MarkdownImportIssue:
    return MarkdownImportIssue(code=code, message=message, severity="error")


def _decode_markdown(raw: bytes) -> str:
    if len(raw) > MAX_MARKDOWN_BYTES:
        raise MarkdownImportError(
            f"Markdownファイルが上限（{MAX_MARKDOWN_BYTES // (1024 * 1024)} MiB）を超えています"
        )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise MarkdownImportError("MarkdownはUTF-8で保存してください") from exc
    if "\x00" in text:
        raise MarkdownImportError("MarkdownにNUL文字が含まれています")
    return text.replace("\r\n", "\n").replace("\r", "\n")
