"""Privacy-safe comparison for Phase 0 game round-trip outputs."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import struct
from typing import Any

from saga_seeker_skill_editor.core.html_locator import (
    HtmlStructureError,
    find_unique_script_json,
)


CANDIDATE_REQUIRED_HTML_IDS = (
    "character-sheet-data",
    "name-value",
    "profile-value",
    "abilities-value",
    "skills-value",
    "personality-value",
    "memories-value",
    "icon-value",
)

GAME_EXPORT_REQUIRED_HTML_IDS = (
    "container",
    "name",
    "name-value",
    "detail",
    "icon",
    "icon-value",
    "personality",
    "personality-value",
    "abilities",
    "abilities-value",
    "skills",
    "skills-value",
    "memories",
    "memories-value",
    "character-sheet-data",
)

ALL_HTML_IDS = tuple(
    dict.fromkeys((*CANDIDATE_REQUIRED_HTML_IDS, *GAME_EXPORT_REQUIRED_HTML_IDS))
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
EXPORTED_AT_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{7}Z$")
CHARACTER_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}_\d{4}-\d{2}-\d{2}$"
)
MEMORY_ID_PATTERN = re.compile(
    r"^memory_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}_"
    r"\d{4}-\d{2}-\d{2}-\d{2}-\d{2}$"
)


class RoundTripComparisonError(ValueError):
    """Raised when either input is not a comparable character sheet."""


def compare_roundtrip(candidate_raw: bytes, roundtrip_raw: bytes) -> dict[str, object]:
    """Compare without exposing character content in the returned report."""

    candidate = _load_document(candidate_raw, "candidate")
    roundtrip = _load_document(roundtrip_raw, "roundtrip")
    candidate_data = _dict_at(candidate, "data", "candidate.data")
    roundtrip_data = _dict_at(roundtrip, "data", "roundtrip.data")

    schema_candidate = _schema_signature(candidate)
    schema_roundtrip = _schema_signature(roundtrip)
    metadata = {
        "formatVersion": _safe_scalar_comparison(
            candidate.get("formatVersion"),
            roundtrip.get("formatVersion"),
            expose_value=True,
        ),
        "exportedAt": {
            "candidateType": _type_name(candidate.get("exportedAt")),
            "roundtripType": _type_name(roundtrip.get("exportedAt")),
            "candidateFormatValid": _matches_string(candidate.get("exportedAt"), EXPORTED_AT_PATTERN),
            "roundtripFormatValid": _matches_string(roundtrip.get("exportedAt"), EXPORTED_AT_PATTERN),
            "same": candidate.get("exportedAt") == roundtrip.get("exportedAt"),
        },
        "characterId": {
            "candidatePresent": "characterId" in candidate_data,
            "roundtripPresent": "characterId" in roundtrip_data,
            "candidateType": _type_name(candidate_data.get("characterId")),
            "roundtripType": _type_name(roundtrip_data.get("characterId")),
            "candidateFormatValid": _matches_string(
                candidate_data.get("characterId"),
                CHARACTER_ID_PATTERN,
            ),
            "roundtripFormatValid": _matches_string(
                roundtrip_data.get("characterId"),
                CHARACTER_ID_PATTERN,
            ),
            "same": candidate_data.get("characterId") == roundtrip_data.get("characterId"),
        },
    }

    content = {
        "name": _name_preservation(
            candidate_data.get("name"),
            roundtrip_data.get("name"),
        ),
        "profile": _known_mapping_preservation(
            candidate_data.get("profile"),
            roundtrip_data.get("profile"),
            PROFILE_KEYS,
        ),
        "status": _known_mapping_preservation(
            candidate_data.get("status"),
            roundtrip_data.get("status"),
            STATUS_KEYS,
        ),
        "skills": _array_preservation(candidate_data.get("skills"), roundtrip_data.get("skills")),
        "personalities": _array_preservation(
            candidate_data.get("personalities"),
            roundtrip_data.get("personalities"),
        ),
        "memories": _memory_preservation(
            candidate_data.get("memories"),
            roundtrip_data.get("memories"),
        ),
        "icon": _icon_preservation(candidate_data.get("icon"), roundtrip_data.get("icon")),
    }
    html_report = {
        "candidate": _html_signature(candidate_raw),
        "roundtrip": _html_signature(roundtrip_raw),
    }

    schema_compatible = schema_candidate == schema_roundtrip
    structured_content_compatible = _structured_content_compatible(content)
    icon_compatible = _icon_compatible(content["icon"])
    candidate_html_present = all(
        html_report["candidate"]["idCounts"].get(identifier, 0) == 1
        for identifier in CANDIDATE_REQUIRED_HTML_IDS
    )
    game_export_html_present = all(
        html_report["roundtrip"]["requiredIds"].get(identifier, 0) == 1
        for identifier in GAME_EXPORT_REQUIRED_HTML_IDS
    )
    game_contract_compatible = bool(
        schema_compatible
        and structured_content_compatible
        and icon_compatible
        and candidate_html_present
        and game_export_html_present
    )
    return {
        "privacy": "No character text, IDs, tags, or image bytes are included in this report.",
        "schema": {
            "same": schema_compatible,
            "candidate": schema_candidate,
            "roundtrip": schema_roundtrip,
        },
        "metadata": metadata,
        "content": content,
        "html": html_report,
        "verdict": {
            "schemaCompatible": schema_compatible,
            "structuredContentCompatible": structured_content_compatible,
            "iconCompatible": icon_compatible,
            "candidateHtmlContractPresent": candidate_html_present,
            "gameExportHtmlContractPresent": game_export_html_present,
            "gameContractCompatible": game_contract_compatible,
            "readyForManualReview": game_contract_compatible,
            "manualReviewRequired": True,
        },
    }


def _load_document(raw: bytes, label: str) -> dict[str, Any]:
    try:
        span = find_unique_script_json(raw)
    except HtmlStructureError as error:
        raise RoundTripComparisonError(f"{label}: {error}") from error
    try:
        value = json.loads(raw[span.content_start : span.content_end].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RoundTripComparisonError(f"{label}: invalid character-sheet-data JSON") from error
    if not isinstance(value, dict):
        raise RoundTripComparisonError(f"{label}: JSON root must be an object")
    if not isinstance(value.get("data"), dict):
        raise RoundTripComparisonError(f"{label}: data must be an object")
    return value


def _schema_signature(value: object) -> object:
    if isinstance(value, dict):
        return {
            "type": "object",
            "keys": list(value),
            "values": {key: _schema_signature(child) for key, child in value.items()},
        }
    if isinstance(value, list):
        return {
            "type": "array",
            "count": len(value),
            "items": [_schema_signature(child) for child in value],
        }
    return {"type": _type_name(value)}


def _safe_scalar_comparison(
    candidate: object,
    roundtrip: object,
    *,
    expose_value: bool,
) -> dict[str, object]:
    result: dict[str, object] = {
        "candidateType": _type_name(candidate),
        "roundtripType": _type_name(roundtrip),
        "same": candidate == roundtrip,
    }
    if expose_value:
        result["candidateValue"] = candidate
        result["roundtripValue"] = roundtrip
    return result


def _known_mapping_preservation(
    candidate: object,
    roundtrip: object,
    keys: tuple[str, ...],
) -> dict[str, object]:
    if not isinstance(candidate, dict) or not isinstance(roundtrip, dict):
        return {
            "candidateType": _type_name(candidate),
            "roundtripType": _type_name(roundtrip),
            "allKnownValuesPreserved": False,
            "fields": {key: False for key in keys},
        }
    fields = {key: candidate.get(key) == roundtrip.get(key) for key in keys}
    return {
        "candidateType": "object",
        "roundtripType": "object",
        "allKnownValuesPreserved": all(fields.values()),
        "fields": fields,
    }


def _name_preservation(candidate: object, roundtrip: object) -> dict[str, object]:
    exact = candidate == roundtrip
    accepted_blank_normalization = (
        candidate == "" and isinstance(roundtrip, str) and roundtrip != ""
    )
    return {
        "candidateType": _type_name(candidate),
        "roundtripType": _type_name(roundtrip),
        "exact": exact,
        "candidateEmpty": candidate == "",
        "roundtripEmpty": roundtrip == "",
        "acceptedBlankNameNormalization": accepted_blank_normalization,
        "compatible": exact or accepted_blank_normalization,
    }


def _array_preservation(candidate: object, roundtrip: object) -> dict[str, object]:
    if not isinstance(candidate, list) or not isinstance(roundtrip, list):
        return {
            "candidateType": _type_name(candidate),
            "roundtripType": _type_name(roundtrip),
            "candidateCount": len(candidate) if isinstance(candidate, list) else None,
            "roundtripCount": len(roundtrip) if isinstance(roundtrip, list) else None,
            "orderAndValuesPreserved": False,
            "items": [],
        }
    items = []
    for index in range(max(len(candidate), len(roundtrip))):
        left = candidate[index] if index < len(candidate) else None
        right = roundtrip[index] if index < len(roundtrip) else None
        items.append(
            {
                "index": index,
                "candidateType": _type_name(left),
                "roundtripType": _type_name(right),
                "schemaSame": _schema_signature(left) == _schema_signature(right),
                "valuePreserved": left == right,
            }
        )
    return {
        "candidateType": "array",
        "roundtripType": "array",
        "candidateCount": len(candidate),
        "roundtripCount": len(roundtrip),
        "orderAndValuesPreserved": candidate == roundtrip,
        "items": items,
    }


def _memory_preservation(candidate: object, roundtrip: object) -> dict[str, object]:
    base = _array_preservation(candidate, roundtrip)
    if not isinstance(candidate, list) or not isinstance(roundtrip, list):
        base["placeholderSequencePreserved"] = False
        base["nonEmptyIdFormatsValid"] = False
        return base
    candidate_placeholders = [
        item.get("isPlaceholder") if isinstance(item, dict) else None for item in candidate
    ]
    roundtrip_placeholders = [
        item.get("isPlaceholder") if isinstance(item, dict) else None for item in roundtrip
    ]
    non_empty_ids = [
        item.get("id")
        for item in roundtrip
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item.get("id")
    ]
    base["placeholderSequencePreserved"] = candidate_placeholders == roundtrip_placeholders
    base["nonEmptyIdFormatsValid"] = all(
        isinstance(value, str) and MEMORY_ID_PATTERN.fullmatch(value) is not None
        for value in non_empty_ids
    )
    return base


def _icon_preservation(candidate: object, roundtrip: object) -> dict[str, object]:
    if not isinstance(candidate, dict) or not isinstance(roundtrip, dict):
        return {
            "candidateType": _type_name(candidate),
            "roundtripType": _type_name(roundtrip),
            "mimePreserved": False,
            "dataPreserved": False,
        }
    candidate_uri = candidate.get("dataUri")
    roundtrip_uri = roundtrip.get("dataUri")
    candidate_webp = _webp_data_uri_info(candidate_uri)
    roundtrip_webp = _webp_data_uri_info(roundtrip_uri)
    dimensions_preserved = bool(
        candidate_webp.get("valid")
        and roundtrip_webp.get("valid")
        and candidate_webp.get("width") == roundtrip_webp.get("width")
        and candidate_webp.get("height") == roundtrip_webp.get("height")
    )
    return {
        "candidateType": "object",
        "roundtripType": "object",
        "mimePreserved": candidate.get("mime") == roundtrip.get("mime"),
        "dataPreserved": candidate_uri == roundtrip_uri,
        "candidateWebp": candidate_webp,
        "roundtripWebp": roundtrip_webp,
        "dimensionsPreserved": dimensions_preserved,
        "acceptedGameReencode": candidate_uri != roundtrip_uri and dimensions_preserved,
        "candidateDataSha256": _hash_string(candidate_uri),
        "roundtripDataSha256": _hash_string(roundtrip_uri),
    }


def _html_signature(raw: bytes) -> dict[str, object]:
    ids = {
        identifier: len(
            re.findall(
                rb"\bid\s*=\s*([\"'])" + re.escape(identifier.encode("ascii")) + rb"\1",
                raw,
                re.I,
            )
        )
        for identifier in ALL_HTML_IDS
    }
    direct_counts = {
        identifier: _simple_direct_li_count(raw, identifier)
        for identifier in ("skills-value", "personality-value", "memories-value")
    }
    return {
        "idCounts": ids,
        "requiredIds": ids,
        "directLiCounts": direct_counts,
        "hasExternalScriptSource": re.search(rb"<script\b[^>]*\bsrc\s*=", raw, re.I) is not None,
        "hasExternalStylesheet": re.search(
            rb"<link\b[^>]*\brel\s*=\s*([\"'])stylesheet\1",
            raw,
            re.I,
        )
        is not None,
    }


def _simple_direct_li_count(raw: bytes, identifier: str) -> int | None:
    match = re.search(
        rb"<ul\b[^>]*\bid\s*=\s*([\"'])"
        + re.escape(identifier.encode("ascii"))
        + rb"\1[^>]*>(.*?)</ul\s*>",
        raw,
        re.I | re.S,
    )
    if match is None:
        return None
    content = match.group(2)
    return len(re.findall(rb"<li\b", content, re.I))


def _structured_content_compatible(content: dict[str, object]) -> bool:
    name = content["name"]
    profile = content["profile"]
    status = content["status"]
    skills = content["skills"]
    personalities = content["personalities"]
    memories = content["memories"]
    return bool(
        isinstance(name, dict)
        and name.get("compatible")
        and isinstance(profile, dict)
        and profile.get("allKnownValuesPreserved")
        and isinstance(status, dict)
        and status.get("allKnownValuesPreserved")
        and isinstance(skills, dict)
        and skills.get("orderAndValuesPreserved")
        and isinstance(personalities, dict)
        and personalities.get("orderAndValuesPreserved")
        and isinstance(memories, dict)
        and memories.get("orderAndValuesPreserved")
    )


def _icon_compatible(value: object) -> bool:
    return bool(
        isinstance(value, dict)
        and value.get("mimePreserved")
        and (value.get("dataPreserved") or value.get("acceptedGameReencode"))
    )


def _dict_at(value: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    child = value.get(key)
    if not isinstance(child, dict):
        raise RoundTripComparisonError(f"{label} must be an object")
    return child


def _type_name(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return type(value).__name__


def _matches_string(value: object, pattern: re.Pattern[str]) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _hash_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _webp_data_uri_info(value: object) -> dict[str, object]:
    result: dict[str, object] = {
        "valid": False,
        "width": None,
        "height": None,
        "encodedByteCount": None,
    }
    if not isinstance(value, str):
        return result
    prefix = "data:image/webp;base64,"
    if not value.startswith(prefix):
        return result
    try:
        payload = base64.b64decode(value[len(prefix) :], validate=True)
    except (ValueError, binascii.Error):
        return result
    result["encodedByteCount"] = len(payload)
    dimensions = _webp_dimensions(payload)
    if dimensions is None:
        return result
    result["valid"] = True
    result["width"], result["height"] = dimensions
    return result


def _webp_dimensions(payload: bytes) -> tuple[int, int] | None:
    if len(payload) < 30 or payload[:4] != b"RIFF" or payload[8:12] != b"WEBP":
        return None
    offset = 12
    while offset + 8 <= len(payload):
        chunk_type = payload[offset : offset + 4]
        chunk_size = struct.unpack_from("<I", payload, offset + 4)[0]
        data_start = offset + 8
        data_end = data_start + chunk_size
        if data_end > len(payload):
            return None
        chunk = payload[data_start:data_end]
        if chunk_type == b"VP8X" and len(chunk) >= 10:
            width = 1 + int.from_bytes(chunk[4:7], "little")
            height = 1 + int.from_bytes(chunk[7:10], "little")
            return width, height
        if chunk_type == b"VP8 " and len(chunk) >= 10 and chunk[3:6] == b"\x9d\x01\x2a":
            width = struct.unpack_from("<H", chunk, 6)[0] & 0x3FFF
            height = struct.unpack_from("<H", chunk, 8)[0] & 0x3FFF
            return width, height
        if chunk_type == b"VP8L" and len(chunk) >= 5 and chunk[0] == 0x2F:
            bits = int.from_bytes(chunk[1:5], "little")
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
            return width, height
        offset = data_end + (chunk_size & 1)
    return None
