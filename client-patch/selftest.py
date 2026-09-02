#!/usr/bin/env python3
"""Exercise the whole client-patch pipeline against a real client, read-only.

    python3 selftest.py "B:/World.of.Warcraft.3.3.5a"

Resolves every source file through the client's archive stack, applies each
transform, builds the archives in a temp folder, reads them back, and checks the
results. Nothing in the client is written to. Exits non-zero on any failure.
"""

from __future__ import annotations

import os
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from lib import (blp, charcreate, clientfs, dbc, exepatch, gluestrings,  # noqa: E402
                 mpq, outfit)

CHRCLASSES = "DBFilesClient\\ChrClasses.dbc"
CHARBASEINFO = "DBFilesClient\\CharBaseInfo.dbc"
SKILLRACECLASSINFO = "DBFilesClient\\SkillRaceClassInfo.dbc"
CHARSTARTOUTFIT = "DBFilesClient\\CharStartOutfit.dbc"
GLUESTRINGS = "Interface\\GlueXML\\GlueStrings.lua"
CHARCREATE_LUA = "Interface\\GlueXML\\CharacterCreate.lua"

FAILURES = []


def check(label, condition, detail=""):
    status = "ok  " if condition else "FAIL"
    print("  [%s] %s%s" % (status, label, (" -- " + detail) if detail else ""))
    if not condition:
        FAILURES.append(label)
    return condition


def dbc_strings(data):
    record_count, _fields, record_size, string_size = dbc.parse_header(data)
    start = 20 + record_count * record_size
    return data[start:start + string_size]


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    wow = argv[1]
    data_dir = os.path.join(wow, "Data")
    if not os.path.isdir(data_dir):
        print("no Data folder in %s" % wow)
        return 2

    locales = clientfs.detect_locales(data_dir)
    print("client : %s" % wow)
    print("locales: %s" % ", ".join(locales))

    for locale in locales:
        print("\n== %s" % locale)
        with clientfs.ClientFiles(data_dir, locale) as files:
            print("  archive chain: %d archives, top is %s"
                  % (len(files.chain), os.path.basename(files.chain[0])))

            # --- ChrClasses -------------------------------------------------
            raw, source = files.find(CHRCLASSES)
            patched, renamed = dbc.rename_all_classes(raw, "Hero")
            patched, unrelic = dbc.clear_relic_slot(patched)
            check("ChrClasses resolved", bool(raw), os.path.basename(source))
            check("all classes renamed", len(renamed) >= 10,
                  "%d records" % len(renamed))

            # Slot 17 is a relic slot for Paladin, DK, Shaman and Druid, and the
            # client draws nothing there -- which made every bow, gun and wand
            # invisible on the Paladin chassis.
            relic_ids = {c[0] for c in unrelic}
            check("relic slot cleared on exactly the 4 relic classes",
                  relic_ids == {2, 6, 7, 11},
                  "classes %s" % sorted(relic_ids))
            still = []
            rcount, rfields, rsize, _rs = dbc.parse_header(patched)
            for index in range(rcount):
                row = struct.unpack_from("<%dI" % rfields, patched, 20 + index * rsize)
                if row[dbc.CHRCLASSES_FLAGS_FIELD] & dbc.CHRCLASSES_FLAG_RELIC_SLOT:
                    still.append(row[0])
            check("no class still has a relic slot", not still, "%s" % still)

            count, fields, size, _ = dbc.parse_header(patched)
            strings = dbc_strings(patched)
            names, tokens = set(), []
            for index in range(count):
                row = struct.unpack_from("<%dI" % fields, patched, 20 + index * size)
                names.add(dbc.read_string(strings, row[dbc.CHRCLASSES_NAME_COLUMNS[0]]))
                tokens.append(dbc.read_string(strings, row[dbc.CHRCLASSES_TOKEN_FIELD]))
            check("every name is Hero", names == {"Hero"}, repr(sorted(names)))
            check("class tokens preserved",
                  {"WARRIOR", "MAGE", "DRUID", "DEATHKNIGHT"} <= set(tokens),
                  ", ".join(tokens[:4]) + ", ...")

            # --- CharBaseInfo -----------------------------------------------
            raw, source = files.find(CHARBASEINFO)
            combos, races = dbc.single_class_combos(raw, 2)  # Paladin shell
            body = combos[20:20 + races * 2]
            pairs = {(body[i], body[i + 1]) for i in range(0, len(body), 2)}
            check("one class per race", len(pairs) == races == 10,
                  "%d rows" % races)
            check("only the Paladin shell is offered",
                  {klass for _race, klass in pairs} == {2})
            # --- SkillRaceClassInfo ------------------------------------------
            # The client draws a spellbook tab only for a class skill line its
            # own table allows the character's class. Open them all, as the
            # server SQL already does, and prove none of the targeted lines
            # is still class-locked afterwards.
            raw, source = files.find(SKILLRACECLASSINFO)
            opened_dbc, opened, already = dbc.open_class_skill_lines(raw)
            check("SkillRaceClassInfo resolved", bool(raw), os.path.basename(source))
            rc_, fc_, rs_, _ss = dbc.parse_header(opened_dbc)
            by_skill = {}
            for index in range(rc_):
                row = struct.unpack_from("<8I", opened_dbc, 20 + index * rs_)
                by_skill.setdefault(row[1], []).append(row)
            still_locked = [sk for sk in dbc.CLASS_SKILL_LINES
                            if sk in by_skill
                            and not any(dbc._open_to_all(r) for r in by_skill[sk])]
            # and they must be written the way the CLIENT reads "everyone" --
            # the server's 0/0 wildcard draws no tab
            client_form = [sk for sk in opened
                           if not any((r[3] & dbc.ALL_CLASSES_MASK) == dbc.ALL_CLASSES_MASK
                                      for r in by_skill.get(sk, []))]
            check("opened rows use the client's all-classes mask, not 0/0",
                  not client_form, "%d rows written with a 0 mask" % len(client_form))
            check("class skill lines opened to every class",
                  not still_locked and len(opened) + len(already) > 0,
                  "%d opened, %d already open, %d still locked"
                  % (len(opened), len(already), len(still_locked)))
            # the client list must mirror the server SQL exactly, or the two
            # halves of the fix drift apart silently
            sql_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir,
                                    "data", "sql", "db-world", "cw_world_skillraceclass.sql")
            sql_ids = set()
            try:
                import re as _re
                with open(sql_path, encoding="utf-8") as fh:
                    for m in _re.finditer(r"^\(99\d+,(\d+),", fh.read(), _re.M):
                        sql_ids.add(int(m.group(1)))
            except OSError:
                sql_ids = None
            check("client skill-line list matches the server SQL",
                  sql_ids is None or sql_ids == set(dbc.CLASS_SKILL_LINES),
                  "n/a (SQL not found)" if sql_ids is None else
                  "%d in SQL, %d in client list" % (len(sql_ids), len(dbc.CLASS_SKILL_LINES)))
            # idempotent: patching the patched file adds nothing
            _again, opened_again, _al = dbc.open_class_skill_lines(opened_dbc)
            check("SkillRaceClassInfo patch idempotent", not opened_again,
                  "%d added on second pass" % len(opened_again))

            check("every race still creatable",
                  {race for race, _klass in pairs} == set(dbc.PLAYABLE_RACES))

            # --- GlueStrings ------------------------------------------------
            raw, source = files.find(GLUESTRINGS)
            text = raw.decode("utf-8", "surrogateescape")
            new_text, replaced = gluestrings.rewrite(text, "Hero")
            check("class strings rewritten", len(replaced) >= 20,
                  "%d keys from %s" % (len(replaced), os.path.basename(source)))
            check("unrelated strings untouched",
                  text.count("REALM_LIST") == new_text.count("REALM_LIST"))
            check("no key lost", len(text.splitlines()) == len(new_text.splitlines()))

            # --- CharacterCreate hide-class hook ----------------------------
            raw, source = files.find(CHARCREATE_LUA)
            lua = raw.decode("utf-8", "surrogateescape")
            hooked = charcreate.add_hide_class_hook(lua)
            check("hide-class hook appended",
                  "ClasslessWildcard_HideClass" in hooked
                  and "function CharacterCreateEnumerateClasses(" in hooked)
            check("hide-class hook idempotent",
                  charcreate.add_hide_class_hook(hooked) == hooked)

            # --- CharStartOutfit armored look -------------------------------
            raw, source = files.find(CHARSTARTOUTFIT)
            new_dbc, updated, added = outfit.build_hero_outfit(raw, 2)
            oc, of, orc, oss = struct.unpack_from("<4I", new_dbc, 4)
            check("outfit rows present for every race+gender",
                  updated + added == 20, "%d updated + %d added" % (updated, added))
            # no head slot (invtype 1) on the human-male Hero row
            def _row(data, race, gender, cls):
                rc = struct.unpack_from("<I", data, 4)[0]
                rs = struct.unpack_from("<I", data, 12)[0]
                for i in range(rc):
                    b = 20 + i * rs
                    r, c, g, o = struct.unpack_from("<4B", data, b + 4)
                    if r == race and g == gender and c == cls:
                        return struct.unpack_from("<%di" % (rs // 4), data, b)
                return None
            hm = _row(new_dbc, 1, 0, 2)  # human male Paladin (Hero)
            check("Hero outfit keeps the face (no helmet)",
                  hm is not None and all(hm[50 + k] != 1 for k in range(24)))

            # --- Hero icon BLP ----------------------------------------------
            atlas = blp.render_hero_class_atlas()
            if atlas is None:
                print("  [skip] Pillow not installed; no Hero-icon check")
            else:
                mo = [x for x in struct.unpack_from("<16I", atlas, 20) if x]
                ml = [x for x in struct.unpack_from("<16I", atlas, 84) if x]
                check("BLP header matches genuine (01 08 08 01)",
                      atlas[8:12] == bytes.fromhex("01080801"))
                check("BLP full mip chain + self-consistent",
                      len(mo) == 9 and len(atlas) == mo[-1] + ml[-1])

            # --- archives ---------------------------------------------------
            payload = {CHRCLASSES: patched, CHARBASEINFO: combos,
                       SKILLRACECLASSINFO: opened_dbc}
            # the locale archive carries the DBCs as well: it is the one Wow.exe
            # loads above the client's own patch-<loc>-N archives, so a DBC that
            # only sits in patch-Z.MPQ is shadowed and never seen
            glue = {GLUESTRINGS: new_text.encode("utf-8", "surrogateescape")}
            glue.update(payload)
            # prove the shadowing claim against THIS client's chain: for every
            # DBC we patch, the stock copy must resolve from a locale archive,
            # which is exactly why the base patch alone could never win
            shadowed_by_locale = []
            for dbc_name in (CHRCLASSES, CHARBASEINFO, SKILLRACECLASSINFO):
                _r, src_arch = files.find(dbc_name)
                in_locale = os.sep + locale + os.sep in src_arch or ("-%s" % locale) in os.path.basename(src_arch)
                shadowed_by_locale.append(in_locale)
            check("stock DBCs live in locale archives (so ours must too)",
                  all(shadowed_by_locale),
                  "%d of %d resolve from a locale archive" % (sum(shadowed_by_locale), len(shadowed_by_locale)))
            with tempfile.TemporaryDirectory() as tmp:
                base = os.path.join(tmp, "patch-Z.MPQ")
                loc = os.path.join(tmp, "patch-%s-Z.MPQ" % locale)
                mpq.write_archive(base, payload)
                mpq.write_archive(loc, glue)

                for path, expected in ((base, payload), (loc, glue)):
                    archive = mpq.MPQArchive(path)
                    for name, original in expected.items():
                        check("roundtrip %s" % name.rsplit("\\", 1)[-1],
                              archive.read_file(name) == original)
                    check("listfile in %s" % os.path.basename(path),
                          b"(listfile)" in archive.read_file("(listfile)"))
                    archive.close()

                try:
                    import mpyq
                except ImportError:
                    print("  [skip] mpyq not installed; no cross-validation")
                else:
                    for path, expected in ((base, payload), (loc, glue)):
                        other = mpyq.MPQArchive(path)
                        try:
                            for name, original in expected.items():
                                check("mpyq agrees on %s" % name.rsplit("\\", 1)[-1],
                                      other.read_file(name) == original)
                        finally:
                            other.file.close()  # mpyq holds the handle open

    # --- exe ------------------------------------------------------------
    print("\n== Wow.exe")
    exe = None
    for name in ("Wow.exe", "WoW.exe", "wow.exe"):
        if os.path.isfile(os.path.join(wow, name)):
            exe = os.path.join(wow, name)
            break
    if not exe:
        check("Wow.exe present", False)
    else:
        state, offset, digest, label = exepatch.inspect(exe)
        # A client here may be pristine (patch sites found) or already patched
        # by a prior install (sites consumed). Both are healthy; only "unknown"
        # -- a client the pattern set does not fit -- is a failure.
        check("interface patch applies or is applied", state != exepatch.UNKNOWN,
              "state=%s%s" % (state, "" if label is None
                              else " (%s)" % label))
        if state == exepatch.UNPATCHED:
            check("patch site located", offset is not None,
                  "offset=%s" % (offset and hex(offset)))

    print()
    if FAILURES:
        print("FAILED: %s" % ", ".join(FAILURES))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
