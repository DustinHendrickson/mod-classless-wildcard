-- ClasslessWildcard: Hero Advancement panel for mod-classless-wildcard
-- WotLK 3.3.5a client. Talks to the server over the "CWCL" addon channel.

local PREFIX = "CWCL"
-- Reveal and starting-hand animation timings. One table, not nine
-- locals: Lua 5.1 gives the main chunk 200 and this file lives near
-- that ceiling -- go over and nothing below the offending line is
-- ever defined.
local ANIM = {}

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
    [12] = "Hero",
}
-- Every class, Death Knight included. Whether its button is SHOWN depends on
-- the server: with IncludeDeathKnight off there are no Death Knight abilities
-- or talents in the library, so the button would open an empty page. The old
-- list left 6 out permanently, which meant a realm that enabled Death Knight
-- content had no way to browse it.
local CLASS_HERO = 12       -- not a class: the Hero line's own browser page
local CLASS_ORDER = { 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, CLASS_HERO }

-- ---------------------------------------------------------------------------
-- state
-- ---------------------------------------------------------------------------
local CW = {
    state = { mode = 255, ae = 0, te = 0, pity = 0, chance = 0, scrolls = 0,
              level = 1, deadline = 2, rebirth = 0, rebirthCost = 0,
              -- Rebirth, the New Game Plus: the rank, whether this character
              -- can be reborn now (at the cap), its gold price, and how many
              -- heirlooms the rank lets them carry through. rebirthCost above
              -- is the configured base price; the server sends it, unused here.
              rebirths = 0, rebirthReady = 0, rebirthPrice = 0, heirloomMax = 1,
              -- the challenge run: which (0 none), lives left and started
              -- with, shards, an extra life held, and whether one can start
              run = 0, lives = 0, livesMax = 0, shards = 0, extraLife = 0, runReady = 0,
              rerolls = 0, scrollCost = 0, scrollBuy = 0,
              -- 0 until the first state packet: the resource bars stay hidden
              -- until the server has told us this character actually has the
              -- extra pools, rather than flashing up on a non-module realm
              universalResources = 0,
              -- runes, mirrored from the server. nil until the first RU
              -- message, which is how the bar stays invisible on realms that
              -- do not run Death Knight abilities at all.
              runes = nil, runic = 0, runicMax = 0 },
    classIndex = 1,
    -- classless talent pricing; the server overrides these via the CFG message
    talentCost = 1, talentFlat = false,
    -- the realm's numbers the Help guide quotes; the server sends them in CFG
    rules = { startAE = 3, aeStart = 4, aePer = 1, teStart = 10, tePer = 1,
              abilityCost = { 1, 2, 3, 5, 8 }, wcStart = 4, wcRollStart = 10,
              rerollsPerLevel = 3, synBase = 10, synInc = 10, banRolls = 25,
              weightCommon = 100, weightLegendary = 25, xpFirst = 100, xpPerRank = 50,
              xpMax = 300, statPct = 3, statMax = 15, maxLevel = 80, defaultMode = 0,
              otherXpPerRank = 25, otherXpMax = 100 },
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
    -- label, and the level scope the server expects: 1 keeps only what this
    -- character's level lets them take, 0 keeps the whole list. Shared by both
    -- browsers, which each remember their own choice.
    SCOPES = { { "My level", 1 }, { "Any level", 0 } },
}
CW.abilSort, CW.abilType, CW.talSort = 1, 1, 1
-- Both browsers open on what the character can take right now.
CW.abilScope, CW.talScope = 1, 1

local function RequestAbil(page)
    CW.abilPage = page
    Send("ABIL " .. CLASS_ORDER[CW.classIndex] .. " " .. page .. " " .. (CW.abilSort - 1)
         .. " " .. CW.BROWSE.ABIL_TYPES[CW.abilType][2]
         .. " " .. CW.BROWSE.SCOPES[CW.abilScope][2])
end

local function RequestTal(page)
    local t = CW.tabs[CW.tabIndex]
    if not t then return end
    CW.talPage = page
    Send("TAL " .. t.id .. " " .. page .. " " .. (CW.talSort - 1)
         .. " " .. CW.BROWSE.SCOPES[CW.talScope][2])
end
CW.RequestAbil, CW.RequestTal = RequestAbil, RequestTal

-- ---------------------------------------------------------------------------
-- main frame: "Hero Advancement" — Ascension-style single-screen layout
-- (class strip on top, Abilities + Talents panes, My Build sidebar, bottom bar)
-- ---------------------------------------------------------------------------
local frame = CreateFrame("Frame", "ClasslessWildcardFrame", UIParent)
frame:SetWidth(950); frame:SetHeight(600)
frame:SetPoint("CENTER")
-- Above the rest of the interface while it is open. UIParent is MEDIUM and a
-- plain child of it inherits that, which tied the panel with the resource bars
-- and with minimap buttons -- and a tie is broken by creation order, so those
-- drew over it. HIGH clears everything the game puts at MEDIUM or below,
-- including MinimapCluster and PlayerFrame at BACKGROUND, and still sits under
-- DIALOG (the flyouts, StaticPopups) and FULLSCREEN_DIALOG (the roll reveal,
-- the starting hand). Toplevel so clicking the panel raises it over anything
-- else that lands at HIGH.
frame:SetFrameStrata("HIGH")
frame:SetToplevel(true)
-- The whole look of the panel (pane outlines, header strips, textured
-- ground) is one baked image. It is a plain texture region, NOT the backdrop's
-- bgFile: a backdrop resolves its files once and never asks for one again, so
-- a new character whose intro cinematic dropped the file (the client purges
-- every texture it loaded before the movie) kept a flat panel for the whole
-- session however many times SetBackdrop was torn down and re-applied -- the
-- border came back each time, the art did not. A texture region is re-read on
-- draw, which is why the die crest and the lock icons on the same screen never
-- went missing. The backdrop now carries only the border.
CW.PANEL_BACKDROP = {
    edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
    tile = false, edgeSize = 32,
    insets = { left = 0, right = 0, top = 0, bottom = 0 },
}
CW.PANEL_ART = "Interface\\AddOns\\ClasslessWildcard\\panel_bg"
frame:SetBackdrop(CW.PANEL_BACKDROP)
-- The art, exactly where the backdrop's bgFile sat (the full frame, insets 0),
-- and the ONLY region the panel has on BACKGROUND. The backdrop's border draws
-- on BORDER, over it.
--
-- One texture on purpose. panel_bg.tga is fully opaque: the dark glaze inside
-- the panes is baked onto the panel's backing colour (10, 11, 15) in the file
-- itself. It used to be a translucent image over a separate opaque backing
-- texture, and 3.3.5 cannot order two regions on one layer: it has no draw
-- sublevels (CreateTexture never reads a fourth argument and SetDrawLayer only
-- the layer, read out of Wow.exe 2026-10-13). Whenever the backing drew last,
-- the panel came up flat. Raising the art to BORDER instead put it level with
-- the backdrop's border, and the border went. With nothing under the art there
-- is nothing to order.
-- On the frame itself, not a local: the main chunk sits at Lua 5.1's limit of
-- 200 active locals.
frame.art = frame:CreateTexture(nil, "BACKGROUND")
frame.art:SetAllPoints(frame)
frame.art:SetTexture(CW.PANEL_ART)

frame:SetMovable(true); frame:EnableMouse(true)
frame:RegisterForDrag("LeftButton")
frame:SetScript("OnDragStart", frame.StartMoving)
frame:SetScript("OnDragStop", frame.StopMovingOrSizing)
frame:Hide()
tinsert(UISpecialFrames, "ClasslessWildcardFrame")
tinsert(UISpecialFrames, "ClasslessWildcardTalentReroll")
tinsert(UISpecialFrames, "ClasslessWildcardHand")

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

-- A reborn Hero's crest glows on its own, brighter with each Rebirth; the
-- hover still lifts it to full. Zero until the first state packet says
-- otherwise, so a fresh character's crest is as plain as it always was.
function CW.GlowBase()
    local n = CW.state.rebirths or 0
    if n <= 0 then return 0 end
    return math.min(0.6, 0.15 + 0.1 * n)
end

function CW.RefreshPanelArt()
    -- Torn down FIRST, then rebuilt. SetTexture with the path a texture
    -- already holds can be a no-op, and a no-op does not reload a dropped
    -- file; nil clears the handle so the second call has to resolve the file
    -- again. SetTexture reports whether the file resolved: when it did not
    -- (the client has not finished purging after a cinematic, or the panel
    -- opened during a loading screen) a retry is queued for the next frames
    -- rather than leaving the panel flat until something else happens to
    -- call this.
    frame.art:SetTexture(nil)
    titleIcon:SetTexture(nil)
    titleGlow:SetTexture(nil)
    local ok = frame.art:SetTexture(CW.PANEL_ART)
    titleIcon:SetTexture("Interface\\AddOns\\ClasslessWildcard\\icon")
    titleGlow:SetTexture("Interface\\AddOns\\ClasslessWildcard\\glow")
    if ok then
        frame.artRetries = nil
        frame:SetScript("OnUpdate", nil)
        return
    end
    frame.artRetries = (frame.artRetries or 0) + 1
    if frame.artRetries > 20 then
        frame.artRetries = nil
        frame:SetScript("OnUpdate", nil)
        return
    end
    frame.artWait = 0.25
    frame:SetScript("OnUpdate", function(self, elapsed)
        self.artWait = self.artWait - elapsed
        if self.artWait <= 0 then
            self:SetScript("OnUpdate", nil)
            CW.RefreshPanelArt()
        end
    end)
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
        GameTooltip:AddLine("Click to open your Starting Hand.", 0.3, 1, 0.3, true)
        GameTooltip:AddLine("Rerolls are free before level " .. (s.freeReroll or 10)
            .. ". Lock the ones you like.", 0.6, 0.9, 0.6, true)
    else
        GameTooltip:SetText("Starting Hand (closed)")
        GameTooltip:AddLine("Free starter rolls end at level " .. (s.freeReroll or 10) .. ".",
            0.8, 0.8, 0.8, true)
        GameTooltip:AddLine("Reroll anything you own one at a time from |cffffd100My Build|r, using the circular arrow beside it.", 0.6, 0.9, 0.6, true)
    end
    GameTooltip:Show()
end)
titleBtn:SetScript("OnLeave", function()
    titleGlow:SetAlpha(CW.GlowBase())
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
title:SetText("Hero Advancement")

local closeBtn = CreateFrame("Button", nil, frame, "UIPanelCloseButton")
closeBtn:SetPoint("TOPRIGHT", -8, -8)

local statusText = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
statusText:SetPoint("TOP", 0, -40)
CW.statusText = statusText   -- read by the flow test

local subStatusText = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
subStatusText:SetPoint("TOP", 0, -56)

-- A life pip: a heart. The client ships no plain heart (every heart in its
-- files is a whole spell or item icon with its own background, a little square
-- at this size), so the addon draws its own: heart_full.tga and
-- heart_empty.tga, painted by client-addon/gen_hearts.py. Used for the run's
-- lives in the header, in the challenge list and on the challenge page, so
-- lives look the same everywhere they appear.
--
-- The empty heart is the pip and the full heart sits over it while the life is
-- in hand. The two are on DIFFERENT draw layers, ARTWORK under OVERLAY: on one
-- layer with a sub-level between them, the client drew some pips with the base
-- over the top piece and they came out empty. Two layers is an order the
-- client always keeps.
function CW.MakePip(parent, size)
    local bg = parent:CreateTexture(nil, "ARTWORK")
    bg:SetWidth(size); bg:SetHeight(size)
    bg:SetTexture("Interface\\AddOns\\ClasslessWildcard\\heart_empty")
    bg.gem = parent:CreateTexture(nil, "OVERLAY")
    bg.gem:SetWidth(size); bg.gem:SetHeight(size)
    bg.gem:SetPoint("CENTER", bg, "CENTER", 0, 0)
    bg.gem:SetTexture("Interface\\AddOns\\ClasslessWildcard\\heart_full")
    bg:Hide(); bg.gem:Hide()
    return bg
end

-- shown or not, and full (a life in hand) or empty (a life lost). The empty
-- heart is drawn dark already, so it is not dimmed further: at 0.3 it all but
-- vanished against the panel.
function CW.SetPip(pip, shown, alive)
    if not shown then pip:Hide(); pip.gem:Hide() return end
    pip:SetAlpha(1)
    pip:Show()
    if alive then pip.gem:Show() else pip.gem:Hide() end
end

-- A run with no limit on lives (Nemesis) carries this number for both its
-- lives and the lives it started with. It shows as one full heart.
CW.UNLIMITED_LIVES = 255
function CW.Unlimited(n) return (n or 0) == CW.UNLIMITED_LIVES end
-- how many hearts to draw for a run that started with `max`
function CW.PipCount(max, cap)
    if CW.Unlimited(max) then return 1 end
    return math.min(cap, max or 0)
end
-- "3 of 5 lives left", or "unlimited lives"
function CW.LivesLeftText(lives, max)
    if CW.Unlimited(max) then return "unlimited lives" end
    return (lives or 0) .. " of " .. (max or 0) .. ((max or 0) == 1 and " life" or " lives") .. " left"
end

-- The run badge, top-right under the close button: the challenge being run,
-- its reward ability's icon, and one heart per life it started with. Hover it
-- for the whole challenge (how it plays, lives, the clock where there is one,
-- what level 80 pays); click it for the challenge page. Hidden with no run.
--
-- Measured, because it has to fit a gap: 164 x 50, right edge at -42, top at
-- -28. To its right the close button starts at -40. To its left is the class
-- strip, centred, 11 buttons of 38 with 8 between (498 wide, so it ends at 724)
-- plus the 1.72x slot frame each wears, which reaches 13.7 past the button:
-- 738. The badge starts at 744. At 196 wide it started at 710 and sat over
-- the last class icons, which was the whole complaint about it. The test
-- measures the same numbers from the frames themselves.
--
-- The panel's own colours: a dark plate in a gold rim, like the confirm
-- popups. The icon is 30 inside a black 32 frame, 9 in from the left, clear of
-- the rim's rounded corner. Name level with the icon's top, hearts with its
-- bottom. No "2 of 3" beside them: six hearts and a count do not fit in 164,
-- the hearts already show it, and the hover card says it in words.
do
    local b = CreateFrame("Button", "ClasslessWildcardRunBadge", frame)
    b:SetWidth(164); b:SetHeight(50)
    b:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -42, -28)
    b:SetBackdrop({
        bgFile = "Interface\\Buttons\\WHITE8X8",
        edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
        tile = false, edgeSize = 12,
        insets = { left = 3, right = 3, top = 3, bottom = 3 },
    })
    b:SetBackdropColor(0.05, 0.045, 0.04, 0.94)
    b:SetBackdropBorderColor(0.80, 0.62, 0.22, 1)
    -- the hover glow stays inside the rim instead of washing over it
    b.hl = b:CreateTexture(nil, "HIGHLIGHT")
    b.hl:SetPoint("TOPLEFT", 4, -4)
    b.hl:SetPoint("BOTTOMRIGHT", -4, 4)
    b.hl:SetTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight")
    b.hl:SetBlendMode("ADD")
    b.iconFrame = b:CreateTexture(nil, "BORDER")
    b.iconFrame:SetWidth(32); b.iconFrame:SetHeight(32)
    b.iconFrame:SetPoint("LEFT", b, "LEFT", 9, 0)
    b.iconFrame:SetTexture(0, 0, 0, 1)
    b.icon = b:CreateTexture(nil, "ARTWORK")
    b.icon:SetWidth(30); b.icon:SetHeight(30)
    b.icon:SetPoint("CENTER", b.iconFrame, "CENTER", 0, 0)
    b.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    b:Hide()
    CW.runBadge = b

    CW.runText = b:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    CW.runText:SetPoint("TOPLEFT", b.iconFrame, "TOPRIGHT", 9, -2)
    CW.runText:SetPoint("RIGHT", b, "RIGHT", -10, 0)
    CW.runText:SetJustifyH("LEFT")

    -- One pip per life the run started with, the lost ones empty. Six is the
    -- most a run can have (five plus a bought extra life).
    CW.lifeIcons = {}
    for i = 1, 6 do
        local t = CW.MakePip(b, 14)
        t:SetPoint("BOTTOMLEFT", b.iconFrame, "BOTTOMRIGHT", 8 + (i - 1) * 15, 1)
        CW.lifeIcons[i] = t
    end

    -- What the reward ability does, read off the game's own tooltip for it
    -- (the reveal's scanner): every line but the name, the description last
    -- and wrapped. 3.3.5 has no call that returns a spell's description.
    function CW.AddAbilityLines(spellId)
        local fx = CW.revealFX
        local lines = fx and fx.ScanSpell and fx.ScanSpell(spellId) or {}
        for _, l in ipairs(lines) do
            if l.left and l.right then
                GameTooltip:AddDoubleLine(l.left, l.right, 0.75, 0.75, 0.75, 0.75, 0.75, 0.75)
            elseif l.left then
                GameTooltip:AddLine(l.left, l.r or 1, l.g or 0.82, l.b or 0, true)
            end
        end
    end

    local function Minutes(sec)
        sec = math.max(0, math.floor(sec))
        if sec < 60 then return "under a minute" end
        local m = math.floor(sec / 60)
        return m .. (m == 1 and " minute" or " minutes")
    end

    -- the hover card: everything the challenge page says about the live run,
    -- without opening it
    function CW.RunTooltip(self)
        local s = CW.state
        local c = CW.challengesById and CW.challengesById[s.run or 0]
        GameTooltip:SetOwner(self, "ANCHOR_NONE")
        GameTooltip:ClearAllPoints()
        GameTooltip:SetPoint("TOPRIGHT", self, "BOTTOMRIGHT", 0, -4)
        GameTooltip:SetText(c and c.name or "Challenge run", 1, 0.27, 0.27)
        GameTooltip:AddLine("Your challenge run", 0.6, 0.6, 0.6)
        if not c then
            GameTooltip:AddLine("Loading the challenge...", 0.8, 0.8, 0.8)
            GameTooltip:Show()
            return
        end
        GameTooltip:AddLine(" ")
        -- the rule alone: the full text is on the challenge page, and a
        -- tooltip line with line breaks in it stops wrapping
        GameTooltip:AddLine(c.rule, 1, 1, 1, true)
        GameTooltip:AddLine(" ")
        local unlimited = CW.Unlimited(s.livesMax)
        GameTooltip:AddDoubleLine("Lives", unlimited and "Unlimited" or ((s.lives or 0) .. " of " .. (s.livesMax or 0) .. " left"),
            1, 0.82, 0, 1, 1, 1)
        if (s.hourglassLeft or 0) > 0 then
            local left = s.hourglassLeft - (GetTime() - (CW.hourglassAt or GetTime()))
            local low = left < 300 and 0.4 or 1   -- red in the last five minutes, as the warning says
            GameTooltip:AddDoubleLine("This level's clock", Minutes(left) .. " left", 1, 0.82, 0, 1, low, low)
        end
        if unlimited then
            GameTooltip:AddLine("A death never ends this run.", 0.7, 0.7, 0.7, true)
        else
            GameTooltip:AddLine("A death costs one life. Battlegrounds, arenas and duels cost nothing. "
                .. "Run out and the rule lifts; you keep your level, gear and build.", 0.7, 0.7, 0.7, true)
        end
        GameTooltip:AddLine(" ")
        local goal = (c.vengeance or 0) > 0 and ("Reach level 80 with " .. c.vengeance .. " Vengeance for")
            or (unlimited and "Reach level 80 for" or "Reach level 80 with a life left for")
        GameTooltip:AddLine(goal, 1, 0.82, 0)
        GameTooltip:AddDoubleLine("Gold", "|cffffffff" .. (c.gold or 0)
            .. "|r|TInterface\\MoneyFrame\\UI-GoldIcon:14:14:2:0|t", 0.8, 0.8, 0.8, 1, 1, 1)
        local title = (c.title or ""):gsub("%%s", UnitName("player") or "you")
        if title ~= "" then
            GameTooltip:AddDoubleLine("Title", title, 0.8, 0.8, 0.8, 0.9, 0.8, 0.5)
        end
        if (c.reward or 0) > 0 then
            GameTooltip:AddDoubleLine("Ability", (GetSpellInfo(c.reward)) or "Reward ability",
                0.8, 0.8, 0.8, 0.64, 0.21, 0.93)
            CW.AddAbilityLines(c.reward)
            GameTooltip:AddLine("Yours for good as an heirloom: usable from level 1 and kept through every Rebirth.",
                0.6, 0.6, 0.6, true)
        end
        if c.finished == 1 then
            GameTooltip:AddLine("You finished this challenge before: this time it pays shards, and the Unbroken title if you have not earned it.", 0.6, 0.6, 0.6, true)
        end
        GameTooltip:AddLine(" ")
        GameTooltip:AddLine("Click for the challenge page: tips, the ability's tooltip and your record.", 0.3, 1, 0.3, true)
        GameTooltip:Show()
    end

    b:SetScript("OnEnter", function(self)
        CW.RunTooltip(self)
        -- the clock moves while the card is up; a fresh state redraws it
        if (CW.state.hourglassLeft or 0) > 0 then Send("STATE") end
    end)
    b:SetScript("OnLeave", function() GameTooltip:Hide() end)
    b:SetScript("OnClick", function()
        GameTooltip:Hide()
        if CW.runFly and CW.OpenRuns then
            CW.runFly.selected = CW.state.run
            CW.OpenRuns()
        end
    end)
end

function CW.UpdateLives()
    local s = CW.state
    local b, icons = CW.runBadge, CW.lifeIcons
    if (s.run or 0) == 0 or (s.livesMax or 0) == 0 then
        for i = 1, #icons do CW.SetPip(icons[i], false) end
        b:Hide()
        if GameTooltip:IsOwned(b) then GameTooltip:Hide() end
        return
    end
    local c = CW.challengesById and CW.challengesById[s.run]
    CW.runText:SetText("|cffff5544" .. (c and c.name or ("Challenge " .. s.run)) .. "|r")
    b.icon:SetTexture(c and (c.reward or 0) > 0 and SpellIcon(c.reward) or "Interface\\Icons\\INV_Misc_Bone_HumanSkull_01")
    local n = CW.PipCount(s.livesMax, #icons)
    for i = 1, #icons do
        CW.SetPip(icons[i], i <= n, i <= (s.lives or 0))
    end
    b:Show()
    if GameTooltip:IsOwned(b) then CW.RunTooltip(b) end
end

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
    if tc then
        b.icon:SetTexCoord(tc[1], tc[2], tc[3], tc[4])
    else
        -- the Hero page: the same icon its spellbook tab wears
        b.icon:SetTexture("Interface\\Icons\\Ability_Hunter_FocusedAim")
    end
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
        -- tree, so both panes are showing the same class. The Hero page has one
        -- of its own now -- the server reports the Hero talent tab as class 12
        -- -- so it takes the same path as every other button.
        if CW.SyncTalentTabToClass and CW.SyncTalentTabToClass() then
            RequestTal(0)
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
CW.classButtons = classButtons

-- Point the Talents pane at the selected class's first tree.
--
-- classIndex and tabIndex default to 1 independently, and tab 1 is whichever
-- tree has the lowest TalentTab id -- a Mage tree -- so the panel opened
-- showing Warrior abilities beside Mage talents. Clicking a class button
-- always reconciled them; nothing did at load, because the tab list arrives
-- over the addon channel after the first render.
--
-- Only moves the pane when the tree on screen belongs to a DIFFERENT class, so
-- paging to Warrior tree 2 and reopening the panel keeps tree 2.
-- Returns whether the pane is showing the selected class once this is done,
-- so a caller can tell "nothing to refresh" from "that class has no trees".
function CW.SyncTalentTabToClass()
    local want = CLASS_ORDER[CW.classIndex]
    if not want or not CW.tabs or #CW.tabs == 0 then return false end
    local current = CW.tabs[CW.tabIndex]
    if current and current.class == want then return true end
    for idx, t in ipairs(CW.tabs) do
        if t.class == want then
            CW.tabIndex = idx
            return true
        end
    end
    return false          -- that class has no trees (Death Knight switched off)
end

-- Position the strip over the buttons that are actually visible, so hiding the
-- Death Knight one leaves the rest centred instead of gapped.
function CW.LayoutClassStrip()
    local visible = {}
    for _, b in ipairs(classButtons) do
        if (b.classId == 6 and not CW.dkEnabled)
            or (b.classId == CLASS_HERO and not CW.forgedEnabled) then
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

    -- drawn above the slot frame. Both want OVERLAY and 3.3.5 has no
    -- sublevels to order them, so the tick lives on a child frame, which
    -- draws over every layer of its parent.
    e.checkLayer = CreateFrame("Frame", nil, e)
    e.checkLayer:SetAllPoints(e)
    e.check = e.checkLayer:CreateTexture(nil, "OVERLAY")
    e.check:SetWidth(18); e.check:SetHeight(18)
    e.check:SetPoint("BOTTOMRIGHT", e.icon, "BOTTOMRIGHT", 4, -3)
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
            GameTooltip:Hide()   -- the same link on a shown tooltip toggles it off
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
MakePaneHeader(ABIL_X + 84, 80, "Abilities")

local abilEntries = {}
for i = 1, ENTRIES do
    abilEntries[i] = MakeEntry(ABIL_X, PANE_TOP - 36 - (i - 1) * ENTRY_H, ABIL_W, i)
end
local abilPrev, abilPage, abilNext = MakePager(ABIL_X, ABIL_W, 66)

-- Talents pane -------------------------------------------------------------------
local TAL_X, TAL_W = 336, 296
MakePaneHeader(TAL_X + 84, 80, "Talents")

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
    -- Slots on the strip: sort on the left, then the pane title, then the
    -- filters. Widths are the widest label each control has to hold plus the
    -- button art's padding, measured in the game's own font.
    local abilSortBtn = MakeHeaderButton(ABIL_X + 4, 80, B.ABIL_SORTS[1])
    local abilTypeBtn = MakeHeaderButton(ABIL_X + 164, 58, B.ABIL_TYPES[1][1])
    local abilScopeBtn = MakeHeaderButton(ABIL_X + 226, 66, B.SCOPES[1][1])
    local talSortBtn = MakeHeaderButton(TAL_X + 4, 80, B.TAL_SORTS[1])
    local talScopeBtn = MakeHeaderButton(TAL_X + 226, 66, B.SCOPES[1][1])

    -- Stands in for the list when a filter leaves nothing, so an empty pane
    -- reads as a filter result rather than a panel that failed to load.
    local function MakeEmptyNote(x, width)
        local t = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
        t:SetPoint("TOPLEFT", x + 16, PANE_TOP - 36 - 2 * ENTRY_H)
        t:SetWidth(width - 32)
        t:SetJustifyH("CENTER")
        t:Hide()
        return t
    end
    CW.abilEmpty = MakeEmptyNote(ABIL_X, ABIL_W)
    CW.talEmpty = MakeEmptyNote(TAL_X, TAL_W)
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
    abilScopeBtn:SetScript("OnClick", function()
        CW.abilScope = CW.abilScope % #B.SCOPES + 1
        abilScopeBtn:SetText(B.SCOPES[CW.abilScope][1])
        SaveBrowseChoice("abilScope", CW.abilScope)
        RequestAbil(0)
    end)
    talScopeBtn:SetScript("OnClick", function()
        CW.talScope = CW.talScope % #B.SCOPES + 1
        talScopeBtn:SetText(B.SCOPES[CW.talScope][1])
        SaveBrowseChoice("talScope", CW.talScope)
        RequestTal(0)
    end)
    CW.abilSortBtn, CW.abilTypeBtn, CW.talSortBtn = abilSortBtn, abilTypeBtn, talSortBtn
    CW.abilScopeBtn, CW.talScopeBtn = abilScopeBtn, talScopeBtn

    -- saved choices arrive with the saved variables, after this file has run
    function CW.LoadBrowseChoices()
        ClasslessWildcardDB = ClasslessWildcardDB or {}
        CW.abilSort = B.ABIL_SORTS[ClasslessWildcardDB.abilSort or 0] and ClasslessWildcardDB.abilSort or 1
        CW.abilType = B.ABIL_TYPES[ClasslessWildcardDB.abilType or 0] and ClasslessWildcardDB.abilType or 1
        CW.talSort = B.TAL_SORTS[ClasslessWildcardDB.talSort or 0] and ClasslessWildcardDB.talSort or 1
        CW.abilScope = B.SCOPES[ClasslessWildcardDB.abilScope or 0] and ClasslessWildcardDB.abilScope or 1
        CW.talScope = B.SCOPES[ClasslessWildcardDB.talScope or 0] and ClasslessWildcardDB.talScope or 1
        abilSortBtn:SetText(B.ABIL_SORTS[CW.abilSort])
        abilTypeBtn:SetText(B.ABIL_TYPES[CW.abilType][1])
        talSortBtn:SetText(B.TAL_SORTS[CW.talSort])
        abilScopeBtn:SetText(B.SCOPES[CW.abilScope][1])
        talScopeBtn:SetText(B.SCOPES[CW.talScope][1])
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
            GameTooltip:Hide()   -- the same link on a shown tooltip toggles it off
            GameTooltip:SetOwner(self, "ANCHOR_LEFT")
            GameTooltip:SetHyperlink("spell:" .. self.spellId)
            if self.note then
                GameTooltip:AddLine(" ")
                GameTooltip:AddLine(self.note, 0.6, 0.6, 0.6, true)
            end
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
CW.statsBtn = statsBtn

local respecBtn = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
respecBtn:SetWidth(90); respecBtn:SetHeight(22)
respecBtn:SetPoint("BOTTOMRIGHT", -20, 26)
respecBtn:SetText("Respec")
respecBtn:SetScript("OnClick", function() StaticPopup_Show("CW_CLASSLESS_RESPEC") end)
respecBtn:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    GameTooltip:SetText("Respec")
    GameTooltip:AddLine("Unlearn every ability and talent. All essence is refunded, and it is free.", 1, 1, 1, true)
    GameTooltip:Show()
end)
respecBtn:SetScript("OnLeave", function() GameTooltip:Hide() end)
StaticPopupDialogs["CW_CLASSLESS_RESPEC"] = {
    text = "Unlearn every ability and talent? All essence is refunded. Heirloom abilities stay.",
    button1 = "Respec",
    button2 = "Cancel",
    OnAccept = function() Send("RESPEC") end,
    timeout = 0, whileDead = 1, hideOnEscape = 1, preferredIndex = 3,
}
-- 4.2: an archetype replaces the build, so it asks first
StaticPopupDialogs["CW_CLASSLESS_ARCHETYPE"] = {
    text = "Follow %s? Your abilities and talents are unlearned and refunded, then its build is bought for you as you level.",
    button1 = "Follow",
    button2 = "Cancel",
    OnAccept = function(self)
        if self.data then Send("ARCHAPPLY " .. self.data) end
        if CW.SetTab then CW.SetTab("HERO") end   -- show what the archetype bought
    end,
    timeout = 0, whileDead = 1, hideOnEscape = 1, preferredIndex = 3,
}
StaticPopupDialogs["CW_CLASSLESS_BUYLIFE"] = {
    text = "Spend %d shards on an extra life for your next run?",
    button1 = "Buy",
    button2 = "Cancel",
    OnAccept = function() Send("BUYLIFE") end,
    timeout = 0, whileDead = 1, hideOnEscape = 1, preferredIndex = 3,
}

-- Rebirth: the new life at level 1. Confirmed last, once the heirlooms and
-- the path are chosen in the picker below, which fills in what gets sent.
StaticPopupDialogs["CW_CLASSLESS_REBIRTH"] = {
    text = "%s",
    button1 = "Be reborn",
    button2 = "Cancel",
    OnAccept = function() if CW.rebirthFly and CW.rebirthFly.Confirm then CW.rebirthFly.Confirm() end end,
    timeout = 0, whileDead = 1, hideOnEscape = 1, preferredIndex = 3,
}
-- Asked before the last word: whether the new life forgets the quests done.
-- Either answer goes on to the confirm above, which is where Cancel lives, so
-- Escape is off here: it would count as Keep quests without being chosen.
StaticPopupDialogs["CW_CLASSLESS_REBIRTH_QUESTS"] = {
    text = "Wipe all quest progress?\n\nWipe: every quest can be done again for its XP and rewards. "
        .. "Keep: quests you have done stay done.",
    button1 = "Wipe quests",
    button2 = "Keep quests",
    OnAccept = function() if CW.rebirthFly and CW.rebirthFly.ChooseQuests then CW.rebirthFly.ChooseQuests(false) end end,
    OnCancel = function() if CW.rebirthFly and CW.rebirthFly.ChooseQuests then CW.rebirthFly.ChooseQuests(true) end end,
    timeout = 0, whileDead = 1, hideOnEscape = 0, preferredIndex = 3,
}
local rebirthBtn =CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
rebirthBtn:SetWidth(90); rebirthBtn:SetHeight(22)
rebirthBtn:SetPoint("BOTTOMRIGHT", -116, 26)
rebirthBtn:SetText("Rebirth")
rebirthBtn:Hide()
rebirthBtn:SetScript("OnClick", function()
    local s = CW.state
    if s.mode == 255 then
        frame:Hide()
        CW.ShowPathChoice()
    elseif s.rebirthReady == 1 then
        CW.OpenRebirth()
    elseif s.runReady == 1 then
        CW.OpenRuns()      -- a fresh Hero: a run with nothing to carry
    end
end)
rebirthBtn:SetScript("OnEnter", function(self)
    local s = CW.state
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    if s.rebirthReady == 1 then
        GameTooltip:SetText("|cffff8800Rebirth|r")
        GameTooltip:AddLine("Start a new life at level 1 with a permanent rank that stacks: more kill XP, a bonus to every stat, and an heirloom ability carried through.", 0.8, 0.8, 0.8, true)
    elseif s.runReady == 1 then
        GameTooltip:SetText("|cffff4444Challenge run|r")
        GameTooltip:AddLine("Level from here under one rule, with the lives it gives.", 0.8, 0.8, 0.8, true)
        GameTooltip:AddLine("Finish at level " .. CW.rules.maxLevel .. " for gold, a title, and an ability no roll or shop can give.", 0.8, 0.8, 0.8, true)
        GameTooltip:AddLine("Open to see every challenge, its rule and its rewards.", 0.6, 0.6, 0.6, true)
    elseif s.mode == 255 then
        GameTooltip:SetText("Choose path")
        GameTooltip:AddLine("Classless or Wildcard. This character keeps the path it chooses.", 0.8, 0.8, 0.8, true)
    end
    GameTooltip:Show()
end)
rebirthBtn:SetScript("OnLeave", function() GameTooltip:Hide() end)
CW.rebirthBtn = rebirthBtn

-- The Rebirth picker and the challenge screen are full screens over the panel
-- that open confirm popups of their own. Blizzard's StaticPopups draw on the
-- DIALOG strata, and so did these: on a tie the screen won and covered its own
-- popup, buttons and all. So they sit on the panel's strata, HIGH, which every
-- popup draws over, and are lifted well clear of the panel's own frames every
-- time they open, since a click can raise the toplevel panel's level.
function CW.OverPanel(screen)
    screen:SetFrameStrata("HIGH")
    screen:SetFrameLevel(frame:GetFrameLevel() + 40)
end

-- Rebirth picker ------------------------------------------------------------
-- Which abilities come along into the new life, on the character's own path. Rows
-- are the owned abilities a Rebirth may carry: what was picked or rolled,
-- and heirlooms already carried once. What came with a talent or free with
-- another ability cannot be carried on its own, and the server refuses it.
-- Everything lives on CW.rebirthFly; the main chunk is at Lua's local limit.
do
    -- 460 x 500, centred on the panel, in the panel's own flyout dress, laid
    -- out like the summary card that follows it. Top to bottom: icon and
    -- title -18; the next rank as three rows under a header -70 (to -146);
    -- what is kept and what is reset -158 (four lines at most, to -212); the
    -- Heirlooms header and its count -222, the hint -244, six rows of 24 from
    -- -272 (to -416), the page arrows at -420; the cost and the two buttons
    -- along the bottom.
    local W, PAD = 460, 18
    local fly = CreateFrame("Frame", "ClasslessWildcardRebirth", frame)
    fly:SetWidth(W); fly:SetHeight(500)
    fly:SetPoint("CENTER", frame, "CENTER", 0, 0)
    CW.OverPanel(fly)   -- under the confirm popups, over the panel
    fly:SetBackdrop({
        bgFile = "Interface\\Buttons\\WHITE8X8",
        edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
        tile = false, edgeSize = 14,
        insets = { left = 4, right = 4, top = 4, bottom = 4 },
    })
    fly:SetBackdropColor(0.03, 0.03, 0.05, 0.97) -- solid: the panes underneath must not show through
    fly:EnableMouse(true)
    fly:Hide()
    CW.rebirthFly = fly
    fly.picked = {}
    fly.page = 0
    local ROWS, ROW_H = 6, 24

    local function SectionHeader(text, y)
        local h = fly:CreateFontString(nil, "OVERLAY", "GameFontNormal")
        h:SetPoint("TOPLEFT", PAD, y)
        h:SetJustifyH("LEFT")
        h:SetText(text)
        local rule = fly:CreateTexture(nil, "ARTWORK")
        rule:SetHeight(1)
        rule:SetTexture(1, 0.82, 0, 0.25)
        rule:SetPoint("TOPLEFT", PAD, y - 16)
        rule:SetPoint("TOPRIGHT", -PAD, y - 16)
        return h
    end

    fly.icon = fly:CreateTexture(nil, "ARTWORK")
    fly.icon:SetWidth(36); fly.icon:SetHeight(36)
    fly.icon:SetPoint("TOPLEFT", PAD + 2, -PAD)
    fly.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    fly.icon:SetTexture("Interface\\Icons\\Spell_Nature_Reincarnation")
    fly.iconBorder = fly:CreateTexture(nil, "OVERLAY")
    fly.iconBorder:SetWidth(58); fly.iconBorder:SetHeight(58)
    fly.iconBorder:SetPoint("CENTER", fly.icon, "CENTER", 0, 0)
    fly.iconBorder:SetTexture("Interface\\Buttons\\UI-Quickslot2")
    fly.title = fly:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    fly.title:SetPoint("TOPLEFT", fly.icon, "TOPRIGHT", 12, -1)
    fly.title:SetJustifyH("LEFT")
    fly.title:SetTextColor(1, 0.53, 0)
    fly.title:SetText("Rebirth")
    fly.subtitle = fly:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    fly.subtitle:SetPoint("TOPLEFT", fly.title, "BOTTOMLEFT", 0, -5)
    fly.subtitle:SetJustifyH("LEFT")

    -- the rank this Rebirth brings, from the realm's own numbers
    SectionHeader("Your rank after this Rebirth", -70)
    fly.rankRows = {}
    for i = 1, 3 do
        local y = -92 - (i - 1) * 18
        local label = fly:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        label:SetPoint("TOPLEFT", PAD + 4, y)
        label:SetJustifyH("LEFT")
        label:SetTextColor(0.85, 0.85, 0.85)
        local value = fly:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        value:SetPoint("TOPRIGHT", -PAD, y)
        value:SetJustifyH("RIGHT")
        value:SetTextColor(0.1, 1, 0.1)
        fly.rankRows[i] = { label = label, value = value }
    end
    fly.rankRows[1].label:SetText("Kills and dungeons")
    fly.rankRows[2].label:SetText("Quests, exploration, PvP")
    fly.rankRows[3].label:SetText("Every primary stat")

    fly.intro = fly:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    fly.intro:SetPoint("TOPLEFT", PAD, -158)
    fly.intro:SetWidth(W - 2 * PAD)
    fly.intro:SetJustifyH("LEFT")
    fly.intro:SetTextColor(0.75, 0.75, 0.75)
    fly.intro:SetText("|cffffd100Kept:|r gold, bags, bank, reputation, riding and flight paths.\n"
        .. "|cffffd100Reset:|r your level, build and stat points. Worn gear goes into your bags, or by mail if they are full.\n"
        .. "|cffffd100Quests:|r you choose next whether they are wiped or kept.")

    SectionHeader("Heirlooms", -222)
    fly.count = fly:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    fly.count:SetPoint("TOPRIGHT", -PAD, -222)
    fly.count:SetJustifyH("RIGHT")
    fly.hint = fly:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    fly.hint:SetPoint("TOPLEFT", PAD, -244)
    fly.hint:SetWidth(W - 2 * PAD)
    fly.hint:SetJustifyH("LEFT")
    fly.hint:SetTextColor(0.75, 0.75, 0.75)
    fly.hint:SetText("Click the abilities to carry. An heirloom is usable from level 1 and never rerolled.")

    fly.rows = {}
    for i = 1, ROWS do
        local r = CreateFrame("Button", nil, fly)
        r:SetWidth(W - 2 * PAD); r:SetHeight(ROW_H)
        r:SetPoint("TOPLEFT", PAD, -272 - (i - 1) * ROW_H)
        r.stripe = r:CreateTexture(nil, "BACKGROUND")
        r.stripe:SetAllPoints(r)
        r.stripe:SetTexture("Interface\\Buttons\\WHITE8X8")
        r.stripe:SetVertexColor(1, 1, 1, i % 2 == 0 and 0.04 or 0.08)
        r.icon = r:CreateTexture(nil, "ARTWORK")
        r.icon:SetWidth(20); r.icon:SetHeight(20)
        r.icon:SetPoint("LEFT", 4, 0)
        r.icon:SetTexCoord(0.06, 0.94, 0.06, 0.94)
        r.name = r:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        r.name:SetPoint("LEFT", r.icon, "RIGHT", 8, 0)
        r.name:SetPoint("RIGHT", -30, 0)
        r.name:SetJustifyH("LEFT")
        r.check = r:CreateTexture(nil, "OVERLAY")
        r.check:SetWidth(18); r.check:SetHeight(18)
        r.check:SetPoint("RIGHT", -6, 0)
        r.check:SetTexture("Interface\\RaidFrame\\ReadyCheck-Ready")
        r:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight", "ADD")
        r:SetScript("OnClick", function(self)
            if self.id then
                if PlaySound then pcall(PlaySound, "igMainMenuOptionCheckBoxOn") end
                CW.ToggleHeirloom(self.id)
            end
        end)
        r:SetScript("OnEnter", function(self)
            if not self.spellId then return end
            GameTooltip:Hide()   -- the same link on a shown tooltip toggles it off
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:SetHyperlink("spell:" .. self.spellId)
            GameTooltip:Show()
        end)
        r:SetScript("OnLeave", function() GameTooltip:Hide() end)
        fly.rows[i] = r
    end
    fly.empty = fly:CreateFontString(nil, "OVERLAY", "GameFontDisable")
    fly.empty:SetPoint("TOPLEFT", PAD + 4, -278)
    fly.empty:SetText("You own nothing that can be carried.")

    -- the panel's own page arrows, not text buttons
    fly.prev = CreateFrame("Button", nil, fly)
    StyleArrow(fly.prev, true)
    fly.prev:SetPoint("TOPLEFT", PAD, -420)
    fly.next = CreateFrame("Button", nil, fly)
    StyleArrow(fly.next, false)
    fly.next:SetPoint("TOPRIGHT", -PAD, -420)
    fly.pageText = fly:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    fly.pageText:SetPoint("TOP", 0, -427)
    fly.prev:SetScript("OnClick", function() fly.page = math.max(0, fly.page - 1); CW.RenderRebirth() end)
    fly.next:SetScript("OnClick", function() fly.page = fly.page + 1; CW.RenderRebirth() end)

    fly.reborn = CreateFrame("Button", nil, fly, "UIPanelButtonTemplate")
    fly.reborn:SetWidth(140); fly.reborn:SetHeight(22)
    fly.reborn:SetPoint("BOTTOMLEFT", PAD, 16)
    fly.reborn:SetText("Be reborn")
    fly.reborn:SetScript("OnClick", function() CW.AskRebirth() end)
    fly.cancel = CreateFrame("Button", nil, fly, "UIPanelButtonTemplate")
    fly.cancel:SetWidth(100); fly.cancel:SetHeight(22)
    fly.cancel:SetPoint("BOTTOMRIGHT", -PAD, 16)
    fly.cancel:SetText("Cancel")
    fly.cancel:SetScript("OnClick", function() fly:Hide() end)
    fly.cost = fly:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    fly.cost:SetPoint("BOTTOM", fly, "BOTTOM", 0, 22)

    function CW.RebirthCandidates()
        local out = {}
        for _, e in ipairs(CW.owned or {}) do
            if e.source == 0 or e.source == 1 or e.source == 4 then tinsert(out, e) end
        end
        return out
    end

    local function PickedCount()
        local n = 0
        for _ in pairs(fly.picked) do n = n + 1 end
        return n
    end

    function CW.RenderRebirth()
        local s = CW.state
        local list = CW.RebirthCandidates()
        local max = s.heirloomMax or 1
        local rank = (s.rebirths or 0) + 1
        local r = CW.rules
        fly.title:SetText("Rebirth " .. rank)
        fly.subtitle:SetText("Begin a new life at level 1, on your "
            .. (s.mode == 0 and "|cff00ccffClassless|r" or "|cffff8800Wildcard|r") .. " path.")
        -- the same formulas as RebirthXpPct and ApplyRebirthMods
        fly.rankRows[1].value:SetText("+" .. math.min(r.xpFirst + r.xpPerRank * (rank - 1), r.xpMax) .. "% XP")
        fly.rankRows[2].value:SetText("+" .. math.min(r.otherXpPerRank * rank, r.otherXpMax) .. "% XP")
        fly.rankRows[3].value:SetText("+" .. math.min(r.statPct * rank, r.statMax) .. "%")
        fly.count:SetText("|cff00ff00" .. PickedCount() .. "|r of " .. max)
        fly.cost:SetText("Cost  |cffffffff" .. (s.rebirthPrice or 0) .. "|r |TInterface\\MoneyFrame\\UI-GoldIcon:14:14:2:0|t")
        if #list == 0 then fly.empty:Show() else fly.empty:Hide() end
        local total = math.max(1, math.ceil(#list / ROWS))
        if fly.page >= total then fly.page = total - 1 end
        fly.pageText:SetText((fly.page + 1) .. " / " .. total)
        if total > 1 then fly.prev:Show(); fly.next:Show(); fly.pageText:Show()
        else fly.prev:Hide(); fly.next:Hide(); fly.pageText:Hide() end
        for i = 1, ROWS do
            local it = list[fly.page * ROWS + i]
            local r = fly.rows[i]
            if it then
                r.id, r.spellId = it.id, it.id
                r.icon:SetTexture(SpellIcon(it.id))
                r.name:SetText(SpellLabel(it.id, it.rarity) .. (it.source == 4 and "  |cffff8800heirloom|r" or ""))
                if fly.picked[it.id] then
                    r.check:Show()
                    r.stripe:SetVertexColor(1, 0.82, 0.3, 0.16)
                else
                    r.check:Hide()
                    r.stripe:SetVertexColor(1, 1, 1, i % 2 == 0 and 0.04 or 0.08)
                end
                r:Show()
            else
                r.id, r.spellId = nil, nil
                r:Hide()
            end
        end
    end

    function CW.ToggleHeirloom(id)
        if fly.picked[id] then
            fly.picked[id] = nil
        else
            local max = CW.state.heirloomMax or 1
            if PickedCount() >= max then
                Print("|cffff4444You may carry " .. max .. " heirloom" .. (max == 1 and "" or "s") .. " this time.|r")
                return
            end
            fly.picked[id] = true
        end
        CW.RenderRebirth()
    end

    function CW.OpenRebirth()
        CW.OverPanel(fly)
        fly.picked = {}
        fly.page = 0
        if CW.runFly then CW.runFly:Hide() end
        CW.statFly:Hide(); CW.helpFly:Hide(); CW.archFly:Hide()
        if CW.setFly then CW.setFly:Hide() end
        Send("OWN")   -- the list is redrawn when the fresh answer lands
        CW.RenderRebirth()
        fly:Show()
    end

    -- Be reborn asks about the quests first; the answer leads to the last word.
    function CW.AskRebirth()
        fly.keepQuests = nil
        StaticPopup_Show("CW_CLASSLESS_REBIRTH_QUESTS")
    end

    -- The last word before it is sent: which heirlooms, the quests, and what
    -- it costs. The popup's OK calls fly.Confirm, which sends exactly this.
    function fly.ChooseQuests(keep)
        local s = CW.state
        fly.keepQuests = keep and true or false
        local ids = {}
        for id in pairs(fly.picked) do tinsert(ids, id) end
        table.sort(ids)
        fly.pendingIds = ids
        local names = {}
        for _, id in ipairs(ids) do tinsert(names, (GetSpellInfo(id)) or ("#" .. id)) end
        local path = s.mode == 0 and "|cff00ccffClassless|r" or "|cffff8800Wildcard|r"
        StaticPopup_Show("CW_CLASSLESS_REBIRTH",
            "Rebirth " .. ((s.rebirths or 0) + 1) .. " on your " .. path .. " path for |cffffd100"
            .. (s.rebirthPrice or 0) .. " gold|r.\n\nBack to level 1. Heirlooms: "
            .. (#names > 0 and table.concat(names, ", ") or "none") .. ".\n"
            .. (fly.keepQuests and "Quests: kept." or "Quests: wiped."))
    end

    function fly.Confirm()
        local parts = { "REBIRTH" }
        if fly.keepQuests then tinsert(parts, "KEEPQ") end
        for _, id in ipairs(fly.pendingIds or {}) do tinsert(parts, tostring(id)) end
        Send(table.concat(parts, " "))
    end
end

-- Challenge runs ------------------------------------------------------------
-- The list the server sends (CH ... CHE): id, name, lives, reward, rule, the
-- best this character did on it. Pick one, read its rule, start it. Shards
-- and the extra life live here too. Everything hangs on CW.runFly.
CW.challenges = {}

-- What a Loaded Die throw says in the middle of the screen: the face, gold on
-- the top one, and the 1 it threw away when it was thrown again.
function CW.LoadedDieText(roll, sides, rerolled)
    local text
    if roll >= sides then
        text = "Loaded Die: " .. roll .. "! The die returns to your hand."
    else
        text = "Loaded Die: " .. roll
    end
    if rerolled then text = "Rolled a 1, thrown again. " .. text end
    if roll >= sides then return text, 1.0, 0.82, 0.0 end
    local t = (roll - 1) / math.max(1, sides - 1)          -- low red, high green
    return text, 1.0 - 0.6 * t, 0.4 + 0.6 * t, 0.4
end

-- A challenge built on one path's mechanics is for that path only (the
-- server's Challenge::path); 255 is either. A run never changes a path.
function CW.RunPathFits(c)
    local want = c and c.path or 255
    return want == 255 or (CW.state.mode or 255) == want
end

function CW.RunPathText(c)
    local want = c and c.path == 1 and "Wildcard" or "Classless"
    local mode = CW.state.mode or 255
    if mode == 255 then
        return want .. " Heroes only. Choose the " .. want .. " path to start it."
    end
    return want .. " Heroes only. Your path is " .. (mode == 1 and "Wildcard" or "Classless") .. "."
end
-- A run starts before the path deadline on the character's own path, so
-- the last word only confirms.
StaticPopupDialogs["CW_RUN_CONFIRM"] = {
    text = "%s",
    button1 = "Begin the run",
    button2 = "Cancel",
    OnAccept = function() if CW.runFly and CW.runFly.Confirm then CW.runFly.Confirm() end end,
    timeout = 0, whileDead = 1, hideOnEscape = 1, preferredIndex = 3,
}
StaticPopupDialogs["CW_RUN_DEATH"] = {
    text = "%s", button1 = "Onward",
    timeout = 0, whileDead = 1, hideOnEscape = 1, preferredIndex = 3,
}
-- ---------------------------------------------------------------------------
-- The summary card: what a Rebirth or the end of a run gave, laid out the
-- way the panel lays things out. An icon and a large title, then sections of
-- label and value rows in two aligned columns, then notes, then one button.
-- A StaticPopup centres every line in a narrow box and wraps mid-phrase, so
-- this is a frame of its own. Escape closes it.
--
-- spec = { icon, title, titleColor = {r,g,b}, subtitle,
--          sections = { { header, rows = { { label, value, {r,g,b}, icon } } } },
--          notes = { "..." }, button }
-- ---------------------------------------------------------------------------
do
    local W, PAD, ROW_H, ICON = 380, 20, 20, 40
    local LABEL_W = 160
    local GREEN, ORANGE, GOLD, PURPLE, GREY = { 0.1, 1, 0.1 }, { 1, 0.53, 0 }, { 1, 0.82, 0 },
        { 0.64, 0.21, 0.93 }, { 0.6, 0.6, 0.6 }
    CW.SUMMARY_COLORS = { green = GREEN, orange = ORANGE, gold = GOLD, purple = PURPLE, grey = GREY }

    local card = CreateFrame("Frame", "ClasslessWildcardSummary", UIParent)
    card:SetWidth(W); card:SetHeight(200)
    card:SetPoint("CENTER", UIParent, "CENTER", 0, 80)
    card:SetFrameStrata("DIALOG")
    card:SetToplevel(true)
    card:SetBackdrop({
        bgFile = "Interface\\Buttons\\WHITE8X8",
        edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
        tile = false, edgeSize = 32,
        insets = { left = 11, right = 12, top = 12, bottom = 11 },
    })
    -- near solid, like the panel's flyouts: the world must not show through the rows
    card:SetBackdropColor(0.03, 0.03, 0.05, 0.96)
    card:EnableMouse(true)
    card:Hide()
    CW.summary = card
    tinsert(UISpecialFrames, "ClasslessWildcardSummary")

    card.icon = card:CreateTexture(nil, "ARTWORK")
    card.icon:SetWidth(ICON); card.icon:SetHeight(ICON)
    card.icon:SetPoint("TOPLEFT", PAD + 2, -PAD - 2)
    card.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    card.iconBorder = card:CreateTexture(nil, "OVERLAY")
    card.iconBorder:SetWidth(ICON + 22); card.iconBorder:SetHeight(ICON + 22)
    card.iconBorder:SetPoint("CENTER", card.icon, "CENTER", 0, 0)
    card.iconBorder:SetTexture("Interface\\Buttons\\UI-Quickslot2")
    card.title = card:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    card.title:SetPoint("TOPLEFT", card.icon, "TOPRIGHT", 12, -2)
    card.title:SetJustifyH("LEFT")
    card.subtitle = card:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    card.subtitle:SetPoint("TOPLEFT", card.title, "BOTTOMLEFT", 0, -5)
    card.subtitle:SetPoint("RIGHT", card, "RIGHT", -PAD, 0)
    card.subtitle:SetJustifyH("LEFT")

    card.button = CreateFrame("Button", nil, card, "UIPanelButtonTemplate")
    card.button:SetWidth(130); card.button:SetHeight(22)
    card.button:SetScript("OnClick", function() card:Hide() end)

    -- pooled pieces, made the first time a card needs that many
    card.headers, card.rules, card.rows, card.notes = {}, {}, {}, {}
    local function Header(i)
        local h = card.headers[i]
        if not h then
            h = card:CreateFontString(nil, "OVERLAY", "GameFontNormal")
            h:SetJustifyH("LEFT")
            card.headers[i] = h
        end
        return h
    end
    local function Rule(i)
        local r = card.rules[i]
        if not r then
            r = card:CreateTexture(nil, "ARTWORK")
            r:SetHeight(1)
            r:SetTexture(1, 0.82, 0, 0.25)
            card.rules[i] = r
        end
        return r
    end
    local function Row(i)
        local r = card.rows[i]
        if not r then
            r = {}
            r.icon = card:CreateTexture(nil, "ARTWORK")
            r.icon:SetWidth(16); r.icon:SetHeight(16)
            r.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
            r.label = card:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
            r.label:SetJustifyH("LEFT")
            r.label:SetWidth(LABEL_W)
            r.value = card:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
            r.value:SetJustifyH("RIGHT")
            card.rows[i] = r
        end
        return r
    end
    local function Note(i)
        local n = card.notes[i]
        if not n then
            n = card:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
            n:SetJustifyH("LEFT")
            n:SetWidth(W - 2 * PAD)
            card.notes[i] = n
        end
        return n
    end
    local function HideAll(list, key)
        for _, v in ipairs(list) do
            if key then v[key]:Hide() else v:Hide() end
        end
    end

    -- A Rebirth that ends a live run sends both cards at once; the second
    -- waits for the first to be closed rather than replacing it unseen.
    card.queue = {}
    card:SetScript("OnHide", function()
        local nextSpec = tremove(card.queue, 1)
        if nextSpec then CW.ShowSummary(nextSpec) end
    end)

    function CW.ShowSummary(spec)
        if card:IsShown() then
            tinsert(card.queue, spec)
            return
        end
        HideAll(card.headers); HideAll(card.rules); HideAll(card.notes)
        for _, r in ipairs(card.rows) do r.icon:Hide(); r.label:Hide(); r.value:Hide() end

        card.icon:SetTexture(spec.icon or "Interface\\Icons\\INV_Misc_QuestionMark")
        local c = spec.titleColor or GOLD
        card.title:SetText(spec.title or "")
        card.title:SetTextColor(c[1], c[2], c[3])
        card.subtitle:SetText(spec.subtitle or "")

        local y = -PAD - ICON - 18
        local nh, nr = 0, 0
        for _, sec in ipairs(spec.sections or {}) do
            nh = nh + 1
            local h = Header(nh)
            h:ClearAllPoints()
            h:SetPoint("TOPLEFT", PAD, y)
            h:SetText(sec.header or "")
            h:Show()
            local rule = Rule(nh)
            rule:ClearAllPoints()
            rule:SetPoint("TOPLEFT", PAD, y - 16)
            rule:SetPoint("TOPRIGHT", -PAD, y - 16)
            rule:Show()
            y = y - 22
            for _, row in ipairs(sec.rows or {}) do
                nr = nr + 1
                local r = Row(nr)
                local x = PAD + 4
                r.icon:ClearAllPoints()
                if row[4] then
                    r.icon:SetTexture(row[4])
                    r.icon:SetPoint("TOPRIGHT", card, "TOPRIGHT", -PAD, y - 1)
                end
                r.label:ClearAllPoints()
                r.label:SetPoint("TOPLEFT", x, y - 2)
                r.label:SetText(row[1] or "")
                r.label:SetTextColor(0.85, 0.85, 0.85)
                r.value:ClearAllPoints()
                r.value:SetPoint("TOPRIGHT", card, "TOPRIGHT", row[4] and (-PAD - 22) or -PAD, y - 2)
                r.value:SetWidth(W - 2 * PAD - 4 - LABEL_W - 8 - (row[4] and 22 or 0))
                r.value:SetText(row[2] or "")
                local vc = row[3] or { 1, 1, 1 }
                r.value:SetTextColor(vc[1], vc[2], vc[3])
                r.label:Show(); r.value:Show()
                if row[4] then r.icon:Show() end
                y = y - ROW_H
            end
            y = y - 12
        end

        for i, text in ipairs(spec.notes or {}) do
            local n = Note(i)
            n:ClearAllPoints()
            n:SetPoint("TOPLEFT", PAD, y)
            n:SetText(text)
            n:SetTextColor(0.75, 0.75, 0.75)
            n:Show()
            local h = n:GetStringHeight()
            y = y - ((h and h > 0) and h or 12) - 5
        end

        y = y - 10
        card.button:ClearAllPoints()
        card.button:SetPoint("TOP", card, "TOP", 0, y)
        card.button:SetText(spec.button or OKAY)
        card:SetHeight(-y + 24 + PAD + 2)
        card:Show()
    end

    -- "RE|finished|level|shards|gold|name|challenge|lives left|lives max|
    --  reward spell|title|Unbroken title|repeat"; the fields past name are
    -- absent from older servers and read as nothing new.
    function CW.RunEndSpec(p)
        local finished, level = tonumber(p[2]) == 1, tonumber(p[3]) or 1
        local shards, gold, name = tonumber(p[4]) or 0, tonumber(p[5]) or 0, p[6] or "Challenge"
        local id, left, max = tonumber(p[7]) or 0, tonumber(p[8]) or 0, tonumber(p[9]) or 0
        local reward, title, unbroken = tonumber(p[10]) or 0, p[11] or "", p[12] or ""
        local repeatRun = tonumber(p[13]) == 1
        -- 14: deaths on the run, 15: ended by a Rebirth (both from newer servers)
        local deaths, rebirth = tonumber(p[14]), tonumber(p[15]) == 1
        local ch = CW.challengesById and CW.challengesById[id]
        local iconSpell = reward > 0 and reward or (ch and ch.reward or 0)

        local run = { { "Level reached", tostring(level) } }
        if CW.Unlimited(max) then
            tinsert(run, { "Lives", "Unlimited" })
        elseif max > 0 then
            tinsert(run, { "Lives left", left .. " of " .. max })
        end
        local rewards = { { "Shards", tostring(shards), GOLD, CW.SHARD_ICON } }
        if gold > 0 then tinsert(rewards, { "Gold", tostring(gold), GOLD, "Interface\\MoneyFrame\\UI-GoldIcon" }) end
        if reward > 0 then
            tinsert(rewards, { "Heirloom ability", (GetSpellInfo(reward)) or "Reward ability", PURPLE, SpellIcon(reward) })
        end
        if title ~= "" then tinsert(rewards, { "New title", title, GOLD }) end
        if unbroken ~= "" then tinsert(rewards, { "New title", unbroken, GOLD }) end

        local notes = {}
        -- an unlimited run never spends a life, so only the death count can say it was clean
        local clean = deaths and deaths == 0 or (not deaths and max > 0 and not CW.Unlimited(max) and left == max)
        if finished and clean then
            tinsert(notes, (CW.Unlimited(max) and "Not a single death" or "Not a life lost") .. ": a third more shards.")
        end
        if repeatRun then tinsert(notes, "Gold is paid for the first finish only.") end
        if rebirth then
            tinsert(notes, "Your Rebirth ended the run. The rule lifts.")
        else
            tinsert(notes, finished and "The rule lifts." or "The rule lifts. Your level, gear and build stay.")
        end

        return {
            icon = iconSpell > 0 and SpellIcon(iconSpell) or "Interface\\Icons\\INV_Misc_Bone_HumanSkull_01",
            title = finished and "Challenge Complete" or "Challenge Over",
            titleColor = finished and GREEN or { 1, 0.27, 0.27 },
            subtitle = name,
            sections = { { header = "The run", rows = run }, { header = finished and "Rewards" or "Earned", rows = rewards } },
            notes = notes,
            button = OKAY,
        }
    end

    -- "RB|rank|kill%|other%|stat%|questsKept|mailed|abilityEssence|talentEssence|
    --  heirlooms next time|new title|carried ids"
    function CW.RebirthDoneSpec(p)
        local rank = tonumber(p[2]) or 1
        local kill, other, stat = tonumber(p[3]) or 0, tonumber(p[4]) or 0, tonumber(p[5]) or 0
        local kept, mailed = tonumber(p[6]) == 1, tonumber(p[7]) or 0
        local ae, te, nextMax = tonumber(p[8]) or 0, tonumber(p[9]) or 0, tonumber(p[10]) or 0
        local title, ids = p[11] or "", p[12] or ""

        local life = {}
        for id in string.gmatch(ids, "%d+") do
            id = tonumber(id)
            tinsert(life, { #life == 0 and "Heirlooms" or "", (GetSpellInfo(id)) or ("#" .. id), ORANGE, SpellIcon(id) })
        end
        if #life == 0 then tinsert(life, { "Heirlooms", "None", GREY }) end
        if ae > 0 or te > 0 then
            tinsert(life, { "Ability Essence", tostring(ae), GREEN })
            tinsert(life, { "Talent Essence", tostring(te), GREEN })
        else
            tinsert(life, { "Starting hand", "Dealt", GREEN })
        end
        tinsert(life, { "Quest history", kept and "Kept" or "Cleared" })
        if title ~= "" then tinsert(life, { "New title", title, GOLD }) end

        local notes = {}
        if not kept then tinsert(notes, "Every quest pays its experience again.") end
        if mailed > 0 then
            tinsert(notes, mailed .. (mailed == 1 and " piece of gear" or " pieces of gear")
                .. " did not fit in your bags and " .. (mailed == 1 and "was" or "were") .. " mailed to you.")
        end
        if nextMax > 0 then
            tinsert(notes, "Your next Rebirth carries up to " .. nextMax .. (nextMax == 1 and " heirloom." or " heirlooms."))
        end

        return {
            icon = "Interface\\Icons\\Spell_Nature_Reincarnation",
            title = "Rebirth " .. rank,
            titleColor = ORANGE,
            subtitle = "A new life begins at level 1.",
            sections = {
                { header = "Your rank", rows = {
                    { "Kills and dungeons", "+" .. kill .. "% XP", GREEN },
                    { "Quests, exploration, PvP", "+" .. other .. "% XP", GREEN },
                    { "Every primary stat", "+" .. stat .. "%", GREEN },
                } },
                { header = "This life", rows = life },
            },
            notes = notes,
            button = "Begin",
        }
    end
end
do
    -- The whole panel, edge to edge, so the challenges get its full size.
    -- Two panes. On the left every challenge at once, each a row with its
    -- lives as pips and its gold. On the right the
    -- one selected, in full: the rule, how it plays, what it takes to start,
    -- its lives, every reward with the reward ability's own tooltip, and the
    -- character's record on it. The right pane scrolls, so no amount of text
    -- can run into anything; the bottom bar under it holds Start, and the X
    -- in the top-right closes it.
    --
    -- Measured, left: title -12, subtitle -34, fourteen rows of 29 from -54
    -- (to -460; thirteen challenges and room for one more), shards at 40 from
    -- the bottom, Extra life at 10. Right: name -12,
    -- rule -40 (two lines, to -72), divider -80, scroll from -86 to 46 from
    -- the bottom, Start at 12, the summary at 18. Widths follow the panel's.
    local fly = CreateFrame("Frame", "ClasslessWildcardRuns", frame)
    fly:SetAllPoints(frame)
    fly:SetWidth(frame:GetWidth()); fly:SetHeight(frame:GetHeight())
    CW.OverPanel(fly)   -- under the confirm popups, over the panel
    fly:SetBackdrop({
        bgFile = "Interface\\Buttons\\WHITE8X8",
        edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
        tile = false, edgeSize = 14,
        insets = { left = 4, right = 4, top = 4, bottom = 4 },
    })
    fly:SetBackdropColor(0.03, 0.03, 0.05, 0.98)
    fly:EnableMouse(true)
    fly:Hide()
    CW.runFly = fly
    fly.selected = nil
    local FLY_W = frame:GetWidth()
    -- the right pane's text column: the scroll frame's width less its bar
    local ROWS, ROW_H, LEFT_W, RX, CW_W = 14, 29, 284, 318, FLY_W - 318 - 72
    -- gold as the game draws it: the amount, then the gold coin
    local function Coin(amount, size)
        size = size or 14
        return "|cffffffff" .. amount .. "|r|TInterface\\MoneyFrame\\UI-GoldIcon:" .. size .. ":" .. size .. ":2:0|t"
    end
    local OK = "|TInterface\\RAIDFRAME\\ReadyCheck-Ready:14:14:0:-1|t "
    local NO = "|TInterface\\RAIDFRAME\\ReadyCheck-NotReady:14:14:0:-1|t "

    fly.close = CreateFrame("Button", nil, fly, "UIPanelCloseButton")
    fly.close:SetPoint("TOPRIGHT", -2, -2)
    fly.close:SetScript("OnClick", function() fly:Hide() end)

    -- ---- left: the list --------------------------------------------------
    fly.listTitle = fly:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    fly.listTitle:SetPoint("TOPLEFT", 16, -12)
    fly.listTitle:SetText("Challenge Runs")
    fly.listSub = fly:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    fly.listSub:SetPoint("TOPLEFT", 16, -34)
    fly.listSub:SetWidth(LEFT_W)
    fly.listSub:SetJustifyH("LEFT")
    fly.listSub:SetText("|cffaaaaaaOne rule, and the lives it gives.|r")

    fly.rows = {}
    for i = 1, ROWS do
        local r = CreateFrame("Button", nil, fly)
        r:SetWidth(LEFT_W); r:SetHeight(ROW_H)
        r:SetPoint("TOPLEFT", 12, -54 - (i - 1) * ROW_H)
        r.stripe = r:CreateTexture(nil, "BACKGROUND")
        r.stripe:SetAllPoints(r)
        r.stripe:SetTexture("Interface\\Buttons\\WHITE8X8")
        r.accent = r:CreateTexture(nil, "BORDER")
        r.accent:SetWidth(3)
        r.accent:SetPoint("TOPLEFT", 0, 0); r.accent:SetPoint("BOTTOMLEFT", 0, 0)
        r.accent:SetTexture("Interface\\Buttons\\WHITE8X8")
        r.accent:SetVertexColor(1, 0.82, 0.2, 1)
        r.accent:Hide()
        r.name = r:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        r.name:SetPoint("LEFT", 12, 0)
        r.name:SetWidth(120)
        r.name:SetJustifyH("LEFT")
        r.pips = {}
        for k = 1, 6 do
            local pip = CW.MakePip(r, 12)
            pip:SetPoint("LEFT", r, "LEFT", 136 + (k - 1) * 13, 0)
            r.pips[k] = pip
        end
        -- beside the one heart of a run with no limit on lives
        r.unlimited = r:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
        r.unlimited:SetPoint("LEFT", r, "LEFT", 136 + 15, 0)
        r.unlimited:SetText("|cffaaaaaaunlimited|r")
        r.unlimited:Hide()
        r.done = r:CreateTexture(nil, "OVERLAY")
        r.done:SetWidth(16); r.done:SetHeight(16)
        r.done:SetPoint("LEFT", r, "LEFT", 218, 0)
        r.done:SetTexture("Interface\\RAIDFRAME\\ReadyCheck-Ready")
        r.done:Hide()
        r.gold = r:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
        r.gold:SetPoint("RIGHT", -8, 0)
        r.gold:SetJustifyH("RIGHT")
        r:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight", "ADD")
        r:SetScript("OnClick", function(self)
            if self.id and self.id ~= fly.selected then
                if PlaySound then pcall(PlaySound, "igMainMenuOptionCheckBoxOn") end
                fly.selected = self.id
                CW.RenderRuns(true)
            end
        end)
        fly.rows[i] = r
    end

    fly.shards = fly:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    fly.shards:SetPoint("BOTTOMLEFT", 16, 40)
    fly.shards:SetWidth(LEFT_W)
    fly.shards:SetJustifyH("LEFT")
    fly.life = CreateFrame("Button", nil, fly, "UIPanelButtonTemplate")
    fly.life:SetWidth(200); fly.life:SetHeight(22)
    fly.life:SetPoint("BOTTOMLEFT", 12, 10)
    fly.life:SetScript("OnClick", function() StaticPopup_Show("CW_CLASSLESS_BUYLIFE", CW.EXTRA_LIFE_SHARDS) end)
    fly.life:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_TOP")
        GameTooltip:SetText("Extra life")
        GameTooltip:AddLine("One more life for your next run, " .. CW.EXTRA_LIFE_SHARDS .. " shards. One per run.", 0.8, 0.8, 0.8, true)
        GameTooltip:AddLine("Shards come from every run that ends: one per level reached, two per level past 60, a third more with no life lost.", 0.6, 0.6, 0.6, true)
        GameTooltip:Show()
    end)
    fly.life:SetScript("OnLeave", function() GameTooltip:Hide() end)

    fly.split = fly:CreateTexture(nil, "ARTWORK")
    fly.split:SetWidth(1)
    fly.split:SetPoint("TOPLEFT", RX - 14, -12)
    fly.split:SetPoint("BOTTOMLEFT", RX - 14, 12)
    fly.split:SetTexture(1, 1, 1, 0.12)

    -- ---- right: the header -------------------------------------------------
    fly.dName = fly:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    fly.dName:SetPoint("TOPLEFT", RX, -12)
    fly.dName:SetWidth(FLY_W - RX - 40)     -- a width, not a RIGHT anchor: that would centre it vertically
    fly.dName:SetJustifyH("LEFT")
    fly.rule = fly:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    fly.rule:SetPoint("TOPLEFT", RX, -40)
    fly.rule:SetWidth(FLY_W - RX - 40)
    fly.rule:SetJustifyH("LEFT")
    fly.rule:SetJustifyV("TOP")
    fly.rule:SetHeight(34)
    fly.headLine = fly:CreateTexture(nil, "ARTWORK")
    fly.headLine:SetHeight(1)
    fly.headLine:SetPoint("TOPLEFT", RX, -80)
    fly.headLine:SetPoint("TOPRIGHT", -16, -80)
    fly.headLine:SetTexture(1, 0.82, 0.2, 0.35)

    -- ---- right: the scrolling detail --------------------------------------
    fly.scroll = CreateFrame("ScrollFrame", "ClasslessWildcardRunsScroll", fly, "UIPanelScrollFrameTemplate")
    fly.scroll:SetPoint("TOPLEFT", RX, -86)
    fly.scroll:SetPoint("BOTTOMRIGHT", -36, 46)
    fly.content = CreateFrame("Frame", nil, fly.scroll)
    fly.content:SetWidth(CW_W); fly.content:SetHeight(1)
    fly.scroll:SetScrollChild(fly.content)
    local C = fly.content

    local function Header(text)
        local h = C:CreateFontString(nil, "OVERLAY", "GameFontNormal")
        h:SetJustifyH("LEFT")
        h:SetText(text)
        h.line = C:CreateTexture(nil, "ARTWORK")
        h.line:SetHeight(1)
        h.line:SetTexture(1, 0.82, 0.2, 0.25)
        return h
    end
    local function Body(font)
        local b = C:CreateFontString(nil, "OVERLAY", font or "GameFontHighlight")
        b:SetWidth(CW_W)
        b:SetJustifyH("LEFT")
        b:SetJustifyV("TOP")
        b:SetSpacing(3)
        return b
    end

    fly.hPlay = Header("How it plays")
    fly.detail = Body()
    fly.detail:SetTextColor(0.88, 0.88, 0.88)
    fly.hTips = Header("Tips")
    fly.tips = Body()
    fly.tips:SetTextColor(0.88, 0.88, 0.88)
    fly.hReq = Header("Starting this run")
    fly.req = Body()
    fly.hLives = Header("Lives")
    fly.lifePips = {}
    for k = 1, 6 do fly.lifePips[k] = CW.MakePip(C, 16) end
    fly.livesText = Body()
    fly.hReward = Header("Rewards for finishing")
    fly.rewardIntro = Body("GameFontHighlightSmall")
    fly.rewardIntro:SetTextColor(0.7, 0.7, 0.7)
    -- one label and one value per reward, the values in one column so every
    -- line starts at the same place however long its label is
    fly.rwLabels, fly.rwValues = {}, {}
    for k = 1, 5 do
        local l = C:CreateFontString(nil, "OVERLAY", "GameFontNormal")
        l:SetWidth(118)
        l:SetJustifyH("LEFT"); l:SetJustifyV("TOP")
        local v = C:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        v:SetWidth(CW_W - 128)
        v:SetJustifyH("LEFT"); v:SetJustifyV("TOP")
        v:SetSpacing(3)
        fly.rwLabels[k], fly.rwValues[k] = l, v
    end

    fly.hAbility = Header("Reward ability")
    fly.abilityBtn = CreateFrame("Button", nil, C)
    fly.abilityBtn:SetWidth(44); fly.abilityBtn:SetHeight(44)
    fly.abilityBtn.icon = fly.abilityBtn:CreateTexture(nil, "ARTWORK")
    fly.abilityBtn.icon:SetAllPoints(fly.abilityBtn)
    fly.abilityBtn.icon:SetTexCoord(0.06, 0.94, 0.06, 0.94)
    fly.abilityBtn.ring = fly.abilityBtn:CreateTexture(nil, "OVERLAY")
    fly.abilityBtn.ring:SetWidth(76); fly.abilityBtn.ring:SetHeight(76)
    fly.abilityBtn.ring:SetPoint("CENTER", 0, 0)
    fly.abilityBtn.ring:SetTexture("Interface\\Buttons\\UI-ActionButton-Border")
    fly.abilityBtn.ring:SetBlendMode("ADD")
    fly.abilityBtn.ring:SetVertexColor(0.64, 0.21, 0.93)
    fly.abilityBtn:SetScript("OnEnter", function(self)
        if not self.spellId then return end
        GameTooltip:Hide()   -- the same link on a shown tooltip toggles it off
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetHyperlink("spell:" .. self.spellId)
        GameTooltip:Show()
    end)
    fly.abilityBtn:SetScript("OnLeave", function() GameTooltip:Hide() end)
    fly.abilityName = C:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    fly.abilityName:SetJustifyH("LEFT")
    fly.abilitySub = C:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    fly.abilitySub:SetJustifyH("LEFT")
    fly.abilitySub:SetTextColor(0.7, 0.7, 0.7)
    fly.abilityNote = Body()
    -- the spell's own tooltip, in a box like the tooltip it is: a dark plate
    -- with a hairline border in the epic colour. Its rows hang under this
    -- invisible line, at its width.
    fly.plateLine = C:CreateTexture(nil, "ARTWORK")
    fly.plateLine:SetHeight(1)
    fly.plateLine:SetWidth(CW_W - 28)
    fly.plateLine:SetTexture(1, 1, 1, 0)
    fly.hRecord = Header("Your record")
    fly.record = Body()

    -- ---- the bottom bar ------------------------------------------------------
    fly.summary = fly:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    fly.summary:SetPoint("BOTTOMLEFT", RX, 18)
    fly.summary:SetWidth(330)
    fly.summary:SetJustifyH("LEFT")
    fly.start = CreateFrame("Button", nil, fly, "UIPanelButtonTemplate")
    fly.start:SetWidth(170); fly.start:SetHeight(22)
    fly.start:SetPoint("BOTTOMRIGHT", -14, 12)
    fly.start:SetText("Start this run")
    fly.start:SetScript("OnClick", function() CW.AskRun() end)
    -- No Back button: the X in the top-right is the one way out, as on every
    -- other panel in the game.

    function CW.RunName(id)
        local c = CW.challengesById and CW.challengesById[id]
        return c and c.name or nil
    end

    local function Selected()
        for _, c in ipairs(CW.challenges) do
            if c.id == fly.selected then return c end
        end
        return CW.challenges[1]
    end

    -- Stack the detail top to bottom from measured heights. Every block's top
    -- is the bottom of the one above it plus a gap, so a long rule or a long
    -- spell description pushes everything under it and nothing overlaps.
    local function Place(region, x, y)
        region:ClearAllPoints()
        region:SetPoint("TOPLEFT", C, "TOPLEFT", x, -y)
    end
    local function H(region, fallback)
        local v = tonumber(region:GetStringHeight()) or 0
        return v > 0 and v or (fallback or 14)
    end
    local function PlaceHeader(h, y)
        Place(h, 0, y)
        h.line:ClearAllPoints()
        h.line:SetPoint("TOPLEFT", C, "TOPLEFT", 0, -(y + 18))
        h.line:SetWidth(CW_W)
        h:Show(); h.line:Show()
        return y + 26
    end

    local function FillDetail(c, s)
        local y = 0
        local player = UnitName("player") or "you"

        -- how it plays
        y = PlaceHeader(fly.hPlay, y)
        fly.detail:SetText(CW.FormatChallengeText(c.detail ~= "" and c.detail or c.rule))
        Place(fly.detail, 0, y)
        y = y + H(fly.detail, 48) + 18

        -- tips: what actually helps under this rule
        if (c.tips or "") ~= "" then
            y = PlaceHeader(fly.hTips, y)
            fly.tips:SetText(CW.FormatChallengeText(c.tips))
            Place(fly.tips, 0, y)
            fly.tips:Show()
            y = y + H(fly.tips, 48) + 18
        else
            fly.hTips:Hide(); fly.hTips.line:Hide(); fly.tips:Hide()
        end

        -- Starting this run: whether this character can start it right now.
        y = PlaceHeader(fly.hReq, y)
        local cap = CW.rules.maxLevel
        local status
        local live = CW.challengesById and CW.challengesById[s.run or 0]
        local lives = CW.LivesLeftText(s.lives, s.livesMax)
        -- Only what the player cannot already tell: whether it can start. When
        -- the run ends is under Lives and Rewards below.
        if (s.run or 0) > 0 and s.run == c.id then
            status = "|cffff8800You are on this run|r: " .. lives .. "."
        elseif (s.run or 0) > 0 then
            status = NO .. "|cffff4444You are on " .. (live and live.name or "another run") .. "|r: " .. lives .. "."
        elseif not CW.RunPathFits(c) then
            status = NO .. "|cffff4444" .. CW.RunPathText(c) .. "|r"
        elseif s.runReady == 1 then
            status = OK .. "|cff00ff00You can start this now.|r"
        else
            status = NO .. "|cffff4444Challenge runs start before level " .. (s.deadline or 2) .. ".|r"
        end
        fly.req:SetText(status)
        Place(fly.req, 0, y)
        y = y + H(fly.req, 60) + 18

        -- lives
        y = PlaceHeader(fly.hLives, y)
        local unlimited = CW.Unlimited(c.lives)
        local extra = (s.extraLife or 0) > 0 and not unlimited and 1 or 0
        local total = unlimited and 1 or math.min(6, c.lives + extra)
        for k = 1, 6 do
            local pip = fly.lifePips[k]
            pip:ClearAllPoints()
            pip:SetPoint("TOPLEFT", C, "TOPLEFT", (k - 1) * 19, -(y + 1))
            CW.SetPip(pip, k <= total, true)
        end
        if unlimited then
            fly.livesText:SetText("|cffffffffUnlimited lives|r on this challenge. A death never ends the run"
                .. ((s.extraLife or 0) > 0 and ", and the extra life you hold waits for your next run." or "."))
        else
            fly.livesText:SetText("|cffffffff" .. c.lives .. (c.lives == 1 and " life" or " lives") .. "|r on this challenge"
                .. (extra > 0 and ", |cff00ff00plus the extra life you hold|r" or "") .. ". "
                .. "A death costs one. Deaths in battlegrounds, arenas and duels cost nothing. "
                .. "Run out and the run ends: the rule lifts, and you keep your level, gear and build.")
        end
        Place(fly.livesText, 0, y + 24)
        y = y + 24 + H(fly.livesText, 32) + 18

        -- rewards: a label column and a value column, every value a sentence
        y = PlaceHeader(fly.hReward, y)
        local goal = " with at least one life left."
        if (c.vengeance or 0) > 0 then
            goal = " with " .. c.vengeance .. " Vengeance: the total level of the nemeses you slay."
        elseif CW.Unlimited(c.lives) then
            goal = "."
        end
        fly.rewardIntro:SetText("Paid once, when you reach level " .. CW.rules.maxLevel .. goal)
        Place(fly.rewardIntro, 0, y)
        y = y + H(fly.rewardIntro, 12) + 10
        local title = (c.title or ""):gsub("%%s", player)
        local rows = {
            { "Gold", Coin(c.gold) },
            { "Title", title ~= "" and ("|cffe6cc80" .. title .. "|r") or "None" },
            { "Flawless run", "Finish without " .. (CW.Unlimited(c.lives) and "dying" or "losing a life")
                .. " to also earn |cffe6cc80" .. player
                .. " the Unbroken|r and a third more shards." },
            { "Shards", "Paid whenever the run ends, whether you finish or not. You earn one per level reached, and two per level past 60." },
        }
        if c.finished == 1 then
            tinsert(rows, { "Already earned", "You finished this challenge. Running it again pays shards, and the Unbroken title if you have not earned it." })
        end
        for k = 1, 5 do
            local l, v = fly.rwLabels[k], fly.rwValues[k]
            local row = rows[k]
            if row then
                l:SetText(row[1]); v:SetText(row[2])
                Place(l, 0, y); Place(v, 128, y)
                l:Show(); v:Show()
                y = y + math.max(H(l, 14), H(v, 14)) + 8
            else
                l:Hide(); v:Hide()
            end
        end
        y = y + 10

        -- the reward ability, in full
        y = PlaceHeader(fly.hAbility, y)
        local reward = c.reward or 0
        local plate = fly.plate
        if reward > 0 then
            local name = (GetSpellInfo(reward)) or "Reward ability"
            fly.abilityBtn.spellId = reward
            fly.abilityBtn.icon:SetTexture(SpellIcon(reward))
            Place(fly.abilityBtn, 2, y + 2)
            fly.abilityBtn:Show()
            fly.abilityName:SetText("|cffa335ee" .. name .. "|r")
            Place(fly.abilityName, 58, y + 4)
            fly.abilityName:Show()
            fly.abilitySub:SetText("Epic ability, kept as an heirloom")
            Place(fly.abilitySub, 58, y + 27)
            fly.abilitySub:Show()
            y = y + 56
            fly.abilityNote:SetText("No roll or shop can give this ability. Once earned it is yours as an heirloom: "
                .. "you can use it from level 1, it carries through every Rebirth, and it is never rerolled or refunded. "
                .. "Hover the icon for the full tooltip.")
            Place(fly.abilityNote, 0, y)
            fly.abilityNote:Show()
            y = y + H(fly.abilityNote, 42) + 12

            -- the tooltip box
            if not plate then
                plate = CW.revealFX.MakeInfo(C, fly.plateLine)
                plate:SetRowWidth(CW_W - 28)
                -- the body's size, not the card's 14: this sits among
                -- paragraphs, not under a die
                for i = 1, #plate.rows do
                    local face = plate.rows[i].left:GetFont()
                    if face then
                        plate.rows[i].left:SetFont(face, 12)
                        plate.rows[i].right:SetFont(face, 12)
                    end
                end
                fly.plate = plate
            end
            Place(fly.plateLine, 14, y + 2)
            local ph = plate:Fill(reward) or 0
            local boxH = 2 + 10 + ph + 12
            plate.panel:ClearAllPoints()
            plate.panel:SetPoint("TOPLEFT", C, "TOPLEFT", 0, -y)
            plate.panel:SetWidth(CW_W)
            plate.panel:SetHeight(boxH)
            plate.panel:Show()
            for _, e in ipairs(plate.edges) do
                e:SetVertexColor(0.64, 0.21, 0.93, 0.85)
                e:Show()
            end
            y = y + boxH + 18
        else
            fly.abilityBtn.spellId = nil
            fly.abilityBtn:Hide(); fly.abilityName:Hide(); fly.abilitySub:Hide()
            if plate then plate:Clear() end
            fly.abilityNote:SetText("|cffaaaaaaThis challenge pays its gold and title, but no ability.|r")
            Place(fly.abilityNote, 0, y)
            fly.abilityNote:Show()
            y = y + H(fly.abilityNote, 14) + 18
        end

        -- record
        y = PlaceHeader(fly.hRecord, y)
        local rec
        if c.finished == 1 then
            rec = OK .. "|cff00ff00Finished.|r Its gold, title and ability have been paid."
        elseif (c.best or 0) > 0 then
            rec = "Not finished yet. Your best on it: level " .. c.best .. "."
        else
            rec = "You have not tried this one yet."
        end
        fly.record:SetText(rec)
        Place(fly.record, 0, y)
        y = y + H(fly.record, 14) + 14

        C:SetHeight(y)
    end

    function CW.RenderRuns(toTop)
        local s = CW.state
        local list = CW.challenges
        if not fly.selected and list[1] then fly.selected = list[1].id end

        fly.shards:SetText("Shards  |cff00ff00" .. (s.shards or 0) .. "|r" .. CW.ShardTag()
            .. ((s.extraLife or 0) > 0 and "     |cff00ff00extra life held|r" or ""))
        fly.life:SetText((s.extraLife or 0) > 0 and "Extra life held"
            or ("Buy an extra life  (" .. CW.EXTRA_LIFE_SHARDS .. CW.ShardTag() .. ")"))
        if (s.extraLife or 0) > 0 or (s.shards or 0) < CW.EXTRA_LIFE_SHARDS then fly.life:Disable() else fly.life:Enable() end

        for i = 1, ROWS do
            local c = list[i]
            local r = fly.rows[i]
            if c then
                r.id = c.id
                local mark = fly.selected == c.id
                r.name:SetText((mark and "|cffffd100" or "|cffffffff") .. c.name .. "|r")
                local pips = CW.PipCount(c.lives, 6)
                for k = 1, 6 do CW.SetPip(r.pips[k], k <= pips, true) end
                if CW.Unlimited(c.lives) then r.unlimited:Show() else r.unlimited:Hide() end
                if c.finished == 1 then r.done:Show() else r.done:Hide() end
                r.gold:SetText(Coin(c.gold, 12))
                if mark then
                    r.stripe:SetVertexColor(1, 0.82, 0.3, 0.16)
                    r.accent:Show()
                else
                    r.stripe:SetVertexColor(1, 1, 1, i % 2 == 0 and 0.03 or 0.07)
                    r.accent:Hide()
                end
                r:Show()
            else
                r.id = nil
                r:Hide()
            end
        end

        local c = #list > 0 and Selected() or nil
        if c then
            fly.dName:SetText(c.name)
            fly.rule:SetText(c.rule)
            FillDetail(c, s)
            fly.scroll:Show()
            if CW.Unlimited(c.lives) then
                fly.summary:SetText("Starts with |cffffffffunlimited lives|r")
            else
                local lives = math.min(6, c.lives + ((s.extraLife or 0) > 0 and 1 or 0))
                fly.summary:SetText("Starts with |cffffffff" .. lives .. (lives == 1 and " life" or " lives") .. "|r")
            end
            local canStart = (s.run or 0) == 0 and s.runReady == 1 and CW.RunPathFits(c)
            if canStart then fly.start:Enable() else fly.start:Disable() end
        else
            fly.dName:SetText("Challenge Runs")
            fly.rule:SetText("|cffaaaaaaLoading the challenges...|r")
            fly.scroll:Hide()
            fly.summary:SetText("")
            fly.start:Disable()
        end
        if toTop and fly.scroll.SetVerticalScroll then fly.scroll:SetVerticalScroll(0) end
    end

    -- The page is the panel's child, so it can only show while the panel
    -- does: the tracker's click, with the panel closed, showed nothing.
    function CW.OpenRuns()
        if not frame:IsShown() then frame:Show() end
        CW.OverPanel(fly)
        if CW.rebirthFly then CW.rebirthFly:Hide() end
        if CW.archFly then CW.archFly:Hide() end
        if CW.helpFly then CW.helpFly:Hide() end
        if CW.statFly then CW.statFly:Hide() end
        if CW.setFly then CW.setFly:Hide() end
        Send("CHL")
        CW.RenderRuns(true)
        fly:Show()
    end

    function CW.AskRun()
        local s = CW.state
        local chosen = #CW.challenges > 0 and Selected() or nil
        if not chosen then return end
        fly.pendingId = chosen.id
        local livesText
        if CW.Unlimited(chosen.lives) then
            livesText = "unlimited lives"
        else
            local lives = chosen.lives + ((s.extraLife or 0) > 0 and 1 or 0)
            livesText = lives .. (lives == 1 and " life" or " lives")
        end
        StaticPopup_Show("CW_RUN_CONFIRM", "|cffff4444" .. chosen.name .. "|r with " .. livesText
            .. ".\n\n" .. chosen.rule)
    end

    function fly.Confirm()
        Send("RUN " .. (fly.pendingId or 0))
    end
end
CW.EXTRA_LIFE_SHARDS = 30   -- what the server charges; the label only
-- Shards beside a count, the way the gold coin sits beside gold. The client's
-- own Soul Shard icon.
CW.SHARD_ICON = "Interface\\Icons\\INV_Misc_Gem_Amethyst_02"
function CW.ShardTag(size)
    size = size or 14
    return "|T" .. CW.SHARD_ICON .. ":" .. size .. ":" .. size .. ":2:0|t"
end


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

-- The essence line hangs between the two button clusters. Anchored to the
-- buttons themselves rather than the frame's centre, so it cannot land under
-- Settings whatever the frame's width, and Buy Scroll or Archetypes taking the
-- slot beside Help changes nothing: Settings already sits past the wider of them.
bottomText:ClearAllPoints()
bottomText:SetPoint("LEFT", setBtn, "RIGHT", 12, 0)
bottomText:SetPoint("RIGHT", statsBtn, "LEFT", -12, 0)

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
-- Wider and taller than it was: each row now carries the character's TOTAL for
-- that stat and everything the stat is doing at that total, not just how many
-- points were spent on it. "Intellect 30 pts = +30" said nothing about the 28
-- Intellect the character actually had, nor about the mana and crit it gave.
statFly:SetWidth(frame:GetWidth()); statFly:SetHeight(frame:GetHeight())
statFly:SetPoint("CENTER", frame, "CENTER", 0, 0)
statFly:SetFrameStrata("DIALOG")
statFly:SetBackdrop({
    bgFile = "Interface\\Buttons\\WHITE8X8",
    edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
    tile = false, edgeSize = 14,
    insets = { left = 4, right = 4, top = 4, bottom = 4 },
})
statFly:SetBackdropColor(0.03, 0.03, 0.05, 0.97) -- solid: the panes underneath must not show through
-- and solid to the MOUSE as well, which is a separate thing. A frame that does
-- not take mouse input passes it to whatever is under it however opaque it is
-- drawn, so the ability rows behind this panel were still lighting up and
-- showing their tooltips through it. Every other flyout here does this; this
-- one was missed.
statFly:EnableMouse(true)
statFly:Hide()

-- The page: a heading, a banner with the points left to place, then a card
-- per stat. A card is the stat's icon, its name and live total with what that
-- total is doing, and on the right the points placed in it with - and +.
statFly.close = CreateFrame("Button", nil, statFly, "UIPanelCloseButton")
statFly.close:SetPoint("TOPRIGHT", -6, -6)
statFly.close:SetScript("OnClick", function() statFly:Hide() end)
statFly.header = statFly:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
statFly.header:SetPoint("TOP", 0, -16)
statFly.header:SetText("Primary Stats")

CW.CARD_BACKDROP = {
    bgFile = "Interface\\Tooltips\\UI-Tooltip-Background",
    edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
    tile = true, tileSize = 16, edgeSize = 14,
    insets = { left = 3, right = 3, top = 3, bottom = 3 },
}
statFly.banner = CreateFrame("Frame", nil, statFly)
statFly.banner:SetWidth(380); statFly.banner:SetHeight(58)
statFly.banner:SetPoint("TOP", 0, -42)
statFly.banner:SetBackdrop(CW.CARD_BACKDROP)
statFly.banner:SetBackdropColor(0.1, 0.08, 0.02, 0.9)
statFly.banner:SetBackdropBorderColor(0.8, 0.65, 0.2)
-- Both lines belong to the banner. A child frame draws over every layer of
-- its parent, text included, so on the page they sat UNDER the banner's fill
-- and came out dim and muddy.
local statTitle = statFly.banner:CreateFontString(nil, "OVERLAY", "GameFontNormalHuge")
CW.statTitle = statTitle
statTitle:SetTextColor(1, 1, 1)      -- white, so the green count stands out
statTitle:SetPoint("CENTER", statFly.banner, "CENTER", 0, 7)
statFly.bannerSub = statFly.banner:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
statFly.bannerSub:SetPoint("TOP", statTitle, "BOTTOM", 0, -3)
statFly.bannerSub:SetTextColor(0.75, 0.75, 0.75)
statFly.bannerSub:SetText("points to place")
statFly.hint = statFly:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
statFly.hint:SetPoint("TOP", statFly.banner, "BOTTOM", 0, -8)
statFly.hint:SetWidth(700)
statFly.hint:SetTextColor(0.65, 0.65, 0.65)
statFly.hint:SetText("Points arrive every level, and moving them is free at any time. Hover a stat for everything it does for you.")

local statRows = {}
CW.statRows = statRows
CW.STAT_ICONS = { "Spell_Nature_Strength", "Spell_Holy_BlessingOfAgility", "Spell_Holy_WordFortitude",
                  "Spell_Holy_MagicalSentry", "Spell_Holy_DivineSpirit" }
for i = 1, 5 do
    local r = CreateFrame("Frame", nil, statFly)
    r:SetWidth(820); r:SetHeight(70)
    r:SetPoint("TOP", 0, -130 - (i - 1) * 78)
    r:SetBackdrop(CW.CARD_BACKDROP)
    r:SetBackdropColor(0.07, 0.07, 0.1, 0.9)
    r:SetBackdropBorderColor(0.4, 0.4, 0.45)

    r.icon = r:CreateTexture(nil, "ARTWORK")
    r.icon:SetWidth(42); r.icon:SetHeight(42)
    r.icon:SetPoint("LEFT", 18, 0)
    r.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    r.icon:SetTexture("Interface\\Icons\\" .. CW.STAT_ICONS[i])
    r.iconBorder = r:CreateTexture(nil, "OVERLAY")
    r.iconBorder:SetWidth(71); r.iconBorder:SetHeight(71)
    r.iconBorder:SetPoint("CENTER", r.icon, "CENTER", 0, 0)
    r.iconBorder:SetTexture("Interface\\Buttons\\UI-Quickslot2")

    -- line 1: the stat, its live total, the Rebirth share, what Apply makes it
    r.label = r:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    r.label:SetPoint("TOPLEFT", 78, -14)
    r.label:SetWidth(570)
    r.label:SetJustifyH("LEFT")
    -- line 2: everything that total is worth, from the realm's own rates
    r.sub = r:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    r.sub:SetPoint("TOPLEFT", 78, -40)
    r.sub:SetWidth(580)
    r.sub:SetJustifyH("LEFT")

    -- the points placed here, between - and +
    r.plus = CreateFrame("Button", nil, r, "UIPanelButtonTemplate")
    r.plus:SetWidth(30); r.plus:SetHeight(26)
    r.plus:SetPoint("RIGHT", -18, 0)
    r.plus:SetText("+")
    r.count = r:CreateFontString(nil, "OVERLAY", "GameFontHighlightLarge")
    r.count:SetPoint("CENTER", r, "RIGHT", -80, 6)
    r.countLabel = r:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    r.countLabel:SetPoint("CENTER", r, "RIGHT", -80, -12)
    r.countLabel:SetText("points")
    r.minus = CreateFrame("Button", nil, r, "UIPanelButtonTemplate")
    r.minus:SetWidth(30); r.minus:SetHeight(26)
    r.minus:SetPoint("RIGHT", -112, 0)
    r.minus:SetText("-")
    statRows[i] = r
end
-- the client drops textures it loaded before a cinematic: set them on show
statFly:HookScript("OnShow", function()
    for i, r in ipairs(statRows) do
        r.icon:SetTexture(nil)
        r.icon:SetTexture("Interface\\Icons\\" .. CW.STAT_ICONS[i])
    end
end)

local statApply = CreateFrame("Button", nil, statFly, "UIPanelButtonTemplate")
statApply:SetWidth(150); statApply:SetHeight(24)
statApply:SetPoint("BOTTOM", -82, 20)
statApply:SetText("Apply")
CW.statApply = statApply

local statReset = CreateFrame("Button", nil, statFly, "UIPanelButtonTemplate")
statReset:SetWidth(150); statReset:SetHeight(24)
statReset:SetPoint("BOTTOM", 82, 20)
statReset:SetText("Reset edits")
CW.statReset = statReset

-- archetype flyout ----------------------------------------------------------
-- The same starter builds the Hero Advancement NPC lists, applied with one
-- click. Classless only: the server refuses ARCHAPPLY on any other path, and
-- UpdateStatus hides the button and this panel outside that mode.
local archFly = CreateFrame("Frame", "ClasslessWildcardArchetypes", frame)
archFly:SetWidth(frame:GetWidth()); archFly:SetHeight(frame:GetHeight())
archFly:SetPoint("CENTER", frame, "CENTER", 0, 0)
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
archFly.close = CreateFrame("Button", nil, archFly, "UIPanelCloseButton")
archFly.close:SetPoint("TOPRIGHT", -6, -6)
archFly.close:SetScript("OnClick", function() archFly:Hide() end)

-- Laid out like the panel's other cards: an icon and a large title, then
-- three short labelled lines in place of a paragraph, then the builds.
archFly.icon = archFly:CreateTexture(nil, "ARTWORK")
archFly.icon:SetWidth(32); archFly.icon:SetHeight(32)
archFly.icon:SetPoint("TOPLEFT", 18, -16)
archFly.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
archFly.icon:SetTexture("Interface\\Icons\\INV_Misc_Book_11")
archFly.iconBorder = archFly:CreateTexture(nil, "OVERLAY")
archFly.iconBorder:SetWidth(54); archFly.iconBorder:SetHeight(54)
archFly.iconBorder:SetPoint("CENTER", archFly.icon, "CENTER", 0, 0)
archFly.iconBorder:SetTexture("Interface\\Buttons\\UI-Quickslot2")
archFly.title = archFly:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
archFly.title:SetPoint("TOPLEFT", archFly.icon, "TOPRIGHT", 12, -1)
archFly.title:SetText("Archetypes")
archFly.subtitle = archFly:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
archFly.subtitle:SetPoint("TOPLEFT", archFly.title, "BOTTOMLEFT", 0, -4)
archFly.subtitle:SetText("A build that is bought for you as you level.")

function archFly.IntroText()
    return "|cffffd100Follow:|r its abilities and talents are bought for you, in order, as each becomes available, "
        .. "from level 1 to " .. (CW.rules.maxLevel or 80) .. ".\n"
        .. "|cffffd100Switch:|r your current abilities are unlearned and refunded, and your talents are reset.\n"
        .. "|cffffd100Stop:|r at any time. What you own stays.\n"
        .. "|cffffd100Build:|r see every step and the level it is bought at before you choose."
end
archFly.INTRO = archFly.IntroText()
archFly.intro = archFly:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
archFly.intro:SetPoint("TOPLEFT", 18, -62)
archFly.intro:SetWidth(900)
archFly.intro:SetJustifyH("LEFT")
archFly.intro:SetTextColor(0.8, 0.8, 0.8)
archFly.intro:SetText(archFly.INTRO)

-- One archetype row: the name on the first line, the description under it
-- (it may wrap), the ability and talent counts on a line of their own, and a
-- button on the right. Rows are stacked from their measured text heights by
-- FillArchRows, so nothing overlaps whatever the text wraps to. The panel
-- flyout and the first-login wizard both use these.
-- Each row sits on a faint stripe with 8px of padding, its text column
-- clear of two buttons on the right: Build (the build order, in its own
-- window) and the row's action.
local ARCH_ROW_H = 46
local function MakeArchRow(parent, width, buttonText)
    local r = CreateFrame("Frame", nil, parent)
    r:SetWidth(width); r:SetHeight(ARCH_ROW_H)
    r.stripe = r:CreateTexture(nil, "BACKGROUND")
    r.stripe:SetAllPoints(r)
    r.stripe:SetTexture("Interface\\Buttons\\WHITE8X8")
    r.stripe:SetVertexColor(1, 1, 1, 0.05)
    local textW = width - 170
    r.name = r:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    r.name:SetPoint("TOPLEFT", 8, -6)
    r.name:SetWidth(textW)
    r.name:SetJustifyH("LEFT")
    r.desc = r:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    r.desc:SetPoint("TOPLEFT", 8, -23)
    r.desc:SetWidth(textW)
    r.desc:SetJustifyH("LEFT")
    r.desc:SetJustifyV("TOP")
    r.counts = r:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    r.counts:SetPoint("TOPLEFT", r.desc, "BOTTOMLEFT", 0, -3)
    r.counts:SetWidth(textW)
    r.counts:SetJustifyH("LEFT")
    r.apply = CreateFrame("Button", nil, r, "UIPanelButtonTemplate")
    r.apply:SetWidth(72); r.apply:SetHeight(22)
    r.apply:SetPoint("RIGHT", -8, 0)
    r.apply:SetText(buttonText)
    r.apply.defaultText = buttonText
    r.view = CreateFrame("Button", nil, r, "UIPanelButtonTemplate")
    r.view:SetWidth(72); r.view:SetHeight(22)
    r.view:SetPoint("RIGHT", r.apply, "LEFT", -6, 0)
    r.view:SetText("Build")
    r.view:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:AddLine("Build order")
        GameTooltip:AddLine("Every ability and talent this archetype buys, in order, with the level each is bought at.",
            1, 1, 1, true)
        GameTooltip:Show()
    end)
    r.view:SetScript("OnLeave", function() GameTooltip:Hide() end)
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
    -- where the list is scrolled to, kept for the next time it is drawn
    L.scroll:HookScript("OnVerticalScroll", function(_, offset) L.at = offset end)
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
-- `key` names the list being shown: drawn again with the same key, the list
-- keeps its place (a build deleted, or the editor closed); a new key starts
-- at the top.
local function FillArchRows(L, list, onChoose, x, top, key)
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
            r.name:SetText("|cffffd100" .. arch.name .. "|r" .. (arch.following and "  |cff00ff00Following|r" or ""))
            r.desc:SetText(arch.desc)
            r.counts:SetText("|cff999999" .. count .. "|r")
            r.apply:SetText(arch.following and "Stop" or r.apply.defaultText)
            r.apply:SetScript("OnClick", function() onChoose(arch) end)
            r.view:SetScript("OnClick", function() if CW.OpenArchPlan then CW.OpenArchPlan(arch) end end)
            -- the row being followed is picked out in gold, the rest alternate
            if arch.following then
                r.stripe:SetVertexColor(1, 0.82, 0.3, 0.12)
            else
                r.stripe:SetVertexColor(1, 1, 1, i % 2 == 0 and 0.03 or 0.06)
            end
            local h = 23 + TextHeight(r.desc) + 3 + 12 + 8
            if CW.DecorateBuildRow then h = h + CW.DecorateBuildRow(r, arch) end
            r:ClearAllPoints()
            r:SetPoint("TOPLEFT", 0, -y)
            r:SetHeight(h)
            r:Show()
            y = y + h + 4   -- a 4px gap between rows
        else
            r:Hide()
        end
    end
    if #list > 0 then y = y - 4 end   -- and none after the last
    local visible = math.min(y, L.maxH or ARCH_LIST_MAX_H)
    L.child:SetHeight(math.max(y, 1))
    L.scroll:ClearAllPoints()
    L.scroll:SetPoint("TOPLEFT", x, -top)
    L.scroll:SetHeight(math.max(visible, ARCH_ROW_H))
    L.scroll:UpdateScrollChildRect()
    -- the place it was at, short of the end of a list that may have shrunk;
    -- the bar's range is set first, or it would clamp the place to the old one
    local range = math.max(0, y - math.max(visible, ARCH_ROW_H))
    local at = (key ~= nil and key == L.key) and math.min(L.at or 0, range) or 0
    L.key = key
    local bar = _G[(L.scroll:GetName() or "") .. "ScrollBar"]
    if bar then bar:SetMinMaxValues(0, range) end
    L.scroll:SetVerticalScroll(at)
    L.scroll:Show()
    return #list, visible
end

archFly.list = MakeArchList(archFly, "ClasslessWildcardArchetypeList", 914, "Follow")
archFly.rows = archFly.list.rows

-- Fills the flyout from CW.archetypes (cached from the last AR/ARE reply):
-- the intro text first, the rows stacked under whatever height it wrapped
-- to, and the panel sized to the lot.
local function RenderArchFly()
    -- the My Builds tab is drawn by its own block further down
    if CW.archTab == "MINE" and CW.RenderMyBuilds then
        CW.RenderMyBuilds()
        return
    end
    if CW.ArchTabsRefresh then CW.ArchTabsRefresh() end
    if CW.HideMyBuildsBar then CW.HideMyBuildsBar() end
    if archFly.empty then archFly.empty:Hide() end
    local list = CW.archetypes or {}
    archFly.INTRO = archFly.IntroText()   -- the cap is the realm's, read fresh
    if #list > 0 then
        archFly.intro:SetText(archFly.INTRO)
    elseif CW.archetypesLoaded then
        archFly.intro:SetText("No archetypes are available.")
    else
        archFly.intro:SetText("Loading...")
    end
    local top = 62 + TextHeight(archFly.intro) + 14
    -- the list takes whatever the page has left under the header
    archFly.list.maxH = archFly:GetHeight() - top - 24
    local shown, used = FillArchRows(archFly.list, list, function(arch)
        archFly:Hide()
        if arch.following then
            Send("ARCHAPPLY 0")   -- stop following: nothing is lost
        else
            local dlg = StaticPopup_Show("CW_CLASSLESS_ARCHETYPE", arch.name)
            if dlg then dlg.data = arch.id end
        end
    end, 18, top, "STARTER")
end
CW.RenderArchFly = RenderArchFly
-- the flyout's own list, filled from any list of rows (My Builds uses it)
function CW.FillArchRowsFor(list, onChoose, top, key)
    archFly.list.maxH = archFly:GetHeight() - top - 24
    return FillArchRows(archFly.list, list, onChoose, 18, top, key)
end

-- Share codes ---------------------------------------------------------------
-- A custom build as a string that survives chat, forums and Discord:
-- "CWA1:" and URL-safe base64 (A-Z a-z 0-9 - _, no padding) of
--   version (1) | name length, name | description length, description |
--   ability count, ability ids as zigzag deltas | talent count,
--   (talent id, rank) pairs | CRC-16 of all of it
-- Version 2 is the same with one byte more after each ability id and each
-- talent rank: the level the build holds it back to (0 = none). A build
-- that holds nothing back still writes version 1, so its code is unchanged.
-- with every count and id a varint. Plain arithmetic throughout: no bit
-- library is needed, so it runs the same in any 5.1.
do
    local B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    local B64INV = {}
    for i = 1, 64 do B64INV[B64:sub(i, i)] = i - 1 end
    local PREFIX, VERSION, MAX_ENTRIES, NAME_MAX, DESC_MAX = "CWA1:", 2, 200, 32, 120

    local function xor(a, b)
        local r, p = 0, 1
        while a > 0 or b > 0 do
            local x, y = a % 2, b % 2
            if x ~= y then r = r + p end
            a, b, p = (a - x) / 2, (b - y) / 2, p * 2
        end
        return r
    end

    -- CRC-16/CCITT-FALSE: polynomial 0x1021, starting at 0xFFFF
    local function crc16(bytes, n)
        local crc = 65535
        for i = 1, n do
            crc = xor(crc, bytes[i] * 256)
            for _ = 1, 8 do
                if crc >= 32768 then
                    crc = xor((crc * 2) % 65536, 4129)
                else
                    crc = (crc * 2) % 65536
                end
            end
        end
        return crc
    end

    local function putVarint(out, n)
        while n >= 128 do
            out[#out + 1] = n % 128 + 128
            n = math.floor(n / 128)
        end
        out[#out + 1] = n
    end

    local function putText(out, s, max)
        s = s:sub(1, max)
        out[#out + 1] = #s
        for i = 1, #s do out[#out + 1] = s:byte(i) end
    end

    -- the build's name and description as they may be stored: no client
    -- escape code or separators, trimmed, capped without splitting a character
    -- `loose` keeps punctuation (a description); a name also loses the
    -- separators the server's messages are split on
    function CW.CleanBuildText(s, max, loose)
        s = (s or ""):gsub(loose and "[%c|]" or "[%c|;:,]", ""):gsub("^%s+", ""):gsub("%s+$", "")
        if #s > max then
            s = s:sub(1, max)
            while #s > 0 and s:byte(#s) >= 128 and s:byte(#s) < 192 do s = s:sub(1, -2) end
            if #s > 0 and s:byte(#s) >= 192 then s = s:sub(1, -2) end
        end
        return s
    end

    function CW.EncodeBuild(build)
        local waitA, waitT = build.waitA or {}, build.waitT or {}
        local held = next(waitA) ~= nil or next(waitT) ~= nil
        local out = { held and 2 or 1 }
        putText(out, CW.CleanBuildText(build.name, NAME_MAX), NAME_MAX)
        putText(out, CW.CleanBuildText(build.desc, DESC_MAX, true), DESC_MAX)
        putVarint(out, #build.abilities)
        local prev = 0
        for _, id in ipairs(build.abilities) do
            local d = id - prev
            putVarint(out, d >= 0 and d * 2 or -d * 2 - 1)
            if held then out[#out + 1] = math.min(waitA[id] or 0, 255) end
            prev = id
        end
        putVarint(out, #build.talents)
        for _, t in ipairs(build.talents) do
            putVarint(out, t[1])
            out[#out + 1] = t[2]
            if held then out[#out + 1] = math.min(waitT[t[1] .. ":" .. t[2]] or waitT[t[1]] or 0, 255) end
        end
        local crc = crc16(out, #out)
        out[#out + 1] = math.floor(crc / 256)
        out[#out + 1] = crc % 256
        local chars, n = {}, #out
        for i = 1, n, 3 do
            local a, b, c = out[i], out[i + 1] or 0, out[i + 2] or 0
            local v = a * 65536 + b * 256 + c
            local left = n - i + 1
            chars[#chars + 1] = B64:sub(math.floor(v / 262144) + 1, math.floor(v / 262144) + 1)
            local k2 = math.floor(v / 4096) % 64
            chars[#chars + 1] = B64:sub(k2 + 1, k2 + 1)
            if left > 1 then
                local k3 = math.floor(v / 64) % 64
                chars[#chars + 1] = B64:sub(k3 + 1, k3 + 1)
            end
            if left > 2 then
                local k4 = v % 64
                chars[#chars + 1] = B64:sub(k4 + 1, k4 + 1)
            end
        end
        return PREFIX .. table.concat(chars)
    end

    -- the build, or nil and why not
    function CW.DecodeBuild(code)
        code = (code or ""):gsub("%s", "")
        if code:sub(1, #PREFIX) ~= PREFIX then
            return nil, "That is not a build code. Build codes start with " .. PREFIX
        end
        code = code:sub(#PREFIX + 1)
        if #code % 4 == 1 then return nil, "The code is incomplete. Copy all of it." end
        local bytes = {}
        for i = 1, #code, 4 do
            local v, got = 0, 0
            for j = 0, 3 do
                local ch = code:sub(i + j, i + j)
                if ch ~= "" then
                    local k = B64INV[ch]
                    if not k then return nil, "The code has a character it should not." end
                    v = v * 64 + k
                    got = got + 1
                else
                    v = v * 64
                end
            end
            -- a short last group's spare bits are zero, so a build has one code
            if (got == 2 and math.floor(v / 4096) % 16 ~= 0) or (got == 3 and math.floor(v / 64) % 4 ~= 0) then
                return nil, "The code is damaged or incomplete. Copy all of it."
            end
            bytes[#bytes + 1] = math.floor(v / 65536) % 256
            if got > 2 then bytes[#bytes + 1] = math.floor(v / 256) % 256 end
            if got > 3 then bytes[#bytes + 1] = v % 256 end
        end
        local n = #bytes
        if n < 3 then return nil, "The code is incomplete. Copy all of it." end
        if crc16(bytes, n - 2) ~= bytes[n - 1] * 256 + bytes[n] then
            return nil, "The code is damaged or incomplete. Copy all of it."
        end
        local pos, last = 1, n - 2
        local function byte()
            if pos > last then error("short", 0) end
            pos = pos + 1
            return bytes[pos - 1]
        end
        local function varint()
            local v, mul = 0, 1
            for _ = 1, 5 do
                local b = byte()
                v = v + (b % 128) * mul
                if b < 128 then return v end
                mul = mul * 128
            end
            error("long", 0)
        end
        local function text(max)
            local len = byte()
            if len > max then error("text", 0) end
            local t = {}
            for i = 1, len do t[i] = string.char(byte()) end
            return table.concat(t)
        end
        local ok, build = pcall(function()
            local version = byte()
            if version < 1 or version > VERSION then error("version", 0) end
            local held = version >= 2
            local b = { abilities = {}, talents = {}, waitA = {}, waitT = {} }
            b.name = text(NAME_MAX)
            b.desc = text(DESC_MAX)
            local na = varint()
            if na > MAX_ENTRIES then error("count", 0) end
            local prev = 0
            for i = 1, na do
                local z = varint()
                prev = prev + ((z % 2 == 0) and z / 2 or -(z + 1) / 2)
                b.abilities[i] = prev
                if held then
                    local w = byte()
                    if w > 0 then b.waitA[prev] = w end
                end
            end
            local nt = varint()
            if nt > MAX_ENTRIES then error("count", 0) end
            for i = 1, nt do
                local id = varint()
                b.talents[i] = { id, byte() }
                if held then
                    local w = byte()
                    if w > 0 then b.waitT[id .. ":" .. b.talents[i][2]] = w end
                end
            end
            if pos <= last then error("trailing", 0) end
            return b
        end)
        if not ok then
            return nil, build == "version" and "That build code is from a newer version of the addon."
                or "The code is damaged or incomplete. Copy all of it."
        end
        build.name = CW.CleanBuildText(build.name, NAME_MAX)
        build.desc = CW.CleanBuildText(build.desc, DESC_MAX, true)
        return build
    end

    -- The server takes a build as plain ids in pieces, and checks every one.
    function CW.UploadBuild(build)
        Send("ARCHUP CLEAR")
        local piece = {}
        local function flush(kind)
            if #piece > 0 then Send("ARCHUP " .. kind .. " " .. table.concat(piece, ",")) end
            piece = {}
        end
        -- "id@level" when the build holds it back to a level
        local waitA, waitT = build.waitA or {}, build.waitT or {}
        for _, id in ipairs(build.abilities) do
            piece[#piece + 1] = id .. (waitA[id] and ("@" .. waitA[id]) or "")
            if #piece >= 16 then flush("A") end
        end
        flush("A")
        for _, t in ipairs(build.talents) do
            local w = waitT[t[1] .. ":" .. t[2]] or waitT[t[1]]
            piece[#piece + 1] = t[1] .. ":" .. t[2] .. (w and ("@" .. w) or "")
            if #piece >= 14 then flush("T") end
        end
        flush("T")
    end

    -- The saved builds: account-wide, in the addon's saved variables.
    function CW.SavedBuilds()
        ClasslessWildcardDB = ClasslessWildcardDB or {}
        ClasslessWildcardDB.customBuilds = ClasslessWildcardDB.customBuilds or {}
        return ClasslessWildcardDB.customBuilds
    end

    function CW.CopyBuild(b)
        local c = { name = b.name, desc = b.desc or "", abilities = {}, talents = {}, waitA = {}, waitT = {} }
        for i, id in ipairs(b.abilities or {}) do c.abilities[i] = id end
        for i, t in ipairs(b.talents or {}) do c.talents[i] = { t[1], t[2] } end
        for id, lv in pairs(b.waitA or {}) do c.waitA[id] = lv end
        for id, lv in pairs(b.waitT or {}) do c.waitT[id] = lv end
        return c
    end
end

-- Build order --------------------------------------------------------------
-- One archetype's whole build, in the order following it buys things, with
-- the level each is bought at on this character (the server simulates the
-- essence schedule: ARCHPLAN -> APA/APT pieces -> APE). Abilities, then
-- talents, in one scrolling list; every row shows the spell's own tooltip on
-- hover. Opened from a row's Build button, over the archetype list.
do
    local W, H, PAD, ROW_H = 420, 500, 18, 22
    local P = CreateFrame("Frame", "ClasslessWildcardArchPlan", frame)
    P:SetWidth(W); P:SetHeight(H)
    P:SetPoint("CENTER", frame, "CENTER", 0, 0)
    P:SetFrameStrata("DIALOG")
    P:SetToplevel(true)
    P:SetBackdrop({
        bgFile = "Interface\\Buttons\\WHITE8X8",
        edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
        tile = false, edgeSize = 14,
        insets = { left = 4, right = 4, top = 4, bottom = 4 },
    })
    P:SetBackdropColor(0.03, 0.03, 0.05, 0.98)
    P:EnableMouse(true)
    P:Hide()
    CW.archPlan = P

    P.close = CreateFrame("Button", nil, P, "UIPanelCloseButton")
    P.close:SetPoint("TOPRIGHT", -2, -2)
    P.close:SetScript("OnClick", function() P:Hide() end)
    P.icon = P:CreateTexture(nil, "ARTWORK")
    P.icon:SetWidth(32); P.icon:SetHeight(32)
    P.icon:SetPoint("TOPLEFT", PAD, -16)
    P.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    P.icon:SetTexture("Interface\\Icons\\INV_Misc_Book_11")
    P.iconBorder = P:CreateTexture(nil, "OVERLAY")
    P.iconBorder:SetWidth(54); P.iconBorder:SetHeight(54)
    P.iconBorder:SetPoint("CENTER", P.icon, "CENTER", 0, 0)
    P.iconBorder:SetTexture("Interface\\Buttons\\UI-Quickslot2")
    P.title = P:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    P.title:SetPoint("TOPLEFT", P.icon, "TOPRIGHT", 12, -1)
    P.title:SetPoint("RIGHT", P, "RIGHT", -32, 0)
    P.title:SetJustifyH("LEFT")
    P.subtitle = P:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    P.subtitle:SetPoint("TOPLEFT", P.title, "BOTTOMLEFT", 0, -4)
    P.subtitle:SetText("Build order")
    P.note = P:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    P.note:SetPoint("TOPLEFT", PAD, -60)
    P.note:SetWidth(W - 2 * PAD)
    P.note:SetJustifyH("LEFT")
    P.note:SetTextColor(0.75, 0.75, 0.75)
    P.note:SetText("Bought in this order as you level. The level is when each is bought, "
        .. "from the Ability and Talent Essence you earn. Hover any row for its tooltip.")

    P.scroll = CreateFrame("ScrollFrame", "ClasslessWildcardArchPlanScroll", P, "UIPanelScrollFrameTemplate")
    P.scroll:SetPoint("TOPLEFT", PAD, -94)
    P.scroll:SetPoint("BOTTOMRIGHT", -PAD - 22, 46)
    P.scroll.scrollBarHideable = 1
    P.child = CreateFrame("Frame", nil, P.scroll)
    P.child:SetWidth(W - 2 * PAD - 22); P.child:SetHeight(1)
    P.scroll:SetScrollChild(P.child)
    local CHILD_W = W - 2 * PAD - 22

    P.loading = P:CreateFontString(nil, "OVERLAY", "GameFontDisable")
    P.loading:SetPoint("TOPLEFT", PAD + 4, -100)
    P.loading:SetText("Loading...")

    P.follow = CreateFrame("Button", nil, P, "UIPanelButtonTemplate")
    P.follow:SetWidth(110); P.follow:SetHeight(22)
    P.follow:SetPoint("BOTTOMLEFT", PAD, 14)
    P.follow:SetText("Follow")
    P.done = CreateFrame("Button", nil, P, "UIPanelButtonTemplate")
    P.done:SetWidth(100); P.done:SetHeight(22)
    P.done:SetPoint("BOTTOMRIGHT", -PAD, 14)
    P.done:SetText(CLOSE or "Close")
    P.done:SetScript("OnClick", function() P:Hide() end)
    -- a starter build as the start of one of your own
    P.copy = CreateFrame("Button", nil, P, "UIPanelButtonTemplate")
    P.copy:SetWidth(140); P.copy:SetHeight(22)
    P.copy:SetPoint("BOTTOM", P, "BOTTOM", 0, 14)
    P.copy:SetText("Copy to My Builds")
    P.copy:SetScript("OnClick", function()
        local d = P.data
        if not d or not d.done or not CW.OpenBuildEditor then return end
        -- every entry at the level the archetype buys it at, held there when
        -- that is later than the level it becomes available at
        local b = { name = (P.arch and P.arch.name or "Build") .. " (copy)", desc = P.arch and P.arch.desc or "",
                    abilities = {}, talents = {}, waitA = {}, waitT = {} }
        CW.abilityInfo = CW.abilityInfo or {}
        CW.talentInfo = CW.talentInfo or {}
        for _, s in ipairs(d.abilities) do
            tinsert(b.abilities, s.spell)
            local unlock = s.unlock or 1
            if (s.level or 0) > unlock then b.waitA[s.spell] = s.level end
            local info = CW.abilityInfo[s.spell] or {}
            info.unlock, info.cost = unlock, s.cost or info.cost
            CW.abilityInfo[s.spell] = info
        end
        for _, s in ipairs(d.talents) do
            if s.talentId then
                tinsert(b.talents, { s.talentId, s.rank })
                local tier = s.tier or 10
                if (s.level or 0) > tier then b.waitT[s.talentId .. ":" .. s.rank] = s.level end
                CW.talentInfo[s.talentId] = { spell = s.spell, rarity = s.rarity, max = s.maxRank, tier = tier }
            end
        end
        P:Hide()
        CW.OpenBuildEditor(b, nil)
    end)

    -- pooled pieces of the list
    P.headers, P.rows = {}, {}
    local function Header(i)
        local h = P.headers[i]
        if not h then
            h = { text = P.child:CreateFontString(nil, "OVERLAY", "GameFontNormal"),
                  rule = P.child:CreateTexture(nil, "ARTWORK") }
            h.text:SetJustifyH("LEFT")
            h.rule:SetHeight(1)
            h.rule:SetTexture(1, 0.82, 0, 0.25)
            P.headers[i] = h
        end
        return h
    end
    local function Row(i)
        local r = P.rows[i]
        if not r then
            r = CreateFrame("Button", nil, P.child)
            r:SetWidth(CHILD_W); r:SetHeight(ROW_H)
            r.stripe = r:CreateTexture(nil, "BACKGROUND")
            r.stripe:SetAllPoints(r)
            r.stripe:SetTexture("Interface\\Buttons\\WHITE8X8")
            r.level = r:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
            r.level:SetPoint("LEFT", 4, 0)
            r.level:SetWidth(40)
            r.level:SetJustifyH("LEFT")
            r.icon = r:CreateTexture(nil, "ARTWORK")
            r.icon:SetWidth(18); r.icon:SetHeight(18)
            r.icon:SetPoint("LEFT", 48, 0)
            r.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
            r.name = r:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
            r.name:SetPoint("LEFT", r.icon, "RIGHT", 8, 0)
            r.name:SetPoint("RIGHT", -44, 0)
            r.name:SetJustifyH("LEFT")
            r.rank = r:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
            r.rank:SetPoint("RIGHT", -6, 0)
            r.rank:SetJustifyH("RIGHT")
            r:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight", "ADD")
            r:SetScript("OnEnter", function(self)
                if not self.spellId then return end
                GameTooltip:Hide()   -- the same link on a shown tooltip toggles it off
                GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
                GameTooltip:SetHyperlink("spell:" .. self.spellId)
                GameTooltip:Show()
            end)
            r:SetScript("OnLeave", function() GameTooltip:Hide() end)
            P.rows[i] = r
        end
        return r
    end

    function CW.RenderArchPlan()
        local d = P.data
        for _, h in ipairs(P.headers) do h.text:Hide(); h.rule:Hide() end
        for _, r in ipairs(P.rows) do r:Hide() end
        if not d or not d.done then
            P.loading:Show()
            return
        end
        P.loading:Hide()
        local y, nh, nr = 0, 0, 0
        local function Section(label, steps, talents)
            nh = nh + 1
            local h = Header(nh)
            h.text:ClearAllPoints()
            h.text:SetPoint("TOPLEFT", P.child, "TOPLEFT", 0, -y)
            h.text:SetText(label)
            h.rule:ClearAllPoints()
            h.rule:SetPoint("TOPLEFT", P.child, "TOPLEFT", 0, -y - 16)
            h.rule:SetPoint("TOPRIGHT", P.child, "TOPRIGHT", 0, -y - 16)
            h.text:Show(); h.rule:Show()
            y = y + 22
            for i, s in ipairs(steps) do
                nr = nr + 1
                local r = Row(nr)
                r.spellId = s.spell
                r:ClearAllPoints()
                r:SetPoint("TOPLEFT", P.child, "TOPLEFT", 0, -y)
                r.stripe:SetVertexColor(1, 1, 1, i % 2 == 0 and 0.03 or 0.06)
                -- 0: the essence never reaches it before the cap
                r.level:SetText(s.level > 0 and ("Lv " .. s.level)
                    or ("|cff888888" .. (CW.rules.maxLevel or 80) .. "+|r"))
                r.icon:SetTexture(SpellIcon(s.spell))
                r.name:SetText(SpellLabel(s.spell, s.rarity))
                r.rank:SetText(talents and ("|cffaaaaaa" .. s.rank .. "/" .. s.maxRank .. "|r") or "")
                r:Show()
                y = y + ROW_H
            end
            y = y + 12
        end
        local ranks = 0
        for _, s in ipairs(d.talents) do ranks = ranks + s.rank end
        Section("Abilities  |cffaaaaaa" .. #d.abilities .. "|r", d.abilities, false)
        if #d.talents > 0 then
            Section("Talents  |cffaaaaaa" .. ranks .. " ranks|r", d.talents, true)
        end
        P.child:SetHeight(math.max(y, 1))
        P.scroll:SetVerticalScroll(0)
        P.scroll:UpdateScrollChildRect()
    end

    -- arch.build marks one of the player's own builds: the server has not got
    -- it, so it is uploaded and previewed (id 0) rather than looked up by id
    function CW.OpenArchPlan(arch)
        P.arch = arch
        P.data = { id = arch.build and 0 or arch.id, abilities = {}, talents = {} }
        P.title:SetText(arch.name)
        P.follow:SetText(arch.following and "Stop" or "Follow")
        P.follow:SetScript("OnClick", function()
            P:Hide()
            if CW.archFly then CW.archFly:Hide() end
            if arch.following then
                Send("ARCHAPPLY 0")
            elseif arch.build then
                CW.FollowBuild(arch.build)
            else
                local dlg = StaticPopup_Show("CW_CLASSLESS_ARCHETYPE", arch.name)
                if dlg then dlg.data = arch.id end
            end
        end)
        -- the follow button belongs to the panel's flyout; the first-login
        -- wizard chooses with its own buttons, so it is hidden there
        if CW.archFly and CW.archFly:IsShown() then P.follow:Show() else P.follow:Hide() end
        -- copying is for starter builds on the Classless path; a saved build is edited instead
        if not arch.build and CW.state.mode == 0 then P.copy:Show() else P.copy:Hide() end
        -- the window lives on whichever host opened it: the first-login wizard
        -- is up with the panel closed and sits a strata higher, so a window
        -- left on the panel would be hidden with it
        local wizard = _G.ClasslessWildcardWizard
        local host = (wizard and wizard:IsShown()) and wizard or frame
        local over = (host == wizard) and wizard or CW.archFly
        P:SetParent(host)
        P:ClearAllPoints()
        P:SetPoint("CENTER", host, "CENTER", 0, 0)
        P:SetFrameStrata(host == wizard and "FULLSCREEN_DIALOG" or "DIALOG")
        P:SetFrameLevel((over and over:GetFrameLevel() or 0) + 20)
        CW.RenderArchPlan()
        P:Show()
        if arch.build then
            CW.planTarget = "plan"
            CW.UploadBuild(arch.build)
            Send("ARCHPLANX " .. CW.CleanBuildText(arch.build.name, 32))
        else
            Send("ARCHPLAN " .. arch.id)
        end
    end

    -- "APA|id|spell:rarity:level;..." and "APT|id|spell:rarity:rank:max:level:talentId;..."
    -- pieces arrive in order; APE|id|spentA|totalA|spentT|totalT|problem draws
    -- the lot. A preview (id 0) is the editor's when the editor asked for it.
    function CW.ReadArchPlan(kind, p)
        if tonumber(p[2]) == 0 and CW.planTarget == "editor" and CW.EditorReadPlan then
            CW.EditorReadPlan(kind, p)
            return
        end
        local d = P.data
        if not d or tonumber(p[2]) ~= d.id then return end
        if kind == "APW" then
            return   -- row warnings are the editor's business
        elseif kind == "APA" then
            -- spell:rarity:level:unlock:free:cost
            for spell, rarity, level, unlock, _, cost in string.gmatch(p[3] or "", "(%d+):(%d+):(%d+):?(%d*):?(%d*):?(%d*);") do
                tinsert(d.abilities, { spell = tonumber(spell), rarity = tonumber(rarity), level = tonumber(level),
                                       unlock = tonumber(unlock), cost = tonumber(cost) })
            end
        elseif kind == "APT" then
            for spell, rarity, rank, max, level, tid, tier in string.gmatch(p[3] or "", "(%d+):(%d+):(%d+):(%d+):(%d+):?(%d*):?(%d*);") do
                tinsert(d.talents, { spell = tonumber(spell), rarity = tonumber(rarity), rank = tonumber(rank),
                                     maxRank = tonumber(max), level = tonumber(level), talentId = tonumber(tid),
                                     tier = tonumber(tier) })
            end
        else
            d.done = true
            if P:IsShown() then CW.RenderArchPlan() end
        end
    end
end

-- My Builds ------------------------------------------------------------------
-- The player's own archetypes: saved in the addon (account-wide, this
-- computer), moved and shared as build codes, followed exactly like a starter
-- build. The server checks every build before it is previewed or followed and
-- refuses one that does not fit the essence a Hero earns by the cap.
StaticPopupDialogs["CW_CLASSLESS_CUSTOM"] = {
    text = "Follow %s? Your abilities and talents are unlearned and refunded, then its build is bought for you as you level.",
    button1 = "Follow",
    button2 = "Cancel",
    OnAccept = function(self)
        if self.data then Send("ARCHCUSTOM " .. self.data) end
        if CW.SetTab then CW.SetTab("HERO") end
    end,
    timeout = 0, whileDead = 1, hideOnEscape = 1, preferredIndex = 3,
}
StaticPopupDialogs["CW_CLASSLESS_DELETEBUILD"] = {
    text = "Delete %s? Share it first if you want to keep a copy.",
    button1 = "Delete",
    button2 = "Cancel",
    OnAccept = function(self) if self.data and CW.DeleteBuild then CW.DeleteBuild(self.data) end end,
    timeout = 0, whileDead = 1, hideOnEscape = 1, preferredIndex = 3,
}
StaticPopupDialogs["CW_CLASSLESS_DISCARDBUILD"] = {
    text = "Close the editor? Your changes to %s are not saved.",
    button1 = "Close",
    button2 = "Keep editing",
    OnAccept = function(self) if CW.FinishBuildEditor then CW.FinishBuildEditor(self.data) end end,
    timeout = 0, whileDead = 1, hideOnEscape = 1, preferredIndex = 3,
}
StaticPopupDialogs["CW_CLASSLESS_SHAREDBUILD"] = {
    text = "%s shared a build: %s.",
    button1 = "View",
    button2 = "Ignore",
    OnAccept = function(self) if self.data and CW.OpenBuildEditor then CW.OpenBuildEditor(self.data, nil) end end,
    timeout = 0, whileDead = 1, hideOnEscape = 1, preferredIndex = 3,
}

do
    local NAME_MAX, DESC_MAX = 32, 120

    function CW.FollowBuild(build)
        CW.UploadBuild(build)
        local name = CW.CleanBuildText(build.name, NAME_MAX)
        local dlg = StaticPopup_Show("CW_CLASSLESS_CUSTOM", name)
        if dlg then dlg.data = name end
    end

    function CW.DeleteBuild(index)
        tremove(CW.SavedBuilds(), index)
        if CW.archFly and CW.archFly:IsShown() then CW.RenderArchFly() end
    end

    local function Counts(b)
        local ranks = 0
        for _, t in ipairs(b.talents) do ranks = ranks + t[2] end
        return #b.abilities, ranks
    end

    -- ---- the page switch and My Builds' bar ----------------------------------------
    -- One button, beside the title only: it names the other page. The
    -- subtitle under the title stops short of it, so the two never meet.
    local fly = CW.archFly
    CW.archTab = "STARTER"
    fly.tabMine = CreateFrame("Button", nil, fly, "UIPanelButtonTemplate")
    fly.tabMine:SetWidth(124); fly.tabMine:SetHeight(22)
    fly.tabMine:SetPoint("TOPRIGHT", -44, -17)   -- left of the close button
    fly.tabMine:SetScript("OnClick", function()
        CW.archTab = CW.archTab == "MINE" and "STARTER" or "MINE"
        CW.RenderArchFly()
    end)
    fly.subtitle:SetWidth(520 - 62 - 16 - 124 - 12)
    fly.subtitle:SetJustifyH("LEFT")

    fly.bar = CreateFrame("Frame", nil, fly)
    fly.bar:SetWidth(484); fly.bar:SetHeight(24)
    fly.bar:Hide()
    local function BarButton(text, w, x, onClick, tip)
        local b = CreateFrame("Button", nil, fly.bar, "UIPanelButtonTemplate")
        b:SetWidth(w); b:SetHeight(22)
        b:SetPoint("LEFT", x, 0)
        b:SetText(text)
        b:SetScript("OnClick", onClick)
        b:SetScript("OnEnter", function(self)
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:AddLine(text)
            GameTooltip:AddLine(tip, 1, 1, 1, true)
            GameTooltip:Show()
        end)
        b:SetScript("OnLeave", function() GameTooltip:Hide() end)
        return b
    end
    fly.bar.mine = BarButton("Save my build", 130, 0, function()
        CW.awaitMine = { abilities = {}, talents = {} }
        Send("ARCHMINE")
    end, "Your current abilities and talents as a new build, abilities in the order they unlock.")
    fly.bar.new = BarButton("New", 80, 136, function()
        CW.OpenBuildEditor({ name = "New build", desc = "", abilities = {}, talents = {} }, nil)
    end, "An empty build, opened in the My Build column. Click abilities and talents to add them.")
    fly.bar.import = BarButton("Import", 80, 222, function()
        CW.OpenShareWindow("import")
    end, "Paste a build code someone shared with you.")

    function CW.HideMyBuildsBar()
        fly.bar:Hide()
    end

    function CW.ArchTabsRefresh()
        local mine = CW.archTab == "MINE"
        fly.tabMine:SetText(mine and "Starter Builds" or "My Builds")
        fly.title:SetText(mine and "My Builds" or "Archetypes")
        fly.subtitle:SetText(mine and "Your own archetypes, saved on this computer."
            or "A build that is bought for you as you level.")
    end

    local MINE_INTRO = "|cffffd100Follow:|r a build of your own, bought for you as you level like a starter build.\n"
        .. "|cffffd100Share:|r a build travels as a code. Copy it to move a build to another computer or give it to a friend.\n"
        .. "|cffffd100Budget:|r a build must fit the Ability and Talent Essence a Hero earns by the level cap."

    -- the flyout's My Builds page: the bar, then the saved builds as rows
    function CW.RenderMyBuilds()
        CW.ArchTabsRefresh()
        local s = CW.state
        local builds = CW.SavedBuilds()
        fly.intro:SetText(MINE_INTRO)
        local top = 62 + math.max(12, fly.intro:GetStringHeight() or 0) + 12
        fly.bar:ClearAllPoints()
        fly.bar:SetPoint("TOPLEFT", 18, -top)
        fly.bar:Show()
        top = top + 24 + 12
        local list = {}
        for i, b in ipairs(builds) do
            local count, ranks = Counts(b)
            list[i] = {
                id = 0, build = b, index = i,
                name = CW.CleanBuildText(b.name, NAME_MAX), desc = b.desc ~= "" and b.desc or "No description.",
                count = count, ranks = ranks,
                following = (s.customName or "") ~= "" and s.customName == CW.CleanBuildText(b.name, NAME_MAX),
            }
        end
        if #list == 0 then
            fly.empty = fly.empty or fly:CreateFontString(nil, "OVERLAY", "GameFontDisable")
            fly.empty:ClearAllPoints()
            fly.empty:SetPoint("TOPLEFT", 26, -top - 4)
            fly.empty:SetText("No builds yet. Save your own, start a new one, or import a code.")
            fly.empty:Show()
        elseif fly.empty then
            fly.empty:Hide()
        end
        local _, used = CW.FillArchRowsFor(list, function(arch)
            fly:Hide()
            if arch.following then
                Send("ARCHAPPLY 0")
            else
                CW.FollowBuild(arch.build)
            end
        end, top, "MINE")
    end

    -- the small actions a saved build's row carries, made on first use
    function CW.DecorateBuildRow(r, arch)
        if not r.edit then
            local function Small(text, x)
                local b = CreateFrame("Button", nil, r, "UIPanelButtonTemplate")
                b:SetWidth(64); b:SetHeight(18)
                b:SetPoint("BOTTOMLEFT", x, 6)
                b:SetText(text)
                return b
            end
            r.edit, r.share, r.del = Small("Edit", 8), Small("Share", 76), Small("Delete", 144)
        end
        if arch and arch.build then
            r.edit:SetScript("OnClick", function() CW.OpenBuildEditor(arch.build, arch.index) end)
            r.share:SetScript("OnClick", function() CW.OpenShareWindow("share", arch.build) end)
            r.del:SetScript("OnClick", function()
                local dlg = StaticPopup_Show("CW_CLASSLESS_DELETEBUILD", arch.name)
                if dlg then dlg.data = arch.index end
            end)
            r.edit:Show(); r.share:Show(); r.del:Show()
            return 24   -- the height the actions add to the row
        end
        r.edit:Hide(); r.share:Hide(); r.del:Hide()
        return 0
    end

    -- ---- "Save my build" ---------------------------------------------------------
    -- AMA|id,id,...  AMT|id:rank,...  AME| : the character's build as a plan
    function CW.ReadMyBuild(kind, p)
        local m = CW.awaitMine
        if not m then return end
        if kind == "AMA" then
            for id in string.gmatch(p[2] or "", "(%d+),") do tinsert(m.abilities, tonumber(id)) end
        elseif kind == "AMT" then
            for id, rank in string.gmatch(p[2] or "", "(%d+):(%d+),") do tinsert(m.talents, { tonumber(id), tonumber(rank) }) end
        else
            CW.awaitMine = nil
            local who = UnitName("player") or "My"
            CW.OpenBuildEditor({ name = who .. "'s build", desc = "", abilities = m.abilities, talents = m.talents }, nil)
        end
    end
end

-- Build editor ----------------------------------------------------------------
-- A build is edited in the main panel itself, not in a window beside it. The
-- My Build column turns into the build being drafted, and the Abilities and
-- Talents lists next to it become the picker: while a build is open a click on
-- a row adds it to the build instead of buying it, and a right-click takes it
-- (or one talent rank) back out. Rows already in the build are tinted and
-- ticked, so the lists show at a glance what the build holds.
--
-- The draft is kept in the order things are bought, which is the order of
-- the levels they are bought at. Each row's level can be chosen (click it,
-- or turn the mouse wheel over it): a later level holds the entry back to
-- it, and the row moves to its place. The arrows mean sooner and later: past
-- a row of another level they take that row's level. Every change is
-- previewed on the server (ARCHPLANX) a moment later; the levels, the budget
-- and any reason to refuse come from there, and Save waits for a clean verdict.
do
    local W = BUILD_W
    local function Shown(x, on) if on then x:Show() else x:Hide() end end
    local ROW_H, CTRL = 20, 14
    local E = CreateFrame("Frame", "ClasslessWildcardBuildEditor", frame)
    E:SetPoint("TOPLEFT", frame, "TOPLEFT", BUILD_X, PANE_TOP - 30)
    E:SetPoint("BOTTOMRIGHT", frame, "BOTTOMLEFT", BUILD_X + W, 64)
    -- Kept above the panel. The panel is toplevel, so every click on it
    -- raises its level, and a level set once at load soon falls under it:
    -- the panel's opaque ground then covers the editor, which still works
    -- but cannot be seen. Lifted on open and whenever the panel overtakes it.
    function E.Lift()
        local want = frame:GetFrameLevel() + 20
        if E:GetFrameLevel() < want then E:SetFrameLevel(want) end
    end
    E.Lift()
    E:EnableMouse(true)
    E:Hide()
    CW.buildEditor = E

    -- name and description, each with its label shown inside while empty
    local function Box(name, y, max, placeholder)
        local b = CreateFrame("EditBox", name, E, "InputBoxTemplate")
        b:SetHeight(20)
        b:SetPoint("TOPLEFT", 6, y)
        b:SetPoint("TOPRIGHT", -2, y)
        b:SetAutoFocus(false)
        b:SetMaxLetters(max)
        b:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
        b:SetScript("OnEnterPressed", function(self) self:ClearFocus() end)
        b.hint = b:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
        b.hint:SetPoint("LEFT", 2, 0)
        b.hint:SetText(placeholder)
        b:SetScript("OnEditFocusGained", function(self) self.hint:Hide() end)
        b:SetScript("OnEditFocusLost", function(self)
            if (self:GetText() or "") == "" then self.hint:Show() end
        end)
        return b
    end
    E.name = Box("ClasslessWildcardBuildName", 0, 32, "Build name")
    E.desc = Box("ClasslessWildcardBuildDesc", -24, 120, "Description (optional)")
    local function SyncHints()
        Shown(E.name.hint, (E.name:GetText() or "") == "")
        Shown(E.desc.hint, (E.desc:GetText() or "") == "")
    end

    -- the draft, scrolling
    E.scroll = CreateFrame("ScrollFrame", "ClasslessWildcardBuildEditorScroll", E, "UIPanelScrollFrameTemplate")
    E.scroll:SetPoint("TOPLEFT", 0, -52)
    E.scroll:SetPoint("BOTTOMRIGHT", -20, 96)
    E.scrollBar = _G["ClasslessWildcardBuildEditorScrollScrollBar"]
    local CHILD_W = W - 20
    E.child = CreateFrame("Frame", nil, E.scroll)
    E.child:SetWidth(CHILD_W); E.child:SetHeight(1)
    E.scroll:SetScrollChild(E.child)

    E.empty = E.child:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    E.empty:SetPoint("TOPLEFT", 6, -30)
    E.empty:SetWidth(CHILD_W - 12)
    E.empty:SetJustifyH("LEFT")
    E.empty:SetTextColor(0.75, 0.75, 0.75)
    E.empty:SetText("Click an ability or talent in the lists on the left to add it here. "
        .. "Right-click takes it back out, or one talent rank.\n\n"
        .. "Each row shows the level it is bought at. Click the level to type another, turn the "
        .. "mouse wheel over it, or use the arrows. Only that row changes.")

    E.budget = E:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    E.budget:SetPoint("BOTTOMLEFT", 2, 80)
    E.budget:SetWidth(W - 4)
    E.budget:SetJustifyH("LEFT")
    E.verdict = E:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    E.verdict:SetPoint("BOTTOMLEFT", 2, 28)
    E.verdict:SetWidth(W - 4)
    E.verdict:SetHeight(48)
    E.verdict:SetJustifyH("LEFT")
    E.verdict:SetJustifyV("TOP")

    local BTN_W = math.floor((W - 12) / 3)
    local function Button(text, x)
        local b = CreateFrame("Button", nil, E, "UIPanelButtonTemplate")
        b:SetWidth(BTN_W); b:SetHeight(22)
        b:SetPoint("BOTTOMLEFT", x, 2)
        b:SetText(text)
        return b
    end
    E.save = Button("Save", 0)
    E.shareBtn = Button("Share", BTN_W + 6)
    E.fix = Button("Fix order", BTN_W + 6)
    E.fix:Hide()
    E.cancel = Button("Close", 2 * (BTN_W + 6))
    E.cancel:SetScript("OnClick", function() CW.CloseBuildEditor() end)
    E.fix:SetScript("OnClick", function()
        if not E.preview or not E.preview.done then return end
        CW.FixBuildOrder(E.build, E.preview)
        CW.BuildEditorChanged()
    end)
    E.fix:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:AddLine("Fix order")
        GameTooltip:AddLine("Puts abilities in the order they unlock, "
            .. "caps ranks and drops repeats. Rows marked in red say what is wrong.", 1, 1, 1, true)
        GameTooltip:Show()
    end)
    E.fix:SetScript("OnLeave", function() GameTooltip:Hide() end)

    -- talent names, icons, ranks and tier levels, and the level each ability
    -- unlocks at, as the editor has seen them in the lists and the previews:
    -- a build stores only the ids
    CW.talentInfo = CW.talentInfo or {}
    CW.abilityInfo = CW.abilityInfo or {}

    -- ---- levels -------------------------------------------------------------------
    -- Every entry has a level of its own: the level it becomes available at
    -- (an ability's unlock, a talent's tier), or a later one the build holds
    -- it back to. Changing one entry's level never moves another. The build
    -- has to afford each entry at its level: the essence a Hero has earned by
    -- then covers it and every entry set at or before it. An entry cannot be
    -- set earlier than that, so it stops at the earliest level it can be
    -- bought. The lists are shown in level order, ties in the order added.
    local function Cap() return CW.rules.maxLevel or 80 end
    local function FloorA(id) local i = CW.abilityInfo[id]; return i and i.unlock or 1 end
    local function FloorT(tid) local i = CW.talentInfo[tid]; return i and i.tier or 10 end
    local function Waits(b)
        b.waitA = b.waitA or {}
        b.waitT = b.waitT or {}
    end
    local function LevelA(b, id) return math.max(FloorA(id), (b.waitA or {})[id] or 0) end
    -- A talent's ranks are entries of their own, one rank each, keyed
    -- "talent:rank", each with its own level. A rank comes no sooner than
    -- the rank before it.
    local function TKey(t) return t[1] .. ":" .. t[2] end
    local function TSplit(k)
        local tid, rank = k:match("^(%d+):(%d+)$")
        return tonumber(tid), tonumber(rank)
    end
    local function PrevRank(b, tid, rank)
        if rank <= 1 then return nil end
        for _, t in ipairs(b.talents) do
            if t[1] == tid and t[2] == rank - 1 then return t end
        end
        return nil
    end
    local function LevelT(b, k)
        local tid, rank = TSplit(k)
        local lv = math.max(FloorT(tid), (b.waitT or {})[k] or 0)
        local prev = PrevRank(b, tid, rank)
        if prev then lv = math.max(lv, LevelT(b, TKey(prev))) end
        return lv
    end
    -- what an entry costs: an ability its own price, or nothing when another
    -- entry in the build brings it free; a talent its ranks
    local function CostA(id)
        local s = E.preview and E.preview.abilities and E.preview.abilities[id]
        if s and s.free then return 0 end
        local i = CW.abilityInfo[id]
        return i and i.cost or 0
    end
    local function CostT(t)
        local c = CW.talentCost or 1
        if CW.talentFlat then return t[2] == 1 and c or 0 end
        return c
    end
    -- What a Hero with no Rebirth bonus has earned by a level: the schedule
    -- the server holds a build to, so a build that fits here fits anyone.
    local function Earned(kind, lv)
        local r = CW.rules
        if kind == "A" then
            return (r.startAE or 3) + math.max(0, lv - (r.aeStart or 4) + 1) * (r.aePer or 1)
        end
        return math.max(0, lv - (r.teStart or 10) + 1) * (r.tePer or 1)
    end
    -- one list's accessors, so the abilities and talents share the code
    local function Kind(kind)
        local b = E.build
        Waits(b)
        -- list, waits, key, level, the earliest level, cost, and the level
        -- it becomes available at (below which no hold is stored)
        if kind == "A" then
            return b.abilities, b.waitA, function(x) return x end,
                function(id) return LevelA(b, id) end, FloorA, function(x) return CostA(x) end, FloorA
        end
        return b.talents, b.waitT, TKey,
            function(k) return LevelT(b, k) end,
            function(k)
                local tid, rank = TSplit(k)
                local prev = PrevRank(b, tid, rank)
                return math.max(FloorT(tid), prev and LevelT(b, TKey(prev)) or 0)
            end, CostT, function(k) return FloorT((TSplit(k))) end
    end
    -- The first level at which the build runs short of essence, or nil when
    -- it never does. `id` can be tried at another level (`at`), or left out
    -- altogether (`at` false).
    local function ShortAt(kind, id, at)
        local list, _, key, level, _, cost = Kind(kind)
        local spend = {}
        for _, x in ipairs(list) do
            local k = key(x)
            local lv = level(k)
            if k == id and at ~= nil then lv = at end
            if lv then spend[lv] = (spend[lv] or 0) + cost(x) end
        end
        local sum = 0
        for lv = 1, Cap() do
            if spend[lv] then
                sum = sum + spend[lv]
                if sum > Earned(kind, lv) then return lv end
            end
        end
        return nil
    end
    -- The earliest level from `from` at which the build can afford `id`
    -- there; nil when none by the cap. When the build is short without it,
    -- nothing it does changes that, so the level asked for stands.
    local function Fit(kind, id, from)
        local _, _, _, _, floor = Kind(kind)
        from = math.max(from, floor(id))
        if ShortAt(kind, id, false) then return from end
        for lv = from, Cap() do
            if not ShortAt(kind, id, lv) then return lv end
        end
        return nil
    end
    local function SortByLevel(kind)
        local list, _, key, level = Kind(kind)
        local tmp = {}
        for i, x in ipairs(list) do tmp[i] = { x = x, at = i, lv = level(key(x)) } end
        table.sort(tmp, function(p, q)
            if p.lv ~= q.lv then return p.lv < q.lv end
            return p.at < q.at
        end)
        for i, t in ipairs(tmp) do list[i] = t.x end
    end
    -- A build that runs short, saved before every entry had a level of its
    -- own (a starter build, an old code): each entry, in order, gets the
    -- level it was bought at then, which is no earlier than the one before it
    -- and no earlier than the essence allows. A build that fits is left as
    -- it is. Needs the costs, so it runs once the server has looked.
    local function Settle(kind)
        if not ShortAt(kind) then return false end
        local list, waits, key, level, _, cost, base = Kind(kind)
        local sum, prev = 0, 1
        for _, x in ipairs(list) do
            local k = key(x)
            local lv = math.max(level(k), prev)
            sum = sum + cost(x)
            while lv < Cap() and sum > Earned(kind, lv) do lv = lv + 1 end
            waits[k] = lv > base(k) and lv or nil
            prev = lv
        end
        return true
    end
    -- One entry per rank. A build saved with one entry for several ranks (a
    -- starter build, an older save or code, Save my build) is split into its
    -- ranks; the level it held the talent back to goes to the first of them.
    local function Expand(b)
        Waits(b)
        local out, top = {}, {}
        for _, t in ipairs(b.talents) do
            local tid, rank = t[1], t[2]
            local from = (top[tid] or 0) + 1
            local held = b.waitT[tid]
            for r = from, rank do
                out[#out + 1] = { tid, r }
                local k = tid .. ":" .. r
                if r == from and held and not b.waitT[k] then b.waitT[k] = held end
            end
            if rank > (top[tid] or 0) then top[tid] = rank end
        end
        for k in pairs(b.waitT) do
            if type(k) == "number" then b.waitT[k] = nil end
        end
        b.talents = out
    end
    -- The build in the order it is bought, level by level: what the server is
    -- asked about, saved and shared, whatever order the rows are in while the
    -- wheel turns. The server buys in list order, so a row left out of place
    -- would read as bought late.
    local function Sorted(b)
        local c = CW.CopyBuild(b)
        local function by(list, lv)
            local tmp = {}
            for i, x in ipairs(list) do tmp[i] = { x = x, at = i, lv = lv(x) } end
            table.sort(tmp, function(p, q)
                if p.lv ~= q.lv then return p.lv < q.lv end
                return p.at < q.at
            end)
            for i, t in ipairs(tmp) do list[i] = t.x end
        end
        by(c.abilities, function(id) return LevelA(c, id) end)
        by(c.talents, function(t) return LevelT(c, TKey(t)) end)
        return c
    end
    -- Only once the server has said where everything unlocks: before that a
    -- loaded build's floors are unknown and a sort would scramble it.
    local function Normalize()
        if not (E.preview and E.preview.done) then return end
        SortByLevel("A")
        SortByLevel("T")
    end

    local function Changed(sort)
        if sort then
            Normalize()
            E.wheeling, E.sortDue = nil, nil
        end
        E.dirty = true
        E.verdictOk = false
        E.checking = true
        E.previewDue = GetTime() + 0.4
        CW.RenderBuildEditor()
        -- the lists' ticks and ranks follow the draft
        if CW.RenderBrowsers then CW.RenderBrowsers() end
    end

    function CW.BuildEditorChanged(sort) Changed(sort) end
    function CW.SettleBuildLevels()
        local a, t = Settle("A"), Settle("T")
        return a or t
    end
    -- for the rows: the first level each list runs short at
    function CW.BuildShortAt(kind) return ShortAt(kind) end

    -- the preview a moment after the last change, not one per keystroke
    E:SetScript("OnUpdate", function()
        E.Lift()
        -- the wheel's sort waits for the preview, which knows where each unlocks
        if E.sortDue and GetTime() >= E.sortDue and E.preview and E.preview.done then Changed(true) end
        if E.previewDue and GetTime() >= E.previewDue then
            E.previewDue = nil
            local b = E.build
            b.name = E.name:GetText() or ""
            b.desc = E.desc:GetText() or ""
            E.preview = { abilities = {}, talents = {}, warnA = {}, warnT = {} }
            CW.planTarget = "editor"
            E.asked = (E.asked or 0) + 1
            CW.UploadBuild(Sorted(b))
            Send("ARCHPLANX " .. CW.CleanBuildText(b.name, 32))
        end
    end)
    E.name:SetScript("OnTextChanged", function(_, user) if user then Changed() end end)
    E.desc:SetScript("OnTextChanged", function(_, user) if user then E.dirty = true end end)

    function CW.EditorReadPlan(kind, p)
        local pv = E.preview
        if not pv then return end
        if kind == "APA" then
            -- spell:rarity:level:unlock:free:cost; free is 1 when the ability
            -- comes free with another entry
            for spell, rarity, level, unlock, free, cost in
                string.gmatch(p[3] or "", "(%d+):(%d+):(%d+):?(%d*):?(%d*):?(%d*);") do
                spell = tonumber(spell)
                pv.abilities[spell] = { level = tonumber(level), rarity = tonumber(rarity),
                                        unlock = tonumber(unlock) or 1, free = free == "1" }
                local info = CW.abilityInfo[spell] or {}
                info.unlock = tonumber(unlock) or info.unlock or 1
                info.cost = tonumber(cost) or info.cost
                CW.abilityInfo[spell] = info
            end
        elseif kind == "APW" then
            -- kind:index:code:extra; the index is 0-based in its list
            for k, i, code, extra in string.gmatch(p[3] or "", "([AT]):(%d+):(%a+):(%d+);") do
                local list = k == "A" and pv.warnA or pv.warnT
                list[tonumber(i) + 1] = { code = code, extra = tonumber(extra) }
            end
        elseif kind == "APT" then
            for spell, rarity, rank, max, level, tid, tier in string.gmatch(p[3] or "", "(%d+):(%d+):(%d+):(%d+):(%d+):?(%d*):?(%d*);") do
                tid = tonumber(tid)
                if tid then
                    pv.talents[tid] = { level = tonumber(level) }
                    local info = CW.talentInfo[tid] or {}
                    info.spell, info.rarity, info.max = info.spell or tonumber(spell), tonumber(rarity), tonumber(max)
                    info.tier = tonumber(tier) or info.tier
                    CW.talentInfo[tid] = info
                end
            end
        else
            pv.spentA, pv.totalA = tonumber(p[3]) or 0, tonumber(p[4]) or 0
            pv.spentT, pv.totalT = tonumber(p[5]) or 0, tonumber(p[6]) or 0
            pv.problem = p[7] or ""
            pv.done = true
            -- Only the answer to the latest change counts: while another is
            -- due or on its way, this one is about a build that has changed.
            E.answered = (E.answered or 0) + 1
            E.checking = E.previewDue ~= nil or E.answered < (E.asked or 0)
            E.verdictOk = pv.problem == "" and not E.checking
            -- the first look at a build that ran on the old rule pins its
            -- levels; the server is asked again about the result
            if E.settle then
                E.settle = nil
                if CW.SettleBuildLevels() then
                    Changed(true)
                    return
                end
            end
            CW.RenderBuildEditor()
        end
    end

    -- ---- editing the draft ------------------------------------------------------------
    local function IndexOf(list, id)
        for i, x in ipairs(list) do
            if (type(x) == "table" and x[1] or x) == id then return i end
        end
        return nil
    end
    local function Refuse(text) UIErrorsFrame:AddMessage(text, 1.0, 0.1, 0.1) end
    -- A new ability goes in at the earliest level the build can afford it,
    -- and nothing else moves. One the essence never reaches is refused.
    local function AddAbility(id)
        if IndexOf(E.build.abilities, id) then return end
        tinsert(E.build.abilities, id)
        local lv = Fit("A", id, FloorA(id))
        if not lv then
            tremove(E.build.abilities)
            Refuse("Not enough Ability Essence for that by level " .. Cap() .. ".")
            return
        end
        Waits(E.build)
        E.build.waitA[id] = lv > FloorA(id) and lv or nil
        E.reveal = "A" .. id
        Changed(true)
    end
    local function RemoveAbility(id)
        local i = IndexOf(E.build.abilities, id)
        if not i then return end
        tremove(E.build.abilities, i)
        Waits(E.build)
        E.build.waitA[id] = nil
        Changed()
    end
    -- the highest rank of a talent the build takes
    local function TopRank(tid)
        local top = 0
        for _, t in ipairs(E.build.talents) do
            if t[1] == tid and t[2] > top then top = t[2] end
        end
        return top
    end
    -- One rank more is an entry of its own, at the earliest level the build
    -- can afford it and no sooner than the rank before it. Nothing else moves.
    local function AddRank(tid, max)
        Waits(E.build)
        local top = TopRank(tid)
        if max and top >= max then return end
        local t = { tid, top + 1 }
        tinsert(E.build.talents, t)
        local k = TKey(t)
        local _, _, _, _, floor = Kind("T")
        local lv = Fit("T", k, floor(k))
        if not lv then
            tremove(E.build.talents)
            Refuse("Not enough Talent Essence for that by level " .. Cap() .. ".")
            return
        end
        E.build.waitT[k] = lv > FloorT(tid) and lv or nil
        E.reveal = "T" .. k
        Changed(true)
    end
    -- a rank out, and every higher rank of that talent with it
    local function RemoveTalentFrom(tid, rank)
        Waits(E.build)
        for i = #E.build.talents, 1, -1 do
            local t = E.build.talents[i]
            if t[1] == tid and t[2] >= rank then
                E.build.waitT[TKey(t)] = nil
                tremove(E.build.talents, i)
            end
        end
        Changed()
    end
    -- a right-click in the Talents list: the highest rank comes out
    local function RemoveRank(tid)
        local top = TopRank(tid)
        if top > 0 then RemoveTalentFrom(tid, top) end
    end

    -- The level an entry is bought at, chosen: never before it is available,
    -- never before the build can afford it there, never past the cap. Its own
    -- floor clears the hold. No other entry moves.
    local function SetLevel(kind, id, lv, keepOrder)
        local _, waits, _, level, floor, _, base = Kind(kind)
        lv = math.max(floor(id), math.min(math.floor(tonumber(lv) or 0), Cap()))
        if kind == "T" then
            -- never past the rank after it: rank 2 is not bought before rank 1
            local tid, rank = TSplit(id)
            for _, t in ipairs(E.build.talents) do
                if t[1] == tid and t[2] == rank + 1 then lv = math.min(lv, LevelT(E.build, TKey(t))) end
            end
        end
        if lv < level(id) then lv = Fit(kind, id, lv) or level(id) end
        waits[id] = lv > base(id) and lv or nil
        Changed(not keepOrder)
    end

    -- The arrows: one level sooner or later for that row alone. Sooner stops
    -- at the earliest level the row can be bought.
    local function CanMove(kind, i, d)
        local list, _, key, level = Kind(kind)
        local me = key(list[i])
        local lv = level(me)
        if d > 0 then
            if kind == "T" then
                local tid, rank = TSplit(me)
                for _, t in ipairs(E.build.talents) do
                    if t[1] == tid and t[2] == rank + 1 and LevelT(E.build, TKey(t)) <= lv then return false end
                end
            end
            return lv < Cap()
        end
        local to = Fit(kind, me, lv - 1)
        return to ~= nil and to < lv
    end
    local function Move(kind, i, d)
        local list, _, key, level = Kind(kind)
        local me = key(list[i])
        SetLevel(kind, me, level(me) + d)
    end

    -- ---- the rows ------------------------------------------------------------------
    E.rows, E.headers = {}, {}
    local function IconButton(parent, tex, size, tip)
        local b = CreateFrame("Button", nil, parent)
        b:SetWidth(size); b:SetHeight(size)
        b:SetNormalTexture(tex .. "-Up")
        b:SetPushedTexture(tex .. "-Down")
        b:SetHighlightTexture("Interface\\Buttons\\UI-Common-MouseHilight", "ADD")
        if tip then
            b:SetScript("OnEnter", function(self)
                GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
                GameTooltip:SetText(tip)
                GameTooltip:Show()
            end)
            b:SetScript("OnLeave", function() GameTooltip:Hide() end)
        end
        return b
    end
    local function Row(i)
        local r = E.rows[i]
        if r then return r end
        r = CreateFrame("Button", nil, E.child)
        r:SetWidth(CHILD_W); r:SetHeight(ROW_H)
        r:RegisterForClicks("LeftButtonUp", "RightButtonUp")
        r.stripe = r:CreateTexture(nil, "BACKGROUND")
        r.stripe:SetAllPoints(r)
        r.stripe:SetTexture("Interface\\Buttons\\WHITE8X8")
        -- the level: click to choose it, mouse wheel for one level either way
        -- wide enough for "Lv 80" on one line
        r.levelBtn = CreateFrame("Button", nil, r)
        r.levelBtn:SetWidth(38); r.levelBtn:SetHeight(ROW_H)
        r.levelBtn:SetPoint("LEFT", 0, 0)
        r.levelBtn:SetHighlightTexture("Interface\\Buttons\\UI-Common-MouseHilight", "ADD")
        r.levelBtn:EnableMouseWheel(true)
        r.level = r.levelBtn:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
        r.level:SetPoint("LEFT", 3, 0)
        r.level:SetWidth(36); r.level:SetHeight(ROW_H)
        r.level:SetJustifyH("LEFT")
        r.icon = r:CreateTexture(nil, "ARTWORK")
        r.icon:SetWidth(16); r.icon:SetHeight(16)
        r.icon:SetPoint("LEFT", 40, 0)
        r.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
        r.del = IconButton(r, "Interface\\Buttons\\UI-MinusButton", CTRL, "Take it out")
        r.del:SetPoint("RIGHT", -1, 0)
        r.down = IconButton(r, "Interface\\Buttons\\UI-ScrollBar-ScrollDownButton", CTRL + 2, "One level later")
        r.down:SetPoint("RIGHT", r.del, "LEFT", 1, 0)
        r.down:SetDisabledTexture("Interface\\Buttons\\UI-ScrollBar-ScrollDownButton-Disabled")
        r.up = IconButton(r, "Interface\\Buttons\\UI-ScrollBar-ScrollUpButton", CTRL + 2, "One level sooner")
        r.up:SetPoint("RIGHT", r.down, "LEFT", 3, 0)
        r.up:SetDisabledTexture("Interface\\Buttons\\UI-ScrollBar-ScrollUpButton-Disabled")
        r.rank = r:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        r.rank:SetPoint("RIGHT", r.up, "LEFT", -2, 0)
        r.rank:SetWidth(26)
        r.rank:SetJustifyH("RIGHT")
        r.name = r:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        r.name:SetPoint("LEFT", r.icon, "RIGHT", 4, 0)
        r.name:SetHeight(12)
        r.name:SetJustifyH("LEFT")
        -- The rank column only when the row has something in it (a talent's
        -- rank, "free"): otherwise the name has the room.
        function r.SetRank(text)
            r.rank:SetText(text or "")
            r.name:SetPoint("RIGHT", (text and text ~= "") and r.rank or r.up, "LEFT", -3, 0)
        end
        r:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight", "ADD")
        r:SetScript("OnEnter", function(self)
            GameTooltip:Hide()   -- the same link on a shown tooltip toggles it off
            GameTooltip:SetOwner(self, "ANCHOR_LEFT")
            if self.spellId then
                GameTooltip:SetHyperlink("spell:" .. self.spellId)
            else
                GameTooltip:SetText(self.name:GetText() or "")
            end
            -- what the server found wrong with this row, under the spell
            if self.warning then GameTooltip:AddLine(self.warning, 1, 0.33, 0.27, true) end
            GameTooltip:AddLine(self.isTalent and "Right-click: one rank fewer." or "Right-click: take it out.",
                0.9, 0.8, 0.4)
            GameTooltip:Show()
        end)
        r:SetScript("OnLeave", function() GameTooltip:Hide() end)
        E.rows[i] = r
        return r
    end
    E.levelBox = CreateFrame("EditBox", "ClasslessWildcardBuildLevel", E.child, "InputBoxTemplate")
    E.levelBox:SetWidth(24); E.levelBox:SetHeight(18)
    E.levelBox:SetAutoFocus(false)
    E.levelBox:SetNumeric(true)
    E.levelBox:SetMaxLetters(2)
    E.levelBox:SetJustifyH("CENTER")
    E.levelBox:Hide()
    -- Enter, or clicking away, keeps the typed level; Escape keeps the old one
    E.levelBox:SetScript("OnEnterPressed", function(self) self:ClearFocus() end)
    E.levelBox:SetScript("OnEscapePressed", function(self) self.target = nil; self:ClearFocus() end)
    E.levelBox:SetScript("OnEditFocusLost", function(self)
        local t = self.target
        self.target = nil
        if self.row then self.row.level:Show(); self.row = nil end
        self:Hide()
        if t and (self:GetText() or "") ~= "" then SetLevel(t.kind, t.id, self:GetText()) end
    end)
    E.levelBox:SetScript("OnHide", function(self)
        if self.row then self.row.level:Show(); self.row = nil end
    end)

    -- what a row's level button says and does
    local function WireLevel(r, kind, id, step)
        local _, waits, _, level, floor = Kind(kind)
        local held = waits[id]
        r.levelBtn:SetScript("OnClick", function(self)
            local box = E.levelBox
            if box:IsShown() then box:ClearFocus() end
            box:ClearAllPoints()
            box:SetPoint("LEFT", self, "LEFT", 6, 0)
            box:SetFrameLevel(r:GetFrameLevel() + 5)
            r.level:Hide()
            box.row = r
            box.target = { kind = kind, id = id }
            box:SetText(tostring(level(id)))
            box:Show()
            box:SetFocus()
            box:HighlightText()
        end)
        -- The row stays where it is while the wheel turns, or the next notch
        -- would land on whatever row slid under the cursor. It takes its
        -- place in the list once the wheel has rested for a moment.
        r.levelBtn:SetScript("OnMouseWheel", function(_, delta)
            E.wheeling = kind .. id
            E.sortDue = GetTime() + 1.2
            SetLevel(kind, id, level(id) + (delta > 0 and -1 or 1), true)
        end)
        r.levelBtn:SetScript("OnEnter", function(self)
            GameTooltip:SetOwner(self, "ANCHOR_LEFT")
            local free = step and step.free
            GameTooltip:AddLine((free and "Comes free at level " or "Bought at level ") .. level(id))
            if free then
                GameTooltip:AddLine("Another ability or talent in the build brings it, so it costs no essence.",
                    1, 1, 1, true)
            end
            if held then GameTooltip:AddLine("Held back to this level.", 1, 0.82, 0) end
            GameTooltip:AddLine((kind == "A" and "Unlocks" or "Its tier opens") .. " at level " .. floor(id) .. ".",
                0.75, 0.75, 0.75)
            GameTooltip:AddLine("Click to type a level. Mouse wheel: one level sooner or later. "
                .. "It cannot come before the build has the essence for it. No other row moves.", 0.9, 0.8, 0.4, true)
            GameTooltip:Show()
        end)
        r.levelBtn:SetScript("OnLeave", function() GameTooltip:Hide() end)
    end

    local function Header(i)
        local h = E.headers[i]
        if h then return h end
        h = { text = E.child:CreateFontString(nil, "OVERLAY", "GameFontNormal"), rule = E.child:CreateTexture(nil, "ARTWORK") }
        h.text:SetJustifyH("LEFT")
        h.rule:SetHeight(1)
        h.rule:SetTexture(1, 0.82, 0, 0.25)
        E.headers[i] = h
        return h
    end

    -- the row's warning in words, from the code the server sent
    local function Warning(w)
        if not w then return nil end
        local cap = CW.rules.maxLevel or 80
        if w.code == "gone" then return "This realm does not have it, or it cannot be bought." end
        if w.code == "twice" then return "It is already in the build." end
        if w.code == "rank" then return "It does not have that many ranks." end
        if w.code == "never" then return "In this order it is never bought by level " .. cap .. "." end
        if w.code == "needs" then
            if (w.extra or 0) == 0 then return "It needs an ability that is not in the build." end
            local info = CW.talentInfo[w.extra]
            local name = info and info.spell and (GetSpellInfo(info.spell))
            return "It needs " .. (name or "another talent") .. " earlier in the build."
        end
        return nil
    end


    function CW.RenderBuildEditor()
        local b, pv = E.build, E.preview or {}
        if not b then return end
        for _, r in ipairs(E.rows) do r:Hide() end
        for _, h in ipairs(E.headers) do h.text:Hide(); h.rule:Hide() end
        local y, nr, nh = 0, 0, 0
        local cap = CW.rules.maxLevel or 80
        local function Section(label)
            nh = nh + 1
            local h = Header(nh)
            h.text:ClearAllPoints(); h.text:SetPoint("TOPLEFT", E.child, "TOPLEFT", 2, -y)
            h.text:SetText(label)
            h.rule:ClearAllPoints()
            h.rule:SetPoint("TOPLEFT", E.child, "TOPLEFT", 0, -y - 15)
            h.rule:SetPoint("TOPRIGHT", E.child, "TOPRIGHT", 0, -y - 15)
            h.text:Show(); h.rule:Show()
            y = y + 19
        end
        local shortA, shortT = CW.BuildShortAt("A"), CW.BuildShortAt("T")
        local function LevelText(held, key, lv, short)
            if short and lv == short then return "|cffff5544Lv " .. lv .. "|r" end
            if held or E.wheeling == key then return "|cffffd100Lv " .. lv .. "|r" end
            return "Lv " .. lv
        end
        local function ShortWarning(lv, short, what)
            if not short or lv ~= short then return nil end
            return "By level " .. lv .. " a Hero has not earned the " .. what .. " for everything set at or "
                .. "before it. Set this or an earlier entry later."
        end
        local function Arrows(r, kind, i)
            if CanMove(kind, i, -1) then r.up:Enable() else r.up:Disable() end
            if CanMove(kind, i, 1) then r.down:Enable() else r.down:Disable() end
        end
        Waits(b)
        local function Place(r, i, warning)
            r.top = y
            r:ClearAllPoints()
            r:SetPoint("TOPLEFT", E.child, "TOPLEFT", 0, -y)
            r:SetPoint("TOPRIGHT", E.child, "TOPRIGHT", 0, -y)
            r.warning = warning
            if warning then r.stripe:SetVertexColor(1, 0.2, 0.15, 0.18)
            else r.stripe:SetVertexColor(1, 1, 1, i % 2 == 0 and 0.03 or 0.07) end
            r:Show()
            y = y + ROW_H
        end

        local empty = #b.abilities + #b.talents == 0
        if empty then E.empty:Show() else E.empty:Hide() end

        Section("Abilities  |cffaaaaaa" .. #b.abilities .. "|r")
        for i, id in ipairs(b.abilities) do
            nr = nr + 1
            local r = Row(nr)
            local step = pv.abilities and pv.abilities[id]
            r.spellId, r.isTalent = id, false
            r.revealKey = "A" .. id
            local lv = LevelA(b, id)
            Place(r, i, Warning(pv.warnA and pv.warnA[i]) or ShortWarning(lv, shortA, "Ability Essence"))
            r.level:SetText((r.warning and not (shortA == lv)) and "|cffff5544!|r"
                or LevelText(b.waitA[id], "A" .. id, lv, shortA))
            WireLevel(r, "A", id, step)
            Arrows(r, "A", i)
            r.icon:SetTexture(SpellIcon(id))
            r.name:SetText(SpellLabel(id, step and step.rarity or 0))
            r.SetRank(step and step.free and "|cffaaaaaafree|r" or "")
            r:SetScript("OnClick", function(_, button) if button == "RightButton" then RemoveAbility(id) end end)
            r.up:SetScript("OnClick", function() Move("A", i, -1) end)
            r.down:SetScript("OnClick", function() Move("A", i, 1) end)
            r.del:SetScript("OnClick", function() RemoveAbility(id) end)
        end
        if empty then y = y + 96 end
        y = y + 8
        local ranks = #b.talents
        Section("Talents  |cffaaaaaa" .. ranks .. (ranks == 1 and " rank" or " ranks") .. "|r")
        for i, t in ipairs(b.talents) do
            nr = nr + 1
            local r = Row(nr)
            local info = CW.talentInfo[t[1]] or {}
            local step = pv.talents and pv.talents[t[1]]
            local tid, key = t[1], TKey(t)
            r.revealKey = "T" .. key
            r.spellId, r.isTalent = info.spell, true
            Place(r, i, Warning(pv.warnT and pv.warnT[i]))
            local lvT = LevelT(b, key)
            if not r.warning then r.warning = ShortWarning(lvT, shortT, "Talent Essence") end
            if r.warning then r.stripe:SetVertexColor(1, 0.2, 0.15, 0.18) end
            r.level:SetText((r.warning and not (shortT == lvT)) and "|cffff5544!|r"
                or LevelText(b.waitT[key], "T" .. key, lvT, shortT))
            WireLevel(r, "T", key, step)
            Arrows(r, "T", i)
            r.icon:SetTexture(info.spell and SpellIcon(info.spell) or "Interface\\Icons\\INV_Misc_QuestionMark")
            r.name:SetText(info.spell and SpellLabel(info.spell, info.rarity or 0) or ("Talent " .. tid))
            r.SetRank(t[2] .. "/" .. (info.max or "?"))
            r:SetScript("OnClick", function(_, button) if button == "RightButton" then RemoveRank(tid) end end)
            r.up:SetScript("OnClick", function() Move("T", i, -1) end)
            r.down:SetScript("OnClick", function() Move("T", i, 1) end)
            local rank = t[2]
            r.del:SetScript("OnClick", function() RemoveTalentFrom(tid, rank) end)
        end
        E.child:SetHeight(math.max(y, 1))
        E.scroll:UpdateScrollChildRect()
        -- the bar only when there is something to scroll, and the rows take
        -- its room when there is not
        local view = E.scroll:GetHeight() or 0
        local bar = y > view and view > 0
        E.scroll:SetPoint("BOTTOMRIGHT", bar and -20 or -2, 96)
        E.child:SetWidth(W - (bar and 20 or 2))
        if E.scrollBar then
            if bar then
                E.scrollBar:Show()
            else
                E.scrollBar:Hide()
                E.scroll:SetVerticalScroll(0)
            end
        end
        -- Something just added: scroll just far enough that its row shows.
        -- The bar's range is set first, or it would hold the list to the old one.
        if E.reveal then
            local want
            for _, r in ipairs(E.rows) do
                if r:IsShown() and r.revealKey == E.reveal then want = r.top end
            end
            E.reveal = nil
            if want and bar then
                local range = math.max(0, y - view)
                local at = E.scroll:GetVerticalScroll() or 0
                if want < at then
                    at = want
                elseif want + ROW_H > at + view then
                    at = want + ROW_H - view
                end
                at = math.max(0, math.min(at, range))
                if E.scrollBar then E.scrollBar:SetMinMaxValues(0, range) end
                E.scroll:SetVerticalScroll(at)
            end
        end

        -- the budget and the verdict, once the server has looked
        if pv.done then
            local function Part(label, spent, total)
                local c = spent > total and "|cffff5544" or "|cff00ff00"
                return label .. " " .. c .. spent .. "|r / " .. total
            end
            E.budget:SetText(Part("Ability Essence", pv.spentA, pv.totalA) .. "    "
                .. Part("Talent", pv.spentT, pv.totalT))
            if E.checking then
                E.verdict:SetText("|cffaaaaaaChecking the build...|r")
            elseif pv.problem ~= "" then
                E.verdict:SetText("|cffff5544" .. pv.problem .. "|r")
            elseif E.dirty then
                E.verdict:SetText("|cff00ff00Fits by level " .. cap .. ". Not saved yet.|r")
            else
                E.verdict:SetText("|cff00ff00Fits by level " .. cap .. ". Saved.|r")
            end
        else
            E.budget:SetText("|cffaaaaaaChecking the build...|r")
            E.verdict:SetText("")
        end
        if E.verdictOk then E.save:Enable() else E.save:Disable() end
        if E.verdictOk then E.shareBtn:Enable() else E.shareBtn:Disable() end
        -- Fix order takes Share's place while there is something it can fix
        if CW.BuildNeedsFix(pv) then E.fix:Show(); E.shareBtn:Hide() else E.fix:Hide(); E.shareBtn:Show() end
    end

    -- Whether Fix order has anything it can do: a repeat, a rank past the
    -- maximum, a talent above what it needs, or a step the order leaves unbought.
    function CW.BuildNeedsFix(pv)
        if not pv or not pv.done then return false end
        for _, list in ipairs({ pv.warnA or {}, pv.warnT or {} }) do
            for _, w in pairs(list) do
                if w.code == "twice" or w.code == "rank" or w.code == "never"
                    or (w.code == "needs" and (w.extra or 0) > 0) then
                    return true
                end
            end
        end
        return false
    end

    -- Fix order: repeats dropped, ranks capped, abilities in the order they
    -- unlock (ties keep their place), and every talent moved below the talent
    -- it needs. What order cannot fix (something the realm lacks, an ability
    -- a talent needs) is left for the player, still marked.
    function CW.FixBuildOrder(b, pv)
        local seen, abilities = {}, {}
        local waitA, waitT = b.waitA or {}, b.waitT or {}
        for i, id in ipairs(b.abilities) do
            if not seen[id] then
                seen[id] = true
                abilities[#abilities + 1] = { id = id, at = i,
                    unlock = math.max((pv.abilities[id] and pv.abilities[id].unlock) or 1, waitA[id] or 0) }
            end
        end
        table.sort(abilities, function(x, y)
            if x.unlock ~= y.unlock then return x.unlock < y.unlock end
            return x.at < y.at
        end)
        b.abilities = {}
        for i, a in ipairs(abilities) do b.abilities[i] = a.id end

        local needs, inBuild, talents = {}, {}, {}
        for i, t in ipairs(b.talents) do
            local w = pv.warnT and pv.warnT[i]
            if w and w.code == "needs" and (w.extra or 0) > 0 then needs[t[1]] = w.extra end
        end
        seen = {}
        for i, t in ipairs(b.talents) do
            local key = TKey(t)
            local info = CW.talentInfo[t[1]]
            -- a rank past the talent's last, or the same rank twice, goes
            if not seen[key] and not (info and info.max and t[2] > info.max) then
                seen[key] = true
                talents[#talents + 1] = { t[1], t[2], at = i, lv = LevelT(b, key) }
                inBuild[t[1]] = true
            end
        end
        -- by the level each is bought at first; the pass below then moves
        -- anything above what it needs
        table.sort(talents, function(x, y)
            if x.lv ~= y.lv then return x.lv < y.lv end
            return x.at < y.at
        end)
        for _, t in ipairs(talents) do t.at, t.lv = nil, nil end
        local placed, out, left = {}, {}, talents
        while #left > 0 do
            local rest, moved = {}, false
            for _, t in ipairs(left) do
                local dep = needs[t[1]]
                if not dep or placed[dep] or not inBuild[dep] then
                    out[#out + 1] = t
                    placed[t[1]] = true
                    moved = true
                else
                    rest[#rest + 1] = t
                end
            end
            if not moved then
                for _, t in ipairs(rest) do out[#out + 1] = t end
                break
            end
            left = rest
        end
        b.talents = out
    end

    -- ---- opening and closing -----------------------------------------------------------
    -- The lists show every level while a build is drafted: a build is planned
    -- to 80 whatever level the character is now. The player's own choice
    -- comes back when the editor closes.
    local function WidenScopes()
        E.scopes = E.scopes or { abil = CW.abilScope, tal = CW.talScope }
        CW.abilScope, CW.talScope = 2, 2
    end
    local function RestoreScopes()
        if not E.scopes then return end
        if CW.abilScope == 2 then CW.abilScope = E.scopes.abil end
        if CW.talScope == 2 then CW.talScope = E.scopes.tal end
        E.scopes = nil
    end
    local function ScopeLabels()
        local S = CW.BROWSE.SCOPES
        if CW.abilScopeBtn and S[CW.abilScope] then CW.abilScopeBtn:SetText(S[CW.abilScope][1]) end
        if CW.talScopeBtn and S[CW.talScope] then CW.talScopeBtn:SetText(S[CW.talScope][1]) end
    end

    local function Open(build, index)
        E.build = CW.CopyBuild(build)
        Expand(E.build)
        E.index = index
        E.dirty = index == nil
        E.verdictOk = false
        E.preview = nil
        E.settle = true
        E.name:SetText(E.build.name or "")
        E.desc:SetText(E.build.desc or "")
        SyncHints()
        -- nothing may sit over the lists the build is picked from
        if not E:IsShown() then
            E.fromFly = CW.archFly and CW.archFly:IsShown() and CW.archTab == "MINE"
        end
        if CW.archFly then CW.archFly:Hide() end
        if CW.archPlan then CW.archPlan:Hide() end
        WidenScopes()
        ScopeLabels()
        E.scroll:SetVerticalScroll(0)
        local opening = not E:IsShown()
        E.Lift()
        E:Show()
        if opening then
            UIErrorsFrame:AddMessage("Click abilities and talents on the left to add them to the build.", 1.0, 0.82, 0.0)
        end
        if not frame:IsShown() then frame:Show() end
        E.previewDue = GetTime()
        CW.RenderBuildEditor()
        if CW.SetTab then CW.SetTab(CW.tab) end
    end

    -- Opening another build over unsaved changes asks first.
    function CW.OpenBuildEditor(build, index)
        if E:IsShown() and E.dirty and E.build and #E.build.abilities + #E.build.talents > 0 then
            local dlg = StaticPopup_Show("CW_CLASSLESS_DISCARDBUILD", CW.CleanBuildText(E.name:GetText(), 32))
            if dlg then dlg.data = { build = build, index = index } end
            return
        end
        Open(build, index)
    end

    -- Leaves the editor for good: the panel's My Build column, the lists'
    -- own clicks and level choice come back, and My Builds reopens if that is
    -- where the editor was opened from.
    function CW.FinishBuildEditor(nextBuild)
        E.dirty = false
        if nextBuild then
            Open(nextBuild.build, nextBuild.index)
            return
        end
        E.build = nil
        E:Hide()
        RestoreScopes()
        ScopeLabels()
        if CW.SetTab then CW.SetTab(CW.tab) end
        if E.fromFly and CW.archFly then
            CW.archTab = "MINE"
            CW.archFly:Show()
            CW.RenderArchFly()
        end
        E.fromFly = nil
    end

    -- Escape hides the editor straight away. It is shown again and closed
    -- the proper way, so unsaved changes still ask and the lists come back.
    -- Hiding the whole panel leaves it open (still shown, just not visible).
    E:SetScript("OnHide", function()
        if E.build and not E:IsShown() then
            E:Show()
            CW.CloseBuildEditor()
        end
    end)

    function CW.CloseBuildEditor()
        if E.dirty and E.build and #E.build.abilities + #E.build.talents > 0 then
            StaticPopup_Show("CW_CLASSLESS_DISCARDBUILD", CW.CleanBuildText(E.name:GetText(), 32))
            return
        end
        CW.FinishBuildEditor()
    end

    E.save:SetScript("OnClick", function()
        if not E.verdictOk then return end
        local b = Sorted(E.build)
        b.name = CW.CleanBuildText(E.name:GetText(), 32)
        b.desc = CW.CleanBuildText(E.desc:GetText(), 120, true)
        local saved = CW.SavedBuilds()
        if E.index and saved[E.index] then saved[E.index] = b else tinsert(saved, b); E.index = #saved end
        E.dirty = false
        E.fromFly = true      -- closing goes back to My Builds, where it now is
        UIErrorsFrame:AddMessage(b.name .. " saved.", 1.0, 0.82, 0.0)
        CW.RenderBuildEditor()
    end)
    E.shareBtn:SetScript("OnClick", function()
        local b = Sorted(E.build)
        b.name, b.desc = E.name:GetText() or "", E.desc:GetText() or ""
        CW.OpenShareWindow("share", b)
    end)

    -- While a build is open the lists are its picker: a click adds, a
    -- right-click takes out, and nothing is bought. Rows in the build are
    -- tinted and ticked; a talent shows the rank the build takes.
    function CW.BrowserRowHook(w, kind, e)
        if not w.draftTint then
            w.draftTint = w:CreateTexture(nil, "BORDER")
            w.draftTint:SetAllPoints(w)
            w.draftTint:SetTexture("Interface\\Buttons\\WHITE8X8")
            w.draftTint:SetVertexColor(0.25, 1, 0.35, 0.12)
            w.draftTint:Hide()
        end
        if not kind or not E:IsShown() or not E.build then
            w.draftTint:Hide()
            w:RegisterForClicks("LeftButtonUp")
            return
        end
        w:RegisterForClicks("LeftButtonUp", "RightButtonUp")
        local b = E.build
        if kind == "A" then
            local id = e.id
            local info = CW.abilityInfo[id] or {}
            info.unlock, info.cost = e.lvl or 1, tonumber(e.cost) or info.cost
            CW.abilityInfo[id] = info
            local inBuild = IndexOf(b.abilities, id) ~= nil
            Shown(w.draftTint, inBuild)
            if inBuild then w.check:Show() else w.check:Hide() end
            w.tipLine = inBuild and "In the build. Right-click to take it out." or "Click to add it to the build."
            w:SetScript("OnClick", function(_, button)
                if button == "RightButton" then RemoveAbility(id) else AddAbility(id) end
            end)
        else
            CW.talentInfo[e.talentId] = { spell = e.spell, rarity = e.rarity, max = e.max, tier = 10 + (e.row or 0) * 5 }
            local tid, max = e.talentId, e.max
            local rank = TopRank(tid)
            Shown(w.draftTint, rank > 0)
            if rank > 0 then w.check:Show() else w.check:Hide() end
            w.name:SetText(SpellLabel(e.spell, e.rarity) .. "  " .. (rank > 0 and "|cff40ff40" or "|cffaaaaaa")
                .. rank .. "/" .. max .. "|r")
            w.tipLine = "Click: one rank more in the build. Right-click: one rank fewer."
            w:SetScript("OnClick", function(_, button)
                if button == "RightButton" then RemoveRank(tid) else AddRank(tid, max) end
            end)
        end
    end
end

-- Share and import ------------------------------------------------------------
-- One small window, two jobs: show a build's code ready to copy (and send it
-- to the party), or take a pasted code and open it in the editor.
do
    local W, PAD = 440, 18
    local S = CreateFrame("Frame", "ClasslessWildcardShare", UIParent)
    S:SetWidth(W); S:SetHeight(230)
    S:SetPoint("CENTER", UIParent, "CENTER", 0, 60)
    S:SetFrameStrata("DIALOG")
    S:SetToplevel(true)
    S:SetBackdrop({
        bgFile = "Interface\\Buttons\\WHITE8X8",
        edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
        tile = false, edgeSize = 32,
        insets = { left = 11, right = 12, top = 12, bottom = 11 },
    })
    S:SetBackdropColor(0.03, 0.03, 0.05, 0.96)
    S:EnableMouse(true)
    S:Hide()
    CW.shareWindow = S
    tinsert(UISpecialFrames, "ClasslessWildcardShare")

    S.title = S:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    S.title:SetPoint("TOPLEFT", PAD + 4, -20)
    S.sub = S:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    S.sub:SetPoint("TOPLEFT", S.title, "BOTTOMLEFT", 0, -6)
    S.sub:SetWidth(W - 2 * PAD - 8)
    S.sub:SetJustifyH("LEFT")
    S.sub:SetTextColor(0.75, 0.75, 0.75)

    S.boxBg = CreateFrame("Frame", nil, S)
    S.boxBg:SetPoint("TOPLEFT", PAD + 2, -64)
    S.boxBg:SetPoint("TOPRIGHT", -PAD - 2, -64)
    S.boxBg:SetHeight(90)
    S.boxBg:SetBackdrop({
        bgFile = "Interface\\Buttons\\WHITE8X8",
        edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
        tile = false, edgeSize = 12,
        insets = { left = 3, right = 3, top = 3, bottom = 3 },
    })
    S.boxBg:SetBackdropColor(0, 0, 0, 0.6)
    -- The code has no spaces, so the client wraps it mid-word and draws the
    -- selection at the unwrapped width, out of the window and across the
    -- panel. A scroll frame clips what it holds, so the box lives in one,
    -- with a width of its own to wrap to.
    S.clip = CreateFrame("ScrollFrame", nil, S.boxBg)
    S.clip:SetPoint("TOPLEFT", 8, -8)
    S.clip:SetPoint("BOTTOMRIGHT", -8, 8)
    S.box = CreateFrame("EditBox", "ClasslessWildcardShareBox", S.clip)
    S.box:SetWidth(W - 2 * (PAD + 2) - 16)
    S.box:SetHeight(90 - 16)
    S.clip:SetScrollChild(S.box)
    S.box:SetMultiLine(true)
    S.box:SetAutoFocus(false)
    S.box:SetFontObject(ChatFontNormal)
    S.box:SetMaxLetters(2000)
    S.box:SetScript("OnEscapePressed", function() S:Hide() end)

    S.error = S:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    S.error:SetPoint("TOPLEFT", PAD + 4, -160)
    S.error:SetWidth(W - 2 * PAD - 8)
    S.error:SetJustifyH("LEFT")

    S.go = CreateFrame("Button", nil, S, "UIPanelButtonTemplate")
    S.go:SetWidth(140); S.go:SetHeight(22)
    S.go:SetPoint("BOTTOMLEFT", PAD + 4, 18)
    S.done = CreateFrame("Button", nil, S, "UIPanelButtonTemplate")
    S.done:SetWidth(100); S.done:SetHeight(22)
    S.done:SetPoint("BOTTOMRIGHT", -PAD - 4, 18)
    S.done:SetScript("OnClick", function() S:Hide() end)

    -- share mode keeps the code as it is: a stray key press cannot damage it
    S.box:SetScript("OnTextChanged", function(self, user)
        if S.mode == "share" and user and self:GetText() ~= S.code then
            self:SetText(S.code)
            self:HighlightText()
        end
    end)

    local function Count(f)
        local n = f and f()
        return type(n) == "number" and n or 0
    end
    local function InRaid() return Count(GetNumRaidMembers) > 0 end
    local function InGroup() return InRaid() or Count(GetNumPartyMembers) > 0 end

    function CW.OpenShareWindow(mode, build)
        S.mode = mode
        S.error:SetText("")
        if mode == "share" then
            S.code = CW.EncodeBuild(build)
            S.title:SetText("Share " .. CW.CleanBuildText(build.name, 32))
            S.sub:SetText("The build's code. Press Ctrl+C to copy it, then paste it anywhere: chat, a forum, a friend.")
            S.box:SetText(S.code)
            S.go:SetText("Send to party")
            if InGroup() then S.go:Enable() else S.go:Disable() end
            S.go:SetScript("OnClick", function()
                CW.SendBuildToGroup(S.code)
                S.error:SetText("|cff00ff00Sent to your " .. (InRaid() and "raid" or "party") .. ".|r")
            end)
            S.done:SetText(CLOSE or "Close")
            S:Show()
            S.box:SetFocus()
            S.box:HighlightText()
        else
            S.code = nil
            S.title:SetText("Import a build")
            S.sub:SetText("Paste a build code (Ctrl+V). It opens in the editor, where you can check it and save it.")
            S.box:SetText("")
            S.go:SetText("Import")
            S.go:Enable()
            S.go:SetScript("OnClick", function()
                local build, why = CW.DecodeBuild(S.box:GetText())
                if not build then
                    S.error:SetText("|cffff5544" .. why .. "|r")
                    return
                end
                S:Hide()
                CW.OpenBuildEditor(build, nil)
            end)
            S.done:SetText(CANCEL or "Cancel")
            S:Show()
            S.box:SetFocus()
        end
    end

    -- ---- party and raid sharing ----------------------------------------------------
    -- A code goes out over the addon channel in numbered pieces; members with
    -- the addon put the pieces back together and are asked whether to look.
    local SHARE_PREFIX, PIECE = "CWSH", 200
    CW.SHARE_PREFIX = SHARE_PREFIX
    function CW.SendBuildToGroup(code)
        local channel = InRaid() and "RAID" or "PARTY"
        local n = math.ceil(#code / PIECE)
        for i = 1, n do
            SendAddonMessage(SHARE_PREFIX, i .. "/" .. n .. "/" .. code:sub((i - 1) * PIECE + 1, i * PIECE), channel)
        end
    end

    local incoming = {}
    function CW.ReceiveBuildPiece(sender, msg)
        if not sender or sender == UnitName("player") then return end
        local i, n, piece = (msg or ""):match("^(%d+)/(%d+)/(.*)$")
        i, n = tonumber(i), tonumber(n)
        if not i or not n or n < 1 or n > 20 or i > n then return end
        local box = incoming[sender]
        if not box or box.n ~= n or i == 1 then
            box = { n = n, pieces = {}, got = 0 }
            incoming[sender] = box
        end
        if not box.pieces[i] then box.got = box.got + 1 end
        box.pieces[i] = piece
        if box.got < n then return end
        incoming[sender] = nil
        local build = CW.DecodeBuild(table.concat(box.pieces))
        if not build then return end
        local dlg = StaticPopup_Show("CW_CLASSLESS_SHAREDBUILD", sender, build.name ~= "" and build.name or "a build")
        if dlg then dlg.data = build end
    end
end
-- help flyout ---------------------------------------------------------------
-- A scrollable "how it works" panel covering both systems. Static text, so it
-- is built once here; the Help button toggles it.
local helpFly = CreateFrame("Frame", "ClasslessWildcardHelp", frame)
-- the panel's own size and place: every flyout is a page over the panel
helpFly:SetWidth(frame:GetWidth()); helpFly:SetHeight(frame:GetHeight())
helpFly:SetPoint("CENTER", frame, "CENTER", 0, 0)
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
helpTitle:SetText("Hero Guide")

local helpCloseBtn = CreateFrame("Button", nil, helpFly, "UIPanelCloseButton")
helpCloseBtn:SetPoint("TOPRIGHT", -6, -6)
helpCloseBtn:SetScript("OnClick", function() helpFly:Hide() end)

local helpScroll = CreateFrame("ScrollFrame", "ClasslessWildcardHelpScroll", helpFly, "UIPanelScrollFrameTemplate")
helpScroll:SetPoint("TOPLEFT", 16, -44)
helpScroll:SetPoint("BOTTOMRIGHT", -34, 16)

local helpContent = CreateFrame("Frame", nil, helpScroll)
helpContent:SetWidth(880); helpContent:SetHeight(1)
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
        return "+" .. Rate(s.strMeleeAP or 2)
            .. " melee attack power, +0.5 block value"
    elseif i == 2 then
        local melee = (s.agiMeleeAP or 0) + (uni and (s.apPerAgi or 0) or 0)
        local ranged = (s.agiRangedAP or 1) + (uni and (s.rapPerAgi or 0) or 0)
        local ap
        if melee > 0 then
            ap = "+" .. Rate(melee) .. " melee and +" .. Rate(ranged) .. " ranged attack power"
        else
            ap = "+" .. Rate(ranged) .. " ranged attack power"
        end
        ap = ap .. ", +" .. Rate(tonumber(ARMOR_PER_AGILITY) or 2) .. " armor"
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

-- The core gives the first 20 points of Stamina and Intellect one point of
-- health or mana each, and every point after that the full rate. Every tooltip
-- in the addon quotes that rule, so the arithmetic behind it lives in one
-- place rather than being re-derived per caller.
-- On CW rather than as locals: this chunk is close to Lua 5.1's ceiling of 200
-- locals in one function, and these are read from two places.
CW.POOL = { SOFT = 20, HP_PER_STA = 10, MP_PER_INT = 15 }
function CW.Pooled(value, perPoint)
    if value <= CW.POOL.SOFT then return math.floor(value) end
    return CW.POOL.SOFT + math.floor((value - CW.POOL.SOFT) * perPoint)
end

-- EVERYTHING a stat is worth at `value`, as a list of short phrases, from the
-- server's own rates. This used to be StatContribution, which answered for
-- Strength, Agility and (spell power only) Intellect and nil for the other
-- two -- so three of the five rows on the stat panel had nothing to say about
-- themselves and Intellect under-reported what it was doing by two thirds.
function CW.StatEffects(i, value, short)
    local s = CW.stats
    local uni = s.uniStats
    local out = {}
    value = math.max(0, math.floor(value or 0))
    -- `short` uses the game's own abbreviations. At level 80 the spelled-out
    -- Agility line is 369px and the stat row has 312, so the row asks for the
    -- short form and the tooltip, which has all the space it wants, does not.
    local AP = short and " AP" or " attack power"
    local SP = short and " SP" or " spell power"
    local CRIT = short and "%% crit" or "%% critical strike"
    local SCRIT = short and "%% spell crit" or "%% spell critical strike"
    local PER5 = short and "/5s" or " per 5 sec"

    if i == 1 then
        out[#out + 1] = "+" .. math.floor(value * (s.strMeleeAP or 2)) .. " melee" .. AP
        -- Player::GetShieldBlockValue is (base + Strength x 0.5 - 10), floored
        -- at zero. The -10 is a flat offset the core applies once, and leaving
        -- it out overstated this line by ten at every Strength there is.
        out[#out + 1] = "+" .. math.max(0, math.floor(value * 0.5) - 10) .. " block value"
    elseif i == 2 then
        local melee = (s.agiMeleeAP or 0) + (uni and (s.apPerAgi or 0) or 0)
        local ranged = (s.agiRangedAP or 1) + (uni and (s.rapPerAgi or 0) or 0)
        if melee > 0 then
            out[#out + 1] = "+" .. math.floor(value * melee) .. " melee" .. AP
        end
        if ranged > 0 then
            out[#out + 1] = "+" .. math.floor(value * ranged) .. " ranged" .. AP
        end
        if (s.critPerAgi or 0) > 0 then
            out[#out + 1] = string.format("+%.2f" .. CRIT, value * s.critPerAgi)
        end
        -- Armour is the one thing the stock character sheet said about Agility
        -- that this did not, and the sheet reads these lines now. Long form
        -- only: the row this feeds is 312px and the spelled-out Agility line
        -- already runs to 369.
        if not short then
            out[#out + 1] = "+" .. math.floor(value * (tonumber(ARMOR_PER_AGILITY) or 2)) .. " armor"
        end
        -- Dodge is the one effect with no per-point number to give: the core
        -- runs Agility through diminishing returns that depend on class and
        -- level (Player::GetDodgeFromAgility), so there is no rate to quote and
        -- no client call for Agility's share alone. What CAN be shown is where
        -- the character stands, which is what the bare word "dodge" was not
        -- saying. Labelled a total, because base and defence are in it too.
        local dodge = GetDodgeChance and tonumber(GetDodgeChance())
        if dodge and not short then
            out[#out + 1] = string.format("dodge (%.2f%% total)", dodge)
        else
            out[#out + 1] = "dodge"
        end
    elseif i == 3 then
        out[#out + 1] = "+" .. CW.Pooled(value, CW.POOL.HP_PER_STA) .. " health"
    elseif i == 4 then
        out[#out + 1] = "+" .. CW.Pooled(value, CW.POOL.MP_PER_INT) .. " mana"
        local sp = uni and (s.spPerInt or 0) or 0
        if sp > 0 then
            -- the first 10 Intellect buy no spell power, the same shape the
            -- per-point line quotes
            out[#out + 1] = "+" .. math.floor(math.max(0, value - 10) * sp) .. SP
        end
        if (s.spellCritPerInt or 0) > 0 then
            out[#out + 1] = string.format("+%.2f" .. SCRIT, value * s.spellCritPerInt)
        end
    elseif i == 5 then
        if (s.mp5PerSpi or 0) > 0 then
            out[#out + 1] = string.format("+%.1f mana" .. PER5, value * s.mp5PerSpi)
            out[#out + 1] = string.format("+%.1f health" .. PER5, value * (s.hp5PerSpi or 0))
        else
            out[#out + 1] = "mana and health regeneration"
        end
    end
    return out
end

-- One line of the above, for anywhere that wants a sentence rather than a list.
function CW.StatContribution(i, value)
    local out = CW.StatEffects(i, value)
    if #out == 0 then return nil end
    return table.concat(out, ", ")
end

local function HelpKey()
    local key = GetBindingKey and GetBindingKey("CLASSLESSWILDCARD_TOGGLE")
    if key then
        return "|cffffff00" .. key .. "|r|cffaaaaaa, |r"
    end
    return ""
end

-- Armor weight for the guide: a line per armor type with what a FULL set
-- gives, worded the way the Armor Weight buff's hover text words it. Every
-- number is the realm's own, from its armor report; until that has arrived
-- the guide points at the buff instead of guessing.
function CW.ArmorWeightHelp()
    local out = {}
    local speed = {}
    for _, e in ipairs(CW.ARMOR_EFFECTS or {}) do speed[e[1]] = e[2] or false end
    for _, aura in ipairs({ 962043, 962044, 962045, 962046 }) do
        local data, text = (CW.armorWeight or {})[aura], (CW.ARMOR_WEIGHT_TEXT or {})[aura]
        if data and text then
            local parts = {}
            for i, label in ipairs(text.effects) do
                local full = data.full[i] or 0
                if full ~= 0 then
                    local word = string.lower(label)
                    if speed[label] then
                        parts[#parts + 1] = word .. " " .. math.abs(full) .. "% " .. (full < 0 and "slower" or "faster")
                    else
                        parts[#parts + 1] = word .. " " .. (full > 0 and "+" or "") .. full .. "%"
                    end
                end
            end
            if #parts > 0 then
                local name = string.upper(string.sub(text.armor, 1, 1)) .. string.sub(text.armor, 2)
                out[#out + 1] = "   |cffffd100" .. name .. ":|r " .. table.concat(parts, ", ") .. "."
            end
        end
    end
    if #out == 0 then
        out[1] = "   Hover the |cffffd100Armor Weight|r buff on your buff bar for this realm's numbers."
    end
    return out
end

-- The guide, as pages. Each page has an icon, a title, one line on what it
-- covers, and its blocks: a short heading and a paragraph under it, or a
-- grey note. Every number comes from the realm (CFG, S and the armor
-- report), never from here.
function CW.HelpSections()
    local r, s = CW.rules, CW.state
    local free = s.freeReroll or 10
    local cap = r.maxLevel
    local c = r.abilityCost
    local teByCap = math.max(0, cap - r.teStart + 1) * r.tePer
    local talentPrice = CW.talentFlat
        and ("Each talent costs " .. (CW.talentCost or 1) .. " TE, whatever rank you take it to.")
        or ("Each talent rank costs " .. (CW.talentCost or 1) .. " TE, so a 5-rank talent costs " .. 5 * (CW.talentCost or 1) .. " TE in full.")
    local cooldown = math.max(0, r.banRolls - 1)
    local deadline = s.deadline or 2
    local defaultPath = r.defaultMode == 1 and "Wildcard" or "Classless"
    local ICON = "Interface\\Icons\\"
    local sections = {}
    local function page(key, title, icon, summary, blocks)
        sections[#sections + 1] = { key = key, title = title, icon = icon, summary = summary, blocks = blocks }
    end
    local function b(head, text) return { head = head, text = text } end
    local function note(text) return { text = text, note = true } end

    page("start", "Start", "Interface\\AddOns\\ClasslessWildcard\\icon", "What a Hero is, and your first steps.", {
        b("You are a Hero", "Your race keeps its racial traits. Every ability and talent you earn yourself, and you can take it from |cffffffffany class in the game|r."),
        b("Two paths", "There are two ways to earn them, chosen once per character: |cff00ccffClassless|r, where you choose every ability, and |cffff8800Wildcard|r, where the dice deal them. Choose before level " .. deadline .. ", or you start on the " .. defaultPath .. " path. A character keeps the path it chooses."),
        b("Past the level cap", "At level " .. cap .. ", |cffffd100Rebirth|r starts a new life with a permanent rank, and a |cffffd100Challenge run|r is a life under one rule."),
        b("1.  Choose your path", "Choose when the choice appears, or later with the |cffffd100Choose path|r button on this panel."),
        b("2.  Place your stats", "Open |cffffd100Stats|r and place your first points. More arrive every level, and moving them is free."),
        b("3.  Get your first abilities", "|cff00ccffClassless:|r spend the |cff00ff00" .. r.startAE .. " Ability Essence|r you start with in the Abilities list.\n|cffff8800Wildcard:|r your |cffffd100Starting Hand|r of " .. r.wcStart .. " is dealt. Lock what you like and roll the rest, free until level " .. free .. "."),
        b("4.  Play", "Everything you own is in |cffffd100My Build|r and in your spellbook, and ranks up on its own as you level."),
        note("Everything here can also be done at the Hero Advancement NPC in every capital city, Dalaran and Shattrath. Open this panel with " .. HelpKey() .. "|cffffff00/cw|r|cffaaaaaa, or the dice button on your minimap. Rebind the key under Key Bindings > Hero Advancement.|r"),
    })

    page("classless", "Classless", ICON .. "INV_Misc_Book_11", "You choose every ability and talent, and pay with essence.", {
        b("Two currencies", "|cffffd100Ability Essence (AE)|r buys abilities. |cffffd100Talent Essence (TE)|r buys talent ranks.\nYou start with |cff00ff00" .. r.startAE .. " AE|r and earn |cff00ff00+" .. r.aePer .. " AE every level from " .. r.aeStart .. "|r. |cff00ff00Talent Essence arrives from level " .. r.teStart .. ", +" .. r.tePer .. " a level|r: " .. teByCap .. " by level " .. cap .. "."),
        b("Prices", "Abilities are priced by rarity: |cffffffff" .. c[1] .. "|r / |cff1eff00" .. c[2] .. "|r / |cff0070dd" .. c[3] .. "|r / |cffa335ee" .. c[4] .. "|r / |cffff8000" .. c[5] .. "|r AE from common to legendary. " .. talentPrice .. " Any talent can be taken without the talents above it, and each tier opens at its level."),
        b("Changing your mind", "Unlearning an ability refunds what you paid. |cffffd100Respec|r unlearns everything at once, free."),
        b("Ranks", "Every ability line you own |cff00ff00ranks up on its own|r as you level. Talents that teach a spell (Pyroblast, Mortal Strike, Mangle) are in the Abilities list instead, with every rank."),
        b("Archetypes", "Builds you follow from level 1 to " .. cap .. ". Pick one from the |cffffd100Archetypes|r button on this panel or at the Hero Advancement NPC. It replaces your build (abilities and talents refunded, free), then buys its abilities and talents for you as each becomes available. Everything it buys is a normal purchase, and you can stop following it at any time."),
        b("My Builds", "On the same page, |cffffd100My Builds|r keeps builds of your own, to follow yourself or to share with a friend as a code."),
    })

    page("wildcard", "Wildcard", ICON .. "INV_Misc_Dice_01", "The dice deal your abilities and talents. You steer your luck.", {
        b("The schedule", "|cff00ff00Level 1:|r " .. r.wcStart .. " random abilities to begin.\n|cff00ff00From level " .. r.wcRollStart .. ":|r one roll every level, alternating between an ability and a talent."),
        b("Rarity", "Rolls are weighted by rarity: a legendary is weighted " .. r.weightLegendary .. " against a common's " .. r.weightCommon .. ", so most of what you are dealt is common and a legendary is a real find. A roll only ever gives you something you do not already own, and it never replaces anything you have."),
        b("Talent ranks", "A talent roll also rolls the |cffffd100rank|r you land on, and the rank is its rarity: rank 1 common, rank 2 uncommon, rank 3 rare, rank 4 epic, |cffff8000rank 5 legendary|r. A talent you have never had can arrive at any rank up to its top one, for free."),
        b("Deepening a talent", "A roll never raises a rank you already hold. To push a talent higher, reroll it and stake |cffffd100Reroll Scrolls|r on it. The reroll costs its charge as usual and trades the talent for a new one; every extra scroll you stake buys a chance to keep it and raise its rank instead, possibly by more than one. If the stake fails the scrolls are spent and the talent is traded away. Use the circular arrow beside a talent in |cffffd100My Build|r."),
        b("Rerolls", "Rerolls are free below level " .. free .. ". From level " .. r.wcRollStart .. ", every level grants " .. r.rerollsPerLevel .. " reroll charges, spent on abilities or talents alike. Reroll from the roll reveal, or later from |cffffd100My Build|r with the circular arrow next to anything you own."),
        b("Locks", "While your Starting Hand is open, a padlock holds an ability back from |cffffd100Roll Abilities|r, which rerolls everything unlocked at once. At level " .. free .. " the padlocks come off: from then on you reroll one ability at a time, and only the one you choose."),
        b("Synergy", "Some rolls only offer abilities that share a class with something you already own. The chance starts at " .. r.synBase .. "% and climbs " .. r.synInc .. " points every time you reroll, then resets when a synergy roll lands."),
        b("Reroll cooldown", "Anything you reroll cannot come back for the next " .. cooldown .. " rolls, about " .. cooldown .. " levels. If everything you could use is owned or on cooldown, the cooldowns lift so you always get something usable."),
        b("Reroll Scrolls", "One scroll rerolls an ability or a talent once your charges run out. Buy them from level " .. free .. " at the Hero Advancement NPC or with |cffffd100Buy Scroll|r on this panel; the price rises with level."),
        note("Below level " .. free .. ", the dice crest at the top-left of this window reopens your Starting Hand."),
    })

    page("both", "Both paths", ICON .. "Spell_Arcane_ArcaneResilience", "What every Hero has, whichever path they walk.", {
        b("Universal resources", "You carry mana, rage and energy at once, and each spell draws its own. The extra bars sit under your player frame and remember where you drag them. |cffffd100Settings|r on this panel picks which to show, including runes and runic power; |cffffd100/cwbars|r toggles them all. Combo points show on your target's frame, as they do for a Rogue."),
        b("Primary stats", "You get points every level to spend across Strength, Agility, Stamina, Intellect and Spirit, and moving them is free at any time. Open |cffffd100Stats|r and hover a stat to see what it is doing for you right now. Each point gives:\n"
            .. "   |cffffd100Strength:|r " .. StatPerPoint(1) .. ".\n"
            .. "   |cffffd100Agility:|r " .. StatPerPoint(2) .. ".\n"
            .. "   |cffffd100Stamina:|r " .. StatPerPoint(3) .. ".\n"
            .. "   |cffffd100Intellect:|r " .. StatPerPoint(4) .. ".\n"
            .. "   |cffffd100Spirit:|r " .. StatPerPoint(5) .. ".\n"
            .. "Mana regeneration pauses for 5 seconds after you cast; Meditation, Arcane Meditation and Intensity let some of it continue."),
        b("Abilities that come as a set", "An ability that only works in a stance or form brings that form, and one that needs others brings those: Rend and Charge bring Battle Stance, Cat Form brings Claw and Prowl, Tame Beast brings Call Pet, Revive Pet, Feed Pet and Dismiss Pet. These extras are free, are not one of your rolls, and leave when nothing you own needs them."),
        b("Passives come with their abilities", "Death Knight spells strike for double on a critical, Flame Shock and Immolate can crit over time, Chaos Bolt goes through absorbs, and feral attack power works in Cat and Bear form. Nothing to buy or roll for."),
        b("Talents reach every class", "A talent that improves all of its class's abilities of one kind improves every ability of that kind, whichever class it comes from. Fire Power makes every Fire spell hit harder, Impale makes every melee strike crit harder, and Spiritual Healing strengthens every direct Holy heal. A talent that names particular spells, such as Improved Fireball, improves only those."),
        b("Tooltips count your talents", "Cost, cooldown, cast time, range, duration and values show what your build gives, talents from other classes included. An action button lights up only when you can pay what it costs."),
        b("Summons leave with their spell", "Reroll or unlearn Summon Imp and the imp is dismissed. Reroll Tame Beast away and the beast is stabled; own it again and the same beast returns. A tamed beast's pet talents open from the stock Talents button."),
        b("The Hero line", "Abilities that belong to no class, and a Hero talent tree of their own, in the pool beside everything else. The |cffffd100elemental variants|r are the physical strikes in seven elements, Fiery Heroic Strike to Holy Aimed Shot, each an ability of its own."),
        b("No class tools", "Spells that ask for a class item, such as Stoneskin Totem asking for an Earth Totem, cast without it. Reagents still apply."),
        b("Riding", "Trained for you, free: Apprentice at 20, Journeyman at 40, flying at 60, Northrend flying at 68 and epic flying at 70. Mounts are bought and earned as normal. The class mounts (Warhorse, Charger, Felsteed, Dreadsteed, Acherus Deathcharger) are abilities, so they come from a roll or from Ability Essence."),
    })

    local armor = CW.ArmorWeightHelp()
    page("gear", "Gear", ICON .. "INV_Chest_Plate04", "Wear anything. Each armor type is a trade.", {
        b("Proficiencies", "Every armor and weapon type, dual wield and Parry, from level 1. Weapon skills rise by use."),
        b("Armor weight", "Any Hero may wear any armor, and each type is a trade. Each piece in the eight armor slots counts toward its type, so a mixed set gets a share of each. A full set of:\n"
            .. table.concat(armor, "\n")
            .. "\nOne |cffffd100Armor Weight|r buff on your buff bar stands for all of it. Hover it to see each type you wear, what it gives now beside a full set, and everything added together."),
        b("Auto Shot", "Auto Shot is taught while a bow, gun or crossbow is equipped, and taken back when it comes off. While you know it, Attack switches to Auto Shot whenever your target is out of melee reach, so a bow worn only for its stats would hold your swings back. Shoot and Throw are always yours, and |cffffd100Settings|r can keep Auto Shot off whatever you wear."),
        b("Items", "Every item is open to every Hero: class armor sets, every glyph, poisons, soul bags, quivers and relics. The Hero Advancement NPC also sells classless items with stat mixes no class had, by level, and Hero heirlooms that grow with you from 1 to " .. cap .. ". Both drop in the world as well."),
        b("Starter kit", "A new Hero begins with a neutral outfit, a bag, a spread of basic weapons with ammunition, a shield, and food and water."),
        b("Class quests", "Every class quest chain is open to you. A reward that would teach a class ability gives nothing for that part; items, gold and reputation are paid as normal."),
    })

    page("rebirth", "Rebirth", ICON .. "Spell_Holy_Resurrection", "At level " .. cap .. ", start a new life with a rank that stays.", {
        b("Starting over", "At level " .. cap .. " the |cffffd100Rebirth|r button starts you over at level 1, at your race's starting area, on the same path."),
        b("What stays and what goes", "You choose whether your quest progress is wiped, so every quest pays XP again, or kept. Worn gear goes into your bags, or to your mailbox if they are full. Your gold, bank, reputation, riding and flight paths stay."),
        b("Your rank", "Each Rebirth raises a |cffffd100rank|r that is yours for good:\n   |cff00ff00+" .. r.xpFirst .. "% kill and dungeon XP|r for the first, +" .. r.xpPerRank .. "% more for each after, up to +" .. r.xpMax .. "%. Quest XP rises more gently.\n   |cff00ff00+" .. r.statPct .. "% to every primary stat|r per rank, up to +" .. r.statMax .. "%."),
        b("Heirlooms", "Carry one ability through, usable from level 1 and never rerolled or refunded. Each rank lets you carry one more."),
        b("Titles and essence", "A title per rank: the Reborn, the Twice Reborn, and so on. Classless Heroes start the new life with bonus Ability and Talent Essence per rank."),
        note("The price rises with each rank."),
    })

    page("challenges", "Challenges", ICON .. "Ability_Warrior_Challange", "A life under one rule.", {
        b("How a run works", "A run is a life under one rule, on your own path. Challenge runs start before level " .. deadline .. ". Pick a challenge, read its rule, go."),
        b("Lives", "Each challenge shows how many lives it gives. A death costs one, a fall or drowning included; deaths in battlegrounds and arenas, and while you are dueling, are free. Nemesis and Dealt Hand have unlimited lives. On Nemesis a death makes a nemesis instead, and the run finishes at level 80 with enough Vengeance."),
        b("Where to see them", "The hearts on the run badge at the top-right of this panel, and on the challenge tracker at the top of your screen. Hover either for your challenge's rule and rewards. The tracker also shows what your challenge is counting: the time left on the level on Hourglass, whether the hunter is on you on Pursued, your nemeses on Nemesis, and your health band on Berserker. Drag it to move it, click it for the challenge page, and hide or show it under Settings or with /cw tracker."),
        b("Nemesis", "The creature that kills you becomes your nemesis: a rare elite above your level, there for you alone, waiting where it lives. It is on your minimap and has an arrow over its head. Each has strengths and a weakness, learned by fighting it; die to it again and it grows. |cffffd100Swear Vendetta|r makes a nemesis of a creature you choose, stronger and worth more. Slaying one pays experience and |cffffd100Vengeance|r, its level, and drops a trophy that works from your bags for the rest of the run. Finish the run and your best trophies merge into your |cffffd100Nemesis Charm|r, which you keep."),
        b("Ending a run", "|cffffd100Running out|r ends the run: the rule lifts and you keep everything. A Rebirth ends a run too. |cffffd100Reaching " .. cap .. "|r with a life left finishes it. Your first finish of a challenge pays its gold, its title, and an ability no roll or shop can give, kept as an heirloom. Finish without a single death for |cffffd100the Unbroken|r, once per character."),
        b("Shards", "Every run pays them when it ends, finished or not: one per level reached, two per level past 60, and a third more for a run without a death. They buy an |cffffd100extra life|r for your next run, on the challenge page."),
    })
    return sections
end

-- Rendering. The page's list of sections runs down the left like the stock
-- Interface Options; the chosen one fills the right: its icon and title, a
-- line on what it covers, a rule, then its blocks in a scroll. Rebuilt
-- whenever the numbers it quotes arrive (CFG, the state, the armor report).
do
    local H = { heads = {}, bodies = {}, buttons = {}, sections = {}, current = 1 }
    CW.help = H
    helpFly:SetWidth(frame:GetWidth()); helpFly:SetHeight(frame:GetHeight())
    helpTitle:ClearAllPoints()
    helpTitle:SetPoint("TOP", 0, -16)
    helpTitle:SetText("Hero Guide")

    local NAV_X, NAV_W, TOP_Y = 18, 206, 48
    local CONTENT_X, CONTENT_W = NAV_X + NAV_W + 26, 610

    H.nav = CreateFrame("Frame", nil, helpFly)
    H.nav:SetWidth(NAV_W); H.nav:SetHeight(helpFly:GetHeight() - TOP_Y - 18)
    H.nav:SetPoint("TOPLEFT", NAV_X, -TOP_Y)
    H.nav:SetBackdrop(CW.CARD_BACKDROP)
    H.nav:SetBackdropColor(0.06, 0.06, 0.09, 0.9)
    H.nav:SetBackdropBorderColor(0.4, 0.4, 0.45)

    -- the chosen section's header
    H.icon = helpFly:CreateTexture(nil, "ARTWORK")
    H.icon:SetWidth(40); H.icon:SetHeight(40)
    H.icon:SetPoint("TOPLEFT", CONTENT_X + 6, -TOP_Y - 4)
    H.iconBorder = helpFly:CreateTexture(nil, "OVERLAY")
    H.iconBorder:SetWidth(68); H.iconBorder:SetHeight(68)
    H.iconBorder:SetPoint("CENTER", H.icon, "CENTER", 0, 0)
    H.iconBorder:SetTexture("Interface\\Buttons\\UI-Quickslot2")
    H.title = helpFly:CreateFontString(nil, "OVERLAY", "GameFontNormalHuge")
    H.title:SetPoint("TOPLEFT", H.icon, "TOPRIGHT", 14, 0)
    H.summary = helpFly:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    H.summary:SetPoint("TOPLEFT", H.title, "BOTTOMLEFT", 0, -4)
    H.summary:SetTextColor(0.75, 0.75, 0.75)
    H.rule = helpFly:CreateTexture(nil, "ARTWORK")
    H.rule:SetHeight(1)
    H.rule:SetPoint("TOPLEFT", CONTENT_X, -TOP_Y - 58)
    H.rule:SetWidth(CONTENT_W + 30)
    H.rule:SetTexture(1, 0.82, 0, 0.35)

    helpScroll:ClearAllPoints()
    helpScroll:SetPoint("TOPLEFT", CONTENT_X, -TOP_Y - 70)
    helpScroll:SetPoint("BOTTOMRIGHT", -40, 20)
    helpContent:SetWidth(CONTENT_W)

    -- the whole guide as one string, for anything that wants to read it
    function CW.HelpText()
        local out = {}
        for _, sec in ipairs(H.sections) do
            for _, blk in ipairs(sec.blocks) do
                if blk.head then out[#out + 1] = blk.head end
                out[#out + 1] = blk.text
            end
        end
        return table.concat(out, "\n")
    end

    -- one section onto the right-hand side
    function H.Show(index)
        local sec = H.sections[index]
        if not sec then return end
        H.current = index
        H.icon:SetTexture(nil)
        H.icon:SetTexture(sec.icon)
        if string.find(sec.icon, "\\Icons\\", 1, true) then
            H.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
        else
            H.icon:SetTexCoord(0, 1, 0, 1)
        end
        H.title:SetText(sec.title)
        H.summary:SetText(sec.summary)
        local y = 0
        for i, blk in ipairs(sec.blocks) do
            local head, body = H.heads[i], H.bodies[i]
            if not head then
                head = helpContent:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
                head:SetWidth(CONTENT_W); head:SetJustifyH("LEFT")
                body = helpContent:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
                body:SetWidth(CONTENT_W); body:SetJustifyH("LEFT"); body:SetJustifyV("TOP")
                body:SetSpacing(4)
                H.heads[i], H.bodies[i] = head, body
            end
            if blk.head then
                head:SetPoint("TOPLEFT", 0, -y)
                head:SetText(blk.head)
                head:Show()
                y = y + TextHeight(head) + 6
            else
                head:Hide()
            end
            body:SetPoint("TOPLEFT", 0, -y)
            if blk.note then
                body:SetTextColor(0.6, 0.6, 0.6)
            else
                body:SetTextColor(0.92, 0.92, 0.92)
            end
            body:SetText(blk.text)
            body:Show()
            y = y + TextHeight(body) + 20
        end
        for i = #sec.blocks + 1, #H.bodies do H.heads[i]:Hide(); H.bodies[i]:Hide() end
        helpContent:SetHeight(y + 8)
        helpScroll:SetVerticalScroll(0)
        for i, btn in ipairs(H.buttons) do
            if i == index then btn.selected:Show() else btn.selected:Hide() end
        end
    end

    function CW.RefreshHelpText()
        H.sections = CW.HelpSections()
        for i, sec in ipairs(H.sections) do
            local btn = H.buttons[i]
            if not btn then
                btn = CreateFrame("Button", nil, H.nav)
                btn:SetWidth(NAV_W - 16); btn:SetHeight(34)
                btn:SetPoint("TOPLEFT", 8, -10 - (i - 1) * 38)
                btn.selected = btn:CreateTexture(nil, "BACKGROUND")
                btn.selected:SetAllPoints(btn)
                btn.selected:SetTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight")
                btn.selected:SetBlendMode("ADD")
                btn.selected:SetVertexColor(1, 0.82, 0.2, 0.9)
                btn.selected:Hide()
                btn:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight", "ADD")
                btn.icon = btn:CreateTexture(nil, "ARTWORK")
                btn.icon:SetWidth(24); btn.icon:SetHeight(24)
                btn.icon:SetPoint("LEFT", 6, 0)
                btn.label = btn:CreateFontString(nil, "OVERLAY", "GameFontNormal")
                btn.label:SetPoint("LEFT", btn.icon, "RIGHT", 10, 0)
                btn:SetScript("OnClick", function(self)
                    if PlaySound then pcall(PlaySound, "igMainMenuOptionCheckBoxOn") end
                    H.Show(self.index)
                end)
                H.buttons[i] = btn
            end
            btn.index = i
            btn.icon:SetTexture(sec.icon)
            if string.find(sec.icon, "\\Icons\\", 1, true) then
                btn.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
            else
                btn.icon:SetTexCoord(0, 1, 0, 1)
            end
            btn.label:SetText(sec.title)
            btn:Show()
        end
        for i = #H.sections + 1, #H.buttons do H.buttons[i]:Hide() end
        H.Show(math.min(H.current, #H.sections))
    end
    CW.RefreshHelpText()
    -- the client drops textures it loaded before a cinematic: set them on show
    helpFly:HookScript("OnShow", function() CW.RefreshHelpText() end)
end
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

-- The button carries the count, so the panel does not have to be open to see
-- there are points waiting: "Stats (3)", and "Stats (0)" once they are spent.
-- Counted from the pending allocation rather than the server's number, so it
-- moves while points are being spent and always agrees with the panel's own
-- "N of M unspent" line.
local function UpdateStatsButton()
    local unspent = (CW.stats.budget or 0) - PendingSpent()
    if unspent < 0 then unspent = 0 end
    statsBtn:SetText("Stats (" .. unspent .. ")")
    -- a realm with stat allocation off has nothing to open
    if CW.stats.enabled == 0 then
        statsBtn:Hide()
        if CW.statFly then CW.statFly:Hide() end
    else
        statsBtn:Show()
    end
end
CW.UpdateStatsButton = UpdateStatsButton

local function UpdateStatus()
    UpdateStatsButton()
    local s = CW.state
    local modeText = s.mode == 0 and "|cff00ccffClassless|r" or (s.mode == 1 and "|cffff8800Wildcard|r" or "|cffff0000Path not chosen|r")
    -- The Rebirth rank rides next to the path, and the crest glows for it.
    if (s.rebirths or 0) > 0 then
        modeText = modeText .. "   |cffff8800Rebirth " .. s.rebirths .. "|r"
    end
    titleGlow:SetAlpha(CW.GlowBase())
    -- The challenge run rides in the top-right with its lives, and the
    -- bottom-right button says what it will do: Rebirth at the cap, a
    -- Challenge for a fresh Hero, and nothing in between. A path is for good.
    CW.UpdateLives()
    CW.rebirthBtn:SetText(s.rebirthReady == 1 and "Rebirth" or "Challenge")
    local rebirthOffered = (s.rebirth == 1 and s.rebirthReady == 1) or s.runReady == 1
    if s.mode == 0 then
        statusText:SetText(modeText .. "   Ability Essence: |cff00ff00" .. s.ae .. "|r   Talent Essence: |cff00ff00" .. s.te .. "|r")
        subStatusText:SetText("Level " .. s.level)
        bottomText:SetText("")
        respecBtn:Show()
        if rebirthOffered then CW.rebirthBtn:Show() else CW.rebirthBtn:Hide() end
        CW.buyScrollBtn:Hide()
        CW.archBtn:Show()
    elseif s.mode == 1 then
        statusText:SetText(modeText .. "   Reroll charges: |cff00ff00" .. s.rerolls .. "|r   Reroll Scrolls: |cff00ff00" .. s.scrolls .. "|r")
        subStatusText:SetText("Level " .. s.level .. "   Synergy chance: " .. s.chance .. "%")
        bottomText:SetText("")
        respecBtn:Hide()
        if rebirthOffered then CW.rebirthBtn:Show() else CW.rebirthBtn:Hide() end
        CW.archBtn:Hide(); CW.archFly:Hide()
        if s.scrollBuy == 1 then
            CW.buyScrollBtn:SetText("Buy Scroll  " .. GetCoinTextureString(s.scrollCost or 0))
            CW.buyScrollBtn:Show()
        else CW.buyScrollBtn:Hide() end
    else
        statusText:SetText(modeText)
        subStatusText:SetText("Choose your path before level " .. s.deadline .. ", or you start on the "
            .. (CW.rules.defaultMode == 1 and "Wildcard" or "Classless") .. " path.")
        respecBtn:Hide()
        CW.rebirthBtn:SetText("Choose path")
        CW.rebirthBtn:Show()
        CW.buyScrollBtn:Hide()
        CW.archBtn:Hide(); CW.archFly:Hide()
        bottomText:SetText("")
    end
end

-- What an empty pane says. A level filter emptying a list is the ordinary
-- case for a low-level character, so it names the way out.
function CW.ShowEmptyNote(note, firstRow, scope, what)
    if firstRow then
        note:Hide()
        return
    end
    note:SetText(scope == 1
        and ("|cffaaaaaaNo " .. what .. " at your level yet.\nSwitch to Any level to see the rest.|r")
        or ("|cffaaaaaaNo " .. what .. " match this filter.|r"))
    note:Show()
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
            if e.owned == 1 then w.check:Show() else w.check:Hide() end
            local lvlText = LevelTag(e.lvl, s.level)
            local typeTag = (CW.abilSort == 5 or CW.abilType ~= 1)
                and ("|cffaaaaaa" .. (CW.BROWSE.TYPE_NAMES[e.type or 0] or "") .. "|r  ") or ""
            -- the type tag already says Passive when it is shown
            w.name:SetText(SpellLabel(e.id, e.rarity)
                .. ((e.passive == 1 and typeTag == "") and " |cff888888(passive)|r" or ""))
            if s.mode == 1 then
                w.sub:SetText(typeTag .. (RARITY_NAMES[e.rarity] or "") .. lvlText)
                w.tipLine = "Dealt by Wildcard rolls"
                w:SetScript("OnClick", nil)
            else
                w.sub:SetText(typeTag .. e.cost .. " Ability Essence" .. lvlText)
                if e.owned == 1 then
                    w.tipLine = "Known"
                elseif s.mode ~= 0 then
                    w.tipLine = "Choose the Classless path to buy abilities."
                elseif (e.lvl or 1) > (s.level or 1) then
                    w.tipLine = "Requires level " .. e.lvl
                else
                    w.tipLine = "Click to learn"
                end
                local id = e.id
                w:SetScript("OnClick", function()
                    if s.mode == 0 and e.owned ~= 1 and (e.lvl or 1) <= (CW.state.level or 1) then
                        Send("BUY " .. id)
                    end
                end)
            end
            w:Show()
            -- the build editor's + button, while it is open
            if CW.BrowserRowHook then CW.BrowserRowHook(w, "A", e) end
        else
            w.spellId = nil
            w:Hide()
            if CW.BrowserRowHook then CW.BrowserRowHook(w, nil) end
        end
    end
    CW.ShowEmptyNote(CW.abilEmpty, CW.abilRows[1], CW.abilScope, "abilities")
end

-- Talent tree names, read out of the client's own TalentTab.dbc.
--
-- The server cannot send these: TalentTabEntry drops the name column in both
-- the struct and the DBC format string, so the core never loads it. The client
-- has the strings, and the addon runs on the client, so the table lives here.
-- 990 is the module's own Hero tab. Names repeat across classes -- two Holys,
-- two Protections, two Frosts -- which is why the class stays in the label.
CW.TREE_NAMES = {
    [41]  = "Fire",          [61]  = "Frost",         [81]  = "Arcane",
    [161] = "Arms",          [163] = "Protection",    [164] = "Fury",
    [181] = "Combat",        [182] = "Assassination", [183] = "Subtlety",
    [201] = "Discipline",    [202] = "Holy",          [203] = "Shadow",
    [261] = "Elemental",     [262] = "Restoration",   [263] = "Enhancement",
    [281] = "Feral Combat",  [282] = "Restoration",   [283] = "Balance",
    [301] = "Destruction",   [302] = "Affliction",    [303] = "Demonology",
    [361] = "Beast Mastery", [362] = "Survival",      [363] = "Marksmanship",
    [381] = "Retribution",   [382] = "Holy",          [383] = "Protection",
    [398] = "Blood",         [399] = "Frost",         [400] = "Unholy",
    [990] = "Hero",
}

CW.treeText = treeText        -- exposed so the harness can read the header

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
        local className = CLASS_NAMES[tabInfo.class] or "?"
        local treeName = CW.TREE_NAMES[tabInfo.id]
        -- "Hero: Hero" would be silly, and the Hero page has one tree anyway
        if treeName == className then treeName = nil end
        if treeName then
            treeText:SetText("|cffffd100" .. className .. ": " .. treeName
                .. "|r  |cffaaaaaa(" .. within .. " of " .. count .. ")|r")
        else
            treeText:SetText("|cffffd100" .. className
                .. " tree " .. within .. " of " .. count .. "|r")
        end
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
                w.tipLine = "Dealt by Wildcard rolls"
                w:SetScript("OnClick", nil)
            else
                -- price comes from the server (CFG): per rank by default,
                -- or one charge for all ranks when TalentFlatCost is on
                local cost = CW.talentCost or 1
                local costText = cost .. " Talent Essence"
                    .. (CW.talentFlat and " (all ranks)" or "/rank")
                w.sub:SetText(typeTag .. "Tier " .. (t.row + 1) .. "  " .. costText .. LevelTag(tlvl, s.level))
                if t.owned >= t.max then
                    w.tipLine = "Maxed"
                elseif s.mode ~= 0 then
                    w.tipLine = "Choose the Classless path to buy talents."
                elseif (tlvl or 1) > (s.level or 1) then
                    w.tipLine = "Requires level " .. tlvl
                else
                    w.tipLine = "Click to learn a rank"
                end
                local id = t.talentId
                w:SetScript("OnClick", function()
                    if s.mode == 0 and t.owned < t.max then Send("TALBUY " .. id) end
                end)
            end
            w:Show()
            if CW.BrowserRowHook then CW.BrowserRowHook(w, "T", t) end
        else
            w.spellId = nil
            w:Hide()
            if CW.BrowserRowHook then CW.BrowserRowHook(w, nil) end
        end
    end
    CW.ShowEmptyNote(CW.talEmpty, CW.talRows[1], CW.talScope, "talents")
end

-- A padlock holds a card back from the starting hand's roll-everything pass,
-- and nothing else. Once free rolls are over there is no such pass: every
-- reroll is one ability the player picked off this list, so a padlock has
-- nothing left to protect and would only refuse a reroll they asked for. The
-- server drops them all at that level; this is the same window, so the button
-- goes at the same moment.
-- A run that bars every reroll (Dealt Hand). The server refuses them; these
-- keep the buttons from offering one at all, and say why when one is pressed.
function CW.NoRerolls()
    return (CW.state.noRerolls or 0) == 1
end

function CW.SayNoRerolls()
    UIErrorsFrame:AddMessage("No rerolls on Dealt Hand. You play what you are dealt.", 1.0, 0.82, 0.0)
end

-- Padlocks only decide what a starting-hand reroll keeps, so with no rerolls
-- there is nothing for them to do.
function CW.LocksMatter()
    local s = CW.state
    return s.mode == 1 and (s.level or 1) < (s.freeReroll or 10) and not CW.NoRerolls()
end

-- Rerolling a talent trades it away for a new one. Staking extra Reroll
-- Scrolls on it buys a chance to keep it and raise its rank instead, so the
-- same button either widens the build or deepens it.
function CW.TalentUpgradeOdds(scrolls)
    local s = CW.state
    return math.min(100, (s.tuBase or 0) + (scrolls or 0) * (s.tuPerScroll or 0))
end

function CW.CanStakeScrolls()
    local s = CW.state
    return (s.tuPerScroll or 0) > 0 and (s.tuMaxScrolls or 0) > 0
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

CW.buildRows = buildRows

local function RenderBuild()
    local s = CW.state
    -- while a build is being edited, the column is the editor's
    if CW.buildEditor and CW.buildEditor:IsShown() then
        buildHeader:SetText("|cffffd100Build editor|r")
        for i = 1, BUILD_ROWS do buildRows[i]:Hide() end
        buildPrev:Hide(); buildNext:Hide(); buildPage:Hide()
        return
    end
    buildPrev:Show(); buildNext:Show(); buildPage:Show()
    local list = BuildList()
    buildHeader:SetText("|cffffd100My Build|r  |cffaaaaaa(" .. #CW.owned .. (#CW.owned == 1 and " ability, " or " abilities, ")
        .. #CW.ownedT .. (#CW.ownedT == 1 and " talent)|r" or " talents)|r"))
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
            -- Source 4 is an heirloom carried through Rebirth: it cost
            -- nothing this life, is never rerolled and never refunded, so it
            -- gets the same treatment, with its own note.
            local freebie = it.kind == "A" and (it.source == 2 or it.source == 3 or it.source == 4)
            r.note = nil
            if freebie then
                suffix = suffix .. (it.source == 4 and "  |cffff8800heirloom|r"
                                    or it.source == 3 and "  |cffaaaaaafree|r"
                                    or "  |cffaaaaaatalent|r")
                r.note = it.source == 4 and "Heirloom: carried through Rebirth, usable from level 1, never rerolled."
                    or it.source == 3 and "Came free with another ability, and leaves with it."
                    or "Came with a talent, and leaves with it."
            end
            r.name:SetWidth(freebie and (BUILD_W - 36) or (BUILD_W - 86))
            r.name:SetText(SpellLabel(it.spell, it.rarity) .. suffix)
            if freebie then
                r.lockBtn:Hide()
                r.actBtn:Hide()
            elseif s.mode == 1 then
                -- lock toggle (abilities only, and only while it does anything)
                -- + die reroll
                if it.kind == "A" and CW.LocksMatter() then
                    r.lockBtn:Show()
                    r.lockBtn.tex:SetTexture(it.locked == 1
                        and "Interface\\AddOns\\ClasslessWildcard\\lock_closed"
                        or  "Interface\\AddOns\\ClasslessWildcard\\lock_open")
                    r.lockBtn.tex:SetVertexColor(1, 1, 1, it.locked == 1 and 1 or 0.7)
                    -- the state we want, not a flip: see the hand's padlock
                    local id, want = it.id, (it.locked == 1) and 0 or 1
                    r.lockBtn:SetScript("OnClick", function()
                        Send("LOCK " .. id .. " " .. want)
                    end)
                    r.lockBtn:SetScript("OnEnter", function(self)
                        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
                        GameTooltip:SetText(want == 1 and "Lock this ability" or "Unlock this ability")
                        GameTooltip:AddLine(want == 1
                            and "A locked ability is never taken by a reroll."
                            or "An unlocked ability can be rerolled away.", 1, 1, 1, true)
                        GameTooltip:Show()
                    end)
                    r.lockBtn:SetScript("OnLeave", function() GameTooltip:Hide() end)
                else
                    r.lockBtn:Hide()
                end
                -- A locked ability cannot be rerolled, so it gets no die.
                -- Offering one put an action on screen the server was always
                -- going to refuse, which reads as the lock being ignored.
                -- On Dealt Hand nothing is rerolled, so no row gets one.
                if (it.kind == "A" and it.locked == 1 and CW.LocksMatter()) or CW.NoRerolls() then
                    r.actBtn:Hide()
                else
                    r.actBtn:Show()
                    r.actBtn.tex:SetTexture("Interface\\Buttons\\UI-RotationRight-Button-Up")
                    r.actBtn.tex:SetVertexColor(1, 0.85, 0.3)
                    local id, kind = it.id, it.kind
                    local tname, trank, tmax = SpellLabel(it.spell, it.rarity), it.rank, it.max
                    r.actBtn:SetScript("OnClick", function()
                        if kind == "T" then
                            CW.AskTalentReroll(id, tname, trank, tmax)
                        elseif CW.NoRerolls() then
                            CW.SayNoRerolls()
                        else
                            Send("RR " .. id)
                        end
                    end)
                    r.actBtn:SetScript("OnEnter", function(self)
                        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
                        GameTooltip:SetText("Reroll this " .. (kind == "T" and "talent" or "ability"))
                        local left = (CW.state.rerolls or 0) + (CW.state.scrolls or 0)
                        GameTooltip:AddLine("You have |cff00ff00" .. left .. "|r reroll" .. (left == 1 and "" or "s")
                            .. " (charges + scrolls).", 1, 1, 1)
                        -- a talent with a rank still to win can be kept instead
                        if kind == "T" and CW.CanStakeScrolls() and (trank or 0) < (tmax or 0) then
                            GameTooltip:AddLine("Trades it away for a new talent. Stake Reroll Scrolls "
                                .. "instead to keep this one and raise its rank.", 0.4, 1, 0.4, true)
                        end
                        GameTooltip:Show()
                    end)
                    r.actBtn:SetScript("OnLeave", function() GameTooltip:Hide() end)
                end
            else
                r.lockBtn:Hide()
                -- Classless: anything you bought, you can give back. A talent
                -- goes the same way an ability does, and the server refuses if
                -- another talent you own still stands on this one.
                r.actBtn:Show()
                r.actBtn.tex:SetTexture("Interface\\Buttons\\UI-GroupLoot-Pass-Up")
                r.actBtn.tex:SetVertexColor(1, 1, 1)
                local id, isTal = it.id, it.kind == "T"
                local ranks = it.rank or 0
                r.actBtn:SetScript("OnClick", function()
                    Send((isTal and "TALUNL " or "UNL ") .. id)
                end)
                r.actBtn:SetScript("OnEnter", function(self)
                    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
                    GameTooltip:SetText(isTal and "Unlearn this talent" or "Unlearn this ability")
                    if isTal then
                        GameTooltip:AddLine("Refunds the Talent Essence you paid"
                            .. ((not CW.talentFlat and ranks > 1) and (" for all " .. ranks .. " ranks.") or ".")
                            .. " Any ability it handed over goes with it.", 1, 1, 1, true)
                    else
                        GameTooltip:AddLine("Refunds the Ability Essence you paid.", 1, 1, 1)
                    end
                    GameTooltip:Show()
                end)
                r.actBtn:SetScript("OnLeave", function() GameTooltip:Hide() end)
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
-- What a tamed beast inherits from its owner, from spell_hun_generic_scaling,
-- which is bound to 34902-34904 in the world database and reads
-- GetUnitOwner()->GetOwner() with no class test at all -- so a Hero's pet
-- scales exactly as a Hunter's does.
--
-- These are NOT the client's numbers. Interface\FrameXML\PaperDollFrame.lua
-- carries HUNTER_PET_BONUS with 0.3 for Stamina, and the core gives 45%; its
-- ComputePetBonus is also hard-gated to Warlock and Hunter, so on any other
-- chassis it answers 0 and the lines never appear. Ours come from the server's
-- side of the same relationship.
--
-- Wild Hunt raises all three and cannot be seen from here, so these read as
-- the floor rather than the exact number a specced pet gets.
local PET_INHERITS = { STAMINA = 45, RANGED_AP = 22, SPELL_POWER = 12.87 }

-- A tamed beast, as opposed to a summoned one: happiness is a hunter-pet
-- concept and the API answers nil for anything else, which beats reading a
-- localised creature family name.
local function HasTamedPet()
    if not (UnitExists and UnitExists("pet")) then return false end
    return GetPetHappiness ~= nil and GetPetHappiness() ~= nil
end
CW.HasTamedPet, CW.PET_INHERITS = HasTamedPet, PET_INHERITS

local STAT_DESC = {
    [1] = "Melee attack power and block value.",
    [2] = "Melee and ranged attack power, critical strike chance, dodge.",
    [3] = "Health.",
    [4] = "Mana, spell power, spell critical strike chance.",
    [5] = "Mana and health regeneration. Mana regeneration pauses for 5 seconds after you cast.",
}

-- The same numbers the row shows, itemised. Both read CW.StatEffects, so the
-- row and its tooltip can never quote different figures.
local function ShowStatTooltip(row, i)
    local total, after, delta = CW.StatTotals(i)
    local s = CW.stats

    GameTooltip:SetOwner(row, "ANCHOR_RIGHT")
    GameTooltip:AddLine(STAT_NAMES[i], 1, 0.82, 0)
    GameTooltip:AddLine(STAT_DESC[i], 1, 1, 1, true)
    GameTooltip:AddLine(" ")
    GameTooltip:AddLine("Each point: " .. StatPerPoint(i), 1, 0.82, 0, true)

    GameTooltip:AddLine(" ")
    GameTooltip:AddDoubleLine("Total " .. STAT_NAMES[i], tostring(total), 0.8, 0.8, 0.8, 1, 1, 1)
    local applied = (s.alloc[i] or 0) * (s.perPoint or 1)
    if applied > 0 then
        GameTooltip:AddDoubleLine("   of which you allocated", "+" .. applied,
            0.6, 0.6, 0.6, 0.4, 1, 0.4)
    end
    for _, line in ipairs(CW.StatEffects(i, total)) do
        GameTooltip:AddDoubleLine(" ", line, 1, 1, 1, 0.4, 1, 0.4)
    end
    -- and what the pet takes from it
    if i == 3 and HasTamedPet() then
        GameTooltip:AddDoubleLine(" ", "+" .. math.floor(total * PET_INHERITS.STAMINA / 100)
            .. " pet Stamina", 1, 1, 1, 0.4, 1, 0.4)
    end

    if delta ~= 0 then
        GameTooltip:AddLine(" ")
        GameTooltip:AddDoubleLine("Pending (press Apply)",
            (delta > 0 and "+" or "") .. delta .. "  ->  " .. after,
            0.8, 0.8, 0.8, 1, 0.82, 0)
        for _, line in ipairs(CW.StatEffects(i, after)) do
            GameTooltip:AddDoubleLine(" ", line, 1, 1, 1, 1, 0.82, 0)
        end
    end
    GameTooltip:Show()
end
-- the stock character sheet shows this same tooltip; see the paper doll block
CW.ShowStatTooltip = ShowStatTooltip

-- The character's live total for a stat, and what it becomes if the pending
-- edits are applied. UnitStat's second return is the total the character sheet
-- shows, buffs and gear included.
function CW.StatTotals(i)
    local total = 0
    if UnitStat then
        local _, stat = UnitStat("player", i)
        total = tonumber(stat) or 0
    end
    local s = CW.stats
    local delta = ((PendingAlloc()[i] or 0) - (s.alloc[i] or 0)) * (s.perPoint or 1)
    return total, total + delta, delta
end

local function RenderStats()
    local pending = PendingAlloc()
    local spent = PendingSpent()
    local unspent = CW.stats.budget - spent
    statTitle:SetText("|cff00ff00" .. unspent .. "|r of " .. CW.stats.budget .. " unspent")
    local changed = false
    for i = 1, 5 do
        local r = statRows[i]
        local total, after, delta = CW.StatTotals(i)
        -- the total is the number the player cares about; the points they put
        -- in sit on the right, beside the buttons that move them
        local head = "|cffffd100" .. STAT_NAMES[i] .. "|r  |cffffffff" .. total .. "|r"
        -- the part of it the Rebirth bonus gives
        local reborn = CW.stats.rebirth and CW.stats.rebirth[i] or 0
        if reborn > 0 then head = head .. "  |cffff8800+" .. reborn .. " Rebirth|r" end
        if delta ~= 0 then
            head = head .. "  |cffffd100becomes " .. after .. "|r"
        end
        r.label:SetText(head)
        -- and what that total is worth, projected to the pending value so the
        -- numbers move while you are spending
        local effects = table.concat(CW.StatEffects(i, after, true), ", ")
        r.sub:SetText((delta ~= 0 and "|cffffd100" or "|cffcccccc") .. effects .. "|r")
        r.count:SetText(tostring(pending[i] or 0))
        -- a card with an edit waiting is picked out in gold
        if (pending[i] or 0) ~= (CW.stats.alloc[i] or 0) then
            changed = true
            r:SetBackdropBorderColor(1, 0.82, 0)
        else
            r:SetBackdropBorderColor(0.4, 0.4, 0.45)
        end
        if unspent > 0 then r.plus:Enable() else r.plus:Disable() end
        if (pending[i] or 0) > 0 then r.minus:Enable() else r.minus:Disable() end
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
        -- the +/- buttons sit on top of the card and would otherwise swallow
        -- the hover, leaving part of it tooltip-less
        r.plus:SetScript("OnEnter", function() ShowStatTooltip(r, i) end)
        r.plus:SetScript("OnLeave", function() GameTooltip:Hide() end)
        r.minus:SetScript("OnEnter", function() ShowStatTooltip(r, i) end)
        r.minus:SetScript("OnLeave", function() GameTooltip:Hide() end)
    end
    -- nothing to apply or undo until something has moved
    if changed then statApply:Enable(); statReset:Enable() else statApply:Disable(); statReset:Disable() end
    UpdateStatsButton()   -- the count moves as the points are spent
end

local function RenderList()
    UpdateClassStrip()
    RenderAbilPane()
    RenderTalPane()
    RenderBuild()
    if statFly:IsShown() then RenderStats() end
    UpdateStatus()
end
-- the lists and the My Build column from what is cached, no request: the
-- build editor redraws them as its draft changes
function CW.RenderBrowsers()
    RenderAbilPane()
    RenderTalPane()
    RenderBuild()
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
-- onboarding: the intro, then the path wizard
-- ---------------------------------------------------------------------------
-- Two top-level names only (the chunk sits at Lua 5.1's ceiling of 200
-- active locals): the wizard frame, read by the state handler, and
-- ShowPathChoice. Everything else lives on a table inside its block.
local wizard = CreateFrame("Frame", "ClasslessWildcardWizard", UIParent)
local ShowPathChoice
do
    local W = {}
    CW.wiz = W
    W.W, W.H = 560, 440          -- page 1: the two path cards
    W.ARCH_W = 560               -- page 2: two buttons per row beside the text
    wizard:SetWidth(W.W); wizard:SetHeight(W.H)
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

    -- The crest at the top, with the same soft glow the panel's title wears.
    -- Set on Show rather than once: the client purges every texture it loaded
    -- before a cinematic, and a new character's first sight of this is right
    -- after one.
    W.glow = wizard:CreateTexture(nil, "BORDER")      -- under the crest
    W.glow:SetWidth(96); W.glow:SetHeight(96)
    W.glow:SetPoint("TOP", 0, -2)
    W.glow:SetBlendMode("ADD")
    W.glow:SetVertexColor(1, 0.82, 0.3)
    W.glow:SetAlpha(0.7)
    W.crest = wizard:CreateTexture(nil, "ARTWORK")
    W.crest:SetWidth(46); W.crest:SetHeight(46)
    W.crest:SetPoint("TOP", 0, -24)
    function W.SetArt()
        W.crest:SetTexture(nil); W.glow:SetTexture(nil)
        W.crest:SetTexture("Interface\\AddOns\\ClasslessWildcard\\icon")
        W.glow:SetTexture("Interface\\AddOns\\ClasslessWildcard\\glow")
        for _, card in ipairs(W.cards or {}) do
            card.icon:SetTexture(nil)
            card.icon:SetTexture(card.iconPath)
            card.icon:SetTexCoord(unpack(card.iconCoords))
        end
    end
    wizard:SetScript("OnShow", W.SetArt)

    W.title = wizard:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    W.title:SetPoint("TOP", 0, -78)
    W.title:SetText("Choose Your Path, Hero")

    W.text = wizard:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    W.text:SetPoint("TOP", 0, -104)
    W.text:SetWidth(500)
    function CW.WizPathText()
        return "Every spell and talent of every class is open to you. Will you choose each ability yourself, "
            .. "or let the Wildcard deal them?"
    end
    W.text:SetText(CW.WizPathText())

    -- A path as a card: its icon and name, three lines on what it means, and
    -- the button that chooses it. The card lights up under the mouse so the
    -- two read as choices, not as paragraphs. `coords` crops the icon to the
    -- part worth showing: a spell icon's baked border, or the die in the
    -- lower half of the micro-menu button art (128 by 256, the die drawn at
    -- 18..112 across and 125..222 down).
    local function PathCard(side, name, rgb, iconPath, coords, lines, label)
        local card = CreateFrame("Button", nil, wizard)
        card:SetWidth(248); card:SetHeight(180)
        card:SetPoint(side == 1 and "TOPLEFT" or "TOPRIGHT", side == 1 and 24 or -24, -154)
        card:SetBackdrop({
            bgFile = "Interface\\Tooltips\\UI-Tooltip-Background",
            edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
            tile = true, tileSize = 16, edgeSize = 14,
            insets = { left = 3, right = 3, top = 3, bottom = 3 },
        })
        card:SetBackdropColor(0.05, 0.05, 0.08, 0.9)
        card:SetBackdropBorderColor(0.5, 0.5, 0.5)
        card.iconPath, card.iconCoords = iconPath, coords
        card.icon = card:CreateTexture(nil, "ARTWORK")
        card.icon:SetWidth(34); card.icon:SetHeight(34)
        card.icon:SetPoint("TOPLEFT", 16, -14)
        card.icon:SetTexture(iconPath)
        card.icon:SetTexCoord(unpack(coords))
        card.name = card:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
        card.name:SetPoint("LEFT", card.icon, "RIGHT", 8, 0)
        card.name:SetText(string.format("|cff%02x%02x%02x%s|r", math.floor(rgb[1] * 255), math.floor(rgb[2] * 255), math.floor(rgb[3] * 255), name))
        card.body = card:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        card.body:SetPoint("TOPLEFT", 16, -60)
        card.body:SetWidth(216)
        card.body:SetJustifyH("LEFT")
        card.body:SetSpacing(2)
        card.body:SetText(table.concat(lines, "\n"))
        card.button = CreateFrame("Button", nil, card, "UIPanelButtonTemplate")
        card.button:SetWidth(150); card.button:SetHeight(22)
        card.button:SetPoint("BOTTOM", 0, 14)
        card.button:SetText(label)
        local function lit(on)
            if on then card:SetBackdropBorderColor(rgb[1], rgb[2], rgb[3]) else card:SetBackdropBorderColor(0.5, 0.5, 0.5) end
        end
        card:SetScript("OnEnter", function() lit(true) end)
        card:SetScript("OnLeave", function() lit(false) end)
        card.button:SetScript("OnEnter", function() lit(true) end)
        card.button:SetScript("OnLeave", function() lit(false) end)
        card:SetScript("OnClick", function() card.button:Click() end)
        return card
    end
    W.cards = {
        PathCard(1, "Classless", { 0, 0.8, 1 }, "Interface\\Icons\\INV_Misc_Book_11", { 0.07, 0.93, 0.07, 0.93 }, {
            "You choose every ability and talent.",
            "Pay with the essence you earn each level.",
            "Follow a starter build, or make your own.",
        }, "Choose Classless"),
        PathCard(2, "Wildcard", { 1, 0.53, 0 }, "Interface\\AddOns\\ClasslessWildcard\\micro_die",
            { 18 / 128, 112 / 128, 125 / 256, 222 / 256 }, {
            "The dice deal your abilities and talents.",
            "Start with a hand of cards and reroll the ones you do not want.",
            "A rare roll is a real find.",
        }, "Choose Wildcard"),
    }
    W.classless, W.wildcard = W.cards[1].button, W.cards[2].button
    W.classless:SetScript("OnClick", function() Send("MODE 0"); Send("ARCH") end)
    W.wildcard:SetScript("OnClick", function()
        Send("MODE 1")
        wizard:Hide()
        -- the STARTING HAND opens next (pendingHand); the main panel waits
        -- until the player keeps their hand
    end)

    -- the window this has to be decided in, and what happens if it is not
    W.deadline = wizard:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    W.deadline:SetPoint("BOTTOM", 0, 54)
    W.deadline:SetWidth(500)
    W.deadline:SetTextColor(0.75, 0.75, 0.75)
    function W.DeadlineText()
        return "Choose before level " .. (CW.state.deadline or 2) .. ", or you start on the "
            .. (CW.rules.defaultMode == 1 and "Wildcard" or "Classless")
            .. " path. This character keeps the path it chooses."
    end

    W.later = CreateFrame("Button", nil, wizard, "UIPanelButtonTemplate")
    W.later:SetWidth(120); W.later:SetHeight(22)
    W.later:SetPoint("BOTTOM", 0, 18)
    W.later:SetText("Decide later")
    W.later:SetScript("OnClick", function() wizard:Hide() end)
    W.later:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_TOP")
        GameTooltip:SetText("Decide later")
        GameTooltip:AddLine("Close this for now. Open it again with the Choose path button on the Hero Advancement panel, "
            .. "or at the Hero Advancement NPC in any capital city.", 0.8, 0.8, 0.8, true)
        GameTooltip:Show()
    end)
    W.later:SetScript("OnLeave", function() GameTooltip:Hide() end)

    -- Page 2: archetype rows (shown after choosing Classless). The wizard grows
    -- to fit them and shrinks back when page 1 is shown again.
    W.list = MakeArchList(wizard, "ClasslessWildcardWizardArchetypes", W.ARCH_W - 40, "Choose")
    W.skip = CreateFrame("Button", nil, wizard, "UIPanelButtonTemplate")
    W.skip:SetWidth(180); W.skip:SetHeight(22)
    W.skip:SetPoint("BOTTOM", 0, 14)
    W.skip:SetText("Start with an empty slate")
    W.skip:Hide()
    W.skip:SetScript("OnClick", function()
        wizard:Hide()
        frame:Show()
        CW.SetTab("ABIL")
    end)

    function ShowPathChoice()
        wizard:SetWidth(W.W); wizard:SetHeight(W.H)
        W.title:ClearAllPoints(); W.title:SetPoint("TOP", 0, -78)
        W.text:ClearAllPoints(); W.text:SetPoint("TOP", 0, -104)
        W.title:SetText("Choose Your Path, Hero")
        W.text:SetWidth(500)
        W.text:SetText(CW.WizPathText())
        W.deadline:SetText(W.DeadlineText())
        W.deadline:Show()
        W.crest:Show(); W.glow:Show()
        for _, card in ipairs(W.cards) do card:Show() end
        W.later:Show()
        W.list.scroll:Hide()
        for _, r in ipairs(W.list.rows) do r:Hide() end
        W.skip:Hide()
        wizard:Show()
        if PlaySound then pcall(PlaySound, "igMainMenuOpen") end
    end

    function W.ShowArchetypeChoices()
        W.title:ClearAllPoints(); W.title:SetPoint("TOP", 0, -20)
        W.text:ClearAllPoints(); W.text:SetPoint("TOP", 0, -46)
        W.title:SetText("Pick a Starter Archetype")
        W.text:SetWidth(W.ARCH_W - 50)
        W.deadline:Hide()
        W.crest:Hide(); W.glow:Hide()
        for _, card in ipairs(W.cards) do card:Hide() end
        W.later:Hide()
        local list = CW.archetypes or {}
        if #list > 0 then
            W.text:SetText("An archetype is a build you follow: its abilities and talents are bought for you as you level, all the way to 80. Change or stop it later from the Archetypes button.")
        else
            W.text:SetText("No archetypes are available.")
        end
        wizard:SetWidth(W.ARCH_W)
        local top = 46 + TextHeight(W.text) + 14
        local shown, used = FillArchRows(W.list, list, function(arch)
            Send("ARCHAPPLY " .. arch.id)
            wizard:Hide()
            frame:Show()
            CW.SetTab("HERO")
        end, 20, top)
        wizard:SetHeight(top + math.max(used, ARCH_ROW_H) + 52)
        W.skip:Show()
        wizard:Show()
    end
    CW.wizard, CW.wizArchRows, CW.wizArchList, CW.wizArchSkip = wizard, W.list.rows, W.list, W.skip
    CW.wizClassless, CW.wizWildcard, CW.wizLater = W.classless, W.wildcard, W.later
    CW.wizTitle, CW.wizText, CW.wizDeadline, CW.wizCards = W.title, W.text, W.deadline, W.cards
    CW.ShowPathChoice = ShowPathChoice
    CW.ShowArchetypeChoices = W.ShowArchetypeChoices
end

-- The intro: what a brand-new Hero sees once, before the path wizard.
--
-- Staged like a cinematic. Letterbox bars close in over a darkened world and
-- three lines of narration come and go one at a time in the quest-book face.
-- Then the crest slams down: a flash, a kick, the starburst, rising embers and
-- the level-up chord. "You are a Hero" punches in with the achievement shine
-- swept across it, the scroll rule unrolls beneath, and the line that leads
-- into the path choice settles under that. The art and the font are the
-- client's own (Morpheus, the quest frame's rule, the achievement alert's
-- shine) beside the addon's crest, rays and glow.
--
-- A click during the narration skips to the crest; a click after the title
-- ends it, as does Escape at any point, and it ends on its own after the
-- timeline. Shown once per character; /cw intro replays it. A new character
-- arrives in the world inside the race cinematic, so the state packet that
-- would open the wizard waits for CINEMATIC_STOP, and the art is set at show
-- time: the client purges every texture it loaded before a cinematic.
do
    local I = {}
    CW.intro = I
    I.f = CreateFrame("Frame", "ClasslessWildcardIntro", UIParent)
    I.f:SetAllPoints(UIParent)
    I.f:SetFrameStrata("FULLSCREEN_DIALOG")
    I.f:EnableMouse(true)
    I.f:EnableKeyboard(true)
    I.f:Hide()

    I.MORPHEUS = "Fonts\\MORPHEUS.ttf"
    I.FRIZ = "Fonts\\FRIZQT__.TTF"
    I.ART = "Interface\\AddOns\\ClasslessWildcard\\"

    -- the world darkens, and the letterbox closes in over it
    I.dim = I.f:CreateTexture(nil, "BACKGROUND")
    I.dim:SetAllPoints(I.f)
    I.dim:SetTexture(0, 0, 0, 1)
    I.bars = {}
    for i, side in ipairs({ "TOP", "BOTTOM" }) do
        local bar = I.f:CreateTexture(nil, "BORDER")
        bar:SetTexture(0, 0, 0, 1)
        bar:SetPoint(side .. "LEFT", I.f, side .. "LEFT", 0, 0)
        bar:SetPoint(side .. "RIGHT", I.f, side .. "RIGHT", 0, 0)
        bar:SetHeight(1)
        I.bars[i] = bar
    end
    -- the flash of the landing, between the bars
    I.flash = I.f:CreateTexture(nil, "ARTWORK")
    I.flash:SetPoint("TOPLEFT", I.bars[1], "BOTTOMLEFT", 0, 0)
    I.flash:SetPoint("BOTTOMRIGHT", I.bars[2], "TOPRIGHT", 0, 0)
    I.flash:SetTexture(1, 0.85, 0.5, 1)
    I.flash:SetBlendMode("ADD")

    -- Everything that kicks on the landing rides this frame; the bars and the
    -- dark stay put. A child frame draws over all of its parent's layers.
    I.stage = CreateFrame("Frame", nil, I.f)
    I.stage:SetWidth(1); I.stage:SetHeight(1)
    I.stage:SetPoint("CENTER", I.f, "CENTER", 0, 0)

    local function Text(parent, face, size, r, g, b, y)
        local fs = parent:CreateFontString(nil, "OVERLAY", "GameFontNormal")
        fs:SetFont(face, size, "OUTLINE")
        fs:SetShadowColor(0, 0, 0, 1)
        fs:SetShadowOffset(2, -2)
        fs:SetTextColor(r, g, b)
        fs:SetPoint("CENTER", parent, "CENTER", 0, y)
        fs:SetWidth(1000)
        return fs
    end

    -- the narration, one line at a time
    I.BEATS = {
        { text = "Azeroth has known many champions.", t0 = 2.6, t1 = 6.0 },
        { text = "Each was bound to a single calling: warrior, mage, priest, rogue.", t0 = 6.4, t1 = 10.0 },
        { text = "You are bound to none.", t0 = 10.4, t1 = 12.6 },
    }
    I.beats = {}
    for i, beat in ipairs(I.BEATS) do
        local fs = Text(I.stage, I.MORPHEUS, i == 3 and 34 or 28, 1, 0.92, 0.75, 20)
        fs:SetText(beat.text)
        I.beats[i] = fs
    end

    -- the crest and its light
    local CREST_Y = 96
    local function Light(size, r, g, b)
        local t = I.stage:CreateTexture(nil, "ARTWORK")
        t:SetWidth(size); t:SetHeight(size)
        t:SetPoint("CENTER", I.stage, "CENTER", 0, CREST_Y)
        t:SetBlendMode("ADD")
        t:SetVertexColor(r, g, b)
        return t
    end
    -- all additive, so their order on the layer changes nothing
    I.rays = Light(220, 1, 0.82, 0.3)
    I.rays2 = Light(155, 1, 0.9, 0.6)
    I.glow = Light(75, 1, 0.85, 0.4)
    I.crest = I.stage:CreateTexture(nil, "OVERLAY")
    I.crest:SetPoint("CENTER", I.stage, "CENTER", 0, CREST_Y)
    I.CREST = 64             -- the crest at rest: icon.tga is 64x64, so this draws it 1:1

    -- embers rising from below the crest once it has landed
    I.EMBERS = 28
    I.embers = {}
    for i = 1, I.EMBERS do
        local e = I.stage:CreateTexture(nil, "ARTWORK")
        e:SetBlendMode("ADD")
        e:SetVertexColor(1, 0.7 + math.random() * 0.2, 0.3)
        I.embers[i] = e
    end

    -- the title punches in on a frame of its own, so it can be scaled
    I.TITLE_Y = 6
    I.titleFrame = CreateFrame("Frame", nil, I.stage)
    I.titleFrame:SetWidth(1); I.titleFrame:SetHeight(1)
    I.titleFrame:SetPoint("CENTER", I.stage, "CENTER", 0, I.TITLE_Y)
    I.title = Text(I.titleFrame, I.MORPHEUS, 58, 1, 0.82, 0.1, 0)
    I.title:SetText("You are a Hero")
    -- the achievement alert's shine, swept across the title once
    I.shine = I.titleFrame:CreateTexture(nil, "OVERLAY")
    I.shine:SetWidth(64); I.shine:SetHeight(78)
    I.shine:SetBlendMode("ADD")
    I.shine:SetTexCoord(0.78125, 0.912109375, 0, 0.28125)

    -- the quest frame's scroll rule, unrolled from the middle; drawn twice,
    -- the second copy in gold light, because the art itself is a dark bronze
    I.RULE_W, I.RULE_H = 420, 36
    I.RULE_COORD = { 23 / 256, 232 / 256, 7 / 32, 25 / 32 }
    I.rule, I.ruleLight = I.stage:CreateTexture(nil, "ARTWORK"), I.stage:CreateTexture(nil, "OVERLAY")
    for _, t in ipairs({ I.rule, I.ruleLight }) do
        t:SetPoint("CENTER", I.stage, "CENTER", 0, -32)
        t:SetHeight(I.RULE_H)
    end
    I.ruleLight:SetBlendMode("ADD")
    I.ruleLight:SetVertexColor(1, 0.8, 0.35)

    I.sub = Text(I.stage, I.FRIZ, 20, 1, 1, 1, -62)
    I.sub:SetText("Every class. Every spell. Every talent. Yours to claim.")
    I.question = Text(I.stage, I.MORPHEUS, 26, 1, 0.92, 0.75, -110)
    I.question:SetText("Will you forge your own power, or let the dice decide your fate?")

    -- in the bottom bar, the way a cinematic carries its subtitles
    I.hint = Text(I.f, I.FRIZ, 14, 0.75, 0.75, 0.75, 0)
    I.hint:ClearAllPoints()
    I.hint:SetPoint("CENTER", I.bars[2], "CENTER", 0, 0)

    -- the timeline, in seconds from the start
    I.T = {
        DIM = 1.6,          -- the world darkens and the bars close in, then a beat of quiet
        CREST = 12.3,       -- the crest starts its fall
        LAND = 12.75,       -- and lands: flash, kick, starburst, embers, sound
        KICK = 0.35,        -- how long the landing shakes the stage
        TITLE = 12.95,      -- "You are a Hero" punches in
        SHINE = 13.45,      -- the shine crosses it
        RULE = 13.9,        -- the rule unrolls
        SUB = 14.2,         -- the line under the rule
        QUESTION = 15.1,    -- and the question that leads to the choice
        HINT = 16.2,        -- the prompt changes from skip to continue
        AUTO = 30,          -- it ends on its own
        OUT = 0.8,          -- the fade to the wizard
    }
    I.SPIN = 0.04           -- turns per second
    I.rot = 0

    -- 3.3.5 has no Texture:SetRotation: a rotation is a rotated quad handed
    -- to SetTexCoord (rays.tga is transparent to its border, so the corners
    -- that sample outside it clamp to nothing).
    function I.Spin(tex, angle)
        local c, s = math.cos(angle), math.sin(angle)
        local function r(x, y) return 0.5 + x * c - y * s, 0.5 + x * s + y * c end
        local ax, ay = r(-0.5, -0.5)
        local bx, by = r(-0.5,  0.5)
        local cx, cy = r( 0.5, -0.5)
        local dx, dy = r( 0.5,  0.5)
        tex:SetTexCoord(ax, ay, bx, by, cx, cy, dx, dy)
    end

    function I.SetArt()
        for _, tex in ipairs({ I.rays, I.rays2, I.glow, I.crest, I.shine, I.rule, I.ruleLight }) do tex:SetTexture(nil) end
        I.rays:SetTexture(I.ART .. "rays")
        I.rays2:SetTexture(I.ART .. "rays")
        I.glow:SetTexture(I.ART .. "glow")
        I.crest:SetTexture(I.ART .. "icon")
        I.shine:SetTexture("Interface\\AchievementFrame\\UI-Achievement-Alert-Glow")
        I.shine:SetTexCoord(0.78125, 0.912109375, 0, 0.28125)
        I.rule:SetTexture("Interface\\QuestFrame\\UI-HorizontalBreak")
        I.ruleLight:SetTexture("Interface\\QuestFrame\\UI-HorizontalBreak")
        for _, e in ipairs(I.embers) do
            e:SetTexture(nil)
            e:SetTexture(I.ART .. "glow")
        end
    end

    -- 0 before t0, 1 after t0 + len, eased in between
    local function ramp(t, t0, len)
        if t <= t0 then return 0 end
        if t >= t0 + len then return 1 end
        local p = (t - t0) / len
        return p * p * (3 - 2 * p)
    end
    I.ramp = ramp

    -- an ember starts low and to one side of the crest, and rises
    local function Respawn(e, now)
        e.x = (math.random() * 2 - 1) * 260
        e.y = -170 + math.random() * 60
        e.speed = 26 + math.random() * 40
        e.sway = 6 + math.random() * 14
        e.phase = math.random() * 6.28
        e.life = 3 + math.random() * 3
        e.born = now
        local size = 5 + math.random() * 9
        e:SetWidth(size); e:SetHeight(size)
    end

    function I.Play(replay)
        if I.f:IsShown() then return end
        I.SetArt()
        I.phase = "in"
        I.t0 = GetTime()
        I.landed = nil
        I.replay = replay
        -- the bars are a share of the screen; a frame not laid out yet reads 0
        local height = I.f:GetHeight()
        if not height or height < 100 then height = 768 end
        I.BAR = math.floor(height * 0.11)
        I.f:SetAlpha(1)
        I.dim:SetAlpha(0)
        for _, bar in ipairs(I.bars) do bar:SetHeight(1) end
        I.flash:SetAlpha(0)
        I.rays:SetAlpha(0); I.rays2:SetAlpha(0); I.glow:SetAlpha(0)
        I.crest:SetAlpha(0); I.crest:SetWidth(I.CREST); I.crest:SetHeight(I.CREST)
        for _, fs in ipairs(I.beats) do fs:SetAlpha(0) end
        for _, e in ipairs(I.embers) do e:SetAlpha(0); e.born = nil end
        I.title:SetAlpha(0); I.shine:SetAlpha(0)
        I.titleFrame:SetScale(1)
        I.rule:SetAlpha(0); I.ruleLight:SetAlpha(0)
        I.sub:SetAlpha(0); I.question:SetAlpha(0)
        I.hint:SetText("Click to skip")
        I.hint:SetAlpha(0)
        I.f:Show()
    end

    -- the fade out; the wizard follows unless this was a replay
    function I.Finish()
        if I.phase ~= "in" then return end
        I.phase = "out"
        I.t0 = GetTime()
    end
    I.Skip = I.Finish

    -- a click in the narration jumps to the crest's fall, so the landing
    -- still plays; a click once the title is up ends it
    function I.Advance()
        local t = GetTime() - (I.t0 or GetTime())
        if t < 0.3 then return end          -- the click that opened the world
        if not I.landed then
            if t < I.T.CREST then I.t0 = GetTime() - I.T.CREST end
        elseif t >= I.T.TITLE then
            I.Finish()
        end
    end

    function I.Done()
        I.phase = nil
        I.f:Hide()
        I.f:SetAlpha(1)
        ClasslessWildcardCharDB = ClasslessWildcardCharDB or {}
        ClasslessWildcardCharDB.introSeen = true
        if not I.replay and CW.state.mode == 255 then ShowPathChoice() end
    end

    I.f:SetScript("OnUpdate", function(self, elapsed)
        local T = I.T
        local now = GetTime()
        local t = now - (I.t0 or now)
        if I.phase == "out" then
            self:SetAlpha(1 - ramp(t, 0, T.OUT))
            if t >= T.OUT then I.Done() end
            return
        end
        if I.phase ~= "in" then return end

        -- the dark and the letterbox
        local inn = ramp(t, 0, T.DIM)
        I.dim:SetAlpha(0.82 * inn)
        for _, bar in ipairs(I.bars) do bar:SetHeight(math.max(1, I.BAR * inn)) end

        -- the narration: each line rises a touch while it is up
        for i, beat in ipairs(I.BEATS) do
            local a = ramp(t, beat.t0, 1.0) * (1 - ramp(t, beat.t1 - 0.6, 0.6))
            local fs = I.beats[i]
            fs:SetAlpha(a)
            if a > 0 then
                fs:SetPoint("CENTER", I.stage, "CENTER", 0, 14 + 10 * ramp(t, beat.t0, beat.t1 - beat.t0))
            end
        end

        -- the fall: from high and large, accelerating into the landing
        if t >= T.CREST and not I.landed then
            local p = math.min(1, (t - T.CREST) / (T.LAND - T.CREST))
            local size = I.CREST + (1 - p * p * p) * 260
            I.crest:SetWidth(size); I.crest:SetHeight(size)
            I.crest:SetAlpha(math.min(1, p * 2))
        end
        if t >= T.LAND and not I.landed then
            I.landed = t
            I.crest:SetWidth(I.CREST); I.crest:SetHeight(I.CREST); I.crest:SetAlpha(1)
            if PlaySound then pcall(PlaySound, "LEVELUPSOUND") end
            if PlaySoundFile then pcall(PlaySoundFile, "Sound\\Spells\\Resurrection.wav") end
            for _, e in ipairs(I.embers) do
                Respawn(e, now)
                e.born = now - math.random() * e.life   -- already mid-flight, not all at once
            end
        end

        if I.landed then
            local since = t - T.LAND
            -- flash and kick
            I.flash:SetAlpha(0.45 * math.max(0, 1 - since / 0.6))
            if since < T.KICK then
                local k = 7 * (1 - since / T.KICK)
                I.stage:SetPoint("CENTER", I.f, "CENTER", (math.random() * 2 - 1) * k, (math.random() * 2 - 1) * k)
            else
                I.stage:SetPoint("CENTER", I.f, "CENTER", 0, 0)
            end
            -- the starburst, swelling in and breathing
            local up = ramp(since, 0, 0.5)
            local breathe = 1 + math.sin(now * 2.2) * 0.08
            I.rot = I.rot + (elapsed or 0) * I.SPIN * math.pi * 2
            I.Spin(I.rays, I.rot)
            I.Spin(I.rays2, -I.rot * 0.6)
            I.rays:SetAlpha(0.38 * breathe * up)
            I.rays2:SetAlpha(0.2 * (2 - breathe) * up)
            I.glow:SetAlpha(0.25 * up + 0.5 * math.max(0, 1 - since / 0.4))
            -- the embers
            for _, e in ipairs(I.embers) do
                local age = now - (e.born or now)
                if age > e.life then Respawn(e, now); age = 0 end
                local f = age / e.life
                e:SetPoint("CENTER", I.stage, "CENTER", e.x + math.sin(e.phase + age * 1.3) * e.sway, e.y + age * e.speed)
                e:SetAlpha(0.7 * math.sin(math.pi * f) * up)
            end
        end

        -- the title: punched in from large
        local tp = ramp(t, T.TITLE, 0.45)
        I.title:SetAlpha(tp)
        local scale = 1 + (1 - tp) * 0.35
        I.titleFrame:SetScale(scale)
        I.titleFrame:SetPoint("CENTER", I.stage, "CENTER", 0, I.TITLE_Y / scale)
        -- the shine crossing it
        local sp = (t - T.SHINE) / 0.8
        if sp > 0 and sp < 1 then
            local half = (I.title:GetStringWidth() or 300) / 2 + 30
            I.shine:SetPoint("CENTER", I.titleFrame, "CENTER", -half + 2 * half * sp, 0)
            I.shine:SetAlpha(math.sin(math.pi * sp))
        else
            I.shine:SetAlpha(0)
        end
        -- the rule, unrolled from its middle
        local rp = ramp(t, T.RULE, 0.6)
        if rp > 0 then
            local c = I.RULE_COORD
            local l, r = 0.5 - (0.5 - c[1]) * rp, 0.5 + (c[2] - 0.5) * rp
            for _, tex in ipairs({ I.rule, I.ruleLight }) do
                tex:SetWidth(math.max(1, I.RULE_W * rp))
                tex:SetTexCoord(l, r, c[3], c[4])
            end
            I.rule:SetAlpha(rp)
            I.ruleLight:SetAlpha(0.7 * rp)
        end
        I.sub:SetAlpha(ramp(t, T.SUB, 0.6))
        I.question:SetAlpha(ramp(t, T.QUESTION, 0.8))

        -- the prompt in the bottom bar
        if t >= T.HINT then
            if I.hint:GetText() ~= "Click to begin" then I.hint:SetText("Click to begin") end
            I.hint:SetAlpha(0.6 + 0.4 * math.sin((t - T.HINT) * 2.5))
        else
            I.hint:SetAlpha(0.6 * ramp(t, 3.2, 0.8) * (1 - ramp(t, T.CREST, 0.3)))
        end
        if t >= T.AUTO then I.Finish() end
    end)
    I.f:SetScript("OnMouseDown", function() I.Advance() end)
    I.f:SetScript("OnKeyDown", function(_, key) if key == "ESCAPE" then I.Finish() end end)

    -- the state packet arrived during the race cinematic: play when it ends
    function I.OnCinematicStop()
        if I.pending then
            I.pending = nil
            I.Play()
        end
    end

    -- What the state handler calls for an unchosen Hero inside the choosing
    -- window: the intro the first time, the wizard straight away after that.
    function CW.BeginOnboarding()
        ClasslessWildcardCharDB = ClasslessWildcardCharDB or {}
        if ClasslessWildcardCharDB.introSeen then
            ShowPathChoice()
            return
        end
        if I.f:IsShown() or I.pending then return end
        if CinematicFrame and CinematicFrame:IsShown() then
            I.pending = true
            return
        end
        I.Play()
    end
end

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
-- made the block look crooked: the rune row sat 14 from the left and 18 from
-- the right with its rings hanging up into the row above.
--
-- The pip sizes are taken from the client's own frames rather than from taste.
-- RuneFrame's button is 18x18 with the rune AND its ring both drawn at 24, so
-- the art is meant to overhang its cell; the old code drew the rune at 18 and
-- the ring at 26, which is why the two never sat together.
--
-- Combo points are not drawn here: the client patch opens them to every class,
-- so Blizzard's own ComboFrame on the target frame shows them, as for a Rogue.
local BARS = {
    W = 160, PAD = 7, TOP = 7, BOTTOM = 8, GAP = 6,
    BAR_H = 14, BAR_STEP = 17,
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
-- A HUD element: above the world, below the panel and every dialog.
barsFrame:SetFrameStrata("MEDIUM")
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
    if CW.LayoutPlayerDock then CW.LayoutPlayerDock() end   -- back in the stack
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

-- A hairline under the pools. Runes are not more resources, and with nothing
-- between them the block read as one long list of bars.
barsFrame.divider = barsFrame:CreateTexture(nil, "ARTWORK")
barsFrame.divider:SetTexture(1, 1, 1, 0.14)
barsFrame.divider:SetWidth(BARS.W - BARS.PAD * 2)
barsFrame.divider:SetHeight(1)
barsFrame.divider:Hide()

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

-- An invisible catcher so the rune row can answer a hover the way the bars
-- above it do, and can be dragged like the rest of the frame.
for _, key in ipairs({ "runeMouse" }) do
    local m = CreateFrame("Frame", nil, barsFrame)
    m:EnableMouse(true)
    m:Hide()
    m:SetScript("OnLeave", function() GameTooltip:Hide() end)
    CW.BarsDragProxy(m)
    barsFrame[key] = m
end
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

    if barsFrame.needRule then barsFrame.divider:Hide() end
    barsFrame.rowsShown = rows
    barsFrame:SetHeight(y + BARS.BOTTOM)
    return shown
end

-- Between layout passes: each shown pool's fill, and its number when it moves.
function CW.TickBarValues()
    if not barsFrame:IsShown() then return end
    local displayed = UnitPowerType("player")
    for _, bar in ipairs(powerBars) do
        if bar:IsShown() then
            local cur = UnitPower("player", bar.powerIndex) or 0
            if cur ~= bar.lastValue then
                bar.lastValue = cur
                bar:SetValue(cur)
                local marker = (bar.powerIndex == displayed) and "|cffffd100\194\187|r " or ""
                bar.label:SetText(marker .. bar.powerName .. ": " .. cur .. "/"
                    .. (UnitPowerMax("player", bar.powerIndex) or 0))
            end
        end
    end
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

-- ---------------------------------------------------------------------------
-- The stock character sheet, for a Hero who carries every pool at once
--
-- Interface\FrameXML\PaperDollFrame.lua gates three things on
-- UnitHasMana("player"), and that answers from the pool the client is SHOWING,
-- not from the ones the character has. A Hero has mana, rage and energy
-- together and shows one of them, so with the rage bar up the sheet says
-- Intellect does nothing at all (tooltip2 is set to nil outright), drops
-- Spirit's mana regen line, and prints "N/A" where Mana Regen goes. The mana
-- was there the whole time; only the question was wrong.
--
-- Every number below comes from the client's own API, the same calls Blizzard
-- makes on the other side of that `if`, so this restores what it would have
-- written rather than offering a second opinion about it. Gated on the
-- server's own universalResources flag, so a character the module leaves alone
-- keeps the stock sheet exactly as it is.
-- ---------------------------------------------------------------------------
do
    -- frame -> stat index, and which frames the pass being drawn touched
    local stamped, thisPass = {}, {}

    local function HaveRates()
        return CW.state and CW.state.universalResources == 1
            and CW.stats and CW.stats.have and CW.ShowStatTooltip
    end

    local function ManaIsHidden()
        return CW.state and CW.state.universalResources == 1
            and not (UnitHasMana and UnitHasMana("player"))
    end

    local function FixStat(statFrame, statIndex)
        if not statFrame then return end
        local _, effective = UnitStat("player", statIndex)
        effective = tonumber(effective) or 0

        -- Which stat this frame is showing, for the tooltip hook below. The
        -- same six frames are reused for Melee, Ranged, Spell and Defenses, so
        -- the stamp is cleared at the end of every pass and only survives on a
        -- frame this pass actually stamped.
        stamped[statFrame] = statIndex
        thisPass[statFrame] = true

        -- Before the server's first packet there are no rates, so fall back to
        -- repairing only what UnitHasMana threw away.
        if not ManaIsHidden() then return end
        if statIndex == 4 then
            local base = math.min(20, effective)
            local body = format(_G["DEFAULT_STAT4_TOOLTIP"] or "",
                                base + (effective - base) * (tonumber(MANA_PER_INTELLECT) or 15),
                                GetSpellCritChanceFromIntellect("player"))
            -- The body was nil'd, so anything still on the frame is the pet's
            -- Intellect line, which arrives already starting with a newline.
            statFrame.tooltip2 = body .. (statFrame.tooltip2 or "")
        elseif statIndex == 5 then
            local regen = math.floor((GetUnitManaRegenRateFromSpirit("player") or 0) * 5.0)
            statFrame.tooltip2 = (statFrame.tooltip2 or "")
                .. "\n" .. format(MANA_REGEN_FROM_SPIRIT or "", regen)
        end
    end

    local function FixManaRegen(statFrame)
        if not statFrame or not ManaIsHidden() then return end
        -- The server's own numbers first. GetManaRegen() reads a unit field
        -- at the slot for the power bar being SHOWN, and the core only ever
        -- writes the mana slot, so a Hero showing rage reads a slot nothing
        -- writes and gets 0 -- next to a character regenerating nine mana a
        -- second. These come straight off the field the core wrote.
        local base, casting = CW.stats.mp5, CW.stats.mp5Casting
        if base == nil then
            base, casting = GetManaRegen()
            base = (tonumber(base) or 0) * 5.0
            casting = (tonumber(casting) or 0) * 5.0
        end
        base = math.floor(tonumber(base) or 0)
        casting = math.floor(tonumber(casting) or 0)
        -- and if there is still no figure, leave Blizzard's "N/A" alone: it is
        -- a better answer than a confident "0 mana regenerated every 5 sec"
        if base <= 0 and casting <= 0 then return end
        local text = statFrame.GetName and _G[(statFrame:GetName() or "") .. "StatText"]
        if text then text:SetText(base) end
        statFrame.tooltip = HIGHLIGHT_FONT_COLOR_CODE .. MANA_REGEN .. FONT_COLOR_CODE_CLOSE
        statFrame.tooltip2 = format(MANA_REGEN_TOOLTIP or "", base, casting)
        statFrame:Show()
    end

    -- Ranged Attack Power carries two pet lines in the stock UI, and stock
    -- ComputePetBonus answers 0 for any chassis that is not Warlock or Hunter,
    -- so a Hero with a tamed beast never saw them (the client patch now edits
    -- that function, and these are written only where it has not). The
    -- relationship is real --
    -- spell_hun_generic_scaling gives the pet 22% of the owner's ranged attack
    -- power and 12.87% of it as spell power, with no class test -- so this
    -- writes the lines the row should have had, from the server's numbers.
    local function FixRangedAP(statFrame)
        if not statFrame or not (CW.state and CW.state.universalResources == 1) then return end
        if not CW.HasTamedPet() then return end
        -- The client patch teaches ComputePetBonus a Hero's pet, and then the
        -- stock code writes both lines itself (with the same 22% and 12.87%).
        if type(ComputePetBonus) == "function"
           and (tonumber(ComputePetBonus("PET_BONUS_RAP_TO_AP", 100)) or 0) > 0 then
            return
        end
        local base, pos, neg = UnitRangedAttackPower("player")
        local total = math.max(0, (tonumber(base) or 0) + (tonumber(pos) or 0)
                                  + (tonumber(neg) or 0))
        local ap = math.floor(total * CW.PET_INHERITS.RANGED_AP / 100)
        local sp = math.floor(total * CW.PET_INHERITS.SPELL_POWER / 100)
        local lines = { statFrame.tooltip2 }
        if PET_BONUS_TOOLTIP_RANGED_ATTACK_POWER then
            lines[#lines + 1] = format(PET_BONUS_TOOLTIP_RANGED_ATTACK_POWER, ap)
        end
        if PET_BONUS_TOOLTIP_SPELLDAMAGE then
            lines[#lines + 1] = format(PET_BONUS_TOOLTIP_SPELLDAMAGE, sp)
        end
        statFrame.tooltip2 = table.concat(lines, "\n")
    end

    CW.FixPaperDollStat, CW.FixPaperDollManaRegen = FixStat, FixManaRegen
    CW.FixPaperDollRangedAP = FixRangedAP

    -- The sheet's own tooltip is one line of Blizzard's text. This is the
    -- module's, the same one the Stats panel shows: what the stat is, what a
    -- point of it buys HERE, the character's total, and every effect that
    -- total is worth. One tooltip, in both places, from one function.
    local function FullTooltip(statFrame)
        local i = statFrame and stamped[statFrame]
        if not i or not HaveRates() then return end
        CW.ShowStatTooltip(statFrame, i)
    end

    -- A pass over the six rows is finished. UpdatePaperdollStats reuses the
    -- same frames for Melee, Ranged, Spell and Defenses, so a row this pass did
    -- NOT set as a stat is Attack Power or Dodge or Armor now, and must stop
    -- answering as Agility.
    local function ClearStamps(prefix)
        if type(prefix) ~= "string" then return end
        for i = 1, 6 do
            local f = _G[prefix .. i]
            if f and not thisPass[f] then stamped[f] = nil end
        end
        for f in pairs(thisPass) do thisPass[f] = nil end
    end

    if hooksecurefunc then
        if type(PaperDollFrame_SetStat) == "function" then
            hooksecurefunc("PaperDollFrame_SetStat", FixStat)
        end
        if type(PaperDollFrame_SetManaRegen) == "function" then
            hooksecurefunc("PaperDollFrame_SetManaRegen", FixManaRegen)
        end
        if type(PaperDollStatTooltip) == "function" then
            hooksecurefunc("PaperDollStatTooltip", FullTooltip)
        end
        if type(UpdatePaperdollStats) == "function" then
            hooksecurefunc("UpdatePaperdollStats", ClearStamps)
        end
        if type(PaperDollFrame_SetRangedAttackPower) == "function" then
            hooksecurefunc("PaperDollFrame_SetRangedAttackPower", FixRangedAP)
        end
    end

    -- universalResources is 0 until the server's first state packet lands, so
    -- a sheet opened before it arrives was drawn from the wrong answer. Redraw
    -- it once, when the answer changes.
    function CW.RefreshPaperDoll()
        if PaperDollFrame and PaperDollFrame:IsShown()
           and type(PaperDollFrame_UpdateStats) == "function" then
            PaperDollFrame_UpdateStats()
        end
    end
end

-- The tick lives on its own always-shown frame rather than on the bar frame.
-- The bar frame hides itself when it has nothing to draw -- every row off --
-- and a hidden frame gets no
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
    elseif CW.TickBarValues then
        -- the client predicts every pool between server updates (the regen
        -- patch), so the fill follows it each frame like the stock bar does
        CW.TickBarValues()
    end
end)

-- ---------------------------------------------------------------------------
-- talent reroll: trade it away, or stake scrolls on its rank
-- ---------------------------------------------------------------------------
do
    -- On UIParent, not the panel: it is offered from the roll reveal too, and
    -- the reveal shows with the panel closed, where a child of a hidden frame
    -- cannot appear at all.
    local fly = CreateFrame("Frame", "ClasslessWildcardTalentReroll", UIParent)
    fly:SetWidth(360); fly:SetHeight(200)
    fly:SetPoint("CENTER", UIParent, "CENTER", 0, 0)
    fly:SetFrameStrata("FULLSCREEN_DIALOG")
    fly:SetBackdrop({
        bgFile = "Interface\\Buttons\\WHITE8X8",
        edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
        tile = false, edgeSize = 14,
        insets = { left = 4, right = 4, top = 4, bottom = 4 },
    })
    fly:SetBackdropColor(0.03, 0.03, 0.05, 0.97)
    fly:EnableMouse(true)
    fly:Hide()
    CW.talentRerollFly = fly

    fly.title = fly:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    fly.title:SetPoint("TOP", 0, -12)

    fly.body = fly:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    fly.body:SetPoint("TOPLEFT", 16, -36)
    fly.body:SetWidth(328)
    fly.body:SetJustifyH("LEFT")

    fly.stake = fly:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    fly.stake:SetPoint("TOP", 0, -96)

    fly.minus = CreateFrame("Button", nil, fly, "UIPanelButtonTemplate")
    fly.minus:SetWidth(26); fly.minus:SetHeight(22)
    fly.minus:SetPoint("TOP", -110, -92)
    fly.minus:SetText("-")
    fly.plus = CreateFrame("Button", nil, fly, "UIPanelButtonTemplate")
    fly.plus:SetWidth(26); fly.plus:SetHeight(22)
    fly.plus:SetPoint("TOP", 110, -92)
    fly.plus:SetText("+")

    fly.go = CreateFrame("Button", nil, fly, "UIPanelButtonTemplate")
    fly.go:SetWidth(150); fly.go:SetHeight(22)
    fly.go:SetPoint("BOTTOMLEFT", 16, 14)
    fly.cancel = CreateFrame("Button", nil, fly, "UIPanelButtonTemplate")
    fly.cancel:SetWidth(150); fly.cancel:SetHeight(22)
    fly.cancel:SetPoint("BOTTOMRIGHT", -16, 14)
    fly.cancel:SetText("Cancel")
    fly.cancel:SetScript("OnClick", function() fly:Hide() end)

    function CW.RenderTalentReroll()
        local s = CW.state
        local n = fly.scrolls or 0
        local max = math.min(s.tuMaxScrolls or 0, s.scrolls or 0)
        if n > max then n = max; fly.scrolls = n end
        local odds = CW.TalentUpgradeOdds(n)

        fly.title:SetText("Reroll " .. (fly.talentName or "this talent"))
        fly.body:SetText("A reroll trades this talent away and the Wildcard deals you a new one "
            .. "in its place. Stake Reroll Scrolls on it instead and they buy a chance to |cffffd100keep|r "
            .. "it and raise its rank. If the stake fails, it is traded away as normal.\n\n"
            .. "You have |cff00ff00" .. (s.scrolls or 0) .. "|r Reroll Scroll"
            .. (((s.scrolls or 0) == 1) and "" or "s")
            .. ". Up to |cffffd100" .. (s.tuMaxScrolls or 0) .. "|r can be staked on one reroll."
            .. (s.scrollBuy == 1 and " Buy more with Buy Scroll on the Hero Advancement panel." or ""))
        if max > 0 then
            fly.stake:SetText("Stake |cffffd100" .. n .. "|r  =  |cff00ff00" .. odds .. "%|r to raise its rank")
        else
            -- nothing to stake, so say what one WOULD buy: that is the whole
            -- reason to go and get some
            fly.stake:SetText("|cffaaaaaaOne scroll would buy |r|cff00ff00"
                .. CW.TalentUpgradeOdds(1) .. "%|cffaaaaaa to raise its rank|r")
        end
        fly.minus:Show(); fly.plus:Show()
        if n > 0 then fly.minus:Enable() else fly.minus:Disable() end
        if n < max then fly.plus:Enable() else fly.plus:Disable() end
        fly.go:SetText(n > 0 and ("Reroll + " .. n) or "Reroll")
    end

    fly.plus:SetScript("OnClick", function()
        fly.scrolls = (fly.scrolls or 0) + 1
        CW.RenderTalentReroll()
    end)
    fly.minus:SetScript("OnClick", function()
        fly.scrolls = math.max(0, (fly.scrolls or 0) - 1)
        CW.RenderTalentReroll()
    end)
    fly.go:SetScript("OnClick", function()
        Send("RRT " .. fly.talentId .. " " .. (fly.scrolls or 0))
        local sent = fly.onSent
        fly.onSent = nil
        fly:Hide()
        if sent then sent() end
    end)

    -- A maxed talent has no rank left to win, so the stake is not offered and
    -- the reroll goes straight out.
    -- Opens for any talent that still has a rank to win, whether or not the
    -- Hero has a scroll to stake. Skipping it when they had none hid the whole
    -- mechanic from everyone who had not already bought scrolls, which is
    -- everyone who has not yet been told what scrolls are for.
    -- `onSent` runs once the reroll has actually gone out, so the caller can
    -- react. The roll reveal uses it to hold itself open for the replacement.
    function CW.AskTalentReroll(talentId, name, rank, maxRank, onSent)
        if CW.NoRerolls() then
            CW.SayNoRerolls()
            return
        end
        if not CW.CanStakeScrolls() or (rank or 0) >= (maxRank or 0) then
            Send("RRT " .. talentId .. " 0")
            if onSent then onSent() end
            return
        end
        CW.helpFly:Hide(); CW.statFly:Hide(); CW.archFly:Hide(); CW.setFly:Hide()
        fly.talentId, fly.talentName, fly.scrolls = talentId, name, 0
        fly.onSent = onSent
        CW.RenderTalentReroll()
        -- above the reveal when it is the reveal asking
        if CW.revealFrame and CW.revealFrame:IsShown() then
            fly:SetFrameLevel(CW.revealFrame:GetFrameLevel() + 10)
        end
        fly:Show()
    end
end

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
          tip = "The mini-bars under your player frame. Drag them anywhere you like." },
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
    fly:SetWidth(frame:GetWidth()); fly:SetHeight(frame:GetHeight())
    fly:SetPoint("CENTER", frame, "CENTER", 0, 0)
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

    fly.title = fly:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    fly.title:SetPoint("TOP", 0, -16)
    fly.title:SetText("Settings")
    fly.close = CreateFrame("Button", nil, fly, "UIPanelCloseButton")
    fly.close:SetPoint("TOPRIGHT", -6, -6)
    fly.close:SetScript("OnClick", function() fly:Hide() end)

    -- Laid out as boxed groups on two columns: the resource bars on the
    -- left, the tracker and abilities stacked on the right. Each group says
    -- where it is kept, since some settings follow the character and some
    -- the computer. A group's box is sized once its contents are placed.
    local LEFT, RIGHT, COL_W, TOP = 60, 490, 400, 64
    local function Group(x, y, title, note)
        local g = CreateFrame("Frame", nil, fly)
        g:SetWidth(COL_W)
        g:SetPoint("TOPLEFT", x, -y)
        g:SetBackdrop({
            bgFile = "Interface\\Tooltips\\UI-Tooltip-Background",
            edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
            tile = true, tileSize = 16, edgeSize = 14,
            insets = { left = 3, right = 3, top = 3, bottom = 3 },
        })
        g:SetBackdropColor(0.08, 0.08, 0.12, 0.85)
        g:SetBackdropBorderColor(0.45, 0.45, 0.5)
        g.title = g:CreateFontString(nil, "OVERLAY", "GameFontNormal")
        g.title:SetPoint("TOPLEFT", 16, -14)
        g.title:SetText(title)
        g.note = g:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        g.note:SetPoint("TOPLEFT", 16, -32)
        g.note:SetTextColor(0.6, 0.6, 0.6)
        g.note:SetText(note)
        return g
    end
    -- a checkbox inside a group at (x, y) from the group's top-left
    local function Check(g, name, x, y, label, tip, onClick)
        local cb = CreateFrame("CheckButton", name, g, "UICheckButtonTemplate")
        cb:SetWidth(24); cb:SetHeight(24)
        cb:SetPoint("TOPLEFT", x, -y)
        local text = _G[name .. "Text"]
        if text then text:SetText(label) end
        cb:SetScript("OnClick", onClick)
        cb:SetScript("OnEnter", function(self)
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:AddLine(label)
            GameTooltip:AddLine(tip, 1, 1, 1, true)
            GameTooltip:Show()
        end)
        cb:SetScript("OnLeave", function() GameTooltip:Hide() end)
        return cb
    end
    local function Button(g, x, y, text, tip, onClick)
        local b = CreateFrame("Button", nil, g, "UIPanelButtonTemplate")
        b:SetWidth(180); b:SetHeight(22)
        b:SetPoint("TOPLEFT", x, -y)
        b:SetText(text)
        b:SetScript("OnClick", onClick)
        b:SetScript("OnEnter", function(self)
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:AddLine(text)
            GameTooltip:AddLine(tip, 1, 1, 1, true)
            GameTooltip:Show()
        end)
        b:SetScript("OnLeave", function() GameTooltip:Hide() end)
        return b
    end

    fly.subtitle = fly:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    fly.subtitle:SetPoint("TOP", 0, -40)
    fly.subtitle:SetTextColor(0.7, 0.7, 0.7)
    fly.subtitle:SetText("Hover any setting for what it does.")

    -- Resource bars: the frame itself, then a row per pool in two columns
    local checks = {}
    local bars = Group(LEFT, TOP, "Resource bars", "Saved on this computer, for every character.")
    fly.barsGroup = bars
    local y, pools = 56, 0
    for i, row in ipairs(ROWS) do
        if row.head == "Show a bar for" then
            y = y + 8
            local h = bars:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
            h:SetPoint("TOPLEFT", 16, -y)
            h:SetText("|cffffd100" .. row.head .. "|r")
            y = y + 20
        elseif not row.head then
            local x, at = 18, y
            if row.key ~= "frame" and row.key ~= "lock" then
                -- the pools sit two to a line, so six rows take three lines
                x = 18 + (pools % 2) * 180
                at = y + math.floor(pools / 2) * 26
                pools = pools + 1
            end
            local cb = Check(bars, "ClasslessWildcardSetting" .. i, x, at, row.label, row.tip, function(self)
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
            cb.rowKey = row.key
            checks[#checks + 1] = cb
            if row.key == "frame" or row.key == "lock" then y = y + 26 end
        end
    end
    y = y + math.ceil(pools / 2) * 26 + 12
    Button(bars, 18, y, "Reset bar position", "Puts the bars back under the player frame.",
        function() CW.ResetBarsPosition() end)
    bars:SetHeight(y + 22 + 18)

    -- Challenge tracker
    local tracker = Group(RIGHT, TOP, "Challenge tracker", "Saved on this computer, for every character.")
    fly.trackerGroup = tracker
    fly.trackerCheck = Check(tracker, "ClasslessWildcardSettingTracker", 18, 56, "Show the tracker",
        "The frame at the top of the screen during a challenge run: your lives, and what the "
            .. "rule is counting. Drag it anywhere you like.",
        function(self) CW.SetTrackerShown(self:GetChecked() and true or false) end)
    fly.trackerReset = Button(tracker, 18, 94, "Reset tracker position", "Puts the tracker back at the top of the screen.",
        function() if CW.ResetTrackerPosition then CW.ResetTrackerPosition() end end)
    tracker:SetHeight(94 + 22 + 18)

    -- Abilities: kept on the server for this character, so the box shows what
    -- the server says and a click asks it to change
    local abilities = Group(RIGHT, TOP + 134 + 16, "Abilities", "Saved for this character.")
    fly.abilitiesGroup = abilities
    fly.autoShotCheck = Check(abilities, "ClasslessWildcardSettingAutoShot", 18, 56, "Disable Auto Shot",
        "Auto Shot is taught while a bow, gun or crossbow is equipped. "
            .. "Tick to keep it off whatever is equipped. Shoot still fires a bow, gun or crossbow.",
        function(self) Send("AUTOSHOT " .. (self:GetChecked() and 1 or 0)) end)
    abilities:SetHeight(56 + 24 + 18)

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
        fly.trackerCheck:SetChecked((not CW.TrackerShown or CW.TrackerShown()) and 1 or nil)
        fly.autoShotCheck:SetChecked((CW.state.autoShotOff or 0) == 1 and 1 or nil)
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
-- Spellbook tabs past the eighth: Blizzard's tabs, Blizzard's pages.
--
-- The client's SpellBookFrame.lua: SpellButton_OnClick reads
-- SpellBookFrame.selectedSkillLineOffset and SPELLBOOK_PAGENUMBERS[line] and
-- then calls CastSpell, which is protected. SpellBookFrame_Update loops
-- `for i=1, MAX_SKILLLINE_TABS` and then rewrites that offset in
-- SpellButton_UpdateButton. An addon raising MAX_SKILLLINE_TABS taints every
-- update at that read, so the offset is tainted, so every cast from the book
-- is "blocked from an action only available to the Blizzard UI".
--
-- So the ceiling stays at 8 and Blizzard's loop never touches ours. Tabs 9
-- and up are still Blizzard's template with Blizzard's own click handler,
-- created and dressed here after each update: same art, same page, same spell
-- buttons. What those tabs need that only this addon can give them is
-- SPELLBOOK_PAGENUMBERS[9..], and that seed is tainted, so ON A TAB PAST EIGHT
-- Blizzard's spell buttons cannot cast. There, twelve invisible secure action
-- buttons sit over the stock ones and cast, drag, link and tooltip the way
-- SpellButton_OnClick, _OnDrag and _OnEnter do. On tabs 1 to 8 they are hidden
-- and nothing of Blizzard's is touched.
-- ---------------------------------------------------------------------------
do
    local BLIZZ_TABS = 8            -- what SpellBookFrame.xml declares, and MAX_SKILLLINE_TABS stays
    local PER_COLUMN = 7            -- an 8th row lands on the page-turn row
    local STEP_Y, STEP_X = 49, 42   -- 32px button + Blizzard's 17px gap
    local PER_PAGE = 12             -- SPELLS_PER_PAGE
    local MAX_TABS = 40             -- comfortably above the 33 lines that carry spells
    local BOOK = BOOKTYPE_SPELL or "spell"

    local sb = { overlays = {}, installed = false }
    CW.spellbook = sb

    local function anchorTab(tab, i)
        local col = math.floor((i - 1) / PER_COLUMN)
        local row = math.fmod(i - 1, PER_COLUMN)
        tab:ClearAllPoints()
        tab:SetPoint("TOPLEFT", SpellBookFrame, "TOPRIGHT",
                     -32 + col * STEP_X, -65 - row * STEP_Y)
    end

    -- A tab past the eighth: Blizzard's template, so the click runs
    -- SpellBookSkillLineTab_OnClick as Blizzard wrote it. Nothing here calls
    -- SetScript on it. The Flash texture is what LEARNED_SPELL_IN_TAB shows.
    local function tabFor(i)
        local name = "SpellBookSkillLineTab" .. i
        local tab = _G[name]
        if tab then return tab end
        tab = CreateFrame("CheckButton", name, SpellBookFrame, "SpellBookSkillLineTabTemplate")
        tab:SetID(i)
        local flashParent = SpellBookTabFlashFrame or SpellBookFrame
        local flash = flashParent:CreateTexture(name .. "Flash", "OVERLAY")
        flash:SetTexture("Interface\\Buttons\\CheckButtonGlow")
        flash:SetBlendMode("ADD")
        flash:SetWidth(64); flash:SetHeight(64)
        flash:SetPoint("CENTER", tab, "CENTER", 0, 0)
        flash:Hide()
        return tab
    end

    -- Which spell the stock button under overlay `i` is showing.
    --
    -- Blizzard's own function, not a copy of it. SpellBook_GetSpellID reads
    -- SpellBookFrame.selectedSkillLineOffset and
    -- SPELLBOOK_PAGENUMBERS[selectedSkillLine], and SpellButton_UpdateButton
    -- has already set that offset for the button we are covering by the time
    -- this runs -- our update is hooked onto the END of SpellBookFrame_Update.
    -- So this returns the number that drew the icon, and the tooltip and the
    -- cast cannot name a different spell than the picture.
    --
    -- This used to work the same arithmetic out again -- offset, page stride,
    -- the highest-rank swap when ranks are hidden, the bounds check. Every one
    -- of those is a chance to disagree with the book on a page the author never
    -- had, and disagreeing by one is what a wrong tooltip IS.
    --
    -- Returns the known-rank slot (what the button draws and what a tooltip
    -- wants) and the display slot (what the bound is measured in).
    local function slotFor(i, line)
        if type(SpellBook_GetSpellID) ~= "function" then return nil end
        local known, display = SpellBook_GetSpellID(i)
        if not known then return nil end

        -- and the same bound the button uses to disable itself:
        -- SpellButton_UpdateButton hides everything past offset + numSpells,
        -- which is where one tab's slots end and the next tab's begin.
        if type(SpellBook_GetTabInfo) == "function" and display then
            local _, _, offset, num = SpellBook_GetTabInfo(line)
            offset, num = tonumber(offset) or 0, tonumber(num) or 0
            if num > 0 and display > offset + num then return nil end
        end
        return known, display
    end

    -- The slot a button is over RIGHT NOW, not the one the last update left on
    -- it. Blizzard's own SpellButton_OnEnter and _OnClick call
    -- SpellBook_GetSpellID at the moment of the hover or the click, and that is
    -- exactly why the stock book never shows the wrong tooltip: the page can
    -- move between an update and a mouse-over -- another addon reskinning the
    -- book and re-running its own update, an event we are not hooked to -- and
    -- a cached slot then names a spell that is no longer under the cursor.
    --
    -- If it HAS moved, re-arm before answering, so the tooltip and the cast are
    -- the same spell rather than merely both plausible. Only the secure cast
    -- attribute has to be cached, and only combat stops it being re-armed --
    -- and in combat the book is pinned to where the buttons already point.
    local function liveSlot(b)
        if not b.slot or not b.index then return b.slot end
        local line = tonumber(SpellBookFrame and SpellBookFrame.selectedSkillLine) or 1
        local slot = slotFor(b.index, line)
        if slot and slot ~= b.slot and sb.update
           and not (InCombatLockdown and InCombatLockdown()) then
            sb.update()
            slot = b.slot
        end
        return slot or b.slot
    end

    local function overlayFor(i)
        local b = sb.overlays[i]
        if b then return b end
        local under = _G["SpellButton" .. i]
        b = CreateFrame("Button", "ClasslessWildcardSpellOverlay" .. i, SpellBookFrame,
                        "SecureActionButtonTemplate")
        if under then
            b:SetAllPoints(under)
            b:SetFrameLevel((under:GetFrameLevel() or 0) + 2)
        end
        b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
        b:RegisterForDrag("LeftButton")
        b:SetAttribute("type", "spell")
        -- a modified click is not a cast in the stock book either: it links,
        -- or picks up. PostClick below does what SpellButton_OnModifiedClick does.
        b:SetAttribute("shift-type*", "none")
        b:SetAttribute("ctrl-type*", "none")
        b:SetAttribute("alt-type*", "none")
        b:SetScript("PostClick", function(self)
            local slot = liveSlot(self)
            if not slot or not IsModifiedClick or not IsModifiedClick() then return end
            if IsModifiedClick("CHATLINK") then
                local link = GetSpellLink and GetSpellLink(slot, BOOK)
                if link and ChatEdit_InsertLink then ChatEdit_InsertLink(link) end
            elseif IsModifiedClick("PICKUPACTION") then
                if PickupSpell then PickupSpell(slot, BOOK) end
            end
        end)
        b:SetScript("OnDragStart", function(self)
            local slot = liveSlot(self)
            if slot and PickupSpell then PickupSpell(slot, BOOK) end
        end)
        b:SetScript("OnReceiveDrag", function(self)
            local slot = liveSlot(self)
            if slot and PickupSpell then PickupSpell(slot, BOOK) end
        end)
        b:SetScript("OnEnter", function(self)
            local slot = liveSlot(self)
            if not slot then return end
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:SetSpell(slot, BOOK)
        end)
        b:SetScript("OnLeave", function() GameTooltip:Hide() end)
        b:Hide()
        sb.overlays[i] = b
        return b
    end

    -- After every SpellBookFrame_Update: dress the tabs past eight the way
    -- Blizzard's loop dresses the first eight, and lay the overlays over the
    -- page when the selected tab is one of ours.
    local function update()
        if not SpellBookFrame then return end
        local lines = tonumber(GetNumSpellTabs()) or 0
        local spellBook = (SpellBookFrame.bookType or BOOK) == BOOK
        local selected = tonumber(SpellBookFrame.selectedSkillLine) or 1

        for i = 1, BLIZZ_TABS do
            local tab = _G["SpellBookSkillLineTab" .. i]
            if tab then anchorTab(tab, i) end
        end
        for i = BLIZZ_TABS + 1, MAX_TABS do
            if i <= lines and spellBook then
                local tab = tabFor(i)
                -- Blizzard seeds the first eight page numbers in OnLoad; the
                -- rest are ours to seed, and the reason the overlays exist
                if SPELLBOOK_PAGENUMBERS and SPELLBOOK_PAGENUMBERS[i] == nil then
                    SPELLBOOK_PAGENUMBERS[i] = 1
                end
                local name, texture = GetSpellTabInfo(i)
                tab:SetNormalTexture(texture or "Interface\\Icons\\INV_Misc_QuestionMark")
                tab.tooltip = name
                anchorTab(tab, i)
                tab:SetChecked(selected == i)
                tab:Show()
            elseif _G["SpellBookSkillLineTab" .. i] then
                _G["SpellBookSkillLineTab" .. i]:Hide()
            end
        end

        -- the overlays: only on a tab past eight, and never in combat, where a
        -- secure button cannot be shown, hidden or retargeted
        local ours = spellBook and selected > BLIZZ_TABS and selected <= lines
        if InCombatLockdown and InCombatLockdown() then
            sb.stale = true
            -- A secure button cannot be re-armed in combat, and the book can
            -- still be paged and re-tabbed: the icons move and the buttons on
            -- top of them do not, so a click shows one spell and casts the one
            -- that used to be there. That is what "his spells became wrong"
            -- looks like, and it is the only place it can happen -- Blizzard's
            -- own buttons on tabs 1 to 8 read their slot at click time.
            --
            -- We cannot move the buttons, so move the book back to them.
            local armed = sb.armed
            if armed and not sb.pinning then
                local page = (SPELLBOOK_PAGENUMBERS and SPELLBOOK_PAGENUMBERS[selected]) or 1
                if selected ~= armed.line or page ~= armed.page then
                    SpellBookFrame.selectedSkillLine = armed.line
                    if SPELLBOOK_PAGENUMBERS then
                        SPELLBOOK_PAGENUMBERS[armed.line] = armed.page
                    end
                    -- re-entrant: this is a hook ON SpellBookFrame_Update. The
                    -- flag is what stops the second pass pinning again.
                    sb.pinning = true
                    if SpellBookFrame_Update then SpellBookFrame_Update() end
                    sb.pinning = nil
                end
            end
            return
        end
        sb.stale = nil
        -- where the buttons are pointing, so combat can put the book back here
        sb.armed = ours and { line = selected,
                              page = (SPELLBOOK_PAGENUMBERS and SPELLBOOK_PAGENUMBERS[selected]) or 1 }
                        or nil
        for i = 1, PER_PAGE do
            local b = overlayFor(i)
            -- Re-anchor and re-stack every time, not once at creation. A UI
            -- replacement skins the stock spell buttons AFTER this addon has
            -- built its overlays -- ElvUI is the common one -- and anything
            -- that moves a button or raises its frame level leaves ours behind
            -- it, where a click reaches the skin instead of the secure button
            -- and the spell simply does not cast. Cheap to assert, and only
            -- ever reached out of combat, where anchoring a secure frame is
            -- still allowed.
            local under = _G["SpellButton" .. i]
            if under then
                b:ClearAllPoints()
                b:SetAllPoints(under)
                b:SetFrameLevel((under:GetFrameLevel() or 0) + 2)
            end
            -- A spell button's NAME and its ID are different numbers.
            -- SpellBookFrame.xml lays the names down the left column and then
            -- the right (1, 3, 5 ... 2, 4, 6 ...) while the IDs run in spell
            -- order, so SpellButton3 carries id 2 and SpellButton5 id 3. They
            -- agree only on 1 and 12. Blizzard's own OnEnter and OnClick pass
            -- self:GetID(); passing the name's number instead is why the
            -- second spell in a column wore the third one's tooltip, the third
            -- wore the fifth's, and it got worse down the page.
            local id = (under and under.GetID and under:GetID()) or i
            if not id or id < 1 then id = i end
            b.index = id
            local slot, shown = nil, nil
            if ours then
                slot, shown = slotFor(id, selected)
                if slot then
                    local texture = GetSpellTexture(slot, BOOK)
                    if not texture or texture == "" then slot = nil end
                end
            end
            b.slot = slot
            if slot then
                local name, rank = GetSpellName(slot, BOOK)
                if rank and rank ~= "" then
                    b:SetAttribute("spell", name .. "(" .. rank .. ")")
                else
                    b:SetAttribute("spell", name)
                end
                b:Show()
            else
                -- and it stops naming a spell as well as going away: a hidden
                -- secure button cannot be clicked, but leaving last page's
                -- spell on it is a lie waiting for the next time it is shown
                b:SetAttribute("spell", nil)
                b:Hide()
            end
        end
    end

    local function install()
        if sb.installed or not SpellBookFrame then return end
        sb.installed = true
        update()
        if hooksecurefunc and SpellBookFrame_Update then
            hooksecurefunc("SpellBookFrame_Update", update)
        end
    end
    sb.install, sb.update = install, update

    local watcher = CreateFrame("Frame")
    watcher:RegisterEvent("PLAYER_ENTERING_WORLD")
    watcher:RegisterEvent("ADDON_LOADED")
    watcher:RegisterEvent("PLAYER_REGEN_ENABLED")   -- overlays could not move in combat
    watcher:SetScript("OnEvent", function(_, event)
        if not sb.installed then install() end
        if sb.installed and event == "PLAYER_REGEN_ENABLED" and sb.stale then update() end
    end)
end

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
    elseif cmd == "show" or cmd == "hide" or cmd == "" then
        if cmd == "" then
            ClasslessWildcardDB.hideBars = not ClasslessWildcardDB.hideBars
        else
            ClasslessWildcardDB.hideBars = (cmd == "hide")
        end
        CW.UpdateBarsVisibility()
        Print(ClasslessWildcardDB.hideBars and "Resource bars hidden." or "Resource bars shown.")
        if CW.setFly and CW.setFly:IsShown() then CW.RenderSettings() end
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
        GameTooltip:AddLine("Left-click: Hero Advancement" .. (key and ("  (" .. key .. ")") or ""), 1, 1, 1)
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
        HelpMicroButton.newbieText = "Opens Hero Advancement. Shift-click for the Help / GM window."

        -- The stock Talents button only ever shows a tamed beast's talents
        -- now, so it says so. Blizzard rewrites this title on every binding
        -- change (TalentMicroButton_OnEvent), hence the hook below.
        if TalentMicroButton then
            TalentMicroButton.tooltipText = MicroButtonTooltipText
                and MicroButtonTooltipText("Pet Talents", "TOGGLETALENTS") or "Pet Talents"
            TalentMicroButton.newbieText = "Your tamed beast's talents. Your own are in Hero Advancement."
        end
    end
    CW.RefreshMicroTooltip()
    -- On the button's script, not the global: its XML binds OnEvent to the
    -- function itself, so a hook on the name would never run.
    if TalentMicroButton and TalentMicroButton.HookScript then
        TalentMicroButton:HookScript("OnEvent", function() CW.RefreshMicroTooltip() end)
    end

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
-- roll reveal: animated d20 that spins, lights up and bursts into the rolled
-- ability/talent (Ascension-style level-up moment)
-- ---------------------------------------------------------------------------
local SPIN_ATLAS = "Interface\\AddOns\\ClasslessWildcard\\d20_spin"
ANIM.SPIN_TIME, ANIM.BURST_TIME = 1.6, 0.35

-- frameless, Ascension-style: the die floats over the world on a soft shadow,
-- no dialog box
local reveal = CreateFrame("Frame", "ClasslessWildcardReveal", UIParent)
reveal:SetWidth(360); reveal:SetHeight(404)
reveal:SetPoint("CENTER", 0, 170)
reveal:SetFrameStrata("FULLSCREEN_DIALOG") -- always clearly above the panel
reveal:EnableMouse(true)                   -- and never leaks clicks through
reveal:Hide()

-- The shadow and the text scrims sit on a frame of their own BENEATH the
-- reveal. 3.3.5 has no draw sublevels, so on the reveal's BACKGROUND they had
-- no order against the starburst, and a shadow drawn last dimmed the beams.
-- A frame one level down is under every layer the reveal draws. It follows
-- the reveal: anchored to it, shown and hidden with it.
reveal.under = CreateFrame("Frame", nil, UIParent)
reveal.under:SetFrameStrata("FULLSCREEN_DIALOG")
reveal.under:SetAllPoints(reveal)
reveal.under:Hide()
reveal:SetFrameLevel(reveal.under:GetFrameLevel() + 2)
reveal:HookScript("OnShow", function(self)
    self.under:SetFrameLevel(math.max(0, self:GetFrameLevel() - 1))
    self.under:Show()
end)
reveal:HookScript("OnHide", function(self) self.under:Hide() end)

local rvShadow = reveal.under:CreateTexture(nil, "BACKGROUND")
rvShadow:SetWidth(470); rvShadow:SetHeight(470)
rvShadow:SetPoint("CENTER", 0, 0)
rvShadow:SetTexture("Interface\\AddOns\\ClasslessWildcard\\shadow")

-- Text over open world is unreadable against bright ground, so darken a band
-- behind the title and the name/rarity lines. Two soft bars rather than a panel:
-- the reveal is meant to float, not become a dialog box.
local function TextScrim(parent, y, height, alpha)
    local t = parent:CreateTexture(nil, "BACKGROUND")
    t:SetTexture("Interface\\AddOns\\ClasslessWildcard\\shadow")
    t:SetWidth(360); t:SetHeight(height)
    t:SetPoint("CENTER", 0, y)
    t:SetAlpha(alpha)
    return t
end
TextScrim(reveal.under, 176, 96, 0.85)
local rvTextScrim = TextScrim(reveal.under, -148, 122, 0.9)

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
-- The reveal's own layers, bottom up: BACKGROUND the starbursts and the glow
-- (all additive, so their order among themselves changes nothing), BORDER the
-- info plate, ARTWORK the plate's edge and the icon (which never overlap),
-- OVERLAY the die and the text.
rvFX.rays = reveal:CreateTexture(nil, "BACKGROUND")
rvFX.rays:SetWidth(372); rvFX.rays:SetHeight(372)
rvFX.rays:SetPoint("CENTER", 0, 26)
rvFX.rays:SetTexture("Interface\\AddOns\\ClasslessWildcard\\rays")
rvFX.rays:SetBlendMode("ADD")
rvFX.rays:Hide()

rvFX.rays2 = reveal:CreateTexture(nil, "BACKGROUND")
rvFX.rays2:SetWidth(268); rvFX.rays2:SetHeight(268)
rvFX.rays2:SetPoint("CENTER", 0, 26)
rvFX.rays2:SetTexture("Interface\\AddOns\\ClasslessWildcard\\rays")
rvFX.rays2:SetBlendMode("ADD")
rvFX.rays2:Hide()

local rvGlow = reveal:CreateTexture(nil, "BACKGROUND")
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
        GameTooltip:Hide()   -- the same link on a shown tooltip toggles it off
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetHyperlink("spell:" .. d.spell)
        GameTooltip:Show()
    end
end)
rvHover:SetScript("OnLeave", function() GameTooltip:Hide() end)

local rvName = reveal:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
rvName:SetPoint("CENTER", 0, -138)
-- given a width by ShowResult, so it needs to know how to use one
rvName:SetJustifyH("CENTER")

-- Hung off the name rather than pinned to its own centre offset: the two were
-- 32px apart by coincidence of two hardcoded numbers, and the name got bigger.
local rvSub = reveal:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
rvSub:SetPoint("TOP", rvName, "BOTTOM", 0, -6)
rvSub:SetJustifyH("CENTER")

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

-- The text block, measured rather than anchored from both ends. The panel used
-- to be pinned TOP-to-the-name and BOTTOM-to-the-last-row and left to work its
-- own height out, which put its edge straight through the name whenever the two
-- anchors disagreed. Now the block is measured here and the panel is given a
-- position and a height, so there is one answer and it is the same every time.
rvFX.PAD = 14        -- clear space inside the panel, above the name and below the last row
rvFX.NAME_GAP = 6    -- name to tier line
rvFX.INFO_GAP = 10   -- tier line to the first tooltip row
rvFX.NAME_Y = -138   -- the name's centre, as an offset from the reveal's centre
rvFX.SIDE = 22       -- and clear space inside its left and right edges
-- The plate was a fixed 344 wide and the name was never given a width, so a
-- long one ("Improved Concussive Shot  Rank 1") ran straight out of both
-- sides of it. The plate is measured off its widest line now, and every line
-- in it is held to the plate, so a name past even the maximum wraps instead of
-- escaping.
rvFX.PANEL_MIN, rvFX.PANEL_MAX = 344, 480

-- A real panel behind the text. The reveal floats over the world, and a shadow
-- alone is not a background: small text on grass is unreadable however hard its
-- shadow is. This is the tooltip treatment -- near-black plate, hairline border
-- in the rarity's colour -- drawn on BACKGROUND/BORDER so the OVERLAY font
-- strings of this same frame stay on top of it without any reparenting.
-- One plate, built for whichever frame asks for it. The reveal has had one
-- since it was written; the starting hand wants the same thing under its row,
-- and two copies of this would drift apart the first time either changed.
--
-- Returns an object with its own panel, border and rows. `anchor` is the region
-- the first row hangs from -- the sub-line in both cases -- so the caller keeps
-- control of the column above it.
function rvFX.MakeInfo(parent, anchor)
    local info = { rows = {}, edges = {} }

    -- A real panel behind the text. Both frames float over the world, and a
    -- shadow alone is not a background: small text on grass is unreadable
    -- however hard its shadow is. This is the tooltip treatment -- near-black
    -- plate, hairline border in the rarity's colour -- drawn on BORDER and
    -- ARTWORK so the OVERLAY font strings of the same frame stay on top of it
    -- without any reparenting, and the additive glow and starburst on
    -- BACKGROUND stay under it.
    info.panel = parent:CreateTexture(nil, "BORDER")
    info.panel:SetTexture(0, 0, 0)
    info.panel:SetAlpha(0.86)
    info.panel:SetWidth(344)
    info.panel:Hide()

    for i = 1, 4 do
        local e = parent:CreateTexture(nil, "ARTWORK")   -- over the plate
        e:SetTexture(1, 1, 1)
        e:Hide()
        info.edges[i] = e
    end
    info.edges[1]:SetPoint("TOPLEFT", info.panel, "TOPLEFT", 0, 0)
    info.edges[1]:SetPoint("TOPRIGHT", info.panel, "TOPRIGHT", 0, 0)
    info.edges[1]:SetHeight(1)
    info.edges[2]:SetPoint("BOTTOMLEFT", info.panel, "BOTTOMLEFT", 0, 0)
    info.edges[2]:SetPoint("BOTTOMRIGHT", info.panel, "BOTTOMRIGHT", 0, 0)
    info.edges[2]:SetHeight(1)
    info.edges[3]:SetPoint("TOPLEFT", info.panel, "TOPLEFT", 0, 0)
    info.edges[3]:SetPoint("BOTTOMLEFT", info.panel, "BOTTOMLEFT", 0, 0)
    info.edges[3]:SetWidth(1)
    info.edges[4]:SetPoint("TOPRIGHT", info.panel, "TOPRIGHT", 0, 0)
    info.edges[4]:SetPoint("BOTTOMRIGHT", info.panel, "BOTTOMRIGHT", 0, 0)
    info.edges[4]:SetWidth(1)

    -- One row per tooltip line, laid out like the tooltip itself: a
    -- left-justified string and a right-justified one sharing the same box, so
    -- "10 Rage" and "Melee Range" sit at opposite ends of the same line. Rows
    -- chain downward from the one above, so a wrapped description pushes what
    -- follows it. Neither frame is resized around them -- nothing clips
    -- children here, so the block extends below and the buttons are re-anchored
    -- under whatever it came to.
    for i = 1, rvFX.INFO_LINES do
        local row = {}
        row.left = parent:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
        row.left:SetWidth(304)
        row.left:SetJustifyH("LEFT")
        row.left:SetJustifyV("TOP")
        row.left:SetShadowColor(0, 0, 0, 1)
        row.left:SetShadowOffset(1, -1)
        if i == 1 then
            row.left:SetPoint("TOP", anchor, "BOTTOM", 0, -10)
        else
            row.left:SetPoint("TOP", info.rows[i - 1].left, "BOTTOM", 0, -2)
        end
        row.right = parent:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
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
        info.rows[i] = row
    end

    -- Every row is held to the plate's inner width, so a long description wraps
    -- inside it rather than running past the edge.
    function info:SetRowWidth(w)
        -- Remembered, because Fill has to know how much room a row has before
        -- it can tell whether a left/right pair will collide in it.
        self.rowWidth = w
        for i = 1, rvFX.INFO_LINES do
            self.rows[i].left:SetWidth(w)
        end
    end

    function info:Clear()
        self.panel:Hide()
        for _, e in ipairs(self.edges) do e:Hide() end
        for i = 1, rvFX.INFO_LINES do
            local row = self.rows[i]
            row.left:SetText(""); row.right:SetText("")
            row.left:Hide(); row.right:Hide()
        end
    end

    -- Fill the block from a spell's own tooltip and return how tall it came out.
    function info:Fill(spellId)
        local lines = rvFX.ScanSpell(spellId)
        local height, last = 0, nil
        for i = 1, rvFX.INFO_LINES do
            local row, line = self.rows[i], lines[i]
            if line then
                local left, right = line.left or "", line.right or ""
                row.left:SetText(left)
                row.right:SetText(right)
                -- The two share ONE rectangle: row.right is SetAllPoints(row.left)
                -- and merely justified the other way. So the moment the pair is
                -- wider than the plate they run into each other in the middle
                -- rather than pushing it wider the way a real tooltip would. On
                -- the hand's 216px card that printed Auto Shot's "Instant cast"
                -- and "2.5 sec cooldown" as "Instant ca2s.5t sec cooldown".
                --
                -- When they will not both fit, hand the right-hand text to the
                -- left string and let it wrap onto a second line. Two readable
                -- lines beat one unreadable one, and the row measures its own
                -- height below so the rows under it still land correctly.
                local room = self.rowWidth or 0
                if room > 0 and left ~= "" and right ~= "" then
                    local lw = tonumber(row.left:GetStringWidth()) or 0
                    local rw = tonumber(row.right:GetStringWidth()) or 0
                    if lw + rw + 8 > room then
                        row.left:SetText(left .. "  " .. right)
                        row.right:SetText("")
                    end
                end
                row.left:SetTextColor(line.r, line.g, line.b)
                row.right:SetTextColor(line.r, line.g, line.b)
                row.left:Show(); row.right:Show()
                height = height + (tonumber(row.left:GetStringHeight()) or 12) + 2
                last = row.left
            else
                -- blank as well as hidden: a hidden string keeps its old height
                -- and would still push the row below it
                row.left:SetText(""); row.right:SetText("")
                row.left:Hide(); row.right:Hide()
            end
        end
        return height, last
    end

    return info
end

-- The reveal's own, and the names the rest of the file has always called it by.
rvFX.reveal = rvFX.MakeInfo(reveal, rvSub)
rvFX.panel, rvFX.edges, rvFX.info = rvFX.reveal.panel, rvFX.reveal.edges, rvFX.reveal.rows
function rvFX.SetRowWidth(w) rvFX.reveal:SetRowWidth(w) end
function rvFX.HideInfo() rvFX.reveal:Clear() end
function rvFX.ShowInfo(spellId) return rvFX.reveal:Fill(spellId) end

-- These are the only two things on the reveal you can act on, and they were
-- smaller than the buttons on the panel behind it. The large font carries
-- that; the height stays the stock 22, where the button art is not stretched.
local rvKeep = CreateFrame("Button", nil, reveal, "UIPanelButtonTemplate")
rvKeep:SetWidth(150); rvKeep:SetHeight(22)
rvKeep:SetPoint("BOTTOM", -82, 4)
rvKeep:SetText("Keep")

local rvReroll = CreateFrame("Button", nil, reveal, "UIPanelButtonTemplate")
rvReroll:SetWidth(150); rvReroll:SetHeight(22)
rvReroll:SetPoint("BOTTOM", 82, 4)
rvReroll:SetText("Reroll")

for _, b in ipairs({ rvKeep, rvReroll }) do
    if b.SetNormalFontObject then
        b:SetNormalFontObject("GameFontNormalLarge")
        b:SetDisabledFontObject("GameFontDisableLarge")
        b:SetHighlightFontObject("GameFontHighlightLarge")
    end
end

-- Out of charges and out of scrolls, the reroll button becomes the way to
-- get one: it buys a Reroll Scroll, and the next press spends it. The price is
-- on the button, so pressing it is the confirmation. The panel's own Buy
-- Scroll button asks first with a StaticPopup, which cannot be used here: the
-- reveal sits on FULLSCREEN_DIALOG and the popup would open behind it.
function rvFX.SetRerollButton()
    local s = CW.state
    local charges = (s.rerolls or 0) + (s.scrolls or 0)
    rvReroll.buy = nil
    if CW.NoRerolls() then
        -- Dealt Hand: the card is yours, and the button says so
        rvReroll:SetText("No rerolls")
        rvReroll:Disable()
    elseif (s.level or 1) < (s.freeReroll or 10) then
        rvReroll:SetText("Reroll (free)")
        rvReroll:Enable()
    elseif charges > 0 then
        rvReroll:SetText("Reroll (" .. charges .. ")")
        rvReroll:Enable()
    elseif (s.scrollBuy or 0) == 1 then
        rvReroll.buy = true
        rvReroll:SetText("Buy Scroll  " .. GetCoinTextureString(s.scrollCost or 0))
        rvReroll:Enable()
    else
        rvReroll:SetText("Reroll (0)")
        rvReroll:Disable()
    end
    -- the price makes for a longer label than "Reroll (3)" ever is
    rvReroll:SetWidth(rvReroll.buy and 210 or 150)
end

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
--
-- Turns per second is not what the eye reads: the starburst has 24 beams, so
-- one turn is 24 beams going past. The old legendary rate of 0.62 put fifteen
-- of them past a second, which is a strobe rather than a glow. A quarter of
-- that is a beam every third of a second, still clearly turning and still
-- faster the better the roll.
rvFX.tiers = {
    [0] = { rays = 0,    spin = 0,    pulse = 0,    pop = 0,  shake = 0,   snd = "igMainMenuOptionCheckBoxOn" },
    [1] = { rays = 0.22, spin = 0.04, pulse = 0.05, pop = 4,  shake = 0,   snd = "LOOTWINDOWCOINSOUND" },
    [2] = { rays = 0.38, spin = 0.07, pulse = 0.10, pop = 9,  shake = 0,   snd = "QUESTCOMPLETED" },
    [3] = { rays = 0.54, spin = 0.11, pulse = 0.16, pop = 15, shake = 3,   snd = "LEVELUPSOUND" },
    [4] = { rays = 0.74, spin = 0.16, pulse = 0.24, pop = 24, shake = 6,   snd = "PVPTHROUGHQUEUE",
            snd2 = "LEVELUPSOUND" },
}

-- A nemesis slain: a banner over the world, the way a boss kill announces
-- itself, while the server bursts the body and lights the Hero up.
-- "NK|name|experience returned|bonus|Vengeance gained|Vengeance|needed|trophy item". Built on
-- first use, every part on one table: the main chunk is at Lua 5.1's local
-- limit. Nothing on it takes the mouse, so it never blocks a click.
rvFX.NK = { IN = 0.22, HOLD = 4.6, OUT = 1.2, GONG = "Sound\\Doodad\\G_GongTroll01.wav",
            CRY = "Sound\\Spells\\Bloodlust_player_cast_head.wav", CRY_AT = 0.3 }
function CW.NemesisBannerFrame()
    local NK = rvFX.NK
    local B = NK.frame
    if not B then
        B = CreateFrame("Frame", "ClasslessWildcardNemesisBanner", UIParent)
        B:SetWidth(560); B:SetHeight(220)
        B:SetPoint("CENTER", 0, 170)
        B:SetFrameStrata("FULLSCREEN_DIALOG")
        B:EnableMouse(false)
        -- BACKGROUND: the starbursts and the glow, additive, red for blood
        B.rays = B:CreateTexture(nil, "BACKGROUND")
        B.rays:SetWidth(330); B.rays:SetHeight(330)
        B.rays:SetPoint("CENTER", 0, 50)
        B.rays:SetTexture("Interface\\AddOns\\ClasslessWildcard\\rays")
        B.rays:SetBlendMode("ADD")
        B.rays:SetVertexColor(1, 0.25, 0.12)
        B.glow = B:CreateTexture(nil, "BACKGROUND")
        B.glow:SetWidth(200); B.glow:SetHeight(200)
        B.glow:SetPoint("CENTER", 0, 50)
        B.glow:SetTexture("Interface\\AddOns\\ClasslessWildcard\\glow")
        B.glow:SetBlendMode("ADD")
        B.glow:SetVertexColor(1, 0.3, 0.15)
        -- BORDER: a dark band so the words read on grass and on stone
        B.band = B:CreateTexture(nil, "BORDER")
        B.band:SetWidth(560); B.band:SetHeight(118)
        B.band:SetPoint("CENTER", 0, -55)
        B.band:SetTexture(0, 0, 0, 0.6)
        -- ARTWORK: the skull
        B.skull = B:CreateTexture(nil, "ARTWORK")
        B.skull:SetWidth(60); B.skull:SetHeight(60)
        B.skull:SetPoint("CENTER", 0, 50)
        B.skull:SetTexture("Interface\\Icons\\Spell_Shadow_Skull")
        B.skull:SetTexCoord(0.07, 0.93, 0.07, 0.93)
        local face = "Fonts\\MORPHEUS.ttf"
        local function line(size, r, g, b, y)
            local fs = B:CreateFontString(nil, "OVERLAY")
            fs:SetFont(face, size, "OUTLINE")
            fs:SetTextColor(r, g, b)
            fs:SetShadowColor(0, 0, 0, 1)
            fs:SetShadowOffset(1, -1)
            fs:SetPoint("CENTER", 0, y)
            return fs
        end
        B.title = line(36, 1, 0.22, 0.12, -2)
        B.name = line(20, 1, 0.82, 0.3, -32)
        B.xp = line(16, 0.45, 1, 0.45, -56)
        B.head = line(16, 1, 0.82, 0, -78)
        B.trophy = line(14, 0.64, 0.21, 0.93, -100)
        B:SetScript("OnUpdate", CW.NemesisBannerTick)
        NK.frame = B
    end
    return B
end
-- the banner shown: the slam, its first sound now and its second at CRY_AT
function CW.NemesisBannerShow(B, first, second)
    B.cry = second
    B.t, B.cried = 0, nil
    B:SetAlpha(0)
    B:Show()
    if PlaySoundFile then pcall(PlaySoundFile, first) end
end

function CW.NemesisSlain(p)
    local NK = rvFX.NK
    local B = CW.NemesisBannerFrame()
    local back, bonus = tonumber(p[3]) or 0, tonumber(p[4]) or 0
    local gained, total, need = tonumber(p[5]) or 0, tonumber(p[6]) or 0, tonumber(p[7]) or 0
    local trophy = tonumber(p[8]) or 0
    B.title:SetText("Nemesis Slain")
    B.name:SetText(p[2] or "")
    if back > 0 then
        B.xp:SetText("+" .. back .. " experience returned    +" .. bonus .. " bonus")
    else
        B.xp:SetText("+" .. bonus .. " experience for the kill")
    end
    B.head:SetText("+" .. gained .. " Vengeance    " .. total .. " of " .. need)
    if trophy > 0 then
        B.trophy:SetText((GetItemInfo(trophy)) or CW.TrophyName(trophy))
    else
        B.trophy:SetText("")
    end
    CW.NemesisBannerShow(B, NK.GONG, NK.CRY)
end

-- A vendetta sworn: the same banner, for the oath. "NV|name|level|title".
-- War drums, then Mark of Blood's cry.
rvFX.NK.DRUMS = "Sound\\Event Sounds\\Event_wardrum_ogre.wav"
rvFX.NK.BLOOD = "Sound\\Spells\\DeathKnight_MarkofBlood.wav"
function CW.VendettaSworn(p)
    local NK = rvFX.NK
    local B = CW.NemesisBannerFrame()
    B.title:SetText("Vendetta Sworn")
    B.name:SetText((p[2] or "") .. ((p[4] or "") ~= "" and (", " .. p[4]) or ""))
    B.xp:SetText("A level " .. (tonumber(p[3]) or 0) .. " rare elite in a blood fury")
    B.head:SetText("Slay it for Vengeance and a trophy")
    B.trophy:SetText("")
    CW.NemesisBannerShow(B, NK.DRUMS, NK.BLOOD)
end

function CW.NemesisBannerTick(self, dt)
    local NK = rvFX.NK
    self.t = (self.t or 0) + (dt or 0)
    local t = self.t
    if not self.cried and t >= NK.CRY_AT then
        self.cried = true
        if PlaySoundFile then pcall(PlaySoundFile, self.cry or NK.CRY) end
    end
    local alpha, scale
    if t < NK.IN then
        local k = t / NK.IN
        alpha, scale = k, 1.6 - 0.6 * k          -- slams in from big
    elseif t < NK.IN + NK.HOLD then
        alpha, scale = 1, 1
    elseif t < NK.IN + NK.HOLD + NK.OUT then
        alpha, scale = 1 - (t - NK.IN - NK.HOLD) / NK.OUT, 1
    else
        self:Hide()
        return
    end
    self:SetAlpha(alpha)
    self:SetScale(scale)
    -- the burst turns slowly and breathes; the skull's glow pulses with it
    rvFX.Spin(self.rays, t * 0.5)
    self.rays:SetAlpha(0.55 + 0.25 * math.sin(t * 3))
    self.glow:SetAlpha(0.6 + 0.3 * math.sin(t * 3))
end

-- The second layer turns against the first. It used to run 1.45x FASTER, which
-- put the two sets of beams through each other quicker than either one alone;
-- slower than the first reads as depth instead of churn.
rvFX.COUNTER_SPIN = -0.6
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
    -- The client's own lines carry the client patch's LOWERED cost and
    -- cooldown, so they get the same correction GameTooltip does, and a spell
    -- with none yet is put to the server (the answer redraws whatever showed it).
    if CW.spellFix and CW.spellFix[spellId] then
        CW.ApplyTooltipFix(tip, spellId)
    elseif CW.spellFixAsked and not CW.spellFixAsked[spellId] then
        CW.spellFixAsked[spellId] = true
        Send("SFQ " .. spellId)
    end
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
function rvFX.CardFX(slot, rarity, boost, fade)
    local fx = rvFX.Tier(rarity)
    fade = fade or 1
    local rgb = RARITY_RGB[math.min(rarity or 0, 4)] or RARITY_RGB[0]
    -- Every card sits in a pool of its own colour, exactly as the reveal does:
    -- rvGlow is 0.55 + rays * 0.35 there and is never switched off, so a common
    -- is DIMMER than a legendary rather than unlit. This used to hide the glow
    -- whenever the tier had no starburst, which is every common in the game.
    --
    -- `fade` is the card's own alpha during the deal. The glow lives on the
    -- shared layer under all the cards, not on the card, so it does not follow
    -- slot:SetAlpha and would otherwise light an empty space before the die
    -- had reached it.
    slot.glow:SetVertexColor(rgb[1], rgb[2], rgb[3])
    slot.glow:SetAlpha((0.55 + fx.rays * 0.35 + boost * 0.9) * fade)
    slot.glow:Show()
    if fx.rays >= 0.5 then          -- epic and legendary
        slot.rays:SetVertexColor(rgb[1], rgb[2], rgb[3])
        slot.rays:SetAlpha((fx.rays * 0.55 + boost * 0.5) * fade)
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
        rvSub:SetText((RARITY_NAMES[d.rarity or 0] or "") .. "  |cffaaaaaaDealt free at Rank " .. (d.rank or 1) .. "|r")
    else
        rvSub:SetText(RARITY_NAMES[d.rarity or 0] or "")
    end
    rvName:Show(); rvSub:Show()

    -- Everything the tooltip would have said, without asking for a hover: what
    -- it costs, its range, cast time, cooldown, any stance it needs, and what
    -- it actually does. The block grows downward and the buttons follow it, so
    -- a one-line passive and a six-line spell both sit right.
    -- Width first, because a wrapped line is taller and the height depends on
    -- it. GetStringWidth reports what the text WANTS, not what it was given,
    -- so it still answers honestly for a line that is already wrapping.
    local wide = math.max(tonumber(rvName:GetStringWidth()) or 0,
                          tonumber(rvSub:GetStringWidth()) or 0)
    local panelW = math.max(rvFX.PANEL_MIN,
        math.min(rvFX.PANEL_MAX, wide + rvFX.SIDE * 2))
    local inner = panelW - rvFX.SIDE * 2
    rvFX.panel:SetWidth(panelW)
    rvName:SetWidth(inner)
    rvSub:SetWidth(inner)
    rvFX.SetRowWidth(inner)

    local infoH = rvFX.ShowInfo(d.spell)

    -- Measure the block, then place the plate on it. Everything in the column
    -- hangs off the name, so its height is the sum of the pieces plus the
    -- padding either end -- no second anchor to disagree with the first.
    local nameH = tonumber(rvName:GetStringHeight()) or 20
    local subH = tonumber(rvSub:GetStringHeight()) or 14
    local blockH = rvFX.PAD + nameH + rvFX.NAME_GAP + subH
        + (infoH > 0 and (rvFX.INFO_GAP + infoH) or 0) + rvFX.PAD
    -- top edge of the plate: the name's centre, up half its height, up the pad
    local blockTop = rvFX.NAME_Y + nameH / 2 + rvFX.PAD

    rvFX.panel:ClearAllPoints()
    rvFX.panel:SetPoint("TOP", reveal, "CENTER", 0, blockTop)
    rvFX.panel:SetHeight(blockH)
    rvFX.panel:Show()
    for _, e in ipairs(rvFX.edges) do
        e:SetVertexColor(rgb[1], rgb[2], rgb[3], 0.85)
        e:Show()
    end

    -- and the buttons sit under the plate, not under whichever text row
    -- happened to be last
    rvKeep:ClearAllPoints()
    rvReroll:ClearAllPoints()
    rvKeep:SetPoint("TOPRIGHT", rvFX.panel, "BOTTOM", -8, -14)
    rvReroll:SetPoint("TOPLEFT", rvFX.panel, "BOTTOM", 8, -14)

    -- the soft scrim still sits under the plate and blends its edges out
    rvTextScrim:SetWidth(panelW + 140)
    rvTextScrim:SetHeight(blockH + 96)
    rvTextScrim:ClearAllPoints()
    rvTextScrim:SetPoint("CENTER", 0, blockTop - blockH / 2 - 24)
    -- reroll button shows what the player can actually spend
    local s = CW.state
    rvFX.SetRerollButton()
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
        rvFX.Spin(rvFX.rays2, rvFX.rot * rvFX.COUNTER_SPIN)
        -- a slow breath on top, deeper the higher the tier
        local breathe = 1 + math.sin(GetTime() * 3) * fx.pulse
        local up = math.min(1, (GetTime() - rvFX.hit) / 0.35)
        rvFX.rays:SetAlpha(fx.rays * breathe * up)
        rvFX.rays2:SetAlpha(fx.rays * 0.5 * (2 - breathe) * up)
    end

    if rvAnim.phase == "spin" then
        local p = (GetTime() - rvAnim.t0) / ANIM.SPIN_TIME
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
        local p = (GetTime() - rvAnim.t0) / ANIM.BURST_TIME
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
    if rvReroll.buy then
        -- buy only. The state that comes back turns this into "Reroll (1)",
        -- so nothing is spent on a roll the player did not ask for.
        Send("BUYSCROLL 0")
        return
    end
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
    if d.isTalent then
        -- the same choice My Build offers: trade it away, or stake scrolls on
        -- keeping it and raising its rank
        CW.AskTalentReroll(d.entry, SpellLabel(d.spell, d.rarity), d.rank, d.maxRank, AwaitReroll)
        return
    end
    if CW.NoRerolls() then
        CW.SayNoRerolls()
        return
    end
    Send("RR " .. d.entry)
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
-- Four reveal cards across, and each card is a die, a name, a tier line and a
-- tooltip plate. 236 to a column, 150 of that the die.
hand:SetWidth(980); hand:SetHeight(500)
hand:SetPoint("CENTER", 0, 30)
hand:SetFrameStrata("FULLSCREEN_DIALOG")
hand:EnableMouse(true)
hand:Hide()

local handShadow = hand:CreateTexture(nil, "BACKGROUND")
handShadow:SetWidth(1080); handShadow:SetHeight(620)
handShadow:SetPoint("CENTER", 0, 0)
handShadow:SetTexture("Interface\\AddOns\\ClasslessWildcard\\shadow")

-- extra darkening under the title and the instruction line: over bright ground
-- the shadow alone was not enough to read them against
-- (both dark, so which of the two draws first makes no difference)
local handTextScrim = hand:CreateTexture(nil, "BACKGROUND")
handTextScrim:SetWidth(980); handTextScrim:SetHeight(140)
handTextScrim:SetPoint("TOP", 0, 22)
handTextScrim:SetTexture("Interface\\AddOns\\ClasslessWildcard\\shadow")
handTextScrim:SetAlpha(0.9)

local handGlow = hand:CreateTexture(nil, "BORDER")
handGlow:SetWidth(960); handGlow:SetHeight(420)
handGlow:SetPoint("CENTER", 0, 40)
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
    " Roll Abilities rerolls only the unlocked ones.")

-- Four cards. Not a layout budget that happens to fit four -- four is the size
-- of the starting hand, full stop. The server clamps StartingAbilities to the
-- same number so it can never deal a card this screen would not draw.
local HAND_SLOTS = 4
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

-- A card is the reveal, at the size four of them fit at.
--
-- The reveal draws a 280px rarity die with a 96px icon in its window; these are
-- the same picture at 150 and 52, four across. Everything a card owns -- die,
-- icon, padlock, name, tier line, plate -- is parented to the card itself, so
-- one SetAlpha fades all of it in together as the travelling die reaches it,
-- and the plate of one card can never be painted over by the glow of the next.
-- One table, not five locals: the main chunk is at Lua 5.1's 200-local ceiling.
local HG = {
    die = 150,        -- the rarity die, the reveal's 280 brought down
    icon = 52,        -- its window, in the same proportion
    col = 236,        -- centre to centre
    top = -78,        -- the die's top edge, from the frame's top
    plate = 216,      -- a column's plate, narrower than the reveal's
    gap = 12,         -- die to name
}

for i = 1, HAND_SLOTS do
    local slot = CreateFrame("Button", nil, hand)
    slot:SetWidth(HG.die); slot:SetHeight(HG.die)
    slot:SetPoint("TOP", hand, "TOP", (i - 2.5) * HG.col, HG.top)

    -- Tier dressing (see rvFX.CardFX). It lives on the shared layer under all
    -- the cards, not on this card, but stays anchored to this one so it
    -- follows the card as it rises into place.
    slot.rays = hand.fxLayer:CreateTexture(nil, "ARTWORK")   -- additive, as is the glow
    slot.rays:SetWidth(HG.die * 1.35); slot.rays:SetHeight(HG.die * 1.35)
    slot.rays:SetPoint("CENTER", slot, "CENTER", 0, 0)
    slot.rays:SetTexture("Interface\\AddOns\\ClasslessWildcard\\rays")
    slot.rays:SetBlendMode("ADD")
    slot.rays:Hide()
    slot.glow = hand.fxLayer:CreateTexture(nil, "ARTWORK")
    -- Sized off the reveal's own proportion (310 of glow around a 280 die),
    -- not the old 44px card's 3x: at 150 the die no longer swallows the bright
    -- middle of glow.tga, and anything wider reaches into the next column.
    slot.glow:SetWidth(HG.die * 1.15); slot.glow:SetHeight(HG.die * 1.15)
    slot.glow:SetPoint("CENTER", slot, "CENTER", 0, 0)
    slot.glow:SetTexture("Interface\\AddOns\\ClasslessWildcard\\glow")
    slot.glow:SetBlendMode("ADD")
    slot.glow:Hide()

    -- gold halo = LOCKED IN, said in light rather than in a border that would
    -- fight the die's own frame
    slot.ring = slot:CreateTexture(nil, "BACKGROUND")   -- the card's only BACKGROUND region
    slot.ring:SetWidth(HG.die * 1.25); slot.ring:SetHeight(HG.die * 1.25)
    slot.ring:SetPoint("CENTER", 0, 0)
    slot.ring:SetTexture("Interface\\AddOns\\ClasslessWildcard\\glow")
    slot.ring:SetBlendMode("ADD")
    slot.ring:SetVertexColor(1, 0.82, 0.2)
    slot.ring:SetAlpha(0.55)
    slot.ring:Hide()

    -- the icon sits in the die's window, and the die is drawn over it
    slot.icon = slot:CreateTexture(nil, "ARTWORK")
    slot.icon:SetWidth(HG.icon); slot.icon:SetHeight(HG.icon)
    slot.icon:SetPoint("CENTER", 1, 3)
    slot.icon:SetTexCoord(0.02, 0.98, 0.02, 0.98)
    slot.die = slot:CreateTexture(nil, "OVERLAY")
    slot.die:SetAllPoints(slot)
    slot.die:SetTexture(REVEAL_ATLAS)

    -- big padlock over the die: gold CLOSED = kept, grey OPEN = will reroll
    -- The die is OVERLAY too, and 3.3.5 has no sublevel to put the lock above
    -- it, so the lock rides a child frame, which draws over the whole card.
    slot.lockLayer = CreateFrame("Frame", nil, slot)
    slot.lockLayer:SetAllPoints(slot)
    slot.lock = slot.lockLayer:CreateTexture(nil, "OVERLAY")
    slot.lock:SetWidth(28); slot.lock:SetHeight(28)
    slot.lock:SetPoint("BOTTOM", slot, "TOP", 0, -6)
    slot.lock:SetTexture("Interface\\AddOns\\ClasslessWildcard\\lock_open")

    slot.name = slot:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    slot.name:SetPoint("TOP", slot, "BOTTOM", 0, -HG.gap)
    slot.name:SetWidth(HG.plate - rvFX.SIDE * 2)
    slot.name:SetJustifyH("CENTER")
    slot.sub = slot:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    slot.sub:SetPoint("TOP", slot.name, "BOTTOM", 0, -rvFX.NAME_GAP)
    slot.sub:SetWidth(HG.plate - rvFX.SIDE * 2)
    slot.sub:SetJustifyH("CENTER")

    -- its own plate, from the same factory the reveal's comes from
    slot.info = rvFX.MakeInfo(slot, slot.sub)
    slot.info:SetRowWidth(HG.plate - rvFX.SIDE * 2)

    slot:SetScript("OnClick", function(self)
        if self.abilityId then
            -- Say which state we want, never "flip whatever you have". A flip
            -- inverts the two ends for good the moment one of them is out of
            -- step, and from then on the padlock on screen is a lie: the card
            -- looks kept and the next Roll Abilities takes it anyway.
            local want = (self.entryRef and self.entryRef.locked == 1) and 0 or 1
            Send("LOCK " .. self.abilityId .. " " .. want)
            if PlaySound then pcall(PlaySound, "igMainMenuOptionCheckBoxOn") end
            -- Shown straight away so the click feels answered, but the server
            -- pushes the owned list back after every lock and that is what the
            -- padlock is finally drawn from.
            if self.entryRef then
                self.entryRef.locked = want
                CW.RenderHand()
            end
        end
    end)
    -- No tooltip: the card already says everything one would, in bigger type,
    -- without covering the card next to it.
    slot.index = i
    slot:Hide()
    handSlots[i] = slot
end

-- Fill one card from the ability it holds: the die's rarity face, the icon in
-- its window, the name in the rarity's colour, the tier under it, and the
-- plate under that. Everything below the die hangs off the name, so the plate
-- is placed from the name's own measured height rather than a second guess.
function hand.DressCard(slot)
    local rarity = math.min(slot.rarity or 0, 4)
    local rgb = RARITY_RGB[rarity] or RARITY_RGB[0]

    -- 4x2 atlas of 256px frames, one per rarity (the client caps textures at
    -- 1024), the same faces the reveal lands on
    local col, row = rarity % 4, math.floor(rarity / 4)
    slot.die:SetTexCoord(col / 4, (col + 1) / 4, row / 2, (row + 1) / 2)
    slot.icon:SetTexture(SpellIcon(slot.spellId))

    slot.name:SetText(SpellLabel(slot.spellId, rarity))
    slot.sub:SetText(RARITY_NAMES[rarity] or "")

    local infoH = slot.info:Fill(slot.spellId)
    local nameH = tonumber(slot.name:GetStringHeight()) or 16
    local subH = tonumber(slot.sub:GetStringHeight()) or 12
    local blockH = rvFX.PAD + nameH + rvFX.NAME_GAP + subH
        + (infoH > 0 and (rvFX.INFO_GAP + infoH) or 0) + rvFX.PAD

    slot.info.panel:SetWidth(HG.plate)
    slot.info.panel:ClearAllPoints()
    -- 12 is the name's own gap from the die; the pad above it is the plate's
    slot.info.panel:SetPoint("TOP", slot, "BOTTOM", 0, -HG.gap + rvFX.PAD)
    slot.info.panel:SetHeight(blockH)
    slot.info.panel:Show()
    slot.blockH = blockH   -- the buttons go under the deepest of these
    for _, e in ipairs(slot.info.edges) do
        e:SetVertexColor(rgb[1], rgb[2], rgb[3], 0.85)
        e:Show()
    end
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
handRoll:SetWidth(150); handRoll:SetHeight(22)
handRoll:SetPoint("BOTTOMLEFT", 40, 20)
handRoll:SetText("Roll Abilities")

local handKeep = CreateFrame("Button", nil, hand, "UIPanelButtonTemplate")
handKeep:SetWidth(150); handKeep:SetHeight(22)
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

-- x of card i's centre when n cards are shown, as an offset from the frame's
-- own centre. Three cards centre on the middle one; four fill the row.
local function HandCardX(i, n)
    return (i - (n + 1) / 2) * HG.col
end

-- Deal-in animation. The die bounces in from off the left, rolls along the
-- row, and each card appears as the die reaches it; past the last card the
-- die runs on and fades out. Everything the OnUpdate below needs is worked
-- out here, where the layout is already known.
function hand.DealIn(n)
    if CW.handAnimatePending then
        CW.handAnimatePending = nil
        if n > 0 then
            -- x of each card's centre, as an offset from the frame's centre,
            -- and the y the row sits on
            local xs = {}
            for i = 1, n do xs[i] = HandCardX(i, n) end
            CW.handAnim = {
                t0 = GetTime(), phase = "in", n = n, xs = xs, popped = {},
                -- the row's own line, from the frame's centre: the cards hang
                -- HG.top from the top and are HG.die tall
                rowY = hand:GetHeight() / 2 + HG.top - HG.die / 2, spin = 0,
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

-- A slot with nothing on it, in either mode.
function hand.ClearSlot(slot)
    slot.abilityId = nil
    slot.spellId = nil
    slot.entryRef = nil
    slot.blockH = nil
    slot.glow:Hide(); slot.rays:Hide()
    slot.info:Clear()
    slot:Hide()
end

local function RenderHand()
    local list = OrderedHand()
    local n = math.min(#list, HAND_SLOTS)

    for i = 1, HAND_SLOTS do
        local slot = handSlots[i]
        local e = list[i]
        if e and i <= n then
            slot:ClearAllPoints()
            slot:SetPoint("TOP", hand, "TOP", HandCardX(i, n), HG.top)
            slot.abilityId = e.id
            slot.spellId = e.id
            slot.entryRef = e
            slot.rarity = e.rarity or 0
            hand.DressCard(slot)
            slot.lock:Show()
            if e.locked == 1 then
                -- closed GOLD padlock + gold halo = locked in
                slot.lock:SetTexture("Interface\\AddOns\\ClasslessWildcard\\lock_closed")
                slot.lock:SetVertexColor(1, 1, 1, 1)
                slot.ring:Show()
                slot.icon:SetVertexColor(1, 1, 1)
                slot.die:SetVertexColor(1, 1, 1)
            else
                -- open grey padlock, and the card sits back a little
                slot.lock:SetTexture("Interface\\AddOns\\ClasslessWildcard\\lock_open")
                slot.lock:SetVertexColor(1, 1, 1, 0.8)
                slot.ring:Hide()
                slot.icon:SetVertexColor(0.82, 0.82, 0.82)
                slot.die:SetVertexColor(0.86, 0.86, 0.86)
            end
            slot:Show()
        else
            hand.ClearSlot(slot)
        end
    end

    -- Under the deepest description on the row, not on the frame's bottom edge:
    -- a plate is drawn on its own card, three frame levels above these buttons,
    -- so a long description simply painted over them where they used to sit.
    local deepest = 0
    for i = 1, n do deepest = math.max(deepest, handSlots[i].blockH or 0) end
    local y = HG.top - HG.die - HG.gap + rvFX.PAD - deepest - 18
    handRoll:ClearAllPoints()
    handKeep:ClearAllPoints()
    handRoll:SetPoint("TOP", hand, "TOP", -84, y)
    handKeep:SetPoint("TOP", hand, "TOP", 84, y)

    hand.DealIn(n)
end
CW.RenderHand = RenderHand

-- in: bounce on from the left. roll: travel the row, dealing as it goes.
-- out: carry on past the last card and fade. pop: how long a card takes to
-- arrive once the die has reached it. lift: how far below its place a card
-- starts. spin: die frames per second (the atlas is 16 frames).
ANIM.HAND_IN_TIME, ANIM.HAND_ROLL_TIME, ANIM.HAND_OUT_TIME = 0.55, 0.95, 0.30
ANIM.HAND_POP_TIME, ANIM.HAND_LIFT, ANIM.HAND_BOUNCE, ANIM.HAND_SPIN_RATE = 0.24, 14, 30, 34
hand:SetScript("OnUpdate", function(self, elapsed)
    -- An epic or legendary card keeps its starburst turning for as long as the
    -- hand is open, deal or no deal, so this runs before the animation check.
    rvFX.handRot = (rvFX.handRot or 0) + (elapsed or 0)
    for i = 1, HAND_SLOTS do
        local slot = handSlots[i]
        if slot.rays:IsShown() then
            rvFX.Spin(slot.rays, rvFX.handRot * (slot.spinRate or 0.04) * math.pi * 2)
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
        a.spin = a.spin + (elapsed or 0) * ANIM.HAND_SPIN_RATE
        local idx = math.floor(a.spin) % 16
        handDie:SetTexCoord((idx % 8) / 8, (idx % 8 + 1) / 8,
                            math.floor(idx / 8) / 2, (math.floor(idx / 8) + 1) / 2)
    end

    if a.phase == "in" then
        local p = math.min(1, t / ANIM.HAND_IN_TIME)
        local e = 1 - (1 - p) * (1 - p) * (1 - p)          -- ease out, fast then settling
        x = a.fromX + (a.xs[1] - a.fromX) * e
        -- two decaying hops, touching down on the row at the end of each
        y = a.rowY + math.abs(math.sin(p * math.pi * 2)) * ANIM.HAND_BOUNCE * (1 - p)
        handDie:SetAlpha(p)
        if p >= 1 then a.phase = "roll"; a.t0 = now end
    elseif a.phase == "roll" then
        local p = math.min(1, t / ANIM.HAND_ROLL_TIME)
        x = a.xs[1] + (a.xs[a.n] - a.xs[1]) * p
        handDie:SetAlpha(1)
        if p >= 1 then a.phase = "out"; a.t0 = now end
    elseif a.phase == "out" then
        local p = math.min(1, t / ANIM.HAND_OUT_TIME)
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
            local q = since and math.min(1, (now - since) / ANIM.HAND_POP_TIME) or 0
            local e = 1 - (1 - q) * (1 - q)
            local lift = ANIM.HAND_LIFT + fx.pop * 0.6
            slot:SetAlpha(e)
            slot:ClearAllPoints()
            slot:SetPoint("TOP", hand, "TOP", a.xs[i], HG.top - (1 - e) * lift)
            local boost = since and math.max(0, 1 - (now - since) / rvFX.cardFlash) or 0
            rvFX.CardFX(slot, slot.rarity, boost, e)
            -- the deal is not over until the last flash has burned down
            if q < 1 or boost > 0 then settled = false end
        end
    end
    if settled then CW.handAnim = nil end
end)

handRoll:SetScript("OnClick", function()
    if CW.NoRerolls() then
        CW.SayNoRerolls()
        return
    end
    -- One command: the server rerolls every unlocked ability from its own
    -- state. Firing one RR per entry from this snapshot went stale as soon as
    -- the first landed, so the rest came back "You do not own that ability".
    Send("RRALL")
    CW.handAnimatePending = true -- deal the new cards in with the die spin
    Send("OWN")
end)
handKeep:SetScript("OnClick", function()
    -- just close it: the hand is the whole point of this screen, and dropping
    -- the Hero Advancement panel on top of a player who has finished with
    -- it is one modal too many. The panel is a click away on the minimap
    -- button whenever they want it.
    hand:Hide()
end)

hand:SetScript("OnShow", function()
    hand.ApplyLayers()
    -- the level free rolls end at is the server's to decide, so say what it says
    if CW.NoRerolls() then
        -- Dealt Hand: this is the hand, and it stays
        handHint:SetText("|cffff5544Dealt Hand|r: this is your hand. Nothing can be rerolled on this run.")
        handRoll:Disable()
    else
        handHint:SetText("Click an ability to lock it in: |cffffd100gold ring + closed padlock = kept|r." ..
            " Roll Abilities rerolls only the unlocked ones. Free until level "
            .. (CW.state.freeReroll or 10) .. "!")
        handRoll:Enable()
    end
    ClasslessWildcardCharDB = ClasslessWildcardCharDB or {}
    ClasslessWildcardCharDB.handSeen = true   -- opened by any route: don't auto-open again
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

-- One spell correction (an SF or SQ record, already split by ParseEntries).
function CW.ReadFix(f)
    local function num(i) return tonumber(f[i]) or 0 end
    return {
        cost = tonumber(f[2]), cast = num(3), cd = num(4),
        durBase = num(5), durMod = num(6),
        rangeBase = num(7), rangeMod = num(8),
        -- each pair is (what the client will print, what it should)
        pairs = { { num(9), num(10) }, { num(11), num(12) },
                  { num(13), num(14) } },
    }
end

local collectingArch = false

local function HandleMessage(msg)
    local p = SplitPipes(msg)
    local kind = p[1]

    if kind == "S" then
        local s = CW.state
        local wasLevel = s.level
        s.mode, s.ae, s.te, s.pity, s.chance = tonumber(p[2]) or 255, tonumber(p[3]) or 0, tonumber(p[4]) or 0, tonumber(p[5]) or 0, tonumber(p[6]) or 0
        s.scrolls, s.level, s.deadline = tonumber(p[7]) or 0, tonumber(p[8]) or 1, tonumber(p[9]) or 2
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
        -- the Help guide quotes the free-reroll and path-lock levels
        if CW.RefreshHelpText and CW.helpFly and CW.helpFly:IsShown() then CW.RefreshHelpText() end
        -- what a scroll staked on a talent reroll buys
        s.tuBase = tonumber(p[17]) or 0
        s.tuPerScroll = tonumber(p[18]) or 0
        s.tuMaxScrolls = tonumber(p[19]) or 0
        -- Rebirth: rank, ready now, gold price, heirlooms allowed
        s.rebirths = tonumber(p[20]) or 0
        s.rebirthReady = tonumber(p[21]) or 0
        s.rebirthPrice = tonumber(p[22]) or 0
        s.heirloomMax = tonumber(p[23]) or 1
        -- the challenge run
        s.run = tonumber(p[24]) or 0
        s.lives = tonumber(p[25]) or 0
        s.livesMax = tonumber(p[26]) or 0
        s.shards = tonumber(p[27]) or 0
        s.extraLife = tonumber(p[28]) or 0
        s.runReady = tonumber(p[29]) or 0
        s.hourglassLeft = tonumber(p[30]) or 0   -- Hourglass: seconds left on this level
        s.noRerolls = tonumber(p[31]) or 0        -- Dealt Hand: nothing may be rerolled
        s.customName = p[32] or ""                -- the player's own build, while it is followed
        s.autoShotOff = tonumber(p[33]) or 0      -- Settings: Auto Shot turned off for this character
        if CW.setFly and CW.setFly:IsShown() and CW.RenderSettings then CW.RenderSettings() end
        CW.hourglassAt = GetTime()
        -- the live run is named from the challenge list, which a fresh login
        -- has not fetched yet: ask once, so the header does not say "Challenge 3"
        if s.run > 0 and #CW.challenges == 0 and not CW._askedChallenges then
            CW._askedChallenges = true
            Send("CHL")
        end
        -- a scroll bought from the reveal changes what its own button says
        if reveal:IsShown() and rvFX.SetRerollButton then rvFX.SetRerollButton() end
        CW.UpdateBarsVisibility()
        -- the character sheet may have been drawn before we knew this
        if CW.RefreshPaperDoll then CW.RefreshPaperDoll() end
        UpdateStatus()
        -- A level-up opens rows that the level filter was hiding, so ask for
        -- the page again rather than leaving a stale list behind.
        if wasLevel and s.level ~= wasLevel and frame:IsShown() then
            if CW.abilScope == 1 then RequestAbil(CW.abilPage or 0) end
            if CW.talScope == 1 then RequestTal(CW.talPage or 0) end
        end
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
            CW.BeginOnboarding()
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
        -- tabs just arrived: point the pane at the selected class before asking
        -- for a page, or the panel opens showing one class's abilities beside
        -- another class's talents
        if CW.SyncTalentTabToClass then CW.SyncTalentTabToClass() end
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
        if CW.rebirthFly and CW.rebirthFly:IsShown() then CW.RenderRebirth() end

    elseif kind == "SF" then
        -- What a spell really costs, casts, waits and prints once the Hero's
        -- talents are counted. The client cannot work this out for a talent
        -- outside its own class: the modifier packet carries a class-mask bit
        -- and no spell family, so it matches those bits only against the
        -- chassis's family.
        -- A fresh list replaces everything, the one-off answers to SFQ
        -- included: the build changed, so those numbers may have too.
        if not CW._collectingFix then
            CW.spellFix, CW.spellFixByName, CW._collectingFix = {}, {}, true
            CW.spellFixAsked = {}
        end
        for _, f in ipairs(ParseEntries(p[2], 14)) do
            local id = tonumber(f[1])
            if id then
                CW.spellFix[id] = CW.ReadFix(f)
                local name, rank = GetSpellInfo(id)
                if name then
                    CW.spellFixByName[name .. "|" .. (rank or "")] = id
                end
            end
        end
    elseif kind == "SFE" then
        CW._collectingFix = false
        if CW.RefreshUsable then CW.RefreshUsable() end
    elseif kind == "SQ" then
        -- The answer to SFQ: one spell the panel showed before it was bought,
        -- which the login list (spells the Hero owns) never covers. "-" is a
        -- spell with nothing to correct. Kept by id only: the spellbook and
        -- action bar look spells up by name, and those are owned ones. The
        -- tooltip still up for it is drawn again, now with the true numbers.
        local id, rest = (p[2] or ""):match("^(%d+):(.*)$")
        id = tonumber(id)
        if id then
            if rest:sub(1, 1) ~= "-" then
                local f = ParseEntries(p[2], 14)[1]
                if f then CW.spellFix[id] = CW.ReadFix(f) end
            end
            if CW.tipSpell == id and GameTooltip:IsShown() and CW.spellFix[id] then
                -- Drawn again through the owner's own OnEnter, after a Hide:
                -- SetHyperlink with the link a shown tooltip already holds
                -- toggles it OFF (the client's chat-link toggle lives in it),
                -- which left the row under the mouse with no tooltip at all.
                -- The OnEnter also puts back the row's own hint line.
                local owner = GameTooltip:GetOwner()
                local enter = owner and owner.GetScript and owner:GetScript("OnEnter")
                GameTooltip:Hide()
                if enter then enter(owner) end
            elseif CW.spellFix[id] and CW.runBadge and GameTooltip:IsOwned(CW.runBadge) then
                CW.RunTooltip(CW.runBadge)   -- the run card quotes its reward ability
            end
        end

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
            CW.ShowArchetypeChoices()
        elseif archFly:IsShown() then
            RenderArchFly()
        end

    elseif kind == "ST" then
        local s = CW.stats
        -- Edits waiting on Apply survive a refresh (a level-up mid-edit), as
        -- long as they still fit the budget; with none waiting, the page
        -- starts again from what the server now holds.
        local kept
        if CW.statsPending then
            local edited, total = false, 0
            for i = 1, 5 do
                total = total + (CW.statsPending[i] or 0)
                if (CW.statsPending[i] or 0) ~= (s.alloc[i] or 0) then edited = true end
            end
            if edited then kept = { pending = CW.statsPending, total = total } end
        end
        s.budget, s.unspent, s.perPoint = tonumber(p[2]) or 0, tonumber(p[3]) or 0, tonumber(p[4]) or 1
        for i = 1, 5 do
            s.alloc[i] = tonumber(p[4 + i]) or 0
        end
        s.enabled = tonumber(p[10]) or 1
        -- fields 24-28: how much of each stat the Rebirth bonus gives
        s.rebirth = {}
        for i = 1, 5 do s.rebirth[i] = tonumber(p[23 + i]) or 0 end
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
        -- the character's real mana regeneration per 5 sec, gear and auras
        -- included: the client reads this off a field indexed by the power bar
        -- it is SHOWING, so on a Hero showing rage it sees nothing at all
        s.mp5 = tonumber(p[22])
        s.mp5Casting = tonumber(p[23])
        s.have = true   -- the rates are real now, not the shipped defaults
        -- the help panel quotes these rates, so rebuild it now they are known
        if CW.RefreshHelpText then CW.RefreshHelpText() end
        CW.statsPending = (kept and kept.total <= s.budget) and kept.pending or nil
        RenderList() -- refreshes the stats flyout when it is open

    elseif kind == "CFG" then
        -- classless pricing the browser needs to label costs honestly
        CW.talentCost = tonumber(p[2]) or 1
        CW.talentFlat = (tonumber(p[3]) or 0) == 1
        -- Whether Death Knight content is in the library. Absent from older
        -- servers, which is why the default is off rather than on: a missing
        -- field must not conjure a class button with nothing behind it.
        local dk = (tonumber(p[4]) or 0) == 1
        -- Absent from older servers, and absent means off: a Hero button with
        -- nothing behind it is worse than no button.
        local forged = (tonumber(p[5]) or 0) == 1
        if dk ~= CW.dkEnabled or forged ~= CW.forgedEnabled then
            CW.dkEnabled, CW.forgedEnabled = dk, forged
            CW.LayoutClassStrip()
        end
        -- the realm's rules, for the Help guide; absent fields keep the defaults
        local r = CW.rules
        local function num(i, key) local v = tonumber(p[i]); if v then r[key] = v end end
        num(6, "startAE"); num(7, "aeStart"); num(8, "aePer"); num(9, "teStart"); num(10, "tePer")
        for k = 1, 5 do
            local v = tonumber(p[10 + k]); if v then r.abilityCost[k] = v end
        end
        num(16, "wcStart"); num(17, "wcRollStart"); num(18, "rerollsPerLevel")
        num(19, "synBase"); num(20, "synInc"); num(21, "banRolls")
        num(22, "weightCommon"); num(23, "weightLegendary")
        num(24, "xpFirst"); num(25, "xpPerRank"); num(26, "xpMax")
        num(27, "statPct"); num(28, "statMax"); num(29, "maxLevel"); num(30, "defaultMode")
        num(31, "otherXpPerRank"); num(32, "otherXpMax")
        if CW.RefreshHelpText then CW.RefreshHelpText() end
        RenderList()

    elseif kind == "RV" then
        -- a wildcard roll happened: refresh state (reroll charges/scrolls
        -- changed) and play the d20 reveal
        Send("STATE")
        -- ...and whatever list is open, exactly as OK does below. A roll
        -- changes what the Hero owns, and the rows carry the owned rank: the
        -- talent list draws "1/2", the tooltip describes rank 1 and offers to
        -- teach a rank, while the server has already granted rank 2 and the
        -- game is applying it. Improved Disciplines read "30 secs" that way
        -- with Shield Wall already down to 240.
        if frame:IsShown() then CW.SetTab(CW.tab) end
        if p[2] == "A" then
            CW.EnqueueReveal({ isTalent = false, entry = tonumber(p[3]) or 0, spell = tonumber(p[3]) or 0,
                               rarity = tonumber(p[4]) or 0, flags = tonumber(p[5]) or 0 })
        elseif p[2] == "T" then
            CW.EnqueueReveal({ isTalent = true, entry = tonumber(p[3]) or 0, spell = tonumber(p[4]) or 0,
                               rarity = tonumber(p[5]) or 0, rank = tonumber(p[6]) or 1, flags = tonumber(p[7]) or 0,
                               maxRank = tonumber(p[8]) or 0 })
        end

    -- ---- challenge runs ----
    elseif kind == "CH" then
        if CW._collectingCh ~= "on" then
            CW.challenges, CW.challengesById = {}, {}
            CW._collectingCh = "on"
        end
        local c = {
            id = tonumber(p[2]) or 0, name = p[3] or "", lives = tonumber(p[4]) or 1,
            gold = tonumber(p[5]) or 0, rule = p[6] or "",
            best = tonumber(p[7]) or 0, finished = tonumber(p[8]) or 0,
            reward = tonumber(p[9]) or 0,   -- the ability it pays, a spell id
            title = p[10] or "",            -- "%s the Nemesis", as the client shows it
            path = tonumber(p[11]) or 255,  -- the path it asks for: 0, 1, or 255 for either
            vengeance = tonumber(p[12]) or 0,   -- Vengeance it asks for besides the level cap
            detail = "",                    -- how it plays, joined from CD pieces
            tips = "",                      -- advice, joined from CT pieces
        }
        tinsert(CW.challenges, c)
        CW.challengesById[c.id] = c
    elseif kind == "CD" or kind == "CT" then
        -- a piece of a challenge's full text (CD) or its tips (CT); pieces
        -- arrive in order and are joined with the space they were split on
        local c = CW.challengesById and CW.challengesById[tonumber(p[2]) or 0]
        local field = kind == "CD" and "detail" or "tips"
        if c and p[3] then
            c[field] = ((c[field] or "") == "" and p[3]) or (c[field] .. " " .. p[3])
        end
    elseif kind == "CHE" then
        CW._collectingCh = false
        if CW.runFly and CW.runFly:IsShown() then CW.RenderRuns(true) end
        CW.UpdateLives()   -- the live run's name comes from this list
        if CW.UpdateTracker then CW.UpdateTracker() end
    elseif kind == "RT" then
        CW.ReadTracker(p)
    elseif kind == "NG" then
        CW.ReadNemesisGuids(p[2])
    elseif kind == "NLB" then
        CW.nemesisListNew = {}
    elseif kind == "NL" then
        tinsert(CW.nemesisListNew or {}, { name = p[2] or "", title = p[3] or "", kind = p[4] or "",
            levels = tonumber(p[5]) or 0, strengths = p[6] or "?", weakness = p[7] or "?",
            zone = p[8] or "", x = tonumber(p[9]) or 0, y = tonumber(p[10]) or 0 })
    elseif kind == "NLE" then
        CW.nemesisList = CW.nemesisListNew or {}
        CW.nemesisListNew = nil
        CW.NemesisPins()
        if CW.UpdateTracker then CW.UpdateTracker() end
    elseif kind == "NT" then
        CW.ReadNemesisCharm(p)
    elseif kind == "NX" then
        CW.ReadNemesisTraitNums(p)
    elseif kind == "NK" then
        CW.NemesisSlain(p)
    elseif kind == "NV" then
        CW.VendettaSworn(p)
    elseif kind == "APA" or kind == "APT" or kind == "APW" or kind == "APE" then
        CW.ReadArchPlan(kind, p)
    elseif kind == "AMA" or kind == "AMT" or kind == "AME" then
        CW.ReadMyBuild(kind, p)
    elseif kind == "LD" then
        -- Loaded Die landed: "LD|roll|sides|rerolled"
        local text, r, g, b = CW.LoadedDieText(tonumber(p[2]) or 0, tonumber(p[3]) or 20, tonumber(p[4]) == 1)
        UIErrorsFrame:AddMessage(text, r, g, b)
        if (tonumber(p[2]) or 0) == (tonumber(p[3]) or 20) and PlaySound then pcall(PlaySound, "LEVELUPSOUND") end
    elseif kind == "AW" then
        -- the armor weight in force, for the auras' hover text
        CW.ReadArmorWeight(p[2])
        if CW.RefreshHelpText then CW.RefreshHelpText() end   -- the guide quotes the full-set numbers
    elseif kind == "RD" then
        -- a life lost: lives left, lives at the start, what the rule did
        local lives, max, what = tonumber(p[2]) or 0, tonumber(p[3]) or 0, p[4] or ""
        local head = CW.Unlimited(max) and "|cffff4444You died.|r The run goes on."
            or ("|cffff4444A life lost.|r " .. lives .. " of " .. max .. (lives == 1 and " life" or " lives") .. " left.")
        StaticPopup_Show("CW_RUN_DEATH", head .. (what ~= "" and ("\n\n" .. what) or ""))
        Send("STATE")
    elseif kind == "RE" then
        -- the run is over: what it paid, and what is new
        CW.ShowSummary(CW.RunEndSpec(p))
        if PlaySound then pcall(PlaySound, tonumber(p[2]) == 1 and "LEVELUPSOUND" or "igQuestFailed") end
        Send("STATE")
        Send("OWN")
    elseif kind == "RB" then
        -- a Rebirth went through: the new life, summed up
        CW.ShowSummary(CW.RebirthDoneSpec(p))
        if PlaySound then pcall(PlaySound, "LEVELUPSOUND") end

    elseif kind == "OK" then
        if p[2] == "MODE" then
            CW.pendingHand = true -- open the starting hand once state arrives
        end
        -- the new life has begun: the picker has nothing left to pick
        if p[2] == "REBIRTH" and CW.rebirthFly then CW.rebirthFly:Hide() end
        if p[2] == "RUN" then
            if CW.rebirthFly then CW.rebirthFly:Hide() end
            if CW.runFly then CW.runFly:Hide() end
        end
        if p[2] == "BUYLIFE" and CW.runFly and CW.runFly:IsShown() then CW.RenderRuns() end
        -- refresh whatever list is open after a successful operation
        if frame:IsShown() then CW.SetTab(CW.tab) end
        -- LOCK is the exception: the server pushes the owned list itself, so
        -- asking for it again here would only be a second copy of the answer
        if hand:IsShown() and p[2] ~= "LOCK" then Send("OWN") end

    elseif kind == "ERR" then
        Print("|cffff4444" .. (p[2] or "Error") .. "|r")
        -- a refused reroll must not leave the die spinning forever
        if CW.CancelReroll then CW.CancelReroll() end
        -- A refusal means this client and the server disagreed about
        -- something. Whatever was drawn from a guess -- a padlock, above all
        -- -- goes back to being drawn from the server's answer.
        Send("OWN")
    end
end

-- ---------------------------------------------------------------------------
-- Tooltip corrections
--
-- A Hero's talents come from every class, and the client will not apply their
-- modifiers to a spell tooltip: SMSG_SET_FLAT_SPELL_MODIFIER carries a
-- class-mask bit and no family, and the client only ever expected its own
-- class's talents. Thunder Clap kept reading 20 Rage with Improved Thunder
-- Clap at 3/3 while the server charged 16.
--
-- So the server sends the numbers (SC records) and this puts them on screen.
-- The cost line is rewritten in place; everything else is appended, because
-- rewriting a cooldown or a cast time by pattern would be guessing at formats
-- that change with locale and magnitude.
-- ---------------------------------------------------------------------------
do
    -- One table for the helpers below. Lua 5.1 allows a function only
    -- 200 locals and this file sits near that ceiling, so a block that
    -- wants eleven of them takes one and hangs them off it.
    local T = {}
    CW.spellFix = CW.spellFix or {}
    CW.spellFixByName = CW.spellFixByName or {}
    CW.spellFixAsked = CW.spellFixAsked or {}   -- spells already put to the server with SFQ

    -- the client's own power names, so the cost line is found without matching
    -- English. Anything absent is simply skipped.
    local POWER_WORDS = {}
    for _, g in ipairs({ "MANA", "RAGE", "ENERGY", "FOCUS", "RUNIC_POWER", "HEALTH", "RUNES" }) do
        local w = _G[g]
        if type(w) == "string" and w ~= "" then POWER_WORDS[#POWER_WORDS + 1] = w end
    end

    function T.fixFor(spellId)
        return spellId and CW.spellFix[spellId] or nil
    end

    -- The client builds "5 min cooldown" from SPELL_RECAST_TIME_MIN, which is
    -- "%.3g min cooldown" here and something else entirely on a Russian
    -- client. Split that global around its placeholder and we have the exact
    -- prefix and suffix the client just wrote, in the player's own locale --
    -- enough to FIND the line it wrote and to write the line back the same
    -- way. Nothing here types a format out.
    -- Split a format string around its FIRST placeholder, whatever that
    -- placeholder is. enUS writes "%.3g min cooldown" but nothing promises
    -- another locale uses the same conversion, and SPELL_RANGE_DUAL uses the
    -- positional "%1$s" form, so the whole shape is matched rather than one
    -- hard-coded spec. Returns nil when there is no placeholder at all.
    T.SPEC = "%%%d?%$?[-+ #0]*%d*%.?%d*[diouxXeEfgGqcs]"

    function T.fmtParts(fmt)
        if type(fmt) ~= "string" then return nil end
        local at, stop = fmt:find(T.SPEC)
        if not at then return nil end
        return fmt:sub(1, at - 1), fmt:sub(stop + 1)
    end

    -- The line the client wrote for this format, and ONLY that line: prefix,
    -- suffix, and a bare number between them. Without the number test,
    -- "Melee: 5 yd range" (SPELL_RANGE_DUAL) matches SPELL_RANGE's shape and
    -- the rewrite would throw away the "Melee:" half.
    function T.looksLike(text, fmt)
        local pre, suf = T.fmtParts(fmt)
        if not pre then return false end
        if #pre > 0 and text:sub(1, #pre) ~= pre then return false end
        if #suf > 0 and text:sub(-#suf) ~= suf then return false end
        local middle = text:sub(#pre + 1, #text - #suf)
        return middle:match("^%s*%-?[%d%.,]+%s*$") ~= nil
    end

    -- Walk both columns. A spell tooltip puts the cost at the right of line 1
    -- and the cooldown at the right of line 2, with the cast time on the left
    -- beside it, but a talent-modified rank or a tooltip raised from the panel
    -- can shift them, so neither column nor line number is assumed.
    function T.eachLine(tip, fn)
        local name = tip:GetName()
        for i = 1, 8 do
            for _, side in ipairs({ "TextLeft", "TextRight" }) do
                local line = _G[name .. side .. i]
                local text = line and line:GetText()
                if text and text ~= "" and fn(line, text) then return true end
            end
        end
        return false
    end

    -- Replace the line the client wrote for `fmts` with `newText`.
    function T.replaceLine(tip, fmts, newText)
        if not newText then return end
        T.eachLine(tip, function(line, text)
            for _, fmt in ipairs(fmts) do
                if T.looksLike(text, fmt) then
                    line:SetText(newText)
                    return true
                end
            end
        end)
    end

    -- Same minute/second split the client uses, so 240000 comes back as
    -- "4 min cooldown" and 6000 as "6 sec cooldown".
    function T.timeText(ms, secFmt, minFmt)
        local sec = ms / 1000
        if sec >= 60 and type(minFmt) == "string" then
            return string.format(minFmt, sec / 60)
        end
        if type(secFmt) == "string" then
            return string.format(secFmt, sec)
        end
        return nil
    end

    -- Swap the leading number on the line that names a power, leaving the
    -- localised unit word untouched.
    function T.rewriteCost(tip, cost)
        if not cost then return end
        T.eachLine(tip, function(line, text)
            for _, word in ipairs(POWER_WORDS) do
                -- The power's own localised name anchors the line; the number
                -- is then the first one on it, wherever the locale puts it.
                -- enUS writes "20 Rage", and nothing says every locale leads
                -- with the number.
                if text:find(word, 1, true) and text:find("%d") then
                    line:SetText((text:gsub("%d+", tostring(cost), 1)))
                    return true
                end
            end
        end)
    end

    -- Find a number in a line as a WHOLE number: "5" must not match inside
    -- "55" or "1.5". Returns how many standalone times it occurs and where the
    -- last one starts.
    -- A whole number must be written "12", never "12.0": the client prints
    -- integers and a division here produces a float.
    function T.numText(v)
        if v == math.floor(v) then return string.format("%d", v) end
        return tostring(v)
    end

    function T.findStandalone(text, num)
        local want = T.numText(num)
        local from, count, at = 1, 0, nil
        while true do
            local i, j = text:find(want, from, true)
            if not i then break end
            local before = (i > 1) and text:sub(i - 1, i - 1) or ""
            local after = text:sub(j + 1, j + 1)
            if not before:match("[%d%.]") and not after:match("[%d%.]") then
                count, at = count + 1, i
            end
            from = j + 1
        end
        return count, at
    end

    -- Swap a number the description printed for the one the Hero's talents
    -- actually give. Only when it appears EXACTLY ONCE across the tooltip: a
    -- sentence that says "5" twice, or a value the client never printed
    -- because it folded spell power into it, is left exactly as it is. A wrong
    -- number is worse than an uncorrected one.
    function T.substituteOnce(tip, from, to)
        if not from or not to or from == 0 or from == to then return end
        local name, total, hitLine, hitAt = tip:GetName(), 0, nil, nil
        for i = 2, 8 do
            local line = _G[name .. "TextLeft" .. i]
            local text = line and line:GetText()
            if text and text ~= "" then
                local n, at = T.findStandalone(text, from)
                if n > 0 then
                    total, hitLine, hitAt = total + n, line, at
                end
            end
        end
        if total ~= 1 or not hitLine then return end
        local text = hitLine:GetText()
        hitLine:SetText(text:sub(1, hitAt - 1) .. T.numText(to)
                        .. text:sub(hitAt + #T.numText(from)))
    end

    function T.decorate(tip, spellId)
        local fix = T.fixFor(spellId)
        if not fix then return end
        T.rewriteCost(tip, fix.cost)

        -- Cooldown, cast time and range are corrected IN PLACE, on the line the
        -- client itself wrote and in the format it used. Nothing is appended:
        -- the tooltip reads the way it would on a character whose own class
        -- owned the talent.
        if fix.cd and fix.cd > 0 then
            T.replaceLine(tip, { _G.SPELL_RECAST_TIME_MIN, _G.SPELL_RECAST_TIME_SEC },
                        T.timeText(fix.cd, _G.SPELL_RECAST_TIME_SEC,
                                         _G.SPELL_RECAST_TIME_MIN))
        end
        if fix.cast and fix.cast > 0 then
            T.replaceLine(tip, { _G.SPELL_CAST_TIME_MIN, _G.SPELL_CAST_TIME_SEC },
                        T.timeText(fix.cast, _G.SPELL_CAST_TIME_SEC,
                                         _G.SPELL_CAST_TIME_MIN))
        end
        if fix.rangeMod and fix.rangeMod > 0 and type(_G.SPELL_RANGE) == "string" then
            T.replaceLine(tip, { _G.SPELL_RANGE },
                        string.format(_G.SPELL_RANGE, fix.rangeMod))
        end

        -- The numbers inside the sentence. $s1/$s2/$s3 are the effect values
        -- and $d the duration; the server sends what the client will print
        -- beside what it should, and the swap is refused unless it is
        -- unambiguous.
        if fix.pairs then
            for _, pair in ipairs(fix.pairs) do
                T.substituteOnce(tip, pair[1], pair[2])
            end
        end
        if fix.durBase and fix.durBase > 0 and fix.durMod and fix.durMod > 0
           and fix.durBase ~= fix.durMod then
            local was, now = fix.durBase / 1000, fix.durMod / 1000
            -- only whole seconds: the client writes fractions its own way
            if was == math.floor(was) and now == math.floor(now) then
                T.substituteOnce(tip, was, now)
            end
        end
        -- Crit chance, threat, crit damage and damage-over-time multipliers are
        -- deliberately absent. A stock tooltip does not print them for the
        -- class that owns the talent either; the talent's own tooltip says what
        -- it does.
    end

    -- exposed so the harness can drive it: this is the one piece whose output
    -- the player reads directly, and its cost rewrite is easy to get subtly wrong
    CW.ApplyTooltipFix = T.decorate

    -- The spellbook hands us a book slot, the action bar an action slot; both
    -- resolve to a spell name and rank, and CW.spellFixByName is keyed on that
    -- because 3.3.5 gives no way to read a spell id back off a tooltip.
    local function idFromBook(slot, book)
        local name, rank = GetSpellName(slot, book)
        if not name then return nil end
        return CW.spellFixByName[name .. "|" .. (rank or "")]
    end

    if GameTooltip and hooksecurefunc then
        hooksecurefunc(GameTooltip, "SetSpell", function(self, slot, book)
            T.decorate(self, idFromBook(slot, book))
        end)
        -- Every tooltip the panel itself raises goes through SetHyperlink
        -- ("spell:<id>"), which hands us the id outright -- no name matching.
        -- Missing this hook is why the Abilities list still read 20 Rage.
        --
        -- A spell the Hero does not own yet has no correction from the login
        -- list, and the client's copy of it is the client patch's lowered one:
        -- the Abilities list read Heroic Strike at 9 rage and Revenge at a
        -- 1 sec cooldown. So the first time one comes up without a record the
        -- server is asked (SFQ), once, and its answer (SQ) draws this tooltip
        -- again if it is still up.
        hooksecurefunc(GameTooltip, "SetHyperlink", function(self, link)
            local id = link and tonumber(link:match("^spell:(%d+)"))
            if not id then return end
            if self == GameTooltip then CW.tipSpell = id end
            if T.fixFor(id) then
                T.decorate(self, id)
            elseif not CW.spellFixAsked[id] then
                CW.spellFixAsked[id] = true
                Send("SFQ " .. id)
            end
        end)
        -- the tooltip moved on: an answer arriving now must not redraw it
        GameTooltip:HookScript("OnTooltipCleared", function() CW.tipSpell = nil end)
        GameTooltip:HookScript("OnHide", function() CW.tipSpell = nil end)
        hooksecurefunc(GameTooltip, "SetAction", function(self, slot)
            local kind, id = GetActionInfo(slot)
            if kind ~= "spell" or not id or id == 0 then return end
            local name, rank = GetSpellName(id, BOOKTYPE_SPELL)
            if not name then return end
            T.decorate(self, CW.spellFixByName[name .. "|" .. (rank or "")])
        end)
        -- The Reborn aura's hover text. Its row holds no numbers, since they
        -- depend on the rank and the realm's config, so the text is written
        -- here from the aura's stack count (the rank, on any unit) and the
        -- same formulas as RebirthXpPct and ApplyRebirthMods.
        local function rebornTip(self, unit, index, filter)
            local _, _, _, count, _, _, _, _, _, _, id = UnitAura(unit, index, filter)
            -- the Armor aura on the player: everything the armor worn gives
            -- now, summed from the server's AW report. Before the first
            -- report, and on anyone else, the row's own text stands.
            if id == CW.ARMOR_DISPLAY then
                local lines = unit and UnitIsUnit(unit, "player") and CW.ArmorTip()
                if lines then
                    self:ClearLines()
                    for _, l in ipairs(lines) do
                        if l.right then
                            self:AddDoubleLine(l[1], l.right, l[2], l[3], l[4], 1, 1, 1)
                        else
                            self:AddLine(l[1], l[2], l[3], l[4], true)
                        end
                    end
                    self:Show()
                end
                return
            end
            if id ~= CW.REBIRTH_AURA then return end
            local lines = CW.RebirthAuraTip(math.max(1, tonumber(count) or 1))
            self:ClearLines()
            self:AddLine(lines[1], 1, 1, 1)
            for i = 2, #lines do self:AddLine(lines[i], 1, 0.82, 0, true) end
            self:Show()
        end
        hooksecurefunc(GameTooltip, "SetUnitAura", rebornTip)
        hooksecurefunc(GameTooltip, "SetUnitBuff", function(self, unit, index, filter)
            rebornTip(self, unit, index, filter and ("HELPFUL " .. filter) or "HELPFUL")
        end)
        hooksecurefunc(GameTooltip, "SetUnitDebuff", function(self, unit, index, filter)
            rebornTip(self, unit, index, filter and ("HARMFUL " .. filter) or "HARMFUL")
        end)
    end
end

-- Armor weight (gen_forged_spells.py's ARMOR_WEIGHTS): four hidden auras do
-- the work, one per armor type, and the one Armor aura (ARMOR_DISPLAY) is what
-- the buff bar shows. Each type's effects in its row's order, named for the
-- hover text; a speed reads "% slower" or "% faster", anything else "+%".
-- Words only: every number comes from the server's AW report.
CW.ARMOR_DISPLAY = 962042
CW.ARMOR_WEIGHT_TEXT = {
    [962043] = { armor = "plate",   effects = { "Casting", "Attacks" } },
    [962044] = { armor = "mail",    effects = { "Casting", "Attacks" } },
    [962045] = { armor = "leather", effects = { "Casting", "Attacks", "Dodge" } },
    [962046] = { armor = "cloth",   effects = { "Spell critical strike chance", "Mana regeneration" } },
}
-- the order the summed effects are listed in, and which of them are speeds
CW.ARMOR_EFFECTS = {
    { "Casting", true }, { "Attacks", true }, { "Dodge" },
    { "Spell critical strike chance" }, { "Mana regeneration" },
}
CW.armorWeight = {}   -- aura id -> { pieces, now = {...}, full = {...} }, from "AW"

-- "AW|aura:pieces:in force,...:full set,...;..."
function CW.ReadArmorWeight(list)
    CW.armorWeight = {}
    for aura, pieces, now, full in string.gmatch(list or "", "(%d+):(%d+):([^:;]*):([^:;]*);") do
        local entry = { pieces = tonumber(pieces), now = {}, full = {} }
        for v in string.gmatch(now, "[^,]+") do tinsert(entry.now, tonumber(v)) end
        for v in string.gmatch(full, "[^,]+") do tinsert(entry.full, tonumber(v)) end
        CW.armorWeight[tonumber(aura)] = entry
    end
end

-- The Armor aura's hover text, as lines { text, r, g, b, right = text }:
-- each armor type worn with its pieces of eight, every effect of it as what
-- the pieces give now beside what a full set gives, then (when more than one
-- type is worn) everything added together. Speeds from different types
-- multiply, as they do in game; the rest add. Every number is the server's,
-- conf overrides included. nil until the server has reported.
function CW.ArmorTip()
    local speed = {}
    for _, e in ipairs(CW.ARMOR_EFFECTS) do speed[e[1]] = e[2] or false end
    local types, sums, mult = {}, {}, {}
    local reported = false
    for _, aura in ipairs({ 962043, 962044, 962045, 962046 }) do
        local data, text = CW.armorWeight[aura], CW.ARMOR_WEIGHT_TEXT[aura]
        if data and text then
            reported = true
            if data.pieces > 0 then tinsert(types, { data = data, text = text }) end
            for i, label in ipairs(text.effects) do
                local v = data.now[i] or 0
                sums[label] = (sums[label] or 0) + v
                -- a slow lengthens by (1 + v), a haste shortens by 1 / (1 + v)
                local f = v < 0 and (1 - v / 100) or 1 / (1 + v / 100)
                mult[label] = (mult[label] or 1) * f
            end
        end
    end
    if not reported then return nil end

    local WHITE, GOLD, GREY = { 1, 1, 1 }, { 1, 0.82, 0 }, { 0.6, 0.6, 0.6 }
    local function line(t, c, right) return { t, c[1], c[2], c[3], right = right } end
    local lines = { line(GetSpellInfo(CW.ARMOR_DISPLAY) or "Armor Weight", WHITE) }
    if #types == 0 then
        tinsert(lines, line("You wear no armor that counts.", GREY))
        return lines
    end

    -- Numbers coloured by what they do to you: red costs, green helps, grey
    -- nothing. The full set sits after the slash in grey, a reference beside
    -- the number that counts.
    local function hue(cost, value)
        if value == 0 then return "|cff999999" end
        return cost and "|cffff6666" or "|cff66ff66"
    end
    local function pair(nowText, fullText, cost, now)
        return hue(cost, now) .. nowText .. "|r|cff999999 / " .. fullText .. "|r"
    end

    -- each type: its pieces, and every effect as now / full set
    tinsert(lines, line("Your armor", GREY, "|cff999999now / full set|r"))
    for _, t in ipairs(types) do
        local name = string.upper(string.sub(t.text.armor, 1, 1)) .. string.sub(t.text.armor, 2)
        tinsert(lines, line(name .. "  " .. t.data.pieces .. "/8", GOLD))
        for i, label in ipairs(t.text.effects) do
            local now, full = t.data.now[i] or 0, t.data.full[i] or 0
            if full ~= 0 then
                local left, right
                if speed[label] then
                    -- the full set's sign names the direction; both numbers
                    -- read as amounts of it
                    left = label .. (full < 0 and " slower" or " faster")
                    right = pair(math.abs(now) .. "%", math.abs(full) .. "%", full < 0, now)
                else
                    left = label
                    right = pair((now > 0 and "+" or "") .. now .. "%", (full > 0 and "+" or "") .. full .. "%",
                        full < 0, now)
                end
                tinsert(lines, line("  " .. left, WHITE, right))
            end
        end
    end

    -- together, when more than one type adds into the same effects
    if #types > 1 then
        tinsert(lines, line("All together", GOLD))
        for _, e in ipairs(CW.ARMOR_EFFECTS) do
            local label = e[1]
            if speed[label] and mult[label] then
                local m = mult[label]
                local pct = math.floor((m >= 1 and (m - 1) or (1 / m - 1)) * 100 + 0.5)
                if pct > 0 then
                    tinsert(lines, line("  " .. label, WHITE,
                        hue(m >= 1, pct) .. pct .. "% " .. (m >= 1 and "slower" or "faster") .. "|r"))
                end
            elseif not speed[label] and (sums[label] or 0) ~= 0 then
                tinsert(lines, line("  " .. label, WHITE,
                    hue(sums[label] < 0, sums[label]) .. (sums[label] > 0 and "+" or "") .. sums[label] .. "%|r"))
            end
        end
    end
    return lines
end

-- The Reborn aura (gen_forged_spells.py's REBIRTH_AURA_ID) and its hover text
-- for a rank: the title line, then what the rank gives on this realm.
CW.REBIRTH_AURA = 962047
function CW.RebirthAuraTip(rank)
    local r = CW.rules
    local kill = math.min(r.xpFirst + r.xpPerRank * (rank - 1), r.xpMax)
    local other = math.min(r.otherXpPerRank * rank, r.otherXpMax)
    local stat = math.min(r.statPct * rank, r.statMax)
    return {
        "Reborn",
        "Rebirth " .. rank .. ".",
        "+" .. kill .. "% experience from kills and dungeons.",
        "+" .. other .. "% experience from quests, exploration and battlegrounds.",
        "+" .. stat .. "% to every primary stat.",
    }
end

-- ---------------------------------------------------------------------------
-- Action buttons and the true cost
--
-- The client patch lowers its copy of every talent-reducible cost to the least
-- any build could pay, so a Hero holding the talent is not refused before the
-- server is asked. The bar colours a button from that copy, though: Heroic
-- Strike lit up at 9 rage while the server wanted 15 and refused the press.
-- The server's cost for every owned spell is in CW.spellFix, so a button whose
-- spell costs more than the Hero has is drawn the way the client draws "not
-- enough mana" itself.
--
-- ActionButton_UpdateUsable only runs when the CLIENT thinks usability changed,
-- and by its copy nothing changes between 9 and 15 rage. So every button it has
-- drawn is drawn again whenever the player's power moves.
-- ---------------------------------------------------------------------------
do
    local U = { buttons = {} }

    function U.short(action)
        local kind, slot = GetActionInfo(action)
        if kind ~= "spell" or not slot or slot == 0 then return false end
        local name, rank = GetSpellName(slot, BOOKTYPE_SPELL)
        if not name then return false end
        local id = CW.spellFixByName[name .. "|" .. (rank or "")]
        local fix = id and CW.spellFix[id]
        if not fix or not fix.cost or fix.cost <= 0 then return false end
        local powerType = select(6, GetSpellInfo(id))
        if type(powerType) ~= "number" or powerType < 0 then return false end
        return UnitPower("player", powerType) < fix.cost
    end

    function CW.RefreshUsable()
        for button in pairs(U.buttons) do
            if button.action and button:IsVisible() then ActionButton_UpdateUsable(button) end
        end
    end

    if ActionButton_UpdateUsable and hooksecurefunc then
        hooksecurefunc("ActionButton_UpdateUsable", function(self)
            local name = self:GetName()
            if not name or not self.action then return end
            U.buttons[self] = true
            if IsUsableAction(self.action) and U.short(self.action) then
                _G[name .. "Icon"]:SetVertexColor(0.5, 0.5, 1.0)
                _G[name .. "NormalTexture"]:SetVertexColor(0.5, 0.5, 1.0)
            end
        end)
        local watch = CreateFrame("Frame")
        for _, e in ipairs({ "UNIT_MANA", "UNIT_RAGE", "UNIT_ENERGY", "UNIT_FOCUS", "UNIT_RUNIC_POWER" }) do
            watch:RegisterEvent(e)
        end
        watch:SetScript("OnEvent", function(_, _, unit)
            if unit == "player" then CW.RefreshUsable() end
        end)
    end
end

-- ---------------------------------------------------------------------------
-- The login unlearn spam
--
-- A Hero keeps only what it earned here, so StripUnearnedSpells takes back the
-- class-library spells the chassis handed out for free -- Holy Light, Seal of
-- Righteousness and the rest of the paladin starter kit. Anything bought or
-- rolled through the system is in the earned set and is never touched.
--
-- The server cannot silence the line. It sends SMSG_REMOVED_SPELL and the
-- client prints ERR_SPELL_UNLEARNED_S itself, so this is a chat filter. It is
-- deliberately narrow: only that one message, and only for a few seconds after
-- entering the world, which is the only time the stripping runs. Unlearn an
-- ability yourself from the panel later and you still get told.
-- ---------------------------------------------------------------------------
do
    local QUIET_FOR = 8            -- seconds after entering the world
    local quietUntil = 0

    -- Built from the global string, not typed out, so it still matches when
    -- the client is not English. Escape the magic characters, then let %s be
    -- the spell name.
    local pattern
    local raw = _G.ERR_SPELL_UNLEARNED_S
    if type(raw) == "string" then
        -- escape the magic characters, then let the %s placeholder stand for
        -- the spell name. The second gsub pattern is "%%s": %% matches one
        -- literal per cent, so it finds the %s that the first gsub left alone
        -- (per cent is not a magic character and is not escaped above).
        pattern = raw:gsub("([%^%$%(%)%.%[%]%*%+%-%?])", "%%%1"):gsub("%%s", ".+")
    end

    function CW.QuietUnlearnsForLogin()
        quietUntil = GetTime() + QUIET_FOR
    end

    if pattern and ChatFrame_AddMessageEventFilter then
        ChatFrame_AddMessageEventFilter("CHAT_MSG_SYSTEM", function(_, _, msg)
            if msg and GetTime() < quietUntil and msg:match(pattern) then
                return true          -- swallowed
            end
            return false
        end)
    end
end

-- ---------------------------------------------------------------------------
-- Challenge tracker
--
-- Your nemesis is one creature, and the client keeps the elite dragon per kind
-- of creature, so the server sends the GUIDs of the nemeses near you
-- ("NG|guid,guid") and the target and focus frames give the elite border to
-- those alone. A rare nemesis wears the rare elite border.
CW.nemesisGuids, CW.nemesisBorderOn = {}, {}
-- Elite World (challenge 2) makes every enemy a Hero can fight an elite, a
-- rare a rare elite, and a nemesis is a rare elite: the server changes the
-- creature itself, but the client draws the dragon from the creature's kind,
-- so these frames draw it here. Read off the unit, so it needs nothing sent.
CW.ELITE_WORLD = 2
function CW.MadeEliteBorder(unit, class)
    local guid = UnitGUID(unit)
    if guid and CW.nemesisGuids[guid] then
        return "Interface\\TargetingFrame\\UI-TargetingFrame-Rare-Elite"
    end
    if CW.state and CW.state.run == CW.ELITE_WORLD and UnitCanAttack("player", unit)
        and not UnitPlayerControlled(unit) and UnitCreatureType(unit) ~= "Critter" then
        if class == "rare" then return "Interface\\TargetingFrame\\UI-TargetingFrame-Rare-Elite" end
        if class == "normal" then return "Interface\\TargetingFrame\\UI-TargetingFrame-Elite" end
    end
end

function CW.NemesisBorder(frame, forceNormal, fromStock)
    if type(frame) ~= "table" or not frame.borderTexture or not frame.unit then return end
    CW.NemesisTitleLine(frame)
    local class = UnitClassification(frame.unit)
    local made = not forceNormal and CW.MadeEliteBorder(frame.unit, class) or nil
    local mark = made and true or nil
    local was = CW.nemesisBorderOn[frame]
    CW.nemesisBorderOn[frame] = mark
    -- the client's own pass has just drawn its border: nothing of ours to undo
    if not mark and (fromStock or not was) then return end
    local texture
    if mark then
        texture = made
    elseif class == "worldboss" or class == "elite" then
        texture = "Interface\\TargetingFrame\\UI-TargetingFrame-Elite"
    elseif class == "rareelite" then
        texture = "Interface\\TargetingFrame\\UI-TargetingFrame-Rare-Elite"
    elseif class == "rare" then
        texture = "Interface\\TargetingFrame\\UI-TargetingFrame-Rare"
    end
    local dragon = texture and not forceNormal
    frame.borderTexture:SetTexture(dragon and texture or "Interface\\TargetingFrame\\UI-TargetingFrame")
    -- the threat glow follows the border's shape, as TargetFrame_CheckClassification has it
    local glow = frame.threatIndicator
    if glow then
        if dragon then
            glow:SetTexCoord(0, 0.9453125, 0.181640625, 0.400390625)
            glow:SetWidth(242)
            glow:SetHeight(112)
            glow:SetPoint("TOPLEFT", frame, "TOPLEFT", -22, 9)
        else
            glow:SetTexCoord(0, 0.9453125, 0, 0.181640625)
            glow:SetWidth(242)
            glow:SetHeight(93)
            glow:SetPoint("TOPLEFT", frame, "TOPLEFT", -24, 0)
        end
    end
end
-- "0xGUID=title,...": the Hero's own nemeses, and what each is called
-- A challenge's long text, as the page draws it: the server marks a new
-- paragraph with " ^ " and a heading with ~Words~ (one message cannot carry a
-- line break or a colour code).
function CW.FormatChallengeText(s)
    s = string.gsub(s or "", "%s*%^%s*", "\n\n")
    s = string.gsub(s, "~([^~]+)~%s*", "|cffffd100%1|r\n")
    return s
end

function CW.ReadNemesisGuids(list)
    local set = {}
    for item in string.gmatch(list or "", "[^,]+") do
        local guid, title = string.match(item, "^([^=]+)=?(.*)$")
        if guid then set[guid] = title ~= "" and title or true end
    end
    CW.nemesisGuids = set
    CW.NemesisBorder(TargetFrame)
    CW.NemesisBorder(FocusFrame)
end
-- its title, under its name on the target and focus frames
function CW.NemesisTitleLine(frame)
    if type(frame) ~= "table" or not frame.unit or not frame.CreateFontString then return end
    local guid = UnitGUID(frame.unit)
    local title = guid and CW.nemesisGuids[guid]
    if type(title) ~= "string" then
        if frame.cwTitle then frame.cwTitle:Hide() end
        return
    end
    if not frame.cwTitle then
        -- its own frame, above the one holding the name and the border: on
        -- the target frame itself the elite dragon draws over it
        local holder = CreateFrame("Frame", nil, frame)
        holder:SetAllPoints(frame)
        local over = frame.name and frame.name.GetParent and frame.name:GetParent()
        holder:SetFrameLevel(((over and over.GetFrameLevel and over:GetFrameLevel()) or frame:GetFrameLevel()) + 5)
        frame.cwTitleHolder = holder
        frame.cwTitle = holder:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
        frame.cwTitle:SetPoint("BOTTOM", frame.name or frame, "TOP", 0, 2)
        frame.cwTitle:SetTextColor(1, 0.53, 0)
        frame.cwTitle:SetShadowColor(0, 0, 0, 1)
        frame.cwTitle:SetShadowOffset(1, -1)
    end
    frame.cwTitle:SetText("<" .. title .. ">")
    frame.cwTitle:Show()
end

-- Trophies and the Nemesis Charm. Their items carry no stats; what they give
-- is the server's, sent as "NT|star values|charm ranks|trophies carried",
-- each list in NemesisStrength order. A trophy's entry is 991000 +
-- (effect - 1) * 3 + (stars - 1); the charm is 991030.
CW.NEMESIS_FX = {
    { name = "Bloodlust", what = "haste", pct = true },
    { name = "Ironhide", what = "armor", pct = true },
    { name = "Spellward", what = "resistance to every school" },
    { name = "Venomous", what = "critical strike chance", pct = true },
    { name = "Unyielding", what = "maximum health", pct = true },
    { name = "Warband", what = "attack power and spell power", pct = true },
    { name = "Relentless", what = "all primary stats", pct = true },
}
CW.nemesisCharm = { star = {}, ranks = {}, max = 4 }
function CW.ReadNemesisCharm(p)
    local c = CW.nemesisCharm
    c.star, c.ranks = {}, {}
    for v in string.gmatch(p[2] or "", "[^,]+") do tinsert(c.star, tonumber(v) or 0) end
    for v in string.gmatch(p[3] or "", "[^,]+") do tinsert(c.ranks, tonumber(v) or 0) end
    c.max = tonumber(p[4]) or c.max
end
function CW.TrophyOf(id)
    id = tonumber(id) or 0
    if id >= 991000 and id <= 991020 then
        return math.floor((id - 991000) / 3) + 1, (id - 991000) % 3 + 1
    end
end
function CW.TrophyName(id)
    local effect, stars = CW.TrophyOf(id)
    if not effect then return "" end
    return "Trophy of " .. CW.NEMESIS_FX[effect].name .. " " .. ({ "I", "II", "III" })[stars]
end
-- "+2.4% haste", from stars of one effect; the bare effect before NT arrives
function CW.NemesisFxText(effect, stars)
    local fx = CW.NEMESIS_FX[effect]
    local per = CW.nemesisCharm.star[effect]
    if not per then return fx.what end
    local v = per * stars
    local num = (v == math.floor(v)) and string.format("%d", v) or string.format("%.1f", v)
    return "+" .. num .. (fx.pct and "% " or " ") .. fx.what
end
function CW.NemesisItemTooltip(tip)
    if not tip or not tip.GetItem then return end
    local _, link = tip:GetItem()
    local id = link and tonumber(string.match(link, "item:(%d+)"))
    if not id then return end
    local effect, stars = CW.TrophyOf(id)
    if effect then
        tip:AddLine(CW.NemesisFxText(effect, stars), 0.1, 1, 0.1)
        local rank = CW.nemesisCharm.ranks[effect] or 0
        tip:AddLine("On finishing, if it is your best of its kind: " .. CW.NEMESIS_FX[effect].name .. " rank "
            .. rank .. " to " .. math.min(rank + stars, 5) .. " of 5 on your Nemesis Charm.", 1, 0.82, 0, true)
        tip:AddLine("On a Nemesis run, every trophy you carry adds up. You can carry "
            .. CW.nemesisCharm.max .. ".", 0.7, 0.7, 0.7, true)
        tip:AddLine("Finish the run and the best trophy of each kind adds its stars to your Nemesis Charm. "
            .. "If the run ends unfinished, they are gone.", 0.7, 0.7, 0.7, true)
        tip:Show()
    elseif id == 991030 then
        local any = false
        for i, fx in ipairs(CW.NEMESIS_FX) do
            local r = CW.nemesisCharm.ranks[i] or 0
            if r > 0 then
                any = true
                tip:AddDoubleLine(fx.name .. " " .. r .. "/5", CW.NemesisFxText(i, r), 1, 0.82, 0, 0.1, 1, 0.1)
            end
        end
        if not any then tip:AddLine("No ranks yet.", 0.7, 0.7, 0.7) end
        tip:AddLine("Finish a Nemesis run and the best trophy of each kind adds its stars here, up to rank 5.",
            0.7, 0.7, 0.7, true)
        tip:Show()
    end
end
-- a nemesis under the mouse says so, and what it is called
function CW.NemesisUnitTooltip(tip)
    if not tip or not tip.GetUnit then return end
    local _, unit = tip:GetUnit()
    local guid = unit and UnitGUID(unit)
    local title = guid and CW.nemesisGuids[guid]
    if not title then return end
    tip:AddLine(type(title) == "string" and ("Your nemesis, " .. title) or "Your nemesis", 1, 0.53, 0)
    tip:Show()
end
if GameTooltip and GameTooltip.HookScript then
    GameTooltip:HookScript("OnTooltipSetItem", CW.NemesisItemTooltip)
    GameTooltip:HookScript("OnTooltipSetUnit", CW.NemesisUnitTooltip)
end
if ItemRefTooltip and ItemRefTooltip.HookScript then
    ItemRefTooltip:HookScript("OnTooltipSetItem", CW.NemesisItemTooltip)
end

-- A nemesis's strengths (buffs) and weakness (a debuff) on its frame: the
-- server sends them to its Hero alone, the client patch names them, and their
-- tooltips get the realm's numbers here, from "NX|..." (in its order below).
CW.nemesisTraitNums = {}
CW.NEMESIS_TRAIT_TEXT = {
    [54060] = "Attacks and casts %1%% faster.",
    [70522] = "Takes %2%% less physical damage.",
    [6747] = "Takes %3%% less spell damage.",
    [6748] = "Its hits poison you for %4%% of your health every 2 seconds, for %5 seconds.",
    [15068] = "Deals %6%% more damage below %7%% health.",
    [23674] = "Calls %8 of its kind to its side, once a fight.",
    [24653] = "Regains %9%% of its health every second out of combat.",
    [32557] = "Takes %10%% more damage from Fire.",
    [36676] = "Takes %10%% more damage from Frost.",
    [45016] = "Takes %10%% more damage from Shadow.",
    [47929] = "Takes %10%% more damage from Nature.",
    [48031] = "Takes %10%% more damage from Arcane.",
    [48209] = "Takes %10%% more damage from Holy.",
    [46334] = "A stun ends its rage, and it takes %11%% more damage for %12 seconds.",
    [47464] = "Flees at %14%% health for %15 seconds, then takes %13%% more damage.",
    [33930] = "It has a weakness. Find it in the fight.",
}
function CW.ReadNemesisTraitNums(p)
    local nums = {}
    for i = 2, 16 do nums[i - 1] = p[i] or "?" end
    CW.nemesisTraitNums = nums
end
-- the text for one trait aura, nil for any other spell, nil before NX arrives
function CW.NemesisTraitText(spellId)
    local text = CW.NEMESIS_TRAIT_TEXT[tonumber(spellId) or 0]
    if not text or not CW.nemesisTraitNums[1] then return nil end
    text = string.gsub(text, "%%(%d+)", function(n) return CW.nemesisTraitNums[tonumber(n)] or "?" end)
    text = string.gsub(text, "%%%%", "%%")
    return text
end
function CW.NemesisAuraTooltip(tip, spellId)
    local text = CW.NemesisTraitText(spellId)
    if not text or not tip then return end
    local line = tip.GetName and _G[(tip:GetName() or "") .. "TextLeft2"]
    if line and line.SetText then
        line:SetText(text)
    else
        tip:AddLine(text, 1, 0.82, 0, true)
    end
    tip:Show()
end
if hooksecurefunc and GameTooltip then
    for _, f in ipairs({ { "SetUnitBuff", "UnitBuff" }, { "SetUnitDebuff", "UnitDebuff" }, { "SetUnitAura", "UnitAura" } }) do
        if GameTooltip[f[1]] then
            local query = f[2]
            hooksecurefunc(GameTooltip, f[1], function(tip, unit, index, filter)
                local getter = _G[query]
                if type(getter) ~= "function" then return end
                CW.NemesisAuraTooltip(tip, select(11, getter(unit, index, filter)))
            end)
        end
    end
end

-- The class bars above the main bar: stances and forms, the totem bar, the
-- pet bar, possession. Blizzard lays them out for one class at a time
-- (UIParent_ManageFramePositions): the stance bar, the possess bar and the
-- totem bar share one spot, the totem bar is hidden whenever either of the
-- others shows ("we have too many bars"), and the pet bar goes after the
-- stance bar, or after the totem bar when there is no stance bar. A Hero can
-- hold stances, totems and a pet at once.
--
-- So after each of Blizzard's passes, the totem bar is put on the row instead
-- of hidden: after the stance bar, or after the pet bar when that shares the
-- row, and on a row of its own above when the main bar is not wide enough. The
-- stance and pet bars stay where Blizzard put them, so nothing of Blizzard's
-- is moved. Possession and a vehicle still take the totem bar away, as stock:
-- both replace the bars on purpose. Frames with secure buttons cannot be moved
-- in combat, so a pass then waits for combat to end.
CW.CLASS_BAR_GAP = 12
-- The border of the stance buttons past ten. Blizzard's layout pass sizes the
-- stock ten (50 over the bottom-left bar, 64 without it); with the client patch
-- it reads only those ten, so these follow it here. A texture size is not
-- protected, so this runs in combat too.
function CW.SizeFormButtons()
    local small = MultiBarBottomLeft and MultiBarBottomLeft:IsShown()
    for i = CW.StockFormSlots() + 1, CW.FORM_SLOTS do
        local tex = rawget(_G, "ShapeshiftButton" .. i .. "NormalTexture")
        if tex then
            tex:SetWidth(small and 50 or 64)
            tex:SetHeight(small and 50 or 64)
        end
    end
end

function CW.LayoutClassBars()
    local mc, ss, pet, bar = MultiCastActionBarFrame, ShapeshiftBarFrame, PetActionBarFrame, MainMenuBar
    if type(mc) ~= "table" or type(ss) ~= "table" or type(bar) ~= "table" then return end
    CW.SizeFormButtons()
    -- With the client patch, Blizzard's own layout puts the totem bar in the
    -- row (ShapeshiftBar_RowRight is its helper). Writing the bar's fields or
    -- anchor from here would taint that secure code, so it is left to it.
    if type(rawget(_G, "ShapeshiftBar_RowRight")) == "function" then return end
    if InCombatLockdown and InCombatLockdown() then
        CW.classBarsPending = true
        return
    end
    CW.classBarsPending = nil
    if (mc.numActiveSlots or 0) == 0
            or (PossessBarFrame and PossessBarFrame:IsShown())
            or (UnitHasVehicleUI and UnitHasVehicleUI("player")) then
        return   -- no totem bar to place, or the bars are taken over on purpose
    end
    if not ss:IsShown() then
        -- The totem bar alone sits in Blizzard's own place, but it has to be
        -- up: a hide Blizzard's pass made while a stance bar showed, during a
        -- combat this waited out, is otherwise never undone (a death or a ghost
        -- run takes the stance bar away, and nothing re-shows the totem bar).
        if not mc:IsShown() or mc.mode == "hide" then
            mc.mode = "none"
            mc:Show()
        end
        return
    end
    local left = bar:GetLeft() or 0
    -- the row starts where Blizzard put the stance bar this pass (it moves up
    -- over the bottom-left action bar and the watch bars)
    local _, _, _, x0, y0 = ss:GetPoint()
    local rowRight = (x0 or 30) + (ss:GetWidth() or 0)
    local lastForm = _G["ShapeshiftButton" .. (GetNumShapeshiftForms and GetNumShapeshiftForms() or 0)]
    if lastForm and lastForm.GetRight and lastForm:GetRight() then
        rowRight = lastForm:GetRight() - left
    end
    if pet and pet.IsShown and pet:IsShown()
            and not (PetActionBarFrame_IsAboveShapeshift and PetActionBarFrame_IsAboveShapeshift()) then
        rowRight = math.max(rowRight, (PETACTIONBAR_XPOS or 36) + (pet:GetWidth() or 0))
    end
    local x = rowRight + CW.CLASS_BAR_GAP
    mc.mode = "none"   -- cancel the slide out Blizzard's pass just started
    mc:ClearAllPoints()
    if x + (mc:GetWidth() or 0) <= (bar:GetWidth() or 1024) then
        mc:SetPoint("BOTTOMLEFT", bar, "TOPLEFT", x, y0 or 0)
    else
        mc:SetPoint("BOTTOMLEFT", ss, "TOPLEFT", 0, 4)   -- the row is full: one above
    end
    mc:Show()
end
-- Blizzard puts the totem bar back in two places: its layout pass, and
-- ShowMultiCastActionBar, which the totem bar's own update event calls (a pet
-- dismissed fires it). That one slides the bar to its stock spot under the
-- stance bar, so the row is laid out again after either.
CW.classBarHooks = {}
function CW.HookClassBars()
    if not hooksecurefunc then return end
    for _, fn in ipairs({ "UIParent_ManageFramePositions", "ShowMultiCastActionBar" }) do
        if not CW.classBarHooks[fn] and type(rawget(_G, fn)) == "function" then
            hooksecurefunc(fn, CW.LayoutClassBars)
            CW.classBarHooks[fn] = true
        end
    end
end
CW.HookClassBars()
do
    local ev = CreateFrame("Frame")
    -- after combat, a death or a level, and the totem bar's own update: each
    -- can change which bars are up without a layout pass of Blizzard's
    for _, e in ipairs({ "PLAYER_REGEN_ENABLED", "PLAYER_ALIVE", "PLAYER_UNGHOST", "PLAYER_LEVEL_UP",
                         "UPDATE_MULTI_CAST_ACTIONBAR" }) do
        ev:RegisterEvent(e)
    end
    ev:SetScript("OnEvent", function() CW.LayoutClassBars() end)
end

-- What hangs under the player frame: the stock second mana bar (shown when
-- the displayed power is not mana), this addon's resource bars when they are
-- docked there, the totem timers, and the pet frame. Blizzard places each for
-- one class (the pet frame moves down only for a Death Knight, Druid or
-- Shaman, the totem timers sit where a Shaman's pet is not), so on a Hero they
-- land on top of one another. They are stacked here instead, top to bottom in
-- that order. A row is kept whenever it CAN show, not only while it does: the
-- pet frame is a secure button that cannot move in combat, so a totem dropped
-- mid-fight has to land in a row already left for it.
CW.DOCK = { TOP = 38, MANA_BOTTOM = 23, GAP = 3, TOTEM_H = 48, TOTEM_X = 99, PET_X = 80, BARS_X = 100,
            PARTY_X = 10, PARTY_Y = -160 }
function CW.LayoutPlayerDock()
    local pf = rawget(_G, "PlayerFrame")
    if type(pf) ~= "table" then return end
    if InCombatLockdown and InCombatLockdown() then
        CW.dockPending = true
        return
    end
    CW.dockPending = nil
    local D = CW.DOCK
    local y = D.TOP
    local used = false
    -- the second mana bar keeps Blizzard's own place, at the top
    local alt = rawget(_G, "PlayerFrameAlternateManaBar")
    if type(alt) == "table" and alt:IsShown() then
        y = D.MANA_BOTTOM - D.GAP
        used = true
    end
    -- this addon's bars, while they sit where they dock (not moved by hand)
    local bars = rawget(_G, "ClasslessWildcardBars")
    ClasslessWildcardDB = ClasslessWildcardDB or {}
    if type(bars) == "table" and bars:IsShown() and not ClasslessWildcardDB.barsPos then
        bars:ClearAllPoints()
        bars:SetPoint("TOPLEFT", pf, "BOTTOMLEFT", D.BARS_X, math.min(y, 24))
        y = math.min(y, 24) - (bars:GetHeight() or 0) - D.GAP
        used = true
    end
    -- the totem timers: their row whenever the Hero has totems to drop
    local tf = rawget(_G, "TotemFrame")
    local mc = rawget(_G, "MultiCastActionBarFrame")
    if type(tf) == "table" and (tf:IsShown() or (type(mc) == "table" and (mc.numActiveSlots or 0) > 0)) then
        tf:ClearAllPoints()
        tf:SetPoint("TOPLEFT", pf, "BOTTOMLEFT", D.TOTEM_X, y)
        y = y - D.TOTEM_H
        used = true
    end
    -- the pet frame last; with nothing above it, Blizzard's own place stands
    local pet = rawget(_G, "PetFrame")
    local stackBottom = y
    if used and type(pet) == "table" then
        pet:ClearAllPoints()
        pet:SetPoint("TOPLEFT", pf, "BOTTOMLEFT", D.PET_X, y)
        if pet:IsShown() then stackBottom = y - (pet:GetHeight() or 53) end
    end
    -- The party frames sit at a fixed spot under the player frame
    -- (PartyMemberFrame1 at UIParent TOPLEFT 10,-160, the others hang from
    -- it), so a taller stack ran into them: they move down just far enough,
    -- and back when the room is not needed.
    local party, ui = rawget(_G, "PartyMemberFrame1"), rawget(_G, "UIParent")
    if type(party) == "table" and type(ui) == "table" then
        local need
        local bottom, top = pf:GetBottom(), ui:GetTop()
        if used and bottom and top then
            local partyY = -(top - (bottom + stackBottom - D.GAP))
            if partyY < D.PARTY_Y then need = partyY end
        end
        if need then
            party:ClearAllPoints()
            party:SetPoint("TOPLEFT", ui, "TOPLEFT", D.PARTY_X, need)
            CW.partyMoved = true
        elseif CW.partyMoved then
            party:ClearAllPoints()
            party:SetPoint("TOPLEFT", ui, "TOPLEFT", D.PARTY_X, D.PARTY_Y)
            CW.partyMoved = nil
        end
    end
end
function CW.HookPlayerDock()
    CW.dockHooks = CW.dockHooks or {}
    if hooksecurefunc and not CW.dockHooks.totem and type(rawget(_G, "TotemFrame_Update")) == "function" then
        hooksecurefunc("TotemFrame_Update", CW.LayoutPlayerDock)
        CW.dockHooks.totem = true
    end
    for _, name in ipairs({ "PetFrame", "PlayerFrameAlternateManaBar", "TotemFrame", "ClasslessWildcardBars" }) do
        local f = rawget(_G, name)
        if not CW.dockHooks[name] and type(f) == "table" and f.HookScript then
            f:HookScript("OnShow", CW.LayoutPlayerDock)
            f:HookScript("OnHide", CW.LayoutPlayerDock)
            if name == "ClasslessWildcardBars" then
                f:HookScript("OnSizeChanged", CW.LayoutPlayerDock)   -- rows come and go
            end
            CW.dockHooks[name] = true
        end
    end
end
do
    local ev = CreateFrame("Frame")
    for _, e in ipairs({ "PLAYER_ENTERING_WORLD", "PLAYER_REGEN_ENABLED", "UNIT_DISPLAYPOWER", "UNIT_PET" }) do
        ev:RegisterEvent(e)
    end
    ev:SetScript("OnEvent", function(_, event)
        if event == "PLAYER_ENTERING_WORLD" then CW.HookPlayerDock() end
        if event ~= "PLAYER_REGEN_ENABLED" or CW.dockPending then CW.LayoutPlayerDock() end
    end)
end

-- Stances and forms past ten. The client keeps every form a Hero knows (any
-- spell with the shapeshift aura or the stance flag) in a list with no limit,
-- and GetNumShapeshiftForms, GetShapeshiftFormInfo and CastShapeshiftForm all
-- reach past ten. Only Blizzard's bar stops: it has ShapeshiftButton1 to 10.
-- Worse, two of its loops run to GetNumShapeshiftForms() and index
-- ShapeshiftButton<n> (UIParent_ManageFramePositions sizes each one's
-- NormalTexture, PetActionBar_UpdatePositionValues reads the last one's right
-- edge), so an eleventh form threw a Lua error. The rest of the row is made
-- here under those names, at load, so both loops find them: secure buttons
-- that cast the form's spell, laid out like Blizzard's and inside its bar art,
-- which already stretches to the form count.
CW.FORM_SLOTS = 30
-- Blizzard's own button count (BonusActionBarFrame.lua), ten
function CW.StockFormSlots() return tonumber(rawget(_G, "NUM_SHAPESHIFT_SLOTS")) or 10 end
function CW.MakeFormButtons()
    local stock = CW.StockFormSlots()
    if type(rawget(_G, "ShapeshiftBarFrame")) ~= "table" or not rawget(_G, "ShapeshiftButton" .. stock) then return end
    for i = stock + 1, CW.FORM_SLOTS do
        local name = "ShapeshiftButton" .. i
        if not rawget(_G, name) then
            local b = CreateFrame("CheckButton", name, ShapeshiftBarFrame,
                "ActionButtonTemplate, SecureActionButtonTemplate")
            b:SetID(i)
            b:SetWidth(30); b:SetHeight(30)
            -- the stock stride (BonusActionBarFrame.xml: 8 apart): the client
            -- patch's layout works out where the row ends from it
            b:SetPoint("LEFT", _G["ShapeshiftButton" .. (i - 1)], "RIGHT", 8, 0)
            b:SetAttribute("type", "spell")
            b:SetScript("OnEnter", function(self)
                GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
                GameTooltip:SetShapeshift(self:GetID())
            end)
            b:SetScript("OnLeave", function() GameTooltip:Hide() end)
            b:Hide()
        end
    end
end
-- which forms the extra buttons cast, and which show: out of combat only
function CW.BuildFormButtons()
    if InCombatLockdown and InCombatLockdown() then
        CW.formButtonsPending = true
        return
    end
    CW.formButtonsPending = nil
    local n = GetNumShapeshiftForms and GetNumShapeshiftForms() or 0
    for i = CW.StockFormSlots() + 1, CW.FORM_SLOTS do
        local b = rawget(_G, "ShapeshiftButton" .. i)
        if b then
            local _, spell = nil, nil
            if i <= n then _, spell = GetShapeshiftFormInfo(i) end
            b:SetAttribute("spell", spell)
            if spell then b:Show() else b:Hide() end
        end
    end
    CW.UpdateFormButtons()
end
-- their look: icon, active, usable, cooldown (allowed in combat)
function CW.UpdateFormButtons()
    local n = GetNumShapeshiftForms and GetNumShapeshiftForms() or 0
    for i = CW.StockFormSlots() + 1, math.min(n, CW.FORM_SLOTS) do
        local b = rawget(_G, "ShapeshiftButton" .. i)
        if b then
            local texture, _, isActive, isCastable = GetShapeshiftFormInfo(i)
            local icon = _G["ShapeshiftButton" .. i .. "Icon"]
            if icon then
                icon:SetTexture(texture)
                if isCastable then icon:SetVertexColor(1, 1, 1) else icon:SetVertexColor(0.4, 0.4, 0.4) end
            end
            b:SetChecked(isActive and true or false)
            local cooldown = _G["ShapeshiftButton" .. i .. "Cooldown"]
            if cooldown and GetShapeshiftFormCooldown and CooldownFrame_SetTimer then
                CooldownFrame_SetTimer(cooldown, GetShapeshiftFormCooldown(i))
            end
        end
    end
end
CW.MakeFormButtons()
do
    local ev = CreateFrame("Frame")
    for _, e in ipairs({ "PLAYER_ENTERING_WORLD", "UPDATE_SHAPESHIFT_FORMS", "PLAYER_REGEN_ENABLED" }) do
        ev:RegisterEvent(e)
    end
    ev:SetScript("OnEvent", function(_, event)
        if event ~= "PLAYER_REGEN_ENABLED" or CW.formButtonsPending then CW.BuildFormButtons() end
    end)
    local look = CreateFrame("Frame")
    for _, e in ipairs({ "UPDATE_SHAPESHIFT_FORM", "UPDATE_SHAPESHIFT_USABLE", "UPDATE_SHAPESHIFT_COOLDOWN",
                         "SPELL_UPDATE_COOLDOWN", "ACTIONBAR_UPDATE_USABLE" }) do
        look:RegisterEvent(e)
    end
    look:SetScript("OnEvent", function() CW.UpdateFormButtons() end)
end

-- Where each nemesis lives, as a skull on the world map when its zone is the
-- one shown. The server sends the zone's name and the spot in percent.
function CW.NemesisPinsNow()
    local pins = CW.nemesisPins or {}
    CW.nemesisPins = pins
    local zoneName
    if WorldMapButton and GetMapZones and GetCurrentMapContinent and GetCurrentMapZone then
        local zone = GetCurrentMapZone()
        if zone and zone > 0 then zoneName = select(zone, GetMapZones(GetCurrentMapContinent())) end
    end
    local n = 0
    if zoneName then
        local w, h = WorldMapButton:GetWidth(), WorldMapButton:GetHeight()
        for _, e in ipairs(CW.nemesisList or {}) do
            if e.zone == zoneName and (e.x > 0 or e.y > 0) then
                n = n + 1
                local pin = pins[n]
                if not pin then
                    pin = CreateFrame("Frame", nil, WorldMapButton)
                    pin:SetWidth(20); pin:SetHeight(20)
                    pin:SetFrameLevel(WorldMapButton:GetFrameLevel() + 5)
                    pin.icon = pin:CreateTexture(nil, "OVERLAY")
                    pin.icon:SetAllPoints(pin)
                    pin.icon:SetTexture("Interface\\TargetingFrame\\UI-TargetingFrame-Skull")
                    pin:EnableMouse(true)
                    pin:SetScript("OnEnter", function(self)
                        local e = self.entry
                        WorldMapTooltip:SetOwner(self, "ANCHOR_RIGHT")
                        WorldMapTooltip:AddLine(e.name .. (e.title ~= "" and (" " .. e.title) or ""), 1, 0.53, 0)
                        WorldMapTooltip:AddLine(e.kind .. " nemesis, " .. e.levels .. " levels above you", 1, 1, 1)
                        WorldMapTooltip:Show()
                    end)
                    pin:SetScript("OnLeave", function() WorldMapTooltip:Hide() end)
                    pins[n] = pin
                end
                pin.entry = e
                pin:ClearAllPoints()
                pin:SetPoint("CENTER", WorldMapButton, "TOPLEFT", e.x / 100 * w, -e.y / 100 * h)
                pin:Show()
            end
        end
    end
    for i = n + 1, #pins do pins[i]:Hide() end
    return n
end
function CW.NemesisPins()
    local ok, n = pcall(CW.NemesisPinsNow)
    return ok and n or 0
end
do
    local ev = CreateFrame("Frame")
    ev:RegisterEvent("WORLD_MAP_UPDATE")
    ev:SetScript("OnEvent", function() CW.NemesisPins() end)
end
if hooksecurefunc and type(TargetFrame_CheckClassification) == "function" then
    hooksecurefunc("TargetFrame_CheckClassification", function(self, forceNormal)
        CW.NemesisBorder(self, forceNormal, true)
    end)
end

-- A run's live numbers on screen while playing, not only in the panel: the
-- challenge, its lives, and whatever its rule is counting. Hourglass's level
-- clock drains as a bar, Pursued says whether the hunter is out, Nemesis
-- counts your nemeses (named on hover), and Berserker says which health
-- band you are in. The server sends "RT" with every state, on run events and
-- every 30 seconds while a clock runs; between those the bar counts down here.
-- Drag to move, click for the challenge page, /cw tracker to hide or show.
-- ---------------------------------------------------------------------------
do
    local RT = { run = 0, lives = 0, livesMax = 0, a = 0, b = 0, c = 0, d = 0, list = {}, at = 0 }
    CW.rt = RT
    local HOURGLASS, PURSUED, BERSERKER, NEMESIS = 15, 4, 18, 1

    local f = CreateFrame("Button", "ClasslessWildcardTracker", UIParent)
    f:SetWidth(220); f:SetHeight(48)
    f:SetFrameStrata("MEDIUM")
    f:SetPoint("TOP", UIParent, "TOP", 0, -40)
    f:SetBackdrop({
        bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
        edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
        tile = true, tileSize = 16, edgeSize = 12,
        insets = { left = 3, right = 3, top = 3, bottom = 3 },
    })
    f:SetMovable(true); f:EnableMouse(true); f:SetClampedToScreen(true)
    f:RegisterForDrag("LeftButton")
    f:Hide()
    CW.tracker = f

    f.icon = f:CreateTexture(nil, "ARTWORK")
    f.icon:SetWidth(18); f.icon:SetHeight(18)
    f.icon:SetPoint("TOPLEFT", 8, -7)
    f.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    f.name = f:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    f.name:SetPoint("LEFT", f.icon, "RIGHT", 6, 0)
    f.name:SetJustifyH("LEFT")
    f.pips = {}
    for i = 1, 6 do
        local t = CW.MakePip(f, 12)
        t:SetPoint("TOPRIGHT", f, "TOPRIGHT", -8 - (6 - i) * 13, -10)
        f.pips[i] = t
    end

    -- the line under the name: a bar for a clock, text for everything else
    f.bar = CreateFrame("StatusBar", nil, f)
    f.bar:SetPoint("BOTTOMLEFT", 9, 8); f.bar:SetPoint("BOTTOMRIGHT", -9, 8)
    f.bar:SetHeight(12)
    f.bar:SetStatusBarTexture("Interface\\TargetingFrame\\UI-StatusBar")
    f.bar:SetMinMaxValues(0, 1)
    f.bar.bg = f.bar:CreateTexture(nil, "BACKGROUND")
    f.bar.bg:SetAllPoints(f.bar)
    f.bar.bg:SetTexture(0, 0, 0, 0.5)
    f.bar.text = f.bar:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    f.bar.text:SetPoint("CENTER", f.bar, "CENTER", 0, 0)
    f.line = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    f.line:SetPoint("BOTTOMLEFT", 10, 9); f.line:SetPoint("BOTTOMRIGHT", -10, 9)
    f.line:SetJustifyH("LEFT")

    function CW.TrackerClock(sec)
        sec = math.max(0, math.floor(sec))
        return string.format("%d:%02d", math.floor(sec / 60), sec % 60)
    end

    -- Hourglass: seconds left now, and whether the sand is holding still
    function CW.HourglassNow()
        local paused = RT.c == 1 or (UnitIsDeadOrGhost and UnitIsDeadOrGhost("player")) and true or false
        if paused then return RT.a, true end
        return math.max(0, RT.a - (GetTime() - RT.at)), false
    end

    -- Berserker: which band the player's health is in
    function CW.BerserkerBand()
        local max = UnitHealthMax("player") or 0
        local pct = max > 0 and (UnitHealth("player") or 0) * 100 / max or 100
        if pct < RT.a then return "low" end
        if pct > RT.b then return "high" end
        return "mid"
    end

    function CW.RenderTracker()
        local c = CW.challengesById and CW.challengesById[RT.run]
        f.name:SetText("|cffff5544" .. (c and c.name or ("Challenge " .. RT.run)) .. "|r")
        f.icon:SetTexture(c and (c.reward or 0) > 0 and SpellIcon(c.reward) or "Interface\\Icons\\INV_Misc_Bone_HumanSkull_01")
        local n = CW.PipCount(RT.livesMax, #f.pips)
        for i = 1, #f.pips do
            -- right-aligned: the last n slots are this run's lives
            local slot = i - (#f.pips - n)
            CW.SetPip(f.pips[i], slot >= 1, slot >= 1 and slot <= RT.lives)
        end
        f.bar:Hide(); f.line:Hide()
        f:SetHeight(48)
        if RT.run == HOURGLASS and RT.b > 0 then
            local left, paused = CW.HourglassNow()
            f.bar:SetValue(left / RT.b)
            if paused then
                f.bar:SetStatusBarColor(0.5, 0.5, 0.5)
                f.bar.text:SetText(CW.TrackerClock(left) .. "  paused")
            else
                if left <= 60 then f.bar:SetStatusBarColor(0.9, 0.15, 0.1)
                elseif left <= RT.d then f.bar:SetStatusBarColor(1, 0.55, 0)
                else f.bar:SetStatusBarColor(0.85, 0.7, 0.2) end
                f.bar.text:SetText(CW.TrackerClock(left) .. " left on this level")
            end
            f.bar:Show()
        elseif RT.run == PURSUED then
            f.line:SetText(RT.a == 1 and ("|cffff4444The hunter is on you|r (level " .. RT.b .. ")")
                or "|cffaaaaaaNo hunter on you. One is coming.|r")
            f.line:Show()
        elseif RT.run == NEMESIS then
            -- b Vengeance of c needed
            local vengeance = RT.c > 0 and ("Vengeance |cffffd100" .. RT.b .. "/" .. RT.c .. "|r  ") or ""
            f.line:SetText(vengeance .. (RT.a == 0 and (RT.b > 0 and "|cffaaaaaaNo nemesis now|r" or "|cffaaaaaaNo nemesis yet|r")
                or ("|cffff8800" .. RT.a .. (RT.a == 1 and " nemesis" or " nemeses") .. "|r")))
            f.line:Show()
        elseif RT.run == BERSERKER then
            local band = CW.BerserkerBand()
            if band == "low" then
                f.line:SetText("|cffff4444Below " .. RT.a .. "%: double damage, slows break|r")
            elseif band == "high" then
                f.line:SetText("|cffaaaaaaAbove " .. RT.b .. "%: " .. RT.c .. "% less damage|r")
            else
                f.line:SetText("Normal damage")
            end
            f.line:Show()
        else
            f:SetHeight(32)
        end
        if GameTooltip:IsOwned(f) then CW.TrackerTooltip(f) end
    end

    function CW.TrackerTooltip(self)
        CW.RunTooltip(self)
        if RT.run == NEMESIS and RT.c > 0 then
            GameTooltip:AddLine(" ")
            GameTooltip:AddDoubleLine("Vengeance", RT.b .. " of " .. RT.c, 1, 0.82, 0, 1, 1, 1)
            GameTooltip:AddLine("The total level of the nemeses you slay. A Sworn one counts for more.", 0.7, 0.7, 0.7, true)
            GameTooltip:Show()
        end
        local list = CW.nemesisList or {}
        if RT.run == NEMESIS and #list > 0 then
            GameTooltip:AddLine(" ")
            GameTooltip:AddLine("Your nemeses", 1, 0.53, 0)
            for _, e in ipairs(list) do
                GameTooltip:AddDoubleLine(e.name .. (e.title ~= "" and (" " .. e.title) or ""),
                    e.kind .. " +" .. e.levels .. " levels", 1, 1, 1, 1, 0.53, 0)
                GameTooltip:AddDoubleLine("   strengths", e.strengths == "?" and "fight it to learn" or e.strengths,
                    0.7, 0.7, 0.7, 0.4, 1, 0.4)
                GameTooltip:AddDoubleLine("   weakness", e.weakness == "?" and "fight it to learn" or e.weakness,
                    0.7, 0.7, 0.7, 1, 0.4, 0.4)
                if e.zone ~= "" then
                    GameTooltip:AddDoubleLine("   lives in", e.zone, 0.7, 0.7, 0.7, 1, 1, 1)
                end
            end
            GameTooltip:Show()
        end
    end

    function CW.UpdateTracker()
        ClasslessWildcardDB = ClasslessWildcardDB or {}
        if RT.run == 0 or RT.livesMax == 0 or ClasslessWildcardDB.trackerOff then
            f:Hide()
            if GameTooltip:IsOwned(f) then GameTooltip:Hide() end
            return
        end
        CW.RenderTracker()
        f:Show()
    end

    -- "RT|run|lives|livesMax|a|b|c|d|name:levels;..."
    function CW.ReadTracker(p)
        RT.run = tonumber(p[2]) or 0
        RT.lives = tonumber(p[3]) or 0
        RT.livesMax = tonumber(p[4]) or 0
        RT.a, RT.b = tonumber(p[5]) or 0, tonumber(p[6]) or 0
        RT.c, RT.d = tonumber(p[7]) or 0, tonumber(p[8]) or 0
        RT.at = GetTime()
        RT.list = {}
        -- Nemesis: "name:levels:experience held;", or "name:levels;" from an
        -- older server
        for entry in string.gmatch(p[9] or "", "([^;]+);") do
            local name, levels, held = string.match(entry, "^([^:]+):(%d+):?(%d*)$")
            if name then
                tinsert(RT.list, { name = name, levels = tonumber(levels), held = tonumber(held) or 0 })
            end
        end
        -- the run is named from the challenge list; a fresh login asks once
        if RT.run > 0 and #CW.challenges == 0 and not CW._askedChallenges then
            CW._askedChallenges = true
            Send("CHL")
        end
        -- the freshest word on the run: the panel's badge and the hover card
        -- read these
        local s = CW.state
        s.run, s.lives, s.livesMax = RT.run, RT.lives, RT.livesMax
        s.hourglassLeft = RT.run == HOURGLASS and RT.a or 0
        CW.hourglassAt = RT.at
        CW.UpdateLives()
        CW.UpdateTracker()
    end

    -- the clock between server updates; a twice-a-second redraw is plenty
    local since = 0
    f:SetScript("OnUpdate", function(_, elapsed)
        since = since + elapsed
        if since < 0.5 then return end
        since = 0
        if RT.run == HOURGLASS or RT.run == BERSERKER then CW.RenderTracker() end
    end)

    f:SetScript("OnDragStart", function(self) self:StartMoving() end)
    f:SetScript("OnDragStop", function(self)
        self:StopMovingOrSizing()
        ClasslessWildcardDB = ClasslessWildcardDB or {}
        local point, _rel, relPoint, x, y = self:GetPoint()
        if point then
            ClasslessWildcardDB.trackerPos = { point = point, relPoint = relPoint, x = x, y = y }
        end
    end)
    f:SetScript("OnEnter", function(self) CW.TrackerTooltip(self) end)
    f:SetScript("OnLeave", function() GameTooltip:Hide() end)
    f:SetScript("OnClick", function()
        GameTooltip:Hide()
        if CW.runFly and CW.OpenRuns then
            CW.runFly.selected = RT.run
            CW.OpenRuns()
        end
    end)

    function CW.RestoreTrackerPosition()
        ClasslessWildcardDB = ClasslessWildcardDB or {}
        local pos = ClasslessWildcardDB.trackerPos
        if not pos or not pos.point then return end
        f:ClearAllPoints()
        f:SetPoint(pos.point, UIParent, pos.relPoint or pos.point, pos.x or 0, pos.y or 0)
    end

    -- The Settings checkbox and /cw tracker change the same setting, stored
    -- by absence like the bars' so an old saved-variables file shows it.
    function CW.TrackerShown()
        return not (ClasslessWildcardDB and ClasslessWildcardDB.trackerOff)
    end

    function CW.SetTrackerShown(on)
        ClasslessWildcardDB = ClasslessWildcardDB or {}
        ClasslessWildcardDB.trackerOff = (not on) or nil
        CW.UpdateTracker()
        if CW.setFly and CW.setFly:IsShown() and CW.RenderSettings then CW.RenderSettings() end
    end

    function CW.ToggleTracker()
        CW.SetTrackerShown(not CW.TrackerShown())
        Print(CW.TrackerShown() and "Challenge tracker shown."
            or "Challenge tracker hidden. /cw tracker shows it again.")
    end

    function CW.ResetTrackerPosition()
        ClasslessWildcardDB = ClasslessWildcardDB or {}
        ClasslessWildcardDB.trackerPos = nil
        f:ClearAllPoints()
        f:SetPoint("TOP", UIParent, "TOP", 0, -40)
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
events:RegisterEvent("PLAYER_LEVEL_UP")   -- a level brings stat points: ask for the new budget
events:RegisterEvent("UNIT_STATS")        -- the totals the Stats page quotes have moved
events:SetScript("OnEvent", function(self, event, arg1, arg2, arg3, arg4)
    if event == "CHAT_MSG_ADDON" then
        if arg1 == PREFIX and arg4 == UnitName("player") then
            HandleMessage(arg2)
        elseif arg1 == CW.SHARE_PREFIX and CW.ReceiveBuildPiece then
            CW.ReceiveBuildPiece(arg4, arg2)   -- a build shared by a party member
        end
    elseif event == "CINEMATIC_STOP" then
        CW.RefreshPanelArt()
        if CW.intro then CW.intro.OnCinematicStop() end
    elseif event == "PLAYER_ENTERING_WORLD" then
        -- the server strips the chassis's free class spells about now
        if CW.QuietUnlearnsForLogin then CW.QuietUnlearnsForLogin() end
        CW.RefreshPanelArt()
        CW.LoadBrowseChoices()
        CW.RestoreBarsPosition()
        CW.RestoreTrackerPosition()
        Send("HELLO")
        -- The stat RATES, now rather than the first time the Stats panel is
        -- opened. The character sheet quotes them, and a sheet opened before
        -- they arrived showed Blizzard's own numbers until something else went
        -- and fetched them.
        Send("STATS")
        if CW.ClaimHotkey then CW.ClaimHotkey() end
        if CW.ClaimTalentsKey then CW.ClaimTalentsKey() end
        if CW.RefreshMicroTooltip then CW.RefreshMicroTooltip() end
    elseif event == "UPDATE_BINDINGS" then
        -- the player rebound us in Key Bindings: keep the "(N)" suffix honest
        if CW.RefreshMicroTooltip then CW.RefreshMicroTooltip() end
    elseif event == "PLAYER_LEVEL_UP" then
        -- The server sends the stat budget only when asked, so a level's new
        -- points never reached the Stats page or the "Stats (N)" button. The
        -- server has levelled the character by the time this arrives.
        Send("STATS")
    elseif event == "UNIT_STATS" then
        -- The page shows the character's live totals (UnitStat). After Apply
        -- the server's reply lands before the new totals do, so the page drew
        -- the old ones until something else redrew it; draw again when the
        -- totals actually change.
        if arg1 == "player" and CW.statFly and CW.statFly:IsShown() and CW.RenderStats then
            CW.RenderStats()
        end
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
            Print("The Starting Hand is only available to Wildcard Heroes below level " .. (CW.state.freeReroll or 10)
                .. ". Reroll from |cffffff00My Build|r instead.")
        end
        return
    elseif msg == "tracker" then
        CW.ToggleTracker()
        return
    elseif msg == "intro" then
        CW.intro.Play(true)   -- see it again; the path wizard does not follow a replay
        return
    elseif msg == "builds" or msg == "import" then
        -- My Builds, or straight to pasting a code; Classless Heroes only
        if CW.state.mode ~= 0 then
            Print("Builds are for the Classless path.")
            return
        end
        if msg == "import" then
            CW.OpenShareWindow("import")
            return
        end
        if not frame:IsShown() then frame:Show() end
        CW.archTab = "MINE"
        CW.archFly:Show()
        CW.RenderArchFly()
        return
    elseif msg == "testcards" and ClasslessWildcardDB and ClasslessWildcardDB.dev then
        -- preview both summary cards with sample numbers; nothing is sent
        local me = UnitName("player") or "Hero"
        CW.ShowSummary(CW.RunEndSpec({ "RE", "1", "80", "142", "400", "Glass", "5", "3", "3", "133",
            me .. " the Unshattered", me .. " the Unbroken", "0" }))
        CW.ShowSummary(CW.RebirthDoneSpec({ "RB", "2", "150", "50", "6", "0", "2", "9", "4", "3",
            me .. " the Twice Reborn", "133,686" }))
        return
    elseif msg == "testroll" and ClasslessWildcardDB and ClasslessWildcardDB.dev then
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
-- Escape closes an open flyout first and the panel after. Blizzard's Escape
-- hides every shown frame named in UISpecialFrames at once, so while a
-- flyout is open it takes the panel's place in that list, and gives it back
-- when it closes. Nothing of Blizzard's is replaced, so nothing is tainted.
-- ---------------------------------------------------------------------------
do
    local FLYOUTS = { "ClasslessWildcardStats", "ClasslessWildcardArchetypes", "ClasslessWildcardHelp",
                      "ClasslessWildcardSettings", "ClasslessWildcardRebirth", "ClasslessWildcardRuns",
                      "ClasslessWildcardArchPlan", "ClasslessWildcardBuildEditor" }
    local function Listed(name, on)
        for i = #UISpecialFrames, 1, -1 do
            if UISpecialFrames[i] == name then tremove(UISpecialFrames, i) end
        end
        if on then tinsert(UISpecialFrames, name) end
    end
    function CW.SyncEscape()
        local open = false
        for _, name in ipairs(FLYOUTS) do
            local f = _G[name]
            local shown = f and f:IsVisible() and true or false
            Listed(name, shown)
            open = open or shown
        end
        Listed("ClasslessWildcardFrame", not open)
    end
    for _, name in ipairs(FLYOUTS) do
        local f = _G[name]
        if f then
            f:HookScript("OnShow", CW.SyncEscape)
            f:HookScript("OnHide", CW.SyncEscape)
        end
    end
end

-- ---------------------------------------------------------------------------
-- key bindings (Bindings.xml declares the actions; these are their handlers)
-- ---------------------------------------------------------------------------
BINDING_HEADER_CLASSLESSWILDCARD = "Hero Advancement"
BINDING_NAME_CLASSLESSWILDCARD_TOGGLE = "Toggle Hero Advancement"
BINDING_NAME_CLASSLESSWILDCARD_HELP = "Toggle the Help guide"
BINDING_NAME_CLASSLESSWILDCARD_BARS = "Toggle the resource bars"

function ClasslessWildcard_TogglePanel()
    if frame:IsShown() then frame:Hide() else frame:Show() end
end

-- ---------------------------------------------------------------------------
-- The Venom Beetle's spellbook tab reads "Pet", not "Demon"
--
-- The core only makes a SUMMONED pet permanent when its creature type is demon
-- or undead, and a pet that is not permanent is never sent its spell list at
-- all -- no pet bar, no Pet tab, no owner pet auras, and nothing saved at
-- logout. A tamed wolf sidesteps all of that by being a HUNTER_PET, which the
-- core makes permanent whatever it is; a summoned beast has no such branch. So
-- the beetle is filed as a demon, and the client picks its tab label from the
-- creature type: there are only two, PET_TYPE_DEMON and PET_TYPE_PET.
--
-- It is the one pet with no creature family, which is what tells it apart from
-- a real imp or felhunter a Hero may also own.
-- ---------------------------------------------------------------------------
do
    local function relabel()
        local tab = _G.SpellBookFrameTabButton2
        if not tab or tab.bookType ~= BOOKTYPE_PET then return end
        if UnitCreatureFamily("pet") then return end     -- a real demon: leave it
        if tab:GetText() ~= _G.PET_TYPE_PET then
            tab:SetText(_G.PET_TYPE_PET)
        end
        -- The title is set as text. SpellBookFrame.petTitle is Blizzard's own
        -- field: the page buttons read it and go on to write the pet book's page
        -- number, which SpellButton_OnClick reads before CastSpell, so an addon
        -- value there would taint casting a pet spell from the book.
        if SpellBookFrame.bookType == BOOKTYPE_PET and SpellBookTitleText then
            SpellBookTitleText:SetText(_G.PET_TYPE_PET)
        end
    end

    if hooksecurefunc then
        for _, fn in ipairs({ "SpellBookFrame_Update", "SpellBookPrevPageButton_OnClick",
                              "SpellBookNextPageButton_OnClick" }) do
            if type(_G[fn]) == "function" then hooksecurefunc(fn, relabel) end
        end
    end
end

-- ---------------------------------------------------------------------------
-- The stock talent window shows PET talents only
--
-- A Hero's talents come from every class and are read in this addon's talent
-- browser. The stock frame can only draw the chassis class's three trees, which
-- are not the Hero's build and are very nearly empty, so opening it on a player
-- spec sends you to the browser instead.
--
-- Pet talents are left exactly as they are: those really are the pet's own
-- trees, the stock frame draws them correctly, and there is nothing here that
-- replaces it.
--
-- But the Talents button and key open the window on the PLAYER spec, and pet
-- talents are only a side tab inside it, so sending the player spec away also
-- sent the pet's with it: a Hero with a tamed beast had no way to spend its
-- points. So with a pet that has talents the window opens on the pet's spec
-- and the player spec tabs are hidden; without one it closes again with a
-- line saying what the button is for.
-- ---------------------------------------------------------------------------
do
    local P = {}
    CW.talentSteer = P   -- for the harness, which has to run the deferred close

    -- the client's own answer: a tamed beast of a family with a talent tree
    function P.petHasTalents()
        return (GetNumTalentGroups(false, true) or 0) > 0
    end

    -- In combat a close from here would slide the other panels from tainted
    -- code, so it waits until combat ends. The Talents button and key never
    -- get this far without a pet: the client patch has ToggleTalentFrame ask
    -- first (lib/framexml.py). This is for every other way in.
    P.regen = CreateFrame("Frame")
    P.regen:SetScript("OnEvent", function(self)
        self:UnregisterEvent("PLAYER_REGEN_ENABLED")
        P.later:Show()
    end)

    function P.close()
        if InCombatLockdown() then
            P.regen:RegisterEvent("PLAYER_REGEN_ENABLED")
        else
            HideUIPanel(PlayerTalentFrame)
        end
    end

    -- Without a pet the window has nothing for a Hero, so it closes and says
    -- what the button is for, where the game says "Not enough rage": the
    -- centre-screen line that fades by itself. Hero Advancement has its own
    -- button and key.
    function P.steer()
        if not PlayerTalentFrame or not PlayerTalentFrame:IsShown() then return end
        if PlayerTalentFrame.pet then return end      -- pet talents: leave it alone
        if P.petHasTalents() then
            PlayerTalentFrame_Open(true, 1)
            return
        end
        P.close()
        UIErrorsFrame:AddMessage("Pet talents open here when you have a tamed beast out.", 1.0, 0.82, 0.0)
    end

    -- Any route onto a player spec -- the frame's own default on show, the
    -- fallback when a pet is dismissed, a glyph being put in -- goes through
    -- PlayerSpecTab_OnClick. A frame later, turn it to the pet's spec while
    -- there is one, or close it: closing it here would run inside its own
    -- OnShow, before the Toggle hook above has had the chance to open the
    -- browser instead.
    --
    -- Glyphs live on the player's spec too, and every way in goes through the
    -- same click: right-clicking a glyph (USE_GLYPH) runs
    -- PlayerTalentFrame_OpenGlyphFrame, which shows the window, clicks the
    -- player spec and only THEN selects the Glyphs tab. So the turn to the
    -- pet's spec waits a frame as well, and neither it nor the close happens
    -- while the Glyphs tab is the one selected. Turning or closing at once sent
    -- every glyph away before it could be put in a socket.
    function P.onGlyphs()
        return GLYPH_TALENT_TAB ~= nil and type(PanelTemplates_GetSelectedTab) == "function"
            and PanelTemplates_GetSelectedTab(PlayerTalentFrame) == GLYPH_TALENT_TAB
    end

    P.later = CreateFrame("Frame")
    P.later:Hide()
    P.later:SetScript("OnUpdate", function(self)
        self:Hide()
        if not PlayerTalentFrame or not PlayerTalentFrame:IsShown() or PlayerTalentFrame.pet then return end
        if P.onGlyphs() then return end
        if P.petHasTalents() then
            PlayerTalentFrame_Open(true, 1)
        else
            P.close()
        end
    end)

    function P.onSpecClick(tab)
        if not tab or not PlayerTalentFrame or not PlayerTalentFrame:IsShown() then return end
        if PlayerTalentFrame.pet then return end
        P.later:Show()
    end

    -- the side tabs for the player's own specs: there is nothing on them
    function P.hidePlayerTabs()
        for i = 1, 8 do
            local tab = _G["PlayerSpecTab" .. i]
            if not tab then break end
            if type(tab.specIndex) == "string" and not tab.specIndex:find("^pet") then
                tab:Hide()
            end
        end
    end

    local function attach()
        if type(_G.PlayerTalentFrame_Toggle) ~= "function" then return false end
        hooksecurefunc("PlayerTalentFrame_Toggle", P.steer)
        if type(_G.PlayerTalentFrame_Open) == "function" then
            hooksecurefunc("PlayerTalentFrame_Open", P.steer)
        end
        if type(_G.PlayerSpecTab_OnClick) == "function" then
            hooksecurefunc("PlayerSpecTab_OnClick", P.onSpecClick)
        end
        if type(_G.PlayerTalentFrame_UpdateSpecs) == "function" then
            hooksecurefunc("PlayerTalentFrame_UpdateSpecs", P.hidePlayerTabs)
        end
        return true
    end

    -- Blizzard_TalentUI is load-on-demand, so the function usually does not
    -- exist yet; try now in case it does, and watch for the load if it does not.
    if not attach() then
        local watcher = CreateFrame("Frame")
        watcher:RegisterEvent("ADDON_LOADED")
        watcher:SetScript("OnEvent", function(_, _, name)
            if name == "Blizzard_TalentUI" and attach() then
                watcher:UnregisterAllEvents()
            end
        end)
    end
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
-- Everything is rebindable under Key Bindings > Hero Advancement.
-- J is not a fallback here: it is the stock Talents key's new home, below,
-- and the only letter WTF\DefaultBindings.wtf leaves unbound.
local PREFERRED_KEY = "N"
local REPLACEABLE_ACTIONS = { TOGGLETALENTS = true }
local FALLBACK_KEYS = { "Y", "G", "K" }

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
            .. (occupied and ", in place of the Talents key" or "")
            .. ". Rebind it under Key Bindings > Hero Advancement.")
        return true
    end

    if Claim(PREFERRED_KEY, true) then return end
    for _, key in ipairs(FALLBACK_KEYS) do
        if Claim(key, false) then return end
    end

    ClasslessWildcardDB.hotkeyClaimed = true
    Print("No free hotkey was available. Bind |cffffff00Toggle Hero Advancement|r under Key Bindings > Hero Advancement.")
end

-- N went to Hero Advancement, which left the stock Talents action with no key,
-- and that window is where a tamed beast's talents are. Give it J, once per
-- account: J is the one letter the stock defaults leave free (T is Attack
-- Target). Only while J is still unbound and Talents has no key of its own; a
-- player who has put anything on either keeps it.
function CW.ClaimTalentsKey()
    ClasslessWildcardDB = ClasslessWildcardDB or {}
    if ClasslessWildcardDB.talentsKeyClaimed then return end
    if InCombatLockdown and InCombatLockdown() then return end
    if not SetBinding or not SaveBindings or not GetBindingAction then return end

    ClasslessWildcardDB.talentsKeyClaimed = true
    if GetBindingKey and GetBindingKey("TOGGLETALENTS") then return end
    local inUse = GetBindingAction("J")
    if inUse and inUse ~= "" then return end
    if not SetBinding("J", "TOGGLETALENTS") then return end
    pcall(SaveBindings, GetCurrentBindingSet and GetCurrentBindingSet() or 1)
    Print("Hotkey |cffffff00J|r opens the Talents window, where a tamed beast's talents are.")
end

-- Our confirm popups get a dark, near-opaque backing. The stock dialog
-- background is see-through, and over this panel's title and class strip the
-- popup's text was hard to read. StaticPopup1 to 4 are shared with the rest of
-- the UI, so the backing shows only while one of ours is up and hides with it.
-- Every CW_ dialog is wrapped, including any added later in this file.
do
    local function Backing(popup)
        if not popup.cwBacking then
            local t = popup:CreateTexture(nil, "BACKGROUND")
            t:SetTexture("Interface\\Buttons\\WHITE8X8")
            t:SetVertexColor(0.02, 0.02, 0.03, 0.92)
            -- inside the dialog border's own insets, so the gold frame stays
            t:SetPoint("TOPLEFT", popup, "TOPLEFT", 11, -11)
            t:SetPoint("BOTTOMRIGHT", popup, "BOTTOMRIGHT", -11, 11)
            popup.cwBacking = t
        end
        return popup.cwBacking
    end
    for key, d in pairs(StaticPopupDialogs) do
        if type(key) == "string" and key:sub(1, 3) == "CW_" and type(d) == "table" then
            local show, hide = d.OnShow, d.OnHide
            d.OnShow = function(self, ...)
                Backing(self):Show()
                if show then return show(self, ...) end
            end
            d.OnHide = function(self, ...)
                if self.cwBacking then self.cwBacking:Hide() end
                if hide then return hide(self, ...) end
            end
        end
    end
end

-- exposed for debugging and third-party extensions
_G.ClasslessWildcard_API = CW


