"""Runs the client patch's bar-row edits (lib/framexml.py open_bar_row and
open_pet_bar_row) under Lua 5.1, against this client's own UIParent.lua and
PetActionBarFrame.lua: both files still compile, the edit is idempotent, and
the new layout block puts the totem bar where it should go with a stance bar,
more than ten forms, a pet bar, a full row, and the possess bar.

Usage: python test_bar_row.py "C:/path/to/World of Warcraft"
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


def main():
    wow = sys.argv[1] if len(sys.argv) > 1 else r"B:\World.of.Warcraft.3.3.5a"
    data_dir = os.path.join(wow, "Data")
    own = set()
    for p in glob.glob(os.path.join(data_dir, "patch-*.MPQ")) + glob.glob(os.path.join(data_dir, "*", "patch-*.MPQ")):
        if install._is_our_archive(p):
            own.add(os.path.basename(p).lower())
    with clientfs.ClientFiles(data_dir, "enUS", exclude=own) as f:
        ui = f.find(framexml.UIPARENT_LUA)[0].decode("utf-8", "surrogateescape")
        pb = f.find(framexml.PETBAR_LUA)[0].decode("utf-8", "surrogateescape")
    ui2, c1 = framexml.open_bar_row(ui)
    pb2, c2 = framexml.open_pet_bar_row(pb)
    check("both edits land on this client", c1 and c2)
    check("and a second pass changes nothing",
          not framexml.open_bar_row(ui2)[1] and not framexml.open_pet_bar_row(pb2)[1])

    L = lua51.LuaRuntime()
    comp = L.eval("function(s) local f, e = loadstring(s) return f ~= nil, e end")
    ok, err = comp(ui2)
    check("the edited UIParent.lua compiles under Lua 5.1", ok, str(err or ""))
    ok, err = comp(pb2)
    check("the edited PetActionBarFrame.lua compiles under Lua 5.1", ok, str(err or ""))

    # a small model: ten stock stance buttons 38 apart, the bars, and the calls
    L.execute("""
min, max = math.min, math.max
NUM_SHAPESHIFT_SLOTS = 10
local function btn(left, right) return { GetLeft = function() return left end, GetRight = function() return right end } end
for i = 1, 10 do _G["ShapeshiftButton" .. i] = btn(30 + (i - 1) * 38, 60 + (i - 1) * 38) end
MainMenuBar = { GetLeft = function() return 0 end, GetWidth = function() return 1024 end }
function makeFrame(w, h) local f = { shown = false, w = w, h = h }
  function f:IsShown() return self.shown end
  function f:GetWidth() return self.w end
  function f:GetHeight() return self.h end
  function f:GetParent() return MainMenuBar end
  function f:SetPoint(...) self.point = { ... } end
  return f end
ShapeshiftBarFrame = makeFrame(0, 0)
PetActionBarFrame = makeFrame(380, 40)
PossessBarFrame = makeFrame(0, 0)
MultiCastActionBarFrame = makeFrame(230, 38)
FORMS = 3
function GetNumShapeshiftForms() return FORMS end
function HasMultiCastActionBar() return true end
function PetActionBarFrame_IsAboveShapeshift() return nil end
function PetActionBar_UpdatePositionValues() PETACTIONBAR_XPOS = ShapeshiftBar_RowRight() + 20 end
SHOWN, HIDDEN = 0, 0
function ShowMultiCastActionBar() SHOWN = SHOWN + 1 end
function HideMultiCastActionBar() HIDDEN = HIDDEN + 1 end
""")
    # the helper exactly as the edit appends it, and the new block as a function
    L.execute(framexml._ROW_RIGHT)
    L.execute("function RunBlock() MULTICASTACTIONBAR_YPOS = 0\n" + framexml._TOTEM_ROW + "\nend")
    g = L.globals()

    def run(**kw):
        for k, v in kw.items():
            L.execute(k + " = " + v)
        L.execute("SHOWN, HIDDEN = 0, 0; MultiCastActionBarFrame.point = nil; RunBlock()")
        return g.MULTICASTACTIONBAR_XPOS, g.MULTICASTACTIONBAR_YPOS, g.SHOWN, g.HIDDEN

    r = run(**{"ShapeshiftBarFrame.shown": "true", "FORMS": "3"})
    check("three forms: the totem bar starts 12 past the third button", r == (60 + 2 * 38 + 12, 0, 1, 0), str(r))
    r = run(**{"FORMS": "13"})
    check("thirteen forms: past the thirteenth, at the stock stride", r[0] == 60 + 12 * 38 + 12, str(r))
    r = run(**{"FORMS": "3", "PetActionBarFrame.shown": "true"})
    check("a pet bar: the totem bar goes after it", r[0] == (60 + 2 * 38 + 20) + 380 + 12, str(r))
    r = run(**{"PetActionBarFrame.w": "700"})
    check("the row full: one row up, in Blizzard's own place", r[:2] == (30, 38 + 4), str(r))
    r = run(**{"PetActionBarFrame.shown": "false", "MultiCastActionBarFrame.shown": "true",
               "MultiCastActionBarFrame.state": "'top'"})
    pt = L.eval("MultiCastActionBarFrame.point and MultiCastActionBarFrame.point[4]")
    check("a bar already up is moved straight away", pt == r[0] and r[2] == 1, str((pt, r)))
    r = run(**{"ShapeshiftBarFrame.shown": "false"})
    check("no stance bar: Blizzard's own place", r[:3] == (30, 0, 1), str(r))
    r = run(**{"ShapeshiftBarFrame.shown": "true", "PossessBarFrame.shown": "true"})
    check("the possess bar still hides it", r[3] == 1 and r[2] == 0, str(r))

    # the stock block, for contrast: a stance bar hid the totem bar
    L.execute("function RunStock() MULTICASTACTIONBAR_YPOS = 0\n" + framexml._TOTEM_HACK + "\nend")
    L.execute("PossessBarFrame.shown = false; ShapeshiftBarFrame.shown = true; SHOWN, HIDDEN = 0, 0; RunStock()")
    check("the stock block hides the totem bar with a stance bar up (the bug this fixes)",
          g.HIDDEN == 1 and g.SHOWN == 0)

    if FAILS:
        print("\nFAILED: " + ", ".join(FAILS))
        return 1
    print("\nall bar row checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
