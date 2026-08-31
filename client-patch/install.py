#!/usr/bin/env python3
"""One-step client setup for mod-classless-wildcard.

Point this at a World of Warcraft 3.3.5a folder and it does everything the
client side needs:

  * builds the data patch from the player's OWN client files and drops it in
    Data/ (every class shows as Hero, every race/class pair selectable)
  * builds the matching locale patch with the classless creation-screen copy
  * lets Wow.exe accept that custom creation screen, backing the exe up first
  * installs the ClasslessWildcard addon
  * clears the client Cache so the new data is picked up

Everything is reversible with --uninstall.

Requires nothing but Python 3.7+. No compiler, no StormLib, no other packages.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from lib import clientfs, dbc, exepatch, gluestrings, mpq  # noqa: E402

MANIFEST_NAME = "ClasslessWildcard-install.json"
ADDON_NAME = "ClasslessWildcard"

CHRCLASSES = "DBFilesClient\\ChrClasses.dbc"
CHARBASEINFO = "DBFilesClient\\CharBaseInfo.dbc"
GLUESTRINGS = "Interface\\GlueXML\\GlueStrings.lua"

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

def build_data_patch(files, name, all_combos, report):
    """Assemble the base patch archive contents from the client's own DBCs."""
    payload = {}

    raw, source = files.find(CHRCLASSES)
    patched, renamed = dbc.rename_all_classes(raw, name)
    payload[CHRCLASSES] = patched
    report.append("  ChrClasses.dbc   %d classes renamed to %s (from %s)"
                  % (len(renamed), name, os.path.basename(source)))

    if all_combos:
        raw, source = files.find(CHARBASEINFO)
        patched, added, total = dbc.all_race_class_combos(raw)
        payload[CHARBASEINFO] = patched
        report.append("  CharBaseInfo.dbc %d race/class combos (%d new, from %s)"
                      % (total, added, os.path.basename(source)))

    return payload


def build_locale_patch(files, name, report, locale):
    """Assemble the locale patch archive contents for one locale."""
    raw, source = files.find(GLUESTRINGS)
    text = raw.decode("utf-8", "surrogateescape")
    new_text, replaced = gluestrings.rewrite(text, name)
    if not replaced:
        raise Abort(
            "Found GlueStrings.lua for %s but none of the class description "
            "keys matched, so the creation screen would be unchanged.\n"
            "This locale names its strings differently and needs a look. "
            "Re-run with --no-glue to install everything else." % locale)
    report.append("  GlueStrings.lua  %d class strings rewritten (from %s)"
                  % (len(replaced), os.path.basename(source)))
    return {GLUESTRINGS: new_text.encode("utf-8", "surrogateescape")}


# ----------------------------------------------------------------- actions

def install_addon(wow_dir, dry_run, report):
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

    print("World of Warcraft : %s" % wow_dir)
    print("Locales           : %s" % ", ".join(locales))
    print("Patch archives    : patch-%s.MPQ  (+ patch-<locale>-%s.MPQ)"
          % (suffix, suffix))
    print("Class name        : %s" % args.name)
    if previous:
        print("Note              : replacing a previous install (same letter)")
    print()

    if not args.yes and not args.dry_run:
        if sys.stdin and sys.stdin.isatty():
            answer = input("Install to this client? [Y/n] ").strip().lower()
            if answer and not answer.startswith("y"):
                raise Abort("cancelled; nothing was changed")
        print()

    report = []
    written = []

    # base patch: built once, from the highest-priority locale's chain
    with clientfs.ClientFiles(data_dir, locales[0]) as files:
        payload = build_data_patch(files, args.name, args.all_combos, report)
    target = os.path.join(data_dir, "patch-%s.MPQ" % suffix)
    if not args.dry_run:
        mpq.write_archive(target, payload)
    written.append("Data/patch-%s.MPQ" % suffix)
    report.append("  -> Data/patch-%s.MPQ" % suffix)

    # locale patches: the creation-screen copy, per locale
    if args.glue:
        for locale in locales:
            with clientfs.ClientFiles(data_dir, locale) as files:
                payload = build_locale_patch(files, args.name, report, locale)
            name = "patch-%s-%s.MPQ" % (locale, suffix)
            target = os.path.join(data_dir, locale, name)
            if not args.dry_run:
                mpq.write_archive(target, payload)
            written.append("Data/%s/%s" % (locale, name))
            report.append("  -> Data/%s/%s" % (locale, name))

    # exe
    exe_patched = False
    if args.exe and args.glue:
        if not exe:
            report.append("  Wow.exe          SKIPPED, not found")
        elif args.dry_run:
            state, _offset, digest, label = exepatch.inspect(exe)
            report.append("  Wow.exe          %s (%s)"
                          % (state, label or "sha256 " + digest[:16]))
        else:
            report.append("  Wow.exe          %s" % exepatch.apply(exe))
            exe_patched = True

    addon_rel = None
    if args.addon:
        addon_rel = install_addon(wow_dir, args.dry_run, report)

    clear_cache(wow_dir, args.dry_run, report)

    write_manifest(wow_dir, {
        "version": 1,
        "suffix": suffix,
        "locales": locales,
        "name": args.name,
        "files": written,
        "addon": addon_rel,
        "exe_patched": exe_patched or bool((previous or {}).get("exe_patched")),
    }, args.dry_run)

    print("\n".join(report))
    print()
    if args.dry_run:
        print("Dry run: nothing was written.")
        return 0

    print("Done. Start the game and every class will read %s." % args.name)
    print("To undo everything:  python install.py --uninstall \"%s\"" % wow_dir)
    return 0


# --------------------------------------------------------------- uninstall

def do_uninstall(args, wow_dir):
    manifest = read_manifest(wow_dir)
    report = []

    if manifest:
        targets = manifest.get("files", [])
        addon_rel = manifest.get("addon")
    else:
        # no manifest: fall back to the names this installer would have used
        targets = []
        data_dir = resolve_child(wow_dir, "Data")
        for suffix in "ZYXWVUTSRQPONMLKJIHGFEDCBA":
            candidate = "Data/patch-%s.MPQ" % suffix
            if os.path.isfile(os.path.join(wow_dir, candidate)):
                targets.append(candidate)
        addon_rel = "Interface/AddOns/%s" % ADDON_NAME
        report.append("  no install manifest found; removing by name only")

    for rel in targets:
        path = os.path.join(wow_dir, rel.replace("/", os.sep))
        if os.path.isfile(path):
            if not args.dry_run:
                os.remove(path)
            report.append("  removed %s" % rel)

    if addon_rel:
        path = os.path.join(wow_dir, addon_rel.replace("/", os.sep))
        if os.path.isdir(path):
            if not args.dry_run:
                shutil.rmtree(path)
            report.append("  removed %s" % addon_rel)

    exe = find_wow_exe(wow_dir)
    if exe and args.exe:
        if args.dry_run:
            state, _o, _d, _l = exepatch.inspect(exe)
            report.append("  Wow.exe is %s" % state)
        else:
            report.append("  Wow.exe %s" % exepatch.restore(exe))

    clear_cache(wow_dir, args.dry_run, report)

    manifest_path = os.path.join(wow_dir, MANIFEST_NAME)
    if os.path.isfile(manifest_path) and not args.dry_run:
        os.remove(manifest_path)

    print("\n".join(report) if report else "  nothing to remove")
    print()
    print("Dry run: nothing was written." if args.dry_run
          else "Client restored to stock.")
    return 0


# -------------------------------------------------------------------- main

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
    parser.add_argument("--no-all-combos", dest="all_combos",
                        action="store_false",
                        help="do not unlock every race/class pair on the "
                             "creation screen (use this if your realm did not "
                             "apply cw_all_race_class.sql)")
    parser.add_argument("--no-glue", dest="glue", action="store_false",
                        help="skip the creation-screen text and the exe patch")
    parser.add_argument("--no-exe", dest="exe", action="store_false",
                        help="do not touch Wow.exe")
    parser.add_argument("--no-addon", dest="addon", action="store_false",
                        help="do not install the in-game addon")
    args = parser.parse_args(argv)

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
