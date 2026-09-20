# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays
# Mascota fork - local system sensor collection

"""Local system sensor collection using psutil and nvidia-smi.

Collects CPU, RAM, and GPU metrics without requiring administrator privileges
(decision D11 in odd/tasks/mascota.md).
"""

import subprocess
from typing import Any, Callable, Dict, Optional

import psutil


def get_cpu_percent() -> Optional[float]:
    """Return CPU utilization percentage (0.0 - 100.0) or None if unavailable."""
    try:
        val = psutil.cpu_percent(interval=None)
        return float(val)
    except Exception:
        return None


def get_ram_percent() -> Optional[float]:
    """Return RAM utilization percentage (0.0 - 100.0) or None if unavailable."""
    try:
        val = psutil.virtual_memory().percent
        return float(val)
    except Exception:
        return None


def get_cpu_temp() -> Optional[float]:
    """Return CPU temperature in degrees Celsius or None if unavailable.

    psutil.sensors_temperatures() is available on Linux and FreeBSD,
    but not on Windows without administrator/kernel drivers.
    """
    try:
        temps_fn = getattr(psutil, "sensors_temperatures", None)
        if callable(temps_fn):
            temps = temps_fn()
            if temps:
                for entries in temps.values():
                    for entry in entries:
                        current = getattr(entry, "current", None)
                        if current is not None and current > 0:
                            return float(current)
    except Exception:
        pass
    return None


def get_gpu_info(runner: Callable[..., Any] = subprocess.run) -> Optional[Dict[str, float]]:
    """Return GPU utilization, temperature and VRAM via nvidia-smi.

    Returns None if nvidia-smi is not found, returns an error, or if output cannot be parsed.
    Guards with CREATE_NO_WINDOW so no console window flashes on Windows.
    """
    cmd = [
        "nvidia-smi",
        "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        res = runner(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2.0,
            creationflags=creationflags,
        )
        if res.returncode != 0 or not res.stdout:
            return None
        line = res.stdout.strip().splitlines()[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            return None
        util = float(parts[0])
        temp = float(parts[1])
        vram_used = float(parts[2])
        vram_total = float(parts[3])
        vram_pct = (vram_used / vram_total * 100.0) if vram_total > 0 else 0.0
        return {
            "util": util,
            "temp": temp,
            "vram": vram_pct,
            "vram_used": vram_used,
            "vram_total": vram_total,
        }
    except Exception:
        return None


def read_system_sensors(runner: Callable[..., Any] = subprocess.run) -> Dict[str, Any]:
    """Collect all local system sensors into a dictionary matching render expectations."""
    return {
        "cpu": get_cpu_percent(),
        "ram": get_ram_percent(),
        "gpu": get_gpu_info(runner=runner),
        "cpu_temp": get_cpu_temp(),
    }
