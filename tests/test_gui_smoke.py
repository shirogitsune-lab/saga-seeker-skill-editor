from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from saga_seeker_skill_editor.core.character_sheet import load_character_sheet  # noqa: E402
from saga_seeker_skill_editor.gui.main_window import MainState, MainWindow  # noqa: E402
from saga_seeker_skill_editor.gui.skill_editor_widget import (  # noqa: E402
    DeletionConfirmationDialog,
    ReplacementModeDialog,
    SkillActionDialog,
    deletion_effect_text,
)
from saga_seeker_skill_editor.gui.vacant_slot_editor_widget import VacantSlotEditorWidget  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _sheet_bytes() -> bytes:
    skill = {
        "id": "skill_no01_2025-12-30-05-02",
        "name": "GUI Smoke",
        "description": "Loaded by the GUI smoke test",
        "type": "",
        "key": "",
    }
    data = {
        "formatVersion": "1.0.0",
        "exportedAt": "2026-07-20T00:00:00Z",
        "data": {
            "name": "Synthetic GUI",
            "profile": {},
            "status": {},
            "skills": [skill],
            "personalities": [],
            "memories": [],
            "icon": {},
        },
    }
    li = (
        '<li data-skill-id="skill_no01_2025-12-30-05-02" '
        'data-skill-name="GUI Smoke" data-skill-type="" '
        'data-skill-description="Loaded by the GUI smoke test">GUI Smoke</li>'
    )
    return (
        "<html><body>"
        f'<ul id="skills-value">{li}</ul>'
        f'<script id="character-sheet-data" type="application/json">{json.dumps(data, ensure_ascii=False)}</script>'
        "</body></html>"
    ).encode("utf-8")


def test_main_window_loads_synthetic_sheet_offscreen(tmp_path: Path) -> None:
    _app()
    path = tmp_path / "synthetic.html"
    path.write_bytes(_sheet_bytes())

    window = MainWindow()
    window.load_path(path)

    assert window.sheet is not None
    assert window.sheet.character_name == "Synthetic GUI"
    assert len(window.skill_widgets) == 1
    assert window.skill_widgets[0].name_edit.text() == "GUI Smoke"
    assert window.main_state == MainState.NORMAL
    assert not window.save_button.isEnabled()
    assert window.save_button.toolTip() == "変更がないため保存できません"
    assert window.skill_list.topLevelItemCount() == 1


def test_main_window_places_default_replacement_in_advanced_section(tmp_path: Path) -> None:
    _app()
    default = {
        "id": "42",
        "name": "Default",
        "description": "Protected",
        "type": "精神",
        "key": "Default_Key",
    }
    data = {
        "formatVersion": "1.0.0",
        "exportedAt": "2026-07-20T00:00:00Z",
        "data": {
            "name": "Synthetic Default",
            "profile": {},
            "status": {},
            "skills": [default],
            "personalities": [],
            "memories": [],
            "icon": {},
        },
    }
    li = (
        '<li data-skill-id="42" data-skill-name="Default" data-skill-type="精神" '
        'data-skill-description="Protected">Default</li>'
    )
    path = tmp_path / "default.html"
    path.write_bytes(
        (
            f'<ul id="skills-value">{li}</ul>'
            f'<script id="character-sheet-data" type="application/json">{json.dumps(data, ensure_ascii=False)}</script>'
        ).encode("utf-8")
    )

    window = MainWindow()
    window.load_path(path)

    editor = window.skill_widgets[0]
    assert not editor.advanced_section.isHidden()
    assert editor.action_button.text() == "このスキルの操作を選ぶ..."
    assert not editor.name_edit.isEnabled()
    assert not editor.description_edit.isEnabled()


def test_main_window_reports_registered_and_vacant_slots(tmp_path: Path) -> None:
    _app()
    default = {
        "id": "21",
        "name": "Default",
        "description": "Protected",
        "type": "physical",
        "key": "Default_Key",
    }
    data = {
        "formatVersion": "1.0.0",
        "exportedAt": "2026-07-20T00:00:00Z",
        "data": {
            "name": "Six Slot Test",
            "profile": {},
            "status": {},
            "skills": [default],
            "personalities": [],
            "memories": [],
            "icon": {},
        },
    }
    path = tmp_path / "six-slots.html"
    path.write_bytes(
        (
            '<ul id="skills-value">'
            '<li data-skill-id="21" data-skill-name="Default" data-skill-type="physical" '
            'data-skill-description="Protected">Default</li>'
            + "<li>&nbsp;</li>" * 5
            + "</ul>"
            + f'<script id="character-sheet-data" type="application/json">{json.dumps(data)}</script>'
        ).encode("utf-8")
    )

    window = MainWindow()
    assert window.load_path(path)

    assert window.sheet is not None
    assert window.sheet.read_only is False
    assert window.slot_summary_label.text() == "スキル欄: 登録済み 1 / 全6枠 | 未使用枠 5"
    assert window.skill_widgets[0].action_button.isEnabled()
    assert window.skill_list.topLevelItemCount() == 6
    assert len(window.skill_widgets) == 6
    assert isinstance(window.skill_widgets[1], VacantSlotEditorWidget)
    assert window.skill_widgets[1].name_edit.isEnabled()
    assert window.skill_widgets[2].name_edit.isEnabled()
    assert window.skill_widgets[5].name_edit.isEnabled()


def test_vacant_slot_input_marks_dirty_and_appends_to_first_slot(tmp_path: Path) -> None:
    _app()
    path = tmp_path / "vacant-add.html"
    raw = _sheet_bytes().replace(b"</ul>", b"<li>&nbsp;</li><li>&nbsp;</li></ul>")
    path.write_bytes(raw)
    window = MainWindow()
    assert window.load_path(path)

    vacant = window.skill_widgets[1]
    vacant.name_edit.setText("Added Original")
    vacant.description_edit.setPlainText("Added to the first vacant slot")

    assert window.changed_indices == {1}
    assert window.save_button.isEnabled()
    assert window.skill_list.topLevelItem(1).text(window.skill_list.NAME_COLUMN) == "Added Original"
    assert window.skill_widgets[0].action_button.isHidden()
    assert "追加を編集中" in window.skill_widgets[0].advanced_explanation.text()

    rendered = load_character_sheet(window._render_current_edits())
    assert len(rendered.entries) == 2
    assert rendered.entries[1].skill["id"] == "sk1"
    assert rendered.entries[1].skill["name"] == "Added Original"
    assert rendered.vacant_slot_count == 1


def test_deletion_confirmation_explains_middle_and_tail_results() -> None:
    middle = deletion_effect_text(becomes_vacant=False)
    tail = deletion_effect_text(becomes_vacant=True)

    assert "データの位置対応" in middle
    assert "空スキルへ置き換え" in middle
    assert "自動追加を防ぎます" in middle
    assert "未使用枠へ戻ります" in tail
    assert "自動追加される可能性" in tail


def test_default_action_dialog_offers_position_specific_choices() -> None:
    _app()
    middle = SkillActionDialog(None, is_last_entry=False)
    tail = SkillActionDialog(None, is_last_entry=True)

    assert middle.replace_radio.text() == "オリジナルスキルへ置き換える"
    assert middle.delete_radio.text() == "空スキルへ置き換える"
    assert tail.delete_radio.text() == "削除して未使用枠へ戻す"
    assert middle.action_group.exclusive()


def test_default_uses_one_contextual_action_button(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    default = {
        "id": "default-id",
        "name": "Protected",
        "description": "Keep this text",
        "type": "physical",
        "key": "Default_Key",
    }
    data = {"data": {"name": "Action Test", "skills": [default]}}
    li = (
        '<li data-skill-id="default-id" data-skill-name="Protected" '
        'data-skill-type="physical" data-skill-description="Keep this text">Protected</li>'
    )
    path = tmp_path / "default-action.html"
    path.write_bytes(
        (
            f'<ul id="skills-value">{li}<li>&nbsp;</li></ul>'
            f'<script id="character-sheet-data" type="application/json">{json.dumps(data)}</script>'
        ).encode("utf-8")
    )
    window = MainWindow()
    assert window.load_path(path)
    editor = window.skill_widgets[0]
    monkeypatch.setattr(SkillActionDialog, "ask", lambda *_args, **_kwargs: "replace")
    monkeypatch.setattr(ReplacementModeDialog, "ask", lambda *_args, **_kwargs: "keep")

    editor.action_button.click()

    assert editor.replacement_confirmed
    assert editor.action_button.text() == "置き換え予定を取り消す"
    assert editor.name_edit.text() == "Protected"
    assert editor.description_edit.toPlainText() == "Keep this text"
    assert not hasattr(editor, "replace_button")
    assert not hasattr(editor, "delete_button")


def test_gui_deletes_middle_to_empty_and_tail_to_vacant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    skills = [
        {"id": "sk1", "name": "First", "description": "One", "type": "", "key": ""},
        {"id": "sk2", "name": "Last", "description": "Two", "type": "", "key": ""},
    ]
    data = {
        "data": {
            "name": "Deletion Test",
            "skills": skills,
        }
    }
    lis = "".join(
        f'<li data-skill-id="{skill["id"]}" data-skill-name="{skill["name"]}" '
        f'data-skill-type="" data-skill-description="{skill["description"]}">{skill["name"]}</li>'
        for skill in skills
    )
    path = tmp_path / "delete.html"
    path.write_bytes(
        (
            f'<ul id="skills-value">{lis}<li>&nbsp;</li></ul>'
            f'<script id="character-sheet-data" type="application/json">{json.dumps(data)}</script>'
        ).encode("utf-8")
    )

    confirmations: list[bool] = []

    def confirm(_parent, *, skill_name: str, becomes_vacant: bool) -> bool:
        assert skill_name
        confirmations.append(becomes_vacant)
        return True

    monkeypatch.setattr(DeletionConfirmationDialog, "ask", confirm)

    middle_window = MainWindow()
    assert middle_window.load_path(path)
    assert middle_window.skill_widgets[0].action_button.text() == "空スキルへ置き換える..."
    middle_window.skill_widgets[0].action_button.click()
    assert middle_window.skill_widgets[0].action_button.text() == "削除予定を取り消す"
    middle_rendered = load_character_sheet(middle_window._render_current_edits())
    assert middle_rendered.entries[0].classification.kind.value == "empty_slot"
    assert middle_rendered.entries[1].skill == skills[1]

    tail_window = MainWindow()
    assert tail_window.load_path(path)
    assert tail_window.skill_widgets[1].action_button.text() == "削除して未使用枠へ戻す..."
    tail_window.skill_widgets[1].action_button.click()
    assert tail_window.skill_widgets[1].action_button.text() == "削除予定を取り消す"
    tail_rendered = load_character_sheet(tail_window._render_current_edits())
    assert [entry.skill for entry in tail_rendered.entries] == [skills[0]]
    assert tail_rendered.vacant_slot_count == 2
    assert confirmations == [False, True]


def test_vacant_slots_allow_drafting_but_block_gaps_until_fixed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    path = tmp_path / "vacant-gap.html"
    path.write_bytes(
        _sheet_bytes().replace(
            b"</ul>",
            b"<li>&nbsp;</li><li>&nbsp;</li><li>&nbsp;</li></ul>",
        )
    )
    window = MainWindow()
    assert window.load_path(path)

    second_vacant = window.skill_widgets[2]
    second_vacant.name_edit.setText("Later Skill")
    second_vacant.description_edit.setPlainText("Drafted before the earlier slot")

    assert window.main_state == MainState.ERROR
    assert window.validation_error is not None
    assert "スロット 2 が空欄" in window.validation_error
    assert window.skill_widgets[1].reason_label.property("state") == "error"
    assert window.save_button.isEnabled()
    assert window.save_button.toolTip() == "保存前に、途中の空欄を修正してください"

    messages: list[str] = []
    monkeypatch.setattr(window, "_present_validation_error", messages.append)
    monkeypatch.setattr(
        window,
        "_choose_save_path",
        lambda: pytest.fail("file picker must not open while a gap remains"),
    )
    assert not window.save_as()
    assert messages and "スロット 2 が空欄" in messages[0]

    first_vacant = window.skill_widgets[1]
    first_vacant.name_edit.setText("Earlier Skill")
    first_vacant.description_edit.setPlainText("Fills the gap")

    assert window.validation_error is None
    assert window.main_state == MainState.DIRTY
    assert first_vacant.reason_label.property("state") is None
    rendered = load_character_sheet(window._render_current_edits())
    assert [entry.skill["name"] for entry in rendered.entries] == [
        "GUI Smoke",
        "Earlier Skill",
        "Later Skill",
    ]

    first_vacant.name_edit.clear()
    assert window.validation_error is not None
    assert window.main_state == MainState.ERROR


def test_multiple_consecutive_vacant_skills_save_together(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _app()
    source = tmp_path / "multi-add.html"
    source.write_bytes(
        _sheet_bytes().replace(
            b"</ul>",
            b"<li>&nbsp;</li><li>&nbsp;</li><li>&nbsp;</li></ul>",
        )
    )
    destination = tmp_path / "multi-added.html"
    window = MainWindow()
    assert window.load_path(source)
    window.skill_widgets[1].name_edit.setText("Second")
    window.skill_widgets[2].name_edit.setText("Third")
    monkeypatch.setattr(window, "_choose_save_path", lambda: destination)

    assert window.save_as()
    assert window.current_path == destination
    assert window.changed_indices == set()
    saved = load_character_sheet(destination.read_bytes())
    assert [entry.skill["name"] for entry in saved.entries] == ["GUI Smoke", "Second", "Third"]
    assert saved.vacant_slot_count == 1


def test_main_window_empty_slot_is_editable(tmp_path: Path) -> None:
    _app()
    empty = {"id": "", "name": "", "description": "", "type": "", "key": ""}
    data = {
        "formatVersion": "1.0.0",
        "exportedAt": "2026-07-20T00:00:00Z",
        "data": {
            "name": "Synthetic Empty",
            "profile": {},
            "status": {},
            "skills": [empty],
            "personalities": [],
            "memories": [],
            "icon": {},
        },
    }
    path = tmp_path / "empty.html"
    path.write_bytes(
        (
            '<ul id="skills-value"><li>&nbsp;</li></ul>'
            f'<script id="character-sheet-data" type="application/json">{json.dumps(data, ensure_ascii=False)}</script>'
        ).encode("utf-8")
    )

    window = MainWindow()
    window.load_path(path)

    assert window.skill_widgets[0].name_edit.isEnabled()
    assert window.skill_widgets[0].description_edit.isEnabled()
