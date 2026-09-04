-- mod-classless-wildcard: starter kits for forms, stances and paired abilities
--
-- A form or a stance does nothing on its own. Under the class system nobody
-- ever holds one in isolation -- a druid who can turn into a bear has always
-- had Maul to swing in it, and a warrior in Defensive Stance has always had
-- Taunt to justify standing there. Draw one out of the Wildcard deck with
-- nothing to go with it and you have shapeshifted into a creature that cannot
-- attack. The same is true of abilities a class always learned as a set: Tame
-- Beast is useless without Call Pet, Revive Pet and Feed Pet.
--
-- So gaining the ability hands over the basic kit that goes with it, free and
-- immediately. The pairs are data, not code: both columns are plain spell ids
-- and neither has to be a form, so a realm can pair anything with anything --
-- add a row and restart the worldserver.
--
-- A granted spell is a free extra, not one of the Hero's rolls or purchases:
-- it is not a card in the starting hand, it cannot be rerolled or unlearned on
-- its own, and it leaves when the Hero no longer owns anything that needs it.
--
-- Turn the whole feature off with ClasslessWildcard.FormStarterKits = 0, or
-- drop individual pairs by setting `enabled` = 0.
--
-- Every spell id below was verified against the client's Spell.dbc.

CREATE TABLE IF NOT EXISTS `cw_form_kits` (
  `form_spell` INT UNSIGNED NOT NULL COMMENT 'the form or stance spell; any rank of the line matches',
  `granted_spell` INT UNSIGNED NOT NULL COMMENT 'spell handed over free when that form is gained',
  `enabled` TINYINT UNSIGNED NOT NULL DEFAULT 1,
  `comment` VARCHAR(128) NOT NULL DEFAULT '',
  PRIMARY KEY (`form_spell`, `granted_spell`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Classless form/stance starter kits';

-- Scoped to the rows this file ships (tagged 'default:'), so re-applying picks
-- up corrections without touching pairs a realm added itself.
DELETE FROM `cw_form_kits` WHERE `comment` LIKE 'default:%';
INSERT INTO `cw_form_kits` (`form_spell`, `granted_spell`, `enabled`, `comment`) VALUES
-- Druid: Cat Form -- an opener and something to hit with
(768,  1082, 1, 'default: Cat Form -> Claw'),
(768,  5215, 1, 'default: Cat Form -> Prowl'),
-- Druid: Bear Form -- Dire Bear is listed too, in case a core keeps it as its
-- own spell line rather than a higher rank of Bear Form
(5487, 6807, 1, 'default: Bear Form -> Maul'),
(5487, 99,   1, 'default: Bear Form -> Demoralizing Roar'),
(9634, 6807, 1, 'default: Dire Bear Form -> Maul'),
(9634, 99,   1, 'default: Dire Bear Form -> Demoralizing Roar'),
-- Warrior stances -- each gets the ability that gives it a purpose
(2457, 100,  1, 'default: Battle Stance -> Charge'),
(71,   355,  1, 'default: Defensive Stance -> Taunt'),
(2458, 6552, 1, 'default: Berserker Stance -> Pummel'),
-- Hunter pet handling. Tame Beast is the only way to get a pet, and every
-- spell for keeping one is worthless without it, so the four arrive together.
-- cw_world_base.sql disables them in `cw_ability_override`, so they are out of
-- the roll pool and Tame Beast is the single card that carries the whole kit.
(1515, 883,  1, 'default: Tame Beast -> Call Pet'),
(1515, 982,  1, 'default: Tame Beast -> Revive Pet'),
(1515, 6991, 1, 'default: Tame Beast -> Feed Pet'),
(1515, 2641, 1, 'default: Tame Beast -> Dismiss Pet');
