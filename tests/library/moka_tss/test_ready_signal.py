# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library
# for USB-C displays
# Mascota fork - tests for ready-signal contract

"""Unit tests for MOKA TSS ready signal and format_ready_line helper."""

import io
import unittest
from unittest.mock import MagicMock, patch

from library.moka_tss.app import MokaApp, format_ready_line


class TestFormatReadyLine(unittest.TestCase):
    """Tests for format_ready_line pure helper function."""

    def test_format_ready_line_valid_ports(self):
        """format_ready_line returns ready line for valid ports."""
        self.assertEqual(format_ready_line(8765), "MOKA_READY port=8765")
        self.assertEqual(format_ready_line(1), "MOKA_READY port=1")
        self.assertEqual(format_ready_line(65535), "MOKA_READY port=65535")
        self.assertEqual(format_ready_line(8080), "MOKA_READY port=8080")

    def test_format_ready_line_invalid_type(self):
        """format_ready_line raises ValueError for non-integer types."""
        invalid_types = [None, "8765", 8765.0, True, False, [], {}, (8765,)]
        for val in invalid_types:
            with self.subTest(val=val):
                with self.assertRaises(ValueError):
                    format_ready_line(val)

    def test_format_ready_line_out_of_range(self):
        """format_ready_line raises ValueError for ports outside 1-65535."""
        invalid_ports = [0, -1, -8080, 65536, 100000]
        for port in invalid_ports:
            with self.subTest(port=port):
                with self.assertRaises(ValueError):
                    format_ready_line(port)


class TestMokaAppReadySignal(unittest.TestCase):
    """Tests for MokaApp.run() ready signal emission."""

    def _create_app(self) -> MokaApp:
        """Create a lightweight MokaApp instance with mocked components."""
        return MokaApp(
            serial_port=None,
            screen=None,
            read_sensors=MagicMock(return_value={}),
            agenthub_client=MagicMock(),
            codexbar_client=MagicMock(),
            rule_engine=MagicMock(),
            sprites=None,
            renderer=MagicMock(),
            web_server=None,
            tray_enabled=False,
            simulate=False,
            instance_lock=MagicMock(),
        )

    def test_run_emits_ready_line_when_port_available(self):
        """run() prints ready line to stdout when server starts."""
        app = self._create_app()
        app._init_hardware = MagicMock()
        app.start_config_server = MagicMock(return_value=8765)
        app._setup_tray = MagicMock()
        app._run_loop = MagicMock()
        app.stop = MagicMock()

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            app.run()

        output = mock_stdout.getvalue()
        self.assertIn("MOKA_READY port=8765\n", output)
        app._init_hardware.assert_called_once()
        app.start_config_server.assert_called_once()
        app._setup_tray.assert_called_once()
        app._run_loop.assert_called_once()
        app.stop.assert_called_once()

    def test_run_does_not_emit_ready_line_when_port_is_none(self):
        """run() does not emit ready signal when port is None."""
        app = self._create_app()
        app._init_hardware = MagicMock()
        app.start_config_server = MagicMock(return_value=None)
        app._setup_tray = MagicMock()
        app._run_loop = MagicMock()
        app.stop = MagicMock()

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            app.run()

        output = mock_stdout.getvalue()
        self.assertNotIn("MOKA_READY", output)
        app.start_config_server.assert_called_once()
        app.stop.assert_called_once()
