--[[ Shuttlecraft -- the hull outside, the hatch, and arriving aboard.

    The hull is a world model dropped on a square rather than a tile sprite,
    which means it needs no TileZed-packed tileset and can be set down
    anywhere the ground allows.

    It is not one tile. A police box needs a single free square and can
    materialise in a hallway; a shuttle needs a patch of street or field, and
    Core.roomToLand is the whole of that difference. It reports a *reason*
    rather than a bare boolean, because "there is a wall in the way" and "that
    ground has not loaded yet" want completely different answers.

    Arrival is the delicate part. The cabin lives in a cell nothing else ever
    visits, so its chunks are not streamed in until a player is standing
    there -- and nothing can be built into a chunk that has not loaded. So the
    player is moved in first and held, unfalling and unhurt, until the deck
    under their feet exists.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local Core = {}
TREK.Core = Core

-- How long to wait for the cabin chunks before giving up and putting the
-- player back outside. Ticks, so roughly ten seconds.
local ARRIVAL_TIMEOUT = 600

---------------------------------------------------------------------------
-- Finding the hull
---------------------------------------------------------------------------
--- The world item that represents the hull on a square, if it is there.
function Core.hullOn(sq)
    if not sq then return nil end
    local found = nil
    U.try("worldObjects", function()
        local objs = sq:getWorldObjects()
        if not objs then return end
        for i = 0, objs:size() - 1 do
            local o = objs:get(i)
            local item = o and o:getItem()
            if item and item:getFullType() == C.ExteriorItem then
                found = o
                return
            end
        end
    end)
    return found
end

--- True when a position is on or under the landed hull. The model is anchored
--- on one square but covers its whole footprint, so right-clicking any part
--- of it has to find the ship.
function Core.hullCovers(x, y, z)
    local s = U.state()
    if not s.landed then return false end
    if math.floor(z) ~= s.z then return false end
    for _, d in ipairs(C.footprintOffsets()) do
        if s.x + d[1] == math.floor(x) and s.y + d[2] == math.floor(y) then
            return true
        end
    end
    return false
end

--- Takes the hull off its square.
---
--- Returns `removed, reason`, and the reason is the point of it: "unloaded"
--- means the answer is not knowable yet, which is very different from
--- "absent" meaning there is nothing there. Treating those two the same is
--- what leaves a second hull standing every time the ship flies -- a landing
--- site is by definition far from where the ship was, so the old chunk is
--- never streamed in at the moment the new hull goes down.
function Core.removeHullAt(x, y, z)
    if not U.chunkLoaded(x, y, z) then return false, "unloaded" end
    local sq = U.square(x, y, z, false)
    if not sq then return false, "unloaded" end
    local obj = Core.hullOn(sq)
    if not obj then return false, "absent" end
    local ok = U.try("removeHull", function()
        sq:removeWorldObject(obj)
        return true
    end) == true
    return ok, ok and "removed" or "failed"
end

---------------------------------------------------------------------------
-- Hulls left behind
---------------------------------------------------------------------------
-- A hull that could not be lifted because its chunk was not loaded is
-- remembered here and swept up the next time the world streams that spot in.
-- Without this the old ship simply stays in the world for good.
local MAX_GHOSTS = 32

-- How far around the player to look for hulls nobody wrote down. Small: the
-- ship is five tiles long and impossible to miss, so this only has to cover
-- ground the player is standing on, not search for it.
local STRAY_RADIUS = 10

--- Notes a position that still has a hull on it we mean to be rid of.
function Core.forgetHull(x, y, z)
    local s = U.state()
    for _, g in ipairs(s.ghosts) do
        if g.x == x and g.y == y and g.z == z then return false end
    end
    table.insert(s.ghosts, { x = x, y = y, z = z })
    -- Bounded on purpose: this list is written to the save, and a player who
    -- flies a hundred times should not carry a hundred entries forever.
    while #s.ghosts > MAX_GHOSTS do table.remove(s.ghosts, 1) end
    U.log("the old hull at %d,%d,%d is out of reach; it will be cleared when " ..
          "that area loads", x, y, z)
    return true
end

--- Clears any remembered hull whose chunk has since streamed in.
---
--- A loaded chunk settles the question either way: the hull is removed, or it
--- was already gone. Either way the entry is done with.
function Core.sweepGhosts()
    local s = U.state()
    if #s.ghosts == 0 then return 0 end

    local cleared = 0
    for i = #s.ghosts, 1, -1 do
        local g = s.ghosts[i]
        if U.chunkLoaded(g.x, g.y, g.z) then
            local removed = Core.removeHullAt(g.x, g.y, g.z)
            table.remove(s.ghosts, i)
            if removed then
                cleared = cleared + 1
                U.log("cleared the old hull at %d,%d,%d", g.x, g.y, g.z)
            end
        end
    end
    return cleared
end

--- Catch-all: removes any hull standing near the player that is not the one
--- the ship is recorded at. The ghost list only knows about hulls this build
--- left behind; this is the only thing that will ever find the others.
--- Deliberately slow and short-ranged -- it is a tidy-up, not a search.
function Core.sweepStrays(player)
    local s = U.state()
    if not player then return 0 end

    local px, py = math.floor(player:getX()), math.floor(player:getY())
    local pz = math.floor(player:getZ())
    if U.isInterior(px, py) then return 0 end

    local removed = 0
    for dx = -STRAY_RADIUS, STRAY_RADIUS do
        for dy = -STRAY_RADIUS, STRAY_RADIUS do
            local x, y = px + dx, py + dy
            local isOurs = s.landed and x == s.x and y == s.y and pz == s.z
            if not isOurs then
                -- Straight at the square rather than through removeHullAt:
                -- the player is standing here, so the chunk check that call
                -- makes would be 441 pointless trips out to Java.
                local sq = U.square(x, y, pz, false)
                local obj = sq and Core.hullOn(sq)
                local isFlightModel = obj and TREK.Flight
                                      and TREK.Flight.isModelObject(obj)
                if obj and not isFlightModel and U.try("removeStray", function()
                    sq:removeWorldObject(obj)
                    return true
                end) then
                    removed = removed + 1
                    U.log("removed a stray hull at %d,%d,%d", x, y, pz)
                end
            end
        end
    end
    return removed
end

---------------------------------------------------------------------------
-- Room to land
---------------------------------------------------------------------------
--- Whether one square could take part of the hull.
---
--- Returns `ok, reason`. The reason names the first thing in the way, and
--- "unloaded" is not one of the others: it means the world has not streamed
--- that ground in and the answer is not knowable yet.
local function squareIsClear(sq)
    if not sq then return false, "unloaded" end
    if U.isInterior(sq:getX(), sq:getY()) then return false, "interior" end

    -- The probe answers "ok" rather than nil for a clear square, because
    -- U.try also returns nil when the call itself failed -- and a probe that
    -- threw must never read as clear ground to land a ship on.
    local why = U.try("squareIsClear", function()
        if not sq:getFloor() then return "void" end
        if sq:isSolid() or sq:isSolidTrans() then return "blocked" end
        if sq:getVehicleContainer() then return "vehicle" end
        if not sq:isFree(false) then return "occupied" end
        return "ok"
    end)
    if why == "ok" then return true, nil end
    return false, why or "engine"
end

--- Is there room to set the shuttle down centred on this square?
---
--- Returns `ok, reason, blocked` -- the reason names what is in the way and
--- `blocked` counts how many of the footprint's squares were no good, which
--- is what turns "you cannot land here" into a message worth reading.
---
--- `exempt` is one square to treat as clear whatever is standing on it, and
--- it is always the square the player who ordered the landing is standing on.
--- Without it nothing ever works: the ship is five tiles long, so anybody
--- calling it down in front of them is inside the footprint, and anybody
--- beamed to a destination for the ship to follow them to is standing in the
--- middle of it. The player is not an obstruction to a landing they asked
--- for; they step aside as it comes in, which Core.land then does for them.
---
--- "unloaded" is reported only when *every* bad square was unloaded. A single
--- wall inside an area that is otherwise still streaming in is a real
--- refusal, and answering "wait and see" to it would leave the landing job
--- retrying against a site that is never going to work.
function Core.roomToLand(cx, cy, z, exempt)
    local blocked, first = 0, nil
    for _, d in ipairs(C.footprintOffsets()) do
        local x, y = cx + d[1], cy + d[2]
        local skip = Core.hullCovers(x, y, z)
                     or (exempt and exempt.x == x and exempt.y == y)
        -- Standing on our own hull is not an obstruction either: recalling the
        -- ship to where it already is must not be refused by the ship itself.
        if not skip then
            local ok, why = squareIsClear(U.square(x, y, z, false))
            if not ok then
                blocked = blocked + 1
                if why ~= "unloaded" and not first then first = why end
            end
        end
    end
    if blocked == 0 then return true, nil, 0 end
    if first then return false, first, blocked end
    return false, "unloaded", blocked
end

--- The square a player is standing on, in the shape Core.roomToLand wants.
function Core.exemptFor(player)
    if not player then return nil end
    return { x = math.floor(player:getX()), y = math.floor(player:getY()) }
end

--- How many squares the footprint needs, for messages and the self-test.
function Core.footprintArea()
    return C.Footprint.w * C.Footprint.h
end

---------------------------------------------------------------------------
-- Landing and recalling
---------------------------------------------------------------------------
--- Sets the shuttle down centred on a square, lifting it from wherever it was
--- before. The same call handles the first landing and every later one.
function Core.land(sq, player)
    if not sq then return false, "unloaded" end
    local x, y, z = sq:getX(), sq:getY(), sq:getZ()

    local ok, why = Core.roomToLand(x, y, z, Core.exemptFor(player))
    if not ok then return false, why end

    local s = U.state()
    if s.landed then
        -- The old hull must go, and "I could not reach it" is not the same as
        -- "it is gone". When its chunk is not loaded -- which is every flight,
        -- since a landing site is nowhere near where the ship was -- write the
        -- position down and clear it when the world catches up.
        local _, gone = Core.removeHullAt(s.x, s.y, s.z)
        if gone == "unloaded" or gone == "failed" then
            Core.forgetHull(s.x, s.y, s.z)
        end
    end

    local placed = U.try("placeHull", function()
        local obj = sq:AddWorldInventoryItem(C.ExteriorItem, 0.5, 0.5, 0.0)
        if obj and obj.setIgnoreRemoveSandbox then
            -- keep the world-item cleanup rules from sweeping the ship away
            obj:setIgnoreRemoveSandbox(true)
        end
        return obj
    end)
    if not placed then return false, "failed" end

    s.landed = true
    s.everLanded = true
    s.x, s.y, s.z = x, y, z
    s.destination = nil

    -- The player was very likely standing inside the footprint -- that is the
    -- exemption above -- so put them at the foot of the ramp rather than
    -- underneath five tiles of hull.
    if player and Core.hullCovers(player:getX(), player:getY(), player:getZ()) then
        local beside = Core.landingBeside(x, y, z)
        if beside then
            U.teleport(player, beside.x, beside.y, beside.z)
            s.returnX, s.returnY, s.returnZ = beside.x, beside.y, beside.z
        end
    end

    U.log("shuttle down at %d,%d,%d", x, y, z)
    return true, nil
end

--- Sends the shuttle back up. It stops being anywhere; the transporter still
--- reaches it, the hatch does not.
function Core.recall()
    local s = U.state()
    if not s.landed then return false end
    local _, why = Core.removeHullAt(s.x, s.y, s.z)
    if why == "unloaded" or why == "failed" then
        Core.forgetHull(s.x, s.y, s.z)
    end
    s.landed = false
    U.log("shuttle recalled from %d,%d,%d", s.x, s.y, s.z)
    return true
end

--- First walkable square beside the landed hull, for stepping out of the
--- hatch. Searched from the stern outward, because that is where the ramp is.
function Core.landingBeside(x, y, z)
    local hh = math.floor((C.Footprint.h - 1) / 2)
    local hw = math.floor((C.Footprint.w - 1) / 2)
    local aft = C.Footprint.h - 1 - hh
    local offsets = {}
    -- the ramp, then the flanks, then anywhere at all
    for dx = -hw, hw do table.insert(offsets, { dx, aft + 1 }) end
    for dy = -hh, aft do
        table.insert(offsets, { -hw - 1, dy })
        table.insert(offsets, { hw + 1, dy })
    end
    for dx = -hw, hw do table.insert(offsets, { dx, -hh - 1 }) end

    for _, o in ipairs(offsets) do
        local sq = U.square(x + o[1], y + o[2], z, false)
        if sq then
            local ok = U.try("landingBeside", function()
                return sq:getFloor() ~= nil and not sq:isSolid() and sq:isFree(false)
            end)
            if ok == true then
                return { x = x + o[1], y = y + o[2], z = z }
            end
        end
    end
    return nil
end

---------------------------------------------------------------------------
-- Arrival: holding the player while the cabin streams in and is built
---------------------------------------------------------------------------
local arrival = nil   -- { x, y, z, tries, player, wasGod, wasNoClip }

local function protect(player, on)
    U.try("protect", function()
        player:setGodMod(on)
        player:setNoClip(on)
        if on then player:setbFalling(false) end
    end)
end

--- Starts an arrival on the transporter pad. When `move` is true the player is
--- teleported there first; when false they are already standing aboard.
function Core.beginArrival(player, move)
    if not player then return false end
    local x, y, z = U.padSpot()

    if arrival then
        arrival.x, arrival.y, arrival.z, arrival.tries = x, y, z, 0
    else
        arrival = {
            x = x, y = y, z = z, tries = 0, player = player,
            wasGod = U.try("wasGod", function() return player:isGodMod() end) == true,
            wasNoClip = U.try("wasNoClip", function() return player:isNoClip() end) == true,
        }
        protect(player, true)
    end

    if move then U.teleport(player, x, y, z) end
    return true
end

local function endArrival(restorePosition)
    if not arrival then return end
    local job = arrival
    local player = job.player
    arrival = nil
    if player then
        U.try("unprotect", function()
            player:setGodMod(job.wasGod == true)
            player:setNoClip(job.wasNoClip == true)
        end)
        if restorePosition then
            U.teleport(player, job.x, job.y, job.z)
        end
    end
end

function Core.arriving()
    return arrival ~= nil
end

--- Runs each tick while an arrival is outstanding: pins the player in place,
--- raises the cabin the moment its chunks appear, then hands control back.
local function serviceArrival()
    if not arrival then return end
    local player = arrival.player
    if not player then arrival = nil return end

    arrival.tries = arrival.tries + 1

    -- Report what the world is doing, so a stall is diagnosable from the log
    -- rather than just looking like a hang.
    if arrival.tries == 1 or arrival.tries == 120 or arrival.tries == 420 then
        U.log("arrival tick %d: pad chunk loaded=%s, cabin ready=%s",
              arrival.tries,
              tostring(U.chunkLoaded(arrival.x, arrival.y, arrival.z)),
              tostring(TREK.Build.cabinReady()))
    end

    -- Hold position so the player cannot drift or drop while waiting.
    U.try("hold", function()
        player:setX(arrival.x + 0.5)
        player:setY(arrival.y + 0.5)
        player:setZ(arrival.z)
        player:setbFalling(false)
    end)

    TREK.Build.ensureCabin()
    if TREK.Build.cabinCurrent() then
        -- Built is not the same as safe: only let go of the player once there
        -- is demonstrably a floor under the pad they are being put down on.
        local pad = U.square(arrival.x, arrival.y, arrival.z, false)
        local floored = pad and U.try("padFloor", function()
            return pad:getFloor() ~= nil
        end) == true
        if not floored then
            if arrival.tries > 180 then
                U.log("cabin built but the pad has no floor; ejecting")
                Core.ejectToOutside("no floor on the transporter pad")
            end
            return
        end
        U.log("materialised on the transporter pad")
        endArrival(true)
        return
    end

    if arrival.tries > ARRIVAL_TIMEOUT then
        Core.ejectToOutside("the cabin failed to stream in")
    end
end

--- Last resort: get the player out of the cabin and back onto real ground.
--- Nothing aboard is worth being stuck in the void for.
function Core.ejectToOutside(why)
    local s = U.state()
    local player = arrival and arrival.player or U.player(0)
    U.log("ejecting to outside: %s", tostring(why))
    endArrival(false)
    if not player then return false end

    local bx, by, bz = s.returnX, s.returnY, s.returnZ
    if not bx and s.landed then bx, by, bz = s.x, s.y, s.z end
    if not bx then return false end
    local target = Core.landingBeside(bx, by, bz) or { x = bx, y = by, z = bz }
    U.teleport(player, target.x, target.y, target.z)
    s.inside = false
    U.note(player, getText("IGUI_TREK_ArrivalFailed"), 255, 90, 90)
    return true
end

---------------------------------------------------------------------------
-- The hatch
---------------------------------------------------------------------------
--- Walks the player up the ramp into the cabin, remembering the way back.
--- Only possible while the ship is on the ground; otherwise it is a beam.
function Core.enter(player)
    if not player then return false end
    local s = U.state()
    if U.isInteriorPlayer(player) then return false end
    if not s.landed then return false end

    s.returnX, s.returnY, s.returnZ = s.x, s.y, s.z
    s.inside = true

    -- Move first, build second: the cabin cannot be raised until the player
    -- standing there has caused its chunks to stream in.
    Core.beginArrival(player, true)
    U.log("boarding through the hatch")
    return true
end

--- Puts the player back down the ramp. Only meaningful when the ship is on
--- the ground -- with the shuttle overhead the way off is the transporter.
function Core.exit(player)
    if not player then return false end
    local s = U.state()
    if not s.landed then return false end
    endArrival(false)

    Core.repelZombies()

    local target = Core.landingBeside(s.x, s.y, s.z) or { x = s.x, y = s.y, z = s.z }
    if not U.teleport(player, target.x, target.y, target.z) then return false end
    s.inside = false
    s.returnX, s.returnY, s.returnZ = target.x, target.y, target.z
    U.log("stepped out at %d,%d,%d", target.x, target.y, target.z)
    return true
end

---------------------------------------------------------------------------
-- Upkeep
---------------------------------------------------------------------------
--- Tops one fixture up, and returns whether it is holding water afterwards.
---
--- Two mechanisms, because build 42 has two and a fixture may use either.
--- A sink's water is *reserve* water -- the waterAmount / waterMaxAmount
--- sprite properties -- reached through getReserveWaterAmount and
--- setReserveWaterAmount. A rain barrel, or anything else carrying a
--- FluidContainer, holds a *fluid* and wants addFluid instead.
---
--- A sink has no FluidContainer at all, so getFluidCapacity returns 0 and the
--- fluid path on its own tops up precisely nothing, without complaining. That
--- is what this function used to do. Both paths run, and then hasWater() is
--- asked, because it is the same question the game asks before it will let
--- anybody drink.
local function refillFixture(o)
    U.try("reserveWater", function()
        local max = o:getReserveWaterMax()
        if max and max > 0 and (o:getReserveWaterAmount() or 0) < max then
            o:setReserveWaterAmount(max)
        end
    end)
    U.try("fluidWater", function()
        local cap = o:getFluidCapacity()
        if cap and cap > 0 then
            local have = o:getFluidAmount() or 0
            if have < cap then o:addFluid(FluidType.Water, cap - have) end
        end
    end)
    return U.try("hasWater", function() return o:hasWater() end) == true
end

-- Where the layout puts plumbed fixtures. Worked out once from the authored
-- interior rather than by sweeping the cabin, so this can run every couple of
-- seconds while somebody is aboard without costing anything.
local waterSpots = nil

local function findWaterSpots()
    if waterSpots then return waterSpots end
    waterSpots = {}
    local ok, L = pcall(require, "TREK/TREK_InteriorLayout")
    if ok and L and L.tiles then
        for _, entry in ipairs(L.tiles) do
            if C.WaterTags[entry.tag] then
                table.insert(waterSpots, { entry.x, entry.y })
            end
        end
    end
    return waterSpots
end

--- The ship's water never runs dry: the galley sink, the head and the shower
--- are kept full. Anything the layout tagged sink, shower or toilet is
--- included, so adding another fixture in BuildingEd needs no change here.
---
--- Returns the number holding water and the number that would not fill.
function Core.refillWater()
    local s = U.state()
    if not s.built then return 0, 0 end
    local wet, dry = 0, 0
    for _, spot in ipairs(findWaterSpots()) do
        local x, y = U.at(spot[1], spot[2])
        local sq = U.square(x, y, C.CabinZ, false)
        if sq then
            U.eachObject(sq, function(o)
                local md = U.try("md", function() return o:getModData() end)
                local tag = md and md.TREK
                if tag and C.WaterTags[tag] then
                    if refillFixture(o) then wet = wet + 1 else dry = dry + 1 end
                end
            end)
        end
    end
    if dry > 0 then
        U.warnOnce("waterDry",
            string.format("%d water fixture(s) will not hold water", dry))
    end
    U.debug("water: %d fixtures full, %d dry", wet, dry)
    return wet, dry
end

--- Exposed for the debug console: TREK_Water()
function TREK_Water()
    local wet, dry = Core.refillWater()
    U.log("water: %d fixtures holding water, %d dry", wet, dry)
    return wet, dry
end

---------------------------------------------------------------------------
-- The field around the hatch
---------------------------------------------------------------------------
--- Pushes the dead back out of a ring around the landed hull, so stepping out
--- is never an ambush and nothing can crowd the ramp while the ship sits
--- there.
---
--- They are shoved to the edge of the field rather than killed: no free
--- experience, no free loot, and they are still waiting when the ship is
--- somewhere else.
function Core.repelZombies()
    local s = U.state()
    if not s.landed then return 0 end
    -- Lowered from the helm. The field is the shields; there is nothing else
    -- to switch off.
    if s.shields == false then return 0 end

    local cell = U.cell()
    if not cell then return 0 end
    local zombies = U.try("getZombieList", function() return cell:getZombieList() end)
    if not zombies then return 0 end

    local n = U.try("zombieCount", function() return zombies:size() end) or 0
    if n == 0 then return 0 end

    local radius = C.FieldRadius
    local pushed = 0
    for i = 0, n - 1 do
        local z = U.try("zombieAt", function() return zombies:get(i) end)
        if z then
            U.try("repel", function()
                if math.floor(z:getZ()) ~= s.z then return end
                local dx, dy = z:getX() - s.x, z:getY() - s.y
                local dist = math.sqrt(dx * dx + dy * dy)
                if dist > radius then return end

                -- straight overhead: pick a direction rather than divide by zero
                if dist < 0.01 then dx, dy, dist = 1, 0, 1 end
                local scale = (radius + 1.5) / dist
                local nx, ny = s.x + dx * scale, s.y + dy * scale

                z:setX(nx) z:setY(ny)
                z:setLastX(nx) z:setLastY(ny)
                z:setTarget(nil)
                z:setStaggerBack(true)
                pushed = pushed + 1
            end)
        end
    end
    if pushed > 0 then U.debug("field pushed back %d zombies", pushed) end
    return pushed
end

---------------------------------------------------------------------------
-- Keeping anyone aboard on solid ground
---------------------------------------------------------------------------
local voidStrikes = 0

local function onPlayerUpdate(player)
    if not player then return end
    if arrival then return end
    if not U.isInteriorPlayer(player) then return end

    if not TREK.Build.cabinCurrent() then
        Core.beginArrival(player, false)
        return
    end

    -- Built, but the player is over a hole with nothing under them.
    local sq = U.square(player:getX(), player:getY(), math.floor(player:getZ()), false)
    if sq and sq:getFloor() then
        voidStrikes = 0
        return
    end

    local x, y, z = U.padSpot()
    local pad = U.square(x, y, z, false)
    if pad and pad:getFloor() then
        voidStrikes = 0
        U.teleport(player, x, y, z)
        return
    end

    -- Nothing under the player and nothing under the pad either: the cabin is
    -- not habitable, so stop shuffling them around inside it.
    voidStrikes = voidStrikes + 1
    if voidStrikes >= 5 then
        voidStrikes = 0
        Core.ejectToOutside("the cabin has no floor to stand on")
    end
end

Events.OnTick.Add(serviceArrival)
Events.EveryTenMinutes.Add(Core.refillWater)

local rescueTick, fieldTick, ghostTick, strayTick, voidTick = 0, 0, 0, 0, 0
local waterTick = 0
Events.OnPlayerUpdate.Add(function(player)
    rescueTick = rescueTick + 1
    if rescueTick >= 10 then
        rescueTick = 0
        onPlayerUpdate(player)
    end
    -- The field runs whether or not anyone is aboard, so the ramp stays clear
    -- and nothing gathers around the ship while it is parked.
    -- Nearby wilderness chunks may stream after the initial cabin build.
    -- Sweep them again while aboard so late trees cannot remain visible.
    voidTick = voidTick + 1
    if voidTick >= 180 then
        voidTick = 0
        if U.isInteriorPlayer(player) then
            TREK.Build.clearLoadedSurroundings()
        end
    end

    -- Water, while somebody is aboard to use it. The ten-minute timer keeps
    -- the fixtures full the rest of the time; this is what makes them
    -- impossible to drain while you are standing at them. It visits only the
    -- squares the layout puts fixtures on, so it is a handful of lookups.
    waterTick = waterTick + 1
    if waterTick >= C.WaterInterval then
        waterTick = 0
        if U.isInteriorPlayer(player) then Core.refillWater() end
    end

    fieldTick = fieldTick + 1
    if fieldTick >= 20 then
        fieldTick = 0
        Core.repelZombies()
    end

    -- Sweeping up old hulls. The ghost list is cheap and checked often, so a
    -- hull the ship flew away from goes the moment the player is near enough
    -- for its chunk to load. The stray sweep walks squares, so it is rare.
    ghostTick = ghostTick + 1
    if ghostTick >= 30 then
        ghostTick = 0
        Core.sweepGhosts()
    end
    strayTick = strayTick + 1
    if strayTick >= 300 then
        strayTick = 0
        Core.sweepStrays(player)
    end
end)

--- Exposed for the debug console: TREK_Ghosts()
function TREK_Ghosts()
    local s = U.state()
    U.log("ghosts: %d hull(s) pending removal", #s.ghosts)
    for _, g in ipairs(s.ghosts) do
        U.log("  %d,%d,%d  chunk loaded=%s", g.x, g.y, g.z,
              tostring(U.chunkLoaded(g.x, g.y, g.z)))
    end
    local cleared = Core.sweepGhosts()
    local strays = Core.sweepStrays(U.player(0))
    U.log("ghosts: cleared %d, plus %d stray(s) near you; %d still pending",
          cleared, strays, #s.ghosts)
    return cleared + strays
end

--- Exposed for the debug console: TREK_Room()
---
--- Reports whether the shuttle could set down where you are standing, and if
--- not, what is in the way and how many of its squares are blocked. Stand
--- somewhere it refuses to land and run this.
function TREK_Room()
    local player = U.player(0)
    if not player then return false end
    local x, y = math.floor(player:getX()), math.floor(player:getY())
    local z = math.floor(player:getZ())
    local ok, why, blocked = Core.roomToLand(x, y, z, Core.exemptFor(player))
    U.log("room to land at %d,%d,%d: %s (needs %d squares, %d blocked%s)",
          x, y, z, ok and "yes" or "no", Core.footprintArea(), blocked,
          why and (", first: " .. why) or "")
    return ok
end

return Core
