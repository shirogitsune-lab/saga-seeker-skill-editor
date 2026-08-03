from __future__ import annotations

from hashlib import sha256
import importlib.util
from pathlib import Path
import sys
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
VERSION = "2.0.2"


def _load_module():
    path = ROOT / "scripts" / "package_release_assets.py"
    spec = importlib.util.spec_from_file_location("package_release_assets", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    scripts_path = str(path.parent)
    sys.path.insert(0, scripts_path)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(scripts_path)
    return module


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    onefile = tmp_path / "onefile" / "SagaSeekerSkillEditor.exe"
    onefile.parent.mkdir()
    onefile.write_bytes(b"onefile-executable")
    onedir = tmp_path / "onedir" / "SagaSeekerSkillEditor"
    (onedir / "_internal").mkdir(parents=True)
    (onedir / "SagaSeekerSkillEditor.exe").write_bytes(b"onedir-executable")
    guide = tmp_path / "guide" / "guide.html"
    guide.parent.mkdir()
    guide.write_bytes(b'<img src="data:image/png;base64,cG5n">')
    (onedir / "使い方.html").write_bytes(guide.read_bytes())
    (onedir / "_internal" / "runtime.bin").write_bytes(b"runtime")
    return onefile, onedir, guide


def test_release_asset_set_is_exact_verified_and_deterministic(tmp_path: Path) -> None:
    module = _load_module()
    onefile, onedir, guide = _inputs(tmp_path)
    output = tmp_path / "release"

    first = module.package_release_assets(onefile, onedir, guide, output, VERSION)
    first_bytes = {path.name: path.read_bytes() for path in first}
    second = module.package_release_assets(onefile, onedir, guide, output, VERSION)

    expected_names = {
        f"SagaSeekerSkillEditor-v{VERSION}-windows-x64-onefile.exe",
        f"SagaSeekerSkillEditor-v{VERSION}-windows-x64-onedir.zip",
        f"SagaSeekerSkillEditor-v{VERSION}-guide.html",
        "SHA256SUMS.txt",
    }
    assert {path.name for path in first} == expected_names
    assert {path.name: path.read_bytes() for path in second} == first_bytes
    assert module.verify_release_assets(output, VERSION)

    archive = output / f"SagaSeekerSkillEditor-v{VERSION}-windows-x64-onedir.zip"
    with zipfile.ZipFile(archive) as package:
        assert package.read("SagaSeekerSkillEditor/使い方.html") == guide.read_bytes()
        assert "SagaSeekerSkillEditor/SagaSeekerSkillEditor.exe" in package.namelist()
        assert not any("user-guide-assets" in name for name in package.namelist())
        assert not any(name.endswith(".py") for name in package.namelist())

    checksum_lines = (output / "SHA256SUMS.txt").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(checksum_lines) == 3
    for name in sorted(expected_names - {"SHA256SUMS.txt"}):
        digest = sha256((output / name).read_bytes()).hexdigest()
        assert f"{digest}  {name}" in checksum_lines


def test_release_packaging_refuses_mismatched_onedir_guide_and_preserves_output(
    tmp_path: Path,
) -> None:
    module = _load_module()
    onefile, onedir, guide = _inputs(tmp_path)
    output = tmp_path / "release"
    output.mkdir()
    (output / "previous.txt").write_bytes(b"keep")
    (onedir / "使い方.html").write_bytes(b"different")

    with pytest.raises(module.ReleasePackagingError):
        module.package_release_assets(onefile, onedir, guide, output, VERSION)

    assert tuple(output.iterdir()) == (output / "previous.txt",)
    assert (output / "previous.txt").read_bytes() == b"keep"


def test_release_verification_rejects_tampered_file(tmp_path: Path) -> None:
    module = _load_module()
    onefile, onedir, guide = _inputs(tmp_path)
    output = tmp_path / "release"
    paths = module.package_release_assets(onefile, onedir, guide, output, VERSION)
    next(path for path in paths if path.suffix == ".html").write_bytes(b"tampered")

    with pytest.raises(module.ReleasePackagingError):
        module.verify_release_assets(output, VERSION)


def test_public_ci_verifies_and_archives_the_exact_release_candidate() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    package_step = workflow.index("python scripts/package_release_assets.py")
    extracted_smoke = workflow.index(
        "work/release-extracted/SagaSeekerSkillEditor/SagaSeekerSkillEditor.exe"
    )
    onefile_smoke = workflow.index(
        f"work/release-candidate/SagaSeekerSkillEditor-v{VERSION}-windows-x64-onefile.exe"
    )
    upload_step = workflow.index("name: release-candidate-${{ github.sha }}")

    assert package_step < extracted_smoke < onefile_smoke < upload_step
    assert workflow.count("./scripts/exe_image_smoke.ps1") >= 2
    assert "path: work/release-candidate/*" in workflow
