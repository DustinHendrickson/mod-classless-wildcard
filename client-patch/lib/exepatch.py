"""Let a 3.3.5a Wow.exe load custom (unsigned) GlueXML / FrameXML.

Replacing an interface file the client signs -- GlueStrings.lua, for the Hero
creation-screen text -- makes the client reject the whole set with "Your login
interface files are corrupt". The fix is the well-known "allow custom interface"
binary patch: it forces the interface signature-scope check to always report the
accepted scope, so modified UI files load.

The byte patterns below are the ones used by the Project Reforged 3.3.5 patcher
(https://github.com/Stormhand-dev/WoW-3.3.5-Patcher---Project-Reforged), which
is in use on a live server. They are applied here only after verifying each one
matches the target exe EXACTLY ONCE, so a client this set does not fit is
refused rather than corrupted. A backup is always written first, and restore()
puts the original back.

Each replacement is the same length as what it replaces (in-place byte edits:
je/jz/jg -> jmp, and `mov eax,1` -> `mov eax,3`), so offsets never move.
"""

from __future__ import annotations

import hashlib
import os
import shutil

# The stock 3.3.5a build 12340 client (for labelling only; patching does not
# depend on it -- the pattern match is the real gate).
KNOWN_SHA256 = {
    "aa63a5750d60ef16746c686b3d5e26876d98953eab08b1c026cd0faf78e88cb8":
        "3.3.5a build 12340 (Wow.exe)",
}

# (search, replace). `core` patterns must each be present exactly once (or
# already applied) or the exe is refused. Non-core patterns are applied when
# present and skipped when absent -- they cover client revisions this one is not.
_PATCHES = [
    # signature-scope validation: branches -> always take the accept path,
    # and both "return 1" (reject) sites -> "return 3" (accept).
    ("04 85 C0 74 39 56",                "04 85 C0 EB 39 56",                True),
    ("C0 FF 85 C0 75 05 5E 8B",          "C0 FF 85 C0 EB 05 5E 8B",          True),
    ("B6 C0 FF B8 01 00 00 00",          "B6 C0 FF B8 03 00 00 00",          True),
    ("C0 FF 5F B8 01 00 00 00",          "C0 FF 5F B8 03 00 00 00",          True),
    ("B8 01 00 00 00 7F 12 83 C8 FF F7", "B8 01 00 00 00 EB 12 83 C8 FF F7", True),
    ("C0 5F 83 C0 03 5E 8B E5 5D C3 CC", "C0 5F B8 03 00 00 00 EB ED C3 CC", True),
    # present only on some client revisions; absent on stock 12340.
    ("00 A1 26",                         "00 16 4E",                         False),
]

UNPATCHED = "unpatched"
PATCHED = "patched"
UNKNOWN = "unknown"


def _bytes(hex_str):
    return bytes.fromhex(hex_str.replace(" ", ""))


def _count(data, needle):
    n = 0
    start = 0
    while True:
        i = data.find(needle, start)
        if i < 0:
            return n
        n += 1
        start = i + 1


def sha256(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_path(exe) -> str:
    return str(exe) + ".classless-bak"


def _classify(data):
    """Per-pattern state: 'apply' (1 source match), 'done' (already replaced),
    'absent' (neither), or 'ambiguous' (2+ source matches)."""
    result = []
    for search, replace, core in _PATCHES:
        sb, rb = _bytes(search), _bytes(replace)
        src = _count(data, sb)
        if src == 1:
            result.append(("apply", sb, rb, core))
        elif src == 0 and _count(data, rb) >= 1:
            result.append(("done", sb, rb, core))
        elif src == 0:
            result.append(("absent", sb, rb, core))
        else:
            result.append(("ambiguous", sb, rb, core))
    return result


def inspect(exe):
    """Return (state, None, sha256, label). state is one of the module consts."""
    with open(exe, "rb") as handle:
        data = handle.read()
    digest = hashlib.sha256(data).hexdigest()
    label = KNOWN_SHA256.get(digest)

    states = _classify(data)
    core = [s for s in states if s[3]]
    if any(st == "ambiguous" for st, *_ in core):
        return UNKNOWN, None, digest, label
    if core and all(st == "done" for st, *_ in core):
        return PATCHED, None, digest, label
    if core and all(st in ("apply", "done") for st, *_ in core):
        # at least one core still needs applying -> treat as unpatched/ready
        if any(st == "apply" for st, *_ in core):
            return UNPATCHED, None, digest, label
        return PATCHED, None, digest, label
    return UNKNOWN, None, digest, label


def apply(exe):
    """Apply the interface-signature bypass. Returns a summary line."""
    with open(exe, "rb") as handle:
        data = bytearray(handle.read())
    digest = hashlib.sha256(bytes(data)).hexdigest()

    states = _classify(data)

    # refuse a client the core set does not cleanly fit
    for (st, sb, rb, core) in states:
        if core and st == "ambiguous":
            raise RuntimeError(
                "the interface-signature check appears more than once in this "
                "Wow.exe, so it was not touched. This binary is not one the "
                "known patch fits; nothing was written.")
    core_states = [st for (st, sb, rb, core) in states if core]
    if not core_states or any(st == "absent" for st in core_states):
        raise RuntimeError(
            "could not find the interface-signature check in this Wow.exe "
            "(sha256 %s). It is not the client this patch knows, so nothing was "
            "written. If your client already loads custom interface files, you "
            "do not need this." % digest[:16])

    if all(st == "done" for st in core_states):
        return "already accepts custom interface files; left alone"

    backup = backup_path(exe)
    if not os.path.exists(backup):
        shutil.copy2(exe, backup)

    applied = 0
    for (st, sb, rb, core) in states:
        if st == "apply":
            i = data.find(sb)
            data[i:i + len(sb)] = rb
            applied += 1

    with open(exe, "wb") as handle:
        handle.write(bytes(data))

    note = "" if KNOWN_SHA256.get(digest) else \
        " (unrecognised build, but the patch sites matched exactly)"
    return "patched %d site(s) to accept custom interface files%s (backup: %s)" \
        % (applied, note, os.path.basename(backup))


def restore(exe):
    """Put the original exe back. Returns a summary line."""
    backup = backup_path(exe)
    if os.path.isfile(backup):
        shutil.copy2(backup, exe)
        os.remove(backup)
        return "restored from %s" % os.path.basename(backup)

    # no backup: reverse the byte edits in place if they are present
    with open(exe, "rb") as handle:
        data = bytearray(handle.read())
    reverted = 0
    for search, replace, _core in _PATCHES:
        sb, rb = _bytes(search), _bytes(replace)
        # only reverse when the patched form is uniquely present and the
        # original is not, to avoid touching an unrelated match
        if _count(data, rb) == 1 and _count(data, sb) == 0 and sb != rb:
            i = data.find(rb)
            data[i:i + len(rb)] = sb
            reverted += 1
    if not reverted:
        return "was not patched; left alone"
    with open(exe, "wb") as handle:
        handle.write(bytes(data))
    return "reverted %d patch site(s) in place (no backup was present)" % reverted
