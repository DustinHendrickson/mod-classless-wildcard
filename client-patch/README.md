# Client setup

The classless system works on a stock 3.3.5a client with nothing installed.
This folder is the optional polish — run one installer and your client will:

- show every class as **Hero**, everywhere it appears
- reduce the class list to a **single choice per race** — there are no classes to
  pick between, so the screen stops offering ten
- install the **ClasslessWildcard** addon
- with `--creation-text`: hide the leftover class selector, dress the Hero in an
  armored starting outfit, and replace the class icon with a **Hero** emblem

It is one command and `--uninstall` puts your client back exactly as it was. The
default install writes only new patch files plus the addon and **never touches
`Wow.exe`**.

> The creation-screen **class description** is left as-is by default. Rewriting it to
> the Hero pitch means editing a *signed* interface file, so `--creation-text` also
> applies the well-known "allow custom interface" patch to `Wow.exe` (backed up first,
> reversible with `--uninstall`) so the client accepts it — see [Options](#options).
> The Hero name and single-class list do not need it.

---

## What you need

- Your **World of Warcraft 3.3.5a** folder — the one with `Wow.exe` and `Data` in it.
- **Python 3** (any version from 3.7 up).
  Windows: get it from [python.org/downloads](https://www.python.org/downloads/) and
  tick **"Add python.exe to PATH"** on the first screen of the installer.

Nothing else. No compiler, no StormLib, no MPQ editor, no extra downloads.

---

## Install

### Windows

**Double-click `install.bat`.**

It finds your WoW folder, asks whether to also install the Hero creation-screen
text (see below), shows what it is about to do, and confirms once before touching
anything. If it cannot find your client, drag your WoW folder onto `install.bat`
and drop it. **Close World of Warcraft first** if you say yes to the creation-screen
text, since that patches `Wow.exe`.

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
Patch archive     : patch-Z.MPQ
Class name        : Hero
Creation text     : no (safe default; class description unchanged)

Install to this client? [Y/n] y

  ChrClasses.dbc   10 classes renamed to Hero (from patch-enUS-3.MPQ)
  CharBaseInfo.dbc all 10 races, one cosmetic class (shown as Hero)
  -> Data/patch-Z.MPQ
  addon            12 files -> Interface/AddOns/ClasslessWildcard
  cache            cleared (the client rebuilds it on next login)

Done. Start the game and every class will read Hero.
```

Then just start the game. The default install writes only new patch files and the
addon — it never modifies `Wow.exe`, so it does not matter whether the game is open,
though a running client keeps the old files loaded until you restart it.

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

You will not normally need any of these.

**`--creation-text` is the one to know about.** The Hero *name* and the single-class
creation list come from data files (DBCs) that no client checks, so they always work.
The creation-screen *description paragraph* lives in `GlueStrings.lua`, a signed
interface file, so editing it also requires patching `Wow.exe` to accept custom
interface files. `--creation-text` does both: it installs the text **and** applies the
well-known "allow custom interface" byte patch (the same one the Project Reforged
patcher uses), after backing `Wow.exe` up to `Wow.exe.classless-bak`. `--uninstall`
restores the backup. This is confirmed working on a stock 3.3.5a build 12340 client. It is off by default because it modifies your executable, and
because if anything is off you would rather opt in deliberately: if the login screen
still shows *"interface files are corrupt"*, run `--uninstall`. Close the game before
running it — a running client locks `Wow.exe`.

| Option              | Effect                                                                  |
| ------------------- | ----------------------------------------------------------------------- |
| `--dry-run`         | Print the plan and write nothing                                        |
| `--uninstall`       | Undo everything the installer did                                       |
| `--yes` / `-y`      | Skip the confirmation prompt                                            |
| `--name Champion`   | Call every class something other than `Hero`                            |
| `--creation-text`   | Also rewrite the creation-screen class blurb (patches `Wow.exe` — see below) |
| `--no-exe`          | With `--creation-text`, install the text but do not patch `Wow.exe`     |
| `--no-addon`        | Do not install the addon                                                |
| `--locale enUS`     | Patch one locale only, on a multi-language client                       |

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

**The creation screen still shows the old class descriptions.**
That is the default — the description paragraph is only changed by `--creation-text`,
which is off because it can break clients that enforce interface signatures. The Hero
name and the single-class list are already applied.

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
