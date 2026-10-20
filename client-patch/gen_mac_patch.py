#!/usr/bin/env python3
"""Write the Mac client's patch for one build into mac_patch.json.

    python3 gen_mac_patch.py "B:/code/wowdecomp/bin/Mac/World of Warcraft.app"

The Mac client is World of Warcraft.app, built from wowdecomp's macos-arm64
branch, and every player of a realm gets the same build, as they get the same
Wow.exe. lib/exepatch.py patches Wow.exe 12340 at fixed offsets; this finds the
same places in an arm64 build and writes their offsets and bytes for
lib/machopatch.py to apply on the player's Mac.

Each site is found by its function's symbol (the build keeps them) and an
exact run of instructions inside it, which must be there the expected number
of times or nothing is written. Edits that need more room than they replace
branch to a cave: code placed in the zero padding between the load commands
and the first section of __TEXT, which is mapped executable with the rest of
it. Run this again on every new build before players get it, then run
test_mac_patch.py on it: a pattern can still match where a register the cave
borrows has become live, and only running the code shows that.

Maintainers only: needs `pip install capstone keystone-engine` and the build.
Players' installs read mac_patch.json with the standard library alone.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import plistlib
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from lib import exepatch, machopatch, macho  # noqa: E402
from lib.framexml import HERO_RGB  # noqa: E402

FILL_FIRST_ID = exepatch.FILL_FIRST_ID
HEX = r"(0x[0-9a-f]+)"


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


# Caves: assembly with the same placeholders, filled from the site that uses
# them. A cave named by two sites (the Face arrows) is written once.
CAVES = {
    # tst w8, #0x14 has no arm64 encoding; w9 is dead until the next call
    "glow": "mov w9, #0x14; tst w8, w9; b {next}",
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

# (name, exepatch twin, [Code or Data, ...]): one group, applied together
SITES = [
    ("signature", ("INTERFACE",), [
        # every way FrameXML_CheckSignature rejects goes to its digest step
        # instead, and the answer is 3 (valid): the build's own
        # DISABLE_SIGNATURE_CHECKS path, as the Windows patch does
        Code("__Z23FrameXML_CheckSignaturePKcS0_PKhPh",
             [r"bl #" + HEX, r"cbz w0, #" + HEX, r"ldr w8, \[sp, #0x14\]", r"cmp w8, #0x114"],
             (1, 1, "cbz w0, {sym:digest}")),
        Code("__Z23FrameXML_CheckSignaturePKcS0_PKhPh",
             [r"ldr x0, \[sp, #0x18\]", r"bl #" + HEX, r"mov w0, #1$"],
             (2, 1, "b {sym:digest}")),
        Code("__Z23FrameXML_CheckSignaturePKcS0_PKhPh",
             [r"cmp x8, #0$", r"mov w8, #2$", r"cinc w0, w8, eq"],
             (1, 2, "mov w0, #3; nop")),
    ]),
    ("glow", ("GLOW",), [
        Code("__ZN19CCharacterComponent14GeosRenderPrepEv",
             [r"ldr w8, \[x0, #0x28\]", r"tst w8, #4$", r"cset w\d+, eq"],
             (1, 1, "b {cave:glow}"), cave="glow"),
    ]),
    ("face-arrow", ("FACE_ARROW",), [
        Code(symbol, [r"mov x4, x21", r"bl #{sym:__Z21ComponentGetNumColorsP7st_raceii20COMPONENT_VARIATIONSi}",
                      r"cmp w0, #1$"],
             (1, 1, "bl {cave:face_count}"), cave="face_count")
        for symbol in ("__ZN19CCharacterComponent11SetNextFaceE17COMPONENT_CONTEXTi",
                       "__ZN19CCharacterComponent11SetPrevFaceE17COMPONENT_CONTEXTi")
    ] + [
        Code(symbol, [r"cbz x25, #" + HEX, r"mov x24, x0", r"ldr w0, \[x25, #0x28\]", r"mov x1, x20",
                      r"bl #{sym:__Z19ComponentFlagsMatchj19COMPONENT_SELECTION}"],
             (2, 1, "bl {cave:face_fits}"), cave="face_fits")
        for symbol in ("__ZN19CCharacterComponent11SetNextFaceE17COMPONENT_CONTEXTi",
                       "__ZN19CCharacterComponent11SetPrevFaceE17COMPONENT_CONTEXTi")
    ]),
    ("totem", ("TOTEM_TOOL",), [
        Code("__ZN7CGBag_C17FindTotemCategoryEij", [r"cbz x8, #" + HEX, r"sub sp, sp, #0x20"],
             (1, 1, "b {cave:totem}"), cave="totem"),
    ]),
    ("rune", ("RUNE",), [
        Code("__ZN8CGUnit_C12DoPowerRegenEj",
             [r"cmp w21, #6$", r"ccmp x8, x0, #0, eq", r"b\.ne #" + HEX],
             (1, 1, "cmp x8, x0")),
    ]),
    ("combo", ("CLASS_GATES", 0), [
        Code("__Z21Script_GetComboPointsP9lua_State",
             [r"cmp w8, #0xb$", r"ccmp w8, #4, #4, ne", r"b\.ne #" + HEX],
             (2, 1, "nop")),
    ]),
    ("regen", ("CLASS_GATES", 1), [
        Code("__ZN8CGUnit_C12DoPowerRegenEj",
             [r"ldrb w8, \[x8, #0x45\]", r"cmp w8, #0xb$", r"b\.ne #" + HEX],
             (2, 1, "nop")),
    ]),
    ("cangainxp", ("CLASS_GATES", 2), [
        # a hunter pet is told by its focus bar, not by a Hunter owner
        Code("__ZNK8CGUnit_C9CanGainXPEv",
             [r"cbz w9, #" + HEX, r"ldr x0, \[x8, #0x28\]", r"adrp x2, #" + HEX,
              r"add x2, x2, #" + HEX, r"mov w1, #0x10$", r"mov w3, #" + HEX],
             (1, 5, "ldrb w8, [x8, #0x47]; cmp w8, #2; cset w0, eq; ldp x29, x30, [sp], #0x10; ret")),
    ]),
    ("personality", ("CLASS_GATES", 3), [
        Code("__ZNK8CGUnit_C17GetPetPersonalityEv",
             [r"cbz w9, #" + HEX, r"ldr x0, \[x8, #0x28\]", r"adrp x2, #" + HEX,
              r"add x2, x2, #" + HEX, r"mov w1, #0x10$", r"mov w3, #" + HEX, r"bl #" + HEX,
              r"cbz x0, #" + HEX, r"ldr x8, \[x0, #0x160\]", r"ldrb w8, \[x8, #0x45\]",
              r"cmp w8, #3$", r"b\.ne #" + HEX, r"adrp x9, #" + HEX],
             (1, 4, "ldrb w8, [x8, #0x47]; cmp w8, #2; b.ne {g0}; b {@12}")),
    ]),
    ("track-poisons", ("CLASS_GATES", 4), [
        Data(2 * 32 + 24, "10000000", "00000000", symbol="__ZN14CGMinimapFrame15s_trackingTypesE")]),
    ("track-ammo", ("CLASS_GATES", 5), [
        Data(3 * 32 + 24, "1A000000", "00000000", symbol="__ZN14CGMinimapFrame15s_trackingTypesE")]),
    ("track-stable", ("CLASS_GATES", 6), [
        Data(7 * 32 + 24, "08000000", "00000000", symbol="__ZN14CGMinimapFrame15s_trackingTypesE")]),
    ("feral-dps", ("CLASS_GATES", 7), [
        Code("__ZN18CGItemStatsSummary17AccumulateDpsStatEPK11ItemStats_C", FERAL, (1, 1, "cmp w8, #2"))]),
    ("feral-scaling", ("CLASS_GATES", 8), [
        Code("__ZN18CGItemStatsSummary18FillOutScalingItemEPK11ItemStats_Ci", FERAL, (1, 1, "cmp w8, #2"))]),
    ("feral-line", ("CLASS_GATES", 9), [
        # the compiler copied the Druid test into each path to the line
        Code("__ZN9CGTooltip7SetItemEiPK7WOWGUIDS2_iiiiS0_iP7__sFILEiPK12ItemLinkInfoiii",
             FERAL, (1, 1, "cmp w8, #2"), count=4)]),
    ("reagent", ("CLASS_GATES", 10), [
        Code("__Z24Spell_C_HasNoReagentCostP10CGPlayer_CPK8SpellRec",
             [r"cmp w8, #0$", r"ccmp w8, w9, #0, ne", r"b\.eq #" + HEX],
             (1, 2, "nop; b.ne {g0}")),
    ]),
    ("relic", ("CLASS_GATES", 11), [
        Code("__ZN8CGItem_C11CanGoInSlotEiji",
             [r"cmp x8, #0x1c", r"cset w9, eq", r"cmp w9, w20", r"b\.ne #" + HEX],
             (3, 1, "nop")),
    ]),
    ("power-sync", ("CLASS_GATES", 12), [
        Code("__Z22UnitPowerUpdateHandler7WOWGUIDjjPKvPv",
             [r"ldr w8, \[x8, #0x1818\]", r"cmp w9, w8", r"b\.le #" + HEX],
             (1, 1, "b {cave:power}"), cave="power"),
    ]),
    ("class-color", ("HERO_COLOR",), [
        # s_classColors is copied out of this constant at startup
        Data(8, _PALADIN, _HERO, find=_CLASS_COLORS)]),
]

# The signature group's edits jump to the digest step, found by its own run.
ANCHORS = {
    "digest": ("__Z23FrameXML_CheckSignaturePKcS0_PKhPh",
               [r"ldr x0, \[sp, #0x18\]", r"ldr q0, \[x0\]", r"str q0, \[sp, #0x30\]",
                r"bl #" + HEX, r"sub x0, x29, #0xc0"], 4),
}


class GenError(Exception):
    pass


class Build:
    def __init__(self, path):
        import capstone
        import keystone
        with open(path, "rb") as handle:
            self.data = handle.read()
        self.image = macho.MachO(self.data)
        self.names = {}
        for addr, name in self.image.symbols():
            self.names.setdefault(name, addr)
        self.starts = sorted(set(self.image.function_start_addresses()))
        self.cs = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        self.ks = keystone.Ks(keystone.KS_ARCH_ARM64, keystone.KS_MODE_LITTLE_ENDIAN)

    def symbol(self, name):
        if name not in self.names:
            raise GenError("symbol %s is not in this build" % name)
        return self.names[name]

    def function(self, name):
        import bisect
        start = self.symbol(name)
        i = bisect.bisect_right(self.starts, start)
        end = self.starts[i] if i < len(self.starts) else start + 0x10000
        base = self.image.file_offset(start)
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


def generate(path):
    build = Build(path)
    values = {}
    for name, (symbol, pattern, index) in ANCHORS.items():
        hits = build.match(symbol, pattern, values)
        if len(hits) != 1:
            raise GenError("anchor %s: found %d times in %s" % (name, len(hits), symbol))
        values["sym:" + name] = hits[0][0][index]

    pad_start, pad_end = build.image.header_padding()
    # pass 1: every site found, its edit and cave sized
    found = []
    cave_sizes = {}
    for name, twin, parts in SITES:
        for part in parts:
            if isinstance(part, Data):
                continue
            hits = build.match(part.symbol, part.pattern, values)
            if len(hits) != part.count:
                raise GenError("%s: the instructions in %s are there %d time(s), expected %d"
                               % (name, part.symbol, len(hits), part.count))
            found.append((name, part, hits))
            if part.cave and part.cave not in cave_sizes:
                body = re.sub(r"\{[^}]+\}", "0x100000000", CAVES[part.cave])
                cave_sizes[part.cave] = len(build.assemble(body, 0x100000000))
    # caves sit at the end of the padding, clear of the load commands
    total = sum((size + 15) & ~15 for size in cave_sizes.values())
    cave_off = (pad_end - total - 0x40) & ~0xF
    if cave_off < pad_start + 0x100:
        raise GenError("the header padding is too small for the caves")
    caves, at = {}, cave_off
    for cave in sorted(cave_sizes):
        caves[cave] = build.image.address(at)
        at += (cave_sizes[cave] + 15) & ~15
    values.update({"cave:" + k: v for k, v in caves.items()})

    groups = {name: {"name": name, "twin": list(twin), "parts": []} for name, twin, _p in SITES}
    written_caves = set()
    for name, part, hits in found:
        first, count, asm = part.edit
        for addrs, groups_found in hits:
            local = dict(values)
            local.update({"at": addrs[first], "next": addrs[first] + 4 * count,
                          "end": addrs[-1] + 4})
            local.update({"@%d" % i: a for i, a in enumerate(addrs)})
            local.update({"g%d" % i: g for i, g in enumerate(groups_found)})
            code = build.assemble(build.subst(asm, local), addrs[first])
            if len(code) != 4 * count:
                raise GenError("%s: the edit is %d bytes for %d replaced" % (name, len(code), 4 * count))
            off = build.image.file_offset(addrs[first])
            groups[name]["parts"].append([off, build.data[off:off + len(code)].hex().upper(),
                                          code.hex().upper()])
            if part.cave and part.cave not in written_caves:
                written_caves.add(part.cave)
                cave_addr = caves[part.cave]
                body = build.assemble(build.subst(CAVES[part.cave], local), cave_addr)
                coff = build.image.file_offset(cave_addr)
                stock = build.data[coff:coff + len(body)]
                if stock.strip(b"\0"):
                    raise GenError("the cave for %s is not empty in this build" % part.cave)
                groups[name]["parts"].append([coff, stock.hex().upper(), body.hex().upper()])
    for name, twin, parts in SITES:
        for part in parts:
            if not isinstance(part, Data):
                continue
            if part.symbol:
                off = build.image.file_offset(build.symbol(part.symbol)) + part.offset
            else:
                needle = bytes.fromhex(part.find)
                if build.data.count(needle) != 1:
                    raise GenError("%s: the stock bytes are there %d times"
                                   % (name, build.data.count(needle)))
                off = build.data.find(needle) + part.offset
            stock = bytes.fromhex(part.stock)
            if build.data[off:off + len(stock)] != stock:
                raise GenError("%s: %s is not the stock value here" % (name, part.stock))
            groups[name]["parts"].append([off, part.stock.upper(), part.patched.upper()])

    claimed = []
    for group in groups.values():
        for off, stock, _patched in group["parts"]:
            claimed.append((off, off + len(stock) // 2, group["name"]))
    claimed.sort()
    for (a0, a1, n0), (b0, _b1, n1) in zip(claimed, claimed[1:]):
        if a1 > b0:
            raise GenError("%s and %s overlap" % (n0, n1))

    app = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(path))))
    try:
        with open(os.path.join(app, "Contents", "Info.plist"), "rb") as handle:
            info = plistlib.load(handle)
        label = "%s (%s)" % (info.get("CFBundleShortVersionString"), info.get("CFBundleVersion"))
    except (OSError, ValueError):
        label = "unknown"
    return {
        "uuid": build.image.uuid,
        "label": "World of Warcraft.app %s" % label,
        "sha256": hashlib.sha256(build.data).hexdigest(),
        "size": len(build.data),
        "caves": {k: "%#x" % v for k, v in sorted(caves.items())},
        "groups": list(groups.values()),
    }


def executable_of(path):
    if path.endswith(".app") or os.path.isdir(path):
        return machopatch.app_executable(path)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("app", help="World of Warcraft.app, or the executable in it (a stock build)")
    parser.add_argument("--check", action="store_true",
                        help="only say whether mac_patch.json already holds this build")
    args = parser.parse_args(argv)
    exe = executable_of(args.app)
    try:
        entry = generate(exe)
    except (GenError, macho.MachOError) as error:
        print("Not written: %s" % error)
        return 1
    manifest = machopatch.load_manifest()
    old = [b for b in manifest["builds"] if b["uuid"] == entry["uuid"]]
    if args.check:
        same = bool(old) and old[0] == entry
        print("%s: %s" % (entry["uuid"], "in mac_patch.json and current" if same
                          else "in mac_patch.json but different" if old else "not in mac_patch.json"))
        return 0 if same else 1
    manifest["builds"] = [b for b in manifest["builds"] if b["uuid"] != entry["uuid"]] + [entry]
    machopatch.save_manifest(manifest)
    parts = sum(len(g["parts"]) for g in entry["groups"])
    print("%s %s: %d groups, %d parts, caves at %s -> %s"
          % (entry["label"], entry["uuid"], len(entry["groups"]), parts,
             ", ".join("%s %s" % kv for kv in entry["caves"].items()), machopatch.MANIFEST))
    return 0


if __name__ == "__main__":
    sys.exit(main())
