from __future__ import annotations

import json
import os
from html import escape
from pathlib import Path

import pytest

from saga_seeker_skill_editor.core.character_sheet import load_character_sheet
from saga_seeker_skill_editor.core.default_skill_catalog import DefaultSkill
from saga_seeker_skill_editor.core.sheet_editor import render_default_skill_selection
from saga_seeker_skill_editor.core.skill_classifier import SkillKind


def _skill_li(skill: dict[str, str], *, extra_attr: str = "") -> str:
    extra = f' {extra_attr}' if extra_attr else ""
    return (
        f'<li{extra} data-skill-id="{escape(skill["id"], quote=True)}" '
        f'data-skill-name="{escape(skill["name"], quote=True)}" '
        f'data-skill-type="{escape(skill["type"], quote=True)}" '
        f'data-skill-description="{escape(skill["description"], quote=True)}">'
        f'{escape(skill["name"])}</li>'
    )


def _sheet_bytes(skills: list[dict[str, str]], skill_html: str) -> bytes:
    data = {"data": {"name": "Default skill review regression", "skills": skills}}
    return (
        f'<ul id="skills-value">{skill_html}</ul>'
        '<script id="character-sheet-data" type="application/json">'
        f"{json.dumps(data, ensure_ascii=False)}</script>"
    ).encode("utf-8")


def test_default_selection_preserves_unknown_attrs_on_attributed_empty_slot() -> None:
    empty = {
        "id": "existing-empty-id",
        "name": "",
        "description": "",
        "type": "",
        "key": "",
    }
    selected = DefaultSkill(
        id="8",
        name="Catalog Default",
        description="Five exact fields",
        type="精神",
        key="ExactKey",
    )
    raw = _sheet_bytes(
        [empty],
        _skill_li(empty, extra_attr='data-extra="must-stay"'),
    )
    sheet = load_character_sheet(raw)
    assert sheet.entries[0].classification.kind == SkillKind.EMPTY_SLOT

    updated = render_default_skill_selection(sheet, index=0, skill=selected)
    rendered = load_character_sheet(updated)

    assert rendered.entries[0].skill == selected.as_dict()
    assert rendered.entries[0].li.attrs["data-extra"] == "must-stay"
    assert rendered.entries[0].li.attrs["data-skill-id"] == selected.id
    assert rendered.entries[0].li.attrs["data-skill-name"] == selected.name
    assert rendered.entries[0].li.attrs["data-skill-type"] == selected.type
    assert (
        rendered.entries[0].li.attrs["data-skill-description"]
        == selected.description
    )


def test_existing_original_edit_is_rendered_before_new_default_id_collision(
    tmp_path: Path,
) -> None:
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    from saga_seeker_skill_editor.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    assert app is not None

    first = {
        "id": "first-original",
        "name": "First original",
        "description": "First description",
        "type": "",
        "key": "",
    }
    later = {
        "id": "17",
        "name": "Later original",
        "description": "Later description",
        "type": "",
        "key": "",
    }
    selected = DefaultSkill(
        id="17",
        name="不死者の肉体",
        description="Catalog description",
        type="肉体",
        key="Shapeshifting",
    )
    path = tmp_path / "same-save-id-collision.html"
    path.write_bytes(
        _sheet_bytes(
            [first, later],
            _skill_li(first) + _skill_li(later),
        )
    )
    window = MainWindow()
    assert window.load_path(path)

    first_widget = window.skill_widgets[0]
    first_widget.selected_default = selected
    first_widget.name_edit.setText(selected.name)
    first_widget.description_edit.setPlainText(selected.description)
    first_widget._on_value_changed()

    later_widget = window.skill_widgets[1]
    later_widget.name_edit.setText("Later edited")
    later_widget.description_edit.setPlainText("Later description edited")

    rendered = load_character_sheet(window._render_current_edits())

    assert rendered.entries[0].skill == selected.as_dict()
    assert rendered.entries[1].skill["id"] == "17"
    assert rendered.entries[1].skill["name"] == "Later edited"
    assert rendered.entries[1].skill["description"] == "Later description edited"
    assert (
        rendered.entries[1].classification.kind
        == SkillKind.ORIGINAL_NEEDS_ID_REPAIR
    )
    window.deleteLater()
