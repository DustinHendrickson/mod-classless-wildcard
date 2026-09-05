/*
 * mod-classless-wildcard
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

#include "ClasslessMgr.h"
#include "Chat.h"
#include "Config.h"
#include "DBCStores.h"
#include "DatabaseEnv.h"
#include "Log.h"
#include "ObjectMgr.h"
#include "Pet.h"
#include "Player.h"
#include "Random.h"
#include "SharedDefines.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "StringConvert.h"
#include "StringFormat.h"
#include "Tokenize.h"
#include "WorldSession.h"
#include <algorithm>

using namespace ClasslessWildcard;

namespace
{
    constexpr char MSG_PREFIX[] = "|cff00ccff[Classless]|r ";

    std::string SpellName(uint32 spellId)
    {
        if (SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId))
            if (info->SpellName[0])
                return info->SpellName[0];
        return "Unknown";
    }

    void Msg(Player* player, std::string const& text)
    {
        ChatHandler(player->GetSession()).SendSysMessage(std::string(MSG_PREFIX) + text);
    }

    std::vector<uint32> ParseUintList(std::string const& value)
    {
        std::vector<uint32> out;
        for (auto const& tok : Acore::Tokenize(value, ',', false))
            if (Optional<uint32> v = Acore::StringTo<uint32>(tok))
                out.push_back(*v);
        return out;
    }

    Rarity RarityFromTalentRow(uint32 row)
    {
        if (row <= 1) return Rarity::Common;
        if (row <= 3) return Rarity::Uncommon;
        if (row <= 5) return Rarity::Rare;
        if (row <= 7) return Rarity::Epic;
        return Rarity::Legendary;
    }

    AbilityType ClassifyAbility(SpellInfo const* info, bool passive)
    {
        if (passive)
            return AbilityType::Passive;
        if (!info)
            return AbilityType::Utility;
        for (uint8 i = 0; i < MAX_SPELL_EFFECTS; ++i)
        {
            SpellEffectInfo const& eff = info->Effects[i];
            if (eff.Effect == SPELL_EFFECT_HEAL || eff.Effect == SPELL_EFFECT_HEAL_PCT
                || eff.Effect == SPELL_EFFECT_HEAL_MAX_HEALTH
                || (eff.Effect == SPELL_EFFECT_APPLY_AURA
                    && (eff.ApplyAuraName == SPELL_AURA_PERIODIC_HEAL || eff.ApplyAuraName == SPELL_AURA_OBS_MOD_HEALTH)))
                return AbilityType::Heal;
        }
        switch (info->DmgClass)
        {
            case SPELL_DAMAGE_CLASS_MELEE:  return AbilityType::Melee;
            case SPELL_DAMAGE_CLASS_RANGED: return AbilityType::Ranged;
            case SPELL_DAMAGE_CLASS_MAGIC:  return AbilityType::Spell;
            default:                        return AbilityType::Utility;
        }
    }

}

char const* ClasslessWildcard::RarityName(Rarity r)
{
    switch (r)
    {
        case Rarity::Common:    return "Common";
        case Rarity::Uncommon:  return "Uncommon";
        case Rarity::Rare:      return "Rare";
        case Rarity::Epic:      return "Epic";
        case Rarity::Legendary: return "Legendary";
        default:                return "Unknown";
    }
}

char const* ClasslessWildcard::RarityColor(Rarity r)
{
    switch (r)
    {
        case Rarity::Common:    return "|cffffffff";
        case Rarity::Uncommon:  return "|cff1eff00";
        case Rarity::Rare:      return "|cff0070dd";
        case Rarity::Epic:      return "|cffa335ee";
        case Rarity::Legendary: return "|cffff8000";
        default:                return "|cffffffff";
    }
}

ClasslessMgr* ClasslessMgr::instance()
{
    static ClasslessMgr instance;
    return &instance;
}

// -------------------------------------------------------------------------
// Config
// -------------------------------------------------------------------------

void ClasslessMgr::LoadConfig(bool /*reload*/)
{
    cfg.enabled = sConfigMgr->GetOption<bool>("ClasslessWildcard.Enable", true);
    cfg.announce = sConfigMgr->GetOption<bool>("ClasslessWildcard.Announce", true);
    cfg.defaultMode = sConfigMgr->GetOption<uint8>("ClasslessWildcard.DefaultMode", 0);
    cfg.allowModeChoice = sConfigMgr->GetOption<bool>("ClasslessWildcard.AllowModeChoice", true);
    cfg.modeChoiceDeadline = sConfigMgr->GetOption<uint8>("ClasslessWildcard.ModeChoiceDeadline", 5);

    cfg.includeDeathKnight = sConfigMgr->GetOption<bool>("ClasslessWildcard.IncludeDeathKnight", true);
    cfg.replaceAbilityTalents = sConfigMgr->GetOption<bool>("ClasslessWildcard.ReplaceAbilityTalents", true);
    cfg.includeRacials = sConfigMgr->GetOption<bool>("ClasslessWildcard.IncludeRacials", false);
    cfg.includePassives = sConfigMgr->GetOption<bool>("ClasslessWildcard.IncludePassives", true);
    cfg.respectLevelReqs = sConfigMgr->GetOption<bool>("ClasslessWildcard.RespectLevelRequirements", true);
    cfg.trainerTaughtOnly = sConfigMgr->GetOption<bool>("ClasslessWildcard.TrainerTaughtOnly", true);

    cfg.stripStartingSpells = sConfigMgr->GetOption<bool>("ClasslessWildcard.StripStartingSpells", true);
    cfg.starterKitEnable = sConfigMgr->GetOption<bool>("ClasslessWildcard.StarterKit.Enable", true);
    cfg.starterKitStripEquipped = sConfigMgr->GetOption<bool>("ClasslessWildcard.StarterKit.StripEquipped", true);
    cfg.starterKitBag = sConfigMgr->GetOption<uint32>("ClasslessWildcard.StarterKit.Bag", 5573);
    auto parseKit = [](std::string const& list, std::vector<std::pair<uint32, uint32>>& out)
    {
        out.clear();
        for (std::string_view piece : Acore::Tokenize(list, ',', false))
        {
            std::vector<std::string_view> kv = Acore::Tokenize(piece, ':', false);
            Optional<uint32> id = kv.size() >= 1 ? Acore::StringTo<uint32>(kv[0]) : std::nullopt;
            Optional<uint32> cnt = kv.size() >= 2 ? Acore::StringTo<uint32>(kv[1]) : Optional<uint32>(1);
            if (id && *id)
                out.emplace_back(*id, cnt.value_or(1));
        }
    };
    // bag items: 2x dagger, 1H mace, 2H sword/mace/axe, staff, bow+arrows,
    // gun+shot, thrown, and a stack each of food and water
    std::string kitList = sConfigMgr->GetOption<std::string>(
        "ClasslessWildcard.StarterKit.Items",
        "2092:2,36:1,1194:1,2361:1,12282:1,35:1,2504:1,2512:200,2508:1,2516:200,25861:200,4540:20,159:20");
    parseKit(kitList, cfg.starterKitItems);
    // auto-equipped: standard armor (shirt/pants/boots) + 1H sword + shield
    std::string equipList = sConfigMgr->GetOption<std::string>(
        "ClasslessWildcard.StarterKit.Equip",
        "38:1,39:1,40:1,25:1,2362:1");
    parseKit(equipList, cfg.starterKitEquip);

    cfg.excludedSpells.clear();
    for (uint32 id : ParseUintList(sConfigMgr->GetOption<std::string>("ClasslessWildcard.ExcludedSpells", "")))
        cfg.excludedSpells.insert(id);

    cfg.exemptAccountPrefixes.clear();
    {
        std::string prefixes = sConfigMgr->GetOption<std::string>("ClasslessWildcard.ExemptAccountPrefixes", "rndbot");
        for (auto const& tok : Acore::Tokenize(prefixes, ',', false))
            if (!tok.empty())
                cfg.exemptAccountPrefixes.emplace_back(tok);
    }

    // Riding: the four ranks plus Cold Weather Flying, each at the level its
    // trainer sells it. Cold Weather Flying is the odd one out -- it grants no
    // skill, it is the permission the server checks before letting anyone fly
    // in Northrend -- but it is bought from the same trainer, so it belongs in
    // the same list.
    cfg.callPetSpell = sConfigMgr->GetOption<uint32>("ClasslessWildcard.CallPetSpell", 883);
    cfg.ridingEnable = sConfigMgr->GetOption<bool>("ClasslessWildcard.Riding.Enable", true);
    parseKit(sConfigMgr->GetOption<std::string>("ClasslessWildcard.Riding.Grants",
        "33388:20,33391:40,34090:60,54197:68,34091:70"), cfg.ridingGrants);

    cfg.teachProficiencies = sConfigMgr->GetOption<bool>("ClasslessWildcard.TeachProficiencies", true);
    cfg.proficiencySpells = ParseUintList(sConfigMgr->GetOption<std::string>(
        "ClasslessWildcard.ProficiencySpells",
        // cloth, leather, mail, plate, shield, swords 1h/2h, axes 1h/2h, maces 1h/2h,
        // polearms, staves, daggers, fist, bows, guns, crossbows, thrown, wands,
        // Shoot wand (5019), Shoot bow/gun/crossbow (3018), Throw (2764), dual wield
        "9078,9077,8737,750,9116,201,202,196,197,198,199,200,227,1180,15590,264,266,5011,2567,5009,5019,3018,2764,674"));

    cfg.suppressTalentPoints = sConfigMgr->GetOption<bool>("ClasslessWildcard.SuppressTalentPoints", true);
    cfg.blockOutsideSpellSources = sConfigMgr->GetOption<bool>("ClasslessWildcard.BlockOutsideSpellSources", true);
    cfg.classlessClassChecks = sConfigMgr->GetOption<bool>("ClasslessWildcard.ClasslessClassChecks", true);
    cfg.spellbookTabs = uint8(sConfigMgr->GetOption<uint32>("ClasslessWildcard.SpellbookTabs", 1));
    cfg.formKitsEnable = sConfigMgr->GetOption<bool>("ClasslessWildcard.FormStarterKits", true);
    cfg.ignoreSpellTools = sConfigMgr->GetOption<bool>("ClasslessWildcard.IgnoreSpellTools", true);
    cfg.elementalEnable = sConfigMgr->GetOption<bool>("ClasslessWildcard.Elemental.Enable", true);
    cfg.elementalRarityBump = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Elemental.RarityBump", 1);
    cfg.elementalRollWeightPct = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Elemental.RollWeightPct", 8);
    cfg.elementalInPool = sConfigMgr->GetOption<bool>("ClasslessWildcard.Elemental.InPool", true);
    cfg.elementalShowInBrowser = sConfigMgr->GetOption<bool>("ClasslessWildcard.Elemental.ShowInBrowser", true);
    cfg.worldDropEnable = sConfigMgr->GetOption<bool>("ClasslessWildcard.WorldDrops.Enable", true);
    cfg.worldDropChance = sConfigMgr->GetOption<float>("ClasslessWildcard.WorldDrops.Chance", 1.0f);
    cfg.worldDropRareMultiplier = sConfigMgr->GetOption<float>("ClasslessWildcard.WorldDrops.RareMultiplier", 5.0f);
    cfg.worldDropHeirloomChance = sConfigMgr->GetOption<float>("ClasslessWildcard.WorldDrops.HeirloomChance", 2.0f);

    cfg.startingAbilityEssence = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Classless.StartingAbilityEssence", 3);
    cfg.essenceStartLevel = sConfigMgr->GetOption<uint8>("ClasslessWildcard.Classless.EssenceStartLevel", 4);
    cfg.talentEssenceStartLevel = sConfigMgr->GetOption<uint8>("ClasslessWildcard.Classless.TalentEssenceStartLevel", 10);
    cfg.abilityEssencePerLevel = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Classless.AbilityEssencePerLevel", 1);
    cfg.talentEssencePerLevel = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Classless.TalentEssencePerLevel", 1);
    // Printed at every load so a stale classless_wildcard.conf shows up in the
    // worldserver log instead of as a Hero with the wrong amount of essence.
    LOG_INFO("module.classless", "mod-classless-wildcard: Classless economy: {} AE at creation, +{} AE per level from {}, "
             "+{} TE per level from {}",
             cfg.startingAbilityEssence, cfg.abilityEssencePerLevel, uint32(cfg.essenceStartLevel),
             cfg.talentEssencePerLevel, uint32(cfg.talentEssenceStartLevel));
    cfg.talentCostPerRank = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Classless.TalentCostPerRank", 1);
    cfg.talentFlatCost = sConfigMgr->GetOption<bool>("ClasslessWildcard.Classless.TalentFlatCost", false);
    cfg.enforceTalentRows = sConfigMgr->GetOption<bool>("ClasslessWildcard.Classless.EnforceTalentRows", true);
    cfg.refundOnUnlearn = sConfigMgr->GetOption<bool>("ClasslessWildcard.Classless.RefundOnUnlearn", true);
    cfg.respecCostGold = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Classless.RespecCostGold", 50);

    {
        std::vector<uint32> costs = ParseUintList(sConfigMgr->GetOption<std::string>(
            "ClasslessWildcard.Classless.AbilityCostByRarity", "1,2,3,5,8"));
        for (size_t i = 0; i < costs.size() && i < 5; ++i)
            cfg.abilityCostByRarity[i] = costs[i];
    }

    // The starting hand is FOUR cards. The screen is built around four and the
    // number is the mechanic, not a display limit, so a larger setting is
    // clamped rather than half-dealt.
    cfg.wcStartingAbilities = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.StartingAbilities", 4);
    if (cfg.wcStartingAbilities > ClasslessWildcard::MAX_STARTING_HAND)
    {
        LOG_ERROR("module.classless",
                  "mod-classless-wildcard: ClasslessWildcard.Wildcard.StartingAbilities = {} is above the "
                  "maximum starting hand of {}; using {}",
                  cfg.wcStartingAbilities, ClasslessWildcard::MAX_STARTING_HAND, ClasslessWildcard::MAX_STARTING_HAND);
        cfg.wcStartingAbilities = ClasslessWildcard::MAX_STARTING_HAND;
    }
    cfg.wcRollStartLevel = sConfigMgr->GetOption<uint8>("ClasslessWildcard.Wildcard.RollStartLevel", 10);
    cfg.wcAbilityEveryLevels = std::max<uint32>(1, sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.AbilityEveryLevels", 2));
    cfg.wcFreeRerollLevel = sConfigMgr->GetOption<uint8>("ClasslessWildcard.Wildcard.FreeRerollBelowLevel", 10);

    {
        // Roll weight per rarity. Equal weights make every entry in the pool
        // exactly as likely; the default ladder makes a legendary roll at a
        // quarter the rate of a common.
        std::vector<uint32> weights = ParseUintList(sConfigMgr->GetOption<std::string>(
            "ClasslessWildcard.Wildcard.RarityWeights", "100,85,65,45,25"));
        for (size_t i = 0; i < weights.size() && i < 5; ++i)
            cfg.wcRarityWeights[i] = weights[i];
    }

    {
        std::vector<uint32> secs = ParseUintList(sConfigMgr->GetOption<std::string>(
            "ClasslessWildcard.Rarity.CooldownSeconds", "30,60,180,600"));
        for (size_t i = 0; i < secs.size() && i < 4; ++i)
            cfg.rarityCooldownMs[i] = secs[i] * 1000;
        std::vector<uint32> tr = ParseUintList(sConfigMgr->GetOption<std::string>(
            "ClasslessWildcard.Rarity.TalentRows", "2,4,6,8"));
        for (size_t i = 0; i < tr.size() && i < 4; ++i)
            cfg.rarityTalentRow[i] = tr[i];
        std::vector<uint32> lv = ParseUintList(sConfigMgr->GetOption<std::string>(
            "ClasslessWildcard.Rarity.LevelFloors", "25,50"));
        for (size_t i = 0; i < lv.size() && i < 2; ++i)
            cfg.rarityLevel[i] = lv[i];
    }

    {
        // Rank is the steepest thing a single roll can hand over, so it gets
        // its own ladder rather than borrowing the rarity one.
        std::vector<uint32> weights = ParseUintList(sConfigMgr->GetOption<std::string>(
            "ClasslessWildcard.Wildcard.TalentRankWeights", "100,75,50,25,10"));
        for (size_t i = 0; i < weights.size() && i < 5; ++i)
            cfg.wcTalentRankWeights[i] = weights[i];
    }

    cfg.wcTalentUpgradeBase = sConfigMgr->GetOption<uint32>(
        "ClasslessWildcard.Wildcard.TalentUpgradeBaseChance", 0);
    cfg.wcTalentUpgradePerScroll = sConfigMgr->GetOption<uint32>(
        "ClasslessWildcard.Wildcard.TalentUpgradePerScroll", 20);
    cfg.wcTalentUpgradeMaxScrolls = sConfigMgr->GetOption<uint32>(
        "ClasslessWildcard.Wildcard.TalentUpgradeMaxScrolls", 5);

    cfg.wcSynergyBaseChance = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.SynergyBaseChance", 10);
    cfg.wcSynergyIncrement = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.SynergyIncrement", 10);
    cfg.wcSynergyBanRolls = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.SynergyBanRolls", 25);
    cfg.wcScrollItemId = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.ScrollItemId", 990101);
    cfg.wcTalentEveryLevels = std::max<uint32>(1, sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.TalentEveryLevels", 2));
    // Phase for the talent roll, so it can land on the levels the ability roll
    // does not. Without it a cadence of 2 for both would stack them on the same
    // levels and leave the levels between empty.
    cfg.wcTalentRollOffset = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.TalentRollOffset", 1);
    cfg.wcRerollsPerLevel = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.RerollsPerLevel", 3);
    cfg.wcFreeScrollEveryLevels = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.FreeScrollEveryLevels", 0);
    cfg.wcFreeScrollCount = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.FreeScrollCount", 1);
    cfg.wcScrollBuyEnable = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.ScrollBuyEnable", 1);
    cfg.wcScrollBuyBaseCopper = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.ScrollBuyBaseCopper", 500);
    cfg.wcScrollBuyPerLevelCopper = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.ScrollBuyPerLevelCopper", 500);

    cfg.urMaxRage = sConfigMgr->GetOption<uint32>("ClasslessWildcard.UniversalResources.MaxRage", 1000);
    cfg.urMaxEnergy = sConfigMgr->GetOption<uint32>("ClasslessWildcard.UniversalResources.MaxEnergy", 100);
    cfg.urRageDealtPct = sConfigMgr->GetOption<uint32>("ClasslessWildcard.UniversalResources.RageFromDealtPct", 100);
    cfg.urRageTakenPct = sConfigMgr->GetOption<uint32>("ClasslessWildcard.UniversalResources.RageFromTakenPct", 100);

    cfg.chassisEnable = sConfigMgr->GetOption<bool>("ClasslessWildcard.Chassis.Enable", true);
    cfg.chassisClass = uint8(sConfigMgr->GetOption<uint32>("ClasslessWildcard.Chassis.Class", CLASS_PALADIN));
    // The chassis must own a real mana pool. Heroes cast whatever they learn,
    // and a great many of those spells cost mana or a percentage of base mana;
    // on a rage or energy chassis the character has neither, so the abilities
    // simply would not fire. Refuse the setting rather than hand someone a
    // realm of Heroes who cannot cast.
    if (cfg.chassisEnable)
    {
        ChrClassesEntry const* chassis = sChrClassesStore.LookupEntry(cfg.chassisClass);
        if (!chassis || Powers(chassis->powerType) != POWER_MANA)
        {
            LOG_ERROR("module.classless",
                      "mod-classless-wildcard: ClasslessWildcard.Chassis.Class = {} is not a "
                      "mana class — Heroes there could not pay for a mana spell. Falling back "
                      "to Paladin ({}).", cfg.chassisClass, uint32(CLASS_PALADIN));
            cfg.chassisClass = CLASS_PALADIN;
        }
    }

    cfg.usMeleeAPPerAgi = sConfigMgr->GetOption<float>("ClasslessWildcard.UniversalStats.MeleeAPPerAgility", 1.0f);
    cfg.usRangedAPPerAgi = sConfigMgr->GetOption<float>("ClasslessWildcard.UniversalStats.RangedAPPerAgility", 1.0f);
    cfg.usSpellPowerPerInt = sConfigMgr->GetOption<float>("ClasslessWildcard.UniversalStats.SpellPowerPerIntellect", 0.5f);

    cfg.statsEnable = sConfigMgr->GetOption<bool>("ClasslessWildcard.Stats.Enable", true);
    cfg.statStartingPoints = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Stats.StartingPoints", 4);
    cfg.statPointsPerLevel = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Stats.PointsPerLevel", 2);
    cfg.statValuePerPoint = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Stats.ValuePerPoint", 1);

    cfg.rebirthEnable = sConfigMgr->GetOption<bool>("ClasslessWildcard.Rebirth.Enable", true);
    cfg.rebirthCostGold = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Rebirth.CostGold", 100);

    cfg.npcEntry = sConfigMgr->GetOption<uint32>("ClasslessWildcard.NpcEntry", 990100);
}

// -------------------------------------------------------------------------
// Library building
// -------------------------------------------------------------------------

void ClasslessMgr::BuildLibrary()
{
    if (!cfg.enabled)
        return;

    _abilities.clear();
    _skillLearnedClassSpells.clear();
    _talents.clear();
    _spellToFirst.clear();

    uint32 const dkMask = 1 << (CLASS_DEATH_KNIGHT - 1);

    // Trainer allowlist + REAL learn levels: what classes actually learn is
    // starter spells + class-trainer lists (npc_trainer). This kills NPC/pet
    // variants ("Demonic Immolate") and tiers every rank by the level a real
    // class would learn it.
    std::unordered_map<uint32, uint8> learnLevels; // spellId -> req level
    // Spells that reached learnLevels ONLY because another spell teaches them.
    // The dedupe below needs to tell those apart: see the comment there.
    std::unordered_set<uint32> taughtOnly;
    bool useTrainerFilter = cfg.trainerTaughtOnly;
    if (useTrainerFilter)
    {
        // AzerothCore master uses trainer/trainer_spell; older databases used
        // npc_trainer. A query against a missing table is FATAL, so probe
        // information_schema first and use whichever table this DB has.
        auto tableExists = [](char const* table) -> bool
        {
            QueryResult r = WorldDatabase.Query(
                "SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{}'", table);
            return r != nullptr;
        };

        std::string trainerQuery;
        if (tableExists("trainer_spell"))
            trainerQuery = "SELECT SpellId, MIN(ReqLevel) FROM trainer_spell WHERE ReqSkillLine = 0 AND SpellId > 0 GROUP BY SpellId";
        else if (tableExists("npc_trainer"))
            trainerQuery = "SELECT SpellID, MIN(ReqLevel) FROM npc_trainer WHERE ReqSkillLine = 0 AND SpellID > 0 GROUP BY SpellID";

        if (trainerQuery.empty())
        {
            LOG_ERROR("module.classless", "mod-classless-wildcard: no trainer_spell/npc_trainer table found — "
                "TrainerTaughtOnly filter disabled for this session");
            useTrainerFilter = false;
        }

        if (useTrainerFilter)
        {
            if (QueryResult res = WorldDatabase.Query(trainerQuery))
            {
                do
                {
                    Field* f = res->Fetch();
                    uint32 sid = f[0].Get<uint32>();
                    uint8 lvl = uint8(std::min<uint32>(f[1].Get<uint32>(), 255));
                    SpellInfo const* si = sSpellMgr->GetSpellInfo(sid);
                    if (!si)
                        continue;
                    bool wrapper = false;
                    for (uint8 ei = 0; ei < MAX_SPELL_EFFECTS; ++ei)
                        if (si->Effects[ei].Effect == SPELL_EFFECT_LEARN_SPELL && si->Effects[ei].TriggerSpell)
                        {
                            learnLevels.emplace(uint32(si->Effects[ei].TriggerSpell), lvl);
                            wrapper = true;
                        }
                    if (!wrapper)
                        learnLevels.emplace(sid, lvl);
                } while (res->NextRow());
            }
            if (tableExists("playercreateinfo_spell_custom"))
                if (QueryResult res = WorldDatabase.Query("SELECT Spell FROM playercreateinfo_spell_custom"))
                    do
                        learnLevels.emplace(res->Fetch()[0].Get<uint32>(), uint8(1));
                    while (res->NextRow());

            // Trainers are not the only way a class gets a spell, and the two
            // gaps mattered: a spell learned automatically with the class
            // (every starting ability, and Battle Stance) and a spell handed
            // over by a class quest (Defensive Stance, Berserker Stance,
            // Taunt, Bear Form, Maul, the warlock's demons, the shaman's
            // totems). Neither is on a trainer list, so the filter dropped
            // every one of them -- which is why Rend could be rolled while
            // Battle Stance, the stance Rend cannot be used outside of, was
            // not in the library at all and could never be handed over.
            //
            // Both are read from the client's own data rather than a list of
            // ids, so they follow whatever a realm's DBCs actually say.
            uint32 autoLearned = 0, questTaught = 0;
            {
                std::unordered_set<uint32> classSpells;
                for (uint32 i = 0; i < sSkillLineAbilityStore.GetNumRows(); ++i)
                {
                    SkillLineAbilityEntry const* sla = sSkillLineAbilityStore.LookupEntry(i);
                    if (!sla || !sla->ClassMask)
                        continue;
                    SkillLineEntry const* line = sSkillLineStore.LookupEntry(sla->SkillLine);
                    if (!line || line->categoryId != SKILL_CATEGORY_CLASS)
                        continue;
                    classSpells.insert(sla->Spell);

                    // AcquireMethod 1/2: learned with the skill line itself
                    if (sla->AcquireMethod != SKILL_LINE_ABILITY_LEARNED_ON_SKILL_VALUE
                        && sla->AcquireMethod != SKILL_LINE_ABILITY_LEARNED_ON_SKILL_LEARN)
                        continue;
                    SpellInfo const* si = sSpellMgr->GetSpellInfo(sla->Spell);
                    if (!si)
                        continue;
                    // hidden state and proc passives ride in the same way and
                    // are not abilities: they carry no level of their own
                    if (si->IsPassive())
                        continue;
                    uint32 lvl = si->SpellLevel ? si->SpellLevel : si->BaseLevel;
                    if (!lvl)
                        continue;
                    if (learnLevels.emplace(sla->Spell, uint8(std::min<uint32>(lvl, 255))).second)
                        ++autoLearned;
                }

                // Taught by another spell. Class quests reward a wrapper --
                // "Path of Defense", "Path of the Berserker", "Bear Form",
                // "Teach Summon Voidwalker" -- whose only effect is to teach
                // the real ability, so the ability itself appears on no list.
                for (uint32 sid = 1; sid < sSpellMgr->GetSpellInfoStoreSize(); ++sid)
                {
                    SpellInfo const* teacher = sSpellMgr->GetSpellInfo(sid);
                    if (!teacher)
                        continue;
                    // A TALENT that teaches a spell is not a quest: the spell
                    // is part of the talent and belongs to the talent tree.
                    // Admitting Primal Fury, Spirit Weapons and Tree of Life
                    // here would make each of them an ability line, which
                    // takes the talent off the tree (ReplaceAbilityTalents)
                    // and strands everything that depends on it.
                    if (GetTalentSpellCost(sid))
                        continue;
                    for (uint8 ei = 0; ei < MAX_SPELL_EFFECTS; ++ei)
                    {
                        if (teacher->Effects[ei].Effect != SPELL_EFFECT_LEARN_SPELL)
                            continue;
                        uint32 taught = uint32(teacher->Effects[ei].TriggerSpell);
                        if (!taught || !classSpells.count(taught))
                            continue;
                        SpellInfo const* si = sSpellMgr->GetSpellInfo(taught);
                        if (!si)
                            continue;
                        uint32 lvl = si->SpellLevel ? si->SpellLevel : si->BaseLevel;
                        if (learnLevels.emplace(taught, uint8(std::min<uint32>(lvl ? lvl : 1, 255))).second)
                        {
                            taughtOnly.insert(taught);
                            ++questTaught;
                        }
                    }
                }
            }

            if (learnLevels.empty())
            {
                LOG_ERROR("module.classless", "mod-classless-wildcard: trainer tables yielded no class spells — "
                    "TrainerTaughtOnly filter disabled for this session");
                useTrainerFilter = false;
            }
            else
                LOG_INFO("module.classless", "mod-classless-wildcard: {} spells classes actually learn collected "
                         "({} learned with the class, {} from class quests)",
                         learnLevels.size(), autoLearned, questTaught);
        }
    }

    // ---- abilities from SkillLineAbility.dbc (class spells) ----
    for (uint32 i = 0; i < sSkillLineAbilityStore.GetNumRows(); ++i)
    {
        SkillLineAbilityEntry const* sla = sSkillLineAbilityStore.LookupEntry(i);
        if (!sla || !sla->ClassMask)
            continue;
        if (!cfg.includeRacials && sla->RaceMask)
            continue;
        if (!cfg.includeDeathKnight && (sla->ClassMask & dkMask) && sla->ClassMask == dkMask)
            continue;

        // only real class ability lines — keeps weapon/armor proficiencies,
        // professions, languages and generic junk out of the roll pool
        SkillLineEntry const* skillLine = sSkillLineStore.LookupEntry(sla->SkillLine);
        if (!skillLine || skillLine->categoryId != SKILL_CATEGORY_CLASS)
            continue;

        // Remember which tab the client will file this spell under. Done
        // before the pool filters below, so a spell kept out of the roll pool
        // still lands in the right tab if a Hero gets it some other way.
        _spellSkillLine[sla->Spell] = uint16(sla->SkillLine);
        _classSkillLines.insert(uint16(sla->SkillLine));

        // Spells the core hands out free with the line itself. 38 in the whole
        // game, and the only ones a Hero can end up with by owning nothing.
        if (sla->AcquireMethod == SKILL_LINE_ABILITY_LEARNED_ON_SKILL_VALUE
            || sla->AcquireMethod == SKILL_LINE_ABILITY_LEARNED_ON_SKILL_LEARN)
            _skillLearnedClassSpells.insert(sla->Spell);

        SpellInfo const* info = sSpellMgr->GetSpellInfo(sla->Spell);
        if (!info || !info->SpellName[0] || !*info->SpellName[0])
            continue;
        if (GetTalentSpellCost(sla->Spell)) // talent spells live in the talent pool
            continue;
        if (info->IsPassive() && !cfg.includePassives)
            continue;
        // Ranged auto-attacks (Auto Shot, Shoot, Throw) are not abilities to
        // roll for: they fire on their own once a ranged weapon is equipped,
        // and the module already teaches the ones a Hero needs as
        // proficiencies. Auto Shot is learned with the Hunter class rather
        // than from a trainer, so nothing else keeps it out.
        if (info->HasAttribute(SPELL_ATTR2_AUTO_REPEAT))
            continue;
        if (cfg.excludedSpells.count(sla->Spell))
            continue;

        // proficiency-style and crafting effects never belong in the pool
        bool utility = false;
        for (uint8 ei = 0; ei < MAX_SPELL_EFFECTS && !utility; ++ei)
            switch (info->Effects[ei].Effect)
            {
                case SPELL_EFFECT_WEAPON:
                case SPELL_EFFECT_PROFICIENCY:
                case SPELL_EFFECT_DUAL_WIELD:
                case SPELL_EFFECT_LANGUAGE:
                case SPELL_EFFECT_TRADE_SKILL:
                case SPELL_EFFECT_SKILL:
                case SPELL_EFFECT_ATTACK:
                    utility = true;
                    break;
                default:
                    break;
            }
        if (utility)
            continue;

        // spells the module itself teaches as proficiencies
        bool isProficiency = false;
        for (uint32 prof : cfg.proficiencySpells)
            if (prof == sla->Spell)
                isProficiency = true;
        if (isProficiency)
            continue;

        uint32 first = sSpellMgr->GetFirstSpellInChain(sla->Spell);
        if (cfg.excludedSpells.count(first))
            continue;

        AbilityEntry& e = _abilities[first];
        if (!e.firstSpellId)
        {
            e.firstSpellId = first;
            e.passive = info->IsPassive();
        }
        e.classMask |= sla->ClassMask;
    }

    // fill rank chains and heuristics
    for (auto itr = _abilities.begin(); itr != _abilities.end();)
    {
        AbilityEntry& e = itr->second;
        uint32 spellId = e.firstSpellId;
        while (spellId)
        {
            SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
            if (!info)
                break;
            e.ranks.push_back(spellId);
            e.rankLevels.push_back(uint8(info->SpellLevel ? info->SpellLevel : info->BaseLevel));
            _spellToFirst[spellId] = e.firstSpellId;
            spellId = sSpellMgr->GetNextSpellInChain(spellId);
        }

        if (e.ranks.empty())
        {
            itr = _abilities.erase(itr);
            continue;
        }

        // trainer filter: the line must contain at least one rank a class
        // actually learns; ranks take their REAL trainer learn level
        if (useTrainerFilter)
        {
            bool trainable = false;
            for (size_t ri = 0; ri < e.ranks.size(); ++ri)
                if (auto lvlItr = learnLevels.find(e.ranks[ri]); lvlItr != learnLevels.end())
                {
                    trainable = true;
                    if (lvlItr->second > e.rankLevels[ri])
                        e.rankLevels[ri] = lvlItr->second;
                }
            if (!trainable)
            {
                for (uint32 sp : e.ranks)
                    _spellToFirst.erase(sp);
                itr = _abilities.erase(itr);
                continue;
            }
            // learn levels never decrease across ranks
            for (size_t ri = 1; ri < e.rankLevels.size(); ++ri)
                if (e.rankLevels[ri] < e.rankLevels[ri - 1])
                    e.rankLevels[ri] = e.rankLevels[ri - 1];
        }

        SpellInfo const* firstInfo = sSpellMgr->GetSpellInfo(e.firstSpellId);
        if (firstInfo && firstInfo->SpellName[0])
            e.name = firstInfo->SpellName[0];
        e.type = ClassifyAbility(firstInfo, e.passive);

        // no talent row yet -- talents load later, and the re-gate pass below
        // rates every talent-taught line again once they have
        e.rarity = RarityFromPower(LineCooldown(e), 0, e.rankLevels.empty() ? 0 : e.rankLevels[0]);
        e.cost = cfg.abilityCostByRarity[uint8(e.rarity)];
        e.weight = 0; // 0 = use rarity weight
        ++itr;
    }

    // Dedupe by NAME: the DBC holds multiple spell ids with identical names
    // (unchained copies, NPC variants, Polymorph: Pig against Polymorph). Keep
    // the best line per name -- most ranks, then lowest id -- and take the rest
    // out of play, merging class masks so browsing still finds the survivor
    // under every class. A loser the module could still grant under the
    // surviving name is disabled; one that only ever came from a quest or an
    // item is dropped outright, so that source keeps working.
    {
        std::unordered_map<std::string, AbilityEntry*> byName;
        std::vector<uint32> dropped;
        uint32 disabled = 0;
        for (auto& [first, e] : _abilities)
        {
            if (!e.enabled || e.name.empty())
                continue;
            auto [itr2, inserted] = byName.try_emplace(e.name, &e);
            if (inserted)
                continue;
            AbilityEntry* keep = itr2->second;
            bool newBetter = e.ranks.size() > keep->ranks.size()
                || (e.ranks.size() == keep->ranks.size() && e.firstSpellId < keep->firstSpellId);
            AbilityEntry* loser = newBetter ? keep : &e;
            if (newBetter)
            {
                e.classMask |= keep->classMask;
                itr2->second = &e;
            }
            else
                keep->classMask |= e.classMask;

            // A duplicate that is in the library ONLY because something teaches
            // it -- Polymorph: Pig, from its mage quest -- leaves the library
            // altogether rather than sitting here disabled. Disabled is the
            // worst of both: the Hero can never roll or buy it, AND
            // BlockOutsideSpellSources takes it back off them when the quest
            // hands it over, so the reward silently does nothing. Dropping the
            // line puts it back outside the module, where the quest teaches it
            // like it does on any realm. Lines that a trainer or the class
            // itself also teaches stay, disabled: those the module can grant
            // under their surviving name.
            bool taughtDuplicate = !loser->ranks.empty();
            for (uint32 rankSpell : loser->ranks)
                if (!taughtOnly.count(rankSpell))
                    taughtDuplicate = false;
            if (taughtDuplicate)
                dropped.push_back(loser->firstSpellId);
            else
            {
                loser->enabled = false;
                ++disabled;
            }
        }
        for (uint32 first : dropped)
        {
            if (auto itr2 = _abilities.find(first); itr2 != _abilities.end())
            {
                for (uint32 rankSpell : itr2->second.ranks)
                    _spellToFirst.erase(rankSpell);
                _abilities.erase(itr2);
            }
        }
        LOG_INFO("module.classless",
                 "mod-classless-wildcard: disabled {} duplicate-name ability lines, dropped {} taught-only duplicates",
                 disabled, uint32(dropped.size()));
    }

    // ---- talents from Talent.dbc / TalentTab.dbc ----
    for (uint32 i = 0; i < sTalentStore.GetNumRows(); ++i)
    {
        TalentEntry const* talent = sTalentStore.LookupEntry(i);
        if (!talent)
            continue;

        TalentTabEntry const* tab = sTalentTabStore.LookupEntry(talent->TalentTab);
        if (!tab || tab->petTalentMask || !tab->ClassMask)
            continue;
        if (!cfg.includeDeathKnight && tab->ClassMask == dkMask)
            continue;

        TalentPoolEntry t;
        t.talentId = talent->TalentID;
        t.tabId = talent->TalentTab;
        t.classMask = tab->ClassMask;
        t.row = talent->Row;
        t.col = talent->Col;
        t.dependsOn = talent->DependsOn;
        t.dependsOnRank = talent->DependsOnRank;

        for (uint8 r = 0; r < MAX_TALENT_RANK; ++r)
        {
            uint32 rankSpell = talent->RankID[r];
            if (!rankSpell || !sSpellMgr->GetSpellInfo(rankSpell))
                break;
            if (cfg.excludedSpells.count(rankSpell))
                break;
            t.rankSpells[r] = rankSpell;
            t.maxRank = r + 1;
        }

        if (!t.maxRank)
            continue;

        t.rarity = RarityFromTalentRow(t.row);
        t.weight = 0;
        _talents[t.talentId] = t;
    }

    // Talent-granted spells lie about their level: Unstable Affliction reports
    // SpellLevel 6 although it is a 41-point talent, so level gating alone
    // would still hand it to a level 6 Hero. Gate them by the tree row that
    // actually grants them (row R unlocks at 10 + R*5). Runs before
    // LoadOverrides so an admin override still wins.
    {
        std::unordered_map<uint32, uint32> spellRow; // talent rank spell -> row
        for (auto const& [talentId, t] : _talents)
            for (uint8 r = 0; r < t.maxRank; ++r)
                if (t.rankSpells[r])
                    spellRow[t.rankSpells[r]] = t.row;

        uint32 regated = 0;
        for (auto& [firstSpell, e] : _abilities)
        {
            uint32 row = 0;
            bool fromTalent = false;
            for (uint32 sp : e.ranks)
                if (auto it = spellRow.find(sp); it != spellRow.end())
                {
                    fromTalent = true;
                    row = std::max(row, it->second);
                }
            if (!fromTalent || e.rankLevels.empty())
                continue;

            uint8 need = uint8(std::min<uint32>(255, 10 + row * 5));
            if (e.rankLevels[0] < need)
            {
                uint8 shift = need - e.rankLevels[0];
                for (uint8& lv : e.rankLevels)
                    lv = uint8(std::min<uint32>(255, uint32(lv) + shift));
                ++regated;
            }
            // The row is a rarity signal whether or not the level needed
            // moving: a capstone is a capstone at any level. This used to sit
            // behind the `continue` above, so a talent line already gated
            // correctly never had its row counted at all.
            e.rarity = RarityFromPower(LineCooldown(e), row, e.rankLevels[0]);
            e.cost = cfg.abilityCostByRarity[uint8(e.rarity)];
        }
        if (regated)
            LOG_INFO("module.classless",
                     "mod-classless-wildcard: re-gated {} talent-granted ability lines to their talent tier", regated);
    }

    // Variants come after the base pool is final (dedupe and talent re-gating
    // done) and before overrides, so a realm can still tune any variant row
    // in cw_ability_override like any other ability.
    LoadVariants();
    ResolveTalentAbilityLines();

    std::unordered_set<uint32> overridden;
    LoadOverrides(&overridden);
    // now the bases are final, and the variants can be told what they vary
    ResyncVariants(overridden);
    BuildFormSpellMap();
    LoadFormKits();
    LoadArchetypes();
    StripSpellTools();
    _libraryBuilt = true;

    LOG_INFO("module", "mod-classless-wildcard: library built — {} ability lines, {} talents.",
             _abilities.size(), _talents.size());
}

void ClasslessMgr::LoadOverrides(std::unordered_set<uint32>* overridden)
{
    if (QueryResult result = WorldDatabase.Query("SELECT first_spell, rarity, cost, weight, enabled FROM cw_ability_override"))
    {
        do
        {
            Field* f = result->Fetch();
            if (overridden)
                overridden->insert(f[0].Get<uint32>());
            auto itr = _abilities.find(f[0].Get<uint32>());
            if (itr == _abilities.end())
                continue;
            AbilityEntry& e = itr->second;
            uint8 rarity = f[1].Get<uint8>();
            if (rarity < uint8(Rarity::Max))
                e.rarity = Rarity(rarity);
            if (uint32 cost = f[2].Get<uint32>())
                e.cost = cost;
            e.weight = f[3].Get<uint32>();
            e.enabled = f[4].Get<bool>();
        } while (result->NextRow());
    }

    if (QueryResult result = WorldDatabase.Query("SELECT talent_id, rarity, weight, enabled FROM cw_talent_override"))
    {
        do
        {
            Field* f = result->Fetch();
            auto itr = _talents.find(f[0].Get<uint32>());
            if (itr == _talents.end())
                continue;
            TalentPoolEntry& t = itr->second;
            uint8 rarity = f[1].Get<uint8>();
            if (rarity < uint8(Rarity::Max))
                t.rarity = Rarity(rarity);
            t.weight = f[2].Get<uint32>();
            t.enabled = f[3].Get<bool>();
        } while (result->NextRow());
    }
}

// A variant is registered one rarity tier above the line it varies, and that
// sum was worked out in LoadVariants -- which runs BEFORE LoadOverrides, on
// purpose, so a realm can tune a variant row in cw_ability_override like any
// other ability. The cost of that order is that every variant was derived from
// its base's heuristic rarity rather than its final one: the shipped example
// row makes Backstab epic, and its elemental copies stayed uncommon, one tier
// above the common Backstab used to be.
//
// So do the sum again now the bases are settled. A variant with a row of its
// own in cw_ability_override is left exactly as the realm wrote it.
uint32 ClasslessMgr::ResyncVariants(std::unordered_set<uint32> const& overridden)
{
    if (!cfg.elementalEnable)
        return 0;

    uint32 changed = 0;
    for (auto& [firstSpell, e] : _abilities)
    {
        if (!e.variant || !e.variantBase || overridden.count(firstSpell))
            continue;
        auto baseItr = _abilities.find(e.variantBase);
        if (baseItr == _abilities.end())
            continue;
        AbilityEntry const& base = baseItr->second;

        // a base switched off by an override takes its copies with it, the
        // same way LoadVariants refuses to build one from a disabled base
        if (!base.enabled && e.enabled)
        {
            e.enabled = false;
            ++changed;
        }

        uint8 const bumped = uint8(std::min<uint32>(uint32(base.rarity) + cfg.elementalRarityBump,
                                                    uint32(Rarity::Legendary)));
        if (uint8(e.rarity) == bumped)
            continue;

        e.rarity = static_cast<Rarity>(bumped);
        e.cost = cfg.abilityCostByRarity[bumped];
        e.weight = std::max<uint32>(1, cfg.wcRarityWeights[bumped] * cfg.elementalRollWeightPct / 100);
        ++changed;
    }

    if (changed)
        LOG_INFO("module.classless",
                 "mod-classless-wildcard: re-derived {} elemental variant(s) from their final base rarity", changed);
    return changed;
}

// Which ability puts a Hero into each shapeshift form?
//
// Derived from spell data rather than a table: a form spell is simply one whose
// aura is SPELL_AURA_MOD_SHAPESHIFT, and the form it grants is that effect's
// MiscValue. Only library entries are considered, so the map can never point at
// something a Hero has no way to obtain.
//
// EVERY rank is scanned, not just the first, and the map stores the rank spell
// that grants the form. Higher ranks change form: Dire Bear Form is rank 2 of
// Bear Form and puts you in form 8 rather than 5, and Swift Flight Form is rank
// 2 of Flight Form. Reading rank 1 alone left those two forms unmapped, so an
// ability locked to Dire Bear -- Mangle (Bear) -- could be rolled with no way
// to use it and nothing the module could hand over. Storing the rank rather
// than the line also keeps "can the Hero already use this?" honest: owning Bear
// Form at rank 1 is not owning Dire Bear.
void ClasslessMgr::BuildFormSpellMap()
{
    _formSpells.clear();
    for (auto const& [firstSpell, e] : _abilities)
        for (uint32 rankSpell : e.ranks)
        {
            SpellInfo const* info = sSpellMgr->GetSpellInfo(rankSpell);
            if (!info)
                continue;
            for (uint8 ei = 0; ei < MAX_SPELL_EFFECTS; ++ei)
            {
                if (info->Effects[ei].ApplyAuraName != SPELL_AURA_MOD_SHAPESHIFT)
                    continue;
                uint32 form = uint32(info->Effects[ei].MiscValue);
                if (form && !_formSpells.count(form))
                    _formSpells[form] = rankSpell;
            }
        }
    LOG_INFO("module.classless", "mod-classless-wildcard: {} shapeshift forms mapped to abilities",
             _formSpells.size());
}

// An ability that can only be used in a stance or form is useless without it.
// Charge needs Battle Stance, Maul needs Bear Form, Shred needs Cat Form -- and
// under the class system nobody could ever hold one without the other, because
// the stance came with the class. A Hero can draw Charge on its own and find it
// permanently greyed out.
//
// SpellInfo::Stances is a mask of the forms a spell may be cast in, so this is
// general: it covers every stance- or form-locked ability in the game without
// naming any of them.
void ClasslessMgr::GrantRequiredForm(Player* player, AbilityEntry const& e)
{
    if (!cfg.formKitsEnable || _grantingKit)
        return;

    SpellInfo const* info = sSpellMgr->GetSpellInfo(e.firstSpellId);
    if (!info || !info->Stances)
        return;

    // A non-empty Stances mask does NOT mean the spell needs a form. Half the
    // priest and druid book lists one -- Shadow Word: Pain names Shadowform,
    // Nature's Grasp names Cat, Bear and Moonkin -- and carries
    // SPELL_ATTR2_ALLOW_WHILE_NOT_SHAPESHIFTED, which is exactly what
    // SpellInfo::CheckShapeshift reads to allow the cast outside any form. The
    // mask is there to permit the form, not to require it, so handing one over
    // would be a free ability for an entry that needs nothing.
    if (info->HasAttribute(SPELL_ATTR2_ALLOW_WHILE_NOT_SHAPESHIFTED))
        return;

    // Stances is a 64-bit mask, so the bit has to be built as one: a 32-bit
    // shift is undefined past form 32 and quietly matches nothing.
    //
    // Already able to use it? Any one of the allowed forms is enough, so a
    // Hero who owns Berserker Stance is not handed Battle Stance as well.
    for (auto const& [form, formSpell] : _formSpells)
        if ((info->Stances & (uint64(1) << (form - 1))) && player->HasSpell(formSpell))
            return;

    // Otherwise hand over the lowest-numbered form that would unlock it, which
    // keeps the choice stable rather than depending on map order.
    uint32 best = 0, bestForm = 0;
    for (auto const& [form, formSpell] : _formSpells)
        if ((info->Stances & (uint64(1) << (form - 1))) && (!bestForm || form < bestForm))
        {
            bestForm = form;
            best = formSpell;
        }
    if (!best)
        return;

    // _formSpells stores the RANK that grants the form (Dire Bear Form, not
    // Bear Form), so resolve it back to the line that has to be owned.
    AbilityEntry const* formEntry = FindAbilityBySpell(best);
    if (!formEntry)
        return;
    // Already owned, just not at the rank that grants this form yet: the rank
    // arrives with level on its own. Re-granting here would rewrite the entry
    // and stamp a line the Hero BOUGHT as a free companion, which the prune
    // would then be entitled to take away.
    if (GetState(player).abilities.count(formEntry->firstSpellId))
        return;

    GrantGuard guard(_grantingKit);
    GrantAbilityInternal(player, *formEntry, GrantSource::Companion, true, false);
    if (!_revealSuppress)
        Msg(player, Acore::StringFormat("{} can only be used in {}, so that comes with it.",
            SpellName(e.firstSpellId), SpellName(best)));
}

// Elemental variants: the same strike dealt as an element, generated into
// spell_dbc by data/sql/generators/gen_elemental_variants.py and listed in
// cw_ability_variants. Each row names the variant line's first spell and the
// base line it varies. The variant becomes an ordinary AbilityEntry -- bought,
// rolled, rerolled, locked, ranked up on level like anything else -- with its
// base's levels, class mask (so synergy counts it toward the same classes) and
// spellbook tab, and one rarity tier above the base because it is strictly
// the more interesting spell.
//
// A variant whose base is not in the pool is skipped and logged rather than
// registered: the generator mirrors BuildLibrary's filters, but a realm that
// excluded the base by config should not get the variant either.
void ClasslessMgr::LoadVariants()
{
    if (!cfg.elementalEnable)
        return;

    QueryResult result = WorldDatabase.Query(
        "SELECT variant_first_spell, base_first_spell FROM cw_ability_variants WHERE enabled = 1");
    if (!result)
    {
        LOG_INFO("module.classless", "mod-classless-wildcard: no elemental variants configured");
        return;
    }

    uint32 added = 0, skipped = 0;
    do
    {
        Field* f = result->Fetch();
        uint32 const variantFirst = f[0].Get<uint32>();
        uint32 baseFirst = f[1].Get<uint32>();

        // The generator writes the first rank it copied. For a talent-taught
        // strike (Mortal Strike, Devastate, Mangle, Aimed Shot, Hemorrhage)
        // that is the first trained rank, not the talent spell that heads the
        // pool's line, so resolve through the rank map before the lookup.
        if (auto lineItr = _spellToFirst.find(baseFirst); lineItr != _spellToFirst.end())
            baseFirst = lineItr->second;

        auto baseItr = _abilities.find(baseFirst);
        if (baseItr == _abilities.end() || !baseItr->second.enabled)
        {
            // Expected for the Death Knight strikes on a realm with
            // IncludeDeathKnight off, so this is debug, not a warning; the
            // summary line below still carries the count.
            LOG_DEBUG("module.classless",
                      "mod-classless-wildcard: variant {} skipped, base {} is not in the ability pool",
                      variantFirst, baseFirst);
            ++skipped;
            continue;
        }
        if (_abilities.count(variantFirst))
            continue;

        AbilityEntry const& base = baseItr->second;
        AbilityEntry e;
        e.firstSpellId = variantFirst;
        e.passive = false;
        e.variant = true;

        // rank chain from spell_ranks, exactly as the stock pass walks it
        for (uint32 sp = variantFirst; sp; sp = sSpellMgr->GetNextSpellInChain(sp))
        {
            SpellInfo const* info = sSpellMgr->GetSpellInfo(sp);
            if (!info)
                break;
            e.ranks.push_back(sp);
            // the spell's own level, raised to the base rank's trainer level
            // where one exists, so a variant is never learnable before its base
            uint8 level = uint8(info->SpellLevel ? info->SpellLevel : info->BaseLevel);
            size_t const ri = e.ranks.size() - 1;
            if (ri < base.rankLevels.size())
                level = std::max(level, base.rankLevels[ri]);
            e.rankLevels.push_back(level);
        }
        if (e.ranks.empty())
        {
            LOG_WARN("module.classless",
                     "mod-classless-wildcard: variant {} skipped, spell is missing from spell_dbc", variantFirst);
            ++skipped;
            continue;
        }
        for (size_t ri = 1; ri < e.rankLevels.size(); ++ri)
            if (e.rankLevels[ri] < e.rankLevels[ri - 1])
                e.rankLevels[ri] = e.rankLevels[ri - 1];

        SpellInfo const* firstInfo = sSpellMgr->GetSpellInfo(variantFirst);
        if (firstInfo && firstInfo->SpellName[0])
            e.name = firstInfo->SpellName[0];
        e.type = ClassifyAbility(firstInfo, false);

        e.classMask = base.classMask;
        e.variantBase = baseFirst;
        uint8 const bumped = uint8(std::min<uint32>(uint32(base.rarity) + cfg.elementalRarityBump,
                                                    uint32(Rarity::Legendary)));
        e.rarity = static_cast<Rarity>(bumped);
        e.cost = cfg.abilityCostByRarity[bumped];
        // Roll weight is set explicitly rather than left to rarity. With the
        // shipped equal rarity weights the bump above changes nothing about
        // how often a variant rolls, and every strike gains seven siblings:
        // left at the rarity weight, the Wildcard pool would be mostly
        // elemental strikes. At 15% each, the seven together roughly equal one
        // more copy of the base.
        e.weight = std::max<uint32>(1, cfg.wcRarityWeights[bumped] * cfg.elementalRollWeightPct / 100);

        // same spellbook tab as the base
        if (auto lineItr = _spellSkillLine.find(base.firstSpellId); lineItr != _spellSkillLine.end())
            for (uint32 sp : e.ranks)
                _spellSkillLine[sp] = lineItr->second;
        for (uint32 sp : e.ranks)
            _spellToFirst[sp] = variantFirst;

        _abilities.emplace(variantFirst, std::move(e));
        ++added;
    } while (result->NextRow());

    // The generation id the rows were produced with. The client installer
    // prints the same id for the manifest it applied; when the two differ, a
    // player's tooltips describe rows this server is not running.
    std::string generation = "unknown";
    if (QueryResult meta = WorldDatabase.Query(
            "SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = 'cw_ability_variants_meta'"))
        if (QueryResult gen = WorldDatabase.Query(
                "SELECT `value` FROM cw_ability_variants_meta WHERE `key` = 'generation'"))
            generation = gen->Fetch()[0].Get<std::string>();

    LOG_INFO("module.classless",
             "mod-classless-wildcard: {} elemental variants registered ({} skipped), generation {}",
             added, skipped, generation);
}

// A talent that teaches a spell (Pyroblast, Mortal Strike, Mangle) is, on a
// classless realm, just another door to an ability line the pool already
// carries: the trainer ranks of that same spell. Taking the talent grants the
// line outright, so the spell ranks up with level like anything bought or
// rolled instead of sitting at the talent's rank 1 for the rest of the
// character's life. Resolved once the pool is final: a talent rank spell that
// heads a line, or teaches one through a learn effect, names that line.
void ClasslessMgr::ResolveTalentAbilityLines()
{
    uint32 resolved = 0;
    for (auto& entry : _talents)
    {
        TalentPoolEntry& t = entry.second;   // a structured binding cannot be captured below
        t.abilityLines.clear();
        auto add = [&](uint32 spellId)
        {
            auto itr = _spellToFirst.find(spellId);
            if (itr == _spellToFirst.end())
                return;
            AbilityEntry const* e = GetAbility(itr->second);
            if (!e || !e->enabled)
                return;
            if (std::find(t.abilityLines.begin(), t.abilityLines.end(), e->firstSpellId) == t.abilityLines.end())
                t.abilityLines.push_back(e->firstSpellId);
        };
        for (uint8 r = 0; r < t.maxRank; ++r)
        {
            uint32 rankSpell = t.rankSpells[r];
            if (!rankSpell)
                continue;
            add(rankSpell);
            if (SpellInfo const* info = sSpellMgr->GetSpellInfo(rankSpell))
                for (uint8 i = 0; i < MAX_SPELL_EFFECTS; ++i)
                    if (info->Effects[i].Effect == SPELL_EFFECT_LEARN_SPELL && info->Effects[i].TriggerSpell)
                        add(info->Effects[i].TriggerSpell);
        }
        if (!t.abilityLines.empty())
            ++resolved;
    }

    // With ReplaceAbilityTalents on, those talents leave the list altogether:
    // the ability line is the one way to the spell, and the entry is kept
    // aside so a talent that depended on it can be met by owning the ability.
    _replacedTalents.clear();
    if (cfg.replaceAbilityTalents)
    {
        for (auto itr = _talents.begin(); itr != _talents.end();)
        {
            if (itr->second.abilityLines.empty())
            {
                ++itr;
                continue;
            }
            _replacedTalents.emplace(itr->first, std::move(itr->second));
            itr = _talents.erase(itr);
        }
        LOG_INFO("module.classless",
                 "mod-classless-wildcard: {} ability talents taken off the Talents list; their ability lines stand in for them",
                 _replacedTalents.size());
        return;
    }
    LOG_INFO("module.classless",
             "mod-classless-wildcard: {} talents teach an ability line and grant it outright", resolved);
}

// Whether a Hero owns an ability that stands in for a talent taken off the
// list (0 when the talent is not one of those).
bool ClasslessMgr::OwnsReplacedTalent(CharState const& st, uint32 talentId) const
{
    auto itr = _replacedTalents.find(talentId);
    if (itr == _replacedTalents.end())
        return false;
    for (uint32 first : itr->second.abilityLines)
        if (st.abilities.count(first))
            return true;
    return false;
}

// The spells that come free with a form or stance, from `cw_form_kits`. Both
// columns are plain spell ids so a realm can pair anything with anything; the
// shipped rows are the kits the class system itself hands out.
void ClasslessMgr::LoadFormKits()
{
    // Loaded whichever way the config is set: GrantFormKit checks the flag at
    // grant time, so a `.reload config` can turn the feature on and off without
    // a restart.
    _formKits.clear();
    QueryResult result = WorldDatabase.Query(
        "SELECT form_spell, granted_spell FROM cw_form_kits WHERE enabled = 1");
    if (!result)
    {
        LOG_INFO("module.classless", "mod-classless-wildcard: no form starter kits configured");
        return;
    }

    uint32 skipped = 0;
    do
    {
        Field* f = result->Fetch();
        uint32 formSpell = f[0].Get<uint32>();
        uint32 granted = f[1].Get<uint32>();

        // A row naming a spell this core does not have would silently grant
        // nothing, so say so rather than leaving it to be discovered in game.
        if (!sSpellMgr->GetSpellInfo(formSpell) || !sSpellMgr->GetSpellInfo(granted))
        {
            LOG_WARN("module.classless",
                     "mod-classless-wildcard: cw_form_kits row {} -> {} names a spell that does not exist, ignored",
                     formSpell, granted);
            ++skipped;
            continue;
        }

        std::vector<uint32>& kit = _formKits[formSpell];
        if (std::find(kit.begin(), kit.end(), granted) == kit.end())
            kit.push_back(granted);
    } while (result->NextRow());

    uint32 pairs = 0;
    for (auto const& entry : _formKits)
        pairs += uint32(entry.second.size());
    LOG_INFO("module.classless",
             "mod-classless-wildcard: {} form starter kits ({} spells{})",
             _formKits.size(), pairs,
             skipped ? Acore::StringFormat(", {} rows ignored", skipped) : std::string());
}

void ClasslessMgr::LoadArchetypes()
{
    _archetypes.clear();
    QueryResult result = WorldDatabase.Query("SELECT id, name, description, abilities, talents FROM cw_archetypes ORDER BY id");
    if (!result)
        return;

    do
    {
        Field* f = result->Fetch();
        Archetype arch;
        arch.id = f[0].Get<uint32>();
        arch.name = f[1].Get<std::string>();
        arch.description = f[2].Get<std::string>();

        std::string abilitiesCsv = f[3].Get<std::string>();
        std::string talentsCsv = f[4].Get<std::string>();

        for (auto const& tok : Acore::Tokenize(abilitiesCsv, ',', false))
            if (Optional<uint32> id = Acore::StringTo<uint32>(tok))
                if (_abilities.count(*id))
                    arch.abilities.push_back(*id);

        // talents CSV: "talentId:rank,talentId:rank"
        for (auto const& tok : Acore::Tokenize(talentsCsv, ',', false))
        {
            auto parts = Acore::Tokenize(tok, ':', false);
            if (parts.empty())
                continue;
            Optional<uint32> tid = Acore::StringTo<uint32>(parts[0]);
            uint8 rank = 1;
            if (parts.size() > 1)
                if (Optional<uint32> r = Acore::StringTo<uint32>(parts[1]))
                    rank = uint8(std::min<uint32>(*r, MAX_TALENT_RANK));
            if (tid && _talents.count(*tid))
                arch.talents.emplace_back(*tid, rank);
        }

        _archetypes[arch.id] = arch;
    } while (result->NextRow());

    LOG_INFO("module", "mod-classless-wildcard: loaded {} archetypes.", _archetypes.size());
}

std::string ClasslessMgr::SpellNameOf(uint32 spellId) const
{
    return SpellName(spellId);
}

std::string ClasslessMgr::ArchetypeName(uint32 archetypeId) const
{
    auto itr = _archetypes.find(archetypeId);
    return itr == _archetypes.end() ? std::string("an archetype") : itr->second.name;
}

static std::string JoinNames(std::vector<std::string> const& names)
{
    std::string out;
    for (std::string const& n : names)
        out += (out.empty() ? "" : ", ") + n;
    return out;
}

bool ClasslessMgr::ApplyArchetype(Player* player, uint32 archetypeId, std::string* err)
{
    CharState& st = GetState(player);
    if (st.mode != Mode::Classless)
    {
        if (err) *err = "Archetypes are build templates for the Classless path.";
        return false;
    }

    if (!archetypeId)
    {
        if (!st.archetype)
        {
            if (err) *err = "You are not following an archetype.";
            return false;
        }
        std::string name = ArchetypeName(st.archetype);
        st.archetype = 0;
        SaveState(player);
        Msg(player, Acore::StringFormat("You no longer follow |cffffff00{}|r. Everything you own stays; from here you buy your own abilities and talents.", name));
        return true;
    }

    auto itr = _archetypes.find(archetypeId);
    if (itr == _archetypes.end())
    {
        if (err) *err = "Unknown archetype.";
        return false;
    }
    Archetype const& arch = itr->second;

    // An archetype replaces the build. Abilities come off with a full refund,
    // exactly as unlearning them one by one would. Talents can only be reset
    // by a respec, so a Hero who owns talents pays the respec fee; that respec
    // also clears and refunds every ability.
    if (!st.talents.empty())
    {
        std::string why;
        if (!Respec(player, &why))
        {
            if (err) *err = "Following a new archetype resets your talents, which is a respec. " + why;
            return false;
        }
    }
    else
    {
        std::vector<std::pair<uint32, GrantSource>> owned;
        for (auto const& [firstSpell, o] : st.abilities)
            owned.emplace_back(firstSpell, o.source);
        for (auto const& [firstSpell, source] : owned)
            if (AbilityEntry const* e = GetAbility(firstSpell))
            {
                RemoveAbilityInternal(player, *e);
                // Refund only what was BOUGHT. An ability that came with a
                // talent or free with another ability cost no essence, so
                // paying it back here minted it: buy Bear Form, take Maul and
                // Demoralizing Roar for free, then switch archetype and be
                // refunded for all three.
                if (source == GrantSource::Picked)
                    st.abilityEssence += AbilityCost(*e);
            }
    }

    st.archetype = archetypeId;
    SaveState(player);

    FollowResult got = FollowArchetype(player);
    std::string line = Acore::StringFormat("You now follow |cffffff00{}|r. Bought now: {} abilities, {} talent ranks.",
        arch.name, got.abilities, got.talentRanks);
    auto queue = ArchetypeQueue(player);
    if (!queue.empty())
    {
        auto const& [firstSpell, unlock] = queue.front();
        if (unlock > player->GetLevel())
            line += Acore::StringFormat(" Next: {} at level {}.", SpellName(firstSpell), uint32(unlock));
        else
            line += Acore::StringFormat(" Next: {}, as soon as you have the Ability Essence.", SpellName(firstSpell));
    }
    Msg(player, line + Acore::StringFormat(" AE left: |cff00ff00{}|r, TE left: |cff00ff00{}|r.",
        st.abilityEssence, st.talentEssence));
    return true;
}

uint32 ClasslessMgr::LevelsEarned(uint8 level, uint8 startLevel)
{
    return level >= startLevel ? uint32(level - startLevel + 1) : 0;
}

// The build's abilities are bought strictly in build order: the next one is
// taken as soon as it is unlocked and affordable, and nothing after it is
// touched before it. The cursor is the entry after the LAST owned one, so an
// ability the player unlearned on purpose further back is left alone.
size_t ClasslessMgr::ArchetypeCursor(CharState const& st, Archetype const& arch) const
{
    size_t cursor = 0;
    for (size_t i = 0; i < arch.abilities.size(); ++i)
        if (st.abilities.count(arch.abilities[i]))
            cursor = i + 1;
    return cursor;
}

ClasslessMgr::FollowResult ClasslessMgr::FollowArchetype(Player* player)
{
    FollowResult out;
    CharState& st = GetState(player);
    if (st.mode != Mode::Classless || !st.archetype)
        return out;
    auto itr = _archetypes.find(st.archetype);
    if (itr == _archetypes.end())
        return out;
    Archetype const& arch = itr->second;

    uint8 level = player->GetLevel();
    for (size_t i = ArchetypeCursor(st, arch); i < arch.abilities.size(); ++i)
    {
        uint32 firstSpell = arch.abilities[i];
        if (st.abilities.count(firstSpell))
            continue;
        AbilityEntry const* e = GetAbility(firstSpell);
        if (!e || !e->enabled)
            continue;
        uint8 unlock = e->rankLevels.empty() ? 1 : e->rankLevels[0];
        if (cfg.respectLevelReqs && unlock > level)
            break;                                  // waits for the level
        if (!BuyAbility(player, firstSpell, nullptr))
        {
            out.stalled.push_back(SpellName(firstSpell));
            break;                                  // waits for essence
        }
        ++out.abilities;
        out.learned.push_back(SpellName(firstSpell));
    }

    // Talents strictly in plan order. The plan is written tier by tier, so
    // stopping at the first rank that cannot be bought yet keeps the tree
    // rules honest, and the next level-up carries on from that point.
    for (auto const& [talentId, rank] : arch.talents)
    {
        uint8 owned = 0;
        if (auto o = st.talents.find(talentId); o != st.talents.end())
            owned = o->second;
        bool blocked = false;
        while (owned < rank)
        {
            if (!BuyTalentRank(player, talentId, nullptr))
            {
                blocked = true;
                break;
            }
            ++owned;
            ++out.talentRanks;
        }
        if (blocked)
            break;
    }
    return out;
}

std::vector<std::pair<uint32, uint8>> ClasslessMgr::ArchetypeQueue(Player* player)
{
    std::vector<std::pair<uint32, uint8>> out;
    CharState& st = GetState(player);
    auto itr = _archetypes.find(st.archetype);
    if (!st.archetype || itr == _archetypes.end())
        return out;
    Archetype const& arch = itr->second;
    for (size_t i = ArchetypeCursor(st, arch); i < arch.abilities.size(); ++i)
    {
        uint32 firstSpell = arch.abilities[i];
        if (st.abilities.count(firstSpell))
            continue;
        if (AbilityEntry const* e = GetAbility(firstSpell))
            out.emplace_back(firstSpell, e->rankLevels.empty() ? uint8(1) : e->rankLevels[0]);
    }
    return out;
}

bool ClasslessMgr::Rebirth(Player* player, Mode target, std::string* err)
{
    CharState& st = GetState(player);
    if (!cfg.rebirthEnable)
    {
        if (err) *err = "Rebirth is disabled on this realm.";
        return false;
    }
    if (target != Mode::Classless && target != Mode::Wildcard)
    {
        if (err) *err = "Choose a valid path: classless or wildcard.";
        return false;
    }

    int32 costCopper = int32(cfg.rebirthCostGold) * GOLD;
    if (!player->HasEnoughMoney(costCopper))
    {
        if (err) *err = Acore::StringFormat("Rebirth costs {} gold.", cfg.rebirthCostGold);
        return false;
    }
    player->ModifyMoney(-costCopper);

    uint32 guid = player->GetGUID().GetCounter();

    // wipe everything
    std::vector<uint32> ownedAbilities;
    for (auto const& [firstSpell, owned] : st.abilities)
        ownedAbilities.push_back(firstSpell);
    for (uint32 firstSpell : ownedAbilities)
        if (AbilityEntry const* e = GetAbility(firstSpell))
            RemoveAbilityInternal(player, *e);

    std::vector<uint32> ownedTalents;
    for (auto const& [talentId, rank] : st.talents)
        ownedTalents.push_back(talentId);
    for (uint32 talentId : ownedTalents)
        if (TalentPoolEntry const* t = GetTalent(talentId))
            RemoveTalentInternal(player, *t);

    st.bans.clear();
    st.pity = 0;
    st.archetype = 0;
    CharacterDatabase.Execute("DELETE FROM cw_char_bans WHERE guid = {}", guid);

    st.mode = target;
    uint8 level = player->GetLevel();
    st.lastProcessedLevel = level;

    if (target == Mode::Classless)
    {
        st.abilityEssence = cfg.startingAbilityEssence + LevelsEarned(level, cfg.essenceStartLevel) * cfg.abilityEssencePerLevel;
        st.talentEssence = LevelsEarned(level, cfg.talentEssenceStartLevel) * cfg.talentEssencePerLevel;
        SaveState(player);
        Msg(player, Acore::StringFormat("|cffff8800Rebirth complete.|r You walk the Classless path anew. "
            "AE: |cff00ff00{}|r, TE: |cff00ff00{}|r.", st.abilityEssence, st.talentEssence));
    }
    else
    {
        st.abilityEssence = 0;
        st.talentEssence = 0;
        SaveState(player);
        Msg(player, "|cffff8800Rebirth complete.|r The Wildcard takes your fate. Rolling your Hero...");

        GrantGuard noReveal(_revealSuppress); // bulk regrant: no popup spam
        for (uint32 i = 0; i < cfg.wcStartingAbilities; ++i)
            RollAbility(player);

        // replay the roll schedule (and its earned rerolls) for every level gained
        for (uint8 lvl = cfg.wcRollStartLevel; lvl <= level; ++lvl)
        {
            uint32 offset = lvl - cfg.wcRollStartLevel;
            if ((offset + cfg.wcTalentRollOffset) % cfg.wcTalentEveryLevels == 0)
                RollTalent(player);
            if (offset % cfg.wcAbilityEveryLevels == 0)
                RollAbility(player);
            // Rerolls are earned by LEVELLING, not by the individual roll, so
            // the charge is the same whichever kind of roll the level carried.
            st.rerolls += cfg.wcRerollsPerLevel;
        }
        SaveState(player);
    }

    UpdateAbilityRanks(player);
    // Everything is gone, so every class line is provably empty: clear
    // them now rather than leave stale empty tabs until the next login.
    SyncSpellbookTabs(player, true);
    return true;
}

// Price in COPPER so the cost reads as silver in the early game and only grows
// into gold near the level cap. which 1 (talent-only scroll) is half.
uint32 ClasslessMgr::ScrollBuyCost(uint8 level) const
{
    return cfg.wcScrollBuyBaseCopper + cfg.wcScrollBuyPerLevelCopper * uint32(level);
}

// "1g 20s 5c", trimming empty leading units.
static std::string CopperToText(uint32 copper)
{
    uint32 g = copper / GOLD;
    uint32 s = (copper % GOLD) / SILVER;
    uint32 c = copper % SILVER;
    std::string out;
    if (g) out += Acore::StringFormat("{}g", g);
    if (s) out += Acore::StringFormat("{}{}s", out.empty() ? "" : " ", s);
    if (c || out.empty()) out += Acore::StringFormat("{}{}c", out.empty() ? "" : " ", c);
    return out;
}

bool ClasslessMgr::BuyScroll(Player* player, std::string* err)
{
    if (!cfg.wcScrollBuyEnable)
    {
        if (err) *err = "Buying scrolls is disabled on this realm.";
        return false;
    }
    // Below the free-reroll level every reroll is free, so scrolls are pointless
    // there -- don't let players waste coin on them yet.
    if (player->GetLevel() < cfg.wcFreeRerollLevel)
    {
        if (err) *err = Acore::StringFormat("Rerolls are free below level {} -- you don't need scrolls yet.", cfg.wcFreeRerollLevel);
        return false;
    }

    // one scroll, good for abilities AND talents alike
    uint32 costCopper = ScrollBuyCost(player->GetLevel());
    if (!player->HasEnoughMoney(int32(costCopper)))
    {
        if (err) *err = Acore::StringFormat("A Reroll Scroll costs {}.", CopperToText(costCopper));
        return false;
    }

    // Add the item first so a full bag fails before the player is charged.
    if (!player->AddItem(cfg.wcScrollItemId, 1))
    {
        if (err) *err = "Your bags are full.";
        return false;
    }
    player->ModifyMoney(-int32(costCopper));

    Msg(player, Acore::StringFormat("Purchased a |cff0070ddReroll Scroll|r for |cffffd100{}|r.",
        CopperToText(costCopper)));
    return true;
}

AbilityEntry const* ClasslessMgr::GetAbility(uint32 firstSpellId) const
{
    auto itr = _abilities.find(firstSpellId);
    return itr != _abilities.end() ? &itr->second : nullptr;
}

TalentPoolEntry const* ClasslessMgr::GetTalent(uint32 talentId) const
{
    auto itr = _talents.find(talentId);
    return itr != _talents.end() ? &itr->second : nullptr;
}

AbilityEntry const* ClasslessMgr::FindAbilityBySpell(uint32 spellId) const
{
    auto itr = _spellToFirst.find(spellId);
    return itr != _spellToFirst.end() ? GetAbility(itr->second) : nullptr;
}

uint32 ClasslessMgr::AbilityCost(AbilityEntry const& e) const
{
    return e.cost ? e.cost : cfg.abilityCostByRarity[uint8(e.rarity)];
}

uint32 ClasslessMgr::RollWeight(Rarity rarity, uint32 overrideWeight) const
{
    return overrideWeight ? overrideWeight : cfg.wcRarityWeights[uint8(rarity)];
}

// Rank IS rarity for talents, by the rank NUMBER: rank 1 common, rank 2
// uncommon, rank 3 rare, rank 4 epic, rank 5 legendary. (Mapping it to the
// talent's own rank span instead would call rank 2 of a two-rank talent
// "legendary", which is neither what the rules say nor rollable in practice.)
// A talent that is already rare in its own right never reads as less than that,
// and single-rank talents just keep their own tier.
Rarity ClasslessMgr::RankRarity(TalentPoolEntry const& t, uint8 rank) const
{
    if (t.maxRank <= 1 || !rank)
        return t.rarity;

    uint8 byRank = std::min<uint8>(uint8(rank - 1), 4);
    return Rarity(std::max<uint8>(byRank, uint8(t.rarity)));
}

// The longest wait on any rank of a line. Some spells carry it as their own
// cooldown and some as their category's -- Ice Block uses RecoveryTime, Divine
// Shield the category it shares with the other bubbles -- so both are read and
// the larger wins.
uint32 ClasslessMgr::LineCooldown(AbilityEntry const& e) const
{
    uint32 worst = 0;
    for (uint32 sp : e.ranks)
        if (SpellInfo const* info = sSpellMgr->GetSpellInfo(sp))
            worst = std::max({ worst, info->RecoveryTime, info->CategoryRecoveryTime });
    return worst;
}

// How much of a prize is this ability? Rarity drives the roll weight, the
// essence price and the colour, so it has to mean "how good is this", and the
// level an ability is learned at does not say that. Rating by level alone
// called Bloodlust legendary for being level 70, Backstab common and Pain
// Suppression common as well because its SpellLevel is 0.
//
// Three signals, strongest wins:
//
//   cooldown    the game's own statement of size. A twenty-minute Lay on Hands
//               and a no-cooldown Fireball are not the same kind of thing.
//   talent row  a spell taught from row R costs 5R points to reach, so the row
//               IS the tier: forty points in is a capstone by construction.
//   level       a floor only, capped at rare. It is when you MAY learn
//               something, not how strong it is, so it can lift a late
//               no-cooldown spell off the bottom but never make it epic.
Rarity ClasslessMgr::RarityFromPower(uint32 cooldownMs, uint32 talentRow, uint8 level) const
{
    uint8 tier = 0;
    for (uint8 i = 0; i < 4; ++i)
        if (cfg.rarityCooldownMs[i] && cooldownMs >= cfg.rarityCooldownMs[i])
            tier = std::max<uint8>(tier, uint8(i + 1));
    for (uint8 i = 0; i < 4; ++i)
        if (cfg.rarityTalentRow[i] && talentRow >= cfg.rarityTalentRow[i])
            tier = std::max<uint8>(tier, uint8(i + 1));
    for (uint8 i = 0; i < 2; ++i)
        if (cfg.rarityLevel[i] && level >= cfg.rarityLevel[i])
            tier = std::max<uint8>(tier, uint8(i + 1));
    return Rarity(std::min<uint8>(tier, uint8(Rarity::Legendary)));
}

// Pick which rank a roll lands on, weighted by that rank's rarity -- so rank 5
// shows up as rarely as any other legendary. Returns 0 when the talent is
// already maxed.
uint8 ClasslessMgr::RollTalentRank(TalentPoolEntry const& t, uint8 fromRank) const
{
    if (fromRank >= t.maxRank)
        return 0;

    // Weighted by RANK on its own ladder, not by the rank's rarity. A rank is
    // a whole talent point where a rarity is only which entry came up, so the
    // two are tuned separately.
    auto rankWeight = [&](uint8 r) -> uint32
    {
        return cfg.wcTalentRankWeights[std::min<uint8>(uint8(r - 1), 4)];
    };

    uint32 total = 0;
    for (uint8 r = fromRank + 1; r <= t.maxRank; ++r)
        total += rankWeight(r);

    if (!total)
        return fromRank + 1; // every weight configured to zero: lowest rank

    uint32 pick = urand(0, total - 1);
    for (uint8 r = fromRank + 1; r <= t.maxRank; ++r)
    {
        uint32 w = rankWeight(r);
        if (pick < w)
            return r;
        pick -= w;
    }
    return fromRank + 1;
}

// -------------------------------------------------------------------------
// Per-character state / persistence
// -------------------------------------------------------------------------

CharState& ClasslessMgr::GetState(Player* player)
{
    CharState& st = _states[player->GetGUID().GetCounter()];
    if (!st.loaded)
        LoadCharacter(player, st);
    return st;
}

void ClasslessMgr::UnloadState(ObjectGuid guid)
{
    _states.erase(guid.GetCounter());
}

void ClasslessMgr::LoadCharacter(Player* player, CharState& st)
{
    uint32 guid = player->GetGUID().GetCounter();

    // bot/system account exemption (e.g. mod-playerbots random-bot accounts):
    // exempt characters play with vanilla class rules
    if (!cfg.exemptAccountPrefixes.empty())
    {
        if (QueryResult result = LoginDatabase.Query(
            "SELECT username FROM account WHERE id = {}", player->GetSession()->GetAccountId()))
        {
            std::string name = (*result)[0].Get<std::string>();
            std::transform(name.begin(), name.end(), name.begin(), ::tolower);
            for (std::string const& prefix : cfg.exemptAccountPrefixes)
            {
                std::string p = prefix;
                std::transform(p.begin(), p.end(), p.begin(), ::tolower);
                if (name.rfind(p, 0) == 0)
                {
                    st.exempt = true;
                    break;
                }
            }
        }
    }

    // Fixed for the session on purpose -- see CharState::runes.
    st.runes = cfg.includeDeathKnight && !st.exempt;

    if (QueryResult result = CharacterDatabase.Query(
        "SELECT mode, ability_essence, talent_essence, pity, rerolls, last_level, "
        "stat_str, stat_agi, stat_sta, stat_int, stat_spi, display_power, archetype FROM cw_char_state WHERE guid = {}", guid))
    {
        Field* f = result->Fetch();
        st.mode = Mode(f[0].Get<uint8>());
        st.abilityEssence = f[1].Get<uint32>();
        st.talentEssence = f[2].Get<uint32>();
        st.pity = f[3].Get<uint32>();
        st.rerolls = f[4].Get<uint32>();
        st.lastProcessedLevel = f[5].Get<uint8>();
        for (uint8 i = 0; i < 5; ++i)
            st.statAlloc[i] = f[6 + i].Get<uint32>();
        st.displayPower = f[11].Get<uint8>();
        st.archetype = f[12].Get<uint32>();
    }

    if (QueryResult result = CharacterDatabase.Query(
        "SELECT first_spell, source, locked FROM cw_char_abilities WHERE guid = {}", guid))
    {
        do
        {
            Field* f = result->Fetch();
            OwnedAbility owned;
            owned.source = GrantSource(f[1].Get<uint8>());
            owned.locked = f[2].Get<bool>();
            st.abilities[f[0].Get<uint32>()] = owned;
        } while (result->NextRow());
    }

    if (QueryResult result = CharacterDatabase.Query(
        "SELECT talent_id, talent_rank FROM cw_char_talents WHERE guid = {}", guid))
    {
        do
        {
            Field* f = result->Fetch();
            st.talents[f[0].Get<uint32>()] = f[1].Get<uint8>();
        } while (result->NextRow());
    }

    if (QueryResult result = CharacterDatabase.Query(
        "SELECT is_talent, entry, rolls_left FROM cw_char_bans WHERE guid = {}", guid))
    {
        do
        {
            Field* f = result->Fetch();
            RollBan ban;
            ban.isTalent = f[0].Get<bool>();
            ban.entry = f[1].Get<uint32>();
            ban.rollsLeft = f[2].Get<int32>();
            st.bans.push_back(ban);
        } while (result->NextRow());
    }

    st.loaded = true;
}

void ClasslessMgr::SaveState(Player* player)
{
    CharState& st = GetState(player);
    CharacterDatabase.Execute(
        "REPLACE INTO cw_char_state (guid, mode, ability_essence, talent_essence, pity, rerolls, last_level, "
        "stat_str, stat_agi, stat_sta, stat_int, stat_spi, display_power, archetype) VALUES ({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {})",
        player->GetGUID().GetCounter(), uint32(st.mode), st.abilityEssence, st.talentEssence, st.pity,
        st.rerolls, st.lastProcessedLevel,
        st.statAlloc[0], st.statAlloc[1], st.statAlloc[2], st.statAlloc[3], st.statAlloc[4],
        uint32(st.displayPower), st.archetype);
}

bool ClasslessMgr::SetDisplayPower(Player* player, uint8 powerIdx, std::string* err)
{
    if (IsExempt(player))
        return false;
    if (powerIdx != POWER_MANA && powerIdx != POWER_RAGE && powerIdx != POWER_ENERGY && powerIdx != 255)
    {
        if (err) *err = "Pick mana, rage or energy.";
        return false;
    }

    CharState& st = GetState(player);
    st.displayPower = powerIdx;
    CharacterDatabase.Execute("UPDATE cw_char_state SET display_power = {} WHERE guid = {}",
        uint32(powerIdx), player->GetGUID().GetCounter());
    ApplyDisplayPower(player);
    return true;
}

void ClasslessMgr::ApplyDisplayPower(Player* player)
{
    CharState& st = GetState(player);
    if (st.exempt || st.displayPower == 255)
        return;
    if (player->getPowerType() != Powers(st.displayPower))
        player->setPowerType(Powers(st.displayPower));
}

void ClasslessMgr::SaveBans(ObjectGuid guid, CharState const& st)
{
    uint32 low = guid.GetCounter();
    CharacterDatabase.Execute("DELETE FROM cw_char_bans WHERE guid = {}", low);
    for (RollBan const& ban : st.bans)
        CharacterDatabase.Execute(
            "INSERT INTO cw_char_bans (guid, is_talent, entry, rolls_left) VALUES ({}, {}, {}, {})",
            low, ban.isTalent ? 1 : 0, ban.entry, ban.rollsLeft);
}

// -------------------------------------------------------------------------
// Lifecycle
// -------------------------------------------------------------------------

// Riding comes with being a Hero.
//
// It is not class power and it is not in the classless library, so it never
// rolls and cannot be bought with essence -- but a Hero who ROLLS a class mount
// still needs the skill to sit on it, and paying a trainer for something the
// module hands out to everyone else is just a tax. So it is given, on the
// schedule the trainers use.
//
// That schedule matters. The riding spells carry no level of their own (every
// one of them reads SpellLevel 0 in Spell.dbc); the gate lives entirely in
// npc_trainer and in each mount item's own RequiredLevel. Handing all four out
// at level 1 would therefore lean completely on mount items being level-gated,
// which is a realm-by-realm question. Following the trainer levels cannot
// outrun anything, because it IS what the trainers do. A realm that wants them
// all at once only has to set every level in Riding.Grants to 1.
uint32 ClasslessMgr::GrantRidingSkill(Player* player)
{
    if (!cfg.ridingEnable || cfg.ridingGrants.empty())
        return 0;
    if (GetState(player).exempt)
        return 0;   // bots ride by the normal rules

    GrantGuard guard(_applyingGrant);
    uint32 const level = player->GetLevel();
    uint32 taught = 0;
    for (auto const& [spellId, atLevel] : cfg.ridingGrants)
    {
        if (level < atLevel || player->HasSpell(spellId))
            continue;
        if (!sSpellMgr->GetSpellInfo(spellId))
        {
            LOG_WARN("module.classless", "Riding.Grants lists spell {}, which does not exist", spellId);
            continue;
        }
        player->learnSpell(spellId);
        ++taught;
        Msg(player, Acore::StringFormat("You have learned {}. Riding is trained for every Hero.",
            SpellName(spellId)));
    }
    return taught;
}

void ClasslessMgr::TeachProficiencies(Player* player)
{
    if (!cfg.teachProficiencies)
        return;

    GrantGuard guard(_applyingGrant);

    for (uint32 spellId : cfg.proficiencySpells)
        if (sSpellMgr->GetSpellInfo(spellId) && !player->HasSpell(spellId))
            player->learnSpell(spellId);

    // A ranged proficiency without its use-ability is a dead skill: 5019 only
    // shoots WANDS -- bows/guns/crossbows fire with 3018 (Shoot) and thrown
    // weapons with 2764 (Throw). Teach those alongside their proficiencies
    // even when an older conf list predates them.
    auto listed = [&](uint32 id)
    {
        return std::find(cfg.proficiencySpells.begin(), cfg.proficiencySpells.end(), id) != cfg.proficiencySpells.end();
    };
    std::vector<uint32> useAbilities;
    if (listed(264) || listed(266) || listed(5011))
        useAbilities.push_back(3018);   // Shoot (bow / gun / crossbow)
    if (listed(2567))
        useAbilities.push_back(2764);   // Throw
    for (uint32 spellId : useAbilities)
        if (sSpellMgr->GetSpellInfo(spellId) && !player->HasSpell(spellId))
            player->learnSpell(spellId);

    player->UpdateSkillsToMaxSkillsForLevel();
}

// Force every Hero onto the single configured chassis class.
//
// This is what makes the system genuinely classless. While characters keep
// whatever class the creation screen sent, the core's own per-class math
// differs between them — base stats, base health and mana, which stat feeds
// attack power, the crit and dodge conversion ratios — and picking a class
// quietly becomes a build decision again. One chassis for everyone makes that
// math identical by construction instead of by correction, so the class chosen
// at creation is nothing but the model and the name (which reads "Hero"
// anyway once the client patch is installed).
//
// Called at creation and at every login, so characters made before the module
// was installed convert on their next login.
bool ClasslessMgr::EnforceChassis(Player* player)
{
    if (!cfg.enabled || !cfg.chassisEnable || !player)
        return false;
    if (IsExempt(player))          // bots/system accounts keep vanilla classes
        return false;

    uint8 const want = cfg.chassisClass;
    if (!want || player->getClass() == want)
        return false;

    ChrClassesEntry const* entry = sChrClassesStore.LookupEntry(want);
    if (!entry)
    {
        LOG_ERROR("module.classless",
                  "mod-classless-wildcard: ClasslessWildcard.Chassis.Class = {} is not a "
                  "valid class id — leaving characters on their original class", want);
        return false;
    }

    uint8 const from = player->getClass();

    // the core's own way of changing a unit's class
    player->SetByteValue(UNIT_FIELD_BYTES_0, 1, want);
    player->setPowerType(Powers(entry->powerType));

    // rebuild everything that is derived from the class
    player->InitStatsForLevel(true);
    player->InitTaxiNodesForLevel();
    player->InitTalentForLevel();
    player->UpdateAllStats();
    player->SetFullHealth();
    if (player->getPowerType() == POWER_MANA)
        player->SetPower(POWER_MANA, player->GetMaxPower(POWER_MANA));

    // armor/weapon skills came from the old class; the chassis re-teaches the
    // full classless set anyway
    TeachProficiencies(player);

    // persist immediately: characters.class is written from this field, and a
    // crash before the next periodic save would leave the client and the DB
    // disagreeing about what the character is
    player->SaveToDB(false, false);

    LOG_INFO("module.classless",
             "mod-classless-wildcard: {} converted from class {} to chassis class {} ({})",
             player->GetName(), from, want, entry->name[0] ? entry->name[0] : "?");
    return true;
}

bool ClasslessMgr::ApplyStarterGear(Player* player)
{
    // Runs at character creation (so the character-select preview shows the
    // neutral outfit instead of the shell class's plate) and again in the
    // first-login kit. Exempt characters (bots/system) keep vanilla gear.
    if (!cfg.enabled || !cfg.starterKitEnable || IsExempt(player))
        return false;

    bool changed = false;
    if (cfg.starterKitStripEquipped)
        for (uint8 slot = EQUIPMENT_SLOT_START; slot < EQUIPMENT_SLOT_END; ++slot)
            if (player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))
            {
                player->DestroyItem(INVENTORY_SLOT_BAG_0, slot, true);
                changed = true;
            }

    // empty equip slots mean StoreNewItemInBestSlots equips the outfit (shirt/
    // pants/boots) rather than dropping it into the bags
    for (auto const& [itemId, count] : cfg.starterKitEquip)
        changed = player->StoreNewItemInBestSlots(itemId, count) || changed;
    return changed;
}

void ClasslessMgr::HandleFirstLogin(Player* player)
{
    if (!cfg.enabled)
        return;

    CharState& st = GetState(player);
    if (st.exempt)
        return;
    st.mode = cfg.allowModeChoice ? Mode::Unchosen : Mode(cfg.defaultMode);
    st.abilityEssence = cfg.startingAbilityEssence;
    st.talentEssence = 0;
    st.lastProcessedLevel = player->GetLevel();

    // clean slate: a Hero starts with NO class abilities — everything comes
    // through essences (classless) or rolls (wildcard)
    if (cfg.stripStartingSpells)
        StripUnearnedSpells(player);

    // With the chassis spells gone there is nothing left under the chassis
    // class's own tab, so take the tab away too. This is the one moment it
    // costs nothing, and the only time the module removes a skill line.
    SyncSpellbookTabs(player, true);

    // neutral Hero starter kit
    if (cfg.starterKitEnable)
    {
        // Strip the shell class's default BACKPACK items (the equipped gear is
        // handled by ApplyStarterGear, already run at character creation). Both
        // are stripped so the Hero begins from a clean slate rather than
        // duplicating the neutral kit on top of the shell class's starters.
        if (cfg.starterKitStripEquipped)
            for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
                if (player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))
                    player->DestroyItem(INVENTORY_SLOT_BAG_0, slot, true);

        // (re)apply the visible outfit -- idempotent with the character-create pass
        ApplyStarterGear(player);

        // an extra bag, equipped in a bag slot, so the Hero has room for the kit
        // (StoreNewItemInBestSlots equips a bag into a free bag slot)
        if (cfg.starterKitBag)
            player->StoreNewItemInBestSlots(cfg.starterKitBag, 1);
        // weapons and consumables go into the bags, unequipped -- the Hero picks
        // up the neutral weapons from there when they want them
        for (auto const& [itemId, count] : cfg.starterKitItems)
        {
            uint32 give = count;
            // Safety net: a non-stackable item with a big count (a stale conf
            // with "throwing axe x200", say) would fill every bag slot with
            // copies. Cap non-stackables at 2 (dual-wield pairs are legit).
            if (ItemTemplate const* proto = sObjectMgr->GetItemTemplate(itemId))
                if (proto->GetMaxStackSize() <= 1 && give > 2)
                {
                    LOG_WARN("module.classless", "StarterKit.Items: item {} does not stack; count {} clamped to 1", itemId, count);
                    give = 1;
                }
            player->AddItem(itemId, give);
        }

        // The backpack strip above also destroys the creation Hearthstone (and
        // non-native shell-class race combos never get one from the DBC outfit
        // at all). Every Hero must keep one -- put it back.
        constexpr uint32 HEARTHSTONE = 6948;
        if (!player->HasItemCount(HEARTHSTONE, 1))
            player->AddItem(HEARTHSTONE, 1);
    }

    TeachProficiencies(player);

    if (st.mode == Mode::Wildcard)
    {
        GrantGuard noReveal(_revealSuppress); // starting hand shows these
        for (uint32 i = 0; i < cfg.wcStartingAbilities; ++i)
            RollAbility(player);
    }

    SaveState(player);

    if (cfg.announce)
    {
        if (st.mode == Mode::Unchosen)
        {
            Msg(player, "Welcome, Hero! You have no class, and there was none to pick. Every Hero shares the "
                        "same |cffffff00chassis|r, and it grants nothing (your race keeps its own racial traits). You "
                        "carry mana, rage and energy at once, every stat is worth having, and every spell, talent, "
                        "weapon and armor type in the game is open to you.");
            Msg(player, "Speak to the |cffffff00Hero Advancement|r NPC (or use |cffffff00.classless mode|r / the "
                        "|cffffff00/cw|r addon) to choose your path: Classless free-pick or Wildcard random rolls.");
        }
        else
            AnnounceState(player);
    }
}

// The choice window has closed with nothing chosen, so the realm default takes
// over. This has to happen on LEVEL-UP as well as at login: SetMode refuses
// once the Hero is at the deadline level, so a player who reached it during a
// session was left with no mode at all -- no essence income, no rolls, and the
// NPC answering "your path is locked in" to both buttons -- until they relogged.
bool ClasslessMgr::ApplyDefaultMode(Player* player)
{
    CharState& st = GetState(player);
    if (st.exempt || st.mode != Mode::Unchosen || player->GetLevel() < cfg.modeChoiceDeadline)
        return false;

    st.mode = Mode(cfg.defaultMode);
    if (st.mode == Mode::Wildcard)
    {
        GrantGuard noReveal(_revealSuppress); // the starting hand shows these
        for (uint32 i = 0; i < cfg.wcStartingAbilities; ++i)
            RollAbility(player);
    }
    if (cfg.announce)
        Msg(player, st.mode == Mode::Wildcard
            ? "You did not choose a path in time, so the Wildcard chose for you. Your starting abilities have been dealt."
            : "You did not choose a path in time, so you walk the Classless path. Spend your Ability Essence at the Hero Advancement NPC.");
    return true;
}

void ClasslessMgr::HandleLogin(Player* player)
{
    if (!cfg.enabled)
        return;

    CharState& st = GetState(player);
    if (st.exempt)
        return;

    // characters created before the module was installed
    if (st.lastProcessedLevel == 0)
    {
        st.abilityEssence = cfg.startingAbilityEssence;
        st.lastProcessedLevel = 1;
    }

    ApplyDefaultMode(player);

    TeachProficiencies(player);
    GrantRidingSkill(player);
    ApplyStatMods(player);
    // characters who passed the line before this rule existed, or while
    // logged out
    ClearStaleLocks(player);

    // A talent that has since left the list (ReplaceAbilityTalents) turns
    // into the ability it stood for: the line is granted at no cost, the
    // Talent Essence comes back on the Classless path, and the talent row goes.
    {
        std::vector<uint32> gone;
        for (auto const& [talentId, rank] : st.talents)
            if (_replacedTalents.count(talentId))
                gone.push_back(talentId);
        for (uint32 talentId : gone)
        {
            TalentPoolEntry const& t = _replacedTalents.at(talentId);
            GrantSource source = st.mode == Mode::Wildcard ? GrantSource::Rolled : GrantSource::Picked;
            for (uint32 first : t.abilityLines)
                if (!st.abilities.count(first))
                    if (AbilityEntry const* e = GetAbility(first))
                        GrantAbilityInternal(player, *e, source, true, false);
            // the talent's own spell, unless it is a rank of a line now owned
            for (uint8 r = 0; r < t.maxRank; ++r)
                if (t.rankSpells[r] && player->HasSpell(t.rankSpells[r]) && !FindAbilityBySpell(t.rankSpells[r]))
                    player->removeSpell(t.rankSpells[r], SPEC_MASK_ALL, false);
            if (st.mode == Mode::Classless)
                st.talentEssence += cfg.talentCostPerRank;
            st.talents.erase(talentId);
            CharacterDatabase.Execute("DELETE FROM cw_char_talents WHERE guid = {} AND talent_id = {}",
                                      player->GetGUID().GetCounter(), talentId);
            if (!t.abilityLines.empty())
                Msg(player, Acore::StringFormat("{} is an ability now. It is in your build{}.",
                    SpellName(t.abilityLines[0]),
                    st.mode == Mode::Classless ? ", and its Talent Essence is back" : ""));
        }
    }

    // With ReplaceAbilityTalents off, an ability talent owned from before
    // talents handed over their line gets the line now, so the spell starts
    // ranking up like everyone else's.
    {
        std::vector<std::pair<TalentPoolEntry const*, uint32>> due;
        for (auto const& [talentId, rank] : st.talents)
            if (TalentPoolEntry const* t = GetTalent(talentId))
                for (uint32 first : t->abilityLines)
                    if (!st.abilities.count(first))
                        due.emplace_back(t, first);
        for (auto const& [t, first] : due)
            if (AbilityEntry const* e = GetAbility(first))
                if (!st.abilities.count(first))
                    GrantAbilityInternal(player, *e, GrantSource::Talent, true, false);
    }

    // Sweep again on every login, not just the first. The chassis class's own
    // spells come back on their own -- a Hero was showing Holy Light in the
    // Paladin tab of a spellbook they never trained -- and a first-login-only
    // strip leaves anything that arrives later in place permanently.
    // Tabs first, then the sweep. LoadFromDB has already re-added the chassis
    // class's skill lines on the way in, so this is where they come back off --
    // and adding a line hands out its learned-on-skill spells, which the sweep
    // then takes back.
    SyncSpellbookTabs(player, true);

    if (cfg.stripStartingSpells)
        if (uint32 removed = StripUnearnedSpells(player))
            LOG_DEBUG("module.classless",
                      "mod-classless-wildcard: removed {} unearned spell(s) from {} at login",
                      removed, player->GetName());

    // Hand over any stance or form the build needs and does not have, then
    // take back the free extras nothing needs any more.
    SyncRequiredForms(player);
    PruneCompanions(player);
    DismissOrphanedSummons(player);

    // catch up levels gained while the module was off / before install
    if (st.lastProcessedLevel < player->GetLevel())
        HandleLevelUp(player, st.lastProcessedLevel);
    else
        UpdateAbilityRanks(player);

    SaveState(player);

    if (cfg.announce)
        AnnounceState(player);
}

void ClasslessMgr::HandleLevelUp(Player* player, uint8 oldLevel)
{
    if (!cfg.enabled)
        return;

    CharState& st = GetState(player);
    if (st.exempt)
        return;

    // Reaching the deadline level is itself the moment the default takes over.
    ApplyDefaultMode(player);

    uint8 newLevel = player->GetLevel();
    if (newLevel <= oldLevel && st.lastProcessedLevel >= newLevel)
        return;

    // Never pay for a level twice. A character that goes DOWN a level (a GM
    // command, a de-levelling script) used to have lastProcessedLevel dragged
    // down with it, so levelling back up handed out the same essence, rolls and
    // reroll charges all over again. Start above the highest level already
    // settled, whichever of the two that is.
    uint8 const from = std::max(oldLevel, st.lastProcessedLevel);
    for (uint8 lvl = from + 1; lvl <= newLevel; ++lvl)
    {
        if (st.mode == Mode::Classless && lvl >= cfg.essenceStartLevel)
            st.abilityEssence += cfg.abilityEssencePerLevel;
        if (st.mode == Mode::Classless && lvl >= cfg.talentEssenceStartLevel)
            st.talentEssence += cfg.talentEssencePerLevel;
        else if (st.mode == Mode::Wildcard && lvl >= cfg.wcRollStartLevel)
        {
            uint32 offset = lvl - cfg.wcRollStartLevel;
            if ((offset + cfg.wcTalentRollOffset) % cfg.wcTalentEveryLevels == 0)
                RollTalent(player);
            if (offset % cfg.wcAbilityEveryLevels == 0)
                RollAbility(player);
            // one grant per level gained, from the first scheduled roll onward
            st.rerolls += cfg.wcRerollsPerLevel;
        }

        // optional extra scroll faucet at level milestones (off by default)
        if (st.mode == Mode::Wildcard && cfg.wcFreeScrollEveryLevels
            && lvl % cfg.wcFreeScrollEveryLevels == 0 && cfg.wcFreeScrollCount)
        {
            if (player->AddItem(cfg.wcScrollItemId, cfg.wcFreeScrollCount))
                Msg(player, Acore::StringFormat("The Wildcard rewards your journey: |cff0070dd{} Scroll{} of Fortune|r!",
                    cfg.wcFreeScrollCount, cfg.wcFreeScrollCount > 1 ? "s" : ""));
        }
    }

    st.lastProcessedLevel = std::max(st.lastProcessedLevel, newLevel);
    UpdateAbilityRanks(player);
    GrantRidingSkill(player);

    if (uint32 freed = ClearStaleLocks(player))
        Msg(player, Acore::StringFormat(
            "Your starting hand is over, so {} padlock{} come off. From here you reroll one "
            "ability at a time, and only the one you choose.",
            freed, freed == 1 ? " comes" : "s"));

    if (st.mode == Mode::Classless && st.archetype)
    {
        FollowResult got = FollowArchetype(player);
        std::string name = ArchetypeName(st.archetype);
        if (!got.learned.empty())
            Msg(player, Acore::StringFormat("|cffffff00{}|r: learned {}.", name, JoinNames(got.learned)));
        if (got.talentRanks)
            Msg(player, Acore::StringFormat("|cffffff00{}|r: {} talent rank{} bought.", name,
                got.talentRanks, got.talentRanks == 1 ? "" : "s"));
        if (!got.stalled.empty())
            Msg(player, Acore::StringFormat("|cffffff00{}|r: {} is next and waits for Ability Essence.",
                name, JoinNames(got.stalled)));
    }
    SaveState(player);

    if (st.mode == Mode::Classless && newLevel >= cfg.essenceStartLevel && cfg.announce)
        Msg(player, Acore::StringFormat("You now have |cff00ff00{}|r Ability Essence and |cff00ff00{}|r Talent Essence.",
            st.abilityEssence, st.talentEssence));
}

bool ClasslessMgr::SetMode(Player* player, Mode mode, std::string* err)
{
    CharState& st = GetState(player);

    if (st.exempt)
    {
        if (err) *err = "This account is exempt from the classless system.";
        return false;
    }

    if (st.mode == mode)
    {
        if (err) *err = "That is already your mode.";
        return false;
    }

    if (st.mode != Mode::Unchosen || player->GetLevel() >= cfg.modeChoiceDeadline)
    {
        if (err) *err = Acore::StringFormat("Your path is locked in (mode must be chosen before level {}).", cfg.modeChoiceDeadline);
        return false;
    }

    st.mode = mode;

    if (mode == Mode::Wildcard)
    {
        GrantGuard noReveal(_revealSuppress); // the starting hand UI shows these
        for (uint32 i = 0; i < cfg.wcStartingAbilities; ++i)
            RollAbility(player);
        Msg(player, "The Wildcard has been drawn! You received random starting abilities. Reroll them freely at the "
                    "Hero Advancement NPC until level 10.");
    }
    else
        Msg(player, Acore::StringFormat("Classless path chosen. You have |cff00ff00{}|r Ability Essence to spend.", st.abilityEssence));

    SaveState(player);
    return true;
}

void ClasslessMgr::AnnounceState(Player* player)
{
    CharState& st = GetState(player);
    if (st.mode == Mode::Classless)
        Msg(player, Acore::StringFormat(
            "Classless Hero. Abilities: {}, talents: {}, AE: |cff00ff00{}|r, TE: |cff00ff00{}|r.",
            st.abilities.size(), st.talents.size(), st.abilityEssence, st.talentEssence));
    else if (st.mode == Mode::Wildcard)
        Msg(player, Acore::StringFormat(
            "Wildcard Hero. Abilities: {}, talents: {}. Rerolls: |cff00ff00{}|r (earned as you level, spend on either).",
            st.abilities.size(), st.talents.size(), st.rerolls));
}

// -------------------------------------------------------------------------
// Grant / remove internals
// -------------------------------------------------------------------------

void ClasslessMgr::GrantAbilityInternal(Player* player, AbilityEntry const& e, GrantSource source, bool persist,
                                        bool announce)
{
    GrantGuard guard(_applyingGrant);
    CharState& st = GetState(player);

    OwnedAbility owned;
    owned.source = source;
    st.abilities[e.firstSpellId] = owned;

    // learn rank 1 always, higher ranks as level allows
    uint8 level = player->GetLevel();
    for (size_t i = 0; i < e.ranks.size(); ++i)
        if (i == 0 || e.rankLevels[i] <= level)
            if (!player->HasSpell(e.ranks[i]))
                player->learnSpell(e.ranks[i]);

    if (persist)
        CharacterDatabase.Execute(
            "REPLACE INTO cw_char_abilities (guid, first_spell, source, locked) VALUES ({}, {}, {}, 0)",
            player->GetGUID().GetCounter(), e.firstSpellId, uint32(source));

    if (announce)
        Msg(player, Acore::StringFormat("You gained the ability {}{}|r ({}).",
            RarityColor(e.rarity), SpellName(e.firstSpellId), RarityName(e.rarity)));

    GrantFormKit(player, e);
    GrantRequiredForm(player, e);
    // a newly gained spell needs its tab straight away, not at next login
    SyncSpellbookTabs(player);
}

// Some abilities do nothing on their own: a Hero who draws Bear Form without
// Maul has shapeshifted into a creature that cannot attack, one who draws
// Defensive Stance without Taunt has a stance with no reason to use it, and one
// who draws Tame Beast without Call Pet has a pet they cannot summon. Where the
// class system hands these out together, so does this -- free, and the moment
// the first one lands.
//
// Nothing here is form-specific; cw_form_kits is a plain table of spell pairs
// and either side can be any spell.
void ClasslessMgr::GrantFormKit(Player* player, AbilityEntry const& form)
{
    if (!cfg.formKitsEnable || _formKits.empty() || _grantingKit)
        return;

    // Match on every rank, not just the first: Bear Form is 5487 and Dire Bear
    // Form 9634, and either one arriving should hand over the same kit.
    std::vector<uint32> kit;
    for (uint32 rankSpell : form.ranks)
    {
        auto itr = _formKits.find(rankSpell);
        if (itr == _formKits.end())
            continue;
        for (uint32 spellId : itr->second)
            if (std::find(kit.begin(), kit.end(), spellId) == kit.end())
                kit.push_back(spellId);
    }
    if (kit.empty())
        return;

    GrantGuard guard(_grantingKit);
    std::vector<std::string> gained;

    for (uint32 spellId : kit)
    {
        // Prefer granting it as a real owned ability so it shows up in My
        // Build, survives a relog and is excluded from future rolls like
        // anything else the Hero owns. A kit spell that is not in the library
        // (disabled by an override, say) is simply taught.
        if (AbilityEntry const* companion = FindAbilityBySpell(spellId))
        {
            // re-read the state each time: the grant below writes to it
            if (GetState(player).abilities.count(companion->firstSpellId))
                continue;
            GrantAbilityInternal(player, *companion, GrantSource::Companion, true, false);
            gained.push_back(SpellName(companion->firstSpellId));
        }
        else if (!player->HasSpell(spellId))
        {
            player->learnSpell(spellId);
            gained.push_back(SpellName(spellId));
        }
    }

    if (gained.empty())
        return;

    if (_revealSuppress)
        return;   // a whole hand is being dealt; the hand screen speaks for it

    std::string list = gained[0];
    for (size_t i = 1; i < gained.size(); ++i)
        list += (i + 1 == gained.size() ? " and " : ", ") + gained[i];
    Msg(player, Acore::StringFormat("{} comes with {}, yours to use straight away.",
        SpellName(form.firstSpellId), list));
}

// Is this free extra still earning its place?
//
// Only abilities the Hero EARNED count as a reason to keep one, never another
// companion. Otherwise a stance and the ability that came with it would vouch
// for each other and neither could ever leave.
bool ClasslessMgr::IsCompanionJustified(CharState const& st, AbilityEntry const& e) const
{
    // Which forms does this ability put the Hero into? A line can grant more
    // than one -- Bear Form is form 5 and its rank 2, Dire Bear Form, is form
    // 8 -- so collect them all rather than stopping at the first.
    uint64 grantsForms = 0;
    for (auto const& [form, formSpell] : _formSpells)
        if (std::find(e.ranks.begin(), e.ranks.end(), formSpell) != e.ranks.end())
            grantsForms |= uint64(1) << (form - 1);

    for (auto const& [ownedFirst, owned] : st.abilities)
    {
        if (owned.source == GrantSource::Companion || ownedFirst == e.firstSpellId)
            continue;
        AbilityEntry const* owner = GetAbility(ownedFirst);
        if (!owner)
            continue;

        // the form it grants is one something owned cannot be used outside of
        if (grantsForms)
            if (SpellInfo const* info = sSpellMgr->GetSpellInfo(owner->firstSpellId))
                if ((info->Stances & grantsForms)
                    && !info->HasAttribute(SPELL_ATTR2_ALLOW_WHILE_NOT_SHAPESHIFTED))
                    return true;

        // or it is part of the starter kit of an ability still owned
        for (uint32 rankSpell : owner->ranks)
        {
            auto itr = _formKits.find(rankSpell);
            if (itr == _formKits.end())
                continue;
            for (uint32 kitSpell : itr->second)
                if (std::find(e.ranks.begin(), e.ranks.end(), kitSpell) != e.ranks.end())
                    return true;
        }
    }
    return false;
}

uint32 ClasslessMgr::ClearStaleLocks(Player* player)
{
    if (player->GetLevel() < cfg.wcFreeRerollLevel)
        return 0;

    CharState& st = GetState(player);
    uint32 cleared = 0;
    for (auto& [firstSpell, owned] : st.abilities)
        if (owned.locked)
        {
            owned.locked = false;
            ++cleared;
        }

    if (cleared)
        CharacterDatabase.Execute("UPDATE cw_char_abilities SET locked = 0 WHERE guid = {}",
                                  player->GetGUID().GetCounter());
    return cleared;
}

uint32 ClasslessMgr::PruneCompanions(Player* player)
{
    CharState& st = GetState(player);

    std::vector<uint32> drop;
    for (auto const& [firstSpell, owned] : st.abilities)
        if (owned.source == GrantSource::Companion)
            if (AbilityEntry const* e = GetAbility(firstSpell))
                if (!IsCompanionJustified(st, *e))
                    drop.push_back(firstSpell);

    for (uint32 firstSpell : drop)
        if (AbilityEntry const* e = GetAbility(firstSpell))
        {
            RemoveAbilityInternal(player, *e);
            Msg(player, Acore::StringFormat("{} came free with an ability you no longer have, so it goes too.",
                SpellName(firstSpell)));
        }
    return uint32(drop.size());
}

// Repair a build whose stance the library could not offer, and any build made
// before that was fixed. GrantRequiredForm does nothing when the Hero can
// already use the ability, so this is safe to run at every login.
void ClasslessMgr::SyncRequiredForms(Player* player)
{
    if (!cfg.formKitsEnable)
        return;

    CharState& st = GetState(player);
    std::vector<uint32> earned;
    for (auto const& [firstSpell, owned] : st.abilities)
        if (owned.source != GrantSource::Companion)
            earned.push_back(firstSpell);

    for (uint32 firstSpell : earned)
        if (AbilityEntry const* e = GetAbility(firstSpell))
            GrantRequiredForm(player, *e);
}

// A pet is a creature standing in the world, not an aura, so losing Summon Imp
// left the imp out for good, following a Hero who could never call it back.
// Anything out that the Hero can no longer summon is sent home.
//
// That includes tamed beasts, which an earlier comment here claimed it did
// not. A beast DOES record the spell that produced it: Unit::InitTamedPet
// writes Tame Beast into UNIT_CREATED_BY_SPELL when it is tamed, and
// EffectSummonPet overwrites it with Call Pet once it has been put away and
// called back. Both of those leave with Tame Beast (Call Pet is its
// companion), so a rerolled Tame Beast already took the beast with it. Only a
// pet carrying a zero -- older data, a GM spawn -- was ever missed, and the
// fallback below covers that.
//
// PET_SAVE_NOT_IN_SLOT is what Dismiss Pet uses: the beast is put away, not
// destroyed, so rolling Tame Beast again calls the same one back.
void ClasslessMgr::DismissOrphanedSummons(Player* player)
{
    Pet* pet = player->GetPet();
    if (!pet)
        return;

    uint32 needed = pet->GetUInt32Value(UNIT_CREATED_BY_SPELL);
    if (!needed && pet->getPetType() == HUNTER_PET)
        needed = cfg.callPetSpell;   // nothing recorded: a beast still needs Call Pet
    if (!needed || player->HasSpell(needed))
        return;

    Msg(player, Acore::StringFormat("{} is dismissed: you no longer know {}.",
        pet->GetName(), SpellName(needed)));
    pet->Remove(PET_SAVE_NOT_IN_SLOT);
}

// A class tool is the one requirement a Hero can never meet. Stoneskin Totem
// asks for an Earth Totem, which is handed to shamans and to nobody else, so
// the spell arrives permanently unusable however it was earned. The tool is
// class identity rather than balance, so it comes off every spell in the
// library, in both columns the game reads: a named item (Totem) and a tool
// category (TotemCategory). Reagents stay, because those are vendor goods
// anyone can buy. The client patch clears the same two columns so the tooltip
// agrees with the server.
void ClasslessMgr::StripSpellTools()
{
    if (!cfg.ignoreSpellTools)
        return;

    uint32 cleared = 0;
    auto strip = [&cleared](uint32 spellId)
    {
        SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
        if (!info)
            return;
        if (!info->Totem[0] && !info->Totem[1] && !info->TotemCategory[0] && !info->TotemCategory[1])
            return;
        SpellInfo* editable = const_cast<SpellInfo*>(info);
        editable->Totem.fill(0);
        editable->TotemCategory.fill(0);
        ++cleared;
    };

    for (auto const& [firstSpell, e] : _abilities)
        for (uint32 rankSpell : e.ranks)
            strip(rankSpell);
    for (auto const& [talentId, t] : _talents)
        for (uint8 r = 0; r < t.maxRank; ++r)
            if (t.rankSpells[r])
                strip(t.rankSpells[r]);

    LOG_INFO("module.classless", "mod-classless-wildcard: tool requirement cleared from {} spells", cleared);
}

void ClasslessMgr::RemoveAbilityInternal(Player* player, AbilityEntry const& e, bool persist)
{
    CharState& st = GetState(player);
    st.abilities.erase(e.firstSpellId);

    for (uint32 rankSpell : e.ranks)
        if (player->HasSpell(rankSpell))
            player->removeSpell(rankSpell, SPEC_MASK_ALL, false);

    if (persist)
        CharacterDatabase.Execute(
            "DELETE FROM cw_char_abilities WHERE guid = {} AND first_spell = {}",
            player->GetGUID().GetCounter(), e.firstSpellId);

    DismissOrphanedSummons(player);
}

void ClasslessMgr::GrantTalentRankInternal(Player* player, TalentPoolEntry const& t, uint8 newRank, bool persist)
{
    GrantGuard guard(_applyingGrant);
    CharState& st = GetState(player);
    if (!newRank || newRank > t.maxRank)
        return;

    if (newRank > 1 && t.rankSpells[newRank - 2] && player->HasSpell(t.rankSpells[newRank - 2]))
        player->removeSpell(t.rankSpells[newRank - 2], SPEC_MASK_ALL, false);

    player->learnSpell(t.rankSpells[newRank - 1]);
    // a talent that teaches a spell needs its tab now, not at next login
    SyncSpellbookTabs(player);
    st.talents[t.talentId] = newRank;

    // an ability talent hands over its whole ability line, so the spell keeps
    // ranking up with level instead of stalling at the talent's rank 1
    for (uint32 first : t.abilityLines)
        if (!st.abilities.count(first))
            if (AbilityEntry const* e = GetAbility(first))
                GrantAbilityInternal(player, *e, GrantSource::Talent, persist, false);

    if (persist)
        CharacterDatabase.Execute(
            "REPLACE INTO cw_char_talents (guid, talent_id, talent_rank) VALUES ({}, {}, {})",
            player->GetGUID().GetCounter(), t.talentId, newRank);

    // the rank drives the rarity, so the chat line matches the reveal popup
    Rarity shown = RankRarity(t, newRank);
    Msg(player, Acore::StringFormat("Talent: {}{}|r rank {}/{} ({}).",
        RarityColor(shown), SpellName(t.rankSpells[newRank - 1]), newRank, uint32(t.maxRank), RarityName(shown)));
}

void ClasslessMgr::RemoveTalentInternal(Player* player, TalentPoolEntry const& t, bool persist)
{
    CharState& st = GetState(player);
    st.talents.erase(t.talentId);

    for (uint8 r = 0; r < t.maxRank; ++r)
    {
        uint32 rankSpell = t.rankSpells[r];
        if (!rankSpell || !player->HasSpell(rankSpell))
            continue;
        // a rank spell that is also rank 1 of a line the Hero bought or
        // rolled stays: that line owns it now
        if (AbilityEntry const* line = FindAbilityBySpell(rankSpell))
            if (auto o = st.abilities.find(line->firstSpellId);
                o != st.abilities.end() && o->second.source != GrantSource::Talent)
                continue;
        player->removeSpell(rankSpell, SPEC_MASK_ALL, false);
    }

    // the ability line the talent handed over goes with it
    for (uint32 first : t.abilityLines)
        if (auto o = st.abilities.find(first); o != st.abilities.end() && o->second.source == GrantSource::Talent)
            if (AbilityEntry const* e = GetAbility(first))
                RemoveAbilityInternal(player, *e, persist);

    if (persist)
        CharacterDatabase.Execute(
            "DELETE FROM cw_char_talents WHERE guid = {} AND talent_id = {}",
            player->GetGUID().GetCounter(), t.talentId);
}

// Every CLASS spell the Hero has NOT earned, removed.
//
// "Earned" means a rank of an ability they own or a rank spell of a talent they
// own -- so this cannot take away anything bought, rolled, or handed over with
// a form. Everything else is a spell the chassis class gave them for free,
// which is the one thing the classless economy must not allow.
//
// The sweep walks the library AND the spells the core hands out with a class
// skill line, not the library alone. The name dedupe DROPS a duplicate whose
// every rank is class- or quest-taught, which is right for a quest reward but
// leaves a chassis starter with nothing watching it: Seal of Righteousness is
// two spell ids, 20154 and 21084, both auto-learned with the Paladin line, and
// the one the dedupe threw out was never in _abilities to be found. It came
// back free with that line every time the core re-added it, and a Hero who had
// never rolled a paladin ability had it in their spellbook.
//
// _skillLearnedClassSpells is deliberately narrow: only AcquireMethod 1 or 2,
// the same rows learnSkillRewardedSpells teaches, on a class-category line
// with a class mask. 38 spells in the whole game. It holds no proficiency, no
// racial, no riding rank, nothing off a non-class line such as Attack or Duel,
// and no quest reward -- Polymorph: Pig has a SkillLineAbility row but
// AcquireMethod 0, so the mage quest that teaches it keeps working.
uint32 ClasslessMgr::StripUnearnedSpells(Player* player)
{
    CharState& st = GetState(player);

    std::unordered_set<uint32> earned;
    for (auto const& [firstSpell, owned] : st.abilities)
        if (AbilityEntry const* e = GetAbility(firstSpell))
            for (uint32 rank : e->ranks)
                earned.insert(rank);
    for (auto const& [talentId, rank] : st.talents)
        if (TalentPoolEntry const* t = GetTalent(talentId))
            for (uint8 r = 0; r < rank && r < t->rankSpells.size(); ++r)
                if (t->rankSpells[r])
                    earned.insert(t->rankSpells[r]);

    GrantGuard guard(_applyingGrant);
    uint32 removed = 0;
    auto take = [&](uint32 spellId)
    {
        if (earned.count(spellId) || !player->HasSpell(spellId))
            return;
        player->removeSpell(spellId, SPEC_MASK_ALL, false);
        ++removed;
    };

    // the library's own lines, including ranks that carry no SkillLineAbility
    // row of their own
    for (auto const& [firstSpell, e] : _abilities)
        for (uint32 rank : e.ranks)
            take(rank);

    // and the free-with-the-line spells, kept by the library or not
    for (uint32 spellId : _skillLearnedClassSpells)
        take(spellId);

    return removed;
}

// Keep the Hero's class skill lines in step with what they know.
//
// This is NOT what draws spellbook tabs -- that turned out to be decided
// entirely on the client, from SkillLineAbility's ClassMask, and is handled by
// the client patch. What this does is stop the chassis class re-teaching its
// starter spells: Player::LoadFromDB re-adds the chassis lines every login and
// fires learnSkillRewardedSpells for each, so a line the Hero has nothing in
// has to come back off, and a line they do have something in is kept so the
// core's own skill bookkeeping (UpdateSkillsForLevel etc.) stays consistent.
//
// Removing is the dangerous direction -- Player::SetSkill unlearns every spell
// attached to a skill line it removes -- so it is only ever done for a line the
// Hero has no EARNED spell in, where by construction there is nothing to lose.
//
// It has to run at every login, not once. Player::LoadFromDB calls
// LearnDefaultSkills on the way in, which re-adds any default skill the
// character is missing -- so the chassis class's line comes back every session
// however cleanly it was removed. Worse, SetSkill then fires
// learnSkillRewardedSpells, and Holy Light and Seal of Righteousness are
// AcquireMethod 2 (LEARNED_ON_SKILL_VALUE) at MinSkillLineRank 1 on line 594, so
// they are re-taught with it. That is the whole reason a Hero kept finding Holy
// Light in a Paladin tab they never trained: stripping the spell alone could
// never hold, because the line that hands it back was still there.
//
// Adding a line has the same property in reverse: SetSkill calls
// learnSkillRewardedSpells, so giving a Hero the Fire line to file a rolled
// Fireball under would also hand them the rest of that line's starter spells
// free. Hence the sweep at the end -- everything unearned goes straight back
// out, whichever direction it arrived from.
void ClasslessMgr::SyncSpellbookTabs(Player* player, bool clearChassisLines)
{
    if (!cfg.spellbookTabs || _classSkillLines.empty())
        return;
    CharState& st = GetState(player);
    if (st.exempt)
        return;

    // Which lines does the Hero have EARNED spells in? Built from what they
    // own, so it is exactly the set of tabs that would have something in them.
    std::set<uint16> want;
    auto add = [&](uint32 spellId)
    {
        auto itr = _spellSkillLine.find(spellId);
        if (itr != _spellSkillLine.end())
            want.insert(itr->second);
    };
    for (auto const& [firstSpell, owned] : st.abilities)
        if (AbilityEntry const* e = GetAbility(firstSpell))
            for (uint32 rank : e->ranks)
                add(rank);
    for (auto const& [talentId, rank] : st.talents)
        if (TalentPoolEntry const* t = GetTalent(talentId))
            for (uint8 r = 0; r < rank && r < t->rankSpells.size(); ++r)
                if (t->rankSpells[r])
                    add(t->rankSpells[r]);

    GrantGuard guard(_applyingGrant);

    // Drop the chassis class's own skill lines, and any other the Hero has
    // nothing in. This is what removes the lonely "Holy" tab a Paladin chassis
    // starts with, and what stops its auto-learned spells returning.
    //
    // Only ever for lines with nothing earned in them, so the unlearn cascade
    // SetSkill performs has nothing to take.
    if (clearChassisLines && cfg.spellbookTabs < 2)
        for (uint16 line : _classSkillLines)
            if (!want.count(line) && player->HasSkill(line))
                player->SetSkill(line, 0, 0, 0);

    // Then a tab for each school they actually know.
    std::set<uint16> const& give = (cfg.spellbookTabs >= 2) ? _classSkillLines : want;
    bool added = false;
    for (uint16 line : give)
        if (!player->HasSkill(line))
        {
            // value 1 with a level-scaled max, exactly what LearnDefaultSkill
            // gives a class line (SKILL_RANGE_LEVEL) and what UpdateSkillsForLevel
            // re-writes it to on every level-up
            player->SetSkill(line, 0, 1, player->GetMaxSkillValueForLevel());
            added = true;
        }

    // SetSkill just fired learnSkillRewardedSpells for every line added, which
    // hands out that line's learned-on-skill starter spells. Take back anything
    // the Hero did not earn, right now rather than at next login -- otherwise a
    // roll that opens a new tab pays out free spells until they relog.
    if (added && cfg.stripStartingSpells)
        StripUnearnedSpells(player);
}

void ClasslessMgr::UpdateAbilityRanks(Player* player)
{
    GrantGuard guard(_applyingGrant);
    CharState& st = GetState(player);
    uint8 level = player->GetLevel();

    for (auto const& [firstSpell, owned] : st.abilities)
    {
        AbilityEntry const* e = GetAbility(firstSpell);
        if (!e)
            continue;
        for (size_t i = 0; i < e->ranks.size(); ++i)
            if ((i == 0 || e->rankLevels[i] <= level) && !player->HasSpell(e->ranks[i]))
                player->learnSpell(e->ranks[i]);
    }
}

// -------------------------------------------------------------------------
// Classless free-pick operations
// -------------------------------------------------------------------------

bool ClasslessMgr::BuyAbility(Player* player, uint32 firstSpellId, std::string* err)
{
    CharState& st = GetState(player);
    if (st.mode != Mode::Classless)
    {
        if (err) *err = st.mode == Mode::Wildcard
            ? "Wildcard Heroes cannot pick abilities. The Wildcard picks for you, and you reroll what you dislike."
            : "Choose your path first (Hero Advancement NPC or .classless mode).";
        return false;
    }
    AbilityEntry const* e = GetAbility(firstSpellId);
    if (!e && sSpellMgr->GetSpellInfo(firstSpellId))
        e = FindAbilityBySpell(sSpellMgr->GetFirstSpellInChain(firstSpellId));

    if (!e || !e->enabled)
    {
        if (err) *err = "That spell is not part of the classless library.";
        return false;
    }
    if (e->variant && !cfg.elementalInPool)
    {
        if (err) *err = "Elemental variants are not available on this realm.";
        return false;
    }
    if (st.abilities.count(e->firstSpellId))
    {
        if (err) *err = "You already know that ability.";
        return false;
    }
    if (cfg.respectLevelReqs && !e->rankLevels.empty() && e->rankLevels[0] > player->GetLevel())
    {
        if (err) *err = Acore::StringFormat("That ability requires level {}.", uint32(e->rankLevels[0]));
        return false;
    }
    uint32 cost = AbilityCost(*e);
    if (st.abilityEssence < cost)
    {
        if (err) *err = Acore::StringFormat("Not enough Ability Essence ({} needed, {} available).", cost, st.abilityEssence);
        return false;
    }

    st.abilityEssence -= cost;
    GrantAbilityInternal(player, *e, GrantSource::Picked);
    SaveState(player);
    return true;
}

bool ClasslessMgr::UnlearnAbility(Player* player, uint32 firstSpellId, std::string* err)
{
    CharState& st = GetState(player);
    if (st.mode != Mode::Classless)
    {
        if (err) *err = "Unlearning is a Classless-path feature. Wildcard Heroes reroll instead.";
        return false;
    }
    AbilityEntry const* e = GetAbility(firstSpellId);
    if (!e && sSpellMgr->GetSpellInfo(firstSpellId))
        e = FindAbilityBySpell(sSpellMgr->GetFirstSpellInChain(firstSpellId));

    if (!e || !st.abilities.count(e->firstSpellId))
    {
        if (err) *err = "You do not own that ability.";
        return false;
    }
    if (st.abilities[e->firstSpellId].source == GrantSource::Talent)
    {
        if (err) *err = "That ability came with a talent and leaves with it. Respec to give it up.";
        return false;
    }
    // A companion cost nothing, so there is nothing to refund and nothing to
    // decide: it goes when the ability that brought it in goes.
    if (st.abilities[e->firstSpellId].source == GrantSource::Companion)
    {
        if (err) *err = "That came free with another ability. Unlearn the one it came with instead.";
        return false;
    }

    RemoveAbilityInternal(player, *e);
    if (cfg.refundOnUnlearn)
        st.abilityEssence += AbilityCost(*e);
    PruneCompanions(player);
    SaveState(player);
    Msg(player, Acore::StringFormat("Unlearned {}.", SpellName(e->firstSpellId)));
    return true;
}

uint32 ClasslessMgr::SpentTalentRanksInTab(CharState const& st, uint32 tabId) const
{
    uint32 total = 0;
    for (auto const& [talentId, rank] : st.talents)
        if (TalentPoolEntry const* t = GetTalent(talentId))
            if (t->tabId == tabId)
                total += rank;
    // an ability standing in for a talent of this tree counts as its point
    for (auto const& [talentId, t] : _replacedTalents)
        if (t.tabId == tabId && OwnsReplacedTalent(st, talentId))
            ++total;
    return total;
}

bool ClasslessMgr::BuyTalentRank(Player* player, uint32 talentId, std::string* err)
{
    CharState& st = GetState(player);
    if (st.mode != Mode::Classless)
    {
        if (err) *err = st.mode == Mode::Wildcard
            ? "Wildcard Heroes cannot pick talents. The Wildcard picks for you."
            : "Choose your path first (Hero Advancement NPC or .classless mode).";
        return false;
    }
    TalentPoolEntry const* t = GetTalent(talentId);
    if (!t || !t->enabled)
    {
        if (err) *err = "Unknown talent.";
        return false;
    }

    uint8 ownedRank = 0;
    if (auto itr = st.talents.find(talentId); itr != st.talents.end())
        ownedRank = itr->second;

    if (ownedRank >= t->maxRank)
    {
        if (err) *err = "That talent is already at max rank.";
        return false;
    }
    // A talent costs one point, not one per rank: only the first rank is
    // charged, so ranking a talent all the way to 5 still costs a single point.
    uint32 cost = (cfg.talentFlatCost && ownedRank > 0) ? 0 : cfg.talentCostPerRank;
    if (st.talentEssence < cost)
    {
        if (err) *err = Acore::StringFormat("Not enough Talent Essence ({} needed).", cost);
        return false;
    }
    if (t->dependsOn)
    {
        uint8 depRank = 0;
        if (auto itr = st.talents.find(t->dependsOn); itr != st.talents.end())
            depRank = itr->second;
        // a prerequisite that became an ability is met by owning that ability
        if (OwnsReplacedTalent(st, t->dependsOn))
            depRank = MAX_TALENT_RANK;
        if (depRank < t->dependsOnRank + 1)
        {
            if (err) *err = "You are missing a prerequisite talent.";
            if (auto rep = _replacedTalents.find(t->dependsOn); rep != _replacedTalents.end() && !rep->second.abilityLines.empty())
                if (err) *err = Acore::StringFormat("That needs the {} ability first. It is in the Abilities list.",
                                                    SpellName(rep->second.abilityLines[0]));
            return false;
        }
    }
    if (cfg.enforceTalentRows && SpentTalentRanksInTab(st, t->tabId) < t->row * 5)
    {
        if (err) *err = Acore::StringFormat("You need {} points in this tree to unlock that tier.", t->row * 5);
        return false;
    }
    // The tier's own level, the rule the browser labels rows with and the
    // Wildcard roll pool applies: tier R opens at level 10 + 5R. The essence
    // schedule already lands there on its own; this keeps it true whatever
    // the schedule is set to.
    if (cfg.respectLevelReqs && player->GetLevel() < 10 + t->row * 5)
    {
        if (err) *err = Acore::StringFormat("That talent tier requires level {}.", 10 + t->row * 5);
        return false;
    }

    st.talentEssence -= cost;
    GrantTalentRankInternal(player, *t, ownedRank + 1);
    SaveState(player);
    return true;
}

bool ClasslessMgr::Respec(Player* player, std::string* err)
{
    CharState& st = GetState(player);
    if (st.mode != Mode::Classless)
    {
        if (err) *err = "Respec is only available on the Classless path (Wildcard Heroes reroll instead).";
        return false;
    }

    int32 costCopper = int32(cfg.respecCostGold) * GOLD;
    if (!player->HasEnoughMoney(costCopper))
    {
        if (err) *err = Acore::StringFormat("Respec costs {} gold.", cfg.respecCostGold);
        return false;
    }
    player->ModifyMoney(-costCopper);

    std::vector<uint32> ownedAbilities;
    for (auto const& [firstSpell, owned] : st.abilities)
        ownedAbilities.push_back(firstSpell);
    for (uint32 firstSpell : ownedAbilities)
        if (AbilityEntry const* e = GetAbility(firstSpell))
            RemoveAbilityInternal(player, *e);

    std::vector<uint32> ownedTalents;
    for (auto const& [talentId, rank] : st.talents)
        ownedTalents.push_back(talentId);
    for (uint32 talentId : ownedTalents)
        if (TalentPoolEntry const* t = GetTalent(talentId))
            RemoveTalentInternal(player, *t);

    // rebuild full essence pools from the schedule
    uint8 level = player->GetLevel();
    st.abilityEssence = cfg.startingAbilityEssence + LevelsEarned(level, cfg.essenceStartLevel) * cfg.abilityEssencePerLevel;
    st.talentEssence = LevelsEarned(level, cfg.talentEssenceStartLevel) * cfg.talentEssencePerLevel;
    if (st.archetype)
    {
        Msg(player, Acore::StringFormat("You no longer follow |cffffff00{}|r.", ArchetypeName(st.archetype)));
        st.archetype = 0;
    }

    SaveState(player);
    Msg(player, Acore::StringFormat("Respec complete. AE: |cff00ff00{}|r, TE: |cff00ff00{}|r.",
        st.abilityEssence, st.talentEssence));
    // Everything is gone, so every class line is provably empty: clear
    // them now rather than leave stale empty tabs until the next login.
    SyncSpellbookTabs(player, true);
    return true;
}

// -------------------------------------------------------------------------
// Primary stat allocation ("choose your primary stat allocation,
// and reallocate at will" — free reallocation, like Ascension)
// -------------------------------------------------------------------------

uint32 ClasslessMgr::StatBudget(Player* player) const
{
    if (!cfg.statsEnable)
        return 0;
    return cfg.statStartingPoints + cfg.statPointsPerLevel * (player->GetLevel() - 1);
}

uint32 ClasslessMgr::SpentStatPoints(CharState const& st) const
{
    uint32 total = 0;
    for (uint32 points : st.statAlloc)
        total += points;
    return total;
}

void ClasslessMgr::ApplyStatMods(Player* player)
{
    CharState& st = GetState(player);
    for (uint8 i = 0; i < 5; ++i)
    {
        int32 want = cfg.statsEnable ? int32(st.statAlloc[i] * cfg.statValuePerPoint) : 0;
        if (want == st.appliedStatBonus[i])
            continue;
        if (st.appliedStatBonus[i])
            player->HandleStatFlatModifier(UnitMods(UNIT_MOD_STAT_START + i), TOTAL_VALUE, float(st.appliedStatBonus[i]), false);
        if (want)
            player->HandleStatFlatModifier(UnitMods(UNIT_MOD_STAT_START + i), TOTAL_VALUE, float(want), true);
        st.appliedStatBonus[i] = want;
    }
}

bool ClasslessMgr::SetStatAllocation(Player* player, std::array<uint32, 5> const& alloc, std::string* err)
{
    if (!cfg.statsEnable)
    {
        if (err) *err = "Stat allocation is disabled on this realm.";
        return false;
    }

    uint32 total = 0;
    for (uint32 points : alloc)
        total += points;

    uint32 budget = StatBudget(player);
    if (total > budget)
    {
        if (err) *err = Acore::StringFormat("That allocation needs {} points but you have {}.", total, budget);
        return false;
    }

    CharState& st = GetState(player);
    st.statAlloc = alloc;
    ApplyStatMods(player);
    SaveState(player);

    Msg(player, Acore::StringFormat(
        "Stats allocated. STR +{}, AGI +{}, STA +{}, INT +{}, SPI +{} ({} of {} points).",
        alloc[0] * cfg.statValuePerPoint, alloc[1] * cfg.statValuePerPoint, alloc[2] * cfg.statValuePerPoint,
        alloc[3] * cfg.statValuePerPoint, alloc[4] * cfg.statValuePerPoint, total, budget));
    return true;
}

// -------------------------------------------------------------------------
// Wildcard engine
// -------------------------------------------------------------------------

bool ClasslessMgr::IsBanned(CharState const& st, bool isTalent, uint32 entry) const
{
    for (RollBan const& ban : st.bans)
        if (ban.isTalent == isTalent && ban.entry == entry && ban.rollsLeft > 0)
            return true;
    return false;
}

// A reroll cooldown exists to stop the replacement roll handing back the exact
// thing the Hero just rerolled. It was never meant to outrank keeping a roll at
// the Hero's own level -- but because IsBanned filters the fallback pool too, a
// starved level-legal pool used to mean the Hero got an ability well above
// their level instead. That bites hardest at level 1, where the legal pool is
// smallest and rerolls are free, so players churn them.
//
// So when the legal pool runs dry, the cooldowns are what give way: put them
// all back in play and roll from a healthy pool again. Handing back something
// rerolled a few rolls ago beats handing a level 1 Hero a spell they cannot
// cast for twenty levels.
bool ClasslessMgr::ReleaseCooldowns(CharState& st, ObjectGuid guid, bool isTalent)
{
    std::size_t const before = st.bans.size();
    st.bans.erase(std::remove_if(st.bans.begin(), st.bans.end(),
                                 [isTalent](RollBan const& b) { return b.isTalent == isTalent; }),
                  st.bans.end());
    if (st.bans.size() == before)
        return false;

    SaveBans(guid, st);
    LOG_DEBUG("module.classless",
              "mod-classless-wildcard: {} roll pool starved for guid {}; released {} reroll cooldown(s)",
              isTalent ? "talent" : "ability", guid.GetCounter(), before - st.bans.size());
    return true;
}

void ClasslessMgr::TickBans(CharState& st, ObjectGuid guid)
{
    bool changed = false;
    for (auto itr = st.bans.begin(); itr != st.bans.end();)
    {
        if (--itr->rollsLeft <= 0)
        {
            itr = st.bans.erase(itr);
            changed = true;
        }
        else
            ++itr;
    }
    if (changed)
        SaveBans(guid, st);
}

uint32 ClasslessMgr::OwnedClassMask(CharState const& st) const
{
    uint32 mask = 0;
    for (auto const& [firstSpell, owned] : st.abilities)
        if (AbilityEntry const* e = GetAbility(firstSpell))
            mask |= e->classMask;
    for (auto const& [talentId, rank] : st.talents)
        if (TalentPoolEntry const* t = GetTalent(talentId))
            mask |= t->classMask;
    return mask;
}

uint32 ClasslessMgr::RollAbility(Player* player, GrantSource source)
{
    CharState& st = GetState(player);
    ObjectGuid guid = player->GetGUID();
    TickBans(st, guid);

    // never deal an ability whose NAME the Hero already owns (duplicate spell
    // ids with identical names exist in the DBC)
    std::unordered_set<std::string> ownedNames;
    for (auto const& [ownedFirst, ownedAb] : st.abilities)
        if (AbilityEntry const* oe = GetAbility(ownedFirst))
            if (!oe->name.empty())
                ownedNames.insert(oe->name);

    // candidates — tiered: only spells whose rank-1 learn level the Hero has
    // reached (fall back to the full pool if the level-legal one is exhausted)
    std::vector<AbilityEntry const*> candidates;
    std::vector<AbilityEntry const*> anyLevel;
    candidates.reserve(_abilities.size());
    auto buildPool = [&]()
    {
        candidates.clear();
        anyLevel.clear();
        for (auto const& [firstSpell, e] : _abilities)
        {
            if (!e.enabled || st.abilities.count(firstSpell) || IsBanned(st, false, firstSpell))
                continue;
            if (e.variant && !cfg.elementalInPool)
                continue;
            if (!e.name.empty() && ownedNames.count(e.name))
                continue;
            anyLevel.push_back(&e);
            if (!cfg.respectLevelReqs || e.rankLevels.empty() || e.rankLevels[0] <= player->GetLevel())
                candidates.push_back(&e);
        }
    };
    buildPool();

    // Every ability the Hero could actually USE is owned or on a reroll
    // cooldown. Release the cooldowns and rebuild rather than reaching above
    // the Hero's level for something they cannot cast -- see ReleaseCooldowns.
    if (candidates.empty() && ReleaseCooldowns(st, guid, false))
        buildPool();

    // Still nothing legal, so the Hero genuinely owns everything at their
    // level. Fall back to the LOWEST-level entries rather than to the whole
    // library: the old "anyLevel" fallback is how a level 1 Hero got dealt
    // Unstable Affliction. A roll is still never lost, it just stays as close
    // to the Hero's level as the remaining pool allows.
    if (candidates.empty() && !anyLevel.empty())
    {
        uint32 best = 0xFFFFFFFF;
        for (AbilityEntry const* e : anyLevel)
            best = std::min<uint32>(best, e->rankLevels.empty() ? 0 : e->rankLevels[0]);
        for (AbilityEntry const* e : anyLevel)
            if ((e->rankLevels.empty() ? 0u : uint32(e->rankLevels[0])) == best)
                candidates.push_back(e);
    }

    if (candidates.empty())
        return 0;

    // synergy roll?
    bool synergy = false;
    uint32 ownedMask = OwnedClassMask(st);
    if (ownedMask)
    {
        uint32 chance = std::min<uint32>(cfg.wcSynergyBaseChance + st.pity * cfg.wcSynergyIncrement, 100);
        if (roll_chance_i(int32(chance)))
        {
            std::vector<AbilityEntry const*> filtered;
            for (AbilityEntry const* e : candidates)
                if (e->classMask & ownedMask)
                    filtered.push_back(e);
            if (!filtered.empty())
            {
                candidates = std::move(filtered);
                synergy = true;
            }
        }
    }

    // weighted pick
    uint32 total = 0;
    for (AbilityEntry const* e : candidates)
        total += RollWeight(e->rarity, e->weight);
    AbilityEntry const* chosen = nullptr;
    if (!total) // all weights zero -> uniform pick
        chosen = candidates[urand(0, candidates.size() - 1)];
    else
    {
        uint32 pick = urand(0, total - 1);
        chosen = candidates.back();
        for (AbilityEntry const* e : candidates)
        {
            uint32 w = RollWeight(e->rarity, e->weight);
            if (pick < w) { chosen = e; break; }
            pick -= w;
        }
    }

    if (synergy)
    {
        st.pity = 0;
        Msg(player, "|cff00ff88Synergy roll!|r This ability complements your Hero.");
    }

    // The pool is built to exclude everything owned, so this can only fire if
    // the library changed underneath the roll. Say so rather than re-granting
    // a line, which would stamp over its source and clear its padlock.
    if (st.abilities.count(chosen->firstSpellId))
    {
        LOG_WARN("module.classless", "Roll picked ability {} ({}) which guid {} already owns; skipped",
                 chosen->firstSpellId, SpellName(chosen->firstSpellId), player->GetGUID().GetCounter());
        return 0;
    }

    GrantAbilityInternal(player, *chosen, source);
    SaveState(player);
    // _revealSuppress is on while a whole hand is being dealt at once (the
    // starting hand, a Rebirth): the client shows those in bulk on its own
    // screen, so a die-roll popup per ability is noise. It used to be set in
    // four places and read in none, which left Rebirth firing a popup per
    // ability and the starting hand relying on the addon to throw them away.
    if (!_revealSuppress)
        PushAddon(player, Acore::StringFormat("RV|A|{}|{}|{}",
            chosen->firstSpellId, uint32(chosen->rarity), synergy ? 1 : 0));
    return chosen->firstSpellId;
}

uint32 ClasslessMgr::RollTalent(Player* player)
{
    CharState& st = GetState(player);
    ObjectGuid guid = player->GetGUID();
    TickBans(st, guid);

    uint32 ownedMask = OwnedClassMask(st);
    uint32 lastGranted = 0;

    // ONE roll, ONE talent. This used to chain: landing on a talent already
    // owned upgraded it and rolled again, up to four times, and a talent
    // reroll ran the whole thing once per rank refunded. A single reroll of a
    // rank 5 talent could therefore hand over twenty grants.
    {
        // tiered: a talent in tree row R unlocks at level 10 + R*5 (the level a
        // vanilla character could first reach that row); fall back to the full
        // pool if the level-legal one is exhausted
        std::vector<TalentPoolEntry const*> candidates;
        std::vector<TalentPoolEntry const*> anyLevel;
        candidates.reserve(_talents.size());
        auto buildPool = [&]()
        {
            candidates.clear();
            anyLevel.clear();
            for (auto const& [talentId, t] : _talents)
            {
                if (!t.enabled || IsBanned(st, true, talentId))
                    continue;
                // A roll only ever hands over a talent the Hero does not
                // have. Deepening one already held is what a reroll with
                // scrolls is for, so a roll is never spent on something the
                // Hero already owns.
                if (st.talents.count(talentId))
                    continue;
                anyLevel.push_back(&t);
                if (!cfg.respectLevelReqs || player->GetLevel() >= 10 + t.row * 5)
                    candidates.push_back(&t);
            }
        };
        buildPool();

        // same rule as abilities: cooldowns give way before the tier does
        if (candidates.empty() && ReleaseCooldowns(st, guid, true))
            buildPool();

        // when nothing is level-legal even then, drop to the LOWEST tier still
        // available rather than opening up the whole tree
        if (candidates.empty() && !anyLevel.empty())
        {
            uint32 best = 0xFFFFFFFF;
            for (TalentPoolEntry const* t : anyLevel)
                best = std::min<uint32>(best, t->row);
            for (TalentPoolEntry const* t : anyLevel)
                if (t->row == best)
                    candidates.push_back(t);
        }

        if (candidates.empty())
            return lastGranted;

        bool synergy = false;
        if (ownedMask)
        {
            uint32 chance = std::min<uint32>(cfg.wcSynergyBaseChance + st.pity * cfg.wcSynergyIncrement, 100);
            if (roll_chance_i(int32(chance)))
            {
                std::vector<TalentPoolEntry const*> filtered;
                for (TalentPoolEntry const* t : candidates)
                    if (t->classMask & ownedMask)
                        filtered.push_back(t);
                if (!filtered.empty())
                {
                    candidates = std::move(filtered);
                    synergy = true;
                }
            }
        }

        uint32 total = 0;
        for (TalentPoolEntry const* t : candidates)
            total += RollWeight(t->rarity, t->weight);
        TalentPoolEntry const* chosen = nullptr;
        if (!total) // all weights zero -> uniform pick
            chosen = candidates[urand(0, candidates.size() - 1)];
        else
        {
            uint32 pick = urand(0, total - 1);
            chosen = candidates.back();
            for (TalentPoolEntry const* t : candidates)
            {
                uint32 w = RollWeight(t->rarity, t->weight);
                if (pick < w) { chosen = t; break; }
                pick -= w;
            }
        }

        if (synergy)
        {
            st.pity = 0;
            Msg(player, "|cff00ff88Synergy roll!|r This talent complements your Hero.");
        }

        // the roll decides the RANK too, not just the talent, on its own
        // weight ladder: rank 5 is roughly a twentieth as likely as rank 1
        uint8 newRank = RollTalentRank(*chosen, 0);
        if (!newRank)
            return lastGranted; // no rank to give (a zero-rank talent row)
        Rarity shown = RankRarity(*chosen, newRank);

        GrantTalentRankInternal(player, *chosen, newRank);
        lastGranted = chosen->talentId;
        if (!_revealSuppress)
            // field 8 is the talent's maximum rank: the reveal needs it to know
            // whether this one still has a rank left to stake scrolls on
            PushAddon(player, Acore::StringFormat("RV|T|{}|{}|{}|{}|{}|{}",
                chosen->talentId, chosen->rankSpells[newRank - 1], uint32(shown),
                uint32(newRank), synergy ? 1 : 0, uint32(chosen->maxRank)));
    }

    SaveState(player);
    return lastGranted;
}

bool ClasslessMgr::Reroll(Player* player, bool isTalent, uint32 entry, std::string* err,
                          uint32 extraScrolls)
{
    CharState& st = GetState(player);
    if (st.mode != Mode::Wildcard)
    {
        if (err) *err = "Rerolls are a Wildcard mechanic.";
        return false;
    }

    bool free = player->GetLevel() < cfg.wcFreeRerollLevel;

    if (isTalent)
    {
        TalentPoolEntry const* t = GetTalent(entry);
        auto itr = st.talents.find(entry);
        if (!t || itr == st.talents.end())
        {
            if (err) *err = "You do not own that talent.";
            return false;
        }

        uint8 const heldRank = itr->second;
        bool const canDeepen = heldRank < t->maxRank;

        // Extra scrolls buy a chance to KEEP this talent and raise its rank
        // rather than trade it away. There is nothing to raise on a maxed one.
        extraScrolls = std::min<uint32>(extraScrolls, cfg.wcTalentUpgradeMaxScrolls);
        if (extraScrolls && !canDeepen)
        {
            if (err) *err = Acore::StringFormat(
                "{} is already at rank {}. There is no higher rank to roll for.",
                SpellName(t->rankSpells[0]), uint32(t->maxRank));
            return false;
        }

        // The reroll itself is one charge, or one scroll when no charge is
        // left, or nothing below the free-reroll level. Every extra is a
        // scroll on top, at any level.
        uint32 scrolls = extraScrolls;
        bool spendCharge = false;
        if (!free)
        {
            if (st.rerolls > 0)
                spendCharge = true;
            else
                ++scrolls;
        }
        if (scrolls && !player->HasItemCount(cfg.wcScrollItemId, int32(scrolls)))
        {
            if (err) *err = extraScrolls
                ? Acore::StringFormat("That costs {} Reroll Scrolls and you do not have that many.", scrolls)
                : std::string("No rerolls left. You earn one with every roll the Wildcard deals you, or buy a Reroll Scroll.");
            return false;
        }
        if (spendCharge)
            --st.rerolls;
        if (scrolls)
            player->DestroyItemCount(cfg.wcScrollItemId, scrolls, true);

        ++st.pity;

        uint32 const chance = std::min<uint32>(100,
            cfg.wcTalentUpgradeBase + extraScrolls * cfg.wcTalentUpgradePerScroll);
        if (canDeepen && chance && roll_chance_i(int32(chance)))
        {
            // Kept and deepened. Nothing was given up, so nothing is banned.
            uint8 const newRank = RollTalentRank(*t, heldRank);
            if (newRank)
            {
                GrantTalentRankInternal(player, *t, newRank);
                if (!_revealSuppress)
                    PushAddon(player, Acore::StringFormat("RV|T|{}|{}|{}|{}|0|{}",
                        t->talentId, t->rankSpells[newRank - 1],
                        uint32(RankRarity(*t, newRank)), uint32(newRank), uint32(t->maxRank)));
                Msg(player, Acore::StringFormat("{} rises to rank {} of {}.",
                    SpellName(t->rankSpells[0]), uint32(newRank), uint32(t->maxRank)));
                PruneCompanions(player);
                SaveState(player);
                return true;
            }
        }

        // Traded away: it goes, it cannot come straight back, and the Wildcard
        // deals one new talent in its place.
        if (extraScrolls)
            Msg(player, Acore::StringFormat("{} did not hold. The Wildcard deals again.",
                SpellName(t->rankSpells[0])));
        RemoveTalentInternal(player, *t);

        st.bans.push_back({ entry, true, int32(cfg.wcSynergyBanRolls) });
        SaveBans(player->GetGUID(), st);

        RollTalent(player);
    }
    else
    {
        AbilityEntry const* e = GetAbility(entry);
        if (!e && sSpellMgr->GetSpellInfo(entry))
            e = FindAbilityBySpell(sSpellMgr->GetFirstSpellInChain(entry));

        if (!e || !st.abilities.count(e->firstSpellId))
        {
            if (err) *err = "You do not own that ability.";
            return false;
        }
        if (st.abilities[e->firstSpellId].locked)
        {
            // Nothing should ever ask for this: every caller filters locked
            // lines out first. Reaching it means the client's padlock and the
            // server's disagreed, which is worth a line in the log naming both,
            // because the player will report it as a lock that did not hold.
            LOG_WARN("module.classless",
                     "Reroll refused: guid {} asked to reroll LOCKED ability {} ({})",
                     player->GetGUID().GetCounter(), e->firstSpellId, SpellName(e->firstSpellId));
            if (err) *err = "That ability is locked. Unlock it first.";
            return false;
        }
        if (st.abilities[e->firstSpellId].source == GrantSource::Talent)
        {
            if (err) *err = "That ability came with a talent. Reroll the talent instead.";
            return false;
        }
        if (st.abilities[e->firstSpellId].source == GrantSource::Companion)
        {
            if (err) *err = "That came free with another ability. Reroll the one it came with instead.";
            return false;
        }

        if (!free)
        {
            if (st.rerolls > 0)
                --st.rerolls; // earned charge (granted with every roll)
            else if (player->HasItemCount(cfg.wcScrollItemId, 1))
                player->DestroyItemCount(cfg.wcScrollItemId, 1, true);
            else
            {
                if (err) *err = "No rerolls left. You earn one with every roll the Wildcard deals you, or buy a Reroll Scroll.";
                return false;
            }
        }

        RemoveAbilityInternal(player, *e);

        st.bans.push_back({ e->firstSpellId, false, int32(cfg.wcSynergyBanRolls) });
        SaveBans(player->GetGUID(), st);
        ++st.pity;

        RollAbility(player);
    }

    // Whichever branch ran, the replacement may already need the stance the old
    // entry brought in, so the sweep goes last. A talent reroll matters here
    // too: RemoveTalentInternal takes away the ability lines the talent handed
    // over, and those can have companions of their own.
    PruneCompanions(player);

    SaveState(player);
    return true;
}

uint32 ClasslessMgr::RerollUnlockedAbilities(Player* player, std::string* err)
{
    CharState& st = GetState(player);
    if (st.mode != Mode::Wildcard)
    {
        if (err) *err = "Rerolls are a Wildcard mechanic.";
        return 0;
    }

    // snapshot from OUR state, not the client's: the ids are guaranteed to be
    // owned right now, and rerolled entries are banned from coming straight
    // back, so nothing in the list can be invalidated by an earlier reroll
    std::vector<uint32> targets;
    uint32 kept = 0;
    for (auto const& [firstSpell, owned] : st.abilities)
    {
        if (owned.source == GrantSource::Talent || owned.source == GrantSource::Companion)
            continue;
        if (owned.locked)
        {
            ++kept;
            continue;
        }
        targets.push_back(firstSpell);
    }

    // What the server believed the padlocks were, at the moment it acted on
    // them. "It rerolled one I had locked" is otherwise impossible to tell
    // apart from "the lock never reached the server".
    LOG_INFO("module.classless", "Reroll all: guid {} rerolling {} line(s), keeping {} locked",
             player->GetGUID().GetCounter(), uint32(targets.size()), kept);

    uint32 done = 0;
    for (uint32 firstSpell : targets)
    {
        if (!st.abilities.count(firstSpell))
            continue; // defensive: already gone
        std::string one;
        if (!Reroll(player, false, firstSpell, &one))
        {
            // out of charges (or similar): report once, don't spam per ability
            if (err && err->empty())
                *err = one;
            break;
        }
        ++done;
    }
    return done;
}

bool ClasslessMgr::SetLock(Player* player, uint32 firstSpellId, bool locked, std::string* err)
{
    CharState& st = GetState(player);
    AbilityEntry const* e = GetAbility(firstSpellId);
    if (!e && sSpellMgr->GetSpellInfo(firstSpellId))
        e = FindAbilityBySpell(sSpellMgr->GetFirstSpellInChain(firstSpellId));

    if (!e || !st.abilities.count(e->firstSpellId))
    {
        if (err) *err = "You do not own that ability.";
        return false;
    }

    // A lock only protects an ability from a reroll, and neither of these can
    // be rerolled in the first place: they come and go with whatever granted
    // them. Refusing here keeps the chat command in step with the addon and the
    // NPC, which show no padlock on either.
    if (GrantSource const source = st.abilities[e->firstSpellId].source;
        source == GrantSource::Companion || source == GrantSource::Talent)
    {
        if (err) *err = source == GrantSource::Companion
            ? "That came free with another ability. It cannot be rerolled, so there is nothing to lock."
            : "That came with a talent. It cannot be rerolled, so there is nothing to lock.";
        return false;
    }

    if (locked && player->GetLevel() >= cfg.wcFreeRerollLevel)
    {
        if (err) *err = Acore::StringFormat(
            "Padlocks only matter while the starting hand is open (below level {}). "
            "From there you reroll one ability at a time, and only the one you pick.",
            uint32(cfg.wcFreeRerollLevel));
        return false;
    }

    OwnedAbility& owned = st.abilities[e->firstSpellId];
    bool const changed = owned.locked != locked;
    owned.locked = locked;
    // Written every time, not only when it changed. An explicit set is the one
    // moment the row can be put right if it ever fell out of step with memory,
    // and re-asking for a lock you already hold is exactly what a player does
    // when the padlock looks wrong.
    CharacterDatabase.Execute(
        "UPDATE cw_char_abilities SET locked = {} WHERE guid = {} AND first_spell = {}",
        owned.locked ? 1 : 0, player->GetGUID().GetCounter(), e->firstSpellId);

    if (changed)
        Msg(player, Acore::StringFormat("{} is now {}.", SpellName(e->firstSpellId),
            owned.locked ? "|cffffff00locked|r" : "unlocked"));
    return true;
}

bool ClasslessMgr::ToggleLock(Player* player, uint32 firstSpellId, std::string* err)
{
    CharState& st = GetState(player);
    AbilityEntry const* e = GetAbility(firstSpellId);
    if (!e && sSpellMgr->GetSpellInfo(firstSpellId))
        e = FindAbilityBySpell(sSpellMgr->GetFirstSpellInChain(firstSpellId));

    bool want = true;
    if (e)
        if (auto o = st.abilities.find(e->firstSpellId); o != st.abilities.end())
            want = !o->second.locked;
    return SetLock(player, firstSpellId, want, err);
}

