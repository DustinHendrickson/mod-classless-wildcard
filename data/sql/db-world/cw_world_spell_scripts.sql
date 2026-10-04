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

-- Four Death Knight TALENTS a Hero can buy and could never make work. Their
-- core scripts compare getClass() to CLASS_DEATH_KNIGHT outright and return
-- before touching a rune, so Blade Barrier never procs and Blood of the North,
-- Reaping and Death Rune Mastery never convert one. The module's versions ask
-- the same question through IsClass(..., CLASS_CONTEXT_ABILITY), which is what
-- allocates the Hero's runes in the first place.
--
-- The ids are negative in spell_script_names: that means the spell and every
-- rank below it, which is how one row covers a five-rank talent.
DELETE FROM `spell_script_names` WHERE `spell_id` = -49182 AND `ScriptName` = 'spell_dk_blade_barrier';
DELETE FROM `spell_script_names` WHERE `spell_id` IN (-49208, -49467, -54639) AND `ScriptName` = 'spell_dk_death_rune';

-- Item and set procs that pick a reward by class with getClass(), so a Hero
-- always took the Paladin's: Eye of Gruul and Soul Preserver cheapened Paladin
-- heals only, Blessing of Faith the same, Flask of the North never rolled
-- attack power, and the T3 6-piece Holy and Totemic Power gave a Hero target
-- mp5 every time. The module's versions treat a Hero as every class and leave
-- everyone else exactly as the core has them.
--
-- 60510 has been bound to both spell_item_healing_trance and
-- spell_item_soul_preserver across core updates; both come off.
DELETE FROM `spell_script_names` WHERE `spell_id` IN (37705, 60510)
    AND `ScriptName` IN ('spell_item_healing_trance', 'spell_item_soul_preserver');
DELETE FROM `spell_script_names` WHERE `spell_id` = 37877 AND `ScriptName` = 'spell_pal_blessing_of_faith';
DELETE FROM `spell_script_names` WHERE `spell_id` = 67019 AND `ScriptName` = 'spell_item_flask_of_the_north';
DELETE FROM `spell_script_names` WHERE `spell_id` = 28789 AND `ScriptName` = 'spell_pal_t3_6p_bonus';
DELETE FROM `spell_script_names` WHERE `spell_id` = 28823 AND `ScriptName` = 'spell_sha_t3_6p_bonus';

DELETE FROM `spell_script_names` WHERE `ScriptName` IN
    ('spell_cw_frenzied_regeneration', 'spell_cw_judgement_of_wisdom',
     'spell_cw_pet_hit_expertise_scaling',
     'spell_cw_dk_blade_barrier', 'spell_cw_dk_death_rune',
     'spell_cw_healing_trance', 'spell_cw_blessing_of_faith',
     'spell_cw_flask_of_the_north', 'spell_cw_t3_6p_bonus');
INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`) VALUES
(37705, 'spell_cw_healing_trance'),
(60510, 'spell_cw_healing_trance'),
(37877, 'spell_cw_blessing_of_faith'),
(67019, 'spell_cw_flask_of_the_north'),
(28789, 'spell_cw_t3_6p_bonus'),
(28823, 'spell_cw_t3_6p_bonus'),
(22842, 'spell_cw_frenzied_regeneration'),
(20186, 'spell_cw_judgement_of_wisdom'),
(61013, 'spell_cw_pet_hit_expertise_scaling'),
(61017, 'spell_cw_pet_hit_expertise_scaling'),
(-49182, 'spell_cw_dk_blade_barrier'),
(-49208, 'spell_cw_dk_death_rune'),
(-49467, 'spell_cw_dk_death_rune'),
(-54639, 'spell_cw_dk_death_rune');
