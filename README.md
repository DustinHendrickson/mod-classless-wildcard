<div align="center">

<img src="docs/classless-wildcard-github-header.webp" alt="Classless Wildcard, an AzerothCore module for WotLK 3.3.5a. Every spell. Every talent. Every class. Or let the dice decide." width="100%">

<br>

[![AzerothCore](https://img.shields.io/badge/AzerothCore-master-blue?style=flat-square)](https://www.azerothcore.org/)
[![Client](https://img.shields.io/badge/client-WotLK%203.3.5a-c8952f?style=flat-square)](https://www.azerothcore.org/)
[![Language](https://img.shields.io/badge/C%2B%2B-17-00599C?style=flat-square)](src/)
[![Addon](https://img.shields.io/badge/client%20addon-included-a335ee?style=flat-square)](client-addon/)
[![License](https://img.shields.io/badge/license-GPL--2.0--or--later-green?style=flat-square)](#license)

**Every character can learn every spell and every talent from every class.** Buy them with
Essence, or let the server roll for you in Wildcard mode.

[Install](#installation) · [How it plays](#two-ways-to-play) · [Playerbots](#playerbots) · [Commands](#commands) · [Configuration](#configuration) · [Uninstall](#uninstall)

</div>

---

> [!CAUTION]
> **This is a total server overhaul, and it is experimental.**
>
> It replaces the class system outright and rebuilds progression, resources, stats, gear and
> quest access around it. Plan a realm around it; do not add it to an existing one you care about.
>
> The [client patch](#client-setup) is **required**, not optional polish. Every player must run
> it, or the game will be broken for them rather than merely unpolished.
>
> Installing changes character data and writes to core tables. It is [reversible](#uninstall),
> but back up your world and characters databases first, and do not install it on a realm
> where data loss would be a problem.

---

## Overview

`mod-classless-wildcard` is a **total server overhaul**, not a feature you bolt onto an
otherwise normal realm. It removes the class system from WotLK 3.3.5a and rebuilds progression,
resources, stats, gear and quest access around a single classless character. Every character is
a **Hero**. All Heroes run on one shared base class, so the class picked at character creation is
cosmetic: it grants no class abilities and locks nothing away. Race still provides its racial
traits. Everything else, every ability and every talent, is earned in game and can come from any
class.

Because it changes that much, **the client patch is required**, not optional polish. A stock
3.3.5a client will connect and play, but it still renders the class system it was built for: it
shows real class names, offers a class picker at character creation, has no working ranged slot
on the base class, and has no interface for buying abilities or seeing rolls. Players who skip
it get a broken realm, not a plainer one. See [Client setup](#client-setup).

Two progression paths ship with the module:

- **Classless.** An Essence economy. Players buy exactly the abilities and talents they want,
  priced by rarity.
- **Wildcard.** The Season 9/10 ruleset from Project Ascension. The server rolls abilities and
  talents on a fixed schedule, and players steer the result with rerolls, ability locks and
  bad-luck protection.

Every player also runs a one-click client setup that ships with the module. It patches their
3.3.5a client and installs the addon. See [Client setup](#client-setup).

---

## Two ways to play

|                       | **Classless** (free pick)                                           | **Wildcard** (rolled)                                              |
| --------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------ |
| How you gain power    | Spend Ability Essence (AE) and Talent Essence (TE)                   | The server rolls abilities and talents for you                      |
| Starting kit          | 9 AE to spend as you like                                            | 4 random abilities at level 1                                       |
| Progression           | +1 AE and +1 TE per level from level 10                              | 1 talent per level and 1 ability every 2 levels, from level 10      |
| Cost model            | Abilities cost 1 / 2 / 3 / 5 / 8 AE by rarity, talents 1 TE per rank | Free but weighted. Legendary is rarest, and talent rank is rarity   |
| Control over outcomes | Total. Unlearning refunds, and a full respec costs gold              | Rerolls, ability locks, synergy rolls, reroll cooldowns             |
| Changing your mind    | `.classless respec`                                                  | `.wildcard reroll`, Reroll Scrolls, Rebirth                         |

Both paths share the universal resource pools, primary stat allocation, full proficiency
training, the Hero Advancement NPC and the addon UI. Players choose a path per character, or the
realm forces one through config. **Rebirth** lets a player switch paths later for gold.

---

## Screenshots

<div align="center">

<img src="docs/advancement_addon.webp" alt="The Character Advancement panel: an ability browser, talent trees for every class, and the current build side by side" width="92%">

<em>The <b>Character Advancement</b> panel. Browse every class's abilities and talent trees,<br>
with your build on the right. Lock or reroll anything you own from the same window.</em>

<br><br>

<img src="docs/wildcard_addon.webp" alt="A Wildcard roll revealing Healing Wave, showing its rarity with Keep and Reroll buttons" width="62%">

<em>A <b>Wildcard</b> roll. The die lands on a new ability and shows its rarity.<br>
Keep it, or spend a reroll.</em>

</div>

---

## Features

### Progression

- **Classless free pick.** Rarity-priced abilities, and talents from every class tree bought a
  rank at a time with prerequisites and tier rules enforced. Unlearning refunds essence, a full
  respec costs gold, and owned spell lines rank up automatically as you level.
- **Wildcard rolls.** The Season 10 schedule and mechanics: free rerolls below level 10,
  rarity-weighted rolls, rolled talent ranks, ability locking, and synergy rolls. See
  [How Wildcard rolls work](#how-wildcard-rolls-work).
- **Talent rank is its rarity.** A talent roll also rolls which rank you land on, and the rank
  sets the tier: rank 1 common through rank 5 legendary. Rolls cost nothing, so landing on rank 5
  hands you the full-strength talent for free, where a Classless Hero pays for every rank up to
  it. Rank odds follow `RarityWeights`. The shipped Season 9 default weights every rank equally;
  use descending weights such as `100,60,30,10,3` to make rank 5 a rare prize. The exact rules
  are under [How Wildcard rolls work](#how-wildcard-rolls-work).
- **Rerolls scale with leveling.** Every scheduled roll grants a reroll charge. Charges are one
  pool spent on abilities and talents alike, and anything you already own can be rerolled later
  from **My Build**. Reroll Scrolls top the pool up when charges run out and work for either
  kind. They are sold by the Hero Advancement NPC and by the addon's **Buy Scroll** button. The
  price scales with level, from silver in the early game to gold near the cap. Both the price
  and the button are configurable.
- **Rebirth.** A full reset that also switches a character between paths, available after the
  mode lock and gated by config. A Wildcard rebirth replays the entire roll schedule.

### Making every build work

- **One base class for everyone.** Every Hero runs on a single base class, Paladin by default.
  The class picked at creation grants no class abilities and locks no build away. Race is the
  meaningful choice, because it keeps its racial traits.
- **Universal resources.** Every Hero carries mana, rage and energy at the same time. One shows
  on the main bar and the addon draws mini-bars for the rest (`/cwbars`). Each spell draws from
  its own resource, so the same Hero casts Fireball on mana and Bloodthirst on rage, and no
  spell is unusable because of what it costs. Mana, its base value, its Intellect scaling and its
  Spirit regeneration all come from the base class, so they behave as they do anywhere else, five
  second rule included. Rage and energy are what the module adds. A Hero who wants Spirit to
  regenerate mana during a fight learns Meditation, Arcane Meditation or Intensity, any of which
  any Hero can take.
- **Death Knight abilities.** Off by default, because they cost runes and the core only builds a
  rune block for a real Death Knight. Set `IncludeDeathKnight` to `1` and every Hero gets one:
  runes, rune cooldowns and runic power. The stock UI cannot draw any of it, so the server sends
  the rune state to the addon, which shows six pips coloured by rune type, dimmed while
  recharging, plus a runic power bar.
- **Primary stat allocation.** A point budget spent freely across STR, AGI, STA, INT and SPI,
  applied immediately, with free reallocation at any time from the addon's Stats tab or
  `.classless stat`. The budget is `StartingPoints + PointsPerLevel x (level - 1)`, which on the
  defaults is 4 points at level 1 and 162 at level 80.
- **What a point of each stat is worth.** On the default Paladin base class, one point gives:

  | Stat | Per point, at level 80 |
  | --------- | ------------------------------------------------------------------------------- |
  | Strength  | +2 melee attack power, +0.5 block value                                            |
  | Agility   | +1 melee and +2 ranged attack power, and 1% critical strike per 52 Agility         |
  | Stamina   | +10 health (the first 20 points give +1 each)                                      |
  | Intellect | +15 mana (first 20 give +1 each), +0.5 spell power, 1% spell crit per 167 Intellect |
  | Spirit    | mana and health regeneration, rising with your Intellect                           |

  Agility's melee attack power and Intellect's spell power are the module's addition, on top of
  what the base class already converts, because a Hero's build can point in any direction. Both
  rates are configurable under `UniversalStats`.

  Critical strike, spell critical strike and regeneration are worth less per point the higher
  your level: the same Agility that buys 1% critical strike per 8 points at level 20 needs 52 at
  level 80. Dodge diminishes as you stack it, so it has no flat rate at all. Hovering a stat in
  the addon's Stats panel reads the live values for your own level and base class, so it always
  shows what a point is worth to you right now.
- **All proficiencies taught.** Armor, weapons and dual wield, each configurable.
- **The base class never restricts a build.** The core checks whether a player is a Paladin,
  Druid or Shaman wherever behaviour is class-specific, which on a classless realm would answer
  for everyone. The module answers those checks so that classless means every class: any
  **relic** equips (Libram, Idol, Totem, Sigil and the warlock relic share one slot that the core
  normally gives to a single class each), shields work regardless of base class, and the aura
  states behind **Overpower, Revenge, Riposte and Counterattack** exist so those abilities fire.
  The client patch turns that same slot back into a real ranged slot, so bows, guns and wands are
  drawn on the character, the ammo slot appears, and ranged attack power shows a real number.
- **Forms and stances arrive usable.** A form on its own does nothing, so gaining one also hands
  over the basic abilities that go with it, free and immediately. Cat Form brings Claw and Prowl,
  Bear Form brings Maul and Demoralizing Roar, Battle Stance brings Charge, Defensive Stance
  brings Taunt, Berserker Stance brings Pummel. Without this a Hero could roll Bear Form and find
  they had turned into a creature with no way to attack. The pairs are rows in `cw_form_kits`, so
  you can add your own, and one config flag turns the whole feature off.
- **Class quests are open to everyone.** Every class's quest chains are available to every Hero,
  so the warrior's Whirlwind Axe chain, the warlock's pet summoning quests and every class mount
  chain are reachable instead of dead content. Applied automatically and reversible. See
  [Class quests](#class-quests).

### Getting players in the door

- **Hero Advancement NPC** (entry `990100`). One spawn in each of Stormwind, Ironforge,
  Darnassus, the Exodar, Orgrimmar, Thunder Bluff, Undercity, Silvermoon City, Dalaran and
  Shattrath City, placed beside that city's guild master so it is easy to find. Shattrath's
  stands by A'dal. Every spawn carries the full gossip UI plus the scroll and item vendor, and
  everything it offers is also reachable from the addon panel. `.npc add 990100` places more.
- **Starter archetypes.** Six curated builds (*Blade Dancer*, *Battle Mage*, *Ranger of the
  Light*, *Shadow Mender*, *Stealthy Healer*, *Storm Warrior*) that spend a new Hero's starting
  essence on a coherent role. Add your own rows to `cw_archetypes`.
- **First-login onboarding.** A welcome flow, plus an addon wizard that walks a fresh character
  through picking a path.
- **A starter kit that fits any build.** A new Hero cannot be given class starter gear, because
  which class they will play does not exist yet. The shell class's gear is replaced with a neutral
  kit: Recruit's shirt, pants and boots worn, an eight-slot bag, and in the bags one of every
  basic weapon type, so whatever the Hero learns or rolls first, they have something to use it
  with. That is a one-handed sword and shield, two daggers, a one-handed mace, a two-handed sword,
  hammer and axe, a staff, a bow with 200 arrows, a gun with 200 shot, and a throwing axe, plus 20
  bread and 20 water to eat and drink between fights. The creation Hearthstone is preserved. The
  whole kit is config, in `StarterKit.Items` and `StarterKit.Equip`.
- **Classless item packs.** 262 items sold by the NPC and dropped by mobs, built around stat
  combinations the class system does not allow: intellect guns and wands with attack power,
  strength staves and bows, mail tanking and caster gear, plate caster sets, spellpower fist
  weapons and shields, and hybrid rings and necks. The catalogue also carries hit and haste
  pieces. One rating covers melee, ranged and spell in 3.3.5a, so the same helm contributes to a
  caster's spell hit and a swordsman's melee hit. Most of the catalogue is tiered across nine
  level bands from 1 to 80, so there is something worth buying the whole way up rather than only
  at level 35. Prices follow the medians of real 3.3.5a items, from roughly 16 silver at level 1
  to over 100 gold at level 80. Every piece uses artwork from a real item of the same class,
  subclass and slot, so the icon and model match the tooltip, and the look advances with the
  level band. The whole catalogue is server-side, so no custom art or files ship to players.
- **A browsable shop.** A single vendor list cannot hold more than 150 items, so the catalogue is
  split across 16 lists opened from the NPC's gossip menu: pick *Weapons*, *Armor* or *Jewelry &
  off-hand*, then a level bracket (1-20, 21-40, 41-60, 61-80) or *All levels*. Nothing is hidden
  by level. Every item is reachable at any level, for buying ahead or gearing an alt.
- **Hero heirlooms.** 23 items that scale with the character from level 1 to 80, using the
  client's own heirloom system. Weapons of every family, plus armor pieces the original classes
  could never wear: spellpower plate, strength mail, agility cloth, and single-stat trinkets for
  spellpower, haste and crit. They cost 2 to 10 gold, priced to be bought early and grown into,
  and rares and world bosses can drop one.
- **Gear drops in the world.** The NPC is not the only source of gear. Any mob can drop a piece
  of the same catalogue, banded to the mob's level, so a level 20 zone yields level 20 gear
  whoever kills there, and farming low-level mobs at 80 returns low-level gear. Rares, rare
  elites and world bosses drop more often and are the only kills that can yield a scaling
  heirloom. Rates are configurable and the feature can be switched off. Drops are added to the
  kill at runtime, so no `creature_loot_template` rows are modified.

### Client setup

Every player runs the installer in [`client-patch/`](client-patch/README.md). They close WoW and
double-click `install.bat` on Windows, or run `./install.sh "/path/to/WoW"` on Linux and macOS.
It needs Python 3.7 or newer and nothing else: no compiler, no MPQ tools, no manual file copying.
Running it with `--uninstall` returns the client to stock.

It installs:

- the **ClasslessWildcard addon**: the Hero Advancement panel, with an ability browser, talent
  trees, your build with reroll and lock controls, the Wildcard roll UI, the onboarding wizard,
  and a **Help** panel explaining both systems
- every class shown as **Hero** on the creation screen, character sheet, `/who` and tooltips
- a single class per race on the creation screen, described as the Hero
- the Hero starter outfit on the creation preview, and a Hero emblem for the class icon

The creation-screen text lives in a signed game file, so the installer also applies the standard
"allow custom interface" patch to `Wow.exe`. It backs the file up first, and `--uninstall`
reverses it.

The Hero emblem needs the Python **Pillow** library (`pip install pillow`). Everything else works
without it.

---

## Playerbots

`mod-playerbots` works alongside this module. Bots are exempt from the classless system and keep
playing by vanilla class rules, which is what makes the combination work: playerbots initialises a
bot's spells and talents directly from its class, so a bot stripped down to a Hero would have
nothing to cast.

Exemption is by account name prefix, set with `ExemptAccountPrefixes` (default `rndbot`, which is
what playerbots uses for its random bot accounts). For any character on a matching account:

- it keeps its **real class**, so no base class conversion happens
- it keeps its **class abilities**, native **talent points** and class trainers
- it keeps **class-appropriate stats, resources and starting gear**, and equips gear by its own
  class rules
- it gets no essences, no rolls, no stat allocation and no Hero starter kit

The one thing that does change is the label. The client patch renames all ten classes to **Hero**
in `ChrClasses.dbc`, and the client resolves any character's class name locally, so bots appear as
Hero in the target frame, `/who` and inspect, exactly like players. Underneath, a bot is still a
Warrior or a Priest in every way that affects behaviour: what it casts, how it gears, and how it
plays its role. Only the displayed class name is shared.

If you run bots on accounts that do not start with `rndbot`, add your prefix to
`ExemptAccountPrefixes` or they will be converted to Heroes and lose their abilities.

---

## Requirements

- An AzerothCore **master** build you can recompile. The module adds C++ sources.
- A **3.3.5a** client for every player, with the client patch applied. This is required.
- **Python 3.7 or newer** on each player's machine, for the client installer.
- No core edits, and no other module is required. `mod-playerbots` is supported if you use it,
  see [Playerbots](#playerbots).

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

**3. Start the worldserver.** AzerothCore's DB updater applies the SQL under
`data/sql/db-world` and `data/sql/db-characters` on startup. This is required. It creates the
module's tables, the NPC and its spawns, the item catalogue and the vendor lists, and the module
does not work without it. Check the startup log to confirm the files applied.

**4. Configure.** Copy `conf/classless_wildcard.conf.dist` next to your `worldserver.conf` as
`classless_wildcard.conf`, then edit it. The build can also install it for you.

**5. Set up every player's client.** Give players the `client-patch` and `client-addon` folders
and point them at [`client-patch/README.md`](client-patch/README.md). The module expects a
patched client, so this step is required.

### Class quests

`data/sql/db-world/cw_world_class_quests.sql` is applied automatically with the rest of the
module SQL. Every Hero shares one base class, so without it the only class quests anyone could
reach would be that one class's. It clears `quest_template_addon`.`AllowableClasses` and saves
the original masks in `cw_quest_class_backup` first, so it is exactly reversible: run
`data/sql/manual/cw_class_quests_revert.sql` and delete the world SQL file, or the updater will
re-apply it on the next start. Uninstalling also restores the masks.

Ability rewards are still governed by `BlockOutsideSpellSources`, so a quest that would teach a
class ability grants nothing for that part. Its item, XP, gold and reputation rewards are
unaffected.

### Unlocking every item for every class

`data/sql/manual/cw_classless_items.sql` removes the class restriction from every item in the
game. It is not applied by the updater and must be run against your world database by hand.

> **This script is destructive.** It overwrites `item_template`.`AllowableClass` with `-1` for
> every item and keeps no backup, and the original masks cannot be recomputed. Back up
> `item_template` before running it. Players should clear their client `Cache` folder afterwards.
>
> If you installed this module before September 2026, an earlier version applied this script
> automatically on your first startup. Check with
> `SELECT * FROM acore_world.updates WHERE name = 'cw_classless_items.sql';`. If a row comes
> back, your `item_template` was already overwritten and only a backup will restore it.

---

## Commands

Everything the NPC and the addon do is also available as a chat command.

### `.classless`

| Command                                           | What it does                                      |
| ------------------------------------------------- | ------------------------------------------------- |
| `.classless status`                               | Mode, essence balances, spent totals              |
| `.classless mode classless\|wildcard`              | Choose your path, before the deadline level       |
| `.classless learn <spellId>`                      | Buy an ability with Ability Essence               |
| `.classless unlearn <spellId>`                    | Drop an ability. Refunds per config               |
| `.classless talent <talentId>`                    | Buy the next rank of a talent with Talent Essence |
| `.classless respec`                               | Full respec for gold                              |
| `.classless stats`                                | Show stat allocation and remaining points         |
| `.classless stat str\|agi\|sta\|int\|spi <points>` | Allocate points. Reallocation is free             |
| `.classless bar mana\|rage\|energy\|default`       | Pick which resource the main power bar displays   |
| `.classless archetypes`                           | List starter archetypes and their IDs             |
| `.classless archetype <id>`                       | Apply a starter build to a fresh Hero             |
| `.classless rebirth classless\|wildcard`           | Full reset and path switch. Costs gold            |

### `.wildcard`

| Command                             | What it does                                      |
| ----------------------------------- | ------------------------------------------------- |
| `.wildcard status`                  | Pending rolls, reroll charges, pity counter       |
| `.wildcard reroll <spellId>`        | Reroll a rolled ability                           |
| `.wildcard rerolltalent <talentId>` | Reroll a rolled talent                            |
| `.wildcard lock <spellId>`          | Lock an ability so future rolls cannot replace it |

### Addon slash commands

| Command               | What it does                            |
| --------------------- | --------------------------------------- |
| `/cw` or `/classless` | Open the Character Advancement panel    |
| `/cw help`            | Open the built-in guide to both systems |
| `/cwbars`             | Toggle the universal resource mini-bars |

### Addon key bindings

The addon takes **`N`**, the stock Talents key, for the advancement panel the first time it runs.
This module suppresses native talents, so that key would otherwise open an empty frame. The addon
only takes `N` while it is still bound to the talent frame. If a player has already rebound it,
the addon leaves it alone and uses the first free key among `J`, `Y`, `G` and `K`. All three
actions appear under **Key Bindings > ClasslessWildcard** and can be rebound.

| Binding                  | Default     |
| ------------------------ | ----------- |
| Toggle Hero Advancement  | `N`         |
| Toggle the Help guide    | *(unbound)* |
| Toggle the resource bars | *(unbound)* |

---

## How Wildcard rolls work

Detail behind the Wildcard path, for players who want to know what the dice are doing and admins
tuning the numbers below. `.wildcard status` reports your live pity count, synergy chance and
cooldowns.

### The roll

Candidates are every ability you do not already own whose rank-1 learn level you have reached,
minus anything on a reroll cooldown. One is picked at random, weighted by `RarityWeights`. If
nothing is legal at your level, the roll drops to the lowest-level entries still available rather
than the whole library, so it stays as close to your level as the remaining pool allows instead of
reaching for a level 70 ability. A roll comes up empty only if you already own the entire library,
at which point there is nothing left to hand you.

### Synergy and pity

Every ability and talent carries the class mask it came from, and your Hero's mask is the union
of everything you own. A synergy roll narrows the pool to entries sharing a class with that mask,
so the result fits your build. You get a chat message when one fires.

The chance is `SynergyBaseChance + (pity x SynergyIncrement)`, capped at 100. On the defaults
that is 10%, rising 10 points per pity point.

**Pity counts rerolls, not rolls.** Only rerolling raises it, never a scheduled level-up roll, so
a Hero who never rerolls sits at 10% for the whole game, and nine rerolls without a synergy hit
makes the tenth certain. A synergy roll resets pity, and so does Rebirth.

Synergy matters most early. Your mask only ever grows, and Wildcard opens with four random
abilities from up to four different classes, so within a few levels it covers most of the game
and the filter has little left to exclude.

### Talent rolls

A talent roll picks a talent, then rolls which rank you land on. The rank is drawn from every rank
above the one you already hold, up to that talent's maximum, weighted the same way abilities are.
It is **not** a step of one: roll into a talent you hold at rank 2 and you can land on rank 5
directly. A fresh talent is drawn from rank 1 to its maximum, so your first sight of a talent can
be its top rank.

You are granted that rank's spell, and it replaces the lower rank if you had one. You never hold
the intermediate ranks as separate things, which is the whole saving over the Classless path,
where each rank is bought one at a time.

The rank also sets the rarity shown, rank 1 common through rank 5 legendary, unless the talent's
own rarity is higher. That acts as a floor, so a talent set to epic in `cw_talent_override` never
reads as common at rank 1.

If the roll lands on a talent you already own, it upgrades and the Wildcard rolls again. That
chain runs to a maximum of four grants from one roll before it stops. Talents already at maximum
rank are excluded from the pool, so a roll is never spent on something that cannot improve.

### Reroll cooldowns

Rerolling something puts it on a cooldown so the reroll cannot immediately hand it back. This
applies to the free rerolls below level 10 exactly as it does to a charged one.

The cooldown is counted in rolls, not time, and it is long. The default `SynergyBanRolls` of 25
excludes a pick from the next 24 rolls, the replacement roll included. At roughly 1.5 rolls per
level that is about 16 levels: reroll Fireball at level 12 and it returns around level 28. That
makes rerolling a lasting decision rather than a do-over. Set it to about 3 if you only want to
stop an immediate repeat.

If every ability you could actually use is owned or on cooldown, the cooldowns are released and
the roll is taken from the full pool again. Level-appropriateness outranks the cooldown, so you
always get something you can cast. That is what keeps the first ten levels usable, where rerolls
are free and the legal pool is at its smallest. Talents work the same way against their tier.

Cooldowns are per character, survive logging out, and apply only to your own rerolls. They are
unrelated to `cw_ability_override`, which is how an admin removes an ability for everyone.

---

## Configuration

All 77 settings live in
[`conf/classless_wildcard.conf.dist`](conf/classless_wildcard.conf.dist) and are documented
inline. The ones most likely to need changing:

| Setting                                             | Default      | Meaning                                                       |
| --------------------------------------------------- | ------------ | ------------------------------------------------------------- |
| `ClasslessWildcard.Enable`                          | `1`          | Master switch                                                  |
| `ClasslessWildcard.DefaultMode`                     | `0`          | `0` classless, `1` wildcard                                    |
| `ClasslessWildcard.AllowModeChoice`                 | `1`          | Let players pick. `0` forces `DefaultMode` realm-wide           |
| `ClasslessWildcard.ModeChoiceDeadline`              | `5`          | Level after which the path locks                               |
| `ClasslessWildcard.IncludeDeathKnight`              | `0`          | Include DK abilities, which cost runes                         |
| `ClasslessWildcard.NpcEntry`                        | `990100`     | Hero Advancement NPC entry                                     |
| `Chassis.Enable`                                    | `1`          | Put every character on one base class                          |
| `Chassis.Class`                                     | `2`          | Which class. Mana classes only; others are refused at startup   |
| `Classless.StartingAbilityEssence`                  | `9`          | AE granted at character creation                               |
| `Classless.AbilityCostByRarity`                     | `1,2,3,5,8`  | AE cost per rarity tier                                        |
| `Classless.AbilityEssencePerLevel`                  | `1`          | AE per level from `EssenceStartLevel`                          |
| `Classless.TalentEssencePerLevel`                   | `1`          | TE per level                                                   |
| `Classless.TalentFlatCost`                          | `0`          | Charge only rank 1, so a talent costs 1 point total            |
| `Classless.RespecCostGold`                          | `50`         | Gold cost of a full respec                                     |
| `Wildcard.StartingAbilities`                        | `4`          | Abilities rolled at level 1                                    |
| `Wildcard.RollStartLevel`                           | `10`         | Level the roll schedule begins                                 |
| `Wildcard.TalentEveryLevels` / `AbilityEveryLevels` | `1` / `2`    | Roll cadence                                                   |
| `Wildcard.RarityWeights`                            | `100,...`      | Roll weights per rarity tier. Also picks talent rank           |
| `Wildcard.FreeRerollBelowLevel`                     | `10`         | Rerolls are free under this level                              |
| `Wildcard.ScrollBuyEnable`                          | `1`          | Buy Scroll button on the addon panel                           |
| `Wildcard.ScrollBuyBaseCopper` / `...PerLevelCopper`  | `500` / `500`| Scroll price in copper: base + per-level x level               |
| `UniversalResources.Enable`                         | `1`          | Mana, rage and energy on every character                       |
| `UniversalStats.SpellPowerPerIntellect`             | `0.5`        | Spell power per Intellect. 1 INT is worth about 1 STR          |
| `UniversalStats.MeleeAPPerAgility`                  | `1`          | Melee attack power per Agility                                 |
| `ClasslessWildcard.ClasslessClassChecks`            | `1`          | Any relic equips; shields and reactive abilities work          |
| `ClasslessWildcard.FormStarterKits`                 | `1`          | Forms and stances hand over their basic spells free            |
| `ClasslessWildcard.WorldDrops.Enable`               | `1`          | Mobs can drop the classless gear                               |
| `ClasslessWildcard.WorldDrops.Chance`               | `1.0`        | Percent per kill, banded to the mob's level                    |
| `ClasslessWildcard.WorldDrops.RareMultiplier`       | `5.0`        | Chance multiplier for rares, rare elites and bosses            |
| `ClasslessWildcard.WorldDrops.HeirloomChance`       | `2.0`        | Percent for a heirloom. Rares and bosses only; `0` disables    |
| `Stats.Enable` / `Stats.PointsPerLevel`             | `1` / `2`    | Primary stat allocation                                        |
| `Rebirth.Enable` / `Rebirth.CostGold`               | `1` / `100`  | Path switching after the mode lock                             |

### Per-spell and per-talent tuning

Rarity, cost, roll weight and an enable flag can be overridden for any individual spell or talent
through the `cw_ability_override` and `cw_talent_override` world tables. Use them to ban a
problem ability or make one legendary without rebuilding the module.

The abilities a form or stance hands over are also data, in `cw_form_kits`. It holds two spell ID
columns, so you can pair anything with anything, or set a row's `enabled` to `0` to drop just
that pair. Restart the worldserver after editing it.

---

## Notes and limitations

These follow from the stock 3.3.5a client and are not bugs:

- **The talent frame is unused.** Talents are granted as their underlying spells, and native
  talent points are set to zero. Everything you learn appears in the spellbook.
- **Death Knight abilities are disabled by default**, because they cost runes. Set
  `IncludeDeathKnight` to `1` to enable them along with the rune bar the addon draws.

---

## Uninstall

The module can be removed. Most of what it does is additive: its own tables, its own item and NPC
entries, and runtime hooks. The one large per-character change, cross-class spells, is cleaned up
by the core's own login validation after the module's SQL is removed.

The base class conversion is the exception. Characters keep the base class after uninstalling,
because their original class was never stored. Restore a pre-install backup to get it back.

<details>
<summary><b>Step-by-step revert</b></summary>

<br>

Do this with the worldserver stopped:

1. **Back up** your world and characters databases.
2. **Remove the code.** Delete `modules/mod-classless-wildcard`, re-run CMake, rebuild the
   worldserver, and delete `classless_wildcard.conf`.
3. **World database.** Run `data/sql/uninstall/cw_uninstall_world.sql` by hand. The updater never
   applies it. It drops the module's world tables, the scrolls, the item packs, the NPC
   (template, spawns and vendor lists) and the custom `skillraceclassinfo_dbc` rows, and clears
   the module's DB-updater bookkeeping.
4. **Characters database.** Run `data/sql/uninstall/cw_uninstall_characters.sql`. It drops the
   `cw_char_*` state tables and removes the taught proficiency spells.
5. **Start the server.** With the custom skill-validity rows gone, the core's own login
   validation (`ValidateSkillLearnedBySpells`, on by default) deletes every spell and skill that
   is invalid for a character's real class the next time they log in. Talent points return and
   the power bar reverts to the class default.
6. **Client side.** Players run `python3 install.py --uninstall "/path/to/WoW"`, which removes
   the patch archives and the addon, clears the cache, and restores `Wow.exe` if an older version
   of the installer patched it. Current versions do not touch it.

**What does not revert automatically:**

- **`manual/cw_classless_items.sql`**, if you ran it. It set `item_template.AllowableClass` to
  `-1` for every item and kept no backup, and the originals cannot be recomputed. Restore
  `item_template` from your pre-install backup, or re-import it from the AzerothCore base SQL
  matching your core revision. Quest class requirements do revert automatically: they are saved
  in `cw_quest_class_backup` and the uninstall script restores them before dropping the table.
- **Same-class spells.** Abilities a Hero was granted that are legal for its base class survive
  validation. They are harmless, and a GM can `.unlearn` them individually.
- **Characters created while the module was active** had their class starter spells and gear
  stripped and received the Hero starter kit instead. After the revert they relearn missing
  spells at a class trainer as normal, and the kit items are ordinary vendorable items.
- **Every Hero is effectively respecced** when their granted abilities disappear. This is
  inherent to removing a classless system. Tell your players before you revert.

To reinstall later, the uninstall scripts clear the DB-updater bookkeeping, so the module SQL
applies again on the next startup.

</details>

---

## Contributing

Issues and pull requests are welcome. When reporting a bug, please include your AzerothCore
revision, the module commit, how your `classless_wildcard.conf` differs from the `.dist` file,
and the worldserver log around the failure.

## License

GNU General Public License v2 or later, matching AzerothCore. `acore.json` declares GPL2, and
every core source header reads "version 2 of the License, or (at your option) any later version".
Full text in [`LICENSE`](LICENSE).

## Credits

Mechanics are modeled on the published Season 9/10 rules of
[Project Ascension](https://ascension.gg/)'s classless and Wildcard realms. This project is
unaffiliated with Project Ascension and with Blizzard Entertainment.
