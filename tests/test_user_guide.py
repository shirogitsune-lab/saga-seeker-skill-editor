from __future__ import annotations

from hashlib import sha256
from html.parser import HTMLParser
import importlib.util
from pathlib import Path
import struct


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

    assert "アプリケーションバージョン 2.0.0" in text
    assert "AI向けMarkdown形式 v2" in text
    assert "復元されません" in text


def test_formal_screenshot_set_is_exact_and_has_fixed_dimensions() -> None:
    paths = sorted(ASSET_DIR.glob("*.png"))
    assert [path.name for path in paths] == list(EXPECTED_SCREENSHOTS)
    for path in paths:
        raw = path.read_bytes()
        assert raw.startswith(b"\x89PNG\r\n\x1a\n")
        assert raw[12:16] == b"IHDR"
        assert struct.unpack(">II", raw[16:24]) == (1440, 900)


def test_packaging_is_byte_identical_removes_stale_assets_and_is_idempotent(
    tmp_path: Path,
) -> None:
    module = _load_packaging_module()
    destination = tmp_path / "distribution"
    stale = destination / "user-guide-assets" / "obsolete.png"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"obsolete")

    distributed_html, distributed_assets = module.package_user_guide(destination)

    assert distributed_html.read_bytes() == GUIDE_HTML.read_bytes()
    assert not stale.exists()
    for source in sorted(ASSET_DIR.glob("*.png")):
        assert (distributed_assets / source.name).read_bytes() == source.read_bytes()
    first_hash = _tree_hash(destination)

    module.package_user_guide(destination)

    assert _tree_hash(destination) == first_hash


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
