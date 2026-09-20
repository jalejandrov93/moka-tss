# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays
# Mascota fork - local loopback web configuration panel
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

"""Local loopback web server for the "panel de configuracion" (D13).

The user asked for "una interfaz intuitiva moderna amigable" for tuning
codexbar/agent-hub endpoints, alert rules, brightness, orientation and the
refresh interval. D13 picked a static page served by the app itself on
127.0.0.1 and opened from the tray icon in the default browser, instead of
tkinter or a Tauri toolchain -- see odd/tasks/mascota.md.

This module is standard-library only (`http.server`, `json`, `threading`):
the project's stated end goal is a single double-clickable .exe (T12), so a
second toolchain here would work against that.

Security posture (read this before touching request handling)
---------------------------------------------------------------
A page loaded from ANY origin can still make a request to 127.0.0.1 from
the user's own browser (the loopback address is not itself a same-origin
boundary), so a server here that blindly accepted writes would be a real
cross-site request forgery hole, not a theoretical one. Every request is
checked before it reaches a handler:

- The socket only ever binds to 127.0.0.1 (`DEFAULT_HOST`); there is no way
  to construct a `WebConfigServer` that listens on 0.0.0.0.
- `Host` must match this server's own `127.0.0.1:<port>` on every request
  (GET included) -- this is the baseline loopback check.
- `Origin` must match this server's own `http://127.0.0.1:<port>` on every
  state-changing request (POST). GET is exempt: a plain browser navigation
  to the page does not send an `Origin` header, and requiring one would
  break "open this from the tray icon" (D13).
- `Content-Type` must be exactly `application/json` (parameters such as a
  charset are accepted) on every POST; anything else is refused before the
  body is even parsed.
- Static files are served from an explicit allowlist of URL path -> local
  filename (`STATIC_ASSETS`). There is no code path that joins a URL onto
  a filesystem path, so a `..` in the URL simply matches nothing in the
  allowlist and falls through to a 404 -- it is never resolved against disk.

Writes (`POST /api/config`, `POST /api/rules`) are validated BEFORE any
file is touched, and written with `_atomic_write_text` (temp file +
`os.replace`), so a validation failure or a mid-write OS error always
leaves the previous file exactly as it was.
"""

import json
import os
import tempfile
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Dict, Optional
from urllib.parse import urlparse

import yaml

from library.mascota.rules import RuleEngine, RulesConfigError

DEFAULT_HOST = "127.0.0.1"

# agent-hub already owns 7777 and codexbar owns 8787 on this machine (see
# library/sensors/mascota/agenthub.py and codexbar.py); 8765 is unrelated to
# either so opening the panel does not race a port one of them might grab.
DEFAULT_PORT = 8765

ALLOWED_ORIENTATIONS = ("landscape", "portrait")

DEFAULT_SETTINGS: Dict[str, object] = {
    "codexbar_url": "http://127.0.0.1:8787",
    "agenthub_url": "http://127.0.0.1:7777",
    "hidden_providers": ["copilot", "opencodego"],
    "brightness": 85,
    "orientation": "landscape",
    "refresh_interval_seconds": 2.0,
}

STATIC_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
}


class ConfigValidationError(Exception):
    """Raised for a settings payload that fails validation.

    Always names the offending field, the same contract rules.py's
    RulesConfigError follows, so a bad POST body is never a mystery.
    """


def default_config_path() -> Path:
    # library/mascota/webconfig.py -> library/mascota -> library -> repo root
    return Path(__file__).resolve().parents[2] / "res" / "mascota" / "webconfig.json"


def default_rules_path() -> Path:
    return Path(__file__).resolve().parents[2] / "res" / "mascota" / "rules.yaml"


def default_webui_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "res" / "mascota" / "webui"


def _atomic_write_text(path: Path, text: str) -> None:
    """Write `text` to `path` without ever leaving a truncated file behind.

    Writes to a sibling temp file in the same directory (so the final
    `os.replace` is a same-filesystem rename, which POSIX and Windows both
    guarantee is atomic) then swaps it into place. If anything raises
    before the swap -- encoding the payload, the OS write itself, or the
    replace -- the temp file is removed and the exception re-raised, and
    `path` is left exactly as it was found.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".webconfig-tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, str(path))
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _require_str(data: dict, field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ConfigValidationError(f"Setting '{field}' must be a non-empty string, got {value!r}.")
    return value


def _require_url(data: dict, field: str) -> str:
    value = _require_str(data, field)
    if not (value.startswith("http://") or value.startswith("https://")):
        raise ConfigValidationError(
            f"Setting '{field}' must start with 'http://' or 'https://', got {value!r}."
        )
    return value


def validate_config(data: dict) -> Dict[str, object]:
    """Validate and normalize a full settings dict, never mutating `data`.

    Raises ConfigValidationError naming the offending field on any problem.
    Callers are expected to have already merged partial POST bodies onto
    the previously saved (or default) settings, so this always sees a
    complete dict.
    """
    if not isinstance(data, dict):
        raise ConfigValidationError(f"Config must be a JSON object, got {type(data).__name__}.")

    normalized: Dict[str, object] = dict(data)

    normalized["codexbar_url"] = _require_url(data, "codexbar_url")
    normalized["agenthub_url"] = _require_url(data, "agenthub_url")

    hidden = data.get("hidden_providers", [])
    if not isinstance(hidden, list) or not all(isinstance(item, str) for item in hidden):
        raise ConfigValidationError(
            f"Setting 'hidden_providers' must be a list of strings, got {hidden!r}."
        )
    normalized["hidden_providers"] = list(hidden)

    brightness = data.get("brightness")
    if isinstance(brightness, bool) or not isinstance(brightness, (int, float)):
        raise ConfigValidationError(f"Setting 'brightness' must be a number, got {brightness!r}.")
    if not (0 <= brightness <= 100):
        raise ConfigValidationError(
            f"Setting 'brightness' must be between 0 and 100, got {brightness!r}."
        )
    normalized["brightness"] = brightness

    orientation = data.get("orientation")
    if orientation not in ALLOWED_ORIENTATIONS:
        allowed = ", ".join(ALLOWED_ORIENTATIONS)
        raise ConfigValidationError(
            f"Setting 'orientation' must be one of [{allowed}], got {orientation!r}."
        )
    normalized["orientation"] = orientation

    refresh = data.get("refresh_interval_seconds")
    if isinstance(refresh, bool) or not isinstance(refresh, (int, float)):
        raise ConfigValidationError(
            f"Setting 'refresh_interval_seconds' must be a number, got {refresh!r}."
        )
    if refresh <= 0:
        raise ConfigValidationError(
            f"Setting 'refresh_interval_seconds' must be > 0, got {refresh!r}."
        )
    normalized["refresh_interval_seconds"] = float(refresh)

    return normalized


def load_config(path: Path) -> Dict[str, object]:
    """Return the saved settings merged onto the defaults.

    A missing file (first run) simply yields the defaults -- there is
    nothing to validate or repair, so this never raises for that case.
    """
    merged = dict(DEFAULT_SETTINGS)
    if path.is_file():
        with open(path, "r", encoding="utf-8") as handle:
            saved = json.load(handle)
        if isinstance(saved, dict):
            merged.update(saved)
    return merged


def save_config(path: Path, updates: dict) -> Dict[str, object]:
    """Merge `updates` onto the current settings, validate, then write.

    Raises ConfigValidationError (without touching `path`) if the merged
    result is invalid. Returns the full, normalized settings that were
    written.
    """
    merged = load_config(path)
    merged.update(updates)
    normalized = validate_config(merged)
    _atomic_write_text(path, json.dumps(normalized, indent=2, ensure_ascii=False))
    return normalized


def load_rules(path: Path) -> dict:
    """Return the rules config as a plain dict, parsed from YAML.

    An absent file is reported as an empty-but-valid shell so a fresh
    install's GET /api/rules has something sane to show before the user
    has saved anything.
    """
    if not path.is_file():
        return {"moods": [], "default_mood": None, "rules": []}
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data if isinstance(data, dict) else {}


def save_rules(path: Path, data: dict) -> None:
    """Validate `data` the exact way rules.py's RuleEngine would, then save.

    Raises RulesConfigError (rules.py's own exception, naming the
    offending rule) without writing anything if the payload is invalid --
    this project never wants to discover a broken rules.yaml at render
    time (see rules.py's module docstring).
    """
    RuleEngine.from_dict(data)  # raises RulesConfigError; result is discarded
    _atomic_write_text(path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))


def _default_status() -> Dict[str, object]:
    return {"connected": False, "mood": None, "last_refresh": None}


class _ConfigRequestHandler(BaseHTTPRequestHandler):
    """Routes GET/POST for the panel. All shared state lives on `self.server`
    (an _ConfigHTTPServer), never as class attributes, so multiple servers
    in the same process (e.g. parallel tests) never share state."""

    server_version = "MascotaWebConfig/1.0"

    def log_message(self, format_str, *args):  # noqa: A002 - stdlib signature
        # Never spam stderr on every request; nothing here is a hint that
        # anything went wrong, so it is not worth wiring a real logger.
        pass

    def _expected_host(self) -> str:
        return f"127.0.0.1:{self.server.server_port}"

    def _expected_origin(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def _host_is_valid(self) -> bool:
        return self.headers.get("Host") == self._expected_host()

    def _send_json(self, status: HTTPStatus, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: HTTPStatus, message: str) -> None:
        self._send_json(status, {"error": message})

    def do_GET(self):  # noqa: N802 - stdlib method name
        if not self._host_is_valid():
            self._send_error_json(HTTPStatus.FORBIDDEN, "Host header does not match this server.")
            return

        path = urlparse(self.path).path

        if path == "/api/config":
            self._send_json(HTTPStatus.OK, load_config(self.server.config_path))
            return
        if path == "/api/rules":
            self._send_json(HTTPStatus.OK, load_rules(self.server.rules_path))
            return
        if path == "/api/status":
            self._send_json(HTTPStatus.OK, self.server.status_provider())
            return

        asset = STATIC_ASSETS.get(path)
        if asset is None:
            self._send_error_json(HTTPStatus.NOT_FOUND, f"No such resource: {path}")
            return
        filename, content_type = asset
        file_path = self.server.webui_dir / filename
        if not file_path.is_file():
            self._send_error_json(HTTPStatus.NOT_FOUND, f"Static asset missing: {filename}")
            return
        body = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802 - stdlib method name
        # Baseline loopback check first, same as GET.
        if not self._host_is_valid():
            self._send_error_json(HTTPStatus.FORBIDDEN, "Host header does not match this server.")
            return

        # CSRF checks: a page on another origin can still reach 127.0.0.1
        # from the victim's browser, so Origin must match this server's own
        # address on every write (see module docstring).
        if self.headers.get("Origin") != self._expected_origin():
            self._send_error_json(HTTPStatus.FORBIDDEN, "Origin header does not match this server.")
            return

        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        if content_type != "application/json":
            self._send_error_json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Content-Type must be application/json."
            )
            return

        path = urlparse(self.path).path
        if path not in ("/api/config", "/api/rules"):
            self._send_error_json(HTTPStatus.NOT_FOUND, f"No such resource: {path}")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_error_json(HTTPStatus.BAD_REQUEST, "Invalid Content-Length header.")
            return
        raw_body = self.rfile.read(length) if length > 0 else b""

        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, f"Invalid JSON body: {exc}")
            return

        if path == "/api/config":
            self._handle_post_config(payload)
        else:
            self._handle_post_rules(payload)

    def _handle_post_config(self, payload) -> None:
        if not isinstance(payload, dict):
            self._send_error_json(HTTPStatus.BAD_REQUEST, "Config body must be a JSON object.")
            return
        try:
            saved = save_config(self.server.config_path, payload)
        except ConfigValidationError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except OSError as exc:
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, f"Could not save config: {exc}")
            return
        self._send_json(HTTPStatus.OK, saved)

    def _handle_post_rules(self, payload) -> None:
        if not isinstance(payload, dict):
            self._send_error_json(HTTPStatus.BAD_REQUEST, "Rules body must be a JSON object.")
            return
        try:
            save_rules(self.server.rules_path, payload)
        except RulesConfigError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except OSError as exc:
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, f"Could not save rules: {exc}")
            return
        self._send_json(HTTPStatus.OK, payload)


class _ConfigHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer carrying the panel's shared, per-instance state."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler_cls, *, config_path, rules_path, webui_dir, status_provider):
        super().__init__(address, handler_cls)
        self.config_path = config_path
        self.rules_path = rules_path
        self.webui_dir = webui_dir
        self.status_provider = status_provider


class WebConfigServer:
    """Public entry point: owns one loopback-only HTTP server and its thread.

    Always binds to 127.0.0.1 -- there is deliberately no `host` parameter,
    so a caller cannot accidentally widen this to 0.0.0.0 (see D13 and the
    module docstring's security section).

    `port=0` (the default in tests) asks the OS for an ephemeral free port,
    read back afterwards via `.port`. The real app should pass
    `DEFAULT_PORT` explicitly.
    """

    def __init__(
        self,
        *,
        config_path: Optional[Path] = None,
        rules_path: Optional[Path] = None,
        webui_dir: Optional[Path] = None,
        port: int = DEFAULT_PORT,
        status_provider: Optional[Callable[[], Dict[str, object]]] = None,
    ):
        self._config_path = Path(config_path) if config_path is not None else default_config_path()
        self._rules_path = Path(rules_path) if rules_path is not None else default_rules_path()
        self._webui_dir = Path(webui_dir) if webui_dir is not None else default_webui_dir()
        self._requested_port = port
        self._status_provider = status_provider or _default_status
        self._httpd: Optional[_ConfigHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def port(self) -> int:
        if self._httpd is None:
            raise RuntimeError("WebConfigServer has not been started yet.")
        return self._httpd.server_port

    def start(self) -> None:
        if self._httpd is not None:
            raise RuntimeError("WebConfigServer is already running.")
        self._httpd = _ConfigHTTPServer(
            (DEFAULT_HOST, self._requested_port),
            _ConfigRequestHandler,
            config_path=self._config_path,
            rules_path=self._rules_path,
            webui_dir=self._webui_dir,
            status_provider=self._status_provider,
        )
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="mascota-webconfig",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._httpd = None
        self._thread = None

    def __enter__(self) -> "WebConfigServer":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
