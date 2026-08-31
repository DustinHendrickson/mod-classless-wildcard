/*
 * mod-classless-wildcard
 * Released under GNU AGPL v3, like AzerothCore.
 */

#include "Chat.h"
#include "ClasslessMgr.h"
#include "DBCStores.h"
#include "Duration.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "Spell.h"
#include "SpellInfo.h"

using namespace ClasslessWildcard;

// Chassis classes whose native power is not mana (warrior, rogue, DK) get a
// SYNTHETIC mana pool. Detected via ChrClasses — NOT GetCreatePowers(), since
// we deliberately set a create-mana on these players (see below).
static bool SyntheticManaChassis(Player* player)
{
    ChrClassesEntry const* ce = sChrClassesStore.LookupEntry(player->getClass());
    return ce && Powers(ce->powerType) != POWER_MANA;
}

static uint32 SyntheticManaTarget(Player* player)
{
    Config const& cfg = sClasslessMgr->cfg;
    // real WoW intellect->mana conversion: first 20 points give 1 mana each,
    // the rest give ManaPerIntellect each; plus base + per-level growth
    uint32 intellect = uint32(player->GetStat(STAT_INTELLECT));
    uint32 intMana = intellect <= 20 ? intellect
                                     : 20 + (intellect - 20) * cfg.urManaPerIntellect;
    return cfg.urBaseMana + cfg.urManaPerLevel * (player->GetLevel() - 1) + intMana;
}

class ClasslessWorldScript : public WorldScript
{
public:
    ClasslessWorldScript() : WorldScript("ClasslessWorldScript", {
        WORLDHOOK_ON_BEFORE_CONFIG_LOAD,
        WORLDHOOK_ON_STARTUP
    }) { }

    void OnBeforeConfigLoad(bool reload) override
    {
        sClasslessMgr->LoadConfig(reload);
    }

    void OnStartup() override
    {
        sClasslessMgr->BuildLibrary();
    }
};

class ClasslessPlayerScript : public PlayerScript
{
    std::unordered_map<uint64, uint32> _manaRegenAcc; // guid low -> ms accumulator

public:
    ClasslessPlayerScript() : PlayerScript("ClasslessPlayerScript", {
        PLAYERHOOK_ON_FIRST_LOGIN,
        PLAYERHOOK_ON_LOGIN,
        PLAYERHOOK_ON_LOGOUT,
        PLAYERHOOK_ON_LEVEL_CHANGED,
        PLAYERHOOK_ON_CALCULATE_TALENTS_POINTS,
        PLAYERHOOK_CAN_LEARN_TALENT,
        PLAYERHOOK_ON_LEARN_SPELL,
        PLAYERHOOK_ON_AFTER_UPDATE_MAX_POWER,
        PLAYERHOOK_ON_UPDATE
    }) { }

    // Universal resources: every Hero keeps mana, rage AND energy pools alive
    // simultaneously (the client already tracks all pools — druids prove it —
    // only the chassis bar is displayed; the addon renders the off-pools).
    // This hook fires at the end of Player::UpdateMaxPower for every power
    // type on every stat update, so the pools can never be zeroed out.
    void OnPlayerAfterUpdateMaxPower(Player* player, Powers& power, float& value) override
    {
        Config const& cfg = sClasslessMgr->cfg;
        if (!cfg.enabled || !cfg.universalResources)
            return;
        if (sClasslessMgr->IsExempt(player)) // bots/system accounts stay vanilla
            return;

        switch (power)
        {
            case POWER_RAGE:
                value = std::max(value, float(cfg.urMaxRage));
                break;
            case POWER_ENERGY:
                value = std::max(value, float(cfg.urMaxEnergy));
                break;
            case POWER_MANA:
                // only chassis without a native mana pool get the synthetic one.
                // HARD-ASSIGN (not max): if the core scaled our create-mana up,
                // max() would keep the inflated value — assignment forces the
                // exact synthetic pool size.
                if (SyntheticManaChassis(player))
                    value = float(SyntheticManaTarget(player));
                break;
            default:
                break;
        }
    }

    void OnPlayerFirstLogin(Player* player) override
    {
        if (sClasslessMgr->cfg.enabled)
            sClasslessMgr->HandleFirstLogin(player);
    }

    void OnPlayerLogin(Player* player) override
    {
        Config const& cfg = sClasslessMgr->cfg;
        if (!cfg.enabled)
            return;
        sClasslessMgr->HandleLogin(player);

        // synthetic mana pools (non-mana chassis) load in at 0 — fill them once
        // the login stat pass has settled, and give the player a real BASE mana
        // so spells with %-of-base-mana costs stop computing to zero
        if (cfg.universalResources && !sClasslessMgr->IsExempt(player))
            player->m_Events.AddEventAtOffset([player]()
            {
                sClasslessMgr->ApplyDisplayPower(player); // saved bar choice
                if (!SyntheticManaChassis(player))
                    return;
                player->SetCreateMana(SyntheticManaTarget(player));
                player->UpdateMaxPower(POWER_MANA);       // re-run our hard-assign hook
                player->SetPower(POWER_MANA, player->GetMaxPower(POWER_MANA));
            }, 2s);
    }

    void OnPlayerLogout(Player* player) override
    {
        _manaRegenAcc.erase(player->GetGUID().GetCounter());
        sClasslessMgr->UnloadState(player->GetGUID());
    }

    // 2-second maintenance tick:
    //  * universal STAT layer — fills the gaps the (warrior) chassis math
    //    leaves so every allocatable stat matters on a classless Hero:
    //    AGI -> melee/ranged AP, INT -> spell power, SPI -> mana regen.
    //    (STR->AP/block, STA->health, AGI->crit/dodge, INT->mana/spell crit
    //    already work uniformly through the shared chassis.)
    //  * synthetic mana upkeep — base mana for %-cost spells, spirit-driven
    //    regeneration (the core's own table gives non-mana classes ~none).
    void OnPlayerUpdate(Player* player, uint32 p_time) override
    {
        Config const& cfg = sClasslessMgr->cfg;
        if (!cfg.enabled || (!cfg.universalResources && !cfg.universalStats))
            return;
        if (!player->IsInWorld() || !player->IsAlive())
            return;

        uint32& acc = _manaRegenAcc[player->GetGUID().GetCounter()];
        acc += p_time;
        if (acc < 2000)
            return;
        uint32 ticks = acc / 2000;
        acc %= 2000;

        if (sClasslessMgr->IsExempt(player))
            return;

        CharState& st = sClasslessMgr->GetState(player);

        if (cfg.universalStats)
        {
            int32 agi = int32(player->GetStat(STAT_AGILITY));
            int32 intel = int32(player->GetStat(STAT_INTELLECT));
            int32 meleeAP = int32(agi * cfg.usMeleeAPPerAgi);
            int32 rangedAP = int32(agi * cfg.usRangedAPPerAgi);
            int32 spellPower = int32(std::max<int32>(0, intel - 10) * cfg.usSpellPowerPerInt);

            if (meleeAP != st.usMeleeAP)
            {
                player->HandleStatFlatModifier(UNIT_MOD_ATTACK_POWER, TOTAL_VALUE, float(meleeAP - st.usMeleeAP), true);
                st.usMeleeAP = meleeAP;
            }
            if (rangedAP != st.usRangedAP)
            {
                player->HandleStatFlatModifier(UNIT_MOD_ATTACK_POWER_RANGED, TOTAL_VALUE, float(rangedAP - st.usRangedAP), true);
                st.usRangedAP = rangedAP;
            }
            if (spellPower != st.usSpellPower)
            {
                player->ApplySpellPowerBonus(spellPower - st.usSpellPower, true);
                st.usSpellPower = spellPower;
            }
        }

        if (cfg.universalResources && SyntheticManaChassis(player))
        {
            // keep base mana current (intellect changes with gear/buffs) so
            // %-of-base-mana spell costs stay correct
            uint32 target = SyntheticManaTarget(player);
            if (player->GetCreateMana() != target)
                player->SetCreateMana(target);

            uint32 maxMana = player->GetMaxPower(POWER_MANA);
            uint32 curMana = player->GetPower(POWER_MANA);
            if (maxMana && curMana < maxMana)
            {
                // mana per 5s: Base + Spirit*PerSpirit + Pct% of max
                float mp5 = cfg.urManaRegenBase
                    + player->GetStat(STAT_SPIRIT) * cfg.urManaRegenPerSpirit
                    + float(maxMana) * float(cfg.urManaRegenPct) / 100.0f;
                int32 add = std::max<int32>(1, int32(mp5 * 2.0f / 5.0f));
                player->ModifyPower(POWER_MANA, add * int32(ticks));
            }
        }
    }

    void OnPlayerLevelChanged(Player* player, uint8 oldLevel) override
    {
        if (sClasslessMgr->cfg.enabled)
            sClasslessMgr->HandleLevelUp(player, oldLevel);
    }

    // Talents flow through the module — suppress the native talent frame
    // economy (except for exempt bot/system accounts, which play vanilla).
    void OnPlayerCalculateTalentsPoints(Player const* player, uint32& talentPointsForLevel) override
    {
        if (!sClasslessMgr->cfg.enabled || !sClasslessMgr->cfg.suppressTalentPoints)
            return;
        if (sClasslessMgr->IsExempt(const_cast<Player*>(player)))
            return;
        talentPointsForLevel = 0;
    }

    bool OnPlayerCanLearnTalent(Player* player, TalentEntry const* /*talent*/, uint32 /*rank*/) override
    {
        if (!sClasslessMgr->cfg.enabled || !sClasslessMgr->cfg.suppressTalentPoints)
            return true;
        return sClasslessMgr->IsExempt(player);
    }

    // Class trainers (and quest rewards) would bypass the essence/roll economy:
    // a Warrior chassis could still buy warrior spells for gold. When a
    // class-library spell is learned outside the module, revert it and point
    // the player at the Hero Advancement system instead.
    void OnPlayerLearnSpell(Player* player, uint32 spellID) override
    {
        using namespace ClasslessWildcard;

        Config const& cfg = sClasslessMgr->cfg;
        if (!cfg.enabled || !cfg.blockOutsideSpellSources)
            return;
        if (sClasslessMgr->IsApplyingGrant())
            return; // our own grant
        if (!player->IsInWorld())
            return; // character-creation starter spells
        if (sClasslessMgr->IsExempt(player))
            return; // bot/system accounts learn spells normally

        for (uint32 allowed : cfg.proficiencySpells)
            if (allowed == spellID)
                return;

        AbilityEntry const* e = sClasslessMgr->FindAbilityBySpell(spellID);
        if (!e)
            return; // not part of the classless library (professions, mounts, ...)

        CharState& st = sClasslessMgr->GetState(player);
        if (st.mode == Mode::Unchosen || st.abilities.count(e->firstSpellId))
            return; // no mode yet, or a rank of a line the Hero legitimately owns

        // revert after the learn completes (safe outside the learn call stack)
        uint32 firstSpell = e->firstSpellId;
        player->m_Events.AddEventAtOffset([player, firstSpell]()
        {
            AbilityEntry const* entry = sClasslessMgr->GetAbility(firstSpell);
            if (!entry)
                return;
            for (uint32 rankSpell : entry->ranks)
                if (player->HasSpell(rankSpell))
                    player->removeSpell(rankSpell, SPEC_MASK_ALL, false);
            ChatHandler(player->GetSession()).SendSysMessage(
                "|cff00ccff[Classless]|r That spell is managed by the classless system — learn it through the "
                "Hero Advancement NPC (or /cw) instead of a class trainer.");
        }, 1ms);
    }
};

// EXPERIMENTAL: allow casting spells that use a power type the chassis class lacks
// (e.g. a Warrior chassis casting mana spells). The power check is waived; the cast
// then drains whatever the player has of that power (usually nothing).
class ClasslessSpellScript : public AllSpellScript
{
public:
    ClasslessSpellScript() : AllSpellScript("ClasslessSpellScript", {
        ALLSPELLHOOK_ON_SPELL_CHECK_CAST
    }) { }

    void OnSpellCheckCast(Spell* spell, bool /*strict*/, SpellCastResult& res) override
    {
        if (!sClasslessMgr->cfg.enabled || !sClasslessMgr->cfg.crossPowerCasting)
            return;
        if (res != SPELL_FAILED_NO_POWER)
            return;

        Unit* caster = spell->GetCaster();
        if (!caster || !caster->IsPlayer())
            return;

        SpellInfo const* info = spell->GetSpellInfo();
        if (!info)
            return;

        // only waive the check when the spell's power type differs from the caster's
        if (info->PowerType != POWER_HEALTH && Powers(info->PowerType) != caster->getPowerType())
            res = SPELL_CAST_OK;
    }
};

// Rage generation for non-rage chassis: the core only rewards rage when the
// DISPLAYED power type is rage, so a Mage chassis swinging a sword would never
// fill its rage pool. Mirror the warrior formulas here for everyone else.
class ClasslessUnitScript : public UnitScript
{
public:
    ClasslessUnitScript() : UnitScript("ClasslessUnitScript", true, {
        UNITHOOK_MODIFY_MELEE_DAMAGE,
        UNITHOOK_ON_DAMAGE
    }) { }

    static float RageConversion(uint8 level)
    {
        return 0.0091107836f * level * level + 3.225598133f * level + 4.2652911f;
    }

    static bool WantsCustomRage(Unit* unit)
    {
        Config const& cfg = sClasslessMgr->cfg;
        if (!cfg.enabled || !cfg.universalResources)
            return false;
        if (!unit || !unit->IsPlayer() || !unit->IsAlive())
            return false;
        if (sClasslessMgr->IsExempt(unit->ToPlayer()))
            return false; // bots/system accounts stay vanilla
        if (unit->getPowerType() == POWER_RAGE) // native rage gen already applies
            return false;
        return unit->GetMaxPower(POWER_RAGE) > 0;
    }

    // rage from dealing melee damage (fires per swing, melee only)
    void ModifyMeleeDamage(Unit* /*target*/, Unit* attacker, uint32& damage) override
    {
        if (!damage || !WantsCustomRage(attacker))
            return;
        Config const& cfg = sClasslessMgr->cfg;
        if (!cfg.urRageDealtPct)
            return;
        float addRage = float(damage) / RageConversion(attacker->GetLevel()) * 7.5f;
        addRage = addRage * float(cfg.urRageDealtPct) / 100.0f;
        attacker->ModifyPower(POWER_RAGE, int32(addRage * 10.0f));
    }

    // rage from taking damage (any source)
    void OnDamage(Unit* /*attacker*/, Unit* victim, uint32& damage) override
    {
        if (!damage || !WantsCustomRage(victim))
            return;
        Config const& cfg = sClasslessMgr->cfg;
        if (!cfg.urRageTakenPct)
            return;
        float addRage = float(damage) / RageConversion(victim->GetLevel()) * 2.5f;
        addRage = addRage * float(cfg.urRageTakenPct) / 100.0f;
        victim->ModifyPower(POWER_RAGE, int32(addRage * 10.0f));
    }
};

void AddClasslessPlayerScripts()
{
    new ClasslessWorldScript();
    new ClasslessPlayerScript();
    new ClasslessSpellScript();
    new ClasslessUnitScript();
}
