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
    // `extraScrolls` applies to talents only: each one buys a chance to keep
    // the talent and raise its rank instead of trading it away.
    bool Reroll(Player* player, bool isTalent, uint32 entry, std::string* err,
                uint32 extraScrolls = 0);
    // Reroll every unlocked ability in one pass, from the server's own state.
    // The starting hand used to fire one RR per ability from a client snapshot,
    // which went stale the moment the first one landed. Returns how many were
    // rerolled.
    uint32 RerollUnlockedAbilities(Player* player, std::string* err);
    // Set the padlock outright. A lock is the only promise the Wildcard makes
    // about a roll, so the client says which state it wants rather than asking
    // for a flip: a toggle inverts the two ends for good the moment one of them
    // is out of step, and then the padlock on screen is a lie. Idempotent, and
    // it writes the row every time, so an explicit set also repairs a row that
    // fell out of step with memory.
    bool SetLock(Player* player, uint32 firstSpellId, bool locked, std::string* err);
    bool ToggleLock(Player* player, uint32 firstSpellId, std::string* err);
    // Padlocks exist to hold a card back from the starting hand's "reroll
    // everything" pass. Once free rolls are over that pass is gone and every
    // reroll is one ability the player picked, so a leftover lock protects
    // nothing and only refuses what they asked for. Returns how many it freed.
    uint32 ClearStaleLocks(Player* player);

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
    // Follow an archetype: it replaces the current build and from then on
    // its abilities and talent ranks are bought for the Hero as each one
    // becomes available. Id 0 stops following.
    bool ApplyArchetype(Player* player, uint32 archetypeId, std::string* err);
    std::string ArchetypeName(uint32 archetypeId) const;
    std::string SpellNameOf(uint32 spellId) const;   // rank-1 spell name, for chat lines
    struct FollowResult
    {
        uint32 abilities = 0;
        uint32 talentRanks = 0;
        std::vector<std::string> learned;   // ability names bought now
        std::vector<std::string> stalled;   // unlocked, but not affordable
    };
    // Buy the followed archetype's abilities strictly in build order while
    // each is unlocked and affordable, then its talent ranks in order.
    FollowResult FollowArchetype(Player* player);
    // What the build still has to buy, in order, with each unlock level.
    std::vector<std::pair<uint32, uint8>> ArchetypeQueue(Player* player);
    static uint32 LevelsEarned(uint8 level, uint8 startLevel);
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
    // Riding ranks the Hero has reached the level for. Returns how many were
    // newly taught, so the caller can stay quiet when there is nothing to say.
    uint32 GrantRidingSkill(Player* player);
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
    // A summoned pet outlives the spell that summoned it: losing Summon Imp
    // left the imp standing there for good. Send home anything whose summoning
    // spell the Hero no longer knows. Public because the maintenance tick calls
    // it too: a pet that was temporarily unsummoned (mounted) when its ability
    // went is not standing there to be caught at removal time.
    void DismissOrphanedSummons(Player* player);
    void SaveState(Player* player);          // persist scalar state row
    void AnnounceState(Player* player);      // login summary line
    uint32 AbilityCost(ClasslessWildcard::AbilityEntry const& e) const;
    // A rolled talent can arrive at ANY rank. The rank it lands on decides how
    // rare the find is -- rank 5 is a legendary result -- and since Wildcard
    // rolls cost nothing, a high rank is every one of those ranks for free.
    ClasslessWildcard::Rarity RankRarity(ClasslessWildcard::TalentPoolEntry const& t, uint8 rank) const;
    // Rarity from what an ability DOES, not from when it is learned. See the
    // definition for why each signal is there.
    ClasslessWildcard::Rarity RarityFromPower(uint32 cooldownMs, uint32 talentRow, uint8 level) const;
    // The longest wait on any rank of a line, spell cooldown or category
    // cooldown, whichever the spell actually uses.
    uint32 LineCooldown(ClasslessWildcard::AbilityEntry const& e) const;
    // Weighted pick of a rank above `fromRank`, rarer the higher it goes.
    uint8 RollTalentRank(ClasslessWildcard::TalentPoolEntry const& t, uint8 fromRank) const;
    uint32 RollWeight(ClasslessWildcard::Rarity rarity, uint32 overrideWeight) const;
    uint32 SpentTalentRanksInTab(ClasslessWildcard::CharState const& st, uint32 tabId) const;

private:
    ClasslessMgr() = default;

    // `overridden` collects every first_spell that had a row in
    // cw_ability_override, so later passes can leave a realm's own tuning alone.
    void LoadOverrides(std::unordered_set<uint32>* overridden = nullptr);
    // A variant's rarity is its base's, bumped. Variants are built before
    // overrides are read (so a realm can tune a variant row like any other
    // ability), which means every one of them was derived from its base's
    // heuristic rarity rather than its final one. Put that right.
    uint32 ResyncVariants(std::unordered_set<uint32> const& overridden);
    void LoadFormKits();
    // Elemental variants of pool abilities, from cw_ability_variants. They are
    // module-owned spells with no trainer, so they bypass TrainerTaughtOnly
    // and inherit their base's levels, class mask and spellbook tab.
    void LoadVariants();
    // Which ability lines each talent's spells head or teach (Pyroblast,
    // Mortal Strike, Mangle); taking the talent grants those lines.
    void ResolveTalentAbilityLines();
    bool OwnsReplacedTalent(ClasslessWildcard::CharState const& st, uint32 talentId) const;
    // form id -> the library ability that puts you in it, built from spell data
    void BuildFormSpellMap();
    // Give a Hero the stance or form an ability cannot be used without.
    void GrantRequiredForm(Player* player, ClasslessWildcard::AbilityEntry const& e);
    // Hand over the basic spells that make a freshly gained form or stance
    // usable. Called for every ability grant; does nothing for the vast
    // majority that are not forms.
    void GrantFormKit(Player* player, ClasslessWildcard::AbilityEntry const& form);
    // Is this companion still needed -- a form something owned has to be in,
    // or part of the kit of a form still owned? Only abilities the Hero
    // EARNED count, so two companions can never keep each other alive.
    bool IsCompanionJustified(ClasslessWildcard::CharState const& st,
                              ClasslessWildcard::AbilityEntry const& e) const;
    // Take away the free extras nothing needs any more. Returns how many went.
    uint32 PruneCompanions(Player* player);
    // Hand out any stance or form the Hero's earned abilities require but do
    // not have. Runs at login so a build that predates the form rules is
    // repaired in place.
    void SyncRequiredForms(Player* player);
    // Clear the class tool (totem/relic item) requirement from every library
    // spell -- see Config::ignoreSpellTools.
    void StripSpellTools();
    // The deadline has passed with no path chosen: put the Hero on the realm
    // default and deal a starting hand if that is Wildcard. Returns true if it
    // did anything. Runs at login AND on level-up -- see the comment there.
    bool ApplyDefaultMode(Player* player);
    void LoadCharacter(Player* player, ClasslessWildcard::CharState& st);
    size_t ArchetypeCursor(ClasslessWildcard::CharState const& st, ClasslessWildcard::Archetype const& arch) const;
    void GrantAbilityInternal(Player* player, ClasslessWildcard::AbilityEntry const& e,
                              ClasslessWildcard::GrantSource source, bool persist = true,
                              bool announce = true);
    void RemoveAbilityInternal(Player* player, ClasslessWildcard::AbilityEntry const& e, bool persist = true);
    void GrantTalentRankInternal(Player* player, ClasslessWildcard::TalentPoolEntry const& t, uint8 newRank, bool persist = true);
    void RemoveTalentInternal(Player* player, ClasslessWildcard::TalentPoolEntry const& t, bool persist = true);
    void TickBans(ClasslessWildcard::CharState& st, ObjectGuid guid);
    void SaveBans(ObjectGuid guid, ClasslessWildcard::CharState const& st);
    bool IsBanned(ClasslessWildcard::CharState const& st, bool isTalent, uint32 entry) const;
    // Release every reroll cooldown of one kind. Used when the level-legal pool
    // has been starved by them; returns true if anything was actually freed.
    bool ReleaseCooldowns(ClasslessWildcard::CharState& st, ObjectGuid guid, bool isTalent);
    uint32 OwnedClassMask(ClasslessWildcard::CharState const& st) const;

    void LoadArchetypes();

    std::map<uint32, ClasslessWildcard::AbilityEntry> _abilities;      // firstSpellId -> entry
    std::map<uint32, ClasslessWildcard::TalentPoolEntry> _talents;     // talentId -> entry
    // ability talents taken off the Talents list (ReplaceAbilityTalents):
    // kept aside for prerequisite checks, tree point counts and migration
    std::map<uint32, ClasslessWildcard::TalentPoolEntry> _replacedTalents;
    std::map<uint32, ClasslessWildcard::Archetype> _archetypes;
    std::unordered_map<uint32, uint32> _spellToFirst;                  // any rank -> firstSpellId
    // form/stance spell (any rank) -> the basic spells that come with it
    std::unordered_map<uint32, std::vector<uint32>> _formKits;
    // shapeshift form id -> the RANK spell that grants that form. Not the
    // first rank: Dire Bear Form is rank 2 of Bear Form and grants a
    // different form id, so the line alone cannot answer which is which.
    std::unordered_map<uint32, uint32> _formSpells;
    // spell (any rank) -> the class skill line it is filed under, and the set of
    // every class skill line the library touches
    std::unordered_map<uint32, uint16> _spellSkillLine;
    // Class spells the core hands out WITH their skill line, which is what
    // Player::learnSkillRewardedSpells teaches whenever a line is added.
    // The strip needs these by id whether or not the library kept them.
    std::unordered_set<uint32> _skillLearnedClassSpells;
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
