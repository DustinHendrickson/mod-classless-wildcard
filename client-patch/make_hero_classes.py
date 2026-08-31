#!/usr/bin/env python3
"""
make_hero_classes.py — rewrite every class name in a 3.3.5a ChrClasses.dbc to a
single classless name ("Hero" by default), for the mod-classless-wildcard
client patch. Class names on the character-creation screen, character sheet,
/who, tooltips etc. all come from this DBC, so a DBC-only patch renames them
without touching signed interface files.

Usage:
    python3 make_hero_classes.py ChrClasses.dbc ChrClasses_hero.dbc [--name Hero]
    # then pack it:
    ./mpqtool create patch-4.MPQ 'ChrClasses_hero.dbc@DBFilesClient\\ChrClasses.dbc'

Get the original ChrClasses.dbc out of your client with:
    ./mpqtool extract "World of Warcraft/Data/enUS/locale-enUS.MPQ" \
        'DBFilesClient\\ChrClasses.dbc' ChrClasses.dbc
"""

import argparse
import struct
import sys

# AzerothCore's ChrClassesEntryfmt for 3.3.5a (DBCfmt.h). One char per 4-byte
# field: n/i = int, x = skipped int, s = string offset. The 16 's' fields are
# the localized name columns (enUS first).
CHR_CLASSES_FMT = "nxixssssssssssssssssxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxixii"

WDBC_MAGIC = b"WDBC"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--name", default="Hero", help="new name for every class (default: Hero)")
    args = parser.parse_args()

    with open(args.input, "rb") as fh:
        data = fh.read()

    if data[:4] != WDBC_MAGIC:
        print("error: not a WDBC file", file=sys.stderr)
        return 1

    record_count, field_count, record_size, string_size = struct.unpack_from("<4I", data, 4)
    header_size = 20
    records_off = header_size
    strings_off = header_size + record_count * record_size

    if field_count != len(CHR_CLASSES_FMT):
        print(f"warning: field count {field_count} != expected {len(CHR_CLASSES_FMT)} "
              f"(client build mismatch?) — proceeding by format string anyway", file=sys.stderr)
    if record_size != field_count * 4:
        print(f"error: unexpected record size {record_size} for {field_count} fields", file=sys.stderr)
        return 1

    old_strings = data[strings_off:strings_off + string_size]

    def read_cstr(offset: int) -> str:
        end = old_strings.find(b"\0", offset)
        return old_strings[offset:end].decode("utf-8", "replace") if end >= 0 else ""

    # Preserve the ORIGINAL string block untouched and append the new name at
    # the end. Other columns (the internal class token like "WARRIOR" that the
    # client and addons key colors/icons off, pet name tokens, ...) also hold
    # offsets into this block — rebuilding it minimally would orphan them.
    new_name_bytes = args.name.encode("utf-8") + b"\0"
    name_offset = len(old_strings)
    new_strings = bytes(old_strings) + new_name_bytes

    string_field_indexes = [i for i, ch in enumerate(CHR_CLASSES_FMT) if ch == "s"]

    records = bytearray(data[records_off:strings_off])
    renamed = []
    for rec in range(record_count):
        base = rec * record_size
        class_id = struct.unpack_from("<I", records, base)[0]
        old = struct.unpack_from("<I", records, base + string_field_indexes[0] * 4)[0]
        renamed.append((class_id, read_cstr(old)))
        for field_index in string_field_indexes:
            struct.pack_into("<I", records, base + field_index * 4, name_offset)

    header = WDBC_MAGIC + struct.pack("<4I", record_count, field_count, record_size, len(new_strings))
    with open(args.output, "wb") as fh:
        fh.write(header + bytes(records) + new_strings)

    for class_id, old_name in renamed:
        print(f"class {class_id:2}: {old_name or '?':<14} -> {args.name}")
    print(f"wrote {args.output} ({record_count} classes renamed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
