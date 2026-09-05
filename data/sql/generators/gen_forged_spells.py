#!/usr/bin/env python3
"""Build the forged spells: brand-new abilities that belong to no class.

Reads the client's extracted DBCs and writes two things from ONE source, so the
server's numbers and the client's tooltips cannot drift:

    ../db-world/cw_spells_forged.sql   server rows (skillline_dbc,
                                       skillraceclassinfo_dbc, spell_dbc,
                                       skilllineability_dbc, spell_ranks,
                                       cw_forged_spells)
    ../../../client-patch/forged_manifest.json
                                       what the installer appends to the
                                       player's own SkillLine, Spell,
                                       SpellVisual and SkillLineAbility

Run:  python3 gen_forged_spells.py [--dbc DIR] [--only KEY,KEY,...]

Every spell is a donor row with fields overridden, never a row built from
nothing: that way attributes, interrupt flags and equipped-item requirements
come from a spell the game already ships and already works.

Damage and healing come off the anchors in CURVE, which were measured from the
median of every trainable class rank at that level. Anything the curve cannot
price -- a damage reduction, an interrupt lockout -- is a literal, checked by
hand against a named spell and recorded in the recipe's `compare` field.
"""
import argparse
import hashlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from gen_elemental_variants import (Dbc, F, SPELL_DBC_COLUMNS, LOCALE_BLOCKS,
                                    STRING_FIELDS, spell_values, sql_literal)

OUT_SQL = os.path.join(HERE, os.pardir, "db-world", "cw_spells_forged.sql")
OUT_MANIFEST = os.path.join(HERE, os.pardir, os.pardir, os.pardir,
                            "client-patch", "forged_manifest.json")
DEFAULT_DBC = r"B:\New folder\dbc"

# ---- id blocks --------------------------------------------------------------
# A recipe's block depends on its index in RECIPES, so adding a recipe never
# renumbers spells a player already owns. 32 ids each: up to 16 ranks, and a
# hidden companion for every rank where one is needed.
SPELL_BASE = 960000          # elemental variants end at 957167, items are 990xxx
PER_RECIPE = 32
# Clear of BOTH the stock tables and the elemental generator's blocks. The
# elemental run allocates one visual and one SkillLineAbility id per variant
# RANK, not per line: 189 lines are 1085 rows today and the block is sized for
# 64 bases x 7 elements x 16 ranks = 7168. So elemental owns 17000..24167 of
# SpellVisual and 22000..29167 of SkillLineAbility in the worst case, and these
# start above that. check_blocks() below enforces it against the real manifest.
SLA_BASE = 35000             # stock SkillLineAbility ends at 21980
VISUAL_BASE = 30000          # stock SpellVisual ends at 16679
BLOCK_END = SPELL_BASE + 64 * PER_RECIPE - 1

HERO_LINE = 990              # highest SkillLine.dbc id the client ships is 788
HERO_LINE_NAME = "Hero"
HERO_LINE_ICON = 3411        # Ability_Hunter_FocusedAim, unused by any pool spell
SKILL_CATEGORY_CLASS = 7
RCI_ID = 990500              # skillraceclassinfo_dbc, clear of cw_world_skillraceclass
RCI_FLAGS = 1040             # what the module's other class-line rows use
ALL_CLASSES = 0x5FF

# ---- the curve --------------------------------------------------------------
# (band midpoint, median value) measured over 540 damage and 158 heal effects
# on trainable class ranks. Interpolated linearly; a fitted power law overshoots
# the middle bands by about a quarter.
CURVE = {
    "dmg":  [(5, 15), (15, 43), (25, 92), (35, 176), (45, 261), (55, 350), (65, 469), (75, 655)],
    "heal": [(5, 51), (15, 197), (25, 286), (35, 435), (45, 567), (55, 880), (65, 1190), (75, 2150)],
}


def anchor(kind, level):
    pts = CURVE[kind]
    if level <= pts[0][0]:
        return float(pts[0][1])
    if level >= pts[-1][0]:
        return float(pts[-1][1])
    for (l0, v0), (l1, v1) in zip(pts, pts[1:]):
        if l0 <= level <= l1:
            return v0 + (v1 - v0) * (level - l0) / float(l1 - l0)
    return float(pts[-1][1])


# ---- effect, aura and index constants, all verified against real rows -------
E_SCHOOL_DAMAGE, E_DUMMY, E_HEAL = 2, 3, 10
E_PERSISTENT_AREA, E_SUMMON, E_ENERGIZE = 27, 28, 30
E_INTERRUPT_CAST, E_TRIGGER_SPELL = 68, 64
# 31 takes base points as a PERCENTAGE of weapon damage (Backstab is 127).
# 121 is normalized weapon damage plus base points as a FLAT add (Sinister
# Strike is +3). They are easy to swap by accident and the mistake is silent:
# 110 on 121 is +110 damage at level 1, not 110% of a weapon.
E_WEAPON_PERCENT, E_NORMALIZED_WEAPON_DMG, E_CHARGE = 31, 121, 96
E_PULL_TOWARDS_DEST = 145            # the core comments this "Black Hole Effect"
E_APPLY_AURA = 6

A_PERIODIC_DAMAGE_AREA = 4           # on a persistent area
A_MOD_CONFUSE = 5                    # Blind, Polymorph
A_PERIODIC_DAMAGE = 3
A_PERIODIC_HEAL = 8
A_MOD_DECREASE_SPEED = 33
A_MOD_DAMAGE_TAKEN_PCT = 87          # Shield Wall, Pain Suppression
A_MOD_DAMAGE_DONE_PCT = 79           # Death Wish, Avenging Wrath
A_MOD_MELEE_HASTE = 192              # what Bloodlust uses, not 138 which is the slow
A_MOD_CASTING_SPEED = 65             # Bloodlust, Icy Veins

T_SELF, T_ENEMY = 1, 6
T_DEST_AREA_ENEMY, T_AREA_ENEMY_SRC = 28, 22
T_TARGET_ALLY, T_AREA_ALLY_SRC = 21, 31

RANGE_SELF, RANGE_MELEE, RANGE_20, RANGE_30, RANGE_40 = 1, 2, 3, 4, 5
CAST_INSTANT, CAST_1500, CAST_2000, CAST_2500 = 1, 16, 5, 19
DUR_NONE, DUR_6S, DUR_8S, DUR_10S, DUR_12S, DUR_15S, DUR_20S = 0, 32, 31, 1, 29, 8, 18
RADIUS_8YD, RADIUS_10YD, RADIUS_15YD = 14, 36, 12

POWER = {"mana": 0, "rage": 1, "energy": 3}

# SpellVisual.dbc slots. Each points at a SpellVisualKit, and each kit carries
# its own sound, so a new row here is a new look AND a new sound built entirely
# from parts the client already ships.
VISUAL_SLOT = dict(precast=1, cast=2, impact=3, state=4, state_done=5, channel=6,
                   caster_impact=14, target_impact=15, instant_area=23,
                   impact_area=24, persistent_area=25)
VISUAL_FIELDS = 32


def dmg(mult):
    return ("dmg", mult)


def heal(mult):
    return ("heal", mult)


# ---- the recipes ------------------------------------------------------------
# donor: the spell whose row is copied. Choose one whose shape already matches,
#        so equipped-item requirements and interrupt flags come along correct.
# compare: the shipped spell each non-curve number was checked against. Kept in
#        the file because it is the only record of why a literal is what it is.
RECIPES = [
    dict(
        key="makeshift_strike", name="Makeshift Strike", rarity=0,
        first_level=1, ranks=7, step=12, donor=1752, school=1,
        icon=2185, visual=253, visual_kits=dict(impact=4551), power=("energy", 15),
        range_idx=RANGE_MELEE, cast_idx=CAST_INSTANT, cooldown_ms=0,
        effects=[
            dict(eff=E_WEAPON_PERCENT, base=110, tgt=T_ENEMY),
            dict(eff=E_SCHOOL_DAMAGE, base=dmg(0.35), tgt=T_ENEMY),
            dict(eff=E_ENERGIZE, base=dmg(0.6), tgt=T_SELF, misc=POWER["mana"]),
        ],
        desc=("A rough, untrained swing that deals $s1% weapon damage plus $s2 damage, "
              "and wrings $s3 mana out of the blow."),
        compare="Sinister Strike is a better strike; this one funds the spells that cost mana.",
    ),
    dict(
        key="second_nature", name="Second Nature", rarity=0,
        first_level=6, ranks=6, step=14, donor=139, school=2,
        icon=2900, visual=280, visual_kits=dict(instant_area=9159), power=("mana", 8), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=45000,
        duration_idx=DUR_12S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_PERIODIC_HEAL, base=heal(0.30),
                 tgt=T_SELF, amplitude=3000),
        ],
        desc="You steady yourself, regaining $o1 health over $d.",
        compare="A rolled instant heal is about four times this; 1.2x the heal anchor over 4 ticks.",
    ),
    dict(
        key="emberfeed", name="Emberfeed", rarity=1,
        first_level=10, ranks=6, step=12, donor=133, school=4,
        icon=183, visual=67, visual_kits=dict(caster_impact=3374), power=("mana", 14), power_is_pct=True,
        range_idx=RANGE_30, cast_idx=CAST_2000, cooldown_ms=0,
        effects=[
            dict(eff=E_SCHOOL_DAMAGE, base=dmg(1.0), tgt=T_ENEMY),
            dict(eff=E_HEAL, base=dmg(0.40), tgt=T_SELF),
        ],
        desc=("Hurls a guttering ember, burning the enemy for $s1 Fire damage and "
              "returning $s2 health to you."),
        compare="Heal is 40% of the damage, well under a real heal per point of mana.",
    ),
    dict(
        key="antipode_blast", name="Antipode Blast", rarity=2,
        first_level=26, ranks=5, step=12, donor=133, school=4,
        icon=2371, visual=12253, visual_kits=dict(impact=728, target_impact=4991), power=("mana", 16), power_is_pct=True,
        range_idx=RANGE_30, cast_idx=CAST_2000, cooldown_ms=8000,
        duration_idx=DUR_6S,
        effects=[
            dict(eff=E_SCHOOL_DAMAGE, base=dmg(0.5), tgt=T_ENEMY),
            dict(eff=E_APPLY_AURA, aura=A_PERIODIC_DAMAGE, base=dmg(0.10),
                 tgt=T_ENEMY, amplitude=2000),
            dict(eff=E_TRIGGER_SPELL, base=1, tgt=T_ENEMY, trigger="companion"),
        ],
        companion=dict(
            name="Antipode Blast", school=16, visual=67, icon=2371,
            desc="Frost half of Antipode Blast.",
            duration_idx=DUR_6S,
            effects=[
                dict(eff=E_SCHOOL_DAMAGE, base=dmg(0.5), tgt=T_ENEMY),
                dict(eff=E_APPLY_AURA, aura=A_MOD_DECREASE_SPEED, base=-30, tgt=T_ENEMY),
            ],
        ),
        desc=("Splits a bolt of opposing energies, dealing $s1 Fire and an equal amount of "
              "Frost damage. Leaves the target burning and slowed for $d."),
        compare="Chain Lightning does 191 at level 32 on 6s; the 30% slow is half Chains of Ice.",
    ),
    dict(
        key="overflow", name="Overflow", rarity=2,
        first_level=24, ranks=5, step=12, donor=2061, school=2,
        icon=1871, visual=3077, visual_kits=dict(persistent_area=9366), power=("mana", 18), power_is_pct=True,
        range_idx=RANGE_40, cast_idx=CAST_2500, cooldown_ms=0,
        effects=[
            dict(eff=E_HEAL, base=heal(1.0), tgt=T_TARGET_ALLY),
            dict(eff=E_HEAL, base=heal(0.28), tgt=T_AREA_ALLY_SRC, radius=RADIUS_8YD),
        ],
        desc=("Heals a friendly target for $s1, spilling $s2 of it to allies within "
              "$a2 yards of them."),
        compare="Prayer of Healing puts 301 on the whole party at level 30; this is dumber and smaller.",
    ),
    dict(
        key="vanguard_rush", name="Vanguard Rush", rarity=3,
        first_level=34, ranks=4, step=12, donor=100, school=1,
        icon=1886, visual=867, visual_kits=dict(instant_area=9366), power=("rage", 20),
        range_idx=RANGE_20, cast_idx=CAST_INSTANT, cooldown_ms=30000,
        effects=[
            dict(eff=E_CHARGE, base=1, tgt=T_ENEMY),
            dict(eff=E_HEAL, base=heal(0.35), tgt=T_AREA_ALLY_SRC, radius=RADIUS_10YD),
            dict(eff=E_TRIGGER_SPELL, base=1, tgt=T_ENEMY, trigger="companion"),
        ],
        companion=dict(
            name="Vanguard Rush", school=1, visual=867, icon=1886,
            desc="Impact of Vanguard Rush.",
            effects=[dict(eff=E_SCHOOL_DAMAGE, base=dmg(0.5), tgt=T_ENEMY)],
        ),
        desc=("Charge an enemy. Allies within $a2 yards of you are healed for $s2. "
              "The impact deals damage."),
        compare="Circle of Healing is 343 in 15yd on 6s at level 50; this is ~a tenth the throughput.",
    ),
    dict(
        key="hush", name="Hush", rarity=1,
        first_level=22, ranks=4, step=14, donor=1766, school=32,
        icon=2847, visual=10906, power=("energy", 20),
        range_idx=RANGE_20, cast_idx=CAST_INSTANT, cooldown_ms=15000,
        effects=[
            dict(eff=E_INTERRUPT_CAST, base=1, tgt=T_ENEMY),
        ],
        desc=("Interrupts spellcasting and prevents any spell of that school from being "
              "cast for $d."),
        compare="Kick: 10s cd / 5s lock, melee. Counterspell: 24s / 8s. This: 15s / 4s, ranged.",
        duration_idx=DUR_6S,
    ),
    dict(
        key="vertigo", name="Vertigo", rarity=2,
        first_level=38, ranks=4, step=11, donor=8122, school=32,
        icon=2875, visual=263, visual_kits=dict(target_impact=3394), power=("mana", 12), power_is_pct=True,
        range_idx=RANGE_20, cast_idx=CAST_INSTANT, cooldown_ms=30000,
        duration_idx=DUR_6S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_MOD_CONFUSE, base=0,
                 tgt=T_AREA_ENEMY_SRC, radius=RADIUS_8YD),
        ],
        desc=("The ground betrays everything near your target, disorienting enemies within "
              "$a1 yards for $d. Any damage ends the effect."),
        compare="Psychic Scream fears for 8s on 30s cd around the caster; this is 6s, at range, "
                "and breaks on damage.",
    ),
    dict(
        key="gravity_well", name="Gravity Well", rarity=3,
        first_level=46, ranks=4, step=11, donor=5740, school=32,
        icon=2242, visual=7732, visual_kits=dict(persistent_area=9352), power=("mana", 22), power_is_pct=True,
        range_idx=RANGE_30, cast_idx=CAST_INSTANT, cooldown_ms=45000,
        duration_idx=DUR_6S,
        effects=[
            dict(eff=E_PULL_TOWARDS_DEST, base=1, tgt=T_DEST_AREA_ENEMY, radius=RADIUS_8YD),
            dict(eff=E_PERSISTENT_AREA, aura=A_PERIODIC_DAMAGE_AREA, base=dmg(0.125),
                 tgt=T_DEST_AREA_ENEMY, radius=RADIUS_8YD, amplitude=1000),
            dict(eff=E_APPLY_AURA, aura=A_MOD_DECREASE_SPEED, base=-60,
                 tgt=T_DEST_AREA_ENEMY, radius=RADIUS_8YD),
        ],
        desc=("Collapses a point of space. Enemies within $a1 yards are dragged to its centre, "
              "then slowed and burned for $d."),
        compare="Frost Nova roots 8s on 25s cd for 19 damage: the game prices hard holds at ~0 "
                "damage, so this slows instead of rooting.",
    ),
    dict(
        key="bulwark_anchor", name="Bulwark Anchor", rarity=2,
        first_level=28, ranks=5, step=12, donor=5730, school=8,
        icon=334, visual=8111, visual_kits=dict(instant_area=9264), power=("mana", 16), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=60000,
        duration_idx=DUR_20S,
        summon=dict(entry=990110, name="Bulwark Anchor"),
        effects=[
            dict(eff=E_SUMMON, base=1, tgt=41, misc=990110),
        ],
        desc="Drives an anchor into the ground for $d. You and allies within 15 yards take 4% less damage.",
        compare="Blessing of Sanctuary gives 3% party-wide, permanently. This is 4% in a fixed circle for 20s.",
    ),
    dict(
        key="reclaimed_sentry", name="Reclaimed Sentry", rarity=3,
        first_level=56, ranks=3, step=8, donor=5730, school=8,
        icon=3065, visual=8111, power=("mana", 20), power_is_pct=True,
        range_idx=RANGE_30, cast_idx=CAST_INSTANT, cooldown_ms=120000,
        duration_idx=DUR_20S,
        summon=dict(entry=990111, name="Reclaimed Sentry"),
        effects=[
            dict(eff=E_SUMMON, base=1, tgt=46, misc=990111),
        ],
        desc=("Raises a stationary sentry for $d. It fires at your target and cannot move, "
              "be healed, or hold threat."),
        compare="620 total damage over its life against a 469 band anchor: ~1.3 casts spread over 20s.",
    ),
    # ---- the six that need a SpellScript ------------------------------------
    # Each script has one job and touches nothing else. None of them redirects
    # damage, moves a unit, or makes a pet cast: those are the three shapes that
    # got Tether and Ancestral Echo cut.
    dict(
        key="crossdraw", name="Crossdraw", rarity=1, script=True,
        first_level=14, ranks=6, step=12, donor=1752, school=1,
        icon=2458, visual=253, power=("energy", 20),
        range_idx=RANGE_MELEE, cast_idx=CAST_INSTANT, cooldown_ms=0,
        effects=[
            dict(eff=E_WEAPON_PERCENT, base=100, tgt=T_ENEMY),
        ],
        companion=dict(
            name="Crossdraw", school=64, visual=253, icon=2458,
            visual_kits=dict(impact=1005),
            desc="The arcane half of Crossdraw.",
            effects=[dict(eff=E_SCHOOL_DAMAGE, base=dmg(0.5), tgt=T_ENEMY)],
        ),
        desc=("Strike for $s1% weapon damage. If you cast a spell in the last 5 sec, "
              "the strike releases arcane energy as well."),
        compare="0.35x anchor base plus 0.5x when the weave lands: 0.85x total, an instant "
                "on a short cooldown's worth, which is what setting it up is worth.",
    ),
    dict(
        key="ricochet_shot", name="Ricochet Shot", rarity=2, script=True,
        first_level=18, ranks=5, step=12, donor=133, school=1,
        icon=105, visual=567, visual_kits=dict(impact=282),
        power=("energy", 25),
        range_idx=RANGE_30, cast_idx=CAST_INSTANT, cooldown_ms=10000,
        effects=[
            dict(eff=E_SCHOOL_DAMAGE, base=dmg(0.5), tgt=T_ENEMY, chain=2),
        ],
        desc=("Looses a shot for $s1 damage that ricochets to nearby enemies. Each "
              "ricochet costs mana, paid on the shot; without it, the shot bounces "
              "fewer times."),
        compare="Multi-Shot: level 18, chain 3, 10s cooldown. Same cooldown, chain caps at 3.",
    ),
    dict(
        key="bleed_over", name="Bleed Over", rarity=2, script=True,
        first_level=30, ranks=4, step=12, donor=133, school=8,
        icon=1468, visual=67, visual_kits=dict(impact=3031),
        power=("mana", 15), power_is_pct=True,
        range_idx=RANGE_30, cast_idx=CAST_INSTANT, cooldown_ms=15000,
        duration_idx=DUR_12S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_PERIODIC_DAMAGE, base=dmg(0.30),
                 tgt=T_ENEMY, amplitude=3000),
        ],
        desc=("Afflicts the target for $o1 Nature damage over $d, and extends your own "
              "periodic effects on it by 6 sec."),
        compare="Extends by a fixed 6s rather than refreshing to full: refreshing approaches "
                "never recasting a dot again, which is an exploit, not a spell.",
    ),
    dict(
        key="quickening", name="Quickening", rarity=3, script=True,
        first_level=42, ranks=4, step=10, donor=1044, school=64,
        icon=2899, visual=263, visual_kits=dict(instant_area=9159),
        power=("mana", 15), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=120000,
        duration_idx=DUR_12S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_MOD_MELEE_HASTE, base=0, tgt=T_SELF),
            dict(eff=E_APPLY_AURA, aura=A_MOD_CASTING_SPEED, base=0, tgt=T_SELF),
        ],
        desc=("Consumes all your rage and energy. For $d, your attack and casting speed "
              "increase by 1% for every 10 points consumed, up to 20%."),
        compare="Bloodlust is +30% haste for 40s. This caps at +20% for 12s on 2 minutes.",
    ),
    dict(
        key="repertoire", name="Repertoire", rarity=3, script=True,
        first_level=52, ranks=3, step=9, donor=1044, school=2,
        icon=2615, visual=246, visual_kits=dict(instant_area=1005),
        power=("mana", 10), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=180000,
        duration_idx=DUR_20S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_MOD_DAMAGE_DONE_PCT, base=0, tgt=T_SELF),
        ],
        desc=("For $d, each different ability you use increases your damage by 3%, "
              "stacking up to 5 times. Using the same ability twice does not stack."),
        compare="Avenging Wrath is +20% for 20s on 3 minutes. This tops out at +15% for the "
                "same 20s on the same cooldown, and only if you cycle five abilities.",
    ),
    dict(
        key="wildcard_surge", name="Wildcard Surge", rarity=4, script=True,
        first_level=70, ranks=2, step=8, donor=133, school=64,
        icon=1950, visual=12006, visual_kits=dict(impact_area=13152),
        power=("mana", 20), power_is_pct=True,
        range_idx=RANGE_30, cast_idx=CAST_INSTANT, cooldown_ms=180000,
        effects=[
            dict(eff=E_SCHOOL_DAMAGE, base=dmg(1.6), tgt=T_ENEMY),
        ],
        desc=("Unleashes everything you have learned, dealing $s1 damage. Damage is "
              "increased by 8% for each Epic or Legendary ability you own, up to 40%."),
        compare="1.6x the anchor for a 3 minute cooldown. Capped at +40%: uncapped, a lucky "
                "hero reached +90% and an unlucky one got nothing.",
    ),
]

# Which lines carry a SpellScript, read off the recipes so the two can never
# disagree. Their C++ lives in src/ClasslessForgedScripts.cpp, and the spell
# ids it needs are the `first` of each line below.
SCRIPTED = [r["key"] for r in RECIPES if r.get("script")]


def block_of(index):
    return SPELL_BASE + index * PER_RECIPE


def check_blocks(spells, visuals):
    """Refuse to write rows that would land on the elemental generator's ids.

    Both generators append to the same four client tables, and an id already
    present is SKIPPED by the appenders rather than overwritten -- so a
    collision does not error, it silently leaves the other generator's row in
    place and the spell comes out wearing the wrong look. Checked here against
    the elemental manifest itself, because the ranges are easy to misremember:
    an earlier draft of this file put the forged blocks inside both of them.
    """
    path = os.path.join(HERE, os.pardir, os.pardir, os.pardir,
                        "client-patch", "elemental_manifest.json")
    if not os.path.exists(path):
        return
    doc = json.load(io.open(path, encoding="utf-8"))
    taken_visual = {v["visual"]["id"] for v in doc.get("variants", [])}
    taken_sla = {v["sla"][0] for v in doc.get("variants", []) if v.get("sla")}
    taken_spell = {v["id"] for v in doc.get("variants", [])}

    clashes = []
    for v in visuals:
        if v["id"] in taken_visual:
            clashes.append("SpellVisual %d" % v["id"])
    for sp in spells:
        if sp["id"] in taken_spell:
            clashes.append("Spell %d" % sp["id"])
        if sp["sla"] and sp["sla"][0] in taken_sla:
            clashes.append("SkillLineAbility %d" % sp["sla"][0])
    if clashes:
        sys.exit("forged ids collide with the elemental generator's (%d): %s\n"
                 "Raise SLA_BASE / VISUAL_BASE / SPELL_BASE past its block."
                 % (len(clashes), ", ".join(clashes[:6])))


# ---- row building -----------------------------------------------------------
def build_row(spell, recipe, rank_index, level, spell_id, next_id, companion_id):
    """One Spell.dbc row: the donor's, with everything this recipe states."""
    donor_row = spell.row_of(recipe["donor"])
    if donor_row is None:
        sys.exit("donor %d for %s is not in Spell.dbc" % (recipe["donor"], recipe["key"]))
    donor = spell_values(spell, donor_row)
    v = list(donor)

    def setf(name, val, off=0):
        v[F[name] + off] = val

    setf("Id", spell_id)
    # A copied row carries the donor's family, which would let that class's
    # talents modify a spell no class owns. Cut it and the class mask with it.
    v[208] = 0                                  # SpellFamilyName
    for off in range(3):
        setf("EffectSpellClassMask", 0, off * 3)
        setf("EffectSpellClassMask", 0, off * 3 + 1)
        setf("EffectSpellClassMask", 0, off * 3 + 2)
    v[1] = 0                                    # Category
    v[49] = 0                                   # StackAmount

    setf("SpellLevel", level)
    setf("BaseLevel", level)
    v[37] = 0                                   # maxLevel
    v[28] = recipe["cast_idx"]
    v[46] = recipe["range_idx"]
    v[29] = recipe.get("cooldown_ms", 0)
    v[30] = recipe.get("cooldown_ms", 0)
    setf("DurationIndex", recipe.get("duration_idx", DUR_NONE))
    setf("SchoolMask", recipe["school"])
    setf("SpellVisual", recipe["visual"])
    setf("SpellIconID", recipe["icon"])

    kind, amount = recipe.get("power", ("mana", 0))
    v[41] = POWER[kind]
    if recipe.get("power_is_pct"):
        v[42] = 0
        v[227] = amount                         # ManaCostPercentage
    else:
        v[42] = amount
        v[227] = 0

    for slot in range(3):
        e = recipe["effects"][slot] if slot < len(recipe["effects"]) else None
        setf("Effect", e["eff"] if e else 0, slot)
        setf("EffectApplyAuraName", (e.get("aura", 0) if e else 0), slot)
        setf("EffectImplicitTargetA", (e.get("tgt", 0) if e else 0), slot)
        setf("EffectImplicitTargetB", 0, slot)
        setf("EffectRadiusIndex", (e.get("radius", 0) if e else 0), slot)
        setf("EffectAmplitude", (e.get("amplitude", 0) if e else 0), slot)
        setf("EffectChainTarget", (e.get("chain", 0) if e else 0), slot)
        setf("EffectMiscValue", (e.get("misc", 0) if e else 0), slot)
        setf("EffectMiscValueB", 0, slot)
        setf("EffectDieSides", 1 if e else 0, slot)
        setf("EffectRealPointsPerLevel", 0.0, slot)
        setf("EffectPointsPerComboPoint", 0.0, slot)
        setf("EffectMechanic", 0, slot)
        setf("EffectItemType", 0, slot)
        trig = 0
        base = 0
        if e:
            if e.get("trigger") == "companion":
                trig = companion_id or 0
                base = 0
            else:
                base = resolve(e["base"], level)
        setf("EffectTriggerSpell", trig, slot)
        # EffectBasePoints is stored one below the value the client shows
        setf("EffectBasePoints", int(round(base)) - 1, slot)

    for first, mask in LOCALE_BLOCKS:
        for k in range(first, mask):
            v[k] = ""
    v[F["SpellName"]] = recipe["name"]
    v[F["Rank"]] = "Rank %d" % (rank_index + 1) if recipe["ranks"] > 1 else ""
    v[F["Description"]] = recipe["desc"]
    v[F["ToolTip"]] = ""
    return v, donor


def resolve(base, level):
    if isinstance(base, tuple):
        kind, mult = base
        return anchor(kind, level) * mult
    return base


def overrides_of(values, donor):
    """Only the columns this recipe actually changed, text columns excluded.
    The client installer applies these on top of the donor's own row, so a
    community patch's edits to untouched columns survive."""
    return {i: values[i] for i in range(234)
            if i not in STRING_FIELDS and values[i] != donor[i]}


def build(spell, only=None):
    spells, lines, meta, visuals = [], [], [], []
    for index, recipe in enumerate(RECIPES):
        if only and recipe["key"] not in only:
            continue
        first = block_of(index)
        if recipe.get("visual_kits"):
            vid = VISUAL_BASE + index
            visuals.append(dict(id=vid, base=recipe["visual"],
                                kits={VISUAL_SLOT[k]: v
                                      for k, v in recipe["visual_kits"].items()}))
            recipe = dict(recipe, visual=vid)
        companion_base = first + 16
        ids = []
        for r in range(recipe["ranks"]):
            level = recipe["first_level"] + r * recipe["step"]
            if level > 80:
                break
            sid = first + r
            cid = (companion_base + r) if recipe.get("companion") else None
            row, donor = build_row(spell, recipe, r, level, sid, None, cid)
            spells.append(dict(id=sid, first=first, rank=r + 1, level=level,
                               key=recipe["key"], values=row,
                               base=recipe["donor"], fields=overrides_of(row, donor),
                               visual=recipe["visual"], icon=recipe["icon"],
                               sla=[SLA_BASE + index * PER_RECIPE + r, HERO_LINE, sid,
                                    0, ALL_CLASSES, 0, 0, 1,
                                    (first + r + 1) if r + 1 < recipe["ranks"] else 0,
                                    0, 0, 0, 0, 0]))
            ids.append(sid)
            if cid:
                comp = dict(recipe)
                comp.update(recipe["companion"])
                comp["ranks"] = 1
                crow, cdonor = build_row(spell, comp, 0, level, cid, None, None)
                # a hidden half: no skill line row, so it never shows in a tab
                spells.append(dict(id=cid, first=cid, rank=1, level=level,
                                   key=recipe["key"] + "_companion", values=crow,
                                   base=comp["donor"], fields=overrides_of(crow, cdonor),
                                   visual=comp["visual"], icon=comp["icon"], sla=None))
        lines.append(dict(key=recipe["key"], first=first, rarity=recipe["rarity"],
                          name=recipe["name"], ids=ids))
        meta.append(dict(key=recipe["key"], compare=recipe["compare"]))
    return spells, lines, meta, visuals


def generation_id(spells):
    h = hashlib.sha1()
    for s in sorted(spells, key=lambda x: x["id"]):
        h.update(json.dumps([s["id"], s["values"], s["sla"]],
                            sort_keys=True, default=str).encode("utf-8"))
    return h.hexdigest()[:12]


# ---- output -----------------------------------------------------------------
def write_sql(spells, lines, gen, path):
    L = ["-- mod-classless-wildcard: forged spells, generated by",
         "-- data/sql/generators/gen_forged_spells.py. Do not hand-edit.",
         "-- Requires a worldserver restart.",
         "",
         "CREATE TABLE IF NOT EXISTS `cw_forged_spells` (",
         "  `first_spell` INT UNSIGNED NOT NULL COMMENT 'rank 1 of the forged line',",
         "  `recipe`      VARCHAR(48) NOT NULL COMMENT 'the recipe key, for tracing',",
         "  `rarity`      TINYINT UNSIGNED NOT NULL DEFAULT 255 COMMENT '255 = derive from power',",
         "  `enabled`     TINYINT UNSIGNED NOT NULL DEFAULT 1,",
         "  PRIMARY KEY (`first_spell`)",
         ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci "
         "COMMENT='Classless forged spells';",
         "",
         "CREATE TABLE IF NOT EXISTS `cw_forged_meta` (",
         "  `key`   VARCHAR(32) NOT NULL,",
         "  `value` VARCHAR(64) NOT NULL,",
         "  PRIMARY KEY (`key`)",
         ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci "
         "COMMENT='Which generator run the forged rows came from';",
         "REPLACE INTO `cw_forged_meta` (`key`, `value`) VALUES ('generation', '%s');" % gen,
         "",
         "-- The Hero skill line. Both rows are load-bearing: without the",
         "-- skillline_dbc row GetSkillRangeType returns SKILL_RANGE_NONE, and",
         "-- without the skillraceclassinfo_dbc row _LoadSkills deletes the skill",
         "-- at every login.",
         "DELETE FROM `skillline_dbc` WHERE `ID` = %d;" % HERO_LINE,
         "INSERT INTO `skillline_dbc` (`ID`, `CategoryID`, `SkillCostsID`, `DisplayName_Lang_enUS`, "
         "`Description_Lang_enUS`, `SpellIconID`, `AlternateVerb_Lang_enUS`, `CanLink`) VALUES",
         "(%d, %d, 0, '%s', '', %d, '', 0);"
         % (HERO_LINE, SKILL_CATEGORY_CLASS, HERO_LINE_NAME, HERO_LINE_ICON),
         "",
         "DELETE FROM `skillraceclassinfo_dbc` WHERE `ID` = %d;" % RCI_ID,
         "INSERT INTO `skillraceclassinfo_dbc` (`ID`,`SkillID`,`RaceMask`,`ClassMask`,`Flags`,"
         "`MinLevel`,`SkillTierID`,`SkillCostIndex`) VALUES",
         "(%d, %d, 0, 0, %d, 0, 0, 0);" % (RCI_ID, HERO_LINE, RCI_FLAGS),
         "",
         "DELETE FROM `spell_dbc` WHERE `ID` BETWEEN %d AND %d;" % (SPELL_BASE, BLOCK_END),
         "DELETE FROM `skilllineability_dbc` WHERE `Spell` BETWEEN %d AND %d;" % (SPELL_BASE, BLOCK_END),
         "DELETE FROM `spell_ranks` WHERE `first_spell_id` BETWEEN %d AND %d;" % (SPELL_BASE, BLOCK_END),
         "DELETE FROM `cw_forged_spells` WHERE `first_spell` BETWEEN %d AND %d;" % (SPELL_BASE, BLOCK_END),
         ""]

    L.append("INSERT INTO `spell_dbc` (%s) VALUES" % ", ".join("`%s`" % c for c in SPELL_DBC_COLUMNS))
    for n, s in enumerate(spells):
        end = ";" if n == len(spells) - 1 else ","
        L.append("(%s)%s" % (", ".join(sql_literal(x) for x in s["values"]), end))
    L.append("")

    withsla = [s for s in spells if s["sla"]]
    L.append("INSERT INTO `skilllineability_dbc` (`ID`, `SkillLine`, `Spell`, `RaceMask`, "
             "`ClassMask`, `ExcludeRace`, `ExcludeClass`, `MinSkillLineRank`, `SupercededBySpell`, "
             "`AcquireMethod`, `TrivialSkillLineRankHigh`, `TrivialSkillLineRankLow`, "
             "`CharacterPoints_1`, `CharacterPoints_2`) VALUES")
    for n, s in enumerate(withsla):
        end = ";" if n == len(withsla) - 1 else ","
        L.append("(%s)%s" % (", ".join(str(x) for x in s["sla"]), end))
    L.append("")

    ranked = [s for s in spells if not s["key"].endswith("_companion")]
    L.append("INSERT INTO `spell_ranks` (`first_spell_id`, `spell_id`, `rank`) VALUES")
    for n, s in enumerate(ranked):
        end = ";" if n == len(ranked) - 1 else ","
        L.append("(%d, %d, %d)%s" % (s["first"], s["id"], s["rank"], end))
    L.append("")

    # One row per RANK, not per line: a SpellScript is bound by spell id, so a
    # line whose later ranks are missing here would silently lose its script
    # partway up the level range. The name is the C++ class name, which is what
    # RegisterSpellScript registers under.
    scripted = [s for s in spells
                if s["key"] in SCRIPTED and not s["key"].endswith("_companion")]
    if scripted:
        L.append("DELETE FROM `spell_script_names` WHERE `spell_id` BETWEEN %d AND %d;"
                 % (SPELL_BASE, BLOCK_END))
        L.append("INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`) VALUES")
        for n, sp in enumerate(scripted):
            end = ";" if n == len(scripted) - 1 else ","
            L.append("(%d, 'spell_cw_%s')%s" % (sp["id"], sp["key"], end))
        L.append("")

    L.append("INSERT INTO `cw_forged_spells` (`first_spell`, `recipe`, `rarity`, `enabled`) VALUES")
    for n, ln in enumerate(lines):
        end = ";" if n == len(lines) - 1 else ","
        L.append("(%d, '%s', %d, 1)%s" % (ln["first"], ln["key"], ln["rarity"], end))
    L.append("")

    io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")


def write_manifest(spells, lines, visuals, gen, path, run_desc):
    doc = dict(version=1, run=run_desc, generation=gen,
               spell_block=[SPELL_BASE, BLOCK_END],
               skill_line=dict(id=HERO_LINE, name=HERO_LINE_NAME,
                               category=SKILL_CATEGORY_CLASS, icon=HERO_LINE_ICON),
               lines=[dict(key=l["key"], name=l["name"], first=l["first"]) for l in lines],
               visuals=visuals,
               spells=[dict(id=s["id"], first=s["first"], rank=s["rank"], level=s["level"],
                            key=s["key"], name=s["values"][F["SpellName"]],
                            rank_text=s["values"][F["Rank"]],
                            description=s["values"][F["Description"]],
                            base=s["base"], fields={str(k): v for k, v in s["fields"].items()},
                            values=s["values"], visual=s["visual"], icon=s["icon"],
                            sla=s["sla"])
                       for s in spells])
    io.open(path, "w", encoding="utf-8", newline="\n").write(
        json.dumps(doc, indent=1, default=str))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dbc", default=DEFAULT_DBC)
    ap.add_argument("--only", default="", help="comma separated recipe keys")
    ap.add_argument("--out-sql", default=OUT_SQL)
    ap.add_argument("--out-manifest", default=OUT_MANIFEST)
    args = ap.parse_args(argv)

    path = os.path.join(args.dbc, "Spell.dbc")
    if not os.path.exists(path):
        sys.exit("missing Spell.dbc (extracted DBCs expected in %s)" % args.dbc)
    spell = Dbc(path)
    if spell.fields != 234:
        sys.exit("Spell.dbc has %d fields; this generator understands the 234-field layout"
                 % spell.fields)

    only = {k.strip() for k in args.only.split(",") if k.strip()} or None
    spells, lines, meta, visuals = build(spell, only)
    check_blocks(spells, visuals)
    gen = generation_id(spells)

    print("forged spells: %d lines, %d rows, generation %s" % (len(lines), len(spells), gen))
    for ln in lines:
        print("   %-18s first %-7d %d rank(s)" % (ln["key"], ln["first"], len(ln["ids"])))
    print("   %d recombined SpellVisual row(s)" % len(visuals))
    print("\nscripted lines (src/ClasslessForgedScripts.cpp): %s" % ", ".join(SCRIPTED))
    for ln in lines:
        if ln["key"] in SCRIPTED:
            print("   %-18s first spell %d" % (ln["key"], ln["first"]))

    run_desc = "only=%s" % (args.only or "all data-only recipes")
    write_sql(spells, lines, gen, args.out_sql)
    write_manifest(spells, lines, visuals, gen, args.out_manifest, run_desc)
    print("\nwrote %s\n      %s" % (args.out_sql, args.out_manifest))


if __name__ == "__main__":
    main()
