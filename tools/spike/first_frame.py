# SPDX-License-Identifier: GPL-3.0-or-later
#
# Spike (ODD T1/T8): first real frame of the Mascota layout on the physical screen.
#
# Disposable end-to-end proof: reads live codexbar + agent-hub data, renders the
# "data first" layout (decision D1), and pushes it to the Turing 3.5" Rev A.
# Standalone on purpose, so it runs on Windows with only pyserial + Pillow.
#
# Usage:  py -3.13 first_frame.py [COM3]

import json
import sys
import time
import urllib.error
import urllib.request

import serial
import serial.tools.list_ports
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 320, 480
DISPLAY_BITMAP = 197
CHUNK = WIDTH * 8

CODEXBAR = "http://127.0.0.1:8787"
AGENTHUB = "http://127.0.0.1:7777"
TOKEN_UNC = r"\\wsl.localhost\Ubuntu\home\alejandro\.config\codexbar\dashboard-token"

BG = (14, 16, 22)
FG = (232, 236, 244)
DIM = (120, 130, 148)
TRACK = (34, 38, 50)
WARN = (235, 170, 60)
CRIT = (232, 74, 90)


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


# ------------------------------------------------------------------------- render

def font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def bar(draw, x, y, w, h, frac, color):
    draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=TRACK)
    filled = int(w * max(0.0, min(1.0, frac)))
    if filled > 2:
        draw.rounded_rectangle([x, y, x + filled, y + h], radius=h // 2, fill=color)


def hex_rgb(value, fallback=(120, 140, 200)):
    try:
        v = value.lstrip("#")
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    except (AttributeError, ValueError):
        return fallback


def mascot(draw, x, y, size, mood):
    """Tiny placeholder mascot. Real pixel-art sprites land in T6."""
    eye, mouth = {
        "tranquila": ((255, 255, 255), "smile"),
        "atenta": ((255, 255, 255), "flat"),
        "alarmada": (CRIT, "frown"),
    }[mood]
    body = (38, 44, 60) if mood != "alarmada" else (58, 30, 38)
    draw.rounded_rectangle([x, y, x + size, y + size], radius=12, fill=body)
    ey = y + size // 3
    for ex in (x + size // 3, x + 2 * size // 3):
        draw.ellipse([ex - 5, ey - 5, ex + 5, ey + 5], fill=eye)
    my = y + int(size * 0.68)
    cx = x + size // 2
    if mouth == "smile":
        draw.arc([cx - 14, my - 10, cx + 14, my + 8], 20, 160, fill=FG, width=3)
    elif mouth == "frown":
        draw.arc([cx - 14, my - 2, cx + 14, my + 16], 200, 340, fill=FG, width=3)
    else:
        draw.line([cx - 10, my + 2, cx + 10, my + 2], fill=FG, width=3)


def render(snapshot, state):
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    d = ImageDraw.Draw(img)

    f_title = font("C:/Windows/Fonts/segoeuib.ttf", 17)
    f_label = font("C:/Windows/Fonts/segoeui.ttf", 14)
    f_num = font("C:/Windows/Fonts/consolab.ttf", 15)
    f_small = font("C:/Windows/Fonts/segoeui.ttf", 12)

    d.text((14, 12), "MASCOTA", font=f_title, fill=FG)
    d.text((WIDTH - 14, 15), time.strftime("%H:%M"), font=f_num, fill=DIM, anchor="ra")
    d.line([14, 38, WIDTH - 14, 38], fill=TRACK, width=1)

    # ---- quotas -------------------------------------------------------------
    d.text((14, 48), "CUOTAS", font=f_small, fill=DIM)
    y = 68
    worst = 0.0
    providers = (snapshot or {}).get("providers", [])
    for p in providers:
        windows = p.get("windows") or []
        if not windows:
            continue
        w0 = max(windows, key=lambda w: w.get("usedPercent") or 0)
        used = float(w0.get("usedPercent") or 0)
        worst = max(worst, used)
        accent = hex_rgb((p.get("display") or {}).get("accentColor"))
        color = CRIT if used >= 90 else WARN if used >= 75 else accent

        d.text((14, y), (p.get("name") or p.get("id") or "?")[:12], font=f_label, fill=FG)
        d.text((WIDTH - 14, y), f"{used:.0f}%", font=f_num, fill=color, anchor="ra")
        bar(d, 14, y + 20, WIDTH - 28, 7, used / 100.0, color)
        d.text((14, y + 30), (w0.get("label") or "")[:26], font=f_small, fill=DIM)
        y += 52

    if not providers:
        d.text((14, y), "codexbar no responde", font=f_label, fill=CRIT)
        y += 30

    # ---- jobs + mascot ------------------------------------------------------
    d.line([14, HEIGHT - 116, WIDTH - 14, HEIGHT - 116], fill=TRACK, width=1)
    jobs = [j for j in ((state or {}).get("jobs") or []) if j.get("status") == "running"]
    d.text((14, HEIGHT - 106), "AGENTES", font=f_small, fill=DIM)
    d.text((14, HEIGHT - 88), f"{len(jobs)} activos", font=f_label, fill=FG)
    jy = HEIGHT - 66
    for j in jobs[:3]:
        d.text((14, jy), f"- {(j.get('title') or j.get('agent') or '?')[:20]}",
               font=f_small, fill=DIM)
        jy += 16

    mood = "alarmada" if worst >= 90 else "atenta" if worst >= 75 else "tranquila"
    mascot(d, WIDTH - 78, HEIGHT - 78, 64, mood)
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


def to_rgb565le(img):
    out = bytearray()
    for r, g, b in img.getdata():
        v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        out += v.to_bytes(2, "little")
    return bytes(out)


def push(ser, img, x=0, y=0):
    data = to_rgb565le(img)
    w, h = img.size
    t0 = time.perf_counter()
    ser.write(cmd_bytes(DISPLAY_BITMAP, x, y, x + w - 1, y + h - 1))
    for i in range(0, len(data), CHUNK):
        ser.write(data[i:i + CHUNK])
    ser.flush()
    return time.perf_counter() - t0


def find_port():
    for p in serial.tools.list_ports.comports():
        if p.serial_number == "USB35INCHIPSV2" or (p.vid == 0x1A86 and p.pid == 0x5722):
            return p.device
    return None


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_port()
    if not port:
        print("No encontre la pantalla (USB35INCHIPSV2 / 1A86:5722).")
        return 1

    print("Leyendo datos en vivo...")
    token = read_token()
    print(f"  token codexbar: {'ok' if token else 'NO DISPONIBLE'}")
    snapshot = get_json(f"{CODEXBAR}/dashboard/v1/snapshot", token)
    state = get_json(f"{AGENTHUB}/api/state")
    print(f"  providers: {len((snapshot or {}).get('providers', []))}")
    print(f"  jobs: {len((state or {}).get('jobs', []))}")

    img, mood = render(snapshot, state)
    img.save("first_frame.png")
    print(f"  mascota: {mood}  (preview en first_frame.png)")

    print(f"Puerto: {port}")
    ser = serial.Serial(port, 115200, timeout=1, rtscts=True)
    try:
        dt = push(ser, img)
        print(f"Frame enviado en {dt:.3f}s")
    finally:
        ser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
