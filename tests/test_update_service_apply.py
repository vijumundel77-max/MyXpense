"""Tests for the update apply/handoff logic."""
import sys
import subprocess
from pathlib import Path
from unittest import TestCase, mock

# Ensure the services package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import update_service  # noqa: E402


class ApplyUpdateTest(TestCase):
    @mock.patch("services.update_service.subprocess.Popen")
    @mock.patch("services.update_service.os.getpid", return_value=1234)
    def test_apply_update_spawns_detached_helper_dev(self, mock_getpid, mock_popen):
        """Development (non‑frozen) path uses python -m."""
        with mock.patch.object(sys, "frozen", False, create=True):
            installer = Path("C:/tmp/ExpenzoSetup-1.2.3.exe")
            update_service.apply_update(installer)

        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        cmd = args[0]
        self.assertIn(sys.executable, cmd)
        self.assertIn("-m", cmd)
        self.assertIn("services.update_service", cmd)
        self.assertIn("--apply-helper", cmd)
        self.assertIn("1234", cmd)
        self.assertIn(str(installer), cmd)

        if sys.platform == "win32":
            self.assertTrue(kwargs["creationflags"] & subprocess.DETACHED_PROCESS)
            self.assertTrue(kwargs["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP)

    @mock.patch("services.update_service.subprocess.Popen")
    @mock.patch("services.update_service.os.getpid", return_value=5678)
    def test_apply_update_spawns_detached_helper_frozen(self, mock_getpid, mock_popen):
        """Frozen (PyInstaller) path re‑launches the same exe."""
        with mock.patch.object(sys, "frozen", True, create=True):
            installer = Path("C:/tmp/ExpenzoSetup-1.2.3.exe")
            update_service.apply_update(installer)

        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        cmd = args[0]
        # In frozen mode the command is the exe itself, no -m
        self.assertEqual(cmd[0], sys.executable)
        self.assertNotIn("-m", cmd)
        self.assertNotIn("services.update_service", cmd)
        self.assertIn("--apply-helper", cmd)
        self.assertIn("5678", cmd)
        self.assertIn(str(installer), cmd)

        if sys.platform == "win32":
            self.assertTrue(kwargs["creationflags"] & subprocess.DETACHED_PROCESS)
            self.assertTrue(kwargs["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP)

    @mock.patch("services.update_service._wait_for_pid")
    @mock.patch("services.update_service.subprocess.run")
    def test_apply_helper_waits_and_runs_installer(self, mock_run, mock_wait):
        pid = 42
        installer = Path("C:/tmp/ExpenzoSetup-1.2.3.exe")
        update_service._apply_helper(pid, installer)

        mock_wait.assert_called_once_with(pid)
        mock_run.assert_called_once_with(
            [str(installer), "/VERYSILENT", "/NORESTART"],
            check=True,
        )

    @mock.patch("services.update_service._wait_for_pid", side_effect=TimeoutError("timed out"))
    @mock.patch("services.update_service.subprocess.run")
    def test_apply_helper_logs_on_wait_failure(self, mock_run, mock_wait):
        pid = 99
        installer = Path("C:/tmp/ExpenzoSetup-1.2.3.exe")
        with self.assertRaises(TimeoutError):
            update_service._apply_helper(pid, installer)
        # Ensure installer not launched
        mock_run.assert_not_called()