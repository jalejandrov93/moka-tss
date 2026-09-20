# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays
# Mascota fork - tests for declarative theme system

"""Tests for library.mascota.theme and theme-driven rendering.

Verifies theme loading, schema validation (missing fields, unknown fields,
out-of-range fractions), orientation reflow, color parsing, and compositor
integration.
"""

import time
import unittest

from PIL import Image


from library.mascota.render import MascotSprites, render
from library.mascota.theme import (
    Theme,
    ThemeValidationError,
    load_theme,
    parse_color,
)


class StubSprites(MascotSprites):
    """Stub sprite provider for render tests."""

    def frame(self, mood, tick):
        return Image.new("RGBA", (self.SIZE, self.SIZE), (10, 20, 30, 255))

    def frame_count(self, mood):
        return 4


def fixed_clock():
    return time.strptime("2026-09-19 12:34", "%Y-%m-%d %H:%M")


def minimal_theme_dict():
    """Return a minimal valid theme dictionary for test mutations."""
    return {
        "name": "test_theme",
        "display": {
            "size": [480, 320],
            "orientation": "landscape",
        },
        "palette": {
            "background": "#0F172A",
            "panel": "#1E293B",
            "lines": "#334155",
            "text": "#F8FAFC",
            "muted": "#6E7D96",
            "accent": "#22C55E",
            "warning": "#EAB308",
            "critical": "#EF4444",
            "warning_threshold": 75.0,
            "critical_threshold": 90.0,
        },
        "fonts": {
            "candidates": ["DejaVuSansMono.ttf"],
        },
        "regions": {
            "status_bar": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.075},
            "quotas": {"x": 0.0, "y": 0.075, "width": 0.575, "height": 0.925},
            "system": {"x": 0.575, "y": 0.075, "width": 0.425, "height": 0.475},
            "mascot": {"x": 0.575, "y": 0.55, "width": 0.425, "height": 0.45},
            "jobs": {"x": 0.0, "y": 0.0, "width": 0.25, "height": 0.075},
        },
    }


class ColorParsingTests(unittest.TestCase):
    def test_parse_hex_color(self):
        self.assertEqual(parse_color("#0F172A"), (15, 23, 42))
        self.assertEqual(parse_color("#22C55E"), (34, 197, 94))

    def test_parse_rgb_tuple(self):
        self.assertEqual(parse_color([15, 23, 42]), (15, 23, 42))
        self.assertEqual(parse_color((34, 197, 94)), (34, 197, 94))

    def test_invalid_color_raises_value_error(self):
        with self.assertRaises(ValueError):
            parse_color("not_a_color")


class ThemeValidationTests(unittest.TestCase):
    def test_unknown_top_level_field_rejected(self):
        data = minimal_theme_dict()
        data["extra_unknown_field"] = "bad"
        with self.assertRaises(ThemeValidationError) as ctx:
            Theme.from_dict(data)
        err = str(ctx.exception)
        self.assertIn("test_theme", err)
        self.assertIn("extra_unknown_field", err)

    def test_unknown_nested_palette_field_rejected(self):
        data = minimal_theme_dict()
        data["palette"]["superfluous"] = "#123456"
        with self.assertRaises(ThemeValidationError) as ctx:
            Theme.from_dict(data)
        err = str(ctx.exception)
        self.assertIn("test_theme", err)
        self.assertIn("superfluous", err)

    def test_missing_required_top_level_field_rejected(self):
        data = minimal_theme_dict()
        del data["palette"]
        with self.assertRaises(ThemeValidationError) as ctx:
            Theme.from_dict(data)
        err = str(ctx.exception)
        self.assertIn("test_theme", err)
        self.assertIn("palette", err)

    def test_missing_required_display_field_rejected(self):
        data = minimal_theme_dict()
        del data["display"]["orientation"]
        with self.assertRaises(ThemeValidationError) as ctx:
            Theme.from_dict(data)
        err = str(ctx.exception)
        self.assertIn("test_theme", err)
        self.assertIn("orientation", err)

    def test_missing_required_region_rejected(self):
        data = minimal_theme_dict()
        del data["regions"]["mascot"]
        with self.assertRaises(ThemeValidationError) as ctx:
            Theme.from_dict(data)
        err = str(ctx.exception)
        self.assertIn("test_theme", err)
        self.assertIn("mascot", err)

    def test_out_of_range_fraction_negative_rejected(self):
        data = minimal_theme_dict()
        data["regions"]["status_bar"]["x"] = -0.05
        with self.assertRaises(ThemeValidationError) as ctx:
            Theme.from_dict(data)
        err = str(ctx.exception)
        self.assertIn("test_theme", err)
        self.assertIn("status_bar", err)

    def test_out_of_range_fraction_greater_than_one_rejected(self):
        data = minimal_theme_dict()
        data["regions"]["quotas"]["width"] = 1.15
        with self.assertRaises(ThemeValidationError) as ctx:
            Theme.from_dict(data)
        err = str(ctx.exception)
        self.assertIn("test_theme", err)
        self.assertIn("quotas", err)


class ThemeLoadShippedTests(unittest.TestCase):
    def test_horizontal_theme_loads_and_validates(self):
        theme = load_theme("horizontal")
        self.assertEqual(theme.name, "horizontal")
        self.assertEqual(theme.display.orientation, "landscape")
        self.assertEqual(theme.display.size, (480, 320))
        self.assertIn("status_bar", theme.regions)
        self.assertIn("quotas", theme.regions)
        self.assertIn("system", theme.regions)
        self.assertIn("mascot", theme.regions)

    def test_vertical_theme_loads_and_validates(self):
        theme = load_theme("vertical")
        self.assertEqual(theme.name, "vertical")
        self.assertEqual(theme.display.orientation, "portrait")
        self.assertEqual(theme.display.size, (320, 480))
        self.assertIn("status_bar", theme.regions)
        self.assertIn("quotas", theme.regions)
        self.assertIn("system", theme.regions)
        self.assertIn("mascot", theme.regions)

    def test_amber_theme_loads_and_validates(self):
        theme = load_theme("amber")
        self.assertEqual(theme.name, "amber")
        self.assertEqual(theme.display.orientation, "landscape")
        self.assertEqual(theme.display.size, (480, 320))
        self.assertEqual(theme.palette.text, (255, 176, 0))


class ThemeRenderTests(unittest.TestCase):
    def test_portrait_theme_renders_at_320x480_no_negative_dimensions(self):
        theme = load_theme("vertical")
        snapshot = {
            "providers": [
                {
                    "id": "claude",
                    "name": "Claude",
                    "windows": [{"usedPercent": 55.0, "label": "Session", "resetAt": "2026-09-19T10:00:00Z"}],
                    "display": {"accentColor": "#CC7C5E"},
                }
            ]
        }
        state = {"jobs": [{"status": "running"}]}
        system = {"cpu": 25.0, "ram": 50.0, "gpu": {"util": 30.0, "temp": 45.0, "vram": 20.0, "vram_used": 2048.0}}
        img = render(snapshot, state, system, theme=theme, sprites=StubSprites(), now=fixed_clock)
        self.assertEqual(img.size, (320, 480))

    def test_landscape_theme_produces_consistent_regions(self):
        theme = load_theme("horizontal")
        img = render(None, None, None, theme=theme, sprites=StubSprites(), now=fixed_clock)
        self.assertEqual(img.size, (480, 320))

    def test_na_percentage_does_not_crash_with_theme(self):
        theme = load_theme("horizontal")
        snapshot = {
            "providers": [
                {
                    "id": "claude",
                    "name": "Claude",
                    "windows": [{"usedPercent": "N/A", "label": "Session"}],
                }
            ]
        }
        img = render(snapshot, None, None, theme=theme, sprites=StubSprites(), now=fixed_clock)
        self.assertEqual(img.size, (480, 320))

    def test_missing_font_falls_back_with_theme(self):
        data = minimal_theme_dict()
        data["fonts"]["candidates"] = ["/nonexistent/fake_font_path.ttf"]
        theme = Theme.from_dict(data)
        img = render(None, None, None, theme=theme, sprites=StubSprites(), now=fixed_clock)
        self.assertEqual(img.size, (480, 320))

    def test_render_with_theme_is_pure(self):
        theme = load_theme("horizontal")
        snapshot = {
            "providers": [
                {
                    "id": "claude",
                    "name": "Claude",
                    "windows": [{"usedPercent": 40.0, "label": "Session"}],
                }
            ]
        }
        state = {"jobs": []}
        system = {"cpu": 15.0, "ram": 35.0, "gpu": None}
        img1 = render(snapshot, state, system, theme=theme, sprites=StubSprites(), now=fixed_clock)
        img2 = render(snapshot, state, system, theme=theme, sprites=StubSprites(), now=fixed_clock)
        self.assertEqual(img1.tobytes(), img2.tobytes())


if __name__ == "__main__":
    unittest.main()
