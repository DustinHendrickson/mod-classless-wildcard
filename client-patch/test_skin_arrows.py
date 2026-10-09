#!/usr/bin/env python3
"""Run the creation screen's own Skin and Face arrows from Wow.exe in an emulator.

    python3 test_skin_arrows.py "B:/World.of.Warcraft.3.3.5a"

Needs `pip install unicorn`. Copies the client's Wow.exe (its pristine backup
when there is one) to a temp folder and maps it at 0x400000. The game's own
index builder (0x4f3dd0) loads a CharSections.dbc, then the real arrows are
pressed: Skin next/prev (0x4eb150 / 0x4eb290) and Face next/prev (0x4eb710 /
0x4eb990), as a Paladin and as a Death Knight. Only the allocator (0x76e540)
and the two redraws are faked: SetSkin (0x4ea6b0) and SetFace (0x4ea490) just
record what would be on screen.

  stock exe, stock table (what shipped before the fill)
      most faces never reach a Death Knight skin: the bug, reproduced
  stock exe, filled table
      the Face arrow lands on filled-in copies: why the exe filter exists
  patched exe, filled table (what the installer ships)
      Skin arrows reach every Death Knight skin from every face and never
      change the face; Face arrows never land on a copy, and show exactly
      what the stock exe shows on the stock table, press by press

Exits non-zero on any failure. The real client is never written.
"""

from __future__ import annotations

import glob
import os
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from lib import clientfs, dbc, exepatch  # noqa: E402

try:
    import pefile
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
    from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_ECX,
                                   UC_X86_REG_EIP, UC_X86_REG_ESP)
except ImportError as error:
    print("FAILED: %s -- run: python3 -m pip install --user unicorn pefile" % error)
    sys.exit(1)

CHARSECTIONS = "DBFilesClient\\CharSections.dbc"
CHRRACES = "DBFilesClient\\ChrRaces.dbc"
SKIN_NEXT, SKIN_PREV = 0x4EB150, 0x4EB290
FACE_NEXT, FACE_PREV = 0x4EB710, 0x4EB990
INDEX_BUILD, INDEX_GLOBAL = 0x4F3DD0, 0xB6B864
RECORD_COUNT, RECORDS = 0xAD3334, 0xAD3348
ALLOC, SET_SKIN, SET_FACE = 0x76E540, 0x4EA6B0, 0x4EA490
PALADIN, DEATH_KNIGHT = 2, 6
PRESSES = 30

FAILURES = []


def check(label, ok, detail=""):
    print("  [%s] %s%s" % ("ok  " if ok else "FAIL", label, " -- " + detail if detail else ""))
    if not ok:
        FAILURES.append(label)


class Client:
    """One emulated Wow.exe with CharSections indexed the way the game does it."""

    HEAP, STACK, MAGIC = 0x30000000, 0x0F000000, 0x0F0FF000

    def __init__(self, exe, table, max_race):
        # from bytes, not the path: pefile keeps a path memory-mapped, and
        # Windows then refuses to delete the temp copy
        with open(exe, "rb") as handle:
            pe = pefile.PE(data=handle.read(), fast_load=True)
        image = pe.get_memory_mapped_image()
        pe.close()
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        self.uc.mem_map(0x400000, (len(image) + 0xFFF) & ~0xFFF)
        self.uc.mem_write(0x400000, image)
        self.uc.mem_map(self.HEAP, 0x4000000)
        self.uc.mem_map(self.STACK, 0x100000)
        self.top = self.HEAP
        self.uc.mem_write(self.MAGIC, b"\xcc")
        for address in (ALLOC, SET_SKIN, SET_FACE, self.MAGIC):
            self.uc.hook_add(UC_HOOK_CODE, self._hook, begin=address, end=address)
        count, _fields, size, _strings = dbc.parse_header(table)
        records = self.alloc(count * size)
        self.uc.mem_write(records, table[20:20 + count * size])
        self.wr(RECORD_COUNT, count)
        self.wr(RECORDS, records)
        # the game passes (ChrRaces max id + 1) * 2 race/sex slots
        self.call(INDEX_BUILD, [max_race * 2 + 2, INDEX_GLOBAL])
        if not self.rd(INDEX_GLOBAL):
            raise RuntimeError("the client's index builder produced nothing")
        self.comp = self.alloc(0x600)

    def alloc(self, n):
        p = self.top
        self.top += (n + 15) & ~15
        return p

    def rd(self, a):
        return struct.unpack("<I", self.uc.mem_read(a, 4))[0]

    def wr(self, a, v):
        self.uc.mem_write(a, struct.pack("<I", v & 0xFFFFFFFF))

    def _hook(self, uc, address, size, user):
        esp = uc.reg_read(UC_X86_REG_ESP)
        if address == ALLOC:            # stdcall (size, file, line, flags)
            uc.reg_write(UC_X86_REG_EAX, self.alloc(self.rd(esp + 4)))
            pop = 16
        elif address == SET_SKIN:       # thiscall (colour, a, b, c)
            self.wr(uc.reg_read(UC_X86_REG_ECX) + 0x28, self.rd(esp + 4))
            pop = 16
        elif address == SET_FACE:       # thiscall (face, a, b)
            self.wr(uc.reg_read(UC_X86_REG_ECX) + 0x2C, self.rd(esp + 4))
            pop = 12
        else:
            uc.emu_stop()
            return
        uc.reg_write(UC_X86_REG_EIP, self.rd(esp))
        uc.reg_write(UC_X86_REG_ESP, esp + 4 + pop)

    def call(self, fn, args, ecx=None):
        esp = self.STACK + 0xF0000
        for a in reversed(args):
            esp -= 4
            self.wr(esp, a)
        esp -= 4
        self.wr(esp, self.MAGIC)
        self.uc.reg_write(UC_X86_REG_ESP, esp)
        if ecx is not None:
            self.uc.reg_write(UC_X86_REG_ECX, ecx)
        self.uc.emu_start(fn, self.MAGIC, count=5_000_000)

    def press(self, arrow, klass, race, sex, face, colour):
        """Press one arrow PRESSES times; returns the (face, colour) on screen
        after each press."""
        c = self.comp
        self.uc.mem_write(c, bytes(0x600))
        self.wr(c + 0x18, race)
        self.wr(c + 0x1C, sex)
        self.wr(c + 0x20, klass)
        self.wr(c + 0x28, colour)
        self.wr(c + 0x2C, face)
        shown = []
        for _ in range(PRESSES):
            if arrow in (SKIN_NEXT, SKIN_PREV):
                self.call(arrow, [0], ecx=c)                  # mode 0: creation
            else:
                # the Face arrow starts its colour search at the skin the Skin
                # arrow last chose (0xb6b18c); here, the one on screen
                self.call(arrow, [0, colour], ecx=c)
            shown.append((self.rd(c + 0x2C), self.rd(c + 0x28)))
        return shown


def survey(exe, table, stock_rows, max_race):
    client = Client(exe, table, max_race)
    count, _f, size, _s = dbc.parse_header(table)
    rows = [struct.unpack_from("<10I", table, 20 + i * size) for i in range(count)]
    face_row = {(r[1], r[2], r[8], r[9]): r for r in rows if r[3] == 1}
    dk, faces = {}, {}
    for r in stock_rows:
        if r[3] == 0 and r[7] & 0x4:
            dk.setdefault((r[1], r[2]), set()).add(r[9])
        if r[3] == 1 and r[9] == 0:
            faces.setdefault((r[1], r[2]), set()).add(r[8])
    out = {}
    for klass in (PALADIN, DEATH_KNIGHT):
        s = dict(skin_runs=0, skin_reached=0, skin_never=0, face_changed=0,
                 face_runs=0, on_copy=0, face_shown={})
        for (race, sex), colours in sorted(dk.items()):
            every = faces[(race, sex)]
            for face in sorted(every):
                for arrow in (SKIN_NEXT, SKIN_PREV):
                    shown = client.press(arrow, klass, race, sex, face, 0)
                    seen = {colour for _f, colour in shown}
                    s["skin_runs"] += 1
                    s["skin_reached"] += colours <= seen
                    s["skin_never"] += not (colours & seen)
                    s["face_changed"] += any(f != face for f, _c in shown)
            # from every face, on a normal skin and on each Death Knight skin
            for colour in [0] + sorted(colours):
                for start in sorted(every):
                    for arrow in (FACE_NEXT, FACE_PREV):
                        shown = client.press(arrow, klass, race, sex, start, colour)
                        s["face_runs"] += 1
                        s["on_copy"] += any(
                            face_row.get((race, sex, f, c), (0,))[0]
                            >= dbc.CHARSECTIONS_FILL_FIRST_ID for f, c in shown)
                        s["face_shown"][(race, sex, colour, start, arrow)] = shown
        out[klass] = s
    return out


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    wow = argv[1]
    exe = os.path.join(wow, "Wow.exe")
    source = exepatch.backup_path(exe) if os.path.isfile(exepatch.backup_path(exe)) else exe
    data_dir = os.path.join(wow, "Data")

    import install as installer
    own = set()
    for path in glob.glob(os.path.join(data_dir, "**", "patch-*.MPQ"), recursive=True):
        if installer._is_our_archive(path):
            own.add(os.path.basename(path).lower())
    locale = clientfs.detect_locales(data_dir)[0]
    with clientfs.ClientFiles(data_dir, locale, exclude=own) as files:
        stock = files.find(CHARSECTIONS)[0]
        races = files.find(CHRRACES)[0]
    count, _f, size, _s = dbc.parse_header(stock)
    stock_rows = [struct.unpack_from("<10I", stock, 20 + i * size) for i in range(count)]
    rcount, _rf, rsize, _rs = dbc.parse_header(races)
    max_race = max(struct.unpack_from("<I", races, 20 + i * rsize)[0] for i in range(rcount))
    opened_only = dbc.open_death_knight_appearance(stock)[0]
    shipped = dbc.open_death_knight_appearance(
        dbc.fill_death_knight_skin_faces(stock)[0])[0]

    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "Wow.exe")
        shutil.copy2(source, copy)
        with open(copy, "rb") as handle:
            before = exepatch._group_state(handle.read(), exepatch.FACE_ARROW)
        print("source  : %s (Face arrow sites: %s)" % (source, before))
        stock_faces = {}
        if before == "apply":
            print("\n== stock exe, stock table")
            baseline = survey(copy, opened_only, stock_rows, max_race)
            stock_faces = {k: v["face_shown"] for k, v in baseline.items()}
            s = baseline[PALADIN]
            check("the gap is reproduced: most faces never reach a Death Knight skin",
                  s["skin_never"] > s["skin_runs"] // 2,
                  "%d of %d runs never reach one" % (s["skin_never"], s["skin_runs"]))
            print("\n== stock exe, filled table")
            s = survey(copy, shipped, stock_rows, max_race)[PALADIN]
            check("without the exe filter the Face arrow lands on copies",
                  s["on_copy"] > 0, "%d of %d runs" % (s["on_copy"], s["face_runs"]))

        print("\n== patched exe, filled table (what the installer ships)")
        print("  " + exepatch.apply(copy))
        with open(copy, "rb") as handle:
            after = exepatch._group_state(handle.read(), exepatch.FACE_ARROW)
        check("Face arrow sites patched", after == "done", after)
        stats = survey(copy, shipped, stock_rows, max_race)
        for klass, name in ((PALADIN, "Hero (Paladin)"), (DEATH_KNIGHT, "Death Knight")):
            s = stats[klass]
            check("%s: Skin arrows reach all three Death Knight skins from every face" % name,
                  s["skin_reached"] == s["skin_runs"],
                  "%d of %d runs" % (s["skin_reached"], s["skin_runs"]))
            check("%s: Skin arrows never change the face" % name,
                  s["face_changed"] == 0, "%d runs changed it" % s["face_changed"])
            check("%s: Face arrows never land on a filled-in copy" % name,
                  s["on_copy"] == 0, "%d of %d runs did" % (s["on_copy"], s["face_runs"]))
            if before == "apply":
                # the copies are invisible to the Face arrows: the same face
                # AND skin as the stock exe on the stock table, every press
                differ = [k for k, v in s["face_shown"].items() if stock_faces[klass][k] != v]
                check("%s: Face arrows show exactly what stock shows, press by press" % name,
                      not differ, "%d of %d runs differ" % (len(differ), len(s["face_shown"])))

    print()
    if FAILURES:
        print("FAILED: %s" % ", ".join(FAILURES))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
