# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays
# Mascota fork - partial-blit driver for the Turing 3.5" Revision A panel
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

"""Partial-blit driver for the Turing Smart Screen 3.5" Revision A panel.

Measured on this exact hardware (see odd/tasks/mascota.md): a full 480x320
refresh costs ~0.573s (1.75 FPS) while an 80x40 tile costs ~0.012s
(~80 FPS) -- the panel sustains a roughly constant ~524 kB/s no matter how
the payload is sliced. A full repaint is the expensive operation; a small
region is nearly free. `Screen.show()` exploits that asymmetry: it keeps
the previously sent frame and retransmits only the tiles whose bytes
changed, instead of blindly repainting all 307,200 bytes every tick.

This module reuses the wire-protocol command codes from
`library.lcd.lcd_comm_rev_a.Command` and the pixel serialization from
`library.lcd.serialize` (`image_to_RGB565`, `chunked`), but it talks to the
serial port directly rather than going through `LcdComm`/`LcdCommRevA`:
that class's constructor opens a real hardware serial port as a side
effect of instantiation, which makes it unusable with a fake serial object
in unit tests. `Screen` instead accepts any object exposing `write(bytes)`
and `flush()`.
"""

import time
from typing import List, Optional, Tuple

from PIL import Image

from library.lcd.lcd_comm_rev_a import Command
from library.lcd.serialize import chunked, image_to_RGB565

# Measured sweet spot (tools/spike/measure_throughput.py): small enough that
# a handful of changed tiles cost single-digit milliseconds, large enough
# that per-tile command overhead stays negligible.
TILE_WIDTH = 80
TILE_HEIGHT = 40

# The upstream default of 25% is nearly invisible once inverted (see
# `brightness_absolute`), so Mascota defaults brighter.
DEFAULT_BRIGHTNESS = 90


def command_frame(cmd: int, x: int, y: int, ex: int, ey: int) -> bytes:
    """Build the 6-byte Revision A command frame.

    Layout: b[0]=x>>2, b[1]=((x&3)<<6)+(y>>4), b[2]=((y&15)<<4)+(ex>>6),
    b[3]=((ex&63)<<2)+(ey>>8), b[4]=ey&255, b[5]=cmd.
    """
    buf = bytearray(6)
    buf[0] = (x >> 2) & 0xFF
    buf[1] = (((x & 3) << 6) + (y >> 4)) & 0xFF
    buf[2] = (((y & 15) << 4) + (ex >> 6)) & 0xFF
    buf[3] = (((ex & 63) << 2) + (ey >> 8)) & 0xFF
    buf[4] = ey & 0xFF
    buf[5] = cmd & 0xFF
    return bytes(buf)


def orientation_frame(orientation: int, width: int, height: int) -> bytes:
    """Build the 16-byte orientation-change frame.

    buf[5]=SET_ORIENTATION, buf[6]=orientation+100, buf[7:9]=width (big
    endian), buf[9:11]=height (big endian). Landscape is orientation=2,
    giving a 480x320 panel.
    """
    buf = bytearray(16)
    buf[5] = Command.SET_ORIENTATION
    buf[6] = (orientation + 100) & 0xFF
    buf[7] = (width >> 8) & 0xFF
    buf[8] = width & 0xFF
    buf[9] = (height >> 8) & 0xFF
    buf[10] = height & 0xFF
    return bytes(buf)


def brightness_absolute(percent: int) -> int:
    """Convert a 0-100 brightness percentage to the panel's inverted scale.

    The panel takes 0 as brightest and 255 as darkest -- the opposite of
    what "brightness" usually means. Getting this backwards cost a real
    debugging session (tools/spike/first_frame.py): the upstream default
    of 25% renders as nearly off.

    Raises ValueError (never an assert -- this ships as an optimized
    PyInstaller exe, and `python3 -O` strips asserts) so an out-of-range
    value cannot silently reach the wire as a near-invisible byte.
    """
    if not 0 <= percent <= 100:
        raise ValueError(f"brightness percent must be in [0, 100], got {percent!r}")
    return int(255 - ((percent / 100) * 255))


def image_to_rgb565le(image: Image.Image) -> bytes:
    """RGB565 little-endian bytes, vectorised via numpy (library/lcd/serialize.py)."""
    return image_to_RGB565(image, "little")


def _tile_boxes(width: int, height: int) -> List[Tuple[int, int, int, int]]:
    """Enumerate the fixed 80x40 grid of tile boxes covering (width, height)."""
    boxes = []
    for ty in range(0, height, TILE_HEIGHT):
        for tx in range(0, width, TILE_WIDTH):
            boxes.append((tx, ty, min(tx + TILE_WIDTH, width), min(ty + TILE_HEIGHT, height)))
    return boxes


class Screen:
    """Partial-blit driver: keeps the previous frame, resends only changed tiles.

    `serial_port` needs only `write(bytes)` and `flush()`; any object
    satisfying that duck-typed contract works, including a fake one in
    tests. This class never opens, closes, or auto-detects the serial
    port -- that lifecycle stays with the caller.
    """

    def __init__(self, serial_port, size: Tuple[int, int] = (480, 320)):
        self.serial_port = serial_port
        self.width, self.height = size
        self._previous: Optional[Image.Image] = None
        self._stats = {
            "frames_total": 0,
            "full_frames": 0,
            "partial_frames": 0,
            "tiles_sent_total": 0,
            "bytes_sent_total": 0,
            "last_elapsed_ms": 0.0,
            "last_tiles": 0,
            "last_kind": "none",
        }

    def set_orientation(self, orientation: int, width: int, height: int) -> None:
        """Send the 16-byte orientation frame. Landscape=2 gives 480x320."""
        self.serial_port.write(orientation_frame(orientation, width, height))
        self.serial_port.flush()

    def set_brightness(self, percent: int = DEFAULT_BRIGHTNESS) -> None:
        """Set brightness from a 0-100 percentage (inverted on the wire)."""
        level = brightness_absolute(percent)
        self.serial_port.write(command_frame(Command.SET_BRIGHTNESS, level, 0, 0, 0))
        self.serial_port.flush()

    def push(self, image: Image.Image, x: int = 0, y: int = 0) -> float:
        """Send one region unconditionally. Returns elapsed seconds."""
        data = image_to_rgb565le(image)
        w, h = image.size
        t0 = time.perf_counter()
        self.serial_port.write(command_frame(Command.DISPLAY_BITMAP, x, y, x + w - 1, y + h - 1))
        chunk_size = self.width * 8
        for chunk in chunked(data, chunk_size):
            self.serial_port.write(chunk)
        self.serial_port.flush()
        elapsed = time.perf_counter() - t0
        self._stats["frames_total"] += 1
        self._stats["bytes_sent_total"] += len(data)
        return elapsed

    def show(self, image: Image.Image) -> Tuple[float, int, str]:
        """Send only the tiles that changed since the previous frame.

        The first call after construction (or after `reset()`) has no
        previous frame to diff against, so it always sends the whole
        image and reports kind "full". Every later call reports "partial"
        and its tile count, even when that count is zero (nothing changed).

        A size change from the previous frame also forces a full repaint:
        diffing tile-by-tile against a differently-sized previous frame
        would compare against `Image.crop()`'s silent zero-padding outside
        the smaller image's bounds, which can make a fully-changed screen
        look mostly unchanged.

        Returns (elapsed_seconds, tile_count, "full" | "partial").
        """
        if self._previous is not None and self._previous.size != image.size:
            self.reset()
        if self._previous is None:
            elapsed = self.push(image)
            self._previous = image.copy()
            self._stats["full_frames"] += 1
            self._stats["last_tiles"] = 1
            self._stats["last_kind"] = "full"
            self._stats["last_elapsed_ms"] = float(elapsed * 1000)
            return elapsed, 1, "full"

        dirty = [box for box in _tile_boxes(self.width, self.height)
                 if image.crop(box).tobytes() != self._previous.crop(box).tobytes()]

        t0 = time.perf_counter()
        for box in dirty:
            self.push(image.crop(box), x=box[0], y=box[1])
        self._previous = image.copy()
        elapsed = time.perf_counter() - t0
        self._stats["partial_frames"] += 1
        self._stats["last_tiles"] = len(dirty)
        self._stats["last_kind"] = "partial"
        self._stats["tiles_sent_total"] += len(dirty)
        self._stats["last_elapsed_ms"] = float(elapsed * 1000)
        return elapsed, len(dirty), "partial"

    def reset(self) -> None:
        """Forget the previous frame, forcing the next `show()` to be full."""
        self._previous = None

    def stats_snapshot(self) -> dict:
        """Return a copy of the current transmission statistics."""
        return dict(self._stats)
