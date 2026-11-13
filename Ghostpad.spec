# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build definition for Ghostpad.

Build with:  python -m PyInstaller --noconfirm --clean Ghostpad.spec
Output:      dist/Ghostpad/Ghostpad.exe  (ship the whole dist/Ghostpad folder)
"""

import re
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

ROOT = Path(SPECPATH)  # noqa: F821 - injected by PyInstaller

# Single source of truth for the version: __version__ in ghostpad.pyw.
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "ghostpad.pyw").read_text(encoding="utf-8")).group(1)
VERSION_TUPLE = (*(int(part) for part in VERSION.split(".")), 0)[:4]

# Shown in Explorer > Properties > Details and in "Installed apps".
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=VERSION_TUPLE, prodvers=VERSION_TUPLE),
    kids=[
        StringFileInfo([
            StringTable("040904B0", [
                StringStruct("CompanyName", "The Ghostpad authors"),
                StringStruct("FileDescription", "Ghostpad"),
                StringStruct("FileVersion", VERSION),
                StringStruct("InternalName", "Ghostpad"),
                StringStruct("LegalCopyright", "MIT License"),
                StringStruct("OriginalFilename", "Ghostpad.exe"),
                StringStruct("ProductName", "Ghostpad"),
                StringStruct("ProductVersion", VERSION),
            ])
        ]),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

a = Analysis(
    ["ghostpad.pyw"],
    pathex=[],
    binaries=[],
    datas=[("assets/ghostpad.ico", "assets")],  # window/dialog icon at runtime
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Ghostpad",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-packed executables trigger more antivirus false positives
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/ghostpad.ico",  # Explorer / Start menu icon
    version=version_info,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Ghostpad",
)
