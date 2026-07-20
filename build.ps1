param(
    [ValidateSet("onedir", "onefile")]
    [string]$Mode = "onedir"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $Python = $VenvPython
} else {
    $Python = "C:\Program Files\Python313\python.exe"
}
$TestTemp = Join-Path $Root "work\tmp"
New-Item -ItemType Directory -Force -Path $TestTemp | Out-Null

if (-not (Test-Path "assets\kanaria.ico")) {
    & $Python "scripts\convert_icon.py"
}

$env:PYTHONPATH = "src"
$env:TMP = $TestTemp
$env:TEMP = $TestTemp
& $Python -m pytest -q --basetemp=work\pytest-tmp -o cache_dir=work\.pytest_cache
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($Mode -eq "onedir") {
    $SpecPath = Join-Path $Root "work\pyinstaller-spec"
    $IconPath = Join-Path $Root "assets\kanaria.ico"
    $StylesPath = Join-Path $Root "src\saga_seeker_skill_editor\gui\styles"
    New-Item -ItemType Directory -Force -Path $SpecPath | Out-Null
    & $Python -m PyInstaller --clean --noconfirm --onedir --windowed --icon $IconPath --add-data "$IconPath;assets" --add-data "$StylesPath;saga_seeker_skill_editor/gui/styles" --specpath $SpecPath --name SagaSeekerSkillEditor "src\saga_seeker_skill_editor\main.py"
} else {
    & $Python -m PyInstaller --clean --noconfirm SagaSeekerSkillEditor.spec
}
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
