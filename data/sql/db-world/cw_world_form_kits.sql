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
(1515, 2641, 1, 'default: Tame Beast -> Dismiss Pet'),
-- Mend Pet and Eyes of the Beast are pet upkeep in the same way Call Pet is,
-- so they ride with Tame Beast too rather than sitting in the deck as cards
-- that do nothing. cw_world_base.sql takes them out of the pool.
(1515, 136,  1, 'default: Tame Beast -> Mend Pet'),
(1515, 1002, 1, 'default: Tame Beast -> Eyes of the Beast'),
-- Kill Command stays a card of its own -- it is a damage cooldown, not upkeep
-- -- but it cannot be cast without a pet, so it brings the pet with it. Listed
-- one by one because a kit does not chain: granting Tame Beast this way does
-- not fire Tame Beast's own kit.
(34026, 1515, 1, 'default: Kill Command -> Tame Beast'),
(34026, 883,  1, 'default: Kill Command -> Call Pet'),
(34026, 982,  1, 'default: Kill Command -> Revive Pet'),
(34026, 6991, 1, 'default: Kill Command -> Feed Pet'),
(34026, 2641, 1, 'default: Kill Command -> Dismiss Pet'),
(34026, 136,  1, 'default: Kill Command -> Mend Pet'),
-- Warlock: a Soul Shard is not vendor goods. Drain Soul is the only thing in
-- the game that makes one, so every spell that spends a shard hands it over.
-- Without this a Hero can own Summon Voidwalker and have no way to cast it.
(6201,  1120, 1, 'default: Create Healthstone -> Drain Soul'),
(693,   1120, 1, 'default: Create Soulstone -> Drain Soul'),
(6366,  1120, 1, 'default: Create Firestone -> Drain Soul'),
(2362,  1120, 1, 'default: Create Spellstone -> Drain Soul'),
(697,   1120, 1, 'default: Summon Voidwalker -> Drain Soul'),
(712,   1120, 1, 'default: Summon Succubus -> Drain Soul'),
(691,   1120, 1, 'default: Summon Felhunter -> Drain Soul'),
(698,   1120, 1, 'default: Ritual of Summoning -> Drain Soul'),
(29893, 1120, 1, 'default: Ritual of Souls -> Drain Soul'),
(1098,  1120, 1, 'default: Enslave Demon -> Drain Soul'),
(17877, 1120, 1, 'default: Shadowburn -> Drain Soul'),
(6353,  1120, 1, 'default: Soul Fire -> Drain Soul'),
(29858, 1120, 1, 'default: Soulshatter -> Drain Soul'),
-- Warlock: both of these are cast on the demon, and the Imp is the one summon
-- that costs no shard, so it is what they bring.
(755,   688,  1, 'default: Health Funnel -> Summon Imp'),
(18220, 688,  1, 'default: Dark Pact -> Summon Imp'),
-- Warlock: the teleport goes to a circle that only the summon can place. Two
-- halves of one ability, learned at the same level.
(48020, 48018, 1, 'default: Demonic Circle: Teleport -> Demonic Circle: Summon'),
-- Talents are matched the same way, on their rank spells. Shadowburn and Dark
-- Pact need no rows of their own: their talent's rank spell IS the first rank
-- of the ability line above, so the pairs already listed cover both routes.
(30146, 1120, 1, 'default: Summon Felguard -> Drain Soul'),
(19028, 688,  1, 'default: Soul Link -> Summon Imp'),
(47193, 688,  1, 'default: Demonic Empowerment -> Summon Imp'),
(63560, 46584, 1, 'default: Ghoul Frenzy -> Raise Dead'),
-- Both of these are commands given to a pet, so they bring one, listed out in
-- full for the same reason Kill Command is.
(19574, 1515, 1, 'default: Bestial Wrath -> Tame Beast'),
(19574, 883,  1, 'default: Bestial Wrath -> Call Pet'),
(19574, 982,  1, 'default: Bestial Wrath -> Revive Pet'),
(19574, 6991, 1, 'default: Bestial Wrath -> Feed Pet'),
(19574, 2641, 1, 'default: Bestial Wrath -> Dismiss Pet'),
(19574, 136,  1, 'default: Bestial Wrath -> Mend Pet'),
(19577, 1515, 1, 'default: Intimidation -> Tame Beast'),
(19577, 883,  1, 'default: Intimidation -> Call Pet'),
(19577, 982,  1, 'default: Intimidation -> Revive Pet'),
(19577, 6991, 1, 'default: Intimidation -> Feed Pet'),
(19577, 2641, 1, 'default: Intimidation -> Dismiss Pet'),
(19577, 136,  1, 'default: Intimidation -> Mend Pet'),
-- Master's Call frees the pet from a snare, so it needs one. It reached the
-- library late: its SkillLineAbility row carries no class mask, which is how
-- Blizzard wrote every ability after vanilla, and the pool used to skip those.
(53271, 1515, 1, 'default: Master''s Call -> Tame Beast'),
(53271, 883,  1, 'default: Master''s Call -> Call Pet'),
(53271, 982,  1, 'default: Master''s Call -> Revive Pet'),
(53271, 6991, 1, 'default: Master''s Call -> Feed Pet'),
(53271, 2641, 1, 'default: Master''s Call -> Dismiss Pet'),
(53271, 136,  1, 'default: Master''s Call -> Mend Pet'),
-- Three requirements that live in the CORE's spell scripts rather than in the
-- spell's own data, so nothing reading Spell.dbc can see them. Savage Roar and
-- Survival Instincts both read Stances 0 and are refused outside a feral form
-- by spell_dru_savage_roar and spell_dru_survival_instincts; Death Pact reads
-- as an ordinary heal and is refused with no ghoul by spell_dk_death_pact.
(52610, 768,  1, 'default: Savage Roar -> Cat Form'),
(61336, 768,  1, 'default: Survival Instincts -> Cat Form'),
(48743, 46584, 1, 'default: Death Pact -> Raise Dead');
