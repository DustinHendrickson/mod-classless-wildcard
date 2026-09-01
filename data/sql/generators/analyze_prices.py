"""What did real 3.3.5 items actually cost?

Reads the core's item_template and reports median BuyPrice by required level,
quality and slot class, so our vendor prices can be based on the game's own
spread instead of invented numbers.
"""
import io, os, re, statistics, collections

CORE = r"B:\code\azerothcore-wotlk\data\sql\base\db_world\item_template.sql"

# entry,class,subclass,SoundOverride,name,displayid,Quality,Flags,FlagsExtra,
# BuyCount,BuyPrice,SellPrice,InventoryType,AllowableClass,AllowableRace,
# ItemLevel,RequiredLevel
ROW = re.compile(
    r"\((\d+),(\d+),(\d+),(-?\d+),'((?:[^'\\]|\\.)*)',(\d+),(\d+),(\d+),(\d+),"
    r"(\d+),(-?\d+),(\d+),(\d+),(-?\d+),(-?\d+),(\d+),(\d+),")

TWO_HAND = {17}
ONE_HAND = {13, 21, 22, 15, 26, 25}
BIG_ARMOR = {5, 20, 7}
SMALL_ARMOR = {1, 3, 10, 8, 16, 14, 6, 9}
JEWEL = {2, 11, 12, 23}


def slot_class(cls, inv):
    if cls == 2:
        return "weapon2h" if inv in TWO_HAND else "weapon1h"
    if inv in BIG_ARMOR:
        return "big_armor"
    if inv in SMALL_ARMOR:
        return "small_armor"
    if inv in JEWEL:
        return "jewel"
    return None


buckets = collections.defaultdict(list)
txt = io.open(CORE, encoding="utf-8", errors="replace").read()
total = 0
for m in ROW.finditer(txt):
    cls, inv = int(m.group(2)), int(m.group(13))
    quality, buy = int(m.group(7)), int(m.group(11))
    req, ilvl = int(m.group(17)), int(m.group(16))
    if cls not in (2, 4) or buy <= 0:
        continue
    sc = slot_class(cls, inv)
    if not sc:
        continue
    # quality 2 uncommon / 3 rare / 4 epic -- the tiers we sell
    if quality not in (2, 3, 4):
        continue
    lvl = req if req > 0 else ilvl
    if not (1 <= lvl <= 80):
        continue
    band = max(1, (lvl // 10) * 10)
    buckets[(sc, band)].append(buy)
    total += 1

print("sampled %d real equippable items\n" % total)


def money(c):
    g, s, cc = c // 10000, (c % 10000) // 100, c % 100
    out = ""
    if g:
        out += "%dg " % g
    if s:
        out += "%ds " % s
    if cc or not out:
        out += "%dc" % cc
    return out.strip()


BANDS = [1, 10, 20, 30, 40, 50, 60, 70, 80]
print("%-12s %s" % ("slot class", "  ".join("%9d" % b for b in BANDS)))
print("-" * 100)
fits = {}
for sc in ("weapon2h", "weapon1h", "big_armor", "small_armor", "jewel"):
    cells, pts = [], []
    for b in BANDS:
        vals = buckets.get((sc, b), [])
        if vals:
            med = int(statistics.median(vals))
            cells.append("%9s" % money(med))
            pts.append((b, med))
        else:
            cells.append("%9s" % "-")
    print("%-12s %s" % (sc, "  ".join(cells)))
    fits[sc] = pts

# Publish the measured medians for the generators to price against. A fitted
# curve was tried but tracked the real data poorly at both ends (it undershoots
# level 80 by a third), so the medians themselves are the better basis.
import json
out = {sc: {str(b): int(statistics.median(buckets[(sc, b)]))
            for b in BANDS if buckets.get((sc, b))}
       for sc in fits}
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prices.json")
io.open(path, "w", encoding="utf-8").write(json.dumps(out, indent=1, sort_keys=True))
print("\nwrote prices.json -- median real BuyPrice per slot class and level band")
