"""Print privacy-safe aggregate schema counts for private character sheets."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re


SCRIPT_PATTERN = re.compile(
    rb"<script\b(?=[^>]*\bid=[\"']character-sheet-data[\"'])[^>]*>(.*?)</script\s*>",
    re.I | re.S,
)

ROOT_KEYS = ("formatVersion", "exportedAt", "data")
DATA_KEYS = (
    "characterId",
    "name",
    "profile",
    "status",
    "skills",
    "personalities",
    "memories",
    "icon",
)
PROFILE_KEYS = (
    "basicSettings",
    "appearance",
    "personality",
    "speechStyle",
    "background",
    "talentsAndRole",
    "otherFeatures",
)
STATUS_KEYS = (
    "strength",
    "endurance",
    "intelligence",
    "mentalStrength",
    "agility",
    "charm",
    "luck",
)
ICON_KEYS = ("mime", "dataUri")


def aggregate(input_dir: Path) -> dict[str, object]:
    files = sorted(input_dir.glob("*.html"))
    versions: Counter[str] = Counter()
    version_types: Counter[str] = Counter()
    presence = {
        **{f"root.{key}": 0 for key in ROOT_KEYS},
        **{f"data.{key}": 0 for key in DATA_KEYS},
        **{f"profile.{key}": 0 for key in PROFILE_KEYS},
        **{f"status.{key}": 0 for key in STATUS_KEYS},
        **{f"icon.{key}": 0 for key in ICON_KEYS},
    }
    script_missing = 0
    json_parse_failed = 0
    format_version_missing = 0
    parsed = 0

    for path in files:
        match = SCRIPT_PATTERN.search(path.read_bytes())
        if match is None:
            script_missing += 1
            continue
        try:
            document = json.loads(match.group(1).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            json_parse_failed += 1
            continue
        if not isinstance(document, dict):
            json_parse_failed += 1
            continue

        parsed += 1
        if "formatVersion" not in document:
            format_version_missing += 1
        else:
            version = document["formatVersion"]
            versions[json.dumps(version, ensure_ascii=False, sort_keys=True)] += 1
            version_types[type(version).__name__] += 1

        for key in ROOT_KEYS:
            presence[f"root.{key}"] += int(key in document)
        data = document.get("data")
        data = data if isinstance(data, dict) else {}
        for key in DATA_KEYS:
            presence[f"data.{key}"] += int(key in data)
        for value, keys, prefix in (
            (data.get("profile"), PROFILE_KEYS, "profile"),
            (data.get("status"), STATUS_KEYS, "status"),
            (data.get("icon"), ICON_KEYS, "icon"),
        ):
            group = value if isinstance(value, dict) else {}
            for key in keys:
                presence[f"{prefix}.{key}"] += int(key in group)

    return {
        "htmlTotal": len(files),
        "scriptMissing": script_missing,
        "jsonParseFailed": json_parse_failed,
        "jsonParsed": parsed,
        "formatVersionMissing": format_version_missing,
        "formatVersionValues": dict(sorted(versions.items())),
        "formatVersionTypes": dict(sorted(version_types.items())),
        "presenceDenominator": parsed,
        "presenceCounts": presence,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    args = parser.parse_args()
    if not args.input_dir.is_dir():
        parser.error(f"input directory does not exist: {args.input_dir}")
    print(json.dumps(aggregate(args.input_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
