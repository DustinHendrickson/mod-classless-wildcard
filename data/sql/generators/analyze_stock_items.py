"""What do real 3.3.5 items look like? Writes stock_items.json.

Reads the core's item_template dump and records three things our generated
items copy instead of inventing:

  look    the most common (Material, sheath) for each (class, subclass,
          InventoryType). The server checks both against Item.dbc at startup
          and overwrites item_template with what the DBC says, so the SQL and
          the client patch's Item.dbc rows have to carry the same pair. The
          stock dump and the stock Item.dbc agree on these counts.
  chest   median chest armour per armour subclass and level band, uncommon to
          epic. Plate has no stock items below level 40, so its early bands
          follow mail by the plate/mail ratio measured from 40 up.
  ratio   median armour of each slot as a fraction of the chest at the same
          subclass and band.
  shield  median shield armour and block value per level band.

The first armour curve here was a straight line per level and came out at a
quarter of stock at 80, and shields carried no block value at all.

Run:  python analyze_stock_items.py     (writes stock_items.json)
"""
import collections
import io
import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = r"B:\code\azerothcore-wotlk\data\sql\base\db_world\item_template.sql"
OUT = os.path.join(HERE, "stock_items.json")

# item_template column positions, from the dump's CREATE TABLE
C_CLASS, C_SUB, C_QUALITY, C_INV, C_REQ = 1, 2, 6, 12, 16
C_ARMOR, C_MATERIAL, C_SHEATH, C_BLOCK = 55, 107, 108, 111
N_COLS = 138

ITEM_CLASS_ARMOR = 4
CLOTH, LEATHER, MAIL, PLATE, SHIELD = 1, 2, 3, 4, 6
CHEST_SLOTS = (5, 20)
BANDS = [1, 10, 20, 30, 40, 50, 60, 70, 80]


def band_of(req):
    return max(1, (req // 10) * 10)


def split_top(s):
    """Split a row on top-level commas; the dump escapes quotes with a backslash."""
    parts, cur, q, i = [], [], False, 0
    while i < len(s):
        c = s[i]
        if q:
            if c == "\\":
                cur.append(s[i:i + 2])
                i += 2
                continue
            if c == "'":
                q = False
        elif c == "'":
            q = True
        elif c == ",":
            parts.append("".join(cur).strip())
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    parts.append("".join(cur).strip())
    return parts


def rows():
    txt = io.open(CORE, encoding="utf-8", errors="replace").read()
    body = txt[txt.index("INSERT INTO"):]
    q = esc = False
    depth, start = 0, None
    for j, c in enumerate(body):
        if q:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == "'":
                q = False
            continue
        if c == "'":
            q = True
        elif c == "(":
            if depth == 0:
                start = j + 1
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                v = split_top(body[start:j])
                if len(v) == N_COLS:
                    yield [x.strip("'") for x in v]


def main():
    looks = collections.defaultdict(collections.Counter)
    armor = collections.defaultdict(list)       # (sub, inv, band) -> [armor]
    block = collections.defaultdict(list)       # band -> [block]
    total = 0
    for v in rows():
        n = lambda k: int(float(v[k]))
        total += 1
        looks["%d,%d,%d" % (n(C_CLASS), n(C_SUB), n(C_INV))][
            (n(C_MATERIAL), n(C_SHEATH))] += 1
        if n(C_CLASS) != ITEM_CLASS_ARMOR or n(C_QUALITY) not in (2, 3, 4):
            continue
        if not 1 <= n(C_REQ) <= 80 or n(C_ARMOR) <= 0:
            continue
        band = band_of(n(C_REQ))
        armor[(n(C_SUB), n(C_INV), band)].append(n(C_ARMOR))
        if n(C_SUB) == SHIELD and n(C_BLOCK) > 0:
            block[band].append(n(C_BLOCK))
    print("read %d stock items" % total)

    look = {k: list(c.most_common(1)[0][0]) for k, c in sorted(looks.items())}

    chest = {}
    for sub in (CLOTH, LEATHER, MAIL, PLATE):
        chest[sub] = {}
        for band in BANDS:
            got = [a for inv in CHEST_SLOTS for a in armor.get((sub, inv, band), [])]
            if got:
                chest[sub][band] = statistics.median(got)
    plate_over_mail = statistics.median(
        chest[PLATE][b] / chest[MAIL][b] for b in BANDS if b in chest[PLATE])
    for band in BANDS:
        chest[PLATE].setdefault(band, chest[MAIL][band] * plate_over_mail)
    for sub in chest:
        missing = [b for b in BANDS if b not in chest[sub]]
        if missing:
            raise SystemExit("no stock chest armour for subclass %d at %s" % (sub, missing))

    ratio = collections.defaultdict(dict)
    per_slot = collections.defaultdict(list)
    for (sub, inv, band), got in armor.items():
        if sub in chest and inv not in CHEST_SLOTS:
            per_slot[(sub, inv)] += [a / chest[sub][band] for a in got]
    for (sub, inv), got in per_slot.items():
        if len(got) >= 10:
            ratio[sub][inv] = round(statistics.median(got), 4)

    shield = {}
    for band in BANDS:
        a, b = armor.get((SHIELD, 14, band), []), block.get(band, [])
        if not a or not b:
            raise SystemExit("no stock shields at band %d" % band)
        shield[band] = dict(armor=int(statistics.median(a)),
                            block=int(statistics.median(b)))

    out = dict(
        look=look,
        chest={str(s): {str(b): int(round(a)) for b, a in sorted(c.items())}
               for s, c in chest.items()},
        ratio={str(s): {str(i): r for i, r in sorted(c.items())}
               for s, c in sorted(ratio.items())},
        shield={str(b): v for b, v in shield.items()})
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(
        json.dumps(out, indent=1, sort_keys=True))
    print("plate/mail ratio %.2f" % plate_over_mail)
    for sub, name in ((CLOTH, "cloth"), (LEATHER, "leather"), (MAIL, "mail"), (PLATE, "plate")):
        print("  %-8s chest %s" % (name, [out["chest"][str(sub)][str(b)] for b in BANDS]))
    print("  shield   %s" % [(shield[b]["armor"], shield[b]["block"]) for b in BANDS])
    print("wrote %s" % OUT)


def look_of(table, cls, sub, inv):
    """(Material, sheath) stock items of this kind carry, or (-1, 0) if none do."""
    return tuple(table["look"].get("%d,%d,%d" % (cls, sub, inv), (-1, 0)))


def load():
    return json.load(io.open(OUT, encoding="utf-8"))


if __name__ == "__main__":
    main()
