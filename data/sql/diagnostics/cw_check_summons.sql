-- Why is a "place a thing here" spell not placing anything?
--
-- Run against acore_world. Every row that comes back says PASS or names the
-- exact fault. Four separate bugs have made these spells summon nothing, and
-- each one is invisible in the game and silent in the log except the first:
--
--   1. EffectMiscValueB = 0. Spell::EffectSummonType looks the value up in
--      SummonProperties.dbc and returns before creating anything when there is
--      no such row. There is no row 0. The worldserver log carries
--      "EffectSummonType: Unhandled summon type 0" once per cast.
--   2. flags_extra 0x80 (CREATURE_FLAG_EXTRA_TRIGGER). Unit.cpp replaces the
--      display id in the update block with GetFirstInvisibleModel() for every
--      viewer who is not in GM mode, whatever the model table says.
--   3. No creature_template_model row at all, which stops Creature::Create.
--   4. Display 11686, which IS the invisible model (InvisibleStalker.mdx).
--
-- A spell that passes all four and still places nothing is something new, and
-- the output below is what to send back.

SELECT
    s.ID                                   AS spell,
    s.Name_Lang_enUS                       AS name,
    s.EffectMiscValue_1                    AS creature,
    s.EffectMiscValueB_1                   AS summon_type,
    m.CreatureDisplayID                    AS display,
    CASE
        -- SUMMON_PET (56) is Player::SummonPet and never reads MiscValueB, so a
        -- zero there is correct for it and a fault for everything else. The
        -- first cut of this query checked the zero first and reported the one
        -- summon that has always worked as broken.
        WHEN s.Effect_1 = 56
            THEN 'PASS (SUMMON_PET, which does not use a summon type)'
        WHEN s.Effect_1 <> 28
            THEN CONCAT('effect 1 is ', s.Effect_1, ', not 28 SUMMON')
        WHEN s.EffectMiscValueB_1 = 0
            THEN 'FAIL 1: summon type 0, so the effect returns before summoning'
        WHEN c.entry IS NULL
            THEN CONCAT('FAIL: no creature_template row for ', s.EffectMiscValue_1)
        WHEN (c.flags_extra & 0x80) <> 0
            THEN 'FAIL 2: CREATURE_FLAG_EXTRA_TRIGGER, so the client is told to draw nothing'
        WHEN m.CreatureDisplayID IS NULL
            THEN 'FAIL 3: no creature_template_model row, so Creature::Create fails'
        WHEN m.CreatureDisplayID = 11686
            THEN 'FAIL 4: display 11686 is the invisible model'
        ELSE 'PASS'
    END                                    AS verdict
FROM spell_dbc s
LEFT JOIN creature_template       c ON c.entry     = s.EffectMiscValue_1
LEFT JOIN creature_template_model m ON m.CreatureID = s.EffectMiscValue_1 AND m.Idx = 0
WHERE s.ID BETWEEN 960000 AND 962047
  AND s.Effect_1 IN (28, 56)
ORDER BY s.ID;

-- Which generator run the server is actually holding. If this does not match
-- the generation printed at the top of cw_spells_forged.sql, the file has not
-- been applied and nothing above means anything.
SELECT `value` AS generation_loaded FROM cw_forged_meta WHERE `key` = 'generation';
