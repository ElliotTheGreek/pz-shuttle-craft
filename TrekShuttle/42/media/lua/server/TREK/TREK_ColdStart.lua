--[[ Shuttlecraft -- the cold start (ENERGY.md section 10).

    A new world, by default, begins with the ship dark: zero power, no spare
    crystals, two probes in the rack, and the shuttle landed beside the first
    player, undamaged. She cannot be driven and will not beam. The crew walk
    aboard through the hatch, launch a probe, walk to the dilithium it finds,
    walk back and load it into the core -- and she comes to life. That first
    power-up is the commissioning, and it is what starts the story's clock.

    **Nothing here needed new machinery beyond the power system**, which is why
    it was built last. A dark ship is the power system at zero:

      * the state is written once, here, when a brand new ship is created;
      * she is landed with S.land, a clean spawn, and the dark ship's own parts
        (a flat battery, a dry tank) refuse to drive her;
      * the commissioning is TREK_Energy's first powerUp of a ship that was
        never commissioned;
      * and the recovery probe is the one guard against a campaign with no way
        forward left in it.

    **An existing save is never drained.** A ship that has ever been built or
    landed carries on commissioned, whatever the sandbox says. ROADMAP2: never
    infer a campaign from a low reserve -- `s.commissioned` is explicit and
    published, and nothing reads the reserve to decide it.

    Authority only.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_World"
require "TREK/TREK_Power"
require "TREK/TREK_Probes"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Ship = TREK.Ship
local W = TREK.World

local CS = {}
TREK.ColdStart = CS

---------------------------------------------------------------------------
-- 10.2: the state
---------------------------------------------------------------------------
--- Decides, once, how this ship begins. Returns "cold", "commissioned",
--- "migrated" or nil when it was already decided.
function CS.init()
    local s = U.state()
    if s.commissioned ~= nil then return nil end

    -- A save from before the cold start: whatever the sandbox says, it goes
    -- on as it was. A ship that has never existed at all is new.
    if s.built == true or s.everLanded == true or s.landed == true or s.vehicleId then
        s.commissioned = true
        Ship.commit()
        U.log("cold start: an existing ship carries on commissioned")
        return "migrated"
    end

    if C.startState() ~= C.StartCold then
        s.commissioned = true
        Ship.commit()
        U.log("cold start: the sandbox asks for a commissioned ship")
        return "commissioned"
    end

    -- Written here, explicitly, by the server, and never by a first read:
    -- U.state() fills a missing reserve with a full crystal, which is right
    -- for an old save and exactly wrong for this one. furnishCore issues its
    -- spares only when the count is missing, so the 0 stands.
    s.commissioned = false
    s.coldStart = true
    s.power = 0
    s.crystals = 0
    s.probes = C.ColdStartProbes
    s.dark = true
    Ship.commit()
    U.log("cold start: a new ship, dark -- no power, no spares, %d probes",
          C.ColdStartProbes)
    return "cold"
end

---------------------------------------------------------------------------
-- 10.3: where she is
---------------------------------------------------------------------------
-- Landed beside the first player rather than overhead: a dark ship overhead
-- could never be reached. The server builds only where somebody is standing,
-- so it waits for them, then searches around them on the ring between
-- C.ColdPlaceMin and C.ColdPlaceMax -- close enough to see, room to walk --
-- sliced, because the ring is hundreds of positions of fifteen squares each.

local ring = nil
local function ringOffsets()
    if ring then return ring end
    ring = {}
    for r = C.ColdPlaceMin, C.ColdPlaceMax do
        for dx = -r, r do
            for dy = -r, r do
                if math.max(math.abs(dx), math.abs(dy)) == r then
                    table.insert(ring, { dx, dy })
                end
            end
        end
    end
    return ring
end

-- The search under way: around which square, for whom, and how far through.
local placing = nil

--- The player a cold ship is set down beside: the first one in the world who
--- is alive, on their feet on real ground (not aboard, not in a vehicle), and
--- whose ground is loaded. On a server that is the first to join; everybody
--- else finds her where she is.
local function firstOnFoot()
    for _, p in ipairs(U.players()) do
        local ok = U.try("coldFirst", function()
            if p:isDead() then return false end
            if p:getVehicle() then return false end
            if U.isInteriorPlayer(p) then return false end
            return U.chunkLoaded(math.floor(p:getX()), math.floor(p:getY()), 0)
        end)
        if ok == true then return p end
    end
    return nil
end

--- True while a cold ship needs setting down: never commissioned, and not
--- on the ground.
---
--- **Not "until she has been placed once."** ENERGY.md 10.3 had a flag to
--- stop it happening twice, and a mutation showed the flag could change
--- nothing -- the `landed` test already covers it -- and also what it would
--- have cost: a cold ship whose vehicle is lost before she is commissioned
--- (burnt out, removed) is recorded as overhead by the vehicle pass, and a
--- dark ship overhead can never be reached. So she is set down beside the
--- first player again, which is the same answer the first time gave.
--- `s.coldPlaced` is kept as a record, for the log and the tests.
function CS.needsPlacing()
    local s = U.state()
    return s.coldStart == true and s.commissioned == false and s.landed ~= true
end

--- One slice of the search. Returns true once she is down.
function CS.servicePlacement()
    local s = U.state()
    if not CS.needsPlacing() then return false end
    local p = firstOnFoot()
    if not p then return false end
    local px, py = math.floor(p:getX()), math.floor(p:getY())

    -- A player who has walked on is searched around afresh: "if there is no
    -- room within the radius, it retries as the player moves".
    if not placing or math.abs(placing.x - px) + math.abs(placing.y - py) > 8 then
        placing = { x = px, y = py, cursor = 0, exempt = W.exemptFor(p) }
    end

    local order = ringOffsets()
    for _ = 1, W.SITES_PER_TICK do
        placing.cursor = placing.cursor + 1
        if placing.cursor > #order then placing.cursor = 1 end
        local d = order[placing.cursor]
        local x, y = placing.x + d[1], placing.y + d[2]
        local sq = U.square(x, y, 0, false)
        if sq and U.try("coldFloor", function() return sq:getFloor() ~= nil end) then
            local ok = W.roomToLand(x, y, 0, placing.exempt)
            if ok then
                local landed, why = TREK.Server.land(x, y, 0, p)
                if landed then
                    placing = nil
                    s.coldPlaced = true
                    Ship.commit()
                    Net.toClient(p, "coldPlaced", { x = x, y = y, z = 0 })
                    U.log("cold start: the shuttle is down at %d,%d, %d squares from %s, "
                          .. "without power", x, y, math.max(math.abs(x - px), math.abs(y - py)),
                          Ship.usernameOf(p))
                    return true
                end
                U.log("WARN cold start: landing at %d,%d refused (%s)", x, y, tostring(why))
            end
        end
    end
    return false
end

---------------------------------------------------------------------------
-- 10.6: the recovery probe
---------------------------------------------------------------------------
--- True when a cold ship has run out of every way forward the ship itself
--- can offer: no probe in the rack or in flight, no dilithium contact still
--- out there, and nothing in the core. The crew may still find a crystal in
--- the world -- twelve loot tables and the tricorder -- but a campaign that
--- depends on that alone is one bad afternoon from a soft-lock.
function CS.stranded()
    local s = U.state()
    if s.commissioned ~= false then return false end
    if (s.probes or 0) > 0 then return false end
    if TREK.Probes.active() then return false end
    for _, contact in ipairs(TREK.Probes.unresolved()) do
        if contact.kind == "dilithium" then return false end
    end
    if TREK.Power.reserve() >= 1 or TREK.Power.crystals() > 0 then return false end
    return true
end

--- Once a game day at most: a stranded cold ship is given one probe.
function CS.serviceRecovery()
    local s = U.state()
    if s.commissioned ~= false then return false end
    local now = U.try("coldHours", function()
        return getGameTime():getWorldAgeHours()
    end) or 0
    if s.coldRecoveryAt and now - s.coldRecoveryAt < 24 then return false end
    if not CS.stranded() then return false end
    s.coldRecoveryAt = now
    s.probes = 1
    s.coldRecoveries = (s.coldRecoveries or 0) + 1
    Ship.commit()
    U.log("cold start: the ship had no way left to find dilithium; one probe is in "
          .. "the rack (%d so far)", s.coldRecoveries)
    if s.coldRecoveries > C.ColdRecoveryWarn then
        U.log("WARN cold start: %d recovery probes in one save -- that is a bug, "
              .. "not bad luck", s.coldRecoveries)
    end
    Net.toAll("coldRecovery", {})
    return true
end

---------------------------------------------------------------------------
-- Timers
---------------------------------------------------------------------------
Events.OnInitGlobalModData.Add(function()
    U.try("coldInit", CS.init)
end)

-- Every tick while she needs placing, and a few comparisons otherwise.
Events.OnTick.Add(function()
    if CS.needsPlacing() then U.try("coldPlace", CS.servicePlacement) end
end)

Events.EveryTenMinutes.Add(function()
    U.try("coldRecovery", CS.serviceRecovery)
end)

return CS
