-- mod-classless-wildcard: Hero heirlooms (level-scaling gear)
--
-- Heirlooms are the 3.3.5 client's own level-scaling system, so these grow with
-- the character from level 1 to 80 with no custom code:
--
--   Quality 7 + Flags 134221824  -> heirloom quality and account binding
--   ScalingStatDistribution      -> WHICH stats the item gives (client DBC id)
--   ScalingStatValue             -> HOW MUCH, per slot, looked up by player level
--
-- Both DBCs ship with every stock 3.3.5a client, so only real ids are used here
-- (taken from Blizzard's own heirlooms) and NO client patch is needed. The
-- ScalingStatValue masks are likewise copied from live heirlooms:
--
--   shoulder  0x01 + armor(cloth 0x20 / leather 0x40 / mail 0x80 / plate 0x100)
--   chest     0x08 + armor(cloth 0x100000 / leather 0x200000 / mail 0x400000 /
--                          plate 0x800000), cloak 0x80000
--   weapon    1H 0x04|0x200 = 516, 2H 0x08|0x400 = 1032,
--             caster 1H 0x04|0x800 = 2052, caster 2H 0x08|0x1000 = 4104,
--             ranged 0x10|0x2000 = 8208
--   trinket   0x02
--
-- The point of the set is that a Hero can wear ANY armor with ANY stats, so it
-- deliberately pairs armor classes with the stats their original class could
-- never use: spellpower plate, strength mail, agility cloth.
--
-- Stats, armor and weapon damage all come from the scaling tables, which is why
-- every stat/armor/damage column below is zero.

DELETE FROM `item_template` WHERE `entry` BETWEEN 990250 AND 990272;
INSERT INTO `item_template`
  (`entry`, `class`, `subclass`, `name`, `displayid`, `Quality`, `Flags`, `BuyCount`,
   `BuyPrice`, `SellPrice`, `InventoryType`, `AllowableClass`, `AllowableRace`,
   `ItemLevel`, `RequiredLevel`, `stackable`, `ScalingStatDistribution`, `ScalingStatValue`,
   `dmg_type1`, `delay`, `bonding`, `MaxDurability`, `Material`, `sheath`,
   `description`, `VerifiedBuild`)
VALUES
-- ---------------------------------------------------------------------------
-- Weapons -- one of every family, including the combinations no class gets
-- ---------------------------------------------------------------------------
(990250, 2, 7, 'Everkeen Warblade', 32722, 7, 134221824, 1, 65000, 13000, 13, -1, -1, 1, 1, 1,
   1, 516, 0, 2600, 1, 100, 1, 3,
 'Strength, stamina and crit -- and it never outgrows you.', 12340),
(990251, 2, 15, 'Everkeen Fang', 29706, 7, 134221824, 1, 65000, 13000, 13, -1, -1, 1, 1, 1,
   2, 516, 0, 1700, 1, 100, 1, 3,
 'A dagger that sharpens itself as you rise.', 12340),
(990252, 2, 7, 'Everkeen Spellblade', 31309, 7, 134221824, 1, 65000, 13000, 13, -1, -1, 1, 1, 1,
   334, 2052, 0, 2400, 1, 100, 1, 3,
 'A sword that carries spellpower instead of muscle.', 12340),
(990253, 2, 1, 'Everkeen Reaver', 31735, 7, 134221824, 1, 100000, 20000, 17, -1, -1, 1, 1, 1,
   1, 1032, 0, 3600, 1, 130, 1, 1,
 'Two hands, one very long career.', 12340),
(990254, 2, 10, 'Everkeen Battlestaff', 34114, 7, 134221824, 1, 100000, 20000, 17, -1, -1, 1, 1, 1,
   336, 4104, 0, 3200, 1, 120, 4, 2,
 'A caster stave that keeps pace with its bearer.', 12340),
(990255, 2, 10, 'Everkeen Warstaff', 33015, 7, 134221824, 1, 100000, 20000, 17, -1, -1, 1, 1, 1,
   1, 1032, 0, 3400, 1, 130, 4, 2,
 'A staff swung, not channelled. Strength and stamina.', 12340),
(990256, 2, 2, 'Everkeen Longbow', 31338, 7, 134221824, 1, 65000, 13000, 15, -1, -1, 1, 1, 1,
   2, 8208, 0, 2800, 1, 90, 2, 0,
 'Agility and attack power at range, forever.', 12340),
(990257, 2, 3, 'Everkeen Handcannon', 31876, 7, 134221824, 1, 65000, 13000, 26, -1, -1, 1, 1, 1,
   5, 8208, 0, 2900, 1, 90, 1, 0,
 'A firearm that answers to intellect. Only a Hero would think to try.', 12340),

-- ---------------------------------------------------------------------------
-- Armor -- deliberately "wrong" armor class for the stats it carries
-- ---------------------------------------------------------------------------
(990258, 4, 4, 'Timeless Plate Chestguard', 31083, 7, 134221824, 1, 37500, 7500, 5, -1, -1, 1, 1, 1,
   336, 8388616, 0, 0, 1, 165, 6, 0,
 'Full plate that channels spellpower. Cast from inside a fortress.', 12340),
(990259, 4, 4, 'Timeless Plate Pauldrons', 26662, 7, 134221824, 1, 22500, 4500, 3, -1, -1, 1, 1, 1,
   336, 257, 0, 0, 1, 120, 6, 0,
 'Spellcaster shoulders, in the heaviest armor there is.', 12340),
(990260, 4, 3, 'Timeless Mail Hauberk', 25222, 7, 134221824, 1, 37500, 7500, 5, -1, -1, 1, 1, 1,
   1, 4194312, 0, 0, 1, 150, 5, 0,
 'Mail cut for raw strength.', 12340),
(990261, 4, 3, 'Timeless Mail Spaulders', 32128, 7, 134221824, 1, 22500, 4500, 3, -1, -1, 1, 1, 1,
   1, 129, 0, 0, 1, 110, 5, 0,
 'Strength and stamina, on a mail frame.', 12340),
(990262, 4, 2, 'Timeless Leather Cuirass', 36015, 7, 134221824, 1, 37500, 7500, 5, -1, -1, 1, 1, 1,
   333, 2097160, 0, 0, 1, 130, 8, 0,
 'Light leather for a heavy hitter.', 12340),
(990263, 4, 2, 'Timeless Leather Mantle', 31038, 7, 134221824, 1, 22500, 4500, 3, -1, -1, 1, 1, 1,
   333, 65, 0, 0, 1, 95, 8, 0,
 'Strength on the shoulders of a scout.', 12340),
(990264, 4, 1, 'Timeless Cloth Robe', 30824, 7, 134221824, 1, 37500, 7500, 20, -1, -1, 1, 1, 1,
   331, 1048584, 0, 0, 1, 110, 7, 0,
 'A robe carrying attack power and agility. Nobody else would dare.', 12340),
(990265, 4, 1, 'Timeless Cloth Mantle', 36038, 7, 134221824, 1, 22500, 4500, 3, -1, -1, 1, 1, 1,
   331, 33, 0, 0, 1, 80, 7, 0,
 'Silk shoulders for a knife fighter.', 12340),
(990266, 4, 3, 'Timeless Mail Vest of Insight', 31641, 7, 134221824, 1, 37500, 7500, 5, -1, -1, 1, 1, 1,
   334, 4194312, 0, 0, 1, 150, 5, 0,
 'Mail that favours intellect and spirit over brawn.', 12340),
(990267, 4, 2, 'Timeless Leather Vest of Ruin', 14496, 7, 134221824, 1, 37500, 7500, 5, -1, -1, 1, 1, 1,
   336, 2097160, 0, 0, 1, 130, 8, 0,
 'Spellpower leather -- mobility without the silk.', 12340),
(990268, 4, 1, 'Timeless Greatcloak', 31978, 7, 134221824, 1, 22500, 4500, 16, -1, -1, 1, 1, 1,
   334, 524296, 0, 0, 1, 0, 7, 0,
 'A cloak woven for spellcasters, and it grows with them.', 12340),
(990269, 4, 1, 'Timeless Warcloak', 24159, 7, 134221824, 1, 22500, 4500, 16, -1, -1, 1, 1, 1,
   331, 524296, 0, 0, 1, 0, 7, 0,
 'A cloak for the ones who close the distance.', 12340),

-- ---------------------------------------------------------------------------
-- Trinkets -- single-stat scaling, one for each build direction
-- ---------------------------------------------------------------------------
(990270, 4, 0, 'Everflowing Spell Focus', 34149, 7, 134221824, 1, 24000, 4800, 12, -1, -1, 1, 1, 1,
   271, 2, 0, 0, 1, 0, 0, 0,
 'Pure spellpower, scaled to whoever holds it.', 12340),
(990271, 4, 0, 'Everquick Chronometer', 39186, 7, 134221824, 1, 24000, 4800, 12, -1, -1, 1, 1, 1,
   251, 2, 0, 0, 1, 0, 0, 0,
 'Pure haste. Everything you do, sooner.', 12340),
(990272, 4, 0, 'Everseeing Eye', 31029, 7, 134221824, 1, 24000, 4800, 12, -1, -1, 1, 1, 1,
   104, 2, 0, 0, 1, 0, 0, 0,
 'Pure critical strike, whatever it is you are striking with.', 12340);

-- Shelving lives in cw_world_vendor_lists.sql, which reads this file back and
-- lays every item out by category and level bracket across several vendor
-- lists. Adding npc_vendor rows here as well would put duplicates on the shop.