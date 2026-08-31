# Client setup

The classless system works on a stock 3.3.5a client with nothing installed.
This folder is the optional polish — run one installer and your client will:

- show every class as **Hero**, everywhere it appears
- reduce the class list to a **single choice per race** — there are no classes to
  pick between, so the screen stops offering ten
- explain the classless system on the creation screen instead of the old class blurb
- install the **ClasslessWildcard** addon

It is one command, it backs up anything it changes, and `--uninstall` puts your
client back exactly as it was.

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

It finds your WoW folder, shows you what it is about to do, and asks once before
touching anything. If it cannot find your client, drag your WoW folder onto
`install.bat` and drop it.

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
Patch archives    : patch-Z.MPQ  (+ patch-<locale>-Z.MPQ)
Class name        : Hero

Install to this client? [Y/n] y

  ChrClasses.dbc   10 classes renamed to Hero (from patch-enUS-3.MPQ)
  CharBaseInfo.dbc all 10 races, one cosmetic class (shown as Hero)
  -> Data/patch-Z.MPQ
  GlueStrings.lua  76 class strings rewritten (from patch-enUS-3.MPQ)
  -> Data/enUS/patch-enUS-Z.MPQ
  Wow.exe          patched at file offset 0x243F (backup: Wow.exe.classless-bak)
  addon            12 files -> Interface/AddOns/ClasslessWildcard
  cache            cleared (the client rebuilds it on next login)

Done. Start the game and every class will read Hero.
```

Then just start the game. **Close WoW before running the installer** — Windows will
not let it replace `Wow.exe` while the game is open.

---

## Uninstall

```bash
python3 install.py --uninstall "C:\Games\World of Warcraft"
```

Windows users can run `install.bat --uninstall` instead.

This removes the patch archives, restores `Wow.exe` from the backup it made,
removes the addon and clears the cache. Your client is back to stock.

---

## Options

You will not normally need any of these.

| Option              | Effect                                                                  |
| ------------------- | ----------------------------------------------------------------------- |
| `--dry-run`         | Print the plan and write nothing                                        |
| `--uninstall`       | Undo everything the installer did                                       |
| `--yes` / `-y`      | Skip the confirmation prompt                                            |
| `--name Champion`   | Call every class something other than `Hero`                            |
| `--no-glue`         | Skip the creation-screen text (and the `Wow.exe` change it needs)       |
| `--no-exe`          | Never touch `Wow.exe`                                                   |
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

**"Could not find the signature check in Wow.exe."**
The installer could not locate the exact spot it needs, so it wrote nothing.
Many private-server client packs already ship a `Wow.exe` that accepts custom
interface files, in which case everything works anyway — re-run with `--no-exe`
to skip that step. Everything else still installs.

**Permission denied writing Wow.exe.**
Close the game. On Windows, run the command prompt as Administrator if your WoW
folder lives under `C:\Program Files`.

**Classes still show their old names.**
Delete the `Cache` folder in your WoW directory and start the game again. The
installer does this for you, but a client left running can write it back.

**The creation screen still shows the old class descriptions.**
That part needs the `Wow.exe` change. Check it applied:

```bash
python3 patch_client_exe.py --status "C:\Games\World of Warcraft\Wow.exe"
```

---

## A note on what gets shipped

This folder contains no Blizzard data. The installer reads the DBC and interface
files out of **your own client**, edits them on your machine, and writes the result
into a new patch archive next to the originals. Your original files are never
modified — patch archives sit on top of them, and deleting them reverts everything.

`Wow.exe` is the one file changed in place, and only so it will accept the custom
creation screen. Two bytes change. The installer copies it to
`Wow.exe.classless-bak` first, requires the spot it edits to be unambiguous, checks
the bytes are what it expects before writing, and refuses rather than guessing if
anything looks different.

Server admins and anyone curious about how the patch is built: see
[`MAINTAINERS.md`](MAINTAINERS.md).
