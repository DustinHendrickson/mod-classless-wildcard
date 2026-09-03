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

Pillow is required by the installer; without it apply() refuses to paint and
the install stops. (Earlier versions fell back to the base icons, which is how
variants ended up looking exactly like the ability they came from.) Without it
the variants would still work and simply show their
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

def _shade(colour, factor):
    """Darken (factor < 1) or lighten toward white (factor > 1) a colour."""
    if factor <= 1:
        return tuple(int(c * factor) for c in colour)
    t = factor - 1
    return tuple(min(255, int(c + (255 - c) * t)) for c in colour)


# The badge sits in the bottom-left corner, pulled in from both edges: the
# action bar and the addon's lists round or overdraw the outer few pixels of
# an icon, so a badge flush with the corner loses its border there. A third
# of the icon wide, so the symbol still reads at 36 pixels.
BADGE_FRACTION = 0.32   # of the icon's width
BADGE_INSET = 0.06      # of the icon's width, from the left and bottom edges


def _symbol(draw, kind, box, colour, background):
    """A bold, filled element symbol. Thin strokes vanish at the size these are
    shown, so every mark here is a solid shape."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    thick = max(2, int(w * 0.16))
    if kind == "flame":
        draw.polygon([(cx, y0), (x1 - w * 0.08, cy + h * 0.10), (cx + w * 0.12, y1),
                      (x0 + w * 0.08, cy + h * 0.15), (cx - w * 0.22, cy - h * 0.10)], fill=colour)
        draw.ellipse((cx - w * 0.16, cy + h * 0.05, cx + w * 0.16, y1 - h * 0.05), fill=background)
    elif kind == "snowflake":
        r = w * 0.46
        for k in range(3):
            a = math.pi / 2 + k * math.pi / 3
            draw.line([(cx - r * math.cos(a), cy - r * math.sin(a)),
                       (cx + r * math.cos(a), cy + r * math.sin(a))], fill=colour, width=thick)
    elif kind == "boulder":
        draw.polygon([(x0 + w * 0.05, cy + h * 0.15), (x0 + w * 0.25, y0 + h * 0.15),
                      (cx + w * 0.15, y0 + h * 0.05), (x1 - w * 0.05, cy - h * 0.10),
                      (x1 - w * 0.15, y1 - h * 0.05), (x0 + w * 0.22, y1)], fill=colour)
    elif kind == "drop":
        draw.polygon([(cx, y0), (x1 - w * 0.18, cy + h * 0.05), (x0 + w * 0.18, cy + h * 0.05)], fill=colour)
        draw.ellipse((x0 + w * 0.18, cy - h * 0.22, x1 - w * 0.18, y1), fill=colour)
    elif kind == "star":
        pts = []
        for k in range(8):
            a = math.pi / 2 + k * math.pi / 4
            rr = w * 0.50 if k % 2 == 0 else w * 0.17
            pts.append((cx + rr * math.cos(a), cy - rr * math.sin(a)))
        draw.polygon(pts, fill=colour)
    elif kind == "crescent":
        r = w * 0.44
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=colour)
        draw.ellipse((cx - r + w * 0.30, cy - r - h * 0.08, cx + r + w * 0.30, cy + r - h * 0.08), fill=background)
    elif kind == "sun":
        r = w * 0.24
        for k in range(8):
            a = k * math.pi / 4
            draw.line([(cx + r * 1.2 * math.cos(a), cy + r * 1.2 * math.sin(a)),
                       (cx + w * 0.5 * math.cos(a), cy + w * 0.5 * math.sin(a))], fill=colour, width=thick)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=colour)


def render_icon(base_blp: bytes, icon) -> bytes | None:
    """Stamp an element badge on the base icon. Returns BLP2 bytes, or None without Pillow.

    The base icon is left exactly as drawn. A square plate of black tinted
    toward the element's colour sits in the bottom-left corner, a third of the
    icon wide and inset from the edges, bordered in the element's colour, with
    a bold filled symbol of the element inside it. Drawn at four times the
    size and scaled down, so the edges are clean at the 36 pixels the game
    shows icons at.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    width, height, rgba = blp.decode_blp(base_blp)
    img = Image.frombytes("RGBA", (width, height), rgba)
    hue = tuple(icon["hue"])
    # a dark element colour (Shadow, Earth) needs a lifted symbol to read on the plate
    v = max(hue) / 255.0
    symbol = _shade(hue, 1.0 + (1.0 - v) * 0.8) if v < 0.75 else hue
    plate = _shade(hue, 0.20)

    scale = 4
    size = max(8, int(round(width * BADGE_FRACTION)))
    big = size * scale
    badge = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(badge)
    draw.rectangle((0, 0, big - 1, big - 1), fill=plate + (255,), outline=hue + (255,), width=scale)
    inset = int(big * 0.17)
    _symbol(draw, icon["glyph"], (inset, inset, big - inset, big - inset), symbol + (255,), plate + (255,))
    badge = badge.resize((size, size), Image.LANCZOS)

    out = img.copy()
    inset_px = int(round(width * BADGE_INSET))
    out.alpha_composite(badge, (inset_px, height - size - inset_px))
    # The base icon already uses a full 256-colour palette, so the badge's
    # colours must be reserved in the output palette or they are mapped to the
    # nearest base colour and the badge comes out grey. Its own colours, most
    # common first, go in ahead of the base's.
    counts = {}
    for px in badge.getdata():
        if px[3] >= 128:
            counts[px[:3]] = counts.get(px[:3], 0) + 1
    reserve = [rgb for rgb, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:24]]
    return blp.encode_palettized(out, reserve=reserve)


# ----------------------------------------------------------------- the step

def apply(files, payload: dict, manifest: dict, report: list, want_icons: bool = True):
    """Add the elemental variants to the patch payload. `files` is a
    clientfs.ClientFiles; `payload` maps archive paths to bytes and may already
    hold a patched SkillLineAbility.dbc, which is extended rather than replaced."""
    variants = [dict(v, fields=dict(v["fields"])) for v in manifest["variants"]]
    if not variants:
        return payload
    report.append("  elemental variants  generation %s: %d variant(s); the worldserver logs the "
                  "generation it loaded, and the two must match"
                  % (manifest.get("generation", "unknown"), len(variants)))

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
        raise ElementalError("the elemental icons cannot be painted: the Python library "
                             "'Pillow' is missing (python -m pip install --user pillow)")

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
