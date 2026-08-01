from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from saga_seeker_skill_editor.core.character_sheet import load_character_sheet
from saga_seeker_skill_editor.core.markdown_interchange import (
    MarkdownFormatKind,
    MarkdownImportError,
    create_character_sheet_from_markdown,
    detect_markdown_format,
    parse_character_markdown,
    render_ai_markdown,
)
from saga_seeker_skill_editor.core.personality_catalog import (
    load_personality_catalog,
)
from saga_seeker_skill_editor.core.phase0_candidate_sheet import (
    GenerationInputs,
    build_candidate_golden_document,
    make_empty_placeholder_memory,
    render_candidate_html,
)
from saga_seeker_skill_editor.core.skill_classifier import SkillKind


def _generation() -> GenerationInputs:
    return GenerationInputs(
        uuid_factory=lambda: UUID("123e4567-e89b-42d3-a456-426614174000"),
        clock=lambda: datetime(
            2026,
            7,
            24,
            3,
            4,
            5,
            123456,
            tzinfo=timezone.utc,
        ),
        local_timezone=timezone(timedelta(hours=9)),
    )


def _rich_sheet():
    catalog = load_personality_catalog()
    document = build_candidate_golden_document(
        icon_webp=b"synthetic-webp",
        generation=_generation(),
    )
    data = document["data"]
    data["name"] = "異界実況スレ"
    data["profile"] = {
        "basicSettings": "基本\n設定",
        "appearance": "外見",
        "personality": "性格",
        "speechStyle": "口調",
        "background": "経歴",
        "talentsAndRole": "特技と役割",
        "otherFeatures": "その他",
    }
    data["status"] = {
        "strength": "S",
        "endurance": "A",
        "intelligence": "B",
        "mentalStrength": "C",
        "agility": "D",
        "charm": "S",
        "luck": "E",
    }
    data["skills"] = [
        {
            "id": "default_internal_id",
            "name": "既定スキル",
            "description": "既定スキルの詳細",
            "type": "default",
            "key": "default-key",
        },
        {
            "id": "sk2",
            "name": "オリジナルスキル",
            "description": "HTMLだけでなくJSONの詳細も保持する",
            "type": "",
            "key": "",
        },
    ]
    data["personalities"] = [catalog[0].as_dict(), catalog[30].as_dict()]
    data["memories"] = [
        {
            "id": f"memory-{index}",
            "title": f"思い出 {index}",
            "summary": f"概要 {index}",
            "location": f"場所 {index}",
            "intent": f"意図 {index}",
            "outcome": f"結果 {index}",
            "tags": ["重複", "重複", " 前後空白 "],
            "isPlaceholder": False,
        }
        for index in range(7)
    ]
    data["memories"].insert(1, make_empty_placeholder_memory())
    return load_character_sheet(render_candidate_html(document))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            b"<!-- saga-seeker-ai-markdown:2 -->\n",
            MarkdownFormatKind.CANONICAL_V2,
        ),
        (
            b"\xef\xbb\xbf<!-- saga-seeker-ai-markdown:2 -->\r",
            MarkdownFormatKind.CANONICAL_V2,
        ),
        (
            b"<!-- saga-seeker-ai-markdown:1 -->\n",
            MarkdownFormatKind.LEGACY_MARKED_V1,
        ),
        (b"# markerless\n", MarkdownFormatKind.LEGACY_UNMARKED),
        (
            b"\n<!-- saga-seeker-ai-markdown:2 -->\n",
            MarkdownFormatKind.INVALID_MARKER_POSITION,
        ),
        (
            b"<!-- saga-seeker-ai-markdown:99 -->\n",
            MarkdownFormatKind.UNKNOWN_VERSION,
        ),
        (
            b"<!-- saga-seeker-ai-markdown:2-->\n",
            MarkdownFormatKind.UNKNOWN_VERSION,
        ),
        (
            b"<!-- saga-seeker-ai-markdown: -->\n",
            MarkdownFormatKind.UNKNOWN_VERSION,
        ),
        (
            b"<!-- saga-seeker-ai-markdown:2 -->\n"
            b"<!-- saga-seeker-ai-markdown:2 -->\n",
            MarkdownFormatKind.DUPLICATE_MARKER,
        ),
        (
            b"<!-- saga-seeker-ai-markdown:2 -->\n"
            b"<!-- saga-seeker-ai-markdown:1 -->\n",
            MarkdownFormatKind.MIXED_VERSION_MARKERS,
        ),
        (
            b"<!-- saga-seeker-text:start -->\n"
            b"<!-- saga-seeker-ai-markdown:2 -->\n"
            b"<!-- saga-seeker-text:end -->\n",
            MarkdownFormatKind.LEGACY_UNMARKED,
        ),
        (
            b"<!-- saga-seeker-text:start -->\nunterminated\n",
            MarkdownFormatKind.MALFORMED_TEXT_BLOCK,
        ),
    ],
)
def test_format_detection_classifies_only_markers_outside_text_blocks(
    raw: bytes,
    expected: MarkdownFormatKind,
) -> None:
    assert detect_markdown_format(raw).kind is expected


def test_format_detection_ignores_other_version_markers_inside_v2_text_block() -> None:
    raw = (
        b"<!-- saga-seeker-ai-markdown:2 -->\n"
        b"<!-- saga-seeker-text:start -->\n"
        b"<!-- saga-seeker-ai-markdown:1 -->\n"
        b"<!-- saga-seeker-ai-markdown:99 -->\n"
        b"<!-- saga-seeker-text:end -->\n"
    )

    assert detect_markdown_format(raw).kind is MarkdownFormatKind.CANONICAL_V2


def test_ai_markdown_exports_semantic_sections_without_internal_identifiers() -> None:
    markdown = render_ai_markdown(_rich_sheet()).decode("utf-8")

    assert markdown.startswith(
        "<!-- saga-seeker-ai-markdown:2 -->\n"
        "# Saga & Seeker キャラクター\n"
    )
    assert "## キャラクター名\n<!-- saga-seeker-text:start -->" in markdown
    assert (
        "### 基本設定\n"
        "<!-- saga-seeker-text:start -->\n"
        "基本\n設定\n"
        "<!-- saga-seeker-text:end -->"
    ) in markdown
    assert "- 筋力: S" in markdown
    assert "- 運: E" in markdown
    assert "### スキル 1\n#### 名前" in markdown
    assert "### スキル 2\n#### 名前" in markdown
    assert "既定スキルの詳細" in markdown
    assert "HTMLだけでなくJSONの詳細も保持する" in markdown
    assert f"- 枠1: {load_personality_catalog()[0].name}" in markdown
    assert "### 思い出 7" in markdown
    assert (
        "> このセクションはAI参照用です。"
        "Markdownから新規作成しても思い出は復元されません。"
    ) in markdown
    assert "空白保持枠" not in markdown
    assert "characterId" not in markdown
    assert "default_internal_id" not in markdown
    assert "data:image/webp" not in markdown
    assert "魅力" not in markdown


def test_canonical_markdown_can_restore_its_supported_subset() -> None:
    sheet = _rich_sheet()
    sheet.data["data"]["profile"]["basicSettings"] = (
        "\n先頭\n\n"
        "<!-- saga-seeker-text:start -->\n"
        "<!-- saga-seeker-text:end -->\n"
        "<!-- saga-seeker-ai-markdown:1 -->\n"
        "path\\name\n"
        "### 本文中の見出し\n"
    )
    sheet.data["data"]["profile"]["appearance"] = ""
    sheet.data["data"]["profile"]["personality"] = "（未入力）"
    sheet.data["data"]["profile"]["speechStyle"] = "CRLF\r\nCR\rlast"
    sheet.data["data"]["skills"][1]["description"] = (
        "説明の導入\n\n- 箇条書き1\n## 本文中のH2\n- 箇条書き2"
    )

    plan = parse_character_markdown(
        render_ai_markdown(sheet),
        catalog=load_personality_catalog(),
    )

    assert plan.can_create
    assert not plan.legacy_format
    assert plan.format_kind is MarkdownFormatKind.CANONICAL_V2
    assert plan.name == "異界実況スレ"
    assert plan.profile["basicSettings"] == (
        "\n先頭\n\n"
        "<!-- saga-seeker-text:start -->\n"
        "<!-- saga-seeker-text:end -->\n"
        "<!-- saga-seeker-ai-markdown:1 -->\n"
        "path\\name\n"
        "### 本文中の見出し\n"
    )
    assert plan.profile["appearance"] == ""
    assert plan.profile["personality"] == "（未入力）"
    assert plan.profile["speechStyle"] == "CRLF\nCR\nlast"
    assert plan.status["strength"] == "S"
    assert [skill.name for skill in plan.skills] == [
        "既定スキル",
        "オリジナルスキル",
    ]
    assert plan.skills[1].description == (
        "説明の導入\n\n- 箇条書き1\n## 本文中のH2\n- 箇条書き2"
    )
    assert plan.memory_count == 7

    created = load_character_sheet(
        create_character_sheet_from_markdown(
            plan,
            icon_webp=b"default-webp",
            generation=_generation(),
        )
    )
    assert created.data["data"]["memories"] == []
    assert created.data["data"]["profile"]["personality"] == "（未入力）"


@pytest.mark.parametrize(
    "value",
    [
        "\\q",
        "trailing\\",
    ],
)
def test_canonical_text_block_rejects_unknown_escapes(value: str) -> None:
    raw = render_ai_markdown(_rich_sheet()).decode("utf-8")
    raw = raw.replace(
        "<!-- saga-seeker-text:start -->\n異界実況スレ\n"
        "<!-- saga-seeker-text:end -->",
        "<!-- saga-seeker-text:start -->\n"
        + value
        + "\n<!-- saga-seeker-text:end -->",
        1,
    )

    with pytest.raises(MarkdownImportError, match="エスケープ"):
        parse_character_markdown(
            raw.encode("utf-8"),
            catalog=load_personality_catalog(),
        )


def test_canonical_character_and_skill_names_must_be_single_line() -> None:
    raw = render_ai_markdown(_rich_sheet()).decode("utf-8")
    raw = raw.replace(
        "<!-- saga-seeker-text:start -->\n異界実況スレ\n"
        "<!-- saga-seeker-text:end -->",
        "<!-- saga-seeker-text:start -->\nfirst\nsecond\n"
        "<!-- saga-seeker-text:end -->",
        1,
    )

    with pytest.raises(MarkdownImportError, match="単一行"):
        parse_character_markdown(
            raw.encode("utf-8"),
            catalog=load_personality_catalog(),
        )


def test_canonical_skill_name_must_be_single_line() -> None:
    raw = render_ai_markdown(_rich_sheet()).decode("utf-8")
    raw = raw.replace(
        "#### 名前\n"
        "<!-- saga-seeker-text:start -->\n既定スキル\n"
        "<!-- saga-seeker-text:end -->",
        "#### 名前\n"
        "<!-- saga-seeker-text:start -->\nfirst\nsecond\n"
        "<!-- saga-seeker-text:end -->",
        1,
    )

    with pytest.raises(MarkdownImportError, match="単一行"):
        parse_character_markdown(
            raw.encode("utf-8"),
            catalog=load_personality_catalog(),
        )


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("## ステータス", "## 能力値", "ステータス"),
        ("### 基本設定", "### 基礎設定", "基本設定"),
        (
            "> このセクションはAI参照用です。"
            "Markdownから新規作成しても思い出は復元されません。",
            "> 思い出を復元します。",
            "セクションはAI参照用",
        ),
    ],
)
def test_canonical_structure_requires_exact_fixed_lines(
    old: str,
    new: str,
    message: str,
) -> None:
    raw = render_ai_markdown(_rich_sheet()).decode("utf-8").replace(old, new, 1)

    with pytest.raises(MarkdownImportError, match=message):
        parse_character_markdown(
            raw.encode("utf-8"),
            catalog=load_personality_catalog(),
        )


def test_canonical_unescaped_start_marker_inside_text_is_rejected() -> None:
    raw = render_ai_markdown(_rich_sheet()).decode("utf-8")
    raw = raw.replace(
        "<!-- saga-seeker-text:start -->\n異界実況スレ\n"
        "<!-- saga-seeker-text:end -->",
        "<!-- saga-seeker-text:start -->\n"
        "<!-- saga-seeker-text:start -->\n"
        "<!-- saga-seeker-text:end -->",
        1,
    )

    with pytest.raises(MarkdownImportError, match="開始マーカー"):
        parse_character_markdown(
            raw.encode("utf-8"),
            catalog=load_personality_catalog(),
        )


def test_legacy_markdown_is_partially_imported_as_a_new_safe_sheet() -> None:
    catalog = load_personality_catalog()
    raw = f"""## キャラクター名

復元候補

## キャラクター詳細

### 基本設定

設定本文

### 性格

（未入力）

## 性格キーワード

- {catalog[0].name}
- {catalog[30].name}

## ステータス

- 筋力: S
- 運: A

## スキル

### 読み込んだ技

AI向けの説明

### 説明なしの技
""".encode("utf-8")

    with pytest.raises(MarkdownImportError, match="旧形式として解析する"):
        parse_character_markdown(raw, catalog=catalog)

    plan = parse_character_markdown(
        raw,
        catalog=catalog,
        allow_legacy=True,
    )

    assert plan.can_create
    assert plan.legacy_format
    assert plan.name == "復元候補"
    assert plan.profile["basicSettings"] == "設定本文"
    assert plan.profile["personality"] == ""
    assert plan.status["strength"] == "S"
    assert plan.status["luck"] == "A"
    assert [skill.name for skill in plan.skills] == [
        "読み込んだ技",
        "説明なしの技",
    ]
    assert any("（未入力）" in issue.message for issue in plan.issues)

    created = load_character_sheet(
        create_character_sheet_from_markdown(
            plan,
            icon_webp=b"default-webp",
            generation=_generation(),
        )
    )
    data = created.data["data"]
    assert data["name"] == "復元候補"
    assert data["profile"]["basicSettings"] == "設定本文"
    assert data["profile"]["appearance"] == ""
    assert data["status"]["strength"] == "S"
    assert data["status"]["endurance"] == "E"
    assert data["status"]["charm"] == "E"
    assert data["memories"] == []
    assert [item["id"] for item in data["skills"]] == ["sk1", "sk2"]
    assert all(item["type"] == item["key"] == "" for item in data["skills"])
    assert all(
        entry.classification.kind == SkillKind.ORIGINAL
        for entry in created.entries
    )
    assert [item["id"] for item in data["personalities"]] == [
        catalog[0].id,
        catalog[30].id,
    ]


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("## ステータス\n\n- 筋力: Z\n", "ステータス"),
        ("## 性格キーワード\n\n- 存在しない性格\n", "カタログ"),
        (
            "## スキル\n\n"
            + "\n\n".join(f"### 技{i}\n\n説明" for i in range(7)),
            "6件",
        ),
    ],
)
def test_import_never_silently_repairs_unsupported_values(
    body: str,
    message: str,
) -> None:
    plan = parse_character_markdown(
        body.encode("utf-8"),
        catalog=load_personality_catalog(),
        allow_legacy=True,
    )

    assert not plan.can_create
    assert any(message in issue.message for issue in plan.issues)
    with pytest.raises(MarkdownImportError):
        create_character_sheet_from_markdown(
            plan,
            icon_webp=b"default-webp",
            generation=_generation(),
        )


def test_imported_user_text_is_not_emitted_as_executable_html() -> None:
    sheet = _rich_sheet()
    sheet.data["data"]["name"] = (
        '<img src="https://example.invalid/x" onerror="alert(1)">'
    )
    sheet.data["data"]["profile"]["basicSettings"] = (
        "</script><script>alert(1)</script>"
    )
    plan = parse_character_markdown(
        render_ai_markdown(sheet),
        catalog=load_personality_catalog(),
    )
    created = create_character_sheet_from_markdown(
        plan,
        icon_webp=b"default-webp",
        generation=_generation(),
    )

    assert b'<img src="https://example.invalid/x"' not in created
    assert b"</script><script>alert(1)</script>" not in created
    parsed = load_character_sheet(created)
    assert parsed.data["data"]["name"].startswith("<img ")
    assert parsed.data["data"]["profile"]["basicSettings"] == (
        "</script><script>alert(1)</script>"
    )


def test_legacy_bullet_only_skills_are_ambiguous_errors() -> None:
    plan = parse_character_markdown(
        "## スキル\n\n- 候補A\n- 候補B\n".encode("utf-8"),
        catalog=load_personality_catalog(),
        allow_legacy=True,
    )

    assert not plan.can_create
    assert any(issue.code == "ambiguous-legacy-skill" for issue in plan.issues)


def test_legacy_missing_information_is_warning_not_ambiguity_error() -> None:
    plan = parse_character_markdown(
        "## キャラクター名\n\n旧形式\n".encode("utf-8"),
        catalog=load_personality_catalog(),
        allow_legacy=True,
    )
    warning_codes = {
        issue.code for issue in plan.issues if issue.severity == "warning"
    }

    assert plan.can_create
    assert {
        "legacy-missing-profile",
        "legacy-missing-status",
        "legacy-missing-personality",
        "legacy-image-not-restored",
        "legacy-memories-not-restored",
    }.issubset(warning_codes)


def test_legacy_memory_bullets_are_counted_but_never_restored() -> None:
    plan = parse_character_markdown(
        "## キャラクター名\n\n復元候補\n\n"
        "## 思い出\n\n- 思い出タイトル1\n- 思い出タイトル2\n".encode(
            "utf-8"
        ),
        catalog=load_personality_catalog(),
        allow_legacy=True,
    )

    assert plan.can_create
    assert plan.memory_count == 2
    created = load_character_sheet(
        create_character_sheet_from_markdown(
            plan,
            icon_webp=b"default-webp",
            generation=_generation(),
        )
    )
    assert created.data["data"]["memories"] == []


@pytest.mark.parametrize(
    ("body", "expected_count"),
    (
        ("## 思い出\n", 0),
        ("## 思い出\n\n### 思い出A\n\n本文\n\n### 思い出B\n", 2),
    ),
)
def test_legacy_memory_empty_and_h3_representations_remain_supported(
    body: str,
    expected_count: int,
) -> None:
    plan = parse_character_markdown(
        body.encode("utf-8"),
        catalog=load_personality_catalog(),
        allow_legacy=True,
    )

    assert plan.can_create
    assert plan.memory_count == expected_count


def test_legacy_memory_mixed_bullet_and_h3_representations_are_blocking() -> None:
    plan = parse_character_markdown(
        "## 思い出\n\n### 思い出A\n\n本文\n\n- 思い出タイトルB\n".encode(
            "utf-8"
        ),
        catalog=load_personality_catalog(),
        allow_legacy=True,
    )

    assert not plan.can_create
    assert any(
        issue.code == "ambiguous-legacy-memory-format"
        for issue in plan.issues
    )


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (
            "## キャラクター名\n\nfirst\nsecond\n",
            "legacy-multiline-name",
        ),
        (
            "## ステータス\n\nunknown line\n",
            "invalid-status-line",
        ),
        (
            "## キャラクター詳細\n\n### 性格\n\nA\n"
            "### 性格\n\nB\n",
            "duplicate-profile-field",
        ),
    ],
)
def test_legacy_ambiguous_structures_are_errors(
    body: str,
    code: str,
) -> None:
    plan = parse_character_markdown(
        body.encode("utf-8"),
        catalog=load_personality_catalog(),
        allow_legacy=True,
    )

    assert not plan.can_create
    assert any(issue.code == code for issue in plan.issues)


@pytest.mark.parametrize(
    "unknown_heading",
    ("### 補足情報", "## 補足情報"),
)
def test_legacy_unknown_structural_heading_is_a_blocking_error(
    unknown_heading: str,
) -> None:
    raw = f"""## キャラクター名

復元候補

## キャラクター詳細

### 基本設定

ここは残る

{unknown_heading}

この文章を黙って捨ててはならない

## ステータス

- 筋力: A
""".encode("utf-8")

    plan = parse_character_markdown(
        raw,
        catalog=load_personality_catalog(),
        allow_legacy=True,
    )

    assert not plan.can_create
    assert any(
        issue.code in {"unknown-legacy-section", "unknown-profile-field"}
        for issue in plan.issues
        if issue.severity == "error"
    )


def test_legacy_unknown_heading_without_body_is_still_a_blocking_error() -> None:
    plan = parse_character_markdown(
        "## キャラクター詳細\n\n### 基本設定\n\n設定\n\n### 補足情報\n".encode(
            "utf-8"
        ),
        catalog=load_personality_catalog(),
        allow_legacy=True,
    )

    assert not plan.can_create
    assert any(issue.code == "unknown-profile-field" for issue in plan.issues)


@pytest.mark.parametrize(
    "body",
    (
        "### 補足情報\n\nこの文章を黙って捨ててはならない\n\n"
        "## キャラクター名\n\n復元候補\n",
        "## キャラクター名\n\n復元候補\n\n"
        "## 未知の区切り\n\n区切り本文\n\n"
        "### 補足情報\n\nこの文章を黙って捨ててはならない\n\n"
        "## ステータス\n\n- 筋力: A\n",
    ),
)
def test_legacy_orphan_h3_without_recognized_h2_is_a_blocking_error(
    body: str,
) -> None:
    plan = parse_character_markdown(
        body.encode("utf-8"),
        catalog=load_personality_catalog(),
        allow_legacy=True,
    )

    assert not plan.can_create
    assert any(issue.code == "orphan-legacy-h3" for issue in plan.issues)


@pytest.mark.parametrize(
    ("body", "expected_name"),
    (
        ("## キャラクター名\n\n### 補足情報\n", ""),
        (
            "## キャラクター名\n\n復元候補\n\n"
            "### 補足情報\n\n名前へ連結してはならない\n",
            "復元候補",
        ),
    ),
)
def test_legacy_h3_under_character_name_is_a_blocking_error(
    body: str,
    expected_name: str,
) -> None:
    plan = parse_character_markdown(
        body.encode("utf-8"),
        catalog=load_personality_catalog(),
        allow_legacy=True,
    )

    assert not plan.can_create
    assert plan.name == expected_name
    issue = next(
        issue
        for issue in plan.issues
        if issue.code == "invalid-legacy-h3-owner"
    )
    assert "補足情報" in issue.message
    assert "キャラクター名" in issue.message


@pytest.mark.parametrize("section", ("性格キーワード", "ステータス"))
def test_legacy_h3_under_non_h3_section_is_a_blocking_error(
    section: str,
) -> None:
    plan = parse_character_markdown(
        f"## {section}\n\n### 補足情報\n\n解釈してはならない\n".encode(
            "utf-8"
        ),
        catalog=load_personality_catalog(),
        allow_legacy=True,
    )

    assert not plan.can_create
    issue = next(
        issue
        for issue in plan.issues
        if issue.code == "invalid-legacy-h3-owner"
    )
    assert "補足情報" in issue.message
    assert section in issue.message


def test_legacy_plain_preamble_text_remains_accepted() -> None:
    plan = parse_character_markdown(
        "これは構造見出しではない前文です\n\n"
        "## キャラクター名\n\n復元候補\n".encode("utf-8"),
        catalog=load_personality_catalog(),
        allow_legacy=True,
    )

    assert plan.can_create
    assert plan.name == "復元候補"
    assert not any(
        issue.code in {"orphan-legacy-h3", "invalid-legacy-h3-owner"}
        for issue in plan.issues
    )


def test_legacy_all_seven_official_profile_fields_remain_supported() -> None:
    labels = [label for _key, label in (
        ("basicSettings", "基本設定"),
        ("appearance", "外見"),
        ("personality", "性格"),
        ("speechStyle", "口調"),
        ("background", "経歴"),
        ("talentsAndRole", "特技と役割"),
        ("otherFeatures", "その他の特徴"),
    )]
    body = "\n\n".join(f"### {label}\n\n{label}の本文" for label in labels)
    plan = parse_character_markdown(
        f"## キャラクター詳細\n\n{body}\n".encode("utf-8"),
        catalog=load_personality_catalog(),
        allow_legacy=True,
    )

    assert plan.can_create
    assert plan.profile["otherFeatures"] == "その他の特徴の本文"


def test_canonical_personality_lines_reject_internal_blank_lines() -> None:
    sheet = _rich_sheet()
    raw = render_ai_markdown(sheet).decode("utf-8")
    raw = raw.replace(
        "- 枠1: 勇敢\n- 枠2:",
        "- 枠1: 勇敢\n\n- 枠2:",
        1,
    )

    with pytest.raises(MarkdownImportError, match="性格キーワード.*空行"):
        parse_character_markdown(
            raw.encode("utf-8"),
            catalog=load_personality_catalog(),
        )


@pytest.mark.parametrize("count", [0, 1, 6])
def test_canonical_personality_writer_shape_accepts_zero_one_or_six_entries(
    count: int,
) -> None:
    sheet = _rich_sheet()
    raw = render_ai_markdown(sheet).decode("utf-8")
    before, remainder = raw.split("## 性格キーワード\n", 1)
    _old_personalities, after = remainder.split("## ステータス\n", 1)
    catalog = load_personality_catalog()
    personality_lines = "".join(
        f"- 枠{index}: {catalog[index - 1].name}\n"
        for index in range(1, count + 1)
    )
    candidate = (
        before
        + "## 性格キーワード\n\n"
        + personality_lines
        + "\n## ステータス\n"
        + after
    )

    plan = parse_character_markdown(candidate.encode("utf-8"), catalog=catalog)

    assert len(plan.personalities) == count
