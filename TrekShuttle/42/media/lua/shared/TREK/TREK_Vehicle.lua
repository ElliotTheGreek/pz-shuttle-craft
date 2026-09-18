--[[ Shuttlecraft -- the shuttle as a vehicle.

    When the ship is on the ground it *is* a vehicle
    (media/scripts/vehicles/trekshuttle_vehicle.txt): four doorless seats,
    driven like a truck, synced by the game's own vehicle code. The server
    spawns it where the ship lands and removes it when the ship is recalled
    (TREK_Server); clients get in, switch seats and drive with the vanilla
    vehicle controls (TREK_VehicleMenu adds the way into the cabin).

    Which vehicle is *the* ship: the server tags it with an id in its mod data
    and records the same id in the ship state. A shuttle vehicle whose id is
    not the current one is a leftover -- the ship landed somewhere else while
    that spot was not loaded -- and the server removes it when it next loads.
    Clients never need the id: there is only ever one shuttle to click on.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local U = TREK.Util

local V = {}
TREK.Vehicle = V

V.SCRIPT = "Base.TrekShuttleCraft"

--- True for a shuttle vehicle, the current one or not.
function V.isShuttle(vehicle)
    if not vehicle then return false end
    return U.try("vehicleScriptName", function()
        return vehicle:getScriptName()
    end) == V.SCRIPT
end

--- The id the server tagged a shuttle vehicle with, or nil.
function V.idOf(vehicle)
    local md = U.try("vehicleModData", function() return vehicle:getModData() end)
    return md and md.TREKShipId or nil
end

--- Calls fn(vehicle) for every shuttle vehicle loaded here.
function V.each(fn)
    local cell = U.cell()
    if not cell then return end
    local set = U.try("cellVehicles", function() return cell:getVehicles() end)
    if not set then return end
    local list = {}
    U.try("vehicleIterate", function()
        local it = set:iterator()
        while it:hasNext() do
            local v = it:next()
            if v then table.insert(list, v) end
        end
    end)
    -- Collected first: fn may remove a vehicle, and the set must not change
    -- under its own iterator.
    for _, v in ipairs(list) do
        if V.isShuttle(v) then fn(v) end
    end
end

--- The loaded shuttle vehicle carrying this id, or nil.
function V.find(id)
    if not id then return nil end
    local found = nil
    V.each(function(v)
        if not found and V.idOf(v) == id then found = v end
    end)
    return found
end

--- The vehicle that *is* the ship, as far as this machine can tell.
---
--- The tag is the authority and the server always has it. A client never does:
--- build 42 syncs a vehicle's *parts'* mod data (VehiclePartModData is a
--- network field) and not the vehicle's own, so getModData() on a client is
--- empty however carefully the server filled it in. Identifying the ship by
--- its tag therefore works perfectly in single player and fails on every
--- client of every server -- which is exactly the class of bug MULTIPLAYER.md
--- exists to catch, and it was caught by the two-player test rather than in
--- the game.
---
--- So: the tag when it can be read, and otherwise the shuttle standing where
--- the ship is recorded. There is only ever one.
function V.ship()
    local s = U.state()
    local tagged = V.find(s.vehicleId)
    if tagged then return tagged end
    if not s.landed and not s.flying then return nil end

    local best, bestDist = nil, nil
    V.each(function(v)
        local x = U.try("shipVehicleX", function() return v:getX() end)
        local y = U.try("shipVehicleY", function() return v:getY() end)
        if not x then return end
        local d = U.dist2(x, y, s.x or 0, s.y or 0)
        if not bestDist or d < bestDist then best, bestDist = v, d end
    end)
    return best
end

--- True when anyone is sitting in the vehicle.
function V.occupied(vehicle)
    local n = U.try("maxPassengers", function() return vehicle:getMaxPassengers() end) or 0
    for seat = 0, n - 1 do
        if U.try("seatCharacter", function() return vehicle:getCharacter(seat) end) then
            return true
        end
    end
    return false
end

return V
