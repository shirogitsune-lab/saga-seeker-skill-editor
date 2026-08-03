from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from xml.etree import ElementTree


class JUnitPrivacyError(RuntimeError):
    """Raised when a JUnit report is missing, invalid, or unsafe to publish."""


_FORBIDDEN_PATTERNS = (
    re.compile(r"(?i)(?<![A-Za-z0-9])[A-Z]:[\\/]"),
    re.compile(r"(?<![\\])\\\\[^\\/\s<>:'\"]+[\\/]"),
    re.compile(r"(?i)(?<![:/A-Za-z0-9])/(?:home|users|tmp|var|mnt)(?:/|$)"),
    re.compile(r"(?i)file:(?:/{2,3}|\\{2,3})"),
    re.compile(r"(?i)\.html(?:\b|$)"),
)


def _report_values(root: ElementTree.Element) -> Iterable[str]:
    for element in root.iter():
        yield from element.attrib.values()
        if element.text:
            yield element.text
        if element.tail:
            yield element.tail


def verify_junit_xml(report_path: Path) -> None:
    """Reject report content that could identify a private local fixture."""

    try:
        root = ElementTree.parse(report_path).getroot()
    except (OSError, ElementTree.ParseError) as exc:
        raise JUnitPrivacyError("JUnit report could not be verified") from exc

    if root.tag not in {"testsuite", "testsuites"}:
        raise JUnitPrivacyError("JUnit report has an unsupported root element")

    for value in _report_values(root):
        if any(pattern.search(value) for pattern in _FORBIDDEN_PATTERNS):
            raise JUnitPrivacyError("JUnit report violates the publication privacy policy")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify that a pytest JUnit XML report is safe to publish."
    )
    parser.add_argument("junit_xml", type=Path)
    args = parser.parse_args(argv)
    try:
        verify_junit_xml(args.junit_xml)
    except JUnitPrivacyError:
        print("JUnit privacy verification failed.", file=sys.stderr)
        return 1
    print("JUnit privacy verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
