"""Write BLP2 textures the 3.3.5a client can read, and draw the Hero icon.

Only what the client patch needs: encode a 256-colour palettized BLP2 (the most
broadly supported uncompressed BLP format) and render the class-icon atlas so
every class shows one "Hero" emblem instead of its old class icon.

Palettized BLP2 layout (encoding 1, 8-bit alpha, no mipmaps):

    "BLP2"                     4 bytes
    type            uint32     1
    encoding        uint8      1  (palettized)
    alphaDepth      uint8      8
    alphaEncoding   uint8      0
    hasMips         uint8      0
    width           uint32
    height          uint32
    mipOffsets[16]  uint32     [0] points at the pixel data
    mipSizes[16]    uint32     [0] = width*height*2 (indices + alpha)
    palette[256]    BGRA       1024 bytes
    <width*height index bytes><width*height alpha bytes>

Rendering uses Pillow if present; if it is not, the whole Hero-icon step is
skipped by the installer, so this stays an optional extra with no hard
dependency.
"""

from __future__ import annotations

import struct

_HEADER_BYTES = 8 + 4 + 4 + 4 + 64 + 64  # through mipSizes
_PALETTE_BYTES = 256 * 4
_PIXELS_OFFSET = _HEADER_BYTES + _PALETTE_BYTES


def encode_palettized(rgba, width, height) -> bytes:
    """Encode a flat RGBA byte sequence (len == width*height*4) as BLP2."""
    if len(rgba) != width * height * 4:
        raise ValueError("rgba length does not match dimensions")

    # build a <=256 colour palette from the opaque RGB values
    palette = []
    palette_index = {}
    indices = bytearray(width * height)
    alpha = bytearray(width * height)

    for i in range(width * height):
        r, g, b, a = rgba[i * 4:i * 4 + 4]
        alpha[i] = a
        key = (r, g, b)
        idx = palette_index.get(key)
        if idx is None:
            if len(palette) < 256:
                idx = len(palette)
                palette_index[key] = idx
                palette.append(key)
            else:
                idx = _nearest(palette, key)
        indices[i] = idx

    pal_bytes = bytearray()
    for r, g, b in palette:
        pal_bytes += bytes((b, g, r, 0))          # BGRA, pad alpha 0
    pal_bytes += bytes(_PALETTE_BYTES - len(pal_bytes))

    mip_offsets = [0] * 16
    mip_sizes = [0] * 16
    mip_offsets[0] = _PIXELS_OFFSET
    mip_sizes[0] = width * height * 2

    out = bytearray()
    out += b"BLP2"
    out += struct.pack("<I", 1)                    # type
    out += bytes((1, 8, 0, 0))                     # enc, alphaDepth, alphaEnc, mips
    out += struct.pack("<II", width, height)
    out += struct.pack("<16I", *mip_offsets)
    out += struct.pack("<16I", *mip_sizes)
    out += bytes(pal_bytes)
    out += bytes(indices)
    out += bytes(alpha)
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

    rgba = img.tobytes()
    return encode_palettized(rgba, size, size)


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
