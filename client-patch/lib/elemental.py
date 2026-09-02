"""Elemental ability variants, client side.

The generator (data/sql/generators/gen_elemental_variants.py) writes the
server's spell rows and, from the same run, elemental_manifest.json. This
module turns that manifest into the client's half:

  Spell.dbc             one appended row per variant rank, copied from the
                        base spell's own row in THIS player's client and
                        patched with the manifest's field overrides and text
  SpellVisual.dbc       one row per variant: the base visual with the
                        element's impact kit
  SpellIcon.dbc         one row per (base icon, element)
  SkillLineAbility.dbc  one row per variant, so it files under its base's tab
  Interface/Icons/      one painted icon per (base icon, element), built from
                        the player's own copy of the base icon

Everything is appended to the player's own tables, so a community patch's
rows survive, and nothing of Blizzard's is carried in the repository: the
manifest holds ids, overrides and text, not copies of rows or art.

Pillow is optional. Without it the variants still work and simply show their
base's icon.
"""

from __future__ import annotations

import json
import math
import os
import struct

from . import blp, dbc

SPELL = "DBFilesClient\\Spell.dbc"
SPELLVISUAL = "DBFilesClient\\SpellVisual.dbc"
SPELLICON = "DBFilesClient\\SpellIcon.dbc"
SKILLLINEABILITY = "DBFilesClient\\SkillLineAbility.dbc"
ICON_DIR = "Interface\\Icons\\"

SPELL_FIELDS = 234
SPELLVISUAL_FIELDS = 32
SPELLICON_FIELDS = 2
SLA_FIELDS = 14
VISUAL_IMPACT_KIT = 3

# Spell.dbc float columns; everything else is an integer or a string offset
FLOAT_FIELDS = {47} | set(range(77, 80)) | set(range(101, 104)) \
    | set(range(119, 122)) | set(range(216, 219)) | set(range(229, 232))
# (first locale column, mask column) for name, rank, description, tooltip
LOCALE_BLOCKS = ((136, 152), (153, 169), (170, 186), (187, 203))


class ElementalError(ValueError):
    pass


def manifest_path():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "elemental_manifest.json")


def load_manifest(path=None):
    path = path or manifest_path()
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("version") != 1:
        raise ElementalError("elemental manifest version %r is not understood" % data.get("version"))
    return data


# ----------------------------------------------------------------- dbc plumbing

def _split(data: bytes, expected_fields: int, name: str):
    count, fields, rec, strsize = dbc.parse_header(data)
    if fields != expected_fields:
        raise dbc.DbcError("%s has %d fields, expected %d. This client build is not "
                           "the 3.3.5a layout this patch understands." % (name, fields, expected_fields))
    records_off = 20
    strings_off = records_off + count * rec
    return (count, fields, rec,
            bytearray(data[records_off:strings_off]),
            bytearray(data[strings_off:strings_off + strsize]))


def _join(count, fields, rec, records, strings) -> bytes:
    header = dbc.WDBC_MAGIC + struct.pack("<4I", count, fields, rec, len(strings))
    return header + bytes(records) + bytes(strings)


def _ids(records, rec, count):
    return {struct.unpack_from("<I", records, i * rec)[0]: i for i in range(count)}


def _add_string(strings: bytearray, text: str) -> int:
    off = len(strings)
    strings += text.encode("utf-8") + b"\0"
    return off


# ----------------------------------------------------------------- appenders

def append_spells(data: bytes, variants):
    """Append one Spell.dbc row per variant. Returns (bytes, added, missing_bases)."""
    count, fields, rec, records, strings = _split(data, SPELL_FIELDS, "Spell.dbc")
    ids = _ids(records, rec, count)
    added, missing = 0, []
    for v in variants:
        if v["id"] in ids:
            continue
        base_row = ids.get(v["base"])
        if base_row is None:
            missing.append(v["base"])
            continue
        row = bytearray(records[base_row * rec:(base_row + 1) * rec])
        for key, value in v["fields"].items():
            idx = int(key)
            if idx in FLOAT_FIELDS:
                struct.pack_into("<f", row, idx * 4, float(value))
            elif int(value) < 0:
                struct.pack_into("<i", row, idx * 4, int(value))
            else:
                struct.pack_into("<I", row, idx * 4, int(value))
        # the same English text in every locale column, so a client of any
        # locale reads it; the mask bits stay as the base row had them
        texts = (v["name"], v.get("rank_text", ""), v["description"], "")
        for (first, mask), text in zip(LOCALE_BLOCKS, texts):
            off = _add_string(strings, text) if text else 0
            for col in range(first, mask):
                struct.pack_into("<I", row, col * 4, off)
        records += row
        ids[v["id"]] = count
        count += 1
        added += 1
    return _join(count, fields, rec, records, strings), added, missing


def append_visuals(data: bytes, variants):
    """One SpellVisual row per variant: the base's row with the element's impact kit."""
    count, fields, rec, records, strings = _split(data, SPELLVISUAL_FIELDS, "SpellVisual.dbc")
    ids = _ids(records, rec, count)
    added = 0
    for v in variants:
        vis = v["visual"]
        if vis["id"] in ids:
            continue
        base_row = ids.get(vis["base"])
        row = bytearray(records[base_row * rec:(base_row + 1) * rec]) if base_row is not None \
            else bytearray(rec)
        struct.pack_into("<I", row, 0, vis["id"])
        struct.pack_into("<I", row, VISUAL_IMPACT_KIT * 4, vis["impact_kit"])
        records += row
        ids[vis["id"]] = count
        count += 1
        added += 1
    return _join(count, fields, rec, records, strings), added


def icon_file_stem(icon) -> str:
    """CW_Fire_Spell_Shadow_RitualOfSacrifice, from the base icon's own file name."""
    base = icon["base_path"].split("\\")[-1] if icon.get("base_path") else "Spell"
    return "CW_%s_%s" % (icon["element"].capitalize(), base)


def append_icons(data: bytes, variants, painted: set):
    """One SpellIcon row per painted (base icon, element). Variants whose icon
    was not painted keep the base icon id and need no row."""
    count, fields, rec, records, strings = _split(data, SPELLICON_FIELDS, "SpellIcon.dbc")
    ids = _ids(records, rec, count)
    added = 0
    for v in variants:
        icon = v["icon"]
        if icon["id"] in ids or icon["id"] not in painted:
            continue
        row = bytearray(rec)
        struct.pack_into("<I", row, 0, icon["id"])
        struct.pack_into("<I", row, 4, _add_string(strings, ICON_DIR + icon_file_stem(icon)))
        records += row
        ids[icon["id"]] = count
        count += 1
        added += 1
    return _join(count, fields, rec, records, strings), added


def append_skill_lines(data: bytes, variants):
    """One SkillLineAbility row per variant, open to every class like the rest
    of the patched table."""
    count, fields, rec, records, strings = _split(data, SLA_FIELDS, "SkillLineAbility.dbc")
    ids = _ids(records, rec, count)
    added = 0
    for v in variants:
        sla = v.get("sla")
        if not sla or sla[0] in ids:
            continue
        values = list(sla)
        values[4] = dbc.ALL_CLASSES_MASK
        records += struct.pack("<14I", *[x & 0xFFFFFFFF for x in values])
        ids[sla[0]] = count
        count += 1
        added += 1
    return _join(count, fields, rec, records, strings), added


def retarget_unpainted(variants, painted: set):
    """Variants whose icon could not be painted point back at their base icon."""
    for v in variants:
        if v["icon"]["id"] not in painted:
            v["fields"]["133"] = v["icon"]["base_icon"]


# ----------------------------------------------------------------- icons

def _glyph(draw, kind, box, colour, outline):
    """A small procedural mark for the corner of the icon, supersampled by the caller."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    lw = max(2, int(w * 0.09))
    if kind == "flame":
        pts = [(cx, y0), (x1 - w * 0.12, cy + h * 0.15), (cx + w * 0.1, y1),
               (x0 + w * 0.12, cy + h * 0.2), (cx - w * 0.15, cy - h * 0.05)]
        draw.polygon(pts, fill=colour, outline=outline)
    elif kind == "snowflake":
        r = w * 0.45
        for k in range(3):
            a = math.pi / 2 + k * math.pi / 3
            draw.line([(cx - r * math.cos(a), cy - r * math.sin(a)),
                       (cx + r * math.cos(a), cy + r * math.sin(a))], fill=colour, width=lw)
        draw.ellipse((cx - lw, cy - lw, cx + lw, cy + lw), fill=colour)
    elif kind == "boulder":
        pts = [(x0 + w * 0.1, cy + h * 0.1), (x0 + w * 0.3, y0 + h * 0.15), (cx + w * 0.15, y0 + h * 0.05),
               (x1 - w * 0.08, cy - h * 0.1), (x1 - w * 0.15, y1 - h * 0.1), (x0 + w * 0.25, y1 - h * 0.05)]
        draw.polygon(pts, fill=colour, outline=outline)
    elif kind == "drop":
        draw.polygon([(cx, y0), (x1 - w * 0.2, cy + h * 0.1), (x0 + w * 0.2, cy + h * 0.1)], fill=colour)
        draw.ellipse((x0 + w * 0.2, cy - h * 0.15, x1 - w * 0.2, y1), fill=colour, outline=outline)
    elif kind == "star":
        pts = []
        for k in range(8):
            a = math.pi / 2 + k * math.pi / 4
            rr = w * 0.48 if k % 2 == 0 else w * 0.18
            pts.append((cx + rr * math.cos(a), cy - rr * math.sin(a)))
        draw.polygon(pts, fill=colour, outline=outline)
    elif kind == "eye":
        draw.ellipse((x0, cy - h * 0.28, x1, cy + h * 0.28), fill=colour, outline=outline)
        draw.ellipse((cx - w * 0.16, cy - h * 0.16, cx + w * 0.16, cy + h * 0.16), fill=outline)
    elif kind == "sunburst":
        r = w * 0.22
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=colour, outline=outline)
        for k in range(8):
            a = k * math.pi / 4
            draw.line([(cx + r * 1.3 * math.cos(a), cy + r * 1.3 * math.sin(a)),
                       (cx + w * 0.5 * math.cos(a), cy + w * 0.5 * math.sin(a))], fill=colour, width=lw)


def render_icon(base_blp: bytes, icon) -> bytes | None:
    """Paint the element onto the base icon. Returns BLP2 bytes, or None without Pillow."""
    try:
        from PIL import Image, ImageDraw, ImageChops
    except ImportError:
        return None

    width, height, rgba = blp.decode_blp(base_blp)
    img = Image.frombytes("RGBA", (width, height), rgba)
    hue = tuple(icon["hue"])
    rim = tuple(icon["rim"])

    # 1. shift the colour toward the element: keep the base's shading (its
    #    luminance) but lend it the element's hue
    lum = img.convert("L")
    tint = Image.new("RGB", img.size, hue)
    coloured = ImageChops.multiply(tint, Image.merge("RGB", (lum, lum, lum)))
    coloured = Image.blend(img.convert("RGB"), coloured, 0.55)

    # 2. a rim in the element's colour, strongest at the edges
    s = 4
    big = (width * s, height * s)
    mask = Image.new("L", big, 0)
    d = ImageDraw.Draw(mask)
    steps = 14
    for i in range(steps):
        inset = int(min(big) * 0.02 * i)
        d.rectangle((inset, inset, big[0] - 1 - inset, big[1] - 1 - inset),
                    outline=int(255 * (1 - i / steps) ** 2), width=max(1, s))
    mask = mask.resize(img.size, Image.LANCZOS)
    rim_layer = Image.new("RGB", img.size, rim)
    coloured = Image.composite(rim_layer, coloured, mask)

    # 3. the glyph, bottom-right, drawn large and downscaled for clean edges
    glyph = Image.new("RGBA", big, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glyph)
    gw = int(big[0] * 0.34)
    box = (big[0] - gw - int(big[0] * 0.06), big[1] - gw - int(big[1] * 0.06),
           big[0] - int(big[0] * 0.06), big[1] - int(big[1] * 0.06))
    shadow = (0, 0, 0, 170)
    _glyph(gd, icon["glyph"], tuple(c + max(1, s) for c in box), shadow, shadow)
    _glyph(gd, icon["glyph"], box, rim + (255,), (20, 20, 20, 255))
    glyph = glyph.resize(img.size, Image.LANCZOS)

    out = coloured.convert("RGBA")
    out.alpha_composite(glyph)
    out.putalpha(img.getchannel("A"))
    return blp.encode_palettized(out)


# ----------------------------------------------------------------- the step

def apply(files, payload: dict, manifest: dict, report: list, want_icons: bool = True):
    """Add the elemental variants to the patch payload. `files` is a
    clientfs.ClientFiles; `payload` maps archive paths to bytes and may already
    hold a patched SkillLineAbility.dbc, which is extended rather than replaced."""
    variants = [dict(v, fields=dict(v["fields"])) for v in manifest["variants"]]
    if not variants:
        return payload

    # icons first, so variants whose icon fails can fall back before the
    # spell rows are written
    painted = set()
    icons_done = {}
    if want_icons and blp.have_pillow():
        for v in variants:
            icon = v["icon"]
            if icon["id"] in icons_done:
                continue
            try:
                raw, _source = files.find(icon["base_path"] + ".blp")
                out = render_icon(raw, icon)
            except (FileNotFoundError, ValueError, KeyError):
                out = None
            icons_done[icon["id"]] = out
            if out:
                painted.add(icon["id"])
                payload[ICON_DIR + icon_file_stem(icon) + ".blp"] = out
    retarget_unpainted(variants, painted)

    raw, source = files.find(SPELL)
    patched, added, missing = append_spells(raw, variants)
    payload[SPELL] = patched
    report.append("  Spell.dbc        %d elemental variant rows appended (from %s)"
                  % (added, os.path.basename(source)))
    if missing:
        report.append("  Spell.dbc        %d variant(s) skipped, base spell not in this client: %s"
                      % (len(missing), ", ".join(str(m) for m in sorted(set(missing))[:8])))

    raw, source = files.find(SPELLVISUAL)
    patched, added = append_visuals(raw, variants)
    payload[SPELLVISUAL] = patched
    report.append("  SpellVisual.dbc  %d rows, base swing with the element's impact" % added)

    if painted:
        raw, source = files.find(SPELLICON)
        patched, added = append_icons(raw, variants, painted)
        payload[SPELLICON] = patched
        report.append("  SpellIcon.dbc    %d painted icons registered" % added)
    elif want_icons:
        report.append("  elemental icons  skipped (Python 'Pillow' not installed); variants use their base icons")

    if SKILLLINEABILITY in payload:
        raw = payload[SKILLLINEABILITY]
        source = "patched table"
    else:
        raw, source = files.find(SKILLLINEABILITY)
    patched, added = append_skill_lines(raw, variants)
    payload[SKILLLINEABILITY] = patched
    report.append("  SkillLineAbility.dbc  %d variant rows, filed under their base's tab (from %s)"
                  % (added, os.path.basename(source) if source != "patched table" else source))
    return payload
