# mod-classless-wildcard — Build Plan

An AzerothCore (master / WotLK 3.3.5a) module that replicates Project Ascension's
**Classless system** and its **Season 10 "Wildcard" mode** as faithfully as the stock
3.3.5 client allows.

---

## 1. What Ascension actually does (research summary)

### 1.1 Classless free-pick system (all seasons)

- No classes: every spell, talent, weapon and armor type is available to every Hero.
- **Ability Essence (AE)** and **Talent Essence (TE)** are the progression currencies.
  A small AE pool (~9) is granted at level 1 for starter abilities; from ~level 10 the
  Hero earns **1 AE and 1 TE per level** up to the cap.
- Abilities are tiered by **rarity** (Common → Legendary) and cost different amounts of
  AE ("basic spells cost ~2 AE; build-defining spells cost much more"), forcing
  trade-offs — you cannot own every strong spell.
- Talents are bought with TE from **all class trees at once**; some talents have
  capstone bonuses when fully ranked. Talents that grant an active ability also cost AE.
- The **Character Advancement Panel** (custom client UI) is the hub: pick abilities,
  invest talents, and **allocate/reallocate primary stats** at will.
- **Multi-spec**: many specs per Hero, switchable.
- **Mystic/Random Enchants** on gear modify ability behaviour (uncommon/rare stack ×3,
  max 1 legendary + 3 epic per set; rerolled/extracted/applied with Mystic Runes /
  Extracts / Orbs at Enchanting Altars).
- Itemization is classless: `AllowableClass` restrictions effectively don't exist.

### 1.2 Season 10 Wildcard mode (Darkmoon realm, and S9 Elune rules it inherits)

- **Level 1**: the Hero receives **4 random abilities**, each individually
  re-rollable / lockable (free) before level 10.
- **From level 10 to cap**: **every level → 1 random talent**, **every 2 levels →
  1 random ability** (≈26 abilities / 51 talents at a level-60 cap).
- **Rarity = roll weight**: legendary abilities/talents roll least often, common most.
- **Rerolls** consume **Scroll of Fortune** (abilities+talents) or **Scroll of
  Fortune: Talents** (talents only), bought from Silas Darkmoon for Marks of
  Ascension. "Keep what you like, reroll the rest."
- **Talent upgrade rule**: rerolling into a higher rank of a talent you already own
  auto-upgrades it, and the reroll fires again for another talent.
- **Synergy & Relevancy** (replaced the old "weighting"): every reroll increases the
  chance that the next roll is a **Synergy Roll** — an ability/talent complementing
  what the Hero already owns. **Bad-luck protection**: a rejected Synergy result is
  banned from the pool for the next **25 rolls**.

### 1.3 What requires Ascension's custom client (out of scope, server-side substitutes provided)

| Ascension feature            | 3.3.5 client reality                        | Our substitute                                    |
|------------------------------|---------------------------------------------|---------------------------------------------------|
| Character Advancement Panel  | No custom UI                                | Hero Advancement **NPC gossip** + `.classless`/`.wildcard` chat commands (an optional client AIO addon is Phase 3) |
| One universal "Hero" class   | A character has one class & one power bar   | Any race/class chassis; all spells learnable; optional experimental cross-power casting config |
| Talent trees for all classes in the talent frame | Talent UI is class-locked  | Talents are granted as their underlying spells through our TE/gossip system; native talent points are suppressed |
| Mystic enchant UI            | No custom enchant UI                        | Phase 2 (item-based applier), out of core scope   |

---

## 2. Architecture

```
mod-classless-wildcard/
├── PLAN.md / README.md
├── conf/classless_wildcard.conf.dist        # all tuning knobs
├── data/sql/
│   ├── db-characters/cw_characters_base.sql # per-character persistence
│   ├── db-world/cw_world_base.sql           # NPC, scroll items, vendor, override tables
│   └── manual/
│       └── cw_classless_items.sql           # AllowableClass = -1 on all items (HAND-APPLY ONLY —
│                                            #  never under db-world/, which auto-applies recursively)
└── src/
    ├── cw_loader.cpp              # Addmod_classless_wildcardScripts()
    ├── ClasslessWildcard.h        # config struct, shared enums, state structs
    ├── ClasslessMgr.cpp           # library/pools, config load, persistence, essence + roll engines
    ├── ClasslessPlayerScript.cpp  # login / first-login / level-up / talent-suppression hooks
    ├── ClasslessNpc.cpp           # "Hero Advancement" NPC gossip UI (both modes)
    └── ClasslessCommands.cpp      # .classless and .wildcard command families
```

### 2.1 ClasslessMgr (singleton, built in `WorldScript::OnStartup`)

**Ability library** — built from `SkillLineAbility.dbc`:
keep entries with `ClassMask != 0` (class spells), group by
`sSpellMgr->GetFirstSpellInChain()` so one library entry = one spell line with all its
ranks; racial (`RaceMask != 0`) and Death Knight lines excluded by default (DK spells
need runes; config to include). Each entry carries: first-rank spell id, origin class
mask, rarity, AE cost, roll weight.

**Talent pool** — built from `Talent.dbc` + `TalentTab.dbc`:
player tabs only (`petTalentMask == 0`, `ClassMask != 0`); each talent exposes its
rank-spell ids (`RankID[0..4]`), tab, row/col and prerequisite (`DependsOn`).

**Rarity model** — Ascension hand-tunes rarity per spell. We ship:
1. a **heuristic default** (talents: by tree row — rows 0-1 common → row 8+/31-pointers
   legendary; abilities: by first-rank spell level bracket), and
2. **world-DB override tables** (`cw_ability_override`, `cw_talent_override`) where an
   admin sets rarity / AE cost / weight / enabled per entry — this is the tuning
   surface that stands in for Ascension's curated data.

### 2.2 Persistence (characters DB)

| table              | contents                                                          |
|--------------------|-------------------------------------------------------------------|
| `cw_char_state`    | guid, mode (0 classless / 1 wildcard / 255 unchosen), AE, TE, pity counter, last processed level |
| `cw_char_abilities`| guid, first_spell, source (picked/rolled), locked flag            |
| `cw_char_talents`  | guid, talent_id, rank                                             |
| `cw_char_bans`     | guid, is_talent, entry, rolls_left (synergy bad-luck protection)  |

Learned spells themselves persist natively in `character_spell` (we call
`Player::learnSpell(id, false)`), so our tables only track the meta-state.

### 2.3 Core hooks (all verified against current master `ScriptDefines/PlayerScript.h`)

| Hook                                    | Use                                                        |
|-----------------------------------------|------------------------------------------------------------|
| `OnPlayerFirstLogin`                    | init state row, grant proficiencies, starter AE, Wildcard's 4 random starting abilities |
| `OnPlayerLogin`                         | load state, re-teach proficiencies, catch up missed levels |
| `OnPlayerLevelChanged`                  | grant AE/TE (classless) or run the roll schedule (wildcard); auto-learn newly available ranks of owned lines |
| `OnPlayerCalculateTalentsPoints`        | force native talent points to 0 (talents flow through TE)  |
| `OnPlayerCanLearnTalent`                | block native talent frame purchases                        |
| `AllSpellScript::OnSpellCheckCast`      | (config-gated, experimental) let a rage/energy chassis cast mana spells |
| `WorldScript::OnStartup / OnAfterConfigLoad` | build library / load config                           |

### 2.4 Class restriction removal

- **Gear**: `Player::CanUseItem` checks `AllowableClass` *before* the script hook fires,
  so a hook can't bypass it — and the client red-flags items anyway. The correct lever
  is data: the optional SQL sets `AllowableClass = -1` on `item_template`
  (client sees it through the item query cache — DBC untouched). Shipped **opt-in**.
- **Proficiencies**: on login every character is taught all armor classes
  (cloth/leather/mail/plate/shield) and all weapon skills + dual wield (configurable
  spell list), so anything can actually be equipped and swung.
- **Spells**: `learnSpell()` is class-agnostic server-side, and the 3.3.5 client
  happily displays and casts cross-class spells learned this way.

### 2.5 Free-pick mode (Ascension classless)

- AE: `Classless.StartingAbilityEssence` (9) at creation; +1 AE and +1 TE per level
  from level 10 (all configurable), matching Ascension's published economy.
- Learn/unlearn through the NPC (browse by class → paginated spell lists with cost
  and rarity color) or `.classless learn <spellId>`; cost by rarity
  (default 1/2/3/5/8 AE), refund on unlearn, full respec for gold.
- Talents: browse trees of every class; buying a rank teaches `RankID[rank]` and
  enforces prerequisite talents and (configurably) the 5-points-per-row rule
  *across our own bookkeeping*, replicating tiered trees without the talent frame.
- Owned lines auto-rank-up when leveling (next rank taught when its level is reached).

### 2.6 Wildcard engine (Season 10 rules)

Schedule (all configurable, Ascension defaults):
- level 1 → `Wildcard.StartingAbilities` = 4 random abilities;
- from `Wildcard.RollStartLevel` = 10: 1 talent **every** level, 1 ability **every 2nd**
  level (level cap 80 simply extends the schedule).

Roll algorithm:
1. Build candidate set (enabled, not owned, not banned).
2. **Synergy check**: chance = `SynergyBaseChance + pity × SynergyIncrement`;
   a synergy roll restricts candidates to entries sharing an origin class with
   something the Hero already owns, then resets the pity counter.
3. Weighted pick by rarity weight (`Common 100 … Legendary 3` by default).
4. **Talent rolls**: landing on an owned talent below max rank upgrades it and
   **rolls again** (Ascension's upgrade rule, chained safely).

Rerolls ("keep what you like, reroll the rest"):
- any unlocked rolled ability/talent can be rerolled at the NPC or via
  `.wildcard reroll`;
- **free below level 10** (starting-ability tuning phase), afterwards consumes
  **Scroll of Fortune** (item 990101, abilities+talents) or **Scroll of Fortune:
  Talents** (990102) — both sold by the NPC (vendor entries in world SQL, price
  configurable via `item_template`);
- the rejected entry goes into `cw_char_bans` for `Wildcard.SynergyBanRolls` = 25
  rolls; each reroll bumps the pity counter (→ rising synergy chance);
- rerolling a talent refunds its ranks and immediately rolls the same number of
  replacement talent grants.
- locking (`.wildcard lock`) protects an ability from accidental rerolls.

Mode selection: per-character opt-in at the NPC (or `.classless mode …`) before
level `ModeChoiceDeadline` = 5; unchosen characters fall back to `DefaultMode`.

---

## 3. Phases

**Phase 1 — this module (implemented)**
Library/pool builder, override tables, both modes, essence economy, wildcard roll
engine (schedule, rarity weights, synergy + bad-luck protection, upgrade rule,
scrolls and locks), proficiencies, NPC gossip UI, command families, respec,
config surface, SQL, README.

**Phase 2 — onboarding, exits, itemization (implemented)**
- Starter **archetypes** (`cw_archetypes` world table + 6 shipped builds) that
  auto-spend a new Hero's essence — Ascension's role-focused onboarding.
- **Rebirth**: config-gated full reset + path switch (classless ↔ wildcard) for
  gold after the mode lock; wildcard rebirths replay the roll schedule.
- **Classless item pack**: 12 server-side items (int guns, str javelins, mail
  tank / plate caster / spellpower fist etc.) sold by the NPC.

**Phase 3 — client UI (implemented)**
- `client-addon/ClasslessWildcard`: a stock-client addon panel (no patch).
  Protocol: the addon self-whispers `CWCL\t<cmd>` on the addon channel; the
  server intercepts it in the private-chat hook, executes against ClasslessMgr
  and answers with addon packets. Panels: class-tabbed ability browser
  (icons/tooltips/rarity), talent trees, My Hero (unlearn / reroll / lock),
  Wildcard (talent rerolls, cards, pity/synergy), first-login onboarding
  wizard with archetype picks.

**Phase 4 — future fidelity upgrades**
- Stat reallocation (spend points on str/agi/sta/int/spi, server-side mods).
- Mystic-enchant-style random gear affixes (aura-scripted, no client patch).
- Multi-spec loadouts (save/swap ability+talent sets).
- Cross-power casting hardening (power-cost conversion, not just check waiver).
- Curated rarity/cost dataset shipped in the override tables.
- Custom classless spells via Spell.dbc + client MPQ patch (crosses the
  "players must download a patch" line — optional).

## 4. Compatibility & build

- Target: AzerothCore **master** (renamed `OnPlayer*` hooks, `ChatCommandBuilder`
  tables, module SQL auto-updater). Drop the folder into `modules/`, re-run CMake.
- Module SQL is applied automatically by the DB updater (`data/sql/db-*`);
  the item-unlock SQL is in `optional/` and must be applied deliberately.
- No core edits, no DBC edits required for Phase 1.
