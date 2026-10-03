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
#include "Duration.h"      // the 1ms the Weave refund is scheduled by
#include "GameTime.h"
#include "Chat.h"           // Last Breath says it fired
#include "Group.h"          // Healing Spit reads the party
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

    // ---------------------------------------------------------------------
    // Hero talents that a spell modifier cannot express.
    //
    // Every Hero talent sits on SpellFamilyName 14, so its ICON is what tells
    // one from another: GetDummyAuraEffect(family, icon, effIndex) is how
    // Blizzard's own scripts find a talent and it is how these do. The numbers
    // are the icons gen_forged_spells.py writes, and test_forged.py refuses to
    // build if this file and the generator ever disagree.
    // ---------------------------------------------------------------------
    constexpr SpellFamilyNames HERO_FAMILY = SpellFamilyNames(14);
    constexpr uint32 ICON_ADRENAL_SURGE = 1904;   // Quickening's cap
    constexpr uint32 ICON_OVERCLOCKED = 2303;     // the sentry's firing rate
    constexpr uint32 ICON_TWO_SCHOOLS = 2215;     // a school other than the last
    constexpr uint32 ICON_JACK_OF_ALL = 2590;     // breadth of the build
    constexpr uint32 ICON_IMPROVISED_ARSENAL = 2185;  // the strike shortens the throw
    constexpr uint32 ICON_FIELD_REPAIRS = 1997;   // reserves also break snares
    constexpr uint32 ICON_LAST_RESERVE = 3397;    // a shield spent to the last point
    constexpr uint32 ICON_OPPORTUNIST = 350;      // energy for each enemy caught
    constexpr uint32 ICON_WEAVE = 2458;           // every Nth Hero ability is free
    constexpr uint32 ICON_VENOM_HANDLER = 1630;   // the beetle's poison outlives its host

    // How far a Venom Handler poison reaches from the body it came off.
    // Eight yards is what the game's own spreading effects use.
    constexpr float VENOM_SPREAD_RANGE = 8.0f;
    constexpr uint32 ICON_FIELD_STUDY = 1468;     // Emberfeed paid for by a bleed
    constexpr uint32 ICON_BROAD_STROKES = 1871;   // Overflow spills back to you
    constexpr uint32 ICON_MEDICINAL_VENOM = 2101; // the beetle learns to heal

    // Two Schools: the school mask of the last damage this character dealt.
    // A pure cache like the two below -- losing it costs one hit's bonus.
    std::unordered_map<ObjectGuid::LowType, uint32> _lastDamageSchool;

    // Weave: Hero abilities cast since the last free one. Also a cache; losing
    // it costs one cycle of counting, never a refund already given.
    std::unordered_map<ObjectGuid::LowType, uint32> _weaveCount;

    // Returns the talent's amount, or 0 when the Hero does not own it. A talent
    // that needs a second number carries it in its next slot (gen_forged_spells.py
    // `extra`), and its text names it as $s2.
    int32 HeroTalentAmount(Unit const* unit, uint32 icon, SpellEffIndex slot = EFFECT_0)
    {
        if (!unit)
            return 0;
        if (AuraEffect* eff = unit->GetDummyAuraEffect(HERO_FAMILY, icon, slot))
            return eff->GetAmount();
        return 0;
    }

    // Two Schools and Jack of All Trades both scale outgoing numbers, and both
    // apply to melee, spells and heals alike. Kept in one place so the two can
    // never drift apart on which of the three they reach.
    void ApplyHeroTalentBonus(Unit* attacker, uint32 schoolMask, int32& amount,
                              bool isHeal)
    {
        Player* player = attacker ? attacker->ToPlayer() : nullptr;
        if (!player || amount <= 0)
            return;

        int32 pct = 0;

        // Jack of All Trades: one step for every three different classes the
        // Hero has drawn an ability from.
        if (int32 const step = HeroTalentAmount(player, ICON_JACK_OF_ALL))
            if (int32 const classes = HeroTalentAmount(player, ICON_JACK_OF_ALL, EFFECT_1))
                pct += step * (sClasslessMgr->OwnedClassCount(player) / classes);

        // Two Schools: only on damage, and only when the school differs from
        // the last one this character dealt. Recorded either way, so repeating
        // a school simply earns nothing.
        if (!isHeal && schoolMask)
        {
            ObjectGuid::LowType const guid = player->GetGUID().GetCounter();
            auto itr = _lastDamageSchool.find(guid);
            bool const different = (itr == _lastDamageSchool.end() || itr->second != schoolMask);
            if (different)
                if (int32 const bonus = HeroTalentAmount(player, ICON_TWO_SCHOOLS))
                    pct += bonus;
            _lastDamageSchool[guid] = schoolMask;
        }

        if (pct > 0)
            amount = int32(amount + CalculatePct(amount, pct));
    }

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

    // The tuning numbers of these lines live in their own spell rows, in the
    // slots gen_forged_spells.py puts them in, so a tooltip's $s3 and the
    // script read one value. Only the id layout is fixed here.
    constexpr uint32 CROSSDRAW_COMPANION_OFFSET = 16;   // matches PER_RECIPE / 2
    constexpr uint32 QUICKENING_DATA_OFFSET = 16;       // the row holding its minimum
    constexpr uint32 RICOCHET_COMPANION_OFFSET = 16;    // matches PER_RECIPE / 2
    // the creature entries this module owns, from gen_forged_spells.py
    constexpr uint32 FORGED_CREATURE_FIRST = 990110;
    constexpr uint32 FORGED_CREATURE_LAST = 990130;

    // One slot's value off a spell row, worked out for `caster` the way the
    // client works out the same slot's $s for the tooltip.
    int32 SlotValue(uint32 spellId, SpellEffIndex slot, Unit const* caster = nullptr)
    {
        SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
        return info ? info->Effects[slot].CalcValue(caster) : 0;
    }

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

        // Only what the player PRESSED. Spell::cast reaches this hook for a
        // triggered cast as well, and half the forged lines fire a hidden
        // companion through SPELL_EFFECT_TRIGGER_SPELL or CastSpell(..., true):
        // Makeshift Strike's mana return, Hurl's rage, Antipode Blast's frost
        // half, Crossdraw's arcane half. Counted, those made one button two
        // Repertoire stacks and two of Weave's N -- and Crossdraw's own
        // companion is a damaging cast, so one Crossdraw satisfied the next
        // one's condition forever, which is exactly what IsDamagingSpellCast
        // refusing weapon strikes was meant to rule out.
        if (spell->IsTriggered())
            return;

        if (IsDamagingSpellCast(info))
            _lastDamagingCastMs[guid] = uint32(GameTime::GetGameTimeMS().count());

        // Weave: every Nth Hero ability gives its cost back. Family 14 is what
        // makes a spell a Hero ability, so nothing else is counted.
        //
        // The refund is scheduled a tick out rather than paid here, and that is
        // not tidiness: Spell::cast runs this hook BEFORE TakePower, so handing
        // the power back now would only see it taken again a few lines later.
        if (info->SpellFamilyName == HERO_FAMILY && !info->IsPassive())
            if (int32 const every = HeroTalentAmount(player, ICON_WEAVE))
            {
                uint32& cast = _weaveCount[guid];
                if (++cast >= uint32(every))
                {
                    cast = 0;
                    int32 const cost = spell->GetPowerCost();
                    Powers const power = Powers(info->PowerType);
                    if (cost > 0)
                        player->m_Events.AddEventAtOffset([player, power, cost]()
                        {
                            player->ModifyPower(power, cost);
                        }, 1ms);
                }
            }

        // Repertoire counts DISTINCT abilities, so a repeat is free to ignore.
        // The set is created when the aura goes up and dropped when it comes
        // down, so an absent entry means the buff is not running.
        auto itr = _repertoireUsed.find(guid);
        if (itr == _repertoireUsed.end())
            return;
        if (!itr->second.used.insert(info->Id).second)
            return;

        int32 const limit = std::max<int32>(1, SlotValue(itr->second.auraSpellId, EFFECT_1, player));
        uint8 const stacks = uint8(std::min<size_t>(itr->second.used.size(), size_t(limit)));
        if (Aura* aura = player->GetAura(itr->second.auraSpellId, player->GetGUID()))
            if (aura->GetStackAmount() != stacks)
                aura->SetStackAmount(stacks);
    }

    void OnPlayerLogout(Player* player) override
    {
        ObjectGuid::LowType const guid = player->GetGUID().GetCounter();
        _lastDamagingCastMs.erase(guid);
        _lastDamageSchool.erase(guid);
        _repertoireUsed.erase(guid);
        _weaveCount.erase(guid);
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
        uint32 const window = uint32(std::max<int32>(0, GetSpellInfo()->Effects[EFFECT_1].CalcValue(caster)));
        if (now < itr->second || now - itr->second > window)
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
    Unit* NextRicochetTarget(Unit* from, Player* owner, uint32 mainId, uint32 bounceId, float range)
    {
        std::list<Unit*> nearby;
        Acore::AnyUnfriendlyUnitInObjectRangeCheck check(from, owner, range);
        Acore::UnitListSearcher<Acore::AnyUnfriendlyUnitInObjectRangeCheck> searcher(from, nearby, check);
        Cell::VisitObjects(from, searcher, range);

        Unit* best = nullptr;
        float bestDist = range + 1.0f;
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
        SpellInfo const* main = sSpellMgr->GetSpellInfo(mainId);
        if (!main || !sSpellMgr->GetSpellInfo(bounceId))
            return;                                     // the rank's rows are missing
        Unit* next = NextRicochetTarget(from, owner, mainId, bounceId, main->Effects[EFFECT_2].CalcRadius(owner));
        if (!next)
            return;
        uint32 const manaPct = uint32(std::max<int32>(0, main->Effects[EFFECT_2].CalcValue(owner)));
        uint32 const cost = std::max<uint32>(1, owner->GetMaxPower(POWER_MANA) * manaPct / 100);
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
        int32 const least = SlotValue(GetSpellInfo()->Id + QUICKENING_DATA_OFFSET, EFFECT_0, caster);
        if (int32(caster->GetPower(POWER_RAGE) / 10 + caster->GetPower(POWER_ENERGY)) < least)
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
        // Adrenal Surge raises the ceiling, nothing else about the spell.
        int32 const cap = GetSpellInfo()->Effects[EFFECT_0].CalcValue(caster)
            + HeroTalentAmount(caster, ICON_ADRENAL_SURGE);
        int32 const perPct = std::max<int32>(1, GetSpellInfo()->Effects[EFFECT_2].CalcValue(caster));
        _pct = std::min<int32>((rage / 10 + energy) / perPct, cap);
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
        amount = GetSpellInfo()->Effects[EFFECT_0].CalcValue(GetCaster())
            * int32(aurEff->GetBase()->GetStackAmount());
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

        int32 const bonus = std::min<int32>(int32(good) * GetSpellInfo()->Effects[EFFECT_1].CalcValue(caster),
                                            GetSpellInfo()->Effects[EFFECT_2].CalcValue(caster));
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
// Medicinal Venom's spell lives in the beetle's creature_template_spell at
// slot 3 with SpellLevel 255, so Pet::InitLevelupSpellsForLevel never hands it
// out and this file never holds a spell id. What the talent does is teach it,
// and stop the level-up pass taking it away again.
namespace
{
    constexpr uint8 HEALING_SPIT_SLOT = 3;

    // A scarab at a pet's 1.15 run speed scuttles in fast-forward. One is a
    // running player's speed, which is what it spends its life following.
    //
    // It has to be set from a script: Pet.cpp writes 1.15f over
    // creature_template.speed_run for every pet there is, and
    // Guardian::InitStatsForLevel comes back and does it again on every level
    // change. The row still carries the number so the data says what it means.
    constexpr float BEETLE_RUN_SPEED = 1.0f;

    void SlowForgedPet(Unit* pet)
    {
        if (!pet)
            return;
        uint32 const entry = pet->GetEntry();
        if (entry < FORGED_CREATURE_FIRST || entry > FORGED_CREATURE_LAST)
            return;
        // Unit::SetSpeed returns early when the rate already matches, so this
        // is safe to call as often as the hooks fire.
        pet->SetSpeed(MOVE_RUN, BEETLE_RUN_SPEED);
    }

    // The spell the beetle would learn from the talent, or 0 for any other pet.
    //
    // Read from the creature TEMPLATE, not from the pet. Pet declares its own
    // m_spells -- a map of what it has learned -- which shadows the array of
    // eight template slots Creature declares under the same name, so
    // `pet->m_spells[3]` is a different container that does not even compile
    // through a const pointer. creature_template_spell fills the template's
    // array, and that is the one holding the id this talent wants.
    uint32 TalentPetSpell(Pet const* pet)
    {
        static_assert(HEALING_SPIT_SLOT < MAX_CREATURE_SPELLS, "slot is out of the template");
        if (!pet)
            return 0;
        uint32 const entry = pet->GetEntry();
        if (entry < FORGED_CREATURE_FIRST || entry > FORGED_CREATURE_LAST)
            return 0;
        CreatureTemplate const* tmpl = pet->GetCreatureTemplate();
        uint32 const spellId = tmpl ? tmpl->spells[HEALING_SPIT_SLOT] : 0;
        return sSpellMgr->GetSpellInfo(spellId) ? spellId : 0;
    }

    bool OwnerHasMedicinalVenom(Pet const* pet)
    {
        Unit* owner = pet ? pet->GetOwner() : nullptr;
        Player* player = owner ? owner->ToPlayer() : nullptr;
        return player && HeroTalentAmount(player, ICON_MEDICINAL_VENOM) > 0;
    }

    // The talent's spell, handed over or taken back. Both directions, so
    // unlearning the talent takes the beetle's heal with it rather than
    // leaving a pet that keeps casting something nothing paid for.
    //
    // Pet::learnSpell sends PetLearnedSpell and calls PetSpellInitialize, so
    // the bar the player is looking at redraws with it.
    void SyncTalentPetSpell(Pet* pet)
    {
        uint32 const spit = TalentPetSpell(pet);
        if (!spit)
            return;
        bool const wanted = OwnerHasMedicinalVenom(pet);
        bool const known = pet->HasSpell(spit);
        if (wanted && !known)
        {
            pet->learnSpell(spit);
            if (SpellInfo const* info = sSpellMgr->GetSpellInfo(spit))
                pet->ToggleAutocast(info, true);
        }
        else if (!wanted && known)
            pet->unlearnSpell(spit, false);
    }
}

// Declared in ClasslessMgr.h. A talent bought while the beetle is already out
// reached nothing: the summon hook below is the only other caller, and it has
// long since run.
void CW_SyncTalentPetSpell(Player* player)
{
    if (player)
        SyncTalentPetSpell(player->GetPet());
}

class cw_forged_pet_model : public PetScript
{
public:
    cw_forged_pet_model() : PetScript("cw_forged_pet_model", {
        PETHOOK_ON_PET_ADD_TO_WORLD,
        PETHOOK_CAN_UNLEARN_SPELL_DEFAULT,
        PETHOOK_ON_INIT_STATS_FOR_LEVEL
    }) { }

    // Stat init is where the core writes 1.15 over the row's speed, and it runs
    // again on every level change, so this runs after it every time.
    void OnInitStatsForLevel(Guardian* guardian, uint8 /*petlevel*/) override
    {
        SlowForgedPet(guardian);
    }

    // Pet::InitLevelupSpellsForLevel unlearns every default spell whose
    // SpellLevel is above the pet's, which Healing Spit's 255 always is. For a
    // Hero who owns the talent, that is the one spell it must not take.
    [[nodiscard]] bool CanUnlearnSpellDefault(Pet* pet, SpellInfo const* spellInfo) override
    {
        if (!spellInfo || spellInfo->Id != TalentPetSpell(pet))
            return true;
        return !OwnerHasMedicinalVenom(pet);
    }

    void OnPetAddToWorld(Pet* pet) override
    {
        if (!pet)
            return;
        SlowForgedPet(pet);
        uint32 const entry = pet->GetEntry();
        if (entry < FORGED_CREATURE_FIRST || entry > FORGED_CREATURE_LAST)
            return;

        SyncTalentPetSpell(pet);
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
// The turret's own numbers ride on the bolt it fires, slot 3: the value is
// its reach in yards and the amplitude its time between shots. The tooltip
// quotes the same slot as ${pet}s3 and ${pet}t3.
namespace
{
    uint32 SentryInterval(Creature const* turret)
    {
        SpellInfo const* bolt = sSpellMgr->GetSpellInfo(turret->m_spells[0]);
        return bolt ? uint32(std::max<int32>(0, bolt->Effects[EFFECT_2].Amplitude)) : 0;
    }
}

struct npc_cw_reclaimed_sentry : public NullCreatureAI
{
    explicit npc_cw_reclaimed_sentry(Creature* creature)
        : NullCreatureAI(creature), _timer(SentryInterval(creature)) { }

    void UpdateAI(uint32 diff) override
    {
        if (_timer > diff)
        {
            _timer -= diff;
            return;
        }

        uint32 const bolt = me->m_spells[0];
        SpellInfo const* boltInfo = bolt ? sSpellMgr->GetSpellInfo(bolt) : nullptr;
        uint32 const interval = SentryInterval(me);
        if (!boltInfo || !interval)
            return;                     // this entry's bolt row is missing
        _timer = interval;

        TempSummon const* summon = me->ToTempSummon();
        if (!summon)
            return;
        Player* owner = ObjectAccessor::GetPlayer(*me, summon->GetSummonerGUID());
        if (!owner || !owner->IsInWorld() || !owner->IsAlive())
            return;

        // Overclocked shortens the interval by its own percentage. Read from
        // the OWNER, because the turret carries no talents of its own.
        if (int32 const faster = HeroTalentAmount(owner, ICON_OVERCLOCKED))
            _timer = std::max<uint32>(200, interval - CalculatePct(interval, faster));

        // Wider Net promises a bigger radius on "everything you place", and
        // the turret's reach is this constant rather than a radius column, so
        // the spell-mod system never saw it. Asked of the owner's modifiers
        // against the line's own id: every rank shares the line's class bit,
        // so the first rank answers for all of them.
        float range = float(boltInfo->Effects[EFFECT_2].CalcValue(owner));
        if (uint32 const line = sClasslessMgr->ForgedLine("reclaimed_sentry"))
            owner->ApplySpellMod(line, SPELLMOD_RADIUS, range);

        std::list<Unit*> nearby;
        Acore::AnyUnfriendlyUnitInObjectRangeCheck check(me, owner, range);
        Acore::UnitListSearcher<Acore::AnyUnfriendlyUnitInObjectRangeCheck> searcher(me, nearby, check);
        Cell::VisitObjects(me, searcher, range);

        // Spread the armour strip before doubling up: the nearest enemy not
        // already carrying it, and only when they all are does it fall back to
        // the nearest of them.
        Unit* pick = nullptr;
        float best = range + 1.0f;
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

// =====================================================================
// Improvised Arsenal -- the strike shortens the throw.
//
// Makeshift Strike has no cooldown and Hurl has six seconds, so before this
// they were two buttons doing the same job at different speeds. Now landing
// the cheap one brings the expensive one back, and the pair reads as one
// improvised kit rather than two spells that happen to share a talent.
//
// Hurl is found by recipe name rather than by id: this file deliberately holds
// no generated spell ids, and the recipe string is the one name the generator
// and the server already share.
// =====================================================================
class spell_cw_makeshift_strike : public SpellScript
{
    PrepareSpellScript(spell_cw_makeshift_strike);

    void ShortenHurl()
    {
        Player* caster = GetCaster() ? GetCaster()->ToPlayer() : nullptr;
        if (!caster || !GetHitUnit())
            return;

        int32 const ms = HeroTalentAmount(caster, ICON_IMPROVISED_ARSENAL);
        if (ms <= 0)
            return;

        uint32 const first = sClasslessMgr->ForgedLine("hurl");
        if (!first)
            return;                     // forged spells are off on this realm
        ClasslessWildcard::AbilityEntry const* line = sClasslessMgr->GetAbility(first);
        if (!line)
            return;

        // Every rank, because only the one they hold is ever on cooldown and
        // ModifySpellCooldown returns silently for the rest.
        for (uint32 rank : line->ranks)
            caster->ModifySpellCooldown(rank, -ms);
    }

    void Register() override
    {
        AfterHit += SpellHitFn(spell_cw_makeshift_strike::ShortenHurl);
    }
};

// =====================================================================
// Field Repairs -- getting your reserves back is no use if you cannot move.
//
// One point, and it turns Second Nature and Adrenaline from "press when empty"
// into the answer to being kited or rooted. Bound to both, so the two can
// never drift apart on what the talent does.
// =====================================================================
class spell_cw_reserve_break : public SpellScript
{
    PrepareSpellScript(spell_cw_reserve_break);

    void FreeMovement()
    {
        Player* caster = GetCaster() ? GetCaster()->ToPlayer() : nullptr;
        if (!caster)
            return;
        if (!HeroTalentAmount(caster, ICON_FIELD_REPAIRS))
            return;
        caster->RemoveMovementImpairingAuras(true);   // roots included
    }

    void Register() override
    {
        AfterCast += SpellCastFn(spell_cw_reserve_break::FreeMovement);
    }
};

// =====================================================================
// Last Reserve -- a shield spent to the last point pays for itself.
//
// The test is the absorb's own remaining amount, not the removal mode: an
// absorb that runs out is removed by whatever spell finished it, while one
// that simply expires still has points left. Reading the amount is the only
// answer that means "you timed this right" in both cases.
// =====================================================================
class spell_cw_ward_off : public AuraScript
{
    PrepareAuraScript(spell_cw_ward_off);

    void Spent(AuraEffect const* aurEff, AuraEffectHandleModes /*mode*/)
    {
        Player* owner = GetUnitOwner() ? GetUnitOwner()->ToPlayer() : nullptr;
        if (!owner || aurEff->GetAmount() > 0)
            return;

        int32 const pct = HeroTalentAmount(owner, ICON_LAST_RESERVE);
        int32 const cooldown = int32(GetSpellInfo()->RecoveryTime);
        if (pct <= 0 || cooldown <= 0)
            return;

        owner->ModifySpellCooldown(GetId(), -CalculatePct(cooldown, pct));
    }

    void Register() override
    {
        AfterEffectRemove += AuraEffectRemoveFn(spell_cw_ward_off::Spent, EFFECT_0,
                                                SPELL_AURA_SCHOOL_ABSORB,
                                                AURA_EFFECT_HANDLE_REAL);
    }
};

// =====================================================================
// Opportunist -- catching a crowd pays, catching one thing does not.
//
// AfterHit runs once per unit the spell reached, so the count is the number of
// enemies actually caught rather than the number aimed at. Capped, because a
// pull of twenty should not refill the bar on its own.
// =====================================================================
class spell_cw_area_control : public SpellScript
{
    PrepareSpellScript(spell_cw_area_control);

    void Caught()
    {
        Player* caster = GetCaster() ? GetCaster()->ToPlayer() : nullptr;
        if (!caster || !GetHitUnit()
            || _paid >= HeroTalentAmount(caster, ICON_OPPORTUNIST, EFFECT_1))
            return;

        int32 const energy = HeroTalentAmount(caster, ICON_OPPORTUNIST);
        if (energy <= 0)
            return;

        ++_paid;
        caster->ModifyPower(POWER_ENERGY, energy);
    }

    void Register() override
    {
        AfterHit += SpellHitFn(spell_cw_area_control::Caught);
    }

private:
    int32 _paid = 0;
};

// =====================================================================
// Healing Spit -- the beetle spits at whoever is hurt worst.
//
// PetAI offers a positive spell each ally in turn and casts on the first one
// the spell accepts (Spell::CanAutoCast runs the cast check), so "hurt worst"
// is enforced by refusing everyone else. Nobody hurt means nobody accepted and
// the beetle simply does not cast, which is what keeps a twenty second
// cooldown for the moment it is worth something.
// =====================================================================
class spell_cw_healing_spit : public SpellScript
{
    PrepareSpellScript(spell_cw_healing_spit);

    static constexpr float HURT_ENOUGH = 90.0f;   // per cent of health

    SpellCastResult CheckWounded()
    {
        Unit* caster = GetCaster();
        Unit* target = GetExplTargetUnit();
        if (!caster || !target)
            return SPELL_FAILED_BAD_TARGETS;

        Unit* owner = caster->GetOwner();
        Player* player = owner ? owner->ToPlayer() : nullptr;
        if (!player)
            return SPELL_FAILED_BAD_TARGETS;

        float const range = GetSpellInfo()->GetMaxRange(true);
        Unit* worst = nullptr;
        float worstPct = HURT_ENOUGH;

        auto consider = [&](Unit* ally)
        {
            if (!ally || !ally->IsAlive() || !caster->IsWithinDistInMap(ally, range))
                return;
            float const pct = ally->GetHealthPct();
            if (pct >= worstPct)
                return;
            worst = ally;
            worstPct = pct;
        };

        consider(player);
        consider(caster);                       // the beetle counts as one of you
        if (Group const* group = player->GetGroup())
            for (GroupReference const* itr = group->GetFirstMember(); itr; itr = itr->next())
                if (Player* member = itr->GetSource())
                    if (member != player)
                        consider(member);

        return worst == target ? SPELL_CAST_OK : SPELL_FAILED_BAD_TARGETS;
    }

    void Register() override
    {
        OnCheckCast += SpellCheckCastFn(spell_cw_healing_spit::CheckWounded);
    }
};

// =====================================================================
// Field Study -- a bleed pays for the bolt.
//
// Emberfeed is a two second cast that heals you for part of what it deals, and
// Bleed Over is an instant leech. Separately they are two damage spells that
// happen to feed you; in this order they are a rotation, and the cost of the
// slow one comes back.
//
// The refund is taken in AfterCast, which Spell::cast reaches AFTER TakePower,
// so the power really has been paid by the time it is handed back. (The Weave
// talent cannot do this: its hook runs before the cost is taken at all.)
// =====================================================================
class spell_cw_emberfeed : public SpellScript
{
    PrepareSpellScript(spell_cw_emberfeed);

    void PayBack()
    {
        Player* caster = GetCaster() ? GetCaster()->ToPlayer() : nullptr;
        Unit* target = GetExplTargetUnit();
        if (!caster || !target)
            return;

        int32 const pct = HeroTalentAmount(caster, ICON_FIELD_STUDY);
        if (pct <= 0)
            return;

        uint32 const first = sClasslessMgr->ForgedLine("bleed_over");
        if (!first)
            return;
        ClasslessWildcard::AbilityEntry const* line = sClasslessMgr->GetAbility(first);
        if (!line)
            return;

        // Any rank, and only this caster's: someone else's bleed is not your
        // setup and should not pay you.
        bool bleeding = false;
        for (uint32 rank : line->ranks)
            if (target->GetAura(rank, caster->GetGUID()))
            {
                bleeding = true;
                break;
            }
        if (!bleeding)
            return;

        int32 const cost = GetSpell() ? GetSpell()->GetPowerCost() : 0;
        if (cost <= 0)
            return;
        caster->ModifyPower(Powers(GetSpellInfo()->PowerType), CalculatePct(cost, pct));
    }

    void Register() override
    {
        AfterCast += SpellCastFn(spell_cw_emberfeed::PayBack);
    }
};

// =====================================================================
// Broad Strokes -- the spill reaches the one who cast it.
//
// Overflow heals a friendly target and spills to allies around THEM, so
// healing someone on the far side of a fight healed the caster for nothing at
// all. Adding the caster to the spill's target list is the whole talent: no
// second heal, no new spell, just one more name on the list the effect was
// always going to run down.
// =====================================================================
class spell_cw_overflow : public SpellScript
{
    PrepareSpellScript(spell_cw_overflow);

    void IncludeCaster(std::list<WorldObject*>& targets)
    {
        Unit* caster = GetCaster();
        if (!caster || !HeroTalentAmount(caster, ICON_BROAD_STROKES))
            return;
        if (std::find(targets.begin(), targets.end(), caster) == targets.end())
            targets.push_back(caster);
    }

    void Register() override
    {
        OnObjectAreaTargetSelect += SpellObjectAreaTargetSelectFn(
            spell_cw_overflow::IncludeCaster, EFFECT_1, TARGET_UNIT_DEST_AREA_ALLY);
    }
};

// =====================================================================
// Two Schools and Jack of All Trades.
//
// Neither belongs to an ability, so neither can be a spell modifier: they
// scale everything the Hero does. All three hooks route through one helper so
// melee, spells and heals can never drift apart.
// =====================================================================
class cw_forged_talents : public UnitScript
{
public:
    cw_forged_talents() : UnitScript("cw_forged_talents", true, {
        UNITHOOK_MODIFY_MELEE_DAMAGE,
        UNITHOOK_MODIFY_SPELL_DAMAGE_TAKEN,
        UNITHOOK_MODIFY_PERIODIC_DAMAGE_AURAS_TICK,
        UNITHOOK_MODIFY_HEAL_RECEIVED,
        UNITHOOK_ON_UNIT_DEATH
    }) { }

    void ModifyMeleeDamage(Unit* /*target*/, Unit* attacker, uint32& damage) override
    {
        int32 amount = int32(damage);
        ApplyHeroTalentBonus(attacker, SPELL_SCHOOL_MASK_NORMAL, amount, false);
        damage = uint32(std::max<int32>(0, amount));
    }

    // A tick is not a cast. CalculateSpellDamageTaken, where the hook above
    // runs, is the direct-damage path only: Bleed Over, Antipode Blast's
    // burn, Sinkhole and the beetle's poison all tick through
    // HandlePeriodicDamageAurasTick instead, and Jack of All Trades reached
    // none of them. Two Schools is left out here on purpose -- it asks what
    // you CAST last, and a bleed ticking between swings is not that.
    //
    // A periodic HEAL tick comes through this same hook and then through
    // ModifyHealReceived a line later, so a heal is skipped here or Cairn and
    // Brace would be paid twice.
    void ModifyPeriodicDamageAurasTick(Unit* /*target*/, Unit* attacker, uint32& damage,
                                       SpellInfo const* spellInfo) override
    {
        if (!spellInfo || spellInfo->HasAura(SPELL_AURA_PERIODIC_HEAL)
            || spellInfo->HasAura(SPELL_AURA_OBS_MOD_HEALTH))
            return;
        int32 amount = int32(damage);
        ApplyHeroTalentBonus(attacker, 0, amount, false);
        damage = uint32(std::max<int32>(0, amount));
    }

    void ModifySpellDamageTaken(Unit* /*target*/, Unit* attacker, int32& damage,
                                SpellInfo const* spellInfo) override
    {
        ApplyHeroTalentBonus(attacker, spellInfo ? spellInfo->GetSchoolMask() : 0,
                             damage, false);
    }

    void ModifyHealReceived(Unit* /*target*/, Unit* healer, uint32& heal,
                            SpellInfo const* /*spellInfo*/) override
    {
        int32 amount = int32(heal);
        ApplyHeroTalentBonus(healer, 0, amount, true);
        heal = uint32(std::max<int32>(0, amount));
    }

    // Venom Handler: a poison that outlives what it killed.
    //
    // Only a Hero pet's own aura qualifies, which family 14 settles without
    // holding a spell id: the beetle's poisons are forged spells and nothing
    // else a pet casts is. The aura is read out of the corpse BEFORE anything
    // is cast, because casting into a live aura map is how iterators die.
    void OnUnitDeath(Unit* unit, Unit* /*killer*/) override
    {
        if (!unit || !unit->IsInWorld())
            return;

        Creature* beetle = nullptr;
        Player* owner = nullptr;
        uint32 poison = 0;
        int32 spread = 0;
        for (auto const& pair : unit->GetAppliedAuras())
        {
            Aura* aura = pair.second ? pair.second->GetBase() : nullptr;
            if (!aura || aura->GetSpellInfo()->SpellFamilyName != HERO_FAMILY)
                continue;
            Unit* caster = aura->GetCaster();
            if (!caster || !caster->IsCreature() || !caster->IsPet())
                continue;
            Unit* master = caster->GetOwner();
            Player* player = master ? master->ToPlayer() : nullptr;
            if (!player)
                continue;
            spread = HeroTalentAmount(player, ICON_VENOM_HANDLER);
            if (spread <= 0)
                continue;
            beetle = caster->ToCreature();
            owner = player;
            poison = aura->GetId();
            break;
        }
        if (!beetle || !owner || !poison)
            return;

        std::list<Unit*> nearby;
        Acore::AnyUnfriendlyUnitInObjectRangeCheck check(unit, owner, VENOM_SPREAD_RANGE);
        Acore::UnitListSearcher<Acore::AnyUnfriendlyUnitInObjectRangeCheck> searcher(unit, nearby, check);
        Cell::VisitObjects(unit, searcher, VENOM_SPREAD_RANGE);

        for (Unit* next : nearby)
        {
            if (spread <= 0)
                break;
            if (next == unit || !next->IsAlive() || next->HasAura(poison, beetle->GetGUID()))
                continue;
            if (!owner->IsValidAttackTarget(next))
                continue;
            beetle->CastSpell(next, poison, TRIGGERED_FULL_MASK, nullptr, nullptr, owner->GetGUID());
            --spread;
        }
    }
};


// =====================================================================
// The challenge-run rewards.
//
// Twelve abilities, one per challenge, each paid for finishing a run and
// each doing something no class can. The rows (gen_forged_spells.py) carry
// the shape and the look; this is the part a row cannot say. Lines are
// found by recipe key through ForgedLine, never by a written-in id, and a
// line's hidden companion is its first rank plus the same 16 Crossdraw and
// Ricochet use.
//
// Most live in the spell and aura scripts below. Six answer to a hit or a
// death rather than to their own cast, so they are one UnitScript at the end
// of the section: Mark of the Nemesis, Turnabout, Spite Mirror, Sanguine
// Pact, Last Breath's healing and Brink's damage, and Trophy Hunt's trophy.
// =====================================================================
namespace
{
    constexpr uint32 REWARD_COMPANION_OFFSET = 16;      // matches PER_RECIPE / 2

    uint32 RewardLine(char const* key)
    {
        return sClasslessMgr->ForgedLine(key);
    }

    uint32 RewardCompanion(char const* key)
    {
        uint32 const first = RewardLine(key);
        return first ? first + REWARD_COMPANION_OFFSET : 0;
    }

    // every hostile, living, attackable unit within `range` of `centre`, as
    // `asker` judges hostility
    std::vector<Unit*> EnemiesNear(WorldObject* centre, Unit* asker, float range)
    {
        std::list<Unit*> nearby;
        Acore::AnyUnfriendlyUnitInObjectRangeCheck check(centre, asker, range);
        Acore::UnitListSearcher<Acore::AnyUnfriendlyUnitInObjectRangeCheck> searcher(centre, nearby, check);
        Cell::VisitObjects(centre, searcher, range);
        std::vector<Unit*> out;
        for (Unit* u : nearby)
            if (u != centre && u->IsAlive() && asker->IsValidAttackTarget(u))
                out.push_back(u);
        return out;
    }

    // The live amount of one slot of an aura `unit` carries, 0 when it has none.
    int32 AuraSlot(Unit const* unit, uint32 spellId, SpellEffIndex slot, ObjectGuid caster = ObjectGuid::Empty)
    {
        AuraEffect const* eff = unit ? unit->GetAuraEffect(spellId, slot, caster) : nullptr;
        return eff ? eff->GetAmount() : 0;
    }
}

// Giantsbane: a strike that grows with how much bigger the target is.
class spell_cw_giantsbane : public SpellScript
{
    PrepareSpellScript(spell_cw_giantsbane);

    // OnHit runs after the damage is worked out and before it is dealt.
    void Scale()
    {
        Unit* caster = GetCaster();
        Unit* target = GetHitUnit();
        if (!caster || !target || !caster->GetMaxHealth())
            return;
        // slot 2 is the cap, slot 3 the % per 1% of health the target has over you
        int32 const cap = GetSpellInfo()->Effects[EFFECT_1].CalcValue(caster);
        int32 const rate = GetSpellInfo()->Effects[EFFECT_2].CalcValue(caster);
        float const ratio = float(target->GetMaxHealth()) / float(caster->GetMaxHealth());
        int32 const bonus = std::clamp(int32((ratio - 1.0f) * 100.0f * float(rate)), 0, std::max(0, cap));
        if (bonus)
            SetHitDamage(GetHitDamage() * (100 + bonus) / 100);
    }

    void Register() override
    {
        OnHit += SpellHitFn(spell_cw_giantsbane::Scale);
    }
};

// One Against Many: recounts the enemies around you once a second and sets
// the damage done and taken to match.
class spell_cw_one_against_many : public AuraScript
{
    PrepareAuraScript(spell_cw_one_against_many);

    void Count()
    {
        Unit* owner = GetUnitOwner();
        if (!owner)
            return;
        // slot 1 holds the most enemies counted and how near they must be;
        // slots 2 and 3 hold what each one is worth
        SpellInfo const* info = GetSpellInfo();
        float const range = info->Effects[EFFECT_0].CalcRadius(owner);
        uint32 const most = uint32(std::max<int32>(0, info->Effects[EFFECT_0].CalcValue(owner)));
        uint32 const n = std::min<uint32>(uint32(EnemiesNear(owner, owner, range).size()), most);
        if (AuraEffect* up = GetAura()->GetEffect(EFFECT_1))
            up->ChangeAmount(info->Effects[EFFECT_1].CalcValue(owner) * int32(n));
        if (AuraEffect* down = GetAura()->GetEffect(EFFECT_2))
            down->ChangeAmount(info->Effects[EFFECT_2].CalcValue(owner) * int32(n));
    }

    void Applied(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Count();
    }

    void Tick(AuraEffect const* /*aurEff*/)
    {
        Count();
    }

    void Register() override
    {
        AfterEffectApply += AuraEffectApplyFn(spell_cw_one_against_many::Applied, EFFECT_0,
                                              SPELL_AURA_PERIODIC_DUMMY, AURA_EFFECT_HANDLE_REAL);
        OnEffectPeriodic += AuraEffectPeriodicFn(spell_cw_one_against_many::Tick, EFFECT_0,
                                                 SPELL_AURA_PERIODIC_DUMMY);
    }
};

// Rewind: keeps where you stood and what you had, and puts you back when the
// mark runs out or is cancelled. A death in the six seconds is not undone.
class spell_cw_rewind : public AuraScript
{
    PrepareAuraScript(spell_cw_rewind);

    uint32 _map = 0;
    uint32 _instance = 0;
    float _x = 0.0f, _y = 0.0f, _z = 0.0f, _o = 0.0f;
    uint32 _health = 0;
    int32 _mana = 0, _rage = 0, _energy = 0;
    bool _marked = false;

    void Mark(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Player* player = GetUnitOwner() ? GetUnitOwner()->ToPlayer() : nullptr;
        if (!player)
            return;
        _map = player->GetMapId();
        _instance = player->GetInstanceId();
        player->GetPosition(_x, _y, _z, _o);
        _health = player->GetHealth();
        _mana = player->GetPower(POWER_MANA);
        _rage = player->GetPower(POWER_RAGE);
        _energy = player->GetPower(POWER_ENERGY);
        _marked = true;
    }

    void Return(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        AuraRemoveMode const how = GetTargetApplication()->GetRemoveMode();
        if (!_marked || (how != AURA_REMOVE_BY_EXPIRE && how != AURA_REMOVE_BY_CANCEL))
            return;
        Player* player = GetUnitOwner() ? GetUnitOwner()->ToPlayer() : nullptr;
        if (!player || !player->IsAlive() || player->GetMapId() != _map || player->GetInstanceId() != _instance)
            return;
        uint32 const flash = GetId() + REWARD_COMPANION_OFFSET;
        float const x = _x, y = _y, z = _z, o = _o;
        uint32 const health = _health;
        int32 const mana = _mana, rage = _rage, energy = _energy;
        // A tick out, not here: this runs inside the aura's own removal, and a
        // teleport is not something to start from the middle of that.
        player->m_Events.AddEventAtOffset([player, flash, x, y, z, o, health, mana, rage, energy]()
        {
            if (!player->IsInWorld() || !player->IsAlive())
                return;
            player->NearTeleportTo(x, y, z, o);
            player->SetHealth(std::min<uint32>(std::max<uint32>(health, 1), player->GetMaxHealth()));
            player->SetPower(POWER_MANA, std::min<int32>(mana, player->GetMaxPower(POWER_MANA)));
            player->SetPower(POWER_RAGE, std::min<int32>(rage, player->GetMaxPower(POWER_RAGE)));
            player->SetPower(POWER_ENERGY, std::min<int32>(energy, player->GetMaxPower(POWER_ENERGY)));
            if (sSpellMgr->GetSpellInfo(flash))
                player->CastSpell(player, flash, true);
        }, 1ms);
    }

    void Register() override
    {
        AfterEffectApply += AuraEffectApplyFn(spell_cw_rewind::Mark, EFFECT_0, SPELL_AURA_DUMMY,
                                              AURA_EFFECT_HANDLE_REAL);
        AfterEffectRemove += AuraEffectRemoveFn(spell_cw_rewind::Return, EFFECT_0, SPELL_AURA_DUMMY,
                                                AURA_EFFECT_HANDLE_REAL);
    }
};

// Shatterpoint: health spent as power. The shard carries three times what
// was paid, then bursts into everything near the target for half.
class spell_cw_shatterpoint : public SpellScript
{
    PrepareSpellScript(spell_cw_shatterpoint);

    uint32 _spent = 0;
    int32 _total = 0;

    // paid when the cast completes, as the shard leaves the hand
    void Spend()
    {
        Unit* caster = GetCaster();
        if (!caster)
            return;
        _spent = caster->CountPctFromCurHealth(GetSpellInfo()->Effects[EFFECT_1].CalcValue(caster));
        if (_spent >= caster->GetHealth())
            _spent = caster->GetHealth() > 1 ? caster->GetHealth() - 1 : 0;
        if (_spent)
            caster->ModifyHealth(-int32(_spent));
    }

    void Empower()
    {
        _total = GetHitDamage()
            + int32(CalculatePct(_spent, GetSpellInfo()->Effects[EFFECT_2].CalcValue(GetCaster())));
        SetHitDamage(_total);
    }

    // Each shard is cast BY the target at an enemy near it, with the Hero as
    // original caster, the way Ricochet Shot's bounces are: the missile is
    // drawn from the shattering point and the damage is the Hero's.
    void Shatter()
    {
        Unit* target = GetHitUnit();
        Player* owner = GetCaster() ? GetCaster()->ToPlayer() : nullptr;
        if (!target || !owner || _total < 2)
            return;
        uint32 const shard = GetSpellInfo()->Id + REWARD_COMPANION_OFFSET;
        SpellInfo const* shardInfo = sSpellMgr->GetSpellInfo(shard);
        if (!shardInfo)
            return;
        // the shard's slot 2: its share of the damage, and how far it shatters
        int32 const share = CalculatePct(_total, shardInfo->Effects[EFFECT_1].CalcValue(owner));
        if (share < 1)
            return;
        for (Unit* next : EnemiesNear(target, owner, shardInfo->Effects[EFFECT_1].CalcRadius(owner)))
        {
            CustomSpellValues values;
            values.AddSpellMod(SPELLVALUE_BASE_POINT0, share);
            target->CastCustomSpell(shard, values, next, TRIGGERED_FULL_MASK, nullptr, nullptr, owner->GetGUID());
        }
    }

    void Register() override
    {
        OnCast += SpellCastFn(spell_cw_shatterpoint::Spend);
        OnHit += SpellHitFn(spell_cw_shatterpoint::Empower);
        AfterHit += SpellHitFn(spell_cw_shatterpoint::Shatter);
    }
};

// Last Breath: an unlimited absorb that answers only a killing blow, once
// every five minutes, the way the rogue's Cheat Death is built. The cooldown
// sits on the companion, which is the buff that follows.
class spell_cw_last_breath : public AuraScript
{
    PrepareAuraScript(spell_cw_last_breath);

    void Unlimited(AuraEffect const* /*aurEff*/, int32& amount, bool& /*canBeRecalculated*/)
    {
        amount = -1;
    }

    void Absorb(AuraEffect* /*aurEff*/, DamageInfo& dmgInfo, uint32& absorbAmount)
    {
        absorbAmount = 0;
        Player* player = GetTarget() ? GetTarget()->ToPlayer() : nullptr;
        if (!player || dmgInfo.GetDamage() < player->GetHealth())
            return;
        uint32 const buff = GetId() + REWARD_COMPANION_OFFSET;
        if (!sSpellMgr->GetSpellInfo(buff) || player->HasSpellCooldown(buff))
            return;
        absorbAmount = dmgInfo.GetDamage() - player->GetHealth() + 1;
        player->CastSpell(player, buff, true);
        // slot 2 is the cooldown, in seconds
        player->AddSpellCooldown(buff, 0, uint32(std::max<int32>(0, GetSpellInfo()->Effects[EFFECT_1].CalcValue(player)))
                                          * IN_MILLISECONDS);
        ChatHandler(player->GetSession()).SendSysMessage("|cffff8800Last Breath|r: you refuse to fall.");
    }

    void Register() override
    {
        DoEffectCalcAmount += AuraEffectCalcAmountFn(spell_cw_last_breath::Unlimited, EFFECT_0,
                                                     SPELL_AURA_SCHOOL_ABSORB);
        OnEffectAbsorb += AuraEffectAbsorbFn(spell_cw_last_breath::Absorb, EFFECT_0);
    }
};

// Brink: for its duration no blow is a killing blow. The damage it adds is
// in cw_reward_effects.
class spell_cw_brink : public AuraScript
{
    PrepareAuraScript(spell_cw_brink);

    void Unlimited(AuraEffect const* /*aurEff*/, int32& amount, bool& /*canBeRecalculated*/)
    {
        amount = -1;
    }

    void Absorb(AuraEffect* /*aurEff*/, DamageInfo& dmgInfo, uint32& absorbAmount)
    {
        absorbAmount = 0;
        Unit* target = GetTarget();
        if (target && dmgInfo.GetDamage() >= target->GetHealth())
            absorbAmount = dmgInfo.GetDamage() - target->GetHealth() + 1;
    }

    void Register() override
    {
        DoEffectCalcAmount += AuraEffectCalcAmountFn(spell_cw_brink::Unlimited, EFFECT_0,
                                                     SPELL_AURA_SCHOOL_ABSORB);
        OnEffectAbsorb += AuraEffectAbsorbFn(spell_cw_brink::Absorb, EFFECT_0);
    }
};

// Ironbound: armour equal to half the caster's maximum health, worked out as
// the aura goes up.
class spell_cw_ironbound : public AuraScript
{
    PrepareAuraScript(spell_cw_ironbound);

    void Armor(AuraEffect const* /*aurEff*/, int32& amount, bool& /*canBeRecalculated*/)
    {
        if (Unit* caster = GetCaster())
            amount = int32(caster->CountPctFromMaxHealth(GetSpellInfo()->Effects[EFFECT_0].CalcValue(caster)));
    }

    void Register() override
    {
        DoEffectCalcAmount += AuraEffectCalcAmountFn(spell_cw_ironbound::Armor, EFFECT_0,
                                                     SPELL_AURA_MOD_RESISTANCE);
    }
};

// Trophy Hunt: only big game. The trophy itself is paid in cw_reward_effects
// when the quarry dies.
class spell_cw_trophy_hunt : public SpellScript
{
    PrepareSpellScript(spell_cw_trophy_hunt);

    SpellCastResult Quarry()
    {
        Creature* creature = GetExplTargetUnit() ? GetExplTargetUnit()->ToCreature() : nullptr;
        if (!creature)
            return SPELL_FAILED_BAD_TARGETS;
        CreatureTemplate const* tmpl = creature->GetCreatureTemplate();
        if ((tmpl && tmpl->rank != CREATURE_ELITE_NORMAL) || creature->IsDungeonBoss())
            return SPELL_CAST_OK;
        return SPELL_FAILED_BAD_TARGETS;
    }

    void Register() override
    {
        OnCheckCast += SpellCheckCastFn(spell_cw_trophy_hunt::Quarry);
    }
};

// What the rewards do when somebody is hit or dies.
class cw_reward_effects : public UnitScript
{
public:
    cw_reward_effects() : UnitScript("cw_reward_effects", true, {
        UNITHOOK_MODIFY_MELEE_DAMAGE,
        UNITHOOK_MODIFY_SPELL_DAMAGE_TAKEN,
        UNITHOOK_ON_UNIT_DEATH
    }) { }

    void ModifyMeleeDamage(Unit* target, Unit* attacker, uint32& damage) override
    {
        Apply(target, attacker, damage, nullptr);
    }

    void ModifySpellDamageTaken(Unit* target, Unit* attacker, int32& damage, SpellInfo const* spellInfo) override
    {
        if (damage <= 0)
            return;
        uint32 amount = uint32(damage);
        Apply(target, attacker, amount, spellInfo);
        damage = int32(amount);
    }

    void OnUnitDeath(Unit* unit, Unit* /*killer*/) override
    {
        if (!unit || !unit->IsInWorld())
            return;

        // Mark of the Nemesis: the marker is paid back, and the mark leaps.
        if (uint32 const mark = RewardLine("mark_of_the_nemesis"))
            if (Aura* aura = unit->GetAura(mark))
                if (Player* player = aura->GetCaster() ? aura->GetCaster()->ToPlayer() : nullptr)
                    if (player->IsAlive())
                    {
                        SpellInfo const* info = aura->GetSpellInfo();
                        int32 const restore = info->Effects[EFFECT_1].CalcValue(player);
                        float const leap = float(info->Effects[EFFECT_2].CalcValue(player));
                        player->ModifyHealth(int32(player->CountPctFromMaxHealth(restore)));
                        player->ModifyPower(POWER_MANA, int32(CalculatePct(player->GetMaxPower(POWER_MANA), restore)));
                        if (uint32 const due = mark + REWARD_COMPANION_OFFSET; sSpellMgr->GetSpellInfo(due))
                            player->CastSpell(player, due, true);   // the golden surge
                        Unit* next = nullptr;
                        float best = leap + 1.0f;
                        for (Unit* u : EnemiesNear(player, player, leap))
                            if (u != unit && !u->HasAura(mark, player->GetGUID()))
                                if (float const d = player->GetDistance(u); d < best)
                                {
                                    next = u;
                                    best = d;
                                }
                        if (next)
                            player->CastSpell(next, mark, TRIGGERED_FULL_MASK);
                    }

        // Trophy Hunt: big game down, a trophy taken.
        if (uint32 const quarry = RewardLine("trophy_hunt"))
            if (Aura* aura = unit->GetAura(quarry))
                if (Player* player = aura->GetCaster() ? aura->GetCaster()->ToPlayer() : nullptr)
                    if (uint32 const trophy = quarry + REWARD_COMPANION_OFFSET;
                        player->IsAlive() && sSpellMgr->GetSpellInfo(trophy))
                        player->CastSpell(player, trophy, true);
    }

private:
    void Apply(Unit* target, Unit* attacker, uint32& damage, SpellInfo const* spellInfo)
    {
        if (!target || !attacker || !damage || target == attacker)
            return;

        // ---- the Hero dealing it ----------------------------------------------
        if (Player* dealer = attacker->ToPlayer())
        {
            int32 pct = 100;
            if (uint32 const mark = RewardLine("mark_of_the_nemesis"))
                pct += AuraSlot(target, mark, EFFECT_0, dealer->GetGUID());
            if (uint32 const stun = RewardCompanion("turnabout"); stun && target->HasAura(stun, dealer->GetGUID()))
                pct += SlotValue(RewardLine("turnabout"), EFFECT_0, dealer);
            if (uint32 const brink = RewardLine("brink"); brink && dealer->HasAura(brink))
            {
                // slot 2: % per 1% of health missing; slot 3: the cap
                int32 const rate = AuraSlot(dealer, brink, EFFECT_1);
                int32 const cap = AuraSlot(dealer, brink, EFFECT_2);
                pct += std::min<int32>(cap, int32((100.0f - dealer->GetHealthPct()) * float(rate)));
            }
            if (pct != 100)
                damage = uint32(uint64(damage) * uint32(pct) / 100);

            if (dealer->IsAlive())
            {
                if (uint32 const breath = RewardCompanion("last_breath"); breath && dealer->HasAura(breath))
                    dealer->ModifyHealth(int32(CalculatePct(damage, AuraSlot(dealer, breath, EFFECT_0))));
                else if (uint32 const pact = RewardLine("sanguine_pact"); pact && dealer->HasAura(pact))
                    Sanguine(dealer, CalculatePct(damage, AuraSlot(dealer, pact, EFFECT_0)),
                             AuraSlot(dealer, pact, EFFECT_1));
            }
        }

        // ---- the Hero taking it -----------------------------------------------
        Player* victim = target->ToPlayer();
        if (!victim || !victim->IsAlive())
            return;
        // the third Spite Mirror sends back must not be sent back again
        uint32 const spite = RewardLine("spite_mirror");
        uint32 const spiteBolt = RewardCompanion("spite_mirror");
        if (spite && victim->HasAura(spite) && !(spellInfo && spellInfo->Id == spiteBolt))
            Later(victim, attacker, spiteBolt, int32(CalculatePct(damage, AuraSlot(victim, spite, EFFECT_0))));
        if (uint32 const turn = RewardLine("turnabout"); turn && victim->HasAura(turn) && victim->IsValidAttackTarget(attacker))
        {
            victim->RemoveAurasDueToSpell(turn);
            Turn(victim, attacker);
        }
    }

    // Heal by the hit; what spills over full health grows the shield, held
    // to `capPct` of maximum health (the pact's slot 2).
    static void Sanguine(Player* dealer, uint32 heal, int32 capPct)
    {
        uint32 const missing = dealer->GetMaxHealth() - dealer->GetHealth();
        uint32 const healed = std::min(heal, missing);
        if (healed)
            dealer->ModifyHealth(int32(healed));
        uint32 const over = heal - healed;
        uint32 const shield = RewardCompanion("sanguine_pact");
        if (!over || !shield)
            return;
        int32 const cap = int32(dealer->CountPctFromMaxHealth(capPct));
        if (AuraEffect* eff = dealer->GetAuraEffect(shield, EFFECT_0))
            eff->ChangeAmount(std::min<int32>(cap, eff->GetAmount() + int32(over)));
        else
            Later(dealer, dealer, shield, std::min<int32>(cap, int32(over)));
    }

    // A cast a tick out, never from inside the damage being worked out: the
    // other unit is looked up again by guid when it runs.
    static void Later(Player* caster, Unit* target, uint32 spellId, int32 amount)
    {
        if (!spellId || amount < 1 || !sSpellMgr->GetSpellInfo(spellId))
            return;
        ObjectGuid const targetGuid = target->GetGUID();
        caster->m_Events.AddEventAtOffset([caster, targetGuid, spellId, amount]()
        {
            Unit* to = ObjectAccessor::GetUnit(*caster, targetGuid);
            if (!to || !to->IsAlive() || !caster->IsAlive())
                return;
            CustomSpellValues values;
            values.AddSpellMod(SPELLVALUE_BASE_POINT0, amount);
            caster->CastCustomSpell(spellId, values, to, TRIGGERED_FULL_MASK);
        }, 1ms);
    }

    // Turnabout: step behind the one who struck, and stun it.
    static void Turn(Player* victim, Unit* attacker)
    {
        uint32 const stun = RewardCompanion("turnabout");
        ObjectGuid const attackerGuid = attacker->GetGUID();
        victim->m_Events.AddEventAtOffset([victim, attackerGuid, stun]()
        {
            Unit* foe = ObjectAccessor::GetUnit(*victim, attackerGuid);
            if (!foe || !foe->IsAlive() || !victim->IsAlive())
                return;
            Position behind = foe->GetNearPosition(1.5f, float(M_PI));
            victim->NearTeleportTo(behind.GetPositionX(), behind.GetPositionY(), behind.GetPositionZ(),
                                   behind.GetAngle(foe));
            if (stun && sSpellMgr->GetSpellInfo(stun))
                victim->CastSpell(foe, stun, TRIGGERED_FULL_MASK);
        }, 1ms);
    }
};

void AddClasslessForgedScripts()
{
    new cw_forged_pet_model();
    new cw_forged_sentry();
    new cw_forged_talents();
    new cw_forged_watcher();
    RegisterSpellScript(spell_cw_crossdraw);
    RegisterSpellScript(spell_cw_ricochet_shot);
    RegisterSpellScript(spell_cw_ricochet_shot_bounce);
    RegisterSpellScript(spell_cw_quickening);
    RegisterSpellScript(spell_cw_repertoire);
    RegisterSpellScript(spell_cw_wildcard_surge);
    RegisterSpellScript(spell_cw_makeshift_strike);
    RegisterSpellScript(spell_cw_reserve_break);
    RegisterSpellScript(spell_cw_ward_off);
    RegisterSpellScript(spell_cw_area_control);
    RegisterSpellScript(spell_cw_emberfeed);
    RegisterSpellScript(spell_cw_overflow);
    RegisterSpellScript(spell_cw_healing_spit);
    // the challenge-run rewards
    new cw_reward_effects();
    RegisterSpellScript(spell_cw_giantsbane);
    RegisterSpellScript(spell_cw_one_against_many);
    RegisterSpellScript(spell_cw_rewind);
    RegisterSpellScript(spell_cw_shatterpoint);
    RegisterSpellScript(spell_cw_last_breath);
    RegisterSpellScript(spell_cw_brink);
    RegisterSpellScript(spell_cw_ironbound);
    RegisterSpellScript(spell_cw_trophy_hunt);
}
