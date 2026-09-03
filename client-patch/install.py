#!/usr/bin/env python3
"""One-step client setup for mod-classless-wildcard.

Point this at a World of Warcraft 3.3.5a folder and it does everything the
client side needs:

  * builds a data patch from the player's OWN client files and drops it in
    Data/ (every class shows as Hero; the creation screen lists one class)
  * installs the ClasslessWildcard addon
  * clears the client Cache so the new data is picked up

The default install never modifies Wow.exe. The optional --creation-text flag
also rewrites the creation-screen class blurb; because that is a signed
interface file, --creation-text also applies the well-known "allow custom
interface" patch to Wow.exe (backed up first) so the client loads it. Confirmed
working on a stock 3.3.5a build 12340 client. Off by default because it edits
the executable.

Everything is reversible with --uninstall.

Requires nothing but Python 3.7+. No compiler, no StormLib, no other packages.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from lib import (blp, charcreate, clientfs, dbc, elemental, exepatch,  # noqa: E402
                 gluestrings, mpq, outfit)

MANIFEST_NAME = "ClasslessWildcard-install.json"
ADDON_NAME = "ClasslessWildcard"

CHRCLASSES = "DBFilesClient\\ChrClasses.dbc"
CHARBASEINFO = "DBFilesClient\\CharBaseInfo.dbc"
CHARSTARTOUTFIT = "DBFilesClient\\CharStartOutfit.dbc"
SKILLRACECLASSINFO = "DBFilesClient\\SkillRaceClassInfo.dbc"
SKILLLINEABILITY = "DBFilesClient\\SkillLineAbility.dbc"
SKILLLINE = "DBFilesClient\\SkillLine.dbc"
GLUESTRINGS = "Interface\\GlueXML\\GlueStrings.lua"
CHARCREATE_LUA = "Interface\\GlueXML\\CharacterCreate.lua"
CLASSICONS_INGAME = "Interface\\TargetingFrame\\UI-Classes-Circles.blp"
CLASSICONS_CREATE = "Interface\\Glues\\CharacterCreate\\UI-CharacterCreate-Classes.blp"

COMMON_INSTALL_DIRS = [
    r"C:\World of Warcraft",
    r"C:\Games\World of Warcraft",
    r"C:\Program Files (x86)\World of Warcraft",
    r"C:\Program Files\World of Warcraft",
    os.path.expanduser("~/World of Warcraft"),
    os.path.expanduser("~/Games/World of Warcraft"),
    os.path.expanduser("~/Applications/World of Warcraft"),
]


class Abort(Exception):
    """A clean, explained failure -- printed without a traceback."""


# ---------------------------------------------------------------- discovery

def resolve_child(parent, name):
    """Find `name` inside `parent` ignoring case, for Linux and macOS.

    Returns the existing path if there is one, otherwise the plain join so the
    caller can create it with the spelling we prefer.
    """
    direct = os.path.join(parent, name)
    if os.path.exists(direct):
        return direct
    try:
        entries = os.listdir(parent)
    except OSError:
        return direct
    lowered = name.lower()
    for entry in entries:
        if entry.lower() == lowered:
            return os.path.join(parent, entry)
    return direct


def resolve_path(root, *parts):
    path = root
    for part in parts:
        path = resolve_child(path, part)
    return path


def looks_like_client(path) -> bool:
    if not path or not os.path.isdir(path):
        return False
    if not os.path.isdir(resolve_child(path, "Data")):
        return False
    if find_wow_exe(path):
        return True
    # a macOS client has no Wow.exe; the data patches still apply
    return os.path.exists(resolve_child(path, "World of Warcraft.app"))


def find_wow_exe(wow_dir):
    try:
        entries = os.listdir(wow_dir)
    except OSError:
        return None
    for entry in entries:
        if entry.lower() == "wow.exe":
            candidate = os.path.join(wow_dir, entry)
            if os.path.isfile(candidate):
                return candidate
    return None


def autodetect_client():
    """Look in the obvious places before asking the player to type a path."""
    candidates = []

    # the installer may have been copied into the client folder itself
    probe = HERE
    for _ in range(4):
        candidates.append(probe)
        probe = os.path.dirname(probe)

    candidates.append(os.getcwd())
    candidates.extend(COMMON_INSTALL_DIRS)

    seen = set()
    for path in candidates:
        real = os.path.abspath(path)
        if real in seen:
            continue
        seen.add(real)
        if looks_like_client(real):
            return real
    return None


def prompt_for_client():
    if not sys.stdin or not sys.stdin.isatty():
        return None
    print("Could not find your World of Warcraft folder automatically.")
    print("It is the folder that contains Wow.exe and the Data folder.")
    print()
    try:
        raw = input("Path to your WoW 3.3.5a folder (or blank to cancel): ")
    except (EOFError, KeyboardInterrupt):
        return None
    raw = raw.strip().strip('"').strip("'")
    return raw or None


# ------------------------------------------------------------------- build

# The one class the creation screen offers, shown as "Hero". This IS the chassis
# class (Paladin): a Hero is created as a Paladin directly, so there is no
# runtime class conversion, mana is native, and the Paladin class icon (which
# the client patch reskins to the Hero emblem) shows from creation onward.
# Paladin is not vanilla-creatable by every race, so the module's
# cw_world_hero_races.sql adds the missing playercreateinfo rows server-side.
SHELL_CLASS = 2


def build_data_patch(files, name, report, theme=False):
    """Assemble the base patch archive contents from the client's own DBCs.

    theme=True (with --creation-text) also gives the Hero the armored starting
    outfit via CharStartOutfit.dbc.
    """
    payload = {}

    raw, source = files.find(CHRCLASSES)
    patched, renamed = dbc.rename_all_classes(raw, name)
    # Slot 17 is a RELIC slot for Paladin, Death Knight, Shaman and Druid, and
    # the client never draws a relic. With the default Paladin chassis that
    # made every bow, gun and wand invisible on the character. Turn it back
    # into an ordinary ranged slot.
    patched, unrelic = dbc.clear_relic_slot(patched)
    payload[CHRCLASSES] = patched
    report.append("  ChrClasses.dbc   %d classes renamed to %s (from %s)"
                  % (len(renamed), name, os.path.basename(source)))
    report.append("  ChrClasses.dbc   ranged slot restored on %d relic classes "
                  "(bows, guns and wands now show)" % len(unrelic))

    raw, source = files.find(CHARBASEINFO)
    patched, races = dbc.single_class_combos(raw, SHELL_CLASS)
    payload[CHARBASEINFO] = patched
    report.append("  CharBaseInfo.dbc all %d races, one cosmetic class "
                  "(shown as %s)" % (races, name))

    # The client decides spellbook tabs from its OWN copy of this table, so
    # the server opening every class skill line to every class was invisible
    # to it: a Hero given Balance for a rolled Moonfire still had no Balance
    # tab, because the client's table said Balance is for Druids. Open the
    # client the same way the server was opened.
    raw, source = files.find(SKILLRACECLASSINFO)
    patched, opened, already = dbc.open_class_skill_lines(raw)
    payload[SKILLRACECLASSINFO] = patched
    report.append("  SkillRaceClassInfo.dbc  %d class skill lines opened to every class "
                  "(from %s)" % (len(opened), os.path.basename(source)))

    # This is the one that actually decides spellbook tabs. The client fixes a
    # class's tab set from SkillLineAbility's ClassMask and files a known spell
    # under a tab only if the spell's own row says it belongs to this class --
    # so a rolled Eviscerate sat in General while its row said "Rogue". Make
    # every class spell belong to every class; empty tabs stay hidden.
    categories = dbc.skill_line_categories(files.find(SKILLLINE)[0])
    raw, source = files.find(SKILLLINEABILITY)
    patched, changed, already = dbc.open_class_abilities(raw, categories)
    payload[SKILLLINEABILITY] = patched
    report.append("  SkillLineAbility.dbc  %d class spells now belong to every class "
                  "(spellbook tabs for cross-class spells; from %s)"
                  % (changed, os.path.basename(source)))

    if theme:
        try:
            raw, source = files.find(CHARSTARTOUTFIT)
            patched, updated, added = outfit.build_hero_outfit(raw, SHELL_CLASS)
            payload[CHARSTARTOUTFIT] = patched
            report.append("  CharStartOutfit.dbc  starter gear on the preview, %d "
                          "rows updated + %d added (from %s)"
                          % (updated, added, os.path.basename(source)))
        except (FileNotFoundError, outfit.OutfitError) as error:
            report.append("  CharStartOutfit.dbc  skipped (%s)" % error)

    return payload


def build_locale_patch(files, name, report, locale, theme=False, icon=False):
    """Assemble the locale patch archive contents for one locale.

    theme -> the Hero creation-screen text + hidden class selector.
    icon  -> the Hero emblem over the class icon (independent; needs no exe
             patch, but replaces UI-Classes-Circles, used all over the UI, so
             it is its own opt-in).
    Returns a possibly-empty payload.
    """
    payload = {}

    if theme:
        raw, source = files.find(GLUESTRINGS)
        text = raw.decode("utf-8", "surrogateescape")
        new_text, replaced = gluestrings.rewrite(text, name)
        if not replaced:
            raise Abort(
                "Found GlueStrings.lua for %s but none of the class description "
                "keys matched, so the creation screen would be unchanged.\n"
                "This locale names its strings differently and needs a look. "
                "Drop --creation-text to install everything else." % locale)
        report.append("  GlueStrings.lua  %d class strings rewritten (from %s)"
                      % (len(replaced), os.path.basename(source)))
        payload[GLUESTRINGS] = new_text.encode("utf-8", "surrogateescape")

        try:
            raw, source = files.find(CHARCREATE_LUA)
        except FileNotFoundError:
            report.append("  CharacterCreate.lua  not found; selector left visible")
        else:
            lua = raw.decode("utf-8", "surrogateescape")
            hooked = charcreate.add_hide_class_hook(lua)
            payload[CHARCREATE_LUA] = hooked.encode("utf-8", "surrogateescape")
            report.append("  CharacterCreate.lua  class selector hidden (from %s)"
                          % os.path.basename(source))

    if icon:
        try:
            raw, source = files.find(CLASSICONS_INGAME)
        except FileNotFoundError:
            raw = None
        atlas = blp.reskin_hero_cell(raw) if raw else None
        if atlas is None and raw is not None:
            raise Abort("The Hero class icon could not be painted: the Python library "
                        "'Pillow' is missing. Run:  python -m pip install --user pillow")
        elif atlas is None:
            report.append("  Hero class icon      skipped (class-icon atlas not found)")
        else:
            # ONLY UI-Classes-Circles (the player's own class icon: unit frames,
            # character select). The addon draws its ability-group tabs from
            # UI-CharacterCreate-Classes, which is deliberately left alone, so
            # every class icon there stays intact for by-class grouping.
            payload[CLASSICONS_INGAME] = atlas
            report.append("  Hero class icon      emblem on the Hero's own class "
                          "icon; addon class icons untouched (from %s)"
                          % os.path.basename(source))

    return payload


# ----------------------------------------------------------------- actions

def install_addon(wow_dir, dry_run, report, files=None):
    source = os.path.abspath(os.path.join(HERE, os.pardir, "client-addon", ADDON_NAME))
    if not os.path.isdir(source):
        report.append("  addon            SKIPPED, not found at %s" % source)
        return None
    target = resolve_path(wow_dir, "Interface", "AddOns", ADDON_NAME)
    if not dry_run:
        if os.path.isdir(target):
            shutil.rmtree(target)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copytree(source, target)
    count = sum(len(names) for _root, _dirs, names in os.walk(source))
    report.append("  addon            %d files -> Interface/AddOns/%s"
                  % (count, ADDON_NAME))

    # give the addon its OWN copy of the class-icon atlas, built from the
    # client, so it does not depend on the shared game texture (the addon falls
    # back to that texture if this is absent)
    if files is not None:
        try:
            raw, _src = files.find(CLASSICONS_CREATE)
        except FileNotFoundError:
            raw = None
        atlas = blp.build_addon_class_atlas(raw) if raw else None
        if atlas is not None and not dry_run:
            with open(os.path.join(target, "classicons.blp"), "wb") as handle:
                handle.write(atlas)
        if atlas is not None:
            report.append("  addon class icons    embedded (classicons.blp)")
        elif raw is not None:
            raise Abort("The addon class icons could not be painted: the Python library "
                        "'Pillow' is missing. Run:  python -m pip install --user pillow")

    return os.path.relpath(target, wow_dir).replace("\\", "/")


def clear_cache(wow_dir, dry_run, report):
    cache = resolve_child(wow_dir, "Cache")
    if not os.path.isdir(cache):
        report.append("  cache            nothing to clear")
        return
    if not dry_run:
        shutil.rmtree(cache, ignore_errors=True)
    report.append("  cache            cleared (the client rebuilds it on next login)")


def read_manifest(wow_dir):
    path = os.path.join(wow_dir, MANIFEST_NAME)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def write_manifest(wow_dir, data, dry_run):
    if dry_run:
        return
    path = os.path.join(wow_dir, MANIFEST_NAME)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


# ----------------------------------------------------------------- install

def do_install(args, wow_dir):
    data_dir = resolve_child(wow_dir, "Data")
    exe = find_wow_exe(wow_dir)

    locales = clientfs.detect_locales(data_dir)
    if args.locale:
        if args.locale not in locales:
            raise Abort("locale %s not found in %s (present: %s)"
                        % (args.locale, data_dir, ", ".join(locales) or "none"))
        locales = [args.locale]
    if not locales:
        raise Abort("no locale folder (enUS, deDE, ...) found in %s" % data_dir)

    previous = read_manifest(wow_dir)
    suffix = (previous or {}).get("suffix")
    if not suffix:
        suffix = clientfs.free_patch_suffix(data_dir, locales)
    if not suffix:
        raise Abort("every patch letter from A to Z is already taken in %s"
                    % data_dir)

    def yn(on):
        return "yes" if on else "no"

    print("World of Warcraft : %s" % wow_dir)
    print("Locales           : %s" % ", ".join(locales))
    print("Class name        : %s" % args.name)
    print("Creation text     : %s" % yn(args.glue))
    print("Armored outfit    : %s" % yn(args.glue))
    print("Hero class icon   : %s" % yn(args.hero_icon))
    print("Elemental variants: %s" % yn(args.elemental))
    print("Patch Wow.exe     : %s" % yn(args.exe))
    print("Addon             : %s" % yn(args.addon))
    if previous:
        print("Note              : replacing a previous install (same letter)")
    print()

    if args.exe:
        print("  This installs the full Hero client. The creation-screen text edits")
        print("  a signed interface file, so Wow.exe is patched (the well-known")
        print("  \"allow custom interface\" patch) to accept it -- backed up first to")
        print("  Wow.exe.classless-bak and reversible with --uninstall. CLOSE THE")
        print("  GAME before running this, or the patch cannot be written.")
        print()

    if not args.yes and not args.dry_run:
        if sys.stdin and sys.stdin.isatty():
            answer = input("Install to this client? [Y/n] ").strip().lower()
            if answer and not answer.startswith("y"):
                raise Abort("cancelled; nothing was changed")
        print()

    report = []
    written = []

    # read sources as if OUR OWN previous archives were not there, so a
    # reinstall always builds from the pristine client files, never its output
    def own_archives(locale):
        return {"patch-%s.MPQ" % suffix, "patch-%s-%s.MPQ" % (locale, suffix)}

    # base patch: built once, from the highest-priority locale's chain
    with clientfs.ClientFiles(data_dir, locales[0],
                              exclude=own_archives(locales[0])) as files:
        dbc_payload = build_data_patch(files, args.name, report, theme=args.glue)
        # Elemental ability variants: the server's generated spell rows have
        # to exist in the client's own Spell.dbc too, or the game has no name,
        # icon or tooltip for them. Appended to the player's tables, with one
        # painted icon per base icon and element.
        if args.elemental:
            manifest_file = elemental.manifest_path()
            if os.path.exists(manifest_file):
                try:
                    manifest = elemental.load_manifest(manifest_file)
                    elemental.apply(files, dbc_payload, manifest, report)
                except (elemental.ElementalError, dbc.DbcError, FileNotFoundError) as error:
                    report.append("  elemental variants  skipped (%s)" % error)
            else:
                report.append("  elemental variants  skipped (no elemental_manifest.json shipped)")
    target = os.path.join(data_dir, "patch-%s.MPQ" % suffix)
    if not args.dry_run:
        mpq.write_archive(target, dbc_payload)
    written.append("Data/patch-%s.MPQ" % suffix)
    report.append("  -> Data/patch-%s.MPQ" % suffix)

    # Locale patches -- and the DBCs go in here TOO, which is the part that
    # actually matters. Wow.exe loads every locale patch archive above every
    # base one (see clientfs.archive_chain), so a DBC that also ships in a
    # patch-<loc>-N archive is shadowed if we only put ours in patch-Z.MPQ.
    # That is every DBC we touch: ChrClasses lives in patch-enUS-3,
    # CharStartOutfit and SkillRaceClassInfo in patch-enUS-2, CharBaseInfo in
    # locale-enUS. For a long time the class rename, the relic-slot fix and
    # the skill-line rows were all written correctly and never loaded, while
    # the Lua and strings -- which always went to the locale archive -- worked,
    # which made it look as though the patch was applying.
    #
    # The base archive is still written so a locale folder without a locale
    # patch of its own is covered, but the locale copy is the one that wins.
    for locale in locales:
        with clientfs.ClientFiles(data_dir, locale,
                                  exclude=own_archives(locale)) as files:
            payload = build_locale_patch(files, args.name, report, locale,
                                         theme=args.glue, icon=args.hero_icon)
        payload.update(dbc_payload)
        name = "patch-%s-%s.MPQ" % (locale, suffix)
        target = os.path.join(data_dir, locale, name)
        if not args.dry_run:
            mpq.write_archive(target, payload)
        written.append("Data/%s/%s" % (locale, name))
        report.append("  -> Data/%s/%s  (DBCs here outrank the client's own locale patches)"
                      % (locale, name))

    # Wow.exe -- only when installing the creation text, and only with the
    # verified pattern set. A running game locks it; that must not throw away
    # the archives already written, so a lock is reported, not fatal.
    exe_patched = False
    exe_locked = False
    if args.exe:
        if not exe:
            report.append("  Wow.exe          SKIPPED, not found")
        elif args.dry_run:
            state, _o, digest, label = exepatch.inspect(exe)
            report.append("  Wow.exe          %s (%s)"
                          % (state, label or "sha256 " + digest[:16]))
        else:
            try:
                report.append("  Wow.exe          %s" % exepatch.apply(exe))
                exe_patched = True
            except PermissionError:
                exe_locked = True
                report.append("  Wow.exe          COULD NOT WRITE -- close the "
                              "game and re-run")
            except (OSError, RuntimeError) as error:
                exe_locked = True
                report.append("  Wow.exe          NOT PATCHED -- %s" % error)

    addon_rel = None
    if args.addon:
        with clientfs.ClientFiles(data_dir, locales[0],
                                  exclude=own_archives(locales[0])) as files:
            addon_rel = install_addon(wow_dir, args.dry_run, report, files)

    clear_cache(wow_dir, args.dry_run, report)

    write_manifest(wow_dir, {
        "version": 1,
        "suffix": suffix,
        "locales": locales,
        "name": args.name,
        "exe_patched": exe_patched or bool((previous or {}).get("exe_patched")),
        "files": written,
        "addon": addon_rel,
        "creation_text": bool(args.glue),
    }, args.dry_run)

    print("\n".join(report))
    print()
    if args.dry_run:
        print("Dry run: nothing was written.")
        return 0

    if exe_locked:
        print("Almost done -- the game was open, so Wow.exe was not patched and")
        print("the creation-screen text will show as corrupt until it is. Close")
        print("World of Warcraft completely and run this installer again to finish.")
        print()

    print("Done. Start the game and every class will read %s." % args.name)
    if args.glue and not exe_locked:
        print("The creation screen now shows the Hero pitch. If it instead says")
        print("the interface is corrupt, re-run with --uninstall to revert.")
    print("To undo everything:  python install.py --uninstall \"%s\"" % wow_dir)
    return 0


# --------------------------------------------------------------- uninstall

# Every file the installer ever writes into a patch archive. An archive is ours
# only if EVERY file in it is one of these -- a client pack's own archive always
# has something else in it, so it can never be matched by luck of the letter.
_OUR_FILES = frozenset(x.lower() for x in (
    CHRCLASSES, CHARBASEINFO, CHARSTARTOUTFIT, SKILLRACECLASSINFO, SKILLLINEABILITY,
    GLUESTRINGS, CHARCREATE_LUA,
    CLASSICONS_INGAME, CLASSICONS_CREATE,
    elemental.SPELL, elemental.SPELLVISUAL, elemental.SPELLICON,
))
# the elemental step paints one icon per (base icon, element); the names are
# derived, so ownership of those is decided by prefix rather than by list
_OUR_ICON_PREFIX = (elemental.ICON_DIR + "cw_").lower()


def _is_ours(name: str) -> bool:
    return name in _OUR_FILES or (name.startswith(_OUR_ICON_PREFIX) and name.endswith(".blp"))


def _is_our_archive(path):
    """True only if every file in this MPQ is one the installer writes.

    Used by uninstall when there is no manifest. Reads the listfile and refuses
    to claim anything with an unexpected file in it, so a client pack's own
    patch archive can never be matched by luck of the patch letter.
    """
    try:
        archive = mpq.MPQArchive(path)
    except Exception:
        return False
    try:
        raw = archive.read_file("(listfile)")
    except Exception:
        return False
    finally:
        archive.close()
    names = {n.strip().lower().replace("/", "\\")
             for n in raw.decode("utf-8", "replace").replace("\r", "\n").split("\n")
             if n.strip() and n.strip().lower() != "(listfile)"}
    return bool(names) and all(_is_ours(n) for n in names)


def do_uninstall(args, wow_dir):
    manifest = read_manifest(wow_dir)
    report = []

    locked = []  # things a running game held onto

    if manifest:
        targets = manifest.get("files", [])
        addon_rel = manifest.get("addon")
    else:
        # No manifest: find our archives by CONTENT, never by filename. A patch
        # letter is not proof of ownership -- the client may ship its own
        # patch-enUS-T.MPQ and friends, and deleting those would break it. Ours
        # are the only archives whose listfile is exactly the files we write.
        targets = []
        data_dir = resolve_child(wow_dir, "Data")
        candidates = []
        for suffix in "ZYXWVUTSRQPONMLKJIHGFEDCBA0123456789":
            candidates.append("Data/patch-%s.MPQ" % suffix)
            for locale in clientfs.detect_locales(data_dir):
                candidates.append("Data/%s/patch-%s-%s.MPQ"
                                  % (locale, locale, suffix))
        for rel in candidates:
            path = os.path.join(wow_dir, rel.replace("/", os.sep))
            if os.path.isfile(path) and _is_our_archive(path):
                targets.append(rel)
        addon_rel = "Interface/AddOns/%s" % ADDON_NAME
        report.append("  no install manifest found; removing archives that "
                      "match our contents only")

    for rel in targets:
        path = os.path.join(wow_dir, rel.replace("/", os.sep))
        if os.path.isfile(path):
            if args.dry_run:
                report.append("  would remove %s" % rel)
                continue
            try:
                os.remove(path)
                report.append("  removed %s" % rel)
            except OSError:
                locked.append(rel)
                report.append("  LOCKED, not removed: %s" % rel)

    if addon_rel:
        path = os.path.join(wow_dir, addon_rel.replace("/", os.sep))
        if os.path.isdir(path):
            if args.dry_run:
                report.append("  would remove %s" % addon_rel)
            else:
                try:
                    shutil.rmtree(path)
                    report.append("  removed %s" % addon_rel)
                except OSError:
                    locked.append(addon_rel)
                    report.append("  LOCKED, not removed: %s" % addon_rel)

    # Current versions never touch Wow.exe, but an install from an older
    # version might have, so always offer to restore it -- restore() is a
    # no-op ("was not patched; left alone") when there is nothing to undo.
    exe = find_wow_exe(wow_dir)
    if exe:
        if args.dry_run:
            state, _o, _d, _l = exepatch.inspect(exe)
            if state != "unpatched":
                report.append("  Wow.exe is %s (would restore)" % state)
        else:
            try:
                result = exepatch.restore(exe)
                if "left alone" not in result:
                    report.append("  Wow.exe %s" % result)
            except OSError:
                locked.append("Wow.exe")
                report.append("  Wow.exe          LOCKED, not restored")

    clear_cache(wow_dir, args.dry_run, report)

    # keep the manifest if anything was locked, so a re-run after the game
    # closes knows what is still left to remove
    manifest_path = os.path.join(wow_dir, MANIFEST_NAME)
    if os.path.isfile(manifest_path) and not args.dry_run and not locked:
        os.remove(manifest_path)

    print("\n".join(report) if report else "  nothing to remove")
    print()
    if args.dry_run:
        print("Dry run: nothing was written.")
    elif locked:
        print("Some files were in use (the game is running). Close World of")
        print("Warcraft fully and run --uninstall again to finish.")
    else:
        print("Client restored to stock.")
    return 0


# -------------------------------------------------------------------- main

def ensure_pillow():
    """The install paints the Hero emblem and the elemental icons, so the
    Python 'Pillow' library is required. Install it on the spot when it is
    missing, and stop if that fails: a client without the icons is not the
    full install."""
    try:
        import PIL  # noqa: F401
        return
    except ImportError:
        pass
    cmd = [sys.executable, "-m", "pip", "install", "--user", "pillow"]
    print("The Python library 'Pillow' is needed to paint the Hero and elemental icons.")
    print("Installing it now:  " + " ".join(cmd))
    print()
    try:
        subprocess.run(cmd, check=True)
    except (OSError, subprocess.CalledProcessError):
        raise Abort("Pillow could not be installed automatically. Run this, then run the installer again:\n"
                    "  " + " ".join(cmd))
    import importlib
    importlib.invalidate_caches()
    try:
        import PIL  # noqa: F401
    except ImportError:
        raise Abort("Pillow was installed but this Python cannot import it. Run this, then try again:\n"
                    "  " + " ".join(cmd))
    print()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Install the mod-classless-wildcard client patch and addon.",
        epilog="With no folder given, common install locations are searched.")
    parser.add_argument("wow_folder", nargs="?",
                        help="the folder containing Wow.exe and Data")
    parser.add_argument("--uninstall", action="store_true",
                        help="remove everything this installer added")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would happen, write nothing")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="do not ask for confirmation")
    parser.add_argument("--locale", help="patch only this locale, e.g. enUS")
    parser.add_argument("--name", default="Hero",
                        help="what every class is called (default: Hero)")
    parser.add_argument("--no-addon", dest="addon", action="store_false",
                        help="do not install the in-game addon")
    # The full Hero client is the default. These turn single pieces OFF for
    # maintainers; a player's install is always the full one.
    parser.add_argument("--no-creation-text", dest="glue", action="store_false",
                        help="skip the Hero creation-screen text and armored "
                             "outfit (and the Wow.exe patch they need)")
    parser.add_argument("--no-elemental", dest="elemental", action="store_false",
                        help="leave out the elemental ability variants (spell rows and icons)")
    parser.add_argument("--no-hero-icon", dest="hero_icon", action="store_false",
                        help="keep the stock class icon instead of the Hero emblem")
    parser.add_argument("--no-exe", dest="exe_ok", action="store_false",
                        help="install the creation text but do NOT patch Wow.exe "
                             "(only for clients that already accept custom "
                             "interface files)")
    args = parser.parse_args(argv)
    # Wow.exe is patched only when installing the creation text, and only with
    # the verified community pattern set in lib/exepatch.py.
    args.exe = args.glue and args.exe_ok
    if not args.uninstall:
        ensure_pillow()

    print("mod-classless-wildcard client installer")
    print("=" * 39)
    print()

    wow_dir = args.wow_folder or autodetect_client()
    if wow_dir:
        wow_dir = os.path.abspath(wow_dir.strip().strip('"'))
    if not looks_like_client(wow_dir):
        typed = prompt_for_client()
        wow_dir = os.path.abspath(typed) if typed else None

    if not looks_like_client(wow_dir):
        raise Abort(
            "That is not a World of Warcraft folder.\n"
            "Give me the folder that contains Wow.exe and the Data folder, "
            "for example:\n"
            "    python install.py \"C:\\Games\\World of Warcraft\"")

    if args.uninstall:
        return do_uninstall(args, wow_dir)
    return do_install(args, wow_dir)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Abort as error:
        print("\n%s" % error, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\ncancelled", file=sys.stderr)
        sys.exit(130)
    except PermissionError as error:
        print("\nPermission denied: %s\n"
              "Close World of Warcraft if it is running. On Windows, if the "
              "client is under C:\\Program Files, run the installer as "
              "Administrator." % error, file=sys.stderr)
        sys.exit(1)
    except OSError as error:
        print("\nFile error: %s" % error, file=sys.stderr)
        sys.exit(1)
