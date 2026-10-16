"""Class gates in the client's own interface code, opened for a Hero.

Every Hero is a Paladin to the client, so a FrameXML branch kept for another
class never runs, whatever that class's abilities the Hero holds. These edits
are made at install time to the files read from the player's own client, the
same way charcreate.py edits CharacterCreate.lua, and load because the exe
patch accepts custom interface files. Editing Blizzard's file keeps the code
Blizzard's: an addon re-doing the same work from outside would taint it (the
totem buttons' right-click DestroyTotem would then be refused in combat).

Each edit matches exact stock text and is skipped, not forced, when the text is
not there, so another client revision is left as it was. Each is idempotent.
"""

TOTEMFRAME_LUA = "Interface\\FrameXML\\TotemFrame.lua"
OPTIONS_LUA = "Interface\\FrameXML\\InterfaceOptionsPanels.lua"
OPTIONS_XML = "Interface\\FrameXML\\InterfaceOptionsPanels.xml"

# TotemFrame_Update hides the totem timers whenever a pet is out, unless the
# class is a Death Knight or a Shaman: a Hero with a pet lost them, and their
# right-click to destroy a totem. The hiding branch goes.
_TOTEM_HIDE = "\t\telse\n\t\t\tTotemFrame:Hide();\n\t\t\treturn;\n"
_TOTEM_KEEP = "\t\t-- mod-classless-wildcard: every class keeps its totem timers with a pet out\n"

# The floating combat text "Combo Points" option is forced off and greyed for
# anyone not a Rogue or a Druid (three tests, two in the Lua and one in the
# XML). A Hero earns combo points too.
_COMBO_GATE = 'if ( class ~= "ROGUE" and class ~= "DRUID" ) then'
_COMBO_OPEN = 'if ( false ) then -- mod-classless-wildcard: a Hero earns combo points too'


CONSTANTS_LUA = "Interface\\FrameXML\\Constants.lua"
PAPERDOLL_LUA = "Interface\\FrameXML\\PaperDollFrame.lua"
RAIDUI_LUA = "Interface\\AddOns\\Blizzard_RaidUI\\Blizzard_RaidUI.lua"

# The Hero's class color, in place of the Paladin's pink: names in chat, the
# raid and party frames, the who and guild lists (RAID_CLASS_COLORS), and the
# nameplates (the exe's own table, exepatch.HERO_COLOR). Jade, a hue no stock
# class uses, and neither path's color in the addon (Classless 00ccff,
# Wildcard ff8800).
HERO_RGB = (0x1A, 0xE6, 0xB3)

_PALADIN_COLOR = '\t["PALADIN"] = { r = 0.96, g = 0.55, b = 0.73 },\n'
_HERO_COLOR = ('\t["PALADIN"] = { r = %.2f, g = %.2f, b = %.2f }, '
               '-- mod-classless-wildcard: the Hero color\n'
               % tuple(c / 255 for c in HERO_RGB))

# The raid window's Pets group lists the pets of Hunters and Warlocks only.
_RAID_PETS = 'if ( fileName == "HUNTER" or fileName == "WARLOCK" ) then'
_RAID_PETS_HERO = ('if ( fileName == "HUNTER" or fileName == "WARLOCK" or fileName == "PALADIN" ) then'
                   ' -- mod-classless-wildcard: a Hero can keep a pet')

# The character sheet's pet lines ("Increases your pet's Stamina by ...") come
# from ComputePetBonus, which knows only the Warlock and the Hunter, so a
# Hero's read 0 and were left out. A Hero's pet takes the bonus of its own
# kind: a hunter pet the Hunter's, a demon the Warlock's (a named family and a
# mana bar; a ghoul runs on energy and a water elemental has no family).
_PET_BONUS_HEAD = ('function ComputePetBonus(stat, value)\n'
                   '\tlocal temp, unitClass = UnitClass("player");\n'
                   '\tunitClass = strupper(unitClass);\n')
_PET_BONUS_HERO = (_PET_BONUS_HEAD +
                   '\t-- mod-classless-wildcard: a Hero\'s pet takes the bonus of its own kind\n'
                   '\tif ( unitClass == "PALADIN" ) then\n'
                   '\t\tlocal hasPetUI, isHunterPet = HasPetUI();\n'
                   '\t\tif ( isHunterPet ) then\n'
                   '\t\t\tunitClass = "HUNTER";\n'
                   '\t\telseif ( hasPetUI and UnitCreatureFamily("pet") and UnitPowerType("pet") == 0 ) then\n'
                   '\t\t\tunitClass = "WARLOCK";\n'
                   '\t\tend\n'
                   '\tend\n')


def _lf(text):
    return text.replace("\r\n", "\n"), "\r\n" in text


def _restore(text, crlf):
    return text.replace("\n", "\r\n") if crlf else text


def open_totem_frame(lua_text: str):
    """Returns (new_text, changed)."""
    text, crlf = _lf(lua_text)
    if _TOTEM_KEEP in text or text.count(_TOTEM_HIDE) != 1:
        return lua_text, False
    return _restore(text.replace(_TOTEM_HIDE, _TOTEM_KEEP), crlf), True


def open_combo_option(text: str, expected: int):
    """Opens the combo point option's class tests; `expected` is how many the
    stock file has (2 in the Lua, 1 in the XML). Returns (new_text, changed)."""
    body, crlf = _lf(text)
    if _COMBO_OPEN in body or body.count(_COMBO_GATE) != expected:
        return text, False
    return _restore(body.replace(_COMBO_GATE, _COMBO_OPEN), crlf), True


def _swap_once(text: str, stock: str, ours: str):
    body, crlf = _lf(text)
    if ours in body or body.count(stock) != 1:
        return text, False
    return _restore(body.replace(stock, ours), crlf), True


def hero_class_color(lua_text: str):
    """Constants.lua: the Paladin entry of RAID_CLASS_COLORS becomes the Hero
    color. Returns (new_text, changed)."""
    return _swap_once(lua_text, _PALADIN_COLOR, _HERO_COLOR)


def open_raid_pets(lua_text: str):
    """Blizzard_RaidUI.lua: a Hero's pet joins the raid window's Pets group.
    Returns (new_text, changed)."""
    return _swap_once(lua_text, _RAID_PETS, _RAID_PETS_HERO)


def open_pet_bonus(lua_text: str):
    """PaperDollFrame.lua: a Hero's pet bonus lines. Returns (new_text, changed)."""
    return _swap_once(lua_text, _PET_BONUS_HEAD, _PET_BONUS_HERO)


# ---------------------------------------------------------------- the bar row
#
# A Hero can hold a stance bar, a pet bar and a totem bar at once, and more
# than ten forms. Blizzard's layout pass (UIParent_ManageFramePositions, run
# through the secure FramePositionDelegate) hides the totem bar whenever a
# stance bar shows, and reads ShapeshiftButton1..N by global name for N forms.
# The addon used to put the totem bar back and make buttons 11 and up itself,
# and both taint that secure pass: a global an addon created, or a field it
# wrote (MultiCastActionBarFrame.mode), turns everything after the read
# insecure, so a slide of the pet or totem bar in combat could be blocked.
# These edits do the same work inside Blizzard's own code:
#   - the layout reads only the ten stock stance buttons;
#   - the pet bar is placed after the whole stance row, from ShapeshiftButton1,
#     ShapeshiftButton2 and the form count (the addon spaces its extra buttons
#     at the stock stride);
#   - the totem bar goes after the stance row and the pet bar instead of
#     hiding, or one row up when the row is full.
UIPARENT_LUA = "Interface\\FrameXML\\UIParent.lua"
PETBAR_LUA = "Interface\\FrameXML\\PetActionBarFrame.lua"

_FORM_LOOP = "for i=1, GetNumShapeshiftForms() do"
_FORM_LOOP_STOCK_TEN = "for i=1, min(GetNumShapeshiftForms(), NUM_SHAPESHIFT_SLOTS) do"

_TOTEM_HACK = (
    "\t-- HACK: we have too many bars in this game now...\n"
    "\t-- if the shapeshift bar is shown then hide the multi-cast bar\n"
    "\t-- we'll have to figure out what we should do in this case if it ever really becomes a problem\n"
    "\t-- HACK 2: if the possession bar is shown then hide the multi-cast bar\n"
    "\t-- yeah, way too many bars...\n"
    "\tif ( ( ShapeshiftBarFrame and ShapeshiftBarFrame:IsShown() ) or\n"
    "\t\t ( PossessBarFrame and PossessBarFrame:IsShown() ) ) then\n"
    "\t\tHideMultiCastActionBar();\n"
    "\telseif ( HasMultiCastActionBar and HasMultiCastActionBar() ) then\n"
    "\t\tShowMultiCastActionBar();\n"
    "\tend\n")
_TOTEM_ROW = (
    "\t-- mod-classless-wildcard: a Hero can have a stance bar and a totem bar at once,\n"
    "\t-- so the totem bar goes after the stance row (and the pet bar) instead of hiding.\n"
    "\t-- The possess bar still takes the place over.\n"
    "\tif ( PossessBarFrame and PossessBarFrame:IsShown() ) then\n"
    "\t\tHideMultiCastActionBar();\n"
    "\telseif ( HasMultiCastActionBar and HasMultiCastActionBar() ) then\n"
    "\t\tMULTICASTACTIONBAR_XPOS = 30;\n"
    "\t\tif ( ShapeshiftBarFrame and ShapeshiftBarFrame:IsShown() and GetNumShapeshiftForms() > 0 ) then\n"
    "\t\t\tlocal x = ShapeshiftBar_RowRight() - (MainMenuBar:GetLeft() or 0);\n"
    "\t\t\tif ( PetActionBarFrame:IsShown() and not PetActionBarFrame_IsAboveShapeshift() ) then\n"
    "\t\t\t\tPetActionBar_UpdatePositionValues();\n"
    "\t\t\t\tx = max(x, PETACTIONBAR_XPOS + PetActionBarFrame:GetWidth());\n"
    "\t\t\tend\n"
    "\t\t\tx = x + 12;\n"
    "\t\t\tif ( x + MultiCastActionBarFrame:GetWidth() <= MainMenuBar:GetWidth() ) then\n"
    "\t\t\t\tMULTICASTACTIONBAR_XPOS = x;\n"
    "\t\t\telse\n"
    "\t\t\t\tMULTICASTACTIONBAR_YPOS = MULTICASTACTIONBAR_YPOS + MultiCastActionBarFrame:GetHeight() + 4;\n"
    "\t\t\tend\n"
    "\t\tend\n"
    "\t\tif ( MultiCastActionBarFrame:IsShown() and MultiCastActionBarFrame.state == \"top\" ) then\n"
    "\t\t\tMultiCastActionBarFrame:SetPoint(\"BOTTOMLEFT\", MultiCastActionBarFrame:GetParent(), \"TOPLEFT\", MULTICASTACTIONBAR_XPOS, MULTICASTACTIONBAR_YPOS);\n"
    "\t\tend\n"
    "\t\tShowMultiCastActionBar();\n"
    "\tend\n")
_ROW_RIGHT = (
    "\n-- mod-classless-wildcard: the right edge of the whole stance row, forms past\n"
    "-- the ten stock buttons included, from Blizzard's own buttons and the form count\n"
    "function ShapeshiftBar_RowRight()\n"
    "\tlocal forms = GetNumShapeshiftForms();\n"
    "\tlocal stock = min(forms, NUM_SHAPESHIFT_SLOTS);\n"
    "\tlocal right = _G[\"ShapeshiftButton\"..stock]:GetRight() or 0;\n"
    "\tif ( forms > stock ) then\n"
    "\t\tright = right + (forms - stock) * ((ShapeshiftButton2:GetLeft() or 0) - (ShapeshiftButton1:GetLeft() or 0));\n"
    "\tend\n"
    "\treturn right;\n"
    "end\n")

_PETBAR_STOCK = "\t\tPETACTIONBAR_XPOS = _G[\"ShapeshiftButton\"..GetNumShapeshiftForms()]:GetRight() + 20;\n"
_PETBAR_ROW = ("\t\t-- mod-classless-wildcard: after the whole stance row, forms past ten included\n"
               "\t\tPETACTIONBAR_XPOS = (ShapeshiftBar_RowRight and ShapeshiftBar_RowRight()\n"
               "\t\t\tor _G[\"ShapeshiftButton\"..GetNumShapeshiftForms()]:GetRight()) + 20;\n")


def open_bar_row(lua_text: str):
    """UIParent.lua: the stance loops read the ten stock buttons only, the
    totem bar goes after the stance row instead of hiding, and the row's right
    edge is ShapeshiftBar_RowRight(). Returns (new_text, changed)."""
    body, crlf = _lf(lua_text)
    if "function ShapeshiftBar_RowRight()" in body:
        return lua_text, False
    if body.count(_FORM_LOOP) != 2 or body.count(_TOTEM_HACK) != 1:
        return lua_text, False
    body = body.replace(_FORM_LOOP, _FORM_LOOP_STOCK_TEN).replace(_TOTEM_HACK, _TOTEM_ROW)
    return _restore(body + _ROW_RIGHT, crlf), True


def open_pet_bar_row(lua_text: str):
    """PetActionBarFrame.lua: the pet bar starts after the whole stance row.
    Returns (new_text, changed)."""
    return _swap_once(lua_text, _PETBAR_STOCK, _PETBAR_ROW)
