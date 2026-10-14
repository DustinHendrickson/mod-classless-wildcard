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
 * The rules of the challenge runs.
 *
 * A run is a life under one rule with a fixed number of lives, on either
 * path; ClasslessMgr owns the run itself (starting it, the lives, the end).
 * This file is where each rule touches the world: what a death
 * does, what a kill is worth, what a creature becomes when it engages a Hero
 * on a run, and how the Hero's own hits, heals and gear behave. One hook per
 * rule, and every hook asks the manager which rule is live before doing
 * anything. A rule changes the fight; none of them merely takes something
 * away.
 */

#include "ClasslessMgr.h"
#include "Chat.h"
#include "Creature.h"
#include "CellImpl.h"
#include "CreatureAI.h"
#include "DBCStores.h"
#include "Formulas.h"
#include "GameTime.h"
#include "GridNotifiers.h"
#include "GridNotifiersImpl.h"
#include "Group.h"
#include "Item.h"
#include "ItemTemplate.h"
#include "Map.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SpellAuraEffects.h"
#include "SpellInfo.h"
#include "SpellScript.h"
#include "SpellScriptLoader.h"
#include "StringFormat.h"
#include "TemporarySummon.h"
#include "World.h"

#include <unordered_set>

using namespace ClasslessWildcard;

namespace
{
    constexpr uint32 RULE_TICK_MS = 5 * IN_MILLISECONDS;
    // InvisibleStalker.mdx: the model that draws nothing
    constexpr uint32 NOTHING_DISPLAY_ID = 11686;
    // a nemesis's poison (Venomous) and Bloodlust's flare: stock "Poison", a
    // nature tick every 2 seconds, cast with its Hero's own numbers; and
    // Bloodlust's cast kit (2825's visual)
    constexpr uint32 NEMESIS_POISON_SPELL = 8313;
    constexpr uint32 NEMESIS_BLOODLUST_KIT = 6746;

    // Hourglass: seconds a level may take, by the level being left
    uint32 HourglassLimit(uint8 level)
    {
        if (level < 20)
            return 20 * MINUTE;
        if (level > 60)
            return 45 * MINUTE;
        return 30 * MINUTE;
    }
    constexpr uint32 HOURGLASS_WARNING = 5 * MINUTE;

    // Legion: how many more of its kind an enemy calls, and how long a
    // called one lingers if the fight never finds it
    constexpr uint32 LEGION_CALLED = 2;
    constexpr uint32 LEGION_LINGER_MS = 5 * MINUTE * IN_MILLISECONDS;

    constexpr uint32 SPITEFUL_PCT = 20;
    constexpr uint32 BLOODPACT_LEECH_PCT = 15;
    constexpr float  BERSERKER_LOW = 35.0f;
    constexpr float  BERSERKER_HIGH = 75.0f;
    constexpr uint32 BERSERKER_HIGH_PENALTY = 30;

    void Say(Player* player, std::string const& text)
    {
        ChatHandler(player->GetSession()).SendSysMessage(text);
    }

    // The player behind a unit: the player, or the owner of their pet.
    Player* OwnerPlayer(Unit* unit)
    {
        if (!unit)
            return nullptr;
        if (Player* player = unit->ToPlayer())
            return player;
        Unit* owner = unit->GetOwner();
        return owner ? owner->ToPlayer() : nullptr;
    }

    // A creature nobody owns: the world's own, not a pet, totem or summon.
    bool WildCreature(Unit* unit)
    {
        return unit && unit->IsCreature() && !unit->IsPet() && !unit->IsTotem() && !unit->GetOwnerGUID();
    }
}

// The realm's health and melee damage rates for a rank, as the core applies
// them (Creature::_GetHealthMod is protected; _GetDamageMod is not).
static float CW_RankHealthRate(uint32 rank)
{
    switch (rank)
    {
        case CREATURE_ELITE_ELITE:     return sWorld->getRate(RATE_CREATURE_ELITE_ELITE_HP);
        case CREATURE_ELITE_RAREELITE: return sWorld->getRate(RATE_CREATURE_ELITE_RAREELITE_HP);
        case CREATURE_ELITE_WORLDBOSS: return sWorld->getRate(RATE_CREATURE_ELITE_WORLDBOSS_HP);
        case CREATURE_ELITE_RARE:      return sWorld->getRate(RATE_CREATURE_ELITE_RARE_HP);
        default:                       return sWorld->getRate(RATE_CREATURE_NORMAL_HP);
    }
}

// Re-level a creature that is already in the world, as `rank` would have it.
// Creature::SelectLevel reads the TEMPLATE's level range and rank, so a
// creature grown past it, or made a rank it is not, has its stats rebuilt
// here by hand from the same base-stat table SelectLevel uses, with the
// realm's Rate.Creature.* health and damage rates for that rank. The health
// goes in as the creature's own base stat, so the core rebuilding its health
// (an aura, a stat change) keeps it. Declared in ClasslessMgr.cpp, which uses
// it for Pursued's hunter: a creature that exists for one Hero only.
void CW_ReLevelCreature(Creature* creature, uint8 level, uint32 rank)
{
    if (!creature)
        return;
    CreatureTemplate const* cInfo = creature->GetCreatureTemplate();
    if (!cInfo)
        return;
    CreatureBaseStats const* stats = sObjectMgr->GetCreatureBaseStats(level, cInfo->unit_class);
    if (!stats)
        return;

    creature->SetLevel(level);

    float const healthMod = CW_RankHealthRate(rank);
    uint32 const health = std::max<uint32>(1, uint32(std::max<uint32>(1, stats->GenerateHealth(cInfo)) * healthMod));
    creature->SetCreateHealth(health);
    creature->SetMaxHealth(health);
    creature->SetHealth(health);
    creature->SetStatFlatModifier(UNIT_MOD_HEALTH, BASE_VALUE, float(health));

    uint32 const mana = stats->GenerateMana(cInfo);
    creature->SetCreateMana(mana);
    creature->SetMaxPower(POWER_MANA, mana);
    creature->SetPower(POWER_MANA, mana);
    creature->SetStatFlatModifier(UNIT_MOD_MANA, BASE_VALUE, float(mana));

    // The template's DamageModifier already carries the realm's damage rate
    // for the template's own rank (ObjectMgr multiplies it in at load) and the
    // core applies it on every hit, so the wanted rate REPLACES that one here
    // rather than stacking on top of it.
    float const rankRate = Creature::_GetDamageMod(cInfo->rank);
    float const damageMod = Creature::_GetDamageMod(int32(rank)) / (rankRate > 0.0f ? rankRate : 1.0f);
    float const base = stats->GenerateBaseDamage(cInfo) * damageMod;
    for (WeaponAttackType type : { BASE_ATTACK, OFF_ATTACK, RANGED_ATTACK })
    {
        creature->SetBaseWeaponDamage(type, MINDAMAGE, base);
        creature->SetBaseWeaponDamage(type, MAXDAMAGE, base * 1.5f);
    }
    creature->SetStatFlatModifier(UNIT_MOD_ATTACK_POWER, BASE_VALUE, float(stats->AttackPower));
    creature->SetStatFlatModifier(UNIT_MOD_ATTACK_POWER_RANGED, BASE_VALUE, float(stats->RangedAttackPower));
    creature->UpdateAllStats();
}

// Elite World makes every enemy its Hero can fight an elite, a rare a rare
// elite, for that Hero alone: one nobody owns, that can fight, and that is not
// already elite, rare elite or a world boss. Pets, totems, summons, critters
// and triggers never change. A "civilian" (flags_extra 2) does: the flag only
// means it never starts a fight, and many beasts carry it. Declared in
// ClasslessMgr.cpp, whose ChallengeViewOf asks it.
bool CW_EliteWorldCandidate(Creature const* creature)
{
    if (!creature || creature->IsPet() || creature->IsTotem() || creature->GetOwnerGUID()
        || creature->IsCritter() || creature->IsTrigger())
        return false;
    CreatureTemplate const* tmpl = creature->GetCreatureTemplate();
    return tmpl && (tmpl->rank == CREATURE_ELITE_NORMAL || tmpl->rank == CREATURE_ELITE_RARE);
}

// What a creature's view (ClasslessMgr::ChallengeViewOf) is worth against the
// creature as it really is: its health, and its damage, melee or spell, at
// the view's level and rank over its own, from the same base-stat table and
// realm rates the core builds it from.
static float CW_ViewHealthRatio(Creature const* creature, ClasslessMgr::ChallengeView const& view)
{
    CreatureTemplate const* tmpl = creature->GetCreatureTemplate();
    CreatureBaseStats const* now = tmpl ? sObjectMgr->GetCreatureBaseStats(creature->GetLevel(), tmpl->unit_class) : nullptr;
    CreatureBaseStats const* seen = tmpl ? sObjectMgr->GetCreatureBaseStats(view.level, tmpl->unit_class) : nullptr;
    if (!now || !seen)
        return 1.0f;
    float const from = float(std::max<uint32>(1, now->GenerateHealth(tmpl))) * CW_RankHealthRate(tmpl->rank);
    float const to = float(std::max<uint32>(1, seen->GenerateHealth(tmpl))) * CW_RankHealthRate(view.rank);
    return from > 0.0f ? to / from : 1.0f;
}

static float CW_ViewDamageRatio(Creature const* creature, ClasslessMgr::ChallengeView const& view, bool spell)
{
    CreatureTemplate const* tmpl = creature->GetCreatureTemplate();
    CreatureBaseStats const* now = tmpl ? sObjectMgr->GetCreatureBaseStats(creature->GetLevel(), tmpl->unit_class) : nullptr;
    CreatureBaseStats const* seen = tmpl ? sObjectMgr->GetCreatureBaseStats(view.level, tmpl->unit_class) : nullptr;
    if (!now || !seen)
        return 1.0f;
    float const base = now->GenerateBaseDamage(tmpl);
    float const level = base > 0.0f ? seen->GenerateBaseDamage(tmpl) / base : 1.0f;
    Creature* c = const_cast<Creature*>(creature);   // GetSpellDamageMod is not const
    float const from = spell ? c->GetSpellDamageMod(tmpl->rank) : Creature::_GetDamageMod(tmpl->rank);
    float const to = spell ? c->GetSpellDamageMod(int32(view.rank)) : Creature::_GetDamageMod(int32(view.rank));
    return level * (from > 0.0f ? to / from : 1.0f);
}

// One fight's worth of a nemesis copy's traits, kept on the copy itself.
struct CW_CopyFight : DataMap::Base
{
    uint64 brittleUntil = 0;   // game time, ms
    bool fled = false;
    bool enraged = false;
    bool warbandCalled = false;
    bool taunted = false;      // it has said its piece for this fight
};

// A creature made for one Hero alone (Warband's pack): it fights them only.
struct CW_PrivateTag : DataMap::Base
{
    ObjectGuid owner;
};

// End a fight between a creature and one unit: off its threat list and out of
// combat with it, whoever else it is fighting. For a nemesis's original and
// its Hero, who cannot see it, and a Hero's copy and anyone else. Declared in
// ClasslessMgr.cpp.
void CW_DropFight(Creature* creature, Unit* other)
{
    if (!creature || !other)
        return;
    creature->GetThreatMgr().ClearThreat(other);
    auto const& refs = creature->GetCombatManager().GetPvECombatRefs();
    if (auto itr = refs.find(other->GetGUID()); itr != refs.end())
        itr->second->EndCombat();
}

// Send the creatures around a Hero again, so their client draws them as the
// Hero's run now says (a run starting or ending). Declared in ClasslessMgr.cpp.
void CW_RefreshViewsAround(Player* player)
{
    if (!player || !player->IsInWorld())
        return;
    float const range = player->GetVisibilityRange();
    std::list<Unit*> nearby;
    Acore::AnyUnitInObjectRangeCheck check(player, range);
    Acore::UnitListSearcher<Acore::AnyUnitInObjectRangeCheck> searcher(player, nearby, check);
    Cell::VisitObjects(player, searcher, range);
    for (Unit* unit : nearby)
        if (Creature* creature = unit->ToCreature())
            ClasslessMgr::RefreshChallengeView(creature);
}

// =====================================================================
// What a Hero on a run earns, loses, wears and is healed for.
// =====================================================================
uint32 ClasslessMgr::HourglassSecondsLeft(Player* player)
{
    CharState* st = player ? FindState(player) : nullptr;
    if (!st || st->run != uint8(ChallengeId::Hourglass))
        return 0;
    uint32 const limit = HourglassLimit(player->GetLevel());
    return st->runData < limit ? limit - st->runData : 0;
}

namespace
{
    // the Hourglass sand holds still while the Hero is dead or where deaths are free
    bool HourglassPaused(Player* player)
    {
        return !player->IsAlive() || player->InBattleground() || player->InArena();
    }

    // free text inside one RT field: the list separators are its own
    std::string TrackerText(std::string s)
    {
        for (char& c : s)
            if (c == '|' || c == ':' || c == ';' || c == '\t' || c == '\n')
                c = ' ';
        return s;
    }
}

// "RT|run|lives|livesMax|a|b|c|d|list". What a to d and the list mean depends
// on the run:
//   Hourglass  seconds left, seconds this level allows, 1 while paused, and
//              the seconds left when the warning comes
//   Pursued    1 while a hunter is out, its level
//   Berserker  the low and high health percents, the damage given up above
//   Nemesis    how many nemeses, Vengeance, Vengeance needed to finish; each
//              nemesis goes in its own NL messages (PushNemesisList)
// Every other run sends zeros: its rule has nothing that changes.
void ClasslessMgr::PushRunTracker(Player* player)
{
    CharState* st = player ? FindState(player) : nullptr;
    if (!st)
        return;
    uint32 a = 0, b = 0, c = 0, d = 0;
    std::string list;
    switch (ChallengeId(st->run))
    {
        case ChallengeId::Hourglass:
            b = HourglassLimit(player->GetLevel());
            a = HourglassSecondsLeft(player);
            c = HourglassPaused(player) ? 1 : 0;
            d = HOURGLASS_WARNING;
            break;
        case ChallengeId::Pursued:
            if (st->hunterGuid)
                if (Creature* hunter = ObjectAccessor::GetCreature(*player, st->hunterGuid))
                    if (hunter->IsAlive())
                    {
                        a = 1;
                        b = hunter->GetLevel();
                    }
            break;
        case ChallengeId::Berserker:
            a = uint32(BERSERKER_LOW);
            b = uint32(BERSERKER_HIGH);
            c = BERSERKER_HIGH_PENALTY;
            break;
        case ChallengeId::Nemesis:
            a = uint32(st->nemeses.size());
            b = st->nemesisVengeance;
            c = sClasslessMgr->cfg.nemesisVengeanceToFinish;
            // each nemesis in detail goes in its own NL messages
            sClasslessMgr->PushNemesisList(player);
            break;
        default:
            break;
    }
    st->trackerTicks = 0;
    st->trackerPaused = c != 0 && st->run == uint8(ChallengeId::Hourglass);
    PushAddon(player, Acore::StringFormat("RT|{}|{}|{}|{}|{}|{}|{}|{}", uint32(st->run), uint32(st->lives),
                                          uint32(st->livesMax), a, b, c, d, list));
}

class cw_challenge_rules : public PlayerScript
{
public:
    cw_challenge_rules() : PlayerScript("cw_challenge_rules", {
        PLAYERHOOK_ON_PLAYER_KILLED_BY_CREATURE,
        PLAYERHOOK_ON_PVP_KILL,
        PLAYERHOOK_ON_CREATURE_KILL,
        PLAYERHOOK_ON_GIVE_EXP,
        PLAYERHOOK_ON_LEVEL_CHANGED,
        PLAYERHOOK_ON_AFTER_UPDATE_MAX_HEALTH,
        PLAYERHOOK_CAN_EQUIP_ITEM,
        PLAYERHOOK_ON_UPDATE,
        PLAYERHOOK_ON_BEFORE_TELEPORT
    }) { }

    // A Hero's nemesis copies stay where they live: leaving the map takes
    // them away, while they can still be reached on this one.
    bool OnPlayerBeforeTeleport(Player* player, uint32 mapid, float /*x*/, float /*y*/, float /*z*/,
                                float /*orientation*/, uint32 /*options*/, Unit* /*target*/) override
    {
        if (player && player->IsInWorld() && mapid != player->GetMapId())
            sClasslessMgr->DespawnNemesisCopies(player);
        return true;
    }

    // ---- deaths ---------------------------------------------------------
    void OnPlayerKilledByCreature(Creature* killer, Player* killed) override
    {
        sClasslessMgr->LoseLife(killed, killer);
    }

    void OnPlayerPVPKill(Player* killer, Player* killed) override
    {
        sClasslessMgr->LoseLife(killed, killer);
    }

    // ---- kills: Nemesis and the hunter ----------------------------------
    void OnPlayerCreatureKill(Player* killer, Creature* killed) override
    {
        if (!killer || !killed)
            return;
        // a nemesis is credited from cw_challenge_world::OnUnitDeath
        if (sClasslessMgr->OnRun(killer, ChallengeId::Pursued))
            sClasslessMgr->HunterSlain(killer, killed);
    }

    // ---- Big Game Hunter --------------------------------------------------
    // Normal enemies are worth nothing; elites, rares and bosses are worth
    // what they always were, and a quest pays double. Where the XP comes from
    // is the rule, so the hunt is for the dangerous things.
    void OnPlayerGiveXP(Player* player, uint32& amount, Unit* victim, uint8 source) override
    {
        // An elite in this Hero's eyes (Elite World, a nemesis) pays them what
        // the core pays for one: the experience of its level as they see it,
        // doubled for an elite (Acore::XP::Gain reads the creature's real
        // level and rank, so it never sees either). Nobody else's changes.
        if (amount && source == XPSOURCE_KILL)
            if (Creature* killed = victim ? victim->ToCreature() : nullptr)
            {
                // a Hero's copy of their nemesis is a rare elite of its real
                // level, and pays as one
                if (ClasslessMgr::NemesisCopyOwner(killed) == player->GetGUID() && !killed->isElite())
                    amount *= 2;
                ClasslessMgr::ChallengeView view;
                if (sClasslessMgr->ChallengeViewOf(player, killed, view))
                {
                    if (view.level != killed->GetLevel())
                    {
                        ContentLevels const content = GetContentLevelsForMapAndZone(killed->GetMapId(), killed->GetZoneId());
                        uint32 const from = Acore::XP::BaseGain(player->GetLevel(), killed->GetLevel(), content);
                        uint32 const to = Acore::XP::BaseGain(player->GetLevel(), view.level, content);
                        if (from)
                            amount = uint32(uint64(amount) * to / from);
                    }
                    if (!killed->isElite())
                        amount *= 2;
                }
            }

        if (!amount || !sClasslessMgr->OnRun(player, ChallengeId::BigGameHunter))
            return;
        if (source == XPSOURCE_QUEST || source == XPSOURCE_QUEST_DF)
        {
            amount *= 2;
            return;
        }
        if (source != XPSOURCE_KILL)
            return;
        Creature* creature = victim ? victim->ToCreature() : nullptr;
        if (!creature)
            return;
        CreatureTemplate const* tmpl = creature->GetCreatureTemplate();
        bool const dangerous = (tmpl && tmpl->rank != CREATURE_ELITE_NORMAL) || creature->IsDungeonBoss();
        if (!dangerous)
            amount = 0;
    }

    // ---- Hourglass: the clock resets with every level ---------------------
    void OnPlayerLevelChanged(Player* player, uint8 oldLevel) override
    {
        CharState* st = sClasslessMgr->FindState(player);
        if (!st || st->run != uint8(ChallengeId::Hourglass))
            return;
        if (player->GetLevel() > oldLevel)
        {
            st->runData = 0;
            sClasslessMgr->SaveState(player);
            sClasslessMgr->PushRunTracker(player);
        }
    }

    // ---- Glass ----------------------------------------------------------
    void OnPlayerAfterUpdateMaxHealth(Player* player, float& value) override
    {
        if (sClasslessMgr->OnRun(player, ChallengeId::Glass))
            value = std::max(1.0f, value * 0.5f);
    }

    // ---- Ironman: white gear only ----------------------------------------
    bool OnPlayerCanEquipItem(Player* player, uint8 /*slot*/, uint16& /*dest*/, Item* item,
                              bool /*swap*/, bool notLoading) override
    {
        // The same hook runs while the character's inventory is being loaded,
        // and a refusal there has the core mail the piece away. The run took
        // off anything above white when it started, so only a player's own
        // equip attempt is answered.
        if (!notLoading || !item || !sClasslessMgr->OnRun(player, ChallengeId::Ironman))
            return true;
        if (item->GetTemplate()->Quality <= ITEM_QUALITY_NORMAL)
            return true;
        Say(player, "|cffff4444Ironman|r: only white gear on this run.");
        return false;
    }

    // ---- the clock: Pursued's hunter, Hourglass's level timer --------------
    void OnPlayerUpdate(Player* player, uint32 diff) override
    {
        CharState* st = sClasslessMgr->FindState(player);
        if (!st || !st->run || !player->IsInWorld())
            return;
        if (st->run == uint8(ChallengeId::Pursued))
            sClasslessMgr->HunterTick(player, diff);

        st->ruleTickMs += diff;
        if (st->ruleTickMs < RULE_TICK_MS)
            return;
        st->ruleTickMs = 0;

        if (st->run == uint8(ChallengeId::Nemesis))
            sClasslessMgr->NemesisTick(player);

        // The sand holds still in battlegrounds and arenas, where deaths are free.
        if (st->run == uint8(ChallengeId::Hourglass) && player->IsAlive()
            && !player->InBattleground() && !player->InArena())
        {
            uint32 const limit = HourglassLimit(player->GetLevel());
            uint32 const before = st->runData;
            st->runData += RULE_TICK_MS / IN_MILLISECONDS;
            if (before < limit - HOURGLASS_WARNING && st->runData >= limit - HOURGLASS_WARNING)
                Say(player, "|cffff8800Hourglass|r: five minutes left on this level.");
            if (st->runData >= limit)
            {
                Say(player, "|cffff4444Hourglass|r: the sand ran out.");
                sClasslessMgr->LoseLife(player, nullptr);   // resets the clock
            }
        }

        // The tracker counts down on its own between these; this keeps it
        // honest, and tells it at once when the sand stops or starts again.
        if (st->run == uint8(ChallengeId::Hourglass) || st->run == uint8(ChallengeId::Pursued))
        {
            bool const pausedNow = st->run == uint8(ChallengeId::Hourglass) && HourglassPaused(player);
            if (++st->trackerTicks >= 6 || pausedNow != st->trackerPaused)
                sClasslessMgr->PushRunTracker(player);
        }
    }
};

// =====================================================================
// What the world becomes for a Hero on a run: Nemesis marks, Elite World's
// scaling and Legion's reinforcements on engage, the damage rates both ways
// (Elite World, Glass, Spiteful, Bloodpact, Berserker), halved healing on
// Bloodpact, and forgetting a creature once it is dead so its respawn is
// handled afresh.
// =====================================================================
class cw_challenge_world : public UnitScript
{
public:
    cw_challenge_world() : UnitScript("cw_challenge_world", true, {
        UNITHOOK_ON_UNIT_ENTER_COMBAT,
        UNITHOOK_MODIFY_MELEE_DAMAGE,
        UNITHOOK_MODIFY_SPELL_DAMAGE_TAKEN,
        UNITHOOK_MODIFY_HEAL_RECEIVED,
        UNITHOOK_MODIFY_PERIODIC_DAMAGE_AURAS_TICK,
        UNITHOOK_ON_DAMAGE,
        UNITHOOK_ON_UNIT_DEATH,
        UNITHOOK_SHOULD_TRACK_VALUES_UPDATE_POS_BY_INDEX,
        UNITHOOK_ON_PATCH_VALUES_UPDATE,
        UNITHOOK_ON_AURA_APPLY
    }) { }

    // Brittle: its Hero's stun breaks its rage and leaves it open.
    void OnAuraApply(Unit* unit, Aura* aura) override
    {
        Creature* copy = unit ? unit->ToCreature() : nullptr;
        if (!copy || !aura || !(aura->GetSpellInfo()->GetAllEffectsMechanicMask() & (1 << MECHANIC_STUN)))
            return;
        ObjectGuid const owner = ClasslessMgr::NemesisCopyOwner(copy);
        if (owner.IsEmpty())
            return;
        Unit* caster = aura->GetCaster();
        Player* hero = caster ? OwnerPlayer(caster) : nullptr;
        if (!hero || hero->GetGUID() != owner)
            return;
        NemesisMark* mark = sClasslessMgr->MarkOfCopy(copy, hero);
        if (!mark || mark->weakness != NW_BRITTLE)
            return;
        CW_CopyFight* fight = copy->CustomData.GetDefault<CW_CopyFight>("cw_copy_fight");
        fight->brittleUntil = uint64(GameTime::GetGameTimeMS().count())
                              + uint64(sClasslessMgr->cfg.nemesisBrittleSeconds) * IN_MILLISECONDS;
        fight->enraged = false;
        if (sClasslessMgr->LearnNemesis(hero, copy, NEMESIS_LEARNED_WEAKNESS))
            ChatHandler(hero->GetSession()).SendNotification("Weakness found: brittle. A stun breaks it open.");
    }

    // A creature's level, health and size, as each viewer should see them.
    // The core builds one update for every viewer of a creature and patches
    // it per viewer; these four fields are marked for patching on every
    // creature, and OnPatchValuesUpdate writes a Hero's view of it into the
    // copy only that Hero is sent.
    bool ShouldTrackValuesUpdatePosByIndex(Unit const* unit, uint8 /*updateType*/, uint16 index) override
    {
        return unit && unit->IsCreature()
            && (index == OBJECT_FIELD_SCALE_X || index == UNIT_FIELD_LEVEL
                || index == UNIT_FIELD_HEALTH || index == UNIT_FIELD_MAXHEALTH
                // what it holds and rides: a hidden original draws neither
                || (index >= UNIT_VIRTUAL_ITEM_SLOT_ID && index < UNIT_VIRTUAL_ITEM_SLOT_ID + MAX_EQUIPMENT_ITEMS)
                || index == UNIT_FIELD_MOUNTDISPLAYID);
    }

    void OnPatchValuesUpdate(Unit const* unit, ByteBuffer& buffer, BuildValuesCachePosPointers& positions,
                             Player* target) override
    {
        Creature const* creature = unit ? unit->ToCreature() : nullptr;
        if (!creature || !target)
            return;
        // A nemesis's original is not there for its Hero: they fight their
        // own copy of it. Drawn with the core's draw-nothing model, holding no
        // weapons and riding nothing (both are drawn apart from the model),
        // and made unselectable, for them alone.
        if (sClasslessMgr->IsNemesisOriginalOf(target, creature))
        {
            if (positions.UnitFieldDisplayPos >= 0)
                buffer.put<uint32>(positions.UnitFieldDisplayPos, uint32(NOTHING_DISPLAY_ID));
            if (positions.UnitFieldFlagsPos >= 0)
                buffer.put<uint32>(positions.UnitFieldFlagsPos, creature->GetUInt32Value(UNIT_FIELD_FLAGS)
                                                                 | UNIT_FLAG_NOT_SELECTABLE | UNIT_FLAG_NON_ATTACKABLE);
            for (auto const& [index, at] : positions.other)
                if ((index >= UNIT_VIRTUAL_ITEM_SLOT_ID && index < UNIT_VIRTUAL_ITEM_SLOT_ID + MAX_EQUIPMENT_ITEMS)
                    || index == UNIT_FIELD_MOUNTDISPLAYID)
                    buffer.put<uint32>(at, 0u);
            return;
        }
        ClasslessMgr::ChallengeView view;
        if (positions.other.empty() || !sClasslessMgr->ChallengeViewOf(target, creature, view))
            return;
        float const health = CW_ViewHealthRatio(creature, view);
        for (auto const& [index, at] : positions.other)
        {
            switch (index)
            {
                case OBJECT_FIELD_SCALE_X:
                    buffer.put<float>(at, creature->GetObjectScale() * view.scale);
                    break;
                case UNIT_FIELD_LEVEL:
                    buffer.put<uint32>(at, uint32(view.level));
                    break;
                case UNIT_FIELD_HEALTH:
                {
                    uint32 const now = creature->GetHealth();
                    buffer.put<uint32>(at, now ? std::max<uint32>(1, uint32(float(now) * health)) : 0u);
                    break;
                }
                case UNIT_FIELD_MAXHEALTH:
                    buffer.put<uint32>(at, std::max<uint32>(1, uint32(float(creature->GetMaxHealth()) * health)));
                    break;
                default:
                    break;
            }
        }
    }

    // Fires for a CREATURE engaging a target (Creature.cpp); the target is the
    // Hero or the Hero's pet.
    void OnUnitEnterCombat(Unit* unit, Unit* victim) override
    {
        Creature* creature = unit ? unit->ToCreature() : nullptr;
        Player* player = OwnerPlayer(victim);
        if (!creature || !player)
            return;
        if (ObjectGuid const owner = ClasslessMgr::NemesisCopyOwner(creature); !owner.IsEmpty())
        {
            if (owner != player->GetGUID())
                CW_DropFight(creature, victim);   // a copy fights its own Hero alone
            else
                CopyEngages(creature, player);
            return;
        }
        if (!WildCreature(creature))
            return;
        if (sClasslessMgr->IsNemesisOriginalOf(player, creature))
        {
            CW_DropFight(creature, victim);   // they cannot see it, and fight their copy instead
            return;
        }
        if (sClasslessMgr->ApplyNemesis(player, creature))
            return;
        if (sClasslessMgr->OnRun(player, ChallengeId::Legion))
            CallTheLegion(creature, player);
    }

    void ModifyMeleeDamage(Unit* target, Unit* attacker, uint32& damage) override
    {
        Scale(target, attacker, damage);
        Exchange(target, attacker, damage, nullptr);
    }

    void ModifySpellDamageTaken(Unit* target, Unit* attacker, int32& damage, SpellInfo const* spellInfo) override
    {
        if (damage <= 0)
            return;
        uint32 amount = uint32(damage);
        Scale(target, attacker, amount);
        Exchange(target, attacker, amount, spellInfo);
        damage = int32(amount);
    }

    // Damage over time is its own hook, and the same hook carries heal-over-
    // time ticks a line before ModifyHealReceived: only damage ticks scale.
    void ModifyPeriodicDamageAurasTick(Unit* target, Unit* attacker, uint32& damage, SpellInfo const* spellInfo) override
    {
        if (!spellInfo || !(spellInfo->HasAura(SPELL_AURA_PERIODIC_DAMAGE) || spellInfo->HasAura(SPELL_AURA_PERIODIC_LEECH)
                            || spellInfo->HasAura(SPELL_AURA_PERIODIC_DAMAGE_PERCENT)))
            return;
        Scale(target, attacker, damage);
        Exchange(target, attacker, damage, spellInfo);
    }

    // What a hit actually did, once the core has rolled it, taken off armor
    // and absorbs, and is about to apply it: damage over time included, a
    // miss, dodge or parry never arriving here. Bloodpact's leech, Spiteful's
    // reflection and Berserker's snare break answer this, not the swing.
    void OnDamage(Unit* attacker, Unit* victim, uint32& damage) override
    {
        // Venomous: a nemesis's landed hit poisons its Hero, unless the poison
        // is already on them (its own ticks come through here too)
        if (Creature* copy = attacker ? attacker->ToCreature() : nullptr)
            if (Player* hero = victim ? victim->ToPlayer() : nullptr; hero && damage)
                if (NemesisMark* mark = sClasslessMgr->MarkOfCopy(copy, hero); mark && mark->Has(NS_VENOMOUS)
                    && !hero->HasAura(NEMESIS_POISON_SPELL, copy->GetGUID()))
                {
                    int32 tick = int32(hero->CountPctFromMaxHealth(int32(sClasslessMgr->cfg.nemesisVenomousPct)));
                    copy->CastCustomSpell(hero, NEMESIS_POISON_SPELL, &tick, nullptr, nullptr, true);
                    if (Aura* poison = hero->GetAura(NEMESIS_POISON_SPELL, copy->GetGUID()))
                    {
                        poison->SetMaxDuration(int32(sClasslessMgr->cfg.nemesisVenomousSeconds * IN_MILLISECONDS));
                        poison->RefreshDuration();
                    }
                }

        Player* dealer = attacker ? attacker->ToPlayer() : nullptr;
        if (!dealer || !victim || victim == attacker || !damage || !dealer->IsAlive())
            return;
        if (sClasslessMgr->OnRun(dealer, ChallengeId::Berserker) && dealer->GetHealthPct() < BERSERKER_LOW)
            dealer->RemoveMovementImpairingAuras(false);
        if (sClasslessMgr->OnRun(dealer, ChallengeId::Bloodpact))
            dealer->ModifyHealth(int32(damage * BLOODPACT_LEECH_PCT / 100));
        if (sClasslessMgr->OnRun(dealer, ChallengeId::Spiteful) && WildCreature(victim))
            if (uint32 const back = damage * SPITEFUL_PCT / 100)
                Unit::DealDamage(victim, dealer, back, nullptr, DIRECT_DAMAGE, SPELL_SCHOOL_MASK_NORMAL, nullptr, false);
    }

    // Bloodpact: every heal that reaches the Hero is halved. The leech below
    // adds health directly and never comes through here.
    void ModifyHealReceived(Unit* target, Unit* /*healer*/, uint32& heal, SpellInfo const* /*spellInfo*/) override
    {
        Player* player = target ? target->ToPlayer() : nullptr;
        if (player && heal && sClasslessMgr->OnRun(player, ChallengeId::Bloodpact))
            heal /= 2;
    }

    void OnUnitDeath(Unit* unit, Unit* killer) override
    {
        if (!unit || !unit->IsCreature())
            return;
        CreditNemesis(unit->ToCreature(), killer);
        for (AuraEffect const* eff : unit->GetAuraEffectsByType(SPELL_AURA_MOD_STALKED))
            if (eff->GetId() == ClasslessMgr::NEMESIS_TRACK_SPELL)
                if (Player* hero = ObjectAccessor::FindPlayer(eff->GetCasterGUID()))
                {
                    sClasslessMgr->SendNemesisMark(hero, unit->ToCreature(), false);
                    sClasslessMgr->SendNemesisTraits(hero, unit->ToCreature(), false);
                }
        _legionCalled.erase(unit->GetGUID());
        _legionSpawn.erase(unit->GetGUID());
        sClasslessMgr->ForgetCreature(unit->GetGUID());
        // passive, so death alone would leave a corpse on the minimap
        unit->RemoveAurasDueToSpell(ClasslessMgr::NEMESIS_TRACK_SPELL);
    }

private:
    // A nemesis is killed when it dies to its Hero, their pet or totem, or the
    // group that tagged it, not only when the Hero lands the killing blow:
    // OnPlayerCreatureKill fires for that last case alone. A Hero who is dead
    // when it falls keeps the mark, since the experience could not be given
    // back to them; the creature respawns still their nemesis.
    void CreditNemesis(Creature* creature, Unit* killer)
    {
        ObjectGuid const owner = ClasslessMgr::NemesisCopyOwner(creature);
        if (!creature || owner.IsEmpty())
            return;
        std::vector<Player*> heroes;
        auto add = [&heroes](Player* p)
        {
            if (p && std::find(heroes.begin(), heroes.end(), p) == heroes.end())
                heroes.push_back(p);
        };
        add(OwnerPlayer(killer));
        add(creature->GetLootRecipient());
        if (Group* group = creature->GetLootRecipientGroup())
            for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                if (Player* member = ref->GetSource(); member && member->IsInMap(creature))
                    add(member);
        for (Player* hero : heroes)
            if (hero->GetGUID() == owner && hero->IsAlive() && sClasslessMgr->OnRun(hero, ChallengeId::Nemesis))
                sClasslessMgr->NemesisSlain(hero, creature);
    }

    // Legion: the enemy calls two more of its kind, once per life. A called
    // one never calls (or every fight would be a flood), and nothing is
    // called for a boss, a critter, or anything that cannot fight. The copies
    // are the creature's own summons, not the player's, so they give XP and
    // loot like any other of their kind.
    void CallTheLegion(Creature* creature, Player* player)
    {
        if (_legionSpawn.count(creature->GetGUID()) || !_legionCalled.insert(creature->GetGUID()).second)
            return;
        CreatureTemplate const* tmpl = creature->GetCreatureTemplate();
        if (!tmpl || creature->IsDungeonBoss() || tmpl->rank == CREATURE_ELITE_WORLDBOSS
            || creature->GetCreatureType() == CREATURE_TYPE_CRITTER || creature->IsTrigger())
            return;
        for (uint32 i = 0; i < LEGION_CALLED; ++i)
        {
            Position const pos = creature->GetNearPosition(3.0f, float(i) * 2.0f);
            TempSummon* called = creature->SummonCreature(creature->GetEntry(), pos,
                                                          TEMPSUMMON_TIMED_OR_DEAD_DESPAWN, LEGION_LINGER_MS);
            if (!called)
                continue;
            _legionSpawn[called->GetGUID()] = player->GetGUID();
            called->SetHomePosition(pos);
            if (called->AI())
                called->AI()->AttackStart(player);
        }
    }

    // A nemesis's copy starts a fight with its Hero: they learn what it is,
    // Warband calls its two, Bloodlust shows.
    void CopyEngages(Creature* copy, Player* hero)
    {
        NemesisMark* mark = sClasslessMgr->MarkOfCopy(copy, hero);
        if (!mark)
            return;
        CW_CopyFight* fight = copy->CustomData.GetDefault<CW_CopyFight>("cw_copy_fight");
        if (!fight->taunted)
        {
            fight->taunted = true;
            sClasslessMgr->NemesisTaunt(hero, copy, *mark, ClasslessMgr::NemesisMoment::Engage);
        }
        if (sClasslessMgr->LearnNemesis(hero, copy, NEMESIS_LEARNED_STRENGTHS))
        {
            std::string list;
            for (uint8 s : mark->strengths)
                if (s != NS_NONE)
                    list += (list.empty() ? "" : ", ") + std::string(ClasslessMgr::NemesisStrengthName(s));
            Say(hero, Acore::StringFormat("|cffff8800{}|r: {}.", copy->GetName(), list));
        }
        if (mark->Has(NS_BLOODLUST))
            copy->SendPlaySpellVisual(NEMESIS_BLOODLUST_KIT);
        if (mark->Has(NS_WARBAND) && !fight->warbandCalled)
        {
            fight->warbandCalled = true;
            for (uint32 i = 0; i < sClasslessMgr->cfg.nemesisWarbandCount; ++i)
            {
                Position const pos = copy->GetNearPosition(3.0f, float(i) * 2.0f + 1.0f);
                TempSummon* called = hero->SummonCreature(copy->GetEntry(), pos,
                    TEMPSUMMON_TIMED_DESPAWN_OUT_OF_COMBAT, 30 * IN_MILLISECONDS, 0, nullptr, true);
                if (!called)
                    continue;
                called->CustomData.GetDefault<CW_PrivateTag>("cw_private")->owner = hero->GetGUID();
                CW_ReLevelCreature(called, hero->GetLevel(), CREATURE_ELITE_NORMAL);
                if (called->AI())
                    called->AI()->AttackStart(hero);
            }
            sClasslessMgr->NemesisSay(hero, copy, "calls its pack to its side!", true);
        }
    }

    // It strikes its Hero: Unyielding's rage, low on health.
    void CopyHits(Creature* copy, Player* hero, NemesisMark const& mark, uint32& damage)
    {
        if (!mark.Has(NS_UNYIELDING) || copy->GetHealthPct() >= float(sClasslessMgr->cfg.nemesisUnyieldingBelowPct))
            return;
        CW_CopyFight* fight = copy->CustomData.GetDefault<CW_CopyFight>("cw_copy_fight");
        if (uint64(GameTime::GetGameTimeMS().count()) < fight->brittleUntil)
            return;   // a stun broke it
        if (!fight->enraged)
        {
            fight->enraged = true;
            sClasslessMgr->NemesisSay(hero, copy, "becomes enraged!", true);
        }
        damage += damage * sClasslessMgr->cfg.nemesisUnyieldingPct / 100;
    }

    // Its Hero strikes it: Ironhide and Spellward, and its weakness.
    void CopyTakes(Creature* copy, Player* hero, NemesisMark const& mark, uint32& damage, uint32 school)
    {
        Config const& cfg = sClasslessMgr->cfg;
        CW_CopyFight* fight = copy->CustomData.GetDefault<CW_CopyFight>("cw_copy_fight");
        if ((school & SPELL_SCHOOL_MASK_NORMAL) && mark.Has(NS_IRONHIDE))
            damage -= damage * cfg.nemesisIronhidePct / 100;
        if ((school & SPELL_SCHOOL_MASK_MAGIC) && mark.Has(NS_SPELLWARD))
            damage -= damage * cfg.nemesisSpellwardPct / 100;

        static uint32 const schools[NW_COUNT] = { 0, SPELL_SCHOOL_MASK_FIRE, SPELL_SCHOOL_MASK_FROST,
            SPELL_SCHOOL_MASK_SHADOW, SPELL_SCHOOL_MASK_NATURE, SPELL_SCHOOL_MASK_ARCANE, SPELL_SCHOOL_MASK_HOLY, 0, 0 };
        if (mark.weakness < NW_COUNT && schools[mark.weakness] && (school & schools[mark.weakness]))
        {
            damage += damage * cfg.nemesisWeakSchoolPct / 100;
            if (sClasslessMgr->LearnNemesis(hero, copy, NEMESIS_LEARNED_WEAKNESS))
                ChatHandler(hero->GetSession()).SendNotification(Acore::StringFormat("Weakness found: {}.",
                    ClasslessMgr::NemesisWeaknessName(mark.weakness)));
        }
        if (mark.weakness == NW_BRITTLE && uint64(GameTime::GetGameTimeMS().count()) < fight->brittleUntil)
            damage += damage * cfg.nemesisBrittlePct / 100;
        if (mark.weakness == NW_COWARDLY)
        {
            if (fight->fled)
                damage += damage * cfg.nemesisCowardlyPct / 100;
            else if (copy->GetHealth() > damage
                     && copy->GetHealth() - damage < copy->CountPctFromMaxHealth(int32(cfg.nemesisCowardlyFleePct)))
            {
                fight->fled = true;
                copy->GetMotionMaster()->MoveFleeing(hero, cfg.nemesisCowardlyFleeSeconds * IN_MILLISECONDS);
                sClasslessMgr->NemesisSay(hero, copy, "turns to flee!", true);
                if (sClasslessMgr->LearnNemesis(hero, copy, NEMESIS_LEARNED_WEAKNESS))
                    ChatHandler(hero->GetSession()).SendNotification("Weakness found: cowardly. Run it down.");
            }
        }
    }

    // Pursued's hunter and Legion's reinforcements exist for one Hero: the
    // hunter is that Hero's summon, a reinforcement was called against them.
    ObjectGuid PrivateOwner(Creature const* creature) const
    {
        if (ObjectGuid const owner = ClasslessMgr::NemesisCopyOwner(creature); !owner.IsEmpty())
            return owner;
        if (CW_PrivateTag const* tag = creature->CustomData.Get<CW_PrivateTag>("cw_private"))
            return tag->owner;
        if (creature->GetEntry() == ClasslessMgr::HUNTER_ENTRY && creature->IsSummon())
            return creature->ToTempSummon()->GetSummonerGUID();
        auto itr = _legionSpawn.find(creature->GetGUID());
        return itr != _legionSpawn.end() ? itr->second : ObjectGuid::Empty;
    }

    // A hit between a Hero and a creature their challenge changed, as the Hero
    // sees that creature: it strikes them and their pet as its view's level and
    // rank would, and takes their hits against that view's health. Nobody
    // else's fight with it changes. And a creature that exists for one Hero
    // fights that Hero alone: it harms no one else, and no one else harms it.
    void Exchange(Unit* target, Unit* attacker, uint32& damage, SpellInfo const* spellInfo)
    {
        if (!damage || !target || !attacker)
            return;
        bool const spell = spellInfo && spellInfo->DmgClass == SPELL_DAMAGE_CLASS_MAGIC;
        Creature* from = attacker->ToCreature();
        Creature* to = target->ToCreature();
        if (from)
            if (ObjectGuid const owner = PrivateOwner(from); !owner.IsEmpty())
                if (Player* hero = OwnerPlayer(target); !hero || hero->GetGUID() != owner)
                {
                    damage = 0;
                    return;
                }
        if (to)
            if (ObjectGuid const owner = PrivateOwner(to); !owner.IsEmpty())
                if (Player* hero = OwnerPlayer(attacker); !hero || hero->GetGUID() != owner)
                {
                    damage = 0;
                    return;
                }

        // a nemesis's original and its Hero never trade blows: it is hidden
        // from them, and their fight is with their copy
        if (from)
            if (Player* hero = OwnerPlayer(target); hero && sClasslessMgr->IsNemesisOriginalOf(hero, from))
            {
                damage = 0;
                return;
            }
        if (to)
            if (Player* hero = OwnerPlayer(attacker); hero && sClasslessMgr->IsNemesisOriginalOf(hero, to))
            {
                damage = 0;
                return;
            }

        // a nemesis's traits, in the fight with its Hero
        if (from)
            if (Player* hero = OwnerPlayer(target))
                if (NemesisMark* mark = sClasslessMgr->MarkOfCopy(from, hero))
                    CopyHits(from, hero, *mark, damage);
        if (to)
            if (Player* hero = OwnerPlayer(attacker))
                if (NemesisMark* mark = sClasslessMgr->MarkOfCopy(to, hero))
                    CopyTakes(to, hero, *mark, damage, spellInfo ? spellInfo->GetSchoolMask() : SPELL_SCHOOL_MASK_NORMAL);

        ClasslessMgr::ChallengeView view;
        if (from)
            if (Player* hero = OwnerPlayer(target); hero && sClasslessMgr->ChallengeViewOf(hero, from, view))
                damage = std::max<uint32>(1, uint32(float(damage) * CW_ViewDamageRatio(from, view, spell)));
        if (to)
            if (Player* hero = OwnerPlayer(attacker); hero && sClasslessMgr->ChallengeViewOf(hero, to, view))
                if (float const health = CW_ViewHealthRatio(to, view); health > 0.0f)
                    damage = std::max<uint32>(1, uint32(float(damage) / health));
    }

    // The Hero's own damage rates, on melee, direct spells and damage over
    // time alike. Glass adds a third, and Berserker doubles it below 35%
    // health and takes 30% off above 75%.
    void Scale(Unit* target, Unit* attacker, uint32& damage)
    {
        if (!damage || !attacker || !target)
            return;

        Player* dealer = attacker->ToPlayer();
        if (!dealer)
            return;
        if (sClasslessMgr->OnRun(dealer, ChallengeId::Glass))
            damage += damage / 3;
        if (sClasslessMgr->OnRun(dealer, ChallengeId::Berserker))
        {
            float const hp = dealer->GetHealthPct();
            if (hp < BERSERKER_LOW)
                damage *= 2;
            else if (hp > BERSERKER_HIGH)
                damage -= damage * BERSERKER_HIGH_PENALTY / 100;
        }
    }

    std::unordered_set<ObjectGuid> _legionCalled;   // originals that have called
    std::unordered_map<ObjectGuid, ObjectGuid> _legionSpawn;   // the called, who never call -> their Hero
};

// 36779 - Swear Vendetta (a stock dummy the client patch renames). Refused,
// with a reason on screen, where the rules say no; makes the target the
// Hero's Sworn nemesis where they say yes.
class spell_cw_swear_vendetta : public SpellScript
{
    PrepareSpellScript(spell_cw_swear_vendetta);

    SpellCastResult CheckCast()
    {
        Player* player = GetCaster() ? GetCaster()->ToPlayer() : nullptr;
        Unit* explicitTarget = GetExplTargetUnit();
        Creature* target = explicitTarget ? explicitTarget->ToCreature() : nullptr;
        std::string err;
        if (!player || !sClasslessMgr->CanSwearVendetta(player, target, &err))
        {
            if (player && !err.empty())
                ChatHandler(player->GetSession()).SendNotification(err);
            return SPELL_FAILED_DONT_REPORT;
        }
        return SPELL_CAST_OK;
    }

    void HandleDummy(SpellEffIndex /*effIndex*/)
    {
        Player* player = GetCaster() ? GetCaster()->ToPlayer() : nullptr;
        if (Creature* target = GetHitCreature(); player && target)
            sClasslessMgr->SwearVendetta(player, target);
    }

    void Register() override
    {
        OnCheckCast += SpellCheckCastFn(spell_cw_swear_vendetta::CheckCast);
        OnEffectHitTarget += SpellEffectFn(spell_cw_swear_vendetta::HandleDummy, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

void AddClasslessChallengeScripts()
{
    new cw_challenge_rules();
    new cw_challenge_world();
    RegisterSpellScript(spell_cw_swear_vendetta);
}
