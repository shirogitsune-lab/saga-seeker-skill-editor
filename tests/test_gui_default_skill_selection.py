from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from saga_seeker_skill_editor.core.character_sheet import load_character_sheet  # noqa: E402
from saga_seeker_skill_editor.core.default_skill_catalog import (  # noqa: E402
    load_default_skill_catalog,
)
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


def _sheet_bytes() -> bytes:
    skill = {
        "id": "sk1",
        "name": "Original",
        "description": "Keep",
        "type": "",
        "key": "",
    }
    data = {"data": {"name": "Default skill GUI", "skills": [skill]}}
    raw = (
        '<ul id="skills-value"><li data-skill-id="sk1" '
        'data-skill-name="Original" data-skill-type="" '
        'data-skill-description="Keep">Original</li></ul>'
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
    assert widget.name_edit.text() == selected.name
    assert widget.description_edit.toPlainText() == selected.description
    assert not widget.name_edit.isEnabled()
    assert not widget.description_edit.isEnabled()

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
    assert not widget.name_edit.isEnabled()

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
