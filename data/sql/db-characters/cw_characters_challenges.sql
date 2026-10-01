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
  `creature_entry` INT UNSIGNED NOT NULL,
  `levels` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `kills` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`guid`, `creature_entry`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Nemesis marks on the live run';
