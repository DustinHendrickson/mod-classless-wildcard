/*
 * mod-classless-wildcard
 *
 * Ascension-style classless system + Season 10 "Wildcard" mode for AzerothCore.
 * Copyright (C) 2026 Dustin Hendrickson
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
 * General Public License for more details.
 */

#ifndef MOD_CLASSLESS_WILDCARD_H
#define MOD_CLASSLESS_WILDCARD_H

#include "Define.h"
#include "ObjectGuid.h"
#include <array>
#include <map>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

class Player;

namespace ClasslessWildcard
{
    // implemented in ClasslessAddon.cpp: raw push to the client addon
    // (used e.g. for "RV|..." roll-reveal notifications)
    void PushAddon(Player* player, std::string const& body);

    enum class Mode : uint8
    {
        Classless = 0,  // free-pick with essences
        Wildcard  = 1,  // random rolls
        Unchosen  = 255
    };

    enum class Rarity : uint8
    {
        Common    = 0,
        Uncommon  = 1,
        Rare      = 2,
        Epic      = 3,
        Legendary = 4,
        Max       = 5
    };

    enum class GrantSource : uint8
    {
        Picked = 0,   // bought with essence (classless mode)
        Rolled = 1    // wildcard random roll
    };

    // One entry of the ability library: a spell line (first rank) + all its ranks.
    struct AbilityEntry
    {
        uint32 firstSpellId = 0;
        std::string name;               // rank-1 spell name (dedupe + owned-name checks)
        std::vector<uint32> ranks;      // rank spell ids in order, [0] == firstSpellId
        std::vector<uint8>  rankLevels; // required level per rank
        uint32 classMask = 0;           // origin class(es)
        Rarity rarity = Rarity::Common;
        uint32 cost = 1;                // ability essence cost (classless mode)
        uint32 weight = 100;            // wildcard roll weight
        bool   enabled = true;
        bool   passive = false;
    };

    // One entry of the talent pool.
    struct TalentPoolEntry
    {
        uint32 talentId = 0;
        uint32 tabId = 0;
        uint32 classMask = 0;           // from TalentTab
        uint32 row = 0;
        uint32 col = 0;
        uint32 dependsOn = 0;           // prerequisite talent id (0 = none)
        uint32 dependsOnRank = 0;
        std::array<uint32, 5> rankSpells = { 0, 0, 0, 0, 0 };
        uint8  maxRank = 0;
        Rarity rarity = Rarity::Common;
        uint32 weight = 100;
        bool   enabled = true;
    };

    struct OwnedAbility
    {
        GrantSource source = GrantSource::Picked;
        bool locked = false;
    };

    struct RollBan
    {
        uint32 entry = 0;
        bool   isTalent = false;
        int32  rollsLeft = 0;
    };

    // Pre-built starter builds for onboarding (Ascension's "archetypes").
    struct Archetype
    {
        uint32 id = 0;
        std::string name;
        std::string description;
        std::vector<uint32> abilities;                    // first-rank spell ids
        std::vector<std::pair<uint32, uint8>> talents;    // talentId -> rank
    };

    // Per-character runtime state (mirrored to characters DB).
    struct CharState
    {
        Mode   mode = Mode::Unchosen;
        uint32 abilityEssence = 0;
        uint32 talentEssence = 0;
        uint32 pity = 0;                 // rerolls since last synergy roll
        // One pool of earned reroll charges, spent on abilities OR talents --
        // two separate pools just made the UI read as three confusing numbers.
        uint32 rerolls = 0;
        uint8  lastProcessedLevel = 0;

        // which resource bar the default unit frame displays
        // (0 mana, 1 rage, 3 energy, 255 = chassis default)
        uint8  displayPower = 255;

        // primary stat allocation (points per stat: STR, AGI, STA, INT, SPI)
        std::array<uint32, 5> statAlloc = { 0, 0, 0, 0, 0 };
        std::array<int32, 5>  appliedStatBonus = { 0, 0, 0, 0, 0 }; // currently applied, runtime only

        // universal stat layer bonuses currently applied (runtime only)
        int32 usMeleeAP = 0;
        int32 usRangedAP = 0;
        int32 usSpellPower = 0;

        // last combo-point count mirrored to the addon (runtime only; 255 =
        // nothing pushed yet, so the first update always syncs)
        uint8 lastComboPush = 255;

        std::unordered_map<uint32 /*firstSpellId*/, OwnedAbility> abilities;
        std::unordered_map<uint32 /*talentId*/, uint8 /*rank*/>   talents;
        std::vector<RollBan>   bans;
        bool exempt = false;   // bot/system account: classless rules don't apply
        bool loaded = false;
    };

    struct Config
    {
        bool   enabled = true;
        bool   announce = true;
        uint8  defaultMode = 0;
        bool   allowModeChoice = true;
        uint8  modeChoiceDeadline = 5;

        // library filters
        bool   includeDeathKnight = false;
        bool   includeRacials = false;
        bool   includePassives = true;
        std::unordered_set<uint32> excludedSpells;

        // tiered acquisition: rolls/purchases respect each spell's own level
        // requirement (rank 1 learn level) and each talent's tree-row level,
        // so low levels can't be dealt end-game spells
        bool   respectLevelReqs = true;

        // only spells players actually learn (starter spells + class trainer
        // lists) enter the library; also sources each rank's REAL learn level
        // from trainer data. Kills NPC/pet variants like "Demonic Immolate".
        bool   trainerTaughtOnly = true;

        // proficiencies
        bool   teachProficiencies = true;
        std::vector<uint32> proficiencySpells;

        // clean-slate start: strip the chassis class's default spells at
        // creation and hand out the neutral Hero kit instead
        bool   stripStartingSpells = true;
        bool   starterKitEnable = true;
        // strip EVERY piece of default gear the shell class was created with,
        // so the Hero starts bare and the kit armour actually equips (the old
        // "replace weapons only" left the shell's shirt/pants/boots on, so the
        // kit armour fell through to the bags)
        bool   starterKitStripEquipped = true;
        uint32 starterKitBag = 5573;   // an 8-slot bag equipped at creation (0 = none)
        std::vector<std::pair<uint32, uint32>> starterKitItems;  // into bags
        std::vector<std::pair<uint32, uint32>> starterKitEquip;  // auto-equipped (armour)

        // accounts whose name starts with one of these prefixes play VANILLA
        // rules (no essences/rolls, native talents, trainers work) — for
        // playerbots' random-bot accounts and similar system accounts
        std::vector<std::string> exemptAccountPrefixes;

        // native talent suppression
        bool   suppressTalentPoints = true;

        // revert class-library spells learned outside the module (class
        // trainers, quest rewards) so essence/rolls stay the only path
        bool   blockOutsideSpellSources = true;

        // A shapeshift form or a warrior stance is useless on its own: a Hero
        // who draws Bear Form and nothing else cannot attack in it. Gaining one
        // hands over the basic kit that goes with it (Maul, Demoralizing Roar),
        // free, so it is usable the moment it lands. The pairs live in the
        // `cw_form_kits` table.
        // Answer the core's "is this player a <class>?" questions as YES for the
        // contexts where classless means every class at once: equipping any
        // relic, shields, and the reactive-ability aura states. Off = the
        // chassis class decides, which is the stock behaviour.
        bool   classlessClassChecks = true;

        bool   formKitsEnable = true;

        // Classless gear as world drops. The catalogue was vendor-only, which
        // made the Hero Advancement NPC the only answer to "where does gear
        // come from". Any mob can now drop a piece banded to ITS level, so a
        // level 20 zone yields level 20 gear whoever kills there. Heirlooms are
        // the premium reward and come only off rares and bosses.
        bool   worldDropEnable = true;
        float  worldDropChance = 1.0f;           // percent, per qualifying kill
        float  worldDropRareMultiplier = 5.0f;   // rares/elites/bosses drop more often
        float  worldDropHeirloomChance = 2.0f;   // percent, rares and bosses only

        // classless (free-pick) economy
        uint32 startingAbilityEssence = 9;
        uint8  essenceStartLevel = 10;
        uint32 abilityEssencePerLevel = 1;
        uint32 talentEssencePerLevel = 1;
        std::array<uint32, 5> abilityCostByRarity = { 1, 2, 3, 5, 8 };
        uint32 talentCostPerRank = 1;
        // Optional: charge only the FIRST rank, making a talent cost one point
        // however far it is ranked. Off by default -- in Classless you choose
        // what you buy, so each rank is paid for. (The "rank 5 for one point"
        // rule belongs to Wildcard, where the roll hands you the rank free.)
        bool   talentFlatCost = false;
        bool   enforceTalentRows = true;
        bool   refundOnUnlearn = true;
        uint32 respecCostGold = 50;

        // wildcard
        uint32 wcStartingAbilities = 4;
        uint8  wcRollStartLevel = 10;
        uint32 wcTalentEveryLevels = 1;
        uint32 wcAbilityEveryLevels = 2;
        uint8  wcFreeRerollLevel = 10;   // below this, rerolls are free
        std::array<uint32, 5> wcRarityWeights = { 100, 60, 30, 10, 3 };
        uint32 wcSynergyBaseChance = 10;   // percent
        uint32 wcSynergyIncrement = 10;    // percent per pity point
        uint32 wcSynergyBanRolls = 25;
        uint32 wcScrollItemId = 990101;        // Reroll Scroll (top-up item)
        uint32 wcRerollsPerAbilityRoll = 1;    // earned reroll charges per scheduled ability roll
        uint32 wcRerollsPerTalentRoll = 1;     // earned reroll charges per scheduled talent roll
        uint32 wcFreeScrollEveryLevels = 0;    // optional extra: scrolls every N levels (0 = off)
        uint32 wcFreeScrollCount = 1;          // scrolls granted per milestone
        uint32 wcScrollBuyEnable = 1;          // allow buying scrolls from the addon panel
        uint32 wcScrollBuyBaseCopper = 500;    // base price of a Scroll of Fortune, in copper
        uint32 wcScrollBuyPerLevelCopper = 500;// added copper per character level (silver early, gold at cap)

        // SINGLE CHASSIS
        //
        // Every Hero is forced onto one class, whatever the creation screen
        // sent. This is the whole point: as long as characters keep different
        // classes, the core's own per-class math differs between them — base
        // stats, base health and mana, which stat converts into attack power —
        // and "roll a mana class if you want to cast" creeps back in. One
        // chassis makes that math identical by construction rather than by
        // correction, so the class you picked is purely cosmetic.
        //
        // Paladin is the default: it has a real mana pool with proper base
        // mana (so %-of-base-mana spell costs work) and spirit regen, and no
        // forms, stances or runes to suppress. Rage and energy are layered on
        // top by the universal-resource code below.
        bool   chassisEnable = true;
        uint8  chassisClass = 2;          // CLASS_PALADIN

        // universal resources: every Hero maintains mana, rage AND energy
        // pools simultaneously (druid-style — the client tracks all pools,
        // only the chassis bar is displayed; the addon shows the others)
        bool   universalResources = true;
        // synthetic mana, used only when the configured chassis has no native
        // mana pool. With the default Paladin chassis this never runs. Uses
        // the real WoW conversion:
        // the first 20 Intellect give 1 mana each, points beyond 20 give
        // ManaPerIntellect each; plus a flat base and per-level growth
        uint32 urBaseMana = 100;
        uint32 urManaPerLevel = 35;
        uint32 urManaPerIntellect = 15;    // per point of Intellect ABOVE 20
        uint32 urMaxRage = 1000;           // internal units (1000 = 100 rage)
        uint32 urMaxEnergy = 100;
        uint32 urRageDealtPct = 100;       // % of warrior-formula rage gained when dealing melee damage
        uint32 urRageTakenPct = 100;       // % of warrior-formula rage gained when taking damage
        // synthetic mana regen (per 5s): Base + Spirit*PerSpirit + Pct% of max
        float  urManaRegenBase = 4.0f;
        float  urManaRegenPerSpirit = 0.3f;
        uint32 urManaRegenPct = 0;

        // universal stat layer: fills the gaps the chassis math leaves so
        // EVERY stat is worth allocating on a classless Hero:
        //   AGI -> melee + ranged attack power, INT -> spell power,
        //   SPI -> mana regen (above). STR/STA already work via the core.
        // Because every Hero shares one chassis, these apply identically to
        // everyone -- there is no class whose native conversions make it a
        // better caster or a better melee.
        bool   universalStats = true;
        float  usMeleeAPPerAgi = 1.0f;
        float  usRangedAPPerAgi = 1.0f;
        float  usSpellPowerPerInt = 1.0f;  // per Intellect point above 10

        // primary stat allocation
        bool   statsEnable = true;
        uint32 statStartingPoints = 4;
        uint32 statPointsPerLevel = 2;
        uint32 statValuePerPoint = 1;      // stat granted per point

        // rebirth (late mode switch / full reset)
        bool   rebirthEnable = true;
        uint32 rebirthCostGold = 100;

        uint32 npcEntry = 990100;
    };

    char const* RarityName(Rarity r);
    char const* RarityColor(Rarity r); // client color escape
} // namespace ClasslessWildcard

#endif // MOD_CLASSLESS_WILDCARD_H
