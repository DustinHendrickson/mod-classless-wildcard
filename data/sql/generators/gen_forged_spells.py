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
# 32 ids per line: up to 16 ranks, and a hidden companion for every rank that
# needs one. Which block a line gets comes from ID_ORDER at the bottom of this
# file, NOT from where its recipe sits in RECIPES -- see the note there.
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

# The summoned markers. They exist to be looked at: not attackable, cannot
# move, cannot be selected, give no experience and never aggro. Everything the
# spell actually does is an area effect on the spell itself.
UNIT_FLAGS_MARKER = 0x00000002 | 0x00000004 | 0x02000000   # non-attackable, no move, no select
EXTRA_FLAGS_MARKER = 0x00000002 | 0x00000040 | 0x00000080  # civilian, no xp, trigger
CREATURE_TYPE_TOTEM = 11
CREATURE_TYPE_BEAST = 1
SUMMON_GUARDIAN = 1562       # what Force of Nature uses: temporary, fights, despawns
# (entry, name, CreatureDisplayID). The display id is not optional: models
# live in creature_template_model, and a creature without a row there spawns
# invisible. All three are stock totem models.
# Every display here is a totem object NO player-pool spell can summon. The
# obvious four -- Healing Stream 4587, Earthbind 4588, Searing 4589, Sentry
# 4590 -- are all reachable by rolling the shaman totem that places them, so
# they are off limits for the same reason their icons would be.
SUMMON_CREATURES = [
    (990110, "Bulwark Anchor", 2420, None),      # Earthgrab Totem
    (990111, "Reclaimed Sentry", 11686, None),   # Dire Maul Crystal Totem
    (990112, "Cairn", 2418, None),               # Spirit Calling Totem
    (990113, "Waystone", 2419, None),            # Elemental Protection Totem
    (990114, "Signal Fire", 4683, None),         # Fire Nova Totem
    (990115, "Rally Point", 15231, None),        # Totem of Spirits
    (990116, "Drill Ground", 1421, None),        # Lava Spout Totem
]

# A pet creature per RANK, because a creature carries one spell list. The
# modifiers stack on top of the level scaling Guardian::InitStats already does.
PET_CREATURES = {
    "venom_beetle": [
        # (entry, display, how many of the recipe's pet_spells it knows, dmg, hp)
        (990117, 2730, 1, 1.0, 1.0),
        (990118, 2730, 2, 1.35, 1.35),
        (990119, 2730, 3, 1.7, 1.7),
    ],
}
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
A_MOD_TAUNT = 11                     # Taunt, Hand of Reckoning
A_MOD_INCREASE_SPEED = 31            # Sprint, Dash
A_SCHOOL_ABSORB = 69                 # Power Word: Shield, Savage Defense
A_MOD_ATTACK_POWER = 99              # Battle Shout up, Demoralizing Shout down
A_MOD_STAT = 29                      # Mark of the Wild, with misc -1 for every stat
A_MOD_COOLDOWN = 196                 # flat SECONDS added to a cooldown as it starts;
                                     # its only stock users add time, so this subtracts

E_ATTACK_ME = 114                    # the taunt half of Taunt itself

T_SELF, T_ENEMY = 1, 6
T_DEST_AREA_ENEMY, T_AREA_ENEMY_SRC = 28, 22
T_TARGET_ALLY, T_AREA_ALLY_SRC = 21, 31

RANGE_SELF, RANGE_MELEE, RANGE_20, RANGE_30, RANGE_40 = 1, 2, 3, 4, 5
CAST_INSTANT, CAST_1500, CAST_2000, CAST_2500 = 1, 16, 5, 19
DUR_NONE, DUR_4S, DUR_6S, DUR_8S, DUR_10S, DUR_12S, DUR_15S, DUR_20S, DUR_30S = \
    0, 35, 32, 31, 1, 29, 8, 18, 9
# Read out of SpellRadius.dbc, not guessed: index 36 is 0 yards and index 12 is
# 100. An area effect with a zero radius hits a point and nothing else, and
# nothing anywhere reports it.
RADIUS_5YD, RADIUS_8YD, RADIUS_10YD, RADIUS_15YD, RADIUS_20YD = 8, 14, 13, 18, 9

POWER = {"mana": 0, "rage": 1, "energy": 3}

# ManaCostPct is column 204. Column 227 sits next to PowerDisplayID and is not
# a cost at all: writing there makes a spell free and says nothing in the
# tooltip, which is exactly how it went unnoticed. Nearly every caster spell in
# WotLK prices itself this way -- Fireball is 8%, Flash Heal 18%, Chain
# Lightning 26% -- and the median across every band is 12 to 18%.
MANA_COST_PCT = 204

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
        key="makeshift_strike", name="Makeshift Strike", rarity=0, type=1,
        first_level=1, ranks=7, step=12, donor=1752, school=1,
        icon=2185, visual=253, visual_kits=dict(impact=4551), power=("energy", 40),
        range_idx=RANGE_MELEE, cast_idx=CAST_INSTANT, cooldown_ms=0,
        effects=[
            dict(eff=E_WEAPON_PERCENT, base=110, tgt=T_ENEMY),
            dict(eff=E_SCHOOL_DAMAGE, base=dmg(0.35), tgt=T_ENEMY),
            dict(eff=E_ENERGIZE, base=dmg(0.6), tgt=T_SELF, misc=POWER["mana"]),
        ],
        desc=("A graceless swing with whatever you happen to be holding, dealing $s1% "
              "weapon damage plus $s2 damage. The effort is worth $s3 mana."),
        compare="Sinister Strike is a better strike; this one funds the spells that cost mana.",
    ),
    dict(
        key="second_nature", name="Second Nature", rarity=0, type=4,
        first_level=6, ranks=6, step=14, donor=139, school=2,
        icon=2900, visual=280, visual_kits=dict(instant_area=9159), power=("mana", 10), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=45000,
        duration_idx=DUR_12S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_PERIODIC_HEAL, base=heal(0.30),
                 tgt=T_SELF, amplitude=3000),
        ],
        desc="Catch your breath and let the worst of it close. Restores $o1 health over $d.",
        compare="A rolled instant heal is about four times this; 1.2x the heal anchor over 4 ticks.",
    ),
    dict(
        key="emberfeed", name="Emberfeed", rarity=1, type=3,
        first_level=10, ranks=6, step=12, donor=133, school=4,
        icon=183, visual=67, visual_kits=dict(caster_impact=3374), power=("mana", 12), power_is_pct=True,
        range_idx=RANGE_30, cast_idx=CAST_2000, cooldown_ms=0,
        effects=[
            dict(eff=E_SCHOOL_DAMAGE, base=dmg(1.0), tgt=T_ENEMY),
            dict(eff=E_HEAL, base=dmg(0.40), tgt=T_SELF),
        ],
        desc=("Hurls a guttering ember that burns the enemy for $s1 Fire damage and "
              "feeds $s2 health back to you."),
        compare="Heal is 40% of the damage, well under a real heal per point of mana.",
    ),
    dict(
        key="antipode_blast", name="Antipode Blast", rarity=2, type=3,
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
        desc=("Splits a bolt into halves that should not hold together, dealing $s1 Fire "
              "and as much again in Frost. The target is left burning and slowed for $d."),
        compare="Chain Lightning does 191 at level 32 on 6s; the 30% slow is half Chains of Ice.",
    ),
    dict(
        key="overflow", name="Overflow", rarity=2, type=4,
        first_level=24, ranks=5, step=12, donor=2061, school=2,
        icon=1871, visual=3077, visual_kits=dict(persistent_area=9366), power=("mana", 24), power_is_pct=True,
        range_idx=RANGE_40, cast_idx=CAST_2500, cooldown_ms=0,
        effects=[
            dict(eff=E_HEAL, base=heal(1.0), tgt=T_TARGET_ALLY),
            dict(eff=E_HEAL, base=heal(0.28), tgt=T_AREA_ALLY_SRC, radius=RADIUS_8YD),
        ],
        desc=("Pours healing into a friendly target for $s1. What will not fit spills to "
              "allies within $a2 yards of them for $s2."),
        compare="Prayer of Healing puts 301 on the whole party at level 30; this is dumber and smaller.",
    ),
    dict(
        key="vanguard_rush", name="Vanguard Rush", rarity=3, type=1,
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
        desc=("Charge an enemy and strike them on arrival. Allies within $a2 yards of where "
              "you land are healed for $s2."),
        compare="Circle of Healing is 343 in 15yd on 6s at level 50; this is ~a tenth the throughput.",
    ),
    dict(
        key="hush", name="Hush", rarity=1, type=0,
        first_level=22, ranks=4, step=14, donor=1766, school=32,
        icon=2847, visual=10906, power=("energy", 25),
        range_idx=RANGE_20, cast_idx=CAST_INSTANT, cooldown_ms=15000,
        effects=[
            dict(eff=E_INTERRUPT_CAST, base=1, tgt=T_ENEMY),
        ],
        desc=("Cuts a spell off mid-word. Interrupts casting and locks that school for $d."),
        compare="Kick: 10s cd / 5s lock, melee. Counterspell: 24s / 8s. This: 15s / 4s, ranged.",
        duration_idx=DUR_4S,
    ),
    dict(
        key="vertigo", name="Vertigo", rarity=2, type=0, mechanic=2,   # disoriented
        first_level=38, ranks=4, step=11, donor=8122, school=32,
        icon=2875, visual=263, visual_kits=dict(target_impact=3394), power=("mana", 12), power_is_pct=True,
        range_idx=RANGE_20, cast_idx=CAST_INSTANT, cooldown_ms=30000,
        duration_idx=DUR_6S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_MOD_CONFUSE, base=0,
                 tgt=T_AREA_ENEMY_SRC, radius=RADIUS_8YD),
        ],
        desc=("The ground stops agreeing with them. Enemies within $a1 yards of your target "
              "are disoriented for $d. Any damage ends it."),
        compare="Psychic Scream fears for 8s on 30s cd around the caster; this is 6s, at range, "
                "and breaks on damage.",
    ),
    dict(
        key="sinkhole", name="Sinkhole", rarity=3, type=3, mechanic=11,  # snare
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
        desc=("The ground gives way. Enemies within $a1 yards are dragged to the centre "
              "and held there, slowed and burning, for $d."),
        compare="Frost Nova roots 8s on 25s cd for 19 damage: the game prices hard holds at ~0 "
                "damage, so this slows instead of rooting.",
    ),
    dict(
        key="bulwark_anchor", name="Bulwark Anchor", rarity=2, type=0,
        first_level=28, ranks=5, step=12, donor=5730, school=8,
        icon=334, visual=8111, visual_kits=dict(instant_area=9264), power=("mana", 16), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=60000,
        duration_idx=DUR_20S,
        summon=dict(entry=990110, name="Bulwark Anchor"),
        effects=[
            dict(eff=E_SUMMON, base=1, tgt=41, misc=990110),
            dict(eff=E_APPLY_AURA, aura=A_MOD_DAMAGE_TAKEN_PCT, base=-4,
                 tgt=T_AREA_ALLY_SRC, radius=RADIUS_15YD),
        ],
        desc=("Drives an anchor into the ground. You and allies within $a2 yards of it take "
              "4% less damage for $d."),
        compare="Blessing of Sanctuary gives 3% party-wide, permanently. This is 4% in a fixed circle for 20s.",
    ),
    dict(
        key="reclaimed_sentry", name="Reclaimed Sentry", rarity=3, type=0,
        first_level=56, ranks=3, step=8, donor=5730, school=8,
        icon=3065, visual=8111, power=("mana", 20), power_is_pct=True,
        range_idx=RANGE_30, cast_idx=CAST_INSTANT, cooldown_ms=120000,
        duration_idx=DUR_20S,
        summon=dict(entry=990111, name="Reclaimed Sentry"),
        effects=[
            dict(eff=E_SUMMON, base=1, tgt=46, misc=990111),
            dict(eff=E_PERSISTENT_AREA, aura=A_PERIODIC_DAMAGE_AREA, base=dmg(0.13),
                 tgt=T_DEST_AREA_ENEMY, radius=RADIUS_10YD, amplitude=2000),
        ],
        desc=("Raises a sentry out of the ground. It fires on anything hostile within $a2 "
              "yards of it for $d. It cannot move, be healed, or hold threat."),
        compare="Ten ticks over its life against a 469 band anchor: ~1.3 casts' worth, spread "
                "over 20s and only against whatever stays near it.",
    ),
    # ---- the low-level Commons -----------------------------------------------
    # A fresh Hero starts with four cards and no guarantee any of them is a
    # ranged attack, a defensive, or a way to get away. These are the floor
    # under that: cheap, unexciting, and always available.
    dict(
        key="hurl", name="Hurl", rarity=0, type=2,
        first_level=3, ranks=7, step=11, donor=133, school=1,
        icon=251, visual=567, power=("energy", 20),
        range_idx=RANGE_20, cast_idx=CAST_INSTANT, cooldown_ms=6000,
        effects=[
            dict(eff=E_SCHOOL_DAMAGE, base=dmg(0.85), tgt=T_ENEMY),
        ],
        desc=("Throws whatever is to hand at a distant enemy for $s1 damage. No weapon "
              "required, and no aim worth the name."),
        compare="0.85x anchor for an instant on a 6s cooldown. The point is having any "
                "ranged attack at all, which a rolled build often has none of.",
    ),
    dict(
        key="brace", name="Brace", rarity=0, type=0,
        first_level=5, ranks=6, step=13, donor=1044, school=1,
        icon=3397, visual=4050, visual_kits=dict(instant_area=9264),
        power=("energy", 15),
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=30000,
        duration_idx=DUR_6S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_MOD_DAMAGE_TAKEN_PCT, base=-10, tgt=T_SELF),
        ],
        desc="Set your feet and take the hit. Damage you suffer is reduced by 10% for $d.",
        compare="Shield Wall is -60% for 12s on 5 minutes. This is -10% for 6s on 30 seconds, "
                "which is about a tenth of the mitigation for a fifth of the wait.",
    ),
    dict(
        key="kick_dirt", name="Kick Dirt", rarity=0, type=0, mechanic=11,  # snare
        first_level=9, ranks=5, step=13, donor=1766, school=1,
        icon=350, visual=263, power=("energy", 20),
        range_idx=RANGE_MELEE, cast_idx=CAST_INSTANT, cooldown_ms=15000,
        duration_idx=DUR_6S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_MOD_DECREASE_SPEED, base=-50, tgt=T_ENEMY),
        ],
        desc="A faceful of grit and gravel. The target is slowed by 50% for $d.",
        compare="Chains of Ice is -95% for 10s and Crippling Poison -50% on every hit. "
                "This is -50% for 6s on a 15s cooldown: an escape, not a lockdown.",
    ),
    dict(
        key="adrenaline", name="Adrenaline", rarity=0, type=0,
        first_level=12, ranks=5, step=13, donor=1044, school=64,
        icon=1904, visual=4050, visual_kits=dict(instant_area=1005),
        power=("mana", 12), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=60000,
        effects=[
            dict(eff=E_ENERGIZE, base=dmg(1.4), tgt=T_SELF, misc=POWER["energy"]),
        ],
        desc="Burn a moment of focus for a second wind. Restores $s1 energy.",
        compare="Makeshift Strike turns energy into mana; this turns mana back into energy, "
                "so neither pool can strand a build that leans on the other.",
    ),
    dict(
        key="draw_attention", name="Draw Attention", rarity=0, type=0,
        first_level=8, ranks=1, step=1, donor=355, school=1,
        icon=1938, visual=246, visual_kits=dict(instant_area=9264),
        power=("energy", 15),
        range_idx=RANGE_20, cast_idx=CAST_INSTANT, cooldown_ms=8000,
        duration_idx=DUR_6S,
        effects=[
            dict(eff=E_ATTACK_ME, base=1, tgt=T_ENEMY),
            dict(eff=E_APPLY_AURA, aura=A_MOD_TAUNT, base=1, tgt=T_ENEMY),
        ],
        desc=("A shout, a gesture, a thrown rock. The target turns on you for $d."),
        compare="Taunt itself: level 10, 8s cooldown, no rank scaling. Copied wholesale, "
                "because a taunt either works or it does not.",
    ),
    dict(
        key="wide_arc", name="Wide Arc", rarity=0, type=1,
        first_level=11, ranks=6, step=12, donor=1680, school=1,
        icon=1952, visual=12006, visual_kits=dict(impact=4551),
        power=("energy", 35),
        range_idx=RANGE_MELEE, cast_idx=CAST_INSTANT, cooldown_ms=6000,
        effects=[
            dict(eff=E_WEAPON_PERCENT, base=55, tgt=T_AREA_ENEMY_SRC, radius=RADIUS_8YD),
        ],
        desc=("A wide, untidy swing at everything within $a1 yards, for $s1% weapon damage."),
        compare="Whirlwind is 100% weapon damage to everything on a 10s cooldown at level 36. "
                "This is 55% on 6s from level 11, which is worse per swing and available "
                "twenty-five levels earlier.",
    ),
    dict(
        key="bolt_forward", name="Bolt Forward", rarity=0, type=0,
        first_level=14, ranks=1, step=1, donor=2983, school=1,
        icon=3897, visual=4050, visual_kits=dict(instant_area=3394),
        power=("energy", 20),
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=90000,
        duration_idx=DUR_6S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_MOD_INCREASE_SPEED, base=40, tgt=T_SELF),
        ],
        desc="A short, ugly burst of speed. Movement speed increases by 40% for $d.",
        compare="Sprint is +50% for 15s on 5 minutes and Dash the same. This is +40% for 6s "
                "on 90 seconds: less of it, more often, and never a substitute for either.",
    ),
    dict(
        key="rattle", name="Rattle", rarity=0, type=0,
        first_level=16, ranks=5, step=13, donor=1160, school=1,
        icon=1739, visual=263, visual_kits=dict(target_impact=6898),
        power=("energy", 20),
        range_idx=RANGE_20, cast_idx=CAST_INSTANT, cooldown_ms=0,
        duration_idx=DUR_15S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_MOD_ATTACK_POWER, base=("dmg", -0.6),
                 tgt=T_ENEMY),
        ],
        desc="Puts the target off their stride, reducing their attack power by $s1 for $d.",
        compare="Demoralizing Shout takes 35 attack power off everything nearby at level 14. "
                "This takes less, off one target, and is the only weaken a rolled build is "
                "guaranteed to have.",
    ),
    dict(
        key="ward_off", name="Ward Off", rarity=0, type=0,
        first_level=17, ranks=5, step=13, donor=17, school=2,
        icon=65, visual=784, visual_kits=dict(instant_area=9159),
        power=("mana", 14), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=45000,
        duration_idx=DUR_10S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_SCHOOL_ABSORB, base=heal(0.50), tgt=T_SELF),
        ],
        desc="A hasty guard thrown up in front of you. Absorbs $s1 damage for $d.",
        compare="Power Word: Shield absorbs 44 at level 6 with no cooldown. This is half the "
                "heal anchor on a 45 second cooldown, so it eats one hit rather than a fight.",
    ),
    dict(
        key="borrowed_stance", name="Borrowed Stance", rarity=0, type=0,
        first_level=20, ranks=4, step=14, donor=1044, school=2,
        icon=2140, visual=246, visual_kits=dict(instant_area=1005),
        power=("mana", 10), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=60000,
        duration_idx=DUR_15S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_MOD_DAMAGE_DONE_PCT, base=5, tgt=T_SELF),
        ],
        desc=("You settle into a stance that belongs to nobody in particular. Damage done "
              "increases by 5% for $d."),
        compare="Death Wish is +20% for 30s on 3 minutes. This is +5% for 15s on 1 minute: "
                "a quarter of the size for a fifth of the wait, which is where a Common "
                "version of a signature cooldown belongs.",
    ),
    dict(
        key="cairn", name="Cairn", rarity=0, type=0,
        first_level=15, ranks=5, step=13, donor=5730, school=8,
        icon=442, visual=8111, visual_kits=dict(instant_area=9366),
        power=("mana", 12), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=45000,
        duration_idx=DUR_15S,
        summon=dict(entry=990112, name="Cairn"),
        effects=[
            dict(eff=E_SUMMON, base=1, tgt=41, misc=990112),
            dict(eff=E_APPLY_AURA, aura=A_PERIODIC_HEAL, base=heal(0.14),
                 tgt=T_AREA_ALLY_SRC, radius=RADIUS_10YD, amplitude=3000),
        ],
        desc=("Stacks a few stones into something that means safety here. You and allies "
              "within $a2 yards recover $o2 health over $d."),
        compare="Second Nature heals one person and Overflow heals in a burst; this is the "
                "only healing in the set that stays somewhere. A fifth of the heal anchor "
                "per tick, spread across whoever stands in it.",
    ),
    dict(
        key="waystone", name="Waystone", rarity=0, type=0,
        first_level=22, ranks=1, step=1, donor=5730, school=8,
        icon=2034, visual=8111, visual_kits=dict(instant_area=9366),
        power=("mana", 12), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=60000,
        duration_idx=DUR_20S,
        summon=dict(entry=990113, name="Waystone"),
        effects=[
            dict(eff=E_SUMMON, base=1, tgt=41, misc=990113),
            dict(eff=E_APPLY_AURA, aura=A_MOD_INCREASE_SPEED, base=15,
                 tgt=T_AREA_ALLY_SRC, radius=RADIUS_15YD),
        ],
        desc=("Sets a marker worth walking towards. You and allies within $a2 yards of it "
              "move 15% faster for $d."),
        compare="Sprint is +50% for 15s on 5 minutes, for one person. This is +15% for the "
                "group. It lands once when planted, because a speed buff you have to stand "
                "next to would be worth nothing.",
    ),
    dict(
        key="signal_fire", name="Signal Fire", rarity=1, type=0,
        first_level=26, ranks=4, step=13, donor=5730, school=4,
        icon=1887, visual=8111, visual_kits=dict(instant_area=728),
        power=("mana", 14), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=60000,
        duration_idx=DUR_20S,
        summon=dict(entry=990114, name="Signal Fire"),
        effects=[
            dict(eff=E_SUMMON, base=1, tgt=41, misc=990114),
            dict(eff=E_APPLY_AURA, aura=A_MOD_STAT, base=("dmg", 0.06), misc=-1,
                 tgt=T_AREA_ALLY_SRC, radius=RADIUS_15YD),
        ],
        desc=("Lights something that can be seen from a distance. You and allies within $a2 "
              "yards gain $s2 to all attributes for $d."),
        compare="Mark of the Wild is +37 to every attribute, permanently, on the whole raid. "
                "This is a fraction of that for 20 seconds, and the only stat buff a rolled "
                "build is guaranteed to have.",
    ),
    dict(
        key="rally_point", name="Rally Point", rarity=2, type=0,
        first_level=34, ranks=1, step=1, donor=5730, school=1,
        icon=433, visual=8111, visual_kits=dict(instant_area=1005),
        power=("mana", 16), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=120000,
        duration_idx=DUR_20S,
        summon=dict(entry=990115, name="Rally Point"),
        effects=[
            dict(eff=E_SUMMON, base=1, tgt=41, misc=990115),
            dict(eff=E_APPLY_AURA, aura=A_MOD_DAMAGE_DONE_PCT, base=3,
                 tgt=T_AREA_ALLY_SRC, radius=RADIUS_15YD),
        ],
        desc=("Plants a banner worth fighting under. You and allies within $a2 yards deal 3% "
              "more damage for $d."),
        compare="Borrowed Stance gives one person 5% for 15s on a minute. This gives the group "
                "3% for 20s on two, which is the usual trade: less each, more people, longer wait.",
    ),
    dict(
        key="drill_ground", name="Drill Ground", rarity=3, type=0,
        first_level=44, ranks=1, step=1, donor=5730, school=64,
        icon=2186, visual=8111, visual_kits=dict(instant_area=9159),
        power=("mana", 18), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=180000,
        duration_idx=DUR_20S,
        summon=dict(entry=990116, name="Drill Ground"),
        effects=[
            dict(eff=E_SUMMON, base=1, tgt=41, misc=990116),
            dict(eff=E_APPLY_AURA, aura=A_MOD_COOLDOWN, base=-2,
                 tgt=T_AREA_ALLY_SRC, radius=RADIUS_15YD),
        ],
        desc=("Marks out ground to work on. For $d, abilities you and allies within $a2 yards "
              "begin using come off cooldown 2 sec sooner."),
        compare="SPELL_AURA_MOD_COOLDOWN is read when a cooldown STARTS, so this shortens "
                "cooldowns begun during the window rather than speeding up ones already "
                "running. Flat seconds, so it is worth far more to a 6 second ability than "
                "a 3 minute one, and the global cooldown is the floor either way.",
    ),
    dict(
        key="venom_beetle", name="Venom Beetle", rarity=2, type=0,
        first_level=30, ranks=3, step=16, donor=5730, school=8,
        icon=1630, visual=8111, visual_kits=dict(instant_area=3031),
        power=("mana", 18), power_is_pct=True,
        range_idx=RANGE_30, cast_idx=CAST_INSTANT, cooldown_ms=120000,
        duration_idx=DUR_30S,
        summon=dict(entry=990117, name="Venom Beetle"),
        effects=[
            dict(eff=E_SUMMON, base=1, tgt=T_ENEMY,
                 misc=("rank", [990117, 990118, 990119]), miscb=SUMMON_GUARDIAN),
        ],
        # What it knows. Each lands on the pet bar with an autocast toggle, and
        # a rank adds the next one: rank 1 bites, rank 2 spits, rank 3 chokes.
        pet_spells=[
            dict(name="Venom Bite", school=8, icon=1630, visual=67,
                 visual_kits=dict(impact=3031), duration_idx=DUR_12S,
                 range_idx=RANGE_MELEE, cast_idx=CAST_INSTANT, cooldown_ms=6000,
                 power=("mana", 0),
                 desc="Poisons the target for $o1 Nature damage over $d.",
                 effects=[dict(eff=E_APPLY_AURA, aura=A_PERIODIC_DAMAGE,
                               base=("dmg", 0.20), tgt=T_ENEMY, amplitude=3000)]),
            dict(name="Weakening Spit", school=8, icon=1739, visual=67,
                 visual_kits=dict(impact=3031), duration_idx=DUR_15S,
                 range_idx=RANGE_20, cast_idx=CAST_INSTANT, cooldown_ms=15000,
                 power=("mana", 0),
                 desc="Spits acid, reducing the target's attack power by $s1 for $d.",
                 effects=[dict(eff=E_APPLY_AURA, aura=A_MOD_ATTACK_POWER,
                               base=("dmg", -0.5), tgt=T_ENEMY)]),
            dict(name="Spore Wash", school=8, icon=68, visual=7732,
                 visual_kits=dict(persistent_area=9352), duration_idx=DUR_6S,
                 range_idx=RANGE_20, cast_idx=CAST_INSTANT, cooldown_ms=30000,
                 power=("mana", 0),
                 desc="Washes the ground with spores, slowing enemies within $a1 yards for $d.",
                 effects=[dict(eff=E_APPLY_AURA, aura=A_MOD_DECREASE_SPEED, base=-40,
                               tgt=T_DEST_AREA_ENEMY, radius=RADIUS_8YD)]),
        ],
        desc=("Turns something out of the ground that resents being disturbed. It fights for "
              "you for $d, and what it knows grows with its rank."),
        compare="A guardian in Force of Nature's shape, which the core treats as a "
                "CONTROLLABLE_GUARDIAN: its melee scales with the level it is summoned at, "
                "its abilities sit on the pet bar with autocast, and DamageModifier climbs "
                "1.0, 1.35, 1.7 across the ranks on top of that.",
    ),
    # ---- the six that need a SpellScript ------------------------------------
    # Each script has one job and touches nothing else. None of them redirects
    # damage, moves a unit, or makes a pet cast: those are the three shapes that
    # got Tether and Ancestral Echo cut.
    dict(
        key="crossdraw", name="Crossdraw", rarity=1, script=True, type=1,
        first_level=14, ranks=6, step=12, donor=1752, school=1,
        icon=2458, visual=253, power=("energy", 45),
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
        desc=("Strike for $s1% weapon damage. If you have cast a spell in the last 5 sec, "
              "the blow carries its leftover charge and burns as well."),
        compare="0.35x anchor base plus 0.5x when the weave lands: 0.85x total, an instant "
                "on a short cooldown's worth, which is what setting it up is worth.",
    ),
    dict(
        key="ricochet_shot", name="Ricochet Shot", rarity=2, script=True, type=2,
        first_level=18, ranks=5, step=12, donor=133, school=1,
        icon=105, visual=567, visual_kits=dict(impact=282),
        power=("energy", 30),
        range_idx=RANGE_30, cast_idx=CAST_INSTANT, cooldown_ms=10000,
        effects=[
            dict(eff=E_SCHOOL_DAMAGE, base=dmg(0.5), tgt=T_ENEMY, chain=("rank", 2, 3)),
        ],
        desc=("Looses a shot for $s1 damage that ricochets to nearby enemies. Every "
              "ricochet is paid for in mana as the shot leaves your hand. What you "
              "cannot pay for, it does not do."),
        compare="Multi-Shot: level 18, chain 3, 10s cooldown. Same cooldown, chain caps at 3.",
    ),
    dict(
        key="bleed_over", name="Bleed Over", rarity=2, script=True, type=3,
        first_level=30, ranks=4, step=12, donor=133, school=8,
        icon=1468, visual=67, visual_kits=dict(impact=3031),
        power=("mana", 15), power_is_pct=True,
        range_idx=RANGE_30, cast_idx=CAST_INSTANT, cooldown_ms=15000,
        duration_idx=DUR_12S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_PERIODIC_DAMAGE, base=dmg(0.30),
                 tgt=T_ENEMY, amplitude=3000),
        ],
        desc=("Afflicts the target for $o1 Nature damage over $d, and gives every wound you "
              "have already opened on it another 6 sec to work."),
        compare="Extends by a fixed 6s rather than refreshing to full: refreshing approaches "
                "never recasting a dot again, which is an exploit, not a spell.",
    ),
    dict(
        key="quickening", name="Quickening", rarity=3, script=True, type=0,
        first_level=42, ranks=4, step=10, donor=1044, school=64,
        icon=2899, visual=263, visual_kits=dict(instant_area=9159),
        power=("mana", 15), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=120000,
        duration_idx=DUR_12S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_MOD_MELEE_HASTE, base=0, tgt=T_SELF),
            dict(eff=E_APPLY_AURA, aura=A_MOD_CASTING_SPEED, base=0, tgt=T_SELF),
        ],
        desc=("Spends every point of rage and energy you have. For $d, attack and casting "
              "speed increase by 1% per 10 points spent, to a maximum of 20%."),
        compare="Bloodlust is +30% haste for 40s. This caps at +20% for 12s on 2 minutes.",
    ),
    dict(
        key="repertoire", name="Repertoire", rarity=3, script=True, type=0,
        first_level=52, ranks=3, step=9, donor=1044, school=2,
        icon=2615, visual=246, visual_kits=dict(instant_area=1005),
        power=("mana", 10), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=180000,
        duration_idx=DUR_20S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_MOD_DAMAGE_DONE_PCT, base=0, tgt=T_SELF),
        ],
        desc=("For $d, every different ability you use raises your damage by 3%, to a "
              "maximum of five. Repeating an ability adds nothing."),
        compare="Avenging Wrath is +20% for 20s on 3 minutes. This tops out at +15% for the "
                "same 20s on the same cooldown, and only if you cycle five abilities.",
    ),
    dict(
        key="wildcard_surge", name="Wildcard Surge", rarity=4, script=True, type=3,
        first_level=70, ranks=2, step=8, donor=133, school=64,
        icon=1950, visual=12006, visual_kits=dict(impact_area=13152),
        power=("mana", 20), power_is_pct=True,
        range_idx=RANGE_30, cast_idx=CAST_INSTANT, cooldown_ms=180000,
        effects=[
            dict(eff=E_SCHOOL_DAMAGE, base=dmg(1.6), tgt=T_ENEMY),
        ],
        desc=("Everything you have gathered, spent at once, for $s1 damage. Increased by 8% "
              "for each Epic or Legendary ability you own, to a maximum of 40%."),
        compare="1.6x the anchor for a 3 minute cooldown. Capped at +40%: uncapped, a lucky "
                "hero reached +90% and an unlucky one got nothing.",
    ),
]

# ---- id assignment ----------------------------------------------------------
# APPEND ONLY. A line's spell ids, skill-line ids and visual id are all derived
# from its position here, so moving or inserting a key renumbers everything
# after it -- and a client that already installed the old numbers keeps them,
# because the installer skips ids it already has. The result is silent: the new
# rows simply do not apply and the spells wear the wrong data.
#
# RECIPES above is free to be in whatever order reads best. This is the order
# that must never change.
ID_ORDER = [
    "makeshift_strike", "second_nature", "emberfeed", "antipode_blast",
    "overflow", "vanguard_rush", "hush", "vertigo", "sinkhole",
    "bulwark_anchor", "reclaimed_sentry",
    "crossdraw", "ricochet_shot", "bleed_over", "quickening", "repertoire",
    "wildcard_surge",
    # added after the first install, so they take the blocks after it
    "hurl", "brace", "kick_dirt", "adrenaline",
    # the second wave of Commons, appended again rather than inserted
    "draw_attention", "wide_arc", "bolt_forward", "rattle", "ward_off",
    "borrowed_stance", "cairn",
    "waystone", "signal_fire", "rally_point", "drill_ground", "venom_beetle",
]

_recipe_keys = {r["key"] for r in RECIPES}
assert _recipe_keys <= set(ID_ORDER), \
    "recipes missing from ID_ORDER: %s" % (_recipe_keys - set(ID_ORDER))
assert len(ID_ORDER) == len(set(ID_ORDER)), "ID_ORDER has a duplicate"

# Which lines carry a SpellScript, read off the recipes so the two can never
# disagree. Their C++ lives in src/ClasslessForgedScripts.cpp, and the spell
# ids it needs are the `first` of each line below.
SCRIPTED = [r["key"] for r in RECIPES if r.get("script")]


def pinned_index(key):
    """Where this line's ids live. Fixed for the life of the line."""
    try:
        return ID_ORDER.index(key)
    except ValueError:
        sys.exit("recipe '%s' is not in ID_ORDER. Append it to the END of that list; "
                 "inserting renumbers every line after it." % key)


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

    # A donor's form requirement is the sharpest edge on this whole approach.
    # SpellInfo::CheckShapeshift refuses a caster in NO form when Stances is
    # set, so Charge's Battle Stance or Psychic Scream's Shadowform would make
    # a classless spell uncastable for almost everyone, with no error anywhere
    # except the red text on the player's screen. Both masks go.
    v[12] = 0                                   # Stances
    v[14] = 0                                   # StancesNot
    # The same argument applies to the attribute bits that gate a cast on a
    # condition of the donor's class. Charge is out-of-combat only, which would
    # have made Vanguard Rush a gap closer that cannot be used in a fight, and
    # NOT_SHAPESHIFTED would stop any Hero who rolled a form from using the set
    # at all. Cleared, not tolerated.
    v[4] &= ~(0x10000000     # NOT_IN_COMBAT_ONLY_PEACEFUL
              | 0x00010000   # NOT_SHAPESHIFTED
              | 0x00004000   # ONLY_INDOORS
              | 0x00008000   # ONLY_OUTDOORS
              | 0x00020000   # ONLY_STEALTHED
              | 0x00000040)  # PASSIVE
    v[18] = 0                                   # RequiresSpellFocus
    for i in range(8):
        v[52 + i] = 0                           # Reagent
        v[60 + i] = 0                           # ReagentCount
    v[50] = v[51] = 0                           # Totem

    setf("SpellLevel", level)
    setf("BaseLevel", level)
    v[37] = 0                                   # maxLevel
    v[28] = recipe["cast_idx"]
    v[46] = recipe["range_idx"]
    v[29] = recipe.get("cooldown_ms", 0)
    v[30] = recipe.get("cooldown_ms", 0)
    setf("DurationIndex", recipe.get("duration_idx", DUR_NONE))
    setf("SchoolMask", recipe["school"])
    v[3] = recipe.get("mechanic", 0)            # Mechanic, stated per recipe
    setf("SpellVisual", recipe["visual"])
    setf("SpellIconID", recipe["icon"])

    kind, amount = recipe.get("power", ("mana", 0))
    v[41] = POWER[kind]
    if recipe.get("power_is_pct"):
        v[42] = 0
        v[MANA_COST_PCT] = amount
    else:
        v[42] = amount
        v[MANA_COST_PCT] = 0

    for slot in range(3):
        e = recipe["effects"][slot] if slot < len(recipe["effects"]) else None
        setf("Effect", e["eff"] if e else 0, slot)
        setf("EffectApplyAuraName", (e.get("aura", 0) if e else 0), slot)
        setf("EffectImplicitTargetA", (e.get("tgt", 0) if e else 0), slot)
        setf("EffectImplicitTargetB", 0, slot)
        setf("EffectRadiusIndex", (e.get("radius", 0) if e else 0), slot)
        setf("EffectAmplitude", (e.get("amplitude", 0) if e else 0), slot)
        chain = e.get("chain", 0) if e else 0
        if isinstance(chain, tuple):
            # ("rank", first, cap): widens by one per rank, up to the cap. The
            # game's own chain spells stop at 3, so that is the ceiling.
            chain = min(chain[1] + rank_index, chain[2])
        setf("EffectChainTarget", chain, slot)
        setf("EffectMiscValue", 0, slot)
        setf("EffectMiscValueB", (e.get("miscb", 0) if e else 0), slot)
        setf("EffectDieSides", 1 if e else 0, slot)
        setf("EffectRealPointsPerLevel", 0.0, slot)
        setf("EffectPointsPerComboPoint", 0.0, slot)
        setf("EffectMechanic", 0, slot)
        setf("EffectItemType", 0, slot)
        trig = 0
        base = 0
        if e:
            misc = e.get("misc", 0)
            if isinstance(misc, tuple) and misc[0] == "rank":
                # one creature per rank: rank 2's beetle is not rank 1's
                misc = misc[1][min(rank_index, len(misc[1]) - 1)]
            setf("EffectMiscValue", misc, slot)
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
    for recipe in RECIPES:
        if only and recipe["key"] not in only:
            continue
        index = pinned_index(recipe["key"])
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
        # A pet's abilities are hidden spells of their own, one per entry in
        # pet_spells, built at the level of the rank that unlocks them so each
        # is worth something when it arrives.
        for n, petspell in enumerate(recipe.get("pet_spells", [])):
            unlock = recipe["first_level"] + n * recipe["step"]
            ps = dict(recipe)
            ps.update(petspell)
            ps["ranks"] = 1
            pid = first + 16 + n
            prow, pdonor = build_row(spell, ps, 0, min(unlock, 80), pid, None, None)
            spells.append(dict(id=pid, first=pid, rank=1, level=min(unlock, 80),
                               key=recipe["key"] + "_pet%d" % n, values=prow,
                               base=ps["donor"], fields=overrides_of(prow, pdonor),
                               visual=ps["visual"], icon=ps["icon"], sla=None))

        lines.append(dict(key=recipe["key"], first=first, rarity=recipe["rarity"],
                          type=recipe.get("type", 255), name=recipe["name"], ids=ids))
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
         "  `type`        TINYINT UNSIGNED NOT NULL DEFAULT 255 "
         "COMMENT '0 utility 1 melee 2 ranged 3 spell 4 heal 5 passive, 255 = classify from the spell',",
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

    # spell_ranks lists a LINE's ranks. A hidden half and a pet's ability are
    # neither, and a row here would make the server treat each as a line of its
    # own. `sla is None` is the same test that keeps them out of the tab.
    ranked = [s for s in spells if s["sla"] is not None]
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

    L.append("-- The markers the two summons place. A creature that only stands there")
    L.append("-- has no AI to get wrong and no combat stats to balance; the spell's own")
    L.append("-- area effect does the work.")
    creatures = [(e, n, d, None, 1.0, 1.0) for e, n, d, _p in SUMMON_CREATURES]
    for key, entries in PET_CREATURES.items():
        pname = next((r["name"] for r in RECIPES if r["key"] == key), key)
        for entry, display, nspells, dmg, hp in entries:
            creatures.append((entry, pname, display, (key, nspells), dmg, hp))

    L.append("DELETE FROM `creature_template` WHERE `entry` IN (%s);"
             % ", ".join(str(c[0]) for c in creatures))
    L.append("INSERT INTO `creature_template`")
    L.append("  (`entry`, `name`, `subname`, `minlevel`, `maxlevel`, `faction`, `npcflag`, "
             "`unit_class`,")
    L.append("   `unit_flags`, `type`, `type_flags`, `RegenHealth`, `flags_extra`, "
             "`DamageModifier`, `HealthModifier`, `ScriptName`, `VerifiedBuild`)")
    L.append("VALUES")
    for n, (entry, cname, _display, pet, dmg, hp) in enumerate(creatures):
        end = ";" if n == len(creatures) - 1 else ","
        if pet:
            # a real guardian: attackable, mobile, a beast, and it fights
            L.append("(%d, '%s', '', 1, 80, 35, 0, 1, 0, %d, 0, 1, %d, %.2f, %.2f, '', 12340)%s"
                     % (entry, cname, CREATURE_TYPE_BEAST, 0x00000040, dmg, hp, end))
        else:
            L.append("(%d, '%s', '', 1, 80, 35, 0, 1, %d, %d, 0, 1, %d, 1.00, 1.00, '', 12340)%s"
                     % (entry, cname, UNIT_FLAGS_MARKER, CREATURE_TYPE_TOTEM,
                        EXTRA_FLAGS_MARKER, end))
    L.append("")

    L.append("-- Models live in their own table. Without a row here the marker")
    L.append("-- spawns and is invisible, which is exactly what happened.")
    L.append("DELETE FROM `creature_template_model` WHERE `CreatureID` IN (%s);"
             % ", ".join(str(c[0]) for c in creatures))
    L.append("INSERT INTO `creature_template_model` "
             "(`CreatureID`, `Idx`, `CreatureDisplayID`, `DisplayScale`, `Probability`, "
             "`VerifiedBuild`) VALUES")
    for n, c in enumerate(creatures):
        end = ";" if n == len(creatures) - 1 else ","
        L.append("(%d, 0, %d, 1, 1, 12340)%s" % (c[0], c[2], end))
    L.append("")

    # A creature's own spells. Creature.cpp copies these into m_spells, which is
    # what gives a guardian something to cast beyond swinging.
    petrows = []
    for entry, _n, _d, pet, _dm, _hm in creatures:
        if not pet:
            continue
        key, nspells = pet
        for idx in range(nspells):
            sid = next((sp["id"] for sp in spells
                        if sp["key"] == "%s_pet%d" % (key, idx)), None)
            if sid:
                petrows.append((entry, idx, sid))
    if petrows:
        L.append("-- What the pet knows. Creature.cpp copies these into m_spells, and")
        L.append("-- InitCharmCreateSpells puts each one on the pet bar with an autocast")
        L.append("-- toggle. A creature holds ONE list, so each rank is its own creature.")
        L.append("DELETE FROM `creature_template_spell` WHERE `CreatureID` IN (%s);"
                 % ", ".join(sorted({str(e) for e, _i, _s in petrows})))
        L.append("INSERT INTO `creature_template_spell` (`CreatureID`, `Index`, `Spell`, "
                 "`VerifiedBuild`) VALUES")
        for n, (entry, idx, sid) in enumerate(petrows):
            end = ";" if n == len(petrows) - 1 else ","
            L.append("(%d, %d, %d, 12340)%s" % (entry, idx, sid, end))
        L.append("")

    L.append("INSERT INTO `cw_forged_spells` (`first_spell`, `recipe`, `rarity`, `type`, `enabled`) "
             "VALUES")
    for n, ln in enumerate(lines):
        end = ";" if n == len(lines) - 1 else ","
        L.append("(%d, '%s', %d, %d, 1)%s"
                 % (ln["first"], ln["key"], ln["rarity"], ln["type"], end))
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
