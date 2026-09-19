# SPDX-License-Identifier: GPL-3.0-or-later
#
# Spike (ODD T1/T8): the Mascota layout on the physical screen.
#
# Disposable end-to-end proof: reads live codexbar + agent-hub data and local
# CPU/GPU/RAM sensors, renders the "data first" layout (decisions D1/D7), and
# pushes it to the Turing 3.5" Rev A. Standalone on purpose, so it runs on
# Windows with only pyserial + Pillow + psutil.
#
# Design system (ui-ux-pro-max): Dark Mode OLED, "code dark + run green",
# Fira Code family -> Cascadia Code locally (Fira Code is not installed).
#
# Usage:  py -3.13 first_frame.py [--portrait] [--brightness N] [--port COM3]

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

import serial
import serial.tools.list_ports
from PIL import Image, ImageDraw, ImageFont

try:
    import psutil
except ImportError:
    psutil = None

# Protocol (library/lcd/lcd_comm_rev_a.py)
SET_BRIGHTNESS = 110
SET_ORIENTATION = 121
DISPLAY_BITMAP = 197
PORTRAIT, LANDSCAPE = 0, 2

CODEXBAR = "http://127.0.0.1:8787"
AGENTHUB = "http://127.0.0.1:7777"
TOKEN_UNC = r"\\wsl.localhost\Ubuntu\home\alejandro\.config\codexbar\dashboard-token"

# Providers the user has no account for. Also disabled in codexbar's own
# config.json, but filtered here too so the screen is right even if the
# codexbar service has not been restarted yet.
HIDDEN_PROVIDERS = {"copilot", "opencodego"}

# Palette: Dark Mode (OLED) from the design system.
BG = (15, 23, 42)          # #0F172A
PANEL = (30, 41, 59)       # #1E293B
LINE = (51, 65, 85)        # #334155
TEXT = (248, 250, 252)     # #F8FAFC
MUTED = (110, 125, 150)
GREEN = (34, 197, 94)      # #22C55E  "run green"
AMBER = (234, 179, 8)
RED = (239, 68, 68)

MONO = "C:/Windows/Fonts/CascadiaCode.ttf"
MONO_FALLBACK = "C:/Windows/Fonts/consola.ttf"


# --------------------------------------------------------------------------- data

def read_token():
    try:
        with open(TOKEN_UNC, "r", encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return None


def get_json(url, token=None, timeout=25):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"  ! {url} -> {type(exc).__name__}")
        return None


def read_gpu():
    """nvidia-smi works without admin, unlike LibreHardwareMonitor."""
    query = "utilization.gpu,temperature.gpu,memory.used,memory.total"
    try:
        out = subprocess.run(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=6, check=True,
        ).stdout.strip().splitlines()[0]
        used, temp, vram_used, vram_total = [float(v) for v in out.split(",")]
        return {"util": used, "temp": temp,
                "vram": 100.0 * vram_used / vram_total if vram_total else 0.0,
                "vram_used": vram_used, "vram_total": vram_total}
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def read_system():
    stats = {"cpu": None, "ram": None, "gpu": read_gpu()}
    if psutil:
        stats["cpu"] = psutil.cpu_percent(interval=0.3)
        stats["ram"] = psutil.virtual_memory().percent
    return stats


# ------------------------------------------------------------------------- render

def font(size, bold=False):
    for path in (MONO, MONO_FALLBACK):
        try:
            f = ImageFont.truetype(path, size)
            if bold and path == MONO_FALLBACK:
                f = ImageFont.truetype("C:/Windows/Fonts/consolab.ttf", size)
            return f
        except OSError:
            continue
    return ImageFont.load_default()


def level_color(pct, accent=None):
    if pct >= 90:
        return RED
    if pct >= 75:
        return AMBER
    return accent or GREEN


def seg_bar(d, x, y, w, h, frac, color, segments=16):
    """Segmented bar - reads as an instrument, not a web progress bar."""
    gap = 2
    sw = (w - gap * (segments - 1)) / segments
    lit = int(round(max(0.0, min(1.0, frac)) * segments))
    for i in range(segments):
        sx = x + i * (sw + gap)
        d.rectangle([sx, y, sx + sw, y + h], fill=color if i < lit else LINE)


def hex_rgb(value, fallback=GREEN):
    try:
        v = value.lstrip("#")
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    except (AttributeError, ValueError):
        return fallback


def mascot(d, x, y, size, mood):
    """Placeholder mascot. Real sprites land in T6."""
    skin = {"calma": GREEN, "atenta": AMBER, "alarmada": RED}[mood]
    d.rounded_rectangle([x, y, x + size, y + size], radius=10,
                        fill=PANEL, outline=skin, width=2)
    px = size / 16.0  # draw on a 16x16 pixel grid so it reads as pixel art

    def blk(cx, cy, w=1, h=1, fill=skin):
        d.rectangle([x + cx * px, y + cy * px,
                     x + (cx + w) * px - 1, y + (cy + h) * px - 1], fill=fill)

    if mood == "calma":
        blk(4, 5, 2, 2, TEXT); blk(10, 5, 2, 2, TEXT)
        blk(5, 10, 6, 1); blk(4, 9, 1, 1); blk(11, 9, 1, 1)
    elif mood == "atenta":
        blk(4, 4, 2, 3, TEXT); blk(10, 4, 2, 3, TEXT)
        blk(6, 10, 4, 1)
    else:
        blk(4, 4, 2, 2, TEXT); blk(10, 4, 2, 2, TEXT)
        blk(5, 11, 6, 1); blk(4, 10, 1, 1); blk(11, 10, 1, 1)
        blk(3, 2, 1, 2); blk(12, 2, 1, 2)


def render(snapshot, state, system, size):
    w, h = size
    img = Image.new("RGB", size, BG)
    d = ImageDraw.Draw(img)

    f_xs = font(10)
    f_sm = font(11)
    f_md = font(13)
    f_lg = font(17)

    providers = [p for p in (snapshot or {}).get("providers", [])
                 if p.get("windows") and p.get("id") not in HIDDEN_PROVIDERS]
    jobs = [j for j in ((state or {}).get("jobs") or []) if j.get("status") == "running"]

    worst, worst_name = 0.0, None
    for p in providers:
        w0 = max(p["windows"], key=lambda x: x.get("usedPercent") or 0)
        used = float(w0.get("usedPercent") or 0)
        if used > worst:
            worst, worst_name = used, (p.get("name") or p.get("id") or "?")
    mood = "alarmada" if worst >= 90 else "atenta" if worst >= 75 else "calma"
    accent = level_color(worst)

    # ---- status bar (tmux/powerline flavour, carries the worst alert) --------
    d.rectangle([0, 0, w, 24], fill=PANEL)
    d.rectangle([0, 0, 3, 24], fill=accent)
    d.text((12, 5), "mascota", font=f_md, fill=TEXT)
    d.text((82, 7), "~/dev", font=f_sm, fill=MUTED)

    dot = GREEN if jobs else MUTED
    d.ellipse([146, 10, 152, 16], fill=dot)
    d.text((158, 7), f"{len(jobs)} jobs", font=f_sm, fill=TEXT if jobs else MUTED)

    if worst_name:
        d.text((w - 62, 7), f"{worst_name[:9].lower()} {worst:.0f}%",
               font=f_sm, fill=accent, anchor="ra")
    d.text((w - 12, 6), time.strftime("%H:%M"), font=f_md, fill=TEXT, anchor="ra")

    # ---- columns ------------------------------------------------------------
    split = 276
    d.line([split, 32, split, h - 10], fill=LINE, width=1)

    # ---- quotas -------------------------------------------------------------
    d.text((12, 34), "CUOTAS", font=f_xs, fill=MUTED)
    y = 52
    # Fewer providers -> taller rows, and there is room for the window label.
    step = 32 if len(providers) > 4 else 48
    for p in providers:
        w0 = max(p["windows"], key=lambda x: x.get("usedPercent") or 0)
        used = float(w0.get("usedPercent") or 0)
        name = (p.get("id") or "?").lower()
        color = level_color(used, hex_rgb((p.get("display") or {}).get("accentColor")))
        d.text((12, y), name[:12], font=f_md if step > 32 else f_sm, fill=TEXT)
        d.text((252, y + 1), f"{used:>3.0f}%", font=f_sm, fill=color, anchor="ra")
        seg_bar(d, 12, y + 18, 240, 6 if step > 32 else 5, used / 100.0, color)
        if step > 32:
            reset = (w0.get("resetAt") or "")[11:16]
            tail = (w0.get("label") or "").lower()
            if reset:
                tail = f"{tail}  reset {reset}"
            d.text((12, y + 28), tail[:34], font=f_xs, fill=MUTED)
        y += step

    if not providers:
        d.text((12, y), "codexbar sin respuesta", font=f_sm, fill=RED)

    # ---- system -------------------------------------------------------------
    sx, sw = split + 16, w - split - 28
    d.text((sx, 34), "SISTEMA", font=f_xs, fill=MUTED)
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
        d.text((sx, y), label, font=f_sm, fill=TEXT)
        if value is None:
            d.text((sx + sw, y), "n/d", font=f_sm, fill=MUTED, anchor="ra")
            seg_bar(d, sx, y + 16, sw, 5, 0, LINE, segments=10)
        else:
            c = level_color(value)
            tail = f"{value:>3.0f}%" + (f" {extra}" if extra else "")
            d.text((sx + sw, y), tail, font=f_sm, fill=c, anchor="ra")
            seg_bar(d, sx, y + 16, sw, 5, value / 100.0, c, segments=10)
        y += 30

    # ---- mascot -------------------------------------------------------------
    m = 84
    mx = sx + (sw - m) // 2
    my = h - m - 26
    mascot(d, mx, my, m, mood)
    d.text((sx + sw // 2, h - 20), mood.upper(), font=f_xs, fill=accent, anchor="ma")

    return img, mood


# --------------------------------------------------------------------------- wire

def cmd_bytes(cmd, x, y, ex, ey):
    b = bytearray(6)
    b[0] = (x >> 2) & 0xFF
    b[1] = (((x & 3) << 6) + (y >> 4)) & 0xFF
    b[2] = (((y & 15) << 4) + (ex >> 6)) & 0xFF
    b[3] = (((ex & 63) << 2) + (ey >> 8)) & 0xFF
    b[4] = ey & 0xFF
    b[5] = cmd
    return bytes(b)


def set_orientation(ser, orientation, width, height):
    b = bytearray(16)
    b[5] = SET_ORIENTATION
    b[6] = orientation + 100
    b[7] = (width >> 8) & 0xFF
    b[8] = width & 0xFF
    b[9] = (height >> 8) & 0xFF
    b[10] = height & 0xFF
    ser.write(bytes(b))
    ser.flush()


def set_brightness(ser, level):
    """level is 0-100 percent. The panel is inverted: 0 brightest, 255 darkest."""
    assert 0 <= level <= 100
    ser.write(cmd_bytes(SET_BRIGHTNESS, int(255 - ((level / 100) * 255)), 0, 0, 0))
    ser.flush()


def to_rgb565le(img):
    out = bytearray()
    for r, g, b in img.getdata():
        v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        out += v.to_bytes(2, "little")
    return bytes(out)


def push(ser, img, screen_w, x=0, y=0):
    data = to_rgb565le(img)
    w, h = img.size
    t0 = time.perf_counter()
    ser.write(cmd_bytes(DISPLAY_BITMAP, x, y, x + w - 1, y + h - 1))
    chunk = screen_w * 8
    for i in range(0, len(data), chunk):
        ser.write(data[i:i + chunk])
    ser.flush()
    return time.perf_counter() - t0


def find_port():
    for p in serial.tools.list_ports.comports():
        if p.serial_number == "USB35INCHIPSV2" or (p.vid == 0x1A86 and p.pid == 0x5722):
            return p.device
    return None


# ------------------------------------------------------------------- partial blits

TILE_W, TILE_H = 80, 40


class Screen:
    """Keeps the last frame so a refresh only retransmits the tiles that changed.

    A full 480x320 frame costs 0.573s on this panel; an 80x40 tile costs 0.012s.
    That gap is the whole reason the dashboard can refresh every couple of
    seconds without the screen visibly redrawing itself.
    """

    def __init__(self, ser, size):
        self.ser = ser
        self.w, self.h = size
        self.prev = None

    def show(self, img):
        if self.prev is None:
            dt = push(self.ser, img, self.w)
            self.prev = img.copy()
            return dt, 1, "completo"

        dirty = []
        for ty in range(0, self.h, TILE_H):
            for tx in range(0, self.w, TILE_W):
                box = (tx, ty, min(tx + TILE_W, self.w), min(ty + TILE_H, self.h))
                if img.crop(box).tobytes() != self.prev.crop(box).tobytes():
                    dirty.append(box)

        t0 = time.perf_counter()
        for box in dirty:
            push(self.ser, img.crop(box), self.w, x=box[0], y=box[1])
        self.prev = img.copy()
        return time.perf_counter() - t0, len(dirty), "parcial"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--portrait", action="store_true", help="320x480 instead of 480x320")
    ap.add_argument("--brightness", type=int, default=90, help="0-100 (default 90)")
    ap.add_argument("--port", default=None)
    ap.add_argument("--no-push", action="store_true", help="render only, no serial")
    ap.add_argument("--watch", action="store_true",
                    help="keep refreshing, retransmitting only the tiles that changed")
    ap.add_argument("--tick", type=float, default=2.0, help="watch period in seconds")
    args = ap.parse_args()

    landscape = not args.portrait
    size = (480, 320) if landscape else (320, 480)

    token = read_token()
    print(f"token codexbar: {'ok' if token else 'NO DISPONIBLE'}")

    if args.no_push:
        snapshot = get_json(f"{CODEXBAR}/dashboard/v1/snapshot", token)
        state = get_json(f"{AGENTHUB}/api/state")
        img, mood = render(snapshot, state, read_system(), size)
        img.save("first_frame.png")
        print(f"mascota: {mood}  (preview en first_frame.png)")
        return 0

    port = args.port or find_port()
    if not port:
        print("No encontre la pantalla (USB35INCHIPSV2 / 1A86:5722).")
        return 1
    print(f"Puerto: {port}")

    ser = serial.Serial(port, 115200, timeout=1, rtscts=True)
    screen = Screen(ser, size)
    # Cadence per source: local sensors are cheap, agent-hub is fast and local,
    # the codexbar snapshot measurably takes several seconds while it refreshes.
    snapshot = state = None
    next_codexbar = next_agenthub = 0.0
    try:
        set_orientation(ser, LANDSCAPE if landscape else PORTRAIT, size[0], size[1])
        time.sleep(0.2)
        set_brightness(ser, args.brightness)

        while True:
            now = time.monotonic()
            if now >= next_codexbar:
                fresh = get_json(f"{CODEXBAR}/dashboard/v1/snapshot", token)
                if fresh:
                    snapshot = fresh          # keep the last good one on failure
                next_codexbar = now + 60
            if now >= next_agenthub:
                fresh = get_json(f"{AGENTHUB}/api/state")
                if fresh:
                    state = fresh
                next_agenthub = now + 5

            system = read_system()
            img, mood = render(snapshot, state, system, size)
            dt, tiles, kind = screen.show(img)
            gpu = system.get("gpu")
            line = (f"{time.strftime('%H:%M:%S')}  {kind:8} {tiles:2} tiles  {dt:.3f}s  "
                    f"cpu {system.get('cpu'):.0f}%  ram {system.get('ram'):.0f}%")
            if gpu:
                line += f"  gpu {gpu['util']:.0f}% {gpu['temp']:.0f}C"
            line += f"  jobs {len([j for j in (state or {}).get('jobs', []) if j.get('status') == 'running'])}"
            print(line, flush=True)

            if not args.watch:
                img.save("first_frame.png")
                break
            time.sleep(max(0.0, args.tick - (time.monotonic() - now)))
    except KeyboardInterrupt:
        print("\ncortado por el usuario")
    finally:
        ser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
