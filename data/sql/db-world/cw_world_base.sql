-- mod-classless-wildcard: world data
-- Hero Advancement NPC, Scrolls of Fortune, rarity/cost override tables.

-- ---------------------------------------------------------------------------
-- Admin tuning tables (stand-in for Ascension's curated rarity/cost data)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `cw_ability_override` (
  `first_spell` INT UNSIGNED NOT NULL COMMENT 'first-rank spell id of the line',
  `rarity` TINYINT UNSIGNED NOT NULL DEFAULT 255 COMMENT '0 common .. 4 legendary, 255 = keep heuristic',
  `cost` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'ability essence cost, 0 = by rarity',
  `weight` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'wildcard roll weight, 0 = by rarity',
  `enabled` TINYINT UNSIGNED NOT NULL DEFAULT 1,
  PRIMARY KEY (`first_spell`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Classless ability tuning';

CREATE TABLE IF NOT EXISTS `cw_talent_override` (
  `talent_id` INT UNSIGNED NOT NULL,
  `rarity` TINYINT UNSIGNED NOT NULL DEFAULT 255 COMMENT '0 common .. 4 legendary, 255 = keep heuristic',
  `weight` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'wildcard roll weight, 0 = by rarity',
  `enabled` TINYINT UNSIGNED NOT NULL DEFAULT 1,
  PRIMARY KEY (`talent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Classless talent tuning';

-- A few sensible starter overrides (build-defining abilities cost more / roll less)
INSERT IGNORE INTO `cw_ability_override` (`first_spell`, `rarity`, `cost`, `weight`, `enabled`) VALUES
(53, 3, 0, 0, 1),        -- Backstab: epic example
(5185, 1, 0, 0, 1),      -- Healing Touch
(133, 0, 0, 0, 1),       -- Fireball
(686, 0, 0, 0, 1),       -- Shadow Bolt
(17, 1, 0, 0, 1),        -- Power Word: Shield
(100, 0, 0, 0, 1);       -- Charge

-- ---------------------------------------------------------------------------
-- Scrolls of Fortune (wildcard reroll currency)
-- ---------------------------------------------------------------------------

DELETE FROM `item_template` WHERE `entry` IN (990101, 990102);
INSERT INTO `item_template`
  (`entry`, `class`, `subclass`, `name`, `displayid`, `Quality`, `BuyCount`, `BuyPrice`, `SellPrice`,
   `InventoryType`, `AllowableClass`, `AllowableRace`, `ItemLevel`, `RequiredLevel`, `maxcount`, `stackable`,
   `BagFamily`, `description`, `VerifiedBuild`)
VALUES
(990101, 15, 0, 'Scroll of Fortune', 1103, 3, 1, 5000, 0, 0, -1, -1, 1, 1, 0, 20,
 0, 'Rerolls one of your Wildcard abilities or talents. A top-up: you earn a reroll with every roll the Wildcard deals you.', 12340),
(990102, 15, 0, 'Scroll of Fortune: Talents', 1103, 2, 1, 2500, 0, 0, -1, -1, 1, 1, 0, 20,
 0, 'Rerolls one of your Wildcard talents. A top-up: you earn a reroll with every roll the Wildcard deals you.', 12340);

-- ---------------------------------------------------------------------------
-- Hero Advancement NPC (gossip + vendor)
-- ---------------------------------------------------------------------------

DELETE FROM `creature_template` WHERE `entry` = 990100;
INSERT INTO `creature_template`
  (`entry`, `name`, `subname`, `minlevel`, `maxlevel`, `faction`, `npcflag`, `unit_class`,
   `unit_flags`, `type`, `type_flags`, `RegenHealth`, `flags_extra`, `ScriptName`, `VerifiedBuild`)
VALUES
(990100, 'Hero Advancement', 'Classless & Wildcard', 80, 80, 35, 129, 1, 2, 7, 0, 1, 2, 'npc_hero_advancement', 12340);

-- scoped delete: cw_items_pack.sql manages its own rows on this vendor
DELETE FROM `npc_vendor` WHERE `entry` = 990100 AND `item` IN (990101, 990102);
INSERT INTO `npc_vendor` (`entry`, `slot`, `item`, `maxcount`, `incrtime`, `ExtendedCost`, `VerifiedBuild`) VALUES
(990100, 0, 990101, 0, 0, 0, 12340),
(990100, 1, 990102, 0, 0, 0, 12340);

-- ---------------------------------------------------------------------------
-- Model + spawns (schema-adaptive)
--
-- Current AzerothCore master uses `creature_template_model` and `creature.id1`;
-- older cores / forks / repacks use `creature_template.modelid1` and
-- `creature.id`. Only the branch matching this database executes.
-- Spawns: Stormwind (Trade District), Orgrimmar (Valley of Strength), Dalaran
-- (Krasus' Landing). Move/delete to taste; `.npc add 990100` adds more.
-- ---------------------------------------------------------------------------

DROP PROCEDURE IF EXISTS cw_world_setup;
DELIMITER //
CREATE PROCEDURE cw_world_setup()
BEGIN
    -- NPC display model
    IF EXISTS (SELECT 1 FROM information_schema.TABLES
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'creature_template_model') THEN
        DELETE FROM `creature_template_model` WHERE `CreatureID` = 990100;
        INSERT INTO `creature_template_model` (`CreatureID`, `Idx`, `CreatureDisplayID`, `DisplayScale`, `Probability`, `VerifiedBuild`)
        VALUES (990100, 0, 26482, 1, 1, 12340);
    ELSEIF EXISTS (SELECT 1 FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'creature_template' AND COLUMN_NAME = 'modelid1') THEN
        UPDATE `creature_template` SET `modelid1` = 26482 WHERE `entry` = 990100;
    END IF;

    -- spawns
    IF EXISTS (SELECT 1 FROM information_schema.COLUMNS
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'creature' AND COLUMN_NAME = 'id1') THEN
        DELETE FROM `creature` WHERE `id1` = 990100;
        INSERT INTO `creature` (`id1`, `map`, `zoneId`, `areaId`, `spawnMask`, `phaseMask`, `position_x`, `position_y`, `position_z`, `orientation`, `spawntimesecs`, `wander_distance`, `MovementType`)
        VALUES
        (990100, 0, 1519, 1519, 1, 1, -8842.09, 626.358, 94.0867, 3.61283, 300, 0, 0),
        (990100, 1, 1637, 1637, 1, 1, 1633.33, -4439.11, 15.7588, 1.06465, 300, 0, 0),
        (990100, 571, 4395, 4395, 1, 1, 5813.9, 448.14, 658.75, 2.19, 300, 0, 0);
    ELSEIF EXISTS (SELECT 1 FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'creature' AND COLUMN_NAME = 'wander_distance') THEN
        DELETE FROM `creature` WHERE `id` = 990100;
        INSERT INTO `creature` (`id`, `map`, `zoneId`, `areaId`, `spawnMask`, `phaseMask`, `position_x`, `position_y`, `position_z`, `orientation`, `spawntimesecs`, `wander_distance`, `MovementType`)
        VALUES
        (990100, 0, 1519, 1519, 1, 1, -8842.09, 626.358, 94.0867, 3.61283, 300, 0, 0),
        (990100, 1, 1637, 1637, 1, 1, 1633.33, -4439.11, 15.7588, 1.06465, 300, 0, 0),
        (990100, 571, 4395, 4395, 1, 1, 5813.9, 448.14, 658.75, 2.19, 300, 0, 0);
    ELSE
        -- oldest schema variant: spawndist instead of wander_distance
        DELETE FROM `creature` WHERE `id` = 990100;
        INSERT INTO `creature` (`id`, `map`, `spawnMask`, `phaseMask`, `position_x`, `position_y`, `position_z`, `orientation`, `spawntimesecs`, `spawndist`, `MovementType`)
        VALUES
        (990100, 0, 1, 1, -8842.09, 626.358, 94.0867, 3.61283, 300, 0, 0),
        (990100, 1, 1, 1, 1633.33, -4439.11, 15.7588, 1.06465, 300, 0, 0),
        (990100, 571, 1, 1, 5813.9, 448.14, 658.75, 2.19, 300, 0, 0);
    END IF;
END//
DELIMITER ;
CALL cw_world_setup();
DROP PROCEDURE IF EXISTS cw_world_setup;
