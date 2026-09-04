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
    if k == "SetAlpha" then return function(s, v) rawset(s, "__alpha", v) end end
    if k == "GetAlpha" then return function(s) return rawget(s, "__alpha") or 1 end end
    if k == "SetFrameLevel" then return function(s, v) rawset(s, "__level", v) end end
    if k == "GetFrameLevel" then return function(s) return rawget(s, "__level") or 0 end end
    if k == "SetTexCoord" then return function(s, ...) rawset(s, "__coord", {...}) end end
    if k == "SetVertexColor" then return function(s, r, g, b) rawset(s, "__rgb", {r, g, b}) end end
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
NOW = 100
function GetTime() return NOW end
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
SOUNDS = {}
function PlaySound(name) table.insert(SOUNDS, name) end
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
# cost, scroll buy allowed, free-reroll level.
def state(mode, ae=12, te=3, level=20, rerolls=0, scroll_buy=0, free_reroll=10):
    return "S|%d|%d|%d|0|10|0|%d|5|1|50|%d|1|5000|%d|%d" % (
        mode, ae, te, level, rerolls, scroll_buy, free_reroll)


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
    h.check("Blade Dancer" in name1 and "26 abilities, 71 talent ranks" in str(rows[1].counts["__text"]),
            "row shows the name, and the counts on their own line: %r" % str(rows[1].counts["__text"]))
    h.check(rows[1]["__h"] == 50 and rows[2]["__h"] == 50, "rows are sized from their text (%s)" % rows[1]["__h"])
    h.check("following" in str(rows[2].name["__text"]) and str(rows[2].apply["__text"]) == "Stop",
            "the followed archetype is tagged and offers Stop")
    h.check(str(rows[1].apply["__text"]) == "Follow", "an unfollowed archetype offers Follow")
    h.clear_sent()
    h.click(rows[2].apply)
    h.check("ARCHAPPLY 0" in h.sent(), "Stop sends ARCHAPPLY 0")
    h.click(btn)
    h.check(str(rows[2].desc["__text"]).startswith("Armored caster"), "row shows the description")
    h.check(fly["__h"] == 54 + 2 * 50 + 10, "flyout sized to intro plus two rows (%s)" % fly["__h"])
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
    h.check(fly.list.scroll["__h"] == 50 and fly.list.child["__h"] == 50, "one row: the list is one row tall, nothing to scroll")

    # the shipped realm sends thirteen: rows are made on demand and the list
    # scrolls instead of growing the flyout past the panel
    for i in range(1, 14):
        h.recv("AR|%d|Build %d|Description %d.|24|71|0" % (i, i, i))
    h.recv("ARE|")
    h.check(rows[13] is not None and rows[13]["__shown"] is True and rows[14] is None,
            "thirteen rows exist and show, no fourteenth")
    h.check("Build 13" in str(rows[13].name["__text"]), "row 13 is the last archetype")
    h.check(fly.list.child["__h"] == 13 * 50, "scroll child holds all thirteen (%s)" % fly.list.child["__h"])
    h.check(fly.list.scroll["__h"] == 440, "visible list capped at 440 (%s)" % fly.list.scroll["__h"])
    h.check(fly["__h"] == 54 + 440 + 10, "flyout sized to the capped list (%s)" % fly["__h"])
    h.clear_sent()
    h.click(rows[13].apply)
    h.check("ARCHAPPLY 13" in h.sent(), "a row past the old six still applies its own id")
    h.click(btn)

    # empty realm
    h.recv("ARE|")
    h.check(rows[1]["__shown"] is False, "a reply with no rows clears the list")
    h.check("No archetypes" in str(fly.intro["__text"]), "empty list says so instead of Loading...")
    h.check(fly["__h"] == 54 + 46 + 10, "flyout keeps one row of height when empty (%s)" % fly["__h"])

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
    h.check(wizard["__w"] == 480 and wizard["__h"] == 72 + 2 * 50 + 52, "wizard resized to fit (%sx%s)" % (wizard["__w"], wizard["__h"]))
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
    h.check(CW.wizArchList.scroll["__shown"] is False, "page 1 again hides the list")

    # thirteen archetypes: the wizard stops growing at the list cap and scrolls
    for i in range(1, 14):
        h.recv("AR|%d|Build %d|Description %d.|24|71|0" % (i, i, i))
    h.recv("ARE|")
    h.check(rows[13]["__shown"] is True and CW.wizArchList.scroll["__shown"] is True, "thirteen rows shown in the list")
    h.check(CW.wizArchList.scroll["__h"] == 440 and wizard["__h"] == 72 + 440 + 52,
            "wizard sized to the capped list (%s)" % wizard["__h"])
    h.clear_sent()
    h.click(rows[13].apply)
    h.check("ARCHAPPLY 13" in h.sent() and wizard["__shown"] is False, "choosing row 13 applies id 13 and closes the wizard")
    CW.ShowPathChoice()

    h.recv("ARE|")  # a realm with no archetypes
    h.check("No archetypes" in str(CW.wizText["__text"]) and wizard["__h"] == 72 + 46 + 52, "empty list says so and keeps one row of height (%s)" % wizard["__h"])
    frame["__shown"] = False
    h.click(CW.wizArchSkip)
    h.check(wizard["__shown"] is False and frame["__shown"] is True and str(CW.tab) == "ABIL", "empty slate closes the wizard and opens the browser")


def test_browser(h):
    print("--- browser sort and filter buttons, panel art refresh")
    CW, g = h.CW, h.g
    frame = g.ClasslessWildcardFrame
    h.recv(state(0))
    h.clear_sent()
    CW.SetTab("ABIL")
    h.check("ABIL 1 0 0 0" in h.sent(), "default request: class 1, page 0, level ascending, all types")
    h.clear_sent()
    for _ in range(4):
        h.click(CW.abilSortBtn)
    h.check(str(CW.abilSortBtn["__text"]) == "By type" and "ABIL 1 0 4 0" in h.sent(),
            "four clicks reach By type and re-request page 0 (%s)" % str(CW.abilSortBtn["__text"]))
    h.clear_sent()
    h.click(CW.abilTypeBtn)
    h.check(str(CW.abilTypeBtn["__text"]) == "Melee" and "ABIL 1 0 4 2" in h.sent(), "type filter Melee sends type 2")
    h.recv("AB|1|0|1|100:0:1:0:0:4:1;72:0:2:0:0:12:1;")
    sub = str(CW.abilEntries[1].sub["__text"])
    h.check("Melee" in sub and "1 Ability Essence" in sub, "rows carry the type while filtering: %r" % sub)
    h.click(CW.abilSortBtn)
    h.check(str(CW.abilSortBtn["__text"]) == "Level 1-80", "the sort cycles back to level ascending")
    g.ClasslessWildcardDB.abilType = 1
    CW.LoadBrowseChoices()
    h.check(CW.abilType == 1 and str(CW.abilTypeBtn["__text"]) == "All", "saved choices reload with a valid value")

    h.recv("TB|161:1;")
    h.clear_sent()
    h.recv("TBE|")
    h.check("TAL 161 0 0" in h.sent(), "tabs arriving request the tree in tier order")
    h.clear_sent()
    for _ in range(4):
        h.click(CW.talSortBtn)
    h.check(str(CW.talSortBtn["__text"]) == "By type" and "TAL 161 0 4" in h.sent(), "talent sort cycles to By type")
    h.recv("TL|161|0|1|1234:12294:0:0:1:6:1;1235:12295:0:0:3:0:0;")
    subs = [str(CW.talEntries[i].sub["__text"]) for i in (1, 2)]
    h.check("Active" in subs[0] and "Passive" in subs[1], "talent rows are tagged Active / Passive: %r" % subs)

    frame["__scripts"]["OnShow"](frame)
    h.recv(state(0))
    h.check(callable(CW.RefreshPanelArt), "panel art refresh is wired")

    # stat tooltip: chassis and module rates together, so melee and ranged differ
    h.recv("ST|10|4|1|0|0|0|0|0|1|1|1|1|0.5|2|0|1|0.0192|0.006|0.473|0.31")
    agi = str(CW.StatContribution(2, 20))
    h.check(agi == "+20 melee and +40 ranged attack power", "Agility tooltip counts the chassis ranged AP too: %r" % agi)
    h.check(str(CW.StatContribution(1, 20)) == "+40 melee attack power, +10 block value", "Strength tooltip shows its attack power")
    h.recv("ST|10|4|1|0|0|0|0|0|1|0|1|1|0.5|2|0|1|0.0192|0.006|0.473|0.31")
    h.check(str(CW.StatContribution(2, 20)) == "+20 ranged attack power", "with the universal layer off only the chassis ranged AP remains")


def test_state_packet(h):
    print("--- state packet: read by position, extra fields ignored")
    CW = h.CW
    h.recv(state(0, ae=7, te=2, level=22, rerolls=4, scroll_buy=1))
    s = CW.state
    h.check(s.ae == 7 and s.te == 2, "essences read")
    h.check(s.rerolls == 4, "rerolls read from field 12 (%s)" % s.rerolls)
    h.check(s.universalResources == 1, "universal resources read from field 13")
    h.check(s.scrollCost == 5000, "scroll cost read from field 14 (%s)" % s.scrollCost)
    h.check(s.scrollBuy == 1, "scroll buy read from field 15")

    h.check(s.freeReroll == 10, "free-reroll level read from field 16 (%s)" % s.freeReroll)

    # a server that grows the packet must not shift anything already parsed:
    # this is the case the old 16-field back-compat branch got wrong
    h.recv(state(0, ae=7, te=2, level=22, rerolls=4, scroll_buy=1) + "|99|123")
    s = CW.state
    h.check(s.rerolls == 4 and s.universalResources == 1 and s.scrollCost == 5000
            and s.scrollBuy == 1, "two extra fields change nothing")

    # a realm that moved the free-reroll level: the hand window follows the
    # server, it is not hard-coded at 10 any more
    h.recv(state(1, level=12, free_reroll=15))
    h.check(CW.CanShowHand() is True, "hand window follows Wildcard.FreeRerollLevel (level 12 of 15)")
    h.recv(state(1, level=12, free_reroll=10))
    h.check(CW.CanShowHand() is False, "and closes when the server says it is over")


def test_auto_hand(h):
    print("--- starting hand opens for a Hero the server put on Wildcard")
    CW, g = h.CW, h.g
    hand = CW.handFrame
    hand["__shown"] = False
    h.rt.execute("ClasslessWildcardCharDB = {}")   # a character that has never seen it

    # no MODE was ever sent: this is AllowModeChoice = 0, or the level deadline
    h.recv(state(1, level=4))
    h.check(hand["__shown"] is True, "hand opens with no MODE round trip")

    hand["__shown"] = False
    h.recv(state(1, level=4))
    h.check(hand["__shown"] is False, "and does not reopen once the character has seen it")

    h.rt.execute("ClasslessWildcardCharDB = {}")
    h.recv(state(0, level=4))
    h.check(hand["__shown"] is False, "a Classless Hero is never shown the hand")

    h.rt.execute("ClasslessWildcardCharDB = {}")
    h.recv(state(1, level=30))
    h.check(hand["__shown"] is False, "nor a Wildcard Hero past the free-reroll level")


def test_hand_animation(h):
    print("--- the die rolls the row and deals as it passes")
    CW = h.CW
    hand, die, slots = CW.handFrame, CW.handDie, CW.handSlots

    def step(dt):
        h.rt.execute("NOW = NOW + %r" % dt)
        hand["__scripts"]["OnUpdate"](hand, dt)

    h.recv(state(1, level=4))
    hand["__shown"] = True
    hand["__scripts"]["OnShow"](hand)
    h.recv("OA|133:0:0:1;772:0:0:1;1752:0:0:1;686:0:0:1;")
    h.recv("OAE|")

    a = CW.handAnim
    h.check(a is not None and str(a.phase) == "in", "starts off the row, bouncing in")
    h.check(die["__shown"] is True and die["__alpha"] == 0, "die starts invisible")
    h.check(all(s["__alpha"] == 0 for s in [slots[i] for i in range(1, 5)]),
            "no card is showing yet")

    # ride in: the die must travel right, and still deal nothing
    step(0.3)
    h.check(CW.handAnim.popped[1] is None, "nothing dealt during the run-in")
    h.check(die["__alpha"] > 0, "die fades in on the way (%.2f)" % die["__alpha"])

    step(0.3)
    h.check(str(CW.handAnim.phase) == "roll", "reaches the first card and starts rolling")
    h.check(CW.handAnim.popped[1] is not None, "card 1 dealt as the die arrives")
    h.check(CW.handAnim.popped[4] is None, "card 4 not dealt yet")

    step(0.5)
    p = CW.handAnim.popped
    h.check(p[2] is not None and p[4] is None,
            "the row keeps dealing, and the last card is still to come")

    step(0.5)
    h.check(CW.handAnim.popped[4] is not None, "the last card deals as the die reaches it")
    h.check(str(CW.handAnim.phase) == "out", "then the die runs on past the row")

    times = [CW.handAnim.popped[i] for i in range(1, 5)]
    step(0.31)
    h.check(die["__shown"] is False, "die is gone once it has left the row")

    step(0.3)
    h.check(CW.handAnim is None, "animation ends once every card has settled")
    h.check(all(slots[i]["__alpha"] == 1 for i in range(1, 5)), "all four cards fully shown")
    h.check(times == sorted(times) and len(times) == 4,
            "and they were dealt strictly left to right (%s)" % (times,))


def test_hand_tiers(h):
    print("--- the hand deals each card in its own tier")
    CW = h.CW
    hand, slots = CW.handFrame, CW.handSlots

    def step(dt):
        h.rt.execute("NOW = NOW + %r" % dt)
        hand["__scripts"]["OnUpdate"](hand, dt)

    h.recv(state(1, level=4))
    hand["__shown"] = True
    h.rt.execute("SOUNDS = {}")
    hand["__scripts"]["OnShow"](hand)
    # common, rare, epic, legendary -- dealt in that order, left to right
    h.recv("OA|133:0:0:1;772:2:0:1;1752:3:0:1;686:4:0:1;")
    h.recv("OAE|")
    for _ in range(12):
        step(0.2)

    h.check(CW.handAnim is None, "the deal finishes")
    snd = [str(x) for x in h.rt.globals().SOUNDS.values()]
    h.check(snd == ["igMainMenuOptionCheckBoxOn", "QUESTCOMPLETED", "LEVELUPSOUND",
                    "PVPTHROUGHQUEUE", "LEVELUPSOUND"],
            "each card played its own tier's sound (%s)" % snd)

    h.check(slots[1].glow["__shown"] is False, "the common card settles plain")
    h.check(slots[2].glow["__shown"] is True and slots[2].rays["__shown"] is False,
            "the rare card keeps a glow but no starburst")
    h.check(slots[4].glow["__shown"] is True and slots[4].rays["__shown"] is True,
            "the legendary card keeps both")
    rgb = [round(v, 2) for v in slots[4].glow["__rgb"].values()]
    h.check(rgb == [1, 0.5, 0], "and wears the legendary colour (%s)" % rgb)
    h.check(slots[4].glow["__alpha"] > slots[2].glow["__alpha"],
            "brighter the better the card (%.2f vs %.2f)"
            % (slots[4].glow["__alpha"], slots[2].glow["__alpha"]))

    before = [round(v, 4) for v in slots[4].rays["__coord"].values()]
    step(0.25)
    after = [round(v, 4) for v in slots[4].rays["__coord"].values()]
    h.check(CW.handAnim is None and before != after,
            "the starburst keeps turning while the hand sits open")

    # stacking: dressing under every card, cards under the die
    h.rt.execute("""
        local CW = ClasslessWildcard_API
        local H = CW.handFrame
        PARENTS_OK = CW.handDie:GetParent() == H.dieLayer
                 and CW.handSlots[1].glow:GetParent() == H.fxLayer
                 and CW.handSlots[1].rays:GetParent() == H.fxLayer
                 and CW.handSlots[4].glow:GetParent() == H.fxLayer
        FX_LVL, CARD_LVL, DIE_LVL =
            H.fxLayer:GetFrameLevel(), CW.handSlots[1]:GetFrameLevel(), H.dieLayer:GetFrameLevel()
    """)
    g = h.rt.globals()
    h.check(bool(g.PARENTS_OK), "every card's glow lives on the shared layer, the die on its own")
    h.check(g.FX_LVL < g.CARD_LVL, "dressing draws under the cards (%d < %d)" % (g.FX_LVL, g.CARD_LVL))
    h.check(g.CARD_LVL < g.DIE_LVL,
            "and the die draws over them, so it reveals the row from in front (%d < %d)"
            % (g.CARD_LVL, g.DIE_LVL))


def test_reveal_tooltip(h):
    print("--- the reveal says what the ability does, without a hover")
    CW = h.CW
    reveal = CW.revealFrame

    # stand a real tooltip up for the scanner to read
    h.rt.execute("""
        local tip = ClasslessWildcardScanTip
        tip.NumLines = function() return 5 end
        tip.ClearLines = function() end
        tip.SetHyperlink = function() end
        local LEFT  = { "Battle Shout", "10 Rage", "Instant",
                        "Requires Battle Stance",
                        "The warrior shouts, increasing attack power." }
        local RIGHT = { nil, "Melee Range", nil, nil, nil }
        for i = 1, 5 do
            _G["ClasslessWildcardScanTipTextLeft" .. i] = {
                GetText = function() return LEFT[i] end,
                GetTextColor = function() return 1, 0.82, 0 end,
            }
            _G["ClasslessWildcardScanTipTextRight" .. i] = {
                GetText = function() return RIGHT[i] end,
            }
        end
        SCANNED = ClasslessWildcard_API.revealFX.ScanSpell(6673)
    """)
    g = h.rt.globals()
    lines = [dict(left=r["left"], right=r["right"]) for r in g.SCANNED.values()]
    h.check(len(lines) == 4, "the name is skipped, the other four lines are read (%d)" % len(lines))
    h.check(lines[0]["left"] == "10 Rage" and lines[0]["right"] == "Melee Range",
            "cost and range land on the same row, opposite ends")
    h.check(lines[2]["left"] == "Requires Battle Stance", "the stance requirement is kept")
    h.check("increasing attack power" in lines[3]["left"], "and so is the description")

    # now run a reveal and check the rows actually carry it
    h.rt.execute("""
        local CW = ClasslessWildcard_API
        CW.suppressReveals = false
        CW.pendingHand = nil
        CW.revealQueue = {}
        CW.revealAnim.phase = "idle"
        CW.revealAnim.awaiting = false
        CW.revealFrame:Hide()
        CW.EnqueueReveal({ isTalent = false, entry = 6673, spell = 6673, rarity = 1, flags = 0 })
    """)
    for dt in (1.7, 0.05, 0.4):
        h.rt.execute("NOW = NOW + %r" % dt)
        reveal["__scripts"]["OnUpdate"](reveal, dt)

    info = CW.revealFX.info
    h.check(str(info[1].left["__text"]) == "10 Rage" and info[1].left["__shown"] is True,
            "the block is filled in on the result (%s)" % info[1].left["__text"])
    h.check(str(info[1].right["__text"]) == "Melee Range", "right column too")
    h.check(str(info[4].left["__text"]).startswith("The warrior shouts"),
            "description included")
    h.check(info[5].left["__shown"] is False and str(info[5].left["__text"]) == "",
            "unused rows are blanked, not just hidden")

    # a fresh spin must not leave the last ability's text on screen
    h.rt.execute("ClasslessWildcard_API.revealFX.HideInfo()")
    h.check(info[1].left["__shown"] is False and str(info[1].left["__text"]) == "",
            "and cleared before the next roll")


def test_reveal_tiers(h):
    print("--- a better roll puts on a bigger show")
    CW, g = h.CW, h.g
    reveal, fx = CW.revealFrame, CW.revealFX

    def run(rarity):
        # the hand test left reveals suppressed, and a queued reveal only
        # starts when nothing is on screen
        h.rt.execute("""
            SOUNDS = {}
            local CW = ClasslessWildcard_API
            CW.suppressReveals = false
            CW.pendingHand = nil
            CW.revealQueue = {}
            CW.revealAnim.phase = "idle"
            CW.revealAnim.awaiting = false
            CW.revealFrame:Hide()
            CW.EnqueueReveal({ isTalent = false, entry = 133, spell = 133,
                               rarity = %d, flags = 0 })
        """ % rarity)
        # spin, then the frame that lands the tier, then settle
        for dt in (1.7, 0.05, 0.05, 0.4):
            h.rt.execute("NOW = NOW + %r" % dt)
            reveal["__scripts"]["OnUpdate"](reveal, dt)
        return [str(x) for x in h.rt.globals().SOUNDS.values()]

    h.recv(state(1, level=20))

    snd = run(0)
    h.check(fx.rays["__shown"] is False, "common: no starburst")
    h.check(snd == ["igMainMenuOptionCheckBoxOn"], "common: one quiet tick (%s)" % snd)

    snd = run(2)
    h.check(fx.rays["__shown"] is True, "rare: starburst lights up")
    h.check(fx.rays2["__shown"] is False, "rare: only the one layer")
    h.check(snd == ["QUESTCOMPLETED"], "rare: its own sound (%s)" % snd)

    snd = run(4)
    h.check(fx.rays["__shown"] is True and fx.rays2["__shown"] is True,
            "legendary: both layers turning")
    h.check(len(snd) == 2, "legendary: two sounds layered (%s)" % snd)
    h.check(fx.rays["__alpha"] > 0.4, "legendary: brightest starburst (%.2f)" % fx.rays["__alpha"])
    rgb = [round(v, 2) for v in fx.rays["__rgb"].values()]
    h.check(rgb == [1, 0.5, 0], "legendary: starburst wears the rarity colour (%s)" % rgb)

    # the two layers must actually be turning, and against each other
    before = [round(v, 4) for v in fx.rays["__coord"].values()]
    before2 = [round(v, 4) for v in fx.rays2["__coord"].values()]
    h.rt.execute("NOW = NOW + 0.2")
    reveal["__scripts"]["OnUpdate"](reveal, 0.2)
    after = [round(v, 4) for v in fx.rays["__coord"].values()]
    after2 = [round(v, 4) for v in fx.rays2["__coord"].values()]
    h.check(len(after) == 8 and before != after, "the starburst rotates")
    h.check(before2 != after2 and after2 != after, "the second layer turns the other way")

    # brightness has to climb with the tier, not just be present
    peaks = [h.rt.eval("ClasslessWildcard_API.revealFX.Tier(%d).rays" % r) for r in range(5)]
    h.check(peaks == sorted(peaks) and peaks[0] == 0 and peaks[4] > peaks[3],
            "each tier is brighter than the one below (%s)" % peaks)


def test_starting_hand(h):
    print("--- starting hand: only the cards the Wildcard dealt")
    CW, g = h.CW, h.g
    hand, frame = CW.handFrame, g.ClasslessWildcardFrame

    h.recv(state(1, level=3))          # Wildcard hero, below the level 10 cut-off
    hand["__shown"] = True
    h.clear_sent()
    hand["__scripts"]["OnShow"](hand)
    h.check("OWN" in h.sent(), "opening the hand asks the server for the build")
    h.check(frame["__shown"] is False, "the panel steps aside while the hand is up")

    # four dealt abilities, plus Battle Stance (source 3) which came free with
    # one of them and a talent-granted line (source 2)
    h.recv("OA|133:0:0:1;772:0:0:1;1752:0:0:1;686:0:1:1;2457:0:0:3;11366:0:0:2;")
    h.recv("OAE|")
    order = [int(v) for v in CW.handOrder.values()]
    h.check(len(order) == 4, "four cards for four rolls, not six (%d)" % len(order))
    h.check(2457 not in order, "the free stance is not a card")
    h.check(11366 not in order, "a talent's ability is not a card")

    # rolling again brings in another companion: the hand must stay four wide
    h.recv("OA|133:0:0:1;772:0:0:1;1752:0:0:1;686:0:1:1;2457:0:0:3;768:0:0:3;1082:0:0:3;")
    h.recv("OAE|")
    order = [int(v) for v in CW.handOrder.values()]
    h.check(len(order) == 4, "more companions do not widen the hand (%d)" % len(order))
    h.check(686 in order, "a locked card keeps its place")

    frame["__shown"] = False
    h.click(CW.handKeep)
    h.check(hand["__shown"] is False, "Keep Abilities closes the hand")
    h.check(frame["__shown"] is False, "Keep Abilities does not open the advancement panel")


def main():
    try:
        h = Harness()
    except Exception as e:  # a load-time error is a failure, not a crash
        print("FAIL: addon did not load: %s" % e)
        return 1
    print("addon loaded: %d frames" % len(h.g.FRAMES))
    test_archetypes(h)
    test_wizard(h)
    test_browser(h)
    test_state_packet(h)
    test_auto_hand(h)
    test_hand_animation(h)
    test_hand_tiers(h)
    test_reveal_tooltip(h)
    test_reveal_tiers(h)
    test_starting_hand(h)
    if h.failures:
        print("\n%d check(s) FAILED" % h.failures)
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
