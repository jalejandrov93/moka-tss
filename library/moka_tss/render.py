# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays
# Mascota fork - layout compositor for the dashboard
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

"""Layout compositor for the Mascota dashboard.

`render()` is pure: given quota/system/job data (and an optional mascot
sprite sheet and clock) it returns a PIL Image, with no serial I/O, no
network calls, and no clock reads other than the injectable `now`
callable. That purity is what makes this module unit-testable without a
panel attached, and is why it lives apart from `library.mascota.screen`,
which owns the actual wire transfer.

Layout (approved, see odd/tasks/mascota.md decisions D1/D7/D8/D9): a
tmux-style status bar across the top carries the worst active alert, the
live job count, and the clock -- deliberately with no decorative title
header. The left column lists AI-agent quotas as segmented bars (an
instrument reading, not a web progress bar). The right column shows
system sensors (cpu, gpu+temperature, ram, vram) and the mascot with its
mood label underneath.

Design system (decision D9, Dark Mode OLED): background #0F172A, panel
#1E293B, lines #334155, text #F8FAFC, accent green #22C55E, amber #EAB308
at >=75%, red #EF4444 at >=90%. Monospace throughout, Cascadia Code with a
graceful fallback chain since it will not exist on Linux where the tests
run.

Degradation is deliberate: a missing/None snapshot, state, or system dict
must still render an honest "no data" view rather than crash. The mascot
sprite sheet comes from a parallel task through the frozen `MascotSprites`
interface below; this module only calls it, it never implements it.
"""

import time
from functools import lru_cache
from typing import Callable, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from library.moka_tss.theme import Theme, load_theme

# ----------------------------------------------------------------- background


def _draw_background(image: Image.Image, theme: Theme) -> None:
    """Draw theme background image with fit and darken overlay."""
    if theme.background is None:
        return

    bg_config = theme.background
    try:
        bg_img = Image.open(bg_config.path)
    except (OSError, FileNotFoundError):
        # If background image can't be loaded, fall back to solid color
        return

    width, height = image.size
    fit = bg_config.fit
    darken = bg_config.darken

    # Resize background based on fit mode
    if fit == "cover":
        # Scale to cover entire canvas, may crop
        bg_ratio = bg_img.width / bg_img.height
        canvas_ratio = width / height
        if bg_ratio > canvas_ratio:
            # Background is wider - scale to height
            new_height = height
            new_width = int(height * bg_ratio)
        else:
            # Background is taller - scale to width
            new_width = width
            new_height = int(width / bg_ratio)
        bg_img = bg_img.resize((new_width, new_height), Image.LANCZOS)
        # Center crop
        left = (new_width - width) // 2
        top = (new_height - height) // 2
        bg_img = bg_img.crop((left, top, left + width, top + height))

    elif fit == "contain":
        # Scale to fit entirely within canvas, may have bars
        bg_img.thumbnail((width, height), Image.LANCZOS)
        # Create new image with background color and paste centered
        result = Image.new("RGB", (width, height), (0, 0, 0))
        left = (width - bg_img.width) // 2
        top = (height - bg_img.height) // 2
        result.paste(bg_img, (left, top))
        bg_img = result

    elif fit == "stretch":
        # Stretch to fill exactly
        bg_img = bg_img.resize((width, height), Image.LANCZOS)

    # Apply darken overlay
    if darken > 0.0:
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, int(255 * darken)))
        bg_img = bg_img.convert("RGBA")
        bg_img = Image.alpha_composite(bg_img, overlay)
        bg_img = bg_img.convert("RGB")

    # Paste onto main image
    image.paste(bg_img, (0, 0))


# ----------------------------------------------------------------- interfaces


class MascotSprites:
    """Frozen interface implemented by a parallel task (library.moka_tss.mascot).

    Not implemented here -- code against this shape, use a stub in tests.
    """

    MOODS = ("durmiendo", "calma", "atenta", "agobiada", "alarmada", "error")
    SIZE = 96

    def frame(self, mood: str, tick: int) -> Image.Image:  # pragma: no cover
        raise NotImplementedError

    def frame_count(self, mood: str) -> int:  # pragma: no cover
        raise NotImplementedError


# ------------------------------------------------------------------- palette

BACKGROUND = (15, 23, 42)      # #0F172A
PANEL = (30, 41, 59)           # #1E293B
LINE = (51, 65, 85)            # #334155
TEXT = (248, 250, 252)         # #F8FAFC
MUTED = (110, 125, 150)
GREEN = (34, 197, 94)          # #22C55E
AMBER = (234, 179, 8)          # #EAB308
RED = (239, 68, 68)            # #EF4444

AMBER_THRESHOLD = 75.0
RED_THRESHOLD = 90.0

# Providers the user has no account for (decision D10). A default so
# callers get sane behaviour for free, but never hardcoded into the
# filtering logic below -- pass a different set to change it.
HIDDEN_PROVIDERS = frozenset({"copilot", "opencodego"})

DEFAULT_SIZE = (480, 320)
STATUS_BAR_HEIGHT = 24
COLUMN_SPLIT_X = 276

# Cascadia Code locally, falling back through progressively more generic
# monospace fonts so a missing font never raises -- it will not exist on
# Linux, where the tests run.
FONT_CANDIDATES = (
    "C:/Windows/Fonts/CascadiaCode.ttf",
    "C:/Windows/Fonts/consola.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "DejaVuSansMono.ttf",
)


@lru_cache(maxsize=32)
def _load_font(size: int, candidates: Optional[Sequence[str]] = None) -> ImageFont.FreeTypeFont:
    paths = candidates if candidates is not None else FONT_CANDIDATES
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


@lru_cache(maxsize=4)
def _get_default_theme(name: str = "horizontal") -> Theme:
    return load_theme(name)


def level_color(percent: float, accent: Optional[Tuple[int, int, int]] = None,
                theme: Optional[Theme] = None) -> Tuple[int, int, int]:
    """Map a 0-100 usage percentage to the alert palette."""
    red_thresh = theme.palette.critical_threshold if theme else RED_THRESHOLD
    amber_thresh = theme.palette.warning_threshold if theme else AMBER_THRESHOLD
    red_col = theme.palette.critical if theme else RED
    amber_col = theme.palette.warning if theme else AMBER
    default_accent = theme.palette.accent if theme else GREEN

    if percent >= red_thresh:
        return red_col
    if percent >= amber_thresh:
        return amber_col
    return accent or default_accent


def _hex_rgb(value, fallback=GREEN) -> Tuple[int, int, int]:
    try:
        v = value.lstrip("#")
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    except (AttributeError, ValueError, TypeError):
        return fallback


def _segmented_bar(draw: ImageDraw.ImageDraw, x, y, w, h, frac, color,
                   unlit_color: Tuple[int, int, int] = LINE, segments: int = 16) -> None:
    """Segmented bar: reads as an instrument, not a web progress bar."""
    gap = 2
    available_w = w - gap * (segments - 1)
    if available_w <= 0:
        draw.rectangle([x, y, x + max(1, w), y + h], fill=color if frac > 0 else unlit_color)
        return
    segment_w = available_w / segments
    lit = int(round(max(0.0, min(1.0, frac)) * segments))
    for i in range(segments):
        sx = x + i * (segment_w + gap)
        draw.rectangle([sx, y, sx + segment_w, y + h], fill=color if i < lit else unlit_color)


def _visible_providers(snapshot, hidden_providers):

    if not snapshot:
        return []
    providers = snapshot.get("providers") or []
    return [p for p in providers if p.get("id") not in hidden_providers]


def _theme_provider_selection(theme) -> list:
    system = getattr(theme, "system", None)
    quotas = getattr(system, "quotas", None)
    return list(getattr(quotas, "providers", None) or [])


def _theme_sensor_selection(theme) -> list:
    system = getattr(theme, "system", None)
    return list(getattr(system, "sensors", None) or [])


def _apply_provider_selection(providers, theme) -> list:
    """Filter and order providers per theme.system.quotas.providers.

    An empty selection means "show all" (backwards compatible default).
    Unknown ids in the selection are ignored; providers missing from the
    selection are dropped only when the selection is non-empty.
    """
    wanted = _theme_provider_selection(theme)
    if not wanted:
        return providers
    by_id = {}
    for p in providers:
        pid = p.get("id")
        if pid not in by_id:
            by_id[pid] = p
    return [by_id[pid] for pid in wanted if pid in by_id]


def _apply_sensor_selection(rows, theme) -> list:
    """Filter and order (label, value, extra) rows per theme.system.sensors.

    An empty selection means "show all in default order".
    """
    wanted = _theme_sensor_selection(theme)
    if not wanted:
        return rows
    by_label = {label: row for label, row in ((r[0], r) for r in rows)}
    return [by_label[label] for label in wanted if label in by_label]


def _safe_percent(value) -> float:
    """Coerce a usedPercent reading to float, treating anything that is not
    a real number (None, a string, NaN, a bool) as missing -> 0.0.

    codexbar can hand back an odd value when a provider errors; one bad
    reading must never crash the render loop.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    if isinstance(value, float) and value != value:  # NaN
        return 0.0
    return float(value)


def _worst_provider_usage(providers):
    """Return (worst_percent, worst_name) across all providers' busiest window."""
    worst, name = 0.0, None
    for p in providers:
        windows = p.get("windows") or []
        if not windows:
            continue
        busiest = max(windows, key=lambda win: _safe_percent(win.get("usedPercent")))
        used = _safe_percent(busiest.get("usedPercent"))
        if used > worst:
            worst, name = used, (p.get("name") or p.get("id") or "?")
    return worst, name


def _compute_mood(snapshot, providers, red_threshold: float = RED_THRESHOLD,
                  amber_threshold: float = AMBER_THRESHOLD) -> str:
    """Derive the mascot mood from quota pressure.

    `snapshot is None` means codexbar never answered at all -- an honest
    "error" mood rather than pretending everything is calm.
    """
    if snapshot is None:
        return "error"
    worst, _ = _worst_provider_usage(providers)
    if worst >= red_threshold:
        return "alarmada"
    if worst >= amber_threshold:
        return "atenta"
    return "calma"


def _running_jobs(state):
    if not state:
        return []
    jobs = state.get("jobs") or []
    return [j for j in jobs if isinstance(j, dict) and j.get("status") == "running"]


def _draw_status_bar(draw, rect, palette, fonts_candidates, accent, worst, worst_name, jobs, clock_text, theme=None):
    rx, ry, rw, rh = rect
    f_sm = _load_font(11, fonts_candidates)
    f_md = _load_font(13, fonts_candidates)

    draw.rectangle([rx, ry, rx + rw, ry + rh], fill=palette.panel)
    draw.rectangle([rx, ry, rx + 3, ry + rh], fill=accent)

    dot_color = palette.accent if jobs else palette.muted
    draw.ellipse([rx + 12, ry + 10, rx + 18, ry + 16], fill=dot_color)
    draw.text((rx + 24, ry + 7), f"{len(jobs)} jobs", font=f_sm, fill=palette.text if jobs else palette.muted)

    if worst_name:
        worst_color = level_color(worst, theme=theme)
        draw.text((rx + rw - 62, ry + 7), f"{worst_name[:9].lower()} {worst:.0f}%",
                  font=f_sm, fill=worst_color, anchor="ra")
    draw.text((rx + rw - 12, ry + 6), clock_text, font=f_md, fill=palette.text, anchor="ra")


def _draw_quota_column(draw, rect, providers, palette, fonts_candidates, theme):
    rx, ry, rw, rh = rect
    f_xs = _load_font(10, fonts_candidates)
    f_sm = _load_font(11, fonts_candidates)
    f_md = _load_font(13, fonts_candidates)

    draw.text((rx + 12, ry + 10), "CUOTAS", font=f_xs, fill=palette.muted)
    y = ry + 28
    # Fewer providers -> taller rows, with room for the window label.
    step = 32 if len(providers) > 4 else 48
    if len(providers) > 0 and y + step * len(providers) > ry + rh:
        available = max(30, rh - 28)
        step = max(24, available // len(providers))

    right_edge = rx + rw - 24
    bar_w = max(10, rw - 36)
    for p in providers:
        windows = p.get("windows") or []
        # Same guard as _worst_provider_usage: a provider that errored can hand
        # back a string, and this loop runs inside the 2-second render loop.
        busiest = max(windows, key=lambda win: _safe_percent(win.get("usedPercent"))) if windows else {}
        used = _safe_percent(busiest.get("usedPercent"))
        name = (p.get("id") or "?").lower()
        provider_accent = _hex_rgb((p.get("display") or {}).get("accentColor"), fallback=palette.accent)
        color = level_color(used, provider_accent, theme=theme)
        draw.text((rx + 12, y), name[:12], font=f_md if step > 32 else f_sm, fill=palette.text)
        draw.text((right_edge, y + 1), f"{used:>3.0f}%", font=f_sm, fill=color, anchor="ra")
        _segmented_bar(draw, rx + 12, y + 18, bar_w, 6 if step > 32 else 5, used / 100.0, color, unlit_color=palette.lines)
        if step > 32:
            reset = (busiest.get("resetAt") or "")[11:16]
            tail = (busiest.get("label") or "").lower()
            if reset:
                tail = f"{tail}  reset {reset}"
            draw.text((rx + 12, y + 28), tail[:34], font=f_xs, fill=palette.muted)
        y += step

    if not providers:
        draw.text((rx + 12, y), "codexbar sin respuesta", font=f_sm, fill=palette.critical)


def _draw_system_column(draw, rect, system, palette, fonts_candidates, theme):
    rx, ry, rw, rh = rect
    f_xs = _load_font(10, fonts_candidates)
    f_sm = _load_font(11, fonts_candidates)

    system = system or {}
    sx = rx + 16
    sw = max(10, rw - 28)
    draw.text((sx, ry + 10), "SISTEMA", font=f_xs, fill=palette.muted)
    y = ry + 28
    gpu = system.get("gpu")
    rows = [
        ("cpu", system.get("cpu"), None),
        ("gpu", gpu["util"] if gpu else None, f"{gpu['temp']:.0f}C" if gpu else None),
        ("ram", system.get("ram"), None),
        ("vram", gpu["vram"] if gpu else None,
         f"{gpu['vram_used'] / 1024:.1f}G" if gpu else None),
    ]
    rows = _apply_sensor_selection(rows, theme)
    step = 30
    if len(rows) > 0 and y + step * len(rows) > ry + rh:
        available = max(30, rh - 28)
        step = max(20, available // len(rows))

    for label, value, extra in rows:
        draw.text((sx, y), label, font=f_sm, fill=palette.text)
        if value is None:
            draw.text((sx + sw, y), "n/d", font=f_sm, fill=palette.muted, anchor="ra")
            _segmented_bar(draw, sx, y + 16, sw, 5, 0.0, palette.lines, unlit_color=palette.lines, segments=10)
        else:
            color = level_color(value, theme=theme)
            tail = f"{value:>3.0f}%" + (f" {extra}" if extra else "")
            draw.text((sx + sw, y), tail, font=f_sm, fill=color, anchor="ra")
            _segmented_bar(draw, sx, y + 16, sw, 5, value / 100.0, color, unlit_color=palette.lines, segments=10)
        y += step
    return sx, sw


def _draw_mascot(image, draw, rect, sprites, mood, tick, palette, fonts_candidates, accent):

    rx, ry, rw, rh = rect
    f_xs = _load_font(10, fonts_candidates)
    size = getattr(sprites, "SIZE", 96) if sprites is not None else 84
    actual_size = min(size, rw - 4, rh - 24) if (rw < size or rh < size + 24) else size
    actual_size = max(16, actual_size)
    mx = rx + max(0, (rw - actual_size) // 2)
    my = ry + max(0, rh - actual_size - 24)

    if sprites is not None:
        frame = sprites.frame(mood, tick)
        if actual_size != getattr(sprites, "SIZE", 96):
            frame = frame.resize((actual_size, actual_size), Image.NEAREST)
        image.paste(frame, (mx, my), frame if frame.mode == "RGBA" else None)
    else:
        draw.rounded_rectangle(
            [mx, my, mx + actual_size, my + actual_size],
            radius=10, fill=palette.panel, outline=accent, width=2,
        )

    label_y = min(ry + rh - 16, my + actual_size + 4)
    draw.text((rx + rw // 2, label_y), mood.upper(), font=f_xs, fill=accent, anchor="ma")


def render(snapshot: Optional[dict], state: Optional[dict], system: Optional[dict], *,
           size: Optional[Tuple[int, int]] = None,
           theme: Optional[Theme] = None,
           sprites: Optional[MascotSprites] = None,
           mood: Optional[str] = None,
           tick: int = 0,
           hidden_providers=HIDDEN_PROVIDERS,
           now: Callable[[], time.struct_time] = time.localtime) -> Image.Image:
    """Render one dashboard frame as a PIL Image.

    Pure function: no serial I/O, no network calls, no clock reads other
    than the injected `now` callable. The default is `time.localtime`
    itself -- visible in the signature, not hidden behind a `None` check
    in the body -- so a caller can see exactly what it is overriding.
    `snapshot` (codexbar), `state` (agent-hub) and `system` (local
    sensors) may each independently be None -- a data source being down
    must still produce an honest, non-crashing frame.

    `sprites` is the frozen `MascotSprites` interface from a parallel
    task; when None the mascot area degrades to a neutral placeholder
    instead of raising or leaving a hole.
    """
    if theme is None:
        if size is not None and size[1] > size[0]:
            theme = _get_default_theme("vertical")
        else:
            theme = _get_default_theme("horizontal")

    if size is None:
        size = theme.display.size

    width, height = size
    canvas_size = (width, height)
    palette = theme.palette
    fonts_candidates = theme.fonts.candidates

    image = Image.new("RGB", size, palette.background)
    _draw_background(image, theme)
    draw = ImageDraw.Draw(image)

    providers = _visible_providers(snapshot, hidden_providers)
    providers = _apply_provider_selection(providers, theme)
    jobs = _running_jobs(state)
    worst, worst_name = _worst_provider_usage(providers)
    # The caller may already know the mood - the app resolves it through the
    # rule engine, which sees metrics this function never receives. Only fall
    # back to the quota-only heuristic when nobody supplied one.
    if mood is None:
        mood = _compute_mood(
            snapshot, providers,
            red_threshold=palette.critical_threshold,
            amber_threshold=palette.warning_threshold,
        )
    accent = level_color(worst, theme=theme)

    clock_text = time.strftime("%H:%M", now())

    # Draw status bar
    sb_rect = theme.regions["status_bar"].resolve(canvas_size)
    _draw_status_bar(
        draw, sb_rect, palette, fonts_candidates, accent,
        worst, worst_name, jobs, clock_text, theme=theme,
    )

    # Draw separators
    for sep in theme.separators:
        x1, y1, x2, y2 = sep.resolve(canvas_size)
        draw.line([x1, y1, x2, y2], fill=palette.lines, width=1)

    # Draw quota column
    q_rect = theme.regions["quotas"].resolve(canvas_size)
    _draw_quota_column(draw, q_rect, providers, palette, fonts_candidates, theme)

    # Draw system column
    sys_rect = theme.regions["system"].resolve(canvas_size)
    _draw_system_column(draw, sys_rect, system, palette, fonts_candidates, theme)

    # Draw mascot
    m_rect = theme.regions["mascot"].resolve(canvas_size)
    _draw_mascot(image, draw, m_rect, sprites, mood, tick, palette, fonts_candidates, accent)

    return image
