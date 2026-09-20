# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays
# Mascota fork - sprite / animation state machine
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

"""Sprite loading and per-mood animation for the pixel-art mascot.

`library/mascota/rules.py` produces one of six moods every tick
(`RuleEngine.MOODS`-compatible: durmiendo, calma, atenta, agobiada,
alarmada, error). This module turns a mood name plus a monotonically
increasing `tick` (bumped once per render loop refresh, ~every 2s) into a
concrete 96x96 RGBA frame to blit onto the panel.

Source art and mood mapping
----------------------------
The committed frames (see res/mascota/sprites/CREDITS.md) come from the LPC
"Cats and Dogs" sheet by bluecarrot16 (GPL-3.0-compatible): 32x32 tan-cat
crops from FIVE distinct poses/facings on the sheet, not just one recolored
silhouette. Mood must read from the OUTLINE first, tint second:

- durmiendo -> the lying-down pose (``sleep_a``/``sleep_b``), no tint. A
  slow two-frame breathing loop. Distinct silhouette: reclined, low profile.
- calma     -> side-profile walk-left, 3 frames (``calma_a/b/c``), no tint,
  slow cycle. Distinct silhouette: full body length, head and tail visible.
- atenta    -> rear/walking-away view, 3 frames (``atenta_a/b/c``), no
  tint, medium cycle -- "looking away, scanning its surroundings". Distinct
  silhouette: narrow rear profile, ears and tail centered.
- agobiada  -> the bristled/defensive front pose, 3 frames
  (``alert_a/b/c``), a light amber tint (#EAB308, the project's warning
  color) so eyes and markings stay visible, medium-fast cycle. Distinct
  silhouette: tall front stance with raised fur.
- alarmada  -> side-profile walk-right (mirrored facing from ``calma``), 2
  of the 3 frames (``alarm_a/b``), a light red tint (#EF4444, the
  project's critical color), fast cycle (shortest period of the animated
  moods) -- "fleeing", not just "the bristled cat but redder". Differs from
  agobiada in silhouette (side vs. front) and from calma in facing, tint
  and speed.
- error     -> generated at load time, not extracted from the sheet: a
  desaturated calm frame with a glitch overlay (scanlines, channel-shifted
  noise, and a bold red X) flickering against an inverted copy every other
  tick. Nothing in the source set means "system error", so this is drawn
  deliberately unmistakable against the other five.

Tints are intentionally light (15-25% alpha): a tint should shade a pose,
not repaint it, so the cat's eyes and body markings stay legible after
tinting -- distinguishing moods is the outline's job, color is secondary.

All tinting/glitch generation happens once in `load()`; `frame()` only
indexes into precomputed, cached PIL Images and never touches disk or
recomputes pixels.
"""

import random
from pathlib import Path
from typing import Dict, List, Optional, Union

from PIL import Image, ImageDraw, ImageOps

_AMBER = (234, 179, 8)
_RED = (239, 68, 68)

# Raw pose files expected under the assets directory (see CREDITS.md).
_POSE_FILES = (
    "sleep_a", "sleep_b",
    "calma_a", "calma_b", "calma_c",
    "atenta_a", "atenta_b", "atenta_c",
    "alert_a", "alert_b", "alert_c",
    "alarm_a", "alarm_b", "alarm_c",
)


def _default_assets_dir() -> Path:
    # library/mascota/mascot.py -> library/mascota -> library -> repo root
    return Path(__file__).resolve().parents[2] / "res" / "mascota" / "sprites"


def _load_pose(assets_dir: Path, filename: str) -> Image.Image:
    path = assets_dir / filename
    if not path.is_file():
        raise FileNotFoundError(
            f"Mascot sprite asset missing: '{path}'. Expected the committed "
            f"frames under res/mascota/sprites/ (see CREDITS.md there)."
        )
    with Image.open(path) as handle:
        return handle.convert("RGBA")


def _scale(image: Image.Image, size: int) -> Image.Image:
    # NEAREST keeps pixel-art edges crisp; any smoothing filter would blur it.
    return image.resize((size, size), Image.NEAREST)


def _tinted(image: Image.Image, color, alpha: float) -> Image.Image:
    """Blend a flat color over the opaque pixels of `image`, alpha in [0, 1].

    Transparent pixels stay transparent: the tint is composited through the
    source's own alpha channel so the mascot's silhouette never changes.
    """
    overlay = Image.new("RGBA", image.size, color + (0,))
    alpha_channel = image.getchannel("A").point(lambda a: int(a * alpha))
    overlay.putalpha(alpha_channel)
    return Image.alpha_composite(image, overlay)


def _glitch_frame(base: Image.Image, size: int, invert: bool, seed: int) -> Image.Image:
    """Build one unmistakable "error" frame from a calm base pose.

    Deliberately not a recolor of an existing pose: desaturated body,
    scanlines, deterministic pixel noise, and a bold red X. `invert`
    flips it into a high-contrast counterpart so the two error frames
    read as a flicker rather than a single static picture.
    """
    grayscale = ImageOps.grayscale(base.convert("RGB")).convert("RGBA")
    grayscale.putalpha(base.getchannel("A"))
    frame = _scale(grayscale, size)
    if invert:
        rgb = ImageOps.invert(frame.convert("RGB")).convert("RGBA")
        rgb.putalpha(frame.getchannel("A"))
        frame = rgb

    rng = random.Random(seed)
    pixels = frame.load()
    for _ in range(size * 6):
        x = rng.randrange(size)
        y = rng.randrange(size)
        r, g, b, a = pixels[x, y]
        if a == 0:
            continue
        pixels[x, y] = (255, 0, 0, a) if rng.random() < 0.5 else (0, 0, 0, a)
    for y in range(1, size, 4):
        for x in range(size):
            r, g, b, a = pixels[x, y]
            if a:
                pixels[x, y] = (max(r - 40, 0), max(g - 40, 0), max(b - 40, 0), a)

    draw = ImageDraw.Draw(frame)
    margin = size // 6
    width = max(size // 16, 2)
    draw.line((margin, margin, size - margin, size - margin), fill=_RED + (255,), width=width)
    draw.line((size - margin, margin, margin, size - margin), fill=_RED + (255,), width=width)
    return frame


def _repeated(frames: List[Image.Image], repeat: int) -> List[Image.Image]:
    sequence: List[Image.Image] = []
    for frame in frames:
        sequence.extend([frame] * repeat)
    return sequence


class MascotSprites:
    """Preloaded, precomputed animation frames for every mascot mood.

    Every mood maps to a fixed, cached list of 96x96 RGBA frames built once
    in `load()`. `frame()` only does `tick % len(sequence)` indexing, so it
    is safe to call every render tick without touching disk again.
    """

    MOODS = ("durmiendo", "calma", "atenta", "agobiada", "alarmada", "error")
    SIZE = 96
    FALLBACK_MOOD = "calma"

    def __init__(self, sequences: Dict[str, List[Image.Image]]):
        self._sequences = sequences

    @classmethod
    def load(cls, assets_dir: Optional[Union[str, Path]] = None) -> "MascotSprites":
        directory = Path(assets_dir) if assets_dir is not None else _default_assets_dir()
        if not directory.is_dir():
            raise FileNotFoundError(
                f"Mascot sprite assets directory not found: '{directory}'. "
                f"Expected the frames committed under res/mascota/sprites/."
            )

        poses = {name: _load_pose(directory, f"{name}.png") for name in _POSE_FILES}
        size = cls.SIZE
        scaled = {name: _scale(image, size) for name, image in poses.items()}

        sequences: Dict[str, List[Image.Image]] = {}
        sequences["durmiendo"] = _repeated(
            [scaled["sleep_a"], scaled["sleep_b"]], repeat=3
        )
        sequences["calma"] = _repeated(
            [scaled["calma_a"], scaled["calma_b"], scaled["calma_c"]], repeat=3
        )
        sequences["atenta"] = _repeated(
            [scaled["atenta_a"], scaled["atenta_b"], scaled["atenta_c"]], repeat=2
        )
        agobiada_frames = [
            _tinted(scaled["alert_a"], _AMBER, 0.20),
            _tinted(scaled["alert_b"], _AMBER, 0.20),
            _tinted(scaled["alert_c"], _AMBER, 0.20),
        ]
        sequences["agobiada"] = _repeated(agobiada_frames, repeat=1)
        alarmada_frames = [
            _tinted(scaled["alarm_a"], _RED, 0.25),
            _tinted(scaled["alarm_b"], _RED, 0.25),
        ]
        sequences["alarmada"] = _repeated(alarmada_frames, repeat=1)
        sequences["error"] = [
            _glitch_frame(poses["calma_a"], size, invert=False, seed=1),
            _glitch_frame(poses["calma_b"], size, invert=True, seed=2),
        ]

        return cls(sequences)

    def frame(self, mood: str, tick: int) -> Image.Image:
        sequence = self._sequences.get(mood) or self._sequences[self.FALLBACK_MOOD]
        try:
            index = int(tick) % len(sequence)
        except (TypeError, ValueError):
            index = 0
        return sequence[index]

    def frame_count(self, mood: str) -> int:
        sequence = self._sequences.get(mood) or self._sequences[self.FALLBACK_MOOD]
        return len(sequence)
