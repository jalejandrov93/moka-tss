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

from library.moka_tss.app import MokaApp, SingleInstanceError


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
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    """Main application entry point."""
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%m/%d/%y %H:%M:%S",
    )
    logger = logging.getLogger("moka_tss")

    serial_port = None
    if not args.simulate:
        try:
            import serial
            serial_port = serial.Serial(args.port, 115200, timeout=1, rtscts=True)
        except Exception as exc:
            logger.error("No se pudo abrir el puerto serie %s: %s", args.port, exc)
            sys.exit(1)

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
