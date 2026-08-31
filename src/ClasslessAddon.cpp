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
 * Addon bridge: the ClasslessWildcard client addon talks to the server by
 * whispering ITSELF on the addon channel ("CWCL\t<command>"). We intercept
 * those in the whisper chat hook (which fires for LANG_ADDON), execute the
 * request against ClasslessMgr, and answer with addon whisper packets the
 * client receives as CHAT_MSG_ADDON events. No client patch required.
 */

#include "Chat.h"
#include "ClasslessMgr.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SharedDefines.h"
#include "SpellMgr.h"
#include "StringConvert.h"
#include "StringFormat.h"
#include "Tokenize.h"
#include "WorldPacket.h"
#include "WorldSession.h"

using namespace ClasslessWildcard;

namespace ClasslessWildcard
{
    // raw push to the client addon, callable from anywhere in the module
    void PushAddon(Player* player, std::string const& body)
    {
        WorldPacket data;
        ChatHandler::BuildChatPacket(data, CHAT_MSG_WHISPER, LANG_ADDON, player, player,
            std::string("CWCL\t") + body);
        player->GetSession()->SendPacket(&data);
    }
}

namespace
{
    constexpr char ADDON_PREFIX[] = "CWCL";
    constexpr size_t MAX_BODY = 200;      // payload budget per addon message
    constexpr uint32 LIST_PAGE = 10;      // entries per browse page (abilities)
    constexpr uint32 TAL_PAGE = 9;        // talents: the tree-selector row eats one slot

    void SendAddon(Player* player, std::string const& body)
    {
        WorldPacket data;
        ChatHandler::BuildChatPacket(data, CHAT_MSG_WHISPER, LANG_ADDON, player, player,
            std::string(ADDON_PREFIX) + "\t" + body);
        player->GetSession()->SendPacket(&data);
    }

    std::string Sanitize(std::string s)
    {
        for (char& c : s)
            if (c == '|' || c == ';' || c == ':' || c == '\t' || c == '\n')
                c = ' ';
        return s;
    }

    void SendState(Player* player)
    {
        CharState& st = sClasslessMgr->GetState(player);
        Config const& cfg = sClasslessMgr->cfg;
        uint32 chance = std::min<uint32>(cfg.wcSynergyBaseChance + st.pity * cfg.wcSynergyIncrement, 100);
        uint32 scrolls = player->GetItemCount(cfg.wcScrollItemId);
        SendAddon(player, Acore::StringFormat("S|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}",
            uint32(st.mode), st.abilityEssence, st.talentEssence, st.pity, chance,
            scrolls, player->GetLevel(), cfg.modeChoiceDeadline,
            cfg.rebirthEnable ? 1 : 0, cfg.rebirthCostGold,
            st.rerolls, cfg.universalResources ? 1 : 0,
            sClasslessMgr->ScrollBuyCost(player->GetLevel()),
            (cfg.wcScrollBuyEnable && player->GetLevel() >= cfg.wcFreeRerollLevel) ? 1 : 0));

        // Talent pricing, so the browser can label what a talent actually
        // costs instead of assuming. Sent as its own message rather than more
        // positional fields on S -- an addon that predates it simply ignores
        // the unknown kind.
        SendAddon(player, Acore::StringFormat("CFG|{}|{}",
            cfg.talentCostPerRank, cfg.talentFlatCost ? 1 : 0));
    }

    void SendErr(Player* player, std::string const& text)
    {
        SendAddon(player, "ERR|" + Sanitize(text));
    }

    void SendOk(Player* player, std::string const& op)
    {
        SendAddon(player, "OK|" + op);
        SendState(player);
    }

    // ---- browse: abilities of one class, paged ----
    void SendAbilityPage(Player* player, uint8 classId, uint32 page)
    {
        CharState& st = sClasslessMgr->GetState(player);
        uint32 classMask = classId >= 1 && classId <= 11 ? (1u << (classId - 1)) : 0;

        std::vector<AbilityEntry const*> list;
        for (auto const& [firstSpell, e] : sClasslessMgr->Abilities())
            if (e.enabled && (e.classMask & classMask))
                list.push_back(&e);

        uint32 totalPages = list.empty() ? 1 : (uint32(list.size()) + LIST_PAGE - 1) / LIST_PAGE;
        if (page >= totalPages)
            page = totalPages - 1;

        std::string body = Acore::StringFormat("AB|{}|{}|{}|", classId, page, totalPages);
        uint32 start = page * LIST_PAGE;
        for (uint32 i = start; i < list.size() && i < start + LIST_PAGE; ++i)
        {
            AbilityEntry const* e = list[i];
            body += Acore::StringFormat("{}:{}:{}:{}:{}:{};", e->firstSpellId, uint32(e->rarity),
                sClasslessMgr->AbilityCost(*e), st.abilities.count(e->firstSpellId) ? 1 : 0, e->passive ? 1 : 0,
                e->rankLevels.empty() ? 1 : uint32(e->rankLevels[0]));
        }
        SendAddon(player, body);
    }

    // ---- browse: talent tabs, then talents of one tab, paged ----
    void SendTalentTabs(Player* player)
    {
        std::map<uint32, uint32> tabs; // tabId -> classMask
        for (auto const& [talentId, t] : sClasslessMgr->Talents())
            tabs[t.tabId] = t.classMask;

        std::string body = "TB|";
        for (auto const& [tabId, mask] : tabs)
        {
            uint8 classId = 1;
            for (uint8 c = 1; c <= 11; ++c)
                if (mask & (1u << (c - 1))) { classId = c; break; }
            std::string piece = Acore::StringFormat("{}:{};", tabId, classId);
            if (body.size() + piece.size() > MAX_BODY)
            {
                SendAddon(player, body);
                body = "TB|";
            }
            body += piece;
        }
        SendAddon(player, body);
        SendAddon(player, "TBE|");
    }

    void SendTalentPage(Player* player, uint32 tabId, uint32 page)
    {
        CharState& st = sClasslessMgr->GetState(player);

        std::vector<TalentPoolEntry const*> list;
        for (auto const& [talentId, t] : sClasslessMgr->Talents())
            if (t.enabled && t.tabId == tabId)
                list.push_back(&t);
        std::sort(list.begin(), list.end(), [](auto a, auto b)
        {
            return a->row != b->row ? a->row < b->row : a->col < b->col;
        });

        uint32 totalPages = list.empty() ? 1 : (uint32(list.size()) + TAL_PAGE - 1) / TAL_PAGE;
        if (page >= totalPages)
            page = totalPages - 1;

        std::string body = Acore::StringFormat("TL|{}|{}|{}|", tabId, page, totalPages);
        uint32 start = page * TAL_PAGE;
        for (uint32 i = start; i < list.size() && i < start + TAL_PAGE; ++i)
        {
            TalentPoolEntry const* t = list[i];
            uint8 owned = 0;
            if (auto itr = st.talents.find(t->talentId); itr != st.talents.end())
                owned = itr->second;
            body += Acore::StringFormat("{}:{}:{}:{}:{}:{};", t->talentId, t->rankSpells[0],
                uint32(t->rarity), owned, t->maxRank, t->row);
        }
        SendAddon(player, body);
    }

    // ---- owned lists (chunked) ----
    void SendOwnedAbilities(Player* player)
    {
        CharState& st = sClasslessMgr->GetState(player);
        std::string body = "OA|";
        for (auto const& [firstSpell, owned] : st.abilities)
        {
            AbilityEntry const* e = sClasslessMgr->GetAbility(firstSpell);
            std::string piece = Acore::StringFormat("{}:{}:{}:{};", firstSpell,
                e ? uint32(e->rarity) : 0, owned.locked ? 1 : 0, uint32(owned.source));
            if (body.size() + piece.size() > MAX_BODY)
            {
                SendAddon(player, body);
                body = "OA|";
            }
            body += piece;
        }
        SendAddon(player, body);
        SendAddon(player, "OAE|");
    }

    void SendOwnedTalents(Player* player)
    {
        CharState& st = sClasslessMgr->GetState(player);
        std::string body = "OT|";
        for (auto const& [talentId, rank] : st.talents)
        {
            TalentPoolEntry const* t = sClasslessMgr->GetTalent(talentId);
            if (!t)
                continue;
            std::string piece = Acore::StringFormat("{}:{}:{}:{}:{};", talentId,
                t->rankSpells[0], uint32(t->rarity), rank, t->maxRank);
            if (body.size() + piece.size() > MAX_BODY)
            {
                SendAddon(player, body);
                body = "OT|";
            }
            body += piece;
        }
        SendAddon(player, body);
        SendAddon(player, "OTE|");
    }

    void SendStats(Player* player)
    {
        CharState& st = sClasslessMgr->GetState(player);
        Config const& cfg = sClasslessMgr->cfg;
        uint32 budget = sClasslessMgr->StatBudget(player);
        uint32 spent = sClasslessMgr->SpentStatPoints(st);
        SendAddon(player, Acore::StringFormat("ST|{}|{}|{}|{}|{}|{}|{}|{}|{}",
            budget, budget > spent ? budget - spent : 0, cfg.statValuePerPoint,
            st.statAlloc[0], st.statAlloc[1], st.statAlloc[2], st.statAlloc[3], st.statAlloc[4],
            cfg.statsEnable ? 1 : 0));
    }

    void SendArchetypes(Player* player)
    {
        for (auto const& [id, arch] : sClasslessMgr->Archetypes())
            SendAddon(player, Acore::StringFormat("AR|{}|{}|{}|{}",
                id, Sanitize(arch.name), Sanitize(arch.description), uint32(arch.abilities.size())));
        SendAddon(player, "ARE|");
    }

    void HandleRequest(Player* player, std::string_view request)
    {
        std::vector<std::string_view> args = Acore::Tokenize(request, ' ', false);
        if (args.empty())
            return;

        std::string_view cmd = args[0];
        auto argNum = [&](size_t i) -> uint32
        {
            if (i < args.size())
                if (Optional<uint32> v = Acore::StringTo<uint32>(args[i]))
                    return *v;
            return 0;
        };

        std::string err;

        if (cmd == "HELLO" || cmd == "STATE")
            SendState(player);
        else if (cmd == "ABIL")
            SendAbilityPage(player, uint8(argNum(1)), argNum(2));
        else if (cmd == "TABS")
            SendTalentTabs(player);
        else if (cmd == "TAL")
            SendTalentPage(player, argNum(1), argNum(2));
        else if (cmd == "OWN")
            SendOwnedAbilities(player);
        else if (cmd == "OWNT")
            SendOwnedTalents(player);
        else if (cmd == "ARCH")
            SendArchetypes(player);
        else if (cmd == "STATS")
            SendStats(player);
        else if (cmd == "STATSETALL")
        {
            std::array<uint32, 5> alloc = { argNum(1), argNum(2), argNum(3), argNum(4), argNum(5) };
            if (sClasslessMgr->SetStatAllocation(player, alloc, &err))
            {
                SendAddon(player, "OK|STATS");
                SendStats(player);
                SendState(player);
            }
            else
                SendErr(player, err);
        }
        else if (cmd == "BUY")
            sClasslessMgr->BuyAbility(player, argNum(1), &err) ? SendOk(player, "BUY") : SendErr(player, err);
        else if (cmd == "UNL")
            sClasslessMgr->UnlearnAbility(player, argNum(1), &err) ? SendOk(player, "UNL") : SendErr(player, err);
        else if (cmd == "TALBUY")
            sClasslessMgr->BuyTalentRank(player, argNum(1), &err) ? SendOk(player, "TALBUY") : SendErr(player, err);
        else if (cmd == "RESPEC")
            sClasslessMgr->Respec(player, &err) ? SendOk(player, "RESPEC") : SendErr(player, err);
        else if (cmd == "BAR")
            sClasslessMgr->SetDisplayPower(player, uint8(argNum(1)), &err) ? SendOk(player, "BAR") : SendErr(player, err);
        else if (cmd == "MODE")
            sClasslessMgr->SetMode(player, Mode(uint8(argNum(1))), &err) ? SendOk(player, "MODE") : SendErr(player, err);
        else if (cmd == "RR")
            sClasslessMgr->Reroll(player, false, argNum(1), &err) ? SendOk(player, "RR") : SendErr(player, err);
        else if (cmd == "RRT")
            sClasslessMgr->Reroll(player, true, argNum(1), &err) ? SendOk(player, "RRT") : SendErr(player, err);
        else if (cmd == "LOCK")
            sClasslessMgr->ToggleLock(player, argNum(1), &err) ? SendOk(player, "LOCK") : SendErr(player, err);
        else if (cmd == "ARCHAPPLY")
            sClasslessMgr->ApplyArchetype(player, argNum(1), &err) ? SendOk(player, "ARCH") : SendErr(player, err);
        else if (cmd == "REBIRTH")
            sClasslessMgr->Rebirth(player, Mode(uint8(argNum(1))), &err) ? SendOk(player, "REBIRTH") : SendErr(player, err);
        else if (cmd == "BUYSCROLL")
            sClasslessMgr->BuyScroll(player, argNum(1), &err) ? SendOk(player, "BUYSCROLL") : SendErr(player, err);
    }
}

class ClasslessAddonScript : public PlayerScript
{
public:
    ClasslessAddonScript() : PlayerScript("ClasslessAddonScript", {
        PLAYERHOOK_CAN_PLAYER_USE_PRIVATE_CHAT
    }) { }

    bool OnPlayerCanUseChat(Player* player, uint32 type, uint32 language, std::string& msg, Player* receiver) override
    {
        if (!sClasslessMgr->cfg.enabled)
            return true;
        if (language != LANG_ADDON || type != CHAT_MSG_WHISPER || receiver != player)
            return true;

        // client sends "CWCL\t<request>"
        std::string_view view = msg;
        if (view.substr(0, 5) != "CWCL\t")
            return true;

        HandleRequest(player, view.substr(5));
        return false; // swallow the self-whisper
    }
};

void AddClasslessAddonScripts()
{
    new ClasslessAddonScript();
}
