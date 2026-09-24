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
require "TREK/TREK_Medical"
require "TREK/TREK_Replicator"
require "TREK/TREK_Probes"
require "TREK/TREK_EMH"
require "TREK/TREK_Build"
require "TREK/TREK_Energy"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Ship = TREK.Ship
local W = TREK.World
local V = TREK.Vehicle
local B = TREK.Build
local Rep = TREK.Replicator
local Probes = TREK.Probes

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
    -- After repair(), which fills the tank and charges the battery for
    -- nothing (ENERGY.md V4): a dark ship has to come out of it flat.
    S.powerVehicle(vehicle)
end

--- True while the vehicle's own parts should say the ship has power. The
--- emergency landing keeps her engine alive with nothing charged
--- (ENERGY.md 7.1).
local function vehiclePowered()
    return not TREK.Power.dark() or U.state().emergency == true
end

--- Sets the battery's charge, writing only when it changed. The charge lives
--- in the part's item and rides transmitPartUsedDelta, not part mod data
--- (ENERGY.md V3; vanilla's VehicleUtils.chargeBattery).
local function chargeBattery(vehicle, level)
    U.try("vehicleBattery", function()
        local part = vehicle:getPartById("Battery")
        local item = part and part:getInventoryItem()
        if not item then return end
        if math.abs((item:getCurrentUsesFloat() or 0) - level) < 0.01 then return end
        item:setUsedDelta(level)
        if isServer() then vehicle:transmitPartUsedDelta(part) end
    end)
end

--- The ship's power, in the vehicle's own parts (ENERGY.md 4.2). The engine
--- already obeys them, so nothing of ours is in the ignition path:
---
---   * powered: the battery full and the tank topped up whenever it falls
---     below half -- the ship never runs dry;
---   * dark: the battery flat, which vanilla refuses to start on with its own
---     message and sound, and the tank empty, which stalls an engine that is
---     already running. `shutOff` as well, because a flat battery only stops
---     a *start* (V3), and the stall waits for the engine's next check.
function S.powerVehicle(vehicle)
    if not vehicle then return end
    if vehiclePowered() then
        chargeBattery(vehicle, 1.0)
        S.refuel(vehicle)
        return
    end
    chargeBattery(vehicle, 0)
    U.try("vehicleDrain", function()
        local tank = vehicle:getPartById("GasTank")
        if not tank or tank:getContainerContentAmount() <= 0 then return end
        tank:setContainerContentAmount(0)
        if isServer() then vehicle:transmitPartModData(tank) end
    end)
    if U.try("vehicleRunning", function() return vehicle:isEngineRunning() end) == true then
        U.try("vehicleShutOff", function() vehicle:shutOff() end)
        U.log("power: the shuttle's engine is shut down -- the ship is dark")
    end
end

--- Mends crash damage while the shields are up and there is power
--- (ENERGY.md 5.2), charged per condition point, silently.
---
--- On the server, because that is where collision damage is applied: a
--- client's crash only sends vehicle/crash, and part conditions travel
--- server to client with no driver check, so a condition set here reaches the
--- driver and stays (V4). Vanilla's own fixPart is the shape: setCondition,
--- the item's stats, then transmitPartCondition and transmitPartItem, and the
--- vehicle's stats once at the end. **Never vehicle:repair()**: it refills the
--- tank and recharges the battery for nothing.
---
--- The tank and the battery are skipped: those are power, not damage. When
--- the reserve runs out part-way, a part is mended only as far as what was
--- paid for, and the ship is dark. Shields down, or dark, and the damage
--- stays: she is an ordinary damaged vehicle.
---
--- It does not heal the crew. Crash damage hurts the occupants as well, and
--- no part repair undoes that.
---
--- There is no separate dark check, and that is deliberate: a dark ship's
--- partial payment is always nothing, so nothing is mended. A guard that
--- could never change the outcome was deleted when a mutation said so.
function S.shieldRepair(vehicle)
    if not U.shieldsUp() then return 0 end
    local count = U.try("partCount", function() return vehicle:getPartCount() end) or 0
    local mended = 0
    for i = 0, count - 1 do
        local part = U.try("partAt", function() return vehicle:getPartByIndex(i) end)
        local id = part and U.try("partId", function() return part:getId() end)
        if id and id ~= "GasTank" and id ~= "Battery" then
            local cond = U.try("partCond", function() return part:getCondition() end) or 100
            if cond < 100 then
                local cost = (100 - cond) * C.RepairCostPerPoint
                local _, paid = TREK.Energy.energize(nil, "repair", cost,
                    { partial = true, silent = true, noCommit = true })
                paid = paid or 0
                local to = math.min(100, cond + math.floor(paid / C.RepairCostPerPoint + 1e-6))
                if to > cond then
                    U.try("partMend", function()
                        part:setCondition(to)
                        local item = part:getInventoryItem()
                        if item then
                            part:doInventoryItemStats(item, part:getMechanicSkillInstaller())
                        end
                        if isServer() then
                            vehicle:transmitPartCondition(part)
                            if item then vehicle:transmitPartItem(part) end
                        end
                    end)
                    mended = mended + (to - cond)
                end
                if TREK.Power.dark() then break end
            end
        end
    end
    if mended > 0 then
        U.try("partStats", function()
            vehicle:updatePartStats()
            vehicle:updateBulletStats()
        end)
        Ship.commit()
        U.log("shields: %d point(s) of damage mended", mended)
    end
    return mended
end

-- Whether each shuttle's engine was running at the last pass, by ship id.
-- Server-local and transient: a restart finds the engine off, which is what
-- a world load does to it anyway.
local engineWas = {}

--- Charges the engine's start, on its false-to-true edge (ENERGY.md 4.2).
---
--- Watched rather than requested: the engine's state is decided on the
--- server and sent to clients (V3), so this machine sees the start for itself
--- and no client has to report it. Charged to the driver, with the note --
--- starting her is a thing they did. A dark ship never gets this far: the
--- flat battery refused the start.
function S.engineEdge(vehicle)
    local id = V.idOf(vehicle) or 0
    local running = U.try("engineRunning", function()
        return vehicle:isEngineRunning()
    end) == true
    local was = engineWas[id] == true
    engineWas[id] = running
    if running and not was then
        local driver = U.try("engineDriver", function() return vehicle:getDriver() end)
        TREK.Energy.energize(driver, "engine", C.EngineStartCost, { partial = true })
        return true
    end
    return false
end

--- The ship never runs dry while she has power: her tank is topped up
--- whenever it falls below half. The same call vanilla's own refuelling
--- command makes. Only S.powerVehicle's powered branch calls it, which is
--- what keeps a dark ship dry; a guard here as well could never fire.
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

-- Declared here and defined in the Flight section below: landing has to ask
-- whether anybody is aboard before it pulls her out of the sky, and Lua
-- resolves a local by where it was declared rather than by when it is called.
local crewAboard

--- Sets the ship down centred on a square, lifting it from wherever it was.
--- Returns `ok, reason, blocked`.
function S.land(x, y, z, player)
    if not U.chunkLoaded(x, y, z) then return false, "unloaded", 0 end
    local sq = U.square(x, y, z, false)
    if not sq then return false, "unloaded", 0 end

    local s = U.state()

    -- She cannot arrive hovering, and the check is here rather than in the
    -- caller because every way of landing her comes through this function.
    --
    -- Two things reach it with `flying` set. One is a crewman on the ground
    -- calling her down while somebody else is flying her, and that is refused
    -- for the same reason a recall is: pulling her out of the sky from under
    -- her pilot drops them. The other is a stale flight, which is what the
    -- 2026-09-23 report was -- she was spawned on the ground and every client
    -- then paved a plane under her and lifted her straight back up, "called in
    -- hover state so I cannot enter". A ship being set down on a named square
    -- is not flying, whatever the record thinks.
    --
    -- Before the "already here" test, because that returns early.
    if s.flying then
        if crewAboard(V.find(s.vehicleId)) then return false, "inFlight", 0 end
        S.endFlight("she is being set down")
    end

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

---------------------------------------------------------------------------
-- Flight
---------------------------------------------------------------------------
--- Takes the ship out of flight, whatever the reason.
---
--- One function, called from every ending, because the 1.1 flight's worst bug
--- was an ending it did not cover: flight outlived the pilot's death and flew
--- on for the respawned character. Landing, a dead pilot, a crew who all left,
--- a disconnect and a world reload all come through here.
---
--- `toOrbit` is the ending where nobody is aboard any more. She does not come
--- down where she happens to be -- that drops five tonnes of shuttle into
--- whatever is underneath her, which may be a roof, a pond or a horde. She
--- goes back up instead, exactly as `recall` sends her up from the ground, and
--- the crew call her down again when they want her.
function S.endFlight(why, toOrbit)
    local s = U.state()
    if not s.flying then return false end
    s.flying = nil
    s.pilot = nil
    s.level = nil
    s.pilotGrace = nil
    U.log("flight ended: %s", tostring(why))
    Ship.commit()
    -- The clients bring her down and take the plane up; only they can, since
    -- build 42's server runs no vehicle physics at all. Before the vehicle is
    -- removed, so that every client's plane is lifted while it can still see
    -- what it was holding up.
    Net.toAll("flightEnded", { why = why, z = s.z, toOrbit = toOrbit == true })
    if toOrbit then S.toOrbit(why) end
    return true
end

--- Sends her back up from wherever she was hovering: no vehicle left in the
--- sky, no hull dropped on the ground, and `landed = false`, which is the
--- state the whole call-down and recall machinery already understands.
---
--- There is no hull to lift here the way `S.recall` lifts one: a flying ship
--- is always a vehicle, and a hull only ever exists for a save made before
--- there was one.
function S.toOrbit(why)
    local s = U.state()
    if not s.landed then return false end
    local vehicle = V.find(s.vehicleId)
    if vehicle then removeVehicle(vehicle, why or "back up") end
    s.landed = false
    s.vehicleId = nil
    s.missingChecks = nil
    Ship.commit()
    U.log("the shuttle has gone back up from %d,%d (%s)", s.x, s.y, tostring(why))
    return true
end

--- Is anybody still aboard her -- in a seat, or aft in the cabin?
---
--- Not "is the recorded pilot online": a pilot who dies and respawns keeps
--- their username, and a ship that stayed up for a dead pilot is the exact bug
--- that got the 1.1 flight removed.
---
--- And not "is the pilot in the seat", either. The whole point of the plane
--- holding the ship up is that the crew can go aft to the cabin in flight and
--- come back, so anybody standing in the cabin counts -- which is also what
--- makes "go aboard at any phase" safe: stepping through to the cabin is not
--- leaving her.
---
--- It asks about **everybody**, not only the pilot. On a server the pilot may
--- beam down while a crewman is still aft, and pulling the ship out from under
--- them would leave them in a cabin belonging to nothing.
---
--- The seat test is `== true` and that is a fix, not a style. `U.try` hands
--- back whatever the function returned, so `U.try(...) ~= nil` was true for a
--- successful call that answered **false** -- which is to say for a player who
--- is not in a seat at all. Every living player counted as aboard, and the
--- only ending that ever fired was death.
function crewAboard(vehicle)
    for _, p in ipairs(U.players()) do
        if U.try("crewDead", function() return p:isDead() end) == false then
            if U.isInteriorPlayer(p) then return true end
            -- **getSeat answers -1 for somebody not in the vehicle**, never
            -- nil (BaseVehicle.getSeat, bci 27: iconst_m1). `~= nil` counted
            -- every living player near a hovering shuttle as seated in her,
            -- so a crew who beamed down beside her could not call her down
            -- -- "Not while the shuttle is in the air" -- and she never went
            -- back up while anybody stood near. The simulation answered nil,
            -- which is how it passed.
            if vehicle and U.try("crewSeated", function()
                local seat = vehicle:getSeat(p)
                return seat ~= nil and seat >= 0
            end) == true then
                return true
            end
        end
    end
    return false
end

--- Sends the ship back up. Refused while anyone is sitting in it: recalling a
--- vehicle out from under its crew would drop them in the road.
function S.recall()
    local s = U.state()
    if not s.landed then return false end
    local vehicle = V.find(s.vehicleId)

    -- A hovering ship can be sent back up too, as long as she is empty.
    --
    -- This used to be a flat refusal, on the reasoning that recalling her out
    -- from under her crew would leave them standing on nothing -- which is
    -- true, and only true while somebody is aboard. Empty, it is the crew's
    -- own way of dealing with a shuttle hovering somewhere they cannot reach,
    -- and *that state was unreachable by any other means* for one build: the
    -- watchdog below only ran while her chunk was loaded, so a crew who beamed
    -- down and walked away left her flying for ever, the hatch shut against
    -- them and recall refusing. Both halves are fixed; this is the manual one.
    if s.flying then
        if crewAboard(vehicle) then return false, "inFlight" end
        S.endFlight("recalled", true)
        return true
    end

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
    -- `landed` is the ship being *here*; `flying` is it being here and off the
    -- ground. Both mean the vehicle is ours. Testing only `landed` would drop
    -- the ship's own vehicle into the leftover list below, and the leftover
    -- sweep removes anything nobody is sitting in -- so the ship would be
    -- deleted out of the sky the first time the pilot stepped aft.
    local ours = s.landed or s.flying
    local others = {}
    V.each(function(vehicle)
        local id = V.idOf(vehicle)
        if ours and id and id == s.vehicleId then
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

    -- Somebody has to be aboard for her to stay up -- in a seat, or aft in the
    -- cabin. Nobody there for long enough -- they died, they logged out, they
    -- beamed down -- and she goes back up rather than hanging in the sky for
    -- the rest of the world's life.
    --
    -- **This runs whether or not her vehicle is loaded, and that is the whole
    -- point.** It used to live inside the `if found` block below, and `found`
    -- is nil exactly when nobody is standing near her -- which is exactly the
    -- case it exists to catch. A crew who beamed down and walked away left her
    -- flying for ever: the hatch shut against them (`inFlight`), recall
    -- refused (`inFlight`), and a call-down that spawned her on the ground and
    -- was immediately lifted back to hover by every client, because `flying`
    -- was still set. Seen in game, 2026-09-23, and every symptom in that
    -- report is this one line's fault.
    --
    -- `crewAboard(nil)` is correct rather than merely tolerated: a player in a
    -- seat keeps her chunk loaded by being in it, so an unloaded ship has
    -- nobody in a seat by definition, and the cabin test does not need her at
    -- all.
    --
    -- The grace is what makes a beam survivable: a player is briefly in
    -- neither the seat nor the cabin while the transporter has them.
    -- `flightHold` is the longer version of the same thing, set when somebody
    -- is granted a beam *towards* her -- streaming the ground at the far end
    -- can take a good deal longer than the beam itself.
    if s.flying then
        if crewAboard(found) then
            s.pilotGrace, s.flightHold = nil, nil
        elseif (s.flightHold or 0) > 0 then
            s.flightHold = s.flightHold - 1
            s.pilotGrace = nil
        else
            s.pilotGrace = (s.pilotGrace or 0) + 1
            -- **A dark ship cannot go back up** (ENERGY.md 7.2). She comes
            -- down where there is room instead, which S.serviceEmergency does
            -- once her ground is loaded; until somebody is near her she waits.
            if s.pilotGrace >= C.FlightPilotGrace and TREK.Power.dark() then
                if s.emergency ~= true then
                    s.emergency = true
                    Ship.commit()
                end
            elseif s.pilotGrace >= C.FlightPilotGrace then
                -- Going back up is a recall, and costs one (ENERGY.md 3.5).
                -- Partial and silent: nobody asked for it, and a ship too low
                -- to pay still must not hang in the sky for ever. What a
                -- dark ship does instead is ENERGY.md section 7.
                TREK.Energy.energize(nil, "recall", C.RecallCost,
                                     { partial = true, silent = true, noCommit = true })
                S.endFlight("nobody is aboard her", true)
                return
            end
        end
    end

    if found then
        s.missingChecks = nil
        S.powerVehicle(found)
        S.engineEdge(found)
        S.shieldRepair(found)
        if S.serviceEmergency(found) then return end
        local x = math.floor(found:getX())
        local y = math.floor(found:getY())
        local changed = false

        -- **The odometer** (ENERGY.md 4.3): the distance since the last pass,
        -- billed per tile, dearer in the air. It rides the commit this pass
        -- already makes when she has moved, so driving adds no commit of its
        -- own. A jump is not a journey: a respawn, a landing move or a
        -- teleport is ignored rather than billed.
        if s.x and s.y and (x ~= s.x or y ~= s.y) then
            local d = math.sqrt(U.dist2(x, y, s.x, s.y))
            if d <= C.OdometerMaxJump then
                local rate = s.flying and C.AirCostPerTile or C.GroundCostPerTile
                TREK.Energy.energize(nil, s.flying and "fly" or "drive",
                                     d * rate, { partial = true, silent = true,
                                                 noCommit = true })
            end
        end

        -- s.z is the ground the ship stands on, and stays that way even when
        -- the ship is three levels above it. Letting the flying z in here is
        -- the most expensive mistake available: s.z is what Core.exit steps a
        -- player out onto, what W.hullCovers compares against, what the
        -- shields measure from and what S.land's "already here" check reads.
        -- The altitude is s.level, and only the pilot's client sets it.
        --
        -- And `flying` is not the whole of "in the air" any more: she is
        -- carried up for a couple of seconds before the pilot's client reports
        -- her airborne, and carried down for a couple after the server has
        -- recorded her landed. So the ground never moves *up* from here. It
        -- is set where she lands (S.land, touchdown) and only ever corrected
        -- downwards -- a ship on the ground has nowhere higher to be.
        if not s.flying then
            local z = math.floor(found:getZ())
            if z < (s.z or 0) then s.z = z changed = true end
        end
        if x ~= s.x or y ~= s.y then s.x, s.y = x, y changed = true end

        if changed then Ship.commit() end
        return
    end

    if s.flying and s.emergency == true then
        -- Her vehicle is not loaded, so nobody is near her: she waits for them.
        S.serviceEmergency(nil)
    end

    -- A ship in the air is not a ship that has gone missing. The vehicle can
    -- drop out of the cell's list for a moment while the ground under it
    -- streams, and counting that as "the vehicle is gone" would clear the id
    -- and let the next landing spawn a second shuttle -- the "Two shuttles"
    -- signature in DEV_GUIDE.md.
    if s.flying then
        s.missingChecks = nil
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
--
-- `energy` is what the move costs the ship (ENERGY.md 4.1), and `check` is
-- what it must be able to afford without paying it here: take-her-down is
-- checked for the landing and charged once, at the land. The hatch is a door
-- and costs nothing, which is how a dark crew gets out; `recover` is a
-- failure path and never charged.
local MOVES = {
    beamUp   = { cost = 1, access = true, energy = "BeamCost" },
    hatchIn  = { cost = 1, access = true },
    descend  = { cost = 1, need = 2, access = true, check = "LandCost" },
    -- Leaving is never refused for access: nobody is trapped aboard because
    -- the owner took them off the crew.
    beamDown = { cost = 1, energy = "BeamCost" },
    hatchOut = { cost = 1 },
    -- The way home from a landing with no room; paid for when it was taken.
    recover  = { cost = 0 },
}

Net.onServer("move", function(player, args)
    local kind = args.kind
    local rule = MOVES[kind]
    if not rule or not alive(player) then return end
    if rule.access and not mayUse(player) then return end
    local s = U.state()
    -- The ramp only exists when she is on the ground. While she is flying the
    -- hatch is three levels up, and walking into it would be a walk into open
    -- air; the same goes for stepping back out of it.
    if (kind == "hatchIn" or kind == "hatchOut") and (not s.landed or s.flying) then
        deny(player, s.flying and "inFlight" or "notLanded")
        return
    end

    -- **Energy is checked before the transporter charge and paid after it**,
    -- so neither refusal costs the other: a ship too short of power to beam
    -- keeps the player's charge, and a transporter still recharging keeps the
    -- ship's power. `kind` in the denial drops the client's waiting move.
    local energy = rule.energy and C[rule.energy] or 0
    local need = math.max(energy, rule.check and C[rule.check] or 0)
    -- The emergency descent from orbit is free (ENERGY.md 7.3): the ship takes
    -- herself down with the crew, and the only thing she has is no power.
    if kind == "descend" and U.state().emergency ~= nil then need = 0 end
    if need > 0 and not TREK.Power.canPay(need) then
        TREK.Energy.energize(player, kind, need, { kind = kind })
        return
    end

    local ok, value = S.spendCharge(player, rule.cost, rule.need)
    if not ok then
        deny(player, "recharging", { secs = value, kind = kind })
        return
    end
    -- Silent: the transporter's own "energizing" note carries the cost, and a
    -- halo note holds one line, so a second would hide it.
    if energy > 0 then
        TREK.Energy.energize(player, kind, energy, { silent = true })
    end
    if rule.access then claim(player) end

    -- **Where they are leaving from, written down on this machine too.** The
    -- return point is player mod data and the client sets it -- on the
    -- client's own copy of the player. A dedicated server never sees that
    -- write, so `Ship.worldOrigin` asked about a player standing in the cabin
    -- had no answer there: a probe launched aboard was refused for want of a
    -- position fix, and a distress call had nowhere to be measured from.
    -- Single player never showed it, because there the two copies are one
    -- (DEV_GUIDE: *Single player cannot test a fix that both ends apply*).
    -- This handler runs before the move, so the player is still standing
    -- where they are leaving from.
    if kind == "beamUp" or kind == "hatchIn" then
        local px = U.try("moveFromX", function() return player:getX() end)
        local py = U.try("moveFromY", function() return player:getY() end)
        local pz = U.try("moveFromZ", function() return player:getZ() end)
        if px and py and pz and not U.isAboard(px, py, pz) then
            Ship.setReturnPoint(player, px, py, pz)
        end
    end

    -- Somebody is on their way aboard a ship that is hovering with nobody in
    -- her. Hold the watchdog off while they are in transit: a beam is a second
    -- and a half, and the ground at the far end can take a good deal longer
    -- than that to stream in. Without this the crew could watch her leave
    -- while they were still dematerialised.
    if kind == "beamUp" and s.flying then
        s.flightHold = C.FlightBoardingChecks
    end

    Net.toClient(player, "moveGranted", { kind = kind, token = args.token,
                                          cost = energy > 0 and energy or nil })
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

    -- Checked before and charged after (ENERGY.md 4.1): a landing that is
    -- refused costs nothing. A refusal for power goes as a landingRefused
    -- rather than a denial, because a take-her-down has already beamed the
    -- player to the site, and that reply is what beams them home.
    --
    -- An emergency landing (ENERGY.md 7.2, 7.3) is free. A dark ship still in
    -- the air is taken out of flight first -- S.land refuses a hovering ship
    -- with crew aboard, which is exactly this ship -- but only once the site
    -- is known to be clear, so a refusal never drops her where she hangs.
    local s = U.state()
    local emergency = s.emergency ~= nil
    if not emergency and not TREK.Power.canPay(C.LandCost) then
        Net.toClient(player, "landingRefused", {
            why = "noPower", x = x, y = y, z = z,
            need = C.LandCost, have = math.floor(TREK.Power.reserve()),
        })
        return
    end
    if emergency and s.flying then
        local clear, cwhy, cblocked = W.roomToLand(x, y, z, W.exemptFor(player))
        if not clear then
            Net.toClient(player, "landingRefused",
                         { why = cwhy, blocked = cblocked, x = x, y = y, z = z })
            return
        end
        S.endFlight("emergency landing")
    end

    local ok, why, blocked = S.land(x, y, z, player)
    if ok then
        claim(player)
        if emergency then
            U.state().emergency = nil
            Ship.commit()
            U.log("power: the emergency landing is down at %d,%d,%d", x, y, z)
        else
            TREK.Energy.energize(player, "land", C.LandCost)
        end
        Net.toClient(player, "landed", { x = x, y = y, z = z })
    else
        Net.toClient(player, "landingRefused",
                     { why = why, blocked = blocked, x = x, y = y, z = z })
    end
end)

Net.onServer("recall", function(player)
    if not mayUse(player) then return end
    -- A dark ship cannot go up: a landed one stays landed, and says why.
    local s = U.state()
    if s.landed and not TREK.Power.canPay(C.RecallCost) then
        TREK.Energy.energize(player, "recall", C.RecallCost)
        return
    end
    local ok, why = S.recall()
    if ok then
        TREK.Energy.energize(player, "recall", C.RecallCost)
        Net.toClient(player, "recalled", {})
    elseif why then
        deny(player, why)
    end
end)

---------------------------------------------------------------------------
-- Flight commands
---------------------------------------------------------------------------
--- The vehicle the ship is, if this machine can see it, and whether this
--- player is in its driver's seat.
local function drivenBy(player)
    local vehicle = V.ship()
    if not vehicle then return nil end
    local driving = U.try("isDriver", function()
        return vehicle:isDriver(player)
    end) == true
    return vehicle, driving
end

--- A pilot asks to take her up. The server says who may; the client does the
--- lifting, because build 42's server runs no vehicle physics at all.
Net.onServer("takeoff", function(player)
    if not mayUse(player) then return end
    local s = U.state()
    if s.flying then return end
    if not s.landed then
        deny(player, "notLanded")
        return
    end
    local _, driving = drivenBy(player)
    if not driving then
        deny(player, "notPilot")
        return
    end
    -- Checked here and spent at `airborne`, once she is really up, so a
    -- climb that gives up costs nothing (ENERGY.md 4.4).
    if not TREK.Power.canPay(C.TakeoffCost) then
        TREK.Energy.energize(player, "takeoff", C.TakeoffCost)
        return
    end
    claim(player)
    Net.toClient(player, "takeoffGranted", { level = C.flightLevel() })
    U.log("%s has the helm; clearing her for level %d",
          Ship.usernameOf(player), C.flightLevel())
end)

--- The client got her up and the engine held the height. Only now is the ship
--- recorded as flying: a lift that failed must never leave the state saying
--- she is in the air when she is sitting on the grass.
Net.onServer("airborne", function(player, args)
    if not mayUse(player) then return end
    local s = U.state()
    if not s.landed then return end
    local _, driving = drivenBy(player)
    if not driving then return end
    -- One altitude, so this is an equality and not a range. A client reporting
    -- any other height is reporting something the ship cannot be doing.
    local level = int(args.level)
    if level ~= C.flightLevel() then return end
    s.flying = true
    s.level = level
    s.pilot = Ship.usernameOf(player)
    s.pilotGrace = nil
    -- Where the plane is, so that a flight ending in a crash rather than a
    -- landing still gets its invisible floors taken up by whoever next loads
    -- that ground.
    --
    -- Nobody reports back that they have done it, and there is deliberately no
    -- command for that. Each client lays its own plane and so has its own to
    -- lift; a first-one-home flag would have let whichever client finished
    -- first stop all the others mid-sweep. The clients remember for themselves
    -- which spot they have already cleared, and this is simply overwritten by
    -- the next flight.
    s.skyAt = { x = s.x, y = s.y, level = level }
    -- Partial: if the ship went dark between the take-off and now, she is
    -- airborne and dark, which is ENERGY.md section 7's case, not this one's.
    TREK.Energy.energize(player, "takeoff", C.TakeoffCost,
                         { partial = true, noCommit = true })
    Ship.commit()
    U.log("shuttle airborne at %d,%d level %d, flown by %s",
          s.x, s.y, level, s.pilot)
end)

-- There is deliberately no `setAltitude`. Flight is a binary -- she is on the
-- ground or she is hovering at C.FlightLevel -- so there is no altitude to
-- set, and leaving the command in place as a no-op would be a request with a
-- handler that quietly does nothing, which is the shape this project keeps
-- paying for.

--- The ship's flight speed. Anyone who may use her may set it -- the helm is
--- in the cabin and the pilot is in the cockpit, so on a server the crewman
--- setting the speed is usually not the one flying.
Net.onServer("setSpeed", function(player, args)
    if not mayUse(player) then return end
    local step = int(args.step)
    if not step or step < 1 or step > #C.FlightSpeedSteps then return end
    local s = U.state()
    if s.speed == step then return end
    s.speed = step
    Ship.commit()
    U.log("flight speed set to step %d (%s) by %s",
          step, tostring(C.FlightSpeedSteps[step]), Ship.usernameOf(player))
end)

--- Setting her down. Deliberately *not* S.land: that path lifts the old ship
--- and spawns a new one, which would destroy the seats, the trunk and
--- everything the crew had stowed in it, every single landing.
Net.onServer("touchdown", function(player, args)
    if not mayUse(player) then return end
    local s = U.state()
    if not s.flying then return end
    local vehicle, driving = drivenBy(player)
    if not driving then
        deny(player, "notPilot")
        return
    end
    local x, y, z = position(args)
    if not x then return end

    local ok, why, blocked = W.roomToLand(x, y, z, W.exemptFor(player), true)
    if not ok then
        Net.toClient(player, "landingRefused",
                     { why = why, blocked = blocked, x = x, y = y, z = z })
        return
    end

    s.flying = nil
    s.pilot = nil
    s.level = nil
    s.pilotGrace = nil
    s.skyAt = nil
    -- An emergency landing ends here (ENERGY.md 7.4): she is an ordinary dark
    -- ship on the ground, and the next vehicle pass flattens her battery.
    s.emergency = nil
    s.landed = true
    s.everLanded = true
    s.x, s.y, s.z = x, y, z
    s.destination = nil
    Ship.commit()
    Net.toClient(player, "touchdownGranted", { x = x, y = y, z = z })
    U.log("shuttle set down at %d,%d,%d", x, y, z)
end)

--- Photon torpedoes.
---
--- **The blast happens here and nowhere else**, and that is forced by the
--- engine rather than chosen. IsoTrap.shouldProcess decides who an explosion
--- may damage: a client processes only zombies it owns (isLocal) and never a
--- player; the server processes every zombie. If both fired, a zombie owned by
--- a client would be hit twice, once by its owner and once by us. So the
--- server is the only trigger, and vanilla's own IsoMovingObject.Hit carries
--- the damage to everyone -- no packet of ours, and no exception to
--- "one authority per piece of state" of the kind the sky plane needed.
---
--- The trap is vanilla's explosive, configured the way vanilla configures a
--- pipe bomb -- except that it **burns**, which is the point of the weapon and
--- which three earlier commits suppressed. See C.TorpedoFireChance.
---
--- **The blast waits for the torpedo to arrive.** It used to happen in this
--- handler, on the frame the command landed, which put the explosion before
--- the thing that caused it. The shot is queued here with a due time, the
--- launch is broadcast so every client can draw the flight, and `detonate`
--- below runs when it gets there. Nothing about that is ship state: a torpedo
--- lives for under a second and a world that shuts down with one in the air
--- should not reopen and set it off.

--- True when torpedoes are allowed to start fires on this server.
---
--- Sandbox only. A server owner who wants no fire anywhere at all already has
--- ServerOptions.noFire, which IsoGridSquare.Burn() checks by itself before
--- doing anything -- so this is the narrower question of whether *this weapon*
--- burns, not whether fire exists.
---
--- Absent sandbox vars mean the weapon as designed, never a silent disarm:
--- reading a missing option as "no fire" is how a feature turns itself off in
--- the one setup nobody tested.
function S.torpedoesBurn()
    local mode = U.try("sandboxTorpedoFire", function()
        return SandboxVars.TrekShuttle and SandboxVars.TrekShuttle.TorpedoFire
    end)
    return tonumber(mode) ~= C.TorpedoFireNone
end

-- Torpedoes between the tube and the ground. Server-local, transient, never
-- published and never saved.
local inFlight = {}

--- Sets one off. The only place in the mod where anything explodes.
local function detonate(t)
    -- Never build where no player is standing: between launch and arrival the
    -- chunk can go, and an orphan square throws on the first engine call.
    local sq = U.square(t.x, t.y, t.z, false)
    if not sq then
        U.log("WARN torpedo: the ground at %d,%d,%d unloaded in flight -- " ..
              "nothing detonated", t.x, t.y, t.z)
        return
    end

    -- IsoTrap.new copies the entire explosion off the weapon -- sensor range,
    -- fire range, fire energy, fire chance, power, blast radius, noise, extra
    -- damage -- so the weapon is not optional and cannot be nil. Passing nil
    -- threw on the very first property it reads:
    --
    --   NullPointerException: Cannot invoke "HandWeapon.getSensorRange()"
    --   because "weapon" is null
    --
    -- which is what "the torpedo failed to arm" meant in game. The item is a
    -- specification and nothing else: nobody holds one, it is never put in a
    -- container, and it exists for the length of this function.
    local warhead = U.try("torpedo.warhead", function()
        return instanceItem(C.TorpedoItem)
    end)
    if not warhead then
        U.log("WARN torpedo: %s would not instance -- the trap has no warhead "
              .. "to copy its explosion from", tostring(C.TorpedoItem))
        return
    end

    local burns = S.torpedoesBurn()
    -- The engine clamps every one of these to 15 itself (Math.min at the top
    -- of drawCircleExplosion); clamping here too means the log tells the truth
    -- about what actually happened rather than what was asked for.
    local chance = burns and math.min(C.TorpedoFireChance, 100) or 0
    local fireR  = burns and math.min(C.TorpedoFireRange, 15) or 0
    local smokeR = burns and math.min(C.TorpedoSmokeRange, 15) or 0
    local energy = burns and C.TorpedoFireEnergy or 0

    -- The pilot, if they are still connected: it is who the kills belong to.
    -- A torpedo outlives its firer by design -- they can disconnect, die or be
    -- beamed away in the second it is in the air -- so a stale reference is
    -- expected rather than exceptional, and nil is a legal attacker: vanilla's
    -- own 3-argument IsoTrap constructor passes aconst_null for it.
    local who = (t.player and alive(t.player)) and t.player or nil

    local fired = U.try("torpedo.trap", function()
        local trap = IsoTrap.new(who, warhead, sq:getCell(), sq)
        if not trap then return false end
        trap:setExplosionPower(C.TorpedoPower)
        trap:setExplosionRange(math.min(C.TorpedoRange, 15))
        -- These four are the whole visible half of the weapon. At zero the
        -- torpedo kills in silence, which is exactly what it did for three
        -- commits: triggerExplosion() skips the Fire and Smoke passes whose
        -- range is <= 0, and the Explosion pass gates Burn() and StartFire on
        -- getFireStartingChance() per square.
        trap:setFireStartingChance(chance)
        trap:setFireStartingEnergy(energy)
        trap:setFireRange(fireR)
        trap:setSmokeRange(smokeR)
        trap:setInstantExplosion(true)
        trap:triggerExplosion()
        return true
    end) == true

    if not fired then
        U.log("WARN torpedo: the trap would not fire at %d,%d,%d", t.x, t.y, t.z)
        return
    end

    Net.toAll("torpedoDetonated", { x = t.x, y = t.y, z = t.z })

    -- Read the result back, as everything else here does. `caught` is what
    -- proves the blast reached anything; `burning` is what proves the fire
    -- half is working, and it is the number that was silently 0 before.
    local caught = U.try("torpedo.count", function()
        local objs = sq:getMovingObjects()
        return objs and objs:size() or 0
    end) or 0
    local burning = U.try("torpedo.burning", function()
        return sq:haveFire() and 1 or 0
    end) or 0
    U.log("torpedo detonated at %d,%d,%d: power %d, blast %d, fire chance %d " ..
          "over %d, smoke %d -- %d on the target square, fire on it: %s (%s)",
          t.x, t.y, t.z, C.TorpedoPower, math.min(C.TorpedoRange, 15),
          chance, fireR, smokeR, caught,
          burning == 1 and "yes" or "no",
          burns and "sandbox: Full" or "sandbox: Blast only")
end

--- Detonates anything that has arrived. Called every tick; with nothing in
--- the air it is one length check.
function S.serviceTorpedoes()
    if #inFlight == 0 then return end
    local now = getTimestampMs()
    for i = #inFlight, 1, -1 do
        local t = inFlight[i]
        if now >= t.due then
            table.remove(inFlight, i)
            U.try("torpedo.detonate", detonate, t)
        end
    end
end

Net.onServer("fireTorpedo", function(player, args)
    if not mayUse(player) then return end
    local s = U.state()
    if not s.flying then
        deny(player, "notFlying")
        return
    end
    local _, driving = drivenBy(player)
    if not driving then
        deny(player, "notPilot")
        return
    end

    local now = getTimestampMs()
    if s.torpedoAt and now - s.torpedoAt < C.TorpedoCooldownMs then
        deny(player, "torpedoReloading",
             { ms = C.TorpedoCooldownMs - (now - s.torpedoAt) })
        return
    end

    local x, y = int(args.x), int(args.y)
    if not x or not y then return end
    -- The ground under her, not her altitude: a torpedo falls.
    local z = int(args.z) or s.z or 0
    if z < 0 then return end

    -- A client is a request, never a fact. Without this bound the command is
    -- a mortar that reaches anywhere on the map.
    local dx, dy = x - s.x, y - s.y
    local dist = math.sqrt(dx * dx + dy * dy)
    if dist > C.TorpedoMaxRange then
        deny(player, "torpedoRange")
        return
    end
    -- And the blast is centred on the ground, so firing at your own shadow
    -- would catch the ship.
    if dist < C.TorpedoMinRange then
        deny(player, "torpedoTooClose")
        return
    end

    -- Never build where no player is standing: an unloaded chunk hands back an
    -- orphan square and the first engine call on it throws.
    local sq = U.square(x, y, z, false)
    if not sq then
        deny(player, "torpedoNoGround")
        U.log("torpedo: no loaded square at %d,%d,%d -- not fired", x, y, z)
        return
    end

    -- The warhead is instanced at detonation, not here: it is a specification
    -- the trap copies, it is worth nothing in between, and instancing it a
    -- second early only widens the window in which it could go missing.

    -- How long she takes to get there. Bounded at both ends: the floor stops a
    -- close shot being a single frame nobody sees, and the ceiling means a
    -- mistaken speed cannot leave a detonation owed for ever.
    local flight = (dist / C.TorpedoSpeed) * 1000
    if flight < C.TorpedoMinFlightMs then flight = C.TorpedoMinFlightMs end
    if flight > C.TorpedoMaxFlightMs then flight = C.TorpedoMaxFlightMs end

    table.insert(inFlight, {
        x = x, y = y, z = z,
        due = now + flight,
        player = player,
    })

    -- The cooldown starts at launch, not at impact. Otherwise the flight time
    -- would be free reload time, and a close shot would rearm sooner than a
    -- far one -- backwards, and exploitable.
    s.torpedoAt = now
    Ship.commit()

    -- Every client draws the flight for itself from this: the ship's position
    -- and level at launch, the target, and how long it has to cross. Scenery,
    -- the same documented exception the sky plane uses -- no client touches
    -- ship state and no client does damage.
    Net.toAll("torpedoLaunched", {
        x0 = s.x, y0 = s.y, level = s.level or C.flightLevel(),
        x = x, y = y, z = z,
        ms = flight,
    })
    U.log("torpedo away: %d,%d -> %d,%d,%d, %d tiles, %d ms in the air, fired by %s",
          math.floor(s.x or 0), math.floor(s.y or 0), x, y, z,
          math.floor(dist), math.floor(flight), Ship.usernameOf(player))
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

-- username -> ms of the last shield report taken from them.
local shieldReports = {}

--- What a client's shields pushed (ENERGY.md 5.1), charged silently.
---
--- **The count is the client's word**, and there is no checking it: the
--- server does not simulate the zombies a client owns, so a push it did not
--- see is a push it cannot count. What it can check is everything around the
--- number -- one report per player per window, at most C.ShieldReportMax in
--- it, shields up, the ship landed and lit, and the reporter standing within
--- reach of the field on the server's own copy of them. A modified client can
--- still under-report and get cheaper shields; it cannot drain a shared ship.
---
--- Not gated on the crew list: a stranger standing by her is shielded by
--- her, and it is her power that did it.
Net.onServer("shieldDraw", function(player, args)
    if not alive(player) then return end
    local n = int(args.n)
    if not n or n < 1 then return end
    if n > C.ShieldReportMax then n = C.ShieldReportMax end
    local s = U.state()
    if not s.landed or s.flying or s.shields == false or TREK.Power.dark() then return end

    local name = Ship.usernameOf(player)
    local now = getTimestampMs()
    local last = shieldReports[name]
    -- A little slack under the window: the client's clock and this one are
    -- not the same clock.
    if last and now - last < C.ShieldReportSecs * 1000 * 0.8 then return end

    local px = U.try("shieldX", function() return player:getX() end)
    local py = U.try("shieldY", function() return player:getY() end)
    if not px or not py then return end
    local reach = C.FieldRadius + 30
    if U.dist2(px, py, s.x, s.y) > reach * reach then return end

    shieldReports[name] = now
    TREK.Energy.energize(nil, "shields", n * C.ShieldPushCost,
                         { partial = true, silent = true })
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

---------------------------------------------------------------------------
-- The tricorder's lock override
---------------------------------------------------------------------------
-- A lock is world state, so the server opens it and tells everyone. The
-- client looked first, but only so it could offer the option: it is asked
-- again here, from scratch, because a client is a request and never a fact.
--
-- **This is deliberately not gated on the ship's access rules.** The
-- tricorder is an item somebody is carrying, not the shuttle, and a crew
-- list is about who may fly her. What it *is* gated on is carrying the
-- tricorder at all, a range the server measures itself, and a cooldown --
-- without the range bound a crafted command is a master key for the map.
--
-- What it will not open is in TREK_Medical.lockOn: a padlock, or anything
-- inside a safehouse this player is not a member of. Both are another
-- player's property, and a mod that picks them is a griefing tool on every
-- server that installs it.
local unlockCooling = {}   -- username -> millisecond stamp of the last override

local function unlockDenied(player, why)
    Net.toClient(player, "unlocked", { ok = false, why = why })
end

Net.onServer("unlock", function(player, args)
    if not alive(player) then return end

    local x, y, z = position(args)
    if not x then return end

    local name = Ship.usernameOf(player)
    local now = getTimestampMs()
    local last = unlockCooling[name]
    if last and now - last < C.UnlockCooldownMs then
        unlockDenied(player, "cooling")
        return
    end

    if not TREK.Medical.carries(player, C.TricorderType, C.TricorderItem) then
        unlockDenied(player, "notool")
        return
    end

    -- Measured on the server's own copy of where the player is, not on
    -- anything the command carried.
    local px = U.try("unlock.px", function() return player:getX() end)
    local py = U.try("unlock.py", function() return player:getY() end)
    local pz = U.try("unlock.pz", function() return math.floor(player:getZ()) end)
    if not px or not py or pz ~= z
       or U.dist2(px, py, x + 0.5, y + 0.5) > C.UnlockRange * C.UnlockRange then
        unlockDenied(player, "far")
        return
    end

    -- An unloaded chunk is "cannot tell yet", not "nothing there".
    local sq = U.square(x, y, z, false)
    if not sq then
        unlockDenied(player, "unloaded")
        return
    end

    local obj, why = TREK.Medical.lockOn(sq, name)
    if not obj then
        unlockDenied(player, why or "nolock")
        return
    end

    -- The cooldown is spent on the attempt that reached a real lock, not on
    -- the ones that were refused: a player who clicked a padlock should not
    -- be locked out of the tool for twenty seconds for it.
    unlockCooling[name] = now

    local opened = TREK.Medical.unlock(obj)
    Net.toClient(player, "unlocked", { ok = opened, why = opened and nil or "stuck" })
    U.log("tricorder: %s override at %d,%d,%d -> %s",
          name, x, y, z, opened and "open" or "refused")
end)

---------------------------------------------------------------------------
-- The replicator
---------------------------------------------------------------------------
-- **The item is created here and nowhere else.** This is the one feature in
-- the mod that can hand a player anything in the game, so every part of the
-- request is checked against the server's own copy of the world: who is
-- asking, whether they are standing at the machine, whether the id is a real
-- catalogue entry, whether the ship holds a pattern for it, whether the
-- reserve covers it -- and then the tray is counted before and after, because
-- a replicator that reports success and produced nothing is this project's
-- favourite bug.
--
-- Two things a client sends that are never trusted: the id (looked up in the
-- real catalogue, never instanceItem'd blind) and the quantity (matched
-- against the list the panel offers, so a crafted command cannot ask for a
-- thousand).

--- Everything the player is carrying, anywhere: pockets, bags and hands, as
--- a map of full type to count.
---
--- `getAllEvalRecurse(function() return true end)` is vanilla's own way of
--- asking for the lot -- ISInventoryPaneContextMenu.lua:1355 uses that exact
--- predicate -- and it walks sub-containers, which matters because a player
--- keeps everything in a bag. The hands are added separately: an equipped
--- item is not always in the container listing.
local function carriedTypes(player)
    local out = {}
    if not player then return out end

    local inv = U.try("rep.inventory", function() return player:getInventory() end)
    if not inv then return out end

    local list = U.try("rep.allItems", function()
        return inv:getAllEvalRecurse(function() return true end)
    end)
    if not list then
        -- The top level alone is worse than nothing at all only if it is
        -- silent, so it is the fallback and it is logged by U.try above.
        list = U.try("rep.items", function() return inv:getItems() end)
    end
    if list then
        local join = U.batch("rep.carried")
        local n = join(function() return list:size() end) or 0
        for i = 0, n - 1 do
            join(function()
                local item = list:get(i)
                local t = item and item:getFullType()
                if t then out[t] = (out[t] or 0) + 1 end
            end)
        end
    end

    local function hand(fn)
        local t = U.try("rep.hand", function()
            local item = fn(player)
            return item and item:getFullType() or nil
        end)
        if t then out[t] = (out[t] or 0) + 1 end
    end
    hand(function(p) return p:getPrimaryHandItem() end)
    hand(function(p) return p:getSecondaryHandItem() end)
    return out
end

--- Materialises `count` of one item into the asking player's hands, and says
--- how many actually arrived.
---
--- **Into their inventory, because the machine has no tray.** It used to
--- materialise into a steel counter on the same square, and that counter was
--- doing the work the replicator should have been doing; there is no counter
--- now, and a machine that makes a thing and drops it on the deck would be a
--- worse answer than either.
---
--- The count is still the whole point. `instanceItem` answers nil for an
--- obsolete item that slipped the catalogue filter, and from here that looks
--- exactly like success -- so the inventory is measured after every single
--- one and the player is charged for what arrived.
---
--- `B.giveGalley` is the same shape and the precedent for the send: add to
--- the container, then `sendAddItemToContainer` so the client's copy has it
--- too. U.batch rather than U.try because this repeats.
local function materialise(player, id, count)
    local inv = U.try("rep.inv", function() return player:getInventory() end)
    if not inv then return 0 end

    local function held()
        local items = U.try("rep.invItems", function() return inv:getItems() end)
        return items and items:size() or 0
    end

    local join = U.batch("rep.materialise")
    local made = 0
    for _ = 1, count do
        local before = held()
        local ok = join(function()
            local item = instanceItem(id)
            if not item then return false end
            inv:AddItem(item)
            if isServer() then sendAddItemToContainer(inv, item) end
            return true
        end)
        if ok ~= true or held() <= before then break end
        made = made + 1
    end
    return made
end

--- Alive, allowed to use the ship, the machine is not switched off, and the
--- player is really standing at it -- measured here, not taken from the
--- command.
local function atReplicator(player)
    if not mayUse(player) then return false end
    if Rep.isOff() then
        deny(player, "repOff")
        return false
    end
    -- Scanning costs nothing, but the machine that scans is dark too.
    if TREK.Power.dark() then
        deny(player, "repOffline")
        return false
    end
    if not Rep.inReachOf(player) then
        deny(player, "repFar")
        return false
    end
    return true
end

Net.onServer("replicate", function(player, args)
    if not atReplicator(player) then return end

    local row = Rep.row(args.id)
    if not row then
        deny(player, "repUnknown")
        return
    end
    local count = int(args.count)
    if not count or not Rep.isQuantity(count) then
        deny(player, "repUnknown")
        return
    end
    if not Rep.knows(row.id) then
        deny(player, "repNoPattern")
        return
    end

    local s = U.state()
    local now = getTimestampMs()
    if s.repAt and now - s.repAt < C.ReplicatorCooldownMs then
        deny(player, "repCycling", { ms = C.ReplicatorCooldownMs - (now - s.repAt) })
        return
    end

    -- **The ship burns a crystal here if it has to.** The reserve is one
    -- crystal's charge, so running out mid-shift is normal: Power.afford
    -- swaps a spare in from the chamber and answers again.
    --
    -- One refusal rather than two, and that is a correction: there was a
    -- separate "not enough power" for a low reserve with spares still in the
    -- chamber, and it could never fire. A fresh crystal is five thousand
    -- units and the dearest thing in the game is fifteen hundred, so if a
    -- spare exists the swap always covers the cost. The only real failure is
    -- having none.
    --
    -- Checked before and paid after, because what is charged is what really
    -- landed in the player's hands. Silent: the `replicated` note below says
    -- what it cost, and a halo note holds one line, so a second would hide it.
    local cost = Rep.cost(row, count)
    if not TREK.Power.canPay(cost) then
        deny(player, "repNoCrystal",
             { need = cost, have = math.floor(TREK.Power.reserve()) })
        return
    end

    local made = materialise(player, row.id, count)
    local spent = Rep.cost(row, made)
    s.repAt = now
    TREK.Energy.energize(player, "replicate", spent,
                         { silent = true, noCommit = true })
    Ship.commit()

    Net.toClient(player, "replicated", {
        id = row.id, name = row.name, asked = count, made = made,
        cost = spent, energy = math.floor(TREK.Power.reserve()),
        crystals = TREK.Power.crystals(),
    })
    U.log("replicator: %s asked for %d x %s, made %d for %d unit(s); %d left",
          Ship.usernameOf(player), count, row.id, made, spent,
          math.floor(TREK.Power.reserve()))
end)

---------------------------------------------------------------------------
-- The warp core
---------------------------------------------------------------------------
--- One crystal the player is really carrying, or nil.
---
--- The engine's recursive search compares the **bare** type, which is not
--- namespaced, so the results are filtered on the full id: another mod's
--- TrekDilithium is not the ship's fuel. The phaser and the medical set do
--- the same, and the chamber count used to as well.
--- Returns one crystal and how many they are carrying.
local function carriedCrystals(player)
    local inv = U.try("core.inv", function() return player:getInventory() end)
    if not inv then return nil, 0 end
    local list = U.try("core.carried", function()
        return inv:getAllTypeRecurse(C.DilithiumType)
    end)
    if not list then return nil, 0 end

    local join = U.batch("core.findCrystal")
    local size = join(function() return list:size() end) or 0
    local first, n = nil, 0
    for i = 0, size - 1 do
        local item = join(function() return list:get(i) end)
        local t = item and U.try("core.type", function() return item:getFullType() end)
        if t == C.DilithiumItem then
            n = n + 1
            if not first then first = item end
        end
    end
    return first, n
end

--- The two things a player may do at the core, and the checks they share.
local function atCore(player)
    if not mayUse(player) then return false end
    if not TREK.Power.inReachOf(player) then
        deny(player, "coreFar")
        return false
    end
    return true
end

--- Loading one in. The client asks; the server looks in its own copy of the
--- player's inventory, takes the crystal out of it and puts it in the ship.
Net.onServer("loadCrystal", function(player)
    if not atCore(player) then return end

    local crystal, before = carriedCrystals(player)
    if not crystal then
        deny(player, "coreNoCrystal")
        return
    end

    -- Out of the player's hands first, and **counted** rather than compared:
    -- a Remove that did nothing would turn one crystal into an unlimited
    -- supply, and two Java objects are not a thing to test with `==` from
    -- here. This is the same read-back the old chamber had.
    local inv = U.try("core.inv", function() return player:getInventory() end)
    U.try("core.remove", function() inv:Remove(crystal) end)
    local _, after = carriedCrystals(player)
    if after >= before then
        U.log("WARN core: %s's crystal would not come out of their inventory",
              Ship.usernameOf(player))
        deny(player, "coreNoCrystal")
        return
    end
    if isServer() then
        U.try("core.syncInv", function() sendRemoveItemFromContainer(inv, crystal) end)
    end

    TREK.Power.addCrystals(1)
    -- **A dark ship burns it at once** (ENERGY.md 3.3). A spare is normally
    -- burned lazily, by the next charge that needs it -- but a dark ship has
    -- to come back on the moment the crystal goes in, because that is the
    -- payoff the cold start is built around.
    --
    -- Keyed on the core being empty rather than on `s.dark`: an empty core
    -- with this crystal as its only spare *is* the dark ship, and one with
    -- other spares loses nothing by burning now (less than a unit, V1).
    if TREK.Power.reserve() < 1 then
        TREK.Power.burnCrystal()
    end
    Ship.commit()
    TREK.Energy.powerChanged()
    Net.toClient(player, "crystalLoaded",
                 { crystals = TREK.Power.crystals() })
    U.log("core: %s loaded a crystal; %d spare(s) aboard",
          Ship.usernameOf(player), TREK.Power.crystals())
end)

--- Taking one back out, for a crew splitting their stores before a trip.
Net.onServer("takeCrystal", function(player)
    if not atCore(player) then return end

    if TREK.Power.crystals() <= 0 then
        deny(player, "coreEmpty")
        return
    end

    -- Made into the player's hands and **counted**, exactly as a replication
    -- is: a container at capacity drops what it is handed in silence, and the
    -- ship must not lose a crystal to that.
    local made = materialise(player, C.DilithiumItem, 1)
    if made < 1 then
        deny(player, "coreFull")
        return
    end
    TREK.Power.takeCrystal()
    Ship.commit()
    Net.toClient(player, "crystalTaken",
                 { crystals = TREK.Power.crystals() })
    U.log("core: %s took a crystal; %d spare(s) aboard",
          Ship.usernameOf(player), TREK.Power.crystals())
end)

--- Storing one pattern, from the item's own right-click menu.
---
--- Scanning does not consume the item -- the ship reads it and gives it back
--- -- so the only thing to check is that the player really has one, and that
--- is checked in the player's inventory **on the server's own copy of it**.
Net.onServer("storePattern", function(player, args)
    if not atReplicator(player) then return end

    local row = Rep.row(args.id)
    if not row then
        deny(player, "repUnknown")
        return
    end
    if Rep.store().known[row.id] then
        Net.toClient(player, "patternStored",
                     { id = row.id, name = row.name, learned = 0, already = true })
        return
    end
    if not carriedTypes(player)[row.id] then
        deny(player, "repNoItem")
        return
    end

    Rep.learn(row.id)
    Rep.publish()
    Net.toClient(player, "patternStored",
                 { id = row.id, name = row.name, learned = 1 })
    U.log("replicator: %s stored a pattern for %s (%d in all)",
          Ship.usernameOf(player), row.id, Rep.patternCount())
end)

--- Everything the player is carrying, in one pass, from the panel's button.
--- The same rule, applied to a bagful: read, keep, hand it all back.
Net.onServer("scanCarried", function(player)
    if not atReplicator(player) then return end

    local learned, seen = 0, 0
    for id in pairs(carriedTypes(player)) do
        seen = seen + 1
        if Rep.row(id) and Rep.learn(id) then learned = learned + 1 end
    end
    if learned > 0 then Rep.publish() end

    Net.toClient(player, "patternStored", { learned = learned, seen = seen })
    U.log("replicator: %s scanned %d carried item(s), %d new pattern(s), %d in all",
          Ship.usernameOf(player), seen, learned, Rep.patternCount())
end)

---------------------------------------------------------------------------
-- The Emergency Medical Hologram
---------------------------------------------------------------------------
-- **Every body in this feature is written here and nowhere else**, and that
-- is forced by the engine rather than chosen for tidiness.
-- `BodyDamage.Update()` decides who simulates a body at bci 21-62: not a
-- client, run the whole simulation; a client with its own body, return; a
-- client with somebody *else's* body, `RestoreToFullHealth()` it. So in
-- multiplayer a remote player's body on a client is wiped clean every single
-- tick. The server is not a better place to treat somebody from; it is the
-- only machine that knows they are hurt.
--
-- Three consequences the rest of this section is shaped by:
--
--   * the panel cannot read another patient by itself, so `emhLook` exists
--     and answers with what the server can see;
--   * the parts are pushed back with `syncBodyPart`, which is a no-op off
--     the server -- Med.publish;
--   * the BodyDamage flags and the infection moodle do **not** ride that
--     packet (it carries BodyPart fields only), so a cured patient's own
--     client is told to clear its own.
--
-- And nobody is ever treated without being asked. Treating yourself needs no
-- consent; treating anybody else mints a token, raises a yes/no on *their*
-- screen, and re-validates everything from scratch when the answer comes
-- back -- because between the offer and the answer the asker can walk away,
-- the core can be emptied and the patient can leave the ship. That is the
-- padlock-and-safehouse rule from MULTIPLAYER.md applied to bodies: nobody
-- can force-heal, or force-anything, another player.

local EMH = TREK.EMH
local Med = TREK.Medical

-- token -> { from, who, what, cost, at }. Server-local, transient, never
-- published and never saved: an offer that outlived a restart would be a
-- promise the ship had forgotten making.
local offers = {}
local offerSerial = 0

-- name -> world hour a patient under a cure was first seen off the ship.
-- Server-local and transient on purpose: it is a grace period measured in
-- game minutes, and a restart in the middle of one simply starts it again.
local offShip = {}

--- The common gate. Alive, allowed, the sandbox is on, standing at the
--- station -- all measured here, on the server's own copy of the world.
local function atEMH(player)
    if not alive(player) then return false end
    local why = EMH.refusal(player)
    if why then
        deny(player, why)
        return false
    end
    return true
end

--- The patient a command names, resolved **from the server's own view**.
---
--- A client may say who it wants treated and the server looks that name up
--- among the people it can see standing in the cabin. A client is a request,
--- never a fact, including about who the patient is: without this, a crafted
--- command is a way to reach into anybody's body from anywhere on the map.
local function patientFor(player, args)
    local name = args and args.who
    if name == nil or name == "" then return player, Ship.usernameOf(player) end
    local patient = EMH.patientNamed(name)
    if not patient then
        deny(player, "emhNoPatient")
        return nil, nil
    end
    return patient, Ship.usernameOf(patient)
end

--- Spends the treatment's power. Returns true when the ship could pay.
--- Silent when it pays: `emhTreated` is the note, and it says what he did.
local function spendTreatment(player)
    if TREK.Power.canPay(EMH.treatCost()) then
        return TREK.Energy.energize(player, "emhTreat", EMH.treatCost(),
                                    { silent = true })
    end
    return TREK.Energy.energize(player, "emhTreat", EMH.treatCost(),
                                { why = "emhNoPower" })
end

--- Treats a body. **Supplies are infinite; power is not.**
---
--- The hypospray's list, then the regenerator's **unskipped**, and the glass
--- and the bullets come out. `Med.obstructed` is deliberately not applied:
--- the regenerator refuses to close skin over a shard, and the Doctor takes
--- the shard out first -- which is the whole reason he is better than the
--- instrument in your pocket.
---
--- **It leaves a bite and the infection exactly where it found them.** The
--- hypospray's six-dose limit, the regenerator's scope and the reason the
--- EMH exists all rest on the bite being the one thing you come home for.
--- Nothing here touches Med.CURE.
local function treatBody(patient)
    local counts = { total = 0 }
    local function merge(part)
        for key, n in pairs(part) do
            if type(n) == "number" and key ~= "total" and key ~= "skipped" then
                counts[key] = (counts[key] or 0) + n
            end
        end
        counts.total = counts.total + (part.total or 0)
    end
    -- **The order is the design.** The skin pass runs while the glass is
    -- still in the wound, and it runs *unskipped* -- that is the whole
    -- difference between the Doctor and the regenerator in your pocket,
    -- which refuses to close skin over a shard. Take the foreign bodies out
    -- first and applying Med.obstructed here would change nothing at all,
    -- which would make the one thing worth asserting about this pass
    -- unassertable.
    merge(Med.treatWith(patient, Med.TREATMENTS))
    merge(Med.treatWith(patient, Med.SKIN))
    merge(Med.removeForeign(patient))
    Med.publish(patient)
    return counts
end

--- Cures the zombie infection. Authority only, and only from the register.
---
--- **Both levels in one pass.** Med.cure does the parts -- including the
--- bite, through the two-argument SetBitten that does not re-infect the limb
--- -- and this does the body. `BodyDamage.isInfected` is a one-way latch
--- re-derived from the parts each tick and skipped once true, so clearing it
--- alone is undone next tick and clearing the parts alone never clears it.
---
--- `-1`, not `0`, for the two times: `Update()` treats a negative value as
--- "the countdown has not started" and initialises it from any other, so a
--- cure written as zero leaves a running clock and the player dies anyway.
local function cureBody(patient)
    local counts = Med.cure(patient)

    local damage = Med.damageOf(patient)
    if damage then
        U.try("emh.cureBody", function()
            damage:setInfected(false)
            damage:setIsFakeInfected(false)
            damage:setReduceFakeInfection(false)
            damage:setInfectionTime(-1.0)
            damage:setInfectionMortalityDuration(-1.0)
        end)
        local still = U.try("emh.cureCheck", function()
            return damage:isInfected()
        end)
        if still == true then
            U.log("WARN emh: the body still reports the infection after a cure")
            counts.left = (counts.left or 0) + 1
        end
    end

    Med.publish(patient)
    return counts
end

Net.onServer("emhSummon", function(player)
    if not atEMH(player) then return end
    local s = U.state()
    if s.emh ~= true then
        -- Projecting him costs power; putting him away is free (ENERGY.md 6).
        if not TREK.Energy.energize(player, "emhProject", C.EmhProjectCost,
                                    { why = "emhNoPower", noCommit = true }) then
            return
        end
        s.emh = true
        Ship.commit()
    end
    -- The deck is brought into line straight away rather than waiting for a
    -- tick: the player is standing at the station looking at an empty square.
    B.serviceEMH()
    U.log("emh: %s brought the Doctor up", Ship.usernameOf(player))
end)

Net.onServer("emhDismiss", function(player)
    -- Deliberately **not** atEMH: dismissing is the way out, and a player who
    -- has walked off, or whose ship has run flat while the panel was open,
    -- must still be able to put him away. Alive and allowed to use the ship
    -- is the whole gate.
    if not alive(player) then return end
    if not Ship.canUse(player) then
        deny(player, "access")
        return
    end
    local s = U.state()
    if s.emh ~= nil then
        s.emh = nil
        Ship.commit()
    end
    B.serviceEMH()
    U.log("emh: %s dismissed the Doctor", Ship.usernameOf(player))
end)

--- What he can see about a patient, for a panel that cannot look itself.
Net.onServer("emhLook", function(player, args)
    if not atEMH(player) then return end
    local patient, name = patientFor(player, args)
    if not patient then return end

    local found = EMH.findings(patient)
    Net.toClient(player, "emhFindings", {
        who = name,
        total = found.total,
        infected = found.infected,
        bitten = found.bitten,
        items = found.items,
    })
end)

--- Mints a consent offer and puts it on the patient's screen.
local function offer(player, patient, name, what, cost)
    offerSerial = offerSerial + 1
    local token = offerSerial
    offers[token] = { from = Ship.usernameOf(player), who = name,
                      what = what, cost = cost, at = getTimestampMs() }
    Net.toClient(patient, "emhOffered", {
        token = token, from = offers[token].from, what = what, cost = cost,
    })
    U.log("emh: %s asked to %s %s (offer %d)",
          offers[token].from, what, name, token)
end

--- Treating. Yourself at once; anybody else only if they say yes.
Net.onServer("emhTreat", function(player, args)
    if not atEMH(player) then return end
    local patient, name = patientFor(player, args)
    if not patient then return end

    local why = EMH.treatRefusal(patient)
    if why then
        deny(player, why)
        return
    end

    if name ~= Ship.usernameOf(player) then
        -- Nothing is spent yet. The offer is a question, not a reservation.
        offer(player, patient, name, "treat", EMH.treatCost())
        return
    end

    if not spendTreatment(player) then return end
    local counts = treatBody(patient)
    Net.toClient(player, "emhTreated", { who = name, counts = counts,
                                         total = counts.total })
    U.log("emh: treated %s -- %d thing(s) put right, %d unit(s) spent, "
          .. "%d left in the reserve", name, counts.total, EMH.treatCost(),
          math.floor(TREK.Power.reserve()))
end)

--- The cure. Yourself at once; anybody else only if they say yes.
Net.onServer("emhCure", function(player, args)
    if not atEMH(player) then return end
    local patient, name = patientFor(player, args)
    if not patient then return end

    local why = EMH.cureRefusal(patient, name)
    if why then
        deny(player, why)
        return
    end

    if name ~= Ship.usernameOf(player) then
        offer(player, patient, name, "cure", C.EmhCureCrystals)
        return
    end
    S.beginCure(player, patient, name)
end)

--- Takes the crystal and writes the patient into the register.
---
--- **The crystal is spent now**, and the panel says so before the button is
--- pressed. The treatment is a commitment rather than a reservation, which
--- is the whole weight of the twelve hours: walking out of the cabin halfway
--- through costs it.
function S.beginCure(player, patient, name)
    if TREK.Power.crystals() < C.EmhCureCrystals then
        deny(player, "emhNoCrystal")
        return false
    end
    for _ = 1, C.EmhCureCrystals do
        if not TREK.Power.takeCrystal() then
            deny(player, "emhNoCrystal")
            return false
        end
    end

    local due = EMH.worldHours() + C.EmhCureHours
    EMH.cures()[name] = due
    Ship.commit()

    Net.toClient(patient, "emhCureStarted", { hours = C.EmhCureHours })
    U.log("emh: a cure has begun for %s -- due at world hour %.1f, %d spare "
          .. "crystal(s) left", name, due, TREK.Power.crystals())
    return true
end

--- The patient's answer. Re-validated from scratch, because the world moves
--- between the question and the answer.
local function resolveOffer(player, args, accepted)
    if not alive(player) then return end
    local token = int(args and args.token)
    local job = token and offers[token]
    if not job then
        deny(player, "emhNoOffer")
        return
    end
    -- Single use, whatever happens next.
    offers[token] = nil

    if job.who ~= Ship.usernameOf(player) then
        -- Somebody else's offer. Not an error a player can see -- it is a
        -- crafted command -- but it is worth a line in the log.
        U.log("WARN emh: %s answered an offer addressed to %s",
              Ship.usernameOf(player), tostring(job.who))
        return
    end

    if getTimestampMs() - job.at > C.EmhOfferMs then
        deny(player, "emhOfferLapsed")
        return
    end
    if not accepted then
        U.log("emh: %s declined to be %sed", job.who, job.what)
        return
    end

    -- Everything again, from scratch: the asker may have walked off, the
    -- patient may have left the ship, the core may have been emptied.
    local asker = playerNamed(job.from)
    if not asker or EMH.refusal(asker) then
        deny(player, "emhGone")
        return
    end
    local patient = EMH.patientNamed(job.who)
    if not patient then
        deny(player, "emhNoPatient")
        return
    end

    if job.what == "cure" then
        local why = EMH.cureRefusal(patient, job.who)
        if why then
            deny(player, why)
            return
        end
        S.beginCure(asker, patient, job.who)
        return
    end

    local why = EMH.treatRefusal(patient)
    if why then
        deny(player, why)
        return
    end
    if not spendTreatment(asker) then return end
    local counts = treatBody(patient)
    Net.toClient(patient, "emhTreated", { who = job.who, counts = counts,
                                          total = counts.total })
    U.log("emh: treated %s at %s's asking -- %d thing(s) put right",
          job.who, job.from, counts.total)
end

Net.onServer("emhAccept", function(player, args)
    resolveOffer(player, args, true)
end)

Net.onServer("emhDecline", function(player, args)
    resolveOffer(player, args, false)
end)

--- Finishes, abandons or leaves alone every cure in the register.
---
--- Three cases and they are all deliberate:
---
---   * **the patient has left the ship** -- the entry goes, they are told,
---     and the crystal does not come back. Not a refund: see S.beginCure;
---   * **it is due** -- cure them, both levels, and tell their own client to
---     clear the flags and the moodle the packet cannot carry;
---   * **they are not online** -- leave it. The register is ship state and is
---     saved, so a cure survives a relog.
function S.serviceCures()
    local cures = EMH.cures()
    local names = {}
    for name in pairs(cures) do table.insert(names, name) end
    if #names == 0 then return 0 end

    local now = EMH.worldHours()
    local done, dropped = 0, 0
    for _, name in ipairs(names) do
        local patient = playerNamed(name)
        if patient then
            local aboard = EMH.aboardForCure(patient)
            if aboard then
                offShip[name] = nil
            elseif not offShip[name] then
                -- The first check off the ship starts the grace; it does not
                -- end the cure. Changing places -- forward to the cockpit,
                -- aft to the cabin -- passes through the ground beside her.
                offShip[name] = now
                U.log("emh: %s is off the ship; the cure is lost if they stay "
                      .. "off for %.0f game minute(s)", name,
                      C.EmhCureGraceHours * 60)
            end
            if not aboard and now - offShip[name] >= C.EmhCureGraceHours then
                cures[name] = nil
                offShip[name] = nil
                dropped = dropped + 1
                Net.toClient(patient, "emhCureLost", {})
                U.log("emh: %s left the ship and the cure is lost, crystal "
                      .. "and all", name)
            elseif aboard and now >= (cures[name] or 0) then
                -- Only aboard: a cure that falls due during the grace waits
                -- for them to come back, rather than landing on the road.
                cures[name] = nil
                done = done + 1
                local counts = cureBody(patient)
                -- **The reply is not optional.** syncBodyPart carries
                -- BodyPart fields only, so the BodyDamage flags above and
                -- the infection moodle do not ride it -- and the moodle is
                -- written from inside a countdown that is gated on
                -- isInfected(), so clearing the infection *stops* its only
                -- writer and the last value it wrote is what stays on screen:
                -- a perfect cure with the player still told they are dying.
                Net.toClient(patient, "emhCured", {})
                U.log("emh: %s is cured -- %d field(s) cleared, %d left set",
                      name, counts.total or 0, counts.left or 0)
            end
        end
    end
    if done > 0 or dropped > 0 then Ship.commit() end
    return done
end

--- The ship has gone dark (ENERGY.md 6). The projection needs power to exist
--- at all, so he goes out; and a cure that is running **fails** -- the
--- author's decision, 2026-09-24: "PZ is a fiercely realistic simulator".
---
--- The twelve hours aboard are the Doctor keeping the patient under
--- treatment. With him gone the patient stays infected, the crystal that paid
--- for it is gone with no refund, and the crew are told plainly. It has to be
--- delivered: a cure that ends in silence reads as a bug.
function S.failCures(why)
    local s = U.state()
    local changed = false
    if s.emh ~= nil then
        s.emh = nil
        changed = true
    end
    local cures = EMH.cures()
    local names = {}
    for name in pairs(cures) do table.insert(names, name) end
    for _, name in ipairs(names) do
        cures[name] = nil
        offShip[name] = nil
        changed = true
        Net.toAll("emhCureFailed", { who = name })
        U.log("emh: %s -- the cure for %s has failed; still infected, crystal lost",
              tostring(why), name)
    end
    if changed then Ship.commit() end
    U.try("serviceEMH", B.serviceEMH)
    return #names
end

TREK.Energy.onPowerDown(function() S.failCures("main power lost") end)

---------------------------------------------------------------------------
-- Long-range probes
---------------------------------------------------------------------------
-- A launch is **one authority-side transaction**: validate, spend, and create
-- the job, with nothing in between that a second request could interleave
-- with. Two crew hitting the menu together therefore produce one probe and
-- one deduction, which is what ROADMAP2 asks for -- "Racing launch requests
-- create one job and one deduction" -- and it comes out of doing the whole
-- thing in one handler rather than out of any locking.
--
-- The **server chooses the bearing**. It is not a client's to pick: a client
-- that could name the direction could name the one with the crystal in it.
Net.onServer("launchProbe", function(player, args)
    if not mayUse(player) then return end

    -- Aboard, because the probe is fabricated and launched by the ship. This
    -- is checked against the *server's* copy of where the player is.
    if not U.isAboard(player:getX(), player:getY(), player:getZ()) then
        deny(player, "probeAboard")
        return
    end
    if Probes.active() then
        deny(player, "probeActive")
        return
    end

    -- Launching costs a **probe**, not energy. Energy bought it earlier, at
    -- the fabricator, which is what makes "three probes aboard" a thing the
    -- crew can see and plan around.
    local s = U.state()
    if (s.probes or 0) < 1 then
        deny(player, "probeNone")
        return
    end
    s.probes = (s.probes or 0) - 1

    -- **From where the crew actually are**, not from the ship's own record.
    -- `s.x, s.y` is where the shuttle was last set down, and it is 0,0 in a
    -- world where she has never been called down -- which put the first probe
    -- anybody fired in the far corner of the map while the crew stood in
    -- Muldraugh. Ship.worldOrigin answers the question that was meant: where
    -- is this player in the real world, or where would they be if they beamed
    -- down.
    local ox, oy = Ship.worldOrigin(player)
    if not ox then
        s.probes = (s.probes or 0) + 1
        Ship.commit()
        deny(player, "probeNoFix")
        U.log("WARN a probe was launched with no position fix for %s",
              Ship.usernameOf(player))
        return
    end

    -- **Pick a bearing that actually lands somewhere.** A straight line from a
    -- ship parked near the edge of the map spends much of the compass
    -- pointing at nothing, and a contact outside the world is a mark the crew
    -- walk toward that can never have anything on it. That is what the first
    -- probe anybody launched did.
    local span = C.ProbeMaxDistance - C.ProbeMinDistance
    local bearing, distance
    for _ = 1, C.ProbeBearingTries do
        local b = (U.try("probeBearing", function()
            return ZombRand(3600) / 3600.0
        end) or 0) * math.pi * 2
        local d = C.ProbeMinDistance + (U.try("probeRange", function()
            return ZombRand(span + 1)
        end) or math.floor(span / 2))
        -- Shrink toward the ship rather than abandon the bearing: a shorter
        -- hop the same way is still a probe, and near a map edge that is the
        -- difference between reporting something and reporting nothing.
        while d >= C.ProbeMinDistance do
            if U.inWorld(ox + math.cos(b) * d, oy + math.sin(b) * d) then
                bearing, distance = b, d
                break
            end
            d = d - 30
        end
        if bearing then break end
    end

    if not bearing then
        -- Every bearing tried and none lands in the world. Give the probe
        -- back rather than charging for a launch that cannot report.
        s.probes = (s.probes or 0) + 1
        Ship.commit()
        deny(player, "probeNoRoom")
        U.log("WARN no bearing from %d,%d puts a probe inside the world", ox, oy)
        return
    end

    local probe = Probes.begin(ox, oy, bearing, distance,
                               C.ProbeFlightTicks)
    if not probe then
        -- Nothing took the power. begin() only refuses when a probe is
        -- already up, and that was checked above, so reaching here means the
        -- two disagree -- give the power back rather than quietly charging
        -- for nothing, and **say so**.
        --
        -- The WARN is the point. Without it this branch is invisible: it
        -- refunds, refuses with the same reason the guard above would have
        -- given, and is indistinguishable from the guard working. A test
        -- cannot tell the two apart and neither could anybody reading a log.
        U.log("WARN probe launch got past the active check and begin() still "
              .. "refused; the probe is back in the rack")
        s.probes = (s.probes or 0) + 1
        Ship.commit()
        deny(player, "probeActive")
        return
    end

    Ship.commit()       -- the rack changed
    Probes.publish()    -- and so did the probe log
    U.log("probe %s away on bearing %.2f for %d tiles, %d left in the rack",
          probe.id, bearing, distance, s.probes)
end)

--- Turns reserve into a probe. One at a time, and the same shape as a launch:
--- validate, spend, and hand the thing over in one handler.
Net.onServer("buildProbe", function(player, args)
    if not mayUse(player) then return end
    if not U.isAboard(player:getX(), player:getY(), player:getZ()) then
        deny(player, "probeAboard")
        return
    end

    local s = U.state()
    if (s.probes or 0) >= C.MaxProbes then
        deny(player, "probeRackFull")
        return
    end

    -- The ledger burns a spare crystal when the reserve is short, which is
    -- the whole reason a crystal is worth carrying.
    if not TREK.Energy.energize(player, "probe", C.ProbeCost,
                                { why = "probeNoPower", noCommit = true }) then
        return
    end

    s.probes = (s.probes or 0) + 1
    Ship.commit()
    U.log("a probe is fabricated; %d in the rack, %d units left",
          s.probes, math.floor(TREK.Power.reserve()))
end)

--- Puts the crystal in the world, once somebody is close enough to ask.
---
--- **This is what makes a probe report real.** A contact out of a probe is a
--- record and nothing else: its squares are in unloaded chunks, and asking
--- the engine about those is the one thing DEV_GUIDE forbids outright --
--- `getOrCreateGridSquare` on an unloaded chunk hands back an orphan and the
--- first call touching it throws. So the crystal is placed when a player
--- legitimately loads the chunk, which is exactly the pattern `s.ghosts` and
--- `sweepGhosts` already use for removal, run the other way round.
---
--- A nil square in a *loaded* chunk really is nothing there; only an unloaded
--- chunk means "ask again later". Getting that backwards is what leaves a
--- sweep re-walking the same squares for the life of the save.
local function placeContact(contact)
    if contact.placed then return false end

    -- **The whole search area has to be loaded, not just the centre.** The
    -- search below spans ContactPlaceRadius squares either side and can cross
    -- a chunk boundary, and a nil square in an unloaded chunk means "ask
    -- again later", never "nothing there" (DEV_GUIDE, *Never build where no
    -- player is standing*). Checking only the middle would let a player
    -- walking past the edge of a contact retire it before they ever arrived.
    --
    -- One check rather than two: this is also the cheap early-out that stops
    -- a hundred and sixty-nine square lookups happening for every contact on
    -- file, every game minute, for ever.
    local r = C.ContactPlaceRadius
    if not (U.chunkLoaded(contact.x - r, contact.y - r, contact.z)
            and U.chunkLoaded(contact.x + r, contact.y - r, contact.z)
            and U.chunkLoaded(contact.x - r, contact.y + r, contact.z)
            and U.chunkLoaded(contact.x + r, contact.y + r, contact.z)) then
        return false
    end

    -- Search outward from the reported square for ground that will hold it.
    -- The probe's fix is approximate by design, so the exact square it named
    -- may be a wall, a roof or a pond.
    local best = nil
    for ring = 0, r do
        for dx = -ring, ring do
            for dy = -ring, ring do
                if math.abs(dx) == ring or math.abs(dy) == ring then
                    local sq = U.square(contact.x + dx, contact.y + dy,
                                        contact.z, false)
                    if sq then
                        local ok = U.try("contactGround", function()
                            return sq:getFloor() ~= nil and not sq:isSolid()
                                   and not sq:isSolidTrans()
                        end)
                        if ok then best = sq break end
                    end
                end
            end
            if best then break end
        end
        if best then break end
    end

    if not best then
        -- Loaded, looked at, and genuinely nowhere to put it -- the middle of
        -- a lake or inside a building. Retire it rather than retrying the
        -- same squares for the life of the save.
        U.log("WARN contact %s: no ground within %d squares of %d,%d; expired",
              contact.id, C.ContactPlaceRadius, contact.x, contact.y)
        contact.status = "expired"
        return true
    end

    -- A crystal, or a clue's fragment: the contact says which.
    local what = contact.item or C.DilithiumItem
    local item = U.try("contactCrystal", function()
        return best:AddWorldInventoryItem(what, 0.5, 0.5, 0.0)
    end)
    if not item then
        U.log("WARN contact %s: %s could not be created", contact.id, what)
        return false
    end

    contact.placed = true
    contact.x = U.try("contactX", function() return math.floor(best:getX()) end)
                or contact.x
    contact.y = U.try("contactY", function() return math.floor(best:getY()) end)
                or contact.y
    -- No longer a guess: the ship knows exactly where it put it.
    contact.approximate = false
    contact.status = "investigated"
    U.log("contact %s: %s is on the ground at %d,%d",
          contact.id, what, contact.x, contact.y)
    return true
end

--- True when the crystal this contact placed is no longer lying there.
local function crystalTaken(contact)
    local sq = U.square(contact.x, contact.y, contact.z, false)
    if not sq then return false end     -- unloaded: cannot tell, not "gone"
    local found = U.try("contactLook", function()
        local items = sq:getWorldObjects()
        if not items then return false end
        for i = 0, items:size() - 1 do
            local o = items:get(i)
            local it = o and o.getItem and o:getItem()
            if it and it:getFullType() == (contact.item or C.DilithiumItem) then
                return true
            end
        end
        return false
    end)
    return found == false
end

--- Places crystals people have come to find, and retires the ones they took.
--- Authority only, on the per-minute tick.
function S.serviceContacts()
    local changed = false
    for _, contact in ipairs(Probes.contacts()) do
        -- A contact outside the playable world can never be reached, let
        -- alone have a crystal put on it. Saves made before the range was
        -- corrected carry these, so they are retired here rather than left on
        -- the map as a mark the crew walk toward for ever.
        if not Probes.isResolved(contact.status)
           and not U.inWorld(contact.x, contact.y) then
            contact.status = "invalid"
            changed = true
            U.log("contact %s at %d,%d is outside the world; retired",
                  contact.id, contact.x, contact.y)
        elseif (contact.kind == "dilithium" or contact.kind == "clue")
               and not Probes.isResolved(contact.status) then
            if not contact.placed then
                -- No proximity pre-check. There was one -- skip contacts no
                -- player is near -- and it could not be observed from
                -- outside: `placeContact` asks `U.chunkLoaded` first, and a
                -- chunk is only loaded when somebody *is* near, so the two
                -- guards always agreed. A branch a mutation cannot break is
                -- either untested or unreachable, and this one was neither
                -- load-bearing nor measurable. The cap is 64 contacts and
                -- this runs once a game minute.
                if placeContact(contact) then changed = true end
            elseif crystalTaken(contact) then
                contact.status = "recovered"
                changed = true
                U.log("contact %s: the crystal has been recovered", contact.id)
            end
        end
    end
    if changed then
        Probes.prune()
        Probes.publish()
    end
end

--- Which fragment a probe finds, or nil for a crystal. Authority only.
---
--- A fragment is owed while it is not on tape and no live contact already
--- points at one. **Not** "while nobody has picked it up": a fragment lost on
--- a body, or burned in a house, is a fragment a later probe can find again
--- -- he made more than one copy of everything, which is the kind of man he
--- was (LORE.md 1c). So the chain cannot be soft-locked by losing one, and a
--- death on the way home costs time rather than the story.
function S.clueFor()
    local Cm = TREK.Comms
    if not Cm then return nil end
    local d = Cm.store()
    if not d.flags.met then return nil end
    local live = {}
    for _, c in ipairs(Probes.contacts()) do
        if c.kind == "clue" and not Probes.isResolved(c.status) and c.fragment then
            live[c.fragment] = true
        end
    end
    local owed = {}
    for n = 1, 6 do
        if not (d.converted or {})[n] and not live[n] then table.insert(owed, n) end
    end
    if #owed == 0 then return nil end
    local roll = U.try("clueRoll", function() return ZombRand(100) end) or 100
    if roll >= math.floor(C.ProbeClueShare * 100) then return nil end
    local pick = U.try("cluePick", function() return ZombRand(#owed) end) or 0
    return owed[pick + 1]
end

--- Advances the probe and reports what it found. Authority only.
---
--- Runs on the game-minute tick rather than per server tick, because a
--- three-hundred-tick flight at sixty ticks a second is five seconds and this
--- is meant to be a journey. It is also the tick every setup is certain to
--- run, so a probe cannot be stranded by a client disconnecting -- ROADMAP2:
--- "A probe continues if its launching player disconnects."
function S.serviceProbe()
    if not Probes.active() then return end
    local done = Probes.advance(C.ProbeWorkPerTick)
    if not done then
        -- Progress is persisted, so a server restart mid-flight resumes
        -- rather than losing the probe and the power that bought it.
        Probes.publish()
        return
    end

    -- **The first probe of a save always finds something.** At a 65% hit rate
    -- one launch in three is 250 units and an hour of game time for a line in
    -- a log the player never reads, and the very first one coming back empty
    -- is indistinguishable from the feature being broken -- which is exactly
    -- how it read the first time anybody played it. ROADMAP2 1.6 wants a
    -- guaranteed opening for the cold start anyway; this is the honest
    -- minimum of it, and every probe after the first is a fair roll.
    --
    -- And never more than C.ProbeDryLimit empty ones in a row: the first
    -- cold-start play drew four, which is a campaign stalled on luck.
    local s = U.state()
    local found
    if not s.probeEverFound or (s.probeDry or 0) >= C.ProbeDryLimit then
        found = true
    else
        found = (U.try("probeRoll", function()
            return ZombRand(100)
        end) or 0) < math.floor(C.ProbeFindChance * 100)
    end
    s.probeDry = found and 0 or (s.probeDry or 0) + 1

    if found then
        -- A long-range fix is a region, not a square. The spread is what the
        -- tricorder is for, and a probe that named the exact spot would make
        -- the whole close-range half of the design pointless.
        local function scatter()
            return (U.try("probeScatter", function()
                return ZombRand(C.ProbeReportSpread * 2 + 1)
            end) or C.ProbeReportSpread) - C.ProbeReportSpread
        end
        -- The scatter is applied *after* the bearing was checked, so it can
        -- push an otherwise valid fix back out of the world. Fall back to the
        -- endpoint itself rather than reporting a square nobody can reach.
        local cx, cy = done.x + scatter(), done.y + scatter()
        if not U.inWorld(cx, cy) then cx, cy = done.x, done.y end
        -- The third result: a holo fragment's site, once Shepard has been
        -- met and while any of the six is still owed. Never the first probe
        -- of a save -- that one is the crystal the ship needs.
        local clue = s.probeEverFound and S.clueFor and S.clueFor()
        local contact
        if clue then
            contact = Probes.addContact("clue", cx, cy, 0, done.id, true)
            if contact then
                contact.fragment = clue
                contact.item = C.FragmentItems[clue]
                if TREK.CommsServer then TREK.CommsServer.event("clue") end
            end
        else
            contact = Probes.addContact("dilithium", cx, cy, 0, done.id, true)
        end
        if contact then
            U.log("probe %s reports %s at %d,%d", done.id, contact.kind,
                  contact.x, contact.y)
        end
    else
        -- An honest empty result is a real outcome and has to be reported as
        -- one. What must never look like this is an engine failure, which is
        -- why every call above goes through U.try and logs a WARN of its own.
        U.log("probe %s returned nothing", done.id)
    end

    if found then s.probeEverFound = true end
    s.probeReport = { id = done.id, found = found, at = getTimestampMs() }
    Ship.commit()
    Probes.publish()

    -- **Tell the crew.** Until this, the only trace of an empty report was a
    -- line in console.txt, so from the console a probe that found nothing and
    -- a probe that never happened looked exactly the same. ROADMAP2 asks for
    -- the page to show recent reports, and an honest empty result is a real
    -- outcome that has to be reported as one.
    for _, p in ipairs(U.players()) do
        Net.toClient(p, "probeReport", { found = found })
    end
end

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
    elseif what == "power" then
        TREK.Power.report()
    elseif what == "galley" then
        B.giveGalley(player)
    elseif what == "ghosts" then
        local s = U.state()
        U.log("ghosts: %d hull(s) pending removal", #s.ghosts)
        local cleared = S.sweepGhosts()
        local strays = S.sweepStrays(player)
        U.log("ghosts: cleared %d, plus %d stray(s) near %s",
              cleared, strays, Ship.usernameOf(player))
    elseif what == "replicator" then
        S.replicatorReport()
    elseif what == "emh" then
        S.emhReport()
    elseif what == "uniform" then
        S.uniformReport()
    elseif what == "charges" then
        local c = chargeOf(Ship.usernameOf(player))
        U.log("transporter: limited=%s, %d charge(s) for %s",
              tostring(S.chargesLimited()), c.n, Ship.usernameOf(player))
    end
end)

---------------------------------------------------------------------------
-- The emergency landing (ENERGY.md section 7)
---------------------------------------------------------------------------
-- The author's rule: "with no power the fallback is no beaming, but as soon
-- as there is room to land, it lands with no damage." Ground is only loaded
-- around a player, and the server builds only where one is standing, so an
-- emergency landing happens where the crew are. Each case follows from that.
--
-- `s.emergency` is published: `true` for a dark ship in the air (7.1, 7.2),
-- "descend" for a dark ship overhead with crew in her cabin (7.3). It clears
-- at touchdown, or when the power comes back.

-- The server's own search for somewhere to put her down (7.2), resumed each
-- vehicle pass. Server-local: a restart simply searches again.
local emergencySearch = nil
-- When the crew were last asked to take her down from orbit (7.3).
local descendAskedAt = nil

--- The first living player standing in the cabin, or nil.
local function firstAboard()
    for _, p in ipairs(U.players()) do
        if U.isInteriorPlayer(p) and alive(p) then return p end
    end
    return nil
end

--- Takes her down with the first of the crew aboard (ENERGY.md 7.3). It is
--- the helm's own take-her-down (T.descend) run on their machine, free, and a
--- *landing* in the story as in the code -- not a transporter beam. Approved
--- by the author, 2026-09-24: it is the one place the ship moves the crew
--- without being asked, and the only way the engine lets her land where
--- nobody is standing.
---
--- **In orbit** it goes to where that crewman beamed up from. **Hovering**,
--- with nobody at her controls and nobody near her, it goes to the ground
--- beneath her: her ground is not loaded, so the server cannot search it
--- (7.2), the hatch is shut in flight and a dark ship does not beam, so
--- without this her crew would be sealed in a ship that waited for ever for
--- somebody to come near. The crew arrive standing beside her.
---
--- Asked at most once every C.EmergencyDescendRetryMs, unless `now`: the
--- crewman's machine may be busy, or the landing may have found no room and
--- beamed them back aboard.
function S.emergencyDescend(now)
    local s = U.state()
    if not TREK.Power.dark() then return false end
    local airborne = s.flying == true
    if s.landed and not airborne then return false end
    local p = firstAboard()
    if not p then return false end
    local clock = getTimestampMs()
    if not now and descendAskedAt and clock - descendAskedAt < C.EmergencyDescendRetryMs then
        return false
    end
    if not airborne and s.emergency ~= "descend" then
        s.emergency = "descend"
        Ship.commit()
    end
    descendAskedAt = clock
    local args = {}
    if airborne then args = { x = s.x, y = s.y, z = s.z or 0 } end
    Net.toClient(p, "emergencyDescend", args)
    U.log("power: asking %s's machine to take her down %s", Ship.usernameOf(p),
          airborne and "from the air, beneath her" or "from orbit")
    return true
end

--- The moment the ship goes dark: which emergency, if any, this is.
function S.beginEmergency()
    local s = U.state()
    emergencySearch = nil
    if s.flying then
        s.emergency = true
        Ship.commit()
        Net.toAll("emergency", {})
        U.log("power: dark in the air -- emergency landing")
        return "hover"
    end
    if not s.landed and firstAboard() then
        Net.toAll("emergency", {})
        S.emergencyDescend(true)
        return "descend"
    end
    return nil
end

TREK.Energy.onPowerDown(function() S.beginEmergency() end)
TREK.Energy.onPowerUp(function()
    local s = U.state()
    emergencySearch = nil
    if s.emergency ~= nil then
        s.emergency = nil
        Ship.commit()
        U.log("power: back before she was down -- the emergency is over")
    end
end)

--- Every vehicle pass during an emergency in the air. Returns true when it
--- set her down (and the rest of the pass should stop).
---
--- 7.1, **a pilot in the seat**: nothing here. Their machine owns her
--- physics, keeps her engine alive at a crawl and asks for the ordinary
--- touchdown the moment the footprint below is clear.
---
--- 7.2, **nobody in the seat**: the server searches round her for a clear
--- footprint, sliced and only while her ground is loaded, and sets her down
--- there through S.land -- a clean spawn, so no damage. Nothing clear, and it
--- keeps looking. Her ground not loaded means nobody is near her: with crew in
--- the cabin, one of them takes her down beneath her (S.emergencyDescend);
--- with nobody aboard at all, she waits for somebody to come.
function S.serviceEmergency(vehicle)
    local s = U.state()
    if s.emergency ~= true or not s.flying then return false end
    if vehicle and U.try("emergencyDriver", function() return vehicle:getDriver() end) then
        emergencySearch = nil
        return false
    end
    local x, y = s.x, s.y
    if vehicle then
        x = math.floor(vehicle:getX())
        y = math.floor(vehicle:getY())
    end
    if not x or not U.chunkLoaded(x, y, 0) then
        S.emergencyDescend()
        return false
    end

    if not emergencySearch or emergencySearch.x ~= x or emergencySearch.y ~= y then
        emergencySearch = { x = x, y = y, z = 0, cursor = 0 }
    end
    local sq = W.searchSlice(emergencySearch)
    if not sq then return false end

    local tx, ty = sq:getX(), sq:getY()
    emergencySearch = nil
    s.emergency = nil
    S.endFlight("emergency landing")
    local ok, why = S.land(tx, ty, 0, nil)
    if not ok then
        -- The ground changed between the search and the landing. She is out
        -- of the air now and the next pass looks again from wherever she is.
        s.emergency = true
        Ship.commit()
        U.log("WARN power: the emergency landing at %d,%d was refused (%s)",
              tx, ty, tostring(why))
        return false
    end
    Net.toAll("emergencyLanded", { x = tx, y = ty, z = 0 })
    U.log("power: emergency landing at %d,%d with nobody at the controls", tx, ty)
    return true
end

--- Once a game minute: a dark ship still in orbit with crew aboard, whose
--- descent has not happened, is asked again. The flag is cleared once she is
--- down or the power is back.
function S.serviceEmergencyDescend()
    local s = U.state()
    if s.landed or not TREK.Power.dark() then
        if s.emergency == "descend" then
            s.emergency = nil
            Ship.commit()
        end
        return false
    end
    return S.emergencyDescend()
end

---------------------------------------------------------------------------
-- Timers
---------------------------------------------------------------------------
-- Every tick while anyone is waiting: they are standing over nothing until the
-- cabin exists, and each tick of delay is a tick they can fall. With nobody
-- waiting the check is one empty table walk.
local vehicleTick = 0
Events.OnTick.Add(function()
    U.try("serviceWaiting", serviceWaiting)
    -- Every tick, because a torpedo is in the air for well under a second and
    -- anything slower would make the impact visibly late for its own flight.
    -- With nothing in the air it is a length check on an empty table.
    U.try("serviceTorpedoes", S.serviceTorpedoes)
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
    -- The cure is measured in game hours and lands on this tick. Outside the
    -- cabin-loaded branch on purpose: a patient who has left the ship has to
    -- lose their treatment whether or not anybody is aboard to see it.
    U.try("serviceCures", S.serviceCures)
    -- Outside the cabin-loaded branch on purpose, like the cures: a probe is
    -- a logical job with no world object behind it, and it must keep flying
    -- whether or not anybody is aboard to watch it.
    U.try("serviceProbe", S.serviceProbe)
    -- Contacts become crystals only when somebody goes and looks, so this
    -- runs wherever the players are rather than only near the ship.
    U.try("serviceContacts", S.serviceContacts)
    U.try("emergencyDescend", S.serviceEmergencyDescend)
    if B.cabinCurrent() and B.cabinLoaded() then
        -- Nobody can drain the tap faster than a game minute refills it.
        U.try("refillWater", B.refillWater)
        if anyoneAboard() then
            -- The deck brought back into line with s.emh. Idempotent both
            -- ways, so this is also what heals a dismissal that happened
            -- while the cabin's chunks were not loaded -- no ghost list.
            U.try("serviceEMH", B.serviceEMH)
            -- Power is not here: TREK_Power registers its own per-minute tick,
            -- because the engine drains a device's cell in every process and
            -- a server-only top-up would leave each client switching the
            -- television off by itself.
            U.try("clearMargin", B.clearLoadedSurroundings)
        end
    end
end)

Events.EveryTenMinutes.Add(function()
    for _, p in ipairs(U.players()) do
        U.try("sweepStrays", S.sweepStrays, p)
    end
    -- Nothing refills the ship's power any more: it is a dilithium crystal,
    -- and a crystal has to be found. TREK_Power swaps a spare in out of the
    -- chamber when the replicator asks for more than is left.
end)

-- The schema migration runs on the authority as soon as the world's data is
-- there, and is published, so no client ever sees a schema 1 table.
Events.OnInitGlobalModData.Add(function()
    local s = U.state()
    -- Flight never survives a world load. Nothing about a vehicle's physics is
    -- saved, so a world that shut down with the ship in the air reopens with
    -- it on the ground -- and U.state() only runs its migration block when the
    -- schema changes, so `flying` would otherwise persist with a pilot who is
    -- not even connected. s.skyAt is deliberately kept: it is how the
    -- invisible floors that flight left behind get taken up again.
    if s.flying then
        U.log("the world was saved with the shuttle in flight; she is on the " ..
              "ground now")
        s.flying = nil
        s.pilot = nil
        s.level = nil
        s.pilotGrace = nil
    end
    -- A hologram does not survive a world reload, and clearing the flag here
    -- deletes the entire class of stale-flag bug: nobody ever has to explain
    -- why the Doctor is standing in an empty sick bay after a restart.
    --
    -- **s.emhCures is kept.** A cure in progress has been paid for with a
    -- crystal and has to survive, which is the whole reason it is ship state
    -- rather than a table in this file.
    if s.emh then
        U.log("the world was saved with the Doctor projected; he is off now")
        s.emh = nil
    end
    Ship.commit()
    U.log("ship authority ready (%s, v%s, build %d): landed=%s built=%s rev=%s owner=%s, " ..
          "beams limited=%s", isServer() and "server" or "single player", C.Version,
          C.BuildRev, tostring(s.landed), tostring(s.built), tostring(s.rev),
          tostring(s.owner), tostring(S.chargesLimited()))
    S.checkVoidMap()

    -- The ship knows its own stores. Run on every start rather than once, so
    -- an item added to the mod later is a pattern with no migration, and it
    -- only publishes when something was actually new.
    local seeded = U.try("seedPatterns", Rep.seedDefaults) or 0
    if seeded > 0 then Rep.publish() end
end)

--- One line per thing that can be wrong with the replicator, for
--- TREK_Replicator() from the console.
---
--- Four of this mod's bugs have been a fixture that is present, drawn and
--- inert, so the machine is looked for rather than assumed: the model is a
--- world item on its square, and if it is not there the panel still works but
--- there is nothing to right-click.
function S.replicatorReport()
    local mode = Rep.mode()
    local modeName = (mode == C.ReplicatorOff and "off")
                  or (mode == C.ReplicatorUnrestricted and "unrestricted")
                  or "patterns and energy"
    U.log("replicator: sandbox %s, reserve %d/%d units, %d spare crystal(s), "
          .. "%d pattern(s), %d catalogue entr(ies)",
          modeName, math.floor(TREK.Power.reserve()), C.PowerMax,
          TREK.Power.crystals(), Rep.patternCount(), #Rep.catalogue())

    local ox, oy = Rep.spot()
    local x, y = U.at(ox, oy)
    if not U.chunkLoaded(x, y, C.CabinZ) then
        U.log("replicator: the square at %d,%d is not loaded, so the machine "
              .. "cannot be looked for from here", ox, oy)
        return false
    end

    local standing = B.replicatorsAt(U.square(x, y, C.CabinZ, false))
    U.log("replicator: %d machine(s) standing at %d,%d", standing, ox, oy)
    if standing ~= 1 then
        U.log("replicator: expected exactly one; the panel still opens from "
              .. "that square either way, but there is nothing to right-click "
              .. "if it is zero")
    end
    return standing == 1
end

--- One line per uniform, for TREK_Uniform(). **This is the check that the
--- static tests cannot make.**
---
--- tests/test_assets.py proves the item, the clothing XML, the GUID row, the
--- mesh and the texture all exist and agree on disk. None of that proves the
--- *engine* agreed: `OutfitManager.getClothingItem(guid)` resolves through
--- the merged table, and if this mod's fileGuidTable.xml did not merge -- a
--- path the engine reads with a catch that only reaches ExceptionLogger --
--- every one of those files is perfect and every uniform draws nothing.
---
--- So this asks the engine and reads the answer back, which is the only thing
--- that has ever caught this shape of bug in this project: an unopenable
--- locker, a tap with no water, a weapon one module away from its model. A
--- uniform whose ClothingItem is nil here is present, drawn and inert.
function S.uniformReport()
    local resolved, missing = 0, 0
    for _, id in ipairs(C.UniformIssue or {}) do
        local item = U.try("instanceItem:" .. id, function()
            return instanceItem(id)
        end)
        if not item then
            U.log("WARN uniform %s: instanceItem returned nothing -- the item "
                  .. "script did not load", id)
            missing = missing + 1
        else
            -- getClothingItem() is a method on an object the engine handed
            -- us, so it is reachable from Lua; it returns null when the GUID
            -- is not in the merged table.
            local cloth = U.try("getClothingItem:" .. id, function()
                return item:getClothingItem()
            end)
            if not cloth then
                U.log("WARN uniform %s: ClothingItem is nil. The GUID is not "
                      .. "in the merged table, so this garment equips, weighs "
                      .. "and insulates and draws NOTHING. Check that "
                      .. "media/fileGuidTable.xml shipped.", id)
                missing = missing + 1
            else
                local male = U.try("maleModel", function()
                    return cloth:getMaleModel()
                end)
                local female = U.try("femaleModel", function()
                    return cloth:getFemaleModel()
                end)
                local texes = U.try("textureChoices", function()
                    local list = cloth:getTextureChoices()
                    if not list or list:size() == 0 then return nil end
                    return tostring(list:get(0))
                end)
                U.log("uniform %s: male=%s female=%s texture=%s",
                      id, tostring(male), tostring(female), tostring(texes))
                if not male or tostring(male) == "" then
                    U.log("WARN uniform %s: resolved with no male model", id)
                end
                if not female or tostring(female) == "" then
                    U.log("WARN uniform %s: resolved with no female model -- "
                          .. "it would be invisible on a female character", id)
                end
                if not texes then
                    U.log("WARN uniform %s: resolved with no texture", id)
                end
                resolved = resolved + 1
            end
        end
    end
    U.log("uniforms: %d of %d resolved through the GUID table",
          resolved, resolved + missing)
    return missing == 0
end

--- One line per thing that can be wrong with the Doctor, for TREK_EMH().
---
--- Four of this mod's bugs have been a fixture that is present, drawn and
--- inert, so the figure is looked for rather than assumed -- and the two
--- numbers that matter are on separate lines: what the ship *believes* and
--- what is actually standing there.
function S.emhReport()
    local modeName = EMH.isOff() and "off" or "full"
    local cures = EMH.cures()
    local waiting, now = 0, EMH.worldHours()
    for name, due in pairs(cures) do
        waiting = waiting + 1
        U.log("emh: a cure for %s is due at world hour %.1f (%.1f to go)",
              name, due, math.max(0, due - now))
    end
    U.log("emh: sandbox %s, reserve %d/%d units, %d spare crystal(s), "
          .. "a treatment costs %d, a cure costs %d crystal and %d hours, "
          .. "%d cure(s) running",
          modeName, math.floor(TREK.Power.reserve()), C.PowerMax,
          TREK.Power.crystals(), C.EmhTreatCost, C.EmhCureCrystals,
          C.EmhCureHours, waiting)
    return B.emhReport()
end

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
