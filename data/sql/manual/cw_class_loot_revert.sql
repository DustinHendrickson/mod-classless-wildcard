-- Undo cw_world_class_loot.sql: put the armour-class gate back on the Sons of
-- Hodir satchels, and each block back in a group of its own.
--
-- Apply to the world database, then restart the worldserver.

UPDATE `item_loot_template` SET `GroupId` = 1 WHERE `Entry` BETWEEN 51999 AND 52005 AND `Reference` IN (10036, 10039, 10042, 10046, 10050, 10054, 10058);
UPDATE `item_loot_template` SET `GroupId` = 2 WHERE `Entry` BETWEEN 51999 AND 52005 AND `Reference` IN (10037, 10040, 10043, 10047, 10051, 10055, 10059);
UPDATE `item_loot_template` SET `GroupId` = 3 WHERE `Entry` BETWEEN 51999 AND 52005 AND `Reference` IN (10038, 10041, 10044, 10048, 10052, 10056, 10060);
UPDATE `item_loot_template` SET `GroupId` = 4 WHERE `Entry` BETWEEN 51999 AND 52005 AND `Reference` IN (10045, 10049, 10053, 10057, 10061);

DELETE FROM `conditions`
 WHERE `SourceTypeOrReferenceId` = 10
   AND `ConditionTypeOrReference` = 15
   AND `SourceGroup` BETWEEN 10036 AND 10061;
INSERT INTO `conditions` (`SourceTypeOrReferenceId`, `SourceGroup`, `SourceEntry`, `SourceId`, `ElseGroup`, `ConditionTypeOrReference`, `ConditionTarget`, `ConditionValue1`, `ConditionValue2`, `ConditionValue3`, `NegativeCondition`, `ErrorType`, `ErrorTextId`, `ScriptName`, `Comment`) VALUES
(10,10036,51968,0,0,15,0,400,0,0,0,0,0,'','SOHG: Enumerated Wrap only for clothusers'),
(10,10036,51994,0,0,15,0,400,0,0,0,0,0,'','SOHG: Tumultuous Cloak only for clothusers'),
(10,10037,51964,0,0,15,0,1100,0,0,0,0,0,'','SOHG: Vigorous Belt only for leatherusers'),
(10,10037,51994,0,0,15,0,1100,0,0,0,0,0,'','SOHG: Tumultuous Cloak only for leatherusers'),
(10,10038,51978,0,0,15,0,3,0,0,0,0,0,'','SOHG: Earthbound Girdle only for mail users'),
(10,10038,51994,0,0,15,0,3,0,0,0,0,0,'','SOHG: Tumultuous Cloak only for mail users'),
(10,10039,51973,0,0,15,0,400,0,0,0,0,0,'','SOHG: Enumerated Handwraps only for clothusers'),
(10,10039,51996,0,0,15,0,400,0,0,0,0,0,'','SOHG: Tumultuous Necklace only for clothusers'),
(10,10040,51965,0,0,15,0,1100,0,0,0,0,0,'','SOHG: Vigorous Handguards only for leatherusers'),
(10,10040,51996,0,0,15,0,1100,0,0,0,0,0,'','SOHG: Tumultuous Necklace only for leatherusers'),
(10,10041,51980,0,0,15,0,3,0,0,0,0,0,'','SOHG: Earthbound Handgrips only for mail users'),
(10,10041,51996,0,0,15,0,3,0,0,0,0,0,'','SOHG: Tumultuous Necklace only for Mail users'),
(10,10042,51974,0,0,15,0,400,0,0,0,0,0,'','SOHG: Enumerated Shoulderpads only for clothusers'),
(10,10042,51992,0,0,15,0,400,0,0,0,0,0,'','SOHG: Tumultuous Ring only for clothusers'),
(10,10043,51966,0,0,15,0,1032,0,0,0,0,0,'','SOHG: Vigorous Spaulders only for leatherusers'),
(10,10043,51992,0,0,15,0,1032,0,0,0,0,0,'','SOHG: Tumultuous ring only for leatherusers'),
(10,10044,51976,0,0,15,0,68,0,0,0,0,0,'','SOHG: Earthbound Shoulderguards only for mail users'),
(10,10044,51992,0,0,15,0,68,0,0,0,0,0,'','SOHG: Tumultuous Ring only for mail users'),
(10,10045,51984,0,0,15,0,35,0,0,0,0,0,'','SOHG: Stalwart Shoulderpads only for plate users'),
(10,10045,51992,0,0,15,0,35,0,0,0,0,0,'','SOHG: Tumultuous Ring only for plate users'),
(10,10046,51967,0,0,15,0,400,0,0,0,0,0,'','SOHG: Enumerated Sandals only for clothusers'),
(10,10046,51972,0,0,15,0,400,0,0,0,0,0,'','SOHG: Enumerated Bracers only for clothusers'),
(10,10047,51962,0,0,15,0,1032,0,0,0,0,0,'','SOHG: Vigorous Bracers only for leatherusers'),
(10,10047,51963,0,0,15,0,1032,0,0,0,0,0,'','SOHG: Vigorous Stompers only for leatherusers'),
(10,10048,51981,0,0,15,0,68,0,0,0,0,0,'','SOHG: Earthbound Wristguards only for mail users'),
(10,10048,51982,0,0,15,0,68,0,0,0,0,0,'','SOHG: Earthbound Boots only for mail users'),
(10,10049,51989,0,0,15,0,35,0,0,0,0,0,'','SOHG: Stalwart Bands only for plate users'),
(10,10049,51990,0,0,15,0,35,0,0,0,0,0,'','SOHG: Stalwart Treads only for plate users'),
(10,10050,51971,0,0,15,0,400,0,0,0,0,0,'','SOHG: Enumerated Belt only for clothusers'),
(10,10050,51993,0,0,15,0,400,0,0,0,0,0,'','SOHG: Turbulent Cloak only for clothusers'),
(10,10051,51959,0,0,15,0,1032,0,0,0,0,0,'','SOHG: Vigorous Belt only for leatherusers'),
(10,10051,51993,0,0,15,0,1032,0,0,0,0,0,'','SOHG: Turbulent Cloak only for leatherusers'),
(10,10052,51977,0,0,15,0,68,0,0,0,0,0,'','SOHG: Earthbound Girdle only for mail users'),
(10,10052,51993,0,0,15,0,68,0,0,0,0,0,'','SOHG: Turbulent Cloak only for mail users'),
(10,10053,51985,0,0,15,0,35,0,0,0,0,0,'','SOHG: Stalwart Belt only for plate users'),
(10,10053,51993,0,0,15,0,35,0,0,0,0,0,'','SOHG: Turbulent Cloak only for plate users'),
(10,10054,51970,0,0,15,0,400,0,0,0,0,0,'','SOHG: Enumerated Gloves only for clothusers'),
(10,10054,51995,0,0,15,0,400,0,0,0,0,0,'','SOHG: Turbulent Necklace only for clothusers'),
(10,10055,51960,0,0,15,0,1032,0,0,0,0,0,'','SOHG: Vigorous Gloves only for leatherusers'),
(10,10055,51995,0,0,15,0,1032,0,0,0,0,0,'','SOHG: Turbulent Necklace only for leatherusers'),
(10,10056,51979,0,0,15,0,68,0,0,0,0,0,'','SOHG: Earthbound Grips only for mail users'),
(10,10056,51995,0,0,15,0,68,0,0,0,0,0,'','SOHG: Turbulent Necklace only for mail users'),
(10,10057,51987,0,0,15,0,35,0,0,0,0,0,'','SOHG: Stalwart Grips only for plate users'),
(10,10057,51995,0,0,15,0,35,0,0,0,0,0,'','SOHG: Turbulent Necklace only for plate users'),
(10,10058,51961,0,0,15,0,1032,0,0,0,0,0,'','SOHG: Vigorous Shoulderguards only for leatherusers'),
(10,10058,51991,0,0,15,0,1032,0,0,0,0,0,'','SOHG: Turbulent Signet only for leatherusers'),
(10,10059,51969,0,0,15,0,400,0,0,0,0,0,'','SOHG: Enumerated Shoulders only for clothusers'),
(10,10059,51991,0,0,15,0,400,0,0,0,0,0,'','SOHG: Turbulent Signet only for clothusers'),
(10,10060,51975,0,0,15,0,68,0,0,0,0,0,'','SOHG: Earthbound Shoulders only for mail users'),
(10,10060,51991,0,0,15,0,68,0,0,0,0,0,'','SOHG: Turbulent Signet only for Mail users'),
(10,10061,51983,0,0,15,0,35,0,0,0,0,0,'','SOHG: Stalwart Shoulderguards only for plate users'),
(10,10061,51991,0,0,15,0,35,0,0,0,0,0,'','SOHG: Turbulent Signet only for plate users');
