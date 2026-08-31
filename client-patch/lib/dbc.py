"""The two DBC edits the classless client patch needs.

ChrClasses.dbc  - what every class is called on screen.
CharBaseInfo.dbc - which race/class pairs the creation screen offers.

Both are rewritten from the copy already winning in the client's archive stack,
so a community patch's version is preserved rather than reverted.
"""

from __future__ import annotations

import struct

WDBC_MAGIC = b"WDBC"

# ChrClasses.dbc, 3.3.5a build 12340: 60 uint32 fields per record.
#   0      ID
#   3      pet name token (string)
#   4-19   Name_lang, one column per locale (string)
#   20     Name_lang mask
#   21-36  NameFemale_lang        37 mask
#   38-53  NameMale_lang          54 mask
#   55     filename token, e.g. "WARRIOR" (string)  <- class colours and icons
#          key off this, so it must survive untouched
CHRCLASSES_FIELDS = 60
CHRCLASSES_NAME_COLUMNS = list(range(4, 20))
CHRCLASSES_NAME_FEMALE_COLUMNS = list(range(21, 37))
CHRCLASSES_NAME_MALE_COLUMNS = list(range(38, 54))
CHRCLASSES_TOKEN_FIELD = 55

# 3.3.5a playable races and classes. Race 9 (goblin) and class 10 are absent
# from the client's own tables and stay absent here.
PLAYABLE_RACES = (1, 2, 3, 4, 5, 6, 7, 8, 10, 11)
PLAYABLE_CLASSES = (1, 2, 3, 4, 5, 6, 7, 8, 9, 11)


class DbcError(ValueError):
    pass


def parse_header(data: bytes):
    if data[:4] != WDBC_MAGIC:
        raise DbcError("not a WDBC file (magic is %r)" % data[:4])
    record_count, field_count, record_size, string_size = struct.unpack_from(
        "<4I", data, 4)
    if record_size != field_count * 4 and record_size not in (1, 2, 3):
        raise DbcError("record size %d does not match %d fields"
                       % (record_size, field_count))
    return record_count, field_count, record_size, string_size


def read_string(strings: bytes, offset: int) -> str:
    end = strings.find(b"\0", offset)
    if end < 0:
        return ""
    return strings[offset:end].decode("utf-8", "replace")


def rename_all_classes(data: bytes, new_name: str):
    """Point every localized class-name column at a single new name.

    Returns (new_dbc_bytes, [(class_id, old_name), ...]).

    The original string block is kept intact and the new name appended, because
    other columns -- the class token especially -- hold offsets into it.
    """
    record_count, field_count, record_size, string_size = parse_header(data)
    if field_count != CHRCLASSES_FIELDS:
        raise DbcError(
            "ChrClasses.dbc has %d fields, expected %d. This client build is "
            "not the 3.3.5a layout this patch understands."
            % (field_count, CHRCLASSES_FIELDS))

    records_off = 20
    strings_off = records_off + record_count * record_size
    strings = data[strings_off:strings_off + string_size]

    name_bytes = new_name.encode("utf-8") + b"\0"
    name_offset = len(strings)
    new_strings = bytes(strings) + name_bytes

    columns = (CHRCLASSES_NAME_COLUMNS + CHRCLASSES_NAME_FEMALE_COLUMNS
               + CHRCLASSES_NAME_MALE_COLUMNS)

    records = bytearray(data[records_off:strings_off])
    renamed = []
    for index in range(record_count):
        base = index * record_size
        class_id = struct.unpack_from("<I", records, base)[0]
        old = read_string(strings, struct.unpack_from(
            "<I", records, base + CHRCLASSES_NAME_COLUMNS[0] * 4)[0])
        token = read_string(strings, struct.unpack_from(
            "<I", records, base + CHRCLASSES_TOKEN_FIELD * 4)[0])
        renamed.append((class_id, old, token))
        for column in columns:
            struct.pack_into("<I", records, base + column * 4, name_offset)

    header = WDBC_MAGIC + struct.pack("<4I", record_count, field_count,
                                      record_size, len(new_strings))
    return header + bytes(records) + new_strings, renamed


def all_race_class_combos(data: bytes):
    """Rebuild CharBaseInfo.dbc offering every race/class pair.

    Returns (new_dbc_bytes, added_count, total_count).
    """
    record_count, field_count, record_size, string_size = parse_header(data)
    if record_size != 2:
        raise DbcError("CharBaseInfo.dbc records are %d bytes, expected 2"
                       % record_size)

    existing = set()
    body = data[20:20 + record_count * record_size]
    for i in range(0, len(body), 2):
        existing.add((body[i], body[i + 1]))

    combos = [(race, klass)
              for race in PLAYABLE_RACES
              for klass in PLAYABLE_CLASSES]

    records = bytearray()
    for race, klass in combos:
        records += bytes([race, klass])

    header = WDBC_MAGIC + struct.pack("<4I", len(combos), field_count, 2, 1)
    return header + bytes(records) + b"\0", len(set(combos) - existing), len(combos)
