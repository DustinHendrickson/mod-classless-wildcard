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
 *
 * Classless gear as world drops.
 *
 * The whole catalogue was vendor-only, which made the Hero Advancement NPC the
 * single answer to "where does gear come from". Killing things in the world now
 * has a chance to drop the same items, banded to the level the mob is worth --
 * so a level 20 zone yields level 20 gear whoever kills there, the way ordinary
 * WoW loot behaves.
 *
 * This is deliberately NOT done with creature_loot_template rows. That would
 * mean writing into a core table for thousands of creatures, could never reach
 * the many mobs whose lootid is 0 (they have no loot template to add to), and
 * would be unpleasant to reverse. Adding to the Loot object at kill time costs
 * no world data at all.
 */

#include "ClasslessMgr.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "Log.h"
#include "LootMgr.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "Random.h"
#include "ScriptMgr.h"
#include <algorithm>
#include <vector>

using namespace ClasslessWildcard;

namespace
{
    // Every entry the module's item packs own. Read from item_template rather
    // than hardcoded, so adding gear to the SQL packs adds it to the drop pool
    // with no code change.
    constexpr uint32 CW_ITEM_LO = 990200;
    constexpr uint32 CW_ITEM_HI = 990999;
    constexpr uint32 HEIRLOOM_QUALITY = 7;

    // How far below a mob's level a piece may sit and still drop from it. The
    // gear comes in bands ten levels apart, so this means "the band at or just
    // under this mob", never gear from further down than that.
    constexpr uint8 LEVEL_WINDOW = 10;

    struct DropItem
    {
        uint32 entry = 0;
        uint8  reqLevel = 0;
    };

    std::vector<DropItem> g_gear;       // ordinary pieces, from any mob
    std::vector<DropItem> g_heirlooms;  // rare and boss kills only
    bool g_loaded = false;

    void LoadPool()
    {
        g_gear.clear();
        g_heirlooms.clear();
        g_loaded = true;

        QueryResult result = WorldDatabase.Query(
            "SELECT entry, RequiredLevel, Quality FROM item_template "
            "WHERE entry BETWEEN {} AND {}", CW_ITEM_LO, CW_ITEM_HI);
        if (!result)
        {
            LOG_INFO("module.classless",
                     "mod-classless-wildcard: no classless items found, world drops will not fire");
            return;
        }

        do
        {
            Field* f = result->Fetch();
            DropItem it;
            it.entry = f[0].Get<uint32>();
            it.reqLevel = uint8(std::min<uint32>(f[1].Get<uint32>(), 80));
            if (f[2].Get<uint32>() == HEIRLOOM_QUALITY)
                g_heirlooms.push_back(it);
            else
                g_gear.push_back(it);
        } while (result->NextRow());

        LOG_INFO("module.classless",
                 "mod-classless-wildcard: world drop pool -- {} gear pieces, {} heirlooms",
                 g_gear.size(), g_heirlooms.size());
    }

    // A piece suited to this mob's level: at or below it, and no more than one
    // band beneath. Falls back to the highest band the mob clears, so a mob
    // below the lowest band still has something to give.
    uint32 PickForLevel(std::vector<DropItem> const& pool, uint8 level)
    {
        if (pool.empty())
            return 0;

        std::vector<uint32> eligible;
        for (DropItem const& it : pool)
            if (it.reqLevel <= level && it.reqLevel + LEVEL_WINDOW > level)
                eligible.push_back(it.entry);

        if (eligible.empty())
        {
            uint8 best = 0;
            for (DropItem const& it : pool)
                if (it.reqLevel <= level)
                    best = std::max(best, it.reqLevel);
            for (DropItem const& it : pool)
                if (it.reqLevel == best)
                    eligible.push_back(it.entry);
        }

        if (eligible.empty())
            return 0;
        return eligible[urand(0, uint32(eligible.size() - 1))];
    }

    bool IsRareOrBoss(Creature* creature)
    {
        switch (creature->GetCreatureTemplate()->rank)
        {
            case CREATURE_ELITE_RARE:
            case CREATURE_ELITE_RAREELITE:
            case CREATURE_ELITE_WORLDBOSS:
                return true;
            default:
                return false;
        }
    }

    // Things that die without being "a mob you killed": critters, totems, and
    // anything somebody summoned. Without this every Deviate Guppy and every
    // expired water elemental is a lottery ticket.
    bool IsValidDropSource(Creature* creature)
    {
        if (creature->IsCritter() || creature->IsTotem() || creature->IsPet() || creature->IsSummon())
            return false;
        if (creature->GetCreatureTemplate()->type == CREATURE_TYPE_CRITTER)
            return false;
        return true;
    }

    void TryWorldDrop(Player* killer, Creature* killed)
    {
        if (!killer || !killed)
            return;

        Config const& cfg = sClasslessMgr->cfg;
        if (!cfg.enabled || !cfg.worldDropEnable)
            return;
        // Exempt accounts (bots, system) play by vanilla rules; handing them
        // classless gear would only churn loot they have no use for.
        if (sClasslessMgr->IsExempt(killer))
            return;
        if (!IsValidDropSource(killed))
            return;

        if (!g_loaded)
            LoadPool();

        bool rareOrBoss = IsRareOrBoss(killed);

        // Heirlooms are the premium reward, so they come only off rares and
        // bosses, and are rolled first as the better prize. They carry
        // RequiredLevel 1 because they scale, so level plays no part here.
        uint32 itemId = 0;
        if (rareOrBoss && cfg.worldDropHeirloomChance > 0.0f &&
            roll_chance_f(cfg.worldDropHeirloomChance))
            itemId = PickForLevel(g_heirlooms, 80);

        if (!itemId)
        {
            float chance = cfg.worldDropChance;
            if (rareOrBoss)
                chance *= cfg.worldDropRareMultiplier;
            if (chance <= 0.0f || !roll_chance_f(chance))
                return;
            itemId = PickForLevel(g_gear, killed->GetLevel());
        }

        if (!itemId)
            return;

        Loot& loot = killed->loot;
        // Whether the corpse is lootable at all was decided in Unit::Kill
        // BEFORE this hook runs, from the loot it held at that moment. A mob
        // that rolled nothing else is already flagged unlootable, so adding an
        // item without re-flagging would drop it into a corpse nobody can open.
        bool wasEmpty = loot.isLooted();

        loot.AddItem(LootStoreItem(itemId, 0, 100.0f, false, LOOT_MODE_DEFAULT, 0, 1, 1));

        if (wasEmpty && !loot.isLooted())
            killed->SetDynamicFlag(UNIT_DYNFLAG_LOOTABLE);
    }
}

class ClasslessLootScript : public PlayerScript
{
public:
    ClasslessLootScript() : PlayerScript("ClasslessLootScript", {
        PLAYERHOOK_ON_CREATURE_KILL,
        PLAYERHOOK_ON_CREATURE_KILLED_BY_PET
    }) { }

    void OnPlayerCreatureKill(Player* killer, Creature* killed) override
    {
        TryWorldDrop(killer, killed);
    }

    // A pet or totem landing the killing blow routes here instead of
    // OnPlayerCreatureKill, so hunters and warlocks are not quietly excluded.
    // Unit::Kill fires exactly one of the two, so this cannot double up.
    void OnPlayerCreatureKilledByPet(Player* owner, Creature* killed) override
    {
        TryWorldDrop(owner, killed);
    }
};

void AddClasslessLootScripts()
{
    new ClasslessLootScript();
}
