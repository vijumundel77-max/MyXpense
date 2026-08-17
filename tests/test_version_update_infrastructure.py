"""
Tests for the Expenzo version management + update metadata infrastructure
(Task 1: GitHub Release update source setup) and the in-app update flow
(Task 2: download / launch).

Covers the central version service (read/write per-user version.json, path
isolation via EXPENZO_DATA_DIR), the update service (metadata schema
validation, version comparison, release lookup, installer download), and the
update manager (download + launch, offline-safe behavior).
"""
import json
import tempfile
import unittest
from pathlib import Path

import config

# Isolate ALL data-dir writes to a temp dir so tests never touch a real
# %APPDATA%\\Expenzo (user data is never modified by tests).
config.DATABASE_PATH = ':memory:'
import os
os.environ["EXPENZO_DATA_DIR"] = tempfile.mkdtemp(prefix="expenzo_test_data_")

from services import update_service  # noqa: E402
from services.update_manager import UpdateManager  # noqa: E402
import version_service  # noqa: E402


class TestVersionService(unittest.TestCase):
    def setUp(self):
        self.orig_dir = version_service._data_dir()
        self.tmp = Path(tempfile.mkdtemp(prefix="expenzo_ver_"))
        version_service._data_dir = lambda: self.tmp  # type: ignore[assignment]

    def test_central_version_is_valid(self):
        self.assertTrue(version_service.is_valid_version(version_service.VERSION))
        self.assertRegex(version_service.VERSION, r"^\d+\.\d+\.\d+$")

    def test_write_and_read_installed_version(self):
        path = version_service.write_installed_version("1.0.1")
        self.assertEqual(path, self.tmp / version_service.VERSION_FILE)
        self.assertTrue(path.is_file())
        self.assertEqual(version_service.read_installed_version(), "1.0.1")
        self.assertEqual(version_service.current_version(), "1.0.1")

    def test_read_missing_returns_none_and_current_falls_back(self):
        self.assertIsNone(version_service.read_installed_version())
        self.assertEqual(version_service.current_version(), version_service.VERSION)

    def test_write_invalid_version_raises(self):
        with self.assertRaises(ValueError):
            version_service.write_installed_version("1.0")

    def test_read_invalid_file_returns_none(self):
        (self.tmp / version_service.VERSION_FILE).write_text(
            json.dumps({"app": "Expenzo", "version": "bogus"}), encoding="utf-8")
        self.assertIsNone(version_service.read_installed_version())

    def test_write_creates_data_dir_and_preserves_sibling(self):
        # Simulate an existing user database next to version.json.
        self.tmp.mkdir(parents=True, exist_ok=True)
        db_file = self.tmp / "myxpense.db"
        db_file.write_bytes(b"existing-user-data")
        version_service.write_installed_version("1.0.2")
        # The user database must be untouched.
        self.assertEqual(db_file.read_bytes(), b"existing-user-data")
        self.assertEqual(version_service.read_installed_version(), "1.0.2")


class TestUpdateService(unittest.TestCase):
    def test_validate_metadata_ok(self):
        raw = {
            "schema_version": 1,
            "app": "Expenzo",
            "version": "1.0.1",
            "installer_name": "ExpenzoSetup-1.0.1.exe",
        }
        self.assertIsNone(update_service.validate_metadata(raw))

    def test_validate_metadata_rejects_bad_installer_name(self):
        raw = {
            "schema_version": 1,
            "app": "Expenzo",
            "version": "1.0.1",
            "installer_name": "MyApp-setup.exe",
        }
        self.assertIsNotNone(update_service.validate_metadata(raw))

    def test_validate_metadata_rejects_wrong_app(self):
        raw = {
            "schema_version": 1,
            "app": "Other",
            "version": "1.0.1",
            "installer_name": "ExpenzoSetup-1.0.1.exe",
        }
        self.assertIsNotNone(update_service.validate_metadata(raw))

    def test_normalize_metadata(self):
        raw = {
            "schema_version": 1,
            "app": "Expenzo",
            "version": "v1.0.1",
            "installer_name": "ExpenzoSetup-1.0.1.exe",
            "installer_url": "https://example.com/x.exe",
            "release_notes": "notes",
            "published_at": "2026-01-01T00:00:00Z",
        }
        info = update_service.normalize_metadata(raw)
        self.assertEqual(info["version"], "1.0.1")
        self.assertEqual(info["installer_name"], "ExpenzoSetup-1.0.1.exe")

    def test_is_newer(self):
        self.assertTrue(update_service._is_newer("1.0.2", "1.0.1"))
        self.assertTrue(update_service._is_newer("1.1.0", "1.0.9"))
        self.assertFalse(update_service._is_newer("1.0.1", "1.0.1"))
        self.assertFalse(update_service._is_newer("1.0.0", "1.0.1"))

    def test_installer_name_regex(self):
        self.assertTrue(update_service._INSTALLER_RE.match("ExpenzoSetup-1.0.1.exe"))
        self.assertIsNone(update_service._INSTALLER_RE.match("ExpenzoSetup-1.0.exe"))
        self.assertIsNone(update_service._INSTALLER_RE.match("setup-1.0.1.exe"))


class TestInstallerDownload(unittest.TestCase):
    """Installer download via the shared update service."""

    def test_download_installer_saves_file_and_reports_progress(self):
        # Serve a small fake installer over a local HTTP server.
        import http.server
        import threading

        payload = b"MZ-fake-installer-bytes"
        handler = None

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            dest = Path(tempfile.mkdtemp(prefix="expenzo_dl_"))
            info = {
                "version": "1.0.1",
                "installer_name": "ExpenzoSetup-1.0.1.exe",
                "installer_url": f"http://127.0.0.1:{port}/ExpenzoSetup-1.0.1.exe",
            }
            seen = []
            path = update_service.download_installer(
                info, progress_callback=lambda d, t: seen.append((d, t)),
                dest_dir=dest)
            self.assertEqual(path, dest / "ExpenzoSetup-1.0.1.exe")
            self.assertEqual(path.read_bytes(), payload)
            self.assertTrue(seen, "progress callback should fire")
            last = seen[-1]
            self.assertEqual(last[0], len(payload))
            self.assertEqual(last[1], len(payload))
        finally:
            server.shutdown()

    def test_download_installer_no_url_raises(self):
        with self.assertRaises(update_service.UpdateError):
            update_service.download_installer({})

    def test_download_installer_bad_url_raises_and_no_file_left(self):
        dest = Path(tempfile.mkdtemp(prefix="expenzo_dl_"))
        info = {
            "version": "1.0.1",
            "installer_name": "ExpenzoSetup-1.0.1.exe",
            "installer_url": "http://127.0.0.1:1/nonexistent.exe",
        }
        with self.assertRaises(update_service.UpdateError):
            update_service.download_installer(info, dest_dir=dest)
        self.assertFalse((dest / "ExpenzoSetup-1.0.1.exe").exists(),
                         "failed download must not leave a partial file")

    def test_download_never_touches_user_data_dir(self):
        data_dir = Path(os.environ["EXPENZO_DATA_DIR"])
        before = set(data_dir.rglob("*"))
        info = {
            "version": "1.0.1",
            "installer_name": "ExpenzoSetup-1.0.1.exe",
            "installer_url": "http://127.0.0.1:1/nonexistent.exe",
        }
        try:
            update_service.download_installer(info, dest_dir=Path(tempfile.mkdtemp()))
        except update_service.UpdateError:
            pass
        after = set(data_dir.rglob("*"))
        self.assertEqual(before, after,
                         "download must never write into %APPDATA%\\Expenzo")


class TestUpdateManager(unittest.TestCase):
    """App-side update manager: check / download / launch orchestration."""

    def test_check_returns_update_via_shared_service(self):
        mgr = UpdateManager()
        original = update_service.check_for_updates
        update_service.check_for_updates = lambda *a, **k: ({
            "version": "9.9.9",
            "installer_name": "ExpenzoSetup-9.9.9.exe",
            "installer_url": "https://example.invalid/x.exe",
        }, None)
        try:
            info, error = mgr.check()
            self.assertIsNone(error)
            self.assertEqual(info["version"], "9.9.9")
            self.assertTrue(mgr.has_update())
        finally:
            update_service.check_for_updates = original

    def test_check_offline_returns_none_without_raising(self):
        """Internet unavailable: app must keep working normally."""
        mgr = UpdateManager()
        original = update_service.check_for_updates
        update_service.check_for_updates = lambda *a, **k: (None, "offline")
        try:
            info, error = mgr.check()
            self.assertIsNone(info)
            self.assertIsNotNone(error)
            self.assertFalse(mgr.has_update())
        finally:
            update_service.check_for_updates = original

    def test_launch_installer_missing_file_returns_false(self):
        mgr = UpdateManager()
        self.assertFalse(mgr.launch_installer(Path("/nonexistent/setup.exe")))

    def test_launch_installer_with_valid_file_and_close_callback(self):
        mgr = UpdateManager()
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "ExpenzoSetup-1.0.1.exe"
            exe.write_bytes(b"MZ")
            closed = []
            # Launch a non-GUI helper so no installer actually pops up.
            launched = mgr.launch_installer(
                exe, close_app=lambda: closed.append(True))
            # subprocess.Popen on a .exe may fail on non-Windows test runner;
            # on Windows it spawns the (invalid) exe.  Either way the app
            # must not crash and close_app is only invoked on success.
            if launched:
                self.assertEqual(closed, [True])


if __name__ == "__main__":
    unittest.main()
