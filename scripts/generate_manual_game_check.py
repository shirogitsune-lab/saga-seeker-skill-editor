"""Generate an anonymous HTML sheet and checklist for manual game validation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from saga_seeker_skill_editor.core.character_sheet import (
    CharacterSheetDraft,
    load_character_sheet,
    render_character_sheet,
)
from saga_seeker_skill_editor.core.phase0_candidate_sheet import (
    GenerationInputs,
    build_candidate_golden_document,
    render_candidate_html,
)
from saga_seeker_skill_editor.resources import resource_path


HTML_NAME = "SagaSeekerSkillEditor_v2_profile_br_manual_check.html"
CHECKLIST_NAME = "SagaSeekerSkillEditor_v2_manual_checklist.md"
EXPECTED_PROFILE = "1行目: <探索者> & 仲間\n2行目: 引用符 \"確認\"\n\n4行目: 空行の後"


def generate(destination: Path) -> tuple[Path, Path]:
    destination.mkdir(parents=True, exist_ok=True)
    generation = GenerationInputs(
        uuid_factory=lambda: UUID("123e4567-e89b-42d3-a456-426614174000"),
        clock=lambda: datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc),
        local_timezone=timezone.utc,
    )
    document = build_candidate_golden_document(
        icon_webp=resource_path("assets/カナリア.webp").read_bytes(),
        generation=generation,
    )
    data = document["data"]
    assert isinstance(data, dict)
    data["name"] = "匿名改行確認"
    data["profile"] = {
        "basicSettings": "編集前の合成テキスト",
        "appearance": "青い外套\n銀色の留め具",
        "personality": "慎重\n協力的",
        "speechStyle": "短く明瞭に話す",
        "background": "合成都市で地図作りを学んだ",
        "talentsAndRole": "調査と支援",
        "otherFeatures": "実在の人物・場所とは無関係",
    }
    data["status"] = {
        "strength": "C",
        "endurance": "B",
        "intelligence": "A",
        "mentalStrength": "B",
        "agility": "C",
        "charm": "E",
        "luck": "D",
    }
    data["skills"] = [
        {
            "id": "manual-check-skill",
            "name": "合成テスト技能",
            "description": "ゲーム取込後に表示だけ確認する安全な合成技能。",
            "type": "",
            "key": "",
        }
    ]
    data["personalities"] = [
        {"id": 1, "name": "勇敢", "type": "力", "karma": "美徳"}
    ]
    data["memories"] = []

    baseline = load_character_sheet(render_candidate_html(document))
    draft = CharacterSheetDraft.from_sheet(baseline)
    draft.set_profile("basicSettings", EXPECTED_PROFILE)
    rendered = render_character_sheet(baseline, draft)
    verified = load_character_sheet(rendered)
    actual = verified.data["data"]["profile"]["basicSettings"]
    if actual != EXPECTED_PROFILE:
        raise RuntimeError("合成HTMLのプロフィール改行を再読込できません")
    expected_visible_html = "&lt;探索者&gt; &amp; 仲間<br>".encode("utf-8")
    if expected_visible_html not in rendered:
        raise RuntimeError("表示HTMLにエスケープ済みテキストと<br>がありません")

    html_path = destination / HTML_NAME
    checklist_path = destination / CHECKLIST_NAME
    html_path.write_bytes(rendered)
    checklist_path.write_text(
        """# Saga & Seeker ゲーム手動確認チェックリスト

対象は同じフォルダの匿名合成HTMLです。実在のキャラクターデータは含みません。

## 取込前

- [ ] 元のゲームデータをバックアップした
- [ ] `SagaSeekerSkillEditor_v2_profile_br_manual_check.html` を選んだ
- [ ] キャラクター名が「匿名改行確認」である

## ゲームへ取り込んだ後

- [ ] 基本設定が次の4行構造で表示される
  - `1行目: <探索者> & 仲間`
  - `2行目: 引用符 "確認"`
  - 空行
  - `4行目: 空行の後`
- [ ] 外見が2行で表示される
- [ ] 性格が2行で表示される
- [ ] ステータス、合成テスト技能、性格キーワード「勇敢」が表示される
- [ ] 文字化けやHTMLタグの露出がない

## ゲームから再出力した後

- [ ] 再出力HTMLをアプリケーションバージョン 2.1.0で開ける
- [ ] 基本設定の先頭・空行・末尾の意味が維持される
- [ ] 読み取り専用にならない
- [ ] 元の提出HTMLは変更されていない

結果とゲーム側のバージョンは、このチェックリストのコピーへ記録してください。
""",
        encoding="utf-8",
        newline="\n",
    )
    return html_path, checklist_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    html_path, checklist_path = generate(args.destination)
    print(html_path)
    print(checklist_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
