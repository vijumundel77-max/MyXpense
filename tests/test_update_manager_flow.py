"""Integration test for the Update Now flow via UpdateManager."""
import sys
from pathlib import Path
from unittest import TestCase, mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import update_manager  # noqa: E402
from services import update_service  # noqa: E402


class UpdateManagerFlowTest(TestCase):
    @mock.patch("services.update_manager.sys.exit")
    @mock.patch("services.update_manager.update_service.apply_update")
    @mock.patch("services.update_manager.Path.is_file", return_value=True)
    def test_launch_installer_calls_apply_update_and_exits(self, mock_is_file, mock_apply, mock_exit):
        mgr = update_manager.UpdateManager()
        installer = Path("C:/tmp/ExpenzoSetup-1.2.3.exe")
        # launch_installer should call apply_update then sys.exit(0)
        mgr.launch_installer(installer)
        mock_apply.assert_called_once_with(installer)
        mock_exit.assert_called_once_with(0)

    @mock.patch("services.update_manager.sys.exit")
    @mock.patch("services.update_manager.update_service.apply_update", side_effect=RuntimeError("helper fail"))
    @mock.patch("services.update_manager.subprocess.Popen")
    @mock.patch("services.update_manager.Path.is_file", return_value=True)
    def test_launch_installer_fallback_on_helper_failure(self, mock_is_file, mock_popen, mock_apply, mock_exit):
        mgr = update_manager.UpdateManager()
        installer = Path("C:/tmp/ExpenzoSetup-1.2.3.exe")
        mgr.launch_installer(installer, close_app=lambda: None)
        # apply_update attempted
        mock_apply.assert_called_once_with(installer)
        # fallback Popen used
        mock_popen.assert_called_once()
        # sys.exit NOT called because fallback path returns
        mock_exit.assert_not_called()