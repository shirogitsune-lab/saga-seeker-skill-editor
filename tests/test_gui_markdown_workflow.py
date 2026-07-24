from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
import pytest

from saga_seeker_skill_editor.gui.main_window import MainWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


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
        "## ステータス\n\n- 筋力: Z\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        window,
        "_present_markdown_import_issues",
        lambda _plan: None,
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
    source.write_text(
        """<!-- saga-seeker-ai-markdown:1 -->
## キャラクター名

Markdown取込

## キャラクター詳細

### 性格

慎重に行動する

## ステータス

- 筋力: A

## スキル

### 読み込んだスキル

安全な部分復元
""",
        encoding="utf-8",
    )
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
