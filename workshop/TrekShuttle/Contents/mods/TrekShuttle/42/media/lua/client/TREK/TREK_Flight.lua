--[[ Shuttlecraft -- hands-on local flight.

    The exterior hull is a square-bound world item, not a vehicle. During
    flight the pilot's own body is the camera and chunk-streaming proxy: hidden
    from view, and held above the ground rather than on it. A UI-layer shadow
    marks the ground under the ship. Core and Travel remain authoritative for
    hull cleanup and safe landing.

    Why the body hovers instead of being "protected". Build 42's setGodMod,
    setZombiesDontAttack, setInvincible, setNoClip and setInvisible all check
    the character's role for a matching capability and silently do nothing
    for an ordinary player -- god mode during flight never worked, and the dead
    scratched a pilot hovering still over them. There is a route around the
    role check, but it is gated on Core.debug: it would pass every test run
    with -debug and fail for every Workshop player. Zombies attack only on
    their own floor, so a body C.FlightHoverHeight above the ground is out of
    reach with no permissions, no cheats and no zombie handling at all, and
    the dead still see the ship and gather beneath it.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local F = {}
TREK.Flight = F

F.active = nil
F.overlay = nil

TREKFlightOverlay = ISUIElement:derive("TREKFlightOverlay")

function TREKFlightOverlay:new()
    local core = getCore()
    local o = ISUIElement:new(0, 0, core:getScreenWidth(), core:getScreenHeight())
    setmetatable(o, self)
    self.__index = self
    return o
end

--- The overlay covers the whole screen and must not swallow clicks: right-
--- click in flight is the land / enter / beam-down menu. setConsumeMouseEvents
--- is a method of the Java UIElement, which only exists once the element is
--- instantiated -- calling it on the Lua table in new() threw on every
--- takeoff, and the overlay never appeared at all.
function TREKFlightOverlay:instantiate()
    ISUIElement.instantiate(self)
    U.try("overlayPassClicks", function()
        self.javaObject:setConsumeMouseEvents(false)
    end)
end

function TREKFlightOverlay:prerender()
    ISUIElement.prerender(self)
    local flight = F.active
    if not flight then return end

    local rise = math.min(1, flight.ticks / C.FlightTakeoffTicks)
    local w = C.FlightShadowW * (0.80 + rise * 0.20)
    local h = C.FlightShadowH * (0.80 + rise * 0.20)
    -- The ground under the ship. The camera follows the pilot's raised body,
    -- so screen centre is no longer the ground; project the actual square.
    local playerNum = U.try("overlayPlayerNum", function()
        return flight.player:getPlayerNum()
    end) or 0
    local cx = U.try("shadowX", function()
        return isoToScreenX(playerNum, flight.x + 0.5, flight.y + 0.5, flight.groundZ)
    end) or self.width / 2
    local groundY = U.try("shadowY", function()
        return isoToScreenY(playerNum, flight.x + 0.5, flight.y + 0.5, flight.groundZ)
    end) or (self.height / 2 + 58)

    -- The actual 3D hull is rendered in the world. This layer only draws its
    -- projected shadow and the controls.
    for i = 0, 5 do
        local inset = i * 7
        self:drawRect(cx - w / 2 + inset, groundY - h / 2 + i * 2,
                      w - inset * 2, h - i * 3,
                      C.FlightShadowAlpha / 6, 0, 0, 0)
    end
    self:drawTextCentre(getText("IGUI_TREK_FlightControls"), cx,
        self.height - 72, 0.80, 0.92, 1.0, 0.95, UIFont.Small)
end

--- Hides the pilot's body for the flight and shows it again afterwards.
---
--- Alpha is the only part of the old "protection" that ever worked: it needs
--- no permission. It is local rendering, so in multiplayer other players see
--- the body until visibility is handled on the server (see MULTIPLAYER.md).
function F.protect(player, flight, enabled)
    if enabled then
        U.try("flightAlpha", function()
            flight.wasAlpha = player:getAlpha()
            flight.wasTargetAlpha = player:getTargetAlpha()
            player:setAlpha(0)
            player:setTargetAlpha(0)
        end)
    else
        U.try("flightAlpha", function()
            player:setAlpha(flight.wasAlpha or 1)
            player:setTargetAlpha(flight.wasTargetAlpha or 1)
        end)
    end
end

--- Where the pilot's body is held during flight: C.FlightHoverHeight floors
--- above the ground the ship is over.
function F.hoverZ(flight)
    return flight.groundZ + C.FlightHoverHeight
end

--- Puts the body back on the ground under the ship, with no fall pending.
--- Every way out of flight goes through here before anything else moves the
--- player, so none of them can drop a body from hover height.
function F.settle(player, flight)
    if not player or not flight then return end
    U.try("flightSettle", function()
        player:setZ(flight.groundZ)
        player:setLastZ(flight.groundZ)
        player:setFallTime(0)
        player:setbFalling(false)
    end)
end
local protect = F.protect

local function pin(flight)
    local player = flight and flight.player
    if not player then return end
    U.try("flightPin", function()
        -- Held above the ground, out of the dead's reach. There is no floor up
        -- here, so the engine starts a fall every tick; resetting the fall
        -- time each tick means none accumulates to be applied on landing.
        local z = F.hoverZ(flight)
        player:setX(flight.x + 0.5)
        player:setY(flight.y + 0.5)
        player:setZ(z)
        player:setLastX(flight.x + 0.5)
        player:setLastY(flight.y + 0.5)
        player:setLastZ(z)
        player:setbFalling(false)
        player:setFallTime(0)
    end)
end

local function keyDown(key)
    if not key or not isKeyDown then return false end
    local ok, result = pcall(isKeyDown, key)
    return ok and result == true
end

local function setFlightZoom(flight, enabled)
    U.try("flightZoom", function()
        local core = getCore()
        if enabled then
            flight.oldZoom1x = core:getOptionZoomLevels1x()
            flight.oldZoom2x = core:getOptionZoomLevels2x()
            core:setOptionZoom(true)
            core:setOptionZoomLevels1x(C.FlightZoomLevels1x)
            core:setOptionZoomLevels2x(C.FlightZoomLevels2x)
        else
            if flight.oldZoom1x then core:setOptionZoomLevels1x(flight.oldZoom1x) end
            if flight.oldZoom2x then core:setOptionZoomLevels2x(flight.oldZoom2x) end
        end
        core:zoomLevelsChanged()
    end)
end

local function removeModel(flight)
    if not flight or not flight.modelObject or not flight.modelSquare then return end
    U.try("removeFlightModel", function()
        flight.modelSquare:removeWorldObject(flight.modelObject)
    end)
    flight.modelObject = nil
    flight.modelSquare = nil
end

local function placeModel(flight, rise)
    local tx, ty = math.floor(flight.x), math.floor(flight.y)
    local sq = U.square(tx, ty, flight.groundZ, false)
    if not sq then return false end

    if flight.modelTileX ~= tx or flight.modelTileY ~= ty or not flight.modelObject then
        removeModel(flight)
        U.try("placeFlightModel", function()
            if flight.modelItem then
                sq:AddWorldInventoryItem(flight.modelItem,
                    flight.x - tx, flight.y - ty, 0)
                flight.modelObject = flight.modelItem:getWorldItem()
            else
                flight.modelItem = sq:AddWorldInventoryItem(C.ExteriorItem,
                    flight.x - tx, flight.y - ty, 0)
                if flight.modelItem then
                    flight.modelObject = flight.modelItem:getWorldItem()
                end
            end
        end)
        if not flight.modelObject then
            flight.modelObject = TREK.Core.hullOn(sq)
            if flight.modelObject then flight.modelItem = flight.modelObject:getItem() end
        end
        if not flight.modelObject then return false end
        flight.modelSquare = sq
        flight.modelTileX, flight.modelTileY = tx, ty
        if flight.modelObject.setIgnoreRemoveSandbox then
            flight.modelObject:setIgnoreRemoveSandbox(true)
        end
    end

    U.try("positionFlightModel", function()
        flight.modelObject:setOffset(flight.x - tx, flight.y - ty, 0)
        flight.modelObject:setRenderYOffset(-C.FlightModelLift * rise)
        if flight.modelItem then
            flight.modelItem:setWorldZRotation(flight.heading or 0)
        end
    end)
    return true
end

local function takeLandedModel(s)
    local sq = U.square(s.x, s.y, s.z, false)
    local obj = sq and TREK.Core.hullOn(sq)
    if not obj then return nil end
    local item = obj:getItem()
    sq:removeWorldObject(obj)
    return item
end

function F.isActive()
    return F.active ~= nil
end

--- True only for the transient world object rendering the airborne hull.
function F.isModelObject(obj)
    return F.active ~= nil and F.active.modelObject == obj
end

function F.position()
    local flight = F.active
    if not flight then return nil end
    return { x = math.floor(flight.x), y = math.floor(flight.y), z = flight.groundZ }
end

function F.start(player)
    if not player or F.active then return false, "busy" end
    if TREK.Transport and TREK.Transport.pending then return false, "busy" end
    if TREK.Travel and TREK.Travel.pending then return false, "busy" end

    local s = U.state()
    local x = s.landed and s.x or s.flightX or s.returnX
    local y = s.landed and s.y or s.flightY or s.returnY
    local z = s.landed and s.z or s.flightZ or s.returnZ or 0
    if not x or not y then return false, "nowhere" end

    local modelItem = nil
    if s.landed then
        modelItem = takeLandedModel(s)
        if modelItem then
            s.landed = false
        elseif not TREK.Core.recall() then
            return false, "recall"
        end
    end

    local flight = {
        player = player, x = x, y = y, groundZ = math.floor(z),
        ticks = 0, suspended = false, heading = 0, modelItem = modelItem,
    }
    F.active = flight
    s.inside = false
    s.flightX, s.flightY, s.flightZ = x, y, flight.groundZ
    s.returnX, s.returnY, s.returnZ = math.floor(x), math.floor(y), flight.groundZ

    protect(player, flight, true)
    pin(flight)
    setFlightZoom(flight, true)
    placeModel(flight, 0)

    local overlay = TREKFlightOverlay:new()
    overlay:initialise()
    overlay:addToUIManager()
    F.overlay = overlay

    U.note(player, getText("IGUI_TREK_TakingOff"))
    U.log("FLIGHT BUILD 1.4: takeoff over %.1f,%.1f,%d", x, y, flight.groundZ)
    return true
end

function F.stop(putOnGround)
    local flight = F.active
    if not flight then return nil end
    local player = flight.player
    local spot = F.position()

    if F.overlay then
        F.overlay:removeFromUIManager()
        F.overlay = nil
    end
    removeModel(flight)
    setFlightZoom(flight, false)
    F.active = nil
    if player then
        F.settle(player, flight)
        protect(player, flight, false)
        if putOnGround then U.teleport(player, spot.x, spot.y, spot.z) end
    end

    local s = U.state()
    s.flightX, s.flightY, s.flightZ = spot.x, spot.y, spot.z
    s.returnX, s.returnY, s.returnZ = spot.x, spot.y, spot.z
    return spot
end

function F.land(player)
    local spot = F.position()
    if not spot then return false end
    F.stop(false)
    if TREK.Travel.descend(player, spot) then return true end
    U.teleport(player, spot.x, spot.y, spot.z)
    return false
end

function F.enterInterior(player)
    local spot = F.stop(false)
    if not spot or not player then return false end
    local s = U.state()
    s.inside = true
    s.returnX, s.returnY, s.returnZ = spot.x, spot.y, spot.z
    TREK.Core.beginArrival(player, true)
    U.log("entered the interior from hands-on flight")
    return true
end

function F.beamBelow(player)
    local spot = F.position()
    if not spot or not TREK.Transport then return false, "nowhere" end
    F.active.suspended = true
    local ok, why = TREK.Transport.beamDownFromFlight(player, spot)
    if not ok and F.active then F.active.suspended = false end
    return ok, why
end

function F.resume()
    if F.active then F.active.suspended = false end
end

local function serviceFlight()
    local flight = F.active
    if not flight then return end
    if not flight.player then F.stop(false) return end

    flight.ticks = flight.ticks + 1
    if not flight.suspended then
        local dx, dy = 0, 0
        if keyDown(Keyboard and Keyboard.KEY_A) then dx = dx - 1 end
        if keyDown(Keyboard and Keyboard.KEY_D) then dx = dx + 1 end
        if keyDown(Keyboard and Keyboard.KEY_W) then dy = dy - 1 end
        if keyDown(Keyboard and Keyboard.KEY_S) then dy = dy + 1 end
        if dx ~= 0 or dy ~= 0 then
            if dx == 0 and dy < 0 then flight.heading = 0
            elseif dx > 0 and dy < 0 then flight.heading = 45
            elseif dx > 0 and dy == 0 then flight.heading = 90
            elseif dx > 0 and dy > 0 then flight.heading = 135
            elseif dx == 0 and dy > 0 then flight.heading = 180
            elseif dx < 0 and dy > 0 then flight.heading = 225
            elseif dx < 0 and dy == 0 then flight.heading = 270
            else flight.heading = 315 end

            -- Read every tick, so a speed chosen at the helm applies at once.
            local length = math.sqrt(dx * dx + dy * dy)
            local speed = U.flightSpeed()
            flight.x = flight.x + dx / length * speed
            flight.y = flight.y + dy / length * speed
            local s = U.state()
            s.flightX, s.flightY, s.flightZ = flight.x, flight.y, flight.groundZ
            s.returnX, s.returnY, s.returnZ = math.floor(flight.x),
                math.floor(flight.y), flight.groundZ
        end
    end
    pin(flight)
    if not placeModel(flight, math.min(1, flight.ticks / C.FlightTakeoffTicks)) then
        U.warnOnce("flightModelMissing",
            "airborne hull could not be placed on a streamed square")
    end
end

Events.OnTick.Add(serviceFlight)
U.log("FLIGHT BUILD 1.4 loaded -- hands-on controller registered")

return F
