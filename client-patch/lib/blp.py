"""Write BLP2 textures the 3.3.5a client can read, and draw the Hero icon.

Only what the client patch needs: encode a 256-colour palettized BLP2 (the most
broadly supported uncompressed BLP format) and render the class-icon atlas so
every class shows one "Hero" emblem instead of its old class icon.

Palettized BLP2 layout (encoding 1, 8-bit alpha, full mip chain) -- matched
byte-for-byte against the genuine enc=1 textures the 3.3.5a client ships
(header 01 08 08 01: encoding 1, alphaDepth 8, alphaType 8, hasMips 1):

    "BLP2"                     4 bytes
    type            uint32     1
    encoding        uint8      1  (palettized)
    alphaDepth      uint8      8
    alphaType       uint8      8  (8-bit alpha; NOT 0 -- 0 fails to load)
    hasMips         uint8      1  (a full mip chain IS required, or icons break)
    width           uint32
    height          uint32
    mipOffsets[16]  uint32
    mipSizes[16]    uint32
    palette[256]    BGRA       1024 bytes
    per mip level:  <w*h index bytes><w*h alpha bytes>, halving down to 1x1

Rendering uses Pillow if present; if it is not, the whole Hero-icon step is
skipped by the installer, so this stays an optional extra with no hard
dependency.
"""

from __future__ import annotations

import struct

_HEADER_BYTES = 8 + 4 + 4 + 4 + 64 + 64  # through mipSizes
_PALETTE_BYTES = 256 * 4
_PIXELS_OFFSET = _HEADER_BYTES + _PALETTE_BYTES


def encode_palettized(image) -> bytes:
    """Encode a Pillow RGBA image as a palettized BLP2 with a full mip chain."""
    from PIL import Image

    width, height = image.size

    # one palette, built from the base level and reused for every mip
    palette = []
    palette_index = {}

    def index_of(rgb):
        idx = palette_index.get(rgb)
        if idx is None:
            if len(palette) < 256:
                idx = len(palette)
                palette_index[rgb] = idx
                palette.append(rgb)
            else:
                idx = _nearest(palette, rgb)
                palette_index[rgb] = idx
        return idx

    # build the mip chain: (indices, alpha) per level
    levels = []
    mip = image.convert("RGBA")
    w, h = width, height
    while True:
        rgba = mip.tobytes()
        indices = bytearray(w * h)
        alpha = bytearray(w * h)
        for i in range(w * h):
            r, g, b, a = rgba[i * 4:i * 4 + 4]
            alpha[i] = a
            indices[i] = index_of((r, g, b))
        levels.append((bytes(indices), bytes(alpha)))
        if w == 1 and h == 1:
            break
        w = max(1, w // 2)
        h = max(1, h // 2)
        mip = mip.resize((w, h), Image.LANCZOS)

    pal_bytes = bytearray()
    for r, g, b in palette:
        pal_bytes += bytes((b, g, r, 0))          # BGRA, palette alpha unused
    pal_bytes += bytes(_PALETTE_BYTES - len(pal_bytes))

    mip_offsets = [0] * 16
    mip_sizes = [0] * 16
    offset = _PIXELS_OFFSET
    body = bytearray()
    for i, (indices, alpha) in enumerate(levels):
        mip_offsets[i] = offset
        mip_sizes[i] = len(indices) + len(alpha)
        body += indices + alpha
        offset += mip_sizes[i]

    out = bytearray()
    out += b"BLP2"
    out += struct.pack("<I", 1)                    # type
    out += bytes((1, 8, 8, 1))                     # enc, alphaDepth, alphaType, hasMips
    out += struct.pack("<II", width, height)
    out += struct.pack("<16I", *mip_offsets)
    out += struct.pack("<16I", *mip_sizes)
    out += bytes(pal_bytes)
    out += bytes(body)
    return bytes(out)


def _nearest(palette, key):
    r, g, b = key
    best, bd = 0, 1 << 30
    for i, (pr, pg, pb) in enumerate(palette):
        d = (pr - r) ** 2 + (pg - g) ** 2 + (pb - b) ** 2
        if d < bd:
            best, bd = i, d
    return best


def have_pillow() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def render_hero_class_atlas(size=256, cells=4):
    """Draw the class-icon atlas: every cell the same round gold "Hero" sigil.

    Returns BLP2 bytes, or None if Pillow is not installed. Every class token
    maps to a cell of this 4x4 atlas, and all classes are Hero, so filling each
    cell with the same emblem makes the Hero icon show everywhere a class icon
    would (character select, unit frames).
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    cell = size // cells
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    emblem = _draw_emblem(cell)
    for cy in range(cells):
        for cx in range(cells):
            img.paste(emblem, (cx * cell, cy * cell), emblem)

    return encode_palettized(img)


def _draw_emblem(cell):
    """One round Hero sigil: dark disc, gold rim, gold upward chevron + star."""
    from PIL import Image, ImageDraw

    # supersample for smoother edges, then downscale
    scale = 4
    s = cell * scale
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    pad = int(s * 0.06)
    disc = (pad, pad, s - pad, s - pad)
    gold = (230, 196, 106, 255)
    gold_dim = (150, 120, 54, 255)
    dark = (20, 22, 30, 255)

    d.ellipse(disc, fill=dark, outline=gold, width=max(2, s // 32))
    d.ellipse((disc[0] + s // 20, disc[1] + s // 20,
               disc[2] - s // 20, disc[3] - s // 20),
              outline=gold_dim, width=max(1, s // 64))

    cx, cyc = s / 2, s / 2
    # upward chevron (a hero's mark)
    w = s * 0.26
    top = cyc - s * 0.20
    bot = cyc + s * 0.02
    thick = s * 0.11
    d.line([(cx - w, bot), (cx, top), (cx + w, bot)], fill=gold,
           width=int(thick), joint="curve")
    # a small four-point star below
    sy = cyc + s * 0.20
    r1, r2 = s * 0.11, s * 0.045
    pts = []
    import math
    for k in range(8):
        ang = math.pi / 2 + k * math.pi / 4
        rr = r1 if k % 2 == 0 else r2
        pts.append((cx + rr * math.cos(ang), sy - rr * math.sin(ang)))
    d.polygon(pts, fill=gold)

    return im.resize((cell, cell), Image.LANCZOS)
