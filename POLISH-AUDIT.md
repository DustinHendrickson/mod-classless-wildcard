# Polish audit, 2026-10-02

Four read-only sweeps (addon UI, server text, data/tooltip text, docs vs code), merged and
deduplicated. ✔ = I re-checked it in the code myself. Line numbers are as of commit `2580ded`.
README errors found by the sweep are already fixed in the working tree.

Abbreviations: **Lua** = `client-addon/ClasslessWildcard/ClasslessWildcard.lua`,
**Mgr** = `src/ClasslessMgr.cpp`, **Npc** = `src/ClasslessNpc.cpp`, **Cmd** = `src/ClasslessCommands.cpp`,
**Forged** = `data/sql/generators/gen_forged_spells.py`, **conf** = `conf/classless_wildcard.conf.dist`.

---

## 1. Gameplay bugs found along the way (not text, but players will hit them)

**Status: all nine fixed in the working tree (batch 1).**

| # | Where | Problem | Suggested fix |
|---|---|---|---|
| 1.1 ✔ | Mgr:1487, 5464-5474, 5626-5636 | Hero-line abilities and challenge rewards get `classMask = 0x5FF`, and `OwnedClassMask` / `OwnedClassCount` count them. Owning Makeshift Strike counts as owning 10 classes: **Jack of All Trades** jumps to its max step, and **synergy rolls** filter nothing. | Skip `forged` entries in both functions. |
| 1.2 ✔ | Mgr:2721 | Challenge gold is paid on **every** finish. Repeating Hardcore pays 1000g each time. The addon (Lua:1641) says a repeat "pays shards only". | Pay gold only on the first finish, matching the addon. |
| 1.3 | Mgr:1944-1961 | `ApplyArchetype` with no talents owned removes every ability, **heirlooms included**, unrefunded. The Respec path keeps heirlooms. | Skip `GrantSource::Heirloom` in that loop. |
| 1.4 | Mgr:3991, 4081-4092, 3743 | A Hero who picks Classless at level 4, or is defaulted at 5, misses the AE for levels already gained (ends at 79 AE, not 80). | Back-pay AE/TE for levels past the start level in `SetMode` / `ApplyDefaultMode`. |
| 1.5 | ClasslessChallenges.cpp:261-272, Mgr:2666 | Hourglass keeps ticking in a battleground. `LoseLife` returns early without resetting the clock, so "sand ran out" spams every 5 sec and a life is taken on the first tick after leaving. | Pause the Hourglass clock in BG/arena, or reset it in the early return. |
| 1.6 ✔ | Mgr:2080-2100 | `SwitchPath` accepts the path you are already on (100g for a free respec), and lets an Unchosen Hero pay past the deadline. | Refuse `target == st.mode` and `Mode::Unchosen`. |
| 1.7 | cw_world_base.sql:72 vs Mgr:2949 | NPC Reroll Scroll: flat 50s and sold below level 10. Panel: 500 + 500 × level copper, refused below 10. At 80, NPC 50s vs panel ~4g. | Drop the scroll from the NPC vendor and sell through the gossip at the panel price, or flatten both. |
| 1.8 | Lua:6232, 948 | `Stats.Enable = 0` still shows the Stats button, which opens an empty allocator. | Hide `statsBtn` when disabled. |
| 1.9 | Lua:69, 6261 | Addon defaults `talentFlat = true` until CFG arrives; the server default is per-rank. The Talents pane briefly says "(all ranks)". | Default `false`, parse with `or 0`. |

## 2. Wrong information shown to players

**Status: fixed in batch 2; 2.28 fixed after: the Dungeon Finder reward gets the kill rate.**

| # | Where | Current | Fix |
|---|---|---|---|
| 2.1 ✔ | Cmd:111, Mgr:5828, 5918 | "you earn one with every roll the Wildcard deals" | Charges come 3 per level from level 10. "No reroll charges or Reroll Scrolls left. You earn 3 charges each level." |
| 2.2 ✔ | Mgr:4012 | "Scroll{} of Fortune" | The item is **Reroll Scroll**. |
| 2.3 | Npc:391, 430 | "(Consumes a Reroll Scroll from level 10.)" | A charge is spent first, a scroll only when charges are gone; level from `wcFreeRerollLevel`. |
| 2.4 ✔ | Lua:2349 | "24 rolls, which is around 16 levels" | One roll a level: "about 24 levels". Cmd:121 comment has the same stale figure. |
| 2.5 | Lua:2344 vs 2345 | Says a roll can jump a held talent from rank 2 to 5, then says a roll never raises a rank. | Delete the rank-jump sentence (the jump is the scroll stake). |
| 2.6 | Lua:2379 | "deadlier rules give five, fight-changing three" | Legion has 4. "Each challenge shows its lives." |
| 2.7 | Lua:1006 vs 2380 | "most challenges" / "some runs" give an ability | All 12 do. |
| 2.8 | Lua:2351, 266 | Crest "opens the roll screen any time" / "Click to reroll your starter abilities" | It only opens the starting hand, below level 10, and rerolls nothing. |
| 2.9 | Lua:5143 | Talent reveal: "- dealt free, all ranks included" | You get the rank rolled. "Dealt free at Rank N." |
| 2.10 | Lua:2366, 2378 | Tells players to press **Rebirth** to change path. | The button reads "Change path" below the cap. |
| 2.11 | Lua:2383 | "Open this panel any time with N (the old Talents key -- talents live here now)" | Use `GetBindingKey(...)`; the key may be J/Y/G/K. |
| 2.12 | Lua:2336 | Talent-taught ability counts "for prerequisites and tree points" | There are no tree points. |
| 2.13 | Lua:2333-2335, 2334, 2341, 2343, 2347, 2349, 2371, 6758 | Hardcoded 3 AE, 1/2/3/5/8, 4 abilities, level 10, 10%, +100/50/300%, +3/15%... | Send these in CFG and build the text. At least use `freeReroll` and `deadline`, which the client already has. |
| 2.14 | Mgr:4088 | "Reroll them freely at the Hero Advancement NPC until level 10." | Use config level; mention /cw. |
| 2.15 | ClasslessPlayerScript.cpp:1029 | Trainer refusal: "managed by the classless system... Learn it through the Hero Advancement NPC" | Wildcard Heroes cannot buy. Branch by path; name the spell. |
| 2.16 ✔ | Mgr:2085 | Path change disabled says "Rebirth is disabled". | "Changing path is disabled on this realm." |
| 2.17 | Forged:1312-1314 | Quickening tooltip renders "up to 20%,. Requires..." and says "rage or energy" (code uses combined). | Rewrite (see audit text in section 5). |
| 2.18 | Forged:673 | Vertigo says "within $a1 yards of you"; it is a cone and also slows 30%. | "...in a $a1 yard cone in front of you and slows them by $s2%..." |
| 2.19 | Forged:1031 | Cairn: "anything that strikes you" | The shield is on every ally in range: "strikes one of you". |
| 2.20 | Forged:1772 | Long Reach "ranged Hero abilities" misses 7 ranged lines in `affects`. | Add them, or name the lines. |
| 2.21 | conf:455, Mgr:5756 | "rank 5 roughly a twentieth as likely" | Weights 10 vs 100: a tenth. |
| 2.22 | conf:221-226 | Every variant "adds an elemental hit" | Frost, Earth, Shadow apply an aura, no hit. |
| 2.23 | conf:83, 90-92 | "whatever was picked at creation", "The class chosen at creation" | Nothing is picked; it is the Paladin chassis. |
| 2.24 | client-patch/lib/charcreate.py:3, dbc.py:718 | Say the shell is Warrior with server conversion. | Paladin, no conversion (`install.py:175`). |
| 2.25 | client-patch/README.md:274, 237, 240, 255, 276, 251, 180 | "Wow.exe never modified by default"; `--creation-text` / `--hero-icon` flags that do not exist; `--no-forged` missing; dead anchor; "12 files" (16). | Rewrite the options section against `install.py`. |
| 2.26 | cw_world_challenges.sql:3 | Pursued hunter "every ten minutes" | 15 to 30 minutes. |
| 2.27 | Mgr:2509-2510 | Legion rule: reinforcements never call more; its tip says every joiner calls its own. | Fix the tip. |
| 2.28 | ClasslessPlayerScript.cpp:916 | Rebirth "kill and dungeon XP": Dungeon Finder XP gets the lower rate. | Decide which is intended; conf:867 text follows. |
| 2.29 | Uninstall | `chartitles_dbc` rows 180-197 not removed or listed. | Add to `cw_uninstall_world.sql` and the README. |

## 3. Visible text bugs

**Status: fixed in batch 2, 3.10 and 3.14 were finished in batch 5. 3.6: the tooltip plurals use the client's `$l` token.**

| # | Where | Current | Fix |
|---|---|---|---|
| 3.1 ✔ | Mgr:4027 | "so 1 padlock comes come off" | `freed == 1 ? "padlock comes" : "padlocks come"` |
| 3.2 ✔ | ClasslessAddon.cpp:147 | `SendErr` uses `Sanitize`, which strips `:` and `;`. Every panel error loses its colons ("Choose a valid path  classless or wildcard."). | Use `SanitizeText`. |
| 3.3 ✔ | Npc:310 | "Warrior tree #161"; the Hero tree shows as "Warrior tree #990". | Use the tab's name from `sTalentTabStore`. |
| 3.4 | Npc:265-268 | All 33 Hero-line abilities listed under every class. | Filter `forged` out of class pages; give them a Hero page. |
| 3.5 | Mgr:4676, 5600, 5752, 2024, 2044 | A path change, Rebirth or archetype at 80 prints dozens of lines; "Synergy roll!" never names the item. | Respect `_revealSuppress`, print one summary. |
| 3.6 | Plurals | "1 Reroll Scrolls" (Mgr:5827), "returns in 1 rolls" (Cmd:126), "(1 abilities, 1 talents)" (Lua:2682), "1 shards" (Lua:6341), "1 enemies" / "2 additional time" / "$s2 more times" (Forged:1722, 1765, 1263) | Pluralise; use `$lsingular:plural;` in tooltips. |
| 3.7 | Lua:2356-2360 | Stat help lines: "...per 52 Agility, plus dodge per point.", "+10 health (...) per point.", Spirit "increases +0.50 mana..." | Prefix "Each point:" as the tooltip at Lua:2851 does. |
| 3.8 | Mgr:2698, 2769 | "A life lost. Nemesis 2 of 5 left." / "{} complete. {} shards and {} gold, and X is yours to keep." | "Nemesis: 2 of 5 lives left." / "Nemesis complete! You earn ..." |
| 3.9 | Forged:577, 1249 | Debuff tooltips "Frost half of Antipode Blast." / "Ricochet of Ricochet Shot." | "Movement speed reduced by $s2%." / "Struck by Ricochet Shot." |
| 3.10 | Forged (all), gen_elemental_variants.py:198-218 | No recipe sets `tooltip=`, so buff/debuff tooltips are the cast text minus "for $d". | Add Blizzard-style aura tooltips (list in the data sweep: Hush, Sinkhole, Brace, the elemental riders...). |
| 3.11 | Lua:2374 | "the Twice Reborn, and on." | "and so on." |
| 3.12 | Lua:3474 | "Anything that builds them builds them" | "Any ability that builds combo points builds them for you." |
| 3.13 | cw_items_pack.sql:5 | Mojibake "â€”"; three item SQL files start with a BOM. | Rewrite; strip BOMs. |
| 3.14 | Spell names | "Arcane Cleave", "Holy Cleave", "Shadow Cleave" exist in stock Spell.dbc. | Rename the Cleave variants. |

## 4. Missing feedback and confirms

**Status: fixed in batch 3; 4.14 finished after: an open flyout takes the panel's place in UISpecialFrames, so Escape closes it first.**

| # | Where | Problem |
|---|---|---|
| 4.1 | Lua:958 | Panel **Respec** wipes everything in one click, no confirm, no tooltip. The NPC confirms. In Wildcard it is disabled with no reason. |
| 4.2 | Lua:2120, 1385 | Following an archetype replaces the build with no confirm; Buy extra life spends 30 shards with no confirm; its label "(30)" has no unit. |
| 4.3 | Npc:107-108, 585-590 | Choosing a path at the NPC is permanent with no confirm; the path-change submenu offers your current path and shows no cost. |
| 4.4 | Cmd:307, 355, 378 | `.classless rebirth`, `.classless run` at cap, `.classless path` act immediately. Require a `confirm` token. |
| 4.5 | Lua:2465, 2497, 3068 | An Unchosen Hero who closed the wizard has no way to choose from the panel; "Decide later" never says the Wildcard is assigned at the deadline. |
| 4.6 | Lua:2538, 2627 | Rows say "Click to learn" with a cost when the click does nothing (above your level, or not Classless). |
| 4.7 | Npc:488 | NPC lock failures are silently dropped. |
| 4.8 | Mgr:3321, Cmd:222, Addon:836 | `SetDisplayPower` fails with empty `err`: a blank red line. |
| 4.9 | Cmd (all) | No `command` table help rows: bad arguments give the core's generic syntax error with no usage. |
| 4.10 | Mgr:5259, 5246, 2097, 2382, 5097 | Errors that do not say what is missing: which prerequisite talent, how much TE/gold you have, which spell. |
| 4.11 | Npc:377, 134, 196, 595 | NPC offers Unlearn/Reroll/Lock on heirlooms (all fail), Reroll Scrolls to Classless Heroes, and a dead "Rebirth" info line below the cap. |
| 4.12 | Npc:339 | Talent list cost ignores flat pricing; maxed and level-locked talents look buyable; says "row" where errors say "tier". |
| 4.13 | Npc:524, 476-518 | After buying/rerolling, the NPC drops you back to the main menu or page 0. |
| 4.14 | Lua:191 | Escape closes the whole panel over a flyout; the talent reroll dialog, starting hand and path wizard ignore Escape. |
| 4.15 | Lua:1217, 1791 | Stats/Settings/Help flyouts (DIALOG strata) draw over the Rebirth picker and Challenge screen. |
| 4.16 | Lua:4449-4454, 4509 | `/cwbars show/hide` and minimap right-click print nothing and do not refresh the Settings checkboxes. |
| 4.17 | Lua:963-971 | Path popup reads "Classless \| Cancel \| Wildcard", offers your current path, and has a hard line break mid-sentence. |
| 4.18 | Lua:3932 | Talent reroll dialog shows the stake limit only when you have zero scrolls, and points at a Buy button that may be hidden. |

## 5. House-rule violations (dashes, dev talk, class talk)

**Status: fixed in batches 2 and 4.**

- **" -- " in player prose:** Lua help text (2326-2383, 268), Mgr:2978, `client-patch/lib/gluestrings.py:23-31` (the **character creation** paragraph), Reroll Scroll description `cw_world_base.sql:73`, heirloom flavour `cw_items_heirlooms.sql:42, 97`, installer output `install.py:516, 591, 701, 705, 719, 741`, conf:95. Real em-dashes in `cw_uninstall_world.sql:2, 98`, `cw_uninstall_characters.sql:2`.
- **Class talk / chassis jargon:** welcome message Mgr:3720 ("You have no class, and there was none to pick... chassis"), Lua:2326 ("no class to pick... hidden base class"), Lua:3045 wizard ("a shared chassis (resource bar...)"), gluestrings.py ("only one class... the class is purely cosmetic"), `install.py:757` ("every class will read Hero").
- **Dev commentary:** Lua:2340 ("The server rolls"), 2342 (design justification), 6903 ("replaced the unused Talents frame"), 2114/3107 ("configured on this realm"), 2363 ("as they always were"); Mgr:4065 ("exempt from the classless system"), Cmd:79, Cmd:113 ("Reroll pity"); conf:850 ("Rebirth used to be"), conf:378 ("the name is misleading"), conf:131 ("Still experimental"), conf:896; SQL headers `cw_world_base.sql:30-33, 53-57, 75-76`, `cw_world_class_quests.sql:13`, generated headers from Forged:2531, 2477 and `gen_tiered_gear.py:247`.
- **.toc:** Title "ClasslessWildcard", Author "mod-classless-wildcard", Notes "for the mod-classless-wildcard server"; version 1.0 vs `ADDON_VERSION = "0.9.5"` printed on every login.
- **Debug left in:** `/cw testroll` is open to every player (Lua:6761).

## 6. Naming and terminology

**Status: fixed in batch 4, except the item-name rows (duplicate base names, reused flavour lines, Pocket Sand, Sabatons of the Silk Road, the Heroic tier prefix, Stealthy Healer, the NPC subname), which were finished in batch 5. The conf stays in British spelling as admin text.**

| Term | Variants in use | Pick |
|---|---|---|
| The panel | "Character Advancement" (title), "Hero Advancement" (button, binding, NPC), "classless panel" (minimap, micro button) | Hero Advancement |
| Chat prefix | `[Classless]` for every Hero, including Wildcard (Mgr:46, Lua:90); errors and challenge alerts unprefixed | `[Hero]`, everywhere |
| Key Bindings header | "ClasslessWildcard" | Hero Advancement |
| Path | "Mode:" / "That is already your mode" (Cmd:92, Mgr:4071) | Path |
| Rerolls | "Rerolls", "reroll charges", "Scrolls", "Reroll Scrolls", "Scroll of Fortune" | reroll charges / Reroll Scroll |
| Heirloom | scaling gear and Rebirth-carried abilities | heirloom gear / heirloom abilities |
| Talent row | "Tier" (sort), "Row N" (rows, NPC), "tier" (errors) | Tier |
| Wildcard hint | "Dealt by Wildcard rolls" vs "Rolled at level-up" | one phrase |
| Essence | AE/TE in chat lines vs spelled out elsewhere | spell out in chat |
| Common rarity colour | white in code, grey in help (Lua:2335) | white |
| Challenge name colour | gold in list, red in messages | one |
| Spelling | "spellpower", "favours", "channelled" in item text; conf all British | US, "spell power" |
| Mini-bar position | "beside your unit frame" vs "under the player frame" | under the player frame |
| Item names | Same base names with different stats: Zealot's Hide Jerkin, Windrunner's, Kingslayer's, Ironweave Battlerobe, Loop of Contradiction; reused flavour lines | distinct names / lines |
| Odd names | "Pocket Sand", "Sabatons of the Silk Road" (cloth), "Heroic" tier prefix, "Stealthy Healer", NPC subname "Classless & Wildcard" | rename |

## 7. Lower priority

**Status: all done. The two PaperDollFrame_SetStat hooks did not conflict: the second was written for a later client's (frame, unit, index) signature and never ran on 3.3.5, so it was removed. Five Hero-line tooltips (Sentry Bolt, Spore Wash, Turnabout, Sanguine Pact, Brink) keep literal numbers because the value lives in another spell or a script.**

- Hardcoded numbers in Hero-line tooltips where an effect token exists (18 spells, Forged:585-1612). They match today but will drift.
- Two `PaperDollFrame_SetStat` hooks overwrite each other (Lua:3811, 4590) with disagreeing stat descriptions.
- Duplicate essence/reroll readout at top and bottom of the panel; My Build name suffixes and talent sub-lines likely truncate (Lua:898, 2626).
- Load message on every login (Lua:6953).
- "(passive)" shown twice when sorting by type (Lua:2527).
- conf:244-255 `Forged.Enable` filed inside the Elemental section with its tag after Default.
- Nemesis refund is next-level XP × levels ÷ 20 (five levels back = 25% of a level); rule text "take the levels back as XP" oversells it.
