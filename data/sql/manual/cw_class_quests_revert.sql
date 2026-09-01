-- mod-classless-wildcard: put the class requirements back on quests
--
-- Undoes data/sql/db-world/cw_world_class_quests.sql, which is applied
-- automatically and clears `quest_template_addon`.`AllowableClasses` so any
-- Hero can take any class's quest chain. This restores every mask it recorded
-- in `cw_quest_class_backup`.
--
-- Only useful if you want the stock class gating back while keeping the rest of
-- the module. Note that the module will simply clear the column again the next
-- time the world SQL is re-applied (the updater re-runs a file whose contents
-- have changed), so to keep quests gated, also delete
-- data/sql/db-world/cw_world_class_quests.sql from the module.
--
-- Apply by hand, with the worldserver stopped:
--     mysql acore_world < cw_class_quests_revert.sql

UPDATE `quest_template_addon` `qta`
  JOIN `cw_quest_class_backup` `b` ON `b`.`ID` = `qta`.`ID`
  SET `qta`.`AllowableClasses` = `b`.`AllowableClasses`;

-- The backup has served its purpose; drop it so a later re-apply takes a fresh
-- one rather than trusting a stale snapshot.
DROP TABLE IF EXISTS `cw_quest_class_backup`;
