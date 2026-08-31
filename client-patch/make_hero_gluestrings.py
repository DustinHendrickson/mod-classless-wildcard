#!/usr/bin/env python3
"""Rewrite the character-creation class description to the classless "Hero"
pitch, in place, inside a client GlueStrings.lua.

The 3.3.5a client shows a per-class blurb on the creation screen, pulled from
CLASS_INFO_* / <CLASS>_* string globals in Interface\\GlueXML\\GlueStrings.lua.
Because our chassis is Warrior, players see the Warrior text. This script
replaces the Warrior strings with Hero text, leaving every other line intact.

USAGE
    1. Extract the original from your client (mpqtool built by build_mpqtool.sh):
         mpqtool extract "Data\\enUS\\locale-enUS.MPQ" \\
             "Interface\\GlueXML\\GlueStrings.lua" GlueStrings.lua
       (locale folder/name varies: enUS, enGB, etc.)
    2. Rewrite it:
         python3 make_hero_gluestrings.py GlueStrings.lua GlueStrings_hero.lua
    3. Pack it:
         mpqtool create patch-enUS-4.MPQ \\
             "GlueStrings_hero.lua@Interface\\GlueXML\\GlueStrings.lua"
    4. Drop patch-enUS-4.MPQ into Data\\enUS\\ .

REQUIRES a client whose WoW.exe skips the GlueXML signature check (standard on
custom-server client packs; a stock client shows "Login interface corrupted").
Test first with the ChrClasses "Hero" rename only — if that loads, glue patches
are accepted.
"""
import re, sys

# Warrior string globals -> replacement text. Keys are matched as
# `KEY = "..."` assignments; only these lines are rewritten.
HERO = {
    "WARRIOR":            "Hero",
    "CLASS_WARRIOR":      "Hero",
    # the creation-screen info block (3.3.5 uses INFO_ tables; some locales
    # inline the blurb into a single string — both handled)
    "WARRIOR_INFO_TEXT":
        "A Hero belongs to no class. Every spell, talent, weapon and armor "
        "type of every class is yours to learn or roll.\n\n"
        "- Role: anything. Tank, healer, caster or melee - you decide.\n"
        "- Wears every armor type and wields every weapon.\n"
        "- Maintains mana, rage AND energy at once.\n"
        "- Allocate your own primary stats; every stat matters.\n"
        "- Gain power through Ability Essence, or let the Wildcard roll for you.",
    "WARRIOR_ROLE_TANK":   "Any Role",
    "WARRIOR_ROLE_DAMAGE": "Any Role",
}

def rewrite(text):
    changed = 0
    def repl(m):
        nonlocal changed
        key, q = m.group("key"), m.group("q")
        if key in HERO:
            changed += 1
            val = (HERO[key]
                   .replace("\\", "\\\\")
                   .replace(q, "\\" + q)
                   .replace("\n", "\\n"))  # keep it a single valid Lua string
            return f'{key} = {q}{val}{q}'
        return m.group(0)
    # match:  KEY = "..."   or   KEY = '...'
    pat = re.compile(r'(?P<key>[A-Z0-9_]+)\s*=\s*(?P<q>["\'])(?:\\.|(?!\2).)*\2')
    out = pat.sub(repl, text)
    return out, changed

def main():
    if len(sys.argv) != 3:
        print(__doc__); sys.exit(1)
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, encoding="utf-8", errors="replace") as f:
        text = f.read()
    out, n = rewrite(text)
    # append explicit Hero globals so custom CharacterCreate code can use them
    out += (
        "\n-- ClasslessWildcard additions\n"
        'CLASS_HERO = "Hero";\n'
        'HERO_INFO_TEXT = WARRIOR_INFO_TEXT;\n'
    )
    with open(dst, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"rewrote {n} Warrior string(s) -> Hero; wrote {dst}")
    if n == 0:
        print("WARNING: no Warrior strings matched — your locale may name them "
              "differently. Open the file and grep for the Warrior blurb, then "
              "add its key(s) to the HERO dict at the top of this script.")

if __name__ == "__main__":
    main()
