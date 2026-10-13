-- mod-classless-wildcard: schema upgrade for databases created before the
-- per-character settings (adds no_auto_shot). Fresh installs already have it
-- from cw_characters_base.sql; the guard makes this a no-op there.
--
-- Sorts after cw_characters_challenges.sql, which adds `extra_life`, the
-- column this one is placed after.

DROP PROCEDURE IF EXISTS cw_upgrade_char_settings;
DELIMITER //
CREATE PROCEDURE cw_upgrade_char_settings()
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.TABLES
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cw_char_state')
       AND NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                       WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cw_char_state'
                         AND COLUMN_NAME = 'no_auto_shot') THEN
        ALTER TABLE `cw_char_state`
            ADD COLUMN `no_auto_shot` TINYINT UNSIGNED NOT NULL DEFAULT 0
                COMMENT '1: the player turned Auto Shot off in Settings' AFTER `extra_life`;
    END IF;
END//
DELIMITER ;
CALL cw_upgrade_char_settings();
DROP PROCEDURE IF EXISTS cw_upgrade_char_settings;
