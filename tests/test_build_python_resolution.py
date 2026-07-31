from __future__ import annotations

from pathlib import Path
import json
import os
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell.exe")


def _run_resolver(command: str, *, path: Path | None = None) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL is not None
    environment = os.environ.copy()
    if path is not None:
        system32 = Path(POWERSHELL).parents[2]
        environment["PATH"] = os.pathsep.join((str(path), str(system32)))
    return subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_build_script_has_no_machine_specific_python_fallback() -> None:
    source = (ROOT / "build.ps1").read_text(encoding="utf-8")

    assert "C:\\Program Files\\Python313\\python.exe" not in source
    assert "[string]$PythonPath" in source
    assert "Resolve-BuildPython" in source
    assert "uv sync --extra dev --extra build" in source


def test_python_resolver_documents_supported_candidate_order() -> None:
    resolver = ROOT / "scripts" / "resolve_build_python.ps1"
    assert resolver.is_file()
    source = resolver.read_text(encoding="utf-8")

    explicit = source.index("PythonPath")
    venv = source.index(".venv")
    launcher = source.index("Get-Command py")
    path_python = source.index("Get-Command python")
    assert explicit < venv < launcher < path_python
    assert "3.11" in source
    assert 'PrefixArguments @("-3")' in source
    assert all(selector not in source for selector in ("-3.13", "-3.12", "-3.11"))


def test_python_resolver_accepts_explicit_supported_interpreter() -> None:
    resolver = ROOT / "scripts" / "resolve_build_python.ps1"
    command = (
        f". '{resolver}'; "
        f"$result = Resolve-BuildPython -RepositoryRoot '{ROOT}' "
        f"-PythonPath '{sys.executable}'; "
        "$result | ConvertTo-Json -Compress"
    )
    completed = _run_resolver(command)
    completed.check_returncode()
    result = json.loads(completed.stdout)

    assert Path(result["Executable"]).resolve() == Path(sys.executable).resolve()
    assert result["Description"] == "-PythonPath"


def test_python_resolver_prefers_repository_local_venv() -> None:
    resolver = ROOT / "scripts" / "resolve_build_python.ps1"
    command = (
        f". '{resolver}'; "
        f"$result = Resolve-BuildPython -RepositoryRoot '{ROOT}'; "
        "$result | ConvertTo-Json -Compress"
    )
    completed = _run_resolver(command)
    completed.check_returncode()
    result = json.loads(completed.stdout)

    assert result["Description"] == ".venv"
    assert tuple(result["Version"].values()) >= (3, 11, 0, -1, 0)


def test_python_resolver_uses_launcher_default_python_3_and_supports_spaces(
    tmp_path: Path,
) -> None:
    resolver = ROOT / "scripts" / "resolve_build_python.ps1"
    command_dir = tmp_path / "launcher path with spaces"
    command_dir.mkdir()
    launcher = command_dir / "py.cmd"
    launcher.write_text(
        "@echo off\r\n"
        'if not "%1"=="-3" exit /b 2\r\n'
        f'"{sys.executable}" %2 %3\r\n',
        encoding="utf-8",
    )
    repository = tmp_path / "repository without venv"
    repository.mkdir()
    command = (
        f". '{resolver}'; "
        f"$result = Resolve-BuildPython -RepositoryRoot '{repository}'; "
        "$result | ConvertTo-Json -Compress"
    )
    completed = _run_resolver(command, path=command_dir)
    completed.check_returncode()
    result = json.loads(completed.stdout)

    assert result["Description"] == "py -3"
    assert result["PrefixArguments"] == ["-3"]


def test_python_resolver_uses_supported_path_python(tmp_path: Path) -> None:
    resolver = ROOT / "scripts" / "resolve_build_python.ps1"
    repository = tmp_path / "repository"
    repository.mkdir()
    path_dir = Path(sys.executable).parent
    command = (
        f". '{resolver}'; "
        f"$result = Resolve-BuildPython -RepositoryRoot '{repository}'; "
        "$result | ConvertTo-Json -Compress"
    )
    completed = _run_resolver(command, path=path_dir)
    completed.check_returncode()
    result = json.loads(completed.stdout)

    assert result["Description"] == "PATH python"
    assert Path(result["Executable"]).resolve() == Path(sys.executable).resolve()


def test_python_resolver_rejects_python_3_10_with_actionable_error(
    tmp_path: Path,
) -> None:
    resolver = ROOT / "scripts" / "resolve_build_python.ps1"
    command_dir = tmp_path / "old-python"
    command_dir.mkdir()
    (command_dir / "python.cmd").write_text(
        "@echo 3.10.0\r\n",
        encoding="utf-8",
    )
    repository = tmp_path / "repository"
    repository.mkdir()
    command = f". '{resolver}'; Resolve-BuildPython -RepositoryRoot '{repository}'"

    completed = _run_resolver(command, path=command_dir)

    assert completed.returncode != 0
    assert "Python 3.11 or newer was not found" in completed.stderr
    assert "Get-Command python" in completed.stderr


def test_python_resolver_reports_when_no_candidate_exists(tmp_path: Path) -> None:
    resolver = ROOT / "scripts" / "resolve_build_python.ps1"
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    repository = tmp_path / "repository"
    repository.mkdir()
    command = f". '{resolver}'; Resolve-BuildPython -RepositoryRoot '{repository}'"

    completed = _run_resolver(command, path=empty_path)

    assert completed.returncode != 0
    assert "Python 3.11 or newer was not found" in completed.stderr
    assert "Configure -PythonPath, .venv, py -3, or PATH" in completed.stderr
