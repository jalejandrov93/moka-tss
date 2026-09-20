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

from library.moka_tss.app import (
    InstanceLock,
    MascotaApp,
    MokaApp,
    SingleInstanceError,
)
from library.sensors.moka_tss.agenthub import FetchResult


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
        self.lock_path = Path(self.temp_dir.name) / "moka_tss.lock"

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
        from library.moka_tss.rules import EvaluationResult
        mock_rule_engine = MagicMock()
        mock_rule_engine.evaluate_detailed.return_value = EvaluationResult(
            mood="alarmada",
            winning_rule_id="r1",
            fired_rule_ids=["r1"]
        )
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
        self.assertEqual(app.last_mood, "alarmada")
        self.assertEqual(app.last_rule, {"winning_rule_id": "r1", "fired": ["r1"]})

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
        # Ensure no thread from MOKA is left running
        moka_threads = [t for t in new_threads if "moka" in t.name.lower()]
        self.assertEqual(moka_threads, [])

    def test_simulate_mode_saves_image(self):
        sim_png = Path(self.temp_dir.name) / "screencap.png"
        app = MokaApp(
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
        from moka import parse_args
        args = parse_args([])
        self.assertEqual(args.tick, 2.0)
        self.assertEqual(args.brightness, 85)
        self.assertEqual(args.port, "COM3")
        self.assertFalse(args.no_tray)
        self.assertFalse(args.simulate)

    def test_parse_args_custom(self):
        from moka import parse_args
        args = parse_args(["--tick", "1.5", "--brightness", "70", "--port", "/dev/ttyUSB0", "--no-tray", "--simulate"])
        self.assertEqual(args.tick, 1.5)
        self.assertEqual(args.brightness, 70)
        self.assertEqual(args.port, "/dev/ttyUSB0")
        self.assertTrue(args.no_tray)
        self.assertTrue(args.simulate)


if __name__ == "__main__":
    unittest.main()


class RendererThemeIntegrationTests(unittest.TestCase):
    """The app and the compositor were built in parallel. Each suite passed on
    its own while the pair was broken, because nothing exercised the seam."""

    def test_default_renderer_works_with_a_real_theme(self):
        from library.moka_tss import app as app_module
        from library.moka_tss.theme import load_theme

        system = {"cpu": 40.0, "ram": 50.0, "gpu": None}
        snapshot = {"providers": [{"id": "claude", "name": "Claude",
                                   "windows": [{"kind": "session", "label": "Session",
                                                "usedPercent": 95}],
                                   "display": {"accentColor": "#CC7C5E"}}]}
        for name in ("horizontal", "vertical"):
            with self.subTest(theme=name):
                frame = app_module.default_renderer(
                    snapshot, None, system,
                    mood="alarmada", sprites=None, tick=0,
                    theme=load_theme(name),
                )
                self.assertIsNotNone(frame)


class ConfigServerAtStartupTests(unittest.TestCase):
    """The panel used to exist only after someone found the tray icon and
    clicked it, so its URL was unbookmarkable and died on every restart."""

    def test_run_starts_the_config_server(self):
        from library.moka_tss import app as app_module

        started = []

        class FakeServer:
            port = 9999
            _httpd = None

            def start(self):
                self._httpd = object()
                started.append(True)

            def stop(self):
                self._httpd = None

        app = app_module.MokaApp(simulate=True, tray_enabled=False,
                                 web_server=FakeServer())
        port = app.start_config_server()
        self.assertEqual(port, 9999)
        self.assertEqual(started, [True])

    def test_start_config_server_is_idempotent(self):
        from library.moka_tss import app as app_module

        calls = []

        class FakeServer:
            port = 9999

            def __init__(self):
                self._httpd = object()

            def start(self):
                calls.append(True)

            def stop(self):
                pass

        app = app_module.MokaApp(simulate=True, tray_enabled=False,
                                 web_server=FakeServer())
        app.start_config_server()
        app.start_config_server()
        self.assertEqual(calls, [], "an already-serving panel must not be restarted")


class ApplySavedSettingsTests(unittest.TestCase):
    """Tests for dynamic application of settings saved via the config panel."""

    def test_apply_saved_settings_with_mock_screen(self):
        mock_screen = MagicMock()
        app = MokaApp(
            serial_port=None,
            screen=mock_screen,
            tray_enabled=False,
            simulate=True,
        )
        app._apply_saved_settings({"brightness": 70})
        mock_screen.set_brightness.assert_called_once_with(70)
        self.assertEqual(app.brightness, 70)

    def test_apply_saved_settings_without_screen_does_not_raise(self):
        app = MokaApp(
            serial_port=None,
            screen=None,
            tray_enabled=False,
            simulate=True,
        )
        app._apply_saved_settings({"brightness": 50})
        self.assertEqual(app.brightness, 50)

    def test_apply_saved_settings_screen_exception_is_handled(self):
        mock_screen = MagicMock()
        mock_screen.set_brightness.side_effect = RuntimeError("I2C error")
        app = MokaApp(
            serial_port=None,
            screen=mock_screen,
            tray_enabled=False,
            simulate=True,
        )
        app._apply_saved_settings({"brightness": 30})
        mock_screen.set_brightness.assert_called_once_with(30)
        self.assertEqual(app.brightness, 30)

    def test_apply_saved_settings_ignores_invalid_brightness(self):
        mock_screen = MagicMock()
        app = MokaApp(
            serial_port=None,
            screen=mock_screen,
            tray_enabled=False,
            simulate=True,
        )
        app._apply_saved_settings({"brightness": -5})
        app._apply_saved_settings({"brightness": 105})
        app._apply_saved_settings({"brightness": "invalid"})
        app._apply_saved_settings({"brightness": True})
        mock_screen.set_brightness.assert_not_called()

    def test_start_config_server_wires_apply_saved_settings(self):
        from unittest.mock import patch
        app = MokaApp(simulate=True, tray_enabled=False)
        with patch("library.moka_tss.webconfig.WebConfigServer") as mock_cls:
            mock_inst = MagicMock()
            mock_inst.port = 8765
            mock_cls.return_value = mock_inst
            port = app.start_config_server()
            self.assertEqual(port, 8765)
            mock_cls.assert_called_once_with(
                status_provider=app._get_status,
                on_config_saved=app._apply_saved_settings,
            )
