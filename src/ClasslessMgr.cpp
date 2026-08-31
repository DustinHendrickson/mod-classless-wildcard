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

    Rarity RarityFromSpellLevel(uint32 level)
    {
        if (level < 10) return Rarity::Common;
        if (level < 25) return Rarity::Uncommon;
        if (level < 45) return Rarity::Rare;
        if (level < 60) return Rarity::Epic;
        return Rarity::Legendary;
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

    cfg.includeDeathKnight = sConfigMgr->GetOption<bool>("ClasslessWildcard.IncludeDeathKnight", false);
    cfg.includeRacials = sConfigMgr->GetOption<bool>("ClasslessWildcard.IncludeRacials", false);
    cfg.includePassives = sConfigMgr->GetOption<bool>("ClasslessWildcard.IncludePassives", true);
    cfg.respectLevelReqs = sConfigMgr->GetOption<bool>("ClasslessWildcard.RespectLevelRequirements", true);
    cfg.trainerTaughtOnly = sConfigMgr->GetOption<bool>("ClasslessWildcard.TrainerTaughtOnly", true);

    cfg.stripStartingSpells = sConfigMgr->GetOption<bool>("ClasslessWildcard.StripStartingSpells", true);
    cfg.starterKitEnable = sConfigMgr->GetOption<bool>("ClasslessWildcard.StarterKit.Enable", true);
    cfg.starterKitStripEquipped = sConfigMgr->GetOption<bool>("ClasslessWildcard.StarterKit.StripEquipped", true);
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
    // gun+shot, thrown
    std::string kitList = sConfigMgr->GetOption<std::string>(
        "ClasslessWildcard.StarterKit.Items",
        "2092:2,36:1,1194:1,2361:1,12282:1,35:1,2504:1,2512:200,2508:1,2516:200,25861:200");
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

    cfg.teachProficiencies = sConfigMgr->GetOption<bool>("ClasslessWildcard.TeachProficiencies", true);
    cfg.proficiencySpells = ParseUintList(sConfigMgr->GetOption<std::string>(
        "ClasslessWildcard.ProficiencySpells",
        // cloth, leather, mail, plate, shield, swords 1h/2h, axes 1h/2h, maces 1h/2h,
        // polearms, staves, daggers, fist, bows, guns, crossbows, thrown, wands, shoot, dual wield
        "9078,9077,8737,750,9116,201,202,196,197,198,199,200,227,1180,15590,264,266,5011,2567,5009,5019,674"));

    cfg.suppressTalentPoints = sConfigMgr->GetOption<bool>("ClasslessWildcard.SuppressTalentPoints", true);
    cfg.blockOutsideSpellSources = sConfigMgr->GetOption<bool>("ClasslessWildcard.BlockOutsideSpellSources", true);

    cfg.startingAbilityEssence = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Classless.StartingAbilityEssence", 9);
    cfg.essenceStartLevel = sConfigMgr->GetOption<uint8>("ClasslessWildcard.Classless.EssenceStartLevel", 10);
    cfg.abilityEssencePerLevel = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Classless.AbilityEssencePerLevel", 1);
    cfg.talentEssencePerLevel = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Classless.TalentEssencePerLevel", 1);
    cfg.talentCostPerRank = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Classless.TalentCostPerRank", 1);
    cfg.enforceTalentRows = sConfigMgr->GetOption<bool>("ClasslessWildcard.Classless.EnforceTalentRows", true);
    cfg.refundOnUnlearn = sConfigMgr->GetOption<bool>("ClasslessWildcard.Classless.RefundOnUnlearn", true);
    cfg.respecCostGold = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Classless.RespecCostGold", 50);

    {
        std::vector<uint32> costs = ParseUintList(sConfigMgr->GetOption<std::string>(
            "ClasslessWildcard.Classless.AbilityCostByRarity", "1,2,3,5,8"));
        for (size_t i = 0; i < costs.size() && i < 5; ++i)
            cfg.abilityCostByRarity[i] = costs[i];
    }

    cfg.wcStartingAbilities = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.StartingAbilities", 4);
    cfg.wcRollStartLevel = sConfigMgr->GetOption<uint8>("ClasslessWildcard.Wildcard.RollStartLevel", 10);
    cfg.wcTalentEveryLevels = std::max<uint32>(1, sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.TalentEveryLevels", 1));
    cfg.wcAbilityEveryLevels = std::max<uint32>(1, sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.AbilityEveryLevels", 2));
    cfg.wcFreeRerollLevel = sConfigMgr->GetOption<uint8>("ClasslessWildcard.Wildcard.FreeRerollBelowLevel", 10);

    {
        // Season 9 default: equal weights = pure random ("no weighting, no hidden
        // rules"). Set descending weights (e.g. 100,60,30,10,3) for Season-10-style
        // rarity-weighted rolls.
        std::vector<uint32> weights = ParseUintList(sConfigMgr->GetOption<std::string>(
            "ClasslessWildcard.Wildcard.RarityWeights", "100,100,100,100,100"));
        for (size_t i = 0; i < weights.size() && i < 5; ++i)
            cfg.wcRarityWeights[i] = weights[i];
    }

    cfg.wcSynergyBaseChance = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.SynergyBaseChance", 10);
    cfg.wcSynergyIncrement = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.SynergyIncrement", 10);
    cfg.wcSynergyBanRolls = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.SynergyBanRolls", 25);
    // Season 9 default: 0 + 0 of a type = UNLIMITED card slots ("no skill card caps")
    cfg.wcAbilityCards = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.AbilityCards", 0);
    cfg.wcGoldenAbilityCards = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.GoldenAbilityCards", 0);
    cfg.wcTalentCards = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.TalentCards", 0);
    cfg.wcGoldenTalentCards = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.GoldenTalentCards", 0);
    cfg.wcScrollItemId = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.ScrollItemId", 990101);
    cfg.wcScrollTalentItemId = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.ScrollTalentItemId", 990102);
    cfg.wcRerollsPerAbilityRoll = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.RerollsPerAbilityRoll", 1);
    cfg.wcRerollsPerTalentRoll = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.RerollsPerTalentRoll", 1);
    cfg.wcFreeScrollEveryLevels = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.FreeScrollEveryLevels", 0);
    cfg.wcFreeScrollCount = sConfigMgr->GetOption<uint32>("ClasslessWildcard.Wildcard.FreeScrollCount", 1);

    cfg.universalResources = sConfigMgr->GetOption<bool>("ClasslessWildcard.UniversalResources.Enable", true);
    cfg.urBaseMana = sConfigMgr->GetOption<uint32>("ClasslessWildcard.UniversalResources.BaseMana", 100);
    cfg.urManaPerLevel = sConfigMgr->GetOption<uint32>("ClasslessWildcard.UniversalResources.ManaPerLevel", 35);
    cfg.urManaPerIntellect = sConfigMgr->GetOption<uint32>("ClasslessWildcard.UniversalResources.ManaPerIntellect", 15);
    cfg.urMaxRage = sConfigMgr->GetOption<uint32>("ClasslessWildcard.UniversalResources.MaxRage", 1000);
    cfg.urMaxEnergy = sConfigMgr->GetOption<uint32>("ClasslessWildcard.UniversalResources.MaxEnergy", 100);
    cfg.urRageDealtPct = sConfigMgr->GetOption<uint32>("ClasslessWildcard.UniversalResources.RageFromDealtPct", 100);
    cfg.urRageTakenPct = sConfigMgr->GetOption<uint32>("ClasslessWildcard.UniversalResources.RageFromTakenPct", 100);
    cfg.urManaRegenBase = sConfigMgr->GetOption<float>("ClasslessWildcard.UniversalResources.ManaRegenBase", 4.0f);
    cfg.urManaRegenPerSpirit = sConfigMgr->GetOption<float>("ClasslessWildcard.UniversalResources.ManaRegenPerSpirit", 0.3f);
    cfg.urManaRegenPct = sConfigMgr->GetOption<uint32>("ClasslessWildcard.UniversalResources.ManaRegenPct", 0);

    cfg.chassisEnable = sConfigMgr->GetOption<bool>("ClasslessWildcard.Chassis.Enable", true);
    cfg.chassisClass = uint8(sConfigMgr->GetOption<uint32>("ClasslessWildcard.Chassis.Class", CLASS_PALADIN));

    cfg.universalStats = sConfigMgr->GetOption<bool>("ClasslessWildcard.UniversalStats.Enable", true);
    cfg.usMeleeAPPerAgi = sConfigMgr->GetOption<float>("ClasslessWildcard.UniversalStats.MeleeAPPerAgility", 1.0f);
    cfg.usRangedAPPerAgi = sConfigMgr->GetOption<float>("ClasslessWildcard.UniversalStats.RangedAPPerAgility", 1.0f);
    cfg.usSpellPowerPerInt = sConfigMgr->GetOption<float>("ClasslessWildcard.UniversalStats.SpellPowerPerIntellect", 1.0f);

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
    _talents.clear();
    _spellToFirst.clear();

    uint32 const dkMask = 1 << (CLASS_DEATH_KNIGHT - 1);

    // Trainer allowlist + REAL learn levels: what classes actually learn is
    // starter spells + class-trainer lists (npc_trainer). This kills NPC/pet
    // variants ("Demonic Immolate") and tiers every rank by the level a real
    // class would learn it.
    std::unordered_map<uint32, uint8> learnLevels; // spellId -> req level
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

            if (learnLevels.empty())
            {
                LOG_ERROR("module.classless", "mod-classless-wildcard: trainer tables yielded no class spells — "
                    "TrainerTaughtOnly filter disabled for this session");
                useTrainerFilter = false;
            }
            else
                LOG_INFO("module.classless", "mod-classless-wildcard: {} trainer/starter spells collected", learnLevels.size());
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

        SpellInfo const* info = sSpellMgr->GetSpellInfo(sla->Spell);
        if (!info || !info->SpellName[0] || !*info->SpellName[0])
            continue;
        if (GetTalentSpellCost(sla->Spell)) // talent spells live in the talent pool
            continue;
        if (info->IsPassive() && !cfg.includePassives)
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

        if (SpellInfo const* firstInfo = sSpellMgr->GetSpellInfo(e.firstSpellId))
            if (firstInfo->SpellName[0])
                e.name = firstInfo->SpellName[0];

        e.rarity = RarityFromSpellLevel(e.rankLevels[0]);
        e.cost = cfg.abilityCostByRarity[uint8(e.rarity)];
        e.weight = 0; // 0 = use rarity weight
        ++itr;
    }

    // Dedupe by NAME: the DBC holds multiple spell ids with identical names
    // (unchained copies, NPC variants). Keep the best line per name — most
    // ranks, then lowest id — and disable the rest, merging class masks so
    // browsing still finds the survivor under every class.
    {
        std::unordered_map<std::string, AbilityEntry*> byName;
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
            if (newBetter)
            {
                e.classMask |= keep->classMask;
                keep->enabled = false;
                itr2->second = &e;
            }
            else
            {
                keep->classMask |= e.classMask;
                e.enabled = false;
            }
            ++disabled;
        }
        LOG_INFO("module.classless", "mod-classless-wildcard: disabled {} duplicate-name ability lines", disabled);
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

    LoadOverrides();
    LoadArchetypes();
    _libraryBuilt = true;

    LOG_INFO("module", "mod-classless-wildcard: library built — {} ability lines, {} talents.",
             _abilities.size(), _talents.size());
}

void ClasslessMgr::LoadOverrides()
{
    if (QueryResult result = WorldDatabase.Query("SELECT first_spell, rarity, cost, weight, enabled FROM cw_ability_override"))
    {
        do
        {
            Field* f = result->Fetch();
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

bool ClasslessMgr::ApplyArchetype(Player* player, uint32 archetypeId, std::string* err)
{
    CharState& st = GetState(player);
    if (st.mode != Mode::Classless)
    {
        if (err) *err = "Archetypes are starter builds for the Classless path.";
        return false;
    }
    auto itr = _archetypes.find(archetypeId);
    if (itr == _archetypes.end())
    {
        if (err) *err = "Unknown archetype.";
        return false;
    }

    Archetype const& arch = itr->second;
    uint32 learned = 0;
    for (uint32 firstSpell : arch.abilities)
        if (BuyAbility(player, firstSpell, nullptr))
            ++learned;

    uint32 talentsLearned = 0;
    for (auto const& [talentId, rank] : arch.talents)
        for (uint8 r = 0; r < rank; ++r)
            if (BuyTalentRank(player, talentId, nullptr))
                ++talentsLearned;

    if (!learned && !talentsLearned)
    {
        if (err) *err = "Nothing could be applied (not enough essence, or already known).";
        return false;
    }

    Msg(player, Acore::StringFormat("Archetype |cffffff00{}|r applied: {} abilities, {} talent ranks. "
        "AE left: |cff00ff00{}|r, TE left: |cff00ff00{}|r.",
        arch.name, learned, talentsLearned, st.abilityEssence, st.talentEssence));
    return true;
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

    st.cards.clear();
    st.bans.clear();
    st.pity = 0;
    CharacterDatabase.Execute("DELETE FROM cw_char_cards WHERE guid = {}", guid);
    CharacterDatabase.Execute("DELETE FROM cw_char_bans WHERE guid = {}", guid);

    st.mode = target;
    uint8 level = player->GetLevel();
    st.lastProcessedLevel = level;

    if (target == Mode::Classless)
    {
        uint32 levelsEarned = level >= cfg.essenceStartLevel ? uint32(level - cfg.essenceStartLevel + 1) : 0;
        st.abilityEssence = cfg.startingAbilityEssence + levelsEarned * cfg.abilityEssencePerLevel;
        st.talentEssence = levelsEarned * cfg.talentEssencePerLevel;
        SaveState(player);
        Msg(player, Acore::StringFormat("|cffff8800Rebirth complete.|r You walk the Classless path anew — "
            "AE: |cff00ff00{}|r, TE: |cff00ff00{}|r.", st.abilityEssence, st.talentEssence));
    }
    else
    {
        st.abilityEssence = 0;
        st.talentEssence = 0;
        SaveState(player);
        Msg(player, "|cffff8800Rebirth complete.|r The Wildcard takes your fate — rolling your Hero...");

        GrantGuard noReveal(_revealSuppress); // bulk regrant: no popup spam
        for (uint32 i = 0; i < cfg.wcStartingAbilities; ++i)
            RollAbility(player);

        // replay the roll schedule (and its earned rerolls) for every level gained
        for (uint8 lvl = cfg.wcRollStartLevel; lvl <= level; ++lvl)
        {
            uint32 offset = lvl - cfg.wcRollStartLevel;
            if (offset % cfg.wcTalentEveryLevels == 0)
            {
                RollTalent(player);
                st.talentRerolls += cfg.wcRerollsPerTalentRoll;
            }
            if (offset % cfg.wcAbilityEveryLevels == 0)
            {
                RollAbility(player);
                st.abilityRerolls += cfg.wcRerollsPerAbilityRoll;
            }
        }
        SaveState(player);
    }

    UpdateAbilityRanks(player);
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

    if (QueryResult result = CharacterDatabase.Query(
        "SELECT mode, ability_essence, talent_essence, pity, ability_rerolls, talent_rerolls, last_level, "
        "stat_str, stat_agi, stat_sta, stat_int, stat_spi, display_power FROM cw_char_state WHERE guid = {}", guid))
    {
        Field* f = result->Fetch();
        st.mode = Mode(f[0].Get<uint8>());
        st.abilityEssence = f[1].Get<uint32>();
        st.talentEssence = f[2].Get<uint32>();
        st.pity = f[3].Get<uint32>();
        st.abilityRerolls = f[4].Get<uint32>();
        st.talentRerolls = f[5].Get<uint32>();
        st.lastProcessedLevel = f[6].Get<uint8>();
        for (uint8 i = 0; i < 5; ++i)
            st.statAlloc[i] = f[7 + i].Get<uint32>();
        st.displayPower = f[12].Get<uint8>();
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
        "SELECT is_talent, entry, golden, used FROM cw_char_cards WHERE guid = {}", guid))
    {
        do
        {
            Field* f = result->Fetch();
            SkillCard card;
            card.isTalent = f[0].Get<bool>();
            card.entry = f[1].Get<uint32>();
            card.golden = f[2].Get<bool>();
            card.used = f[3].Get<bool>();
            st.cards.push_back(card);
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
        "REPLACE INTO cw_char_state (guid, mode, ability_essence, talent_essence, pity, ability_rerolls, talent_rerolls, last_level, "
        "stat_str, stat_agi, stat_sta, stat_int, stat_spi, display_power) VALUES ({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {})",
        player->GetGUID().GetCounter(), uint32(st.mode), st.abilityEssence, st.talentEssence, st.pity,
        st.abilityRerolls, st.talentRerolls, st.lastProcessedLevel,
        st.statAlloc[0], st.statAlloc[1], st.statAlloc[2], st.statAlloc[3], st.statAlloc[4],
        uint32(st.displayPower));
}

bool ClasslessMgr::SetDisplayPower(Player* player, uint8 powerIdx, std::string* err)
{
    if (!cfg.universalResources)
    {
        if (err) *err = "Universal resources are disabled on this realm.";
        return false;
    }
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

void ClasslessMgr::TeachProficiencies(Player* player)
{
    if (!cfg.teachProficiencies)
        return;

    GrantGuard guard(_applyingGrant);

    for (uint32 spellId : cfg.proficiencySpells)
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
    {
        GrantGuard guard(_applyingGrant);
        for (auto const& [firstSpell, e] : _abilities)
            for (uint32 rank : e.ranks)
                if (player->HasSpell(rank))
                    player->removeSpell(rank, SPEC_MASK_ALL, false);
    }

    // neutral Hero starter kit
    if (cfg.starterKitEnable)
    {
        // strip every piece of gear the shell class was created wearing, so
        // the Hero starts bare -- otherwise the kit armour finds the slots
        // occupied and falls through to the bags, leaving the default gear on
        if (cfg.starterKitStripEquipped)
            for (uint8 slot = EQUIPMENT_SLOT_START; slot < EQUIPMENT_SLOT_END; ++slot)
                if (player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))
                    player->DestroyItem(INVENTORY_SLOT_BAG_0, slot, true);

        // the basic armour (shirt/pants/boots) goes onto the character; the now
        // empty slots mean StoreNewItemInBestSlots equips it rather than bagging
        for (auto const& [itemId, count] : cfg.starterKitEquip)
            player->StoreNewItemInBestSlots(itemId, count);
        // weapons and consumables go into the bags, unequipped -- the Hero picks
        // up the neutral weapons from there when they want them
        for (auto const& [itemId, count] : cfg.starterKitItems)
            player->AddItem(itemId, count);
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
            Msg(player, "Welcome, Hero! You have no class. Every Hero shares the same |cffffff00chassis|r, so the "
                        "one you picked at creation changes nothing — you carry mana, rage and energy at once, every "
                        "stat is worth having, and every spell, talent, weapon and armor type in the game is open "
                        "to you.");
            Msg(player, "Speak to the |cffffff00Hero Advancement|r NPC (or use |cffffff00.classless mode|r / the "
                        "|cffffff00/cw|r addon) to choose your path: Classless free-pick or Wildcard random rolls.");
        }
        else
            AnnounceState(player);
    }
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

    // mode fallback once the choice window has passed
    if (st.mode == Mode::Unchosen && player->GetLevel() >= cfg.modeChoiceDeadline)
    {
        st.mode = Mode(cfg.defaultMode);
        if (st.mode == Mode::Wildcard)
        {
            GrantGuard noReveal(_revealSuppress);
            for (uint32 i = 0; i < cfg.wcStartingAbilities; ++i)
                RollAbility(player);
        }
    }

    TeachProficiencies(player);
    ApplyStatMods(player);

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
    uint8 newLevel = player->GetLevel();
    if (newLevel <= oldLevel && st.lastProcessedLevel >= newLevel)
        return;

    for (uint8 lvl = oldLevel + 1; lvl <= newLevel; ++lvl)
    {
        if (st.mode == Mode::Classless && lvl >= cfg.essenceStartLevel)
        {
            st.abilityEssence += cfg.abilityEssencePerLevel;
            st.talentEssence += cfg.talentEssencePerLevel;
        }
        else if (st.mode == Mode::Wildcard && lvl >= cfg.wcRollStartLevel)
        {
            uint32 offset = lvl - cfg.wcRollStartLevel;
            if (offset % cfg.wcTalentEveryLevels == 0)
            {
                RollTalent(player);
                st.talentRerolls += cfg.wcRerollsPerTalentRoll; // every roll comes with its reroll
            }
            if (offset % cfg.wcAbilityEveryLevels == 0)
            {
                RollAbility(player);
                st.abilityRerolls += cfg.wcRerollsPerAbilityRoll;
            }
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

    st.lastProcessedLevel = newLevel;
    UpdateAbilityRanks(player);
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
        Msg(player, "The Wildcard has been drawn! You received random starting abilities — reroll them freely at the "
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
            "Classless Hero — abilities: {}, talents: {}, AE: |cff00ff00{}|r, TE: |cff00ff00{}|r.",
            st.abilities.size(), st.talents.size(), st.abilityEssence, st.talentEssence));
    else if (st.mode == Mode::Wildcard)
        Msg(player, Acore::StringFormat(
            "Wildcard Hero — abilities: {}, talents: {}. Rerolls: |cff00ff00{}|r ability / |cff00ff00{}|r talent (earned as you level).",
            st.abilities.size(), st.talents.size(), st.abilityRerolls, st.talentRerolls));
}

// -------------------------------------------------------------------------
// Grant / remove internals
// -------------------------------------------------------------------------

void ClasslessMgr::GrantAbilityInternal(Player* player, AbilityEntry const& e, GrantSource source, bool persist)
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

    Msg(player, Acore::StringFormat("You gained the ability {}{}|r ({}).",
        RarityColor(e.rarity), SpellName(e.firstSpellId), RarityName(e.rarity)));
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
    st.talents[t.talentId] = newRank;

    if (persist)
        CharacterDatabase.Execute(
            "REPLACE INTO cw_char_talents (guid, talent_id, talent_rank) VALUES ({}, {}, {})",
            player->GetGUID().GetCounter(), t.talentId, newRank);

    Msg(player, Acore::StringFormat("Talent: {}{}|r rank {} ({}).",
        RarityColor(t.rarity), SpellName(t.rankSpells[newRank - 1]), newRank, RarityName(t.rarity)));
}

void ClasslessMgr::RemoveTalentInternal(Player* player, TalentPoolEntry const& t, bool persist)
{
    CharState& st = GetState(player);
    st.talents.erase(t.talentId);

    for (uint8 r = 0; r < t.maxRank; ++r)
        if (t.rankSpells[r] && player->HasSpell(t.rankSpells[r]))
            player->removeSpell(t.rankSpells[r], SPEC_MASK_ALL, false);

    if (persist)
        CharacterDatabase.Execute(
            "DELETE FROM cw_char_talents WHERE guid = {} AND talent_id = {}",
            player->GetGUID().GetCounter(), t.talentId);
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
            ? "Wildcard Heroes cannot pick abilities — the Wildcard picks for you (reroll what you dislike)."
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
        if (err) *err = "Unlearning is a Classless-path feature — Wildcard Heroes reroll instead.";
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

    RemoveAbilityInternal(player, *e);
    if (cfg.refundOnUnlearn)
        st.abilityEssence += AbilityCost(*e);
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
    return total;
}

bool ClasslessMgr::BuyTalentRank(Player* player, uint32 talentId, std::string* err)
{
    CharState& st = GetState(player);
    if (st.mode != Mode::Classless)
    {
        if (err) *err = st.mode == Mode::Wildcard
            ? "Wildcard Heroes cannot pick talents — the Wildcard picks for you."
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
    if (st.talentEssence < cfg.talentCostPerRank)
    {
        if (err) *err = Acore::StringFormat("Not enough Talent Essence ({} needed).", cfg.talentCostPerRank);
        return false;
    }
    if (t->dependsOn)
    {
        uint8 depRank = 0;
        if (auto itr = st.talents.find(t->dependsOn); itr != st.talents.end())
            depRank = itr->second;
        if (depRank < t->dependsOnRank + 1)
        {
            if (err) *err = "You are missing a prerequisite talent.";
            return false;
        }
    }
    if (cfg.enforceTalentRows && SpentTalentRanksInTab(st, t->tabId) < t->row * 5)
    {
        if (err) *err = Acore::StringFormat("You need {} points in this tree to unlock that tier.", t->row * 5);
        return false;
    }

    st.talentEssence -= cfg.talentCostPerRank;
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
    uint32 levelsEarned = level >= cfg.essenceStartLevel ? uint32(level - cfg.essenceStartLevel + 1) : 0;
    st.abilityEssence = cfg.startingAbilityEssence + levelsEarned * cfg.abilityEssencePerLevel;
    st.talentEssence = levelsEarned * cfg.talentEssencePerLevel;

    SaveState(player);
    Msg(player, Acore::StringFormat("Respec complete. AE: |cff00ff00{}|r, TE: |cff00ff00{}|r.",
        st.abilityEssence, st.talentEssence));
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
        "Stats allocated — STR +{}, AGI +{}, STA +{}, INT +{}, SPI +{} ({} of {} points).",
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

SkillCard* ClasslessMgr::FindUnusedCard(CharState& st, bool isTalent)
{
    for (SkillCard& card : st.cards)
        if (card.isTalent == isTalent && !card.used)
            return &card;
    return nullptr;
}

uint32 ClasslessMgr::RollAbility(Player* player, GrantSource source)
{
    CharState& st = GetState(player);
    ObjectGuid guid = player->GetGUID();
    TickBans(st, guid);

    // skill card guarantee first
    if (SkillCard* card = FindUnusedCard(st, false))
    {
        if (AbilityEntry const* e = GetAbility(card->entry); e && !st.abilities.count(e->firstSpellId))
        {
            card->used = true;
            CharacterDatabase.Execute(
                "UPDATE cw_char_cards SET used = 1 WHERE guid = {} AND is_talent = 0 AND entry = {}",
                guid.GetCounter(), card->entry);
            GrantAbilityInternal(player, *e, GrantSource::Card);
            Msg(player, "An Ability Card was consumed to guarantee that roll!");
            PushAddon(player, Acore::StringFormat("RV|A|{}|{}|2", e->firstSpellId, uint32(e->rarity)));
            return e->firstSpellId;
        }
    }

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
    for (auto const& [firstSpell, e] : _abilities)
    {
        if (!e.enabled || st.abilities.count(firstSpell) || IsBanned(st, false, firstSpell))
            continue;
        if (!e.name.empty() && ownedNames.count(e.name))
            continue;
        anyLevel.push_back(&e);
        if (!cfg.respectLevelReqs || e.rankLevels.empty() || e.rankLevels[0] <= player->GetLevel())
            candidates.push_back(&e);
    }
    if (candidates.empty())
        candidates = std::move(anyLevel);

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

    GrantAbilityInternal(player, *chosen, source);
    SaveState(player);
    PushAddon(player, Acore::StringFormat("RV|A|{}|{}|{}",
        chosen->firstSpellId, uint32(chosen->rarity), synergy ? 1 : 0));
    return chosen->firstSpellId;
}

uint32 ClasslessMgr::RollTalent(Player* player)
{
    CharState& st = GetState(player);
    ObjectGuid guid = player->GetGUID();
    TickBans(st, guid);

    // skill card guarantee first
    if (SkillCard* card = FindUnusedCard(st, true))
    {
        if (TalentPoolEntry const* t = GetTalent(card->entry))
        {
            uint8 ownedRank = 0;
            if (auto itr = st.talents.find(t->talentId); itr != st.talents.end())
                ownedRank = itr->second;
            if (ownedRank < t->maxRank)
            {
                card->used = true;
                CharacterDatabase.Execute(
                    "UPDATE cw_char_cards SET used = 1 WHERE guid = {} AND is_talent = 1 AND entry = {}",
                    guid.GetCounter(), card->entry);
                GrantTalentRankInternal(player, *t, ownedRank + 1);
                Msg(player, "A Talent Card was consumed to guarantee that roll!");
                PushAddon(player, Acore::StringFormat("RV|T|{}|{}|{}|{}|2",
                    t->talentId, t->rankSpells[0], uint32(t->rarity), uint32(ownedRank + 1)));
                return t->talentId;
            }
        }
    }

    uint32 ownedMask = OwnedClassMask(st);
    uint32 lastGranted = 0;

    // Ascension's upgrade rule: rolling into an owned talent upgrades it and rolls again.
    for (uint8 chain = 0; chain < 4; ++chain)
    {
        // tiered: a talent in tree row R unlocks at level 10 + R*5 (the level a
        // vanilla character could first reach that row); fall back to the full
        // pool if the level-legal one is exhausted
        std::vector<TalentPoolEntry const*> candidates;
        std::vector<TalentPoolEntry const*> anyLevel;
        candidates.reserve(_talents.size());
        for (auto const& [talentId, t] : _talents)
        {
            if (!t.enabled || IsBanned(st, true, talentId))
                continue;
            auto itr = st.talents.find(talentId);
            if (itr != st.talents.end() && itr->second >= t.maxRank)
                continue; // maxed out
            anyLevel.push_back(&t);
            if (!cfg.respectLevelReqs || player->GetLevel() >= 10 + t.row * 5)
                candidates.push_back(&t);
        }
        if (candidates.empty())
            candidates = std::move(anyLevel);

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

        uint8 ownedRank = 0;
        if (auto itr = st.talents.find(chosen->talentId); itr != st.talents.end())
            ownedRank = itr->second;

        GrantTalentRankInternal(player, *chosen, ownedRank + 1);
        lastGranted = chosen->talentId;
        PushAddon(player, Acore::StringFormat("RV|T|{}|{}|{}|{}|{}",
            chosen->talentId, chosen->rankSpells[0], uint32(chosen->rarity),
            uint32(ownedRank + 1), synergy ? 1 : 0));

        if (ownedRank == 0)
            break; // fresh talent — done

        // it was an upgrade: Ascension rules say the roll fires again
        Msg(player, "The talent upgraded — the Wildcard rolls again!");
    }

    SaveState(player);
    return lastGranted;
}

bool ClasslessMgr::Reroll(Player* player, bool isTalent, uint32 entry, std::string* err)
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

        if (!free)
        {
            if (st.talentRerolls > 0)
                --st.talentRerolls; // earned charge (granted with every talent roll)
            else if (player->HasItemCount(cfg.wcScrollTalentItemId, 1))
                player->DestroyItemCount(cfg.wcScrollTalentItemId, 1, true);
            else if (player->HasItemCount(cfg.wcScrollItemId, 1))
                player->DestroyItemCount(cfg.wcScrollItemId, 1, true);
            else
            {
                if (err) *err = "No talent rerolls left — you earn one with every talent the Wildcard deals you (or buy a Scroll of Fortune).";
                return false;
            }
        }

        uint8 refundRanks = itr->second;
        RemoveTalentInternal(player, *t);

        st.bans.push_back({ entry, true, int32(cfg.wcSynergyBanRolls) });
        SaveBans(player->GetGUID(), st);
        ++st.pity;

        for (uint8 i = 0; i < refundRanks; ++i)
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
            if (err) *err = "That ability is locked. Unlock it first (.wildcard lock).";
            return false;
        }

        if (!free)
        {
            if (st.abilityRerolls > 0)
                --st.abilityRerolls; // earned charge (granted with every ability roll)
            else if (player->HasItemCount(cfg.wcScrollItemId, 1))
                player->DestroyItemCount(cfg.wcScrollItemId, 1, true);
            else
            {
                if (err) *err = "No ability rerolls left — you earn one with every ability the Wildcard deals you (or buy a Scroll of Fortune).";
                return false;
            }
        }

        RemoveAbilityInternal(player, *e);

        st.bans.push_back({ e->firstSpellId, false, int32(cfg.wcSynergyBanRolls) });
        SaveBans(player->GetGUID(), st);
        ++st.pity;

        RollAbility(player);
    }

    SaveState(player);
    return true;
}

bool ClasslessMgr::ToggleLock(Player* player, uint32 firstSpellId, std::string* err)
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

    OwnedAbility& owned = st.abilities[e->firstSpellId];
    owned.locked = !owned.locked;
    CharacterDatabase.Execute(
        "UPDATE cw_char_abilities SET locked = {} WHERE guid = {} AND first_spell = {}",
        owned.locked ? 1 : 0, player->GetGUID().GetCounter(), e->firstSpellId);

    Msg(player, Acore::StringFormat("{} is now {}.", SpellName(e->firstSpellId),
        owned.locked ? "|cffffff00locked|r" : "unlocked"));
    return true;
}

bool ClasslessMgr::AddCard(Player* player, bool isTalent, uint32 entry, std::string* err)
{
    CharState& st = GetState(player);
    if (st.mode != Mode::Wildcard)
    {
        if (err) *err = "Skill Cards are a Wildcard mechanic.";
        return false;
    }
    if (player->GetLevel() >= 10)
    {
        if (err) *err = "Skill Cards can only be activated before level 10.";
        return false;
    }

    if (isTalent ? !GetTalent(entry) : !GetAbility(entry))
    {
        if (err) *err = isTalent ? "Unknown talent id." : "Unknown ability (use the first-rank spell id).";
        return false;
    }

    // slot budget: 0 base+golden means UNLIMITED (Season 9: "no skill card caps")
    uint32 slots = isTalent ? cfg.wcTalentCards + cfg.wcGoldenTalentCards
                            : cfg.wcAbilityCards + cfg.wcGoldenAbilityCards;
    uint32 active = 0;
    for (SkillCard const& card : st.cards)
    {
        if (card.isTalent != isTalent)
            continue;
        if (card.entry == entry)
        {
            if (err) *err = "That card is already active.";
            return false;
        }
        ++active;
    }
    if (slots && active >= slots)
    {
        if (err) *err = Acore::StringFormat("All {} card slots of that type are in use (remove one first).", slots);
        return false;
    }

    SkillCard card;
    card.entry = entry;
    card.isTalent = isTalent;
    card.golden = active >= (isTalent ? cfg.wcTalentCards : cfg.wcAbilityCards);
    st.cards.push_back(card);

    CharacterDatabase.Execute(
        "REPLACE INTO cw_char_cards (guid, is_talent, entry, golden, used) VALUES ({}, {}, {}, {}, 0)",
        player->GetGUID().GetCounter(), isTalent ? 1 : 0, entry, card.golden ? 1 : 0);

    Msg(player, Acore::StringFormat("{} Card activated: {}.",
        isTalent ? "Talent" : "Ability",
        SpellName(isTalent ? GetTalent(entry)->rankSpells[0] : entry)));
    return true;
}

bool ClasslessMgr::RemoveCard(Player* player, bool isTalent, uint32 entry, std::string* err)
{
    CharState& st = GetState(player);
    if (player->GetLevel() >= 10)
    {
        if (err) *err = "Skill Cards are locked in from level 10.";
        return false;
    }

    for (auto itr = st.cards.begin(); itr != st.cards.end(); ++itr)
    {
        if (itr->isTalent == isTalent && itr->entry == entry && !itr->used)
        {
            st.cards.erase(itr);
            CharacterDatabase.Execute(
                "DELETE FROM cw_char_cards WHERE guid = {} AND is_talent = {} AND entry = {}",
                player->GetGUID().GetCounter(), isTalent ? 1 : 0, entry);
            Msg(player, "Card removed.");
            return true;
        }
    }

    if (err) *err = "No such active card.";
    return false;
}
