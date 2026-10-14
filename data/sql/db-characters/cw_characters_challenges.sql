-- mod-classless-wildcard: schema upgrade for databases created before the
-- challenge runs (adds the run columns and the two run tables). Fresh installs
-- already have all of it from cw_characters_base.sql; the guards make this a
-- no-op there.

DROP PROCEDURE IF EXISTS cw_upgrade_char_challenges;
DELIMITER //
CREATE PROCEDURE cw_upgrade_char_challenges()
BEGIN
    -- The updater applies a directory in name order, and this file sorts
    -- BEFORE cw_characters_rebirth.sql, so on a realm from before Rebirth the
    -- `rebirths` column the run columns anchor on does not exist yet when
    -- this runs. Add it here first; the rebirth file then finds it and does
    -- nothing. (Seen live: "Unknown column 'rebirths'" stopped the whole
    -- character update.)
    IF EXISTS (SELECT 1 FROM information_schema.TABLES
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cw_char_state')
       AND NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                       WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cw_char_state'
                         AND COLUMN_NAME = 'rebirths') THEN
        ALTER TABLE `cw_char_state`
            ADD COLUMN `rebirths` INT UNSIGNED NOT NULL DEFAULT 0
                COMMENT 'Rebirths completed: the New Game Plus rank' AFTER `archetype`;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.TABLES
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cw_char_state')
       AND NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                       WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cw_char_state'
                         AND COLUMN_NAME = 'run') THEN
        ALTER TABLE `cw_char_state`
            ADD COLUMN `run` TINYINT UNSIGNED NOT NULL DEFAULT 0
                COMMENT 'challenge run live (ClasslessMgr.cpp CHALLENGES id), 0 none' AFTER `rebirths`,
            ADD COLUMN `lives` TINYINT UNSIGNED NOT NULL DEFAULT 0
                COMMENT 'lives left on the live run' AFTER `run`,
            ADD COLUMN `lives_max` TINYINT UNSIGNED NOT NULL DEFAULT 0
                COMMENT 'lives the live run started with' AFTER `lives`,
            ADD COLUMN `run_data` INT UNSIGNED NOT NULL DEFAULT 0
                COMMENT 'what the live rule remembers' AFTER `lives_max`,
            ADD COLUMN `shards` INT UNSIGNED NOT NULL DEFAULT 0
                COMMENT 'paid out by runs, spent at the panel' AFTER `run_data`,
            ADD COLUMN `extra_life` TINYINT UNSIGNED NOT NULL DEFAULT 0
                COMMENT 'a life bought for the next run' AFTER `shards`;
    END IF;
END//
DELIMITER ;
CALL cw_upgrade_char_challenges();
DROP PROCEDURE IF EXISTS cw_upgrade_char_challenges;

CREATE TABLE IF NOT EXISTS `cw_char_runs` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `guid` INT UNSIGNED NOT NULL,
  `challenge` TINYINT UNSIGNED NOT NULL,
  `level_reached` TINYINT UNSIGNED NOT NULL DEFAULT 1,
  `lives_used` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `finished` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `finished_at` INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `guid` (`guid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Challenge runs, one row per run ended';

CREATE TABLE IF NOT EXISTS `cw_char_nemeses` (
  `guid` INT UNSIGNED NOT NULL,
  `spawn_id` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'the creature that killed the Hero (creature.guid); 0 is a mark saved per kind before marks were per creature',
  `creature_entry` INT UNSIGNED NOT NULL,
  `levels` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `kills` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `stolen` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'experience this creature took, returned when it dies',
  `kind` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0 Marked (it killed the Hero), 1 Sworn (Swear Vendetta)',
  `strength1` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'NemesisStrength, 0 none',
  `strength2` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `strength3` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `weakness` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'NemesisWeakness',
  `learned` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '1 strengths known, 2 weakness known',
  PRIMARY KEY (`guid`, `spawn_id`, `creature_entry`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Nemesis marks on the live run';

CREATE TABLE IF NOT EXISTS `cw_char_nemesis_heads` (
  `guid` INT UNSIGNED NOT NULL,
  `creature_entry` INT UNSIGNED NOT NULL,
  PRIMARY KEY (`guid`, `creature_entry`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Nemesis heads on the live run: kinds slain while marked';

CREATE TABLE IF NOT EXISTS `cw_char_nemesis_run` (
  `guid` INT UNSIGNED NOT NULL,
  `vengeance` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'levels of nemeses slain on the live run',
  `pending` VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'trophies waiting for room, item entries joined by commas',
  PRIMARY KEY (`guid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Nemesis run Vengeance';

CREATE TABLE IF NOT EXISTS `cw_char_nemesis_charm` (
  `guid` INT UNSIGNED NOT NULL,
  `effect` TINYINT UNSIGNED NOT NULL COMMENT 'NemesisStrength',
  `rank` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0 to 5',
  PRIMARY KEY (`guid`, `effect`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Nemesis Charm ranks, kept for good';

-- Nemesis keeps the experience a creature kind took, to hand back when one of
-- them dies. Tables made before that get the column here; the guard makes
-- this a no-op where it is already there.
DROP PROCEDURE IF EXISTS cw_upgrade_char_nemesis_stolen;
DELIMITER //
CREATE PROCEDURE cw_upgrade_char_nemesis_stolen()
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cw_char_nemeses'
                     AND COLUMN_NAME = 'stolen') THEN
        ALTER TABLE `cw_char_nemeses`
            ADD COLUMN `stolen` INT UNSIGNED NOT NULL DEFAULT 0
                COMMENT 'experience this kind took, returned when one dies' AFTER `kills`;
    END IF;
END//
DELIMITER ;
CALL cw_upgrade_char_nemesis_stolen();
DROP PROCEDURE IF EXISTS cw_upgrade_char_nemesis_stolen;

-- A nemesis is one creature, held by its spawn id. Tables made when a mark lay
-- on a whole kind get the column here, with 0 on their old rows, which the
-- module lifts at login and pays back. The guard makes this a no-op where the
-- column is already there.
DROP PROCEDURE IF EXISTS cw_upgrade_char_nemesis_spawn;
DELIMITER //
CREATE PROCEDURE cw_upgrade_char_nemesis_spawn()
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cw_char_nemeses'
                     AND COLUMN_NAME = 'spawn_id') THEN
        ALTER TABLE `cw_char_nemeses`
            ADD COLUMN `spawn_id` INT UNSIGNED NOT NULL DEFAULT 0
                COMMENT 'the creature that killed the Hero (creature.guid); 0 is a mark saved per kind before marks were per creature'
                AFTER `guid`,
            DROP PRIMARY KEY,
            ADD PRIMARY KEY (`guid`, `spawn_id`, `creature_entry`);
    END IF;
END//
DELIMITER ;
CALL cw_upgrade_char_nemesis_spawn();
DROP PROCEDURE IF EXISTS cw_upgrade_char_nemesis_spawn;

-- How a nemesis was made and what it carries (PLAN-nemesis.md). Tables from
-- before get the columns here; the module gives old rows a strength and a
-- weakness when it loads them. No-op where they are already there.
DROP PROCEDURE IF EXISTS cw_upgrade_char_nemesis_traits;
DELIMITER //
CREATE PROCEDURE cw_upgrade_char_nemesis_traits()
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cw_char_nemeses'
                     AND COLUMN_NAME = 'kind') THEN
        ALTER TABLE `cw_char_nemeses`
            ADD COLUMN `kind` TINYINT UNSIGNED NOT NULL DEFAULT 0
                COMMENT '0 Marked (it killed the Hero), 1 Sworn (Swear Vendetta)' AFTER `stolen`,
            ADD COLUMN `strength1` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'NemesisStrength, 0 none' AFTER `kind`,
            ADD COLUMN `strength2` TINYINT UNSIGNED NOT NULL DEFAULT 0 AFTER `strength1`,
            ADD COLUMN `strength3` TINYINT UNSIGNED NOT NULL DEFAULT 0 AFTER `strength2`,
            ADD COLUMN `weakness` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'NemesisWeakness' AFTER `strength3`,
            ADD COLUMN `learned` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '1 strengths known, 2 weakness known' AFTER `weakness`;
    END IF;
END//
DELIMITER ;
CALL cw_upgrade_char_nemesis_traits();
DROP PROCEDURE IF EXISTS cw_upgrade_char_nemesis_traits;
