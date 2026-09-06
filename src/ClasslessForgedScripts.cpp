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
 * The six forged spells that cannot be expressed in DBC rows alone.
 *
 * A spell made of rows cannot read the character: not what else was rolled, not
 * what school was last cast, not what is already on the target. Every idea that
 * ties a classless build together needs one of these, and the other eleven
 * forged spells need none.
 *
 * Each script has exactly one job. None of them redirects damage, moves a unit,
 * or has a pet cast the owner's spells -- those three shapes were cut from the
 * design rather than guarded, because they are where re-entrancy, desync and
 * misattributed threat come from.
 *
 * Which spell ids carry which script is decided by spell_script_names rows that
 * gen_forged_spells.py writes, one per rank, so adding a rank never means
 * editing this file.
 */

#include "ClasslessMgr.h"
#include "GameTime.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellMgr.h"
#include "SpellScript.h"
#include "Pet.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "PassiveAI.h"
#include "TemporarySummon.h"
#include "CellImpl.h"
#include "GridNotifiers.h"
#include "GridNotifiersImpl.h"
#include "SpellDefines.h"

#include <algorithm>
#include <unordered_map>
#include <unordered_set>
#include <vector>

using namespace ClasslessWildcard;

namespace
{
    // ---------------------------------------------------------------------
    // Shared state
    //
    // Both of the pieces below are keyed by character guid and are pure
    // caches: losing one costs a player one weave or one stack, never a
    // stuck aura. They are cleared on logout so a long-lived worldserver does
    // not accumulate a row per character it has ever seen.
    // ---------------------------------------------------------------------

    // Crossdraw: when did this character last land a damaging cast?
    std::unordered_map<ObjectGuid::LowType, uint32> _lastDamagingCastMs;

    // Repertoire: the open window, if there is one. The aura's own spell id is
    // kept because the line has several ranks and the watcher has to find the
    // exact aura it opened, not "a Repertoire".
    struct RepertoireWindow
    {
        uint32 auraSpellId = 0;
        std::unordered_set<uint32> used;
    };
    std::unordered_map<ObjectGuid::LowType, RepertoireWindow> _repertoireUsed;

    constexpr uint32 CROSSDRAW_WINDOW_MS = 5000;
    constexpr uint32 CROSSDRAW_COMPANION_OFFSET = 16;   // matches PER_RECIPE / 2
    constexpr uint8  REPERTOIRE_MAX_STACKS = 5;
    constexpr int32  REPERTOIRE_PER_STACK = 3;
    constexpr uint32 QUICKENING_MIN_POINTS = 20;      // rage plus energy, in displayed points
    constexpr int32  QUICKENING_POINTS_PER_PCT = 5;
    constexpr int32  QUICKENING_MAX_PCT = 20;
    constexpr uint32 RICOCHET_COMPANION_OFFSET = 16;    // matches PER_RECIPE / 2
    constexpr float  RICOCHET_RANGE = 8.0f;
    constexpr uint32 RICOCHET_MANA_PCT = 6;              // of maximum mana, per ricochet
    // the creature entries this module owns, from gen_forged_spells.py
    constexpr uint32 FORGED_CREATURE_FIRST = 990110;
    constexpr uint32 FORGED_CREATURE_LAST = 990130;
    constexpr int32  SURGE_PER_ABILITY_PCT = 8;
    constexpr int32  SURGE_MAX_PCT = 40;

    // A CAST, not a swing. Crossdraw asks whether a spell went out just before
    // the strike, so anything that deals weapon damage is explicitly not one:
    // counting strikes would let Crossdraw satisfy its own condition, and
    // pressing it twice would proc the bonus forever.
    bool IsDamagingSpellCast(SpellInfo const* info)
    {
        if (!info)
            return false;
        bool damaging = false;
        for (uint8 i = 0; i < MAX_SPELL_EFFECTS; ++i)
        {
            uint32 const effect = info->Effects[i].Effect;
            if (effect == SPELL_EFFECT_WEAPON_PERCENT_DAMAGE
                || effect == SPELL_EFFECT_WEAPON_DAMAGE
                || effect == SPELL_EFFECT_WEAPON_DAMAGE_NOSCHOOL
                || effect == SPELL_EFFECT_NORMALIZED_WEAPON_DMG)
                return false;
            if (effect == SPELL_EFFECT_SCHOOL_DAMAGE)
                damaging = true;
            else if (effect == SPELL_EFFECT_APPLY_AURA
                     && info->Effects[i].ApplyAuraName == SPELL_AURA_PERIODIC_DAMAGE)
                damaging = true;
        }
        return damaging;
    }
}

// =====================================================================
// Bookkeeping for the two scripts that need to watch what a Hero does.
//
// One PlayerScript rather than one per spell: the hook fires on every cast a
// character makes, so doing the least possible work here matters more than
// keeping the two features apart.
// =====================================================================
class cw_forged_watcher : public PlayerScript
{
public:
    cw_forged_watcher() : PlayerScript("cw_forged_watcher") { }

    void OnPlayerSpellCast(Player* player, Spell* spell, bool /*skipCheck*/) override
    {
        if (!player || !spell || !spell->GetSpellInfo())
            return;
        SpellInfo const* info = spell->GetSpellInfo();
        ObjectGuid::LowType const guid = player->GetGUID().GetCounter();

        if (IsDamagingSpellCast(info))
            _lastDamagingCastMs[guid] = uint32(GameTime::GetGameTimeMS().count());

        // Repertoire counts DISTINCT abilities, so a repeat is free to ignore.
        // The set is created when the aura goes up and dropped when it comes
        // down, so an absent entry means the buff is not running.
        auto itr = _repertoireUsed.find(guid);
        if (itr == _repertoireUsed.end())
            return;
        if (!itr->second.used.insert(info->Id).second)
            return;

        uint8 const stacks = uint8(std::min<size_t>(itr->second.used.size(), REPERTOIRE_MAX_STACKS));
        if (Aura* aura = player->GetAura(itr->second.auraSpellId, player->GetGUID()))
            if (aura->GetStackAmount() != stacks)
                aura->SetStackAmount(stacks);
    }

    void OnPlayerLogout(Player* player) override
    {
        ObjectGuid::LowType const guid = player->GetGUID().GetCounter();
        _lastDamagingCastMs.erase(guid);
        _repertoireUsed.erase(guid);
    }
};

// =====================================================================
// Crossdraw -- a strike that pays extra if you cast a spell just before it.
//
// The bonus is a SEPARATE spell rather than a second effect on this one,
// because a spell's school is a property of its row: an arcane hit has to come
// from an arcane row. The companion sits a fixed distance up the id block from
// its rank, so rank 3's bonus is rank 3's id plus sixteen.
// =====================================================================
class spell_cw_crossdraw : public SpellScript
{
    PrepareSpellScript(spell_cw_crossdraw);

    void HandleWeave()
    {
        Player* caster = GetCaster() ? GetCaster()->ToPlayer() : nullptr;
        Unit* target = GetHitUnit();
        if (!caster || !target || !target->IsAlive())
            return;

        auto itr = _lastDamagingCastMs.find(caster->GetGUID().GetCounter());
        if (itr == _lastDamagingCastMs.end())
            return;
        uint32 const now = uint32(GameTime::GetGameTimeMS().count());
        if (now < itr->second || now - itr->second > CROSSDRAW_WINDOW_MS)
            return;

        uint32 const companion = GetSpellInfo()->Id + CROSSDRAW_COMPANION_OFFSET;
        if (!sSpellMgr->GetSpellInfo(companion))
            return;   // the rank's companion row is missing: land the strike alone
        caster->CastSpell(target, companion, true);
    }

    void Register() override
    {
        AfterHit += SpellHitFn(spell_cw_crossdraw::HandleWeave);
    }
};

// =====================================================================
// Ricochet Shot -- one shot, then ricochets that are casts of their own.
//
// Every ricochet is cast BY the target it leaves, at the next enemy within
// eight yards, with this player as the original caster. That is what draws
// the missile between the two of them, and what keeps the damage and the
// threat the player's: Spell::DoAllEffectOnTarget deals from the original
// caster. The main spell's second effect is a marker aura whose base points
// are the rank's ricochet budget; the companion (id + 16) is one ricochet's
// damage, a dummy effect carrying the budget that remains, and the same
// marker, so a shot never returns to something it has already hit. Each
// ricochet costs a share of the player's maximum mana and stops when that
// cannot be paid.
// =====================================================================
namespace
{
    Unit* NextRicochetTarget(Unit* from, Player* owner, uint32 mainId, uint32 bounceId)
    {
        std::list<Unit*> nearby;
        Acore::AnyUnfriendlyUnitInObjectRangeCheck check(from, owner, RICOCHET_RANGE);
        Acore::UnitListSearcher<Acore::AnyUnfriendlyUnitInObjectRangeCheck> searcher(from, nearby, check);
        Cell::VisitObjects(from, searcher, RICOCHET_RANGE);

        Unit* best = nullptr;
        float bestDist = RICOCHET_RANGE + 1.0f;
        for (Unit* u : nearby)
        {
            if (u == from || u == owner || !u->IsAlive())
                continue;
            if (u->HasAura(mainId) || u->HasAura(bounceId))
                continue;                               // this shot has been there
            if (!owner->IsValidAttackTarget(u))
                continue;
            float const d = from->GetDistance(u);
            if (d < bestDist)
            {
                best = u;
                bestDist = d;
            }
        }
        return best;
    }

    void Ricochet(Unit* from, Player* owner, uint32 mainId, uint32 bounceId, int32 remaining)
    {
        if (remaining <= 0 || !from || !owner)
            return;
        if (!sSpellMgr->GetSpellInfo(bounceId))
            return;                                     // the rank's companion row is missing
        Unit* next = NextRicochetTarget(from, owner, mainId, bounceId);
        if (!next)
            return;
        uint32 const cost = std::max<uint32>(1, owner->GetMaxPower(POWER_MANA) * RICOCHET_MANA_PCT / 100);
        if (uint32(owner->GetPower(POWER_MANA)) < cost)
            return;                                     // what you cannot pay for, it does not do
        owner->ModifyPower(POWER_MANA, -int32(cost));

        CustomSpellValues values;
        values.AddSpellMod(SPELLVALUE_BASE_POINT1, remaining - 1);
        from->CastCustomSpell(bounceId, values, next, TRIGGERED_FULL_MASK, nullptr, nullptr, owner->GetGUID());
    }
}

class spell_cw_ricochet_shot : public SpellScript
{
    PrepareSpellScript(spell_cw_ricochet_shot);

    // AfterHit, not OnEffectHit: by then the marker aura is on the target, so
    // the first ricochet's search already sees it.
    void Bounce()
    {
        Player* owner = GetCaster() ? GetCaster()->ToPlayer() : nullptr;
        Unit* target = GetHitUnit();
        if (!owner || !target)
            return;
        int32 const budget = GetSpellInfo()->Effects[EFFECT_1].CalcValue(owner);
        Ricochet(target, owner, GetSpellInfo()->Id,
                 GetSpellInfo()->Id + RICOCHET_COMPANION_OFFSET, budget);
    }

    void Register() override
    {
        AfterHit += SpellHitFn(spell_cw_ricochet_shot::Bounce);
    }
};

class spell_cw_ricochet_shot_bounce : public SpellScript
{
    PrepareSpellScript(spell_cw_ricochet_shot_bounce);

    void Bounce()
    {
        Unit* from = GetHitUnit();
        Unit* original = GetOriginalCaster();
        Player* owner = original ? original->ToPlayer() : nullptr;
        if (!from || !owner)
            return;
        int32 const remaining = GetSpellValue()->EffectBasePoints[EFFECT_1];
        Ricochet(from, owner, GetSpellInfo()->Id - RICOCHET_COMPANION_OFFSET,
                 GetSpellInfo()->Id, remaining);
    }

    void Register() override
    {
        AfterHit += SpellHitFn(spell_cw_ricochet_shot_bounce::Bounce);
    }
};

// =====================================================================
// Quickening -- mana to cast, rage and energy to make it worth casting.
//
// The DBC gives a spell one PowerType, so mana is the declared cost and the
// other two pools are spent here. They AMPLIFY rather than gate: an earlier
// design required rage, which simply locked out anyone who never melees.
// =====================================================================
class spell_cw_quickening : public SpellScript
{
    PrepareSpellScript(spell_cw_quickening);

    int32 _pct = 0;

    SpellCastResult CheckPools()
    {
        Player* caster = GetCaster() ? GetCaster()->ToPlayer() : nullptr;
        if (!caster)
            return SPELL_FAILED_BAD_TARGETS;
        // rage is stored ten to the displayed point; energy is not
        if (caster->GetPower(POWER_RAGE) / 10 + caster->GetPower(POWER_ENERGY) < int32(QUICKENING_MIN_POINTS))
            return SPELL_FAILED_NO_POWER;
        return SPELL_CAST_OK;
    }

    void SpendPools()
    {
        Player* caster = GetCaster() ? GetCaster()->ToPlayer() : nullptr;
        if (!caster)
            return;
        int32 const rage = caster->GetPower(POWER_RAGE);      // stored units, ten a point
        int32 const energy = caster->GetPower(POWER_ENERGY);
        _pct = std::min<int32>((rage / 10 + energy) / QUICKENING_POINTS_PER_PCT, QUICKENING_MAX_PCT);
        caster->ModifyPower(POWER_RAGE, -rage);
        caster->ModifyPower(POWER_ENERGY, -energy);
    }

    void SetHaste(SpellEffIndex /*effIndex*/)
    {
        SetEffectValue(_pct);
    }

    void Register() override
    {
        OnCheckCast += SpellCheckCastFn(spell_cw_quickening::CheckPools);
        OnCast += SpellCastFn(spell_cw_quickening::SpendPools);
        OnEffectLaunchTarget += SpellEffectFn(spell_cw_quickening::SetHaste,
                                              EFFECT_0, SPELL_EFFECT_APPLY_AURA);
        OnEffectLaunchTarget += SpellEffectFn(spell_cw_quickening::SetHaste,
                                              EFFECT_1, SPELL_EFFECT_APPLY_AURA);
    }
};

// =====================================================================
// Repertoire -- a window where breadth beats depth.
//
// The aura holds the stacks; the watcher above adds them. The set of used ids
// lives and dies with the aura, so there is no state to leak and no way for a
// stack to survive into the next cast.
// =====================================================================
class spell_cw_repertoire : public AuraScript
{
    PrepareAuraScript(spell_cw_repertoire);

    void OpenWindow(AuraEffect const* /*effect*/, AuraEffectHandleModes /*mode*/)
    {
        if (Player* owner = GetUnitOwner() ? GetUnitOwner()->ToPlayer() : nullptr)
        {
            RepertoireWindow& window = _repertoireUsed[owner->GetGUID().GetCounter()];
            window.auraSpellId = GetId();
            window.used.clear();
        }
    }

    void CloseWindow(AuraEffect const* /*effect*/, AuraEffectHandleModes /*mode*/)
    {
        if (Player* owner = GetUnitOwner() ? GetUnitOwner()->ToPlayer() : nullptr)
            _repertoireUsed.erase(owner->GetGUID().GetCounter());
    }

    void CalcAmount(AuraEffect const* aurEff, int32& amount, bool& /*canBeRecalculated*/)
    {
        amount = REPERTOIRE_PER_STACK * int32(aurEff->GetBase()->GetStackAmount());
    }

    void Register() override
    {
        OnEffectApply += AuraEffectApplyFn(spell_cw_repertoire::OpenWindow,
                                           EFFECT_0, SPELL_AURA_MOD_DAMAGE_PERCENT_DONE,
                                           AURA_EFFECT_HANDLE_REAL);
        OnEffectRemove += AuraEffectRemoveFn(spell_cw_repertoire::CloseWindow,
                                             EFFECT_0, SPELL_AURA_MOD_DAMAGE_PERCENT_DONE,
                                             AURA_EFFECT_HANDLE_REAL);
        DoEffectCalcAmount += AuraEffectCalcAmountFn(spell_cw_repertoire::CalcAmount,
                                                     EFFECT_0, SPELL_AURA_MOD_DAMAGE_PERCENT_DONE);
    }
};

// =====================================================================
// Wildcard Surge -- the payoff, sized by the build behind it.
//
// Capped, deliberately. Uncapped this reached +90% on a hero with a lucky roll
// history and nothing on an unlucky one, which is too wide a spread for a spell
// that is itself rolled for.
// =====================================================================
class spell_cw_wildcard_surge : public SpellScript
{
    PrepareSpellScript(spell_cw_wildcard_surge);

    void ScaleWithBuild(SpellEffIndex /*effIndex*/)
    {
        Player* caster = GetCaster() ? GetCaster()->ToPlayer() : nullptr;
        if (!caster || GetHitDamage() <= 0)
            return;

        uint32 good = 0;
        CharState& st = sClasslessMgr->GetState(caster);
        for (auto const& [firstSpell, owned] : st.abilities)
            if (AbilityEntry const* e = sClasslessMgr->GetAbility(firstSpell))
                if (e->rarity == Rarity::Epic || e->rarity == Rarity::Legendary)
                    ++good;

        int32 const bonus = std::min<int32>(int32(good) * SURGE_PER_ABILITY_PCT, SURGE_MAX_PCT);
        if (bonus)
            SetHitDamage(GetHitDamage() * (100 + bonus) / 100);
    }

    void Register() override
    {
        OnEffectHitTarget += SpellEffectFn(spell_cw_wildcard_surge::ScaleWithBuild,
                                           EFFECT_0, SPELL_EFFECT_SCHOOL_DAMAGE);
    }
};

// =====================================================================
// A forged pet wears the model its creature_template says, not the one its
// character_pet row remembers.
//
// Pet::LoadPetFromDB applies petInfo->DisplayId, which SavePetToDB wrote when
// the pet was first summoned. Changing creature_template_model therefore fixes
// only pets that have never existed; one already saved keeps the old look for
// good. This corrects our own entries as they enter the world, so a beetle
// summoned before the model changed fixes itself on the next summon.
// =====================================================================
class cw_forged_pet_model : public PetScript
{
public:
    cw_forged_pet_model() : PetScript("cw_forged_pet_model", { PETHOOK_ON_PET_ADD_TO_WORLD }) { }

    void OnPetAddToWorld(Pet* pet) override
    {
        if (!pet)
            return;
        uint32 const entry = pet->GetEntry();
        if (entry < FORGED_CREATURE_FIRST || entry > FORGED_CREATURE_LAST)
            return;
        CreatureTemplate const* tmpl = sObjectMgr->GetCreatureTemplate(entry);
        if (!tmpl)
            return;
        CreatureModel const* model = tmpl->GetRandomValidModel();
        if (!model || !model->CreatureDisplayID)
            return;
        if (pet->GetNativeDisplayId() == model->CreatureDisplayID)
            return;                             // already right, nothing to do
        pet->SetDisplayId(model->CreatureDisplayID);
        pet->SetNativeDisplayId(model->CreatureDisplayID);
    }
};

// =====================================================================
// Reclaimed Sentry -- an emplacement that actually fires.
//
// The turret is a marker summon: visible, non-attackable, immobile, and left
// on faction 35, which is friendly to everything. It cannot judge who is
// hostile and never tries. TempSummon::InitStats hands the owner's faction and
// level only to a creature carrying CREATURE_FLAG_EXTRA_TRIGGER, and that flag
// is what replaces a creature's model with the invisible one -- the last thing
// this summon can afford. So every question about a target is asked of the
// OWNER, and every bolt is cast with the owner as original caster, which puts
// the damage, the threat and the spell bonuses on the player. Ricochet Shot
// already works exactly this way.
//
// Which bolt it fires comes from creature_template_spell, one row per rank's
// own creature entry, which Creature::UpdateEntry copies into m_spells. A
// marker summon records no spell id at all -- the default branch of
// EffectSummonType passes none and UNIT_CREATED_BY_SPELL is set for pets only
// -- so the entry IS how a turret knows its rank. Nothing here holds a spell
// id, and another rank needs no edit to this file.
// =====================================================================
namespace
{
    constexpr uint32 SENTRY_SHOT_MS = 1000;
    constexpr float SENTRY_RANGE = 20.0f;
}

struct npc_cw_reclaimed_sentry : public NullCreatureAI
{
    explicit npc_cw_reclaimed_sentry(Creature* creature)
        : NullCreatureAI(creature), _timer(SENTRY_SHOT_MS) { }

    void UpdateAI(uint32 diff) override
    {
        if (_timer > diff)
        {
            _timer -= diff;
            return;
        }
        _timer = SENTRY_SHOT_MS;

        uint32 const bolt = me->m_spells[0];
        if (!bolt || !sSpellMgr->GetSpellInfo(bolt))
            return;                     // this entry's bolt row is missing

        TempSummon const* summon = me->ToTempSummon();
        if (!summon)
            return;
        Player* owner = ObjectAccessor::GetPlayer(*me, summon->GetSummonerGUID());
        if (!owner || !owner->IsInWorld() || !owner->IsAlive())
            return;

        std::list<Unit*> nearby;
        Acore::AnyUnfriendlyUnitInObjectRangeCheck check(me, owner, SENTRY_RANGE);
        Acore::UnitListSearcher<Acore::AnyUnfriendlyUnitInObjectRangeCheck> searcher(me, nearby, check);
        Cell::VisitObjects(me, searcher, SENTRY_RANGE);

        // Spread the armour strip before doubling up: the nearest enemy not
        // already carrying it, and only when they all are does it fall back to
        // the nearest of them.
        Unit* pick = nullptr;
        float best = SENTRY_RANGE + 1.0f;
        bool fresh = false;
        for (Unit* target : nearby)
        {
            if (!target->IsAlive() || !owner->IsValidAttackTarget(target))
                continue;
            bool const unmarked = !target->HasAura(bolt);
            float const dist = me->GetDistance(target);
            if (unmarked && !fresh)
            {
                pick = target;
                best = dist;
                fresh = true;
                continue;
            }
            if (unmarked != fresh || dist >= best)
                continue;
            pick = target;
            best = dist;
        }
        if (!pick)
            return;

        me->CastSpell(pick, bolt, TRIGGERED_FULL_MASK, nullptr, nullptr, owner->GetGUID());
    }

private:
    uint32 _timer;
};

class cw_forged_sentry : public CreatureScript
{
public:
    cw_forged_sentry() : CreatureScript("npc_cw_reclaimed_sentry") { }

    CreatureAI* GetAI(Creature* creature) const override
    {
        return new npc_cw_reclaimed_sentry(creature);
    }
};

void AddClasslessForgedScripts()
{
    new cw_forged_pet_model();
    new cw_forged_sentry();
    new cw_forged_watcher();
    RegisterSpellScript(spell_cw_crossdraw);
    RegisterSpellScript(spell_cw_ricochet_shot);
    RegisterSpellScript(spell_cw_ricochet_shot_bounce);
    RegisterSpellScript(spell_cw_quickening);
    RegisterSpellScript(spell_cw_repertoire);
    RegisterSpellScript(spell_cw_wildcard_surge);
}
