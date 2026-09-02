# Client setup

The classless system works on a stock 3.3.5a client with nothing installed.
This folder is the optional polish. **One installer sets up the full Hero client:**

- every class shows as **Hero**, everywhere it appears
- the creation screen offers a **single class per race** (no class to choose)
- the creation-screen **class description** is the Hero pitch, and the leftover
  class selector is hidden
- new characters wear an **armored Hero outfit** on the creation screen
- the **Hero emblem** replaces the class icon *for the Hero only* — every other
  class icon is kept, so your addon can still group abilities by class
- the **ClasslessWildcard** addon is installed

The creation-screen text is a *signed* interface file, so the installer also applies
the well-known "allow custom interface" patch to `Wow.exe` (backed up first,
reversible with `--uninstall`). **Close World of Warcraft before installing.**

Want less? `--minimal` installs only the Hero name, the single-class list and the
addon, and never touches `Wow.exe`. `--uninstall` always restores everything.

> The Hero emblem needs the Python **Pillow** library (`pip install pillow`). Without
> it the icon step is skipped and the rest installs normally.

---

## What you need

- Your **World of Warcraft 3.3.5a** folder — the one with `Wow.exe` and `Data` in it.
- **Python 3** (any version from 3.7 up).
  Windows: get it from [python.org/downloads](https://www.python.org/downloads/) and
  tick **"Add python.exe to PATH"** on the first screen of the installer.

Nothing else. No compiler, no StormLib, no MPQ editor, no extra downloads.

> The one exception is `--hero-icon` (the custom class emblem), which needs the
> Python **Pillow** imaging library (`pip install pillow`). Every other feature,
> including the default install, needs nothing beyond Python 3. Without Pillow the
> icon step is simply skipped.

---

## Install

### Windows

**Double-click `install.bat`.**

It finds your WoW folder, shows what it is about to do, and confirms once before
touching anything. If it cannot find your client, drag your WoW folder onto
`install.bat` and drop it. **Close World of Warcraft first** — the install patches
`Wow.exe`, which the running game locks.

### macOS / Linux

```bash
./install.sh "/path/to/World of Warcraft"
```

### Any system, explicitly

```bash
python3 install.py "C:\Games\World of Warcraft"
```

Want to see exactly what would happen before committing to it?

```bash
python3 install.py --dry-run "C:\Games\World of Warcraft"
```

That writes nothing at all — it just prints the plan.

### What you should see

```
mod-classless-wildcard client installer
=======================================

World of Warcraft : C:\Games\World of Warcraft
Locales           : enUS
Class name        : Hero
Creation text     : yes
Armored outfit    : yes
Hero class icon   : yes
Patch Wow.exe     : yes
Addon             : yes

Install to this client? [Y/n] y

  ChrClasses.dbc   10 classes renamed to Hero
  ChrClasses.dbc   ranged slot restored on 4 relic classes (bows, guns and wands now show)
  CharBaseInfo.dbc all 10 races, one cosmetic class (shown as Hero)
  CharStartOutfit.dbc  armored Hero look on 18 races +Blood Elf
  -> Data/patch-Z.MPQ
  GlueStrings.lua  76 class strings rewritten
  CharacterCreate.lua  class selector hidden
  Hero class icon      emblem on the Hero cell, other class icons kept
  -> Data/enUS/patch-enUS-Z.MPQ
  Wow.exe          patched 6 site(s) to accept custom interface files
  addon            12 files -> Interface/AddOns/ClasslessWildcard
  cache            cleared (the client rebuilds it on next login)

Done. Start the game and every class will read Hero.
```

Then just start the game.

---

## Uninstall

```bash
python3 install.py --uninstall "C:\Games\World of Warcraft"
```

Windows users can run `install.bat --uninstall` instead.

This removes the patch archives, removes the addon, clears the cache, and — if an
older version had patched `Wow.exe` — restores it from the backup. Your client is
back to stock.

---

## Options

The full Hero client installs by default. These turn pieces off.

| Option                | Effect                                                                |
| --------------------- | --------------------------------------------------------------------- |
| `--dry-run`           | Print the plan and write nothing                                      |
| `--uninstall`         | Undo everything the installer did                                     |
| `--yes` / `-y`        | Skip the confirmation prompt                                          |
| `--name Champion`     | Call the class something other than `Hero`                            |
| `--minimal`           | Only the Hero name + single-class list + addon (no text, outfit, icon, or exe patch) |
| `--no-creation-text`  | Skip the Hero text + armored outfit (and the `Wow.exe` patch they need) |
| `--no-hero-icon`      | Keep the stock class icon instead of the Hero emblem                  |
| `--no-exe`            | Install the text but not the `Wow.exe` patch (only for clients that already accept custom UI) |
| `--no-addon`          | Do not install the addon                                              |
| `--locale enUS`       | Patch one locale only, on a multi-language client                     |

The `Wow.exe` patch is the well-known "allow custom interface" patch (the same one the
Project Reforged patcher uses), confirmed working on a stock 3.3.5a build 12340 client.
It is backed up to `Wow.exe.classless-bak` and restored by `--uninstall`.

---

## Troubleshooting

**"Python 3 is required and was not found."**
Install Python and make sure you ticked *Add python.exe to PATH*. Restart the
command prompt afterwards.

**"That is not a World of Warcraft folder."**
Give it the folder that directly contains `Wow.exe` and `Data`, not a parent
folder and not the `Data` folder itself.

**"Your login interface files are corrupt" at the login screen.**
The `Wow.exe` patch that `--creation-text` applies did not take — most often because
the game was open when you ran the installer, so the exe could not be written (the
output would have said *"close the game and re-run"*). Close World of Warcraft
completely and run `--creation-text` again. If it still happens after a clean patch,
your client is one the known patch does not fit — run `--uninstall`; the Hero name and
single-class list work without it.

**Permission denied writing Wow.exe.**
Close the game. On Windows, run the command prompt as Administrator if your WoW
folder lives under `C:\Program Files`.

**Classes still show their old names.**
Delete the `Cache` folder in your WoW directory and start the game again. The
installer does this for you, but a client left running can write it back.

**Class icons show as a green box.**
That means a `--hero-icon` install wrote a texture the client could not read.
Current versions match the client's own texture format, so update and re-run; if
it persists, reinstall with `--no-hero-icon` to keep the stock icon; everything else
is unaffected.

**The creation screen still shows the old class descriptions.**
The `Wow.exe` patch that lets the client load the custom text did not take — usually
because the game was open during install (it locks `Wow.exe`). Close the game fully and
run the installer again, or check with `--dry-run` whether it reports the exe as patched.

---

## A note on what gets shipped

This folder contains no Blizzard data. The installer reads the DBC and interface
files out of **your own client**, edits them on your machine, and writes the result
into a new patch archive next to the originals. Your original files are never
modified — patch archives sit on top of them, and deleting them reverts everything.

`Wow.exe` is **never** modified by a default install — only new patch archives (which
sit on top of your originals) and the addon folder are written, so nothing you already
had is changed and deleting them reverts everything. The optional `--creation-text`
adds the rewritten `GlueStrings.lua` and applies the "allow custom interface" patch to
`Wow.exe` so the client accepts it; the exe is backed up to `Wow.exe.classless-bak`
first and `--uninstall` restores it. The patch only ever writes when its exact byte
sites are found in your exe, so a client it does not fit is left untouched rather than
corrupted.

Server admins and anyone curious about how the patch is built: see
[`MAINTAINERS.md`](MAINTAINERS.md).
