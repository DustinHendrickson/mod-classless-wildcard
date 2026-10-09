"""Normal faces in the Death Knight skin tones, painted from the player's own client.

Blizzard drew the three Death Knight skin colours for only three faces per race
and sex, and painted those three with the Death Knight's glowing blue eyes. So
a Hero who picks a normal face and a Death Knight skin had nothing to wear but
one of those glowing faces. This makes the missing art at install time, from
the client's own textures; nothing derived from Blizzard art is stored in the
repository.

For each race and sex, and each Death Knight skin colour:

1. A tone map is fitted on the BODY skin textures: the normal skin (colour 0)
   and the Death Knight skin are the same artwork in two tones, so their pixel
   pairs say exactly how one tone becomes the other. A quadratic RGB -> RGB
   least-squares fit over a sample of those pairs; it reproduces Blizzard's
   Death Knight body skins to within a few levels out of 255.
2. The map only touches skin, which is everything except what is clearly not
   skin: near-white (eye whites), or a colour the normal body skin never uses
   that is also more than 45 degrees from its hue and saturated above 0.25
   (irises, jewellery). Those keep their own colour, so the face keeps its
   eyes. Skin in a colour the body itself never uses (a Tauren's brown
   muzzle on a grey body) is first swapped for the body's own colour at the
   same brightness, because the fit has seen nothing like it and would guess.
3. Map and mask are both functions of the colour alone, so they bake into one
   33-point 3D lookup table that Pillow applies in C.

Every normal face's own textures at colour 0 then go through that table and
are written as palettized BLP2 (the format Blizzard ships faces in), named
`cw_<original name>_dk<colour>.blp` beside the originals.

Needs Pillow; numpy is not used.
"""

from __future__ import annotations

import struct

from . import blp
from . import dbc

SOURCE_COLOUR = 0
SAMPLE_STEP = 7          # every 7th body pixel feeds the fit
LUT_SIZE = 33
BINS = 32                 # colour grid for "does the body skin use this colour"
MIN_SATURATION = 0.1      # below this a body pixel has no meaningful hue
OTHER_HUE = 45 / 360.0    # further than this from the skin hue ...
VIVID = 0.25              # ... and more saturated than this: not skin
WHITE_VALUE = 0.85        # brighter than this ...
WHITE_SATURATION = 0.12   # ... and greyer than this: an eye white


class FaceError(RuntimeError):
    pass


def _features(r, g, b):
    return (1.0, r, g, b, r * r, g * g, b * b, r * g, r * b, g * b)


def _solve(ata, aty):
    """Solve the 10x10 normal equations by Gaussian elimination (3 right-hand sides)."""
    n = len(ata)
    m = [row[:] + list(rhs) for row, rhs in zip(ata, aty)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            raise FaceError("tone map fit is singular")
        m[col], m[pivot] = m[pivot], m[col]
        p = m[col][col]
        m[col] = [v / p for v in m[col]]
        for r in range(n):
            if r != col and m[r][col]:
                f = m[r][col]
                m[r] = [a - f * b for a, b in zip(m[r], m[col])]
    return [[m[i][n + k] for k in range(3)] for i in range(n)]   # coef[feature][channel]


def _image(files, path):
    from PIL import Image
    width, height, rgba = blp.decode_blp(files.find(path)[0])
    return Image.frombytes("RGBA", (width, height), rgba)


def fit_tone_map(body_src, body_dk):
    """Quadratic RGB fit from the normal body skin to the Death Knight one."""
    from PIL import Image
    if body_src.size != body_dk.size:
        body_src = body_src.resize(body_dk.size, Image.LANCZOS)
    src = body_src.tobytes()
    dst = body_dk.convert("RGB").tobytes()
    ata = [[0.0] * 10 for _ in range(10)]
    aty = [[0.0] * 3 for _ in range(10)]
    pixels = body_dk.size[0] * body_dk.size[1]
    used = 0
    for i in range(0, pixels, SAMPLE_STEP):
        if src[i * 4 + 3] < 128:
            continue
        x = _features(src[i * 4] / 255.0, src[i * 4 + 1] / 255.0, src[i * 4 + 2] / 255.0)
        y = (dst[i * 3] / 255.0, dst[i * 3 + 1] / 255.0, dst[i * 3 + 2] / 255.0)
        for a in range(10):
            xa = x[a]
            row = ata[a]
            for b in range(a, 10):
                row[b] += xa * x[b]
            ya = aty[a]
            ya[0] += xa * y[0]
            ya[1] += xa * y[1]
            ya[2] += xa * y[2]
        used += 1
    if used < 1000:
        raise FaceError("too few body pixels to fit a tone map (%d)" % used)
    for a in range(10):
        for b in range(a):
            ata[a][b] = ata[b][a]
    return _solve(ata, aty)


def _hue_sat(r, g, b):
    mx, mn = max(r, g, b), min(r, g, b)
    sat = 0.0 if mx == 0 else (mx - mn) / mx
    if mx == mn:
        return 0.0, sat
    d = mx - mn
    if mx == r:
        h = ((g - b) / d) % 6
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h / 6.0, sat


def skin_model(body_src):
    """The colours the body's skin uses (a 32-level grid, grown one step) and
    its median hue."""
    data = body_src.tobytes()
    occupied = set()
    hues = []
    by_level = [[0, 0, 0, 0] for _ in range(BINS)]
    for i in range(0, len(data), 4):
        if data[i + 3] < 128:
            continue
        r, g, b = data[i], data[i + 1], data[i + 2]
        occupied.add((r * BINS // 256, g * BINS // 256, b * BINS // 256))
        acc = by_level[_luma(r, g, b) * BINS // 256]
        acc[0] += r
        acc[1] += g
        acc[2] += b
        acc[3] += 1
        if i % (4 * SAMPLE_STEP) == 0:
            h, s = _hue_sat(r / 255.0, g / 255.0, b / 255.0)
            if s >= MIN_SATURATION:
                hues.append(h)
    if not hues:
        raise FaceError("no saturated body pixels to read the skin hue from")
    grown = set()
    for (r, g, b) in occupied:
        for dr in (-1, 0, 1):
            for dg in (-1, 0, 1):
                for db in (-1, 0, 1):
                    grown.add((r + dr, g + dg, b + db))
    hues.sort()
    # the body's average colour at each brightness level; a level the body
    # never reaches borrows the nearest one that it does
    known = [i for i, acc in enumerate(by_level) if acc[3]]
    shade = []
    for level in range(BINS):
        acc = by_level[min(known, key=lambda k: abs(k - level))]
        shade.append((acc[0] / acc[3] / 255.0, acc[1] / acc[3] / 255.0,
                      acc[2] / acc[3] / 255.0))
    return grown, hues[len(hues) // 2], shade


def _luma(r, g, b):
    return (299 * r + 587 * g + 114 * b) // 1000


def keeps_own_colour(r, g, b, skin):
    """True for what is clearly not skin, which keeps its own colour:
    near-white (eye whites), or a colour the body skin never uses that is also
    far from its hue and clearly saturated (irises, jewellery). Everything
    else is skin and is recoloured. All three tests are needed: by hue alone a
    Blood Elf's fel-green eyes looked like skin, and by the body's colours
    alone a Tauren's brown muzzle did not."""
    grown, skin_hue, _shade = skin
    h, s = _hue_sat(r, g, b)
    if max(r, g, b) > WHITE_VALUE and s < WHITE_SATURATION:
        return True
    q = (min(int(r * BINS), BINS - 1), min(int(g * BINS), BINS - 1),
         min(int(b * BINS), BINS - 1))
    if q in grown:
        return False
    dh = abs(h - skin_hue)
    dh = min(dh, 1 - dh)
    return dh > OTHER_HUE and s > VIVID


def build_lut(coef, skin):
    from PIL import ImageFilter

    grown, _hue, shade = skin

    def transform(r, g, b):
        if keeps_own_colour(r, g, b, skin):
            return r, g, b
        q = (min(int(r * BINS), BINS - 1), min(int(g * BINS), BINS - 1),
             min(int(b * BINS), BINS - 1))
        if q not in grown:
            # skin in a colour the body never uses (a Tauren's brown muzzle
            # on a grey body): the fit has seen nothing like it and would
            # guess, so use the body's own colour at the same brightness
            r, g, b = shade[min(_luma(int(r * 255), int(g * 255), int(b * 255)) * BINS // 256, BINS - 1)]
        x = _features(r, g, b)
        out = []
        for k in range(3):
            v = sum(x[i] * coef[i][k] for i in range(10))
            out.append(0.0 if v < 0 else 1.0 if v > 1 else v)
        return tuple(out)

    return ImageFilter.Color3DLUT.generate(LUT_SIZE, transform)


def generated_name(path, colour):
    """Character\\Human\\Male\\HumanMaleFaceLower05_00.blp ->
    Character\\Human\\Male\\cw_HumanMaleFaceLower05_00_dk12.blp"""
    folder, _sep, base = path.rpartition("\\")
    stem = base[:-4] if base.lower().endswith(".blp") else base
    return "%s\\cw_%s_dk%d.blp" % (folder, stem, colour)


def is_generated_name(name):
    lowered = name.lower().replace("/", "\\")
    return (lowered.startswith("character\\") and "\\cw_" in lowered
            and "_dk" in lowered and lowered.endswith(".blp"))


def generate(files, stock):
    """Paint every normal face in every Death Knight skin colour.

    `stock` is the client's own CharSections.dbc (Death Knight rows still
    carrying 0x4). Returns (textures, faces): textures maps an archive path to
    BLP bytes; faces lists (race, sex, face, colour, lower_path, upper_path).
    """
    count, fields, size, string_size = dbc.parse_header(stock)
    strings = stock[20 + count * size:20 + count * size + string_size]
    rows = [struct.unpack_from("<10I", stock, 20 + i * size) for i in range(count)]
    by_key = {(r[1], r[2], r[3], r[8], r[9]): r for r in rows}

    def text(offset):
        return dbc.read_string(strings, offset) if offset else ""

    dk_colours = {}
    for r in rows:
        if r[3] == dbc.CHARSECTION_SKIN and r[7] & dbc.CHARSECTION_DEATH_KNIGHT_ONLY:
            dk_colours.setdefault((r[1], r[2]), set()).add(r[9])

    textures, faces = {}, []
    for (race, sex), colours in sorted(dk_colours.items()):
        body_row = by_key.get((race, sex, dbc.CHARSECTION_SKIN, 0, SOURCE_COLOUR))
        if not body_row:
            continue
        body_src = _image(files, text(body_row[4])).convert("RGBA")
        skin = skin_model(body_src)
        normal = sorted(v for (ra, se, sec, v, c), r in by_key.items()
                        if (ra, se, sec, c) == (race, sex, dbc.CHARSECTION_FACE, SOURCE_COLOUR)
                        and not r[7] & dbc.CHARSECTION_DEATH_KNIGHT_ONLY)
        sources = {}
        for face in normal:
            r = by_key[(race, sex, dbc.CHARSECTION_FACE, face, SOURCE_COLOUR)]
            sources[face] = (text(r[4]), text(r[5]))
        for colour in sorted(colours):
            dk_row = by_key[(race, sex, dbc.CHARSECTION_SKIN, 0, colour)]
            body_dk = _image(files, text(dk_row[4]))
            lut = build_lut(fit_tone_map(body_src, body_dk), skin)
            for face in normal:
                out_paths = []
                for path in sources[face]:
                    name = generated_name(path, colour)
                    if name not in textures:
                        painted = _image(files, path).convert("RGB").filter(lut)
                        textures[name] = blp.encode_palettized_opaque(painted)
                    out_paths.append(name)
                faces.append((race, sex, face, colour, out_paths[0], out_paths[1]))
    return textures, faces
