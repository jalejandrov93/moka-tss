# SPDX-License-Identifier: GPL-3.0-or-later
#
# Tests for library/mascota/paths.py -- path resolution that must behave
# identically running from source, frozen one-dir, and frozen one-file
# (PyInstaller), and must never write user data inside sys._MEIPASS.

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from library.mascota.paths import base_dir, is_frozen, resource_path, user_data_dir

REPO_ROOT = Path(__file__).resolve().parents[3]


class IsFrozenTests(unittest.TestCase):
    def test_not_frozen_by_default(self):
        with patch.object(sys, "frozen", False, create=True):
            self.assertFalse(is_frozen())

    def test_frozen_when_sys_frozen_true(self):
        with patch.object(sys, "frozen", True, create=True):
            self.assertTrue(is_frozen())


class BaseDirTests(unittest.TestCase):
    def test_source_returns_repo_root(self):
        with patch.object(sys, "frozen", False, create=True):
            self.assertEqual(base_dir(), REPO_ROOT)

    def test_frozen_with_meipass_returns_meipass(self):
        with tempfile.TemporaryDirectory() as tmp:
            meipass = str(Path(tmp).resolve())
            with patch.object(sys, "frozen", True, create=True), \
                    patch.object(sys, "_MEIPASS", meipass, create=True):
                self.assertEqual(base_dir(), Path(meipass))

    def test_frozen_without_meipass_falls_back_to_executable_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            install_dir = Path(tmp).resolve()
            exe_path = install_dir / "mascota.exe"
            with patch.object(sys, "frozen", True, create=True):
                if hasattr(sys, "_MEIPASS"):
                    delattr(sys, "_MEIPASS")
                with patch.object(sys, "executable", str(exe_path)):
                    self.assertEqual(base_dir(), install_dir)


class ResourcePathTests(unittest.TestCase):
    def test_joins_against_base_dir_from_source(self):
        with patch.object(sys, "frozen", False, create=True):
            self.assertEqual(
                resource_path("res", "mascota", "rules.yaml"),
                REPO_ROOT / "res" / "mascota" / "rules.yaml",
            )

    def test_joins_against_base_dir_frozen_meipass(self):
        with tempfile.TemporaryDirectory() as tmp:
            meipass = str(Path(tmp).resolve())
            with patch.object(sys, "frozen", True, create=True), \
                    patch.object(sys, "_MEIPASS", meipass, create=True):
                self.assertEqual(
                    resource_path("res", "docs", "error-in-theme.png"),
                    Path(meipass) / "res" / "docs" / "error-in-theme.png",
                )

    def test_joins_against_base_dir_frozen_one_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            install_dir = Path(tmp).resolve()
            exe_path = install_dir / "mascota.exe"
            with patch.object(sys, "frozen", True, create=True):
                if hasattr(sys, "_MEIPASS"):
                    delattr(sys, "_MEIPASS")
                with patch.object(sys, "executable", str(exe_path)):
                    self.assertEqual(
                        resource_path("external", "LibreHardwareMonitor", "HidSharp.dll"),
                        install_dir / "external" / "LibreHardwareMonitor" / "HidSharp.dll",
                    )

    def test_no_parts_returns_base_dir(self):
        with patch.object(sys, "frozen", False, create=True):
            self.assertEqual(resource_path(), REPO_ROOT)


class UserDataDirTests(unittest.TestCase):
    def test_never_inside_meipass(self):
        with tempfile.TemporaryDirectory() as tmp:
            meipass = Path(tmp).resolve() / "_MEI123456"
            with patch.object(sys, "frozen", True, create=True), \
                    patch.object(sys, "_MEIPASS", str(meipass), create=True):
                out = user_data_dir()
                self.assertNotEqual(out, meipass)
                self.assertNotIn(meipass, out.parents)
                self.assertFalse(str(out).startswith(str(meipass)))

    def test_windows_uses_appdata(self):
        with patch.object(sys, "platform", "win32"):
            with patch.dict(os.environ, {"APPDATA": r"C:\Users\alejandro\AppData\Roaming"}):
                self.assertEqual(
                    user_data_dir(),
                    Path(r"C:\Users\alejandro\AppData\Roaming") / "Mascota",
                )

    def test_windows_without_appdata_falls_back_to_home(self):
        with patch.object(sys, "platform", "win32"):
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(
                    user_data_dir(),
                    Path.home() / "AppData" / "Roaming" / "Mascota",
                )

    def test_linux_uses_xdg_data_home(self):
        with patch.object(sys, "platform", "linux"):
            with patch.dict(os.environ, {"XDG_DATA_HOME": "/home/alejandro/.local/share"}):
                self.assertEqual(
                    user_data_dir(),
                    Path("/home/alejandro/.local/share") / "mascota",
                )

    def test_linux_without_xdg_falls_back_to_default(self):
        with patch.object(sys, "platform", "linux"):
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(
                    user_data_dir(),
                    Path.home() / ".local" / "share" / "mascota",
                )

    def test_macos_is_not_treated_as_windows(self):
        with patch.object(sys, "platform", "darwin"):
            with patch.dict(os.environ, {}, clear=True):
                out = user_data_dir()
                self.assertNotIn("AppData", str(out))
                self.assertEqual(out, Path.home() / ".local" / "share" / "mascota")


class LhmDllPathIndependentOfCwdTests(unittest.TestCase):
    """library/sensors/sensors_librehardwaremonitor.py builds its two DLL
    paths from resource_path(); this proves that primitive is stable when
    the process working directory changes, which is the exact scenario
    a double-clicked .exe or a shortcut with no "Start in" hits."""

    def test_dll_path_unchanged_when_cwd_changes(self):
        with patch.object(sys, "frozen", False, create=True):
            before = resource_path("external", "LibreHardwareMonitor", "LibreHardwareMonitorLib.dll")
            orig_cwd = os.getcwd()
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    os.chdir(tmp)
                    after = resource_path("external", "LibreHardwareMonitor", "LibreHardwareMonitorLib.dll")
            finally:
                os.chdir(orig_cwd)
            self.assertEqual(before, after)
            self.assertEqual(before, REPO_ROOT / "external" / "LibreHardwareMonitor" / "LibreHardwareMonitorLib.dll")

    def test_hidsharp_dll_path_unchanged_when_cwd_changes(self):
        with patch.object(sys, "frozen", False, create=True):
            before = resource_path("external", "LibreHardwareMonitor", "HidSharp.dll")
            orig_cwd = os.getcwd()
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    os.chdir(tmp)
                    after = resource_path("external", "LibreHardwareMonitor", "HidSharp.dll")
            finally:
                os.chdir(orig_cwd)
            self.assertEqual(before, after)

    def test_lhm_source_no_longer_calls_getcwd(self):
        source = (REPO_ROOT / "library" / "sensors" / "sensors_librehardwaremonitor.py").read_text(encoding="utf-8")
        self.assertNotIn("os.getcwd()", source)

    def test_lhm_source_uses_resource_path(self):
        source = (REPO_ROOT / "library" / "sensors" / "sensors_librehardwaremonitor.py").read_text(encoding="utf-8")
        self.assertIn("resource_path(", source)

    def test_theme_editor_error_image_no_longer_uses_naked_relative_path(self):
        source = (REPO_ROOT / "theme-editor.py").read_text(encoding="utf-8")
        self.assertNotIn('Image.open("res/docs/error-in-theme.png")', source)

    def test_theme_editor_source_uses_resource_path(self):
        source = (REPO_ROOT / "theme-editor.py").read_text(encoding="utf-8")
        self.assertIn("resource_path(", source)


if __name__ == "__main__":
    unittest.main()
