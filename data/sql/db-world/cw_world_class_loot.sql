-- mod-classless-wildcard: the armour-class gate on the Sons of Hodir satchels
--
-- Seven satchels (51999-52005) each reference three or four blocks of gear --
-- one per armour class -- and each block sits in its own loot GROUP with a
-- CONDITION_CLASS on it. Under the class system exactly one block matches you,
-- so a satchel hands over exactly one set.
--
-- A Hero matches the chassis's block and nothing else, so every satchel it
-- ever opened paid out plate. Every item is open to every Hero, so that is the
-- one thing this reward should not be deciding.
--
-- Dropping the conditions alone would pay out ALL the blocks, because they are
-- separate groups: a satchel would hand over three or four sets at once. So
-- the groups are collapsed into one at the same time, and the blocks are set
-- to Chance 0. A loot group picks a single entry, and entries at Chance 0 are
-- the equal-chanced kind, picked uniformly -- so a satchel still hands over
-- exactly one set, now any of them rather than the chassis's.
--
-- Chance 0 rather than the stock Chance 100 matters twice: four entries at 100
-- in one group is a total of 400%, which the loot loader reports as an error
-- at startup, and LootGroup::Roll returns the FIRST entry whose chance is 100
-- or more, so every satchel would pay out the same armour class every time.
--
-- Reversible with data/sql/manual/cw_class_loot_revert.sql.

DELETE FROM `conditions`
 WHERE `SourceTypeOrReferenceId` = 10
   AND `ConditionTypeOrReference` = 15
   AND `SourceGroup` BETWEEN 10036 AND 10061;

UPDATE `item_loot_template`
   SET `GroupId` = 1,
       `Chance`  = 0
 WHERE `Entry` BETWEEN 51999 AND 52005
   AND `Reference` BETWEEN 10036 AND 10061;
