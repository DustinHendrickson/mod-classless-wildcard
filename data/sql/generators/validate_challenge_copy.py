"""Check that every challenge's player-facing text says what its code does.

The challenge text lives in CHALLENGES (src/ClasslessMgr.cpp) and the README
table; the numbers it quotes live in the rule code (src/ClasslessChallenges.cpp,
src/ClasslessMgr.cpp, the headers). Each check below reads the number FROM THE
CODE and looks for it in the text, so a rule changed without its text fails
here, and so does text edited away from its rule.

It also refuses claims that were in the text and were wrong (an audit on
2026-10-14 found them against the code): add one here whenever a wrong claim
is fixed, so it cannot come back.

    python3 validate_challenge_copy.py        exit 1 on any failure
"""
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
SRC = os.path.join(ROOT, "src")
WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 15: "fifteen", 30: "thirty"}
FRACTIONS = {2: "half", 3: "a third", 4: "a quarter", 5: "a fifth"}

failures = []


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def const(text, name, where):
    m = re.search(r"\b%s\s*=\s*([0-9.]+)f?\b" % re.escape(name), text)
    if not m:
        failures.append("%s: constant %s not found, so its text cannot be checked" % (where, name))
        return None
    v = float(m.group(1))
    return int(v) if v.is_integer() else v


def need(cond, label):
    print("    %s %s" % ("ok  " if cond else "FAIL", label))
    if not cond:
        failures.append(label)


def says(ch, field, phrase, why):
    text = ch[field]
    need(phrase.lower() in text.lower(), "%s %s says %r (%s)" % (ch["name"], field, phrase, why))


def never(ch, phrase, why):
    for field in ("rule", "detail", "tips"):
        if phrase.lower() in ch[field].lower():
            need(False, "%s %s must not say %r (%s)" % (ch["name"], field, phrase, why))
            return
    need(True, "%s never says %r" % (ch["name"], phrase))


mgr = read("src", "ClasslessMgr.cpp")
rules = read("src", "ClasslessChallenges.cpp")
hdr = read("src", "ClasslessMgr.h") + read("src", "ClasslessWildcard.h")
readme = read("README.md")

# ---- the challenge entries --------------------------------------------------
STR = r'"((?:[^"\\]|\\.)*)"'
entry = re.compile(r"\{\s*(\d+),\s*" + STR + r",\s*" + STR + r",\s*(\w+),\s*" + STR + r",\s*(\d+),\s*(\d+),\s*"
                   + STR + r",\s*" + STR + r",\s*" + STR, re.S)
CH = {}
for m in entry.finditer(mgr):
    CH[m.group(3)] = dict(id=int(m.group(1)), key=m.group(2), name=m.group(3), lives=m.group(4), rule=m.group(5),
                          gold=int(m.group(6)), detail=m.group(9), tips=m.group(10))
need(len(CH) >= 13, "found the challenge entries (%d)" % len(CH))

ROWS = {}
for line in readme.splitlines():
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if len(cells) >= 6 and cells[0] in CH:
        ROWS[cells[0]] = dict(lives=cells[1], rule=cells[2], gold=cells[3])

print("--- every challenge: lives, gold, the README row, and the text's own format")
unlimited = "UNLIMITED_LIVES"
for name, ch in sorted(CH.items()):
    row = ROWS.get(name)
    need(row is not None, "%s has a README table row" % name)
    if ch["lives"] == unlimited:
        says(ch, "rule", "Unlimited lives", "UNLIMITED_LIVES")
        if row:
            need(row["lives"] == "Unlimited", "%s README lives is Unlimited (%s)" % (name, row["lives"]))
    elif row:
        need(row["lives"] == ch["lives"], "%s README lives %s matches the code's %s" % (name, row["lives"], ch["lives"]))
    if row:
        need(row["gold"] == str(ch["gold"]), "%s README gold %s matches the code's %d" % (name, row["gold"], ch["gold"]))
    # the addon splits the rule on ':' and ';', and the page text on '|'
    need(":" not in ch["rule"] and ";" not in ch["rule"], "%s rule has no ':' or ';'" % name)
    need("|" not in ch["detail"] + ch["tips"], "%s detail and tips have no '|'" % name)
    need("—" not in ch["rule"] + ch["detail"] + ch["tips"], "%s has no em dash" % name)


def word(n):
    return WORDS.get(n, str(n))


# ---- Nemesis ----------------------------------------------------------------
print("--- Nemesis")
n = CH["Nemesis"]
per_death = const(mgr, "NEMESIS_LEVELS_MAX_PER_DEATH", "Nemesis")
cap = const(mgr, "NEMESIS_LEVEL_CAP", "Nemesis")
first = const(mgr, "NEMESIS_SCALE_FIRST", "Nemesis")
most = const(mgr, "NEMESIS_SCALE_MAX", "Nemesis")
heads = const(hdr, "NEMESIS_HEADS_TO_FINISH", "Nemesis")
if per_death:
    says(n, "rule", "up to %s levels" % word(per_death), "NEMESIS_LEVELS_MAX_PER_DEATH")
    says(n, "detail", "%s for a full bar" % word(per_death), "NEMESIS_LEVELS_MAX_PER_DEATH")
    says(n, "detail", "one for an empty bar", "one level plus the quarters taken")
if cap:
    says(n, "detail", "up to level %d" % cap, "NEMESIS_LEVEL_CAP")
if first == 1.5:
    says(n, "detail", "half again as large", "NEMESIS_SCALE_FIRST 1.5")
else:
    need(False, "NEMESIS_SCALE_FIRST is %s: say the new size in the Nemesis text, then teach this check" % first)
if most == 2:
    says(n, "detail", "twice its size", "NEMESIS_SCALE_MAX 2.0")
else:
    need(False, "NEMESIS_SCALE_MAX is %s: say it in the Nemesis text, then teach this check" % most)
if heads:
    says(n, "detail", "%s heads" % word(heads), "NEMESIS_HEADS_TO_FINISH")
    says(n, "rule", "%s nemeses" % word(heads), "NEMESIS_HEADS_TO_FINISH")
says(n, "detail", "dungeons and raids make no nemesis", "MarkNemesis refuses IsDungeon maps")
says(n, "detail", "elites, bosses", "MarkNemesis refuses isElite and bosses")
never(n, "up to thirty", "there is no total cap on levels")
never(n, "every creature of that kind", "a nemesis is the one creature, by spawn id")

# ---- Elite World --------------------------------------------------------------
print("--- Elite World")
e = CH["Elite World"]
need("GetMaxHealth() * 3" in rules, "Elite World code triples health")
says(e, "rule", "triple health", "GetMaxHealth() * 3")
says(e, "rule", "double damage", "damage *= 2 for a creature hitting the Hero")
says(e, "detail", "damage over time", "Scale runs from ModifyPeriodicDamageAurasTick too")
need("UNITHOOK_MODIFY_PERIODIC_DAMAGE_AURAS_TICK" in rules, "the damage rules cover damage over time")
never(e, "is an elite", "the creature's rank is not changed")

# ---- Legion -------------------------------------------------------------------
print("--- Legion")
g = CH["Legion"]
called = const(rules, "LEGION_CALLED", "Legion")
if called:
    says(g, "rule", "%s more" % word(called), "LEGION_CALLED")
m = re.search(r"LEGION_LINGER_MS\s*=\s*(\d+)\s*\*\s*MINUTE", rules)
need(m is not None, "Legion linger time read from LEGION_LINGER_MS")
if m:
    says(g, "detail", "%s minutes" % word(int(m.group(1))), "LEGION_LINGER_MS")
says(g, "detail", "only once", "_legionCalled: once per life")

# ---- Pursued ------------------------------------------------------------------
print("--- Pursued")
p = CH["Pursued"]
lo = re.search(r"HUNTER_MIN_S\s*=\s*(\d+)\s*\*\s*MINUTE", mgr)
hi = re.search(r"HUNTER_MAX_S\s*=\s*(\d+)\s*\*\s*MINUTE", mgr)
grace = const(mgr, "HUNTER_LOGIN_GRACE_S", "Pursued")
need(bool(lo and hi), "Pursued clock read from HUNTER_MIN_S and HUNTER_MAX_S")
if lo and hi:
    says(p, "rule", "%s to %s minutes" % (lo.group(1), hi.group(1)), "HUNTER_MIN_S, HUNTER_MAX_S")
    says(p, "detail", "%s to %s minutes" % (lo.group(1), hi.group(1)), "HUNTER_MIN_S, HUNTER_MAX_S")
lv = re.search(r"GetLevel\(\) \+ (\d+), NEMESIS_LEVEL_CAP", mgr)
need(lv is not None, "Pursued hunter level offset found")
if lv:
    says(p, "rule", "%s levels above you" % word(int(lv.group(1))), "SpawnHunter level offset")
if grace:
    says(p, "detail", "%d seconds" % grace, "HUNTER_LOGIN_GRACE_S")
says(p, "detail", "changing maps", "a map change leaves the hunter behind")
hunter = re.search(r"HUNTER_ENTRY\s*=\s*(\d+)", hdr)
chsql = read("data", "sql", "db-world", "cw_world_challenges.sql")
vsql = read("data", "sql", "db-world", "cw_world_vendor_lists.sql")
if hunter:
    hid = hunter.group(1)
    need("(%s, 'Relentless Hunter'" % hid in chsql, "the hunter's row is entry %s, as the code spawns" % hid)
    need(hid not in vsql, "no vendor list claims the hunter's entry %s" % hid)
    row = re.search(r"\(%s, 'Relentless Hunter'[^)]*\)" % hid, chsql)
    cols = re.search(r"\(`entry`.*?\)\s*VALUES", chsql, re.S)
    if row and cols:
        names = re.findall(r"`(\w+)`", cols.group(0))
        vals = [v.strip() for v in row.group(0).strip("()").split(",")]
        rank = vals[names.index("rank")] if "rank" in names else "0"
        need(rank == "1", "the hunter is elite rank, as 'elite experience' says (rank %s)" % rank)

# ---- Hourglass ----------------------------------------------------------------
print("--- Hourglass")
h = CH["Hourglass"]
fn = re.search(r"uint32 HourglassLimit\(uint8 level\)\s*\{(.*?)\n    \}", rules, re.S)
need(fn is not None, "HourglassLimit found")
if fn:
    body = fn.group(1)
    below = re.search(r"level < (\d+)\)\s*return (\d+) \* MINUTE", body)
    above = re.search(r"level > (\d+)\)\s*return (\d+) \* MINUTE", body)
    mid = re.findall(r"return (\d+) \* MINUTE;\s*$", body.strip(), re.M)
    if below and above and mid:
        says(h, "detail", "Below level %s you have %s minutes" % (below.group(1), below.group(2)), "HourglassLimit")
        says(h, "detail", "past %s you have %s" % (above.group(1), above.group(2)), "HourglassLimit")
        says(h, "detail", "you have %s" % mid[-1], "HourglassLimit")
        says(h, "rule", "every %s minutes" % mid[-1], "HourglassLimit")
    else:
        need(False, "HourglassLimit's shape changed: teach this check")
warn = re.search(r"HOURGLASS_WARNING\s*=\s*(\d+)\s*\*\s*MINUTE", rules)
if warn:
    says(h, "detail", "%s minutes left" % word(int(warn.group(1))), "HOURGLASS_WARNING")

# ---- Glass, Spiteful, Bloodpact, Berserker -------------------------------------
print("--- Glass, Spiteful, Bloodpact, Berserker")
gl = CH["Glass"]
need("value * 0.5f" in rules, "Glass code halves max health")
says(gl, "rule", "halved", "value * 0.5f")
need("damage += damage / 3" in rules, "Glass code adds a third")
says(gl, "rule", "a third", "damage += damage / 3")
never(gl, "worth more than ever", "Stamina gives half its health under Glass")

sp = CH["Spiteful"]
pct = const(rules, "SPITEFUL_PCT", "Spiteful")
if pct:
    says(sp, "rule", FRACTIONS.get(100 // pct, "%d%%" % pct), "SPITEFUL_PCT")
never(sp, "Armor, absorbs", "the reflection is DealDamage, past armor and absorbs")
never(sp, "Absorb shields and healing over time soak", "the reflection is DealDamage, past armor and absorbs")

bp = CH["Bloodpact"]
leech = const(rules, "BLOODPACT_LEECH_PCT", "Bloodpact")
if leech:
    says(bp, "rule", "%d%%" % leech, "BLOODPACT_LEECH_PCT")
    says(bp, "detail", "%d%%" % leech, "BLOODPACT_LEECH_PCT")
never(bp, "potions and food is halved", "food regenerates through MOD_REGEN, never halved")
never(bp, "Resting to full is slow", "natural regeneration is untouched")

bz = CH["Berserker"]
low = const(rules, "BERSERKER_LOW", "Berserker")
high = const(rules, "BERSERKER_HIGH", "Berserker")
pen = const(rules, "BERSERKER_HIGH_PENALTY", "Berserker")
# whole phrases: a bare "30%" would be found in the penalty when the band moved
if low:
    says(bz, "rule", "Below %d%% health" % low, "BERSERKER_LOW")
    says(bz, "detail", "Below %d%% health" % low, "BERSERKER_LOW")
if high:
    says(bz, "rule", "Above %d%%" % high, "BERSERKER_HIGH")
    says(bz, "detail", "Above %d%% health" % high, "BERSERKER_HIGH")
if pen:
    says(bz, "rule", "%d%% less" % pen, "BERSERKER_HIGH_PENALTY")
    says(bz, "detail", "reduced by %d%%" % pen, "BERSERKER_HIGH_PENALTY")
never(bz, "nothing can slow you", "only snares break, on a hit, while below the low band")

# the leech, reflection and snare break answer the hit that landed
need("void OnDamage(Unit* attacker, Unit* victim" in rules and "UNITHOOK_ON_DAMAGE" in rules,
     "Bloodpact, Spiteful and Berserker's snare break run on the damage dealt (OnDamage)")

# ---- Ironman, Big Game Hunter, Hardcore ---------------------------------------
print("--- Ironman, Big Game Hunter, Hardcore")
im = CH["Ironman"]
need("Quality <= ITEM_QUALITY_NORMAL" in rules, "Ironman lets white and grey through")
says(im, "rule", "white and grey", "Quality <= ITEM_QUALITY_NORMAL")
if "Ironman" in ROWS:
    need("grey" in ROWS["Ironman"]["rule"], "Ironman README row says grey")

bg = CH["Big Game Hunter"]
says(bg, "rule", "give no XP", "normal rank kill XP is 0")
says(bg, "rule", "double", "quest XP doubled")

hc = CH["Hardcore"]
need("ch->lives + st.extraLife" in mgr, "a held extra life is added to a counted run")
says(hc, "rule", "extra life", "StartRun adds a held extra life, Hardcore included")
says(hc, "detail", "two if you hold an extra life", "StartRun adds a held extra life")

# ---- shared text ----------------------------------------------------------------
print("--- shared run text")
extra = const(hdr, "EXTRA_LIFE_SHARDS", "extra life")
if extra:
    need("%d shards" % extra in readme, "README prices the extra life at %d shards" % extra)
lua = read("client-addon", "ClasslessWildcard", "ClasslessWildcard.lua")
for wrong, why in (("counted lives", "two challenges have unlimited lives"),
                   ("fixed number of lives", "two challenges have unlimited lives"),
                   ("pays shards only", "a repeat run can still award the Unbroken")):
    need(wrong not in lua, "the addon never says %r (%s)" % (wrong, why))

print()
if failures:
    print("%d check(s) FAILED" % len(failures))
    sys.exit(1)
print("all challenge text matches its code")
