# SPDX-License-Identifier: GPL-3.0-or-later
#
# Tests for WSL path and distro discovery.
# Tests run on Linux and must never shell out to a real wsl.exe or touch UNC paths.

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from library.moka_tss import wsl


class WslOutputDecodingTests(unittest.TestCase):
    def test_decodes_ascii_and_utf8(self):
        raw = b"Ubuntu\r\nDebian\n"
        decoded = wsl._decode_wsl_output(raw)
        self.assertEqual(decoded, "Ubuntu\nDebian\n")

    def test_decodes_utf16_le_with_null_bytes(self):
        raw = "Ubuntu\r\nDebian\r\n".encode("utf-16le")
        decoded = wsl._decode_wsl_output(raw)
        self.assertIn("Ubuntu", decoded)
        self.assertIn("Debian", decoded)
        self.assertNotIn("\x00", decoded)

    def test_empty_bytes_returns_empty_string(self):
        self.assertEqual(wsl._decode_wsl_output(b""), "")


class WslProbePlatformTests(unittest.TestCase):
    def setUp(self):
        wsl.clear_wsl_cache()

    def tearDown(self):
        wsl.clear_wsl_cache()

    @mock.patch("sys.platform", "linux")
    @mock.patch("subprocess.run")
    def test_probe_skipped_entirely_on_non_windows(self, mock_run):
        candidates = wsl.find_wsl_candidate_paths()
        self.assertEqual(candidates, [])
        mock_run.assert_not_called()

    @mock.patch("sys.platform", "darwin")
    @mock.patch("subprocess.run")
    def test_probe_skipped_entirely_on_macos(self, mock_run):
        candidates = wsl.find_wsl_candidate_paths()
        self.assertEqual(candidates, [])
        mock_run.assert_not_called()


class WslDiscoveryTests(unittest.TestCase):
    def setUp(self):
        wsl.clear_wsl_cache()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root_path = Path(self.temp_dir.name)

    def tearDown(self):
        wsl.clear_wsl_cache()

    @mock.patch("sys.platform", "win32")
    @mock.patch("subprocess.run")
    def test_windows_builds_correct_path_for_discovered_distro_and_user(self, mock_run):
        mock_run.return_value = mock.Mock(
            returncode=0,
            stdout="Ubuntu\r\n".encode("utf-16le"),
        )
        fake_user = self.root_path / "Ubuntu" / "home" / "alejandro"
        fake_user.mkdir(parents=True)

        with mock.patch.object(wsl, "WSL_LOCALHOST_ROOT", self.root_path):
            paths = wsl.find_wsl_candidate_paths()

        expected = fake_user / ".config" / "codexbar" / "dashboard-token"
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0], expected)
        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs.get("timeout"), 3.0)
        self.assertTrue(kwargs.get("creationflags", 0) >= 0)

    @mock.patch("sys.platform", "win32")
    @mock.patch("subprocess.run")
    def test_subprocess_timeout_skips_without_raising(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="wsl.exe", timeout=3.0)
        with mock.patch.object(wsl, "WSL_LOCALHOST_ROOT", self.root_path / "nonexistent"):
            paths = wsl.find_wsl_candidate_paths()
        self.assertEqual(paths, [])

    @mock.patch("sys.platform", "win32")
    @mock.patch("subprocess.run")
    def test_subprocess_error_skips_without_raising(self, mock_run):
        mock_run.side_effect = OSError("wsl.exe not found")
        with mock.patch.object(wsl, "WSL_LOCALHOST_ROOT", self.root_path / "nonexistent"):
            paths = wsl.find_wsl_candidate_paths()
        self.assertEqual(paths, [])

    @mock.patch("sys.platform", "win32")
    @mock.patch("subprocess.run")
    def test_discovery_result_is_cached_and_subprocess_runs_once(self, mock_run):
        mock_run.return_value = mock.Mock(
            returncode=0,
            stdout=b"Ubuntu\r\n",
        )
        fake_user = self.root_path / "Ubuntu" / "home" / "alejandro"
        fake_user.mkdir(parents=True)

        with mock.patch.object(wsl, "WSL_LOCALHOST_ROOT", self.root_path):
            paths1 = wsl.find_wsl_candidate_paths()
            paths2 = wsl.find_wsl_candidate_paths()

        self.assertEqual(paths1, paths2)
        self.assertEqual(mock_run.call_count, 1)

    @mock.patch("sys.platform", "win32")
    @mock.patch("subprocess.run")
    def test_fallback_to_wsl_localhost_directory_listing(self, mock_run):
        mock_run.side_effect = subprocess.SubprocessError("wsl failed")
        fake_user = self.root_path / "Debian" / "home" / "javm"
        fake_user.mkdir(parents=True)

        with mock.patch.object(wsl, "WSL_LOCALHOST_ROOT", self.root_path):
            paths = wsl.find_wsl_candidate_paths()

        expected = fake_user / ".config" / "codexbar" / "dashboard-token"
        self.assertEqual(paths, [expected])


class WslStatusTests(unittest.TestCase):
    def setUp(self):
        wsl.clear_wsl_cache()

    def tearDown(self):
        wsl.clear_wsl_cache()

    @mock.patch("sys.platform", "linux")
    def test_wsl_status_non_windows_returns_available_false(self):
        result = wsl.wsl_status()
        self.assertFalse(result["available"])
        self.assertEqual(result["distros"], [])

    @mock.patch("sys.platform", "darwin")
    def test_wsl_status_macos_returns_available_false(self):
        result = wsl.wsl_status()
        self.assertFalse(result["available"])
        self.assertEqual(result["distros"], [])

    @mock.patch("sys.platform", "win32")
    @mock.patch("library.moka_tss.wsl.get_wsl_distros")
    def test_wsl_status_windows_returns_distros(self, mock_get_distros):
        mock_get_distros.return_value = ["Ubuntu", "Debian", "Kali"]
        result = wsl.wsl_status()
        self.assertTrue(result["available"])
        self.assertEqual(result["distros"], ["Ubuntu", "Debian", "Kali"])

    @mock.patch("sys.platform", "win32")
    @mock.patch("library.moka_tss.wsl.get_wsl_distros")
    def test_wsl_status_exception_in_discovery_never_raises(self, mock_get_distros):
        mock_get_distros.side_effect = RuntimeError("wsl.exe crashed")
        result = wsl.wsl_status()
        self.assertFalse(result["available"])
        self.assertEqual(result["distros"], [])

    @mock.patch("sys.platform", "win32")
    @mock.patch("library.moka_tss.wsl.get_wsl_distros")
    def test_wsl_status_oserror_in_discovery_never_raises(self, mock_get_distros):
        mock_get_distros.side_effect = OSError("permission denied")
        result = wsl.wsl_status()
        self.assertFalse(result["available"])
        self.assertEqual(result["distros"], [])

    @mock.patch("sys.platform", "win32")
    @mock.patch("library.moka_tss.wsl.get_wsl_distros")
    def test_wsl_status_empty_distros_list(self, mock_get_distros):
        mock_get_distros.return_value = []
        result = wsl.wsl_status()
        self.assertTrue(result["available"])
        self.assertEqual(result["distros"], [])


if __name__ == "__main__":
    unittest.main()
