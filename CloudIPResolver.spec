# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for the one-file Windows desktop application.

Run this spec through ``scripts/build_windows.ps1`` on Windows. PyInstaller is
not a cross-compiler: a Windows executable must be created on Windows.
"""

from pathlib import Path

# PyInstaller exposes SPECPATH while executing a spec file. Because this spec is
# stored at the repository root, SPECPATH is also our project root.
PROJECT_ROOT = Path(SPECPATH)
LAUNCHER = PROJECT_ROOT / "packaging" / "windows_launcher.py"
VERSION_FILE = PROJECT_ROOT / "packaging" / "windows_version_info.txt"

a = Analysis(
    [str(LAUNCHER)],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# Passing binaries and data directly to EXE creates PyInstaller's one-file
# bundle. ``console=False`` uses the Windows GUI subsystem, so double-clicking
# CloudIPResolver.exe does not open a separate black console window.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CloudIPResolver",
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
    version=str(VERSION_FILE),
)
