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
 * Hero Advancement panel.
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
        BASE_MY_TALENTS_PG    = 900000000, // + page
        BASE_TALENT_DEEPEN    = 1000000000 // + talentId (reroll, one scroll spent on its rank)
    };

    // The Hero line's page in the class browser: one past Druid, and the bit
    // the Hero talent tab carries in its ClassMask.
    constexpr uint8 HERO_PAGE = 12;

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
            case HERO_PAGE:     return "Hero";
            default:            return "Unknown";
        }
    }

    // TalentTab.dbc carries the tree names, but the core does not load them.
    char const* TreeName(uint32 tabId)
    {
        switch (tabId)
        {
            case 41:  return "Fire";          case 61:  return "Frost";         case 81:  return "Arcane";
            case 161: return "Arms";          case 163: return "Protection";    case 164: return "Fury";
            case 181: return "Combat";        case 182: return "Assassination"; case 183: return "Subtlety";
            case 201: return "Discipline";    case 202: return "Holy";          case 203: return "Shadow";
            case 261: return "Elemental";     case 262: return "Restoration";   case 263: return "Enhancement";
            case 281: return "Feral Combat";  case 282: return "Restoration";   case 283: return "Balance";
            case 301: return "Destruction";   case 302: return "Affliction";    case 303: return "Demonology";
            case 361: return "Beast Mastery"; case 362: return "Survival";      case 363: return "Marksmanship";
            case 381: return "Retribution";   case 382: return "Holy";          case 383: return "Protection";
            case 398: return "Blood";         case 399: return "Frost";         case 400: return "Unholy";
            default:  return nullptr;
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
            AddGossipItemFor(player, GOSSIP_ICON_TRAINER, "|cff00ccffChoose the Classless path|r (pick every ability yourself)",
                GOSSIP_SENDER_MAIN, ACT_MODE_CLASSLESS,
                "Walk the Classless path? This character keeps it for good.", 0, false);
            AddGossipItemFor(player, GOSSIP_ICON_BATTLE, "|cffff8800Choose the Wildcard path|r (random abilities, reroll what you dislike)",
                GOSSIP_SENDER_MAIN, ACT_MODE_WILDCARD,
                "Walk the Wildcard path? This character keeps it for good.", 0, false);
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
            AddGossipItemFor(player, GOSSIP_ICON_INTERACT_1, "Unlearn everything (free)", GOSSIP_SENDER_MAIN, ACT_RESPEC);
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
            AddGossipItemFor(player, GOSSIP_ICON_VENDOR, st.mode == Mode::Wildcard
                                 ? "Browse the Hero's wares (gear, heirlooms, Reroll Scrolls)..."
                                 : "Browse the Hero's wares (gear and heirlooms)...",
                             GOSSIP_SENDER_MAIN, ACT_VENDOR);

        // Rebirth picks heirlooms, which a gossip menu cannot do, so at the
        // cap the menu says where to go.
        if (cfg.rebirthEnable && sClasslessMgr->RebirthEligible(player))
            AddGossipItemFor(player, GOSSIP_ICON_CHAT,
                "Rebirth into a new life at level 1 is done from the Hero Advancement panel (/cw).",
                GOSSIP_SENDER_MAIN, ACT_MAIN);

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
                Acore::StringFormat("{}  |cff888888{} ({} items)|r",
                    VENDOR_CATEGORIES[c].name, VENDOR_CATEGORIES[c].blurb, CategoryTotal(c)),
                GOSSIP_SENDER_MAIN, BASE_VENDOR_CATEGORY + c);

        // Reroll Scrolls sell here at the same level-scaled price as the
        // panel's Buy Scroll button, through the same purchase.
        CharState const& st = sClasslessMgr->GetState(player);
        Config const& cfg = sClasslessMgr->cfg;
        if (st.mode == Mode::Wildcard && cfg.wcScrollBuyEnable && player->GetLevel() >= cfg.wcFreeRerollLevel)
        {
            uint32 const cost = sClasslessMgr->ScrollBuyCost(player->GetLevel());
            std::string price;
            if (cost / GOLD)
                price += Acore::StringFormat("{}g", cost / GOLD);
            if ((cost % GOLD) / SILVER)
                price += Acore::StringFormat("{}{}s", price.empty() ? "" : " ", (cost % GOLD) / SILVER);
            if (price.empty())
                price = Acore::StringFormat("{}c", cost);
            AddGossipItemFor(player, GOSSIP_ICON_MONEY_BAG,
                Acore::StringFormat("Buy a Reroll Scroll  |cffffd100{}|r", price),
                GOSSIP_SENDER_MAIN, ACT_VENDOR_SUPPLIES);
        }
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
                    "and your talents are reset with them. Its abilities and talents are then bought for you "
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
        if (sClasslessMgr->cfg.forgedEnable)
            AddGossipItemFor(player, GOSSIP_ICON_TRAINER, ClassNameById(HERO_PAGE), GOSSIP_SENDER_MAIN,
                BASE_CLASS_PAGE + uint32(HERO_PAGE) * 100000);
        AddGossipItemFor(player, GOSSIP_ICON_TALK, "<- Back", GOSSIP_SENDER_MAIN, ACT_MAIN);
        SendGossipMenuFor(player, DEFAULT_GOSSIP_MESSAGE, creature->GetGUID());
    }

    // A page past the end (the last item on it was just bought or dropped)
    // falls back to the last page there is.
    uint32 ClampPage(uint32 page, size_t count)
    {
        uint32 const pages = count ? uint32((count + PAGE_SIZE - 1) / PAGE_SIZE) : 1;
        return std::min(page, pages - 1);
    }

    std::vector<AbilityEntry const*> ClassAbilityList(Player* player, uint8 classId)
    {
        CharState& st = sClasslessMgr->GetState(player);
        uint32 classMask = 1u << (classId - 1);
        // Hero-line abilities carry every class bit; they list on their own
        // Hero page rather than under every class.
        bool const heroPage = classId == HERO_PAGE;
        std::vector<AbilityEntry const*> list;
        for (auto const& [firstSpell, e] : sClasslessMgr->Abilities())
            if (e.enabled && (heroPage ? e.forged : (!e.forged && (e.classMask & classMask)))
                && !st.abilities.count(firstSpell)
                && (!e.variant || sClasslessMgr->cfg.elementalShowInBrowser))
                list.push_back(&e);
        return list;
    }

    // The class page an ability is browsed under: the Hero page, or its
    // first class.
    uint8 BrowseClassOf(AbilityEntry const& e)
    {
        if (e.forged)
            return HERO_PAGE;
        for (uint8 c = 1; c <= 11; ++c)
            if (e.classMask & (1u << (c - 1)))
                return c;
        return CLASS_WARRIOR;
    }

    std::vector<TalentPoolEntry const*> TalentTabList(uint32 tabId)
    {
        std::vector<TalentPoolEntry const*> list;
        for (auto const& [talentId, t] : sClasslessMgr->Talents())
            if (t.enabled && t.tabId == tabId)
                list.push_back(&t);
        std::sort(list.begin(), list.end(), [](auto a, auto b)
        {
            return a->row != b->row ? a->row < b->row : a->col < b->col;
        });
        return list;
    }

    void ShowClassAbilities(Player* player, Creature* creature, uint8 classId, uint32 page)
    {
        ClearGossipMenuFor(player);
        std::vector<AbilityEntry const*> list = ClassAbilityList(player, classId);
        page = ClampPage(page, list.size());

        uint32 start = page * PAGE_SIZE;
        for (uint32 i = start; i < list.size() && i < start + PAGE_SIZE; ++i)
        {
            AbilityEntry const* e = list[i];
            // The unlock level is part of the price: without it the only way to
            // find out an ability is out of reach was to click it and be told.
            uint32 unlock = e->rankLevels.empty() ? 1u : uint32(e->rankLevels[0]);
            bool tooHigh = sClasslessMgr->cfg.respectLevelReqs && unlock > player->GetLevel();
            AddGossipItemFor(player, GOSSIP_ICON_TRAINER,
                Acore::StringFormat("{}{}|r  [{} AE]  {}Lv {}|r{}", RarityColor(e->rarity), SpellNameOf(e->firstSpellId),
                    sClasslessMgr->AbilityCost(*e), tooHigh ? "|cffff4444" : "|cff888888", unlock,
                    e->passive ? " (passive)" : ""),
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
            uint8 classId = HERO_PAGE;
            for (uint8 c = 1; c <= 11; ++c)
                if (info.first & (1u << (c - 1))) { classId = c; break; }
            char const* tree = TreeName(tabId);
            AddGossipItemFor(player, GOSSIP_ICON_TRAINER,
                classId == HERO_PAGE ? std::string("Hero")
                    : tree ? Acore::StringFormat("{}: {}", ClassNameById(classId), tree)
                           : Acore::StringFormat("{} talents", ClassNameById(classId)),
                GOSSIP_SENDER_MAIN, BASE_TALENT_TAB + tabId * 1000);
        }
        AddGossipItemFor(player, GOSSIP_ICON_TALK, "<- Back", GOSSIP_SENDER_MAIN, ACT_MAIN);
        SendGossipMenuFor(player, DEFAULT_GOSSIP_MESSAGE, creature->GetGUID());
    }

    void ShowTalentTab(Player* player, Creature* creature, uint32 tabId, uint32 page)
    {
        ClearGossipMenuFor(player);
        CharState& st = sClasslessMgr->GetState(player);
        Config const& cfg = sClasslessMgr->cfg;

        std::vector<TalentPoolEntry const*> list = TalentTabList(tabId);
        page = ClampPage(page, list.size());

        uint32 start = page * PAGE_SIZE;
        for (uint32 i = start; i < list.size() && i < start + PAGE_SIZE; ++i)
        {
            TalentPoolEntry const* t = list[i];
            uint8 owned = 0;
            if (auto itr = st.talents.find(t->talentId); itr != st.talents.end())
                owned = itr->second;
            uint32 const unlock = 10 + t->row * 5;
            bool const tooHigh = cfg.respectLevelReqs && unlock > player->GetLevel();
            std::string price;
            if (owned >= t->maxRank)
                price = "|cff888888maxed|r";
            else
            {
                uint32 const cost = (cfg.talentFlatCost && owned > 0) ? 0 : cfg.talentCostPerRank;
                price = cost ? Acore::StringFormat("[{} TE]", cost) : std::string("[free]");
            }
            AddGossipItemFor(player, GOSSIP_ICON_TRAINER,
                Acore::StringFormat("{}{}|r  [{}/{}]  {}  {}Tier {}, Lv {}|r", RarityColor(t->rarity),
                    SpellNameOf(t->rankSpells[0]), owned, t->maxRank, price,
                    tooHigh ? "|cffff4444" : "|cff888888", t->row + 1, unlock),
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
        page = ClampPage(page, owned.size());

        uint32 start = page * PAGE_SIZE;
        for (uint32 i = start; i < owned.size() && i < start + PAGE_SIZE; ++i)
        {
            uint32 firstSpell = owned[i];
            AbilityEntry const* e = sClasslessMgr->GetAbility(firstSpell);
            OwnedAbility const& o = st.abilities[firstSpell];
            bool locked = o.locked;
            std::string label = Acore::StringFormat("{}{}|r{}", e ? RarityColor(e->rarity) : "|cffffffff",
                SpellNameOf(firstSpell), locked ? " |cffffff00[locked]|r" : "");

            // Free extras have nothing to offer here: they cost nothing, so
            // there is no essence to refund, and they cannot be rerolled or
            // locked on their own. Listed so the build is complete, with no
            // action attached and a note saying where they came from.
            if (o.source == GrantSource::Companion || o.source == GrantSource::Talent
                || o.source == GrantSource::Heirloom)
            {
                AddGossipItemFor(player, GOSSIP_ICON_CHAT,
                    Acore::StringFormat("{}  |cff888888({})|r", label,
                        o.source == GrantSource::Companion ? "came free with another ability"
                        : o.source == GrantSource::Talent  ? "came with a talent"
                                                           : "heirloom, kept through Rebirth"),
                    GOSSIP_SENDER_MAIN, BASE_MY_ABILITIES_PG + page);
                continue;
            }

            if (wildcard)
            {
                AddGossipItemFor(player, GOSSIP_ICON_BATTLE, Acore::StringFormat("Reroll: {}", label),
                    GOSSIP_SENDER_MAIN, BASE_ABILITY_ACTION + firstSpell,
                    Acore::StringFormat("Reroll this ability? Free below level {}. After that it uses a reroll charge, "
                        "or a Reroll Scroll when you have no charges left.", sClasslessMgr->cfg.wcFreeRerollLevel), 0, false);
                // A padlock is only worth offering while the starting hand's
                // reroll-everything pass can still take the card.
                if (locked || player->GetLevel() < sClasslessMgr->cfg.wcFreeRerollLevel)
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
        page = ClampPage(page, owned.size());

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
                Acore::StringFormat("Reroll this talent? It is replaced by one new random talent. Free below level {}. "
                    "After that it uses a reroll charge, or a Reroll Scroll when you have no charges left.",
                    sClasslessMgr->cfg.wcFreeRerollLevel), 0, false);

            // and the same reroll with a scroll staked on keeping it instead
            if (uint32 const per = sClasslessMgr->cfg.wcTalentUpgradePerScroll;
                per && rank < t->maxRank && sClasslessMgr->cfg.wcTalentUpgradeMaxScrolls)
            {
                uint32 const odds = std::min<uint32>(100, sClasslessMgr->cfg.wcTalentUpgradeBase + per);
                AddGossipItemFor(player, GOSSIP_ICON_MONEY_BAG,
                    Acore::StringFormat("   ...and stake a Reroll Scroll on its rank ({}%)", odds),
                    GOSSIP_SENDER_MAIN, BASE_TALENT_DEEPEN + talentId,
                    Acore::StringFormat("Spend one extra Reroll Scroll for a {}% chance to KEEP this talent and raise its rank instead? If it fails, the talent is replaced as normal.", odds),
                    0, false);
            }
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

    // Where an owned ability or talent sits in the "My ..." lists, which are
    // sorted by id, so an action can return to the page it was taken from.
    static uint32 OwnedAbilityPage(Player* player, uint32 firstSpell)
    {
        CharState& st = sClasslessMgr->GetState(player);
        uint32 before = 0;
        for (auto const& [id, o] : st.abilities)
            if (id < firstSpell)
                ++before;
        return before / PAGE_SIZE;
    }

    static uint32 OwnedTalentPage(Player* player, uint32 talentId)
    {
        CharState& st = sClasslessMgr->GetState(player);
        uint32 before = 0;
        for (auto const& [id, rank] : st.talents)
            if (id < talentId)
                ++before;
        return before / PAGE_SIZE;
    }

    bool OnGossipSelect(Player* player, Creature* creature, uint32 /*sender*/, uint32 action) override
    {
        std::string err;

        if (action >= BASE_TALENT_DEEPEN)
        {
            uint32 const page = OwnedTalentPage(player, action - BASE_TALENT_DEEPEN);
            if (!sClasslessMgr->Reroll(player, true, action - BASE_TALENT_DEEPEN, &err, 1) && !err.empty())
                ChatHandler(player->GetSession()).SendSysMessage(err);
            ShowMyTalents(player, creature, page);
        }
        else if (action >= BASE_MY_TALENTS_PG)
            ShowMyTalents(player, creature, action - BASE_MY_TALENTS_PG);
        else if (action >= BASE_REROLL_TALENT)
        {
            uint32 const page = OwnedTalentPage(player, action - BASE_REROLL_TALENT);
            if (!sClasslessMgr->Reroll(player, true, action - BASE_REROLL_TALENT, &err) && !err.empty())
                ChatHandler(player->GetSession()).SendSysMessage(err);
            ShowMyTalents(player, creature, page);
        }
        else if (action >= BASE_LOCK_ABILITY)
        {
            // 4.7: a refused padlock says why
            if (!sClasslessMgr->ToggleLock(player, action - BASE_LOCK_ABILITY, &err) && !err.empty())
                ChatHandler(player->GetSession()).SendSysMessage(err);
            ShowMyAbilities(player, creature, OwnedAbilityPage(player, action - BASE_LOCK_ABILITY));
        }
        else if (action >= BASE_MY_ABILITIES_PG)
            ShowMyAbilities(player, creature, action - BASE_MY_ABILITIES_PG);
        else if (action >= BASE_LEARN_TALENT)
        {
            if (!sClasslessMgr->BuyTalentRank(player, action - BASE_LEARN_TALENT, &err) && !err.empty())
                ChatHandler(player->GetSession()).SendSysMessage(err);
            // stay on the same tab
            if (TalentPoolEntry const* t = sClasslessMgr->GetTalent(action - BASE_LEARN_TALENT))
            {
                std::vector<TalentPoolEntry const*> list = TalentTabList(t->tabId);
                uint32 const index = uint32(std::find(list.begin(), list.end(), t) - list.begin());
                ShowTalentTab(player, creature, t->tabId, index / PAGE_SIZE);
            }
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
            uint32 const page = OwnedAbilityPage(player, firstSpell);
            if (sClasslessMgr->GetState(player).mode == Mode::Wildcard)
            {
                if (!sClasslessMgr->Reroll(player, false, firstSpell, &err) && !err.empty())
                    ChatHandler(player->GetSession()).SendSysMessage(err);
            }
            else if (!sClasslessMgr->UnlearnAbility(player, firstSpell, &err) && !err.empty())
                ChatHandler(player->GetSession()).SendSysMessage(err);
            ShowMyAbilities(player, creature, page);
        }
        else if (action >= BASE_LEARN_ABILITY)
        {
            uint32 const firstSpell = action - BASE_LEARN_ABILITY;
            AbilityEntry const* e = sClasslessMgr->GetAbility(firstSpell);
            // back to the class page it was bought from, at the same place
            uint8 classId = e ? BrowseClassOf(*e) : 0;
            uint32 page = 0;
            if (e)
            {
                std::vector<AbilityEntry const*> list = ClassAbilityList(player, classId);
                page = uint32(std::find(list.begin(), list.end(), e) - list.begin()) / PAGE_SIZE;
            }
            if (!sClasslessMgr->BuyAbility(player, firstSpell, &err) && !err.empty())
                ChatHandler(player->GetSession()).SendSysMessage(err);
            if (e)
                ShowClassAbilities(player, creature, classId, page);
            else
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
                AddGossipItemFor(player, GOSSIP_ICON_INTERACT_1,
                    "|cffff0000Confirm|r: unlearn every ability and talent, essence refunded",
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
            case ACT_VENDOR:
                ShowVendorMenu(player, creature);
                break;
            case ACT_VENDOR_SUPPLIES:
                if (!sClasslessMgr->BuyScroll(player, &err) && !err.empty())
                    ChatHandler(player->GetSession()).SendSysMessage(err);
                ShowVendorMenu(player, creature);
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
