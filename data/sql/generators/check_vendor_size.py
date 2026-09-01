"""How many items does the Hero Advancement vendor show at each level?

SMSG_LIST_INVENTORY caps at MAX_VENDOR_ITEMS = 150 in 3.3.5, and the core
applies that cap AFTER filtering by conditions -- anything past 150 is silently
dropped from the packet. So what matters is the worst-case count for a single
player, not how many items are attached to the vendor.
"""
import io, os, re, collections

WORLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "db-world")
CAP = 150
FILES = ["cw_world_base.sql", "cw_items_pack.sql", "cw_items_pack2.sql",
         "cw_items_heirlooms.sql", "cw_items_tiered.sql"]

# every item sold by the vendor
sold = set()
for name in FILES:
    txt = io.open(os.path.join(WORLD, name), encoding="utf-8").read()
    for m in re.finditer(r"\(990100,\s*\d+,\s*(99\d{4}),", txt):        # explicit rows
        sold.add(int(m.group(1)))
    for m in re.finditer(r"SELECT 990100,[^;]*?BETWEEN (99\d{4}) AND (99\d{4})", txt, re.S):
        lo, hi = int(m.group(1)), int(m.group(2))
        entries = set(int(x) for x in re.findall(r"^\((99\d{4}),", txt, re.M))
        sold |= {e for e in entries if lo <= e <= hi}

# level windows from the conditions rows (absent = always visible)
lo_of, hi_of = {}, {}
for name in FILES:
    txt = io.open(os.path.join(WORLD, name), encoding="utf-8").read()
    # literal condition rows
    for e, v, cmp_ in re.findall(r"\(23, 990100, (\d+), 0, 0, 27, 0, (\d+), (\d)", txt):
        e, v = int(e), int(v)
        if cmp_ == "3":
            lo_of[e] = v
        elif cmp_ == "4":
            hi_of[e] = v
    # ...and the SELECT ... FROM item_template WHERE entry BETWEEN a AND b form
    for v, cmp_, lo, hi in re.findall(
            r"SELECT 23, 990100, `entry`, 0, 0, 27, 0, (\d+), (\d)[^;]*?"
            r"BETWEEN (99\d{4}) AND (99\d{4})", txt, re.S):
        v, lo, hi = int(v), int(lo), int(hi)
        for e in range(lo, hi + 1):
            if e in sold:
                (lo_of if cmp_ == "3" else hi_of)[e] = v

print("items attached to the vendor: %d" % len(sold))
print("of those, level-gated        : %d" % len(set(lo_of) | set(hi_of)))
print("always visible               : %d\n" % len(sold - (set(lo_of) | set(hi_of))))

worst = (0, 0)
rows = []
for lvl in range(1, 81):
    n = 0
    for e in sold:
        if lvl < lo_of.get(e, 0):
            continue
        if lvl > hi_of.get(e, 255):
            continue
        n += 1
    rows.append((lvl, n))
    if n > worst[1]:
        worst = (lvl, n)

for lvl, n in rows:
    if lvl in (1, 10, 20, 30, 40, 50, 60, 70, 71, 80):
        print("  level %-2d  %3d items  (%d pages)  %s"
              % (lvl, n, -(-n // 10), "OVER CAP" if n > CAP else ""))

print("\nworst case: %d items at level %d  (cap %d, headroom %d)"
      % (worst[1], worst[0], CAP, CAP - worst[1]))
print("status: %s" % ("OK" if worst[1] <= CAP else "EXCEEDS CAP -- items would be dropped"))
