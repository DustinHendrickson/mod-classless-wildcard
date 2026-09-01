"""Reprice the hand-written item packs and the heirlooms.

Everything was priced far too high: the packs asked 15-30 gold for level-35
gear, and the heirlooms 70-120 gold. Heirlooms in particular are meant to be
bought EARLY and grow with the character, so a price no low-level Hero can
reach defeats the point of them entirely.

Prices now follow the same curve the generated tiered gear uses, and heirlooms
get a flat, deliberately cheap price so they can be picked up while levelling.

The INSERT column list is parsed from each file, so this keeps working if the
column order ever changes.

Run:  python reprice_items.py
"""
import io, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.join(HERE, os.pardir, "db-world")

# Prices come from the game's own data (see analyze_prices.py): the median real
# BuyPrice per slot class and level band, written to prices.json.
import json
PRICES = json.load(open(os.path.join(HERE, "prices.json"), encoding="utf-8"))


def band_of(level):
    return max(1, (level // 10) * 10)

# InventoryType -> price class
INV_PRICE = {
    17: "weapon2h",                                   # two-hand
    13: "weapon1h", 21: "weapon1h", 22: "weapon1h",   # one-hand / main / off
    15: "weapon1h", 26: "weapon1h", 25: "weapon1h",   # bow / gun+wand / thrown
    5: "big_armor", 20: "big_armor", 7: "big_armor",  # chest / robe / legs
    1: "small_armor", 3: "small_armor", 10: "small_armor",
    8: "small_armor", 16: "small_armor", 14: "small_armor",
    2: "jewel", 11: "jewel", 12: "jewel", 23: "jewel",
}

# Heirlooms are bought once and then scale to 80, so they sit deliberately off
# the curve: priced near a real level-30 item of the same slot plus a premium,
# they are a genuine investment a levelling Hero can save for, and obviously
# worth it. Pricing them at their level-80 equivalent (100g+) would put them out
# of reach of exactly the characters they exist for.
HEIRLOOM_PRICE = {
    17: 100000,                         # two-hand           10g
    13: 65000, 15: 65000, 26: 65000,    # one-hand / ranged  6g 50s
    5: 37500, 20: 37500,                # chest / robe       3g 75s
    3: 22500,                           # shoulder           2g 25s
    16: 22500,                          # cloak              2g 25s
    12: 24000,                          # trinket            2g 40s
}


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


def money(c):
    g, s, cc = c // 10000, (c % 10000) // 100, c % 100
    return (("%dg " % g) if g else "") + (("%ds " % s) if s else "") + (("%dc" % cc) if cc else "")


def reprice(path, heirloom=False):
    txt = io.open(path, encoding="utf-8").read()
    m = re.search(r"INSERT INTO `item_template`\s*\((.*?)\)\s*VALUES", txt, re.S)
    if not m:
        print("  %s: no item_template INSERT, skipped" % os.path.basename(path))
        return txt, 0
    cols = [c.strip().strip("`") for c in m.group(1).replace("\n", " ").split(",")]
    iBuy, iSell = cols.index("BuyPrice"), cols.index("SellPrice")
    iInv, iReq = cols.index("InventoryType"), cols.index("RequiredLevel")

    body_start = m.end()
    body_end = txt.index(";\n", body_start)
    body = txt[body_start:body_end]

    changed = 0
    out, depth, start, q, i = [], 0, None, False, 0
    pieces = []
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
                pieces.append((start, i))
        i += 1

    newbody, last = [], 0
    for a, b in pieces:
        tup = body[a + 1:b]
        vals = split_top(tup)
        if len(vals) != len(cols):
            continue
        inv = int(vals[iInv].strip())
        req = int(vals[iReq].strip())
        if heirloom:
            buy = HEIRLOOM_PRICE.get(inv, 12000)
        else:
            buy = int(PRICES[INV_PRICE.get(inv, "jewel")][str(band_of(req))])
        sell = buy // 5
        old = int(vals[iBuy].strip())
        vals[iBuy] = (" " if vals[iBuy].startswith(" ") else "") + str(buy)
        vals[iSell] = (" " if vals[iSell].startswith(" ") else "") + str(sell)
        newbody.append(body[last:a + 1] + ",".join(vals))
        last = b
        if old != buy:
            changed += 1
    newbody.append(body[last:])
    return txt[:body_start] + "".join(newbody) + txt[body_end:], changed


for name, is_heir in (("cw_items_pack.sql", False),
                      ("cw_items_pack2.sql", False),
                      ("cw_items_heirlooms.sql", True)):
    path = os.path.join(WORLD, name)
    new, n = reprice(path, is_heir)
    io.open(path, "w", encoding="utf-8", newline="\n").write(new)
    print("%-26s repriced %d rows" % (name, n))

print("\nexample prices now (medians from real 3.3.5 items):")
for lvl in (1, 35, 80):
    for cls in ("weapon1h", "big_armor"):
        print("  level %-2d %-11s %s" % (lvl, cls, money(int(PRICES[cls][str(band_of(lvl))]))))
print("  heirloom weapon   %s" % money(HEIRLOOM_PRICE[13]))
print("  heirloom chest    %s" % money(HEIRLOOM_PRICE[5]))
print("  heirloom cloak    %s" % money(HEIRLOOM_PRICE[16]))

