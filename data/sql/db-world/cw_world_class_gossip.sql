-- mod-classless-wildcard: class gates in `conditions` and achievement data that
-- shut a Hero out
--
-- Every Hero is a Paladin to the core, so a condition that asks for another
-- class (ConditionMgr CONDITION_CLASS, getClassMask) never passes for one,
-- whatever that class's gear, pets or spells the Hero has.
--
--  * The Icecrown Citadel tier-10 vendors: each one's "browse your goods" is
--    gated to its own class (gossip menus 11095-11104 option 0, and Ormus the
--    Penitent's Scourge-lord armour, menu 10996 option 5). The items are open
--    to every Hero (cw_world_item_classes.sql), so only the Paladin vendor
--    answered and the other nine sets could not be bought.
--  * The pet trainers' "How do I train my pet?" and "I wish to untrain my pet"
--    (menu 4783, all 19 trainers) are hunter-only. A Hero's tamed beast has a
--    pet talent tree and could never reset it. Untraining now asks for a
--    hunter pet out (CONDITION_PET_TYPE, mask 1 << HUNTER_PET), which a real
--    Hunter needs for it anyway; the explanation is open to everyone.
--  * Soulok Stormfury's stable option (menu 9576 option 0) is hunter-only.
--  * The holiday achievements that want a race AND class of target ("Let It
--    Snow", "Fistful of Love", "Turkey Lurkey"): every Hero is a "<race>
--    Paladin", so most of their criteria could only be met on a bot. They now
--    ask for the race alone.
--
-- REVERSIBLE: the rows are copied before anything changes, and the world
-- uninstall script puts them back.

CREATE TABLE IF NOT EXISTS `cw_conditions_class_backup` LIKE `conditions`;

INSERT IGNORE INTO `cw_conditions_class_backup`
SELECT * FROM `conditions`
WHERE `SourceTypeOrReferenceId` = 15 AND `ConditionTypeOrReference` = 15
  AND ((`SourceGroup` BETWEEN 11095 AND 11104 AND `SourceEntry` = 0)
    OR (`SourceGroup` = 10996 AND `SourceEntry` = 5)
    OR (`SourceGroup` = 4783 AND `SourceEntry` IN (0, 1))
    OR (`SourceGroup` = 9576 AND `SourceEntry` = 0));

DELETE FROM `conditions`
WHERE `SourceTypeOrReferenceId` = 15 AND `ConditionTypeOrReference` = 15
  AND ((`SourceGroup` BETWEEN 11095 AND 11104 AND `SourceEntry` = 0)
    OR (`SourceGroup` = 10996 AND `SourceEntry` = 5)
    OR (`SourceGroup` = 4783 AND `SourceEntry` IN (0, 1))
    OR (`SourceGroup` = 9576 AND `SourceEntry` = 0));

DELETE FROM `conditions`
WHERE `SourceTypeOrReferenceId` = 15 AND `SourceGroup` = 4783 AND `SourceEntry` = 1
  AND `ConditionTypeOrReference` = 45;
INSERT INTO `conditions` (`SourceTypeOrReferenceId`, `SourceGroup`, `SourceEntry`, `SourceId`,
    `ElseGroup`, `ConditionTypeOrReference`, `ConditionTarget`, `ConditionValue1`,
    `ConditionValue2`, `ConditionValue3`, `NegativeCondition`, `ErrorType`, `ErrorTextId`,
    `ScriptName`, `Comment`) VALUES
(15, 4783, 1, 0, 0, 45, 0, 2, 0, 0, 0, 0, 0, '',
 'mod-classless-wildcard: untrain a pet only with a hunter pet out');

CREATE TABLE IF NOT EXISTS `cw_criteria_class_backup` (
  `criteria_id` INT NOT NULL COMMENT 'achievement_criteria_data.criteria_id',
  `type` TINYINT UNSIGNED NOT NULL COMMENT 'achievement_criteria_data.type',
  `value1` INT UNSIGNED NOT NULL COMMENT 'the class the criterion asked for',
  PRIMARY KEY (`criteria_id`, `type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Original class requirements of achievement criteria, so cw_world_class_gossip.sql can be undone';

-- type 2 only, the TARGET's class and race. Type 21 (the earner's own class)
-- is the Realm First! Level 80 per-class set, which stays as it is.
INSERT IGNORE INTO `cw_criteria_class_backup` (`criteria_id`, `type`, `value1`)
SELECT `criteria_id`, `type`, `value1` FROM `achievement_criteria_data`
WHERE `type` = 2 AND `value1` <> 0;

UPDATE `achievement_criteria_data` SET `value1` = 0
WHERE `type` = 2 AND `value1` <> 0;
