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

One more site rides along: the Death Knight eye glow. 0x4ed900 in build 12340
draws it for class 6, or when the character's face row in CharSections.dbc
carries 0x4 (Death Knight only). The client patch turns that bit into 0x10 so
every class can pick those faces (lib/dbc.py, open_death_knight_appearance),
which would leave a Hero wearing one with ordinary eyes. The test byte becomes
0x14, so either bit lights the eyes. No stock face row has 0x10, so this draws
exactly the faces it drew before.
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

# Death Knight eye glow, Wow.exe 12340 at 0x4ed93b: the face row lookup
# returned non-null, then the Death Knight-only flag test, then the jump past
# "glow = 1". Only the flag byte changes.
GLOW_SEARCH = "85 C0 74 0A F6 40 1C 04 74 04 C6 45 FF 01"
GLOW_REPLACE = "85 C0 74 0A F6 40 1C 14 74 04 C6 45 FF 01"

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
    # eye glow: `test byte ptr [eax+0x1c], 4` -> `..., 0x14` on the face row.
    (GLOW_SEARCH,                        GLOW_REPLACE,                       False),
]

# Death Knight skins from any face (with lib/dbc.py's filled-in faces).
# Blizzard drew the three Death Knight skins for three faces per race and sex,
# and the skin arrows only offer a colour the current face has a row for. The
# client patch gives every face a row at those colours (ids from
# CHARSECTIONS_FILL_FIRST_ID, copies of the nearest drawn face), so the skin
# arrows reach them from any face and never change which face is picked.
#
# The Face arrows (next 0x4eb710, prev 0x4eb990) must behave exactly as stock
# with those copies present, which takes two things:
#
# 1. Their colour count. For each face they ask 0x4f3b10 how many colours the
#    face has and try colour (counter + last chosen skin) % count, storing the
#    result back into the counter (a Blizzard quirk that adds the offset
#    twice). The copies raise an undrawn face's count from 10 to 15, which
#    changes every colour that formula picks and can skip a face outright. A
#    replacement for 0x4f3b10 at those two calls (C) returns the same count but
#    drops trailing copies and empty slots, so each face gets its stock count
#    and the copies, all at the top, are never tried.
#
#       C: slot = table + ((sex + race*2)*5 + section)*8
#          eax = 0; if var >= [slot] return
#          entry = [slot+4] + var*8; eax = [entry]; list = [entry+4]
#          if !list return 0
#          while eax > 0: row = list[eax-1]
#                         if row && [row] < 30000 return eax
#                         eax--
#
# 2. "Does the face it found also fit the skin on screen", which reads that
#    one face row directly (`mov ecx,[ebp-8]; mov edx,[ebx+0x1c]`, then the
#    gate 0x4f39a0). A call to B loads the same two registers and zeroes the
#    flags when the row is a copy, so the gate refuses it and the arrow moves to
#    a skin the face was drawn for, as stock does.
#
#       B: mov ecx,[ebp-8] / mov edx,[ebx+0x1c] / cmp dword [ebx],30000 /
#          jb +2 / xor edx,edx / ret
#
# C (76 bytes) sits in .text's file slack, the 77 zero bytes between the last
# instruction (VA 0x9de3b3) and the end of the section's raw data, and .text's
# VirtualSize is raised to its raw size so the loader maps it. B (17 bytes)
# sits in the int3 padding between a `ret` at 0x9296a1 and the function at
# 0x9296c0, which nothing jumps into. The calls are relative, so every part is
# checked at its build 12340 file offset and the eight are applied, detected
# and reverted together or not at all.
FILL_FIRST_ID = 30000      # must equal dbc.CHARSECTIONS_FILL_FIRST_ID
_TEXT_TAIL = "6A 00 6A FE 68 50 EB B2 00 50 E8 EE 01 D9 FF C3"
_TEXT_HEADER = (0x208, "2E 74 65 78 74 00 00 00 B3 D3 5D 00",
                       "2E 74 65 78 74 00 00 00 00 D4 5D 00")
_FACE_COUNT = ("8B 44 24 0C 8B 4C 24 08 8D 04 48 8D 04 80 03 44 24 10 8B 4C 24 04 "
               "8D 0C C1 8B 54 24 14 31 C0 3B 11 73 28 8B 49 04 8D 0C D1 8B 01 8B "
               "49 04 85 C9 74 17 85 C0 7E 15 8B 54 81 FC 85 D2 74 08 81 3A 30 75 "
               "00 00 72 05 48 EB E9 31 C0 C3")
_FACE_FITS = "8B 4D F8 8B 53 1C 81 3B 30 75 00 00 72 02 31 D2 C3"
FACE_ARROW = [
    # (file offset, stock bytes, patched bytes)
    _TEXT_HEADER,
    (0x5DD7A3, _TEXT_TAIL + " 00" * 77,
               _TEXT_TAIL + " " + _FACE_COUNT + " 00"),
    (0x528AA2, "CC" + " CC" * 29,
               "CC CC " + _FACE_FITS + " CC" * 11),
    # Face next / prev: the colour count for a face -> C
    (0xEAB81, "E8 8A 83 00 00 8B C8 83 C4 14 33 FF 85 C9 89 4D F4 0F 8E D0",
              "E8 2D 2C 4F 00 8B C8 83 C4 14 33 FF 85 C9 89 4D F4 0F 8E D0"),
    (0xEAE01, "E8 0A 81 00 00 8B C8 83 C4 14 33 FF 85 C9 89 4D F4 0F 8E D0",
              "E8 AD 29 4F 00 8B C8 83 C4 14 33 FF 85 C9 89 4D F4 0F 8E D0"),
    # Face next / prev: "does it fit the skin on screen" -> B
    (0xEACFB, "8B 4D F8 8B 53 1C 51 52 E8 98 80 00 00 83 C4 08 84 C0 74 53",
              "E8 A4 DD 43 00 90 51 52 E8 98 80 00 00 83 C4 08 84 C0 74 53"),
    (0xEAF79, "8B 4D F8 8B 53 1C 51 52 E8 1A 7E 00 00 83 C4 08 84 C0 74 53",
              "E8 26 DB 43 00 90 51 52 E8 1A 7E 00 00 83 C4 08 84 C0 74 53"),
]

# Shipped briefly (b685c7a) and replaced: the skin arrows switched to a drawn
# face when the current one had no art, and never switched back. Kept so an
# exe that has it is put back to stock before FACE_ARROW goes on.
_LEGACY_SKIN_FACE_CAVE = (
    "8B 45 F8 85 C0 75 42 53 6A 3F 5B 6A 00 57 53 6A 01 FF 76 1C FF 76 18 "
    "FF 35 64 B8 B6 00 E8 CB 57 B1 FF 89 45 F8 85 C0 74 0D FF 75 FC FF 70 1C "
    "E8 B9 55 B1 FF 84 C0 8D 65 DC 75 07 4B 79 CD 31 C0 5B C3 89 5E 2C 8B 45 "
    "F8 5B 85 C0 C3")
_LEGACY_ARROW = "74 35 8B 55 FC 8B 40 1C 52 50 E8 %s 00 00 83 C4 08 84 C0 74 21 83 7D 08 02 74 %s"
LEGACY_SKIN_FACE = [
    _TEXT_HEADER,
    (0x5DD7A3, _TEXT_TAIL + " 00" * 77,
               _TEXT_TAIL + " " + _LEGACY_SKIN_FACE_CAVE + " 00"),
    (0xEA61A, "8B 45 F8 85 C0 " + _LEGACY_ARROW % ("72 87", "39"),
              "E8 94 31 4F 00 " + _LEGACY_ARROW % ("72 87", "39")),
    (0xEA75B, "8B 45 F8 85 C0 " + _LEGACY_ARROW % ("31 86", "3A"),
              "E8 53 30 4F 00 " + _LEGACY_ARROW % ("31 86", "3A")),
]


def _group_state(data, group):
    """'apply' when every part is stock at its offset, 'done' when every part
    is patched, otherwise 'absent' (another build, or a mix): left alone."""
    states = set()
    for offset, search, replace in group:
        sb, rb = _bytes(search), _bytes(replace)
        here = bytes(data[offset:offset + len(sb)])
        states.add("apply" if here == sb else "done" if here == rb else "absent")
    return states.pop() if len(states) == 1 and "absent" not in states else "absent"


def _group_write(data, group, patched):
    for offset, search, replace in group:
        new = _bytes(replace if patched else search)
        data[offset:offset + len(new)] = new


def _face_arrow_state(data):
    """FACE_ARROW's state, reading an exe that still has the legacy skin-arrow
    routine as one it can be applied to (apply() takes that out first)."""
    if _group_state(data, LEGACY_SKIN_FACE) == "done":
        return "apply"
    return _group_state(data, FACE_ARROW)


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
    if core and all(st in ("apply", "done") for st, *_ in core):
        # any site still waiting, core or not (a client patched before the eye
        # glow site existed), means apply() has work to do
        if any(st == "apply" for st, *_ in states) \
                or _face_arrow_state(data) == "apply":
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

    glow = _bytes(GLOW_SEARCH)
    glow_state = next(st for (st, sb, rb, core) in states if sb == glow)
    glow_note = {"apply": "; Death Knight eye glow follows the face",
                 "done": "; Death Knight eye glow already follows the face",
                 }.get(glow_state, "; eye glow site not found, left alone")

    skin_state = _face_arrow_state(data)
    glow_note += {"apply": "; Death Knight skins reachable from any face",
                  "done": "; Death Knight skins already reachable from any face",
                  }.get(skin_state, "; face arrow sites not found, left alone")

    if not any(st == "apply" for (st, sb, rb, core) in states) \
            and skin_state != "apply":
        return "already accepts custom interface files%s; left alone" % glow_note

    backup = backup_path(exe)
    if not os.path.exists(backup):
        shutil.copy2(exe, backup)

    applied = 0
    for (st, sb, rb, core) in states:
        if st == "apply" and sb != glow:
            i = data.find(sb)
            data[i:i + len(sb)] = rb
            applied += 1
    if glow_state == "apply":
        i = data.find(glow)
        data[i:i + len(glow)] = _bytes(GLOW_REPLACE)
    if skin_state == "apply":
        if _group_state(data, LEGACY_SKIN_FACE) == "done":
            _group_write(data, LEGACY_SKIN_FACE, patched=False)
        _group_write(data, FACE_ARROW, patched=True)

    with open(exe, "wb") as handle:
        handle.write(bytes(data))

    # a client an earlier install already patched has a hash of its own, so
    # only call the build unrecognised when the interface sites were found here
    note = "" if KNOWN_SHA256.get(digest) or not applied else \
        " (unrecognised build, but the patch sites matched exactly)"
    head = ("patched %d site(s) to accept custom interface files" % applied
            if applied else "already accepts custom interface files")
    return "%s%s%s (backup: %s)" \
        % (head, glow_note, note, os.path.basename(backup))


def has_changes(exe) -> bool:
    """Would restore() undo anything? A backup, or any patched pattern in place.

    Not the same as inspect() != UNPATCHED: an exe with the interface sites
    done and the eye glow site still waiting reads as UNPATCHED, yet restoring
    it reverts the interface sites.
    """
    if os.path.isfile(backup_path(exe)):
        return True
    with open(exe, "rb") as handle:
        data = handle.read()
    return _group_state(data, FACE_ARROW) == "done" or \
        _group_state(data, LEGACY_SKIN_FACE) == "done" or \
        any(_count(data, _bytes(replace)) == 1
            and _count(data, _bytes(search)) == 0
            for search, replace, _core in _PATCHES)


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
    for group in (FACE_ARROW, LEGACY_SKIN_FACE):
        if _group_state(data, group) == "done":
            _group_write(data, group, patched=False)
            reverted += len(group)
    if not reverted:
        return "was not patched; left alone"
    with open(exe, "wb") as handle:
        handle.write(bytes(data))
    return "reverted %d patch site(s) in place (no backup was present)" % reverted
