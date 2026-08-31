-- mod-classless-wildcard: schema upgrade for databases created by an earlier
-- version of cw_characters_base.sql (adds earned reroll charges and primary
-- stat allocation columns). Fresh installs already have these from the base
-- file; the guard makes this a no-op there.

DROP PROCEDURE IF EXISTS cw_upgrade_char_state;
DELIMITER //
CREATE PROCEDURE cw_upgrade_char_state()
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cw_char_state'
                     AND COLUMN_NAME = 'ability_rerolls') THEN
        ALTER TABLE `cw_char_state`
            ADD COLUMN `ability_rerolls` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `pity`,
            ADD COLUMN `talent_rerolls` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `ability_rerolls`;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cw_char_state'
                     AND COLUMN_NAME = 'stat_str') THEN
        ALTER TABLE `cw_char_state`
            ADD COLUMN `stat_str` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `last_level`,
            ADD COLUMN `stat_agi` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `stat_str`,
            ADD COLUMN `stat_sta` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `stat_agi`,
            ADD COLUMN `stat_int` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `stat_sta`,
            ADD COLUMN `stat_spi` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `stat_int`;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cw_char_state'
                     AND COLUMN_NAME = 'display_power') THEN
        ALTER TABLE `cw_char_state`
            ADD COLUMN `display_power` TINYINT UNSIGNED NOT NULL DEFAULT 255
                COMMENT '0 mana, 1 rage, 3 energy, 255 chassis default' AFTER `stat_spi`;
    END IF;
END//
DELIMITER ;
CALL cw_upgrade_char_state();
DROP PROCEDURE IF EXISTS cw_upgrade_char_state;
