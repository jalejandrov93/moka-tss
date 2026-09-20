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
        }
        self.assertEqual(set(data.keys()), expected_keys)
        self.assertEqual(len(data), 10)


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


if __name__ == "__main__":
    unittest.main()
