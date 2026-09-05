"""Client side of the forged spells: the Hero tab and the spells under it.

What this appends to the player's own tables:

  SkillLine.dbc         one row, the Hero line itself. Without it the tab has
                        no name and no icon.
  Spell.dbc             one row per forged spell and per hidden companion
  SpellVisual.dbc       one row per recombined look: a donor's row with some of
                        its kit slots pointed elsewhere. Each kit carries its
                        own sound, so this is where a new spell gets a look and
                        a sound that no stock spell has, without new art.
  SkillLineAbility.dbc  one row per visible spell, which is what files it under
                        the Hero tab. Hidden companions deliberately get none.

Nothing of Blizzard's lives in the repository: the manifest holds ids and the
columns each row changes, and every row is built by copying the player's own
donor row and applying that diff. A community patch's edits to columns this
does not touch survive.

The row appenders for Spell.dbc and SkillLineAbility.dbc are elemental.py's,
unchanged: the manifest is written in the shape they already read, so there is
one implementation of each rather than two that can drift.
"""
import io
import json
import os
import struct

from . import dbc
from .elemental import (_add_string, _ids, _join, _split, append_skill_lines,
                        append_spells)

SKILLLINE = "DBFilesClient\\SkillLine.dbc"
SPELL = "DBFilesClient\\Spell.dbc"
SPELLVISUAL = "DBFilesClient\\SpellVisual.dbc"
SKILLLINEABILITY = "DBFilesClient\\SkillLineAbility.dbc"

SKILLLINE_FIELDS = 56
SPELLVISUAL_FIELDS = 32

# SkillLine.dbc, 3.3.5a: 0 ID, 1 CategoryID, 2 SkillCostsID,
# 3..18 DisplayName + 19 mask, 20..35 Description + 36 mask, 37 SpellIcon,
# 38..53 AlternateVerb + 54 mask, 55 CanLink
SL_NAME_FIRST, SL_NAME_MASK = 3, 19
SL_ICON = 37


class ForgedError(Exception):
    pass


def manifest_path():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "forged_manifest.json")


def load_manifest(path=None):
    path = path or manifest_path()
    with io.open(path, encoding="utf-8") as handle:
        doc = json.load(handle)
    if doc.get("version") != 1:
        raise ForgedError("forged_manifest.json is version %s, expected 1" % doc.get("version"))
    return doc


# ----------------------------------------------------------------- appenders

def append_skill_line(data: bytes, line: dict):
    """The Hero line. Returns (bytes, added)."""
    count, fields, rec, records, strings = _split(data, SKILLLINE_FIELDS, "SkillLine.dbc")
    ids = _ids(records, rec, count)
    if line["id"] in ids:
        return _join(count, fields, rec, records, strings), 0

    row = bytearray(rec)
    struct.pack_into("<I", row, 0, line["id"])
    struct.pack_into("<I", row, 1 * 4, line["category"])
    struct.pack_into("<I", row, SL_ICON * 4, line["icon"])
    # the same name in every locale column, so a client of any locale reads it
    off = _add_string(strings, line["name"])
    for col in range(SL_NAME_FIRST, SL_NAME_MASK):
        struct.pack_into("<I", row, col * 4, off)
    struct.pack_into("<I", row, SL_NAME_MASK * 4, 0xFF)
    records += row
    return _join(count + 1, fields, rec, records, strings), 1


def append_visuals(data: bytes, visuals):
    """One SpellVisual row per recombination: the donor's row with the named
    kit slots pointed somewhere else. Returns (bytes, added, missing)."""
    count, fields, rec, records, strings = _split(data, SPELLVISUAL_FIELDS, "SpellVisual.dbc")
    ids = _ids(records, rec, count)
    added, missing = 0, []
    for v in visuals:
        if v["id"] in ids:
            continue
        base_row = ids.get(v["base"])
        if base_row is None:
            missing.append(v["base"])
            continue
        row = bytearray(records[base_row * rec:(base_row + 1) * rec])
        struct.pack_into("<I", row, 0, v["id"])
        for col, kit in v["kits"].items():
            struct.pack_into("<I", row, int(col) * 4, int(kit))
        records += row
        ids[v["id"]] = count
        count += 1
        added += 1
    return _join(count, fields, rec, records, strings), added, missing


# --------------------------------------------------------------------- apply

def apply(files, payload: dict, manifest: dict, report: list):
    """Add the forged spells to the patch payload. `files` is a
    clientfs.ClientFiles; `payload` maps archive paths to bytes and may already
    hold tables the elemental pass extended, which are extended again rather
    than replaced."""
    spells = [dict(s, fields=dict(s["fields"])) for s in manifest.get("spells", [])]
    if not spells:
        return payload

    report.append("  forged spells       generation %s: %d row(s) on the %s tab; the worldserver "
                  "logs the generation it loaded, and the two must match"
                  % (manifest.get("generation", "unknown"), len(spells),
                     manifest["skill_line"]["name"]))

    def table(path):
        """Build on the patched copy when an earlier pass made one."""
        if path in payload:
            return payload[path], "patched table"
        raw, _source = files.find(path)
        return raw, "archive"

    raw, _ = table(SKILLLINE)
    patched, added = append_skill_line(raw, manifest["skill_line"])
    payload[SKILLLINE] = patched
    report.append("    SkillLine.dbc     %d row added: the %s tab"
                  % (added, manifest["skill_line"]["name"]))

    visuals = manifest.get("visuals", [])
    if visuals:
        raw, _ = table(SPELLVISUAL)
        patched, added, missing = append_visuals(raw, visuals)
        payload[SPELLVISUAL] = patched
        report.append("    SpellVisual.dbc   %d recombined look(s)%s"
                      % (added, (", %d donor(s) missing" % len(missing)) if missing else ""))

    raw, _ = table(SPELL)
    patched, added, missing = append_spells(raw, spells)
    payload[SPELL] = patched
    if missing:
        raise ForgedError("Spell.dbc is missing %d donor row(s) the forged spells copy from "
                          "(first: %s). This client is not the 3.3.5a build the patch expects."
                          % (len(missing), missing[0]))
    report.append("    Spell.dbc         %d spell row(s)" % added)

    raw, _ = table(SKILLLINEABILITY)
    patched, added = append_skill_lines(raw, spells)
    payload[SKILLLINEABILITY] = patched
    report.append("    SkillLineAbility  %d row(s); hidden companions get none on purpose" % added)
    return payload
