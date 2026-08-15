"""PyInstaller spec for Expenzo 1.0.0 (onedir, windowed).

Build:  python -m PyInstaller packaging/expenzo.spec --noconfirm --clean
Output: dist/Expenzo/Expenzo.exe

The application database is NOT bundled: a clean database is created by the
app itself under the per-user data dir (%%APPDATA%%\\Expenzo) on first run,
and existing user data there is always preserved across reinstalls.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

# Resolve repo-root paths explicitly: a spec file's relative paths are
# interpreted relative to the spec file's own directory, not the CWD.
_SPEC_DIR = Path(SPECPATH).resolve()
_ROOT = _SPEC_DIR.parent

block_cipher = None

datas, binaries, hiddenimports = collect_all("customtkinter")
datas += [(str(_ROOT / "assets" / "expenzo.ico"), "assets")]

hiddenimports += ["darkdetect", "PIL._tkinter_finder"]

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
