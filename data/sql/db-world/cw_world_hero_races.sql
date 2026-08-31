-- mod-classless-wildcard: every race can create the Hero (Paladin chassis)
--
-- The client patch reduces the creation screen to one class per race -- the
-- Paladin chassis, shown as "Hero". Paladin is the chassis so a Hero is a
-- Paladin from creation (native mana, no runtime class change). Vanilla only
-- lets Human/Dwarf/Draenei/Blood Elf be Paladins, so this adds the missing
-- playercreateinfo rows for the other races. INSERT IGNORE is a no-op where
-- a row already exists.
--
-- Stats derive from player_race_stats x player_class_stats on AzerothCore
-- master, so only the start position and action bar need adding. Starter
-- items are irrelevant -- the module strips class kits and grants its own.

-- start position: copy each race's own existing spawn (any non-DK class)
INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`)
SELECT 1, 2, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`
FROM `playercreateinfo` WHERE `race`=1 AND `class`<>6 LIMIT 1;   -- Human

INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`)
SELECT 2, 2, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`
FROM `playercreateinfo` WHERE `race`=2 AND `class`<>6 LIMIT 1;   -- Orc

INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`)
SELECT 3, 2, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`
FROM `playercreateinfo` WHERE `race`=3 AND `class`<>6 LIMIT 1;   -- Dwarf

INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`)
SELECT 4, 2, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`
FROM `playercreateinfo` WHERE `race`=4 AND `class`<>6 LIMIT 1;   -- Night Elf

INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`)
SELECT 5, 2, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`
FROM `playercreateinfo` WHERE `race`=5 AND `class`<>6 LIMIT 1;   -- Undead

INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`)
SELECT 6, 2, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`
FROM `playercreateinfo` WHERE `race`=6 AND `class`<>6 LIMIT 1;   -- Tauren

INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`)
SELECT 7, 2, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`
FROM `playercreateinfo` WHERE `race`=7 AND `class`<>6 LIMIT 1;   -- Gnome

INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`)
SELECT 8, 2, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`
FROM `playercreateinfo` WHERE `race`=8 AND `class`<>6 LIMIT 1;   -- Troll

INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`)
SELECT 10, 2, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`
FROM `playercreateinfo` WHERE `race`=10 AND `class`<>6 LIMIT 1;   -- Blood Elf

INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`)
SELECT 11, 2, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`
FROM `playercreateinfo` WHERE `race`=11 AND `class`<>6 LIMIT 1;   -- Draenei

-- action bar: copy the Human Paladin template for every race
INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`)
SELECT 1, 2, `button`,`action`,`type`
FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=2;   -- Human

INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`)
SELECT 2, 2, `button`,`action`,`type`
FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=2;   -- Orc

INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`)
SELECT 3, 2, `button`,`action`,`type`
FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=2;   -- Dwarf

INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`)
SELECT 4, 2, `button`,`action`,`type`
FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=2;   -- Night Elf

INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`)
SELECT 5, 2, `button`,`action`,`type`
FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=2;   -- Undead

INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`)
SELECT 6, 2, `button`,`action`,`type`
FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=2;   -- Tauren

INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`)
SELECT 7, 2, `button`,`action`,`type`
FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=2;   -- Gnome

INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`)
SELECT 8, 2, `button`,`action`,`type`
FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=2;   -- Troll

INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`)
SELECT 10, 2, `button`,`action`,`type`
FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=2;   -- Blood Elf

INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`)
SELECT 11, 2, `button`,`action`,`type`
FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=2;   -- Draenei
