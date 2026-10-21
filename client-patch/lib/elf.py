"""Just enough of ELF64 to read the Switch client's symbols.

A Switch build is WoW.nro, which keeps no symbol names, plus Wow.elf, the same
program with them (wowdecomp's Tools/Switch/build.sh writes both). This reads
the .elf's symbol table and loadable segments so gen_arm64_patch.py can find
functions by name. Standard library only.
"""

from __future__ import annotations

import struct

PT_LOAD = 1
SHT_SYMTAB = 2
STT_OBJECT = 1
STT_FUNC = 2
NT_GNU_BUILD_ID = 3


class ElfError(Exception):
    pass


class Elf:
    def __init__(self, data):
        if data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
            raise ElfError("not a 64-bit little-endian ELF file")
        self.data = data
        (_type, machine, _ver, _entry, phoff, shoff, _flags, _ehsize, phentsize, phnum,
         shentsize, shnum, _shstrndx) = struct.unpack_from("<HHIQQQIHHHHHH", data, 16)
        if machine != 183:
            raise ElfError("not an AArch64 ELF file")
        self.loads = []
        for i in range(phnum):
            ptype, _fl, offset, vaddr, _pa, filesz, memsz, _al = \
                struct.unpack_from("<IIQQQQQQ", data, phoff + i * phentsize)
            if ptype == PT_LOAD:
                self.loads.append((vaddr, memsz, offset, filesz))
        self.sections = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + i * shentsize)
                         for i in range(shnum)]

    def symbols(self):
        """[(address, size, name)] for every function and data symbol."""
        out = []
        for _name, stype, _fl, _addr, offset, size, link, _info, _al, entsize in self.sections:
            if stype != SHT_SYMTAB:
                continue
            stroff = self.sections[link][4]
            for at in range(offset, offset + size, entsize):
                st_name, st_info, _other, shndx, value, sym_size = struct.unpack_from("<IBBHQQ", self.data, at)
                if (st_info & 0xF) not in (STT_FUNC, STT_OBJECT) or not shndx or not value:
                    continue
                end = self.data.index(b"\0", stroff + st_name)
                out.append((value, sym_size, self.data[stroff + st_name:end].decode("ascii", "replace")))
        return out

    def build_id(self):
        """The GNU build id, as hex, or None."""
        for _name, stype, _fl, _addr, offset, size, _l, _i, _al, _e in self.sections:
            if stype != 7:          # SHT_NOTE
                continue
            at = offset
            while at + 12 <= offset + size:
                namesz, descsz, ntype = struct.unpack_from("<III", self.data, at)
                desc = at + 12 + ((namesz + 3) & ~3)
                if ntype == NT_GNU_BUILD_ID:
                    return self.data[desc:desc + descsz].hex()
                at = desc + ((descsz + 3) & ~3)
        return None
