"""Paint ClasslessWildcard/heart_full.tga and heart_empty.tga, the life pips.

A challenge run counts lives, and the addon draws them in three places: the
challenge list, the challenge screen's Lives section and the panel header.
The client ships no plain heart -- every heart in its files is a whole spell
or item icon with its own painted background, which reads as a little square
at 12 to 16 pixels -- so these are drawn here, the way rays.tga is.

  heart_full.tga   a life in hand: a red heart with a dark rim and a glint
  heart_empty.tga  a life lost: the same heart, dark and hollow

Both are 32 x 32, 32-bit with alpha, stored bottom-up like the addon's other
art, and supersampled so the edge is smooth when the client scales them down.

    python3 gen_hearts.py          # writes both into ClasslessWildcard/
"""

from __future__ import annotations

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "ClasslessWildcard")
SIZE = 32
SUPERSAMPLE = 6


def inside(x, y, scale):
    """The classic implicit heart, (x^2 + y^2 - 1)^3 - x^2 y^3 <= 0."""
    x /= scale
    y /= scale
    a = x * x + y * y - 1.0
    return a * a * a - x * x * y * y * y <= 0.0


def heart_coords(u, v):
    """Pixel space (u, v in -0.5..0.5, v down) to heart space (y up)."""
    return u * 2.7, -v * 2.7 + 0.08


def sample(u, v, full):
    """One supersample: (r, g, b, a) in 0..1."""
    x, y = heart_coords(u, v)
    if not inside(x, y, 1.0):
        return (0.0, 0.0, 0.0, 0.0)
    if not inside(x, y, 0.80):
        # the rim
        return (0.22, 0.02, 0.04, 1.0) if full else (0.42, 0.36, 0.36, 0.95)
    if not full:
        return (0.10, 0.07, 0.08, 0.85)
    # the body: brighter at the top, deeper at the point
    t = min(1.0, max(0.0, (v + 0.5)))
    r = 0.93 - 0.35 * t
    g = 0.16 - 0.12 * t
    b = 0.20 - 0.14 * t
    # a glint on the upper left lobe
    gx, gy = x + 0.42, y - 0.38
    if gx * gx / 0.05 + gy * gy / 0.025 <= 1.0:
        r, g, b = r + (1 - r) * 0.65, g + (1 - g) * 0.65, b + (1 - b) * 0.65
    return (r, g, b, 1.0)


def build(full):
    rows = []
    n = SUPERSAMPLE * SUPERSAMPLE
    for y in range(SIZE):
        row = bytearray()
        for x in range(SIZE):
            pr = pg = pb = pa = 0.0
            for sy in range(SUPERSAMPLE):
                v = (y + (sy + 0.5) / SUPERSAMPLE) / SIZE - 0.5
                for sx in range(SUPERSAMPLE):
                    u = (x + (sx + 0.5) / SUPERSAMPLE) / SIZE - 0.5
                    r, g, b, a = sample(u, v, full)
                    pr += r * a
                    pg += g * a
                    pb += b * a
                    pa += a
            if pa > 0:
                r, g, b = pr / pa, pg / pa, pb / pa
            else:
                r = g = b = 0.0
            a = pa / n

            def byte(c):
                return min(255, max(0, int(round(c * 255))))

            row += bytes((byte(b), byte(g), byte(r), byte(a)))   # BGRA
        rows.append(bytes(row))
    # TGA is stored bottom-up (descriptor 0x08, same as the addon's other art)
    return b"".join(reversed(rows))


def write(name, full):
    path = os.path.join(OUT_DIR, name)
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x08)
    data = build(full)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(data)
    print("wrote %s (%d x %d, %d bytes)" % (path, SIZE, SIZE, len(header) + len(data)))


def main():
    write("heart_full.tga", True)
    write("heart_empty.tga", False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
