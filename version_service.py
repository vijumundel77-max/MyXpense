"""
Expenzo — Version Service

Central place for the application version.  The build/installer/release
scripts and the app itself all read the SAME version from here, so bumping
a future release (1.0.1, 1.0.2, …) is a one-line change:

    1. edit ``VERSION`` below, or
    2. run ``python -m version_service 1.0.2`` to write a new value
       (the scripts also accept an explicit ``--version`` override).

The version is also mirrored to a per-user metadata file under
%APPDATA%\\Expenzo\\version.json so the installed app can detect the
installed release without reading the source tree.  That file lives next to
the user database — it is never touched by the installer and is never
deleted/reset/overwritten by the update or release process.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

# The single source of truth for the CURRENT release.  Bump this for every
# new release; the release builder reads it to name the installer and tag.
VERSION = "1.0.2"

# Version file name kept in the per-user data dir (same folder as the
# database) — it records which release is installed on this machine.
VERSION_FILE = "version.json"

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _data_dir() -> Path:
    """The per-user data dir, resolved exactly like config.py does."""
    env = os.environ.get("EXPENZO_DATA_DIR")
    if env:
        return Path(env)
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "Expenzo"
    return Path.home() / ".local" / "share" / "Expenzo"


def _version_file_path() -> Path:
    return _data_dir() / VERSION_FILE


def is_valid_version(value: str) -> bool:
    """True for ``MAJOR.MINOR.PATCH`` versions like ``1.0.1``."""
    return bool(_VERSION_RE.match(value or ""))


def read_installed_version() -> Optional[str]:
    """Version recorded in the per-user version.json, or None.

    Returns None when the file is missing or unreadable — the caller then
    falls back to the app's compiled-in VERSION.
    """
    try:
        path = _version_file_path()
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            value = str(data.get("version", "")).strip()
            if is_valid_version(value):
                return value
    except Exception:
        pass
    return None


def write_installed_version(version: str) -> Path:
    """Write the installed version to the per-user version.json.

    The file is created next to the database so it follows the user's data
    across machines and is preserved across reinstall/update — the installer
    never deletes it.  Creating it here is safe: it only adds a small JSON
    file alongside the existing data directory.
    """
    value = str(version).strip()
    if not is_valid_version(value):
        raise ValueError(
            f"Invalid version {version!r}; expected MAJOR.MINOR.PATCH (e.g. 1.0.1).")
    path = _version_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"app": "Expenzo", "version": value}, indent=2),
        encoding="utf-8",
    )
    return path


def current_version() -> str:
    """The installed release version: per-user record when present, else
    the compiled-in VERSION (matches the installer name ExpenzoSetup-X.X.X.exe)."""
    installed = read_installed_version()
    if installed:
        return installed
    return VERSION


if __name__ == "__main__":
    import sys

    args = [a for a in sys.argv[1:] if a.startswith("--version=")]
    new_version = args[0].split("=", 1)[1] if args else None
    if new_version:
        write_installed_version(new_version)
        print(f"Expenzo version -> {new_version} (written to {_version_file_path()})")
    else:
        print(f"Expenzo version: {current_version()} (source: {VERSION})")
