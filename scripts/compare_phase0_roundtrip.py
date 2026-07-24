"""Compare a Phase 0 candidate with a game-exported round-trip sheet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from saga_seeker_skill_editor.core.phase0_roundtrip import (
    RoundTripComparisonError,
    compare_roundtrip,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("roundtrip", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = compare_roundtrip(
            args.candidate.read_bytes(),
            args.roundtrip.read_bytes(),
        )
    except (OSError, RoundTripComparisonError) as error:
        print(f"Phase 0 comparison failed: {error}", file=sys.stderr)
        return 2
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["verdict"]["readyForManualReview"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
