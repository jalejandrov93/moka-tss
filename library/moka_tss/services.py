# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays
# Mascota fork - TCP service prober

"""TCP service prober for configured services.

Probes service availability via TCP connection and measures round-trip latency.
Design MD-3.1, schema MD-3.2.
"""

import socket
import time
from typing import Any, Dict, List, Optional


def probe_service(
    host: str,
    port: int,
    timeout: float = 0.5,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """Probe a single TCP service at (host, port).

    Args:
        host: Target hostname or IP address.
        port: Target TCP port number (1-65535).
        timeout: Socket connect timeout in seconds (default: 0.5).
        name: Optional service identifier to include in result.

    Returns:
        Dict with keys:
            - 'name': (optional) string service name if provided
            - 'reachable': bool indicating connection success
            - 'latency_ms': round-trip connect latency in milliseconds (float),
              or None if unreachable/failed.
    """
    result: Dict[str, Any] = {
        "reachable": False,
        "latency_ms": None,
    }
    if name is not None:
        result["name"] = name

    if not isinstance(host, str) or not host.strip():
        return result

    if isinstance(port, bool) or not isinstance(port, int) or not (1 <= port <= 65535):
        return result

    try:
        connect_timeout = float(timeout)
        if connect_timeout <= 0:
            return result
    except (ValueError, TypeError):
        return result

    try:
        start_time = time.perf_counter()
        with socket.create_connection((host, port), timeout=connect_timeout):
            pass
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        result["reachable"] = True
        result["latency_ms"] = round(latency_ms, 2)
    except Exception:
        result["reachable"] = False
        result["latency_ms"] = None

    return result


def probe_services(
    services: List[Dict[str, Any]],
    host: str = "127.0.0.1",
    timeout: float = 0.5,
) -> List[Dict[str, Any]]:
    """Probe a list of configured services over TCP.

    Args:
        services: List of service dictionaries, each typically containing
            'name', 'port', and 'health' path.
        host: Hostname or IP to probe against (default: '127.0.0.1').
        timeout: Socket connect timeout per probe in seconds (default: 0.5).

    Returns:
        List of service dictionaries containing original fields (including
        'health' path as-is), augmented with:
            - 'reachable': bool
            - 'latency_ms': float | None
    """
    probed: List[Dict[str, Any]] = []
    if not isinstance(services, (list, tuple)):
        return probed

    for svc in services:
        if not isinstance(svc, dict):
            probed.append({
                "name": None,
                "port": None,
                "health": None,
                "reachable": False,
                "latency_ms": None,
            })
            continue

        item = dict(svc)
        port = svc.get("port")
        probe_res = probe_service(host=host, port=port, timeout=timeout)
        item["reachable"] = probe_res["reachable"]
        item["latency_ms"] = probe_res["latency_ms"]
        probed.append(item)

    return probed
