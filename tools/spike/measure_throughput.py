# SPDX-License-Identifier: GPL-3.0-or-later
#
# Spike descartable (ODD T1): mide el throughput real de la Turing Smart Screen 3.5" Rev A.
#
# No es codigo de produccion. Implementa el protocolo a mano, a proposito, para no depender
# del resto del repo y poder correr desde Windows con solo pyserial instalado.
#
# Uso:  py -3.13 measure_throughput.py [COM3]

import sys
import time

import serial
import serial.tools.list_ports

DISPLAY_BITMAP = 197
WIDTH, HEIGHT = 320, 480
CHUNK = WIDTH * 8  # mismo tamano de chunk que usa el upstream


def find_port():
    for p in serial.tools.list_ports.comports():
        if p.serial_number == "USB35INCHIPSV2":
            return p.device
        if p.vid == 0x1A86 and p.pid == 0x5722:
            return p.device
    return None


def cmd_bytes(cmd, x, y, ex, ey):
    """Trama de 6 bytes del protocolo Rev A (ver library/lcd/lcd_comm_rev_a.py)."""
    b = bytearray(6)
    b[0] = (x >> 2) & 0xFF
    b[1] = (((x & 3) << 6) + (y >> 4)) & 0xFF
    b[2] = (((y & 15) << 4) + (ex >> 6)) & 0xFF
    b[3] = (((ex & 63) << 2) + (ey >> 8)) & 0xFF
    b[4] = ey & 0xFF
    b[5] = cmd
    return bytes(b)


def solid_rgb565(w, h, rgb):
    r, g, b = rgb
    v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    return v.to_bytes(2, "little") * (w * h)


def blit(ser, x, y, w, h, color):
    """Manda una region solida y devuelve (segundos, bytes_de_pixeles)."""
    data = solid_rgb565(w, h, color)
    t0 = time.perf_counter()
    ser.write(cmd_bytes(DISPLAY_BITMAP, x, y, x + w - 1, y + h - 1))
    for i in range(0, len(data), CHUNK):
        ser.write(data[i:i + CHUNK])
    ser.flush()
    return time.perf_counter() - t0, len(data)


def bench(ser, label, x, y, w, h, runs=5):
    colors = [(20, 20, 30), (200, 40, 60), (40, 180, 120), (220, 190, 40), (60, 90, 220)]
    times = []
    payload = 0
    for i in range(runs):
        dt, payload = blit(ser, x, y, w, h, colors[i % len(colors)])
        times.append(dt)
    times.sort()
    median = times[len(times) // 2]
    kbs = (payload / 1024) / median if median else float("inf")
    fps = 1 / median if median else float("inf")
    print(f"{label:<22} {payload:>9,} B  "
          f"min {min(times):6.3f}s  med {median:6.3f}s  max {max(times):6.3f}s  "
          f"{kbs:7.1f} kB/s  {fps:6.2f} fps")
    return median, payload


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_port()
    if not port:
        print("No encontre la pantalla (USB35INCHIPSV2 / 1A86:5722). "
              "Pasa el puerto como argumento.")
        return 1

    print(f"Puerto: {port}")
    ser = serial.Serial(port, 115200, timeout=1, rtscts=True)
    try:
        # Una escritura de calentamiento para no medir el costo de abrir el puerto.
        blit(ser, 0, 0, 64, 64, (0, 0, 0))
        print()
        print(f"{'region':<22} {'payload':>11}  {'min':>10} {'mediana':>11} {'max':>10}"
              f"  {'throughput':>13}  {'fps':>10}")
        print("-" * 100)
        bench(ser, "frame 320x480", 0, 0, WIDTH, HEIGHT, runs=3)
        bench(ser, "banda 320x64", 0, 0, WIDTH, 64)
        bench(ser, "sprite 96x96", 0, 0, 96, 96)
        bench(ser, "sprite 64x64", 0, 0, 64, 64)
        bench(ser, "numero 48x16", 0, 0, 48, 16, runs=10)
        print()
    finally:
        ser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
