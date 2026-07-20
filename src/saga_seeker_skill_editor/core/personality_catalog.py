"""Game-defined personality keyword catalog."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache

from saga_seeker_skill_editor.resources import package_resource_path


class PersonalityCatalogError(ValueError):
    """Raised when the bundled personality catalog is incomplete or invalid."""


@dataclass(frozen=True)
class PersonalityKeyword:
    id: int
    name: str
    type: str
    karma: str

    def as_dict(self) -> dict[str, object]:
        return {"id": self.id, "name": self.name, "type": self.type, "karma": self.karma}


@lru_cache(maxsize=1)
def load_personality_catalog() -> tuple[PersonalityKeyword, ...]:
    path = package_resource_path("data/personality_keywords.csv")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise PersonalityCatalogError(f"性格キーワード一覧を読み込めません: {exc}") from exc

    expected_fields = {"id", "name", "type", "karma"}
    keywords: list[PersonalityKeyword] = []
    for row_number, row in enumerate(rows, start=2):
        if set(row) != expected_fields:
            raise PersonalityCatalogError(f"性格キーワード一覧の列が不正です（{row_number}行目）")
        try:
            keyword = PersonalityKeyword(
                id=int(row["id"]),
                name=row["name"],
                type=row["type"],
                karma=row["karma"],
            )
        except (TypeError, ValueError) as exc:
            raise PersonalityCatalogError(f"性格キーワード一覧のIDが不正です（{row_number}行目）") from exc
        if keyword.id <= 0 or not keyword.name or not keyword.type or not keyword.karma:
            raise PersonalityCatalogError(f"性格キーワード一覧に空の必須項目があります（{row_number}行目）")
        keywords.append(keyword)

    ids = [keyword.id for keyword in keywords]
    names = [keyword.name for keyword in keywords]
    if len(ids) != len(set(ids)) or len(names) != len(set(names)):
        raise PersonalityCatalogError("性格キーワード一覧に重複があります")
    if len(keywords) != 150:
        raise PersonalityCatalogError(f"性格キーワード一覧は150件必要です（{len(keywords)}件）")
    return tuple(keywords)


def catalog_by_id(catalog: tuple[PersonalityKeyword, ...]) -> dict[int, PersonalityKeyword]:
    return {keyword.id: keyword for keyword in catalog}
