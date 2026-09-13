--[[ Shuttlecraft -- the in-game self test.

    A step machine rather than a straight function, because almost every step
    has to wait for the world: chunks stream in on their own schedule, the
    transporter takes a second and a half by design, and a landing may spend
    several seconds looking for ground. Each step returns "done", "again" or a
    failure, and the runner advances one step per tick.

    It writes TREK-TEST lines to console.txt. Pull them out with
    tools/readtest.sh.

    On a fresh world it runs itself; on a world where the ship is already in
    use it stays out of the way, because it flies the character around and
    that is unwelcome mid-game. TREK_SelfTest() from the debug console forces
    it.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local S = {}
TREK.SelfTest = S

local PREFIX = "TREK-TEST"
local run = nil

local function report(name, ok, detail)
    print(string.format("%s %s %s%s", PREFIX, ok and "PASS" or "FAIL",
                        name, detail and ("  -- " .. detail) or ""))
    if not ok then run.failed = run.failed + 1 end
    run.checked = run.checked + 1
end

local function banner(text)
    print(string.format("%s ==== %s ====", PREFIX, text))
end

---------------------------------------------------------------------------
-- Steps
---------------------------------------------------------------------------
-- Each step is { name, fn }. fn returns "done" to move on, "again" to be
-- called back next tick, or "fail" to abandon the run.

local steps = {}

local function step(name, fn)
    table.insert(steps, { name = name, fn = fn })
end

step("start", function()
    banner("shuttlecraft self test")
    local p = U.player(0)
    if not p then return "again" end
    run.player = p
    run.homeX = math.floor(p:getX())
    run.homeY = math.floor(p:getY())
    run.homeZ = math.floor(p:getZ())
    print(string.format("%s standing at %d,%d,%d", PREFIX,
                        run.homeX, run.homeY, run.homeZ))
    return "done"
end)

step("config", function()
    banner("configuration")
    report("config.footprint", TREK.Core.footprintArea() >= 9,
           string.format("%dx%d = %d squares", C.Footprint.w, C.Footprint.h,
                         TREK.Core.footprintArea()))
    report("config.padInHull", C.inShape(C.Landing.x, C.Landing.y),
           "the transporter pad is inside the cabin")
    report("config.rackInHull",
           C.inShape(C.PhaserRack.x, C.PhaserRack.y)
           and not C.isLanding(C.PhaserRack.x, C.PhaserRack.y),
           "the phaser locker is inside the cabin and off the pad")
    -- The cabin must not overlap anything the vanilla map ships, nor the
    -- TARDIS mod's interior if that is also installed.
    local cx = U.cabinOrigin()
    report("config.clearOfMap", cx > 78 * 256,
           string.format("cabin origin x=%d", cx))
    return "done"
end)

step("beamUp", function()
    banner("transporter: up")
    if not run.beamStarted then
        local ok, why = TREK.Transport.beamUp(run.player)
        report("beam.up.accepted", ok, why)
        if not ok then return "fail" end
        run.beamStarted = true
        run.waited = 0
        return "again"
    end
    run.waited = run.waited + 1
    if U.isInteriorPlayer(run.player) then
        report("beam.up.arrived", true,
               string.format("after %d ticks", run.waited))
        return "done"
    end
    if run.waited > 900 then
        report("beam.up.arrived", false, "never reached the cabin")
        return "fail"
    end
    return "again"
end)

step("cabin", function()
    if not TREK.Build.cabinCurrent() or TREK.Core.arriving() then
        run.waited = (run.waited or 0) + 1
        if run.waited > 900 then
            report("cabin.built", false, "the cabin never finished")
            return "fail"
        end
        return "again"
    end
    banner("the cabin")
    report("cabin.built", true)

    -- Floor everywhere the plan says there should be floor.
    local holes, floors = 0, 0
    for ox = 0, C.CabinW do
        for oy = 0, C.CabinL do
            if C.inShape(ox, oy) then
                local x, y = U.at(ox, oy)
                local sq = U.square(x, y, C.CabinZ, false)
                if sq and sq:getFloor() then floors = floors + 1
                else holes = holes + 1 end
            end
        end
    end
    report("cabin.floor", holes == 0,
           string.format("%d floored, %d holes", floors, holes))

    -- Nothing overhead. There is only one storey, so this should be trivially
    -- true -- it is checked because the day somebody adds a second one, the
    -- renderer will draw it straight over this one and nothing else will say
    -- so. See the note in TREK_Config.
    local overhead = 0
    for ox = 0, C.CabinW, 3 do
        for oy = 0, C.CabinL, 3 do
            if C.inShape(ox, oy) then
                local x, y = U.at(ox, oy)
                for z = C.CabinZ + 1, C.CabinZ + 3 do
                    local sq = U.square(x, y, z, false)
                    if sq and sq:getFloor() then overhead = overhead + 1 end
                end
            end
        end
    end
    report("cabin.nothingOverhead", overhead == 0,
           string.format("%d floors found above the deck", overhead))
    return "done"
end)

step("fittings", function()
    banner("fittings")
    local counts = {}
    for ox = 0, C.CabinW do
        for oy = 0, C.CabinL do
            local x, y = U.at(ox, oy)
            local sq = U.square(x, y, C.CabinZ, false)
            if sq then
                U.eachObject(sq, function(o)
                    local md = o:getModData()
                    local tag = md and md.TREK
                    if tag then counts[tag] = (counts[tag] or 0) + 1 end
                end)
            end
        end
    end
    local function want(tag, least)
        report("fitting." .. tag, (counts[tag] or 0) >= least,
               string.format("%d (wanted at least %d)", counts[tag] or 0, least))
    end
    want("wall", 40)
    want("sink", 2)         -- the galley and the head
    want("shower", 1)
    want("toilet", 1)
    want("bunk", 2)         -- a bed is two squares
    want("biobed", 2)
    want("medbay", 6)
    want("cargo.food", 3)
    want("cargo.medical", 3)
    want("fridge", 2)
    want("oven", 1)
    want("phasers", 1)
    want("lamp", 4)
    return "done"
end)

step("water", function()
    banner("water")
    TREK.Core.refillWater()
    local wet, dry = 0, 0
    for ox = 0, C.CabinW do
        for oy = 0, C.CabinL do
            local x, y = U.at(ox, oy)
            local sq = U.square(x, y, C.CabinZ, false)
            if sq then
                U.eachObject(sq, function(o)
                    local md = o:getModData()
                    local tag = md and md.TREK
                    if tag == "sink" or tag == "shower" or tag == "toilet" then
                        local amount = U.try("fluid", function()
                            return o:getFluidAmount()
                        end) or 0
                        if amount > 0 then wet = wet + 1 else dry = dry + 1 end
                    end
                end)
            end
        end
    end
    report("water.filled", wet > 0 and dry == 0,
           string.format("%d fixtures holding water, %d dry", wet, dry))
    return "done"
end)

step("phasers", function()
    banner("phasers")
    local x, y = U.at(C.PhaserRack.x, C.PhaserRack.y)
    local sq = U.square(x, y, C.CabinZ, false)
    local found = 0
    if sq then
        U.eachObject(sq, function(o)
            local container = U.containerOf(o)
            if not container then return end
            U.try("rackItems", function()
                local items = container:getItems()
                if not items then return end
                for i = 0, items:size() - 1 do
                    local it = items:get(i)
                    if it and it:getFullType() == C.PhaserItem then
                        found = found + 1
                    end
                end
            end)
        end)
    end
    report("phaser.inRack", found >= C.PhaserCount,
           string.format("%d of %d in the locker", found, C.PhaserCount))

    -- Take one and prove the recharge actually reaches it. Emptying it first
    -- is the point: a phaser that was never fired proves nothing.
    if found > 0 then
        local inv = run.player:getInventory()
        local item = U.try("giveSelf", function()
            return inv:AddItem(C.PhaserItem)
        end)
        if item then
            U.try("drain", function()
                item:setCurrentAmmoCount(0)
                item:setRoundChambered(false)
            end)
            TREK.Phaser.sweep(run.player)
            local ammo = U.try("readAmmo", function()
                return item:getCurrentAmmoCount()
            end) or 0
            local max = U.try("readMax", function()
                return item:getMaxAmmo()
            end) or 0
            report("phaser.recharges", ammo > 0 and ammo == max,
                   string.format("%d of %d rounds after a sweep", ammo, max))
        else
            report("phaser.recharges", false, "could not spawn one to test")
        end
    end
    return "done"
end)

step("bookmark", function()
    banner("helm")
    local before = #TREK.Travel.bookmarks()
    TREK.Travel.setDestination(run.homeX, run.homeY, run.homeZ)
    local ok = TREK.Travel.addBookmark("self test")
    report("helm.bookmark", ok and #TREK.Travel.bookmarks() == before + 1,
           string.format("%d logged positions", #TREK.Travel.bookmarks()))
    TREK.Travel.removeBookmark(#TREK.Travel.bookmarks())
    TREK.Travel.clearDestination()
    return "done"
end)

step("beamDown", function()
    banner("transporter: down")
    if not run.downStarted then
        local ok, why = TREK.Transport.beamDown(run.player)
        report("beam.down.accepted", ok, why)
        if not ok then return "fail" end
        run.downStarted = true
        run.waited = 0
        return "again"
    end
    run.waited = run.waited + 1
    if not U.isInteriorPlayer(run.player) then
        report("beam.down.arrived", true,
               string.format("at %d,%d after %d ticks",
                             math.floor(run.player:getX()),
                             math.floor(run.player:getY()), run.waited))
        return "done"
    end
    if run.waited > 900 then
        report("beam.down.arrived", false, "never left the cabin")
        return "fail"
    end
    return "again"
end)

step("landing", function()
    banner("landing")
    local px = math.floor(run.player:getX())
    local py = math.floor(run.player:getY())
    local pz = math.floor(run.player:getZ())

    -- roomToLand has to give an answer here one way or the other: the player
    -- is standing on this ground, so it is loaded and knowable.
    local exempt = TREK.Core.exemptFor(run.player)
    local ok, why, blocked = TREK.Core.roomToLand(px, py, pz, exempt)
    report("land.answers", why ~= "unloaded",
           string.format("%s, %d of %d squares blocked%s",
                         ok and "room" or "no room", blocked or 0,
                         TREK.Core.footprintArea(),
                         why and (", first: " .. why) or ""))

    local sq = TREK.Travel.findLandingSite(px, py, pz, run.player)
    if not sq then
        -- Not a failure: the character may genuinely be indoors. Say so
        -- plainly rather than reporting a fault that is not one.
        report("land.site", true,
               "no site within " .. C.LandingSearchRadius ..
               " squares -- standing somewhere too tight to test a landing")
        return "done"
    end
    local landed, failed = TREK.Core.land(sq, run.player)
    report("land.setDown", landed, failed)
    if landed then
        local s = U.state()
        report("land.hullFound",
               TREK.Core.hullOn(U.square(s.x, s.y, s.z, false)) ~= nil,
               string.format("hull at %d,%d,%d", s.x, s.y, s.z))
        report("land.hullCovers",
               TREK.Core.hullCovers(s.x, s.y, s.z)
               and TREK.Core.hullCovers(s.x, s.y + 1, s.z),
               "the whole footprint answers to the ship")
        report("land.beside", TREK.Core.landingBeside(s.x, s.y, s.z) ~= nil,
               "there is somewhere to stand at the foot of the ramp")
    end
    return "done"
end)

step("hatch", function()
    banner("the hatch")
    local s = U.state()
    if not s.landed then
        report("hatch.board", true, "the ship is not down; nothing to test")
        return "done"
    end
    if not run.boarded then
        report("hatch.board", TREK.Core.enter(run.player) == true)
        run.boarded = true
        run.waited = 0
        return "again"
    end
    run.waited = run.waited + 1
    if TREK.Core.arriving() then
        if run.waited > 900 then
            report("hatch.aboard", false, "never finished boarding")
            return "fail"
        end
        return "again"
    end
    report("hatch.aboard", U.isInteriorPlayer(run.player))
    report("hatch.out", TREK.Core.exit(run.player) == true)
    return "done"
end)

step("recall", function()
    banner("recall")
    local s = U.state()
    if s.landed then
        local wasX, wasY, wasZ = s.x, s.y, s.z
        report("recall.up", TREK.Core.recall() == true)
        report("recall.gone",
               TREK.Core.hullOn(U.square(wasX, wasY, wasZ, false)) == nil,
               "the hull is no longer on the ground")
        report("recall.hullCovers", not TREK.Core.hullCovers(wasX, wasY, wasZ),
               "and nothing there answers to the ship any more")
    else
        report("recall.up", true, "already overhead")
    end
    return "done"
end)

step("finish", function()
    banner(string.format("%d checks, %d failed", run.checked, run.failed))
    return "done"
end)

---------------------------------------------------------------------------
-- The runner
---------------------------------------------------------------------------
local function tick()
    if not run then return end
    local current = steps[run.index]
    if not current then
        Events.OnTick.Remove(tick)
        run = nil
        return
    end

    -- A step that throws must end the run, not repeat its exception every
    -- tick for the rest of the session.
    local ok, result = pcall(current.fn)
    if not ok then
        report(current.name, false, "threw: " .. tostring(result))
        Events.OnTick.Remove(tick)
        run = nil
        return
    end

    if result == "again" then return end
    if result == "fail" then
        banner(string.format("abandoned at %s -- %d checks, %d failed",
                             current.name, run.checked, run.failed))
        Events.OnTick.Remove(tick)
        run = nil
        return
    end
    run.index = run.index + 1
    run.waited = 0
end

function S.start()
    if run then
        U.log("self test already running")
        return false
    end
    run = { index = 1, checked = 0, failed = 0, waited = 0 }
    Events.OnTick.Add(tick)
    return true
end

--- Exposed for the debug console: TREK_SelfTest()
function TREK_SelfTest()
    return S.start()
end

-- Run itself on a world where the ship has never been used. Anywhere else it
-- stays quiet: it beams the character across the map and back, which is not
-- something to do to a game in progress.
Events.OnGameStart.Add(function()
    local s = U.state()
    if s.built or s.everLanded then
        U.log("self test skipped: the ship is already in use " ..
              "(TREK_SelfTest() to force it)")
        return
    end
    if not isDebugEnabled or not isDebugEnabled() then return end
    U.log("fresh world with -debug: running the self test")
    S.start()
end)

return S
