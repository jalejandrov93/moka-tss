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
import os
import signal
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from PIL import Image

import library.mascota.render as render_module
from library.lcd.lcd_comm_rev_a import Command
from library.mascota.paths import resource_path, user_data_dir
from library.mascota.render import (
    DEFAULT_SIZE,
    HIDDEN_PROVIDERS,
    MascotSprites,
    _visible_providers,
    _worst_provider_usage,
)
from library.mascota.rules import RuleEngine
from library.mascota.screen import DEFAULT_BRIGHTNESS, Screen, command_frame
from library.mascota.sensors_local import read_system_sensors
from library.sensors.mascota.agenthub import AgentHubClient
from library.sensors.mascota.codexbar import CodexBarClient

logger = logging.getLogger("mascota")


class SingleInstanceError(Exception):
    """Raised when another instance of Mascota is already running."""


class InstanceLock:
    """Cross-platform single-instance file lock.

    Guarantees only one process writes to the serial port. On Windows,
    a byte-range lock on a 0-byte file succeeds for every caller, so
    a single byte is written and seeked to 0 before locking.
    """

    def __init__(self, lock_path: Optional[Path] = None):
        self.lock_path = Path(lock_path) if lock_path is not None else (user_data_dir() / "mascota.lock")
        self._file = None

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.lock_path, "a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)

        if sys.platform == "win32":
            import msvcrt
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except (OSError, IOError) as exc:
                handle.close()
                raise SingleInstanceError("Ya hay otra instancia de Mascota en ejecución.") from exc
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, IOError) as exc:
                handle.close()
                raise SingleInstanceError("Ya hay otra instancia de Mascota en ejecución.") from exc
        self._file = handle

    def release(self) -> None:
        if self._file is not None:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    self._file.seek(0)
                    msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
            except (OSError, IOError):
                pass
            finally:
                try:
                    self._file.close()
                except (OSError, IOError):
                    pass
                self._file = None

    def __enter__(self) -> "InstanceLock":
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()


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


class MascotaApp:
    """Main application coordinator for the Turing Smart Screen dashboard."""

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
        self.agenthub_available = False
        self.codexbar_available = False

        self._last_sensors_time = -1e9
        self._last_agenthub_time = -1e9
        self._last_codexbar_time = -1e9

    def _load_default_rule_engine(self) -> RuleEngine:
        rules_path = resource_path("res", "mascota", "rules.yaml")
        if rules_path.is_file():
            return RuleEngine.from_yaml_file(rules_path)
        return RuleEngine.from_dict({"moods": ["calma"], "default_mood": "calma", "rules": []})

    def _load_default_sprites(self) -> Optional[MascotSprites]:
        sprites_dir = resource_path("res", "mascota", "sprites")
        try:
            from library.mascota.mascot import MascotSprites as RealMascotSprites
            return RealMascotSprites.load(sprites_dir)
        except Exception as exc:
            logger.warning("Failed to load mascot sprites from %s: %s", sprites_dir, exc)
            return None

    def _get_status(self) -> Dict[str, Any]:
        return {
            "tick": self.tick_count,
            "agenthub_available": self.agenthub_available,
            "codexbar_available": self.codexbar_available,
            "running": self._running,
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
        except Exception as exc:
            logger.error("Rendering failed: %s", exc)
            frame = Image.new("RGB", DEFAULT_SIZE, (15, 23, 42))

        if self.simulate:
            try:
                self.simulate_output_path.parent.mkdir(parents=True, exist_ok=True)
                frame.save(self.simulate_output_path)
            except Exception as exc:
                logger.warning("Failed to save simulation frame: %s", exc)
            if self.screen is not None:
                try:
                    self.screen.show(frame)
                except Exception as exc:
                    logger.warning("Screen show failed in simulation: %s", exc)
        elif self.screen is not None:
            self.screen.show(frame)

    def step(self) -> None:
        """Execute one refresh cycle: poll sources according to cadence, evaluate rules, and render."""
        now = self._clock()
        self._poll_local_sensors(now)
        self._poll_agenthub(now)
        self._poll_codexbar(now)
        metrics = self._collect_rule_metrics()
        mood = self._evaluate_mood(metrics)
        self._render_and_output(mood)
        self.tick_count += 1

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
                from library.mascota.webconfig import WebConfigServer
                self.web_server = WebConfigServer(status_provider=self._get_status)
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
            self.tray_icon = pystray.Icon("mascota", icon_img, "Mascota", menu=menu)
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
        self._loop_thread = threading.Thread(target=self._run_loop, name="mascota-loop", daemon=True)
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
