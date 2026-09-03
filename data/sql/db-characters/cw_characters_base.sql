-- mod-classless-wildcard: per-character persistence

CREATE TABLE IF NOT EXISTS `cw_char_state` (
  `guid` INT UNSIGNED NOT NULL,
  `mode` TINYINT UNSIGNED NOT NULL DEFAULT 255,
  `ability_essence` INT UNSIGNED NOT NULL DEFAULT 0,
  `talent_essence` INT UNSIGNED NOT NULL DEFAULT 0,
  `pity` INT UNSIGNED NOT NULL DEFAULT 0,
  `rerolls` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'earned reroll charges, spent on abilities or talents',
  `last_level` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `stat_str` INT UNSIGNED NOT NULL DEFAULT 0,
  `stat_agi` INT UNSIGNED NOT NULL DEFAULT 0,
  `stat_sta` INT UNSIGNED NOT NULL DEFAULT 0,
  `stat_int` INT UNSIGNED NOT NULL DEFAULT 0,
  `stat_spi` INT UNSIGNED NOT NULL DEFAULT 0,
  `display_power` TINYINT UNSIGNED NOT NULL DEFAULT 255 COMMENT '0 mana, 1 rage, 3 energy, 255 chassis default',
  `archetype` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'cw_archetypes.id the Hero follows, 0 none',
  PRIMARY KEY (`guid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Classless/Wildcard character state';

-- (databases created by an older version are upgraded to this shape by
--  cw_characters_rerolls.sql, which runs after this file)

CREATE TABLE IF NOT EXISTS `cw_char_abilities` (
  `guid` INT UNSIGNED NOT NULL,
  `first_spell` INT UNSIGNED NOT NULL,
  `source` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0 picked, 1 rolled, 2 granted by an ability talent',
  `locked` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (`guid`, `first_spell`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Owned classless ability lines';

CREATE TABLE IF NOT EXISTS `cw_char_talents` (
  `guid` INT UNSIGNED NOT NULL,
  `talent_id` INT UNSIGNED NOT NULL,
  `talent_rank` TINYINT UNSIGNED NOT NULL DEFAULT 1,
  PRIMARY KEY (`guid`, `talent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Owned classless talents';

CREATE TABLE IF NOT EXISTS `cw_char_bans` (
  `guid` INT UNSIGNED NOT NULL,
  `is_talent` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `entry` INT UNSIGNED NOT NULL,
  `rolls_left` INT NOT NULL DEFAULT 0,
  PRIMARY KEY (`guid`, `is_talent`, `entry`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Wildcard bad-luck-protection roll bans';
