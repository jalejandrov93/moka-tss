# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays
# Mascota fork - tests for Screen transmission stats

"""Unit tests for Screen._stats / stats_snapshot (MD-4.2)."""

import json
import unittest

from PIL import Image

from library.moka_tss.screen import Screen


class FakeSerial:
    """Minimal serial double: records written bytes."""

    def __init__(self):
        self.written = bytearray()

    def write(self, data: bytes) -> None:
        self.written += data

    def flush(self) -> None:
        pass


def _frame(color=(10, 20, 30)):
    return Image.new("RGB", (480, 320), color)


class TestScreenStats(unittest.TestCase):
    def test_initial_stats_are_zero(self):
        snap = Screen(FakeSerial()).stats_snapshot()
        self.assertEqual(
            snap,
            {
                "frames_total": 0,
                "full_frames": 0,
                "partial_frames": 0,
                "tiles_sent_total": 0,
                "bytes_sent_total": 0,
                "last_elapsed_ms": 0.0,
                "last_tiles": 0,
                "last_kind": "none",
            },
        )

    def test_first_show_is_full(self):
        screen = Screen(FakeSerial())
        elapsed, tiles, kind = screen.show(_frame())
        self.assertEqual((tiles, kind), (1, "full"))
        snap = screen.stats_snapshot()
        self.assertEqual(snap["full_frames"], 1)
        self.assertEqual(snap["partial_frames"], 0)
        self.assertEqual(snap["last_kind"], "full")
        self.assertEqual(snap["last_tiles"], 1)
        self.assertGreater(snap["bytes_sent_total"], 0)
        self.assertGreaterEqual(snap["last_elapsed_ms"], 0.0)

    def test_identical_second_show_is_empty_partial(self):
        screen = Screen(FakeSerial())
        screen.show(_frame())
        elapsed, tiles, kind = screen.show(_frame())
        self.assertEqual((tiles, kind), (0, "partial"))
        snap = screen.stats_snapshot()
        self.assertEqual(snap["partial_frames"], 1)
        self.assertEqual(snap["tiles_sent_total"], 0)
        self.assertEqual(snap["last_tiles"], 0)

    def test_changed_region_counts_tiles_and_bytes_grow(self):
        screen = Screen(FakeSerial())
        screen.show(_frame())
        before = screen.stats_snapshot()["bytes_sent_total"]
        frame2 = _frame()
        frame2.paste(Image.new("RGB", (80, 40), (200, 0, 0)), (0, 0))
        elapsed, tiles, kind = screen.show(frame2)
        self.assertEqual(kind, "partial")
        self.assertGreaterEqual(tiles, 1)
        snap = screen.stats_snapshot()
        self.assertEqual(snap["tiles_sent_total"], tiles)
        self.assertGreater(snap["bytes_sent_total"], before)

    def test_reset_preserves_stats_but_forces_full(self):
        screen = Screen(FakeSerial())
        screen.show(_frame())
        screen.reset()
        snap = screen.stats_snapshot()
        self.assertEqual(snap["full_frames"], 1)
        elapsed, tiles, kind = screen.show(_frame())
        self.assertEqual(kind, "full")
        self.assertEqual(screen.stats_snapshot()["full_frames"], 2)

    def test_snapshot_is_json_serializable_copy(self):
        screen = Screen(FakeSerial())
        screen.show(_frame())
        snap = screen.stats_snapshot()
        json.dumps(snap)
        snap["full_frames"] = 999
        self.assertNotEqual(screen.stats_snapshot()["full_frames"], 999)


if __name__ == "__main__":
    unittest.main()
