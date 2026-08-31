-- mod-classless-wildcard: starter archetypes (onboarding)
-- Ready-made builds that spend a new Hero's starting Ability Essence, like
-- Ascension's role-focused archetypes. abilities = first-rank spell ids (CSV),
-- talents = "talentId:rank" CSV (starting characters have no TE, so these are
-- mostly useful for admin-made higher-level archetypes).

CREATE TABLE IF NOT EXISTS `cw_archetypes` (
  `id` INT UNSIGNED NOT NULL,
  `name` VARCHAR(64) NOT NULL,
  `description` VARCHAR(255) NOT NULL DEFAULT '',
  `abilities` TEXT,
  `talents` TEXT,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Classless starter archetypes';

DELETE FROM `cw_archetypes`;
INSERT INTO `cw_archetypes` (`id`, `name`, `description`, `abilities`, `talents`) VALUES
(1, 'Blade Dancer',
 'Fast melee striker: rogue strikes backed by warrior mobility.',
 '1752,2098,100,772', ''),
(2, 'Battle Mage',
 'Armored caster: fireballs up close, sword in hand.',
 '133,168,100,772', ''),
(3, 'Ranger of the Light',
 'Hybrid archer-paladin: shoot from range, heal and bless in melee.',
 '3044,635,465,20154', ''),
(4, 'Shadow Mender',
 'Priest hybrid: shield and mend allies, wither foes with shadow.',
 '589,585,17,2061', ''),
(5, 'Stealthy Healer',
 'Druidic infiltrator: slip through shadows, restore life from hiding.',
 '1784,5185,774,8921', ''),
(6, 'Storm Warrior',
 'Shamanistic bruiser: lightning from afar, heroic strikes up close.',
 '403,331,78,2687', '');
