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

#ifndef MOD_CW_CLASSLESS_MGR_H
#define MOD_CW_CLASSLESS_MGR_H

#include "ClasslessWildcard.h"

class Player;

class ClasslessMgr
{
public:
    static ClasslessMgr* instance();

    ClasslessWildcard::Config cfg;

    void LoadConfig(bool reload);
    void BuildLibrary(); // call once world data (DBC/SpellMgr) is loaded

    // ------- library access -------
    ClasslessWildcard::AbilityEntry const* GetAbility(uint32 firstSpellId) const;
    ClasslessWildcard::TalentPoolEntry const* GetTalent(uint32 talentId) const;
    std::map<uint32, ClasslessWildcard::AbilityEntry> const& Abilities() const { return _abilities; }
    std::map<uint32, ClasslessWildcard::TalentPoolEntry> const& Talents() const { return _talents; }
    // resolve any spell id (any rank) to its library entry, nullptr if not in library
    ClasslessWildcard::AbilityEntry const* FindAbilityBySpell(uint32 spellId) const;

    // ------- per-character state -------
    ClasslessWildcard::CharState& GetState(Player* player);
    void UnloadState(ObjectGuid guid);
    // bot/system accounts (e.g. mod-playerbots "rndbot" accounts) play with
    // vanilla class rules so their factories keep working
    bool IsExempt(Player* player) { return GetState(player).exempt; }
    bool IsWildcard(Player* player) { return GetState(player).mode == ClasslessWildcard::Mode::Wildcard; }

    // ------- lifecycle -------
    // Force the character onto the one configured chassis class. Returns true
    // if it actually converted one. Safe to call repeatedly.
    bool EnforceChassis(Player* player);
    void HandleFirstLogin(Player* player);
    void HandleLogin(Player* player);
    void HandleLevelUp(Player* player, uint8 oldLevel);
    bool SetMode(Player* player, ClasslessWildcard::Mode mode, std::string* err = nullptr);

    // ------- classless (free-pick) -------
    bool BuyAbility(Player* player, uint32 firstSpellId, std::string* err);
    bool UnlearnAbility(Player* player, uint32 firstSpellId, std::string* err);
    bool BuyTalentRank(Player* player, uint32 talentId, std::string* err);
    bool Respec(Player* player, std::string* err);

    // ------- wildcard -------
    // returns granted entry (firstSpellId / talentId) or 0
    uint32 RollAbility(Player* player, ClasslessWildcard::GrantSource source = ClasslessWildcard::GrantSource::Rolled);
    uint32 RollTalent(Player* player);
    bool Reroll(Player* player, bool isTalent, uint32 entry, std::string* err);
    bool ToggleLock(Player* player, uint32 firstSpellId, std::string* err);

    // ------- displayed resource bar (0 mana, 1 rage, 3 energy, 255 default) -------
    bool SetDisplayPower(Player* player, uint8 powerIdx, std::string* err);
    void ApplyDisplayPower(Player* player); // re-apply saved choice (login)

    // ------- primary stat allocation -------
    uint32 StatBudget(Player* player) const;
    uint32 SpentStatPoints(ClasslessWildcard::CharState const& st) const;
    void   ApplyStatMods(Player* player);   // sync applied bonuses to the allocation
    bool   SetStatAllocation(Player* player, std::array<uint32, 5> const& alloc, std::string* err);

    // ------- onboarding & exits -------
    std::map<uint32, ClasslessWildcard::Archetype> const& Archetypes() const { return _archetypes; }
    bool ApplyArchetype(Player* player, uint32 archetypeId, std::string* err);
    // Full reset + (optional) mode switch for gold — the late "exit" once the
    // level-based mode lock has passed.
    bool Rebirth(Player* player, ClasslessWildcard::Mode target, std::string* err);

    // Buy a Scroll of Fortune for gold straight from the addon panel; which 0 =
    // ability scroll, 1 = talent scroll (cheaper). Cost scales with level.
    bool BuyScroll(Player* player, uint32 which, std::string* err);
    // Gold price of an ability Scroll of Fortune at the given level (talent
    // scrolls are half). Shared by BuyScroll and the addon state packet.
    uint32 ScrollBuyCost(uint8 level) const;

    // ------- helpers -------
    // Strip the shell class's equipped creation gear and equip the neutral Hero
    // outfit. Run at character creation (so the character-select preview is
    // right) and again as part of the first-login starter kit. Returns true
    // when it changed anything -- the creation hook fires AFTER the initial
    // SaveToDB, so the caller must re-save for the change to persist.
    bool ApplyStarterGear(Player* player);
    void TeachProficiencies(Player* player);
    void UpdateAbilityRanks(Player* player); // learn newly available ranks of owned lines
    // true while the module itself is teaching spells (lets the learn-spell
    // hook distinguish module grants from trainers/quests)
    bool IsApplyingGrant() const { return _applyingGrant; }
    void SaveState(Player* player);          // persist scalar state row
    void AnnounceState(Player* player);      // login summary line
    uint32 AbilityCost(ClasslessWildcard::AbilityEntry const& e) const;
    uint32 RollWeight(ClasslessWildcard::Rarity rarity, uint32 overrideWeight) const;
    uint32 SpentTalentRanksInTab(ClasslessWildcard::CharState const& st, uint32 tabId) const;

private:
    ClasslessMgr() = default;

    void LoadOverrides();
    void LoadCharacter(Player* player, ClasslessWildcard::CharState& st);
    void GrantAbilityInternal(Player* player, ClasslessWildcard::AbilityEntry const& e,
                              ClasslessWildcard::GrantSource source, bool persist = true);
    void RemoveAbilityInternal(Player* player, ClasslessWildcard::AbilityEntry const& e, bool persist = true);
    void GrantTalentRankInternal(Player* player, ClasslessWildcard::TalentPoolEntry const& t, uint8 newRank, bool persist = true);
    void RemoveTalentInternal(Player* player, ClasslessWildcard::TalentPoolEntry const& t, bool persist = true);
    void TickBans(ClasslessWildcard::CharState& st, ObjectGuid guid);
    void SaveBans(ObjectGuid guid, ClasslessWildcard::CharState const& st);
    bool IsBanned(ClasslessWildcard::CharState const& st, bool isTalent, uint32 entry) const;
    uint32 OwnedClassMask(ClasslessWildcard::CharState const& st) const;

    void LoadArchetypes();

    std::map<uint32, ClasslessWildcard::AbilityEntry> _abilities;      // firstSpellId -> entry
    std::map<uint32, ClasslessWildcard::TalentPoolEntry> _talents;     // talentId -> entry
    std::map<uint32, ClasslessWildcard::Archetype> _archetypes;
    std::unordered_map<uint32, uint32> _spellToFirst;                  // any rank -> firstSpellId
    std::unordered_map<ObjectGuid::LowType, ClasslessWildcard::CharState> _states;
    bool _libraryBuilt = false;
    bool _applyingGrant = false;
    // true while batch-granting (starting hand, rebirth replay): the client
    // shows those results in bulk, so per-roll reveal popups are suppressed
    bool _revealSuppress = false;

    struct GrantGuard
    {
        explicit GrantGuard(bool& flag) : _flag(flag) { _flag = true; }
        ~GrantGuard() { _flag = false; }
        bool& _flag;
    };
};

#define sClasslessMgr ClasslessMgr::instance()

#endif
