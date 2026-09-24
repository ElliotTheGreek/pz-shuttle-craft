--[[ Shuttlecraft -- the transporter.

    Beaming is the shuttle's own trick and works wherever the ship is: landed,
    or overhead. It is the one way aboard that needs no clear ground.

    A beam moves this client's own character, which only this client can do
    for an ordinary player. It asks the server first (Core.requestMove):
    on a server with the speed anti-cheat on, every beam is rationed, and a
    refused one is explained ("the transporter is recharging") instead of the
    server kicking the player.

    A beam is two stages: the request, then a short delay while the player
    dematerialises -- an instant snap reads as a debug teleport -- then the
    move. Beaming down waits a little longer if the ground there has not
    streamed in yet.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Ship"
require "TREK/TREK_World"
require "TREK/TREK_Vehicle"
require "TREK/TREK_Core"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Ship = TREK.Ship
local W = TREK.World
local Core = TREK.Core

local T = {}
TREK.Transport = T

-- The beam in progress, if any. One at a time; beams are per local player,
-- and split-screen players wait for each other rather than share a pad.
T.pending = nil

--- Kept for anything that still calls it through the transporter.
T.spotNear = W.spotNear

local function begin(player, dir, x, y, z)
    T.pending = { dir = dir, tries = 0, player = player, x = x, y = y, z = z }
    -- The beam's own note carries what it cost the ship, when the server
    -- said: this is the "Energizing (25 power)" the ledger would otherwise
    -- send, and a halo note holds one line.
    local cost = Core.grantedCost
    U.note(player, cost and getText("IGUI_TREK_Energizing", tostring(math.floor(cost)))
                        or getText("IGUI_TREK_Energising"))
end

local function busy()
    return T.pending ~= nil or Core.moveWaiting()
end

--- Beams the player up to the transporter pad from wherever they are.
---
--- Where they were is written down when the beam goes: that is what "beam me
--- back" means later. It is kept on the character, not the ship -- in a crew
--- of four, each of them came from somewhere different.
function T.beamUp(player)
    if not player then return false, "no player" end
    if U.isInteriorPlayer(player) then return false, "aboard" end
    if busy() then return false, "busy" end

    Core.requestMove(player, "beamUp", function(p)
        -- Beaming up abandons a landing in progress, or both would run.
        if TREK.Travel and TREK.Travel.pending then
            TREK.Travel.pending = nil
            U.log("beam up cancelled the landing in progress")
        end
        Ship.setReturnPoint(p, p:getX(), p:getY(), p:getZ())
        begin(p, "up")
        U.log("beaming up from %d,%d,%d", math.floor(p:getX()),
              math.floor(p:getY()), math.floor(p:getZ()))
    end)
    return true
end

--- True for somebody sitting in the shuttle's cockpit rather than in the
--- cabin. A pilot is "aboard" as far as beaming is concerned: while the ship
--- is flying it is the only way out of the seat that does not involve
--- stepping into open air.
local function inCockpit(player)
    return TREK.Vehicle ~= nil and TREK.Vehicle.isShuttle(
        U.try("playerVehicle", function() return player:getVehicle() end))
end

--- Beams the player down. With no destination this is the return trip to
--- wherever they beamed up from; with one it is a landing party.
function T.beamDown(player, dest)
    if not player then return false, "no player" end
    if not U.isInteriorPlayer(player) and not inCockpit(player) then
        return false, "not aboard"
    end
    if busy() then return false, "busy" end

    local x, y, z
    if dest then
        x, y, z = dest.x, dest.y, dest.z or 0
    else
        x, y, z = Ship.returnPoint(player)
        local s = Ship.get()
        -- From the cockpit the way down is the ground below the ship, not
        -- wherever this character last beamed up from -- and beside her rather
        -- than under her. Directly underneath is where the hull stands when
        -- she is down, and where her own floor casts its shadow when she is
        -- up, so a beam to that square arrives either inside the ship or in
        -- the dark.
        if inCockpit(player) and s.landed then
            local beside = W.clearOfShip(s.x, s.y, s.z)
            if beside then
                x, y, z = beside.x, beside.y, beside.z
            else
                x, y, z = s.x, s.y + 4, s.z
            end
        end
        if not x and s.landed then x, y, z = s.x, s.y, s.z end
    end
    if not x then return false, "nowhere" end
    x, y, z = math.floor(x), math.floor(y), math.floor(z)

    Core.requestMove(player, "beamDown", function(p)
        -- The seat is not left until the last moment. A beam takes a second
        -- and a half, and stepping out of a flying ship at the start of it
        -- leaves the character standing on a five-by-five island of invisible
        -- floor three levels up -- where the engine draws that level and culls
        -- everything under it, so the whole world goes black until they
        -- rematerialise. Staying in the seat keeps the view normal and the
        -- character supported; the way out happens in finishDown, one tick
        -- before they arrive. Seen in game.
        begin(p, "down", x, y, z)
        U.log("beaming down to %d,%d", x, y)
    end)
    return true
end

--- Beams the player from the cabin back to the cockpit.
---
--- Without this, going aft in flight is a one-way door: the hatch is shut
--- while she hovers, *Step outside* is hidden for the same reason, and the
--- aboard menu's only other way off her is a beam down -- which now sends her
--- back up as soon as the last of the crew has gone. A pilot who stepped
--- through to read the helm could never fly her again. Reported from the game
--- as "we cannot get back in the craft".
---
--- It arrives on the **ground beneath her**, not on the sky plane beside her.
--- That is the whole safety of it: the ground is real ground, so a shuttle
--- that never streams in leaves the player standing somewhere rather than on
--- a five-by-five island of invisible floor with the engine culling
--- everything below it. `vehicle:enter(seat, character)` is vanilla's own
--- call (`ISEnterVehicle.lua:50`) and the distance check lives in the action
--- rather than in the method, so the engine will take them from there.
function T.toCockpit(player)
    if not player then return false, "no player" end
    if not U.isInteriorPlayer(player) then return false, "not aboard" end
    if busy() then return false, "busy" end
    local s = Ship.get()
    -- In flight, or on the ground. Overhead there are no seats anywhere near
    -- to go to: she is not a vehicle in the world at all.
    local grounded = s.landed == true and not s.flying
    if not s.flying and not grounded then return false, "notLanded" end

    Core.requestMove(player, "beamUp", function(p)
        -- **Where they arrive is the one difference.** In flight it is the
        -- ground beneath her, because that is real ground under a ship three
        -- metres up. On the ground that square *is* her hull -- a player put
        -- there stands inside a vehicle while it streams in -- so they arrive
        -- where stepping out through the hatch puts people, clear of her,
        -- and the seat takes them from there (vehicle:enter has no distance
        -- check; the distance check lives in vanilla's action).
        local y = math.floor(s.y)
        if grounded then y = y + Core.STEP_OUT_OFFSET end
        begin(p, "cockpit", math.floor(s.x), y, math.floor(s.z))
        U.log("beaming forward to the cockpit at %d,%d (%s)", s.x, s.y,
              grounded and "on the ground" or "in flight")
    end)
    return true
end

--- The first seat nobody is in, the driver's for preference.
local function freeSeat(vehicle)
    local n = U.try("maxPassengers", function()
        return vehicle:getMaxPassengers()
    end) or 0
    for seat = 0, n - 1 do
        local taken = U.try("seatCharacter", function()
            return vehicle:getCharacter(seat)
        end)
        if not taken then return seat end
    end
    return nil
end

--- Beams the player straight back aboard after a landing with no room. The
--- charge for this was held back when the landing was asked for.
function T.recoverAboard(player, message)
    if not player then return false end
    T.pending = nil
    Core.requestMove(player, "recover", function(p)
        Core.beginArrival(p, true)
        if message then U.note(p, message, 255, 170, 90) end
    end)
    return true
end

---------------------------------------------------------------------------
-- Servicing a beam
---------------------------------------------------------------------------
--- Materialises the player at the target, then settles them on the nearest
--- clear square.
---
--- In that order, because the ground far from the ship is not loaded -- not
--- on this client, not on the server -- until a player stands there. Looking
--- for a clear square first finds nothing and the beam fails. The settling
--- step is a short move within sight, not a second long jump.
local function finishDown(job)
    local player = job.player
    if not job.arrived then
        -- Out of the seat now, not when the beam was asked for: the engine
        -- otherwise believes the character is still riding and puts them back
        -- in. vehicle:exit is what vanilla's own ISExitVehicle action calls.
        Core.leaveSeat(player)
        U.teleport(player, job.x, job.y, job.z)
        Ship.playerData(player).aboard = false
        job.arrived = true
        job.arrivedAt = job.tries
        return false
    end

    local spot = W.spotNear(job.x, job.y, job.z)
    if not spot then
        -- The ground is still streaming in; hold the player still meanwhile.
        if job.tries - job.arrivedAt < 300 then
            Core.hold(player, job.x, job.y, job.z)
            return false
        end
        U.note(player, getText("IGUI_TREK_NoBeamSite"), 255, 90, 90)
        U.log("no clear ground to beam down to near %d,%d", job.x, job.y)
        spot = { x = job.x, y = job.y, z = job.z }
    end
    U.teleport(player, spot.x, spot.y, spot.z)
    Ship.setReturnPoint(player, spot.x, spot.y, spot.z)
    U.log("materialised at %d,%d,%d", spot.x, spot.y, spot.z)
    return true
end

--- Materialises the player on the ground under the hovering ship, waits for
--- her to stream in, and puts them in a seat.
---
--- Two stages, for the same reason a beam down has two: the ground under her
--- is not loaded -- on this client or on the server -- until somebody is
--- standing on it, and neither is she. Held still meanwhile, because the
--- engine carries its own fall state through a move.
local function finishCockpit(job)
    local p = job.player
    if not job.arrived then
        U.teleport(p, job.x, job.y, job.z)
        Ship.playerData(p).aboard = false
        job.arrived = true
        job.arrivedAt = job.tries
        return false
    end

    local vehicle = TREK.Vehicle and TREK.Vehicle.ship()
    if not vehicle then
        if job.tries - job.arrivedAt < 300 then
            Core.hold(p, job.x, job.y, job.z)
            return false
        end
        -- She has gone, or her ground will not load. They are on real ground
        -- under where she was, which is the safe half of this, and they are
        -- told -- a beam that ends in silence is indistinguishable from one
        -- that never happened.
        Ship.setReturnPoint(p, job.x, job.y, job.z)
        U.note(p, getText("IGUI_TREK_NoCockpit"), 255, 90, 90)
        U.log("the shuttle never streamed in at %d,%d; left standing there",
              job.x, job.y)
        return true
    end

    local seat = freeSeat(vehicle)
    if not seat then
        Ship.setReturnPoint(p, job.x, job.y, job.z)
        U.note(p, getText("IGUI_TREK_CockpitFull"), 255, 170, 90)
        U.log("no free seat in the shuttle; left standing underneath her")
        return true
    end
    U.try("vehicleEnter", function() vehicle:enter(seat, p) end)
    U.log("materialised in the cockpit, seat %d", seat)
    return true
end

local function serviceBeam()
    local job = T.pending
    if not job then return end
    if not job.player then T.pending = nil return end

    job.tries = job.tries + 1
    if job.tries < C.BeamDelay then return end

    if job.dir == "down" then
        -- A beam-down still waiting for its ground keeps the job alive.
        if finishDown(job) then T.pending = nil end
        return
    end

    if job.dir == "cockpit" then
        if finishCockpit(job) then T.pending = nil end
        return
    end

    -- Out of the seat before the arrival, for the same reason finishDown does
    -- it on the way out -- and this half was missing, which cost a session.
    --
    -- A pilot who beams up is still, as far as the engine is concerned, riding
    -- the shuttle: `player:getVehicle()` keeps returning her. The character is
    -- then put down in the cabin's cell, the shuttle's chunk unloads behind
    -- them, and every part of that vehicle is left with a null back-reference.
    -- Vanilla's own inventory window takes the `elseif playerObj:getVehicle()`
    -- branch of ISInventoryPage.refreshBackpacks, walks those parts, and
    -- `ItemContainer.isOccupiedVehicleSeat` throws on each one -- in
    -- `prerender`, which is every frame. 829 stack traces in one short
    -- session, the game unresponsive, and no way into the interior: DEV_GUIDE's
    -- "black screen, character falling, game unresponsive" signature exactly.
    --
    -- Nothing in the mod's own Lua appears in that stack trace, which is what
    -- made it look like a vanilla fault rather than a missing line here.
    if Core.leaveSeat(job.player) then
        U.log("left the cockpit on beaming up")
    end

    T.pending = nil
    Core.beginArrival(job.player, true)
    U.log("materialised aboard")
end

Events.OnTick.Add(serviceBeam)

--- Exposed for the debug console: TREK_Beam()
--- Beams you up if you are outside and back down if you are aboard.
function TREK_Beam()
    local player = U.player(0)
    if not player then return false end
    if U.isInteriorPlayer(player) then
        local ok, why = T.beamDown(player)
        U.log("beam down: %s%s", tostring(ok), why and (" (" .. why .. ")") or "")
        return ok
    end
    local ok, why = T.beamUp(player)
    U.log("beam up: %s%s", tostring(ok), why and (" (" .. why .. ")") or "")
    return ok
end

return T
