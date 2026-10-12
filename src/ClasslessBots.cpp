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
 */

#include "ClasslessBots.h"

// Only a realm built with mod-playerbots has its headers on the include path
// (a static module build collects every module's include directories into
// one list), so this is how the module tells whether playerbots is there.
#if __has_include("PlayerbotAI.h")

#include "ClasslessMgr.h"
#include "Creature.h"
#include "DBCStores.h"
#include "Group.h"
#include "Log.h"
#include "ObjectMgr.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Spell.h"
#include "SpellAuraDefines.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"

#include "Action.h"
#include "AiObjectContext.h"
#include "MeleeCombatStrategy.h"
#include "MovementActions.h"
#include "Multiplier.h"
#include "NamedObjectContext.h"
#include "PlayerbotAI.h"
#include "Playerbots.h"
#include "RangedCombatStrategy.h"
#include "Strategy.h"
#include "Value.h"

#include "DKAiObjectContext.h"
#include "DruidAiObjectContext.h"
#include "HunterAiObjectContext.h"
#include "MageAiObjectContext.h"
#include "PaladinAiObjectContext.h"
#include "PriestAiObjectContext.h"
#include "RogueAiObjectContext.h"
#include "ShamanAiObjectContext.h"
#include "WarlockAiObjectContext.h"
#include "WarriorAiObjectContext.h"

#include <array>
#include <memory>
#include <set>
#include <string>
#include <vector>

using namespace ClasslessWildcard;

namespace
{
    // ---------------------------------------------------------------------
    // How the bot decides. Spell numbers (damage, healing, range, radius,
    // cost) all come from the spells themselves; these are the bot's own
    // judgement calls.
    // ---------------------------------------------------------------------
    constexpr float HEALER_HEAL_BELOW   = 90.0f;  // a healer tops up anyone under this
    constexpr float HEALER_HOT_BELOW    = 97.0f;  // and keeps a heal over time on them under this
    constexpr float HEALER_SHIELD_BELOW = 85.0f;  // and shields them under this, in combat
    constexpr float SELF_HEAL_BELOW     = 50.0f;  // anyone else heals themselves under this
    constexpr float OTHERS_HEAL_BELOW   = 35.0f;  // and a party member under this
    constexpr float BIG_HEAL_BELOW      = 50.0f;  // below this the strongest heal, above it the cheapest
    constexpr float OUT_OF_COMBAT_HEAL  = 70.0f;  // out of combat, top up anyone under this
    constexpr float DEFENSIVE_BELOW     = 35.0f;  // own health that calls for a defensive cooldown
    constexpr float DOT_TARGET_ABOVE    = 25.0f;  // not worth a damage over time on a target under this
    constexpr float BURST_TARGET_ABOVE  = 40.0f;  // offensive cooldowns on a strong target above this
    constexpr uint32 AOE_MIN_ENEMIES    = 3;      // area damage is for this many or more
    constexpr uint8 FINISHER_POINTS     = 4;      // combo points a finisher waits for
    constexpr float FINISHER_EXECUTE    = 25.0f;  // unless the target is under this
    constexpr uint32 BUFF_MIN_DURATION  = 60 * IN_MILLISECONDS;  // shorter auras are cooldowns, not buffs
    constexpr uint32 CONTROL_MIN_DURATION = 10 * IN_MILLISECONDS; // a confuse this long is crowd control, not a gouge
    constexpr float DEBUFF_TARGET_ABOVE = 50.0f;  // a weak enemy below this dies before a debuff pays off
    constexpr float ESCAPE_BELOW        = 60.0f;  // a ranged Hero roots or fears its way out under this
    constexpr float APPROACH_MARGIN     = 2.0f;   // yards inside a spell's range the bot walks to
    constexpr float TOTEM_KEEP_DISTANCE = 20.0f;  // a totem further than this from the bot is left behind
    constexpr uint32 GUARDIAN_MIN_ENEMIES = 2;    // or a strong enemy: worth calling a temporary fighter
    constexpr uint32 COOLDOWN_MIN       = 30 * IN_MILLISECONDS;  // a defensive or offensive cooldown
    constexpr uint32 KIT_REBUILD_MS     = 5 * IN_MILLISECONDS;   // how often a bot re-reads its spellbook
    constexpr uint32 FORM_SWITCH_MS     = 10 * IN_MILLISECONDS;  // shortest time between form changes

    constexpr char const* S_CLASSLESS    = "classless";
    constexpr char const* S_CLASSLESS_NC = "classless nc";
    constexpr char const* S_TANK         = "classless tank";
    constexpr char const* S_HEAL         = "classless heal";
    constexpr char const* S_MELEE        = "classless melee";
    constexpr char const* S_RANGED       = "classless ranged";
    constexpr char const* V_KIT          = "classless kit";

    // ---------------------------------------------------------------------
    // The kit: every spell the Hero owns, sorted by what it does.
    // ---------------------------------------------------------------------
    enum class Kind : uint8
    {
        Nuke,       // direct damage on one enemy
        Dot,        // damage over time on one enemy
        Aoe,        // damage to every enemy in an area
        Heal,       // direct heal
        Hot,        // heal over time
        Shield,     // damage absorb on a friend
        Interrupt,  // stops a spell being cast
        Taunt,      // makes the target attack the caster
        Buff,       // a long aura the caster keeps up
        Defensive,  // a cooldown that keeps the caster alive
        Burst,      // a cooldown that raises the caster's damage
        Form,       // a shapeshift form or stance
        Debuff,     // weakens an enemy without hurting it (armor, attack power, marks)
        Control,    // long crowd control that breaks on damage (polymorph, sleep, banish, shackle)
        Stun,       // short stun or silence on one enemy: stops a cast when there is no interrupt
        Escape,     // roots, fears or stuns everything around the caster
        Pet,        // summons the Hero's permanent pet
        Totem,      // drops a totem into one of the four element slots
        Guardian,   // summons a fighter for a while (Water Elemental, Feral Spirit)
        Fear,       // fears one enemy
    };

    struct KitSpell
    {
        uint32 id = 0;
        SpellInfo const* info = nullptr;
        Kind kind = Kind::Nuke;
        bool melee = false;       // melee range
        bool dest = false;        // cast at a point on the ground
        bool aroundSelf = false;  // an area centred on the caster
        bool selfOnly = false;    // cannot be cast on anyone else
        float radius = 0.0f;      // area spells
        float estimate = 0.0f;    // damage or healing per cast, from the spell's own values
        uint32 form = 0;          // Kind::Form: the ShapeshiftForm it enters
        uint32 entry = 0;         // Kind::Totem, Kind::Guardian: the creature it summons
        uint8 slot = 0;           // Kind::Totem: SUMMON_SLOT_TOTEM_FIRE .. _AIR
        bool offensive = false;   // Kind::Totem: it attacks, rather than helping the party
    };

    struct Kit
    {
        std::vector<KitSpell> spells;
        ClasslessBots::Role role = ClasslessBots::ROLE_MELEE;
        bool runes = false;       // the Hero has a rune block, so rune spells can be paid for
    };

    using KitPtr = std::shared_ptr<Kit const>;

    bool HasAnyAura(SpellInfo const* info, std::initializer_list<AuraType> auras)
    {
        for (AuraType a : auras)
            if (info->HasAura(a))
                return true;
        return false;
    }

    bool IsDamageEffect(uint32 effect)
    {
        switch (effect)
        {
            case SPELL_EFFECT_SCHOOL_DAMAGE:
            case SPELL_EFFECT_WEAPON_DAMAGE:
            case SPELL_EFFECT_WEAPON_DAMAGE_NOSCHOOL:
            case SPELL_EFFECT_NORMALIZED_WEAPON_DMG:
            case SPELL_EFFECT_WEAPON_PERCENT_DAMAGE:
            case SPELL_EFFECT_HEALTH_LEECH:
                return true;
            default:
                return false;
        }
    }

    bool IsPeriodicDamageAura(uint32 aura)
    {
        return aura == SPELL_AURA_PERIODIC_DAMAGE || aura == SPELL_AURA_PERIODIC_LEECH
            || aura == SPELL_AURA_PERIODIC_DAMAGE_PERCENT;
    }

    bool IsHealEffect(uint32 effect)
    {
        return effect == SPELL_EFFECT_HEAL || effect == SPELL_EFFECT_HEAL_PCT || effect == SPELL_EFFECT_HEAL_MAX_HEALTH;
    }

    bool IsAuraEffect(uint32 effect)
    {
        return effect == SPELL_EFFECT_APPLY_AURA || effect == SPELL_EFFECT_APPLY_AREA_AURA_PARTY
            || effect == SPELL_EFFECT_APPLY_AREA_AURA_RAID;
    }

    // Spells a combat AI has no business casting on its own: travel, utility,
    // summons other than the permanent pet (Classify takes that first), item
    // makers, resurrection.
    bool IsNotForCombat(SpellInfo const* info)
    {
        if (info->IsPassive() || info->IsRequiringDeadTarget() || info->IsAutoRepeatRangedSpell())
            return true;
        if (HasAnyAura(info, { SPELL_AURA_MOUNTED, SPELL_AURA_FLY, SPELL_AURA_MOD_STEALTH,
                               SPELL_AURA_MOD_INVISIBILITY, SPELL_AURA_TRANSFORM, SPELL_AURA_CONTROL_VEHICLE }))
            return true;
        for (SpellEffectInfo const& eff : info->Effects)
        {
            switch (eff.Effect)
            {
                case SPELL_EFFECT_SUMMON:
                case SPELL_EFFECT_SUMMON_PET:
                case SPELL_EFFECT_TELEPORT_UNITS:
                case SPELL_EFFECT_TELEPORT_UNITS_FACE_CASTER:
                case SPELL_EFFECT_RESURRECT:
                case SPELL_EFFECT_RESURRECT_NEW:
                case SPELL_EFFECT_SELF_RESURRECT:
                case SPELL_EFFECT_CREATE_ITEM:
                case SPELL_EFFECT_CREATE_ITEM_2:
                case SPELL_EFFECT_ENCHANT_ITEM:
                case SPELL_EFFECT_ENCHANT_ITEM_TEMPORARY:
                case SPELL_EFFECT_TRANS_DOOR:
                case SPELL_EFFECT_SUMMON_OBJECT_WILD:
                case SPELL_EFFECT_SUMMON_OBJECT_SLOT1:
                case SPELL_EFFECT_SUMMON_PLAYER:
                case SPELL_EFFECT_LEARN_SPELL:
                case SPELL_EFFECT_TAMECREATURE:
                case SPELL_EFFECT_OPEN_LOCK:
                case SPELL_EFFECT_SKINNING:
                case SPELL_EFFECT_PICKPOCKET:
                case SPELL_EFFECT_DISMISS_PET:
                case SPELL_EFFECT_FEED_PET:
                    return true;
                default:
                    break;
            }
        }
        return false;
    }

    // The combat forms worth standing in. Travel, aquatic, flight and the
    // like change how the Hero moves, not how it fights.
    bool IsCombatForm(uint32 form)
    {
        switch (form)
        {
            case FORM_CAT:
            case FORM_TREE:
            case FORM_BEAR:
            case FORM_DIREBEAR:
            case FORM_BATTLESTANCE:
            case FORM_DEFENSIVESTANCE:
            case FORM_BERSERKERSTANCE:
            case FORM_METAMORPHOSIS:
            case FORM_SHADOW:
            case FORM_MOONKIN:
                return true;
            default:
                return false;
        }
    }

    // Damage one cast deals, from the spell's own effect values. Weapon
    // strikes add the main hand's average swing.
    float EstimateDamage(Player* bot, SpellInfo const* info)
    {
        float avgWeapon = (bot->GetWeaponDamageRange(BASE_ATTACK, MINDAMAGE) + bot->GetWeaponDamageRange(BASE_ATTACK, MAXDAMAGE)) / 2.0f;
        float total = 0.0f;
        for (SpellEffectInfo const& eff : info->Effects)
        {
            if (!eff.Effect)
                continue;
            float value = float(std::max(0, eff.CalcValue(bot)));
            switch (eff.Effect)
            {
                case SPELL_EFFECT_WEAPON_DAMAGE:
                case SPELL_EFFECT_WEAPON_DAMAGE_NOSCHOOL:
                case SPELL_EFFECT_NORMALIZED_WEAPON_DMG:
                    total += avgWeapon + value;
                    break;
                case SPELL_EFFECT_WEAPON_PERCENT_DAMAGE:
                    total += avgWeapon * value / 100.0f;
                    break;
                case SPELL_EFFECT_SCHOOL_DAMAGE:
                case SPELL_EFFECT_HEALTH_LEECH:
                    total += value;
                    break;
                default:
                    if (IsAuraEffect(eff.Effect) && IsPeriodicDamageAura(eff.ApplyAuraName) && eff.Amplitude > 0)
                    {
                        int32 duration = info->GetDuration();
                        if (duration > 0)
                            total += value * float(duration / eff.Amplitude);
                    }
                    break;
            }
        }
        return total;
    }

    float EstimateHealing(Player* bot, SpellInfo const* info)
    {
        float total = 0.0f;
        for (SpellEffectInfo const& eff : info->Effects)
        {
            if (!eff.Effect)
                continue;
            float value = float(std::max(0, eff.CalcValue(bot)));
            if (eff.Effect == SPELL_EFFECT_HEAL)
                total += value;
            else if (eff.Effect == SPELL_EFFECT_HEAL_PCT)
                total += bot->GetMaxHealth() * value / 100.0f;
            else if (eff.Effect == SPELL_EFFECT_HEAL_MAX_HEALTH)
                total += bot->GetMaxHealth();
            else if (IsAuraEffect(eff.Effect) && eff.ApplyAuraName == SPELL_AURA_PERIODIC_HEAL && eff.Amplitude > 0)
            {
                int32 duration = info->GetDuration();
                if (duration > 0)
                    total += value * float(duration / eff.Amplitude);
            }
            else if (IsAuraEffect(eff.Effect) && eff.ApplyAuraName == SPELL_AURA_SCHOOL_ABSORB)
                total += value;
        }
        return total;
    }

    uint32 Cooldown(SpellInfo const* info)
    {
        return std::max(info->RecoveryTime, info->CategoryRecoveryTime);
    }

    bool IsMeleeRange(SpellInfo const* info)
    {
        return (info->RangeEntry && (info->RangeEntry->Flags & SPELL_RANGE_MELEE))
            || info->DmgClass == SPELL_DAMAGE_CLASS_MELEE;
    }

    // What a summoned creature does, from the first spell on its template.
    // A totem's spell is often a pulse (PERIODIC_TRIGGER_SPELL), so a pulse
    // is followed one step to what it fires.
    SpellInfo const* SummonedSpell(uint32 entry)
    {
        CreatureTemplate const* ct = sObjectMgr->GetCreatureTemplate(entry);
        if (!ct)
            return nullptr;
        for (uint32 spellId : ct->spells)
        {
            SpellInfo const* info = spellId ? sSpellMgr->GetSpellInfo(spellId) : nullptr;
            if (!info)
                continue;
            for (SpellEffectInfo const& eff : info->Effects)
                if (IsAuraEffect(eff.Effect) && eff.ApplyAuraName == SPELL_AURA_PERIODIC_TRIGGER_SPELL && eff.TriggerSpell)
                    if (SpellInfo const* pulse = sSpellMgr->GetSpellInfo(eff.TriggerSpell))
                        return pulse;
            return info;
        }
        return nullptr;
    }

    // Totems and temporary fighters. A totem counts only when it either
    // attacks (Searing, Magma) or helps the whole party (Strength of Earth,
    // Mana Spring, Healing Stream, Windfury). Tremor, Grounding, Earthbind and
    // the cleansing totems answer one situation each and are left to the
    // owner, and totems with a long cooldown (the elementals, Mana Tide) are
    // not spent on whatever the bot happens to be fighting.
    bool ClassifySummon(SpellInfo const* info, KitSpell& out)
    {
        for (SpellEffectInfo const& eff : info->Effects)
        {
            if (eff.Effect != SPELL_EFFECT_SUMMON)
                continue;
            SummonPropertiesEntry const* props = sSummonPropertiesStore.LookupEntry(uint32(eff.MiscValueB));
            if (!props || !eff.MiscValue)
                continue;
            out.entry = uint32(eff.MiscValue);

            if (props->Type == SUMMON_TYPE_TOTEM)
            {
                if (props->Slot < SUMMON_SLOT_TOTEM_FIRE || props->Slot > SUMMON_SLOT_TOTEM_AIR)
                    return false;
                if (Cooldown(info) >= COOLDOWN_MIN)
                    return false;
                SpellInfo const* does = SummonedSpell(out.entry);
                if (!does)
                    return false;
                bool attacks = false, helps = false;
                for (SpellEffectInfo const& e : does->Effects)
                {
                    if (IsDamageEffect(e.Effect) || (IsAuraEffect(e.Effect) && IsPeriodicDamageAura(e.ApplyAuraName)))
                        attacks = true;
                    if (e.Effect == SPELL_EFFECT_APPLY_AREA_AURA_PARTY || e.Effect == SPELL_EFFECT_APPLY_AREA_AURA_RAID
                        || IsHealEffect(e.Effect) || e.Effect == SPELL_EFFECT_ENERGIZE)
                        helps = true;
                }
                if (!attacks && !(helps && does->IsPositive()))
                    return false;
                out.kind = Kind::Totem;
                out.slot = uint8(props->Slot);
                out.offensive = attacks;
                out.radius = does->GetMaxRange(false);
                for (SpellEffectInfo const& e : does->Effects)
                    if (e.Effect)
                        out.radius = std::max(out.radius, e.CalcRadius());
                out.selfOnly = !out.dest;
                return true;
            }

            bool fighter = props->Category == SUMMON_CATEGORY_PET
                || props->Type == SUMMON_TYPE_PET || props->Type == SUMMON_TYPE_GUARDIAN
                || props->Type == SUMMON_TYPE_MINION || props->Type == SUMMON_TYPE_GUARDIAN2;
            if (!fighter || props->Category == SUMMON_CATEGORY_PUPPET || props->Category == SUMMON_CATEGORY_VEHICLE)
                return false;
            if (!sObjectMgr->GetCreatureTemplate(out.entry))
                return false;
            out.kind = Kind::Guardian;
            return true;
        }
        return false;
    }

    // What one spell does, or false when it is nothing a combat AI casts.
    bool Classify(Player* bot, SpellInfo const* info, KitSpell& out)
    {
        out.info = info;
        out.id = info->Id;

        out.melee = IsMeleeRange(info);
        out.dest = (info->GetExplicitTargetMask() & TARGET_FLAG_DEST_LOCATION) != 0;
        bool explicitUnit = info->NeedsExplicitUnitTarget();
        bool positive = info->IsPositive();
        out.selfOnly = !explicitUnit && !out.dest;

        // Summons, before IsNotForCombat turns the rest of them away.
        if (info->IsPassive())
            return false;
        if (info->HasEffect(SPELL_EFFECT_SUMMON_PET))
        {
            out.kind = Kind::Pet;
            out.selfOnly = true;
            return true;
        }
        if (ClassifySummon(info, out))
            return true;

        if (IsNotForCombat(info))
            return false;

        bool directDamage = false, periodicDamage = false, area = false;
        bool heal = false, hot = false, absorb = false;
        bool control = false, controlArea = false, auraArea = false;
        float auraRadius = 0.0f;
        for (SpellEffectInfo const& eff : info->Effects)
        {
            if (!eff.Effect)
                continue;
            if (IsAuraEffect(eff.Effect))
            {
                bool cc = eff.ApplyAuraName == SPELL_AURA_MOD_STUN || eff.ApplyAuraName == SPELL_AURA_MOD_FEAR
                    || eff.ApplyAuraName == SPELL_AURA_MOD_ROOT || eff.ApplyAuraName == SPELL_AURA_MOD_CONFUSE
                    || eff.ApplyAuraName == SPELL_AURA_MOD_SILENCE || eff.ApplyAuraName == SPELL_AURA_MOD_PACIFY_SILENCE;
                control = control || cc;
                if (eff.IsTargetingArea())
                {
                    auraArea = true;
                    controlArea = controlArea || cc;
                    auraRadius = std::max(auraRadius, eff.CalcRadius(bot));
                }
            }
            if (IsDamageEffect(eff.Effect))
                directDamage = true;
            if (IsAuraEffect(eff.Effect) && IsPeriodicDamageAura(eff.ApplyAuraName))
                periodicDamage = true;
            if (IsHealEffect(eff.Effect))
                heal = true;
            if (IsAuraEffect(eff.Effect) && eff.ApplyAuraName == SPELL_AURA_PERIODIC_HEAL)
                hot = true;
            if (IsAuraEffect(eff.Effect) && eff.ApplyAuraName == SPELL_AURA_SCHOOL_ABSORB)
                absorb = true;
            if (eff.IsTargetingArea() && (IsDamageEffect(eff.Effect) || IsHealEffect(eff.Effect)
                || (IsAuraEffect(eff.Effect) && IsPeriodicDamageAura(eff.ApplyAuraName))))
            {
                area = true;
                out.radius = std::max(out.radius, eff.CalcRadius(bot));
            }
        }
        out.aroundSelf = area && !out.dest && !explicitUnit;
        out.selfOnly = !explicitUnit && !out.dest;

        if (info->HasEffect(SPELL_EFFECT_INTERRUPT_CAST))
        {
            out.kind = Kind::Interrupt;
            return true;
        }
        if (info->HasEffect(SPELL_EFFECT_ATTACK_ME) || info->HasAura(SPELL_AURA_MOD_TAUNT))
        {
            out.kind = Kind::Taunt;
            return true;
        }

        if (info->HasAura(SPELL_AURA_MOD_SHAPESHIFT))
        {
            for (SpellEffectInfo const& eff : info->Effects)
                if (IsAuraEffect(eff.Effect) && eff.ApplyAuraName == SPELL_AURA_MOD_SHAPESHIFT)
                    out.form = uint32(eff.MiscValue);
            if (!IsCombatForm(out.form))
                return false;
            out.kind = Kind::Form;
            return true;
        }

        if (positive && (heal || hot || absorb))
        {
            out.estimate = EstimateHealing(bot, info);
            out.kind = heal ? Kind::Heal : (hot ? Kind::Hot : Kind::Shield);
            // a shield that only goes on the caster is a defensive cooldown
            if (out.kind == Kind::Shield && out.selfOnly && Cooldown(info) >= COOLDOWN_MIN)
                out.kind = Kind::Defensive;
            return true;
        }

        // Roots, fears and stuns on everything around the caster (Frost Nova,
        // Psychic Scream): a way out when enemies close in, whatever small
        // damage rides along.
        if (!positive && controlArea && !out.dest && !explicitUnit
            && HasAnyAura(info, { SPELL_AURA_MOD_ROOT, SPELL_AURA_MOD_FEAR, SPELL_AURA_MOD_STUN }))
        {
            out.kind = Kind::Escape;
            out.aroundSelf = true;
            out.radius = std::max(out.radius, auraRadius);
            return true;
        }

        if (!positive && (directDamage || periodicDamage))
        {
            out.estimate = EstimateDamage(bot, info);
            if (area)
                out.kind = Kind::Aoe;
            else if (periodicDamage && !info->IsChanneled())
                out.kind = Kind::Dot;
            else
                out.kind = Kind::Nuke;
            return true;
        }

        if (!positive)
        {
            bool allAuras = true;
            for (SpellEffectInfo const& eff : info->Effects)
                if (eff.Effect && !IsAuraEffect(eff.Effect))
                    allAuras = false;
            int32 duration = info->GetDuration();
            uint64 mechanics = info->GetAllEffectsMechanicMask();
            if (info->Mechanic)
                mechanics |= 1ULL << info->Mechanic;
            constexpr uint64 longControl = (1ULL << MECHANIC_POLYMORPH) | (1ULL << MECHANIC_SLEEP)
                | (1ULL << MECHANIC_BANISH) | (1ULL << MECHANIC_SHACKLE) | (1ULL << MECHANIC_SAPPED);
            constexpr uint64 stops = (1ULL << MECHANIC_STUN) | (1ULL << MECHANIC_SILENCE) | (1ULL << MECHANIC_INTERRUPT);

            if (explicitUnit && control)
            {
                if ((mechanics & longControl) || (info->HasAura(SPELL_AURA_MOD_CONFUSE) && duration >= int32(CONTROL_MIN_DURATION)))
                {
                    out.kind = Kind::Control;
                    return true;
                }
                if ((mechanics & stops) || HasAnyAura(info, { SPELL_AURA_MOD_STUN, SPELL_AURA_MOD_SILENCE,
                                                              SPELL_AURA_MOD_PACIFY_SILENCE }))
                {
                    out.kind = Kind::Stun;
                    return true;
                }
                if (info->HasAura(SPELL_AURA_MOD_FEAR))
                {
                    out.kind = Kind::Fear;
                    return true;
                }
                return false;
            }

            // An aura that weakens the enemy and does nothing else: no crowd
            // control, no snare, no mind control.
            if (allAuras && !control && duration != 0
                && !HasAnyAura(info, { SPELL_AURA_MOD_DECREASE_SPEED, SPELL_AURA_MOD_CHARM, SPELL_AURA_MOD_POSSESS }))
            {
                if (explicitUnit)
                {
                    out.kind = Kind::Debuff;
                    return true;
                }
                if (auraArea && !out.dest)
                {
                    out.kind = Kind::Debuff;
                    out.aroundSelf = true;
                    out.radius = std::max(out.radius, auraRadius);
                    return true;
                }
            }
            return false;
        }

        // From here on: helpful auras the caster puts on itself or its party.
        bool allAuras = true;
        for (SpellEffectInfo const& eff : info->Effects)
            if (eff.Effect && !IsAuraEffect(eff.Effect))
                allAuras = false;
        if (!allAuras)
            return false;

        uint32 cooldown = Cooldown(info);
        int32 duration = info->GetDuration();
        if (cooldown >= COOLDOWN_MIN)
        {
            if (HasAnyAura(info, { SPELL_AURA_MOD_DAMAGE_PERCENT_TAKEN, SPELL_AURA_SCHOOL_ABSORB,
                                   SPELL_AURA_SCHOOL_IMMUNITY, SPELL_AURA_DAMAGE_IMMUNITY,
                                   SPELL_AURA_MOD_PARRY_PERCENT, SPELL_AURA_MOD_DODGE_PERCENT,
                                   SPELL_AURA_MOD_INCREASE_HEALTH, SPELL_AURA_MOD_INCREASE_HEALTH_PERCENT,
                                   SPELL_AURA_SPLIT_DAMAGE_PCT, SPELL_AURA_REFLECT_SPELLS,
                                   SPELL_AURA_MOD_RESISTANCE_PCT }))
            {
                out.kind = Kind::Defensive;
                return true;
            }
            if (HasAnyAura(info, { SPELL_AURA_MOD_DAMAGE_PERCENT_DONE, SPELL_AURA_MOD_MELEE_HASTE,
                                   SPELL_AURA_MOD_MELEE_RANGED_HASTE, SPELL_AURA_HASTE_SPELLS,
                                   SPELL_AURA_MOD_CASTING_SPEED_NOT_STACK, SPELL_AURA_MOD_SPELL_CRIT_CHANCE,
                                   SPELL_AURA_MOD_CRIT_PCT, SPELL_AURA_MOD_ATTACK_POWER_PCT,
                                   SPELL_AURA_MOD_ATTACK_POWER, SPELL_AURA_MOD_TOTAL_STAT_PERCENTAGE }))
            {
                out.kind = Kind::Burst;
                return true;
            }
            return false;
        }

        if (duration < 0 || uint32(duration) >= BUFF_MIN_DURATION)
        {
            out.kind = Kind::Buff;
            return true;
        }
        return false;
    }

    // Every rank-carrying spell the Hero owns through the module: library
    // abilities (stock, elemental variants and the Hero line) and talent
    // spells. Professions, mounts and the like are left alone.
    Kit BuildKit(Player* bot)
    {
        Kit kit;
        CharState* st = sClasslessMgr->FindState(bot);
        if (!st)
            return kit;
        kit.runes = st->runes;

        std::set<uint32> talentSpells;
        for (auto const& [talentId, rank] : st->talents)
            if (TalentPoolEntry const* t = sClasslessMgr->GetTalent(talentId))
                for (uint8 r = 0; r < rank && r < t->rankSpells.size(); ++r)
                    if (t->rankSpells[r])
                        talentSpells.insert(t->rankSpells[r]);

        // the highest rank of each line the bot has active
        std::map<uint32, uint32> best;   // first rank -> highest active rank
        for (auto const& [spellId, spell] : bot->GetSpellMap())
        {
            if (spell->State == PLAYERSPELL_REMOVED || !spell->Active)
                continue;
            if (!sClasslessMgr->FindAbilityBySpell(spellId) && !talentSpells.count(spellId))
                continue;
            uint32 first = sSpellMgr->GetFirstSpellInChain(spellId);
            auto itr = best.find(first);
            if (itr == best.end() || sSpellMgr->GetSpellRank(spellId) > sSpellMgr->GetSpellRank(itr->second))
                best[first] = spellId;
        }

        uint32 heals = 0, damage = 0, meleeDamage = 0, rangedDamage = 0;
        bool taunt = false;
        for (auto const& [first, spellId] : best)
        {
            SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId);
            if (!info)
                continue;
            KitSpell ks;
            if (!Classify(bot, info, ks))
                continue;
            // a rune spell on a Hero without a rune block would read a null block
            if (info->PowerType == POWER_RUNE && !kit.runes)
                continue;
            kit.spells.push_back(ks);

            switch (ks.kind)
            {
                case Kind::Heal: case Kind::Hot: case Kind::Shield:
                    if (!ks.selfOnly || ks.aroundSelf)
                        ++heals;
                    break;
                case Kind::Nuke: case Kind::Dot: case Kind::Aoe:
                    ++damage;
                    ++(ks.melee ? meleeDamage : rangedDamage);
                    break;
                case Kind::Taunt:
                    taunt = true;
                    break;
                default:
                    break;
            }
        }

        // The role the kit points to. A healer has a real share of heals; a
        // tank has a taunt and fights up close; everyone else stands where
        // most of their damage reaches from.
        if (heals >= 3 && heals * 2 >= damage)
            kit.role = ClasslessBots::ROLE_HEAL;
        else if (taunt && meleeDamage >= rangedDamage)
            kit.role = ClasslessBots::ROLE_TANK;
        else if (rangedDamage > meleeDamage)
            kit.role = ClasslessBots::ROLE_RANGED;
        else
            kit.role = ClasslessBots::ROLE_MELEE;
        return kit;
    }

    // ---------------------------------------------------------------------
    // Can the bot cast this spell on this target right now?
    //
    // PlayerbotAI::CanCastSpell checks the spell with its power and reagent
    // cost ignored, and calls a spell that is out of range or needs another
    // form castable, so all of that is checked here first. A Hero pays from
    // whichever pool the spell names, mana, rage, energy, runic power or
    // runes, so the pool is the spell's, never the bar on display.
    // ---------------------------------------------------------------------
    bool CanPay(Player* bot, Kit const& kit, SpellInfo const* info)
    {
        if (info->PowerType == POWER_RUNE)
        {
            if (!kit.runes)
                return false;
            Spell probe(bot, info, TRIGGERED_NONE);
            return probe.CheckRuneCost(info->RuneCostID) == SPELL_CAST_OK;
        }
        if (info->PowerType == POWER_HEALTH)
            return true;
        if (info->PowerType >= MAX_POWERS)
            return false;
        int32 cost = info->CalcPowerCost(bot, SpellSchoolMask(info->SchoolMask));
        return cost <= 0 || int32(bot->GetPower(Powers(info->PowerType))) >= cost;
    }

    bool HasReagents(Player* bot, SpellInfo const* info)
    {
        for (uint8 i = 0; i < MAX_SPELL_REAGENTS; ++i)
            if (info->Reagent[i] > 0 && info->ReagentCount[i] > 0
                && !bot->HasItemCount(uint32(info->Reagent[i]), info->ReagentCount[i]))
                return false;
        return true;
    }

    bool InRange(Player* bot, Unit* target, KitSpell const& ks)
    {
        if (!target || target == bot)
            return true;
        if (!bot->IsWithinLOSInMap(target))
            return false;
        if (ks.melee)
            return bot->IsWithinMeleeRange(target);
        bool friendly = !bot->IsHostileTo(target);
        float max = ks.info->GetMaxRange(friendly, bot);
        float min = ks.info->GetMinRange(friendly);
        if (max > 0.0f && !bot->IsWithinDistInMap(target, max))
            return false;
        if (min > 0.0f && bot->IsWithinDistInMap(target, min))
            return false;
        return true;
    }

    // `checkRange` false asks "castable if the bot were close enough", which
    // is how the approach action finds a spell worth walking in for.
    bool Ready(PlayerbotAI* ai, Player* bot, Kit const& kit, KitSpell const& ks, Unit* target, bool checkRange = true)
    {
        SpellInfo const* info = ks.info;
        if (info->CheckShapeshift(bot->GetShapeshiftForm()) != SPELL_CAST_OK)
            return false;
        if (!CanPay(bot, kit, info) || !HasReagents(bot, info))
            return false;
        if (info->NeedsComboPoints())
        {
            uint8 cp = target ? bot->GetComboPoints(target) : 0;
            bool execute = target && target->GetHealthPct() < FINISHER_EXECUTE;
            if (cp == 0 || (cp < FINISHER_POINTS && !execute))
                return false;
        }
        if (ks.dest)
        {
            if (!target)
                return false;
            if (checkRange && !InRange(bot, target, ks))
                return false;
            return ai->CanCastSpell(ks.id, target->GetPositionX(), target->GetPositionY(), target->GetPositionZ());
        }
        Unit* on = ks.selfOnly ? bot : target;
        if (checkRange && !InRange(bot, on, ks))
            return false;
        // CanCastSpell itself calls an out-of-range spell castable
        return ai->CanCastSpell(ks.id, on);
    }

    bool Cast(PlayerbotAI* ai, Player* bot, KitSpell const& ks, Unit* target)
    {
        if (ks.dest && target)
            return ai->CastSpell(ks.id, target->GetPositionX(), target->GetPositionY(), target->GetPositionZ());
        return ai->CastSpell(ks.id, ks.selfOnly ? bot : target);
    }

    uint32 EnemiesNear(PlayerbotAI* ai, Player* bot, WorldObject const* center, float radius)
    {
        uint32 n = 0;
        GuidVector attackers = ai->GetAiObjectContext()->GetValue<GuidVector>("attackers")->Get();
        for (ObjectGuid const& guid : attackers)
            if (Unit* u = ObjectAccessor::GetUnit(*bot, guid))
                if (u->IsAlive() && u->IsWithinDistInMap(center, radius))
                    ++n;
        return n;
    }

    // The party member (or the bot) with the lowest health share that the
    // bot can reach, or nullptr when everyone is above `below`.
    Unit* LowestFriend(Player* bot, float below, float range)
    {
        Unit* lowest = nullptr;
        float lowestPct = below;
        auto consider = [&](Unit* u)
        {
            if (!u || !u->IsAlive() || !u->IsInWorld() || u->GetMapId() != bot->GetMapId())
                return;
            if (u != bot && (!bot->IsWithinDistInMap(u, range) || !bot->IsWithinLOSInMap(u)))
                return;
            float pct = u->GetHealthPct();
            if (pct < lowestPct)
            {
                lowestPct = pct;
                lowest = u;
            }
        };
        consider(bot);
        if (Group* group = bot->GetGroup())
            for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                if (Player* member = ref->GetSource())
                    if (member != bot)
                        consider(member);
        return lowest;
    }

    bool IsStrongTarget(Unit* target)
    {
        if (!target)
            return false;
        if (target->IsPlayer())
            return true;
        if (Creature* c = target->ToCreature())
            return c->isElite() || c->isWorldBoss() || c->IsDungeonBoss();
        return false;
    }

    // Does `target` already carry, from this bot, an aura this one would
    // replace? Seals, auras, aspects, presences and curses are one of a kind
    // by spell type; blessings and the like by their spell group. Without
    // this a bot that owns two of them swaps one for the other forever.
    bool HasExclusiveSibling(Player* bot, Unit* target, SpellInfo const* info)
    {
        SpellSpecificType spec = info->GetSpellSpecific();
        for (auto const& [auraId, app] : target->GetAppliedAuras())
        {
            Aura const* aura = app->GetBase();
            if (!aura || aura->GetCasterGUID() != bot->GetGUID())
                continue;
            SpellInfo const* other = aura->GetSpellInfo();
            if (spec != SPELL_SPECIFIC_NORMAL && other->GetSpellSpecific() == spec)
                return true;
            if (other->Id != info->Id
                && sSpellMgr->CheckSpellGroupStackRules(info, other) != SPELL_GROUP_STACK_RULE_DEFAULT)
                return true;
        }
        return false;
    }

    // Already held by somebody's crowd control.
    bool IsControlled(Unit* target)
    {
        return target->HasAuraType(SPELL_AURA_MOD_CONFUSE) || target->HasAuraType(SPELL_AURA_MOD_STUN)
            || target->HasAuraType(SPELL_AURA_MOD_FEAR) || target->HasAuraType(SPELL_AURA_MOD_PACIFY_SILENCE);
    }

    // Already wearing this spell, any rank, from anyone.
    bool HasAnyRank(Unit* target, SpellInfo const* info)
    {
        uint32 first = sSpellMgr->GetFirstSpellInChain(info->Id);
        for (auto const& [auraId, app] : target->GetAppliedAuras())
            if (sSpellMgr->GetFirstSpellInChain(auraId) == first)
                return true;
        return false;
    }

    // The party members (and the bot) the bot can reach with a spell.
    std::vector<Unit*> Friends(Player* bot, float range)
    {
        std::vector<Unit*> out = { bot };
        if (Group* group = bot->GetGroup())
            for (GroupReference* ref = group->GetFirstMember(); ref; ref = ref->next())
                if (Player* member = ref->GetSource())
                    if (member != bot && member->IsAlive() && member->IsInWorld() && member->GetMapId() == bot->GetMapId()
                        && bot->IsWithinDistInMap(member, range) && bot->IsWithinLOSInMap(member))
                        out.push_back(member);
        return out;
    }

    // ---------------------------------------------------------------------
    // The kit as a playerbots value, rebuilt every few seconds so a newly
    // bought or rolled ability is picked up without a relog.
    // ---------------------------------------------------------------------
    class KitValue : public CalculatedValue<KitPtr>
    {
    public:
        explicit KitValue(PlayerbotAI* botAI) : CalculatedValue<KitPtr>(botAI, V_KIT, KIT_REBUILD_MS) { }

    protected:
        KitPtr Calculate() override { return std::make_shared<Kit const>(BuildKit(bot)); }
    };

    // ---------------------------------------------------------------------
    // Actions. Each one picks the best owned spell for its job at this moment
    // and says it is useless when there is none, so all of them sit in the
    // strategy's default list and the engine runs whichever ranks highest.
    // ---------------------------------------------------------------------
    class KitAction : public Action
    {
    public:
        KitAction(PlayerbotAI* botAI, std::string const name) : Action(botAI, name) { }

        bool isUseful() override
        {
            _pick = nullptr;
            _target = nullptr;
            if (bot->IsNonMeleeSpellCast(false, false, true))
                return false;
            _kit = AI_VALUE(KitPtr, V_KIT);
            if (!_kit)
                return false;
            Pick();
            return _pick != nullptr;
        }

        bool isPossible() override { return _pick != nullptr; }

        bool Execute(Event /*event*/) override
        {
            if (!_pick)
                return false;
            return Cast(botAI, bot, *_pick, _target);
        }

    protected:
        virtual void Pick() = 0;

        Unit* Enemy() { return AI_VALUE(Unit*, "current target"); }

        bool Usable(KitSpell const& ks, Unit* target) { return Ready(botAI, bot, *_kit, ks, target); }

        void Choose(KitSpell const& ks, Unit* target)
        {
            _pick = &ks;
            _target = target;
        }

        KitPtr _kit;
        KitSpell const* _pick = nullptr;
        Unit* _target = nullptr;
    };

    class NukeAction : public KitAction
    {
    public:
        explicit NukeAction(PlayerbotAI* botAI) : KitAction(botAI, "classless nuke") { }

    protected:
        void Pick() override
        {
            Unit* enemy = Enemy();
            if (!enemy || !enemy->IsAlive())
                return;
            float bestScore = 0.0f;
            for (KitSpell const& ks : _kit->spells)
            {
                if (ks.kind != Kind::Nuke || !Usable(ks, enemy))
                    continue;
                // damage per second of the bot's time
                float castMs = float(std::max<uint32>(ks.info->CalcCastTime(bot), 1500));
                if (ks.info->IsChanneled() && ks.info->GetDuration() > 0)
                    castMs = float(std::max(ks.info->GetDuration(), 1500));
                float score = ks.estimate * 1000.0f / castMs;
                if (score > bestScore || !_pick)
                {
                    bestScore = score;
                    Choose(ks, enemy);
                }
            }
        }
    };

    class DotAction : public KitAction
    {
    public:
        explicit DotAction(PlayerbotAI* botAI) : KitAction(botAI, "classless dot") { }

    protected:
        void Pick() override
        {
            Unit* enemy = Enemy();
            if (!enemy || !enemy->IsAlive() || enemy->GetHealthPct() < DOT_TARGET_ABOVE)
                return;
            float best = 0.0f;
            for (KitSpell const& ks : _kit->spells)
            {
                if (ks.kind != Kind::Dot || enemy->HasAura(ks.id, bot->GetGUID()) || !Usable(ks, enemy))
                    continue;
                if (ks.estimate > best || !_pick)
                {
                    best = ks.estimate;
                    Choose(ks, enemy);
                }
            }
        }
    };

    class AoeAction : public KitAction
    {
    public:
        explicit AoeAction(PlayerbotAI* botAI) : KitAction(botAI, "classless aoe") { }

    protected:
        void Pick() override
        {
            Unit* enemy = Enemy();
            if (!enemy || !enemy->IsAlive())
                return;
            float best = 0.0f;
            for (KitSpell const& ks : _kit->spells)
            {
                if (ks.kind != Kind::Aoe)
                    continue;
                WorldObject const* center = ks.aroundSelf ? static_cast<WorldObject const*>(bot) : enemy;
                if (EnemiesNear(botAI, bot, center, std::max(ks.radius, 5.0f)) < AOE_MIN_ENEMIES)
                    continue;
                if (!Usable(ks, enemy))
                    continue;
                if (ks.estimate > best || !_pick)
                {
                    best = ks.estimate;
                    Choose(ks, enemy);
                }
            }
        }
    };

    class HealAction : public KitAction
    {
    public:
        HealAction(PlayerbotAI* botAI, std::string const name, bool inCombat) : KitAction(botAI, name), _inCombat(inCombat) { }

    protected:
        void Pick() override
        {
            bool healer = _kit->role == ClasslessBots::ROLE_HEAL;
            float range = botAI->GetRange("heal");

            // who needs it: a healer looks after everyone, anyone else after
            // themselves and a party member in real trouble
            Unit* target = nullptr;
            if (!_inCombat)
                target = LowestFriend(bot, OUT_OF_COMBAT_HEAL, range);
            else if (healer)
                target = LowestFriend(bot, HEALER_HOT_BELOW, range);
            else
            {
                target = LowestFriend(bot, OTHERS_HEAL_BELOW, range);
                if (!target && bot->GetHealthPct() < SELF_HEAL_BELOW)
                    target = bot;
            }
            if (!target)
                return;

            float pct = target->GetHealthPct();
            float deficit = float(target->GetMaxHealth() - target->GetHealth());
            bool big = pct < BIG_HEAL_BELOW;
            float bestScore = 0.0f;
            for (KitSpell const& ks : _kit->spells)
            {
                if (ks.kind != Kind::Heal && ks.kind != Kind::Hot && ks.kind != Kind::Shield)
                    continue;
                if (ks.selfOnly && !ks.aroundSelf && target != bot)
                    continue;
                if (ks.aroundSelf && !bot->IsWithinDistInMap(target, std::max(ks.radius, 5.0f)))
                    continue;
                if (ks.kind == Kind::Hot && target->HasAura(ks.id, bot->GetGUID()))
                    continue;
                if (ks.kind == Kind::Shield && (target->HasAura(ks.id) || !_inCombat
                    || pct >= (healer ? HEALER_SHIELD_BELOW : OTHERS_HEAL_BELOW)))
                    continue;
                if (ks.kind == Kind::Heal && healer && _inCombat && pct >= HEALER_HEAL_BELOW)
                    continue;
                Unit* on = (ks.selfOnly || ks.aroundSelf) ? bot : target;
                if (!Usable(ks, on))
                    continue;

                // strongest when it is urgent, otherwise the one that does the
                // job for the least
                float score;
                if (big)
                    score = ks.estimate;
                else
                {
                    int32 cost = std::max(1, ks.info->CalcPowerCost(bot, SpellSchoolMask(ks.info->SchoolMask)));
                    score = std::min(ks.estimate, deficit) / float(cost);
                }
                if (score > bestScore || !_pick)
                {
                    bestScore = score;
                    Choose(ks, on);
                }
            }
        }

    private:
        bool _inCombat;
    };

    class InterruptAction : public KitAction
    {
    public:
        explicit InterruptAction(PlayerbotAI* botAI) : KitAction(botAI, "classless interrupt") { }

    protected:
        void Pick() override
        {
            Unit* enemy = Enemy();
            if (!enemy || !enemy->IsAlive())
                return;
            Spell* casting = enemy->GetCurrentSpell(CURRENT_GENERIC_SPELL);
            if (!casting)
                casting = enemy->GetCurrentSpell(CURRENT_CHANNELED_SPELL);
            if (!casting || !(casting->GetSpellInfo()->InterruptFlags & SPELL_INTERRUPT_FLAG_INTERRUPT))
                return;
            for (KitSpell const& ks : _kit->spells)
                if (ks.kind == Kind::Interrupt && Usable(ks, enemy))
                {
                    Choose(ks, enemy);
                    return;
                }
            // no interrupt ready: a stun or silence stops the cast as well
            for (KitSpell const& ks : _kit->spells)
                if (ks.kind == Kind::Stun && Usable(ks, enemy))
                {
                    Choose(ks, enemy);
                    return;
                }
        }
    };

    class TauntAction : public KitAction
    {
    public:
        explicit TauntAction(PlayerbotAI* botAI) : KitAction(botAI, "classless taunt") { }

    protected:
        void Pick() override
        {
            if (_kit->role != ClasslessBots::ROLE_TANK)
                return;
            Unit* enemy = Enemy();
            if (!enemy || !enemy->IsAlive())
                return;
            Unit* victim = enemy->GetVictim();
            if (!victim || victim == bot)
                return;
            Player* victimPlayer = victim->ToPlayer();
            if (!victimPlayer || !bot->IsInSameGroupWith(victimPlayer))
                return;
            for (KitSpell const& ks : _kit->spells)
                if (ks.kind == Kind::Taunt && Usable(ks, enemy))
                {
                    Choose(ks, enemy);
                    return;
                }
        }
    };

    class DefensiveAction : public KitAction
    {
    public:
        explicit DefensiveAction(PlayerbotAI* botAI) : KitAction(botAI, "classless defensive") { }

    protected:
        void Pick() override
        {
            if (bot->GetHealthPct() >= DEFENSIVE_BELOW)
                return;
            for (KitSpell const& ks : _kit->spells)
                if (ks.kind == Kind::Defensive && !bot->HasAura(ks.id) && Usable(ks, bot))
                {
                    Choose(ks, bot);
                    return;
                }
        }
    };

    class BurstAction : public KitAction
    {
    public:
        explicit BurstAction(PlayerbotAI* botAI) : KitAction(botAI, "classless burst") { }

    protected:
        void Pick() override
        {
            Unit* enemy = Enemy();
            if (!IsStrongTarget(enemy) || enemy->GetHealthPct() < BURST_TARGET_ABOVE)
                return;
            for (KitSpell const& ks : _kit->spells)
                if (ks.kind == Kind::Burst && !bot->HasAura(ks.id) && Usable(ks, bot))
                {
                    Choose(ks, bot);
                    return;
                }
        }
    };

    // Long buffs. In combat only on the bot itself, so a fight is not spent
    // buffing; out of combat on everyone in the party the spell can reach.
    class BuffAction : public KitAction
    {
    public:
        BuffAction(PlayerbotAI* botAI, std::string const name, bool party) : KitAction(botAI, name), _party(party) { }

    protected:
        void Pick() override
        {
            std::vector<Unit*> friends = _party ? Friends(bot, botAI->GetRange("spell")) : std::vector<Unit*>{ bot };
            for (Unit* target : friends)
                for (KitSpell const& ks : _kit->spells)
                {
                    if (ks.kind != Kind::Buff || (target != bot && ks.selfOnly))
                        continue;
                    if (HasAnyRank(target, ks.info) || HasExclusiveSibling(bot, target, ks.info))
                        continue;
                    if (Usable(ks, target))
                    {
                        Choose(ks, target);
                        return;
                    }
                }
        }

    private:
        bool _party;
    };

    // Weakening auras (Sunder Armor, Faerie Fire, Hunter's Mark, a shout that
    // lowers attack power) are worth a global cooldown on an enemy that will
    // live a while: a strong one, or anything still above half health.
    class DebuffAction : public KitAction
    {
    public:
        explicit DebuffAction(PlayerbotAI* botAI) : KitAction(botAI, "classless debuff") { }

    protected:
        void Pick() override
        {
            Unit* enemy = Enemy();
            if (!enemy || !enemy->IsAlive())
                return;
            if (!IsStrongTarget(enemy) && enemy->GetHealthPct() < DEBUFF_TARGET_ABOVE)
                return;
            for (KitSpell const& ks : _kit->spells)
            {
                if (ks.kind != Kind::Debuff || enemy->HasAura(ks.id) || HasExclusiveSibling(bot, enemy, ks.info))
                    continue;
                if (ks.aroundSelf && !bot->IsWithinDistInMap(enemy, std::max(ks.radius, 5.0f)))
                    continue;
                if (Usable(ks, enemy))
                {
                    Choose(ks, enemy);
                    return;
                }
            }
        }
    };

    // Long crowd control on an add. Playerbots' own `cc target` picks it the
    // way it does for a mage's Polymorph: the enemy marked with the crowd
    // control raid icon first, otherwise one no tank is holding that is not
    // the current target and not in the middle of area damage.
    class ControlAction : public KitAction
    {
    public:
        explicit ControlAction(PlayerbotAI* botAI) : KitAction(botAI, "classless control") { }

    protected:
        void Pick() override
        {
            for (KitSpell const& ks : _kit->spells)
            {
                if (ks.kind != Kind::Control)
                    continue;
                Unit* target = AI_VALUE2(Unit*, "cc target", ks.info->SpellName[0]);
                if (!target || !target->IsAlive() || IsControlled(target))
                    continue;
                if (Usable(ks, target))
                {
                    Choose(ks, target);
                    return;
                }
            }
            // A fear sends the enemy running, possibly into the next pack, so
            // it goes only on the enemy the owner marked for crowd control.
            Unit* marked = AI_VALUE(Unit*, "rti cc target");
            if (!marked || !marked->IsAlive() || IsControlled(marked))
                return;
            for (KitSpell const& ks : _kit->spells)
                if (ks.kind == Kind::Fear && Usable(ks, marked))
                {
                    Choose(ks, marked);
                    return;
                }
        }
    };

    // A ranged Hero or healer with enemies hitting it in melee roots or fears
    // them off, once its health is going.
    class EscapeAction : public KitAction
    {
    public:
        explicit EscapeAction(PlayerbotAI* botAI) : KitAction(botAI, "classless escape") { }

    protected:
        void Pick() override
        {
            if (_kit->role == ClasslessBots::ROLE_TANK || _kit->role == ClasslessBots::ROLE_MELEE)
                return;
            if (bot->GetHealthPct() >= ESCAPE_BELOW)
                return;
            for (KitSpell const& ks : _kit->spells)
            {
                if (ks.kind != Kind::Escape)
                    continue;
                if (EnemiesNear(botAI, bot, bot, std::max(ks.radius, 5.0f)) == 0)
                    continue;
                if (Usable(ks, bot))
                {
                    Choose(ks, bot);
                    return;
                }
            }

            // Nothing that clears the area: fear or stun the one enemy
            // hitting the bot. Sending it running is the point here.
            Unit* attacker = nullptr;
            for (ObjectGuid const& guid : AI_VALUE(GuidVector, "attackers"))
                if (Unit* u = ObjectAccessor::GetUnit(*bot, guid))
                    if (u->IsAlive() && u->GetVictim() == bot && bot->IsWithinMeleeRange(u) && !IsControlled(u))
                    {
                        attacker = u;
                        break;
                    }
            if (!attacker)
                return;
            for (Kind kind : { Kind::Fear, Kind::Stun })
                for (KitSpell const& ks : _kit->spells)
                    if (ks.kind == kind && Usable(ks, attacker))
                    {
                        Choose(ks, attacker);
                        return;
                    }
        }
    };

    // Totems, one per element. A totem already down within reach stays,
    // whichever one it is; an empty slot, or one left behind, gets a new
    // one. With an enemy within a totem's reach the attacking kind is
    // preferred, otherwise the one that helps the party; the higher-level
    // spell breaks a tie.
    class TotemAction : public KitAction
    {
    public:
        explicit TotemAction(PlayerbotAI* botAI) : KitAction(botAI, "classless totem") { }

    protected:
        void Pick() override
        {
            Unit* enemy = Enemy();
            if (enemy && !enemy->IsAlive())
                enemy = nullptr;
            for (uint8 slot = SUMMON_SLOT_TOTEM_FIRE; slot <= SUMMON_SLOT_TOTEM_AIR; ++slot)
            {
                ObjectGuid placedGuid = bot->m_SummonSlot[slot];
                Creature* placed = placedGuid ? ObjectAccessor::GetCreature(*bot, placedGuid) : nullptr;
                if (placed && placed->IsAlive() && bot->IsWithinDistInMap(placed, TOTEM_KEEP_DISTANCE))
                    continue;

                KitSpell const* best = nullptr;
                bool bestFits = false;
                for (KitSpell const& ks : _kit->spells)
                {
                    if (ks.kind != Kind::Totem || ks.slot != slot)
                        continue;
                    bool reaches = enemy && bot->IsWithinDistInMap(enemy, std::max(ks.radius, MELEE_RANGE));
                    bool fits = ks.offensive == reaches;
                    if (best && (bestFits > fits || (bestFits == fits && best->info->SpellLevel >= ks.info->SpellLevel)))
                        continue;
                    if (!Usable(ks, bot))
                        continue;
                    best = &ks;
                    bestFits = fits;
                }
                if (best)
                {
                    Choose(*best, bot);
                    return;
                }
            }
        }
    };

    // A temporary fighter is worth calling for a strong enemy or a crowd,
    // and not again while the last one is still out.
    class GuardianAction : public KitAction
    {
    public:
        explicit GuardianAction(PlayerbotAI* botAI) : KitAction(botAI, "classless guardian") { }

    protected:
        void Pick() override
        {
            Unit* enemy = Enemy();
            if (!enemy || !enemy->IsAlive())
                return;
            if (!IsStrongTarget(enemy)
                && EnemiesNear(botAI, bot, bot, botAI->GetRange("spell")) < GUARDIAN_MIN_ENEMIES)
                return;
            for (KitSpell const& ks : _kit->spells)
                if (ks.kind == Kind::Guardian && !HasOut(ks.entry) && Usable(ks, enemy))
                {
                    Choose(ks, enemy);
                    return;
                }
        }

    private:
        bool HasOut(uint32 entry)
        {
            for (Unit* u : bot->m_Controlled)
                if (u && u->GetEntry() == entry && u->IsAlive())
                    return true;
            return false;
        }
    };

    // The permanent pet, whenever there is none out. The summon from the
    // highest-level spell wins, so a Hero with both Summon Imp and Summon
    // Felhunter keeps the felhunter; a hunter without a tamed beast fails
    // Call Pet's own check and the next summon is tried.
    class PetAction : public KitAction
    {
    public:
        PetAction(PlayerbotAI* botAI, std::string const name) : KitAction(botAI, name) { }

    protected:
        void Pick() override
        {
            if (bot->GetPet() || bot->IsMounted() || bot->GetCharmGUID())
                return;
            KitSpell const* best = nullptr;
            for (KitSpell const& ks : _kit->spells)
                if (ks.kind == Kind::Pet && Usable(ks, bot) && (!best || ks.info->SpellLevel > best->info->SpellLevel))
                    best = &ks;
            if (best)
                Choose(*best, bot);
        }
    };

    // Playerbots walks a ranged bot to its configured spell distance. A Hero
    // whose damage reaches less far than that would stand there doing
    // nothing, so when no damage spell can be cast from here but one could be
    // from closer, this walks in to just inside that spell's range.
    class ApproachAction : public MovementAction
    {
    public:
        explicit ApproachAction(PlayerbotAI* botAI) : MovementAction(botAI, "classless approach") { }

        bool isUseful() override
        {
            _distance = 0.0f;
            if (botAI->HasStrategy("stay", botAI->GetState()) || bot->GetCurrentSpell(CURRENT_CHANNELED_SPELL))
                return false;
            KitPtr kit = AI_VALUE(KitPtr, V_KIT);
            Unit* enemy = AI_VALUE(Unit*, "current target");
            if (!kit || !enemy || !enemy->IsAlive())
                return false;
            float reach = 0.0f;
            for (KitSpell const& ks : kit->spells)
            {
                if (ks.kind != Kind::Nuke && ks.kind != Kind::Dot && ks.kind != Kind::Aoe)
                    continue;
                if (ks.melee || ks.aroundSelf)
                    continue;   // melee reach is playerbots' own job
                if (!Ready(botAI, bot, *kit, ks, enemy, false))
                    continue;
                if (InRange(bot, enemy, ks))
                    return false;   // something can be cast from here
                reach = std::max(reach, ks.info->GetMaxRange(false, bot));
            }
            if (reach <= 0.0f)
                return false;
            _distance = std::max(reach - APPROACH_MARGIN, MELEE_RANGE);
            return !bot->IsWithinCombatRange(enemy, _distance);
        }

        bool Execute(Event /*event*/) override
        {
            return ReachCombatTo(AI_VALUE(Unit*, "current target"), _distance);
        }

    private:
        float _distance = 0.0f;
    };

    // Stances and forms. A Hero who bought Mortal Strike needs Battle Stance
    // before it can be used, and a cat needs Cat Form: the bot stands in the
    // combat form that leaves the most of its kit usable, and only moves when
    // another form would unlock strictly more.
    class FormAction : public KitAction
    {
    public:
        explicit FormAction(PlayerbotAI* botAI) : KitAction(botAI, "classless form") { }

    protected:
        void Pick() override
        {
            if (getMSTime() - _lastSwitch < FORM_SWITCH_MS && _lastSwitch)
                return;
            uint32 current = bot->GetShapeshiftForm();
            uint32 here = UsableIn(current);
            KitSpell const* best = nullptr;
            uint32 bestCount = here;
            for (KitSpell const& ks : _kit->spells)
            {
                if (ks.kind != Kind::Form || ks.form == current)
                    continue;
                uint32 count = UsableIn(ks.form);
                if (count > bestCount && Usable(ks, bot))
                {
                    bestCount = count;
                    best = &ks;
                }
            }
            if (best)
                Choose(*best, bot);
        }

    public:
        bool Execute(Event event) override
        {
            bool done = KitAction::Execute(event);
            if (done)
                _lastSwitch = getMSTime();
            return done;
        }

    private:
        // How many of the kit's attacks and heals work in this form.
        uint32 UsableIn(uint32 form)
        {
            uint32 n = 0;
            for (KitSpell const& ks : _kit->spells)
                if (ks.kind != Kind::Form && ks.kind != Kind::Buff
                    && ks.info->CheckShapeshift(form) == SPELL_CAST_OK)
                    ++n;
            return n;
        }

        uint32 _lastSwitch = 0;
    };

    // ---------------------------------------------------------------------
    // Strategies
    // ---------------------------------------------------------------------

    // Playerbots' own spell and talent upkeep is written for real classes:
    // `maintenance` resets the talents and picks a spec of the chassis class,
    // and the talent commands do the same. On a Hero that would take apart a
    // build the module manages, so a Hero bot drops those actions. (A zero
    // multiplier is how the engine discards an action.)
    class KeepBuildMultiplier : public Multiplier
    {
    public:
        explicit KeepBuildMultiplier(PlayerbotAI* botAI) : Multiplier(botAI, "classless keep build") { }

        float GetValue(Action* action) override
        {
            static std::set<std::string> const blocked = {
                "maintenance", "auto maintenance on levelup", "talents", "auto talents",
            };
            return action && blocked.count(action->getName()) ? 0.0f : 1.0f;
        }
    };

    class ClasslessStrategy : public Strategy
    {
    public:
        explicit ClasslessStrategy(PlayerbotAI* botAI) : Strategy(botAI) { }
        std::string const getName() override { return S_CLASSLESS; }
        void InitMultipliers(std::vector<Multiplier*>& multipliers) override
        {
            multipliers.push_back(new KeepBuildMultiplier(botAI));
        }
        std::vector<NextAction> getDefaultActions() override
        {
            return {
                NextAction("classless defensive", ACTION_EMERGENCY - 2),
                NextAction("classless escape",    ACTION_EMERGENCY - 5),
                NextAction("classless interrupt", ACTION_INTERRUPT),
                NextAction("classless heal",      ACTION_CRITICAL_HEAL + 2),
                NextAction("classless form",      ACTION_HIGH + 8),
                NextAction("classless control",   ACTION_HIGH + 6),
                NextAction("classless taunt",     ACTION_HIGH + 5),
                NextAction("classless guardian",  ACTION_HIGH + 4),
                NextAction("classless pet",       ACTION_HIGH + 3),
                NextAction("classless totem",     ACTION_HIGH + 1),
                NextAction("classless buff",      ACTION_HIGH + 2),
                NextAction("classless burst",     ACTION_HIGH),
                NextAction("classless aoe",       ACTION_NORMAL + 5),
                NextAction("classless debuff",    ACTION_NORMAL + 4),
                NextAction("classless dot",       ACTION_NORMAL + 3),
                NextAction("classless nuke",      ACTION_NORMAL),
                NextAction("classless approach",  ACTION_NORMAL - 1),
            };
        }
    };

    class ClasslessNonCombatStrategy : public Strategy
    {
    public:
        explicit ClasslessNonCombatStrategy(PlayerbotAI* botAI) : Strategy(botAI) { }
        std::string const getName() override { return S_CLASSLESS_NC; }
        uint32 GetType() const override { return STRATEGY_TYPE_NONCOMBAT; }
        void InitMultipliers(std::vector<Multiplier*>& multipliers) override
        {
            multipliers.push_back(new KeepBuildMultiplier(botAI));
        }
        std::vector<NextAction> getDefaultActions() override
        {
            return {
                NextAction("classless nc pet",  ACTION_NORMAL + 6),
                NextAction("classless nc heal", ACTION_NORMAL + 5),
                NextAction("classless nc buff", ACTION_NORMAL + 2),
            };
        }
    };

    // The roles. Each carries the positioning and the type bits playerbots
    // reads to decide whether a bot is a tank, a healer, melee or ranged
    // (PlayerbotAI::IsTank and friends ask the strategies, not the class).
    // They are siblings: adding one takes the others off.
    template <class Base, uint32 Type>
    class RoleStrategy : public Base
    {
    public:
        RoleStrategy(PlayerbotAI* botAI, char const* name, char const* autoAttack)
            : Base(botAI), _name(name), _autoAttack(autoAttack) { }
        std::string const getName() override { return _name; }
        uint32 GetType() const override { return Type; }
        std::vector<NextAction> getDefaultActions() override { return { NextAction(_autoAttack, ACTION_DEFAULT) }; }

    private:
        char const* _name;
        char const* _autoAttack;
    };

    using TankRole   = RoleStrategy<MeleeCombatStrategy,  STRATEGY_TYPE_COMBAT | STRATEGY_TYPE_TANK | STRATEGY_TYPE_MELEE>;
    using MeleeRole  = RoleStrategy<MeleeCombatStrategy,  STRATEGY_TYPE_COMBAT | STRATEGY_TYPE_DPS  | STRATEGY_TYPE_MELEE>;
    using RangedRole = RoleStrategy<RangedCombatStrategy, STRATEGY_TYPE_COMBAT | STRATEGY_TYPE_DPS  | STRATEGY_TYPE_RANGED>;
    using HealRole   = RoleStrategy<RangedCombatStrategy, STRATEGY_TYPE_COMBAT | STRATEGY_TYPE_HEAL | STRATEGY_TYPE_RANGED>;

    // ---------------------------------------------------------------------
    // Registration. Every bot's AiObjectContext is one of the ten class
    // subclasses, each holding its creators in public static lists that the
    // per-bot lists reference, so adding to all ten reaches every bot.
    // ---------------------------------------------------------------------
    class StrategyCtx : public NamedObjectContext<Strategy>
    {
    public:
        StrategyCtx()
        {
            creators[S_CLASSLESS]    = [](PlayerbotAI* ai) -> Strategy* { return new ClasslessStrategy(ai); };
            creators[S_CLASSLESS_NC] = [](PlayerbotAI* ai) -> Strategy* { return new ClasslessNonCombatStrategy(ai); };
        }
    };

    class RoleCtx : public NamedObjectContext<Strategy>
    {
    public:
        RoleCtx() : NamedObjectContext<Strategy>(false, true)
        {
            creators[S_TANK]   = [](PlayerbotAI* ai) -> Strategy* { return new TankRole(ai, S_TANK, "melee"); };
            creators[S_MELEE]  = [](PlayerbotAI* ai) -> Strategy* { return new MeleeRole(ai, S_MELEE, "melee"); };
            creators[S_RANGED] = [](PlayerbotAI* ai) -> Strategy* { return new RangedRole(ai, S_RANGED, "shoot"); };
            creators[S_HEAL]   = [](PlayerbotAI* ai) -> Strategy* { return new HealRole(ai, S_HEAL, "shoot"); };
        }
    };

    class ActionCtx : public NamedObjectContext<Action>
    {
    public:
        ActionCtx()
        {
            creators["classless nuke"]      = [](PlayerbotAI* ai) -> Action* { return new NukeAction(ai); };
            creators["classless dot"]       = [](PlayerbotAI* ai) -> Action* { return new DotAction(ai); };
            creators["classless aoe"]       = [](PlayerbotAI* ai) -> Action* { return new AoeAction(ai); };
            creators["classless heal"]      = [](PlayerbotAI* ai) -> Action* { return new HealAction(ai, "classless heal", true); };
            creators["classless nc heal"]   = [](PlayerbotAI* ai) -> Action* { return new HealAction(ai, "classless nc heal", false); };
            creators["classless interrupt"] = [](PlayerbotAI* ai) -> Action* { return new InterruptAction(ai); };
            creators["classless taunt"]     = [](PlayerbotAI* ai) -> Action* { return new TauntAction(ai); };
            creators["classless defensive"] = [](PlayerbotAI* ai) -> Action* { return new DefensiveAction(ai); };
            creators["classless burst"]     = [](PlayerbotAI* ai) -> Action* { return new BurstAction(ai); };
            creators["classless buff"]      = [](PlayerbotAI* ai) -> Action* { return new BuffAction(ai, "classless buff", false); };
            creators["classless nc buff"]   = [](PlayerbotAI* ai) -> Action* { return new BuffAction(ai, "classless nc buff", true); };
            creators["classless debuff"]    = [](PlayerbotAI* ai) -> Action* { return new DebuffAction(ai); };
            creators["classless control"]   = [](PlayerbotAI* ai) -> Action* { return new ControlAction(ai); };
            creators["classless escape"]    = [](PlayerbotAI* ai) -> Action* { return new EscapeAction(ai); };
            creators["classless pet"]       = [](PlayerbotAI* ai) -> Action* { return new PetAction(ai, "classless pet"); };
            creators["classless nc pet"]    = [](PlayerbotAI* ai) -> Action* { return new PetAction(ai, "classless nc pet"); };
            creators["classless approach"]  = [](PlayerbotAI* ai) -> Action* { return new ApproachAction(ai); };
            creators["classless totem"]     = [](PlayerbotAI* ai) -> Action* { return new TotemAction(ai); };
            creators["classless guardian"]  = [](PlayerbotAI* ai) -> Action* { return new GuardianAction(ai); };
            creators["classless form"]      = [](PlayerbotAI* ai) -> Action* { return new FormAction(ai); };
        }
    };

    class ValueCtx : public NamedObjectContext<UntypedValue>
    {
    public:
        ValueCtx()
        {
            creators[V_KIT] = [](PlayerbotAI* ai) -> UntypedValue* { return new KitValue(ai); };
        }
    };

    bool g_registered = false;

    // The strategy names that belong to one class's own AI, by class id:
    // in that class's list, but neither in the shared playerbots list nor in
    // every class's list (which is where other modules' strategies land).
    std::array<std::set<std::string>, MAX_CLASSES> g_classOnly;

    struct ClassLists
    {
        uint8 classId;
        SharedNamedObjectContextList<Strategy>& strategies;
        SharedNamedObjectContextList<Action>& actions;
        SharedNamedObjectContextList<UntypedValue>& values;
    };

    std::vector<ClassLists> AllClasses()
    {
        return {
            { CLASS_DEATH_KNIGHT, DKAiObjectContext::sharedStrategyContexts,      DKAiObjectContext::sharedActionContexts,      DKAiObjectContext::sharedValueContexts },
            { CLASS_DRUID,        DruidAiObjectContext::sharedStrategyContexts,   DruidAiObjectContext::sharedActionContexts,   DruidAiObjectContext::sharedValueContexts },
            { CLASS_HUNTER,       HunterAiObjectContext::sharedStrategyContexts,  HunterAiObjectContext::sharedActionContexts,  HunterAiObjectContext::sharedValueContexts },
            { CLASS_MAGE,         MageAiObjectContext::sharedStrategyContexts,    MageAiObjectContext::sharedActionContexts,    MageAiObjectContext::sharedValueContexts },
            { CLASS_PALADIN,      PaladinAiObjectContext::sharedStrategyContexts, PaladinAiObjectContext::sharedActionContexts, PaladinAiObjectContext::sharedValueContexts },
            { CLASS_PRIEST,       PriestAiObjectContext::sharedStrategyContexts,  PriestAiObjectContext::sharedActionContexts,  PriestAiObjectContext::sharedValueContexts },
            { CLASS_ROGUE,        RogueAiObjectContext::sharedStrategyContexts,   RogueAiObjectContext::sharedActionContexts,   RogueAiObjectContext::sharedValueContexts },
            { CLASS_SHAMAN,       ShamanAiObjectContext::sharedStrategyContexts,  ShamanAiObjectContext::sharedActionContexts,  ShamanAiObjectContext::sharedValueContexts },
            { CLASS_WARLOCK,      WarlockAiObjectContext::sharedStrategyContexts, WarlockAiObjectContext::sharedActionContexts, WarlockAiObjectContext::sharedValueContexts },
            { CLASS_WARRIOR,      WarriorAiObjectContext::sharedStrategyContexts, WarriorAiObjectContext::sharedActionContexts, WarriorAiObjectContext::sharedValueContexts },
        };
    }

    char const* RoleStrategyName(uint8 role)
    {
        switch (role)
        {
            case ClasslessBots::ROLE_TANK:   return S_TANK;
            case ClasslessBots::ROLE_HEAL:   return S_HEAL;
            case ClasslessBots::ROLE_RANGED: return S_RANGED;
            case ClasslessBots::ROLE_MELEE:  return S_MELEE;
            default:                         return nullptr;
        }
    }

    // Builds a ChangeStrategy string from the strategies an engine has now.
    struct StrategyEdit
    {
        std::set<std::string> have;
        std::string changes;

        explicit StrategyEdit(std::vector<std::string> const& current) : have(current.begin(), current.end()) { }

        void Add(std::string const& name)
        {
            if (!have.count(name))
                changes += (changes.empty() ? "+" : ",+") + name;
        }

        void Remove(std::string const& name)
        {
            if (have.count(name))
                changes += (changes.empty() ? "-" : ",-") + name;
        }
    };
}

void ClasslessBots::Register()
{
    if (g_registered)
        return;

    // Idempotent; playerbots has normally done it already in
    // OnBeforeWorldInitialized, and this makes sure ours lands in built lists.
    AiObjectContext::BuildAllSharedContexts();

    std::vector<ClassLists> classes = AllClasses();

    // What every class has in common, before anything of ours is added.
    SharedNamedObjectContextList<Strategy> shared;
    AiObjectContext::BuildSharedStrategyContexts(shared);
    std::map<std::string, uint32> inClasses;
    for (ClassLists const& c : classes)
        for (auto const& [name, creator] : c.strategies.creators)
            ++inClasses[name];
    for (ClassLists const& c : classes)
    {
        std::set<std::string>& own = g_classOnly[c.classId];
        for (auto const& [name, creator] : c.strategies.creators)
            if (!shared.creators.count(name) && inClasses[name] < classes.size())
                own.insert(name);
    }

    // Each list owns what it is given and deletes it, so every class gets
    // its own instances.
    for (ClassLists const& c : classes)
    {
        c.strategies.Add(new StrategyCtx());
        c.strategies.Add(new RoleCtx());
        c.actions.Add(new ActionCtx());
        c.values.Add(new ValueCtx());
    }

    g_registered = true;
    for (ClassLists const& c : classes)
        g_registered = g_registered && c.strategies.creators.count(S_CLASSLESS) && c.strategies.creators.count(S_HEAL)
            && c.actions.creators.count("classless nuke") && c.values.creators.count(V_KIT);

    if (g_registered)
        LOG_INFO("server.loading", ">> Classless: Hero bots fight with their own abilities (playerbots strategy '{}').",
                 S_CLASSLESS);
    else
        LOG_ERROR("server.loading", ">> Classless: could not add the '{}' strategy to every playerbots class. "
                  "Hero bots will use their chassis class's rotation.", S_CLASSLESS);
}

void ClasslessBots::Tick(Player* player, CharState& st)
{
    if (!g_registered)
        return;
    PlayerbotAI* ai = GET_PLAYERBOT_AI(player);
    if (!ai)
        return;

    std::set<std::string> const& classOnly = g_classOnly[player->getClass()];

    // ---- combat ----
    StrategyEdit combat(ai->GetStrategies(BOT_STATE_COMBAT));
    for (std::string const& name : combat.have)
        if (classOnly.count(name))
            combat.Remove(name);
    combat.Add(S_CLASSLESS);

    // The role. One the owner chose with `co +classless <role>` is kept even
    // after playerbots resets the strategies; otherwise the kit decides.
    uint8 present = ROLE_NONE;
    for (uint8 r : { ROLE_TANK, ROLE_HEAL, ROLE_MELEE, ROLE_RANGED })
        if (combat.have.count(RoleStrategyName(r)))
            present = r;
    KitPtr kit = ai->GetAiObjectContext()->GetValue<KitPtr>(V_KIT)->Get();
    uint8 derived = kit ? uint8(kit->role) : uint8(ROLE_MELEE);
    // Only once this session has put a role on the bot: a role strategy
    // playerbots saved last session is the old kit's, not a choice.
    if (st.botRole != ROLE_NONE && present != ROLE_NONE && present != st.botRole && present != derived)
        st.botRoleOverride = present;
    uint8 role = st.botRoleOverride ? st.botRoleOverride : derived;
    if (present != role)
        combat.Add(RoleStrategyName(role));   // its siblings come off with it
    st.botRole = role;

    // targeting and positioning that go with the role
    bool tank = role == ROLE_TANK;
    bool meleeDps = role == ROLE_MELEE;
    if (tank)
    {
        combat.Add("tank assist");
        combat.Add("tank face");
        combat.Remove("dps assist");
    }
    else
    {
        combat.Add("dps assist");
        combat.Remove("tank assist");
        combat.Remove("tank face");
    }
    if (meleeDps)
        combat.Add("behind");
    else
        combat.Remove("behind");
    // the class's own positioning would fight the role's
    combat.Remove("close");
    combat.Remove("ranged");

    // ---- out of combat ----
    StrategyEdit nonCombat(ai->GetStrategies(BOT_STATE_NON_COMBAT));
    for (std::string const& name : nonCombat.have)
        if (classOnly.count(name))
            nonCombat.Remove(name);
    nonCombat.Add(S_CLASSLESS_NC);
    if (tank)
    {
        nonCombat.Add("tank assist");
        nonCombat.Remove("dps assist");
    }
    else
    {
        nonCombat.Add("dps assist");
        nonCombat.Remove("tank assist");
    }

    if (!combat.changes.empty())
    {
        LOG_DEBUG("module", "Classless: bot {} combat strategies {}", player->GetName(), combat.changes);
        ai->ChangeStrategy(combat.changes, BOT_STATE_COMBAT);
    }
    if (!nonCombat.changes.empty())
    {
        LOG_DEBUG("module", "Classless: bot {} non-combat strategies {}", player->GetName(), nonCombat.changes);
        ai->ChangeStrategy(nonCombat.changes, BOT_STATE_NON_COMBAT);
    }
}

#else   // no mod-playerbots on this realm

void ClasslessBots::Register() { }
void ClasslessBots::Tick(Player* /*player*/, ClasslessWildcard::CharState& /*st*/) { }

#endif
