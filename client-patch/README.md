# Client patch (MPQ): "Hero" class + all race/class combos

Renames every class to **Hero** (or any name you choose) on the character
creation screen, character sheet, /who, chat and tooltips — the last visible
trace of the old classes. Class names come from `ChrClasses.dbc`, which ships
inside the client's MPQ archives and has **no signature check** (unlike
GlueXML), so this is a clean, ban-free data patch.

The chassis mechanics (which resource bar is displayed, base stats) are
unchanged — this is purely cosmetic naming. Everything else the classless
system needs is server-side + addon.

## Build the tool (once)

```bash
./build_mpqtool.sh          # clones & builds StormLib, compiles mpqtool
```

## What goes in the patch

- **ChrClasses.dbc** — every class renamed to "Hero" (creation screen,
  character sheet, /who, tooltips). Internal class tokens (WARRIOR, MAGE, …)
  are preserved so class colors, icons and addons keep working.
- **CharBaseInfo.dbc** — every race/class chassis combination unlocked on the
  creation screen (100 combos). Pair this with the module's
  `data/sql/db-world/optional/cw_all_race_class.sql`, which unlocks the same
  combos server-side (start locations, action bars, starter kits — stats are
  automatic on AzerothCore master since they derive from
  player_race_stats × player_class_stats).

## Make the patch

```bash
# 1. pull the original DBCs out of your client (adjust locale)
./mpqtool extract "/path/to/WoW/Data/enUS/locale-enUS.MPQ" \
    'DBFilesClient\ChrClasses.dbc' ChrClasses.dbc
./mpqtool extract "/path/to/WoW/Data/common.MPQ" \
    'DBFilesClient\CharBaseInfo.dbc' CharBaseInfo.dbc

# 2. rename all classes (pick any name) + unlock all combos (--no-dk to skip DK)
python3 make_hero_classes.py ChrClasses.dbc ChrClasses_hero.dbc --name Hero
python3 make_all_combos_charbaseinfo.py CharBaseInfo.dbc CharBaseInfo_all.dbc

# 3. pack them as a patch archive
./mpqtool create patch-4.MPQ \
    'ChrClasses_hero.dbc@DBFilesClient\ChrClasses.dbc' \
    'CharBaseInfo_all.dbc@DBFilesClient\CharBaseInfo.dbc'
```

## Install

Drop `patch-4.MPQ` into the client's `Data/` folder (next to patch.MPQ,
patch-2.MPQ, patch-3.MPQ). Patches load alphabetically/numerically, so `-4`
overrides the originals. Players delete their `Cache/` folder once and log in:
every class shows as **Hero**.

Distribute the MPQ to your players alongside the `ClasslessWildcard` addon —
a launcher or a zip with both is typical private-server practice.

## Verified

The whole pipeline (DBC rewrite → MPQ pack → list → extract → byte-identical
roundtrip → all names read back as "Hero") is exercised by the module's test
run against a synthetic ChrClasses.dbc. You run it against the real one from
your client, which we don't redistribute for copyright reasons.

## Extending the patch later

The same `mpqtool create` command takes any number of `file@mpqpath` pairs, so
future additions — custom `Spell.dbc` rows for exclusive classless spells,
custom icons, `TalentTab.dbc` tweaks — go into the same archive. Keep the DBC
edits matched with server-side data or the client will disagree with the
server.


## Creation-screen class description ("Hero" pitch instead of the Warrior blurb)

Two files, in order — try step A alone first; only do step B if the client
refuses the custom glue.

**A. The text (patch MPQ).** Rewrite the Warrior strings to the Hero pitch and
pack them; on many 3.3.5a clients this loads with no exe change at all:

    mpqtool extract "Data\enUS\locale-enUS.MPQ" \
        "Interface\GlueXML\GlueStrings.lua" GlueStrings.lua
    python3 make_hero_gluestrings.py GlueStrings.lua GlueStrings_hero.lua
    mpqtool create patch-enUS-4.MPQ \
        "GlueStrings_hero.lua@Interface\GlueXML\GlueStrings.lua"
    #   -> drop patch-enUS-4.MPQ into Data\enUS\

**B. Accept custom glue (exe patch, only if A shows a signature/corrupted
error).** `patch_client_exe.py` flips the single TOC-signature branch in the
client so custom GlueXML is accepted. It is run LOCALLY by each player on their
OWN Wow.exe — you never distribute a modified binary — and is safe and
reversible:

    python3 patch_client_exe.py --dry-run Wow.exe   # shows the site, writes nothing
    python3 patch_client_exe.py         Wow.exe   # backs up to Wow.exe.bak, patches
    python3 patch_client_exe.py --restore Wow.exe   # revert

It verifies the exe is the known build-12340 client by SHA-256, locates the
patch site by a unique byte pattern (74 28 -> EB 28 at VA 0x40303F), refuses on
any mismatch, always writes Wow.exe.bak first, and detects an already-patched
exe. Verified and round-trip tested against the standard 3.3.5a 12340 Wow.exe
(SHA-256 aa63a575...e88cb8). A different build/locale aborts safely instead of
corrupting anything — send its SHA-256 to add support rather than forcing it.
