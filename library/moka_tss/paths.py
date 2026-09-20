# SPDX-License-Identifier: GPL-3.0-or-later
#
# Path resolution for the MOKA TSS dashboard, correct whether it runs from
# source, as a PyInstaller one-dir build, or as a PyInstaller one-file
# ("onefile") build.
#
# Two separate concerns live here, and they must never be mixed:
#   - resource_path() / base_dir(): READ-ONLY bundled data (rules.yaml,
#     sprites, res/docs/...). Under a onefile build this may point inside
#     sys._MEIPASS, a temp directory PyInstaller wipes on exit.
#   - user_data_dir(): the only place the app may WRITE (user-edited
#     config, logs). It must never resolve inside sys._MEIPASS, or every
#     write silently vanishes on the next restart.

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """True when running inside a PyInstaller-built executable."""
    return bool(getattr(sys, "frozen", False))


def base_dir() -> Path:
    """Directory containing the app's bundled (read-only) data.

    - Frozen one-file: sys._MEIPASS, the temp dir PyInstaller extracted to.
    - Frozen one-dir (or one-file without _MEIPASS for any reason): the
      directory containing sys.executable.
    - Running from source: the repository root.
    """
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    # library/moka_tss/paths.py -> library -> moka_tss -> repo root
    return Path(__file__).resolve().parents[2]


def resource_path(*parts: str) -> Path:
    """Path to a bundled, read-only resource, e.g.
    resource_path('res', 'moka_tss', 'rules.yaml').

    Never build this kind of path with os.getcwd() or a hardcoded
    separator: the working directory of a double-clicked .exe (or a
    shortcut with no "Start in" set) is not the app's install directory.
    """
    return base_dir().joinpath(*parts)


def user_data_dir() -> Path:
    """Directory the app may WRITE to: user-edited config, logs.

    Deliberately independent of base_dir()/resource_path(): it must never
    resolve inside sys._MEIPASS.
      - Windows: %APPDATA%\\MokaTSS (falls back to ~/AppData/Roaming/MokaTSS
        if APPDATA is unset).
      - Everywhere else: the XDG base directory spec, i.e. $XDG_DATA_HOME
        /moka-tss, falling back to ~/.local/share/moka-tss.
    """
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return root / "MokaTSS"

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    root = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
    return root / "moka-tss"

