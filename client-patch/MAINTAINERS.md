# Client patch internals

Player-facing instructions are in [`README.md`](README.md). This file is the
how-and-why, for maintaining the thing.

## Why it is built this way

The patch is **generated on the player's machine from their own client**, never
shipped prebuilt. Two reasons:

1. No Blizzard data lives in this repository.
2. The edits are applied on top of whatever the client already has. A player
   running a community patch pack that already replaced `ChrClasses.dbc` or
   `GlueStrings.lua` gets our changes layered onto *their* version instead of
   silently reverting to the vanilla one.

That second point is why `lib/clientfs.py` exists. It reconstructs the client's
own archive priority order and reads the copy of a file that actually wins:

```
Data/<locale>/patch-<locale>-{Z..A,9..2}.MPQ     highest
Data/<locale>/patch-<locale>.MPQ
Data/<locale>/{lichking,expansion}-{locale,speech}-<locale>.MPQ
Data/<locale>/{speech,locale,base}-<locale>.MPQ
Data/patch-{Z..A,9..2}.MPQ
Data/patch.MPQ
Data/{lichking,expansion,common-2,common}.MPQ    lowest
```

The installer then writes its own archives at the **highest free letter**
(searching Z downwards), so it lands above everything already installed without
colliding with it. The chosen letter is recorded in
`ClasslessWildcard-install.json` in the WoW folder, so a re-run replaces its own
archives instead of accumulating new ones, and `--uninstall` knows what to remove.

## No StormLib

`lib/mpq.py` is a self-contained MPQ implementation, which is what removes the
"build a C tool first" step that made the old process unusable.

- **Reading** handles what WotLK archives actually contain: v1–v4 headers,
  archives past 4 GiB via the hi-block table, encrypted files, single-unit files,
  sector CRCs, and zlib / bzip2 / PKWARE-DCL / stored sectors.
- **Writing** emits exactly what StormLib emits — v1 header, unencrypted,
  zlib-compressed sectors with an offset table — so any MPQ reader can open the
  result. Verified against `mpyq`, an unrelated implementation, which recovers
  every file byte-for-byte.

`lib/pkware.py` is only reached if some archive in the stack uses PKWARE
compression. Blizzard's WotLK archives use zlib, so on a stock client this code
never runs.

## What the patch actually changes

### `ChrClasses.dbc` — the class name

3.3.5a build 12340 layout, 60 `uint32` fields per record:

| Field   | Meaning                                                    |
| ------- | ---------------------------------------------------------- |
| 0       | class ID                                                   |
| 3       | pet name token                                             |
| 4–19    | `Name_lang`, one column per locale                         |
| 20      | `Name_lang` mask                                           |
| 21–36   | `NameFemale_lang`  (37 = mask)                             |
| 38–53   | `NameMale_lang`    (54 = mask)                             |
| 55      | filename token — `WARRIOR`, `DEATHKNIGHT`, …               |

All three name blocks are pointed at one new string. **Field 55 is deliberately
left alone**: class colours, class icons and every addon that keys off the class
token depend on it. The original string block is preserved intact and the new
name appended, because the token offsets point into it.

The client renders whichever `Name_lang` column matches its locale, so every
column is set rather than just column 0.

### `CharBaseInfo.dbc` — creation screen combinations

Two bytes per record, `(race, class)`. Rebuilt as one row per playable race
`(1–8, 10, 11)` — 10 rows, down from the stock 62 — all pointing at a single
**cosmetic shell class**.

The shell is **Paladin** (`SHELL_CLASS` in `install.py`), which is also the
server chassis — so a Hero is created as a Paladin directly, with native mana
and no runtime class change. Paladin is only vanilla-creatable by four races, so
the module's auto-applied `cw_world_hero_races.sql` adds the missing
`playercreateinfo` rows for the other six (Orc/Night Elf/Undead/Tauren/Gnome/
Troll); stats derive from `player_race_stats` x `player_class_stats`, so only the
start position and action bar need adding.

### `CharSections.dbc` — the Death Knight looks

10 `uint32` per record: `ID, Race, Sex, BaseSection, Texture×3, Flags,
VariationIndex, ColorIndex`. Blizzard reserved 2829 rows for Death Knights:
three extra skin colours per race and sex (not Undead), each with its own face
and underwear textures; a second set of faces for every stock skin colour; and
three extra hair and facial hair colours. A Hero is created as a Paladin, so
the creation screen hid all of them.

Who sees a row is decided in Wow.exe 12340 by one gate, `0x4f39a0`, with the
rule picked by `0x4f3a40` from the screen and `class == 6`:

```
creation,   other class    0x1 set, none of 0x4 / 0x8
creation,   Death Knight   0x1 set, 0x4 or 0x10 set, no 0x8
barbershop, other class    0x1 or 0x2 set, none of 0x4 / 0x8
barbershop, Death Knight   0x1 or 0x2 set, 0x4 or 0x10 set, no 0x8
```

The patch swaps `0x4` for `0x10` on those rows (`0x5`→`0x11`, `0x6`→`0x12`,
the same flags the stock rows carry). Clearing `0x4` alone would hide the rows
from real Death Knights, who need `0x4` or `0x10`. The server never reads this
table, so nothing changes there.

**The Death Knight skins pair with three faces.** Blizzard drew each Death
Knight skin colour for only three faces per race and sex (Human male: faces 0,
2, 11) and the client holds no other art. The skin arrows (`0x4eb150` next,
`0x4eb290` prev) offer colour `c` only when the skin row, the *current face's*
row and the underwear row at `c` all pass the gate, so from any other face the
new colours were skipped: 520 of 628 face/arrow runs never reached one.

Those three were also painted with the Death Knight's glowing blue eyes (the
eye glow is in the texture, on top of the geoset glow below), so even where
art exists it is a glowing face. Every face therefore gets a row at each Death
Knight colour, and the skin arrows reach those colours from any face and
**never change which face is picked**:

- **Normal faces are painted** (`lib/dkfaces.py`, `add_generated_faces`):
  each normal face's own textures, recoloured into the Death Knight tone at
  install time from the player's client. **Nothing derived from Blizzard art
  is in the repository**, only the code. The tone map is a quadratic RGB fit
  between the normal body skin and the Death Knight one (the same artwork in
  two tones; within a few levels of 255), baked with the "is it skin" rule
  into one Pillow `Color3DLUT`. Not skin, so kept: near-white (eye whites),
  or a colour the body never uses that is also over 45 degrees from its hue
  and saturated above 0.25 (irises, jewellery). Skin in a colour the body
  never uses goes through the body's own colour at the same brightness
  first, because the fit would guess. 471 face/colour pairs, 942 textures,
  about 32 MB, 30 to 40 seconds, written as palettized BLP2 (Blizzard's face
  format) named `cw_<original>_dk<colour>.blp` beside the originals, in the
  base archive only. Rows: 309 new, ids from `CHARSECTIONS_GENERATED_FIRST_ID`
  (20000), and Blizzard's 162 drawn ones repointed, all flags `0x01` (no glow;
  a Death Knight never sees normal faces, as in stock).
- **Glowing faces borrow** (`fill_death_knight_skin_faces(normal_faces=False)`):
  a copy of the nearest drawn (glowing) face, ids from
  `CHARSECTIONS_FILL_FIRST_ID` (30000). 471 rows.
- **Wow.exe:** the Face arrows must not see the borrowed copies (see "Death
  Knight skins from any face" under `Wow.exe`), or a Death Knight skin shows
  the same three looks over and over. Painted rows are real, distinct art and
  stay visible, so on a Death Knight skin the Face arrow steps through every
  normal face without leaving it.

If painting fails (no Pillow, a missing texture), the installer says so and
every face borrows instead, as in `00e773c`.

**Appended rows must be one sorted block.** The client indexes CharSections
in file order (`0x4f3e00`): a run of rows sharing race, sex and section sizes
that race's variation list from the run's highest variation, a run sharing
the variation sizes its colour list, and in both cases the **last** run wins.
Rows beyond the sizes are silently dropped. The first painted build appended
the borrowed copies (faces 12-23) and then the painted rows (faces 0-10) as
two blocks, so the last run capped Human males at 11 faces: face 11 and every
glowing face vanished in game, and the skin arrows on those faces stuck.
`add_generated_faces` now writes everything with an id from 20000 as one
block sorted by race, sex, section, variation and colour, and
`dbc.client_index_misses()` replays the three passes; selftest requires it to
return nothing for the stock table, the shipped table, the fallback and the
installer's own payload. That broken table lost 2105 rows to it.

The rule for "is it skin" took four tries, each found on the preview sheet:
"unchanged across normal skins" (the iris swatch is tinted with the skin),
"in the body's colour range" (a Tauren's grey body rejected real skin), "vivid
and off-hue" alone (a Blood Elf's skin is so saturated that its fel-green eyes
counted as skin and turned cyan), then all three together. Blizzard's own
Tauren Death Knight faces keep the brown band along the lip, so ours does too.

Earlier attempts that failed in game on 2026-10-09: borrowed copies for every
face (a normal face became a glowing one on a Death Knight skin); before the
exe filter, the Face arrow (`0x4eb710`) never left a Death Knight skin; and a
skin-arrow routine that switched to a drawn face, one-way, so a player who
picked a glowing face lost it after one pass through the skins.
`test_skin_arrows.py` runs the real arrows to prove the current design.

The blue Death Knight eye glow (geoset 1703) is drawn by Wow.exe `0x4ed900`
for class 6, or when the character's **face** row (section 1, the face at that
skin colour) has `0x4`. The swap alone would leave a Hero with ordinary eyes,
so the exe patch widens that test to `0x14` (see the `Wow.exe` section). No
stock face row carries `0x10`, so the same 1791 faces glow as before, now for
every class. The selftest checks both halves.

### `Spell.dbc` — the class tool requirement

234 `uint32` per record. Four columns are cleared, and only for spells that
appear on a category-7 (class) `SkillLineAbility` row:

```
50, 51     Totem[2]                  a named item the caster must hold
222, 223   RequiredTotemCategoryID   a tool category: Earth Totem, Runeforge
```

A Hero draws spells from every class and is handed no class's tools, so
Stoneskin Totem arrives with a red `Tools: Earth Totem` line and will not cast.
The server clears the same two fields on its own `SpellInfo`, always and not
optionally; the client copy is what removes the tooltip line and stops the
client refusing the cast before it is ever sent, so both halves are needed and
neither is a setting — a server that kept the requirement would disagree with
every client on the realm. Profession recipes keep their hammer and their skinning
knife — around 2190 rows still require a tool after the pass. Reagents are a
different mechanism and are untouched.

`lib/dbc.py: clear_spell_tools()` does the work and `class_spell_ids()` builds
the set it is scoped to. `build_data_patch` runs it, then `elemental.apply`
appends the variant rows to the *patched* table rather than re-reading the
archive copy.

### `GlueStrings.lua` — the creation screen copy

The keys the 3.3.5a creation screen reads, per class token:

```
CLASS_<TOKEN>            long paragraph, |n for line breaks
CLASS_<TOKEN>_FEMALE     same paragraph, female phrasing
CLASS_INFO_<TOKEN><N>    bullet list, N = 0..5 (most classes have 5, some 6)
```

`lib/gluestrings.py` rewrites those 76 keys for all ten tokens and passes the
other ~860 strings through untouched. Edit `PARAGRAPH` and `BULLETS` there to
change the pitch.

> The old version of this script targeted keys named `WARRIOR_INFO_TEXT` and
> `WARRIOR_ROLE_TANK`. Those do not exist in any 3.3.5a client, so it silently
> rewrote nothing. If you change the key set, verify against a real client.

The remaining three edits below are the `--creation-text` / `--hero-icon`
visual extras. Text and hide-class ride in the locale patch and need the exe
patch; the outfit and icon are plain data and do not.

### `SpellShapeshiftForm.dbc` — stances can be clicked off

A stance pages the main action bar out to its bonus bar, and Battle, Defensive
and Berserker Stance (forms 17 to 19) carry flag `0x2`, which makes the client
refuse to cancel them: `Spell_C_CancelAura` (`0x802F80`) returns before sending
`CMSG_CANCEL_AURA` for a form with it. A Warrior is never out of a stance, so
that costs a Warrior nothing; a Hero with one stance could never get their bar
back. `dbc.open_stance_cancel` clears `0x2` on every form flagged a stance
(`0x1`), which is exactly those three. Nothing else in the client reads `0x2`
and the server never does; its cancel handler already accepts the stance
spells (positive, not passive, no `SPELL_ATTR0_NO_AURA_CANCEL`).

### `CharacterCreate.lua` — hide the single-class selector (`--creation-text`)

The server offers one class per race, so the creation screen shows a lone class
button. `lib/charcreate.py` appends a hook to the client's own
`CharacterCreate.lua` that wraps `CharacterCreateEnumerateClasses` and hides
every `CharacterCreateClassButton` after the original runs. Append-only: the
original file is passed through untouched. Class selection is separate state
(`SetCharacterClass`, driven by `GetSelectedClass`), so hiding the buttons does
not affect Accept. The override ships in the locale patch, which outranks the
client pack's copy.

### `CharStartOutfit.dbc` — the Hero starter gear (`--creation-text`)

74 `uint32` per record: ID, packed `(race,class,gender,outfit)`, then
`ItemID[24]`, `DisplayInfoID[24]`, `InventoryType[24]`. The model is drawn from
the **DisplayInfoID** array, not the item IDs.

`lib/outfit.py` rewrites every Hero's shell-class (Paladin) row to wear exactly
the neutral starter kit the module equips at first login -- Recruit's shirt,
pants and boots (`STARTER_ITEMS` = 38, 39, 40, the module's default
StarterKit.Equip) -- with no weapon, because the module drops the starter
weapons in the bag rather than equipping them. So the creation preview matches
what a new Hero actually wears. Display ids and slots are resolved from the
client's own CharStartOutfit rows, so nothing is invented; a shell-class row is
added for every race+gender that lacks one (six races cannot be Paladins in
vanilla), so no Hero previews naked. If a realm changes StarterKit.Equip, update
STARTER_ITEMS to match.

### The class-icon atlases — the Hero emblem (`--hero-icon`)

A class icon is a cell of a 4×4 grid in a 256×256 atlas (`CLASS_ICON_TCOORDS`
maps each token to a cell). `lib/blp.py` **decodes** the client's own atlas
(`decode_blp`: palettized, DXT1/3/5 or uncompressed), pastes the gold emblem
into the **Paladin** cell (`_HERO_CELLS_TC`) -- Paladin is the Hero's class
(shell and chassis), so that is the cell the interface draws a Hero with -- and
re-encodes. Every other class icon comes back exactly as it was.

Three atlases share that layout, and all three get the emblem:

| Atlas | Where the game draws it |
|---|---|
| `Interface\TargetingFrame\UI-Classes-Circles` | unit frames, arena frames |
| `Interface\Glues\CharacterCreate\UI-CharacterCreate-Classes` | the raid window's class buttons, calendar invites |
| `Interface\WorldStateFrame\Icons-Classes` | the battleground scoreboard |

The addon's by-class ability tabs keep every class icon: `install_addon` gives
the addon its own copy of the **stock** `UI-CharacterCreate-Classes`
(`classicons.blp`, read with our own archives excluded), and the addon falls
back to the game's file only if that copy is missing.

> Earlier tries got this wrong twice: filling *every* cell erased the icons the
> addon needs, and rewriting `UI-CharacterCreate-Classes` broke the addon's
> class tabs, back when the addon read the game's file. It reads its own copy
> now, so the game's file can carry the emblem.

To read the pristine original on a reinstall (not the installer's own previous
output), `install.py` builds its `ClientFiles` with `exclude=` set to the patch
archives it is about to write.

The atlases are written **uncompressed** (`encode_argb8888`: BLP2 header
`03 08 08 01`, encoding 3, BGRA pixels, a full mip chain). A 256-colour palette
over ten unrelated icons shifted the other nine cells' colours (the Rogue's
yellows went brown); encoding 3 is lossless. The client copies encoding 3
straight through as ARGB8888 (`CBLPFile::Lock`, `0x6AF990`; `TextureLoadBlpMips`
asks for ARGB8888 for anything not DXT). Only character skins insist on a
palettized file (`TextureCacheGetPal`), and these are not skins.

The BLP **format matters** — a wrong header makes the client draw a green
"missing texture" box everywhere the icon is used. For the palettized textures
the installer writes elsewhere (`encode_palettized`, the element icons), the
header is matched byte-for-byte against the genuine enc=1 textures the client
ships: `01 08 08 01` (encoding 1 palettized, alphaDepth 8, **alphaType 8**,
**hasMips 1**) with a **full mip chain** (256→1, `w*h` index bytes + `w*h`
alpha bytes per level). alphaType 0 or a missing mip chain both fail to load.
Pillow is required: `install.py` installs it with pip when missing and aborts if
it cannot, because a client without the painted icons is not the full install.

The full Hero client -- name, single-class list, text, outfit, icon, exe patch,
addon -- installs by **default**; the `--no-*` flags turn single pieces off
for testing. The icon needs no exe patch (textures are not signature-checked) and can be
skipped with `--no-hero-icon`. Swap `_draw_emblem` in `lib/blp.py` to change the
mark.

### `Wow.exe` — the "allow custom interface" patch

Replacing `GlueStrings.lua` makes the client reject the whole interface set with
*"Your login interface files are corrupt"* unless the interface signature check
is disabled. `--creation-text` applies the well-known signature-scope bypass to
`Wow.exe` so the custom text loads. The default install never touches the exe.

> An earlier version shipped a single-byte flip at `0x243F` and claimed it did
> this. It was wrong: `0x243F` is next to the *MPQ data* signature strings
> (`0x9E0387`, *"game's signature version"*), not the GlueXML check, whose
> strings live at `0x9F2AC4` (*"GlueXML is modified or corrupt"*). It patched an
> unrelated branch, so the client still rejected custom glue. Never re-add a
> byte-flip without confirming which check it hits.

The correct patch is six same-length in-place edits inside the signature-scope
validation function, taken from the Project Reforged 3.3.5 patcher
(`patch-004-allow_interface_edit.bat`,
<https://github.com/Stormhand-dev/WoW-3.3.5-Patcher---Project-Reforged>). On a
stock 12340 exe they sit at these file offsets:

| offset     | from → to                       | effect                          |
| ---------- | ------------------------------- | ------------------------------- |
| `0x1F41BC` | `74 39` → `EB 39`               | `jz` → `jmp` (take accept path) |
| `0x415A25` | `75 05` → `EB 05`               | `jnz` → `jmp`                   |
| `0x415A3B` | `B8 01…` → `B8 03…`             | `mov eax,1` → `mov eax,3`       |
| `0x415A93` | `B8 01…` → `B8 03…`             | `mov eax,1` → `mov eax,3`       |
| `0x415B46` | `7F 12` → `EB 12`               | `jg` → `jmp`                    |
| `0x415B5D` | `83 C0 03 … 5D C3 CC` → `B8 03…`| force return scope 3            |

Scope `3` is the value the check treats as valid, so making the function always
return it accepts modified UI files.

`lib/exepatch.py` does not hard-code offsets — it carries the byte *patterns*
and, before writing, requires each to match the target exe **exactly once**
(same length in, same length out), so a client the set does not fit is refused
rather than corrupted. It writes `Wow.exe.classless-bak` first, is idempotent
(re-running detects the patched form), and `restore()` reverts from the backup
or, failing that, by reversing the unique patched patterns in place. A seventh
Reforged pattern (`00 A1 26` → `00 16 4E`) is absent from stock 12340 and is
applied only if present.

Verified on a real 12340 exe: 6 sites, 12 bytes changed, `apply → inspect →
restore` round-trips byte-identical, **and confirmed at the login/character
screen** — with the patch applied, the custom `GlueStrings.lua` loads and the
creation screen shows the Hero description instead of the corrupt-interface
error.

#### The Death Knight eye glow

One more site, not part of the interface bypass: `0x4ed93b` (file offset
`0xECD3B`), `test byte ptr [eax+0x1c], 4` → `..., 0x14`, one byte. See the
CharSections section for why. It is non-core, so an exe it does not fit still
gets the interface bypass. An exe an older install already patched picks up
this site on the next install (`inspect` reports `unpatched` while any site is
waiting, and `apply` no longer stops once the interface sites are done). A
stock exe now changes 13 bytes; the existing backup is never overwritten, so
`--uninstall` still restores the original.

#### Runes come back on any power bar

One more non-core site: `0x728aa4` (file offset `0x327EA4`), the `jne` after
`cmp ebx, 6`, becomes two NOPs. The client keeps its own rune ready mask at
`0xc24388` (all bits set at login), and only two places write it: the rune list
in `SMSG_SPELL_GO` for a spell whose PowerType is runes (`0x8068f6`,
`0x80e712`, both into `0x5ee240`), and the per-frame check in `0x728a20`, which
sets a spent rune's bit once its ready time passes. That check runs only when
the active player's DISPLAYED power is runic power (6). A Death Knight always
passes; a Hero, on mana, rage or energy, never does, so a Hero's runes came
back only when the next rune spell's SPELL_GO carried the server's mask. Spend
all six and the client refuses every rune spell (its cost check counts bits in
that mask), no SPELL_GO comes, and the runes stay spent until a relog.

`SMSG_ADD_RUNE_POWER` (`0x5ee520`) does not set the mask; it sets the rune's
ready time to now and leaves the rest to that per-frame check, which is why the
server's per-rune notice did nothing on its own. `SMSG_RESYNC_RUNES`
(`0x5ee440`) does not set it either. With the gate lifted, both work as they do
for a Death Knight.

#### The shaman totem bar without totems

The totem bar (Call of the Elements, the Ancestors, the Spirits) never showed
for a Hero, for two reasons, both behind one function. `0x542030`, the client's
"spell learned" routine, files a spell with AttributesEx7 `0x20` (a player
totem) under each element its tool category (Spell.dbc 222-223, field 158 of
the in-memory record) maps to, in the per-element lists at `0xbe8ea0` that
`GetMultiCastTotemSpells` (`0x5a8330`) reads. `clear_spell_tools` cleared those
categories so the totems would cast without the Earth/Fire/Water/Air Totem
items, which left every list empty. And `GetTotemInfo` (`0x51d330`), with no
totem down, reports an element only when its totem item is in the bags; the
bar counts an element only when both hold.

Every one of those checks, the cast check (`0x8091e8`, its category test at
`0x80923a`), `GetTotemInfo`, the learn path's update event and the tooltip's
"Tools:" line, calls `0x7548f0`: "does an item in the bags fit this
category". Its tail (`0x7548f3` to `0x75493f`, file `0x353CF3`, 77 bytes, the
last six int3 padding) is rewritten in place, `TOTEM_TOOL`: a category whose
TotemCategory.dbc type is 2 (2 Earth, 3 Air, 4 Fire, 5 Water, 21 Master
Totem: the shaman totems and nothing else) reads as carried, every other tool
asks the bags as before. The two bounds checks are retargeted to the moved
failure block; nothing else in the exe jumps into the range. With it,
`clear_spell_tools(keep_totem_categories=True)` leaves the elemental category
on totem spells, only when the installer patches the exe.

One thing stays Lua: `UIParent_ManageFramePositions` hides the totem bar
whenever the stance bar shows, since no shaman has both. The addon's
`CW.LayoutClassBars` puts it on the row instead, after the stance bar or the
pet bar (or a row up when the main bar is full), and moves nothing of
Blizzard's.

#### Class checks a Hero trips over

Every Hero is a Paladin to the client, so a branch kept for another class never
runs. The decompiled client (`B:\\code\\wowdecomp`, every function tagged with
its address) lists ~90 reads of the class byte (`m_unitFieldBytes0[1]`); most
are per-class tables the Paladin chassis is meant to use, or lookups the
SkillLineAbility patch already opened. `CLASS_GATES` opens the ones that take a
feature away from a Hero who has it:

- `Script_GetComboPoints` (`0x611670`): Rogue or Druid only; the `je` past the
  class test becomes a `jmp`.
- `CGUnit_C::DoPowerRegen` (`0x728A20`): predicts mana and energy off the
  displayed bar only for a Druid; the `jne` goes, so every class predicts them.
- `CGUnit_C::CanGainXP` (`0x71B630`) and `GetPetPersonality` (`0x71F390`): a
  hunter pet only when the owner is a Hunter. Both now test the pet's own power
  type, focus (2), which a hunter pet has and a demon does not.
- `CGMinimapFrame::s_trackingTypes`: the Stable Master (Hunter), Ammunition
  (Warrior, Hunter, Rogue) and Poisons (Rogue) masks are cleared.
- Feral weapons: the tooltip line "increases attack power by N in Cat, Bear
  and Moonkin form" (`AddItemSpellStatLines`, inlined at `0x62BB5E`) and the
  item comparison sums (`0x61F493`, `0x61F7AA`) test for a Druid (11); they ask
  for the Paladin chassis (2) now. The server adds that attack power in a feral
  form (`CW_FeralWeaponAP`, ClasslessPlayerScript.cpp).

- `Spell_C_HasNoReagentCost` (`0x800D60`): a "no reagent" aura counts only for
  a spell of the character's own class family (`ChrClasses.spellClassSet`, the
  Paladin's), so Decimation and the reagent glyphs still asked for the reagent
  and the cast was refused before it was sent. The `jne` after
  `cmp ecx, [0xD397B4]` goes; the server's `CanNoReagentCast` tests the mask
  alone, so the two agree.
- `CGItem_C::CanGoInSlot` (`0x7082B0`): slot 17 took a relic only when the
  `bypass` argument (ChrClasses flag `0x08`, cleared by `dbc.clear_relic_slot`)
  matched. The `je` becomes a `jmp` to the slot-table test, so a relic can be
  dragged there and shows in the flyout; the server's EQUIP_RELIC answer decides.
- `UnitPowerUpdateHandler` (`0x7234D0`): for the player and the pet the client
  drops a server power value at or below its own prediction. Only the pool on
  the bar (and mana and energy, via `DoPowerRegen`) is ever predicted down, so
  a Hero's rage or runic power off the bar stayed at its peak after the server
  decayed it, and `IsUsableSpell` agreed with the stale number. The guard now
  covers health and the bar's own pool only. The rewrite sits in a dead branch:
  the `predictedPower` cvar is tested at `0x723501` and again at `0x72354A`, so
  the second test's fallback never runs.

The ranged slot's relic rule (ChrClasses flag `0x08`) was already handled by
`dbc.clear_relic_slot`.

#### The Hero class color

Every Hero wore the Paladin's pink: in chat, the raid and party frames, the who
and guild lists (`RAID_CLASS_COLORS` in `Constants.lua`) and on enemy players'
nameplates (`s_classColors`, `0xB2DA20` in `.data`, read only by
`CGNamePlateFrame::UpdateColorDisplay`, `0x98EE30`). The Paladin entry of both
becomes the Hero color, jade `1AE6B3` (`framexml.HERO_RGB`, one constant for
both). No stock class uses that hue, and neither path color in the addon
(Classless `00ccff`, Wildcard `ff8800`) is near it. The exe table stores a
`CImVector` as blue, green, red, alpha; `HERO_COLOR` is the one 4-byte entry.

The interface half is one of the install-time edits in `lib/framexml.py`, made
to the client's own files so the code stays Blizzard's (an addon doing the same
from outside would taint it). Each matches exact stock text and is skipped when
the text is not there:

- `TotemFrame.lua`: the totem timers stay up with a pet out.
- `InterfaceOptionsPanels.lua`/`.xml`: the combo point combat text option is
  open to a Hero.
- `Constants.lua`: the Hero class color above.
- `Blizzard_RaidUI.lua`: the raid window's Pets group lists a Hero's pet (it
  listed Hunters' and Warlocks' only).
- `PaperDollFrame.lua`: `ComputePetBonus` knew only the Warlock and the Hunter,
  so a Hero's pet lines on the character sheet read 0 and were left out. A
  Hero's pet takes the bonus of its own kind: a hunter pet (`HasPetUI`'s second
  return) the Hunter's, a demon (a named creature family and a mana bar) the
  Warlock's. A ghoul runs on energy and a water elemental has no family, so
  neither gets a line, as for a Death Knight or a Mage.

#### Stances and forms past ten

No exe change. The client's form list (`0xbe8e28` count, `0xbe8e2c` entries of
8 bytes, filled in `0x542030` for a spell with aura 36 or the stance flag, then
sorted) grows without a limit, and `GetNumShapeshiftForms` (`0x53c0b0`),
`GetShapeshiftFormInfo` (`0x53de90`) and `CastShapeshiftForm` (`0x53c0f0`) all
take any index below the count. Only FrameXML stops at ten (`ShapeshiftButton1`
to `10`), and two of its loops index `ShapeshiftButton<n>` up to the count
(`UIParent_ManageFramePositions`, `PetActionBar_UpdatePositionValues`), which
threw on an eleventh form. The addon makes `ShapeshiftButton11` to `30` at
load (`CW.MakeFormButtons`): secure `type = spell` buttons in the bar's own row
and art, filled out of combat (`CW.BuildFormButtons`), at the stock stride
(8 apart, as `BonusActionBarFrame.xml` spaces 1 to 10).

Those two loops read the addon's buttons by global name from Blizzard's secure
layout pass (`FramePositionDelegate`), and a global an addon created taints
everything after the read: the pet bar's `SetPoint`, the totem bar's slide and
`PETACTIONBAR_XPOS`. The layout pass also hid the totem bar whenever a stance
bar showed, which the addon used to undo by writing
`MultiCastActionBarFrame.mode`, tainting the totem bar's own slide code. Both
are now install-time edits in `lib/framexml.py`:

- `UIParent.lua` (`open_bar_row`): the two stance loops stop at
  `NUM_SHAPESHIFT_SLOTS`; the "too many bars" hide becomes a placement, after
  the stance row and the pet bar, or one row up when the row is full (the
  possess bar still hides it); and `ShapeshiftBar_RowRight()` is appended,
  which finds the row's right edge from `ShapeshiftButton1`, `ShapeshiftButton2`
  and `GetNumShapeshiftForms()` alone.
- `PetActionBarFrame.lua` (`open_pet_bar_row`): the pet bar starts after
  `ShapeshiftBar_RowRight()`, falling back to the stock read if the
  `UIParent.lua` edit is missing.

The addon sizes its own buttons' borders (`CW.SizeFormButtons`) and leaves the
totem bar alone whenever `ShapeshiftBar_RowRight` exists. `test_bar_row.py`
runs both edits under Lua 5.1 against the client's own files.

#### The Talents button and key

The stock talent window is for a tamed beast's talents; a Hero's own are in
Hero Advancement. `ToggleTalentFrame` (the Talents micro button and the
`TOGGLETALENTS` key) opened it on the player's spec, and the addon turned it to
the pet's or closed it again. In combat it could not close it:
`HideUIPanel` from an addon slides the other panels through
`FramePositionDelegate` from tainted code, and a plain `Hide()` leaves the
frame in the delegate's slot, where `CloseWindows` keeps finding it and Escape
stops opening the game menu. So `UIParent.lua` gets a second edit
(`pet_talents_key`): without a pet that has talents
(`GetNumTalentGroups(false, true)`) `ToggleTalentFrame` shows the "tamed beast"
line and opens nothing, and with one it opens the pet's spec. The installer
builds the second `UIParent.lua` edit on the first. Other ways onto the player's
spec (the pet dismissed with the window up) still go through the addon, which
in combat waits for `PLAYER_REGEN_ENABLED` to close it. `test_talents_key.py`
runs the edited function under Lua 5.1, in and out of combat, with the stock one
for contrast.

#### Death Knight skins from any face

The skin arrows are stock; the filled-in faces do their work. The Face arrows
(next `0x4eb710`, prev `0x4eb990`) are made blind to those copies in two places:

- **Their colour count.** For each face they ask `0x4f3b10` how many colours
  it has and try `(counter + last chosen skin) % count`, writing the result
  back into the counter (a Blizzard quirk that adds the offset twice). The
  copies raise an undrawn face's count from 10 to 15, which changes every
  colour that formula picks and can skip faces altogether: at the last Death
  Knight skin the arrow cycled only the three drawn faces. Both count calls
  (`0x4eb781`, `0x4eba01`; file `0xEAB81`, `0xEAE01`) go to a 76-byte
  replacement that returns the same count minus trailing copies and empty
  slots, i.e. the stock count. It sits in `.text`'s file slack (VA
  `0x9de3b3`, file `0x5DD7B3`; 77 zero bytes before the raw data ends), and
  `.text`'s VirtualSize (header, file `0x210`) goes from `0x5DD3B3` to
  `0x5DD400` so the loader maps it.
- **"Does the face it found fit the skin on screen."** That reads one face
  row directly (`mov ecx,[ebp-8]; mov edx,[ebx+0x1c]` at `0x4eb8fb` /
  `0x4ebb79`; file `0xEACFB`, `0xEAF79`). Each becomes a call to a 17-byte
  routine that loads the same registers and zeroes the flags of a copy, so
  the gate refuses it. It sits in the int3 padding between a `ret` at
  `0x9296a1` and the function at `0x9296c0` (file `0x528AA2`), which nothing
  jumps into.

Both routines compare the row id with 30000, which must equal
`dbc.CHARSECTIONS_FILL_FIRST_ID` (`exepatch.FILL_FIRST_ID`; selftest checks).
The eight edits are one group (`FACE_ARROW`): each must sit at its 12340 file
offset, because the calls are relative, and they are applied, detected and
reverted all together or not at all. The source assembly is in
`lib/exepatch.py`.

`LEGACY_SKIN_FACE` is the routine that shipped in `b685c7a` and was replaced:
it switched faces from inside the skin arrows and never switched back.
`apply()` takes it out of an exe that has it before adding `FACE_ARROW`, and
`restore()` reverts either.

`test_skin_arrows.py` maps a copy of the exe in `unicorn`, lets the game's own
index builder (`0x4f3dd0`) load a CharSections table, and presses the real
arrows 30 times from every face of every race as a Paladin and as a Death
Knight. Stock exe, stock table: 520 of 628 skin runs never reach a Death
Knight skin. Stock exe, filled table: the Face arrows land on copies (1884 of
2512 runs). Patched exe, filled table: the skin arrows reach all three from
every face without changing it, and all 2512 Face arrow runs show exactly
what the stock exe shows on the stock table, face and skin, press by press.
Leaving out either routine fails those last two checks.

### The Mac and Switch clients — the same changes, in arm64

The Mac client is `World of Warcraft.app` and the Switch client `WoW.nro`, both
arm64 builds of wowdecomp (the `macos-arm64` and `switch-aarch64` branches of
<https://github.com/DustinHendrickson/wowdecomp>), each installed beside `Data`
(the Switch one in `sdmc:/switch/wow`). The realm hands every player the same
build, as every Windows player has the same `Wow.exe`, so they are patched the
same way: known bytes at known offsets, checked before anything is written.

`arm64_patch.json` holds, per build (keyed by its Mach-O UUID or NRO build id),
one group per `exepatch` site, each part `[file offset, stock bytes, patched
bytes]`. A group can hold no parts and a `built` note when the build has the
change already: the Switch build is made with the interface signature checks
off. The installer applies a build only when every part holds its stock bytes,
and reads it as patched only when every part holds its patched bytes. A build
neither table holds is worked out on the player's PC first (see below), and
refused when that fails. `lib/armpatch.py` does the bytes
(standard library only) and the NRO (backup `WoW.nro.classless-bak`, nothing
else: homebrew is not signed); `lib/macapp.py` the Mac bundle: it keeps
`World of Warcraft.app.classless-bak`, patches, and signs the app again with the
command wowdecomp's own build runs (`codesign --force --sign -`), because an
Apple Silicon Mac will not start an executable whose signature no longer
matches. Both run before any archive is written, so a failure leaves the game
folder as it was. A Switch player installs from a PC, pointed at the card.

`gen_arm64_patch.py` writes the table from a stock build. Each site is found by
its function's symbol and an exact run of instructions in it, which must occur
the expected number of times. A Mac app keeps its symbols; an NRO does not, so
the `Wow.elf` the same build writes is read for them (its build id must match).
A site may have several forms, because the two builds' compilers (Apple clang
17, LLVM clang 19 for `aarch64-none-elf`) lay some code out differently; the
first form whose every part is found is used. Edits that need more room than
they replace jump to a cave: code in executable padding the build does not use
(between the load commands and the first section of a Mac app, the end of an
NRO's code segment). Only `b` and `bl` reach a cave, since a conditional branch
reaches 1 MB. What differs from `Wow.exe`:

- **interface signatures** — Mac: the reject paths of `FrameXML_CheckSignature`
  go to its digest step and the answer is 3 (valid), the build's own
  `DISABLE_SIGNATURE_CHECKS` path. Switch: built with the checks off already.
- **eye glow** — `tst #0x14` has no arm64 encoding, so a cave tests both bits.
  The Switch build keeps the glow as a bit (`ubfx`), so its cave sets it.
- **the feral line** — the Mac compiler copied the Druid test into the four
  paths that reach it, so there it is four parts; the Switch build has one.
- **combo points, runes, reagents** — the Switch build branches where the Mac
  build uses `ccmp`, so those sites are a `nop` there.
- **nameplate colors** — `s_classColors` is filled from a read-only constant at
  startup; the constant is patched.
- **hunter pets** — `CanGainXP` and `GetPetPersonality` are rewritten in place
  to read the pet's power type at `+0x47`, as on Windows.

Every rebuild moves the code, and a player's installer handles that itself.
For a build `arm64_patch.json` does not hold, `install.py` calls
`gen_arm64_patch.learn()` on the player's PC: it generates the entry (an NRO's
symbols from the `Wow.elf` beside it, which is why Switch players get both
files), runs `test_arm64_patch.py` against it, and keeps it in that PC's
`arm64_patch.local.json` (git-ignored, never shipped) only when every check
passes; otherwise it is dropped and the install stops before writing anything.
The checks matter: a pattern can still match where a register a cave borrows
has become live, and only running the code shows that. capstone and unicorn
are installed on demand, as Pillow is. keystone is not, because it has no Apple
Silicon build: edits and caves are put together by `gen_arm64_patch.assemble()`,
which encodes branches itself and takes every other instruction from the
`encodings` table in `arm64_patch.json`. After changing `SITES` or `CAVES`, run
`gen_arm64_patch.py` on a build with keystone installed to refresh that table;
selftest fails until it covers every instruction and matches keystone.

Adding a build to the shipped table (`gen_arm64_patch.py <build>`) is optional:
it saves players the first-install step for that build. When `learn()` says a
build moved code (`SiteMissing`), give the site a form for it in `SITES`.

Checked on Windows: the Mac 3.3.5 build (UUID `7db2888e...`, 108 checks) and
the Switch build `5e4b1972...` (96 checks; the feral line is one site there),
every group's patched code running as the `Wow.exe` patch does and the stock
code not; installs, reinstalls and both uninstall routes on copies of each (Mac
`codesign` stubbed). Not checked: signing and play on a Mac, or play on a Switch.

## Testing

`test_skin_arrows.py` needs `pip install unicorn` and a client; it never writes
to the client:

```bash
python3 test_skin_arrows.py "B:/World.of.Warcraft.3.3.5a"
```

`test_power_sync.py` (unicorn) runs the patched power-update guard from a
patched copy of the client's bytes, for every pool against the bar's pool, and
the stock bytes for contrast. `test_bar_row.py` (lupa) runs the bar-row edits,
and `test_talents_key.py` (lupa) the Talents key edit:

```bash
python3 test_power_sync.py "B:/World.of.Warcraft.3.3.5a"
python3 test_bar_row.py "B:/World.of.Warcraft.3.3.5a"
python3 test_talents_key.py "B:/World.of.Warcraft.3.3.5a"
```

`test_elemental.py` checks the elemental-variant step against a DBC extract, no
client needed: it appends every variant in `elemental_manifest.json` to real
Spell, SpellVisual, SpellIcon and SkillLineAbility tables, reads the rows back
and compares them with the manifest, and paints every element's icon on a
synthetic BLP.

```bash
python3 test_elemental.py --dbc "B:/New folder/dbc"
```

`preview_elemental_icons.py` renders every shipped base icon in every element
from a real client's art into one sheet, at twice the in-game size, so a change
to the element colours or to `render_icon` can be judged before anyone
reinstalls:

```bash
python3 preview_elemental_icons.py "B:/World.of.Warcraft.3.3.5a" --out preview.png
```

The manifest itself is generated, together with the server's SQL, by
`data/sql/generators/gen_elemental_variants.py`; regenerate both from one run
so the server's numbers and the client's tooltips stay identical. Each run stamps a
twelve-digit generation id into both: the installer prints it in its report and the
worldserver logs it when it registers the variants, so a server and a client from
different runs can be told apart at a glance. Its defaults
produce the shipped set; `--bases ALL --elements ALL --ranks all` produces
every eligible strike, and `--bases "Sinister Strike" --elements fire --ranks
first` is the single-variant spike used to prove the pipeline. After any
regeneration the server needs a restart and every player a client reinstall.

`selftest.py` runs the whole pipeline against a real client without writing to it:

```bash
python3 selftest.py "B:/World.of.Warcraft.3.3.5a"
```

It resolves each source file through the archive chain, applies every transform,
builds the archives in a temp folder, reads them back, and — if `mpyq` is
installed — cross-checks with that independent reader.

It also checks `arm64_patch.json` against `exepatch` (a twin for every byte
patch in every build, the same Hero color and filled-face id). Name the Mac
and Switch builds to apply and revert the table on them in memory, and to
check the table is exactly what `gen_arm64_patch.py` writes from each:

```bash
python3 selftest.py "B:/World.of.Warcraft.3.3.5a" --macapp "B:/code/wowdecomp/bin/Mac/World of Warcraft.app" --nro "B:/code/wowdecomp/bin/Switch/WoW.nro"
```

`test_arm64_patch.py` (unicorn) runs the patched arm64 code itself, stock and
patched, for every group of one build:

```bash
python3 test_arm64_patch.py "B:/code/wowdecomp/bin/Mac/World of Warcraft.app"
python3 test_arm64_patch.py "B:/code/wowdecomp/bin/Switch/WoW.nro"
```

Run it against any client you can get hold of before tagging a release,
especially a non-enUS one.

## Known gaps

- Only `enUS` string keys are verified. Other locales use the same key names, so
  they should work, but the installer aborts with a clear message rather than
  writing a no-op patch if nothing matches.
- Incremental MPQ patch files (`MPQ_FILE_PATCH_FILE`) are not applied. No
  3.3.5a archive in the normal load order uses them; if one did, the reader
  raises rather than returning wrong bytes.
- `Wow.exe` is never modified, so the creation-screen *description text*
  (`--creation-text`) only works on clients that do not enforce GlueXML
  signatures. There is no in-installer bypass for clients that do.

## Extending the patch

`mpq.write_archive(path, {"archive\\path": b"..."})` takes any set of files, so
custom `Spell.dbc` rows, icons or `TalentTab.dbc` edits go in the same archive.
Keep DBC edits matched with the server-side data or the client will disagree
with the server.
