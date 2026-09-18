# Hazards — how this module can destroy a player's spells, and where to look

Developer notes. Nothing here is player-facing.

The module takes spells away on purpose: it strips the chassis class's free
starter kit so a Hero begins with nothing, and it removes skill lines so the
chassis's tabs disappear. Both operations are blunt instruments, and both have
destroyed things they were never aimed at.

---

## 1. Removing a skill line unlearns everything on it

`Player::SetSkill(line, 0, 0, 0)` unlearns **every spell on that line**, with no
class check and no regard for where the player got them. `SyncSpellbookTabs`
removes any `SKILL_CATEGORY_CLASS` line the Hero has earned nothing in
**through the library** — which is not the same question as "has nothing on".

A player can hold a spell on a class line without the library knowing:

| how they got it | example |
| --- | --- |
| bought from a vendor as an item | any mount, `Summon Pinto` 472 |
| learned from a tome or book | Polymorph: Turtle, Inferno, Ritual of Doom |
| given at character creation | see §2 |

None of those adds anything to `want`, so the line looked empty and was removed,
and the spell went with it. That is the 2026-09-18 bug: **every vendor-bought
mount vanished from `character_spell` on the next login.**

### What protects it now

Three guards, all in `ClasslessMgr.cpp`:

1. **A mount lends no class mask to its line.** `SkillLine 777` (Mounts) is a
   class line by category and holds the four paladin class mounts beside 311
   ordinary ones. The four carry `ClassMask 2`, the line inherited it, and every
   0-mask mount then read as a paladin ability — which is what pulled 777 into
   `_classSkillLines`. Stated as a rule about mounts rather than the number 777;
   measured against the client tables it moves exactly one line.
2. **Mounts is never removed**, alongside Runeforging. The paladin mount rows
   carry a `RaceMask`, so `IncludeRacials = 1` re-admits them, puts the line
   back and re-arms the trap — the mask fix alone is not enough.
3. **The general rule:** a line is kept when the Hero knows any spell on it that
   is neither a library rank nor in `_skillLearnedClassSpells`. Free-with-the-line
   spells are deliberately excluded — those are the chassis starter kit,
   `StripUnearnedSpells` owns them, and counting them would keep every chassis
   line alive and defeat the sweep entirely.

Guard 3 is the one that generalises. 1 and 2 stay because Mounts is granted to
every character at creation, so it is the one line where the sweep can fire on a
character that has never touched the module.

---

## 2. Where to look

The bug was hard to trace because the deciding facts are spread across four
different places, and three of them are not in the module.

| question | look here |
| --- | --- |
| Is this line in the class category? | `SkillLine.dbc`, `categoryId == 7` |
| Does a row on it carry a class mask? | `SkillLineAbility.dbc`, `ClassMask` (column 4) and `RaceMask` (3) |
| **Does the player already have this skill?** | **`playercreateinfo_skills`** — a row with racemask 0 and classmask 0 is *every character* |
| Is it handed out when a spell is learned? | `Player::addSpell` — only for `AcquireMethod 2`, plus Lockpicking and Runeforging |
| Can the library admit it? | `BuildLibrary`'s trainer filter, whose list is mostly **`trainer_spell` in the world DB**, not the DBCs |
| Can a player get it another way? | `item_template.spellid_N` with `spelltrigger_N = 6`, and quest rewards |

`playercreateinfo_skills` is the one that cost the most time. Nothing in
`addSpell` grants the Mounts skill — mounts are `AcquireMethod 0` — so the skill
appeared to come from nowhere until that table turned up.

Two `SKILL_CATEGORY_CLASS` lines are given to every character there:

- **777 Mounts** — the bug.
- **778 Companions** — safe *only* because not one of its 205 rows carries a
  class mask. If one ever does, every vanity pet a player owns is exposed the
  same way, and it needs the same treatment as Mounts.

---

## 3. The check

```
python data/sql/generators/validate_skill_lines.py
```

It watches the data the guards were sized against, because a realm can ship
different tables:

- the set of class-category lines granted at character creation is still
  exactly `{777, 778}`;
- Companions still has no row carrying a class mask;
- every masked row on Mounts is still a mount, so the "a mount lends no class
  mask" rule still zeroes that line;
- and it lists the item-taught spells on class lines that the library does not
  hold (currently 9 — four Polymorph tomes and two Dalaran books on Arcane,
  Inferno and Ritual of Doom on Demonology, Healing Stream Totem on
  Restoration). Those are covered by guard 3; the list is printed so a growing
  set is visible rather than silent.

Run it after any world-DB update and after touching anything about skill lines.

---

## 4. Parsing traps in this data

Three separate wrong answers in one investigation came from reading a table with
guessed column positions. Read the header, every time.

- **`SkillLineAbility.dbc`** — `RaceMask` is 3 and `ClassMask` is 4;
  `AcquireMethod` is 9, not 7. `DBCStructure.h` has the layout.
- **`player_class_stats.sql`** — the dump's column order is *not* the order of
  the `SELECT` in `ObjectMgr.cpp`: BaseHP and BaseMana come before the stats.
- **`item_template.sql`** — the dump has no column list at all. Read its
  `CREATE TABLE`: `spellid_1` is index 65, `spelltrigger_1` is 66.
- **A naive `\(([^()]*)\)` regex over a mysqldump silently drops rows**, because
  a quoted value can contain parentheses — `(0,0,183,0,'GENERIC (DND)')` was
  invisible to one. Split on top-level commas with a quote-aware parser.
