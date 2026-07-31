from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from uuid import UUID

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog
import pytest

from saga_seeker_skill_editor.core.character_sheet import load_character_sheet
from saga_seeker_skill_editor.core.markdown_interchange import (
    MarkdownImportIssue,
    parse_character_markdown,
    render_ai_markdown,
)
from saga_seeker_skill_editor.core.phase0_candidate_sheet import (
    GenerationInputs,
    build_candidate_golden_document,
    render_candidate_html,
)
from saga_seeker_skill_editor.core.personality_catalog import load_personality_catalog
from saga_seeker_skill_editor.gui import main_window as main_window_module
from saga_seeker_skill_editor.gui.main_window import MainWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _canonical_markdown(*, with_memory: bool = False) -> str:
    document = build_candidate_golden_document(
        icon_webp=b"synthetic-webp",
        generation=GenerationInputs(
            uuid_factory=lambda: UUID("123e4567-e89b-42d3-a456-426614174000"),
            clock=lambda: datetime(2026, 7, 24, tzinfo=timezone.utc),
            local_timezone=timezone.utc,
        ),
    )
    data = document["data"]
    data["name"] = "Markdown取込"
    data["profile"]["personality"] = "慎重に行動する"
    data["status"]["strength"] = "A"
    data["skills"] = [
        {
            "id": "source-id",
            "name": "読み込んだスキル",
            "description": "安全な部分復元",
            "type": "",
            "key": "",
        }
    ]
    if with_memory:
        data["memories"] = [
            {
                "id": "memory-synthetic",
                "title": "参照用の思い出",
                "summary": "復元されない概要",
                "location": "合成場所",
                "intent": "合成意図",
                "outcome": "合成結果",
                "tags": ["synthetic"],
                "isPlaceholder": False,
            }
        ]
    return render_ai_markdown(
        load_character_sheet(render_candidate_html(document))
    ).decode("utf-8")


def test_loaded_editor_exposes_both_markdown_import_and_export() -> None:
    _app()
    window = MainWindow()
    assert window.create_new_sheet()

    assert window.import_markdown_button.text() == "Markdownから新規作成"
    assert window.import_markdown_button.isEnabled()
    assert window.export_markdown_button.text() == "Markdownを書き出す"
    assert window.export_markdown_button.isEnabled()
    assert (
        window.import_markdown_button.toolTip()
        != window.export_markdown_button.toolTip()
    )


def test_markdown_export_uses_current_draft_without_changing_html_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    window = MainWindow()
    assert window.create_new_sheet()
    assert window.sheet is not None
    baseline = window.sheet.raw_html
    window.character_details_editor.profile_edits[
        "basicSettings"
    ].setPlainText("Markdownへ出す編集中の設定")
    destination = tmp_path / "character.md"
    monkeypatch.setattr(
        window,
        "_choose_markdown_save_path",
        lambda: destination,
    )

    assert window.export_ai_markdown()

    assert "Markdownへ出す編集中の設定" in destination.read_text(encoding="utf-8")
    assert window.sheet.raw_html == baseline
    assert window.current_path is None
    assert window.unsaved_changes


def test_invalid_markdown_import_keeps_current_sheet_and_draft(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    window = MainWindow()
    assert window.create_new_sheet()
    window.character_details_editor.profile_edits["personality"].setPlainText(
        "保持する編集中の性格"
    )
    original_sheet = window.sheet
    original_draft = window.character_draft
    source = tmp_path / "invalid.md"
    source.write_text(
        _canonical_markdown().replace("- 筋力: A", "- 筋力: Z", 1),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        window,
        "_present_error_dialog",
        lambda _error: None,
    )

    assert not window.import_markdown_path(source)

    assert window.sheet is original_sheet
    assert window.character_draft is original_draft
    assert (
        window.character_details_editor.profile_edits["personality"].toPlainText()
        == "保持する編集中の性格"
    )
    assert window.unsaved_changes


def test_valid_markdown_import_creates_a_new_sheet_after_preview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    window = MainWindow()
    source = tmp_path / "character.md"
    source.write_text(_canonical_markdown(), encoding="utf-8")
    monkeypatch.setattr(
        window,
        "_confirm_markdown_import",
        lambda _plan: True,
    )

    assert window.import_markdown_path(source)

    assert window.current_path is None
    assert window.sheet is not None
    data = window.sheet.data["data"]
    assert data["name"] == "Markdown取込"
    assert data["profile"]["personality"] == "慎重に行動する"
    assert data["status"]["strength"] == "A"
    assert data["status"]["charm"] == "E"
    assert data["skills"] == [
        {
            "id": "sk1",
            "name": "読み込んだスキル",
            "description": "安全な部分復元",
            "type": "",
            "key": "",
        }
    ]
    assert not window.unsaved_changes


def test_markdown_preview_cancel_keeps_current_sheet_and_dirty_draft(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    window = MainWindow()
    assert window.create_new_sheet()
    window.character_details_editor.profile_edits["personality"].setPlainText(
        "キャンセル後も保持する内容"
    )
    original_sheet = window.sheet
    original_draft = window.character_draft
    source = tmp_path / "canonical.md"
    source.write_text(_canonical_markdown(), encoding="utf-8")
    monkeypatch.setattr(window, "_confirm_markdown_import", lambda _plan: False)

    assert not window.import_markdown_path(source)

    assert window.sheet is original_sheet
    assert window.character_draft is original_draft
    assert window.unsaved_changes
    assert (
        window.character_details_editor.profile_edits["personality"].toPlainText()
        == "キャンセル後も保持する内容"
    )


def test_legacy_markdown_is_not_parsed_before_explicit_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    window = MainWindow()
    source = tmp_path / "legacy.md"
    source.write_text("## キャラクター名\n\n旧形式\n", encoding="utf-8")
    confirmation_kinds = []
    preview_called = False

    def reject_legacy(kind) -> bool:
        confirmation_kinds.append(kind)
        return False

    def unexpected_preview(_plan) -> bool:
        nonlocal preview_called
        preview_called = True
        return False

    monkeypatch.setattr(window, "_confirm_legacy_markdown_parse", reject_legacy)
    monkeypatch.setattr(window, "_confirm_markdown_import", unexpected_preview)
    monkeypatch.setattr(window, "_present_error_dialog", lambda _error: None)

    assert not window.import_markdown_path(source)
    assert len(confirmation_kinds) == 1
    assert not preview_called


def test_confirmed_legacy_markdown_reaches_detailed_preview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    window = MainWindow()
    source = tmp_path / "legacy.md"
    source.write_text(
        """<!-- saga-seeker-ai-markdown:1 -->
## キャラクター名

旧形式取込

## キャラクター詳細

### 基本設定

旧形式の設定

## ステータス

- 筋力: A

## スキル

### 旧形式スキル

説明
""",
        encoding="utf-8",
    )
    confirmations = []
    previews = []
    monkeypatch.setattr(
        window,
        "_confirm_legacy_markdown_parse",
        lambda detection: confirmations.append(detection.kind) or True,
    )
    monkeypatch.setattr(
        window,
        "_confirm_markdown_import",
        lambda plan: previews.append(plan) or True,
    )

    assert window.import_markdown_path(source)
    assert len(confirmations) == 1
    assert len(previews) == 1
    assert previews[0].legacy_format
    assert window.sheet is not None
    assert window.sheet.data["data"]["name"] == "旧形式取込"


def test_markdown_preview_explicitly_reports_memories_are_not_restored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    window = MainWindow()
    source = tmp_path / "canonical.md"
    source.write_text(
        _canonical_markdown(with_memory=True),
        encoding="utf-8",
    )
    shown_text = []

    def capture_dialog(dialog):
        shown_text.append(dialog.preview_text.toPlainText())
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(
        main_window_module.MarkdownImportPreviewDialog,
        "exec",
        capture_dialog,
    )

    assert not window.import_markdown_path(source)
    assert len(shown_text) == 1
    assert "形式: AI向けMarkdown形式 v2" in shown_text[0]
    assert "思い出: 1件検出" in shown_text[0]
    assert "取込結果: 復元されません" in shown_text[0]


def test_markdown_preview_exposes_full_long_values_and_all_warnings() -> None:
    plan = parse_character_markdown(
        _canonical_markdown().encode("utf-8"),
        catalog=load_personality_catalog(),
    )
    long_profile = "長いプロフィール" * 100
    long_description = "長いスキル説明" * 100
    plan.profile["basicSettings"] = long_profile
    object.__setattr__(
        plan,
        "skills",
        (type(plan.skills[0])(plan.skills[0].name, long_description),),
    )
    warnings = tuple(
        MarkdownImportIssue(f"warning-{index}", f"警告全文 {index}", "warning")
        for index in range(1, 22)
    )
    object.__setattr__(plan, "issues", warnings)

    preview = main_window_module.format_markdown_import_preview(plan)

    assert long_profile in preview
    assert long_description in preview
    assert "警告全文 21" in preview
    assert "画像" in preview
    assert "内部ID" in preview
    assert "タイムスタンプ" in preview
    assert "魅力" in preview
    assert "スキル種別" in preview


def test_markdown_import_uses_a_scrollable_dedicated_preview_dialog() -> None:
    _app()
    dialog_type = getattr(main_window_module, "MarkdownImportPreviewDialog", None)
    assert dialog_type is not None

    plan = parse_character_markdown(
        _canonical_markdown(with_memory=True).encode("utf-8"),
        catalog=load_personality_catalog(),
    )
    dialog = dialog_type(plan)

    assert dialog.preview_text.isReadOnly()
    assert dialog.preview_text.toPlainText() == main_window_module.format_markdown_import_preview(plan)
    assert dialog.preview_text.textInteractionFlags()
    assert dialog.cancel_button.isDefault()
    assert dialog.cancel_button.autoDefault()
    assert not dialog.confirm_button.isDefault()


@pytest.mark.parametrize(
    "legacy_body",
    (
        "## キャラクター詳細\n\n### 基本設定\n\n設定\n\n"
        "### 補足情報\n\n消える本文\n",
        "### 補足情報\n\n消える本文\n\n## キャラクター名\n\n復元候補\n",
    ),
)
def test_legacy_unknown_heading_error_keeps_current_sheet_and_dirty_draft(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    legacy_body: str,
) -> None:
    _app()
    window = MainWindow()
    assert window.create_new_sheet()
    window.character_details_editor.profile_edits["personality"].setPlainText(
        "保持する未保存内容"
    )
    original_sheet = window.sheet
    original_draft = window.character_draft
    source = tmp_path / "legacy-unknown-heading.md"
    source.write_text(legacy_body, encoding="utf-8")
    monkeypatch.setattr(window, "_confirm_legacy_markdown_parse", lambda _kind: True)
    monkeypatch.setattr(window, "_present_error_dialog", lambda _error: None)
    shown_issues = []
    monkeypatch.setattr(
        window,
        "_present_markdown_import_issues",
        lambda plan: shown_issues.append(plan),
    )
    preview_calls = []
    monkeypatch.setattr(
        window,
        "_confirm_markdown_import",
        lambda plan: preview_calls.append(plan) or False,
    )

    assert not window.import_markdown_path(source)
    assert preview_calls == []
    assert len(shown_issues) == 1
    assert window.sheet is original_sheet
    assert window.character_draft is original_draft
    assert window.unsaved_changes
    assert (
        window.character_details_editor.profile_edits["personality"].toPlainText()
        == "保持する未保存内容"
    )
