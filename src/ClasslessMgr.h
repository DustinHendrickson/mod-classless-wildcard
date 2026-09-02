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
    // Reroll every unlocked ability in one pass, from the server's own state.
    // The starting hand used to fire one RR per ability from a client snapshot,
    // which went stale the moment the first one landed. Returns how many were
    // rerolled.
    uint32 RerollUnlockedAbilities(Player* player, std::string* err);
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

    // Buy a Reroll Scroll for gold straight from the addon panel. Cost scales
    // with level. One scroll covers abilities and talents alike -- the split
    // ability/talent scrolls this used to take a selector for are gone.
    bool BuyScroll(Player* player, std::string* err);
    // Gold price of a Reroll Scroll at the given level. Shared by BuyScroll
    // and the addon state packet.
    uint32 ScrollBuyCost(uint8 level) const;

    // ------- helpers -------
    // Strip the shell class's equipped creation gear and equip the neutral Hero
    // outfit. Run at character creation (so the character-select preview is
    // right) and again as part of the first-login starter kit. Returns true
    // when it changed anything -- the creation hook fires AFTER the initial
    // SaveToDB, so the caller must re-save for the change to persist.
    bool ApplyStarterGear(Player* player);
    void TeachProficiencies(Player* player);
    // Give the Hero the skill lines their spells belong to, so the client files
    // each one under its own spellbook tab instead of dumping them in General.
    // `clearChassisLines` also takes away the class lines the Hero has nothing
    // in. Needed at EVERY login, not once: Player::LoadFromDB re-runs
    // LearnDefaultSkills, which puts the chassis class's lines straight back.
    void SyncSpellbookTabs(Player* player, bool clearChassisLines = false);
    void UpdateAbilityRanks(Player* player); // learn newly available ranks of owned lines
    // Remove class-library spells the Hero did not earn. Runs at every login,
    // not just the first: anything the core re-teaches afterwards would
    // otherwise stay forever.
    uint32 StripUnearnedSpells(Player* player);
    // true while the module itself is teaching spells (lets the learn-spell
    // hook distinguish module grants from trainers/quests)
    bool IsApplyingGrant() const { return _applyingGrant; }
    void SaveState(Player* player);          // persist scalar state row
    void AnnounceState(Player* player);      // login summary line
    uint32 AbilityCost(ClasslessWildcard::AbilityEntry const& e) const;
    // A rolled talent can arrive at ANY rank. The rank it lands on decides how
    // rare the find is -- rank 5 is a legendary result -- and since Wildcard
    // rolls cost nothing, a high rank is every one of those ranks for free.
    ClasslessWildcard::Rarity RankRarity(ClasslessWildcard::TalentPoolEntry const& t, uint8 rank) const;
    // Weighted pick of a rank above `fromRank`, rarer the higher it goes.
    uint8 RollTalentRank(ClasslessWildcard::TalentPoolEntry const& t, uint8 fromRank) const;
    uint32 RollWeight(ClasslessWildcard::Rarity rarity, uint32 overrideWeight) const;
    uint32 SpentTalentRanksInTab(ClasslessWildcard::CharState const& st, uint32 tabId) const;

private:
    ClasslessMgr() = default;

    void LoadOverrides();
    void LoadFormKits();
    // form id -> the library ability that puts you in it, built from spell data
    void BuildFormSpellMap();
    // Give a Hero the stance or form an ability cannot be used without.
    void GrantRequiredForm(Player* player, ClasslessWildcard::AbilityEntry const& e,
                           ClasslessWildcard::GrantSource source);
    // Hand over the basic spells that make a freshly gained form or stance
    // usable. Called for every ability grant; does nothing for the vast
    // majority that are not forms.
    void GrantFormKit(Player* player, ClasslessWildcard::AbilityEntry const& form,
                      ClasslessWildcard::GrantSource source);
    void LoadCharacter(Player* player, ClasslessWildcard::CharState& st);
    void GrantAbilityInternal(Player* player, ClasslessWildcard::AbilityEntry const& e,
                              ClasslessWildcard::GrantSource source, bool persist = true,
                              bool announce = true);
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
    // form/stance spell (any rank) -> the basic spells that come with it
    std::unordered_map<uint32, std::vector<uint32>> _formKits;
    // shapeshift form id -> the first-rank spell that grants that form
    std::unordered_map<uint32, uint32> _formSpells;
    // spell (any rank) -> the class skill line it is filed under, and the set of
    // every class skill line the library touches
    std::unordered_map<uint32, uint16> _spellSkillLine;
    std::set<uint16> _classSkillLines;
    std::unordered_map<ObjectGuid::LowType, ClasslessWildcard::CharState> _states;
    bool _libraryBuilt = false;
    bool _applyingGrant = false;
    // true while handing out a form's starter kit, so a kit spell that is
    // itself a form cannot start the whole thing over
    bool _grantingKit = false;
    // true while batch-granting (starting hand, rebirth replay): the client
    // shows those results in bulk, so per-roll reveal popups are suppressed
    bool _revealSuppress = false;

    // Saves and restores rather than clearing: granting a form now grants its
    // starter kit too, so these nest. Clearing on the inner scope's exit would
    // drop _applyingGrant while the outer grant is still running, and the
    // learn-spell hook would take the rest of it for an outside source and
    // revert it.
    struct GrantGuard
    {
        explicit GrantGuard(bool& flag) : _flag(flag), _prev(flag) { _flag = true; }
        ~GrantGuard() { _flag = _prev; }
        bool& _flag;
        bool  _prev;
    };
};

#define sClasslessMgr ClasslessMgr::instance()

#endif
