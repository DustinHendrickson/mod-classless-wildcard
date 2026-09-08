<div align="center">

<img src="docs/classless-wildcard-github-header.webp" alt="Classless Wildcard, an AzerothCore module for WotLK 3.3.5a. Every spell. Every talent. Every class. Or let the dice decide." width="100%">

<br>

[![AzerothCore](https://img.shields.io/badge/AzerothCore-master-blue?style=flat-square)](https://www.azerothcore.org/)
[![Client](https://img.shields.io/badge/client-WotLK%203.3.5a-c8952f?style=flat-square)](https://www.azerothcore.org/)
[![Language](https://img.shields.io/badge/C%2B%2B-17-00599C?style=flat-square)](src/)
[![Addon](https://img.shields.io/badge/client%20addon-included-a335ee?style=flat-square)](client-addon/)
[![License](https://img.shields.io/badge/license-GPL--2.0--or--later-green?style=flat-square)](#license)

### An [AzerothCore](https://www.azerothcore.org/) module for WotLK 3.3.5a

**Every character can learn every spell and every talent from every class.** Buy them with
Essence, or let the server roll for you in Wildcard mode.

It installs into `modules/` on an AzerothCore master build and needs a recompile, its own SQL and
a client patch every player runs. See [Requirements](#requirements) and [Install](#installation).

[What it is](#what-it-is) · [Features](#features) · [Install](#installation) · [Playerbots](#playerbots) · [Commands](#commands) · [Configuration](#configuration) · [Wildcard rolls](#how-wildcard-rolls-work) · [Hero line](#the-hero-line) · [Elemental variants](#elemental-variants) · [Uninstall](#uninstall)

</div>

---

> [!CAUTION]
> **This is a total server overhaul, and it is experimental.**
>
> It replaces the class system outright and rebuilds progression, resources, stats, gear and
> quest access around it. Plan a realm around it; do not add it to an existing one you care about.
>
> The [client patch](#client-every-player) is **required**. Every player must run it, or the
> game is broken for them.
>
> Installing changes character data and writes to core tables. It is [reversible](#uninstall),
> but back up your world and characters databases first.

---

> [!IMPORTANT]
> **What it runs on, and what it changes.**
>
> **A stock 3.3.5a client, patched by this module.** There is no custom client build, no
> launcher and no third-party patch to find. The installer in [`client-patch`](client-patch/)
> adds `Data/patch-Z.MPQ` and `Data/<locale>/patch-<locale>-Z.MPQ`, patches `Wow.exe` to accept
> custom interface files, and installs the ClasslessWildcard addon. The client's own archives are
> never edited, the edits ride in those two new ones, the executable is backed up before it is
> patched, and `--uninstall` returns the client to stock. Client and server must be installed
> from the same version of the module: the patch carries spell data the server loads too, and a
> mismatch shows wrong tooltips or fails casts.
>
> **Server SQL, and not only in this module's own tables.** The DB updater applies it on startup.
> It writes to `item_template`, `quest_template_addon`, `playercreateinfo`,
> `playercreateinfo_action`, `creature_template` and `npc_vendor`, and to the DBC override tables
> `spell_dbc`, `spell_ranks`, `talent_dbc`, `talenttab_dbc`, `skillline_dbc`,
> `skilllineability_dbc` and `skillraceclassinfo_dbc`. Original values are copied into backup
> tables first and the [uninstall](#uninstall) scripts put them back, but take your own backup of
> the world and characters databases before the first start.
>
> **Heroes out-scale classes, and some builds badly.** Every character can hold abilities and
> talents no single class could: a warrior's damage with a druid's heal over time and a paladin's
> immunity, cooldowns that were balanced against each other in separate kits, and the Hero line
> and elemental variants on top. Most builds land somewhere above a well-played class; a few
> specific combinations land a long way above, and the deck can hand one to a player who was not
> looking for it. Levelling content and five-mans are the first things to feel easy.
>
> This module deliberately does not touch encounter tuning, because how hard a realm should be
> is yours to decide. If the default game feels too easy, turn the creatures up in
> `worldserver.conf` rather than nerfing builds:
>
> ```
> Rate.Creature.Normal.HP                = 1.5
> Rate.Creature.Normal.Damage            = 1.3
> Rate.Creature.Normal.SpellDamage       = 1.3
> Rate.Creature.Elite.Elite.HP           = 1.5
> Rate.Creature.Elite.Elite.Damage       = 1.3
> Rate.Creature.Elite.Elite.SpellDamage  = 1.3
> ```
>
> The same three rates exist for `RARE`, `RAREELITE` and `WORLDBOSS`. Those numbers are a
> starting point, not a recommendation: raise them a little, play a few levels, and raise them
> again. Health alone makes fights longer without making them dangerous, so move damage with it.

> **No UI addon is guaranteed to work.** Every character is a single shared class that reads as
> Hero, one spellbook holds spells from all ten classes across extra tabs, the talent trees are
> served by this module rather than the client's own, and the resource bars show mana, rage and
> energy on a character the client thinks has one of them. An addon that keys off class, the
> spellbook, the talent frames, the paper doll or the power type can misread all of it, and some
> will throw Lua errors. The bundled ClasslessWildcard addon is the supported interface. Others
> may work, may look wrong, or may break, and none of them is tested here.

---

## What it is

`mod-classless-wildcard` removes the class system from WotLK 3.3.5a. Every character is a
**Hero**. Character creation offers a race and nothing else. Behind the scenes every Hero runs on
one shared base class that grants no abilities and locks nothing away, so race is the only choice
that carries anything, and it keeps its racial traits. Every ability and every talent is earned in
game and can come from any class.

There are two ways to earn them:

- **Classless.** Buy exactly the abilities and talents you want with Essence, priced by rarity.
- **Wildcard.** The Season 9/10 ruleset from Project Ascension. The server rolls abilities and
  talents on a fixed schedule. Players steer the result with rerolls, ability locks and bad-luck
  protection.

|                       | **Classless** (free pick)                                            | **Wildcard** (rolled)                                             |
| --------------------- | -------------------------------------------------------------------- | ----------------------------------------------------------------- |
| How you gain power    | Spend Ability Essence (AE) and Talent Essence (TE)                   | The server rolls abilities and talents for you                    |
| Starting kit          | 3 AE to spend as you like                                            | 4 random abilities at level 1                                     |
| Progression           | +1 AE per level from 4, +1 TE per level from 10                      | One roll per level from level 10, alternating ability and talent  |
| Cost model            | Abilities cost 1 / 2 / 3 / 5 / 8 AE by rarity, talents 1 TE per rank | Free but weighted. Legendary is rarest, and talent rank is rarity |
| Control over outcomes | Total. Unlearning refunds, and a respec drops the lot at once, free   | Rerolls, ability locks, synergy rolls, reroll cooldowns           |
| Changing your mind    | `.classless respec`                                                  | `.wildcard reroll`, Reroll Scrolls, Rebirth                       |

Both paths share the same resources, stats, proficiencies, NPC and addon. Players choose a path
per character, or the realm forces one through config. **Rebirth** switches paths later for gold.

The stock client still renders the class system it was built for, so the **client patch is
required**. It renames every class to Hero, removes the class picker, restores the ranged slot,
and installs the addon that players use to buy abilities and see rolls. See
[Client (every player)](#client-every-player).

---

## Screenshots

<div align="center">

<img src="docs/hero_creation.webp" alt="The WotLK character creation screen with no class list: the race panel on the left, and a Hero panel on the right listing what a Hero can do" width="96%">

<em><b>Character creation.</b> There is no class list. Pick a race, and the panel on the right<br>
tells you what every character gets: all armour and weapons, every resource, and any spell in the game.</em>

<br><br>

<img src="docs/advancement_panel.webp" alt="The Character Advancement panel: an ability browser, talent trees for every class, and the current build side by side" width="92%">

<em>The <b>Character Advancement</b> panel. Browse every class's abilities and talent trees,<br>
with your build on the right. Lock or reroll anything you own from the same window.</em>

<br><br>

<img src="docs/wildcard_roll.webp" alt="A Wildcard roll revealing Fireball: the die with the ability's icon in its window, the spell's cost, range, cast time and description below it, and Keep and Reroll buttons" width="42%">

<em>A <b>Wildcard</b> roll. The die lands on a new ability and shows its rarity,<br>
with everything its tooltip would say. Keep it, or spend a reroll.</em>

<br><br>

<img src="docs/stat_allocation.webp" alt="The primary stat panel with a row per stat showing the character's total and what it grants, and a tooltip breaking Spirit down further" width="72%">

<em><b>Primary stats.</b> Every row carries your total and what that total is worth,<br>
projected as you spend. Reallocating is free.</em>

</div>

---

## Features

### Building a Hero

- **Classless free pick.** Rarity-priced abilities, and talents from every tree bought a rank at
  a time with prerequisites enforced and each tier opening at its level (no points-in-tree
  total: a Hero draws from every tree at once). Unlearning an ability or a talent refunds its
  essence, a respec drops everything at once for free, and owned spell lines rank up as you
  level.
- **Wildcard rolls.** Free rerolls below level 10, rarity-weighted rolls, ability locking, and
  synergy rolls that favour classes you already own. A talent roll also rolls its rank, and rank
  is rarity: rank 1 is common, rank 5 is legendary, and landing on rank 5 hands you the full
  talent for free. See [How Wildcard rolls work](#how-wildcard-rolls-work).
- **Rerolls.** Every level from 10 grants 3 reroll charges, spent on abilities and talents alike.
  Anything you own can be rerolled later from **My Build**. Reroll Scrolls top the pool up, sold
  by the NPC and the addon at a price that scales with level.
- **Rebirth.** A full reset that also switches paths, available after the mode lock and gated by
  config. A Wildcard rebirth replays the whole roll schedule.
- **Archetypes.** Thirteen build templates a Classless Hero can follow from 1 to 80. Six mix
  two classes (*Blade Dancer*, *Battle Mage*, *Ranger of the Light*, *Shadow Mender*, *Stealthy
  Healer*, *Storm Warrior*) and seven are built around one element's variant strikes and the
  talent tree that feeds it (*Hellfire Knight*, *Rime Reaver*, *Stoneguard*, *Venomstalker*,
  *Nightclaw*, *Dawnward*, *Spellblade*). Following one replaces the current build and then buys
  each ability and talent rank with the Hero's own essence as it unlocks. Stop at any time and
  keep what was bought.
- **The Hero line.** Thirty-three abilities that belong to no class, in a Hero spellbook tab of
  their own, plus a 23-talent Hero tree that rewards drawing on several classes at once. See
  [The Hero line](#the-hero-line).
- **Elemental variants.** Twenty-seven weapon attacks each come in Fiery, Frozen, Earthen,
  Venomous, Arcane, Shadow and Holy forms: the same swing, cost and cooldown, dealt as the element,
  and each element does something of its own on hit -- a burn, a snare, an attack-speed cut, a
  healing cut, a bigger hit, lifesteal. See [Elemental variants](#elemental-variants).
- **Talents are talents, and spells.** A talent you buy is recorded as a real talent, so the
  stock talent frame shows it at the rank you own, and granted as its underlying spell, so it is
  in your spellbook too. You spend Talent Essence rather than talent points: the native point
  total stays at zero, whatever your level.
- **Ability talents are abilities.** A talent that teaches a spell, such as Pyroblast, Mortal
  Strike or Mangle, is not on the Talents list. The spell is in the Abilities list instead, at
  the level its talent tier would open, with every rank. Owning it meets any prerequisite on
  the old talent and counts as a point in that tree.

### Everything works on one character

- **No class to pick.** Character creation shows races only. Every Hero runs on the same
  Paladin chassis, which grants no class abilities and locks nothing away.
- **Universal resources.** Every Hero has mana, rage and energy at once. One shows on the main
  bar and the addon draws mini-bars for the rest. Each spell draws from its own resource, so the
  same Hero casts Fireball on mana and Bloodthirst on rage.
- **Death Knight abilities** are in the pool by default. Every Hero gets runes and runic power,
  and the addon draws the rune bar. Set `IncludeDeathKnight` to `0` to leave them out.
- **Primary stat allocation.** A point budget spent freely across STR, AGI, STA, INT and SPI,
  reallocated at any time for free. Because a build can point in any direction, the module also
  adds melee attack power per Agility, extra ranged attack power per Agility and spell power per
  Intellect. Hovering a stat in the addon shows what a point is worth at your level.
- **All proficiencies taught.** Armor, weapons and dual wield, each configurable.
- **The base class never restricts a build.** Any relic equips, shields work, and Overpower,
  Revenge, Riposte and Counterattack fire regardless of base class.
- **Every item is open to every Hero.** Class armour sets, all 353 glyphs, rogue poisons, soul
  bags, quivers and class-locked relics. The core checks an item's class mask before any script
  can answer, so this is done in the world database and reverts with
  `data/sql/manual/cw_item_classes_revert.sql`.
- **Abilities that need each other arrive together.** Cat Form brings Claw and Prowl, Bear Form
  brings Maul, Tame Beast brings Call Pet and the rest of the pet kit. It works the other way
  too: Rend and Charge bring Battle Stance, Shred brings Cat Form. Anything that arrives this way
  is free, is not one of your rolls, cannot be rerolled or unlearned on its own, and leaves when
  nothing you own still needs it. The pairs are rows in `cw_form_kits`, and neither side has to
  be a form.
- **No spell asks for a class tool.** Stoneskin Totem wants an Earth Totem and Runeforging wants
  a runeforge, tools handed to one class each. Every spell in the library drops that requirement,
  on the server and in the client patch, so it casts whoever earned it. Reagents are unchanged.
- **A summon leaves with its spell.** Reroll Summon Imp away and the imp is dismissed instead of
  standing there permanently. Rerolling Tame Beast away puts the tamed beast away too. The beast
  is kept, not destroyed, so rolling Tame Beast again calls the same one back.
- **Class quests are open to everyone.** Every chain is reachable by every Hero. A reward that
  would teach a class ability gives nothing for that part; items, XP, gold and reputation are
  unchanged. Reversible with `data/sql/manual/cw_class_quests_revert.sql`.

### Gear

- **A starter kit that fits any build.** A neutral outfit, a bag, one of every basic weapon
  type with ammunition, and food and water. Whatever a Hero learns or rolls first, they have
  something to use it with. Configurable under `StarterKit`.
- **A classless item catalogue.** 262 items with stat combinations the class system never
  allowed: intellect guns, strength staves, plate caster sets, spellpower shields, hybrid rings
  and more, tiered across level 1 to 80. The NPC sells them in level brackets and any mob can drop
  one banded to its level. Everything is server-side; players need no custom files.
- **Hero heirlooms.** 23 items that scale from level 1 to 80, including armor the original
  classes could never wear. Cheap to buy early, and rares and world bosses can drop one.

### In the world

- **Hero Advancement NPC** (entry `990100`). One in each capital city, Dalaran and Shattrath,
  beside the guild master. It carries the full advancement menu and the vendor. `.npc add 990100`
  places more.
- **Addon.** The Character Advancement panel, the Wildcard roll UI, resource bars, a first-login
  wizard and a Help guide. Everything it does is also a chat command.
- **Tooltips that count your talents.** The client only ever expected its own class's talents, so
  it will not apply an Improved Thunder Clap bought by a Hero: the spellbook kept reading 20 Rage
  while the server charged 16. The server sends what each spell really costs, casts and waits, and
  the addon puts those numbers on the tooltip.

---

## Requirements

- An AzerothCore **master** build you can recompile. The module adds C++ sources.
- A **3.3.5a** client for every player, with the client patch applied.
- **Python 3.7 or newer** on each player's machine, for the client installer.
- No core edits and no other module. `mod-playerbots` is supported, see [Playerbots](#playerbots).

---

## Installation

### Server

**1. Clone into your modules directory**

```bash
git clone https://github.com/DustinHendrickson/mod-classless-wildcard.git azerothcore-wotlk/modules/mod-classless-wildcard
```

**2. Re-run CMake and rebuild the worldserver**

```bash
cmake .. && make -j$(nproc)
```

**3. Start the worldserver.** The DB updater applies the SQL under `data/sql/db-world` and
`data/sql/db-characters` on startup. It creates the module's tables, the NPC, the item catalogue
and the vendor lists. Check the startup log to confirm the files applied.

**4. Configure.** Copy `conf/classless_wildcard.conf.dist` next to `worldserver.conf` as
`classless_wildcard.conf` and edit it. See [Configuration](#configuration).

### Client (every player)

Give players the `client-patch` and `client-addon` folders and point them at
[`client-patch/README.md`](client-patch/README.md). With WoW closed, they double-click
`install.bat` on Windows or run `./install.sh "/path/to/WoW"` on Linux and macOS. It needs
Python 3.7 or newer and installs the Pillow imaging library itself if it is missing. Running it
with `--uninstall` returns the client to stock.

It installs:

- the **ClasslessWildcard addon**
- every class shown as **Hero** on the creation screen, character sheet, `/who` and tooltips
- a single Hero entry per race on the creation screen, with the Hero outfit and emblem
- names, tooltips and icons for the elemental variants

The creation-screen text lives in a signed game file, so the installer also applies the standard
"allow custom interface" patch to `Wow.exe`. It backs the file up first.

### Every item is unlocked for every class

`data/sql/db-world/cw_world_item_classes.sql` clears `item_template`.`AllowableClass` on the
6,509 items that carry a class restriction, and is applied by the updater like the rest of the
module SQL. The core tests that mask in `Player::CanUseItem` and returns before any script hook
can answer, so the world database is the only place it can be done.

Without it a Hero is limited to the base class's items: no class armour set, no glyph but the
base class's, no rogue poison, no soul bag, and six relics that carry a class mask of their own
stay unusable however many druid or shaman spells the build has bought.

The original masks are copied into `cw_item_class_backup` first, so
`data/sql/manual/cw_item_classes_revert.sql` and the world uninstall script both put them back.
Players should clear their client `Cache` folder after the first apply.

> If you installed this module before September 2026, an earlier version shipped this as an
> opt-in script that kept no backup. Check with
> `SELECT * FROM acore_world.updates WHERE name = 'cw_classless_items.sql';`. If a row comes
> back, your `item_template` was already overwritten and only a backup will restore it.

---

## Playerbots

`mod-playerbots` works alongside this module. Bots are exempt from the classless system and play
by vanilla class rules, because playerbots initialises a bot's spells and talents from its class.

Exemption is by account name prefix, set with `ExemptAccountPrefixes` (default `rndbot`, which is
what playerbots uses). A character on a matching account keeps its real class, abilities, talent
points, trainers, stats and gear rules, and gets no essence, rolls or stat allocation. Only the
displayed class name changes: the client patch renames every class to Hero, so bots show as Hero
in the target frame, `/who` and inspect, exactly like players.

If your bots use accounts that do not start with `rndbot`, add your prefix to
`ExemptAccountPrefixes` or they will be converted to Heroes and lose their abilities.

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
| `.classless respec`                               | Unlearn everything at once. Free, and refunds all of it |
| `.classless stats`                                | Show stat allocation and remaining points         |
| `.classless stat str\|agi\|sta\|int\|spi <points>` | Allocate points. Reallocation is free             |
| `.classless bar mana\|rage\|energy\|default`       | Pick which resource the main power bar displays   |
| `.classless archetypes`                           | List the archetypes and their IDs                 |
| `.classless archetype <id>`                       | Follow an archetype. `0` stops following          |
| `.classless rebirth classless\|wildcard`           | Full reset and path switch. Costs gold            |

### `.wildcard`

| Command                             | What it does                                      |
| ----------------------------------- | ------------------------------------------------- |
| `.wildcard status`                  | Pending rolls, reroll charges, pity counter       |
| `.wildcard reroll <spellId>`        | Reroll a rolled ability                           |
| `.wildcard rerolltalent <talentId>` | Reroll a rolled talent                            |
| `.wildcard lock <spellId>`          | Lock an ability so future rolls cannot replace it |

### Addon

| Command                 | What it does                                       |
| ----------------------- | -------------------------------------------------- |
| `/cw` or `/classless`   | Open the Character Advancement panel               |
| `/cw help`              | Open the built-in guide to both systems            |
| `/cwbars`               | Toggle the universal resource mini-bars            |
| `/cwbars show \| hide`  | Set the mini-bars instead of toggling them         |
| `/cwbars lock \| unlock` | Pin the mini-bars in place, or let them be dragged |
| `/cwbars reset`         | Put the mini-bars back under the player frame      |

**Browsing.** Each pane's header carries its own controls. On the left is the sort order: by
level or tier, by name, or grouped by type. On the right is the level filter, **My level** or
**Any level**: My level lists only what the character can take at the level they are, Any level
lists the whole library. Abilities have a type filter between the two as well, for melee, ranged,
spells, heals, utility or passive. Both panes open on My level, and each remembers its own
choices per account.

**Padlocks.** A padlock holds an ability back from the starting hand's "Roll Abilities" pass,
which rerolls everything unlocked at once. That pass only exists below `FreeRerollBelowLevel`,
so at that level every remaining padlock is dropped, the button stops being offered, and rerolls
are one ability at a time and always the one you picked. A padlock can be set from the starting
hand, from **My Build**, from the Hero Advancement NPC or with `.wildcard lock`, and all four show
the same state.

The addon binds the advancement panel to **`N`**, the stock Talents key, unless the player has
already rebound it, in which case it uses the first free key among `J`, `Y`, `G` and `K`. The
panel, the Help guide and the resource bars can all be rebound under
**Key Bindings > ClasslessWildcard**.

The mini-bars remember where they were dragged to, per account. They show mana, rage and energy
always, and add a rune row, a runic power bar and a combo point row only while the character
actually has those, so nothing empty is left on screen.

The **Settings** button on the advancement panel has a checkbox per row -- mana, rage, energy,
runes, runic power, combo points -- plus the frame's own show and lock switches and a position
reset. Every row is on by default. Switching all of them off puts the frame away entirely.

---

## Configuration

All settings live in [`conf/classless_wildcard.conf.dist`](conf/classless_wildcard.conf.dist)
and are documented inline. Every name below is prefixed `ClasslessWildcard.` in the file. These
are the ones a realm usually touches; anything not listed is either a detail or something that
breaks the module when changed, which is why it is not a setting at all.

| Setting | Default | Meaning |
| --- | --- | --- |
| **the path a character takes** | | |
| `Enable` | `1` | Master switch |
| `DefaultMode` | `0` | `0` classless, `1` wildcard |
| `AllowModeChoice` | `1` | Let players pick. `0` forces `DefaultMode` realm-wide |
| `ModeChoiceDeadline` | `5` | Level after which the path locks |
| `Rebirth.Enable` / `Rebirth.CostGold` | `1` / `100` | Switching path after the lock, and its price |
| **what is in the pool** | | |
| `IncludeDeathKnight` | `1` | Death Knight abilities and talents, and runes for every Hero |
| `Forged.Enable` | `1` | The Hero line: 33 abilities and a talent tree of their own |
| `Elemental.Enable` | `1` | Elemental variants of physical strikes |
| `Elemental.RarityBump` | `1` | Rarity tiers a variant sits above its base attack |
| `Elemental.RollWeightPct` | `8` | How often a variant rolls, as a percent of its base's weight |
| `Elemental.InPool` | `1` | Variants can be rolled and bought. `0` stops new ones only |
| `Elemental.ShowInBrowser` | `1` | Variants appear in the addon's class menus and the NPC |
| **classless: what things cost** | | |
| `Classless.StartingAbilityEssence` | `3` | AE granted at character creation |
| `Classless.EssenceStartLevel` | `4` | First level that grants AE |
| `Classless.AbilityEssencePerLevel` | `1` | AE per level after it |
| `Classless.TalentEssenceStartLevel` | `10` | First level that grants TE |
| `Classless.TalentEssencePerLevel` | `1` | TE per level |
| `Classless.AbilityCostByRarity` | `1,2,3,5,8` | AE cost per rarity tier |
| `Classless.TalentFlatCost` | `0` | Charge rank 1 only, so a whole talent costs 1 TE |
| **wildcard: how rolls fall** | | |
| `Wildcard.StartingAbilities` | `4` | Abilities rolled at level 1. Four is the cap |
| `Wildcard.RollStartLevel` | `10` | Level the roll schedule begins |
| `Wildcard.AbilityEveryLevels` / `Wildcard.TalentEveryLevels` | `2` / `2` | Roll cadence. With `TalentRollOffset` 1 that is one roll a level, alternating |
| `Wildcard.RarityWeights` | `100,85,65,45,25` | Roll weight per rarity tier |
| `Wildcard.FreeRerollBelowLevel` | `10` | Rerolls are free under this level |
| `Wildcard.TalentUpgradePerScroll` | `20` | Percent per scroll staked on keeping a rerolled talent |
| `Wildcard.ScrollBuyEnable` | `1` | Buy Scroll button on the addon panel |
| `Wildcard.ScrollBuyBaseCopper` / `Wildcard.ScrollBuyPerLevelCopper` | `500` / `500` | Scroll price in copper: base plus per-level times level |
| **resources, stats and gear** | | |
| `UniversalResources.MaxRage` / `UniversalResources.MaxEnergy` | `1000` / `100` | Off-chassis pool sizes. The pools themselves are not optional |
| `UniversalStats.SpellPowerPerIntellect` | `0.5` | 1 INT is worth about 1 STR |
| `UniversalStats.MeleeAPPerAgility` | `1` | Melee attack power per Agility |
| `UniversalStats.RangedAPPerAgility` | `1` | Ranged AP per Agility, on top of the chassis's own |
| `Stats.Enable` / `Stats.PointsPerLevel` | `1` / `2` | Primary stat allocation |
| `FormStarterKits` | `1` | Forms and stances hand over their basic spells free |
| `WorldDrops.Enable` | `1` | Mobs can drop the classless gear |
| `WorldDrops.Chance` | `1.0` | Percent per kill, banded to the mob's level |
| `WorldDrops.RareMultiplier` | `5.0` | Chance multiplier for rares, rare elites and bosses |
| `WorldDrops.HeirloomChance` | `2.0` | Percent for a heirloom. Rares and bosses only |
| `NpcEntry` | `990100` | Hero Advancement NPC entry |

### Per-spell and per-talent tuning

Rarity, cost, roll weight and an enable flag can be overridden for any spell or talent through
the `cw_ability_override` and `cw_talent_override` world tables. Use them to ban a problem
ability or make one legendary without rebuilding the module. The abilities a form hands over are
rows in `cw_form_kits`. Restart the worldserver after editing any of them.

---

## How Wildcard rolls work

From level 10 you get one roll a level, alternating: an ability on even levels, a talent on odd
ones. `.wildcard status` reports your live pity count, synergy chance and cooldowns.

**The roll.** Candidates are every ability you do not own whose learn level you have reached,
minus anything on a reroll cooldown, picked at random and weighted by `RarityWeights`. If nothing
is legal at your level, the roll drops to the lowest-level entries still available rather than
the whole library.

**Synergy and pity.** Every ability and talent carries the class mask it came from, and your
Hero's mask is the union of everything you own. A synergy roll narrows the pool to entries that
share a class with that mask. The chance is `SynergyBaseChance + (pity x SynergyIncrement)`,
capped at 100, which on the defaults is 10% rising 10 points per pity point. Pity counts rerolls
only, never scheduled rolls, and a synergy roll or Rebirth resets it.

**Riding.** Riding is not in the classless library. It never rolls, it cannot be bought with
essence, and the module neither strips it nor reverts it if a Hero trains it at a trainer. Every
Hero is given it free as they reach the level for it:

| level | granted |
| --- | --- |
| 20 | Apprentice Riding |
| 40 | Journeyman Riding |
| 60 | Expert Riding |
| 68 | Cold Weather Flying |
| 70 | Artisan Riding |

The schedule is `Riding.Grants`, a list of `spell:level` pairs; set every level to 1 to grant them
all at character creation. `Riding.Enable = 0` turns the grant off and leaves riding to the
trainers. Cold Weather Flying is the permission to fly in Northrend rather than a skill rank.

**Mounts.** Vendor mounts, drops, reputation mounts and quest mounts carry no class mask, are not
in the library, and behave as they do on any realm.

The five class mounts are library abilities: **Warhorse**, **Charger**, **Felsteed**,
**Dreadsteed** and the **Acherus Deathcharger** sit on class skill lines with a class mask. They
are rolled or bought with Ability Essence like any other ability, gated at their learn level (20
for the basic pair, 40 for the epic pair, 55 for the Deathcharger), and cannot be learned from a
class trainer, which takes the spell back and refunds the gold.

Companion and vanity pets carry no class mask either, and are untouched.

**Ability rarity.** Rarity sets how often an ability rolls, what a Classless Hero pays for it and
what colour it is shown in. With no row in `cw_ability_override` it is taken from the strongest of
three signals:

| signal | measured from | default thresholds |
| --- | --- | --- |
| cooldown | the longest wait on any rank of the line, spell or category cooldown | `Rarity.CooldownSeconds` = 30 / 60 / 180 / 600 |
| talent row | the deepest talent row that teaches the line, where row R costs 5R points | `Rarity.TalentRows` = 2 / 4 / 6 / 8 |
| learn level | the level of the first rank, as a floor only and capped at rare | `Rarity.LevelFloors` = 25 / 50 |

The pool comes out around 53% common, 14% uncommon, 16% rare, 10% epic and 7% legendary. Fireball,
Backstab, Kick and Polymorph are common; Divine Shield, Ice Block, Mortal Strike and Bloodlust
epic; Lay on Hands, Rebirth and the 41-point capstones legendary.

A row in `cw_ability_override` replaces all of it (`rarity` 255 keeps the heuristic). Nothing is
overridden by default.

An elemental variant takes its base's rarity plus `Elemental.RarityBump` (1 by default), capped at
legendary, and rolls at `Elemental.RollWeightPct` of that rarity's weight (8% by default,
since each of the 27 bases gains seven copies). A variant follows its
base's final rarity, including one set by an override, and a base switched off by an override
takes its variants with it. A variant with its own row in `cw_ability_override` keeps exactly what
that row says.

**Talent rolls.** A talent roll picks a talent, then rolls the rank from every rank above the one
you hold up to the maximum. It is not a step of one: a talent you hold at rank 2 can land on
rank 5 directly, and a fresh talent can arrive at its top rank. The rank has its own weight
ladder, `TalentRankWeights`, defaulting to `100,75,50,25,10`, which makes rank 5 roughly a
twentieth as likely as rank 1. The rank sets the rarity shown, unless the talent's own rarity in
`cw_talent_override` is higher.

A roll only ever hands over a talent you do **not** already have, and an ability you already own
is never rolled either. **One roll grants exactly one thing.** Nothing you own is ever replaced or
taken by a roll: everything is additive.

**Deepening a talent.** Since a roll never raises a rank, the way to deepen a talent is to reroll
it and stake Reroll Scrolls on the outcome. A talent reroll costs its charge or scroll as usual
and trades the talent away for a new random one. Each extra scroll staked adds
`Wildcard.TalentUpgradePerScroll` percentage points (20 by default, on top of
`TalentUpgradeBaseChance`) to the chance that the talent is **kept and its rank raised** instead.
Five scrolls is a certainty on the defaults.

If the stake lands, the new rank is drawn from every rank above the one you hold on
`TalentRankWeights`, so it can jump more than one, and nothing is banned because nothing was given
up. If it fails, the scrolls are spent and the talent is traded away as normal. A talent already
at its maximum has no rank to win, so the stake is refused and the reroll goes straight out.

That makes the same button the choice between widening a build and deepening it: reroll for
something new, or pay to keep what you have and push it further. It is offered by the reroll die
in **My Build**, by the Hero Advancement NPC, and by `.wildcard rerolltalent <talentId> [scrolls]`.

**Reroll cooldowns.** Rerolling something puts it on a cooldown, counted in rolls, so the reroll
cannot hand it straight back. The default `SynergyBanRolls` of 25 excludes a pick from the next
24 rolls, which is 24 levels for a Hero who never rerolls. Set it to about 3 if you only want to
stop an immediate repeat. If everything you could use is owned or on cooldown, the cooldowns are
released so you always get something you can cast. Cooldowns are per character and survive
logging out.

---

## The Hero line

Thirty-three abilities that belong to no class, and a talent tree of their own. They are not
reused Blizzard spells: they are built by this module, and they file under a **Hero** tab in the
spellbook that no class has. A Classless Hero buys them with Ability Essence, Wildcard rolls
them, they carry rarity like anything else, and their ranks arrive with level.

Some of what is in there:

| Ability | What it does |
| ------- | ------------ |
| **Makeshift Strike** | A weapon strike that gives back a little mana, rage and energy |
| **Second Nature** | Restores a percentage of your mana, rage and energy at once |
| **Reclaimed Sentry** | Deploys a salvaged turret that fires on what comes near and strips its armor |
| **Venom Beetle** | A pet that learns a second and third poison as you level, and a healing one from a talent |
| **Cairn**, **Waystone**, **Signal Fire**, **Rally Point** | Markers planted beside you that help allies and hinder enemies around them |
| **Quickening** | Spends all your rage and energy for attack and casting speed |
| **Repertoire** | Pays you for using a different ability each time instead of the same one twice |
| **Wildcard Surge** | Arcane damage that grows with how many Epic and Legendary abilities you know |
| **Antipode Blast** | Fire and Frost in one cast, and the target keeps burning |
| **Hurl**, **Wide Arc**, **Crossdraw**, **Ricochet Shot** | Throws, sweeps, a spell-then-strike combo, and a shot that bounces |

### The Hero talent tree

Twenty-three talents in four columns, bought and rolled exactly like a class tree. Half of them
change what an ability does rather than what it adds up to:

| Talent | What it changes |
| ------ | --------------- |
| **Improvised Arsenal** | Makeshift Strike cuts Hurl's cooldown, so the cheap swing pays for the expensive throw |
| **Field Repairs** | Second Nature and Adrenaline also break snares and roots |
| **Last Reserve** | Ward Off refunds its cooldown when the shield is absorbed to the last point |
| **Opportunist** | Pocket Sand, Vertigo and Sinkhole pay energy for every enemy they catch |
| **Weave** | Every few Hero abilities, one refunds its cost, as long as you keep casting them |
| **Field Study** | Emberfeed refunds its cost against a target already bleeding from Bleed Over |
| **Venom Handler** | When an enemy dies with your Venom Beetle's poison on it, the beetle plants it on enemies near the body |
| **Medicinal Venom** | Your Venom Beetle learns Healing Spit and lands it on whoever in your party is hurt worst |
| **Broad Strokes** | Overflow's spill reaches you too, however far away its target is |
| **Overclocked** | Your Reclaimed Sentry fires twice as often |
| **Ricochet Chamber** | Ricochet Shot bounces again |
| **Two Schools** | Damage in a different school from your last hit is increased |
| **Jack of All Trades** | Damage and healing rise for every three classes you own an ability from |

The last two are the reason the tree exists: neither is worth a point to a build that stays in
one class. The rest of the tree is ordinary and useful, sharpening what you place (*Scavenger's
Eye*, *Wider Net*, *Quick Deploy*), what you throw (*Sharpened*, *Long Reach*) and what your
reserves cost (*Thrift*, *Overdraw*).

The Hero abilities and the tree both need the client patch for their names, tooltips and icons.
The startup log prints the generation id the server loaded and the client installer prints the id
it applied; if the two disagree, reinstall the patch. `Forged.Enable` turns the whole line off,
which is only safe before anyone has been given one.

---

## Elemental variants

<div align="center">

<img src="docs/elemental_variants.webp" alt="Backstab's icon followed by its seven elemental variants, each badged along the bottom edge for Fire, Frost, Earth, Poison, Arcane, Shadow and Holy" width="72%">

<em>A variant keeps its base attack's icon and adds a badge for the element.<br>
Left to right: the base attack, then Fire, Frost, Earth, Poison, Arcane, Shadow, Holy.</em>

</div>

Twenty-seven physical weapon attacks exist in seven elemental forms each, every rank included:
**Fiery**, **Frozen**, **Earthen**, **Venomous**, **Arcane**, **Shadow** and **Holy**. A Fiery
Sinister Strike has the same energy cost, swing, combo point and rank chain as Sinister Strike.

What changes is the damage, and what the strike does on top of it. The damage is dealt as the
element instead of Physical, so armour does not reduce it and resistance does, and anything that
increases your Fire damage increases a Fiery strike. The attack keeps 85% of its weapon
multiplier (75% for Holy, which almost nothing resists), and the rest of its power goes into the
element:

| | Element | What the element does |
| :-: | ------- | ------------------- |
| <img src="docs/badges/fire.png" alt="" width="20"> | Fire | Burns the target over 6 seconds |
| <img src="docs/badges/frost.png" alt="" width="20"> | Frost | Slows the target's movement by 30% for 6 seconds |
| <img src="docs/badges/earth.png" alt="" width="20"> | Earth | Slows the target's attacks by 10% for 6 seconds |
| <img src="docs/badges/poison.png" alt="" width="20"> | Poison | Poisons the target over 12 seconds |
| <img src="docs/badges/arcane.png" alt="" width="20"> | Arcane | An extra hit, half again as large as any other element's |
| <img src="docs/badges/shadow.png" alt="" width="20"> | Shadow | Reduces healing the target receives by 20% for 6 seconds |
| <img src="docs/badges/holy.png" alt="" width="20"> | Holy | Heals you for 25% of the damage the strike deals |

Fire, Poison and Arcane are damage; Frost, Earth and Shadow trade that damage for control; Holy
trades it for sustain. Fire and Poison deal half again what Arcane's hit does, spread over their
ticks, and like Arcane they grow with your spell power, so those four reward Intellect as well as
attack power.

A handful of attacks cannot take their element's effect, because a spell carries one duration and
theirs is already spoken for: Overpower's lasts a millisecond, Maim's is bought with combo points
and Mangle's is a minute. Those get Arcane's extra hit instead, and so do Shadow's Mortal Strike
and Aimed Shot, which already cut healing on their own. Seventy-five of the 1,085 variants fall
back this way. Mocking Blow and Deadly Throw have no variants at all.

The attacks with variants: Sinister Strike, Backstab, Ambush, Hemorrhage, Heroic Strike, Cleave,
Whirlwind, Overpower, Mortal Strike, Devastate, Raptor Strike, Multi-Shot, Aimed Shot, Kill Shot,
Claw, Shred, Ravage, Maul, Maim, Swipe (Cat), Mangle (Cat), Mangle (Bear), Fan of Knives and,
when Death Knight abilities are enabled, Blood Strike, Plague Strike, Obliterate and Death
Strike.

Variants are obtained like any other ability, one rarity tier above the attack they come from,
and roll less often so they do not crowd the pool. They file under the base attack's spellbook
tab, and owning a base attack and one of its variants together is allowed. The `Elemental`
settings turn them off, keep them out of rolls and purchase, or hide them from the menus.

The client patch adds their names, tooltips and icons. The badged icons need Python's Pillow
library, which the installer adds itself. Without it a variant shows its base attack's icon.

---

## Uninstall

Most of what the module does is additive: its own tables, items, NPC and runtime hooks. After the
module's SQL is removed, the core's own login validation cleans up cross-class spells.

The base class conversion is the exception. Characters keep the base class after uninstalling,
because their original class was never stored. Restore a pre-install backup to get it back.

<details>
<summary><b>Step-by-step revert</b></summary>

<br>

Do this with the worldserver stopped:

1. **Back up** your world and characters databases.
2. **Remove the code.** Delete `modules/mod-classless-wildcard`, re-run CMake, rebuild the
   worldserver, and delete `classless_wildcard.conf`.
3. **World database.** Run `data/sql/uninstall/cw_uninstall_world.sql` by hand. It drops the
   module's world tables, the scrolls, the item catalogue, the NPC and the custom
   `skillraceclassinfo_dbc` rows, restores quest class requirements, and clears the module's
   DB-updater bookkeeping.
4. **Characters database.** Run `data/sql/uninstall/cw_uninstall_characters.sql`. It drops the
   `cw_char_*` tables and removes the taught proficiency spells.
5. **Start the server.** The core's login validation (`ValidateSkillLearnedBySpells`, on by
   default) deletes every spell and skill that is invalid for a character's real class the next
   time they log in. Talent points return and the power bar reverts to the class default.
6. **Client side.** Players run the installer with `--uninstall`, which removes the patch
   archives and the addon, clears the cache, and restores `Wow.exe`.

**What does not revert automatically:**

- **Item class masks cleared by the OLD opt-in `manual/cw_classless_items.sql`**, if you ran that
  version. It kept no backup, so `cw_item_class_backup` has nothing to restore for those rows:
  re-import `item_template` from the AzerothCore base SQL for your revision. Masks cleared by the
  current `cw_world_item_classes.sql` are restored automatically.
- **The generated spell rows.** The Hero line and the elemental variants stay behind in
  `spell_dbc`, `spell_ranks`, `talent_dbc`, `talenttab_dbc`, `skillline_dbc` and
  `spell_script_names`. Nothing grants them once the module is gone and the login validation
  takes back any a character still holds, so they are inert. To clear them out anyway, delete
  ids `950000`-`957167` and `960000`-`962047` from the spell tables, `9000`-`9022` from
  `talent_dbc`, and `990` from `talenttab_dbc` and `skillline_dbc`.
- **Same-class spells.** Abilities that are legal for the base class survive validation. They are
  harmless, and a GM can `.unlearn` them.
- **Characters created while the module was active** received the Hero starter kit instead of
  class starter spells and gear. They relearn missing spells at a class trainer as normal.
- **Every Hero is effectively respecced** when their granted abilities disappear. Tell your
  players before you revert.

To reinstall later, the uninstall scripts clear the DB-updater bookkeeping, so the module SQL
applies again on the next startup.

</details>

---

## Contributing

Issues and pull requests are welcome. When reporting a bug, include your AzerothCore revision,
the module commit, how your `classless_wildcard.conf` differs from the `.dist` file, and the
worldserver log around the failure.

## License

GNU General Public License v2 or later, matching AzerothCore. Full text in [`LICENSE`](LICENSE).

## Credits

Mechanics are modeled on the published Season 9/10 rules of
[Project Ascension](https://ascension.gg/)'s classless and Wildcard realms. This project is
unaffiliated with Project Ascension and with Blizzard Entertainment.
