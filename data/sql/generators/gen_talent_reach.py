#!/usr/bin/env python3
"""Let general talents reach every class's abilities.

A talent that changes abilities names them by spell family (its class) and a
bit mask of that family's spells; the core applies it to a spell only when the
spell is in the talent's family AND carries one of its bits. So Fire Power
(+10% damage of your Fire spells) reaches mage Fire spells and never a
warlock's Immolate or a Fiery Heroic Strike, Impale reaches warrior strikes and
never a rogue's, and so on for about two thirds of every class talent. On a
classless realm that is wrong: a talent that improves ALL of its class's
abilities of one kind should improve every Hero ability of that kind.

This works out, for every class talent's spell-modifier effect, whether it is
GENERAL or names specific spells:

  * the abilities of its own family it reaches (its mask), counted per ability
    line rather than per rank, must be at least MIN_LINES lines, and
  * they must share a kind -- damage class (spell, melee, ranged), school and
    role (damage or healing), dropping whichever of those they do not share --
    and cover at least MIN_COVERAGE of their family's lines of that kind.

Improved Fireball (one line) is specific. Fire Power (every mage Fire damage
spell) is general, of kind "spell, Fire, damage". Impale (every warrior strike)
is general, of kind "melee". A general effect then also reaches every ability
of every other family that is of the same kind and that its operation can act
on: a cost cut only reaches abilities paid in the same power, a cast-time cut
only abilities with a cast time, a periodic-damage bonus only abilities that
deal periodic damage, and so on. Only the operations that mean the same thing
on any spell are carried across; the ones that change a spell's own effect
values (EFFECT1-3, ALL_EFFECTS, ...) are not, because "+1 to effect 2" means a
different thing on every spell.

Outputs, from the same run so the server and the client agree:

  * data/sql/db-world/cw_talent_reach.sql -- cw_talent_reach, one row per
    (talent, effect, target ability). The server adds a spell modifier per
    target family when the talent's aura is applied (ClasslessMgr talent reach).
  * client-patch/talent_reach_manifest.json -- the cost and cooldown entries,
    which the client patch's cost and cooldown floors need, or the client would
    refuse a cast the server now prices lower.
  * talent_reach_report.txt beside this script: every general effect, its kind
    and how many abilities it now reaches, for review.

Abilities are the pool: what a Hero can buy or be dealt, built the way the
server's BuildLibrary builds it (gen_archetypes.Pool, from the DBCs, the
core's trainer_spell and spell_ranks dumps and the module conf), every rank of
every enabled line that is not passive. The server keeps only targets that
are in its own live pool when it loads the table, so a realm's own settings
always win. Hero talents are not widened: the Hero
tree is the module's own and already aimed at the Hero line.

Run:  python3 gen_talent_reach.py [--dbc DIR]
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_archetypes as archetypes  # noqa: E402  the pool, the way BuildLibrary builds it

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir, os.pardir))
DEFAULT_DBC = r"B:\New folder\dbc"
OUT_SQL = os.path.join(ROOT, "data", "sql", "db-world", "cw_talent_reach.sql")
OUT_MANIFEST = os.path.join(ROOT, "client-patch", "talent_reach_manifest.json")
OUT_REPORT = os.path.join(HERE, "talent_reach_report.txt")
ELEMENTAL_MANIFEST = os.path.join(ROOT, "client-patch", "elemental_manifest.json")
FORGED_MANIFEST = os.path.join(ROOT, "client-patch", "forged_manifest.json")

MIN_LINES = 3          # a talent reaching fewer of its own lines names them
MIN_COVERAGE = 0.6     # share of its family's lines of the kind it must reach

# Spell.dbc 3.3.5a columns (gen_elemental_variants.SPELL_DBC_COLUMNS order)
C = dict(Id=0, Attributes=4, CastingTimeIndex=28, RecoveryTime=29, CategoryRecoveryTime=30,
         DurationIndex=40, PowerType=41, ManaCost=42, RangeIndex=46, Effect=71, EffectAura=95,
         EffectMiscValue=110, EffectClassMask=122, Family=208, FamilyFlags=209, DmgClass=213,
         ManaCostPct=204, SchoolMask=225, Name=136, BasePoints=80, DieSides=74)
ATTR0_PASSIVE = 0x40
ATTR0_HIDDEN = 0x80    # SPELL_ATTR0_DO_NOT_DISPLAY
SKILL_CATEGORY_CLASS = 7
HERO_FAMILY = 14

EFFECT_APPLY_AURA = 6
AURA_ADD_FLAT_MODIFIER = 107
AURA_ADD_PCT_MODIFIER = 108
DAMAGE_EFFECTS = {2, 9, 17, 31, 58, 121}       # school, leech, weapon (x4)
HEAL_EFFECTS = {10, 67, 136}                   # heal, heal max health, heal pct
PERIODIC_DAMAGE_AURAS = {3, 53, 89}            # periodic damage, leech, damage pct
PERIODIC_HEAL_AURAS = {8, 20}                  # periodic heal, heal pct

# SpellModOp: what each operation can act on, or None when it is not carried
OPS = {
    0: "damage", 1: "duration", 2: "threat", 5: "range", 6: "radius", 7: "crit chance",
    9: "pushback", 10: "cast time", 11: "cooldown", 14: "cost", 15: "crit damage",
    16: "hit", 22: "periodic damage", 24: "bonus coefficient", 28: "dispel resistance",
}
FAMILIES = {3: "mage", 4: "warrior", 5: "warlock", 6: "priest", 7: "druid", 8: "rogue",
            9: "hunter", 10: "paladin", 11: "shaman", 15: "death knight", 14: "hero"}
SCHOOLS = {1: "Physical", 2: "Holy", 4: "Fire", 8: "Nature", 16: "Frost", 32: "Shadow", 64: "Arcane"}
DMGCLASS = {0: "none", 1: "spell", 2: "melee", 3: "ranged"}


class Dbc:
    def __init__(self, path):
        self.blob = open(path, "rb").read()
        magic, self.rows, self.fields, self.rec, self.strsize = struct.unpack_from("<4sIIII", self.blob, 0)
        if magic != b"WDBC":
            sys.exit("%s is not a WDBC file" % path)
        self.body = 20
        self.strings = self.blob[self.body + self.rows * self.rec:]

    def row(self, index):
        return list(struct.unpack_from("<%di" % self.fields, self.blob, self.body + index * self.rec))

    def text(self, offset):
        end = self.strings.find(b"\0", offset)
        return self.strings[offset:end].decode("utf-8", "replace") if end >= 0 else ""


def u32(v):
    return v & 0xFFFFFFFF


class Spells:
    """Every Spell.dbc row, plus the generated rows (a donor row overlaid with
    the manifest's fields), as lists of signed ints."""

    def __init__(self, dbc_dir):
        self.dbc = Dbc(os.path.join(dbc_dir, "Spell.dbc"))
        self.rows = {}
        self.names = {}
        for i in range(self.dbc.rows):
            r = self.dbc.row(i)
            self.rows[r[0]] = r
            self.names[r[0]] = self.dbc.text(u32(r[C["Name"]]))

    def add_generated(self, entry):
        donor = self.rows.get(entry["base"])
        if donor is None:
            return None
        row = list(donor)
        for col, value in entry.get("fields", {}).items():
            col = int(col)
            if isinstance(value, int):
                row[col] = value if value < 0x80000000 else value - 0x100000000
        row[0] = entry["id"]
        self.rows[entry["id"]] = row
        self.names[entry["id"]] = entry.get("name", "")
        return row


def flags(row):
    return (u32(row[C["FamilyFlags"]]), u32(row[C["FamilyFlags"] + 1]), u32(row[C["FamilyFlags"] + 2]))


def effect_mask(row, e):
    base = C["EffectClassMask"] + 3 * e
    return (u32(row[base]), u32(row[base + 1]), u32(row[base + 2]))


def hits(a, b):
    return any(x & y for x, y in zip(a, b))


def role(row):
    effects = [row[C["Effect"] + e] for e in range(3)]
    auras = [row[C["EffectAura"] + e] for e in range(3)]
    if any(e in DAMAGE_EFFECTS for e in effects) or any(a in PERIODIC_DAMAGE_AURAS for a in auras):
        return "damage"
    if any(e in HEAL_EFFECTS for e in effects) or any(a in PERIODIC_HEAL_AURAS for a in auras):
        return "heal"
    return "other"


def school(row):
    return u32(row[C["SchoolMask"]])


def has_periodic_damage(row):
    return any(row[C["EffectAura"] + e] in PERIODIC_DAMAGE_AURAS for e in range(3))


def cost_of(row):
    return row[C["ManaCost"]] > 0 or row[C["ManaCostPct"]] > 0


def can_take(op, row, power):
    """Whether operation `op` means anything on ability `row`."""
    if op == 14:
        return cost_of(row) and row[C["PowerType"]] == power
    if op == 11:
        return row[C["RecoveryTime"]] > 0 or row[C["CategoryRecoveryTime"]] > 0
    if op in (10, 9):
        return row[C["CastingTimeIndex"]] not in (0, 1)
    if op == 1:
        return row[C["DurationIndex"]] != 0
    if op == 22:
        return has_periodic_damage(row)
    if op in (7, 15, 0, 24):
        return role(row) in ("damage", "heal")
    if op == 5:
        return row[C["RangeIndex"]] not in (0, 1)
    return True


def instant(row):
    return row[C["CastingTimeIndex"]] in (0, 1)


def delivery(row):
    """How a damage or heal lands: 'direct', 'periodic' or 'both'."""
    effects = [row[C["Effect"] + e] for e in range(3)]
    auras = [row[C["EffectAura"] + e] for e in range(3)]
    direct = any(e in DAMAGE_EFFECTS or e in HEAL_EFFECTS for e in effects)
    periodic = any(a in PERIODIC_DAMAGE_AURAS or a in PERIODIC_HEAL_AURAS for a in auras)
    return "both" if direct and periodic else "direct" if direct else "periodic" if periodic else "none"


# The traits a kind is made of, in the order they are reported.
TRAITS = (("dmgclass", lambda r: r[C["DmgClass"]]), ("school", school), ("role", role),
          ("delivery", delivery), ("instant", instant))
KIND_MAJORITY = 0.8    # a trait defines the kind when this share of the lines share it
ABSENT = {"other", "none", "both"}   # trait values that mean "nothing shared"
DAMAGE_OPS = {0, 7, 15, 16, 22, 24}  # damage, crit, crit damage, hit, periodic, coefficient
SUMMON_TOTEM_EFFECTS = {87, 88, 89, 90}


def traits_for(op):
    """The traits that bear on what operation `op` changes."""
    if op in DAMAGE_OPS:
        return {"dmgclass", "school", "role", "delivery", "instant"}
    if op == 14:
        return {"dmgclass", "school", "role", "instant"}
    if op in (11, 10, 9):
        return {"dmgclass", "school", "role"}
    return {"dmgclass", "school"}


TOTEM_SUMMON_PROPERTIES = {63, 81, 82, 83}   # SummonProperties rows for the four totem slots


def is_totem(row):
    # 3.3.5 totems are SPELL_EFFECT_SUMMON (28) into a totem slot, EffectMiscValueB
    return any(row[C["Effect"] + e] in SUMMON_TOTEM_EFFECTS
               or (row[C["Effect"] + e] == 28 and row[113 + e] in TOTEM_SUMMON_PROPERTIES)
               for e in range(3))
EXPLAIN = set()        # talent names (lower case) to print the reasoning for


def class_spell_ids(dbc_dir):
    sla = Dbc(os.path.join(dbc_dir, "SkillLineAbility.dbc"))
    skill = Dbc(os.path.join(dbc_dir, "SkillLine.dbc"))
    category = {}
    for i in range(skill.rows):
        r = skill.row(i)
        category[r[0]] = r[1]
    ids = set()
    for i in range(sla.rows):
        r = sla.row(i)
        if category.get(r[1]) == SKILL_CATEGORY_CLASS:
            ids.add(r[2])
    return ids


def talent_ranks(dbc_dir):
    """Class talents as lists of rank spell ids, rank 1 first."""
    talent = Dbc(os.path.join(dbc_dir, "Talent.dbc"))
    tab = Dbc(os.path.join(dbc_dir, "TalentTab.dbc"))
    class_tab = {}
    for i in range(tab.rows):
        r = tab.row(i)
        class_tab[r[0]] = u32(r[20])         # ClassMask; pet trees have none
    out = []
    for i in range(talent.rows):
        r = talent.row(i)
        if not class_tab.get(r[1]):
            continue
        ranks = [x for x in r[4:13] if x > 0]
        if ranks:
            out.append(ranks)
    return out


def modifier_value(row, e):
    v = row[C["BasePoints"] + e]
    if row[C["DieSides"] + e] == 1:
        v += 1
    return v


def build(dbc_dir, conf_path):
    spells = Spells(dbc_dir)
    # The generated rows, so every pool spell has a full row to read.
    for path, key in ((ELEMENTAL_MANIFEST, "variants"), (FORGED_MANIFEST, "spells")):
        for entry in json.load(open(path, encoding="utf-8")).get(key, []):
            spells.add_generated(entry)

    # The abilities are the POOL: what a Hero can buy or be dealt, built the
    # way BuildLibrary builds it (gen_archetypes.Pool: class lines with a
    # trainer, minus utility, auto-repeat, disabled and talent spells, plus
    # the elemental variants and the Hero line), every rank of every enabled
    # line that is not passive. Judging talents and choosing targets from
    # anything wider counted spells no Hero can own.
    pool = archetypes.Pool(dbc_dir, archetypes.DEFAULT_CORE, archetypes.read_conf(conf_path),
                           ELEMENTAL_MANIFEST)
    abilities = {sid for e in pool.abilities.values() if e["enabled"] and not e["passive"]
                 for sid in e["ranks"] if sid in spells.rows and spells.rows[sid][C["Family"]]}

    # One ability "line" per set of class bits. Blizzard gives related spells
    # the same bit -- every rank, the eight Judgements, a strike and its
    # elemental variants -- so counting bit sets counts what a talent can tell
    # apart. Counting names let "all Judgements" pass for most of a paladin's
    # melee, and every elemental copy of a strike count as another strike.
    def line(sid):
        row = spells.rows[sid]
        return (row[C["Family"]], flags(row))

    by_family = collections.defaultdict(set)
    for sid in abilities:
        by_family[spells.rows[sid][C["Family"]]].add(sid)
    # each family's lines, one row per line (the lowest rank), for trait shares
    family_lines = collections.defaultdict(dict)
    for sid in sorted(abilities):
        family_lines[spells.rows[sid][C["Family"]]].setdefault(line(sid), spells.rows[sid])

    general = []           # dicts, one per widened talent effect
    skipped = collections.Counter()
    for ranks in talent_ranks(dbc_dir):
        first = ranks[0]
        trow = spells.rows.get(first)
        if trow is None:
            continue
        family = trow[C["Family"]]
        if not family or family == HERO_FAMILY:
            continue
        for e in range(3):
            if trow[C["Effect"] + e] != EFFECT_APPLY_AURA:
                continue
            aura = trow[C["EffectAura"] + e]
            if aura not in (AURA_ADD_FLAT_MODIFIER, AURA_ADD_PCT_MODIFIER):
                continue
            mask = effect_mask(trow, e)
            if not any(mask):
                continue
            op = trow[C["EffectMiscValue"] + e]
            if op not in OPS:
                skipped["operation not carried across"] += 1
                continue
            own = {sid for sid in by_family[family]
                   if hits(flags(spells.rows[sid]), mask) and not is_totem(spells.rows[sid])}
            # A damage, critical or hit talent is about the spells it can
            # actually make hit harder: judge it on its damaging and healing
            # spells, not on the buffs that happen to share its bits.
            if op in DAMAGE_OPS:
                own = {s for s in own if role(spells.rows[s]) in ("damage", "heal")}
            # one representative row per line: the lowest rank
            line_row = {}
            for s in sorted(own):
                line_row.setdefault(line(s), spells.rows[s])
            if len(line_row) < MIN_LINES:
                skipped["names specific abilities"] += 1
                continue

            # The kind: each trait the great majority of the reached lines
            # share. A majority rather than all of them, so one odd spell in a
            # mask (a utility spell sharing a bit) does not loosen the kind to
            # "anything" and carry a strike talent onto heals. Only the traits
            # that bear on what the talent changes, and only real values: a
            # shared "no damage" says nothing. School only when it narrows:
            # nearly every paladin spell is Holy, so "Holy" in a paladin talent
            # says nothing about the talent.
            kind = {}
            for key, fn in TRAITS:
                if key not in traits_for(op):
                    continue
                counts = collections.Counter(fn(r) for r in line_row.values())
                value, n = counts.most_common(1)[0]
                if value in ABSENT or n < KIND_MAJORITY * len(line_row):
                    continue
                if key == "school":
                    share = sum(1 for r in family_lines[family].values() if fn(r) == value) \
                        / max(1, len(family_lines[family]))
                    if share >= KIND_MAJORITY:
                        continue
                kind[key] = value

            def of_kind(row):
                if is_totem(row):
                    return False
                for key, fn in TRAITS:
                    if key not in kind:
                        continue
                    value = fn(row)
                    # a spell that hits AND lingers (every elemental strike's
                    # burn or poison) is both a direct and a periodic one
                    if key == "delivery" and value == "both" and kind[key] in ("direct", "periodic"):
                        continue
                    if value != kind[key]:
                        return False
                return True

            reached = {ln for ln, r in line_row.items() if of_kind(r)}
            kind_lines = {line(s) for s in by_family[family] if of_kind(spells.rows[s])}
            coverage = len(reached) / max(1, len(kind_lines))
            if EXPLAIN and spells.names.get(first, "").lower() in EXPLAIN:
                print("-- %s effect %d op %s (%s): %d own lines, kind %s, %d of %d kind lines (%.0f%%)"
                      % (spells.names.get(first), e, OPS.get(op, op), "flat" if aura == AURA_ADD_FLAT_MODIFIER else "pct",
                         len(line_row), kind_text(kind), len(reached), len(kind_lines), coverage * 100))
                print("     reaches:", sorted(spells.names.get(r[0], "") for r in line_row.values())[:40])
                missing = kind_lines - reached
                print("     kind lines not reached:", sorted({spells.names.get(s, "") for s in by_family[family]
                                                          if line(s) in missing})[:40])
            if len(reached) < MIN_LINES or coverage < MIN_COVERAGE:
                skipped["names specific abilities"] += 1
                continue
            own_lines = reached

            power = None
            if op == 14:
                powers = {spells.rows[s][C["PowerType"]] for s in own if cost_of(spells.rows[s])}
                if len(powers) != 1:
                    skipped["cost cut over mixed powers"] += 1
                    continue
                power = powers.pop()

            targets = sorted(sid for sid in abilities
                             if spells.rows[sid][C["Family"]] != family
                             and of_kind(spells.rows[sid]) and can_take(op, spells.rows[sid], power))
            if not targets:
                continue

            # the deepest value any rank gives, for the client's floors
            values = [modifier_value(spells.rows[r], e) for r in ranks if r in spells.rows]
            deepest = min(values) if op in (14, 11, 10) else max(values)
            general.append(dict(talent=first, ranks=ranks, effect=e, op=op,
                                flat=aura == AURA_ADD_FLAT_MODIFIER, value=deepest,
                                name=spells.names.get(first, ""), family=family, kind=kind,
                                own_lines=len(own_lines), coverage=coverage, targets=targets))
    return spells, abilities, general, skipped


def kind_text(kind):
    parts = []
    if "dmgclass" in kind:
        parts.append(DMGCLASS.get(kind["dmgclass"], str(kind["dmgclass"])))
    if "school" in kind:
        parts.append("/".join(n for b, n in SCHOOLS.items() if kind["school"] & b) or "?")
    if "role" in kind:
        parts.append(kind["role"])
    if "delivery" in kind:
        parts.append(kind["delivery"])
    if "instant" in kind:
        parts.append("instant" if kind["instant"] else "cast")
    return ", ".join(parts) or "any ability"


def generation_id(general):
    h = hashlib.sha1()
    for g in general:
        h.update(("%d:%d:%d:%s;" % (g["talent"], g["effect"], g["op"], ",".join(map(str, g["targets"])))).encode())
    return h.hexdigest()[:12]


def write_sql(general, path, gen):
    rows = sum(len(g["targets"]) for g in general)
    out = [
        "-- mod-classless-wildcard: talents that reach every class (GENERATED)",
        "--",
        "-- Do not hand-edit: regenerate with data/sql/generators/gen_talent_reach.py.",
        "--",
        "-- A class talent's spell modifier reaches only its own class's abilities, by",
        "-- family and bit. For every talent effect that improves ALL of its class's",
        "-- abilities of one kind (damage class, school, role), each row here is an",
        "-- ability of another class of that kind which it now also reaches. The server",
        "-- adds the modifiers when the talent's aura is applied; the client patch reads",
        "-- the cost and cooldown rows from talent_reach_manifest.json, same run.",
        "--",
        "-- %d talent effects, %d rows. Generation: %s" % (len(general), rows, gen),
        "",
        "CREATE TABLE IF NOT EXISTS `cw_talent_reach` (",
        "  `talent_spell` INT UNSIGNED NOT NULL COMMENT 'rank 1 of the talent',",
        "  `effect`       TINYINT UNSIGNED NOT NULL COMMENT 'effect index 0-2 of the talent spell',",
        "  `target_spell` INT UNSIGNED NOT NULL COMMENT 'an ability of another class it also reaches',",
        "  PRIMARY KEY (`talent_spell`, `effect`, `target_spell`)",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Classless general talents across classes';",
        "",
        "DELETE FROM `cw_talent_reach`;",
    ]
    values = ["(%d,%d,%d)" % (g["talent"], g["effect"], t) for g in general for t in g["targets"]]
    for i in range(0, len(values), 500):
        out.append("INSERT INTO `cw_talent_reach` (`talent_spell`, `effect`, `target_spell`) VALUES")
        out.append(",\n".join(values[i:i + 500]) + ";")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
    return rows


def write_manifest(general, path, gen):
    entries = [dict(talent=g["talent"], ranks=g["ranks"], effect=g["effect"], op=g["op"],
                    flat=g["flat"], value=g["value"], targets=g["targets"])
               for g in general if g["op"] in (11, 14)]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(dict(version=1, generation=gen, entries=entries), fh, indent=1)
        fh.write("\n")
    return len(entries)


def write_report(spells, general, skipped, path, gen):
    lines = ["Talents that reach every class -- generation %s" % gen, ""]
    by_family = collections.defaultdict(list)
    for g in general:
        by_family[g["family"]].append(g)
    for fam in sorted(by_family, key=lambda f: FAMILIES.get(f, str(f))):
        lines.append("== %s" % FAMILIES.get(fam, fam))
        for g in sorted(by_family[fam], key=lambda g: g["name"]):
            lines.append("   %-34s %-18s %-30s %3d own lines (%3d%%)  -> %4d abilities of other classes"
                         % (g["name"], OPS[g["op"]], kind_text(g["kind"]), g["own_lines"],
                            round(g["coverage"] * 100), len(g["targets"])))
    lines.append("")
    lines.append("Not widened: " + ", ".join("%s %d" % (k, v) for k, v in sorted(skipped.items())))
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dbc", default=DEFAULT_DBC, help="directory of extracted 3.3.5a DBCs")
    ap.add_argument("--conf", default=archetypes.DEFAULT_CONF,
                    help="module conf the pool is built with (IncludeDeathKnight, IncludeRacials, ...)")
    ap.add_argument("--explain", action="append", default=[],
                    help="print how this talent (by name) was judged; repeatable")
    args = ap.parse_args(argv)
    EXPLAIN.update(n.lower() for n in args.explain)
    spells, abilities, general, skipped = build(args.dbc, args.conf)
    gen = generation_id(general)
    rows = write_sql(general, OUT_SQL, gen)
    client = write_manifest(general, OUT_MANIFEST, gen)
    write_report(spells, general, skipped, OUT_REPORT, gen)
    print("abilities considered: %d" % len(abilities))
    print("general talent effects: %d (%d rows); client cost/cooldown entries: %d" % (len(general), rows, client))
    print("not widened: %s" % dict(skipped))
    print("wrote %s\n      %s\n      %s" % (OUT_SQL, OUT_MANIFEST, OUT_REPORT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
