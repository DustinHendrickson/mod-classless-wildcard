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

### `Wow.exe` — not touched

**The installer no longer patches `Wow.exe`.** An earlier version flipped one
byte at file offset `0x243F` (`74 28` → `EB 28`) intending to disable the
GlueXML `## Signature:` scope check so a custom creation-screen would be
accepted. It did not work: on a real stock build-12340 client the patch applied
cleanly yet the client still rejected the custom `GlueStrings.lua` with *"Your
login interface files are corrupt"*. The exact site was never verified against a
disassembly, so shipping it did nothing but risk bricking clients.

`lib/exepatch.py` is kept only for its `inspect()` / `restore()` — so
`--uninstall` can undo an exe that an older version patched — and its `apply()`
is unused. If you want to revisit accepting custom GlueXML, verify the check in a
debugger against the specific client first; do not re-enable a blind byte-flip.

This is why `--creation-text` is opt-in and carries a loud warning: replacing
`GlueStrings.lua` only works on clients that do not enforce interface signatures,
and there is currently no reliable in-installer way to make one that does accept
it.

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
