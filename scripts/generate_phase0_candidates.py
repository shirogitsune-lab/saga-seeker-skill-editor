"""Generate private Phase 0 candidate sheets for manual game validation."""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
from uuid import UUID

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QColor, QImage, QImageWriter

from saga_seeker_skill_editor.core.character_sheet import CharacterSheetError, load_character_sheet
from saga_seeker_skill_editor.core.phase0_candidate_sheet import (
    GenerationInputs,
    build_candidate_golden_document,
    build_full_probe_document,
    render_candidate_html,
)
from saga_seeker_skill_editor.core.skill_classifier import SkillKind


FIXED_NOW = datetime(2026, 7, 24, 3, 4, 5, 123456, tzinfo=timezone.utc)
JST = timezone(timedelta(hours=9))
UUIDS = (
    UUID("123e4567-e89b-42d3-a456-426614174000"),
    UUID("223e4567-e89b-42d3-a456-426614174000"),
    UUID("323e4567-e89b-42d3-a456-426614174000"),
    UUID("423e4567-e89b-42d3-a456-426614174000"),
    UUID("523e4567-e89b-42d3-a456-426614174000"),
    UUID("623e4567-e89b-42d3-a456-426614174000"),
    UUID("723e4567-e89b-42d3-a456-426614174000"),
)


def _uuid_factory(values: Iterator[UUID]):
    return lambda: next(values)


def _default_icon_webp() -> bytes:
    image = QImage(512, 512, QImage.Format.Format_RGB32)
    image.fill(QColor("#6b7280"))
    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise RuntimeError("could not open the icon output buffer")
    writer = QImageWriter(buffer, b"webp")
    writer.setQuality(90)
    if not writer.write(image):
        raise RuntimeError(f"could not encode the Phase 0 WebP icon: {writer.errorString()}")
    buffer.close()
    return bytes(byte_array)


def _find_private_catalog_values(
    input_dir: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    default_skill: dict[str, object] | None = None
    personality: dict[str, object] | None = None
    for path in sorted(input_dir.glob("*.html")):
        try:
            sheet = load_character_sheet(path.read_bytes())
        except CharacterSheetError:
            continue
        if default_skill is None:
            match = next(
                (
                    entry.skill
                    for entry in sheet.entries
                    if entry.classification.kind == SkillKind.DEFAULT
                ),
                None,
            )
            if match is not None:
                default_skill = dict(match)
        if personality is None and sheet.personality_entries:
            personality = dict(sheet.personality_entries[0].keyword)
        if default_skill is not None and personality is not None:
            return default_skill, personality
    raise RuntimeError(
        "private input did not contain both a safely recognized default skill "
        "and a catalog-backed personality keyword"
    )


def _write_outputs(input_dir: Path, output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    icon_webp = _default_icon_webp()
    default_skill, personality = _find_private_catalog_values(input_dir)

    blank_generation = GenerationInputs(
        uuid_factory=_uuid_factory(iter(UUIDS[:1])),
        clock=lambda: FIXED_NOW,
        local_timezone=JST,
    )
    probe_generation = GenerationInputs(
        uuid_factory=_uuid_factory(iter(UUIDS[1:])),
        clock=lambda: FIXED_NOW,
        local_timezone=JST,
    )
    blank_document = build_candidate_golden_document(
        icon_webp=icon_webp,
        generation=blank_generation,
    )
    probe_document = build_full_probe_document(
        icon_webp=icon_webp,
        generation=probe_generation,
        default_skill=default_skill,
        personality_keyword=personality,
    )
    outputs = {
        "phase0_candidate_blank.html": render_candidate_html(blank_document),
        "phase0_full_probe.html": render_candidate_html(probe_document),
    }
    hashes: dict[str, str] = {}
    for name, raw in outputs.items():
        path = output_dir / name
        path.write_bytes(raw)
        hashes[name] = hashlib.sha256(raw).hexdigest()

    instructions = """# Phase 0 ゲーム内手動確認

このディレクトリは非公開の一時検証物です。リポジトリへコミットしないでください。

## 1. phase0_candidate_blank.html

- ゲームのキャラクターシート読込から読み込む
- 空の名前、7プロフィール、全Eステータス、無地画像を確認する
- スキル、性格、思い出が空であることを確認する
- ゲームから別名で再出力する

## 2. phase0_full_probe.html

- ゲームへ読み込む
- 名前、全プロフィール、S〜Eのステータスを確認する
- デフォルトスキル、オリジナルスキル、未使用スキル枠を確認する
- 性格キーワードを確認する
- 通常思い出と空白保持枠を確認する
- スクロールして7件目・8件目の扱いを確認する
- ゲームから別名で再出力する

## 返却してほしい結果

- 両ファイルが読み込めたか
- 表示や編集画面に欠落・誤認識があったか
- ゲームから再出力できたか
- 再出力した2つのHTMLファイル

手動結果が承認されるまでPhase 1以降へ進みません。
"""
    (output_dir / "PHASE0_MANUAL_CHECK.md").write_text(instructions, encoding="utf-8")
    manifest = {
        "candidateStatus": "provisional-until-game-round-trip",
        "generatedAt": "2026-07-24T03:04:05.1234560Z",
        "files": hashes,
        "defaultIcon": {
            "mime": "image/webp",
            "width": 512,
            "height": 512,
            "sha256": hashlib.sha256(icon_webp).hexdigest(),
        },
        "probe": {
            "skillJsonCount": 2,
            "skillHtmlSlotCount": 6,
            "personalityJsonCount": 1,
            "personalityHtmlSlotCount": 6,
            "memoryJsonCount": 8,
            "memoryHtmlSlotCount": 6,
        },
    }
    (output_dir / "phase0_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("private_input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    if not args.private_input_dir.is_dir():
        parser.error(f"private input directory does not exist: {args.private_input_dir}")
    try:
        manifest = _write_outputs(args.private_input_dir, args.output_dir)
    except Exception as error:
        print(f"Phase 0 generation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
