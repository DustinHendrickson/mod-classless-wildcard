#!/usr/bin/env python3
"""Write the Hero patch for one arm64 client build into arm64_patch.json.

    python3 gen_arm64_patch.py "B:/code/wowdecomp/bin/Mac/World of Warcraft.app"
    python3 gen_arm64_patch.py "B:/code/wowdecomp/bin/Switch/WoW.nro"

The Mac client (World of Warcraft.app) and the Switch client (WoW.nro) are
wowdecomp's arm64 builds, and every player of a realm gets the same file, as
they get the same Wow.exe. lib/exepatch.py patches Wow.exe 12340 at fixed
offsets; this finds the same places in an arm64 build and writes their offsets
and bytes for lib/armpatch.py to apply on the player's machine.

Each site is found by its function's symbol and an exact run of instructions
inside it, which must be there the expected number of times. A site may have
several forms (the Mac and Switch compilers lay some of them out differently);
the first form whose every part is found is used, or nothing is written. A
form may also be a change the build already has, like the Switch build's
interface signature checks being off. Edits that need more room than they
replace branch to a cave: code in executable padding the build leaves unused
(between the load commands and the first section of a Mac app, at the end of
an NRO's code segment). Run this again on every new build before players get
it, then test_arm64_patch.py on it: a pattern can still match where a register
a cave borrows has become live, and only running the code shows that.

A Mac app keeps its symbols. An NRO does not: give the Wow.elf the same build
wrote next to it (found beside the .nro, or --elf). Maintainers only: needs
`pip install capstone keystone-engine`. Players' installs read
arm64_patch.json with the standard library alone.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import os
import plistlib
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from lib import armpatch, elf, exepatch, macho, nro  # noqa: E402
from lib.framexml import HERO_RGB  # noqa: E402

FILL_FIRST_ID = exepatch.FILL_FIRST_ID
HEX = r"(0x[0-9a-f]+)"


class GenError(Exception):
    pass


class Code:
    """A run of instructions in one function. `pattern` holds a regex per
    instruction, matched whole against capstone's "mnemonic operands" text;
    `{sym:NAME}` stands for a symbol's address. `edit` is (first instruction,
    count, assembly) and the assembly may name `{at}` (the first replaced
    instruction), `{next}` (the one after the replaced run), `{end}` (the one
    after the whole run), `{@N}` (the Nth matched instruction), `{gN}` (the
    Nth regex group, in order) and `{cave:NAME}`. Only `b` and `bl` reach a
    cave: a conditional branch reaches 1 MB."""

    def __init__(self, symbol, pattern, edit, count=1, cave=None):
        self.symbol, self.pattern, self.edit, self.count, self.cave = symbol, pattern, edit, count, cave


class Data:
    """Bytes at a symbol plus an offset, or inside a unique run of stock
    bytes: (`symbol` or `find`, offset, stock hex, patched hex)."""

    def __init__(self, offset, stock, patched, symbol=None, find=None):
        self.symbol, self.find, self.offset, self.stock, self.patched = symbol, find, offset, stock, patched


class Anchor:
    """An address the form's edits name as {sym:NAME}: the `index`th
    instruction of a run found once in `symbol`."""

    def __init__(self, name, symbol, pattern, index):
        self.name, self.symbol, self.pattern, self.index = name, symbol, pattern, index


class Built:
    """The change is in the build already, shown by `text` in it once (a
    string the source only compiles in with that change)."""

    def __init__(self, text, why):
        self.text, self.why = text, why


# Caves: assembly with the same placeholders, filled from the site that uses
# them. A cave named by two sites (the Face arrows) is written once.
CAVES = {
    # tst w8, #0x14 has no arm64 encoding; w9 is dead until the next call
    "glow": "mov w9, #0x14; tst w8, w9; b {next}",
    # the same test where the glow is kept as a bit (w21 = 1 lights it)
    "glow_bit": "mov w9, #0x14; tst w8, w9; cset w21, ne; b {next}",
    # ComponentGetNumColors, then trailing copied rows (ids >= FILL_FIRST_ID)
    # and empty slots are not counted: exepatch's _FACE_COUNT
    "face_count": """
        add w8, w2, w1, lsl #1
        mov w9, #0x50
        smaddl x8, w8, w9, x0
        add x9, x8, w3, uxtw #4
        ldr x8, [x9, #8]
        cbz x8, face_count_zero
        ldr w9, [x9]
        cmp w9, w4
        ccmp w9, #1, #8, gt
        b.lt face_count_zero
        add x8, x8, w4, sxtw #4
        ldr x9, [x8, #8]
        cbz x9, face_count_zero
        ldr w0, [x8]
        mov w10, #%d
    face_count_loop:
        cmp w0, #1
        b.lt face_count_zero
        sub w11, w0, #1
        ldr x12, [x9, w11, uxtw #3]
        cbz x12, face_count_next
        ldr w13, [x12]
        cmp w13, w10
        b.lo face_count_done
    face_count_next:
        mov w0, w11
        b face_count_loop
    face_count_done:
        ret
    face_count_zero:
        mov w0, #0
        ret""" % FILL_FIRST_ID,
    # the face row's flags, or none for a copied row: exepatch's _FACE_FITS
    "face_fits": "ldr w0, [x25, #0x28]; ldr w9, [x25]; mov w10, #%d; cmp w9, w10; "
                 "csel w0, w0, wzr, lo; ret" % FILL_FIRST_ID,
    # a shaman totem category (type 2) is carried: exepatch's TOTEM_TOOL
    "totem": "ldr w9, [x8, #0x10]; cmp w9, #2; b.ne totem_bags; mov w0, #1; ret; "
             "totem_bags: sub sp, sp, #0x20; b {next}",
    # keep the prediction guard for the bar's own pool only (health keeps its
    # own path): exepatch's power sync gate. A conditional branch reaches only
    # 1 MB, so the cave is entered and left with plain branches.
    "power": "cmp w9, w8; b.gt power_take; ldr x10, [x19, #0x160]; ldrb w10, [x10, #0x47]; "
             "cmp w10, w20; b.ne power_take; b {g0}; power_take: b {end}",
}

_PALADIN = exepatch.HERO_COLOR[0][1].replace(" ", "")
_HERO = "%02X%02X%02XFF" % (HERO_RGB[2], HERO_RGB[1], HERO_RGB[0])
# the first three entries of s_classColors: none, Warrior, Paladin
_CLASS_COLORS = "000000FF" "6D9BC6FF" + _PALADIN

FERAL = [r"ldrb w8, \[x8, #0x45\]", r"cmp w8, #0xb$"]
SIG = "__Z23FrameXML_CheckSignaturePKcS0_PKhPh"
NEXT_FACE = "__ZN19CCharacterComponent11SetNextFaceE17COMPONENT_CONTEXTi"
PREV_FACE = "__ZN19CCharacterComponent11SetPrevFaceE17COMPONENT_CONTEXTi"
NUM_COLORS = "{sym:__Z21ComponentGetNumColorsP7st_raceii20COMPONENT_VARIATIONSi}"
FLAGS_MATCH = "{sym:__Z19ComponentFlagsMatchj19COMPONENT_SELECTION}"


def _fits(symbol):
    return Code(symbol, [r"cbz x25, #" + HEX, r"mov x24, x0", r"ldr w0, \[x25, #0x28\]",
                         r"mov [wx]1, [wx]20", r"bl #" + FLAGS_MATCH],
                (2, 1, "bl {cave:face_fits}"), cave="face_fits")


# (name, exepatch twin, [form, ...]): each form a list of parts, applied
# together. The first form whose every part is found is the one written.
SITES = [
    ("signature", ("INTERFACE",), [
        # every way FrameXML_CheckSignature rejects goes to its digest step
        # instead, and the answer is 3 (valid): the build's own
        # DISABLE_SIGNATURE_CHECKS path, as the Windows patch does
        [Anchor("digest", SIG, [r"ldr x0, \[sp, #0x18\]", r"ldr q0, \[x0\]", r"str q0, \[sp, #0x30\]",
                                r"bl #" + HEX, r"sub x0, x29, #0xc0"], 4),
         Code(SIG, [r"bl #" + HEX, r"cbz w0, #" + HEX, r"ldr w8, \[sp, #0x14\]", r"cmp w8, #0x114"],
              (1, 1, "cbz w0, {sym:digest}")),
         Code(SIG, [r"ldr x0, \[sp, #0x18\]", r"bl #" + HEX, r"mov w0, #1$"], (2, 1, "b {sym:digest}")),
         Code(SIG, [r"cmp x8, #0$", r"mov w8, #2$", r"cinc w0, w8, eq"], (1, 2, "mov w0, #3; nop"))],
        # the Switch build is made with the checks off
        [Built(b"signature check OFF (built with WOWDECOMP_DISABLE_SIGNATURE_CHECKS",
               "built with WOWDECOMP_DISABLE_SIGNATURE_CHECKS: unsigned interface files load")],
    ]),
    ("glow", ("GLOW",), [
        [Code("__ZN19CCharacterComponent14GeosRenderPrepEv",
              [r"ldr w8, \[x0, #0x28\]", r"tst w8, #4$", r"cset w\d+, eq"],
              (1, 1, "b {cave:glow}"), cave="glow")],
        [Code("__ZN19CCharacterComponent14GeosRenderPrepEv",
              [r"ldrb w8, \[x0, #0x28\]", r"ubfx w21, w8, #2, #1", r"b #" + HEX],
              (1, 1, "b {cave:glow_bit}"), cave="glow_bit")],
    ]),
    ("face-arrow", ("FACE_ARROW",), [
        [Code(symbol, [r"mov x4, x21", r"bl #" + NUM_COLORS, r"cmp w0, #1$"],
              (1, 1, "bl {cave:face_count}"), cave="face_count")
         for symbol in (NEXT_FACE, PREV_FACE)] + [_fits(NEXT_FACE), _fits(PREV_FACE)],
        [Code(symbol, [r"mov w4, w21", r"ldp w1, w2, \[x19, #0x20\]", r"bl #" + NUM_COLORS, r"cmp w0, #1$"],
              (2, 1, "bl {cave:face_count}"), cave="face_count")
         for symbol in (NEXT_FACE, PREV_FACE)] + [_fits(NEXT_FACE), _fits(PREV_FACE)],
    ]),
    ("totem", ("TOTEM_TOOL",), [
        [Code("__ZN7CGBag_C17FindTotemCategoryEij", [r"cbz x8, #" + HEX, r"sub sp, sp, #0x20"],
              (1, 1, "b {cave:totem}"), cave="totem")],
    ]),
    ("rune", ("RUNE",), [
        [Code("__ZN8CGUnit_C12DoPowerRegenEj",
              [r"cmp w21, #6$", r"ccmp x8, x0, #0, eq", r"b\.ne #" + HEX], (1, 1, "cmp x8, x0"))],
        [Code("__ZN8CGUnit_C12DoPowerRegenEj",
              [r"cmp w21, #6$", r"b\.ne #" + HEX, r"ldr x8, \[x19\]", r"cmp x8, x0", r"b\.ne #" + HEX],
              (1, 1, "nop"))],
    ]),
    ("combo", ("CLASS_GATES", 0), [
        [Code("__Z21Script_GetComboPointsP9lua_State",
              [r"cmp w8, #0xb$", r"ccmp w8, #4, #4, ne", r"b\.ne #" + HEX], (2, 1, "nop"))],
        [Code("__Z21Script_GetComboPointsP9lua_State",
              [r"cmp w8, #0xb$", r"b\.eq #" + HEX, r"movi d0, #0000000000000000", r"cmp w8, #4$",
               r"b\.ne #" + HEX], (4, 1, "nop"))],
    ]),
    ("regen", ("CLASS_GATES", 1), [
        [Code("__ZN8CGUnit_C12DoPowerRegenEj",
              [r"ldrb w8, \[x8, #0x45\]", r"cmp w8, #0xb$", r"b\.ne #" + HEX], (2, 1, "nop"))],
    ]),
    ("cangainxp", ("CLASS_GATES", 2), [
        # a hunter pet is told by its focus bar, not by a Hunter owner
        [Code("__ZNK8CGUnit_C9CanGainXPEv",
              [r"cbz w9, #" + HEX, r"ldr x0, \[x8, #0x28\]", r"adrp x2, #" + HEX,
               r"add x2, x2, #" + HEX, r"mov w1, #0x10$", r"mov w3, #" + HEX],
              (1, 5, "ldrb w8, [x8, #0x47]; cmp w8, #2; cset w0, eq; ldp x29, x30, [sp], #0x10; ret"))],
    ]),
    ("personality", ("CLASS_GATES", 3), [
        [Code("__ZNK8CGUnit_C17GetPetPersonalityEv",
              [r"cbz w9, #" + HEX, r"ldr x0, \[x8, #0x28\]", r"adrp x2, #" + HEX,
               r"add x2, x2, #" + HEX, r"mov w1, #0x10$", r"mov w3, #" + HEX, r"bl #" + HEX,
               r"cbz x0, #" + HEX, r"ldr x8, \[x0, #0x160\]", r"ldrb w8, \[x8, #0x45\]",
               r"cmp w8, #3$", r"b\.ne #" + HEX, r"adrp x9, #" + HEX],
              (1, 4, "ldrb w8, [x8, #0x47]; cmp w8, #2; b.ne {g0}; b {@12}"))],
    ]),
    ("track-poisons", ("CLASS_GATES", 4), [
        [Data(2 * 32 + 24, "10000000", "00000000", symbol="__ZN14CGMinimapFrame15s_trackingTypesE")]]),
    ("track-ammo", ("CLASS_GATES", 5), [
        [Data(3 * 32 + 24, "1A000000", "00000000", symbol="__ZN14CGMinimapFrame15s_trackingTypesE")]]),
    ("track-stable", ("CLASS_GATES", 6), [
        [Data(7 * 32 + 24, "08000000", "00000000", symbol="__ZN14CGMinimapFrame15s_trackingTypesE")]]),
    ("feral-dps", ("CLASS_GATES", 7), [
        [Code("__ZN18CGItemStatsSummary17AccumulateDpsStatEPK11ItemStats_C", FERAL, (1, 1, "cmp w8, #2"))]]),
    ("feral-scaling", ("CLASS_GATES", 8), [
        [Code("__ZN18CGItemStatsSummary18FillOutScalingItemEPK11ItemStats_Ci", FERAL, (1, 1, "cmp w8, #2"))]]),
    ("feral-line", ("CLASS_GATES", 9), [
        # the Mac compiler copied the Druid test into each path to the line
        [Code("__ZN9CGTooltip7SetItemEiPK7WOWGUIDS2_iiiiS0_iP7__sFILEiPK12ItemLinkInfoiii",
              FERAL, (1, 1, "cmp w8, #2"), count=4)],
        [Code("__ZN9CGTooltip7SetItemEiPK7WOWGUIDS2_iiiiS0_iP7__sFILEiPK12ItemLinkInfoiii",
              FERAL + [r"b\.ne #" + HEX], (1, 1, "cmp w8, #2"))],
    ]),
    ("reagent", ("CLASS_GATES", 10), [
        [Code("__Z24Spell_C_HasNoReagentCostP10CGPlayer_CPK8SpellRec",
              [r"cmp w8, #0$", r"ccmp w8, w9, #0, ne", r"b\.eq #" + HEX], (1, 2, "nop; b.ne {g0}"))],
        [Code("__Z24Spell_C_HasNoReagentCostP10CGPlayer_CPK8SpellRec",
              [r"cbz w9, #" + HEX, r"adrp x10, #" + HEX, r"ldr w10, \[x10, #" + HEX + r"\]",
               r"cmp w9, w10", r"b\.ne #" + HEX], (4, 1, "nop"))],
    ]),
    ("relic", ("CLASS_GATES", 11), [
        [Code("__ZN8CGItem_C11CanGoInSlotEiji",
              [r"cmp x8, #0x1c", r"cset w9, eq", r"cmp w9, w20", r"b\.ne #" + HEX], (3, 1, "nop"))],
    ]),
    ("power-sync", ("CLASS_GATES", 12), [
        [Code("__Z22UnitPowerUpdateHandler7WOWGUIDjjPKvPv",
              [r"ldr w8, \[x8, #0x1818\]", r"cmp w9, w8", r"b\.le #" + HEX],
              (1, 1, "b {cave:power}"), cave="power")],
    ]),
    ("class-color", ("HERO_COLOR",), [
        # s_classColors is copied out of this constant at startup
        [Data(8, _PALADIN, _HERO, find=_CLASS_COLORS)]]),
]


# ------------------------------------------------------------------ builds

class Build:
    """One arm64 build: its bytes, symbols and functions, and the matcher and
    assembler the sites are found and written with."""

    platform = label = key = None

    def __init__(self, data):
        import capstone
        import keystone
        self.data = data
        self.cs = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        self.ks = keystone.Ks(keystone.KS_ARCH_ARM64, keystone.KS_MODE_LITTLE_ENDIAN)

    def symbol(self, name):
        """A symbol's address. Names are written as the Mac spells them; an
        ELF build has the same name without the Mach-O leading underscore."""
        for candidate in (name, name[1:] if name.startswith("_") else None):
            if candidate in self.names:
                return self.names[candidate]
        raise GenError("symbol %s is not in this build" % name)

    def function(self, name):
        start = self.symbol(name)
        end = self.function_end(start)
        base = self.file_offset(start)
        return [(ins.address, ("%s %s" % (ins.mnemonic, ins.op_str)).strip())
                for ins in self.cs.disasm(self.data[base:base + end - start], start)]

    def subst(self, text, values):
        def one(match):
            key = match.group(1)
            if key.startswith("sym:"):
                return "0x%x" % (values[key] if key in values else self.symbol(key[4:]))
            if key not in values:
                raise GenError("nothing named {%s} here" % key)
            return "0x%x" % values[key]
        return re.sub(r"\{([^}]+)\}", one, text)

    def match(self, symbol, pattern, values):
        listing = self.function(symbol)
        regexes = [re.compile(self.subst(p, values)) for p in pattern]
        hits = []
        for i in range(len(listing) - len(regexes) + 1):
            groups = []
            for rx, (_addr, text) in zip(regexes, listing[i:i + len(regexes)]):
                m = rx.fullmatch(text)
                if not m:
                    break
                groups.extend(int(g, 16) for g in m.groups())
            else:
                hits.append(([a for a, _t in listing[i:i + len(regexes)]], groups))
        return hits

    def assemble(self, text, addr):
        encoding, _count = self.ks.asm(text, addr)
        return bytes(encoding)


class MacBuild(Build):
    """World of Warcraft.app's executable: a Mach-O that keeps its symbols."""

    platform = "mac"

    def __init__(self, path):
        exe = armpatch.app_executable(path) if os.path.isdir(path) else path
        with open(exe, "rb") as handle:
            super().__init__(handle.read())
        self.image = macho.MachO(self.data)
        self.key = self.image.uuid
        self.names = {}
        for addr, name in self.image.symbols():
            self.names.setdefault(name, addr)
        self.starts = sorted(set(self.image.function_start_addresses()))
        app = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(exe))))
        try:
            with open(os.path.join(app, "Contents", "Info.plist"), "rb") as handle:
                info = plistlib.load(handle)
            version = "%s (%s)" % (info.get("CFBundleShortVersionString"), info.get("CFBundleVersion"))
        except (OSError, ValueError):
            version = "unknown"
        self.label = "World of Warcraft.app %s" % version

    def function_end(self, start):
        i = bisect.bisect_right(self.starts, start)
        return self.starts[i] if i < len(self.starts) else start + 0x10000

    def file_offset(self, addr):
        return self.image.file_offset(addr)

    def address(self, offset):
        return self.image.address(offset)

    def cave_space(self):
        return self.image.header_padding()


class SwitchBuild(Build):
    """WoW.nro, with its symbols read from the Wow.elf the same build wrote."""

    platform = "switch"

    def __init__(self, path, elf_path=None):
        with open(path, "rb") as handle:
            super().__init__(handle.read())
        self.image = nro.Nro(self.data)
        self.key = self.image.build_id
        elf_path = elf_path or next((os.path.join(os.path.dirname(path), name)
                                     for name in os.listdir(os.path.dirname(path) or ".")
                                     if name.lower() == "wow.elf"), None)
        if not elf_path:
            raise GenError("an NRO keeps no symbols: put the Wow.elf this build wrote next to it, "
                           "or name it with --elf")
        with open(elf_path, "rb") as handle:
            symbols_file = elf.Elf(handle.read())
        if symbols_file.build_id() != self.key:
            raise GenError("%s is not from the same build as %s (build id %s, not %s)"
                           % (elf_path, path, symbols_file.build_id(), self.key))
        self.names, self.sizes = {}, {}
        for addr, size, name in symbols_file.symbols():
            self.names.setdefault(name, addr)
            self.sizes.setdefault(addr, size)
        code_va, code_memsz = symbols_file.loads[0][0], symbols_file.loads[0][1]
        self.code_used = code_va + code_memsz
        self.label = "WoW.nro (Switch) build %s" % self.key[:8]

    def function_end(self, start):
        return start + self.sizes.get(start, 0x10000)

    def file_offset(self, addr):
        return self.image.file_offset(addr)

    def address(self, offset):
        return offset

    def cave_space(self):
        return (self.code_used + 15) & ~15, self.image.code_end()


def load(path, elf_path=None):
    """The build at `path`: an app, a Mach-O executable or an NRO."""
    if os.path.isdir(path):
        return MacBuild(path)
    with open(path, "rb") as handle:
        head = handle.read(0x80)
    if nro.is_nro(head):
        return SwitchBuild(path, elf_path)
    return MacBuild(path)


# --------------------------------------------------------------- generate

def _form_found(build, form, values):
    """(code hits, data parts, notes) when every part of `form` is found in
    this build, else None."""
    local = dict(values)
    codes, datas, notes = [], [], []
    for part in form:
        if isinstance(part, Anchor):
            try:
                hits = build.match(part.symbol, part.pattern, local)
            except GenError:
                return None
            if len(hits) != 1:
                return None
            local["sym:" + part.name] = hits[0][0][part.index]
        elif isinstance(part, Built):
            if build.data.count(part.text) != 1:
                return None
            notes.append(part.why)
        elif isinstance(part, Data):
            if part.symbol:
                try:
                    off = build.file_offset(build.symbol(part.symbol)) + part.offset
                except GenError:
                    return None
            else:
                needle = bytes.fromhex(part.find)
                if build.data.count(needle) != 1:
                    return None
                off = build.data.find(needle) + part.offset
            if build.data[off:off + len(part.stock) // 2] != bytes.fromhex(part.stock):
                return None
            datas.append((off, part))
        else:
            try:
                hits = build.match(part.symbol, part.pattern, local)
            except GenError:
                return None
            if len(hits) != part.count:
                return None
            codes.append((part, hits))
    return codes, datas, notes, local


def generate(build):
    """The arm64_patch.json entry for one build. Raises GenError, having
    written nothing, when a site is not found."""
    chosen = []
    cave_sizes = {}
    for name, twin, forms in SITES:
        for form in forms:
            found = _form_found(build, form, {})
            if found:
                chosen.append((name, twin, found))
                break
        else:
            raise GenError("%s: none of its %d form(s) is in this build" % (name, len(forms)))
        for part, _hits in found[0]:
            if part.cave and part.cave not in cave_sizes:
                body = re.sub(r"\{[^}]+\}", "0x0", CAVES[part.cave])
                cave_sizes[part.cave] = len(build.assemble(body, 0))

    # caves sit at the end of the free space, clear of whatever comes before
    start, end = build.cave_space()
    total = sum((size + 15) & ~15 for size in cave_sizes.values())
    cave_off = (end - total - 0x40) & ~0xF
    if cave_off < start + 0x40:
        raise GenError("there is no room for the caves (%d bytes free, %d needed)" % (end - start, total))
    caves, at = {}, cave_off
    for cave in sorted(cave_sizes):
        caves[cave] = build.address(at)
        at += (cave_sizes[cave] + 15) & ~15

    groups = []
    written_caves = set()
    for name, twin, (codes, datas, notes, local_values) in chosen:
        group = {"name": name, "twin": list(twin), "parts": []}
        if notes:
            group["built"] = "; ".join(notes)
        for part, hits in codes:
            first, count, asm = part.edit
            for addrs, groups_found in hits:
                local = dict(local_values)
                local.update({"cave:" + k: v for k, v in caves.items()})
                local.update({"at": addrs[first], "next": addrs[first] + 4 * count, "end": addrs[-1] + 4})
                local.update({"@%d" % i: a for i, a in enumerate(addrs)})
                local.update({"g%d" % i: g for i, g in enumerate(groups_found)})
                code = build.assemble(build.subst(asm, local), addrs[first])
                if len(code) != 4 * count:
                    raise GenError("%s: the edit is %d bytes for %d replaced" % (name, len(code), 4 * count))
                off = build.file_offset(addrs[first])
                group["parts"].append([off, build.data[off:off + len(code)].hex().upper(), code.hex().upper()])
                if part.cave and part.cave not in written_caves:
                    written_caves.add(part.cave)
                    cave_addr = caves[part.cave]
                    body = build.assemble(build.subst(CAVES[part.cave], local), cave_addr)
                    coff = build.file_offset(cave_addr)
                    stock = build.data[coff:coff + len(body)]
                    if stock.strip(b"\0"):
                        raise GenError("the cave for %s is not empty in this build" % part.cave)
                    group["parts"].append([coff, stock.hex().upper(), body.hex().upper()])
        for off, part in datas:
            group["parts"].append([off, part.stock.upper(), part.patched.upper()])
        groups.append(group)

    claimed = sorted((off, off + len(stock) // 2, g["name"])
                     for g in groups for off, stock, _p in g["parts"])
    for (_a0, a1, n0), (b0, _b1, n1) in zip(claimed, claimed[1:]):
        if a1 > b0:
            raise GenError("%s and %s overlap" % (n0, n1))
    return {
        "platform": build.platform,
        "key": build.key,
        "label": build.label,
        "sha256": hashlib.sha256(build.data).hexdigest(),
        "size": len(build.data),
        "caves": {k: "%#x" % v for k, v in sorted(caves.items())},
        "groups": groups,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("build", help="World of Warcraft.app (or its executable), or WoW.nro: a stock build")
    parser.add_argument("--elf", help="the Wow.elf of an NRO build, when it is not next to the .nro")
    parser.add_argument("--check", action="store_true",
                        help="only say whether arm64_patch.json already holds this build")
    args = parser.parse_args(argv)
    try:
        entry = generate(load(args.build, args.elf))
    except (GenError, macho.MachOError, nro.NroError, elf.ElfError, OSError) as error:
        print("Not written: %s" % error)
        return 1
    manifest = armpatch.load_manifest()
    old = [b for b in manifest["builds"] if b["key"] == entry["key"]]
    if args.check:
        same = bool(old) and old[0] == entry
        print("%s: %s" % (entry["key"], "in arm64_patch.json and current" if same
                          else "in arm64_patch.json but different" if old else "not in arm64_patch.json"))
        return 0 if same else 1
    manifest["builds"] = [b for b in manifest["builds"] if b["key"] != entry["key"]] + [entry]
    armpatch.save_manifest(manifest)
    parts = sum(len(g["parts"]) for g in entry["groups"])
    print("%s %s: %d groups, %d parts, caves at %s -> %s"
          % (entry["label"], entry["key"], len(entry["groups"]), parts,
             ", ".join("%s %s" % kv for kv in entry["caves"].items()), armpatch.MANIFEST))
    for group in entry["groups"]:
        if group.get("built"):
            print("  %s: nothing to patch, %s" % (group["name"], group["built"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
