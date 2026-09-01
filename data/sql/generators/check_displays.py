"""Does every item's artwork match what the item claims to be?

`displayid` drives both the inventory icon and the 3D model. Nothing in
item_template ties it to `class` / `subclass` / `InventoryType`, so an item can
happily call itself a Thrown weapon while wearing a two-handed axe's icon --
which is exactly what shipped.

This reads the core's item_template, records which (class, subclass,
InventoryType) combinations each display id is really used with, and then
checks every item in our packs against that. A display used by real Thrown
weapons is a valid look for our Thrown weapon; anything else is a mismatch.

Run:  python check_displays.py
"""
import io, os, re, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.join(HERE, os.pardir, "db-world")
CORE = r"B:\code\azerothcore-wotlk\data\sql\base\db_world\item_template.sql"

PACKS = ["cw_items_pack.sql", "cw_items_pack2.sql",
         "cw_items_heirlooms.sql", "cw_items_tiered.sql"]

# entry,class,subclass,SoundOverride,name,displayid,Quality,Flags,FlagsExtra,
# BuyCount,BuyPrice,SellPrice,InventoryType,...
CORE_ROW = re.compile(
    r"\((\d+),(\d+),(\d+),(-?\d+),'((?:[^'\\]|\\.)*)',(\d+),(\d+),(\d+),(\d+),"
    r"(\d+),(-?\d+),(\d+),(\d+),")

# Slots that share artwork: the game itself reuses one look across these.
SLOT_ALIAS = {5: 5, 20: 5,          # chest and robe are the same model
              21: 13, 22: 13, 13: 13,  # main-hand / off-hand / one-hand
              26: 26, 15: 15}


def norm(inv):
    return SLOT_ALIAS.get(inv, inv)


def load_core():
    used = collections.defaultdict(set)
    txt = io.open(CORE, encoding="utf-8", errors="replace").read()
    for m in CORE_ROW.finditer(txt):
        cls, sub, disp, inv = (int(m.group(2)), int(m.group(3)),
                               int(m.group(6)), int(m.group(13)))
        if disp:
            used[disp].add((cls, sub, norm(inv)))
    return used


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
                out.append(body[start + 1:i])
        i += 1
    return out


def read_pack(path):
    txt = io.open(path, encoding="utf-8").read()
    m = re.search(r"INSERT INTO `item_template`\s*\((.*?)\)\s*VALUES", txt, re.S)
    if not m:
        return []
    cols = [c.strip().strip("`") for c in m.group(1).replace("\n", " ").split(",")]
    body = txt[m.end():txt.index(";\n", m.end())]
    items = []
    for tup in tuples(body):
        vals = split_top(tup)
        if len(vals) != len(cols):
            continue
        d = dict(zip(cols, (v.strip() for v in vals)))
        items.append(dict(entry=int(d["entry"]), cls=int(d["class"]),
                          sub=int(d["subclass"]), disp=int(d["displayid"]),
                          inv=int(d["InventoryType"]),
                          name=d["name"].strip("'").replace("''", "'")))
    return items


used = load_core()
bad, unknown, total = [], [], 0
for pack in PACKS:
    for it in read_pack(os.path.join(WORLD, pack)):
        total += 1
        want = (it["cls"], it["sub"], norm(it["inv"]))
        have = used.get(it["disp"])
        if not have:
            unknown.append((pack, it))
        elif want not in have:
            bad.append((pack, it, sorted(have)))

print("checked %d items across %d packs\n" % (total, len(PACKS)))

if unknown:
    print("DISPLAY ID NOT USED BY ANY REAL ITEM (%d):" % len(unknown))
    for pack, it in unknown:
        print("  %-26s %6d  %-44s display %d"
              % (pack, it["entry"], it["name"], it["disp"]))
    print()

if bad:
    print("ARTWORK DOES NOT MATCH THE ITEM (%d):" % len(bad))
    for pack, it, have in bad:
        print("  %-26s %6d  %-44s" % (pack, it["entry"], it["name"]))
        print("      declares class %d sub %d slot %d, but display %d is real"
              " artwork for %s" % (it["cls"], it["sub"], it["inv"], it["disp"],
                                   ", ".join("%d/%d/%d" % h for h in have[:4])))
    print()

if not bad and not unknown:
    print("every item's artwork matches its class, subclass and slot")
sys.exit(1 if (bad or unknown) else 0)
