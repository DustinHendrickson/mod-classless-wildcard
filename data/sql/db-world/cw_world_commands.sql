-- mod-classless-wildcard: help text for the .classless and .wildcard chat
-- commands. The core prints a command's help when it is typed with missing or
-- wrong arguments, and .help lists it.

DELETE FROM `command` WHERE `name` IN ('classless', 'wildcard') OR `name` LIKE 'classless %' OR `name` LIKE 'wildcard %';
INSERT INTO `command` (`name`, `security`, `help`) VALUES
('classless', 0, 'Syntax: .classless $subcommand\r\nHero Advancement commands. Type .classless status to start, or .help classless for the list.'),
('classless status', 0, 'Syntax: .classless status\r\nShows your path, abilities and talents, essence, reroll charges and reroll cooldowns.'),
('classless mode', 0, 'Syntax: .classless mode classless|wildcard\r\nChooses your path. Only before your path locks.'),
('classless learn', 0, 'Syntax: .classless learn $spellId\r\nBuys an ability with Ability Essence. Classless path only.'),
('classless unlearn', 0, 'Syntax: .classless unlearn $spellId\r\nUnlearns an ability and refunds its Ability Essence. Classless path only.'),
('classless talent', 0, 'Syntax: .classless talent $talentId\r\nBuys the next rank of a talent with Talent Essence. Classless path only.'),
('classless respec', 0, 'Syntax: .classless respec\r\nUnlearns every ability and talent and refunds all essence. Free. Classless path only.'),
('classless stats', 0, 'Syntax: .classless stats\r\nShows your primary stat allocation and unspent points.'),
('classless stat', 0, 'Syntax: .classless stat str|agi|sta|int|spi $points\r\nPuts points into a primary stat. Reallocating is free.'),
('classless bar', 0, 'Syntax: .classless bar mana|rage|energy|default\r\nChooses which resource the main power bar shows.'),
('classless archetypes', 0, 'Syntax: .classless archetypes\r\nLists the archetypes and their IDs.'),
('classless archetype', 0, 'Syntax: .classless archetype $id\r\nFollows an archetype, replacing your build. 0 stops following. Classless path only.'),
('classless path', 0, 'Syntax: .classless path classless|wildcard confirm\r\nWipes your build and starts a path at your current level, for gold. Without confirm, shows what it will do.'),
('classless rebirth', 0, 'Syntax: .classless rebirth classless|wildcard [$abilityId ...] confirm\r\nAt the level cap: back to level 1 with a permanent Rebirth rank, carrying the listed heirloom abilities. Without confirm, shows what it will do.'),
('classless challenges', 0, 'Syntax: .classless challenges\r\nLists the challenge runs with their IDs, lives and rewards.'),
('classless run', 0, 'Syntax: .classless run $id classless|wildcard [$abilityId ...] confirm\r\nStarts a challenge run. At the level cap it is a Rebirth and needs confirm.'),
('wildcard', 0, 'Syntax: .wildcard $subcommand\r\nWildcard path commands. Type .help wildcard for the list.'),
('wildcard status', 0, 'Syntax: .wildcard status\r\nShows your path, abilities and talents, reroll charges, synergy chance and reroll cooldowns.'),
('wildcard reroll', 0, 'Syntax: .wildcard reroll $spellId\r\nRerolls an ability you own. Free below the free-reroll level, then a reroll charge or a Reroll Scroll.'),
('wildcard rerolltalent', 0, 'Syntax: .wildcard rerolltalent $talentId [$scrolls]\r\nRerolls a talent you own. Each staked scroll adds a chance to keep the talent and raise its rank instead.'),
('wildcard lock', 0, 'Syntax: .wildcard lock $spellId\r\nPadlocks or unlocks an ability in your Starting Hand.');
