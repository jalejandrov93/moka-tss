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
from typing import Callable, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

# ----------------------------------------------------------------- interfaces


class MascotSprites:
    """Frozen interface implemented by a parallel task (library.mascota.mascot).

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


@lru_cache(maxsize=8)
def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def level_color(percent: float, accent: Optional[Tuple[int, int, int]] = None) -> Tuple[int, int, int]:
    """Map a 0-100 usage percentage to the D9 alert palette."""
    if percent >= RED_THRESHOLD:
        return RED
    if percent >= AMBER_THRESHOLD:
        return AMBER
    return accent or GREEN


def _hex_rgb(value, fallback=GREEN) -> Tuple[int, int, int]:
    try:
        v = value.lstrip("#")
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    except (AttributeError, ValueError, TypeError):
        return fallback


def _segmented_bar(draw: ImageDraw.ImageDraw, x, y, w, h, frac, color, segments=16) -> None:
    """Segmented bar: reads as an instrument, not a web progress bar."""
    gap = 2
    segment_w = (w - gap * (segments - 1)) / segments
    lit = int(round(max(0.0, min(1.0, frac)) * segments))
    for i in range(segments):
        sx = x + i * (segment_w + gap)
        draw.rectangle([sx, y, sx + segment_w, y + h], fill=color if i < lit else LINE)


def _visible_providers(snapshot, hidden_providers):
    if not snapshot:
        return []
    providers = snapshot.get("providers") or []
    return [p for p in providers if p.get("id") not in hidden_providers]


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


def _compute_mood(snapshot, providers) -> str:
    """Derive the mascot mood from quota pressure.

    `snapshot is None` means codexbar never answered at all -- an honest
    "error" mood rather than pretending everything is calm.
    """
    if snapshot is None:
        return "error"
    worst, _ = _worst_provider_usage(providers)
    if worst >= RED_THRESHOLD:
        return "alarmada"
    if worst >= AMBER_THRESHOLD:
        return "atenta"
    return "calma"


def _running_jobs(state):
    if not state:
        return []
    jobs = state.get("jobs") or []
    return [j for j in jobs if isinstance(j, dict) and j.get("status") == "running"]


def _draw_status_bar(draw, width, accent, worst, worst_name, jobs, clock_text):
    f_sm = _load_font(11)
    f_md = _load_font(13)

    draw.rectangle([0, 0, width, STATUS_BAR_HEIGHT], fill=PANEL)
    draw.rectangle([0, 0, 3, STATUS_BAR_HEIGHT], fill=accent)

    dot_color = GREEN if jobs else MUTED
    draw.ellipse([12, 10, 18, 16], fill=dot_color)
    draw.text((24, 7), f"{len(jobs)} jobs", font=f_sm, fill=TEXT if jobs else MUTED)

    if worst_name:
        draw.text((width - 62, 7), f"{worst_name[:9].lower()} {worst:.0f}%",
                  font=f_sm, fill=level_color(worst), anchor="ra")
    draw.text((width - 12, 6), clock_text, font=f_md, fill=TEXT, anchor="ra")


def _draw_quota_column(draw, providers, split_x):
    f_xs = _load_font(10)
    f_sm = _load_font(11)
    f_md = _load_font(13)

    draw.text((12, 34), "CUOTAS", font=f_xs, fill=MUTED)
    y = 52
    # Fewer providers -> taller rows, with room for the window label.
    step = 32 if len(providers) > 4 else 48
    right_edge = split_x - 24
    for p in providers:
        windows = p.get("windows") or []
        # Same guard as _worst_provider_usage: a provider that errored can hand
        # back a string, and this loop runs inside the 2-second render loop.
        busiest = max(windows, key=lambda win: _safe_percent(win.get("usedPercent"))) if windows else {}
        used = _safe_percent(busiest.get("usedPercent"))
        name = (p.get("id") or "?").lower()
        color = level_color(used, _hex_rgb((p.get("display") or {}).get("accentColor")))
        draw.text((12, y), name[:12], font=f_md if step > 32 else f_sm, fill=TEXT)
        draw.text((right_edge, y + 1), f"{used:>3.0f}%", font=f_sm, fill=color, anchor="ra")
        _segmented_bar(draw, 12, y + 18, split_x - 36, 6 if step > 32 else 5, used / 100.0, color)
        if step > 32:
            reset = (busiest.get("resetAt") or "")[11:16]
            tail = (busiest.get("label") or "").lower()
            if reset:
                tail = f"{tail}  reset {reset}"
            draw.text((12, y + 28), tail[:34], font=f_xs, fill=MUTED)
        y += step

    if not providers:
        draw.text((12, y), "codexbar sin respuesta", font=f_sm, fill=RED)


def _draw_system_column(draw, system, split_x, width):
    f_xs = _load_font(10)
    f_sm = _load_font(11)

    system = system or {}
    sx, sw = split_x + 16, width - split_x - 28
    draw.text((sx, 34), "SISTEMA", font=f_xs, fill=MUTED)
    y = 52
    gpu = system.get("gpu")
    rows = [
        ("cpu", system.get("cpu"), None),
        ("gpu", gpu["util"] if gpu else None, f"{gpu['temp']:.0f}C" if gpu else None),
        ("ram", system.get("ram"), None),
        ("vram", gpu["vram"] if gpu else None,
         f"{gpu['vram_used'] / 1024:.1f}G" if gpu else None),
    ]
    for label, value, extra in rows:
        draw.text((sx, y), label, font=f_sm, fill=TEXT)
        if value is None:
            draw.text((sx + sw, y), "n/d", font=f_sm, fill=MUTED, anchor="ra")
            _segmented_bar(draw, sx, y + 16, sw, 5, 0.0, LINE, segments=10)
        else:
            color = level_color(value)
            tail = f"{value:>3.0f}%" + (f" {extra}" if extra else "")
            draw.text((sx + sw, y), tail, font=f_sm, fill=color, anchor="ra")
            _segmented_bar(draw, sx, y + 16, sw, 5, value / 100.0, color, segments=10)
        y += 30
    return sx, sw


def _draw_mascot(image, draw, sprites, mood, tick, sx, sw, height, accent):
    f_xs = _load_font(10)
    size = getattr(sprites, "SIZE", 96) if sprites is not None else 84
    mx = sx + (sw - size) // 2
    my = height - size - 26

    if sprites is not None:
        frame = sprites.frame(mood, tick)
        image.paste(frame, (mx, my), frame if frame.mode == "RGBA" else None)
    else:
        # Degraded: sprite sheet unavailable, draw a neutral placeholder so
        # the panel still shows something honest instead of a hole.
        draw.rounded_rectangle(
            [mx, my, mx + size, my + size], radius=10, fill=PANEL, outline=accent, width=2)

    draw.text((sx + sw // 2, height - 20), mood.upper(), font=f_xs, fill=accent, anchor="ma")


def render(snapshot: Optional[dict], state: Optional[dict], system: Optional[dict], *,
           size: Tuple[int, int] = DEFAULT_SIZE,
           sprites: Optional[MascotSprites] = None,
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
    width, height = size
    image = Image.new("RGB", size, BACKGROUND)
    draw = ImageDraw.Draw(image)

    providers = _visible_providers(snapshot, hidden_providers)
    jobs = _running_jobs(state)
    worst, worst_name = _worst_provider_usage(providers)
    mood = _compute_mood(snapshot, providers)
    accent = level_color(worst)

    clock_text = time.strftime("%H:%M", now())

    _draw_status_bar(draw, width, accent, worst, worst_name, jobs, clock_text)

    draw.line([COLUMN_SPLIT_X, STATUS_BAR_HEIGHT + 8, COLUMN_SPLIT_X, height - 10],
              fill=LINE, width=1)

    _draw_quota_column(draw, providers, COLUMN_SPLIT_X)
    sx, sw = _draw_system_column(draw, system, COLUMN_SPLIT_X, width)
    _draw_mascot(image, draw, sprites, mood, tick, sx, sw, height, accent)

    return image
