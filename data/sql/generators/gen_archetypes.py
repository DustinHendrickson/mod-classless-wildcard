#!/usr/bin/env python3
"""Author, validate and write the starter archetypes: full level 1 to 80 build
templates for the Classless path.

An archetype is a list of ability lines and talent ranks. A Hero who follows
one gets its abilities bought strictly in build order, each as soon as it is
unlocked and affordable, and each talent rank as soon as its tier,
prerequisite and Talent Essence allow, in list order. The
builds live in this file as spell and talent NAMES; the script resolves them
against the client's DBCs and the core's trainer data exactly the way the
module's BuildLibrary does, simulates a Hero following each build from 1 to
80 on the shipped essence schedule, refuses to write anything that would
stall, and emits ../db-world/cw_archetypes.sql.

Elemental variants ("Fiery Heroic Strike") are part of the pool too, read
from the client manifest the variant generator writes and registered the way
LoadVariants does: the base line's levels and class, one rarity tier up. A
build names them like any other ability, under the base attack's class.

Run:  python3 gen_archetypes.py                 validate + write the SQL
      python3 gen_archetypes.py --catalog Rogue  list what the pool offers a
                                                 class (abilities with unlock
                                                 level and cost, talents by
                                                 tier) to pick from
      python3 gen_archetypes.py --dbc DIR --core DIR --conf FILE --out FILE
                                --manifest client-patch/elemental_manifest.json

Needs the 3.3.5a DBC extract (Spell, SkillLine, SkillLineAbility, Talent,
TalentTab) and the core checkout for data/sql/base/db_world/trainer_spell.sql
and spell_ranks.sql.
"""

from __future__ import annotations

import argparse
import collections
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gen_elemental_variants import Dbc, F, DEFAULT_DBC  # noqa: E402
import gen_forged_spells as forged  # noqa: E402  the Hero line and its talents

MODULE = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir, os.pardir))
DEFAULT_CORE = os.path.abspath(os.path.join(MODULE, os.pardir, os.pardir))
DEFAULT_CONF = os.path.join(MODULE, "conf", "classless_wildcard.conf.dist")
OUT_SQL = os.path.join(HERE, os.pardir, "db-world", "cw_archetypes.sql")
DEFAULT_MANIFEST = os.path.join(MODULE, "client-patch", "elemental_manifest.json")

CLASS_BITS = {"Warrior": 1, "Paladin": 2, "Hunter": 4, "Rogue": 8, "Priest": 16,
              "Death Knight": 32, "Shaman": 64, "Mage": 128, "Warlock": 256, "Druid": 1024,
              # the Hero line: forged abilities and the Hero talent tab, named
              # ("Hero", "Hurl") and ("Hero", "Hero", "Sharpened", 3) in a build
              "Hero": forged.HERO_TAB_CLASSMASK}
SKILL_CATEGORY_CLASS = 7
ATTR0_PASSIVE = 0x40
ATTR2_AUTO_REPEAT = 0x20
F_ATTRIBUTES_EX2 = 6
F_ACQUIRE_METHOD = 9      # SkillLineAbility.dbc column
UTILITY_EFFECTS = {25, 60, 40, 39, 47, 118, 78}   # weapon, proficiency, dual wield, language, trade skill, skill, attack
E_LEARN_SPELL = 36
# Kept out of the pool by cw_ability_override in cw_world_base.sql: they arrive
# with Tame Beast through cw_form_kits and are useless without it, so a build
# must not try to buy one.
POOL_DISABLED = {883, 982, 6991, 2641}
MAX_TALENT_RANK = 5
RARITY_NAMES = ["common", "uncommon", "rare", "epic", "legendary"]


def rarity_from_level(level):
    if level < 10: return 0
    if level < 25: return 1
    if level < 45: return 2
    if level < 60: return 3
    return 4


# =============================================================================
# the builds
# =============================================================================
# abilities: (class, ability name); the server buys them strictly in this
# order (after sorting by unlock level), so put the ones that matter most at a
# level first. talents: (class, tab, talent, rank) in strict purchase order;
# write them tier by tier.

BUILDS = [
    # ---- two classes fused around one or two elements, and the Hero line ------
    dict(id=1, name="Cinderblade",
         description="Warrior and mage in one blade: fiery strikes and cleaves, fireballs between swings, a signal fire on the field.",
         abilities=[
             ("Warrior", "Fiery Heroic Strike"), ("Mage", "Fireball"), ("Warrior", "Charge"), ("Mage", "Fire Blast"),
             ("Warrior", "Hamstring"), ("Hero", "Emberfeed"), ("Warrior", "Fiery Overpower"), ("Hero", "Crossdraw"),
             ("Mage", "Flamestrike"), ("Warrior", "Fiery Cleave"), ("Mage", "Pyroblast"), ("Mage", "Scorch"),
             ("Hero", "Signal Fire"), ("Mage", "Blast Wave"), ("Hero", "Vanguard Rush"), ("Warrior", "Fiery Whirlwind"),
             ("Warrior", "Fiery Mortal Strike"), ("Mage", "Dragon's Breath"), ("Mage", "Living Bomb"),
             ("Mage", "Molten Armor"),
             ("Mage", "Mirror Image"), ("Warrior", "Heroic Throw"),
         ],
         talents=[
             ("Mage", "Fire", "Improved Fire Blast", 2), ("Mage", "Fire", "Incineration", 3),
             ("Mage", "Fire", "Improved Fireball", 5), ("Mage", "Fire", "Ignite", 5), ("Mage", "Fire", "World in Flames", 3),
             ("Mage", "Fire", "Impact", 3), ("Mage", "Fire", "Burning Soul", 2), ("Mage", "Fire", "Improved Scorch", 3),
             ("Mage", "Fire", "Master of Elements", 3), ("Mage", "Fire", "Critical Mass", 3), ("Mage", "Fire", "Fire Power", 5),
             ("Mage", "Fire", "Pyromaniac", 3), ("Mage", "Fire", "Combustion", 1), ("Mage", "Fire", "Molten Fury", 2),
             ("Mage", "Fire", "Empowered Fire", 3), ("Mage", "Fire", "Hot Streak", 3),
             ("Warrior", "Arms", "Improved Heroic Strike", 3), ("Warrior", "Arms", "Tactical Mastery", 3),
             ("Warrior", "Arms", "Improved Charge", 2), ("Warrior", "Arms", "Anger Management", 1),
             ("Warrior", "Arms", "Impale", 2), ("Warrior", "Arms", "Deep Wounds", 3),
             ("Hero", "Hero", "Sharpened", 3), ("Hero", "Hero", "Two Schools", 5),
         ]),
    dict(id=2, name="Frostfire Duelist",
         description="Rogue and mage, fire in one hand and frost in the other: burning and freezing strikes, Antipode Blast to land both at once.",
         abilities=[
             ("Rogue", "Fiery Sinister Strike"), ("Rogue", "Eviscerate"), ("Mage", "Frostbolt"),
             ("Rogue", "Frozen Backstab"), ("Mage", "Fire Blast"), ("Rogue", "Gouge"), ("Rogue", "Evasion"),
             ("Mage", "Frost Nova"), ("Rogue", "Kick"),
             ("Hero", "Crossdraw"), ("Mage", "Blink"), ("Rogue", "Fiery Ambush"), ("Rogue", "Rupture"),
             ("Hero", "Antipode Blast"), ("Mage", "Cone of Cold"), ("Rogue", "Frozen Hemorrhage"),
             ("Hero", "Vertigo"), ("Mage", "Dragon's Breath"),
             ("Mage", "Ice Lance"), ("Rogue", "Cloak of Shadows"), ("Mage", "Frostfire Bolt"),
             ("Rogue", "Frozen Fan of Knives"),
         ],
         talents=[
             ("Rogue", "Combat", "Improved Sinister Strike", 2), ("Rogue", "Combat", "Dual Wield Specialization", 5),
             ("Rogue", "Combat", "Precision", 5), ("Rogue", "Combat", "Endurance", 2),
             ("Rogue", "Combat", "Lightning Reflexes", 3), ("Rogue", "Combat", "Aggression", 5),
             ("Rogue", "Combat", "Blade Flurry", 1), ("Rogue", "Combat", "Weapon Expertise", 2),
             ("Rogue", "Combat", "Adrenaline Rush", 1), ("Rogue", "Combat", "Combat Potency", 5),
             ("Mage", "Frost", "Frostbite", 3), ("Mage", "Frost", "Improved Frostbolt", 5), ("Mage", "Frost", "Ice Shards", 3),
             ("Mage", "Frost", "Precision", 3), ("Mage", "Frost", "Piercing Ice", 3), ("Mage", "Frost", "Icy Veins", 1),
             ("Mage", "Frost", "Shatter", 3), ("Mage", "Frost", "Improved Cone of Cold", 3),
             ("Mage", "Fire", "Improved Fire Blast", 2), ("Mage", "Fire", "Incineration", 3), ("Mage", "Fire", "Impact", 3),
             ("Hero", "Hero", "Opportunist", 5), ("Hero", "Hero", "Sharpened", 3),
         ]),
    dict(id=3, name="Ashen Reaver",
         description="Warrior and warlock in fire and shadow: burning and shadowed strikes, curses and soul fire, a flame turret to hold the ground.",
         abilities=[
             ("Warrior", "Shadow Heroic Strike"), ("Warlock", "Immolate"), ("Warrior", "Charge"), ("Warlock", "Corruption"),
             ("Warlock", "Life Tap"), ("Warrior", "Hamstring"), ("Hero", "Emberfeed"), ("Warrior", "Fiery Overpower"),
             ("Hero", "Wide Arc"), ("Warlock", "Searing Pain"), ("Warrior", "Umbral Cleave"), ("Warrior", "Execute"),
             ("Hero", "Signal Fire"), ("Warlock", "Hellfire"), ("Warrior", "Fiery Whirlwind"), ("Warlock", "Death Coil"),
             ("Warrior", "Shadow Mortal Strike"), ("Warlock", "Soul Fire"), ("Warlock", "Shadowfury"),
             ("Hero", "Reclaimed Sentry"), ("Warlock", "Chaos Bolt"),
             ("Warlock", "Shadowflame"), ("Warrior", "Enraged Regeneration"),
         ],
         talents=[
             ("Warlock", "Destruction", "Improved Shadow Bolt", 5), ("Warlock", "Destruction", "Bane", 5),
             ("Warlock", "Destruction", "Cataclysm", 3), ("Warlock", "Destruction", "Aftermath", 2),
             ("Warlock", "Destruction", "Ruin", 5), ("Warlock", "Destruction", "Intensity", 2),
             ("Warlock", "Destruction", "Improved Searing Pain", 3), ("Warlock", "Destruction", "Improved Immolate", 3),
             ("Warlock", "Destruction", "Devastation", 1), ("Warlock", "Destruction", "Backlash", 3),
             ("Warlock", "Destruction", "Emberstorm", 5), ("Warlock", "Destruction", "Conflagrate", 1),
             ("Warlock", "Destruction", "Soul Leech", 3), ("Warlock", "Destruction", "Shadow and Flame", 5),
             ("Warrior", "Fury", "Cruelty", 5), ("Warrior", "Fury", "Unbridled Wrath", 5),
             ("Warrior", "Fury", "Improved Cleave", 3), ("Warrior", "Fury", "Improved Execute", 2),
             ("Hero", "Hero", "Scavenger's Eye", 2), ("Hero", "Hero", "Overclocked", 1), ("Hero", "Hero", "Wide Swing", 2),
             ("Hero", "Hero", "Two Schools", 5),
         ]),
    dict(id=4, name="Plaguebringer",
         description="Rogue and warlock in poison and shadow: venom-soaked and shadowed blades, corruption and agony, a beetle at heel.",
         abilities=[
             ("Rogue", "Venomous Sinister Strike"), ("Rogue", "Eviscerate"), ("Warlock", "Corruption"),
             ("Rogue", "Shadow Backstab"), ("Warlock", "Curse of Agony"), ("Rogue", "Gouge"), ("Warlock", "Life Tap"),
             ("Rogue", "Evasion"), ("Hero", "Venom Beetle"),
             ("Rogue", "Kick"), ("Warlock", "Drain Life"), ("Rogue", "Rupture"),
             ("Rogue", "Venomous Ambush"), ("Hero", "Bleed Over"), ("Rogue", "Shadow Hemorrhage"),
             ("Rogue", "Kidney Shot"), ("Hero", "Sinkhole"),
             ("Rogue", "Mutilate"), ("Warlock", "Unstable Affliction"), ("Warlock", "Haunt"), ("Rogue", "Envenom"),
             ("Warlock", "Seed of Corruption"),
             ("Warlock", "Shadowflame"),
         ],
         talents=[
             ("Rogue", "Assassination", "Improved Eviscerate", 3), ("Rogue", "Assassination", "Malice", 5),
             ("Rogue", "Assassination", "Ruthlessness", 3), ("Rogue", "Assassination", "Puncturing Wounds", 3),
             ("Rogue", "Assassination", "Lethality", 5), ("Rogue", "Assassination", "Vile Poisons", 3),
             ("Rogue", "Assassination", "Improved Poisons", 5), ("Rogue", "Assassination", "Cold Blood", 1),
             ("Rogue", "Assassination", "Seal Fate", 1), ("Rogue", "Assassination", "Murder", 2),
             ("Rogue", "Assassination", "Master Poisoner", 3), ("Rogue", "Assassination", "Focused Attacks", 3),
             ("Warlock", "Affliction", "Improved Corruption", 5), ("Warlock", "Affliction", "Improved Curse of Agony", 2),
             ("Warlock", "Affliction", "Soul Siphon", 2), ("Warlock", "Affliction", "Fel Concentration", 3),
             ("Warlock", "Affliction", "Empowered Corruption", 3), ("Warlock", "Affliction", "Shadow Embrace", 5),
             ("Warlock", "Affliction", "Siphon Life", 1), ("Warlock", "Affliction", "Contagion", 5),
             ("Hero", "Hero", "Venom Handler", 3), ("Hero", "Hero", "Medicinal Venom", 1), ("Hero", "Hero", "Opportunist", 4),
         ]),
    dict(id=5, name="Dawnstrider",
         description="Hunter and paladin in holy and arcane light: hallowed and arcane shots, seals and judgements when the fight closes in.",
         abilities=[
             ("Hunter", "Holy Raptor Strike"), ("Paladin", "Seal of Righteousness"), ("Hero", "Hurl"),
             ("Hunter", "Serpent Sting"), ("Paladin", "Judgement of Light"), ("Hunter", "Arcane Shot"),
             ("Hunter", "Hunter's Mark"), ("Paladin", "Hammer of Justice"), ("Hunter", "Aspect of the Hawk"),
             ("Hunter", "Arcane Multi-Shot"), ("Hero", "Ricochet Shot"),
             ("Hunter", "Holy Aimed Shot"), ("Paladin", "Exorcism"),
             ("Hunter", "Rapid Fire"), ("Hunter", "Feign Death"), ("Paladin", "Divine Shield"), ("Hero", "Overflow"),
             ("Paladin", "Holy Shock"), ("Paladin", "Hammer of Wrath"), ("Hunter", "Steady Shot"),
             ("Paladin", "Avenging Wrath"), ("Paladin", "Divine Plea"), ("Hunter", "Holy Kill Shot"),
             ("Hunter", "Aspect of the Dragonhawk"),
         ],
         talents=[
             ("Hunter", "Marksmanship", "Lethal Shots", 5), ("Hunter", "Marksmanship", "Focused Aim", 3),
             ("Hunter", "Marksmanship", "Careful Aim", 3), ("Hunter", "Marksmanship", "Mortal Shots", 5),
             ("Hunter", "Marksmanship", "Rapid Killing", 2), ("Hunter", "Marksmanship", "Improved Arcane Shot", 3),
             ("Hunter", "Marksmanship", "Improved Stings", 3), ("Hunter", "Marksmanship", "Efficiency", 5),
             ("Hunter", "Marksmanship", "Barrage", 3), ("Hunter", "Marksmanship", "Readiness", 1),
             ("Hunter", "Marksmanship", "Combat Experience", 2), ("Hunter", "Marksmanship", "Ranged Weapon Specialization", 3),
             ("Hunter", "Marksmanship", "Piercing Shots", 3), ("Hunter", "Marksmanship", "Trueshot Aura", 1),
             ("Hunter", "Marksmanship", "Master Marksman", 5),
             ("Paladin", "Holy", "Seals of the Pure", 5), ("Paladin", "Holy", "Healing Light", 3),
             ("Paladin", "Holy", "Divine Intellect", 5), ("Paladin", "Holy", "Sanctified Light", 3),
             ("Hero", "Hero", "Long Reach", 2), ("Hero", "Hero", "Sharpened", 3), ("Hero", "Hero", "Ricochet Chamber", 2),
             ("Hero", "Hero", "Wide Swing", 1),
         ]),
    dict(id=6, name="Voidclaw",
         description="Druid and priest in shadow: a cat whose claws and shreds carry the void, shadow words before the pounce, a shadowfiend at the kill.",
         abilities=[
             ("Druid", "Wrath"), ("Hero", "Makeshift Strike"), ("Priest", "Shadow Word: Pain"), ("Druid", "Moonfire"),
             ("Priest", "Power Word: Shield"), ("Hero", "Fistful of Grit"), ("Priest", "Mind Blast"), ("Hero", "Wide Arc"),
             ("Priest", "Psychic Scream"), ("Druid", "Cat Form"), ("Druid", "Shadow Claw"), ("Druid", "Rip"),
             ("Druid", "Shadow Shred"), ("Druid", "Rake"), ("Druid", "Tiger's Fury"), ("Druid", "Shadow Ravage"),
             ("Druid", "Ferocious Bite"), ("Hero", "Vertigo"), ("Druid", "Shadow Mangle (Cat)"),
             ("Priest", "Shadow Word: Death"), ("Priest", "Shadowfiend"), ("Druid", "Shadow Swipe (Cat)"),
             ("Priest", "Mind Sear"),
         ],
         talents=[
             ("Druid", "Feral Combat", "Ferocity", 5), ("Druid", "Feral Combat", "Feral Aggression", 5),
             ("Druid", "Feral Combat", "Feral Instinct", 3), ("Druid", "Feral Combat", "Savage Fury", 2),
             ("Druid", "Feral Combat", "Sharpened Claws", 3), ("Druid", "Feral Combat", "Shredding Attacks", 2),
             ("Druid", "Feral Combat", "Predatory Strikes", 3), ("Druid", "Feral Combat", "Primal Fury", 2),
             ("Druid", "Feral Combat", "Primal Precision", 2), ("Druid", "Feral Combat", "Heart of the Wild", 5),
             ("Druid", "Feral Combat", "Leader of the Pack", 1), ("Druid", "Feral Combat", "Predatory Instincts", 3),
             ("Druid", "Feral Combat", "King of the Jungle", 3), ("Druid", "Feral Combat", "Rend and Tear", 5),
             ("Druid", "Feral Combat", "Primal Gore", 1), ("Druid", "Feral Combat", "Berserk", 1),
             ("Priest", "Shadow", "Darkness", 5), ("Priest", "Shadow", "Improved Shadow Word: Pain", 2),
             ("Priest", "Shadow", "Shadow Focus", 3), ("Priest", "Shadow", "Improved Mind Blast", 5),
             ("Hero", "Hero", "Opportunist", 5), ("Hero", "Hero", "Sharpened", 3), ("Hero", "Hero", "Wide Swing", 2),
         ]),
    dict(id=7, name="Twilight Knight",
         description="Warrior and priest between light and shadow: holy and shadowed strikes, a shield of faith, mind blasts at close range.",
         abilities=[
             ("Warrior", "Holy Heroic Strike"), ("Priest", "Smite"), ("Warrior", "Charge"), ("Priest", "Shadow Word: Pain"),
             ("Priest", "Power Word: Shield"), ("Hero", "Makeshift Strike"), ("Warrior", "Hamstring"),
             ("Priest", "Mind Blast"), ("Warrior", "Shadow Overpower"), ("Priest", "Inner Fire"), ("Hero", "Ward Off"),
             ("Warrior", "Hallowed Cleave"), ("Priest", "Holy Fire"), ("Hero", "Borrowed Stance"), ("Warrior", "Execute"),
             ("Hero", "Vanguard Rush"), ("Warrior", "Holy Whirlwind"), ("Warrior", "Shadow Mortal Strike"),
             ("Priest", "Vampiric Touch"), ("Priest", "Shadow Word: Death"), ("Warrior", "Recklessness"),
             ("Priest", "Shadowfiend"), ("Warrior", "Heroic Throw"),
         ],
         talents=[
             ("Warrior", "Arms", "Improved Heroic Strike", 3), ("Warrior", "Arms", "Iron Will", 2),
             ("Warrior", "Arms", "Tactical Mastery", 3), ("Warrior", "Arms", "Improved Charge", 2),
             ("Warrior", "Arms", "Improved Overpower", 2), ("Warrior", "Arms", "Anger Management", 1),
             ("Warrior", "Arms", "Impale", 2), ("Warrior", "Arms", "Deep Wounds", 3),
             ("Warrior", "Arms", "Two-Handed Weapon Specialization", 3), ("Warrior", "Arms", "Taste for Blood", 3),
             ("Warrior", "Arms", "Weapon Mastery", 2), ("Warrior", "Arms", "Trauma", 2),
             ("Warrior", "Arms", "Strength of Arms", 2), ("Warrior", "Arms", "Sudden Death", 3),
             ("Priest", "Discipline", "Twin Disciplines", 5), ("Priest", "Discipline", "Improved Inner Fire", 3),
             ("Priest", "Discipline", "Improved Power Word: Shield", 3), ("Priest", "Discipline", "Mental Strength", 5),
             ("Priest", "Discipline", "Inner Focus", 1),
             ("Priest", "Shadow", "Darkness", 5), ("Priest", "Shadow", "Improved Shadow Word: Pain", 2),
             ("Priest", "Shadow", "Improved Mind Blast", 5),
             ("Hero", "Hero", "Last Reserve", 2), ("Hero", "Hero", "Sharpened", 3), ("Hero", "Hero", "Thrift", 3),
             ("Hero", "Hero", "Weave", 1),
         ]),
    dict(id=8, name="Spellbow",
         description="Hunter and mage in arcane and frost: arcane and frozen shots, a blink out of reach, ice lances while the trap holds.",
         abilities=[
             ("Hunter", "Arcane Raptor Strike"), ("Mage", "Frostbolt"), ("Hunter", "Serpent Sting"), ("Hero", "Hurl"),
             ("Hunter", "Arcane Shot"), ("Hunter", "Hunter's Mark"), ("Mage", "Arcane Missiles"),
             ("Mage", "Frost Nova"),
             ("Hunter", "Frozen Multi-Shot"), ("Hero", "Ricochet Shot"), ("Hunter", "Arcane Aimed Shot"),
             ("Mage", "Blink"), ("Hunter", "Freezing Trap"), ("Mage", "Cone of Cold"), ("Hunter", "Feign Death"),
             ("Hero", "Bleed Over"), ("Hunter", "Volley"), ("Mage", "Ice Barrier"), ("Hunter", "Steady Shot"),
             ("Mage", "Arcane Barrage"), ("Mage", "Ice Lance"), ("Hunter", "Frozen Kill Shot"),
             ("Hunter", "Aspect of the Dragonhawk"),
         ],
         talents=[
             ("Hunter", "Marksmanship", "Lethal Shots", 5), ("Hunter", "Marksmanship", "Focused Aim", 3),
             ("Hunter", "Marksmanship", "Careful Aim", 3), ("Hunter", "Marksmanship", "Mortal Shots", 5),
             ("Hunter", "Marksmanship", "Improved Arcane Shot", 3), ("Hunter", "Marksmanship", "Rapid Killing", 2),
             ("Hunter", "Marksmanship", "Efficiency", 5), ("Hunter", "Marksmanship", "Barrage", 3),
             ("Hunter", "Marksmanship", "Combat Experience", 2), ("Hunter", "Marksmanship", "Piercing Shots", 3),
             ("Hunter", "Marksmanship", "Master Marksman", 5),
             ("Mage", "Arcane", "Arcane Subtlety", 2), ("Mage", "Arcane", "Arcane Focus", 3),
             ("Mage", "Arcane", "Arcane Concentration", 5), ("Mage", "Arcane", "Spell Impact", 3),
             ("Hunter", "Marksmanship", "Improved Hunter's Mark", 1),
             ("Mage", "Frost", "Frostbite", 3), ("Mage", "Frost", "Improved Frostbolt", 5), ("Mage", "Frost", "Ice Shards", 3),
             ("Hero", "Hero", "Long Reach", 2), ("Hero", "Hero", "Ricochet Chamber", 2), ("Hero", "Hero", "Sharpened", 3),
         ]),
    dict(id=9, name="Juggernaut",
         description="Druid and warrior in earth: an earthen bear that mauls and mangles, warrior shouts and thunder to hold every enemy close.",
         abilities=[
             ("Warrior", "Earthen Heroic Strike"),
             ("Warrior", "Rend"), ("Hero", "Brace"), ("Warrior", "Thunder Clap"), ("Hero", "Draw Attention"),
             ("Druid", "Bear Form"), ("Druid", "Earthen Maul"), ("Druid", "Enrage"), ("Druid", "Bash"),
             ("Hero", "Cairn"), ("Druid", "Swipe (Bear)"), ("Hero", "Ward Off"), ("Druid", "Faerie Fire (Feral)"),
             ("Warrior", "Intimidating Shout"), ("Hero", "Bulwark Anchor"), ("Druid", "Challenging Roar"),
             ("Druid", "Frenzied Regeneration"), ("Druid", "Barkskin"), ("Druid", "Earthen Mangle (Bear)"),
             ("Warrior", "Earthen Devastate"), ("Warrior", "Commanding Shout"), ("Druid", "Lacerate"),
             ("Warrior", "Enraged Regeneration"),
         ],
         talents=[
             ("Druid", "Feral Combat", "Ferocity", 5), ("Druid", "Feral Combat", "Feral Instinct", 3),
             ("Druid", "Feral Combat", "Thick Hide", 3), ("Druid", "Feral Combat", "Survival Instincts", 1),
             ("Druid", "Feral Combat", "Sharpened Claws", 3), ("Druid", "Feral Combat", "Feral Swiftness", 2),
             ("Druid", "Feral Combat", "Predatory Strikes", 3), ("Druid", "Feral Combat", "Primal Fury", 2),
             ("Druid", "Feral Combat", "Feral Charge", 1), ("Druid", "Feral Combat", "Brutal Impact", 2),
             ("Druid", "Feral Combat", "Natural Reaction", 3), ("Druid", "Feral Combat", "Survival of the Fittest", 3),
             ("Druid", "Feral Combat", "Heart of the Wild", 5), ("Druid", "Feral Combat", "Leader of the Pack", 1),
             ("Druid", "Feral Combat", "Protector of the Pack", 3), ("Druid", "Feral Combat", "Infected Wounds", 3),
             ("Druid", "Feral Combat", "Primal Tenacity", 3), ("Druid", "Feral Combat", "Rend and Tear", 5),
             ("Warrior", "Protection", "Improved Thunder Clap", 3), ("Warrior", "Protection", "Incite", 3),
             ("Warrior", "Protection", "Toughness", 3),
             ("Warrior", "Fury", "Booming Voice", 2),
             ("Hero", "Hero", "Wider Net", 2), ("Hero", "Hero", "Last Reserve", 2), ("Hero", "Hero", "Thrift", 3),
             ("Hero", "Hero", "Quick Deploy", 2),
         ]),
    dict(id=10, name="Thunder Crusader",
         description="Paladin and shaman in holy light and storm: seals and judgements on a windfury blade, shocks and consecration, totems set at the feet.",
         abilities=[
             ("Paladin", "Seal of Righteousness"), ("Shaman", "Lightning Bolt"), ("Hero", "Makeshift Strike"),
             ("Shaman", "Earth Shock"), ("Paladin", "Judgement of Light"), ("Shaman", "Stoneskin Totem"),
             ("Shaman", "Lightning Shield"), ("Paladin", "Hammer of Justice"), ("Shaman", "Flametongue Weapon"),
             ("Shaman", "Strength of Earth Totem"), ("Hero", "Wide Arc"), ("Shaman", "Wind Shear"),
             ("Paladin", "Consecration"), ("Paladin", "Exorcism"), ("Hero", "Borrowed Stance"),
             ("Shaman", "Windfury Weapon"), ("Shaman", "Windfury Totem"), ("Paladin", "Divine Shield"),
             ("Hero", "Vanguard Rush"), ("Paladin", "Hammer of Wrath"), ("Shaman", "Earth Shield"),
             ("Paladin", "Avenging Wrath"), ("Shaman", "Lava Burst"),
             ("Shaman", "Earth Elemental Totem"), ("Paladin", "Divine Plea"),
         ],
         talents=[
             ("Shaman", "Enhancement", "Ancestral Knowledge", 5), ("Shaman", "Enhancement", "Thundering Strikes", 5),
             ("Shaman", "Enhancement", "Enhancing Totems", 3), ("Shaman", "Enhancement", "Improved Shields", 3),
             ("Shaman", "Enhancement", "Elemental Weapons", 3), ("Shaman", "Enhancement", "Shamanistic Focus", 1),
             ("Shaman", "Enhancement", "Flurry", 5), ("Shaman", "Enhancement", "Improved Windfury Totem", 2),
             ("Shaman", "Enhancement", "Spirit Weapons", 1), ("Shaman", "Enhancement", "Unleashed Rage", 3),
             ("Shaman", "Enhancement", "Weapon Mastery", 3), ("Shaman", "Enhancement", "Stormstrike", 1),
             ("Shaman", "Enhancement", "Static Shock", 3), ("Shaman", "Enhancement", "Maelstrom Weapon", 5),
             ("Paladin", "Retribution", "Benediction", 5), ("Paladin", "Retribution", "Improved Judgements", 2),
             ("Paladin", "Retribution", "Heart of the Crusader", 3), ("Paladin", "Retribution", "Conviction", 5),
             ("Paladin", "Retribution", "Seal of Command", 1), ("Paladin", "Retribution", "Crusade", 3),
             ("Paladin", "Retribution", "Pursuit of Justice", 1),
             ("Hero", "Hero", "Sharpened", 3), ("Hero", "Hero", "Wide Swing", 2), ("Hero", "Hero", "Weave", 3),
         ]),
    dict(id=11, name="Wintertrap Ranger",
         description="Hunter and shaman in frost: frozen shots and traps, a frostbrand edge and chain lightning, earthbind to keep prey where it stands.",
         abilities=[
             ("Hunter", "Frozen Raptor Strike"), ("Shaman", "Lightning Bolt"), ("Hunter", "Serpent Sting"), ("Hero", "Hurl"),
             ("Shaman", "Earth Shock"), ("Shaman", "Earthbind Totem"),
             ("Shaman", "Lightning Shield"), ("Hunter", "Aspect of the Hawk"),
             ("Hunter", "Frozen Multi-Shot"), ("Hero", "Ricochet Shot"),
             ("Shaman", "Frostbrand Weapon"), ("Hunter", "Freezing Trap"),
             ("Hunter", "Frozen Aimed Shot"), ("Hunter", "Frost Trap"), ("Hero", "Sinkhole"),
             ("Shaman", "Chain Lightning"), ("Hunter", "Black Arrow"), ("Shaman", "Thunderstorm"),
             ("Hunter", "Frozen Kill Shot"), ("Hunter", "Aspect of the Dragonhawk"), ("Hunter", "Freezing Arrow"),
             ("Hunter", "Misdirection"),
         ],
         talents=[
             ("Hunter", "Survival", "Savage Strikes", 2), ("Hunter", "Survival", "Hawk Eye", 3),
             ("Hunter", "Survival", "Entrapment", 3), ("Hunter", "Survival", "Trap Mastery", 3),
             ("Hunter", "Survival", "Survival Instincts", 2), ("Hunter", "Survival", "Survivalist", 5),
             ("Hunter", "Survival", "T.N.T.", 3), ("Hunter", "Survival", "Lock and Load", 3),
             ("Hunter", "Survival", "Hunter vs. Wild", 3), ("Hunter", "Survival", "Killer Instinct", 3),
             ("Hunter", "Survival", "Lightning Reflexes", 5), ("Hunter", "Survival", "Expose Weakness", 3),
             ("Hunter", "Survival", "Thrill of the Hunt", 3), ("Hunter", "Survival", "Master Tactician", 5),
             ("Hunter", "Survival", "Sniper Training", 3), ("Hunter", "Survival", "Hunting Party", 3),
             ("Shaman", "Elemental", "Convection", 5), ("Shaman", "Elemental", "Concussion", 5),
             ("Shaman", "Enhancement", "Frozen Power", 2),
             ("Hero", "Hero", "Long Reach", 2), ("Hero", "Hero", "Ricochet Chamber", 2), ("Hero", "Hero", "Opportunist", 3),
         ]),
    dict(id=12, name="Venom Prowler",
         description="Druid and rogue in poison and earth: a cat with envenomed claws, rogue poisons on every shred, earthen blows to break armor.",
         abilities=[
             ("Rogue", "Venomous Sinister Strike"), ("Druid", "Rejuvenation"), ("Rogue", "Eviscerate"),
             ("Druid", "Moonfire"), ("Rogue", "Earthen Backstab"), ("Rogue", "Gouge"), ("Rogue", "Evasion"),
             ("Hero", "Fistful of Grit"), ("Hero", "Venom Beetle"), ("Druid", "Cat Form"),
             ("Druid", "Venomous Claw"), ("Druid", "Rip"), ("Druid", "Venomous Shred"), ("Druid", "Rake"),
             ("Hero", "Bleed Over"), ("Druid", "Earthen Ravage"), ("Druid", "Ferocious Bite"), ("Rogue", "Blind"),
             ("Druid", "Venomous Mangle (Cat)"), ("Rogue", "Envenom"), ("Druid", "Savage Roar"),
             ("Rogue", "Venomous Fan of Knives"),
             ("Rogue", "Shiv"),
         ],
         talents=[
             ("Druid", "Feral Combat", "Ferocity", 5), ("Druid", "Feral Combat", "Feral Aggression", 5),
             ("Druid", "Feral Combat", "Feral Instinct", 3), ("Druid", "Feral Combat", "Savage Fury", 2),
             ("Druid", "Feral Combat", "Sharpened Claws", 3), ("Druid", "Feral Combat", "Shredding Attacks", 2),
             ("Druid", "Feral Combat", "Predatory Strikes", 3), ("Druid", "Feral Combat", "Primal Fury", 2),
             ("Druid", "Feral Combat", "Heart of the Wild", 5), ("Druid", "Feral Combat", "Leader of the Pack", 1),
             ("Druid", "Feral Combat", "Predatory Instincts", 3), ("Druid", "Feral Combat", "King of the Jungle", 3),
             ("Druid", "Feral Combat", "Rend and Tear", 5),
             ("Rogue", "Assassination", "Improved Eviscerate", 1),
             ("Rogue", "Assassination", "Malice", 5), ("Rogue", "Assassination", "Ruthlessness", 3),
             ("Rogue", "Assassination", "Lethality", 5), ("Rogue", "Assassination", "Vile Poisons", 3),
             ("Rogue", "Assassination", "Improved Poisons", 5),
             ("Hero", "Hero", "Venom Handler", 3), ("Hero", "Hero", "Medicinal Venom", 1), ("Hero", "Hero", "Opportunist", 3),
         ]),
    dict(id=13, name="Inquisitor",
         description="Paladin and rogue in holy light: hallowed sinister strikes and ambushes, seals behind every blow, a divine shield to walk out alive.",
         abilities=[
             ("Rogue", "Holy Sinister Strike"), ("Paladin", "Seal of Righteousness"), ("Rogue", "Eviscerate"),
             ("Paladin", "Judgement of Light"), ("Rogue", "Holy Backstab"), ("Rogue", "Gouge"),
             ("Paladin", "Hammer of Justice"), ("Rogue", "Evasion"), ("Hero", "Fistful of Grit"),
             ("Hero", "Crossdraw"), ("Paladin", "Exorcism"),
             ("Rogue", "Holy Ambush"), ("Paladin", "Flash of Light"), ("Rogue", "Rupture"), ("Hero", "Overflow"),
             ("Rogue", "Holy Hemorrhage"), ("Rogue", "Kidney Shot"), ("Paladin", "Divine Shield"),
             ("Paladin", "Hammer of Wrath"), ("Rogue", "Cloak of Shadows"), ("Paladin", "Avenging Wrath"),
             ("Rogue", "Holy Fan of Knives"), ("Paladin", "Sacred Shield"),
             ("Rogue", "Shiv"),
         ],
         talents=[
             ("Paladin", "Retribution", "Benediction", 5), ("Paladin", "Retribution", "Improved Judgements", 2),
             ("Paladin", "Retribution", "Heart of the Crusader", 3), ("Paladin", "Retribution", "Conviction", 5),
             ("Paladin", "Retribution", "Seal of Command", 1), ("Paladin", "Retribution", "Pursuit of Justice", 2),
             ("Paladin", "Retribution", "Sanctity of Battle", 3), ("Paladin", "Retribution", "Crusade", 3),
             ("Paladin", "Retribution", "Vengeance", 3), ("Paladin", "Retribution", "The Art of War", 2),
             ("Paladin", "Retribution", "Judgements of the Wise", 3), ("Paladin", "Retribution", "Repentance", 1),
             ("Paladin", "Retribution", "Fanaticism", 3),
             ("Rogue", "Combat", "Improved Sinister Strike", 2), ("Rogue", "Combat", "Dual Wield Specialization", 5),
             ("Rogue", "Combat", "Precision", 5), ("Rogue", "Combat", "Endurance", 2),
             ("Rogue", "Combat", "Aggression", 5), ("Rogue", "Combat", "Lightning Reflexes", 3),
             ("Rogue", "Combat", "Blade Flurry", 1), ("Rogue", "Combat", "Hack and Slash", 5),
             ("Rogue", "Combat", "Weapon Expertise", 1),
             ("Hero", "Hero", "Sharpened", 3), ("Hero", "Hero", "Wide Swing", 2), ("Hero", "Hero", "Broad Strokes", 1),
         ]),
    dict(id=14, name="Starfire Sage",
         description="Druid and mage in arcane and fire: moonfire and starfire, fireballs and flamestrike, and Antipode Blast when both are not enough.",
         abilities=[
             ("Druid", "Wrath"), ("Mage", "Fireball"), ("Druid", "Moonfire"), ("Mage", "Fire Blast"),
             ("Hero", "Second Nature"), ("Druid", "Entangling Roots"), ("Mage", "Arcane Missiles"), ("Hero", "Emberfeed"),
             ("Mage", "Arcane Explosion"), ("Mage", "Flamestrike"), ("Druid", "Faerie Fire"), ("Druid", "Starfire"),
             ("Mage", "Blink"), ("Hero", "Antipode Blast"), ("Druid", "Insect Swarm"), ("Mage", "Blast Wave"),
             ("Druid", "Hurricane"), ("Druid", "Innervate"), ("Druid", "Barkskin"), ("Druid", "Typhoon"),
             ("Mage", "Living Bomb"), ("Mage", "Arcane Blast"), ("Hero", "Wildcard Surge"),
             ("Mage", "Mirror Image"),
         ],
         talents=[
             ("Druid", "Balance", "Starlight Wrath", 5), ("Druid", "Balance", "Genesis", 5), ("Druid", "Balance", "Moonglow", 3),
             ("Druid", "Balance", "Nature's Majesty", 2), ("Druid", "Balance", "Improved Moonfire", 2),
             ("Druid", "Balance", "Nature's Grace", 3), ("Druid", "Balance", "Nature's Splendor", 1),
             ("Druid", "Balance", "Vengeance", 5), ("Druid", "Balance", "Celestial Focus", 3),
             ("Druid", "Balance", "Lunar Guidance", 3), ("Druid", "Balance", "Moonfury", 3),
             ("Druid", "Balance", "Balance of Power", 2), ("Druid", "Balance", "Moonkin Form", 1),
             ("Druid", "Balance", "Wrath of Cenarius", 5), ("Druid", "Balance", "Eclipse", 3),
             ("Mage", "Fire", "Improved Fireball", 5), ("Mage", "Fire", "Ignite", 5), ("Mage", "Fire", "Incineration", 3),
             ("Mage", "Arcane", "Arcane Subtlety", 2), ("Mage", "Arcane", "Arcane Focus", 3),
             ("Hero", "Hero", "Overdraw", 3), ("Hero", "Hero", "Sharpened", 3), ("Hero", "Hero", "Two Schools", 1),
         ]),
    dict(id=15, name="Gravecaller",
         description="Priest and warlock in shadow and plague: shields and mends for friends, plague, corruption and drains for everyone else.",
         abilities=[
             ("Priest", "Lesser Heal"), ("Warlock", "Shadow Bolt"), ("Priest", "Shadow Word: Pain"),
             ("Warlock", "Corruption"), ("Priest", "Power Word: Shield"), ("Hero", "Second Nature"),
             ("Warlock", "Life Tap"), ("Priest", "Renew"), ("Warlock", "Curse of Agony"), ("Priest", "Mind Blast"),
             ("Hero", "Venom Beetle"), ("Warlock", "Drain Life"), ("Priest", "Heal"), ("Hero", "Ward Off"),
             ("Priest", "Devouring Plague"), ("Priest", "Flash Heal"), ("Hero", "Bleed Over"),
             ("Priest", "Prayer of Healing"), ("Warlock", "Death Coil"), ("Priest", "Greater Heal"),
             ("Priest", "Vampiric Touch"), ("Warlock", "Unstable Affliction"), ("Warlock", "Haunt"),
             ("Warlock", "Seed of Corruption"),
             ("Priest", "Prayer of Mending"), ("Priest", "Divine Hymn"),
         ],
         talents=[
             ("Priest", "Discipline", "Twin Disciplines", 5), ("Priest", "Discipline", "Improved Inner Fire", 3),
             ("Priest", "Discipline", "Meditation", 3), ("Priest", "Discipline", "Inner Focus", 1),
             ("Priest", "Discipline", "Improved Power Word: Shield", 3), ("Priest", "Discipline", "Mental Agility", 3),
             ("Priest", "Discipline", "Mental Strength", 5), ("Priest", "Discipline", "Soul Warding", 1),
             ("Priest", "Discipline", "Focused Power", 2), ("Priest", "Discipline", "Enlightenment", 3),
             ("Priest", "Discipline", "Power Infusion", 1), ("Priest", "Discipline", "Improved Flash Heal", 3),
             ("Priest", "Discipline", "Renewed Hope", 2), ("Priest", "Discipline", "Rapture", 3),
             ("Priest", "Discipline", "Divine Aegis", 3), ("Priest", "Discipline", "Pain Suppression", 1),
             ("Warlock", "Affliction", "Improved Corruption", 5), ("Warlock", "Affliction", "Improved Curse of Agony", 2),
             ("Warlock", "Affliction", "Soul Siphon", 2), ("Warlock", "Affliction", "Fel Concentration", 3),
             ("Warlock", "Affliction", "Empowered Corruption", 3), ("Warlock", "Affliction", "Siphon Life", 1),
             ("Hero", "Hero", "Venom Handler", 3), ("Hero", "Hero", "Medicinal Venom", 1), ("Hero", "Hero", "Thrift", 3),
             ("Priest", "Discipline", "Grace", 2), ("Priest", "Discipline", "Borrowed Time", 4),
         ]),

    # ---- for fun -------------------------------------------------------------------
    dict(id=16, name="Menagerie",
         description="Hunter and warlock, never alone: a tamed beast, a demon, a venom beetle and a turret, with fire and shadow shots over the top.",
         abilities=[
             ("Warlock", "Summon Imp"), ("Hunter", "Fiery Raptor Strike"), ("Warlock", "Immolate"),
             ("Hunter", "Serpent Sting"), ("Warlock", "Corruption"), ("Hunter", "Arcane Shot"), ("Hunter", "Hunter's Mark"),
             ("Hunter", "Tame Beast"), ("Warlock", "Summon Voidwalker"), ("Hero", "Venom Beetle"),
             ("Hunter", "Shadow Multi-Shot"),
             ("Warlock", "Summon Succubus"), ("Hero", "Signal Fire"), ("Hunter", "Feign Death"),
             ("Warlock", "Summon Felhunter"), ("Hero", "Rally Point"), ("Hunter", "Aspect of the Wild"), ("Warlock", "Inferno"),
             ("Hero", "Reclaimed Sentry"), ("Hunter", "Kill Command"), ("Hunter", "Snake Trap"),
             ("Hunter", "Shadow Kill Shot"),
             ("Hunter", "Call Stabled Pet"),
         ],
         talents=[
             ("Hunter", "Beast Mastery", "Improved Aspect of the Hawk", 5), ("Hunter", "Beast Mastery", "Endurance Training", 5),
             ("Hunter", "Beast Mastery", "Focused Fire", 2), ("Hunter", "Beast Mastery", "Thick Hide", 3),
             ("Hunter", "Beast Mastery", "Unleashed Fury", 5), ("Hunter", "Beast Mastery", "Ferocity", 5),
             ("Hunter", "Beast Mastery", "Spirit Bond", 2), ("Hunter", "Beast Mastery", "Intimidation", 1),
             ("Hunter", "Beast Mastery", "Bestial Discipline", 2), ("Hunter", "Beast Mastery", "Animal Handler", 2),
             ("Hunter", "Beast Mastery", "Frenzy", 5), ("Hunter", "Beast Mastery", "Ferocious Inspiration", 3),
             ("Hunter", "Beast Mastery", "Bestial Wrath", 1),
             ("Warlock", "Demonology", "Improved Imp", 3), ("Warlock", "Demonology", "Demonic Embrace", 3),
             ("Warlock", "Demonology", "Fel Vitality", 3), ("Warlock", "Demonology", "Demonic Brutality", 3),
             ("Warlock", "Demonology", "Soul Link", 1), ("Warlock", "Demonology", "Demonic Aegis", 3),
             ("Warlock", "Demonology", "Unholy Power", 5), ("Warlock", "Demonology", "Master Demonologist", 5),
             ("Hero", "Hero", "Venom Handler", 3), ("Hero", "Hero", "Overclocked", 1),
         ]),
    dict(id=17, name="Pyromaniac",
         description="Mage and warlock who agree on one thing: everything burns. Fireballs, immolate, hellfire, rain of fire, and a signal fire for the finish.",
         abilities=[
             ("Mage", "Fireball"), ("Warlock", "Immolate"), ("Mage", "Fire Blast"), ("Warlock", "Life Tap"),
             ("Hero", "Second Nature"), ("Hero", "Emberfeed"), ("Mage", "Flamestrike"), ("Warlock", "Searing Pain"),
             ("Warlock", "Rain of Fire"), ("Mage", "Pyroblast"), ("Mage", "Scorch"), ("Hero", "Signal Fire"),
             ("Warlock", "Hellfire"), ("Mage", "Blast Wave"), ("Mage", "Fire Ward"), ("Warlock", "Soul Fire"),
             ("Mage", "Dragon's Breath"), ("Hero", "Reclaimed Sentry"), ("Mage", "Living Bomb"), ("Warlock", "Chaos Bolt"),
             ("Warlock", "Incinerate"), ("Warlock", "Shadowflame"),
         ],
         talents=[
             ("Mage", "Fire", "Improved Fire Blast", 2), ("Mage", "Fire", "Incineration", 3),
             ("Mage", "Fire", "Improved Fireball", 5), ("Mage", "Fire", "Ignite", 5), ("Mage", "Fire", "World in Flames", 3),
             ("Mage", "Fire", "Impact", 3), ("Mage", "Fire", "Burning Soul", 2), ("Mage", "Fire", "Improved Scorch", 3),
             ("Mage", "Fire", "Master of Elements", 3), ("Mage", "Fire", "Critical Mass", 3), ("Mage", "Fire", "Fire Power", 5),
             ("Mage", "Fire", "Pyromaniac", 3), ("Mage", "Fire", "Combustion", 1),
             ("Warlock", "Destruction", "Bane", 5), ("Warlock", "Destruction", "Cataclysm", 3),
             ("Warlock", "Destruction", "Ruin", 5), ("Warlock", "Destruction", "Improved Immolate", 3),
             ("Warlock", "Destruction", "Emberstorm", 5),
             ("Hero", "Hero", "Scavenger's Eye", 3), ("Hero", "Hero", "Overdraw", 3), ("Hero", "Hero", "Overclocked", 1),
             ("Hero", "Hero", "Two Schools", 2),
         ]),
    dict(id=18, name="Con Artist",
         description="Rogue and priest who talk their way out: a soothing word, a hand in the pocket, a mind controlled, and a shadowed blade if talk fails.",
         abilities=[
             ("Rogue", "Stealth"), ("Rogue", "Shadow Sinister Strike"), ("Rogue", "Eviscerate"),
             ("Rogue", "Pick Pocket"), ("Priest", "Shadow Word: Pain"), ("Rogue", "Gouge"), ("Priest", "Fade"),
             ("Hero", "Fistful of Grit"), ("Rogue", "Sap"), ("Priest", "Psychic Scream"), ("Hero", "Rattle"),
             ("Priest", "Mind Vision"), ("Priest", "Mind Soothe"), ("Hero", "Hush"), ("Rogue", "Vanish"),
             ("Rogue", "Cheap Shot"), ("Priest", "Mind Control"), ("Rogue", "Shadow Hemorrhage"), ("Rogue", "Blind"),
             ("Hero", "Vertigo"), ("Hero", "Sinkhole"), ("Rogue", "Cloak of Shadows"), ("Rogue", "Tricks of the Trade"),
             ("Rogue", "Shadow Fan of Knives"),
             ("Priest", "Shadowfiend"),
         ],
         talents=[
             ("Rogue", "Subtlety", "Relentless Strikes", 5),
             ("Rogue", "Subtlety", "Master of Deception", 3), ("Rogue", "Subtlety", "Opportunity", 2),
             ("Rogue", "Subtlety", "Dirty Tricks", 2), ("Rogue", "Subtlety", "Camouflage", 3),
             ("Rogue", "Subtlety", "Elusiveness", 2), ("Rogue", "Subtlety", "Initiative", 3),
             ("Rogue", "Subtlety", "Setup", 3), ("Rogue", "Subtlety", "Preparation", 1),
             ("Rogue", "Subtlety", "Dirty Deeds", 2), ("Rogue", "Subtlety", "Heightened Senses", 2),
             ("Rogue", "Subtlety", "Master of Subtlety", 3), ("Rogue", "Subtlety", "Cheat Death", 3),
             ("Rogue", "Subtlety", "Waylay", 2), ("Rogue", "Subtlety", "Filthy Tricks", 2),
             ("Priest", "Shadow", "Darkness", 5), ("Priest", "Shadow", "Improved Psychic Scream", 2),
             ("Priest", "Shadow", "Shadow Affinity", 3), ("Priest", "Discipline", "Silent Resolve", 3),
             ("Rogue", "Combat", "Improved Gouge", 3), ("Rogue", "Combat", "Deflection", 3),
             ("Hero", "Hero", "Opportunist", 5), ("Hero", "Hero", "Wide Swing", 2), ("Hero", "Hero", "Long Reach", 2),
             ("Rogue", "Combat", "Endurance", 2), ("Rogue", "Combat", "Lightning Reflexes", 3),
         ]),
    dict(id=19, name="Skinchanger",
         description="Druid and shaman who never keep one shape: wolf, bear and cat in turn, earthen and frozen blows, healing waves between the changes.",
         abilities=[
             ("Shaman", "Healing Wave"), ("Druid", "Healing Touch"), ("Shaman", "Earth Shock"), ("Druid", "Rejuvenation"),
             ("Hero", "Second Nature"), ("Shaman", "Lightning Shield"), ("Druid", "Bear Form"), ("Druid", "Earthen Maul"),
             ("Hero", "Adrenaline"), ("Shaman", "Ghost Wolf"),
             ("Druid", "Cat Form"), ("Druid", "Frozen Claw"), ("Druid", "Frozen Shred"), ("Shaman", "Frost Shock"),
             ("Druid", "Rake"), ("Druid", "Dash"), ("Shaman", "Chain Heal"), ("Hero", "Quickening"),
             ("Druid", "Earthen Mangle (Bear)"), ("Shaman", "Earth Shield"), ("Druid", "Flight Form"),
             ("Druid", "Frozen Swipe (Cat)"),
             ("Shaman", "Earth Elemental Totem"),
         ],
         talents=[
             ("Druid", "Feral Combat", "Ferocity", 5), ("Druid", "Feral Combat", "Feral Instinct", 3),
             ("Druid", "Feral Combat", "Thick Hide", 3), ("Druid", "Feral Combat", "Feral Swiftness", 2),
             ("Druid", "Feral Combat", "Sharpened Claws", 3), ("Druid", "Feral Combat", "Predatory Strikes", 3),
             ("Druid", "Feral Combat", "Primal Fury", 2), ("Druid", "Feral Combat", "Heart of the Wild", 5),
             ("Druid", "Feral Combat", "Leader of the Pack", 1),
             ("Druid", "Restoration", "Furor", 5), ("Druid", "Restoration", "Naturalist", 5),
             ("Druid", "Restoration", "Natural Shapeshifter", 3), ("Druid", "Restoration", "Omen of Clarity", 1),
             ("Druid", "Restoration", "Master Shapeshifter", 2),
             ("Shaman", "Enhancement", "Ancestral Knowledge", 5), ("Shaman", "Enhancement", "Improved Ghost Wolf", 2),
             ("Shaman", "Enhancement", "Improved Shields", 3), ("Shaman", "Enhancement", "Toughness", 5),
             ("Shaman", "Restoration", "Improved Healing Wave", 5),
             ("Hero", "Hero", "Overdraw", 3), ("Hero", "Hero", "Adrenal Surge", 2), ("Hero", "Hero", "Thrift", 3),
         ]),
    dict(id=20, name="Polymath",
         description="A signature from every class and the Hero line to tie them together: Jack of All Trades, Repertoire, Wildcard Surge.",
         abilities=[
             ("Hero", "Makeshift Strike"), ("Rogue", "Sinister Strike"), ("Mage", "Fireball"), ("Paladin", "Holy Light"),
             ("Warlock", "Corruption"), ("Druid", "Rejuvenation"), ("Warrior", "Charge"),
             ("Priest", "Power Word: Shield"), ("Hunter", "Arcane Shot"), ("Rogue", "Evasion"), ("Warlock", "Fear"),
             ("Shaman", "Flame Shock"), ("Hero", "Crossdraw"), ("Hero", "Borrowed Stance"), ("Mage", "Blink"),
             ("Priest", "Flash Heal"), ("Mage", "Ice Block"), ("Shaman", "Chain Lightning"), ("Paladin", "Divine Shield"),
             ("Warrior", "Whirlwind"), ("Druid", "Barkskin"), ("Shaman", "Earth Shield"), ("Warrior", "Recklessness"),
             ("Hero", "Repertoire"), ("Death Knight", "Death Grip"), ("Hero", "Wildcard Surge"),
             ("Paladin", "Avenging Wrath"),
         ],
         talents=[
             ("Hero", "Hero", "Weave", 3), ("Hero", "Hero", "Sharpened", 3), ("Hero", "Hero", "Encore", 3),
             ("Hero", "Hero", "Two Schools", 5), ("Hero", "Hero", "Jack of All Trades", 5),
             ("Rogue", "Combat", "Precision", 5), ("Paladin", "Protection", "Divine Strength", 5),
             ("Priest", "Discipline", "Twin Disciplines", 5), ("Druid", "Restoration", "Naturalist", 5),
             ("Shaman", "Elemental", "Concussion", 5), ("Warlock", "Affliction", "Improved Corruption", 5),
             ("Hunter", "Marksmanship", "Lethal Shots", 5), ("Paladin", "Retribution", "Conviction", 5),
             ("Warrior", "Fury", "Cruelty", 5), ("Mage", "Fire", "Improved Fireball", 5),
             ("Mage", "Arcane", "Arcane Subtlety", 2),
         ]),
]


# =============================================================================
# conf
# =============================================================================

def read_conf(path):
    """The handful of Classless settings the schedule depends on, with the
    shipped defaults if the file lacks a key."""
    # enforce_rows is off: the server has no points-in-tree gate any more (see
    # BuyTalentRank), only the tier's level, so the simulation must not add one
    cfg = dict(starting_ae=3, essence_start=4, te_start=10, ae_per_level=1, te_per_level=1,
               costs=[1, 2, 3, 5, 8], talent_cost=1, talent_flat=0, enforce_rows=0, forged=1,
               respect_levels=1, trainer_only=1, include_racials=0, include_passives=1,
               include_dk=1, elemental=1, elemental_in_pool=1, rarity_bump=1,
               replace_ability_talents=1)
    keys = {
        "ClasslessWildcard.ReplaceAbilityTalents": ("replace_ability_talents", int),
        "ClasslessWildcard.Elemental.Enable": ("elemental", int),
        "ClasslessWildcard.Elemental.InPool": ("elemental_in_pool", int),
        "ClasslessWildcard.Elemental.RarityBump": ("rarity_bump", int),
        "ClasslessWildcard.Classless.StartingAbilityEssence": ("starting_ae", int),
        "ClasslessWildcard.Classless.EssenceStartLevel": ("essence_start", int),
        "ClasslessWildcard.Classless.TalentEssenceStartLevel": ("te_start", int),
        "ClasslessWildcard.Classless.AbilityEssencePerLevel": ("ae_per_level", int),
        "ClasslessWildcard.Classless.TalentEssencePerLevel": ("te_per_level", int),
        "ClasslessWildcard.Classless.AbilityCostByRarity": ("costs", lambda s: [int(x) for x in s.strip('"').split(",")]),
        "ClasslessWildcard.Classless.TalentCostPerRank": ("talent_cost", int),
        "ClasslessWildcard.Classless.TalentFlatCost": ("talent_flat", int),
        "ClasslessWildcard.Classless.EnforceTalentRows": ("enforce_rows", int),
        "ClasslessWildcard.RespectLevelReqs": ("respect_levels", int),
        "ClasslessWildcard.TrainerTaughtOnly": ("trainer_only", int),
        "ClasslessWildcard.IncludeRacials": ("include_racials", int),
        "ClasslessWildcard.IncludePassives": ("include_passives", int),
        "ClasslessWildcard.IncludeDeathKnight": ("include_dk", int),
        "ClasslessWildcard.Forged.Enable": ("forged", int),
    }
    if os.path.exists(path):
        for line in io.open(path, encoding="utf-8"):
            m = re.match(r"^\s*([A-Za-z0-9_.]+)\s*=\s*(.+?)\s*$", line)
            if m and m.group(1) in keys:
                name, conv = keys[m.group(1)]
                try:
                    cfg[name] = conv(m.group(2))
                except ValueError:
                    pass
    return cfg


# =============================================================================
# the pool, the way BuildLibrary builds it
# =============================================================================

class Pool:
    def __init__(self, dbc_dir, core_dir, cfg, manifest=None):
        self.cfg = cfg
        self.spell = Dbc(os.path.join(dbc_dir, "Spell.dbc"))
        self.sla = Dbc(os.path.join(dbc_dir, "SkillLineAbility.dbc"))
        self.skill = Dbc(os.path.join(dbc_dir, "SkillLine.dbc"))
        self.talent = Dbc(os.path.join(dbc_dir, "Talent.dbc"))
        self.tab = Dbc(os.path.join(dbc_dir, "TalentTab.dbc"))
        base = os.path.join(core_dir, "data", "sql", "base", "db_world")
        # _talents first: _trainer_levels needs to know which spells belong to a
        # talent before it decides what a class learns
        self._talents()
        self.learn_levels = self._trainer_levels(os.path.join(base, "trainer_spell.sql"))
        self.first_of, self.chain_of = self._ranks(os.path.join(base, "spell_ranks.sql"))
        self._abilities()
        self._variants(manifest)
        self._forged()
        self._replaced_talents()
        self._hero_talents()

    # ---- helpers ------------------------------------------------------------
    def name(self, spell_id):
        r = self.spell.row_of(spell_id)
        return self.spell.s(r, F["SpellName"]) if r is not None else ""

    def level(self, spell_id):
        r = self.spell.row_of(spell_id)
        return (self.spell.u(r, F["SpellLevel"]) or self.spell.u(r, F["BaseLevel"])) if r is not None else 0

    def _trainer_levels(self, path):
        levels = {}
        if not os.path.exists(path):
            sys.exit("trainer_spell.sql not found at %s (pass --core)" % path)
        text = io.open(path, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r"\((\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(-?\d+)\)", text):
            sid, req_line, req_lvl = int(m.group(2)), int(m.group(4)), int(m.group(9))
            if req_line or not sid:
                continue
            row = self.spell.row_of(sid)
            if row is None:
                continue
            wrapper = False
            for e in range(3):
                if self.spell.u(row, F["Effect"] + e) == E_LEARN_SPELL and self.spell.u(row, F["EffectTriggerSpell"] + e):
                    taught = self.spell.u(row, F["EffectTriggerSpell"] + e)
                    levels[taught] = min(levels.get(taught, 255), req_lvl)
                    wrapper = True
            if not wrapper:
                levels[sid] = min(levels.get(sid, 255), req_lvl)

        # Trainers are not the only way a class gets a spell, and the module
        # counts the other two as well (see ClasslessMgr::BuildLibrary). Keep
        # these in step with it or the generator plans builds out of a library
        # the server does not have.
        class_spells = set()
        class_lines = {self.skill.u(r, 0) for r in range(self.skill.rows)
                       if self.skill.u(r, 1) == SKILL_CATEGORY_CLASS}
        for r in range(self.sla.rows):
            line, sp, cls = self.sla.u(r, 1), self.sla.u(r, 2), self.sla.u(r, 4)
            if not cls or line not in class_lines:
                continue
            class_spells.add(sp)
            # learned with the class itself (AcquireMethod 1 or 2)
            if self.sla.u(r, F_ACQUIRE_METHOD) not in (1, 2):
                continue
            row = self.spell.row_of(sp)
            if row is None or self.spell.u(row, F["Attributes"]) & ATTR0_PASSIVE:
                continue
            lvl = self.spell.u(row, F["SpellLevel"]) or self.spell.u(row, F["BaseLevel"])
            if lvl and sp not in levels:
                levels[sp] = min(lvl, 255)

        # taught by a class quest's reward spell ("Path of Defense" and friends).
        # A TALENT that teaches a spell does not count: the spell belongs to the
        # talent, and making it an ability line would take the talent off the
        # tree and strand whatever depends on it.
        for r in range(self.spell.rows):
            if self.spell.u(r, 0) in self.talent_spells:
                continue
            for e in range(3):
                if self.spell.u(r, F["Effect"] + e) != E_LEARN_SPELL:
                    continue
                taught = self.spell.u(r, F["EffectTriggerSpell"] + e)
                if not taught or taught in levels or taught not in class_spells:
                    continue
                trow = self.spell.row_of(taught)
                if trow is None:
                    continue
                lvl = self.spell.u(trow, F["SpellLevel"]) or self.spell.u(trow, F["BaseLevel"]) or 1
                levels[taught] = min(lvl, 255)
        return levels

    def _ranks(self, path):
        first_of, chains = {}, collections.defaultdict(dict)
        if not os.path.exists(path):
            sys.exit("spell_ranks.sql not found at %s (pass --core)" % path)
        text = io.open(path, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r"\((\d+),\s*(\d+),\s*(\d+)\)", text):
            first, sid, rank = int(m.group(1)), int(m.group(2)), int(m.group(3))
            first_of[sid] = first
            chains[first][rank] = sid
        chain_of = {}
        for first, ranks in chains.items():
            out = []
            for rank in sorted(ranks):
                sid = ranks[rank]
                if self.spell.row_of(sid) is None:
                    break          # GetNextSpellInChain stops at a missing rank
                out.append(sid)
            chain_of[first] = out
        return first_of, chain_of

    def _talents(self):
        self.tabs = {}     # tabId -> (name, classMask)
        for r in range(self.tab.rows):
            if self.tab.u(r, 21):        # pet talent tabs
                continue
            self.tabs[self.tab.u(r, 0)] = (self.tab.s(r, 1), self.tab.u(r, 20))
        self.talent_spells = set()
        self.talents = {}  # talentId -> dict
        self.talent_row_of_spell = {}
        for r in range(self.talent.rows):
            tab_id = self.talent.u(r, 1)
            ranks = [self.talent.u(r, k) for k in range(4, 9)]
            for sp in ranks:
                if sp:
                    self.talent_spells.add(sp)
            tab = self.tabs.get(tab_id)
            if not tab or not tab[1]:
                continue
            if not self.cfg["include_dk"] and tab[1] == CLASS_BITS["Death Knight"]:
                continue
            spells = []
            for sp in ranks:
                if not sp or self.spell.row_of(sp) is None:
                    break
                spells.append(sp)
            if not spells:
                continue
            t = dict(id=self.talent.u(r, 0), tab=tab_id, tab_name=tab[0], class_mask=tab[1],
                     row=self.talent.u(r, 2), col=self.talent.u(r, 3), spells=spells,
                     max_rank=len(spells), depends_on=self.talent.u(r, 13),
                     depends_on_rank=self.talent.u(r, 16), name=self.name(spells[0]))
            self.talents[t["id"]] = t
            for sp in spells:
                self.talent_row_of_spell[sp] = t["row"]

    def _abilities(self):
        class_lines = {self.skill.u(r, 0) for r in range(self.skill.rows)
                       if self.skill.u(r, 1) == SKILL_CATEGORY_CLASS}
        dk = CLASS_BITS["Death Knight"]
        lines = {}   # first spell -> dict(class_mask)
        for r in range(self.sla.rows):
            line, sp, race, cls = self.sla.u(r, 1), self.sla.u(r, 2), self.sla.u(r, 3), self.sla.u(r, 4)
            if not cls or line not in class_lines:
                continue
            if race and not self.cfg["include_racials"]:
                continue
            if not self.cfg["include_dk"] and cls == dk:
                continue
            row = self.spell.row_of(sp)
            if row is None or not self.spell.s(row, F["SpellName"]):
                continue
            if sp in self.talent_spells:
                continue
            if self.spell.u(row, F["Attributes"]) & ATTR0_PASSIVE and not self.cfg["include_passives"]:
                continue
            if any(self.spell.u(row, F["Effect"] + e) in UTILITY_EFFECTS for e in range(3)):
                continue
            # ranged auto-attacks are not abilities to roll or buy
            if self.spell.u(row, F_ATTRIBUTES_EX2) & ATTR2_AUTO_REPEAT:
                continue
            first = self.first_of.get(sp, sp)
            if first in POOL_DISABLED:
                continue
            entry = lines.setdefault(first, dict(first=first, class_mask=0))
            entry["class_mask"] |= cls

        self.abilities = {}
        for first, e in lines.items():
            ranks = self.chain_of.get(first) or ([first] if self.spell.row_of(first) is not None else [])
            if not ranks:
                continue
            levels = [self.level(sp) for sp in ranks]
            if self.cfg["trainer_only"]:
                trained = False
                for i, sp in enumerate(ranks):
                    if sp in self.learn_levels:
                        trained = True
                        levels[i] = max(levels[i], self.learn_levels[sp])
                if not trained:
                    continue
                for i in range(1, len(levels)):
                    levels[i] = max(levels[i], levels[i - 1])
            row = self.spell.row_of(first)
            e.update(ranks=ranks, levels=levels, name=self.name(first),
                     passive=bool(self.spell.u(row, F["Attributes"]) & ATTR0_PASSIVE), enabled=True)
            rows = [self.talent_row_of_spell[sp] for sp in ranks if sp in self.talent_row_of_spell]
            if rows:
                need = 10 + max(rows) * 5
                if levels[0] < need:
                    shift = need - levels[0]
                    e["levels"] = [min(255, lv + shift) for lv in levels]
            e["rarity"] = rarity_from_level(e["levels"][0])
            e["cost"] = self.cfg["costs"][e["rarity"]]
            self.abilities[first] = e

        # dedupe by name: keep the most ranks, then the lowest id
        by_name = {}
        for first, e in sorted(self.abilities.items()):
            keep = by_name.get(e["name"])
            if keep is None:
                by_name[e["name"]] = e
            elif len(e["ranks"]) > len(keep["ranks"]):
                e["class_mask"] |= keep["class_mask"]
                keep["enabled"] = False
                by_name[e["name"]] = e
            else:
                keep["class_mask"] |= e["class_mask"]
                e["enabled"] = False

    def _variants(self, manifest):
        """Elemental variants, registered the way LoadVariants does: the
        base line's levels and class mask, the base rarity bumped by
        Elemental.RarityBump, and skipped when the base is not in the pool.
        The manifest lists every variant rank with its base line and the
        server SQL carries the same rows, so it is the one file to read."""
        self.variants = 0
        if not self.cfg["elemental"] or not self.cfg["elemental_in_pool"]:
            return
        if not manifest or not os.path.exists(manifest):
            print("note: no elemental manifest at %s; variants left out of the pool" % manifest)
            return
        data = json.load(io.open(manifest, encoding="utf-8"))
        lines = collections.defaultdict(list)
        for v in data.get("variants", []):
            lines[v["first"]].append(v)
        for first, ranks in sorted(lines.items()):
            ranks.sort(key=lambda v: v["rank"])
            # the manifest names the base RANK each variant rank copies; the
            # line it belongs to is that rank's first spell (a talent-taught
            # strike's variants start from its first trained rank, not the
            # talent spell)
            base = self.abilities.get(self.first_of.get(ranks[0]["base"], ranks[0]["base"]))
            if base is None or not base["enabled"] or first in self.abilities:
                continue
            levels = list(base["levels"][:len(ranks)])
            while len(levels) < len(ranks):
                levels.append(levels[-1] if levels else 1)
            rarity = min(base["rarity"] + self.cfg["rarity_bump"], len(RARITY_NAMES) - 1)
            self.abilities[first] = dict(
                first=first, class_mask=base["class_mask"], ranks=[v["id"] for v in ranks],
                levels=levels, name=ranks[0]["name"], passive=False, enabled=True,
                rarity=rarity, cost=self.cfg["costs"][rarity], variant=base["name"],
                element=ranks[0]["element"])
            self.variants += 1

    def _forged(self):
        """The Hero line, the way LoadForged registers it: every forged line
        that is not a challenge reward, its ranks at the levels the forged
        generator writes, its rarity from the recipe and its cost from that."""
        self.forged = 0
        if not self.cfg["forged"]:
            return
        for r in forged.RECIPES:
            if r.get("reward"):
                continue        # paid by a challenge run, never bought
            first = forged.block_of(forged.pinned_index(r["key"]))
            levels = [r["first_level"] + i * r["step"] for i in range(r["ranks"])]
            levels = [lv for lv in levels if lv <= 80]
            rarity = r["rarity"]
            self.abilities[first] = dict(
                first=first, class_mask=CLASS_BITS["Hero"], ranks=[first + i for i in range(len(levels))],
                levels=levels, name=r["name"], passive=bool(r.get("passive")), enabled=True,
                rarity=rarity, cost=self.cfg["costs"][rarity], forged=True)
            self.forged += 1

    def _hero_talents(self):
        """The Hero talent tab, as the forged generator writes it to
        talent_dbc: no prerequisites, tiers opening at 10 + 5 per row."""
        if not self.cfg["forged"]:
            return
        self.tabs[forged.HERO_TALENT_TAB] = ("Hero", CLASS_BITS["Hero"])
        for n, tal in enumerate(forged.TALENTS):
            tid = forged.TALENT_ID_BASE + n
            spells = [forged.TALENT_SPELL_BASE + n * forged.TALENT_SPELL_STRIDE + r for r in range(tal["ranks"])]
            self.talents[tid] = dict(id=tid, tab=forged.HERO_TALENT_TAB, tab_name="Hero",
                                     class_mask=CLASS_BITS["Hero"], row=tal["row"], col=tal["col"],
                                     spells=spells, max_rank=tal["ranks"], depends_on=0,
                                     depends_on_rank=0, name=tal["name"])

    def _replaced_talents(self):
        """Ability talents, the way ResolveTalentAbilityLines sees them: a
        talent whose rank spell heads an ability line, or teaches one through
        a learn effect, names that line. With ReplaceAbilityTalents on the
        talent leaves the pool and the line stands in for it: owning the
        ability meets a prerequisite on the talent and counts as one point in
        its tree."""
        self.replaced = {}       # talentId -> talent dict, with "lines"
        self.line_talents = collections.defaultdict(list)   # first spell -> replaced talent ids
        for t in self.talents.values():
            lines = []
            def add(sp):
                first = self.first_of.get(sp, sp)
                e = self.abilities.get(first)
                if e and e["enabled"] and first not in lines:
                    lines.append(first)
            for sp in t["spells"]:
                add(sp)
                row = self.spell.row_of(sp)
                for k in range(3):
                    if self.spell.u(row, F["Effect"] + k) == E_LEARN_SPELL and self.spell.u(row, F["EffectTriggerSpell"] + k):
                        add(self.spell.u(row, F["EffectTriggerSpell"] + k))
            t["lines"] = lines
        if not self.cfg["replace_ability_talents"]:
            return
        for tid in [tid for tid, t in self.talents.items() if t["lines"]]:
            t = self.talents.pop(tid)
            t["replaced"] = True
            self.replaced[tid] = t
            for first in t["lines"]:
                self.line_talents[first].append(tid)

    # ---- lookups ------------------------------------------------------------
    def find_ability(self, cls, name):
        bit = CLASS_BITS[cls]
        hits = [e for e in self.abilities.values()
                if e["enabled"] and e["name"] == name and e["class_mask"] & bit]
        if not hits:
            hits = [e for e in self.abilities.values() if e["enabled"] and e["name"] == name]
            if hits:
                return hits[0], "not a %s line in the pool; using the %s one" % (
                    cls, ", ".join(c for c, b in CLASS_BITS.items() if hits[0]["class_mask"] & b))
            return None, "no ability line named %r" % name
        return hits[0], ""

    def find_talent(self, cls, tab_name, name):
        bit = CLASS_BITS[cls]
        hits = [t for t in self.talents.values()
                if t["class_mask"] == bit and t["tab_name"] == tab_name and t["name"] == name]
        if not hits:
            hits = [t for t in self.replaced.values()
                    if t["class_mask"] == bit and t["tab_name"] == tab_name and t["name"] == name]
        return (hits[0], "") if hits else (None, "no talent %r in %s %s" % (name, cls, tab_name))

    # ---- catalog ------------------------------------------------------------
    def catalog(self, cls):
        bit = CLASS_BITS[cls]
        print("== %s abilities (unlock level, cost, name, ranks) ==" % cls)
        rows = sorted((e for e in self.abilities.values() if e["enabled"] and e["class_mask"] & bit),
                      key=lambda e: (e["levels"][0], e["name"]))
        for e in rows:
            tag = "  passive" if e["passive"] else ""
            if e.get("variant"):
                tag = "  %s variant of %s" % (e["element"], e["variant"])
            print("  L%-2d %d AE  %-32s %2d rank%s%s" % (e["levels"][0], e["cost"], e["name"], len(e["ranks"]),
                  "" if len(e["ranks"]) == 1 else "s", tag))
        print("== %s talents ==" % cls)
        for tab_id, (tab_name, mask) in sorted(self.tabs.items(), key=lambda kv: kv[1][0]):
            if mask != bit:
                continue
            print("  -- %s" % tab_name)
            everything = list(self.talents.values()) + list(self.replaced.values())
            for t in sorted((t for t in everything if t["tab"] == tab_id), key=lambda t: (t["row"], t["col"])):
                dep = ""
                if t["depends_on"] and t["depends_on"] in self.talents:
                    dep = "  needs %s %d" % (self.talents[t["depends_on"]]["name"], t["depends_on_rank"] + 1)
                elif t["depends_on"] and t["depends_on"] in self.replaced:
                    dep = "  needs the %s ability" % self.abilities[self.replaced[t["depends_on"]]["lines"][0]]["name"]
                if t.get("replaced"):
                    print("     tier %2d  %-34s an ability now: %s" % (
                        t["row"] + 1, t["name"], ", ".join(self.abilities[f]["name"] for f in t["lines"])))
                else:
                    print("     tier %2d  %-34s max %d%s" % (t["row"] + 1, t["name"], t["max_rank"], dep))


# =============================================================================
# resolve + simulate
# =============================================================================

def resolve(pool, build):
    problems = []
    abilities = []
    for cls, name in build["abilities"]:
        e, note = pool.find_ability(cls, name)
        if e is None:
            problems.append("%s: %s" % (build["name"], note))
            continue
        if note:
            problems.append("%s: %s %s" % (build["name"], name, note))
        if any(a["first"] == e["first"] for a in abilities):
            problems.append("%s: %s listed twice" % (build["name"], name))
            continue
        e = dict(e, listed_as=cls)    # the class this build takes it from
        abilities.append(e)
    talents = []
    for cls, tab, name, rank in build["talents"]:
        t, note = pool.find_talent(cls, tab, name)
        if t is None:
            problems.append("%s: %s" % (build["name"], note))
            continue
        if t.get("replaced"):
            # an ability talent: not a talent any more. The build lists the
            # ability itself if it wants the spell; here it is just dropped.
            print("  note: %s: the %s talent is the %s ability now; dropped from the talent list%s" % (
                build["name"], name, ", ".join(pool.abilities[f]["name"] for f in t["lines"]),
                "" if any(a["first"] in t["lines"] for a in abilities) else " (the build does not buy the ability)"))
            continue
        if rank > t["max_rank"]:
            problems.append("%s: %s has %d ranks, asked for %d" % (build["name"], name, t["max_rank"], rank))
            rank = t["max_rank"]
        talents.append((t, rank))
    # abilities are bought in unlock order; keep list order within a level
    abilities.sort(key=lambda e: e["levels"][0])
    # talents are bought strictly in list order, so a high tier listed early
    # would hold back every cheaper rank after it: buy them tier by tier,
    # keeping list order within a tier (a prerequisite in the same tier is
    # listed first)
    talents.sort(key=lambda tr: tr[0]["row"])
    return abilities, talents, problems + design_problems(pool, build, abilities, talents)


MAX_SHARE = 0.55        # no one source supplies more than this share of a build
EARLY = 10              # every main source has an ability unlocking by this level
MIN_HERO = 3            # Hero line abilities in every build

RECIPE_KEY = {r["name"]: r["key"] for r in forged.RECIPES}
# What each Hero talent needs the build to own: "any" of the lines it modifies
# (read off the talent's own `affects`), or for the scripted ones the lines
# their script reads. "all" lists lines that must every one be owned.
HERO_TALENT_LINES = {t["name"]: dict(any=set(t["affects"]), all=set())
                     for t in forged.TALENTS if t.get("affects")}
HERO_TALENT_LINES.update({
    "Improvised Arsenal": dict(any=set(), all={"makeshift_strike", "hurl"}),
    "Field Repairs": dict(any={"second_nature", "adrenaline"}, all=set()),
    "Last Reserve": dict(any=set(), all={"ward_off"}),
    "Venom Handler": dict(any=set(), all={"venom_beetle"}),
    "Medicinal Venom": dict(any=set(), all={"venom_beetle"}),
    "Field Study": dict(any=set(), all={"emberfeed", "bleed_over"}),
    "Opportunist": dict(any={"kick_dirt", "vertigo", "sinkhole"}, all=set()),
    "Adrenal Surge": dict(any=set(), all={"quickening"}),
    "Overclocked": dict(any=set(), all={"reclaimed_sentry"}),
    "Broad Strokes": dict(any=set(), all={"overflow"}),
})
JACK_STEP = next(t["extra"][0] for t in forged.TALENTS if t["name"] == "Jack of All Trades")


def source_of(e):
    """Which source an ability line counts for: "Hero", or the class it was
    listed under (a line several classes share counts once, for the first)."""
    if e.get("forged"):
        return "Hero"
    return e.get("listed_as") or "?"


def design_problems(pool, build, abilities, talents):
    """The archetype rules: a real mix of sources from the first levels, the
    Hero line in every build, and talents from more than one tree."""
    out = []
    name = build["name"]
    counts = collections.Counter(source_of(e) for e in abilities)
    first = {}
    for e in abilities:
        first.setdefault(source_of(e), e["levels"][0])
    classes = [s for s in counts if s != "Hero"]
    if len(classes) < 2:
        out.append("%s: abilities from %d class(es); an archetype mixes at least two" % (name, len(classes)))
    if counts.get("Hero", 0) < MIN_HERO:
        out.append("%s: %d Hero line abilities; every archetype uses at least %d" % (name, counts.get("Hero", 0), MIN_HERO))
    core = build.get("core")      # a build may be built around one source on purpose
    for src, n in counts.items():
        if src != core and n > MAX_SHARE * len(abilities):
            out.append("%s: %s supplies %d of %d abilities, more than %d%%" % (name, src, n, len(abilities), MAX_SHARE * 100))
    for src, n in counts.most_common():
        # the main sources (more than three abilities) all show up early
        if n > 3 and first[src] > EARLY:
            out.append("%s: the first %s ability unlocks at %d; every main source starts by level %d"
                       % (name, src, first[src], EARLY))
    trees = {t["tab"] for t, _ in talents}
    if len(trees) < 2:
        out.append("%s: talents from one tree; an archetype draws on at least two" % name)
    # a Hero talent that reaches no line the build owns is ranks spent on nothing
    owned = {RECIPE_KEY.get(e["name"]) for e in abilities if e.get("forged")}
    for t, _ in talents:
        if t["tab_name"] != "Hero":
            continue
        lines = HERO_TALENT_LINES.get(t["name"])
        if lines is None:
            continue
        missing = sorted(lines["all"] - owned)
        if lines["any"] and not lines["any"] & owned:
            missing.append("one of " + "/".join(sorted(lines["any"])))
        if missing:
            out.append("%s: %s needs %s, which the build does not buy"
                       % (name, t["name"], " and ".join(missing)))
    # Jack of All Trades pays one step per three classes owned (the Hero line
    # is no class); OwnedClassMask counts class talents as well as abilities
    jack = [r for t, r in talents if t["name"] == "Jack of All Trades" and t["tab_name"] == "Hero"]
    if jack:
        mask = 0
        for e in abilities:
            if not e.get("forged"):
                mask |= e["class_mask"]
        for t, _ in talents:
            if t["tab_name"] != "Hero":
                mask |= t["class_mask"]
        classes = bin(mask & 0x7FF).count("1")
        if classes < JACK_STEP:
            out.append("%s: Jack of All Trades pays per %d classes and the build has %d; it does nothing"
                       % (name, JACK_STEP, classes))
    total = sum(r for _, r in talents)
    if total != 71:
        out.append("%s: %d talent ranks planned; the essence schedule pays exactly 71 by level 80" % (name, total))
    return out


def mix_report(abilities, talents):
    counts = collections.Counter(source_of(e) for e in abilities)
    first = {}
    for e in abilities:
        first.setdefault(source_of(e), e["levels"][0])
    trees = collections.Counter()
    for t, r in talents:
        trees[t["tab_name"]] += r
    early = [e["name"] for e in abilities if e["levels"][0] <= 12]
    return ("  mix: %s" + "\n" + "  trees: %s" + "\n" + "  levels 1-12: %s") % (
        ", ".join("%s %d (from L%d)" % (s, n, first[s]) for s, n in counts.most_common()),
        ", ".join("%s %d" % kv for kv in trees.most_common()),
        ", ".join(early))


LATE_LEVELS = 3   # an ability bought more than this many levels after it unlocks is a pacing problem


def simulate(pool, build, abilities, talents, verbose=False):
    """Follow the build from 1 to 80 the way FollowArchetype does: abilities
    strictly in build order while unlocked and affordable, then talents in
    order. Returns a list of problems (empty = the build keeps pace)."""
    cfg = pool.cfg
    problems = []
    ae, te = cfg["starting_ae"], 0
    owned = set()
    ranks = collections.Counter()
    tab_points = collections.Counter()
    ledger = []
    counted = set()            # replaced talents already credited as a tree point
    ai = 0                     # next ability in strict order
    ti = 0                     # next talent entry in strict order
    for level in range(1, 81):
        if level >= cfg["essence_start"]:
            ae += cfg["ae_per_level"]
        if level >= cfg["te_start"]:
            te += cfg["te_per_level"]
        bought, stalled = [], []
        while ai < len(abilities):
            e = abilities[ai]
            unlock = e["levels"][0] if cfg["respect_levels"] else 1
            if unlock > level:
                break                       # waits for the level
            if ae < e["cost"]:
                stalled.append(e["name"])   # waits for essence
                break
            ae -= e["cost"]
            owned.add(e["first"])
            # an ability standing in for a talent counts as a point in its tree
            for tid in pool.line_talents.get(e["first"], ()):
                if tid not in counted:
                    counted.add(tid)
                    tab_points[pool.replaced[tid]["tab"]] += 1
            ai += 1
            late = level - unlock
            bought.append("%s (%d AE%s)" % (e["name"], e["cost"], ", %d late" % late if late else ""))
            if late > LATE_LEVELS:
                problems.append("%s: %s unlocks at %d but the build only affords it at %d"
                                % (build["name"], e["name"], unlock, level))
        got_ranks = []
        while ti < len(talents):
            t, target = talents[ti]
            if ranks[t["id"]] >= target:
                ti += 1
                continue
            cost = 0 if (cfg["talent_flat"] and ranks[t["id"]] > 0) else cfg["talent_cost"]
            if te < cost:
                break
            rep = pool.replaced.get(t["depends_on"]) if t["depends_on"] else None
            if rep is not None:
                # the prerequisite is an ability now: owning it is what counts
                if not any(f in owned for f in rep["lines"]):
                    problems.append("%s: %s needs the %s ability first; add it to the build's abilities"
                                    % (build["name"], t["name"], pool.abilities[rep["lines"][0]]["name"]))
                    ti = len(talents)
                    break
            elif t["depends_on"] and ranks[t["depends_on"]] < t["depends_on_rank"] + 1:
                dep = pool.talents.get(t["depends_on"])
                problems.append("%s: %s needs %s %d first; list it earlier"
                                % (build["name"], t["name"], dep["name"] if dep else t["depends_on"], t["depends_on_rank"] + 1))
                ti = len(talents)   # the server would sit on this forever
                break
            if cfg["enforce_rows"] and tab_points[t["tab"]] < t["row"] * 5:
                break               # wait for more points in the tree
            if cfg["respect_levels"] and level < 10 + t["row"] * 5:
                break               # the tier's own level (BuyTalentRank enforces it too)
            te -= cost
            ranks[t["id"]] += 1
            tab_points[t["tab"]] += 1
            got_ranks.append(t["name"])
        if verbose and (bought or got_ranks or stalled):
            ledger.append("  L%-2d AE %2d TE %2d  %s%s%s" % (
                level, ae, te, "; ".join(bought), ("  |  talents: " + ", ".join(got_ranks)) if got_ranks else "",
                ("  |  STALLED " + ", ".join(stalled)) if stalled else ""))
    for t, target in talents:
        if ranks[t["id"]] < target:
            problems.append("%s: %s only reached rank %d of %d by level 80"
                            % (build["name"], t["name"], ranks[t["id"]], target))
            break
    for e in abilities:
        if e["first"] not in owned:
            problems.append("%s: %s is never bought by level 80 (unlocks at %d)" % (build["name"], e["name"], e["levels"][0]))
    summary = "  %d abilities (%d AE), %d talent ranks; AE left %d, TE left %d" % (
        len(abilities), sum(e["cost"] for e in abilities), sum(r for _, r in talents), ae, te)
    return problems, ledger, summary


# =============================================================================
# output
# =============================================================================

HEADER = """-- mod-classless-wildcard: starter archetypes, generated by
-- data/sql/generators/gen_archetypes.py. Edit the builds there, not here.
--
-- An archetype is a build template a Classless Hero follows from level 1 to
-- 80: abilities = first-rank spell ids in unlock order, talents = talentId:rank
-- in purchase order. The server buys each entry as it becomes available.

CREATE TABLE IF NOT EXISTS `cw_archetypes` (
  `id` INT UNSIGNED NOT NULL,
  `name` VARCHAR(64) NOT NULL,
  `description` VARCHAR(255) NOT NULL DEFAULT '',
  `abilities` TEXT,
  `talents` TEXT,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Classless starter archetypes';

DELETE FROM `cw_archetypes` WHERE `id` IN (%s);
INSERT INTO `cw_archetypes` (`id`, `name`, `description`, `abilities`, `talents`) VALUES
"""


def write_sql(path, rows):
    out = [HEADER % ", ".join(str(r["id"]) for r in rows)]
    lines = []
    for r in rows:
        lines.append("(%d, '%s',\n '%s',\n '%s',\n '%s')" % (
            r["id"], r["name"].replace("'", "''"), r["description"].replace("'", "''"),
            ",".join(str(x) for x in r["abilities"]), ",".join("%d:%d" % x for x in r["talents"])))
    out.append(",\n".join(lines) + ";\n")
    io.open(path, "w", encoding="utf-8", newline="\n").write("".join(out))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dbc", default=DEFAULT_DBC)
    ap.add_argument("--core", default=DEFAULT_CORE, help="AzerothCore checkout (for trainer_spell.sql, spell_ranks.sql)")
    ap.add_argument("--conf", default=DEFAULT_CONF)
    ap.add_argument("--out", default=OUT_SQL)
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST,
                    help="elemental variant manifest written by gen_elemental_variants.py")
    ap.add_argument("--catalog", metavar="CLASS", help="print the pool for one class and exit")
    ap.add_argument("--ledger", action="store_true", help="print every purchase of the simulation")
    args = ap.parse_args(argv)

    pool = Pool(args.dbc, args.core, read_conf(args.conf), args.manifest)
    print("pool: %d ability lines (%d elemental variants, %d Hero line), %d talents" % (
        sum(1 for e in pool.abilities.values() if e["enabled"]), pool.variants, pool.forged, len(pool.talents)))
    if args.catalog:
        if args.catalog not in CLASS_BITS:
            sys.exit("class must be one of: " + ", ".join(CLASS_BITS))
        pool.catalog(args.catalog)
        return 0

    rows, failed = [], False
    for build in BUILDS:
        print("== %s" % build["name"])
        abilities, talents, problems = resolve(pool, build)
        sim_problems, ledger, summary = simulate(pool, build, abilities, talents, verbose=args.ledger)
        problems += sim_problems
        for line in ledger:
            print(line)
        print(summary)
        print(mix_report(abilities, talents))
        for p in problems:
            print("  PROBLEM " + p)
        failed = failed or bool(problems)
        rows.append(dict(id=build["id"], name=build["name"], description=build["description"],
                         abilities=[e["first"] for e in abilities],
                         talents=[(t["id"], rank) for t, rank in talents]))
    if failed:
        print("\nnot written: fix the problems above")
        return 1
    write_sql(args.out, rows)
    print("\nwrote %s: %d archetypes" % (args.out, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
