# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays
# Mascota fork - tests for the Revision A partial-blit driver

"""Unit tests for library.mascota.screen.

Every test uses a fake serial object (`FakeSerial`) that only records the
bytes it was asked to write; no real serial port is ever opened. The
regression that matters most here is `test_single_pixel_change_dirties_few_tiles`:
a one-number change in the source image must retransmit a handful of
80x40 tiles, never the whole 480x320 frame.
"""

import unittest

from PIL import Image

from library.mascota.screen import (
    DEFAULT_BRIGHTNESS,
    Screen,
    TILE_HEIGHT,
    TILE_WIDTH,
    brightness_absolute,
    command_frame,
    image_to_rgb565le,
    orientation_frame,
)


class FakeSerial:
    """Records every write, never touches a real port."""

    def __init__(self):
        self.writes = []
        self.flush_count = 0

    def write(self, data: bytes) -> None:
        self.writes.append(bytes(data))

    def flush(self) -> None:
        self.flush_count += 1


def solid_image(size, color):
    return Image.new("RGB", size, color)


class CommandFrameTests(unittest.TestCase):
    def test_six_bytes(self):
        frame = command_frame(197, 10, 20, 30, 40)
        self.assertEqual(len(frame), 6)

    def test_field_layout_matches_wire_protocol(self):
        # Hand-computed for x=479, y=319, ex=479, ey=319, cmd=197 (bottom-right
        # corner of the 480x320 panel) -- a literal, not a recomputation of
        # the production formula, so a wrong formula cannot pass this.
        frame = command_frame(197, 479, 319, 479, 319)
        self.assertEqual(list(frame), [119, 211, 247, 125, 63, 197])


class OrientationFrameTests(unittest.TestCase):
    def test_sixteen_bytes(self):
        self.assertEqual(len(orientation_frame(2, 480, 320)), 16)

    def test_landscape_frame_fields(self):
        # Hand-computed literal bytes for orientation=2 (landscape), 480x320.
        frame = orientation_frame(2, 480, 320)
        expected = [0, 0, 0, 0, 0, 121, 102, 1, 224, 1, 64, 0, 0, 0, 0, 0]
        self.assertEqual(list(frame), expected)


class BrightnessTests(unittest.TestCase):
    def test_inversion_extremes(self):
        self.assertEqual(brightness_absolute(100), 0)
        self.assertEqual(brightness_absolute(0), 255)

    def test_default_is_dim_side_when_uninverted(self):
        # The upstream default (25%) is a real, hard-won gotcha: it looks
        # nearly off once inverted, which is why Mascota defaults to 90.
        self.assertEqual(brightness_absolute(25), 191)
        self.assertEqual(DEFAULT_BRIGHTNESS, 90)
        self.assertEqual(brightness_absolute(DEFAULT_BRIGHTNESS), 25)

    def test_out_of_range_raises_a_real_exception_not_an_assert(self):
        # Asserts are stripped under `python3 -O` (this project ships as a
        # frozen PyInstaller exe, built optimized): validation must raise a
        # real exception the interpreter cannot strip, not rely on assert.
        with self.assertRaises(ValueError):
            brightness_absolute(110)
        with self.assertRaises(ValueError):
            brightness_absolute(-5)

    def test_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            brightness_absolute(101)
        with self.assertRaises(ValueError):
            brightness_absolute(-1)


class Rgb565Tests(unittest.TestCase):
    def test_pure_red_pixel_little_endian(self):
        img = Image.new("RGB", (1, 1), (255, 0, 0))
        data = image_to_rgb565le(img)
        # R=255->31 (0b11111), G=0, B=0 => 0b1111100000000000 = 0xF800
        self.assertEqual(data, (0xF800).to_bytes(2, "little"))

    def test_pure_green_pixel_little_endian(self):
        img = Image.new("RGB", (1, 1), (0, 255, 0))
        data = image_to_rgb565le(img)
        # G=255->63 (0b111111) => bits 5-10 => 0b0000011111100000 = 0x07E0
        self.assertEqual(data, (0x07E0).to_bytes(2, "little"))

    def test_pure_blue_pixel_little_endian(self):
        img = Image.new("RGB", (1, 1), (0, 0, 255))
        data = image_to_rgb565le(img)
        # B=255->31 (0b11111) => 0b0000000000011111 = 0x001F
        self.assertEqual(data, (0x001F).to_bytes(2, "little"))


class ScreenSetupTests(unittest.TestCase):
    def test_set_orientation_writes_one_frame_and_flushes(self):
        serial = FakeSerial()
        screen = Screen(serial, size=(480, 320))
        screen.set_orientation(2, 480, 320)
        self.assertEqual(serial.writes, [orientation_frame(2, 480, 320)])
        self.assertEqual(serial.flush_count, 1)

    def test_set_brightness_writes_inverted_level(self):
        # Hand-computed literal for percent=90 -> inverted level 25 -> the
        # 6-byte SET_BRIGHTNESS (cmd 110) command frame [6,64,0,0,0,110].
        serial = FakeSerial()
        screen = Screen(serial, size=(480, 320))
        screen.set_brightness(90)
        self.assertEqual(serial.writes, [bytes([6, 64, 0, 0, 0, 110])])
        self.assertEqual(serial.flush_count, 1)


class ScreenShowTests(unittest.TestCase):
    def setUp(self):
        self.size = (480, 320)
        self.total_tiles = (self.size[0] // TILE_WIDTH) * (self.size[1] // TILE_HEIGHT)

    def test_first_frame_sends_everything(self):
        serial = FakeSerial()
        screen = Screen(serial, size=self.size)
        img = solid_image(self.size, (0, 0, 0))

        elapsed, tiles, kind = screen.show(img)

        self.assertEqual(kind, "full")
        self.assertEqual(tiles, 1)
        self.assertGreaterEqual(elapsed, 0.0)
        # Exactly one DISPLAY_BITMAP command frame was issued for the whole image.
        display_bitmap_frames = [w for w in serial.writes if len(w) == 6 and w[5] == 197]
        self.assertEqual(len(display_bitmap_frames), 1)
        full_frame = command_frame(197, 0, 0, self.size[0] - 1, self.size[1] - 1)
        self.assertEqual(display_bitmap_frames[0], full_frame)

    def test_identical_second_frame_dirties_nothing(self):
        serial = FakeSerial()
        screen = Screen(serial, size=self.size)
        img = solid_image(self.size, (10, 20, 30))
        screen.show(img)
        serial.writes.clear()

        elapsed, tiles, kind = screen.show(img.copy())

        self.assertEqual(kind, "partial")
        self.assertEqual(tiles, 0)
        self.assertEqual(serial.writes, [])

    def test_single_pixel_change_dirties_few_tiles_not_the_whole_frame(self):
        """The regression that matters: a one-number change must not repaint
        the whole 480x320 frame, only the tile(s) containing that pixel."""
        serial = FakeSerial()
        screen = Screen(serial, size=self.size)
        img = solid_image(self.size, (0, 0, 0))
        screen.show(img)
        serial.writes.clear()

        changed = img.copy()
        changed.putpixel((5, 5), (255, 255, 255))  # one number, inside tile (0,0)

        elapsed, tiles, kind = screen.show(changed)

        self.assertEqual(kind, "partial")
        self.assertEqual(tiles, 1)
        self.assertLess(tiles, self.total_tiles)
        display_bitmap_frames = [w for w in serial.writes if len(w) == 6 and w[5] == 197]
        self.assertEqual(len(display_bitmap_frames), 1)
        # The dirtied region is the top-left 80x40 tile, not the full screen.
        self.assertEqual(display_bitmap_frames[0], command_frame(197, 0, 0, TILE_WIDTH - 1, TILE_HEIGHT - 1))

    def test_two_far_apart_pixel_changes_dirty_exactly_two_tiles(self):
        serial = FakeSerial()
        screen = Screen(serial, size=self.size)
        img = solid_image(self.size, (0, 0, 0))
        screen.show(img)
        serial.writes.clear()

        changed = img.copy()
        changed.putpixel((5, 5), (255, 255, 255))
        changed.putpixel((self.size[0] - 5, self.size[1] - 5), (255, 255, 255))

        _, tiles, kind = screen.show(changed)

        self.assertEqual(kind, "partial")
        self.assertEqual(tiles, 2)

    def test_image_size_change_between_shows_forces_full_repaint(self):
        # If the previous frame was a different size, diffing tile-by-tile
        # against it (via crop, which silently zero-pads) can wrongly
        # decide a fully-changed screen is mostly unchanged. A size change
        # must be treated like the very first frame: a full repaint.
        serial = FakeSerial()
        screen = Screen(serial, size=self.size)
        screen.show(solid_image(self.size, (0, 0, 0)))
        serial.writes.clear()

        smaller = solid_image((240, 160), (255, 255, 255))
        _, tiles, kind = screen.show(smaller)

        self.assertEqual(kind, "full")

    def test_reset_forces_next_show_to_be_full(self):
        serial = FakeSerial()
        screen = Screen(serial, size=self.size)
        img = solid_image(self.size, (0, 0, 0))
        screen.show(img)
        screen.reset()
        serial.writes.clear()

        _, tiles, kind = screen.show(img)

        self.assertEqual(kind, "full")
        self.assertEqual(tiles, 1)


if __name__ == "__main__":
    unittest.main()
