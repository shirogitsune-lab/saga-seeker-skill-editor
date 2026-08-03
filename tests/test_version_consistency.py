from __future__ import annotations

from pathlib import Path
import re
import tomllib

from saga_seeker_skill_editor import __version__


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "2.0.2"


def test_application_version_is_consistent_across_current_release_metadata() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock_text = (ROOT / "uv.lock").read_text(encoding="utf-8")
    guide_text = (ROOT / "docs" / "user-guide" / "index.html").read_text(
        encoding="utf-8"
    )
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    editable_package = re.search(
        r'\[\[package\]\]\s+name = "saga-seeker-skill-editor"\s+version = "([^"]+)"',
        lock_text,
    )
    assert editable_package is not None
    assert {
        __version__,
        pyproject["project"]["version"],
        editable_package.group(1),
    } == {EXPECTED_VERSION}
    assert f"アプリケーションバージョン {EXPECTED_VERSION}" in guide_text
    assert f"v{EXPECTED_VERSION}-guide.html" in readme
    assert f'"{EXPECTED_VERSION}"' in workflow
    assert "AI向けMarkdown形式 v2" in guide_text
