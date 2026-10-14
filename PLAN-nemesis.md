# Nemesis: a game mode

The Nemesis challenge reworked into a mode of its own, after Shadow of Mordor's nemesis
system: enemies that remember you, grow from beating you, carry strengths and weaknesses
you learn by fighting them, can be provoked on purpose, and pay out in trophies shaped by
who they were. Agreed with the user on 2026-10-14. Nothing here is built yet.

Every number marked *(config)* is a `ClasslessWildcard.Nemesis.*` option, with the value
here as its default.

---

## 1. The goal

- The run finishes at level 80 with **500 Vengeance** *(config)*.
- **Vengeance** is the total level of every nemesis slain, counted at the level it fought
  you at. A Sworn nemesis counts **1.5 times** *(config)*.
- Because a nemesis's level follows the Hero's (section 3), early kills are worth little:
  one slain at level 6 gives about 8, one slain at 78 gives 80. There is no way to farm the
  goal at low level.
- Unlimited lives. A death costs nothing beyond the death: **no experience is taken**.
- Replaces: heads, the experience bar being taken, experience returned on a kill, the
  1-to-5 level scale.

## 2. Getting a nemesis

| | Marked | Sworn |
|---|---|---|
| How | The creature that kills you | *Swear Vendetta* on a creature |
| Level | Your level **+2** *(config)* | Your level **+4** *(config)* |
| Starts with | One strength, one weakness | **Bloodlust**, one more strength, one weakness |
| Vengeance | Its level | Its level x1.5 |

**Marked** happens when a normal creature kills you. As now, no nemesis comes from a death
in a dungeon or raid, or to an elite, a boss, a pet, a totem or a summoned creature.

**Sworn** uses *Swear Vendetta*, an ability the Hero has only while on the run (a new spell
in the client patch):
- Instant, 30 yards, **30 minute cooldown** *(config)*.
- Targets a normal creature in the open world, no more than **5 levels** below the Hero
  *(config)*. Never an elite, boss, critter, civilian, pet, totem, summon, or anything in a
  dungeon or raid.
- **One Sworn nemesis alive at a time.**

**Dying to a nemesis again** gives it one more strength, up to **three**, and makes it
larger (x1.5 at first, +0.15 per death, up to x2). Its level offset never changes.

## 3. The private copy: how a nemesis exists for one Hero

A creature cannot have a different level for each player, and the core reads a creature's
real level for every combat roll (`Creature::getLevelForTarget`: spell miss and resist,
weapon skill against defense, dodge, parry, glancing blows, crit suppression, armor). A
level shown only on screen would leave a level 1 wolf "level 52" that almost never hits and
is never missed. So each Hero fights a real creature of the right level, made for them:

- When the Hero comes within sight of their nemesis, the server **summons a copy** of it
  for them: the same creature, its real level the Hero's plus the offset, built with the
  realm's `Rate.Creature.Elite.RAREELITE.*` health and damage (`CW_ReLevelCreature`, as
  Pursued's hunter). Every roll in the fight is then the core's own for that level.
- **The Hero sees only the copy.** For them the original is drawn invisible and cannot be
  targeted; for everyone else the copy is drawn invisible and cannot be targeted. Both
  through the per-viewer update patch (`OnPatchValuesUpdate`: display id, unit flags).
- **The copy fights only its Hero and their pet**, and nobody else can harm it (the
  damage exchange that already does this for the hunter and Legion's reinforcements).
- Killing the copy is killing the nemesis. The original lives on for everyone else.
- The copy despawns when the Hero leaves the area or logs out, and is summoned fresh when
  they return. The nemesis's offset, traits, deaths and what the Hero has learned are
  saved.
- Unavoidable without touching the core: another player standing in the fight may see the
  copy's spell effects appear from nowhere, and their area damage reaches it (at zero).

## 4. Traits

### Strengths

| Strength | Against you | Trophy it gives |
|---|---|---|
| Bloodlust | Attacks and casts 30% faster (real haste on the copy) | Haste |
| Ironhide | Takes 25% less physical damage | Armor |
| Spellward | Takes 25% less spell damage | All resistances |
| Venomous | Its hits poison you for 2% of your health every 2 sec, 6 sec | Critical strike chance |
| Unyielding | Below 30% health it is enraged: +25% damage | Maximum health |
| Warband | Calls two of its kind as the fight starts | Attack power and spell power |
| Relentless | Regenerates 5% health a second out of combat | All primary stats |

### Weaknesses (one each)

| Weakness | Effect |
|---|---|
| A school (fire, frost, shadow, nature, arcane or holy) | That school does 50% more to it |
| Brittle | A stun ends its enrage, and it takes 20% more damage for 8 sec |
| Cowardly | At 20% health it flees; caught, it takes 30% more damage |

- **Learned by fighting.** Its strengths show once you have fought it. Its weakness shows
  when you exploit it (hit it with that school, stun it, make it flee), with a centre-screen
  "Weakness found: frost."
- All trait numbers are *(config)*.

## 5. Making it personal

- **A title** on the Hero's target frame, from its strengths and how it was made:
  "Diseased Timber Wolf, Hero-Slayer". Others: the Unbroken, Bloodsworn, Ironhide,
  Twice-Victorious.
- **Lines only the Hero sees** (monster say sent to them alone): when it first comes into
  sight, after it has killed them again, and as it dies. Separate sets for Marked and
  Sworn. "I left you in the dirt once. I'll do it again." / "You swore on my name? Then
  come and take it."
- **The tracker becomes a list**: title, zone, offset, known traits, Marked or Sworn.
  Clicking one marks where it lives on the map.
- **Kept**: the red arrow and the minimap dot (theirs alone), the rare elite border, the
  slain banner (now with Vengeance gained and the trophy taken).

## 6. Rewards

### On the kill
- **Experience**: its kill experience at its real level, elite rate, plus a bonus of a
  quarter of a level (Marked) or half a level (Sworn) *(config)*.
- **Loot**: the rare drop chance and heirloom roll (built). A Sworn nemesis also
  guarantees one piece of classless gear.
- **A trophy** (below).

### Stars: the one number trophies and the charm share

Every trophy effect has a fixed value **per star** *(config)*, the same in a trophy and on
the charm:

| Effect | Per star | At 5 stars (the charm's cap) |
|---|---|---|
| Haste | 0.8% | 4% |
| Armor | 2% | 10% |
| All resistances | 6 | 30 |
| Critical strike chance | 0.4% | 2% |
| Maximum health | 1.2% | 6% |
| Attack power and spell power | 1.2% | 6% |
| All primary stats | 0.8% | 4% |

### Trophies: charms for the run

- **Every nemesis slain drops a trophy**, all run long, straight into the bags: one item per
  effect and star count ("Trophy of Ironhide II", entries 991000 to 991020).
- **Locked in the bags for the run.** A trophy can be moved between bag slots and
  destroyed, and nothing else:
  - trading, mail, the auction house and a guild bank: refused by the core for a
    soulbound item;
  - a vendor: it has no sell price, and the module's sell hook (`OnPlayerCanSellItem`)
    refuses it;
  - the Hero's own bank and bank bags: the core has no hook, so the module reads the
    client's item-move requests (`CanPacketReceive`: swap, split, auto-bank) and refuses
    any that would put a trophy there, with an error message;
  - and a trophy only ever counts from the bags, so one that got out some other way would
    simply stop working.
- **Its effect** comes from the nemesis's newest strength (Bloodlust gives haste, and so
  on: the table in section 4). Not the first: every Sworn nemesis starts with Bloodlust,
  so the first would make every Sworn trophy a haste one.
- **Its stars**: one per strength the nemesis had, plus one for a Sworn nemesis, up to
  **three**. A ★★ haste trophy gives 2 x 0.8% = 1.6% haste.
- **It works from the bags**, like a Diablo 2 charm: nothing is equipped. The server reads
  the bags and applies the effect as a stat change, the same way Rebirth's stat bonus is
  applied: never an aura, so nothing can be clicked off.
- **Four at most** *(config)*: with four in the bags, or the bags full, the next trophy
  waits (saved with the run) and comes the moment one is destroyed or room is made. The
  four carried are the four that count; there is no other choosing, and no setting one
  aside.
- **All four count, and they stack, kinds included**: four haste trophies give four
  trophies' worth of haste. An all-haste run is a real choice.
- Trophies work only while the Nemesis run is live.
- **A run that ends without finishing** (a Rebirth ending it) takes its trophies away.

### The Nemesis Charm: what finishing keeps

- **One per character**, kept for good: through Rebirth and every later run. It works from
  the bags like a trophy, and sits outside the four-trophy limit.
- **Locked in the bags like a trophy, and it cannot be destroyed either**: the module
  refuses the client's destroy request for it (`CanPacketReceive`, CMSG_DESTROYITEM) as it
  refuses a move to the bank. Its ranks are saved per character, not on the item, so if the
  item is ever missing at login it is made again with the same ranks.
- **Each effect on it has a rank, 0 to 5.** Rank x the effect's per-star value is what it
  gives. Rank 5 is the cap.
- **Finishing the challenge adds stars to the charm: for each kind of effect, only the
  strongest trophy of that kind adds its stars** to that effect's rank, stopping at 5.
  Duplicates carried the run but add nothing to the charm. All the trophies are used up.
  The first finish makes the charm.
  - Example: finishing with ★★★, ★★, ★★ and ★ haste trophies. During the run they gave
    2.4 + 1.6 + 1.6 + 0.8 = 6.4% haste. On finishing only the ★★★ counts: Haste rank +3.
- **The charm and the run's trophies stack.** On a later run, a charm with Haste rank 2
  (1.6%) and a ★★★ haste trophy (2.4%) give 4%.
- **Tooltips say it all**:
  - trophy: "★★ Haste: +1.6% haste. On finishing: Haste rank 2 -> 4 of 5."
  - charm: "Haste ★★★★★ 4%  Armor ★★☆☆☆ 4%  Crit ☆☆☆☆☆ 0%"
- With at most four kinds merged per finish and seven effects of five ranks each, a
  full charm takes many finishes across Rebirths. Its ceiling is the table's last column:
  4% haste, 10% armor, 30 resistances, 2% crit, 6% health, 6% attack and spell power, 4%
  primary stats.
- Finishing still pays the challenge's gold (first finish), title and reward ability.

## 7. What changes in what is built now

- Kept: one creature by spawn id, for one Hero; the arrow and minimap dot sent to them
  alone; the rare elite border; the slain banner; rare drop chances; no nemesis from
  dungeons, raids, elites or bosses.
- Removed: taking the experience bar, experience returned, the 1-to-5 level scale, heads,
  and showing the original creature at a different level, health and size (the private
  copy replaces it).
- Existing runs: heads already taken become Vengeance at the level they were taken.
- Elite World is unchanged. It never changes a creature's level, only its rank, so the
  per-player stats it has now are correct.

## 8. What it takes

Server:
- Nemesis rows gain how it was made (Marked, Sworn), the offset, traits, the weakness,
  what the Hero has learned, and deaths. A table for trophies held and one for the charm.
  Vengeance kept with the run.
- The private copy: summon and despawn around the Hero, the per-viewer hiding of the
  original and the copy, the copy fighting its Hero alone.
- Traits in combat, weakness discovery, the private chat lines.
- *Swear Vendetta*: the spell, its checks and cooldown, granted and taken with the run.
- Trophy and charm items: their item rows (one per effect and star count, the charm one
  item whose ranks are saved per character), the four-trophy limit category, reading the
  bags and applying the stats, the merge on finishing.

Addon:
- The tracker list with map markers, titles on the target frame, the trait and weakness
  tooltip, the star tooltips on trophies and the charm, Vengeance on the banner and the
  tracker.

Client patch:
- *Swear Vendetta*'s spell row: name, icon, text.

Text:
- The challenge's rule, description and tips, the README, and the copy validator, all
  rewritten for the mode.

## 9. Order of work

1. The private copy and the level rule (section 3), with the bar and the 1-to-5 scale
   removed.
2. Sworn and *Swear Vendetta*.
3. Traits and weakness discovery.
4. Vengeance, trophies, the Nemesis Charm.
5. Titles, lines, the tracker list, the text.
