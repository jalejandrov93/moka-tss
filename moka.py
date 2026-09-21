# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays
# Mascota fork - entry point

"""Command-line entry point for Project MOKA TSS."""

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments for MOKA TSS."""
    parser = argparse.ArgumentParser(
        description="MOKA TSS: dashboard reactivo para Turing Smart Screen 3.5\""
    )
    parser.add_argument(
        "--tick",
        type=float,
        default=2.0,
        help="Intervalo de refresco en segundos (default: 2.0)",
    )
    parser.add_argument(
        "--brightness",
        type=int,
        default=85,
        help="Brillo de pantalla de 0 a 100 (default: 85)",
    )
    parser.add_argument(
        "--port",
        type=str,
        default="COM3",
        help="Puerto serie del panel (default: COM3)",
    )
    parser.add_argument(
        "--no-tray",
        action="store_true",
        help="Deshabilitar el ícono de bandeja del sistema",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Modo simulación: guarda capturas en screencap.png sin hardware",
    )
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Generate a JSON diagnostic report and exit",
    )
    return parser.parse_args(argv)


def _run_diagnostics(args: argparse.Namespace) -> None:
    import json
    import socket
    import importlib

    def check_port(p: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", p), timeout=0.5):
                return True
        except OSError:
            return False

    def check_import(m: str) -> bool:
        try:
            importlib.import_module(m)
            return True
        except ImportError:
            return False

    snapshot = {}
    try:
        from library.moka_tss.app import MokaApp

        class MockObj:
            value = None
            available = False

        class MockClient:
            def get_state(self):
                return MockObj()

            def get_snapshot(self):
                return None, None, False

        dummy_app = MokaApp(
            serial_port=None,
            tick_interval=args.tick,
            brightness=args.brightness,
            tray_enabled=False,
            simulate=True,
            simulate_output_path=Path("screencap.png"),
            read_sensors=lambda: {},
            agenthub_client=MockClient(),
            codexbar_client=MockClient(),
            rule_engine=None,
            sprites=None,
            renderer=lambda *a, **k: None,
        )
        snapshot = dummy_app.status_snapshot()
    except Exception as exc:
        snapshot = {"error": str(exc)}

    report = {
        "app_name": "MOKA TSS",
        "python_version": sys.version,
        "args": {
            "tick_interval": args.tick,
            "brightness": args.brightness,
            "port": args.port,
        },
        "status_snapshot": snapshot,
        "config_files": {
            "config.yaml": Path("config.yaml").exists(),
            "res/moka_tss/rules.yaml": Path("res/moka_tss/rules.yaml").exists(),
            "res/moka_tss/webconfig.json": Path("res/moka_tss/webconfig.json").exists(),
        },
        "ports": {
            "codexbar": check_port(8787),
            "agenthub": check_port(7777),
            "panel": check_port(8765),
        },
        "imports": {
            "library.moka_tss.host": check_import("library.moka_tss.host"),
            "library.moka_tss.app": check_import("library.moka_tss.app"),
            "library.moka_tss.render": check_import("library.moka_tss.render"),
            "library.moka_tss.rules": check_import("library.moka_tss.rules"),
            "library.moka_tss.screen": check_import("library.moka_tss.screen"),
        }
    }

    print(json.dumps(report, indent=2))


def main(argv: Optional[List[str]] = None) -> None:
    """Main application entry point."""
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%m/%d/%y %H:%M:%S",
    )
    logger = logging.getLogger("moka_tss")

    if args.diagnostics:
        _run_diagnostics(args)
        return

    serial_port = None

    if not args.simulate:
        try:
            import serial
            serial_port = serial.Serial(args.port, 115200, timeout=1, rtscts=True)
        except Exception as exc:
            logger.error("No se pudo abrir el puerto serie %s: %s", args.port, exc)
            sys.exit(1)

    from library.moka_tss.app import MokaApp, SingleInstanceError

    app = MokaApp(
        serial_port=serial_port,
        tick_interval=args.tick,
        brightness=args.brightness,
        tray_enabled=not args.no_tray,
        simulate=args.simulate,
        simulate_output_path=Path("screencap.png"),
    )

    try:
        app.run()
    except SingleInstanceError as exc:
        logger.error(str(exc))
        sys.exit(1)
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()


if __name__ == "__main__":
    main()
