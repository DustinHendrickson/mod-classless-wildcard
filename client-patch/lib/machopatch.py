"""The Hero changes to the Mac client's executable.

The Mac client is World of Warcraft.app, built from wowdecomp's macos-arm64
branch; a realm gives every player the same build, as every Windows player has
the same Wow.exe. lib/exepatch.py makes the Hero changes to Wow.exe 12340.
This makes the same changes to an arm64 build: the offsets and bytes for each
build live in mac_patch.json, written by gen_mac_patch.py from the build
itself, each group named after the exepatch site it mirrors (`twin`).

The rules are exepatch's. A build is patched only when every part of every
group holds its stock bytes, and is read as patched only when every part holds
its patched bytes; anything else is a build this file does not know, and is
left alone. Writing the bytes breaks the executable's code signature, which an
Apple Silicon Mac will not run, so lib/macapp.py signs the app again after.

Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import os

from . import macho

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(HERE, "mac_patch.json")

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
    manifest["about"] = ("The Hero changes to each Mac client build (World of Warcraft.app), "
                         "written by gen_mac_patch.py and applied by lib/machopatch.py. "
                         "Each part is [file offset, stock bytes, patched bytes].")
    manifest["builds"] = sorted(manifest["builds"], key=lambda build: build["uuid"])
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
    (None, None). The UUID picks the entry; the bytes decide."""
    manifest = manifest or load_manifest()
    try:
        uuid = macho.MachO(data).uuid
    except macho.MachOError:
        return None, None
    for build in manifest["builds"]:
        if build["uuid"] == uuid:
            state = _state(data, build)
            return (build, state) if state != "absent" else (None, None)
    return None, None


def inspect(exe):
    """(state, uuid, label) for an executable."""
    with open(exe, "rb") as handle:
        data = handle.read()
    try:
        uuid = macho.MachO(data).uuid
    except macho.MachOError:
        uuid = None
    build, state = identify(data)
    if not build:
        return UNKNOWN, uuid, None
    return (PATCHED if state == "done" else UNPATCHED), uuid, build["label"]


def patched_bytes(data, patched=True, manifest=None):
    """The executable's bytes with every group applied (or reverted). Raises
    RuntimeError for a build mac_patch.json does not hold."""
    build, state = identify(data, manifest)
    if not build:
        raise RuntimeError("this World of Warcraft.app is not a build the Hero patch knows "
                           "(build %s). Nothing was written." % (macho.MachO(data).uuid
                                                                if data[:4] else "?"))
    out = bytearray(data)
    for off, stock, new in _parts(build):
        value = new if patched else stock
        out[off:off + len(value)] = value
    return bytes(out), build


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def write_executable(exe, patched=True):
    """Patch (or revert) the executable in place. Returns (changed, label)."""
    with open(exe, "rb") as handle:
        data = handle.read()
    new, build = patched_bytes(data, patched)
    if new == data:
        return False, build["label"]
    with open(exe, "wb") as handle:
        handle.write(new)
    return True, build["label"]
