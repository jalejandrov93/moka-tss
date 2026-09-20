# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - Python system monitor for USB-C displays
# Mascota fork - host process coordination and single instance locks

"""Host environment management and single-instance locks for MOKA TSS."""

import os
import sys
from pathlib import Path
from typing import Any, Optional

from library.moka_tss.paths import user_data_dir

__all__ = ["InstanceLock", "SingleInstanceError"]


class SingleInstanceError(Exception):
    """Raised when another instance of MOKA TSS is already running."""


class InstanceLock:
    """Cross-platform single-instance file lock.

    Guarantees only one process writes to the serial port. On Windows,
    a byte-range lock on a 0-byte file succeeds for every caller, so
    a single byte is written and seeked to 0 before locking.
    """

    def __init__(self, lock_path: Optional[Path] = None):
        self.lock_path = (
            Path(lock_path)
            if lock_path is not None
            else (user_data_dir() / "moka_tss.lock")
        )
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
                msg = "Ya hay otra instancia de MOKA TSS en ejecución."
                raise SingleInstanceError(msg) from exc
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, IOError) as exc:
                handle.close()
                msg = "Ya hay otra instancia de MOKA TSS en ejecución."
                raise SingleInstanceError(msg) from exc
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
