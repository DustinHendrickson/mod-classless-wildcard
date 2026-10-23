"""Runs the client patch's Talents key edit (lib/framexml.py pet_talents_key)
under Lua 5.1, against this client's own UIParent.lua: the file still
compiles, the edit is idempotent and goes on top of the bar-row edit, and
ToggleTalentFrame opens nothing without a pet that has talents (in combat
too, where the addon cannot close the window again) and opens the pet's spec
with one. The stock function runs as well, for contrast.

Usage: python test_talents_key.py "C:/path/to/World of Warcraft"
Needs lupa (python -m pip install --user lupa).
"""

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import clientfs, framexml  # noqa: E402
import install  # noqa: E402
from lupa import lua51  # noqa: E402

FAILS = []


def check(label, ok, detail=""):
    print("  [%s] %s%s" % ("ok  " if ok else "FAIL", label, (" -- " + detail) if detail else ""))
    if not ok:
        FAILS.append(label)


def function_text(lua_text, name):
    body = lua_text.replace("\r\n", "\n")
    start = body.index("function %s()" % name)
    return body[start:body.index("\nend\n", start) + 5]


def main():
    wow = sys.argv[1] if len(sys.argv) > 1 else r"B:\World.of.Warcraft.3.3.5a"
    data_dir = os.path.join(wow, "Data")
    own = set()
    for p in glob.glob(os.path.join(data_dir, "patch-*.MPQ")) + glob.glob(os.path.join(data_dir, "*", "patch-*.MPQ")):
        if install._is_our_archive(p):
            own.add(os.path.basename(p).lower())
    with clientfs.ClientFiles(data_dir, "enUS", exclude=own) as f:
        ui = f.find(framexml.UIPARENT_LUA)[0].decode("utf-8", "surrogateescape")
    ui2, changed = framexml.pet_talents_key(ui)
    check("the edit lands on this client", changed)
    check("and a second pass changes nothing", not framexml.pet_talents_key(ui2)[1])
    both, row = framexml.open_bar_row(ui)
    both, keyed = framexml.pet_talents_key(both)
    check("it goes on top of the bar-row edit", row and keyed)

    L = lua51.LuaRuntime()
    comp = L.eval("function(s) local f, e = loadstring(s) return f ~= nil, e end")
    ok, err = comp(ui2)
    check("the edited UIParent.lua compiles under Lua 5.1", ok, str(err or ""))
    ok, err = comp(both)
    check("so does it with both edits", ok, str(err or ""))

    # a small model: the level gate, the pet's talent groups, the error line,
    # and Blizzard_TalentUI's toggle as a record of what it was asked to open
    L.execute("""
SHOW_TALENT_LEVEL = 10
LEVEL, PET_GROUPS, COMBAT = 80, 0, nil
function UnitLevel() return LEVEL end
function GetNumTalentGroups(inspect, pet) if pet then return PET_GROUPS end return 1 end
function GetActiveTalentGroup() return 1 end
function InCombatLockdown() return COMBAT end
function TalentFrame_LoadUI() LOADED = true end
UIErrorsFrame = { AddMessage = function(self, m) table.insert(ERRORS, m) end }
function reset() ERRORS, OPENED, LOADED = {}, nil, nil end
function PlayerTalentFrame_Toggle(pet, group) OPENED = { pet = pet, group = group } end
""")

    def run(func_text):
        L.execute("reset()")
        L.execute(func_text)
        L.execute("ToggleTalentFrame()")
        g = L.globals()
        opened = g.OPENED
        return ((opened.pet, opened.group) if opened else None,
                [str(v) for v in g.ERRORS.values()])

    edited, stock = function_text(both, "ToggleTalentFrame"), function_text(ui, "ToggleTalentFrame")
    for combat in (None, 1):
        L.globals().COMBAT = combat
        when = "in combat" if combat else "out of combat"
        L.globals().PET_GROUPS = 0
        opened, errors = run(edited)
        check("no pet, %s: nothing opens" % when, opened is None, repr(opened))
        check("and one line says what the button is for", len(errors) == 1 and "tamed beast" in errors[0]
              and "\u2014" not in errors[0], repr(errors))
        L.globals().PET_GROUPS = 1
        opened, errors = run(edited)
        check("a pet with talents, %s: the pet's spec opens, with no line" % when,
              opened == (True, 1) and not errors, "%r %r" % (opened, errors))

    L.globals().COMBAT = 1
    L.globals().PET_GROUPS = 0
    opened, errors = run(stock)
    check("contrast: the stock function opens the player's spec with no pet, in combat",
          opened == (False, 1) and not errors, "%r %r" % (opened, errors))

    L.globals().LEVEL = 5
    opened, errors = run(edited)
    check("below the talent level it still does nothing at all",
          opened is None and not errors and not L.globals().LOADED, "%r %r" % (opened, errors))

    if FAILS:
        print("\nFAILED: " + ", ".join(FAILS))
        return 1
    print("\nall Talents key checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
