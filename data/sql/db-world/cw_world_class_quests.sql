-- mod-classless-wildcard: let any Hero take any class's quests
--
-- Every Hero shares one base class, so under stock rules the only class quests
-- a character can see are that one chassis class's. Everything else -- the
-- warrior's Whirlwind Axe chain, the warlock's pet summoning quests, the
-- shaman's totem quests, every class mount and ability chain in the game --
-- would be permanently unreachable content. Clearing the class requirement
-- makes all of it available to everyone.
--
-- The column is `quest_template_addon`.`AllowableClasses`, NOT
-- `quest_template`: quest_template has no such column in AzerothCore, and the
-- core reads the requirement in Quest::LoadQuestTemplateAddon (it lands in
-- Quest::RequiredClasses, which Player::SatisfyQuestClass checks). An earlier
-- version of this script updated quest_template and failed outright.
--
-- Ability rewards are still governed by the module: it reverts any class-library
-- spell learned outside its own system (ClasslessWildcard.BlockOutsideSpellSources,
-- on by default), so a quest that would teach a class ability grants nothing.
-- Item, XP, gold and reputation rewards work as normal.
--
-- REVERSIBLE. The original masks are copied into `cw_quest_class_backup` before
-- anything is overwritten; data/sql/manual/cw_class_quests_revert.sql puts them
-- back, and the world uninstall script does the same.

CREATE TABLE IF NOT EXISTS `cw_quest_class_backup` (
  `ID` INT UNSIGNED NOT NULL COMMENT 'quest_template_addon.ID',
  `AllowableClasses` INT UNSIGNED NOT NULL COMMENT 'the class mask before the module cleared it',
  PRIMARY KEY (`ID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Original quest class requirements, so cw_world_class_quests.sql can be undone';

-- INSERT IGNORE, and only rows that still carry a restriction: re-applying this
-- file after the update has run finds nothing left to record, so a backup taken
-- the first time is never overwritten with the zeroes we just wrote.
INSERT IGNORE INTO `cw_quest_class_backup` (`ID`, `AllowableClasses`)
SELECT `ID`, `AllowableClasses` FROM `quest_template_addon` WHERE `AllowableClasses` <> 0;

UPDATE `quest_template_addon` SET `AllowableClasses` = 0 WHERE `AllowableClasses` <> 0;
