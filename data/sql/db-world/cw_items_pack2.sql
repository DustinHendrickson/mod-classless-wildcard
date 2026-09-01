-- mod-classless-wildcard: classless item pack II
--
-- A second wave of build-enabling gear, additive to cw_items_pack.sql (which
-- owns 990201-990212 and is left untouched). This pack fills the slots the
-- first one never covered -- neck, rings, off-hands, wands, shields, polearms,
-- thrown -- and keeps to the same theme: stat combinations the original class
-- system would never put on that item.
--
-- Pure server-side data. Display ids are reused from existing items, so the
-- client already knows how to draw every one of these; no client patch needed.
-- Same rare tier and level band as the first pack (ilvl 40, usable at 35) so
-- the two sit alongside each other.
--
-- stat_type ids: 3 AGI, 4 STR, 5 INT, 6 SPI, 7 STA, 32 CRIT, 36 HASTE,
--                38 ATTACK POWER, 45 SPELLPOWER

DELETE FROM `item_template` WHERE `entry` BETWEEN 990280 AND 990295;
INSERT INTO `item_template`
  (`entry`, `class`, `subclass`, `name`, `displayid`, `Quality`, `BuyCount`, `BuyPrice`, `SellPrice`,
   `InventoryType`, `AllowableClass`, `AllowableRace`, `ItemLevel`, `RequiredLevel`, `stackable`,
   `stat_type1`, `stat_value1`, `stat_type2`, `stat_value2`, `stat_type3`, `stat_value3`,
   `dmg_min1`, `dmg_max1`, `dmg_type1`, `delay`, `armor`, `bonding`, `MaxDurability`, `Material`, `sheath`,
   `description`, `VerifiedBuild`)
VALUES
-- ---------------------------------------------------------------------------
-- Jewellery -- hybrid stat pairs, the slots the first pack skipped entirely
-- ---------------------------------------------------------------------------
(990280, 4, 0, 'Chain of the Untethered', 6497, 3, 1, 15877, 3175, 2, -1, -1, 40, 35, 1,
 4, 12, 5, 12, 7, 10, 0, 0, 0, 0, 0, 2, 0, 0, 0,
 'Strength and intellect on one chain. Pick a side, or do not.', 12340),
(990281, 4, 0, 'Pendant of Split Purpose', 64205, 3, 1, 15877, 3175, 2, -1, -1, 40, 35, 1,
 3, 12, 45, 20, 7, 10, 0, 0, 0, 0, 0, 2, 0, 0, 0,
 'For the ones who stab and then heal the wound.', 12340),
(990282, 4, 0, 'Band of the Blurred Line', 9840, 3, 1, 15877, 3175, 11, -1, -1, 40, 35, 1,
 4, 10, 45, 18, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0,
 'Strength and spellpower, welded into one ring.', 12340),
(990283, 4, 0, 'Loop of Contradiction', 43706, 3, 1, 15877, 3175, 11, -1, -1, 40, 35, 1,
 3, 10, 5, 14, 7, 8, 0, 0, 0, 0, 0, 2, 0, 0, 0,
 'Agility and intellect have no quarrel here.', 12340),

-- ---------------------------------------------------------------------------
-- Off-hands and shields -- carried by builds that were never allowed them
-- ---------------------------------------------------------------------------
(990284, 4, 0, 'Codex of the Warpriest', 25072, 3, 1, 15877, 3175, 23, -1, -1, 40, 35, 1,
 4, 10, 45, 16, 7, 8, 0, 0, 0, 0, 0, 2, 0, 0, 0,
 'A tome braced to be swung if the reading goes badly.', 12340),
(990285, 4, 0, 'Grimoire of the Berserker', 23321, 3, 1, 15877, 3175, 23, -1, -1, 40, 35, 1,
 3, 12, 38, 24, 7, 10, 0, 0, 0, 0, 0, 2, 0, 0, 0,
 'An off-hand book carrying attack power. It has notes in the margins.', 12340),
(990286, 4, 6, 'Barrier of Raw Intellect', 30835, 3, 1, 14976, 2995, 14, -1, -1, 40, 35, 1,
 5, 14, 45, 20, 7, 10, 0, 0, 0, 0, 2121, 2, 100, 1, 0,
 'A shield for casters who refuse to stand at the back.', 12340),

-- ---------------------------------------------------------------------------
-- Weapons -- families crossed with the wrong stat, on purpose
-- ---------------------------------------------------------------------------
(990287, 2, 10, 'Ironbark Warstaff', 32677, 3, 1, 69689, 13937, 17, -1, -1, 40, 35, 1,
 4, 26, 7, 14, 0, 0, 88, 133, 0, 3300, 0, 2, 120, 4, 2,
 'A staff for hitting things. The wood is only incidental.', 12340),
(990288, 2, 6, 'Arcane Pike', 55966, 3, 1, 69689, 13937, 17, -1, -1, 40, 35, 1,
 5, 22, 45, 30, 7, 12, 82, 124, 0, 3300, 0, 2, 120, 1, 1,
 'A polearm that reaches further than its blade.', 12340),
(990289, 2, 15, 'Kingslayer''s Letter Opener', 6460, 3, 1, 44527, 8905, 13, -1, -1, 40, 35, 1,
 4, 14, 7, 8, 32, 10, 34, 64, 0, 1700, 0, 2, 75, 1, 3,
 'A dagger with a claymore''s attitude.', 12340),
(990290, 2, 4, 'Hammer of Quiet Malice', 57332, 3, 1, 44527, 8905, 13, -1, -1, 40, 35, 1,
 3, 16, 7, 8, 0, 0, 44, 83, 0, 2400, 0, 2, 90, 1, 3,
 'A mace balanced for someone light on their feet.', 12340),
(990291, 2, 3, 'Boneshatter Handcannon', 30809, 3, 1, 44527, 8905, 26, -1, -1, 40, 35, 1,
 4, 16, 7, 8, 0, 0, 48, 89, 0, 2800, 0, 2, 65, 1, 0,
 'Heavy enough to club with once the shot is spent.', 12340),
(990292, 2, 19, 'Wand of Brutal Focus', 45357, 3, 1, 44527, 8905, 26, -1, -1, 40, 35, 1,
 4, 8, 38, 30, 0, 0, 55, 102, 0, 1900, 0, 2, 65, 1, 0,
 'A wand that lends attack power. It is not sure why either.', 12340),
-- stackable 1: thrown weapons do not deplete on 3.3.5a, so one is all you need
(990293, 2, 16, 'Enchanted Bola', 40411, 3, 1, 44527, 8905, 25, -1, -1, 40, 35, 1,
 5, 10, 45, 14, 0, 0, 52, 92, 0, 2200, 0, 0, 0, 1, 0,
 'Thrown, then detonated. The second part is the clever bit.', 12340),

-- ---------------------------------------------------------------------------
-- Armor -- the remaining "wrong armor class" slots
-- ---------------------------------------------------------------------------
(990294, 4, 4, 'Legplates of the Windwalker', 26651, 3, 1, 24841, 4968, 7, -1, -1, 40, 35, 1,
 3, 20, 7, 14, 0, 0, 0, 0, 0, 0, 456, 2, 115, 6, 0,
 'Plate legs light enough to sprint in. Allegedly.', 12340),
(990295, 4, 1, 'Sabatons of the Silk Road', 17138, 3, 1, 14976, 2995, 8, -1, -1, 40, 35, 1,
 4, 14, 7, 10, 0, 0, 0, 0, 0, 0, 116, 2, 65, 7, 0,
 'Cloth boots with a soldier''s tread.', 12340);

-- sell them on the Hero Advancement NPC (slots 50+; heirlooms own 20-42)
DELETE FROM `npc_vendor` WHERE `entry` = 990100 AND `item` BETWEEN 990280 AND 990295;
INSERT INTO `npc_vendor` (`entry`, `slot`, `item`, `maxcount`, `incrtime`, `ExtendedCost`, `VerifiedBuild`)
SELECT 990100, 50 + (`entry` - 990280), `entry`, 0, 0, 0, 12340
FROM `item_template` WHERE `entry` BETWEEN 990280 AND 990295;

-- Same level gate as the first pack: these require level 35, so they stay off
-- the vendor until a Hero is close to using them.
DELETE FROM `conditions` WHERE `SourceTypeOrReferenceId` = 23 AND `SourceGroup` = 990100
  AND `SourceEntry` BETWEEN 990280 AND 990295;
INSERT INTO `conditions`
  (`SourceTypeOrReferenceId`, `SourceGroup`, `SourceEntry`, `SourceId`, `ElseGroup`,
   `ConditionTypeOrReference`, `ConditionTarget`, `ConditionValue1`, `ConditionValue2`,
   `ConditionValue3`, `NegativeCondition`, `ErrorType`, `ErrorTextId`, `ScriptName`, `Comment`)
SELECT 23, 990100, `entry`, 0, 0, 27, 0, 25, 3, 0, 0, 0, 0, '', 'CW item pack II: level >= 25'
FROM `item_template` WHERE `entry` BETWEEN 990280 AND 990295;
