# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays like Turing Smart Screen or XuanFang
# https://github.com/mathoudebine/turing-smart-screen-python/
#
# Copyright (C) 2021 Matthieu Houdebine (mathoudebine)
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

# agent-hub adapter: CustomDataSource implementations backed by the local
# agent-hub HTTP server (job/metrics polling) plus a background SSE client
# for the push channel (`GET /events`).
#
# agent-hub API contract (verified live, no auth, loopback-only):
#   GET /api/state   -> {"jobs": [{"jobId", "agent", "model", "status", ...}]}
#   GET /api/metrics -> {"rows": [{"agent", "samples", "succeeded", "failed", ...}]}
#   GET /events      -> Server-Sent Events, heartbeat every 15s

import contextlib
import math
import os
import threading
import time
from collections import namedtuple
from typing import List, Optional

import requests

from library.sensors.sensors_custom import CustomDataSource

DEFAULT_BASE_URL = "http://127.0.0.1:7777"
BASE_URL_ENV_VAR = "MOKA_AGENTHUB_URL"
LEGACY_BASE_URL_ENV_VAR = "MASCOTA_AGENTHUB_URL"


def _resolve_base_url(base_url: Optional[str]) -> str:
    if base_url:
        return base_url
    return os.environ.get(BASE_URL_ENV_VAR) or os.environ.get(LEGACY_BASE_URL_ENV_VAR) or DEFAULT_BASE_URL


# Result of a single poll: `value` is the parsed JSON payload (or None when
# never fetched successfully), `stale` marks a last-good value served during
# a failure window, `available` is False once continuous failures exceed the
# configured grace window (or nothing ever succeeded).
FetchResult = namedtuple("FetchResult", ["value", "stale", "available"])


class _CacheEntry:
    __slots__ = ("value", "ok", "stale", "fetched_at", "last_success_at")

    def __init__(self, value, ok, stale, fetched_at, last_success_at):
        self.value = value
        self.ok = ok
        self.stale = stale
        self.fetched_at = fetched_at
        self.last_success_at = last_success_at


class AgentHubClient:
    """Polling client for the agent-hub HTTP endpoints.

    Caches successful responses for `success_cache_s`, caches failures for
    `failure_cache_s` (to avoid hammering a down server), and degrades
    gracefully: it keeps serving the last good value (marked stale) until
    `unavailable_after_s` of continuous failure have elapsed, after which it
    reports the endpoint as unavailable.
    """

    def __init__(self, base_url: Optional[str] = None, session=None,
                 success_cache_s: float = 15.0, failure_cache_s: float = 3.0,
                 http_timeout_s: float = 30.0, unavailable_after_s: float = 15 * 60.0,
                 clock=time.monotonic):
        self._base_url = _resolve_base_url(base_url)
        self._session = session or requests.Session()
        self._success_cache_s = success_cache_s
        self._failure_cache_s = failure_cache_s
        self._http_timeout_s = http_timeout_s
        self._unavailable_after_s = unavailable_after_s
        self._clock = clock
        self._cache = {}
        self._lock = threading.Lock()

    def get_state(self) -> FetchResult:
        return self._to_result(self._fetch("/api/state"))

    def get_metrics(self) -> FetchResult:
        return self._to_result(self._fetch("/api/metrics"))

    @staticmethod
    def _to_result(entry: _CacheEntry) -> FetchResult:
        if entry.value is None:
            return FetchResult(value=None, stale=False, available=False)
        return FetchResult(value=entry.value, stale=entry.stale, available=True)

    def _fetch(self, path: str) -> _CacheEntry:
        with self._lock:
            now = self._clock()
            cached = self._cache.get(path)
            if cached is not None:
                ttl = self._success_cache_s if cached.ok else self._failure_cache_s
                if (now - cached.fetched_at) < ttl:
                    return cached

            try:
                response = self._session.get(self._base_url + path, timeout=self._http_timeout_s)
                response.raise_for_status()
                data = response.json()
            except (requests.RequestException, ValueError):
                entry = self._on_failure(cached, now)
            else:
                entry = _CacheEntry(value=data, ok=True, stale=False, fetched_at=now, last_success_at=now)

            self._cache[path] = entry
            return entry

    def _on_failure(self, cached: Optional[_CacheEntry], now: float) -> _CacheEntry:
        last_success_at = cached.last_success_at if cached is not None else None
        within_grace = (
            last_success_at is not None
            and (now - last_success_at) < self._unavailable_after_s
        )
        if within_grace:
            return _CacheEntry(
                value=cached.value, ok=False, stale=True,
                fetched_at=now, last_success_at=last_success_at,
            )
        return _CacheEntry(value=None, ok=False, stale=False, fetched_at=now, last_success_at=last_success_at)


class AgentHubEventStream:
    """Background SSE consumer for `GET /events`.

    Runs entirely on a daemon thread: `start()` launches it, `stop()` joins
    it. Reconnects with exponential backoff (capped at `max_backoff_s`) on
    any connection failure, and relies on the HTTP read timeout
    (`heartbeat_timeout_s`) to detect a connection that has gone silent
    past the ~15s heartbeat cadence agent-hub advertises.
    """

    def __init__(self, base_url: Optional[str] = None, on_event=None, on_state_change=None,
                 session=None, initial_backoff_s: float = 1.0, max_backoff_s: float = 30.0,
                 heartbeat_timeout_s: float = 40.0, connect_timeout_s: float = 10.0,
                 backoff_sleep=None):
        self._base_url = _resolve_base_url(base_url)
        self._on_event = on_event or (lambda event: None)
        self._on_state_change = on_state_change or (lambda state: None)
        self._session = session or requests.Session()
        self._initial_backoff_s = initial_backoff_s
        self._max_backoff_s = max_backoff_s
        self._heartbeat_timeout_s = heartbeat_timeout_s
        self._connect_timeout_s = connect_timeout_s
        self._backoff_sleep = backoff_sleep or self._default_backoff_sleep

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="AgentHubEventStream", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _default_backoff_sleep(self, seconds: float) -> None:
        self._stop_event.wait(seconds)

    def _run(self) -> None:
        backoff = self._initial_backoff_s
        while not self._stop_event.is_set():
            connected = False
            try:
                connected = self._consume_once()
            except Exception:  # never let a stray bug kill the reconnect loop
                connected = False

            if self._stop_event.is_set():
                break

            if connected:
                backoff = self._initial_backoff_s
            else:
                self._on_state_change("reconnecting")
                self._backoff_sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff_s)

        self._on_state_change("stopped")

    def _consume_once(self) -> bool:
        url = self._base_url + "/events"
        try:
            response = self._session.get(
                url, stream=True,
                timeout=(self._connect_timeout_s, self._heartbeat_timeout_s),
            )
        except requests.RequestException:
            self._on_state_change("connect_failed")
            return False

        with contextlib.closing(response):
            if response.status_code != 200:
                self._on_state_change("connect_failed")
                return False

            self._on_state_change("connected")
            try:
                self._pump(response)
            except requests.RequestException:
                self._on_state_change("heartbeat_timeout")
            self._on_state_change("disconnected")
            return True

    def _pump(self, response) -> None:
        data_lines: List[str] = []
        event_type = "message"

        # chunk_size=1: the response has neither Content-Length nor chunked
        # transfer-encoding, so a buffered read for a larger chunk size would
        # block trying to fill it even after a full SSE frame already
        # arrived, starving both live dispatch and heartbeat detection.
        for raw_line in response.iter_lines(decode_unicode=True, chunk_size=1):
            if self._stop_event.is_set():
                return
            if raw_line is None:
                continue

            line = raw_line
            if line == "":
                if data_lines:
                    self._dispatch(event_type, "\n".join(data_lines))
                data_lines = []
                event_type = "message"
                continue
            if line.startswith(":"):
                continue  # comment / heartbeat ping, not an event
            if line.startswith("data:"):
                data_lines.append(line[len("data:"):].lstrip(" "))
            elif line.startswith("event:"):
                event_type = line[len("event:"):].strip()
            # other fields (id:, retry:) are intentionally ignored

    def _dispatch(self, event_type: str, data: str) -> None:
        try:
            self._on_event({"event": event_type, "data": data})
        except Exception:
            pass  # a broken consumer callback must never take down the stream


class _RollingNumericDataSource(CustomDataSource):
    """Shared plumbing for agent-hub numeric sensors.

    Mirrors the upstream `ExampleCustomNumericData` convention: keeps the
    last 10 values (padded with math.nan) for the line-graph widget, and
    guarantees none of the three CustomDataSource methods ever raises.
    """

    def __init__(self, client: Optional[AgentHubClient] = None):
        self._client = client if client is not None else get_default_client()
        self.value: float = math.nan
        self.last_val: List[float] = [math.nan] * 10

    def _compute(self) -> float:
        raise NotImplementedError

    def as_numeric(self) -> float:
        try:
            value = self._compute()
        except Exception:
            value = math.nan
        if value is None:
            value = math.nan
        self.value = value
        self.last_val.append(self.value)
        self.last_val.pop(0)
        return self.value

    def as_string(self) -> str:
        try:
            if math.isnan(self.value):
                return " N/A"
            return self._format(self.value)
        except Exception:
            return " N/A"

    def _format(self, value: float) -> str:
        return f"{value:>5.1f}"

    def last_values(self) -> List[float]:
        try:
            return list(self.last_val)
        except Exception:
            return [math.nan] * 10


class AgentHubRunningJobsData(_RollingNumericDataSource):
    """Number of agent-hub jobs currently RUNNING (from `GET /api/state`)."""

    def _compute(self) -> float:
        result = self._client.get_state()
        if not result.available or result.value is None:
            return math.nan
        jobs = result.value.get("jobs", []) or []
        count = sum(1 for job in jobs if isinstance(job, dict) and job.get("status") == "running")
        return float(count)

    def _format(self, value: float) -> str:
        return f"{int(value):>3}"


class AgentHubSuccessRateData(_RollingNumericDataSource):
    """Overall success rate percentage (from `GET /api/metrics`)."""

    def _compute(self) -> float:
        result = self._client.get_metrics()
        if not result.available or result.value is None:
            return math.nan
        rows = result.value.get("rows", []) or []
        total_samples = 0
        total_succeeded = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            total_samples += row.get("samples", 0) or 0
            total_succeeded += row.get("succeeded", 0) or 0
        if total_samples <= 0:
            return math.nan
        return (total_succeeded / total_samples) * 100.0

    def _format(self, value: float) -> str:
        return f"{value:>5.1f}%"


_default_client_lock = threading.Lock()
_default_client: Optional[AgentHubClient] = None


def get_default_client() -> AgentHubClient:
    """Lazily-created singleton client, shared by CustomDataSource instances
    that are wired up with no constructor arguments (upstream convention)."""
    global _default_client
    with _default_client_lock:
        if _default_client is None:
            _default_client = AgentHubClient()
        return _default_client
