"""Collect several real display ids per (class, subclass, inventorytype),
so generated gear can look different at each level band."""
import io, re, json, collections

SRC = r"B:\code\azerothcore-wotlk\data\sql\base\db_world\item_template.sql"
OUT = r"C:\Users\dusti\AppData\Local\Temp\claude\B--code-azerothcore-wotlk-modules-mod-classless-wildcard\c27b482a-63ff-4b1b-b9ea-c88803d33e92\scratchpad\displays.json"

#            1     2     3      4                5                     6     7     8     9     10    11     12    13
ROW = re.compile(r"\((\d+),(\d+),(\d+),(-?\d+),'((?:[^'\\]|\\.)*)',(\d+),(\d+),(\d+),(\d+),(\d+),(-?\d+),(\d+),(\d+),")

WANT = {
    (2, 3, 26): "gun", (2, 2, 15): "bow", (2, 10, 17): "staff",
    (2, 6, 17): "polearm", (2, 1, 17): "axe2h", (2, 5, 17): "mace2h",
    (2, 8, 17): "sword2h", (2, 15, 13): "dagger", (2, 7, 13): "sword1h",
    (2, 4, 13): "mace1h", (2, 0, 13): "axe1h", (2, 13, 13): "fist",
    (2, 19, 26): "wand", (2, 16, 25): "thrown",
    (4, 6, 14): "shield", (4, 0, 23): "offhand",
    (4, 1, 5): "cloth_chest", (4, 1, 20): "cloth_robe", (4, 1, 3): "cloth_shoulder",
    (4, 1, 7): "cloth_legs", (4, 1, 8): "cloth_feet", (4, 1, 16): "cloak",
    (4, 2, 5): "leather_chest", (4, 2, 3): "leather_shoulder", (4, 2, 7): "leather_legs",
    (4, 3, 5): "mail_chest", (4, 3, 3): "mail_shoulder", (4, 3, 7): "mail_legs",
    (4, 4, 5): "plate_chest", (4, 4, 3): "plate_shoulder", (4, 4, 7): "plate_legs",
    (4, 4, 1): "plate_head", (4, 4, 10): "plate_hands",
    (4, 0, 2): "neck", (4, 0, 11): "ring", (4, 0, 12): "trinket",
}

pool = collections.defaultdict(list)
txt = io.open(SRC, encoding="utf-8", errors="replace").read()
for m in ROW.finditer(txt):
    cls, sub = int(m.group(2)), int(m.group(3))
    disp, qual, inv = int(m.group(6)), int(m.group(7)), int(m.group(13))
    key = (cls, sub, inv)
    if key in WANT and disp > 0 and qual in (2, 3, 4):
        label = WANT[key]
        if disp not in pool[label]:
            pool[label].append(disp)

out = {}
missing = []
for key, label in WANT.items():
    ids = pool.get(label, [])
    if len(ids) < 3:
        missing.append("%s (%d)" % (label, len(ids)))
    out[label] = ids[:12]          # a dozen looks is plenty for 9 bands

io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, indent=1))
print("collected display ids for %d slot types -> displays.json" % len(out))
for label in sorted(out):
    print("  %-18s %2d looks  e.g. %s" % (label, len(out[label]), out[label][:4]))
if missing:
    print("\nTOO FEW LOOKS: %s" % ", ".join(missing))
