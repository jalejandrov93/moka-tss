# SPDX-License-Identifier: GPL-3.0-or-later
#
# Tests for the agent-hub CustomDataSource adapter (poll client + SSE stream).
# All tests run against a local http.server instance on an ephemeral port:
# no test ever talks to the real network.

import json
import math
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from library.sensors.mascota.agenthub import (
    AgentHubClient,
    AgentHubEventStream,
    AgentHubRunningJobsData,
    AgentHubSuccessRateData,
    FetchResult,
)


class _TestServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def start_server(do_get):
    """Start a background HTTP server on an ephemeral port.

    `do_get(handler)` is called for every GET request with the
    BaseHTTPRequestHandler instance, and is responsible for writing the
    full response (status, headers, body).
    """

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args, **_kwargs):
            pass  # keep test output clean

        def do_GET(self):
            do_get(self)

    server = _TestServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    base_url = "http://127.0.0.1:%d" % server.server_address[1]
    return server, thread, base_url


def stop_server(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def find_free_port():
    server, thread, base_url = start_server(lambda h: None)
    stop_server(server, thread)
    return base_url


def wait_until(predicate, timeout=2.0, step=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return predicate()


class FakeClock:
    def __init__(self, start=0.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


# ---------------------------------------------------------------------------
# AgentHubClient
# ---------------------------------------------------------------------------

class TestAgentHubClientHappyPath(unittest.TestCase):
    def setUp(self):
        self.requests_seen = []

        def do_get(handler):
            self.requests_seen.append(handler.path)
            if handler.path == "/api/state":
                body = json.dumps({"jobs": [
                    {"jobId": "a", "status": "running"},
                    {"jobId": "b", "status": "done"},
                ]}).encode("utf-8")
            elif handler.path == "/api/metrics":
                body = json.dumps({"rows": [
                    {"agent": "agy", "samples": 10, "succeeded": 9, "failed": 1},
                ]}).encode("utf-8")
            else:
                handler.send_response(404)
                handler.end_headers()
                return
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.end_headers()
            handler.wfile.write(body)

        self.server, self.thread, self.base_url = start_server(do_get)
        self.client = AgentHubClient(base_url=self.base_url)

    def tearDown(self):
        stop_server(self.server, self.thread)

    def test_get_state_happy_path(self):
        result = self.client.get_state()
        self.assertTrue(result.available)
        self.assertFalse(result.stale)
        self.assertEqual(len(result.value["jobs"]), 2)

    def test_get_metrics_happy_path(self):
        result = self.client.get_metrics()
        self.assertTrue(result.available)
        self.assertFalse(result.stale)
        self.assertEqual(result.value["rows"][0]["agent"], "agy")

    def test_success_is_cached_within_ttl(self):
        clock = FakeClock(0.0)
        client = AgentHubClient(base_url=self.base_url, clock=clock, success_cache_s=15.0)
        client.get_state()
        clock.advance(5.0)
        client.get_state()
        state_requests = [p for p in self.requests_seen if p == "/api/state"]
        self.assertEqual(len(state_requests), 1)


class TestAgentHubClientFailureModes(unittest.TestCase):
    def test_connection_refused_reports_unavailable(self):
        dead_url = find_free_port()  # server already stopped: nothing listens here
        client = AgentHubClient(base_url=dead_url, http_timeout_s=1.0)
        result = client.get_state()
        self.assertFalse(result.available)
        self.assertFalse(result.stale)
        self.assertIsNone(result.value)

    def test_timeout_reports_unavailable(self):
        def do_get(handler):
            time.sleep(0.5)
            handler.send_response(200)
            handler.end_headers()
            handler.wfile.write(b"{}")

        server, thread, base_url = start_server(do_get)
        try:
            client = AgentHubClient(base_url=base_url, http_timeout_s=0.05)
            result = client.get_state()
            self.assertFalse(result.available)
        finally:
            stop_server(server, thread)

    def test_malformed_json_reports_unavailable(self):
        def do_get(handler):
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.end_headers()
            handler.wfile.write(b"{not-json")

        server, thread, base_url = start_server(do_get)
        try:
            client = AgentHubClient(base_url=base_url)
            result = client.get_state()
            self.assertFalse(result.available)
            self.assertIsNone(result.value)
        finally:
            stop_server(server, thread)

    def test_serves_stale_value_within_grace_window(self):
        state = {"ok": True}

        def do_get(handler):
            if state["ok"]:
                handler.send_response(200)
                handler.send_header("Content-Type", "application/json")
                handler.end_headers()
                handler.wfile.write(json.dumps({"jobs": []}).encode("utf-8"))
            else:
                handler.send_response(500)
                handler.end_headers()

        server, thread, base_url = start_server(do_get)
        clock = FakeClock(0.0)
        client = AgentHubClient(
            base_url=base_url, clock=clock,
            success_cache_s=1.0, failure_cache_s=1.0, unavailable_after_s=900.0,
        )
        try:
            good = client.get_state()
            self.assertTrue(good.available)
            self.assertFalse(good.stale)

            state["ok"] = False
            clock.advance(2.0)  # success cache expired -> re-fetch -> fails
            stale = client.get_state()
            self.assertTrue(stale.available)
            self.assertTrue(stale.stale)
            self.assertEqual(stale.value, {"jobs": []})
        finally:
            stop_server(server, thread)

    def test_reports_unavailable_after_continuous_failure_window(self):
        state = {"ok": True}

        def do_get(handler):
            if state["ok"]:
                handler.send_response(200)
                handler.send_header("Content-Type", "application/json")
                handler.end_headers()
                handler.wfile.write(json.dumps({"jobs": []}).encode("utf-8"))
            else:
                handler.send_response(500)
                handler.end_headers()

        server, thread, base_url = start_server(do_get)
        clock = FakeClock(0.0)
        client = AgentHubClient(
            base_url=base_url, clock=clock,
            success_cache_s=1.0, failure_cache_s=1.0, unavailable_after_s=10.0,
        )
        try:
            client.get_state()
            state["ok"] = False
            clock.advance(2.0)
            stale = client.get_state()
            self.assertTrue(stale.available)

            clock.advance(20.0)  # well past unavailable_after_s
            dead = client.get_state()
            self.assertFalse(dead.available)
            self.assertIsNone(dead.value)
        finally:
            stop_server(server, thread)


# ---------------------------------------------------------------------------
# AgentHubEventStream
# ---------------------------------------------------------------------------

class TestAgentHubEventStreamParsing(unittest.TestCase):
    def test_single_line_data_event(self):
        events = []
        got_event = threading.Event()

        def do_get(handler):
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream")
            handler.end_headers()
            handler.wfile.write(b'data: {"foo": 1}\n\n')
            handler.wfile.flush()
            time.sleep(0.3)  # keep the connection open briefly

        server, thread, base_url = start_server(do_get)
        stream = AgentHubEventStream(
            base_url=base_url,
            on_event=lambda evt: (events.append(evt), got_event.set()),
        )
        stream.start()
        try:
            self.assertTrue(wait_until(lambda: len(events) >= 1))
            self.assertEqual(events[0]["event"], "message")
            self.assertEqual(events[0]["data"], '{"foo": 1}')
        finally:
            stream.stop()
            stop_server(server, thread)

    def test_multiline_data_event_is_joined_with_newline(self):
        events = []

        def do_get(handler):
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream")
            handler.end_headers()
            handler.wfile.write(b"data: line1\ndata: line2\n\n")
            handler.wfile.flush()
            time.sleep(0.3)

        server, thread, base_url = start_server(do_get)
        stream = AgentHubEventStream(base_url=base_url, on_event=events.append)
        stream.start()
        try:
            self.assertTrue(wait_until(lambda: len(events) >= 1))
            self.assertEqual(events[0]["data"], "line1\nline2")
        finally:
            stream.stop()
            stop_server(server, thread)

    def test_named_event_type_is_dispatched(self):
        events = []

        def do_get(handler):
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream")
            handler.end_headers()
            handler.wfile.write(b'event: job_update\ndata: {"a": 1}\n\n')
            handler.wfile.flush()
            time.sleep(0.3)

        server, thread, base_url = start_server(do_get)
        stream = AgentHubEventStream(base_url=base_url, on_event=events.append)
        stream.start()
        try:
            self.assertTrue(wait_until(lambda: len(events) >= 1))
            self.assertEqual(events[0]["event"], "job_update")
        finally:
            stream.stop()
            stop_server(server, thread)

    def test_heartbeat_comment_lines_are_ignored(self):
        events = []

        def do_get(handler):
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream")
            handler.end_headers()
            handler.wfile.write(b": ping\n\n")
            handler.wfile.flush()
            handler.wfile.write(b"data: real\n\n")
            handler.wfile.flush()
            time.sleep(0.3)

        server, thread, base_url = start_server(do_get)
        stream = AgentHubEventStream(base_url=base_url, on_event=events.append)
        stream.start()
        try:
            self.assertTrue(wait_until(lambda: len(events) >= 1))
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["data"], "real")
        finally:
            stream.stop()
            stop_server(server, thread)


class TestAgentHubEventStreamReconnection(unittest.TestCase):
    def test_reconnects_after_mid_stream_disconnect(self):
        events = []
        attempt = {"count": 0}

        def do_get(handler):
            attempt["count"] += 1
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream")
            handler.end_headers()
            if attempt["count"] == 1:
                handler.wfile.write(b"data: first\n\n")
                handler.wfile.flush()
                # simulate abrupt mid-stream disconnect
                handler.connection.close()
            else:
                handler.wfile.write(b"data: second\n\n")
                handler.wfile.flush()
                time.sleep(0.3)

        server, thread, base_url = start_server(do_get)
        stream = AgentHubEventStream(
            base_url=base_url, on_event=events.append,
            initial_backoff_s=0.01, max_backoff_s=0.05,
        )
        stream.start()
        try:
            self.assertTrue(wait_until(lambda: len(events) >= 2, timeout=5.0))
            self.assertEqual(events[0]["data"], "first")
            self.assertEqual(events[1]["data"], "second")
        finally:
            stream.stop()
            stop_server(server, thread)

    def test_heartbeat_timeout_triggers_reconnect(self):
        events = []
        attempt = {"count": 0}

        def do_get(handler):
            attempt["count"] += 1
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream")
            handler.end_headers()
            if attempt["count"] == 1:
                time.sleep(0.5)  # longer than heartbeat_timeout_s below: dead air
            else:
                handler.wfile.write(b"data: after-timeout\n\n")
                handler.wfile.flush()
                time.sleep(0.3)

        server, thread, base_url = start_server(do_get)
        states = []
        stream = AgentHubEventStream(
            base_url=base_url, on_event=events.append,
            on_state_change=states.append,
            heartbeat_timeout_s=0.1,
            initial_backoff_s=0.01, max_backoff_s=0.05,
        )
        stream.start()
        try:
            self.assertTrue(wait_until(lambda: len(events) >= 1, timeout=5.0))
            self.assertEqual(events[0]["data"], "after-timeout")
            self.assertIn("heartbeat_timeout", states)
        finally:
            stream.stop()
            stop_server(server, thread)

    def test_backoff_grows_and_is_capped(self):
        dead_url = find_free_port()
        recorded = []
        stream = AgentHubEventStream(
            base_url=dead_url,
            initial_backoff_s=0.01, max_backoff_s=0.05,
            backoff_sleep=lambda seconds: recorded.append(seconds),
        )
        stream.start()
        try:
            self.assertTrue(wait_until(lambda: len(recorded) >= 5))
        finally:
            stream.stop()

        self.assertEqual(recorded[0], 0.01)
        self.assertEqual(recorded[1], 0.02)
        self.assertEqual(recorded[2], 0.04)
        self.assertEqual(recorded[3], 0.05)
        self.assertEqual(recorded[4], 0.05)

    def test_clean_shutdown_leaves_no_surviving_thread(self):
        dead_url = find_free_port()
        stream = AgentHubEventStream(
            base_url=dead_url,
            initial_backoff_s=0.01, max_backoff_s=0.02,
            backoff_sleep=lambda seconds: None,
        )
        before = set(t.ident for t in threading.enumerate())
        stream.start()
        self.assertTrue(wait_until(stream.is_running))
        stream.stop()
        self.assertFalse(stream.is_running())
        after = set(t.ident for t in threading.enumerate())
        self.assertTrue((after - before) == set() or (after - before).issubset(before))


# ---------------------------------------------------------------------------
# CustomDataSource implementations
# ---------------------------------------------------------------------------

class _StubClient:
    def __init__(self, state_result=None, metrics_result=None, raise_error=False):
        self._state_result = state_result
        self._metrics_result = metrics_result
        self._raise_error = raise_error

    def get_state(self):
        if self._raise_error:
            raise RuntimeError("boom")
        return self._state_result

    def get_metrics(self):
        if self._raise_error:
            raise RuntimeError("boom")
        return self._metrics_result


class TestAgentHubRunningJobsData(unittest.TestCase):
    def test_counts_only_running_jobs(self):
        client = _StubClient(state_result=FetchResult(
            value={"jobs": [
                {"status": "running"}, {"status": "running"}, {"status": "done"},
            ]}, stale=False, available=True,
        ))
        source = AgentHubRunningJobsData(client=client)
        self.assertEqual(source.as_numeric(), 2.0)
        self.assertIn("2", source.as_string())

    def test_never_raises_on_client_error(self):
        client = _StubClient(raise_error=True)
        source = AgentHubRunningJobsData(client=client)
        value = source.as_numeric()
        self.assertTrue(math.isnan(value))
        self.assertIsInstance(source.as_string(), str)
        self.assertIsInstance(source.last_values(), list)

    def test_never_raises_when_unavailable(self):
        client = _StubClient(state_result=FetchResult(value=None, stale=False, available=False))
        source = AgentHubRunningJobsData(client=client)
        self.assertTrue(math.isnan(source.as_numeric()))

    def test_last_values_rolling_window(self):
        client = _StubClient(state_result=FetchResult(
            value={"jobs": [{"status": "running"}]}, stale=False, available=True,
        ))
        source = AgentHubRunningJobsData(client=client)
        for _ in range(3):
            source.as_numeric()
        history = source.last_values()
        self.assertEqual(len(history), 10)
        self.assertEqual(history[-3:], [1.0, 1.0, 1.0])
        self.assertTrue(all(math.isnan(v) for v in history[:-3]))


class TestAgentHubSuccessRateData(unittest.TestCase):
    def test_computes_weighted_success_rate(self):
        client = _StubClient(metrics_result=FetchResult(
            value={"rows": [
                {"samples": 10, "succeeded": 9, "failed": 1},
                {"samples": 10, "succeeded": 10, "failed": 0},
            ]}, stale=False, available=True,
        ))
        source = AgentHubSuccessRateData(client=client)
        rate = source.as_numeric()
        self.assertAlmostEqual(rate, 95.0)
        self.assertIn("%", source.as_string())

    def test_never_raises_with_no_samples(self):
        client = _StubClient(metrics_result=FetchResult(value={"rows": []}, stale=False, available=True))
        source = AgentHubSuccessRateData(client=client)
        self.assertTrue(math.isnan(source.as_numeric()))
        self.assertIsInstance(source.as_string(), str)

    def test_never_raises_on_client_error(self):
        client = _StubClient(raise_error=True)
        source = AgentHubSuccessRateData(client=client)
        self.assertTrue(math.isnan(source.as_numeric()))
        self.assertIsInstance(source.as_string(), str)
        self.assertIsInstance(source.last_values(), list)


if __name__ == "__main__":
    unittest.main()
