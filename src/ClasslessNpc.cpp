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
 * "Hero Advancement" NPC — the gossip stand-in for Ascension's
 * Character Advancement Panel.
 */

#include "Chat.h"
#include "ClasslessMgr.h"
#include "ClasslessVendorLists.h"
#include "Creature.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "ScriptedGossip.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "StringFormat.h"
#include "WorldSession.h"
#include <algorithm>
#include <iterator>

using namespace ClasslessWildcard;

namespace
{
    constexpr uint32 PAGE_SIZE = 12;

    // action encoding: <section base> + payload
    enum Actions : uint32
    {
        ACT_MAIN              = 1,
        ACT_MODE_CLASSLESS    = 2,
        ACT_MODE_WILDCARD     = 3,
        ACT_BROWSE_CLASSES    = 10,
        ACT_BROWSE_TALENTS    = 20,
        ACT_MY_ABILITIES      = 30,
        ACT_MY_TALENTS        = 31,
        ACT_RESPEC            = 40,
        ACT_RESPEC_CONFIRM    = 41,
        ACT_VENDOR            = 70,
        ACT_VENDOR_SUPPLIES   = 71,
        ACT_ARCHETYPES        = 80,
        ACT_REBIRTH           = 90,
        ACT_REBIRTH_CLASSLESS = 91,
        ACT_REBIRTH_WILDCARD  = 92,
        BASE_VENDOR_CATEGORY  = 100,   // + index into VENDOR_CATEGORIES
        BASE_VENDOR_LIST      = 200,   // + index into VENDOR_LISTS
        BASE_ARCHETYPE        = 90000, // + archetypeId (keep below BASE_CLASS_PAGE)

        BASE_CLASS_PAGE       = 100000000, // + classId * 100000 + page
        BASE_LEARN_ABILITY    = 200000000, // + firstSpellId
        BASE_ABILITY_ACTION   = 300000000, // + firstSpellId (classless: unlearn / wildcard: reroll)
        BASE_TALENT_TAB       = 400000000, // + tabId * 1000 + page
        BASE_LEARN_TALENT     = 500000000, // + talentId
        BASE_MY_ABILITIES_PG  = 600000000, // + page
        BASE_LOCK_ABILITY     = 700000000, // + firstSpellId
        BASE_REROLL_TALENT    = 800000000, // + talentId
        BASE_MY_TALENTS_PG    = 900000000  // + page
    };

    char const* ClassNameById(uint8 classId)
    {
        switch (classId)
        {
            case CLASS_WARRIOR: return "Warrior";
            case CLASS_PALADIN: return "Paladin";
            case CLASS_HUNTER:  return "Hunter";
            case CLASS_ROGUE:   return "Rogue";
            case CLASS_PRIEST:  return "Priest";
            case CLASS_DEATH_KNIGHT: return "Death Knight";
            case CLASS_SHAMAN:  return "Shaman";
            case CLASS_MAGE:    return "Mage";
            case CLASS_WARLOCK: return "Warlock";
            case CLASS_DRUID:   return "Druid";
            default:            return "Unknown";
        }
    }

    std::string SpellNameOf(uint32 spellId)
    {
        if (SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId))
            if (info->SpellName[0])
                return info->SpellName[0];
        return Acore::StringFormat("Spell {}", spellId);
    }

    void ShowMain(Player* player, Creature* creature)
    {
        ClearGossipMenuFor(player);
        CharState& st = sClasslessMgr->GetState(player);
        Config const& cfg = sClasslessMgr->cfg;

        if (st.mode == Mode::Unchosen)
        {
            AddGossipItemFor(player, GOSSIP_ICON_TRAINER, "|cff00ccffChoose the Classless path|r (pick every ability yourself)", GOSSIP_SENDER_MAIN, ACT_MODE_CLASSLESS);
            AddGossipItemFor(player, GOSSIP_ICON_BATTLE, "|cffff8800Choose the Wildcard path|r (random abilities, reroll what you dislike)", GOSSIP_SENDER_MAIN, ACT_MODE_WILDCARD);
        }
        else if (st.mode == Mode::Classless)
        {
            AddGossipItemFor(player, GOSSIP_ICON_TRAINER, Acore::StringFormat("Browse abilities by class  |cff00ff00[{} AE]|r", st.abilityEssence), GOSSIP_SENDER_MAIN, ACT_BROWSE_CLASSES);
            AddGossipItemFor(player, GOSSIP_ICON_TRAINER, Acore::StringFormat("Browse talents  |cff00ff00[{} TE]|r", st.talentEssence), GOSSIP_SENDER_MAIN, ACT_BROWSE_TALENTS);
            // The old "learn by spell ID" entries are gone: a coded gossip
            // option opens the client's generic ENTER_CODE popup, which ignores
            // the prompt we set and expects a raw spell id nobody has to hand.
            // Browsing by class does the same job by clicking, and
            // ".classless learn <id>" still covers entering one directly.
            AddGossipItemFor(player, GOSSIP_ICON_INTERACT_1, "My abilities (unlearn)", GOSSIP_SENDER_MAIN, BASE_MY_ABILITIES_PG);
            if (!sClasslessMgr->Archetypes().empty())
                AddGossipItemFor(player, GOSSIP_ICON_TABARD, "Apply a starter archetype...", GOSSIP_SENDER_MAIN, ACT_ARCHETYPES);
            AddGossipItemFor(player, GOSSIP_ICON_MONEY_BAG, Acore::StringFormat("Respec everything ({} gold)", cfg.respecCostGold), GOSSIP_SENDER_MAIN, ACT_RESPEC);
        }
        else // Wildcard
        {
            AddGossipItemFor(player, GOSSIP_ICON_BATTLE, "My rolled abilities (reroll / lock)", GOSSIP_SENDER_MAIN, BASE_MY_ABILITIES_PG);
            AddGossipItemFor(player, GOSSIP_ICON_BATTLE, "My rolled talents (reroll)", GOSSIP_SENDER_MAIN, BASE_MY_TALENTS_PG);
        }

        // The vendor is for EVERY Hero, not just Wildcard ones: it carries the
        // classless gear packs and the heirlooms as well as the Reroll Scrolls,
        // and a Classless Hero could not reach any of it before.
        if (st.mode != Mode::Unchosen)
            AddGossipItemFor(player, GOSSIP_ICON_VENDOR, "Browse the Hero's wares (gear, heirlooms, Reroll Scrolls)...",
                             GOSSIP_SENDER_MAIN, ACT_VENDOR);

        if (st.mode != Mode::Unchosen && cfg.rebirthEnable)
            AddGossipItemFor(player, GOSSIP_ICON_BATTLE,
                Acore::StringFormat("|cffff4444Rebirth|r — full reset / switch path ({} gold)", cfg.rebirthCostGold),
                GOSSIP_SENDER_MAIN, ACT_REBIRTH);

        SendGossipMenuFor(player, DEFAULT_GOSSIP_MESSAGE, creature->GetGUID());
    }

    // --- the shop -----------------------------------------------------------
    //
    // 250 items cannot go in one vendor packet: SMSG_LIST_INVENTORY stops at
    // MAX_VENDOR_ITEMS = 150 and the core drops the rest without a word. They
    // are split into per-category, per-level-bracket lists in
    // cw_world_vendor_lists.sql, and SendListInventory(guid, vendorEntry) opens
    // any one of them from this single NPC. ClasslessVendorLists.h is generated
    // alongside that SQL, so the menu below always matches what is on the shelf.

    uint32 CategoryTotal(uint8 category)
    {
        for (VendorList const& l : VENDOR_LISTS)
            if (l.category == category && l.whole)
                return l.count;
        return 0;
    }

    uint32 ListsInCategory(uint8 category)
    {
        uint32 n = 0;
        for (VendorList const& l : VENDOR_LISTS)
            if (l.category == category)
                ++n;
        return n;
    }

    // The list holding the whole category, for the ones that do not bracket.
    uint32 CategoryEntry(uint8 category)
    {
        for (VendorList const& l : VENDOR_LISTS)
            if (l.category == category && l.whole)
                return l.entry;
        return 0;
    }

    void OpenVendorList(Player* player, Creature* creature, uint32 vendorEntry)
    {
        // Leaves the gossip window for the vendor frame, as any vendor does.
        player->GetSession()->SendListInventory(creature->GetGUID(), vendorEntry);
    }

    void ShowVendorMenu(Player* player, Creature* creature)
    {
        ClearGossipMenuFor(player);
        for (uint8 c = 0; c < uint8(std::size(VENDOR_CATEGORIES)); ++c)
            AddGossipItemFor(player, GOSSIP_ICON_VENDOR,
                Acore::StringFormat("{}  |cff888888— {} ({} items)|r",
                    VENDOR_CATEGORIES[c].name, VENDOR_CATEGORIES[c].blurb, CategoryTotal(c)),
                GOSSIP_SENDER_MAIN, BASE_VENDOR_CATEGORY + c);

        AddGossipItemFor(player, GOSSIP_ICON_MONEY_BAG, "Supplies  |cff888888— Reroll Scrolls|r",
                         GOSSIP_SENDER_MAIN, ACT_VENDOR_SUPPLIES);
        AddGossipItemFor(player, GOSSIP_ICON_TALK, "<- Back", GOSSIP_SENDER_MAIN, ACT_MAIN);
        SendGossipMenuFor(player, DEFAULT_GOSSIP_MESSAGE, creature->GetGUID());
    }

    void ShowVendorCategory(Player* player, Creature* creature, uint8 category)
    {
        ClearGossipMenuFor(player);
        for (uint32 i = 0; i < std::size(VENDOR_LISTS); ++i)
        {
            VendorList const& l = VENDOR_LISTS[i];
            if (l.category != category || !l.count)
                continue;
            AddGossipItemFor(player, l.whole ? GOSSIP_ICON_MONEY_BAG : GOSSIP_ICON_VENDOR,
                Acore::StringFormat("{}  |cff888888({} items)|r", l.label, l.count),
                GOSSIP_SENDER_MAIN, BASE_VENDOR_LIST + i);
        }
        AddGossipItemFor(player, GOSSIP_ICON_TALK, "<- Back to the wares", GOSSIP_SENDER_MAIN, ACT_VENDOR);
        SendGossipMenuFor(player, DEFAULT_GOSSIP_MESSAGE, creature->GetGUID());
    }

    void ShowArchetypes(Player* player, Creature* creature)
    {
        ClearGossipMenuFor(player);
        uint32 following = sClasslessMgr->GetState(player).archetype;
        for (auto const& [id, arch] : sClasslessMgr->Archetypes())
        {
            uint32 ranks = 0;
            for (auto const& [talentId, rank] : arch.talents)
                ranks += rank;
            AddGossipItemFor(player, GOSSIP_ICON_TABARD,
                Acore::StringFormat("{}|cffffff00{}|r: {} ({} abilities, {} talent ranks, level 1 to 80)",
                    following == id ? "[following] " : "", arch.name, arch.description,
                    uint32(arch.abilities.size()), ranks),
                GOSSIP_SENDER_MAIN, BASE_ARCHETYPE + id,
                Acore::StringFormat("Follow the {} archetype? It replaces your build: abilities are unlearned and refunded, "
                    "and if you own talents the respec fee applies. Its abilities and talents are then bought for you "
                    "as you level.", arch.name), 0, false);
        }
        if (following)
            AddGossipItemFor(player, GOSSIP_ICON_TALK, "Stop following my archetype", GOSSIP_SENDER_MAIN, BASE_ARCHETYPE);
        AddGossipItemFor(player, GOSSIP_ICON_TALK, "<- Back", GOSSIP_SENDER_MAIN, ACT_MAIN);
        SendGossipMenuFor(player, DEFAULT_GOSSIP_MESSAGE, creature->GetGUID());
    }

    void ShowClassList(Player* player, Creature* creature)
    {
        ClearGossipMenuFor(player);
        for (uint8 classId = CLASS_WARRIOR; classId <= CLASS_DRUID; ++classId)
        {
            if (classId == 10) // no class 10
                continue;
            if (classId == CLASS_DEATH_KNIGHT && !sClasslessMgr->cfg.includeDeathKnight)
                continue;
            AddGossipItemFor(player, GOSSIP_ICON_TRAINER, ClassNameById(classId), GOSSIP_SENDER_MAIN,
                BASE_CLASS_PAGE + uint32(classId) * 100000);
        }
        AddGossipItemFor(player, GOSSIP_ICON_TALK, "<- Back", GOSSIP_SENDER_MAIN, ACT_MAIN);
        SendGossipMenuFor(player, DEFAULT_GOSSIP_MESSAGE, creature->GetGUID());
    }

    void ShowClassAbilities(Player* player, Creature* creature, uint8 classId, uint32 page)
    {
        ClearGossipMenuFor(player);
        CharState& st = sClasslessMgr->GetState(player);
        uint32 classMask = 1u << (classId - 1);

        std::vector<AbilityEntry const*> list;
        for (auto const& [firstSpell, e] : sClasslessMgr->Abilities())
            if (e.enabled && (e.classMask & classMask) && !st.abilities.count(firstSpell)
                && (!e.variant || sClasslessMgr->cfg.elementalShowInBrowser))
                list.push_back(&e);

        uint32 start = page * PAGE_SIZE;
        for (uint32 i = start; i < list.size() && i < start + PAGE_SIZE; ++i)
        {
            AbilityEntry const* e = list[i];
            AddGossipItemFor(player, GOSSIP_ICON_TRAINER,
                Acore::StringFormat("{}{}|r  [{} AE]{}", RarityColor(e->rarity), SpellNameOf(e->firstSpellId),
                    sClasslessMgr->AbilityCost(*e), e->passive ? " (passive)" : ""),
                GOSSIP_SENDER_MAIN, BASE_LEARN_ABILITY + e->firstSpellId);
        }

        if (start + PAGE_SIZE < list.size())
            AddGossipItemFor(player, GOSSIP_ICON_CHAT, "Next page ->", GOSSIP_SENDER_MAIN,
                BASE_CLASS_PAGE + uint32(classId) * 100000 + page + 1);
        if (page > 0)
            AddGossipItemFor(player, GOSSIP_ICON_CHAT, "<- Previous page", GOSSIP_SENDER_MAIN,
                BASE_CLASS_PAGE + uint32(classId) * 100000 + page - 1);
        AddGossipItemFor(player, GOSSIP_ICON_TALK, "<- Back to classes", GOSSIP_SENDER_MAIN, ACT_BROWSE_CLASSES);
        SendGossipMenuFor(player, DEFAULT_GOSSIP_MESSAGE, creature->GetGUID());
    }

    void ShowTalentTabs(Player* player, Creature* creature)
    {
        ClearGossipMenuFor(player);

        // collect distinct tabs from the pool
        std::map<uint32, std::pair<uint32, uint32>> tabs; // tabId -> (classMask, tabpage-ish count)
        for (auto const& [talentId, t] : sClasslessMgr->Talents())
            tabs[t.tabId].first = t.classMask;

        for (auto const& [tabId, info] : tabs)
        {
            uint8 classId = 1;
            for (uint8 c = 1; c <= 11; ++c)
                if (info.first & (1u << (c - 1))) { classId = c; break; }
            AddGossipItemFor(player, GOSSIP_ICON_TRAINER,
                Acore::StringFormat("{} tree #{}", ClassNameById(classId), tabId),
                GOSSIP_SENDER_MAIN, BASE_TALENT_TAB + tabId * 1000);
        }
        AddGossipItemFor(player, GOSSIP_ICON_TALK, "<- Back", GOSSIP_SENDER_MAIN, ACT_MAIN);
        SendGossipMenuFor(player, DEFAULT_GOSSIP_MESSAGE, creature->GetGUID());
    }

    void ShowTalentTab(Player* player, Creature* creature, uint32 tabId, uint32 page)
    {
        ClearGossipMenuFor(player);
        CharState& st = sClasslessMgr->GetState(player);

        std::vector<TalentPoolEntry const*> list;
        for (auto const& [talentId, t] : sClasslessMgr->Talents())
            if (t.enabled && t.tabId == tabId)
                list.push_back(&t);
        std::sort(list.begin(), list.end(), [](auto a, auto b)
        {
            return a->row != b->row ? a->row < b->row : a->col < b->col;
        });

        uint32 start = page * PAGE_SIZE;
        for (uint32 i = start; i < list.size() && i < start + PAGE_SIZE; ++i)
        {
            TalentPoolEntry const* t = list[i];
            uint8 owned = 0;
            if (auto itr = st.talents.find(t->talentId); itr != st.talents.end())
                owned = itr->second;
            AddGossipItemFor(player, GOSSIP_ICON_TRAINER,
                Acore::StringFormat("{}{}|r  [{}/{}] row {}  [{} TE]", RarityColor(t->rarity),
                    SpellNameOf(t->rankSpells[0]), owned, t->maxRank, t->row + 1, sClasslessMgr->cfg.talentCostPerRank),
                GOSSIP_SENDER_MAIN, BASE_LEARN_TALENT + t->talentId);
        }

        if (start + PAGE_SIZE < list.size())
            AddGossipItemFor(player, GOSSIP_ICON_CHAT, "Next page ->", GOSSIP_SENDER_MAIN, BASE_TALENT_TAB + tabId * 1000 + page + 1);
        if (page > 0)
            AddGossipItemFor(player, GOSSIP_ICON_CHAT, "<- Previous page", GOSSIP_SENDER_MAIN, BASE_TALENT_TAB + tabId * 1000 + page - 1);
        AddGossipItemFor(player, GOSSIP_ICON_TALK, "<- Back to trees", GOSSIP_SENDER_MAIN, ACT_BROWSE_TALENTS);
        SendGossipMenuFor(player, DEFAULT_GOSSIP_MESSAGE, creature->GetGUID());
    }

    void ShowMyAbilities(Player* player, Creature* creature, uint32 page)
    {
        ClearGossipMenuFor(player);
        CharState& st = sClasslessMgr->GetState(player);
        bool wildcard = st.mode == Mode::Wildcard;

        std::vector<uint32> owned;
        for (auto const& [firstSpell, o] : st.abilities)
            owned.push_back(firstSpell);
        std::sort(owned.begin(), owned.end());

        uint32 start = page * PAGE_SIZE;
        for (uint32 i = start; i < owned.size() && i < start + PAGE_SIZE; ++i)
        {
            uint32 firstSpell = owned[i];
            AbilityEntry const* e = sClasslessMgr->GetAbility(firstSpell);
            bool locked = st.abilities[firstSpell].locked;
            std::string label = Acore::StringFormat("{}{}|r{}", e ? RarityColor(e->rarity) : "|cffffffff",
                SpellNameOf(firstSpell), locked ? " |cffffff00[locked]|r" : "");

            if (wildcard)
            {
                AddGossipItemFor(player, GOSSIP_ICON_BATTLE, Acore::StringFormat("Reroll: {}", label),
                    GOSSIP_SENDER_MAIN, BASE_ABILITY_ACTION + firstSpell,
                    "Reroll this ability? (Consumes a Reroll Scroll from level 10.)", 0, false);
                AddGossipItemFor(player, GOSSIP_ICON_INTERACT_1, Acore::StringFormat("{}: {}", locked ? "Unlock" : "Lock", label),
                    GOSSIP_SENDER_MAIN, BASE_LOCK_ABILITY + firstSpell);
            }
            else
                AddGossipItemFor(player, GOSSIP_ICON_MONEY_BAG, Acore::StringFormat("Unlearn: {}", label),
                    GOSSIP_SENDER_MAIN, BASE_ABILITY_ACTION + firstSpell,
                    "Unlearn this ability and refund its essence?", 0, false);
        }

        if (start + PAGE_SIZE < owned.size())
            AddGossipItemFor(player, GOSSIP_ICON_CHAT, "Next page ->", GOSSIP_SENDER_MAIN, BASE_MY_ABILITIES_PG + page + 1);
        if (page > 0)
            AddGossipItemFor(player, GOSSIP_ICON_CHAT, "<- Previous page", GOSSIP_SENDER_MAIN, BASE_MY_ABILITIES_PG + page - 1);
        AddGossipItemFor(player, GOSSIP_ICON_TALK, "<- Back", GOSSIP_SENDER_MAIN, ACT_MAIN);
        SendGossipMenuFor(player, DEFAULT_GOSSIP_MESSAGE, creature->GetGUID());
    }

    void ShowMyTalents(Player* player, Creature* creature, uint32 page)
    {
        ClearGossipMenuFor(player);
        CharState& st = sClasslessMgr->GetState(player);

        std::vector<std::pair<uint32, uint8>> owned(st.talents.begin(), st.talents.end());
        std::sort(owned.begin(), owned.end());

        uint32 start = page * PAGE_SIZE;
        for (uint32 i = start; i < owned.size() && i < start + PAGE_SIZE; ++i)
        {
            auto const& [talentId, rank] = owned[i];
            TalentPoolEntry const* t = sClasslessMgr->GetTalent(talentId);
            if (!t)
                continue;
            AddGossipItemFor(player, GOSSIP_ICON_BATTLE,
                Acore::StringFormat("Reroll: {}{}|r [{}/{}]", RarityColor(t->rarity), SpellNameOf(t->rankSpells[0]), rank, t->maxRank),
                GOSSIP_SENDER_MAIN, BASE_REROLL_TALENT + talentId,
                "Reroll this talent? Its ranks are rolled into new random talents. (Consumes a Scroll from level 10.)", 0, false);
        }

        if (start + PAGE_SIZE < owned.size())
            AddGossipItemFor(player, GOSSIP_ICON_CHAT, "Next page ->", GOSSIP_SENDER_MAIN, BASE_MY_TALENTS_PG + page + 1);
        if (page > 0)
            AddGossipItemFor(player, GOSSIP_ICON_CHAT, "<- Previous page", GOSSIP_SENDER_MAIN, BASE_MY_TALENTS_PG + page - 1);
        AddGossipItemFor(player, GOSSIP_ICON_TALK, "<- Back", GOSSIP_SENDER_MAIN, ACT_MAIN);
        SendGossipMenuFor(player, DEFAULT_GOSSIP_MESSAGE, creature->GetGUID());
    }

}

class npc_hero_advancement : public CreatureScript
{
public:
    npc_hero_advancement() : CreatureScript("npc_hero_advancement") { }

    bool OnGossipHello(Player* player, Creature* creature) override
    {
        if (!sClasslessMgr->cfg.enabled)
            return false;
        ShowMain(player, creature);
        return true;
    }

    bool OnGossipSelect(Player* player, Creature* creature, uint32 /*sender*/, uint32 action) override
    {
        std::string err;

        if (action >= BASE_MY_TALENTS_PG)
            ShowMyTalents(player, creature, action - BASE_MY_TALENTS_PG);
        else if (action >= BASE_REROLL_TALENT)
        {
            if (!sClasslessMgr->Reroll(player, true, action - BASE_REROLL_TALENT, &err) && !err.empty())
                ChatHandler(player->GetSession()).SendSysMessage(err);
            ShowMyTalents(player, creature, 0);
        }
        else if (action >= BASE_LOCK_ABILITY)
        {
            sClasslessMgr->ToggleLock(player, action - BASE_LOCK_ABILITY, &err);
            ShowMyAbilities(player, creature, 0);
        }
        else if (action >= BASE_MY_ABILITIES_PG)
            ShowMyAbilities(player, creature, action - BASE_MY_ABILITIES_PG);
        else if (action >= BASE_LEARN_TALENT)
        {
            if (!sClasslessMgr->BuyTalentRank(player, action - BASE_LEARN_TALENT, &err) && !err.empty())
                ChatHandler(player->GetSession()).SendSysMessage(err);
            // stay on the same tab
            if (TalentPoolEntry const* t = sClasslessMgr->GetTalent(action - BASE_LEARN_TALENT))
                ShowTalentTab(player, creature, t->tabId, 0);
            else
                ShowTalentTabs(player, creature);
        }
        else if (action >= BASE_TALENT_TAB)
        {
            uint32 payload = action - BASE_TALENT_TAB;
            ShowTalentTab(player, creature, payload / 1000, payload % 1000);
        }
        else if (action >= BASE_ABILITY_ACTION)
        {
            uint32 firstSpell = action - BASE_ABILITY_ACTION;
            if (sClasslessMgr->GetState(player).mode == Mode::Wildcard)
            {
                if (!sClasslessMgr->Reroll(player, false, firstSpell, &err) && !err.empty())
                    ChatHandler(player->GetSession()).SendSysMessage(err);
            }
            else if (!sClasslessMgr->UnlearnAbility(player, firstSpell, &err) && !err.empty())
                ChatHandler(player->GetSession()).SendSysMessage(err);
            ShowMyAbilities(player, creature, 0);
        }
        else if (action >= BASE_LEARN_ABILITY)
        {
            if (!sClasslessMgr->BuyAbility(player, action - BASE_LEARN_ABILITY, &err) && !err.empty())
                ChatHandler(player->GetSession()).SendSysMessage(err);
            ShowMain(player, creature);
        }
        else if (action >= BASE_CLASS_PAGE)
        {
            uint32 payload = action - BASE_CLASS_PAGE;
            ShowClassAbilities(player, creature, uint8(payload / 100000), payload % 100000);
        }
        else if (action >= BASE_ARCHETYPE)
        {
            if (!sClasslessMgr->ApplyArchetype(player, action - BASE_ARCHETYPE, &err) && !err.empty())
                ChatHandler(player->GetSession()).SendSysMessage(err);
            ShowMain(player, creature);
        }
        else if (action >= BASE_VENDOR_LIST && action < BASE_VENDOR_LIST + std::size(VENDOR_LISTS))
            OpenVendorList(player, creature, VENDOR_LISTS[action - BASE_VENDOR_LIST].entry);
        else if (action >= BASE_VENDOR_CATEGORY && action < BASE_VENDOR_CATEGORY + std::size(VENDOR_CATEGORIES))
        {
            uint8 category = uint8(action - BASE_VENDOR_CATEGORY);
            // A category with nothing to choose between (heirlooms do not
            // bracket by level, since they scale) opens straight to its shelf.
            if (ListsInCategory(category) == 1)
                OpenVendorList(player, creature, CategoryEntry(category));
            else
                ShowVendorCategory(player, creature, category);
        }
        else switch (action)
        {
            case ACT_MODE_CLASSLESS:
                sClasslessMgr->SetMode(player, Mode::Classless, &err);
                if (!err.empty()) ChatHandler(player->GetSession()).SendSysMessage(err);
                ShowMain(player, creature);
                break;
            case ACT_MODE_WILDCARD:
                sClasslessMgr->SetMode(player, Mode::Wildcard, &err);
                if (!err.empty()) ChatHandler(player->GetSession()).SendSysMessage(err);
                ShowMain(player, creature);
                break;
            case ACT_BROWSE_CLASSES:
                ShowClassList(player, creature);
                break;
            case ACT_BROWSE_TALENTS:
                ShowTalentTabs(player, creature);
                break;
            case ACT_RESPEC:
                ClearGossipMenuFor(player);
                AddGossipItemFor(player, GOSSIP_ICON_MONEY_BAG,
                    Acore::StringFormat("|cffff0000Confirm|r: unlearn everything for {} gold", sClasslessMgr->cfg.respecCostGold),
                    GOSSIP_SENDER_MAIN, ACT_RESPEC_CONFIRM);
                AddGossipItemFor(player, GOSSIP_ICON_TALK, "<- Back", GOSSIP_SENDER_MAIN, ACT_MAIN);
                SendGossipMenuFor(player, DEFAULT_GOSSIP_MESSAGE, creature->GetGUID());
                break;
            case ACT_RESPEC_CONFIRM:
                if (!sClasslessMgr->Respec(player, &err) && !err.empty())
                    ChatHandler(player->GetSession()).SendSysMessage(err);
                ShowMain(player, creature);
                break;
            case ACT_ARCHETYPES:
                ShowArchetypes(player, creature);
                break;
            case ACT_REBIRTH:
                ClearGossipMenuFor(player);
                AddGossipItemFor(player, GOSSIP_ICON_TRAINER,
                    "|cffff4444Confirm Rebirth|r into the Classless path (everything is wiped)",
                    GOSSIP_SENDER_MAIN, ACT_REBIRTH_CLASSLESS);
                AddGossipItemFor(player, GOSSIP_ICON_BATTLE,
                    "|cffff4444Confirm Rebirth|r into the Wildcard path (everything is wiped and rerolled)",
                    GOSSIP_SENDER_MAIN, ACT_REBIRTH_WILDCARD);
                AddGossipItemFor(player, GOSSIP_ICON_TALK, "<- Back", GOSSIP_SENDER_MAIN, ACT_MAIN);
                SendGossipMenuFor(player, DEFAULT_GOSSIP_MESSAGE, creature->GetGUID());
                break;
            case ACT_REBIRTH_CLASSLESS:
            case ACT_REBIRTH_WILDCARD:
                if (!sClasslessMgr->Rebirth(player, action == ACT_REBIRTH_CLASSLESS ? Mode::Classless : Mode::Wildcard, &err) && !err.empty())
                    ChatHandler(player->GetSession()).SendSysMessage(err);
                ShowMain(player, creature);
                break;
            case ACT_VENDOR:
                ShowVendorMenu(player, creature);
                break;
            case ACT_VENDOR_SUPPLIES:
                // vendor entry 0 means the creature's own list, which holds the
                // Reroll Scrolls -- so right-clicking the NPC still works too
                OpenVendorList(player, creature, VENDOR_LIST_SUPPLIES);
                break;
            case ACT_MAIN:
            default:
                ShowMain(player, creature);
                break;
        }

        return true;
    }

};

void AddClasslessNpcScripts()
{
    new npc_hero_advancement();
}
