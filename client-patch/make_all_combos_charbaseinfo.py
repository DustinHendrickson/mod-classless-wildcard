#!/usr/bin/env python3
"""
make_all_combos_charbaseinfo.py — rewrite CharBaseInfo.dbc so the character
creation screen allows EVERY race/class combination (class is only a chassis
in the classless system, so a Tauren mage-chassis or Gnome shaman-chassis is
legitimate). Pairs with the module's optional server SQL
(data/sql/db-world/optional/cw_all_race_class.sql) which unlocks the same
combinations server-side.

Usage:
    ./mpqtool extract "/path/to/WoW/Data/common.MPQ" 'DBFilesClient\\CharBaseInfo.dbc' CharBaseInfo.dbc
    python3 make_all_combos_charbaseinfo.py CharBaseInfo.dbc CharBaseInfo_all.dbc [--no-dk]
    ./mpqtool create patch-4.MPQ 'CharBaseInfo_all.dbc@DBFilesClient\\CharBaseInfo.dbc' ...
"""

import argparse
import struct
import sys

RACES = [1, 2, 3, 4, 5, 6, 7, 8, 10, 11]     # 3.3.5 playable races
CLASSES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 11]    # all classes (6 = Death Knight)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--no-dk", action="store_true", help="leave Death Knight combos as they were")
    args = parser.parse_args()

    with open(args.input, "rb") as fh:
        data = fh.read()
    if data[:4] != b"WDBC":
        print("error: not a WDBC file", file=sys.stderr)
        return 1

    rc, fc, rs, ss = struct.unpack_from("<4I", data, 4)
    if rs != 2 or fc != 2:
        print(f"error: unexpected CharBaseInfo layout (fields {fc}, record size {rs})", file=sys.stderr)
        return 1

    existing = { (data[20 + i * rs], data[20 + i * rs + 1]) for i in range(rc) }

    classes = list(CLASSES)
    combos = []
    for race in RACES:
        for cls in classes:
            if args.no_dk and cls == 6 and (race, cls) not in existing:
                continue
            combos.append((race, cls))
    # keep any original pair the lists above might not cover
    for pair in sorted(existing):
        if pair not in combos:
            combos.append(pair)

    records = b"".join(bytes(pair) for pair in combos)
    header = b"WDBC" + struct.pack("<4I", len(combos), 2, 2, 1)
    with open(args.output, "wb") as fh:
        fh.write(header + records + b"\0")

    added = [p for p in combos if p not in existing]
    print(f"wrote {args.output}: {len(combos)} combos ({len(existing)} original, {len(added)} added)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
