# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays
# Mascota fork - tests for local system sensors

"""Unit tests for library.mascota.sensors_local."""

import subprocess
import unittest
from unittest.mock import MagicMock, patch

from library.mascota.sensors_local import (
    get_cpu_percent,
    get_cpu_temp,
    get_gpu_info,
    get_ram_percent,
    read_system_sensors,
)


class TestSensorsLocal(unittest.TestCase):
    """Test suite for local system metrics collection."""

    @patch("psutil.cpu_percent")
    def test_cpu_percent_success(self, mock_cpu):
        mock_cpu.return_value = 23.5
        val = get_cpu_percent()
        self.assertEqual(val, 23.5)
        mock_cpu.assert_called_once_with(interval=None)

    @patch("psutil.cpu_percent", side_effect=Exception("psutil error"))
    def test_cpu_percent_failure_returns_none(self, mock_cpu):
        val = get_cpu_percent()
        self.assertIsNone(val)

    @patch("psutil.virtual_memory")
    def test_ram_percent_success(self, mock_vm):
        mock_vm.return_value = MagicMock(percent=56.2)
        val = get_ram_percent()
        self.assertEqual(val, 56.2)

    @patch("psutil.virtual_memory", side_effect=Exception("psutil error"))
    def test_ram_percent_failure_returns_none(self, mock_vm):
        val = get_ram_percent()
        self.assertIsNone(val)

    def test_gpu_info_success(self):
        fake_runner = MagicMock()
        fake_runner.return_value = MagicMock(
            returncode=0,
            stdout="15, 55, 2048, 8192\n",
        )
        info = get_gpu_info(runner=fake_runner)
        self.assertIsNotNone(info)
        self.assertEqual(info["util"], 15.0)
        self.assertEqual(info["temp"], 55.0)
        self.assertEqual(info["vram_used"], 2048.0)
        self.assertEqual(info["vram_total"], 8192.0)
        self.assertAlmostEqual(info["vram"], 25.0, places=2)

    def test_gpu_info_missing_executable_returns_none(self):
        fake_runner = MagicMock(side_effect=FileNotFoundError("nvidia-smi not found"))
        info = get_gpu_info(runner=fake_runner)
        self.assertIsNone(info)

    def test_gpu_info_nonzero_exit_returns_none(self):
        fake_runner = MagicMock()
        fake_runner.return_value = MagicMock(
            returncode=1,
            stdout="",
        )
        info = get_gpu_info(runner=fake_runner)
        self.assertIsNone(info)

    def test_gpu_info_malformed_output_returns_none(self):
        fake_runner = MagicMock()
        fake_runner.return_value = MagicMock(
            returncode=0,
            stdout="invalid,output\n",
        )
        info = get_gpu_info(runner=fake_runner)
        self.assertIsNone(info)

    def test_gpu_info_passes_create_no_window_flag(self):
        fake_runner = MagicMock()
        fake_runner.return_value = MagicMock(returncode=0, stdout="10, 45, 1000, 4000\n")
        get_gpu_info(runner=fake_runner)
        self.assertTrue(fake_runner.called)
        _, kwargs = fake_runner.call_args
        expected_flag = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.assertEqual(kwargs.get("creationflags"), expected_flag)

    @patch("library.mascota.sensors_local.get_cpu_percent", return_value=12.0)
    @patch("library.mascota.sensors_local.get_ram_percent", return_value=34.0)
    @patch(
        "library.mascota.sensors_local.get_gpu_info",
        return_value={"util": 10.0, "temp": 50.0, "vram": 20.0, "vram_used": 1000.0, "vram_total": 5000.0},
    )
    @patch("library.mascota.sensors_local.get_cpu_temp", return_value=48.0)
    def test_read_system_sensors(self, mock_temp, mock_gpu, mock_ram, mock_cpu):
        sys_data = read_system_sensors()
        self.assertEqual(sys_data["cpu"], 12.0)
        self.assertEqual(sys_data["ram"], 34.0)
        self.assertEqual(sys_data["gpu"]["util"], 10.0)
        self.assertEqual(sys_data["cpu_temp"], 48.0)

    def test_get_cpu_temp_returns_float_or_none(self):
        val = get_cpu_temp()
        self.assertTrue(val is None or isinstance(val, float))


if __name__ == "__main__":
    unittest.main()
