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
#include "DBCStores.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SharedDefines.h"
#include "SpellMgr.h"
#include "StringConvert.h"
#include "StringFormat.h"
#include "Tokenize.h"
#include "WorldPacket.h"
#include "WorldSession.h"

#include <cmath>

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

    // For fields inside ':'/';'-delimited list records: every delimiter goes.
    std::string Sanitize(std::string s)
    {
        for (char& c : s)
            if (c == '|' || c == ';' || c == ':' || c == '\t' || c == '\n')
                c = ' ';
        return s;
    }

    // For a whole '|'-delimited field of free text (archetype names and
    // descriptions): colons and semicolons are ordinary punctuation there.
    std::string SanitizeText(std::string s)
    {
        for (char& c : s)
            if (c == '|' || c == '\t' || c == '\n')
                c = ' ';
        return s;
    }

    void SendState(Player* player)
    {
        CharState& st = sClasslessMgr->GetState(player);
        Config const& cfg = sClasslessMgr->cfg;
        uint32 chance = std::min<uint32>(cfg.wcSynergyBaseChance + st.pity * cfg.wcSynergyIncrement, 100);
        uint32 scrolls = player->GetItemCount(cfg.wcScrollItemId);
        // Field 16 is the level free rerolls stop at. The addon used to hard-code
        // 10 for the starting-hand window and the "Reroll (free)" label, so a
        // realm that tuned Wildcard.FreeRerollLevel got an addon that disagreed
        // with its own server. Fields are read by position now, and anything the
        // addon does not know about is ignored, so the packet can simply grow.
        SendAddon(player, Acore::StringFormat("S|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}",
            uint32(st.mode), st.abilityEssence, st.talentEssence, st.pity, chance,
            scrolls, player->GetLevel(), cfg.modeChoiceDeadline,
            cfg.rebirthEnable ? 1 : 0, cfg.rebirthCostGold,
            // Whether THIS character has the extra pools. Every Hero does;
            // an exempt account (playerbots and friends) plays by vanilla class
            // rules and has only its own, so telling its client "1" would draw
            // mini-bars for pools that are not there. The addon uses this field
            // alone to decide whether to show them.
            st.rerolls, sClasslessMgr->IsExempt(player) ? 0 : 1,
            sClasslessMgr->ScrollBuyCost(player->GetLevel()),
            (cfg.wcScrollBuyEnable && player->GetLevel() >= cfg.wcFreeRerollLevel) ? 1 : 0,
            uint32(cfg.wcFreeRerollLevel),
            // fields 17-19: what a scroll buys on a talent reroll, so the
            // addon can show the odds instead of guessing them
            cfg.wcTalentUpgradeBase, cfg.wcTalentUpgradePerScroll,
            cfg.wcTalentUpgradeMaxScrolls));

        // Talent pricing, so the browser can label what a talent actually
        // costs instead of assuming. Sent as its own message rather than more
        // positional fields on S -- an addon that predates it simply ignores
        // the unknown kind.
        // The third field is whether Death Knight content is in the library.
        // The addon hides the Death Knight class button and its talent trees
        // unless it is, because with IncludeDeathKnight off there is nothing
        // behind them -- and hard-coding that on the client meant the tab could
        // never appear once a realm turned it on.
        SendAddon(player, Acore::StringFormat("CFG|{}|{}|{}",
            cfg.talentCostPerRank, cfg.talentFlatCost ? 1 : 0,
            cfg.includeDeathKnight ? 1 : 0));
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
    // Sort orders the browser offers. 0 is the default.
    enum BrowseSort : uint32
    {
        SORT_LEVEL_ASC  = 0,   // unlock level (talents: tier), then name
        SORT_LEVEL_DESC = 1,
        SORT_NAME_ASC   = 2,
        SORT_NAME_DESC  = 3,
        SORT_TYPE       = 4    // grouped by type (talents: active before passive), then level
    };

    // ABIL <class> <page> [sort] [type]: type 0 shows everything, 1..6 keeps
    // one AbilityType (its value + 1, so a missing argument means "all").
    // Each record: first:rarity:cost:owned:passive:level:type
    void SendAbilityPage(Player* player, uint8 classId, uint32 page, uint32 sort, uint32 typeArg)
    {
        CharState& st = sClasslessMgr->GetState(player);
        uint32 classMask = classId >= 1 && classId <= 11 ? (1u << (classId - 1)) : 0;

        std::vector<AbilityEntry const*> list;
        for (auto const& [firstSpell, e] : sClasslessMgr->Abilities())
            if (e.enabled && (e.classMask & classMask)
                && (!e.variant || sClasslessMgr->cfg.elementalShowInBrowser)
                && (!typeArg || uint32(e.type) + 1 == typeArg))
                list.push_back(&e);

        auto level = [](AbilityEntry const* e) { return e->rankLevels.empty() ? 1u : uint32(e->rankLevels[0]); };
        std::stable_sort(list.begin(), list.end(), [&](AbilityEntry const* a, AbilityEntry const* b)
        {
            switch (sort)
            {
                case SORT_LEVEL_DESC:
                    return level(a) != level(b) ? level(a) > level(b) : a->name < b->name;
                case SORT_NAME_ASC:
                    return a->name != b->name ? a->name < b->name : level(a) < level(b);
                case SORT_NAME_DESC:
                    return a->name != b->name ? a->name > b->name : level(a) < level(b);
                case SORT_TYPE:
                    if (a->type != b->type)
                        return uint8(a->type) < uint8(b->type);
                    return level(a) != level(b) ? level(a) < level(b) : a->name < b->name;
                default:
                    return level(a) != level(b) ? level(a) < level(b) : a->name < b->name;
            }
        });

        uint32 totalPages = list.empty() ? 1 : (uint32(list.size()) + LIST_PAGE - 1) / LIST_PAGE;
        if (page >= totalPages)
            page = totalPages - 1;

        std::string body = Acore::StringFormat("AB|{}|{}|{}|", classId, page, totalPages);
        uint32 start = page * LIST_PAGE;
        for (uint32 i = start; i < list.size() && i < start + LIST_PAGE; ++i)
        {
            AbilityEntry const* e = list[i];
            body += Acore::StringFormat("{}:{}:{}:{}:{}:{}:{};", e->firstSpellId, uint32(e->rarity),
                sClasslessMgr->AbilityCost(*e), st.abilities.count(e->firstSpellId) ? 1 : 0, e->passive ? 1 : 0,
                level(e), uint32(e->type));
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

    // TAL <tab> <page> [sort]. Each record:
    // talent:rank1spell:rarity:owned:max:row:active (active = the talent's
    // rank-1 spell is something you cast, not a passive)
    void SendTalentPage(Player* player, uint32 tabId, uint32 page, uint32 sort)
    {
        CharState& st = sClasslessMgr->GetState(player);

        struct Row { TalentPoolEntry const* t; std::string name; bool active; };
        std::vector<Row> list;
        for (auto const& [talentId, t] : sClasslessMgr->Talents())
            if (t.enabled && t.tabId == tabId)
            {
                SpellInfo const* info = sSpellMgr->GetSpellInfo(t.rankSpells[0]);
                list.push_back({ &t, info && info->SpellName[0] ? info->SpellName[0] : "",
                                 info && !info->IsPassive() });
            }
        auto tree = [](Row const& a, Row const& b)
        {
            return a.t->row != b.t->row ? a.t->row < b.t->row : a.t->col < b.t->col;
        };
        std::stable_sort(list.begin(), list.end(), [&](Row const& a, Row const& b)
        {
            switch (sort)
            {
                case SORT_LEVEL_DESC:
                    return a.t->row != b.t->row ? a.t->row > b.t->row : a.t->col < b.t->col;
                case SORT_NAME_ASC:
                    return a.name != b.name ? a.name < b.name : tree(a, b);
                case SORT_NAME_DESC:
                    return a.name != b.name ? a.name > b.name : tree(a, b);
                case SORT_TYPE:
                    return a.active != b.active ? a.active : tree(a, b);
                default:
                    return tree(a, b);
            }
        });

        uint32 totalPages = list.empty() ? 1 : (uint32(list.size()) + TAL_PAGE - 1) / TAL_PAGE;
        if (page >= totalPages)
            page = totalPages - 1;

        std::string body = Acore::StringFormat("TL|{}|{}|{}|", tabId, page, totalPages);
        uint32 start = page * TAL_PAGE;
        for (uint32 i = start; i < list.size() && i < start + TAL_PAGE; ++i)
        {
            TalentPoolEntry const* t = list[i].t;
            uint8 owned = 0;
            if (auto itr = st.talents.find(t->talentId); itr != st.talents.end())
                owned = itr->second;
            body += Acore::StringFormat("{}:{}:{}:{}:{}:{}:{};", t->talentId, t->rankSpells[0],
                uint32(t->rarity), owned, t->maxRank, t->row, list[i].active ? 1 : 0);
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
            // The rank IS the rarity for a talent, and the reveal popup already
            // says so ("Divine Strength 4/5 (Epic)"). Sending the talent's own
            // base rarity instead left My Build showing every talent in the
            // colour of its tree row, so a rank 5 read as common.
            std::string piece = Acore::StringFormat("{}:{}:{}:{}:{};", talentId,
                t->rankSpells[0], uint32(sClasslessMgr->RankRarity(*t, rank)), rank, t->maxRank);
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

    // Native attack power per stat point for the configured chassis, mirroring
    // the branches in Player::UpdateAttackPowerAndDamage. The addon quotes
    // these in the stat tooltips, so they have to follow the chassis rather
    // than assume Paladin: a Shaman chassis turns Agility into melee attack
    // power where a Paladin one does not.
    static void ChassisAPRates(uint8 cls, float& strMelee, float& agiMelee, float& agiRanged)
    {
        switch (cls)
        {
            case CLASS_WARRIOR:
            case CLASS_PALADIN:
            case CLASS_DEATH_KNIGHT:
            case CLASS_DRUID:          // out of forms
                strMelee = 2.0f; agiMelee = 0.0f; break;
            case CLASS_HUNTER:
            case CLASS_SHAMAN:
            case CLASS_ROGUE:
                strMelee = 1.0f; agiMelee = 1.0f; break;
            default:                   // mage, priest, warlock
                strMelee = 1.0f; agiMelee = 0.0f; break;
        }
        // Every class draws ranged attack power from Agility at 1 per point.
        agiRanged = 1.0f;
    }

    // Per-point rates the core reads out of its game tables. These are indexed
    // by class AND level, so there is no single number to print: a point of
    // Agility is worth less crit at 80 than at 20. Reading the same stores the
    // core reads, with the same indexing as Player::GetMeleeCritFromAgility and
    // friends, keeps the tooltip honest at every level instead of quoting a
    // level 80 figure to a level 12 Hero.
    //
    // Percentages come back per point; regeneration is per point of Spirit at
    // the character's current Intellect, since the core's formula is
    // sqrt(Intellect) * Spirit * ratio.
    static void ChassisTableRates(Player* player, uint8 cls,
                                  float& critPerAgi, float& spellCritPerInt,
                                  float& mp5PerSpi, float& hp5PerSpi)
    {
        critPerAgi = spellCritPerInt = mp5PerSpi = hp5PerSpi = 0.0f;
        uint8 level = player->GetLevel();
        if (level > GT_MAX_LEVEL)
            level = GT_MAX_LEVEL;
        uint32 const row = (uint32(cls) - 1) * GT_MAX_LEVEL + level - 1;

        if (GtChanceToMeleeCritEntry const* e = sGtChanceToMeleeCritStore.LookupEntry(row))
            critPerAgi = e->ratio * 100.0f;
        if (GtChanceToSpellCritEntry const* e = sGtChanceToSpellCritStore.LookupEntry(row))
            spellCritPerInt = e->ratio * 100.0f;

        // Mana regen is per 5 seconds in the client's own terms, and scales
        // with the square root of Intellect, so quote it at what the Hero has.
        if (GtRegenMPPerSptEntry const* e = sGtRegenMPPerSptStore.LookupEntry(row))
            mp5PerSpi = std::sqrt(player->GetStat(STAT_INTELLECT)) * e->ratio * 5.0f;
        if (GtRegenHPPerSptEntry const* e = sGtRegenHPPerSptStore.LookupEntry(row))
            hp5PerSpi = std::sqrt(player->GetStat(STAT_INTELLECT)) * e->ratio * 5.0f;
    }

    void SendStats(Player* player)
    {
        CharState& st = sClasslessMgr->GetState(player);
        Config const& cfg = sClasslessMgr->cfg;
        uint32 budget = sClasslessMgr->StatBudget(player);
        uint32 spent = sClasslessMgr->SpentStatPoints(st);
        // Fields 11+ are the universal-stat RATES. The addon needs them to tell
        // a player what a point of a stat is actually doing for them;
        // hard-coding the shipped defaults client-side would lie on any realm
        // that tuned them. Appended rather than inserted, so an addon that
        // predates them keeps working on the fields it knows.
        float strMeleeAP = 0.0f, agiMeleeAP = 0.0f, agiRangedAP = 0.0f;
        ChassisAPRates(cfg.chassisEnable ? cfg.chassisClass : player->getClass(),
                       strMeleeAP, agiMeleeAP, agiRangedAP);
        float critPerAgi = 0.0f, spellCritPerInt = 0.0f, mp5PerSpi = 0.0f, hp5PerSpi = 0.0f;
        ChassisTableRates(player, cfg.chassisEnable ? cfg.chassisClass : player->getClass(),
                          critPerAgi, spellCritPerInt, mp5PerSpi, hp5PerSpi);
        SendAddon(player, Acore::StringFormat("ST|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}",
            budget, budget > spent ? budget - spent : 0, cfg.statValuePerPoint,
            st.statAlloc[0], st.statAlloc[1], st.statAlloc[2], st.statAlloc[3], st.statAlloc[4],
            cfg.statsEnable ? 1 : 0,
            sClasslessMgr->IsExempt(player) ? 0 : 1,
            cfg.usMeleeAPPerAgi, cfg.usRangedAPPerAgi, cfg.usSpellPowerPerInt,
            strMeleeAP, agiMeleeAP, agiRangedAP,
            critPerAgi, spellCritPerInt, mp5PerSpi, hp5PerSpi));
    }

    // AR|id|name|description|abilities|talent ranks|following
    void SendArchetypes(Player* player)
    {
        CharState& st = sClasslessMgr->GetState(player);
        for (auto const& [id, arch] : sClasslessMgr->Archetypes())
        {
            uint32 ranks = 0;
            for (auto const& [talentId, rank] : arch.talents)
                ranks += rank;
            SendAddon(player, Acore::StringFormat("AR|{}|{}|{}|{}|{}|{}",
                id, SanitizeText(arch.name), SanitizeText(arch.description),
                uint32(arch.abilities.size()), ranks, st.archetype == id ? 1 : 0));
        }
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
            SendAbilityPage(player, uint8(argNum(1)), argNum(2), argNum(3), argNum(4));
        else if (cmd == "TABS")
            SendTalentTabs(player);
        else if (cmd == "TAL")
            SendTalentPage(player, argNum(1), argNum(2), argNum(3));
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
        else if (cmd == "RRALL")
        {
            // starting hand: reroll everything unlocked in one authoritative pass
            uint32 n = sClasslessMgr->RerollUnlockedAbilities(player, &err);
            if (n)
                SendOk(player, "RRALL");
            else
                SendErr(player, err.empty() ? "Nothing to reroll: everything is locked." : err);
        }
        else if (cmd == "RRT")
            // "RRT <talentId> [extraScrolls]" -- each extra scroll buys a
            // chance to keep the talent and raise its rank instead
            sClasslessMgr->Reroll(player, true, argNum(1), &err, argNum(2))
                ? SendOk(player, "RRT") : SendErr(player, err);
        else if (cmd == "LOCK")
        {
            // "LOCK <id> <0|1>" sets the padlock outright; "LOCK <id>" still
            // flips it, for the chat command, the NPC and any addon built
            // before the state was part of the message. A flip is only safe
            // while both ends already agree on where the padlock is.
            bool const ok = args.size() > 2
                ? sClasslessMgr->SetLock(player, argNum(1), argNum(2) != 0, &err)
                : sClasslessMgr->ToggleLock(player, argNum(1), &err);
            if (ok)
            {
                SendOk(player, "LOCK");
                // and the padlock the player ends up looking at comes back
                // from here, rather than from what the client assumed
                SendOwnedAbilities(player);
            }
            else
                SendErr(player, err);
        }
        else if (cmd == "ARCHAPPLY")
            sClasslessMgr->ApplyArchetype(player, argNum(1), &err) ? SendOk(player, "ARCH") : SendErr(player, err);
        else if (cmd == "REBIRTH")
            sClasslessMgr->Rebirth(player, Mode(uint8(argNum(1))), &err) ? SendOk(player, "REBIRTH") : SendErr(player, err);
        else if (cmd == "BUYSCROLL")
            // Any argument an older addon still sends is ignored: there is one
            // scroll now, good for abilities and talents alike.
            sClasslessMgr->BuyScroll(player, &err) ? SendOk(player, "BUYSCROLL") : SendErr(player, err);
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
