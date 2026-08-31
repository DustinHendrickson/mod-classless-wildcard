-- mod-classless-wildcard: WORLD DB uninstall.
-- NOT auto-applied — run by hand, with the worldserver STOPPED, only when
-- removing the module. See "Uninstall / revert" in README.md.

-- module tables
DROP TABLE IF EXISTS `cw_ability_override`;
DROP TABLE IF EXISTS `cw_talent_override`;
DROP TABLE IF EXISTS `cw_archetypes`;

-- module items: scrolls + classless item pack
DELETE FROM `item_template` WHERE `entry` IN (990101, 990102)
   OR (`entry` BETWEEN 990201 AND 990212);

-- Hero Advancement NPC: vendor, template and spawns (schema-adaptive:
-- playerbots forks use creature.id1, stock uses creature.id)
DELETE FROM `npc_vendor` WHERE `entry` = 990100;
DROP PROCEDURE IF EXISTS cw_uninstall_npc;
DELIMITER //
CREATE PROCEDURE cw_uninstall_npc()
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.COLUMNS
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'creature'
                 AND COLUMN_NAME = 'id1') THEN
        DELETE FROM `creature` WHERE `id1` = 990100;
    ELSEIF EXISTS (SELECT 1 FROM information_schema.COLUMNS
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'creature'
                 AND COLUMN_NAME = 'id') THEN
        DELETE FROM `creature` WHERE `id` = 990100;
    END IF;
END//
DELIMITER ;
CALL cw_uninstall_npc();
DROP PROCEDURE IF EXISTS cw_uninstall_npc;
DELETE FROM `creature_template_model` WHERE `CreatureID` = 990100;
DELETE FROM `creature_template` WHERE `entry` = 990100;

-- all-race/class skill validity rows (restores stock race/class skill rules;
-- at next login the core deletes now-invalid cross-class spells and skills
-- from every character automatically)
DELETE FROM `skillraceclassinfo_dbc` WHERE `ID` BETWEEN 990000 AND 990999;

-- rows added by the OPTIONAL cw_all_race_class.sql (no-ops if never applied)
DELETE FROM `charstartoutfit_dbc` WHERE `ID` >= 900000;

-- module DB-updater bookkeeping, so reinstalling later re-applies cleanly
DELETE FROM `updates` WHERE `name` LIKE 'cw_%';

-- NOT handled here (no safe automatic revert):
--  * optional/cw_classless_items.sql overwrote item_template.AllowableClass
--    with -1 for ALL items. Restore item_template from your pre-install
--    backup, or re-import item_template from the AzerothCore base SQL that
--    matches your core revision.
--  * optional/cw_all_race_class.sql playercreateinfo* INSERTs are harmless to
--    keep (the client no longer offers those combos); restore from backup if
--    you want them gone.
