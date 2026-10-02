-- mod-classless-wildcard: the challenge runs' creature.
--
-- Pursued's hunter. Spawned by the server at the Hero's side every 15 to 30
-- minutes of played time, releveled on the spot to the Hero's level plus two and made elite
-- by hand (CW_ReLevelCreature), so the level range here is only a floor and a
-- ceiling. Faction 14 is hostile to everyone. The model is the Syndicate
-- Assassin's (display 3727, Syndicate Assassin 2246 in the core's own dump),
-- a hooded human: something that looks like it came for you.

DELETE FROM `creature_template` WHERE `entry` = 990131;
INSERT INTO `creature_template`
  (`entry`, `name`, `subname`, `minlevel`, `maxlevel`, `faction`, `npcflag`, `unit_class`,
   `unit_flags`, `type`, `type_flags`, `RegenHealth`, `flags_extra`, `speed_walk`, `speed_run`, `DamageModifier`, `HealthModifier`, `ScriptName`, `VerifiedBuild`)
VALUES
(990131, 'Relentless Hunter', 'Pursuer', 1, 80, 14, 0, 1, 0, 7, 0, 1, 0, 1.0, 1.14286, 1.00, 1.00, '', 12340);

DELETE FROM `creature_template_model` WHERE `CreatureID` = 990131;
INSERT INTO `creature_template_model` (`CreatureID`, `Idx`, `CreatureDisplayID`, `DisplayScale`, `Probability`, `VerifiedBuild`) VALUES
(990131, 0, 3727, 1.00, 1, 12340);
