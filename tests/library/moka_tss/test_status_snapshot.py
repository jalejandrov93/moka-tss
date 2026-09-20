# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library
# for USB-C displays
# Mascota fork - tests for MokaApp.status_snapshot() contract

"""Unit tests for MokaApp.status_snapshot state contract."""

import json
import unittest
from unittest.mock import MagicMock

from library.moka_tss.app import MokaApp


class TestStatusSnapshot(unittest.TestCase):
    """Test suite for MokaApp.status_snapshot contract."""

    def _create_app(self) -> MokaApp:
        """Create a lightweight MokaApp instance with no hardware bindings."""
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

    def test_status_snapshot_exact_keys(self):
        """status_snapshot returns exactly the contract keys."""
        app = self._create_app()
        snapshot = app.status_snapshot()
        expected_keys = {
            "tick",
            "running",
            "agenthub_available",
            "codexbar_available",
            "has_system",
            "has_snapshot",
            "has_state",
            "mood",
            "system",
            "screen",
        }
        self.assertEqual(set(snapshot.keys()), expected_keys)
        self.assertEqual(len(snapshot), 10)

    def test_status_snapshot_json_serializable_and_types(self):
        """status_snapshot is JSON-serializable and maintains types."""
        app = self._create_app()
        snapshot = app.status_snapshot()

        # Serialization round-trip with default None mood and empty system
        serialized = json.dumps(snapshot)
        deserialized = json.loads(serialized)
        self.assertEqual(deserialized, snapshot)

        # Explicit Python type guarantees
        self.assertIs(type(snapshot["tick"]), int)
        self.assertIs(type(snapshot["running"]), bool)
        self.assertIs(type(snapshot["agenthub_available"]), bool)
        self.assertIs(type(snapshot["codexbar_available"]), bool)
        self.assertIs(type(snapshot["has_system"]), bool)
        self.assertIs(type(snapshot["has_snapshot"]), bool)
        self.assertIs(type(snapshot["has_state"]), bool)
        self.assertIsNone(snapshot["mood"])

        # System telemetry types and defaults
        self.assertIs(type(snapshot["system"]), dict)
        self.assertEqual(set(snapshot["system"].keys()), {"cpu", "ram", "gpu"})
        self.assertIsNone(snapshot["system"]["cpu"])
        self.assertIsNone(snapshot["system"]["ram"])
        self.assertIsNone(snapshot["system"]["gpu"])

        # Screen status types and defaults
        self.assertIs(type(snapshot["screen"]), dict)
        self.assertEqual(set(snapshot["screen"].keys()), {"present", "simulate", "brightness"})
        self.assertIs(type(snapshot["screen"]["present"]), bool)
        self.assertIs(type(snapshot["screen"]["simulate"]), bool)
        self.assertIs(type(snapshot["screen"]["brightness"]), int)
        self.assertFalse(snapshot["screen"]["present"])
        self.assertFalse(snapshot["screen"]["simulate"])

        # When mood, system and screen are populated, serialization round-trip succeeds
        app.last_mood = "alerta"
        app.last_system = {"cpu": 15.5, "ram": 55.0, "gpu": {"util": 22.0}}
        app.screen = MagicMock()
        app.simulate = True
        app.brightness = 90
        populated = app.status_snapshot()
        self.assertEqual(populated["mood"], "alerta")
        self.assertIs(type(populated["mood"]), str)
        self.assertEqual(populated["system"], {"cpu": 15.5, "ram": 55.0, "gpu": 22.0})
        self.assertEqual(populated["screen"], {"present": True, "simulate": True, "brightness": 90})
        self.assertEqual(json.loads(json.dumps(populated)), populated)

        # NaN values in system sensors are converted to None for valid JSON
        app.last_system = {"cpu": float("nan"), "ram": 42.0, "gpu": float("nan")}
        nan_snapshot = app.status_snapshot()
        self.assertIsNone(nan_snapshot["system"]["cpu"])
        self.assertEqual(nan_snapshot["system"]["ram"], 42.0)
        self.assertIsNone(nan_snapshot["system"]["gpu"])
        self.assertEqual(json.loads(json.dumps(nan_snapshot)), nan_snapshot)

    def test_status_snapshot_reflects_data_flags(self):
        """status_snapshot reflects presence of system, snapshot, and state."""
        app = self._create_app()

        # Initially all data flags are False
        initial = app.status_snapshot()
        self.assertFalse(initial["has_system"])
        self.assertFalse(initial["has_snapshot"])
        self.assertFalse(initial["has_state"])

        # Populate last_system
        app.last_system = {"cpu": 15.0}
        self.assertTrue(app.status_snapshot()["has_system"])

        # Populate last_snapshot
        app.last_snapshot = {"providers": []}
        self.assertTrue(app.status_snapshot()["has_snapshot"])

        # Populate last_state
        app.last_state = {"jobs": []}
        self.assertTrue(app.status_snapshot()["has_state"])

        # Clearing flags reverts to False
        app.last_system = None
        app.last_snapshot = None
        app.last_state = None
        cleared = app.status_snapshot()
        self.assertFalse(cleared["has_system"])
        self.assertFalse(cleared["has_snapshot"])
        self.assertFalse(cleared["has_state"])

    def test_status_snapshot_running_flag_lifecycle_without_hardware(self):
        """running flag tracks internal lifecycle changes without hardware."""
        app = self._create_app()
        self.assertFalse(app.status_snapshot()["running"])

        # Simulate start by setting internal flag
        app._running = True
        self.assertTrue(app.status_snapshot()["running"])

        # app.stop() clears internal flag and cleans up safely
        app.stop()
        self.assertFalse(app.status_snapshot()["running"])

    def test_status_snapshot_reflects_tick_and_availability(self):
        """status_snapshot reflects tick_count and sensor availability."""
        app = self._create_app()
        app.tick_count = 10
        app.agenthub_available = True
        app.codexbar_available = True

        snapshot = app.status_snapshot()
        self.assertEqual(snapshot["tick"], 10)
        self.assertTrue(snapshot["agenthub_available"])
        self.assertTrue(snapshot["codexbar_available"])

    def test_get_status_matches_status_snapshot(self):
        """_get_status returns the 10 keys matching status_snapshot."""
        app = self._create_app()
        self.assertEqual(app._get_status(), app.status_snapshot())
        self.assertEqual(len(app._get_status()), 10)

    def test_step_tracks_mood_with_mocks(self):
        """step() tracks evaluated mood in self.last_mood and snapshot."""
        app = self._create_app()
        self.assertIsNone(app.last_mood)
        self.assertIsNone(app.status_snapshot()["mood"])

        app.rule_engine.evaluate.return_value = "alerta"
        app.step()
        self.assertEqual(app.last_mood, "alerta")
        snapshot = app.status_snapshot()
        self.assertEqual(snapshot["mood"], "alerta")
        self.assertEqual(json.loads(json.dumps(snapshot)), snapshot)

        app.rule_engine.evaluate.return_value = "furia"
        app.step()
        self.assertEqual(app.last_mood, "furia")
        self.assertEqual(app.status_snapshot()["mood"], "furia")


if __name__ == "__main__":
    unittest.main()
