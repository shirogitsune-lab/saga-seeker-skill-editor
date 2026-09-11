"""Game-defined default skill catalog."""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from saga_seeker_skill_editor.resources import package_resource_path


class DefaultSkillCatalogError(ValueError):
    """Raised when the bundled default skill catalog is incomplete or invalid."""


@dataclass(frozen=True)
class DefaultSkill:
    id: str
    name: str
    description: str
    type: str
    key: str

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "key": self.key,
        }


@lru_cache(maxsize=1)
def load_default_skill_catalog() -> tuple[DefaultSkill, ...]:
    path = package_resource_path("data/default_skills.csv")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise DefaultSkillCatalogError(f"デフォルトスキル一覧を読み込めません: {exc}") from exc

    expected_fields = {"id", "name", "description", "type", "key"}
    skills: list[DefaultSkill] = []
    for row_number, row in enumerate(rows, start=2):
        if set(row) != expected_fields:
            raise DefaultSkillCatalogError(f"デフォルトスキル一覧の列が不正です（{row_number}行目）")
        skill = DefaultSkill(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            type=row["type"],
            key=row["key"],
        )
        if not all(skill.as_dict().values()):
            raise DefaultSkillCatalogError(
                f"デフォルトスキル一覧に空の必須項目があります（{row_number}行目）"
            )
        if skill.type not in {"肉体", "精神", "社会"}:
            raise DefaultSkillCatalogError(
                f"デフォルトスキル一覧のtypeが不正です（{row_number}行目）"
            )
        skills.append(skill)

    ids = [skill.id for skill in skills]
    names = [skill.name for skill in skills]
    if len(skills) != 96:
        raise DefaultSkillCatalogError(f"デフォルトスキル一覧は96件必要です（{len(skills)}件）")
    if len(ids) != len(set(ids)):
        raise DefaultSkillCatalogError("デフォルトスキル一覧のIDが重複しています")
    if set(ids) != {str(number) for number in range(1, 97)}:
        raise DefaultSkillCatalogError('デフォルトスキル一覧のIDは文字列"1"～"96"が必要です')
    if len(names) != len(set(names)):
        raise DefaultSkillCatalogError("デフォルトスキル一覧の名前が重複しています")
    if Counter(skill.type for skill in skills) != {"肉体": 32, "精神": 32, "社会": 32}:
        raise DefaultSkillCatalogError("デフォルトスキル一覧は各typeが32件ずつ必要です")
    return tuple(skills)
