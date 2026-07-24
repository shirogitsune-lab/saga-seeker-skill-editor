from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from uuid import UUID

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QColor, QImage, QImageWriter

from saga_seeker_skill_editor.core.phase0_candidate_sheet import (
    GenerationInputs,
    build_full_probe_document,
    render_candidate_html,
)
from saga_seeker_skill_editor.core.phase0_roundtrip import compare_roundtrip


FIXED_NOW = datetime(2026, 7, 24, 3, 4, 5, 123456, tzinfo=timezone.utc)
UUIDS = (
    UUID("123e4567-e89b-42d3-a456-426614174000"),
    UUID("223e4567-e89b-42d3-a456-426614174000"),
    UUID("323e4567-e89b-42d3-a456-426614174000"),
    UUID("423e4567-e89b-42d3-a456-426614174000"),
    UUID("523e4567-e89b-42d3-a456-426614174000"),
    UUID("623e4567-e89b-42d3-a456-426614174000"),
)


def _document() -> dict[str, object]:
    values = iter(UUIDS)
    return build_full_probe_document(
        icon_webp=b"round-trip-icon",
        generation=GenerationInputs(
            uuid_factory=lambda: next(values),
            clock=lambda: FIXED_NOW,
            local_timezone=timezone(timedelta(hours=9)),
        ),
        default_skill={
            "id": "42",
            "name": "PRIVATE DEFAULT NAME",
            "description": "PRIVATE DEFAULT DESCRIPTION",
            "type": "physical",
            "key": "Default_Key",
        },
        personality_keyword={
            "id": 1,
            "name": "PRIVATE PERSONALITY NAME",
            "type": "positive",
            "karma": "virtue",
        },
    )


def _as_game_export_html(raw: bytes) -> bytes:
    return raw.replace(
        b"<main>",
        b'<div id="name"></div><div id="icon"></div><main id="container">',
        1,
    ).replace(b'<div id="profile-value">', b"<div>", 1)


def _webp_bytes(*, quality: int) -> bytes:
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(QColor("#6b7280"))
    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    assert buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    writer = QImageWriter(buffer, b"webp")
    writer.setQuality(quality)
    assert writer.write(image), writer.errorString()
    buffer.close()
    return bytes(byte_array)


def test_exact_data_in_game_export_html_is_ready_and_report_is_private() -> None:
    candidate_raw = render_candidate_html(_document())
    roundtrip_raw = _as_game_export_html(candidate_raw)

    report = compare_roundtrip(candidate_raw, roundtrip_raw)
    serialized = json.dumps(report, ensure_ascii=False)

    assert report["verdict"] == {
        "schemaCompatible": True,
        "structuredContentCompatible": True,
        "iconCompatible": True,
        "candidateHtmlContractPresent": True,
        "gameExportHtmlContractPresent": True,
        "gameContractCompatible": True,
        "readyForManualReview": True,
        "manualReviewRequired": True,
    }
    assert "PRIVATE DEFAULT NAME" not in serialized
    assert "PRIVATE DEFAULT DESCRIPTION" not in serialized
    assert "PRIVATE PERSONALITY NAME" not in serialized
    assert "Phase 0 思い出" not in serialized
    assert "memory_123" not in serialized


def test_metadata_change_is_reported_without_failing_user_content() -> None:
    candidate = _document()
    roundtrip = deepcopy(candidate)
    roundtrip["exportedAt"] = "2026-07-24T04:00:00.0000000Z"

    report = compare_roundtrip(
        render_candidate_html(candidate),
        _as_game_export_html(render_candidate_html(roundtrip)),
    )

    assert report["schema"]["same"] is True
    assert report["metadata"]["exportedAt"]["same"] is False
    assert report["verdict"]["structuredContentCompatible"] is True
    assert report["verdict"]["readyForManualReview"] is True


def test_user_content_change_and_schema_change_are_distinguished() -> None:
    candidate = _document()
    changed_content = deepcopy(candidate)
    changed_content["data"]["profile"]["basicSettings"] = "GAME CHANGED THIS VALUE"
    missing_key = deepcopy(candidate)
    del missing_key["data"]["status"]["charm"]

    content_report = compare_roundtrip(
        render_candidate_html(candidate),
        render_candidate_html(changed_content),
    )
    schema_report = compare_roundtrip(
        render_candidate_html(candidate),
        render_candidate_html(missing_key),
    )

    assert content_report["schema"]["same"] is True
    assert content_report["verdict"]["structuredContentCompatible"] is False
    assert content_report["verdict"]["readyForManualReview"] is False
    assert schema_report["schema"]["same"] is False
    assert schema_report["verdict"]["schemaCompatible"] is False


def test_game_blank_name_and_webp_reencode_are_compatible_normalizations() -> None:
    candidate = _document()
    candidate["data"]["name"] = ""
    candidate["data"]["icon"]["dataUri"] = (
        "data:image/webp;base64,"
        + base64.b64encode(_webp_bytes(quality=90)).decode("ascii")
    )
    roundtrip = deepcopy(candidate)
    roundtrip["data"]["name"] = "game-generated-name"
    roundtrip["data"]["icon"]["dataUri"] = (
        "data:image/webp;base64,"
        + base64.b64encode(_webp_bytes(quality=80)).decode("ascii")
    )

    report = compare_roundtrip(
        render_candidate_html(candidate),
        _as_game_export_html(render_candidate_html(roundtrip)),
    )

    assert report["content"]["name"] == {
        "candidateType": "string",
        "roundtripType": "string",
        "exact": False,
        "candidateEmpty": True,
        "roundtripEmpty": False,
        "acceptedBlankNameNormalization": True,
        "compatible": True,
    }
    assert report["content"]["icon"]["dataPreserved"] is False
    assert report["content"]["icon"]["dimensionsPreserved"] is True
    assert report["content"]["icon"]["acceptedGameReencode"] is True
    assert report["verdict"]["gameContractCompatible"] is True
