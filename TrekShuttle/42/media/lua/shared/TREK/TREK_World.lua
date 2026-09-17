--[[ Shuttlecraft -- reading the world: is there room, where can a person stand.

    Nothing in this file changes the world. It is shared because both sides
    ask the same questions for different reasons:

      * a client searches for a landing site near where its player is standing
        -- only the ground around a player is loaded, on any machine;
      * the server asks again before it places the hull, against its own copy
        of the world, and refuses if the answer has changed. A client's "there
        is room here" is a request, never a fact.

    Every probe answers with a reason, and "unloaded" is never folded into a
    real refusal: it means the ground has not streamed in and the answer is not
    knowable yet.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local W = {}
TREK.World = W

---------------------------------------------------------------------------
-- The hull on the map
---------------------------------------------------------------------------
--- The world item that represents the hull on a square, if it is there.
function W.hullOn(sq)
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
function W.hullCovers(x, y, z)
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

---------------------------------------------------------------------------
-- Room to land
---------------------------------------------------------------------------
--- Whether one square could take part of the hull. Returns `ok, reason`.
function W.squareIsClear(sq)
    if not sq then return false, "unloaded" end
    if U.isInterior(sq:getX(), sq:getY()) then return false, "interior" end

    -- "ok" rather than true, because U.try also returns nil when the call
    -- itself failed -- and a probe that threw must never read as clear ground.
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
--- Returns `ok, reason, blocked`. `exempt` is the square the player who
--- ordered the landing stands on: they are inside the footprint by definition
--- and step aside as the ship comes in. "unloaded" is reported only when every
--- bad square was unloaded.
function W.roomToLand(cx, cy, z, exempt)
    local blocked, first = 0, nil
    for _, d in ipairs(C.footprintOffsets()) do
        local x, y = cx + d[1], cy + d[2]
        local skip = W.hullCovers(x, y, z)
                     or (exempt and exempt.x == x and exempt.y == y)
        if not skip then
            local ok, why = W.squareIsClear(U.square(x, y, z, false))
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

function W.exemptFor(player)
    if not player then return nil end
    return { x = math.floor(player:getX()), y = math.floor(player:getY()) }
end

function W.footprintArea()
    return C.Footprint.w * C.Footprint.h
end

---------------------------------------------------------------------------
-- Where a person can stand
---------------------------------------------------------------------------
--- First walkable square beside a hull at x,y,z, searched from the stern
--- outward, because that is where the ramp is.
function W.landingBeside(x, y, z)
    local hh = math.floor((C.Footprint.h - 1) / 2)
    local hw = math.floor((C.Footprint.w - 1) / 2)
    local aft = C.Footprint.h - 1 - hh
    local offsets = {}
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
            if ok == true then return { x = x + o[1], y = y + o[2], z = z } end
        end
    end
    return nil
end

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

--- A square a person can stand on at or near a target, or nil. One person
--- needs one square, which is the difference from roomToLand.
function W.spotNear(cx, cy, z, radius)
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
-- Searching for a landing site
---------------------------------------------------------------------------
local searchOrder = nil

local function candidates()
    if searchOrder then return searchOrder end
    local out = {}
    for r = 0, C.LandingSearchRadius do
        for dx = -r, r do
            for dy = -r, r do
                if math.max(math.abs(dx), math.abs(dy)) == r then
                    table.insert(out, { dx, dy })
                end
            end
        end
    end
    searchOrder = out
    return out
end

-- Candidate positions examined per call. A whole pass is some thirty-six
-- thousand square lookups: fine spread over a few seconds, a hard lock if done
-- in one frame. The job resumes where it left off and wraps, because ground
-- not loaded on the first pass may be by the third.
W.SITES_PER_TICK = 48

--- Examines the next slice of candidates around job.x, job.y, job.z.
--- Returns `square, reason, exhausted`.
function W.searchSlice(job)
    local order = candidates()
    local exempt = job.exempt or W.exemptFor(job.player)
    local checked, exhausted = 0, false

    while checked < W.SITES_PER_TICK do
        job.cursor = (job.cursor or 0) + 1
        if job.cursor > #order then
            job.cursor = 1
            job.passes = (job.passes or 0) + 1
            exhausted = true
        end
        local d = order[job.cursor]
        local x, y = job.x + d[1], job.y + d[2]
        local sq = U.square(x, y, job.z, false)
        if sq and U.try("landProbe", function() return sq:getFloor() ~= nil end) then
            local ok, why = W.roomToLand(x, y, job.z, exempt)
            if ok then return sq, nil, exhausted end
            if why and why ~= "unloaded" then job.reason = job.reason or why end
        end
        checked = checked + 1
    end
    return nil, job.reason, exhausted
end

return W
