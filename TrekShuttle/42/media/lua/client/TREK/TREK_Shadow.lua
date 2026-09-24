--[[ Shuttlecraft -- her shadow on the ground.

    A soft dark disc on the ground under the square she would set down on:
    the shadow and the landing marker are the same thing, because the square
    under her centre is exactly the one TREK.Flight.land hands the footprint
    check.

    How it is drawn, and why this way and no other:

      * **vanilla's ground markers** -- getWorldMarkers():addGridSquareMarker,
        the tutorial's own call (client/Tutorial/Steps.lua:55, no debug gate).
        Build 42's renderer draws them level by level
        (FBORenderWorldMarkers.render(level, list), bci 136-147: a marker is
        drawn with the level it stands on), so a marker on the ground shows
        while the pilot is five levels above it. They blend normally
        (glBlendFunc SRC_ALPHA, ONE_MINUS_SRC_ALPHA) with a depth test, so a
        black one darkens the ground and a building in front of it hides it;
      * **not** an iso marker carrying a model, which would have taken any
        shape: IsoMarkers.renderIsoMarkers draws those only when the marker is
        on the viewer's own level (bci 149-163), so the pilot -- the one person
        the shadow is for -- would never see it;
      * **not** the vanilla vehicle shadow, which BaseVehicle.renderShadow
        draws at fastfloor(getZ()): at altitude that is the sky plane, directly
        under the hull, not the ground.

    The renderer accepts one texture for these and it is a ring, clear in the
    middle (FBORenderWorldMarkers.render bci 254-284 maps every name but three
    to nothing, and `circle_center` is the one that fills). So the disc is
    rings nested inside each other, which fills the centre in.

    Nothing here touches the world. Every client draws its own, from the
    vehicle it can see, whenever her body is off the ground -- which includes
    the climb and the descent, when the ship's state does not yet say she is
    flying.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Vehicle"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local V = TREK.Vehicle

local Shadow = {}
TREK.Shadow = Shadow

local rings = nil        -- the markers, one per entry of C.ShadowRings
local at = nil           -- { x, y } the square they stand on
local failed = false     -- the markers could not be made; say so once

--- The square her shadow falls on, or nil when she is on the ground (or
--- nowhere this client can see).
function Shadow.target()
    local vehicle = V.ship()
    if not vehicle then return nil end
    local height = U.try("shadowHeight", function()
        local t = Transform.new()
        vehicle:getWorldTransform(t)
        return t:getOrigin():y()
    end)
    if not height or height / C.LevelUnits < C.ShadowMinLevels then return nil end
    local x = U.try("vx", function() return math.floor(vehicle:getX()) end)
    local y = U.try("vy", function() return math.floor(vehicle:getY()) end)
    if not x then return nil end
    return x, y
end

function Shadow.hide()
    if rings then
        for _, m in ipairs(rings) do
            U.try("shadowRemove", function() m:remove() end)
        end
    end
    rings, at = nil, nil
end

local function make(sq)
    local markers = getWorldMarkers()
    local out = {}
    for i, f in ipairs(C.ShadowRings) do
        -- The texture twice: as the ring, and as the overlay, which is the
        -- one name the renderer maps to nothing rather than to the bright
        -- highlight ring the six-argument form would draw round it.
        local m = markers:addGridSquareMarker(C.ShadowTexture, C.ShadowTexture,
                                              sq, 0, 0, 0, false, C.ShadowSize * f)
        if not m then return nil end
        m:setAlpha(C.ShadowAlpha)
        m:setA(C.ShadowAlpha)
        out[i] = m
    end
    return out
end

function Shadow.update()
    local x, y = Shadow.target()
    if not x then
        Shadow.hide()
        return
    end
    if at and at.x == x and at.y == y then return end
    -- The ground, whatever height she is at: level 0 is where she lands.
    local sq = U.square(x, y, 0, false)
    if not sq then
        Shadow.hide()
        return
    end
    if not rings then
        rings = U.try("shadowMake", make, sq)
        if not rings then
            if not failed then
                failed = true
                U.log("WARN the shuttle's shadow could not be drawn: the " ..
                      "ground markers refused it")
            end
            return
        end
        U.log("shadow: showing under her at %d,%d", x, y)
    else
        for i, m in ipairs(rings) do
            local size = C.ShadowSize * C.ShadowRings[i]
            U.try("shadowMove", function() m:setPosAndSize(x, y, 0, size) end)
        end
    end
    at = { x = x, y = y }
end

--- Where the shadow is standing, for the log and the tests.
function Shadow.at()
    if not at then return nil end
    return at.x, at.y
end

Events.OnTick.Add(function() U.try("shadow", Shadow.update) end)

return Shadow
