#!/usr/bin/env python3
"""Check the forged spell rows before they ever reach a server.

Reads the generator's own outputs -- forged_manifest.json and
cw_spells_forged.sql -- and asserts the properties that keep the set safe:
nothing inherits a class family, nothing is auto-granted, nothing sits off the
curve, and no hidden companion can show up in a spellbook tab.

Run:  python3 test_forged.py [CLIENT_DIR]

With a client directory it also applies the rows to that client's own tables in
memory and reads them back, which is the only way to know the appends land where
the game will look for them. Nothing is written to the client.
"""
import io
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.path.join(HERE, os.pardir)
MANIFEST = os.path.join(HERE, "forged_manifest.json")
SQL = os.path.join(MODULE, "data", "sql", "db-world", "cw_spells_forged.sql")
sys.path.insert(0, os.path.join(MODULE, "data", "sql", "generators"))

from gen_forged_spells import (F, RECIPES, HERO_LINE, SPELL_BASE, BLOCK_END,
                               anchor, resolve, ALL_CLASSES)

FAILS = []


def check(label, ok, detail=""):
    print("  [%s] %s%s" % ("ok  " if ok else "FAIL", label, ("  -- " + detail) if detail else ""))
    if not ok:
        FAILS.append(label)




def check_against_client(client_dir, doc):
    """Apply the rows to the client's own tables and read them back."""
    from lib import clientfs, forged

    print("\n-- against the client at %s" % client_dir)
    data = os.path.join(client_dir, "Data")
    with clientfs.ClientFiles(data, clientfs.detect_locales(data)[0]) as files:
        payload, report = {}, []
        forged.apply(files, payload, doc, report)

        def rows(path, fields):
            raw = payload[path]
            count, got, rec, _ = dbc.parse_header(raw)
            assert got == fields, "%s has %d fields" % (path, got)
            body = raw[20:20 + count * rec]
            return count, rec, body

        # the Hero line
        count, rec, body = rows(forged.SKILLLINE, forged.SKILLLINE_FIELDS)
        line = doc["skill_line"]
        found = [i for i in range(count)
                 if struct.unpack_from("<I", body, i * rec)[0] == line["id"]]
        ok = len(found) == 1
        if ok:
            r = found[0]
            cat = struct.unpack_from("<I", body, r * rec + 4)[0]
            icon = struct.unpack_from("<I", body, r * rec + forged.SL_ICON * 4)[0]
            ok = cat == line["category"] and icon == line["icon"]
        check("SkillLine.dbc: the Hero row lands with its category and icon", ok,
              "category %d must be 7 or the client will not draw it as a class tab"
              % line["category"])

        # every spell row
        count, rec, body = rows(forged.SPELL, 234)
        ids = {struct.unpack_from("<I", body, i * rec)[0]: i for i in range(count)}
        missing = [s["id"] for s in doc["spells"] if s["id"] not in ids]
        check("Spell.dbc: every forged row is appended", not missing,
              "%d added, missing %s" % (len(doc["spells"]), missing[:4]))

        # the overrides really applied, spot-checked on every row's school and level
        wrong = []
        for sp in doc["spells"]:
            r = ids.get(sp["id"])
            if r is None:
                continue
            for col in ("225", "39"):        # SchoolMask, SpellLevel
                if col in sp["fields"]:
                    got = struct.unpack_from("<I", body, r * rec + int(col) * 4)[0]
                    if got != sp["fields"][col]:
                        wrong.append("%d col%s want %s got %d"
                                     % (sp["id"], col, sp["fields"][col], got))
        check("Spell.dbc: the manifest's column overrides are what got written",
              not wrong, "offenders: %s" % wrong[:3])

        # recombined visuals
        if doc.get("visuals"):
            count, rec, body = rows(forged.SPELLVISUAL, forged.SPELLVISUAL_FIELDS)
            vids = {struct.unpack_from("<I", body, i * rec)[0]: i for i in range(count)}
            bad = []
            for v in doc["visuals"]:
                r = vids.get(v["id"])
                if r is None:
                    bad.append("%d absent" % v["id"])
                    continue
                for col, kit in v["kits"].items():
                    got = struct.unpack_from("<I", body, r * rec + int(col) * 4)[0]
                    if got != kit:
                        bad.append("%d slot%s want %d got %d" % (v["id"], col, kit, got))
            check("SpellVisual.dbc: every recombined look carries its borrowed kits",
                  not bad, "%d look(s); %s" % (len(doc["visuals"]), bad[:3]))

        # the tab rows
        count, rec, body = rows(forged.SKILLLINEABILITY, 14)
        sla = {}
        for i in range(count):
            row = struct.unpack_from("<14I", body, i * rec)
            sla[row[0]] = row
        want = [s for s in doc["spells"] if s["sla"]]
        bad = [s["id"] for s in want
               if s["sla"][0] not in sla
               or sla[s["sla"][0]][2] != s["id"]
               or sla[s["sla"][0]][1] != doc["skill_line"]["id"]
               or sla[s["sla"][0]][9] != 0]
        check("SkillLineAbility.dbc: every visible spell files under Hero, none auto-granted",
              not bad, "%d row(s); offenders %s" % (len(want), bad[:4]))

        hidden = [s["id"] for s in doc["spells"] if not s["sla"]]
        stray = [i for i in hidden if any(r[2] == i for r in sla.values())]
        check("SkillLineAbility.dbc: no hidden companion gained a tab row", not stray,
              "%d companion(s)" % len(hidden))

        # applying twice must not duplicate anything
        payload2 = dict(payload)
        forged.apply(files, payload2, doc, [])
        c1, _, _, _ = dbc.parse_header(payload[forged.SPELL])
        c2, _, _, _ = dbc.parse_header(payload2[forged.SPELL])
        check("re-applying the patch adds nothing twice", c1 == c2,
              "%d rows then %d" % (c1, c2))


def main():
    doc = json.load(io.open(MANIFEST, encoding="utf-8"))
    spells = doc["spells"]
    by_key = {r["key"]: r for r in RECIPES}
    print("manifest: %d row(s), generation %s\n" % (len(spells), doc["generation"]))

    # ---- the row itself -----------------------------------------------------
    check("every row has the 234-field layout",
          all(len(s["values"]) == 234 for s in spells))

    bad_family = [s["id"] for s in spells if s["values"][208] != 0]
    check("no row keeps its donor's SpellFamilyName", not bad_family,
          "a copied family would let that class's talents modify a classless spell; "
          "offenders: %s" % bad_family[:5])

    ids = [s["id"] for s in spells]
    check("ids are unique", len(ids) == len(set(ids)))
    check("ids stay inside the reserved block",
          all(SPELL_BASE <= i <= BLOCK_END for i in ids),
          "%d..%d" % (min(ids), max(ids)))

    # ---- how they are acquired ---------------------------------------------
    withsla = [s for s in spells if s["sla"]]
    check("every visible spell has a Hero-line row",
          all(s["sla"][1] == HERO_LINE for s in withsla),
          "%d row(s) on line %d" % (len(withsla), HERO_LINE))
    check("no forged spell is handed out with the skill line",
          all(s["sla"][9] == 0 for s in withsla),
          "AcquireMethod 1 or 2 is what made Seal of Righteousness follow Holy Light around")
    check("every visible spell is open to all classes",
          all(s["sla"][4] == ALL_CLASSES for s in withsla))

    companions = [s for s in spells if s["key"].endswith("_companion")]
    check("hidden companions carry no skill line row",
          all(s["sla"] is None for s in companions),
          "%d companion(s); a row would put the hidden half in a spellbook tab" % len(companions))

    # ---- levels -------------------------------------------------------------
    lines = {}
    for s in spells:
        if s["key"].endswith("_companion"):
            continue
        lines.setdefault(s["key"], []).append(s)
    ok_first, ok_order, ok_cap = True, True, True
    for key, rows in lines.items():
        rows.sort(key=lambda x: x["rank"])
        if rows[0]["level"] != by_key[key]["first_level"]:
            ok_first = False
        levels = [r["level"] for r in rows]
        if levels != sorted(levels) or len(set(levels)) != len(levels):
            ok_order = False
        if max(levels) > 80:
            ok_cap = False
    check("rank 1 is learnable at the level its recipe states", ok_first)
    check("levels rise strictly within a line", ok_order)
    check("no rank is past level 80", ok_cap)

    # ---- the curve ----------------------------------------------------------
    off, checked = [], 0
    for s in spells:
        key = s["key"].replace("_companion", "")
        recipe = by_key[key]
        effects = recipe["companion"]["effects"] if s["key"].endswith("_companion") \
            else recipe["effects"]
        for slot, e in enumerate(effects):
            base = e.get("base")
            if not isinstance(base, tuple):
                continue
            want = resolve(base, s["level"])
            got = s["values"][F["EffectBasePoints"] + slot] + 1
            checked += 1
            if want and abs(got - want) / want > 0.2:
                off.append("%s r%d slot%d want %.0f got %d" % (s["key"], s["rank"], slot, want, got))
    check("every curve-priced value is within 20% of its anchor", not off,
          "%d value(s) checked; off: %s" % (checked, off[:3]))

    # ---- the SQL ------------------------------------------------------------
    sql = io.open(SQL, encoding="utf-8").read()
    check("the Hero skill line row is written",
          re.search(r"INSERT INTO `skillline_dbc`", sql) is not None
          and ("(%d, 7, 0, 'Hero'" % HERO_LINE) in sql,
          "without it GetSkillRangeType returns SKILL_RANGE_NONE")
    check("a race/class row exists for the Hero line",
          re.search(r"INSERT INTO `skillraceclassinfo_dbc`[^;]*\(\d+, %d, 0, 0," % HERO_LINE,
                    sql, re.S) is not None,
          "without it _LoadSkills deletes the skill at every login")
    check("the run is stamped with a generation id",
          "cw_forged_meta" in sql and doc["generation"] in sql)
    check("the SQL deletes its own id range before inserting",
          ("DELETE FROM `spell_dbc` WHERE `ID` BETWEEN %d AND %d;" % (SPELL_BASE, BLOCK_END)) in sql)

    scripted_keys = {r["key"] for r in RECIPES if r.get("script")}
    want_rows = sum(1 for sp in doc["spells"]
                    if sp["key"] in scripted_keys and not sp["key"].endswith("_companion"))
    got_rows = re.findall(r"^\((\d+), 'spell_cw_([a-z_]+)'\)", sql, re.M)
    check("every rank of a scripted line binds to its script",
          len(got_rows) == want_rows and want_rows > 0,
          "%d row(s) for %d scripted rank(s); a missing rank loses its script silently"
          % (len(got_rows), want_rows))
    unscripted = [i for i, name in got_rows
                  if name not in scripted_keys]
    check("no unscripted line was given a script row", not unscripted,
          "offenders %s" % unscripted[:4])

    sla_rows = re.findall(r"^\((\d+), (\d+), (\d+), 0, (\d+), 0, 0, 1, (\d+), (\d+),",
                          sql, re.M)
    check("every SQL skill-line row matches the manifest",
          len(sla_rows) == len(withsla) and all(int(r[5]) == 0 for r in sla_rows),
          "%d row(s)" % len(sla_rows))

    if len(sys.argv) > 1:
        sys.path.insert(0, HERE)
        global dbc
        from lib import dbc
        check_against_client(sys.argv[1], doc)

    print()
    if FAILS:
        print("%d check(s) FAILED" % len(FAILS))
        return 1
    print("all forged spell checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
