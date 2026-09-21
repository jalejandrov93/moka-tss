# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays
# Mascota fork - tests for the local web configuration panel
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Tests for library.mascota.webconfig, the local loopback config panel.

Every test binds to an ephemeral port (port=0) on 127.0.0.1 and shuts the
server down deterministically in tearDown, so no thread or socket survives
a test run. Config/rules files live under a per-test TemporaryDirectory,
never touching the real res/mascota/ tree.
"""

import http.client
import json
import socket
import socketserver
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from library.moka_tss import webconfig
from library.moka_tss.rules import RulesConfigError

VALID_RULES = {
    "moods": ["calma", "alarmada"],
    "default_mood": "calma",
    "rules": [
        {"id": "cpu_high", "metric": "cpu_percent", "op": ">=", "value": 90, "mood": "alarmada"},
    ],
}

INVALID_RULES = {
    "moods": ["calma", "alarmada"],
    "default_mood": "calma",
    "rules": [
        {"id": "cpu_high", "metric": "cpu_percent", "op": ">=", "value": 90, "mood": "no_existe"},
    ],
}


class _EchoHandler(socketserver.BaseRequestHandler):
    def handle(self):
        pass


class _TCPServer(socketserver.TCPServer):
    allow_reuse_address = True


class WebConfigServerTestCase(unittest.TestCase):
    """Base case: spins up a real WebConfigServer on an ephemeral port."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp_path = Path(self._tmp.name)
        self.config_path = tmp_path / "webconfig.json"
        self.rules_path = tmp_path / "rules.yaml"
        self.webui_dir = tmp_path / "webui"
        self.webui_dir.mkdir()
        (self.webui_dir / "index.html").write_text("<html>ok</html>", encoding="utf-8")
        (self.webui_dir / "style.css").write_text("body{}", encoding="utf-8")
        (self.webui_dir / "app.js").write_text("//ok", encoding="utf-8")

        self.server = webconfig.WebConfigServer(
            config_path=self.config_path,
            rules_path=self.rules_path,
            webui_dir=self.webui_dir,
            port=0,
            status_provider=lambda: {"connected": True, "mood": "calma", "last_refresh": 42.0},
        )
        self.server.start()
        self.addCleanup(self.server.stop)

    def _connection(self):
        return http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=5)

    def _get(self, path, headers=None):
        conn = self._connection()
        try:
            conn.request("GET", path, headers=headers or {})
            response = conn.getresponse()
            body = response.read()
            return response.status, body
        finally:
            conn.close()

    def _post(self, path, payload_bytes, headers=None):
        conn = self._connection()
        try:
            conn.request("POST", path, body=payload_bytes, headers=headers or {})
            response = conn.getresponse()
            body = response.read()
            return response.status, body
        finally:
            conn.close()

    def _post_json(self, path, data, extra_headers=None):
        headers = {
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{self.server.port}",
        }
        if extra_headers:
            headers.update(extra_headers)
        return self._post(path, json.dumps(data).encode("utf-8"), headers=headers)


class ConfigEndpointTests(WebConfigServerTestCase):
    def test_get_config_returns_defaults_when_no_file_saved(self):
        status, body = self._get("/api/config")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["brightness"], webconfig.DEFAULT_SETTINGS["brightness"])
        self.assertEqual(data["orientation"], webconfig.DEFAULT_SETTINGS["orientation"])

    def test_post_then_get_round_trips_saved_values(self):
        status, body = self._post_json("/api/config", {"brightness": 60, "orientation": "portrait"})
        self.assertEqual(status, 200)

        status, body = self._get("/api/config")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["brightness"], 60)
        self.assertEqual(data["orientation"], "portrait")

    def test_post_config_persists_to_disk(self):
        self._post_json("/api/config", {"brightness": 77})
        self.assertTrue(self.config_path.is_file())
        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["brightness"], 77)

    def test_post_config_rejects_invalid_brightness(self):
        status, body = self._post_json("/api/config", {"brightness": 500})
        self.assertEqual(status, 400)
        self.assertIn("brightness", json.loads(body)["error"])
        # nothing must have been written for an invalid payload
        self.assertFalse(self.config_path.is_file())

    def test_post_config_invokes_on_config_saved_callback(self):
        received = []
        self.server._httpd.on_config_saved = lambda saved: received.append(saved)
        status, _ = self._post_json("/api/config", {"brightness": 72})
        self.assertEqual(status, 200)
        self.assertEqual(len(received), 1)
        self.assertIsInstance(received[0], dict)
        self.assertEqual(received[0]["brightness"], 72)

    def test_post_config_returns_200_even_if_callback_raises(self):
        def faulty_callback(saved):
            raise RuntimeError("Boom!")

        self.server._httpd.on_config_saved = faulty_callback
        status, body = self._post_json("/api/config", {"brightness": 45})
        self.assertEqual(status, 200)
        saved = json.loads(body)
        self.assertEqual(saved["brightness"], 45)


class SecurityTests(WebConfigServerTestCase):
    def test_post_with_wrong_origin_is_rejected(self):
        headers = {
            "Content-Type": "application/json",
            "Origin": "http://evil.example.com",
        }
        status, body = self._post("/api/config", json.dumps({"brightness": 60}).encode("utf-8"), headers=headers)
        self.assertEqual(status, 403)
        self.assertFalse(self.config_path.is_file())

    def test_post_with_wrong_content_type_is_rejected(self):
        headers = {
            "Content-Type": "text/plain",
            "Origin": f"http://127.0.0.1:{self.server.port}",
        }
        status, body = self._post("/api/config", json.dumps({"brightness": 60}).encode("utf-8"), headers=headers)
        self.assertEqual(status, 415)
        self.assertFalse(self.config_path.is_file())

    def test_get_with_wrong_host_header_is_rejected(self):
        status, body = self._get("/api/config", headers={"Host": "evil.example.com"})
        self.assertEqual(status, 403)

    def test_path_traversal_attempt_is_refused(self):
        status, body = self._get("/../../etc/passwd")
        self.assertNotEqual(status, 200)
        self.assertNotIn(b"root:", body)

    def test_unknown_static_path_is_404(self):
        status, body = self._get("/definitely-not-a-file.txt")
        self.assertEqual(status, 404)


class RulesEndpointTests(WebConfigServerTestCase):
    def test_get_rules_returns_saved_yaml_as_json(self):
        webconfig.save_rules(self.rules_path, VALID_RULES)
        status, body = self._get("/api/rules")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["default_mood"], "calma")
        self.assertEqual(data["rules"][0]["id"], "cpu_high")

    def test_post_valid_rules_round_trips(self):
        status, body = self._post_json("/api/rules", VALID_RULES)
        self.assertEqual(status, 200)

        status, body = self._get("/api/rules")
        data = json.loads(body)
        self.assertEqual(data, VALID_RULES)

    def test_post_invalid_rules_is_rejected_and_names_the_rule(self):
        webconfig.save_rules(self.rules_path, VALID_RULES)
        before = self.rules_path.read_text(encoding="utf-8")

        status, body = self._post_json("/api/rules", INVALID_RULES)
        self.assertEqual(status, 400)
        error = json.loads(body)["error"]
        self.assertIn("cpu_high", error)

        after = self.rules_path.read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_post_invalid_rules_never_creates_a_file(self):
        self.assertFalse(self.rules_path.is_file())
        status, body = self._post_json("/api/rules", INVALID_RULES)
        self.assertEqual(status, 400)
        self.assertFalse(self.rules_path.is_file())


class StaticServingTests(WebConfigServerTestCase):
    def test_root_serves_index_html(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"<html>", body)

    def test_style_css_is_served(self):
        status, body = self._get("/style.css")
        self.assertEqual(status, 200)
        self.assertIn(b"body", body)

    def test_app_js_is_served(self):
        status, body = self._get("/app.js")
        self.assertEqual(status, 200)


class StatusEndpointTests(WebConfigServerTestCase):
    def test_get_status_reports_injected_provider(self):
        status, body = self._get("/api/status")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["mood"], "calma")
        self.assertTrue(data["connected"])
        self.assertEqual(data["last_refresh"], 42.0)

    def test_get_status_includes_system_snapshot_and_state_flags(self):
        from unittest.mock import MagicMock
        from library.moka_tss.app import MokaApp

        app = MokaApp(
            serial_port=None,
            screen=None,
            read_sensors=MagicMock(return_value={}),
            agenthub_client=MagicMock(),
            codexbar_client=MagicMock(),
            rule_engine=MagicMock(),
            sprites=None,
            renderer=MagicMock(),
            tray_enabled=False,
            simulate=True,
            instance_lock=MagicMock(),
        )
        self.server._httpd.status_provider = app._get_status

        status, body = self._get("/api/status")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("has_system", data)
        self.assertIn("has_snapshot", data)
        self.assertIn("has_state", data)
        self.assertIn("mood", data)
        self.assertIn("system", data)
        self.assertIn("screen", data)
        self.assertIsInstance(data["has_system"], bool)
        self.assertIsInstance(data["has_snapshot"], bool)
        self.assertIsInstance(data["has_state"], bool)
        self.assertIsNone(data["mood"])
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
            "transmission",
            "rule",
        }
        self.assertEqual(set(data.keys()), expected_keys)
        self.assertEqual(len(data), 12)


class ServicesEndpointTests(WebConfigServerTestCase):
    def _start_tcp_server(self):
        server = _TCPServer(("127.0.0.1", 0), _EchoHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread, port

    def _stop_tcp_server(self, server, thread):
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)

    def _get_closed_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def test_get_services_empty_when_no_services(self):
        status, body = self._get("/api/services")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data, [])

    def test_get_services_open_port_reachable_true(self):
        server, thread, port = self._start_tcp_server()
        try:
            services = [{"name": "echo_svc", "port": port, "health": "/health"}]
            status, _ = self._post_json("/api/config", {"services": services})
            self.assertEqual(status, 200)

            status, body = self._get("/api/services")
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["name"], "echo_svc")
            self.assertEqual(data[0]["port"], port)
            self.assertEqual(data[0]["health"], "/health")
            self.assertTrue(data[0]["reachable"])
            self.assertIsInstance(data[0]["latency_ms"], float)
            self.assertGreaterEqual(data[0]["latency_ms"], 0.0)
        finally:
            self._stop_tcp_server(server, thread)

    def test_get_services_closed_port_reachable_false(self):
        closed_port = self._get_closed_port()
        services = [{"name": "down_svc", "port": closed_port, "health": "/ping"}]
        status, _ = self._post_json("/api/config", {"services": services})
        self.assertEqual(status, 200)

        status, body = self._get("/api/services")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name"], "down_svc")
        self.assertEqual(data[0]["port"], closed_port)
        self.assertEqual(data[0]["health"], "/ping")
        self.assertFalse(data[0]["reachable"])
        self.assertIsNone(data[0]["latency_ms"])

    def test_get_services_with_open_and_closed_ports(self):
        server, thread, open_port = self._start_tcp_server()
        closed_port = self._get_closed_port()
        try:
            services = [
                {"name": "online_svc", "port": open_port, "health": "/health"},
                {"name": "offline_svc", "port": closed_port, "health": "/status"},
            ]
            status, _ = self._post_json("/api/config", {"services": services})
            self.assertEqual(status, 200)

            status, body = self._get("/api/services")
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertEqual(len(data), 2)

            self.assertEqual(data[0]["name"], "online_svc")
            self.assertEqual(data[0]["port"], open_port)
            self.assertEqual(data[0]["health"], "/health")
            self.assertTrue(data[0]["reachable"])
            self.assertIsInstance(data[0]["latency_ms"], float)
            self.assertGreaterEqual(data[0]["latency_ms"], 0.0)

            self.assertEqual(data[1]["name"], "offline_svc")
            self.assertEqual(data[1]["port"], closed_port)
            self.assertEqual(data[1]["health"], "/status")
            self.assertFalse(data[1]["reachable"])
            self.assertIsNone(data[1]["latency_ms"])
        finally:
            self._stop_tcp_server(server, thread)

    def test_get_services_rejects_invalid_host(self):
        status, body = self._get("/api/services", headers={"Host": "evil.example.com"})
        self.assertEqual(status, 403)
        self.assertIn("error", json.loads(body))


class WslEndpointTests(WebConfigServerTestCase):
    def test_get_wsl_endpoint_returns_json(self):
        status, body = self._get("/api/wsl")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("available", data)
        self.assertIn("distros", data)
        self.assertIsInstance(data["available"], bool)
        self.assertIsInstance(data["distros"], list)

    def test_get_wsl_rejects_invalid_host(self):
        status, body = self._get("/api/wsl", headers={"Host": "evil.example.com"})
        self.assertEqual(status, 403)
        self.assertIn("error", json.loads(body))


class AtomicWriteTests(WebConfigServerTestCase):
    def test_failed_write_leaves_previous_config_intact(self):
        status, _ = self._post_json("/api/config", {"brightness": 55})
        self.assertEqual(status, 200)
        before = self.config_path.read_text(encoding="utf-8")

        with patch.object(webconfig.os, "replace", side_effect=OSError("disk full")):
            status, body = self._post_json("/api/config", {"brightness": 91})
            self.assertEqual(status, 500)

        after = self.config_path.read_text(encoding="utf-8")
        self.assertEqual(before, after)
        status, body = self._get("/api/config")
        self.assertEqual(json.loads(body)["brightness"], 55)


class ServerLifecycleTests(unittest.TestCase):
    def test_start_and_stop_leave_no_thread_behind(self):
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            webui_dir = tmp_path / "webui"
            webui_dir.mkdir()
            (webui_dir / "index.html").write_text("<html>ok</html>", encoding="utf-8")
            (webui_dir / "style.css").write_text("body{}", encoding="utf-8")
            (webui_dir / "app.js").write_text("//ok", encoding="utf-8")

            server = webconfig.WebConfigServer(
                config_path=tmp_path / "webconfig.json",
                rules_path=tmp_path / "rules.yaml",
                webui_dir=webui_dir,
                port=0,
            )
            before_threads = threading.active_count()
            server.start()
            self.assertGreater(threading.active_count(), before_threads)
            server.stop()
            self.assertEqual(threading.active_count(), before_threads)

    def test_context_manager_stops_server(self):
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            webui_dir = tmp_path / "webui"
            webui_dir.mkdir()
            (webui_dir / "index.html").write_text("<html>ok</html>", encoding="utf-8")
            (webui_dir / "style.css").write_text("body{}", encoding="utf-8")
            (webui_dir / "app.js").write_text("//ok", encoding="utf-8")

            with webconfig.WebConfigServer(
                config_path=tmp_path / "webconfig.json",
                rules_path=tmp_path / "rules.yaml",
                webui_dir=webui_dir,
                port=0,
            ) as server:
                self.assertIsInstance(server.port, int)
                self.assertGreater(server.port, 0)

    def test_webconfig_server_wires_on_config_saved(self):
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            webui_dir = tmp_path / "webui"
            webui_dir.mkdir()

            def cb(d):
                return None
            with webconfig.WebConfigServer(
                config_path=tmp_path / "webconfig.json",
                rules_path=tmp_path / "rules.yaml",
                webui_dir=webui_dir,
                port=0,
                on_config_saved=cb,
            ) as server:
                self.assertIs(server._httpd.on_config_saved, cb)


class ServicesConfigTests(unittest.TestCase):
    def _base(self, **overrides):
        data = dict(webconfig.DEFAULT_SETTINGS)
        data.update(overrides)
        return data

    def test_default_services_is_empty_list(self):
        self.assertEqual(webconfig.DEFAULT_SETTINGS["services"], [])
        normalized = webconfig.validate_config(self._base())
        self.assertEqual(normalized["services"], [])

    def test_valid_service_passes(self):
        services = [{"name": "agenthub", "port": 7777, "health": "/health"}]
        normalized = webconfig.validate_config(self._base(services=services))
        self.assertEqual(normalized["services"], services)

    def test_port_out_of_range_is_rejected(self):
        services = [{"name": "agenthub", "port": 70000, "health": "/health"}]
        with self.assertRaises(webconfig.ConfigValidationError) as ctx:
            webconfig.validate_config(self._base(services=services))
        message = str(ctx.exception)
        self.assertIn("services[0]", message)
        self.assertIn("port", message)

    def test_health_without_slash_is_rejected(self):
        services = [{"name": "agenthub", "port": 7777, "health": "health"}]
        with self.assertRaises(webconfig.ConfigValidationError) as ctx:
            webconfig.validate_config(self._base(services=services))
        message = str(ctx.exception)
        self.assertIn("services[0]", message)
        self.assertIn("health", message)

    def test_empty_name_is_rejected(self):
        services = [{"name": "  ", "port": 7777, "health": "/health"}]
        with self.assertRaises(webconfig.ConfigValidationError) as ctx:
            webconfig.validate_config(self._base(services=services))
        message = str(ctx.exception)
        self.assertIn("services[0]", message)
        self.assertIn("name", message)


class RulesConfigErrorImportTests(unittest.TestCase):
    """Sanity check that webconfig relies on rules.py's own validation error,
    never redefining or shadowing it (see module contract)."""

    def test_rules_config_error_is_the_real_one(self):
        self.assertTrue(issubclass(RulesConfigError, Exception))


class CorsTests(WebConfigServerTestCase):
    """CORS headers and OPTIONS preflight tests."""

    def test_options_preflight_returns_204_with_cors_headers(self):
        conn = self._connection()
        try:
            conn.request("OPTIONS", "/api/config", headers={"Host": f"127.0.0.1:{self.server.port}"})
            response = conn.getresponse()
            response.read()
            self.assertEqual(response.status, 204)
            self.assertEqual(response.getheader("Access-Control-Allow-Origin"), "*")
            self.assertEqual(response.getheader("Access-Control-Allow-Methods"), "GET, POST, OPTIONS")
            self.assertEqual(response.getheader("Access-Control-Allow-Headers"), "Content-Type, Origin")
        finally:
            conn.close()

    def test_options_with_invalid_host_returns_403(self):
        conn = self._connection()
        try:
            conn.request("OPTIONS", "/api/config", headers={"Host": "evil.example.com"})
            response = conn.getresponse()
            body = response.read()
            self.assertEqual(response.status, 403)
            data = json.loads(body)
            self.assertIn("error", data)
        finally:
            conn.close()

    def test_get_api_status_includes_cors_header(self):
        status, body = self._get("/api/status")
        self.assertEqual(status, 200)
        # The response should have the CORS header
        # Note: _get uses http.client which doesn't expose headers easily
        # We'll verify via a direct connection
        conn = self._connection()
        try:
            conn.request("GET", "/api/status", headers={"Host": f"127.0.0.1:{self.server.port}"})
            response = conn.getresponse()
            self.assertEqual(response.getheader("Access-Control-Allow-Origin"), "*")
        finally:
            conn.close()

    def test_get_static_asset_includes_cors_header(self):
        conn = self._connection()
        try:
            conn.request("GET", "/style.css", headers={"Host": f"127.0.0.1:{self.server.port}"})
            response = conn.getresponse()
            self.assertEqual(response.getheader("Access-Control-Allow-Origin"), "*")
        finally:
            conn.close()

    def test_post_error_response_includes_cors_header(self):
        # POST with invalid content-type should return 415 with CORS header
        conn = self._connection()
        try:
            headers = {
                "Content-Type": "text/plain",
                "Origin": f"http://127.0.0.1:{self.server.port}",
                "Host": f"127.0.0.1:{self.server.port}",
            }
            conn.request("POST", "/api/config", body=b"{}", headers=headers)
            response = conn.getresponse()
            self.assertEqual(response.status, 415)
            self.assertEqual(response.getheader("Access-Control-Allow-Origin"), "*")
        finally:
            conn.close()


def _theme(cards, name="Test", mascotVariant="default"):
    """Build a theme payload dict for tests."""
    return {"id": "test", "name": name, "cards": cards, "mascotVariant": mascotVariant}


class ThemeEndpointTests(WebConfigServerTestCase):
    """Tests for the /api/theme GET and POST endpoints."""

    def test_get_theme_returns_default_when_no_file_saved(self):
        status, body = self._get("/api/theme")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["id"], "default")
        self.assertEqual(data["name"], "Por defecto")
        self.assertEqual(data["cards"], [])
        self.assertEqual(data["mascotVariant"], "default")

    def test_get_theme_returns_saved_theme(self):
        theme = {
            "id": "mytheme",
            "name": "Mi Tema",
            "cards": [
                {"id": "cpu", "visible": True, "order": 0, "sensors": ["cpu_percent"]}
            ],
            "mascotVariant": "happy",
        }
        webconfig.save_config(self.config_path, {"theme": theme})
        status, body = self._get("/api/theme")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["id"], "mytheme")
        self.assertEqual(data["name"], "Mi Tema")
        self.assertEqual(len(data["cards"]), 1)
        self.assertEqual(data["cards"][0]["id"], "cpu")
        self.assertTrue(data["cards"][0]["visible"])
        self.assertEqual(data["cards"][0]["order"], 0)
        self.assertEqual(data["cards"][0]["sensors"], ["cpu_percent"])
        self.assertEqual(data["mascotVariant"], "happy")

    def test_post_theme_valid_round_trips(self):
        theme = {
            "id": "newtheme",
            "name": "Nuevo Tema",
            "cards": [
                {"id": "ram", "visible": False, "order": 1, "sensors": ["memory_percent"]},
                {"id": "disk", "visible": True, "order": 2},
            ],
            "mascotVariant": "sad",
        }
        status, body = self._post_json("/api/theme", theme)
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["id"], "newtheme")
        self.assertEqual(data["name"], "Nuevo Tema")
        self.assertEqual(len(data["cards"]), 2)
        self.assertEqual(data["cards"][0]["id"], "ram")
        self.assertFalse(data["cards"][0]["visible"])
        self.assertEqual(data["cards"][0]["order"], 1)
        self.assertEqual(data["cards"][0]["sensors"], ["memory_percent"])
        self.assertEqual(data["cards"][1]["id"], "disk")
        self.assertTrue(data["cards"][1]["visible"])
        self.assertEqual(data["cards"][1]["order"], 2)
        self.assertEqual(data["cards"][1]["sensors"], [])
        self.assertEqual(data["mascotVariant"], "sad")

        # Verify it persisted
        status, body = self._get("/api/theme")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["id"], "newtheme")

    def test_post_theme_persists_to_disk(self):
        theme = {"id": "persist", "name": "Persist", "cards": [], "mascotVariant": "default"}
        self._post_json("/api/theme", theme)
        self.assertTrue(self.config_path.is_file())
        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["theme"]["id"], "persist")

    def test_post_theme_rejects_invalid_theme_id(self):
        status, body = self._post_json("/api/theme", {"id": "", "name": "Test", "cards": [], "mascotVariant": "default"})
        self.assertEqual(status, 400)
        self.assertIn("theme.id", json.loads(body)["error"])
        self.assertFalse(self.config_path.is_file())

    def test_post_theme_rejects_invalid_theme_name(self):
        status, body = self._post_json("/api/theme", {"id": "test", "name": "  ", "cards": [], "mascotVariant": "default"})
        self.assertEqual(status, 400)
        self.assertIn("theme.name", json.loads(body)["error"])
        self.assertFalse(self.config_path.is_file())

    def test_post_theme_rejects_invalid_mascot_variant(self):
        status, body = self._post_json("/api/theme", {"id": "test", "name": "Test", "cards": [], "mascotVariant": 123})
        self.assertEqual(status, 400)
        self.assertIn("theme.mascotVariant", json.loads(body)["error"])
        self.assertFalse(self.config_path.is_file())

    def test_post_theme_rejects_cards_not_a_list(self):
        status, body = self._post_json("/api/theme", _theme("not a list"))
        self.assertEqual(status, 400)
        self.assertIn("theme.cards", json.loads(body)["error"])
        self.assertFalse(self.config_path.is_file())

    def test_post_theme_rejects_card_with_invalid_id(self):
        status, body = self._post_json("/api/theme", _theme([{"id": "", "visible": True, "order": 0}]))
        self.assertEqual(status, 400)
        self.assertIn("theme.cards[0].id", json.loads(body)["error"])
        self.assertFalse(self.config_path.is_file())

    def test_post_theme_rejects_card_visible_as_int(self):
        status, body = self._post_json("/api/theme", _theme([{"id": "cpu", "visible": 1, "order": 0}]))
        self.assertEqual(status, 400)
        self.assertIn("theme.cards[0].visible", json.loads(body)["error"])
        self.assertFalse(self.config_path.is_file())

    def test_post_theme_rejects_card_order_as_negative(self):
        status, body = self._post_json("/api/theme", _theme([{"id": "cpu", "visible": True, "order": -1}]))
        self.assertEqual(status, 400)
        self.assertIn("theme.cards[0].order", json.loads(body)["error"])
        self.assertFalse(self.config_path.is_file())

    def test_post_theme_rejects_card_order_as_bool(self):
        status, body = self._post_json("/api/theme", _theme([{"id": "cpu", "visible": True, "order": True}]))
        self.assertEqual(status, 400)
        self.assertIn("theme.cards[0].order", json.loads(body)["error"])
        self.assertFalse(self.config_path.is_file())

    def test_post_theme_rejects_card_sensors_not_list_of_strings(self):
        payload = _theme([{"id": "cpu", "visible": True, "order": 0, "sensors": "not a list"}])
        status, body = self._post_json("/api/theme", payload)
        self.assertEqual(status, 400)
        self.assertIn("theme.cards[0].sensors", json.loads(body)["error"])
        self.assertFalse(self.config_path.is_file())

    def test_post_theme_rejects_card_sensors_with_non_string(self):
        status, body = self._post_json("/api/theme", _theme([{"id": "cpu", "visible": True, "order": 0, "sensors": [123]}]))
        self.assertEqual(status, 400)
        self.assertIn("theme.cards[0].sensors", json.loads(body)["error"])
        self.assertFalse(self.config_path.is_file())

    def test_post_theme_invalid_json_body(self):
        headers = {
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{self.server.port}",
        }
        status, body = self._post("/api/theme", b"not json", headers=headers)
        self.assertEqual(status, 400)

    def test_post_theme_with_wrong_origin_is_rejected(self):
        headers = {
            "Content-Type": "application/json",
            "Origin": "http://evil.example.com",
        }
        status, body = self._post("/api/theme", json.dumps(_theme([])).encode("utf-8"), headers=headers)
        self.assertEqual(status, 403)
        self.assertFalse(self.config_path.is_file())

    def test_post_theme_with_wrong_content_type_is_rejected(self):
        headers = {
            "Content-Type": "text/plain",
            "Origin": f"http://127.0.0.1:{self.server.port}",
        }
        status, body = self._post("/api/theme", json.dumps(_theme([])).encode("utf-8"), headers=headers)
        self.assertEqual(status, 415)
        self.assertFalse(self.config_path.is_file())

    def test_get_theme_with_wrong_host_header_is_rejected(self):
        status, body = self._get("/api/theme", headers={"Host": "evil.example.com"})
        self.assertEqual(status, 403)

    def test_post_theme_invalid_never_creates_file(self):
        self.assertFalse(self.config_path.is_file())
        status, body = self._post_json("/api/theme", _theme([{"id": "", "visible": True, "order": 0}]))
        self.assertEqual(status, 400)
        self.assertFalse(self.config_path.is_file())


class ThemeValidationTests(unittest.TestCase):
    """Direct unit tests for theme validation logic."""

    def _base(self, **overrides):
        data = dict(webconfig.DEFAULT_SETTINGS)
        data.update(overrides)
        return data

    def test_default_theme_is_valid(self):
        normalized = webconfig.validate_config(self._base())
        self.assertEqual(normalized["theme"]["id"], "default")
        self.assertEqual(normalized["theme"]["name"], "Por defecto")
        self.assertEqual(normalized["theme"]["cards"], [])
        self.assertEqual(normalized["theme"]["mascotVariant"], "default")
        self.assertNotIn("backgroundImage", normalized["theme"])

    def test_background_image_persists_when_valid(self):
        theme = {"id": "t", "name": "T", "cards": [], "mascotVariant": "d",
                 "backgroundImage": "data:image/webp;base64,AAA"}
        normalized = webconfig.validate_config(self._base(theme=theme))
        self.assertEqual(normalized["theme"]["backgroundImage"], theme["backgroundImage"])

    def test_background_image_rejects_non_data_url_and_oversize(self):
        for bad in ("http://x/y.png", "data:text/plain,hi", "x" * (400 * 1024 + 1)):
            theme = {"id": "t", "name": "T", "cards": [], "mascotVariant": "d",
                     "backgroundImage": bad}
            with self.assertRaises(webconfig.ConfigValidationError):
                webconfig.validate_config(self._base(theme=theme))

    def test_valid_theme_passes(self):
        theme = {
            "id": "mytheme",
            "name": "Mi Tema",
            "cards": [
                {"id": "cpu", "visible": True, "order": 0, "sensors": ["cpu_percent"]},
                {"id": "ram", "visible": False, "order": 1},
            ],
            "mascotVariant": "happy",
        }
        normalized = webconfig.validate_config(self._base(theme=theme))
        self.assertEqual(normalized["theme"]["id"], "mytheme")
        self.assertEqual(normalized["theme"]["name"], "Mi Tema")
        self.assertEqual(len(normalized["theme"]["cards"]), 2)
        self.assertEqual(normalized["theme"]["cards"][0]["sensors"], ["cpu_percent"])
        self.assertEqual(normalized["theme"]["cards"][1]["sensors"], [])
        self.assertEqual(normalized["theme"]["mascotVariant"], "happy")

    def test_theme_id_must_be_non_empty_string(self):
        with self.assertRaises(webconfig.ConfigValidationError) as ctx:
            webconfig.validate_config(self._base(theme={"id": "", "name": "Test", "cards": [], "mascotVariant": "default"}))
        self.assertIn("theme.id", str(ctx.exception))

    def test_theme_name_must_be_non_empty_string(self):
        with self.assertRaises(webconfig.ConfigValidationError) as ctx:
            webconfig.validate_config(self._base(theme={"id": "test", "name": "  ", "cards": [], "mascotVariant": "default"}))
        self.assertIn("theme.name", str(ctx.exception))

    def test_theme_mascot_variant_must_be_string(self):
        with self.assertRaises(webconfig.ConfigValidationError) as ctx:
            webconfig.validate_config(self._base(theme={"id": "test", "name": "Test", "cards": [], "mascotVariant": 123}))
        self.assertIn("theme.mascotVariant", str(ctx.exception))

    def test_theme_cards_must_be_list(self):
        with self.assertRaises(webconfig.ConfigValidationError) as ctx:
            webconfig.validate_config(self._base(theme=_theme("not a list")))
        self.assertIn("theme.cards", str(ctx.exception))

    def test_card_id_must_be_non_empty_string(self):
        with self.assertRaises(webconfig.ConfigValidationError) as ctx:
            webconfig.validate_config(self._base(theme=_theme([{"id": "", "visible": True, "order": 0}])))
        self.assertIn("theme.cards[0].id", str(ctx.exception))

    def test_card_visible_must_be_bool_rejects_int(self):
        with self.assertRaises(webconfig.ConfigValidationError) as ctx:
            webconfig.validate_config(self._base(theme=_theme([{"id": "cpu", "visible": 1, "order": 0}])))
        self.assertIn("theme.cards[0].visible", str(ctx.exception))

    def test_card_order_must_be_int_ge_zero(self):
        with self.assertRaises(webconfig.ConfigValidationError) as ctx:
            webconfig.validate_config(self._base(theme=_theme([{"id": "cpu", "visible": True, "order": -1}])))
        self.assertIn("theme.cards[0].order", str(ctx.exception))

    def test_card_order_rejects_bool(self):
        with self.assertRaises(webconfig.ConfigValidationError) as ctx:
            webconfig.validate_config(self._base(theme=_theme([{"id": "cpu", "visible": True, "order": True}])))
        self.assertIn("theme.cards[0].order", str(ctx.exception))

    def test_card_sensors_optional_list_of_strings(self):
        card = {"id": "cpu", "visible": True, "order": 0, "sensors": ["a", "b"]}
        normalized = webconfig.validate_config(self._base(theme=_theme([card])))
        self.assertEqual(normalized["theme"]["cards"][0]["sensors"], ["a", "b"])

    def test_card_sensors_missing_defaults_to_empty(self):
        normalized = webconfig.validate_config(self._base(theme=_theme([{"id": "cpu", "visible": True, "order": 0}])))
        self.assertEqual(normalized["theme"]["cards"][0]["sensors"], [])

    def test_card_sensors_rejects_non_string(self):
        with self.assertRaises(webconfig.ConfigValidationError) as ctx:
            webconfig.validate_config(self._base(theme=_theme([{"id": "cpu", "visible": True, "order": 0, "sensors": [123]}])))
        self.assertIn("theme.cards[0].sensors", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
