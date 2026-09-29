--[[ Shuttlecraft -- raids, as a player meets them (RAIDS.md).

    The Captain's request panel (her portrait, what she asks, the countdown,
    Accept / Decline), the strip at the top of the screen while a raid runs,
    the right-click way back to both, the notes, and the two beams: out to
    the raid and home again. Everything here asks; TREK_RaidsServer decides.

    **The strip is small on purpose.** The engine treats the mouse as over
    the UI by an element's rectangle alone (DEV_GUIDE: *An overlay that
    covers the screen takes the world's mouse away*), and a raid is a fight.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_Core"
require "TREK/TREK_World"
require "TREK/TREK_Raids"
require "TREK/TREK_Helm"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Ship = TREK.Ship
local Core = TREK.Core
local W = TREK.World
local Rd = TREK.Raids
local H = TREK.Helm
local P = H.P

local RU = {}
TREK.RaidsUI = RU

-- The beam in progress: { player, dir = "in"|"out", tries, x, y, z, ... }.
RU.pending = nil
-- The camp this client has been told of: { id, x, y, z }.
RU.camp = nil
-- The last call's numbers, for the panel: { id, n, distance, compass }.
RU.call = nil

-- Every refusal's words, written out whole (DEV_GUIDE: *An id assembled from
-- parts is invisible to a static check*).
RU.WHY = {
    raidOff = "IGUI_TREK_RaidOff",
    raidGone = "IGUI_TREK_RaidGone",
    raidAlready = "IGUI_TREK_RaidAlready",
    raidClearance = "IGUI_TREK_RaidClearance",
}

local function note(key, ...)
    local p = U.player(0)
    if p then U.note(p, getText(key, ...), 150, 210, 255) end
end

local function warn(key, ...)
    local p = U.player(0)
    if p then U.note(p, getText(key, ...), 255, 170, 90) end
end

---------------------------------------------------------------------------
-- The request panel
---------------------------------------------------------------------------
TREKRaidPanel = ISPanelJoypad:derive("TREKRaidPanel")

local PW, PH = 480, 320
local SIDE, TOPH, PAD, BTNH, FACE = 56, 26, 14, 28, 96

function TREKRaidPanel:new(x, y, player)
    local o = ISPanelJoypad.new(self, x, y, PW, PH)
    o.player = player
    o.playerNum = U.try("raid.playerNum", function() return player:getPlayerNum() end) or 0
    o.background = false
    o.moveWithMouse = true
    return o
end

local function button(self, x, y, w, title, fn, colour)
    local b = TREKLcarsButton:new(x, y, w, BTNH, title, self, fn, colour)
    b:initialise()
    self:addChild(b)
    return b
end

function TREKRaidPanel:createChildren()
    ISPanelJoypad.createChildren(self)
    self.closeBtn = button(self, self.width - 90, 0, 90, getText("IGUI_TREK_Close"),
                           TREKRaidPanel.close, P.violet)
    self.closeBtn.roundLeft = false
    local cx = SIDE + PAD
    local cw = self.width - cx - PAD
    local y = self.height - 16 - PAD - BTNH
    local half = (cw - 6) / 2
    self.acceptBtn = button(self, cx, y, half, "", TREKRaidPanel.onAccept, P.orange)
    self.declineBtn = button(self, cx + half + 6, y, half, getText("IGUI_TREK_RaidDecline"),
                             TREKRaidPanel.onDecline, P.lilac)
    self:insertNewLineOfButtons(self.acceptBtn, self.declineBtn)
    self:setISButtonForB(self.closeBtn)
end

--- Splits text into lines no wider than `width` in `font`.
function RU.wrap(text, font, width)
    local out, line = {}, ""
    local tm = getTextManager()
    for word in tostring(text or ""):gmatch("%S+") do
        local try = line == "" and word or (line .. " " .. word)
        if tm:MeasureStringX(font, try) <= width or line == "" then
            line = try
        else
            table.insert(out, line)
            line = word
        end
    end
    if line ~= "" then table.insert(out, line) end
    return out
end

--- What she says, as lines, for what is on offer now.
function TREKRaidPanel:lines()
    local id, kind, joining = Rd.offer(self.player)
    local out = {}
    if not id then
        table.insert(out, { getText("IGUI_TREK_RaidNothing"), P.dim })
        return out, nil
    end
    local call = RU.call and RU.call.id == id and RU.call or {}
    if joining then
        local raid = Rd.raid()
        local pct, left = Rd.buffer(raid)
        table.insert(out, { getText("IGUI_TREK_RaidAskJoin"), P.text })
        table.insert(out, { getText("IGUI_TREK_RaidUnderway", tostring(pct), tostring(left)), P.gold })
        return out, id
    end
    table.insert(out, { getText("IGUI_TREK_RaidAskOutpost"), P.text })
    if call.distance then
        table.insert(out, { getText("IGUI_TREK_RaidWhere", tostring(call.distance), tostring(call.compass or "?")),
                            P.peach })
    end
    if call.n then table.insert(out, { getText("IGUI_TREK_RaidExpect", tostring(call.n)), P.peach }) end
    local mins = Rd.minutesLeft()
    if mins then
        table.insert(out, { getText("IGUI_TREK_RaidLeft", tostring(math.floor(mins / 60)),
                                    tostring(mins % 60)), P.gold })
    end
    return out, id
end

function TREKRaidPanel:prerender()
    local w, h = self.width, self.height
    self:drawRect(0, 0, w, h, 0.97, 0.008, 0.012, 0.028)
    local function block(x, y, bw, bh, c) self:drawRect(x, y, bw, bh, 1, c[1], c[2], c[3]) end
    local R = 22
    H.pill(self, 0, 0, R * 2, R * 2, P.orange, true, true)
    block(R, 0, SIDE - R, R, P.orange)
    block(0, R, SIDE, 90 - R, P.orange)
    block(SIDE, 0, math.max(0, self.closeBtn.x - 8 - SIDE), TOPH, P.orange)
    local title = string.upper(getText("IGUI_TREK_RaidTitle"))
    local fh = getTextManager():MeasureStringY(UIFont.Medium, title) or 14
    self:drawText(title, SIDE + 12, (TOPH - fh) / 2, 0, 0, 0, 1, UIFont.Medium)
    block(0, 94, SIDE, h - 94 - 90, P.violet)
    block(0, h - 90, SIDE, 90 - R, P.lilac)
    block(R, h - R, SIDE - R, R, P.lilac)
    H.pill(self, 0, h - R * 2, R * 2, R * 2, P.lilac, true, true)
    block(SIDE, h - 16, w - SIDE - 8, 16, P.lilac)
    ISPanelJoypad.prerender(self)
end

function TREKRaidPanel:render()
    ISPanelJoypad.render(self)
    local cx = SIDE + PAD
    local y = TOPH + PAD
    local tex = TREK.CaptainUI and TREK.CaptainUI.portrait and TREK.CaptainUI.portrait()
    if tex then
        self:drawTextureScaled(tex, cx, y, FACE, FACE, 1, 1, 1, 1)
    else
        self:drawRect(cx, y, FACE, FACE, 0.5, P.blue[1] * 0.4, P.blue[2] * 0.4, P.blue[3] * 0.4)
    end
    self:drawRectBorder(cx, y, FACE, FACE, 0.5, P.blue[1], P.blue[2], P.blue[3])
    local tx = cx + FACE + 12
    local tw = self.width - tx - PAD
    local lines, id = self:lines()
    local ly = y
    for _, ln in ipairs(lines) do
        for _, piece in ipairs(RU.wrap(ln[1], UIFont.Small, tw)) do
            if ly + 16 > self.acceptBtn.y - 6 then break end
            self:drawText(piece, tx, ly, ln[2][1], ln[2][2], ln[2][3], 1, UIFont.Small)
            ly = ly + 16
        end
        ly = ly + 4
    end
    local why = Rd.acceptRefusal(self.player, id)
    local _, _, joining = Rd.offer(self.player)
    self.acceptBtn.title = why and getText(RU.WHY[why] or "IGUI_TREK_RaidGone")
        or getText(joining and "IGUI_TREK_RaidJoin" or "IGUI_TREK_RaidAccept")
    self.acceptBtn.enable = why == nil
    self.declineBtn.enable = id ~= nil and not joining
    if self.joyfocus then
        self:drawTextRight(string.upper(getText("IGUI_TREK_MedJoypadHint")), self.width - 22,
                           self.height - 15, 0, 0, 0, 1, UIFont.Small)
    end
end

function TREKRaidPanel:onAccept()
    local id = Rd.offer(self.player)
    if not id then return end
    Net.send(self.player, "raidAccept", { id = id })
    self:close()
end

function TREKRaidPanel:onDecline()
    local id = Rd.offer(self.player)
    if id then Net.send(self.player, "raidDecline", { id = id }) end
    RU.declined = id
    self:close()
end

function TREKRaidPanel:onGainJoypadFocus(joypadData)
    ISPanelJoypad.onGainJoypadFocus(self, joypadData)
    if self:getJoypadFocus() then self:restoreJoypadFocus(joypadData) else self:setJoypadFocusTopLeft(joypadData) end
end

function TREKRaidPanel:onLoseJoypadFocus(joypadData)
    ISPanelJoypad.onLoseJoypadFocus(self, joypadData)
    self:clearJoypadFocus(joypadData)
end

function TREKRaidPanel:close()
    RU.window = nil
    if self.joyfocus then
        U.try("raid.releaseFocus", function() setJoypadFocus(self.playerNum, nil) end)
    end
    self:setVisible(false)
    self:removeFromUIManager()
end

function RU.open(player)
    if not player then return nil end
    if RU.window then U.try("raid.closeOld", function() RU.window:close() end) end
    local w = U.try("raid.open", function()
        local sw = U.try("raid.sw", function() return getCore():getScreenWidth() end) or 1280
        local sh = U.try("raid.sh", function() return getCore():getScreenHeight() end) or 800
        local win = TREKRaidPanel:new(math.floor((sw - PW) / 2), math.floor((sh - PH) / 3), player)
        win:initialise()
        win:instantiate()
        win:addToUIManager()
        return win
    end)
    if not w then return nil end
    RU.window = w
    U.try("raid.focus", function()
        if JoypadState.players[w.playerNum + 1] then setJoypadFocus(w.playerNum, w) end
    end)
    return w
end

---------------------------------------------------------------------------
-- The strip, while a raid runs
---------------------------------------------------------------------------
TREKRaidStrip = ISUIElement:derive("TREKRaidStrip")

local SW, SH = 380, 26

function TREKRaidStrip:new(player)
    local sw = U.try("raid.stripW", function() return getCore():getScreenWidth() end) or 1280
    local o = ISUIElement.new(self, math.floor((sw - SW) / 2), 8, SW, SH)
    o.player = player
    return o
end

--- The strip's words, or nil when there is nothing to show this player.
function RU.stripText(player)
    local raid = Rd.raid()
    if not raid or not Rd.isMember(raid, player) then return nil end
    if raid.state == "arriving" then return getText("IGUI_TREK_RaidStripArriving") end
    if raid.state == "live" then
        local pct, left = Rd.buffer(raid)
        return getText("IGUI_TREK_RaidStrip", tostring(pct), tostring(left))
    end
    if raid.state == "won" then return getText("IGUI_TREK_RaidStripWon") end
    return getText("IGUI_TREK_RaidStripLost")
end

function TREKRaidStrip:render()
    local text = RU.stripText(self.player)
    if not text then return end
    self:drawRect(0, 0, self.width, self.height, 0.8, 0.01, 0.02, 0.05)
    self:drawRect(0, 0, 8, self.height, 1, P.orange[1], P.orange[2], P.orange[3])
    self:drawRectBorder(0, 0, self.width, self.height, 0.8, P.orange[1], P.orange[2], P.orange[3])
    self:drawTextCentre(string.upper(text), self.width / 2, 5, P.gold[1], P.gold[2], P.gold[3], 1, UIFont.Small)
end

function RU.showStrip(player)
    if RU.strip or not player then return end
    RU.strip = U.try("raid.strip", function()
        local s = TREKRaidStrip:new(player)
        s:initialise()
        s:addToUIManager()
        return s
    end)
end

---------------------------------------------------------------------------
-- The right-click way back to it
---------------------------------------------------------------------------
function RU.onOpen(_, player) RU.open(player) end
function RU.onHome(_, player) Net.send(player, "raidHome", {}) end

function RU.fillMenu(playerIndex, context, worldobjects, test)
    local player = U.player(playerIndex)
    if not player then return end
    local offered = Rd.offer(player) ~= nil
    local member = Rd.isMember(Rd.raid(), player)
    if not offered and not member then return end
    if test then return ISWorldObjectContextMenu.setTest() end
    if offered then
        context:addOption(getText("IGUI_TREK_RaidMenu"), worldobjects, RU.onOpen, player)
    end
    if member then
        local raid = Rd.raid()
        context:addOption(getText(raid.state == "won" and "IGUI_TREK_RaidHomeNow" or "IGUI_TREK_RaidRetreat"),
                          worldobjects, RU.onHome, player)
    end
end

Events.OnPreFillWorldObjectContextMenu.Add(RU.fillMenu)

---------------------------------------------------------------------------
-- The beams
---------------------------------------------------------------------------
local function busy()
    return RU.pending ~= nil or Core.moveWaiting() or (TREK.Transport and TREK.Transport.pending ~= nil)
end

--- Out to the raid.
function RU.goOut(player, args)
    if not player or busy() then return false end
    Core.requestMove(player, "raidIn", function(p)
        RU.pending = { player = p, dir = "in", tries = 0, id = args.id,
                       x = math.floor(args.x), y = math.floor(args.y), z = math.floor(args.z or 0) }
        U.note(p, getText("IGUI_TREK_Energising"))
    end)
    return true
end

--- Home again, to where they accepted from.
function RU.goHome(player, ret)
    if not player or type(ret) ~= "table" then return false end
    RU.pending = nil
    Core.requestMove(player, "raidOut", function(p)
        RU.pending = { player = p, dir = "out", tries = 0, ret = ret }
        U.note(p, getText("IGUI_TREK_Energising"))
    end)
    return true
end

local function serviceIn(job)
    local p = job.player
    if not job.arrived then
        Core.leaveSeat(p)
        Ship.playerData(p).aboard = false
        U.teleport(p, job.x, job.y, job.z)
        job.arrived = true
        job.arrivedAt = job.tries
        return false
    end
    local camp = RU.camp
    if camp and camp.id == job.id then
        U.teleport(p, camp.x, camp.y, camp.z)
        note("IGUI_TREK_RaidArrived")
        U.log("raids: arrived at the outpost, %d,%d", camp.x, camp.y)
        return true
    end
    if job.tries - job.arrivedAt > C.RaidArriveTicks then
        warn("IGUI_TREK_RaidNoCamp")
        Net.send(p, "raidHome", {})
        return true
    end
    Core.hold(p, job.x, job.y, job.z)
    return false
end

local function serviceOut(job)
    local p, ret = job.player, job.ret
    if ret.kind == "cabin" then
        Core.beginArrival(p, true)
        return true
    end
    if ret.kind == "deck" and TREK.AdirondackClient then
        TREK.AdirondackClient.beginArrival(p, ret.x, ret.y, ret.k)
        return true
    end
    if not job.arrived then
        U.teleport(p, ret.x, ret.y, ret.z)
        job.arrived = true
        job.arrivedAt = job.tries
        return false
    end
    local spot = W.spotNear(ret.x, ret.y, ret.z)
    if not spot and job.tries - job.arrivedAt < 300 then
        Core.hold(p, ret.x, ret.y, ret.z)
        return false
    end
    spot = spot or { x = ret.x, y = ret.y, z = ret.z }
    U.teleport(p, spot.x, spot.y, spot.z)
    U.log("raids: home at %d,%d", spot.x, spot.y)
    return true
end

local function servicePending()
    local job = RU.pending
    if not job then return end
    if not job.player then RU.pending = nil return end
    job.tries = job.tries + 1
    if job.tries < C.BeamDelay then return end
    local done
    if job.dir == "in" then done = serviceIn(job) else done = serviceOut(job) end
    if done then RU.pending = nil end
end

Events.OnTick.Add(function()
    U.try("raids.pending", servicePending)
end)

---------------------------------------------------------------------------
-- What the server says
---------------------------------------------------------------------------
Net.onClient("raidCall", function(args)
    local p = U.player(0)
    if not p then return end
    RU.call = { id = args.id, n = args.n, distance = args.distance, compass = args.compass }
    U.note(p, getText("IGUI_TREK_RaidCallNote", tostring(args.hours or C.RaidOfferHours)), 255, 200, 90)
    U.try("raid.chirp", function() p:playSoundLocal("TREK_TricorderChirp") end)
    RU.open(p)
end)

Net.onClient("raidWarn", function(args)
    warn("IGUI_TREK_RaidWarn", tostring(args.minutes or "?"))
end)

Net.onClient("raidLapsed", function(args)
    if RU.window then RU.window:close() end
    note(args and args.declined and "IGUI_TREK_RaidDeclinedAll" or "IGUI_TREK_RaidLapsed")
end)

Net.onClient("raidJoined", function(args)
    local p = U.player(0)
    if p and args.by ~= Ship.usernameOf(p) then note("IGUI_TREK_RaidJoined", tostring(args.by)) end
end)

Net.onClient("raidGo", function(args)
    local p = U.player(0)
    if not p then return end
    RU.camp = nil
    RU.showStrip(p)
    RU.goOut(p, args)
end)

Net.onClient("raidCamp", function(args)
    RU.camp = { id = args.id, x = args.x, y = args.y, z = args.z }
end)

Net.onClient("raidWon", function(args)
    note("IGUI_TREK_RaidWonNote", tostring(args.secs or 60))
end)

-- Why it was lost: a note that only said "lost" hid a raid timed out
-- mid-fight behind the look of a defeat.
local LOST = { time = "IGUI_TREK_RaidLostTime", left = "IGUI_TREK_RaidLostLeft" }

Net.onClient("raidLost", function(args)
    warn(LOST[args and args.why] or "IGUI_TREK_RaidLostNote")
end)

-- The raid's dead standing now, by online id: this machine keeps the pace
-- and the hunt of any it simulates (TREK_Raids, Rd.drive).
Net.onClient("raidZeds", function(args)
    Rd.setZedIds(args and args.list)
end)

Net.onClient("raidReturn", function(args)
    local p = U.player(0)
    if p then RU.goHome(p, args) end
end)

return RU
