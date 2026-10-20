"""Just enough of the Mach-O format to patch the Mac client.

The Mac client is World of Warcraft.app, wowdecomp's macOS build: a 64-bit
arm64 Mach-O executable, or a universal file holding one. This reads where its
arm64 slice sits, its build UUID, its segments and sections, its symbols and
its function starts. Nothing here writes. Standard library only, so the
installer can run it on any Mac.
"""

from __future__ import annotations

import struct

MH_MAGIC_64 = 0xFEEDFACF
FAT_MAGIC = 0xCAFEBABE
FAT_MAGIC_64 = 0xCAFEBABF
CPU_TYPE_ARM64 = 0x0100000C

LC_SEGMENT_64 = 0x19
LC_SYMTAB = 0x2
LC_UUID = 0x1B
LC_CODE_SIGNATURE = 0x1D
LC_FUNCTION_STARTS = 0x26


class MachOError(Exception):
    """Not an arm64 Mach-O executable this reader understands."""


class Section:
    def __init__(self, segment, name, addr, size, offset):
        self.segment, self.name, self.addr, self.size, self.offset = segment, name, addr, size, offset


class Segment:
    def __init__(self, name, vmaddr, vmsize, fileoff, filesize, initprot):
        self.name, self.vmaddr, self.vmsize = name, vmaddr, vmsize
        self.fileoff, self.filesize, self.initprot = fileoff, filesize, initprot
        self.sections = []


def _cstr(raw):
    return raw.split(b"\0", 1)[0].decode("ascii", "replace")


def arm64_slice(data):
    """File offset of the arm64 image: 0 for a thin file, the slice's offset
    in a universal one."""
    if len(data) < 32:
        raise MachOError("too short to be a Mach-O file")
    magic_be = struct.unpack_from(">I", data, 0)[0]
    if magic_be in (FAT_MAGIC, FAT_MAGIC_64):
        count = struct.unpack_from(">I", data, 4)[0]
        wide = magic_be == FAT_MAGIC_64
        for i in range(count):
            if wide:
                cpu, _sub, offset, _size, _align, _r = struct.unpack_from(">iiQQII", data, 8 + i * 32)
            else:
                cpu, _sub, offset, _size, _align = struct.unpack_from(">iiIII", data, 8 + i * 20)
            if cpu == CPU_TYPE_ARM64:
                return offset
        raise MachOError("this universal file has no arm64 code")
    if struct.unpack_from("<I", data, 0)[0] != MH_MAGIC_64:
        raise MachOError("not a 64-bit Mach-O file")
    return 0


class MachO:
    """The arm64 image in `data`. File offsets it reports are offsets in the
    whole file (slice offset included), so they can be written to directly."""

    def __init__(self, data):
        self.data = data
        self.base = base = arm64_slice(data)
        magic, cpu, _sub, _ftype, ncmds, sizeofcmds, _flags, _r = struct.unpack_from("<IiiIIIII", data, base)
        if magic != MH_MAGIC_64 or cpu != CPU_TYPE_ARM64:
            raise MachOError("not an arm64 Mach-O image")
        self.header_end = base + 32 + sizeofcmds
        self.segments = []
        self.uuid = None
        self.symtab = None
        self.function_starts = None
        self.code_signature = None
        offset = base + 32
        for _ in range(ncmds):
            cmd, size = struct.unpack_from("<II", data, offset)
            if cmd == LC_SEGMENT_64:
                name = _cstr(data[offset + 8:offset + 24])
                vmaddr, vmsize, fileoff, filesize, _maxprot, initprot, nsects, _fl = \
                    struct.unpack_from("<QQQQiiII", data, offset + 24)
                segment = Segment(name, vmaddr, vmsize, base + fileoff, filesize, initprot)
                for i in range(nsects):
                    at = offset + 72 + i * 80
                    sectname = _cstr(data[at:at + 16])
                    addr, sec_size, sec_off = struct.unpack_from("<QQI", data, at + 32)
                    segment.sections.append(Section(name, sectname, addr, sec_size,
                                                    base + sec_off if sec_off else 0))
                self.segments.append(segment)
            elif cmd == LC_UUID:
                self.uuid = data[offset + 8:offset + 24].hex()
            elif cmd == LC_SYMTAB:
                self.symtab = struct.unpack_from("<IIII", data, offset + 8)
            elif cmd == LC_FUNCTION_STARTS:
                self.function_starts = struct.unpack_from("<II", data, offset + 8)
            elif cmd == LC_CODE_SIGNATURE:
                self.code_signature = struct.unpack_from("<II", data, offset + 8)
            offset += size

    def segment(self, name):
        for segment in self.segments:
            if segment.name == name:
                return segment
        raise MachOError("no %s segment" % name)

    def section(self, segname, sectname):
        for section in self.segment(segname).sections:
            if section.name == sectname:
                return section
        raise MachOError("no %s,%s section" % (segname, sectname))

    def text_base(self):
        return self.segment("__TEXT").vmaddr

    def file_offset(self, addr):
        """File offset of a virtual address inside a segment's file data."""
        for segment in self.segments:
            if segment.vmaddr <= addr < segment.vmaddr + segment.filesize:
                return segment.fileoff + (addr - segment.vmaddr)
        raise MachOError("address %#x is not in the file" % addr)

    def address(self, file_offset):
        for segment in self.segments:
            if segment.fileoff <= file_offset < segment.fileoff + segment.filesize:
                return segment.vmaddr + (file_offset - segment.fileoff)
        raise MachOError("file offset %#x is in no segment" % file_offset)

    def header_padding(self):
        """(start, end) file offsets of the zero bytes between the load
        commands and the first section of __TEXT. They are mapped with the
        rest of __TEXT, executable, and nothing uses them."""
        first = min(s.offset for s in self.segment("__TEXT").sections if s.offset)
        return self.header_end, first

    def symbols(self):
        """[(address, name)] for every defined symbol."""
        if not self.symtab:
            return []
        symoff, nsyms, stroff, strsize = self.symtab
        symoff += self.base
        stroff += self.base
        out = []
        for i in range(nsyms):
            strx, ntype, _sect, _desc, value = struct.unpack_from("<IBBhQ", self.data, symoff + i * 16)
            if ntype & 0xE0 or (ntype & 0x0E) != 0x0E or not value:
                continue    # debug entries, and anything not defined in a section
            out.append((value, _cstr(self.data[stroff + strx:stroff + strx + 512])))
        return out

    def function_start_addresses(self):
        """Every function start the linker recorded, as addresses."""
        if not self.function_starts:
            return []
        dataoff, datasize = self.function_starts
        at, end = self.base + dataoff, self.base + dataoff + datasize
        out, addr = [], self.text_base()
        while at < end:
            value = shift = 0
            while True:
                byte = self.data[at]
                at += 1
                value |= (byte & 0x7F) << shift
                shift += 7
                if not byte & 0x80:
                    break
            if not value:
                break
            addr += value
            out.append(addr)
        return out
