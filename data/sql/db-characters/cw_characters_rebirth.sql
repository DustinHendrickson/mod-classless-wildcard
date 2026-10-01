-- mod-classless-wildcard: schema upgrade for databases created before Rebirth
-- became New Game Plus (adds the Rebirth rank column). Fresh installs already
-- have it from cw_characters_base.sql; the guard makes this a no-op there.
--
-- cw_char_abilities needs nothing: an heirloom is `source` = 4 in the column
-- that already exists.

DROP PROCEDURE IF EXISTS cw_upgrade_char_rebirth;
DELIMITER //
CREATE PROCEDURE cw_upgrade_char_rebirth()
BEGIN
    -- The table has to exist as well as lack the column: the updater applies a
    -- directory in lexicographic order and this file sorts AFTER base, but a
    -- realm that applies files by hand may not, and an ALTER on a missing
    -- table stops the whole install (see cw_characters_archetype.sql).
    IF EXISTS (SELECT 1 FROM information_schema.TABLES
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cw_char_state')
       AND NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                       WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cw_char_state'
                         AND COLUMN_NAME = 'rebirths') THEN
        ALTER TABLE `cw_char_state`
            ADD COLUMN `rebirths` INT UNSIGNED NOT NULL DEFAULT 0
                COMMENT 'Rebirths completed: the New Game Plus rank' AFTER `archetype`;
    END IF;
END//
DELIMITER ;
CALL cw_upgrade_char_rebirth();
DROP PROCEDURE IF EXISTS cw_upgrade_char_rebirth;
