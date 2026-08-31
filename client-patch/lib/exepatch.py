"""Let a 3.3.5a Wow.exe accept custom GlueXML.

The client refuses interface files whose "## Signature:" scope does not match,
which is what blocks a custom creation-screen. One conditional jump enforces
that. Flipping it accepts custom glue.

This runs on the player's own Wow.exe and nothing pre-modified is ever shipped.
It refuses to touch anything it does not recognise, always writes a .bak first,
and can put the original back.
"""

from __future__ import annotations

import hashlib
import os
import shutil

# The stock 3.3.5a build 12340 client.
KNOWN_SHA256 = {
    "aa63a5750d60ef16746c686b3d5e26876d98953eab08b1c026cd0faf78e88cb8":
        "3.3.5a build 12340 (Wow.exe)",
}

# Unique 15-byte anchor around the TOC signature-scope check:
#   83 ff 02        cmp edi, 2         ; edi = parsed signature scope
#   74 28           je  +0x28          ; skip the mismatch error when valid
#   68 98 0f 00 00  push 0xf98
#   68 94 0e 9e 00  push 0x9e0e94      ; -> "signature does not match"
ANCHOR = bytes.fromhex("83ff02" "7428" "68980f0000" "68940e9e00")
JE_OFFSET = 3
FROM_BYTES = bytes([0x74, 0x28])  # je  +0x28
TO_BYTES = bytes([0xEB, 0x28])    # jmp +0x28

UNPATCHED = "unpatched"
PATCHED = "patched"
UNKNOWN = "unknown"


def sha256(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_path(exe) -> str:
    return str(exe) + ".classless-bak"


def inspect(exe):
    """Return (state, offset_or_None, sha256, recognised_label_or_None)."""
    with open(exe, "rb") as handle:
        data = handle.read()

    digest = hashlib.sha256(data).hexdigest()
    label = KNOWN_SHA256.get(digest)

    patched_anchor = bytearray(ANCHOR)
    patched_anchor[JE_OFFSET:JE_OFFSET + 2] = TO_BYTES
    if data.find(bytes(patched_anchor)) != -1:
        return PATCHED, data.find(bytes(patched_anchor)) + JE_OFFSET, digest, label

    hits = []
    start = data.find(ANCHOR)
    while start != -1:
        hits.append(start)
        start = data.find(ANCHOR, start + 1)

    if len(hits) == 1:
        return UNPATCHED, hits[0] + JE_OFFSET, digest, label
    return UNKNOWN, None, digest, label


def apply(exe):
    """Patch the exe. Returns a human-readable summary line."""
    state, offset, digest, label = inspect(exe)

    if state == PATCHED:
        return "already accepts custom glue; left alone"
    if state == UNKNOWN:
        raise RuntimeError(
            "Could not find the signature check in %s.\n"
            "  SHA-256: %s\n"
            "Nothing was written. Some client packs already ship a patched "
            "Wow.exe, in which case the custom creation screen simply works -- "
            "re-run with --no-exe to skip this step." % (exe, digest))

    # Private-server clients are usually repacks, so an unrecognised hash is
    # normal and refusing on it alone would make this unusable. The structural
    # check is the one that matters: exactly one match for the 15-byte anchor,
    # and the two bytes we are about to change are exactly the expected `je`.
    # A backup is written either way.
    with open(exe, "rb") as handle:
        data = bytearray(handle.read())
    if data[offset:offset + 2] != FROM_BYTES:
        raise RuntimeError("unexpected bytes at the patch site; nothing written")

    backup = backup_path(exe)
    if not os.path.exists(backup):
        shutil.copy2(exe, backup)
    data[offset:offset + 2] = TO_BYTES
    with open(exe, "wb") as handle:
        handle.write(bytes(data))

    note = ""
    if label is None:
        note = ("\n                   note: this exe is not the stock build "
                "12340 binary (sha256 %s...).\n"
                "                   The patch site was unambiguous, so it was "
                "applied anyway. Undo with --uninstall." % digest[:16])
    return "patched at file offset 0x%X (backup: %s)%s" % (
        offset, os.path.basename(backup), note)


def restore(exe):
    """Put the original exe back. Returns a summary line."""
    backup = backup_path(exe)
    if os.path.isfile(backup):
        shutil.copy2(backup, exe)
        os.remove(backup)
        return "restored from %s" % os.path.basename(backup)

    state, offset, _digest, _label = inspect(exe)
    if state != PATCHED:
        return "was not patched; left alone"
    with open(exe, "rb") as handle:
        data = bytearray(handle.read())
    data[offset:offset + 2] = FROM_BYTES
    with open(exe, "wb") as handle:
        handle.write(bytes(data))
    return "reverted the signature check in place (no backup was present)"
