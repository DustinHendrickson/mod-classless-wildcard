-- mod-classless-wildcard: let any Hero use any class's items
--
-- `item_template`.`AllowableClass` is a class mask, and the core tests it in
-- Player::CanUseItem with no way for a module to answer:
--
--     if ((proto->AllowableClass & getClassMask()) == 0 ...)
--         return EQUIP_ERR_YOU_CAN_NEVER_USE_THAT_ITEM;
--
-- That check runs and returns BEFORE the OnPlayerCanUseItem script hook, so C++
-- cannot lift it. Every Hero shares one chassis, so the mask was answering
-- "Paladin" for everybody and 6,509 items were closed to every build:
--
--     4,984  class armour sets (PvP, tier, quest rewards)
--       749  recipes
--       353  glyphs -- a Hero could fill six glyph slots with Paladin glyphs
--             and nothing else, which closes off the whole glyph system
--       347  weapons, quest items and miscellany
--        37  consumables, including every rogue poison, so a Hero who rolled
--             rogue abilities could never apply one
--         9  bags (soul bags, ammo pouches, quivers)
--         9  relic-slot items -- the module opens the relic SLOT in C++
--             (ClasslessWildcard.ClasslessClassChecks), but six Idols and
--             Sigils carry a class mask as well and stayed unusable
--
-- Clearing the mask is the same fix, and the same shape of fix, as
-- cw_world_class_quests.sql applies to quest class requirements.
--
-- A handful of these items teach a class ability (Grimoire of Doom, Tome of
-- Tranquilizing Shot). Those now open like everything else, and the module
-- reverts the spell exactly as it does a class trainer's or a class quest's,
-- with a line in chat saying where to learn it instead. The item is spent. The
-- same items also carry engineering schematics and mounts, which are not class
-- abilities and are simply gained.
--
-- REVERSIBLE. The original masks are copied into `cw_item_class_backup` before
-- anything is overwritten; data/sql/manual/cw_item_classes_revert.sql puts them
-- back, and the world uninstall script does the same.

CREATE TABLE IF NOT EXISTS `cw_item_class_backup` (
  `entry` INT UNSIGNED NOT NULL COMMENT 'item_template.entry',
  `AllowableClass` INT NOT NULL COMMENT 'the class mask before the module cleared it',
  PRIMARY KEY (`entry`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Original item class requirements, so cw_world_item_classes.sql can be undone';

-- 2047 is every real class bit (1..11; bit 10 is unused in 3.3.5a). Rows that
-- already allow every class are left alone whatever padding bits they carry, so
-- -1 and the 32767-style "all" masks are not recorded and not rewritten.
--
-- INSERT IGNORE, and only rows that still carry a restriction: re-applying this
-- file after the update has run finds nothing left to record, so a backup taken
-- the first time is never overwritten with the value we just wrote.
INSERT IGNORE INTO `cw_item_class_backup` (`entry`, `AllowableClass`)
SELECT `entry`, `AllowableClass` FROM `item_template`
 WHERE (`AllowableClass` & 2047) <> 2047;

UPDATE `item_template` SET `AllowableClass` = -1
 WHERE (`AllowableClass` & 2047) <> 2047;
