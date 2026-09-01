"""Validate every generated/hand-written item file before it reaches a DB.

Display ids are checked against the client's ItemDisplayInfo.dbc, which is what
actually decides whether an item renders -- not against ids other items happen
to use.
"""
import io, os, re, sys, struct

sys.path.insert(0, r"B:\code\azerothcore-wotlk\modules\mod-classless-wildcard\client-patch")
from lib import clientfs
from lib.dbc import parse_header

WORLD = r"B:\code\azerothcore-wotlk\modules\mod-classless-wildcard\data\sql\db-world"
FILES = ["cw_world_base.sql", "cw_items_pack.sql", "cw_items_pack2.sql",
         "cw_items_heirlooms.sql", "cw_items_tiered.sql"]


def strip_sql_comments(s):
    """Drop -- comments, but not inside string literals."""
    out, i, q = [], 0, False
    while i < len(s):
        c = s[i]
        if q:
            out.append(c)
            if c == "'":
                if i + 1 < len(s) and s[i + 1] == "'":
                    out.append("'"); i += 2; continue
                q = False
            i += 1
            continue
        if c == "'":
            q = True; out.append(c); i += 1; continue
        if c == "-" and i + 1 < len(s) and s[i + 1] == "-":
            j = s.find("\n", i)
            i = len(s) if j < 0 else j
            continue
        out.append(c); i += 1
    return "".join(out)


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
                out.append("".join(buf).strip()); buf = []
            else:
                buf.append(c)
        i += 1
    out.append("".join(buf).strip())
    return out


def tuples(body):
    out, depth, start, q, i = [], 0, None, False, 0
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


# --- authoritative display ids straight from the client DBC ---
data_dir = r"B:\World.of.Warcraft.3.3.5a\Data"
cf = clientfs.ClientFiles(data_dir, clientfs.detect_locales(data_dir)[0])
raw, src = cf.find(r"DBFilesClient\ItemDisplayInfo.dbc")
records, fields, rec_size, _s = parse_header(raw)
valid_disp = set()
for i in range(records):
    valid_disp.add(struct.unpack_from("<I", raw, 20 + i * rec_size)[0])
print("ItemDisplayInfo.dbc: %d display ids (from %s)\n" % (len(valid_disp), src.split("\\")[-1]))

bad, seen = 0, {}
for name in FILES:
    src_txt = strip_sql_comments(io.open(os.path.join(WORLD, name), encoding="utf-8").read())
    m = re.search(r"INSERT INTO `item_template`\s*\((.*?)\)\s*VALUES", src_txt, re.S)
    if not m:
        print("%-26s no item_template INSERT" % name)
        continue
    cols = [c.strip().strip("`") for c in m.group(1).replace("\n", " ").split(",")]
    body = src_txt[m.end():]
    body = body[:body.index(";")]
    rows = tuples(body)

    iE, iD = cols.index("entry"), cols.index("displayid")
    arity_bad = disp_bad = 0
    lo = hi = None
    for t in rows:
        v = split_top(t)
        if len(v) != len(cols):
            print("  !! %s: entry %s has %d values, expected %d" % (name, v[0], len(v), len(cols)))
            arity_bad += 1; bad += 1
            continue
        e, d = int(v[iE]), int(v[iD])
        if d and d not in valid_disp:
            print("  !! %s: entry %d display %d NOT in ItemDisplayInfo.dbc" % (name, e, d))
            disp_bad += 1; bad += 1
        if e in seen:
            print("  !! entry %d duplicated: %s and %s" % (e, seen[e], name))
            bad += 1
        seen[e] = name
        lo = e if lo is None else min(lo, e)
        hi = e if hi is None else max(hi, e)

    print("%-26s %3d rows  %2d cols  entries %d..%d  arity %s  displays %s"
          % (name, len(rows), len(cols), lo, hi,
             "OK" if not arity_bad else "BAD", "OK" if not disp_bad else "BAD"))

# --- every item must actually be on a shelf, and reachable from the menu ---
#
# The shop is split across vendor lists because SMSG_LIST_INVENTORY stops at 150
# items. An item that exists but sits on no list is invisible and unbuyable, and
# nothing else would catch it, so check the shelving against the packs.
shop = io.open(os.path.join(WORLD, "cw_world_vendor_lists.sql"), encoding="utf-8").read()
shelved = {}
for entry, item in re.findall(r"^\((99\d{4}), \d+, (99\d{4}), 0, 0, 0, \d+\)", shop, re.M):
    shelved.setdefault(int(item), []).append(int(entry))

SCROLL = 990101
sellable = set(e for e in seen if e != SCROLL and seen[e] != "cw_world_base.sql")
missing = sellable - set(shelved)
orphan = set(shelved) - sellable

print("\nvendor lists: %d lists holding %d placements of %d items"
      % (len(set(sum(shelved.values(), []))), sum(len(v) for v in shelved.values()),
         len(shelved)))
if missing:
    print("  !! %d items are on no vendor list at all: %s"
          % (len(missing), sorted(missing)[:8])); bad += 1
if orphan:
    print("  !! %d shelved items do not exist: %s"
          % (len(orphan), sorted(orphan)[:8])); bad += 1

# Heirlooms get one list; everything else gets a level bracket plus the
# category's "all levels" list, so exactly two placements.
odd = {e: v for e, v in shelved.items() if len(v) not in (1, 2)}
if odd:
    print("  !! %d items shelved an unexpected number of times: %s"
          % (len(odd), sorted(odd)[:8])); bad += 1

sizes = {}
for item, entries in shelved.items():
    for e in entries:
        sizes[e] = sizes.get(e, 0) + 1
over = {e: n for e, n in sizes.items() if n > 150}
if over:
    print("  !! lists over the 150-item packet cap: %s" % over); bad += 1
else:
    print("  largest list holds %d items, cap is 150" % max(sizes.values()))

print("\ntotal items across all packs: %d" % len(seen))
print("%s" % ("FAILED" if bad else "all item SQL validated"))
sys.exit(1 if bad else 0)
