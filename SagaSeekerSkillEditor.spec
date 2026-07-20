# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


root = Path.cwd()
icon = root / "assets" / "kanaria.ico"
styles = root / "src" / "saga_seeker_skill_editor" / "gui" / "styles"
data = root / "src" / "saga_seeker_skill_editor" / "data"

a = Analysis(
    ["src/saga_seeker_skill_editor/main.py"],
    pathex=[str(root / "src")],
    binaries=[],
    datas=[
        (str(icon), "assets"),
        (str(styles), "saga_seeker_skill_editor/gui/styles"),
        (str(data), "saga_seeker_skill_editor/data"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PIL", "Pillow"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SagaSeekerSkillEditor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon),
)
