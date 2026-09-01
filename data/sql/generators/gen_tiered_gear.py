"""Generate cw_items_tiered.sql -- classless gear across the whole level range.

The first two item packs all sat at item level 40 / required 35, so there was
nothing to buy while levelling and nothing at the cap. This lays the same
"stat combination the class system would never allow" idea across nine level
bands, from a fresh Hero at level 1 to level 80.

Two things keep it usable rather than a wall of 180 vendor entries:

  * prices scale with level and start in silver, so band-1 gear is affordable
    to a character that just left the starting zone;
  * every item is gated by a `conditions` row on the vendor, so the shop only
    offers the two bands around the player's own level. SendListInventory
    filters through GetConditionsForNpcVendorEvent, so this is honoured by the
    core with no custom code.

Run:  python gen_tiered_gear.py     (writes ../db-world/cw_items_tiered.sql)
"""
import json, os, textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, os.pardir, "db-world", "cw_items_tiered.sql")
DISPLAYS = os.path.join(HERE, "displays.json")

FIRST_ENTRY = 990300
VENDOR = 990100
VERIFIED = 12340

# stat ids (item_template.stat_type*)
AGI, STR, INT, SPI, STA, CRIT, AP, SP = 3, 4, 5, 6, 7, 32, 38, 45

BANDS = [1, 10, 20, 30, 40, 50, 60, 70, 80]
TIER_NAME = {1: "Apprentice's", 10: "Journeyman's", 20: "Adept's",
             30: "Veteran's", 40: "Champion's", 50: "Master's",
             60: "Grand Master's", 70: "Heroic", 80: "Ascendant"}

# armor per level for a chest piece, by armour class; other slots scale down
ARMOR_PER_LEVEL = {"cloth": 2.0, "leather": 3.2, "mail": 5.0, "plate": 7.0,
                   "shield": 26.0}

# (base copper, copper per level) by price class
PRICE = {"weapon2h": (400, 900), "weapon1h": (300, 700), "big_armor": (250, 600),
         "small_armor": (200, 420), "jewel": (250, 500)}


def T(key, name, cls, sub, inv, disp, stats, *, kind, price, speed=0,
      armor_class=None, slot=1.0, mat=1, sheath=0, desc=""):
    return dict(key=key, name=name, cls=cls, sub=sub, inv=inv, disp=disp,
                stats=stats, kind=kind, price=price, speed=speed,
                armor_class=armor_class, slot=slot, mat=mat, sheath=sheath,
                desc=desc)


TEMPLATES = [
    # ---- weapons: the wrong stat on the wrong weapon, on purpose ----
    T("gun_int", "Arcane Handcannon", 2, 3, 26, "gun",
      [(INT, 1.0), (SP, 1.6), (STA, 0.5)], kind="weapon", price="weapon1h",
      speed=2900, mat=1, desc="A firearm that answers to intellect."),
    T("bow_str", "Bruteforce Longbow", 2, 2, 15, "bow",
      [(STR, 1.0), (STA, 0.5)], kind="weapon", price="weapon1h",
      speed=2800, mat=2, desc="Drawn by main strength, not finesse."),
    T("staff_str", "Ironbark Warstaff", 2, 10, 17, "staff",
      [(STR, 1.2), (STA, 0.8)], kind="weapon", price="weapon2h",
      speed=3300, mat=4, sheath=2, desc="A staff for hitting things."),
    T("polearm_int", "Arcane Pike", 2, 6, 17, "polearm",
      [(INT, 1.1), (SP, 1.6), (STA, 0.6)], kind="weapon", price="weapon2h",
      speed=3300, mat=1, sheath=1, desc="A polearm that reaches further than its blade."),
    T("axe2h_agi", "Windrunner Cleaver", 2, 1, 17, "axe2h",
      [(AGI, 1.2), (STA, 0.8)], kind="weapon", price="weapon2h",
      speed=3400, mat=1, sheath=1, desc="A greataxe balanced for the fleet of foot."),
    T("dagger_str", "Kingslayer Dagger", 2, 15, 13, "dagger",
      [(STR, 0.9), (STA, 0.5), (CRIT, 0.4)], kind="weapon", price="weapon1h",
      speed=1800, mat=1, sheath=3, desc="A dagger with a claymore's attitude."),
    T("mace_agi", "Hammer of Quiet Malice", 2, 4, 13, "mace1h",
      [(AGI, 1.0), (STA, 0.5)], kind="weapon", price="weapon1h",
      speed=2400, mat=1, sheath=3, desc="A mace balanced for someone light on their feet."),
    T("sword_int", "Spellbinder Blade", 2, 7, 13, "sword1h",
      [(INT, 1.0), (SP, 1.5), (STA, 0.5)], kind="weapon", price="weapon1h",
      speed=2400, mat=1, sheath=3, desc="A sword that carries spellpower instead of muscle."),
    T("fist_sp", "Sparkfist Talon", 2, 13, 13, "fist",
      [(SP, 1.6), (INT, 0.7), (STA, 0.5)], kind="weapon", price="weapon1h",
      speed=2500, mat=1, sheath=3, desc="For those who cast with their knuckles."),
    T("wand_ap", "Wand of Brutal Focus", 2, 19, 26, "wand",
      [(STR, 0.7), (AP, 1.8)], kind="weapon", price="weapon1h",
      speed=1800, mat=1, desc="A wand that lends attack power."),

    # ---- armour: the wrong armour class for the stats it carries ----
    T("plate_chest_sp", "Runeplate Vestment", 4, 4, 5, "plate_chest",
      [(SP, 1.6), (INT, 0.9), (STA, 0.8)], kind="armor", price="big_armor",
      armor_class="plate", slot=1.0, mat=6, desc="Full plate that channels spellpower."),
    T("mail_chest_str", "Bulwark Chainmail", 4, 3, 5, "mail_chest",
      [(STR, 1.1), (STA, 0.9)], kind="armor", price="big_armor",
      armor_class="mail", slot=1.0, mat=5, desc="Mail cut for raw strength."),
    T("leather_chest_int", "Zealot Hide Jerkin", 4, 2, 5, "leather_chest",
      [(INT, 1.0), (SP, 1.4), (STA, 0.7)], kind="armor", price="big_armor",
      armor_class="leather", slot=1.0, mat=8, desc="Spellpower leather, mobility without the silk."),
    T("cloth_robe_ap", "Ironweave Battlerobe", 4, 1, 20, "cloth_robe",
      [(AGI, 1.0), (AP, 2.0), (STA, 0.8)], kind="armor", price="big_armor",
      armor_class="cloth", slot=1.0, mat=7, desc="A robe carrying attack power. Nobody else would dare."),
    T("plate_legs_agi", "Legplates of the Windwalker", 4, 4, 7, "plate_legs",
      [(AGI, 1.1), (STA, 0.8)], kind="armor", price="big_armor",
      armor_class="plate", slot=0.9, mat=6, desc="Plate legs light enough to sprint in. Allegedly."),
    T("mail_legs_sp", "Chainweave Leggings", 4, 3, 7, "mail_legs",
      [(SP, 1.4), (SPI, 0.7), (STA, 0.7)], kind="armor", price="big_armor",
      armor_class="mail", slot=0.9, mat=5, desc="Mail that favours spirit over brawn."),
    T("cloak_str", "Warcloak of the Untethered", 4, 1, 16, "cloak",
      [(STR, 0.9), (STA, 0.5)], kind="armor", price="small_armor",
      armor_class="cloth", slot=0.35, mat=7, desc="A cloak for the ones who close the distance."),
    T("shield_int", "Barrier of Raw Intellect", 4, 6, 14, "shield",
      [(INT, 0.9), (SP, 1.3), (STA, 0.6)], kind="armor", price="small_armor",
      armor_class="shield", slot=1.0, mat=1, desc="A shield for casters who refuse to stand at the back."),

    # ---- jewellery and off-hands: hybrid pairs ----
    T("neck_hybrid", "Chain of the Untethered", 4, 0, 2, "neck",
      [(STR, 0.7), (INT, 0.7), (STA, 0.5)], kind="jewel", price="jewel",
      desc="Strength and intellect on one chain."),
    T("ring_hybrid", "Loop of Contradiction", 4, 0, 11, "ring",
      [(AGI, 0.7), (SP, 1.1), (STA, 0.4)], kind="jewel", price="jewel",
      desc="Agility and spellpower have no quarrel here."),
    T("trinket_sp", "Focus of the Untethered", 4, 0, 12, "trinket",
      [(SP, 1.5), (STA, 0.5)], kind="jewel", price="jewel",
      desc="A focus that hums with borrowed power."),
    T("offhand_ap", "Grimoire of the Berserker", 4, 0, 23, "offhand",
      [(AGI, 0.8), (AP, 1.6), (STA, 0.5)], kind="jewel", price="jewel",
      desc="An off-hand book carrying attack power."),
]

displays = json.load(open(DISPLAYS, encoding="utf-8"))


def esc(s):
    return s.replace("'", "''")


def stat_budget(level):
    return max(2, round(level * 0.6))


def build_rows():
    rows, conds, entry = [], [], FIRST_ENTRY
    for band in BANDS:
        for t in TEMPLATES:
            P = stat_budget(band)
            stats = []
            for sid, weight in t["stats"][:3]:
                stats.append((sid, max(1, int(round(P * weight)))))
            while len(stats) < 3:
                stats.append((0, 0))

            # weapon damage from a dps curve, armour from a per-level curve
            dmin = dmax = delay = 0
            armor = 0
            if t["kind"] == "weapon":
                dps = 1.2 + band * 0.9
                delay = t["speed"]
                swing = delay / 1000.0
                dmin = int(round(dps * swing * 0.8))
                dmax = int(round(dps * swing * 1.2))
                dmin = max(1, dmin)
                dmax = max(dmin + 1, dmax)
            elif t["armor_class"]:
                armor = int(round(ARMOR_PER_LEVEL[t["armor_class"]] * band * t["slot"]))

            base, per = PRICE[t["price"]]
            buy = base + band * per
            sell = buy // 5

            quality = 2 if band <= 20 else (3 if band <= 60 else 4)
            looks = displays[t["disp"]]
            disp = looks[BANDS.index(band) % len(looks)]
            durability = 0 if t["kind"] == "jewel" else (55 + band if t["kind"] == "weapon" else 40 + band)

            rows.append(dict(
                entry=entry, cls=t["cls"], sub=t["sub"],
                name="%s %s" % (TIER_NAME[band], t["name"]),
                disp=disp, quality=quality, buy=buy, sell=sell, inv=t["inv"],
                ilvl=band, req=band, stats=stats, dmin=dmin, dmax=dmax,
                delay=delay, armor=armor, dur=durability, mat=t["mat"],
                sheath=t["sheath"], desc=t["desc"], band=band))
            entry += 1

    # vendor visibility: show a band from its own level until two bands on
    for r in rows:
        i = BANDS.index(r["band"])
        lo = r["band"]
        hi = BANDS[i + 2] - 1 if i + 2 < len(BANDS) else 80
        conds.append((r["entry"], lo, hi))
    return rows, conds


rows, conds = build_rows()
last = rows[-1]["entry"]

L = []
L.append(textwrap.dedent("""\
    -- mod-classless-wildcard: tiered classless gear (GENERATED)
    --
    -- Do not hand-edit: regenerate with data/sql/generators/gen_tiered_gear.py.
    --
    -- The same "stat combination the class system would never allow" idea as the
    -- other packs, but spread across nine level bands from 1 to 80, so a Hero has
    -- something to buy the whole way up instead of only at level 35.
    --
    -- Prices scale with level and start in silver: band-1 gear costs a few silver,
    -- level 80 pieces a handful of gold.
    --
    -- Each item carries a `conditions` row (source type 23 = NPC_VENDOR) limiting
    -- it to the two bands around the buyer's level, so the shop stays readable
    -- instead of listing every piece at once. The core applies this itself in
    -- SendListInventory via GetConditionsForNpcVendorEvent.
    """))
L.append("DELETE FROM `item_template` WHERE `entry` BETWEEN %d AND %d;" % (FIRST_ENTRY, last))
L.append("INSERT INTO `item_template`")
L.append("  (`entry`, `class`, `subclass`, `name`, `displayid`, `Quality`, `BuyCount`, `BuyPrice`, `SellPrice`,")
L.append("   `InventoryType`, `AllowableClass`, `AllowableRace`, `ItemLevel`, `RequiredLevel`, `stackable`,")
L.append("   `stat_type1`, `stat_value1`, `stat_type2`, `stat_value2`, `stat_type3`, `stat_value3`,")
L.append("   `dmg_min1`, `dmg_max1`, `dmg_type1`, `delay`, `armor`, `bonding`, `MaxDurability`, `Material`, `sheath`,")
L.append("   `description`, `VerifiedBuild`)")
L.append("VALUES")
for n, r in enumerate(rows):
    end = ";" if n == len(rows) - 1 else ","
    s = r["stats"]
    L.append("(%d, %d, %d, '%s', %d, %d, 1, %d, %d, %d, -1, -1, %d, %d, 1, "
             "%d, %d, %d, %d, %d, %d, %d, %d, 0, %d, %d, 2, %d, %d, %d, '%s', %d)%s"
             % (r["entry"], r["cls"], r["sub"], esc(r["name"]), r["disp"], r["quality"],
                r["buy"], r["sell"], r["inv"], r["ilvl"], r["req"],
                s[0][0], s[0][1], s[1][0], s[1][1], s[2][0], s[2][1],
                r["dmin"], r["dmax"], r["delay"], r["armor"], r["dur"],
                r["mat"], r["sheath"], esc(r["desc"]), VERIFIED, end))

L.append("")
L.append("-- sell them all from the Hero Advancement NPC")
L.append("DELETE FROM `npc_vendor` WHERE `entry` = %d AND `item` BETWEEN %d AND %d;" % (VENDOR, FIRST_ENTRY, last))
L.append("INSERT INTO `npc_vendor` (`entry`, `slot`, `item`, `maxcount`, `incrtime`, `ExtendedCost`, `VerifiedBuild`)")
L.append("SELECT %d, 100 + (`entry` - %d), `entry`, 0, 0, 0, %d" % (VENDOR, FIRST_ENTRY, VERIFIED))
L.append("FROM `item_template` WHERE `entry` BETWEEN %d AND %d;" % (FIRST_ENTRY, last))

L.append("")
L.append("-- only offer gear near the buyer's own level (23 = NPC_VENDOR,")
L.append("-- 27 = CONDITION_LEVEL; comparison 3 = >=, 4 = <=)")
L.append("DELETE FROM `conditions` WHERE `SourceTypeOrReferenceId` = 23 AND `SourceGroup` = %d" % VENDOR)
L.append("  AND `SourceEntry` BETWEEN %d AND %d;" % (FIRST_ENTRY, last))
L.append("INSERT INTO `conditions`")
L.append("  (`SourceTypeOrReferenceId`, `SourceGroup`, `SourceEntry`, `SourceId`, `ElseGroup`,")
L.append("   `ConditionTypeOrReference`, `ConditionTarget`, `ConditionValue1`, `ConditionValue2`,")
L.append("   `ConditionValue3`, `NegativeCondition`, `ErrorType`, `ErrorTextId`, `ScriptName`, `Comment`)")
L.append("VALUES")
parts = []
for e, lo, hi in conds:
    parts.append("(23, %d, %d, 0, 0, 27, 0, %d, 3, 0, 0, 0, 0, '', 'CW tiered gear: level >= %d')"
                 % (VENDOR, e, lo, lo))
    parts.append("(23, %d, %d, 0, 0, 27, 0, %d, 4, 0, 0, 0, 0, '', 'CW tiered gear: level <= %d')"
                 % (VENDOR, e, hi, hi))
L.append(",\n".join(parts) + ";")
L.append("")

open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(L))

print("wrote %s" % os.path.normpath(OUT))
print("  %d items, entries %d..%d  (%d templates x %d bands)"
      % (len(rows), FIRST_ENTRY, last, len(TEMPLATES), len(BANDS)))
print("  %d vendor conditions" % len(parts))
print()
print("  price / stat sample:")
for band in BANDS:
    r = [x for x in rows if x["band"] == band][0]
    g, s, c = r["buy"] // 10000, (r["buy"] % 10000) // 100, r["buy"] % 100
    money = ("%dg " % g if g else "") + ("%ds " % s if s else "") + ("%dc" % c if c else "")
    print("    level %-2d  %-34s %-10s primary stat %d"
          % (band, r["name"][:34], money.strip(), r["stats"][0][1]))
