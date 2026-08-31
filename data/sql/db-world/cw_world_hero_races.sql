-- mod-classless-wildcard: every race can create the Hero (Warrior shell)
--
-- The client patch reduces the creation screen to one cosmetic class per
-- race -- Warrior, shown as "Hero". The pick means nothing: the server
-- converts every new character to the configured chassis the moment it is
-- created. Warrior is natively creatable for 9 of the 10 races, so all this
-- has to add is the one gap, Blood Elf, for which vanilla has no Warrior
-- rows. INSERT IGNORE makes it a no-op everywhere the rows already exist.
--
-- Start position comes from the race's own existing entries (Blood Elves
-- start where Blood Elves start); the action bar is copied from the Human
-- Warrior template. Starter items are irrelevant -- the module strips class
-- starter kits and hands out its own neutral kit at first login.

INSERT IGNORE INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`)
SELECT 10, 1, `map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`
FROM `playercreateinfo` WHERE `race`=10 AND `class`<>6 LIMIT 1;

INSERT IGNORE INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`)
SELECT 10, 1, `button`,`action`,`type`
FROM `playercreateinfo_action` WHERE `race`=1 AND `class`=1;
