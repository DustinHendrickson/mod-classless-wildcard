#!/usr/bin/env python3
"""Enable custom GlueXML/TOC signatures on a 3.3.5a (build 12340) WoW.exe — run
LOCALLY by each player on their OWN client. Nothing pre-modified is shipped:
this edits the copy already on the player's disk and is fully reversible.

WHY: the client rejects a .toc whose "## Signature:" scope doesn't match, which
blocks a custom GlueXML that carries the classless "Hero" creation-screen text.
This flips the one branch that enforces it, so a custom signature is accepted.
(You do NOT need this just to replace GlueStrings.lua via a patch MPQ — try that
first; only patch the exe if the client still refuses the custom glue.)

SAFETY — this script never blindly writes bytes:
  * verifies the exe's SHA-256 is the known build-12340 client (or --force);
  * finds the patch site by a UNIQUE 15-byte pattern and refuses otherwise;
  * confirms the target bytes are exactly `74 28` before touching them;
  * always writes WoW.exe.bak first; --dry-run writes nothing; --restore reverts.

USAGE
    python3 patch_client_exe.py --dry-run "C:\\WoW335\\Wow.exe"
    python3 patch_client_exe.py           "C:\\WoW335\\Wow.exe"
    python3 patch_client_exe.py --restore "C:\\WoW335\\Wow.exe"
"""
import argparse, hashlib, os, shutil, sys

# Verified against the standard 3.3.5a build 12340 enUS client.
KNOWN_SHA256 = {
    "aa63a5750d60ef16746c686b3d5e26876d98953eab08b1c026cd0faf78e88cb8":
        "3.3.5a build 12340 (Wow.exe, verified)",
}

# Unique 15-byte anchor around the TOC signature-scope check:
#   83 ff 02        cmp edi, 2          ; edi = parsed signature scope
#   74 28           je  +0x28           ; skip the mismatch error when valid
#   68 98 0f 00 00  push 0xf98
#   68 94 0e 9e 00  push 0x9e0e94       ; -> the "signature does not match" msg
# Forcing je(74) -> jmp(EB) always skips the rejection, accepting custom glue.
ANCHOR = bytes.fromhex("83ff02" "7428" "68980f0000" "68940e9e00")
JE_OFFSET_IN_ANCHOR = 3          # position of the 0x74 byte
FROM_BYTES = bytes([0x74, 0x28])  # je +0x28
TO_BYTES   = bytes([0xEB, 0x28])  # jmp +0x28


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description="Enable custom GlueXML on 3.3.5a Wow.exe.")
    ap.add_argument("exe")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--force", action="store_true", help="proceed on an unrecognized SHA-256")
    args = ap.parse_args()

    if not os.path.isfile(args.exe):
        print("not found:", args.exe); sys.exit(1)
    bak = args.exe + ".bak"

    if args.restore:
        if not os.path.isfile(bak):
            print("no backup at", bak); sys.exit(1)
        shutil.copy2(bak, args.exe)
        print("restored", args.exe, "from", bak)
        return

    digest = sha256(args.exe)
    print("SHA-256:", digest)
    label = KNOWN_SHA256.get(digest)

    with open(args.exe, "rb") as f:
        data = bytearray(f.read())

    # locate the check first, so an already-patched exe is recognized even
    # though patching changed its hash
    anchor_patched = bytearray(ANCHOR)
    anchor_patched[JE_OFFSET_IN_ANCHOR:JE_OFFSET_IN_ANCHOR + 2] = TO_BYTES
    if data.find(bytes(anchor_patched)) != -1:
        print("already patched (jmp in place) — nothing to do."); return

    if label:
        print("recognized:", label)
    elif not args.force:
        print("Unrecognized Wow.exe. If this is a genuine 3.3.5a 12340 client, confirm\n"
              "the SHA-256 above with the module author before using --force. Aborting\n"
              "to avoid corrupting a client this patch was not verified against.")
        sys.exit(2)

    hits = [i for i in range(len(data) - len(ANCHOR) + 1) if data[i:i + len(ANCHOR)] == ANCHOR]
    if len(hits) != 1:
        print(f"signature-check pattern found {len(hits)} times (expected 1) — aborting, "
              "no changes made."); sys.exit(3)
    je = hits[0] + JE_OFFSET_IN_ANCHOR
    if data[je:je + 2] != FROM_BYTES:
        print(f"unexpected bytes at patch site: {data[je:je+2].hex()} — aborting."); sys.exit(4)

    print(f"patch site: file 0x{je:X} (VA 0x40303F)  74 28 -> EB 28")
    if args.dry_run:
        print("dry run — no bytes written."); return

    shutil.copy2(args.exe, bak)
    print("backup written:", bak)
    data[je:je + 2] = TO_BYTES
    with open(args.exe, "wb") as f:
        f.write(data)
    print("patched — custom GlueXML/TOC signatures now accepted. Keep the .bak; "
          "--restore reverts.")


if __name__ == "__main__":
    main()
