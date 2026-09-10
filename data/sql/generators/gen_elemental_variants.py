#!/usr/bin/env python3
"""Generate elemental variants of the pool's physical strikes.

A variant is the base ability dealt as an element instead of Physical, at 85%
of the base's own weapon multiplier, with the element's own signature in the
second of the spell's three effect slots: a spell-power-scaled hit for Arcane,
a lifesteal hit for Holy, a burn for Fire, a poison for Poison, a snare for
Frost, an attack-speed cut for Earth, a healing cut for Shadow. Its tooltip is
the base's own description, modified for the element. The shape is Blizzard's
own Frost Strike; see PLAN-elemental-variants.md.

Reads the client's extracted DBCs and writes two things from ONE source, so
the server's numbers and the client's tooltips cannot drift:

    ../db-world/cw_spells_elemental.sql        server rows (spell_dbc,
                                               skilllineability_dbc,
                                               spell_ranks, cw_ability_variants)
    ../../../client-patch/elemental_manifest.json
                                               what the installer appends to the
                                               player's own Spell.dbc, SpellVisual,
                                               SpellIcon and SkillLineAbility, and
                                               the icon recipes

Run:  python3 gen_elemental_variants.py [--dbc DIR] [--bases NAME,NAME,...]
                                        [--elements fire,frost,...] [--ranks first|top|all]

Defaults are the shipped set: every eligible base, every element, every rank.
The Phase 1 wave was
    --bases "Sinister Strike,Heroic Strike,Backstab,Raptor Strike,Claw,Maul"
and the Phase 0 spike
    --bases "Sinister Strike" --elements fire --ranks first
"""
import argparse
import hashlib
import json
import os
import struct
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_SQL = os.path.join(HERE, os.pardir, "db-world", "cw_spells_elemental.sql")
OUT_MANIFEST = os.path.join(HERE, os.pardir, os.pardir, os.pardir,
                            "client-patch", "elemental_manifest.json")
DEFAULT_DBC = r"B:\New folder\dbc"
# The Phase 1 wave: six bases that between them cover on-next-swing (Heroic,
# Raptor), positional (Backstab), combo points (Sinister), and form-locked
# (Claw, Maul) strikes, so every copied attribute gets exercised.
PHASE1_BASES = "Sinister Strike,Heroic Strike,Backstab,Raptor Strike,Claw,Maul"

# ---- id blocks --------------------------------------------------------------
# Deterministic: a variant's id depends on its base's position in the FULL
# candidate list, not on which bases were enabled for this run, so enabling
# more bases later never renumbers the ones players already own.
SPELL_BASE = 950000      # stock max 80864, core customs to 100102, module items 990xxx
VISUAL_BASE = 17000      # stock max 16679
ICON_BASE = 5000         # stock max 4375
SLA_BASE = 22000         # stock max 21980
PER_BASE = 7 * 16        # 7 elements x up to 16 ranks per base
SPELL_BLOCK_END = SPELL_BASE + 64 * PER_BASE - 1

# ---- Spell.dbc, 3.3.5a build 12340: 234 fields -----------------------------
F = dict(Id=0, Attributes=4, Stances=12, DurationIndex=40, SpellLevel=39,
         BaseLevel=38, Effect=71, EffectDieSides=74, EffectRealPointsPerLevel=77,
         EffectBasePoints=80, EffectMechanic=83, EffectImplicitTargetA=86,
         EffectImplicitTargetB=89, EffectRadiusIndex=92, EffectApplyAuraName=95,
         EffectAmplitude=98, EffectValueMultiplier=101, EffectChainTarget=104,
         EffectItemType=107, EffectMiscValue=110, EffectMiscValueB=113,
         EffectTriggerSpell=116, EffectPointsPerComboPoint=119,
         EffectSpellClassMask=122, SpellVisual=131, SpellIconID=133,
         SpellName=136, SpellNameMask=152, Rank=153, RankMask=169,
         Description=170, DescriptionMask=186, ToolTip=187, ToolTipMask=203,
         SpellFamilyName=208, DmgClass=213, SchoolMask=225,
         EffectBonusMultiplier=229, SpellDescriptionVariableID=232)
FLOAT_FIELDS = {47} | set(range(77, 80)) | set(range(101, 104)) \
    | set(range(119, 122)) | set(range(216, 219)) | set(range(229, 232))
SIGNED_FIELDS = set(range(52, 60)) | {68, 69, 70} | set(range(74, 77)) \
    | set(range(80, 83)) | set(range(110, 116)) | {224}
STRING_FIELDS = set(range(136, 152)) | set(range(153, 169)) \
    | set(range(170, 186)) | set(range(187, 203))
LOCALE_BLOCKS = ((136, 152), (153, 169), (170, 186), (187, 203))  # (first col, mask col)

# spell_dbc columns, in DBC field order (AzerothCore world db)
SPELL_DBC_COLUMNS = (
    "ID Category DispelType Mechanic Attributes AttributesEx AttributesEx2 AttributesEx3 "
    "AttributesEx4 AttributesEx5 AttributesEx6 AttributesEx7 ShapeshiftMask unk_320_2 "
    "ShapeshiftExclude unk_320_3 Targets TargetCreatureType RequiresSpellFocus FacingCasterFlags "
    "CasterAuraState TargetAuraState ExcludeCasterAuraState ExcludeTargetAuraState CasterAuraSpell "
    "TargetAuraSpell ExcludeCasterAuraSpell ExcludeTargetAuraSpell CastingTimeIndex RecoveryTime "
    "CategoryRecoveryTime InterruptFlags AuraInterruptFlags ChannelInterruptFlags ProcTypeMask "
    "ProcChance ProcCharges MaxLevel BaseLevel SpellLevel DurationIndex PowerType ManaCost "
    "ManaCostPerLevel ManaPerSecond ManaPerSecondPerLevel RangeIndex Speed ModalNextSpell "
    "CumulativeAura Totem_1 Totem_2 Reagent_1 Reagent_2 Reagent_3 Reagent_4 Reagent_5 Reagent_6 "
    "Reagent_7 Reagent_8 ReagentCount_1 ReagentCount_2 ReagentCount_3 ReagentCount_4 ReagentCount_5 "
    "ReagentCount_6 ReagentCount_7 ReagentCount_8 EquippedItemClass EquippedItemSubclass "
    "EquippedItemInvTypes Effect_1 Effect_2 Effect_3 EffectDieSides_1 EffectDieSides_2 "
    "EffectDieSides_3 EffectRealPointsPerLevel_1 EffectRealPointsPerLevel_2 "
    "EffectRealPointsPerLevel_3 EffectBasePoints_1 EffectBasePoints_2 EffectBasePoints_3 "
    "EffectMechanic_1 EffectMechanic_2 EffectMechanic_3 ImplicitTargetA_1 ImplicitTargetA_2 "
    "ImplicitTargetA_3 ImplicitTargetB_1 ImplicitTargetB_2 ImplicitTargetB_3 EffectRadiusIndex_1 "
    "EffectRadiusIndex_2 EffectRadiusIndex_3 EffectAura_1 EffectAura_2 EffectAura_3 "
    "EffectAuraPeriod_1 EffectAuraPeriod_2 EffectAuraPeriod_3 EffectMultipleValue_1 "
    "EffectMultipleValue_2 EffectMultipleValue_3 EffectChainTargets_1 EffectChainTargets_2 "
    "EffectChainTargets_3 EffectItemType_1 EffectItemType_2 EffectItemType_3 EffectMiscValue_1 "
    "EffectMiscValue_2 EffectMiscValue_3 EffectMiscValueB_1 EffectMiscValueB_2 EffectMiscValueB_3 "
    "EffectTriggerSpell_1 EffectTriggerSpell_2 EffectTriggerSpell_3 EffectPointsPerCombo_1 "
    "EffectPointsPerCombo_2 EffectPointsPerCombo_3 EffectSpellClassMaskA_1 EffectSpellClassMaskA_2 "
    "EffectSpellClassMaskA_3 EffectSpellClassMaskB_1 EffectSpellClassMaskB_2 EffectSpellClassMaskB_3 "
    "EffectSpellClassMaskC_1 EffectSpellClassMaskC_2 EffectSpellClassMaskC_3 SpellVisualID_1 "
    "SpellVisualID_2 SpellIconID ActiveIconID SpellPriority "
    "Name_Lang_enUS Name_Lang_enGB Name_Lang_koKR Name_Lang_frFR Name_Lang_deDE Name_Lang_enCN "
    "Name_Lang_zhCN Name_Lang_enTW Name_Lang_zhTW Name_Lang_esES Name_Lang_esMX Name_Lang_ruRU "
    "Name_Lang_ptPT Name_Lang_ptBR Name_Lang_itIT Name_Lang_Unk Name_Lang_Mask "
    "NameSubtext_Lang_enUS NameSubtext_Lang_enGB NameSubtext_Lang_koKR NameSubtext_Lang_frFR "
    "NameSubtext_Lang_deDE NameSubtext_Lang_enCN NameSubtext_Lang_zhCN NameSubtext_Lang_enTW "
    "NameSubtext_Lang_zhTW NameSubtext_Lang_esES NameSubtext_Lang_esMX NameSubtext_Lang_ruRU "
    "NameSubtext_Lang_ptPT NameSubtext_Lang_ptBR NameSubtext_Lang_itIT NameSubtext_Lang_Unk "
    "NameSubtext_Lang_Mask "
    "Description_Lang_enUS Description_Lang_enGB Description_Lang_koKR Description_Lang_frFR "
    "Description_Lang_deDE Description_Lang_enCN Description_Lang_zhCN Description_Lang_enTW "
    "Description_Lang_zhTW Description_Lang_esES Description_Lang_esMX Description_Lang_ruRU "
    "Description_Lang_ptPT Description_Lang_ptBR Description_Lang_itIT Description_Lang_Unk "
    "Description_Lang_Mask "
    "AuraDescription_Lang_enUS AuraDescription_Lang_enGB AuraDescription_Lang_koKR "
    "AuraDescription_Lang_frFR AuraDescription_Lang_deDE AuraDescription_Lang_enCN "
    "AuraDescription_Lang_zhCN AuraDescription_Lang_enTW AuraDescription_Lang_zhTW "
    "AuraDescription_Lang_esES AuraDescription_Lang_esMX AuraDescription_Lang_ruRU "
    "AuraDescription_Lang_ptPT AuraDescription_Lang_ptBR AuraDescription_Lang_itIT "
    "AuraDescription_Lang_Unk AuraDescription_Lang_Mask "
    "ManaCostPct StartRecoveryCategory StartRecoveryTime MaxTargetLevel SpellClassSet "
    "SpellClassMask_1 SpellClassMask_2 SpellClassMask_3 MaxTargets DefenseType PreventionType "
    "StanceBarOrder EffectChainAmplitude_1 EffectChainAmplitude_2 EffectChainAmplitude_3 "
    "MinFactionID MinReputation RequiredAuraVision RequiredTotemCategoryID_1 "
    "RequiredTotemCategoryID_2 RequiredAreasID SchoolMask RuneCostID SpellMissileID "
    "PowerDisplayID EffectBonusMultiplier_1 EffectBonusMultiplier_2 EffectBonusMultiplier_3 "
    "SpellDescriptionVariableID SpellDifficultyID").split()
assert len(SPELL_DBC_COLUMNS) == 234, len(SPELL_DBC_COLUMNS)

# ---- effects and auras (SharedDefines.h) -------------------------------------
E_SCHOOL_DAMAGE = 2
E_APPLY_AURA = 6
E_HEALTH_LEECH = 9
E_HEAL = 10                             # unused since holy leeches instead
E_WEAPON_DAMAGE_NOSCHOOL = 17
E_WEAPON_PERCENT_DAMAGE = 31
E_WEAPON_DAMAGE = 58
E_ADD_COMBO_POINTS = 80
E_NORMALIZED_WEAPON_DMG = 121
WEAPON_EFFECTS = {E_WEAPON_DAMAGE_NOSCHOOL, E_WEAPON_PERCENT_DAMAGE,
                  E_WEAPON_DAMAGE, E_NORMALIZED_WEAPON_DMG}
A_PERIODIC_DAMAGE = 3
A_MOD_DECREASE_SPEED = 33
A_MOD_HEALING_PCT = 118
A_MOD_MELEE_HASTE = 138
TARGET_UNIT_CASTER = 1
TARGET_UNIT_TARGET_ENEMY = 6
ATTR0_PASSIVE = 0x40
ATTR2_AUTOREPEAT = 0x20
SKILL_CATEGORY_CLASS = 7
DURATION_6S, DURATION_12S = 32, 29     # SpellDuration.dbc indices, verified

# ---- the elements --------------------------------------------------------------
# The elemental slot -- the second of the three -- is what makes an element an
# element, and every element gets one.
#
# It used to hold a flat elemental hit for everybody, and the element's own
# signature only when a THIRD slot happened to be free. On 97 of the 155 bases
# it is not free (Sinister Strike's combo point, Mortal Strike's wound, every
# combo builder), so six of the seven elements collapsed into the same spell in
# different colours: 85% weapon damage plus the same small hit, and nothing to
# tell Fiery Sinister Strike from Shadow Sinister Strike but the damage school.
#
# The signature IS the elemental slot now. Nothing is dropped, no element needs
# a slot that is already spoken for, and the seven read as seven things:
#
#   ("hit",)                                 a flat elemental hit; `add_mult`
#                                            makes it bigger (arcane)
#   ("leech", share)                         that hit, and it heals the caster
#                                            for `share` of the WHOLE strike
#   ("dot", amplitude_ms, duration_index)    DOT_MULT x that hit, over the ticks
#   ("aura", aura, points, misc, duration)   a debuff, and no damage at all
#
# A damage-over-time keeps the spell power the flat hit had: the coefficient
# below is split across the ticks, and the core reads it off the effect's own
# BonusMultiplier for a DOT exactly as it does for a direct hit.
DOT_MULT = 1.5          # a burn is worth more than the same number now: it can
                        # be dispelled, it can be outlived, and it arrives late

# A hit is part of the damage sentence: " ... as Fire damage plus 7 Fire
# damage." A burn or a snare is a sentence of its own, because {payload} sits
# mid-sentence in most templates and "causing X damage and poisons the target"
# does not agree with its own subject. The heal sentence works the same way.
HIT_TEXT = " plus $s2 {E} damage"

ELEMENTS = [
    dict(key="fire",   idx=1, prefix="Fiery",    school=4,  word="Fire",   kit=728,
         payload=("dot", 2000, DURATION_6S), coeff=None,
         text="Burns the target for $o2 {E} damage over $d.",
         hue=(255, 96, 24), glyph="flame"),
    dict(key="frost",  idx=2, prefix="Frozen",   school=16, word="Frost",  kit=4991,
         payload=("aura", A_MOD_DECREASE_SPEED, -31, 0, DURATION_6S), coeff=None,
         text="Slows the target's movement by $s2% for $d.",
         hue=(72, 196, 255), glyph="snowflake"),
    dict(key="earth",  idx=3, prefix="Earthen",  school=8,  word="Nature", kit=3055,
         payload=("aura", A_MOD_MELEE_HASTE, -11, 0, DURATION_6S), coeff=None,
         text="Increases the time between the target's attacks by $s2% for $d.",
         hue=(150, 100, 30), glyph="boulder"),
    dict(key="poison", idx=4, prefix="Venomous", school=8,  word="Nature", kit=3031,
         payload=("dot", 3000, DURATION_12S), coeff=None,
         text="Poisons the target for $o2 {E} damage over $d.",
         hue=(110, 255, 60), glyph="drop"),
    # Arcane's identity is the raw number: no debuff, a hit half again as big.
    dict(key="arcane", idx=5, prefix="Arcane",   school=64, word="Arcane", kit=1005,
         payload=("hit",), coeff=None, add_mult=1.5, text=HIT_TEXT,
         hue=(255, 72, 232), glyph="star"),
    dict(key="shadow", idx=6, prefix="Shadow",   school=32, word="Shadow", kit=6898,
         payload=("aura", A_MOD_HEALING_PCT, -21, 127, DURATION_6S), coeff=None,
         text="Reduces the effectiveness of healing on the target by $s2% for $d.",
         hue=(72, 36, 130), glyph="crescent"),
    # Holy's is sustain, and it costs no slot: the hit is a HEALTH_LEECH, so the
    # heal rides on the damage the whole strike lands. The core reads the share
    # off EffectValueMultiplier (Spell.cpp, "xinef: health leech handling"), so
    # a zero there would heal nothing. 25% is what the extra 10% of weapon
    # damage holy gives up -- nothing resists it -- buys back.
    dict(key="holy",   idx=7, prefix="Holy",     school=2,  word="Holy",   kit=6359,
         payload=("leech", 0.25), coeff=75, text=HIT_TEXT,
         hue=(255, 210, 84), glyph="sun"),
]
ELEMENT_BY_KEY = {e["key"]: e for e in ELEMENTS}

# ---- DBC reading ---------------------------------------------------------------


class Dbc:
    def __init__(self, path):
        self.blob = open(path, "rb").read()
        magic, self.rows, self.fields, self.rec, self.strsize = struct.unpack_from("<4sIIII", self.blob, 0)
        if magic != b"WDBC":
            sys.exit("%s is not a WDBC file" % path)
        self.body = 20
        self.strings = self.blob[self.body + self.rows * self.rec:]
        self.index = {struct.unpack_from("<I", self.blob, self.body + i * self.rec)[0]: i
                      for i in range(self.rows)}

    def raw(self, row, field, fmt="<I"):
        return struct.unpack_from(fmt, self.blob, self.body + row * self.rec + field * 4)[0]

    def u(self, row, field):
        return self.raw(row, field, "<I")

    def i(self, row, field):
        return self.raw(row, field, "<i")

    def f(self, row, field):
        return self.raw(row, field, "<f")

    def s(self, row, field):
        off = self.u(row, field)
        end = self.strings.find(b"\0", off)
        return self.strings[off:end].decode("utf-8", "replace") if end >= 0 else ""

    def row_of(self, ident):
        return self.index.get(ident)


def spell_values(spell, row):
    """The 234 fields of one Spell.dbc row, typed; strings resolved to text."""
    out = []
    for fld in range(234):
        if fld in STRING_FIELDS:
            out.append(spell.s(row, fld))
        elif fld in FLOAT_FIELDS:
            out.append(spell.f(row, fld))
        elif fld in SIGNED_FIELDS:
            out.append(spell.i(row, fld))
        else:
            out.append(spell.u(row, fld))
    return out


# ---- candidate discovery: mirror BuildLibrary's pool filters -------------------


def candidates(spell, sla, skill, talent):
    """name -> [rank spell ids], for every Physical weapon-damage class ability
    the module's pool would contain. Plus the full sorted base list, used for
    stable id allocation."""
    class_lines = {skill.u(r, 0) for r in range(skill.rows) if skill.u(r, 1) == SKILL_CATEGORY_CLASS}
    talent_spells = set()
    for r in range(talent.rows):
        for k in range(4, 9):
            v = talent.u(r, k)
            if v:
                talent_spells.add(v)

    pool = {}
    for r in range(sla.rows):
        line, sp, race, cls = sla.u(r, 1), sla.u(r, 2), sla.u(r, 3), sla.u(r, 4)
        if line in class_lines and cls and not race:
            pool[sp] = r
    triggered = set()
    for sp in pool:
        row = spell.row_of(sp)
        if row is None:
            continue
        for e in range(3):
            t = spell.u(row, F["EffectTriggerSpell"] + e)
            if t:
                triggered.add(t)

    groups = defaultdict(list)
    for sp, slarow in pool.items():
        row = spell.row_of(sp)
        if row is None or sp in triggered or sp in talent_spells:
            continue
        if spell.u(row, F["Attributes"]) & ATTR0_PASSIVE:
            continue
        if spell.u(row, 6) & ATTR2_AUTOREPEAT:          # Auto Shot and kin
            continue
        if not (spell.u(row, F["SpellLevel"]) or spell.u(row, F["BaseLevel"])):
            continue                                     # unlearnable level-0 lines
        # A strike that costs nothing (no mana/rage/energy, no percentage, no
        # runes) is a script-fired proc, not a button: Sweeping Strikes' extra
        # hit, Stormstrike's weapon hits. EffectTriggerSpell cannot see the
        # ones a dummy aura fires from C++, so this catches them.
        if not (spell.u(row, 42) or spell.u(row, 204) or spell.u(row, 226)):
            continue
        if spell.u(row, F["SchoolMask"]) != 1:
            continue
        effs = {spell.u(row, F["Effect"] + e) for e in range(3)}
        if not effs & WEAPON_EFFECTS:
            continue
        groups[spell.s(row, F["SpellName"])].append(sp)

    for name in groups:
        groups[name].sort(key=lambda s: (spell.u(spell.row_of(s), F["SpellLevel"]), s))
    ordered = sorted(groups, key=lambda n: groups[n][0])
    return groups, ordered, pool


# ---- variant construction -----------------------------------------------------


# ---- text: each base's own description, modified for the element ---------------
# Slot 1 is always the weapon percent, slot 2 the element's own payload, slot 3
# the base's own extra effect (combo points, a wound) when it has one.
# {E} is the element word and {payload} the clause for whatever that element
# put in slot 2 -- a flat hit, a burn, a snare. Tokens follow the client's
# tooltip grammar: $s1 the value of slot 1, $o2 the total periodic damage of
# slot 2, $d the duration, $x1 chain targets. A negative aura value prints
# without its sign, the way Frostbolt's -41 reads as 40%.
DESCRIPTIONS = {
    "Backstab": "Backstab the target, causing $s1% weapon damage as {E} damage{payload}.  Must be behind the target.  Requires a dagger in the main hand.  Awards $s3 combo $lpoint:points;.",
    "Heroic Strike": "A strong attack that deals $s1% weapon damage as {E} damage{payload} and causes a high amount of threat.",
    "Cleave": "A sweeping attack that deals $s1% weapon damage as {E} damage to the target and its $?s58366[two nearest allies][nearest ally]{payload}.",
    "Claw": "Claw the enemy, causing $s1% weapon damage as {E} damage{payload}.  Awards $s3 combo $lpoint:points;.",
    "Whirlwind": "In a whirlwind of steel you attack up to $i enemies within $a1 yards, causing $s1% weapon damage as {E} damage to each enemy{payload}.",
    "Sinister Strike": "An instant strike that causes $s1% of your normal weapon damage, dealt as {E} damage{payload}.  Awards $s3 combo $lpoint:points;.",
    "Multi-Shot": "Fires several missiles, hitting $x1 targets for $s1% weapon damage as {E} damage{payload}.",
    "Raptor Strike": "A strong attack that deals $s1% weapon damage as {E} damage{payload}.",
    "Shred": "Shred the target, causing $s1% weapon damage as {E} damage{payload}.  Must be behind the target.  Awards $s3 combo $lpoint:points;.",
    "Ravage": "Ravage the target, causing $s1% weapon damage as {E} damage{payload}.  Must be prowling and behind the target.  Awards $s3 combo $lpoint:points;.",
    "Maul": "A strong attack that deals $s1% weapon damage as {E} damage{payload} and causes a high amount of threat.",
    "Overpower": "Instantly overpower the enemy, causing $s1% weapon damage as {E} damage{payload}.  Only useable after the target dodges.  The Overpower cannot be blocked, dodged or parried.",
    "Ambush": "Ambush the target, causing $s1% weapon damage as {E} damage{payload}.  Must be stealthed and behind the target.  Requires a dagger in the main hand.  Awards $s3 combo $lpoint:points;.",
    "Hemorrhage": "An instant strike that deals $s1% weapon damage as {E} damage{payload} and causes the target to hemorrhage, increasing any Physical damage dealt to the target by up to $s3.  Lasts $n charges or $d.  Awards 1 combo point.",
    "Mortal Strike": "A vicious strike that deals $s1% weapon damage as {E} damage{payload} and wounds the target, reducing the effectiveness of any healing by $s3% for $d.",
    "Maim": "Finishing move that deals $s1% weapon damage as {E} damage{payload} and stuns the target for 1 sec per combo point.  Non-player victim spellcasting is also interrupted for $32747d.",
    "Aimed Shot": "An aimed shot that deals $s1% weapon damage as {E} damage{payload} and reduces healing done to that target by $s3%.  Lasts $d.",
    "Devastate": "Sunder the target's armor causing the Sunder Armor effect.  In addition, deals $s1% weapon damage as {E} damage for each application of Sunder Armor on the target{payload}.  The Sunder Armor effect can stack up to $u times.",
    "Mangle (Cat)": "Mangle the target for $s1% weapon damage as {E} damage{payload} and causes the target to take $s3% additional damage from bleed effects for $d.  Awards $34071s1 combo $lpoint:points;.",
    "Mangle (Bear)": "Mangle the target for $s1% weapon damage as {E} damage{payload} and causes the target to take $s3% additional damage from bleed effects for $d.",
    "Plague Strike": "A vicious strike that deals $s1% weapon damage as {E} damage{payload} and infects the target with Blood Plague, a disease dealing Shadow damage over time.",
    "Blood Strike": "Instantly strike the enemy, causing $s1% weapon damage as {E} damage{payload}, total damage increased by ${$m3/2}.1% for each of your diseases on the target.",
    "Obliterate": "A brutal instant attack that deals $s1% weapon damage as {E} damage{payload}, total damage increased ${$m3/2}.1% per each of your diseases on the target, but consumes the diseases.",
    "Death Strike": "A deadly attack that deals $s1% weapon damage as {E} damage{payload}, total damage increased for each of your diseases on the target.",
    "Fan of Knives": "Instantly throw both weapons at all targets within $a1 yards, causing $s1% weapon damage as {E} damage{payload}.",
    "Kill Shot": "You attempt to finish the wounded target off, firing a long range attack dealing $s1% weapon damage as {E} damage{payload}.  Kill Shot can only be used on enemies that have 20% or less health.",
    "Swipe (Cat)": "Swipe nearby enemies, inflicting $s1% weapon damage as {E} damage{payload}.",
}


def check_tokens(desc, slots, duration):
    """Every $s/$m/$o/$x/$a token must point at a filled slot, and $d at a
    duration; returns the first token that does not, else ''."""
    import re as _re
    for m in _re.finditer(r"\$[smoxa]([1-3])", desc):
        if slots[int(m.group(1)) - 1] is None:
            return m.group(0)
    if "$d" in desc and not duration:
        return "$d"
    return ""


def build_variant(spell, sla, icon, visual, durations, base_id, base_index, rank_index,
                  elem, first_variant_id, coeff_pct, sp_coeff):
    row = spell.row_of(base_id)
    vals = spell_values(spell, row)
    base_name = vals[F["SpellName"]]

    # A variant is the base's row with slots rewritten, so anything not touched
    # is inherited. No base carries a class tool today -- they are all weapon
    # strikes -- but inheriting one would be silent and fatal: the server
    # clears the column at startup, while the client patch's tool sweep runs
    # over class spells BEFORE these rows are appended and never reaches them,
    # so the client would draw a red "Tools:" line and refuse the cast itself.
    # That is exactly what happened to the forged totems. Zeroed here so it
    # cannot depend on which spells someone picks as bases later; test_elemental
    # checks the written rows.
    for _tool in (50, 51, 222, 223):   # Totem[2], RequiredTotemCategoryID[2]
        vals[_tool] = 0
    lvl = vals[F["SpellLevel"]] or vals[F["BaseLevel"]] or 1

    # -- pull the base's effects apart
    weapon, other = [], []
    flat_add = 0
    base_pct = 100          # the base's own weapon multiplier (Ambush 275%, Blood Strike 40%)
    for e in range(3):
        eff = vals[F["Effect"] + e]
        if not eff:
            # Blood Strike keeps its per-disease bonus in a slot with no effect
            # type at all; the core reads Effects[2].BasePoints for it, so the
            # slot must survive as it is.
            if vals[F["EffectBasePoints"] + e]:
                other.append(e)
            continue
        if eff in WEAPON_EFFECTS:
            weapon.append(e)
            if eff in (E_WEAPON_DAMAGE, E_NORMALIZED_WEAPON_DMG, E_WEAPON_DAMAGE_NOSCHOOL):
                flat_add += vals[F["EffectBasePoints"] + e] + max(1, vals[F["EffectDieSides"] + e])
            elif eff == E_WEAPON_PERCENT_DAMAGE:
                base_pct = base_pct * (vals[F["EffectBasePoints"] + e] + 1) // 100
        else:
            other.append(e)
    if not weapon:
        return None, "no weapon effect"
    if len(other) > 1:
        return None, "two non-weapon effects leave no room for the element"
    if base_name not in DESCRIPTIONS:
        return None, "no description template for this base"

    # The kept share applies to the base's own multiplier, so Fiery Ambush is
    # 85% of Ambush's 275%, not a flat 85% that would gut it.
    keep = coeff_pct if elem["coeff"] is None else elem["coeff"]
    coeff = max(1, int(round(base_pct * keep / 100.0)))
    add_value = int(round((flat_add + 3 + lvl * 0.6) * elem.get("add_mult", 1.0)))

    # -- lay the three slots out: weapon %, the element, [the base's own]
    # The base's own targeting for its weapon hit: a single enemy for a
    # strike, an area for Whirlwind, a chain for Cleave. The percent hit, the
    # the element's hit, burn or debuff all use it, so an area strike stays
    # an area strike as a variant.
    w0 = weapon[0]
    hit_target = dict(TargetA=vals[F["EffectImplicitTargetA"] + w0],
                      TargetB=vals[F["EffectImplicitTargetB"] + w0],
                      Radius=vals[F["EffectRadiusIndex"] + w0],
                      Chain=vals[F["EffectChainTarget"] + w0])
    slots = []                        # list of dicts: effect fields for one slot
    slots.append(dict(Effect=E_WEAPON_PERCENT_DAMAGE, BasePoints=coeff - 1, DieSides=1,
                      Aura=0, Amplitude=0, Misc=0, MiscB=0, Trigger=0, Bonus=0.0,
                      RealPerLevel=0.0, Mechanic=0, ValueMult=0.0, **hit_target))

    # -- slot 2: the element's own payload
    #
    # A spell carries ONE duration, so a burn or a snare has to live inside
    # whatever the base's own effect already reserved. Almost every base
    # reserves nothing and the element sets its own -- but Overpower's is 1ms,
    # Maim's is 0 until combo points are spent, and Mangle's is a minute. A
    # burn that cannot tick and a snare that lasts a minute are both worse than
    # no element at all, so those fall back to the flat hit, which is exactly
    # what they have always had.
    payload = elem["payload"]
    kind = payload[0]
    fell_back = ""
    duration = vals[F["DurationIndex"]]
    if kind in ("dot", "aura"):
        want = payload[2] if kind == "dot" else payload[4]
        aura = A_PERIODIC_DAMAGE if kind == "dot" else payload[1]
        if any(vals[F["EffectApplyAuraName"] + e] == aura for e in other):
            # Mortal Strike and Aimed Shot already cut healing; a Shadow one
            # would carry the same aura twice and say so twice.
            kind, fell_back = "hit", "flat hit: the base already applies this aura itself"
        elif not duration:
            duration = want
        elif not (durations.get(want, 0) <= durations.get(duration, 0) <= 3 * durations.get(want, 0)):
            kind = "hit"
            fell_back = ("flat hit: the base's own effect holds the spell at %d ms, and the "
                         "element needs %d" % (durations.get(duration, 0), durations.get(want, 0)))

    if kind == "dot":
        amp = payload[1]
        ticks = max(1, durations.get(duration, 0) // amp)
        # DOT_MULT x the flat hit, spread evenly, and the spell power split the
        # same way so a burn and a hit of the same size scale alike
        slots.append(dict(Effect=E_APPLY_AURA, Aura=A_PERIODIC_DAMAGE,
                          BasePoints=max(1, int(round(add_value * DOT_MULT / ticks))) - 1,
                          DieSides=1, Amplitude=amp, Misc=0, MiscB=0, Trigger=0,
                          Bonus=sp_coeff * DOT_MULT / ticks, RealPerLevel=0.0,
                          Mechanic=0, ValueMult=0.0, **hit_target))
    elif kind == "aura":
        # control instead of damage: the strike keeps its weapon share and
        # spends the elemental slot on the debuff
        slots.append(dict(Effect=E_APPLY_AURA, Aura=payload[1], BasePoints=payload[2],
                          DieSides=1, Amplitude=0, Misc=payload[3], MiscB=0, Trigger=0,
                          Bonus=0.0, RealPerLevel=0.0, Mechanic=0, ValueMult=0.0,
                          **hit_target))
    else:
        leech = payload[1] if kind == "leech" else 0.0
        slots.append(dict(Effect=E_HEALTH_LEECH if leech else E_SCHOOL_DAMAGE,
                          BasePoints=add_value - 1, DieSides=1, Aura=0, Amplitude=0,
                          Misc=0, MiscB=0, Trigger=0, Bonus=sp_coeff, RealPerLevel=0.0,
                          Mechanic=0, ValueMult=float(leech), **hit_target))

    for e in other:
        slots.append(dict(Effect=vals[F["Effect"] + e], BasePoints=vals[F["EffectBasePoints"] + e],
                          DieSides=vals[F["EffectDieSides"] + e],
                          TargetA=vals[F["EffectImplicitTargetA"] + e],
                          TargetB=vals[F["EffectImplicitTargetB"] + e],
                          Aura=vals[F["EffectApplyAuraName"] + e],
                          Amplitude=vals[F["EffectAmplitude"] + e],
                          Misc=vals[F["EffectMiscValue"] + e], MiscB=vals[F["EffectMiscValueB"] + e],
                          Trigger=vals[F["EffectTriggerSpell"] + e],
                          Bonus=vals[F["EffectBonusMultiplier"] + e],
                          RealPerLevel=vals[F["EffectRealPointsPerLevel"] + e],
                          Mechanic=vals[F["EffectMechanic"] + e],
                          ValueMult=vals[F["EffectValueMultiplier"] + e],
                          Radius=vals[F["EffectRadiusIndex"] + e],
                          Chain=vals[F["EffectChainTarget"] + e],
                          copied_from=e))
    while len(slots) < 3:
        slots.append(None)

    # -- write the row: start from the base, override what changes
    new = list(vals)
    overrides = {}

    def setf(field, value):
        new[field] = value
        overrides[field] = value

    setf(F["Id"], first_variant_id + rank_index)
    setf(F["SchoolMask"], elem["school"])
    setf(F["DurationIndex"], duration)
    for e in range(3):
        sl = slots[e]
        keys = [("Effect", "Effect"), ("EffectBasePoints", "BasePoints"),
                ("EffectDieSides", "DieSides"), ("EffectImplicitTargetA", "TargetA"),
                ("EffectImplicitTargetB", "TargetB"), ("EffectApplyAuraName", "Aura"),
                ("EffectAmplitude", "Amplitude"), ("EffectMiscValue", "Misc"),
                ("EffectMiscValueB", "MiscB"), ("EffectTriggerSpell", "Trigger"),
                ("EffectBonusMultiplier", "Bonus"), ("EffectRealPointsPerLevel", "RealPerLevel"),
                ("EffectMechanic", "Mechanic"), ("EffectRadiusIndex", "Radius"),
                ("EffectValueMultiplier", "ValueMult"), ("EffectChainTarget", "Chain")]
        for fname, key in keys:
            setf(F[fname] + e, sl[key] if sl else (0.0 if F[fname] + e in FLOAT_FIELDS else 0))
        # spell class masks and combo scaling of a copied effect follow it; a
        # fresh slot gets none
        src = sl.get("copied_from") if sl else None
        for k in range(3):
            setf(F["EffectSpellClassMask"] + e * 3 + k,
                 vals[F["EffectSpellClassMask"] + src * 3 + k] if src is not None else 0)
        setf(F["EffectPointsPerComboPoint"] + e,
             vals[F["EffectPointsPerComboPoint"] + src] if src is not None else 0.0)
    # a variant's text is generated; the base's description variable no longer applies
    setf(F["SpellDescriptionVariableID"], 0)

    # -- text
    name = "%s %s" % (elem["prefix"], base_name)
    rank_text = vals[F["Rank"]]
    word = elem["word"]
    # What actually went into slot 2 -- the element's own, unless the base
    # pushed it back to a flat hit. A hit joins the damage sentence; anything
    # else follows as one of its own.
    inline = HIT_TEXT if kind in ("hit", "leech") else ""
    desc = DESCRIPTIONS[base_name].replace("{E}", word)                                   .replace("{payload}", inline.replace("{E}", word))
    if kind in ("dot", "aura"):
        desc += "  " + elem["text"].replace("{E}", word)
    elif kind == "leech":
        desc += "  Heals you for %d%% of the damage dealt." % round(payload[1] * 100)
    bad = check_tokens(desc, slots, duration)
    if bad:
        return None, "description token %s has nothing behind it" % bad

    # -- visual: base row with the element's impact kit
    base_visual = vals[F["SpellVisual"]]
    visual_id = VISUAL_BASE + (base_index * 7 + elem["idx"] - 1) * 16 + rank_index
    setf(F["SpellVisual"], visual_id)

    # -- icon: one per (base icon, element); ranks share it
    base_icon = vals[F["SpellIconID"]]
    icon_row = icon.row_of(base_icon)
    base_icon_path = icon.s(icon_row, 1) if icon_row is not None else ""
    icon_id = ICON_BASE + base_index * 7 + elem["idx"] - 1
    setf(F["SpellIconID"], icon_id)

    # -- skill line ability: the base's row with the variant's spell
    sla_row = None
    for r in range(sla.rows):
        if sla.u(r, 2) == base_id and sla.u(r, 4):
            sla_row = r
            break
    sla_fields = [sla.u(sla_row, k) for k in range(14)] if sla_row is not None else None
    sla_id = SLA_BASE + (base_index * 7 + elem["idx"] - 1) * 16 + rank_index
    if sla_fields:
        sla_fields[0] = sla_id
        sla_fields[2] = first_variant_id + rank_index
        # AcquireMethod is set, not copied. 1 and 2 mean the core hands the
        # spell over with the skill line itself, which is what every class's
        # starting strike says -- Heroic Strike, Sinister Strike, Raptor
        # Strike, Plague Strike, Blood Strike. Copied onto a variant it makes
        # the variant a free class spell, and the server reads it as a trained
        # ability rather than a variant, so it is rated from its own power
        # instead of one tier above its base. A variant is rolled for: 0.
        sla_fields[9] = 0

    lost = fell_back
    return dict(id=first_variant_id + rank_index, first=first_variant_id, base=base_id,
                base_name=base_name, element=elem["key"], rank=rank_index + 1,
                name=name, rank_text=rank_text, description=desc, values=new,
                overrides=overrides, visual=dict(id=visual_id, base=base_visual, impact_kit=elem["kit"]),
                icon=dict(id=icon_id, base_icon=base_icon, base_path=base_icon_path,
                          element=elem["key"], hue=elem["hue"], glyph=elem["glyph"]),
                sla=sla_fields, sla_id=sla_id, note=lost), None


# ---- output --------------------------------------------------------------------


def sql_literal(v):
    if isinstance(v, str):
        return "'" + v.replace("\\", "\\\\").replace("'", "''") + "'"
    if isinstance(v, float):
        return repr(v)
    return str(v)


def generation_id(variants):
    """Twelve hex digits over every field the server deals and the client shows.
    Written into both outputs by the same run, so a server and a client from
    different runs can be told apart by comparing two strings."""
    h = hashlib.sha1()
    for v in sorted(variants, key=lambda x: x["id"]):
        h.update(json.dumps([v["id"], v["name"], v["rank_text"], v["description"],
                             v["values"], v["visual"], v["icon"]["id"], v["sla"]],
                            sort_keys=True, default=str).encode("utf-8"))
    return h.hexdigest()[:12]


def write_sql(variants, path, run_desc):
    L = []
    L.append("-- mod-classless-wildcard: elemental ability variants (GENERATED)")
    L.append("--")
    L.append("-- Do not hand-edit: regenerate with data/sql/generators/gen_elemental_variants.py.")
    L.append("--")
    L.append("-- Every physical strike in the pool dealt as an element instead: the same")
    L.append("-- swing, cost and cooldown, at a reduced weapon coefficient, with the element's")
    L.append("-- own signature in the second effect slot: a hit that scales with spell power,")
    L.append("-- a burn, a poison, a snare, an attack-speed cut, a healing cut or lifesteal.")
    L.append("-- The shape is Frost Strike's. Design and every id block")
    L.append("-- are in PLAN-elemental-variants.md.")
    L.append("--")
    L.append("-- The client patch appends the SAME rows to the player's Spell.dbc from")
    L.append("-- client-patch/elemental_manifest.json, written by the same run of the")
    L.append("-- generator, so what the server deals and what the tooltip shows agree.")
    L.append("--")
    L.append("-- This run: %s" % run_desc)
    L.append("-- Generation: %s (the client manifest from the same run carries the same id)" % generation_id(variants))
    L.append("")
    L.append("CREATE TABLE IF NOT EXISTS `cw_ability_variants` (")
    L.append("  `variant_first_spell` INT UNSIGNED NOT NULL COMMENT 'rank 1 of the variant line',")
    L.append("  `base_first_spell`    INT UNSIGNED NOT NULL COMMENT 'rank 1 of the ability it varies',")
    L.append("  `element`             TINYINT UNSIGNED NOT NULL COMMENT '1 fire 2 frost 3 earth 4 poison 5 arcane 6 shadow 7 holy',")
    L.append("  `enabled`             TINYINT UNSIGNED NOT NULL DEFAULT 1,")
    L.append("  PRIMARY KEY (`variant_first_spell`)")
    L.append(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Classless elemental ability variants';")
    L.append("")
    L.append("CREATE TABLE IF NOT EXISTS `cw_ability_variants_meta` (")
    L.append("  `key`   VARCHAR(32) NOT NULL,")
    L.append("  `value` VARCHAR(64) NOT NULL,")
    L.append("  PRIMARY KEY (`key`)")
    L.append(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Which generator run the variant rows came from';")
    L.append("REPLACE INTO `cw_ability_variants_meta` (`key`, `value`) VALUES ('generation', '%s');" % generation_id(variants))
    L.append("")
    lo, hi = SPELL_BASE, SPELL_BLOCK_END
    L.append("DELETE FROM `spell_dbc` WHERE `ID` BETWEEN %d AND %d;" % (lo, hi))
    L.append("DELETE FROM `skilllineability_dbc` WHERE `Spell` BETWEEN %d AND %d;" % (lo, hi))
    L.append("DELETE FROM `spell_ranks` WHERE `first_spell_id` BETWEEN %d AND %d;" % (lo, hi))
    L.append("DELETE FROM `cw_ability_variants` WHERE `variant_first_spell` BETWEEN %d AND %d;" % (lo, hi))
    L.append("")

    L.append("INSERT INTO `spell_dbc` (%s) VALUES" % ", ".join("`%s`" % c for c in SPELL_DBC_COLUMNS))
    for n, v in enumerate(variants):
        vals = list(v["values"])
        # the DB holds text in enUS and leaves the other locales empty
        for first, mask in LOCALE_BLOCKS:
            for k in range(first + 1, mask):
                vals[k] = ""
        vals[F["SpellName"]] = v["name"]
        vals[F["Rank"]] = v["rank_text"]
        vals[F["Description"]] = v["description"]
        vals[F["ToolTip"]] = ""
        end = ";" if n == len(variants) - 1 else ","
        L.append("(%s)%s" % (", ".join(sql_literal(x) for x in vals), end))
    L.append("")

    withsla = [v for v in variants if v["sla"]]
    if withsla:
        L.append("INSERT INTO `skilllineability_dbc` (`ID`, `SkillLine`, `Spell`, `RaceMask`, `ClassMask`, "
                 "`ExcludeRace`, `ExcludeClass`, `MinSkillLineRank`, `SupercededBySpell`, `AcquireMethod`, "
                 "`TrivialSkillLineRankHigh`, `TrivialSkillLineRankLow`, `CharacterPoints_1`, `CharacterPoints_2`) VALUES")
        for n, v in enumerate(withsla):
            end = ";" if n == len(withsla) - 1 else ","
            L.append("(%s)%s" % (", ".join(str(x) for x in v["sla"]), end))
        L.append("")

    # A one-rank line is not a chain: SpellMgr::LoadSpellRanks logs
    # "There is only 1 spell rank for identifier ... entry is not needed!" for
    # each one at startup, and most of that wall of red was ours.
    _per_line = Counter(v["first"] for v in variants)
    chained = [v for v in variants if _per_line[v["first"]] > 1]
    L.append("INSERT INTO `spell_ranks` (`first_spell_id`, `spell_id`, `rank`) VALUES")
    for n, v in enumerate(chained):
        end = ";" if n == len(chained) - 1 else ","
        L.append("(%d, %d, %d)%s" % (v["first"], v["id"], v["rank"], end))
    L.append("")

    firsts = [v for v in variants if v["rank"] == 1]
    L.append("INSERT INTO `cw_ability_variants` (`variant_first_spell`, `base_first_spell`, `element`, `enabled`) VALUES")
    for n, v in enumerate(firsts):
        end = ";" if n == len(firsts) - 1 else ","
        L.append("(%d, %d, %d, 1)%s" % (v["first"], v["base_first"], ELEMENT_BY_KEY[v["element"]]["idx"], end))
    L.append("")
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(L))


def write_manifest(variants, path, run_desc):
    out = dict(version=1, run=run_desc, generation=generation_id(variants),
               spell_block=[SPELL_BASE, SPELL_BLOCK_END],
               elements=[dict(key=e["key"], idx=e["idx"], prefix=e["prefix"], school=e["school"],
                              impact_kit=e["kit"], hue=e["hue"], glyph=e["glyph"],
                              payload=e["payload"][0],
                              leech=(e["payload"][1] if e["payload"][0] == "leech" else 0.0))
                         for e in ELEMENTS],
               variants=[])
    for v in variants:
        out["variants"].append(dict(
            id=v["id"], first=v["first"], base=v["base"], element=v["element"], rank=v["rank"],
            name=v["name"], rank_text=v["rank_text"], description=v["description"],
            fields={str(k): val for k, val in v["overrides"].items()},
            visual=v["visual"], icon=v["icon"], sla=v["sla"], note=v["note"]))
    json.dump(out, open(path, "w", encoding="utf-8", newline="\n"), indent=1)


# ---- main ------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dbc", default=DEFAULT_DBC, help="directory of extracted 3.3.5a DBCs")
    ap.add_argument("--bases", default="ALL", help="comma-separated base ability names, or ALL")
    ap.add_argument("--elements", default="ALL", help="comma-separated element keys, or ALL")
    ap.add_argument("--ranks", default="all", choices=("first", "top", "all"))
    ap.add_argument("--coefficient", type=int, default=85, help="weapon damage kept, percent")
    ap.add_argument("--sp-coefficient", type=float, default=0.15, help="spell power coefficient of the add")
    ap.add_argument("--out-sql", default=OUT_SQL)
    ap.add_argument("--out-manifest", default=OUT_MANIFEST)
    args = ap.parse_args(argv)

    def dbc(name):
        p = os.path.join(args.dbc, name)
        if not os.path.exists(p):
            sys.exit("missing %s (extracted DBCs expected in %s)" % (name, args.dbc))
        return Dbc(p)

    spell, sla, skill, talent = dbc("Spell.dbc"), dbc("SkillLineAbility.dbc"), dbc("SkillLine.dbc"), dbc("Talent.dbc")
    icon, visual = dbc("SpellIcon.dbc"), dbc("SpellVisual.dbc")
    # index -> milliseconds. A spell has ONE duration, so the elemental slot
    # shares whatever the base's own effect already reserved, and this is how
    # the generator tells a usable one from Overpower's 1ms.
    span = dbc("SpellDuration.dbc")
    durations = {ident: span.i(row, 1) for ident, row in span.index.items()}
    if spell.fields != 234:
        sys.exit("Spell.dbc has %d fields; this generator understands the 234-field 3.3.5a layout" % spell.fields)

    groups, ordered, pool = candidates(spell, sla, skill, talent)
    print("pool: %d physical weapon-damage abilities eligible" % len(ordered))

    want_bases = ordered if args.bases.upper() == "ALL" else [b.strip() for b in args.bases.split(",")]
    for b in want_bases:
        if b not in groups:
            sys.exit("no eligible base named %r (eligible: %s)" % (b, ", ".join(ordered)))
    want_elems = ELEMENTS if args.elements.upper() == "ALL" else [ELEMENT_BY_KEY[k.strip()] for k in args.elements.split(",")]

    variants, skipped = [], []
    for base_name in want_bases:
        ranks = groups[base_name]
        base_index = ordered.index(base_name)
        if args.ranks == "first":
            chosen = [(0, ranks[0])]
        elif args.ranks == "top":
            chosen = [(len(ranks) - 1, ranks[-1])]
        else:
            chosen = list(enumerate(ranks))
        for elem in want_elems:
            first_id = SPELL_BASE + (base_index * 7 + elem["idx"] - 1) * 16
            line = []
            for rank_index, base_id in chosen:
                v, why = build_variant(spell, sla, icon, visual, durations, base_id,
                                       base_index, rank_index, elem, first_id,
                                       args.coefficient, args.sp_coefficient)
                if v is None:
                    skipped.append((base_name, elem["key"], why))
                    continue
                v["base_first"] = ranks[0]
                # a "top only" run is still a one-rank line: rank 1 at the top rank's level
                if args.ranks == "top":
                    v["id"] = v["first"]; v["values"][F["Id"]] = v["first"]
                    v["overrides"][F["Id"]] = v["first"]; v["rank"] = 1
                    if v["sla"]:
                        v["sla"][2] = v["first"]
                line.append(v)
            # SkillLineAbility's SupercededBySpell is what the spellbook uses
            # to hide a rank once a higher one is known. Copied from the base
            # it would point at the BASE's next rank, and learning Sinister
            # Strike rank 2 would hide Fiery Sinister Strike rank 1. Walk the
            # variant line instead; the top rank is superseded by nothing.
            for k, v in enumerate(line):
                if v["sla"]:
                    v["sla"][8] = line[k + 1]["id"] if k + 1 < len(line) else 0
            variants.extend(line)

    run_desc = "bases=%s elements=%s ranks=%s coefficient=%d spellpower=%.2f" % (
        args.bases, args.elements, args.ranks, args.coefficient, args.sp_coefficient)
    write_sql(variants, args.out_sql, run_desc)
    write_manifest(variants, args.out_manifest, run_desc)

    print("wrote %s" % os.path.normpath(args.out_sql))
    print("wrote %s" % os.path.normpath(args.out_manifest))
    print("  generation %s  (the server logs this at startup; the installer prints it)" % generation_id(variants))
    print("  %d variant spell rows from %d base(s) x %d element(s)" % (len(variants), len(want_bases), len(want_elems)))
    for b, e, why in sorted(set(skipped)):
        print("  skipped %s / %s: %s" % (b, e, why))
    by_reason = {}
    for v in variants:
        if v["note"]:
            by_reason.setdefault((v["base_name"], v["note"]), set()).add(v["element"])
    for (b, why), es in sorted(by_reason.items()):
        print("  %s: %s -> %s" % (b, ", ".join(sorted(es)), why))
    for v in variants[:8]:
        print("\n  %d  %s  (%s)  base %d %s" % (v["id"], v["name"], v["rank_text"], v["base"], v["base_name"]))
        for e in range(3):
            eff = v["values"][F["Effect"] + e]
            if eff:
                print("    effect%d type=%-3d base=%-5d dice=%d aura=%-3d amp=%-5d misc=%-4d target=%d bonus=%.2f"
                      % (e, eff, v["values"][F["EffectBasePoints"] + e], v["values"][F["EffectDieSides"] + e],
                         v["values"][F["EffectApplyAuraName"] + e], v["values"][F["EffectAmplitude"] + e],
                         v["values"][F["EffectMiscValue"] + e], v["values"][F["EffectImplicitTargetA"] + e],
                         v["values"][F["EffectBonusMultiplier"] + e]))
        print("    school=%d duration=%d visual=%d icon=%d (%s)" % (
            v["values"][F["SchoolMask"]], v["values"][F["DurationIndex"]],
            v["visual"]["id"], v["icon"]["id"], v["icon"]["base_path"]))
        print("    %s" % v["description"])
        if v["note"]:
            print("    NOTE %s" % v["note"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
