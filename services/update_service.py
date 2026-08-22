"""
Expenzo — Update Service

The app-side counterpart of the GitHub Release setup (Task 1).  This module
defines the RELEASE METADATA SCHEMA that every GitHub Release for Expenzo
must carry, and provides the "latest version" lookup the app will use later
(Task 2 builds the Dashboard banner / Settings update UI on top of this).

Metadata contract (release.json attached to each GitHub Release):

    {
      "schema_version": 1,
      "app": "Expenzo",
      "version": "1.0.1",
      "installer_name": "ExpenzoSetup-1.0.1.exe",
      "installer_url": "https://github.com/<owner>/<repo>/releases/download/v1.0.1/ExpenzoSetup-1.0.1.exe",
      "release_notes": "What changed in this release.",
      "published_at": "2026-01-15T10:00:00Z"
    }

The GitHub Release itself uses the tag ``v<version>`` (e.g. ``v1.0.1``) and
attaches exactly one installer asset named ``ExpenzoSetup-<version>.exe``.

Lookup sources, in order:
  1. A file URL / local path (tests, local staging).
  2. The GitHub Releases API: ``https://api.github.com/repos/<owner>/<repo>/releases/latest``.
  3. A raw metadata file in the repo: ``https://raw.githubusercontent.com/<owner>/<repo>/main/updates/latest.json``
     (the release builder keeps this file in sync with the latest release).
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.request import Request, urlopen

from version_service import VERSION, is_valid_version

# Where update metadata lives in the repository (also mirrored into GitHub
# Releases as an attached "release.json" asset).
DEFAULT_REPO = "vijumundel77-max/MyXpense"
METADATA_BRANCH = "main"
REPO_METADATA_PATH = "updates/latest.json"

SCHEMA_VERSION = 1
_INSTALLER_RE = re.compile(r"^ExpenzoSetup-(\d+\.\d+\.\d+)\.exe$")


class UpdateError(Exception):
    """Raised when release metadata cannot be fetched or is invalid."""


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _parse_version(value: Any) -> Optional[str]:
    if isinstance(value, str):
        value = value.strip().lstrip("v")
        if is_valid_version(value):
            return value
    return None


def _fetch_json(url: str, timeout: float = 15.0) -> Dict[str, Any]:
    try:
        req = Request(url, headers={"User-Agent": "Expenzo-UpdateCheck/1.0"})
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise UpdateError(f"Could not fetch update metadata from {url}: {exc}") from exc


# --------------------------------------------------------------------------- #
# metadata validation / normalization
# --------------------------------------------------------------------------- #
def validate_metadata(raw: Dict[str, Any], expected_app: str = "Expenzo") -> Optional[str]:
    """Validate a release-metadata dict.  Returns an error message or None."""
    if not isinstance(raw, dict):
        return "Release metadata is not an object."
    if int(raw.get("schema_version", 0)) != SCHEMA_VERSION:
        return f"Unsupported metadata schema_version (expected {SCHEMA_VERSION})."
    if raw.get("app") != expected_app:
        return f"Metadata is not for {expected_app}."
    if not _parse_version(raw.get("version")):
        return "Metadata version is missing or invalid (expected MAJOR.MINOR.PATCH)."
    installer = str(raw.get("installer_name", "") or "")
    if not _INSTALLER_RE.match(installer):
        return f"installer_name must match ExpenzoSetup-X.X.X.exe (got {installer!r})."
    return None


def normalize_metadata(raw: Dict[str, Any], installer_url: Optional[str] = None) -> Dict[str, Any]:
    """Turn a raw metadata dict into the canonical release-info dict."""
    version = _parse_version(raw.get("version"))
    return {
        "version": version,
        "installer_name": raw.get("installer_name", ""),
        "installer_url": installer_url or raw.get("installer_url", ""),
        "release_notes": raw.get("release_notes", ""),
        "published_at": raw.get("published_at", ""),
    }


# --------------------------------------------------------------------------- #
# GitHub Releases API source
# --------------------------------------------------------------------------- #
def check_github_latest(owner: str = "vijumundel77-max",
                        repo: str = "MyXpense") -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Query the GitHub Releases API for the latest published release.

    Returns ``(release_info, None)`` on success and ``(None, error)`` when
    the fetch fails or the release is not a valid Expenzo release.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    try:
        data = _fetch_json(url)
    except UpdateError as exc:
        return None, str(exc)
    tag = str(data.get("tag_name", "") or "").strip()
    version = _parse_version(tag.lstrip("v")) or _parse_version(data.get("name"))
    if not version:
        return None, f"Latest release {tag!r} has no valid version tag."
    installer_name, installer_url = "", ""
    for asset in data.get("assets", []) or []:
        name = str(asset.get("name", "") or "")
        if _INSTALLER_RE.match(name):
            installer_name = name
            installer_url = asset.get("browser_download_url", "") or ""
            break
    if not installer_name:
        return None, f"Release v{version} has no ExpenzoSetup-X.X.X.exe asset."
    notes = data.get("body", "") or ""
    try:
        published = datetime.strptime(str(data.get("published_at", "")),
                                      "%Y-%m-%dT%H:%M:%SZ").isoformat() + "Z"
    except Exception:
        published = ""
    info = {
        "version": version,
        "installer_name": installer_name,
        "installer_url": installer_url,
        "release_notes": notes,
        "published_at": published,
    }
    return info, None


# --------------------------------------------------------------------------- #
# repo metadata file source (updates/latest.json on the default branch)
# --------------------------------------------------------------------------- #
def check_repo_metadata(owner: str = "vijumundel77-max",
                        repo: str = "MyXpense",
                        branch: str = METADATA_BRANCH) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    url = (f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/"
           f"{REPO_METADATA_PATH}")
    try:
        raw = _fetch_json(url)
    except UpdateError as exc:
        return None, str(exc)
    error = validate_metadata(raw)
    if error:
        return None, f"Invalid update metadata in repo: {error}"
    info = normalize_metadata(raw)
    if not info.get("installer_url"):
        info["installer_url"] = (
            f"https://github.com/{owner}/{repo}/releases/download/"
            f"v{info['version']}/{info['installer_name']}")
    return info, None


# --------------------------------------------------------------------------- #
# public entry point
# --------------------------------------------------------------------------- #
def check_for_updates(current_version: Optional[str] = None,
                      owner: str = "vijumundel77-max",
                      repo: str = "MyXpense") -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Return the latest Expenzo release info when it is newer than the
    current version, else ``(None, None)``.  ``(None, error)`` on failure.

    The result dict is what Task 2's update UI will consume.
    """
    installed = (current_version or VERSION).strip().lstrip("v")
    info, error = check_github_latest(owner, repo)
    if info is None and error is not None:
        info, error = check_repo_metadata(owner, repo)
    if error is not None:
        return None, error
    if info is None:
        return None, None
    if _is_newer(info["version"], installed):
        return info, None
    return None, None


def _is_newer(candidate: str, current: str) -> bool:
    """True when candidate (X.Y.Z) is strictly newer than current."""
    def _parts(value: str):
        return tuple(int(p) for p in value.split(".")[:3])
    try:
        return _parts(candidate) > _parts(current)
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# installer download
# --------------------------------------------------------------------------- #
def _default_download_dir() -> Path:
    """Download location for the installer.

    Never touches the per-user data dir (%APPDATA%\\Expenzo) — user data is
    preserved by the update flow.  Falls back to the system temp dir when the
    user's Downloads folder is not writable.
    """
    try:
        if os.name == "nt":
            import ctypes.wintypes  # noqa: F401
            import ctypes
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(
                    None, 5, None, 0, buf) == 0 and buf.value:
                downloads = Path(buf.value)
                if downloads.is_dir():
                    return downloads
    except Exception:
        pass
    return Path(tempfile.gettempdir())


def download_installer(release_info: Dict[str, Any],
                       progress_callback: Optional[Callable[[int, Optional[int]], None]] = None,
                       dest_dir: Optional[Path] = None) -> Path:
    """Download the release installer from ``release_info`` to ``dest_dir``.

    ``release_info`` is exactly what ``check_for_updates`` returns (its
    ``installer_url`` / ``installer_name``).  ``progress_callback`` receives
    ``(bytes_done, bytes_total_or_None)`` so a UI can show progress.

    Returns the downloaded file's path.  Raises ``UpdateError`` on failure.
    The download goes to the user's Downloads folder (or temp) — never into
    %APPDATA%\\Expenzo, so the user database is never at risk.
    """
    if not release_info:
        raise UpdateError("No release information to download.")
    url = str(release_info.get("installer_url", "") or "")
    if not url:
        raise UpdateError("Release has no installer URL.")
    file_name = str(release_info.get("installer_name", "") or "")
    if not file_name:
        file_name = url.rsplit("/", 1)[-1] or "ExpenzoSetup.exe"

    dest = (dest_dir or _default_download_dir()) / file_name
    dest = dest.resolve()
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    if dest.is_file():
        try:
            dest.unlink()
        except Exception:
            pass

    try:
        req = Request(url, headers={"User-Agent": "Expenzo-Updater/1.0"})
        with urlopen(req, timeout=60.0) as resp:
            total = None
            try:
                total = int(resp.headers.get("Content-Length") or 0) or None
            except Exception:
                total = None
            done = 0
            with dest.open("wb") as out:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    if progress_callback is not None:
                        try:
                            progress_callback(done, total)
                        except Exception:
                            pass
    except Exception as exc:
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass
        raise UpdateError(f"Installer download failed: {exc}") from exc

    if dest.stat().st_size == 0:
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass
        raise UpdateError("Downloaded installer is empty.")
    return dest


# --------------------------------------------------------------------------- #
# apply stage – detached helper
# --------------------------------------------------------------------------- #
def _wait_for_pid(pid: int, timeout: float = 30.0) -> None:
    """Block until the process with ``pid`` exits (Windows)."""
    if os.name != "nt":
        # fallback generic poll
        start = time.time()
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            if time.time() - start > timeout:
                raise TimeoutError(f"Process {pid} did not exit within {timeout}s")
            time.sleep(0.2)

    # Windows: use WaitForSingleObject on a handle with SYNCHRONIZE access
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    SYNCHRONIZE = 0x00100000
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        # process already gone
        return
    try:
        WAIT_OBJECT_0 = 0
        INFINITE = 0xFFFFFFFF
        # Wait with a reasonable timeout loop to allow KeyboardInterrupt etc.
        while True:
            result = kernel32.WaitForSingleObject(handle, 1000)  # 1 sec
            if result == WAIT_OBJECT_0:
                return
    finally:
        kernel32.CloseHandle(handle)


def _apply_helper(pid: int, installer_path: Path) -> None:
    """Runs in a detached process: waits for the old Expenzo to exit,
    then launches the Inno Setup installer silently. Errors are logged
    to a temporary file so they are not swallowed.
    """
    log_path = Path(tempfile.gettempdir()) / "Expenzo_update_error.log"
    try:
        _wait_for_pid(pid)
        # Launch installer silently; Inno Setup will restart the app via its [Run] section
        subprocess.run(
            [str(installer_path), "/VERYSILENT", "/NORESTART"],
            check=True,
        )
    except Exception as exc:  # pragma: no cover – defensive logging
        try:
            with log_path.open("a", encoding="utf-8") as lf:
                lf.write(f"{datetime.utcnow().isoformat()}Z update failed: {exc}\n")
        except Exception:
            pass
        # Re‑raise so the detached process exits non‑zero (visible in logs)
        raise


def _build_helper_cmd(pid: int, installer_path: Path) -> list[str]:
    """Return the command line to launch the detached helper.
    In a frozen (PyInstaller) build sys.executable is the Expenzo.exe itself,
    so we invoke the same executable with a custom flag.  In development we
    fall back to ``python -m services.update_service``.
    """
    if getattr(sys, "frozen", False):
        # Frozen build – re‑launch the same exe with a dedicated flag
        return [sys.executable, "--apply-helper", str(pid), str(installer_path)]
    # Development / source run
    return [
        sys.executable,
        "-m",
        "services.update_service",
        "--apply-helper",
        str(pid),
        str(installer_path),
    ]


def apply_update(installer_path: Path) -> None:
    """Spawn a detached helper that will apply the update after the current
    Expenzo process terminates. This function returns immediately; the caller
    should exit the application (e.g. ``sys.exit(0)``) after calling it.
    """
    pid = os.getpid()
    helper_cmd = _build_helper_cmd(pid, installer_path)
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    # Detach completely – redirect output to a log file to avoid console windows
    log_path = Path(tempfile.gettempdir()) / "Expenzo_update_helper.log"
    with log_path.open("w", encoding="utf-8") as log_file:
        subprocess.Popen(
            helper_cmd,
            creationflags=creationflags,
            stdout=log_file,
            stderr=log_file,
            close_fds=True,
        )
    # Caller is expected to exit now.


# --------------------------------------------------------------------------- #
# command‑line entry point for the detached helper
# --------------------------------------------------------------------------- #
if __name__ == "__main__":  # pragma: no cover
    if "--apply-helper" in sys.argv:
        try:
            idx = sys.argv.index("--apply-helper")
            pid = int(sys.argv[idx + 1])
            installer_path = Path(sys.argv[idx + 2])
            _apply_helper(pid, installer_path)
        except Exception as exc:  # pragma: no cover
            # Ensure a non‑zero exit code so the launcher can detect failure
            sys.exit(1)
    # No other CLI modes for now
