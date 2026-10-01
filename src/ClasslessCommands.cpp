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
 * .classless and .wildcard command families — the scriptable counterpart
 * of the Hero Advancement NPC (also the surface a client addon would drive).
 */

#include "Chat.h"
#include "ChatCommand.h"
#include "ClasslessMgr.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "StringConvert.h"
#include "StringFormat.h"
#include "Tokenize.h"

#include <algorithm>

using namespace Acore::ChatCommands;
using namespace ClasslessWildcard;

class classless_commandscript : public CommandScript
{
public:
    classless_commandscript() : CommandScript("classless_commandscript") { }

    ChatCommandTable GetCommands() const override
    {
        static ChatCommandTable classlessTable =
        {
            { "status",  HandleStatus,        SEC_PLAYER, Console::No },
            { "mode",    HandleMode,          SEC_PLAYER, Console::No },
            { "learn",   HandleLearn,         SEC_PLAYER, Console::No },
            { "unlearn", HandleUnlearn,       SEC_PLAYER, Console::No },
            { "talent",  HandleTalent,        SEC_PLAYER, Console::No },
            { "respec",  HandleRespec,        SEC_PLAYER, Console::No },
            { "stats",   HandleStats,         SEC_PLAYER, Console::No },
            { "stat",    HandleStat,          SEC_PLAYER, Console::No },
            { "bar",     HandleBar,           SEC_PLAYER, Console::No },
            { "archetypes", HandleArchetypes, SEC_PLAYER, Console::No },
            { "archetype", HandleArchetype,   SEC_PLAYER, Console::No },
            { "rebirth", HandleRebirth,       SEC_PLAYER, Console::No },
            { "path",    HandlePath,          SEC_PLAYER, Console::No },
            { "challenges", HandleChallenges, SEC_PLAYER, Console::No },
            { "run",     HandleRun,           SEC_PLAYER, Console::No },
        };
        static ChatCommandTable wildcardTable =
        {
            { "status",  HandleStatus,        SEC_PLAYER, Console::No },
            { "reroll",  HandleReroll,        SEC_PLAYER, Console::No },
            { "rerolltalent", HandleRerollTalent, SEC_PLAYER, Console::No },
            { "lock",    HandleLock,          SEC_PLAYER, Console::No },
        };
        static ChatCommandTable root =
        {
            { "classless", classlessTable },
            { "wildcard",  wildcardTable },
        };
        return root;
    }

    static bool CheckEnabled(ChatHandler* handler)
    {
        if (!sClasslessMgr->cfg.enabled)
        {
            handler->SendSysMessage("The classless system is disabled on this realm.");
            return false;
        }
        return true;
    }

    static bool HandleStatus(ChatHandler* handler)
    {
        if (!CheckEnabled(handler))
            return true;
        Player* player = handler->GetSession()->GetPlayer();
        CharState& st = sClasslessMgr->GetState(player);

        handler->PSendSysMessage("Mode: {}", st.mode == Mode::Wildcard ? "Wildcard" :
            (st.mode == Mode::Classless ? "Classless" : "not chosen yet"));
        handler->PSendSysMessage("Abilities: {} | Talents: {}", st.abilities.size(), st.talents.size());
        if (st.mode == Mode::Classless)
        {
            handler->PSendSysMessage("Ability Essence: {} | Talent Essence: {}", st.abilityEssence, st.talentEssence);
            if (st.archetype)
            {
                std::string next;
                auto queue = sClasslessMgr->ArchetypeQueue(player);
                if (!queue.empty())
                    next = queue.front().second > player->GetLevel()
                        ? Acore::StringFormat(" (next: {} at level {})", sClasslessMgr->SpellNameOf(queue.front().first), uint32(queue.front().second))
                        : Acore::StringFormat(" (next: {}, when you have the Ability Essence)", sClasslessMgr->SpellNameOf(queue.front().first));
                handler->PSendSysMessage("Following: |cffffff00{}|r{}", sClasslessMgr->ArchetypeName(st.archetype), next);
            }
        }
        if (st.mode == Mode::Wildcard)
        {
            handler->PSendSysMessage("Rerolls: {} (you earn one with every roll the Wildcard deals; spend on either)",
                st.rerolls);
            handler->PSendSysMessage("Reroll pity: {} (synergy chance {}%)", st.pity,
                std::min<uint32>(sClasslessMgr->cfg.wcSynergyBaseChance + st.pity * sClasslessMgr->cfg.wcSynergyIncrement, 100));
            if (st.bans.empty())
                handler->PSendSysMessage("On reroll cooldown: none");
            else
            {
                // Show the shortest remaining wait, so the number means
                // something: cooldowns run in ROLLS, and on the shipped cadence
                // a Hero earns about 1.5 of those per level.
                int32 soonest = st.bans.front().rollsLeft;
                for (auto const& ban : st.bans)
                    soonest = std::min(soonest, ban.rollsLeft);
                handler->PSendSysMessage(
                    "On reroll cooldown: {} (things you rerolled; the next one returns in {} rolls)",
                    uint32(st.bans.size()), uint32(std::max<int32>(0, soonest)));
            }
        }
        return true;
    }

    static bool HandleMode(ChatHandler* handler, std::string modeArg)
    {
        if (!CheckEnabled(handler))
            return true;
        Player* player = handler->GetSession()->GetPlayer();

        std::string err;
        if (modeArg == "classless")
            sClasslessMgr->SetMode(player, Mode::Classless, &err);
        else if (modeArg == "wildcard")
            sClasslessMgr->SetMode(player, Mode::Wildcard, &err);
        else
        {
            handler->SendSysMessage("Usage: .classless mode classless | wildcard");
            return true;
        }
        if (!err.empty())
            handler->SendSysMessage(err);
        return true;
    }

    static bool HandleLearn(ChatHandler* handler, uint32 spellId)
    {
        if (!CheckEnabled(handler))
            return true;
        std::string err;
        if (!sClasslessMgr->BuyAbility(handler->GetSession()->GetPlayer(), spellId, &err) && !err.empty())
            handler->SendSysMessage(err);
        return true;
    }

    static bool HandleUnlearn(ChatHandler* handler, uint32 spellId)
    {
        if (!CheckEnabled(handler))
            return true;
        std::string err;
        if (!sClasslessMgr->UnlearnAbility(handler->GetSession()->GetPlayer(), spellId, &err) && !err.empty())
            handler->SendSysMessage(err);
        return true;
    }

    static bool HandleTalent(ChatHandler* handler, uint32 talentId)
    {
        if (!CheckEnabled(handler))
            return true;
        std::string err;
        if (!sClasslessMgr->BuyTalentRank(handler->GetSession()->GetPlayer(), talentId, &err) && !err.empty())
            handler->SendSysMessage(err);
        return true;
    }

    static bool HandleRespec(ChatHandler* handler)
    {
        if (!CheckEnabled(handler))
            return true;
        std::string err;
        if (!sClasslessMgr->Respec(handler->GetSession()->GetPlayer(), &err) && !err.empty())
            handler->SendSysMessage(err);
        return true;
    }

    static int8 StatIndexFromName(std::string const& name)
    {
        if (name == "str") return 0;
        if (name == "agi") return 1;
        if (name == "sta") return 2;
        if (name == "int") return 3;
        if (name == "spi") return 4;
        return -1;
    }

    static bool HandleBar(ChatHandler* handler, std::string barName)
    {
        if (!CheckEnabled(handler))
            return true;
        Player* player = handler->GetSession()->GetPlayer();
        uint8 idx = 255;
        if (barName == "mana") idx = 0;
        else if (barName == "rage") idx = 1;
        else if (barName == "energy") idx = 3;
        else if (barName != "default")
        {
            handler->SendSysMessage("Usage: .classless bar mana|rage|energy|default");
            return true;
        }
        std::string err;
        if (sClasslessMgr->SetDisplayPower(player, idx, &err))
            handler->PSendSysMessage("Main resource bar set to {}.", barName);
        else
            handler->PSendSysMessage("{}", err);
        return true;
    }

    static bool HandleStats(ChatHandler* handler)
    {
        if (!CheckEnabled(handler))
            return true;
        Player* player = handler->GetSession()->GetPlayer();
        CharState& st = sClasslessMgr->GetState(player);
        uint32 budget = sClasslessMgr->StatBudget(player);
        uint32 spent = sClasslessMgr->SpentStatPoints(st);
        uint32 v = sClasslessMgr->cfg.statValuePerPoint;
        handler->PSendSysMessage("Stat points: {} spent / {} total ({} unspent). Each point grants +{} stat.",
            spent, budget, budget > spent ? budget - spent : 0, v);
        handler->PSendSysMessage("STR {} | AGI {} | STA {} | INT {} | SPI {} (points)",
            st.statAlloc[0], st.statAlloc[1], st.statAlloc[2], st.statAlloc[3], st.statAlloc[4]);
        handler->SendSysMessage("Set one with: .classless stat str|agi|sta|int|spi <points>. Reallocation is free.");
        return true;
    }

    static bool HandleStat(ChatHandler* handler, std::string statName, uint32 points)
    {
        if (!CheckEnabled(handler))
            return true;
        int8 index = StatIndexFromName(statName);
        if (index < 0)
        {
            handler->SendSysMessage("Usage: .classless stat str|agi|sta|int|spi <points>");
            return true;
        }
        Player* player = handler->GetSession()->GetPlayer();
        std::array<uint32, 5> alloc = sClasslessMgr->GetState(player).statAlloc;
        alloc[index] = points;
        std::string err;
        if (!sClasslessMgr->SetStatAllocation(player, alloc, &err) && !err.empty())
            handler->SendSysMessage(err);
        return true;
    }

    static bool HandleArchetypes(ChatHandler* handler)
    {
        if (!CheckEnabled(handler))
            return true;
        uint32 following = sClasslessMgr->GetState(handler->GetSession()->GetPlayer()).archetype;
        for (auto const& [id, arch] : sClasslessMgr->Archetypes())
        {
            uint32 ranks = 0;
            for (auto const& [talentId, rank] : arch.talents)
                ranks += rank;
            handler->PSendSysMessage("{}. |cffffff00{}|r: {} ({} abilities, {} talent ranks, level 1 to 80){}",
                id, arch.name, arch.description, uint32(arch.abilities.size()), ranks,
                following == id ? " |cff00ff00following|r" : "");
        }
        if (sClasslessMgr->Archetypes().empty())
            handler->SendSysMessage("No archetypes are configured on this realm.");
        else
            handler->SendSysMessage("Follow one with: .classless archetype <id>   Stop with: .classless archetype 0");
        return true;
    }

    static bool HandleArchetype(ChatHandler* handler, uint32 archetypeId)
    {
        if (!CheckEnabled(handler))
            return true;
        std::string err;
        if (!sClasslessMgr->ApplyArchetype(handler->GetSession()->GetPlayer(), archetypeId, &err) && !err.empty())
            handler->SendSysMessage(err);
        return true;
    }

    static bool ParsePath(std::string const& modeArg, Mode& target)
    {
        if (modeArg == "classless")
            target = Mode::Classless;
        else if (modeArg == "wildcard")
            target = Mode::Wildcard;
        else
            return false;
        return true;
    }

    // ".classless rebirth classless|wildcard [heirloom ability id ...]":
    // New Game Plus, at the level cap. The ids are owned ability lines
    // carried through; the panel is the friendlier way to choose them.
    static bool HandleRebirth(ChatHandler* handler, std::string modeArg, Tail heirloomArgs)
    {
        if (!CheckEnabled(handler))
            return true;
        std::string err;
        Mode target;
        if (!ParsePath(modeArg, target))
        {
            handler->SendSysMessage("Usage: .classless rebirth classless | wildcard [heirloom spell id ...] "
                                    "(level cap only: back to level 1 with a permanent Rebirth rank)");
            return true;
        }
        std::vector<uint32> heirlooms;
        for (std::string_view token : Acore::Tokenize(heirloomArgs, ' ', false))
            if (Optional<uint32> id = Acore::StringTo<uint32>(token))
                heirlooms.push_back(*id);
        if (!sClasslessMgr->Rebirth(handler->GetSession()->GetPlayer(), target, heirlooms, &err) && !err.empty())
            handler->SendSysMessage(err);
        return true;
    }

    // ".classless challenges": the list, with lives, reward and best result.
    static bool HandleChallenges(ChatHandler* handler)
    {
        if (!CheckEnabled(handler))
            return true;
        Player* player = handler->GetSession()->GetPlayer();
        CharState& st = sClasslessMgr->GetState(player);
        handler->SendSysMessage("Challenge runs (.classless run <id> [heirloom spell id ...]):");
        for (Challenge const& ch : ClasslessMgr::Challenges())
        {
            auto best = st.runBest.find(ch.id);
            handler->SendSysMessage(Acore::StringFormat("  {}. |cffffd100{}|r  {} {}, {} gold.  {}{}",
                uint32(ch.id), ch.name, uint32(ch.lives), ch.lives == 1 ? "life" : "lives", ch.rewardGold, ch.rule,
                best == st.runBest.end() ? ""
                    : Acore::StringFormat("  Best: level {}{}", uint32(best->second.first),
                                          best->second.second ? ", finished" : "")));
        }
        if (st.run)
            if (Challenge const* ch = ClasslessMgr::GetChallenge(st.run))
                handler->SendSysMessage(Acore::StringFormat("Live: |cffff4444{}|r, {} of {} lives. Shards: {}.",
                    ch->name, uint32(st.lives), uint32(st.livesMax), st.shards));
        return true;
    }

    // ".classless run <id> classless|wildcard [heirloom spell id ...]": start a
    // challenge run. The path is the one a Rebirth at the cap lands on; a
    // fresh Hero runs on the path they already chose whatever is typed.
    static bool HandleRun(ChatHandler* handler, uint32 challengeId, std::string modeArg, Tail heirloomArgs)
    {
        if (!CheckEnabled(handler))
            return true;
        std::string err;
        Mode target;
        if (!ParsePath(modeArg, target))
        {
            handler->SendSysMessage("Usage: .classless run <id> classless | wildcard [heirloom spell id ...] "
                                    "(.classless challenges lists the ids)");
            return true;
        }
        std::vector<uint32> heirlooms;
        for (std::string_view token : Acore::Tokenize(heirloomArgs, ' ', false))
            if (Optional<uint32> id = Acore::StringTo<uint32>(token))
                heirlooms.push_back(*id);
        if (!sClasslessMgr->StartRun(handler->GetSession()->GetPlayer(), uint8(challengeId), target, heirlooms, &err) && !err.empty())
            handler->SendSysMessage(err);
        return true;
    }

    // ".classless path classless|wildcard": the cheaper path change at the
    // current level, which is what "rebirth" used to mean.
    static bool HandlePath(ChatHandler* handler, std::string modeArg)
    {
        if (!CheckEnabled(handler))
            return true;
        std::string err;
        Mode target;
        if (!ParsePath(modeArg, target))
        {
            handler->SendSysMessage("Usage: .classless path classless | wildcard (wipes the build at this level, costs gold)");
            return true;
        }
        if (!sClasslessMgr->SwitchPath(handler->GetSession()->GetPlayer(), target, &err) && !err.empty())
            handler->SendSysMessage(err);
        return true;
    }

    static bool HandleReroll(ChatHandler* handler, uint32 spellId)
    {
        if (!CheckEnabled(handler))
            return true;
        std::string err;
        if (!sClasslessMgr->Reroll(handler->GetSession()->GetPlayer(), false, spellId, &err) && !err.empty())
            handler->SendSysMessage(err);
        return true;
    }

    static bool HandleRerollTalent(ChatHandler* handler, uint32 talentId, Optional<uint32> scrolls)
    {
        if (!CheckEnabled(handler))
            return true;
        std::string err;
        if (!sClasslessMgr->Reroll(handler->GetSession()->GetPlayer(), true, talentId, &err,
                                   scrolls.value_or(0)) && !err.empty())
            handler->SendSysMessage(err);
        return true;
    }

    static bool HandleLock(ChatHandler* handler, uint32 spellId)
    {
        if (!CheckEnabled(handler))
            return true;
        std::string err;
        if (!sClasslessMgr->ToggleLock(handler->GetSession()->GetPlayer(), spellId, &err) && !err.empty())
            handler->SendSysMessage(err);
        return true;
    }
};

void AddClasslessCommandScripts()
{
    new classless_commandscript();
}
