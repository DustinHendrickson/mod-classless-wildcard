"""Just enough of the Switch homebrew NRO format to patch WoW.nro.

The Switch client is WoW.nro, wowdecomp's Switch build, in sdmc:/switch/wow
beside Data. An NRO is the program's three segments (code, read-only data,
data) stored uncompressed at their own addresses, so an address in the program
is also its offset in the file. Homebrew is not signed, so a patched NRO needs
nothing more. Standard library only.
"""

from __future__ import annotations

import struct

MAGIC = b"NRO0"


class NroError(Exception):
    pass


def is_nro(data) -> bool:
    return len(data) >= 0x80 and data[0x10:0x14] == MAGIC


class Nro:
    def __init__(self, data):
        if not is_nro(data):
            raise NroError("not a Switch NRO file")
        self.data = data
        self.size = struct.unpack_from("<I", data, 0x18)[0]
        # (offset, size) of the code, read-only and data segments
        self.segments = [struct.unpack_from("<II", data, 0x20 + 8 * i) for i in range(3)]
        raw = data[0x40:0x60]
        self.build_id = raw.rstrip(b"\0").hex() or None

    def file_offset(self, addr):
        for offset, size in self.segments:
            if offset <= addr < offset + size:
                return addr
        raise NroError("address %#x is in no segment" % addr)

    def code_end(self):
        offset, size = self.segments[0]
        return offset + size
