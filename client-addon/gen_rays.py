"""Paint ClasslessWildcard/rays.tga, the starburst that turns behind the die.

The reveal already has glow.tga, but that is a soft radial blob: measured across
angles its alpha varies by 9 of 255, so rotating it would look like nothing
moving at all. This draws something with structure instead -- alternating long
and short beams radiating from a hollow centre -- so the addon can spin it and
have the spin read.

White, with all the shape in the alpha channel: the addon tints it per rarity
with SetVertexColor and blends it additively, so one file serves every tier.

The centre is empty because the die covers it, and the alpha falls to zero well
inside the edges. That matters: 3.3.5 has no Texture:SetRotation, so rotation is
done by feeding SetTexCoord a rotated quad, whose corners sample outside 0..1
and clamp to the edge pixels. With a transparent border there is nothing there
to smear.

    python3 gen_rays.py            # writes ClasslessWildcard/rays.tga

Deterministic: same output every run, so a rebuild is a no-op in git unless the
numbers below change.
"""

from __future__ import annotations

import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ClasslessWildcard", "rays.tga")

SIZE = 256          # power of two, as the client requires
SUPERSAMPLE = 3     # per axis, for clean beam edges

BEAMS = 12          # long beams
LONG_SHARPNESS = 7  # higher = narrower
SHORT_WEIGHT = 0.45 # brightness of the short beams between them
SHORT_SHARPNESS = 13

R_HOLE = 0.17       # nothing inside this: the die sits on top of it
R_FULL = 0.27       # full brightness from here
R_EDGE = 0.50       # faded to nothing by here (the texture's own edge)


def smoothstep(a, b, x):
    if b <= a:
        return 0.0
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3.0 - 2.0 * t)


def alpha_at(u, v):
    """u, v are -0.5 .. 0.5 across the texture."""
    r = math.hypot(u, v)
    if r >= R_EDGE or r <= 0.0:
        return 0.0
    radial = smoothstep(R_HOLE, R_FULL, r) * (1.0 - smoothstep(R_FULL, R_EDGE, r))
    if radial <= 0.0:
        return 0.0
    theta = math.atan2(v, u)
    long_beam = max(0.0, math.cos(BEAMS * theta)) ** LONG_SHARPNESS
    short_beam = max(0.0, math.cos(BEAMS * theta + math.pi)) ** SHORT_SHARPNESS
    return radial * min(1.0, long_beam + SHORT_WEIGHT * short_beam)


def build():
    step = 1.0 / (SIZE * SUPERSAMPLE)
    rows = []
    for y in range(SIZE):
        row = bytearray()
        for x in range(SIZE):
            total = 0.0
            for sy in range(SUPERSAMPLE):
                v = (y + (sy + 0.5) / SUPERSAMPLE) / SIZE - 0.5
                for sx in range(SUPERSAMPLE):
                    u = (x + (sx + 0.5) / SUPERSAMPLE) / SIZE - 0.5
                    total += alpha_at(u, v)
            a = int(round(255.0 * total / (SUPERSAMPLE * SUPERSAMPLE)))
            a = min(255, max(0, a))
            row += bytes((255, 255, 255, a))    # BGRA, white
        rows.append(bytes(row))
    # TGA is stored bottom-up (descriptor 0x08, same as the addon's other art)
    return b"".join(reversed(rows))


def main():
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x08)
    data = build()
    with open(OUT, "wb") as fh:
        fh.write(header)
        fh.write(data)
    print("wrote %s (%d x %d, %d bytes)" % (OUT, SIZE, SIZE, len(header) + len(data)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
