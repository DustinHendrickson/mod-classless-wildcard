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
import collections as _collections
import io
import json
import re
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
# NOT 0x80 CREATURE_FLAG_EXTRA_TRIGGER. Unit.cpp:16978 replaces a trigger's
# display id with GetFirstInvisibleModel() for every viewer who is not in GM
# mode, whatever creature_template_model says, which is why the markers stayed
# invisible through a model fix, a summon-properties fix and a targeting fix.
EXTRA_FLAGS_MARKER = 0x00000002 | 0x00000040               # civilian, no xp
CREATURE_TYPE_TOTEM = 11
CREATURE_TYPE_BEAST = 1
SUMMON_GUARDIAN = 1562
# SummonProperties.dbc row for a marker: category 1, type 0, slot 0, flags 0x2.
# Anti-Magic Zone's row, and the only player summon that is a plain stationary
# object placed at a destination for the spell's duration -- it reaches
# EffectSummonType's default branch, a straight Map::SummonCreature.
#
# MiscValueB was 0 on every marker, and there is no SummonProperties row 0, so
# EffectSummonType logged "Unhandled summon type 0" and returned before creating
# anything. Not the totem rows (63/81/82/83): those take shaman totem slots 1-4,
# so a marker would destroy the player's totems, and that branch also refuses
# any summon that is not itself a totem.
SUMMON_MARKER = 121       # what Force of Nature uses: temporary, fights, despawns
# (entry, name, CreatureDisplayID). The display id is not optional: models
# live in creature_template_model, and a creature without a row there spawns
# invisible. All three are stock totem models.
# Every display here is a totem object NO player-pool spell can summon. The
# obvious four -- Healing Stream 4587, Earthbind 4588, Searing 4589, Sentry
# 4590 -- are all reachable by rolling the shaman totem that places them, so
# they are off limits for the same reason their icons would be.
# Props, deliberately not totems: a shaman totem model standing next to real
# totems is confusing, and these are not totems in any mechanical sense either.
# Each display is worn by a live creature and has a creature_model_info row --
# without one Creature::UpdateEntry returns false and nothing spawns.
SUMMON_CREATURES = [
    (990110, "Bulwark Anchor", 31124, None),     # BoneGuardSpike, driven into the ground
    # The Gnomish Flame Turret, and it does turn out to shoot. A marker summon
    # records no spell id (UNIT_CREATED_BY_SPELL is set for pets only), so a
    # turret cannot know which rank made it: each rank is its own creature
    # entry instead, and each entry carries its own bolt in
    # creature_template_spell, which Creature::UpdateEntry copies into
    # m_spells. The AI fires m_spells[0] and never handles a spell id.
    (990111, "Reclaimed Sentry", 19218,
     dict(script="npc_cw_reclaimed_sentry", recipe="reclaimed_sentry", spell=0)),
    (990118, "Reclaimed Sentry", 19218,
     dict(script="npc_cw_reclaimed_sentry", recipe="reclaimed_sentry", spell=1)),
    (990119, "Reclaimed Sentry", 19218,
     dict(script="npc_cw_reclaimed_sentry", recipe="reclaimed_sentry", spell=2)),
    # Was AzsharaStoneTablet02, which is the same look as Waystone's Tablet04:
    # two files, one object on screen. The client exposes no rock pile to
    # creatures at all, so this is the Oracle crystal the core spawns at scale
    # 1 as "Crystal of Unstable Energy" -- a standing glowing outcrop, which
    # suits a thing that mends and shields whoever stands near it.
    (990112, "Cairn", 25931, None),              # O_Crystal_01, a standing crystal
    (990113, "Waystone", 30886, None),           # AzsharaStoneTablet04, a marker stone
    # 26506 is an Ulduar DOODAD at native scale 3.0; at 0.4 only its flame
    # showed and it read as an orb. This is the Midsummer bonfire.
    (990114, "Signal Fire", 22993, None),        # SummerFest_Bonfire_Large01
    (990115, "Rally Point", 27399, None),        # ArgentCrusade_Banner01, a banner
]

# A pet creature per RANK, because a creature carries one spell list. The
# modifiers stack on top of the level scaling Guardian::InitStats already does.
PET_CREATURES = {
    # (entry, display, how many of the recipe's pet_spells it knows, dmg, hp).
    # One creature: a pet learns each default spell when its level reaches the
    # spell's SpellLevel (Pet::InitLevelupSpellsForLevel), so the three
    # abilities arrive at 10, 30 and 50 without a second creature or a second
    # rank. Its stats come from the owner's level, as every pet's do.
    "venom_beetle": [
        # display 15464 is SilithidScarab.mdx at scale 1.0, worn by Spitting
        # Scarab (15462) in Ahn'Qiraj and six other live creatures. The old
        # 2730 was Creature\Scorpion\Scorpion.mdx -- a scorpion, and the
        # commonest hunter pet look there is.
        (990117, 15464, 4, 1.0, 1.0),
    ],
}
ALL_CLASSES = 0x5FF

# creature_template_model.DisplayScale, which Creature::SetDisplayId passes to
# SetObjectScale. The scarab's own model is built for a raid mob and stands
# taller than the player at 1.0.
# The display's own CreatureModelScale multiplies this, so a model built at 3.0
# needs 0.4 to stand at about head height.
# entry -> the CreatureScript that drives it, and entry -> which of the
# recipe's pet_spells it holds. Only an emplacement that acts has either.
CREATURE_SCRIPT = {e: x["script"] for e, _n, _d, x in SUMMON_CREATURES if x}
CREATURE_SPELL = {e: (x["recipe"], x["spell"])
                  for e, _n, _d, x in SUMMON_CREATURES if x}

MODEL_SCALE = {
    990110: 0.90,     # BoneGuardSpike is 0.45 natively, and 2.00 stood over the player
    # SummerFest_Bonfire_Large01 is what the core spawns at 1.00, so 1.50 was
    # half again bigger than a real Midsummer bonfire and stood over the player
    990114: 0.50,     # a fire you could light, not a festival
    990117: 0.33,     # the scarab is a raid mob at 1.00
}

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
E_SUMMON_PET = 56                    # Summon Imp: a real, permanent, saved pet
E_PERSISTENT_AREA, E_SUMMON, E_ENERGIZE = 27, 28, 30
E_ENERGIZE_PCT = 137                 # a PERCENT of a pool, misc = the pool
E_INTERRUPT_CAST, E_TRIGGER_SPELL = 68, 64
# 31 takes base points as a PERCENTAGE of weapon damage (Backstab is 127).
# 121 is normalized weapon damage plus base points as a FLAT add (Sinister
# Strike is +3). They are easy to swap by accident and the mistake is silent:
# 110 on 121 is +110 damage at level 1, not 110% of a weapon.
E_WEAPON_PERCENT, E_NORMALIZED_WEAPON_DMG, E_CHARGE = 31, 121, 96
E_PULL_TOWARDS_DEST = 145            # the core comments this "Black Hole Effect"
E_APPLY_AURA = 6

A_PERIODIC_DAMAGE_AREA = 3           # what Consecration's persistent area applies. 4 is
                                     # SPELL_AURA_DUMMY, and two spells shipped dealing nothing
A_DUMMY = 4                          # a marker with no effect of its own
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
A_MOD_POWER_REGEN = 85               # mana per five seconds
A_OBS_MOD_HEALTH = 20                # a PERCENT of maximum health per tick (Blood Craze)
A_MOD_WEAPON_CRIT = 52               # crit with weapons
A_MOD_SPELL_CRIT = 57                # crit with spells
A_PERIODIC_LEECH = 53                # damage over time that heals the caster
A_PERIODIC_ENERGIZE = 21             # power per tick, gated like E_ENERGIZE
A_MOD_HEALING_TAKEN_PCT = 118        # healing RECEIVED, negative to cut it
A_MOD_STAT = 29                      # Mark of the Wild, with misc -1 for every stat
A_MOD_RESISTANCE_PCT = 101           # Faerie Fire and Expose Armor; misc 1 is armour
A_DAMAGE_SHIELD = 15                 # Thorns, Retribution Aura
A_MOD_POWER_COST_PCT = 72            # misc is a school mask; negative is cheaper
A_MOD_INCREASE_HEALTH_PCT = 133      # Last Stand
A_MOD_ATTACK_SPEED_PCT = 138         # Thunder Clap: negative slows melee swings
A_HASTE_SPELLS = 216                 # Curse of Tongues, Slow: negative slows casting
A_MOD_COOLDOWN = 196                 # flat SECONDS added to a cooldown as it starts;
                                     # its only stock users add time, so this subtracts

E_ATTACK_ME = 114                    # the taunt half of Taunt itself

# Implicit targets, by the table in SpellInfo.cpp. Two kinds matter here: a
# UNIT target chooses who the effect lands on; a SRC or DEST target only sets a
# position, and an effect given one of those on its own lands on nobody. Four
# effects shipped that way (22 alone on a confuse and a weapon swing, 28 alone
# on a pull and two slows). Shapes below are copied from named stock spells.
T_SELF, T_ENEMY, T_TARGET_ALLY = 1, 6, 21
T_SRC_CASTER = 22                    # sets the source; goes in TargetA...
T_AREA_ENEMY_SRC = 15                # ...with this in TargetB: enemies around the
                                     # caster. Frost Nova, Thunder Clap, Psychic
                                     # Scream, Divine Storm: 141 player effects,
                                     # and none writes 15 alone
T_AREA_ENEMY_DEST = 16               # enemies around the destination, alone
                                     # (Shadowfury, Inferno: 27)
T_DEST_TARGET_ANY = 63               # the destination is the target's feet...
T_AREA_ALLY_DEST = 31                # ...with this in TargetB: allies around
                                     # them (Circle of Healing, Wild Growth)
T_AREA_ALLY_SRC = 30                 # with 22 in TargetA: allies around the
                                     # CASTER (Divine Hymn). Target 31 on its
                                     # own, which five markers used, is a shape
                                     # no player spell in the game uses.
T_DEST_DYNOBJ_ENEMY = 28             # where a persistent area sits (Death and Decay)
T_DEST_CAST = 87                     # where the player clicked (Lightwell)
T_DEST_TOTEM_SLOT = 41               # a totem slot beside the caster (Earthbind Totem)
T_DEST_CASTER_SUMMON = 32            # where a pet appears (Summon Imp)
T_CONE_ENEMY = 104                   # a cone in front of the caster. The only cone
                                     # the player pool uses: Cone of Cold and
                                     # Dragon's Breath, both with radius index 13
ALL_SCHOOLS = 0x7F                   # MAX_SPELL_SCHOOL is 7

RANGE_SELF, RANGE_MELEE, RANGE_20, RANGE_30, RANGE_40 = 1, 2, 3, 4, 5
RANGE_RANGED = 114                   # "Hunter Range", 0 to 35 yards: every shot uses it
CAST_INSTANT, CAST_1500, CAST_2000, CAST_2500, CAST_3000 = 1, 16, 5, 19, 14
DUR_NONE, DUR_4S, DUR_6S, DUR_8S, DUR_10S, DUR_12S, DUR_15S, DUR_20S, DUR_30S = \
    0, 35, 32, 31, 1, 29, 8, 18, 9
DUR_PERMANENT = 21                   # -1: Summon Imp's
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
# SpellFamilyNames 2, 14 and 16 are unused by every class in WotLK. Claiming
# 14 for the forged set is what lets a Hero talent modify these spells the way
# Blizzard's own talents modify their class's: SpellInfo::IsAffected matches
# the modifier's family against this one, then the modifier's
# EffectSpellClassMask against this spell's SpellClassMask. Family 0 would have
# meant "affects everything" for any modifier, and a class family would have
# handed these spells to that class's talents -- which is why they were 0.
HERO_FAMILY = 14
# Columns 209-211 are this spell's own class flags, 96 bits across three.
# Every line takes the bit of its pinned index, and a line's companion and pet
# spells take the same one, so a talent that names a line reaches all of it.
SPELL_CLASS_MASK = 209

# ---- the Hero talent tab ------------------------------------------------
# TalentTab 990, the same number the Hero skill line uses. ClassMask 2048 is
# bit 11: ClasslessAddon::SendTalentTabs reports a tab's class as its first set
# bit, and the addon has always known CLASS_HERO = 12 and drawn a Hero button
# for it. Neither the stock tabs nor the stock talents are touched -- a
# `_dbc` world table adds and overrides by id, it does not replace the file.
HERO_TALENT_TAB = 990
HERO_TAB_CLASSMASK = 1 << 11          # bit 11 -> classId 12, the addon's Hero page
HERO_TAB_ICON = 3411                  # Ability_Hunter_FocusedAim, the Hero line's own
TALENT_ID_BASE = 9000                 # stock Talent.dbc ends at 2285
TALENT_SPELL_BASE = 961600            # blocks 50+, past the 33 lines and inside BLOCK_END
TALENT_SPELL_STRIDE = 8               # five ranks and room to spare

# SpellModOp, from SpellDefines.h. A talent effect's EffectMiscValue is the op
# it modifies and its EffectSpellClassMask says which lines it reaches.
MOD_DAMAGE, MOD_DURATION, MOD_RANGE, MOD_RADIUS = 0, 1, 5, 6
MOD_CRIT, MOD_ALL_EFFECTS, MOD_CASTING_TIME, MOD_COOLDOWN = 7, 8, 10, 11
MOD_EFFECT2, MOD_COST, MOD_JUMP_TARGETS = 12, 14, 17
A_DUMMY = 4                           # read by C++ through GetDummyAuraEffect
A_ADD_FLAT_MODIFIER = 107
A_ADD_PCT_MODIFIER = 108
# Spell Impact: passive, one APPLY_AURA of ADD_PCT_MODIFIER, no cost, no
# duration. Everything else in the row is overwritten.
TALENT_DONOR = 11242

MANA_COST_PCT = 204
# AttributesEx7 is column 11, and bit 16 is the core's "Can restore secondary
# power". See build_row: without it a power-restoring effect is a no-op on any
# player whose displayed bar is not the pool being filled.
ATTR7_RESTORE_SECONDARY_POWER = 0x00010000
# Spell.dbc column 47: a missile's speed in yards per second. Zero means the
# effect lands the instant the cast finishes, with nothing drawn between caster
# and target -- which is what every projectile in this file did until it was
# written. Found by scanning the client's own rows for a column where Fireball
# and Frostbolt hold a plausible speed and Whirlwind holds zero.
SPEED = 47
# The speeds the game itself uses, so a forged projectile travels at the same
# rate as the spell a player would compare it to.
SPEED_ARROW = 40.0        # Arcane Shot, Auto Shot
SPEED_BOLT = 24.0         # Fireball
SPEED_THROWN = 20.0       # Throw
SPEED_HEAVY_THROW = 50.0  # Heroic Throw
SPEED_SPIT = 25.0         # between a thrown weapon and an arrow
SPEED_FIREBOLT = 19.0     # the Imp's Firebolt, missile model 188

# The shape of cw_forged_spells, in one place, because write_sql builds both the
# CREATE and the migration that brings an older table up to it: CREATE TABLE IF
# NOT EXISTS silently does nothing to a table that already exists, which is how
# a realm ended up with no `type` column and an INSERT that named one. A new
# column goes here and nowhere else.
FORGED_COLUMNS = [
    ("first_spell", "INT UNSIGNED NOT NULL", "rank 1 of the forged line"),
    ("recipe", "VARCHAR(48) NOT NULL", "the recipe key, for tracing"),
    ("rarity", "TINYINT UNSIGNED NOT NULL DEFAULT 255", "255 = derive from power"),
    ("type", "TINYINT UNSIGNED NOT NULL DEFAULT 255",
     "0 utility 1 melee 2 ranged 3 spell 4 heal 5 passive, 255 = classify from the spell"),
    ("enabled", "TINYINT UNSIGNED NOT NULL DEFAULT 1", ""),
]

META_COLUMNS = [
    ("key", "VARCHAR(32) NOT NULL", ""),
    ("value", "VARCHAR(64) NOT NULL", ""),
]

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
        script=True,
        first_level=1, ranks=7, step=12, donor=1752, school=1,
        icon=2185, visual=253, visual_kits=dict(impact=4551), power=("energy", 40),
        range_idx=RANGE_MELEE, cast_idx=CAST_INSTANT, cooldown_ms=0,
        # The mana arrives through a companion aimed at the ENEMY rather than an
        # ENERGIZE aimed at the caster. A spell's impact kit plays at every unit
        # it touches, so a self-targeted effect put the strike's own impact on
        # the player as well as on what they hit.
        effects=[
            dict(eff=E_WEAPON_PERCENT, base=110, tgt=T_ENEMY),
            dict(eff=E_SCHOOL_DAMAGE, base=dmg(0.35), tgt=T_ENEMY),
            dict(eff=E_TRIGGER_SPELL, base=1, tgt=T_ENEMY, trigger="companion"),
        ],
        companion=dict(
            name="Makeshift Strike", school=1, visual=0, icon=2185, donor=1752,
            range_idx=RANGE_MELEE, cast_idx=CAST_INSTANT, cooldown_ms=0,
            power=("energy", 0), desc="Mana and rage returned by Makeshift Strike.",
            # Rage is a flat hundred-point pool at every level, so it takes a
            # literal per rank the way an energy restore does rather than a
            # level curve. Stored times ten: 50 here is 5 rage.
            effects=[dict(eff=E_ENERGIZE, base=dmg(0.12), tgt=T_SELF,
                          misc=POWER["mana"]),
                     dict(eff=E_ENERGIZE, base=("ranks", [20, 20, 30, 30, 40, 40, 50]),
                          tgt=T_SELF, misc=POWER["rage"])],
        ),
        desc=("Strikes the target for $s1% weapon damage plus $s2 additional damage, and "
              "restores ${companion}s1 mana and $/10;{companion}s2 rage to you."),
        compare="Sinister Strike is a better strike; this one funds the spells that cost mana.",
    ),
    dict(
        key="second_nature", name="Second Nature", rarity=0, type=0,
        script="spell_cw_reserve_break",
        first_level=6, ranks=6, step=14, donor=29166, school=8,
        # Innervate's: a precast, a cast and an impact kit, no missile, and it
        # is the game's own picture of reserves coming back. The icon is
        # Spell_Nature_UnyeildingStamina, a body finding its own second wind,
        # in place of a holy heal sparkle on a spell that no longer heals.
        icon=312, visual=3884,
        # Free. A refill priced in the pool it refills cannot be cast when it
        # is wanted, which is what 10% of a mana bar bought here; Innervate,
        # Arcane Torrent, Bloodrage and Thistle Tea are all free for the same
        # reason.
        power=("mana", 0),
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=90000,
        # SPELL_EFFECT_ENERGIZE_PCT, with MiscValue naming the pool: a percent
        # of maximum, so one number is worth the same at 6 as at 76 and the
        # spell needs no level curve at all. Three effect slots, three pools,
        # and a Hero holds all three at once. AttributesEx7 bit 16 -- set in
        # build_row off these effects -- is what lets the two that are not the
        # displayed bar arrive; without it two thirds of this is a no-op.
        effects=[
            dict(eff=E_ENERGIZE_PCT, base=("ranks", [4, 5, 6, 7, 8, 10]),
                 tgt=T_SELF, misc=POWER["mana"]),
            dict(eff=E_ENERGIZE_PCT, base=("ranks", [8, 11, 14, 17, 20, 25]),
                 tgt=T_SELF, misc=POWER["rage"]),
            dict(eff=E_ENERGIZE_PCT, base=("ranks", [8, 11, 14, 17, 20, 25]),
                 tgt=T_SELF, misc=POWER["energy"]),
        ],
        desc="Restores $s1% of your maximum mana and $s2% of your maximum rage and energy.",
        compare="No button in the game fills more than one pool, because no class has "
                "more than one bar to fill: Innervate and Evocation are mana, Bloodrage is "
                "rage, Thistle Tea is energy. A Hero carries all three, so the classless "
                "refill is the one that answers whichever bar ran dry. Rank 6 is 10% of a "
                "mana bar on 90 seconds, 6.7% a minute against Divine Plea's 25% and Arcane "
                "Torrent's 3%, and 25 rage a cast against Bloodrage's 30 a minute. It was a "
                "self-heal with a mana return, which is Overflow's job and Emberfeed's.",
    ),
    dict(
        key="emberfeed", name="Emberfeed", rarity=1, type=3,
        script=True,
        first_level=10, ranks=6, step=12, donor=133, school=4,
        icon=183, visual=67, visual_kits=dict(caster_impact=2730), power=("mana", 12), power_is_pct=True,
        speed=SPEED_BOLT,   # a fire bolt, at Fireball's speed
        range_idx=RANGE_30, cast_idx=CAST_2000, cooldown_ms=0,
        effects=[
            dict(eff=E_SCHOOL_DAMAGE, base=dmg(1.0), tgt=T_ENEMY),
            dict(eff=E_HEAL, base=dmg(0.40), tgt=T_SELF),
        ],
        desc="Deals $s1 Fire damage to the target and heals you for $s2.",
        compare="Heal is 40% of the damage, well under a real heal per point of mana.",
    ),
    dict(
        key="antipode_blast", name="Antipode Blast", rarity=2, type=3,
        first_level=26, ranks=5, step=12, donor=133, school=4,
        icon=2371, visual=12253, visual_kits=dict(impact=728, target_impact=4991), power=("mana", 16), power_is_pct=True,
        speed=SPEED_BOLT,   # a fire bolt, at Fireball's speed
        range_idx=RANGE_30, cast_idx=CAST_2000, cooldown_ms=8000,
        duration_idx=DUR_6S,
        effects=[
            dict(eff=E_SCHOOL_DAMAGE, base=dmg(0.5), tgt=T_ENEMY),
            dict(eff=E_APPLY_AURA, aura=A_PERIODIC_DAMAGE, base=dmg(0.10),
                 tgt=T_ENEMY, amplitude=2000),
            dict(eff=E_TRIGGER_SPELL, base=1, tgt=T_ENEMY, trigger="companion"),
        ],
        companion=dict(
            # Frostbolt's: this half IS the frost damage.
            name="Antipode Blast", school=16, speed=SPEED_BOLT,
            visual=13, icon=2371,
            desc="Frost half of Antipode Blast.",
            duration_idx=DUR_6S,
            effects=[
                dict(eff=E_SCHOOL_DAMAGE, base=dmg(0.5), tgt=T_ENEMY),
                dict(eff=E_APPLY_AURA, aura=A_MOD_DECREASE_SPEED, base=-30, tgt=T_ENEMY),
            ],
        ),
        desc=("Deals $s1 Fire damage and ${companion}s1 Frost damage to the target. The target "
              "burns for an additional $o2 Fire damage over $d and moves 30% slower for $d."),
        compare="Chain Lightning does 191 at level 32 on 6s; the 30% slow is half Chains of Ice.",
    ),
    dict(
        key="overflow", name="Overflow", rarity=2, type=4,
        script=True,
        first_level=24, ranks=5, step=12, donor=2061, school=2,
        icon=1871,
        # Circle of Healing's, whose own effect shape is (HEAL, TargetA 63,
        # TargetB 31) -- this spell's spill effect exactly. Its cast kit (165)
        # is what single-target buffs use, so nothing paints on the caster.
        # Holy Nova's row was wrong for this and twice over: not the area kit,
        # which 3643 never set, but cast kit 3154, which is used by Holy Nova,
        # Cleanse Nova, Sunseeker Blessing, Fungal Creep and Spirit Heal and
        # by nothing that is not an area centred on the caster. A cast kit
        # plays on the caster; that was the burst.
        visual=8253,
        # The ring is kit 7990, NOT 3153. Read the SpellVisualKit rows and it is
        # plain: 3153 is Chest:129 Holy_ImpactDD_Low_Chest.mdx, a sparkle on the
        # chest, while the expanding ring is Base:1722 holynova_impact_base.mdx,
        # which Holy Nova carries in its CAST kit 3154 -- at the caster's base,
        # which is exactly where it kept appearing. 7990 is that same ring with
        # its sound and no animation at all, so in the impact slot it draws at
        # the base of every unit the spell reaches: the target and each ally the
        # spill heals.
        visual_kits=dict(impact=7990),
        power=("mana", 24), power_is_pct=True,
        range_idx=RANGE_40, cast_idx=CAST_2500, cooldown_ms=0,
        effects=[
            dict(eff=E_HEAL, base=heal(1.0), tgt=T_TARGET_ALLY),
            dict(eff=E_HEAL, base=heal(0.28), tgt=T_DEST_TARGET_ANY, tgtb=T_AREA_ALLY_DEST,
                 radius=RADIUS_8YD),
        ],
        desc=("Heals a friendly target for $s1, and other allies within $a2 yards of them for "
              "$s2."),
        compare="Prayer of Healing puts 301 on the whole party at level 30; this is dumber and smaller.",
    ),
    dict(
        key="vanguard_rush", name="Vanguard Rush", rarity=3, type=1,
        first_level=34, ranks=4, step=12, donor=100, school=1,
        icon=1886, visual=867, visual_kits=dict(instant_area=9366), power=("energy", 40),
        range_idx=RANGE_20, cast_idx=CAST_INSTANT, cooldown_ms=30000,
        effects=[
            dict(eff=E_CHARGE, base=1, tgt=T_ENEMY),
            dict(eff=E_HEAL, base=heal(0.35), tgt=T_DEST_TARGET_ANY, tgtb=T_AREA_ALLY_DEST,
                 radius=RADIUS_10YD),
            dict(eff=E_TRIGGER_SPELL, base=1, tgt=T_ENEMY, trigger="companion"),
        ],
        companion=dict(
            # Shockwave's: Charge's own look has no impact kit at all, so the
            # strike that lands and heals had nothing to show for itself.
            name="Vanguard Rush", school=1, visual=10703, icon=1886,
            desc="Impact of Vanguard Rush.",
            effects=[dict(eff=E_SCHOOL_DAMAGE, base=dmg(0.5), tgt=T_ENEMY)],
        ),
        desc=("Charges an enemy and strikes it on arrival for ${companion}s1 damage. Allies "
              "within $a2 yards of where you land are healed for $s2."),
        compare="Circle of Healing is 343 in 15yd on 6s at level 50; this is ~a tenth the throughput.",
    ),
    dict(
        key="hush", name="Hush", rarity=1, type=0,
        first_level=22, ranks=4, step=14, donor=1766, school=32,
        icon=2847, visual=10906, power=("energy", 25),
        range_idx=RANGE_20, cast_idx=CAST_INSTANT, cooldown_ms=15000,
        effects=[
            dict(eff=E_INTERRUPT_CAST, base=1, tgt=T_ENEMY),
            dict(eff=E_APPLY_AURA, aura=A_HASTE_SPELLS, base=-25, tgt=T_ENEMY),
        ],
        desc=("Interrupts the target's spellcasting and prevents any spell in that school from "
              "being cast for $d. The target also casts 25% slower for $d."),
        compare="Kick: 10s cd / 5s lock, melee. Counterspell: 24s / 8s. This: 15s / 4s, "
                "ranged, plus half a Curse of Tongues for the same 4s so it is not Kick "
                "with a longer reach.",
        duration_idx=DUR_4S,
    ),
    dict(
        key="vertigo", name="Vertigo", rarity=2, type=0, mechanic=2,   # disoriented
        script="spell_cw_area_control",
        first_level=38, ranks=4, step=11, donor=8122, school=32,
        icon=2875, visual=346, visual_kits=dict(target_impact=3394), power=("mana", 12), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=30000,
        duration_idx=DUR_6S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_MOD_CONFUSE, base=0,
                 tgt=T_CONE_ENEMY, radius=RADIUS_10YD),
            dict(eff=E_APPLY_AURA, aura=A_MOD_DECREASE_SPEED, base=-30,
                 tgt=T_CONE_ENEMY, radius=RADIUS_10YD),
        ],
        desc=("Disorients enemies within $a1 yards of you for $d. Any damage taken will break "
              "the effect."),
        compare="Dragon's Breath's shape exactly: target 104 in a 10 yard cone, a confuse "
                "and a slow, which is the only cone shape the player pool uses (Cone of "
                "Cold is the other). Directional, so it can be walked out of.",
    ),
    dict(
        key="sinkhole", name="Sinkhole", rarity=3, type=3, mechanic=11,  # snare
        script="spell_cw_area_control",
        first_level=46, ranks=4, step=11, donor=5740, school=32,
        # 9352 draws NOTHING: every attachment column on that kit is zero and
        # all it carries is a sound and a screen shake, so the sinkhole itself
        # was invisible. 9523 is Death and Decay's ground area
        # (DeathAndDecay_Area_Base.mdx plus its world effect) -- a dark churning
        # patch, which is the right school and the right shape for this.
        icon=2242, visual=7732, visual_kits=dict(persistent_area=9523),
        power=("mana", 22), power_is_pct=True,
        range_idx=RANGE_30, cast_idx=CAST_1500, cooldown_ms=45000,
        duration_idx=DUR_6S,
        effects=[
            dict(eff=E_PULL_TOWARDS_DEST, base=1, tgt=T_AREA_ENEMY_DEST, radius=RADIUS_8YD),
            dict(eff=E_PERSISTENT_AREA, aura=A_PERIODIC_DAMAGE_AREA, base=dmg(0.125),
                 tgt=T_DEST_DYNOBJ_ENEMY, radius=RADIUS_8YD, amplitude=1000),
            dict(eff=E_APPLY_AURA, aura=A_MOD_DECREASE_SPEED, base=-60,
                 tgt=T_AREA_ENEMY_DEST, radius=RADIUS_8YD),
        ],
        desc=("Opens a sinkhole at the target location, pulling enemies within $a1 yards to its "
              "center and slowing them by 60% for $d. Enemies inside take $o2 Shadow damage "
              "over its duration."),
        compare="Frost Nova roots 8s on 25s cd for 19 damage: the game prices hard holds at ~0 "
                "damage, so this slows instead of rooting.",
    ),
    dict(
        key="bulwark_anchor", name="Bulwark Anchor", rarity=2, type=0,
        first_level=28, ranks=5, step=12, donor=5730, school=8,
        icon=3506, visual=5787, visual_kits=dict(instant_area=9264), power=("mana", 16), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=60000,
        duration_idx=DUR_20S,
        summon=dict(entry=990110, name="Bulwark Anchor"),
        effects=[
            dict(eff=E_SUMMON, base=1, tgt=T_DEST_TOTEM_SLOT, misc=990110, miscb=SUMMON_MARKER),
            dict(eff=E_APPLY_AURA, aura=A_MOD_DAMAGE_TAKEN_PCT, base=-4,
                 tgt=T_SRC_CASTER, tgtb=T_AREA_ALLY_SRC, radius=RADIUS_15YD),
            dict(eff=E_APPLY_AURA, aura=A_MOD_ATTACK_SPEED_PCT, base=-15,
                 tgt=T_SRC_CASTER, tgtb=T_AREA_ENEMY_SRC, radius=RADIUS_15YD),
        ],
        desc=("Drives an anchor into the ground beside you for $d. You and allies within $a2 "
              "yards take 4% less damage, and enemies within $a3 yards attack 15% slower."),
        compare="Blessing of Sanctuary gives 3% party-wide, permanently. This is 4% in a fixed circle for 20s.",
    ),
    dict(
        key="reclaimed_sentry", name="Reclaimed Sentry", rarity=3, type=0,
        first_level=56, ranks=3, step=8, donor=5730, school=4,
        icon=2629, visual=13077,
        # Feral Spirit's row has no precast at all, so the cast bar ran with the
        # player standing still; 60 is what Fire Shield, Immolate and Rocket
        # Blast wind up with. The ground field is gone -- the turret shoots now,
        # so there is nothing left to draw on the floor.
        visual_kits=dict(precast=60),
        power=("mana", 20), power_is_pct=True,
        range_idx=RANGE_30, cast_idx=CAST_1500, cooldown_ms=120000,
        duration_idx=DUR_20S,
        summon=dict(entry=990111, name="Reclaimed Sentry"),
        # One creature per rank, so each turret carries its own bolt. The old
        # single entry could not tell rank 1 from rank 3.
        effects=[
            dict(eff=E_SUMMON, base=1, tgt=T_DEST_CAST,
                 misc=("rank", [990111, 990118, 990119]), miscb=SUMMON_MARKER),
        ],
        # What each rank's turret fires, one per rank, built at that rank's
        # level. npc_cw_reclaimed_sentry casts m_spells[0] once a second at
        # whatever is inside twenty yards, with the owner as original caster.
        pet_spells=[
            dict(name="Sentry Bolt", level=56, donor=5730, school=4, icon=2629,
                 visual=28, speed=SPEED_FIREBOLT, duration_idx=DUR_10S,
                 range_idx=RANGE_20, cast_idx=CAST_INSTANT, cooldown_ms=0,
                 power=("mana", 0),
                 desc="Deals $s1 Fire damage and reduces armor by 10% for $d.",
                 effects=[
                     dict(eff=E_SCHOOL_DAMAGE, base=("dmg", 0.08), tgt=T_ENEMY),
                     dict(eff=E_APPLY_AURA, aura=A_MOD_RESISTANCE_PCT, base=-10,
                          misc=1, tgt=T_ENEMY),
                 ]),
            dict(name="Sentry Bolt", level=64, donor=5730, school=4, icon=2629,
                 visual=28, speed=SPEED_FIREBOLT, duration_idx=DUR_10S,
                 range_idx=RANGE_20, cast_idx=CAST_INSTANT, cooldown_ms=0,
                 power=("mana", 0),
                 desc="Deals $s1 Fire damage and reduces armor by 10% for $d.",
                 effects=[
                     dict(eff=E_SCHOOL_DAMAGE, base=("dmg", 0.08), tgt=T_ENEMY),
                     dict(eff=E_APPLY_AURA, aura=A_MOD_RESISTANCE_PCT, base=-10,
                          misc=1, tgt=T_ENEMY),
                 ]),
            dict(name="Sentry Bolt", level=72, donor=5730, school=4, icon=2629,
                 visual=28, speed=SPEED_FIREBOLT, duration_idx=DUR_10S,
                 range_idx=RANGE_20, cast_idx=CAST_INSTANT, cooldown_ms=0,
                 power=("mana", 0),
                 desc="Deals $s1 Fire damage and reduces armor by 10% for $d.",
                 effects=[
                     dict(eff=E_SCHOOL_DAMAGE, base=("dmg", 0.08), tgt=T_ENEMY),
                     dict(eff=E_APPLY_AURA, aura=A_MOD_RESISTANCE_PCT, base=-10,
                          misc=1, tgt=T_ENEMY),
                 ]),
        ],
        desc=("Deploys a salvaged flame turret at the target location for $d. It fires on "
              "enemies within 20 yards about once a second, and its bolts reduce armor by "
              "10% for 10 sec. It cannot move or be healed."),
        compare="Twenty bolts over its life at 0.08x the band anchor each is about 1.6 casts' "
                "worth, spread across whatever stays inside twenty yards, on a two minute "
                "cooldown. The armour strip sits between Faerie Fire's 5% and Expose Armor's "
                "20% and is the only one in the set. Nothing else a Hero can roll puts a "
                "thing on the ground that picks its own targets.",
    ),
    # ---- the low-level Commons -----------------------------------------------
    # A fresh Hero starts with four cards and no guarantee any of them is a
    # ranged attack, a defensive, or a way to get away. These are the floor
    # under that: cheap, unexciting, and always available.
    dict(
        key="hurl", name="Hurl", rarity=0, type=2,
        first_level=3, ranks=7, step=11, donor=133, school=1,
        icon=251,
        # Heroic Throw's look: precast 171 then cast 172 is a real wind-up and
        # throw, and its missile model is -1, which is not a missing model. The
        # client reads -1 as "the weapon the caster is holding", so what flies
        # is the player's own axe or mace. That is the point of the spell and it
        # stays.
        visual=13222, power=("energy", 25),
        # Not Heroic Throw's 50, which is among the fastest missiles in the game
        # and crossed twenty yards in four tenths of a second. Twenty is what
        # the game's own Throw uses, and Throw is exactly this: a weapon leaving
        # your hand. One second over the same range, slower than Fireball's 24
        # covers thirty.
        speed=SPEED_THROWN,
        range_idx=RANGE_20, cast_idx=CAST_INSTANT, cooldown_ms=6000,
        effects=[
            dict(eff=E_SCHOOL_DAMAGE, base=dmg(0.85), tgt=T_ENEMY),
            dict(eff=E_TRIGGER_SPELL, base=1, tgt=T_ENEMY, trigger="companion"),
        ],
        # The rage arrives through a companion aimed at the ENEMY, not an
        # ENERGIZE aimed at the caster: an impact kit plays at every unit a
        # spell touches, and Heroic Throw's look has one (12327), so a
        # self-targeted effect would have landed the thrown object on the
        # player too. The companion carries no visual and no speed at all.
        companion=dict(
            name="Hurl", school=1, visual=0, icon=251, donor=133, speed=0.0,
            range_idx=RANGE_20, cast_idx=CAST_INSTANT, cooldown_ms=0,
            power=("energy", 0), desc="Rage generated by Hurl.",
            effects=[dict(eff=E_ENERGIZE, base=("ranks", [20, 30, 30, 40, 40, 50, 50]),
                          tgt=T_SELF, misc=POWER["rage"])],
        ),
        # The missile is the weapon in your hand, so the text says so rather
        # than "a heavy object".
        desc=("Hurls your weapon at the target, dealing $s1 damage and generating "
              "$/10;{companion}s1 rage."),
        compare="0.85x anchor for an instant on a 6s cooldown. The point is having any "
                "ranged attack at all, which a rolled build often has none of.",
    ),
    dict(
        key="brace", name="Brace", rarity=0, type=0,
        first_level=5, ranks=6, step=13, donor=1044, school=1,
        icon=3397, visual=345, visual_kits=dict(instant_area=9264),
        power=("energy", 15),
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=30000,
        duration_idx=DUR_6S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_MOD_DAMAGE_TAKEN_PCT, base=-15, tgt=T_SELF),
            # a PERCENT of maximum health per tick, which is Blood Craze's aura,
            # so a level 5 ability is still worth pressing at 80
            dict(eff=E_APPLY_AURA, aura=A_OBS_MOD_HEALTH, base=2, tgt=T_SELF,
                 amplitude=2000),
        ],
        desc=("Reduces all damage you take by 15% and restores $s2% of your maximum health "
              "every 2 sec for $d."),
        compare="Shield Wall is -60% for 12s on 5 minutes and returns nothing. Damage taken "
                "with a flat heal on it is Health Funnel and with dodge is Aspect of the "
                "Monkey; with a percentage of maximum health, nothing. Percent-based, so it "
                "does not become the level 5 button nobody presses at 40.",
    ),
    dict(
        key="kick_dirt", name="Pocket Sand", rarity=0, type=0, mechanic=11,  # snare
        script="spell_cw_area_control",
        first_level=9, ranks=5, step=13, donor=2094, school=1,
        # Sand Blast's look: a cast kit and an impact kit, no missile, and the
        # impact plays on every unit a cone reaches. Blind's had a cast kit and
        # nothing else, so the enemies never showed being hit.
        icon=350, visual=7431, power=("energy", 30),
        # Cone of Cold's shape exactly: range index 1, target 104, radius index
        # 13. A handful of grit thrown at face height does not pick one enemy.
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=30000,
        duration_idx=DUR_4S,
        # Blind's two auras, a slow AND a confuse, now across the cone. Four
        # seconds rather than ten and thirty seconds rather than three minutes,
        # and any damage ends the blind, so it stays a peel and not a mez.
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_MOD_DECREASE_SPEED, base=-50,
                 tgt=T_CONE_ENEMY, radius=RADIUS_10YD),
            dict(eff=E_APPLY_AURA, aura=A_MOD_CONFUSE, base=0,
                 tgt=T_CONE_ENEMY, radius=RADIUS_10YD),
        ],
        desc=("Throws a handful of grit in front of you, blinding enemies in a $a1 yard cone "
              "and slowing them by 50% for $d. Any damage ends the blind."),
        compare="Psychic Scream is 8s of fear on 30 seconds at level 14; this is 4s of blind "
                "and a slow on the same cooldown, in a cone rather than all around, and it "
                "breaks the moment anything lands on them.",
    ),
    dict(
        key="adrenaline", name="Adrenaline", rarity=0, type=0,
        script="spell_cw_reserve_break",
        first_level=12, ranks=5, step=13, donor=1044, school=64,
        icon=1997, visual=1588, visual_kits=dict(instant_area=1005),
        power=("mana", 12), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=120000,
        # Rage is stored times ten, so 250 is 25 rage, and it is flat across the
        # ranks the way the energy is not: rage caps at a hundred points at
        # every level, so there is no curve to climb. AttributesEx7 bit 16 is
        # set from these effects in build_row -- without it neither pool
        # arrives for a Hero whose displayed bar is the other one.
        effects=[
            dict(eff=E_ENERGIZE, base=("ranks", [20, 25, 30, 35, 40]), tgt=T_SELF, misc=POWER["energy"]),
            dict(eff=E_ENERGIZE, base=250, tgt=T_SELF, misc=POWER["rage"]),
        ],
        # $/10;s2 is Blizzard's own form for a rage amount held in effect 2:
        # Mighty Rage and Shield Specialization both write it that way.
        desc="Instantly restores $s1 energy and $/10;s2 rage.",
        compare="Makeshift Strike turns energy into mana; this turns mana back into energy "
                "and rage, so no pool can strand a build that leans on another. Bloodrage is "
                "30 rage a minute for health; this is 25 rage and up to 40 energy every two "
                "minutes for mana.",
    ),
    dict(
        key="draw_attention", name="Draw Attention", rarity=0, type=0,
        first_level=8, ranks=1, step=1, donor=355, school=1,
        # Taunt's own impact plays on the taunted enemy; the caster-centred
        # area kit would have flashed it on the caster instead.
        icon=1938, visual=34,
        power=("energy", 15),
        range_idx=RANGE_20, cast_idx=CAST_INSTANT, cooldown_ms=8000,
        duration_idx=DUR_6S,
        effects=[
            dict(eff=E_ATTACK_ME, base=1, tgt=T_ENEMY),
            dict(eff=E_APPLY_AURA, aura=A_MOD_TAUNT, base=1, tgt=T_ENEMY),
        ],
        desc="Taunts the target to attack you for $d.",
        compare="Taunt itself: level 10, 8s cooldown, no rank scaling. Copied wholesale, "
                "because a taunt either works or it does not.",
    ),
    dict(
        key="wide_arc", name="Wide Arc", rarity=0, type=1,
        first_level=11, ranks=6, step=12, donor=1680, school=1,
        icon=1952, visual=12006, visual_kits=dict(impact=4551),
        power=("energy", 45),
        # RANGE_SELF is what Whirlwind and Divine Storm use for this exact target
        # shape (22 + 15): a point-blank swing has no target to be in range of,
        # and index 2 was applying a 5 yard check against a unit never selected.
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=6000,
        effects=[
            dict(eff=E_WEAPON_PERCENT, base=55, tgt=T_SRC_CASTER, tgtb=T_AREA_ENEMY_SRC,
                 radius=RADIUS_8YD),
        ],
        desc="Strikes all enemies within $a1 yards for $s1% weapon damage.",
        compare="Whirlwind is 100% weapon damage to everything on a 10s cooldown at level 36. "
                "This is 55% on 6s from level 11, which is worse per swing and available "
                "twenty-five levels earlier.",
    ),
    dict(
        key="bolt_forward", name="Bolt Forward", rarity=0, type=0,
        first_level=14, ranks=1, step=1, donor=2983, school=1,
        icon=3897, visual=6, visual_kits=dict(instant_area=3394),
        power=("energy", 20),
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=90000,
        duration_idx=DUR_10S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_MOD_INCREASE_SPEED, base=40, tgt=T_SELF),
            dict(eff=E_APPLY_AURA, aura=A_MOD_POWER_REGEN, base=30, misc=0, tgt=T_SELF),
        ],
        desc=("Increases your movement speed by $s1% and restores $s2 mana every 5 sec "
              "for $d."),
        compare="Sprint is +50% for 15s on 5 minutes and gives nothing back. This is +40% "
                "for 10s on 90 seconds with mana behind it, and no spell in the game pairs "
                "run speed with mana regeneration: the run is for whoever closes the gap, "
                "the mana for whoever stands still and casts.",
    ),
    dict(
        key="rattle", name="Rattle", rarity=0, type=0,
        first_level=16, ranks=5, step=13, donor=1160, school=1,
        icon=1739, visual=210, visual_kits=dict(target_impact=6898),
        power=("energy", 20),
        # Fifteen seconds, which is its own duration: a debuff with no cooldown
        # at all could be held on every enemy in a pull at once.
        range_idx=RANGE_20, cast_idx=CAST_INSTANT, cooldown_ms=15000,
        duration_idx=DUR_15S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_MOD_ATTACK_POWER, base=("dmg", -0.6),
                 tgt=T_ENEMY),
        ],
        desc="Reduces the target's attack power by $s1 for $d.",
        compare="Demoralizing Shout takes 35 attack power off everything nearby at level 14. "
                "This takes less, off one target, and is the only weaken a rolled build is "
                "guaranteed to have.",
    ),
    dict(
        key="ward_off", name="Ward Off", rarity=0, type=0,
        script=True,
        first_level=17, ranks=5, step=13, donor=17, school=2,
        icon=65, visual=784, visual_kits=dict(instant_area=9159),
        power=("mana", 14), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=45000,
        duration_idx=DUR_10S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_SCHOOL_ABSORB, base=heal(0.50), tgt=T_SELF),
        ],
        desc="Absorbs $s1 damage for $d.",
        compare="Power Word: Shield absorbs 44 at level 6 with no cooldown. This is half the "
                "heal anchor on a 45 second cooldown, so it eats one hit rather than a fight.",
    ),
    dict(
        key="borrowed_stance", name="Borrowed Stance", rarity=0, type=0,
        first_level=20, ranks=4, step=14, donor=1044, school=2,
        icon=2140, visual=236, visual_kits=dict(instant_area=1005),
        power=("mana", 10), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=60000,
        duration_idx=DUR_15S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_MOD_DAMAGE_DONE_PCT, base=4, tgt=T_SELF),
            dict(eff=E_APPLY_AURA, aura=A_MOD_WEAPON_CRIT, base=5, tgt=T_SELF),
            dict(eff=E_APPLY_AURA, aura=A_MOD_SPELL_CRIT, base=5, tgt=T_SELF),
        ],
        desc=("Increases all damage you deal by $s1% and your critical strike chance with "
              "both weapons and spells by $s2% for $d."),
        compare="A stance belongs to one way of fighting; this one does not. Weapon crit "
                "with spell crit is Demonic Tactics, a passive talent rather than a button, "
                "and no spell puts damage done alongside them. It pays a Hero the same "
                "whatever they rolled, which is the point of the line.",
    ),
    dict(
        key="cairn", name="Cairn", rarity=0, type=0,
        first_level=15, ranks=5, step=13, donor=5730, school=8,
        icon=442, visual=58, visual_kits=dict(instant_area=9366),
        power=("mana", 12), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=45000,
        duration_idx=DUR_15S,
        summon=dict(entry=990112, name="Cairn"),
        effects=[
            dict(eff=E_SUMMON, base=1, tgt=T_DEST_TOTEM_SLOT, misc=990112, miscb=SUMMON_MARKER),
            dict(eff=E_APPLY_AURA, aura=A_PERIODIC_HEAL, base=heal(0.14),
                 tgt=T_SRC_CASTER, tgtb=T_AREA_ALLY_SRC, radius=RADIUS_10YD, amplitude=3000),
            dict(eff=E_APPLY_AURA, aura=A_DAMAGE_SHIELD, base=dmg(0.10),
                 tgt=T_SRC_CASTER, tgtb=T_AREA_ALLY_SRC, radius=RADIUS_10YD),
        ],
        desc=("Places a cairn beside you for $d. You and allies within $a2 yards recover $o2 "
              "health over its duration, and anything that strikes you in melee takes $s3 "
              "Nature damage."),
        compare="Healing Stream Totem heals; Thorns hurts what hits you; no spell does "
                "both. The heal is a fifth of the heal anchor per tick, the shield a tenth "
                "of the damage anchor per hit, which is Thorns' own size at the level.",
    ),
    dict(
        key="waystone", name="Waystone", rarity=0, type=0,
        first_level=22, ranks=1, step=1, donor=5730, school=8,
        icon=2034, visual=3405, visual_kits=dict(instant_area=9366),
        power=("mana", 12), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=60000,
        duration_idx=DUR_20S,
        summon=dict(entry=990113, name="Waystone"),
        effects=[
            dict(eff=E_SUMMON, base=1, tgt=T_DEST_TOTEM_SLOT, misc=990113, miscb=SUMMON_MARKER),
            dict(eff=E_APPLY_AURA, aura=A_MOD_INCREASE_SPEED, base=15,
                 tgt=T_SRC_CASTER, tgtb=T_AREA_ALLY_SRC, radius=RADIUS_15YD),
            dict(eff=E_APPLY_AURA, aura=A_MOD_DECREASE_SPEED, base=-15,
                 tgt=T_SRC_CASTER, tgtb=T_AREA_ENEMY_SRC, radius=RADIUS_15YD),
        ],
        desc=("Places a waystone beside you for $d. You and allies within $a2 yards move 15% "
              "faster, and enemies within $a3 yards move 15% slower."),
        compare="Sprint speeds one person; Earthbind Totem slows enemies; no spell does "
                "both sides. +15% and -15% for 20s, once when planted. Earthbind is -50%.",
    ),
    dict(
        key="signal_fire", name="Signal Fire", rarity=1, type=0,
        first_level=26, ranks=4, step=13, donor=5730, school=4,
        icon=1887, visual=10383, visual_kits=dict(instant_area=728),
        power=("mana", 14), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=60000,
        duration_idx=DUR_20S,
        summon=dict(entry=990114, name="Signal Fire"),
        effects=[
            dict(eff=E_SUMMON, base=1, tgt=T_DEST_TOTEM_SLOT, misc=990114, miscb=SUMMON_MARKER),
            dict(eff=E_APPLY_AURA, aura=A_MOD_STAT, base=("dmg", 0.06), misc=-1,
                 tgt=T_SRC_CASTER, tgtb=T_AREA_ALLY_SRC, radius=RADIUS_15YD),
            dict(eff=E_APPLY_AURA, aura=A_MOD_DAMAGE_TAKEN_PCT, base=4,
                 tgt=T_SRC_CASTER, tgtb=T_AREA_ENEMY_SRC, radius=RADIUS_15YD),
        ],
        desc=("Lights a signal fire beside you for $d. You and allies within $a2 yards gain $s2 "
              "to all attributes, and enemies within $a3 yards take 4% more damage."),
        compare="Mark of the Wild buffs stats; Curse of the Elements is +13% damage taken in "
                "two schools; no spell does both. A fraction of Mark for 20s, and +4% to "
                "all damage for the same 20s.",
    ),
    dict(
        key="rally_point", name="Rally Point", rarity=2, type=0,
        first_level=34, ranks=1, step=1, donor=5730, school=1,
        icon=433, visual=209, visual_kits=dict(instant_area=1005),
        power=("mana", 16), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=120000,
        duration_idx=DUR_20S,
        summon=dict(entry=990115, name="Rally Point"),
        effects=[
            dict(eff=E_SUMMON, base=1, tgt=T_DEST_TOTEM_SLOT, misc=990115, miscb=SUMMON_MARKER),
            dict(eff=E_APPLY_AURA, aura=A_MOD_DAMAGE_DONE_PCT, base=3,
                 tgt=T_SRC_CASTER, tgtb=T_AREA_ALLY_SRC, radius=RADIUS_15YD),
            dict(eff=E_APPLY_AURA, aura=A_MOD_INCREASE_HEALTH_PCT, base=5,
                 tgt=T_SRC_CASTER, tgtb=T_AREA_ALLY_SRC, radius=RADIUS_15YD),
        ],
        desc=("Plants a banner beside you for $d. You and allies within $a2 yards deal 3% more "
              "damage and have 5% more health."),
        compare="Borrowed Stance gives one person 5% for 15s on a minute. This gives the group "
                "3% for 20s on two, which is the usual trade: less each, more people, longer wait.",
    ),
    dict(
        # Was Drill Ground, a marker you stood in. A drill ground is not a
        # thing, and the set already had seven markers. The mechanic survives
        # because no player spell pairs cooldown rate with power cost; the
        # delivery is now a buff you cast on somebody, which the set had none of.
        key="quicksilver", name="Quicksilver", rarity=3, type=0,
        first_level=44, ranks=1, step=1, donor=1044, school=64,
        # Amplify Magic's, which is a mage buff cast on ANOTHER player: the same
        # school, the same shape, and a complete row -- precast 266, cast 267,
        # impact 991. Presence of Mind was wrong twice: it is a SELF buff, so
        # its impact kit is 0 and the ally being buffed saw nothing at all, and
        # its precast is 0 as well so the caster stood still through the cast.
        # No kit override; the row already has all three.
        icon=2186, visual=969,
        power=("mana", 18), power_is_pct=True,
        range_idx=RANGE_30, cast_idx=CAST_1500, cooldown_ms=180000,
        duration_idx=DUR_15S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_MOD_COOLDOWN, base=-2, tgt=T_TARGET_ALLY),
            dict(eff=E_APPLY_AURA, aura=A_MOD_POWER_COST_PCT, base=-10,
                 misc=ALL_SCHOOLS, tgt=T_TARGET_ALLY),
        ],
        desc=("Quickens a friendly target for $d. Their abilities come off cooldown 2 sec "
              "sooner and cost 10% less."),
        compare="Nothing in the player pool puts cooldown rate and power cost on one "
                "button, and the two together are worth an Epic at 44 on a three minute "
                "cooldown. Cast on somebody else, which no other spell in the set is.",
    ),
    dict(
        key="venom_beetle", name="Venom Beetle", rarity=0, type=0,
        first_level=10, ranks=1, step=1, donor=688, school=8,
        icon=1630, visual=4043, visual_kits=dict(instant_area=3031),
        power=("mana", 25), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_3000, cooldown_ms=0,
        duration_idx=DUR_PERMANENT,
        summon=dict(entry=990117, name="Venom Beetle"),
        effects=[
            # SUMMON_PET: Player::SummonPet, saved to character_pet, back at
            # login, dismissable, and it levels with its owner
            dict(eff=E_SUMMON_PET, base=1, tgt=T_DEST_CASTER_SUMMON, misc=990117),
        ],
        # What it knows. Each keeps the marker row as donor: Summon Imp's carries
        # SPELL_ATTR1_NO_AUTOCAST_AI, which would grey them out on the bar. A
        # pet learns a default spell when its level reaches the spell's own, so
        # one beetle bites at 10, spits at 30 and chokes at 50.
        pet_spells=[
            dict(name="Venom Bite", level=10, donor=5730, school=8, icon=1630, visual=5100,
                 duration_idx=DUR_12S,
                 # the cooldown matches the duration: at 6 seconds the pet
                 # recast it over itself and half its casts did nothing
                 range_idx=RANGE_MELEE, cast_idx=CAST_INSTANT, cooldown_ms=12000,
                 power=("mana", 0),
                 desc="Poisons the target, dealing $o1 Nature damage over $d.",
                 effects=[dict(eff=E_APPLY_AURA, aura=A_PERIODIC_DAMAGE,
                               base=("dmg", 0.20), tgt=T_ENEMY, amplitude=3000)]),
            # a real poison projectile (Poison Spit, missile model 675) with a
            # speed, so the spit is visible crossing the twenty yards
            dict(name="Weakening Spit", level=30, donor=5730, school=8, icon=1739,
                 visual=7910, speed=SPEED_SPIT, duration_idx=DUR_15S,
                 range_idx=RANGE_20, cast_idx=CAST_INSTANT, cooldown_ms=15000,
                 power=("mana", 0),
                 desc="Reduces the target's attack power by $s1 for $d.",
                 effects=[dict(eff=E_APPLY_AURA, aura=A_MOD_ATTACK_POWER,
                               base=("dmg", -0.5), tgt=T_ENEMY)]),
            # Venom Web Spray's projectile (missile model 618) for a slow
            dict(name="Spore Wash", level=50, donor=5730, school=8, icon=68,
                 visual=12013, speed=SPEED_SPIT, duration_idx=DUR_6S,
                 range_idx=RANGE_20, cast_idx=CAST_INSTANT, cooldown_ms=30000,
                 power=("mana", 0),
                 desc="Reduces the target's movement speed by 40% for $d.",
                 # Froststorm Breath's shape: a pet slow is a single-target
                 # aura, which is what PetAI knows how to autocast
                 effects=[dict(eff=E_APPLY_AURA, aura=A_MOD_DECREASE_SPEED, base=-40,
                               tgt=T_ENEMY)]),
            # Talent only: Medicinal Venom teaches it, and nothing else can.
            # SpellLevel 255 is above every pet level there is, so
            # Pet::InitLevelupSpellsForLevel unlearns rather than learns it --
            # which the PetScript refuses for a Hero who owns the talent. The
            # creature_template_spell row is still written, so the id sits in
            # m_spells[3] where the script reads it without knowing a number,
            # and the three spells the beetle learns for itself keep slots 0-2.
            #
            # Its numbers are built at 50 -- the talent opens at 30 and is
            # carried to 80, so the middle is where it is least wrong -- and
            # only the row's SpellLevel is 255. Half a heal anchor on a twenty
            # second cooldown: a top-up between fights, not a healer.
            #
            # Venom Spit's visual for the missile (model 675, the green gob the
            # beetle already spits) with Rejuvenation's impact kit instead of
            # the poison splash, so the same slime lands as medicine.
            dict(name="Healing Spit", level=50, spell_level=255,
                 donor=5730, school=8, icon=197,
                 visual=809, visual_kits=dict(impact=56), speed=SPEED_SPIT,
                 range_idx=RANGE_30, cast_idx=CAST_INSTANT, cooldown_ms=20000,
                 power=("mana", 0), script="spell_cw_healing_spit",
                 desc="Spits a healing salve at a wounded ally, healing them for $s1.",
                 effects=[dict(eff=E_HEAL, base=("heal", 0.5), tgt=T_TARGET_ALLY)]),
        ],
        desc=("Summons a Venom Beetle to fight at your side. It knows Venom Bite, and learns "
              "Weakening Spit at level 30 and Spore Wash at level 50."),
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
        # Ambush and Backstab's stab, with an arcane flash where it lands.
        # This was Inner Fire's row (211) for one release, and Inner Fire is a
        # self-buff: its PRECAST kit raises the caster's hands and holds them
        # there, so a melee strike played a spellcast animation and never
        # swung. It was the only weapon-damage spell in the set with a precast
        # kit at all. (Sinister Strike's own 253 is Makeshift Strike's donor.)
        icon=2458, visual=155, visual_kits=dict(impact=1005), power=("energy", 45),
        range_idx=RANGE_MELEE, cast_idx=CAST_INSTANT, cooldown_ms=0,
        effects=[
            dict(eff=E_WEAPON_PERCENT, base=100, tgt=T_ENEMY),
        ],
        companion=dict(
            # Arcane Explosion's: this half IS the arcane damage.
            name="Crossdraw", school=64, visual=965, icon=2458,
            visual_kits=dict(impact=1005),
            desc="The arcane half of Crossdraw.",
            effects=[dict(eff=E_SCHOOL_DAMAGE, base=dmg(0.5), tgt=T_ENEMY)],
        ),
        desc=("Strikes the target for $s1% weapon damage. If you have cast a damaging spell in "
              "the last 5 sec, the strike also deals ${companion}s1 Arcane damage."),
        compare="0.35x anchor base plus 0.5x when the weave lands: 0.85x total, an instant "
                "on a short cooldown's worth, which is what setting it up is worth.",
    ),
    dict(
        key="ricochet_shot", name="Ricochet Shot", rarity=2, script=True, type=2,
        first_level=18, ranks=5, step=12, donor=2643, school=1,
        icon=105, visual=3299, visual_kits=dict(impact=282),
        power=("energy", 30),
        speed=SPEED_ARROW,   # a shot, at Arcane Shot's speed
        range_idx=RANGE_RANGED, cast_idx=CAST_INSTANT, cooldown_ms=10000,
        duration_idx=DUR_6S,
        # Each ricochet is this hidden spell, cast BY the target it leaves at
        # the next enemy with the player as original caster: the missile is
        # drawn between the two, the damage and threat are the player's.
        # Slot 2 carries the budget that remains; slot 3 the same marker.
        companion=dict(
            name="Ricochet Shot", school=1, visual=3299, icon=105, donor=2643,
            speed=SPEED_ARROW,
            range_idx=RANGE_40, cast_idx=CAST_INSTANT, cooldown_ms=0, power=("mana", 0),
            duration_idx=DUR_6S, desc="Ricochet of Ricochet Shot.",
            effects=[
                dict(eff=E_SCHOOL_DAMAGE, base=dmg(0.4), tgt=T_ENEMY),
                dict(eff=E_DUMMY, base=0, tgt=T_ENEMY),
                dict(eff=E_APPLY_AURA, aura=A_DUMMY, base=0, tgt=T_ENEMY),
            ],
        ),
        companion_script=True,
        effects=[
            dict(eff=E_SCHOOL_DAMAGE, base=dmg(0.5), tgt=T_ENEMY),
            # the marker: its value is the rank's ricochet budget, which the
            # script reads and the tooltip shows as $s2
            dict(eff=E_APPLY_AURA, aura=A_DUMMY, base=("ranks", [1, 2, 3, 3, 4]), tgt=T_ENEMY),
        ],
        desc=("Fires a shot at the target for $s1 damage, then ricochets up to $s2 more "
              "times to enemies within 8 yards of the last one hit. Each ricochet deals "
              "80% of that damage and costs 6% of your maximum mana; it stops when you "
              "cannot pay."),
        compare="Multi-Shot: level 18, chain 3, 10s cooldown. Same cooldown, chain caps at 3.",
    ),
    dict(
        key="bleed_over", name="Bleed Over", rarity=2, type=3,
        first_level=30, ranks=4, step=13, donor=172, school=8,
        # Corruption's row: instant, ranged, no weapon and no combo points.
        # The LOOK is Rip's (a bleed with a real cast kit) and that is a
        # separate column -- taking Rip as the donor as well is what made
        # this a finishing move.
        icon=1468, visual=3941,
        power=("mana", 15), power_is_pct=True,
        range_idx=RANGE_30, cast_idx=CAST_INSTANT, cooldown_ms=15000,
        duration_idx=DUR_12S,
        # It used to extend your OTHER damage-over-time effects, which is worth
        # nothing to a Hero who rolled none. This takes from the target and
        # gives to you, and shuts their healing down while it runs.
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_PERIODIC_LEECH, base=dmg(0.28),
                 tgt=T_ENEMY, amplitude=3000),
            dict(eff=E_APPLY_AURA, aura=A_MOD_HEALING_TAKEN_PCT, base=-25,
                 tgt=T_ENEMY),
        ],
        desc=("Opens a wound for $o1 Nature damage over $d, healing you for the damage "
              "done, and reduces healing the target receives by 25%."),
        compare="Every leech in the player pool is a channel except Devouring Plague, and "
                "none of them touches healing received; Mortal Strike and Wound Poison cut "
                "healing and take nothing back. The two together are on no button in the "
                "game. Four ticks at a bit over a quarter of the damage anchor each, which "
                "is under a rolled instant nuke for the same mana, and the healing cut is "
                "half Mortal Strike's.",
    ),
    dict(
        key="quickening", name="Quickening", rarity=3, script=True, type=0,
        first_level=42, ranks=4, step=10, donor=1044, school=64,
        icon=2899, visual=7870, visual_kits=dict(instant_area=9159),
        # Three pools on purpose: mana to cast it, then every point of rage and
        # energy consumed to size the buff. The description says so and a Hero
        # holds all three, so this is a real cost and not a stray column.
        power=("mana", 15), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=120000,
        duration_idx=DUR_12S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_MOD_MELEE_HASTE, base=0, tgt=T_SELF),
            dict(eff=E_APPLY_AURA, aura=A_MOD_CASTING_SPEED, base=0, tgt=T_SELF),
        ],
        desc=("Consumes all of your rage and energy, increasing your attack speed and casting "
              "speed by 1% for every 5 points consumed, up to 20%, for $d. Requires at least 20 "
              "rage or energy."),
        compare="Bloodlust is +30% haste for 40s. This caps at +20% for 12s on 2 minutes.",
    ),
    dict(
        key="repertoire", name="Repertoire", rarity=3, script=True, type=0,
        first_level=52, ranks=3, step=9, donor=1044, school=2,
        icon=2615, visual=7553, visual_kits=dict(instant_area=1005),
        power=("mana", 10), power_is_pct=True,
        range_idx=RANGE_SELF, cast_idx=CAST_INSTANT, cooldown_ms=180000,
        duration_idx=DUR_20S,
        effects=[
            dict(eff=E_APPLY_AURA, aura=A_MOD_DAMAGE_DONE_PCT, base=0, tgt=T_SELF),
        ],
        desc=("For $d, each different ability you use increases your damage by 3%, stacking up "
              "to 5 times. Using an ability again adds nothing."),
        compare="Avenging Wrath is +20% for 20s on 3 minutes. This tops out at +15% for the "
                "same 20s on the same cooldown, and only if you cycle five abilities.",
    ),
    dict(
        key="wildcard_surge", name="Wildcard Surge", rarity=4, script=True, type=3,
        first_level=70, ranks=2, step=8, donor=133, school=64,
        icon=1950,
        # Arcane Barrage's look: Arcane, missile model 322, impact 9849. It
        # was Divine Storm's, a melee whirl with no missile at all.
        # precast 7428 is Arcane Blast's, and a precast kit is what plays
        # DURING the cast bar. 9947's own field 1 is zero, so a two and a half
        # second cast animated nothing at all.
        visual=9947, visual_kits=dict(impact_area=13152, precast=7428),
        power=("mana", 20), power_is_pct=True,
        speed=SPEED_BOLT,   # a bolt, at Fireball's speed
        range_idx=RANGE_30, cast_idx=CAST_2500, cooldown_ms=180000,
        effects=[
            dict(eff=E_SCHOOL_DAMAGE, base=dmg(1.6), tgt=T_ENEMY),
        ],
        desc=("Deals $s1 Arcane damage to the target, increased by 8% for each Epic or "
              "Legendary ability you know, up to 40%."),
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
# =====================================================================
# THE HERO TALENT TAB
#
# A talent reaches a forged line through the ordinary spell-mod path: its
# effect names a SpellModOp in EffectMiscValue and the lines it touches in
# EffectSpellClassMask, and SpellInfo::IsAffected matches this file's
# SpellFamilyName (14) and then that mask against each line's own class bit.
# No script, no hook -- the same machinery every class tree runs on.
#
# `affects` is a list of recipe keys. Their bits are resolved at build time
# from ID_ORDER, so a talent can never point at a line that does not exist.
# =====================================================================
MARKERS = ["cairn", "waystone", "signal_fire", "bulwark_anchor",
           "rally_point", "reclaimed_sentry"]
CONTROL = ["kick_dirt", "vertigo", "hush", "draw_attention", "rattle"]
RESERVES = ["brace", "ward_off", "second_nature", "adrenaline"]

TALENTS = [
    # ---- column 0: improvisation, the pools feeding each other -------------
    # Read by C++: spell_cw_makeshift_strike cuts Hurl's cooldown by this much
    # every time the strike lands. Makeshift Strike has no cooldown of its own
    # and Hurl has six seconds, so the two improvised weapons feed each other
    # instead of sitting in the same bar doing the same thing.
    dict(key="improvised_arsenal", name="Improvised Arsenal", row=0, col=0, ranks=5,
         icon=2185, dummy=True, values=[500, 1000, 1500, 2000, 2500],
         desc="Each time Makeshift Strike deals damage, the remaining cooldown of "
              "Hurl drops by $/1000;s1 sec."),
    # One point, one clear promise. Restoring your reserves while rooted was
    # the moment both of these spells felt pointless.
    dict(key="field_repairs", name="Field Repairs", row=1, col=0, ranks=1,
         icon=1997, dummy=True, values=[1],
         desc="Second Nature and Adrenaline also free you from snares and roots."),
    # A shield that is fully spent was cast at the right moment; one that
    # falls off unused was not. This pays for the first and ignores the second.
    dict(key="last_reserve", name="Last Reserve", row=2, col=0, ranks=2,
         icon=3397, dummy=True, values=[50, 100],
         desc="When Ward Off's shield is absorbed to the last point, $s1% of its "
              "cooldown is refunded."),
    dict(key="thrift", name="Thrift", row=3, col=0, ranks=3,
         icon=3184, affects=RESERVES + ["quicksilver"],
         op=MOD_COST, pct=True, values=[-10, -20, -30],
         desc="Reduces the cost of Brace, Ward Off, Second Nature, Adrenaline and "
              "Quicksilver by $s1%."),
    dict(key="overdraw", name="Overdraw", row=4, col=0, ranks=3,
         icon=2899, affects=["adrenaline", "quickening", "second_nature"],
         op=MOD_COOLDOWN, pct=True, values=[-10, -20, -30],
         desc="Reduces the cooldown of Adrenaline, Quickening and Second Nature by $s1%."),

    # ---- column 1: the things you put on the ground ------------------------
    dict(key="scavengers_eye", name="Scavenger's Eye", row=0, col=1, ranks=3,
         icon=442, affects=MARKERS,
         op=MOD_DURATION, pct=False, values=[3000, 6000, 9000],
         desc="Everything you place lasts $/1000;s1 sec longer."),
    dict(key="wider_net", name="Wider Net", row=1, col=1, ranks=2,
         icon=2034, affects=MARKERS,
         op=MOD_RADIUS, pct=True, values=[10, 20],
         desc="Increases the radius of everything you place by $s1%."),
    # "Pack Mule" is a stock spell name (62076) and the client keys tooltips by
    # name in places, so it takes one of its own.
    # The beetle's alone. The Sentry is a fixed turret with its own talent
    # (Overclocked) and no business in a talent about a beast.
    dict(key="venom_handler", name="Venom Handler", row=2, col=1, ranks=3,
         icon=1630, dummy=True, values=[1, 2, 3],
         desc="When an enemy dies with your Venom Beetle's poison on it, the beetle "
              "plants that poison on up to $s1 enemies near the body."),
    dict(key="quick_deploy", name="Quick Deploy", row=3, col=1, ranks=3,
         icon=2629, affects=MARKERS,
         op=MOD_COOLDOWN, pct=True, values=[-10, -20, -30],
         desc="Reduces the cooldown of everything you place by $s1%."),
    # The beetle's second talent, and the only healing a Hero gets out of a
    # summon. One point: it either knows the spell or it does not.
    dict(key="medicinal_venom", name="Medicinal Venom", row=4, col=1, ranks=1,
         icon=2101, dummy=True, values=[1],
         desc="Your Venom Beetle learns Healing Spit, and spits it at whichever "
              "of your party is hurt worst."),

    # ---- column 2: breadth, the classless payoff ---------------------------
    # An order to press them in, rather than a number on both. Bleed Over is
    # instant and Emberfeed is a two second cast, so the combo costs a global
    # and pays for the nuke that follows.
    dict(key="field_study", name="Field Study", row=0, col=2, ranks=3,
         icon=1468, dummy=True, values=[40, 70, 100],
         desc="Emberfeed refunds $s1% of its cost when its target is already "
              "bleeding from your Bleed Over."),
    # The three area controls only. Hush and Draw Attention are single target
    # and would collect the same energy for catching one thing, which is what
    # this is meant to stop being worth doing.
    dict(key="opportunist", name="Opportunist", row=1, col=2, ranks=5,
         icon=350, dummy=True, values=[2, 4, 6, 8, 10],
         desc="Pocket Sand, Vertigo and Sinkhole restore $s1 energy for every enemy "
              "they catch, up to five."),
    # Counted in cw_forged_watcher, which already sees every cast. The refund
    # is scheduled a tick late on purpose: Spell::cast calls the script hook
    # BEFORE TakePower, so paying it back at the hook would simply be paid
    # again a few lines later.
    dict(key="weave", name="Weave", row=2, col=2, ranks=3,
         icon=2458, dummy=True, values=[5, 4, 3],
         desc="Every $s1 Hero abilities you cast, the last one refunds its cost."),
    dict(key="wide_swing", name="Wide Swing", row=3, col=2, ranks=2,
         icon=2847, affects=["wide_arc", "kick_dirt", "vertigo", "overflow", "sinkhole"],
         op=MOD_RADIUS, pct=True, values=[15, 30],
         desc="Increases the radius of Wide Arc, Pocket Sand, Vertigo, Overflow and "
              "Sinkhole by $s1%."),
    dict(key="ricochet_chamber", name="Ricochet Chamber", row=4, col=2, ranks=2,
         icon=2242, affects=["ricochet_shot"],
         op=MOD_EFFECT2, pct=False, values=[1, 2],
         desc="Ricochet Shot bounces $s1 additional time."),

    # ---- column 3: what a Hero has that no class does ----------------------
    dict(key="long_reach", name="Long Reach", row=2, col=3, ranks=2,
         icon=251, affects=["hurl", "ricochet_shot", "overflow", "quicksilver",
                            "sinkhole", "reclaimed_sentry", "rattle"],
         op=MOD_RANGE, pct=True, values=[10, 20],
         desc="Increases the range of your ranged Hero abilities by $s1%."),
    dict(key="sharpened", name="Sharpened", row=3, col=3, ranks=3,
         icon=2982, affects=["makeshift_strike", "hurl", "wide_arc", "crossdraw",
                             "emberfeed", "antipode_blast", "vanguard_rush",
                             "ricochet_shot", "wildcard_surge"],
         op=MOD_CRIT, pct=False, values=[3, 6, 9],
         desc="Increases the critical strike chance of your damaging Hero abilities "
              "by $s1%."),
    dict(key="encore", name="Encore", row=5, col=3, ranks=3,
         icon=2615, affects=["repertoire"],
         op=MOD_DURATION, pct=False, values=[4000, 8000, 12000],
         desc="Increases the duration of Repertoire by $/1000;s1 sec."),
    # ---- the four a modifier cannot express -------------------------------
    # These carry SPELL_AURA_DUMMY and are read by C++ through
    # GetDummyAuraEffect(family, icon, 0). The icon is the key, so each of the
    # four wears one no other Hero talent does.
    dict(key="adrenal_surge", name="Adrenal Surge", row=5, col=0, ranks=2,
         icon=1904, dummy=True, values=[10, 20],
         desc="Increases the maximum bonus of Quickening by $s1%."),
    # "Overcharge" is a stock spell name (37104, 64218), so this takes its own.
    dict(key="overcharge", name="Overclocked", row=6, col=1, ranks=1,
         icon=2303, dummy=True, values=[50],
         desc="Your Reclaimed Sentry fires twice as often."),
    dict(key="two_schools", name="Two Schools", row=7, col=2, ranks=5,
         icon=2215, dummy=True, values=[2, 4, 6, 8, 10],
         desc="Whenever you deal damage of a different school than your last, that "
              "damage is increased by $s1%."),
    dict(key="jack_of_all_trades", name="Jack of All Trades", row=8, col=3, ranks=5,
         icon=2590, dummy=True, values=[1, 2, 3, 4, 5],
         desc="Increases your damage and healing by $s1% for every 3 different "
              "classes you have an ability from."),

    # Overflow spills around the ally it lands on, so healing someone across
    # the room healed you for nothing. This puts you in the spill wherever you
    # are standing, which is what makes it worth casting on someone else.
    dict(key="broad_strokes", name="Broad Strokes", row=6, col=3, ranks=1,
         icon=1871, dummy=True, values=[1],
         desc="Overflow's spill also reaches you, however far away its target is."),
]


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
    # drill_ground's recipe was replaced by quicksilver rather than edited, so
    # its block is retired and every other id stays where it is
    "quicksilver",
]

_recipe_keys = {r["key"] for r in RECIPES}
assert _recipe_keys <= set(ID_ORDER), \
    "recipes missing from ID_ORDER: %s" % (_recipe_keys - set(ID_ORDER))
assert len(ID_ORDER) == len(set(ID_ORDER)), "ID_ORDER has a duplicate"

# Which lines carry a SpellScript, read off the recipes so the two can never
# disagree. Their C++ lives in src/ClasslessForgedScripts.cpp, and the spell
# ids it needs are the `first` of each line below.
SCRIPTED = [r["key"] for r in RECIPES if r.get("script")]
# `script` is normally True, meaning "spell_cw_<key>". Given a string instead it
# names the script, so several lines can share one -- Second Nature and
# Adrenaline both answer to the talent that breaks snares, and there is no
# reason for two identical classes.
SCRIPT_NAMES = {r["key"]: (r["script"] if isinstance(r["script"], str)
                           else "spell_cw_%s" % r["key"])
                for r in RECIPES if r.get("script")}
# A pet spell can name one too. Its key is <recipe>_pet<n>, which is what the
# spell rows are written under, so the two maps are read the same way.
for _r in RECIPES:
    for _i, _ps in enumerate(_r.get("pet_spells", [])):
        if _ps.get("script"):
            SCRIPT_NAMES["%s_pet%d" % (_r["key"], _i)] = _ps["script"]


def pinned_index(key):
    """Where this line's ids live. Fixed for the life of the line."""
    try:
        return ID_ORDER.index(key)
    except ValueError:
        sys.exit("recipe '%s' is not in ID_ORDER. Append it to the END of that list; "
                 "inserting renumbers every line after it." % key)


def block_of(index):
    return SPELL_BASE + index * PER_RECIPE


def affect_mask(keys):
    """The three 32-bit words naming the lines a talent reaches.

    A key that is not a line is a hard error rather than a silently empty
    mask: an EffectSpellClassMask of zero means "affects every spell in the
    family", which is every forged ability at once.
    """
    words = [0, 0, 0]
    for key in keys:
        bit = pinned_index(key)          # exits if the key is not a real line
        words[bit // 32] |= 1 << (bit % 32)
    assert any(words), "a talent must name at least one line"
    return tuple(words)


def build_talents(spell):
    """One passive spell per talent rank, plus the rows the two tables need."""
    rows, meta = [], []
    for n, tal in enumerate(TALENTS):
        assert len(tal["values"]) == tal["ranks"], tal["key"]
        # A dummy talent is read by C++ rather than matched by the spell-mod
        # system, so it names no lines and carries no mask at all.
        mask = (0, 0, 0) if tal.get("dummy") else affect_mask(tal["affects"])
        level = 10 + tal["row"] * 5
        ranks = []
        for r in range(tal["ranks"]):
            sid = TALENT_SPELL_BASE + n * TALENT_SPELL_STRIDE + r
            rec = dict(
                key="talent_%s" % tal["key"], name=tal["name"], passive=True,
                ranks=tal["ranks"], donor=TALENT_DONOR, school=1,
                icon=tal["icon"], visual=0,
                power=("mana", 0), range_idx=RANGE_SELF, cast_idx=CAST_INSTANT,
                cooldown_ms=0,
                effects=[dict(
                    eff=E_APPLY_AURA,
                    aura=(A_DUMMY if tal.get("dummy") else
                          (A_ADD_PCT_MODIFIER if tal["pct"] else A_ADD_FLAT_MODIFIER)),
                    base=tal["values"][r], tgt=T_SELF,
                    misc=0 if tal.get("dummy") else tal["op"], affect_mask=mask)],
                desc=tal["desc"],
            )
            row, donor = build_row(spell, rec, r, level, sid, None, None)
            rows.append(dict(id=sid, first=TALENT_SPELL_BASE + n * TALENT_SPELL_STRIDE,
                             rank=r + 1, level=level,
                             key="talent_%s_r%d" % (tal["key"], r + 1), values=row,
                             base=TALENT_DONOR, fields=overrides_of(row, donor),
                             visual=0, icon=tal["icon"], sla=None))
            ranks.append(sid)
        meta.append(dict(id=TALENT_ID_BASE + n, key=tal["key"], name=tal["name"],
                         row=tal["row"], col=tal["col"], ranks=ranks))
    return rows, meta


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
    v[208] = recipe.get("family", HERO_FAMILY)   # SpellFamilyName
    for off in range(3):
        setf("EffectSpellClassMask", 0, off * 3)
        setf("EffectSpellClassMask", 0, off * 3 + 1)
        setf("EffectSpellClassMask", 0, off * 3 + 2)
    # This row's OWN class flags. The donor's survive otherwise -- every forged
    # row was carrying one (Makeshift Strike held Sinister Strike's 8388610),
    # inert only because the family was 0, and live the moment it is not.
    v[SPELL_CLASS_MASK] = v[SPELL_CLASS_MASK + 1] = v[SPELL_CLASS_MASK + 2] = 0
    if "class_bit" in recipe:
        bit = recipe["class_bit"]
        v[SPELL_CLASS_MASK + bit // 32] = 1 << (bit % 32)
    # A spell mod cannot reach a spell that refuses caster modifiers, and
    # SpellInfo::IsAffectedBySpellMod checks this before anything else.
    v[7] &= ~0x20000000                         # ATTR3 IGNORE_CASTER_MODIFIERS
    v[1] = 0                                    # Category
    v[49] = 0                                   # StackAmount
    # ProcFlags say WHEN this spell's proc aura fires. None of these spells has
    # one, so a donor's flags are inert at best and a surprise at worst: Charge
    # brought 0xfec3 to Vanguard Rush and Power Word: Shield's donor brought
    # 0x1a84 to Ward Off. A recipe that ever wants a proc can set them back.
    v[27] = recipe.get("proc_flags", 0)          # ProcFlags

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
              | 0x00020000)  # ONLY_STEALTHED
    # PASSIVE is cleared for an ability -- a donor's passive bit would leave it
    # uncastable -- but a talent rank IS a passive, and 0x80 keeps it off the
    # buff bar the way every stock talent passive is.
    if recipe.get("passive"):
        v[4] |= 0x00000040 | 0x00000080
    else:
        v[4] &= ~0x00000040
    # Hand of Freedom is castable while stunned on purpose; six spells that
    # copied its row inherited that and became defensive and offensive
    # cooldowns a stun could not answer. Nothing in this set is meant to beat
    # crowd control, so the bit goes with the rest of the donor's conditions.
    # A finishing move needs combo points, and the requirement lives on the
    # donor's row: Rip's brought "That ability requires combo points" to a
    # ranged Nature bleed that has nothing to do with them. Both bits go, the
    # same way the stance and stun conditions do.
    v[5] &= ~(0x00100000     # ATTR1 FINISHING_MOVE_DAMAGE
              | 0x00400000)  # ATTR1 FINISHING_MOVE_DURATION
    v[9] &= ~0x00000008                          # ATTR5 ALLOW_WHILE_STUNNED
    # AttributesEx7 bit 16, which AzerothCore's own enum info names "Can
    # restore secondary power": the ONLY thing in the server that lets a spell
    # fill a pool which is not a player's displayed bar. EffectEnergize,
    # EffectEnergizePct and HandlePeriodicEnergizeAuraTick each refuse a player
    # outright without it, and those three reads are its only uses anywhere.
    # A Hero holds mana, rage and energy at once -- OnPlayerAfterUpdateMaxPower
    # floors all three -- but only the chassis pool counts as active, so
    # Adrenaline's energy reached nobody but an energy chassis and Makeshift
    # Strike's mana return reached only casters, both without a word on screen.
    # Derived from the effects rather than declared, so the next recipe that
    # restores power gets it whether or not anyone remembers.
    if any(e.get("eff") in (E_ENERGIZE, E_ENERGIZE_PCT)
           or e.get("aura") == A_PERIODIC_ENERGIZE
           for e in recipe["effects"]):
        v[11] |= ATTR7_RESTORE_SECONDARY_POWER
    v[18] = 0                                   # RequiresSpellFocus
    for i in range(8):
        v[52 + i] = 0                           # Reagent
        v[60 + i] = 0                           # ReagentCount
    v[50] = v[51] = 0                           # Totem
    # ...and the tool CATEGORY, which is the other half of the same
    # requirement. Missing it meant every totem-shaped forged spell
    # inherited its donor's Earth Totem: the server strips the column at
    # startup, but the client patch does not reach these rows (the tool
    # sweep runs over class spells, before the forged rows are added), so
    # the client kept a red Tools: line and refused the cast locally.
    v[222] = v[223] = 0                         # RequiredTotemCategoryID

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

    # a missile only travels if the row says how fast; the visual alone does
    # nothing, and a visual WITHOUT a missile ignores this
    v[SPEED] = float(recipe.get("speed", 0.0))

    kind, amount = recipe.get("power", ("mana", 0))
    v[41] = POWER[kind]
    if recipe.get("power_is_pct"):
        v[42] = 0
        v[MANA_COST_PCT] = amount
    else:
        # Rage is stored times ten: Heroic Strike's 15 rage is a 150 in this
        # column, and the client divides on display. A 20 here showed "2 Rage".
        v[42] = amount * 10 if kind == "rage" else amount
        v[MANA_COST_PCT] = 0

    for slot in range(3):
        e = recipe["effects"][slot] if slot < len(recipe["effects"]) else None
        setf("Effect", e["eff"] if e else 0, slot)
        setf("EffectApplyAuraName", (e.get("aura", 0) if e else 0), slot)
        setf("EffectImplicitTargetA", (e.get("tgt", 0) if e else 0), slot)
        setf("EffectImplicitTargetB", (e.get("tgtb", 0) if e else 0), slot)
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
        # Which spells this effect's modifier reaches, matched against the
        # target spell's own class flags.
        #
        # The layout is EFFECT-major, not word-major: the core declares
        # `std::array<flag96, MAX_SPELL_EFFECTS> EffectSpellClassMask` and
        # reads `EffectSpellClassMask[effIndex]`, so the nine columns are
        # effect0's three words, then effect1's, then effect2's. The SQL names
        # (A_1 A_2 A_3 B_1 ...) read the other way round and are a trap: going
        # by them puts word 1 into effect 1's column.
        #
        # Stock proof, checked in test_forged.py so this cannot flip again:
        # Improved Thunder Clap (12287) holds [128,0,0, 128,0,0, 128,0,0] and
        # Thunder Clap's own flags are [128,0,0]. Effect-major gives all three
        # of its effects that mask -- cost, damage and slow, which is what the
        # talent does. Word-major would leave effects 1 and 2 with nothing.
        for word, val in enumerate(e.get("affect_mask", (0, 0, 0)) if e else (0, 0, 0)):
            setf("EffectSpellClassMask", val, slot * 3 + word)
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
                base = resolve(e["base"], level, rank_index)
        setf("EffectTriggerSpell", trig, slot)
        # EffectBasePoints is stored one below the value the client shows
        setf("EffectBasePoints", int(round(base)) - 1, slot)

    for first, mask in LOCALE_BLOCKS:
        for k in range(first, mask):
            v[k] = ""
    v[F["SpellName"]] = recipe["name"]
    v[F["Rank"]] = "Rank %d" % (rank_index + 1) if recipe["ranks"] > 1 else ""
    # ${companion}s1 in a description is the client's cross-spell reference to the
    # rank's own companion, so a hidden half's number shows on the visible half
    v[F["Description"]] = recipe["desc"].replace("{companion}", str(companion_id or 0))
    # Column 187 is what the BUFF ICON shows on hover; column 170 is what the
    # spellbook shows. Every row set this to "", so a Hero could see a buff
    # running and had no way to find out what it was doing. A spell that applies
    # an aura now carries the same sentence in both places.
    if any(v[F["Effect"] + i] in (6, 27) for i in range(3)):
        tip = recipe.get("tooltip", recipe["desc"]).replace(
            "{companion}", str(companion_id or 0))
        # the buff frame already prints "11 seconds remaining", so the duration
        # comes off the end the way Blizzard's own aura tooltips leave it out
        tip = re.sub(r"\s+for \$d(?=[.,]|$)", "", tip)
        v[F["ToolTip"]] = tip
    else:
        v[F["ToolTip"]] = ""
    return v, donor


def resolve(base, level, rank_index=0):
    if isinstance(base, tuple):
        kind, val = base
        if kind == "ranks":
            # a literal per rank, for things the curve cannot price: an energy
            # restore is capped by a 100-point pool whatever the level
            return val[min(rank_index, len(val) - 1)]
        return anchor(kind, level) * val
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
        # the line's own class-flag bit, stable for the life of the line because
        # ID_ORDER is. A companion and a pet spell inherit it with the rest of
        # the recipe, so a talent that names a line reaches every part of it.
        recipe = dict(recipe, class_bit=index)
        first = block_of(index)
        if recipe.get("visual_kits"):
            vid = VISUAL_BASE + index
            visuals.append(dict(id=vid, base=recipe["visual"],
                                kits={VISUAL_SLOT[k]: v
                                      for k, v in recipe["visual_kits"].items()}))
            recipe = dict(recipe, visual=vid)
        # A companion has a look of its own, and may ask for its own kits. This
        # read the recipe's `visual_kits` only, so a companion that asked was
        # handed the raw donor row and none of the kits it named -- silently,
        # because nothing downstream reads the key again. Its own block of ids
        # so a line can recombine both halves.
        _comp = recipe.get("companion")
        if _comp and _comp.get("visual_kits"):
            cvid = VISUAL_BASE + 100 + index
            visuals.append(dict(id=cvid, base=_comp["visual"],
                                kits={VISUAL_SLOT[k]: v
                                      for k, v in _comp["visual_kits"].items()}))
            recipe = dict(recipe, companion=dict(_comp, visual=cvid))
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
                # the PARENT's rank index, not 0: a companion is a single-rank
                # spell (comp["ranks"] = 1 keeps its rank text empty) but its
                # numbers still come from the rank that triggered it, and a
                # ("ranks", [...]) literal resolved to the first entry every time.
                crow, cdonor = build_row(spell, comp, r, level, cid, None, None)
                # a hidden half: no skill line row, so it never shows in a tab
                spells.append(dict(id=cid, first=cid, rank=1, level=level,
                                   key=recipe["key"] + "_companion", values=crow,
                                   base=comp["donor"], fields=overrides_of(crow, cdonor),
                                   visual=comp["visual"], icon=comp["icon"], sla=None))
        # A pet's abilities are hidden spells of their own, one per entry in
        # pet_spells, built at the level of the rank that unlocks them so each
        # is worth something when it arrives.
        for n, petspell in enumerate(recipe.get("pet_spells", [])):
            # a pet learns this at the level it names, so it is built there
            unlock = petspell.get("level", recipe["first_level"] + n * recipe["step"])
            ps = dict(recipe)
            ps.update(petspell)
            ps["ranks"] = 1
            pid = first + 16 + n
            prow, pdonor = build_row(spell, ps, 0, min(unlock, 80), pid, None, None)
            # A pet spell that must never be learned on its own says so here,
            # after the numbers are built: SpellLevel is what
            # Pet::InitLevelupSpellsForLevel reads, and nothing else.
            if "spell_level" in petspell:
                prow[F["SpellLevel"]] = petspell["spell_level"]
            spells.append(dict(id=pid, first=pid, rank=1, level=min(unlock, 80),
                               key=recipe["key"] + "_pet%d" % n, values=prow,
                               base=ps["donor"], fields=overrides_of(prow, pdonor),
                               visual=ps["visual"], icon=ps["icon"], sla=None))

        lines.append(dict(key=recipe["key"], first=first, rarity=recipe["rarity"],
                          type=recipe.get("type", 255), name=recipe["name"], ids=ids))
        meta.append(dict(key=recipe["key"], compare=recipe["compare"]))
    # The Hero talent tab. Its rank spells ride in the same list as everything
    # else, so they reach the client through the one installer and the one
    # manifest; `sla` is None, so none of them gets a skill-line row.
    if not only:
        trows, tmeta = build_talents(spell)
        spells.extend(trows)
    else:
        tmeta = []
    return spells, lines, meta, visuals, tmeta


def generation_id(spells, visuals=(), creatures=()):
    """A fingerprint of the WHOLE run, not just the spell rows.

    It stamps cw_forged_meta and is the one number that says whether a realm is
    running current data. It used to hash only id, values and sla -- and a
    recombined visual keeps its id when its donor changes, so a round that moved
    every spell onto a different look left the stamp identical and a stale
    client patch looked current. Creature rows are in for the same reason: a
    model or a scale change moves nothing else.
    """
    h = hashlib.sha1()
    for s in sorted(spells, key=lambda x: x["id"]):
        h.update(json.dumps([s["id"], s["values"], s["sla"]],
                            sort_keys=True, default=str).encode("utf-8"))
    for v in sorted(visuals, key=lambda x: x["id"]):
        h.update(json.dumps(v, sort_keys=True, default=str).encode("utf-8"))
    for c in sorted(creatures):
        h.update(json.dumps(c, sort_keys=True, default=str).encode("utf-8"))
    return h.hexdigest()[:12]


def table_sql(table, columns, comment):
    """CREATE the table, then add whatever an older copy of it is missing.

    Only the CREATE does anything on a fresh database, and only the ALTERs do
    anything on a realm that already applied an older build of this file. Both
    halves read the same column list, so a column added to that list reaches an
    existing table as well as a new one; without the second half, CREATE TABLE
    IF NOT EXISTS leaves the older table alone and the INSERT further down the
    file dies on the column it does not have.

    The information_schema guard is the shape cw_world_base.sql already uses.
    """
    def column(name, decl, note):
        return "`%s` %s%s" % (name, decl, (" COMMENT '%s'" % note) if note else "")

    proc = "cw_%s_schema" % table.replace("cw_", "", 1)
    L = ["CREATE TABLE IF NOT EXISTS `%s` (" % table]
    L += ["  %s," % column(*c) for c in columns]
    L += ["  PRIMARY KEY (`%s`)" % columns[0][0],
          ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci "
          "COMMENT='%s';" % comment,
          "",
          "-- CREATE TABLE IF NOT EXISTS leaves a table that already exists exactly",
          "-- as it found it, so a realm that applied an earlier build of this file",
          "-- still has that build's columns. Add the missing ones before anything",
          "-- below names them.",
          "DROP PROCEDURE IF EXISTS %s;" % proc,
          "DELIMITER //",
          "CREATE PROCEDURE %s()" % proc,
          "BEGIN"]
    for n, (name, decl, note) in enumerate(columns[1:]):
        L += ["    IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS",
              "                   WHERE TABLE_SCHEMA = DATABASE()",
              "                     AND TABLE_NAME = '%s'" % table,
              "                     AND COLUMN_NAME = '%s') THEN" % name,
              "        ALTER TABLE `%s` ADD COLUMN %s AFTER `%s`;"
              % (table, column(name, decl, note), columns[n][0]),
              "    END IF;"]
    L += ["END //",
          "DELIMITER ;",
          "CALL %s();" % proc,
          "DROP PROCEDURE IF EXISTS %s;" % proc,
          ""]
    return L


# ---- output -----------------------------------------------------------------
def write_sql(spells, lines, gen, path, talents=()):
    L = ["-- mod-classless-wildcard: forged spells, generated by",
         "-- data/sql/generators/gen_forged_spells.py. Do not hand-edit.",
         "-- Requires a worldserver restart.",
         "",
         *table_sql("cw_forged_spells", FORGED_COLUMNS,
                    "Classless forged spells"),
         *table_sql("cw_forged_meta", META_COLUMNS,
                    "Which generator run the forged rows came from"),
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
    # A LINE of one rank is not a chain, and SpellMgr::LoadSpellRanks logs
    # "There is only 1 spell rank for identifier ... entry is not needed!" for
    # every one of them at startup. Ten forged lines have a single rank, so ten
    # of those lines were ours.
    _per_line = _collections.Counter(s["first"] for s in ranked)
    ranked = [s for s in ranked if _per_line[s["first"]] > 1]
    L.append("INSERT INTO `spell_ranks` (`first_spell_id`, `spell_id`, `rank`) VALUES")
    for n, s in enumerate(ranked):
        end = ";" if n == len(ranked) - 1 else ","
        L.append("(%d, %d, %d)%s" % (s["first"], s["id"], s["rank"], end))
    L.append("")

    # One row per RANK, not per line: a SpellScript is bound by spell id, so a
    # line whose later ranks are missing here would silently lose its script
    # partway up the level range. The name is the C++ class name, which is what
    # RegisterSpellScript registers under.
    # A companion is scripted too when its recipe says companion_script: the
    # ricochet has to know how many ricochets are left.
    bounce = {r["key"] for r in RECIPES if r.get("companion_script")}

    def script_name(key):
        if key.endswith("_companion"):
            return "spell_cw_%s_bounce" % key[:-len("_companion")]
        return SCRIPT_NAMES.get(key, "spell_cw_%s" % key)

    pet_scripted = {k for k in SCRIPT_NAMES if "_pet" in k}
    scripted = [s for s in spells
                if (s["key"] in SCRIPTED and not s["key"].endswith("_companion"))
                or (s["key"].endswith("_companion") and s["key"][:-len("_companion")] in bounce)
                or s["key"] in pet_scripted]
    if scripted:
        L.append("DELETE FROM `spell_script_names` WHERE `spell_id` BETWEEN %d AND %d;"
                 % (SPELL_BASE, BLOCK_END))
        L.append("INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`) VALUES")
        for n, sp in enumerate(scripted):
            end = ";" if n == len(scripted) - 1 else ","
            L.append("(%d, '%s')%s" % (sp["id"], script_name(sp["key"]), end))
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
             "`speed_walk`, `speed_run`, "
             "`DamageModifier`, `HealthModifier`, `ScriptName`, `VerifiedBuild`)")
    L.append("VALUES")
    for n, (entry, cname, _display, pet, dmg, hp) in enumerate(creatures):
        end = ";" if n == len(creatures) - 1 else ","
        if pet:
            # a real guardian: attackable, mobile, a beast, and it fights
            # 1.0 is a running player's speed: a scarab at a pet's usual pace
            # scuttled in fast-forward. The row is the statement of intent --
            # Pet.cpp writes 1.15f over speed_run for every pet before anyone
            # sees it, so cw_forged_pet_model is what actually holds the beetle
            # to this number.
            L.append("(%d, '%s', '', 1, 80, 35, 0, 1, 0, %d, 0, 1, %d, 1.0, 1.0, "
                     "%.2f, %.2f, '', 12340)%s"
                     % (entry, cname, CREATURE_TYPE_BEAST, 0x00000040, dmg, hp, end))
        else:
            # ScriptName is what binds a CreatureScript, and an emplacement that
            # acts needs one. Everything else keeps the empty name it had.
            L.append("(%d, '%s', '', 1, 80, 35, 0, 1, %d, %d, 0, 1, %d, 1.0, 1.14286, "
                     "1.00, 1.00, '%s', 12340)%s"
                     % (entry, cname, UNIT_FLAGS_MARKER, CREATURE_TYPE_TOTEM,
                        EXTRA_FLAGS_MARKER, CREATURE_SCRIPT.get(entry, ""), end))
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
        L.append("(%d, 0, %d, %.2f, 1, 12340)%s"
                 % (c[0], c[2], MODEL_SCALE.get(c[0], 1.0), end))
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
    # An emplacement holds exactly one spell, in slot 0, so its AI can fire
    # m_spells[0] without knowing any id. One entry per rank is what makes the
    # rank's own numbers reachable.
    for entry, (key, idx) in sorted(CREATURE_SPELL.items()):
        sid = next((sp["id"] for sp in spells
                    if sp["key"] == "%s_pet%d" % (key, idx)), None)
        if sid:
            petrows.append((entry, 0, sid))
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

    if talents:
        L.append("-- The Hero talent tab. `talenttab_dbc` and `talent_dbc` are world-table")
        L.append("-- overrides: DBCDatabaseLoader::Load ADDS and overrides by id, so the")
        L.append("-- stock 33 tabs and 892 talents are untouched. Column order is the DBC")
        L.append("-- field order, one column per character of the core's format string.")
        L.append("DELETE FROM `talenttab_dbc` WHERE `ID` = %d;" % HERO_TALENT_TAB)
        L.append("INSERT INTO `talenttab_dbc` (`ID`, `Name_Lang_enUS`, `Name_Lang_Mask`, "
                 "`SpellIconID`, `RaceMask`, `ClassMask`, `PetTalentMask`, `OrderIndex`, "
                 "`BackgroundFile`) VALUES")
        # ClassMask bit 11 -> the addon's CLASS_HERO page, which already has a
        # button and an icon and only ever lacked a tree.
        L.append("(%d, 'Hero', 16712190, %d, 0, %d, 0, 0, '');"
                 % (HERO_TALENT_TAB, HERO_TAB_ICON, HERO_TAB_CLASSMASK))
        L.append("")
        first_id = TALENT_ID_BASE
        last_id = TALENT_ID_BASE + len(TALENTS) - 1
        L.append("DELETE FROM `talent_dbc` WHERE `ID` BETWEEN %d AND %d;" % (first_id, last_id))
        L.append("INSERT INTO `talent_dbc` (`ID`, `TabID`, `TierID`, `ColumnIndex`, "
                 "`SpellRank_1`, `SpellRank_2`, `SpellRank_3`, `SpellRank_4`, `SpellRank_5`, "
                 "`SpellRank_6`, `SpellRank_7`, `SpellRank_8`, `SpellRank_9`, "
                 "`PrereqTalent_1`, `PrereqTalent_2`, `PrereqTalent_3`, "
                 "`PrereqRank_1`, `PrereqRank_2`, `PrereqRank_3`, `Flags`, "
                 "`RequiredSpellID`, `CategoryMask_1`, `CategoryMask_2`) VALUES")
        for n, t in enumerate(talents):
            end = ";" if n == len(talents) - 1 else ","
            ranks = list(t["ranks"]) + [0] * (5 - len(t["ranks"]))
            # 23 columns: ID, TabID, TierID, ColumnIndex, SpellRank_1..9,
            # PrereqTalent_1..3, PrereqRank_1..3, Flags, RequiredSpellID and
            # CategoryMask_1..2. That is 4 + 5 written ranks + 14 zeros.
            L.append("(%d, %d, %d, %d, %s, %s)%s"
                     % (t["id"], HERO_TALENT_TAB, t["row"], t["col"],
                        ", ".join(str(x) for x in ranks),
                        ", ".join(["0"] * 14), end))
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
               # The same row the SQL writes to skillraceclassinfo_dbc. The
               # server needs it (Player::_LoadSkills deletes a skill that has
               # none, at every login); the client's copy had none, which was
               # the last difference between the Hero line and a class line.
               # Masks are 0, which both sides read as "no restriction".
               skill_race_class=dict(id=RCI_ID, skill=HERO_LINE, race_mask=0,
                                     class_mask=0, flags=RCI_FLAGS, min_level=0,
                                     tier=0, cost_index=0),
               lines=[dict(key=l["key"], name=l["name"], first=l["first"]) for l in lines],
               visuals=visuals,
               spells=[dict(id=s["id"], first=s["first"], rank=s["rank"], level=s["level"],
                            key=s["key"], name=s["values"][F["SpellName"]],
                            rank_text=s["values"][F["Rank"]],
                            description=s["values"][F["Description"]],
                            tooltip=s["values"][F["ToolTip"]],
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
    spells, lines, meta, visuals, talents = build(spell, only)
    check_blocks(spells, visuals)
    # the whole run, so a round that only changes a look or a model still
    # moves the stamp a realm compares against
    gen = generation_id(spells, visuals,
                        [(e, n, d, MODEL_SCALE.get(e, 1.0)) for e, n, d, _p in SUMMON_CREATURES]
                        + [(e, k, d, MODEL_SCALE.get(e, 1.0))
                           for k, rows in sorted(PET_CREATURES.items())
                           for e, d, _n, _dm, _hm in rows])

    print("forged spells: %d lines, %d rows, generation %s" % (len(lines), len(spells), gen))
    for ln in lines:
        print("   %-18s first %-7d %d rank(s)" % (ln["key"], ln["first"], len(ln["ids"])))
    print("   %d recombined SpellVisual row(s)" % len(visuals))
    print("\nscripted lines (src/ClasslessForgedScripts.cpp): %s" % ", ".join(SCRIPTED))
    for ln in lines:
        if ln["key"] in SCRIPTED:
            print("   %-18s first spell %d" % (ln["key"], ln["first"]))

    run_desc = "only=%s" % (args.only or "all data-only recipes")
    write_sql(spells, lines, gen, args.out_sql, talents)
    write_manifest(spells, lines, visuals, gen, args.out_manifest, run_desc)
    print("\nwrote %s\n      %s" % (args.out_sql, args.out_manifest))


if __name__ == "__main__":
    main()
