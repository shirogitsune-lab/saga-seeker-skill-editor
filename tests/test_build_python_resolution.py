from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


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
    launcher = source.index("py.exe")
    path_python = source.index("Get-Command python")
    assert explicit < venv < launcher < path_python
    assert "3.11" in source


def test_python_resolver_accepts_explicit_supported_interpreter() -> None:
    resolver = ROOT / "scripts" / "resolve_build_python.ps1"
    command = (
        f". '{resolver}'; "
        f"$result = Resolve-BuildPython -RepositoryRoot '{ROOT}' "
        f"-PythonPath '{sys.executable}'; "
        "$result | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert Path(result["Executable"]).resolve() == Path(sys.executable).resolve()
    assert result["Description"] == "-PythonPath"
