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

-- ---------------------------------------------------------------------------
-- main frame: "Character Advancement" — Ascension-style single-screen layout
-- (class strip on top, Abilities + Talents panes, My Build sidebar, bottom bar)
-- ---------------------------------------------------------------------------
local frame = CreateFrame("Frame", "ClasslessWildcardFrame", UIParent)
frame:SetWidth(950); frame:SetHeight(600)
frame:SetPoint("CENTER")
frame:SetBackdrop({
    bgFile = "Interface\\AddOns\\ClasslessWildcard\\panel_bg", -- baked layout art
    edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
    tile = false, edgeSize = 32,
    insets = { left = 0, right = 0, top = 0, bottom = 0 },
})
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

titleBtn:SetScript("OnEnter", function(self)
    titleGlow:SetAlpha(0.9)
    titleIcon:SetVertexColor(1.3, 1.3, 1.3)
    GameTooltip:SetOwner(self, "ANCHOR_BOTTOMRIGHT")
    local s = CW.state
    if s.mode ~= 1 then
        GameTooltip:SetText("Wildcard rolls")
        GameTooltip:AddLine("Only Wildcard Heroes roll the dice for abilities.", 0.8, 0.8, 0.8, true)
    elseif (s.level or 1) < 10 then
        GameTooltip:SetText("|cffffd100Roll your Starting Hand|r")
        GameTooltip:AddLine("Click to reroll your starter abilities.", 0.3, 1, 0.3, true)
        GameTooltip:AddLine("Free before level 10 -- lock the ones you like.", 0.6, 0.9, 0.6, true)
    else
        GameTooltip:SetText("Starting Hand (closed)")
        GameTooltip:AddLine("Free starter rolls end at level 10.", 0.8, 0.8, 0.8, true)
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
    return s.mode == 1 and (s.level or 1) < 10
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
        CW.abilPage = 0
        Send("ABIL " .. classId .. " 0")
        -- follow the class across: jump the Talents pane to that class's first
        -- tree, so both panes are showing the same class
        for idx, t in ipairs(CW.tabs) do
            if t.class == classId then
                CW.tabIndex = idx
                CW.talPage = 0
                Send("TAL " .. t.id .. " 0")
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

-- One archetype row: name and ability count on the first line, the
-- description under it (it may wrap to a second line), and a button on the
-- right. The panel flyout and the first-login wizard both use these.
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
    r.apply = CreateFrame("Button", nil, r, "UIPanelButtonTemplate")
    r.apply:SetWidth(70); r.apply:SetHeight(22)
    r.apply:SetPoint("RIGHT", 0, 0)
    r.apply:SetText(buttonText)
    r.apply.defaultText = buttonText
    r:Hide()
    return r
end

-- Fills rows from an archetype list; onChoose(arch) runs when a row's button
-- is clicked. Returns how many rows are showing.
local function FillArchRows(rows, list, onChoose)
    local shown = 0
    for i, r in ipairs(rows) do
        local arch = list[i]
        if arch then
            local count = (arch.count == 1) and "1 ability" or (arch.count .. " abilities")
            if (arch.ranks or 0) > 0 then count = count .. ", " .. arch.ranks .. " talent ranks" end
            r.name:SetText("|cffffff00" .. arch.name .. "|r" .. (arch.following and "  |cff00ff00following|r" or ""))
            r.desc:SetText(arch.desc .. "  |cffaaaaaa" .. count .. "|r")
            r.apply:SetText(arch.following and "Stop" or r.apply.defaultText)
            r.apply:SetScript("OnClick", function() onChoose(arch) end)
            r:Show()
            shown = shown + 1
        else
            r:Hide()
        end
    end
    return shown
end

archFly.rows = {}
for i = 1, 6 do
    local r = MakeArchRow(archFly, 432, "Follow")
    r:SetPoint("TOPLEFT", 14, -72 - (i - 1) * ARCH_ROW_H)
    archFly.rows[i] = r
end

-- Fills the flyout from CW.archetypes (cached from the last AR/ARE reply) and
-- sizes it to the rows shown.
local function RenderArchFly()
    local shown = FillArchRows(archFly.rows, CW.archetypes or {}, function(arch)
        Send("ARCHAPPLY " .. (arch.following and 0 or arch.id)) -- 0 = stop following
        archFly:Hide()
        CW.SetTab("HERO") -- show what the archetype bought
    end)
    if shown > 0 then
        archFly.intro:SetText(archFly.INTRO)
    elseif CW.archetypesLoaded then
        archFly.intro:SetText("No archetypes are configured on this realm.")
    else
        archFly.intro:SetText("Loading...")
    end
    archFly:SetHeight(72 + math.max(shown, 1) * ARCH_ROW_H + 8)
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
"Unlearning an ability refunds what you paid, |cffffd100Respec|r reshuffles your talents for gold, and every ability line you own |cff00ff00ranks up on its own|r as you level.",
"|cffffd100Archetypes|r are builds you follow from level 1 to 80. Pick one from the |cffffd100Archetypes|r button on this panel or at the Hero Advancement NPC: it replaces your build (abilities refunded, the respec fee if you own talents) and from then on buys its abilities and talents for you as each becomes available. Everything it buys is a normal purchase, and you can stop following it at any time.",
"",
"|cffff8800==  WILDCARD  --  the dice choose  ==|r",
"The server rolls abilities and talents for you on a fixed schedule:",
"   |cff00ff00Level 1:|r  4 random abilities to begin.",
"   |cff00ff00From level 10:|r  one roll every level, alternating -- an ability on the even levels, a talent on the odd ones. Talents come no more often than abilities because a talent roll can land on rank 5 outright.",
"Rolls are rarity-weighted, so legendaries are the rarest.",
"A talent roll also rolls the |cffffd100rank|r you land on, and the rank IS its rarity: rank 1 common, rank 2 uncommon, rank 3 rare, rank 4 epic, |cffff8000rank 5 legendary|r. The rank is drawn from anything above what you already have, not one step up, so a talent you hold at rank 2 can jump straight to rank 5 -- and a talent you have never seen can arrive at its top rank. A high rank is the jackpot: rolls cost you nothing, so landing on rank 5 hands you the full-strength talent for free, where a Classless Hero pays for every rank up to it. Rolling into a talent you already own upgrades it and rolls again, up to four times in one go.",
"You steer your luck:",
"   |cffffd100Rerolls|r -- every level from 10 grants you 3 reroll charges, and rerolls are free below level 10. One pool, spent on abilities or talents alike. Reroll straight from the popup, or later from |cffffd100My Build|r using the circular arrow next to anything you own.",
"   |cffffd100Lock|r -- protect an ability so a later roll can't overwrite it.",
"   |cffffd100Synergy & pity|r -- some rolls are narrowed to abilities that fit the classes you already own. The chance of that starts at 10% and climbs by 10 points every time you reroll, so a cold streak keeps improving your odds until it pays off, then resets. Anything you reroll also goes on a cooldown, so the reroll can never hand you straight back what you just got rid of. That cooldown lasts 24 rolls, which is around 16 levels, so rerolling something is closer to a lasting decision than a do-over. If you reroll through everything available at your level, the cooldowns lift so you always get something you can actually use.",
"   |cffffd100Reroll Scrolls|r -- one scroll, good for an ability OR a talent, for when your charges run dry. Earn them, buy them from the Hero Advancement NPC, or use the |cffffd100Buy Scroll|r button on this panel (the price scales with level -- silver early, gold near the cap).",
"Open the roll screen any time with the |cffffd100dice crest|r at the top-left of this window.",
"",
"|cff40ff40==  Shared by both paths  ==|r",
"   |cffffd100Universal resources|r -- you carry mana, rage AND energy at once, and each spell draws its own, so nothing is ever unusable. Toggle the extra bars with |cffffd100/cwbars|r.",
"   |cffffd100Primary stats|r -- you get points every level to spend across STR / AGI / STA / INT / SPI, and reallocating them is free at any time. Open the |cffffd100Stats|r button and hover any stat to see exactly what it is doing for your Hero right now.",
"      |cffffd100Strength|r -- " .. StatPerPoint(1) .. " per point.",
"      |cffffd100Agility|r -- " .. StatPerPoint(2) .. " per point.",
"      |cffffd100Stamina|r -- " .. StatPerPoint(3) .. " per point.",
"      |cffffd100Intellect|r -- " .. StatPerPoint(4) .. " per point.",
"      |cffffd100Spirit|r -- increases " .. StatPerPoint(5) .. ". Mana regeneration pauses for 5 seconds after you cast. Talents such as Meditation, Arcane Meditation and Intensity let it continue while casting, and any Hero can learn them.",
"   Every stat does something for every Hero, so spend toward the build you are playing.",
"   |cffffd100Proficiencies|r -- every armor and weapon type, dual wield included, is trained for you automatically.",
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
    statFly:Hide(); archFly:Hide()
    if helpFly:IsShown() then helpFly:Hide() else helpFly:Show() end
end)

statsBtn:SetScript("OnClick", function()
    helpFly:Hide(); archFly:Hide()
    if statFly:IsShown() then
        statFly:Hide()
    else
        Send("STATS")
        statFly:Show()
        if CW.RenderStats then CW.RenderStats() end -- render cached data now
    end
end)

archBtn:SetScript("OnClick", function()
    helpFly:Hide(); statFly:Hide()
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
            if s.mode == 1 then
                w.sub:SetText((RARITY_NAMES[e.rarity] or "") .. lvlText)
                w.tipLine = "Dealt by Wildcard rolls"
                w:SetScript("OnClick", nil)
            else
                w.sub:SetText(e.cost .. " Ability Essence" .. lvlText)
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
            if s.mode == 1 then
                w.sub:SetText((RARITY_NAMES[t.rarity] or "") .. LevelTag(tlvl, s.level))
                w.tipLine = "Rolled at level-up"
                w:SetScript("OnClick", nil)
            else
                -- price comes from the server (CFG), not an assumption: a
                -- talent costs one point for ALL its ranks by default
                local cost = CW.talentCost or 1
                local costText = cost .. " Talent Essence"
                    .. (CW.talentFlat and " (all ranks)" or "/rank")
                w.sub:SetText("Row " .. (t.row + 1) .. "  " .. costText .. LevelTag(tlvl, s.level))
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
            r.name:SetText(SpellLabel(it.spell, it.rarity) .. suffix)
            if s.mode == 1 then
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

-- The module's own contribution from a stat, worked out with the same maths
-- the server uses so the two agree.
local function StatContribution(i, value)
    local s = CW.stats
    if not s.uniStats then return nil end
    if i == 2 then
        local ap, rap = math.floor(value * (s.apPerAgi or 0)), math.floor(value * (s.rapPerAgi or 0))
        if ap <= 0 and rap <= 0 then return nil end
        return "+" .. ap .. " melee and +" .. rap .. " ranged attack power"
    elseif i == 4 then
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
    Send("ABIL " .. CLASS_ORDER[CW.classIndex] .. " " .. CW.abilPage)
    if #CW.tabs == 0 then
        Send("TABS")
    elseif CW.tabs[CW.tabIndex] then
        Send("TAL " .. CW.tabs[CW.tabIndex].id .. " " .. CW.talPage)
    end
    Send("OWN"); Send("OWNT")
    if key == "STAT" then Send("STATS"); statFly:Show() end
    if statFly:IsShown() then Send("STATS") end
    RenderList()
end

-- pane pagers / tree selector ------------------------------------------------------
abilPrev:SetScript("OnClick", function()
    if CW.abilPage > 0 then Send("ABIL " .. CLASS_ORDER[CW.classIndex] .. " " .. (CW.abilPage - 1)) end
end)
abilNext:SetScript("OnClick", function()
    if CW.abilPage + 1 < CW.abilTotal then Send("ABIL " .. CLASS_ORDER[CW.classIndex] .. " " .. (CW.abilPage + 1)) end
end)
treeLeft:SetScript("OnClick", function()
    if #CW.tabs > 0 then
        CW.tabIndex = CW.tabIndex > 1 and CW.tabIndex - 1 or #CW.tabs
        CW.talPage = 0
        Send("TAL " .. CW.tabs[CW.tabIndex].id .. " 0")
    end
end)
treeRight:SetScript("OnClick", function()
    if #CW.tabs > 0 then
        CW.tabIndex = CW.tabIndex < #CW.tabs and CW.tabIndex + 1 or 1
        CW.talPage = 0
        Send("TAL " .. CW.tabs[CW.tabIndex].id .. " 0")
    end
end)
talPrev:SetScript("OnClick", function()
    if CW.talPage > 0 and CW.tabs[CW.tabIndex] then
        Send("TAL " .. CW.tabs[CW.tabIndex].id .. " " .. (CW.talPage - 1))
    end
end)
talNext:SetScript("OnClick", function()
    if CW.talPage + 1 < CW.talTotal and CW.tabs[CW.tabIndex] then
        Send("TAL " .. CW.tabs[CW.tabIndex].id .. " " .. (CW.talPage + 1))
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
local archRows = {}
for i = 1, 6 do
    local r = MakeArchRow(wizard, WIZ_ARCH_W - 40, "Choose")
    r:SetPoint("TOPLEFT", 20, -84 - (i - 1) * ARCH_ROW_H)
    archRows[i] = r
end
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
    for _, r in ipairs(archRows) do r:Hide() end
    archSkip:Hide()
    wizard:Show()
end

local function ShowArchetypeChoices()
    wizTitle:SetText("Pick a Starter Archetype")
    wizText:SetWidth(WIZ_ARCH_W - 50)
    wizClassless:Hide(); wizWildcard:Hide(); wizLater:Hide()
    local shown = FillArchRows(archRows, CW.archetypes or {}, function(arch)
        Send("ARCHAPPLY " .. arch.id)
        wizard:Hide()
        frame:Show()
        CW.SetTab("HERO")
    end)
    if shown > 0 then
        wizText:SetText("An archetype is a build you follow: its abilities and talents are bought for you as you level, all the way to 80. Change or stop it later from the Archetypes button.")
    else
        wizText:SetText("No archetypes are configured on this realm.")
    end
    wizard:SetWidth(WIZ_ARCH_W)
    wizard:SetHeight(84 + math.max(shown, 1) * ARCH_ROW_H + 52)
    archSkip:Show()
    wizard:Show()
end
CW.wizard, CW.wizArchRows, CW.wizArchSkip = wizard, archRows, archSkip
CW.wizClassless, CW.wizWildcard, CW.wizLater = wizClassless, wizWildcard, wizLater
CW.wizTitle, CW.wizText = wizTitle, wizText
CW.ShowPathChoice = ShowPathChoice

-- ---------------------------------------------------------------------------
-- universal resource bars: the client tracks mana/rage/energy for every
-- character; the default UI only draws the chassis bar. These mini-bars show
-- the other pools (movable; /cwbars toggles them).
-- ---------------------------------------------------------------------------
local POWER_INFO = {
    { index = 0, name = "Mana",   r = 0.25, g = 0.45, b = 1.00 },
    { index = 1, name = "Rage",   r = 1.00, g = 0.25, b = 0.25 },
    { index = 3, name = "Energy", r = 1.00, g = 0.90, b = 0.25 },
}

local barsFrame = CreateFrame("Frame", "ClasslessWildcardBars", UIParent)
barsFrame:SetWidth(160); barsFrame:SetHeight(58)
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
barsFrame:RegisterForDrag("LeftButton")
barsFrame:SetScript("OnDragStart", barsFrame.StartMoving)
barsFrame:SetScript("OnDragStop", barsFrame.StopMovingOrSizing)
barsFrame:Hide()

local powerBars = {}
for i, info in ipairs(POWER_INFO) do
    local bar = CreateFrame("StatusBar", nil, barsFrame)
    bar:SetWidth(146); bar:SetHeight(14)
    bar:SetPoint("TOPLEFT", 7, -6 - (i - 1) * 17)
    bar:SetStatusBarTexture("Interface\\TargetingFrame\\UI-StatusBar")
    bar:SetStatusBarColor(info.r, info.g, info.b)
    bar:SetMinMaxValues(0, 100)
    bar.label = bar:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    bar.label:SetPoint("CENTER", 0, 0)
    bar.powerIndex = info.index
    bar.powerName = info.name
    -- click a pool to make it the MAIN bar on the default unit frame
    bar:EnableMouse(true)
    bar:SetScript("OnMouseUp", function(self)
        Send("BAR " .. self.powerIndex)
    end)
    bar:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:AddLine(self.powerName)
        GameTooltip:AddLine("Click to make this your main resource bar", 1, 1, 1)
        GameTooltip:Show()
    end)
    bar:SetScript("OnLeave", function() GameTooltip:Hide() end)
    powerBars[i] = bar
end

-- combo points: always visible under the bars (the default target frame also
-- shows them, for any chassis, whenever the server awards them)
local comboDots = {}
for i = 1, 5 do
    local bg = barsFrame:CreateTexture(nil, "ARTWORK")
    bg:SetWidth(12); bg:SetHeight(16)
    bg:SetTexture("Interface\\ComboFrame\\ComboPoint")
    bg:SetTexCoord(0, 0.375, 0, 1)
    local shine = barsFrame:CreateTexture(nil, "OVERLAY")
    shine:SetWidth(8); shine:SetHeight(16)
    shine:SetPoint("CENTER", bg, "CENTER", 0, 0)
    shine:SetTexture("Interface\\ComboFrame\\ComboPoint")
    shine:SetTexCoord(0.375, 0.5625, 0, 1)
    shine:SetAlpha(0)
    comboDots[i] = { bg = bg, shine = shine }
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

local RUNE_SIZE = 18
local runePips = {}
for i = 1, 6 do
    local holder = CreateFrame("Frame", nil, barsFrame)
    holder:SetWidth(RUNE_SIZE); holder:SetHeight(RUNE_SIZE)

    local rune = holder:CreateTexture(nil, "ARTWORK")
    rune:SetAllPoints(holder)

    -- the ring the player frame draws around a real Death Knight's runes
    local ring = holder:CreateTexture(nil, "OVERLAY")
    ring:SetWidth(RUNE_SIZE * 1.45); ring:SetHeight(RUNE_SIZE * 1.45)
    ring:SetPoint("CENTER", holder, "CENTER", 0, 0)
    if not ring:SetTexture("Interface\\PlayerFrame\\UI-PlayerFrame-Deathknight-Ring") then
        ring:Hide()
    end

    holder:Hide()
    runePips[i] = { frame = holder, rune = rune, ring = ring }
end
CW.runePips = runePips

local runicBar = CreateFrame("StatusBar", nil, barsFrame)
runicBar:SetWidth(136); runicBar:SetHeight(8)
runicBar:SetStatusBarTexture("Interface\\TargetingFrame\\UI-StatusBar")
runicBar:SetStatusBarColor(0.00, 0.82, 1.00)
runicBar:SetMinMaxValues(0, 1)
runicBar:SetValue(0)
runicBar:Hide()
local runicBg = runicBar:CreateTexture(nil, "BACKGROUND")
runicBg:SetAllPoints(runicBar)
runicBg:SetTexture(0, 0, 0, 0.5)
CW.runicBar = runicBar

function CW.RefreshBars()
    local displayed = UnitPowerType("player")
    local shown = 0
    for _, bar in ipairs(powerBars) do
        local maxPower = UnitPowerMax("player", bar.powerIndex)
        -- with universal resources active, ALWAYS render all three pools —
        -- a 0/0 bar is a visible bug report, not something to hide
        if (maxPower and maxPower > 0) or CW.state.universalResources == 1 then
            maxPower = maxPower or 0
            local cur = UnitPower("player", bar.powerIndex) or 0
            bar:SetMinMaxValues(0, math.max(1, maxPower))
            bar:SetValue(cur)
            -- the pool currently shown as the MAIN bar gets a gold marker
            local marker = (bar.powerIndex == displayed) and "|cffffd100\194\187|r " or ""
            bar.label:SetText(marker .. bar.powerName .. ": " .. cur .. "/" .. maxPower)
            shown = shown + 1
            bar:SetPoint("TOPLEFT", 7, -6 - (shown - 1) * 17)
            bar:Show()
        else
            bar:Hide()
        end
    end

    -- The stock client hides combo points for non-rogue classes (Wow.exe gates
    -- GetComboPoints), so the server mirrors the real count over the addon
    -- channel ("CP|n"). Use whichever source knows more.
    local cp = CW.state.comboPoints or 0
    local ok, ccp = pcall(GetComboPoints, "player", "target")
    if ok and ccp and ccp > cp then cp = ccp end
    for i = 1, 5 do
        comboDots[i].bg:SetPoint("TOPLEFT", 12 + (i - 1) * 20, -8 - shown * 17)
        comboDots[i].shine:SetAlpha(i <= cp and 1 or 0)
    end

    -- runes, drawn under the combo pips when the server is mirroring them
    local extra = 0
    local runes = CW.state.runes
    if runes then
        local top = -8 - shown * 17 - 20
        for i = 1, 6 do
            local r = runes[i]
            local pip = runePips[i]
            if r then
                local kind = r.kind or 0
                -- a rune on cooldown is dimmed rather than hidden, so the row
                -- never changes width and the eye can count what is missing
                local ready = r.ready
                if not pip.rune:SetTexture(RUNE_TEXTURE[kind] or RUNE_TEXTURE[0]) then
                    local c = RUNE_COLOR[kind] or RUNE_COLOR[0]
                    pip.rune:SetTexture(c[1], c[2], c[3])
                end
                pip.rune:SetVertexColor(1, 1, 1, 1)
                pip.rune:SetAlpha(ready and 1 or 0.30)
                if pip.rune.SetDesaturated then
                    pip.rune:SetDesaturated(not ready)
                end
                pip.ring:SetAlpha(ready and 1 or 0.45)
                pip.frame:ClearAllPoints()
                pip.frame:SetPoint("TOPLEFT", barsFrame, "TOPLEFT", 14 + (i - 1) * 22, top)
                pip.frame:Show()
            else
                pip.frame:Hide()
            end
        end
        extra = extra + 20

        if (CW.state.runicMax or 0) > 0 then
            runicBar:SetPoint("TOPLEFT", 12, top - 18)
            runicBar:SetMinMaxValues(0, CW.state.runicMax)
            runicBar:SetValue(CW.state.runic or 0)
            runicBar:Show()
            extra = extra + 12
        else
            runicBar:Hide()
        end
    else
        for i = 1, 6 do runePips[i].frame:Hide() end
        runicBar:Hide()
    end

    barsFrame:SetHeight(shown * 17 + 30 + extra)
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
    else
        barsFrame:Hide()
    end
end

local barsElapsed = 0
barsFrame:SetScript("OnUpdate", function(self, elapsed)
    barsElapsed = barsElapsed + (elapsed or 0)
    if barsElapsed >= 0.2 then
        barsElapsed = 0
        CW.RefreshBars()
    end
end)

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
SlashCmdList["CLASSLESSWILDCARDBARS"] = function()
    ClasslessWildcardDB = ClasslessWildcardDB or {}
    ClasslessWildcardDB.hideBars = not ClasslessWildcardDB.hideBars
    CW.UpdateBarsVisibility()
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

local rvGlow = reveal:CreateTexture(nil, "BORDER")
rvGlow:SetWidth(310); rvGlow:SetHeight(310)
rvGlow:SetPoint("CENTER", 0, 26)
rvGlow:SetTexture("Interface\\AddOns\\ClasslessWildcard\\glow")
rvGlow:SetBlendMode("ADD")

-- The icon sits BEHIND the die so the frame's own octagonal window masks it --
-- a square icon drawn over the top covers the frame and looks pasted on. The
-- window is 34% of the frame (measured from the art), so the icon is sized just
-- over that: it fills the hole edge to edge and the frame trims its corners.
local rvIcon = reveal:CreateTexture(nil, "ARTWORK")
rvIcon:SetPoint("CENTER", 0, 26)

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
rvSub:SetPoint("CENTER", 0, -164)

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

local function ShowResult()
    local d = rvAnim.data
    rvAnim.phase = "shown"
    local rgb = RARITY_RGB[d.rarity or 0] or RARITY_RGB[0]
    rvGlow:SetAlpha(0.7)
    rvGlow:SetVertexColor(rgb[1], rgb[2], rgb[3])
    -- swap to the rarity die frame; the spell icon shows through its window
    -- (4x2 atlas of 256px frames — the client caps textures at 1024px)
    local r = math.min(d.rarity or 0, 4)
    local col, rowi = r % 4, math.floor(r / 4)
    rvDie:SetTexture(REVEAL_ATLAS)
    rvDie:SetTexCoord(col / 4, (col + 1) / 4, rowi / 2, (rowi + 1) / 2)
    -- The artwork's window is a circle 32% across the frame, so the die is
    -- drawn large (280px) to make that opening a usable 90px. The icon is
    -- sized just past it: it fills the window with no seam and the frame masks
    -- the square corners, which land well inside the opaque face.
    rvDie:SetWidth(280); rvDie:SetHeight(280)
    rvDie:Show()
    rvIcon:SetWidth(96); rvIcon:SetHeight(96)
    rvIcon:SetTexture(SpellIcon(d.spell))
    rvIcon:SetTexCoord(0.08, 0.92, 0.08, 0.92)   -- trim the icon's own dark border
    rvIcon:Show()
    if d.isTalent then
        rvTitle:SetText("Talent Unlocked!")
        -- rank IS the rarity for talents, so it is colored and shown large
        local rgbHex = string.format("|cff%02x%02x%02x", rgb[1] * 255, rgb[2] * 255, rgb[3] * 255)
        rvName:SetText(SpellLabel(d.spell, d.rarity) .. "  " .. rgbHex .. "Rank " .. (d.rank or 1) .. "|r")
    else
        rvTitle:SetText("Ability Unlocked!")
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
    -- reroll button shows what the player can actually spend
    local s = CW.state
    local charges = (s.rerolls or 0) + (s.scrolls or 0)
    if (s.level or 1) < 10 then
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
    if PlaySound then pcall(PlaySound, "LEVELUPSOUND") end
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
    rvDie:SetTexture(SPIN_ATLAS)
    SetDieFrame(0)
    rvDie:SetWidth(205); rvDie:SetHeight(205)
    rvDie:Show()
    reveal:Show()
end

local function NextReveal()
    reveal:Hide()
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
    rvDie:SetTexture(SPIN_ATLAS)
    SetDieFrame(0)
    rvDie:SetWidth(205); rvDie:SetHeight(205)
    rvDie:Show()
end
CW.AwaitReroll = AwaitReroll

reveal:SetScript("OnUpdate", function()
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
            rvGlow:SetAlpha(1)
            return
        end
        local e = 1 - (1 - p) * (1 - p)      -- ease-out: fast spin, slows down
        SetDieFrame(math.floor(e * 40))
        rvGlow:SetAlpha(p * 0.9)
    elseif rvAnim.phase == "burst" then
        local p = (GetTime() - rvAnim.t0) / BURST_TIME
        if p >= 1 then
            ShowResult()
            return
        end
        rvGlow:SetAlpha(1 - p * 0.3)
        local s = 205 + 75 * p               -- die "expands" into the light
        rvDie:SetWidth(s); rvDie:SetHeight(s)
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

local HAND_SLOTS = 8
local HAND_SPACING = 56
local handSlots = {}
-- spinning die shown while the hand rolls in (same atlas as the reveal)
local handDie = hand:CreateTexture(nil, "OVERLAY")
handDie:SetWidth(96); handDie:SetHeight(96)
handDie:SetPoint("CENTER", 0, 0)
handDie:SetTexture("Interface\\AddOns\\ClasslessWildcard\\d20_spin")
handDie:Hide()

for i = 1, HAND_SLOTS do
    local slot = CreateFrame("Button", nil, hand)
    slot:SetWidth(44); slot:SetHeight(44)
    slot:SetPoint("TOPLEFT", 40 + (i - 1) * HAND_SPACING, -96)
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
local function OrderedHand()
    local byId = {}
    for _, e in ipairs(CW.owned) do byId[e.id] = e end

    local slots, used = {}, {}
    for i, id in ipairs(CW.handOrder or {}) do
        if byId[id] then
            slots[i] = id
            used[id] = true
        end
    end
    local fresh = {}
    for _, e in ipairs(CW.owned) do
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
            slot:Hide()
        end
    end

    -- deal-in animation (die spins, then cards pop in one by one)
    if CW.handAnimatePending then
        CW.handAnimatePending = nil
        CW.handAnim = { t0 = GetTime(), phase = "spin" }
        handDie:Show()
        for i = 1, HAND_SLOTS do handSlots[i]:SetAlpha(0) end
    elseif not CW.handAnim then
        for i = 1, HAND_SLOTS do handSlots[i]:SetAlpha(1) end
    end
end
CW.RenderHand = RenderHand

local HAND_SPIN_TIME, HAND_POP_STEP, HAND_POP_TIME = 1.0, 0.14, 0.28
hand:SetScript("OnUpdate", function()
    local a = CW.handAnim
    if not a then return end
    local now = GetTime()
    if a.phase == "spin" then
        local p = (now - a.t0) / HAND_SPIN_TIME
        if p >= 1 then
            a.phase = "pop"
            a.t0 = now
            handDie:Hide()
            if PlaySound then pcall(PlaySound, "LEVELUPSOUND") end
            return
        end
        local e = 1 - (1 - p) * (1 - p)
        local idx = math.floor(e * 32) % 16
        handDie:SetTexCoord((idx % 8) / 8, (idx % 8 + 1) / 8, math.floor(idx / 8) / 2, (math.floor(idx / 8) + 1) / 2)
    elseif a.phase == "pop" then
        local done = true
        for i = 1, HAND_SLOTS do
            local slot = handSlots[i]
            if slot:IsShown() then
                local p = (now - a.t0 - (i - 1) * HAND_POP_STEP) / HAND_POP_TIME
                if p < 0 then p = 0 end
                if p > 1 then p = 1 else done = false end
                slot:SetAlpha(p)
            end
        end
        if done then
            CW.handAnim = nil
        end
    end
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
    hand:Hide()
    frame:Show() -- now show the full Character Advancement screen
end)

hand:SetScript("OnShow", function()
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
CW.handFrame, CW.handRoll, CW.handKeep = hand, handRoll, handKeep

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
        -- Count fields, don't probe for nil: the current packet is 15 fields
        -- and the pre-merge one was 16 (it carried ability and talent rerolls
        -- separately). Probing p[16] matched BOTH, because SplitPipes used to
        -- append a trailing empty string -- so every field after it was read
        -- one place out, and universalResources picked up the scroll price,
        -- which is why the resource bars vanished.
        if #p >= 16 then
            -- older server, still sending the two reroll fields: fold them so
            -- the addon keeps working until the core is rebuilt
            s.rerolls = (tonumber(p[12]) or 0) + (tonumber(p[13]) or 0)
            s.universalResources = tonumber(p[14]) or 0
            s.scrollCost = tonumber(p[15]) or 0
            s.scrollBuy = tonumber(p[16]) or 0
        else
            s.rerolls = tonumber(p[12]) or 0
            s.universalResources = tonumber(p[13]) or 0
            s.scrollCost = tonumber(p[14]) or 0
            s.scrollBuy = tonumber(p[15]) or 0
        end
        CW.UpdateBarsVisibility()
        UpdateStatus()
        -- fresh Wildcard hero: lock & roll your starting hand
        if CW.pendingHand then
            CW.pendingHand = nil
            if CW.CanShowHand() then hand:Show() end
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
            tinsert(CW.abilRows, { id = f[1], rarity = f[2], cost = f[3], owned = f[4], passive = f[5], lvl = f[6] or 1 })
        end
        RenderList()

    elseif kind == "TB" then
        for _, f in ipairs(ParseEntries(p[2], 2)) do
            tinsert(CW.tabs, { id = f[1], class = f[2] })
        end
    elseif kind == "TBE" then
        -- tabs just arrived: fill the Talents pane with the current tree
        if CW.tabs[CW.tabIndex] then
            Send("TAL " .. CW.tabs[CW.tabIndex].id .. " 0")
        end

    elseif kind == "TL" then
        CW.talPage = tonumber(p[3]) or 0
        CW.talTotal = tonumber(p[4]) or 1
        CW.talRows = {}
        for _, f in ipairs(ParseEntries(p[5], 6)) do
            tinsert(CW.talRows, { talentId = f[1], spell = f[2], rarity = f[3], owned = f[4], max = f[5], row = f[6] })
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
events:SetScript("OnEvent", function(self, event, arg1, arg2, arg3, arg4)
    if event == "CHAT_MSG_ADDON" then
        if arg1 == PREFIX and arg4 == UnitName("player") then
            HandleMessage(arg2)
        end
    elseif event == "PLAYER_ENTERING_WORLD" then
        Send("HELLO")
        if CW.ClaimHotkey then CW.ClaimHotkey() end
        if CW.RefreshMicroTooltip then CW.RefreshMicroTooltip() end
    elseif event == "UPDATE_BINDINGS" then
        -- the player rebound us in Key Bindings: keep the "(N)" suffix honest
        if CW.RefreshMicroTooltip then CW.RefreshMicroTooltip() end
    end
end)

frame:SetScript("OnShow", function()
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
