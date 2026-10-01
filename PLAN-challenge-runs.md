# Challenge runs: build plan

A third way to play a Hero, after the Classless and Wildcard paths: a **roguelite run**.
A challenge run is a character that levels under a hard rule it cannot turn off (every
enemy is an elite, no chest or legs, no healing abilities), draws its build by choosing
one of three random abilities or talents at each roll, and either reaches the level cap or
dies. Dying ends the run and pays out **shards**. Finishing pays out a reward that exists
nowhere else: gold, an ability, or a talent that is never rolled and never sold.

**Status (2026-09-30): built.** Steps 1 to 4 and 6 of section 7 are in: the run, lives,
drafts, all thirteen rules, shards and the extra life, the titles and the header. The
server side is `ClasslessMgr.cpp` (the run) and `ClasslessChallenges.cpp` (the rules);
the addon has the challenge page, the draft window, the hearts and the two popups. What
differs from the plan below:

- **A nemesis is not renamed.** The client caches a creature's name per entry from its
  query response and never asks again, so `SetName` on one creature changes nothing on
  screen. A nemesis is marked by its level, its elite stats and a 25% larger model
  instead. The chat line still names it.
- **Step 5 is built for abilities, not talents.** Seven reward lines (`reward=True` in
  `gen_forged_spells.py`: Grudge Strike, Giantsbane, Unbroken Will, Turnabout,
  Shatterpoint, Flashfire, Stolen Hour) are paid by Nemesis, Elite World, Hardcore,
  Pursued, Glass, Wildfire and Borrowed Time as heirlooms. The six one- and two-life
  challenges pay gold and a title only. No reward talents and no shard shop for the
  rewards of finished challenges; `test_forged.py` ties the flag, the SQL row and the
  C++ table together.
- The challenge list is a table in `ClasslessMgr.cpp`, not a world table: the rules are
  code, so a database row would only have held the lives and the gold.
- A fresh-character run needs the Hero to have chosen a path first; the first-login
  wizard was not changed. Runs respect the path: a Wildcard run drafts its rolls, a
  Classless run buys as ever, and Pursued and Wildfire pay essence instead of drafts.
- **The draft was cut (2026-10-01).** Section 2.2 below planned every Wildcard roll on a
  run as a pick of one from three. That was a misreading of the brief: the pick-of-three
  belonged to one challenge idea that was itself cut, not to runs in general. A run now
  changes nothing about how either path plays: Wildcard rolls and earns rerolls as ever,
  Classless buys with essence. Only the rule and the lives are added.
- **The rule set was redesigned after review (2026-10-01).** Seven of the first thirteen
  took something away instead of changing the fight (One Pool, Borrowed Time, Bare
  Shoulders, Silent, Wildfire, Ironborn, Pacifist Opening, Famine) and their life counts
  were arbitrary. They are cut, ids 6 to 13 retired. The twelve that ship are Nemesis,
  Elite World, Legion, Pursued, Hourglass, Glass, Spiteful, Bloodpact, Berserker, Ironman,
  Big Game Hunter and Hardcore, with lives set by how often the rule itself kills: five
  where the world is turned up, three where the fight changes shape, and one only for
  Hardcore, where the rule is death. Section 3 below is the original list, kept as the
  record of what was tried.
- The titles are the module's own rather than stock ones: `TITLES` in the generator,
  written to `chartitles_dbc` and appended to the client's CharTitles.dbc on bits 143 and
  up. One per Rebirth rank, "the Unbroken", and one per challenge.

This was a plan before it was an implementation. It follows the Rebirth work (New Game
Plus) and reuses its pieces: the Rebirth rank on `cw_char_state`, the heirloom source, the
reset to level 1 and the quest wipe. Design decisions are marked as such.

---

## 1. What the module already gives us

- **Rebirth** (`ClasslessMgr::Rebirth`): the reset to level 1, the quest wipe, gear into
  bags, the teleport to the start. A challenge run starts with exactly this, plus a rule.
- **The roll** (`RollAbility`, `RollTalent`): one random entry from the weighted pool with
  bans, synergy and pity. "Pick one of three" is three of these rolls shown together and
  two of them discarded, with no new weighting to invent.
- **The starting hand** (`cw_forged`'s reveal, the addon's `hand` frame): already shows a
  set of cards with lock and reroll per card. A draft of three is a hand of three with one
  lock allowed and no reroll.
- **Grant sources** (`GrantSource`): a run's reward ability is `Heirloom` so it survives a
  later Rebirth, is never rerolled and never refunded. A new source is not needed.
- **UnitScript hooks** (`cw_forged_talents`): the module already scales outgoing damage and
  healing for every Hero. A rule that scales incoming damage, or forbids a school, is one
  more branch there.
- **`cw_forged` spell generation**: a reward ability or talent that exists nowhere else is
  one more recipe in `gen_forged_spells.py`, flagged so it never enters the roll pool.

## 2. The run

### 2.1 Starting one

From the Rebirth picker, a third button: **Challenge run**. It is a Rebirth with a rule, so
it needs the level cap, costs the same and raises the Rebirth rank the same way (a Hero
that finishes a run has done a full 1 to 80 and earned the rank). Design decision: a run
can also be started on a **fresh character** from the first-login wizard, so a player
does not need an 80 to try the mode. A fresh-character run raises no Rebirth rank.

The player picks one challenge from the list (section 3), sees its reward, and confirms.
Heirlooms still come along: the challenge is about the rule, not about starting empty.

### 2.2 Drafting

Every scheduled roll, ability or talent, becomes a **draft of three**: the server rolls
three entries and sends `DRAFT|<kind>|a:b:c`; the addon shows them as a three-card hand;
the player clicks one; the client sends `DRAFT <index>`; the server grants that one and
bans the other two from coming straight back, the way a reroll does. Reroll charges are
not earned on a run and scrolls do nothing: the draft is the only choice there is.

The Classless path has no rolls to turn into drafts, so a run is always drafted. The
essence economy is off for its duration (`mode` stays `Wildcard`, a `run` column on
`cw_char_state` says which challenge is live).

### 2.3 Lives

Every challenge has a number of **lives**, from one to five, on its row in `cw_challenges`.
A death on a run costs a life, and some challenges do something on top of that (section
3): the Nemesis challenge makes the killer stronger, Hardcore takes the life and a level.
`cw_char_state.lives` holds what is left; the header shows it as hearts beside the
challenge name, and each death shows a popup: what was lost, what is left, what changed.

Death is caught on `OnPlayerKilledByCreature` and `OnPlayerPVPKill`, the two
PlayerScript hooks the core has (`PlayerScript.h:264` and `:252`), with the killer in
hand for the challenges that need it. While lives remain
the character resurrects as normal: nothing about the run changes except the count and
whatever the challenge adds. A **free death** is one the rule does not count, and there
are two: dying in a battleground or arena, and dying to a duel. Both would otherwise be
the cheapest way to lose a run on purpose or to grief one.

### 2.4 Running out

The last life ending is what ends the run. The server:

1. Writes the run's outcome to `cw_char_runs` (guid, challenge, level reached, lives used,
   finished or not, when).
2. Pays **shards** into `cw_char_state.shards`: one per level reached, doubled past 60, and
   a third again for a run that used no life at all.
3. Clears the `run` and `lives` columns. The character keeps its level, build and gear and
   is an ordinary Wildcard Hero from then on: nothing is taken, the rule simply lifts.

Design decision: running out of lives does not reset the character to level 1. Losing the
run is the cost; losing the character as well makes nobody start a second one. A player
who wants to try the same challenge again starts a new run from the picker, which is a
Rebirth, so the rank still climbs and the heirlooms still come along.

### 2.5 Finishing

Reaching the cap with a life still in hand writes the same row with `finished = 1`, lifts
the rule, pays the shards and the challenge's reward (section 4). A challenge that was
finished is marked on the picker with the lives it took, and pays only shards the second
time. Finishing without losing a single life is recorded on its own and is what the
"Unbroken" titles in section 4 are for.

## 3. The challenges

All unlocked from the start. Design decision: shards buy rewards (section 4), not
challenges, because a locked list is a list the player has not seen yet, and the point
of a list is choosing from it. Each challenge is one rule and a life count, enforced in
one place. Lives are the difficulty dial: a rule that makes the world harder gets more of
them, a rule that only takes something away gets one or two.

| Challenge | Lives | Rule | Where it lives |
|---|---|---|---|
| **Nemesis** | 5 | Whatever kills you is marked. It gains five levels, becomes elite, keeps your name in its own ("Grimtooth, Bane of Kaelen"), and stays that way for the run. Kill it to take the levels back as a burst of XP. A nemesis that kills you again gains five more. | `OnPlayerKilledByCreature` gets the killer: its entry goes on `cw_char_nemeses` with the level it reached. `cw_forged_talents::OnUnitEnterCombat` reads that table when a creature of the entry engages this Hero and applies the level, rank and name through `SetLevel`, `SetMaxHealth` and `SetName`. `OnPlayerCreatureKill` on a marked entry pays the XP and clears the row. Spawns are per entry, not per creature, so the nemesis is every boar of that kind until one falls. |
| **Elite World** | 5 | Every creature the Hero fights has elite rank: triple health and double damage. | `UnitScript::ModifyMeleeDamage` / `ModifySpellDamageTaken` for the damage; health is scaled on first aggro in `OnUnitEnterCombat` by `SetMaxHealth` with a flag aura so it is done once. |
| **Hardcore** | 3 | A death costs a life and a level. The level comes off with `GiveLevel(level - 1)` and the XP bar empties. | The death hook. Rebirth already proved the level drop path. |
| **Pursued** | 3 | Every ten minutes a hunter spawns at your position: your level plus two, elite, and it tracks you across the zone until one of you dies. Each one killed is worth a draft of three. | A ticking timer in `OnPlayerUpdate`; the hunter is a marker summon that acts, the way the sentry does, with `MoveChase` on the Hero and a despawn on the Hero's death or logout. |
| **Glass** | 3 | Health is halved. Damage done is up by a third. | `OnPlayerAfterUpdateMaxPower`'s sibling for health, `ModifyMeleeDamage` and `ModifySpellDamageTaken` for the bonus. |
| **Borrowed Time** | 3 | Every death lends a level: you keep it, but the next five levels are earned at half XP. | The death hook sets a counter; `OnPlayerGiveXP` halves the award while it runs, and `OnPlayerLevelChanged` counts it down. |
| **Bare Shoulders** | 2 | No chest, legs or shoulder slot. | `PlayerScript::CanEquipItem` refuses the slots; on run start the three are unequipped by `UnequipAllToBags`'s loop limited to those slots. |
| **Silent** | 2 | No ability of the Holy or Nature school; heals only from potions, bandages and the beetle. | `PlayerScript::CanCastSpell`-style refusal when the school matches. The draft never offers one. |
| **One Pool** | 2 | Only one resource bar: mana, rage or energy, chosen at the start. The other two are empty for the run. | `OnPlayerAfterUpdateMaxPower` returns 0 for the two pools not chosen. |
| **Wildfire** | 2 | Your abilities change. Every level, one owned ability is swapped for a draft of three, chosen for you at random. Nothing is locked. | `HandleLevelUp` picks an owned non-heirloom line, removes it, and sends a `DRAFT`. |
| **Ironborn** | 1 | No rest. Resting restores nothing; food and drink do nothing out of combat. | `OnPlayerUpdate` clears the rested state; `OnPlayerSpellCast` refuses food and drink spell families. |
| **Pacifist Opening** | 1 | No kills before level 10. XP comes from exploration and quests only; a kill before 10 costs the life. | `OnPlayerCreatureKill` ends the run when the level is under 10. |
| **Famine** | 1 | No vendors. Nothing can be bought, only looted, crafted or quested. | A refusal in the vendor gossip hook the module already drives for its own NPC. |

Design decision: one rule per challenge, never a pair. A pair of rules is read as the harder
one, and the lesser one just adds annoyance. Nemesis is the one to build first: it is the
only challenge whose rule makes dying interesting rather than merely costly, and its
pieces (a per-character creature table, `OnUnitEnterCombat`, the kill hook) are shared by
Pursued and Elite World.

Two things Nemesis has to get right, found while reading the core for it:

- **Rank and level are per creature, not per spawn.** `Unit::SetLevel` is public and
  `Creature::SelectLevel` (public, `Creature.h:66`) rebuilds health, mana and damage from
  the template's class and the level now set, so marking happens on engage, not on
  spawn, and never touches `creature_template`. The elite multiplier is applied after
  that with `SetMaxHealth`. The name is `WorldObject::SetName`, which the client picks up
  on the next update block.
- **A nemesis that respawns elsewhere is the same nemesis.** The mark is on the entry,
  so a player cannot shake it by moving on; a player who leaves the zone simply has a
  nemesis waiting at home. Design decision: a nemesis that is never killed is cleared at
  the end of the run with no penalty, since the run already ended.

## 4. Rewards

Finishing a challenge pays the reward on its row. The three kinds:

- **Gold.** A flat purse scaled by the level cap, for the challenges that are about
  endurance (Ironborn, Famine).
- **A forged ability.** One of eight recipes added to `gen_forged_spells.py`, each tied to
  the challenge it rewards and flagged `reward=True` so `BuildLibrary` keeps it out of the
  roll pool and the essence shop. It is granted with `GrantSource::Heirloom`. Examples: Elite
  World pays **Giantsbane**, a strike that does more against anything with more health than
  you; Glass pays **Shatterpoint**, a burst that costs health instead of mana.
- **A talent.** One hero talent per challenge, in a new row of the Hero tab the Rebirth
  rank reveals, granted as a Rebirth-only passive the same way the talents the C++ reads
  are: by icon, through `HeroTalentAmount`.

Shards buy the cosmetic and convenience side at the Hero Advancement NPC: a second
heirloom slot for the next Rebirth, **one extra life** for the next run (once per run, so
a five-life challenge can be started with six but never seven), the reward abilities of
challenges the player has finished once, so a second character can own them without a
second run, and titles. Titles are earned rather than bought where the run itself is the
proof: "the Unbroken" for finishing any challenge without losing a life, "Nemesis" for
finishing Nemesis, and "the Hunted" for finishing Pursued.

## 5. Data

```
cw_char_state   + run      TINYINT UNSIGNED  NOT NULL DEFAULT 0   -- challenge id live, 0 none
                + lives    TINYINT UNSIGNED  NOT NULL DEFAULT 0   -- left on the live run
                + shards   INT UNSIGNED      NOT NULL DEFAULT 0
cw_char_runs      guid, challenge, level_reached, lives_used, finished, finished_at
cw_char_nemeses   guid, creature_entry, level, kills_of_you          -- Nemesis marks, per run
cw_challenges     id, name, rule, lives, reward_kind, reward_ref, shard_cost  -- world DB
```

The run column goes on `cw_char_state` through the same guarded upgrade file pattern as
`cw_characters_rebirth.sql`.

## 6. The addon

- The Rebirth picker gets the **Challenge run** button and a second page listing the
  challenges with rule, reward and best result.
- The draft uses the existing hand frame with three cards, a lock on none and reroll on
  none. The reveal animation plays once for the three.
- The header shows the live challenge and its lives beside the Rebirth rank:
  `Wildcard   Rebirth 2   Nemesis  ♥♥♥♡♡`. The crest's glow turns red for the run.
- A death on a run shows one popup: the life lost, the lives left, and what the rule
  did about it ("Grimtooth is now level 17 and elite. It remembers you.").
- The last life ending shows a different one: the level reached, the shards paid, what
  the rule was, and the picker's button to try again.

## 7. Order of work

1. `run`, `lives` and `shards` columns, the runs table, the challenge list, and
   `StartRun` / `LoseLife` / `EndRun` on the manager with the two death hooks and the
   free-death exemptions. No rules yet: a run that can be started, died on until the
   lives are gone, and finished, paying shards. Testable with the flow harness.
2. Nemesis: the marks table, the engage hook, the kill hook. The first rule, because it
   is the one that makes a life worth losing, and its pieces carry the others.
3. The draft: `DRAFT` message, the addon's three-card hand, `DRAFT <index>` back.
4. The remaining rules, one at a time, each with a falsifying test where the harness
   can reach it (slots, schools, pools and the XP counter are testable from Python;
   elite scaling and the hunter are not and are verified in game).
5. The reward recipes in `gen_forged_spells.py`, with `test_forged.py` extended to
   refuse a reward in the roll pool.
6. Shards and the extra life at the NPC, the titles, the header hearts.

Each step ships on its own and is playable without the next.
