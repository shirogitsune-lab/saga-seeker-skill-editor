from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from saga_seeker_skill_editor.core.character_sheet import load_character_sheet
from saga_seeker_skill_editor.core.markdown_interchange import (
    MarkdownImportError,
    create_character_sheet_from_markdown,
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


def test_ai_markdown_exports_semantic_sections_without_internal_identifiers() -> None:
    markdown = render_ai_markdown(_rich_sheet()).decode("utf-8")

    assert markdown.startswith("<!-- saga-seeker-ai-markdown:1 -->\n")
    assert "## キャラクター名\n\n異界実況スレ" in markdown
    assert "### 基本設定\n\n基本\n設定" in markdown
    assert "- 筋力: S" in markdown
    assert "- 運: E" in markdown
    assert "### 既定スキル\n\n既定スキルの詳細" in markdown
    assert "### オリジナルスキル\n\nHTMLだけでなくJSONの詳細も保持する" in markdown
    assert f"- 枠1: {load_personality_catalog()[0].name}" in markdown
    assert "### 思い出 6" in markdown
    assert "空白保持枠" not in markdown
    assert "characterId" not in markdown
    assert "default_internal_id" not in markdown
    assert "data:image/webp" not in markdown
    assert "魅力" not in markdown


def test_canonical_markdown_can_restore_its_supported_subset() -> None:
    sheet = _rich_sheet()
    sheet.data["data"]["skills"][1]["description"] = (
        "説明の導入\n\n- 箇条書き1\n- 箇条書き2"
    )

    plan = parse_character_markdown(
        render_ai_markdown(sheet),
        catalog=load_personality_catalog(),
    )

    assert plan.can_create
    assert not plan.legacy_format
    assert plan.name == "異界実況スレ"
    assert plan.profile["basicSettings"] == "基本\n設定"
    assert plan.status["strength"] == "S"
    assert [skill.name for skill in plan.skills] == [
        "既定スキル",
        "オリジナルスキル",
    ]
    assert plan.skills[1].description == "説明の導入\n\n- 箇条書き1\n- 箇条書き2"


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

- 説明なしの技
""".encode("utf-8")

    plan = parse_character_markdown(raw, catalog=catalog)

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
    raw = """<!-- saga-seeker-ai-markdown:1 -->
## キャラクター名

<img src="https://example.invalid/x" onerror="alert(1)">

## キャラクター詳細

### 基本設定

</script><script>alert(1)</script>
""".encode("utf-8")
    plan = parse_character_markdown(raw, catalog=load_personality_catalog())
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
