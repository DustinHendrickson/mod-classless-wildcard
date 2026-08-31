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

The shell is Warrior (`SHELL_CLASS` in `install.py`) and it has *nothing to do
with the server's chassis*. The server converts every new character to its
configured chassis at creation, so what the client sends is irrelevant; the
class list exists only to show the Hero name, pitch and bullets once instead of
ten identical times. Warrior is the shell because vanilla already permits it
for 9 of the 10 races — the module's auto-applied `cw_world_hero_races.sql`
adds the one missing server row (Blood Elf Warrior), so no manual SQL is
involved.

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

### `CharacterCreate.lua` — hide the single-class selector (`--creation-text`)

The server offers one class per race, so the creation screen shows a lone class
button. `lib/charcreate.py` appends a hook to the client's own
`CharacterCreate.lua` that wraps `CharacterCreateEnumerateClasses` and hides
every `CharacterCreateClassButton` after the original runs. Append-only: the
original file is passed through untouched. Class selection is separate state
(`SetCharacterClass`, driven by `GetSelectedClass`), so hiding the buttons does
not affect Accept. The override ships in the locale patch, which outranks the
client pack's copy.

### `CharStartOutfit.dbc` — the armored Hero look (`--creation-text`)

74 `uint32` per record: ID, packed `(race,class,gender,outfit)`, then
`ItemID[24]`, `DisplayInfoID[24]`, `InventoryType[24]`. The model is drawn from
the **DisplayInfoID** array, not the item IDs.

`lib/outfit.py` rewrites the shell-class (Warrior) rows to wear the Death Knight
starting plate: DK (class 6) has a row for every race and gender, so the display
IDs are real and verified rather than invented. The head slot (InventoryType 1)
is dropped so the customized face stays visible, and a two-hander is kept so the
Hero is armed. It also **adds** a shell-class row for Blood Elf, which has no
vanilla Warrior outfit and would otherwise appear in underwear (126 → 128
records).

### `UI-Classes-Circles.blp` — the Hero emblem (`--hero-icon`)

The class icon is a 4×4 grid in a 256×256 atlas (`CLASS_ICON_TCOORDS` maps each
token to a cell). `lib/blp.py` **decodes** the client's own atlas (`decode_blp`,
handling palettized and DXT1/3/5), pastes the gold emblem into **only the Death
Knight cell** (`_HERO_CELL_TC` = {0.25, 0.5, 0.5, 0.75}), and re-encodes. Death
Knight is disabled in the mod -- it IS the "Hero" class type -- so its cell is
free to carry the mark, and every other class icon is preserved untouched, which
matters because the addon groups abilities by their source class using those
icons. The Hero shows this emblem when its chassis class is Death Knight. Writes over
`Interface\TargetingFrame\UI-Classes-Circles.blp` (in-game, character select,
the addon's icons) and the creation-screen atlas.

> An earlier version filled *every* cell with the emblem, which erased the class
> icons the addon needs and drew the Hero mark over every ability group. Only the
> Death Knight (Hero) cell may change.

To read the pristine original on a reinstall (not the installer's own previous
output), `install.py` builds its `ClientFiles` with `exclude=` set to the patch
archives it is about to write.

The BLP **format matters** — a wrong header makes the client draw a green
"missing texture" box everywhere the icon is used. Matched byte-for-byte against
the genuine enc=1 textures the client ships: header `01 08 08 01` (encoding 1
palettized, alphaDepth 8, **alphaType 8**, **hasMips 1**) with a **full mip
chain** (256→1, `w*h` index bytes + `w*h` alpha bytes per level). alphaType 0 or
a missing mip chain both fail to load. Pillow is optional; without it the icon
step is skipped, not fatal.

The full Hero client -- name, single-class list, text, outfit, icon, exe patch,
addon -- installs by **default**; `--minimal` and the `--no-*` flags turn pieces
off. The icon needs no exe patch (textures are not signature-checked) and can be
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

## Testing

`selftest.py` runs the whole pipeline against a real client without writing to it:

```bash
python3 selftest.py "B:/World.of.Warcraft.3.3.5a"
```

It resolves each source file through the archive chain, applies every transform,
builds the archives in a temp folder, reads them back, and — if `mpyq` is
installed — cross-checks with that independent reader.

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
