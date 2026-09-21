# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays
# Mascota fork - declarative theme system and schema validation

"""Declarative theme system for the Mascota dashboard compositor.

Schema Design Decision:
We intentionally define our own declarative theme schema rather than extending
upstream's theme schema (`res/themes/*/theme.yaml`).

Upstream's schema is tightly coupled to `library/stats.py` and its widget model
(CPU/RAM/GPU/DISK/NET graphs and text placed at fixed pixel coordinates). That
model works for monolithic system monitors with fixed background images, but it
is fundamentally unsuited to Mascota:
1. Mascota renders a reactive, multi-source dashboard containing dynamic agent
   quotas with reset timestamps and accent colors, live agent-hub job counters,
   local hardware sensors, and an animated pixel-art mascot whose mood is
   driven by alert rules.
2. Mascota requires real orientation support (landscape 480x320 and portrait
   320x480) with dynamic reflow. Upstream's absolute pixel coordinates break
   completely when the orientation changes (e.g. producing negative bar widths).
3. Defining our own declarative schema with fractional coordinates (0.0 to 1.0)
   allows regions to reflow cleanly across resolutions and orientations.
4. Strict load-time schema validation ensures that any missing or malformed
   fields fail immediately with informative error messages naming the theme and
   field, preventing runtime freezes on the display panel.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple, Union

import yaml


# Required top-level keys for a valid theme
REQUIRED_TOP_LEVEL = ("name", "display", "palette", "fonts", "regions")
ALLOWED_TOP_LEVEL = {
    "name", "display", "palette", "fonts", "regions", "separators",
    "author", "description", "version", "background", "system",
}

REQUIRED_DISPLAY = ("size", "orientation")
ALLOWED_DISPLAY = {"size", "orientation"}

REQUIRED_PALETTE = (
    "background", "panel", "text", "muted", "accent",
    "warning", "critical", "warning_threshold", "critical_threshold",
)
ALLOWED_PALETTE = {
    "background", "panel", "lines", "line", "text", "muted", "accent",
    "warning", "critical", "warning_threshold", "critical_threshold",
}

REQUIRED_REGIONS = ("status_bar", "quotas", "system", "mascot", "jobs")
ALLOWED_REGION_KEYS = {"x", "y", "width", "height"}
ALLOWED_SEPARATOR_KEYS = {"x1", "y1", "x2", "y2"}


class ThemeValidationError(ValueError):
    """Raised when a theme configuration fails validation at load time."""
    pass


def parse_color(value: Union[str, Sequence[int]]) -> Tuple[int, int, int]:
    """Parse a hex color string ('#RRGGBB') or RGB sequence into an (R, G, B) tuple."""
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return (int(value[0]), int(value[1]), int(value[2]))
    if isinstance(value, str):
        v = value.strip().lstrip("#")
        if len(v) == 6:
            try:
                return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))
            except ValueError:
                pass
    raise ValueError(f"Invalid color value: {value!r}")


@dataclass(frozen=True)
class DisplayConfig:
    size: Tuple[int, int]
    orientation: str


@dataclass(frozen=True)
class PaletteConfig:
    background: Tuple[int, int, int]
    panel: Tuple[int, int, int]
    lines: Tuple[int, int, int]
    text: Tuple[int, int, int]
    muted: Tuple[int, int, int]
    accent: Tuple[int, int, int]
    warning: Tuple[int, int, int]
    critical: Tuple[int, int, int]
    warning_threshold: float
    critical_threshold: float


@dataclass(frozen=True)
class FontsConfig:
    candidates: Tuple[str, ...]


@dataclass(frozen=True)
class RegionConfig:
    x: float
    y: float
    width: float
    height: float

    def resolve(self, canvas_size: Tuple[int, int]) -> Tuple[int, int, int, int]:
        """Convert fractional bounds to pixel coordinates (rx, ry, rw, rh)."""
        cw, ch = canvas_size
        rx = int(round(self.x * cw))
        ry = int(round(self.y * ch))
        rw = int(round(self.width * cw))
        rh = int(round(self.height * ch))
        return rx, ry, rw, rh


@dataclass(frozen=True)
class SeparatorConfig:
    x1: float
    y1: float
    x2: float
    y2: float

    def resolve(self, canvas_size: Tuple[int, int]) -> Tuple[int, int, int, int]:
        """Convert fractional separator line to pixel coordinates (x1, y1, x2, y2)."""
        cw, ch = canvas_size
        return (
            int(round(self.x1 * cw)),
            int(round(self.y1 * ch)),
            int(round(self.x2 * cw)),
            int(round(self.y2 * ch)),
        )


@dataclass(frozen=True)
class BackgroundConfig:
    path: str
    fit: str = "cover"          # cover | contain | stretch
    darken: float = 0.0         # 0.0 to 1.0


@dataclass(frozen=True)
class QuotasSystemConfig:
    providers: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SystemConfig:
    sensors: Tuple[str, ...] = ("cpu", "gpu", "ram", "vram")
    quotas: QuotasSystemConfig = QuotasSystemConfig()


@dataclass(frozen=True)
class Theme:
    name: str
    display: DisplayConfig
    palette: PaletteConfig
    fonts: FontsConfig
    regions: Dict[str, RegionConfig]
    separators: Tuple[SeparatorConfig, ...] = ()
    background: Optional[BackgroundConfig] = None
    system: SystemConfig = SystemConfig()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Theme":
        name = str(data.get("name", "unnamed"))
        _validate_keys(name, data, REQUIRED_TOP_LEVEL, ALLOWED_TOP_LEVEL, "top-level")

        return cls(
            name=name,
            display=_build_display_config(name, data["display"]),
            palette=_build_palette_config(name, data["palette"]),
            fonts=_build_fonts_config(name, data["fonts"]),
            regions=_validate_and_build_regions(name, data["regions"]),
            separators=_validate_and_build_separators(name, data.get("separators", [])),
            background=_build_background_config(name, data.get("background")),
            system=_build_system_config(name, data.get("system")),
        )


def _build_display_config(name: str, disp: Any) -> DisplayConfig:
    if not isinstance(disp, dict):
        raise ThemeValidationError(f"Theme '{name}': display must be a dictionary")
    _validate_keys(name, disp, REQUIRED_DISPLAY, ALLOWED_DISPLAY, "display")

    size_raw = disp["size"]
    if not isinstance(size_raw, (list, tuple)) or len(size_raw) != 2:
        raise ThemeValidationError(f"Theme '{name}': display.size must be a pair of integers")
    size = (int(size_raw[0]), int(size_raw[1]))
    if size[0] <= 0 or size[1] <= 0:
        raise ThemeValidationError(f"Theme '{name}': display.size dimensions must be positive")

    orientation = str(disp["orientation"]).lower()
    if orientation not in ("landscape", "portrait"):
        raise ThemeValidationError(f"Theme '{name}': display.orientation must be 'landscape' or 'portrait'")

    return DisplayConfig(size=size, orientation=orientation)


def _build_palette_config(name: str, pal: Any) -> PaletteConfig:
    if not isinstance(pal, dict):
        raise ThemeValidationError(f"Theme '{name}': palette must be a dictionary")
    _validate_keys(name, pal, REQUIRED_PALETTE, ALLOWED_PALETTE, "palette")

    lines_val = pal.get("lines") if "lines" in pal else pal.get("line")
    if lines_val is None:
        raise ThemeValidationError(f"Theme '{name}': missing required field 'lines' in palette")

    try:
        return PaletteConfig(
            background=parse_color(pal["background"]),
            panel=parse_color(pal["panel"]),
            lines=parse_color(lines_val),
            text=parse_color(pal["text"]),
            muted=parse_color(pal["muted"]),
            accent=parse_color(pal["accent"]),
            warning=parse_color(pal["warning"]),
            critical=parse_color(pal["critical"]),
            warning_threshold=float(pal["warning_threshold"]),
            critical_threshold=float(pal["critical_threshold"]),
        )
    except (ValueError, TypeError) as exc:
        raise ThemeValidationError(f"Theme '{name}': invalid palette value: {exc}") from exc


def _build_fonts_config(name: str, fnt: Any) -> FontsConfig:
    if not isinstance(fnt, dict):
        raise ThemeValidationError(f"Theme '{name}': fonts must be a dictionary")
    _validate_keys(name, fnt, ("candidates",), {"candidates"}, "fonts")
    candidates = fnt["candidates"]
    if not isinstance(candidates, (list, tuple)):
        raise ThemeValidationError(f"Theme '{name}': fonts.candidates must be a list of font paths")
    return FontsConfig(candidates=tuple(str(c) for c in candidates))


def _build_background_config(name: str, bg: Any) -> Optional[BackgroundConfig]:
    if bg is None:
        return None
    if not isinstance(bg, dict):
        raise ThemeValidationError(f"Theme '{name}': background must be a dictionary")

    allowed_bg_keys = {"path", "fit", "darken"}
    for k in bg:
        if k not in allowed_bg_keys:
            raise ThemeValidationError(f"Theme '{name}': unknown field '{k}' in background")

    if "path" not in bg:
        raise ThemeValidationError(f"Theme '{name}': missing required field 'path' in background")
    path = str(bg["path"])

    fit = str(bg.get("fit", "cover")).lower()
    if fit not in ("cover", "contain", "stretch"):
        raise ThemeValidationError(f"Theme '{name}': background.fit must be 'cover', 'contain', or 'stretch'")

    try:
        darken = float(bg.get("darken", 0.0))
    except (ValueError, TypeError) as exc:
        raise ThemeValidationError(f"Theme '{name}': background.darken must be a number") from exc
    if darken < 0.0 or darken > 1.0:
        raise ThemeValidationError(f"Theme '{name}': background.darken must be between 0.0 and 1.0")

    return BackgroundConfig(path=path, fit=fit, darken=darken)


def _build_system_config(name: str, sys: Any) -> SystemConfig:
    if sys is None:
        return SystemConfig()
    if not isinstance(sys, dict):
        raise ThemeValidationError(f"Theme '{name}': system must be a dictionary")

    allowed_sys_keys = {"sensors", "quotas"}
    for k in sys:
        if k not in allowed_sys_keys:
            raise ThemeValidationError(f"Theme '{name}': unknown field '{k}' in system")

    # Parse sensors
    sensors_raw = sys.get("sensors", ["cpu", "gpu", "ram", "vram"])
    if not isinstance(sensors_raw, (list, tuple)):
        raise ThemeValidationError(f"Theme '{name}': system.sensors must be a list of strings")
    sensors = tuple(str(s) for s in sensors_raw)

    # Parse quotas.providers
    quotas_raw = sys.get("quotas", {})
    if not isinstance(quotas_raw, dict):
        raise ThemeValidationError(f"Theme '{name}': system.quotas must be a dictionary")
    providers_raw = quotas_raw.get("providers", [])
    if not isinstance(providers_raw, (list, tuple)):
        raise ThemeValidationError(f"Theme '{name}': system.quotas.providers must be a list of strings")
    providers = tuple(str(p) for p in providers_raw)

    return SystemConfig(
        sensors=sensors,
        quotas=QuotasSystemConfig(providers=providers),
    )


def _validate_keys(theme_name: str, data: dict, required: Sequence[str], allowed: set, context: str) -> None:

    for k in data:
        if k not in allowed:
            raise ThemeValidationError(f"Theme '{theme_name}': unknown field '{k}' in {context}")
    for req in required:
        if req not in data:
            raise ThemeValidationError(f"Theme '{theme_name}': missing required field '{req}' in {context}")


def _validate_region(theme_name: str, reg_name: str, reg: Any) -> RegionConfig:
    if not isinstance(reg, dict):
        raise ThemeValidationError(f"Theme '{theme_name}': region '{reg_name}' must be a dictionary")
    for k in reg:
        if k not in ALLOWED_REGION_KEYS:
            raise ThemeValidationError(f"Theme '{theme_name}': unknown field '{k}' in region '{reg_name}'")
    for k in ("x", "y", "width", "height"):
        if k not in reg:
            raise ThemeValidationError(f"Theme '{theme_name}': missing required field '{k}' in region '{reg_name}'")
        val = reg[k]
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            raise ThemeValidationError(f"Theme '{theme_name}': field '{reg_name}.{k}' must be a number")
        val = float(val)
        if val < 0.0 or val > 1.0:
            raise ThemeValidationError(
                f"Theme '{theme_name}': out-of-range fraction in field '{reg_name}.{k}' ({val})"
            )

    x, y, w, h = float(reg["x"]), float(reg["y"]), float(reg["width"]), float(reg["height"])
    if x + w > 1.0001:
        raise ThemeValidationError(
            f"Theme '{theme_name}': out-of-range fraction in field '{reg_name}.width' (extends past canvas)"
        )
    if y + h > 1.0001:
        raise ThemeValidationError(
            f"Theme '{theme_name}': out-of-range fraction in field '{reg_name}.height' (extends past canvas)"
        )
    return RegionConfig(x=x, y=y, width=w, height=h)


def _validate_and_build_regions(theme_name: str, regions_data: Any) -> Dict[str, RegionConfig]:
    if not isinstance(regions_data, dict):
        raise ThemeValidationError(f"Theme '{theme_name}': regions must be a dictionary")

    aliases = {
        "quota_list": "quotas",
        "system_panel": "system",
        "job_list": "jobs",
    }
    canonical_data = {aliases.get(k, k): v for k, v in regions_data.items()}

    for req in REQUIRED_REGIONS:
        if req not in canonical_data:
            raise ThemeValidationError(f"Theme '{theme_name}': missing required region '{req}'")

    return {
        reg_name: _validate_region(theme_name, reg_name, reg)
        for reg_name, reg in canonical_data.items()
    }


def _validate_and_build_separators(theme_name: str, seps_data: Any) -> Tuple[SeparatorConfig, ...]:

    if not isinstance(seps_data, (list, tuple)):
        raise ThemeValidationError(f"Theme '{theme_name}': separators must be a list")
    result = []
    for i, sep in enumerate(seps_data):
        if not isinstance(sep, dict):
            raise ThemeValidationError(f"Theme '{theme_name}': separator #{i} must be a dictionary")
        for k in sep:
            if k not in ALLOWED_SEPARATOR_KEYS:
                raise ThemeValidationError(f"Theme '{theme_name}': unknown field '{k}' in separator #{i}")
        for k in ("x1", "y1", "x2", "y2"):
            if k not in sep:
                raise ThemeValidationError(f"Theme '{theme_name}': missing required field '{k}' in separator #{i}")
            val = sep[k]
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                raise ThemeValidationError(f"Theme '{theme_name}': field '{k}' in separator #{i} must be a number")
            val = float(val)
            if val < 0.0 or val > 1.0:
                raise ThemeValidationError(
                    f"Theme '{theme_name}': out-of-range fraction in field 'separator.{k}' ({val})"
                )
        result.append(
            SeparatorConfig(
                x1=float(sep["x1"]),
                y1=float(sep["y1"]),
                x2=float(sep["x2"]),
                y2=float(sep["y2"]),
            )
        )
    return tuple(result)


def load_theme(name_or_path: Union[str, Path]) -> Theme:
    """Load and validate a theme by name or YAML file path."""
    path = Path(name_or_path)
    if not path.is_file():
        # Look up in standard themes directory: res/moka_tss/themes/<name>/theme.yaml
        base_dir = Path(__file__).resolve().parent.parent.parent
        candidate = base_dir / "res" / "moka_tss" / "themes" / str(name_or_path) / "theme.yaml"
        if not candidate.is_file():
            fallback_candidate = base_dir / "res" / "mascota" / "themes" / str(name_or_path) / "theme.yaml"
            if fallback_candidate.is_file():
                candidate = fallback_candidate
        if candidate.is_file():
            path = candidate
        else:
            raise FileNotFoundError(f"Theme file not found: {name_or_path} (checked {candidate})")

    theme_dir = path.parent
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ThemeValidationError(f"Theme file {path} does not contain a YAML mapping")
    theme = Theme.from_dict(data)

    # Resolve background path relative to theme directory
    if theme.background is not None:
        bg_path = Path(theme.background.path)
        if not bg_path.is_absolute():
            resolved_path = (theme_dir / bg_path).resolve()
            if resolved_path.is_file():
                # Create a new theme with resolved background path
                theme = Theme(
                    name=theme.name,
                    display=theme.display,
                    palette=theme.palette,
                    fonts=theme.fonts,
                    regions=theme.regions,
                    separators=theme.separators,
                    background=BackgroundConfig(
                        path=str(resolved_path),
                        fit=theme.background.fit,
                        darken=theme.background.darken,
                    ),
                    system=theme.system,
                )
            else:
                raise FileNotFoundError(f"Background image not found: {resolved_path}")

    return theme
