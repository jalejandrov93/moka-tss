# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays
# Mascota fork - test TCP service prober

import socket
import socketserver
import threading
import unittest

from library.moka_tss.services import probe_service, probe_services


class _EchoHandler(socketserver.BaseRequestHandler):
    def handle(self):
        pass


class _TCPServer(socketserver.TCPServer):
    allow_reuse_address = True


class TestServices(unittest.TestCase):
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

    def test_open_port_reachable_and_latency(self):
        server, thread, port = self._start_tcp_server()
        try:
            result = probe_service("127.0.0.1", port, timeout=1.0)
            self.assertTrue(result["reachable"])
            self.assertIsInstance(result["latency_ms"], float)
            self.assertGreaterEqual(result["latency_ms"], 0.0)
            self.assertNotIn("name", result)
        finally:
            self._stop_tcp_server(server, thread)

    def test_open_port_with_name(self):
        server, thread, port = self._start_tcp_server()
        try:
            result = probe_service("127.0.0.1", port, timeout=1.0, name="agenthub")
            self.assertTrue(result["reachable"])
            self.assertEqual(result["name"], "agenthub")
            self.assertIsInstance(result["latency_ms"], float)
            self.assertGreaterEqual(result["latency_ms"], 0.0)
        finally:
            self._stop_tcp_server(server, thread)

    def test_closed_port_unreachable_and_latency_none(self):
        closed_port = self._get_closed_port()
        result = probe_service("127.0.0.1", closed_port, timeout=0.2)
        self.assertFalse(result["reachable"])
        self.assertIsNone(result["latency_ms"])

    def test_probe_services_multiple(self):
        server1, thread1, port1 = self._start_tcp_server()
        server2, thread2, port2 = self._start_tcp_server()
        closed_port = self._get_closed_port()

        services = [
            {"name": "agenthub", "port": port1, "health": "/health"},
            {"name": "codexbar", "port": port2, "health": "/status"},
            {"name": "offline_api", "port": closed_port, "health": "/healthz"},
        ]

        try:
            results = probe_services(services, host="127.0.0.1", timeout=0.5)
            self.assertEqual(len(results), 3)

            # Service 1 (open)
            self.assertEqual(results[0]["name"], "agenthub")
            self.assertEqual(results[0]["port"], port1)
            self.assertEqual(results[0]["health"], "/health")
            self.assertTrue(results[0]["reachable"])
            self.assertIsInstance(results[0]["latency_ms"], float)
            self.assertGreaterEqual(results[0]["latency_ms"], 0.0)

            # Service 2 (open)
            self.assertEqual(results[1]["name"], "codexbar")
            self.assertEqual(results[1]["port"], port2)
            self.assertEqual(results[1]["health"], "/status")
            self.assertTrue(results[1]["reachable"])
            self.assertIsInstance(results[1]["latency_ms"], float)
            self.assertGreaterEqual(results[1]["latency_ms"], 0.0)

            # Service 3 (closed)
            self.assertEqual(results[2]["name"], "offline_api")
            self.assertEqual(results[2]["port"], closed_port)
            self.assertEqual(results[2]["health"], "/healthz")
            self.assertFalse(results[2]["reachable"])
            self.assertIsNone(results[2]["latency_ms"])
        finally:
            self._stop_tcp_server(server1, thread1)
            self._stop_tcp_server(server2, thread2)

    def test_invalid_input_does_not_crash(self):
        # Port out of range
        for bad_port in [0, -1, 65536, 70000]:
            res = probe_service("127.0.0.1", bad_port)
            self.assertFalse(res["reachable"])
            self.assertIsNone(res["latency_ms"])

        # Non-integer port types
        for bad_type in ["7777", None, True, False, [8080]]:
            res = probe_service("127.0.0.1", bad_type)
            self.assertFalse(res["reachable"])
            self.assertIsNone(res["latency_ms"])

        # Invalid hosts
        for bad_host in ["", None, "nonexistent.domain.invalid.local"]:
            res = probe_service(bad_host, 8080, timeout=0.1)
            self.assertFalse(res["reachable"])
            self.assertIsNone(res["latency_ms"])

        # Invalid timeouts
        for bad_timeout in [0, -1.0, "fast"]:
            res = probe_service("127.0.0.1", 8080, timeout=bad_timeout)
            self.assertFalse(res["reachable"])
            self.assertIsNone(res["latency_ms"])

    def test_probe_services_with_invalid_entries(self):
        services = [
            {"name": "bad_port_high", "port": 70000, "health": "/health"},
            {"name": "bad_port_str", "port": "abc", "health": "/ping"},
            {"name": "bad_port_negative", "port": -5, "health": "/test"},
        ]
        results = probe_services(services, host="127.0.0.1")
        self.assertEqual(len(results), 3)
        for entry in results:
            self.assertFalse(entry["reachable"])
            self.assertIsNone(entry["latency_ms"])
            self.assertIn("health", entry)

        # Non-list input
        self.assertEqual(probe_services(None), [])
        self.assertEqual(probe_services([]), [])

        # Non-dict item in services
        malformed = probe_services(["invalid_entry"])
        self.assertEqual(len(malformed), 1)
        self.assertFalse(malformed[0]["reachable"])
        self.assertIsNone(malformed[0]["latency_ms"])


if __name__ == "__main__":
    unittest.main()
