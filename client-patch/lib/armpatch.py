"""The Hero changes to the arm64 clients: the Mac app and the Switch NRO.

wowdecomp's Mac build (World of Warcraft.app) and Switch build (WoW.nro) are
arm64 programs, and a realm gives every player the same file, as every Windows
player has the same Wow.exe. lib/exepatch.py makes the Hero changes to Wow.exe
12340; this makes them to an arm64 build. The offsets and bytes for each build
live in arm64_patch.json, written by gen_arm64_patch.py from the build itself,
keyed by the build's own id (a Mach-O UUID, an NRO build id) and grouped by the
exepatch site each group mirrors (`twin`). A group can hold no parts when the
build already has the change (the Switch build loads unsigned interface files).

The rules are exepatch's. A build is patched only when every part of every
group holds its stock bytes, and is read as patched only when every part holds
its patched bytes; anything else is a build this file does not know, and is
left alone. A patched Mac app must be signed again (lib/macapp.py); an NRO is
homebrew and is not signed, so patch_file() is all it needs.

Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil

from . import macho, nro

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(HERE, "arm64_patch.json")

UNPATCHED = "unpatched"
PATCHED = "patched"
UNKNOWN = "unknown"


def load_manifest(path=MANIFEST):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {"builds": []}


def save_manifest(manifest, path=MANIFEST):
    manifest = dict(manifest)
    manifest["about"] = ("The Hero changes to each arm64 client build (the Mac app, the Switch "
                         "NRO), written by gen_arm64_patch.py and applied by lib/armpatch.py. "
                         "Each part is [file offset, stock bytes, patched bytes].")
    manifest["builds"] = sorted(manifest["builds"], key=lambda build: (build["platform"], build["key"]))
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=1, sort_keys=True)
        handle.write("\n")


def app_executable(app):
    """The executable inside an app bundle, by its Info.plist."""
    import plistlib
    name = None
    try:
        with open(os.path.join(app, "Contents", "Info.plist"), "rb") as handle:
            name = plistlib.load(handle).get("CFBundleExecutable")
    except (OSError, ValueError, plistlib.InvalidFileException):
        pass
    return os.path.join(app, "Contents", "MacOS", name or "World of Warcraft")


def build_key(data):
    """The id a build is looked up by: a Mach-O UUID or an NRO build id."""
    if nro.is_nro(data):
        return nro.Nro(data).build_id
    try:
        return macho.MachO(data).uuid
    except macho.MachOError:
        return None


def _parts(build):
    for group in build["groups"]:
        for off, stock, patched in group["parts"]:
            yield off, bytes.fromhex(stock), bytes.fromhex(patched)


def _state(data, build):
    """'apply' when every part is stock, 'done' when every part is patched,
    otherwise 'absent'."""
    states = set()
    for off, stock, patched in _parts(build):
        here = bytes(data[off:off + len(stock)])
        states.add("apply" if here == stock else "done" if here == patched else "absent")
    return states.pop() if len(states) == 1 and "absent" not in states else "absent"


def identify(data, manifest=None):
    """(build entry, 'apply' or 'done') for the build these bytes are, or
    (None, None). The id picks the entry; the bytes decide."""
    manifest = manifest or load_manifest()
    key = build_key(data)
    for build in manifest["builds"]:
        if key and build["key"] == key:
            state = _state(data, build)
            return (build, state) if state != "absent" else (None, None)
    return None, None


def inspect(path):
    """(state, key, label) for a program file."""
    with open(path, "rb") as handle:
        data = handle.read()
    build, state = identify(data)
    if not build:
        return UNKNOWN, build_key(data), None
    return (PATCHED if state == "done" else UNPATCHED), build["key"], build["label"]


def patched_bytes(data, patched=True, manifest=None):
    """The program's bytes with every group applied (or reverted). Raises
    RuntimeError for a build arm64_patch.json does not hold."""
    build, _state_now = identify(data, manifest)
    if not build:
        raise RuntimeError("this program is not a build the Hero patch knows (build %s). "
                           "Nothing was written." % (build_key(data) or "unreadable"))
    out = bytearray(data)
    for off, stock, new in _parts(build):
        value = new if patched else stock
        out[off:off + len(value)] = value
    return bytes(out), build


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def write_executable(path, patched=True):
    """Patch (or revert) a program file in place. Returns (changed, label)."""
    with open(path, "rb") as handle:
        data = handle.read()
    new, build = patched_bytes(data, patched)
    if new == data:
        return False, build["label"]
    with open(path, "wb") as handle:
        handle.write(new)
    return True, build["label"]


# ------------------------------------------------- a program with no signing

def backup_path(path):
    return path + ".classless-bak"


def patch_file(path):
    """Patch a program that needs no signing (WoW.nro), keeping the stock
    file beside it first. Returns a summary line; raises RuntimeError with the
    file left as it was."""
    state, key, label = inspect(path)
    if state == PATCHED:
        return "already has the Hero changes (%s)" % label
    if state == UNKNOWN:
        raise RuntimeError("this is not a build the Hero patch knows (build %s), so it was not "
                           "touched" % (key or "unreadable"))
    backup = backup_path(path)
    kept = not os.path.exists(backup)
    if kept:
        shutil.copy2(path, backup)
    write_executable(path, patched=True)
    return "Hero changes written (%s)%s" % (
        label, "; the stock file is kept as %s" % os.path.basename(backup) if kept else "")


def has_file_changes(path) -> bool:
    return os.path.isfile(backup_path(path)) or inspect(path)[0] == PATCHED


def restore_file(path):
    """Put the stock program back: the copy kept on install, or the bytes
    reverted in place. Returns a summary line."""
    backup = backup_path(path)
    if os.path.isfile(backup):
        shutil.copy2(backup, path)
        os.remove(backup)
        return "restored from %s" % os.path.basename(backup)
    if inspect(path)[0] != PATCHED:
        return "has no Hero changes; left alone"
    write_executable(path, patched=False)
    return "Hero changes taken out in place (no stock copy was kept)"
