# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays
# Mascota fork - WSL distribution and path discovery for Windows host

"""WSL distribution and filesystem discovery.

On Windows, codexbar typically runs inside WSL while Mascota runs on the Windows host.
This module enumerates reachable WSL distributions and user home directories via
wsl.exe (with fallback to \\\\wsl.localhost directory listing) to locate user configs
without hardcoding distribution names or Linux usernames.
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Union

WSL_EXE = "wsl.exe"
WSL_LOCALHOST_ROOT = Path(r"\\wsl.localhost")
SUBPROCESS_TIMEOUT_SECONDS = 3.0
DEFAULT_RELATIVE_TOKEN_PATH = Path(".config") / "codexbar" / "dashboard-token"

_CACHED_WSL_CANDIDATE_PATHS: Optional[List[Path]] = None


def clear_wsl_cache() -> None:
    """Clear cached WSL discovery results (primarily for tests)."""
    global _CACHED_WSL_CANDIDATE_PATHS
    _CACHED_WSL_CANDIDATE_PATHS = None


def is_windows() -> bool:
    """Return True if running on Windows."""
    return sys.platform == "win32"


def _decode_wsl_output(raw_bytes: bytes) -> str:
    """Decode raw bytes from wsl.exe, handling UTF-16, NUL bytes, and CR."""
    if not raw_bytes:
        return ""
    for encoding in ("utf-16", "utf-16-le", "utf-8"):
        try:
            text = raw_bytes.decode(encoding)
            clean = text.replace("\x00", "").replace("\r", "")
            if clean.strip():
                return clean
        except (UnicodeDecodeError, ValueError):
            continue
    return raw_bytes.decode("utf-8", errors="replace").replace("\x00", "").replace("\r", "")


def _list_wsl_localhost_distros() -> List[str]:
    """Enumerate directory names under \\\\wsl.localhost as fallback."""
    try:
        if WSL_LOCALHOST_ROOT.is_dir():
            return [
                entry.name for entry in WSL_LOCALHOST_ROOT.iterdir()
                if entry.is_dir()
            ]
    except OSError:
        pass
    return []


def _get_wsl_user_homes(distro: str) -> List[Path]:
    """Return list of user home directory Paths under /home for a distribution."""
    home_dir = WSL_LOCALHOST_ROOT / distro / "home"
    try:
        if not home_dir.is_dir():
            return []
        homes = []
        for entry in home_dir.iterdir():
            try:
                if entry.is_dir():
                    homes.append(entry)
            except OSError:
                continue
        return homes
    except OSError:
        return []


def get_wsl_distros() -> List[str]:
    """Enumerate reachable WSL distributions.

    Runs `wsl.exe -l -q` with CREATE_NO_WINDOW and a 3.0s timeout.
    Falls back to directory listing under \\\\wsl.localhost if wsl.exe fails or times out.
    """
    if not is_windows():
        return []

    distros: List[str] = []
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        proc = subprocess.run(
            [WSL_EXE, "-l", "-q"],
            capture_output=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            creationflags=flags,
        )
        if proc.returncode == 0:
            decoded = _decode_wsl_output(proc.stdout)
            distros = [line.strip() for line in decoded.splitlines() if line.strip()]
    except (subprocess.SubprocessError, OSError):
        distros = []

    if not distros:
        distros = _list_wsl_localhost_distros()

    return distros


def find_wsl_candidate_paths(
    relative_path: Union[str, Path] = DEFAULT_RELATIVE_TOKEN_PATH
) -> List[Path]:
    """Find candidate relative paths under each user home across reachable WSL distros.

    Cached for the process lifetime so the subprocess and network probes run once.
    On non-Windows platforms, returns an empty list without probing.
    """
    if not is_windows():
        return []

    global _CACHED_WSL_CANDIDATE_PATHS
    if _CACHED_WSL_CANDIDATE_PATHS is not None:
        return list(_CACHED_WSL_CANDIDATE_PATHS)

    rel_p = Path(relative_path)
    candidates: List[Path] = []

    for distro in get_wsl_distros():
        for user_home in _get_wsl_user_homes(distro):
            candidates.append(user_home / rel_p)

    _CACHED_WSL_CANDIDATE_PATHS = candidates
    return list(candidates)


def wsl_status() -> dict:
    """Return WSL availability and discovered distros.

    Never raises: any exception during discovery is caught and results in
    `available=False` with an empty distros list.
    """
    available = is_windows()
    distros: list[str] = []
    if available:
        try:
            distros = get_wsl_distros()
        except Exception:
            available = False
            distros = []
    return {"available": available, "distros": distros}
