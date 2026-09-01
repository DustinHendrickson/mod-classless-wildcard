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

tier = io.open(os.path.join(WORLD, "cw_items_tiered.sql"), encoding="utf-8").read()
cond_entries = set(int(x) for x in re.findall(r"\(23, 990100, (\d+), 0, 0, 27,", tier))
item_entries = set(int(x) for x in re.findall(r"^\((99\d{4}), \d+, \d+, '", tier, re.M))
print("\nvendor conditions: %d rows covering %d of %d items"
      % (tier.count("(23, 990100,"), len(cond_entries), len(item_entries)))
if cond_entries != item_entries:
    print("  !! %d items have no condition" % len(item_entries - cond_entries)); bad += 1

print("\ntotal items across all packs: %d" % len(seen))
print("%s" % ("FAILED" if bad else "all item SQL validated"))
sys.exit(1 if bad else 0)
