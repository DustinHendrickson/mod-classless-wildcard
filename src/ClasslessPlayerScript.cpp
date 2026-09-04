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

#include "Chat.h"
#include "ClasslessMgr.h"
#include "DBCStores.h"
#include "DatabaseEnv.h"
#include "Duration.h"
#include "GameTime.h"
#include "Optional.h"
#include "Pet.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "StringFormat.h"
#include "World.h"

using namespace ClasslessWildcard;

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
    std::unordered_map<uint64, uint32> _tickAcc; // guid low -> ms accumulator

    // The last money a character SPENT, and the world tick it happened on.
    // A class trainer takes the gold and then teaches the spell, and the
    // module takes the spell straight back -- so without this the Hero pays
    // for nothing. Keyed on the tick because the two happen inside one
    // opcode: a debit from any other source is a different tick.
    struct Spend { uint32 copper = 0; uint32 tick = 0; };
    std::unordered_map<uint64, Spend> _lastSpend;

public:
    ClasslessPlayerScript() : PlayerScript("ClasslessPlayerScript", {
        PLAYERHOOK_ON_CREATE,
        PLAYERHOOK_ON_FIRST_LOGIN,
        PLAYERHOOK_ON_LOGIN,
        PLAYERHOOK_ON_LOGOUT,
        PLAYERHOOK_ON_DELETE_FROM_DB,
        PLAYERHOOK_ON_LEVEL_CHANGED,
        PLAYERHOOK_ON_CALCULATE_TALENTS_POINTS,
        PLAYERHOOK_CAN_LEARN_TALENT,
        PLAYERHOOK_ON_LEARN_SPELL,
        PLAYERHOOK_ON_MONEY_CHANGED,
        PLAYERHOOK_ON_AFTER_UPDATE_MAX_POWER,
        PLAYERHOOK_ON_PLAYER_IS_CLASS,
        PLAYERHOOK_ON_BEFORE_GUARDIAN_INIT_STATS_FOR_LEVEL,
        PLAYERHOOK_ON_UPDATE
    }) { }

    // Runs before the money actually moves, with the signed delta.
    void OnPlayerMoneyChanged(Player* player, int32& amount) override
    {
        if (!sClasslessMgr->cfg.enabled || amount >= 0)
            return;
        Spend& spend = _lastSpend[player->GetGUID().GetCounter()];
        spend.copper = uint32(-amount);
        spend.tick = uint32(GameTime::GetGameTimeMS().count());
    }

    // "Does this Hero count as a <class> for the purposes of X?"
    //
    // The core asks this wherever behaviour is class-specific, tagging each
    // question with a ClassContext. Every Hero runs one chassis (Paladin by
    // default), so without an answer here the chassis quietly decides what a
    // classless character may do -- a Hero could equip a Libram but never an
    // Idol, Totem or Sigil, however much druid or shaman a build had bought.
    //
    // Answered only for the contexts where the chassis would otherwise take
    // something away. std::nullopt everywhere else means "use my real class",
    // deliberately: the untouched contexts drive Death Knight rune machinery
    // and the stat/talent maths this module already replaces, where claiming
    // to be every class at once breaks things rather than freeing them.
    Optional<bool> OnPlayerIsClass(Player const* player, Classes playerClass, ClassContext context) override
    {
        Config const& cfg = sClasslessMgr->cfg;
        if (!cfg.enabled || !cfg.classlessClassChecks)
            return std::nullopt;

        // Decide on the context BEFORE looking the character up. IsClass runs
        // in combat paths and during login, and the state lookup can pull a
        // character in from the database; every context we do not answer must
        // cost nothing but this switch.
        switch (context)
        {
            // Relics: Libram, Idol, Totem, Sigil and the warlock relic all
            // live in slot 17, but the core hands that slot out only to the
            // one class each belongs to -- in FindEquipSlot and again in
            // CanUseItem. A Hero should be able to wear whichever matches the
            // spells they actually bought.
            case CLASS_CONTEXT_EQUIP_RELIC:
            // Shields are restricted to Paladin/Warrior/Shaman. The default
            // chassis already passes that test, but a realm configured onto
            // any other chassis would silently lose shields.
            case CLASS_CONTEXT_EQUIP_SHIELDS:
            // Reactive abilities -- Overpower, Revenge, Riposte, Counterattack
            // -- only light up if the core sets the matching aura state, and
            // it sets each one only for its own class. A Hero who bought
            // Overpower needs the warrior state to exist. Harmless when the
            // ability is not owned: an aura state nothing reads costs nothing.
            case CLASS_CONTEXT_ABILITY_REACTIVE:
                break;
            // Runes, and only the Death Knight question, and only when Death
            // Knight content is switched on.
            //
            // Three sites share this context for CLASS_DEATH_KNIGHT and they
            // must agree: Player::InitRunes allocates m_runes, Player::Update
            // ticks rune cooldowns through it, and Regenerate(RUNIC_POWER)
            // refills the bar. The rune accessors dereference m_runes with no
            // null check, so answering some and not others would allocate
            // nothing and then read it. Answering none -- which is where this
            // module stood -- is self-consistent but leaves a Hero who has
            // bought a rune-cost spell casting into a null rune block.
            //
            // Tied to IncludeDeathKnight so a realm that does not use Death
            // Knight abilities pays neither the allocation nor the per-tick
            // rune loop.
            case CLASS_CONTEXT_ABILITY:
                if (playerClass != CLASS_DEATH_KNIGHT)
                    return std::nullopt;
                // From the character's own snapshot, NOT the live config: this
                // same question gates both the one-time InitRunes allocation
                // and the per-tick loop that reads the block it allocates. If
                // a `.reload config` could change the answer underneath a
                // logged-in character, the loop would read a block InitRunes
                // never made.
                return sClasslessMgr->GetState(const_cast<Player*>(player)).runes;
            // Pets. Answered from the pet the Hero actually has, not from the
            // class alone, because two call sites need opposite answers.
            //
            // Pet::IsPermanentPetFor runs an if/else chain -- warlock, then
            // death knight, then mage -- and permanence decides the pet
            // spellbook, the pet tab and whether owner auras reach it. A flat
            // "yes" to warlock wins that chain every time and answers
            // "is it a demon?" for a ghoul, so a ghoul could never be
            // permanent. Answering per class from the pet's creature type lets
            // the core's own chain fall through to the right branch.
            //
            // Meanwhile LoadPetFromDB bails out on
            //   IsClass(DEATH_KNIGHT, PET) && !CanSeeDKPet()
            // and CanSeeDKPet is the Master of Ghouls flag no Hero has, so
            // claiming death knight there would stop pets loading from the
            // database at all. That call happens while the pet is being
            // restored and the Hero therefore has none, so returning nullopt
            // when there is no pet keeps that path on the real class -- the
            // hazard is closed by construction rather than by remembering.
            case CLASS_CONTEXT_PET:
            {
                // answers inline below, so it checks the exemption itself
                if (sClasslessMgr->IsExempt(const_cast<Player*>(player)))
                    return std::nullopt;
                Pet* pet = player->GetPet();
                if (!pet || !pet->GetCreatureTemplate())
                    return std::nullopt;
                uint32 const creatureType = pet->GetCreatureTemplate()->type;
                switch (playerClass)
                {
                    case CLASS_WARLOCK:      return creatureType == CREATURE_TYPE_DEMON;
                    case CLASS_DEATH_KNIGHT: return creatureType == CREATURE_TYPE_UNDEAD;
                    case CLASS_MAGE:         return creatureType == CREATURE_TYPE_ELEMENTAL;
                    case CLASS_HUNTER:       return creatureType == CREATURE_TYPE_BEAST;
                    default:                 return std::nullopt;
                }
            }
            default:
                return std::nullopt;
        }

        // bots and system accounts play by vanilla class rules
        if (sClasslessMgr->IsExempt(const_cast<Player*>(player)))
            return std::nullopt;

        return true;
    }

    // What KIND of pet is this?
    //
    // Pet::Create works it out from the owner's class, so on a one-chassis
    // realm it worked it out as "none": petType stayed MAX_PET_TYPE, the core
    // logged "Unknown type pet ... summoned by player class 2" on every
    // summon, the pet never got UNIT_FLAG_PLAYER_CONTROLLED (no dismiss
    // prompt), and it was not recorded as the player's current pet. The pet
    // still appeared and still took orders, which is why it looks fine.
    //
    // This hook takes petType by reference and runs before that guess, so
    // decide from the pet instead of from the owner: hunters tame beasts,
    // every other pet a class summons -- demon, undead, elemental -- is a
    // summoned pet. Setting it here also skips the class chain entirely, so a
    // tamed beast cannot be mistyped as a summon.
    void OnPlayerBeforeGuardianInitStatsForLevel(Player* player, Guardian* guardian,
                                                 CreatureTemplate const* cinfo, PetType& petType) override
    {
        Config const& cfg = sClasslessMgr->cfg;
        if (!cfg.enabled || !cfg.classlessClassChecks || !player || !guardian || !cinfo)
            return;
        if (sClasslessMgr->IsExempt(player))
            return;
        if (!guardian->IsPet())
            return;

        petType = (cinfo->type == CREATURE_TYPE_BEAST) ? HUNTER_PET : SUMMON_PET;
    }

    // Universal resources: every Hero keeps mana, rage AND energy pools alive
    // simultaneously (the client already tracks all pools — druids prove it —
    // only the chassis bar is displayed; the addon renders the off-pools).
    // This hook fires at the end of Player::UpdateMaxPower for every power
    // type on every stat update, so the pools can never be zeroed out.
    void OnPlayerAfterUpdateMaxPower(Player* player, Powers& power, float& value) override
    {
        Config const& cfg = sClasslessMgr->cfg;
        if (!cfg.enabled)
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
            default:
                break;
        }
    }

    // Put the character on the one chassis the moment it is created, so the
    // character list, its starting stats and its saved class all agree from
    // the very first byte written.
    void OnPlayerCreate(Player* player) override
    {
        if (sClasslessMgr->cfg.enabled)
        {
            sClasslessMgr->EnforceChassis(player);
            // Dress the Hero in the neutral outfit now, so the character-select
            // screen shows it instead of the shell class's starting gear. This
            // hook fires AFTER creation's SaveToDB already committed, so the
            // gear change must be saved again or it silently evaporates.
            if (sClasslessMgr->ApplyStarterGear(player))
                player->SaveToDB(false, false);
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

        // characters that predate the module, or predate a chassis change,
        // convert here on their next login
        sClasslessMgr->EnforceChassis(player);

        sClasslessMgr->HandleLogin(player);

        // A Hero may keep an undead pet, so let them see one.
        //
        // CanSeeDKPet is the Master of Ghouls flag, and the core leans on it
        // twice: LoadPetFromDB refuses to restore a pet for anyone who counts
        // as a Death Knight without it, and the character-select screen hides
        // a stored ghoul. Since the module answers the Death Knight pet
        // question for a Hero holding an undead pet, leaving the flag off
        // would let that refusal fire while a ghoul is already out and block
        // the next pet from loading. Setting it makes the check moot in the
        // right direction and shows the ghoul on the login screen besides.
        if (cfg.classlessClassChecks && !sClasslessMgr->IsExempt(player))
            player->SetShowDKPet(true);

        // Restore the saved main-bar choice once the login stat pass has
        // settled. The chassis owns the mana pool itself -- it is a real class
        // with a real base mana, so there is nothing here to build.
        if (!sClasslessMgr->IsExempt(player))
            player->m_Events.AddEventAtOffset([player]()
            {
                sClasslessMgr->ApplyDisplayPower(player); // saved bar choice
            }, 2s);
    }

    // A deleted character has to take its module rows with it.
    //
    // ObjectMgr::SetHighestGuids sets the player GUID counter to MAX(guid) + 1
    // at EVERY startup, so deleting the highest character and restarting hands
    // that same GUID to the next character created. Without this, that new
    // character would load the deleted Hero's abilities, talents, essence,
    // stat allocation, chosen path and reroll cooldowns -- a fresh level 1 with
    // somebody else's level 80 build. Even where the GUID is not reused the
    // rows would simply accumulate forever.
    //
    // Appended to the core's own delete transaction, so the rows go with the
    // character or not at all.
    void OnPlayerDeleteFromDB(CharacterDatabaseTransaction trans, uint32 guid) override
    {
        trans->Append("DELETE FROM cw_char_state WHERE guid = {}", guid);
        trans->Append("DELETE FROM cw_char_abilities WHERE guid = {}", guid);
        trans->Append("DELETE FROM cw_char_talents WHERE guid = {}", guid);
        trans->Append("DELETE FROM cw_char_bans WHERE guid = {}", guid);
        sClasslessMgr->UnloadState(ObjectGuid::Create<HighGuid::Player>(guid));
    }

    void OnPlayerLogout(Player* player) override
    {
        _tickAcc.erase(player->GetGUID().GetCounter());
        _lastSpend.erase(player->GetGUID().GetCounter());
        sClasslessMgr->UnloadState(player->GetGUID());
    }

    // 2-second maintenance tick:
    //  * universal STAT layer — fills the gaps the chassis math leaves so
    //    every allocatable stat matters on a classless Hero:
    //    AGI -> melee/ranged AP, INT -> spell power.
    //    (STR->AP/block, STA->health, AGI->crit/dodge, INT->mana/spell crit
    //    already work uniformly through the shared chassis.)
    void OnPlayerUpdate(Player* player, uint32 p_time) override
    {
        Config const& cfg = sClasslessMgr->cfg;
        if (!cfg.enabled)
            return;
        if (!player->IsInWorld() || !player->IsAlive())
            return;

        // The stock 3.3.5 client only shows combo points for rogues and cat
        // druids -- Wow.exe gates GetComboPoints by class, so a Hero never SEES
        // the points the server tracks (retail warriors had the same hidden
        // Overpower combo points). Mirror them over the addon channel whenever
        // they change; the addon lights its own pips from this.
        {
            CharState& cpSt = sClasslessMgr->GetState(player);
            if (!cpSt.exempt)
            {
                // Report points for the CURRENT target only, matching what the
                // client would show: combo points stay attached to the unit
                // they were built on, so selecting another mob (or deselecting)
                // must read as zero rather than leaving stale pips lit.
                Unit* selected = player->GetSelectedUnit();
                uint8 cp = selected ? player->GetComboPoints(selected) : 0;
                if (cp != cpSt.lastComboPush)
                {
                    cpSt.lastComboPush = cp;
                    PushAddon(player, Acore::StringFormat("CP|{}", uint32(cp)));
                }

                // Runes have the same problem, one step worse: the stock UI
                // draws the rune bar only for real Death Knight characters, so
                // a Hero with rune-cost abilities gets no way at all to see
                // which runes are up. Mirror the block over the addon channel
                // and let the addon draw it.
                //
                // Guarded by the character's own snapshot, which is exactly
                // the condition under which InitRunes allocated the block --
                // reading it otherwise would dereference a null pointer.
                if (cpSt.runes)
                {
                    // Summarise first, send only if it actually changed. Rune
                    // cooldowns count down every frame, so comparing the
                    // rendered message would send one addon message per tick
                    // for the whole ten seconds a rune takes to come back.
                    // The signature is what the bar SHOWS: rune types and
                    // which are up. Runic power is handled separately below.
                    uint32 maxRunic = player->GetMaxPower(POWER_RUNIC_POWER);
                    uint32 runic = player->GetPower(POWER_RUNIC_POWER);
                    uint32 sig = 0;
                    for (uint8 i = 0; i < MAX_RUNES; ++i)
                    {
                        sig = sig * 8 + uint32(player->GetCurrentRune(i));
                        sig = sig * 2 + (player->GetRuneCooldown(i) ? 0u : 1u);
                    }
                    uint8 bucket = maxRunic ? uint8(runic * 20 / maxRunic) : uint8(0);

                    // A rune changing state is an event and redraws at once.
                    // Runic power moves continuously, so on its own it redraws
                    // at most once a second -- otherwise it, not the runes,
                    // sets the message rate.
                    cpSt.runeAcc += p_time;
                    bool const runesChanged = (sig != cpSt.lastRuneSig);
                    bool const runicDue = (bucket != cpSt.lastRunicBucket) && cpSt.runeAcc >= 1000;

                    if (runesChanged || runicDue)
                    {
                        cpSt.lastRuneSig = sig;
                        cpSt.lastRunicBucket = bucket;
                        cpSt.runeAcc = 0;
                        // "RU|<runic>|<maxRunic>|<type>,<ready>|... x6"
                        std::string msg = Acore::StringFormat("RU|{}|{}", runic, maxRunic);
                        for (uint8 i = 0; i < MAX_RUNES; ++i)
                            msg += Acore::StringFormat("|{},{}",
                                uint32(player->GetCurrentRune(i)),
                                player->GetRuneCooldown(i) ? 0 : 1);
                        PushAddon(player, msg);
                    }
                }
            }
        }

        uint32& acc = _tickAcc[player->GetGUID().GetCounter()];
        acc += p_time;
        if (acc < 2000)
            return;
        acc %= 2000;

        if (sClasslessMgr->IsExempt(player))
            return;

        CharState& st = sClasslessMgr->GetState(player);

        // A pet that was away when its spell went is not caught by the sweep in
        // RemoveAbilityInternal: mounting temporarily unsummons it, so a Hero
        // who rerolls Summon Imp while mounted has no pet to send home at that
        // moment and gets the imp back on dismounting. Costs a map lookup and a
        // known-spell check every two seconds.
        sClasslessMgr->DismissOrphanedSummons(player);

        // Player::InitDataForForm resets the displayed power to the CLASS's own
        // whenever a shapeshift starts or ends, and a warrior stance counts --
        // so a Hero who picked the rage bar was put back on mana the first time
        // they used Battle Stance. Cat, Ghoul, Bear and Dire Bear are the forms
        // the core gives a power type of their own; in anything else, including
        // no form at all, the Hero's own choice stands.
        if (st.displayPower != 255)
        {
            switch (player->GetShapeshiftForm())
            {
                case FORM_CAT:
                case FORM_GHOUL:
                case FORM_BEAR:
                case FORM_DIREBEAR:
                    break;
                default:
                    sClasslessMgr->ApplyDisplayPower(player);
                    break;
            }
        }

        // The universal stat layer. Not optional: on one chassis, Agility and
        // Intellect do nothing for most builds without it, and a Hero who spent
        // points there would have spent them on nothing.
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

        // A class trainer takes the gold in Trainer::TeachSpell and teaches the
        // spell immediately afterwards, so by the time this fires the Hero has
        // already paid for something they are about to lose. Give it back.
        // Only a debit from this same world tick counts, which is the one the
        // trainer just took: the two happen inside a single opcode.
        uint32 refund = 0;
        if (auto itr = _lastSpend.find(player->GetGUID().GetCounter()); itr != _lastSpend.end())
            if (itr->second.tick == uint32(GameTime::GetGameTimeMS().count()))
            {
                refund = itr->second.copper;
                itr->second.copper = 0;   // never refund the same payment twice
            }

        // revert after the learn completes (safe outside the learn call stack)
        uint32 firstSpell = e->firstSpellId;
        player->m_Events.AddEventAtOffset([player, firstSpell, refund]()
        {
            AbilityEntry const* entry = sClasslessMgr->GetAbility(firstSpell);
            if (!entry)
                return;
            for (uint32 rankSpell : entry->ranks)
                if (player->HasSpell(rankSpell))
                    player->removeSpell(rankSpell, SPEC_MASK_ALL, false);
            if (refund)
                player->ModifyMoney(int32(refund));
            ChatHandler(player->GetSession()).SendSysMessage(
                refund
                ? "|cff00ccff[Classless]|r That spell is managed by the classless system. Your money has been "
                  "returned. Learn it through the Hero Advancement NPC (or /cw) instead of a class trainer."
                : "|cff00ccff[Classless]|r That spell is managed by the classless system. Learn it through the "
                  "Hero Advancement NPC (or /cw) instead of a class trainer.");
        }, 1ms);
    }
};

// There was a spell script here that waived SPELL_FAILED_NO_POWER for any
// ability drawing on a pool other than the displayed one. It did nothing, and
// it must not be brought back:
//
//   * Spell::CheckCast calls the OnSpellCheckCast hook as its FIRST statement,
//     with the result still SPELL_CAST_OK, so no check has run yet and the
//     failure it was looking for can never be seen.
//   * Nothing is missing. Spell::CheckPower reads the pool the SPELL uses, not
//     the one on the unit frame, and RegenerateAll refills energy and mana for
//     every class while the module keeps rage flowing. A Hero with rage casts
//     rage abilities; a Hero without rage should not.
//   * Had it worked it would have been a hole: every off-chassis ability would
//     have been castable on an empty pool, which is most of a classless build.

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
        if (!cfg.enabled)
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
    //
    // Player::RewardRage is
    //   (damage / rageconversion * 7.5 + weaponSpeedHitFactor) / 2
    // and the halving is not optional: without it a Hero earned roughly twice
    // the rage a warrior does for the same swing, which is not what
    // "% of warrior-formula rage" says on the tin. The weapon-speed term needs
    // the attack type the core has and this hook does not, so it is left out
    // and the small amount it adds is simply not granted.
    void ModifyMeleeDamage(Unit* /*target*/, Unit* attacker, uint32& damage) override
    {
        if (!damage || !WantsCustomRage(attacker))
            return;
        Config const& cfg = sClasslessMgr->cfg;
        if (!cfg.urRageDealtPct)
            return;
        float addRage = float(damage) / RageConversion(attacker->GetLevel()) * 7.5f / 2.0f;
        addRage *= sWorld->getRate(RATE_POWER_RAGE_INCOME);
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
        addRage *= sWorld->getRate(RATE_POWER_RAGE_INCOME);
        addRage = addRage * float(cfg.urRageTakenPct) / 100.0f;
        victim->ModifyPower(POWER_RAGE, int32(addRage * 10.0f));
    }
};

void AddClasslessPlayerScripts()
{
    new ClasslessWorldScript();
    new ClasslessPlayerScript();
    new ClasslessUnitScript();
}
