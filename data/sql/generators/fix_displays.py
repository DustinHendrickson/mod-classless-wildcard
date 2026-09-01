"""Give the hand-written item packs artwork that matches what they are.

The original packs picked display ids by eye. Ten of the first twelve items
were wearing art belonging to a different item type: a Thrown javelin with a
display no real item uses at all, a gun with a leather helmet's model, a shield
with a fishing pole's, a robe with a rifle's.

This rewrites `displayid` in place using displaypick, which only ever offers
art that real items of the same class, subclass and slot actually wear -- so
the icon, the model and the texture all agree with the tooltip.

The generated tiered gear does not need this: gen_tiered_gear.py picks from the
same pool when it builds.

Run:  python fix_displays.py
"""
import io, os, re

import displaypick

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.join(HERE, os.pardir, "db-world")
# Art is chosen near the item's own level so a low-level piece does not turn up
# wearing a raid model. Heirlooms are the exception: they carry ItemLevel 1
# because they scale, but they are endgame-priced rewards worn all the way to
# 80, so they get art from that end of the game instead of vanilla starter art.
PACKS = [("cw_items_pack.sql", None),
         ("cw_items_pack2.sql", None),
         ("cw_items_heirlooms.sql", 70)]


def split_top(s):
    out, buf, q, i = [], [], False, 0
    while i < len(s):
        c = s[i]
        if q:
            if c == "'":
                if i + 1 < len(s) and s[i + 1] == "'":
                    buf.append("''"); i += 2; continue
                q = False
            buf.append(c)
        else:
            if c == "'":
                q = True; buf.append(c)
            elif c == ",":
                out.append("".join(buf)); buf = []
            else:
                buf.append(c)
        i += 1
    out.append("".join(buf))
    return out


def tuples(body):
    depth, start, q, i, out = 0, None, False, 0, []
    while i < len(body):
        c = body[i]
        if q:
            if c == "'":
                if i + 1 < len(body) and body[i + 1] == "'":
                    i += 2; continue
                q = False
        elif c == "'":
            q = True
        elif c == "(":
            if depth == 0:
                start = i
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                out.append((start, i))
        i += 1
    return out


def source_of(cls, sub, inv, disp):
    for d, name, ilvl, qual in displaypick.candidates(cls, sub, inv):
        if d == disp:
            return name
    return "?"


def fix(path, art_level=None):
    txt = io.open(path, encoding="utf-8").read()
    m = re.search(r"INSERT INTO `item_template`\s*\((.*?)\)\s*VALUES", txt, re.S)
    if not m:
        return txt, []
    cols = [c.strip().strip("`") for c in m.group(1).replace("\n", " ").split(",")]
    iDisp = cols.index("displayid")
    iCls, iSub = cols.index("class"), cols.index("subclass")
    iInv, iName = cols.index("InventoryType"), cols.index("name")
    iLvl = cols.index("ItemLevel")

    start = m.end()
    end = txt.index(";\n", start)
    body = txt[start:end]

    used, changes, pieces = set(), [], []
    out, last = [], 0
    for a, b in tuples(body):
        vals = split_top(body[a + 1:b])
        if len(vals) != len(cols):
            continue
        cls, sub = int(vals[iCls].strip()), int(vals[iSub].strip())
        inv, ilvl = int(vals[iInv].strip()), int(vals[iLvl].strip())
        name = vals[iName].strip().strip("'").replace("''", "'")
        old = int(vals[iDisp].strip())

        target = art_level if art_level is not None else ilvl
        got = displaypick.pick(cls, sub, inv, name, ilvl=target, exclude=used,
                               by_level=art_level is not None)
        if not got:
            changes.append((name, old, None, None))
            continue
        new = got[0]
        used.add(new)
        if new != old:
            changes.append((name, old, new, source_of(cls, sub, inv, new)))
        pad = " " if vals[iDisp].startswith(" ") else ""
        vals[iDisp] = pad + str(new)
        out.append(body[last:a + 1] + ",".join(vals))
        last = b
    out.append(body[last:])
    return txt[:start] + "".join(out) + txt[end:], changes


for pack, art_level in PACKS:
    path = os.path.join(WORLD, pack)
    new, changes = fix(path, art_level)
    io.open(path, "w", encoding="utf-8", newline="\n").write(new)
    moved = [c for c in changes if c[2]]
    print("%s -- %d items re-arted" % (pack, len(moved)))
    for name, old, disp, src in moved:
        print("    %-40s now wears %-32s (%d)" % (name, src, disp))
    for name, old, disp, src in changes:
        if disp is None:
            print("    !! %-39s no real item has this class/subclass/slot" % name)
    print()
