-- mod-classless-wildcard: WORLD DB uninstall.
-- NOT auto-applied — run by hand, with the worldserver STOPPED, only when
-- removing the module. See "Uninstall / revert" in README.md.

-- Class requirements on quests, put back before the backup table is dropped.
-- The module clears quest_template_addon.AllowableClasses so any Hero can take
-- any class's chain; these are the masks it recorded on the way in. Guarded,
-- because the table is absent on an install that never applied the world SQL
-- and a missing-table error here would abort the rest of this script.
DROP PROCEDURE IF EXISTS cw_uninstall_quests;
DELIMITER //
CREATE PROCEDURE cw_uninstall_quests()
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.TABLES
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'cw_quest_class_backup') THEN
        UPDATE `quest_template_addon` `qta`
          JOIN `cw_quest_class_backup` `b` ON `b`.`ID` = `qta`.`ID`
          SET `qta`.`AllowableClasses` = `b`.`AllowableClasses`;
    END IF;
END//
DELIMITER ;
CALL cw_uninstall_quests();
DROP PROCEDURE IF EXISTS cw_uninstall_quests;

-- module tables
DROP TABLE IF EXISTS `cw_quest_class_backup`;
DROP TABLE IF EXISTS `cw_form_kits`;
DROP TABLE IF EXISTS `cw_ability_override`;
DROP TABLE IF EXISTS `cw_talent_override`;
DROP TABLE IF EXISTS `cw_archetypes`;

-- module items: scrolls + classless item pack
DELETE FROM `item_template` WHERE `entry` IN (990101, 990102)
   OR (`entry` BETWEEN 990201 AND 990212)   -- classless item pack
   OR (`entry` BETWEEN 990250 AND 990272)   -- Hero heirlooms
   OR (`entry` BETWEEN 990280 AND 990295)   -- classless item pack II
   OR (`entry` BETWEEN 990300 AND 990497);  -- tiered classless gear

-- vendor visibility conditions (older versions gated the tiered gear by level;
-- the shop is split into browsable lists now and installs none of these)
DELETE FROM `conditions` WHERE `SourceTypeOrReferenceId` = 23 AND `SourceGroup` = 990100;

-- The split vendor lists: one packet holds 150 items, so the catalogue is
-- spread over lists 990110+, each fronted by its own unspawned creature_template
-- clone. Remove those with their rows.
DELETE FROM `npc_vendor` WHERE `entry` BETWEEN 990110 AND 990209;
DELETE FROM `creature_template_model` WHERE `CreatureID` BETWEEN 990110 AND 990209;
DELETE FROM `creature_template` WHERE `entry` BETWEEN 990110 AND 990209;

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

-- playercreateinfo rows added by cw_world_hero_races.sql (and by the older
-- cw_all_race_class.sql, for installs that predate it) — no-ops if absent
DELETE FROM `charstartoutfit_dbc` WHERE `ID` >= 900000;

-- module DB-updater bookkeeping, so reinstalling later re-applies cleanly
DELETE FROM `updates` WHERE `name` LIKE 'cw_%';

-- NOT handled here (no safe automatic revert):
--  * manual/cw_classless_items.sql overwrote item_template.AllowableClass
--    with -1 for ALL items. Restore item_template from your pre-install
--    backup, or re-import item_template from the AzerothCore base SQL that
--    matches your core revision.
--  * leftover playercreateinfo* INSERTs from older versions are harmless to
--    keep (the client no longer offers those combos); restore from backup if
--    you want them gone.
