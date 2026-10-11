-- mod-classless-wildcard: the build a character follows when it is its own
-- (a custom archetype) rather than one of the starter builds in cw_archetypes.
-- cw_char_state.archetype holds 4294967295 while this row is followed.
-- Saved builds a player keeps but does not follow live in the addon, not here.

CREATE TABLE IF NOT EXISTS `cw_char_custom_archetype` (
    `guid`      INT UNSIGNED NOT NULL COMMENT 'characters.guid',
    `name`      VARCHAR(64)  NOT NULL DEFAULT '' COMMENT 'the build''s name, as the player gave it',
    `abilities` TEXT         NOT NULL COMMENT 'first-rank spell ids in buy order, comma separated',
    `talents`   TEXT         NOT NULL COMMENT 'talentId:rank in buy order, comma separated',
    PRIMARY KEY (`guid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='mod-classless-wildcard: the custom archetype each character follows';
