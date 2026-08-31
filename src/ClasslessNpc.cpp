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
#include "Creature.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "ScriptedGossip.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "StringConvert.h"
#include "StringFormat.h"
#include "WorldSession.h"
#include <algorithm>

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
        ACT_CARDS             = 50,
        ACT_CARD_ADD_ABILITY  = 51,   // coded
        ACT_CARD_ADD_TALENT   = 52,   // coded
        ACT_LEARN_BY_ID       = 60,   // coded
        ACT_TALENT_BY_ID      = 61,   // coded
        ACT_VENDOR            = 70,
        ACT_ARCHETYPES        = 80,
        ACT_REBIRTH           = 90,
        ACT_REBIRTH_CLASSLESS = 91,
        ACT_REBIRTH_WILDCARD  = 92,
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
        BASE_CARD_REMOVE      = 1000000000 // + index into card list
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
            AddGossipItemFor(player, GOSSIP_ICON_CHAT, "Learn ability by spell ID...", GOSSIP_SENDER_MAIN, ACT_LEARN_BY_ID, "Enter the spell ID:", 0, true);
            AddGossipItemFor(player, GOSSIP_ICON_CHAT, "Learn talent by talent ID...", GOSSIP_SENDER_MAIN, ACT_TALENT_BY_ID, "Enter the talent ID:", 0, true);
            AddGossipItemFor(player, GOSSIP_ICON_INTERACT_1, "My abilities (unlearn)", GOSSIP_SENDER_MAIN, BASE_MY_ABILITIES_PG);
            if (!sClasslessMgr->Archetypes().empty())
                AddGossipItemFor(player, GOSSIP_ICON_TABARD, "Apply a starter archetype...", GOSSIP_SENDER_MAIN, ACT_ARCHETYPES);
            AddGossipItemFor(player, GOSSIP_ICON_MONEY_BAG, Acore::StringFormat("Respec everything ({} gold)", cfg.respecCostGold), GOSSIP_SENDER_MAIN, ACT_RESPEC);
        }
        else // Wildcard
        {
            AddGossipItemFor(player, GOSSIP_ICON_BATTLE, "My rolled abilities (reroll / lock)", GOSSIP_SENDER_MAIN, BASE_MY_ABILITIES_PG);
            AddGossipItemFor(player, GOSSIP_ICON_BATTLE, "My rolled talents (reroll)", GOSSIP_SENDER_MAIN, BASE_MY_TALENTS_PG);
            if (player->GetLevel() < 10)
                AddGossipItemFor(player, GOSSIP_ICON_INTERACT_1, "Skill Cards (guarantee rolls)", GOSSIP_SENDER_MAIN, ACT_CARDS);
            AddGossipItemFor(player, GOSSIP_ICON_VENDOR, "Buy Scrolls of Fortune", GOSSIP_SENDER_MAIN, ACT_VENDOR);
        }

        if (st.mode != Mode::Unchosen && cfg.rebirthEnable)
            AddGossipItemFor(player, GOSSIP_ICON_BATTLE,
                Acore::StringFormat("|cffff4444Rebirth|r — full reset / switch path ({} gold)", cfg.rebirthCostGold),
                GOSSIP_SENDER_MAIN, ACT_REBIRTH);

        SendGossipMenuFor(player, DEFAULT_GOSSIP_MESSAGE, creature->GetGUID());
    }

    void ShowArchetypes(Player* player, Creature* creature)
    {
        ClearGossipMenuFor(player);
        for (auto const& [id, arch] : sClasslessMgr->Archetypes())
            AddGossipItemFor(player, GOSSIP_ICON_TABARD,
                Acore::StringFormat("|cffffff00{}|r — {}", arch.name, arch.description),
                GOSSIP_SENDER_MAIN, BASE_ARCHETYPE + id,
                Acore::StringFormat("Apply the {} archetype? It spends your essence on a ready-made starter build.", arch.name), 0, false);
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
            if (e.enabled && (e.classMask & classMask) && !st.abilities.count(firstSpell))
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
                    "Reroll this ability? (Consumes a Scroll of Fortune from level 10.)", 0, false);
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

    void ShowCards(Player* player, Creature* creature)
    {
        ClearGossipMenuFor(player);
        CharState& st = sClasslessMgr->GetState(player);
        Config const& cfg = sClasslessMgr->cfg;

        uint32 abilityCards = 0, talentCards = 0;
        for (uint32 i = 0; i < st.cards.size(); ++i)
        {
            SkillCard const& card = st.cards[i];
            if (card.isTalent) ++talentCards; else ++abilityCards;
            uint32 nameSpell = card.isTalent
                ? (sClasslessMgr->GetTalent(card.entry) ? sClasslessMgr->GetTalent(card.entry)->rankSpells[0] : 0)
                : card.entry;
            AddGossipItemFor(player, GOSSIP_ICON_INTERACT_1,
                Acore::StringFormat("Remove {}{} Card: {}{}", card.golden ? "Golden " : "",
                    card.isTalent ? "Talent" : "Ability", SpellNameOf(nameSpell), card.used ? " (used)" : ""),
                GOSSIP_SENDER_MAIN, BASE_CARD_REMOVE + i);
        }

        if (abilityCards < cfg.wcAbilityCards + cfg.wcGoldenAbilityCards)
            AddGossipItemFor(player, GOSSIP_ICON_CHAT, "Activate an Ability Card...", GOSSIP_SENDER_MAIN,
                ACT_CARD_ADD_ABILITY, "Enter the ability's first-rank spell ID:", 0, true);
        if (talentCards < cfg.wcTalentCards + cfg.wcGoldenTalentCards)
            AddGossipItemFor(player, GOSSIP_ICON_CHAT, "Activate a Talent Card...", GOSSIP_SENDER_MAIN,
                ACT_CARD_ADD_TALENT, "Enter the talent ID:", 0, true);

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

        if (action >= BASE_CARD_REMOVE)
        {
            uint32 index = action - BASE_CARD_REMOVE;
            CharState& st = sClasslessMgr->GetState(player);
            if (index < st.cards.size())
                sClasslessMgr->RemoveCard(player, st.cards[index].isTalent, st.cards[index].entry, &err);
            ShowCards(player, creature);
        }
        else if (action >= BASE_MY_TALENTS_PG)
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
            case ACT_CARDS:
                ShowCards(player, creature);
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
                player->GetSession()->SendListInventory(creature->GetGUID());
                break;
            case ACT_MAIN:
            default:
                ShowMain(player, creature);
                break;
        }

        return true;
    }

    bool OnGossipSelectCode(Player* player, Creature* creature, uint32 /*sender*/, uint32 action, char const* code) override
    {
        std::string err;
        Optional<uint32> id = Acore::StringTo<uint32>(code ? code : "");
        if (!id)
        {
            ChatHandler(player->GetSession()).SendSysMessage("That is not a valid numeric ID.");
            ShowMain(player, creature);
            return true;
        }

        switch (action)
        {
            case ACT_LEARN_BY_ID:
                if (!sClasslessMgr->BuyAbility(player, *id, &err) && !err.empty())
                    ChatHandler(player->GetSession()).SendSysMessage(err);
                break;
            case ACT_TALENT_BY_ID:
                if (!sClasslessMgr->BuyTalentRank(player, *id, &err) && !err.empty())
                    ChatHandler(player->GetSession()).SendSysMessage(err);
                break;
            case ACT_CARD_ADD_ABILITY:
                if (!sClasslessMgr->AddCard(player, false, *id, &err) && !err.empty())
                    ChatHandler(player->GetSession()).SendSysMessage(err);
                break;
            case ACT_CARD_ADD_TALENT:
                if (!sClasslessMgr->AddCard(player, true, *id, &err) && !err.empty())
                    ChatHandler(player->GetSession()).SendSysMessage(err);
                break;
            default:
                break;
        }

        ShowMain(player, creature);
        return true;
    }
};

void AddClasslessNpcScripts()
{
    new npc_hero_advancement();
}
