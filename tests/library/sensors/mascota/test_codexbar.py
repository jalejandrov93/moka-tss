# SPDX-License-Identifier: GPL-3.0-or-later
#
# Tests for the codexbar CustomDataSource adapter.
# No network access, no real token: all HTTP calls are mocked at the
# `requests.get` boundary via _FakeResponse / _install_fake_get.

import json
import math
import unittest
from unittest import mock

import requests

from library.sensors.mascota import codexbar


def _sample_snapshot():
    return {
        "schemaVersion": 1,
        "generatedAt": "2026-09-19T22:20:56Z",
        "staleAfterSeconds": 180,
        "host": {"codexBarVersion": "0.60.3", "refreshIntervalSeconds": 60},
        "providers": [
            {
                "id": "claude",
                "name": "Claude",
                "enabled": True,
                "source": "oauth",
                "error": None,
                "status": None,
                "updatedAt": "2026-09-19T22:20:56Z",
                "windows": [
                    {
                        "kind": "session",
                        "label": "Session",
                        "usedPercent": 2,
                        "remainingPercent": 98,
                        "resetAt": "2026-09-20T03:00:00Z",
                    }
                ],
                "display": {"accentColor": "#CC7C5E", "sortKey": 0, "priority": "normal"},
                "cost": {"last30DaysUSD": 37.41, "todayUSD": None},
                "credits": None,
            }
        ],
    }


class _FakeResponse:
    """Mimics the subset of requests.Response used by the client."""

    def __init__(self, status_code=200, payload=None, raw_text=None):
        self.status_code = status_code
        self._payload = payload
        self._raw_text = raw_text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if self._raw_text is not None:
            return json.loads(self._raw_text)
        return self._payload


def _install_fake_get(test_case, side_effect):
    """Patch requests.get inside the codexbar module. side_effect: callable or
    list of return values / exceptions consumed in order by mock's side_effect."""
    patcher = mock.patch("library.sensors.mascota.codexbar.requests.get", side_effect=side_effect)
    fake_get = patcher.start()
    test_case.addCleanup(patcher.stop)
    return fake_get


def _no_token(test_case):
    patcher = mock.patch(
        "library.sensors.mascota.codexbar._resolve_token", return_value="fake-test-token"
    )
    patcher.start()
    test_case.addCleanup(patcher.stop)


class CodexBarClientHappyPathTests(unittest.TestCase):
    def setUp(self):
        _no_token(self)

    def test_happy_path_returns_snapshot_available_and_fresh(self):
        _install_fake_get(self, [_FakeResponse(200, payload=_sample_snapshot())])
        client = codexbar.CodexBarClient()

        snapshot, is_stale, is_available = client.get_snapshot()

        self.assertIsNotNone(snapshot)
        self.assertFalse(is_stale)
        self.assertTrue(is_available)
        self.assertEqual(snapshot["providers"][0]["id"], "claude")

    def test_window_source_as_numeric_and_as_string_on_happy_path(self):
        _install_fake_get(self, [_FakeResponse(200, payload=_sample_snapshot())])
        client = codexbar.CodexBarClient()
        source = codexbar.CodexBarWindowSource("claude", "session", client=client)

        self.assertEqual(source.as_numeric(), 2.0)
        self.assertEqual(source.as_string(), "2%")

    def test_http_401_with_no_prior_success_reports_unavailable(self):
        _install_fake_get(self, [_FakeResponse(401)])
        client = codexbar.CodexBarClient()
        source = codexbar.CodexBarWindowSource("claude", "session", client=client)

        self.assertTrue(math.isnan(source.as_numeric()))
        self.assertEqual(source.as_string(), "N/D (unavailable)")

    def test_connection_timeout_with_no_prior_success_reports_unavailable(self):
        _install_fake_get(self, requests.exceptions.Timeout("timed out"))
        client = codexbar.CodexBarClient()

        snapshot, is_stale, is_available = client.get_snapshot()

        self.assertIsNone(snapshot)
        self.assertFalse(is_stale)
        self.assertFalse(is_available)

    def test_malformed_json_with_no_prior_success_reports_unavailable(self):
        _install_fake_get(self, [_FakeResponse(200, raw_text="{not valid json")])
        client = codexbar.CodexBarClient()

        snapshot, _is_stale, is_available = client.get_snapshot()

        self.assertIsNone(snapshot)
        self.assertFalse(is_available)

    def test_empty_json_snapshot_has_no_provider_data(self):
        _install_fake_get(self, [_FakeResponse(200, payload={})])
        client = codexbar.CodexBarClient()
        source = codexbar.CodexBarWindowSource("claude", "session", client=client)

        self.assertTrue(math.isnan(source.as_numeric()))
        self.assertEqual(source.as_string(), "N/D")

    def test_provider_with_error_has_no_usable_window(self):
        snapshot = _sample_snapshot()
        snapshot["providers"][0]["error"] = "rate_limited"
        _install_fake_get(self, [_FakeResponse(200, payload=snapshot)])
        client = codexbar.CodexBarClient()
        source = codexbar.CodexBarWindowSource("claude", "session", client=client)

        self.assertTrue(math.isnan(source.as_numeric()))
        self.assertEqual(source.as_string(), "N/D")

    def test_provider_with_no_windows(self):
        snapshot = _sample_snapshot()
        snapshot["providers"][0]["windows"] = []
        _install_fake_get(self, [_FakeResponse(200, payload=snapshot)])
        client = codexbar.CodexBarClient()
        source = codexbar.CodexBarWindowSource("claude", "session", client=client)

        self.assertTrue(math.isnan(source.as_numeric()))
        self.assertEqual(source.as_string(), "N/D")

    def test_cache_hit_inside_ttl_reuses_snapshot(self):
        fake_get = _install_fake_get(self, [_FakeResponse(200, payload=_sample_snapshot())])
        client = codexbar.CodexBarClient()

        client.get_snapshot()
        client.get_snapshot()

        self.assertEqual(fake_get.call_count, 1)

    def test_stale_fallback_after_failure_serves_last_good_marked_stale(self):
        _install_fake_get(
            self, [_FakeResponse(200, payload=_sample_snapshot()), requests.exceptions.Timeout()]
        )
        client = codexbar.CodexBarClient()
        with mock.patch("library.sensors.mascota.codexbar.time.monotonic", side_effect=[0, 20]):
            client.get_snapshot()
            snapshot, is_stale, is_available = client.get_snapshot()

        self.assertIsNotNone(snapshot)
        self.assertTrue(is_stale)
        self.assertTrue(is_available)

    def test_unavailable_after_15_minutes_with_no_success(self):
        _install_fake_get(
            self, [_FakeResponse(200, payload=_sample_snapshot()), requests.exceptions.Timeout()]
        )
        client = codexbar.CodexBarClient()
        with mock.patch("library.sensors.mascota.codexbar.time.monotonic", side_effect=[0, 901]):
            client.get_snapshot()
            snapshot, is_stale, is_available = client.get_snapshot()

        self.assertIsNotNone(snapshot)
        self.assertTrue(is_stale)
        self.assertFalse(is_available)

    def test_last_values_rolls_history_with_nan_padding(self):
        _install_fake_get(self, [_FakeResponse(200, payload=_sample_snapshot())])
        client = codexbar.CodexBarClient()
        source = codexbar.CodexBarWindowSource("claude", "session", client=client)

        initial = source.last_values()
        self.assertEqual(len(initial), 10)
        self.assertTrue(all(math.isnan(v) for v in initial))

        for _ in range(3):
            source.as_numeric()

        values = source.last_values()
        self.assertEqual(len(values), 10)
        self.assertEqual(values[-3:], [2.0, 2.0, 2.0])
        self.assertTrue(all(math.isnan(v) for v in values[:-3]))

    def test_build_sources_lists_available_provider_windows(self):
        _install_fake_get(self, [_FakeResponse(200, payload=_sample_snapshot())])
        client = codexbar.CodexBarClient()

        sources = codexbar.build_sources(client=client)

        self.assertIn("claude:session", sources)
        self.assertIsInstance(sources["claude:session"], codexbar.CodexBarWindowSource)
        self.assertEqual(sources["claude:session"].as_numeric(), 2.0)

    def test_build_sources_empty_when_snapshot_unavailable(self):
        _install_fake_get(self, requests.exceptions.Timeout("timed out"))
        client = codexbar.CodexBarClient()

        self.assertEqual(codexbar.build_sources(client=client), {})


if __name__ == "__main__":
    unittest.main()
