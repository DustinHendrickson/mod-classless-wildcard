# mod-classless-wildcard

Ascension-style **Classless WoW** + **Season 10 Wildcard mode** for
[AzerothCore](https://www.azerothcore.org/) (master branch, WotLK 3.3.5a client).

Every character can learn **every spell and talent from every class**, either by
spending **Ability/Talent Essence** exactly like Ascension's classless realms
(free-pick), or by playing **Wildcard**: 4 random abilities at level 1, then a
random talent every level and a random ability every other level from level 10 —
with rarity-weighted rolls, rerolls via Scrolls of Fortune, lock-in of keepers,
Skill Card guarantees, synergy rolls and 25-roll bad-luck protection, replicating
Ascension's published Season 9/10 Wildcard rules.

See `PLAN.md` for the full research summary, architecture and roadmap.

## Features

- **Classless free-pick mode** — 9 starting Ability Essence, +1 AE / +1 TE per
  level from 10; abilities rarity-priced (1/2/3/5/8 AE); talents from all class
  trees bought per rank with prerequisites and tier rules enforced; unlearn
  refunds; full respec for gold; owned spell lines auto-rank-up while leveling.
- **Wildcard mode** — Ascension S10 schedule and mechanics: starting rolls
  (free rerolls until 10), per-level rolls, rarity weights (legendary rarest),
  Scroll of Fortune rerolls, the talent-upgrade-rolls-again rule, ability
  locking, Skill Cards (2+2 ability, 3+3 talent, locked from level 10),
  synergy rolls with rising pity chance and bad-luck bans.
- **Universal resources** — every Hero runs mana, rage AND energy pools at
  once, druid-style, with no client patch: the client already tracks all
  pools; the chassis picks the displayed bar and the addon draws mini-bars for
  the rest (`/cwbars`). Energy/mana regen and rage decay use the core's normal
  systems; rage gain for non-rage chassis mirrors the warrior formulas
  (tunable). Spells always draw their native resource, so a Warrior chassis
  really casts Fireball with mana and a Mage chassis really Bloodthirsts with
  rage.
- **Primary stat allocation** — Ascension's "choose your primary stats,
  reallocate at will": a per-level point budget spent on STR/AGI/STA/INT/SPI
  from the addon's Stats tab (+/- and Apply) or `.classless stat`, applied
  live, reallocation free.
- **Per-character mode opt-in** (or realm-wide via config).
- **Hero Advancement NPC** (entry 990100; spawned in Stormwind, Orgrimmar and
  Dalaran — every spawn carries the full gossip UI and vendor stock, and
  `.npc add 990100` places more anywhere) — gossip UI for everything, plus the
  scroll and item vendor.
- **Rerolls flow with leveling, like Ascension**: every scheduled roll grants a
  matching reroll charge (1 talent reroll per talent roll, 1 ability reroll per
  ability roll — configurable), rerolls are outright free below level 10, and
  cheap Scrolls of Fortune (50s / 25s) exist only as a top-up when charges run
  dry.
- **Command API**: `.classless status|mode|learn|unlearn|talent|respec`,
  `.wildcard status|reroll|rerolltalent|lock|card` — also the surface a future
  client addon can drive.
- **All proficiencies taught** (armor, weapons, dual wield — configurable) and
  optional SQL to make **every item usable by every class**.
- **In-game addon UI** (`client-addon/ClasslessWildcard/`) — a Character
  Advancement panel for the stock 3.3.5 client: class-tabbed ability browser
  with icons, tooltips and rarity colors, talent trees, My Hero tab
  (unlearn / reroll / lock), Wildcard tab (talent rerolls, cards, pity and
  synergy display), and a first-login onboarding wizard. Talks to the server
  over the `CWCL` addon channel — no client patch. The NPC and chat commands
  remain fully functional for players without the addon.
- **Onboarding**: first-login welcome plus starter **archetypes**
  ("Blade Dancer", "Battle Mage", "Ranger of the Light"…) that auto-spend a
  new Hero's starting essence on a role-focused build (`cw_archetypes` world
  table — add your own).
- **Exits**: classless respec for gold, wildcard rerolls, and **Rebirth** — a
  config-gated full reset that lets a character switch path (classless ↔
  wildcard) after the mode lock, for gold; wildcard rebirths replay the whole
  roll schedule.
- **Classless item pack**: 12 Ascension-flavored items sold by the NPC —
  intellect guns, strength javelins, mail tanking gear, plate caster sets,
  spellpower fist weapons and more. Server-side only.
- Everything tunable in `classless_wildcard.conf.dist`; per-spell/per-talent
  rarity, cost, weight and enable flags in the `cw_ability_override` /
  `cw_talent_override` world tables.

## Install

1. Clone into your modules directory:
   ```
   cd azerothcore-wotlk/modules
   git clone <this repo> mod-classless-wildcard
   ```
2. Re-run CMake and rebuild the worldserver.
3. Start the worldserver — the module SQL in `data/sql/db-world` and
   `data/sql/db-characters` is applied automatically by the DB updater.
4. Copy `conf/classless_wildcard.conf.dist` next to your `worldserver.conf`
   (or let the build install it) and tune to taste.
5. **Optional but recommended for the full Ascension feel:** apply
   `data/sql/db-world/optional/cw_classless_items.sql` to your world DB to
   remove class restrictions from all items (backup `item_template` first;
   players should clear their client `Cache` folder afterwards).
6. **Addon (recommended):** give players the `client-addon/ClasslessWildcard`
   folder to drop into their client's `Interface/AddOns/`. `/cw` opens the
   panel; it also pops an onboarding wizard on a fresh character and shows the
   universal-resource mini-bars (`/cwbars` toggles).
7. **Client MPQ patch (optional, recommended):** `client-patch/` builds a
   `patch-4.MPQ` that renames every class to **Hero** everywhere in the client
   (creation screen, character sheet, /who) — see `client-patch/README.md`.

## Notes & limitations (stock 3.3.5 client)

- The talent frame is not used; talents are granted as their underlying spells
  through the module (native talent points are zeroed). The spellbook shows
  everything you learn.
- A character keeps its chassis class for power type and base stats. Casters
  chassis (mana classes) are the most flexible base for spell-heavy builds;
  `ClasslessWildcard.CrossPowerCasting` (experimental, off by default) lets
  non-mana chassis cast mana spells.
- Death Knight spells are excluded by default (rune costs), configurable.
- Ascension's custom UI, mystic enchants, stat reallocation and multispec are
  Phase 2/3 — see `PLAN.md`.

## Uninstall / revert

Yes — the module is reversible. Almost everything it does is additive (its own
tables, its own item/NPC entries, runtime-only hooks), and the one big
per-character change (cross-class spells) cleans itself up automatically. Do
the steps in this order, **with the worldserver stopped**:

1. **Take a backup first** (world + characters DBs). Cheap insurance.
2. **Remove the code**: delete `modules/mod-classless-wildcard`, re-run CMake,
   rebuild worldserver. Delete `classless_wildcard.conf` from your config dir.
3. **World DB**: run `data/sql/uninstall/cw_uninstall_world.sql` by hand (it is
   never auto-applied). It drops the module's world tables, removes the
   scrolls, the item pack, the Hero Advancement NPC (template, spawns, vendor)
   and the custom `skillraceclassinfo_dbc` rows, and clears the module's rows
   from the DB updater's bookkeeping.
4. **Characters DB**: run `data/sql/uninstall/cw_uninstall_characters.sql`.
   It drops the `cw_char_*` state tables and removes the taught weapon/armor
   proficiency spells.
5. **Start the server.** The rest of the per-character cleanup is automatic:
   with the custom skill-validity rows gone, the core's own login validation
   (`ValidateSkillLearnedBySpells`, on by default) deletes every spell and
   skill that is invalid for a character's real class the next time that
   character logs in. Rolled cross-class abilities, cross-class weapon skills —
   all gone without touching the DB. Talent points come back automatically
   (they were only suppressed at runtime) and the displayed power bar reverts
   to the class default at login.
6. **Client side**: players delete `Data/patch-4.MPQ`, the
   `Interface/AddOns/ClasslessWildcard` folder, and their `Cache` folder.

What does **not** revert automatically:

- **`optional/cw_classless_items.sql`** (if you applied it) overwrote
  `item_template.AllowableClass` with -1 for all items. There is no way to
  recompute the original masks — restore `item_template` from your
  pre-install backup, or re-import it from the AzerothCore base SQL matching
  your core revision. (This is why the install notes say to back it up.)
- **Same-class spells** a character was granted (a Warrior who rolled warrior
  abilities) survive validation, since they are legal for the class. Harmless;
  a GM can `.unlearn` them case by case if desired.
- Characters created while the module was active had their class starter
  spells stripped and got the neutral weapon kit instead. After the revert
  they simply relearn missing spells at their class trainer (trainers work
  normally again); the kit weapons are ordinary items they can vendor.
- Wildcard/classless characters will effectively be respecced (their granted
  kit disappears) — that is the nature of removing a classless system.
  Announce the revert to players before doing it.

Reinstalling later is safe: the uninstall scripts also clear the module's DB
updater bookkeeping, so all module SQL re-applies cleanly on next startup.

## License

GNU AGPL v3, like AzerothCore.
