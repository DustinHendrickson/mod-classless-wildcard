#!/usr/bin/env python3
"""Run the creation screen's own skin arrows from Wow.exe in an emulator.

    python3 test_skin_arrows.py "B:/World.of.Warcraft.3.3.5a"

Needs `pip install unicorn`. Copies the client's Wow.exe (its pristine backup
when there is one) to a temp folder, patches the copy with lib/exepatch.py and
maps it at 0x400000. The game's own index builder (0x4f3dd0) runs over the
CharSections.dbc the installer ships, then the real skin-next (0x4eb150) and
skin-prev (0x4eb290) are pressed 30 times from every face of every race, for a
Paladin and a Death Knight. Only the allocator (0x76e540) and the redraw
(SetSkin, 0x4ea6b0, which records the colour and face it is given) are faked.

Checks, on the stock exe and on the patched copy:
  stock    most faces never reach a Death Knight skin (the bug, reproduced)
  patched  every face reaches all three, and never on a face with no art

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
INDEX_BUILD, INDEX_GLOBAL = 0x4F3DD0, 0xB6B864
RECORD_COUNT, RECORDS = 0xAD3334, 0xAD3348
ALLOC, SET_SKIN = 0x76E540, 0x4EA6B0
PALADIN, DEATH_KNIGHT = 2, 6

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
        self.applied = []
        self.uc.mem_write(self.MAGIC, b"\xcc")
        for address in (ALLOC, SET_SKIN, self.MAGIC):
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
        elif address == SET_SKIN:       # thiscall (colour, a, b, c)
            comp = uc.reg_read(UC_X86_REG_ECX)
            colour = self.rd(esp + 4)
            self.wr(comp + 0x28, colour)
            self.applied.append((colour, self.rd(comp + 0x2C)))
        else:
            uc.emu_stop()
            return
        uc.reg_write(UC_X86_REG_EIP, self.rd(esp))
        uc.reg_write(UC_X86_REG_ESP, esp + 4 + 16)

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

    def press(self, arrow, klass, race, sex, face, times=30):
        c = self.comp
        self.uc.mem_write(c, bytes(0x600))
        self.wr(c + 0x18, race)
        self.wr(c + 0x1C, sex)
        self.wr(c + 0x20, klass)
        self.wr(c + 0x28, 0)
        self.wr(c + 0x2C, face)
        del self.applied[:]
        for _ in range(times):
            self.call(arrow, [0], ecx=c)     # mode 0: the creation screen
        return list(self.applied)


def run(exe, table, stock_rows, max_race):
    client = Client(exe, table, max_race)
    dk, faces = {}, {}
    for r in stock_rows:
        if r[3] == 0 and r[7] & 0x4:
            dk.setdefault((r[1], r[2]), set()).add(r[9])
        if r[3] == 1 and r[9] == 0:
            faces.setdefault((r[1], r[2]), set()).add(r[8])
    art = {(r[1], r[2], r[8], r[9]) for r in stock_rows if r[3] == 1}
    stats = {}
    for klass in (PALADIN, DEATH_KNIGHT):
        runs = reached = never = no_art = 0
        for (race, sex), colours in sorted(dk.items()):
            for face in sorted(faces[(race, sex)]):
                for arrow in (SKIN_NEXT, SKIN_PREV):
                    landed = client.press(arrow, klass, race, sex, face)
                    seen = {colour for colour, _f in landed}
                    runs += 1
                    reached += colours <= seen
                    never += not (colours & seen)
                    no_art += any((race, sex, f, colour) not in art for colour, f in landed)
        stats[klass] = (runs, reached, never, no_art)
    return stats


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
    shipped = dbc.open_death_knight_appearance(stock)[0]

    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "Wow.exe")
        shutil.copy2(source, copy)
        with open(copy, "rb") as handle:
            before = exepatch._skin_face_state(handle.read())
        print("source  : %s (skin arrow sites: %s)" % (source, before))
        if before == "apply":
            print("\n== stock skin arrows")
            runs, reached, never, no_art = run(copy, shipped, stock_rows, max_race)[PALADIN]
            check("the gap is reproduced: most faces never reach a Death Knight skin",
                  never > runs // 2, "%d of %d runs never reach one" % (never, runs))
        print("\n== patched skin arrows")
        print("  " + exepatch.apply(copy))
        with open(copy, "rb") as handle:
            after = exepatch._skin_face_state(handle.read())
        check("skin arrow sites patched", after == "done", after)
        stats = run(copy, shipped, stock_rows, max_race)
        for klass, name in ((PALADIN, "Hero (Paladin)"), (DEATH_KNIGHT, "Death Knight")):
            runs, reached, never, no_art = stats[klass]
            check("%s: every face reaches all three Death Knight skins" % name,
                  reached == runs, "%d of %d runs" % (reached, runs))
            check("%s: a Death Knight skin always lands on a face drawn for it" % name,
                  no_art == 0, "%d runs landed on a face with no art" % no_art)

    print()
    if FAILURES:
        print("FAILED: %s" % ", ".join(FAILURES))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
