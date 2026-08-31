"""Minimal, dependency-free MPQ reader/writer for the 3.3.5a client.

Only what mod-classless-wildcard needs: pull a handful of files out of the
client's archives, and write a small patch archive back. No StormLib, no
compiler, no external packages -- players run the installer with nothing but a
stock Python 3.

Reading supports the archive features WotLK-era MPQs actually use: v1-v4
headers, >4 GiB archives via the hi-block table, encrypted files, single-unit
files, sector CRCs, and zlib / bzip2 / PKWARE-DCL / stored sectors.

Writing deliberately emits the simplest thing the client accepts: a v1 archive
whose files are stored uncompressed and unencrypted. Our payloads are a few
hundred KiB at most, so compression buys nothing and every byte of it would be
another way to be subtly wrong.
"""

from __future__ import annotations

import bz2
import os
import struct
import zlib

from . import pkware

MPQ_MAGIC = b"MPQ\x1a"
USERDATA_MAGIC = b"MPQ\x1b"

# block flags
FLAG_IMPLODE = 0x00000100
FLAG_COMPRESS = 0x00000200
FLAG_ENCRYPTED = 0x00010000
FLAG_FIX_KEY = 0x00020000
FLAG_PATCH_FILE = 0x00100000
FLAG_SINGLE_UNIT = 0x01000000
FLAG_DELETE_MARKER = 0x02000000
FLAG_SECTOR_CRC = 0x04000000
FLAG_EXISTS = 0x80000000

HASH_ENTRY_EMPTY = 0xFFFFFFFF
HASH_ENTRY_DELETED = 0xFFFFFFFE


def _build_crypt_table():
    table = [0] * 0x500
    seed = 0x00100001
    for i in range(0x100):
        index = i
        for _ in range(5):
            seed = (seed * 125 + 3) % 0x2AAAAB
            temp1 = (seed & 0xFFFF) << 16
            seed = (seed * 125 + 3) % 0x2AAAAB
            temp2 = seed & 0xFFFF
            table[index] = temp1 | temp2
            index += 0x100
    return table


_CRYPT = _build_crypt_table()

HASH_TABLE_OFFSET = 0
HASH_NAME_A = 1
HASH_NAME_B = 2
HASH_FILE_KEY = 3


def mpq_hash(name: str, hash_type: int) -> int:
    """The Storm string hash. Paths are case-insensitive and slash-insensitive."""
    seed1 = 0x7FED7FED
    seed2 = 0xEEEEEEEE
    for ch in name.replace("/", "\\").upper():
        code = ord(ch)
        seed1 = _CRYPT[(hash_type << 8) + (code & 0xFF)] ^ ((seed1 + seed2) & 0xFFFFFFFF)
        seed2 = (code + seed1 + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF
    return seed1


def _crypt(data: bytes, key: int, decrypt: bool) -> bytes:
    """Storm's block cipher, operating on whole dwords."""
    count = len(data) // 4
    if count == 0:
        return data
    words = list(struct.unpack_from("<%dI" % count, data, 0))
    seed1 = key & 0xFFFFFFFF
    seed2 = 0xEEEEEEEE
    for i in range(count):
        seed2 = (seed2 + _CRYPT[0x400 + (seed1 & 0xFF)]) & 0xFFFFFFFF
        raw = words[i]
        if decrypt:
            plain = raw ^ ((seed1 + seed2) & 0xFFFFFFFF)
            words[i] = plain
        else:
            plain = raw
            words[i] = raw ^ ((seed1 + seed2) & 0xFFFFFFFF)
        seed1 = ((((~seed1) << 21) & 0xFFFFFFFF) + 0x11111111) | (seed1 >> 11)
        seed1 &= 0xFFFFFFFF
        seed2 = (plain + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF
    return struct.pack("<%dI" % count, *words) + data[count * 4:]


def decrypt(data: bytes, key: int) -> bytes:
    return _crypt(data, key, True)


def encrypt(data: bytes, key: int) -> bytes:
    return _crypt(data, key, False)


def _decompress(chunk: bytes, expected: int) -> bytes:
    """Expand one COMPRESS sector: a mask byte followed by the payload."""
    if not chunk:
        return chunk
    mask = chunk[0]
    body = chunk[1:]
    if mask & 0x02:
        return zlib.decompress(body)
    if mask & 0x10:
        return bz2.decompress(body)
    if mask & 0x08:
        return pkware.explode(body, expected)
    if mask == 0:
        # no compression flagged; the mask byte was part of the data
        return chunk
    raise NotImplementedError(
        "MPQ sector uses compression mask 0x%02x, which this reader does not "
        "implement (only zlib, bzip2 and PKWARE are supported)." % mask
    )


class MPQArchive:
    """Read-only view of one .MPQ file."""

    def __init__(self, path):
        self.path = str(path)
        self._fh = open(self.path, "rb")
        self._hash_table = None
        self._block_table = None
        self._hi_block_table = None
        try:
            self._read_header()
        except Exception:
            self._fh.close()
            raise

    # -- lifecycle -------------------------------------------------------
    def close(self):
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- header ----------------------------------------------------------
    def _read_header(self):
        size = os.path.getsize(self.path)
        offset = 0
        while offset < size:
            self._fh.seek(offset)
            magic = self._fh.read(4)
            if magic == USERDATA_MAGIC:
                # skip the user data block and continue at the real header
                _, _, header_off = struct.unpack("<3I", self._fh.read(12))
                offset += header_off
                continue
            if magic == MPQ_MAGIC:
                break
            offset += 0x200
        else:
            raise ValueError("no MPQ header found in %s" % self.path)

        self.archive_offset = offset
        self._fh.seek(offset)
        head = self._fh.read(32)
        (_magic, self.header_size, self.archive_size, self.format_version,
         self.sector_shift, hash_pos, block_pos, self.hash_count,
         self.block_count) = struct.unpack("<4sIIHHIIII", head)
        self.sector_size = 512 << self.sector_shift

        self.hash_pos = offset + hash_pos
        self.block_pos = offset + block_pos
        self.hi_block_pos = 0

        if self.format_version >= 1 and self.header_size >= 44:
            self._fh.seek(offset + 32)
            hi_block_pos, hash_hi, block_hi = struct.unpack("<QHH", self._fh.read(12))
            # the high 16 bits extend the table offsets past 4 GiB
            self.hash_pos = offset + (hash_pos | (hash_hi << 32))
            self.block_pos = offset + (block_pos | (block_hi << 32))
            if hi_block_pos:
                self.hi_block_pos = offset + hi_block_pos

    # -- tables ----------------------------------------------------------
    def _load_hash_table(self):
        if self._hash_table is None:
            self._fh.seek(self.hash_pos)
            raw = self._fh.read(self.hash_count * 16)
            raw = decrypt(raw, mpq_hash("(hash table)", HASH_FILE_KEY))
            self._hash_table = raw
        return self._hash_table

    def _load_block_table(self):
        if self._block_table is None:
            self._fh.seek(self.block_pos)
            raw = self._fh.read(self.block_count * 16)
            raw = decrypt(raw, mpq_hash("(block table)", HASH_FILE_KEY))
            self._block_table = raw
        return self._block_table

    def _load_hi_block_table(self):
        if self._hi_block_table is None and self.hi_block_pos:
            self._fh.seek(self.hi_block_pos)
            self._hi_block_table = self._fh.read(self.block_count * 2)
        return self._hi_block_table

    def _find_block_index(self, name):
        table = self._load_hash_table()
        if self.hash_count == 0:
            return None
        start = mpq_hash(name, HASH_TABLE_OFFSET) & (self.hash_count - 1)
        want_a = mpq_hash(name, HASH_NAME_A)
        want_b = mpq_hash(name, HASH_NAME_B)
        for probe in range(self.hash_count):
            i = (start + probe) & (self.hash_count - 1)
            hash_a, hash_b, _locale, _platform, block_index = struct.unpack_from(
                "<IIHHI", table, i * 16)
            if block_index == HASH_ENTRY_EMPTY:
                return None
            if block_index == HASH_ENTRY_DELETED:
                continue
            if hash_a == want_a and hash_b == want_b:
                return block_index
        return None

    def _block(self, index):
        table = self._load_block_table()
        pos, csize, fsize, flags = struct.unpack_from("<4I", table, index * 16)
        hi = self._load_hi_block_table()
        if hi:
            pos |= struct.unpack_from("<H", hi, index * 2)[0] << 32
        return pos, csize, fsize, flags

    # -- reading ---------------------------------------------------------
    def has_file(self, name) -> bool:
        index = self._find_block_index(name)
        if index is None or index >= self.block_count:
            return False
        _pos, _csize, _fsize, flags = self._block(index)
        return bool(flags & FLAG_EXISTS) and not (flags & FLAG_DELETE_MARKER)

    def read_file(self, name) -> bytes:
        index = self._find_block_index(name)
        if index is None or index >= self.block_count:
            raise KeyError(name)
        pos, csize, fsize, flags = self._block(index)
        if not (flags & FLAG_EXISTS) or (flags & FLAG_DELETE_MARKER):
            raise KeyError(name)
        if flags & FLAG_PATCH_FILE:
            raise NotImplementedError(
                "%s is an incremental patch file, which this reader cannot "
                "apply. Read it from a lower-priority archive instead." % name)

        base = self.archive_offset + pos
        self._fh.seek(base)
        raw = self._fh.read(csize)

        key = None
        if flags & FLAG_ENCRYPTED:
            base_name = name.replace("/", "\\").rsplit("\\", 1)[-1]
            key = mpq_hash(base_name, HASH_FILE_KEY)
            if flags & FLAG_FIX_KEY:
                key = ((key + pos) ^ fsize) & 0xFFFFFFFF

        compressed = bool(flags & (FLAG_COMPRESS | FLAG_IMPLODE))

        if (flags & FLAG_SINGLE_UNIT) or not compressed:
            if key is not None:
                raw = decrypt(raw, key)
            if not compressed or csize == fsize:
                return raw[:fsize]
            if flags & FLAG_IMPLODE and not (flags & FLAG_COMPRESS):
                return pkware.explode(raw, fsize)
            return _decompress(raw, fsize)[:fsize]

        # sector-based file: a table of offsets, then the sectors themselves
        sector_count = (fsize + self.sector_size - 1) // self.sector_size
        entries = sector_count + 1
        if flags & FLAG_SECTOR_CRC:
            entries += 1
        table_bytes = raw[:entries * 4]
        if key is not None:
            table_bytes = decrypt(table_bytes, (key - 1) & 0xFFFFFFFF)
        offsets = struct.unpack("<%dI" % entries, table_bytes)

        out = bytearray()
        for i in range(sector_count):
            start, end = offsets[i], offsets[i + 1]
            chunk = raw[start:end]
            if key is not None:
                chunk = decrypt(chunk, (key + i) & 0xFFFFFFFF)
            remaining = fsize - len(out)
            expected = min(self.sector_size, remaining)
            if len(chunk) >= expected:
                out += chunk[:expected]
            elif flags & FLAG_IMPLODE and not (flags & FLAG_COMPRESS):
                out += pkware.explode(chunk, expected)
            else:
                out += _decompress(chunk, expected)
        return bytes(out[:fsize])


def _next_power_of_two(value: int) -> int:
    size = 16
    while size < value:
        size <<= 1
    return size


def _pack_sectors(payload: bytes, sector_size: int) -> bytes:
    """Lay a file out the way StormLib does: an offset table, then zlib sectors.

    A sector that does not actually shrink is stored raw, which is the
    convention every reader expects (compressed size == raw size means "no
    compression byte here").
    """
    count = max(1, (len(payload) + sector_size - 1) // sector_size)
    offsets = [4 * (count + 1)]
    chunks = []
    for index in range(count):
        raw = payload[index * sector_size:(index + 1) * sector_size]
        squeezed = b"\x02" + zlib.compress(raw, 9)
        chunk = squeezed if len(squeezed) < len(raw) else raw
        chunks.append(chunk)
        offsets.append(offsets[-1] + len(chunk))
    return struct.pack("<%dI" % len(offsets), *offsets) + b"".join(chunks)


def write_archive(path, files, sector_shift=3):
    """Write a v1 MPQ containing `files` ({archive path: bytes}).

    Files are unencrypted and zlib-compressed per sector -- the same layout
    StormLib emits, so anything that can read a Blizzard archive can read this.
    """
    sector_size = 512 << sector_shift
    names = list(files.keys())
    listfile = "\r\n".join(names + ["(listfile)"]).encode("utf-8")
    entries = [(name, bytes(files[name])) for name in names]
    entries.append(("(listfile)", listfile))

    hash_count = _next_power_of_two(max(16, len(entries) * 4))

    header_size = 32
    data = bytearray()
    blocks = []
    for _name, payload in entries:
        packed = _pack_sectors(payload, sector_size)
        blocks.append((header_size + len(data), len(packed), len(payload),
                       FLAG_EXISTS | FLAG_COMPRESS))
        data += packed

    # hash table: place each name at its home slot, probing forward on collision
    hash_table = bytearray(b"\xff" * (hash_count * 16))
    for i in range(hash_count):
        struct.pack_into("<IIHHI", hash_table, i * 16,
                         0xFFFFFFFF, 0xFFFFFFFF, 0xFFFF, 0xFFFF,
                         HASH_ENTRY_EMPTY)
    for block_index, (name, _payload) in enumerate(entries):
        start = mpq_hash(name, HASH_TABLE_OFFSET) & (hash_count - 1)
        for probe in range(hash_count):
            slot = (start + probe) & (hash_count - 1)
            existing = struct.unpack_from("<I", hash_table, slot * 16 + 12)[0]
            if existing == HASH_ENTRY_EMPTY:
                struct.pack_into("<IIHHI", hash_table, slot * 16,
                                 mpq_hash(name, HASH_NAME_A),
                                 mpq_hash(name, HASH_NAME_B),
                                 0, 0, block_index)
                break
        else:
            raise RuntimeError("hash table full building %s" % path)

    block_table = bytearray()
    for pos, csize, fsize, flags in blocks:
        block_table += struct.pack("<4I", pos, csize, fsize, flags)

    hash_pos = header_size + len(data)
    block_pos = hash_pos + len(hash_table)
    archive_size = block_pos + len(block_table)

    header = struct.pack("<4sIIHHIIII", MPQ_MAGIC, header_size, archive_size,
                         0, sector_shift, hash_pos, block_pos, hash_count,
                         len(blocks))

    out = bytearray(header)
    out += data
    out += encrypt(bytes(hash_table), mpq_hash("(hash table)", HASH_FILE_KEY))
    out += encrypt(bytes(block_table), mpq_hash("(block table)", HASH_FILE_KEY))

    tmp = str(path) + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(out)
    os.replace(tmp, str(path))
    return len(out)
