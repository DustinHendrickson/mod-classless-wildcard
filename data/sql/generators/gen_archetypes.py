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

MODULE = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir, os.pardir))
DEFAULT_CORE = os.path.abspath(os.path.join(MODULE, os.pardir, os.pardir))
DEFAULT_CONF = os.path.join(MODULE, "conf", "classless_wildcard.conf.dist")
OUT_SQL = os.path.join(HERE, os.pardir, "db-world", "cw_archetypes.sql")
DEFAULT_MANIFEST = os.path.join(MODULE, "client-patch", "elemental_manifest.json")

CLASS_BITS = {"Warrior": 1, "Paladin": 2, "Hunter": 4, "Rogue": 8, "Priest": 16,
              "Death Knight": 32, "Shaman": 64, "Mage": 128, "Warlock": 256, "Druid": 1024}
SKILL_CATEGORY_CLASS = 7
ATTR0_PASSIVE = 0x40
UTILITY_EFFECTS = {25, 60, 40, 39, 47, 118, 78}   # weapon, proficiency, dual wield, language, trade skill, skill, attack
E_LEARN_SPELL = 36
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
    dict(id=1, name="Blade Dancer",
         description="Fast melee striker: rogue strikes backed by warrior mobility.",
         abilities=[
             ("Rogue", "Sinister Strike"), ("Rogue", "Eviscerate"), ("Rogue", "Stealth"),
             ("Warrior", "Charge"), ("Warrior", "Rend"), ("Rogue", "Backstab"), ("Rogue", "Gouge"),
             ("Warrior", "Hamstring"), ("Rogue", "Evasion"),
             ("Rogue", "Slice and Dice"), ("Rogue", "Kick"), ("Rogue", "Garrote"), ("Rogue", "Ambush"),
             ("Rogue", "Rupture"), ("Rogue", "Vanish"), ("Warrior", "Execute"),
             ("Rogue", "Cheap Shot"), ("Rogue", "Kidney Shot"), ("Warrior", "Berserker Rage"),
             ("Warrior", "Whirlwind"), ("Warrior", "Pummel"), ("Warrior", "Mortal Strike"),
             ("Warrior", "Recklessness"),
             ("Rogue", "Cloak of Shadows"), ("Rogue", "Shiv"), ("Rogue", "Tricks of the Trade"), ("Rogue", "Fan of Knives"),
         ],
         talents=[
             ("Rogue", "Combat", "Improved Sinister Strike", 2), ("Rogue", "Combat", "Dual Wield Specialization", 5),
             ("Rogue", "Combat", "Precision", 5), ("Rogue", "Combat", "Improved Slice and Dice", 2),
             ("Rogue", "Combat", "Endurance", 2),
             ("Rogue", "Combat", "Lightning Reflexes", 3), ("Rogue", "Combat", "Aggression", 5),
             ("Rogue", "Combat", "Blade Flurry", 1), ("Rogue", "Combat", "Hack and Slash", 5),
             ("Rogue", "Combat", "Weapon Expertise", 2), ("Rogue", "Combat", "Blade Twisting", 2),
             ("Rogue", "Combat", "Vitality", 3), ("Rogue", "Combat", "Adrenaline Rush", 1), ("Rogue", "Combat", "Nerves of Steel", 2),
             ("Rogue", "Combat", "Combat Potency", 5),
             ("Rogue", "Combat", "Surprise Attacks", 1), ("Rogue", "Combat", "Savage Combat", 2),
             ("Rogue", "Combat", "Prey on the Weak", 2),
             ("Rogue", "Combat", "Killing Spree", 1),
             ("Warrior", "Arms", "Improved Rend", 2), ("Warrior", "Arms", "Deflection", 3),
             ("Warrior", "Arms", "Improved Charge", 2), ("Warrior", "Arms", "Tactical Mastery", 3),
             ("Warrior", "Arms", "Improved Overpower", 2), ("Warrior", "Arms", "Anger Management", 1),
             ("Warrior", "Arms", "Impale", 2),
             ("Warrior", "Arms", "Deep Wounds", 3), ("Warrior", "Arms", "Taste for Blood", 2),
         ]),
    dict(id=2, name="Battle Mage",
         description="Armored caster: fireballs up close, sword in hand.",
         abilities=[
             ("Mage", "Fireball"), ("Mage", "Frost Armor"), ("Mage", "Arcane Intellect"),
             ("Warrior", "Charge"), ("Mage", "Frostbolt"), ("Warrior", "Rend"), ("Mage", "Fire Blast"),
             ("Mage", "Polymorph"), ("Mage", "Arcane Missiles"),
             ("Mage", "Frost Nova"), ("Warrior", "Overpower"), ("Mage", "Arcane Explosion"), ("Mage", "Flamestrike"),
             ("Mage", "Blink"), ("Mage", "Pyroblast"), ("Mage", "Scorch"), ("Mage", "Counterspell"),
             ("Mage", "Ice Block"), ("Warrior", "Intercept"), ("Mage", "Mage Armor"), ("Warrior", "Whirlwind"),
             ("Mage", "Ice Barrier"),
             ("Mage", "Dragon's Breath"), ("Warrior", "Recklessness"),
             ("Mage", "Molten Armor"), ("Mage", "Frostfire Bolt"), ("Mage", "Mirror Image"),
         ],
         talents=[
             ("Mage", "Fire", "Improved Fire Blast", 2), ("Mage", "Fire", "Incineration", 3), ("Mage", "Fire", "Improved Fireball", 5),
             ("Mage", "Fire", "Ignite", 5), ("Mage", "Fire", "World in Flames", 3),
             ("Mage", "Fire", "Impact", 3), ("Mage", "Fire", "Pyroblast", 1),
             ("Mage", "Fire", "Burning Soul", 2),
             ("Mage", "Fire", "Master of Elements", 3), ("Mage", "Fire", "Critical Mass", 3),
             ("Mage", "Fire", "Blast Wave", 1), ("Mage", "Fire", "Fire Power", 5),
             ("Mage", "Fire", "Pyromaniac", 3), ("Mage", "Fire", "Combustion", 1), ("Mage", "Fire", "Molten Fury", 2),
             ("Mage", "Fire", "Empowered Fire", 3),
             ("Mage", "Fire", "Dragon's Breath", 1),
             ("Mage", "Fire", "Hot Streak", 3), ("Mage", "Fire", "Burnout", 1),
             ("Mage", "Fire", "Living Bomb", 1),
             ("Mage", "Fire", "Improved Scorch", 3), ("Mage", "Fire", "Flame Throwing", 1),
             ("Warrior", "Arms", "Improved Rend", 2), ("Warrior", "Arms", "Deflection", 3),
             ("Warrior", "Arms", "Improved Charge", 2), ("Warrior", "Arms", "Tactical Mastery", 3),
             ("Warrior", "Arms", "Improved Overpower", 2), ("Warrior", "Arms", "Anger Management", 1),
             ("Warrior", "Arms", "Impale", 2),
             ("Warrior", "Arms", "Deep Wounds", 3), ("Warrior", "Arms", "Taste for Blood", 2),
         ]),
    dict(id=3, name="Ranger of the Light",
         description="Hybrid archer-paladin: shoot from range, heal and bless in melee.",
         abilities=[
             ("Hunter", "Raptor Strike"), ("Paladin", "Holy Light"), ("Paladin", "Devotion Aura"),
             ("Hunter", "Serpent Sting"), ("Paladin", "Seal of Righteousness"), ("Paladin", "Judgement of Light"),
             ("Paladin", "Blessing of Might"), ("Hunter", "Arcane Shot"), ("Hunter", "Concussive Shot"),
             ("Hunter", "Aspect of the Hawk"), ("Hunter", "Wing Clip"), ("Paladin", "Blessing of Wisdom"),
             ("Hunter", "Aimed Shot"),
             ("Paladin", "Retribution Aura"), ("Hunter", "Multi-Shot"), ("Paladin", "Flash of Light"),
             ("Hunter", "Rapid Fire"), ("Hunter", "Feign Death"), ("Paladin", "Divine Shield"),
             ("Hunter", "Volley"), ("Paladin", "Holy Shock"), ("Paladin", "Cleanse"), ("Paladin", "Hammer of Wrath"),
             ("Hunter", "Steady Shot"),
             ("Hunter", "Tranquilizing Shot"), ("Paladin", "Avenging Wrath"), ("Hunter", "Kill Shot"),
         ],
         talents=[
             ("Hunter", "Marksmanship", "Lethal Shots", 5), ("Hunter", "Marksmanship", "Focused Aim", 3),
             ("Hunter", "Marksmanship", "Careful Aim", 3), ("Hunter", "Marksmanship", "Mortal Shots", 5),
             ("Hunter", "Marksmanship", "Go for the Throat", 2), ("Hunter", "Marksmanship", "Aimed Shot", 1),
             ("Hunter", "Marksmanship", "Rapid Killing", 2), ("Hunter", "Marksmanship", "Improved Stings", 3),
             ("Hunter", "Marksmanship", "Readiness", 1), ("Hunter", "Marksmanship", "Barrage", 3),
             ("Hunter", "Marksmanship", "Combat Experience", 2), ("Hunter", "Marksmanship", "Ranged Weapon Specialization", 3),
             ("Hunter", "Marksmanship", "Piercing Shots", 3),
             ("Hunter", "Marksmanship", "Trueshot Aura", 1), ("Hunter", "Marksmanship", "Improved Barrage", 3),
             ("Hunter", "Marksmanship", "Master Marksman", 5),
             ("Hunter", "Marksmanship", "Marked for Death", 5), ("Hunter", "Marksmanship", "Chimera Shot", 1),
             ("Paladin", "Holy", "Spiritual Focus", 5), ("Paladin", "Holy", "Seals of the Pure", 5),
             ("Paladin", "Holy", "Healing Light", 3), ("Paladin", "Holy", "Divine Intellect", 5),
             ("Paladin", "Holy", "Unyielding Faith", 2), ("Paladin", "Holy", "Aura Mastery", 1),
         ]),
    dict(id=4, name="Shadow Mender",
         description="Priest hybrid: shield and mend allies, wither foes with shadow.",
         abilities=[
             ("Priest", "Smite"), ("Priest", "Lesser Heal"), ("Priest", "Power Word: Fortitude"),
             ("Priest", "Shadow Word: Pain"), ("Priest", "Power Word: Shield"), ("Priest", "Renew"), ("Priest", "Fade"),
             ("Priest", "Mind Blast"), ("Priest", "Inner Fire"), ("Priest", "Psychic Scream"), ("Priest", "Heal"),
             ("Priest", "Dispel Magic"), ("Priest", "Flash Heal"), ("Priest", "Mind Flay"),
             ("Priest", "Prayer of Healing"), ("Priest", "Shadow Protection"), ("Priest", "Mind Control"),
             ("Priest", "Abolish Disease"), ("Priest", "Greater Heal"),
             ("Priest", "Prayer of Fortitude"), ("Priest", "Vampiric Touch"),
             ("Priest", "Shadow Word: Death"), ("Priest", "Binding Heal"), ("Priest", "Mind Sear"), ("Priest", "Divine Hymn"),
         ],
         talents=[
             ("Priest", "Shadow", "Spirit Tap", 3), ("Priest", "Shadow", "Darkness", 5),
             ("Priest", "Shadow", "Improved Shadow Word: Pain", 2), ("Priest", "Shadow", "Shadow Focus", 3),
             ("Priest", "Shadow", "Improved Mind Blast", 5), ("Priest", "Shadow", "Mind Flay", 1),
             ("Priest", "Shadow", "Shadow Weaving", 3), ("Priest", "Shadow", "Shadow Reach", 2),
             ("Priest", "Shadow", "Vampiric Embrace", 1),
             ("Priest", "Shadow", "Focused Mind", 3), ("Priest", "Shadow", "Mind Melt", 2),
             ("Priest", "Shadow", "Shadowform", 1), ("Priest", "Shadow", "Shadow Power", 5),
             ("Priest", "Shadow", "Misery", 3), ("Priest", "Shadow", "Improved Shadowform", 2),
             ("Priest", "Shadow", "Vampiric Touch", 1), ("Priest", "Shadow", "Pain and Suffering", 3),
             ("Priest", "Shadow", "Twisted Faith", 5),
             ("Priest", "Shadow", "Dispersion", 1), ("Priest", "Shadow", "Improved Spirit Tap", 2),
             ("Priest", "Discipline", "Twin Disciplines", 5), ("Priest", "Discipline", "Improved Inner Fire", 3),
             ("Priest", "Discipline", "Improved Power Word: Fortitude", 2), ("Priest", "Discipline", "Silent Resolve", 1),
             ("Priest", "Discipline", "Meditation", 3), ("Priest", "Discipline", "Inner Focus", 1),
             ("Priest", "Discipline", "Improved Power Word: Shield", 3), ("Priest", "Discipline", "Mental Agility", 2),
         ]),
    dict(id=5, name="Stealthy Healer",
         description="Druidic infiltrator: slip through shadows, restore life from hiding.",
         abilities=[
             ("Druid", "Healing Touch"), ("Rogue", "Stealth"), ("Druid", "Wrath"), ("Druid", "Mark of the Wild"),
             ("Druid", "Rejuvenation"), ("Druid", "Moonfire"), ("Druid", "Thorns"), ("Druid", "Entangling Roots"),
             ("Druid", "Nature's Grasp"), ("Druid", "Regrowth"), ("Druid", "Travel Form"), ("Druid", "Remove Curse"),
             ("Druid", "Cat Form"), ("Druid", "Prowl"), ("Rogue", "Vanish"),
             ("Druid", "Abolish Poison"), ("Druid", "Tranquility"),
             ("Druid", "Innervate"), ("Druid", "Barkskin"), ("Druid", "Gift of the Wild"),
             ("Druid", "Lifebloom"), ("Rogue", "Cloak of Shadows"), ("Druid", "Cyclone"), ("Druid", "Nourish"),
             ("Druid", "Wild Growth"),
         ],
         talents=[
             ("Druid", "Restoration", "Improved Mark of the Wild", 2), ("Druid", "Restoration", "Nature's Focus", 3),
             ("Druid", "Restoration", "Naturalist", 5), ("Druid", "Restoration", "Subtlety", 3),
             ("Druid", "Restoration", "Intensity", 3), ("Druid", "Restoration", "Omen of Clarity", 1),
             ("Druid", "Restoration", "Tranquil Spirit", 5), ("Druid", "Restoration", "Improved Rejuvenation", 3),
             ("Druid", "Restoration", "Nature's Swiftness", 1), ("Druid", "Restoration", "Gift of Nature", 5),
             ("Druid", "Restoration", "Empowered Touch", 2), ("Druid", "Restoration", "Nature's Bounty", 5),
             ("Druid", "Restoration", "Living Spirit", 3), ("Druid", "Restoration", "Swiftmend", 1),
             ("Druid", "Restoration", "Empowered Rejuvenation", 5),
             ("Druid", "Restoration", "Tree of Life", 1), ("Druid", "Restoration", "Improved Tree of Life", 2),
             ("Druid", "Restoration", "Improved Barkskin", 1),
             ("Rogue", "Subtlety", "Relentless Strikes", 1), ("Rogue", "Subtlety", "Master of Deception", 3),
             ("Rogue", "Subtlety", "Opportunity", 2), ("Rogue", "Subtlety", "Camouflage", 3),
             ("Rogue", "Subtlety", "Dirty Tricks", 2), ("Rogue", "Subtlety", "Elusiveness", 2),
             ("Rogue", "Subtlety", "Serrated Blades", 3), ("Rogue", "Subtlety", "Initiative", 3),
             ("Rogue", "Subtlety", "Setup", 1),
         ]),
    dict(id=6, name="Storm Warrior",
         description="Shamanistic bruiser: lightning from afar, heroic strikes up close.",
         abilities=[
             ("Shaman", "Lightning Bolt"), ("Shaman", "Healing Wave"), ("Warrior", "Heroic Strike"), ("Shaman", "Rockbiter Weapon"),
             ("Shaman", "Earth Shock"), ("Warrior", "Charge"), ("Shaman", "Earthbind Totem"), ("Shaman", "Lightning Shield"),
             ("Shaman", "Flame Shock"), ("Shaman", "Purge"), ("Shaman", "Ghost Wolf"), ("Shaman", "Wind Shear"),
             ("Shaman", "Frost Shock"), ("Warrior", "Cleave"), ("Warrior", "Execute"),
             ("Shaman", "Mana Spring Totem"), ("Shaman", "Windfury Weapon"), ("Shaman", "Chain Lightning"),
             ("Warrior", "Whirlwind"), ("Shaman", "Chain Heal"),
             ("Shaman", "Earth Shield"), ("Warrior", "Recklessness"),
             ("Shaman", "Thunderstorm"), ("Shaman", "Wrath of Air Totem"), ("Shaman", "Lava Burst"), ("Warrior", "Heroic Throw"),
         ],
         talents=[
             ("Shaman", "Enhancement", "Ancestral Knowledge", 5), ("Shaman", "Enhancement", "Enhancing Totems", 3),
             ("Shaman", "Enhancement", "Thundering Strikes", 5),
             ("Shaman", "Enhancement", "Improved Shields", 3), ("Shaman", "Enhancement", "Elemental Weapons", 3),
             ("Shaman", "Enhancement", "Shamanistic Focus", 1),
             ("Shaman", "Enhancement", "Flurry", 5),
             ("Shaman", "Enhancement", "Improved Windfury Totem", 2), ("Shaman", "Enhancement", "Spirit Weapons", 1),
             ("Shaman", "Enhancement", "Mental Dexterity", 3),
             ("Shaman", "Enhancement", "Unleashed Rage", 3), ("Shaman", "Enhancement", "Weapon Mastery", 3),
             ("Shaman", "Enhancement", "Dual Wield", 1), ("Shaman", "Enhancement", "Dual Wield Specialization", 3),
             ("Shaman", "Enhancement", "Stormstrike", 1),
             ("Shaman", "Enhancement", "Lava Lash", 1), ("Shaman", "Enhancement", "Improved Stormstrike", 2),
             ("Shaman", "Enhancement", "Maelstrom Weapon", 5),
             ("Shaman", "Enhancement", "Feral Spirit", 1),
             ("Warrior", "Fury", "Cruelty", 5), ("Warrior", "Fury", "Armored to the Teeth", 3),
             ("Warrior", "Fury", "Unbridled Wrath", 5),
             ("Warrior", "Fury", "Improved Cleave", 3), ("Warrior", "Fury", "Commanding Presence", 4),
         ]),

    # ---- elemental archetypes: one per element, built around the variant
    # strikes and the talent tree that feeds that element's damage -----------
    dict(id=7, name="Hellfire Knight",
         description="Burning warrior: fiery strikes and warlock fire, fed by the Destruction tree.",
         abilities=[
             ("Warrior", "Fiery Heroic Strike"), ("Warrior", "Battle Shout"),
             ("Warlock", "Immolate"), ("Warrior", "Charge"), ("Warlock", "Life Tap"),
             ("Warrior", "Hamstring"), ("Warrior", "Bloodrage"), ("Warrior", "Fiery Overpower"),
             ("Warlock", "Searing Pain"), ("Warrior", "Fiery Cleave"),
             ("Warrior", "Execute"), ("Warrior", "Intercept"), ("Warlock", "Hellfire"),
             ("Warrior", "Berserker Rage"), ("Warrior", "Fiery Whirlwind"), ("Warrior", "Pummel"),
             ("Warrior", "Fiery Mortal Strike"), ("Warlock", "Soul Fire"), ("Warrior", "Recklessness"),
             ("Warlock", "Chaos Bolt"), ("Warlock", "Incinerate"), ("Warrior", "Enraged Regeneration"),
         ],
         talents=[
             ("Warlock", "Destruction", "Bane", 5),
             ("Warlock", "Destruction", "Cataclysm", 3), ("Warlock", "Destruction", "Aftermath", 2),
             ("Warlock", "Destruction", "Ruin", 5),
             ("Warlock", "Destruction", "Intensity", 2), ("Warlock", "Destruction", "Improved Searing Pain", 3),
             ("Warlock", "Destruction", "Improved Immolate", 3), ("Warlock", "Destruction", "Devastation", 1),
             ("Warlock", "Destruction", "Backlash", 3),
             ("Warlock", "Destruction", "Emberstorm", 5),
             ("Warlock", "Destruction", "Conflagrate", 1), ("Warlock", "Destruction", "Pyroclasm", 3),
             ("Warlock", "Destruction", "Soul Leech", 3),
             ("Warlock", "Destruction", "Shadow and Flame", 5),
             ("Warlock", "Destruction", "Backdraft", 3),
             ("Warlock", "Destruction", "Fire and Brimstone", 5),
             ("Warlock", "Destruction", "Molten Skin", 1),
             ("Warrior", "Fury", "Cruelty", 5), ("Warrior", "Fury", "Armored to the Teeth", 3),
             ("Warrior", "Fury", "Unbridled Wrath", 5),
             ("Warrior", "Fury", "Improved Cleave", 3),
             ("Warrior", "Fury", "Improved Execute", 2),
         ]),
    dict(id=8, name="Rime Reaver",
         description="Frozen rogue: chilling strikes and frost magic that slow and shatter.",
         abilities=[
             ("Rogue", "Frozen Sinister Strike"), ("Rogue", "Eviscerate"),
             ("Rogue", "Frozen Backstab"), ("Mage", "Frostbolt"), ("Rogue", "Gouge"), ("Rogue", "Evasion"),
             ("Mage", "Frost Nova"), ("Rogue", "Slice and Dice"), ("Rogue", "Kick"),
             ("Rogue", "Frozen Ambush"), ("Rogue", "Rupture"), ("Rogue", "Vanish"),
             ("Mage", "Cone of Cold"), ("Rogue", "Cheap Shot"), ("Rogue", "Kidney Shot"), ("Mage", "Ice Block"),
             ("Rogue", "Blind"), ("Mage", "Ice Barrier"), ("Rogue", "Mutilate"),
             ("Mage", "Ice Lance"), ("Rogue", "Cloak of Shadows"), ("Rogue", "Shiv"),
             ("Rogue", "Frozen Fan of Knives"),
         ],
         talents=[
             ("Mage", "Frost", "Improved Frostbolt", 5),
             ("Mage", "Frost", "Ice Shards", 3), ("Mage", "Frost", "Precision", 3),
             ("Mage", "Frost", "Piercing Ice", 3), ("Mage", "Frost", "Icy Veins", 1),
             ("Mage", "Frost", "Shatter", 3), ("Mage", "Frost", "Arctic Reach", 2), ("Mage", "Frost", "Frost Channeling", 3),
             ("Mage", "Frost", "Cold Snap", 1), ("Mage", "Frost", "Frozen Core", 3),
             ("Mage", "Frost", "Winter's Chill", 3), ("Mage", "Frost", "Cold as Ice", 2),
             ("Mage", "Frost", "Frostbite", 1), ("Mage", "Frost", "Arctic Winds", 5),
             ("Mage", "Frost", "Fingers of Frost", 2), ("Mage", "Frost", "Empowered Frostbolt", 2),
             ("Mage", "Frost", "Brain Freeze", 3),
             ("Mage", "Frost", "Chilled to the Bone", 5),
             ("Mage", "Frost", "Deep Freeze", 1),
             ("Rogue", "Assassination", "Malice", 5), ("Rogue", "Assassination", "Improved Eviscerate", 3),
             ("Rogue", "Assassination", "Ruthlessness", 3), ("Rogue", "Assassination", "Puncturing Wounds", 3),
             ("Rogue", "Assassination", "Lethality", 5), ("Rogue", "Assassination", "Vigor", 1),
         ]),
    dict(id=9, name="Stoneguard",
         description="Earthen bear: slowing mauls and shaman totems, built to hold the line.",
         abilities=[
             ("Shaman", "Healing Wave"), ("Druid", "Mark of the Wild"), ("Shaman", "Rockbiter Weapon"),
             ("Shaman", "Earth Shock"), ("Shaman", "Earthbind Totem"), ("Shaman", "Lightning Shield"),
             ("Druid", "Bear Form"), ("Druid", "Earthen Maul"), ("Shaman", "Strength of Earth Totem"),
             ("Druid", "Enrage"), ("Druid", "Bash"), ("Druid", "Swipe (Bear)"), ("Druid", "Faerie Fire (Feral)"),
             ("Shaman", "Healing Stream Totem"), ("Druid", "Challenging Roar"),
             ("Shaman", "Grounding Totem"), ("Shaman", "Windfury Weapon"), ("Druid", "Frenzied Regeneration"),
             ("Druid", "Barkskin"), ("Shaman", "Earth Shield"), ("Druid", "Earthen Mangle (Bear)"),
             ("Shaman", "Earth Elemental Totem"), ("Druid", "Lacerate"),
         ],
         talents=[
             ("Druid", "Feral Combat", "Ferocity", 5),
             ("Druid", "Feral Combat", "Feral Instinct", 3), ("Druid", "Feral Combat", "Thick Hide", 3),
             ("Druid", "Feral Combat", "Survival Instincts", 1), ("Druid", "Feral Combat", "Sharpened Claws", 3),
             ("Druid", "Feral Combat", "Feral Swiftness", 2),
             ("Druid", "Feral Combat", "Predatory Strikes", 3), ("Druid", "Feral Combat", "Primal Fury", 2),
             ("Druid", "Feral Combat", "Feral Charge", 1), ("Druid", "Feral Combat", "Brutal Impact", 2),
             ("Druid", "Feral Combat", "Natural Reaction", 3), ("Druid", "Feral Combat", "Survival of the Fittest", 3),
             ("Druid", "Feral Combat", "Heart of the Wild", 5),
             ("Druid", "Feral Combat", "Leader of the Pack", 1), ("Druid", "Feral Combat", "Improved Leader of the Pack", 2),
             ("Druid", "Feral Combat", "Protector of the Pack", 3), ("Druid", "Feral Combat", "Infected Wounds", 3),
             ("Druid", "Feral Combat", "Primal Tenacity", 1),
             ("Druid", "Feral Combat", "Rend and Tear", 5),
             ("Druid", "Feral Combat", "Berserk", 1),
             ("Shaman", "Enhancement", "Ancestral Knowledge", 5), ("Shaman", "Enhancement", "Enhancing Totems", 3),
             ("Shaman", "Enhancement", "Improved Shields", 3), ("Shaman", "Enhancement", "Thundering Strikes", 5),
             ("Shaman", "Enhancement", "Anticipation", 3),
         ]),
    dict(id=10, name="Venomstalker",
         description="Venomous hunter: poisoned shots and stings, with a rogue's opening moves.",
         abilities=[
             ("Hunter", "Venomous Raptor Strike"), ("Rogue", "Stealth"), ("Hunter", "Serpent Sting"),
             ("Hunter", "Arcane Shot"), ("Hunter", "Hunter's Mark"), ("Hunter", "Concussive Shot"),
             ("Hunter", "Aspect of the Hawk"), ("Rogue", "Sprint"), ("Hunter", "Wing Clip"),
             ("Hunter", "Mongoose Bite"), ("Hunter", "Venomous Multi-Shot"), ("Hunter", "Venomous Aimed Shot"),
             ("Hunter", "Freezing Trap"), ("Hunter", "Rapid Fire"), ("Hunter", "Feign Death"),
             ("Hunter", "Counterattack"), ("Hunter", "Viper Sting"),
             ("Hunter", "Wyvern Sting"), ("Hunter", "Volley"), ("Hunter", "Black Arrow"), ("Hunter", "Steady Shot"),
             ("Hunter", "Snake Trap"), ("Hunter", "Venomous Kill Shot"), ("Rogue", "Tricks of the Trade"),
         ],
         talents=[
             ("Hunter", "Survival", "Savage Strikes", 2), ("Hunter", "Survival", "Hawk Eye", 3),
             ("Hunter", "Survival", "Surefooted", 3), ("Hunter", "Survival", "Survival Instincts", 2),
             ("Hunter", "Survival", "Survivalist", 5),
             ("Hunter", "Survival", "T.N.T.", 3), ("Hunter", "Survival", "Lock and Load", 3),
             ("Hunter", "Survival", "Killer Instinct", 3), ("Hunter", "Survival", "Hunter vs. Wild", 3),
             ("Hunter", "Survival", "Lightning Reflexes", 5),
             ("Hunter", "Survival", "Thrill of the Hunt", 3), ("Hunter", "Survival", "Expose Weakness", 3),
             ("Hunter", "Survival", "Noxious Stings", 3), ("Hunter", "Survival", "Master Tactician", 5),
             ("Hunter", "Survival", "Sniper Training", 3), ("Hunter", "Survival", "Entrapment", 2),
             ("Hunter", "Survival", "Hunting Party", 3),
             ("Hunter", "Survival", "Explosive Shot", 1),
             ("Rogue", "Assassination", "Malice", 5), ("Rogue", "Assassination", "Remorseless Attacks", 2),
             ("Rogue", "Assassination", "Ruthlessness", 3), ("Rogue", "Assassination", "Puncturing Wounds", 3),
             ("Rogue", "Assassination", "Lethality", 3),
         ]),
    dict(id=11, name="Nightclaw",
         description="Shadow cat: darkened claws and shreds, sharpened by the Shadow tree.",
         abilities=[
             ("Druid", "Wrath"), ("Druid", "Mark of the Wild"), ("Druid", "Healing Touch"),
             ("Priest", "Shadow Word: Pain"), ("Druid", "Moonfire"), ("Druid", "Rejuvenation"), ("Priest", "Fade"),
             ("Priest", "Mind Blast"), ("Druid", "Regrowth"),
             ("Druid", "Cat Form"), ("Druid", "Shadow Claw"), ("Druid", "Prowl"), ("Druid", "Rip"),
             ("Druid", "Shadow Shred"), ("Druid", "Tiger's Fury"), ("Druid", "Rake"),
             ("Druid", "Ferocious Bite"), ("Druid", "Shadow Ravage"), ("Druid", "Pounce"),
             ("Druid", "Feline Grace"), ("Druid", "Barkskin"), ("Druid", "Shadow Mangle (Cat)"),
             ("Druid", "Shadow Maim"), ("Druid", "Shadow Swipe (Cat)"), ("Druid", "Savage Roar"),
         ],
         talents=[
             ("Priest", "Shadow", "Spirit Tap", 3), ("Priest", "Shadow", "Darkness", 5),
             ("Priest", "Shadow", "Improved Spirit Tap", 2),
             ("Priest", "Shadow", "Improved Shadow Word: Pain", 2), ("Priest", "Shadow", "Shadow Focus", 3),
             ("Priest", "Shadow", "Improved Mind Blast", 5),
             ("Priest", "Shadow", "Shadow Weaving", 3), ("Priest", "Shadow", "Veiled Shadows", 2),
             ("Priest", "Shadow", "Vampiric Embrace", 1), ("Priest", "Shadow", "Focused Mind", 3),
             ("Priest", "Shadow", "Mind Melt", 2), ("Priest", "Shadow", "Improved Vampiric Embrace", 2),
             ("Priest", "Shadow", "Shadow Power", 5),
             ("Priest", "Shadow", "Misery", 3),
             ("Priest", "Shadow", "Pain and Suffering", 3), ("Priest", "Shadow", "Psychic Horror", 1),
             ("Priest", "Shadow", "Twisted Faith", 5),
             ("Druid", "Feral Combat", "Ferocity", 5),
             ("Druid", "Feral Combat", "Savage Fury", 2), ("Druid", "Feral Combat", "Feral Instinct", 3),
             ("Druid", "Feral Combat", "Sharpened Claws", 3), ("Druid", "Feral Combat", "Feral Swiftness", 2),
             ("Druid", "Feral Combat", "Predatory Strikes", 3), ("Druid", "Feral Combat", "Primal Fury", 2),
             ("Druid", "Feral Combat", "Shredding Attacks", 1),
         ]),
    dict(id=12, name="Dawnward",
         description="Holy bulwark: shield and strikes that heal you, backed by both Protection trees.",
         abilities=[
             ("Warrior", "Holy Heroic Strike"), ("Paladin", "Holy Light"),
             ("Paladin", "Seal of Righteousness"), ("Paladin", "Judgement of Light"), ("Paladin", "Blessing of Might"),
             ("Paladin", "Divine Protection"), ("Paladin", "Hammer of Justice"), ("Warrior", "Bloodrage"),
             ("Warrior", "Shield Bash"), ("Paladin", "Righteous Defense"), ("Paladin", "Righteous Fury"),
             ("Warrior", "Shield Block"), ("Paladin", "Consecration"), ("Warrior", "Holy Cleave"),
             ("Warrior", "Shield Wall"), ("Paladin", "Divine Shield"), ("Warrior", "Shield Slam"),
             ("Paladin", "Holy Shield"), ("Paladin", "Cleanse"),
             ("Warrior", "Holy Devastate"), ("Paladin", "Avenger's Shield"),
             ("Paladin", "Greater Blessing of Kings"), ("Paladin", "Divine Plea"), ("Paladin", "Shield of Righteousness"),
         ],
         talents=[
             ("Paladin", "Protection", "Divine Strength", 5),
             ("Paladin", "Protection", "Anticipation", 5),
             ("Paladin", "Protection", "Toughness", 5), ("Paladin", "Protection", "Improved Righteous Fury", 3),
             ("Paladin", "Protection", "Improved Hammer of Justice", 2),
             ("Paladin", "Protection", "Blessing of Sanctuary", 1), ("Paladin", "Protection", "Reckoning", 5),
             ("Paladin", "Protection", "Sacred Duty", 2), ("Paladin", "Protection", "One-Handed Weapon Specialization", 3),
             ("Paladin", "Protection", "Ardent Defender", 3), ("Paladin", "Protection", "Spiritual Attunement", 2),
             ("Paladin", "Protection", "Redoubt", 3), ("Paladin", "Protection", "Combat Expertise", 3),
             ("Paladin", "Protection", "Touched by the Light", 3), ("Paladin", "Protection", "Guarded by the Light", 2),
             ("Paladin", "Protection", "Stoicism", 2),
             ("Paladin", "Protection", "Shield of the Templar", 3),
             ("Paladin", "Protection", "Hammer of the Righteous", 1),
             ("Warrior", "Protection", "Shield Specialization", 5), ("Warrior", "Protection", "Improved Bloodrage", 2),
             ("Warrior", "Protection", "Incite", 3), ("Warrior", "Protection", "Anticipation", 5),
             ("Warrior", "Protection", "Shield Mastery", 2), ("Warrior", "Protection", "Last Stand", 1),
         ]),
    dict(id=13, name="Spellblade",
         description="Arcane duelist: arcane-laced strikes, with Intellect turned into damage.",
         abilities=[
             ("Rogue", "Arcane Sinister Strike"), ("Mage", "Arcane Intellect"), ("Rogue", "Eviscerate"),
             ("Rogue", "Arcane Backstab"), ("Rogue", "Gouge"), ("Mage", "Arcane Missiles"), ("Rogue", "Evasion"),
             ("Rogue", "Slice and Dice"), ("Rogue", "Kick"), ("Mage", "Arcane Explosion"),
             ("Rogue", "Arcane Ambush"), ("Mage", "Blink"), ("Rogue", "Rupture"), ("Rogue", "Vanish"),
             ("Mage", "Counterspell"), ("Rogue", "Cheap Shot"), ("Rogue", "Kidney Shot"),
             ("Rogue", "Mutilate"), ("Mage", "Arcane Barrage"), ("Mage", "Arcane Blast"),
             ("Rogue", "Cloak of Shadows"), ("Rogue", "Shiv"), ("Rogue", "Arcane Fan of Knives"),
         ],
         talents=[
             ("Mage", "Arcane", "Arcane Focus", 3), ("Mage", "Arcane", "Arcane Subtlety", 2),
             ("Mage", "Arcane", "Arcane Concentration", 5),
             ("Mage", "Arcane", "Spell Impact", 3), ("Mage", "Arcane", "Student of the Mind", 2),
             ("Mage", "Arcane", "Torment the Weak", 3), ("Mage", "Arcane", "Arcane Meditation", 2),
             ("Mage", "Arcane", "Presence of Mind", 1), ("Mage", "Arcane", "Arcane Mind", 5),
             ("Mage", "Arcane", "Arcane Instability", 3), ("Mage", "Arcane", "Arcane Potency", 2),
             ("Mage", "Arcane", "Arcane Power", 1), ("Mage", "Arcane", "Arcane Empowerment", 3),
             ("Mage", "Arcane", "Mind Mastery", 5),
             ("Rogue", "Combat", "Improved Sinister Strike", 2), ("Rogue", "Combat", "Dual Wield Specialization", 5),
             ("Rogue", "Combat", "Precision", 5), ("Rogue", "Combat", "Improved Slice and Dice", 2),
             ("Rogue", "Combat", "Endurance", 1),
             ("Rogue", "Combat", "Lightning Reflexes", 3), ("Rogue", "Combat", "Aggression", 5),
             ("Rogue", "Combat", "Blade Flurry", 1), ("Rogue", "Combat", "Hack and Slash", 5),
             ("Rogue", "Combat", "Weapon Expertise", 2),
         ]),
]


# =============================================================================
# conf
# =============================================================================

def read_conf(path):
    """The handful of Classless settings the schedule depends on, with the
    shipped defaults if the file lacks a key."""
    cfg = dict(starting_ae=3, essence_start=4, te_start=10, ae_per_level=1, te_per_level=1,
               costs=[1, 2, 3, 5, 8], talent_cost=1, talent_flat=0, enforce_rows=1,
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
        self.learn_levels = self._trainer_levels(os.path.join(base, "trainer_spell.sql"))
        self.first_of, self.chain_of = self._ranks(os.path.join(base, "spell_ranks.sql"))
        self._talents()
        self._abilities()
        self._variants(manifest)
        self._replaced_talents()

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
            first = self.first_of.get(sp, sp)
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
    return abilities, talents, problems


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
    print("pool: %d ability lines (%d elemental variants), %d talents" % (
        sum(1 for e in pool.abilities.values() if e["enabled"]), pool.variants, len(pool.talents)))
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
