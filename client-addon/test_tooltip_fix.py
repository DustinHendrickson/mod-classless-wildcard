#!/usr/bin/env python3
"""Drive the tooltip corrections end to end, without a game client.

A Hero's talents come from every class and the client will not apply their
modifiers to a tooltip: SMSG_SET_FLAT_SPELL_MODIFIER carries a class-mask bit
and no family, and the client only ever expected its own class's talents.
Thunder Clap read 20 Rage with Improved Thunder Clap at 3/3 while the server
charged 16. So the server sends the real numbers as SC records and the addon
puts them on the tooltip.

test_addon_flow.py stubs hooksecurefunc as a no-op, so it can prove a message
parses but not that a tooltip moves. This reuses its stubs and swaps in a real
hooksecurefunc plus a GameTooltip that keeps its lines, so the whole path runs
the way the client runs it: a CHAT_MSG_ADDON body in, a rendered line out.

Run:  python3 test_tooltip_fix.py
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
FLOW = os.path.join(HERE, "test_addon_flow.py")
PREFIX = "CWCL"
PLAYER = "Tester"

# The flow harness's stubs, lifted verbatim so this cannot drift from the API
# the rest of the addon is tested against. It builds them as a Python
# concatenation, so the one interpolated name is put back by hand.
_lines = io.open(FLOW, encoding="utf-8").read().splitlines(True)
_a = next(i for i, x in enumerate(_lines) if x.startswith("STUBS = r")) + 1
_b = next(i for i, x in enumerate(_lines) if i > _a and x.rstrip() == "'''")
STUBS = "".join(_lines[_a:_b]).replace("''' + PLAYER + r'''", PLAYER)
assert _b > _a, "could not find the stub block in test_addon_flow.py"
assert "PLAYER" not in STUBS, "stub extraction left a Python fragment in the Lua"

# What the flow harness deliberately leaves out: real post-hooks, and a tooltip
# whose TextLeftN font strings can be read back.
TIP = """
MANA, RAGE, ENERGY, FOCUS = "Mana", "Rage", "Energy", "Focus"
RUNIC_POWER, HEALTH, RUNES = "Runic Power", "Health", "Runes"

function hooksecurefunc(tbl, name, post)
    if type(tbl) == "string" then tbl, name, post = _G, tbl, name end
    local orig = tbl[name]
    tbl[name] = function(...) local r = orig(...) post(...) return r end
end

GameTooltip = { lines = {}, shown = false }
function GameTooltip:GetName() return "GameTooltip" end
function GameTooltip:Show() self.shown = true end

-- rawset, because the stubs give _G an __index that conjures CapitalCase
-- globals: without it a cleared line comes back as a stub instead of nil
local function put(i, text)
    GameTooltip.lines[i] = text
    rawset(_G, "GameTooltipTextLeft" .. i, {
        GetText = function() return GameTooltip.lines[i] end,
        SetText = function(_, t) GameTooltip.lines[i] = t end,
    })
end
function GameTooltip:AddLine(t) put(#self.lines + 1, t) end

-- a spell tooltip as the client builds it: name, cost, range, cast time
function GameTooltip:Reset()
    for i = 1, 12 do rawset(_G, "GameTooltipTextLeft" .. i, nil) end
    self.lines, self.shown = {}, false
    put(1, "Thunder Clap")
    put(2, "20 Rage")
    put(3, "Melee Range")
    put(4, "Instant")
end
function GameTooltip:SetSpell(slot, book) self:Reset() end
function GameTooltip:SetAction(slot) self:Reset() end
function GameTooltip:SetHyperlink(link) self:Reset() end
function GameTooltip:Dump() return table.concat(self.lines, " | ") end
"""

PLAIN = "Thunder Clap | 20 Rage | Melee Range | Instant"

rt = LuaRuntime(unpack_returned_tuples=True)
rt.execute(STUBS)
rt.execute(TIP)
rt.execute(io.open(ADDON, encoding="utf-8").read())
G = rt.globals()

EVENTS = None
for _f in list(G.FRAMES.values()):
    if _f["__events"]["CHAT_MSG_ADDON"] and _f["__scripts"]["OnEvent"]:
        EVENTS = _f
assert EVENTS, "no frame listens for CHAT_MSG_ADDON"

FAILURES = []


def recv(msg):
    """Deliver one server message exactly as the client would."""
    EVENTS["__scripts"]["OnEvent"](EVENTS, "CHAT_MSG_ADDON", PREFIX, msg, "WHISPER", PLAYER)


def check(cond, label):
    print("    %s %s" % ("ok  " if cond else "FAIL", label))
    if not cond:
        FAILURES.append(label)


def test_feed():
    print("--- The SC feed")
    rt.execute('GameTooltip:SetHyperlink("spell:6343")')
    check(rt.eval("GameTooltip:Dump()") == PLAIN, "untouched before any correction arrives")

    recv("SC|6343:16:0:0:30;47502:10:1500:6000:0;")
    check(bool(rt.eval("ClasslessWildcard_API._collectingFix")), "SC opens a collection")

    f = rt.eval("ClasslessWildcard_API.spellFix[6343]")
    check(f is not None and f.cost == 16 and f.dmg == 30,
          "6343 parsed (cost %s, dmg %s)" % (f and f.cost, f and f.dmg))
    f = rt.eval("ClasslessWildcard_API.spellFix[47502]")
    check(f is not None and f.cast == 1500 and f.cd == 6000,
          "47502 parsed (cast %s, cooldown %s)" % (f and f.cast, f and f.cd))
    check(rt.eval('ClasslessWildcard_API.spellFixByName["Spell 6343|Rank 1"]') == 6343,
          "the name index is built, for the routes that only know a name")

    recv("SCE|")
    check(rt.eval("ClasslessWildcard_API._collectingFix") is False, "SCE closes the collection")


def test_tooltip():
    print("--- What the player reads")
    rt.execute('GameTooltip:SetHyperlink("spell:6343")')
    dump = rt.eval("GameTooltip:Dump()")
    print("      %s" % dump)
    check("16 Rage" in dump and "20 Rage" not in dump, "the cost is rewritten in place, the unit word kept")
    check("+30% damage" in dump, "damage is appended as its own line")
    check(rt.eval("GameTooltip.shown") is True, "the tooltip is re-shown, so the added line is measured")

    rt.execute('GameTooltip:SetHyperlink("spell:1234")')
    check(rt.eval("GameTooltip:Dump()") == PLAIN, "a spell with no correction is left alone")
    rt.execute('GameTooltip:SetHyperlink("item:6343")')
    check(rt.eval("GameTooltip:Dump()") == PLAIN, "an item link with the same id is not taken for a spell")

    # the spellbook route has no id to work from: GetSpellName(1) reports
    # "Spell1", "Rank 2", and the feed is keyed on the name GetSpellInfo gives
    recv("SC|9999:5:0:0:0;")
    recv("SCE|")
    rt.execute('ClasslessWildcard_API.spellFixByName["Spell1|Rank 2"] = 9999')
    rt.execute("GameTooltip:SetSpell(1, BOOKTYPE_SPELL)")
    check("5 Rage" in rt.eval("GameTooltip:Dump()"), "the spellbook route resolves by name and rank")


def test_appended():
    print("--- Appended, never rewritten")
    recv("SC|6343:0:1500:6000:0;")
    recv("SCE|")
    rt.execute('GameTooltip:SetHyperlink("spell:6343")')
    dump = rt.eval("GameTooltip:Dump()")
    print("      %s" % dump)
    check("6 sec cooldown" in dump and "1.5 sec cast" in dump,
          "cooldown and cast time are appended, whatever the locale formats them as")
    check("Instant" in dump, "and the client's own timing line is left exactly as it wrote it")
    check(rt.eval("ClasslessWildcard_API.spellFix[47502]") is None,
          "a later feed replaces the table, it does not merge into it")


def main():
    test_feed()
    test_tooltip()
    test_appended()
    if FAILURES:
        print("\n%d check(s) FAILED" % len(FAILURES))
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
