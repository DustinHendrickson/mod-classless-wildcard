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
    # " ^ " breaks a paragraph and ~Words~ is a heading; neither belongs in the
    # rule, which is shown on one line
    need("^" not in ch["rule"] and "~" not in ch["rule"], "%s rule has no paragraph or heading marks" % name)
    for field in ("detail", "tips"):
        paragraphs = ch[field].split(" ^ ")
        need("^" not in "".join(paragraphs) and all(p.count("~") in (0, 2) and (p.count("~") == 0 or p.startswith("~"))
                                                   for p in paragraphs),
             "%s %s: every '^' is a paragraph break, every heading opens its paragraph" % (name, field))


def word(n):
    return WORDS.get(n, str(n))


# ---- Nemesis ----------------------------------------------------------------
print("--- Nemesis")
n = CH["Nemesis"]
cap = const(mgr, "NEMESIS_LEVEL_CAP", "Nemesis")
first = const(mgr, "NEMESIS_SCALE_FIRST", "Nemesis")
most = const(mgr, "NEMESIS_SCALE_MAX", "Nemesis")
charm_max = const(hdr, "NEMESIS_CHARM_MAX_RANK", "Nemesis")
max_strengths = const(hdr, "NEMESIS_MAX_STRENGTHS", "Nemesis")
conf = read("conf", "classless_wildcard.conf.dist")
cfgh = read("src", "ClasslessWildcard.h")
# the realm's own numbers go into the text through tokens ChallengeText fills
TOKENS = (("{nemesis_levels}", "ClasslessWildcard.Nemesis.MarkedLevels", "nemesisMarkedLevels"),
          ("{nemesis_bonus}", "ClasslessWildcard.Nemesis.MarkedBonusXpPct", "nemesisMarkedBonusXpPct"),
          ("{sworn_levels}", "ClasslessWildcard.Nemesis.SwornLevels", "nemesisSwornLevels"),
          ("{sworn_bonus}", "ClasslessWildcard.Nemesis.SwornBonusXpPct", "nemesisSwornBonusXpPct"),
          ("{sworn_below}", "ClasslessWildcard.Nemesis.SwornLevelsBelow", "nemesisSwornLevelsBelow"),
          ("{sworn_cooldown}", "ClasslessWildcard.Nemesis.SwornCooldownMinutes", "nemesisSwornCooldownMin"),
          ("{sworn_vengeance}", "ClasslessWildcard.Nemesis.SwornVengeancePct", "nemesisSwornVengeancePct"),
          ("{vengeance}", "ClasslessWildcard.Nemesis.VengeanceToFinish", "nemesisVengeanceToFinish"),
          ("{trophy_max}", "ClasslessWildcard.Nemesis.TrophyMax", "nemesisTrophyMax"))
for token, option, field in TOKENS:
    says(n, "detail", token, "%s fills it from %s" % ("ChallengeText", option))
    # the token filled from that very field, not just filled
    need(re.search(r'fill\("%s", [\w:]+\(cfg\.%s\)\);' % (re.escape(token), field), mgr) is not None,
         "ChallengeText fills %s from cfg.%s" % (token, field))
    shipped = re.search(r"^%s = (\d+)" % re.escape(option), conf, re.M)
    coded = re.search(r'GetOption<uint32>\("%s", (\d+)\)' % re.escape(option), mgr)
    member = re.search(r"\b%s = (\d+);" % field, cfgh)
    need(bool(shipped and coded and member) and shipped.group(1) == coded.group(1) == member.group(1),
         "%s: the conf, the code and the Config default agree (%s / %s / %s)"
         % (option, shipped and shipped.group(1), coded and coded.group(1), member and member.group(1)))
says(n, "rule", "{nemesis_levels} levels above you", "MarkNemesis: the Hero's level plus the offset")
need("ChallengeText(ch.rule)" in read("src", "ClasslessAddon.cpp") and "SanitizeText(sClasslessMgr->ChallengeText(raw))"
     in read("src", "ClasslessAddon.cpp"), "the addon is sent the filled text")
says(n, "detail", "a death takes nothing from you", "MarkNemesis takes no experience")
says(n, "detail", "stays that far above you as you level", "ResyncNemesisCopy follows the Hero's level")
says(n, "detail", "real higher level foe", "the copy's real level sets every roll")
need("player->SummonCreature(mark.entry, at ? *at : pos, TEMPSUMMON_CORPSE_TIMED_DESPAWN" in mgr
     and "nullptr, true);" in mgr, "the nemesis is a private copy, visible to its Hero alone")
need("NOTHING_DISPLAY_ID" in rules and "IsNemesisOriginalOf(target, creature)" in rules,
     "the original is drawn invisible for its Hero")
if first == 1.5 and most == 2:
    says(n, "detail", "up to twice its size", "NEMESIS_SCALE_MAX 2.0")
else:
    need(False, "the nemesis scale constants changed: say it in the Nemesis text, then teach this check")
# Vengeance: the goal, what a kill gives, and where it is counted
says(n, "rule", "{vengeance} Vengeance", "RunGoalMet: nemesisVengeanceToFinish")
says(n, "detail", "reach level 80 with {vengeance} Vengeance", "RunGoalMet: nemesisVengeanceToFinish")
need("return st.nemesisVengeance >= cfg.nemesisVengeanceToFinish;" in mgr, "RunGoalMet asks for the Vengeance")
need("uint32(creature->GetLevel()) * (sworn ? cfg.nemesisSwornVengeancePct : 100) / 100" in mgr,
     "a kill gives its level in Vengeance, the Sworn percent for a Sworn one")
says(n, "detail", "{marked_vengeance}, or {sworn_vengeance} for a Sworn one", "NemesisSlain's Vengeance")
need('fill("{marked_vengeance}", TimesLevel(100));' in mgr, "{marked_vengeance} is its level")
# traits
says(n, "detail", "gains another strength, up to %s" % word(max_strengths), "MarkNemesis: AddNemesisStrength, NEMESIS_MAX_STRENGTHS")
need("AddNemesisStrength(itr->second);" in mgr, "a death to the copy adds a strength")
says(n, "detail", "its strengths when a fight with it starts", "CopyEngages: LearnNemesis(NEMESIS_LEARNED_STRENGTHS)")
need("LearnNemesis(hero, copy, NEMESIS_LEARNED_STRENGTHS)" in rules, "strengths are learned on engage")
# Swear Vendetta
says(n, "detail", "Bloodlust, one more strength and a weakness", "SwearVendetta")
need("mark.strengths[0] = NS_BLOODLUST;\n    AddNemesisStrength(mark);\n    mark.weakness = RollNemesisWeakness();"
     in mgr.replace("\r\n", "\n"), "SwearVendetta gives Bloodlust, one more strength and a weakness")
says(n, "detail", "one Sworn nemesis at a time", "CanSwearVendetta refuses a second")
need('fail("You have a sworn nemesis already. Slay it first.")' in mgr, "CanSwearVendetta refuses a second Sworn")
says(n, "detail", "not an elite or a boss", "CanSwearVendetta")
need('fail("Not on an elite or a boss.")' in mgr and 'fail("Not in a dungeon or raid.")' in mgr,
     "CanSwearVendetta refuses elites, bosses and dungeons")
need("uint32(target->GetLevel()) + cfg.nemesisSwornLevelsBelow < player->GetLevel()" in mgr,
     "CanSwearVendetta measures how far below")
# the drop, trophies and the charm
says(n, "detail", "a Sworn one always drops a piece", "TryWorldDrop skips the roll for a Sworn copy")
need("if (!sworn && (chance <= 0.0f || !roll_chance_f(chance)))" in read("src", "ClasslessLoot.cpp"),
     "a Sworn nemesis skips the drop roll")
says(n, "detail", "a trophy of its newest strength", "NemesisSlain: strengths[strengthsHeld - 1]")
need("itr->second.strengths[strengthsHeld - 1]" in mgr, "the trophy is of the newest strength")
says(n, "detail", "a star for each strength it had and one more if it was Sworn, up to three", "NemesisSlain's stars")
need("std::min<uint32>(uint32(strengthsHeld) + (sworn ? 1 : 0), 3)" in mgr, "stars: strengths, one more if Sworn, up to 3")
says(n, "detail", "all of them add up", "ApplyNemesisFx sums every trophy's stars")
need("stars[TrophyStrength(entry)] += float(TrophyStars(entry));" in mgr, "every trophy's stars add up")
says(n, "detail", "no bank, trade, mail or sale", "the locks")
items = read("data", "sql", "db-world", "cw_world_nemesis_items.sql")
need(items.count(", 1, '") >= 22 and "`bonding`" in items, "trophies and the charm bind on pickup (no trade or mail)")
player_script = read("src", "ClasslessPlayerScript.cpp")
need(all(op in player_script for op in ("case CMSG_SWAP_ITEM:", "case CMSG_SWAP_INV_ITEM:", "case CMSG_AUTOBANK_ITEM:",
                                        "case CMSG_SPLIT_ITEM:")) and "SERVERHOOK_CAN_PACKET_RECEIVE" in player_script,
     "every bank move is refused for them")
need("PLAYERHOOK_CAN_SELL_ITEM" in read("src", "ClasslessLoot.cpp"), "they cannot be sold")
says(n, "detail", "cannot leave them or be destroyed", "CMSG_DESTROYITEM refuses the charm")
need('refuse("Your Nemesis Charm cannot be destroyed.")' in player_script, "the charm cannot be destroyed")
says(n, "detail", "up to %s in each" % word(charm_max), "NEMESIS_CHARM_MAX_RANK")
says(n, "detail", "the best trophy of each kind adds its stars", "EndNemesisTrophies merges the best of each kind")
need("std::max(best[TrophyStrength(item->GetEntry())]," in mgr, "the merge takes the best of each kind")
says(n, "detail", "A run that ends unfinished loses its trophies", "EndNemesisTrophies destroys them either way")
need("EndNemesisTrophies(player, finished);" in mgr, "EndRun ends the trophies, finished or not")
says(n, "detail", "dungeons and raids make no nemesis", "MarkNemesis refuses IsDungeon maps")
says(n, "detail", "elites, bosses", "MarkNemesis refuses isElite and bosses")
says(n, "detail", "red arrow over its head", "NEMESIS_TRACK_SPELL wears Hunter's Mark's arrow")
never(n, "up to thirty", "there is no total cap on levels")
never(n, "every creature of that kind", "a nemesis is the one creature, by spawn id")
never(n, "takes the experience in your bar", "a death takes nothing now")
never(n, "comes back to you", "nothing is taken, so nothing comes back")
never(n, "pet or group", "the copy is its Hero's alone: a group cannot see it")
never(n, "heads", "the run counts Vengeance, not heads")
never(n, "its head and", "a kill gives Vengeance and a trophy")
addon = read("client-addon", "ClasslessWildcard", "ClasslessWildcard.lua")
need("nemesis heads" not in addon.lower(), "the addon never says 'nemesis heads'")

# ---- Elite World --------------------------------------------------------------
print("--- Elite World")
e = CH["Elite World"]
need("bool ClasslessMgr::ChallengeViewOf" in mgr and "void OnPatchValuesUpdate(Unit const* unit" in rules
     and "UNITHOOK_ON_PATCH_VALUES_UPDATE" in rules and "UNITHOOK_SHOULD_TRACK_VALUES_UPDATE_POS_BY_INDEX" in rules,
     "Elite World and a nemesis are drawn per player (ChallengeViewOf, OnPatchValuesUpdate)")
need("CW_ViewDamageRatio" in rules and "CW_ViewHealthRatio" in rules and "void Exchange(" in rules,
     "and fought per player (Exchange)")
need("Acore::XP::BaseGain" in rules and "amount *= 2" in rules, "Elite World and a nemesis pay elite experience per player")
says(e, "rule", "elite for you", "ChallengeViewOf")
says(e, "detail", "for you alone", "ChallengeViewOf: per player")
says(e, "detail", "Other players see and fight", "per player: the creature never changes")
says(e, "detail", "elite experience", "OnPlayerGiveXP")
says(e, "detail", "Rares are rare elites", "ChallengeViewOf")
loot = read("src", "ClasslessLoot.cpp")
need("IsRareOrBoss(killed) || nemesisCopy || sClasslessMgr->ChallengeViewOf(killer, killed, view)" in loot
     and "ClasslessMgr::NemesisCopyOwner(killed) == killer->GetGUID()" in loot,
     "a nemesis and an Elite World enemy drop like rares for their Hero")
says(e, "detail", "drops classless gear as often as a rare, heirloom roll included", "TryWorldDrop reads ChallengeViewOf")
says(CH["Nemesis"], "detail", "drops classless gear as often as a rare, heirloom roll included", "TryWorldDrop reads ChallengeViewOf")
says(e, "detail", "already elite, rare elite or bosses are left as they are", "CW_EliteWorldCandidate")
never(e, "triple health", "the realm's elite rates set it, not a fixed number")
never(e, "anyone near you fights it as an elite", "Elite World is per player")
says(CH["Nemesis"], "detail", "for you alone", "the private copy")
says(CH["Nemesis"], "detail", "Other players see and fight it as it always was", "the private copy")
says(CH["Pursued"], "detail", "it harms no one else", "Exchange: the hunter fights its Hero alone")
says(CH["Legion"], "detail", "fight only you", "Exchange: reinforcements fight their Hero alone")
need("UNITHOOK_MODIFY_PERIODIC_DAMAGE_AURAS_TICK" in rules, "the damage rules cover damage over time")

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
        need(rank == "2", "the hunter is rare elite rank, as the text says (rank %s)" % rank)
says(p, "detail", "rare elite", "the hunter is releveled with the RAREELITE rates")
says(CH["Nemesis"], "detail", "rare elite", "the copy is releveled with the RAREELITE rates")
need("RATE_CREATURE_ELITE_RAREELITE_HP" in rules and "Creature::_GetDamageMod(int32(rank))" in rules,
     "CW_ReLevelCreature reads the realm's rates for the rank it is given")
need("CW_ReLevelCreature(copy, level, CREATURE_ELITE_RAREELITE)" in mgr and "CW_ReLevelCreature(hunter" in mgr
     and "NEMESIS_LEVEL_CAP)), CREATURE_ELITE_RAREELITE);" in mgr,
     "a nemesis's copy and the hunter are releveled as rare elites")

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
