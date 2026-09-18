--[[ Shuttlecraft -- the sky plane the shuttle flies on.

    The shuttle does not hover. It *drives*, on an invisible floor this file
    lays at altitude, because that is the only thing build 42 permits.

    BaseVehicle.update() zeroes a vehicle's z every tick and only restores its
    physics level if a floor tile exists under the vehicle's centre square.
    Lift the physics body without one and the ship flies in Bullet and sits on
    the ground in the game -- drawn on the road, ploughing through fences, and
    at z 0 on every other player's screen. Lay a floor and all of it comes
    right at once: the height is real, the crew are drawn beside the pilot,
    collision happens at the flight level so a two-storey building is passed
    over rather than demolished, and the wheels have something to rest on, so
    the engine drives the ship and nothing here fights gravity.

    The tile is vanilla: invisible_01_0, whose only two properties are
    attachedFloor and solidfloor.

    Why a client lays it, when MULTIPLAYER.md says a client never edits the
    world. The plane is not the ship and it is not state: it is scenery and
    local physics, the same class as the cabin's lights and the powered squares
    in TREK_Core.lightCabin, which each client also makes for itself. The
    server runs no vehicle physics at all in build 42 -- it is a relay -- so it
    has no use for a floor. The driver's client needs one to drive on and every
    client needs one to draw the ship in the air, and all of them derive it
    from the same synced vehicle position, so they agree without a single
    packet crossing the network. It is only ever this one sprite, only ever
    above the ground, and it is always taken up again.

    Three things it does carefully, each of them paid for by an older mistake:

      * it is sliced. A thousand addFloor calls in one frame is the hard lock
        in DEV_GUIDE.md under "Slice any search that touches thousands of
        squares";
      * it is batched, not tried. U.try silences the Lua warning and lets the
        engine keep dumping a Java stack trace per square; U.batch stops;
      * a tile it cannot lift is written down and lifted later. A square whose
        chunk has unloaded cannot answer yet, and reading that as "gone" would
        leave a permanent invisible platform in the sky -- the same mistake
        that once left a police box everywhere the TARDIS had ever been.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local Sky = {}
TREK.Sky = Sky

Sky.TILE = C.SkyTile

-- key -> { x, y, z, native }. `native` marks a square that already had a floor
-- of its own: it is remembered so the plane knows to leave it alone, and never
-- removed, or flying over a tower block would take its roof off.
local laid = {}
local count = 0

-- Squares that could not be lifted because their chunk had gone. Retried.
local pending = {}

-- The paving job: where the plane is centred and how far round it has got.
local job = nil

Sky.stats = { laid = 0, native = 0, lifted = 0, failed = 0, passes = 0 }

local function key(x, y, z)
    return x .. ":" .. y .. ":" .. z
end

---------------------------------------------------------------------------
-- Where the plane goes
---------------------------------------------------------------------------
-- Offsets from the ship, nearest first, built once. This is walked every tick
-- while flying, so it must not allocate -- the same reasoning that memoised
-- C.footprintOffsets() for the landing search.
local order = nil

local function offsets()
    if order then return order end
    local out = {}
    for r = 0, C.SkyRadius do
        for dx = -r, r do
            for dy = -r, r do
                if math.max(math.abs(dx), math.abs(dy)) == r then
                    table.insert(out, { dx, dy })
                end
            end
        end
    end
    order = out
    return out
end

--- How many squares a full pass covers.
function Sky.area()
    return #offsets()
end

---------------------------------------------------------------------------
-- Laying and lifting
---------------------------------------------------------------------------
--- Puts one square of floor down, unless something is already there.
local function layOne(x, y, z, place)
    local k = key(x, y, z)
    if laid[k] then return false end

    -- create=true, but U.square hands back nil rather than an orphan when the
    -- chunk is not loaded, so this simply waits for the ground to stream in.
    local sq = U.square(x, y, z, true)
    if not sq then return false end

    local floor = U.try("skyFloor", function() return sq:getFloor() end)
    if floor then
        -- A real floor: an upper storey the ship is flying level with. It does
        -- the same job and must never be taken up.
        laid[k] = { x = x, y = y, z = z, native = true }
        count = count + 1
        Sky.stats.native = Sky.stats.native + 1
        return true
    end

    -- The batched call must hand something back: U.batch returns nil for a
    -- failure, and a function that returns nothing is indistinguishable from
    -- one that threw.
    local ok = place(function() sq:addFloor(Sky.TILE) return true end)
    if not ok then
        Sky.stats.failed = Sky.stats.failed + 1
        return false
    end
    laid[k] = { x = x, y = y, z = z }
    count = count + 1
    Sky.stats.laid = Sky.stats.laid + 1
    return true
end

--- Takes one square of floor up. Returns true when it is dealt with, false
--- when the answer is not knowable yet.
local function liftOne(t, take)
    if t.native then return true end
    local sq = U.square(t.x, t.y, t.z, false)
    if not sq then return false end       -- chunk gone: not "absent", "unknown"
    local obj = U.findSprite(sq, Sky.TILE)
    if not obj then return true end       -- already gone
    local ok = take(function()
        sq:RemoveTileObjectErosionNoRecalc(obj)
        return true
    end)
    if not ok then return false end
    Sky.stats.lifted = Sky.stats.lifted + 1
    return true
end

---------------------------------------------------------------------------
-- The plane
---------------------------------------------------------------------------
--- Centres the plane on a square at a level. Cheap to call every tick: it
--- only restarts the pass when the ship has actually moved.
function Sky.pave(cx, cy, level)
    cx, cy, level = math.floor(cx), math.floor(cy), math.floor(level)
    if level < C.FlightMinLevel then return end
    if job and job.x == cx and job.y == cy and job.level == level then return end
    job = { x = cx, y = cy, level = level, cursor = 0 }
end

--- Lays the next slice, and chases anything still waiting to be lifted.
---
--- The retry comes first, and runs whether or not there is anything to pave.
--- A tile whose chunk had gone when the plane was taken up goes on the pending
--- list, and that list used to be walked only while a paving job existed --
--- which is to say only while flying. So the squares left over from a landing
--- were never revisited and stayed as invisible floors in the sky: the
--- "random ghost patches" seen in game. They are lifted now the moment their
--- ground comes back, flying or not.
function Sky.service()
    if #pending > 0 then
        local take = U.batch("sky.removeFloor")
        for i = #pending, 1, -1 do
            if liftOne(pending[i], take) then table.remove(pending, i) end
        end
    end

    if not job then return end
    local list = offsets()
    local place = U.batch("sky.addFloor")
    local done = 0

    while done < C.SkyTilesPerTick do
        job.cursor = job.cursor + 1
        if job.cursor > #list then
            job.cursor = #list          -- the pass is complete; hold here
            Sky.stats.passes = Sky.stats.passes + 1
            break
        end
        local d = list[job.cursor]
        layOne(job.x + d[1], job.y + d[2], job.level, place)
        done = done + 1
    end

    -- Every pass, not only when some ceiling is hit. The plane is a patch that
    -- travels with the ship: anything she has left behind is lifted at once,
    -- so the darkness a floor casts over the ground moves with her instead of
    -- being painted across the county.
    Sky.trim()
end

-- The level the ship is *actually* on, which is not always the level it has
-- been told to fly at. Changing altitude means there are briefly two planes,
-- and the old one is what she is still standing on.
local keepAlso = nil

--- Says which level must not be lifted whatever else happens: the one holding
--- the ship up this instant.
function Sky.keep(level)
    keepAlso = level
end

--- Lifts the squares the ship has left behind.
---
--- It must never lift the floor under the ship. Climbing sets the target level
--- and the very next pass used to take up every tile at the old one -- the
--- plane she was resting on -- before the new one existed or she had been
--- raised onto it, so she fell out of the sky the moment the pilot asked to go
--- higher, and once landed in a building. Seen in game, 2026-09-17 20:12:06.
function Sky.trim()
    if not job then return end
    local take = U.batch("sky.removeFloor")
    local limit = C.SkyRadius + C.SkyTrailMargin
    for k, t in pairs(laid) do
        local wrongLevel = t.z ~= job.level and t.z ~= keepAlso
        if wrongLevel
           or math.abs(t.x - job.x) > limit or math.abs(t.y - job.y) > limit then
            if liftOne(t, take) then
                laid[k] = nil
                count = count - 1
            else
                table.insert(pending, t)
                laid[k] = nil
                count = count - 1
            end
        end
    end
end

--- Takes the whole plane up. Every way flight ends comes through here.
function Sky.clear()
    local take = U.batch("sky.removeFloor")
    local left = 0
    for k, t in pairs(laid) do
        if liftOne(t, take) then
            laid[k] = nil
        else
            table.insert(pending, t)
            laid[k] = nil
            left = left + 1
        end
    end
    count = 0
    job = nil
    if left > 0 then
        U.log("sky plane: %d square(s) could not be lifted yet and will be " ..
              "cleared when their ground next loads", left)
    end
end

--- What the plane cost. Logged by itself -- nothing here needs a console.
function Sky.report(why)
    U.log("sky plane (%s): %d square(s) held, %d laid, %d already floored, " ..
          "%d lifted, %d outstanding, %d failed, %d full pass(es) of %d",
          tostring(why), count, Sky.stats.laid, Sky.stats.native,
          Sky.stats.lifted, #pending, Sky.stats.failed, Sky.stats.passes,
          Sky.area())
end

---------------------------------------------------------------------------
-- Clearing up after a flight that ended badly
---------------------------------------------------------------------------
--- Lifts this mod's tile from every level above the ground in a patch, a
--- slice at a time. Returns true when the patch is finished.
---
--- A floor is a world object on a square and squares are saved, so a flight
--- that ended in a crash or a kill rather than a landing would otherwise leave
--- an invisible platform in the sky for the life of the world. The ship state
--- writes down where the plane was; this is how it gets taken up again, by
--- whoever next loads that ground.
function Sky.sweepArea(cx, cy, job)
    local list = offsets()
    local take = U.batch("sky.removeFloor")
    local done = 0
    local levels = C.FlightMaxLevel - C.FlightMinLevel + 1

    while done < C.SkyTilesPerTick do
        job.cursor = (job.cursor or 0) + 1
        if job.cursor > #list * levels then return true end
        local i = ((job.cursor - 1) % #list) + 1
        local level = C.FlightMinLevel + math.floor((job.cursor - 1) / #list)
        local d = list[i]
        local x, y = math.floor(cx) + d[1], math.floor(cy) + d[2]
        local sq = U.square(x, y, level, false)
        if sq then
            local obj = U.findSprite(sq, Sky.TILE)
            if obj then
                take(function()
                    sq:RemoveTileObjectErosionNoRecalc(obj)
                    return true
                end)
                Sky.stats.lifted = Sky.stats.lifted + 1
            end
        end
        done = done + 1
    end
    return false
end

--- True when the ship's own square has floor under it -- the one square that
--- decides whether the engine will accept the height at all.
function Sky.holds(x, y, level)
    local sq = U.square(x, y, level, false)
    if not sq then return false end
    return U.try("skyHolds", function() return sq:getFloor() ~= nil end) == true
end

function Sky.count()
    return count
end

function Sky.outstanding()
    return #pending
end

return Sky
