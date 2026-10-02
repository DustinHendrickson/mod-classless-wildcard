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
#include "CreatureAI.h"
#include "Item.h"
#include "ItemTemplate.h"
#include "Map.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SpellInfo.h"
#include "TemporarySummon.h"
#include "World.h"

#include <unordered_set>

using namespace ClasslessWildcard;

namespace
{
    constexpr uint32 RULE_TICK_MS = 5 * IN_MILLISECONDS;

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

// Re-level a creature that is already in the world. Creature::SelectLevel
// reads the TEMPLATE's level range, so a creature grown past it has its stats
// rebuilt here by hand from the same base-stat table SelectLevel uses, with
// the elite health and damage rates the realm configured. Declared in
// ClasslessMgr.cpp, which uses it for a nemesis and for the hunter.
void CW_ReLevelCreature(Creature* creature, uint8 level, bool elite)
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

    float const healthMod = sWorld->getRate(elite ? RATE_CREATURE_ELITE_ELITE_HP : RATE_CREATURE_NORMAL_HP);
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

    // The rank stays what the template says, so the elite damage rate the
    // core would read off the rank is folded into the base damage instead.
    float const damageMod = sWorld->getRate(elite ? RATE_CREATURE_ELITE_ELITE_DAMAGE : RATE_CREATURE_NORMAL_DAMAGE);
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
        PLAYERHOOK_ON_UPDATE
    }) { }

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
        if (sClasslessMgr->OnRun(killer, ChallengeId::Nemesis))
            sClasslessMgr->NemesisSlain(killer, killed);
        if (sClasslessMgr->OnRun(killer, ChallengeId::Pursued))
            sClasslessMgr->HunterSlain(killer, killed);
    }

    // ---- Big Game Hunter --------------------------------------------------
    // Normal enemies are worth nothing; elites, rares and bosses are worth
    // what they always were, and a quest pays double. Where the XP comes from
    // is the rule, so the hunt is for the dangerous things.
    void OnPlayerGiveXP(Player* player, uint32& amount, Unit* victim, uint8 source) override
    {
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
        UNITHOOK_ON_UNIT_DEATH
    }) { }

    // Fires for a CREATURE engaging a target (Creature.cpp); the target is the
    // Hero or the Hero's pet.
    void OnUnitEnterCombat(Unit* unit, Unit* victim) override
    {
        Creature* creature = unit ? unit->ToCreature() : nullptr;
        Player* player = OwnerPlayer(victim);
        if (!creature || !player || !WildCreature(creature))
            return;
        if (sClasslessMgr->ApplyNemesis(player, creature))
            return;
        if (sClasslessMgr->OnRun(player, ChallengeId::EliteWorld)
            && _eliteScaled.insert(creature->GetGUID()).second)
        {
            uint32 const max = creature->GetMaxHealth() * 3;
            uint32 const now = std::min<uint32>(max, creature->GetHealth() * 3);
            creature->SetMaxHealth(max);
            creature->SetHealth(now);
        }
        if (sClasslessMgr->OnRun(player, ChallengeId::Legion))
            CallTheLegion(creature, player);
    }

    void ModifyMeleeDamage(Unit* target, Unit* attacker, uint32& damage) override
    {
        Scale(target, attacker, damage);
    }

    void ModifySpellDamageTaken(Unit* target, Unit* attacker, int32& damage, SpellInfo const* /*spellInfo*/) override
    {
        if (damage <= 0)
            return;
        uint32 amount = uint32(damage);
        Scale(target, attacker, amount);
        damage = int32(amount);
    }

    // Bloodpact: every heal that reaches the Hero is halved. The leech below
    // adds health directly and never comes through here.
    void ModifyHealReceived(Unit* target, Unit* /*healer*/, uint32& heal, SpellInfo const* /*spellInfo*/) override
    {
        Player* player = target ? target->ToPlayer() : nullptr;
        if (player && heal && sClasslessMgr->OnRun(player, ChallengeId::Bloodpact))
            heal /= 2;
    }

    void OnUnitDeath(Unit* unit, Unit* /*killer*/) override
    {
        if (!unit || !unit->IsCreature())
            return;
        _eliteScaled.erase(unit->GetGUID());
        _legionCalled.erase(unit->GetGUID());
        _legionSpawn.erase(unit->GetGUID());
        sClasslessMgr->ForgetCreature(unit->GetGUID());
    }

private:
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
            || creature->GetCreatureType() == CREATURE_TYPE_CRITTER || creature->IsTrigger()
            || creature->IsCivilian())
            return;
        for (uint32 i = 0; i < LEGION_CALLED; ++i)
        {
            Position const pos = creature->GetNearPosition(3.0f, float(i) * 2.0f);
            TempSummon* called = creature->SummonCreature(creature->GetEntry(), pos,
                                                          TEMPSUMMON_TIMED_OR_DEAD_DESPAWN, LEGION_LINGER_MS);
            if (!called)
                continue;
            _legionSpawn.insert(called->GetGUID());
            called->SetHomePosition(pos);
            if (called->AI())
                called->AI()->AttackStart(player);
        }
    }

    // The damage rates, both ways. Elite World doubles a creature's hit on
    // the Hero. Glass, Berserker and Bloodpact read the Hero's own hits:
    // Glass adds a third, Berserker doubles below 35% health and takes 30%
    // off above 75%, Bloodpact heals the Hero for a share. Spiteful hands a
    // fifth of the Hero's hit back as damage from the enemy.
    void Scale(Unit* target, Unit* attacker, uint32& damage)
    {
        if (!damage || !attacker || !target)
            return;
        if (Player* victim = OwnerPlayer(target))
            if (WildCreature(attacker) && sClasslessMgr->OnRun(victim, ChallengeId::EliteWorld))
                damage *= 2;

        Player* dealer = attacker->ToPlayer();
        if (!dealer)
            return;
        if (sClasslessMgr->OnRun(dealer, ChallengeId::Glass))
            damage += damage / 3;
        if (sClasslessMgr->OnRun(dealer, ChallengeId::Berserker))
        {
            float const hp = dealer->GetHealthPct();
            if (hp < BERSERKER_LOW)
            {
                damage *= 2;
                dealer->RemoveMovementImpairingAuras(false);
            }
            else if (hp > BERSERKER_HIGH)
                damage -= damage * BERSERKER_HIGH_PENALTY / 100;
        }
        if (sClasslessMgr->OnRun(dealer, ChallengeId::Bloodpact) && dealer->IsAlive())
            dealer->ModifyHealth(int32(damage * BLOODPACT_LEECH_PCT / 100));
        if (sClasslessMgr->OnRun(dealer, ChallengeId::Spiteful) && WildCreature(target) && dealer->IsAlive())
            Unit::DealDamage(target, dealer, damage * SPITEFUL_PCT / 100, nullptr, DIRECT_DAMAGE,
                             SPELL_SCHOOL_MASK_NORMAL, nullptr, false);
    }

    std::unordered_set<ObjectGuid> _eliteScaled;
    std::unordered_set<ObjectGuid> _legionCalled;   // originals that have called
    std::unordered_set<ObjectGuid> _legionSpawn;    // the called, who never call
};

void AddClasslessChallengeScripts()
{
    new cw_challenge_rules();
    new cw_challenge_world();
}
