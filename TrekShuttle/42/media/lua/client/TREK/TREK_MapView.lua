--[[ Shuttlecraft -- the ordinary world map, wherever the crew are.

    Three things vanilla's map cannot do for this mod, found in play on
    2026-09-27 ("the map has stopped working"):

    1. **It would not open in the dark.** With the sandbox's *Map needs light*
       on, ISWorldMap.ToggleWorldMap refuses when the player is too dark to
       read (ISWorldMap.lua:1592-1607), and lifts that inside a vehicle only
       for one with a live battery. The shuttle has no battery, so at night
       the map would not open in her cockpit -- the session that reported it
       was flying at three in the morning. Aboard the shuttle, the Adirondack
       or the field station, in the shuttle's seats, or carrying a Starfleet
       screen (a tricorder, a medical tricorder, a PADD), there is always
       light to read by: the map opens the way vanilla opens it, through the
       same timed action, without the darkness check. Anywhere else the
       sandbox's rule stands.
    2. **It opened on the void.** Vanilla centres the map on the character,
       and a character aboard stands in the cabin's cell, off the map: an
       empty picture. Opened aboard, it centres on where the player really is.
    3. **It did not show the ship.** A red dot now marks where the player is
       on the map -- their own position walking or flying, the ship's when
       they are in her cabin, the stockroom when they are in the field
       station, the ground below when they are on the Adirondack -- and an
       orange dot marks the shuttle when she is on the ground.

    Presentation only: nothing here asks the server anything or writes any
    state. It reads the ship state every client already has.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Ship"
require "TREK/TREK_Adirondack"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Ship = TREK.Ship

local MV = {}
TREK.MapView = MV

-- Items whose screen lights a map to read by.
MV.Screens = { C.TricorderType, "TrekMedTricorder", "TrekPADD" }

local function inShuttleSeat(player)
    local v = U.try("mv.vehicle", function() return player:getVehicle() end)
    return v ~= nil and TREK.Vehicle ~= nil and TREK.Vehicle.isShuttle(v) == true
end

local function aboardSomewhere(player)
    if U.isInteriorPlayer(player) then return true end
    return TREK.Adirondack ~= nil and TREK.Adirondack.onShip(player)
end

--- True when this player has light to read the map by, whatever the hour:
--- aboard, in her seats, or with a lit Starfleet screen in their pack.
function MV.hasLight(player)
    if not player then return false end
    if aboardSomewhere(player) or inShuttleSeat(player) then return true end
    local inv = U.try("mv.inv", function() return player:getInventory() end)
    if not inv then return false end
    for _, t in ipairs(MV.Screens) do
        if U.try("mv.screen", function() return inv:containsTypeRecurse(t) end) == true then
            return true
        end
    end
    return false
end

--- Where the player is on the map: x, y, or nil.
---
--- Walking or in her seats that is where they stand. In her cabin it is the
--- ship, on the ground or in the air; with her in orbit it is the ground
--- they beamed up from. In the field station, the stockroom above it; on the
--- Adirondack, the ground they left (Ship.worldOrigin, both).
function MV.playerSpot(player)
    if not player then return nil end
    if U.isInteriorPlayer(player) then
        local s = Ship.get()
        if (s.landed or s.flying) and s.x and s.y and (s.x ~= 0 or s.y ~= 0) then
            return math.floor(s.x), math.floor(s.y)
        end
    end
    -- On the Adirondack the character stands in her cell, off the map: the
    -- ground they left is the place under them.
    local A = TREK.Adirondack
    if A and A.onAdirondack(player) then
        local rx, ry = Ship.returnPoint(player)
        if rx and ry then return math.floor(rx), math.floor(ry) end
        return nil
    end
    return Ship.worldOrigin(player)
end

--- Where the shuttle stands, when she is on the ground: x, y, or nil.
function MV.shipSpot()
    local s = Ship.get()
    if not s.landed or s.flying then return nil end
    if not s.x or not s.y or (s.x == 0 and s.y == 0) then return nil end
    return math.floor(s.x), math.floor(s.y)
end

---------------------------------------------------------------------------
-- Opening it
---------------------------------------------------------------------------
--- The map, opened the way vanilla opens it (ISWorldMap.ToggleWorldMap's own
--- last branch): the queue cleared and the read-the-map action queued --
--- centred where the player is on the map when they are aboard.
function MV.open(player)
    local cx, cy = nil, nil
    if aboardSomewhere(player) then cx, cy = MV.playerSpot(player) end
    U.try("mv.aimIgnore", function() player:setJoypadIgnoreAimUntilCentered(true) end)
    ISTimedActionQueue.clear(player)
    ISTimedActionQueue.add(ISReadWorldMap:new(player, cx, cy, cx and 18.0 or nil))
    return true
end

local baseToggle = ISWorldMap.ToggleWorldMap
if baseToggle then
    function ISWorldMap.ToggleWorldMap(playerNum)
        local player = getSpecificPlayer(playerNum)
        local open = ISWorldMap_instance ~= nil and ISWorldMap_instance:isVisible()
        -- Closing, a map that is not allowed at all, a dead splitscreen
        -- player: all vanilla's, unchanged.
        if open or not player or not ISWorldMap.IsAllowed()
           or (ISPostDeathUI and ISPostDeathUI.instance and #ISPostDeathUI.instance > 0) then
            return baseToggle(playerNum)
        end
        if MV.hasLight(player) then
            if not U.try("mv.open", MV.open, player) then return baseToggle(playerNum) end
            return
        end
        return baseToggle(playerNum)
    end
end

---------------------------------------------------------------------------
-- The dots
---------------------------------------------------------------------------
-- A disc of rects, the way the helm's markers are drawn: the map's UI has no
-- circle, and a square dot reads as a map symbol.
local function disc(map, sx, sy, radius, a, r, g, b)
    for dy = -radius, radius do
        local w = math.floor(math.sqrt(radius * radius - dy * dy) + 0.5)
        map:drawRect(sx - w, sy + dy, w * 2 + 1, 1, a, r, g, b)
    end
end

-- Red for the player, orange for the ship. Outlined in black so either
-- reads on a pale road or a dark wood.
MV.PlayerColour = { 0.95, 0.12, 0.10 }
MV.ShipColour = { 1.00, 0.55, 0.05 }

local function dot(map, wx, wy, colour, label)
    local api = map.mapAPI
    if not api or not wx or not wy then return false end
    local sx = api:worldToUIX(wx + 0.5, wy + 0.5)
    local sy = api:worldToUIY(wx + 0.5, wy + 0.5)
    if not sx or not sy then return false end
    if sx < -10 or sy < -10 or sx > map:getWidth() + 10 or sy > map:getHeight() + 10 then return false end
    sx, sy = math.floor(sx), math.floor(sy)
    disc(map, sx, sy, 7, 0.9, 0, 0, 0)
    disc(map, sx, sy, 5, 1.0, colour[1], colour[2], colour[3])
    if label then
        map:drawTextCentre(label, sx, sy - 24, colour[1], colour[2], colour[3], 1, UIFont.Small)
    end
    return true
end

--- Draws the ship's dot, then the player's on top of it. Returns what was
--- drawn, for the tests.
function MV.drawDots(map)
    local player = map.character or getSpecificPlayer(map.playerNum or 0)
    local drawn = {}
    local sx, sy = MV.shipSpot()
    if sx and dot(map, sx, sy, MV.ShipColour, getText("IGUI_TREK_MapShuttle")) then
        drawn.ship = true
    end
    local px, py = MV.playerSpot(player)
    if px and dot(map, px, py, MV.PlayerColour, nil) then drawn.player = true end
    return drawn
end

local baseRender = ISWorldMap.render
function ISWorldMap:render()
    if baseRender then baseRender(self) end
    U.try("mv.dots", MV.drawDots, self)
end

return MV
