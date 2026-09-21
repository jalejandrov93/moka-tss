#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Slice the husky sprite sheet (360x228, 6x6 grid of 60x38 cells)
into mood frames.

Source: https://inmenus.itch.io/dog (CC0)
Grid layout (6 rows x 6 cols, each cell 60x38):
- Row 0: Idle Stand (6 frames) -> calma (pick 3)
- Row 1: Idle Sit (6 frames) -> durmiendo (pick 2)
- Row 2: Sit Transition (6 frames) -> agobiada (pick 3)
- Row 3: Walk (6 frames) -> atenta (pick 3)
- Row 4: Run (6 frames) -> error (pick 2)
- Row 5: Bark (6 frames) -> alarmada (pick 2)

Outputs 13 files to res/moka_tss/sprites/husky/:
  sleep_a, sleep_b
  calma_a, calma_b, calma_c
  atenta_a, atenta_b, atenta_c
  alert_a, alert_b, alert_c
  alarm_a, alarm_b
"""

from pathlib import Path
from PIL import Image

CELL_W, CELL_H = 60, 38
GRID_COLS, GRID_ROWS = 6, 6
SHEET_W, SHEET_H = GRID_COLS * CELL_W, GRID_ROWS * CELL_H

# Mapping: row_index -> (mood_prefix, num_frames_to_take, frame_indices)
# Using first N frames from each row as they're typically the main
# animation cycle.
# Row 4 (Run) is not directly used - error mood is generated in code
# from calma frames.
ROW_MAP = {
    0: ("calma", 3, [0, 1, 2]),       # Idle Stand -> calma_a/b/c
    1: ("sleep", 2, [0, 1]),          # Idle Sit -> sleep_a/b
    2: ("alert", 3, [0, 1, 2]),       # Sit Transition -> alert_a/b/c
    3: ("atenta", 3, [0, 1, 2]),      # Walk -> atenta_a/b/c
    5: ("alarm", 3, [0, 1, 2]),       # Bark -> alarm_a/b/c
}

OUTPUT_DIR = (
    Path(__file__).resolve().parents[1]
    / "res"
    / "moka_tss"
    / "sprites"
    / "husky"
)
SHEET_PATH = Path(__file__).resolve().parents[1] / "Dog_medium.png"


def main():
    if not SHEET_PATH.is_file():
        print(f"ERROR: Sprite sheet not found at {SHEET_PATH}")
        return 1

    sheet = Image.open(SHEET_PATH)
    if sheet.size != (SHEET_W, SHEET_H):
        print(f"ERROR: Expected {SHEET_W}x{SHEET_H}, got {sheet.size}")
        return 1

    sheet = sheet.convert("RGBA")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Extract all cells
    cells = []
    for row in range(GRID_ROWS):
        row_cells = []
        for col in range(GRID_COLS):
            x = col * CELL_W
            y = row * CELL_H
            cell = sheet.crop((x, y, x + CELL_W, y + CELL_H))
            row_cells.append(cell)
        cells.append(row_cells)

    # Save mapped frames
    saved = []
    for row_idx, (prefix, count, indices) in ROW_MAP.items():
        for i, frame_idx in enumerate(indices):
            if frame_idx >= GRID_COLS:
                msg = (
                    f"WARNING: frame_idx {frame_idx} >= {GRID_COLS} "
                    f"for row {row_idx}"
                )
                print(msg)
                continue
            cell = cells[row_idx][frame_idx]
            fname = f"{prefix}_{chr(ord('a') + i)}.png"
            out_path = OUTPUT_DIR / fname
            cell.save(out_path)
            saved.append(fname)
            print(f"  Saved {fname} (from row {row_idx}, col {frame_idx})")

    print(f"\nDone! Saved {len(saved)} files to {OUTPUT_DIR}")
    for f in saved:
        print(f"  {f}")
    return 0


if __name__ == "__main__":
    exit(main())
