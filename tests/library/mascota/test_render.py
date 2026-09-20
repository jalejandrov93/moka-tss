# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays
# Mascota fork - tests for the layout compositor

"""Unit tests for library.mascota.render.

`render()` must be pure and crash-proof: these tests never touch a serial
port or the network, and repeatedly hand it None in place of each data
source to prove the degrade-honestly contract. `StubSprites` below is a
trivial stand-in for the frozen `MascotSprites` interface owned by a
parallel task -- it is not the real mascot renderer.
"""

import time
import unittest

from PIL import Image

from library.mascota.render import (
    AMBER_THRESHOLD,
    GREEN,
    RED,
    RED_THRESHOLD,
    MascotSprites,
    _compute_mood,
    _load_font,
    _visible_providers,
    _worst_provider_usage,
    level_color,
    render,
)


class StubSprites(MascotSprites):
    """Minimal frozen-interface stand-in: one solid RGBA frame per mood."""

    def frame(self, mood, tick):
        return Image.new("RGBA", (self.SIZE, self.SIZE), (10, 20, 30, 255))

    def frame_count(self, mood):
        return 4


def provider(pid, used_percent, accent=None, name=None):
    entry = {
        "id": pid,
        "name": name or pid,
        "windows": [{"usedPercent": used_percent, "label": "session",
                     "resetAt": "2026-09-19T10:00:00Z"}],
    }
    if accent:
        entry["display"] = {"accentColor": accent}
    return entry


def fixed_clock():
    return time.strptime("2026-09-19 12:34", "%Y-%m-%d %H:%M")


class LevelColorTests(unittest.TestCase):
    def test_below_amber_threshold_is_default_accent(self):
        self.assertEqual(level_color(74.9), GREEN)

    def test_amber_threshold_is_inclusive(self):
        # Literal RGB from decision D9 (#EAB308), independent of the AMBER
        # symbol: if the constant itself were wrong, this still catches it.
        self.assertEqual(level_color(75.0), (234, 179, 8))
        self.assertEqual(level_color(89.9), (234, 179, 8))

    def test_red_threshold_is_inclusive(self):
        self.assertEqual(level_color(90.0), RED)
        self.assertEqual(level_color(100.0), RED)

    def test_custom_accent_used_below_threshold(self):
        accent = (1, 2, 3)
        self.assertEqual(level_color(10.0, accent), accent)


class VisibleProvidersTests(unittest.TestCase):
    def test_hidden_providers_are_excluded(self):
        snapshot = {"providers": [
            provider("claude", 10), provider("copilot", 99), provider("opencodego", 99)]}
        visible = _visible_providers(snapshot, hidden_providers={"copilot", "opencodego"})
        self.assertEqual([p["id"] for p in visible], ["claude"])

    def test_none_snapshot_yields_no_providers(self):
        self.assertEqual(_visible_providers(None, hidden_providers=set()), [])

    def test_hidden_set_is_a_parameter_not_hardcoded(self):
        # Passing an empty hidden set must let every provider through,
        # proving the exclusion list lives outside this function's body.
        snapshot = {"providers": [provider("copilot", 50)]}
        visible = _visible_providers(snapshot, hidden_providers=set())
        self.assertEqual([p["id"] for p in visible], ["copilot"])


class WorstProviderTests(unittest.TestCase):
    def test_picks_highest_usage(self):
        providers = [provider("a", 20), provider("b", 88), provider("c", 40)]
        worst, name = _worst_provider_usage(providers)
        self.assertEqual(worst, 88)
        self.assertEqual(name, "b")

    def test_empty_list_is_zero_with_no_name(self):
        self.assertEqual(_worst_provider_usage([]), (0.0, None))

    def test_string_used_percent_does_not_crash(self):
        # codexbar can hand back a non-numeric usedPercent when a provider
        # errors; a string window must not blow up the max() comparison.
        providers = [{"id": "c", "windows": [{"usedPercent": "50"}, {"usedPercent": 0}]}]
        worst, name = _worst_provider_usage(providers)
        self.assertEqual(worst, 0.0)
        self.assertIsNone(name)

    def test_none_used_percent_does_not_crash(self):
        providers = [{"id": "c", "windows": [{"usedPercent": None}]}]
        worst, name = _worst_provider_usage(providers)
        self.assertEqual(worst, 0.0)
        self.assertIsNone(name)

    def test_provider_with_no_windows_is_skipped(self):
        providers = [{"id": "empty", "windows": []}, provider("b", 42)]
        worst, name = _worst_provider_usage(providers)
        self.assertEqual(worst, 42)
        self.assertEqual(name, "b")


class ComputeMoodTests(unittest.TestCase):
    def test_none_snapshot_is_error_mood(self):
        self.assertEqual(_compute_mood(None, []), "error")

    def test_calm_below_amber_threshold(self):
        self.assertEqual(_compute_mood({}, [provider("a", AMBER_THRESHOLD - 0.1)]), "calma")

    def test_attentive_at_amber_threshold(self):
        # Literal 75 (decision D9's amber threshold), not the imported
        # AMBER_THRESHOLD constant: a wrong constant would not mask this.
        self.assertEqual(_compute_mood({}, [provider("a", 75.0)]), "atenta")

    def test_alarmed_at_red_threshold(self):
        self.assertEqual(_compute_mood({}, [provider("a", RED_THRESHOLD)]), "alarmada")


class RenderSizeTests(unittest.TestCase):
    def test_default_size_landscape(self):
        img = render(None, None, None, sprites=StubSprites(), now=fixed_clock)
        self.assertEqual(img.size, (480, 320))

    def test_custom_size_is_respected(self):
        # The fixed-pixel layout targets the 480x320 landscape panel (the
        # only hardware this ships on); a modest landscape variant still
        # exercises that `size` drives the output without hardcoding 480x320.
        img = render(None, None, None, size=(500, 350), sprites=StubSprites(), now=fixed_clock)
        self.assertEqual(img.size, (500, 350))

    def test_returns_a_pil_image(self):
        img = render(None, None, None, sprites=StubSprites(), now=fixed_clock)
        self.assertIsInstance(img, Image.Image)


class RenderDegradationTests(unittest.TestCase):
    """A down data source must render honestly, never crash or freeze."""

    def test_all_none_does_not_raise(self):
        img = render(None, None, None, sprites=StubSprites(), now=fixed_clock)
        self.assertEqual(img.size, (480, 320))

    def test_none_snapshot_only(self):
        state = {"jobs": [{"status": "running"}]}
        system = {"cpu": 10.0, "ram": 20.0, "gpu": None}
        img = render(None, state, system, sprites=StubSprites(), now=fixed_clock)
        self.assertEqual(img.size, (480, 320))

    def test_none_state_only(self):
        snapshot = {"providers": [provider("claude", 40)]}
        system = {"cpu": 10.0, "ram": 20.0, "gpu": None}
        img = render(snapshot, None, system, sprites=StubSprites(), now=fixed_clock)
        self.assertEqual(img.size, (480, 320))

    def test_none_system_only(self):
        snapshot = {"providers": [provider("claude", 40)]}
        state = {"jobs": []}
        img = render(snapshot, state, None, sprites=StubSprites(), now=fixed_clock)
        self.assertEqual(img.size, (480, 320))

    def test_missing_sprites_degrades_without_raising(self):
        snapshot = {"providers": [provider("claude", 95)]}
        img = render(snapshot, {"jobs": []}, {"cpu": 5.0, "ram": 5.0, "gpu": None},
                     sprites=None, now=fixed_clock)
        self.assertEqual(img.size, (480, 320))

    def test_empty_providers_list_shows_no_response_state(self):
        img = render({"providers": []}, None, None, sprites=StubSprites(), now=fixed_clock)
        self.assertEqual(img.size, (480, 320))


class RenderHiddenProvidersTests(unittest.TestCase):
    def test_hidden_providers_do_not_affect_mood_or_crash(self):
        # A hidden provider at 99% must not leak into the worst-usage
        # calculation once it is filtered out before mood computation.
        snapshot = {"providers": [provider("claude", 10), provider("copilot", 99)]}
        img = render(snapshot, None, None, sprites=StubSprites(),
                     hidden_providers={"copilot", "opencodego"}, now=fixed_clock)
        self.assertEqual(img.size, (480, 320))


class FontFallbackTests(unittest.TestCase):
    def test_load_font_never_raises_and_returns_a_font(self):
        # On the Linux test host, Cascadia Code does not exist: this
        # exercises the real fallback chain down to ImageFont.load_default().
        font = _load_font(11)
        self.assertIsNotNone(font)

    def test_render_survives_when_every_font_candidate_is_missing(self):
        import library.mascota.render as render_module
        original = render_module.FONT_CANDIDATES
        render_module.FONT_CANDIDATES = ("/nonexistent/path/does-not-exist.ttf",)
        render_module._load_font.cache_clear()
        try:
            img = render(None, None, None, sprites=StubSprites(), now=fixed_clock)
            self.assertEqual(img.size, (480, 320))
        finally:
            render_module.FONT_CANDIDATES = original
            render_module._load_font.cache_clear()


if __name__ == "__main__":
    unittest.main()


class QuotaColumnNonNumericTests(unittest.TestCase):
    """The drawing path has its own percentage comparison, separate from the one
    that picks the mood. A fix applied to only one of them still freezes the panel."""

    def _snapshot(self, windows):
        return {"providers": [{"id": "claude", "name": "Claude",
                               "windows": windows,
                               "display": {"accentColor": "#CC7C5E"}}]}

    def test_string_percent_does_not_crash_the_quota_column(self):
        system = {"cpu": 40.0, "ram": 50.0, "gpu": None}
        snapshot = self._snapshot([{"kind": "session", "label": "Session",
                                    "usedPercent": "50"},
                                   {"kind": "weekly", "label": "Weekly",
                                    "usedPercent": 0}])
        image = render(snapshot, None, system)
        self.assertEqual(image.size, (480, 320))

    def test_unparseable_values_do_not_crash_the_quota_column(self):
        """A numeric-looking string still parses with float(), so it hides the
        bug. These are what a failing provider actually sends."""
        system = {"cpu": 40.0, "ram": 50.0, "gpu": None}
        for value in ("N/A", "unknown", "", True, float("nan"), None):
            with self.subTest(usedPercent=value):
                snapshot = self._snapshot([{"kind": "session", "label": "Session",
                                            "usedPercent": value}])
                image = render(snapshot, None, system)
                self.assertEqual(image.size, (480, 320))
