"""Runs the Mac client's patched code on the CPU, from the build's own bytes.

    python3 test_mac_patch.py "B:/code/wowdecomp/bin/Mac/World of Warcraft.app"

mac_patch.json says which bytes to change in an arm64 build; this maps that
build in unicorn twice, stock and patched, calls the functions each group
changes (calls out of them are stubbed) and checks the patched build does what
the Wow.exe patch does, and that the stock one does not: each check is
falsified by the stock run. Every cave borrows registers it believes dead, and
a new build can make one live while the pattern still matches, so run this on
every build gen_mac_patch.py writes.

Needs `pip install unicorn` and a stock build (a patched one is put back to
stock in memory first).
"""

from __future__ import annotations

import os
import struct
import sys

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UcError
from unicorn import arm64_const
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X30, UC_ARM64_REG_SP,
                                 UC_ARM64_REG_PC, UC_ARM64_REG_D0)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import machopatch, macho  # noqa: E402

FAILURES = []
HEAP, STACK, RETURN = 0x300000000, 0x310000000, 0x320000000
X = [getattr(arm64_const, "UC_ARM64_REG_X%d" % i) for i in range(29)]


def check(label, ok, detail=""):
    print("  [%s] %s%s" % ("ok  " if ok else "FAIL", label, (" -- " + detail) if detail else ""))
    if not ok:
        FAILURES.append(label)


class Emu:
    """The build mapped at its own addresses, a heap, a stack, and stubs:
    {address: function(emu) -> x0 or None} that return to the caller."""

    def __init__(self, data, image):
        self.image = image
        self.mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        for seg in image.segments:
            if seg.name in ("__PAGEZERO", "__LINKEDIT"):
                continue
            size = (seg.vmsize + 0x3FFF) & ~0x3FFF
            self.mu.mem_map(seg.vmaddr, size)
            self.mu.mem_write(seg.vmaddr, data[seg.fileoff:seg.fileoff + seg.filesize])
        self.mu.mem_map(HEAP, 0x100000)
        self.mu.mem_map(STACK, 0x100000)
        self.mu.mem_map(RETURN, 0x1000)
        self.heap = HEAP
        self.stubs = {}
        self.calls = []
        self.mu.hook_add(UC_HOOK_CODE, self._hook)

    def alloc(self, size, fill=b""):
        at = self.heap
        self.heap += (size + 0xF) & ~0xF
        if fill:
            self.mu.mem_write(at, fill)
        return at

    def w(self, addr, fmt, *values):
        self.mu.mem_write(addr, struct.pack("<" + fmt, *values))

    def reg(self, i):
        return self.mu.reg_read(X[i])

    def _hook(self, mu, address, size, _):
        if address in self.stubs:
            name, fn = self.stubs[address]
            self.calls.append((name, [self.reg(i) for i in range(5)]))
            value = fn(self) if fn else 0
            if value is not None:
                mu.reg_write(UC_ARM64_REG_X0, value & 0xFFFFFFFFFFFFFFFF)
            mu.reg_write(UC_ARM64_REG_PC, mu.reg_read(UC_ARM64_REG_X30))
        elif address in self.stops:
            self.stopped = address
            mu.emu_stop()

    def stub(self, addr, name, fn=None):
        self.stubs[addr] = (name, fn)

    def run(self, start, regs=None, stops=(), limit=5000):
        """Run from `start` until a stop address or a return. Returns the
        stop address, or RETURN."""
        self.stops = set(stops) | {RETURN}
        self.stopped = None
        for i, value in (regs or {}).items():
            self.mu.reg_write(X[i], value)
        self.mu.reg_write(UC_ARM64_REG_SP, STACK + 0xF0000)
        self.mu.reg_write(UC_ARM64_REG_X30, RETURN)
        try:
            self.mu.emu_start(start, 0, count=limit)
        except UcError as error:
            raise RuntimeError("emulation failed at %#x: %s"
                               % (self.mu.reg_read(UC_ARM64_REG_PC), error))
        return self.stopped


def build_pair(app):
    exe = machopatch.app_executable(app) if os.path.isdir(app) else app
    data = open(exe, "rb").read()
    stock, build = machopatch.patched_bytes(data, patched=False)
    patched, _ = machopatch.patched_bytes(data, patched=True)
    return stock, patched, build


def main():
    app = sys.argv[1] if len(sys.argv) > 1 else r"B:\code\wowdecomp\bin\Mac\World of Warcraft.app"
    stock, patched, build = build_pair(app)
    image = macho.MachO(stock)
    sym = {}
    for addr, name in image.symbols():
        sym.setdefault(name, addr)
    print("build: %s %s" % (build["label"], build["uuid"]))

    def emu(which):
        return Emu(patched if which else stock, image)

    def unit(e, cls=2, display=0, power=None, flags2=0x08, petnumber=0, createdby=0):
        data = e.alloc(0x200)
        e.w(data + 0x45, "B", cls)
        e.w(data + 0x47, "B", display)
        e.w(data + 0xD9, "B", flags2)
        e.w(data + 0x114, "I", petnumber)
        e.w(data + 0x28, "Q", createdby)
        obj = e.alloc(0x2000)
        e.w(obj + 0x160, "Q", data)
        return obj, data

    # --- combo points: GetComboPoints("player") ----------------------------
    print("\n== combo points")
    fn = sym["__Z21Script_GetComboPointsP9lua_State"]
    for which in (0, 1):
        for cls in (2, 4, 11, 1):
            e = emu(which)
            player, _ = unit(e, cls=cls)
            guids = iter([0x1234, 0x9999])
            pushed = []
            e.stub(0x1000fb834, "lua_isstring", lambda e: 1)
            e.stub(0x1000fc398, "lua_tolstring", lambda e: 0)
            e.stub(0x10057ca48, "GetGUIDFromToken", lambda e: e.w(e.reg(1), "Q", next(guids)) or 0)
            e.stub(0x1003f7f30, "GetActivePlayer", lambda e: 0x1234)
            e.stub(0x1003f7f68, "ObjectPtr", lambda e, p=player: p)
            e.stub(0x1004ebfd4, "CGGameUI::GetComboPoints", lambda e: 3)
            e.stub(0x1000fcd44, "lua_pushnumber",
                   lambda e: pushed.append(struct.unpack("<d", struct.pack("<Q", e.mu.reg_read(UC_ARM64_REG_D0)))[0]) or 0)
            e.run(fn, {0: e.alloc(16)})
            want = 3.0 if which or cls in (4, 11) else 0.0
            check("%s, class %d: GetComboPoints answers %s" % ("patched" if which else "stock", cls, want),
                  pushed == [want], str(pushed))

    # --- regen and runes: CGUnit_C::DoPowerRegen -----------------------------
    print("\n== regeneration and runes")
    fn = sym["__ZN8CGUnit_C12DoPowerRegenEj"]
    for which in (0, 1):
        e = emu(which)
        obj, data = unit(e, cls=2, display=0)
        vtable = e.alloc(0x300)
        e.w(vtable + 0x258, "Q", 0x100005000)          # IsDeadOrGhost: a stub address
        e.w(obj, "Q", vtable)
        objdesc = e.alloc(16)
        e.w(objdesc, "Q", 0x1234)
        e.w(obj + 0x10, "Q", objdesc)
        e.w(0x100a6be04, "I", 0xFE)                     # rune 0 spent, its time up
        e.stub(0x100005000, "IsDeadOrGhost", lambda e: 0)
        e.stub(0x1003deefc, "DoPowerRegen(type)")
        e.stub(0x1003f7f30, "GetActivePlayer", lambda e: 0x1234)
        e.stub(0x10057911c, "GetRuneRechargeTime", lambda e: 0)
        e.stub(0x10057a778, "SetPredictedRunes")
        e.run(fn, {0: obj, 1: 50})
        regen = [args[1] for name, args in e.calls if name == "DoPowerRegen(type)"]
        runes = [args[:2] for name, args in e.calls if name == "SetPredictedRunes"]
        check("%s: a Hero on a mana bar regenerates %s" % ("patched" if which else "stock",
              "mana and energy" if which else "mana only"),
              regen == ([0, 3] if which else [0]), str(regen))
        check("%s: a spent rune %s back on a mana bar" % ("patched" if which else "stock",
              "comes" if which else "does not come"),
              (runes == [[0xFE, 0xFF]]) if which else not runes, str(runes))

    # --- hunter pets: CanGainXP, GetPetPersonality ---------------------------
    print("\n== hunter pets")
    for which in (0, 1):
        for owner_cls, pet_power, want_stock, want_patched in (
                (3, 2, 1, 1), (2, 2, 0, 1), (2, 0, 0, 0), (3, 0, 1, 0)):
            e = emu(which)
            owner, _ = unit(e, cls=owner_cls)
            pet, _ = unit(e, display=pet_power, petnumber=7, createdby=0x55)
            e.stub(0x1003f7f68, "ObjectPtr", lambda e, o=owner: o)
            e.run(sym["__ZNK8CGUnit_C9CanGainXPEv"], {0: pet})
            got = e.reg(0) & 0xFF
            want = want_patched if which else want_stock
            check("%s CanGainXP: owner class %d, pet power %d -> %d"
                  % ("patched" if which else "stock", owner_cls, pet_power, want), got == want, str(got))
            # the personality table: one row, id 1
            db = 0x1009b9d28
            record = e.alloc(16)
            rows = e.alloc(8)
            e.w(rows, "Q", record)
            e.w(db + 0x10, "ii", 1, 1)
            e.w(db + 0x30, "Q", rows)
            e.run(sym["__ZNK8CGUnit_C17GetPetPersonalityEv"], {0: pet})
            got = e.reg(0)
            check("%s GetPetPersonality: owner class %d, pet power %d -> %s"
                  % ("patched" if which else "stock", owner_cls, pet_power,
                     "a row" if want else "none"), (got == record) == bool(want), "%#x" % got)

    # --- totems: CGBag_C::FindTotemCategory(category, flags) -----------------
    print("\n== the totem tool")
    for which in (0, 1):
        for cat, ctype, want_patched in ((2, 2, 1), (21, 2, 1), (7, 1, 0), (40, None, 0)):
            e = emu(which)
            db = 0x1009bab28
            rows = e.alloc(64 * 8)
            for c, t in ((2, 2), (21, 2), (7, 1)):
                rec = e.alloc(0x20)
                e.w(rec + 0x10, "ii", t, 1 << c)
                e.w(rows + (c - 1) * 8, "Q", rec)
            e.w(db + 0x10, "ii", 30, 1)                     # max id, min id
            e.w(db + 0x30, "Q", rows)
            e.stub(0x10033b500, "search the bags", lambda e: 0)
            e.run(sym["__ZN7CGBag_C17FindTotemCategoryEij"], {0: e.alloc(16), 1: cat, 2: 0})
            got = e.reg(0) & 0xFF
            want = want_patched if which else 0
            check("%s: category %d (type %s) reads as %s with empty bags"
                  % ("patched" if which else "stock", cat, ctype, "carried" if want else "missing"),
                  got == want, str(got))

    # --- reagents: Spell_C_HasNoReagentCost ----------------------------------
    print("\n== reagent waivers")
    for which in (0, 1):
        for family, want_patched in ((5, 1), (10, 1), (0, 0)):
            e = emu(which)
            player, _ = unit(e)
            pdata = e.alloc(0x1300)
            e.w(player + 0x1890, "Q", pdata)
            e.w(pdata + 0x1224, "III", 0x40, 0, 0)
            spell = e.alloc(0x300)
            e.w(spell + 0x250, "IIII", family, 0x40, 0, 0)
            e.w(0x100bde790, "I", 10)                       # the Paladin's family
            e.run(sym["__Z24Spell_C_HasNoReagentCostP10CGPlayer_CPK8SpellRec"], {0: player, 1: spell})
            got = e.reg(0) & 0xFF
            want = want_patched if which else int(family == 10)
            check("%s: a no-reagent aura on a family %d spell -> %d"
                  % ("patched" if which else "stock", family, want), got == want, str(got))

    # --- the relic slot: CGItem_C::CanGoInSlot, slot 17 -----------------------
    print("\n== the ranged slot")
    fn = sym["__ZN8CGItem_C11CanGoInSlotEiji"]
    start = fn + 0xF0                                     # ldr w8, [x21, #0x18]
    for which in (0, 1):
        for inv, bypass, want_stock, want_patched in ((28, 0, 0, 1), (15, 0, 1, 1), (28, 1, 1, 1), (5, 0, 0, 0)):
            e = emu(which)
            rec = e.alloc(0x40)
            e.w(rec + 0x18, "I", inv)
            stop = e.run(start, {21: rec, 20: bypass}, stops=(fn + 0x294, fn + 0x298))
            got = 0 if stop == fn + 0x294 else e.reg(0) & 1
            want = want_patched if which else want_stock
            check("%s: inventory type %d, relic flag %d -> %d" % ("patched" if which else "stock", inv, bypass, want),
                  got == want, "stopped %s, w0 %d" % (hex(stop or 0), got))

    # --- feral attack power: the class tests ---------------------------------
    print("\n== feral attack power")
    for group in ("feral-dps", "feral-scaling", "feral-line"):
        parts = next(g for g in build["groups"] if g["name"] == group)["parts"]
        for off, _s, _p in parts:
            site = image.address(off)                      # cmp w8, #...
            branch = struct.unpack_from("<I", stock, off + 4)[0]
            target = site + 4 + ((((branch >> 5) & 0x7FFFF) ^ 0x40000) - 0x40000) * 4
            taken_on_eq = branch & 0xF == 0
            for which in (0, 1):
                for cls in (2, 11):
                    e = emu(which)
                    player, _ = unit(e, cls=cls)
                    stop = e.run(site - 8, {0: player, 8: player}, stops=(target, site + 8))
                    feral = (stop == target) == taken_on_eq
                    want = cls == (2 if which else 11)
                    check("%s %s at %#x, class %d: feral line %s" % ("patched" if which else "stock", group,
                          site, cls, "shown" if want else "hidden"), feral == want)

    # --- power sync: UnitPowerUpdateHandler ----------------------------------
    print("\n== power sync")
    fn = sym["__Z22UnitPowerUpdateHandler7WOWGUIDjjPKvPv"]
    MANA, RAGE, ENERGY, RUNIC, HEALTH = 0, 1, 3, 6, -2
    for which in (0, 1):
        for what, ptype, server, predicted, bar, take_stock, take_patched in (
                ("a higher value lands", RAGE, 500, 200, MANA, 1, 1),
                ("rage off the bar takes a lower value", RAGE, 0, 400, MANA, 0, 1),
                ("runic power off the bar takes a lower value", RUNIC, 100, 800, ENERGY, 0, 1),
                ("the bar's own pool keeps its prediction", MANA, 900, 1000, MANA, 0, 0),
                ("an equal value on the bar is kept", ENERGY, 60, 60, ENERGY, 0, 0),
                ("health keeps its prediction", HEALTH, 100, 200, MANA, 0, 0)):
            e = emu(which)
            obj, data = unit(e, display=bar)
            if ptype == HEALTH:
                e.w(data + 0x48, "i", server)
            else:
                e.w(data + 0x4C + 4 * ptype, "i", server)
            e.w(obj + 0x1818 + 4 * ptype, "i", predicted)
            cvar = e.alloc(0x60)
            e.w(cvar + 0x54, "I", 1)
            e.w(0x100a44810, "Q", cvar)
            e.stub(0x1003f7f68, "ObjectPtr", lambda e, o=obj: o)
            e.stub(0x1003f7f30, "GetActivePlayer", lambda e: 0x1234)
            e.stub(0x1005526f8, "GetPet", lambda e: 0)
            e.stub(0x10030652c, "SetPredictedPower")
            e.run(fn, {0: 0x1234, 1: (0x4C + 4 * ptype) & 0xFFFFFFFF})
            took = any(n == "SetPredictedPower" for n, _a in e.calls)
            want = take_patched if which else take_stock
            check("%s: %s" % ("patched" if which else "stock", what), took == bool(want),
                  "took" if took else "kept")

    # --- the Face arrows: colour count and fit --------------------------------
    print("\n== the Face arrows")
    fills = 30000
    for ids, want_patched in (([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, fills, fills + 1], 10),
                              ([1, 2, 3, 4, 5, 6, 7, 8, 9, None, fills, fills + 1], 9),
                              ([fills, fills + 1], 0), ([1, 2, 3], 3)):
        for which in (0, 1):
            e = emu(which)
            lookup = e.alloc(0x50 * 4)
            colors = e.alloc(8 * len(ids))
            for i, rid in enumerate(ids):
                if rid is not None:
                    rec = e.alloc(0x30)
                    e.w(rec, "I", rid)
                    e.w(colors + 8 * i, "Q", rec)
            facelist = e.alloc(16 * 2)
            e.w(facelist + 16, "iiQ", len(ids), 0, colors)
            race, sex = 1, 0
            e.w(lookup + 0x50 * (race * 2 + sex) + 16 * 1, "iiQ", 2, 0, facelist)
            target = image.address(next(g for g in build["groups"] if g["name"] == "face-arrow")["parts"][0][0])
            # the count the arrow's call site reaches: the cave when patched
            callee = sym["__Z21ComponentGetNumColorsP7st_raceii20COMPONENT_VARIATIONSi"]
            if which:
                word = struct.unpack_from("<I", patched, image.file_offset(target))[0]
                callee = target + ((((word & 0x3FFFFFF) ^ 0x2000000) - 0x2000000) * 4)
            e.run(callee, {0: lookup, 1: race, 2: sex, 3: 1, 4: 1})
            got = e.reg(0) & 0xFFFFFFFF
            want = want_patched if which else len(ids)
            check("%s: %d colours (%s) count as %d" % ("patched" if which else "stock", len(ids),
                  "copies at the top" if fills in ids else "none copied", want), got == want, str(got))
    fits = image.address(next(g for g in build["groups"] if g["name"] == "face-arrow")["parts"][3][0])
    for rid, flags, want in ((12, 0x3, 0x3), (fills + 4, 0x3, 0)):
        e = emu(1)
        rec = e.alloc(0x30)
        e.w(rec, "I", rid)
        e.w(rec + 0x28, "I", flags)
        word = struct.unpack_from("<I", patched, image.file_offset(fits))[0]
        cave = fits + ((((word & 0x3FFFFFF) ^ 0x2000000) - 0x2000000) * 4)
        e.run(cave, {25: rec})
        check("patched: row %d hands the skin check flags %#x" % (rid, want), e.reg(0) & 0xFFFFFFFF == want)

    # --- the Death Knight eye glow ---------------------------------------------
    print("\n== eye glow")
    site = image.address(next(g for g in build["groups"] if g["name"] == "glow")["parts"][0][0])
    for which in (0, 1):
        for flags, glow_stock, glow_patched in ((0x4, 1, 1), (0x10, 0, 1), (0x14, 1, 1), (0x1, 0, 0)):
            e = emu(which)
            rec = e.alloc(0x30)
            e.w(rec + 0x28, "I", flags)
            e.run(site - 4, {0: rec}, stops=(site + 8,))
            glow = not (e.reg(21) & 1)                      # cset w21, eq: 1 means no glow
            want = glow_patched if which else glow_stock
            check("%s: face flags %#x %s" % ("patched" if which else "stock", flags,
                  "glow" if want else "do not glow"), glow == bool(want))

    # --- interface signatures: FrameXML_CheckSignature -------------------------
    print("\n== interface signatures")
    fn = sym["__Z23FrameXML_CheckSignaturePKcS0_PKhPh"]
    for which in (0, 1):
        for case, read, size in (("no .sig file", 0, 0), ("a .sig of the wrong size", 1, 0x113)):
            e = emu(which)
            guard = e.alloc(8, b"\x11" * 8)
            e.w(0x1009405e8, "Q", guard)
            digest = e.alloc(16)
            sigdata = e.alloc(0x200)

            def readfile(e, read=read, size=size, sigdata=sigdata):
                e.w(e.reg(2), "Q", sigdata)
                e.w(e.reg(3), "I", size)
                return read
            e.stub(0x1001df0d4, "SStrPrintf")
            e.stub(0x10001d450, "SFile::ReadFile", readfile)
            e.stub(0x10001b964, "SFile::Unload")
            e.stub(0x1001cc114, "MD5Init")
            e.stub(0x1001238f0, "ProcessFileForMakeSign")
            e.stub(0x1001ccbd4, "MD5Final")
            e.stub(0x10082534c, "__stack_chk_fail", lambda e: e.mu.emu_stop())
            e.run(fn, {0: e.alloc(64), 1: 0, 2: e.alloc(256), 3: digest})
            names = [n for n, _a in e.calls]
            got = e.reg(0) & 0xFFFFFFFF
            want = 3 if which else (0 if not read else 1)
            check("%s, %s: answers %d%s" % ("patched" if which else "stock", case, want,
                  " and still computes the digest" if which else ""),
                  got == want and (("MD5Final" in names) == bool(which))
                  and "__stack_chk_fail" not in names, "%d %s" % (got, names))

    print()
    if FAILURES:
        print("FAILED: " + ", ".join(FAILURES))
        return 1
    print("all Mac patch checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
