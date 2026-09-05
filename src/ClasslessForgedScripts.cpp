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
    constexpr uint32 BLEED_OVER_EXTEND_MS = 6000;
    constexpr uint8  REPERTOIRE_MAX_STACKS = 5;
    constexpr int32  REPERTOIRE_PER_STACK = 3;
    constexpr uint32 QUICKENING_MIN_POINTS = 20;
    constexpr int32  QUICKENING_MAX_PCT = 20;
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
// Ricochet Shot -- energy to fire, mana to keep bouncing.
//
// Everything settles at target selection, which the core runs ONCE per cast:
// SelectImplicitChainTargets calls this hook after it has picked the chain, so
// trimming here is the last word and there is nothing to cancel mid-flight.
// The mana is charged for exactly the bounces that survive the trim.
// =====================================================================
class spell_cw_ricochet_shot : public SpellScript
{
    PrepareSpellScript(spell_cw_ricochet_shot);

    void TrimToWhatIsPaidFor(std::list<WorldObject*>& targets)
    {
        Player* caster = GetCaster() ? GetCaster()->ToPlayer() : nullptr;
        if (!caster || targets.size() <= 1)
            return;

        uint32 const perBounce = std::max<uint32>(1, caster->GetMaxPower(POWER_MANA) * 6 / 100);
        uint32 const have = caster->GetPower(POWER_MANA);
        uint32 const afford = perBounce ? have / perBounce : 0;
        // the first target is the shot itself and is paid for with energy
        size_t const keep = std::min<size_t>(targets.size(), size_t(afford) + 1);

        if (keep < targets.size())
            targets.resize(keep);
        uint32 const bounces = uint32(targets.size() - 1);
        if (bounces)
            caster->ModifyPower(POWER_MANA, -int32(bounces * perBounce));
    }

    void Register() override
    {
        OnObjectAreaTargetSelect += SpellObjectAreaTargetSelectFn(
            spell_cw_ricochet_shot::TrimToWhatIsPaidFor, EFFECT_0, TARGET_UNIT_TARGET_ENEMY);
    }
};

// =====================================================================
// Bleed Over -- extends your own periodics on the target.
//
// EXTENDS by a fixed six seconds rather than refreshing to full. Refreshing is
// unbounded: with enough damage-over-time effects it approaches never having to
// recast any of them. Only auras this caster applied are touched, and only ones
// that actually tick, so it can never reach a stun or somebody else's work.
// =====================================================================
class spell_cw_bleed_over : public SpellScript
{
    PrepareSpellScript(spell_cw_bleed_over);

    void ExtendPeriodics(SpellEffIndex /*effIndex*/)
    {
        Unit* caster = GetCaster();
        Unit* target = GetHitUnit();
        if (!caster || !target)
            return;

        // rank 1 reaches two, and each rank one more
        uint32 const first = sSpellMgr->GetFirstSpellInChain(GetSpellInfo()->Id);
        uint32 const rank = GetSpellInfo()->Id - first;
        size_t const limit = size_t(2 + rank);

        std::vector<Aura*> mine;
        for (auto const& applied : target->GetAppliedAuras())
        {
            Aura* aura = applied.second ? applied.second->GetBase() : nullptr;
            if (!aura || aura->GetCasterGUID() != caster->GetGUID())
                continue;
            if (aura->GetId() == GetSpellInfo()->Id)
                continue;                       // not its own dot
            if (aura->GetDuration() < 0)
                continue;                       // permanent: nothing to extend
            SpellInfo const* info = aura->GetSpellInfo();
            bool periodic = false;
            for (uint8 i = 0; i < MAX_SPELL_EFFECTS && !periodic; ++i)
                if (AuraEffect const* eff = aura->GetEffect(i))
                    periodic = eff->GetAmplitude() > 0
                        && (info->Effects[i].ApplyAuraName == SPELL_AURA_PERIODIC_DAMAGE
                            || info->Effects[i].ApplyAuraName == SPELL_AURA_PERIODIC_LEECH
                            || info->Effects[i].ApplyAuraName == SPELL_AURA_PERIODIC_DAMAGE_PERCENT);
            if (periodic)
                mine.push_back(aura);
        }

        // the ones closest to falling off are the ones worth the extension
        std::sort(mine.begin(), mine.end(),
                  [](Aura const* a, Aura const* b) { return a->GetDuration() < b->GetDuration(); });

        for (size_t i = 0; i < mine.size() && i < limit; ++i)
        {
            Aura* aura = mine[i];
            int32 const capped = std::min<int32>(aura->GetDuration() + int32(BLEED_OVER_EXTEND_MS),
                                                 aura->GetMaxDuration() + int32(BLEED_OVER_EXTEND_MS));
            aura->SetDuration(capped);
        }
    }

    void Register() override
    {
        OnEffectHitTarget += SpellEffectFn(spell_cw_bleed_over::ExtendPeriodics,
                                          EFFECT_0, SPELL_EFFECT_APPLY_AURA);
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
        if (caster->GetPower(POWER_RAGE) + caster->GetPower(POWER_ENERGY) < int32(QUICKENING_MIN_POINTS))
            return SPELL_FAILED_NO_POWER;
        return SPELL_CAST_OK;
    }

    void SpendPools()
    {
        Player* caster = GetCaster() ? GetCaster()->ToPlayer() : nullptr;
        if (!caster)
            return;
        int32 const rage = caster->GetPower(POWER_RAGE);
        int32 const energy = caster->GetPower(POWER_ENERGY);
        _pct = std::min<int32>((rage + energy) / 10, QUICKENING_MAX_PCT);
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

void AddClasslessForgedScripts()
{
    new cw_forged_watcher();
    RegisterSpellScript(spell_cw_crossdraw);
    RegisterSpellScript(spell_cw_ricochet_shot);
    RegisterSpellScript(spell_cw_bleed_over);
    RegisterSpellScript(spell_cw_quickening);
    RegisterSpellScript(spell_cw_repertoire);
    RegisterSpellScript(spell_cw_wildcard_surge);
}
