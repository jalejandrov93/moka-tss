# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays
# Mascota fork - main application coordinator and refresh loop

"""Application object for Project Mascota (T9).

Orchestrates local system sensors, codexbar, agent-hub, the declarative
rule engine, partial-blit rendering on the Turing 3.5" display, the local
web configuration server, and the system tray icon.
"""

import logging
import math
import signal
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from PIL import Image

import library.moka_tss.render as render_module
from library.lcd.lcd_comm_rev_a import Command
from library.moka_tss.host import InstanceLock, SingleInstanceError
from library.moka_tss.paths import resource_path
from library.moka_tss.render import (
    DEFAULT_SIZE,
    HIDDEN_PROVIDERS,
    MascotSprites,
    _visible_providers,
    _worst_provider_usage,
)
from library.moka_tss.rules import RuleEngine
from library.moka_tss.screen import DEFAULT_BRIGHTNESS, Screen, command_frame
from library.moka_tss.sensors_local import read_system_sensors
from library.sensors.moka_tss.agenthub import AgentHubClient
from library.sensors.moka_tss.codexbar import CodexBarClient

logger = logging.getLogger("moka_tss")


__all__ = [
    "InstanceLock",
    "SingleInstanceError",
    "MokaApp",
    "MascotaApp",
    "default_renderer",
    "format_ready_line",
]


def format_ready_line(port: Any) -> str:
    """Format readiness line signaled to the host process or Tauri sidecar.

    Args:
        port: Integer TCP port number in the range 1-65535.

    Returns:
        The formatted ready signal line: 'MOKA_READY port=<port>'.

    Raises:
        ValueError: If port is not an integer or is outside the range 1-65535.
    """
    if isinstance(port, bool) or not isinstance(port, int):
        raise ValueError(f"Invalid port: {port!r} (must be an integer)")
    if not (1 <= port <= 65535):
        raise ValueError(f"Port out of range: {port} (must be 1-65535)")
    return f"MOKA_READY port={port}"


def default_renderer(
    snapshot: Optional[dict],
    state: Optional[dict],
    system: Optional[dict],
    *,
    mood: Optional[str] = None,
    sprites: Optional[MascotSprites] = None,
    tick: int = 0,
    **kwargs: Any,
) -> Image.Image:
    """Render a dashboard frame, passing through the mood the rule engine chose.

    The mood is handed to render() as an argument. An earlier version injected it
    by swapping out render's private _compute_mood at runtime, which broke render's
    purity, was not thread-safe inside a refresh loop, and shattered the moment
    that private function gained a parameter.
    """
    return render_module.render(
        snapshot, state, system, sprites=sprites, mood=mood, tick=tick, **kwargs
    )


def _sanitize_metric(val: Any) -> Optional[float]:
    """Convert metric to float, turning absent, non-numeric, or NaN values into None."""
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(val)
        if math.isnan(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


class MokaApp:
    """Main application coordinator for the MOKA Turing Smart Screen dashboard."""

    def __init__(
        self,
        serial_port: Any = None,
        screen: Optional[Screen] = None,
        read_sensors: Optional[Callable[[], Dict[str, Any]]] = None,
        agenthub_client: Optional[AgentHubClient] = None,
        codexbar_client: Optional[CodexBarClient] = None,
        rule_engine: Optional[RuleEngine] = None,
        sprites: Optional[MascotSprites] = None,
        renderer: Optional[Callable[..., Image.Image]] = None,
        web_server: Any = None,
        tray_enabled: bool = True,
        simulate: bool = False,
        simulate_output_path: Optional[Path] = None,
        tick_interval: float = 2.0,
        agenthub_interval: float = 5.0,
        codexbar_interval: float = 60.0,
        brightness: int = DEFAULT_BRIGHTNESS,
        orientation: int = 2,
        hidden_providers: Any = HIDDEN_PROVIDERS,
        clock: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
        instance_lock: Optional[InstanceLock] = None,
    ):
        self.serial_port = serial_port
        self.screen = screen or (Screen(serial_port) if serial_port is not None else None)
        self.read_sensors = read_sensors or read_system_sensors
        self.agenthub_client = agenthub_client or AgentHubClient()
        self.codexbar_client = codexbar_client or CodexBarClient()
        self.rule_engine = rule_engine or self._load_default_rule_engine()
        self.sprites = sprites or self._load_default_sprites()
        self.renderer = renderer or default_renderer
        self.web_server = web_server
        self.tray_enabled = tray_enabled
        self.simulate = simulate
        self.simulate_output_path = Path(simulate_output_path or "screencap.png")
        self.tick_interval = tick_interval
        self.agenthub_interval = agenthub_interval
        self.codexbar_interval = codexbar_interval
        self.brightness = brightness
        self.orientation = orientation
        self.mascot_variant = "default"
        self.hidden_providers = hidden_providers
        self._clock = clock
        self._sleep_fn = sleep_fn
        self.instance_lock = instance_lock or InstanceLock()

        self._running = False
        self._loop_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.tray_icon = None

        self.tick_count = 0
        self.last_system: Optional[Dict[str, Any]] = None
        self.last_state: Optional[Dict[str, Any]] = None
        self.last_snapshot: Optional[Dict[str, Any]] = None
        self.last_mood: Optional[str] = None
        self.last_rule: Optional[Dict[str, Any]] = None
        self.agenthub_available = False
        self.codexbar_available = False

        self._last_sensors_time = -1e9
        self._last_agenthub_time = -1e9
        self._last_codexbar_time = -1e9

        self._consecutive_render_errors = 0
        self._consecutive_screen_errors = 0

    def _load_default_rule_engine(self) -> RuleEngine:
        rules_path = resource_path("res", "moka_tss", "rules.yaml")
        if rules_path.is_file():
            return RuleEngine.from_yaml_file(rules_path)
        return RuleEngine.from_dict({"moods": ["calma"], "default_mood": "calma", "rules": []})

    def _load_default_sprites(self) -> Optional[MascotSprites]:
        sprites_dir = resource_path("res", "moka_tss", "sprites")
        try:
            from library.moka_tss.mascot import MascotSprites as RealMascotSprites
            return RealMascotSprites.load(sprites_dir)
        except Exception as exc:
            logger.warning("Failed to load mascot sprites from %s: %s", sprites_dir, exc)
            return None

    def _get_status(self) -> Dict[str, Any]:
        return self.status_snapshot()

    def status_snapshot(self) -> Dict[str, Any]:
        """Return a JSON-serializable snapshot of application state."""
        system_data = self.last_system if isinstance(self.last_system, dict) else {}
        raw_gpu = system_data.get("gpu")
        if isinstance(raw_gpu, dict):
            raw_gpu = raw_gpu.get("util")

        screen_status = {
            "present": self.screen is not None,
            "simulate": bool(self.simulate),
            "brightness": int(self.brightness),
        }

        transmission = self.screen.stats_snapshot() if self.screen is not None else None

        return {
            "tick": int(self.tick_count),
            "running": bool(self._running),
            "agenthub_available": bool(self.agenthub_available),
            "codexbar_available": bool(self.codexbar_available),
            "has_system": self.last_system is not None,
            "has_snapshot": self.last_snapshot is not None,
            "has_state": self.last_state is not None,
            "mood": self.last_mood,
            "system": {
                "cpu": _sanitize_metric(system_data.get("cpu")),
                "ram": _sanitize_metric(system_data.get("ram")),
                "gpu": _sanitize_metric(raw_gpu),
            },
            "screen": screen_status,
            "transmission": transmission,
            "rule": self.last_rule,
        }

    def _poll_local_sensors(self, now: float) -> None:
        if (now - self._last_sensors_time) < self.tick_interval:
            return
        try:
            system_data = self.read_sensors()
            if system_data is not None:
                self.last_system = system_data
        except Exception as exc:
            logger.warning("Local sensors read failed: %s", exc)
        self._last_sensors_time = now

    def _poll_agenthub(self, now: float) -> None:
        if (now - self._last_agenthub_time) < self.agenthub_interval:
            return
        try:
            res = self.agenthub_client.get_state()
            if res.value is not None:
                self.last_state = res.value
            self.agenthub_available = res.available
        except Exception as exc:
            logger.warning("Agent-hub poll failed: %s", exc)
        self._last_agenthub_time = now

    def _poll_codexbar(self, now: float) -> None:
        if (now - self._last_codexbar_time) < self.codexbar_interval:
            return
        try:
            snapshot, _, is_available = self.codexbar_client.get_snapshot()
            if snapshot is not None:
                self.last_snapshot = snapshot
            self.codexbar_available = is_available
        except Exception as exc:
            logger.warning("Codexbar poll failed: %s", exc)
        self._last_codexbar_time = now

    def _collect_rule_metrics(self) -> Dict[str, Any]:
        system = self.last_system or {}
        snapshot = self.last_snapshot
        state = self.last_state

        worst_quota = 0.0
        if snapshot:
            providers = _visible_providers(snapshot, self.hidden_providers)
            worst_quota, _ = _worst_provider_usage(providers)

        gpu = system.get("gpu")
        gpu_util = gpu.get("util") if isinstance(gpu, dict) else None

        active_jobs = 0
        if state and isinstance(state, dict):
            jobs = state.get("jobs") or []
            active_jobs = sum(1 for j in jobs if isinstance(j, dict) and j.get("status") == "running")

        return {
            "cpu": system.get("cpu"),
            "gpu": gpu_util,
            "cpu_temp": system.get("cpu_temp"),
            "quota_max_used_percent": worst_quota if snapshot else None,
            "agenthub_available": 1 if self.agenthub_available else 0,
            "agenthub_active_jobs": active_jobs if self.agenthub_available else None,
        }

    def _evaluate_mood(self, metrics: Dict[str, Any]) -> str:
        try:
            return self.rule_engine.evaluate(metrics)
        except Exception as exc:
            logger.warning("Rule evaluation failed: %s", exc)
            return getattr(self.rule_engine, "default_mood", "calma")

    def _show_on_screen(self, frame) -> None:
        """Push one frame to the panel, tracking consecutive failures."""
        try:
            self.screen.show(frame)
            self._consecutive_screen_errors = 0
        except Exception as exc:
            if self.simulate:
                logger.warning("Screen show failed in simulation: %s", exc)
            else:
                logger.error("Screen show failed: %s", exc)
            self._consecutive_screen_errors += 1

    def _render_and_output(self, mood: str) -> None:
        try:
            frame = self.renderer(
                self.last_snapshot,
                self.last_state,
                self.last_system,
                mood=mood,
                sprites=self.sprites,
                tick=self.tick_count,
                hidden_providers=self.hidden_providers,
            )
            self._consecutive_render_errors = 0
        except Exception as exc:
            logger.error("Rendering failed: %s", exc)
            self._consecutive_render_errors += 1
            frame = Image.new("RGB", DEFAULT_SIZE, (15, 23, 42))

        if self.simulate:
            try:
                self.simulate_output_path.parent.mkdir(parents=True, exist_ok=True)
                frame.save(self.simulate_output_path)
            except Exception as exc:
                logger.warning("Failed to save simulation frame: %s", exc)
            if self.screen is not None:
                self._show_on_screen(frame)
        elif self.screen is not None:
            self._show_on_screen(frame)

    def _recover_renderer(self) -> None:
        if self._consecutive_render_errors < 3:
            return
        try:
            sprites = self._load_default_sprites()
            if sprites is not None:
                self.sprites = sprites
        except Exception as exc:
            logger.warning("Render recovery failed: %s", exc)
        self._consecutive_render_errors = 0

    def _recover_screen(self) -> None:
        if self._consecutive_screen_errors < 3:
            return
        if self.screen is not None:
            try:
                self.screen.reset()
            except Exception as exc:
                logger.warning("Screen recovery failed: %s", exc)
        self._consecutive_screen_errors = 0

    def _check_recovery(self, now: float) -> None:
        try:
            self._recover_renderer()
            self._recover_screen()
        except Exception as exc:
            logger.error("Recovery check failed unexpectedly: %s", exc)

    def step(self) -> None:
        """Execute one refresh cycle: poll sources according to cadence, evaluate rules, and render."""
        now = self._clock()
        self._poll_local_sensors(now)
        self._poll_agenthub(now)
        self._poll_codexbar(now)
        metrics = self._collect_rule_metrics()
        res = self.rule_engine.evaluate_detailed(metrics)
        mood = res.mood
        self.last_mood = str(mood) if mood is not None else None
        self.last_rule = {
            "winning_rule_id": res.winning_rule_id,
            "fired": list(res.fired_rule_ids),
        }
        self._render_and_output(mood)
        self.tick_count += 1
        self._check_recovery(now)

    def _apply_saved_settings(self, settings: dict) -> None:
        """Apply newly saved settings immediately to the running app and hardware."""
        if not isinstance(settings, dict):
            return
        v = settings.get("brightness")
        if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 100:
            self.brightness = int(v)
            if self.screen is not None:
                try:
                    self.screen.set_brightness(int(v))
                except Exception as exc:
                    logger.warning("Failed to apply brightness %s to screen: %s", v, exc)
        self._apply_mascot_variant(settings)

    def _apply_mascot_variant(self, settings: dict) -> None:
        """Reload mascot sprites when the saved theme selects a new variant."""
        theme = settings.get("theme")
        variant = theme.get("mascotVariant") if isinstance(theme, dict) else None
        if not isinstance(variant, str) or not variant:
            return
        if variant == getattr(self, "mascot_variant", "default"):
            return
        try:
            from library.moka_tss.mascot import MascotSprites as RealMascotSprites
            sprites = RealMascotSprites.load_variant(variant)
        except Exception as exc:
            logger.warning("Failed to load mascot variant %r: %s", variant, exc)
            return
        self.sprites = sprites
        self.mascot_variant = variant

    def start_config_server(self) -> Optional[int]:
        """Start the loopback config panel if it is not already serving.

        Called at startup rather than only from the tray, so the panel has a
        stable address the user can bookmark. Starting it on demand meant the
        URL only existed after someone found the tray icon and clicked it, and
        it died with every restart, leaving an open browser tab pointing at
        nothing. It listens on 127.0.0.1 and costs a socket.

        Returns the port it is serving on, or None if it could not start.
        """
        if self.web_server is None:
            try:
                from library.moka_tss.webconfig import WebConfigServer
                self.web_server = WebConfigServer(
                    status_provider=self._get_status,
                    on_config_saved=self._apply_saved_settings,
                )
            except Exception as exc:
                logger.error("Failed to initialize WebConfigServer: %s", exc)
                return None

        if getattr(self.web_server, "_httpd", None) is None:
            try:
                self.web_server.start()
            except Exception as exc:
                logger.error("Failed to start WebConfigServer: %s", exc)
                return None

        return getattr(self.web_server, "port", None)

    def open_config(self, icon: Any = None, item: Any = None) -> None:
        """Show the config panel, starting it first if it is not up yet.

        pystray calls a menu action with (icon, item), hence the two unused
        parameters. Unlike upstream's tray action, this does not stop the
        dashboard: you can reconfigure it while it keeps refreshing.
        """
        port = self.start_config_server()
        if port is None:
            return
        webbrowser.open(f"http://127.0.0.1:{port}")

    def _init_hardware(self) -> None:
        if self.screen is not None and not self.simulate:
            try:
                self.screen.set_orientation(self.orientation, DEFAULT_SIZE[0], DEFAULT_SIZE[1])
                self.screen.set_brightness(self.brightness)
            except Exception as exc:
                logger.warning("Hardware screen initialization failed: %s", exc)

    def _setup_tray(self) -> None:
        if not self.tray_enabled:
            return
        try:
            import pystray
            icon_img = None
            if self.sprites is not None:
                try:
                    icon_img = self.sprites.frame("calma", 0)
                except Exception:
                    pass
            if icon_img is None:
                icon_img = Image.new("RGBA", (64, 64), (34, 197, 94, 255))

            menu = pystray.Menu(
                pystray.MenuItem("Configurar", self.open_config),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Salir", self.stop),
            )
            self.tray_icon = pystray.Icon("moka_tss", icon_img, "MOKA TSS", menu=menu)
            if sys.platform != "darwin":
                self.tray_icon.run_detached()
        except Exception as exc:
            logger.info("Tray icon unavailable: %s", exc)
            self.tray_icon = None

    def _run_loop(self) -> None:
        while self._running:
            self.step()
            if self._stop_event.wait(timeout=self.tick_interval):
                break

    def start_background_loop(self) -> None:
        """Start the refresh loop in a background thread."""
        self.instance_lock.acquire()
        self._running = True
        self._stop_event.clear()
        self._init_hardware()
        self._setup_tray()
        self._loop_thread = threading.Thread(target=self._run_loop, name="moka-loop", daemon=True)
        self._loop_thread.start()

    def run(self) -> None:
        """Run the main application synchronously until stopped."""
        self.instance_lock.acquire()
        self._running = True
        self._stop_event.clear()

        if threading.current_thread() is threading.main_thread():
            try:
                signal.signal(signal.SIGINT, lambda s, f: self.stop())
                signal.signal(signal.SIGTERM, lambda s, f: self.stop())
            except (ValueError, AttributeError):
                pass

        try:
            self._init_hardware()
            port = self.start_config_server()
            if port is not None:
                logger.info("Panel de configuración en http://127.0.0.1:%d", port)
                print(format_ready_line(port), flush=True)
            self._setup_tray()
            self._run_loop()
        finally:
            self.stop()

    def _stop_tray(self) -> None:
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None

    def _stop_web_server(self) -> None:
        if self.web_server is not None:
            try:
                self.web_server.stop()
            except Exception:
                pass

    def _turn_off_screen(self) -> None:
        if self.screen is not None and not self.simulate:
            try:
                port = getattr(self.screen, "serial_port", None)
                if port:
                    port.write(command_frame(Command.SCREEN_OFF, 0, 0, 0, 0))
                    port.flush()
            except Exception:
                pass

    def _close_serial_port(self) -> None:
        if self.serial_port is not None:
            try:
                self.serial_port.close()
            except Exception:
                pass

    def _join_loop_thread(self) -> None:
        if self._loop_thread is not None and self._loop_thread.is_alive():
            if threading.current_thread() != self._loop_thread:
                self._loop_thread.join(timeout=5.0)
            self._loop_thread = None

    def _release_lock(self) -> None:
        if self.instance_lock is not None:
            self.instance_lock.release()

    def stop(self, icon: Any = None, item: Any = None) -> None:
        """Clean shutdown: stop loop, web server, turn panel off, close port, join threads."""
        self._running = False
        self._stop_event.set()
        self._stop_tray()
        self._stop_web_server()
        self._turn_off_screen()
        self._close_serial_port()
        self._join_loop_thread()
        self._release_lock()


# Backwards-compatibility alias
MascotaApp = MokaApp
