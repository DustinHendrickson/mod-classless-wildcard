"""Runs an arm64 client's patched code on the CPU, from the build's own bytes.

    python3 test_arm64_patch.py "B:/code/wowdecomp/bin/Mac/World of Warcraft.app"
    python3 test_arm64_patch.py "B:/code/wowdecomp/bin/Switch/WoW.nro" [--elf Wow.elf]

arm64_patch.json says which bytes to change in a Mac or Switch build; this maps
that build in unicorn twice, stock and patched, calls the functions each group
changes (calls out of them are stubbed) and checks the patched build does what
the Wow.exe patch does, and that the stock one does not: each check is
falsified by the stock run. A change the build already has (the Switch build
loads unsigned interface files) is checked in the stock build. Every cave
borrows registers it believes dead, and a new build can make one live while
the pattern still matches, so run this on every build gen_arm64_patch.py
writes.

No address here belongs to one build. Functions and globals are found by
their symbols (an NRO's from the Wow.elf beside it); what has none (a static,
an imported stub, a branch target) is read out of the instructions that use
it, with gen_arm64_patch.py's matcher.

Needs `pip install unicorn capstone keystone-engine` and a stock build (a
patched one is put back to stock in memory first).
"""

from __future__ import annotations

import os
import re
import struct
import sys
import tempfile

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UcError
from unicorn import arm64_const
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X30, UC_ARM64_REG_SP,
                                 UC_ARM64_REG_PC, UC_ARM64_REG_D0)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import armpatch, nro  # noqa: E402
import gen_arm64_patch  # noqa: E402
from gen_arm64_patch import GenError, HEX  # noqa: E402

FAILURES = []
# FAKE holds functions the build reaches through a pointer the test writes
HEAP, STACK, RETURN, FAKE = 0x300000000, 0x310000000, 0x320000000, 0x330000000
X = [getattr(arm64_const, "UC_ARM64_REG_X%d" % i) for i in range(29)]
IMM = r"(0x[0-9a-f]+|\d)"                           # capstone writes 0 to 9 in decimal


def check(label, ok, detail=""):
    print("  [%s] %s%s" % ("ok  " if ok else "FAIL", label, (" -- " + detail) if detail else ""))
    if not ok:
        FAILURES.append(label)


class Emu:
    """The build mapped at its own addresses, a heap, a stack, and stubs:
    {address: function(emu) -> x0 or None} that return to the caller."""

    def __init__(self, data, code):
        self.mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        if code.platform == "switch":
            # an NRO's segments sit at their own offsets, and its .bss follows
            image = nro.Nro(data)
            data_off, data_size = image.segments[2]
            bss = struct.unpack_from("<I", data, 0x38)[0]
            self.mu.mem_map(0, (data_off + data_size + bss + 0x3FFF) & ~0x3FFF)
            self.mu.mem_write(0, data[:image.size])
        else:
            for seg in code.image.segments:
                if seg.name in ("__PAGEZERO", "__LINKEDIT"):
                    continue
                size = (seg.vmsize + 0x3FFF) & ~0x3FFF
                self.mu.mem_map(seg.vmaddr, size)
                self.mu.mem_write(seg.vmaddr, data[seg.fileoff:seg.fileoff + seg.filesize])
        self.mu.mem_map(HEAP, 0x100000)
        self.mu.mem_map(STACK, 0x100000)
        self.mu.mem_map(RETURN, 0x1000)
        self.mu.mem_map(FAKE, 0x1000)
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


def build_pair(path):
    exe = armpatch.app_executable(path) if os.path.isdir(path) else path
    data = open(exe, "rb").read()
    stock, build = armpatch.patched_bytes(data, patched=False)
    patched, _ = armpatch.patched_bytes(data, patched=True)
    return stock, patched, build


def listing(stock, path, elf_path):
    """gen_arm64_patch.py's view of the stock bytes: symbols, functions and
    instruction runs."""
    if nro.is_nro(stock) and not elf_path:
        folder = os.path.dirname(os.path.abspath(path))
        elf_path = next((os.path.join(folder, n) for n in os.listdir(folder) if n.lower() == "wow.elf"), None)
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "WoW.nro" if nro.is_nro(stock) else "World of Warcraft")
        with open(copy, "wb") as handle:
            handle.write(stock)
        return gen_arm64_patch.load(copy, elf_path)


def found(code, symbol, pattern):
    """A run of instructions that is in `symbol` exactly once: (its
    addresses, the numbers its groups capture)."""
    hits = code.match(symbol, pattern, {})
    if len(hits) != 1:
        raise GenError("%s: the instructions the test reads are there %d time(s), expected 1"
                       % (symbol, len(hits)))
    return hits[0]


def page_load(code, symbol, pattern):
    """(the address an adrp and the load after it read, the run's other
    numbers). `pattern` opens with those two; OFF in the load stands for its
    offset, which capstone leaves out when it is 0."""
    off = ", #" + IMM
    if not code.match(symbol, [p.replace("OFF", off) for p in pattern], {}):
        off = ""
    _addrs, numbers = found(code, symbol, [p.replace("OFF", off) for p in pattern])
    if not off:
        numbers.insert(1, 0)
    return numbers[0] + numbers[1], numbers[2:]


def group_parts(build, name):
    return next(g for g in build["groups"] if g["name"] == name)["parts"]


def first_after(code, symbol, addr, regex):
    """The numbers in the first instruction of `symbol` at or after `addr`
    that `regex` matches."""
    for at, text in code.function(symbol):
        match = re.fullmatch(regex, text) if at >= addr else None
        if match:
            return [int(g, 16) for g in match.groups()]
    raise GenError("%s: nothing after %#x is %s" % (symbol, addr, regex))


def main():
    args = [a for a in sys.argv[1:] if a != "--elf"]
    elf_path = sys.argv[sys.argv.index("--elf") + 1] if "--elf" in sys.argv else None
    args = [a for a in args if a != elf_path]
    path = args[0] if args else r"B:\code\wowdecomp\bin\Mac\World of Warcraft.app"
    try:
        return run(path, elf_path)
    except GenError as error:
        print("\nNot checked: %s" % error)
        return 1


def run(path, elf_path=None):
    stock, patched, build = build_pair(path)
    code = listing(stock, path, elf_path)
    sym = code.symbol
    print("build: %s %s" % (build["label"], build["key"]))

    def emu(which):
        return Emu(patched if which else stock, code)

    def group(name):
        return next(g for g in build["groups"] if g["name"] == name)

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

    active_player = sym("__Z25ClntObjMgrGetActivePlayerv")
    object_ptr = sym("__Z19ClntObjMgrObjectPtr7WOWGUID8TypeMaskPKci")

    # --- combo points: GetComboPoints("player") ----------------------------
    print("\n== combo points")
    fn = sym("__Z21Script_GetComboPointsP9lua_State")
    for which in (0, 1):
        for cls in (2, 4, 11, 1):
            e = emu(which)
            player, _ = unit(e, cls=cls)
            guids = iter([0x1234, 0x9999])
            pushed = []
            e.stub(sym("_lua_isstring"), "lua_isstring", lambda e: 1)
            e.stub(sym("_lua_tolstring"), "lua_tolstring", lambda e: 0)
            e.stub(sym("__Z23Script_GetGUIDFromTokenPKcR7WOWGUIDb"), "GetGUIDFromToken",
                   lambda e: e.w(e.reg(1), "Q", next(guids)) or 0)
            e.stub(active_player, "GetActivePlayer", lambda e: 0x1234)
            e.stub(object_ptr, "ObjectPtr", lambda e, p=player: p)
            e.stub(sym("__ZN8CGGameUI14GetComboPointsE7WOWGUID"), "CGGameUI::GetComboPoints", lambda e: 3)
            e.stub(sym("_lua_pushnumber"), "lua_pushnumber",
                   lambda e: pushed.append(struct.unpack("<d", struct.pack("<Q", e.mu.reg_read(UC_ARM64_REG_D0)))[0]) or 0)
            e.run(fn, {0: e.alloc(16)})
            want = 3.0 if which or cls in (4, 11) else 0.0
            check("%s, class %d: GetComboPoints answers %s" % ("patched" if which else "stock", cls, want),
                  pushed == [want], str(pushed))

    # --- regen and runes: CGUnit_C::DoPowerRegen -----------------------------
    print("\n== regeneration and runes")
    fn = sym("__ZN8CGUnit_C12DoPowerRegenEj")
    for which in (0, 1):
        e = emu(which)
        obj, data = unit(e, cls=2, display=0)
        vtable = e.alloc(0x300)
        e.w(vtable + 0x258, "Q", FAKE)                  # IsDeadOrGhost
        e.w(obj, "Q", vtable)
        objdesc = e.alloc(16)
        e.w(objdesc, "Q", 0x1234)
        e.w(obj + 0x10, "Q", objdesc)
        e.w(sym("__ZN10CGRuneInfo16m_predictedRunesE"), "I", 0xFE)     # rune 0 spent, its time up
        e.stub(FAKE, "IsDeadOrGhost", lambda e: 0)
        e.stub(sym("__ZN8CGUnit_C12DoPowerRegenE10POWER_TYPEj"), "DoPowerRegen(type)")
        e.stub(active_player, "GetActivePlayer", lambda e: 0x1234)
        e.stub(sym("__ZN10CGRuneInfo19GetRuneRechargeTimeEi"), "GetRuneRechargeTime", lambda e: 0)
        e.stub(sym("__ZN10CGRuneInfo17SetPredictedRunesEhhPKh"), "SetPredictedRunes")
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
    db = sym("_g_petPersonalityDB")
    for which in (0, 1):
        for owner_cls, pet_power, want_stock, want_patched in (
                (3, 2, 1, 1), (2, 2, 0, 1), (2, 0, 0, 0), (3, 0, 1, 0)):
            e = emu(which)
            owner, _ = unit(e, cls=owner_cls)
            pet, _ = unit(e, display=pet_power, petnumber=7, createdby=0x55)
            e.stub(object_ptr, "ObjectPtr", lambda e, o=owner: o)
            e.run(sym("__ZNK8CGUnit_C9CanGainXPEv"), {0: pet})
            got = e.reg(0) & 0xFF
            want = want_patched if which else want_stock
            check("%s CanGainXP: owner class %d, pet power %d -> %d"
                  % ("patched" if which else "stock", owner_cls, pet_power, want), got == want, str(got))
            # the personality table: one row, id 1
            record = e.alloc(16)
            rows = e.alloc(8)
            e.w(rows, "Q", record)
            e.w(db + 0x10, "ii", 1, 1)
            e.w(db + 0x30, "Q", rows)
            e.run(sym("__ZNK8CGUnit_C17GetPetPersonalityEv"), {0: pet})
            got = e.reg(0)
            check("%s GetPetPersonality: owner class %d, pet power %d -> %s"
                  % ("patched" if which else "stock", owner_cls, pet_power,
                     "a row" if want else "none"), (got == record) == bool(want), "%#x" % got)

    # --- totems: CGBag_C::FindTotemCategory(category, flags) -----------------
    print("\n== the totem tool")
    db = sym("_g_totemCategoryDB")
    for which in (0, 1):
        for cat, ctype, want_patched in ((2, 2, 1), (21, 2, 1), (7, 1, 0), (40, None, 0)):
            e = emu(which)
            rows = e.alloc(64 * 8)
            for c, t in ((2, 2), (21, 2), (7, 1)):
                rec = e.alloc(0x20)
                e.w(rec + 0x10, "ii", t, 1 << c)
                e.w(rows + (c - 1) * 8, "Q", rec)
            e.w(db + 0x10, "ii", 30, 1)                     # max id, min id
            e.w(db + 0x30, "Q", rows)
            e.stub(sym("__ZN7CGBag_C17FindTotemCategoryEiRibj"), "search the bags", lambda e: 0)
            e.run(sym("__ZN7CGBag_C17FindTotemCategoryEij"), {0: e.alloc(16), 1: cat, 2: 0})
            got = e.reg(0) & 0xFF
            want = want_patched if which else 0
            check("%s: category %d (type %s) reads as %s with empty bags"
                  % ("patched" if which else "stock", cat, ctype, "carried" if want else "missing"),
                  got == want, str(got))

    # --- reagents: Spell_C_HasNoReagentCost ----------------------------------
    print("\n== reagent waivers")
    symbol = "__Z24Spell_C_HasNoReagentCostP10CGPlayer_CPK8SpellRec"
    # s_spellClassSet is static: by its symbol where the build lists it, or
    # the word the reagent site compares with
    try:
        class_set = sym("__ZL15s_spellClassSet")
    except GenError:
        class_set, _ = page_load(code, symbol, [r"adrp (?:x9|x10), #" + HEX,
                                                r"ldr (?:w9|w10), \[(?:x9|x10)OFF\]"])
    for which in (0, 1):
        for family, want_patched in ((5, 1), (10, 1), (0, 0)):
            e = emu(which)
            player, _ = unit(e)
            pdata = e.alloc(0x1300)
            e.w(player + 0x1890, "Q", pdata)
            e.w(pdata + 0x1224, "III", 0x40, 0, 0)
            spell = e.alloc(0x300)
            e.w(spell + 0x250, "IIII", family, 0x40, 0, 0)
            e.w(class_set, "I", 10)                         # the Paladin's family
            e.run(sym(symbol), {0: player, 1: spell})
            got = e.reg(0) & 0xFF
            want = want_patched if which else int(family == 10)
            check("%s: a no-reagent aura on a family %d spell -> %d"
                  % ("patched" if which else "stock", family, want), got == want, str(got))

    # --- the relic slot: CGItem_C::CanGoInSlot, slot 17 -----------------------
    print("\n== the ranged slot")
    relic = next(form[0] for name, _t, forms in gen_arm64_patch.SITES if name == "relic" for form in forms)
    # from the site's own run: cmp x8, #0x1c ... b.ne refused; the slot's bit
    # is then w0, and the next b leaves for the shared exit
    addrs, (refused,) = found(code, relic.symbol, relic.pattern)
    leave, = first_after(code, relic.symbol, addrs[-1] + 4, r"b #" + HEX)
    for which in (0, 1):
        for inv, bypass, want_stock, want_patched in ((28, 0, 0, 1), (15, 0, 1, 1), (28, 1, 1, 1), (5, 0, 0, 0)):
            e = emu(which)
            stop = e.run(addrs[0], {8: inv, 20: bypass}, stops=(refused, leave))
            got = 0 if stop == refused else e.reg(0) & 1
            want = want_patched if which else want_stock
            check("%s: inventory type %d, relic flag %d -> %d" % ("patched" if which else "stock", inv, bypass, want),
                  got == want, "stopped %s, w0 %d" % (hex(stop or 0), got))

    # --- feral attack power: the class tests ---------------------------------
    print("\n== feral attack power")
    for group_name in ("feral-dps", "feral-scaling", "feral-line"):
        for off, _s, _p in group_parts(build, group_name):
            site = code.address(off)                       # cmp w8, #...
            branch = struct.unpack_from("<I", stock, off + 4)[0]
            target = site + 4 + ((((branch >> 5) & 0x7FFFF) ^ 0x40000) - 0x40000) * 4
            taken_on_eq = branch & 0xF == 0
            for which in (0, 1):
                for cls in (2, 11):
                    e = emu(which)
                    _player, data = unit(e, cls=cls)
                    stop = e.run(site - 4, {8: data}, stops=(target, site + 8))     # ldrb w8, [x8, #0x45]
                    feral = (stop == target) == taken_on_eq
                    want = cls == (2 if which else 11)
                    check("%s %s at %#x, class %d: feral line %s" % ("patched" if which else "stock", group_name,
                          site, cls, "shown" if want else "hidden"), feral == want)

    # --- power sync: UnitPowerUpdateHandler ----------------------------------
    print("\n== power sync")
    fn = sym("__Z22UnitPowerUpdateHandler7WOWGUIDjjPKvPv")
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
            e.w(sym("_g_predictedPowerCVar"), "Q", cvar)
            e.stub(object_ptr, "ObjectPtr", lambda e, o=obj: o)
            e.stub(active_player, "GetActivePlayer", lambda e: 0x1234)
            e.stub(sym("__ZN9CGPetInfo6GetPetEj"), "GetPet", lambda e: 0)
            e.stub(sym("__ZN8CGUnit_C17SetPredictedPowerE10POWER_TYPEi"), "SetPredictedPower")
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
            target = code.address(group("face-arrow")["parts"][0][0])
            # the count the arrow's call site reaches: the cave when patched
            callee = sym("__Z21ComponentGetNumColorsP7st_raceii20COMPONENT_VARIATIONSi")
            if which:
                word = struct.unpack_from("<I", patched, code.file_offset(target))[0]
                callee = target + ((((word & 0x3FFFFFF) ^ 0x2000000) - 0x2000000) * 4)
            e.run(callee, {0: lookup, 1: race, 2: sex, 3: 1, 4: 1})
            got = e.reg(0) & 0xFFFFFFFF
            want = want_patched if which else len(ids)
            check("%s: %d colours (%s) count as %d" % ("patched" if which else "stock", len(ids),
                  "copies at the top" if fills in ids else "none copied", want), got == want, str(got))
    fits = code.address(group("face-arrow")["parts"][3][0])
    for rid, flags, want in ((12, 0x3, 0x3), (fills + 4, 0x3, 0)):
        e = emu(1)
        rec = e.alloc(0x30)
        e.w(rec, "I", rid)
        e.w(rec + 0x28, "I", flags)
        word = struct.unpack_from("<I", patched, code.file_offset(fits))[0]
        cave = fits + ((((word & 0x3FFFFFF) ^ 0x2000000) - 0x2000000) * 4)
        e.run(cave, {25: rec})
        check("patched: row %d hands the skin check flags %#x" % (rid, want), e.reg(0) & 0xFFFFFFFF == want)

    # --- the Death Knight eye glow ---------------------------------------------
    print("\n== eye glow")
    off = group("glow")["parts"][0][0]
    site = code.address(off)
    # the Mac build tests the bit (tst w8, #4; cset wN, eq: 1 means no glow),
    # the Switch build keeps it (ubfx w21, w8, #2, #1: 1 means glow)
    kept = struct.unpack_from("<I", stock, off)[0] & 0xFFC00000 == 0x53000000
    reg = struct.unpack_from("<I", stock, off + (0 if kept else 4))[0] & 0x1F
    for which in (0, 1):
        for flags, glow_stock, glow_patched in ((0x4, 1, 1), (0x10, 0, 1), (0x14, 1, 1), (0x1, 0, 0)):
            e = emu(which)
            rec = e.alloc(0x30)
            e.w(rec + 0x28, "I", flags)
            e.run(site - 4, {0: rec}, stops=(site + (4 if kept else 8),))
            glow = bool(e.reg(reg) & 1) if kept else not (e.reg(reg) & 1)
            want = glow_patched if which else glow_stock
            check("%s: face flags %#x %s" % ("patched" if which else "stock", flags,
                  "glow" if want else "do not glow"), glow == bool(want))

    # --- interface signatures: FrameXML_CheckSignature -------------------------
    print("\n== interface signatures")
    symbol = "__Z23FrameXML_CheckSignaturePKcS0_PKhPh"
    fn = sym(symbol)
    # the stack guard's GOT slot and __stack_chk_fail's stub, from the guard
    # check on the way out, when the build has one
    try:
        guard_slot, (fails,) = page_load(code, symbol, [
            r"adrp x\d+, #" + HEX, r"ldr x\d+, \[x\d+OFF\]", r"ldr x\d+, \[x\d+\]",
            r"cmp x\d+, x\d+", r"b\.ne #" + HEX])
        stack_chk_fail, = first_after(code, symbol, fails, r"bl #" + HEX)
    except GenError:
        guard_slot = stack_chk_fail = None
    # a build made with the checks off answers 3 already: nothing is patched
    built = not group("signature")["parts"]
    for which in (0, 1):
        for case, read, size in (("no .sig file", 0, 0), ("a .sig of the wrong size", 1, 0x113)):
            e = emu(which)
            if guard_slot is not None:
                e.w(guard_slot, "Q", e.alloc(8, b"\x11" * 8))
            digest = e.alloc(16)
            sigdata = e.alloc(0x200)

            def readfile(e, read=read, size=size, sigdata=sigdata):
                e.w(e.reg(2), "Q", sigdata)
                e.w(e.reg(3), "I", size)
                return read
            e.stub(sym("__Z10SStrPrintfPcmPKcz"), "SStrPrintf")
            e.stub(sym("__ZN5SFile8ReadFileEP8SArchivePKcPPvPjjjP11SOVERLAPPED"), "SFile::ReadFile", readfile)
            e.stub(sym("__ZN5SFile6UnloadEPv"), "SFile::Unload")
            e.stub(sym("__Z7MD5InitP7MD5_CTX"), "MD5Init")
            e.stub(sym("__Z22ProcessFileForMakeSignP7MD5_CTXPKcS2_"), "ProcessFileForMakeSign")
            e.stub(sym("__Z8MD5FinalPhP7MD5_CTX"), "MD5Final")
            if stack_chk_fail is not None:
                e.stub(stack_chk_fail, "__stack_chk_fail", lambda e: e.mu.emu_stop())
            e.run(fn, {0: e.alloc(64), 1: 0, 2: e.alloc(256), 3: digest})
            names = [n for n, _a in e.calls]
            got = e.reg(0) & 0xFFFFFFFF
            valid = which or built
            want = 3 if valid else (0 if not read else 1)
            check("%s, %s: answers %d%s" % ("patched" if which else "stock", case, want,
                  " and still computes the digest" if valid else ""),
                  got == want and (("MD5Final" in names) == bool(valid))
                  and "__stack_chk_fail" not in names, "%d %s" % (got, names))

    print()
    if FAILURES:
        print("FAILED: " + ", ".join(FAILURES))
        return 1
    print("all arm64 patch checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
