--[[ Shuttlecraft -- the transporter.

    The transporter is the shuttle's own trick and the reason this mod is not
    just a TARDIS with different paint. There is no door to walk to: from
    anywhere in the world you beam up to the pad, and from the pad you beam
    back down to where you were standing or to anywhere a course has been set
    for.

    It deliberately does not care whether the ship is on the ground. When the
    shuttle is not landed it is overhead, which is not a position at all, and
    the pad reaches you either way. The hatch is the part that needs the ship
    to be sitting somewhere.

    Two things shape how this is written.

    A beam is a two-stage job, not a teleport. An instant snap reads as a
    debug command; a second and a half of dematerialising reads as a
    transporter and gives the halo note time to be seen. So a beam is a
    pending record serviced on a tick, in the same shape as the landing job in
    TREK_Travel.

    And a beam-down has to land somewhere a person can stand. The square you
    left may have a zombie on it by the time you come back, so the arrival
    spirals outward from the target and gives up rather than putting anybody
    inside a wall.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local T = {}
TREK.Transport = T

-- The beam in progress, if any:
--   { dir = "up"|"down", tries, player, x, y, z }
-- Only one at a time; asking for another replaces it.
T.pending = nil

---------------------------------------------------------------------------
-- Where a beam can put somebody down
---------------------------------------------------------------------------
--- Squares in rings outward from a centre, nearest first.
local function spiral(cx, cy, radius)
    local out = {}
    for r = 0, radius do
        for dx = -r, r do
            for dy = -r, r do
                if math.max(math.abs(dx), math.abs(dy)) == r then
                    table.insert(out, { x = cx + dx, y = cy + dy })
                end
            end
        end
    end
    return out
end

--- A square a person can stand on at or near a target, or nil.
---
--- One person needs one square, which is the whole difference between this
--- and Core.roomToLand: the ship needs its whole footprint, a crewman needs
--- somewhere to put their feet.
function T.spotNear(cx, cy, z, radius)
    for _, p in ipairs(spiral(cx, cy, radius or C.BeamScatter)) do
        local sq = U.square(p.x, p.y, z, false)
        if sq then
            local ok = U.try("beamSpot", function()
                if not sq:getFloor() then return false end
                if sq:isSolid() or sq:isSolidTrans() then return false end
                if not sq:isFree(false) then return false end
                return true
            end)
            if ok == true then return { x = p.x, y = p.y, z = z } end
        end
    end
    return nil
end

---------------------------------------------------------------------------
-- Starting a beam
---------------------------------------------------------------------------
local function begin(player, dir, x, y, z)
    T.pending = {
        dir = dir, tries = 0, player = player,
        x = x, y = y, z = z,
    }
end

--- Beams the player up to the transporter pad from wherever they are.
---
--- Where they were is written down first: that is what "beam me back" means
--- later, and it is recorded here rather than at beam-down time so that a
--- player who wanders around the cabin still returns to the spot they left.
function T.beamUp(player)
    if not player then return false, "no player" end
    if U.isInteriorPlayer(player) then return false, "aboard" end
    if T.pending then return false, "busy" end

    -- Beaming up abandons a landing in progress. Otherwise both jobs run:
    -- the ship comes down at the destination and immediately teleports the
    -- player back out of the cabin to stand beside it.
    if TREK.Travel and TREK.Travel.pending then
        TREK.Travel.pending = nil
        U.log("beam up cancelled the landing in progress")
    end

    local s = U.state()
    s.returnX = math.floor(player:getX())
    s.returnY = math.floor(player:getY())
    s.returnZ = math.floor(player:getZ())

    begin(player, "up")
    U.note(player, getText("IGUI_TREK_Energising"))
    U.log("beaming up from %d,%d,%d", s.returnX, s.returnY, s.returnZ)
    return true
end

--- Beams the player down. With no destination this is the return trip to
--- wherever they beamed up from; with one it is a landing party anywhere on
--- the map.
function T.beamDown(player, dest)
    if not player then return false, "no player" end
    if not U.isInteriorPlayer(player) then return false, "not aboard" end
    if T.pending then return false, "busy" end

    local s = U.state()
    local x, y, z
    if dest then
        x, y, z = dest.x, dest.y, dest.z or 0
    elseif s.returnX then
        x, y, z = s.returnX, s.returnY, s.returnZ
    elseif s.landed then
        x, y, z = s.x, s.y, s.z
    else
        return false, "nowhere"
    end

    begin(player, "down", math.floor(x), math.floor(y), math.floor(z))
    U.note(player, getText("IGUI_TREK_Energising"))
    U.log("beaming down to %d,%d", x, y)
    return true
end

--- Beams the player up with no ceremony and no delay.
---
--- The recovery path, used when a landing has failed and the player is
--- standing on ground the ship could not reach. They are already committed to
--- being aboard by then, so there is nothing to announce and no reason to
--- make them wait through it again.
function T.recoverAboard(player, message)
    if not player then return false end
    T.pending = nil
    local s = U.state()
    s.inside = true
    TREK.Core.beginArrival(player, true)
    if message then U.note(player, message, 255, 170, 90) end
    return true
end

---------------------------------------------------------------------------
-- Servicing a beam
---------------------------------------------------------------------------
local function finishUp(job)
    local s = U.state()
    s.inside = true
    -- Core owns arrival: it holds the player on the pad, unfalling and
    -- unhurt, and raises the cabin the moment its chunks stream in.
    TREK.Core.beginArrival(job.player, true)
    U.log("materialised aboard")
end

local function finishDown(job)
    local player = job.player
    local s = U.state()

    local spot = T.spotNear(job.x, job.y, job.z)
    if not spot then
        -- The world may simply not have streamed that ground in yet, which is
        -- the normal case for anywhere the player has not just come from. Keep
        -- trying for a few seconds before admitting it cannot be done.
        if job.tries < C.BeamDelay + 300 then return false end
        T.pending = nil
        U.note(player, getText("IGUI_TREK_NoBeamSite"), 255, 90, 90)
        U.log("no clear ground to beam down to near %d,%d", job.x, job.y)
        return true
    end

    U.teleport(player, spot.x, spot.y, spot.z)
    s.inside = false
    s.returnX, s.returnY, s.returnZ = spot.x, spot.y, spot.z
    U.log("materialised at %d,%d,%d", spot.x, spot.y, spot.z)
    return true
end

--- Runs once a tick while a beam is outstanding.
local function serviceBeam()
    local job = T.pending
    if not job then return end
    if not job.player then T.pending = nil return end

    job.tries = job.tries + 1
    if job.tries < C.BeamDelay then return end

    -- A beam-down that is still waiting for its ground to load keeps the job
    -- alive; everything else is done in one step.
    if job.dir == "down" then
        if finishDown(job) then T.pending = nil end
        return
    end

    T.pending = nil
    finishUp(job)
end

Events.OnTick.Add(serviceBeam)

--- Exposed for the debug console: TREK_Beam()
---
--- Beams you up if you are outside and back down if you are aboard, so the
--- round trip can be exercised without going through the menus.
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
