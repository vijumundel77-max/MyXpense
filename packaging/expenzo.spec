"""PyInstaller spec for Expenzo (onedir, windowed).

Build:  python -m PyInstaller packaging/expenzo.spec --noconfirm --clean
Output: dist/Expenzo/Expenzo.exe

The release version comes from the CENTRAL source:
  - EXPENZO_BUILD_VERSION env var when set (the release script sets it), else
  - services/version_service.py VERSION.

The application database is NOT bundled: a clean database is created by the
app itself under the per-user data dir (%%APPDATA%%\\Expenzo) on first run,
and existing user data there is always preserved across reinstalls.
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

# Resolve repo-root paths explicitly: a spec file's relative paths are
# interpreted relative to the spec file's own directory, not the CWD.
_SPEC_DIR = Path(SPECPATH).resolve()
_ROOT = _SPEC_DIR.parent

# --- Resolve the release version ----------------------------------------- #
_BUILD_VERSION = os.environ.get("EXPENZO_BUILD_VERSION", "").strip()
if not _BUILD_VERSION:
    import re as _re
    _ver_src = (_ROOT / "version_service.py").read_text(encoding="utf-8")
    _m = _re.search(r'^VERSION\s*=\s*"(\d+\.\d+\.\d+)"', _ver_src, _re.MULTILINE)
    _BUILD_VERSION = _m.group(1) if _m else "1.0.0"
_VERSION_TUPLE = tuple(int(p) for p in _BUILD_VERSION.split(".")) + (0,)
_VERSION_TUPLE = _VERSION_TUPLE[:4]
_VERSION_STR = ".".join(str(p) for p in _VERSION_TUPLE)

# Regenerate version_info.txt with the resolved version (Windows file props).
_VERSION_INFO = _SPEC_DIR / "version_info.txt"
_VERSION_INFO.write_text(
    f"""# UTF-8
#
# VSVersionInfo for the Expenzo executable (Windows file properties).
# Generated automatically by expenzo.spec at build time.
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={_VERSION_TUPLE!r},
    prodvers={_VERSION_TUPLE!r},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'040904B0',
          [StringStruct(u'CompanyName', u'Expenzo'),
           StringStruct(u'FileDescription', u'Expenzo Accounting'),
           StringStruct(u'FileVersion', u'{_VERSION_STR}'),
           StringStruct(u'InternalName', u'Expenzo'),
           StringStruct(u'LegalCopyright', u'Copyright (c) Expenzo'),
           StringStruct(u'OriginalFilename', u'Expenzo.exe'),
           StringStruct(u'ProductName', u'Expenzo'),
           StringStruct(u'ProductVersion', u'{_VERSION_STR}')])
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
""",
    encoding="utf-8",
)

block_cipher = None

datas, binaries, hiddenimports = collect_all("customtkinter")
datas += [(str(_ROOT / "assets" / "expenzo.ico"), "assets")]

hiddenimports += ["darkdetect", "PIL._tkinter_finder", "version_service",
                  "services.update_manager"]

a = Analysis(
    [str(_ROOT / "main.py")],
    pathex=[str(_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Expenzo",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(_ROOT / "assets" / "expenzo.ico"),
    version=str(_SPEC_DIR / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Expenzo",
)
