from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from saga_seeker_skill_editor.core.character_sheet import load_character_sheet  # noqa: E402
from saga_seeker_skill_editor.core.personality_catalog import load_personality_catalog  # noqa: E402
from saga_seeker_skill_editor.gui.main_window import MainState, MainWindow  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _sheet_bytes(personality_ids: list[int]) -> bytes:
    catalog = {keyword.id: keyword for keyword in load_personality_catalog()}
    personalities = [catalog[keyword_id].as_dict() for keyword_id in personality_ids]
    names = [item["name"] for item in personalities] + [""] * (6 - len(personalities))
    personality_lis = "".join(f"<li>{name if name else '&nbsp;'}</li>" for name in names)
    skill = {"id": "sk1", "name": "Original", "description": "Keep", "type": "", "key": ""}
    data = {"data": {"name": "Personality GUI", "skills": [skill], "personalities": personalities}}
    return (
        '<ul id="skills-value"><li data-skill-id="sk1" data-skill-name="Original" '
        'data-skill-type="" data-skill-description="Keep">Original</li></ul>'
        f'<ul id="personality-value">{personality_lis}</ul>'
        f'<script id="character-sheet-data" type="application/json">'
        f'{json.dumps(data, ensure_ascii=False, indent=2)}</script>'
    ).encode("utf-8")


def _window(tmp_path: Path, personality_ids: list[int]) -> MainWindow:
    _app()
    path = tmp_path / "personality.html"
    path.write_bytes(_sheet_bytes(personality_ids))
    window = MainWindow()
    assert window.load_path(path)
    return window


def test_personality_tab_has_six_fixed_catalog_selectors_with_all_fields(tmp_path: Path) -> None:
    window = _window(tmp_path, [1])

    assert window.edit_tabs.tabText(1) == "性格キーワード"
    assert len(window.personality_editor.combos) == 6
    assert window.personality_editor.combos[0].count() == 151
    assert window.personality_editor.combos[0].currentData() == 1
    assert window.personality_editor.type_labels[0].text() == "力"
    assert window.personality_editor.karma_labels[0].text() == "美徳"
    assert window.personality_editor.id_labels[0].text() == "1"


def test_personality_change_and_revert_are_comparison_based(tmp_path: Path) -> None:
    window = _window(tmp_path, [1])
    combo = window.personality_editor.combos[0]

    combo.setCurrentIndex(combo.findData(31))
    assert window.personality_changed_indices == {0}
    assert window.main_state == MainState.DIRTY
    assert window.save_button.isEnabled()

    combo.setCurrentIndex(combo.findData(1))
    assert window.personality_changed_indices == set()
    assert window.main_state == MainState.NORMAL
    assert not window.save_button.isEnabled()


def test_personality_gap_and_duplicate_errors_clear_after_correction(tmp_path: Path) -> None:
    window = _window(tmp_path, [1])
    second = window.personality_editor.combos[1]
    third = window.personality_editor.combos[2]

    third.setCurrentIndex(third.findData(32))
    assert window.main_state == MainState.ERROR
    assert window.validation_error is not None and "2枠目が未設定" in window.validation_error

    second.setCurrentIndex(second.findData(2))
    assert window.validation_error is None
    assert window.main_state == MainState.DIRTY

    third.setCurrentIndex(third.findData(2))
    assert window.validation_error is not None and "同じ性格キーワード" in window.validation_error

    third.setCurrentIndex(third.findData(32))
    assert window.validation_error is None


def test_personality_only_save_roundtrips_all_catalog_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    window = _window(tmp_path, [1, 2])
    first = window.personality_editor.combos[0]
    second = window.personality_editor.combos[1]
    first.setCurrentIndex(first.findData(2))
    second.setCurrentIndex(second.findData(31))
    destination = tmp_path / "saved.html"
    monkeypatch.setattr(window, "_choose_save_path", lambda: destination)

    assert window.save_as()
    saved = load_character_sheet(destination.read_bytes())

    assert [entry.keyword for entry in saved.personality_entries] == [
        {"id": 2, "name": "大胆", "type": "力", "karma": "美徳"},
        {"id": 31, "name": "論理的", "type": "知恵", "karma": "美徳"},
    ]
    assert saved.entries[0].skill["name"] == "Original"
    assert window.personality_changed_indices == set()
    assert window.main_state == MainState.NORMAL


def test_personality_change_participates_in_unsaved_state(tmp_path: Path) -> None:
    window = _window(tmp_path, [])
    combo = window.personality_editor.combos[0]
    combo.setCurrentIndex(combo.findData(1))

    assert window.unsaved_changes
    assert window._change_count() == 1
    window.reset_edits()
    assert not window.unsaved_changes
