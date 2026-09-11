-- mod-classless-wildcard: two stock spells whose scripts ask which power bar
-- the player is showing, and hand back nothing when it is the wrong one.
--
-- A Hero has mana, rage and energy at once; the client draws one of them. Most
-- of the core asks that question through Player::HasActivePowerType, which this
-- module answers, but these two ask getPowerType() directly:
--
--   22842 Frenzied Regeneration  `if (getPowerType() != POWER_RAGE) return;`
--                                -- no healing at all, however full the rage is
--   20186 Judgement of Wisdom    `CheckProc: getPowerType() == POWER_MANA`
--                                -- no mana, though the Hero pays mana costs
--   61013 Warlock Pet Scaling 05 `else if (getPowerType() == POWER_MANA)`
--   61017 Hunter Pet Scaling 04  -- how much of the owner's hit and expertise
--                                the pet inherits moved every time the owner
--                                switched which bar was on screen
--
-- 5019 Shoot is the other shape: the core gives a wand shot the WAND's damage
-- school, but gates it on a raw class mask with no hook behind it, so a Hero
-- fired physically. Nothing of the core's is taken over there -- 5019 has no
-- script of its own -- this one is simply added.
--
-- The module's versions are the core's own implementations with that one
-- question answered from the pool instead of the bar, and they keep the core's
-- exact behaviour for anyone the module leaves alone (bots, exempt accounts).
--
-- The binding is TAKEN OVER rather than added to. spell_script_names is a
-- multimap and two scripts can share a spell, but Aura::CallScriptCheckProcHandlers
-- ANDs every script's CheckProc -- so leaving the core's script on 20186 would
-- let its `false` veto the proc whatever this module answered.
--
-- Expected side effect: with the core's rows gone, its scripts are compiled in
-- but bound to nothing, and ScriptMgr says so once at startup --
--
--   Script named 'spell_dru_frenzied_regeneration' is not assigned in the database.
--   Script named 'spell_pal_judgement_of_wisdom_mana' is not assigned in the database.
--   Script named 'spell_pet_hit_expertise_scalling' is not assigned in the database.
--
-- red, because it is LOG_ERROR("sql.sql"), and harmless. Seeing those two lines
-- is how you know this file applied.
--
-- Reversible: data/sql/uninstall/cw_uninstall_world.sql puts the core's rows back.

DELETE FROM `spell_script_names` WHERE `spell_id` = 22842 AND `ScriptName` = 'spell_dru_frenzied_regeneration';
DELETE FROM `spell_script_names` WHERE `spell_id` = 20186 AND `ScriptName` = 'spell_pal_judgement_of_wisdom_mana';

DELETE FROM `spell_script_names` WHERE `spell_id` IN (61013, 61017) AND `ScriptName` = 'spell_pet_hit_expertise_scalling';

DELETE FROM `spell_script_names` WHERE `ScriptName` IN
    ('spell_cw_frenzied_regeneration', 'spell_cw_judgement_of_wisdom',
     'spell_cw_pet_hit_expertise_scaling', 'spell_cw_wand_shoot_school');
INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`) VALUES
(22842, 'spell_cw_frenzied_regeneration'),
(20186, 'spell_cw_judgement_of_wisdom'),
(61013, 'spell_cw_pet_hit_expertise_scaling'),
(61017, 'spell_cw_pet_hit_expertise_scaling'),
(5019,  'spell_cw_wand_shoot_school');
