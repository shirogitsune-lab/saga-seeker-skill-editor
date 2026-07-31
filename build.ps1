param(
    [ValidateSet("onedir", "onefile")]
    [string]$Mode = "onedir",
    [string]$PythonPath
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Set-StrictMode -Version Latest
. (Join-Path $Root "scripts\resolve_build_python.ps1")
$PythonSpec = Resolve-BuildPython -RepositoryRoot $Root -PythonPath $PythonPath

function Invoke-BuildPython {
    param([Parameter(ValueFromRemainingArguments = $true)][object[]]$Arguments)
    $AllArguments = @($script:PythonSpec.PrefixArguments) + $Arguments
    & $script:PythonSpec.Executable @AllArguments
}

Invoke-BuildPython -Arguments @("-c", "import pytest, PyInstaller, PySide6")
if ($LASTEXITCODE -ne 0) {
    throw "Build dependencies are missing. Run: uv sync --extra dev --extra build"
}
$TestTemp = Join-Path $Root "work\tmp"
New-Item -ItemType Directory -Force -Path $TestTemp | Out-Null
$TestRunId = [Guid]::NewGuid().ToString("N")
$PytestBaseTemp = Join-Path $TestTemp "pytest-build-$TestRunId"

if (-not (Test-Path "assets\kanaria.ico")) {
    Invoke-BuildPython -Arguments @("scripts\convert_icon.py")
}

$env:PYTHONPATH = "src"
$env:TMP = $TestTemp
$env:TEMP = $TestTemp
Invoke-BuildPython -Arguments @("-m", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp=$PytestBaseTemp")
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($Mode -eq "onedir") {
    $SpecPath = Join-Path $Root "work\pyinstaller-spec"
    $IconPath = Join-Path $Root "assets\kanaria.ico"
    $AssetsPath = Join-Path $Root "assets"
    $StylesPath = Join-Path $Root "src\saga_seeker_skill_editor\gui\styles"
    $DataPath = Join-Path $Root "src\saga_seeker_skill_editor\data"
    New-Item -ItemType Directory -Force -Path $SpecPath | Out-Null
    Invoke-BuildPython -Arguments @("-m", "PyInstaller", "--clean", "--noconfirm", "--onedir", "--windowed", "--icon", $IconPath, "--add-data", "$AssetsPath;assets", "--add-data", "$StylesPath;saga_seeker_skill_editor/gui/styles", "--add-data", "$DataPath;saga_seeker_skill_editor/data", "--specpath", $SpecPath, "--name", "SagaSeekerSkillEditor", "src\saga_seeker_skill_editor\main.py")
} else {
    Invoke-BuildPython -Arguments @("-m", "PyInstaller", "--clean", "--noconfirm", "SagaSeekerSkillEditor.spec")
}
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($Mode -eq "onedir") {
    $GuideDestination = Join-Path $Root "dist\SagaSeekerSkillEditor"
} else {
    $GuideDestination = Join-Path $Root "dist"
}
Invoke-BuildPython -Arguments @("scripts\package_user_guide.py", $GuideDestination)
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
