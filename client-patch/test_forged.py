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

# columns the shared F map does not name
F = dict(F, RangeIndex=46)

FAILS = []

def effects_for(recipe, key):
    """Which effect list a row was built from."""
    m = re.search(r"_pet(\d+)$", key)
    if m:
        return recipe["pet_spells"][int(m.group(1))]["effects"]
    if key.endswith("_companion"):
        return recipe["companion"]["effects"]
    return recipe["effects"]


def recipe_key(key):
    """A row's key back to its recipe: hidden halves and pet abilities are
    suffixed, and only the stem names a recipe."""
    return re.sub(r"_(companion|pet\d+)$", "", key)



def check(label, ok, detail=""):
    print("  [%s] %s%s" % ("ok  " if ok else "FAIL", label, ("  -- " + detail) if detail else ""))
    if not ok:
        FAILS.append(label)




def check_against_client(client_dir, doc):
    """Apply the rows to the client's own tables and read them back."""
    from lib import clientfs, forged

    print("\n-- against the client at %s" % client_dir)
    data = os.path.join(client_dir, "Data")
    locale = clientfs.detect_locales(data)[0]
    # Read PRISTINE tables, the way install.py does. An installed patch archive
    # already holds forged rows, and the appenders skip an id they already have,
    # so reading our own output back as the source would test the last install
    # rather than this one.
    exclude = set()
    for suffix in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        exclude.add("patch-%s.MPQ" % suffix)
        exclude.add("patch-%s-%s.MPQ" % (locale, suffix))
    with clientfs.ClientFiles(data, locale, exclude=exclude) as files:
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

        # The library dedupes abilities by NAME, so a forged spell sharing a name
        # with a stock one makes one of the two vanish from the pool. "Gravity
        # Well" was already two spells before this caught it.
        # Compare the TEXT, not the string offset. Every appended row gets a
        # fresh offset even when the name is identical, so an offset comparison
        # can never see a clash -- which it did not, until this was fixed.
        raw = payload[forged.SPELL]
        scount, _f, srec, strsize = dbc.parse_header(raw)
        sbody = raw[20:20 + scount * srec]
        blob = raw[20 + scount * srec:20 + scount * srec + strsize]

        def text_at(off):
            end = blob.find(bytes([0]), off)
            return blob[off:end].decode("utf-8", "replace") if end >= 0 else ""

        names = {}
        for i in range(scount):
            sid = struct.unpack_from("<I", sbody, i * srec)[0]
            off = struct.unpack_from("<I", sbody, i * srec + 136 * 4)[0]
            if off:
                names.setdefault(text_at(off).lower(), []).append(sid)
        ours = {sp["id"] for sp in doc["spells"]}
        clashes = []
        for sp in doc["spells"]:
            other = [i for i in names.get((sp["name"] or "").lower(), []) if i not in ours]
            if other:
                clashes.append("%s clashes with %s" % (sp["name"], other[:2]))
        check("no forged spell shares a name with a stock one", not clashes,
              "%s" % clashes[:3])

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
        # hidden halves and pet abilities are not lines of their own
        if recipe_key(s["key"]) != s["key"]:
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
        key = recipe_key(s["key"])
        recipe = by_key[key]
        effects = effects_for(recipe, s["key"])
        for slot, e in enumerate(effects):
            base = e.get("base")
            if not isinstance(base, tuple):
                continue
            want = resolve(base, s["level"], s["rank"] - 1)
            got = s["values"][F["EffectBasePoints"] + slot] + 1
            checked += 1
            if want and abs(got - want) / want > 0.2:
                off.append("%s r%d slot%d want %.0f got %d" % (s["key"], s["rank"], slot, want, got))
    check("every curve-priced value is within 20% of its anchor", not off,
          "%d value(s) checked; off: %s" % (checked, off[:3]))

    # ---- pet abilities, and what must be true of them -----------------------
    sql_pets = io.open(SQL, encoding="utf-8").read()
    ranks_block = re.search(r"INSERT INTO `spell_ranks`[^;]*;", sql_pets, re.S)
    stray = []
    if ranks_block:
        listed = {int(x) for x in re.findall(r"^\(\d+, (\d+), \d+\)",
                                            ranks_block.group(0), re.M)}
        hidden_ids = {sp["id"] for sp in spells if not sp["sla"]}
        stray = sorted(listed & hidden_ids)
    check("spell_ranks lists only real ranks", not stray,
          "a hidden half or a pet ability there becomes an ability line of its own; "
          "offenders %s" % stray[:4])

    # SpellInfo::IsAutocastable refuses PASSIVE (0x40) and NO_AUTOCAST_AI
    # (attr1 0x20000). Either one and the ability reaches the pet bar greyed out.
    notcast = [sp["name"] for sp in spells
               if "_pet" in sp["key"]
               and (sp["values"][4] & 0x40 or sp["values"][5] & 0x20000)]
    petcount = sum(1 for sp in spells if "_pet" in sp["key"])
    check("every pet ability can be autocast", not notcast,
          "%d pet ability row(s); %s" % (petcount, notcast[:3]))

    percreature = {}
    for m in re.finditer(r"^\((\d+), (\d+), (\d+), 12340\)", sql_pets, re.M):
        percreature.setdefault(int(m.group(1)), set()).add(int(m.group(2)))
    over = [c for c, idx in percreature.items() if len(idx) > 4 or max(idx) > 3]
    check("no creature carries more spells than the pet bar holds", not over,
          "MAX_SPELL_CHARM is 4; offenders %s" % over[:3])

    # ---- a buff has to say what it is doing, and be drawable ------------------
    # Column 187 is the ToolTip the BUFF ICON shows on hover; 170 is the
    # spellbook Description. Every forged row shipped with 187 empty, so a Hero
    # could watch a buff run and never find out what it was. And display 11686
    # is Creature\InvisibleStalker\InvisibleStalker.mdx, which the core uses
    # when it wants nothing drawn -- Reclaimed Sentry wore it for six rounds.
    INVISIBLE_DISPLAYS = {11686}
    silent = [sp["name"] for sp in spells
              if any(sp["values"][F["Effect"] + i] in (6, 27) for i in range(3))
              and not sp["values"][187]]
    check("every spell that applies an aura carries a buff tooltip", not silent,
          "%d aura row(s); %s" % (
              sum(1 for sp in spells
                  if any(sp["values"][F["Effect"] + i] in (6, 27) for i in range(3))),
              sorted(set(silent))[:3]))

    sql_disp = io.open(SQL, encoding="utf-8").read()
    invis = ["creature %s is given display %s, which is an invisible model"
             % (m.group(1), m.group(2))
             for m in re.finditer(r"^\((99\d{4}), 0, (\d+), ", sql_disp, re.M)
             if int(m.group(2)) in INVISIBLE_DISPLAYS]
    check("no summoned creature wears an invisible model", not invis, "%s" % invis[:3])

    # ---- a summoned creature must not be a "trigger" --------------------------
    # Unit.cpp:16978 rewrites the display id in the update block sent to each
    # client: a creature template with CREATURE_FLAG_EXTRA_TRIGGER (0x80) is
    # given GetFirstInvisibleModel() for every viewer who is not in GM mode,
    # whatever creature_template_model says. Every marker carried that bit, and
    # it defeated a model fix, a summon-properties fix and a targeting fix in
    # turn -- the creature was there and the client was told to draw nothing.
    sql_cre = io.open(SQL, encoding="utf-8").read()
    triggers = []
    for m in re.finditer(r"^\((99\d{4}), '([^']*)', '', 1, 80, \d+, \d+, \d+, "
                         r"\d+, \d+, \d+, \d+, (\d+),", sql_cre, re.M):
        if int(m.group(3)) & 0x80:
            triggers.append("%s (%s) has CREATURE_FLAG_EXTRA_TRIGGER, so the client is "
                            "told to draw an invisible model" % (m.group(2), m.group(1)))
    check("no summoned creature is flagged as a trigger", not triggers,
          "%s" % triggers[:3])

    # ---- every summon has a creature, and that creature has a model ---------
    # Models live in creature_template_model, not creature_template. A creature
    # with no row there spawns invisible: the spell works and nothing appears.
    sql_all = io.open(SQL, encoding="utf-8").read()
    missing = []
    for sp in spells:
        for i in range(3):
            if sp["values"][F["Effect"] + i] not in (28, 56):   # SUMMON, SUMMON_PET
                continue
            entry = sp["values"][F["EffectMiscValue"] + i]
            if re.search(r"INSERT INTO `creature_template`[^;]*\(%d," % entry, sql_all, re.S) is None:
                missing.append("%s: no creature_template for %d" % (sp["name"], entry))
            if re.search(r"INSERT INTO `creature_template_model`[^;]*\(%d, 0, \d+" % entry,
                         sql_all, re.S) is None:
                missing.append("%s: creature %d has no model" % (sp["name"], entry))
    check("every summon has a creature and a model", not missing,
          "%s" % sorted(set(missing))[:3])

    # ---- what a donor must not bring with it --------------------------------
    # Copying a row copies everything that made the donor a CLASS spell. None of
    # these shows up as an error: SpellInfo::CheckShapeshift simply refuses the
    # cast for anyone not in the donor's form, and a missing reagent simply
    # fails. Charge brought Battle Stance and Psychic Scream brought Shadowform.
    inherited = []
    for sp in spells:
        v = sp["values"]
        who = "%s r%d" % (sp["name"], sp["rank"])
        if v[12] or v[14]:
            inherited.append("%s: form mask 0x%X/0x%X" % (who, v[12], v[14]))
        if v[18]:
            inherited.append("%s: spell focus %d" % (who, v[18]))
        if any(v[52 + i] for i in range(8)) or v[50] or v[51]:
            inherited.append("%s: needs an item" % who)
        # Charge is out-of-combat only; NOT_SHAPESHIFTED would lock out any Hero
        # who rolled a form. Values read from the core's SharedDefines.
        for bit, why in ((0x10000000, "out-of-combat only"),
                         (0x00010000, "not while shapeshifted"),
                         (0x00004000, "indoors only"),
                         (0x00008000, "outdoors only"),
                         (0x00020000, "stealth only"),
                         (0x00000040, "passive")):
            if v[4] & bit:
                inherited.append("%s: %s" % (who, why))
    check("no forged spell inherits its donor's form, focus or reagent",
          not inherited, "%d row(s) checked; %s" % (len(spells), inherited[:3]))

    # ---- effect, target and duration have to agree --------------------------
    # An area effect with a zero radius hits a point. An aura with no duration
    # never expires. A heal aimed at an enemy heals nobody. None of the three
    # errors anywhere: RADIUS_10YD was index 36 for a while, which is 0 yards.
    from gen_forged_spells import Dbc as _Dbc
    import os as _os
    _dbc_dir = _os.environ.get("CW_DBC", r"B:\New folder\dbc")
    coherence = []
    try:
        rad = _Dbc(_os.path.join(_dbc_dir, "SpellRadius.dbc"))
    except Exception:
        rad = None
    # Implicit target ids by what they select, from the table in SpellInfo.cpp.
    # A SRC or DEST id sets a position and selects nobody, so an aura, a heal
    # or a weapon swing given one of those alone lands on nothing. Vertigo,
    # Wide Arc, Sinkhole and Spore Wash shipped exactly that way, and the old
    # version of this check called 22 and 28 "area targets" and let them by.
    UNIT_T = {1, 2, 3, 4, 5, 6, 7, 8, 15, 16, 20, 21, 24, 25, 27, 30, 31, 33, 34,
              35, 37, 38, 45, 54, 104}
    DEST_T = {9, 17, 18, 28, 29, 32, 36, 41, 42, 43, 44, 46, 47, 48, 49, 50, 53,
              55, 63, 87}
    SRC_T = {22}
    # 24 and 104 are the two cone targets; both need a radius, and 104 is the
    # only one the player pool uses (Cone of Cold, Dragon's Breath)
    AREA_T = {7, 8, 15, 16, 20, 30, 31, 33, 34, 37, 28, 24, 104}
    LANDS_ON_UNITS = {2, 6, 10, 30, 31, 64, 68, 96, 114, 121, 145}
    HEAL_EFFECTS = {10, 65}
    DAMAGE_EFFECTS = {2, 31, 121, 58, 17}
    for sp in spells:
        v = sp["values"]
        has_aura = False
        for i in range(3):
            eff = v[F["Effect"] + i]
            if not eff:
                continue
            tgt = v[F["EffectImplicitTargetA"] + i]
            tgtb = v[F["EffectImplicitTargetB"] + i]
            if eff in (6, 27):
                has_aura = True
            if tgt not in UNIT_T | DEST_T | SRC_T:
                coherence.append("%s: effect %d uses target %d, which is not in the table"
                                 % (sp["name"], i, tgt))
            if eff in LANDS_ON_UNITS and tgt not in UNIT_T and tgtb not in UNIT_T:
                coherence.append("%s: effect %d lands on units but targets a position (%d/%d)"
                                 % (sp["name"], i, tgt, tgtb))
            if eff == 27 and tgt not in DEST_T:
                coherence.append("%s: effect %d is a persistent area with no destination"
                                 % (sp["name"], i))
            # Consecration's area applies 3 (PERIODIC_DAMAGE); 4 is DUMMY, and
            # Sinkhole and Reclaimed Sentry shipped dealing nothing with it
            if eff == 27 and v[F["EffectApplyAuraName"] + i] not in (3, 8, 23, 53, 89, 226):
                coherence.append("%s: effect %d is a persistent area applying aura %d, which does nothing"
                                 % (sp["name"], i, v[F["EffectApplyAuraName"] + i]))
            # rage is stored ten to the displayed point: a 20 shows as "2 Rage"
            if v[41] == 1 and v[42] and (v[42] % 10 or v[42] < 50):
                coherence.append("%s: costs %d stored rage, which shows as %.1f"
                                 % (sp["name"], v[42], v[42] / 10.0))
            # ENERGIZE of energy cannot usefully exceed the 100-point pool
            if eff == 30 and v[F["EffectMiscValue"] + i] == 3 \
                    and v[F["EffectBasePoints"] + i] + 1 > 100:
                coherence.append("%s: effect %d restores %d energy into a pool of 100"
                                 % (sp["name"], i, v[F["EffectBasePoints"] + i] + 1))
            if rad is not None and (tgt in AREA_T or tgtb in AREA_T):
                row = rad.row_of(v[F["EffectRadiusIndex"] + i])
                if row is None or not rad.f(row, 1):
                    coherence.append("%s: effect %d is an area target with no radius"
                                     % (sp["name"], i))
            if eff in HEAL_EFFECTS and tgt == 6:
                coherence.append("%s: effect %d heals an enemy" % (sp["name"], i))
            if eff in DAMAGE_EFFECTS and tgt in (1, 21):
                coherence.append("%s: effect %d damages the caster or an ally"
                                 % (sp["name"], i))
            if v[F["RangeIndex"]] == 1 and 6 in (tgt, tgtb):
                coherence.append("%s: effect %d targets an enemy at self range"
                                 % (sp["name"], i))
        if has_aura and not v[F["DurationIndex"]]:
            coherence.append("%s: applies an aura with no duration" % sp["name"])
    check("effects, targets and durations agree", not coherence,
          "%d row(s) checked; %s" % (len(spells), coherence[:3]))

    # ---- a script hook has to name the effect the spell actually has ----------
    # A SpellScript hook names an effect INDEX and an effect TYPE. If the row's
    # effect at that index is something else the hook is never called, the spell
    # quietly loses the half that made it interesting, and nothing logs it.
    # Read from the C++ rather than assumed, so moving an effect breaks this.
    cpp = io.open(os.path.join(MODULE, "src", "ClasslessForgedScripts.cpp"),
                  encoding="utf-8").read()
    E_CONST = {"SPELL_EFFECT_SCHOOL_DAMAGE": 2, "SPELL_EFFECT_DUMMY": 3,
               "SPELL_EFFECT_APPLY_AURA": 6, "SPELL_EFFECT_HEAL": 10,
               "SPELL_EFFECT_PERSISTENT_AREA_AURA": 27, "SPELL_EFFECT_SUMMON": 28,
               "SPELL_EFFECT_ENERGIZE": 30, "SPELL_EFFECT_WEAPON_PERCENT_DAMAGE": 31,
               "SPELL_EFFECT_TRIGGER_SPELL": 64, "SPELL_EFFECT_INTERRUPT_CAST": 68,
               "SPELL_EFFECT_CHARGE": 96, "SPELL_EFFECT_NORMALIZED_WEAPON_DMG": 121}
    A_CONST = {"SPELL_AURA_MOD_DAMAGE_PERCENT_DONE": 79, "SPELL_AURA_PERIODIC_DAMAGE": 3,
               "SPELL_AURA_MOD_MELEE_RANGED_HASTE": 192, "SPELL_AURA_DUMMY": 4,
               "SPELL_AURA_MOD_CASTING_SPEED_NOT_STACK": 65}
    sql_scripts = io.open(SQL, encoding="utf-8").read()
    bound = {}
    for m in re.finditer(r"^\((\d+), '(spell_cw_[a-z_]+)'\)", sql_scripts, re.M):
        bound.setdefault(m.group(2), []).append(int(m.group(1)))
    blocks = [(m.group(1), m.start()) for m in
              re.finditer(r"class (spell_cw_[a-z_]+)\s*:\s*public\s+\w+Script", cpp)]
    blocks.append(("__end__", len(cpp)))
    by_sid = {sp["id"]: sp for sp in spells}
    mismatch = []
    for n in range(len(blocks) - 1):
        cls, a = blocks[n]
        body = cpp[a:blocks[n + 1][1]]
        ids = bound.get(cls, [])
        if not ids:
            mismatch.append("%s is registered but no spell_script_names row names it" % cls)
            continue
        for mm in re.finditer(r"EFFECT_(\d)\s*,\s*(SPELL_(?:EFFECT|AURA)_[A-Z_0-9]+)", body):
            idx, want = int(mm.group(1)), mm.group(2)
            for sid in ids:
                v = by_sid[sid]["values"]
                got_e = v[F["Effect"] + idx]
                got_a = v[F["EffectApplyAuraName"] + idx]
                if want in E_CONST and got_e != E_CONST[want]:
                    mismatch.append("%s hooks EFFECT_%d as %s but %d has effect %d"
                                    % (cls, idx, want, sid, got_e))
                elif want in A_CONST and (got_e != 6 or got_a != A_CONST[want]):
                    mismatch.append("%s hooks EFFECT_%d as %s but %d has aura %d"
                                    % (cls, idx, want, sid, got_a))
        for idx in {int(x) for x in re.findall(r"Effects\[EFFECT_(\d)\]", body)}:
            for sid in ids:
                if not by_sid[sid]["values"][F["Effect"] + idx]:
                    mismatch.append("%s reads EFFECT_%d, empty on %d" % (cls, idx, sid))
    check("every script hook names the effect its spell actually has",
          not mismatch, "%s" % sorted(set(mismatch))[:3])

    # ---- the art a spell points at has to exist -------------------------------
    # An icon id that is not in SpellIcon.dbc is a question mark in the
    # spellbook; a visual that is neither appended nor shipped draws nothing.
    art = []
    try:
        _icon = _Dbc(_os.path.join(_dbc_dir, "SpellIcon.dbc"))
        _vis2 = _Dbc(_os.path.join(_dbc_dir, "SpellVisual.dbc"))
    except Exception:
        _icon = None
    if _icon is not None:
        appended = {vv["id"] for vv in doc.get("visuals", [])}
        for sp in spells:
            v = sp["values"]
            if v[F["SpellIconID"]] and _icon.row_of(v[F["SpellIconID"]]) is None:
                art.append("%s: icon %d does not exist" % (sp["name"], v[F["SpellIconID"]]))
            vi = v[F["SpellVisual"]]
            if vi and vi not in appended and _vis2.row_of(vi) is None:
                art.append("%s: visual %d is neither appended nor shipped" % (sp["name"], vi))
        for vv in doc.get("visuals", []):
            if _vis2.row_of(vv["base"]) is None:
                art.append("recombined visual %d copies a base that does not exist" % vv["id"])
    check("every icon and visual a spell points at exists", not art, "%s" % art[:3])

    # ---- no donor condition survives that would change how a spell plays ------
    # Hand of Freedom is castable while stunned on purpose, and six spells that
    # copied its row inherited that: defensive and offensive cooldowns a stun
    # could not answer. USES_RANGED_SLOT on Ricochet Shot is the one bit here
    # that is meant: it is a shot, and Multi-Shot carries the same.
    STUCK_BITS = [
        (4, 0x00000004, "ON_NEXT_SWING_NO_DAMAGE"), (4, 0x00000400, "ON_NEXT_SWING"),
        (4, 0x00000020, "IS_TRADESKILL"), (4, 0x00000200, "HELD_ITEM_ONLY"),
        (4, 0x00020000, "ONLY_STEALTHED"), (4, 0x00010000, "NOT_SHAPESHIFTED"),
        (4, 0x00004000, "ONLY_INDOORS"), (4, 0x00008000, "ONLY_OUTDOORS"),
        (4, 0x10000000, "NOT_IN_COMBAT_ONLY_PEACEFUL"), (4, 0x00000040, "PASSIVE"),
        (4, 0x00080000, "SCALES_WITH_CREATURE_LEVEL"),
        (9, 0x00000008, "ALLOW_WHILE_STUNNED"),
    ]
    RANGED_OK = {"Ricochet Shot"}
    stuck = []
    for sp in spells:
        v = sp["values"]
        for col, bit, nm in STUCK_BITS:
            if v[col] & bit:
                stuck.append("%s: kept %s from its donor" % (sp["name"], nm))
        if v[4] & 0x00000002 and sp["name"] not in RANGED_OK:
            stuck.append("%s: kept USES_RANGED_SLOT from its donor" % sp["name"])
    check("no donor condition survives that would change how a spell plays",
          not stuck, "%s" % sorted(set(stuck))[:3])

    # ---- a spell has to FUNCTION, not merely be shaped right ------------------
    # The faults that leave a correctly-targeted spell behaving wrongly in play:
    # a periodic with no tick, an aura with no duration, a donor's cooldown
    # category or proc flags still driving it, a rank that does not improve.
    function = []
    try:
        _dur = _Dbc(_os.path.join(_dbc_dir, "SpellDuration.dbc"))
    except Exception:
        _dur = None
    PERIODIC = {3, 8, 23, 24, 53, 64, 89}          # 4 is DUMMY, not a periodic
    by_line = {}
    for sp in spells:
        by_line.setdefault(sp["key"], []).append(sp)
    for sp in spells:
        v = sp["values"]
        who = "%s r%d" % (sp["name"], sp["rank"])
        dms = 0
        if _dur is not None and v[F["DurationIndex"]]:
            row = _dur.row_of(v[F["DurationIndex"]])
            dms = _dur.i(row, 1) if row is not None else 0
        for i in range(3):
            eff, aura = v[F["Effect"] + i], v[F["EffectApplyAuraName"] + i]
            if not eff:
                continue
            amp = v[F["EffectAmplitude"] + i]
            if eff in (6, 27) and aura in PERIODIC and not amp:
                function.append("%s: effect %d is periodic with no tick" % (who, i))
            if eff in (6, 27) and aura in PERIODIC and amp and dms > 0 and amp > dms:
                function.append("%s: effect %d ticks slower than its duration" % (who, i))
            if eff in (6, 27) and not aura:
                function.append("%s: effect %d applies aura 0" % (who, i))
        if v[1]:
            function.append("%s: kept its donor's cooldown category %d" % (who, v[1]))
        if v[49]:
            function.append("%s: kept its donor's StackAmount %d" % (who, v[49]))
        if v[27] and not any(v[F["EffectApplyAuraName"] + i] in (42, 43, 109)
                             for i in range(3)):
            function.append("%s: kept its donor's ProcFlags %#x with no proc aura"
                            % (who, v[27]))
    for key, rws in by_line.items():
        rws = sorted(rws, key=lambda x: x["rank"])
        for i in range(3):
            vals = [r["values"][F["EffectBasePoints"] + i] + 1 for r in rws
                    if r["values"][F["Effect"] + i]]
            if len(vals) != len(rws) or len(set(vals)) < 2:
                continue
            mag = [abs(x) for x in vals]
            if any(b < a for a, b in zip(mag, mag[1:])):
                function.append("%s: effect %d gets weaker with rank: %s"
                                % (rws[0]["name"], i, vals))
    check("every spell functions: ticks, durations, ranks and no donor leftovers",
          not function, "%s" % sorted(set(function))[:3])

    # ---- every (effect, targetA, targetB) has to be a shape the game uses ----
    # Copying a donor row and changing its effects produces target combinations
    # nothing ships. Five markers applied an aura with target 31 alone, which no
    # player spell in the game does, and Wide Arc kept a melee range index after
    # becoming a point-blank swing. Both were invisible until the shape was
    # compared with the shipped spells that do the same thing.
    unknown_shape = []
    try:
        _sp = _Dbc(_os.path.join(_dbc_dir, "Spell.dbc"))
        _sla = _Dbc(_os.path.join(_dbc_dir, "SkillLineAbility.dbc"))
        _skl = _Dbc(_os.path.join(_dbc_dir, "SkillLine.dbc"))
    except Exception:
        _sp = None
    if _sp is not None:
        _cls = {_skl.u(r, 0) for r in range(_skl.rows) if _skl.u(r, 1) == 7}
        _pool = {_sla.u(r, 2) for r in range(_sla.rows)
                 if _sla.u(r, 1) in _cls and _sla.u(r, 4)}
        shapes = set()
        for r in range(_sp.rows):
            if _sp.u(r, 0) not in _pool:
                continue
            for i in range(3):
                if _sp.u(r, F["Effect"] + i):
                    shapes.add((_sp.u(r, F["Effect"] + i),
                                _sp.u(r, F["EffectImplicitTargetA"] + i),
                                _sp.u(r, F["EffectImplicitTargetB"] + i)))
        # the two the set uses on purpose, each half proven on its own
        ALLOWED_NEW = {(145, 16, 0)}       # a ground-targeted pull; no stock one exists
        for sp in spells:
            v = sp["values"]
            for i in range(3):
                if not v[F["Effect"] + i]:
                    continue
                sh = (v[F["Effect"] + i], v[F["EffectImplicitTargetA"] + i],
                      v[F["EffectImplicitTargetB"] + i])
                if sh not in shapes and sh not in ALLOWED_NEW:
                    unknown_shape.append("%s: effect %d is %s, a shape no player spell uses"
                                         % (sp["name"], i, sh))
    check("every effect uses a target shape the game itself ships", not unknown_shape,
          "%s" % sorted(set(unknown_shape))[:3])

    # ---- a summon has to name a summon type that exists -----------------------
    # Spell::EffectSummonType looks up SummonProperties by the effect's
    # MiscValueB and returns immediately when there is no such row, logging
    # "Unhandled summon type". Every marker in this file wrote 0, and there is
    # no SummonProperties row 0, so seven spells summoned nothing at all while
    # their creature and model rows sat unused. Effect 56 (SUMMON_PET) does not
    # read it and is exempt.
    props = None
    try:
        props = _Dbc(_os.path.join(_dbc_dir, "SummonProperties.dbc"))
    except Exception:
        pass
    bad_summon = []
    if props is not None:
        for sp in spells:
            v = sp["values"]
            for i in range(3):
                if v[F["Effect"] + i] != 28:
                    continue
                b = v[F["EffectMiscValueB"] + i]
                if not b or props.row_of(b) is None:
                    bad_summon.append("%s: effect %d summons with type %d, which is not a "
                                      "SummonProperties row" % (sp["name"], i, b))
                elif props.u(props.row_of(b), 4):          # Slot
                    bad_summon.append("%s: effect %d uses summon type %d, which takes totem "
                                      "slot %d" % (sp["name"], i, b, props.u(props.row_of(b), 4)))
    check("every summon names a summon type the core can look up", not bad_summon,
          "%s" % bad_summon[:3])

    # ---- a missile that is drawn has to travel -------------------------------
    # Spell.dbc column 47 is Speed, in yards per second (Fireball 24, Arcane
    # Shot 40, every melee spell 0). The generator never wrote it, so every
    # projectile in the set arrived the instant the cast ended with nothing
    # drawn between caster and target. SpellVisual field 7 says whether the
    # look has a missile at all, so the two have to agree.
    missiles = []
    try:
        vdbc = _Dbc(_os.path.join(_dbc_dir, "SpellVisual.dbc"))
    except Exception:
        vdbc = None
    if vdbc is not None:
        # a recombined look is a donor's row with some kit slots moved, so
        # whether it carries a missile is the DONOR's answer; without this the
        # rule silently skipped every spell that got a new look
        donor_of = {v["id"]: v["base"] for v in doc.get("visuals", [])}
        for sp in spells:
            v = sp["values"]
            vid = v[F["SpellVisual"]]
            if not vid:
                continue          # 0 is "draw nothing", which Throw itself uses
            row = vdbc.row_of(donor_of.get(vid, vid))
            if row is None:
                missiles.append("%s: visual %d resolves to no SpellVisual row"
                                % (sp["name"], vid))
                continue
            has = vdbc.u(row, 7)
            if has and not v[47]:
                missiles.append("%s: visual %d draws a missile but Speed is 0"
                                % (sp["name"], v[F["SpellVisual"]]))
            if v[47] and not has:
                missiles.append("%s: Speed %.0f but visual %d draws no missile"
                                % (sp["name"], v[47], v[F["SpellVisual"]]))
    check("a drawn missile has a speed, and a speed has a missile", not missiles,
          "%d row(s) checked; %s" % (len(spells), missiles[:3]))

    # ---- the tooltips -------------------------------------------------------
    # $s3 on a spell with two effects renders as literal "$s3" in the client, and
    # $d on a spell with no duration renders as nothing. Both are silent: the
    # spell works and only its description is wrong.
    bad_var = []
    by_id = {sp["id"]: sp for sp in spells}
    for sp in spells:
        text = sp["description"] or ""
        vals = sp["values"]
        effects = [vals[F["Effect"] + i] for i in range(3)]
        for m in re.finditer(r"\$([soa])(\d)", text):
            kind, slot = m.group(1), int(m.group(2)) - 1
            if slot < 0 or slot > 2 or not effects[slot]:
                bad_var.append("%s: $%s%d has no effect" % (sp["name"], kind, slot + 1))
                continue
            if kind == "o" and not vals[F["EffectAmplitude"] + slot]:
                bad_var.append("%s: $o%d is not periodic" % (sp["name"], slot + 1))
            if kind == "a" and not vals[F["EffectRadiusIndex"] + slot]:
                bad_var.append("%s: $a%d has no radius" % (sp["name"], slot + 1))
        if "$d" in text and not vals[F["DurationIndex"]]:
            bad_var.append("%s: $d but no duration" % sp["name"])
        # $<spellid>s1 is the client's reference to another spell's value; the
        # generator fills it with the rank's companion, so it has to name a row
        # in this manifest with an effect in that slot
        for m in re.finditer(r"\$(\d+)([soa])(\d)", text):
            other = by_id.get(int(m.group(1)))
            slot = int(m.group(3)) - 1
            if other is None or slot < 0 or slot > 2 or not other["values"][F["Effect"] + slot]:
                bad_var.append("%s: $%s%s%s points at nothing"
                               % (sp["name"], m.group(1), m.group(2), m.group(3)))
    check("every tooltip variable points at something real", not bad_var,
          "%d description(s) checked; %s" % (len(spells), bad_var[:4]))

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
    # The server compiles the Hero line id in (SyncSpellbookTabs hands the
    # skill out by it); the generator writes the rows under HERO_LINE. Two
    # numbers, one meaning.
    header = io.open(os.path.join(MODULE, "src", "ClasslessWildcard.h"), encoding="utf-8").read()
    m = re.search(r"constexpr uint32 HERO_SKILL_LINE = (\d+);", header)
    check("the Hero line id is the one the server compiled in",
          m is not None and int(m.group(1)) == HERO_LINE,
          "header says %s, generator says %d" % (m.group(1) if m else None, HERO_LINE))
    check("the run is stamped with a generation id",
          "cw_forged_meta" in sql and doc["generation"] in sql)
    check("the SQL deletes its own id range before inserting",
          ("DELETE FROM `spell_dbc` WHERE `ID` BETWEEN %d AND %d;" % (SPELL_BASE, BLOCK_END)) in sql)

    # This one shipped: CREATE TABLE IF NOT EXISTS leaves a table that already
    # exists exactly as it found it, so a realm that had applied an earlier
    # build kept a cw_forged_spells with no `type` column, and the INSERT below
    # died with "Unknown column 'type' in 'field list'". For every table this
    # file creates, each column a later write names has to be either the
    # primary key, which no version has been without, or one a guarded ALTER
    # adds first.
    unmigrated, tables = [], re.findall(r"CREATE TABLE IF NOT EXISTS `(\w+)`", sql)
    for table in tables:
        pk = re.search(r"CREATE TABLE IF NOT EXISTS `%s`.*?PRIMARY KEY \(`(\w+)`\)"
                       % table, sql, re.S)
        added = {m.group(1): m.start() for m in
                 re.finditer(r"ALTER TABLE `%s` ADD COLUMN `(\w+)`" % table, sql)}
        for w in re.finditer(r"(?:INSERT|REPLACE) INTO `%s` \(([^)]*)\)" % table, sql):
            for c in re.findall(r"`(\w+)`", w.group(1)):
                if pk and c == pk.group(1):
                    continue
                at = added.get(c)
                if (at is None or at > w.start()
                        or "IF NOT EXISTS" not in sql[max(0, at - 400):at]):
                    unmigrated.append("%s.%s" % (table, c))
    check("every column a write names survives an older copy of its table",
          len(tables) >= 2 and not unmigrated,
          "%d table(s); a column with no guarded ALTER above the write that "
          "names it is an Unknown column error on any realm that applied an "
          "older build; unmigrated %s" % (len(tables), unmigrated))

    scripted_keys = {r["key"] for r in RECIPES if r.get("script")}
    bounce_keys = {r["key"] for r in RECIPES if r.get("companion_script")}
    want_rows = sum(1 for sp in doc["spells"]
                    if (sp["key"] in scripted_keys and not sp["key"].endswith("_companion"))
                    or (sp["key"].endswith("_companion") and sp["key"][:-len("_companion")] in bounce_keys))
    got_rows = re.findall(r"^\((\d+), 'spell_cw_([a-z_]+)'\)", sql, re.M)
    check("every rank of a scripted line binds to its script",
          len(got_rows) == want_rows and want_rows > 0,
          "%d row(s) for %d scripted rank(s); a missing rank loses its script silently"
          % (len(got_rows), want_rows))
    unscripted = [i for i, name in got_rows
                  if (name[:-len("_bounce")] if name.endswith("_bounce") else name) not in scripted_keys]
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
