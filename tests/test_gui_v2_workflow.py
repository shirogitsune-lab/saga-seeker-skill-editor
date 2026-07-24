from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from uuid import UUID

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
import pytest

from saga_seeker_skill_editor.core.character_sheet import (
    CharacterSheetDraft,
    create_character_sheet,
    load_character_sheet,
    render_character_sheet,
)
from saga_seeker_skill_editor.core.phase0_candidate_sheet import GenerationInputs
from saga_seeker_skill_editor.gui.main_window import MainWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


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


def _named_sheet_bytes() -> bytes:
    sheet = load_character_sheet(
        create_character_sheet(
            icon_webp=b"synthetic-webp",
            generation=_generation(),
        )
    )
    draft = CharacterSheetDraft.from_sheet(sheet)
    draft.set_name("V2 Workflow")
    return render_character_sheet(sheet, draft)


def test_start_screen_can_create_new_sheet_and_editor_has_five_tabs() -> None:
    _app()
    window = MainWindow()

    assert window.create_new_sheet()

    assert window.sheet is not None
    assert window.current_path is None
    assert window.edit_tabs.count() == 5
    assert [
        window.edit_tabs.tabText(index)
        for index in range(window.edit_tabs.count())
    ] == ["基本情報", "ステータス", "スキル", "性格キーワード", "思い出"]
    assert window.windowTitle() == "Saga & Seeker キャラクターシートエディター"
    assert window.save_button.isEnabled()


def test_unchanged_save_is_exact_and_destination_becomes_new_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    raw = _named_sheet_bytes()
    source = tmp_path / "source.html"
    destination = tmp_path / "saved.html"
    source.write_bytes(raw)
    window = MainWindow()
    assert window.load_path(source)
    monkeypatch.setattr(window, "_choose_save_path", lambda: destination)

    assert window.save_as()

    assert destination.read_bytes() == raw
    assert window.current_path == destination
    assert window.sheet is not None
    assert window.sheet.raw_html == raw
    assert not window.unsaved_changes


def test_v2_basic_status_and_memory_edits_save_together(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    source = tmp_path / "source.html"
    destination = tmp_path / "saved.html"
    source.write_bytes(_named_sheet_bytes())
    window = MainWindow()
    assert window.load_path(source)
    window.character_details_editor.profile_edits["background"].insertPlainText(
        "編集済み経歴"
    )
    window.status_editor.rank_boxes["luck"].setCurrentText("A")
    window.memory_editor.add_normal_memory()
    window.memory_editor.field_edits["title"].insert("編集済み思い出")
    monkeypatch.setattr(window, "_choose_save_path", lambda: destination)

    assert window.save_as()

    saved = load_character_sheet(destination.read_bytes())
    assert saved.data["data"]["profile"]["background"] == "編集済み経歴"
    assert saved.data["data"]["status"]["luck"] == "A"
    assert saved.data["data"]["memories"][0]["title"] == "編集済み思い出"


def test_unknown_format_version_disables_all_conversion_saves(tmp_path: Path) -> None:
    _app()
    source = tmp_path / "future.html"
    source.write_bytes(
        _named_sheet_bytes().replace(
            b'"formatVersion": "1.0.0"',
            b'"formatVersion": "9.0.0"',
            1,
        )
    )
    window = MainWindow()

    assert window.load_path(source)

    assert window.sheet is not None
    assert window.sheet.whole_sheet_read_only
    assert not window.save_button.isEnabled()


def test_warning_counts_python_code_points_and_does_not_block_output() -> None:
    _app()
    sheet = load_character_sheet(_named_sheet_bytes())
    draft = CharacterSheetDraft.from_sheet(sheet)
    draft.set_name("名" * 21)
    draft.set_profile("basicSettings", "e\u0301" * 501)
    rendered = load_character_sheet(render_character_sheet(sheet, draft))

    warnings = MainWindow._advisory_warnings(rendered)

    assert "キャラクター名が20文字を超えています（21文字）" in warnings
    assert "基本設定が1000文字を超えています（1002文字）" in warnings
