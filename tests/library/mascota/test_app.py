# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays
# Mascota fork - tests for the application entry point and refresh loop

"""Unit tests for library.mascota.app."""

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from library.mascota.app import (
    InstanceLock,
    MascotaApp,
    SingleInstanceError,
)
from library.sensors.mascota.agenthub import FetchResult


class FakeSerial:
    """Duck-typed serial port recording writes."""

    def __init__(self):
        self.buffer = bytearray()
        self.closed = False

    def write(self, data: bytes) -> int:
        self.buffer.extend(data)
        return len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class TestInstanceLock(unittest.TestCase):
    """Verify single instance lock behaviour across processes/handles."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.lock_path = Path(self.temp_dir.name) / "mascota.lock"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_single_instance_lock_refuses_second_start(self):
        lock1 = InstanceLock(self.lock_path)
        lock1.acquire()
        try:
            lock2 = InstanceLock(self.lock_path)
            with self.assertRaises(SingleInstanceError):
                lock2.acquire()
        finally:
            lock1.release()

    def test_lock_release_allows_reacquire(self):
        lock1 = InstanceLock(self.lock_path)
        lock1.acquire()
        lock1.release()

        lock2 = InstanceLock(self.lock_path)
        lock2.acquire()
        lock2.release()


class TestMascotaApp(unittest.TestCase):
    """Test suite for MascotaApp lifecycle, cadence, resilience, and rendering."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.lock_path = Path(self.temp_dir.name) / "test.lock"
        self.fake_serial = FakeSerial()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_loop_calls_sources_at_own_cadence(self):
        # Time progression: 0.0, 2.0, 4.0, 6.0 (4 ticks of 2s)
        current_time = [0.0]

        def fake_clock():
            return current_time[0]

        mock_sensors = MagicMock(return_value={"cpu": 10.0, "ram": 20.0, "gpu": None, "cpu_temp": None})
        mock_agenthub = MagicMock()
        mock_agenthub.get_state.return_value = FetchResult(value={"jobs": []}, stale=False, available=True)
        mock_codexbar = MagicMock()
        mock_codexbar.get_snapshot.return_value = ({"providers": []}, False, True)

        app = MascotaApp(
            serial_port=self.fake_serial,
            read_sensors=mock_sensors,
            agenthub_client=mock_agenthub,
            codexbar_client=mock_codexbar,
            tick_interval=2.0,
            agenthub_interval=5.0,
            codexbar_interval=60.0,
            clock=fake_clock,
            tray_enabled=False,
            simulate=True,
            simulate_output_path=Path(self.temp_dir.name) / "sim.png",
            instance_lock=InstanceLock(self.lock_path),
        )

        # Tick 1 at t=0: all sources polled once
        app.step()
        self.assertEqual(mock_sensors.call_count, 1)
        self.assertEqual(mock_agenthub.get_state.call_count, 1)
        self.assertEqual(mock_codexbar.get_snapshot.call_count, 1)

        # Tick 2 at t=2.0: only local sensors (agenthub next at t=5.0, codexbar next at t=60.0)
        current_time[0] = 2.0
        app.step()
        self.assertEqual(mock_sensors.call_count, 2)
        self.assertEqual(mock_agenthub.get_state.call_count, 1)
        self.assertEqual(mock_codexbar.get_snapshot.call_count, 1)

        # Tick 3 at t=4.0: only local sensors
        current_time[0] = 4.0
        app.step()
        self.assertEqual(mock_sensors.call_count, 3)
        self.assertEqual(mock_agenthub.get_state.call_count, 1)
        self.assertEqual(mock_codexbar.get_snapshot.call_count, 1)

        # Tick 4 at t=6.0: local sensors and agenthub (6.0 - 0.0 >= 5.0), but not codexbar
        current_time[0] = 6.0
        app.step()
        self.assertEqual(mock_sensors.call_count, 4)
        self.assertEqual(mock_agenthub.get_state.call_count, 2)
        self.assertEqual(mock_codexbar.get_snapshot.call_count, 1)

    def test_failing_source_keeps_last_good_value_and_does_not_stop_loop(self):
        mock_codexbar = MagicMock()
        mock_codexbar.get_snapshot.side_effect = [
            ({"providers": [{"id": "claude", "windows": [{"usedPercent": 50}]}]}, False, True),
            (None, False, False),  # down!
        ]
        captured_snapshots = []

        def fake_renderer(snapshot, state, system, **kwargs):
            captured_snapshots.append(snapshot)
            from PIL import Image
            return Image.new("RGB", (480, 320))

        app = MascotaApp(
            serial_port=self.fake_serial,
            codexbar_client=mock_codexbar,
            renderer=fake_renderer,
            codexbar_interval=1.0,
            tick_interval=1.0,
            clock=lambda: 0.0,
            tray_enabled=False,
            simulate=True,
            simulate_output_path=Path(self.temp_dir.name) / "sim.png",
            instance_lock=InstanceLock(self.lock_path),
        )

        app.step()
        self.assertEqual(len(captured_snapshots), 1)
        self.assertEqual(captured_snapshots[0]["providers"][0]["id"], "claude")

        # Step 2: codexbar failed, but previous snapshot is preserved
        app.step()
        self.assertEqual(len(captured_snapshots), 2)
        self.assertIsNotNone(captured_snapshots[1])
        self.assertEqual(captured_snapshots[1]["providers"][0]["id"], "claude")

    def test_source_that_raises_does_not_escape_loop(self):
        mock_sensors = MagicMock(side_effect=RuntimeError("Hardware sensor error"))
        mock_agenthub = MagicMock()
        mock_agenthub.get_state.side_effect = ConnectionError("AgentHub down")
        mock_codexbar = MagicMock()
        mock_codexbar.get_snapshot.side_effect = TimeoutError("Codexbar timeout")

        rendered_frames = []

        def fake_renderer(snapshot, state, system, **kwargs):
            rendered_frames.append(True)
            from PIL import Image
            return Image.new("RGB", (480, 320))

        app = MascotaApp(
            serial_port=self.fake_serial,
            read_sensors=mock_sensors,
            agenthub_client=mock_agenthub,
            codexbar_client=mock_codexbar,
            renderer=fake_renderer,
            tray_enabled=False,
            simulate=True,
            simulate_output_path=Path(self.temp_dir.name) / "sim.png",
            instance_lock=InstanceLock(self.lock_path),
        )

        # Must not raise
        app.step()
        self.assertEqual(len(rendered_frames), 1)

    def test_mood_from_rule_engine_reaches_renderer(self):
        mock_rule_engine = MagicMock()
        mock_rule_engine.evaluate.return_value = "alarmada"
        captured_moods = []

        def fake_renderer(snapshot, state, system, *, mood=None, **kwargs):
            captured_moods.append(mood)
            from PIL import Image
            return Image.new("RGB", (480, 320))

        app = MascotaApp(
            serial_port=self.fake_serial,
            rule_engine=mock_rule_engine,
            renderer=fake_renderer,
            tray_enabled=False,
            simulate=True,
            simulate_output_path=Path(self.temp_dir.name) / "sim.png",
            instance_lock=InstanceLock(self.lock_path),
        )

        app.step()
        self.assertEqual(captured_moods, ["alarmada"])

    def test_shutdown_stops_loop_server_and_port_leaves_no_threads(self):
        fake_server = MagicMock()
        fake_serial = FakeSerial()

        app = MascotaApp(
            serial_port=fake_serial,
            web_server=fake_server,
            tray_enabled=False,
            simulate=False,
            instance_lock=InstanceLock(self.lock_path),
        )

        threads_before = set(threading.enumerate())
        app.start_background_loop()
        time.sleep(0.1)

        # Stop app cleanly
        app.stop()

        # Serial port closed
        self.assertTrue(fake_serial.closed)
        # Web server stopped
        self.assertTrue(fake_server.stop.called)

        # Threads joined
        threads_after = set(threading.enumerate())
        new_threads = threads_after - threads_before
        # Ensure no thread from Mascota is left running
        mascota_threads = [t for t in new_threads if "mascota" in t.name.lower()]
        self.assertEqual(mascota_threads, [])

    def test_simulate_mode_saves_image(self):
        sim_png = Path(self.temp_dir.name) / "screencap.png"
        app = MascotaApp(
            serial_port=None,
            tray_enabled=False,
            simulate=True,
            simulate_output_path=sim_png,
            instance_lock=InstanceLock(self.lock_path),
        )

        app.step()
        self.assertTrue(sim_png.exists())
        self.assertGreater(sim_png.stat().st_size, 0)

    def test_parse_args_defaults(self):
        from mascota import parse_args
        args = parse_args([])
        self.assertEqual(args.tick, 2.0)
        self.assertEqual(args.brightness, 85)
        self.assertEqual(args.port, "COM3")
        self.assertFalse(args.no_tray)
        self.assertFalse(args.simulate)

    def test_parse_args_custom(self):
        from mascota import parse_args
        args = parse_args(["--tick", "1.5", "--brightness", "70", "--port", "/dev/ttyUSB0", "--no-tray", "--simulate"])
        self.assertEqual(args.tick, 1.5)
        self.assertEqual(args.brightness, 70)
        self.assertEqual(args.port, "/dev/ttyUSB0")
        self.assertTrue(args.no_tray)
        self.assertTrue(args.simulate)


if __name__ == "__main__":
    unittest.main()
