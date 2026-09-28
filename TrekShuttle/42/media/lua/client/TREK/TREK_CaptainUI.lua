--[[ Shuttlecraft -- Captain Titus, in front of the player (CAPTAIN.md 3, 5.6).

    The way in, and the panel. Everything here is presentation and a request:
    the conversation is the server's (TREK_CaptainServer), which replies with
    the node to show, the options this player may take and, on the hub, the
    topics with their NEW marks. The panel never asks a condition itself.

    **The way in is a right-click near her chair**, keyed to squares round it
    (TREK_Captain.clicked) rather than to the body sitting in it: a right-click
    lands on the floor square under the cursor, and the conversation has to
    work whether or not the crew director has a body in the chair
    (CAPTAIN.md 5.5).

    **The buttons are a fixed pool**, shown, hidden and relabelled for each
    answer, and re-registered for the controller each time -- the PADD's
    screen does the same with the channel's options.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_Captain"
require "TREK/TREK_Core"
require "TREK/TREK_Helm"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Cap = TREK.Captain
local Core = TREK.Core
local H = TREK.Helm
local P = H.P

local M = {}
TREK.CaptainUI = M

-- What the server last said: { node, avail, topics, named, ended }.
M.reply = nil

TREKCaptainWindow = ISPanelJoypad:derive("TREKCaptainWindow")

local W, HGT = 620, 584
local SIDE, TOPH, BOTH, PAD, RAD = 56, 26, 16, 14, 22
local FACE = 96
local SPEECH = 232        -- the height her words may take
local BTN, GAP = 26, 6
local OPTIONS = 5         -- a node's options, one to a row
local TOPICS = 14         -- the hub's topics, two to a row

function TREKCaptainWindow:new(x, y, player)
    local o = ISPanelJoypad.new(self, x, y, W, HGT)
    o.player = player
    o.playerNum = U.try("captain.playerNum", function() return player:getPlayerNum() end) or 0
    o.background = false
    o.moveWithMouse = true
    return o
end

local function button(self, x, y, w, title, onclick, colour, arg)
    local b = TREKLcarsButton:new(x, y, w, BTN, title, self, onclick, colour)
    b:initialise()
    b.captainArg = arg
    self:addChild(b)
    return b
end

function TREKCaptainWindow:createChildren()
    ISPanelJoypad.createChildren(self)
    local cx = SIDE + PAD
    local cw = self.width - cx - PAD

    self.closeBtn = TREKLcarsButton:new(self.width - 90, 0, 90, TOPH,
        getText("IGUI_TREK_CaptClose"), self, TREKCaptainWindow.close, P.violet)
    self.closeBtn.roundLeft = false
    self.closeBtn:initialise()
    self:addChild(self.closeBtn)

    self.faceY = TOPH + PAD
    self.btnY = self.faceY + SPEECH + 8
    local bottomY = self.height - BOTH - PAD - BTN

    -- A node's options, one to a row.
    self.optBtns = {}
    for i = 1, OPTIONS do
        self.optBtns[i] = button(self, cx, self.btnY + (i - 1) * (BTN + GAP), cw, "",
                                 TREKCaptainWindow.onOption, P.peach, i)
    end
    -- The topics, two to a row, in the same space.
    self.topicBtns = {}
    local half = (cw - GAP) / 2
    for i = 1, TOPICS do
        local col, row = (i - 1) % 2, math.floor((i - 1) / 2)
        self.topicBtns[i] = button(self, cx + col * (half + GAP),
                                   self.btnY + row * (BTN + GAP), half, "",
                                   TREKCaptainWindow.onTopic, P.blue, i)
    end
    self.backBtn = button(self, cx, bottomY, half, getText("IGUI_TREK_CaptBack"),
                          TREKCaptainWindow.onBack, P.lilac)
    self.byeBtn = button(self, cx + half + GAP, bottomY, half, getText("IGUI_TREK_CaptBye"),
                         TREKCaptainWindow.onBye, P.orange)

    self:setISButtonForB(self.closeBtn)
    self:layout()
end

---------------------------------------------------------------------------
-- Showing what the server said
---------------------------------------------------------------------------
--- Shows, hides and labels the pool for the current reply, and puts exactly
--- the shown buttons on the stick.
function TREKCaptainWindow:layout()
    local r = M.reply
    local nd = r and r.node and Cap.tree().nodes[r.node]
    for _, b in ipairs(self.optBtns) do b:setVisible(false) b.captainIndex = nil end
    for _, b in ipairs(self.topicBtns) do b:setVisible(false) b.captainTopic = nil end
    self.backBtn:setVisible(false)
    self.byeBtn:setVisible(false)

    local rows = {}
    if nd and r.ended then
        -- A goodbye: nothing more to ask.
    elseif nd and r.topics then
        local row = {}
        for i, t in ipairs(r.topics) do
            local b = self.topicBtns[i]
            if b then
                local topic = Cap.tree().topics[t.id]
                b.title = getText(topic.title)
                b.colour = t.new and P.orange or P.blue
                b.captainTopic = t.id
                b.captainNew = t.new == true
                b:setVisible(true)
                table.insert(row, b)
                if #row == 2 then table.insert(rows, row) row = {} end
            end
        end
        if #row > 0 then table.insert(rows, row) end
        self.byeBtn:setVisible(true)
        table.insert(rows, { self.byeBtn })
    elseif nd then
        local fresh = {}
        for _, i in ipairs(r.fresh or {}) do fresh[i] = true end
        local shown = 0
        for _, i in ipairs(r.avail or {}) do
            local o = nd.options and nd.options[i]
            if o and shown < OPTIONS then
                shown = shown + 1
                local b = self.optBtns[shown]
                b.title = getText(o.k, "", "", Cap.fullName(self.player))
                b.colour = fresh[i] and P.orange or P.peach
                b.captainIndex = i
                b:setVisible(true)
                table.insert(rows, { b })
            end
        end
        if nd.topic ~= "HUB" then
            self.backBtn:setVisible(true)
            self.byeBtn:setVisible(true)
            table.insert(rows, { self.backBtn, self.byeBtn })
        elseif shown == 0 then
            self.byeBtn:setVisible(true)
            table.insert(rows, { self.byeBtn })
        end
    end

    -- The stick sees exactly what is shown (ISPanelJoypad.clearJoypadButtonsList).
    if self.joyfocus then self:clearJoypadFocus(self.joyfocus) end
    self.joypadIndex, self.joypadIndexY = 1, 1
    self.joypadButtons, self.joypadButtonsY = {}, {}
    for _, row in ipairs(rows) do self:insertNewListOfButtons(row) end
    if #rows == 0 then self:insertNewLineOfButtons(self.closeBtn) end
    if self.joyfocus then
        U.try("captain.focus", function() self:setJoypadFocusTopLeft(self.joyfocus) end)
    end
end

--- Her lines for the current node, wrapped: { { text, r, g, b } }.
function TREKCaptainWindow:speech(width)
    local r = M.reply
    local out = {}
    local nd = r and r.node and Cap.tree().nodes[r.node]
    if not nd then
        table.insert(out, { text = getText("IGUI_TREK_CaptWaiting"), c = P.dim })
        return out
    end
    local a1 = Cap.address(self.player, r.named)
    local a2 = Cap.rankTitle(self.player)
    for _, ln in ipairs(nd.lines) do
        local v = Cap.tree().voices[ln.v] or Cap.tree().voices.captain
        local text = getText(ln.k, a1, a2)
        for _, part in ipairs(TREK.CaptainUI.wrap(text, width)) do
            table.insert(out, { text = part, c = { v.r, v.g, v.b } })
        end
        table.insert(out, { gap = true })
    end
    return out
end

---------------------------------------------------------------------------
-- Drawing
---------------------------------------------------------------------------
function TREKCaptainWindow:prerender()
    -- A panel nobody is standing at closes itself, as the Doctor's does.
    if self.player and not Cap.inReach(self.player) then
        self:close()
        return
    end
    local w, h = self.width, self.height
    self:drawRect(0, 0, w, h, 0.97, 0.008, 0.012, 0.028)
    local function block(x, y, bw, bh, c)
        self:drawRect(x, y, bw, bh, 1, c[1], c[2], c[3])
    end
    H.pill(self, 0, 0, RAD * 2, RAD * 2, P.gold, true, true)
    block(RAD, 0, SIDE - RAD, RAD, P.gold)
    block(0, RAD, SIDE, 96 - RAD, P.gold)
    local title = string.upper(getText("IGUI_TREK_CaptTitle"))
    local closeX = self.closeBtn and self.closeBtn.x or (w - 90)
    block(SIDE, 0, math.max(0, closeX - 8 - SIDE), TOPH, P.gold)
    local fh = getTextManager():MeasureStringY(UIFont.Medium, title) or 14
    self:drawText(title, SIDE + 12, (TOPH - fh) / 2, 0, 0, 0, 1, UIFont.Medium)
    block(0, 100, SIDE, h - 130 - 100, P.orange)
    block(0, h - 130, SIDE, 130 - RAD, P.lilac)
    block(RAD, h - RAD, SIDE - RAD, RAD, P.lilac)
    H.pill(self, 0, h - RAD * 2, RAD * 2, RAD * 2, P.lilac, true, true)
    block(SIDE, h - BOTH, w - SIDE - BOTH / 2, BOTH, P.lilac)
end

function TREKCaptainWindow:render()
    ISPanelJoypad.render(self)
    local cx = SIDE + PAD
    local cw = self.width - cx - PAD
    local tex = M.portrait()
    if tex then
        self:drawTextureScaled(tex, cx, self.faceY, FACE, FACE, 1, 1, 1, 1)
    else
        self:drawRect(cx, self.faceY, FACE, FACE, 0.5,
                      P.gold[1] * 0.4, P.gold[2] * 0.4, P.gold[3] * 0.4)
    end
    self:drawRectBorder(cx, self.faceY, FACE, FACE, 0.5, P.gold[1], P.gold[2], P.gold[3])

    -- Her words, beside the portrait and under it: as many rows as fit.
    local tx = cx + FACE + 12
    local y = self.faceY
    local bottom = self.faceY + SPEECH - 14
    for _, row in ipairs(self:speech(cw - FACE - 12)) do
        if row.gap then
            y = y + 6
        elseif y <= bottom then
            self:drawText(row.text, tx, y, row.c[1], row.c[2], row.c[3], 1, UIFont.Small)
            y = y + 16
        end
    end

    -- The NEW mark's legend, when the hub shows one.
    local r = M.reply
    if r and r.topics then
        for _, t in ipairs(r.topics) do
            if t.new then
                self:drawTextRight(string.upper(getText("IGUI_TREK_CaptNew")),
                                   self.width - PAD, self.btnY - 18,
                                   P.orange[1], P.orange[2], P.orange[3], 1, UIFont.Small)
                break
            end
        end
    end

    if self.joyfocus then
        self:drawTextRight(string.upper(getText("IGUI_TREK_CaptJoypadHint")),
                           self.width - BOTH - 6, self.height - BOTH + 1,
                           0, 0, 0, 1, UIFont.Small)
    end
end

---------------------------------------------------------------------------
-- Controls
---------------------------------------------------------------------------
local function ask(self, args)
    local r = M.reply
    if not r or not r.node then return end
    args.node = r.node
    Core.send(self.player, "captainAsk", args)
end

function TREKCaptainWindow:onOption(b)
    if b and b.captainIndex then ask(self, { o = b.captainIndex }) end
end

function TREKCaptainWindow:onTopic(b)
    if b and b.captainTopic then ask(self, { topic = b.captainTopic }) end
end

function TREKCaptainWindow:onBack()
    ask(self, { back = true })
end

function TREKCaptainWindow:onBye()
    ask(self, { bye = true })
end

function TREKCaptainWindow:onGainJoypadFocus(joypadData)
    ISPanelJoypad.onGainJoypadFocus(self, joypadData)
    self:setJoypadFocusTopLeft(joypadData)
end

function TREKCaptainWindow:onLoseJoypadFocus(joypadData)
    ISPanelJoypad.onLoseJoypadFocus(self, joypadData)
    self:clearJoypadFocus(joypadData)
end

function TREKCaptainWindow:close()
    M.window = nil
    M.reply = nil
    Core.send(self.player, "captainClose", {})
    if self.joyfocus then
        U.try("captain.releaseFocus", function() setJoypadFocus(self.playerNum, nil) end)
    end
    self:setVisible(false)
    self:removeFromUIManager()
end

---------------------------------------------------------------------------
-- Words
---------------------------------------------------------------------------
--- Breaks a line into pieces that fit `width`, by word.
function M.wrap(text, width)
    local tm = getTextManager()
    local out, current = {}, ""
    for word in string.gmatch(tostring(text or ""), "%S+") do
        local try = (current == "") and word or (current .. " " .. word)
        if tm:MeasureStringX(UIFont.Small, try) <= width then
            current = try
        else
            if current ~= "" then table.insert(out, current) end
            current = word
        end
    end
    if current ~= "" then table.insert(out, current) end
    return out
end

local portraitTex, portraitTried = nil, false

--- Her portrait, loaded once. Optional: a missing file is a lit panel.
function M.portrait()
    if portraitTried then return portraitTex end
    portraitTried = true
    portraitTex = U.try("captain.portrait", function()
        return getTexture("media/ui/TREK_CaptainPortrait.png")
    end)
    return portraitTex
end

---------------------------------------------------------------------------
-- Opening it
---------------------------------------------------------------------------
function M.open(player)
    if M.window then U.try("captain.closeOld", function() M.window:close() end) end
    M.reply = nil
    local w = U.try("captain.open", function()
        local win = TREKCaptainWindow:new(140, 90, player)
        win:initialise()
        win:instantiate()
        win:addToUIManager()
        return win
    end)
    if not w then return nil end
    M.window = w
    U.try("captain.joypad", function()
        if JoypadState.players[w.playerNum + 1] then setJoypadFocus(w.playerNum, w) end
    end)
    Core.send(player, "captainTalk", {})
    return w
end

function M.onSpeak(_, player)
    M.open(player)
end

function M.fillMenu(playerIndex, context, worldobjects, test)
    local player = U.player(playerIndex)
    if not player or not TREK.Adirondack.onAdirondack(player) then return end
    local x, y, z = U.clickedSquare(playerIndex, context, player)
    if not x or not Cap.clicked(x, y, z) then return end
    if test then return ISWorldObjectContextMenu.setTest() end
    local option = context:addOption(getText("IGUI_TREK_CaptSpeak"), worldobjects,
                                     M.onSpeak, player)
    -- Shown and greyed, never hidden, with the reason on it.
    if not Cap.inReach(player) then
        option.notAvailable = true
        option.toolTip = ISWorldObjectContextMenu.addToolTip()
        option.toolTip.description = getText("IGUI_TREK_CaptFar")
    end
    return true
end

Events.OnPreFillWorldObjectContextMenu.Add(M.fillMenu)

---------------------------------------------------------------------------
-- What the server says back
---------------------------------------------------------------------------
TREK.Net.onClient("captainSay", function(args)
    M.reply = {
        node = args.node,
        avail = type(args.avail) == "table" and args.avail or {},
        fresh = type(args.fresh) == "table" and args.fresh or {},
        topics = type(args.topics) == "table" and args.topics or nil,
        named = args.named == true,
        ended = args.ended == true,
    }
    if M.window then U.try("captain.layout", function() M.window:layout() end) end
end)

return M
