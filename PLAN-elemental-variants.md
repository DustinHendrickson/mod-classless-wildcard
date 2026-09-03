# Elemental ability variants: build plan

Every physical strike in the pool gets elemental siblings: **Fiery Sinister Strike**,
**Frozen Heroic Strike**, **Venomous Backstab**. A variant keeps the base ability's cast,
cooldown, cost, animation and rank chain, but deals its damage as the element instead of
Physical, trades some weapon damage for an elemental add that scales with spell power, and
carries one short rider the element is known for. Seven elements: Fire, Frost, Earth, Poison,
Arcane, Shadow and Holy. Variants roll and are bought like any other ability, one rarity tier
above their base.

This is a plan, not an implementation. Every id and field below was read from the client's
own 3.3.5a DBCs and the core's `SpellEntry` layout, so the numbers are real; the design
decisions are marked as such and are open to change.

---

## 1. What the game already gives us

The design is not new mechanics. It is one existing spell shape, applied at scale.

### 1.1 The template: Frost Strike (49143)

```
school=Frost   dmgClass=2 (melee)   visual=11612
effect0: NORMALIZED_WEAPON_DMG (121)  base=86     -> normalized weapon damage, +87 flat
effect1: WEAPON_PERCENT_DAMAGE (31)   base=54     -> the whole thing at 55%
Description: "Instantly strike the enemy, causing $s2% weapon damage plus ${$m1*$m2/100} as Frost damage."
```

`Spell::EffectWeaponDmg` folds every weapon effect on a spell into one calculation: flat
adds (`WEAPON_DAMAGE` 58, `NORMALIZED_WEAPON_DMG` 121) accumulate, a `WEAPON_PERCENT_DAMAGE`
(31) scales the total, and 121 additionally normalizes for weapon speed. So Frost Strike is
one melee attack (melee hit and crit tables, attack power, needs a weapon) whose damage is
**dealt as Frost**: mitigated by frost resistance rather than armour, boosted by anything that
increases frost damage, coloured frost in the combat log. That is exactly an "elemental
variant" of a strike, and Blizzard shipped it. Every variant we make is this shape with a
different base and a different school.

### 1.2 The riders: one existing aura per element

Each element's signature debuff already exists as a plain aura effect on a stock spell. We
copy the effect, not the spell.

| Element | School (mask) | Rider, copied from | Effect |
| ------- | ------------- | ------------------ | ------ |
| Fire    | Fire (4)      | Deadly Poison 2818 shape | `PERIODIC_DAMAGE` (aura 3) every 2s for 6s: a burn |
| Frost   | Frost (16)    | Frostbolt 116, effect 0  | `MOD_DECREASE_SPEED` (aura 33) -30% for 6s |
| Earth   | Nature (8)    | Earth Shock 8042, effect 0 | `MOD_MELEE_HASTE` (aura 138) -10% attack speed for 6s |
| Poison  | Nature (8)    | Deadly Poison 2818, effect 0 | `PERIODIC_DAMAGE` (aura 3) every 3s for 12s, weaker but longer than Fire |
| Arcane  | Arcane (64)   | none                     | No rider. Arcane's identity is raw damage: larger elemental add instead |
| Shadow  | Shadow (32)   | Mortal Strike 12294, effect 0 | `MOD_HEALING_PCT` (aura 118, misc 127) -20% for 6s |
| Holy    | Holy (2)      | none on the target       | `HEAL` (effect 10) on the caster for the elemental add's value: smite and mend |

Earth and Poison both use the Nature school. That is how 3.3.5a is built (there is no Earth
school) and it is fine: they are resisted the same way and differ in what they do on hit.

Holy is the outlier for balance rather than mechanics: almost nothing in the game resists it,
so a Holy variant loses nothing to armour and nothing to resistance. It gets a lower weapon
coefficient than the others (2.1) and a self-heal rather than a debuff, so its identity is
sustain, not the biggest number.

### 1.3 The visuals: kits are separable

`SpellVisual.dbc` (32 fields) holds one kit id per phase of a cast. The kits themselves are
in `SpellVisualKit.dbc` and reference effect models by name. Reading the template spells:

```
Visual 39    Heroic Strike     CastKit=324  ImpactKit=437
Visual 253   Sinister Strike   CastKit=399  ImpactKit=3049
Visual 11612 Frost Strike      CastKit=10723 ImpactKit=10724

Kit 324   Heroic Strike cast    anim=57                          (the swing)
Kit 437   Heroic Strike impact  anim=9  Chest: DecisiveStrike_Impact_Chest.mdx
Kit 728   Fire Blast impact     anim=9  Chest: Fire_ImpactDD_Chest.mdx
Kit 4991  Frostbolt impact      anim=9  Chest: Ice_ImpactDD_Med_Chest.mdx
Kit 3055  Earth Shock impact            Chest: EarthShock_Impact_Chest.mdx
Kit 3031  Deadly Poison impact          Chest: Poison_Impact_Chest.mdx
Kit 1005  Arcane Blast impact           Chest: ArcaneExplosion_Impact_Chest.mdx
Kit 6359  Hammer of Wrath impact anim=9  Chest: Holy_ImpactDD_Uber_Chest.mdx + Base
Kit 6898  SW: Death impact              Chest: shadowword_death_impact.mdx
```

A melee impact and an elemental impact are the same kind of thing: one chest-attached
model. So a variant's visual is a new `SpellVisual` row that copies the base row and swaps
`ImpactKit` for the element's. The Hero swings exactly as before and the target lights up
fire, ice, stone, poison, arcane, shadow or holy light. **No new models, no new
animations.** Shadow Bolt's own impact kit (7775) carries seven effect slots and is too busy;
Shadow Word: Death's 6898 is a single clean burst and is the working choice, confirmed in
Phase 0.

### 1.4 The pipeline already exists

| Need | Have |
| ---- | ---- |
| Custom spells server-side | `spell_dbc` and `skilllineability_dbc` override tables; the core ships custom rows up to id 100102 |
| Custom spells client-side | `client-patch/lib/dbc.py` rewrites DBCs and the installer ships them in a patch MPQ |
| Reading base icons | `blp.decode_blp` handles palettized and DXT1/3/5 |
| Writing new icons | `blp.encode_palettized` writes BLP2 with the full mip chain the client insists on |
| Image work | Pillow, already an optional dependency for the Hero emblem |
| Rarity, cost and weight per spell | `cw_ability_override` |

---

## 2. Design

### 2.1 Damage model

A spell has three effect slots, and the base's weapon effects, its non-weapon effects (Sinister
Strike's combo point, Mortal Strike's healing debuff), the elemental add and the rider all
compete for them. The recipe, in priority order:

```
slot A:  WEAPON_PERCENT_DAMAGE (31), basepoints = CoefficientPct - 1, school = element
         REPLACES every weapon effect the base had. A base's flat weapon add (Sinister
         Strike's +3, Mortal Strike's +85) is not lost: it moves into slot B.
slot B:  SCHOOL_DAMAGE (2), basepoints = base's flat add + a per-level bonus,
         EffectBonusMultiplier = SpellPowerCoefficient. Always present.
rest:    the base's own non-weapon effects, copied verbatim (they keep their slot).
last:    the element's rider, only if a slot is still free.
```

So Fiery Heroic Strike (base: one weapon effect) is 31 + 2 + burn. Fiery Sinister Strike
(base: weapon + combo point) is 31 + 2 + combo point, and has no burn: the spell-power add
outranks the rider because the add is the hybrid identity and the rider is flavour. The
generator reports which variants lost their rider so the tooltip and the plan can say so.

Replacing the weapon effects with a single 31 gives up `NORMALIZED_WEAPON_DMG`'s
weapon-speed normalization. That is a deliberate simplification to win back a slot; Blizzard
ships plenty of 31-only strikes (Overpower, Whirlwind, Backstab), and the Frost Strike pattern
of keeping 121 alongside 31 is available for any base with a slot to spare. Revisit in the
Phase 3 balance pass if slow two-handers dominate.

**Why the coefficient is 85%.** Physical damage against a plate-wearing target at 80 loses
roughly a third to armour. Elemental damage loses almost nothing to typical resistance.
Keeping 100% of the weapon damage and changing only the school would be a straight buff.
85% is the opening guess (75% for Holy, which nothing resists); `cw_ability_override` and
the per-element config multipliers are the dials.

**Why the elemental add is `SCHOOL_DAMAGE` with a spell-power coefficient, not a flat
weapon add like Frost Strike's +87.** A flat weapon add scales with nothing.
`SCHOOL_DAMAGE` honours `EffectBonusMultiplier` (Fire Blast's is 0.204), so the elemental
part of a variant grows with spell power. That turns "Fiery Sinister Strike" into a genuine
hybrid ability: the weapon part wants attack power, the fire part wants Intellect. That is
the build space this module exists to open up, and it gives Intellect a reason to appear on a
melee build. Recommended opening coefficient 0.15, about three quarters of a real nuke's,
because the variant also keeps most of its weapon damage.

Everything else is copied from the base row verbatim: `Attributes` through `AttributesEx7`
(so Heroic Strike's on-next-swing flag, Backstab's behind-the-target requirement and
Overpower's aura-state gate all carry over), `Stances` (Claw stays cat-only), casting time,
cooldown, category, power type and cost, range, `EquippedItemClass` and the sub-class mask
(Deadly Throw still needs a thrown weapon), `DmgClass` (so it stays a melee attack that can
crit on the melee table), `SpellFamilyName` and `SpellFamilyFlags` (so talents that modify
the base, such as "increases Sinister Strike damage", also modify the variant).

### 2.2 Which abilities

Read from the client's `SkillLineAbility.dbc`, `Spell.dbc` and `Talent.dbc`: **38 distinct
class abilities** are Physical-school, non-passive, and deal weapon damage. Three groups come
out:

- **Noise**, four: Auto Shot, Sweeping Strikes, Ghostly Strike, Unfair Advantage.
- **Talent rank spells**, seven, which live in the talent pool: Crusader Strike, Devastate,
  Divine Storm, Hemorrhage, Mortal Strike, Scatter Shot, Silencing Shot.
- **Triggered children**: Stormstrike's two weapon hits (32175, 32176) are fired by the
  castable 17364 and are not abilities in their own right. 129 spells in the class pool have
  this shape, so the generator's rule is explicit: **skip any spell that appears as an
  `EffectTriggerSpell` of another class spell.**

That leaves **22 base abilities**, 133 ranks between them:

```
Melee:   Sinister Strike (12 ranks), Heroic Strike (13), Backstab (12), Ambush (10),
         Raptor Strike (11), Cleave (8), Overpower, Mocking Blow, Whirlwind, Maim (2),
         Ravage (7), Shred (9), Claw (8), Maul (10), Swipe (Cat), Fan of Knives,
         Mangle (Cat) (5), Mangle (Bear) (5)
Ranged:  Multi-Shot (8), Aimed Shot (3), Kill Shot (2), Deadly Throw (3)
DK:      Blood Strike, Plague Strike (6), Obliterate, Death Strike (5)   (with IncludeDeathKnight)
```

Seven elements across 133 ranks is about **930 spell rows**; Death Knight adds 91. All
generated, and phased below so the pipeline is proven on a handful first.

Two lines are worth knowing about because they look wrong and are not. **Mangle** is granted
by a hidden talent spell (33917), but the castable Mangle (Cat) and (Bear) sit in
`SkillLineAbility` as ordinary class spells, so the module already offers them without the
talent; they are legitimate bases. **Aimed Shot**'s ranks 1 to 6 are absent from
`SkillLineAbility` and only ranks 7 to 9 are present, so the module's Aimed Shot line starts
at rank 7, level 70, and its variants would too.

The generator must apply exactly the filters `BuildLibrary` applies (class skill line,
non-passive, not a talent rank spell, no utility effects, trainer-taught) plus the trigger
rule above, so a variant only ever exists for a base the pool actually contains. The cleanest
way to guarantee that is for the generator to import the same criteria rather than restate
them; failing that, `LoadVariants` refuses any variant whose base is missing from
`_abilities` at startup and logs it.

Talent-spell bases are a design question rather than a technical one: a "Fiery Mortal
Strike" in the ability pool would be a Mortal Strike you can roll without the talent. That
might be exactly the point of a classless realm, or might undercut the talent. Deferred to
Phase 4 and left as an open question below.

### 2.3 Naming and rarity

One prefix per element, applied to the base name: **Fiery**, **Frozen**, **Earthen**,
**Venomous**, **Arcane**, **Shadow**, **Holy**. Seven names, no exceptions, so a player who
has seen one can read all of them.

Rarity is the base's rarity **plus one tier**, capped at legendary, because a variant is
strictly more interesting than its base (a school change, a spell-power scaling add, and a
rider). Roll weight follows rarity as usual, so variants are rarer rolls than their bases
without any special casing.

Owning a base and its variant together is **allowed**. They share the base's spell category,
so a category cooldown on the base is shared, but the global cooldown is the only thing most
of these have. Whether owning one should exclude the other is an open question.

### 2.4 Icons

Generated at **install time on the player's machine**, from the player's own client files,
the way the Hero emblem is. Nothing of Blizzard's is redistributed in the repository. For
each (base icon, element):

1. `ClientFiles.find("Interface\Icons\<base>.blp")`, `blp.decode_blp` to RGBA.
2. Element treatment in Pillow: the base icon is left exactly as drawn, and a square badge a
   quarter of the icon wide sits in the top-right corner: a plate of black tinted toward the
   element's colour, bordered in that colour, with a bold filled symbol of the element inside
   (flame, snowflake, boulder, drop, star, crescent, sun). Drawn at four times the size and
   scaled down, so it is clean at the 36 pixels the game shows icons at. The shape says which
   ability; the badge says which element; nothing about the art changes. Two whole-icon tints
   were tried first and rejected on a preview from a real client (one left elements
   indistinguishable and read as haze, the other washed highlights out), which is why
   `preview_elemental_icons.py` exists: every change to this gets judged the same way.
3. `blp.encode_palettized`, written to `Interface\Icons\CW_<Element>_<BaseIconName>.blp`.
4. A `SpellIcon.dbc` row per icon, ids from 5000 (the stock table tops out at 4375).

Without Pillow the installer sets the variant's `SpellIconID` to the base's, so the spell
still shows and works; only the tint is lost. Same policy as the Hero emblem today.

| Element | Badge colour | Symbol |
| ------- | ------------ | ------ |
| Fire    | orange-red | flame |
| Frost   | ice blue | snowflake |
| Earth   | brown | boulder |
| Poison  | acid green | drop |
| Arcane  | hot magenta | four-point star |
| Shadow  | deep indigo | crescent |
| Holy    | gold | sun |

Arcane and Shadow are deliberately far apart (magenta against indigo): the first pass put
both near purple and they were indistinguishable on a purple base icon.

### 2.5 Tooltips

The client renders `Description` from its own copy of the row, so a variant's text is
written by the generator in stock tooltip syntax:

```
Fiery Sinister Strike:
  An instant strike that causes $s1% of your normal weapon damage as Fire damage, plus
  $s2 Fire damage, and burns the target for $o3 Fire damage over $d. Awards 1 combo point.
```

`$s1`, `$s2`, `$o3` and `$d` are ordinary spell-text variables the client already expands
from the effect fields. Because one generator emits both the server row and the client row
from one source, the number the server deals and the number the tooltip shows cannot drift.

---

## 3. Server side

### 3.1 Data

A generated SQL file, `data/sql/db-world/cw_spells_elemental.sql`, applied by the updater
like the rest of the module's SQL:

- `spell_dbc` rows: one per variant rank, ids from **950000**. Clear of the stock table
  (max 80864), of the core's own custom rows (max 100102), and of the module's item and NPC
  ids (990xxx) so nothing reads as a collision.
- `skilllineability_dbc` rows, ids from **22000** (stock max 21980): a copy of the base's
  row with `Spell` set to the variant, so the variant files under the same spellbook tab as
  its base. The client patch already opens every class line to every class.
- `spell_ranks` rows linking each variant's ranks, so `GetNextSpellInChain` and the module's
  automatic rank-up on level treat a variant line exactly like a stock one.
- A new module table:

```sql
CREATE TABLE cw_ability_variants (
  variant_first_spell INT UNSIGNED PRIMARY KEY,
  base_first_spell    INT UNSIGNED NOT NULL,
  element             TINYINT UNSIGNED NOT NULL,   -- 1 fire 2 frost 3 earth 4 poison 5 arcane 6 shadow 7 holy
  enabled             TINYINT UNSIGNED NOT NULL DEFAULT 1
);
```

### 3.2 Library

`BuildLibrary` gains a `LoadVariants()` pass after the `SkillLineAbility` pass. For every
enabled row whose base is in `_abilities`:

- Build the rank chain from `spell_ranks` as the stock pass does.
- Copy the base's `rankLevels` and `classMask` (so a variant counts toward the same classes
  for synergy rolls).
- Set rarity to the base's plus one tier, then apply `cw_ability_override` as normal.
- **Bypass the `TrainerTaughtOnly` filter.** That filter exists to keep NPC-only spells out
  of the pool by requiring a trainer entry; module-owned spells are legitimate by
  construction and have no trainer.
- Register the spell-to-tab mapping the same way the stock pass does.

Nothing else in the module needs to know a variant is a variant. Buying, rolling, rerolling,
locking, unlearning, rank-up on level, the addon browser and the reveal all work on
`AbilityEntry` and spell ids.

### 3.3 Config

```
ClasslessWildcard.Elemental.Enable = 1
ClasslessWildcard.Elemental.CoefficientPct = 85       # weapon damage kept, percent of base
ClasslessWildcard.Elemental.CoefficientPct.Holy = 75  # per-element override; Holy is unresisted
ClasslessWildcard.Elemental.SpellPowerCoefficient = 0.15
ClasslessWildcard.Elemental.RarityBump = 1
```

The first is a load-time gate on `LoadVariants`. The other three are read by the generator
when the SQL is produced, and recorded in the conf so the numbers in the rows are traceable;
changing them means regenerating, because they are baked into effect fields the client also
holds.

---

## 4. Client side

### 4.1 Installer step

A new `client-patch/lib/elemental.py`, driven by `client-patch/elemental_manifest.json`
that the generator writes alongside the SQL. The manifest lists, per variant: the base spell
id, the field overrides for the `Spell.dbc` row, the visual override, and the icon recipe.
The installer:

1. Reads the winning `Spell.dbc`, `SpellIcon.dbc`, `SpellVisual.dbc` and
   `SkillLineAbility.dbc` from the client's archive chain (the pattern every existing DBC edit
   uses, so a community patch's rows survive).
2. Appends rows: `Spell.dbc` (copy the base record's 936 bytes, overwrite the listed fields,
   write the name, rank and description into all sixteen locale slots with the locale mask
   set), `SpellVisual.dbc` (copy base, set `ImpactKit`), `SpellIcon.dbc` and
   `SkillLineAbility.dbc` (new rows).
3. Generates the icons as in 2.4.
4. Ships all of it in the patch MPQ it already builds. `--uninstall` removes it with the
   rest.

### 4.2 What the patch carries

`Spell.dbc` is 47 MB uncompressed (49,839 rows of 936 bytes plus a 2.3 MB string block), and
the client loads exactly one copy. The installer therefore reads the player's own `Spell.dbc`
through the archive chain, appends the variant rows to it, and ships the result in the patch
archive, PKWARE-compressed. The repository carries only the manifest (about 1.7 MB of ids,
overrides and text); no Blizzard table is checked in. The player's patch archive does grow by
the compressed table, a one-time download, not a runtime cost.

### 4.3 Addon

No changes required. The reveal and the browser resolve name and icon through
`GetSpellInfo(spellId)`, which reads the client's `Spell.dbc`; once the row is there,
variants render like anything else. An optional touch: colour the reveal title by element.

---

## 5. Status

Built and checked against the DBC extract, not yet run in a client or on a server:

- `data/sql/generators/gen_elemental_variants.py`, the generator. Mirrors the pool's
  filters plus the two the plan added (no `EffectTriggerSpell` children, no free strikes,
  which is how script-fired procs like Sweeping Strikes' extra hit are told apart from
  buttons). Emits `cw_spells_elemental.sql` and `client-patch/elemental_manifest.json`
  from one run. Every full-run row was checked for the 234-column arity.
- `client-patch/lib/elemental.py`, the installer step, wired into `install.py` behind
  `--no-elemental` and off under `--minimal`. Appends to the player's own tables; uninstall
  recognises the painted icons by their `CW_` prefix.
- `src/ClasslessMgr.cpp` `LoadVariants()`, behind `Elemental.Enable`, uncompiled.
- `client-patch/test_elemental.py` exercises the client step against an extract and passes,
  including a rank-chain check: every variant line's `SupercededBySpell` walks the variant
  line, not the base's (the first generator copied the base's, which would have hidden a
  variant in the spellbook the moment a higher rank of the base was learned).
- Realm switches beyond `Enable`: `InPool` (rolls and purchase) and `ShowInBrowser` (the
  addon's class menus and the NPC lists), both on by default.

The shipped set is now the full pass: every eligible base, every element, every rank. 29
bases are eligible; Mocking Blow and Deadly Throw are skipped (two non-weapon effects leave
no slot for the elemental hit), so **27 bases, 189 lines, 1,085 spell rows**, ids stable
against the Phase 1 wave (its 462 ids did not move). The four Death Knight bases ship and
register only on a realm with `IncludeDeathKnight` on; elsewhere `LoadVariants` skips them
quietly and reports the count. Seventeen bases carry the elemental hit but no rider because
their third slot is taken (combo points, Maim's stun, Mangle's bleed bonus, the DK strikes'
disease effects, Whirlwind's off-hand trigger): Aimed Shot, Ambush, Backstab, Claw, Death
Strike, Hemorrhage, Maim, both Mangles, Mortal Strike, Obliterate, Overpower, Plague Strike,
Ravage, Shred, Sinister Strike, Whirlwind. Area and chain strikes keep the base's own
targeting on every slot, so Fiery Whirlwind is still an area attack and Fiery Cleave still
strikes two.

Verified in game on the Phase 0 spike (Fiery Sinister Strike rank 1): dealt in a Wildcard
starting hand, so the server registered it and the roll reached it; the client resolved its
name; energy cost, melee range and weapon requirement copied from the base; the tooltip
rendered its numbers; the painted icon showed; it cast; and the combat log reported the hit as
**13 Fire**, which is 85% of a white swing plus the +7 add, the exact figure the recipe
predicts. Still to check: armour versus resistance on a plate mob, and the add rising with
Intellect.

Found by that first roll: with the shipped equal rarity weights, `RarityBump` does not make
a variant roll less often, so every strike would have gained seven siblings at full weight.
`Elemental.RollWeightPct` (default 15) now sets each variant's roll weight explicitly.

## 6. Phases

**Phase 0, the spike: done.** Fiery Sinister Strike rank 1, verified in game (dealt in a
starting hand, tooltip, icon, cast, `13 Fire` in the combat log). The procedure is kept below
because every later addition should be checked the same way.

**Phase 1, the pipeline: done.** Generator, installer step, `LoadVariants`, tests.

**Phase 2, rank chains: done.** Every rank of every line, `spell_ranks`, `SupercededBySpell`
walking the variant line.

**Phase 3, riders and balance: riders done, balance open.** Every element's rider is in where
a slot allows. The balance pass (the 85% coefficient, the 0.15 spell-power coefficient, the 15%
roll weight, and whether any base wants a `cw_ability_override` row) needs play, not code.

**Phase 4, the rest of the list: done except the decision.** Ranged, form-locked and Death
Knight bases are in the shipped set. Talent-rooted lines (Mortal Strike, Devastate, Hemorrhage,
Aimed Shot, Mangle) are in because the module's own pool already offers their trainer ranks
without the talent; whether that is wanted is the open question below, not a technical gap.

**In-game checks still worth doing on the full set**, because these shapes did not exist in
the spike: a Fiery Whirlwind hitting a group, a Fiery Multi-Shot from a bow with ammo, a
Mangle or Maul variant refusing to cast out of form, an Overpower variant still needing the
dodge, and a rank 2 variant arriving on level-up for a line whose rank 1 is owned.

### Phase 0 procedure

Server:

1. Rebuild the worldserver (the module's C++ changed).
2. Start it. The DB updater applies `cw_spells_elemental.sql` on this start, before the spell
   store loads, so one start is enough. In the log, look for the file being applied and then
   `1 elemental variants registered (0 skipped)`. A `variant 950672 skipped` warning means the
   base was not in the pool; `no elemental variants configured` means the SQL did not apply,
   which `SELECT ID FROM spell_dbc WHERE ID = 950672;` confirms either way.

Client:

3. `pip install pillow` if the icon should be painted (without it the base icon is used).
4. Close WoW, run the installer. The summary must show `Elemental variants: yes` and the
   report must list `Spell.dbc 1 elemental variant rows appended`, `SpellVisual.dbc 1 rows`,
   `SkillLineAbility.dbc 1 variant rows` and, with Pillow, `SpellIcon.dbc 1 painted icons
   registered`. The installer clears the cache; if archives are ever copied by hand, delete
   `Cache\WDB` too, or the client keeps showing the old spell table.

In game, on a **Classless** character (Wildcard characters cannot buy):

5. `.classless learn 950672`. It costs 2 AE: Sinister Strike is common, the variant is one
   tier up. "Unknown ability" here means step 2 failed.
6. Open the spellbook. It files under the **Combat** tab (its base's), named Fiery Sinister
   Strike, and the tooltip reads "An instant strike that deals 85% of your weapon damage as
   Fire damage, plus 7 Fire damage. Awards 1 combo point." with numbers, not `$s1`. A blank
   name or an empty tooltip means the client's Spell.dbc row is missing: step 4.
7. The icon is Sinister Strike's, recoloured orange with a flame in the corner (Pillow), or
   Sinister Strike's own (no Pillow).
8. Cast it on a training dummy. The combat log entry must say **Fire**; the target must show
   the fire impact while the character plays the normal Sinister Strike swing; a combo point
   must appear.
9. Cast Sinister Strike and the variant alternately on a plate-wearing mob and compare
   against their tooltips: the physical one lands well under its number, the Fire one close
   to it. That is armour ignored and resistance applied.
10. Optional, the hybrid scaling: add Intellect on the Stats panel and watch the "plus N Fire
    damage" part of the tooltip rise while the weapon part does not.
11. The Wildcard reveal, if wanted: on a Wildcard character, insert
    `(950672, 255, 0, 1000000, 1)` into `cw_ability_override` (`first_spell, rarity, cost,
    weight, enabled`), restart, reroll anything you own, and the replacement is the variant,
    drawn with the reveal's name and icon. Delete the row afterwards.

Also where the shadow impact kit gets chosen, once Fire is confirmed.

**Phase 1, the pipeline.** `gen_elemental_variants.py` reading extracted DBCs (path
configurable; the current extract is at `B:\New folder\dbc`), `elemental.py` in the
installer, `LoadVariants` in the server. Wave one is six bases (Sinister Strike, Heroic
Strike, Backstab, Raptor Strike, Claw, Maul) across all six elements, **top rank only**
gated at the base's first-rank level. Thirty-six spells: enough to shake out the generator
and the DBC appends, few enough to check by hand.

**Phase 2, rank chains.** Every rank, `spell_ranks` rows, and the module's rank-up on level
verified against a variant line. This is where the row count climbs to the hundreds.

**Phase 3, riders and balance.** The element riders, the per-element coefficient
multipliers, a balance pass against the bases, `cw_ability_override` rows for anything that
needs a nudge. Documentation: conf, README, addon Help.

**Phase 4, the rest of the list.** Ranged bases, form-locked bases (they need the form kit
pairing in `cw_form_kits` too), Death Knight bases behind `IncludeDeathKnight`, and a decision
on talent-spell bases.

---


## 7. Risks and open questions

**Risks**

- **Patch size.** Resolved the way 4.2 describes: the installer splices the rows into the
  player's own `Spell.dbc`, so the repository carries the manifest and no Blizzard table. The
  player's patch archive still grows by one compressed copy of that table.
- **Server and client rows must agree.** They come from one generator, which is the
  mitigation, but a realm that regenerates the SQL and forgets to re-ship the client manifest
  gets tooltips that lie. Mitigated: every run stamps a generation id into both outputs; the
  worldserver logs the one it loaded and the installer prints the one it applied, so a
  mismatch is two different strings side by side. "Regenerate, restart, reinstall" is still
  the rule; this is how you find out it was skipped.
- **Form abilities.** Claw and Maul carry a `Stances` mask; copying it keeps them form-locked,
  which is correct, and the shipped set includes them. The form-kit pairing (Bear Form hands
  over Maul) does not hand over Earthen Maul; a `cw_form_kits` row would, if wanted.
- **Slows do not stack.** A Frozen strike's -30% will not add to Frostbolt's -40%; the
  stronger applies. That is stock behaviour and fine, but worth saying in the tooltip text so
  it does not read as a bug.

**Open questions, none blocking Phase 0**

1. Should owning a base exclude its variants, or the reverse? Current answer: no exclusion.
   A variant can be dealt alongside its base in the same hand, which the first test roll
   appeared to do. Whether that is a feature or a duplicate is a play-test question.
2. Talent-rooted bases (Mortal Strike, Devastate, Hemorrhage, Aimed Shot, Mangle) have
   variants, because the module's own pool already offers their trainer ranks without the
   talent and the generator mirrors the pool. If that is not wanted, the fix belongs in the
   pool filter, and the variants follow.
3. Are the seven prefixes right? Fiery, Frozen, Earthen, Venomous, Arcane, Shadow, Holy.
