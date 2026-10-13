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
local C = TREK.Config
local U = TREK.Util

local V = {}
TREK.Vehicle = V

V.SCRIPT = "Base.TrekShuttleCraft"

-- Every kind of ship (C.Hulls), by its id and by its vehicle script.
V.hulls, V.scripts = {}, {}
for _, hull in ipairs(C.Hulls) do
    V.hulls[hull.id] = hull
    V.scripts[hull.script] = hull
end

--- What kind of ship this is: an entry of C.Hulls. A ship from before there
--- were kinds, or of a kind this build has not got, is the first.
function V.hullOf(s)
    return (s and s.hull and V.hulls[s.hull]) or C.Hulls[1]
end

--- How many skins a kind of ship has.
function V.skinCount(hull)
    return #hull.liveries * #C.HullStates
end

--- Which skin a ship is set down in: an index into the vehicle script's skin
--- blocks, a livery's three states together (C.HullLiveries, C.HullStates;
--- tools/gen_shuttle.py). `s` is her state and `id` which ship she is.
---
--- **Nothing new is kept for it.** Her livery is which ship she is: the
--- shared shuttle wears the fleet's, and a personal shuttle the next one
--- round, so two set down on one street can be told apart. Her state is what
--- has happened to her: a ship nobody has commissioned (ENERGY.md, the cold
--- start) has been down and dark, a derelict where she was lost
--- (MAROONED.md) and worn where she was only left; and a ship that was lost
--- stays worn once she is flying again. A vehicle keeps the skin it was
--- made in, so a change shows the next time she is set down.
---
--- **Unless somebody with the say has had her repainted** (`s.paint`: an
--- admin on a server, the player in single player; SERVERS.md), which is
--- hers until they give it back.
function V.skinFor(s, id)
    local liveries, states = #V.hullOf(s).liveries, #C.HullStates
    local paint = s and tonumber(s.paint)
    if paint and paint >= 0 and paint < liveries * states and paint == math.floor(paint) then
        return paint
    end
    local livery = ((tonumber(id) or 1) - 1) % liveries
    local state = 0
    if s and s.commissioned == false then
        state = s.marooned == true and 2 or 1
    elseif s and s.marooned == true then
        state = 1
    end
    return livery * states + math.min(state, states - 1)
end

--- May this player have her repainted? An admin on a server; in single
--- player it is their world.
function V.mayPaint(player)
    if isClient() or isServer() then return TREK.Ship.isAdmin(player) end
    return true
end

-- What each livery and state is called, written out whole: a key put
-- together from parts is one no check can see.
V.LiveryText = {
    fleet = "IGUI_TREK_Livery_fleet", sciences = "IGUI_TREK_Livery_sciences",
    ops = "IGUI_TREK_Livery_ops", medical = "IGUI_TREK_Livery_medical",
    tactical = "IGUI_TREK_Livery_tactical", survey = "IGUI_TREK_Livery_survey",
    house = "IGUI_TREK_Livery_house", blood = "IGUI_TREK_Livery_blood",
    night = "IGUI_TREK_Livery_night", bronze = "IGUI_TREK_Livery_bronze",
    sand = "IGUI_TREK_Livery_sand", slate = "IGUI_TREK_Livery_slate",
}
V.StateText = {
    kept = "IGUI_TREK_Hull_kept", worn = "IGUI_TREK_Hull_worn",
    derelict = "IGUI_TREK_Hull_derelict",
}

--- True for a ship's vehicle, of any kind, the current one or not.
function V.isShuttle(vehicle)
    if not vehicle then return false end
    local script = U.try("vehicleScriptName", function()
        return vehicle:getScriptName()
    end)
    return script ~= nil and V.scripts[script] ~= nil
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

--- Which ship a shuttle vehicle belongs to, by the server's tag: 1 for the
--- shared ship, and for a vehicle from before there were any others. Like
--- the id, a client cannot read it (see V.ship).
function V.fleetOf(vehicle)
    local md = U.try("vehicleModData", function() return vehicle:getModData() end)
    return md and tonumber(md.TREKFleet) or 1
end

--- The loaded shuttle vehicle carrying this id for the ship in hand, or nil.
--- Each ship counts its own vehicles, so the id alone is not enough once
--- there is more than one ship.
function V.find(id)
    if not id then return nil end
    local found = nil
    V.each(function(v)
        if not found and V.idOf(v) == id and V.fleetOf(v) == U.shipNow then found = v end
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
