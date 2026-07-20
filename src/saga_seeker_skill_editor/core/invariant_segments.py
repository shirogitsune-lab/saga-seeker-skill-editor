"""Validation helpers for unchanged byte ranges."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib


class InvariantSegmentError(ValueError):
    """Raised when bytes outside allowed ranges changed."""


@dataclass(frozen=True)
class Segment:
    start: int
    end: int


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def assert_segments_equal(original: bytes, updated: bytes, segments: list[tuple[Segment, Segment]]) -> None:
    """Assert corresponding original/updated immutable segments are equal."""

    for original_segment, updated_segment in segments:
        original_bytes = original[original_segment.start : original_segment.end]
        updated_bytes = updated[updated_segment.start : updated_segment.end]
        if original_bytes != updated_bytes:
            raise InvariantSegmentError(
                "immutable segment changed: "
                f"original={original_segment.start}:{original_segment.end} "
                f"updated={updated_segment.start}:{updated_segment.end}"
            )
