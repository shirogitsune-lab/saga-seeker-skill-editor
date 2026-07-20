from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from saga_seeker_skill_editor.core.character_sheet import CharacterSheetError, load_character_sheet
from saga_seeker_skill_editor.core.file_writer import atomic_save_bytes
from saga_seeker_skill_editor.core.sheet_editor import (
    render_name_description_edit,
    render_skill_deletion,
    render_vacant_slot_creation,
)
from saga_seeker_skill_editor.core.skill_classifier import SkillKind


def _real_input_dir() -> Path:
    configured = os.environ.get("SAGA_SEEKER_PRIVATE_FIXTURES")
    if configured:
        return Path(configured)
    return Path(__file__).parent / "private_fixtures"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_known_real_sheets_load_without_editing_original_files() -> None:
    input_dir = _real_input_dir()
    if not input_dir.exists():
        pytest.skip("local private real HTML input directory is not available")

    targets = [
        input_dir / "CFSU 戦術作戦センター.html",
        input_dir / "【謎のヒロインＫ】.html",
        input_dir / "ツキ.html",
        input_dir / "アステリオン.html",
        input_dir / "アーサー.html",
    ]
    missing = [path for path in targets if not path.exists()]
    if missing:
        pytest.skip(f"local private real HTML fixtures missing: {missing}")

    sheets = [load_character_sheet(path.read_bytes()) for path in targets]

    assert any(entry.classification.kind == SkillKind.ORIGINAL for entry in sheets[1].entries)
    assert any(entry.classification.kind == SkillKind.DEFAULT for entry in sheets[1].entries)
    assert sheets[2].read_only is False
    assert sheets[2].vacant_slot_count == 1
    assert any(entry.skill.get("id") == "sk1" for entry in sheets[3].entries)
    assert sheets[4].read_only is False
    assert sheets[4].slot_count == 6
    assert sheets[4].vacant_slot_count == 4
    assert all(entry.classification.kind == SkillKind.DEFAULT for entry in sheets[4].entries)


def test_real_input_directory_summary_is_parseable_for_supported_sheets() -> None:
    input_dir = _real_input_dir()
    if not input_dir.exists():
        pytest.skip("local private real HTML input directory is not available")

    html_files = sorted(input_dir.glob("*.html"))
    if not html_files:
        pytest.skip("local private real HTML fixtures are not available")

    loaded = 0
    rejected = 0
    for path in html_files:
        try:
            load_character_sheet(path.read_bytes())
        except CharacterSheetError:
            rejected += 1
        else:
            loaded += 1

    assert loaded >= 100
    assert rejected >= 1


def test_edit_copied_real_html_and_save_atomically_without_touching_original(tmp_path: Path) -> None:
    input_dir = _real_input_dir()
    source = input_dir / "【謎のヒロインＫ】.html"
    if not source.exists():
        pytest.skip("local private real HTML fixture is not available")

    original_hash = _sha256(source)
    working = tmp_path / "working.html"
    output = tmp_path / "edited.html"
    working.write_bytes(source.read_bytes())
    sheet = load_character_sheet(working.read_bytes())
    editable_index = next(
        entry.index for entry in sheet.entries if entry.classification.kind == SkillKind.ORIGINAL
    )

    edited = render_name_description_edit(
        sheet,
        index=editable_index,
        name='保存テスト "quote" & <tag> 日本語 😀',
        description="説明 </script> & < >\n次の行",
    )

    def validate(path: Path) -> None:
        load_character_sheet(path.read_bytes())

    atomic_save_bytes(output, edited, validate_temp_path=validate)
    rendered = load_character_sheet(output.read_bytes())

    assert _sha256(source) == original_hash
    assert rendered.entries[editable_index].skill["name"] == '保存テスト "quote" & <tag> 日本語 😀'
    assert rendered.entries[editable_index].skill["description"] == "説明 </script> & < >\n次の行"
    assert rendered.entries[editable_index].li.attrs["data-skill-name"] == '保存テスト "quote" & <tag> 日本語 😀'


def test_arthur_addition_and_middle_deletion_are_safe_in_memory() -> None:
    source = _real_input_dir() / "アーサー.html"
    if not source.exists():
        pytest.skip("local Arthur HTML fixture is not available")
    original_hash = _sha256(source)
    sheet = load_character_sheet(source.read_bytes())

    added = render_vacant_slot_creation(
        sheet,
        name="Integration Original",
        description="Added to slot three",
    )
    added_sheet = load_character_sheet(added)
    deleted = render_skill_deletion(added_sheet, index=0)
    deleted_sheet = load_character_sheet(deleted)

    assert added_sheet.entries[2].skill["name"] == "Integration Original"
    assert added_sheet.vacant_slot_count == 3
    assert deleted_sheet.entries[0].classification.kind == SkillKind.EMPTY_SLOT
    assert deleted_sheet.entries[2].skill["name"] == "Integration Original"
    assert _sha256(source) == original_hash
