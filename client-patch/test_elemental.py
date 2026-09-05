#!/usr/bin/env python3
"""Check the elemental-variant client step against extracted DBCs, no client
needed.

    python3 test_elemental.py --dbc "B:/New folder/dbc"

Appends every variant in elemental_manifest.json to real Spell, SpellVisual,
SpellIcon and SkillLineAbility tables, re-parses the results, reads the new
rows back and compares them with the manifest. Icon painting is exercised on a
synthetic BLP, because the client's icon art lives in its archives, not in a
DBC extract. Exits non-zero on any failure. selftest.py covers the same step
against a real client.
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from lib import blp, dbc, elemental  # noqa: E402

FAILURES = []


def check(label, condition, detail=""):
    print("  [%s] %s%s" % ("ok  " if condition else "FAIL", label, (" -- " + detail) if detail else ""))
    if not condition:
        FAILURES.append(label)


def cstr(strings, off):
    end = strings.find(b"\0", off)
    return strings[off:end].decode("utf-8", "replace") if end >= 0 else ""


def rows_of(data):
    count, fields, rec, strsize = dbc.parse_header(data)
    return count, fields, rec, data[20:20 + count * rec], data[20 + count * rec:]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dbc", required=True, help="directory holding extracted 3.3.5a DBCs")
    ap.add_argument("--manifest", default=elemental.manifest_path())
    args = ap.parse_args(argv)

    def read(name):
        path = os.path.join(args.dbc, name)
        if not os.path.exists(path):
            sys.exit("missing %s in %s" % (name, args.dbc))
        with open(path, "rb") as fh:
            return fh.read()

    manifest = elemental.load_manifest(args.manifest)
    variants = [dict(v, fields=dict(v["fields"])) for v in manifest["variants"]]
    print("manifest: %d variant(s), %d element(s)" % (len(variants), len(manifest["elements"])))
    if not variants:
        sys.exit("nothing to test")

    # ---- Spell.dbc --------------------------------------------------------
    raw = read("Spell.dbc")
    out, added, missing = elemental.append_spells(raw, variants)
    c0, f0, r0, _, _ = rows_of(raw)
    c1, f1, r1, records, strings = rows_of(out)
    check("Spell.dbc: every variant appended", added == len(variants) and not missing,
          "%d added, %d bases missing" % (added, len(missing)))
    check("Spell.dbc: layout kept", f1 == f0 == 234 and r1 == r0 and c1 == c0 + added)
    ids = {struct.unpack_from("<I", records, i * r1)[0]: i for i in range(c1)}
    bad = 0
    for v in variants:
        row = records[ids[v["id"]] * r1:(ids[v["id"]] + 1) * r1]
        u = lambda f: struct.unpack_from("<I", row, f * 4)[0]
        ok = (cstr(strings, u(136)) == v["name"]
              and cstr(strings, u(170)) == v["description"]
              and all(u(c) == u(136) for c in range(136, 152))
              and all(u(int(k)) == (int(val) & 0xFFFFFFFF) for k, val in v["fields"].items()
                      if int(k) not in elemental.FLOAT_FIELDS))
        if not ok:
            bad += 1
    check("Spell.dbc: names, text and overrides read back", bad == 0, "%d row(s) differ" % bad)
    out2, added2, _ = elemental.append_spells(out, variants)
    check("Spell.dbc: re-append is a no-op", added2 == 0 and len(out2) == len(out))

    # ---- SpellVisual.dbc --------------------------------------------------
    raw = read("SpellVisual.dbc")
    out, added = elemental.append_visuals(raw, variants)
    c0, _, r0, base_records, _ = rows_of(raw)
    c1, _, r1, records, _ = rows_of(out)
    base_ids = {struct.unpack_from("<I", base_records, i * r0)[0]: i for i in range(c0)}
    ids = {struct.unpack_from("<I", records, i * r1)[0]: i for i in range(c1)}
    bad = 0
    for v in variants:
        vis = v["visual"]
        if vis["id"] not in ids:
            bad += 1
            continue
        row = struct.unpack_from("<32i", records, ids[vis["id"]] * r1)
        base = struct.unpack_from("<32i", base_records, base_ids[vis["base"]] * r0) if vis["base"] in base_ids else (0,) * 32
        if row[3] != vis["impact_kit"] or row[2] != base[2]:
            bad += 1
    check("SpellVisual.dbc: base swing kept, element impact set", bad == 0 and added,
          "%d row(s) added, %d wrong" % (added, bad))

    # ---- SpellIcon.dbc ----------------------------------------------------
    raw = read("SpellIcon.dbc")
    painted = {v["icon"]["id"] for v in variants}
    out, added = elemental.append_icons(raw, variants, painted)
    c1, _, r1, records, strings = rows_of(out)
    paths = {}
    for i in range(c1):
        iid, off = struct.unpack_from("<II", records, i * r1)
        paths[iid] = cstr(strings, off)
    bad = sum(1 for v in variants
              if paths.get(v["icon"]["id"]) != elemental.ICON_DIR + elemental.icon_file_stem(v["icon"]))
    check("SpellIcon.dbc: one path per painted icon", bad == 0 and added == len(painted),
          "%d added for %d icons" % (added, len(painted)))
    _, added_none = elemental.append_icons(raw, variants, set())
    check("SpellIcon.dbc: unpainted icons add no rows", added_none == 0)

    # ---- SkillLineAbility.dbc --------------------------------------------
    raw = read("SkillLineAbility.dbc")
    out, added = elemental.append_skill_lines(raw, variants)
    c1, _, r1, records, _ = rows_of(out)
    ids = {struct.unpack_from("<I", records, i * r1)[0]: i for i in range(c1)}
    bad = 0
    for v in variants:
        sla = v["sla"]
        if not sla or sla[0] not in ids:
            bad += 1
            continue
        row = struct.unpack_from("<14I", records, ids[sla[0]] * r1)
        if row[2] != v["id"] or row[4] != dbc.ALL_CLASSES_MASK or row[1] != sla[1]:
            bad += 1
    check("SkillLineAbility.dbc: variant rows open to every class", bad == 0 and added,
          "%d added, %d wrong" % (added, bad))

    # AcquireMethod 1 and 2 mean the core hands the spell over with the skill
    # line itself. Every class's starting strike says that, so a row copied
    # from Heroic Strike or Sinister Strike carries it, and the variant stops
    # being something rolled for: the server also reads it as an ordinary
    # trained ability and rates it from its own power rather than one tier
    # above its base. Every variant row must say 0.
    granted = [v["id"] for v in variants if v["sla"] and v["sla"][9] != 0]
    for v in variants:
        if v["sla"] and v["sla"][0] in ids:
            row = struct.unpack_from("<14I", records, ids[v["sla"][0]] * r1)
            if row[9] != 0 and v["id"] not in granted:
                granted.append(v["id"])
    check("SkillLineAbility.dbc: no variant is handed out with the skill line",
          not granted, "%d row(s) carry AcquireMethod 1/2: %s"
          % (len(granted), granted[:6]) if granted else "%d row(s) checked" % len(variants))

    # ---- targeting ---------------------------------------------------------
    # The percent hit and the elemental add must target exactly what the
    # base's weapon effect targeted: an area strike stays an area strike, a
    # chain strike keeps its chain. Compared against the base rows in the
    # extract, not against the manifest's own copy of them.
    raw = read("Spell.dbc")
    c0, _, r0, base_records, _ = rows_of(raw)
    base_rows = {struct.unpack_from("<I", base_records, i * r0)[0]: i for i in range(c0)}
    WEAPON = {17, 31, 58, 121}
    bad_target = 0
    for v in variants:
        b = base_rows.get(v["base"])
        if b is None:
            continue
        brow = base_records[b * r0:(b + 1) * r0]
        bu = lambda f: struct.unpack_from("<I", brow, f * 4)[0]
        w0 = next((e for e in range(3) if bu(71 + e) in WEAPON), None)
        if w0 is None:
            continue
        want = (bu(86 + w0), bu(89 + w0), bu(92 + w0), bu(104 + w0))
        f = v["fields"]
        for slot in (0, 1):
            got = tuple(int(f.get(str(k + slot), 0)) for k in (86, 89, 92, 104))
            if got != want:
                bad_target += 1
    check("targeting: percent hit and elemental add use the base's targets, radius and chain",
          bad_target == 0, "%d slot(s) differ" % bad_target)

    # ---- rank chains --------------------------------------------------------
    # Every line's SkillLineAbility rows must supersede along the VARIANT line
    # (rank 1 -> rank 2 -> ... -> 0), never point at the base's ranks.
    lines = {}
    for v in variants:
        lines.setdefault(v["first"], []).append(v)
    bad_chain, multi = 0, 0
    for first, members in lines.items():
        members.sort(key=lambda v: v["rank"])
        if len(members) > 1:
            multi += 1
        for k, v in enumerate(members):
            expect = members[k + 1]["id"] if k + 1 < len(members) else 0
            if v["sla"] and v["sla"][8] != expect:
                bad_chain += 1
            if v["rank"] != k + 1:
                bad_chain += 1
    check("rank chains: SupercededBySpell walks the variant line",
          bad_chain == 0, "%d line(s), %d multi-rank, %d bad" % (len(lines), multi, bad_chain))

    # ---- icons ------------------------------------------------------------
    if blp.have_pillow():
        from PIL import Image
        im = Image.new("RGBA", (64, 64))
        px = im.load()
        for y in range(64):
            for x in range(64):
                px[x, y] = (x * 4 % 256, y * 4 % 256, 128, 255)
        synthetic = blp.encode_palettized(im)
        sample = variants[0]["icon"]
        bad = []
        for elem in manifest["elements"]:
            icon = dict(sample, element=elem["key"], hue=elem["hue"], glyph=elem["glyph"])
            try:
                painted_blp = elemental.render_icon(synthetic, icon)
                w, h, _ = blp.decode_blp(painted_blp)
                if (w, h) != (64, 64) or painted_blp[:4] != b"BLP2":
                    bad.append(elem["key"])
            except Exception as error:  # noqa: BLE001 - report, do not crash the run
                bad.append("%s (%s)" % (elem["key"], error))
        check("icons: every element paints a valid 64x64 BLP2", not bad, ", ".join(bad))
    else:
        print("  [skip] icons: Pillow not installed")

    print()
    if FAILURES:
        print("%d check(s) failed" % len(FAILURES))
        return 1
    print("all elemental client-side checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
