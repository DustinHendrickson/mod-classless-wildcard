-- mod-classless-wildcard: CHARACTERS DB uninstall.
-- NOT auto-applied — run by hand, with the worldserver STOPPED, only when
-- removing the module. See "Uninstall / revert" in README.md.

-- Remove proficiency spells the module taught (weapon/armor/dual wield).
-- Cross-class ability/talent spells granted by the module do NOT need manual
-- cleanup: once the custom skillraceclassinfo_dbc rows are gone (world
-- uninstall), the core's login validation deletes every spell and skill that
-- is invalid for the character's real class, automatically, at next login.
DELETE FROM `character_spell` WHERE `spell` IN
(9078,9077,8737,750,9116,201,202,196,197,198,199,200,227,1180,15590,264,266,5011,2567,5009,5019,674);

-- module state tables
DROP TABLE IF EXISTS `cw_char_state`;
DROP TABLE IF EXISTS `cw_char_abilities`;
DROP TABLE IF EXISTS `cw_char_talents`;
DROP TABLE IF EXISTS `cw_char_cards`;
DROP TABLE IF EXISTS `cw_char_bans`;

-- module DB-updater bookkeeping, so reinstalling later re-applies cleanly
DELETE FROM `updates` WHERE `name` LIKE 'cw_%';
