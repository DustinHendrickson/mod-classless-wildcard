-- mod-classless-wildcard: classless item pack
-- Ascension-style items that only make sense in a classless world: intellect
-- guns, strength throwing weapons, mail tanking and caster gear, spellpower
-- fist weapons. Pure server-side data (client reads them from the item query
-- cache; existing display ids are reused) — no client patch needed.
-- Sold by the Hero Advancement NPC alongside the Reroll Scrolls.

DELETE FROM `item_template` WHERE `entry` BETWEEN 990201 AND 990212;
INSERT INTO `item_template`
  (`entry`, `class`, `subclass`, `name`, `displayid`, `Quality`, `BuyCount`, `BuyPrice`, `SellPrice`,
   `InventoryType`, `AllowableClass`, `AllowableRace`, `ItemLevel`, `RequiredLevel`, `stackable`,
   `stat_type1`, `stat_value1`, `stat_type2`, `stat_value2`, `stat_type3`, `stat_value3`,
   `dmg_min1`, `dmg_max1`, `dmg_type1`, `delay`, `armor`, `bonding`, `MaxDurability`, `Material`, `sheath`,
   `description`, `VerifiedBuild`)
VALUES
-- ranged for casters (int/sp guns & bows)
(990201, 2, 3, 'Spellbinder''s Boomstick', 27886, 3, 1, 44527, 8905, 26, -1, -1, 40, 35, 1,
 5, 12, 45, 14, 7, 8, 45, 84, 0, 2800, 0, 2, 65, 1, 0,
 'A firearm tuned to arcane resonance. Casters welcome.', 12340),
(990202, 2, 2, 'Longbow of the Mendicant', 8106, 3, 1, 44527, 8905, 15, -1, -1, 40, 35, 1,
 5, 10, 6, 10, 7, 8, 42, 79, 0, 2600, 0, 2, 65, 2, 0,
 'Strung for those who heal between volleys.', 12340),
-- strength throwing weapon
(990203, 2, 16, 'Warlord''s Heavy Javelin', 22713, 3, 1, 44527, 8905, 25, -1, -1, 40, 35, 200,
 4, 14, 7, 8, 0, 0, 55, 95, 0, 2200, 0, 0, 0, 1, 0,
 'A soldier''s answer to problems at range.', 12340),
-- mail tanking set (defense-flavored via sta/agi)
(990204, 4, 3, 'Bulwark Chainmail of the Hero', 43698, 3, 1, 24841, 4968, 5, -1, -1, 40, 35, 1,
 7, 24, 3, 12, 4, 10, 0, 0, 0, 0, 461, 2, 120, 5, 0,
 'Mail forged for those who tank without a shield wall pedigree.', 12340),
(990205, 4, 3, 'Bulwark Chain Helm of the Hero', 43697, 3, 1, 14976, 2995, 1, -1, -1, 40, 35, 1,
 7, 18, 3, 10, 4, 8, 0, 0, 0, 0, 375, 2, 85, 5, 0,
 'A helm for unconventional defenders.', 12340),
-- plate caster set
(990206, 4, 4, 'Runeplate of the Battle Mage', 24393, 3, 1, 24841, 4968, 5, -1, -1, 40, 35, 1,
 5, 22, 45, 26, 7, 12, 0, 0, 0, 0, 521, 2, 135, 6, 0,
 'Plate etched with channeling runes. Heavy armor, heavier spells.', 12340),
(990207, 4, 4, 'Runeplate Gauntlets of the Battle Mage', 27331, 3, 1, 14976, 2995, 10, -1, -1, 40, 35, 1,
 5, 14, 45, 18, 7, 8, 0, 0, 0, 0, 326, 2, 45, 6, 0,
 'Gauntlets that do not muffle spellcraft.', 12340),
-- spellpower fist weapon (melee caster)
(990208, 2, 13, 'Sparkfist Talon', 45199, 3, 1, 44527, 8905, 13, -1, -1, 40, 35, 1,
 5, 10, 45, 20, 7, 6, 38, 71, 0, 2000, 0, 2, 75, 1, 3,
 'For those who cast with their knuckles.', 12340),
-- leather healer with strength (paladin-rogue hybrids)
(990209, 4, 2, 'Zealot''s Hide Jerkin', 30729, 3, 1, 24841, 4968, 5, -1, -1, 40, 35, 1,
 4, 16, 6, 14, 7, 10, 0, 0, 0, 0, 204, 2, 100, 8, 0,
 'Supple leather for holy warriors who strike from the shadows.', 12340),
-- agility two-hand sword (hunter-warrior hybrids)
(990210, 2, 8, 'Windrunner''s Claymore', 28587, 3, 1, 69689, 13937, 17, -1, -1, 40, 35, 1,
 3, 22, 7, 10, 0, 0, 95, 143, 0, 3300, 0, 2, 100, 1, 1,
 'A greatsword balanced for the fleet of foot.', 12340),
-- spirit shield (caster off-hand defense)
(990211, 4, 6, 'Aegis of Quiet Prayer', 34955, 3, 1, 14976, 2995, 14, -1, -1, 40, 35, 1,
 5, 12, 6, 12, 7, 8, 0, 0, 0, 0, 2121, 2, 100, 1, 0,
 'A shield that hums with restorative energy.', 12340),
-- cloth "tank" chest (sta/armor-heavy robe)
(990212, 4, 1, 'Ironweave Battlerobe of the Hero', 31237, 3, 1, 24841, 4968, 20, -1, -1, 40, 35, 1,
 7, 28, 5, 10, 4, 8, 0, 0, 0, 0, 197, 2, 100, 7, 0,
 'Woven for casters who insist on being hit.', 12340);

-- sell them on the Hero Advancement NPC
DELETE FROM `npc_vendor` WHERE `entry` = 990100 AND `item` BETWEEN 990201 AND 990212;
INSERT INTO `npc_vendor` (`entry`, `slot`, `item`, `maxcount`, `incrtime`, `ExtendedCost`, `VerifiedBuild`) VALUES
(990100, 2, 990201, 0, 0, 0, 12340),
(990100, 3, 990202, 0, 0, 0, 12340),
(990100, 4, 990203, 0, 0, 0, 12340),
(990100, 5, 990204, 0, 0, 0, 12340),
(990100, 6, 990205, 0, 0, 0, 12340),
(990100, 7, 990206, 0, 0, 0, 12340),
(990100, 8, 990207, 0, 0, 0, 12340),
(990100, 9, 990208, 0, 0, 0, 12340),
(990100, 10, 990209, 0, 0, 0, 12340),
(990100, 11, 990210, 0, 0, 0, 12340),
(990100, 12, 990211, 0, 0, 0, 12340),
(990100, 13, 990212, 0, 0, 0, 12340);

-- Only offer these once they are nearly usable. They require level 35, so
-- showing them to a fresh Hero was 12 rows of noise on the vendor. The tiered
-- gear covers every other level band. (23 = NPC_VENDOR, 27 = CONDITION_LEVEL,
-- comparison 3 = >=.)
DELETE FROM `conditions` WHERE `SourceTypeOrReferenceId` = 23 AND `SourceGroup` = 990100
  AND `SourceEntry` BETWEEN 990201 AND 990212;
INSERT INTO `conditions`
  (`SourceTypeOrReferenceId`, `SourceGroup`, `SourceEntry`, `SourceId`, `ElseGroup`,
   `ConditionTypeOrReference`, `ConditionTarget`, `ConditionValue1`, `ConditionValue2`,
   `ConditionValue3`, `NegativeCondition`, `ErrorType`, `ErrorTextId`, `ScriptName`, `Comment`)
SELECT 23, 990100, `entry`, 0, 0, 27, 0, 25, 3, 0, 0, 0, 0, '', 'CW item pack: level >= 25'
FROM `item_template` WHERE `entry` BETWEEN 990201 AND 990212;
