from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

import pytest

from saga_seeker_skill_editor.core import default_skill_catalog as catalog_module
from saga_seeker_skill_editor.core.default_skill_catalog import (
    DefaultSkillCatalogError,
    load_default_skill_catalog,
)
from saga_seeker_skill_editor.resources import package_resource_path


@pytest.fixture(autouse=True)
def clear_catalog_cache() -> None:
    load_default_skill_catalog.cache_clear()
    yield
    load_default_skill_catalog.cache_clear()


def test_default_skill_catalog_loads_all_exact_game_records() -> None:
    catalog = load_default_skill_catalog()

    assert len(catalog) == 96
    assert {skill.id for skill in catalog} == {str(number) for number in range(1, 97)}
    assert Counter(skill.type for skill in catalog) == {
        "肉体": 32,
        "精神": 32,
        "社会": 32,
    }
    assert catalog[16].as_dict() == {
        "id": "17",
        "name": "不死者の肉体",
        "description": "あなたは死ぬことがない。致命傷を負っても、時間が経てば復活する。",
        "type": "肉体",
        "key": "Shapeshifting",
    }


@pytest.mark.parametrize(
    "case",
    ["missing_column", "wrong_count", "duplicate_id", "bad_id", "empty_value", "bad_type", "duplicate_name"],
)
def test_default_skill_catalog_rejects_invalid_data(
    case: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    rows = [skill.as_dict() for skill in load_default_skill_catalog()]
    fields = ["id", "name", "description", "type", "key"]
    if case == "missing_column":
        fields.remove("key")
        rows = [{field: row[field] for field in fields} for row in rows]
    elif case == "wrong_count":
        rows.pop()
    elif case == "duplicate_id":
        rows[-1]["id"] = "1"
    elif case == "bad_id":
        rows[-1]["id"] = "97"
    elif case == "empty_value":
        rows[0]["key"] = ""
    elif case == "bad_type":
        rows[0]["type"] = "不明"
    elif case == "duplicate_name":
        rows[-1]["name"] = rows[0]["name"]

    path = tmp_path / "default_skills.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    monkeypatch.setattr(catalog_module, "package_resource_path", lambda _relative: path)
    load_default_skill_catalog.cache_clear()

    with pytest.raises(DefaultSkillCatalogError):
        load_default_skill_catalog()


def test_default_skill_catalog_uses_package_resource_path_in_source() -> None:
    path = package_resource_path("data/default_skills.csv")

    assert path.is_file()
    assert load_default_skill_catalog()[0].id == "1"


def test_default_skill_catalog_resolves_from_pyinstaller_meipass(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = package_resource_path("data/default_skills.csv")
    packaged = tmp_path / "saga_seeker_skill_editor" / "data" / "default_skills.csv"
    packaged.parent.mkdir(parents=True)
    packaged.write_bytes(source.read_bytes())
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    load_default_skill_catalog.cache_clear()

    assert load_default_skill_catalog()[16].key == "Shapeshifting"
