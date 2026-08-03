from __future__ import annotations

import ast
from pathlib import Path
from xml.etree import ElementTree

import pytest

from scripts.verify_junit_privacy import JUnitPrivacyError, verify_junit_xml


ROOT = Path(__file__).resolve().parents[1]


def _write_junit_report(path: Path, *, skipped_message: str) -> None:
    testsuites = ElementTree.Element("testsuites")
    testsuite = ElementTree.SubElement(
        testsuites,
        "testsuite",
        {"name": "pytest", "tests": "1", "failures": "0", "errors": "0"},
    )
    testcase = ElementTree.SubElement(
        testsuite,
        "testcase",
        {
            "classname": "tests.test_private_real_html_integration",
            "name": "test_anonymous_private_integration",
        },
    )
    skipped = ElementTree.SubElement(testcase, "skipped", {"message": skipped_message})
    skipped.text = skipped_message
    ElementTree.ElementTree(testsuites).write(path, encoding="utf-8", xml_declaration=True)


def test_junit_privacy_accepts_generic_private_fixture_skip(tmp_path: Path) -> None:
    report = tmp_path / "pytest.xml"
    _write_junit_report(
        report,
        skipped_message="private integration fixtures are not available",
    )

    verify_junit_xml(report)


@pytest.mark.parametrize(
    "unsafe_text",
    [
        r"C:\Users\local-user\private-fixtures",
        "/home/local-user/private-fixtures",
        r"\\private-host\private-share\fixtures",
        "private-character-sheet.html",
    ],
    ids=("windows-absolute", "posix-user", "unc", "sheet-filename"),
)
def test_junit_privacy_rejects_local_paths_and_character_sheet_filenames(
    tmp_path: Path,
    unsafe_text: str,
) -> None:
    report = tmp_path / "pytest.xml"
    _write_junit_report(report, skipped_message=unsafe_text)

    with pytest.raises(JUnitPrivacyError, match="privacy policy"):
        verify_junit_xml(report)


def test_junit_privacy_decodes_xml_entities_before_validation(tmp_path: Path) -> None:
    report = tmp_path / "pytest.xml"
    report.write_text(
        """<?xml version=\"1.0\" encoding=\"utf-8\"?>
<testsuites><testsuite name=\"pytest\"><testcase name=\"safe\">
<skipped message=\"private&amp;sheet.html\" />
</testcase></testsuite></testsuites>
""",
        encoding="utf-8",
    )

    with pytest.raises(JUnitPrivacyError, match="privacy policy"):
        verify_junit_xml(report)


def test_junit_privacy_rejects_malformed_xml_without_echoing_input_path(
    tmp_path: Path,
) -> None:
    report = tmp_path / "private-local-name.xml"
    report.write_text("<testsuites>", encoding="utf-8")

    with pytest.raises(JUnitPrivacyError) as exc_info:
        verify_junit_xml(report)

    assert str(report) not in str(exc_info.value)


def test_private_integration_source_contains_no_concrete_fixture_identifiers() -> None:
    source_path = ROOT / "tests" / "test_private_real_html_integration.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    has_concrete_html_literal = any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and ".html" in node.value.casefold()
        and "*" not in node.value
        and "?" not in node.value
        for node in ast.walk(tree)
    )
    if has_concrete_html_literal:
        pytest.fail(
            "private integration source contains a concrete fixture filename",
            pytrace=False,
        )

    test_names = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]
    if any(not name.startswith("test_anonymous_") for name in test_names):
        pytest.fail(
            "private integration test names must describe anonymous scenarios",
            pytrace=False,
        )

    allowed_skip_reason_names = {
        "_PRIVATE_FIXTURE_SKIP_REASON",
        "_PRIVATE_SCENARIO_SKIP_REASON",
    }
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "pytest"
            and node.func.attr == "skip"
        ):
            continue
        if not (
            len(node.args) == 1
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id in allowed_skip_reason_names
        ):
            pytest.fail(
                "private integration skip reasons must use approved generic constants",
                pytrace=False,
            )


def test_public_ci_verifies_junit_privacy_before_artifact_upload() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    verifier = workflow.index("python scripts/verify_junit_privacy.py")
    upload = workflow.index("name: Publish test evidence")

    assert verifier < upload
    assert '-m "not private_integration"' in workflow
    assert "id: junit-privacy" in workflow
    assert "steps.junit-privacy.outcome == 'success'" in workflow

    private_source = (
        ROOT / "tests" / "test_private_real_html_integration.py"
    ).read_text(encoding="utf-8")
    assert "pytestmark = pytest.mark.private_integration" in private_source
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"private_integration:' in pyproject
