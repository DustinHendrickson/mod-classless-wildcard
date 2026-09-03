-- mod-classless-wildcard: schema upgrade for databases created before
-- archetypes became build templates (adds the followed-archetype column).
-- Fresh installs already have it from cw_characters_base.sql; the guard makes
-- this a no-op there.

DROP PROCEDURE IF EXISTS cw_upgrade_char_archetype;
DELIMITER //
CREATE PROCEDURE cw_upgrade_char_archetype()
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
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
