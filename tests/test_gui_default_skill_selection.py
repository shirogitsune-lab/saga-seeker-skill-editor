from __future__ import annotations

import json
import os
from dataclasses import replace
from html import escape
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from saga_seeker_skill_editor.core.character_sheet import load_character_sheet  # noqa: E402
from saga_seeker_skill_editor.core.default_skill_catalog import (  # noqa: E402
    DefaultSkill,
    load_default_skill_catalog,
)
from saga_seeker_skill_editor.core.skill_classifier import SkillKind  # noqa: E402
from saga_seeker_skill_editor.gui.skill_editor_widget import (  # noqa: E402
    DefaultSkillSelectionDialog,
    SkillEditorWidget,
)
from saga_seeker_skill_editor.gui.main_window import MainWindow  # noqa: E402
from saga_seeker_skill_editor.gui.vacant_slot_editor_widget import (  # noqa: E402
    VacantSlotEditorWidget,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _sheet_bytes(skill: dict[str, str] | None = None, *, vacant: bool = False) -> bytes:
    skill = skill or {
        "id": "sk1",
        "name": "Original",
        "description": "Keep",
        "type": "",
        "key": "",
    }
    data = {"data": {"name": "Default skill GUI", "skills": [skill]}}
    vacant_li = "<li>&nbsp;</li>" if vacant else ""
    raw = (
        f'<ul id="skills-value"><li data-skill-id="{escape(skill["id"], quote=True)}" '
        f'data-skill-name="{escape(skill["name"], quote=True)}" '
        f'data-skill-type="{escape(skill["type"], quote=True)}" '
        f'data-skill-description="{escape(skill["description"], quote=True)}">'
        f'{escape(skill["name"])}</li>{vacant_li}</ul>'
        '<script id="character-sheet-data" type="application/json">'
        f"{json.dumps(data, ensure_ascii=False)}</script>"
    ).encode("utf-8")
    return raw


def _original_entry():
    return load_character_sheet(_sheet_bytes()).entries[0]


def test_default_skill_dialog_searches_description_and_filters_type() -> None:
    _app()
    catalog = load_default_skill_catalog()
    dialog = DefaultSkillSelectionDialog(catalog)

    assert dialog.results.topLevelItemCount() == 96
    assert dialog.selected_skill() == catalog[0]

    dialog.type_filter.setCurrentText("肉体")
    assert dialog.results.topLevelItemCount() == 32
    assert all(
        dialog.results.topLevelItem(index).text(1) == "肉体"
        for index in range(dialog.results.topLevelItemCount())
    )

    dialog.type_filter.setCurrentIndex(0)
    target = catalog[16]
    dialog.search_edit.setText(target.description)
    visible_ids = {
        dialog.results.topLevelItem(index).data(0, Qt.ItemDataRole.UserRole)
        for index in range(dialog.results.topLevelItemCount())
    }
    assert target.id in visible_ids


def test_canceling_default_selection_does_not_mark_skill_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    catalog = load_default_skill_catalog()
    widget = SkillEditorWidget(_original_entry(), default_catalog=catalog)
    monkeypatch.setattr(DefaultSkillSelectionDialog, "ask", lambda *_args: None)

    widget._choose_default_skill()

    assert not widget.state().changed
    assert widget.state().default_skill is None
    assert widget.name_edit.text() == "Original"
    assert widget.description_edit.toPlainText() == "Keep"


def test_selecting_default_marks_changed_and_reset_restores_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    catalog = load_default_skill_catalog()
    selected = catalog[16]
    widget = SkillEditorWidget(_original_entry(), default_catalog=catalog)
    monkeypatch.setattr(DefaultSkillSelectionDialog, "ask", lambda *_args: selected)

    widget._choose_default_skill()

    assert widget.state().changed
    assert widget.state().default_skill == selected
    assert not widget.state().pending_default_original
    assert widget.name_edit.text() == selected.name
    assert widget.description_edit.toPlainText() == selected.description
    assert widget.name_edit.isEnabled()
    assert widget.description_edit.isEnabled()
    assert widget.kind_label.text() == "デフォルト候補（未確定）"
    assert widget.protection_label.text() == "未確定・保護なし"

    widget.reset()

    assert not widget.state().changed
    assert widget.state().default_skill is None
    assert widget.name_edit.text() == "Original"
    assert widget.description_edit.toPlainText() == "Keep"
    assert widget.name_edit.isEnabled()
    assert widget.description_edit.isEnabled()


def test_vacant_default_selection_and_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    catalog = load_default_skill_catalog()
    selected = catalog[-1]
    widget = VacantSlotEditorWidget(
        0,
        creation_enabled=True,
        default_catalog=catalog,
    )
    monkeypatch.setattr(DefaultSkillSelectionDialog, "ask", lambda *_args: selected)

    widget._choose_default_skill()

    assert widget.state().changed
    assert widget.state().default_skill == selected
    assert not widget.state().pending_default_original
    assert widget.name_edit.isEnabled()

    widget.reset()

    assert not widget.state().changed
    assert widget.state().default_skill is None
    assert widget.name_edit.text() == ""
    assert widget.description_edit.toPlainText() == ""
    assert widget.name_edit.isEnabled()
    assert widget.description_edit.isEnabled()


def test_main_window_renders_selected_default_as_one_catalog_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    path = tmp_path / "default-selection.html"
    path.write_bytes(_sheet_bytes())
    window = MainWindow()
    assert window.load_path(path)
    selected = load_default_skill_catalog()[16]
    monkeypatch.setattr(DefaultSkillSelectionDialog, "ask", lambda *_args: selected)

    window.skill_widgets[0]._choose_default_skill()
    rendered = load_character_sheet(window._render_current_edits())

    assert rendered.entries[0].skill == selected.as_dict()


def test_pending_default_compares_normalized_name_and_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    selected = DefaultSkill(
        id="pending",
        name="Line Name",
        description="A\r\nB\rC",
        type="精神",
        key="pending-key",
    )
    widget = SkillEditorWidget(_original_entry(), default_catalog=(selected,))
    monkeypatch.setattr(DefaultSkillSelectionDialog, "ask", lambda *_args: selected)

    widget._choose_default_skill()

    assert widget.name_edit.text() == selected.name
    assert widget.description_edit.toPlainText() == "A\nB\nC"
    assert widget.state().default_skill == selected
    assert not widget.state().pending_default_original

    widget.name_edit.setText("Changed name")
    assert widget.state().default_skill is None
    assert widget.state().pending_default_original

    widget.name_edit.setText(selected.name)
    assert widget.state().default_skill == selected
    assert not widget.state().pending_default_original


def test_loading_crlf_description_does_not_create_false_dirty_state() -> None:
    _app()
    entry = replace(
        _original_entry(),
        skill={**_original_entry().skill, "description": "A\r\nB\rC"},
    )

    widget = SkillEditorWidget(entry)

    assert widget.description_edit.toPlainText() == "A\nB\nC"
    assert not widget.state().changed


def test_edited_pending_default_saves_as_original_and_clears_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    source = tmp_path / "pending-original-source.html"
    destination = tmp_path / "pending-original-saved.html"
    source.write_bytes(_sheet_bytes())
    window = MainWindow()
    assert window.load_path(source)
    selected = load_default_skill_catalog()[16]
    monkeypatch.setattr(DefaultSkillSelectionDialog, "ask", lambda *_args: selected)
    monkeypatch.setattr(window, "_choose_save_path", lambda: destination)

    window.skill_widgets[0]._choose_default_skill()
    window.skill_widgets[0].description_edit.setPlainText("A\r\nB")
    assert window.skill_widgets[0].state().pending_default_original
    assert window.save_as()

    assert window.sheet is not None
    saved = window.sheet.entries[0]
    assert saved.classification.kind == SkillKind.ORIGINAL
    assert saved.skill == {
        "id": "sk1",
        "name": selected.name,
        "description": "A\nB",
        "type": "",
        "key": "",
    }
    assert window.skill_widgets[0].selected_default is None
    assert not window.skill_widgets[0].state().pending_default_original
    assert not window.skill_widgets[0].state().changed
    assert window.changed_indices == set()


def test_unchanged_pending_default_saves_as_default_and_clears_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    source = tmp_path / "pending-default-source.html"
    destination = tmp_path / "pending-default-saved.html"
    source.write_bytes(_sheet_bytes())
    window = MainWindow()
    assert window.load_path(source)
    selected = load_default_skill_catalog()[16]
    monkeypatch.setattr(DefaultSkillSelectionDialog, "ask", lambda *_args: selected)
    monkeypatch.setattr(window, "_choose_save_path", lambda: destination)

    window.skill_widgets[0]._choose_default_skill()
    assert window.save_as()

    assert window.sheet is not None
    assert window.sheet.entries[0].classification.kind == SkillKind.DEFAULT
    assert window.sheet.entries[0].skill == selected.as_dict()
    assert window.skill_widgets[0].selected_default is None
    assert not window.skill_widgets[0].state().changed
    assert window.changed_indices == set()


def test_saved_default_edited_via_pending_needs_no_replacement_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    existing = load_default_skill_catalog()[0]
    selected = load_default_skill_catalog()[16]
    source = tmp_path / "saved-default-source.html"
    destination = tmp_path / "saved-default-to-original.html"
    source.write_bytes(_sheet_bytes(existing.as_dict()))
    window = MainWindow()
    assert window.load_path(source)
    assert window.sheet is not None
    assert window.sheet.entries[0].classification.kind == SkillKind.DEFAULT
    monkeypatch.setattr(DefaultSkillSelectionDialog, "ask", lambda *_args: selected)
    monkeypatch.setattr(window, "_choose_save_path", lambda: destination)

    window.skill_widgets[0]._choose_default_skill()
    window.skill_widgets[0].name_edit.setText("Pending original")
    state = window.skill_widgets[0].state()
    assert state.pending_default_original
    assert not state.replacement_confirmed
    assert window.skill_widgets[0].prepare_for_save()
    assert window.save_as()

    assert window.sheet is not None
    saved = window.sheet.entries[0]
    assert saved.classification.kind == SkillKind.ORIGINAL
    assert saved.skill == {
        "id": "sk1",
        "name": "Pending original",
        "description": selected.description,
        "type": "",
        "key": "",
    }
    assert window.skill_widgets[0].selected_default is None
    assert not window.skill_widgets[0].state().changed


def test_vacant_pending_default_edit_saves_as_original(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    source = tmp_path / "vacant-pending-source.html"
    destination = tmp_path / "vacant-pending-saved.html"
    source.write_bytes(_sheet_bytes(vacant=True))
    window = MainWindow()
    assert window.load_path(source)
    selected = load_default_skill_catalog()[-1]
    monkeypatch.setattr(DefaultSkillSelectionDialog, "ask", lambda *_args: selected)
    monkeypatch.setattr(window, "_choose_save_path", lambda: destination)

    widget = window.skill_widgets[1]
    widget._choose_default_skill()
    widget.description_edit.setPlainText("Changed")
    assert widget.state().pending_default_original
    assert window.save_as()

    assert window.sheet is not None
    saved = window.sheet.entries[1]
    assert saved.classification.kind == SkillKind.ORIGINAL
    assert saved.skill["name"] == selected.name
    assert saved.skill["description"] == "Changed"
    assert saved.skill["type"] == ""
    assert saved.skill["key"] == ""
    assert window.skill_widgets[1].selected_default is None
    assert not window.skill_widgets[1].state().changed
