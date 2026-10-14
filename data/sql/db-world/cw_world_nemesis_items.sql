-- mod-classless-wildcard: Nemesis trophies and the Nemesis Charm.
--
-- A trophy drops from each slain nemesis on a Nemesis run: one per effect and
-- star count, entry 991000 + (effect - 1) * 3 + (stars - 1), effects in
-- NemesisStrength order (ClasslessWildcard.h). The charm, 991030, holds what
-- finished runs merged into it. What they give is the server's (ApplyNemesisFx,
-- the Nemesis.Star* options): these rows have no stats of their own, and the
-- addon's tooltip shows the numbers.

DELETE FROM `item_template` WHERE `entry` BETWEEN 991000 AND 991030;
INSERT INTO `item_template`
  (`entry`, `class`, `subclass`, `name`, `displayid`, `Quality`, `BuyCount`, `BuyPrice`, `SellPrice`,
   `InventoryType`, `AllowableClass`, `AllowableRace`, `ItemLevel`, `RequiredLevel`, `maxcount`, `stackable`, `Material`,
   `BagFamily`, `bonding`, `description`, `VerifiedBuild`)
VALUES
(991000, 15, 4, 'Trophy of Bloodlust I', 1310, 2, 1, 0, 0, 0, -1, -1, 1, 1, 0, 1, -1, 0, 1, '1 star of haste. Works from your bags on a Nemesis run. It cannot leave your bags.', 12340),
(991001, 15, 4, 'Trophy of Bloodlust II', 1310, 3, 1, 0, 0, 0, -1, -1, 1, 1, 0, 1, -1, 0, 1, '2 stars of haste. Works from your bags on a Nemesis run. It cannot leave your bags.', 12340),
(991002, 15, 4, 'Trophy of Bloodlust III', 1310, 4, 1, 0, 0, 0, -1, -1, 1, 1, 0, 1, -1, 0, 1, '3 stars of haste. Works from your bags on a Nemesis run. It cannot leave your bags.', 12340),
(991003, 15, 4, 'Trophy of Ironhide I', 3920, 2, 1, 0, 0, 0, -1, -1, 1, 1, 0, 1, -1, 0, 1, '1 star of armor. Works from your bags on a Nemesis run. It cannot leave your bags.', 12340),
(991004, 15, 4, 'Trophy of Ironhide II', 3920, 3, 1, 0, 0, 0, -1, -1, 1, 1, 0, 1, -1, 0, 1, '2 stars of armor. Works from your bags on a Nemesis run. It cannot leave your bags.', 12340),
(991005, 15, 4, 'Trophy of Ironhide III', 3920, 4, 1, 0, 0, 0, -1, -1, 1, 1, 0, 1, -1, 0, 1, '3 stars of armor. Works from your bags on a Nemesis run. It cannot leave your bags.', 12340),
(991006, 15, 4, 'Trophy of Spellward I', 5981, 2, 1, 0, 0, 0, -1, -1, 1, 1, 0, 1, -1, 0, 1, '1 star of resistance to every school. Works from your bags on a Nemesis run. It cannot leave your bags.', 12340),
(991007, 15, 4, 'Trophy of Spellward II', 5981, 3, 1, 0, 0, 0, -1, -1, 1, 1, 0, 1, -1, 0, 1, '2 stars of resistance to every school. Works from your bags on a Nemesis run. It cannot leave your bags.', 12340),
(991008, 15, 4, 'Trophy of Spellward III', 5981, 4, 1, 0, 0, 0, -1, -1, 1, 1, 0, 1, -1, 0, 1, '3 stars of resistance to every school. Works from your bags on a Nemesis run. It cannot leave your bags.', 12340),
(991009, 15, 4, 'Trophy of Venomous I', 53379, 2, 1, 0, 0, 0, -1, -1, 1, 1, 0, 1, -1, 0, 1, '1 star of critical strike chance. Works from your bags on a Nemesis run. It cannot leave your bags.', 12340),
(991010, 15, 4, 'Trophy of Venomous II', 53379, 3, 1, 0, 0, 0, -1, -1, 1, 1, 0, 1, -1, 0, 1, '2 stars of critical strike chance. Works from your bags on a Nemesis run. It cannot leave your bags.', 12340),
(991011, 15, 4, 'Trophy of Venomous III', 53379, 4, 1, 0, 0, 0, -1, -1, 1, 1, 0, 1, -1, 0, 1, '3 stars of critical strike chance. Works from your bags on a Nemesis run. It cannot leave your bags.', 12340),
(991012, 15, 4, 'Trophy of Unyielding I', 2744, 2, 1, 0, 0, 0, -1, -1, 1, 1, 0, 1, -1, 0, 1, '1 star of maximum health. Works from your bags on a Nemesis run. It cannot leave your bags.', 12340),
(991013, 15, 4, 'Trophy of Unyielding II', 2744, 3, 1, 0, 0, 0, -1, -1, 1, 1, 0, 1, -1, 0, 1, '2 stars of maximum health. Works from your bags on a Nemesis run. It cannot leave your bags.', 12340),
(991014, 15, 4, 'Trophy of Unyielding III', 2744, 4, 1, 0, 0, 0, -1, -1, 1, 1, 0, 1, -1, 0, 1, '3 stars of maximum health. Works from your bags on a Nemesis run. It cannot leave your bags.', 12340),
(991015, 15, 4, 'Trophy of Warband I', 9666, 2, 1, 0, 0, 0, -1, -1, 1, 1, 0, 1, -1, 0, 1, '1 star of attack power and spell power. Works from your bags on a Nemesis run. It cannot leave your bags.', 12340),
(991016, 15, 4, 'Trophy of Warband II', 9666, 3, 1, 0, 0, 0, -1, -1, 1, 1, 0, 1, -1, 0, 1, '2 stars of attack power and spell power. Works from your bags on a Nemesis run. It cannot leave your bags.', 12340),
(991017, 15, 4, 'Trophy of Warband III', 9666, 4, 1, 0, 0, 0, -1, -1, 1, 1, 0, 1, -1, 0, 1, '3 stars of attack power and spell power. Works from your bags on a Nemesis run. It cannot leave your bags.', 12340),
(991018, 15, 4, 'Trophy of Relentless I', 14023, 2, 1, 0, 0, 0, -1, -1, 1, 1, 0, 1, -1, 0, 1, '1 star of all primary stats. Works from your bags on a Nemesis run. It cannot leave your bags.', 12340),
(991019, 15, 4, 'Trophy of Relentless II', 14023, 3, 1, 0, 0, 0, -1, -1, 1, 1, 0, 1, -1, 0, 1, '2 stars of all primary stats. Works from your bags on a Nemesis run. It cannot leave your bags.', 12340),
(991020, 15, 4, 'Trophy of Relentless III', 14023, 4, 1, 0, 0, 0, -1, -1, 1, 1, 0, 1, -1, 0, 1, '3 stars of all primary stats. Works from your bags on a Nemesis run. It cannot leave your bags.', 12340),
(991030, 15, 4, 'Nemesis Charm', 23717, 5, 1, 0, 0, 0, -1, -1, 1, 1, 1, 1, -1, 0, 1, 'Made from the trophies of finished Nemesis runs. Works from your bags. It cannot leave your bags.', 12340);
