# Plan: custom archetypes

Players build their own archetypes, save and load them, follow them exactly like the starter
builds, and share them as a string anyone can paste in.

Status (2026-10-10): built, awaiting in-game testing. Decisions settled the same day: saved
builds live in the addon and move between computers by code; party sharing is in; a build
over budget is refused; builds are Classless-only.

Built: My Builds tab, Save my build, New, Import, the editor (reorder, remove, rank -/+, the
browsers' + buttons, budget, the server's verdict, per-row warnings and **Fix order**), Share
with copy and Send to party, receiving a party member's build, following a custom build, Build
on a saved build, Copy to My Builds on a starter build's build-order window, and the commands
`/cw builds` and `/cw import`.

Changed from the plan: no command prints a build's code, because a chat line cannot be copied in
this client; `/cw builds` opens My Builds, where Share shows the code ready to copy. Row
warnings arrive as `APW|0|kind:index:code:extra;...` with each preview, and ability steps carry
their unlock level as a fourth field, which Fix order sorts by.

---

## What exists today, and what it means for this

- An archetype is an **ordered list of ability lines** (first-rank spell ids) plus an **ordered
  list of talents with a target rank** (`Archetype` in `ClasslessWildcard.h`, rows in the world
  table `cw_archetypes`).
- **Following runs on the server.** `FollowArchetype` buys the next ability the moment it is
  unlocked and affordable, strictly in order, and talents in plan order, at every level-up and
  login. So the server must hold the plan a character follows. A build that lives only in the
  addon cannot be followed.
- `ApplyArchetype` already does the switch safely: unlearn and refund only what was **bought**
  (never talent or companion grants), reset talents, then follow. Custom builds reuse it.
- `PlanArchetype` (new this round) simulates a plan from level 1 to the cap on a character and
  returns the level each step is bought at. The editor's preview reuses it.
- Every purchase goes through `BuyAbility` / `BuyTalentRank`, which enforce path, essence,
  level, tier and prerequisite rules. **A custom build automates purchases; it can never grant
  anything a player could not buy by hand.** That is the whole security story, and it holds as
  long as following keeps going through those two functions.

---

## The player's side

### Where it lives

The Archetypes flyout gets two tabs along the top: **Starter** (today's list) and **My Builds**.

**My Builds** lists the saved builds in the same rows as Starter (name, description, counts,
**Build** and **Follow**), plus three small actions on each row: **Edit**, **Share**, **Delete**.
Above the list:

- **Save my build**: turns the character's current abilities and talents into a new build, in
  the order they were bought. The fastest way in, and the way most builds will start.
- **New**: an empty build in the editor.
- **Import**: paste a share string.

A Starter row also gets **Copy to My Builds**, so a starter build can be tweaked.

### The editor

A window the size of the build-order window, built from it:

- **Name** (32 characters) and **description** (one line, 120 characters) at the top.
- The ordered list, abilities then talents, each row showing the simulated **Lv N**, the icon,
  the name (rarity colour) and, for talents, `rank/max`. Hover shows the spell tooltip.
- Each row has **up / down** arrows and a **remove** cross. Order is what following obeys, so
  moving a row is moving when it is bought; the levels update as rows move.
- **Adding**: while the editor is open, every row in the panel's Abilities and Talents browsers
  gets a small **+** button that appends that ability, or one more rank of that talent.
- **Budget**, under the list: Ability Essence and Talent Essence the plan spends against what
  a Hero with no Rebirth bonus earns by the cap. **Over budget is refused**: Save stays off and
  the server's reason is shown. The yardstick ignores Rebirth so a build valid for one player
  is valid for anyone it is shared with.
- **Warnings**, shown inline on the row they concern:
  - a talent placed above its prerequisite (offer **Fix order**, which moves it below)
  - a talent ranked past its maximum
  - an ability or talent this realm does not have (an import from another realm)
  - an ability that is a form's kit or comes with a talent, so it is never bought on its own
- **Save**, **Save as**, **Share**, **Close**. Closing with unsaved changes asks first.

### Sharing

**Share** opens a small window with the string in a read-only edit box, already selected:
*"Press Ctrl+C to copy."* **Import** is the same window, editable: paste, and the build opens
in the editor as a preview with its levels, ready to **Save**.

Optional, phase 3: **Share with party** sends the string over the addon channel, and party
members with the addon get *"Arthas shared a build: Frostfire Duelist. View / Ignore"*.

---

## The share string

Requirements: survives copy and paste through chat, Discord and forums; detects a string that
was cut short or mistyped; stays short enough to paste comfortably; carries nothing but ids and
text, so it cannot be used to do anything a build cannot do.

**Format:** `CWA1:` followed by URL-safe base64 (`A-Z a-z 0-9 - _`, no padding) of a byte
stream:

| Field | Encoding |
|---|---|
| version | 1 byte (1) |
| name | 1 byte length, UTF-8 bytes (max 32) |
| description | 1 byte length, UTF-8 bytes (max 120) |
| ability count | varint |
| ability first-spell ids | varint each, **delta from the previous id, zigzag** |
| talent count | varint |
| talents | varint talent id, 1 byte target rank |
| checksum | 2 bytes, CRC-16 of everything before it |

Spell ids and talent ids are the client's own, which are the same on every 3.3.5 realm, and the
forged lines and Hero talents keep fixed ids (`ID_ORDER`, `TALENT_ID_BASE`). So a string from
one realm loads on another, minus anything that realm turned off, which the editor flags.

Size for a starter-sized build (about 26 abilities and 30 talents): roughly 190 bytes, **about
255 characters**. Too long for one chat line, fine for copy and paste. A readable form
(`name;1752.772...;12294x3...`) came out around 310 characters with no corruption check, so it
loses on both counts.

The addon encodes and decodes, in plain Lua 5.1 arithmetic (no `bit` library needed). The
server never sees the code: the addon uploads plain ids and the server validates every one of
them, which is where the safety comes from. A code's spare bits must be zero, so a build has
exactly one code.

---

## The server's side

### Storage

- **The library of saved builds lives in the addon's saved variables** (`ClasslessWildcardDB`,
  account-wide). No server storage, no limits to administer, and sharing covers moving builds
  between machines.
- **The build a character follows is stored on the server**, because following happens there:

  ```sql
  CREATE TABLE cw_char_custom_archetype (
      guid        INT UNSIGNED NOT NULL PRIMARY KEY,
      name        VARCHAR(32)  NOT NULL,
      abilities   TEXT         NOT NULL,   -- "id,id,..." as cw_archetypes
      talents     TEXT         NOT NULL    -- "id:rank,..." as cw_archetypes
  );
  ```

  `CharState::archetype` keeps meaning "the archetype followed"; a reserved value
  (`CUSTOM_ARCHETYPE = 0xFFFFFFFF`) means "this character's custom row". `FollowArchetype`,
  `ArchetypeQueue`, `PlanArchetype` and `ArchetypeCursor` take the `Archetype` from a small
  lookup that returns either the world row or the character's custom one, so none of their
  logic changes. Deleting a character deletes its row, alongside the other `cw_char_*` tables in
  `OnPlayerDeleteFromDB` (`ClasslessPlayerScript.cpp`).

### Protocol

An addon message carries about 255 characters and a share string can pass that, so a build is
uploaded in pieces:

| Message | Meaning |
|---|---|
| `ARCHUP CLEAR`, `ARCHUP A id,...`, `ARCHUP T id:rank,...` | the build's ids, in pieces, into the character's upload slot (200 entries at most) |
| `ARCHPLANX <name>` | preview the uploaded build: `APA/APT` with id 0, then `APE\|0\|spentA\|totalA\|spentT\|totalT\|problem` |
| `ARCHCUSTOM <name>` | validate the uploaded build and follow it: the same refund and reset as a starter archetype |
| `ARCHMINE` | the current build as a plan (`AMA`, `AMT`, `AME`), for *Save my build* |
| `S` field 32 | the followed custom build's name, so My Builds can mark it |

### Validation (server, on `ARCHPLANX` and `ARCHCUSTOM`)

Refuse with a clear error, never partially apply:

- the string's version, length and checksum
- name and description: printable characters only, no `|` (a client escape code), lengths
- every ability is in the library, enabled, and not a talent's or form's grant
- every talent exists, is enabled, rank 1 to its max, and no talent appears twice
- prerequisites come earlier in the talent order than what needs them
- at most 200 abilities and 200 talents (a sanity cap, far above any real build)

Over budget **is** refused, against a Hero with no Rebirth bonus, and so is an order that leaves
a step unbought by the cap (an early ability waiting on one that unlocks late).

---

## Phases

1. **Follow a custom build.** Server: table, the archetype lookup, `ARCHUP` / `ARCHCUSTOM`,
   decoder and validation. Addon: My Builds tab, **Save my build**, **Follow**, **Build** (the
   build-order window with `ARCHPLANX`), the share and import windows, and the encoder and
   decoder. This alone delivers save, load, follow and share.
2. **The editor.** Reorder, remove, the **+** buttons in both browsers, the budget bars,
   warnings and **Fix order**, **Copy to My Builds** on starter rows.
3. **Extras.** Share with party; a `/cw build` command that prints the followed build's string.

## Tests

- Lua: encode then decode is identity for every starter archetype; any single-character change
  or truncation is rejected by the checksum; a name with `|` cannot be saved; the editor's
  ordering, warnings and **Fix order** against harness data.
- C++: there is no server decoder (the addon uploads ids); validation is the server's part, and
  the MSVC syntax check covers it as usual.
- In game: save a build, share it to a second character, follow it, level a few times and watch
  it buy in order; switch back to a starter build and confirm the refund.

## Decisions (settled)

1. Saved builds live in the addon and move between computers by code. No server library.
2. Share with party: in.
3. Over-budget builds: refused.
4. Classless only.
