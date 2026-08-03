"""Assemble and verify the exact files intended for a GitHub Release."""

from __future__ import annotations

import argparse
import base64
import binascii
from hashlib import sha256
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import zipfile

try:
    from user_guide_artifacts import GuideArtifactError, replace_directory_atomically
except ModuleNotFoundError:  # Imported as scripts.package_release_assets.
    from scripts.user_guide_artifacts import (
        GuideArtifactError,
        replace_directory_atomically,
    )


PRODUCT_NAME = "SagaSeekerSkillEditor"
ONEDIR_GUIDE_NAME = "使い方.html"
_VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+\Z")
_IMAGE_SRC_PATTERN = re.compile(
    r"<img\b[^>]*?\bsrc\s*=\s*[\"'](?P<src>[^\"']+)[\"']",
    re.IGNORECASE,
)


class ReleasePackagingError(RuntimeError):
    """Raised when release assets are incomplete, unsafe, or inconsistent."""


def release_asset_names(version: str) -> tuple[str, str, str, str]:
    if _VERSION_PATTERN.fullmatch(version) is None:
        raise ReleasePackagingError(f"Invalid application version: {version}")
    return (
        f"{PRODUCT_NAME}-v{version}-windows-x64-onefile.exe",
        f"{PRODUCT_NAME}-v{version}-windows-x64-onedir.zip",
        f"{PRODUCT_NAME}-v{version}-guide.html",
        "SHA256SUMS.txt",
    )


def package_release_assets(
    onefile_executable: Path,
    onedir_directory: Path,
    standalone_guide: Path,
    output_directory: Path,
    version: str,
) -> tuple[Path, ...]:
    """Create a deterministic, rollback-safe release-candidate directory."""

    names = release_asset_names(version)
    onefile_executable = onefile_executable.resolve()
    onedir_directory = onedir_directory.resolve()
    standalone_guide = standalone_guide.resolve()
    output_directory = output_directory.resolve()
    _validate_inputs(
        onefile_executable,
        onedir_directory,
        standalone_guide,
        output_directory,
    )

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}-staged-",
            dir=output_directory.parent,
        )
    )
    try:
        shutil.copyfile(onefile_executable, staged / names[0])
        _write_deterministic_onedir_zip(onedir_directory, staged / names[1])
        shutil.copyfile(standalone_guide, staged / names[2])
        checksum_names = names[:3]
        checksum_text = "".join(
            f"{_file_sha256(staged / name)}  {name}\n"
            for name in sorted(checksum_names)
        )
        (staged / names[3]).write_text(
            checksum_text,
            encoding="utf-8",
            newline="\n",
        )
        verify_release_assets(staged, version)
        replace_directory_atomically(staged, output_directory)
    except (OSError, GuideArtifactError, zipfile.BadZipFile) as exc:
        raise ReleasePackagingError(str(exc)) from exc
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    return tuple(output_directory / name for name in names)


def verify_release_assets(output_directory: Path, version: str) -> dict[str, str]:
    """Verify filenames, checksums, standalone guide, and onedir ZIP contents."""

    output_directory = output_directory.resolve()
    names = release_asset_names(version)
    if not output_directory.is_dir():
        raise ReleasePackagingError("Release asset directory does not exist")
    entries = tuple(sorted(path.name for path in output_directory.iterdir()))
    if entries != tuple(sorted(names)):
        raise ReleasePackagingError("Release asset set does not match the required files")
    if any(not (output_directory / name).is_file() for name in names):
        raise ReleasePackagingError("Every release asset must be a regular file")

    actual_hashes = {
        name: _file_sha256(output_directory / name) for name in names[:3]
    }
    expected_lines = [
        f"{actual_hashes[name]}  {name}" for name in sorted(names[:3])
    ]
    try:
        checksum_lines = (output_directory / names[3]).read_text(
            encoding="utf-8"
        ).splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ReleasePackagingError("SHA256SUMS.txt is not readable UTF-8") from exc
    if checksum_lines != expected_lines:
        raise ReleasePackagingError("SHA256SUMS.txt does not match release assets")

    guide_bytes = (output_directory / names[2]).read_bytes()
    _validate_standalone_guide(guide_bytes)
    archive_path = output_directory / names[1]
    try:
        with zipfile.ZipFile(archive_path) as archive:
            bad_entry = archive.testzip()
            if bad_entry is not None:
                raise ReleasePackagingError(f"Corrupt ZIP entry: {bad_entry}")
            archive_names = archive.namelist()
            guide_entry = f"{PRODUCT_NAME}/{ONEDIR_GUIDE_NAME}"
            executable_entry = f"{PRODUCT_NAME}/{PRODUCT_NAME}.exe"
            if guide_entry not in archive_names or executable_entry not in archive_names:
                raise ReleasePackagingError("onedir ZIP is missing its executable or guide")
            if archive.read(guide_entry) != guide_bytes:
                raise ReleasePackagingError(
                    "onedir ZIP guide differs from the standalone release guide"
                )
            _validate_archive_names(archive_names)
    except zipfile.BadZipFile as exc:
        raise ReleasePackagingError("onedir release file is not a valid ZIP") from exc
    return actual_hashes


def _validate_inputs(
    onefile_executable: Path,
    onedir_directory: Path,
    standalone_guide: Path,
    output_directory: Path,
) -> None:
    if not onefile_executable.is_file() or onefile_executable.suffix.lower() != ".exe":
        raise ReleasePackagingError("onefile executable is missing")
    if not onedir_directory.is_dir():
        raise ReleasePackagingError("onedir build directory is missing")
    onedir_executable = onedir_directory / f"{PRODUCT_NAME}.exe"
    onedir_guide = onedir_directory / ONEDIR_GUIDE_NAME
    if not onedir_executable.is_file():
        raise ReleasePackagingError("onedir executable is missing")
    if not standalone_guide.is_file() or not onedir_guide.is_file():
        raise ReleasePackagingError("standalone or onedir guide is missing")
    if standalone_guide.read_bytes() != onedir_guide.read_bytes():
        raise ReleasePackagingError(
            "onedir guide differs from the standalone release guide"
        )
    _validate_standalone_guide(standalone_guide.read_bytes())
    if (onedir_directory / "user-guide-assets").exists():
        raise ReleasePackagingError("onedir build contains obsolete guide assets")
    if any(path.is_symlink() for path in onedir_directory.rglob("*")):
        raise ReleasePackagingError("onedir build must not contain symbolic links")
    if any(
        path.is_file() and path.suffix.lower() == ".py"
        for path in onedir_directory.rglob("*")
    ):
        raise ReleasePackagingError("onedir build contains development source files")
    if any(_paths_overlap(output_directory, path) for path in (
        onefile_executable,
        onedir_directory,
        standalone_guide,
    )):
        raise ReleasePackagingError("Release output must not overlap build inputs")


def _validate_standalone_guide(guide_bytes: bytes) -> None:
    try:
        text = guide_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReleasePackagingError("Standalone guide is not UTF-8") from exc
    sources = [match.group("src") for match in _IMAGE_SRC_PATTERN.finditer(text)]
    if not sources or any(not source.startswith("data:image/") for source in sources):
        raise ReleasePackagingError("Standalone guide has non-embedded images")
    for source in sources:
        header, separator, payload = source.partition(",")
        if not separator or not header.endswith(";base64"):
            raise ReleasePackagingError("Standalone guide has a non-Base64 image")
        try:
            base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ReleasePackagingError("Standalone guide has invalid Base64") from exc
    if "user-guide-assets/" in text or "http://" in text or "https://" in text:
        raise ReleasePackagingError("Standalone guide contains an external reference")


def _write_deterministic_onedir_zip(source: Path, output: Path) -> None:
    files = sorted(
        (path for path in source.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(source).as_posix(),
    )
    if not files:
        raise ReleasePackagingError("onedir build contains no files")
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in files:
            relative = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(
                f"{PRODUCT_NAME}/{relative}",
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            mode = 0o100755 if path.suffix.lower() == ".exe" else 0o100644
            info.external_attr = mode << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)


def _validate_archive_names(names: list[str]) -> None:
    if len(names) != len(set(names)):
        raise ReleasePackagingError("onedir ZIP contains duplicate entries")
    prefix = f"{PRODUCT_NAME}/"
    for name in names:
        pure = PurePosixPath(name)
        if (
            not name.startswith(prefix)
            or pure.is_absolute()
            or ".." in pure.parts
            or name.endswith(".py")
            or "user-guide-assets" in pure.parts
        ):
            raise ReleasePackagingError(f"Unsafe or development ZIP entry: {name}")


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _paths_overlap(first: Path, second: Path) -> bool:
    first = first.resolve()
    second = second.resolve()
    return first == second or first in second.parents or second in first.parents


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("onefile_executable", type=Path)
    parser.add_argument("onedir_directory", type=Path)
    parser.add_argument("standalone_guide", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("version")
    args = parser.parse_args()
    paths = package_release_assets(
        args.onefile_executable,
        args.onedir_directory,
        args.standalone_guide,
        args.output_directory,
        args.version,
    )
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
