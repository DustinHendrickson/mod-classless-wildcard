"""Give the Hero a distinct starting look on the character-creation screen.

CharStartOutfit.dbc drives the gear shown on the previewed character (by
DisplayInfoID). The shell class (Paladin) starts in plain recruit cloth, so
every Hero would look like a peasant. This rebuilds the shell-class rows to wear
the Death Knight starting plate instead: an armored, heroic look that already
exists in the client for every race and gender, so no display IDs are invented.

Two deliberate adjustments:
  * the head slot is dropped, so the face and hair the player just customized
    stay visible (the DK set includes a full helm);
  * a two-handed weapon is kept, so the Hero is holding something.

It also fills real gaps: Paladin is only vanilla-creatable by four races, so the
other six have no Paladin CharStartOutfit row and their Heroes would appear in
underwear. A shell row is added for every race+gender that lacks one, built the
same way (from that race's own Death Knight row).

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

# Playable races (client CharStartOutfit uses these), and the classes we read
# from / write to.
_RACES = (1, 2, 3, 4, 5, 6, 7, 8, 10, 11)
_DK_CLASS = 6

# InventoryType values that show on the character model and that we keep from
# the DK set. Head (1) is deliberately excluded. Weapons are handled separately.
_VISIBLE_ARMOR = {3, 5, 6, 7, 8, 9, 10, 16}   # shoulder chest belt legs feet wrist hands back
_WEAPON_SLOTS = {13, 15, 17, 21, 22, 23, 25, 26}
_HEARTHSTONE_ITEM = 6948

# Fallback two-hander so every Hero is armed, even races with no shell-class row
# to copy a weapon from (Blood Elf). Item 49778 / display 2380 is the warrior
# starter greatsword the client already ships.
_DEFAULT_WEAPON = (49778, 2380, 17)


class OutfitError(ValueError):
    pass


def _unpack_packed(v):
    return struct.unpack("<4B", struct.pack("<I", v & 0xFFFFFFFF))


def _pack_packed(race, cls, gender, outfit):
    return struct.unpack("<I", struct.pack("<4B", race, cls, gender, outfit))[0]


def _pieces(rec):
    """[(item, display, invtype), ...] for the non-empty slots of a record."""
    out = []
    for k in range(_N):
        item = rec[_ITEM + k]
        disp = rec[_DISP + k]
        inv = rec[_INV + k]
        if item > 0 or disp > 0:
            out.append((item, disp, inv))
    return out


def build_hero_outfit(data: bytes, shell_class: int):
    """Rewrite the shell-class rows to the armored Hero look.

    Returns (new_dbc_bytes, races_updated, blood_elf_added).
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

    # index by (race, gender, class)
    index = {}
    max_id = 0
    for rec in records:
        race, cls, gender, _outfit = _unpack_packed(rec[1])
        index[(race, gender, cls)] = rec
        max_id = max(max_id, rec[0])

    def hero_pieces(race, gender):
        dk = index.get((race, gender, _DK_CLASS))
        if not dk:
            return None
        pieces = [p for p in _pieces(dk) if p[2] in _VISIBLE_ARMOR]
        # a weapon: prefer the shell class's own, else the DK set's, else a
        # plain two-hander display so the Hero is not empty-handed
        weapon = None
        shell = index.get((race, gender, shell_class))
        for src in (shell, dk):
            if not src:
                continue
            for it, dp, iv in _pieces(src):
                if iv in _WEAPON_SLOTS:
                    weapon = (it, dp, iv)
                    break
            if weapon:
                break
        pieces.append(weapon or _DEFAULT_WEAPON)
        pieces.append((_HEARTHSTONE_ITEM, 6418, 0))   # hearthstone, not rendered
        return pieces[:_N]

    def write_pieces(rec, pieces):
        for k in range(_N):
            rec[_ITEM + k] = 0
            rec[_DISP + k] = 0
            rec[_INV + k] = 0
        for k, (item, disp, inv) in enumerate(pieces):
            rec[_ITEM + k] = item
            rec[_DISP + k] = disp
            rec[_INV + k] = inv

    updated = 0
    for race in _RACES:
        for gender in (0, 1):
            pieces = hero_pieces(race, gender)
            if not pieces:
                continue
            rec = index.get((race, gender, shell_class))
            if rec is not None:
                write_pieces(rec, pieces)
                updated += 1

    # Any race with no shell-class row in vanilla gets one added, so no Hero
    # appears naked. The shell (Paladin) is only vanilla-creatable by four
    # races; the outfit look is copied from that race's own Death Knight row,
    # which every race has.
    added = 0
    for race in _RACES:
        for gender in (0, 1):
            if (race, gender, shell_class) in index:
                continue
            pieces = hero_pieces(race, gender)
            if not pieces:
                continue
            max_id += 1
            rec = [0] * _FIELDS
            rec[0] = max_id
            rec[1] = _pack_packed(race, shell_class, gender, 0)
            write_pieces(rec, pieces)
            records.append(rec)
            added += 1

    body = b"".join(struct.pack("<%di" % _FIELDS, *rec) for rec in records)
    header = WDBC_MAGIC + struct.pack("<4I", len(records), field_count,
                                      record_size, string_size)
    strings = data[20 + record_count * record_size:
                   20 + record_count * record_size + string_size]
    return header + body + strings, updated, added
