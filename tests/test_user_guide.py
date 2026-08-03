from __future__ import annotations

from hashlib import sha256
from html.parser import HTMLParser
import importlib.util
import base64
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
GUIDE_DIR = ROOT / "docs" / "user-guide"
GUIDE_HTML = GUIDE_DIR / "index.html"
ASSET_DIR = GUIDE_DIR / "user-guide-assets"
EXPECTED_SCREENSHOTS = (
    "01-start-screen.png",
    "02-loaded-sheet.png",
    "03-basic-information.png",
    "04-profile-comparison.png",
    "05-skills.png",
    "06-personality-keywords.png",
    "07-memories.png",
    "08-markdown-import-preview.png",
    "09-read-only.png",
    "10-save-complete.png",
    "11-multiple-profiles.png",
    "12-comparison-window.png",
    "13-vacant-skill.png",
    "14-image-change.png",
    "15-markdown-export.png",
    "16-input-error.png",
    "17-light-theme.png",
    "18-dark-theme.png",
    "19-high-contrast-theme.png",
    "20-status-edit.png",
)


class GuideParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[dict[str, str]] = []
        self.links: list[str] = []
        self.ids: set[str] = set()
        self.headings: list[int] = []
        self.scripts = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = {key: value or "" for key, value in attrs}
        if "id" in values:
            self.ids.add(values["id"])
        if tag == "img":
            self.images.append(values)
        elif tag == "a" and "href" in values:
            self.links.append(values["href"])
        elif tag == "script":
            self.scripts += 1
        elif tag in {"h1", "h2", "h3", "h4"}:
            self.headings.append(int(tag[1]))


def _parse_guide() -> tuple[str, GuideParser]:
    text = GUIDE_HTML.read_text(encoding="utf-8")
    parser = GuideParser()
    parser.feed(text)
    return text, parser


def _load_packaging_module():
    path = ROOT / "scripts" / "package_user_guide.py"
    spec = importlib.util.spec_from_file_location("package_user_guide", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    scripts_path = str(path.parent)
    sys.path.insert(0, scripts_path)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(scripts_path)
    return module


def _load_standalone_module():
    path = ROOT / "scripts" / "standalone_user_guide.py"
    spec = importlib.util.spec_from_file_location("standalone_user_guide", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tree_hash(path: Path) -> str:
    digest = sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(item.read_bytes())
    return digest.hexdigest()


def test_canonical_guide_is_offline_semantic_and_references_exact_assets() -> None:
    text, parser = _parse_guide()

    assert parser.scripts == 0
    assert "http://" not in text
    assert "https://" not in text
    assert "@import" not in text
    assert parser.headings[0] == 1
    assert not any(
        current > previous + 1
        for previous, current in zip(parser.headings, parser.headings[1:])
    )
    assert {link[1:] for link in parser.links if link.startswith("#")} <= parser.ids

    sources = [image["src"] for image in parser.images]
    assert sources == [
        f"user-guide-assets/{name}" for name in EXPECTED_SCREENSHOTS
    ]
    for image in parser.images:
        assert image["alt"].strip()
        assert image["width"] == "1440"
        assert image["height"] == "900"
        assert not image["src"].startswith(("/", "\\"))
        assert (GUIDE_DIR / image["src"]).is_file()

    assert "アプリケーションバージョン 2.0.2" in text
    assert "AI向けMarkdown形式 v2" in text
    assert "復元されません" in text


def test_standalone_guide_embeds_exact_image_bytes_deterministically(
    tmp_path: Path,
) -> None:
    module = _load_standalone_module()
    output = tmp_path / "使い方.html"
    canonical_before = GUIDE_HTML.read_bytes()
    assets_before = {
        path.name: path.read_bytes() for path in sorted(ASSET_DIR.glob("*.png"))
    }

    module.generate_standalone_user_guide(GUIDE_HTML, ASSET_DIR, output)
    first = output.read_bytes()
    module.generate_standalone_user_guide(GUIDE_HTML, ASSET_DIR, output)

    text = first.decode("utf-8")
    parser = GuideParser()
    parser.feed(text)
    sources = [image["src"] for image in parser.images]
    assert len(sources) == len(EXPECTED_SCREENSHOTS)
    assert all(source.startswith("data:image/png;base64,") for source in sources)
    decoded = [base64.b64decode(source.split(",", 1)[1], validate=True) for source in sources]
    assert decoded == [assets_before[name] for name in EXPECTED_SCREENSHOTS]
    assert output.read_bytes() == first
    assert GUIDE_HTML.read_bytes() == canonical_before
    assert {
        path.name: path.read_bytes() for path in sorted(ASSET_DIR.glob("*.png"))
    } == assets_before
    assert "user-guide-assets/" not in text
    assert "http://" not in text
    assert "https://" not in text


def test_standalone_guide_failure_preserves_existing_output(tmp_path: Path) -> None:
    import pytest

    module = _load_standalone_module()
    source = tmp_path / "index.html"
    source.write_text(
        '<html><body><img src="user-guide-assets/missing.png" alt="missing"></body></html>',
        encoding="utf-8",
    )
    output = tmp_path / "guide.html"
    output.write_bytes(b"previous-guide")

    with pytest.raises(module.StandaloneGuideError):
        module.generate_standalone_user_guide(source, ASSET_DIR, output)

    assert output.read_bytes() == b"previous-guide"
    assert not tuple(tmp_path.glob(".guide.html.*.tmp"))


def test_standalone_guide_publish_failure_is_atomic(tmp_path: Path) -> None:
    import pytest

    module = _load_standalone_module()
    output = tmp_path / "guide.html"
    output.write_bytes(b"previous-guide")

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("injected replacement failure")

    with pytest.raises(module.StandaloneGuideError):
        module.generate_standalone_user_guide(
            GUIDE_HTML,
            ASSET_DIR,
            output,
            replace_operation=fail_replace,
        )

    assert output.read_bytes() == b"previous-guide"
    assert not tuple(tmp_path.glob(".guide.html.*.tmp"))


def test_formal_screenshot_set_is_exact_and_has_fixed_dimensions() -> None:
    module_path = ROOT / "scripts" / "user_guide_artifacts.py"
    spec = importlib.util.spec_from_file_location("guide_validation", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    paths = sorted(ASSET_DIR.glob("*.png"))
    assert [path.name for path in paths] == list(EXPECTED_SCREENSHOTS)
    module.validate_screenshot_directory(
        ASSET_DIR,
        expected_names=EXPECTED_SCREENSHOTS,
        expected_size=(1440, 900),
    )


def test_packaging_is_byte_identical_removes_stale_assets_and_is_idempotent(
    tmp_path: Path,
) -> None:
    module = _load_packaging_module()
    destination = tmp_path / "distribution"
    stale = destination / "user-guide-assets" / "obsolete.png"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"obsolete")

    distributed_html = module.package_user_guide(destination)

    parser = GuideParser()
    parser.feed(distributed_html.read_text(encoding="utf-8"))
    assert len(parser.images) == len(EXPECTED_SCREENSHOTS)
    assert all(
        image["src"].startswith("data:image/png;base64,")
        for image in parser.images
    )
    assert not stale.exists()
    assert not (destination / "user-guide-assets").exists()
    assert tuple(destination.iterdir()) == (distributed_html,)
    first_hash = _tree_hash(destination)

    module.package_user_guide(destination)

    assert _tree_hash(destination) == first_hash


def test_distribution_transaction_restores_removed_obsolete_entry_on_failure(
    tmp_path: Path,
) -> None:
    import os
    import pytest

    module_path = ROOT / "scripts" / "user_guide_artifacts.py"
    spec = importlib.util.spec_from_file_location("obsolete_entry_transaction", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    destination = tmp_path / "distribution"
    old_assets = destination / "user-guide-assets"
    old_assets.mkdir(parents=True)
    (destination / "guide.html").write_bytes(b"old-html")
    (old_assets / "old.png").write_bytes(b"old-image")
    before = _tree_hash(destination)
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "guide.html").write_bytes(b"new-html")

    def fail_placement(_source: Path, _target: Path) -> None:
        raise OSError("injected placement failure")

    with pytest.raises(module.GuideArtifactError):
        module.publish_entries_atomically(
            staged,
            destination,
            entry_names=("guide.html",),
            remove_names=("user-guide-assets",),
            replace_operation=fail_placement,
        )

    assert _tree_hash(destination) == before


def test_user_guide_sources_are_not_ignored_by_git() -> None:
    ignore_lines = {
        line.strip()
        for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "*.html" in ignore_lines
    assert "!docs/user-guide/index.html" in ignore_lines
    assert not any(
        candidate in ignore_lines
        for candidate in {
            "*.png",
            "docs/",
            "docs/user-guide/",
            "docs/user-guide/user-guide-assets/",
            "scripts/",
            "tests/",
        }
    )


def test_packaging_refuses_canonical_source_directory_without_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import shutil
    import pytest

    module = _load_packaging_module()
    canonical = tmp_path / "canonical"
    shutil.copytree(GUIDE_DIR, canonical)
    monkeypatch.setattr(module, "CANONICAL_DIR", canonical)
    monkeypatch.setattr(module, "CANONICAL_HTML", canonical / "index.html")
    monkeypatch.setattr(
        module,
        "CANONICAL_ASSETS",
        canonical / "user-guide-assets",
    )
    before = _tree_hash(canonical)

    with pytest.raises(module.UserGuidePackagingError):
        module.package_user_guide(canonical)

    assert _tree_hash(canonical) == before


def test_packaging_refuses_parent_and_child_of_canonical_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import shutil
    import pytest

    module = _load_packaging_module()
    parent = tmp_path / "source-root"
    canonical = parent / "canonical"
    shutil.copytree(GUIDE_DIR, canonical)
    monkeypatch.setattr(module, "CANONICAL_DIR", canonical)
    monkeypatch.setattr(module, "CANONICAL_HTML", canonical / "index.html")
    monkeypatch.setattr(module, "CANONICAL_ASSETS", canonical / "user-guide-assets")
    before = _tree_hash(parent)

    for destination in (parent, canonical / "distribution"):
        with pytest.raises(module.UserGuidePackagingError):
            module.package_user_guide(destination)

    assert _tree_hash(parent) == before


def test_packaging_failure_preserves_previous_distribution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import pytest

    module = _load_packaging_module()
    destination = tmp_path / "distribution"
    old_assets = destination / "user-guide-assets"
    old_assets.mkdir(parents=True)
    (destination / module.DISTRIBUTED_HTML_NAME).write_text("old", encoding="utf-8")
    (old_assets / "old.png").write_bytes(b"old")
    before = _tree_hash(destination)

    def fail_publish(*_args, **_kwargs) -> None:
        raise module.GuideArtifactError("injected publish failure")

    monkeypatch.setattr(module, "publish_entries_atomically", fail_publish)
    with pytest.raises(module.UserGuidePackagingError):
        module.package_user_guide(destination)

    assert _tree_hash(destination) == before


def test_distribution_transaction_restores_both_entries_after_second_placement_fails(
    tmp_path: Path,
) -> None:
    import os
    import pytest

    module_path = ROOT / "scripts" / "user_guide_artifacts.py"
    spec = importlib.util.spec_from_file_location(
        "transaction_user_guide_artifacts",
        module_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    html_name = "使い方.html"
    assets_name = "user-guide-assets"
    destination = tmp_path / "distribution"
    old_assets = destination / assets_name
    old_assets.mkdir(parents=True)
    (destination / html_name).write_bytes(b"old-html")
    (old_assets / "old.png").write_bytes(b"old-image")
    before = _tree_hash(destination)

    staged = tmp_path / "staged"
    new_assets = staged / assets_name
    new_assets.mkdir(parents=True)
    (staged / html_name).write_bytes(b"new-html")
    (new_assets / "new.png").write_bytes(b"new-image")
    placements = 0

    def fail_on_second_placement(source: Path, target: Path) -> None:
        nonlocal placements
        placements += 1
        if placements == 2:
            raise OSError("injected second placement failure")
        os.replace(source, target)

    with pytest.raises(module.GuideArtifactError):
        module.publish_entries_atomically(
            staged,
            destination,
            entry_names=(html_name, assets_name),
            replace_operation=fail_on_second_placement,
        )

    assert placements == 2
    assert _tree_hash(destination) == before
    assert (destination / html_name).read_bytes() == b"old-html"
    assert (destination / assets_name / "old.png").read_bytes() == b"old-image"
    assert not (destination / assets_name / "new.png").exists()


def test_screenshot_generator_does_not_forge_application_status_text() -> None:
    source = (ROOT / "scripts" / "generate_user_guide_screenshots.py").read_text(
        encoding="utf-8"
    )
    assert "window.status_label.setText(" not in source
    assert "window.status_detail_label.setText(" not in source
    assert "window.file_label.setText(" not in source
    assert 'stage_message(\n            "Markdown書出し完了"' not in source


def test_screenshot_support_validates_complete_png_and_publishes_atomically(
    tmp_path: Path,
) -> None:
    module_path = ROOT / "scripts" / "user_guide_artifacts.py"
    assert module_path.is_file()
    spec = importlib.util.spec_from_file_location("user_guide_artifacts", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    valid = ASSET_DIR / EXPECTED_SCREENSHOTS[0]
    truncated = tmp_path / "truncated.png"
    truncated.write_bytes(valid.read_bytes()[:32])
    import pytest

    with pytest.raises(module.GuideArtifactError):
        module.validate_png_file(truncated, expected_size=(1440, 900))

    old = tmp_path / "published"
    old.mkdir()
    (old / "old.txt").write_text("keep", encoding="utf-8")
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "new.txt").write_text("new", encoding="utf-8")
    before = _tree_hash(old)

    def fail_after_backup(_source: Path, _target: Path) -> None:
        raise OSError("injected publish failure")

    with pytest.raises(module.GuideArtifactError):
        module.replace_directory_atomically(
            staged,
            old,
            replace_operation=fail_after_backup,
        )
    assert _tree_hash(old) == before


def test_failed_screenshot_generation_keeps_previous_complete_set(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import argparse
    import pytest

    module_path = ROOT / "scripts" / "generate_user_guide_screenshots.py"
    spec = importlib.util.spec_from_file_location("screenshot_generator", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    scripts_path = str(module_path.parent)
    sys.path.insert(0, scripts_path)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(scripts_path)
    published = tmp_path / "published"
    published.mkdir()
    (published / "old.txt").write_text("keep", encoding="utf-8")
    before = _tree_hash(published)

    def fail_after_partial_output(_args, staged: Path) -> None:
        (staged / module.SCREENSHOTS[0]).write_bytes(b"partial")
        raise RuntimeError("injected generation failure")

    monkeypatch.setattr(module, "_generate_to_directory", fail_after_partial_output)
    args = argparse.Namespace(mode="offscreen", output_dir=published)
    with pytest.raises(RuntimeError):
        module._run(args)

    assert _tree_hash(published) == before
