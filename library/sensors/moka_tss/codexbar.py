# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays
# Mascota fork - custom data source adapter for codexbar
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

"""CustomDataSource adapter for codexbar's dashboard snapshot endpoint.

codexbar exposes AI-agent provider usage (Claude, Codex, Antigravity,
opencodego, Copilot) at GET /dashboard/v1/snapshot. This module provides:

- CodexBarClient: fetches and caches the snapshot, degrading gracefully to the
  last known-good snapshot (marked stale) when the endpoint is unreachable,
  and reporting "unavailable" once no fetch has succeeded in 15 minutes.
- CodexBarWindowSource: a CustomDataSource for one (provider_id, window_kind)
  pair, e.g. ("claude", "session").
- available_provider_windows / build_sources: a small factory so a theme can
  discover which provider/window pairs currently exist in a snapshot.

No method here ever raises: CustomDataSource consumers (the theme renderer)
must never crash or block past the HTTP timeout because codexbar is down.
"""

import logging
import math
import os
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

from library.moka_tss import wsl
from library.sensors.sensors_custom import CustomDataSource

logger = logging.getLogger("moka_tss.codexbar")

DEFAULT_BASE_URL = "http://127.0.0.1:8787"
BASE_URL_ENV_VAR = "MOKA_CODEXBAR_URL"
LEGACY_BASE_URL_ENV_VAR = "MASCOTA_CODEXBAR_URL"
TOKEN_ENV_VAR = "CODEXBAR_DASHBOARD_TOKEN"
TOKEN_FILE_ENV_VAR = "MOKA_CODEXBAR_TOKEN_FILE"
LEGACY_TOKEN_FILE_ENV_VAR = "MASCOTA_CODEXBAR_TOKEN_FILE"
TOKEN_FILE_PATH = Path.home() / ".config" / "codexbar" / "dashboard-token"
DEFAULT_RELATIVE_TOKEN_PATH = Path(".config") / "codexbar" / "dashboard-token"

SNAPSHOT_ENDPOINT = "/dashboard/v1/snapshot"

# Success responses are cached briefly to avoid hammering the endpoint on every
# render tick. Failures are cached for a shorter window so a down endpoint is
# retried reasonably soon, while still coalescing bursts of concurrent callers.
SUCCESS_CACHE_TTL_SECONDS = 15.0
FAILURE_CACHE_TTL_SECONDS = 3.0

# Measured live: this endpoint can take >6s to respond when it refreshes
# providers. A 6s timeout was observed failing. Do not lower this.
HTTP_TIMEOUT_SECONDS = 30.0

# After this long with no successful fetch, stop serving stale data and report
# the source as unavailable instead.
UNAVAILABLE_AFTER_SECONDS = 15 * 60.0

HISTORY_LENGTH = 10


def _candidate_token_paths() -> List[Path]:
    """Return ordered candidate file paths for the codexbar dashboard token."""
    candidates: List[Path] = []
    override = os.environ.get(TOKEN_FILE_ENV_VAR) or os.environ.get(LEGACY_TOKEN_FILE_ENV_VAR)
    if override and override.strip():
        candidates.append(Path(override.strip()))
    candidates.append(TOKEN_FILE_PATH)
    if sys.platform == "win32":
        candidates.extend(wsl.find_wsl_candidate_paths(DEFAULT_RELATIVE_TOKEN_PATH))
    return candidates


def _resolve_token() -> Optional[str]:
    """Resolve the dashboard bearer token: env var, explicit file, home path, WSL.

    Never hardcode a token here. Returns None if no source has one, logging an error
    listing all searched candidate paths.
    """
    token = os.environ.get(TOKEN_ENV_VAR)
    if token and token.strip():
        return token.strip()

    candidate_paths = _candidate_token_paths()
    for path in candidate_paths:
        try:
            raw = path.read_text(encoding="utf-8").strip()
            if raw:
                return raw
        except OSError:
            continue

    lines = ["Codexbar dashboard token not found. Searched candidate paths:"]
    for p in candidate_paths:
        lines.append(f"  - {p}")
    lines.append(f"Set {TOKEN_ENV_VAR} or {TOKEN_FILE_ENV_VAR} to configure the token.")
    logger.error("\n".join(lines))
    return None


def _resolve_base_url() -> str:
    return os.environ.get(BASE_URL_ENV_VAR) or os.environ.get(LEGACY_BASE_URL_ENV_VAR) or DEFAULT_BASE_URL


class CodexBarClient:
    """Fetches and caches codexbar dashboard snapshots.

    Thread-safe: a single lock serializes get_snapshot() calls, which both
    memoizes the result within the active TTL and coalesces concurrent
    callers arriving while a fetch would otherwise be repeated.
    """

    def __init__(self, base_url: Optional[str] = None, timeout: float = HTTP_TIMEOUT_SECONDS):
        self._base_url = base_url or _resolve_base_url()
        self._timeout = timeout
        self._lock = threading.Lock()
        self._last_good_snapshot: Optional[dict] = None
        self._last_good_at: Optional[float] = None
        self._last_check_at: Optional[float] = None
        self._last_check_ok: bool = False

    def get_snapshot(self) -> Tuple[Optional[dict], bool, bool]:
        """Return (snapshot, is_stale, is_available).

        - snapshot is None only when no fetch has ever succeeded.
        - is_stale is True when the returned snapshot came from a previous
          successful fetch, not the current attempt.
        - is_available is False when more than 15 minutes have passed since
          the last successful fetch (or none ever succeeded); callers should
          treat the data as unusable rather than merely stale.
        """
        with self._lock:
            now = time.monotonic()
            ttl = SUCCESS_CACHE_TTL_SECONDS if self._last_check_ok else FAILURE_CACHE_TTL_SECONDS
            if self._last_check_at is not None and (now - self._last_check_at) < ttl:
                return self._compose_result(now)

            try:
                snapshot = self._fetch()
                self._last_good_snapshot = snapshot
                self._last_good_at = now
                self._last_check_ok = True
            except (requests.exceptions.RequestException, ValueError):
                self._last_check_ok = False
            self._last_check_at = now
            return self._compose_result(now)

    def _compose_result(self, now: float) -> Tuple[Optional[dict], bool, bool]:
        if self._last_good_snapshot is None or self._last_good_at is None:
            return None, False, False
        is_stale = not self._last_check_ok
        is_available = (now - self._last_good_at) <= UNAVAILABLE_AFTER_SECONDS
        return self._last_good_snapshot, is_stale, is_available

    def _fetch(self) -> dict:
        token = _resolve_token()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        url = self._base_url + SNAPSHOT_ENDPOINT
        response = requests.get(url, headers=headers, timeout=self._timeout)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("codexbar snapshot payload is not a JSON object")
        return data


def _find_window(snapshot: dict, provider_id: str, window_kind: str) -> Optional[dict]:
    """Find the window dict for (provider_id, window_kind) in a snapshot.

    Returns None if the provider is missing, the provider carries a non-null
    error (its percentages cannot be trusted), or it has no matching window.
    """
    for provider in snapshot.get("providers") or []:
        if provider.get("id") != provider_id:
            continue
        if provider.get("error"):
            return None
        for window in provider.get("windows") or []:
            if window.get("kind") == window_kind:
                return window
        return None
    return None


class CodexBarWindowSource(CustomDataSource):
    """CustomDataSource for one provider's usage window, e.g. claude/session."""

    UNAVAILABLE_MARKER = "N/D (unavailable)"
    NO_DATA_MARKER = "N/D"

    def __init__(self, provider_id: str, window_kind: str, client: Optional[CodexBarClient] = None):
        self._provider_id = provider_id
        self._window_kind = window_kind
        self._client = client or CodexBarClient()
        self._last_val: List[float] = [math.nan] * HISTORY_LENGTH

    def as_numeric(self) -> float:
        value, _marker = self._read()
        return value

    def as_string(self) -> str:
        value, marker = self._read()
        if marker is not None:
            return marker
        return f'{value:.0f}%'

    def last_values(self) -> List[float]:
        return self._last_val

    def _read(self) -> Tuple[float, Optional[str]]:
        snapshot, is_stale, is_available = self._client.get_snapshot()
        value = math.nan
        marker: Optional[str] = None
        if snapshot is None or not is_available:
            marker = self.UNAVAILABLE_MARKER
        else:
            window = _find_window(snapshot, self._provider_id, self._window_kind)
            used = window.get("usedPercent") if window else None
            if not isinstance(used, (int, float)):
                marker = self.NO_DATA_MARKER
            else:
                value = float(used)
                if is_stale:
                    marker = f'{value:.0f}% (stale)'
        self._record(value)
        return value, marker

    def _record(self, value: float) -> None:
        self._last_val.append(value)
        self._last_val.pop(0)


def available_provider_windows(snapshot: dict) -> List[Tuple[str, str]]:
    """List (provider_id, window_kind) pairs present in a snapshot.

    Providers carrying a non-null error are skipped: they have no trustworthy
    window to wire into a theme.
    """
    pairs: List[Tuple[str, str]] = []
    for provider in snapshot.get("providers") or []:
        provider_id = provider.get("id")
        if not provider_id or provider.get("error"):
            continue
        for window in provider.get("windows") or []:
            kind = window.get("kind")
            if kind:
                pairs.append((provider_id, kind))
    return pairs


def build_sources(client: Optional[CodexBarClient] = None) -> Dict[str, CodexBarWindowSource]:
    """Build one CodexBarWindowSource per (provider, window) pair currently
    available, keyed as "<provider_id>:<window_kind>" (e.g. "claude:session").

    Intended to be called once at theme wiring time. If no snapshot is
    available yet, returns an empty dict; the caller may retry later.
    All sources share the given (or a new) client, so they share its cache.
    """
    client = client or CodexBarClient()
    snapshot, _is_stale, _is_available = client.get_snapshot()
    if not snapshot:
        return {}
    sources: Dict[str, CodexBarWindowSource] = {}
    for provider_id, window_kind in available_provider_windows(snapshot):
        key = f"{provider_id}:{window_kind}"
        sources[key] = CodexBarWindowSource(provider_id, window_kind, client=client)
    return sources
