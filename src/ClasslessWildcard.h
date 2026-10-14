/*
 * mod-classless-wildcard
 *
 * Ascension-style classless system + Season 10 "Wildcard" mode for AzerothCore.
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

#ifndef MOD_CLASSLESS_WILDCARD_H
#define MOD_CLASSLESS_WILDCARD_H

#include "Define.h"
#include "ObjectGuid.h"
#include "StringConvert.h"
#include "UnitDefines.h"
#include <algorithm>
#include <array>
#include <string_view>
#include <type_traits>
#include <map>
#include <set>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

class Player;

namespace ClasslessWildcard
{
    // Wand shots and their damage school.
    //
    // The core gives a wand shot the wand's own school (Fire, Shadow, ...)
    // only for Priest, Mage and Warlock, by raw class mask, so a Hero's wand
    // fires as Physical and armour cuts it. Spell::m_spellSchoolMask is
    // protected, so a module cannot correct it. The fix belongs in the core:
    // route that check through IsClass with CLASS_CONTEXT_WAND_SCHOOL, which
    // the module's OnPlayerIsClass then answers for every Hero.
    //
    // Until a core carries that context this compiles to false and the module
    // still builds; once it does, wand shots take their school with no edit
    // here. The detection is by name, so it must match the core's enumerator.
    template <typename E, typename = void>
    struct HasWandSchoolContext : std::false_type { };
    template <typename E>
    struct HasWandSchoolContext<E, std::void_t<decltype(E::CLASS_CONTEXT_WAND_SCHOOL)>> : std::true_type { };

    constexpr bool CoreHasWandSchoolContext = HasWandSchoolContext<ClassContext>::value;

    template <typename E>
    constexpr bool IsWandSchoolContext(E context)
    {
        if constexpr (HasWandSchoolContext<E>::value)
            return context == E::CLASS_CONTEXT_WAND_SCHOOL;
        else
            return false;
    }

    // implemented in ClasslessAddon.cpp: raw push to the client addon
    // (used e.g. for "RV|..." roll-reveal notifications)
    void PushAddon(Player* player, std::string const& body);

    // Re-send the SC records: what a spell really costs, casts and cooldowns
    // for once the Hero's talents are counted. The client cannot work these
    // out itself for a talent outside its own class, so a build change that
    // the addon did not ask for has to say so, or the tooltip keeps the old
    // numbers until the next login.
    void PushSpellCorrections(Player* player);

    // The starting hand is four cards. The client addon draws exactly four and
    // the config is clamped to it, so the two can never disagree.
    constexpr uint32 MAX_STARTING_HAND = 4;
    // The forged spells' own skill line. No class learns it and its rows say
    // AcquireMethod 0, so only SyncSpellbookTabs ever hands the skill out; the
    // client files the spells under General without it. Must equal HERO_LINE in
    // data/sql/generators/gen_forged_spells.py; test_forged.py checks.
    constexpr uint32 HERO_SKILL_LINE = 990;

    // Runeforging: the skill line, and the trade skill that opens the forge
    // window. SkillRaceClassInfo.dbc lists line 776 for class mask 0x20 alone,
    // so Player::LearnDefaultSkill hands the skill to no other chassis and the
    // module sets it directly. See GrantRuneforging.
    constexpr uint32 RUNEFORGING_SKILL_LINE = 776;
    // Every mount a character owns sits on this one line, and none of them is
    // earned through the library. SetSkill unlearns every spell on a line it
    // removes, so this line must never be removed.
    constexpr uint32 MOUNTS_SKILL_LINE = 777;
    constexpr uint32 RUNEFORGING_SPELL = 53428;

    enum class Mode : uint8
    {
        Classless = 0,  // free-pick with essences
        Wildcard  = 1,  // random rolls
        Unchosen  = 255
    };

    enum class Rarity : uint8
    {
        Common    = 0,
        Uncommon  = 1,
        Rare      = 2,
        Epic      = 3,
        Legendary = 4,
        Max       = 5
    };

    enum class GrantSource : uint8
    {
        Picked    = 0,   // bought with essence (classless mode)
        Rolled    = 1,   // wildcard random roll
        Talent    = 2,   // handed over by an ability talent; leaves with it
        // came free with another ability: the stance an ability cannot be used
        // without, or the starter kit an ability arrives with (a form's basic
        // attacks, Tame Beast's pet handling). It is not part of the starting
        // hand, it cannot be rerolled on its own, and it leaves when nothing
        // the Hero earned needs it any more.
        Companion = 3,
        // carried through a Rebirth. Owned like a pick, but it survives the
        // wipe, is usable from level 1 (rank 1 is always learned), and is
        // never rerolled or refunded. How many a Hero may carry is one more
        // than the Rebirths already behind them.
        Heirloom  = 4
    };

    // What an ability is for, from its rank-1 spell: the browser sorts and
    // filters on it. Heals are checked first (a healing spell has a magic
    // damage class too), then the spell's own damage class.
    enum class AbilityType : uint8
    {
        Utility = 0,   // buffs, forms, stances, totems, control
        Melee   = 1,
        Ranged  = 2,
        Spell   = 3,
        Heal    = 4,
        Passive = 5
    };

    // One entry of the ability library: a spell line (first rank) + all its ranks.
    struct AbilityEntry
    {
        uint32 firstSpellId = 0;
        std::string name;               // rank-1 spell name (dedupe + owned-name checks)
        std::vector<uint32> ranks;      // rank spell ids in order, [0] == firstSpellId
        std::vector<uint8>  rankLevels; // required level per rank
        uint32 classMask = 0;           // origin class(es)
        Rarity rarity = Rarity::Common;
        uint32 cost = 1;                // ability essence cost (classless mode)
        uint32 weight = 100;            // wildcard roll weight
        bool   enabled = true;
        bool   passive = false;
        bool   variant = false;         // an elemental variant (cw_ability_variants)
        bool   forged = false;          // a Hero-line spell (cw_forged_spells): owned by no
                                        // class, so it browses under Hero rather than under
                                        // all eleven at once
        uint32 variantBase = 0;         // and the line it varies, so its rarity can be
                                        // re-derived once overrides have touched the base
        AbilityType type = AbilityType::Utility;
    };

    // One entry of the talent pool.
    struct TalentPoolEntry
    {
        uint32 talentId = 0;
        uint32 tabId = 0;
        uint32 classMask = 0;           // from TalentTab
        uint32 row = 0;
        uint32 col = 0;
        uint32 dependsOn = 0;           // prerequisite talent id (0 = none)
        uint32 dependsOnRank = 0;
        std::array<uint32, 5> rankSpells = { 0, 0, 0, 0, 0 };
        uint8  maxRank = 0;
        Rarity rarity = Rarity::Common;
        uint32 weight = 100;
        bool   enabled = true;
        // ability lines (first spell ids) a rank spell heads or teaches; the
        // talent grants them outright so the spell ranks up with level
        std::vector<uint32> abilityLines;
    };

    struct OwnedAbility
    {
        GrantSource source = GrantSource::Picked;
        bool locked = false;
    };

    // ---- challenge runs ----------------------------------------------------
    // A run is a Wildcard life lived under one rule with a fixed number of
    // lives. The rules are code; this is only what the server needs to tell
    // one from another and to tell the client about it.
    enum class ChallengeId : uint8
    {
        None = 0,
        Nemesis = 1, EliteWorld = 2, Hardcore = 3, Pursued = 4, Glass = 5,
        // 6 to 13 were Borrowed Time, Bare Shoulders, Silent, One Pool,
        // Wildfire, Ironborn, Pacifist Opening and Famine: cut before release,
        // rules that took something away instead of changing the fight
        Legion = 14, Hourglass = 15, Spiteful = 16, Bloodpact = 17,
        Berserker = 18, Ironman = 19, BigGameHunter = 20, DealtHand = 21
    };
    // A run's lives when it has no limit: a death never ends it. The state
    // and the client carry this number for both lives and lives at the start.
    constexpr uint8 UNLIMITED_LIVES = 255;

    struct Challenge
    {
        uint8 id;
        char const* key;
        char const* name;
        uint8 lives;            // UNLIMITED_LIVES: a death never ends the run
        char const* rule;       // player-facing, one sentence or two; no ':' or ';' (the addon splits on them)
        uint32 rewardGold;      // paid once, on finishing
        uint32 titleId;         // CharTitles.dbc, on finishing (0 = none)
        char const* rewardRecipe;   // a forged line flagged `reward`, granted as an heirloom ("" = none)
        char const* detail;     // how the rule plays, in full, for the challenge page (no '|')
        char const* tips;       // practical advice for playing under this rule (no '|')
        // The path a character must already walk to start it (a Mode value),
        // or Unchosen for either. A run never sets or changes a path.
        Mode path = Mode::Unchosen;
    };
    // Nemesis: a creature kind that has killed this Hero, how much it grew,
    // and the experience it took, which comes back when one of them dies.
    // A nemesis is Marked (it killed the Hero) or Sworn (the Hero swore
    // vendetta on it), and carries up to three strengths and one weakness
    // (PLAN-nemesis.md, sections 2 and 4).
    enum NemesisKind : uint8 { NEMESIS_MARKED = 0, NEMESIS_SWORN = 1 };
    enum NemesisStrength : uint8
    {
        NS_NONE = 0, NS_BLOODLUST, NS_IRONHIDE, NS_SPELLWARD, NS_VENOMOUS, NS_UNYIELDING, NS_WARBAND,
        NS_RELENTLESS, NS_COUNT
    };
    enum NemesisWeakness : uint8
    {
        NW_NONE = 0, NW_FIRE, NW_FROST, NW_SHADOW, NW_NATURE, NW_ARCANE, NW_HOLY, NW_BRITTLE, NW_COWARDLY, NW_COUNT
    };
    // what its Hero has found out about it
    enum : uint8 { NEMESIS_LEARNED_STRENGTHS = 0x1, NEMESIS_LEARNED_WEAKNESS = 0x2 };
    constexpr uint8 NEMESIS_MAX_STRENGTHS = 3;

    struct NemesisMark
    {
        uint32 entry = 0;     // what kind it is: its name
        uint8 levels = 0;     // how far above its Hero it fights
        uint8 kills = 0;      // how often it has killed its Hero
        uint32 stolen = 0;    // experience taken by a mark from before deaths stopped taking any
        uint8 kind = NEMESIS_MARKED;
        uint8 strengths[NEMESIS_MAX_STRENGTHS] = { NS_NONE, NS_NONE, NS_NONE };
        uint8 weakness = NW_NONE;
        uint8 learned = 0;
        uint32 zone = 0;      // runtime: the zone it lives in, once its Hero has been on its map

        bool Has(uint8 strength) const
        {
            for (uint8 s : strengths)
                if (s == strength)
                    return true;
            return false;
        }
        uint8 StrengthCount() const
        {
            uint8 n = 0;
            for (uint8 s : strengths)
                if (s != NS_NONE)
                    ++n;
            return n;
        }
    };

    struct RollBan
    {
        uint32 entry = 0;
        bool   isTalent = false;
        int32  rollsLeft = 0;
    };

    // Pre-built starter builds for onboarding (Ascension's "archetypes").
    struct Archetype
    {
        uint32 id = 0;
        std::string name;
        std::string description;
        std::vector<uint32> abilities;                    // first-rank spell ids
        // talentId -> rank. A talent can be listed once per rank, each entry
        // for a higher rank than the one before it, so each rank has a level
        // of its own; an entry for rank 3 alone buys ranks 1 to 3.
        std::vector<std::pair<uint32, uint8>> talents;
        // The level the build holds each entry back to, by index into the
        // list beside it: 0 is "as soon as it unlocks and is affordable". A
        // held entry waits the way one that has not unlocked does, so the
        // entries behind it wait too; a build lists them in the order of the
        // levels they are bought at. Shorter than its list (or empty) means
        // nothing is held past the end.
        std::vector<uint8> abilityWait;
        std::vector<uint8> talentWait;

        uint8 AbilityWait(size_t i) const { return i < abilityWait.size() ? abilityWait[i] : 0; }
        // How many talent ranks the build takes: each talent's highest rank,
        // counted once however many entries it has.
        uint32 TalentRanks() const
        {
            std::map<uint32, uint8> top;
            for (auto const& [id, rank] : talents)
                top[id] = std::max(top[id], rank);
            uint32 n = 0;
            for (auto const& [id, rank] : top)
                n += rank;
            return n;
        }
        uint8 TalentWait(size_t i) const { return i < talentWait.size() ? talentWait[i] : 0; }
        void AddAbility(uint32 id, uint8 wait)
        {
            abilityWait.resize(abilities.size(), 0);
            abilities.push_back(id);
            abilityWait.push_back(wait);
        }
        void AddTalent(uint32 id, uint8 rank, uint8 wait)
        {
            talentWait.resize(talents.size(), 0);
            talents.emplace_back(id, rank);
            talentWait.push_back(wait);
        }
    };

    // A build entry as text, the way the addon uploads it and the characters
    // database stores it: "id" or "id@level" for an ability, "id:rank" or
    // "id:rank@level" for a talent. The level is the one it is held back to.
    inline bool ParseAbilityEntry(std::string_view tok, uint32& id, uint8& wait)
    {
        wait = 0;
        size_t const at = tok.find('@');
        Optional<uint32> v = Acore::StringTo<uint32>(tok.substr(0, at));
        if (!v)
            return false;
        id = *v;
        if (at != std::string_view::npos)
            if (Optional<uint32> w = Acore::StringTo<uint32>(tok.substr(at + 1)))
                wait = uint8(std::min<uint32>(*w, 255));
        return true;
    }

    inline bool ParseTalentEntry(std::string_view tok, uint32& id, uint32& rank, uint8& wait)
    {
        wait = 0;
        size_t const at = tok.find('@');
        std::string_view const head = tok.substr(0, at);
        size_t const colon = head.find(':');
        if (colon == std::string_view::npos)
            return false;
        Optional<uint32> v = Acore::StringTo<uint32>(head.substr(0, colon));
        Optional<uint32> r = Acore::StringTo<uint32>(head.substr(colon + 1));
        if (!v || !r)
            return false;
        id = *v;
        rank = *r;
        if (at != std::string_view::npos)
            if (Optional<uint32> w = Acore::StringTo<uint32>(tok.substr(at + 1)))
                wait = uint8(std::min<uint32>(*w, 255));
        return true;
    }

    // CharState::archetype when the character follows its own build, held in
    // CharState::custom and cw_char_custom_archetype rather than cw_archetypes.
    constexpr uint32 CUSTOM_ARCHETYPE = 0xFFFFFFFF;
    // the most entries a custom build may list, far past any real build
    constexpr size_t CUSTOM_ARCHETYPE_MAX = 200;
    constexpr size_t CUSTOM_ARCHETYPE_NAME_MAX = 32;

    // Per-character runtime state (mirrored to characters DB).
    struct CharState
    {
        Mode   mode = Mode::Unchosen;
        uint32 abilityEssence = 0;
        uint32 talentEssence = 0;
        uint32 pity = 0;                 // rerolls since last synergy roll
        // One pool of earned reroll charges, spent on abilities OR talents --
        // two separate pools just made the UI read as three confusing numbers.
        uint32 rerolls = 0;
        uint8  lastProcessedLevel = 0;
        uint32 archetype = 0;            // cw_archetypes.id the Hero follows (0 = none, CUSTOM_ARCHETYPE = `custom`)
        Archetype custom;                // the character's own build, when it follows one (id CUSTOM_ARCHETYPE)
        Archetype upload;                // runtime: a build the addon is sending in pieces (ARCHUP)
        // Rebirths completed: the New Game Plus rank. Each one is a run from
        // 1 to the cap, and the rank sets the XP rate, the stat bonus, the
        // heirloom count and the legacy essence of every run after it.
        uint32 rebirths = 0;
        int32  appliedRebirthPct = 0;    // stat percent currently applied, runtime only

        // The challenge run, if one is live (ChallengeId, 0 = none), its lives,
        // what the live rule remembers (One Pool's bar, Borrowed Time's levels
        // left), the shards runs have paid, and a life bought for the next run.
        uint8  run = 0;
        uint8  lives = 0;
        uint8  livesMax = 0;
        uint32 runData = 0;
        uint32 shards = 0;
        uint8  extraLife = 0;
        std::unordered_map<uint32, NemesisMark> nemeses;  // by spawn id: the one creature that killed you
        uint32 nemesisOldXp = 0;         // experience held by marks saved per kind, before marks were per creature
        std::string nemesisGuidsSent;    // runtime: the nemesis GUIDs the addon was last sent ("NG")
        std::unordered_map<uint32, ObjectGuid> nemesisCopies;   // runtime: spawn id -> this Hero's copy of it
        uint32 nemesisVengeance = 0;                  // the run's Vengeance: levels of nemeses slain
        uint8 charmRanks[NS_COUNT] = {};              // the Nemesis Charm's rank in each effect, 0 to 5
        std::vector<uint32> nemesisPendingTrophies;   // trophies waiting for room among the four
        float nemesisFxApplied[NS_COUNT] = {};        // runtime: each effect's value as applied
        int32 nemesisCritRatingApplied = 0;           // runtime: the crit rating that value came to
        int32 nemesisSpellPowerApplied = 0;           // runtime: the spell power the power effect came to
        bool nemesisCharmMailed = false;              // runtime: a charm that found the bags full was mailed
        std::string nemesisListSent;                  // runtime: the nemesis list the addon was last sent
        std::set<uint32> nemesisHeads;   // heads from before Vengeance, read once and turned into it
        std::unordered_map<uint8, std::pair<uint8, bool>> runBest;  // challenge -> (level reached, finished)
        uint32 hunterTimerMs = 0;        // runtime: Pursued's clock
        uint32 ruleTickMs = 0;           // runtime: the five-second rule tick
        uint8  trackerTicks = 0;         // runtime: rule ticks since the tracker was last sent
        bool   trackerPaused = false;    // runtime: whether the last tracker sent was paused
        ObjectGuid hunterGuid;           // runtime: the hunter out now, if any

        // which resource bar the default unit frame displays
        // (0 mana, 1 rage, 3 energy, 255 = chassis default)
        uint8  displayPower = 255;

        // primary stat allocation (points per stat: STR, AGI, STA, INT, SPI)
        std::array<uint32, 5> statAlloc = { 0, 0, 0, 0, 0 };
        std::array<int32, 5>  appliedStatBonus = { 0, 0, 0, 0, 0 }; // currently applied, runtime only

        // universal stat layer bonuses currently applied (runtime only)
        int32 usMeleeAP = 0;
        int32 usRangedAP = 0;
        int32 usSpellPower = 0;

        // last combo-point count mirrored to the addon (runtime only; 255 =
        // nothing pushed yet, so the first update always syncs)
        uint8 lastComboPush = 255;

        // The spell modifier totals this client was last told, keyed by
        // ClientSpellModKey, and whether a resync is already on its way.
        // Runtime only; see ClasslessMgr::SyncClientSpellMods.
        std::unordered_map<uint32, int32> clientSpellMods;
        bool clientSpellModSyncQueued = false;

        // The shapeshift form this Hero was last seen holding, kept by
        // ClasslessFormScript so a form that is being LEFT can still be named
        // after the core has already reset it to none. Runtime only.
        uint8 heldForm = 0;

        std::unordered_map<uint32 /*firstSpellId*/, OwnedAbility> abilities;
        std::unordered_map<uint32 /*talentId*/, uint8 /*rank*/>   talents;
        std::vector<RollBan>   bans;
        bool exempt = false;   // bot/system account: classless rules don't apply
        // Did this character load WITH a rune block? Player::InitRunes runs
        // once, at load, and the rune accessors dereference that block with no
        // null check -- so whether a Hero "is a Death Knight" for rune purposes
        // has to stay fixed for the session. Reading the live config instead
        // would let a `.reload config` turn the per-tick rune loop on for
        // characters InitRunes had already skipped, and read a null block.
        // Heroes only: an exempt character's rune question goes to the core,
        // which answers from its real class.
        bool runes = false;
        // Last rune state pushed to the addon: which runes are up and what
        // type they are, NOT how many milliseconds are left, because cooldowns
        // tick every frame and keying on the raw numbers would send a message
        // per tick. 0xFFFFFFFF is "nothing pushed yet".
        uint32 lastRuneSig = 0xFFFFFFFF;
        // Runic power is tracked separately and in twentieths, because it is
        // the one part that moves continuously. A rune coming up redraws at
        // once; runic power drifting on its own redraws at most once a second,
        // which is smooth enough for a bar and stops it dominating the traffic.
        uint8  lastRunicBucket = 255;
        uint32 runeAcc = 0;
        // Which runes were up last tick, one bit per rune. Starts all up,
        // which is how InitRunes leaves the block and how the client starts.
        uint8  lastReadyRunes = 0x3F;
        // Does this character own anything that SPENDS runes or runic power?
        // The six rune pips and the runic bar are the tallest thing on the
        // resource frame, and a Hero who has bought no Death Knight ability has
        // no use for either. -1 is "not worked out yet"; the answer is
        // recomputed at most once a second from the owned ability list.
        int8   lastRuneOwn = -1;
        uint32 runeOwnAcc = 0;

        // The 2-second tick the periodic work in OnPlayerUpdate runs on.
        //
        // This lived in an unordered_map on the script, keyed by guid, and
        // OnPlayerUpdate reached it with operator[] -- an INSERT, for every
        // player on every map update, from whichever map thread got there.
        // Maps update in parallel, so two of them rehashed the same container
        // at once and the server came down inside _Try_emplace under
        // Map::Update. Per-player state belongs on the per-player state, where
        // only that player's map thread can reach it.
        uint32 tickAcc = 0;

        // A Hero driven by mod-playerbots (an altbot). The role ClasslessBots
        // last put on the bot, and the one its owner chose with
        // `co +classless <role>`, which outlives playerbots' strategy resets.
        // 0 is none; otherwise a ClasslessBots role. Runtime only.
        uint8 botRole = 0;
        uint8 botRoleOverride = 0;

        // The player asked not to be taught Auto Shot (Settings). Saved.
        bool noAutoShot = false;
        // A ranged-slot change has queued SyncAutoShot for the next tick, so
        // a bow-to-gun swap (one removal, one equip) is one sync, not an
        // unlearn and a relearn. Runtime only.
        bool autoShotSyncPending = false;
        // When the open Overpower window closes, in game-time ms; 0 when shut.
        // A later dodge pushes it out, so the timer that closes it checks this
        // rather than closing a window a newer dodge reopened. Runtime only.
        uint32 overpowerUntil = 0;

        // The armor weight amounts last sent to the addon ("AW|..."), so the
        // 2-second tick only sends when they change. Runtime only.
        std::string armorWeightSent;

        bool loaded = false;
    };

    struct Config
    {
        bool   enabled = true;
        bool   announce = true;
        uint8  defaultMode = 0;
        bool   allowModeChoice = true;
        uint8  modeChoiceDeadline = 2;

        // library filters
        bool   includeDeathKnight = true;
        // A talent that teaches a spell the ability pool already carries
        // (Pyroblast, Mortal Strike, Mangle) leaves the Talents list; the
        // ability line stands in for it, and owning the ability meets any
        // prerequisite on the talent and counts as a point in its tree.
        bool   includeRacials = false;
        bool   includePassives = true;
        std::unordered_set<uint32> excludedSpells;

        // tiered acquisition: rolls/purchases respect each spell's own level
        // requirement (rank 1 learn level) and each talent's tree-row level,
        // so low levels can't be dealt end-game spells
        bool   respectLevelReqs = true;

        // only spells players actually learn (starter spells + class trainer
        // lists) enter the library; also sources each rank's REAL learn level
        // from trainer data. Kills NPC/pet variants like "Demonic Immolate".
        bool   trainerTaughtOnly = true;

        // proficiencies
        bool   teachProficiencies = true;
        bool   armorWeight = true;      // ArmorWeight.Enable: each armor type's aura
        // ArmorWeight.<Armor>.<Effect>: full-set values set in the conf, by
        // key ("Plate.CastSpeed"). A key left empty is absent here, and the
        // aura's own spell row decides.
        std::map<std::string, int32> armorWeightValues;
        std::vector<uint32> proficiencySpells;

        // clean-slate start: strip the chassis class's default spells at
        // creation and hand out the neutral Hero kit instead
        bool   starterKitEnable = true;
        // strip EVERY piece of default gear the shell class was created with,
        // so the Hero starts bare and the kit armour actually equips (the old
        // "replace weapons only" left the shell's shirt/pants/boots on, so the
        // kit armour fell through to the bags)
        bool   starterKitStripEquipped = true;
        uint32 starterKitBag = 5573;   // an 8-slot bag equipped at creation (0 = none)
        // Riding is not class power, so it is not in the classless library and
        // never rolls: it is simply given. Each pair is a spell and the level
        // it arrives at, which by default is the level its trainer would sell
        // it. The spells themselves carry NO level of their own (all five read
        // SpellLevel 0), so this list is the only gate there is.
        // What a hunter pet needs in order to be out. Only used as a fallback
        // for a beast whose UNIT_CREATED_BY_SPELL is zero (older data, a GM
        // spawn); a normally tamed one records the spell itself.
        uint32 callPetSpell = 883;

        bool ridingEnable = true;
        std::vector<std::pair<uint32, uint32>> ridingGrants;

        // Runeforging is not class power either. The runes are weapon
        // enchants handed out as recipes: the forge window lists them instead
        // of the spellbook, they are castable only through Runeforging, and
        // the one trainer that sells them checks the customer's class. Same
        // shape as Riding.Grants, at the levels that trainer uses.
        bool runeforgingEnable = true;
        std::vector<std::pair<uint32, uint32>> runeforgingGrants;

        std::vector<std::pair<uint32, uint32>> starterKitItems;  // into bags
        std::vector<std::pair<uint32, uint32>> starterKitEquip;  // auto-equipped (armour)

        // accounts whose name starts with one of these prefixes play VANILLA
        // rules (no essences/rolls, native talents, trainers work) — for
        // playerbots' random-bot accounts and similar system accounts
        std::vector<std::string> exemptAccountPrefixes;

        // native talent suppression

        // revert class-library spells learned outside the module (class
        // trainers, quest rewards) so essence/rolls stay the only path

        // A shapeshift form or a warrior stance is useless on its own: a Hero
        // who draws Bear Form and nothing else cannot attack in it. Gaining one
        // hands over the basic kit that goes with it (Maul, Demoralizing Roar),
        // free, so it is usable the moment it lands. The pairs live in the
        // `cw_form_kits` table.
        // Answer the core's "is this player a <class>?" questions as YES for the
        // contexts where classless means every class at once: equipping any
        // relic, shields, and the reactive-ability aura states. Off = the
        // chassis class decides, which is the stock behaviour.

        // Spellbook tabs. The client files a spell under a tab by its skill
        // line, and only for skill lines the character HAS -- so a Hero saw one
        // tab for the chassis class and everything else dumped in General.
        //   0 = off (stock behaviour)
        //   1 = a tab for every skill line the Hero owns spells in
        //   2 = a tab for every class skill line, present from the start

        bool   formKitsEnable = true;

        // Some spells ask for a class tool: Stoneskin Totem needs an Earth
        // Totem, Runeforging needs a runeforge. A Hero owns spells from every
        // class and is handed no class's tools, so the requirement comes off
        // every spell in the library. Reagents are untouched.

        // elemental ability variants (cw_ability_variants, generated): a
        // variant is registered one rarity tier above its base
        bool   elementalEnable = true;
        bool   forgedEnable = true;           // the Hero line's own spells
        uint32 elementalRarityBump = 1;
        uint32 elementalRollWeightPct = 8;    // of the rarity weight, per variant
        bool   elementalInPool = true;        // rolled and buyable; off = owned ones keep working
        bool   elementalShowInBrowser = true; // listed in the addon's class menus and the NPC

        // Classless gear as world drops. The catalogue was vendor-only, which
        // made the Hero Advancement NPC the only answer to "where does gear
        // come from". Any mob can now drop a piece banded to ITS level, so a
        // level 20 zone yields level 20 gear whoever kills there. Heirlooms are
        // the premium reward and come only off rares and bosses.
        bool   worldDropEnable = true;
        float  worldDropChance = 1.0f;           // percent, per qualifying kill
        float  worldDropRareMultiplier = 5.0f;   // rares/elites/bosses drop more often
        float  worldDropHeirloomChance = 2.0f;   // percent, rares and bosses only

        // Nemesis (PLAN-nemesis.md): how far above the Hero a Marked nemesis
        // fights, and the experience its kill pays on top, in percent of the
        // Hero's current level
        uint32 nemesisMarkedLevels = 2;
        uint32 nemesisMarkedBonusXpPct = 25;
        // Sworn: Swear Vendetta's nemesis
        uint32 nemesisSwornLevels = 4;
        uint32 nemesisSwornBonusXpPct = 50;
        uint32 nemesisSwornCooldownMin = 30;
        // traits, in percent
        uint32 nemesisBloodlustPct = 30;      // faster attacks and casts
        uint32 nemesisIronhidePct = 25;       // less physical damage taken
        uint32 nemesisSpellwardPct = 25;      // less spell damage taken
        uint32 nemesisVenomousPct = 2;        // of the Hero's health, every 2 seconds for 6
        uint32 nemesisUnyieldingPct = 25;     // more damage below 30% health
        uint32 nemesisRelentlessPct = 5;      // health a second, out of combat
        uint32 nemesisWeakSchoolPct = 50;     // more damage from its weak school
        uint32 nemesisBrittlePct = 20;        // more damage for 8 seconds after a stun
        uint32 nemesisCowardlyPct = 30;       // more damage once it has fled
        uint32 nemesisWarbandCount = 2;       // its kind called to its side
        uint32 nemesisVenomousSeconds = 6;    // how long its poison lasts
        uint32 nemesisUnyieldingBelowPct = 30;   // its health when its rage starts
        uint32 nemesisBrittleSeconds = 8;     // how long a stun opens it up
        uint32 nemesisCowardlyFleePct = 20;   // its health when it flees
        uint32 nemesisCowardlyFleeSeconds = 6;
        // Vengeance and trophies (PLAN-nemesis.md section 6)
        uint32 nemesisVengeanceToFinish = 500;
        uint32 nemesisSwornVengeancePct = 150;   // a Sworn kill's Vengeance, in percent of its level
        uint32 nemesisTrophyMax = 4;             // trophies carried at once
        // what one star is worth, in each trophy effect, indexed by NemesisStrength
        float nemesisStar[NS_COUNT] = { 0.0f, 0.8f, 2.0f, 6.0f, 0.4f, 1.2f, 1.2f, 0.8f };

        // classless (free-pick) economy
        uint32 startingAbilityEssence = 3;
        uint8  essenceStartLevel = 4;          // ability essence income starts here
        uint8  talentEssenceStartLevel = 10;   // talent essence income starts here
        uint32 abilityEssencePerLevel = 1;
        uint32 talentEssencePerLevel = 1;
        std::array<uint32, 5> abilityCostByRarity = { 1, 2, 3, 5, 8 };
        uint32 talentCostPerRank = 1;
        // Optional: charge only the FIRST rank, making a talent cost one point
        // however far it is ranked. Off by default -- in Classless you choose
        // what you buy, so each rank is paid for. (The "rank 5 for one point"
        // rule belongs to Wildcard, where the roll hands you the rank free.)
        bool   talentFlatCost = false;
        bool   refundOnUnlearn = true;

        // wildcard
        uint32 wcStartingAbilities = 4;
        uint8  wcRollStartLevel = 10;
        uint32 wcTalentEveryLevels = 2;
        uint32 wcAbilityEveryLevels = 2;
        uint8  wcFreeRerollLevel = 10;   // below this, rerolls are free
        // How an ability's rarity is worked out when nothing overrides it.
        // Rarity is what a roll is WORTH, so the strongest of three signals
        // wins: the wait the game puts on it, the talent row that teaches it,
        // and -- only as a floor, and never past rare -- the level it is
        // learned at. Thresholds for uncommon, rare, epic, legendary in order.
        std::array<uint32, 4> rarityCooldownMs = { 30000, 60000, 180000, 600000 };
        std::array<uint32, 4> rarityTalentRow = { 2, 4, 6, 8 };
        std::array<uint32, 2> rarityLevel = { 25, 50 };   // uncommon, rare. no higher

        std::array<uint32, 5> wcRarityWeights = { 100, 85, 65, 45, 25 };
        // Weight per talent RANK, rank 1 first. Separate from the rarity
        // weights above because the two do different jobs: rarity decides
        // which talent, rank decides how much of it you get in one roll, and
        // a rank is worth a whole point where a rarity is only flavour.
        std::array<uint32, 5> wcTalentRankWeights = { 100, 75, 50, 25, 10 };
        // Rerolling a talent trades it away for a new one. Extra scrolls buy a
        // chance to keep it and raise its rank instead, so a Hero can either
        // widen the build or deepen it.
        uint32 wcTalentUpgradeBase = 0;         // percent with no extra scroll
        uint32 wcTalentUpgradePerScroll = 20;   // percentage points each
        uint32 wcTalentUpgradeMaxScrolls = 5;
        uint32 wcSynergyBaseChance = 10;   // percent
        uint32 wcSynergyIncrement = 10;    // percent per pity point
        uint32 wcSynergyBanRolls = 25;
        uint32 wcScrollItemId = 990101;        // Reroll Scroll (top-up item)
        uint32 wcTalentRollOffset = 1;         // phase, so talents land between ability rolls
        uint32 wcRerollsPerLevel = 3;          // earned reroll charges per level, from RollStartLevel
        uint32 wcFreeScrollEveryLevels = 0;    // optional extra: scrolls every N levels (0 = off)
        uint32 wcFreeScrollCount = 1;          // scrolls granted per milestone
        uint32 wcScrollBuyEnable = 1;          // allow buying scrolls from the addon panel
        uint32 wcScrollBuyBaseCopper = 500;    // base price of a Scroll of Fortune, in copper
        uint32 wcScrollBuyPerLevelCopper = 500;// added copper per character level (silver early, gold at cap)

        // SINGLE CHASSIS
        //
        // Every Hero is forced onto one class, whatever the creation screen
        // sent. This is the whole point: as long as characters keep different
        // classes, the core's own per-class math differs between them — base
        // stats, base health and mana, which stat converts into attack power —
        // and "roll a mana class if you want to cast" creeps back in. One
        // chassis makes that math identical by construction rather than by
        // correction, so the class you picked is purely cosmetic.
        //
        // The chassis is Paladin, and it must be a mana class. Paladin has a
        // real mana pool with proper base mana (so %-of-base-mana spell costs
        // work) and spirit regen, and no forms, stances or runes to suppress.
        // Rage and energy are layered on top by the universal-resource code
        // below. A rage or energy chassis is refused at load: mana is never
        // synthesised, so such a Hero could not pay for a single mana spell.
        uint8  chassisClass = 2;          // CLASS_PALADIN

        // Universal resources: every Hero maintains mana, rage AND energy pools
        // simultaneously (druid-style: the client tracks all pools, only the
        // chassis bar is displayed and the addon shows the others).
        //
        // There is no switch for this and there must not be. A Hero rolls
        // abilities from every class, so without the off-chassis pools every
        // rage and energy ability they own is uncastable -- which is most of a
        // classless build. Only the numbers below are tunable.
        uint32 urMaxRage = 1000;           // internal units (1000 = 100 rage)
        uint32 urMaxEnergy = 100;

        // Universal stat layer: fills the gaps the chassis math leaves so EVERY
        // stat is worth allocating on a classless Hero:
        //   AGI -> melee + ranged attack power, INT -> spell power,
        //   SPI -> mana regen (above). STR/STA already work via the core.
        // Because every Hero shares one chassis, these apply identically to
        // everyone -- there is no class whose native conversions make it a
        // better caster or a better melee.
        //
        // Also not switchable: the stat allocation screen invites a Hero to
        // spend points on Agility and Intellect, and on the Paladin chassis
        // those do almost nothing without this. Only the rates are tunable.
        float  usMeleeAPPerAgi = 1.0f;
        float  usRangedAPPerAgi = 1.0f;
        float  usSpellPowerPerInt = 0.5f;  // per Intellect point above 10

        // primary stat allocation
        bool   statsEnable = true;
        uint32 statStartingPoints = 4;
        uint32 statPointsPerLevel = 2;
        uint32 statValuePerPoint = 1;      // stat granted per point

        // Rebirth: New Game Plus. At the level cap a Hero starts over at 1
        // with the quest log forgotten, keeps gold, bags, reputation, riding
        // and flight paths, and carries a permanent rank that stacks.
        bool   rebirthEnable = true;
        uint32 rebirthCostGold = 100;      // a Rebirth costs this x (rank + 1)
        uint32 rebirthKillXpFirst = 100;   // percent extra kill and dungeon XP at rank 1
        uint32 rebirthKillXpPerRank = 50;  // added for every rank after the first
        uint32 rebirthKillXpMax = 300;     // cap
        uint32 rebirthOtherXpPerRank = 25; // quest, exploration and battleground XP, per rank
        uint32 rebirthOtherXpMax = 100;    // cap
        uint32 rebirthStatPctPerRank = 3;  // all five primary stats, per rank
        uint32 rebirthStatPctMax = 15;     // cap
        uint32 rebirthLegacyAbilityEssence = 3;  // Classless path: per rank, at level 1
        uint32 rebirthLegacyTalentEssence = 2;   // Classless path: per rank, at level 1

        uint32 npcEntry = 990100;
    };

    char const* RarityName(Rarity r);
    char const* RarityColor(Rarity r); // client color escape
} // namespace ClasslessWildcard

#endif // MOD_CLASSLESS_WILDCARD_H
