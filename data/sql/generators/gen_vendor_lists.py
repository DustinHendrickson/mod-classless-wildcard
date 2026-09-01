"""Lay the Hero Advancement shop out as browsable lists.

SMSG_LIST_INVENTORY carries at most MAX_VENDOR_ITEMS = 150 entries and the core
drops the overflow without a word, so a single flat list could never show all
250 items. Worse, one list of 250 is miserable to shop in even if it fit.

WorldSession::SendListInventory(guid, vendorEntry) reads its items from
`sObjectMgr->GetNpcVendorItemList(vendorEntry)` rather than from the creature,
so one NPC can front any number of separate lists, each with its own 150
budget. Player::BuyItemFromVendorSlot resolves purchases through
WorldSession::GetCurrentVendor(), so buying works from a sublist unchanged.

The shop is split by category and then by level bracket, so any one list is
small enough to read. Nothing is hidden: every list also has an "all levels"
variant, and every one of them stays well under the cap.

One thing to know if you edit this: conditions are looked up with the
CREATURE's entry (`vendor->GetEntry()` in SendListInventory), not the vendor
list's, so a `conditions` row would apply to every sublist at once. The old
level-window conditions are therefore dropped -- the level brackets do that job
now, and do it visibly.

Writes  ../db-world/cw_world_vendor_lists.sql   (applied after cw_world_base)
and     ../../../src/ClasslessVendorLists.h     (the same layout for the gossip
                                                 menu, so the two cannot drift)

Run:  python gen_vendor_lists.py
"""
import io, os, re, textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.join(HERE, os.pardir, "db-world")
SRC = os.path.join(HERE, os.pardir, os.pardir, os.pardir, "src")
OUT_SQL = os.path.join(WORLD, "cw_world_vendor_lists.sql")
OUT_HDR = os.path.join(SRC, "ClasslessVendorLists.h")

NPC = 990100
SCROLL = 990101
VERIFIED = 12340
PACKS = ["cw_items_pack.sql", "cw_items_pack2.sql",
         "cw_items_heirlooms.sql", "cw_items_tiered.sql"]

# Every item entry the module owns, so the file can clear whatever an older
# version of the module left on the vendor.
OWNED_LO, OWNED_HI = 990200, 990999

HEIRLOOM_QUALITY = 7

# InventoryType -> category. Class 2 is always a weapon whatever the slot.
JEWEL_SLOTS = {2, 11, 12, 23}          # neck, finger, trinket, held off-hand

TIERS = [(1, 20), (21, 40), (41, 60), (61, 80)]

# vendorEntry = LIST_BASE + category*10 + tier, tier 4 meaning "all levels".
LIST_BASE = 990110


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
        items.append(dict(
            entry=int(d["entry"]), cls=int(d["class"]), inv=int(d["InventoryType"]),
            quality=int(d["Quality"]), req=int(d["RequiredLevel"]),
            name=d["name"].strip("'").replace("''", "'")))
    return items


items = []
for p in PACKS:
    items += read_pack(os.path.join(WORLD, p))
items = [i for i in items if i["entry"] != SCROLL]


def category(it):
    if it["quality"] == HEIRLOOM_QUALITY:
        return 3
    if it["cls"] == 2:
        return 0
    return 2 if it["inv"] in JEWEL_SLOTS else 1


def tier_of(level):
    for n, (lo, hi) in enumerate(TIERS):
        if lo <= level <= hi:
            return n
    return len(TIERS) - 1


CATS = [
    (0, "Weapons",            "every blade, bow, staff and wand"),
    (1, "Armor",              "chest, legs, shoulders, cloaks and shields"),
    (2, "Jewelry & off-hand", "necks, rings, trinkets and held items"),
    (3, "Heirlooms",          "bought once, they scale with you to 80"),
]

# category -> tier -> items.  Heirlooms carry RequiredLevel 1 because they
# scale, so bracketing them by level would be meaningless: they get one list.
buckets = {}
for it in items:
    c = category(it)
    t = None if c == 3 else tier_of(it["req"])
    buckets.setdefault((c, t), []).append(it)


def entry_for(cat, tier):
    return LIST_BASE + cat * 10 + (4 if tier is None else tier)


lists = []      # (vendorEntry, cat, tier, label, items)
for cat, cname, _desc in CATS:
    if cat == 3:
        got = sorted(buckets.get((cat, None), []), key=lambda i: (i["inv"], i["entry"]))
        lists.append((entry_for(cat, None), cat, None, cname, got))
        continue
    every = []
    for t, (lo, hi) in enumerate(TIERS):
        got = sorted(buckets.get((cat, t), []), key=lambda i: (i["inv"], i["req"], i["entry"]))
        every += got
        lists.append((entry_for(cat, t), cat, t, "Levels %d-%d" % (lo, hi), got))
    every = sorted(every, key=lambda i: (i["req"], i["inv"], i["entry"]))
    lists.append((entry_for(cat, None), cat, None, "All levels", every))

MAX_VENDOR_ITEMS = 150
over = [l for l in lists if len(l[4]) > MAX_VENDOR_ITEMS]
if over:
    raise SystemExit("list %d holds %d items, over the %d cap"
                     % (over[0][0], len(over[0][4]), MAX_VENDOR_ITEMS))

# ---------------------------------------------------------------- SQL --------
L = []
L.append(textwrap.dedent("""\
    -- mod-classless-wildcard: the Hero Advancement shop, split into lists
    -- (GENERATED)
    --
    -- Do not hand-edit: regenerate with data/sql/generators/gen_vendor_lists.py.
    --
    -- SMSG_LIST_INVENTORY carries at most 150 items and the core silently drops
    -- the rest, so the 250 items the module ships cannot go in one list -- and
    -- one list of 250 would be no fun to shop in anyway.
    --
    -- SendListInventory(guid, vendorEntry) takes its items from
    -- GetNpcVendorItemList(vendorEntry) instead of from the creature, so one NPC
    -- can front any number of lists, each with its own 150 budget. The gossip
    -- menu in ClasslessNpc.cpp opens them; src/ClasslessVendorLists.h is
    -- generated from this same layout so the two cannot drift apart.
    --
    -- Note that `conditions` for a vendor are looked up with the CREATURE's
    -- entry, not the list's, so a condition row would hit every list at once.
    -- The level-window conditions the packs used to install are dropped here:
    -- the level brackets replace them, and unlike a hidden filter they let a
    -- player see the whole catalogue.
    --
    -- This file is named to sort after cw_world_base.sql, which creates 990100.
    """))

L.append("-- clear whatever an older version of the module put on the vendor")
L.append("DELETE FROM `npc_vendor` WHERE `entry` = %d AND `item` BETWEEN %d AND %d;"
         % (NPC, OWNED_LO, OWNED_HI))
L.append("DELETE FROM `npc_vendor` WHERE `entry` BETWEEN %d AND %d;"
         % (LIST_BASE, LIST_BASE + 99))
L.append("DELETE FROM `conditions` WHERE `SourceTypeOrReferenceId` = 23")
L.append("  AND `SourceGroup` = %d AND `SourceEntry` BETWEEN %d AND %d;"
         % (NPC, OWNED_LO, OWNED_HI))
L.append("")

L.append(textwrap.dedent("""\
    -- Each list needs a creature_template row of its own. AzerothCore has the
    -- check commented out in ObjectMgr::IsVendorItemValid, so bare ids would
    -- work today, but a fork that enables it would drop every row here without
    -- explanation. Cloning 990100 keeps the data valid either way; none of
    -- these are ever spawned.
    """))
L.append("DELETE FROM `creature_template` WHERE `entry` BETWEEN %d AND %d;"
         % (LIST_BASE, LIST_BASE + 99))
for entry, cat, tier, label, got in lists:
    cname = CATS[cat][1]
    sub = cname if tier is None else "%s: %s" % (cname, label)
    L.append("CREATE TEMPORARY TABLE `cw_vlist` AS SELECT * FROM `creature_template` WHERE `entry` = %d;" % NPC)
    L.append("UPDATE `cw_vlist` SET `entry` = %d, `subname` = '%s', `ScriptName` = '';"
             % (entry, sub.replace("'", "''")))
    L.append("INSERT INTO `creature_template` SELECT * FROM `cw_vlist`;")
    L.append("DROP TEMPORARY TABLE `cw_vlist`;")
L.append("")

L.append(textwrap.dedent("""\
    -- A creature_template row with no model makes the core log an error for it
    -- on every startup, so give the clones 990100's model as well. Current
    -- AzerothCore keeps models in `creature_template_model`; older cores and
    -- repacks keep `modelid1` on the template itself, which the clone above
    -- already copied. Only the branch matching this database runs.
    DROP PROCEDURE IF EXISTS cw_vendor_list_models;
    DELIMITER //
    CREATE PROCEDURE cw_vendor_list_models()
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.TABLES
                   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'creature_template_model') THEN
            DELETE FROM `creature_template_model` WHERE `CreatureID` BETWEEN %d AND %d;
            INSERT INTO `creature_template_model`
              (`CreatureID`, `Idx`, `CreatureDisplayID`, `DisplayScale`, `Probability`, `VerifiedBuild`)
            SELECT ct.`entry`, m.`Idx`, m.`CreatureDisplayID`, m.`DisplayScale`, m.`Probability`, m.`VerifiedBuild`
            FROM `creature_template` ct
            JOIN `creature_template_model` m ON m.`CreatureID` = %d
            WHERE ct.`entry` BETWEEN %d AND %d;
        END IF;
    END //
    DELIMITER ;
    CALL cw_vendor_list_models();
    DROP PROCEDURE IF EXISTS cw_vendor_list_models;
    """ % (LIST_BASE, LIST_BASE + 99, NPC, LIST_BASE, LIST_BASE + 99)))

L.append("-- the lists themselves")
L.append("INSERT INTO `npc_vendor` (`entry`, `slot`, `item`, `maxcount`, `incrtime`, `ExtendedCost`, `VerifiedBuild`)")
L.append("VALUES")
rows = []
for entry, cat, tier, label, got in lists:
    for n, it in enumerate(got):
        rows.append("(%d, %d, %d, 0, 0, 0, %d)" % (entry, n + 1, it["entry"], VERIFIED))
L.append(",\n".join(rows) + ";")
L.append("")

L.append("-- the NPC's own list stays the supplies counter, so right-clicking")
L.append("-- the vendor without going through the gossip menu still works")
L.append("DELETE FROM `npc_vendor` WHERE `entry` = %d AND `item` = %d;" % (NPC, SCROLL))
L.append("INSERT INTO `npc_vendor` (`entry`, `slot`, `item`, `maxcount`, `incrtime`, `ExtendedCost`, `VerifiedBuild`)")
L.append("VALUES (%d, 1, %d, 0, 0, 0, %d);" % (NPC, SCROLL, VERIFIED))
L.append("")

io.open(OUT_SQL, "w", encoding="utf-8", newline="\n").write("\n".join(L))

# ------------------------------------------------------------- header --------
H = []
H.append(textwrap.dedent("""\
    /*
     * mod-classless-wildcard -- vendor list layout (GENERATED)
     *
     * Do not hand-edit: regenerate with
     * data/sql/generators/gen_vendor_lists.py, which writes this header and
     * data/sql/db-world/cw_world_vendor_lists.sql from one description of the
     * shop, so the gossip menu and the npc_vendor rows cannot disagree.
     */

    #ifndef MOD_CLASSLESS_VENDOR_LISTS_H
    #define MOD_CLASSLESS_VENDOR_LISTS_H

    #include <cstdint>

    namespace ClasslessWildcard
    {
        struct VendorList
        {
            uint32_t    entry;    // npc_vendor.entry
            uint8_t     category; // index into VENDOR_CATEGORIES
            char const* label;
            uint32_t    count;    // items in the list, for the menu text
            bool        whole;    // the category's everything-at-once list
        };

        struct VendorCategory
        {
            char const* name;
            char const* blurb;
        };
    """))

H.append("    constexpr VendorCategory VENDOR_CATEGORIES[] =")
H.append("    {")
for cat, cname, desc in CATS:
    H.append('        { "%s", "%s" },' % (cname, desc))
H.append("    };")
H.append("")
H.append("    constexpr VendorList VENDOR_LISTS[] =")
H.append("    {")
for entry, cat, tier, label, got in lists:
    H.append('        { %d, %d, "%s", %d, %s },'
             % (entry, cat, label, len(got), "true" if tier is None else "false"))
H.append("    };")
H.append("")
H.append("    // The supplies counter is the creature's own list, which")
H.append("    // SendListInventory reaches with a vendor entry of 0.")
H.append("    constexpr uint32_t VENDOR_LIST_SUPPLIES = 0;")
H.append("}")
H.append("")
H.append("#endif // MOD_CLASSLESS_VENDOR_LISTS_H")
H.append("")

io.open(OUT_HDR, "w", encoding="utf-8", newline="\n").write("\n".join(H))

print("wrote %s" % os.path.normpath(OUT_SQL))
print("wrote %s" % os.path.normpath(OUT_HDR))
print()
print("  %d items laid out across %d lists (cap %d each)"
      % (len(items), len(lists), MAX_VENDOR_ITEMS))
for entry, cat, tier, label, got in lists:
    print("    %-6d %-20s %-14s %3d items  (%d pages)"
          % (entry, CATS[cat][1], label, len(got), (len(got) + 9) // 10))
print("    %-6s %-20s %-14s %3d items" % ("(npc)", "Supplies", "Reroll Scroll", 1))
