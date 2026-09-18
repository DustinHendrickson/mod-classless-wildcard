"""Watch the data that decides whether the module can destroy a player's spells.

`Player::SetSkill(line, 0, 0, 0)` unlearns EVERY spell on the line it removes,
with no class check. SyncSpellbookTabs removes any SKILL_CATEGORY_CLASS line the
Hero has earned nothing in THROUGH THE LIBRARY -- which is not the same as "has
nothing on". Anything a player got another way (a mount from a vendor, a
Polymorph from a tome, a ritual from a book) sits on the line, is invisible to
the library, and goes with it.

That is how every vendor-bought mount was wiped from `character_spell` on the
next login. See HAZARDS.md for the full write-up.

The module now guards this three ways, and ClasslessMgr.cpp is where they live.
What THIS file watches is the DATA underneath them, because the guards were
sized against one particular set of tables and a realm can ship different ones:

  1. Which class-category lines does every character start with? Those are the
     ones the sweep can fire on for a character that has never touched the
     module. Today: Mounts 777 and Companions 778.
  2. Does Companions still have no row carrying a class mask? It is safe only
     because of that. One masked row would pull it into _classSkillLines the
     way four paladin mounts pulled in Mounts, and every vanity pet a player
     owns would be at risk.
  3. What is reachable outside the library on a class line? Reported rather
     than failed: the general guard in SyncSpellbookTabs covers these, and the
     list is worth seeing when it grows.

Run it after any world-DB update, and after changing anything about skill lines.

    python data/sql/generators/validate_skill_lines.py
"""
import io
import os
import re
import struct
import sys

DBC = r"B:\New folder\dbc"
CORE_SQL = r"B:\code\azerothcore-wotlk\data\sql\base\db_world"

SKILL_CATEGORY_CLASS = 7
MOUNTS_LINE, COMPANIONS_LINE, RUNEFORGING_LINE = 777, 778, 776
A_MOUNTED = 78
ACQUIRE_ON_VALUE, ACQUIRE_ON_LEARN = 1, 2
E_LEARN_SPELL = 36
SPELL_EFFECT, SPELL_AURA, SPELL_TRIGGER = 71, 95, 98
SPELL_ATTR, SPELL_LEVEL, SPELL_BASELEVEL, SPELL_NAME = 4, 39, 38, 136
ATTR_PASSIVE, ATTR_HIDDEN = 0x40, 0x80
UTILITY_EFFECTS = {25, 26, 40, 47, 60, 78, 118}
ITEM_LEARN_ON_USE = 6
NUL = bytes([0])

# What the module expects to be true. A change here is the warning.
EXPECTED_CREATION_CLASS_LINES = {MOUNTS_LINE, COMPANIONS_LINE}

fail = 0


def load(name):
    raw = open(os.path.join(DBC, name), "rb").read()
    _m, rows, fields, rec, _s = struct.unpack_from("<4sIIII", raw, 0)
    return raw, rows, fields, rec


spell_raw, spell_rows, _sf, spell_rec = load("Spell.dbc")
spell_str = spell_raw[20 + spell_rows * spell_rec:]
SPELL_AT = {}
for i in range(spell_rows):
    at = 20 + i * spell_rec
    SPELL_AT[struct.unpack_from("<I", spell_raw, at)[0]] = at


def spell(sid, col):
    return struct.unpack_from("<I", spell_raw, SPELL_AT[sid] + 4 * col)[0]


def spell_name(sid):
    off = spell(sid, SPELL_NAME)
    return spell_str[off:spell_str.index(NUL, off)].decode("utf-8", "replace")


def is_mount(sid):
    return sid in SPELL_AT and any(spell(sid, SPELL_AURA + e) == A_MOUNTED
                                   for e in range(3))


line_raw, line_rows, line_fields, line_rec = load("SkillLine.dbc")
line_str = line_raw[20 + line_rows * line_rec:]
CATEGORY, LINE_NAME = {}, {}
for i in range(line_rows):
    v = struct.unpack_from("<%dI" % line_fields, line_raw, 20 + i * line_rec)
    CATEGORY[v[0]] = v[1]
    LINE_NAME[v[0]] = line_str[v[3]:line_str.index(NUL, v[3])].decode("utf-8", "replace")

# ID 0, SkillLine 1, Spell 2, RaceMask 3, ClassMask 4, ..., AcquireMethod 9
sla_raw, sla_rows, sla_fields, sla_rec = load("SkillLineAbility.dbc")
SLA = [struct.unpack_from("<%dI" % sla_fields, sla_raw, 20 + i * sla_rec)
       for i in range(sla_rows)]


def sql_rows(path):
    """Every (...) tuple in a mysqldump, split at top level."""
    text = io.open(path, encoding="utf-8", errors="replace").read()
    out = []
    for line in text.splitlines():
        line = line.strip().rstrip(";").rstrip(",")
        if not (line.startswith("(") and line.endswith(")")):
            continue
        parts, cur, quote, i = [], [], None, 0
        body = line[1:-1]
        while i < len(body):
            c = body[i]
            if quote:
                if c == quote:
                    if quote == "'" and i + 1 < len(body) and body[i + 1] == "'":
                        cur.append(body[i:i + 2]); i += 2; continue
                    quote = None
                cur.append(c)
            elif c in "'\"":
                quote = c; cur.append(c)
            elif c == ",":
                parts.append("".join(cur)); cur = []
            else:
                cur.append(c)
            i += 1
        parts.append("".join(cur))
        out.append([p.strip() for p in parts])
    return text, out


# ---- 1. what every character starts with -----------------------------------
# playercreateinfo_skills: racemask, classmask, skill, rank. 0/0 is everyone.
_t, rows = sql_rows(os.path.join(CORE_SQL, "playercreateinfo_skills.sql"))
universal = {int(f[2]) for f in rows
             if len(f) >= 3 and f[0] == "0" and f[1] == "0" and f[2].isdigit()}
creation_class_lines = {s for s in universal if CATEGORY.get(s) == SKILL_CATEGORY_CLASS}
print("skills every race and class starts with: %d" % len(universal))
print("of those, in the CLASS category (the sweep can remove these): %s"
      % sorted("%d %s" % (s, LINE_NAME.get(s, "?")) for s in creation_class_lines))
if creation_class_lines != EXPECTED_CREATION_CLASS_LINES:
    added = creation_class_lines - EXPECTED_CREATION_CLASS_LINES
    gone = EXPECTED_CREATION_CLASS_LINES - creation_class_lines
    print("   FAILED: this set changed. Added %s, missing %s. Every line here is "
          "one the spellbook sweep can fire on for a character that never "
          "touched the module -- check it is protected in SyncSpellbookTabs."
          % (sorted(added), sorted(gone)))
    fail = 1

# ---- 2. Companions must stay unmasked --------------------------------------
masked = {}
for v in SLA:
    if v[4] and CATEGORY.get(v[1]) == SKILL_CATEGORY_CLASS:
        masked.setdefault(v[1], []).append(v)
comp = masked.get(COMPANIONS_LINE, [])
print("")
print("Companions (%d) rows carrying a ClassMask: %d" % (COMPANIONS_LINE, len(comp)))
if comp:
    print("   FAILED: the Companions line now inherits a class mask from %s, so it "
          "joins _classSkillLines and every vanity pet a player owns is exposed "
          "the way mounts were. It needs the same treatment as Mounts."
          % [(v[2], spell_name(v[2]) if v[2] in SPELL_AT else "?") for v in comp[:4]])
    fail = 1
else:
    print("   safe: it never reaches _classSkillLines")

mount_masked = masked.get(MOUNTS_LINE, [])
print("Mounts (%d) rows carrying a ClassMask: %d %s"
      % (MOUNTS_LINE, len(mount_masked),
         "(all mounts, so the module's rule zeroes the line)"
         if all(is_mount(v[2]) for v in mount_masked) else ""))
if mount_masked and not all(is_mount(v[2]) for v in mount_masked):
    print("   FAILED: a row on the Mounts line carries a class mask and is NOT a "
          "mount, so the 'a mount lends no class mask' rule no longer zeroes the "
          "line: %s"
          % [(v[2], spell_name(v[2])) for v in mount_masked if not is_mount(v[2])][:4])
    fail = 1

# ---- 3. what is reachable outside the library, reported ---------------------
line_mask = {}
for v in SLA:
    if not v[4] or CATEGORY.get(v[1]) != SKILL_CATEGORY_CLASS or is_mount(v[2]):
        continue
    line_mask[v[1]] = line_mask.get(v[1], 0) | v[4]


def class_mask_of(v):
    return v[4] or line_mask.get(v[1], 0)


# learnLevels: the world DB's trainer list first -- it is the bulk of it, and
# reading only the DBCs badly overstates what the trainer filter admits.
learn = set()
trainer_file = "trainer_spell.sql"
if not os.path.exists(os.path.join(CORE_SQL, trainer_file)):
    trainer_file = "npc_trainer.sql"
_t, rows = sql_rows(os.path.join(CORE_SQL, trainer_file))
for f in rows:
    if len(f) < 5 or not f[1].lstrip("-").isdigit() or not f[3].isdigit():
        continue
    if int(f[3]) != 0:                       # ReqSkillLine = 0, as the module does
        continue
    sid = int(f[1])
    if sid <= 0 or sid not in SPELL_AT:
        continue
    wrapper = False
    for e in range(3):
        if spell(sid, SPELL_EFFECT + e) == E_LEARN_SPELL and spell(sid, SPELL_TRIGGER + e):
            learn.add(spell(sid, SPELL_TRIGGER + e))
            wrapper = True
    if not wrapper:
        learn.add(sid)

class_spells = {v[2] for v in SLA if CATEGORY.get(v[1]) == SKILL_CATEGORY_CLASS}
for v in SLA:
    if not class_mask_of(v) or CATEGORY.get(v[1]) != SKILL_CATEGORY_CLASS:
        continue
    if v[9] not in (ACQUIRE_ON_VALUE, ACQUIRE_ON_LEARN) or v[2] not in SPELL_AT:
        continue
    if spell(v[2], SPELL_ATTR) & ATTR_PASSIVE:
        continue
    if spell(v[2], SPELL_LEVEL) or spell(v[2], SPELL_BASELEVEL):
        learn.add(v[2])
for sid in SPELL_AT:
    for e in range(3):
        if spell(sid, SPELL_EFFECT + e) == E_LEARN_SPELL:
            t = spell(sid, SPELL_TRIGGER + e)
            if t and t in class_spells:
                learn.add(t)

in_library = set()
for v in SLA:
    if not class_mask_of(v) or v[3] or CATEGORY.get(v[1]) != SKILL_CATEGORY_CLASS:
        continue
    sid = v[2]
    if sid not in SPELL_AT or not spell_name(sid):
        continue
    if spell(sid, SPELL_ATTR) & ATTR_HIDDEN:
        continue
    if any(spell(sid, SPELL_EFFECT + e) in UTILITY_EFFECTS for e in range(3)):
        continue
    if sid in learn:
        in_library.add(sid)

# item_template has no column list in the dump: read its CREATE TABLE.
item_text = io.open(os.path.join(CORE_SQL, "item_template.sql"),
                    encoding="utf-8", errors="replace").read()
ddl = item_text[item_text.index("CREATE TABLE `item_template`"):]
ddl = ddl[:ddl.index(") ENGINE")]
item_cols = re.findall(r"^\s+`([A-Za-z0-9_]+)`", ddl, re.M)
spell_at = [item_cols.index("spellid_%d" % n) for n in range(1, 6)]
trig_at = [item_cols.index("spelltrigger_%d" % n) for n in range(1, 6)]

taught_by_item = set()
_t, rows = sql_rows(os.path.join(CORE_SQL, "item_template.sql"))
for f in rows:
    if len(f) != len(item_cols):
        continue
    for si, ti in zip(spell_at, trig_at):
        try:
            sid, trig = int(f[si]), int(f[ti])
        except ValueError:
            continue
        if sid > 0 and trig == ITEM_LEARN_ON_USE and sid in SPELL_AT:
            taught_by_item.add(sid)

risk = {}
for v in SLA:
    if CATEGORY.get(v[1]) != SKILL_CATEGORY_CLASS or not class_mask_of(v):
        continue
    if v[1] == RUNEFORGING_LINE or v[2] in in_library:
        continue
    if v[2] in taught_by_item and v[2] in SPELL_AT:
        risk.setdefault(v[1], set()).add(v[2])

print("")
print("item-taught spells on a class line that the library does not hold:")
print("(the general guard in SyncSpellbookTabs keeps their line -- listed so a "
      "growing set is visible)")
total = sum(len(v) for v in risk.values())
for line, spells in sorted(risk.items(), key=lambda kv: -len(kv[1])):
    print("   line %-5d %-22s %d: %s"
          % (line, LINE_NAME.get(line, "?")[:22], len(spells),
             ", ".join(sorted(spell_name(s) for s in spells))[:70]))
print("   total: %d" % total)

print("")
print("skill line data: %s" % ("PROBLEM" if fail else "as the module's guards expect"))
sys.exit(1 if fail else 0)
