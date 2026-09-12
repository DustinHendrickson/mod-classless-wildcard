"""Write the client manifest for our items: client-patch/items_manifest.json.

The client draws a STOCK item's icon straight away because Item.dbc already
holds its class, subclass, display and slot -- GetItemIcon and GetItemInfo read
that without asking the server. A custom item has no Item.dbc row, so nothing
can draw it until the server answers an item query, and anything that renders a
bag from a saved list (Bagnon and friends) paints INV_Misc_QuestionMark instead.
Clearing the client's Cache makes that worse, not better: it throws away the one
copy the client had.

So the client patch appends a row per generated item. This writes what it needs.

Material and SheatheType are not in item_template. They are copied from a stock
item with the same (class, subclass, InventoryType) -- the same donor idea the
spell generator uses -- so sheathing and the sound a weapon makes stay right.

Run:  python gen_item_manifest.py
"""
import io
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(MOD, "client-patch"))
from lib import clientfs                                    # noqa: E402
from lib.dbc import parse_header                            # noqa: E402

WORLD = os.path.join(MOD, "data", "sql", "db-world")
OUT = os.path.join(MOD, "client-patch", "items_manifest.json")
FILES = ["cw_world_base.sql", "cw_items_pack.sql", "cw_items_pack2.sql",
         "cw_items_heirlooms.sql", "cw_items_tiered.sql"]
CLIENT = r"B:\World.of.Warcraft.3.3.5a\Data"
BS = chr(92)


def split_top(s):
    parts, cur, q, i = [], [], None, 0
    while i < len(s):
        c = s[i]
        if q:
            if c == "\\":
                cur.append(c)
                i += 2
                continue
            if c == q:
                q = None
            cur.append(c)
        elif c in "'\"":
            q = c
            cur.append(c)
        elif c == ",":
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
        i += 1
    parts.append("".join(cur).strip())
    return parts


def strip_sql_comments(s):
    out, i, q = [], 0, False
    while i < len(s):
        c = s[i]
        if q:
            out.append(c)
            if c == "'":
                q = False
            i += 1
        elif c == "'":
            q = True
            out.append(c)
            i += 1
        elif s.startswith("--", i):
            j = s.find("\n", i)
            i = len(s) if j < 0 else j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def read_items():
    items = []
    for name in FILES:
        text = strip_sql_comments(
            io.open(os.path.join(WORLD, name), encoding="utf-8").read())
        m = re.search(r"INSERT INTO `item_template`\s*\((.*?)\)\s*VALUES",
                      text, re.S)
        if not m:
            continue
        cols = [c.strip().strip("`") for c in m.group(1).replace("\n", " ").split(",")]
        body = text[m.end():]
        body = body[:body.index(";")]
        need = ("entry", "class", "subclass", "displayid", "InventoryType")
        if any(k not in cols for k in need):
            print("  %-26s missing a needed column, skipped" % name)
            continue
        idx = {k: cols.index(k) for k in need}
        for chunk in re.findall(r"\(((?:[^()']|'(?:[^']|'')*')*)\)", body):
            v = split_top(chunk)
            if len(v) != len(cols):
                continue
            items.append(dict(
                entry=int(v[idx["entry"]]),
                cls=int(v[idx["class"]]),
                sub=int(v[idx["subclass"]]),
                display=int(v[idx["displayid"]]),
                inv=int(v[idx["InventoryType"]]),
                source=name))
    return items


def main():
    items = read_items()
    print("generated items read: %d" % len(items))

    with clientfs.ClientFiles(CLIENT, clientfs.detect_locales(CLIENT)[0]) as files:
        raw, src = files.find("DBFilesClient" + BS + "Item.dbc")
    rows, fields, rec, _slen = parse_header(raw)
    if fields != 8 or rec != 32:
        raise SystemExit("Item.dbc has %d fields of %d bytes, expected 8 of 32"
                         % (fields, rec))
    print("Item.dbc: %d rows (from %s)" % (rows, os.path.basename(src)))

    # (class, subclass, inventorytype) -> (material, sheathe) from real items
    donor, taken = {}, {}
    for i in range(rows):
        v = struct.unpack_from("<8i", raw, 20 + i * rec)
        taken[v[0]] = True
        donor.setdefault((v[1], v[2], v[6]), (v[4], v[7]))
        donor.setdefault((v[1], v[2], None), (v[4], v[7]))

    out, guessed, clash = [], 0, []
    for it in items:
        if it["entry"] in taken:
            clash.append(it["entry"])
            continue
        mat_sheathe = (donor.get((it["cls"], it["sub"], it["inv"]))
                       or donor.get((it["cls"], it["sub"], None)))
        if mat_sheathe is None:
            mat_sheathe = (-1, 0)
            guessed += 1
        out.append(dict(entry=it["entry"], cls=it["cls"], sub=it["sub"],
                        sound_sub=-1, material=mat_sheathe[0],
                        display=it["display"], inv=it["inv"],
                        sheathe=mat_sheathe[1]))
    if clash:
        raise SystemExit("these entries already exist in Item.dbc: %s" % clash[:6])
    print("   rows to append: %d (%d with no donor, defaulted)" % (len(out), guessed))

    io.open(OUT, "w", encoding="utf-8", newline="\n").write(
        json.dumps(dict(version=1, count=len(out), items=out),
                   indent=1, sort_keys=True))
    print("wrote %s" % OUT)


if __name__ == "__main__":
    main()
