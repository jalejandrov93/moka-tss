# SPDX-License-Identifier: GPL-3.0-or-later
#
# Tests for the mascot sprite/animation state machine (library/mascota/mascot.py).
#
# All tests run against the committed frames under res/mascota/sprites/ --
# no network access, no on-the-fly asset generation. See CREDITS.md there
# for provenance and license of the source art.

import unittest
from pathlib import Path

from PIL import Image

from library.moka_tss.mascot import MascotSprites

REPO_ROOT = Path(__file__).resolve().parents[3]
ASSETS_DIR = REPO_ROOT / "res" / "moka_tss" / "sprites"


class LoadTests(unittest.TestCase):
    def test_moods_constant_matches_rule_engine_contract(self):
        self.assertEqual(
            MascotSprites.MOODS,
            ("durmiendo", "calma", "atenta", "agobiada", "alarmada", "error"),
        )

    def test_size_constant_is_96(self):
        self.assertEqual(MascotSprites.SIZE, 96)

    def test_load_with_default_assets_dir_succeeds(self):
        sprites = MascotSprites.load()
        self.assertIsInstance(sprites, MascotSprites)

    def test_load_with_explicit_assets_dir_succeeds(self):
        sprites = MascotSprites.load(ASSETS_DIR)
        self.assertIsInstance(sprites, MascotSprites)

    def test_load_with_string_assets_dir_succeeds(self):
        sprites = MascotSprites.load(str(ASSETS_DIR))
        self.assertIsInstance(sprites, MascotSprites)

    def test_missing_assets_dir_raises_at_load_time(self):
        missing = ASSETS_DIR / "does-not-exist"
        with self.assertRaises(Exception):
            MascotSprites.load(missing)


class FrameTests(unittest.TestCase):
    def setUp(self):
        self.sprites = MascotSprites.load(ASSETS_DIR)

    def test_every_mood_returns_a_valid_frame(self):
        for mood in MascotSprites.MOODS:
            frame = self.sprites.frame(mood, 0)
            self.assertIsInstance(frame, Image.Image)
            self.assertEqual(frame.size, (96, 96))
            self.assertEqual(frame.mode, "RGBA")

    def test_frame_count_at_least_one_for_every_mood(self):
        for mood in MascotSprites.MOODS:
            self.assertGreaterEqual(self.sprites.frame_count(mood), 1)

    def test_unknown_mood_falls_back_to_calma(self):
        fallback = self.sprites.frame("calma", 0)
        unknown = self.sprites.frame("no-existe", 0)
        self.assertEqual(list(unknown.getdata()), list(fallback.getdata()))

    def test_unknown_mood_never_raises(self):
        try:
            self.sprites.frame("", 0)
            self.sprites.frame(None, 0)
            self.sprites.frame(123, 0)
        except Exception as exc:  # pragma: no cover - failure path
            self.fail(f"frame() raised for an unknown mood: {exc!r}")

    def test_tick_wraps_around_frame_count(self):
        for mood in MascotSprites.MOODS:
            count = self.sprites.frame_count(mood)
            first = self.sprites.frame(mood, 0)
            wrapped = self.sprites.frame(mood, count)
            self.assertEqual(list(first.getdata()), list(wrapped.getdata()))

    def test_large_tick_does_not_raise_and_matches_modulo(self):
        big_tick = 10 ** 9
        for mood in MascotSprites.MOODS:
            count = self.sprites.frame_count(mood)
            expected = self.sprites.frame(mood, big_tick % count)
            actual = self.sprites.frame(mood, big_tick)
            self.assertEqual(list(expected.getdata()), list(actual.getdata()))

    def test_frames_are_precomputed_and_cached_not_reloaded_per_call(self):
        for mood in MascotSprites.MOODS:
            count = self.sprites.frame_count(mood)
            first_call = self.sprites.frame(mood, 0)
            second_call = self.sprites.frame(mood, count)
            # Same cached object, not a fresh decode from disk each time.
            self.assertIs(first_call, second_call)

    def test_alarmada_and_agobiada_are_visually_distinct(self):
        agobiada = self.sprites.frame("agobiada", 0)
        alarmada = self.sprites.frame("alarmada", 0)
        self.assertNotEqual(list(agobiada.getdata()), list(alarmada.getdata()))

    def test_error_mood_is_visually_distinct_from_calma(self):
        calma = self.sprites.frame("calma", 0)
        error = self.sprites.frame("error", 0)
        self.assertNotEqual(list(calma.getdata()), list(error.getdata()))


def _silhouette(image):
    """Set of opaque pixel coordinates: the sprite's outline, ignoring color."""
    return {
        (x, y)
        for x in range(image.width)
        for y in range(image.height)
        if image.getpixel((x, y))[3] > 0
    }


def _silhouette_difference_ratio(a, b):
    """Fraction of the union of two silhouettes that is NOT shared by both.

    0.0 means identical outlines (only color could differ); 1.0 means no
    overlap at all. A mood distinguished by tint alone scores near 0.0 here.
    """
    silhouette_a, silhouette_b = _silhouette(a), _silhouette(b)
    union = silhouette_a | silhouette_b
    if not union:
        return 0.0
    symmetric_difference = silhouette_a ^ silhouette_b
    return len(symmetric_difference) / len(union)


class SilhouetteDistinctionTests(unittest.TestCase):
    """A mood must be recognizable by its OUTLINE, not only by its tint --
    otherwise the sprite reads as one blob with a color-coded status light.
    Each pair below is required to differ in shape by a real margin.
    """

    MIN_DIFFERENCE_RATIO = 0.15

    def setUp(self):
        self.sprites = MascotSprites.load(ASSETS_DIR)

    def _assert_distinct_silhouettes(self, mood_a, mood_b):
        frame_a = self.sprites.frame(mood_a, 0)
        frame_b = self.sprites.frame(mood_b, 0)
        ratio = _silhouette_difference_ratio(frame_a, frame_b)
        self.assertGreaterEqual(
            ratio, self.MIN_DIFFERENCE_RATIO,
            f"'{mood_a}' and '{mood_b}' share essentially the same outline "
            f"(difference ratio {ratio:.2f}); they must differ in pose, not "
            f"only in tint.",
        )

    def test_calma_and_atenta_differ_in_outline(self):
        self._assert_distinct_silhouettes("calma", "atenta")

    def test_calma_and_agobiada_differ_in_outline(self):
        self._assert_distinct_silhouettes("calma", "agobiada")

    def test_calma_and_alarmada_differ_in_outline(self):
        self._assert_distinct_silhouettes("calma", "alarmada")

    def test_agobiada_and_alarmada_differ_in_outline(self):
        self._assert_distinct_silhouettes("agobiada", "alarmada")

    def test_durmiendo_and_calma_differ_in_outline(self):
        self._assert_distinct_silhouettes("durmiendo", "calma")


class LoadVariantTests(unittest.TestCase):
    """Tests for the MascotSprites.load_variant class method."""

    def test_nonexistent_variant_returns_same_moods_as_base(self):
        """A variant that doesn't exist as a directory falls back to base load()."""
        sprites = MascotSprites.load_variant("no-such-variant")
        self.assertIsInstance(sprites, MascotSprites)
        # Should have the same MOODS as the base class
        self.assertEqual(sprites.MOODS, MascotSprites.MOODS)

    def test_invalid_name_with_dotdot_raises(self):
        """Name containing '..' raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            MascotSprites.load_variant("..")

    def test_invalid_name_with_slash_raises(self):
        """Name containing '/' raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            MascotSprites.load_variant("a/b")

    def test_invalid_name_with_uppercase_raises(self):
        """Name containing uppercase letters raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            MascotSprites.load_variant("A B")

    def test_invalid_name_empty_raises(self):
        """Empty name raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            MascotSprites.load_variant("")

    def test_invalid_name_with_special_chars_raises(self):
        """Name with characters outside [a-z0-9_-] raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            MascotSprites.load_variant("variant@name")
        with self.assertRaises(FileNotFoundError):
            MascotSprites.load_variant("variant.name")


if __name__ == "__main__":
    unittest.main()
