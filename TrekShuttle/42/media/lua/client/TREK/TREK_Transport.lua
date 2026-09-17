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
    U.note(player, getText("IGUI_TREK_Energising"))
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

--- Beams the player down. With no destination this is the return trip to
--- wherever they beamed up from; with one it is a landing party.
function T.beamDown(player, dest)
    if not player then return false, "no player" end
    if not U.isInteriorPlayer(player) then return false, "not aboard" end
    if busy() then return false, "busy" end

    local x, y, z
    if dest then
        x, y, z = dest.x, dest.y, dest.z or 0
    else
        x, y, z = Ship.returnPoint(player)
        local s = Ship.get()
        if not x and s.landed then x, y, z = s.x, s.y, s.z end
    end
    if not x then return false, "nowhere" end
    x, y, z = math.floor(x), math.floor(y), math.floor(z)

    Core.requestMove(player, "beamDown", function(p)
        begin(p, "down", x, y, z)
        U.log("beaming down to %d,%d", x, y)
    end)
    return true
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
            U.try("holdBeam", function()
                player:setbFalling(false)
                player:setFallTime(0)
            end)
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
