-- mod-classless-wildcard: OPTIONAL — classless itemization
--
-- Removes class restrictions from every item so any Hero can wear/wield
-- anything, exactly like Ascension. This is the correct lever: the core
-- checks item_template.AllowableClass before any script hook fires, and the
-- client learns the value from the item query cache, so no client patch is
-- needed. Weapon/armor *proficiencies* are taught by the module itself.
--
-- NOT applied automatically (it rewrites item_template). Apply it once to
-- your world database when you're ready:
--     mysql acore_world < cw_classless_items.sql
--
-- To revert, restore AllowableClass from a backup of item_template.
-- Players may need to delete their client Cache folder to see the change.

UPDATE `item_template` SET `AllowableClass` = -1 WHERE `AllowableClass` != -1;

-- Also drop "Classes: ..." requirements coming from RequiredSpell-based sets?
-- (left untouched on purpose — profession/quest requirements keep working)
