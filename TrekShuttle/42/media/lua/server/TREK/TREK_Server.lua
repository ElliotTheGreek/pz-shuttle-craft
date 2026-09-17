--[[ Shuttlecraft -- the ship's authority.

    Runs where the world is authoritative: single player, or the server (a
    dedicated server, or the process a co-op host launches). Never on a client
    connected to a server.

    Every change to the ship arrives here as a command from a client
    (TREK_Net) and is checked before it is applied: who is asking, whether the
    server lets them, whether the numbers make sense, whether the world agrees.
    Then the state is committed (TREK_Ship), which publishes it to every
    client. A client's request is never a fact.

    What lives here:
      * the hull on the map -- placing it, lifting it, and sweeping up old
        hulls that could not be reached when the ship left;
      * the cabin build, triggered when a player aboard has its chunks loaded;
      * water upkeep and the void margin;
      * transporter charges, so a server with the speed anti-cheat on refuses
        a beam in lore instead of kicking the player;
      * course, bookmarks, shields, ownership and crew.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_World"
require "TREK/TREK_Vehicle"
require "TREK/TREK_Build"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Ship = TREK.Ship
local W = TREK.World
local V = TREK.Vehicle
local B = TREK.Build

local S = {}
TREK.Server = S

---------------------------------------------------------------------------
-- Validation helpers
---------------------------------------------------------------------------
local function int(v)
    -- NaN is the one value not equal to itself; infinities fail the range
    -- checks callers make. (Kahlua has no math.huge.)
    if type(v) ~= "number" or v ~= v then
        return nil
    end
    return math.floor(v)
end

--- A world position a client sent, or nil. Build 42 maps are tens of
--- thousands of squares across and have eight levels above ground.
local function position(args)
    local x, y, z = int(args.x), int(args.y), int(args.z or 0)
    if not x or not y or not z then return nil end
    if x < 0 or y < 0 or x > 100000 or y > 100000 or z < 0 or z > 7 then return nil end
    return x, y, z
end

local function alive(player)
    return player ~= nil and U.try("playerDead", function() return player:isDead() end) == false
end

local function deny(player, why, extra)
    local args = extra or {}
    args.why = why
    Net.toClient(player, "denied", args)
end

--- Common gate for anything that changes or moves the ship.
local function mayUse(player)
    if not alive(player) then return false end
    if not Ship.canUse(player) then
        deny(player, "access")
        return false
    end
    return true
end

--- On a server with owner-and-crew access, the first player to use the ship
--- becomes its owner. On a hosted game that is naturally the host.
local function claim(player)
    if not isServer() then return end
    local s = U.state()
    if s.owner then return end
    s.owner = Ship.usernameOf(player)
    U.log("%s now owns the shuttle", s.owner)
    Ship.commit()
end

---------------------------------------------------------------------------
-- The hull
---------------------------------------------------------------------------
--- Takes the hull off its square. Returns `removed, reason`: "unloaded" means
--- the answer is not knowable yet, which is different from "absent".
function S.removeHullAt(x, y, z)
    if not U.chunkLoaded(x, y, z) then return false, "unloaded" end
    local sq = U.square(x, y, z, false)
    if not sq then return false, "unloaded" end
    local obj = W.hullOn(sq)
    if not obj then return false, "absent" end
    local ok = U.try("removeHull", function()
        if isServer() then
            sq:transmitRemoveItemFromSquare(obj)
        else
            sq:removeWorldObject(obj)
        end
        return true
    end) == true
    return ok, ok and "removed" or "failed"
end

-- Old hulls that could not be reached are remembered in the ship state and
-- removed when their chunk next loads. Bounded, because it is saved.
local MAX_GHOSTS = 32

function S.forgetHull(x, y, z)
    local s = U.state()
    for _, g in ipairs(s.ghosts) do
        if g.x == x and g.y == y and g.z == z then return false end
    end
    table.insert(s.ghosts, { x = x, y = y, z = z })
    while #s.ghosts > MAX_GHOSTS do table.remove(s.ghosts, 1) end
    U.log("the old hull at %d,%d,%d is out of reach; it will be cleared when " ..
          "that area loads", x, y, z)
    return true
end

--- Clears any remembered hull whose chunk has since loaded.
function S.sweepGhosts()
    local s = U.state()
    if #s.ghosts == 0 then return 0 end
    local cleared, changed = 0, false
    for i = #s.ghosts, 1, -1 do
        local g = s.ghosts[i]
        if U.chunkLoaded(g.x, g.y, g.z) then
            local removed = S.removeHullAt(g.x, g.y, g.z)
            table.remove(s.ghosts, i)
            changed = true
            if removed then
                cleared = cleared + 1
                U.log("cleared the old hull at %d,%d,%d", g.x, g.y, g.z)
            end
        end
    end
    if changed then Ship.commit() end
    return cleared
end

-- How far around a player to look for hulls nobody wrote down.
local STRAY_RADIUS = 10

--- Removes any hull near a player that is not the one the ship is recorded
--- at. The ghost list only knows about hulls this build left behind.
function S.sweepStrays(player)
    if not player then return 0 end
    local s = U.state()
    local px, py = math.floor(player:getX()), math.floor(player:getY())
    local pz = math.floor(player:getZ())
    if U.isInterior(px, py) then return 0 end

    local removed = 0
    for dx = -STRAY_RADIUS, STRAY_RADIUS do
        for dy = -STRAY_RADIUS, STRAY_RADIUS do
            local x, y = px + dx, py + dy
            local ours = s.landed and x == s.x and y == s.y and pz == s.z
            if not ours then
                local sq = U.square(x, y, pz, false)
                if sq and W.hullOn(sq) and S.removeHullAt(x, y, pz) then
                    removed = removed + 1
                    U.log("removed a stray hull at %d,%d,%d", x, y, pz)
                end
            end
        end
    end
    return removed
end

---------------------------------------------------------------------------
-- The shuttle vehicle
---------------------------------------------------------------------------
--- Readies a freshly spawned shuttle: whole, no key needed, a full tank.
--- Everything here is set on the server before the vehicle's first update
--- reaches any client, and cheatHotwire flags itself for sync.
local function prepareVehicle(vehicle, id)
    U.try("vehicleRepair", function() vehicle:repair() end)
    U.try("vehicleHotwire", function() vehicle:cheatHotwire(true, false) end)
    U.try("vehicleTag", function() vehicle:getModData().TREKShipId = id end)
    S.refuel(vehicle)
end

--- The ship never runs dry: its tank is topped up whenever it falls below
--- half. The same call vanilla's own refuelling command makes.
function S.refuel(vehicle)
    U.try("vehicleRefuel", function()
        local tank = vehicle:getPartById("GasTank")
        if not tank then return end
        local cap = tank:getContainerCapacity()
        if tank:getContainerContentAmount() < cap * 0.5 then
            tank:setContainerContentAmount(cap)
            if isServer() then vehicle:transmitPartModData(tank) end
        end
    end)
end

--- Removes a shuttle vehicle.
---
--- Every client is told first: anyone standing near it has its seats and trunk
--- in their loot window, and a window left holding a container whose vehicle
--- has gone makes vanilla throw every frame -- a black screen, seen in game.
local function removeVehicle(vehicle, why)
    local x, y = math.floor(vehicle:getX()), math.floor(vehicle:getY())
    local id = V.idOf(vehicle)
    Net.toAll("vehicleGone", {})
    local ok = U.try("vehicleRemove", function()
        vehicle:permanentlyRemove()
        return true
    end) == true
    U.log("removing shuttle vehicle %s at %d,%d (%s): %s",
          tostring(id), x, y, why, ok and "done" or "FAILED")
    return ok
end


--- Spawns the shuttle vehicle on a square and makes it the ship.
local function spawnVehicle(sq)
    local s = U.state()
    local vehicle = U.try("addVehicle", function()
        return addVehicleDebug(V.SCRIPT, IsoDirections.N, 0, sq)
    end)
    if not vehicle then
        U.log("WARN could not spawn the shuttle vehicle at %d,%d,%d",
              sq:getX(), sq:getY(), sq:getZ())
        return nil
    end
    s.vehicleSerial = (s.vehicleSerial or 0) + 1
    s.vehicleId = s.vehicleSerial
    prepareVehicle(vehicle, s.vehicleId)
    -- Proof it is tagged: an untagged vehicle looks like a leftover to the
    -- sweep below, which is how the ship could come to delete itself.
    local tagged = V.idOf(vehicle)
    U.log("shuttle vehicle %s spawned at %d,%d,%d",
          tostring(tagged), sq:getX(), sq:getY(), sq:getZ())
    if tagged ~= s.vehicleId then
        U.log("WARN the shuttle vehicle could not be tagged; it will be left alone")
    end
    return vehicle
end

--- Sets the ship down centred on a square, lifting it from wherever it was.
--- Returns `ok, reason, blocked`.
function S.land(x, y, z, player)
    if not U.chunkLoaded(x, y, z) then return false, "unloaded", 0 end
    local sq = U.square(x, y, z, false)
    if not sq then return false, "unloaded", 0 end

    local s = U.state()
    local here = s.landed and s.x == x and s.y == y and s.z == z
    if here and V.find(s.vehicleId) then
        return true, nil, 0
    end

    local ok, why, blocked = W.roomToLand(x, y, z, W.exemptFor(player))
    if not ok then return false, why, blocked end

    -- The old ship goes: its vehicle now if it is loaded, otherwise the leftover
    -- sweep removes it when that ground next loads (its id stops matching).
    -- A hull from before the vehicle is lifted the old way.
    if s.landed then
        local old = V.find(s.vehicleId)
        if old then removeVehicle(old, "the ship landed elsewhere") end
        local _, gone = S.removeHullAt(s.x, s.y, s.z)
        if gone == "unloaded" or gone == "failed" then
            S.forgetHull(s.x, s.y, s.z)
        end
    end

    if not spawnVehicle(sq) then return false, "failed", 0 end

    s.landed = true
    s.everLanded = true
    s.x, s.y, s.z = x, y, z
    s.destination = nil
    s.missingChecks = nil
    Ship.commit()
    U.log("shuttle down at %d,%d,%d (vehicle %d)", x, y, z, s.vehicleId)
    return true, nil, 0
end

--- Sends the ship back up. Refused while anyone is sitting in it: recalling a
--- vehicle out from under its crew would drop them in the road.
function S.recall()
    local s = U.state()
    if not s.landed then return false end
    local vehicle = V.find(s.vehicleId)
    if vehicle and V.occupied(vehicle) then return false, "crewSeated" end
    if vehicle then removeVehicle(vehicle, "recalled") end
    local _, why = S.removeHullAt(s.x, s.y, s.z)
    if why == "unloaded" or why == "failed" then
        S.forgetHull(s.x, s.y, s.z)
    end
    s.landed = false
    s.vehicleId = nil
    Ship.commit()
    U.log("shuttle recalled from %d,%d,%d", s.x, s.y, s.z)
    return true
end

-- Checks in a row that the ship's ground was loaded and its vehicle was not
-- there. A vehicle loads with its chunk, so a few in a row means it is gone
-- (burnt out, removed by an admin) rather than late.
local MISSING_LIMIT = 5

--- Keeps the ship state in step with its vehicle, and tidies up. Runs on a
--- timer on the authority.
---
---  * the ship's position follows its vehicle as it is driven, so the hatch,
---    the shields and the helm all find it where it now is;
---  * the tank is kept topped up;
---  * a shuttle vehicle that is not the ship is removed once nobody is in it;
---  * a save from before the vehicle gets one, in place of its hull;
---  * a ship whose vehicle has gone is treated as overhead, so it can be
---    called down again rather than being lost.
function S.serviceVehicle()
    local s = U.state()
    local found = nil

    -- What makes a vehicle the ship is its tag, not being in view: a leftover
    -- is by definition somewhere the ship is not, so its removal must never
    -- depend on the ship's own vehicle being loaded at the same time.
    local others = {}
    V.each(function(vehicle)
        local id = V.idOf(vehicle)
        if s.landed and id and id == s.vehicleId then
            found = vehicle
        elseif id then
            -- Tagged, and not the ship's tag: a ship the crew left behind when
            -- it landed somewhere its old spot was not loaded.
            table.insert(others, vehicle)
        elseif s.landed and not s.vehicleId then
            -- An untagged shuttle where the ship is: adopt it rather than
            -- delete it (a save from before the tag, or a tagging that failed).
            found = vehicle
            s.vehicleSerial = (s.vehicleSerial or 0) + 1
            s.vehicleId = s.vehicleSerial
            U.try("adoptVehicle", function()
                vehicle:getModData().TREKShipId = s.vehicleId
            end)
            U.log("adopted the shuttle vehicle at %d,%d as the ship",
                  math.floor(vehicle:getX()), math.floor(vehicle:getY()))
            Ship.commit()
        else
            -- Untagged and not adoptable: another mod's, or a tagging that
            -- failed. Never removed -- deleting an unknown vehicle is worse
            -- than leaving one standing.
            U.warnOnce("untaggedShuttle",
                       "a shuttle vehicle with no id is standing at " ..
                       math.floor(vehicle:getX()) .. "," .. math.floor(vehicle:getY()) ..
                       "; leaving it alone")
        end
    end)

    for _, vehicle in ipairs(others) do
        -- Only a vehicle that is certainly not the ship, and only when nobody
        -- is sitting in it. Anyone standing beside it has its containers in
        -- their loot window; the client clears those when this is sent
        -- ("vehicleGone"), which is what stops the black screen.
        if not V.occupied(vehicle) then
            removeVehicle(vehicle, "not the ship")
        end
    end

    if found then
        s.missingChecks = nil
        S.refuel(found)
        local x = math.floor(found:getX())
        local y = math.floor(found:getY())
        local z = math.floor(found:getZ())
        if x ~= s.x or y ~= s.y or z ~= s.z then
            s.x, s.y, s.z = x, y, z
            Ship.commit()
        end
        return
    end

    if not s.landed or not U.chunkLoaded(s.x, s.y, s.z) then return end

    if not s.vehicleId then
        -- A ship landed by a build before the vehicle: swap its hull for one.
        local sq = U.square(s.x, s.y, s.z, false)
        if not sq then return end
        S.removeHullAt(s.x, s.y, s.z)
        if spawnVehicle(sq) then
            U.log("the ship at %d,%d,%d is now a vehicle", s.x, s.y, s.z)
            Ship.commit()
        end
        return
    end

    s.missingChecks = (s.missingChecks or 0) + 1
    if s.missingChecks >= MISSING_LIMIT then
        U.log("the ship's vehicle is gone from %d,%d,%d; it is overhead now",
              s.x, s.y, s.z)
        s.landed = false
        s.vehicleId = nil
        s.missingChecks = nil
        Ship.commit()
    end
end

---------------------------------------------------------------------------
-- Transporter charges
---------------------------------------------------------------------------
-- username -> { n = charges left, at = ms when the next one comes back }
local charges = {}

--- True when beams must be rationed: a server whose speed anti-cheat kicks
--- (2) or bans (1), unless the server owner turned the limit off.
function S.chargesLimited()
    if not isServer() then return false end
    local mode = U.try("sandboxTransporter", function()
        return SandboxVars.TrekShuttle and SandboxVars.TrekShuttle.TransporterLimit
    end)
    if tonumber(mode) == 2 then return false end
    -- An enum option: getInteger answers nil for it, getOption gives "1".."4".
    local speed = U.try("antiCheatSpeed", function()
        return getServerOptions():getOption("AntiCheatSpeed")
    end)
    speed = tonumber(speed)
    return speed == 1 or speed == 2
end

local function chargeOf(name)
    local now = getTimestampMs()
    local c = charges[name]
    if not c then
        c = { n = C.TransporterCharges, at = 0 }
        charges[name] = c
    end
    local period = C.TransporterRechargeSecs * 1000
    while c.n < C.TransporterCharges and c.at > 0 and now >= c.at do
        c.n = c.n + 1
        c.at = (c.n < C.TransporterCharges) and (c.at + period) or 0
    end
    return c, now, period
end

--- Spends `cost` charges, or reports how long until there are enough.
--- `need` may exceed `cost`: taking the ship down needs one to go and one
--- held back for the beam home if there is no room to land.
function S.spendCharge(player, cost, need)
    if not S.chargesLimited() then return true, 0 end
    local c, now, period = chargeOf(Ship.usernameOf(player))
    need = math.max(need or cost, cost)
    if c.n < need then
        local wait = c.at > 0 and (c.at - now) + (need - c.n - 1) * period or period
        return false, math.max(1, math.ceil(wait / 1000))
    end
    c.n = c.n - cost
    if cost > 0 and c.at == 0 then c.at = now + period end
    return true, c.n
end

---------------------------------------------------------------------------
-- Who is aboard
---------------------------------------------------------------------------
-- username -> true, for players who have reported themselves aboard and are
-- waiting for the cabin. Cleared once they have been told it is ready.
local waiting = {}

local function playerNamed(name)
    for _, p in ipairs(U.players()) do
        if Ship.usernameOf(p) == name then return p end
    end
    return nil
end

--- True when any player is standing in the cabin's cell.
local function anyoneAboard()
    for _, p in ipairs(U.players()) do
        if U.isInteriorPlayer(p) then return true end
    end
    return false
end

--- Builds the cabin for players waiting aboard, once its chunks are loaded
--- around them, and tells them when it is ready.
local function serviceWaiting()
    -- The game's Lua (Kahlua) has no `next`; pairs is how to ask "empty?".
    local any = false
    for _ in pairs(waiting) do any = true break end
    if not any then return end
    if not B.cabinLoaded() then return end

    local wasCurrent = B.cabinCurrent()
    local ready = B.ensureCabin()
    if ready and not wasCurrent then Ship.commit() end
    if not ready then return end

    for name in pairs(waiting) do
        local p = playerNamed(name)
        if p then Net.toClient(p, "cabinReady", { rev = C.BuildRev }) end
        waiting[name] = nil
    end
end

---------------------------------------------------------------------------
-- Commands
---------------------------------------------------------------------------
--- A player has arrived aboard (beam, hatch, or already standing there when
--- they loaded in) and needs the cabin.
Net.onServer("boarded", function(player)
    if not alive(player) then return end
    claim(player)
    waiting[Ship.usernameOf(player)] = true
    serviceWaiting()
end)

--- A client asks to move its character a long way: a beam, the hatch, or the
--- trip to a landing site. The client does the moving -- only it can, for an
--- ordinary player -- and the server decides whether it may.
local MOVES = {
    beamUp   = { cost = 1, access = true },
    hatchIn  = { cost = 1, access = true },
    descend  = { cost = 1, need = 2, access = true },
    -- Leaving is never refused for access: nobody is trapped aboard because
    -- the owner took them off the crew.
    beamDown = { cost = 1 },
    hatchOut = { cost = 1 },
    -- The way home from a landing with no room; paid for when it was taken.
    recover  = { cost = 0 },
}

Net.onServer("move", function(player, args)
    local kind = args.kind
    local rule = MOVES[kind]
    if not rule or not alive(player) then return end
    if rule.access and not mayUse(player) then return end
    if kind == "hatchIn" and not U.state().landed then
        deny(player, "notLanded")
        return
    end

    local ok, value = S.spendCharge(player, rule.cost, rule.need)
    if not ok then
        deny(player, "recharging", { secs = value, kind = kind })
        return
    end
    if rule.access then claim(player) end
    Net.toClient(player, "moveGranted", { kind = kind, token = args.token })
end)

--- A client found room to land around itself and asks for the ship there.
--- The server looks again, against its own copy of the world.
Net.onServer("land", function(player, args)
    if not mayUse(player) then return end
    local x, y, z = position(args)
    if not x then return end

    -- The player must be at the site: the ground is only loaded around them.
    local px = U.try("playerX", function() return player:getX() end)
    local py = U.try("playerY", function() return player:getY() end)
    if not px or not py or U.dist2(px, py, x, y) > (C.LandingSearchRadius + 8) ^ 2 then
        Net.toClient(player, "landingRefused", { why = "far", x = x, y = y, z = z })
        return
    end

    local ok, why, blocked = S.land(x, y, z, player)
    if ok then
        claim(player)
        Net.toClient(player, "landed", { x = x, y = y, z = z })
    else
        Net.toClient(player, "landingRefused",
                     { why = why, blocked = blocked, x = x, y = y, z = z })
    end
end)

Net.onServer("recall", function(player)
    if not mayUse(player) then return end
    local ok, why = S.recall()
    if ok then
        Net.toClient(player, "recalled", {})
    elseif why then
        deny(player, why)
    end
end)

Net.onServer("setCourse", function(player, args)
    if not mayUse(player) then return end
    local x, y, z = position(args)
    if not x then return end
    U.state().destination = { x = x, y = y, z = z }
    Ship.commit()
end)

Net.onServer("clearCourse", function(player)
    if not mayUse(player) then return end
    U.state().destination = nil
    Ship.commit()
end)

Net.onServer("addBookmark", function(player, args)
    if not mayUse(player) then return end
    local x, y, z = position(args)
    if not x then return end
    local s = U.state()
    if #s.bookmarks >= C.MaxBookmarks then
        deny(player, "bookmarksFull")
        return
    end
    local name = type(args.name) == "string" and args.name or ""
    -- Printable characters only, and no rich-text markup. Done by byte rather
    -- than with a pattern class, which Kahlua may not support.
    local clean = {}
    for i = 1, #name do
        local b = string.byte(name, i)
        if b >= 32 and b ~= 60 and b ~= 62 and b ~= 127 then
            clean[#clean + 1] = string.sub(name, i, i)
        end
    end
    name = table.concat(clean):sub(1, C.MaxBookmarkName)
    if name == "" then name = string.format("%d, %d", x, y) end
    table.insert(s.bookmarks, { name = name, x = x, y = y, z = z })
    Ship.commit()
end)

Net.onServer("removeBookmark", function(player, args)
    if not mayUse(player) then return end
    local i = int(args.index)
    local s = U.state()
    if not i or not s.bookmarks[i] then return end
    table.remove(s.bookmarks, i)
    Ship.commit()
end)

Net.onServer("setShields", function(player, args)
    if not mayUse(player) then return end
    U.state().shields = args.up == true
    Ship.commit()
end)

Net.onServer("setCrew", function(player, args)
    if not alive(player) then return end
    if not Ship.canManageCrew(player) then
        deny(player, "access")
        return
    end
    local name = type(args.name) == "string" and args.name or nil
    if not name or name == "" or #name > 64 then return end
    local s = U.state()
    claim(player)
    if name == s.owner then return end
    s.crew[name] = (args.on == true) or nil
    Ship.commit()
end)

--- Design and diagnostic tools behind the debug console. Single player, or a
--- server admin.
Net.onServer("debug", function(player, args)
    if isServer() and not Ship.isAdmin(player) then
        deny(player, "access")
        return
    end
    local what = args.what
    if what == "rebuild" then
        B.forceRebuild()
        Ship.commit()
    elseif what == "stock" then
        B.stockReport()
    elseif what == "water" then
        B.waterReport()
    elseif what == "galley" then
        B.giveGalley(player)
    elseif what == "ghosts" then
        local s = U.state()
        U.log("ghosts: %d hull(s) pending removal", #s.ghosts)
        local cleared = S.sweepGhosts()
        local strays = S.sweepStrays(player)
        U.log("ghosts: cleared %d, plus %d stray(s) near %s",
              cleared, strays, Ship.usernameOf(player))
    elseif what == "charges" then
        local c = chargeOf(Ship.usernameOf(player))
        U.log("transporter: limited=%s, %d charge(s) for %s",
              tostring(S.chargesLimited()), c.n, Ship.usernameOf(player))
    end
end)

---------------------------------------------------------------------------
-- Timers
---------------------------------------------------------------------------
-- Every tick while anyone is waiting: they are standing over nothing until the
-- cabin exists, and each tick of delay is a tick they can fall. With nobody
-- waiting the check is one empty table walk.
local vehicleTick = 0
Events.OnTick.Add(function()
    U.try("serviceWaiting", serviceWaiting)
    vehicleTick = vehicleTick + 1
    if vehicleTick >= 60 then
        vehicleTick = 0
        U.try("serviceVehicle", S.serviceVehicle)
    end
end)

Events.EveryOneMinute.Add(function()
    -- The ticker above is the fast path; this is the one every setup is
    -- certain to run, so a build can never be stranded waiting.
    U.try("serviceWaiting", serviceWaiting)
    U.try("sweepGhosts", S.sweepGhosts)
    if B.cabinCurrent() and B.cabinLoaded() then
        -- Nobody can drain the tap faster than a game minute refills it.
        U.try("refillWater", B.refillWater)
        if anyoneAboard() then
            U.try("powerCabin", B.powerCabin)
            U.try("clearMargin", B.clearLoadedSurroundings)
        end
    end
end)

Events.EveryTenMinutes.Add(function()
    for _, p in ipairs(U.players()) do
        U.try("sweepStrays", S.sweepStrays, p)
    end
end)

-- The schema migration runs on the authority as soon as the world's data is
-- there, and is published, so no client ever sees a schema 1 table.
Events.OnInitGlobalModData.Add(function()
    local s = U.state()
    Ship.commit()
    U.log("ship authority ready (%s, v%s, build %d): landed=%s built=%s rev=%s owner=%s, " ..
          "beams limited=%s", isServer() and "server" or "single player", C.Version,
          C.BuildRev, tostring(s.landed), tostring(s.built), tostring(s.rev),
          tostring(s.owner), tostring(S.chargesLimited()))
    S.checkVoidMap()
end)

--- Says, once, whether the void map is loaded. Without it the cabin still
--- works, but the world generator fills the space outside with wilderness and
--- zombies that runtime clearing can only partly remove -- worth a clear line
--- in a server owner's log.
function S.checkVoidMap()
    local dirs = U.try("lotDirectories", function() return getLotDirectories() end)
    if not dirs then return end
    local found = U.try("voidMapListed", function() return dirs:contains(C.VoidMap) end)
    if found then
        U.log("void map '%s' is loaded", C.VoidMap)
    else
        U.log("NOTICE: the '%s' map is not loaded, so the space outside the cabin " ..
              "will show wilderness. Add it before the base map in the server's Map " ..
              "setting, e.g. Map=%s;Muldraugh, KY", C.VoidMap, C.VoidMap)
    end
end

return S
