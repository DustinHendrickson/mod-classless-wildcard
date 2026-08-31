"""Dress the character-creation preview in the Hero starter gear.

CharStartOutfit.dbc drives the gear shown on the previewed character (by
DisplayInfoID). Left alone, the shell class (Paladin) previews in whatever a
Paladin starts with -- and that varies by race and shows a weapon. Instead this
rebuilds every Hero's shell-class row to wear exactly the neutral starter kit the
module equips at first login (Recruit's shirt/pants/boots), with no weapon,
because the module drops the starter weapons into the bag rather than equipping
them. So the creation preview matches what a new Hero actually wears.

The item ids here mirror the module's default `StarterKit.Equip`
(`38,39,40`). Their display ids and slots are resolved from the client's own
CharStartOutfit data, so nothing is invented; if a realm changes StarterKit.Equip
to different armour, update STARTER_ITEMS to match.

It also fills real gaps: the Paladin shell is only vanilla-creatable by four
races, so the other six (and any race missing a row) get a shell-class row added,
built the same way, so no Hero previews naked.

None of this needs the exe patch -- it is data. It ships with --creation-text
only to keep all the visual extras behind one flag.
"""

from __future__ import annotations

import struct

WDBC_MAGIC = b"WDBC"

# 3.3.5a CharStartOutfit record: 74 uint32.
#   [0]      ID
#   [1]      packed race/class/gender/outfit (4 bytes)
#   [2..25]  ItemID[24]
#   [26..49] DisplayInfoID[24]
#   [50..73] InventoryType[24]
_FIELDS = 74
_REC_BYTES = _FIELDS * 4
_N = 24
_ITEM = 2
_DISP = 26
_INV = 50

_RACES = (1, 2, 3, 4, 5, 6, 7, 8, 10, 11)

# The equipped starter armour, matching the module's default StarterKit.Equip:
# Recruit's Shirt (38), Recruit's Pants (39), Recruit's Boots (40). No weapon --
# the module puts the neutral starter weapons in the bag, so none is shown.
STARTER_ITEMS = (38, 39, 40)


class OutfitError(ValueError):
    pass


def _unpack_packed(v):
    return struct.unpack("<4B", struct.pack("<I", v & 0xFFFFFFFF))


def _pack_packed(race, cls, gender, outfit):
    return struct.unpack("<I", struct.pack("<4B", race, cls, gender, outfit))[0]


def build_hero_outfit(data: bytes, shell_class: int):
    """Rewrite the shell-class rows to the neutral Hero starter gear.

    Returns (new_dbc_bytes, rows_updated, rows_added).
    """
    if data[:4] != WDBC_MAGIC:
        raise OutfitError("not a WDBC file")
    record_count, field_count, record_size, string_size = struct.unpack_from(
        "<4I", data, 4)
    if record_size != _REC_BYTES:
        raise OutfitError("CharStartOutfit record is %d bytes, expected %d "
                          "(unexpected client build)" % (record_size, _REC_BYTES))

    records = [list(struct.unpack_from("<%di" % _FIELDS, data, 20 + i * record_size))
               for i in range(record_count)]

    # resolve each starter item's (display, invtype) from the client's own data
    # so we never invent a display id
    item_slot = {}
    for rec in records:
        for k in range(_N):
            item = rec[_ITEM + k]
            if item in STARTER_ITEMS and item not in item_slot:
                item_slot[item] = (rec[_DISP + k], rec[_INV + k])

    pieces = [(item, item_slot[item][0], item_slot[item][1])
              for item in STARTER_ITEMS if item in item_slot]
    if not pieces:
        raise OutfitError("none of the starter items %s were found in "
                          "CharStartOutfit -- cannot build the Hero preview"
                          % (STARTER_ITEMS,))

    def write_pieces(rec):
        for k in range(_N):
            rec[_ITEM + k] = 0
            rec[_DISP + k] = 0
            rec[_INV + k] = 0
        for k, (item, disp, inv) in enumerate(pieces):
            rec[_ITEM + k] = item
            rec[_DISP + k] = disp
            rec[_INV + k] = inv

    index = {}
    max_id = 0
    for rec in records:
        race, cls, gender, _outfit = _unpack_packed(rec[1])
        index[(race, gender, cls)] = rec
        max_id = max(max_id, rec[0])

    updated = 0
    for race in _RACES:
        for gender in (0, 1):
            rec = index.get((race, gender, shell_class))
            if rec is not None:
                write_pieces(rec)
                updated += 1

    # add a shell-class row for every race+gender that lacks one, so no Hero
    # previews naked (six races cannot be Paladins in vanilla)
    added = 0
    for race in _RACES:
        for gender in (0, 1):
            if (race, gender, shell_class) in index:
                continue
            max_id += 1
            rec = [0] * _FIELDS
            rec[0] = max_id
            rec[1] = _pack_packed(race, shell_class, gender, 0)
            write_pieces(rec)
            records.append(rec)
            added += 1

    body = b"".join(struct.pack("<%di" % _FIELDS, *rec) for rec in records)
    header = WDBC_MAGIC + struct.pack("<4I", len(records), field_count,
                                      record_size, string_size)
    strings = data[20 + record_count * record_size:
                   20 + record_count * record_size + string_size]
    return header + body + strings, updated, added
