"""
Expenzo — Update Manager

Orchestrates the in-app auto-update flow (Task 2) on top of the EXISTING
update infrastructure:

    1. check  -> services.update_service.check_for_updates()
    2. download -> services.update_service.download_installer() with progress
    3. launch -> run the downloaded Inno Setup installer (per-user, no admin)
    4. close  -> exit the current app instance
    5. restart -> the installer's [Run] step relaunches Expenzo after install

Safety guarantees:
  - The installer is downloaded to the user's Downloads folder / temp dir —
    NEVER into %APPDATA%\\Expenzo, so the database + user data are untouched.
  - A failed download leaves the current app fully intact (nothing is
    launched, nothing is deleted).
  - If the installer cannot be launched, the app keeps running normally.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

from services import update_service
from version_service import current_version


class UpdateManager:
    """App-side coordinator for checking / downloading / launching updates."""

    def __init__(self) -> None:
        self._release_info: Optional[dict] = None

    # ------------------------------------------------------------------ #
    # check
    # ------------------------------------------------------------------ #
    def check(self) -> Tuple[Optional[dict], Optional[str]]:
        """Reuse the shared update-check logic (no duplicate implementation)."""
        return update_service.check_for_updates(current_version=current_version())

    def has_update(self) -> bool:
        info, error = self.check()
        return info is not None

    # ------------------------------------------------------------------ #
    # download
    # ------------------------------------------------------------------ #
    def download(self,
                 progress_callback: Optional[Callable[[int, Optional[int]], None]] = None,
                 release_info: Optional[dict] = None) -> Path:
        """Download the latest installer.  Returns the file path.

        ``release_info`` may be passed in (e.g. cached from a prior check);
        otherwise the latest release is resolved again via the shared check.
        """
        info = release_info or self._release_info
        if info is None:
            info, error = self.check()
            if info is None:
                raise update_service.UpdateError(error or "No update available.")
        self._release_info = info
        return update_service.download_installer(info, progress_callback)

    # ------------------------------------------------------------------ #
    # launch installer + close app
    # ------------------------------------------------------------------ #
    def launch_installer(self, installer_path: Path,
                         close_app: Optional[Callable[[], None]] = None) -> bool:
        """Launch the downloaded installer via the detached helper and exit the app.

        The helper (``services.update_service.apply_update``) waits for the
        current Expenzo process to terminate, then runs the Inno Setup installer
        silently.  This method never returns – it calls ``sys.exit(0)`` after
        spawning the helper.
        """
        path = Path(installer_path)
        if not path.is_file():
            return False
        # Use the new apply_update flow (works in dev and frozen builds)
        try:
            update_service.apply_update(path)
        except Exception:
            # If we cannot spawn the helper, fall back to the old direct launch
            # to keep the app usable.
            try:
                if os.name == "nt":
                    subprocess.Popen(
                        [str(path)],
                        cwd=str(path.parent),
                        close_fds=True,
                    )
                else:
                    subprocess.Popen(
                        [str(path)],
                        cwd=str(path.parent),
                        start_new_session=True,
                    )
            except Exception:
                return False
            # If fallback succeeded, close the app via provided callback.
            if close_app is not None:
                try:
                    close_app()
                except Exception:
                    pass
            return True

        # Helper spawned successfully – terminate this process so the helper
        # can wait for our PID to disappear.
        sys.exit(0)
        # Unreachable, but keep return for type checkers.
        return True

    def restart_app(self) -> None:
        """Relaunch Expenzo after the new version was installed.

        Best-effort: spawns the current executable (frozen app or dev
        interpreter).  A failure here is non-fatal — the installer's [Run]
        step normally handles the restart, so this is only a fallback.
        """
        try:
            subprocess.Popen([str(Path(sys.executable).resolve())], close_fds=True)
        except Exception:
            pass


# Shared instance for the UI.
update_manager = UpdateManager()
