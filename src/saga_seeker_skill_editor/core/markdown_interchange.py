"""Lossy, AI-oriented Markdown export and conservative partial import.

Markdown is deliberately not treated as a character-sheet archive.  Export
omits images and internal identifiers.  Import builds a new sheet from only
the small set of headings this module owns and validates every catalog-backed
or bounded value before generation.
"""

from __future__ import annotations

from dataclasses import dataclass
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


MARKER = "<!-- saga-seeker-ai-markdown:1 -->"
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
    legacy_format: bool

    @property
    def can_create(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


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
        MARKER,
        "# Saga & Seeker キャラクター",
        "",
        "## キャラクター名",
        "",
        _display(_string(data.get("name"))),
        "",
        "## キャラクター詳細",
        "",
    ]
    profile_object = profile if isinstance(profile, dict) else {}
    for key, label in PROFILE_FIELDS:
        lines.extend(
            [
                f"### {label}",
                "",
                _display(_string(profile_object.get(key))),
                "",
            ]
        )

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
    else:
        lines.append(EMPTY_DISPLAY)
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
            lines.extend([f"### {name}", "", _display(description), ""])
            exported_skill_count += 1
    if not exported_skill_count:
        lines.extend([EMPTY_DISPLAY, ""])

    lines.extend(["## 思い出", ""])
    exported_memory_count = 0
    if isinstance(memories, list):
        for memory in memories:
            if not isinstance(memory, dict) or memory.get("isPlaceholder") is True:
                continue
            title = _string(memory.get("title"))
            lines.extend(
                [
                    f"### {_display(title)}",
                    "",
                    "#### 概要",
                    "",
                    _display(_string(memory.get("summary"))),
                    "",
                    "#### 場所",
                    "",
                    _display(_string(memory.get("location"))),
                    "",
                    "#### 意図",
                    "",
                    _display(_string(memory.get("intent"))),
                    "",
                    "#### 結果",
                    "",
                    _display(_string(memory.get("outcome"))),
                    "",
                ]
            )
            tags = memory.get("tags")
            tag_values = (
                [value for value in tags if isinstance(value, str)]
                if isinstance(tags, list)
                else []
            )
            lines.extend(
                [
                    "#### タグ（JSON）",
                    "",
                    json.dumps(tag_values, ensure_ascii=False, separators=(",", ":")),
                    "",
                ]
            )
            exported_memory_count += 1
    if not exported_memory_count:
        lines.extend([EMPTY_DISPLAY, ""])

    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def parse_character_markdown(
    raw: bytes,
    *,
    catalog: Sequence[PersonalityKeyword],
) -> MarkdownImportPlan:
    """Parse known Markdown headings without interpreting HTML or executing code."""

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

    lines = text.splitlines()
    legacy_format = not any(line.strip() == MARKER for line in lines)
    sections, section_issues = _split_h2_sections(lines)
    issues = list(section_issues)

    name = _field_value(_section_body(sections, "キャラクター名"))
    profile = {key: "" for key, _label in PROFILE_FIELDS}
    detail_lines = _section_body(sections, "キャラクター詳細")
    detail_fields, detail_issues = _split_h3_fields(
        detail_lines,
        {label for _key, label in PROFILE_FIELDS},
        "profile",
    )
    issues.extend(detail_issues)
    for key, label in PROFILE_FIELDS:
        value = _field_value(detail_fields.get(label, []))
        profile[key] = value
        if value == "" and _contains_empty_marker(detail_fields.get(label, [])):
            if legacy_format:
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
        match = re.fullmatch(r"\s*-\s*([^:：]+)\s*[:：]\s*(.*?)\s*", line)
        if match is None:
            continue
        label, rank = match.groups()
        key = status_by_label.get(label.strip())
        if key is None:
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

    personalities, personality_issues = _parse_personalities(
        _section_body(sections, "性格キーワード"),
        catalog,
    )
    issues.extend(personality_issues)

    skills, skill_issues = _parse_skills(
        _section_body(sections, "スキル"),
        legacy_format=legacy_format,
    )
    issues.extend(skill_issues)

    if legacy_format and _contains_empty_marker(_section_body(sections, "キャラクター名")):
        issues.append(
            _warning(
                "legacy-empty-marker",
                f"キャラクター名の「{EMPTY_DISPLAY}」を空欄として取り込みます",
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
        legacy_format=legacy_format,
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
        match = re.fullmatch(r"\s*-\s*(?:枠([0-9]+)\s*[:：]\s*)?(.+?)\s*", line)
        if match is None:
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
        bullet = re.fullmatch(r"\s*-\s+(.+?)\s*", line)
        if heading is not None:
            finish()
            current_name = heading.group(1)
            continue
        if legacy_format and bullet is not None and (
            current_name is None or any(value.strip() for value in current_description)
        ):
            finish()
            current_name = bullet.group(1)
            finish()
            continue
        if current_name is not None:
            current_description.append(line)
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


def _display(value: str) -> str:
    return value if value else EMPTY_DISPLAY


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _warning(code: str, message: str) -> MarkdownImportIssue:
    return MarkdownImportIssue(code=code, message=message, severity="warning")


def _error(code: str, message: str) -> MarkdownImportIssue:
    return MarkdownImportIssue(code=code, message=message, severity="error")
