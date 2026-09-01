"""Rebuild the addon's die textures from the new artwork.

Sources (dropped into the addon folder):
    mystery_die_<rarity>_transparent.png  -> reveal frames, centre is the window
    icon.png                              -> the closed die crest, with the "?"

Everything is written as 32-bit uncompressed bottom-up TGA (desc 0x08), which
is what the existing files are and what the 3.3.5 client reads. Sizes are kept
identical to the files being replaced so no layout code has to move.
"""
import io, os, struct, math
from PIL import Image

ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "ClasslessWildcard")
SRC = os.path.dirname(os.path.abspath(__file__))
os.chdir(SRC)   # read the PNG masters from here

RARITY = ["common", "uncommon", "rare", "epic", "legendary"]


def write_tga(im, path):
    """32-bit uncompressed, bottom-up, 8 alpha bits -- matches the originals."""
    im = im.convert("RGBA")
    w, h = im.size
    hdr = bytes([0, 0, 2, 0, 0, 0, 0, 0]) + struct.pack("<HHHH", 0, 0, w, h) + bytes([32, 0x08])
    rows = []
    px = im.load()
    for y in range(h - 1, -1, -1):          # bottom-up
        row = bytearray()
        for x in range(w):
            r, g, b, a = px[x, y]
            row += bytes((b, g, r, a))      # BGRA on disk
        rows.append(bytes(row))
    io.open(os.path.join(ART, path), "wb").write(hdr + b"".join(rows))  # outputs go to the addon
    print("  wrote %-22s %dx%d" % (os.path.basename(path), w, h))


def square_trim(im):
    """Crop to the artwork's own bounds, then pad to a centred square."""
    im = im.convert("RGBA")
    bbox = im.getchannel("A").getbbox()
    if bbox:
        im = im.crop(bbox)
    w, h = im.size
    side = max(w, h)
    out = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    out.paste(im, ((side - w) // 2, (side - h) // 2))
    return out


def fitted(path, size):
    return square_trim(Image.open(path)).resize((size, size), Image.LANCZOS)


# ---- 1. die_reveal.tga: 4x2 atlas of 256px rarity frames -------------------
print("die_reveal.tga (rarity frames, transparent centre):")
atlas = Image.new("RGBA", (1024, 512), (0, 0, 0, 0))
for i, rar in enumerate(RARITY):
    cell = fitted("mystery_die_%s_transparent.png" % rar, 256)
    atlas.paste(cell, ((i % 4) * 256, (i // 4) * 256))
    print("  cell %d %-10s <- mystery_die_%s_transparent.png" % (i, rar, rar))
write_tga(atlas, "die_reveal.tga")

# ---- 2. icon.tga: the closed crest ----------------------------------------
print("icon.tga (panel crest / minimap):")
write_tga(fitted("icon.png", 64), "icon.tga")

# ---- 3. micro_die: ONE crest, placed where the original had it -------------
# The 128x256 sheet is not two stacked frames -- the original holds a single
# die low in the canvas (measured bbox x 11..116, y 120..228) and the pushed
# variant is the same art nudged 4px down. Pasting it twice put a second die on
# the micro button, which is exactly what it looked like.
print("micro_die.tga / micro_die_down.tga:")
CREST_PX, CREST_X, CREST_Y = 108, 10, 120
crest = fitted("icon.png", CREST_PX)
for name, dy in (("micro_die.tga", 0), ("micro_die_down.tga", 4)):
    sheet = Image.new("RGBA", (128, 256), (0, 0, 0, 0))
    sheet.paste(crest, (CREST_X, CREST_Y + dy))
    write_tga(sheet, name)

# ---- 4. d20_spin.tga: 8x2 atlas of 128px spin frames ----------------------
print("d20_spin.tga (16 rotation frames):")
spin = Image.new("RGBA", (1024, 256), (0, 0, 0, 0))
base = square_trim(Image.open("mystery_die_rare.png"))
for f in range(16):
    ang = -360.0 * f / 16.0
    frame = base.rotate(ang, resample=Image.BICUBIC, expand=False)
    frame = frame.resize((128, 128), Image.LANCZOS)
    spin.paste(frame, ((f % 8) * 128, (f // 8) * 128))
write_tga(spin, "d20_spin.tga")

print("\ndone")
