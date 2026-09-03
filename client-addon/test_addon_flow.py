#!/usr/bin/env python3
"""Load the whole addon under Lua 5.1 against a stubbed WoW API and drive it
with server messages, without a game client.

syntaxcheck.py proves the addon parses and test_statpanel.py proves one pair of
text helpers. This goes further: it runs the file top to bottom the way the
client would, feeds it the same pipe-delimited messages the server sends, and
clicks its buttons, so a nil field or a wrong branch in a message handler
fails here instead of as a red error box in game.

The WoW API is faked with one generic "stub" object: any CapitalCase method
works (Show/Hide/IsShown/SetText/GetText/SetScript/Enable/Disable track their
state, size getters return numbers, everything else returns another stub), and
lowercase fields behave like a plain table so the addon's own bookkeeping on
frames is untouched. Only the API calls whose return values the addon reads
are spelled out.

Covered flows:
  * the Archetypes button and flyout (Classless only, mirrors the NPC's
    "Apply a starter archetype" menu)
  * the first-login wizard: path page, archetype page, sizing, empty slate

Run:  python3 test_addon_flow.py
"""
import io
import os
import sys

try:
    from lupa.lua51 import LuaRuntime
except ImportError:
    sys.exit("needs lupa: python3 -m pip install --user lupa")

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.join(HERE, "ClasslessWildcard", "ClasslessWildcard.lua")
PREFIX = "CWCL"
PLAYER = "Tester"

STUBS = r'''
SENT = {}      -- every addon message the addon sent, in order
FRAMES = {}    -- every CreateFrame result, in order

local NUMERIC = {
    GetWidth = true, GetHeight = true, GetLeft = true, GetRight = true, GetTop = true,
    GetBottom = true, GetScale = true, GetEffectiveScale = true, GetStringWidth = true,
    GetStringHeight = true, GetFrameLevel = true, GetID = true, GetValue = true,
    GetAlpha = true, GetNumPoints = true, GetSpacing = true, GetHorizontalScroll = true,
    GetVerticalScroll = true, GetVerticalScrollRange = true,
}

local Stub
local StubMT = {}
StubMT.__index = function(self, k)
    if type(k) ~= "string" or not k:sub(1, 1):match("%u") then
        return nil -- the addon's own fields on frames read as a plain table
    end
    if k == "Show" then return function(s) rawset(s, "__shown", true) end end
    if k == "Hide" then return function(s) rawset(s, "__shown", false) end end
    if k == "IsShown" or k == "IsVisible" then return function(s) return rawget(s, "__shown") end end
    if k == "SetScript" or k == "HookScript" then return function(s, n, f) rawget(s, "__scripts")[n] = f end end
    if k == "GetScript" then return function(s, n) return rawget(s, "__scripts")[n] end end
    if k == "RegisterEvent" then return function(s, e) rawget(s, "__events")[e] = true end end
    if k == "SetText" then return function(s, t) rawset(s, "__text", t) end end
    if k == "GetText" then return function(s) return rawget(s, "__text") end end
    if k == "Enable" then return function(s) rawset(s, "__enabled", true) end end
    if k == "Disable" then return function(s) rawset(s, "__enabled", false) end end
    if k == "IsEnabled" then return function(s) return rawget(s, "__enabled") ~= false and 1 or nil end end
    if k == "Click" then return function(s, ...) local f = rawget(s, "__scripts").OnClick; if f then f(s, ...) end end end
    if k == "GetName" then return function(s) return rawget(s, "__name") end end
    if k == "GetParent" then return function(s) return rawget(s, "__parent") end end
    if k == "GetObjectType" then return function(s) return rawget(s, "__kind") end end
    if k == "SetHeight" then return function(s, v) rawset(s, "__h", v) end end
    if k == "SetWidth" then return function(s, v) rawset(s, "__w", v) end end
    if k == "GetFont" then return function() return "Fonts\\FRIZQT__.TTF", 12, "" end end
    if k == "GetCenter" then return function() return 0, 0 end end
    if k == "GetPoint" then return function() return "CENTER", nil, "CENTER", 0, 0 end end
    if NUMERIC[k] then
        return function(s)
            if k == "GetHeight" then return rawget(s, "__h") or 0 end
            if k == "GetWidth" then return rawget(s, "__w") or 0 end
            return 0
        end
    end
    return function(s, ...) return Stub(k, nil, s) end
end
StubMT.__call = function(self, ...) return Stub("called") end

function Stub(kind, name, parent)
    local o = { __kind = kind or "Frame", __shown = true, __scripts = {}, __events = {},
                __text = "", __name = name, __parent = parent }
    setmetatable(o, StubMT)
    if type(name) == "string" then rawset(_G, name, o) end
    return o
end

function CreateFrame(kind, name, parent, template)
    local f = Stub(kind, name, parent)
    rawset(f, "__template", template)
    FRAMES[#FRAMES + 1] = f
    return f
end

-- any other CapitalCase global (UIParent, GameTooltip, Minimap, SpellBookFrame,
-- saved variables ...) springs into being as a stub on first touch
setmetatable(_G, { __index = function(t, k)
    if type(k) == "string" and k:sub(1, 1):match("%u") then
        local v = Stub(k)
        rawset(t, k, v)
        return v
    end
    return nil
end })

-- WoW's Lua aliases
tinsert, tremove = table.insert, table.remove
format, strlower, strupper, strlen, strsub, strfind, strmatch, gsub, strrep =
    string.format, string.lower, string.upper, string.len, string.sub, string.find, string.match, string.gsub, string.rep
floor, ceil, abs, max, min = math.floor, math.ceil, math.abs, math.max, math.min
function wipe(t) for k in pairs(t) do t[k] = nil end return t end
function strtrim(s) return (s:gsub("^%s+", ""):gsub("%s+$", "")) end
function strjoin(d, ...) return table.concat({ ... }, d) end
function strsplit(delim, s)
    local out, from = {}, 1
    local a, b = string.find(s, delim, from, true)
    while a do
        out[#out + 1] = string.sub(s, from, a - 1)
        from = b + 1
        a, b = string.find(s, delim, from, true)
    end
    out[#out + 1] = string.sub(s, from)
    return unpack(out)
end

-- API calls whose return values the addon reads
function SendAddonMessage(prefix, msg, channel, target) SENT[#SENT + 1] = msg end
function UnitName() return "''' + PLAYER + r'''" end
function UnitLevel() return 80 end
function UnitStat() return 10, 10, 0, 0 end
function UnitPower() return 100 end
function UnitPowerMax() return 100 end
function UnitPowerType() return 0, "MANA" end
function UnitClass() return "Paladin", "PALADIN", 2 end
function GetTime() return 100 end
function GetSpellInfo(id) return "Spell " .. tostring(id), "Rank 1", "Interface\\Icons\\INV_Misc_QuestionMark", 0, false, 0, 0, 0, 0 end
function GetCoinTextureString(c) return tostring(c) .. "c" end
function GetBindingKey() return nil end
function GetBindingAction() return "" end
function GetCurrentBindingSet() return 1 end
function SetBinding() return true end
function SaveBindings() end
function IsShiftKeyDown() return nil end
function InCombatLockdown() return false end
function GetCursorPosition() return 0, 0 end
function GetScreenWidth() return 1024 end
function GetScreenHeight() return 768 end
function MicroButtonTooltipText(a) return tostring(a) end
function hooksecurefunc() end
function PlaySound() end
function StaticPopup_Show(which) LAST_POPUP = which end
function GetItemInfo() return nil end
function GetItemCount() return 0 end
function GetComboPoints() return 0 end
function UnitHealth() return 100 end
function UnitHealthMax() return 100 end
function GetNumShapeshiftForms() return 0 end
function IsAddOnLoaded() return nil end
MAX_SKILLLINE_TABS = 8
'''

# A current-server state packet: mode, AE, TE, pity, chance, scrolls, level,
# deadline, rebirth on, rebirth cost, rerolls, universal resources, scroll
# cost, scroll buy allowed.
def state(mode, ae=12, te=3, level=20, rerolls=0, scroll_buy=0):
    return "S|%d|%d|%d|0|10|0|%d|5|1|50|%d|1|5000|%d" % (mode, ae, te, level, rerolls, scroll_buy)


class Harness:
    def __init__(self):
        self.rt = LuaRuntime(unpack_returned_tuples=True)
        self.rt.execute(STUBS)
        self.rt.execute(io.open(ADDON, encoding="utf-8").read())
        self.g = self.rt.globals()
        self.CW = self.g.ClasslessWildcard_API
        self.events = None
        for f in list(self.g.FRAMES.values()):
            if f["__events"]["CHAT_MSG_ADDON"] and f["__scripts"]["OnEvent"]:
                self.events = f
        assert self.events, "no frame listens for CHAT_MSG_ADDON"
        self.failures = 0

    def recv(self, msg):
        """Deliver one server message exactly as the client would."""
        self.events["__scripts"]["OnEvent"](self.events, "CHAT_MSG_ADDON", PREFIX, msg, "WHISPER", PLAYER)

    def click(self, button):
        button["__scripts"]["OnClick"](button)

    def sent(self):
        return [str(m) for m in self.g.SENT.values()]

    def clear_sent(self):
        self.rt.execute("SENT = {}")

    def check(self, cond, label):
        print("    %s %s" % ("ok  " if cond else "FAIL", label))
        if not cond:
            self.failures += 1


def test_archetypes(h):
    print("--- Archetypes button and flyout")
    CW, g = h.CW, h.g
    btn, fly, wizard = CW.archBtn, CW.archFly, g.ClasslessWildcardWizard
    h.check(btn["__shown"] is False and fly["__shown"] is False, "hidden before any state arrives")

    h.recv(state(0))
    h.check(btn["__shown"] is True, "Classless: Archetypes button shown")
    h.check(CW.buyScrollBtn["__shown"] is False, "Classless: Buy Scroll hidden (shares the slot)")

    h.clear_sent()
    h.click(btn)
    h.check("ARCH" in h.sent(), "click asks the server for the list (ARCH)")
    h.check(fly["__shown"] is True, "flyout opens")
    h.check(str(fly.intro["__text"]) == "Loading...", "flyout says Loading... until the reply")

    h.recv("AR|1|Blade Dancer|Fast melee striker: rogue strikes backed by warrior mobility.|26|71|0")
    h.recv("AR|2|Battle Mage|Armored caster: fireballs up close, sword in hand.|26|71|1")
    h.recv("ARE|")
    rows = fly.rows
    h.check(rows[1]["__shown"] is True and rows[2]["__shown"] is True and rows[3]["__shown"] is False,
            "two rows shown, the rest hidden")
    name1 = str(rows[1].name["__text"])
    h.check("Blade Dancer" in name1 and "26 abilities, 71 talent ranks" in str(rows[1].desc["__text"]),
            "row shows the name, and the counts under it: %r" % str(rows[1].desc["__text"]))
    h.check("following" in str(rows[2].name["__text"]) and str(rows[2].apply["__text"]) == "Stop",
            "the followed archetype is tagged and offers Stop")
    h.check(str(rows[1].apply["__text"]) == "Follow", "an unfollowed archetype offers Follow")
    h.clear_sent()
    h.click(rows[2].apply)
    h.check("ARCHAPPLY 0" in h.sent(), "Stop sends ARCHAPPLY 0")
    h.click(btn)
    h.check(str(rows[2].desc["__text"]).startswith("Armored caster"), "row shows the description")
    h.check(fly["__h"] == 72 + 2 * 46 + 8, "flyout sized to two rows (%s)" % fly["__h"])
    h.check(str(fly.intro["__text"]) == str(fly.INTRO), "intro text restored once the list arrives")
    h.check(wizard["__shown"] is False, "wizard stays closed (reply went to the flyout)")

    h.clear_sent()
    h.click(rows[1].apply)
    h.check("ARCHAPPLY 1" in h.sent(), "Follow sends ARCHAPPLY with the archetype id")
    h.check(fly["__shown"] is False, "flyout closes after Apply")
    h.check(str(CW.tab) == "HERO", "panel switches to the Hero tab to show the purchase")

    h.recv("OK|ARCH")
    h.recv(state(0, ae=2))
    h.check(CW.state.ae == 2, "OK + state refresh land without error")

    # a fresh list replaces the old one
    h.click(btn)
    h.recv("AR|3|Ranger of the Light|Hybrid archer-paladin.|25|71|0")
    h.recv("ARE|")
    h.check(rows[1]["__shown"] is True and rows[2]["__shown"] is False, "a new reply replaces the cached list")
    h.check("Ranger" in str(rows[1].name["__text"]), "row 1 is the new archetype")

    # empty realm
    h.recv("ARE|")
    h.check(rows[1]["__shown"] is False, "a reply with no rows clears the list")
    h.check("No archetypes" in str(fly.intro["__text"]), "empty list says so instead of Loading...")
    h.check(fly["__h"] == 72 + 46 + 8, "flyout keeps one row of height when empty")

    # the other flyouts close it and it closes them
    h.click(CW.helpBtn)
    h.check(fly["__shown"] is False and CW.helpFly["__shown"] is True, "Help closes the flyout")
    h.click(btn)
    h.check(fly["__shown"] is True and CW.helpFly["__shown"] is False, "Archetypes closes Help")
    g.ClasslessWildcardStats["__shown"] = True
    h.click(btn)  # toggles closed
    h.check(fly["__shown"] is False, "clicking again closes the flyout")

    # Wildcard and undecided hide everything
    h.click(btn)
    h.recv(state(1, rerolls=6, scroll_buy=1))
    h.check(btn["__shown"] is False and fly["__shown"] is False, "Wildcard: button and flyout hidden")
    h.check(CW.buyScrollBtn["__shown"] is True, "Wildcard: Buy Scroll takes the slot")
    h.recv(state(255))
    h.check(btn["__shown"] is False, "no path yet: button hidden")
    h.recv(state(0))
    h.check(btn["__shown"] is True, "back on Classless: button returns")


def test_wizard(h):
    print("--- first-login wizard: path page, then archetype page")
    CW, g = h.CW, h.g
    wizard, frame, rows = CW.wizard, g.ClasslessWildcardFrame, CW.wizArchRows
    frame["__shown"] = False
    h.recv(state(255, level=1))
    h.check(wizard["__shown"] is True, "no path chosen at level 1: wizard opens")
    h.check(wizard["__w"] == 420 and str(CW.wizTitle["__text"]) == "Choose Your Path, Hero", "page 1: path choice, 420 wide")

    h.clear_sent()
    h.click(CW.wizClassless)
    h.check("MODE 0" in h.sent() and "ARCH" in h.sent(), "Classless sends MODE 0 and asks for the archetypes")
    h.recv("AR|1|Blade Dancer|Fast melee striker: rogue strikes backed by warrior mobility.|26|71|0")
    h.recv("AR|2|Battle Mage|Armored caster: fireballs up close, sword in hand.|26|71|0")
    h.recv("ARE|")
    h.check(str(CW.wizTitle["__text"]) == "Pick a Starter Archetype", "page 2: archetype title")
    h.check(rows[1]["__shown"] is True and rows[2]["__shown"] is True and rows[3]["__shown"] is False, "two rows shown, the rest hidden")
    h.check(":" in str(rows[1].desc["__text"]), "description keeps its colon: %r" % str(rows[1].desc["__text"]))
    h.check(wizard["__w"] == 480 and wizard["__h"] == 84 + 2 * 46 + 52, "wizard resized to fit (%sx%s)" % (wizard["__w"], wizard["__h"]))
    h.check(CW.wizClassless["__shown"] is False and CW.wizLater["__shown"] is False and CW.wizArchSkip["__shown"] is True,
            "path buttons hidden, empty-slate button shown")
    h.check(CW.archFly["__shown"] is False, "panel flyout stays closed")

    h.clear_sent()
    h.click(rows[1].apply)
    h.check("ARCHAPPLY 1" in h.sent(), "Choose sends ARCHAPPLY with the id")
    h.check(wizard["__shown"] is False and frame["__shown"] is True and str(CW.tab) == "HERO", "wizard closes, panel opens on Hero")

    CW.ShowPathChoice()
    h.check(wizard["__w"] == 420 and wizard["__h"] == 300 and str(CW.wizTitle["__text"]) == "Choose Your Path, Hero",
            "page 1 again restores size and title")
    h.check(rows[1]["__shown"] is False and CW.wizArchSkip["__shown"] is False and CW.wizClassless["__shown"] is True,
            "page 1 again hides rows and shows the path buttons")

    h.recv("ARE|")  # a realm with no archetypes
    h.check("No archetypes" in str(CW.wizText["__text"]) and wizard["__h"] == 84 + 46 + 52, "empty list says so and keeps one row of height")
    frame["__shown"] = False
    h.click(CW.wizArchSkip)
    h.check(wizard["__shown"] is False and frame["__shown"] is True and str(CW.tab) == "ABIL", "empty slate closes the wizard and opens the browser")


def main():
    try:
        h = Harness()
    except Exception as e:  # a load-time error is a failure, not a crash
        print("FAIL: addon did not load: %s" % e)
        return 1
    print("addon loaded: %d frames" % len(h.g.FRAMES))
    test_archetypes(h)
    test_wizard(h)
    if h.failures:
        print("\n%d check(s) FAILED" % h.failures)
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
