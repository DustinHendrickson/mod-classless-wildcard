#!/usr/bin/env python3
"""One-step client setup for mod-classless-wildcard.

Point this at a World of Warcraft 3.3.5a folder and it does everything the
client side needs:

  * builds a data patch from the player's OWN client files and drops it in
    Data/ (every class shows as Hero; the creation screen lists one class)
  * installs the ClasslessWildcard addon
  * clears the client Cache so the new data is picked up

Wow.exe is NEVER modified. The optional --creation-text flag also rewrites the
creation-screen class blurb, but that touches a signed interface file and only
works on clients that do not enforce GlueXML signatures, so it is off by
default.

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

# The one class the creation screen offers. Purely cosmetic: the server
# converts every new character to its configured chassis no matter what the
# client sends. Warrior is used as the shell because vanilla already allows it
# for 9 of the 10 races (the installer's SQL side adds the one gap), and it is
# renamed "Hero" like everything else.
SHELL_CLASS = 1


def build_data_patch(files, name, report):
    """Assemble the base patch archive contents from the client's own DBCs."""
    payload = {}

    raw, source = files.find(CHRCLASSES)
    patched, renamed = dbc.rename_all_classes(raw, name)
    payload[CHRCLASSES] = patched
    report.append("  ChrClasses.dbc   %d classes renamed to %s (from %s)"
                  % (len(renamed), name, os.path.basename(source)))

    raw, source = files.find(CHARBASEINFO)
    patched, races = dbc.single_class_combos(raw, SHELL_CLASS)
    payload[CHARBASEINFO] = patched
    report.append("  CharBaseInfo.dbc all %d races, one cosmetic class "
                  "(shown as %s)" % (races, name))

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
            "Drop --creation-text to install everything else." % locale)
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
    if args.glue:
        print("Patch archives    : patch-%s.MPQ  +  patch-<locale>-%s.MPQ"
              % (suffix, suffix))
    else:
        print("Patch archive     : patch-%s.MPQ" % suffix)
    print("Class name        : %s" % args.name)
    print("Creation text     : %s"
          % ("YES -- replaces a signed file (see warning below)"
             if args.glue else "no (safe default; class description unchanged)"))
    if previous:
        print("Note              : replacing a previous install (same letter)")
    print()

    if args.glue:
        print("  --creation-text rewrites GlueStrings.lua (the creation-screen")
        print("  class description), which is a signed interface file. To make the")
        if args.exe:
            print("  client accept it, it also applies the well-known \"allow custom")
            print("  interface\" patch to Wow.exe -- backed up first to")
            print("  Wow.exe.classless-bak, and reversible with --uninstall.")
        else:
            print("  client accept it you asked to skip the Wow.exe patch (--no-exe),")
            print("  so this only works if your client already loads custom UI files.")
        print('  If the login screen still says "interface files are corrupt", run')
        print("  this installer again with --uninstall. The Hero name and single-")
        print("  class list do NOT need any of this and install either way.")
        print()

    if not args.yes and not args.dry_run:
        if sys.stdin and sys.stdin.isatty():
            prompt = ("Install the creation text too? [y/N] " if args.glue
                      else "Install to this client? [Y/n] ")
            answer = input(prompt).strip().lower()
            if args.glue:
                if not answer.startswith("y"):
                    raise Abort("cancelled; nothing was changed")
            elif answer and not answer.startswith("y"):
                raise Abort("cancelled; nothing was changed")
        print()

    report = []
    written = []

    # base patch: built once, from the highest-priority locale's chain
    with clientfs.ClientFiles(data_dir, locales[0]) as files:
        payload = build_data_patch(files, args.name, report)
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
        addon_rel = install_addon(wow_dir, args.dry_run, report)

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

# The exact file sets our two archives ever contain. An archive whose listfile
# is one of these (plus the "(listfile)" entry itself) is ours; anything else,
# including a client pack's own patch archive, is left alone.
_OUR_ARCHIVE_CONTENTS = (
    frozenset({CHRCLASSES.lower(), CHARBASEINFO.lower()}),  # base patch
    frozenset({CHRCLASSES.lower()}),                        # base, --no-...
    frozenset({GLUESTRINGS.lower()}),                       # locale patch
)


def _is_our_archive(path):
    """True only if this MPQ's contents are exactly one of ours.

    Used by uninstall when there is no manifest. Reads the listfile and refuses
    to claim anything that has an unexpected file in it, so a client pack's own
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
    return names in _OUR_ARCHIVE_CONTENTS


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
    parser.add_argument("--creation-text", dest="glue", action="store_true",
                        help="ALSO replace the creation-screen class description "
                             "with the Hero pitch. This edits a signed interface "
                             "file, so it also applies the well-known 'allow "
                             "custom interface' patch to Wow.exe (backed up "
                             "first) so the client accepts it. OFF by default; "
                             "fully reversible with --uninstall.")
    parser.add_argument("--no-exe", dest="exe_ok", action="store_false",
                        help="with --creation-text, install the text but do NOT "
                             "patch Wow.exe (only for clients that already accept "
                             "custom interface files)")
    args = parser.parse_args(argv)
    # Wow.exe is patched only when installing the creation text, and only with
    # the verified community pattern set in lib/exepatch.py.
    args.exe = args.glue and args.exe_ok

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
