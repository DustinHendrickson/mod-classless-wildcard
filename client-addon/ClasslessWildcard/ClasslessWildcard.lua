-- ClasslessWildcard: Character Advancement panel for mod-classless-wildcard
-- WotLK 3.3.5a client. Talks to the server over the "CWCL" addon channel.

local PREFIX = "CWCL"
local ADDON_NAME = "ClasslessWildcard"
local ADDON_VERSION = "0.9.5"

local RARITY_COLORS = {
    [0] = "|cffffffff", -- common
    [1] = "|cff1eff00", -- uncommon
    [2] = "|cff0070dd", -- rare
    [3] = "|cffa335ee", -- epic
    [4] = "|cffff8000", -- legendary
}
local RARITY_NAMES = {
    [0] = "|cffffffffCommon|r",
    [1] = "|cff1eff00Uncommon|r",
    [2] = "|cff0070ddRare|r",
    [3] = "|cffa335eeEpic|r",
    [4] = "|cffff8000Legendary|r",
}
local RARITY_RGB = {
    [0] = { 1, 1, 1 }, [1] = { 0.12, 1, 0 }, [2] = { 0, 0.44, 0.87 },
    [3] = { 0.64, 0.21, 0.93 }, [4] = { 1, 0.5, 0 },
}
local CLASS_NAMES = {
    [1] = "Warrior", [2] = "Paladin", [3] = "Hunter", [4] = "Rogue", [5] = "Priest",
    [6] = "Death Knight", [7] = "Shaman", [8] = "Mage", [9] = "Warlock", [11] = "Druid",
}
-- Every class, Death Knight included. Whether its button is SHOWN depends on
-- the server: with IncludeDeathKnight off there are no Death Knight abilities
-- or talents in the library, so the button would open an empty page. The old
-- list left 6 out permanently, which meant a realm that enabled Death Knight
-- content had no way to browse it.
local CLASS_ORDER = { 1, 2, 3, 4, 5, 6, 7, 8, 9, 11 }

-- ---------------------------------------------------------------------------
-- state
-- ---------------------------------------------------------------------------
local CW = {
    state = { mode = 255, ae = 0, te = 0, pity = 0, chance = 0, scrolls = 0,
              level = 1, deadline = 5, rebirth = 0, rebirthCost = 0,
              rerolls = 0, scrollCost = 0, scrollBuy = 0,
              -- 0 until the first state packet: the resource bars stay hidden
              -- until the server has told us this character actually has the
              -- extra pools, rather than flashing up on a non-module realm
              universalResources = 0,
              comboPoints = 0,
              -- runes, mirrored from the server. nil until the first RU
              -- message, which is how the bar stays invisible on realms that
              -- do not run Death Knight abilities at all.
              runes = nil, runic = 0, runicMax = 0 },
    classIndex = 1,
    -- classless talent pricing; the server overrides these via the CFG message
    talentCost = 1, talentFlat = true,
    abilPage = 0, abilTotal = 1, abilRows = {},
    tabs = {}, tabIndex = 1,
    talPage = 0, talTotal = 1, talRows = {},
    owned = {}, ownedT = {},
    archetypes = {},
    tab = "ABIL",
    heroPage = 0, wcPage = 0,
    stats = { budget = 0, unspent = 0, perPoint = 1, alloc = { 0, 0, 0, 0, 0 }, enabled = 1,
              uniStats = false, apPerAgi = 1, rapPerAgi = 1, spPerInt = 0.5,
              strMeleeAP = 2, agiMeleeAP = 0, agiRangedAP = 1,
              critPerAgi = 0, spellCritPerInt = 0, mp5PerSpi = 0, hp5PerSpi = 0 },
    statsPending = nil, -- local unsaved edits
}
local STAT_NAMES = { "Strength", "Agility", "Stamina", "Intellect", "Spirit" }

local function Send(msg)
    SendAddonMessage(PREFIX, msg, "WHISPER", UnitName("player"))
end

local function Print(msg)
    DEFAULT_CHAT_FRAME:AddMessage("|cff00ccff[Classless]|r " .. msg)
end

local function SpellLabel(spellId, rarity)
    local name = GetSpellInfo(spellId) or ("Spell " .. spellId)
    return (RARITY_COLORS[rarity or 0] or "|cffffffff") .. name .. "|r"
end

local function SpellIcon(spellId)
    local _, _, icon = GetSpellInfo(spellId)
    return icon or "Interface\\Icons\\INV_Misc_QuestionMark"
end

-- Browser sort orders and the ability type filter. The server sorts and
-- filters, so a page comes back in the order asked for; the choice is kept in
-- ClasslessWildcardDB across sessions.
CW.BROWSE = {
    ABIL_SORTS = { "Level 1-80", "Level 80-1", "Name A-Z", "Name Z-A", "By type" },
    TAL_SORTS  = { "Tier 1-11", "Tier 11-1", "Name A-Z", "Name Z-A", "By type" },
    -- label, and the type argument the server expects (0 = everything)
    ABIL_TYPES = { { "All", 0 }, { "Melee", 2 }, { "Ranged", 3 }, { "Spells", 4 },
                   { "Heals", 5 }, { "Utility", 1 }, { "Passive", 6 } },
    TYPE_NAMES = { [0] = "Utility", [1] = "Melee", [2] = "Ranged", [3] = "Spell", [4] = "Heal", [5] = "Passive" },
}
CW.abilSort, CW.abilType, CW.talSort = 1, 1, 1

local function RequestAbil(page)
    CW.abilPage = page
    Send("ABIL " .. CLASS_ORDER[CW.classIndex] .. " " .. page .. " " .. (CW.abilSort - 1)
         .. " " .. CW.BROWSE.ABIL_TYPES[CW.abilType][2])
end

local function RequestTal(page)
    local t = CW.tabs[CW.tabIndex]
    if not t then return end
    CW.talPage = page
    Send("TAL " .. t.id .. " " .. page .. " " .. (CW.talSort - 1))
end
CW.RequestAbil, CW.RequestTal = RequestAbil, RequestTal

-- ---------------------------------------------------------------------------
-- main frame: "Character Advancement" — Ascension-style single-screen layout
-- (class strip on top, Abilities + Talents panes, My Build sidebar, bottom bar)
-- ---------------------------------------------------------------------------
local frame = CreateFrame("Frame", "ClasslessWildcardFrame", UIParent)
frame:SetWidth(950); frame:SetHeight(600)
frame:SetPoint("CENTER")
-- The whole look of the panel (pane outlines, header strips, textured
-- ground) is one baked image applied as the backdrop. RefreshPanelArt applies
-- it again on entering the world, after a cinematic and whenever the panel
-- opens: a brand-new character plays the intro movie right after addons
-- load, and the client drops textures loaded before it, which left the panel
-- flat until a reload.
CW.PANEL_BACKDROP = {
    bgFile = "Interface\\AddOns\\ClasslessWildcard\\panel_bg", -- baked layout art
    edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
    tile = false, edgeSize = 32,
    insets = { left = 0, right = 0, top = 0, bottom = 0 },
}
frame:SetBackdrop(CW.PANEL_BACKDROP)
-- Opaque backing UNDER the baked art: panel_bg has transparent regions, so
-- without this the world shows through the gaps between the painted panes.
local frameBg = frame:CreateTexture(nil, "BACKGROUND", nil, -8)
frameBg:SetPoint("TOPLEFT", 6, -6)
frameBg:SetPoint("BOTTOMRIGHT", -6, 6)
frameBg:SetTexture(0.04, 0.045, 0.06, 1)

frame:SetMovable(true); frame:EnableMouse(true)
frame:RegisterForDrag("LeftButton")
frame:SetScript("OnDragStart", frame.StartMoving)
frame:SetScript("OnDragStop", frame.StopMovingOrSizing)
frame:Hide()
tinsert(UISpecialFrames, "ClasslessWildcardFrame")

-- clickable dice crest: opens the Wildcard roll/reroll experience
local titleBtn = CreateFrame("Button", nil, frame)
titleBtn:SetWidth(64); titleBtn:SetHeight(64)
titleBtn:SetPoint("TOPLEFT", 20, -16)

local titleIcon = titleBtn:CreateTexture(nil, "ARTWORK")
titleIcon:SetAllPoints(titleBtn)
titleIcon:SetTexture("Interface\\AddOns\\ClasslessWildcard\\icon")

-- glow behind the die brightens on hover, so it reads as clickable
local titleGlow = titleBtn:CreateTexture(nil, "BACKGROUND")
titleGlow:SetWidth(100); titleGlow:SetHeight(100)
titleGlow:SetPoint("CENTER")
titleGlow:SetTexture("Interface\\AddOns\\ClasslessWildcard\\glow")
titleGlow:SetBlendMode("ADD")
titleGlow:SetVertexColor(0.45, 0.75, 1)
titleGlow:SetAlpha(0)

function CW.RefreshPanelArt()
    frame:SetBackdrop(CW.PANEL_BACKDROP)
    titleIcon:SetTexture("Interface\\AddOns\\ClasslessWildcard\\icon")
    titleGlow:SetTexture("Interface\\AddOns\\ClasslessWildcard\\glow")
end

titleBtn:SetScript("OnEnter", function(self)
    titleGlow:SetAlpha(0.9)
    titleIcon:SetVertexColor(1.3, 1.3, 1.3)
    GameTooltip:SetOwner(self, "ANCHOR_BOTTOMRIGHT")
    local s = CW.state
    if s.mode ~= 1 then
        GameTooltip:SetText("Wildcard rolls")
        GameTooltip:AddLine("Only Wildcard Heroes roll the dice for abilities.", 0.8, 0.8, 0.8, true)
    elseif (s.level or 1) < (s.freeReroll or 10) then
        GameTooltip:SetText("|cffffd100Roll your Starting Hand|r")
        GameTooltip:AddLine("Click to reroll your starter abilities.", 0.3, 1, 0.3, true)
        GameTooltip:AddLine("Free before level " .. (s.freeReroll or 10)
            .. " -- lock the ones you like.", 0.6, 0.9, 0.6, true)
    else
        GameTooltip:SetText("Starting Hand (closed)")
        GameTooltip:AddLine("Free starter rolls end at level " .. (s.freeReroll or 10) .. ".",
            0.8, 0.8, 0.8, true)
        GameTooltip:AddLine("Reroll anything you own one at a time from |cffffd100My Build|r, using the circular arrow beside it.", 0.6, 0.9, 0.6, true)
    end
    GameTooltip:Show()
end)
titleBtn:SetScript("OnLeave", function()
    titleGlow:SetAlpha(0)
    titleIcon:SetVertexColor(1, 1, 1)
    GameTooltip:Hide()
end)
titleBtn:SetScript("OnMouseDown", function() titleGlow:SetAlpha(1); titleIcon:SetVertexColor(0.85, 0.85, 0.85) end)
titleBtn:SetScript("OnMouseUp", function() titleGlow:SetAlpha(0.9); titleIcon:SetVertexColor(1.3, 1.3, 1.3) end)
-- The starting hand is a BELOW-LEVEL-10 mechanic: free rolls, lock what you
-- like, reroll the rest. From level 10 it is over for good -- rerolls cost a
-- charge and are made one at a time from My Build -- so nothing may reopen it.
function CW.CanShowHand()
    local s = CW.state
    return s.mode == 1 and (s.level or 1) < (s.freeReroll or 10)
end

titleBtn:SetScript("OnClick", function()
    if not CW.CanShowHand() then return end
    if PlaySound then pcall(PlaySound, "igMainMenuOptionCheckBoxOn") end
    if CW.handFrame then CW.handFrame:Show() end
end)

local title = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
title:SetPoint("TOP", 0, -18)
title:SetText("Character Advancement")

local closeBtn = CreateFrame("Button", nil, frame, "UIPanelCloseButton")
closeBtn:SetPoint("TOPRIGHT", -8, -8)

local statusText = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
statusText:SetPoint("TOP", 0, -40)

local subStatusText = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
subStatusText:SetPoint("TOP", 0, -56)

-- Blizzard page-arrow styling
local function StyleArrow(btn, prev)
    btn:SetWidth(26); btn:SetHeight(26)
    local base = prev and "Interface\\Buttons\\UI-SpellbookIcon-PrevPage-"
                       or "Interface\\Buttons\\UI-SpellbookIcon-NextPage-"
    btn:SetNormalTexture(base .. "Up")
    btn:SetPushedTexture(base .. "Down")
    btn:SetHighlightTexture("Interface\\Buttons\\UI-Common-MouseHilight", "ADD")
end

-- class strip -------------------------------------------------------------------
local CLASS_TOKENS = {
    [1] = "WARRIOR", [2] = "PALADIN", [3] = "HUNTER", [4] = "ROGUE", [5] = "PRIEST",
    [6] = "DEATHKNIGHT", [7] = "SHAMAN", [8] = "MAGE", [9] = "WARLOCK", [11] = "DRUID",
}
local CLASS_TCOORDS = { -- UI-CharacterCreate-Classes 4x4 atlas
    WARRIOR     = { 0.00, 0.25, 0.00, 0.25 },
    MAGE        = { 0.25, 0.50, 0.00, 0.25 },
    ROGUE       = { 0.50, 0.75, 0.00, 0.25 },
    DRUID       = { 0.75, 1.00, 0.00, 0.25 },
    HUNTER      = { 0.00, 0.25, 0.25, 0.50 },
    SHAMAN      = { 0.25, 0.50, 0.25, 0.50 },
    PRIEST      = { 0.50, 0.75, 0.25, 0.50 },
    WARLOCK     = { 0.75, 1.00, 0.25, 0.50 },
    PALADIN     = { 0.00, 0.25, 0.50, 0.75 },
    DEATHKNIGHT = { 0.25, 0.50, 0.50, 0.75 },
}
local classButtons = {}
local CLASS_BTN = 38
for i, classId in ipairs(CLASS_ORDER) do
    local b = CreateFrame("Button", nil, frame)
    b.classId = classId
    b:SetWidth(CLASS_BTN); b:SetHeight(CLASS_BTN)
    b.icon = b:CreateTexture(nil, "ARTWORK")
    b.icon:SetAllPoints(b)
    -- the addon ships its OWN class-icon atlas (embedded, decoupled from the
    -- game files); fall back to the stock atlas if it was not installed
    if not b.icon:SetTexture("Interface\\AddOns\\ClasslessWildcard\\classicons") then
        b.icon:SetTexture("Interface\\Glues\\CharacterCreate\\UI-CharacterCreate-Classes")
    end
    local tc = CLASS_TCOORDS[CLASS_TOKENS[classId]]
    if tc then b.icon:SetTexCoord(tc[1], tc[2], tc[3], tc[4]) end
    b.slot = b:CreateTexture(nil, "OVERLAY")
    b.slot:SetWidth(CLASS_BTN * 1.72); b.slot:SetHeight(CLASS_BTN * 1.72)
    b.slot:SetPoint("CENTER", 0, -1)
    b.slot:SetTexture("Interface\\Buttons\\UI-Quickslot2")
    b.ring = b:CreateTexture(nil, "OVERLAY")
    b.ring:SetWidth(CLASS_BTN * 1.7); b.ring:SetHeight(CLASS_BTN * 1.7)
    b.ring:SetPoint("CENTER", 0, 0)
    b.ring:SetTexture("Interface\\Buttons\\UI-ActionButton-Border")
    b.ring:SetBlendMode("ADD")
    b.ring:Hide()
    b:SetHighlightTexture("Interface\\Buttons\\ButtonHilight-Square", "ADD")
    b:SetScript("OnClick", function()
        CW.classIndex = i
        RequestAbil(0)
        -- follow the class across: jump the Talents pane to that class's first
        -- tree, so both panes are showing the same class
        for idx, t in ipairs(CW.tabs) do
            if t.class == classId then
                CW.tabIndex = idx
                RequestTal(0)
                break
            end
        end
    end)
    b:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
        GameTooltip:AddLine(CLASS_NAMES[classId] or "?")
        GameTooltip:Show()
    end)
    b:SetScript("OnLeave", function() GameTooltip:Hide() end)
    classButtons[i] = b
end

-- Position the strip over the buttons that are actually visible, so hiding the
-- Death Knight one leaves the rest centred instead of gapped.
function CW.LayoutClassStrip()
    local visible = {}
    for _, b in ipairs(classButtons) do
        if b.classId == 6 and not CW.dkEnabled then
            b:Hide()
        else
            b:Show()
            table.insert(visible, b)
        end
    end
    local width = #visible * (CLASS_BTN + 8) - 8
    for n, b in ipairs(visible) do
        b:ClearAllPoints()
        b:SetPoint("TOPLEFT", (950 - width) / 2 + (n - 1) * (CLASS_BTN + 8), -70)
    end
end
CW.LayoutClassStrip()

local function UpdateClassStrip()
    for i, b in ipairs(classButtons) do
        if i == CW.classIndex then
            b.ring:Show()
            b.icon:SetVertexColor(1, 1, 1)
        else
            b.ring:Hide()
            b.icon:SetVertexColor(0.75, 0.75, 0.75)
        end
    end
end

-- pane scaffolding ---------------------------------------------------------------
local PANE_TOP = -122
local ENTRY_H, ENTRIES = 34, 10
-- talents get one fewer row: the tree-selector strip eats a slot, and 10 rows
-- ran straight into the pager (server pages talents by 9 to match)
local TAL_ENTRIES = 9
local BUILD_H, BUILD_ROWS = 26, 13

local function MakePaneHeader(x, width, text)
    -- the label sits ON the baked header strip inside each pane (y 130..154)
    local h = frame:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    h:SetPoint("TOPLEFT", x, PANE_TOP - 13)
    h:SetWidth(width)
    h:SetJustifyH("CENTER")
    h:SetText("|cffffd100" .. text .. "|r")
    return h
end

-- one two-line list entry (striped row, framed icon, colored name + info line)
local function MakeEntry(x, y, width, index)
    local e = CreateFrame("Button", nil, frame)
    e:SetWidth(width); e:SetHeight(ENTRY_H - 2)
    e:SetPoint("TOPLEFT", x, y)
    e:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight", "ADD")

    e.stripe = e:CreateTexture(nil, "BACKGROUND")
    e.stripe:SetAllPoints(e)
    e.stripe:SetTexture("Interface\\Buttons\\WHITE8X8")
    if index % 2 == 0 then
        e.stripe:SetVertexColor(1, 1, 1, 0.030)
    else
        e.stripe:SetVertexColor(0, 0, 0, 0.22)
    end

    e.sep = e:CreateTexture(nil, "BACKGROUND")
    e.sep:SetHeight(1)
    e.sep:SetPoint("BOTTOMLEFT", 2, 0)
    e.sep:SetPoint("BOTTOMRIGHT", -2, 0)
    e.sep:SetTexture("Interface\\Buttons\\WHITE8X8")
    e.sep:SetVertexColor(0.82, 0.66, 0.20, 0.10)

    e.icon = e:CreateTexture(nil, "ARTWORK")
    e.icon:SetWidth(28); e.icon:SetHeight(28)
    e.icon:SetPoint("LEFT", 4, 0)
    e.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)

    e.slot = e:CreateTexture(nil, "OVERLAY") -- beveled Blizzard slot frame
    e.slot:SetWidth(48); e.slot:SetHeight(48)
    e.slot:SetPoint("CENTER", e.icon, "CENTER", 0, -1)
    e.slot:SetTexture("Interface\\Buttons\\UI-Quickslot2")

    e.check = e:CreateTexture(nil, "OVERLAY")
    e.check:SetWidth(14); e.check:SetHeight(14)
    e.check:SetPoint("BOTTOMRIGHT", e.icon, "BOTTOMRIGHT", 5, -4)
    e.check:SetTexture("Interface\\RaidFrame\\ReadyCheck-Ready")
    e.check:Hide()

    e.name = e:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    e.name:SetPoint("TOPLEFT", e.icon, "TOPRIGHT", 9, -2)
    e.name:SetJustifyH("LEFT")
    e.name:SetWidth(width - 50)
    e.name:SetHeight(11)

    e.sub = e:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    e.sub:SetPoint("BOTTOMLEFT", e.icon, "BOTTOMRIGHT", 9, 2)
    e.sub:SetJustifyH("LEFT")
    e.sub:SetWidth(width - 50)
    e.sub:SetHeight(10)

    e:SetScript("OnEnter", function(self)
        if self.spellId then
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:SetHyperlink("spell:" .. self.spellId)
            if self.tipLine then GameTooltip:AddLine(self.tipLine, 0.9, 0.8, 0.4) end
            GameTooltip:Show()
        end
    end)
    e:SetScript("OnLeave", function() GameTooltip:Hide() end)
    e:Hide()
    return e
end

local function MakePager(x, width, yBottom)
    local prev = CreateFrame("Button", nil, frame)
    prev:SetPoint("BOTTOMLEFT", x, yBottom)
    StyleArrow(prev, true)
    local label = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    label:SetPoint("BOTTOMLEFT", x + width / 2 - 30, yBottom + 8)
    label:SetWidth(60)
    local nxt = CreateFrame("Button", nil, frame)
    nxt:SetPoint("BOTTOMLEFT", x + width - 26, yBottom)
    StyleArrow(nxt, false)
    return prev, label, nxt
end

-- Abilities pane -----------------------------------------------------------------
local ABIL_X, ABIL_W = 24, 296
MakePaneHeader(ABIL_X, ABIL_W, "Abilities")

local abilEntries = {}
for i = 1, ENTRIES do
    abilEntries[i] = MakeEntry(ABIL_X, PANE_TOP - 36 - (i - 1) * ENTRY_H, ABIL_W, i)
end
local abilPrev, abilPage, abilNext = MakePager(ABIL_X, ABIL_W, 66)

-- Talents pane -------------------------------------------------------------------
local TAL_X, TAL_W = 336, 296
MakePaneHeader(TAL_X, TAL_W, "Talents")

-- Sort and filter buttons sit at the ends of the header strips, either side
-- of the pane titles. Clicking cycles the choice and reloads page 1. Block
-- scoped: the main chunk is close to Lua's 200-local limit.
do
    local B = CW.BROWSE
    local HDR_BTN_H = 18
    local function MakeHeaderButton(x, width, label)
        local b = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
        b:SetWidth(width); b:SetHeight(HDR_BTN_H)
        -- centred on the baked header strip (y 130..154, so its middle is
        -- 142): any other offset leaves the button riding the strip's border
        b:SetPoint("TOPLEFT", x, PANE_TOP - (20 - HDR_BTN_H / 2))
        b:SetText(label)
        return b
    end
    local function SaveBrowseChoice(key, value)
        ClasslessWildcardDB = ClasslessWildcardDB or {}
        ClasslessWildcardDB[key] = value
    end
    local abilSortBtn = MakeHeaderButton(ABIL_X + 4, 92, B.ABIL_SORTS[1])
    local abilTypeBtn = MakeHeaderButton(ABIL_X + ABIL_W - 96, 92, B.ABIL_TYPES[1][1])
    local talSortBtn = MakeHeaderButton(TAL_X + 4, 92, B.TAL_SORTS[1])
    abilSortBtn:SetScript("OnClick", function()
        CW.abilSort = CW.abilSort % #B.ABIL_SORTS + 1
        abilSortBtn:SetText(B.ABIL_SORTS[CW.abilSort])
        SaveBrowseChoice("abilSort", CW.abilSort)
        RequestAbil(0)
    end)
    abilTypeBtn:SetScript("OnClick", function()
        CW.abilType = CW.abilType % #B.ABIL_TYPES + 1
        abilTypeBtn:SetText(B.ABIL_TYPES[CW.abilType][1])
        SaveBrowseChoice("abilType", CW.abilType)
        RequestAbil(0)
    end)
    talSortBtn:SetScript("OnClick", function()
        CW.talSort = CW.talSort % #B.TAL_SORTS + 1
        talSortBtn:SetText(B.TAL_SORTS[CW.talSort])
        SaveBrowseChoice("talSort", CW.talSort)
        RequestTal(0)
    end)
    CW.abilSortBtn, CW.abilTypeBtn, CW.talSortBtn = abilSortBtn, abilTypeBtn, talSortBtn

    -- saved choices arrive with the saved variables, after this file has run
    function CW.LoadBrowseChoices()
        ClasslessWildcardDB = ClasslessWildcardDB or {}
        CW.abilSort = B.ABIL_SORTS[ClasslessWildcardDB.abilSort or 0] and ClasslessWildcardDB.abilSort or 1
        CW.abilType = B.ABIL_TYPES[ClasslessWildcardDB.abilType or 0] and ClasslessWildcardDB.abilType or 1
        CW.talSort = B.TAL_SORTS[ClasslessWildcardDB.talSort or 0] and ClasslessWildcardDB.talSort or 1
        abilSortBtn:SetText(B.ABIL_SORTS[CW.abilSort])
        abilTypeBtn:SetText(B.ABIL_TYPES[CW.abilType][1])
        talSortBtn:SetText(B.TAL_SORTS[CW.talSort])
    end
end
local treeLeft = CreateFrame("Button", nil, frame)
treeLeft:SetPoint("TOPLEFT", TAL_X + 2, PANE_TOP - 36)
StyleArrow(treeLeft, true)
local treeText = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
treeText:SetPoint("TOPLEFT", TAL_X + 30, PANE_TOP - 44)
treeText:SetWidth(TAL_W - 60)
local treeRight = CreateFrame("Button", nil, frame)
treeRight:SetPoint("TOPLEFT", TAL_X + TAL_W - 28, PANE_TOP - 36)
StyleArrow(treeRight, false)

local talEntries = {}
for i = 1, TAL_ENTRIES do
    talEntries[i] = MakeEntry(TAL_X, PANE_TOP - 66 - (i - 1) * ENTRY_H, TAL_W, i)
end
local talPrev, talPage, talNext = MakePager(TAL_X, TAL_W, 66)
CW.abilEntries, CW.talEntries = abilEntries, talEntries

-- My Build sidebar ---------------------------------------------------------------
local BUILD_X, BUILD_W = 668, 258
local buildHeader = MakePaneHeader(BUILD_X, BUILD_W, "My Build")
local buildRows = {}
for i = 1, BUILD_ROWS do
    local r = CreateFrame("Button", nil, frame)
    r:SetWidth(BUILD_W); r:SetHeight(BUILD_H - 2)
    r:SetPoint("TOPLEFT", BUILD_X, PANE_TOP - 36 - (i - 1) * BUILD_H)
    r:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight", "ADD")

    r.stripe = r:CreateTexture(nil, "BACKGROUND")
    r.stripe:SetAllPoints(r)
    r.stripe:SetTexture("Interface\\Buttons\\WHITE8X8")
    if i % 2 == 0 then
        r.stripe:SetVertexColor(1, 1, 1, 0.030)
    else
        r.stripe:SetVertexColor(0, 0, 0, 0.22)
    end

    r.icon = r:CreateTexture(nil, "ARTWORK")
    r.icon:SetWidth(20); r.icon:SetHeight(20)
    r.icon:SetPoint("LEFT", 4, 0)
    r.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)

    r.slot = r:CreateTexture(nil, "OVERLAY")
    r.slot:SetWidth(34); r.slot:SetHeight(34)
    r.slot:SetPoint("CENTER", r.icon, "CENTER", 0, -1)
    r.slot:SetTexture("Interface\\Buttons\\UI-Quickslot2")

    r.name = r:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    r.name:SetPoint("LEFT", r.icon, "RIGHT", 8, 0)
    r.name:SetJustifyH("LEFT")
    r.name:SetWidth(BUILD_W - 86)
    r.name:SetHeight(11)

    -- action 1: lock (wildcard) — padlock lights up when locked
    r.lockBtn = CreateFrame("Button", nil, r)
    r.lockBtn:SetWidth(20); r.lockBtn:SetHeight(20)
    r.lockBtn:SetPoint("RIGHT", -28, 0)
    r.lockBtn.tex = r.lockBtn:CreateTexture(nil, "ARTWORK")
    r.lockBtn.tex:SetAllPoints(r.lockBtn)
    r.lockBtn.tex:SetTexture("Interface\\AddOns\\ClasslessWildcard\\lock_open")
    r.lockBtn:SetHighlightTexture("Interface\\Buttons\\UI-Common-MouseHilight", "ADD")

    -- action 2: reroll (wildcard, spin arrows) / unlearn (classless, red X)
    r.actBtn = CreateFrame("Button", nil, r)
    r.actBtn:SetWidth(22); r.actBtn:SetHeight(22)
    r.actBtn:SetPoint("RIGHT", -3, 0)
    r.actBtn.tex = r.actBtn:CreateTexture(nil, "ARTWORK")
    r.actBtn.tex:SetAllPoints(r.actBtn)
    r.actBtn:SetHighlightTexture("Interface\\Buttons\\UI-Common-MouseHilight", "ADD")

    r:SetScript("OnEnter", function(self)
        if self.spellId then
            GameTooltip:SetOwner(self, "ANCHOR_LEFT")
            GameTooltip:SetHyperlink("spell:" .. self.spellId)
            GameTooltip:Show()
        end
    end)
    r:SetScript("OnLeave", function() GameTooltip:Hide() end)
    r:Hide()
    buildRows[i] = r
end
local buildPrev, buildPage, buildNext = MakePager(BUILD_X, BUILD_W, 66)
CW.buildPageNo = 0

-- bottom bar ---------------------------------------------------------------------
local bottomLine = frame:CreateTexture(nil, "ARTWORK")
bottomLine:SetHeight(1); bottomLine:SetWidth(902)
bottomLine:SetPoint("BOTTOMLEFT", 24, 58)
bottomLine:SetTexture("Interface\\Buttons\\WHITE8X8")
bottomLine:SetVertexColor(0.82, 0.66, 0.20, 0.5)

local bottomText = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
-- sits in the empty gap between the left (Help, then Buy Scroll or Archetypes)
-- and right (Stats/Rebirth/Respec) button clusters so it never overlaps a button
bottomText:SetPoint("BOTTOM", -22, 33)
bottomText:SetJustifyH("CENTER")

-- Bottom-right cluster, laid out right-to-left with fixed offsets so nothing
-- overlaps: Respec (-20), Rebirth (-116), Stats (-212).
-- Rebirth only shows sometimes; its slot stays reserved either way.
local statsBtn = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
statsBtn:SetWidth(90); statsBtn:SetHeight(22)
statsBtn:SetPoint("BOTTOMRIGHT", -212, 26)
statsBtn:SetText("Stats")

local respecBtn = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
respecBtn:SetWidth(90); respecBtn:SetHeight(22)
respecBtn:SetPoint("BOTTOMRIGHT", -20, 26)
respecBtn:SetText("Respec")
respecBtn:SetScript("OnClick", function() Send("RESPEC") end)

-- Rebirth: full reset + switch path, for gold (server enforces the cost).
StaticPopupDialogs["CW_CLASSLESS_REBIRTH"] = {
    text = "Rebirth wipes your Hero's abilities and talents and lets you start a\nnew path for |cffffd100%d gold|r. Choose your new path:",
    button1 = "Classless",
    button2 = "Cancel",
    button3 = "Wildcard",
    OnAccept = function() Send("REBIRTH 0") end,   -- Classless
    OnAlt    = function() Send("REBIRTH 1") end,   -- Wildcard
    timeout = 0, whileDead = 1, hideOnEscape = 1, preferredIndex = 3,
}
local rebirthBtn = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
rebirthBtn:SetWidth(90); rebirthBtn:SetHeight(22)
rebirthBtn:SetPoint("BOTTOMRIGHT", -116, 26)
rebirthBtn:SetText("Rebirth")
rebirthBtn:Hide()
rebirthBtn:SetScript("OnClick", function()
    StaticPopup_Show("CW_CLASSLESS_REBIRTH", CW.state.rebirthCost or 0)
end)
CW.rebirthBtn = rebirthBtn

-- Help: opens the "how advancement works" panel (wired to helpFly below).
local helpBtn = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
helpBtn:SetWidth(70); helpBtn:SetHeight(22)
helpBtn:SetPoint("BOTTOMLEFT", 20, 26)
helpBtn:SetText("Help")
CW.helpBtn = helpBtn

-- Buy Scroll: purchase a Reroll Scroll for coin (price scales with level --
-- silver early, gold near cap; the server enforces it). Wildcard-only, where
-- rerolls are spent. scrollCost is copper; GetCoinTextureString renders coins.
StaticPopupDialogs["CW_CLASSLESS_BUYSCROLL"] = {
    text = "Buy a |cff0070ddReroll Scroll|r for %s?\nIt grants one extra reroll for the Wildcard.",
    button1 = "Buy",
    button2 = "Cancel",
    OnAccept = function() Send("BUYSCROLL 0") end,
    timeout = 0, whileDead = 1, hideOnEscape = 1, preferredIndex = 3,
}
local buyScrollBtn = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
buyScrollBtn:SetWidth(160); buyScrollBtn:SetHeight(22)
buyScrollBtn:SetPoint("BOTTOMLEFT", helpBtn, "BOTTOMRIGHT", 8, 0)
buyScrollBtn:SetText("Buy Scroll")
buyScrollBtn:Hide()
buyScrollBtn:SetScript("OnClick", function()
    StaticPopup_Show("CW_CLASSLESS_BUYSCROLL", GetCoinTextureString(CW.state.scrollCost or 0))
end)
buyScrollBtn:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:SetText("Buy a Reroll Scroll")
    GameTooltip:AddLine("Cost: " .. GetCoinTextureString(CW.state.scrollCost or 0) .. "  (rises with your level).", 1, 1, 1)
    GameTooltip:AddLine("Each scroll is one extra reroll for the Wildcard.", 0.8, 0.8, 0.8, true)
    GameTooltip:Show()
end)
buyScrollBtn:SetScript("OnLeave", function() GameTooltip:Hide() end)
CW.buyScrollBtn = buyScrollBtn

-- Settings: the addon's own options, wired to setFly further down (it needs
-- the bar frame, which is built after this).
local setBtn = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
setBtn:SetWidth(90); setBtn:SetHeight(22)
-- past the widest thing that can occupy the shared slot beside Help, so the
-- row does not reflow when Buy Scroll gives way to Archetypes
setBtn:SetPoint("BOTTOMLEFT", 266, 26)
setBtn:SetText("Settings")
CW.settingsBtn = setBtn

-- Archetypes: the starter builds the Hero Advancement NPC offers, for the
-- Classless path. Shares the slot beside Help with Buy Scroll: that one shows
-- only on Wildcard and this one only on Classless, so they never overlap.
-- Wired to archFly below.
local archBtn = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
archBtn:SetWidth(100); archBtn:SetHeight(22)
archBtn:SetPoint("BOTTOMLEFT", helpBtn, "BOTTOMRIGHT", 8, 0)
archBtn:SetText("Archetypes")
archBtn:Hide()
CW.archBtn = archBtn

-- stats flyout -------------------------------------------------------------------
local statFly = CreateFrame("Frame", "ClasslessWildcardStats", frame)
CW.statFly = statFly
statFly:SetWidth(260); statFly:SetHeight(250)
statFly:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -20, 56)
statFly:SetFrameStrata("DIALOG")
statFly:SetBackdrop({
    bgFile = "Interface\\Buttons\\WHITE8X8",
    edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
    tile = false, edgeSize = 14,
    insets = { left = 4, right = 4, top = 4, bottom = 4 },
})
statFly:SetBackdropColor(0.03, 0.03, 0.05, 0.97) -- solid: the panes underneath must not show through
statFly:Hide()

local statTitle = statFly:CreateFontString(nil, "OVERLAY", "GameFontNormal")
statTitle:SetPoint("TOP", 0, -12)

local statRows = {}
for i = 1, 5 do
    local r = CreateFrame("Frame", nil, statFly)
    r:SetWidth(230); r:SetHeight(26)
    r:SetPoint("TOPLEFT", 14, -34 - (i - 1) * 28)
    r.label = r:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    r.label:SetPoint("LEFT", 0, 0)
    r.label:SetJustifyH("LEFT")
    r.label:SetWidth(140)
    r.minus = CreateFrame("Button", nil, r, "UIPanelButtonTemplate")
    r.minus:SetWidth(22); r.minus:SetHeight(20)
    r.minus:SetPoint("RIGHT", -28, 0)
    r.minus:SetText("-")
    r.plus = CreateFrame("Button", nil, r, "UIPanelButtonTemplate")
    r.plus:SetWidth(22); r.plus:SetHeight(20)
    r.plus:SetPoint("RIGHT", 0, 0)
    r.plus:SetText("+")
    statRows[i] = r
end

local statApply = CreateFrame("Button", nil, statFly, "UIPanelButtonTemplate")
statApply:SetWidth(100); statApply:SetHeight(22)
statApply:SetPoint("BOTTOMLEFT", 14, 12)
statApply:SetText("Apply")

local statReset = CreateFrame("Button", nil, statFly, "UIPanelButtonTemplate")
statReset:SetWidth(100); statReset:SetHeight(22)
statReset:SetPoint("BOTTOMRIGHT", -14, 12)
statReset:SetText("Reset edits")

-- archetype flyout ----------------------------------------------------------
-- The same starter builds the Hero Advancement NPC lists, applied with one
-- click. Classless only: the server refuses ARCHAPPLY on any other path, and
-- UpdateStatus hides the button and this panel outside that mode.
local archFly = CreateFrame("Frame", "ClasslessWildcardArchetypes", frame)
archFly:SetWidth(460); archFly:SetHeight(120)
archFly:SetPoint("BOTTOMLEFT", frame, "BOTTOMLEFT", 20, 56)
archFly:SetFrameStrata("DIALOG")
archFly:SetBackdrop({
    bgFile = "Interface\\Buttons\\WHITE8X8",
    edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
    tile = false, edgeSize = 14,
    insets = { left = 4, right = 4, top = 4, bottom = 4 },
})
archFly:SetBackdropColor(0.03, 0.03, 0.05, 0.97) -- solid: the panes underneath must not show through
archFly:EnableMouse(true)
archFly:Hide()
CW.archFly = archFly

archFly.title = archFly:CreateFontString(nil, "OVERLAY", "GameFontNormal")
archFly.title:SetPoint("TOP", 0, -12)
archFly.title:SetText("Starter Archetypes")

archFly.INTRO = "An archetype is a build you follow from level 1 to 80. Choosing one replaces your build: your abilities are unlearned and refunded, and if you own talents the respec fee applies. From then on its abilities and talents are bought for you as each becomes available. Stop following at any time; what you own stays."
archFly.intro = archFly:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
archFly.intro:SetPoint("TOPLEFT", 14, -30)
archFly.intro:SetWidth(432)
archFly.intro:SetJustifyH("LEFT")
archFly.intro:SetText(archFly.INTRO)

-- One archetype row: the name on the first line, the description under it
-- (it may wrap), the ability and talent counts on a line of their own, and a
-- button on the right. Rows are stacked from their measured text heights by
-- FillArchRows, so nothing overlaps whatever the text wraps to. The panel
-- flyout and the first-login wizard both use these.
local ARCH_ROW_H = 46
local function MakeArchRow(parent, width, buttonText)
    local r = CreateFrame("Frame", nil, parent)
    r:SetWidth(width); r:SetHeight(ARCH_ROW_H)
    r.name = r:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    r.name:SetPoint("TOPLEFT", 0, 0)
    r.name:SetWidth(width - 82)
    r.name:SetJustifyH("LEFT")
    r.desc = r:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    r.desc:SetPoint("TOPLEFT", 0, -16)
    r.desc:SetWidth(width - 82)
    r.desc:SetJustifyH("LEFT")
    r.desc:SetJustifyV("TOP")
    r.counts = r:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    r.counts:SetPoint("TOPLEFT", r.desc, "BOTTOMLEFT", 0, -2)
    r.counts:SetWidth(width - 82)
    r.counts:SetJustifyH("LEFT")
    r.apply = CreateFrame("Button", nil, r, "UIPanelButtonTemplate")
    r.apply:SetWidth(70); r.apply:SetHeight(22)
    r.apply:SetPoint("RIGHT", 0, 0)
    r.apply:SetText(buttonText)
    r.apply.defaultText = buttonText
    r:Hide()
    return r
end

-- Text height as the client renders it, never less than one line: the
-- measurement is what the rows are stacked from.
local function TextHeight(fs)
    return math.max(12, fs:GetStringHeight() or 0)
end

-- A scrollable stack of archetype rows. Rows are created for however many
-- archetypes the realm sends and stacked inside a scroll child; once they
-- need more than ARCH_LIST_MAX_H the host stops growing and the list scrolls
-- instead, by mouse wheel or the bar that appears on its right. The panel
-- flyout and the first-login wizard each own one.
local ARCH_LIST_MAX_H = 440   -- tallest the visible part gets before it scrolls
local ARCH_SCROLLBAR_W = 24   -- room kept on the right for the scroll bar
local function MakeArchList(parent, name, width, buttonText)
    local L = { rows = {}, width = width - ARCH_SCROLLBAR_W, buttonText = buttonText }
    L.scroll = CreateFrame("ScrollFrame", name, parent, "UIPanelScrollFrameTemplate")
    L.scroll:SetWidth(L.width); L.scroll:SetHeight(ARCH_ROW_H)
    L.scroll.scrollBarHideable = 1   -- the bar shows only when there is something to scroll
    L.scroll:Hide()
    L.child = CreateFrame("Frame", nil, L.scroll)
    L.child:SetWidth(L.width); L.child:SetHeight(1)
    L.scroll:SetScrollChild(L.child)
    for i = 1, 6 do   -- the usual count up front; FillArchRows makes the rest
        L.rows[i] = MakeArchRow(L.child, L.width, buttonText)
    end
    return L
end

-- Fills a list from an archetype list and places it `top` below the host's
-- top edge at x. Rows are stacked from their measured text heights, made on
-- demand when the realm has more than the list has seen; onChoose(arch) runs
-- when a row's button is clicked. Returns how many rows are showing and the
-- height the visible part takes, which is what the host sizes itself from.
local function FillArchRows(L, list, onChoose, x, top)
    local y = 0
    for i = 1, math.max(#list, #L.rows) do
        local r = L.rows[i]
        if not r then
            r = MakeArchRow(L.child, L.width, L.buttonText)
            L.rows[i] = r
        end
        local arch = list[i]
        if arch then
            local count = (arch.count == 1) and "1 ability" or (arch.count .. " abilities")
            if (arch.ranks or 0) > 0 then count = count .. ", " .. arch.ranks .. " talent ranks" end
            r.name:SetText("|cffffff00" .. arch.name .. "|r" .. (arch.following and "  |cff00ff00following|r" or ""))
            r.desc:SetText(arch.desc)
            r.counts:SetText("|cffaaaaaa" .. count .. "|r")
            r.apply:SetText(arch.following and "Stop" or r.apply.defaultText)
            r.apply:SetScript("OnClick", function() onChoose(arch) end)
            local h = 16 + TextHeight(r.desc) + 2 + 12 + 8
            r:ClearAllPoints()
            r:SetPoint("TOPLEFT", 0, -y)
            r:SetHeight(h)
            r:Show()
            y = y + h
        else
            r:Hide()
        end
    end
    local visible = math.min(y, ARCH_LIST_MAX_H)
    L.child:SetHeight(math.max(y, 1))
    L.scroll:ClearAllPoints()
    L.scroll:SetPoint("TOPLEFT", x, -top)
    L.scroll:SetHeight(math.max(visible, ARCH_ROW_H))
    L.scroll:SetVerticalScroll(0)
    L.scroll:UpdateScrollChildRect()
    L.scroll:Show()
    return #list, visible
end

archFly.list = MakeArchList(archFly, "ClasslessWildcardArchetypeList", 432, "Follow")
archFly.rows = archFly.list.rows

-- Fills the flyout from CW.archetypes (cached from the last AR/ARE reply):
-- the intro text first, the rows stacked under whatever height it wrapped
-- to, and the panel sized to the lot.
local function RenderArchFly()
    local list = CW.archetypes or {}
    if #list > 0 then
        archFly.intro:SetText(archFly.INTRO)
    elseif CW.archetypesLoaded then
        archFly.intro:SetText("No archetypes are configured on this realm.")
    else
        archFly.intro:SetText("Loading...")
    end
    local top = 30 + TextHeight(archFly.intro) + 12
    local shown, used = FillArchRows(archFly.list, list, function(arch)
        Send("ARCHAPPLY " .. (arch.following and 0 or arch.id)) -- 0 = stop following
        archFly:Hide()
        CW.SetTab("HERO") -- show what the archetype bought
    end, 14, top)
    archFly:SetHeight(top + math.max(used, ARCH_ROW_H) + 10)
end
CW.RenderArchFly = RenderArchFly

-- help flyout ---------------------------------------------------------------
-- A scrollable "how it works" panel covering both systems. Static text, so it
-- is built once here; the Help button toggles it.
local helpFly = CreateFrame("Frame", "ClasslessWildcardHelp", frame)
helpFly:SetWidth(600); helpFly:SetHeight(468)
helpFly:SetPoint("CENTER", frame, "CENTER", 0, -8)
helpFly:SetFrameStrata("DIALOG")
helpFly:SetBackdrop({
    edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
    edgeSize = 16,
    insets = { left = 4, right = 4, top = 4, bottom = 4 },
})
helpFly:EnableMouse(true)  -- swallow clicks so the panel behind can't be used through it
helpFly:Hide()

-- solid opaque fill so the busy ability lists behind never bleed through the text
local helpBg = helpFly:CreateTexture(nil, "BACKGROUND")
helpBg:SetPoint("TOPLEFT", 4, -4)
helpBg:SetPoint("BOTTOMRIGHT", -4, 4)
helpBg:SetTexture(0.035, 0.045, 0.07, 1)

local helpTitle = helpFly:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
helpTitle:SetPoint("TOP", 0, -14)
helpTitle:SetText("How Advancement Works")

local helpCloseBtn = CreateFrame("Button", nil, helpFly, "UIPanelCloseButton")
helpCloseBtn:SetPoint("TOPRIGHT", -6, -6)
helpCloseBtn:SetScript("OnClick", function() helpFly:Hide() end)

local helpScroll = CreateFrame("ScrollFrame", "ClasslessWildcardHelpScroll", helpFly, "UIPanelScrollFrameTemplate")
helpScroll:SetPoint("TOPLEFT", 16, -44)
helpScroll:SetPoint("BOTTOMRIGHT", -34, 16)

local helpContent = CreateFrame("Frame", nil, helpScroll)
helpContent:SetWidth(540); helpContent:SetHeight(1)
helpScroll:SetScrollChild(helpContent)

-- Trim a rate for display: 2 not 2.0, 0.5 not 0.50.
local function Rate(v)
    if v == math.floor(v) then return tostring(math.floor(v)) end
    return (string.format("%.2f", v):gsub("0+$", ""):gsub("%.$", ""))
end

-- A per-point percentage this small is unreadable (+0.02%), so invert it into
-- the form players actually use: "1% per 52 Agility".
local function PerPercent(pct)
    if not pct or pct <= 0 then return nil end
    return string.format("%.0f", 1 / pct)
end

-- What one point of a stat is worth. Health and mana come from the core's own
-- fixed conversions; attack power and spell power combine what the chassis
-- gives natively with what the classless layer adds on top. Anything that
-- scales with level (crit, dodge, regeneration) is named rather than given a
-- number, because there is no single per-point figure for it.
local function StatPerPoint(i)
    local s = CW.stats
    local uni = s.uniStats
    if i == 1 then
        return "+" .. Rate(s.strMeleeAP or 2) .. " melee attack power, +0.5 block value"
    elseif i == 2 then
        local melee = (s.agiMeleeAP or 0) + (uni and (s.apPerAgi or 0) or 0)
        local ranged = (s.agiRangedAP or 1) + (uni and (s.rapPerAgi or 0) or 0)
        local ap
        if melee > 0 then
            ap = "+" .. Rate(melee) .. " melee and +" .. Rate(ranged) .. " ranged attack power"
        else
            ap = "+" .. Rate(ranged) .. " ranged attack power"
        end
        local per = PerPercent(s.critPerAgi)
        if per then
            return ap .. ", 1% critical strike per " .. per .. " Agility, plus dodge"
        end
        return ap .. ", plus critical strike and dodge"
    elseif i == 3 then
        return "+10 health (the first 20 points give +1 each)"
    elseif i == 4 then
        local sp = uni and (s.spPerInt or 0) or 0
        local txt = "+15 mana (the first 20 points give +1 each)"
        if sp > 0 then
            txt = txt .. ", +" .. Rate(sp) .. " spell power (past your first 10 Intellect)"
        end
        local per = PerPercent(s.spellCritPerInt)
        if per then
            return txt .. ", 1% spell critical strike per " .. per .. " Intellect"
        end
        return txt .. ", plus spell critical strike"
    end
    if (s.mp5PerSpi or 0) > 0 then
        return string.format("+%.2f mana and +%.2f health per 5 sec while not casting",
                             s.mp5PerSpi, s.hp5PerSpi or 0)
    end
    return "mana and health regeneration, scaling with your level and Intellect"
end

local function BuildHelpText()
    return table.concat({
"|cffffd100You are a Hero.|r |cffffffffThere is no class to pick|r -- character creation offers races only, and every character becomes a Hero. Every Hero runs on the same hidden base class, which grants no special abilities and locks nothing away. Your |cffffffffrace|r is the choice that carries anything: its racial traits are yours to keep. Everything else -- every ability and talent -- you earn yourself, and you can take it from |cffffffffany class in the game|r.",
"",
"You gain that power one of two ways. You choose a path per character, and can |cffffd100Rebirth|r later to switch.",
"",
"|cff00ccff==  CLASSLESS  --  you choose  ==|r",
"Spend two currencies to buy exactly what you want:",
"   |cffffd100Ability Essence (AE)|r  buys abilities.",
"   |cffffd100Talent Essence (TE)|r  buys talent ranks, one point per rank.",
"You start with |cff00ff003 AE|r and earn |cff00ff00+1 AE every level from 4|r, the pace a class learns its abilities at. |cff00ff00Talent Essence arrives from level 10, +1 a level|r: 71 by 80, a full talent build.",
"Abilities are priced by rarity -- |cff9d9d9d1|r / |cff1eff002|r / |cff0070dd3|r / |cffa335ee5|r / |cffff80008|r AE from common to legendary. Talents cost Talent Essence per rank and respect their tree's prerequisites and tier rules -- ranking one to 5 costs 5 TE, so pick your capstones carefully.",
"Unlearning an ability refunds what you paid, |cffffd100Respec|r reshuffles your talents for gold, and every ability line you own |cff00ff00ranks up on its own|r as you level. Talents that teach a spell (Pyroblast, Mortal Strike, Mangle) are not in the talent trees here: the spell is in the Abilities list instead, with every rank, and owning it counts as that talent for prerequisites and tree points.",
"|cffffd100Archetypes|r are builds you follow from level 1 to 80. Pick one from the |cffffd100Archetypes|r button on this panel or at the Hero Advancement NPC: it replaces your build (abilities refunded, the respec fee if you own talents) and from then on buys its abilities and talents for you as each becomes available. Everything it buys is a normal purchase, and you can stop following it at any time.",
"",
"|cffff8800==  WILDCARD  --  the dice choose  ==|r",
"The server rolls abilities and talents for you on a fixed schedule:",
"   |cff00ff00Level 1:|r  4 random abilities to begin.",
"   |cff00ff00From level 10:|r  one roll every level, alternating -- an ability on the even levels, a talent on the odd ones. Talents come no more often than abilities because a talent roll can land on rank 5 outright.",
"Rolls are rarity-weighted: a legendary turns up a little less often than a common.",
"A talent roll also rolls the |cffffd100rank|r you land on, and the rank IS its rarity: rank 1 common, rank 2 uncommon, rank 3 rare, rank 4 epic, |cffff8000rank 5 legendary|r. The rank is drawn from anything above what you already have, not one step up, so a talent you hold at rank 2 can jump straight to rank 5 -- and a talent you have never seen can arrive at its top rank. A high rank is the jackpot: rolls cost you nothing, so landing on rank 5 hands you the full-strength talent for free, where a Classless Hero pays for every rank up to it. Rolling into a talent you already own upgrades it and rolls again, up to four times in one go.",
"You steer your luck:",
"   |cffffd100Rerolls|r -- every level from 10 grants you 3 reroll charges, and rerolls are free below level 10. One pool, spent on abilities or talents alike. Reroll straight from the popup, or later from |cffffd100My Build|r using the circular arrow next to anything you own.",
"   |cffffd100Lock|r -- protect an ability so a later roll can't overwrite it.",
"   |cffffd100Synergy & pity|r -- some rolls are narrowed to abilities that fit the classes you already own. The chance of that starts at 10% and climbs by 10 points every time you reroll, so a cold streak keeps improving your odds until it pays off, then resets. Anything you reroll also goes on a cooldown, so the reroll can never hand you straight back what you just got rid of. That cooldown lasts 24 rolls, which is around 16 levels, so rerolling something is closer to a lasting decision than a do-over. If you reroll through everything available at your level, the cooldowns lift so you always get something you can actually use.",
"   |cffffd100Reroll Scrolls|r -- one scroll, good for an ability OR a talent, for when your charges run dry. Earn them, buy them from the Hero Advancement NPC, or use the |cffffd100Buy Scroll|r button on this panel (the price scales with level -- silver early, gold near the cap).",
"Open the roll screen any time with the |cffffd100dice crest|r at the top-left of this window.",
"",
"|cff40ff40==  Shared by both paths  ==|r",
"   |cffffd100Universal resources|r -- you carry mana, rage AND energy at once, and each spell draws its own, so nothing is ever unusable. The extra bars sit beside your unit frame and remember where you drag them. |cffffd100Settings|r on this panel picks which of them to show, including runes, runic power and combo points; |cffffd100/cwbars|r toggles the lot.",
"   |cffffd100Primary stats|r -- you get points every level to spend across STR / AGI / STA / INT / SPI, and reallocating them is free at any time. Open the |cffffd100Stats|r button and hover any stat to see exactly what it is doing for your Hero right now.",
"      |cffffd100Strength|r -- " .. StatPerPoint(1) .. " per point.",
"      |cffffd100Agility|r -- " .. StatPerPoint(2) .. " per point.",
"      |cffffd100Stamina|r -- " .. StatPerPoint(3) .. " per point.",
"      |cffffd100Intellect|r -- " .. StatPerPoint(4) .. " per point.",
"      |cffffd100Spirit|r -- increases " .. StatPerPoint(5) .. ". Mana regeneration pauses for 5 seconds after you cast. Talents such as Meditation, Arcane Meditation and Intensity let it continue while casting, and any Hero can learn them.",
"   Every stat does something for every Hero, so spend toward the build you are playing.",
"   |cffffd100Proficiencies|r -- every armor and weapon type, dual wield included, is trained for you automatically.",
"   |cffffd100Abilities that come as a set|r -- an ability that can only be used in a stance or a form brings that form with it, and an ability that needs others to be any use brings those: Rend and Charge bring Battle Stance, Cat Form brings Claw and Prowl, Tame Beast brings Call Pet, Revive Pet, Feed Pet and Dismiss Pet. These extras are free, they are not one of your rolls, and they leave when nothing you own still needs them. To be rid of one, reroll or unlearn the ability it came with.",
"   |cffffd100No class tools|r -- spells that ask for a class item, such as Stoneskin Totem asking for an Earth Totem, cast without it. Reagents still apply.",
"   |cffffd100Rebirth|r -- after your path locks in, Rebirth wipes everything and lets you start fresh on either path for gold.",
"",
"|cffaaaaaaEverything here can also be done at the Hero Advancement NPC, found in every major city beside the guild master. Open this panel any time with |r|cffffff00N|r|cffaaaaaa (the old Talents key -- talents live here now), |r|cffffff00/cw|r|cffaaaaaa, or the dice button on your minimap. Rebind the key under Key Bindings > ClasslessWildcard.|r",
}, "\n")
end

local helpText = helpContent:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
helpText:SetPoint("TOPLEFT", 0, 0)
helpText:SetWidth(540)
helpText:SetJustifyH("LEFT")
helpText:SetJustifyV("TOP")
helpText:SetSpacing(3)
local function RefreshHelpText()
    helpText:SetText(BuildHelpText())
    helpContent:SetHeight(helpText:GetStringHeight() + 20)
end
CW.RefreshHelpText = RefreshHelpText
RefreshHelpText()
CW.helpFly = helpFly

helpBtn:SetScript("OnClick", function()
    statFly:Hide(); archFly:Hide(); CW.setFly:Hide()
    if helpFly:IsShown() then helpFly:Hide() else helpFly:Show() end
end)

statsBtn:SetScript("OnClick", function()
    helpFly:Hide(); archFly:Hide(); CW.setFly:Hide()
    if statFly:IsShown() then
        statFly:Hide()
    else
        Send("STATS")
        statFly:Show()
        if CW.RenderStats then CW.RenderStats() end -- render cached data now
    end
end)

archBtn:SetScript("OnClick", function()
    helpFly:Hide(); statFly:Hide(); CW.setFly:Hide()
    if archFly:IsShown() then
        archFly:Hide()
    else
        Send("ARCH")
        RenderArchFly() -- cached list now; the ARE reply re-renders
        archFly:Show()
    end
end)

-- ---------------------------------------------------------------------------
-- rendering
-- ---------------------------------------------------------------------------
local function PendingAlloc()
    if not CW.statsPending then
        CW.statsPending = { CW.stats.alloc[1], CW.stats.alloc[2], CW.stats.alloc[3], CW.stats.alloc[4], CW.stats.alloc[5] }
    end
    return CW.statsPending
end

local function PendingSpent()
    local total = 0
    for _, v in ipairs(PendingAlloc()) do total = total + v end
    return total
end

local function LevelTag(lvl, playerLevel)
    if not lvl or lvl <= 1 then return "" end
    return (lvl > (playerLevel or 1)) and ("  |cffff4444Lv " .. lvl .. "|r")
                                       or ("  |cffaaaaaaLv " .. lvl .. "|r")
end

local function UpdateStatus()
    local s = CW.state
    local modeText = s.mode == 0 and "|cff00ccffClassless|r" or (s.mode == 1 and "|cffff8800Wildcard|r" or "|cffff0000Path not chosen|r")
    if s.mode == 0 then
        statusText:SetText(modeText .. "   Ability Essence: |cff00ff00" .. s.ae .. "|r   Talent Essence: |cff00ff00" .. s.te .. "|r")
        subStatusText:SetText("Level " .. s.level)
        bottomText:SetText("Ability Essence: |cff00ff00" .. s.ae .. "|r    Talent Essence: |cff00ff00" .. s.te .. "|r")
        respecBtn:Enable()
        if s.rebirth == 1 then CW.rebirthBtn:Show() else CW.rebirthBtn:Hide() end
        CW.buyScrollBtn:Hide()
        CW.archBtn:Show()
    elseif s.mode == 1 then
        statusText:SetText(modeText .. "   Rerolls: |cff00ff00" .. s.rerolls .. "|r")
        subStatusText:SetText("Level " .. s.level .. "   Scrolls: " .. s.scrolls .. "   Synergy chance: " .. s.chance .. "%   Pity: " .. s.pity)
        bottomText:SetText("Rerolls: |cff00ff00" .. s.rerolls .. "|r    Reroll Scrolls: |cff00ff00" .. s.scrolls .. "|r")
        respecBtn:Disable()
        if s.rebirth == 1 then CW.rebirthBtn:Show() else CW.rebirthBtn:Hide() end
        CW.archBtn:Hide(); CW.archFly:Hide()
        if s.scrollBuy == 1 then
            CW.buyScrollBtn:SetText("Buy Scroll  " .. GetCoinTextureString(s.scrollCost or 0))
            CW.buyScrollBtn:Show()
        else CW.buyScrollBtn:Hide() end
    else
        statusText:SetText(modeText)
        subStatusText:SetText("Choose your path before level " .. s.deadline .. "!")
        CW.rebirthBtn:Hide()
        CW.buyScrollBtn:Hide()
        CW.archBtn:Hide(); CW.archFly:Hide()
        bottomText:SetText("")
    end
end

local function RenderAbilPane()
    local s = CW.state
    abilPage:SetText((CW.abilPage + 1) .. " / " .. CW.abilTotal)
    for i = 1, ENTRIES do
        local e = CW.abilRows[i]
        local w = abilEntries[i]
        if e then
            w.spellId = e.id
            w.icon:SetTexture(SpellIcon(e.id))
            w.name:SetText(SpellLabel(e.id, e.rarity) .. (e.passive == 1 and " |cff888888(passive)|r" or ""))
            if e.owned == 1 then w.check:Show() else w.check:Hide() end
            local lvlText = LevelTag(e.lvl, s.level)
            local typeTag = (CW.abilSort == 5 or CW.abilType ~= 1)
                and ("|cffaaaaaa" .. (CW.BROWSE.TYPE_NAMES[e.type or 0] or "") .. "|r  ") or ""
            if s.mode == 1 then
                w.sub:SetText(typeTag .. (RARITY_NAMES[e.rarity] or "") .. lvlText)
                w.tipLine = "Dealt by Wildcard rolls"
                w:SetScript("OnClick", nil)
            else
                w.sub:SetText(typeTag .. e.cost .. " Ability Essence" .. lvlText)
                w.tipLine = e.owned == 1 and "Known" or "Click to learn"
                local id = e.id
                w:SetScript("OnClick", function()
                    if s.mode == 0 and e.owned ~= 1 and (e.lvl or 1) <= (CW.state.level or 1) then
                        Send("BUY " .. id)
                    end
                end)
            end
            w:Show()
        else
            w.spellId = nil
            w:Hide()
        end
    end
end

local function RenderTalPane()
    local s = CW.state
    local tabInfo = CW.tabs[CW.tabIndex]
    if tabInfo then
        -- count within this class, not across all 27 trees: "Mage tree 1 of 3"
        local within, count = 0, 0
        for idx, t in ipairs(CW.tabs) do
            if t.class == tabInfo.class then
                count = count + 1
                if idx == CW.tabIndex then within = count end
            end
        end
        treeText:SetText("|cffffd100" .. (CLASS_NAMES[tabInfo.class] or "?")
            .. " tree " .. within .. " of " .. count .. "|r")
    else
        treeText:SetText("No trees loaded")
    end
    talPage:SetText((CW.talPage + 1) .. " / " .. CW.talTotal)
    for i = 1, TAL_ENTRIES do
        local t = CW.talRows[i]
        local w = talEntries[i]
        if t then
            w.spellId = t.spell
            w.icon:SetTexture(SpellIcon(t.spell))
            w.name:SetText(SpellLabel(t.spell, t.rarity) .. "  |cffaaaaaa" .. t.owned .. "/" .. t.max .. "|r")
            if t.owned > 0 then w.check:Show() else w.check:Hide() end
            local tlvl = 10 + (t.row or 0) * 5
            local typeTag = CW.talSort == 5
                and ("|cffaaaaaa" .. (t.active == 1 and "Active" or "Passive") .. "|r  ") or ""
            if s.mode == 1 then
                w.sub:SetText(typeTag .. (RARITY_NAMES[t.rarity] or "") .. LevelTag(tlvl, s.level))
                w.tipLine = "Rolled at level-up"
                w:SetScript("OnClick", nil)
            else
                -- price comes from the server (CFG), not an assumption: a
                -- talent costs one point for ALL its ranks by default
                local cost = CW.talentCost or 1
                local costText = cost .. " Talent Essence"
                    .. (CW.talentFlat and " (all ranks)" or "/rank")
                w.sub:SetText(typeTag .. "Row " .. (t.row + 1) .. "  " .. costText .. LevelTag(tlvl, s.level))
                w.tipLine = t.owned >= t.max and "Maxed" or "Click to learn a rank"
                local id = t.talentId
                w:SetScript("OnClick", function()
                    if s.mode == 0 and t.owned < t.max then Send("TALBUY " .. id) end
                end)
            end
            w:Show()
        else
            w.spellId = nil
            w:Hide()
        end
    end
end

local function BuildList()
    local merged = {}
    for _, e in ipairs(CW.owned) do
        tinsert(merged, { kind = "A", id = e.id, spell = e.id, rarity = e.rarity, locked = e.locked, source = e.source })
    end
    for _, t in ipairs(CW.ownedT) do
        tinsert(merged, { kind = "T", id = t.talentId, spell = t.spell, rarity = t.rarity, rank = t.rank, max = t.max })
    end
    return merged
end

local function RenderBuild()
    local s = CW.state
    local list = BuildList()
    buildHeader:SetText("|cffffd100My Build|r  |cffaaaaaa(" .. #CW.owned .. " abilities, " .. #CW.ownedT .. " talents)|r")
    local total = math.max(1, math.ceil(#list / BUILD_ROWS))
    if CW.buildPageNo >= total then CW.buildPageNo = total - 1 end
    buildPage:SetText((CW.buildPageNo + 1) .. " / " .. total)
    for i = 1, BUILD_ROWS do
        local it = list[CW.buildPageNo * BUILD_ROWS + i]
        local r = buildRows[i]
        if it then
            r.spellId = it.spell
            r.icon:SetTexture(SpellIcon(it.spell))
            local suffix = it.kind == "T" and ("  |cffaaaaaa" .. it.rank .. "/" .. it.max .. "|r") or ""
            -- source 2 came with a talent, source 3 came free with another
            -- ability. Neither was a roll and neither cost essence, so there is
            -- nothing to reroll, unlearn or lock: each leaves with whatever
            -- brought it in. No buttons, and a note saying where it came from.
            local freebie = it.kind == "A" and (it.source == 2 or it.source == 3)
            if freebie then
                suffix = suffix .. (it.source == 3 and "  |cffaaaaaacame free|r"
                                                    or "  |cffaaaaaawith a talent|r")
            end
            r.name:SetText(SpellLabel(it.spell, it.rarity) .. suffix)
            if freebie then
                r.lockBtn:Hide()
                r.actBtn:Hide()
            elseif s.mode == 1 then
                -- lock toggle (abilities only) + die reroll
                if it.kind == "A" then
                    r.lockBtn:Show()
                    r.lockBtn.tex:SetTexture(it.locked == 1
                        and "Interface\\AddOns\\ClasslessWildcard\\lock_closed"
                        or  "Interface\\AddOns\\ClasslessWildcard\\lock_open")
                    r.lockBtn.tex:SetVertexColor(1, 1, 1, it.locked == 1 and 1 or 0.7)
                    local id = it.id
                    r.lockBtn:SetScript("OnClick", function() Send("LOCK " .. id) end)
                else
                    r.lockBtn:Hide()
                end
                r.actBtn:Show()
                r.actBtn.tex:SetTexture("Interface\\Buttons\\UI-RotationRight-Button-Up")
                r.actBtn.tex:SetVertexColor(1, 0.85, 0.3)
                local id, kind = it.id, it.kind
                r.actBtn:SetScript("OnClick", function()
                    Send((kind == "T" and "RRT " or "RR ") .. id)
                end)
                r.actBtn:SetScript("OnEnter", function(self)
                    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
                    GameTooltip:SetText("Reroll this " .. (kind == "T" and "talent" or "ability"))
                    local left = (CW.state.rerolls or 0) + (CW.state.scrolls or 0)
                    GameTooltip:AddLine("You have |cff00ff00" .. left .. "|r reroll" .. (left == 1 and "" or "s")
                        .. " (charges + scrolls).", 1, 1, 1)
                    GameTooltip:Show()
                end)
                r.actBtn:SetScript("OnLeave", function() GameTooltip:Hide() end)
            else
                r.lockBtn:Hide()
                if it.kind == "A" then
                    r.actBtn:Show()
                    r.actBtn.tex:SetTexture("Interface\\Buttons\\UI-GroupLoot-Pass-Up")
                    r.actBtn.tex:SetVertexColor(1, 1, 1)
                    local id = it.id
                    r.actBtn:SetScript("OnClick", function() Send("UNL " .. id) end)
                    r.actBtn:SetScript("OnEnter", function(self)
                        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
                        GameTooltip:SetText("Unlearn this ability")
                        GameTooltip:AddLine("Refunds the Ability Essence you paid.", 1, 1, 1)
                        GameTooltip:Show()
                    end)
                    r.actBtn:SetScript("OnLeave", function() GameTooltip:Hide() end)
                else
                    r.actBtn:Hide()
                end
            end
            r:Show()
        else
            r.spellId = nil
            r:Hide()
        end
    end
end

-- What each stat does for a Hero, and what it is doing for THIS character
-- right now. The stock tooltips describe stats by class, which says nothing
-- useful when every character is the same class -- and the numbers below come
-- from the server's own rates (sent on ST), not from hard-coded defaults, so
-- they stay honest on a realm that tuned them.
local STAT_DESC = {
    [1] = "Melee attack power and block value.",
    [2] = "Melee and ranged attack power, critical strike chance, dodge.",
    [3] = "Health.",
    [4] = "Mana, spell power, spell critical strike chance.",
    [5] = "Mana and health regeneration. Mana regeneration pauses for 5 seconds after you cast.",
}

-- What a stat is contributing right now, chassis and module together, with
-- the same per-point rates the line above it quotes. It used to show only
-- the module's share, which made Agility's melee and ranged attack power
-- read as equal while the character sheet showed them apart.
local function StatContribution(i, value)
    local s = CW.stats
    local uni = s.uniStats
    if i == 1 then
        local ap = math.floor(value * (s.strMeleeAP or 2))
        return "+" .. ap .. " melee attack power, +" .. math.floor(value * 0.5) .. " block value"
    elseif i == 2 then
        local melee = (s.agiMeleeAP or 0) + (uni and (s.apPerAgi or 0) or 0)
        local ranged = (s.agiRangedAP or 1) + (uni and (s.rapPerAgi or 0) or 0)
        local ap, rap = math.floor(value * melee), math.floor(value * ranged)
        if ap <= 0 and rap <= 0 then return nil end
        if ap > 0 then
            return "+" .. ap .. " melee and +" .. rap .. " ranged attack power"
        end
        return "+" .. rap .. " ranged attack power"
    elseif i == 4 then
        if not uni then return nil end
        local sp = math.floor(math.max(0, value - 10) * (s.spPerInt or 0))
        if sp <= 0 then return nil end
        return "+" .. sp .. " spell power"
    end
    return nil
end
CW.StatContribution = StatContribution

local function ShowStatTooltip(row, i)
    local total = 0
    if UnitStat then
        local _, stat = UnitStat("player", i)
        total = stat or 0
    end
    GameTooltip:SetOwner(row, "ANCHOR_RIGHT")
    GameTooltip:AddLine(STAT_NAMES[i], 1, 0.82, 0)
    GameTooltip:AddLine(STAT_DESC[i], 1, 1, 1, true)
    GameTooltip:AddLine(" ")
    GameTooltip:AddLine("Each point: " .. StatPerPoint(i), 1, 0.82, 0, true)
    GameTooltip:AddLine(" ")
    GameTooltip:AddDoubleLine("Current total", tostring(total), 0.8, 0.8, 0.8, 1, 1, 1)

    local contrib = StatContribution(i, total)
    if contrib then
        GameTooltip:AddLine("From your " .. total .. " " .. STAT_NAMES[i] .. ": " .. contrib, 0.4, 1, 0.4, true)
    end

    -- what the points you have allocated (applied or not) are worth
    local s = CW.stats
    local pending = PendingAlloc()
    local applied = (s.alloc[i] or 0) * (s.perPoint or 1)
    if applied > 0 then
        GameTooltip:AddDoubleLine("Allocated by you", "+" .. applied, 0.8, 0.8, 0.8, 0.4, 1, 0.4)
    end
    local unapplied = ((pending[i] or 0) - (s.alloc[i] or 0)) * (s.perPoint or 1)
    if unapplied ~= 0 then
        local sign = unapplied > 0 and "+" or ""
        GameTooltip:AddDoubleLine("Pending (press Apply)", sign .. unapplied, 0.8, 0.8, 0.8, 1, 0.82, 0)
        local after = StatContribution(i, total + unapplied)
        if after then
            GameTooltip:AddLine("After applying: " .. after, 1, 0.82, 0, true)
        end
    end
    GameTooltip:Show()
end

local function RenderStats()
    local pending = PendingAlloc()
    local spent = PendingSpent()
    local unspent = CW.stats.budget - spent
    statTitle:SetText("Primary Stats: |cff00ff00" .. unspent .. "|r of " .. CW.stats.budget .. " unspent")
    for i = 1, 5 do
        local r = statRows[i]
        r.label:SetText("|cffffd100" .. STAT_NAMES[i] .. "|r  " .. pending[i] .. " pts = +" .. (pending[i] * CW.stats.perPoint))
        r.plus:SetScript("OnClick", function()
            if PendingSpent() < CW.stats.budget then
                PendingAlloc()[i] = PendingAlloc()[i] + 1
                RenderStats()
            end
        end)
        r.minus:SetScript("OnClick", function()
            if PendingAlloc()[i] > 0 then
                PendingAlloc()[i] = PendingAlloc()[i] - 1
                RenderStats()
            end
        end)
        r:EnableMouse(true)
        r:SetScript("OnEnter", function(self) ShowStatTooltip(self, i) end)
        r:SetScript("OnLeave", function() GameTooltip:Hide() end)
        -- the +/- buttons sit on top of the row and would otherwise swallow the
        -- hover, leaving most of the row tooltip-less
        r.plus:SetScript("OnEnter", function() ShowStatTooltip(r, i) end)
        r.plus:SetScript("OnLeave", function() GameTooltip:Hide() end)
        r.minus:SetScript("OnEnter", function() ShowStatTooltip(r, i) end)
        r.minus:SetScript("OnLeave", function() GameTooltip:Hide() end)
    end
end

local function RenderList()
    UpdateClassStrip()
    RenderAbilPane()
    RenderTalPane()
    RenderBuild()
    if statFly:IsShown() then RenderStats() end
    UpdateStatus()
end
CW.RenderStats = RenderStats

statApply:SetScript("OnClick", function()
    local p = PendingAlloc()
    Send("STATSETALL " .. p[1] .. " " .. p[2] .. " " .. p[3] .. " " .. p[4] .. " " .. p[5])
end)
statReset:SetScript("OnClick", function()
    CW.statsPending = nil
    RenderStats()
end)

-- everything is on one screen now; SetTab(key) survives as "refresh all data"
-- (and opens the matching flyout for the old STAT key)
function CW.SetTab(key)
    CW.tab = key or CW.tab
    RequestAbil(CW.abilPage)
    if #CW.tabs == 0 then
        Send("TABS")
    else
        RequestTal(CW.talPage)
    end
    Send("OWN"); Send("OWNT")
    if key == "STAT" then Send("STATS"); statFly:Show() end
    if statFly:IsShown() then Send("STATS") end
    RenderList()
end

-- pane pagers / tree selector ------------------------------------------------------
abilPrev:SetScript("OnClick", function()
    if CW.abilPage > 0 then RequestAbil(CW.abilPage - 1) end
end)
abilNext:SetScript("OnClick", function()
    if CW.abilPage + 1 < CW.abilTotal then RequestAbil(CW.abilPage + 1) end
end)
treeLeft:SetScript("OnClick", function()
    if #CW.tabs > 0 then
        CW.tabIndex = CW.tabIndex > 1 and CW.tabIndex - 1 or #CW.tabs
        RequestTal(0)
    end
end)
treeRight:SetScript("OnClick", function()
    if #CW.tabs > 0 then
        CW.tabIndex = CW.tabIndex < #CW.tabs and CW.tabIndex + 1 or 1
        RequestTal(0)
    end
end)
talPrev:SetScript("OnClick", function()
    if CW.talPage > 0 then
        RequestTal(CW.talPage - 1)
    end
end)
talNext:SetScript("OnClick", function()
    if CW.talPage + 1 < CW.talTotal then
        RequestTal(CW.talPage + 1)
    end
end)
buildPrev:SetScript("OnClick", function()
    if CW.buildPageNo > 0 then CW.buildPageNo = CW.buildPageNo - 1; RenderBuild() end
end)
buildNext:SetScript("OnClick", function()
    CW.buildPageNo = CW.buildPageNo + 1; RenderBuild()
end)

-- ---------------------------------------------------------------------------
-- onboarding wizard
-- ---------------------------------------------------------------------------
local wizard = CreateFrame("Frame", "ClasslessWildcardWizard", UIParent)
wizard:SetWidth(420); wizard:SetHeight(300)
wizard:SetPoint("CENTER")
-- own clean dialog backdrop (NOT the main panel's baked pane art)
wizard:SetBackdrop({
    bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
    edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
    tile = true, tileSize = 32, edgeSize = 32,
    insets = { left = 11, right = 12, top = 12, bottom = 11 },
})
wizard:SetFrameStrata("FULLSCREEN_DIALOG")
wizard:EnableMouse(true)
wizard:Hide()

local wizCrest = wizard:CreateTexture(nil, "ARTWORK")
wizCrest:SetWidth(30); wizCrest:SetHeight(30)
wizCrest:SetPoint("TOPLEFT", 16, -14)
wizCrest:SetTexture("Interface\\AddOns\\ClasslessWildcard\\icon")

local wizTitle = wizard:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
wizTitle:SetPoint("TOP", 0, -20)
wizTitle:SetText("Choose Your Path, Hero")

local wizText = wizard:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
wizText:SetPoint("TOP", 0, -46)
wizText:SetWidth(370)
local WIZ_PATH_TEXT = "Every spell and talent of every class awaits. You have no class of your own, only a shared chassis (resource bar and base stats). Will you choose each ability yourself, or let the Wildcard decide your fate?"
wizText:SetText(WIZ_PATH_TEXT)

local wizClassless = CreateFrame("Button", nil, wizard, "UIPanelButtonTemplate")
wizClassless:SetWidth(340); wizClassless:SetHeight(30)
wizClassless:SetPoint("TOP", 0, -108)
wizClassless:SetText("|cff00ccffClassless|r: pick every ability yourself")
wizClassless:SetScript("OnClick", function() Send("MODE 0"); Send("ARCH") end)

local wizWildcard = CreateFrame("Button", nil, wizard, "UIPanelButtonTemplate")
wizWildcard:SetWidth(340); wizWildcard:SetHeight(30)
wizWildcard:SetPoint("TOP", 0, -146)
wizWildcard:SetText("|cffff8800Wildcard|r: random abilities, reroll the rest")
wizWildcard:SetScript("OnClick", function()
    Send("MODE 1")
    wizard:Hide()
    -- the STARTING HAND opens next (pendingHand); the main panel waits
    -- until the player keeps their hand
end)

local wizLater = CreateFrame("Button", nil, wizard, "UIPanelButtonTemplate")
wizLater:SetWidth(120); wizLater:SetHeight(22)
wizLater:SetPoint("BOTTOM", 0, 14)
wizLater:SetText("Decide later")
wizLater:SetScript("OnClick", function() wizard:Hide() end)

-- Page 2: archetype rows (shown after choosing Classless). The wizard grows
-- to fit them and shrinks back when page 1 is shown again.
local WIZ_W, WIZ_H = 420, 300
local WIZ_ARCH_W = 480
local wizList = MakeArchList(wizard, "ClasslessWildcardWizardArchetypes", WIZ_ARCH_W - 40, "Choose")
local archSkip = CreateFrame("Button", nil, wizard, "UIPanelButtonTemplate")
archSkip:SetWidth(180); archSkip:SetHeight(22)
archSkip:SetPoint("BOTTOM", 0, 14)
archSkip:SetText("Start with an empty slate")
archSkip:Hide()
archSkip:SetScript("OnClick", function()
    wizard:Hide()
    frame:Show()
    CW.SetTab("ABIL")
end)

local function ShowPathChoice()
    wizard:SetWidth(WIZ_W); wizard:SetHeight(WIZ_H)
    wizTitle:SetText("Choose Your Path, Hero")
    wizText:SetWidth(370)
    wizText:SetText(WIZ_PATH_TEXT)
    wizClassless:Show(); wizWildcard:Show(); wizLater:Show()
    wizList.scroll:Hide()
    for _, r in ipairs(wizList.rows) do r:Hide() end
    archSkip:Hide()
    wizard:Show()
end

local function ShowArchetypeChoices()
    wizTitle:SetText("Pick a Starter Archetype")
    wizText:SetWidth(WIZ_ARCH_W - 50)
    wizClassless:Hide(); wizWildcard:Hide(); wizLater:Hide()
    local list = CW.archetypes or {}
    if #list > 0 then
        wizText:SetText("An archetype is a build you follow: its abilities and talents are bought for you as you level, all the way to 80. Change or stop it later from the Archetypes button.")
    else
        wizText:SetText("No archetypes are configured on this realm.")
    end
    wizard:SetWidth(WIZ_ARCH_W)
    local top = 46 + TextHeight(wizText) + 14
    local shown, used = FillArchRows(wizList, list, function(arch)
        Send("ARCHAPPLY " .. arch.id)
        wizard:Hide()
        frame:Show()
        CW.SetTab("HERO")
    end, 20, top)
    wizard:SetHeight(top + math.max(used, ARCH_ROW_H) + 52)
    archSkip:Show()
    wizard:Show()
end
CW.wizard, CW.wizArchRows, CW.wizArchList, CW.wizArchSkip = wizard, wizList.rows, wizList, archSkip
CW.wizClassless, CW.wizWildcard, CW.wizLater = wizClassless, wizWildcard, wizLater
CW.wizTitle, CW.wizText = wizTitle, wizText
CW.ShowPathChoice = ShowPathChoice

-- ---------------------------------------------------------------------------
-- universal resource bars: the client tracks mana/rage/energy for every
-- character; the default UI only draws the chassis bar. These mini-bars show
-- the other pools (movable; /cwbars toggles them).
-- ---------------------------------------------------------------------------
local POWER_INFO = {
    { index = 0, key = "mana",   name = "Mana",   r = 0.25, g = 0.45, b = 1.00 },
    { index = 1, key = "rage",   name = "Rage",   r = 1.00, g = 0.25, b = 0.25 },
    { index = 3, key = "energy", name = "Energy", r = 1.00, g = 0.90, b = 0.25 },
}

-- Every layout number for this frame in one place, and every row centred from
-- them instead of placed with a hand-written offset. The old offsets are what
-- made the block look crooked: the combo row sat 12px from the left edge and
-- 56 from the right, and the rune row 14 from the left and 18 from the right
-- with its rings hanging up into the row above.
--
-- The pip sizes are taken from the client's own frames rather than from taste.
-- ComboFrame's point is a 12x16 cell holding a 12x12 socket, with a 6x5 gem
-- inside it drawn 8 wide and a 14x16 star flashed over it on the way in.
-- RuneFrame's button is 18x18 with the rune AND its ring both drawn at 24, so
-- the art is meant to overhang its cell; the old code drew the rune at 18 and
-- the ring at 26, which is why the two never sat together. Everything here is
-- those proportions, the combo art at 1.5x so a pip reads at the same weight
-- as a rune.
local BARS = {
    W = 160, PAD = 7, TOP = 7, BOTTOM = 8, GAP = 6,
    BAR_H = 14, BAR_STEP = 17,
    CP = 18, CP_GAP = 5, CP_GEM_W = 12, CP_GEM_H = 8,
    CP_SHINE_W = 21, CP_SHINE_H = 24, CP_LINGER = 1.5,
    RUNE = 18, RUNE_GAP = 4, RUNE_ART = 24, RUNE_OVER = 3,
    RUNE_SHINE_W = 40, RUNE_SHINE_H = 24,
    RUNIC_H = 13, FLASH = 0.45,
}

-- Every row the frame can draw, in the order the settings panel lists them.
BARS.ROWS = {
    { key = "mana",   label = "Mana" },
    { key = "rage",   label = "Rage" },
    { key = "energy", label = "Energy" },
    { key = "runes",  label = "Runes" },
    { key = "runic",  label = "Runic Power" },
    { key = "combo",  label = "Combo Points" },
}

-- A row the player has switched off is stored by its presence in barsOff, so a
-- saved-variables file written before this existed, and a brand new one, both
-- start with every row on.
function CW.BarRowOn(key)
    ClasslessWildcardDB = ClasslessWildcardDB or {}
    local off = ClasslessWildcardDB.barsOff
    return not (off and off[key])
end

function CW.SetBarRow(key, on)
    ClasslessWildcardDB = ClasslessWildcardDB or {}
    ClasslessWildcardDB.barsOff = ClasslessWildcardDB.barsOff or {}
    ClasslessWildcardDB.barsOff[key] = (not on) or nil
    CW.UpdateBarsVisibility()
end

-- x of the first item in a row of `count` items `w` wide, `gap` apart, so the
-- row ends up centred in the frame.
function CW.RowStart(count, w, gap)
    return math.floor((BARS.W - (count * w + (count - 1) * gap)) / 2 + 0.5)
end

local barsFrame = CreateFrame("Frame", "ClasslessWildcardBars", UIParent)
barsFrame:SetWidth(BARS.W); barsFrame:SetHeight(58)
if PlayerFrame then
    -- dock under the player frame so ALL pools read as one unit frame
    barsFrame:SetPoint("TOPLEFT", PlayerFrame, "BOTTOMLEFT", 100, 24)
else
    barsFrame:SetPoint("TOPLEFT", 20, -180)
end
barsFrame:SetBackdrop({
    bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
    edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
    tile = true, tileSize = 16, edgeSize = 12,
    insets = { left = 3, right = 3, top = 3, bottom = 3 },
})
barsFrame:SetMovable(true); barsFrame:EnableMouse(true)
barsFrame:SetClampedToScreen(true)

function CW.BarsDragStart()
    ClasslessWildcardDB = ClasslessWildcardDB or {}
    if ClasslessWildcardDB.barsLocked then return end
    barsFrame.dragging = true
    barsFrame:StartMoving()
end

-- Where you put it is where it stays. The frame was movable but the position
-- was never written down, so every login threw it back under the player frame.
function CW.BarsDragStop()
    barsFrame:StopMovingOrSizing()
    ClasslessWildcardDB = ClasslessWildcardDB or {}
    local point, _rel, relPoint, x, y = barsFrame:GetPoint()
    if point then
        ClasslessWildcardDB.barsPos = { point = point, relPoint = relPoint, x = x, y = y }
    end
end

barsFrame:RegisterForDrag("LeftButton")
barsFrame:SetScript("OnDragStart", CW.BarsDragStart)
barsFrame:SetScript("OnDragStop", CW.BarsDragStop)
barsFrame:Hide()

-- Hand a drag on a child back to the frame. Nearly every pixel of it is
-- covered by something that wants the mouse -- the pools answer clicks, the
-- pip rows and the runic bar answer hovers -- so without this there is almost
-- nothing left to grab the frame by.
function CW.BarsDragProxy(f)
    f:RegisterForDrag("LeftButton")
    f:SetScript("OnDragStart", CW.BarsDragStart)
    f:SetScript("OnDragStop", CW.BarsDragStop)
end

-- Put it back where the player left it. Runs on PLAYER_ENTERING_WORLD, because
-- saved variables are not loaded yet while this file is being read.
function CW.RestoreBarsPosition()
    ClasslessWildcardDB = ClasslessWildcardDB or {}
    local pos = ClasslessWildcardDB.barsPos
    if not pos or not pos.point then return end
    barsFrame:ClearAllPoints()
    barsFrame:SetPoint(pos.point, UIParent, pos.relPoint or pos.point, pos.x or 0, pos.y or 0)
end

function CW.ResetBarsPosition()
    ClasslessWildcardDB = ClasslessWildcardDB or {}
    ClasslessWildcardDB.barsPos = nil
    barsFrame:ClearAllPoints()
    if PlayerFrame then
        barsFrame:SetPoint("TOPLEFT", PlayerFrame, "BOTTOMLEFT", 100, 24)
    else
        barsFrame:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 20, -180)
    end
end

-- The hairline goes in front of the first section under the pools, whichever
-- of the three that turns out to be.
function CW.BarsRule(y)
    if not barsFrame.needRule then return y end
    barsFrame.needRule = false
    barsFrame.divider:ClearAllPoints()
    barsFrame.divider:SetPoint("TOPLEFT", BARS.PAD, -y)
    barsFrame.divider:Show()
    return y + 1 + BARS.GAP
end

-- The client flashes a star when a combo point lands and again when a rune
-- comes back. Same texture, same reason: a pip quietly changing colour in the
-- corner of the screen is easy to play right past.
function CW.FlashPip(tex, dur)
    if not tex then return end
    tex.fadeLeft = dur or BARS.FLASH
    tex.fadeFor = tex.fadeLeft
    tex:SetAlpha(1)
    barsFrame.flashes = barsFrame.flashes or {}
    for _, t in ipairs(barsFrame.flashes) do
        if t == tex then return end
    end
    table.insert(barsFrame.flashes, tex)
end

local powerBars = {}
for i, info in ipairs(POWER_INFO) do
    local bar = CreateFrame("StatusBar", nil, barsFrame)
    bar:SetWidth(BARS.W - BARS.PAD * 2); bar:SetHeight(BARS.BAR_H)
    bar:SetPoint("TOPLEFT", BARS.PAD, -BARS.TOP - (i - 1) * BARS.BAR_STEP)
    bar:SetStatusBarTexture("Interface\\TargetingFrame\\UI-StatusBar")
    bar:SetStatusBarColor(info.r, info.g, info.b)
    bar:SetMinMaxValues(0, 100)
    -- an empty bar used to show the dialog backdrop straight through it, so a
    -- pool at zero read as a hole in the frame instead of as an empty bar
    bar.bg = bar:CreateTexture(nil, "BACKGROUND")
    bar.bg:SetAllPoints(bar)
    bar.bg:SetTexture("Interface\\TargetingFrame\\UI-StatusBar")
    bar.bg:SetVertexColor(info.r * 0.22, info.g * 0.22, info.b * 0.22, 0.9)
    bar.label = bar:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    bar.label:SetPoint("CENTER", 0, 0)
    bar.label:SetShadowColor(0, 0, 0, 1)
    bar.label:SetShadowOffset(1, -1)
    bar.powerIndex = info.index
    bar.powerName = info.name
    bar.rowKey = info.key
    -- click a pool to make it the MAIN bar on the default unit frame
    bar:EnableMouse(true)
    CW.BarsDragProxy(bar)
    bar:SetScript("OnMouseDown", function() barsFrame.dragging = false end)
    bar:SetScript("OnMouseUp", function(self)
        -- the click that ends a drag is not a click on the bar
        if barsFrame.dragging then barsFrame.dragging = false return end
        Send("BAR " .. self.powerIndex)
    end)
    bar:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:AddLine(self.powerName)
        GameTooltip:AddLine("Click to make this your main resource bar", 1, 1, 1)
        GameTooltip:AddLine("Drag the frame to move it. /cwbars lock pins it in place.",
            0.7, 0.7, 0.7, true)
        GameTooltip:Show()
    end)
    bar:SetScript("OnLeave", function() GameTooltip:Hide() end)
    powerBars[i] = bar
end
CW.powerBars = powerBars
CW.barsFrame = barsFrame

-- A hairline under the pools. Combo points and runes are not more resources,
-- and with nothing between them the block read as one long list of bars.
barsFrame.divider = barsFrame:CreateTexture(nil, "ARTWORK")
barsFrame.divider:SetTexture(1, 1, 1, 0.14)
barsFrame.divider:SetWidth(BARS.W - BARS.PAD * 2)
barsFrame.divider:SetHeight(1)
barsFrame.divider:Hide()

-- Combo points, drawn the way ComboFrame draws them: an always-there socket,
-- a gem that lights inside it, and a star that flashes on the way in. Like
-- ComboFrame the row only exists while there are points to show, so every
-- character that never builds one is not carrying an empty row around.
local comboDots = {}
for i = 1, 5 do
    local bg = barsFrame:CreateTexture(nil, "ARTWORK")
    bg:SetWidth(BARS.CP); bg:SetHeight(BARS.CP)
    bg:SetTexture("Interface\\ComboFrame\\ComboPoint")
    bg:SetTexCoord(0, 0.375, 0, 0.75)      -- the 12x12 socket, without its 4 blank rows
    bg:Hide()

    local shine = barsFrame:CreateTexture(nil, "OVERLAY")
    shine:SetWidth(BARS.CP_GEM_W); shine:SetHeight(BARS.CP_GEM_H)
    shine:SetPoint("CENTER", bg, "CENTER", 0, 0)
    shine:SetTexture("Interface\\ComboFrame\\ComboPoint")
    shine:SetTexCoord(0.375, 0.5625, 0.1875, 0.5)   -- the 6x5 gem, likewise
    shine:SetAlpha(0)
    shine:Hide()

    local flash = barsFrame:CreateTexture(nil, "OVERLAY")
    flash:SetWidth(BARS.CP_SHINE_W); flash:SetHeight(BARS.CP_SHINE_H)
    flash:SetPoint("CENTER", bg, "CENTER", 0, 0)
    flash:SetTexture("Interface\\ComboFrame\\ComboPoint")
    flash:SetTexCoord(0.5625, 1, 0, 1)
    flash:SetBlendMode("ADD")
    flash:SetAlpha(0)

    comboDots[i] = { bg = bg, shine = shine, flash = flash, lit = false }
end
CW.comboDots = comboDots

-- Runes. The stock UI draws the rune bar only for real Death Knight
-- characters, so a Hero with rune-cost abilities would have no way to see
-- which runes are up; the server mirrors the block over the addon channel
-- ("RU|runic|max|type,cooldown x6") and these draw it.
--
-- The game's own rune art, which every 3.3.5a client ships in locale-enUS.MPQ
-- (verified against the archive stack rather than assumed). The solid colours
-- below are the fallback for a client whose archives are incomplete, since a
-- missing texture would otherwise draw nothing at all.
local RUNE_TEXTURE = {
    [0] = "Interface\\PlayerFrame\\UI-PlayerFrame-Deathknight-Blood",
    [1] = "Interface\\PlayerFrame\\UI-PlayerFrame-Deathknight-Unholy",
    [2] = "Interface\\PlayerFrame\\UI-PlayerFrame-Deathknight-Frost",
    [3] = "Interface\\PlayerFrame\\UI-PlayerFrame-Deathknight-Death",
}
local RUNE_COLOR = {
    [0] = { 0.80, 0.10, 0.10 },   -- blood
    [1] = { 0.30, 0.70, 0.20 },   -- unholy
    [2] = { 0.20, 0.55, 0.95 },   -- frost
    [3] = { 0.70, 0.35, 0.90 },   -- death
}

local runePips = {}
for i = 1, 6 do
    local holder = CreateFrame("Frame", nil, barsFrame)
    holder:SetWidth(BARS.RUNE); holder:SetHeight(BARS.RUNE)

    -- rune and ring are both drawn larger than the cell and centred on it,
    -- exactly as RuneFrame does it, so they sit inside one another
    local rune = holder:CreateTexture(nil, "ARTWORK")
    rune:SetWidth(BARS.RUNE_ART); rune:SetHeight(BARS.RUNE_ART)
    rune:SetPoint("CENTER", holder, "CENTER", 0, 0)

    local ring = holder:CreateTexture(nil, "OVERLAY")
    ring:SetWidth(BARS.RUNE_ART); ring:SetHeight(BARS.RUNE_ART)
    ring:SetPoint("CENTER", holder, "CENTER", 0, 0)
    if not ring:SetTexture("Interface\\PlayerFrame\\UI-PlayerFrame-Deathknight-Ring") then
        ring:Hide()
    end

    local flash = holder:CreateTexture(nil, "OVERLAY")
    flash:SetWidth(BARS.RUNE_SHINE_W); flash:SetHeight(BARS.RUNE_SHINE_H)
    flash:SetPoint("CENTER", holder, "CENTER", 0, 0)
    flash:SetTexture("Interface\\ComboFrame\\ComboPoint")
    flash:SetTexCoord(0.5625, 1, 0, 1)
    flash:SetBlendMode("ADD")
    flash:SetAlpha(0)

    holder:Hide()
    runePips[i] = { frame = holder, rune = rune, ring = ring, flash = flash, ready = false }
end
CW.runePips = runePips

-- Same width and inset as the pools above it, which it was not: it was 10px
-- narrower and 5px further in, so the Death Knight block sat visibly off. It
-- also now carries its value, like every other pool in the frame.
local runicBar = CreateFrame("StatusBar", nil, barsFrame)
runicBar:SetWidth(BARS.W - BARS.PAD * 2); runicBar:SetHeight(BARS.RUNIC_H)
runicBar:SetStatusBarTexture("Interface\\TargetingFrame\\UI-StatusBar")
runicBar:SetStatusBarColor(0.00, 0.82, 1.00)
runicBar:SetMinMaxValues(0, 1)
runicBar:SetValue(0)
runicBar:EnableMouse(true)
runicBar:Hide()
local runicBg = runicBar:CreateTexture(nil, "BACKGROUND")
runicBg:SetAllPoints(runicBar)
runicBg:SetTexture("Interface\\TargetingFrame\\UI-StatusBar")
runicBg:SetVertexColor(0.00, 0.18, 0.22, 0.9)
runicBar.label = runicBar:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
runicBar.label:SetPoint("CENTER", 0, 0)
runicBar.label:SetShadowColor(0, 0, 0, 1)
runicBar.label:SetShadowOffset(1, -1)
CW.BarsDragProxy(runicBar)
runicBar:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:AddLine("Runic Power")
    GameTooltip:AddLine("Spending runes builds it. Abilities that cost it spend it.",
        1, 1, 1, true)
    GameTooltip:Show()
end)
runicBar:SetScript("OnLeave", function() GameTooltip:Hide() end)
CW.runicBar = runicBar

-- Invisible catchers so the two picture rows can answer a hover the way the
-- bars above them do, and can be dragged like the rest of the frame.
for _, key in ipairs({ "comboMouse", "runeMouse" }) do
    local m = CreateFrame("Frame", nil, barsFrame)
    m:EnableMouse(true)
    m:Hide()
    m:SetScript("OnLeave", function() GameTooltip:Hide() end)
    CW.BarsDragProxy(m)
    barsFrame[key] = m
end
barsFrame.comboMouse:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:AddLine("Combo Points")
    GameTooltip:AddLine(string.format("%d of 5 on your target.", barsFrame.comboCount or 0),
        1, 1, 1)
    GameTooltip:AddLine("Anything that builds them builds them, whatever else you have picked.",
        0.7, 0.7, 0.7, true)
    GameTooltip:Show()
end)
barsFrame.runeMouse:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:AddLine("Runes")
    GameTooltip:AddLine(string.format("%d of 6 ready.", barsFrame.runesReady or 0), 1, 1, 1)
    GameTooltip:AddLine("A dimmed rune is recharging. Spending one builds runic power.",
        0.7, 0.7, 0.7, true)
    GameTooltip:Show()
end)

function CW.RefreshBars()
    local displayed = UnitPowerType("player")
    local shown, rows = 0, 0
    -- y walks down the frame, so a row that is not there costs nothing and
    -- everything below it closes up instead of leaving a gap
    local y = BARS.TOP
    for _, bar in ipairs(powerBars) do
        local maxPower = UnitPowerMax("player", bar.powerIndex)
        -- with universal resources active, ALWAYS render all three pools --
        -- a 0/0 bar is a visible bug report, not something to hide. Switching
        -- one off in the settings is the one exception, because that is the
        -- player saying they know.
        local want = CW.BarRowOn(bar.rowKey)
            and ((maxPower and maxPower > 0) or CW.state.universalResources == 1)
        if want then
            maxPower = maxPower or 0
            local cur = UnitPower("player", bar.powerIndex) or 0
            bar:SetMinMaxValues(0, math.max(1, maxPower))
            bar:SetValue(cur)
            -- the pool currently shown as the MAIN bar gets a gold marker
            local marker = (bar.powerIndex == displayed) and "|cffffd100\194\187|r " or ""
            bar.label:SetText(marker .. bar.powerName .. ": " .. cur .. "/" .. maxPower)
            shown = shown + 1
            bar:ClearAllPoints()
            bar:SetPoint("TOPLEFT", BARS.PAD, -y)
            bar:Show()
            y = y + BARS.BAR_STEP
        else
            bar:Hide()
        end
    end
    if shown > 0 then y = y - (BARS.BAR_STEP - BARS.BAR_H) end
    rows = shown
    barsFrame.needRule = shown > 0

    -- runes, in their own section under the pools
    local runes = CW.state.runes
    local ready = 0
    if runes and CW.BarRowOn("runes") then
        y = CW.BarsRule(y + BARS.GAP)
        y = y + BARS.RUNE_OVER          -- the art hangs outside its cell
        local x = CW.RowStart(6, BARS.RUNE, BARS.RUNE_GAP)
        for i = 1, 6 do
            local r = runes[i]
            local pip = runePips[i]
            if r then
                local kind = r.kind or 0
                -- a rune on cooldown is dimmed rather than hidden, so the row
                -- never changes width and the eye can count what is missing
                local up = r.ready and true or false
                if not pip.rune:SetTexture(RUNE_TEXTURE[kind] or RUNE_TEXTURE[0]) then
                    local c = RUNE_COLOR[kind] or RUNE_COLOR[0]
                    pip.rune:SetTexture(c[1], c[2], c[3])
                end
                pip.rune:SetVertexColor(1, 1, 1, 1)
                pip.rune:SetAlpha(up and 1 or 0.30)
                if pip.rune.SetDesaturated then
                    pip.rune:SetDesaturated(not up)
                end
                -- the client tints the ring down to .6 grey; a spent rune's
                -- ring goes darker still so the row reads at a glance
                pip.ring:SetVertexColor(0.6, 0.6, 0.6, 1)
                pip.ring:SetAlpha(up and 1 or 0.35)
                if up and not pip.ready then CW.FlashPip(pip.flash) end
                pip.ready = up
                if up then ready = ready + 1 end
                pip.frame:ClearAllPoints()
                pip.frame:SetPoint("TOPLEFT", barsFrame, "TOPLEFT",
                    x + (i - 1) * (BARS.RUNE + BARS.RUNE_GAP), -y)
                pip.frame:Show()
            else
                pip.frame:Hide()
                pip.ready = false
            end
        end
        barsFrame.runeMouse:ClearAllPoints()
        barsFrame.runeMouse:SetPoint("TOPLEFT", BARS.PAD, -(y - BARS.RUNE_OVER))
        barsFrame.runeMouse:SetWidth(BARS.W - BARS.PAD * 2)
        barsFrame.runeMouse:SetHeight(BARS.RUNE + BARS.RUNE_OVER * 2)
        barsFrame.runeMouse:Show()
        y = y + BARS.RUNE + BARS.RUNE_OVER
        rows = rows + 1
    else
        for i = 1, 6 do
            runePips[i].frame:Hide()
            runePips[i].ready = false
        end
        barsFrame.runeMouse:Hide()
    end
    barsFrame.runesReady = ready

    -- Runic power stands on its own rather than inside the rune block: a
    -- player who wants the pool but not the six pips gets exactly that.
    local runicMax = CW.state.runicMax or 0
    if runicMax > 0 and CW.BarRowOn("runic") then
        local cur = CW.state.runic or 0
        -- close under the pips when they are there, its own section when not
        if rows > shown then y = y + 4 else y = CW.BarsRule(y + BARS.GAP) end
        runicBar:ClearAllPoints()
        runicBar:SetPoint("TOPLEFT", BARS.PAD, -y)
        runicBar:SetMinMaxValues(0, runicMax)
        runicBar:SetValue(cur)
        runicBar.label:SetText("Runic Power: " .. cur .. "/" .. runicMax)
        runicBar:Show()
        y = y + BARS.RUNIC_H
        rows = rows + 1
    else
        runicBar:Hide()
    end

    -- The stock client hides combo points for non-rogue classes (Wow.exe gates
    -- GetComboPoints), so the server mirrors the real count over the addon
    -- channel ("CP|n"). Use whichever source knows more.
    local cp = CW.state.comboPoints or 0
    local ok, ccp = pcall(GetComboPoints, "player", "target")
    if ok and ccp and ccp > cp then cp = ccp end
    barsFrame.comboCount = cp
    local now = GetTime()
    if cp > 0 then barsFrame.cpAt = now end
    -- hold the row a moment after the last point is spent, so a finisher shows
    -- the sockets going dark instead of the row vanishing mid-swing
    local showCombo = CW.BarRowOn("combo")
        and (cp > 0 or (barsFrame.cpAt and now - barsFrame.cpAt < BARS.CP_LINGER))
    if showCombo then
        y = CW.BarsRule(y + BARS.GAP)
        local x = CW.RowStart(5, BARS.CP, BARS.CP_GAP)
        for i = 1, 5 do
            local dot = comboDots[i]
            local lit = i <= cp
            dot.bg:ClearAllPoints()
            dot.bg:SetPoint("TOPLEFT", x + (i - 1) * (BARS.CP + BARS.CP_GAP), -y)
            dot.bg:Show()
            dot.shine:SetAlpha(lit and 1 or 0)
            dot.shine:Show()
            if lit and not dot.lit then CW.FlashPip(dot.flash) end
            dot.lit = lit
        end
        barsFrame.comboMouse:ClearAllPoints()
        barsFrame.comboMouse:SetPoint("TOPLEFT", x, -y)
        barsFrame.comboMouse:SetWidth(5 * BARS.CP + 4 * BARS.CP_GAP)
        barsFrame.comboMouse:SetHeight(BARS.CP)
        barsFrame.comboMouse:Show()
        y = y + BARS.CP
        rows = rows + 1
    else
        for i = 1, 5 do
            comboDots[i].bg:Hide()
            comboDots[i].shine:Hide()
            comboDots[i].lit = false
        end
        barsFrame.comboMouse:Hide()
    end

    if barsFrame.needRule then barsFrame.divider:Hide() end
    barsFrame.rowsShown = rows
    barsFrame:SetHeight(y + BARS.BOTTOM)
    return shown
end

function CW.UpdateBarsVisibility()
    ClasslessWildcardDB = ClasslessWildcardDB or {}
    -- universalResources is 0 until the server's first state packet arrives, so
    -- it doubles as the "do we know anything yet" test. It used to also require
    -- mode ~= 255, which was wrong: 255 is Unchosen, and a brand new character
    -- IS unchosen until they pick a path. The server gives every Hero all three
    -- pools at login regardless of mode, so gating on it hid the bars for
    -- exactly the characters seeing them for the first time.
    local enabled = CW.state.universalResources == 1
        and ClasslessWildcardDB.hideBars ~= true
    if enabled then
        barsFrame:Show()
        CW.RefreshBars()
        -- every row switched off is the same as the frame switched off; an
        -- empty box is not a resource display
        if (barsFrame.rowsShown or 0) == 0 then barsFrame:Hide() end
    else
        barsFrame:Hide()
    end
    if not barsFrame:IsShown() and barsFrame.flashes then
        -- nothing fades while the frame is down, so a flash caught mid-way
        -- would still be burning when it comes back
        for _, tex in ipairs(barsFrame.flashes) do tex:SetAlpha(0) end
        barsFrame.flashes = nil
    end
end

-- The tick lives on its own always-shown frame rather than on the bar frame.
-- The bar frame hides itself when it has nothing to draw -- every row off, or
-- only combo points and none on the target -- and a hidden frame gets no
-- OnUpdate, so driving the poll from it would mean it could never come back.
CW.barsTicker = CreateFrame("Frame", nil, UIParent)
local barsElapsed = 0
CW.barsTicker:SetScript("OnUpdate", function(self, elapsed)
    elapsed = elapsed or 0
    -- the gain flashes fade every frame; the numbers only need five reads a
    -- second, and re-laying the whole frame out that often is wasteful
    local flashes = barsFrame.flashes
    if flashes and #flashes > 0 then
        for i = #flashes, 1, -1 do
            local tex = flashes[i]
            tex.fadeLeft = (tex.fadeLeft or 0) - elapsed
            if tex.fadeLeft <= 0 then
                tex:SetAlpha(0)
                table.remove(flashes, i)
            else
                tex:SetAlpha(tex.fadeLeft / (tex.fadeFor or BARS.FLASH))
            end
        end
    end
    barsElapsed = barsElapsed + elapsed
    if barsElapsed >= 0.2 then
        barsElapsed = 0
        CW.UpdateBarsVisibility()
    end
end)

-- ---------------------------------------------------------------------------
-- settings flyout
--
-- Which of the resource rows to draw, plus the two things about the bar frame
-- itself that are worth a checkbox. Everything in here is opt-out and stored
-- by absence, so a saved-variables file written before this panel existed
-- opens with every row already on.
--
-- Wrapped in a do block: the pieces it needs afterwards go on CW, and the rest
-- of its locals give their registers back at the end rather than spending them
-- out of the 200 this chunk gets.
-- ---------------------------------------------------------------------------
do
    local ROWS = {
        { head = "Resource bars" },
        { key = "frame", label = "Show the bars",
          tip = "The mini-bars beside your unit frame. Drag them anywhere you like." },
        { key = "lock", label = "Lock in place",
          tip = "Stops the bars being dragged by accident." },
        { head = "Show a bar for" },
    }
    for _, row in ipairs(BARS.ROWS) do
        ROWS[#ROWS + 1] = {
            key = row.key, label = row.label,
            tip = "Hides this row. The resource itself is unchanged: abilities " ..
                "still build and spend it.",
        }
    end

    local fly = CreateFrame("Frame", "ClasslessWildcardSettings", frame)
    fly:SetWidth(240)
    fly:SetPoint("BOTTOMLEFT", frame, "BOTTOMLEFT", 20, 56)
    fly:SetFrameStrata("DIALOG")
    fly:SetBackdrop({
        bgFile = "Interface\\Buttons\\WHITE8X8",
        edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
        tile = false, edgeSize = 14,
        insets = { left = 4, right = 4, top = 4, bottom = 4 },
    })
    fly:SetBackdropColor(0.03, 0.03, 0.05, 0.97) -- solid: the panes underneath must not show through
    fly:EnableMouse(true)
    fly:Hide()
    CW.setFly = fly

    fly.title = fly:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    fly.title:SetPoint("TOP", 0, -12)
    fly.title:SetText("Settings")

    local checks = {}
    local y = 34
    for i, row in ipairs(ROWS) do
        if row.head then
            if i > 1 then y = y + 6 end   -- a heading needs air above it
            local h = fly:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
            h:SetPoint("TOPLEFT", 16, -y)
            h:SetText("|cffffd100" .. row.head .. "|r")
            y = y + 19
        else
            local name = "ClasslessWildcardSetting" .. i
            local cb = CreateFrame("CheckButton", name, fly, "UICheckButtonTemplate")
            cb:SetWidth(24); cb:SetHeight(24)
            cb:SetPoint("TOPLEFT", 18, -y)
            local label = _G[name .. "Text"]
            if label then label:SetText(row.label) end
            cb.rowKey = row.key
            cb:SetScript("OnClick", function(self)
                local on = self:GetChecked() and true or false
                ClasslessWildcardDB = ClasslessWildcardDB or {}
                if self.rowKey == "frame" then
                    ClasslessWildcardDB.hideBars = (not on) or nil
                    CW.UpdateBarsVisibility()
                elseif self.rowKey == "lock" then
                    ClasslessWildcardDB.barsLocked = on or nil
                else
                    CW.SetBarRow(self.rowKey, on)
                end
                CW.RenderSettings()
            end)
            cb:SetScript("OnEnter", function(self)
                GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
                GameTooltip:AddLine(row.label)
                GameTooltip:AddLine(row.tip, 1, 1, 1, true)
                GameTooltip:Show()
            end)
            cb:SetScript("OnLeave", function() GameTooltip:Hide() end)
            checks[#checks + 1] = cb
            y = y + 24
        end
    end

    local reset = CreateFrame("Button", nil, fly, "UIPanelButtonTemplate")
    reset:SetWidth(150); reset:SetHeight(22)
    reset:SetPoint("TOPLEFT", 18, -y - 8)
    reset:SetText("Reset bar position")
    reset:SetScript("OnClick", function() CW.ResetBarsPosition() end)
    reset:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:AddLine("Reset bar position")
        GameTooltip:AddLine("Puts the bars back under the player frame.", 1, 1, 1, true)
        GameTooltip:Show()
    end)
    reset:SetScript("OnLeave", function() GameTooltip:Hide() end)
    fly:SetHeight(y + 8 + 22 + 14)

    -- The panel is the one place these live, so it reads them back rather than
    -- remembering what it drew: /cwbars and the minimap button change the same
    -- settings from outside it.
    function CW.RenderSettings()
        ClasslessWildcardDB = ClasslessWildcardDB or {}
        for _, cb in ipairs(checks) do
            local on
            if cb.rowKey == "frame" then
                on = ClasslessWildcardDB.hideBars ~= true
            elseif cb.rowKey == "lock" then
                on = ClasslessWildcardDB.barsLocked == true
            else
                on = CW.BarRowOn(cb.rowKey)
            end
            -- 1/nil, never false: SetChecked is not reliably boolean here
            cb:SetChecked(on and 1 or nil)
        end
    end
    CW.settingsChecks = checks

    setBtn:SetScript("OnClick", function()
        CW.helpFly:Hide(); CW.statFly:Hide(); CW.archFly:Hide()
        if fly:IsShown() then
            fly:Hide()
        else
            CW.RenderSettings()
            fly:Show()
        end
    end)
    setBtn:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:AddLine("Settings")
        GameTooltip:AddLine("Choose which resource bars to show, and where they sit.",
            1, 1, 1, true)
        GameTooltip:Show()
    end)
    setBtn:SetScript("OnLeave", function() GameTooltip:Hide() end)
end

-- ---------------------------------------------------------------------------
-- spellbook tabs
--
-- The client files a spell under a tab by its skill line -- "Fire", "Holy",
-- "Feral Combat" -- and the server now gives a Hero the skill lines their
-- spells belong to, so every spell has a heading to sit under instead of
-- everything landing in General.
--
-- Blizzard only ever builds 8 tab buttons, because no real class needs more.
-- A Hero can span all 33 class skill lines, so build the rest from Blizzard's
-- own virtual template and wrap them into columns beside the spellbook: the
-- frame is only tall enough for 8 in a row.
-- ---------------------------------------------------------------------------
local CW_TAB_LIMIT = 40          -- comfortably above the 33 that carry spells
local CW_TABS_PER_COLUMN = 7     -- 8 fit, but the 8th lands on the page-turn row; 7 keeps clear of it
local CW_TAB_STEP_Y = 49         -- 32px button + Blizzard's 17px gap
local CW_TAB_STEP_X = 42

local function CW_LayoutSpellbookTabs()
    if not SpellBookFrame then return end
    for i = 1, MAX_SKILLLINE_TABS do
        local tab = _G["SpellBookSkillLineTab" .. i]
        if tab then
            local col = math.floor((i - 1) / CW_TABS_PER_COLUMN)
            local row = math.fmod(i - 1, CW_TABS_PER_COLUMN)
            tab:ClearAllPoints()
            tab:SetPoint("TOPLEFT", SpellBookFrame, "TOPRIGHT",
                         -32 + col * CW_TAB_STEP_X, -65 - row * CW_TAB_STEP_Y)
        end
    end
end

local function CW_BuildSpellbookTabs()
    if not SpellBookFrame or not MAX_SKILLLINE_TABS then return end
    if MAX_SKILLLINE_TABS >= CW_TAB_LIMIT then return end

    for i = MAX_SKILLLINE_TABS + 1, CW_TAB_LIMIT do
        local name = "SpellBookSkillLineTab" .. i
        if not _G[name] then
            -- Blizzard's own template, so these behave exactly like tabs 1-8:
            -- same art, same click handler, same tooltip.
            local tab = CreateFrame("CheckButton", name, SpellBookFrame,
                                    "SpellBookSkillLineTabTemplate")
            tab:SetID(i)
            tab:Hide()

            -- The glow texture is NOT part of that template. Blizzard declares
            -- eight of them by hand inside SpellBookTabFlashFrame, and
            -- SpellBookFrame_Update calls
            --     _G["SpellBookSkillLineTab"..i.."Flash"]:Hide()
            -- for every tab up to MAX_SKILLLINE_TABS. Raising the ceiling
            -- without making these is what threw "attempt to index field '?'".
            local flashParent = SpellBookTabFlashFrame or SpellBookFrame
            local flash = flashParent:CreateTexture(name .. "Flash", "OVERLAY")
            flash:SetTexture("Interface\\Buttons\\CheckButtonGlow")
            flash:SetBlendMode("ADD")
            flash:SetWidth(64); flash:SetHeight(64)
            flash:SetPoint("CENTER", tab, "CENTER", 0, 0)
            flash:Hide()
        end
    end
    -- The per-tab page counter is a plain table Blizzard seeds for tabs 1-8
    -- only (SPELLBOOK_PAGENUMBERS[1..8] = 1 in SpellBookFrame_OnLoad). It is
    -- read arithmetically -- SPELLS_PER_PAGE * (SPELLBOOK_PAGENUMBERS[tab] - 1)
    -- -- so clicking a tab past 8 with no entry is "nil - 1". Seed the rest.
    if SPELLBOOK_PAGENUMBERS then
        for i = MAX_SKILLLINE_TABS + 1, CW_TAB_LIMIT do
            if SPELLBOOK_PAGENUMBERS[i] == nil then
                SPELLBOOK_PAGENUMBERS[i] = 1
            end
        end
    end

    -- raise the ceiling only after the buttons exist, so Blizzard's update loop
    -- can never index a tab that was not created
    MAX_SKILLLINE_TABS = CW_TAB_LIMIT
    CW_LayoutSpellbookTabs()
end

-- SpellBookFrame is loaded on demand, so wait for it rather than assuming.
local tabWatcher = CreateFrame("Frame")
tabWatcher:RegisterEvent("PLAYER_ENTERING_WORLD")
tabWatcher:RegisterEvent("ADDON_LOADED")
tabWatcher:SetScript("OnEvent", function()
    if SpellBookFrame and not tabWatcher.done then
        tabWatcher.done = true
        CW_BuildSpellbookTabs()
        -- Blizzard re-shows and re-textures tabs on every update but never
        -- re-anchors them, so one layout pass after each update is enough.
        if SpellBookFrame_Update then
            hooksecurefunc("SpellBookFrame_Update", CW_LayoutSpellbookTabs)
        end
    end
end)

SLASH_CLASSLESSWILDCARDBARS1 = "/cwbars"
SlashCmdList["CLASSLESSWILDCARDBARS"] = function(msg)
    ClasslessWildcardDB = ClasslessWildcardDB or {}
    local cmd = strtrim(strlower(msg or ""))
    if cmd == "lock" or cmd == "unlock" then
        ClasslessWildcardDB.barsLocked = (cmd == "lock")
        Print(cmd == "lock" and "Resource bars locked in place."
            or "Resource bars unlocked. Drag them anywhere.")
    elseif cmd == "reset" then
        CW.ResetBarsPosition()
        Print("Resource bars moved back under the player frame.")
    elseif cmd == "show" or cmd == "hide" then
        ClasslessWildcardDB.hideBars = (cmd == "hide")
        CW.UpdateBarsVisibility()
    elseif cmd == "" then
        ClasslessWildcardDB.hideBars = not ClasslessWildcardDB.hideBars
        CW.UpdateBarsVisibility()
    else
        Print("/cwbars, or /cwbars show, hide, lock, unlock, reset.")
    end
end

-- ---------------------------------------------------------------------------
-- minimap button + help ("?") micro-button takeover
-- ---------------------------------------------------------------------------
local function ToggleMainPanel()
    if frame:IsShown() then frame:Hide() else frame:Show() end
end
CW.TogglePanel = ToggleMainPanel

if Minimap then
    local mmBtn = CreateFrame("Button", "ClasslessWildcardMinimapButton", Minimap)
    mmBtn:SetWidth(33); mmBtn:SetHeight(33)
    mmBtn:SetFrameStrata("MEDIUM")
    mmBtn:RegisterForClicks("LeftButtonUp", "RightButtonUp")
    mmBtn:RegisterForDrag("LeftButton")

    local overlay = mmBtn:CreateTexture(nil, "OVERLAY")
    overlay:SetWidth(53); overlay:SetHeight(53)
    overlay:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
    overlay:SetPoint("TOPLEFT", 0, 0)

    local icon = mmBtn:CreateTexture(nil, "BACKGROUND")
    icon:SetWidth(21); icon:SetHeight(21)
    icon:SetTexture("Interface\\AddOns\\ClasslessWildcard\\icon")
    icon:SetTexCoord(0, 1, 0, 1)
    icon:SetPoint("CENTER", 0, 1)

    local atan2 = math.atan2 or function(y, x) return math.atan(y, x) end

    local function UpdatePosition()
        ClasslessWildcardDB = ClasslessWildcardDB or {}
        local angle = math.rad(ClasslessWildcardDB.minimapAngle or 210)
        mmBtn:SetPoint("CENTER", Minimap, "CENTER", 80 * math.cos(angle), 80 * math.sin(angle))
    end

    mmBtn:SetScript("OnDragStart", function(self)
        self:SetScript("OnUpdate", function()
            local mx, my = Minimap:GetCenter()
            local cx, cy = GetCursorPosition()
            local scale = Minimap:GetEffectiveScale()
            cx, cy = cx / scale, cy / scale
            ClasslessWildcardDB = ClasslessWildcardDB or {}
            ClasslessWildcardDB.minimapAngle = math.deg(atan2(cy - my, cx - mx))
            UpdatePosition()
        end)
    end)
    mmBtn:SetScript("OnDragStop", function(self) self:SetScript("OnUpdate", nil) end)

    mmBtn:SetScript("OnClick", function(self, button)
        if button == "RightButton" then
            SlashCmdList["CLASSLESSWILDCARDBARS"]("")
        else
            ToggleMainPanel()
        end
    end)
    mmBtn:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_LEFT")
        GameTooltip:AddLine("Hero Advancement")
        local key = GetBindingKey and GetBindingKey("CLASSLESSWILDCARD_TOGGLE")
        GameTooltip:AddLine("Left-click: classless panel" .. (key and ("  (" .. key .. ")") or ""), 1, 1, 1)
        GameTooltip:AddLine("Right-click: toggle resource bars", 1, 1, 1)
        GameTooltip:AddLine("Drag to move", 0.7, 0.7, 0.7)
        GameTooltip:Show()
    end)
    mmBtn:SetScript("OnLeave", function() GameTooltip:Hide() end)

    UpdatePosition()
    CW.minimapButton = mmBtn
end

-- Repurpose the red "?" micro button on the action bar: normal click opens the
-- classless panel; Shift-click still opens the original Help / GM window so
-- players keep ticket access.
if HelpMicroButton then
    local originalClick = HelpMicroButton:GetScript("OnClick")
    HelpMicroButton:SetScript("OnClick", function(self, button, ...)
        if IsShiftKeyDown and IsShiftKeyDown() and originalClick then
            originalClick(self, button, ...)
        else
            ToggleMainPanel()
        end
    end)
    -- Show the bound key after the name, the way every stock micro button does
    -- ("Player vs. Player (H)"). MicroButtonTooltipText appends it from the
    -- CURRENT binding, so this has to be refreshed whenever bindings change --
    -- notably after we claim our own key, which happens later than this file.
    function CW.RefreshMicroTooltip()
        if not HelpMicroButton then return end
        local label = "Hero Advancement"
        if MicroButtonTooltipText then
            label = MicroButtonTooltipText(label, "CLASSLESSWILDCARD_TOGGLE")
        end
        HelpMicroButton.tooltipText = label
        HelpMicroButton.newbieText = "Opens the classless panel. Shift-click for the Help / GM window."
    end
    CW.RefreshMicroTooltip()

    -- REPLACE the button art outright: the "?" is gone, and the die texture is
    -- baked in the micro button's own 32x64 layout, so it fills the art area
    -- and scales with the button under any bar addon
    HelpMicroButton:SetNormalTexture("Interface\\AddOns\\ClasslessWildcard\\micro_die")
    HelpMicroButton:SetPushedTexture("Interface\\AddOns\\ClasslessWildcard\\micro_die_down")
    HelpMicroButton:SetDisabledTexture("Interface\\AddOns\\ClasslessWildcard\\micro_die")
end

-- ---------------------------------------------------------------------------
-- classless naming belt: in-world UI that reads the FrameXML class-name
-- tables shows "Hero" even for players without the patch-4.MPQ rename
-- ---------------------------------------------------------------------------
local HERO_NAME = "Hero"
for _, tbl in ipairs({ LOCALIZED_CLASS_NAMES_MALE, LOCALIZED_CLASS_NAMES_FEMALE }) do
    if type(tbl) == "table" then
        for token in pairs(tbl) do
            tbl[token] = HERO_NAME
        end
    end
end

-- ---------------------------------------------------------------------------
-- character sheet stat tooltips: the stock UI describes stats by CLASS (a
-- warrior gets no Intellect text at all); Heroes are classless, so describe
-- what each stat does under the universal stat system
-- ---------------------------------------------------------------------------
if PaperDollFrame_SetStat and hooksecurefunc then
    local STAT_TIPS = {
        [1] = "Increases your melee attack power and block value.",
        [2] = "Increases your melee and ranged attack power, critical strike chance and dodge chance.",
        [3] = "Increases your health.",
        [4] = "Increases your mana, spell power and spell critical strike chance.",
        [5] = "Increases your mana and health regeneration.",
    }
    hooksecurefunc("PaperDollFrame_SetStat", function(statFrame, unit, statIndex)
        if unit ~= "player" or not STAT_TIPS[statIndex] then return end
        local tip = STAT_TIPS[statIndex]
        -- append what the classless layer is adding on top, so the sheet agrees
        -- with the Stats panel instead of describing a class this Hero is not
        local _, total = UnitStat("player", statIndex)
        local extra = CW.StatContribution and CW.StatContribution(statIndex, total or 0)
        if extra then
            tip = tip .. "\n\n|cff40ff40Classless: " .. extra .. "|r"
        end
        statFrame.tooltip2 = tip
    end)
end

-- ---------------------------------------------------------------------------
-- roll reveal: animated d20 that spins, lights up and bursts into the rolled
-- ability/talent (Ascension-style level-up moment)
-- ---------------------------------------------------------------------------
local SPIN_ATLAS = "Interface\\AddOns\\ClasslessWildcard\\d20_spin"
local SPIN_TIME, BURST_TIME = 1.6, 0.35

-- frameless, Ascension-style: the die floats over the world on a soft shadow,
-- no dialog box
local reveal = CreateFrame("Frame", "ClasslessWildcardReveal", UIParent)
reveal:SetWidth(360); reveal:SetHeight(404)
reveal:SetPoint("CENTER", 0, 170)
reveal:SetFrameStrata("FULLSCREEN_DIALOG") -- always clearly above the panel
reveal:EnableMouse(true)                   -- and never leaks clicks through
reveal:Hide()

local rvShadow = reveal:CreateTexture(nil, "BACKGROUND")
rvShadow:SetWidth(470); rvShadow:SetHeight(470)
rvShadow:SetPoint("CENTER", 0, 0)
rvShadow:SetTexture("Interface\\AddOns\\ClasslessWildcard\\shadow")

-- Text over open world is unreadable against bright ground, so darken a band
-- behind the title and the name/rarity lines. Two soft bars rather than a panel:
-- the reveal is meant to float, not become a dialog box.
local function TextScrim(parent, y, height, alpha)
    local t = parent:CreateTexture(nil, "BACKGROUND", nil, -6)
    t:SetTexture("Interface\\AddOns\\ClasslessWildcard\\shadow")
    t:SetWidth(360); t:SetHeight(height)
    t:SetPoint("CENTER", 0, y)
    t:SetAlpha(alpha)
    return t
end
local rvTitleScrim = TextScrim(reveal, 176, 96, 0.85)
local rvTextScrim = TextScrim(reveal, -148, 122, 0.9)

local rvTitle = reveal:CreateFontString(nil, "OVERLAY", "GameFontNormalHuge")
rvTitle:SetPoint("TOP", 0, -8)

local REVEAL_ATLAS = "Interface\\AddOns\\ClasslessWildcard\\die_reveal"

-- Two counter-turning starbursts behind the die. glow.tga is a soft radial
-- blob -- its alpha varies by 9 of 255 across angles -- so spinning THAT would
-- read as nothing moving; rays.tga (client-addon/gen_rays.py) has beams, and
-- beams show their rotation. The second layer only lights up for the top two
-- tiers, where two speeds crossing is most of what makes it feel big.
-- One table, not five file-level locals: the main chunk is close to Lua 5.1's
-- 200-local ceiling and five more went over it.
local rvFX = { rot = 0, INFO_LINES = 9 }   -- INFO_LINES here: the rows are built below, before the scanner
rvFX.rays = reveal:CreateTexture(nil, "BACKGROUND", nil, 2)
rvFX.rays:SetWidth(372); rvFX.rays:SetHeight(372)
rvFX.rays:SetPoint("CENTER", 0, 26)
rvFX.rays:SetTexture("Interface\\AddOns\\ClasslessWildcard\\rays")
rvFX.rays:SetBlendMode("ADD")
rvFX.rays:Hide()

rvFX.rays2 = reveal:CreateTexture(nil, "BACKGROUND", nil, 3)
rvFX.rays2:SetWidth(268); rvFX.rays2:SetHeight(268)
rvFX.rays2:SetPoint("CENTER", 0, 26)
rvFX.rays2:SetTexture("Interface\\AddOns\\ClasslessWildcard\\rays")
rvFX.rays2:SetBlendMode("ADD")
rvFX.rays2:Hide()

local rvGlow = reveal:CreateTexture(nil, "BORDER")
rvGlow:SetWidth(310); rvGlow:SetHeight(310)
rvGlow:SetPoint("CENTER", 0, 26)
rvGlow:SetTexture("Interface\\AddOns\\ClasslessWildcard\\glow")
rvGlow:SetBlendMode("ADD")

-- The icon sits BEHIND the die so the frame's own octagonal window masks it --
-- a square icon drawn over the top covers the frame and looks pasted on.
--
-- The window is NOT in the middle of the art. Measured off die_reveal.tga (a
-- 4x2 atlas of 256px frames; flood the transparent surround in from the border
-- and whatever transparency is left is the enclosed hole), the window centre
-- sits at (129.8, 123.3) of 256 on every one of the five rarity frames: 1.8px
-- right of centre and 4.7px above it, with a diameter of 82.5px. The die is
-- drawn at 280 for a 256px source, so on screen that is 2px right and 5px up,
-- on a 90px window. Anchoring the icon at the die's own centre therefore left
-- it low and left in the hole, with the rim eating one side of it.
--
-- The die is anchored CENTER (0, 26), so the window is CENTER (2, 31).
local rvIcon = reveal:CreateTexture(nil, "ARTWORK")
rvIcon:SetPoint("CENTER", 2, 31)

local rvDie = reveal:CreateTexture(nil, "OVERLAY")
rvDie:SetWidth(205); rvDie:SetHeight(205)
rvDie:SetPoint("CENTER", 0, 26)
rvDie:SetTexture(SPIN_ATLAS)

-- hover the revealed ability to read its tooltip
local rvHover = CreateFrame("Button", nil, reveal)
rvHover:SetWidth(250); rvHover:SetHeight(250)
rvHover:SetPoint("CENTER", 0, 26)
rvHover:SetScript("OnEnter", function(self)
    -- CW.revealAnim: rvAnim is declared below, so reach it through CW
    local anim = CW.revealAnim
    local d = anim and anim.data
    if d and d.spell and anim.phase == "shown" then
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetHyperlink("spell:" .. d.spell)
        GameTooltip:Show()
    end
end)
rvHover:SetScript("OnLeave", function() GameTooltip:Hide() end)

local rvName = reveal:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
rvName:SetPoint("CENTER", 0, -138)

local rvSub = reveal:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
rvSub:SetPoint("CENTER", 0, -170)

-- The reveal floats over the world with no dialog behind it, so every line
-- gets a hard shadow or it reads differently on grass than it does on stone.
-- The ability's NAME is the thing being announced and was set smaller than the
-- headline above it; it is the larger of the two now.
do
    local face = rvTitle:GetFont()
    if face then
        rvName:SetFont(face, 24)
        rvSub:SetFont(face, 15)
    end
    for _, fs in ipairs({ rvTitle, rvName, rvSub }) do
        fs:SetShadowColor(0, 0, 0, 1)
        fs:SetShadowOffset(1, -1)
    end
end

-- A real panel behind the text. The reveal floats over the world, and a shadow
-- alone is not a background: small text on grass is unreadable however hard its
-- shadow is. This is the tooltip treatment -- near-black plate, hairline border
-- in the rarity's colour -- drawn on BACKGROUND/BORDER so the OVERLAY font
-- strings of this same frame stay on top of it without any reparenting.
rvFX.panel = reveal:CreateTexture(nil, "BACKGROUND", nil, 5)
rvFX.panel:SetTexture(0, 0, 0)
rvFX.panel:SetAlpha(0.86)
rvFX.panel:SetWidth(344)
rvFX.panel:Hide()

rvFX.edges = {}
for i = 1, 4 do
    local e = reveal:CreateTexture(nil, "BORDER")
    e:SetTexture(1, 1, 1)
    e:Hide()
    rvFX.edges[i] = e
end
rvFX.edges[1]:SetPoint("TOPLEFT", rvFX.panel, "TOPLEFT", 0, 0)
rvFX.edges[1]:SetPoint("TOPRIGHT", rvFX.panel, "TOPRIGHT", 0, 0)
rvFX.edges[1]:SetHeight(1)
rvFX.edges[2]:SetPoint("BOTTOMLEFT", rvFX.panel, "BOTTOMLEFT", 0, 0)
rvFX.edges[2]:SetPoint("BOTTOMRIGHT", rvFX.panel, "BOTTOMRIGHT", 0, 0)
rvFX.edges[2]:SetHeight(1)
rvFX.edges[3]:SetPoint("TOPLEFT", rvFX.panel, "TOPLEFT", 0, 0)
rvFX.edges[3]:SetPoint("BOTTOMLEFT", rvFX.panel, "BOTTOMLEFT", 0, 0)
rvFX.edges[3]:SetWidth(1)
rvFX.edges[4]:SetPoint("TOPRIGHT", rvFX.panel, "TOPRIGHT", 0, 0)
rvFX.edges[4]:SetPoint("BOTTOMRIGHT", rvFX.panel, "BOTTOMRIGHT", 0, 0)
rvFX.edges[4]:SetWidth(1)

-- One row per tooltip line, laid out like the tooltip itself: a left-justified
-- string and a right-justified one sharing the same box, so "10 Rage" and
-- "Melee Range" sit at opposite ends of the same line. Rows chain downward from
-- the one above, so a wrapped description pushes what follows it. The reveal
-- frame is NOT resized around them -- nothing clips children here, so the block
-- simply extends below it and the buttons are re-anchored under whatever it
-- came to.
rvFX.info = {}
for i = 1, rvFX.INFO_LINES do
    local row = {}
    row.left = reveal:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    row.left:SetWidth(304)
    row.left:SetJustifyH("LEFT")
    row.left:SetJustifyV("TOP")
    row.left:SetShadowColor(0, 0, 0, 1)
    row.left:SetShadowOffset(1, -1)
    if i == 1 then
        row.left:SetPoint("TOP", rvSub, "BOTTOM", 0, -10)
    else
        row.left:SetPoint("TOP", rvFX.info[i - 1].left, "BOTTOM", 0, -2)
    end
    row.right = reveal:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    row.right:SetAllPoints(row.left)
    row.right:SetJustifyH("RIGHT")
    row.right:SetJustifyV("TOP")
    row.right:SetShadowColor(0, 0, 0, 1)
    row.right:SetShadowOffset(1, -1)
    local face = row.left:GetFont()
    if face then
        row.left:SetFont(face, 14)
        row.right:SetFont(face, 14)
    end
    row.left:Hide(); row.right:Hide()
    rvFX.info[i] = row
end

function rvFX.HideInfo()
    rvFX.panel:Hide()
    for _, e in ipairs(rvFX.edges) do e:Hide() end
    for i = 1, rvFX.INFO_LINES do
        rvFX.info[i].left:SetText(""); rvFX.info[i].right:SetText("")
        rvFX.info[i].left:Hide(); rvFX.info[i].right:Hide()
    end
end

-- Fill the block from a spell's own tooltip and return how tall it came out.
function rvFX.ShowInfo(spellId)
    local lines = rvFX.ScanSpell(spellId)
    local height, last = 0, nil
    for i = 1, rvFX.INFO_LINES do
        local row, line = rvFX.info[i], lines[i]
        if line then
            row.left:SetText(line.left or "")
            row.right:SetText(line.right or "")
            row.left:SetTextColor(line.r, line.g, line.b)
            row.right:SetTextColor(line.r, line.g, line.b)
            row.left:Show(); row.right:Show()
            height = height + (tonumber(row.left:GetStringHeight()) or 12) + 2
            last = row.left
        else
            -- blank as well as hidden: a hidden string keeps its old height and
            -- would still push the row below it
            row.left:SetText(""); row.right:SetText("")
            row.left:Hide(); row.right:Hide()
        end
    end
    return height, last
end

local rvKeep = CreateFrame("Button", nil, reveal, "UIPanelButtonTemplate")
rvKeep:SetWidth(110); rvKeep:SetHeight(24)
rvKeep:SetPoint("BOTTOM", -60, 4)
rvKeep:SetText("Keep")

local rvReroll = CreateFrame("Button", nil, reveal, "UIPanelButtonTemplate")
rvReroll:SetWidth(110); rvReroll:SetHeight(24)
rvReroll:SetPoint("BOTTOM", 60, 4)
rvReroll:SetText("Reroll")

local rvAnim = { phase = "idle", t0 = 0, data = nil }
CW.revealQueue = {}
CW.revealAnim = rvAnim

local function SetDieFrame(idx)
    local col, rowi = idx % 8, math.floor(idx / 8) % 2
    rvDie:SetTexCoord(col / 8, (col + 1) / 8, rowi / 2, (rowi + 1) / 2)
end

-- 3.3.5 has no Texture:SetRotation, so a rotation is a rotated QUAD handed to
-- SetTexCoord. The corners sample outside 0..1 and clamp to the edge pixels,
-- which is exactly why rays.tga is transparent all the way to its border:
-- there is nothing out there to smear inward.
function rvFX.Spin(tex, angle)
    local c, s2 = math.cos(angle), math.sin(angle)
    local function r(x, y) return 0.5 + x * c - y * s2, 0.5 + x * s2 + y * c end
    local ax, ay = r(-0.5, -0.5)
    local bx, by = r(-0.5,  0.5)
    local cx, cy = r( 0.5, -0.5)
    local dx, dy = r( 0.5,  0.5)
    tex:SetTexCoord(ax, ay, bx, by, cx, cy, dx, dy)
end

-- How much of a show each tier puts on. A common roll stays quiet on purpose:
-- if every result is a fanfare then none of them is one.
--   rays  peak brightness of the starburst   spin  turns per second
--   pulse how hard it breathes               pop   extra px the die overshoots
--   shake px the whole reveal kicks          snd   the hit, snd2 layers over it
rvFX.tiers = {
    [0] = { rays = 0,    spin = 0,    pulse = 0,    pop = 0,  shake = 0,   snd = "igMainMenuOptionCheckBoxOn" },
    [1] = { rays = 0.22, spin = 0.16, pulse = 0.05, pop = 4,  shake = 0,   snd = "LOOTWINDOWCOINSOUND" },
    [2] = { rays = 0.38, spin = 0.26, pulse = 0.10, pop = 9,  shake = 0,   snd = "QUESTCOMPLETED" },
    [3] = { rays = 0.54, spin = 0.42, pulse = 0.16, pop = 15, shake = 3,   snd = "LEVELUPSOUND" },
    [4] = { rays = 0.74, spin = 0.62, pulse = 0.24, pop = 24, shake = 6,   snd = "PVPTHROUGHQUEUE",
            snd2 = "LEVELUPSOUND" },
}
function rvFX.Tier(rarity) return rvFX.tiers[math.min(rarity or 0, 4)] or rvFX.tiers[0] end

-- RARITY_NAMES carries its own colour codes, which cannot be concatenated into
-- a longer coloured phrase. These are the bare words.
rvFX.tierName = { [0] = "Common", [1] = "Uncommon", [2] = "Rare", [3] = "Epic", [4] = "Legendary" }

-- Read the game's OWN tooltip for a spell without ever showing it: a tooltip
-- parented to nothing, pointed at the spell, then its FontStrings read back.
-- That is where cost, range, cast time, cooldown, stance requirements and the
-- description all live already, correctly worded and correctly coloured, so
-- the reveal reproduces those lines rather than inventing its own.
rvFX.scan = CreateFrame("GameTooltip", "ClasslessWildcardScanTip", nil, "GameTooltipTemplate")
rvFX.scan:SetOwner(UIParent, "ANCHOR_NONE")

function rvFX.ScanSpell(spellId)
    local out, tip = {}, rvFX.scan
    if not tip or not spellId then return out end
    if tip.ClearLines then tip:ClearLines() end
    if not pcall(tip.SetHyperlink, tip, "spell:" .. spellId) then return out end
    local n = tonumber(tip.NumLines and tip:NumLines()) or 0
    -- line 1 is the spell's name, which the reveal already shows large
    for i = 2, math.min(n, rvFX.INFO_LINES + 1) do
        local lfs = _G["ClasslessWildcardScanTipTextLeft" .. i]
        local rfs = _G["ClasslessWildcardScanTipTextRight" .. i]
        local lt = lfs and lfs.GetText and lfs:GetText()
        local rt = rfs and rfs.GetText and rfs:GetText()
        if lt == "" then lt = nil end
        if rt == "" then rt = nil end
        local cr, cg, cb = 1, 1, 1
        if lfs and lfs.GetTextColor then
            local a, b, c = lfs:GetTextColor()
            if type(a) == "number" then cr, cg, cb = a, b, c end
        end
        if lt or rt then
            out[#out + 1] = { left = lt, right = rt, r = cr, g = cg, b = cb }
        end
    end
    return out
end

rvFX.cardFlash = 0.55   -- seconds a dealt card flashes before settling

-- A card in the starting hand wears its own tier the same way the reveal does:
-- a pool of its colour behind it, and for the top two a starburst that keeps
-- turning for as long as the hand is open. `boost` is the extra flash as the
-- card lands, decaying to nothing; what is left after that is the resting
-- state, so a legendary in your hand still reads as one while you decide.
function rvFX.CardFX(slot, rarity, boost)
    local fx = rvFX.Tier(rarity)
    if fx.rays <= 0 and boost <= 0 then
        slot.glow:Hide(); slot.rays:Hide()
        return
    end
    local rgb = RARITY_RGB[math.min(rarity or 0, 4)] or RARITY_RGB[0]
    slot.glow:SetVertexColor(rgb[1], rgb[2], rgb[3])
    slot.glow:SetAlpha(fx.rays * 0.80 + boost * 0.9)
    slot.glow:Show()
    if fx.rays >= 0.5 then          -- epic and legendary
        slot.rays:SetVertexColor(rgb[1], rgb[2], rgb[3])
        slot.rays:SetAlpha(fx.rays * 0.55 + boost * 0.5)
        slot.spinRate = fx.spin
        slot.rays:Show()
    else
        slot.rays:Hide()
    end
end

CW.revealFX = rvFX   -- exposed for tests

local function ShowResult()
    local d = rvAnim.data
    rvAnim.phase = "shown"
    local rgb = RARITY_RGB[d.rarity or 0] or RARITY_RGB[0]
    local fx = rvFX.Tier(d.rarity)
    -- a legendary sits in a brighter pool of its own colour than a common does
    rvGlow:SetAlpha(0.55 + fx.rays * 0.35)
    rvGlow:SetVertexColor(rgb[1], rgb[2], rgb[3])
    -- swap to the rarity die frame; the spell icon shows through its window
    -- (4x2 atlas of 256px frames — the client caps textures at 1024px)
    local r = math.min(d.rarity or 0, 4)
    local col, rowi = r % 4, math.floor(r / 4)
    rvDie:SetTexture(REVEAL_ATLAS)
    rvDie:SetTexCoord(col / 4, (col + 1) / 4, rowi / 2, (rowi + 1) / 2)
    -- The artwork's window is a circle 32% across the frame, so the die is
    -- drawn large (280px) to make that opening a usable 90px across, and the
    -- icon is drawn just under that so it fills the hole with the window rim
    -- showing all the way round.
    --
    -- 96px against a 90px window: the icon is deliberately BIGGER than the
    -- hole so it fills it corner to corner with no dark ring showing, and the
    -- rim crops the outer ~3px of every edge -- which is where the icon's own
    -- dark border lives, so that goes with it. Only 2% is trimmed, enough for
    -- the last of the border without eating into the picture.
    --
    -- What sets the ceiling is the elemental badge, which sits 10% up from the
    -- icon's bottom edge (client-patch/lib/elemental.py). Its bottom corners
    -- land 43px from the icon's centre against the window's 45px radius, so
    -- the whole element survives the crop. Raise the icon much past 96 and it
    -- starts eating the badge again.
    rvDie:SetWidth(280); rvDie:SetHeight(280)
    rvDie:Show()
    rvIcon:SetWidth(96); rvIcon:SetHeight(96)
    rvIcon:SetTexture(SpellIcon(d.spell))
    rvIcon:SetTexCoord(0.02, 0.98, 0.02, 0.98)
    rvIcon:Show()
    -- The headline says WHICH tier and wears its colour. "Ability Unlocked!"
    -- said exactly the same thing for a common as for a legendary, which is the
    -- one moment that should not read the same.
    local hex = string.format("|cff%02x%02x%02x", rgb[1] * 255, rgb[2] * 255, rgb[3] * 255)
    local kind = d.isTalent and "Talent" or "Ability"
    rvTitle:SetText(r > 0 and (hex .. rvFX.tierName[r] .. " " .. kind .. "!|r")
                           or (kind .. " Unlocked!"))
    if d.isTalent then
        -- rank IS the rarity for talents, so it is colored and shown large
        rvName:SetText(SpellLabel(d.spell, d.rarity) .. "  " .. hex .. "Rank " .. (d.rank or 1) .. "|r")
    else
        rvName:SetText(SpellLabel(d.spell, d.rarity))
    end
    if d.test then
        rvSub:SetText((RARITY_NAMES[d.rarity or 0] or "") .. "  |cffff8800(preview, nothing is granted)|r")
    elseif d.flags == 1 then
        rvSub:SetText("|cff00ff88Synergy roll: it complements your Hero!|r")
    elseif d.isTalent then
        -- one talent point buys the talent whatever rank it landed on
        rvSub:SetText((RARITY_NAMES[d.rarity or 0] or "") .. "  |cffaaaaaa- dealt free, all ranks included|r")
    else
        rvSub:SetText(RARITY_NAMES[d.rarity or 0] or "")
    end
    rvName:Show(); rvSub:Show()

    -- Everything the tooltip would have said, without asking for a hover: what
    -- it costs, its range, cast time, cooldown, any stance it needs, and what
    -- it actually does. The block grows downward and the buttons follow it, so
    -- a one-line passive and a six-line spell both sit right.
    local infoH, lastRow = rvFX.ShowInfo(d.spell)
    local anchor = lastRow or rvSub
    rvKeep:ClearAllPoints()
    rvReroll:ClearAllPoints()
    rvKeep:SetPoint("TOPRIGHT", anchor, "BOTTOM", -6, -18)
    rvReroll:SetPoint("TOPLEFT", anchor, "BOTTOM", 6, -18)

    -- The plate wraps the name, the tier line and everything read off the
    -- tooltip, from a little above the name to a little below the last row.
    -- Anchoring top and bottom rather than setting a height means a one-line
    -- passive and a six-line spell both come out tight.
    rvFX.panel:ClearAllPoints()
    rvFX.panel:SetPoint("TOP", rvName, "TOP", 0, 12)
    rvFX.panel:SetPoint("BOTTOM", anchor, "BOTTOM", 0, -12)
    rvFX.panel:Show()
    for _, e in ipairs(rvFX.edges) do
        e:SetVertexColor(rgb[1], rgb[2], rgb[3], 0.85)
        e:Show()
    end
    -- the soft scrim still sits under the plate and blends its edges out
    rvTextScrim:SetHeight(170 + infoH)
    rvTextScrim:ClearAllPoints()
    rvTextScrim:SetPoint("CENTER", 0, -168 - infoH / 2)
    -- reroll button shows what the player can actually spend
    local s = CW.state
    local charges = (s.rerolls or 0) + (s.scrolls or 0)
    if (s.level or 1) < (s.freeReroll or 10) then
        rvReroll:SetText("Reroll (free)")
        rvReroll:Enable()
    elseif charges > 0 then
        rvReroll:SetText("Reroll (" .. charges .. ")")
        rvReroll:Enable()
    else
        rvReroll:SetText("Reroll (0)")
        rvReroll:Disable()
    end
    rvKeep:Show(); rvReroll:Show()
    -- No sound here. The tier's own sound already played on the burst frame,
    -- where the colour and the starburst land; a level-up fanfare on top of it
    -- fired for every result and flattened the whole escalation back out.
end

local function StartReveal(d)
    rvAnim.phase = "spin"
    rvAnim.t0 = GetTime()
    rvAnim.awaiting = false   -- any reveal starting fresh is no longer a pending reroll
    rvAnim.data = d
    -- say what is being rolled: a level can deal a talent AND an ability, so
    -- "the Wildcard rolls..." alone left you guessing which one you were seeing
    rvTitle:SetText(d.isTalent and "Rolling a Talent..." or "Rolling an Ability...")
    rvGlow:SetVertexColor(0.45, 0.75, 1) -- cyan rim light while spinning
    rvGlow:SetAlpha(0)
    rvIcon:Hide()
    rvName:Hide(); rvSub:Hide()
    rvKeep:Hide(); rvReroll:Hide()
    rvFX.HideInfo()
    rvDie:SetTexture(SPIN_ATLAS)
    SetDieFrame(0)
    rvDie:SetWidth(205); rvDie:SetHeight(205)
    rvDie:Show()
    -- the rays are the payoff, so nothing about the tier shows while it spins
    rvFX.rays:Hide(); rvFX.rays2:Hide()
    rvFX.hit = nil
    reveal:ClearAllPoints()
    reveal:SetPoint("CENTER", 0, 170)
    reveal:Show()
end

local function NextReveal()
    reveal:Hide()
    rvFX.rays:Hide(); rvFX.rays2:Hide()
    rvFX.hit = nil
    rvAnim.phase = "idle"
    if #CW.revealQueue > 0 then
        StartReveal(table.remove(CW.revealQueue, 1))
    end
end

function CW.EnqueueReveal(d)
    if CW.suppressReveals or CW.pendingHand then return end
    -- A reroll we asked for replaces the reveal being rerolled, in place. It
    -- must NOT go to the back of the queue: on a level that rolled both a
    -- talent and an ability, queueing it made an unrelated reveal appear
    -- between the reroll and its own result.
    if rvAnim.awaiting then
        rvAnim.awaiting = false
        StartReveal(d)
        return
    end
    if rvAnim.phase == "idle" and not reveal:IsShown() then
        StartReveal(d)
    else
        tinsert(CW.revealQueue, d)
    end
end

-- Put the die back into its spin and wait for the server to send the
-- replacement roll. Used by the Reroll button.
local function AwaitReroll()
    rvAnim.phase = "spin"
    rvAnim.t0 = GetTime()
    rvAnim.awaiting = true
    rvAnim.awaitT0 = GetTime()
    local d = rvAnim.data
    rvTitle:SetText((d and d.isTalent) and "Rerolling a Talent..." or "Rerolling an Ability...")
    rvGlow:SetVertexColor(0.45, 0.75, 1)
    rvGlow:SetAlpha(0)
    rvIcon:Hide()
    rvName:Hide(); rvSub:Hide()
    rvKeep:Hide(); rvReroll:Hide()
    rvFX.HideInfo()
    rvDie:SetTexture(SPIN_ATLAS)
    SetDieFrame(0)
    rvDie:SetWidth(205); rvDie:SetHeight(205)
    rvDie:Show()
    rvFX.rays:Hide(); rvFX.rays2:Hide()
    rvFX.hit = nil
end
CW.AwaitReroll = AwaitReroll

reveal:SetScript("OnUpdate", function(self, elapsed)
    local fx = rvFX.Tier(rvAnim.data and rvAnim.data.rarity)

    -- The starburst turns for as long as the reveal is up, and the two layers
    -- turn against each other. Driven off elapsed so the speed is the same at
    -- 30fps and at 144.
    if rvFX.hit and fx.rays > 0 then
        rvFX.rot = rvFX.rot + (elapsed or 0) * fx.spin * math.pi * 2
        rvFX.Spin(rvFX.rays, rvFX.rot)
        rvFX.Spin(rvFX.rays2, -rvFX.rot * 1.45)
        -- a slow breath on top, deeper the higher the tier
        local breathe = 1 + math.sin(GetTime() * 3) * fx.pulse
        local up = math.min(1, (GetTime() - rvFX.hit) / 0.35)
        rvFX.rays:SetAlpha(fx.rays * breathe * up)
        rvFX.rays2:SetAlpha(fx.rays * 0.5 * (2 - breathe) * up)
    end

    if rvAnim.phase == "spin" then
        local p = (GetTime() - rvAnim.t0) / SPIN_TIME
        if p >= 1 then
            -- still waiting on the server's replacement roll: keep spinning
            -- rather than bursting back into the ability we just rerolled
            if rvAnim.awaiting then
                if GetTime() - rvAnim.awaitT0 > 5 then
                    rvAnim.awaiting = false   -- no answer came; don't hang the die
                    NextReveal()
                else
                    rvAnim.t0 = GetTime()
                end
                return
            end
            rvAnim.phase = "burst"
            rvAnim.t0 = GetTime()
            -- Land the tumble UPRIGHT before it swells. Nothing set the resting
            -- frame, so the die froze on whichever one the last OnUpdate
            -- happened to compute -- floor(e * 40) put that at frame 8, which
            -- measures as the worst silhouette match to the die at rest of all
            -- sixteen. It then grew at that angle and snapped upright only when
            -- the rarity art replaced it. Frame 0 is the one drawn upright.
            SetDieFrame(0)
            rvGlow:SetAlpha(1)
            -- THE moment: the tier lands here, not when the text appears.
            -- Colour, starburst and sound all arrive together.
            local rgb = RARITY_RGB[math.min((rvAnim.data and rvAnim.data.rarity) or 0, 4)]
            rvGlow:SetVertexColor(rgb[1], rgb[2], rgb[3])
            rvFX.hit = GetTime()
            if fx.rays > 0 then
                rvFX.rays:SetVertexColor(rgb[1], rgb[2], rgb[3])
                rvFX.rays:SetAlpha(0)
                rvFX.rays:Show()
                if fx.rays >= 0.5 then          -- epic and legendary only
                    rvFX.rays2:SetVertexColor(rgb[1], rgb[2], rgb[3])
                    rvFX.rays2:SetAlpha(0)
                    rvFX.rays2:Show()
                end
            end
            if PlaySound then
                pcall(PlaySound, fx.snd)
                if fx.snd2 then pcall(PlaySound, fx.snd2) end
            end
            return
        end
        -- 48 and not 40: three whole turns of the 16-frame atlas, so the last
        -- frame before the burst is 15 and the upright 0 set above is the very
        -- next one. At 40 it ended on 7 and jumping to 0 skipped half a turn.
        local e = 1 - (1 - p) * (1 - p)      -- ease-out: fast spin, slows down
        SetDieFrame(math.floor(e * 48))
        rvGlow:SetAlpha(p * 0.9)
    elseif rvAnim.phase == "burst" then
        local p = (GetTime() - rvAnim.t0) / BURST_TIME
        if p >= 1 then
            reveal:ClearAllPoints()
            reveal:SetPoint("CENTER", 0, 170)   -- put the kick back
            rvDie:SetWidth(280); rvDie:SetHeight(280)
            ShowResult()
            return
        end
        rvGlow:SetAlpha(1 - p * 0.3)
        -- The die expands into the light, overshooting past its resting 280 by
        -- more the better the roll, then easing back onto it.
        local over = math.sin(p * math.pi) * fx.pop
        local s = 205 + 75 * p + over
        rvDie:SetWidth(s); rvDie:SetHeight(s)
        -- and a decaying kick, epic and up
        if fx.shake > 0 then
            local k = fx.shake * (1 - p)
            reveal:ClearAllPoints()
            reveal:SetPoint("CENTER", (math.random() * 2 - 1) * k, 170 + (math.random() * 2 - 1) * k)
        end
    end
end)

rvKeep:SetScript("OnClick", NextReveal)
rvReroll:SetScript("OnClick", function()
    local d = rvAnim.data
    if not d then
        NextReveal()
        return
    end
    if d.test then
        -- /cw testroll preview: nothing is really owned, so re-roll the preview
        -- here instead of asking the server to reroll an ability we do not have
        NextReveal()
        CW.EnqueueReveal({ isTalent = false, entry = 133, spell = 133,
                           rarity = math.random(0, 4), flags = 0, test = true })
        return
    end
    Send((d.isTalent and "RRT " or "RR ") .. d.entry)
    AwaitReroll()   -- hold this reveal open; the replacement lands in its place
end)

-- the server refused the reroll (no charges, locked, ...): put the die back
function CW.CancelReroll()
    if not rvAnim.awaiting then return false end
    rvAnim.awaiting = false
    if rvAnim.data then
        ShowResult()
    else
        NextReveal()
    end
    return true
end

-- ---------------------------------------------------------------------------
-- starting hand (Wildcard onboarding): lock what you like, roll the rest
-- ---------------------------------------------------------------------------
-- frameless, Ascension-style: icons float in a blue burst of light, padlocks
-- above each one, Roll/Keep beneath
local hand = CreateFrame("Frame", "ClasslessWildcardHand", UIParent)
hand:SetWidth(460); hand:SetHeight(210)
hand:SetPoint("CENTER", 0, 120)
hand:SetFrameStrata("FULLSCREEN_DIALOG")
hand:EnableMouse(true)
hand:Hide()

local handShadow = hand:CreateTexture(nil, "BACKGROUND")
handShadow:SetWidth(560); handShadow:SetHeight(340)
handShadow:SetPoint("CENTER", 0, 0)
handShadow:SetTexture("Interface\\AddOns\\ClasslessWildcard\\shadow")

-- extra darkening under the title and the instruction line: over bright ground
-- the shadow alone was not enough to read them against
local handTextScrim = hand:CreateTexture(nil, "BACKGROUND", nil, -6)
handTextScrim:SetWidth(520); handTextScrim:SetHeight(120)
handTextScrim:SetPoint("TOP", 0, 22)
handTextScrim:SetTexture("Interface\\AddOns\\ClasslessWildcard\\shadow")
handTextScrim:SetAlpha(0.9)

local handGlow = hand:CreateTexture(nil, "BORDER")
handGlow:SetWidth(440); handGlow:SetHeight(230)
handGlow:SetPoint("CENTER", 0, 8)
handGlow:SetTexture("Interface\\AddOns\\ClasslessWildcard\\glow")
handGlow:SetBlendMode("ADD")
handGlow:SetVertexColor(0.35, 0.7, 1)
handGlow:SetAlpha(0.85)

local handTitle = hand:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
handTitle:SetPoint("TOP", 0, -18)
handTitle:SetText("Your Starting Hand")

local handHint = hand:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
handHint:SetPoint("TOP", 0, -40)
handHint:SetText("Click an ability to lock it in: |cffffd100gold ring + closed padlock = kept|r." ..
    " Roll Abilities rerolls only the unlocked ones. Free until level 10!")

-- Four cards. Not a layout budget that happens to fit four -- four is the size
-- of the starting hand, full stop. The server clamps StartingAbilities to the
-- same number so it can never deal a card this screen would not draw.
local HAND_SLOTS = 4
local HAND_SPACING = 56
local handSlots = {}

-- Stacking, set out explicitly, because the defaults get both halves wrong.
--
-- A child frame draws above its parent's own textures whatever draw layer the
-- texture is on, so a die living on `hand` could never roll in FRONT of the
-- cards -- they are Buttons parented to `hand`. And sibling frames on the same
-- level draw in creation order, so card 4's glow (140px wide, on a 56px pitch)
-- landed on top of card 3's art.
--
-- So: every card's glow and starburst go on ONE frame beneath all the cards,
-- the cards sit above that, and the die sits above the cards. The row is then
-- revealed from behind the die as it rolls, and no card's light ever covers a
-- neighbour.
hand.fxLayer = CreateFrame("Frame", nil, hand)
hand.fxLayer:SetAllPoints(hand)
hand.dieLayer = CreateFrame("Frame", nil, hand)
hand.dieLayer:SetAllPoints(hand)

-- spinning die shown while the hand rolls in (same atlas as the reveal)
local handDie = hand.dieLayer:CreateTexture(nil, "OVERLAY")
handDie:SetWidth(72); handDie:SetHeight(72)
handDie:SetPoint("CENTER", 0, 0)
handDie:SetTexture("Interface\\AddOns\\ClasslessWildcard\\d20_spin")
handDie:Hide()

for i = 1, HAND_SLOTS do
    local slot = CreateFrame("Button", nil, hand)
    slot:SetWidth(44); slot:SetHeight(44)
    slot:SetPoint("TOPLEFT", 40 + (i - 1) * HAND_SPACING, -96)
    -- Tier dressing (see rvFX.CardFX). It lives on the shared layer under all
    -- the cards, not on this card, but stays anchored to this one so it
    -- follows the card as it rises into place.
    slot.rays = hand.fxLayer:CreateTexture(nil, "ARTWORK", nil, 0)
    slot.rays:SetWidth(132); slot.rays:SetHeight(132)
    slot.rays:SetPoint("CENTER", slot, "CENTER", 0, 0)
    slot.rays:SetTexture("Interface\\AddOns\\ClasslessWildcard\\rays")
    slot.rays:SetBlendMode("ADD")
    slot.rays:Hide()
    slot.glow = hand.fxLayer:CreateTexture(nil, "ARTWORK", nil, 1)
    -- 140 for a 44px card on purpose: glow.tga puts nearly all its brightness
    -- inside the middle third, and at 92 the card sat on top of exactly that,
    -- leaving a halo too faint to read. At 140 the bright shoulder lands just
    -- outside the card's edge, which is where it needs to be seen. rays.tga is
    -- hollow to 17% of its width, so 132 puts its beams at the same edge.
    slot.glow:SetWidth(140); slot.glow:SetHeight(140)
    slot.glow:SetPoint("CENTER", slot, "CENTER", 0, 0)
    slot.glow:SetTexture("Interface\\AddOns\\ClasslessWildcard\\glow")
    slot.glow:SetBlendMode("ADD")
    slot.glow:Hide()
    slot.icon = slot:CreateTexture(nil, "ARTWORK")
    slot.icon:SetAllPoints(slot)
    slot.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    slot.frame = slot:CreateTexture(nil, "OVERLAY")
    slot.frame:SetWidth(74); slot.frame:SetHeight(74)
    slot.frame:SetPoint("CENTER", 0, -1)
    slot.frame:SetTexture("Interface\\Buttons\\UI-Quickslot2")
    -- gold ring = LOCKED IN (unmistakable)
    slot.ring = slot:CreateTexture(nil, "OVERLAY")
    slot.ring:SetWidth(76); slot.ring:SetHeight(76)
    slot.ring:SetPoint("CENTER", 0, 0)
    slot.ring:SetTexture("Interface\\Buttons\\UI-ActionButton-Border")
    slot.ring:SetBlendMode("ADD")
    slot.ring:SetVertexColor(1, 0.82, 0.2)
    slot.ring:Hide()
    -- big padlock ABOVE the icon: gold CLOSED = kept, grey OPEN = will reroll
    slot.lock = slot:CreateTexture(nil, "OVERLAY")
    slot.lock:SetWidth(26); slot.lock:SetHeight(26)
    slot.lock:SetPoint("BOTTOM", slot, "TOP", 0, 4)
    slot.lock:SetTexture("Interface\\AddOns\\ClasslessWildcard\\lock_open")
    slot:SetScript("OnClick", function(self)
        if self.abilityId then
            Send("LOCK " .. self.abilityId)
            if PlaySound then pcall(PlaySound, "igMainMenuOptionCheckBoxOn") end
            -- instant feedback; the server's OWN refresh confirms it
            if self.entryRef then
                self.entryRef.locked = self.entryRef.locked == 1 and 0 or 1
                CW.RenderHand()
            end
        end
    end)
    slot:SetScript("OnEnter", function(self)
        if self.spellId then
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:SetHyperlink("spell:" .. self.spellId)
            GameTooltip:Show()
        end
    end)
    slot:SetScript("OnLeave", function() GameTooltip:Hide() end)
    slot:Hide()
    handSlots[i] = slot
end

-- dressing < cards < die. Set here and again in OnShow: a frame's level can be
-- reassigned when its strata is applied, and the die being one level out is the
-- difference between rolling over the row and rolling under it.
function hand.ApplyLayers()
    local base = hand:GetFrameLevel()
    hand.fxLayer:SetFrameLevel(base)
    for i = 1, HAND_SLOTS do handSlots[i]:SetFrameLevel(base + 3) end
    hand.dieLayer:SetFrameLevel(base + 6)
end
hand.ApplyLayers()

local handRoll = CreateFrame("Button", nil, hand, "UIPanelButtonTemplate")
handRoll:SetWidth(150); handRoll:SetHeight(26)
handRoll:SetPoint("BOTTOMLEFT", 40, 20)
handRoll:SetText("Roll Abilities")

local handKeep = CreateFrame("Button", nil, hand, "UIPanelButtonTemplate")
handKeep:SetWidth(150); handKeep:SetHeight(26)
handKeep:SetPoint("BOTTOMRIGHT", -40, 20)
handKeep:SetText("Keep Abilities")

-- keep every surviving (e.g. locked) card in its exact slot across rerolls;
-- replacements drop into the slots that were vacated
--
-- Only the abilities the Wildcard DEALT are cards. An ability that arrives
-- free alongside one of them -- the stance it cannot be used without, or a
-- form's starter kit -- is owned, but it was never rolled and cannot be
-- rerolled, so it takes no slot. Drawing the whole owned list added a card to
-- the hand every time a roll brought a companion in with it.
local function OrderedHand()
    local byId, dealt = {}, {}
    for _, e in ipairs(CW.owned) do
        if e.source == 1 then   -- 1 = rolled; 0 picked, 2 talent, 3 companion
            byId[e.id] = e
            tinsert(dealt, e)
        end
    end

    local slots, used = {}, {}
    for i, id in ipairs(CW.handOrder or {}) do
        if byId[id] then
            slots[i] = id
            used[id] = true
        end
    end
    local fresh = {}
    for _, e in ipairs(dealt) do
        if not used[e.id] then tinsert(fresh, e.id) end
    end
    local order, k = {}, 1
    for i = 1, HAND_SLOTS do
        local id = slots[i]
        if not id and fresh[k] then
            id = fresh[k]; k = k + 1
        end
        if id then tinsert(order, id) end
    end
    while fresh[k] and #order < HAND_SLOTS do
        tinsert(order, fresh[k]); k = k + 1
    end
    CW.handOrder = order

    local list = {}
    for _, id in ipairs(order) do tinsert(list, byId[id]) end
    return list
end

local function RenderHand()
    local list = OrderedHand()
    -- center the shown cards
    local n = math.min(#list, HAND_SLOTS)
    local rowWidth = n > 0 and (n * HAND_SPACING - (HAND_SPACING - 44)) or 0
    local startX = (460 - rowWidth) / 2

    for i = 1, HAND_SLOTS do
        local slot = handSlots[i]
        local e = list[i]
        if e and i <= n then
            slot:SetPoint("TOPLEFT", startX + (i - 1) * HAND_SPACING, -96)
            slot.abilityId = e.id
            slot.spellId = e.id
            slot.entryRef = e
            slot.rarity = e.rarity or 0
            slot.icon:SetTexture(SpellIcon(e.id))
            slot.lock:Show()
            if e.locked == 1 then
                -- closed GOLD padlock + gold ring = locked in
                slot.lock:SetTexture("Interface\\AddOns\\ClasslessWildcard\\lock_closed")
                slot.lock:SetVertexColor(1, 1, 1, 1)
                slot.ring:Show()
                slot.icon:SetVertexColor(1, 1, 1)
            else
                -- open grey padlock = will be rerolled
                slot.lock:SetTexture("Interface\\AddOns\\ClasslessWildcard\\lock_open")
                slot.lock:SetVertexColor(1, 1, 1, 0.8)
                slot.ring:Hide()
                slot.icon:SetVertexColor(0.8, 0.8, 0.8)
            end
            slot:Show()
        else
            slot.abilityId = nil
            slot.spellId = nil
            slot.entryRef = nil
            slot.glow:Hide(); slot.rays:Hide()
            slot:Hide()
        end
    end

    -- Deal-in animation. The die bounces in from off the left, rolls along the
    -- row, and each card appears as the die reaches it; past the last card the
    -- die runs on and fades out. Everything the OnUpdate below needs is worked
    -- out here, where the layout is already known.
    if CW.handAnimatePending then
        CW.handAnimatePending = nil
        if n > 0 then
            -- x of each card's centre, as an offset from the frame's centre,
            -- and the y the row sits at (frame is 460x210, cards 44 tall with
            -- their top edge 96 down)
            local xs = {}
            for i = 1, n do xs[i] = startX + (i - 1) * HAND_SPACING + 22 - 230 end
            CW.handAnim = {
                t0 = GetTime(), phase = "in", n = n, xs = xs, popped = {},
                slotX = startX, rowY = -13, spin = 0,
                fromX = xs[1] - 200,        -- off the left edge
                toX = xs[n] + 200,          -- off the right edge
            }
            handDie:Show()
            handDie:SetAlpha(0)
            for i = 1, HAND_SLOTS do
                handSlots[i]:SetAlpha(0)
                handSlots[i].glow:Hide(); handSlots[i].rays:Hide()
            end
        else
            CW.handAnim = nil
            handDie:Hide()
        end
    elseif not CW.handAnim then
        for i = 1, HAND_SLOTS do
            handSlots[i]:SetAlpha(1)
            if i <= n then rvFX.CardFX(handSlots[i], handSlots[i].rarity, 0) end
        end
    end
end
CW.RenderHand = RenderHand

-- in: bounce on from the left. roll: travel the row, dealing as it goes.
-- out: carry on past the last card and fade. pop: how long a card takes to
-- arrive once the die has reached it. lift: how far below its place a card
-- starts. spin: die frames per second (the atlas is 16 frames).
local HAND_IN_TIME, HAND_ROLL_TIME, HAND_OUT_TIME = 0.55, 0.95, 0.30
local HAND_POP_TIME, HAND_LIFT, HAND_BOUNCE, HAND_SPIN_RATE = 0.24, 14, 30, 34
hand:SetScript("OnUpdate", function(self, elapsed)
    -- An epic or legendary card keeps its starburst turning for as long as the
    -- hand is open, deal or no deal, so this runs before the animation check.
    rvFX.handRot = (rvFX.handRot or 0) + (elapsed or 0)
    for i = 1, HAND_SLOTS do
        local slot = handSlots[i]
        if slot.rays:IsShown() then
            rvFX.Spin(slot.rays, rvFX.handRot * (slot.spinRate or 0.2) * math.pi * 2)
        end
    end

    local a = CW.handAnim
    if not a then return end
    local now = GetTime()
    local t = now - a.t0
    local x, y = a.xs[a.n], a.rowY

    if a.phase ~= "done" then
        -- one continuous tumble for the whole run, timed rather than counted
        -- per frame so it looks the same at 30fps and at 144
        a.spin = a.spin + (elapsed or 0) * HAND_SPIN_RATE
        local idx = math.floor(a.spin) % 16
        handDie:SetTexCoord((idx % 8) / 8, (idx % 8 + 1) / 8,
                            math.floor(idx / 8) / 2, (math.floor(idx / 8) + 1) / 2)
    end

    if a.phase == "in" then
        local p = math.min(1, t / HAND_IN_TIME)
        local e = 1 - (1 - p) * (1 - p) * (1 - p)          -- ease out, fast then settling
        x = a.fromX + (a.xs[1] - a.fromX) * e
        -- two decaying hops, touching down on the row at the end of each
        y = a.rowY + math.abs(math.sin(p * math.pi * 2)) * HAND_BOUNCE * (1 - p)
        handDie:SetAlpha(p)
        if p >= 1 then a.phase = "roll"; a.t0 = now end
    elseif a.phase == "roll" then
        local p = math.min(1, t / HAND_ROLL_TIME)
        x = a.xs[1] + (a.xs[a.n] - a.xs[1]) * p
        handDie:SetAlpha(1)
        if p >= 1 then a.phase = "out"; a.t0 = now end
    elseif a.phase == "out" then
        local p = math.min(1, t / HAND_OUT_TIME)
        x = a.xs[a.n] + (a.toX - a.xs[a.n]) * p
        handDie:SetAlpha(1 - p)
        if p >= 1 then
            handDie:Hide()
            a.phase = "done"
        end
    end

    if a.phase ~= "done" then
        handDie:ClearAllPoints()
        handDie:SetPoint("CENTER", x, y)
        -- Every card the die has reached starts arriving. Read from the die's
        -- ACTUAL position rather than from the roll phase, so the first card
        -- deals on the same frame the run-in puts the die on top of it instead
        -- of a frame later.
        for i = 1, a.n do
            if not a.popped[i] and x >= a.xs[i] then
                a.popped[i] = now
                -- the card's OWN tier speaks, exactly as it would in the roll
                -- reveal: a tick for a common, a horn for a legendary
                local fx = rvFX.Tier(handSlots[i].rarity)
                if PlaySound then
                    pcall(PlaySound, fx.snd)
                    if fx.snd2 then pcall(PlaySound, fx.snd2) end
                end
            end
        end
    end

    -- Cards fade and rise into place from the moment the die reached them, and
    -- flash in their own colour as they land. A better card rises from further
    -- down and burns brighter on arrival before settling to its resting glow.
    local settled = (a.phase == "done")
    for i = 1, HAND_SLOTS do
        local slot = handSlots[i]
        if i <= a.n then
            local fx = rvFX.Tier(slot.rarity)
            local since = a.popped[i]
            local q = since and math.min(1, (now - since) / HAND_POP_TIME) or 0
            local e = 1 - (1 - q) * (1 - q)
            local lift = HAND_LIFT + fx.pop * 0.6
            slot:SetAlpha(e)
            slot:SetPoint("TOPLEFT", a.slotX + (i - 1) * HAND_SPACING, -96 - (1 - e) * lift)
            local boost = since and math.max(0, 1 - (now - since) / rvFX.cardFlash) or 0
            rvFX.CardFX(slot, slot.rarity, boost)
            -- the deal is not over until the last flash has burned down
            if q < 1 or boost > 0 then settled = false end
        end
    end
    if settled then CW.handAnim = nil end
end)

handRoll:SetScript("OnClick", function()
    -- One command: the server rerolls every unlocked ability from its own
    -- state. Firing one RR per entry from this snapshot went stale as soon as
    -- the first landed, so the rest came back "You do not own that ability".
    Send("RRALL")
    CW.handAnimatePending = true -- deal the new cards in with the die spin
    Send("OWN")
end)
handKeep:SetScript("OnClick", function()
    -- just close it: the hand is the whole point of this screen, and dropping
    -- the Character Advancement panel on top of a player who has finished with
    -- it is one modal too many. The panel is a click away on the minimap
    -- button whenever they want it.
    hand:Hide()
end)

hand:SetScript("OnShow", function()
    hand.ApplyLayers()
    ClasslessWildcardCharDB = ClasslessWildcardCharDB or {}
    ClasslessWildcardCharDB.handSeen = true   -- opened by any route: don't auto-open again
    -- the level free rolls end at is the server's to decide, so say what it says
    handHint:SetText("Click an ability to lock it in: |cffffd100gold ring + closed padlock = kept|r." ..
        " Roll Abilities rerolls only the unlocked ones. Free until level "
        .. (CW.state.freeReroll or 10) .. "!")
    CW.suppressReveals = true -- the hand shows results directly, no popups
    -- kill any reveal that slipped in before the hand opened
    CW.revealQueue = {}
    if reveal:IsShown() then reveal:Hide() end
    CW.revealAnim.phase = "idle"
    frame:Hide() -- one thing at a time: the hand has the stage
    CW.handOrder = nil -- fresh layout for a fresh look at the hand
    CW.handAnimatePending = true -- deal the opening hand in with the die spin
    Send("OWN")
end)
hand:SetScript("OnHide", function() CW.suppressReveals = false end)

-- exposed for tests / third-party extensions
CW.revealFrame, CW.revealKeep, CW.revealReroll = reveal, rvKeep, rvReroll
CW.revealDie = rvDie   -- exposed for tests
CW.handFrame, CW.handRoll, CW.handKeep = hand, handRoll, handKeep
CW.handSlots, CW.handDie = handSlots, handDie

-- ---------------------------------------------------------------------------
-- protocol handling
-- ---------------------------------------------------------------------------
-- Split on "|" into exactly one field per separator. The old gmatch version
-- ("([^|]*)|?") also produced a trailing empty capture at the end of the
-- string, so #p was always one more than the field count -- which quietly
-- broke any check that counted fields.
local function SplitPipes(msg)
    local out, pos = {}, 1
    while true do
        local a, b = string.find(msg, "|", pos, true)
        if not a then
            tinsert(out, string.sub(msg, pos))
            return out
        end
        tinsert(out, string.sub(msg, pos, a - 1))
        pos = b + 1
    end
end

local function ParseEntries(blob, fieldCount)
    local out = {}
    for entry in string.gmatch(blob or "", "([^;]+)") do
        local fields = {}
        for f in string.gmatch(entry, "([^:]+)") do
            tinsert(fields, tonumber(f) or 0)
        end
        if #fields >= fieldCount then
            tinsert(out, fields)
        end
    end
    return out
end

local collectingArch = false

local function HandleMessage(msg)
    local p = SplitPipes(msg)
    local kind = p[1]

    if kind == "S" then
        local s = CW.state
        s.mode, s.ae, s.te, s.pity, s.chance = tonumber(p[2]) or 255, tonumber(p[3]) or 0, tonumber(p[4]) or 0, tonumber(p[5]) or 0, tonumber(p[6]) or 0
        s.scrolls, s.level, s.deadline = tonumber(p[7]) or 0, tonumber(p[8]) or 1, tonumber(p[9]) or 5
        s.rebirth, s.rebirthCost = tonumber(p[10]) or 0, tonumber(p[11]) or 0
        -- Read every field by position, unconditionally. There used to be a
        -- branch here that treated a 16-field packet as a pre-merge server
        -- (one that sent ability and talent rerolls as two numbers) and folded
        -- them. That made the field count part of the protocol: adding a 16th
        -- field to the CURRENT packet would have been read as the old format
        -- and shifted every field after it by one, which is exactly the bug
        -- that once made the resource bars vanish. The addon ships inside the
        -- module and is installed from the same checkout as the server, so a
        -- mismatched pair is not a thing to support. Fields past the last one
        -- named here are ignored, so the server can grow the packet freely.
        s.rerolls = tonumber(p[12]) or 0
        s.universalResources = tonumber(p[13]) or 0
        s.scrollCost = tonumber(p[14]) or 0
        s.scrollBuy = tonumber(p[15]) or 0
        s.freeReroll = tonumber(p[16]) or 10   -- Wildcard.FreeRerollLevel
        CW.UpdateBarsVisibility()
        UpdateStatus()
        -- fresh Wildcard hero: lock & roll your starting hand
        if CW.pendingHand then
            CW.pendingHand = nil
            if CW.CanShowHand() then hand:Show() end
        end
        -- The server can put a Hero on Wildcard without the addon asking: a
        -- realm with AllowModeChoice = 0 deals the hand at first login, and the
        -- level deadline deals it to anyone who never chose. Neither goes
        -- through MODE, so nothing set pendingHand and the starting hand never
        -- appeared. Open it once per character, and only while the free-reroll
        -- window is still open; the dice crest reopens it after that.
        ClasslessWildcardCharDB = ClasslessWildcardCharDB or {}
        if not ClasslessWildcardCharDB.handSeen and CW.CanShowHand() then
            ClasslessWildcardCharDB.handSeen = true
            hand:Show()
        end
        -- level 10 can arrive while the hand is open: close it out rather than
        -- leaving a "free until level 10" screen up
        if hand:IsShown() and not CW.CanShowHand() then
            hand:Hide()
            frame:Show()
        end
        -- first-login onboarding: unchosen mode and still inside the window
        if s.mode == 255 and s.level < s.deadline and not frame:IsShown() and not wizard:IsShown() then
            ShowPathChoice()
        end

    elseif kind == "RU" then
        -- RU|<runic>|<maxRunic>|<type>,<ready> x6
        local s = CW.state
        s.runic = tonumber(p[2]) or 0
        s.runicMax = tonumber(p[3]) or 0
        local list = {}
        for i = 1, 6 do
            local field = p[3 + i]
            if field then
                local kindStr, readyStr = string.match(field, "^(%d+),(%d+)$")
                if kindStr then
                    list[i] = { kind = tonumber(kindStr), ready = readyStr == "1" }
                end
            end
        end
        s.runes = (next(list) ~= nil) and list or nil
        CW.UpdateBarsVisibility()

    elseif kind == "AB" then
        CW.abilPage = tonumber(p[3]) or 0
        CW.abilTotal = tonumber(p[4]) or 1
        CW.abilRows = {}
        for _, f in ipairs(ParseEntries(p[5], 5)) do
            tinsert(CW.abilRows, { id = f[1], rarity = f[2], cost = f[3], owned = f[4], passive = f[5], lvl = f[6] or 1, type = f[7] or 0 })
        end
        RenderList()

    elseif kind == "TB" then
        for _, f in ipairs(ParseEntries(p[2], 2)) do
            tinsert(CW.tabs, { id = f[1], class = f[2] })
        end
    elseif kind == "TBE" then
        -- tabs just arrived: fill the Talents pane with the current tree
        RequestTal(0)

    elseif kind == "TL" then
        CW.talPage = tonumber(p[3]) or 0
        CW.talTotal = tonumber(p[4]) or 1
        CW.talRows = {}
        for _, f in ipairs(ParseEntries(p[5], 6)) do
            tinsert(CW.talRows, { talentId = f[1], spell = f[2], rarity = f[3], owned = f[4], max = f[5], row = f[6], active = f[7] or 0 })
        end
        RenderList()

    elseif kind == "OA" then
        if not CW._collectingOwned then
            CW.owned = {}
            CW._collectingOwned = true
        end
        for _, f in ipairs(ParseEntries(p[2], 4)) do
            tinsert(CW.owned, { id = f[1], rarity = f[2], locked = f[3], source = f[4] })
        end
    elseif kind == "OAE" then
        CW._collectingOwned = false
        RenderList()
        if hand:IsShown() then CW.RenderHand() end

    elseif kind == "OT" then
        if not CW._collectingOwnedT then
            CW.ownedT = {}
            CW._collectingOwnedT = true
        end
        for _, f in ipairs(ParseEntries(p[2], 5)) do
            tinsert(CW.ownedT, { talentId = f[1], spell = f[2], rarity = f[3], rank = f[4], max = f[5] })
        end
    elseif kind == "OTE" then
        CW._collectingOwnedT = false
        RenderList()

    elseif kind == "AR" then
        if not collectingArch then
            CW.archetypes = {}
            collectingArch = true
        end
        tinsert(CW.archetypes, { id = tonumber(p[2]) or 0, name = p[3] or "?", desc = p[4] or "",
                                 count = tonumber(p[5]) or 0, ranks = tonumber(p[6]) or 0,
                                 following = (tonumber(p[7]) or 0) == 1 })
    elseif kind == "ARE" then
        if not collectingArch then CW.archetypes = {} end -- reply with no AR rows
        collectingArch = false
        CW.archetypesLoaded = true
        if wizard:IsShown() then
            ShowArchetypeChoices()
        elseif archFly:IsShown() then
            RenderArchFly()
        end

    elseif kind == "ST" then
        local s = CW.stats
        s.budget, s.unspent, s.perPoint = tonumber(p[2]) or 0, tonumber(p[3]) or 0, tonumber(p[4]) or 1
        for i = 1, 5 do
            s.alloc[i] = tonumber(p[4 + i]) or 0
        end
        s.enabled = tonumber(p[10]) or 1
        -- Rates for the "what is this stat doing for me" tooltips. Older
        -- servers do not send them; fall back to the shipped defaults so the
        -- tooltip still reads sensibly instead of showing zeroes.
        s.uniStats = (tonumber(p[11]) or 1) == 1
        s.apPerAgi = tonumber(p[12]) or 1
        s.rapPerAgi = tonumber(p[13]) or 1
        s.spPerInt = tonumber(p[14]) or 0.5
        s.strMeleeAP = tonumber(p[15]) or 2
        s.agiMeleeAP = tonumber(p[16]) or 0
        s.agiRangedAP = tonumber(p[17]) or 1
        s.critPerAgi = tonumber(p[18]) or 0
        s.spellCritPerInt = tonumber(p[19]) or 0
        s.mp5PerSpi = tonumber(p[20]) or 0
        s.hp5PerSpi = tonumber(p[21]) or 0
        -- the help panel quotes these rates, so rebuild it now they are known
        if CW.RefreshHelpText then CW.RefreshHelpText() end
        CW.statsPending = nil
        RenderList() -- refreshes the stats flyout when it is open

    elseif kind == "CFG" then
        -- classless pricing the browser needs to label costs honestly
        CW.talentCost = tonumber(p[2]) or 1
        CW.talentFlat = (tonumber(p[3]) or 1) == 1
        -- Whether Death Knight content is in the library. Absent from older
        -- servers, which is why the default is off rather than on: a missing
        -- field must not conjure a class button with nothing behind it.
        local dk = (tonumber(p[4]) or 0) == 1
        if dk ~= CW.dkEnabled then
            CW.dkEnabled = dk
            CW.LayoutClassStrip()
        end
        RenderList()

    elseif kind == "CP" then
        -- server-mirrored combo points (the stock client hides them for
        -- non-rogue classes); light the pips under the resource bars
        CW.state.comboPoints = tonumber(p[2]) or 0
        if barsFrame:IsShown() then CW.RefreshBars() end

    elseif kind == "RV" then
        -- a wildcard roll happened: refresh state (reroll charges/scrolls
        -- changed) and play the d20 reveal
        Send("STATE")
        if p[2] == "A" then
            CW.EnqueueReveal({ isTalent = false, entry = tonumber(p[3]) or 0, spell = tonumber(p[3]) or 0,
                               rarity = tonumber(p[4]) or 0, flags = tonumber(p[5]) or 0 })
        elseif p[2] == "T" then
            CW.EnqueueReveal({ isTalent = true, entry = tonumber(p[3]) or 0, spell = tonumber(p[4]) or 0,
                               rarity = tonumber(p[5]) or 0, rank = tonumber(p[6]) or 1, flags = tonumber(p[7]) or 0 })
        end

    elseif kind == "OK" then
        if p[2] == "MODE" then
            CW.pendingHand = true -- open the starting hand once state arrives
        end
        -- refresh whatever list is open after a successful operation
        if frame:IsShown() then CW.SetTab(CW.tab) end
        if hand:IsShown() then Send("OWN") end

    elseif kind == "ERR" then
        Print("|cffff4444" .. (p[2] or "Error") .. "|r")
        -- a refused reroll must not leave the die spinning forever
        if CW.CancelReroll then CW.CancelReroll() end
    end
end

-- ---------------------------------------------------------------------------
-- events & slash
-- ---------------------------------------------------------------------------
local events = CreateFrame("Frame")
events:RegisterEvent("CHAT_MSG_ADDON")
events:RegisterEvent("PLAYER_ENTERING_WORLD")
events:RegisterEvent("UPDATE_BINDINGS")
events:RegisterEvent("CINEMATIC_STOP")
events:SetScript("OnEvent", function(self, event, arg1, arg2, arg3, arg4)
    if event == "CHAT_MSG_ADDON" then
        if arg1 == PREFIX and arg4 == UnitName("player") then
            HandleMessage(arg2)
        end
    elseif event == "CINEMATIC_STOP" then
        CW.RefreshPanelArt()
    elseif event == "PLAYER_ENTERING_WORLD" then
        CW.RefreshPanelArt()
        CW.LoadBrowseChoices()
        CW.RestoreBarsPosition()
        Send("HELLO")
        if CW.ClaimHotkey then CW.ClaimHotkey() end
        if CW.RefreshMicroTooltip then CW.RefreshMicroTooltip() end
    elseif event == "UPDATE_BINDINGS" then
        -- the player rebound us in Key Bindings: keep the "(N)" suffix honest
        if CW.RefreshMicroTooltip then CW.RefreshMicroTooltip() end
    end
end)

frame:SetScript("OnShow", function()
    CW.RefreshPanelArt()
    Send("STATE")
    CW.SetTab(CW.tab)
    -- The first time this character opens the panel, greet them with the Help
    -- guide so both systems are explained up front (once per character).
    ClasslessWildcardCharDB = ClasslessWildcardCharDB or {}
    if not ClasslessWildcardCharDB.helpSeen and CW.helpFly then
        ClasslessWildcardCharDB.helpSeen = true
        CW.helpFly:Show()
    end
end)

SLASH_CLASSLESSWILDCARD1 = "/cw"
SLASH_CLASSLESSWILDCARD2 = "/classless"
SlashCmdList["CLASSLESSWILDCARD"] = function(msg)
    if msg == "help" then
        if not frame:IsShown() then frame:Show() end
        if CW.helpFly then
            if CW.helpFly:IsShown() then CW.helpFly:Hide() else CW.helpFly:Show() end
        end
        return
    elseif msg == "hand" then
        if hand:IsShown() then
            hand:Hide()
        elseif CW.CanShowHand() then
            hand:Show()
        else
            Print("The Starting Hand is only available to Wildcard Heroes below level 10. Reroll from |cffffff00My Build|r instead.")
        end
        return
    elseif msg == "testroll" then
        -- preview the reveal without a real roll (Fireball, random rarity).
        -- test = true keeps Reroll local: the ability is not really owned, so
        -- asking the server to reroll it just answers "you do not own that".
        CW.EnqueueReveal({ isTalent = false, entry = 133, spell = 133,
                           rarity = math.random(0, 4), flags = 0, test = true })
        return
    end
    if frame:IsShown() then frame:Hide() else frame:Show() end
end

-- ---------------------------------------------------------------------------
-- key bindings (Bindings.xml declares the actions; these are their handlers)
-- ---------------------------------------------------------------------------
BINDING_HEADER_CLASSLESSWILDCARD = "ClasslessWildcard"
BINDING_NAME_CLASSLESSWILDCARD_TOGGLE = "Toggle Hero Advancement"
BINDING_NAME_CLASSLESSWILDCARD_HELP = "Toggle the Help guide"
BINDING_NAME_CLASSLESSWILDCARD_BARS = "Toggle the resource bars"

function ClasslessWildcard_TogglePanel()
    if frame:IsShown() then frame:Hide() else frame:Show() end
end

function ClasslessWildcard_ToggleHelp()
    if not frame:IsShown() then frame:Show() end
    if CW.helpFly then
        if CW.helpFly:IsShown() then CW.helpFly:Hide() else CW.helpFly:Show() end
    end
end

function ClasslessWildcard_ToggleBars()
    SlashCmdList["CLASSLESSWILDCARDBARS"]("")
end

-- Claim a hotkey the first time this account runs the addon.
--
-- "N" is the stock Talents key, and this mod suppresses native talents
-- outright (no talent points, talent-frame purchases blocked), so that key
-- opens a dead frame -- taking it over is the whole point. We only claim N
-- while it still IS the talent binding: if the player has put something of
-- their own there we leave it alone and fall back to a genuinely free key.
-- Everything is rebindable under Key Bindings > ClasslessWildcard.
local PREFERRED_KEY = "N"
local REPLACEABLE_ACTIONS = { TOGGLETALENTS = true }
local FALLBACK_KEYS = { "J", "Y", "G", "K" }

function CW.ClaimHotkey()
    ClasslessWildcardDB = ClasslessWildcardDB or {}
    if ClasslessWildcardDB.hotkeyClaimed then return end
    -- bindings can't be changed in combat; try again on the next load
    if InCombatLockdown and InCombatLockdown() then return end
    if not SetBinding or not SaveBindings or not GetBindingAction then return end

    -- already bound (by us before, or by the player): leave it alone
    if GetBindingKey and GetBindingKey("CLASSLESSWILDCARD_TOGGLE") then
        ClasslessWildcardDB.hotkeyClaimed = true
        return
    end

    local function Claim(key, allowReplace)
        local inUse = GetBindingAction(key)
        local occupied = inUse and inUse ~= ""
        if occupied and not (allowReplace and REPLACEABLE_ACTIONS[inUse]) then
            return false
        end
        if not SetBinding(key, "CLASSLESSWILDCARD_TOGGLE") then
            return false
        end
        pcall(SaveBindings, GetCurrentBindingSet and GetCurrentBindingSet() or 1)
        ClasslessWildcardDB.hotkeyClaimed = true
        if CW.RefreshMicroTooltip then CW.RefreshMicroTooltip() end
        Print("Hotkey |cffffff00" .. key .. "|r opens the Hero Advancement panel"
            .. (occupied and " (it replaced the unused Talents frame)" or "")
            .. ". Rebind it under Key Bindings > ClasslessWildcard.")
        return true
    end

    if Claim(PREFERRED_KEY, true) then return end
    for _, key in ipairs(FALLBACK_KEYS) do
        if Claim(key, false) then return end
    end

    ClasslessWildcardDB.hotkeyClaimed = true
    Print("No free hotkey was available. Bind |cffffff00Toggle Hero Advancement|r under Key Bindings > ClasslessWildcard.")
end

-- exposed for debugging and third-party extensions
_G.ClasslessWildcard_API = CW

Print("ClasslessWildcard |cffffd100v" .. ADDON_VERSION .. "|r loaded. Type |cffffff00/cw|r to open the Hero Advancement panel, or |cffffff00/cw help|r for a guide.")
