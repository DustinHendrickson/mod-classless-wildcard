-- mod-classless-wildcard: the challenge runs' creature.
--
-- Pursued's hunter. Spawned by the server at the Hero's side every 15 to 30
-- minutes of played time, releveled on the spot to the Hero's level plus two and made elite
-- by hand (CW_ReLevelCreature), so the level range here is only a floor and a
-- ceiling. Faction 14 is hostile to everyone. The model is the Syndicate
-- Assassin's (display 3727, Syndicate Assassin 2246 in the core's own dump),
-- a hooded human: something that looks like it came for you.

--
-- Entry 990099. It was 990131 until 2026-10-14, an id cw_world_vendor_lists.sql
-- also claims for a vendor list and loads after this file, so the hunter was
-- overwritten by a civilian, unattackable vendor clone. 990131 is left to the
-- vendor list. Rank 2 (rare elite): the core pays elite experience on it and
-- draws the rare elite dragon, and its health and damage come from the realm's
-- RAREELITE rates (CW_ReLevelCreature).

DELETE FROM `creature_template` WHERE `entry` = 990099;
INSERT INTO `creature_template`
  (`entry`, `name`, `subname`, `minlevel`, `maxlevel`, `faction`, `npcflag`, `unit_class`,
   `unit_flags`, `type`, `type_flags`, `rank`, `RegenHealth`, `flags_extra`, `speed_walk`, `speed_run`, `DamageModifier`, `HealthModifier`, `ScriptName`, `VerifiedBuild`)
VALUES
(990099, 'Relentless Hunter', 'Pursuer', 1, 80, 14, 0, 1, 0, 7, 0, 2, 1, 0, 1.0, 1.14286, 1.00, 1.00, '', 12340);

DELETE FROM `creature_template_model` WHERE `CreatureID` = 990099;
INSERT INTO `creature_template_model` (`CreatureID`, `Idx`, `CreatureDisplayID`, `DisplayScale`, `Probability`, `VerifiedBuild`) VALUES
(990099, 0, 3727, 1.00, 1, 12340);
