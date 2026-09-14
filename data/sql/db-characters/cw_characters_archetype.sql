-- mod-classless-wildcard: schema upgrade for databases created before
-- archetypes became build templates (adds the followed-archetype column).
-- Fresh installs already have it from cw_characters_base.sql; the guard makes
-- this a no-op there -- which matters, because the updater applies this file
-- FIRST (a < b) and cw_char_state does not exist yet at that point.

DROP PROCEDURE IF EXISTS cw_upgrade_char_archetype;
DELIMITER //
CREATE PROCEDURE cw_upgrade_char_archetype()
BEGIN
    -- The TABLE has to be there too, not just the column. The DB updater
    -- applies a directory in lexicographic order, so this file runs BEFORE
    -- cw_characters_base.sql -- and base is what creates cw_char_state. On a
    -- fresh install the column test passed (no table, so no column), the ALTER
    -- ran against a table that did not exist yet and the whole install stopped
    -- on the first file. Checking the table first makes this a clean no-op
    -- there; base then creates cw_char_state with `archetype` already on it.
    IF EXISTS (SELECT 1 FROM information_schema.TABLES
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cw_char_state')
       AND NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                       WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cw_char_state'
                         AND COLUMN_NAME = 'archetype') THEN
        ALTER TABLE `cw_char_state`
            ADD COLUMN `archetype` INT UNSIGNED NOT NULL DEFAULT 0
                COMMENT 'cw_archetypes.id the Hero follows, 0 none' AFTER `display_power`;
    END IF;
END//
DELIMITER ;
CALL cw_upgrade_char_archetype();
DROP PROCEDURE IF EXISTS cw_upgrade_char_archetype;
