--[[ Shuttlecraft -- the power gauge (ENERGY.md 3.4).

    A small LCARS strip at the top of the screen: the crystal burning as a
    bar and a number, and the spares behind it as pips. When the ship is dark
    it reads EMERGENCY POWER, blinking slowly.

    Shown only **while aboard, or seated in her**: the cabin by its own shape
    (U.isAboard), the seats by the vehicle's script. Everywhere else the ship's
    power is not the player's immediate business, and a strip that never went
    away would be one more thing on a screen that already has a lot on it.

    It reads the ship state this client already has and asks the server for
    nothing. It is not interactive: it never takes the mouse or a
    controller's focus, which is how it meets DEV_GUIDE's *Every panel must
    work with a controller* -- there is nothing on it to reach.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Ship"
require "TREK/TREK_Power"
require "TREK/TREK_Vehicle"
require "TREK/TREK_Helm"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Pw = TREK.Power
local V = TREK.Vehicle
local H = TREK.Helm
local P = H.P

local HUD = {}
TREK.PowerHUD = HUD

HUD.W, HUD.H = 220, 40
-- Pips for the spares; more than this reads as a number instead.
HUD.MaxPips = 8
-- The blink when dark: on for most of each period, never off for long.
HUD.BlinkMs, HUD.BlinkOnMs = 1600, 1100

--- True when this player should see the gauge.
function HUD.shouldShow(player)
    if not player then return false end
    if U.try("hud.dead", function() return player:isDead() end) ~= false then
        return false
    end
    local x = U.try("hud.x", function() return player:getX() end)
    local y = U.try("hud.y", function() return player:getY() end)
    local z = U.try("hud.z", function() return player:getZ() end)
    if x and y and U.isAboard(x, y, z) then return true end
    local vehicle = U.try("hud.vehicle", function() return player:getVehicle() end)
    return V.isShuttle(vehicle)
end

TREKPowerHUD = ISUIElement:derive("TREKPowerHUD")

function TREKPowerHUD:new()
    local sw = U.try("hud.screenW", function() return getCore():getScreenWidth() end) or 800
    local o = ISUIElement.new(self, math.floor(sw / 2 - HUD.W / 2), 8, HUD.W, HUD.H)
    o.playerNum = 0
    return o
end

-- Never captures the mouse: a click on the strip belongs to the game.
function TREKPowerHUD:onMouseDown() return false end
function TREKPowerHUD:isMouseOver() return false end

function TREKPowerHUD:render()
    local player = U.player(self.playerNum)
    if not HUD.shouldShow(player) then return end
    local w, h = self.width, self.height
    local dark = Pw.dark()

    self:drawRect(0, 0, w, h, 0.72, 0.008, 0.012, 0.028)
    H.pill(self, 4, 5, 22, 10, dark and P.red or P.peach, true, false)
    self:drawText(string.upper(getText("IGUI_TREK_PowerHeader")), 32, 3,
                  P.peach[1], P.peach[2], P.peach[3], 1, UIFont.Small)

    if dark then
        local now = U.try("hud.clock", getTimestampMs) or 0
        local on = (now % HUD.BlinkMs) < HUD.BlinkOnMs
        if on then
            self:drawTextCentre(getText("IGUI_TREK_PowerEmergency"), w / 2, 20,
                                P.red[1], P.red[2], P.red[3], 1, UIFont.Small)
        end
        self:drawRectBorder(0, 0, w, h, 0.8, P.red[1], P.red[2], P.red[3])
        return
    end

    -- The number, and the spares as pips beside the title.
    local reserve = math.floor(Pw.reserve())
    self:drawTextRight(tostring(reserve), w - 6, 3,
                       P.text[1], P.text[2], P.text[3], 1, UIFont.Small)
    local spares = Pw.crystals()
    local px = 32 + getTextManager():MeasureStringX(UIFont.Small,
                   string.upper(getText("IGUI_TREK_PowerHeader"))) + 8
    if spares > HUD.MaxPips then
        self:drawText("x" .. tostring(spares), px, 3,
                      P.lilac[1], P.lilac[2], P.lilac[3], 1, UIFont.Small)
    else
        for i = 1, spares do
            self:drawRect(px + (i - 1) * 10, 7, 7, 7, 1, P.lilac[1], P.lilac[2], P.lilac[3])
        end
    end

    H.powerBar(self, 6, 22, w - 12, 10)
    self:drawRectBorder(0, 0, w, h, 0.5, P.blue[1], P.blue[2], P.blue[3])
end

--- Makes the gauge once and puts it on screen. It draws nothing until its
--- player is aboard or seated in her.
function HUD.ensure()
    if HUD.panel then return HUD.panel end
    local panel = TREKPowerHUD:new()
    panel:initialise()
    U.try("hud.add", function() panel:addToUIManager() end)
    HUD.panel = panel
    return panel
end

Events.OnGameStart.Add(function()
    U.try("hud.ensure", HUD.ensure)
end)

return HUD
