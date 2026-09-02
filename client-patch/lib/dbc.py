"""The DBC edits the classless client patch needs.

ChrClasses.dbc         - what every class is called on screen, and that it has
                         a ranged slot rather than a relic slot.
CharBaseInfo.dbc       - which race/class pairs the creation screen offers.
SkillRaceClassInfo.dbc - which class skill lines the client accepts for the
                         character, which is what decides spellbook tabs.

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
#   57     Flags, a set of class capability bits. Verified against the shipped
#          3.3.5a table, where they partition the classes exactly:
#            0x04  has a pet          Hunter, Warlock
#            0x08  RELIC slot         Paladin, Death Knight, Shaman, Druid
#            0x10  mail or better     Warrior, Paladin, Hunter, DK, Shaman
#            0x20  plate              Warrior, Paladin, Death Knight
#            0x40  hero class         Death Knight
CHRCLASSES_FLAGS_FIELD = 57
CHRCLASSES_FLAG_RELIC_SLOT = 0x08

# 3.3.5a playable races and classes. Race 9 (goblin) and class 10 are absent
# from the client's own tables and stay absent here.
PLAYABLE_RACES = (1, 2, 3, 4, 5, 6, 7, 8, 10, 11)
PLAYABLE_CLASSES = (1, 2, 3, 4, 5, 6, 7, 8, 9, 11)

# SkillRaceClassInfo.dbc, 3.3.5a: 8 uint32 fields per record.
#   0 ID  1 SkillID  2 RaceMask  3 ClassMask  4 Flags  5 MinLevel
#   6 SkillTierID  7 SkillCostIndex
SKILLRACECLASSINFO_FIELDS = 8

# The class skill lines the SERVER already opened to every race and class, in
# data/sql/db-world/cw_world_skillraceclass.sql. The client must be opened the
# same way, because it decides spellbook tabs from its OWN copy of this table:
# a Hero given the Balance skill line by the server still gets no Balance tab
# while the client's table says Balance is for Druids. Keep this in step with
# that SQL -- selftest.py asserts the two sets are identical.
CLASS_SKILL_LINES = (
    6, 8, 26, 38, 39, 43, 44, 45, 46, 50, 51, 54, 55, 56, 78, 96, 118, 120,
    130, 134, 136, 160, 163, 172, 173, 176, 184, 198, 199, 205, 226, 227,
    228, 229, 237, 238, 239, 241, 242, 243, 244, 245, 246, 247, 252, 253,
    254, 255, 256, 257, 258, 260, 262, 263, 264, 267, 268, 269, 272, 273,
    293, 353, 354, 355, 373, 374, 375, 413, 414, 416, 418, 419, 420, 433,
    453, 473, 515, 573, 574, 593, 594, 613, 633, 770, 772, 776,
)
# Appended rows start here, matching the ids the server SQL uses, well clear
# of the client's own (max 970).
CLASS_SKILL_LINES_FIRST_ID = 990000

# How the CLIENT spells "everyone". The server's GetSkillRaceClassInfo treats a
# mask of 0 as a wildcard, and the server SQL uses 0/0 -- but that is the
# server's own convention. The shipped client table has no 0/0 row anywhere;
# Blizzard writes every-class as 0x5FF (all ten playable classes, bit = class-1)
# and every-race as 0x7FF or 0xFFFFFFFF, and the client tests the character's
# own bit. A 0/0 row is therefore invisible to it, which is exactly how the
# first cut of this patch failed: the rows were there and no tab ever drew.
ALL_CLASSES_MASK = 0x5FF
ALL_RACES_MASK = 0xFFFFFFFF


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


def clear_relic_slot(data: bytes):
    """Give every class an ordinary ranged slot instead of a relic slot.

    Slot 17 is the relic slot for Paladins, Death Knights, Shamans and Druids
    (Libram / Sigil / Totem / Idol), and the client never draws a relic on the
    character. On a classless realm every Hero runs one chassis, and the
    default chassis is Paladin -- so a Hero holding a bow or a gun was carrying
    an invisible weapon, with nothing appearing when they shot.

    Clearing ChrClasses flag 0x08 tells the client that slot is an ordinary
    ranged slot, so bows, guns and wands are drawn and the paper doll labels it
    correctly. Cleared on EVERY class, not just the chassis, because the realm
    can be configured onto any of them and each is called "Hero" anyway.

    Returns (new_dbc_bytes, [(class_id, old_flags, new_flags), ...]) listing
    only the classes that actually changed.
    """
    record_count, field_count, record_size, string_size = parse_header(data)
    if field_count != CHRCLASSES_FIELDS:
        raise DbcError(
            "ChrClasses.dbc has %d fields, expected %d. This client build is "
            "not the 3.3.5a layout this patch understands."
            % (field_count, CHRCLASSES_FIELDS))

    records_off = 20
    strings_off = records_off + record_count * record_size
    records = bytearray(data[records_off:strings_off])

    changed = []
    for index in range(record_count):
        base = index * record_size
        class_id = struct.unpack_from("<I", records, base)[0]
        offset = base + CHRCLASSES_FLAGS_FIELD * 4
        flags = struct.unpack_from("<I", records, offset)[0]
        if not (flags & CHRCLASSES_FLAG_RELIC_SLOT):
            continue
        new_flags = flags & ~CHRCLASSES_FLAG_RELIC_SLOT
        struct.pack_into("<I", records, offset, new_flags)
        changed.append((class_id, flags, new_flags))

    header = WDBC_MAGIC + struct.pack("<4I", record_count, field_count,
                                      record_size, string_size)
    return header + bytes(records) + data[strings_off:], changed


def _open_to_all(row) -> bool:
    """Does this SkillRaceClassInfo row admit every playable race and class?

    Either the client's own all-bits form, or the server's 0 wildcard -- the
    latter so a table someone already patched the old way still reads as open.
    """
    race_ok = row[2] == 0 or (row[2] & 0x7FF) == 0x7FF
    class_ok = row[3] == 0 or (row[3] & ALL_CLASSES_MASK) == ALL_CLASSES_MASK
    return race_ok and class_ok


def open_class_skill_lines(data: bytes):
    """Let every class hold every class skill line.

    The client files a spell under a spellbook tab by its skill line, but only
    draws a tab for a line its OWN SkillRaceClassInfo.dbc allows the character's
    class. The server was opened up long ago (cw_world_skillraceclass.sql) so
    a Hero can be given Balance for a rolled Moonfire -- and the client then
    ignored it, because its table still said Balance belongs to Druids. Holy
    drew a tab only because the chassis is a Paladin.

    Mirror the server's intent, in the client's own dialect: for each line in
    CLASS_SKILL_LINES append one row whose RaceMask and ClassMask cover every
    playable race and class the way Blizzard's own universal rows do (see
    ALL_CLASSES_MASK), copying Flags, MinLevel, tier and cost from the line's
    most permissive existing row so nothing else about it changes. Existing
    rows are left untouched and lines that already have an all-comers row are
    skipped, so this is idempotent over an already-patched file.

    Returns (new_dbc_bytes, [skill ids added], [skill ids already open]).
    """
    record_count, field_count, record_size, string_size = parse_header(data)
    if field_count != SKILLRACECLASSINFO_FIELDS or record_size != SKILLRACECLASSINFO_FIELDS * 4:
        raise DbcError(
            "SkillRaceClassInfo.dbc has %d fields of %d bytes, expected %d of %d. "
            "This client build is not the 3.3.5a layout this patch understands."
            % (field_count, record_size, SKILLRACECLASSINFO_FIELDS,
               SKILLRACECLASSINFO_FIELDS * 4))

    records_off = 20
    strings_off = records_off + record_count * record_size
    records = bytearray(data[records_off:strings_off])
    strings = data[strings_off:strings_off + string_size]

    by_skill = {}
    max_id = 0
    for index in range(record_count):
        row = struct.unpack_from("<8I", records, index * record_size)
        by_skill.setdefault(row[1], []).append(row)
        max_id = max(max_id, row[0])

    next_id = max(CLASS_SKILL_LINES_FIRST_ID, max_id + 1)
    added, already = [], []
    for skill in CLASS_SKILL_LINES:
        rows = by_skill.get(skill)
        if not rows:
            continue                      # not in this client's table at all
        if any(_open_to_all(r) for r in rows):
            already.append(skill)
            continue
        # most permissive existing row: fewest restrictions, lowest MinLevel
        base = sorted(rows, key=lambda r: (bin(r[3]).count("1") if r[3] else 0,
                                           r[5]))[0]
        records += struct.pack("<8I", next_id, skill, ALL_RACES_MASK, ALL_CLASSES_MASK,
                               base[4], base[5], base[6], base[7])
        added.append(skill)
        next_id += 1

    header = WDBC_MAGIC + struct.pack("<4I", record_count + len(added),
                                      field_count, record_size, string_size)
    return header + bytes(records) + bytes(strings), added, already


def single_class_combos(data: bytes, shell_class: int):
    """Rebuild CharBaseInfo.dbc so every race offers exactly one class.

    The class list is COSMETIC on a classless realm: the server converts every
    new character to its configured chassis regardless of what the client
    sends, so offering ten renamed-to-Hero buttons would be ten copies of the
    same non-choice. One row per playable race, all pointing at one shell
    class, keeps every race creatable and removes the question.

    The shell has nothing to do with the server's chassis. The installer uses
    Warrior because vanilla already allows it for 9 of 10 races.

    Returns (new_dbc_bytes, race_count).
    """
    record_count, field_count, record_size, string_size = parse_header(data)
    if record_size != 2:
        raise DbcError("CharBaseInfo.dbc records are %d bytes, expected 2"
                       % record_size)
    if shell_class not in PLAYABLE_CLASSES:
        raise DbcError("shell class %d is not a playable 3.3.5a class"
                       % shell_class)

    records = bytearray()
    for race in PLAYABLE_RACES:
        records += bytes([race, shell_class])

    header = WDBC_MAGIC + struct.pack("<4I", len(PLAYABLE_RACES), field_count,
                                      2, 1)
    return header + bytes(records) + b"\0", len(PLAYABLE_RACES)
