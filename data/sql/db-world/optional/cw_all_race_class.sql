-- mod-classless-wildcard: OPTIONAL — all race/class chassis combinations
--
-- Server-side half of the CharBaseInfo.dbc client patch: unlocks every
-- race/class pair for character creation. Class is only a chassis in the
-- classless system, so a Tauren mage-chassis is as valid as a Human one.
--
-- AzerothCore master derives stats from player_race_stats x player_class_stats,
-- so every combo already has correct stats; this file only adds the missing
-- start locations, action bars, and a basic starter kit (new combos have no
-- CharStartOutfit.dbc entry, so they'd otherwise spawn with nothing).
-- Death Knight rows ship complete for all races and are untouched.
--
-- Apply manually alongside the client patch:
--     mysql acore_world < cw_all_race_class.sql

INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 1, 1, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=1 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 1, 2, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=1 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 1, 3, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=1 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 1, 4, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=1 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 1, 5, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=1 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 1, 7, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=1 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 1, 8, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=1 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 1, 9, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=1 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 1, 11, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=1 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 2, 1, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=2 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 2, 2, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=2 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 2, 3, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=2 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 2, 4, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=2 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 2, 5, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=2 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 2, 7, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=2 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 2, 8, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=2 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 2, 9, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=2 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 2, 11, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=2 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 3, 1, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=3 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 3, 2, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=3 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 3, 3, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=3 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 3, 4, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=3 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 3, 5, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=3 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 3, 7, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=3 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 3, 8, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=3 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 3, 9, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=3 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 3, 11, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=3 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 4, 1, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=4 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 4, 2, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=4 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 4, 3, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=4 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 4, 4, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=4 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 4, 5, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=4 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 4, 7, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=4 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 4, 8, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=4 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 4, 9, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=4 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 4, 11, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=4 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 5, 1, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=5 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 5, 2, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=5 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 5, 3, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=5 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 5, 4, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=5 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 5, 5, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=5 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 5, 7, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=5 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 5, 8, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=5 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 5, 9, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=5 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 5, 11, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=5 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 6, 1, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=6 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 6, 2, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=6 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 6, 3, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=6 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 6, 4, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=6 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 6, 5, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=6 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 6, 7, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=6 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 6, 8, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=6 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 6, 9, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=6 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 6, 11, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=6 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 7, 1, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=7 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 7, 2, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=7 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 7, 3, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=7 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 7, 4, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=7 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 7, 5, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=7 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 7, 7, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=7 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 7, 8, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=7 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 7, 9, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=7 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 7, 11, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=7 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 8, 1, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=8 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 8, 2, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=8 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 8, 3, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=8 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 8, 4, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=8 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 8, 5, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=8 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 8, 7, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=8 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 8, 8, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=8 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 8, 9, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=8 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 8, 11, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=8 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 10, 1, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=10 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 10, 2, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=10 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 10, 3, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=10 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 10, 4, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=10 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 10, 5, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=10 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 10, 7, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=10 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 10, 8, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=10 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 10, 9, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=10 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 10, 11, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=10 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 11, 1, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=11 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 11, 2, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=11 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 11, 3, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=11 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 11, 4, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=11 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 11, 5, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=11 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 11, 7, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=11 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 11, 8, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=11 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 11, 9, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=11 AND `class`<>6 LIMIT 1;
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`) SELECT 11, 11, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` FROM `playercreateinfo` WHERE `race`=11 AND `class`<>6 LIMIT 1;

INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 1, 1, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=1;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 1, 2, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=2;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 1, 3, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=3 AND `class`=3;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 1, 4, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=4;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 1, 5, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=5;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 1, 7, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=2 AND `class`=7;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 1, 8, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=8;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 1, 9, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=9;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 1, 11, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=4 AND `class`=11;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 2, 1, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=1;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 2, 2, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=2;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 2, 3, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=3 AND `class`=3;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 2, 4, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=4;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 2, 5, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=5;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 2, 7, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=2 AND `class`=7;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 2, 8, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=8;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 2, 9, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=9;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 2, 11, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=4 AND `class`=11;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 3, 1, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=1;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 3, 2, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=2;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 3, 3, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=3 AND `class`=3;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 3, 4, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=4;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 3, 5, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=5;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 3, 7, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=2 AND `class`=7;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 3, 8, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=8;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 3, 9, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=9;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 3, 11, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=4 AND `class`=11;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 4, 1, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=1;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 4, 2, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=2;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 4, 3, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=3 AND `class`=3;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 4, 4, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=4;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 4, 5, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=5;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 4, 7, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=2 AND `class`=7;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 4, 8, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=8;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 4, 9, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=9;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 4, 11, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=4 AND `class`=11;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 5, 1, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=1;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 5, 2, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=2;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 5, 3, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=3 AND `class`=3;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 5, 4, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=4;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 5, 5, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=5;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 5, 7, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=2 AND `class`=7;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 5, 8, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=8;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 5, 9, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=9;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 5, 11, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=4 AND `class`=11;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 6, 1, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=1;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 6, 2, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=2;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 6, 3, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=3 AND `class`=3;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 6, 4, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=4;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 6, 5, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=5;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 6, 7, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=2 AND `class`=7;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 6, 8, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=8;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 6, 9, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=9;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 6, 11, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=4 AND `class`=11;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 7, 1, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=1;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 7, 2, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=2;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 7, 3, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=3 AND `class`=3;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 7, 4, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=4;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 7, 5, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=5;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 7, 7, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=2 AND `class`=7;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 7, 8, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=8;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 7, 9, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=9;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 7, 11, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=4 AND `class`=11;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 8, 1, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=1;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 8, 2, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=2;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 8, 3, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=3 AND `class`=3;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 8, 4, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=4;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 8, 5, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=5;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 8, 7, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=2 AND `class`=7;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 8, 8, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=8;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 8, 9, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=9;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 8, 11, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=4 AND `class`=11;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 10, 1, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=1;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 10, 2, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=2;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 10, 3, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=3 AND `class`=3;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 10, 4, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=4;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 10, 5, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=5;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 10, 7, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=2 AND `class`=7;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 10, 8, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=8;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 10, 9, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=9;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 10, 11, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=4 AND `class`=11;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 11, 1, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=1;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 11, 2, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=2;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 11, 3, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=3 AND `class`=3;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 11, 4, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=4;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 11, 5, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=5;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 11, 7, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=2 AND `class`=7;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 11, 8, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=8;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 11, 9, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=9;
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`) SELECT 11, 11, `button`,`action`,`type` FROM `playercreateinfo_action` WHERE `race`=4 AND `class`=11;

-- starter kit for combos with no CharStartOutfit entry (INSERT IGNORE keeps
-- original-combo outfits authoritative; duplicates with DBC outfits are fine)
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,1,25,1,'cw kit: Worn Shortsword');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,1,2362,1,'cw kit: Worn Wooden Shield');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,1,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,1,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,1,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,2,2361,1,'cw kit: Battleworn Hammer');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,2,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,2,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,2,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,3,2504,1,'cw kit: Worn Shortbow');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,3,2512,200,'cw kit: Rough Arrow');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,3,2101,1,'cw kit: Light Quiver');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,3,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,3,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,3,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,4,2092,1,'cw kit: Worn Dagger');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,4,3111,200,'cw kit: Crude Throwing Axe');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,4,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,4,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,4,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,5,36,1,'cw kit: Worn Mace');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,5,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,5,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,5,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,7,36,1,'cw kit: Worn Mace');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,7,2362,1,'cw kit: Worn Wooden Shield');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,7,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,7,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,7,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,8,35,1,'cw kit: Bent Staff');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,8,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,8,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,8,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,9,2092,1,'cw kit: Worn Dagger');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,9,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,9,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,9,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,11,35,1,'cw kit: Bent Staff');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,11,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,11,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (1,11,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,1,25,1,'cw kit: Worn Shortsword');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,1,2362,1,'cw kit: Worn Wooden Shield');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,1,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,1,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,1,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,2,2361,1,'cw kit: Battleworn Hammer');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,2,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,2,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,2,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,3,2504,1,'cw kit: Worn Shortbow');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,3,2512,200,'cw kit: Rough Arrow');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,3,2101,1,'cw kit: Light Quiver');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,3,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,3,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,3,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,4,2092,1,'cw kit: Worn Dagger');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,4,3111,200,'cw kit: Crude Throwing Axe');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,4,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,4,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,4,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,5,36,1,'cw kit: Worn Mace');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,5,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,5,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,5,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,7,36,1,'cw kit: Worn Mace');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,7,2362,1,'cw kit: Worn Wooden Shield');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,7,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,7,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,7,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,8,35,1,'cw kit: Bent Staff');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,8,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,8,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,8,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,9,2092,1,'cw kit: Worn Dagger');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,9,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,9,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,9,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,11,35,1,'cw kit: Bent Staff');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,11,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,11,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (2,11,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,1,25,1,'cw kit: Worn Shortsword');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,1,2362,1,'cw kit: Worn Wooden Shield');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,1,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,1,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,1,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,2,2361,1,'cw kit: Battleworn Hammer');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,2,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,2,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,2,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,3,2504,1,'cw kit: Worn Shortbow');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,3,2512,200,'cw kit: Rough Arrow');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,3,2101,1,'cw kit: Light Quiver');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,3,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,3,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,3,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,4,2092,1,'cw kit: Worn Dagger');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,4,3111,200,'cw kit: Crude Throwing Axe');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,4,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,4,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,4,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,5,36,1,'cw kit: Worn Mace');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,5,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,5,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,5,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,7,36,1,'cw kit: Worn Mace');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,7,2362,1,'cw kit: Worn Wooden Shield');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,7,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,7,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,7,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,8,35,1,'cw kit: Bent Staff');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,8,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,8,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,8,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,9,2092,1,'cw kit: Worn Dagger');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,9,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,9,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,9,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,11,35,1,'cw kit: Bent Staff');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,11,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,11,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (3,11,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,1,25,1,'cw kit: Worn Shortsword');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,1,2362,1,'cw kit: Worn Wooden Shield');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,1,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,1,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,1,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,2,2361,1,'cw kit: Battleworn Hammer');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,2,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,2,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,2,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,3,2504,1,'cw kit: Worn Shortbow');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,3,2512,200,'cw kit: Rough Arrow');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,3,2101,1,'cw kit: Light Quiver');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,3,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,3,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,3,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,4,2092,1,'cw kit: Worn Dagger');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,4,3111,200,'cw kit: Crude Throwing Axe');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,4,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,4,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,4,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,5,36,1,'cw kit: Worn Mace');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,5,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,5,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,5,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,7,36,1,'cw kit: Worn Mace');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,7,2362,1,'cw kit: Worn Wooden Shield');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,7,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,7,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,7,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,8,35,1,'cw kit: Bent Staff');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,8,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,8,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,8,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,9,2092,1,'cw kit: Worn Dagger');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,9,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,9,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,9,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,11,35,1,'cw kit: Bent Staff');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,11,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,11,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (4,11,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,1,25,1,'cw kit: Worn Shortsword');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,1,2362,1,'cw kit: Worn Wooden Shield');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,1,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,1,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,1,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,2,2361,1,'cw kit: Battleworn Hammer');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,2,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,2,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,2,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,3,2504,1,'cw kit: Worn Shortbow');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,3,2512,200,'cw kit: Rough Arrow');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,3,2101,1,'cw kit: Light Quiver');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,3,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,3,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,3,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,4,2092,1,'cw kit: Worn Dagger');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,4,3111,200,'cw kit: Crude Throwing Axe');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,4,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,4,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,4,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,5,36,1,'cw kit: Worn Mace');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,5,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,5,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,5,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,7,36,1,'cw kit: Worn Mace');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,7,2362,1,'cw kit: Worn Wooden Shield');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,7,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,7,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,7,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,8,35,1,'cw kit: Bent Staff');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,8,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,8,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,8,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,9,2092,1,'cw kit: Worn Dagger');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,9,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,9,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,9,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,11,35,1,'cw kit: Bent Staff');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,11,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,11,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (5,11,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,1,25,1,'cw kit: Worn Shortsword');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,1,2362,1,'cw kit: Worn Wooden Shield');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,1,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,1,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,1,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,2,2361,1,'cw kit: Battleworn Hammer');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,2,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,2,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,2,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,3,2504,1,'cw kit: Worn Shortbow');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,3,2512,200,'cw kit: Rough Arrow');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,3,2101,1,'cw kit: Light Quiver');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,3,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,3,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,3,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,4,2092,1,'cw kit: Worn Dagger');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,4,3111,200,'cw kit: Crude Throwing Axe');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,4,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,4,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,4,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,5,36,1,'cw kit: Worn Mace');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,5,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,5,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,5,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,7,36,1,'cw kit: Worn Mace');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,7,2362,1,'cw kit: Worn Wooden Shield');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,7,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,7,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,7,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,8,35,1,'cw kit: Bent Staff');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,8,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,8,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,8,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,9,2092,1,'cw kit: Worn Dagger');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,9,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,9,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,9,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,11,35,1,'cw kit: Bent Staff');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,11,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,11,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (6,11,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,1,25,1,'cw kit: Worn Shortsword');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,1,2362,1,'cw kit: Worn Wooden Shield');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,1,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,1,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,1,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,2,2361,1,'cw kit: Battleworn Hammer');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,2,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,2,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,2,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,3,2504,1,'cw kit: Worn Shortbow');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,3,2512,200,'cw kit: Rough Arrow');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,3,2101,1,'cw kit: Light Quiver');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,3,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,3,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,3,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,4,2092,1,'cw kit: Worn Dagger');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,4,3111,200,'cw kit: Crude Throwing Axe');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,4,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,4,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,4,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,5,36,1,'cw kit: Worn Mace');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,5,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,5,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,5,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,7,36,1,'cw kit: Worn Mace');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,7,2362,1,'cw kit: Worn Wooden Shield');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,7,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,7,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,7,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,8,35,1,'cw kit: Bent Staff');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,8,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,8,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,8,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,9,2092,1,'cw kit: Worn Dagger');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,9,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,9,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,9,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,11,35,1,'cw kit: Bent Staff');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,11,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,11,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (7,11,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,1,25,1,'cw kit: Worn Shortsword');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,1,2362,1,'cw kit: Worn Wooden Shield');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,1,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,1,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,1,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,2,2361,1,'cw kit: Battleworn Hammer');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,2,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,2,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,2,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,3,2504,1,'cw kit: Worn Shortbow');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,3,2512,200,'cw kit: Rough Arrow');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,3,2101,1,'cw kit: Light Quiver');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,3,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,3,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,3,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,4,2092,1,'cw kit: Worn Dagger');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,4,3111,200,'cw kit: Crude Throwing Axe');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,4,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,4,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,4,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,5,36,1,'cw kit: Worn Mace');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,5,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,5,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,5,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,7,36,1,'cw kit: Worn Mace');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,7,2362,1,'cw kit: Worn Wooden Shield');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,7,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,7,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,7,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,8,35,1,'cw kit: Bent Staff');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,8,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,8,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,8,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,9,2092,1,'cw kit: Worn Dagger');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,9,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,9,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,9,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,11,35,1,'cw kit: Bent Staff');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,11,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,11,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (8,11,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,1,25,1,'cw kit: Worn Shortsword');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,1,2362,1,'cw kit: Worn Wooden Shield');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,1,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,1,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,1,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,2,2361,1,'cw kit: Battleworn Hammer');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,2,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,2,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,2,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,3,2504,1,'cw kit: Worn Shortbow');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,3,2512,200,'cw kit: Rough Arrow');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,3,2101,1,'cw kit: Light Quiver');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,3,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,3,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,3,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,4,2092,1,'cw kit: Worn Dagger');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,4,3111,200,'cw kit: Crude Throwing Axe');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,4,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,4,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,4,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,5,36,1,'cw kit: Worn Mace');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,5,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,5,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,5,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,7,36,1,'cw kit: Worn Mace');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,7,2362,1,'cw kit: Worn Wooden Shield');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,7,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,7,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,7,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,8,35,1,'cw kit: Bent Staff');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,8,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,8,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,8,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,9,2092,1,'cw kit: Worn Dagger');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,9,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,9,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,9,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,11,35,1,'cw kit: Bent Staff');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,11,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,11,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (10,11,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,1,25,1,'cw kit: Worn Shortsword');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,1,2362,1,'cw kit: Worn Wooden Shield');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,1,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,1,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,1,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,2,2361,1,'cw kit: Battleworn Hammer');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,2,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,2,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,2,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,3,2504,1,'cw kit: Worn Shortbow');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,3,2512,200,'cw kit: Rough Arrow');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,3,2101,1,'cw kit: Light Quiver');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,3,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,3,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,3,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,4,2092,1,'cw kit: Worn Dagger');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,4,3111,200,'cw kit: Crude Throwing Axe');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,4,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,4,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,4,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,5,36,1,'cw kit: Worn Mace');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,5,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,5,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,5,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,7,36,1,'cw kit: Worn Mace');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,7,2362,1,'cw kit: Worn Wooden Shield');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,7,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,7,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,7,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,8,35,1,'cw kit: Bent Staff');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,8,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,8,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,8,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,9,2092,1,'cw kit: Worn Dagger');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,9,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,9,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,9,6948,1,'cw kit: Hearthstone');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,11,35,1,'cw kit: Bent Staff');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,11,117,10,'cw kit: Tough Jerky');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,11,159,10,'cw kit: Refreshing Spring Water');
INSERT IGNORE INTO `playercreateinfo_item` (`race`,`class`,`itemid`,`amount`,`Note`) VALUES (11,11,6948,1,'cw kit: Hearthstone');

-- ---------------------------------------------------------------------------
-- Older cores / forks (including some playerbot-branch databases) use a
-- per-race-per-class `player_levelstats` table instead of master's
-- player_race_stats x player_class_stats split. When that table exists, copy
-- stats for the new combos from a canonical donor race per class.
-- ---------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS cw_levelstats_combos;
DELIMITER //
CREATE PROCEDURE cw_levelstats_combos()
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.TABLES
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'player_levelstats') THEN
        -- donor races: warrior/paladin/rogue/priest/mage/warlock=human(1),
        -- hunter=dwarf(3), shaman=orc(2), druid=nightelf(4)
        INSERT IGNORE INTO `player_levelstats` (`race`,`class`,`level`,`str`,`agi`,`sta`,`inte`,`spi`)
        SELECT r.race, s.class, s.level, s.str, s.agi, s.sta, s.inte, s.spi
        FROM `player_levelstats` s
        JOIN (SELECT 1 race UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5
              UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 10 UNION SELECT 11) r
        WHERE (s.class IN (1,2,4,5,8,9) AND s.race = 1)
           OR (s.class = 3 AND s.race = 3)
           OR (s.class = 7 AND s.race = 2)
           OR (s.class = 11 AND s.race = 4);
    END IF;
END//
DELIMITER ;
CALL cw_levelstats_combos();
DROP PROCEDURE IF EXISTS cw_levelstats_combos;

-- ---------------------------------------------------------------------------
-- Forks that serve DBC data from the database (charstartoutfit_dbc table
-- present, e.g. the playerbot-branch schema): give the new combos REAL
-- starting outfits by copying the donor race's outfit per class (both sexes).
-- The basic kit above still applies everywhere; maxcount-limited items like
-- the Hearthstone self-deduplicate.
-- ---------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS cw_startoutfit_combos;
DELIMITER //
CREATE PROCEDURE cw_startoutfit_combos()
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.TABLES
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'charstartoutfit_dbc') THEN
        INSERT INTO `charstartoutfit_dbc` (`ID`, `RaceID`, `ClassID`, `SexID`, `OutfitID`, `ItemID_1`, `ItemID_2`, `ItemID_3`, `ItemID_4`, `ItemID_5`, `ItemID_6`, `ItemID_7`, `ItemID_8`, `ItemID_9`, `ItemID_10`, `ItemID_11`, `ItemID_12`, `ItemID_13`, `ItemID_14`, `ItemID_15`, `ItemID_16`, `ItemID_17`, `ItemID_18`, `ItemID_19`, `ItemID_20`, `ItemID_21`, `ItemID_22`, `ItemID_23`, `ItemID_24`, `DisplayItemID_1`, `DisplayItemID_2`, `DisplayItemID_3`, `DisplayItemID_4`, `DisplayItemID_5`, `DisplayItemID_6`, `DisplayItemID_7`, `DisplayItemID_8`, `DisplayItemID_9`, `DisplayItemID_10`, `DisplayItemID_11`, `DisplayItemID_12`, `DisplayItemID_13`, `DisplayItemID_14`, `DisplayItemID_15`, `DisplayItemID_16`, `DisplayItemID_17`, `DisplayItemID_18`, `DisplayItemID_19`, `DisplayItemID_20`, `DisplayItemID_21`, `DisplayItemID_22`, `DisplayItemID_23`, `DisplayItemID_24`, `InventoryType_1`, `InventoryType_2`, `InventoryType_3`, `InventoryType_4`, `InventoryType_5`, `InventoryType_6`, `InventoryType_7`, `InventoryType_8`, `InventoryType_9`, `InventoryType_10`, `InventoryType_11`, `InventoryType_12`, `InventoryType_13`, `InventoryType_14`, `InventoryType_15`, `InventoryType_16`, `InventoryType_17`, `InventoryType_18`, `InventoryType_19`, `InventoryType_20`, `InventoryType_21`, `InventoryType_22`, `InventoryType_23`, `InventoryType_24`)
        SELECT 900000 + r.race * 1000 + o.`ClassID` * 100 + o.`SexID` * 10,
               r.race, o.`ClassID`, o.`SexID`, o.`OutfitID`, o.`ItemID_1`, o.`ItemID_2`, o.`ItemID_3`, o.`ItemID_4`, o.`ItemID_5`, o.`ItemID_6`, o.`ItemID_7`, o.`ItemID_8`, o.`ItemID_9`, o.`ItemID_10`, o.`ItemID_11`, o.`ItemID_12`, o.`ItemID_13`, o.`ItemID_14`, o.`ItemID_15`, o.`ItemID_16`, o.`ItemID_17`, o.`ItemID_18`, o.`ItemID_19`, o.`ItemID_20`, o.`ItemID_21`, o.`ItemID_22`, o.`ItemID_23`, o.`ItemID_24`, o.`DisplayItemID_1`, o.`DisplayItemID_2`, o.`DisplayItemID_3`, o.`DisplayItemID_4`, o.`DisplayItemID_5`, o.`DisplayItemID_6`, o.`DisplayItemID_7`, o.`DisplayItemID_8`, o.`DisplayItemID_9`, o.`DisplayItemID_10`, o.`DisplayItemID_11`, o.`DisplayItemID_12`, o.`DisplayItemID_13`, o.`DisplayItemID_14`, o.`DisplayItemID_15`, o.`DisplayItemID_16`, o.`DisplayItemID_17`, o.`DisplayItemID_18`, o.`DisplayItemID_19`, o.`DisplayItemID_20`, o.`DisplayItemID_21`, o.`DisplayItemID_22`, o.`DisplayItemID_23`, o.`DisplayItemID_24`, o.`InventoryType_1`, o.`InventoryType_2`, o.`InventoryType_3`, o.`InventoryType_4`, o.`InventoryType_5`, o.`InventoryType_6`, o.`InventoryType_7`, o.`InventoryType_8`, o.`InventoryType_9`, o.`InventoryType_10`, o.`InventoryType_11`, o.`InventoryType_12`, o.`InventoryType_13`, o.`InventoryType_14`, o.`InventoryType_15`, o.`InventoryType_16`, o.`InventoryType_17`, o.`InventoryType_18`, o.`InventoryType_19`, o.`InventoryType_20`, o.`InventoryType_21`, o.`InventoryType_22`, o.`InventoryType_23`, o.`InventoryType_24`
        FROM `charstartoutfit_dbc` o
        JOIN (SELECT 1 race UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5
              UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 10 UNION SELECT 11) r
        JOIN (SELECT 1 class, 1 donor UNION SELECT 2, 1 UNION SELECT 3, 3 UNION SELECT 4, 1
              UNION SELECT 5, 1 UNION SELECT 7, 2 UNION SELECT 8, 1 UNION SELECT 9, 1
              UNION SELECT 11, 4) d ON d.class = o.`ClassID` AND o.`RaceID` = d.donor
        WHERE NOT EXISTS (SELECT 1 FROM `charstartoutfit_dbc` x
                          WHERE x.`RaceID` = r.race AND x.`ClassID` = o.`ClassID` AND x.`SexID` = o.`SexID`);
    END IF;
END//
DELIMITER ;
CALL cw_startoutfit_combos();
DROP PROCEDURE IF EXISTS cw_startoutfit_combos;
