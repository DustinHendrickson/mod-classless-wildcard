#!/usr/bin/env python3
"""Render the stat-panel strings under Lua 5.1, without a game client.

The syntax checker only proves the addon parses. This proves the per-point text
a player actually reads comes out right, by lifting the Rate/StatPerPoint pair
straight out of the addon and running them against a stubbed CW.stats -- the
same shape the server fills in from the ST message.

Run:  python3 test_statpanel.py
"""
import io
import os
import re
import sys

try:
    from lupa.lua51 import LuaRuntime
except ImportError:
    sys.exit("needs lupa: python3 -m pip install --user lupa")

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.join(HERE, "ClasslessWildcard", "ClasslessWildcard.lua")

# The two functions under test, lifted verbatim so the test cannot drift from
# the shipped source.
START = "-- Trim a rate for display"
END = "local function BuildHelpText()"

# Chassis rates as the server computes them in ChassisAPRates, paired with the
# UniversalStats defaults.
CASES = [
    ("Paladin chassis, level 80 (real game-table values)",
     dict(uniStats=True, apPerAgi=1, rapPerAgi=1, spPerInt=0.5,
          strMeleeAP=2, agiMeleeAP=0, agiRangedAP=1,
          critPerAgi=0.0192, spellCritPerInt=0.0060,
          mp5PerSpi=0.473, hp5PerSpi=0.31)),
    ("Paladin chassis, level 20 (rates scale with level)",
     dict(uniStats=True, apPerAgi=1, rapPerAgi=1, spPerInt=0.5,
          strMeleeAP=2, agiMeleeAP=0, agiRangedAP=1,
          critPerAgi=0.1237, spellCritPerInt=0.0462,
          mp5PerSpi=0.467, hp5PerSpi=0.28)),
    ("Older server that sends no game-table rates",
     dict(uniStats=True, apPerAgi=1, rapPerAgi=1, spPerInt=0.5,
          strMeleeAP=2, agiMeleeAP=0, agiRangedAP=1)),
    ("Shaman chassis (Agility gives melee AP natively)",
     dict(uniStats=True, apPerAgi=1, rapPerAgi=1, spPerInt=0.5,
          strMeleeAP=1, agiMeleeAP=1, agiRangedAP=1)),
    ("UniversalStats disabled",
     dict(uniStats=False, apPerAgi=1, rapPerAgi=1, spPerInt=0.5,
          strMeleeAP=2, agiMeleeAP=0, agiRangedAP=1)),
]

NAMES = ["Strength", "Agility", "Stamina", "Intellect", "Spirit"]


def extract():
    src = io.open(ADDON, encoding="utf-8").read()
    i, j = src.index(START), src.index(END)
    return src[i:j]


def main():
    body = extract()
    failures = 0
    for label, stats in CASES:
        rt = LuaRuntime(unpack_returned_tuples=True)
        rt.execute("CW = { stats = {} }")
        for k, v in stats.items():
            rt.execute("CW.stats.%s = %s" % (k, "true" if v is True else
                                             "false" if v is False else v))
        # the functions are file-locals in the addon, so export from inside the
        # same chunk where they are still in scope
        rt.execute(body + "\n_G.StatPerPoint = StatPerPoint\n")
        fn = rt.globals().StatPerPoint
        print("--- %s" % label)
        for i in range(1, 6):
            text = fn(i)
            print("    %-10s %s" % (NAMES[i - 1], text))
            if not text or "nil" in str(text):
                print("    ^^ FAIL: empty or nil in output")
                failures += 1
        print()

    if failures:
        print("%d bad line(s)" % failures)
        return 1
    print("all stat lines render")
    return 0


if __name__ == "__main__":
    sys.exit(main())
