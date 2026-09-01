"""Pick artwork that actually belongs to the item.

`displayid` is the single field driving both an item's inventory icon and its
3D model and texture. Nothing in item_template ties it to `class`, `subclass`
or `InventoryType`, so a row can call itself a Thrown weapon and wear a
two-handed axe's model. Several of ours did.

The only safe source of a display id is a real item of the same
(class, subclass, slot): if Blizzard hangs that art on a mail chestpiece, it is
mail chest art, model and texture included.

Two extra preferences on top of that:

  * item level. Picking art by level means band-1 gear looks like starter gear
    and band-80 gear looks like raid gear, instead of a level 1 Hero carrying a
    tier 10 model.
  * name. A candidate whose real name shares words with ours ("Longbow",
    "Javelin", "Gauntlets") is the one a player would expect to see.

The parsed pool is cached in displays_pool.json so the 40 MB core dump is only
read when it changes.
"""
import io, json, os, re, collections

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = r"B:\code\azerothcore-wotlk\data\sql\base\db_world\item_template.sql"
CACHE = os.path.join(HERE, "displays_pool.json")

# entry,class,subclass,SoundOverride,name,displayid,Quality,Flags,FlagsExtra,
# BuyCount,BuyPrice,SellPrice,InventoryType,AllowableClass,AllowableRace,ItemLevel
ROW = re.compile(
    r"\((\d+),(\d+),(\d+),(-?\d+),'((?:[^'\\]|\\.)*)',(\d+),(\d+),(\d+),(\d+),"
    r"(\d+),(-?\d+),(\d+),(\d+),(-?\d+),(-?\d+),(\d+),")

# Slots that genuinely share one model: the game reuses the same art for both.
SLOT_ALIAS = {20: 5,                 # robe uses chest art
              21: 13, 22: 13,        # main-hand / off-hand use one-hand art
              23: 23}

STOP = {"of", "the", "a", "an", "and", "s"}

# Placeholder, NPC-only and cut content. The art behind these is often a
# development stub, and even when it renders it is not something to sell.
JUNK = re.compile(r"^(monster|npc equip|deprecated|test|old|unused|qa)\b"
                  r"|\btest\b|\bdeprecated\b|\[|\bDNT\b|^zzold"
                  # internal build names: "BT59 Plate Physical Chest4",
                  # "90 Epic Rogue Dagger", "D3 Warrior Legs"
                  r"|^(bt|pvp|d)\d|^\d+\s|\bphysical (chest|legs|head)\b"
                  r"|\b(placeholder|dummy|proto|internal)\b", re.I)


def norm_slot(inv):
    return SLOT_ALIAS.get(inv, inv)


def words(name):
    return {w for w in re.findall(r"[a-z]+", name.lower()) if w not in STOP}


def head_noun(name):
    """The word that says what the thing is.

    Item names put it either last ("Warlord's Heavy Javelin") or immediately
    before an "of" phrase ("Longbow of the Mendicant"), so take whichever comes
    first.
    """
    ws = [w for w in re.findall(r"[a-z]+", name.lower()) if w != "s"]
    if not ws:
        return ""
    low = name.lower()
    if " of " in low:
        before = [w for w in re.findall(r"[a-z]+", low.split(" of ")[0])
                  if w != "s"]
        if before:
            return before[-1]
    return ws[-1]


def _akin(a, b):
    return a == b or (len(a) >= 4 and len(b) >= 4 and (a in b or b in a))


def name_match(myname, theirname):
    """How well two item names agree, allowing compound words.

    The head noun dominates: a Javelin should look like a javelin even if some
    Heavy Throwing Dagger shares the word "Heavy". Beyond that, exact shared
    words score, and a word containing another (four letters or more, to keep
    "war" inside "sword" from counting) half-scores, so "Handcannon" finds a
    "Hand Cannon".
    """
    mine, theirs = words(myname), words(theirname)
    score = 2 * len(mine & theirs)
    for a in mine - theirs:
        if len(a) >= 4 and any(_akin(a, b) for b in theirs - mine):
            score += 1
    head = head_noun(myname)
    if head and any(_akin(head, w) for w in theirs):
        score += 8
    return score


def _build():
    pool = collections.defaultdict(dict)
    txt = io.open(CORE, encoding="utf-8", errors="replace").read()
    for m in ROW.finditer(txt):
        cls, sub = int(m.group(2)), int(m.group(3))
        name, disp, qual = m.group(5), int(m.group(6)), int(m.group(7))
        inv, ilvl = int(m.group(13)), int(m.group(16))
        if not disp or cls not in (2, 4) or not inv or JUNK.search(name):
            continue
        key = "%d/%d/%d" % (cls, sub, norm_slot(inv))
        # keep the best-looking example of each display: highest quality wins,
        # so the remembered name is a real named item rather than a vendor grey
        cur = pool[key].get(disp)
        if cur is None or qual > cur[2]:
            pool[key][disp] = (name, ilvl, qual)
    return {k: [[d, v[0], v[1], v[2]] for d, v in sorted(v.items())]
            for k, v in pool.items()}


def load(rebuild=False):
    if not rebuild and os.path.exists(CACHE):
        if os.path.getmtime(CACHE) > os.path.getmtime(CORE):
            return json.load(io.open(CACHE, encoding="utf-8"))
    pool = _build()
    io.open(CACHE, "w", encoding="utf-8").write(json.dumps(pool, sort_keys=True))
    return pool


POOL = load()


def candidates(cls, sub, inv):
    return POOL.get("%d/%d/%d" % (cls, sub, norm_slot(inv)), [])


def pick(cls, sub, inv, name, ilvl=None, exclude=(), count=1, by_level=False):
    """Best display ids for an item of this type, name and level.

    Returns `count` display ids, most suitable first. Empty if nothing in the
    game has this class/subclass/slot combination at all -- which means the
    item itself is describing something that does not exist.

    `by_level` puts the target level ahead of the name. Heirlooms want that:
    matching "Cloth Robe" by name lands on a level 20 rag, when what the item
    needs is something that looks worth its price.
    """
    cands = [c for c in candidates(cls, sub, inv) if c[0] not in exclude]
    if not cands:
        return []

    def score(c):
        disp, cname, cilvl, qual = c
        shared = name_match(name, cname)
        near = abs((cilvl or 1) - ilvl) if ilvl is not None else 0
        if by_level:
            return (near > 25, -shared, near, -qual, disp)
        return (-shared, near, -qual, disp)

    cands.sort(key=score)
    return [c[0] for c in cands[:count]]


def spread(cls, sub, inv, name, levels, exclude=()):
    """One display id per level, walking the art upward with the level.

    Sorting the candidate art by its own item level and sampling across it
    means low bands get low-level looking gear and the top band gets the art
    from real endgame items.
    """
    cands = [c for c in candidates(cls, sub, inv) if c[0] not in exclude]
    if not cands:
        return []
    # prefer art from items that are the same kind of thing by name (a head
    # noun match, score 8), but never at the cost of having enough distinct
    # looks to cover every band
    named = [c for c in cands if name_match(name, c[1]) >= 8]
    if len(named) >= len(levels):
        cands = named
    cands.sort(key=lambda c: (c[2], -c[3], c[0]))
    out, n = [], len(cands)
    for i in range(len(levels)):
        out.append(cands[min(n - 1, i * n // len(levels))][0])
    return out


if __name__ == "__main__":
    pool = load(rebuild=True)
    print("display pool: %d class/subclass/slot combinations" % len(pool))
    for key in sorted(pool, key=lambda k: -len(pool[k]))[:8]:
        print("  %-10s %5d looks" % (key, len(pool[key])))
