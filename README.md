<div align="center">

<img src="docs/banner.svg" alt="mod-classless-wildcard — Ascension-style classless progression and Season 10 Wildcard rolls for AzerothCore" width="100%">

<br>

[![AzerothCore](https://img.shields.io/badge/AzerothCore-master-blue?style=flat-square)](https://www.azerothcore.org/)
[![Client](https://img.shields.io/badge/client-WotLK%203.3.5a-c8952f?style=flat-square)](https://www.azerothcore.org/)
[![Language](https://img.shields.io/badge/C%2B%2B-17-00599C?style=flat-square)](src/)
[![Addon](https://img.shields.io/badge/client%20addon-included-a335ee?style=flat-square)](client-addon/)
[![License](https://img.shields.io/badge/license-GPL--2.0--or--later-green?style=flat-square)](#license)

**Every character can learn every spell and every talent from every class** — buy them
with Essence like Ascension's classless realms, or let the dice decide in Wildcard mode.

[Install](#installation) · [How it plays](#two-ways-to-play) · [Commands](#commands) · [Configuration](#configuration) · [Uninstall](#uninstall)

</div>

---

## Overview

`mod-classless-wildcard` is a server-side AzerothCore module that removes the class system
from WotLK. Not "softened" — removed. Every character runs on one shared chassis class no
matter what the creation screen sent, so base stats, health, resources and every stat
conversion are identical for everyone, and the class you picked is just a model and a name.
Abilities and talents come from anywhere in the game.

Two progression paths ship in the box:

- **Classless** — an Essence economy. You pick exactly what you want, priced by rarity.
- **Wildcard** — Ascension's Season 9/10 ruleset. The server rolls for you on a fixed
  schedule; you steer the outcome with rerolls, locks, Skill Cards and pity protection.

Everything runs on a **stock 3.3.5a client**. The included addon and MPQ patch are optional
polish, not requirements — the whole module is driveable from an NPC and chat commands.

> Design notes, research sources and the full roadmap live in [`PLAN.md`](PLAN.md).

---

## Two ways to play

|                       | **Classless** (free-pick)                                      | **Wildcard** (rolled)                                                             |
| --------------------- | -------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| How you gain power    | Spend Ability Essence (AE) and Talent Essence (TE)              | The server rolls abilities and talents for you                                     |
| Starting kit          | 9 AE to spend as you like                                       | 4 random abilities at level 1                                                      |
| Progression           | +1 AE and +1 TE per level from 10                               | 1 talent per level and 1 ability every 2 levels, from 10                           |
| Cost model            | Abilities cost 1 / 2 / 3 / 5 / 8 AE by rarity, talents per rank | Free, but weighted — legendary is rarest                                           |
| Control over outcomes | Total; unlearn refunds, respec for gold                         | Rerolls, ability lock-in, Skill Cards, synergy rolls, 25-roll bad-luck protection  |
| Changing your mind    | `.classless respec`                                             | `.wildcard reroll`, Scrolls of Fortune, **Rebirth**                                |

Both paths share the universal resource pools, primary-stat allocation, full proficiency
training, the Hero Advancement NPC and the addon UI. Players choose a path per character
(or the realm forces one via config), and **Rebirth** lets them switch later for gold.

---

## Features

#### Progression

- **Classless free-pick** — rarity-priced abilities, talents from every class tree bought per
  rank with prerequisites and tier rules enforced, refunds on unlearn, gold respec, and owned
  spell lines that auto-rank-up as you level.
- **Wildcard rolls** — the Ascension S10 schedule and mechanics: free rerolls below level 10,
  rarity-weighted rolls, the talent-upgrade-rolls-again rule, ability locking, Skill Cards
  (2+2 ability, 3+3 talent, locked from level 10), and synergy rolls with a rising pity chance
  plus bad-luck bans.
- **Rerolls flow with leveling.** Every scheduled roll grants a matching reroll charge, so
  rerolling is part of normal play. Scrolls of Fortune (50s / 25s from the NPC) exist only as
  a top-up when charges run dry.
- **Rebirth** — a config-gated full reset that switches a character between paths after the
  mode lock. Wildcard rebirths replay the entire roll schedule.

#### Making every build actually work

- **One chassis for everyone** — every character is converted to a single class (Paladin by
  default) at creation, and existing characters convert on next login. This is the part that
  makes it classless: with ten different classes underneath, the core's own per-class math —
  base stats, base health and mana, which stat feeds attack power, the crit and dodge ratios —
  differs between them, and picking a class quietly becomes a build decision again.
- **Universal resources** — every Hero runs mana, rage *and* energy at once, druid-style, with
  **no client patch**. The client already tracks all three pools; one is displayed and the
  addon draws mini-bars for the rest (`/cwbars`). Spells always draw their native resource and
  a spell is never unusable because of the pool it costs — the same Hero casts Fireball on
  mana and Bloodthirsts on rage.
- **Primary stat allocation** — a per-level point budget spent freely across
  STR / AGI / STA / INT / SPI, applied live, reallocation free.
- **All proficiencies taught** — armor, weapons and dual wield, each configurable.
- **Optional item unlock** — one SQL script strips class restrictions from every item.

#### Getting players in the door

- **Hero Advancement NPC** (entry `990100`) — spawned in Stormwind, Orgrimmar and Dalaran,
  each spawn carrying the full gossip UI plus the scroll and item vendor. `.npc add 990100`
  places more anywhere.
- **Starter archetypes** — six curated builds (*Blade Dancer*, *Battle Mage*,
  *Ranger of the Light*, *Shadow Mender*, *Stealthy Healer*, *Storm Warrior*) that spend a new
  Hero's starting essence on a coherent role. Add your own in `cw_archetypes`.
- **First-login onboarding** — a welcome flow, plus an addon wizard that walks a fresh
  character through picking a path.
- **Classless item pack** — 12 Ascension-flavored items sold by the NPC: intellect guns,
  strength javelins, mail tanking gear, plate caster sets, spellpower fist weapons. All
  server-side.

#### Client-side (optional)

Players run **one installer** ([`client-patch/install.py`](client-patch/README.md), or
double-click `install.bat` on Windows) and get all of the below. It needs nothing but
Python 3 — no compiler, no MPQ tools, no manual file copying — it never modifies `Wow.exe`,
and `--uninstall` puts the client back to stock.

- **Addon UI** ([`client-addon/ClasslessWildcard/`](client-addon/ClasslessWildcard/)) — a
  Character Advancement panel for the stock client: class-tabbed ability browser with icons,
  tooltips and rarity colors, talent trees, a My Hero tab (unlearn / reroll / lock), a Wildcard
  tab (talent rerolls, cards, pity and synergy display), and the onboarding wizard. Talks to
  the server over the `CWCL` addon channel. Players without it lose nothing but convenience.
- **Every class reads Hero** — creation screen, character sheet, `/who`, tooltips. Class
  colors and icons still work, so addons and raid frames are unaffected.
- **One class on the creation screen.** Every race stays creatable and offers a single
  cosmetic shell (shown as *Hero*, with the Hero pitch and bullets). The pick means
  nothing — the server converts every new character to its chassis regardless — so the
  screen stops asking a question that has no answer.
- **The creation-screen class blurb** (optional) — rewritten to the Hero pitch. Off by
  default: it edits a signed interface file, so it only suits clients that do not enforce
  GlueXML signatures. The Hero name and single-class list above do not need it.

---

## Requirements

- An AzerothCore **master** build you can recompile — the module adds C++ sources.
- A **3.3.5a** client.
- Nothing else. No core edits, no other modules.

---

## Installation

**1. Clone into your modules directory**

```bash
git clone https://github.com/DustinHendrickson/mod-classless-wildcard.git azerothcore-wotlk/modules/mod-classless-wildcard
```

**2. Re-run CMake and rebuild the worldserver**

```bash
cmake .. && make -j$(nproc)
```

**3. Start the worldserver.** The SQL under `data/sql/db-world` and `data/sql/db-characters`
is applied automatically by the DB updater.

**4. Configure.** Copy `conf/classless_wildcard.conf.dist` next to your `worldserver.conf` as
`classless_wildcard.conf` (or let the build install it), then tune to taste.

<details>
<summary><b>Optional steps — recommended for the full Ascension feel</b></summary>

<br>

**Unlock every item for every class.** Apply
`data/sql/manual/cw_classless_items.sql` to your world DB by hand.

> **Back up `item_template` first.** This overwrites `AllowableClass` with `-1` for every item
> and the original masks cannot be recomputed. Players should clear their client `Cache`
> folder afterwards.
>
> ⚠️ **If you ran this module before September 2026:** this script used to live under
> `data/sql/db-world/optional/`, and AzerothCore's updater applies *everything* under
> `db-world` recursively — so it was applied automatically on your first startup, not
> optionally. Check with `SELECT * FROM acore_world.updates WHERE name = 'cw_classless_items.sql';`
> — if a row exists, your `item_template` was already overwritten and only a backup restores it.


**Set your players up.** Hand them the `client-patch` and `client-addon` folders and point
them at [`client-patch/README.md`](client-patch/README.md). They double-click `install.bat`
(or run `python3 install.py "/path/to/WoW"`) once and get the addon, the *Hero* renaming and
the single-class creation list. It only needs Python 3, never touches `Wow.exe`, and
`--uninstall` reverts it. Rewriting the creation-screen *description* is a separate opt-in
(`--creation-text`) because it edits a signed interface file that some clients reject.

</details>

---

## Commands

Everything the NPC and addon do is also available as a chat command.

### `.classless`

| Command                                           | What it does                                      |
| ------------------------------------------------- | ------------------------------------------------- |
| `.classless status`                               | Mode, essence balances, spent totals              |
| `.classless mode classless\|wildcard`              | Choose your path, before the deadline level       |
| `.classless learn <spellId>`                      | Buy an ability with Ability Essence               |
| `.classless unlearn <spellId>`                    | Drop an ability; refunds per config               |
| `.classless talent <talentId>`                    | Buy the next rank of a talent with Talent Essence |
| `.classless respec`                               | Full respec for gold                              |
| `.classless stats`                                | Show stat allocation and remaining points         |
| `.classless stat str\|agi\|sta\|int\|spi <points>` | Allocate points; reallocation is free             |
| `.classless bar mana\|rage\|energy\|default`       | Pick which resource the main power bar displays   |
| `.classless archetypes`                           | List starter archetypes and their IDs             |
| `.classless archetype <id>`                       | Apply a starter build to a fresh Hero             |
| `.classless rebirth classless\|wildcard`           | Full reset and path switch, costs gold            |

### `.wildcard`

| Command                                                             | What it does                                       |
| ------------------------------------------------------------------- | -------------------------------------------------- |
| `.wildcard status`                                                  | Pending rolls, reroll charges, pity counter, cards |
| `.wildcard reroll <spellId>`                                        | Reroll a rolled ability                            |
| `.wildcard rerolltalent <talentId>`                                 | Reroll a rolled talent                             |
| `.wildcard lock <spellId>`                                          | Lock an ability so future rolls can't replace it   |
| `.wildcard card ability\|talent\|removeability\|removetalent <id>`  | Spend a Skill Card                                 |

### Addon slash commands

| Command               | What it does                            |
| --------------------- | --------------------------------------- |
| `/cw` or `/classless` | Open the Character Advancement panel    |
| `/cwbars`             | Toggle the universal-resource mini-bars |

---

## Configuration

Every knob lives in [`conf/classless_wildcard.conf.dist`](conf/classless_wildcard.conf.dist),
which documents all 70+ settings inline. The ones you are most likely to touch:

| Setting                                             | Default     | Meaning                                               |
| --------------------------------------------------- | ----------- | ----------------------------------------------------- |
| `ClasslessWildcard.Enable`                          | `1`         | Master switch                                         |
| `ClasslessWildcard.DefaultMode`                     | `0`         | `0` classless, `1` wildcard                           |
| `ClasslessWildcard.AllowModeChoice`                 | `1`         | Let players pick; `0` forces `DefaultMode` realm-wide |
| `ClasslessWildcard.ModeChoiceDeadline`              | `5`         | Level after which the path locks                      |
| `ClasslessWildcard.IncludeDeathKnight`              | `0`         | Include DK spells — rune costs make these awkward     |
| `ClasslessWildcard.NpcEntry`                        | `990100`    | Hero Advancement NPC entry                            |
| `Chassis.Enable`                                    | `1`         | Force every character onto one class                  |
| `Chassis.Class`                                     | `2`         | Which class that is (2 = Paladin)                     |
| `Classless.StartingAbilityEssence`                  | `9`         | AE granted at character creation                      |
| `Classless.AbilityCostByRarity`                     | `1,2,3,5,8` | AE cost per rarity tier                               |
| `Classless.AbilityEssencePerLevel`                  | `1`         | AE per level from `EssenceStartLevel`                 |
| `Classless.TalentEssencePerLevel`                   | `1`         | TE per level                                          |
| `Classless.RespecCostGold`                          | `50`        | Gold cost of a full respec                            |
| `Wildcard.StartingAbilities`                        | `4`         | Abilities rolled at level 1                           |
| `Wildcard.RollStartLevel`                           | `10`        | Level the roll schedule begins                        |
| `Wildcard.TalentEveryLevels` / `AbilityEveryLevels` | `1` / `2`   | Roll cadence                                          |
| `Wildcard.RarityWeights`                            | `100,…`     | Roll weights per rarity tier                          |
| `Wildcard.FreeRerollBelowLevel`                     | `10`        | Rerolls are free under this level                     |
| `UniversalResources.Enable`                         | `1`         | Mana + rage + energy on every character               |
| `Stats.Enable` / `Stats.PointsPerLevel`             | `1` / `2`   | Primary stat allocation                               |
| `Rebirth.Enable` / `Rebirth.CostGold`               | `1` / `100` | Path switching after the mode lock                    |

### Per-spell and per-talent tuning

Rarity, cost, roll weight and an enable flag can be overridden for any individual spell or
talent through the `cw_ability_override` and `cw_talent_override` world tables — the way to
ban a problem ability, or make one legendary, without recompiling.

---

## Notes and limitations

These follow from the stock 3.3.5a client, and are not bugs:

- **The talent frame is unused.** Talents are granted as their underlying spells through the
  module, and native talent points are zeroed. Everything you learn shows in the spellbook.
- **The class you pick at creation has no mechanical effect.** Every character is converted to
  the configured chassis, so there is no "better base" for casters or for melee. Set
  `ClasslessWildcard.Chassis.Class` before your realm launches; changing it later re-converts
  every character and shifts their base stats.
- **Death Knight spells are excluded by default** because of rune costs. Configurable.
- Mystic enchants and multispec are Phase 2/3 — see [`PLAN.md`](PLAN.md).

---

## Uninstall

The module is fully reversible. Almost everything it does is additive — its own tables, its own
item and NPC entries, runtime-only hooks — and the one large per-character change (cross-class
spells) cleans itself up on next login.

<details>
<summary><b>Step-by-step revert</b></summary>

<br>

Do this **with the worldserver stopped**:

1. **Back up** your world and characters databases.
2. **Remove the code** — delete `modules/mod-classless-wildcard`, re-run CMake, rebuild the
   worldserver, delete `classless_wildcard.conf`.
3. **World DB** — run `data/sql/uninstall/cw_uninstall_world.sql` by hand; it is never
   auto-applied. It drops the module's world tables, the scrolls, the item pack, the NPC
   (template, spawns, vendor) and the custom `skillraceclassinfo_dbc` rows, and clears the
   module's DB-updater bookkeeping.
4. **Characters DB** — run `data/sql/uninstall/cw_uninstall_characters.sql`. It drops the
   `cw_char_*` state tables and removes the taught proficiency spells.
5. **Start the server.** The rest is automatic: with the custom skill-validity rows gone, the
   core's own login validation (`ValidateSkillLearnedBySpells`, on by default) deletes every
   spell and skill invalid for a character's real class the next time they log in. Talent
   points return and the power bar reverts to the class default.
6. **Client side** — players run `python3 install.py --uninstall "/path/to/WoW"`, which removes
   the patch archives and the addon, clears the cache, and restores `Wow.exe` if an older
   version had patched it (current versions never touch it).

**What does not revert automatically:**

- **`optional/cw_classless_items.sql`**, if you applied it, overwrote
  `item_template.AllowableClass` with `-1` for every item. The original masks cannot be
  recomputed — restore `item_template` from your pre-install backup, or re-import it from the
  AzerothCore base SQL matching your core revision.
- **Same-class spells** a character was granted (a Warrior who rolled warrior abilities) survive
  validation, since they are legal for that class. Harmless; a GM can `.unlearn` them
  individually.
- Characters **created while the module was active** had their class starter spells stripped and
  got the neutral weapon kit instead. After the revert they relearn missing spells at their
  class trainer as normal, and the kit weapons are ordinary vendorable items.
- Every Hero is effectively **respecced** when their granted kit disappears. That is inherent to
  removing a classless system — announce the revert to your players first.

Reinstalling later is safe: the uninstall scripts clear the DB-updater bookkeeping, so all module
SQL re-applies cleanly on the next startup.

</details>

---

## Contributing

Issues and pull requests are welcome. When reporting a bug, please include your AzerothCore
revision, the module commit, how your `classless_wildcard.conf` differs from the `.dist`, and
the worldserver log around the failure.

## License

GNU General Public License v2 or later, matching AzerothCore
(`acore.json` declares GPL2 and every core source header reads "version 2 of the
License, or (at your option) any later version"). Full text in [`LICENSE`](LICENSE).

## Credits

Mechanics are modeled on the published Season 9/10 rules of
[Project Ascension](https://ascension.gg/)'s classless and Wildcard realms. This project is
unaffiliated with Project Ascension and with Blizzard Entertainment.
