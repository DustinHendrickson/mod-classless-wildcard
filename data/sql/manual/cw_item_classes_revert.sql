-- mod-classless-wildcard: put the class requirements back on items
--
-- Undoes data/sql/db-world/cw_world_item_classes.sql, which is applied
-- automatically and clears `item_template`.`AllowableClass` so any Hero can use
-- any class's armour, glyphs, poisons, bags and relics. This restores every
-- mask it recorded in `cw_item_class_backup`.
--
-- Only useful if you want the stock class gating back while keeping the rest of
-- the module. Note that the module will simply clear the column again the next
-- time the world SQL is re-applied (the updater re-runs a file whose contents
-- have changed), so to keep items gated, also delete
-- data/sql/db-world/cw_world_item_classes.sql from the module.
--
-- Apply by hand, with the worldserver stopped:
--     mysql acore_world < cw_item_classes_revert.sql

UPDATE `item_template` `it`
  JOIN `cw_item_class_backup` `b` ON `b`.`entry` = `it`.`entry`
  SET `it`.`AllowableClass` = `b`.`AllowableClass`;

-- The backup has served its purpose; drop it so a later re-apply takes a fresh
-- one rather than trusting a stale snapshot.
DROP TABLE IF EXISTS `cw_item_class_backup`;
