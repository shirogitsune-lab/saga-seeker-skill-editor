from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pytest

from saga_seeker_skill_editor.core.character_sheet import (
    CharacterSheet,
    CharacterSheetError,
    load_character_sheet,
)
from saga_seeker_skill_editor.core.file_writer import atomic_save_bytes
from saga_seeker_skill_editor.core.personality_catalog import load_personality_catalog
from saga_seeker_skill_editor.core.personality_editor import render_personality_selections
from saga_seeker_skill_editor.core.sheet_editor import (
    render_name_description_edit,
    render_skill_deletion,
    render_vacant_slot_creation,
)
from saga_seeker_skill_editor.core.skill_classifier import SkillKind


_PRIVATE_FIXTURE_SKIP_REASON = "private integration fixtures are not available"
_PRIVATE_SCENARIO_SKIP_REASON = "private integration scenario is not available"
pytestmark = pytest.mark.private_integration


@dataclass(frozen=True, repr=False)
class _AnonymousFixture:
    raw: bytes
    sheet: CharacterSheet


@dataclass(frozen=True, repr=False)
class _AnonymousSurvey:
    total_count: int
    rejected_count: int
    fixtures: tuple[_AnonymousFixture, ...]


def _private_input_dir() -> Path:
    configured = os.environ.get("SAGA_SEEKER_PRIVATE_FIXTURES")
    if configured:
        return Path(configured)
    return Path(__file__).parent / "private_fixtures"


@lru_cache(maxsize=None)
def _survey_private_fixtures(input_dir: Path) -> _AnonymousSurvey:
    paths = tuple(sorted(input_dir.glob("*.html")))
    fixtures: list[_AnonymousFixture] = []
    rejected_count = 0
    for path in paths:
        try:
            raw = path.read_bytes()
            sheet = load_character_sheet(raw)
        except (OSError, CharacterSheetError):
            rejected_count += 1
            continue
        fixtures.append(_AnonymousFixture(raw=raw, sheet=sheet))
    return _AnonymousSurvey(
        total_count=len(paths),
        rejected_count=rejected_count,
        fixtures=tuple(fixtures),
    )


def _anonymous_survey() -> _AnonymousSurvey:
    input_dir = _private_input_dir()
    if not input_dir.is_dir():
        pytest.skip(_PRIVATE_FIXTURE_SKIP_REASON)
    survey = _survey_private_fixtures(input_dir)
    if survey.total_count == 0:
        pytest.skip(_PRIVATE_FIXTURE_SKIP_REASON)
    return survey


def _anonymous_fixture(
    predicate: Callable[[CharacterSheet], bool],
) -> _AnonymousFixture:
    for fixture in _anonymous_survey().fixtures:
        if predicate(fixture.sheet):
            return fixture
    pytest.skip(_PRIVATE_SCENARIO_SKIP_REASON)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def test_anonymous_real_sheet_survey_is_parseable() -> None:
    survey = _anonymous_survey()

    assert survey.total_count >= 150
    assert len(survey.fixtures) >= 150
    assert len(survey.fixtures) + survey.rejected_count == survey.total_count


def test_anonymous_real_sheets_cover_supported_skill_structures() -> None:
    sheets = tuple(fixture.sheet for fixture in _anonymous_survey().fixtures)

    assert any(
        entry.classification.kind == SkillKind.ORIGINAL
        for sheet in sheets
        for entry in sheet.entries
    )
    assert any(
        entry.classification.kind == SkillKind.DEFAULT
        for sheet in sheets
        for entry in sheet.entries
    )
    assert any(not sheet.read_only and sheet.vacant_slot_count > 0 for sheet in sheets)
    assert any(
        entry.skill.get("id") == "sk1"
        for sheet in sheets
        for entry in sheet.entries
    )
    assert any(sheet.slot_count == 6 for sheet in sheets)


def test_anonymous_real_sheet_copy_can_be_edited_and_saved_atomically(
    tmp_path: Path,
) -> None:
    fixture = _anonymous_fixture(
        lambda sheet: not sheet.read_only
        and any(
            entry.classification.kind == SkillKind.ORIGINAL
            for entry in sheet.entries
        )
    )
    working = tmp_path / "working-copy"
    output = tmp_path / "edited-copy"
    working.write_bytes(fixture.raw)
    original_hash = _sha256(working.read_bytes())
    sheet = load_character_sheet(working.read_bytes())
    editable_index = next(
        entry.index
        for entry in sheet.entries
        if entry.classification.kind == SkillKind.ORIGINAL
    )
    replacement_name = 'Integration "quote" & <tag> 日本語 🦊'
    replacement_description = "Integration </script> & < >\nsecond line"

    edited = render_name_description_edit(
        sheet,
        index=editable_index,
        name=replacement_name,
        description=replacement_description,
    )

    def validate(path: Path) -> None:
        load_character_sheet(path.read_bytes())

    atomic_save_bytes(output, edited, validate_temp_path=validate)
    rendered = load_character_sheet(output.read_bytes())

    assert _sha256(working.read_bytes()) == original_hash
    assert rendered.entries[editable_index].skill["name"] == replacement_name
    assert (
        rendered.entries[editable_index].skill["description"]
        == replacement_description
    )
    assert (
        rendered.entries[editable_index].li.attrs["data-skill-name"]
        == replacement_name
    )


def test_anonymous_real_sheet_vacant_addition_and_deletion_are_safe() -> None:
    fixture = _anonymous_fixture(
        lambda sheet: not sheet.read_only
        and sheet.slot_count >= 3
        and sheet.vacant_slot_count > 0
        and any(
            entry.classification.kind != SkillKind.EMPTY_SLOT
            for entry in sheet.entries
        )
    )
    sheet = fixture.sheet
    deletion_index = next(
        entry.index
        for entry in sheet.entries
        if entry.classification.kind != SkillKind.EMPTY_SLOT
    )

    added = render_vacant_slot_creation(
        sheet,
        name="Integration Original",
        description="Added to an anonymous vacant slot",
    )
    added_sheet = load_character_sheet(added)
    created_index = next(
        entry.index
        for entry in added_sheet.entries
        if entry.skill["name"] == "Integration Original"
    )
    deleted = render_skill_deletion(added_sheet, index=deletion_index)
    deleted_sheet = load_character_sheet(deleted)

    assert added_sheet.entries[created_index].skill["name"] == "Integration Original"
    assert deleted_sheet.entries[deletion_index].classification.kind == SkillKind.EMPTY_SLOT
    assert deleted_sheet.entries[created_index].skill["name"] == "Integration Original"


def test_anonymous_real_sheet_personality_copy_can_be_saved(tmp_path: Path) -> None:
    catalog = load_personality_catalog()

    def supports_personality_edit(sheet: CharacterSheet) -> bool:
        original_ids = {entry.keyword["id"] for entry in sheet.personality_entries}
        return (
            not sheet.read_only
            and bool(original_ids)
            and any(keyword.id not in original_ids for keyword in catalog)
        )

    fixture = _anonymous_fixture(supports_personality_edit)
    working = tmp_path / "working-copy"
    output = tmp_path / "personality-edited-copy"
    working.write_bytes(fixture.raw)
    original_hash = _sha256(working.read_bytes())
    sheet = load_character_sheet(working.read_bytes())
    original_ids = [entry.keyword["id"] for entry in sheet.personality_entries]
    replacement_id = next(
        keyword.id for keyword in catalog if keyword.id not in original_ids
    )
    desired_ids = tuple(
        [replacement_id, *original_ids[1:]]
        + [None] * (sheet.personality_slot_count - len(original_ids))
    )

    updated = render_personality_selections(
        sheet,
        keyword_ids=desired_ids,
        catalog=catalog,
    )
    atomic_save_bytes(
        output,
        updated,
        validate_temp_path=lambda path: load_character_sheet(path.read_bytes()),
    )
    rendered = load_character_sheet(output.read_bytes())

    assert rendered.personality_entries[0].keyword["id"] == replacement_id
    assert [
        entry.keyword["id"] for entry in rendered.personality_entries[1:]
    ] == original_ids[1:]
    assert _sha256(working.read_bytes()) == original_hash
