--[[ Shuttlecraft -- the long-range sensor console.

    The ship's fourth LCARS panel, after the helm, the replicator and the
    Doctor, and built the same way: an ISPanelJoypad with TREKLcarsButtons,
    every control registered for a controller, close on B.

    What it shows, and why each line is on it:

      * the **reserve**, because that is what a probe is made of;
      * **probes in the rack**, because a launch costs one of those and not
        energy -- a number a player can plan around rather than arithmetic
        they have to do;
      * the **flight**, with a progress bar, because a probe that is simply
        "away" for an hour of game time with nothing moving is a feature a
        player assumes is broken;
      * the **contacts**, with bearing and distance, because that is the
        answer the whole system exists to produce.

    Everything here is a *request*. The panel reads the ship state the server
    last published, which is good enough to grey a button and never good
    enough to act on, so every button asks and the server checks again.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Ship"
require "TREK/TREK_Core"
require "TREK/TREK_Net"
require "TREK/TREK_Probes"
require "TREK/TREK_Power"
require "TREK/TREK_Helm"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Core = TREK.Core
local Net = TREK.Net
local P = TREK.Probes
local H = TREK.Helm
local Pal = H.P

local S = {}
TREK.ProbeUI = S

local PW, PH = 420, 470
local SIDE, TOPH, PAD, ROWH = 56, 26, 14, 26

TREKProbeWindow = ISPanelJoypad:derive("TREKProbeWindow")

function TREKProbeWindow:new(x, y, player)
    local o = ISPanelJoypad.new(self, x, y, PW, PH)
    o.player = player
    o.playerNum = U.try("probe.playerNum", function()
        return player:getPlayerNum()
    end) or 0
    o.background = false
    o.moveWithMouse = true
    return o
end

function TREKProbeWindow:createChildren()
    ISPanelJoypad.createChildren(self)
    local cx = SIDE + PAD
    local cw = self.width - cx - PAD
    local gap = 8

    self.closeBtn = TREKLcarsButton:new(self.width - 90, 0, 90, TOPH,
        getText("IGUI_TREK_Close"), self, TREKProbeWindow.close, Pal.violet)
    self.closeBtn.roundLeft = false
    self.closeBtn:initialise()
    self:addChild(self.closeBtn)

    self.statusY = TOPH + PAD
    self.barY = self.statusY + 52
    local btnY = self.barY + 34

    local half = (cw - gap) / 2
    self.buildBtn = TREKLcarsButton:new(cx, btnY, half, ROWH, "", self,
                                        TREKProbeWindow.onBuild, Pal.gold)
    self.buildBtn:initialise()
    self:addChild(self.buildBtn)

    self.launchBtn = TREKLcarsButton:new(cx + half + gap, btnY, half, ROWH, "",
                                         self, TREKProbeWindow.onLaunch,
                                         Pal.orange)
    self.launchBtn:initialise()
    self:addChild(self.launchBtn)

    self.listY = btnY + ROWH + PAD + 16
    local listH = self.height - self.listY - PAD - ROWH - gap
    self.list = ISScrollingListBox:new(cx, self.listY, cw, listH)
    self.list:initialise()
    self.list:instantiate()
    self.list.itemheight = 22
    self.list.selected = 1
    self.list.drawBorder = true
    self.list.backgroundColor = { r = 0.02, g = 0.03, b = 0.06, a = 0.55 }
    self.list.borderColor = { r = Pal.lilac[1], g = Pal.lilac[2],
                              b = Pal.lilac[3], a = 0.55 }
    self:addChild(self.list)

    self.showBtn = TREKLcarsButton:new(cx, self.height - PAD - ROWH, cw, ROWH,
                                       getText("IGUI_TREK_ProbeShow"), self,
                                       TREKProbeWindow.onShow, Pal.lilac)
    self.showBtn:initialise()
    self:addChild(self.showBtn)

    -- Every control on the stick, in the order a thumb would reach them.
    self:insertNewLineOfButtons(self.buildBtn, self.launchBtn)
    self:insertNewListOfButtons({ self.list })
    self:insertNewLineOfButtons(self.showBtn)
    self:setISButtonForB(self.closeBtn)
end

function TREKProbeWindow:close()
    S.window = nil
    if self.joyfocus then
        U.try("probe.releaseFocus", function()
            setJoypadFocus(self.playerNum, nil)
        end)
    end
    self:setVisible(false)
    self:removeFromUIManager()
end

function TREKProbeWindow:onBuild()
    Core.send(self.player, "buildProbe", {})
end

function TREKProbeWindow:onLaunch()
    Core.send(self.player, "launchProbe", {})
end

function TREKProbeWindow:onShow()
    local row = self.list.items[self.list.selected]
    local contact = row and row.item
    if not contact then return end
    if TREK.MapContacts then
        TREK.MapContacts.focus(self.playerNum, contact.id)
    end
end

--- Rebuilds the contact list. Cheap, and done every frame on purpose: the
--- list is a view of a table the server republishes, and a list that only
--- refreshed on open would go stale the moment a probe reported.
function TREKProbeWindow:refresh()
    local selected = self.list.selected
    self.list:clear()
    local px = U.try("probe.px", function() return self.player:getX() end) or 0
    local py = U.try("probe.py", function() return self.player:getY() end) or 0
    for _, contact in ipairs(P.unresolved()) do
        local key = C.ContactLabels[contact.kind]
        if key then
            local dist = math.floor(math.sqrt((contact.x - px) ^ 2
                                              + (contact.y - py) ^ 2))
            self.list:addItem(getText(key, tostring(dist),
                                      S.bearing(px, py, contact.x, contact.y)),
                              contact)
        end
    end
    if selected >= 1 and selected <= #self.list.items then
        self.list.selected = selected
    end
end

function TREKProbeWindow:prerender()
    self:refresh()

    -- The helm's own furniture, for the fourth time. Four Starfleet consoles
    -- in one mod should not look like four mods, so the elbows, the sidebar
    -- and the title bar are the same shapes the helm and the Doctor draw --
    -- in this panel's own colours, so it still reads as its own station.
    local w, h = self.width, self.height
    self:drawRect(0, 0, w, h, 0.97, 0.008, 0.012, 0.028)

    local function block(x, y, bw, bh, c)
        self:drawRect(x, y, bw, bh, 1, c[1], c[2], c[3])
    end

    local RAD = 22
    H.pill(self, 0, 0, RAD * 2, RAD * 2, Pal.orange, true, true)
    block(RAD, 0, SIDE - RAD, RAD, Pal.orange)
    block(0, RAD, SIDE, 96 - RAD, Pal.orange)

    local title = string.upper(getText("IGUI_TREK_SensorTitle"))
    local closeX = self.closeBtn and self.closeBtn.x or (w - 90)
    block(SIDE, 0, math.max(0, closeX - 8 - SIDE), TOPH, Pal.orange)
    local fh = getTextManager():MeasureStringY(UIFont.Medium, title) or 14
    self:drawText(title, SIDE + 12, (TOPH - fh) / 2, 0, 0, 0, 1, UIFont.Medium)

    block(0, 100, SIDE, h - 130 - 100, Pal.gold)
    block(0, h - 130, SIDE, 130 - RAD, Pal.lilac)
    block(RAD, h - RAD, SIDE - RAD, RAD, Pal.lilac)
    H.pill(self, 0, h - RAD * 2, RAD * 2, RAD * 2, Pal.lilac, true, true)
    block(SIDE, h - 16, w - SIDE - 8, 16, Pal.lilac)

    local s = TREK.Ship.get()
    local rack = s.probes or 0
    local active = P.active()

    self.buildBtn.title = getText("IGUI_TREK_ProbeBuild", tostring(C.ProbeCost))
    self.buildBtn.enable = rack < C.MaxProbes
                           and math.floor(TREK.Power.reserve()) >= C.ProbeCost

    self.launchBtn.title = getText("IGUI_TREK_ProbeLaunchBtn")
    self.launchBtn.enable = active == nil and rack > 0

    self.showBtn.enable = #self.list.items > 0

    ISPanelJoypad.prerender(self)
end

function TREKProbeWindow:render()
    ISPanelJoypad.render(self)
    local cx = SIDE + PAD
    local cw = self.width - cx - PAD

    local s = TREK.Ship.get()
    local rack = s.probes or 0
    local reserve = math.floor(TREK.Power.reserve())
    local active = P.active()

    self:drawText(getText("IGUI_TREK_ProbeReserve", tostring(reserve),
                          tostring(C.PowerMax)),
                  cx, self.statusY, Pal.gold[1], Pal.gold[2], Pal.gold[3], 1,
                  UIFont.Small)
    local rc = rack > 0 and Pal.lilac or Pal.dim
    self:drawTextRight(getText("IGUI_TREK_ProbeRack", tostring(rack),
                               tostring(C.MaxProbes)),
                       self.width - PAD, self.statusY, rc[1], rc[2], rc[3], 1,
                       UIFont.Small)

    -- The flight. A bar rather than a number, because "in flight" with
    -- nothing moving for an hour of game time reads as broken.
    local y = self.statusY + 22
    if active then
        local frac = math.max(0, math.min(1, active.progress
                                             / math.max(1, active.ticks)))
        self:drawText(getText("IGUI_TREK_ProbeFlight",
                              tostring(math.floor(frac * 100)) .. "%"),
                      cx, y, Pal.blue[1], Pal.blue[2], Pal.blue[3], 1,
                      UIFont.Small)
        self:drawRect(cx, self.barY, cw, 6, 0.5, 0.05, 0.06, 0.10)
        self:drawRect(cx, self.barY, cw * frac, 6, 0.95,
                      Pal.blue[1], Pal.blue[2], Pal.blue[3])
    else
        self:drawText(getText("IGUI_TREK_ProbeIdle"), cx, y,
                      Pal.dim[1], Pal.dim[2], Pal.dim[3], 1, UIFont.Small)
    end

    local label = #self.list.items > 0
        and getText("IGUI_TREK_ProbeContacts", tostring(#self.list.items))
        or getText("IGUI_TREK_NoContacts")
    self:drawText(label, cx, self.listY - 18,
                  Pal.peach[1], Pal.peach[2], Pal.peach[3], 1, UIFont.Small)

    -- The last probe's verdict, kept on screen. The note above is gone in a
    -- few seconds and a player who was walking when it landed would otherwise
    -- never learn that the probe came back at all -- which reads as the
    -- launch having done nothing.
    local report = s.probeReport
    if report and not active then
        local text = report.found and getText("IGUI_TREK_ProbeLastFound")
                     or getText("IGUI_TREK_ProbeLastEmpty")
        local c = report.found and Pal.blue or Pal.dim
        self:drawTextRight(text, self.width - PAD, y,
                           c[1], c[2], c[3], 1, UIFont.Small)
    end
end

---------------------------------------------------------------------------
-- Bearings
---------------------------------------------------------------------------
-- tan(22.5 degrees): half an octant, which is all the trigonometry a compass
-- point needs. Deliberately not math.atan2 -- Kahlua has it and Lua 5.3
-- onwards does not, so it works in the game and throws in the tests.
local OCTANT = 0.4142135

function S.bearing(fromX, fromY, toX, toY)
    local dx, dy = toX - fromX, toY - fromY
    local ax, ay = math.abs(dx), math.abs(dy)
    if ax <= OCTANT * ay then
        return dy < 0 and "N" or "S"
    elseif ay <= OCTANT * ax then
        return dx > 0 and "E" or "W"
    elseif dy < 0 then
        return dx > 0 and "NE" or "NW"
    else
        return dx > 0 and "SE" or "SW"
    end
end

---------------------------------------------------------------------------
-- What the ship says when a probe comes home
---------------------------------------------------------------------------
-- A note over the player's head, whether or not the console is open. A probe
-- takes an hour of game time and nobody watches the panel for an hour; the
-- one moment worth interrupting them for is the one where it lands.
Net.onClient("probeReport", function(args)
    local player = U.player(0)
    if not player then return end
    if args and args.found then
        U.note(player, getText("IGUI_TREK_ProbeFound"), 150, 220, 255)
    else
        U.note(player, getText("IGUI_TREK_ProbeEmpty"), 220, 190, 120)
    end
end)

---------------------------------------------------------------------------
-- Opening it
---------------------------------------------------------------------------
function S.open(player)
    if S.window then
        U.try("probe.closeOld", function() S.window:close() end)
    end
    local w = U.try("probe.open", function()
        local win = TREKProbeWindow:new(200, 130, player)
        win:initialise()
        win:instantiate()
        win:addToUIManager()
        return win
    end)
    if not w then return nil end
    S.window = w
    U.try("probe.focus", function()
        if JoypadState.players[w.playerNum + 1] then
            setJoypadFocus(w.playerNum, w)
        end
    end)
    return w
end

return S
