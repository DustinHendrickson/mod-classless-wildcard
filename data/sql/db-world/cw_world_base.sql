-- mod-classless-wildcard: world data
-- Hero Advancement NPC, Reroll Scrolls, rarity/cost override tables.

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
-- Cleanup: an early version of this module auto-applied playercreateinfo_item
-- rows (tagged 'cw kit: ...') that duplicated the starter kit at character
-- creation -- piles of throwing axes, a second Hearthstone (STORAGE err 17 in
-- the log), and so on. The starter kit is granted by C++ now; remove any of
-- those rows still sitting in the database.
-- ---------------------------------------------------------------------------

DELETE FROM `playercreateinfo_item` WHERE `Note` LIKE 'cw kit:%';

-- ---------------------------------------------------------------------------
-- Reroll Scrolls (wildcard reroll currency)
-- ---------------------------------------------------------------------------

DELETE FROM `item_template` WHERE `entry` IN (990101, 990102);
INSERT INTO `item_template`
  (`entry`, `class`, `subclass`, `name`, `displayid`, `Quality`, `BuyCount`, `BuyPrice`, `SellPrice`,
   `InventoryType`, `AllowableClass`, `AllowableRace`, `ItemLevel`, `RequiredLevel`, `maxcount`, `stackable`,
   `BagFamily`, `description`, `VerifiedBuild`)
VALUES
(990101, 15, 0, 'Reroll Scroll', 1103, 3, 1, 5000, 0, 0, -1, -1, 1, 1, 0, 20,
 0, 'A stored Wildcard reroll, good for an ability OR a talent. Spent automatically when you reroll something you were dealt and have no free rerolls left. You earn rerolls just by leveling -- keep a few of these for a run of bad luck.', 12340);

-- 990102 was a second, talent-only scroll. One scroll now covers both, so the
-- old item is removed (it is also deleted by the range above).

-- ---------------------------------------------------------------------------
-- Hero Advancement NPC (gossip + vendor)
-- ---------------------------------------------------------------------------

DELETE FROM `creature_template` WHERE `entry` = 990100;
INSERT INTO `creature_template`
  (`entry`, `name`, `subname`, `minlevel`, `maxlevel`, `faction`, `npcflag`, `unit_class`,
   `unit_flags`, `type`, `type_flags`, `RegenHealth`, `flags_extra`, `ScriptName`, `VerifiedBuild`)
VALUES
(990100, 'Hero Advancement', 'Classless & Wildcard', 80, 80, 35, 129, 1, 2, 7, 0, 1, 2, 'npc_hero_advancement', 12340);

-- The NPC's own list is the supplies counter. Everything else it sells lives on
-- separate vendor lists that cw_world_vendor_lists.sql builds and the gossip
-- menu opens -- one packet cannot carry the whole catalogue. Scoped delete, so
-- this does not disturb rows that file owns.
DELETE FROM `npc_vendor` WHERE `entry` = 990100 AND `item` IN (990101, 990102);
INSERT INTO `npc_vendor` (`entry`, `slot`, `item`, `maxcount`, `incrtime`, `ExtendedCost`, `VerifiedBuild`) VALUES
(990100, 0, 990101, 0, 0, 0, 12340);

-- ---------------------------------------------------------------------------
-- Model + spawns (schema-adaptive)
--
-- Current AzerothCore master uses `creature_template_model` and `creature.id1`;
-- older cores / forks / repacks use `creature_template.modelid1` and
-- `creature.id`. Only the branch matching this database executes.
-- Spawns: one in every major city, standing right next to that city's guild
-- master so players always know where to find it -- Stormwind, Ironforge,
-- Darnassus, the Exodar, Orgrimmar, Thunder Bluff, Undercity, Silvermoon and
-- Dalaran; Shattrath (no guild master) sits on the central terrace by A'dal.
-- Adjust per realm: `.npc del` an unwanted one, or `.go` to a spot and
-- `.npc add 990100` to place more.
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
        (990100, 0, 0, 0, 1, 1, -8883.25, 614.395, 95.3576, 3.526, 300, 0, 0),   -- Stormwind -- by Aldwin Laughlin, Guild Master (Trade District)
        (990100, 0, 0, 0, 1, 1, -5014.19, -997.442, 503.966, 2.793, 300, 0, 0),   -- Ironforge -- by Jondor Steelbrow, Guild Master (The Commons)
        (990100, 1, 0, 0, 1, 1, 10077.9, 2199.74, 1346.7, 1.833, 300, 0, 0),   -- Darnassus -- by Lysheana, Guild Master
        (990100, 530, 0, 0, 1, 1, -4090.43, -11626.6, -138.665, 4.224, 300, 0, 0),   -- The Exodar -- by Funaam, Guild Master
        (990100, 1, 0, 0, 1, 1, 1577.8, -4292.67, 26.2826, 4.381, 300, 0, 0),   -- Orgrimmar -- by Urtrun Clanbringer, Guild Master (Valley of Strength)
        (990100, 1, 0, 0, 1, 1, -1289.81, 127.206, 131.703, 6.056, 300, 0, 0),   -- Thunder Bluff -- by Krumn, Guild Master
        (990100, 0, 0, 0, 1, 1, 1593.25, 204.498, -55.2596, 1.728, 300, 0, 0),   -- Undercity -- by Christopher Drakul, Guild Master
        (990100, 530, 0, 0, 1, 1, 9476.5, -7345.44, 16.183, 3.142, 300, 0, 0),   -- Silvermoon City -- by Tandrine, Guild Master
        (990100, 571, 0, 0, 1, 1, 5769.96, 627.193, 650.175, 3.613, 300, 0, 0),   -- Dalaran -- by Andrew Matthews, Guild Master
        (990100, 530, 0, 0, 1, 1, -1838.16, 5301.79, -12.43, 3.86, 300, 0, 0);   -- Shattrath City -- central terrace, by A'dal (no guild master here)
    ELSEIF EXISTS (SELECT 1 FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'creature' AND COLUMN_NAME = 'wander_distance') THEN
        DELETE FROM `creature` WHERE `id` = 990100;
        INSERT INTO `creature` (`id`, `map`, `zoneId`, `areaId`, `spawnMask`, `phaseMask`, `position_x`, `position_y`, `position_z`, `orientation`, `spawntimesecs`, `wander_distance`, `MovementType`)
        VALUES
        (990100, 0, 0, 0, 1, 1, -8883.25, 614.395, 95.3576, 3.526, 300, 0, 0),   -- Stormwind -- by Aldwin Laughlin, Guild Master (Trade District)
        (990100, 0, 0, 0, 1, 1, -5014.19, -997.442, 503.966, 2.793, 300, 0, 0),   -- Ironforge -- by Jondor Steelbrow, Guild Master (The Commons)
        (990100, 1, 0, 0, 1, 1, 10077.9, 2199.74, 1346.7, 1.833, 300, 0, 0),   -- Darnassus -- by Lysheana, Guild Master
        (990100, 530, 0, 0, 1, 1, -4090.43, -11626.6, -138.665, 4.224, 300, 0, 0),   -- The Exodar -- by Funaam, Guild Master
        (990100, 1, 0, 0, 1, 1, 1577.8, -4292.67, 26.2826, 4.381, 300, 0, 0),   -- Orgrimmar -- by Urtrun Clanbringer, Guild Master (Valley of Strength)
        (990100, 1, 0, 0, 1, 1, -1289.81, 127.206, 131.703, 6.056, 300, 0, 0),   -- Thunder Bluff -- by Krumn, Guild Master
        (990100, 0, 0, 0, 1, 1, 1593.25, 204.498, -55.2596, 1.728, 300, 0, 0),   -- Undercity -- by Christopher Drakul, Guild Master
        (990100, 530, 0, 0, 1, 1, 9476.5, -7345.44, 16.183, 3.142, 300, 0, 0),   -- Silvermoon City -- by Tandrine, Guild Master
        (990100, 571, 0, 0, 1, 1, 5769.96, 627.193, 650.175, 3.613, 300, 0, 0),   -- Dalaran -- by Andrew Matthews, Guild Master
        (990100, 530, 0, 0, 1, 1, -1838.16, 5301.79, -12.43, 3.86, 300, 0, 0);   -- Shattrath City -- central terrace, by A'dal (no guild master here)
    ELSE
        -- oldest schema variant: spawndist instead of wander_distance
        DELETE FROM `creature` WHERE `id` = 990100;
        INSERT INTO `creature` (`id`, `map`, `spawnMask`, `phaseMask`, `position_x`, `position_y`, `position_z`, `orientation`, `spawntimesecs`, `spawndist`, `MovementType`)
        VALUES
        (990100, 0, 1, 1, -8883.25, 614.395, 95.3576, 3.526, 300, 0, 0),   -- Stormwind -- by Aldwin Laughlin, Guild Master (Trade District)
        (990100, 0, 1, 1, -5014.19, -997.442, 503.966, 2.793, 300, 0, 0),   -- Ironforge -- by Jondor Steelbrow, Guild Master (The Commons)
        (990100, 1, 1, 1, 10077.9, 2199.74, 1346.7, 1.833, 300, 0, 0),   -- Darnassus -- by Lysheana, Guild Master
        (990100, 530, 1, 1, -4090.43, -11626.6, -138.665, 4.224, 300, 0, 0),   -- The Exodar -- by Funaam, Guild Master
        (990100, 1, 1, 1, 1577.8, -4292.67, 26.2826, 4.381, 300, 0, 0),   -- Orgrimmar -- by Urtrun Clanbringer, Guild Master (Valley of Strength)
        (990100, 1, 1, 1, -1289.81, 127.206, 131.703, 6.056, 300, 0, 0),   -- Thunder Bluff -- by Krumn, Guild Master
        (990100, 0, 1, 1, 1593.25, 204.498, -55.2596, 1.728, 300, 0, 0),   -- Undercity -- by Christopher Drakul, Guild Master
        (990100, 530, 1, 1, 9476.5, -7345.44, 16.183, 3.142, 300, 0, 0),   -- Silvermoon City -- by Tandrine, Guild Master
        (990100, 571, 1, 1, 5769.96, 627.193, 650.175, 3.613, 300, 0, 0),   -- Dalaran -- by Andrew Matthews, Guild Master
        (990100, 530, 1, 1, -1838.16, 5301.79, -12.43, 3.86, 300, 0, 0);   -- Shattrath City -- central terrace, by A'dal (no guild master here)
    END IF;
END//
DELIMITER ;
CALL cw_world_setup();
DROP PROCEDURE IF EXISTS cw_world_setup;
