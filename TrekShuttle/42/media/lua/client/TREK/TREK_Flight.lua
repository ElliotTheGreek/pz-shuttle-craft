--[[ Shuttlecraft -- taking her up.

    Flight here is *driving*. The shuttle is already a vehicle, TREK_Sky lays
    an invisible floor at altitude, and vanilla does everything else: the
    throttle, the steering, the controller and the Steam Deck, the seats and
    seat switching, the camera, the position sync and the physics. There is no
    input handling in this file and no per-tick transform, because there does
    not need to be. All it does is move the ship between levels and watch.

    The move between levels is the one unproven call in the feature:

        local t = Transform.new()
        vehicle:getWorldTransform(t)
        local o = t:getOrigin()
        o:set(o:x(), level * C.LevelUnits, o:z())
        vehicle:setWorldTransform(t)

    Transform and org.joml.Vector3f are both on the engine's Lua exposure
    allow-list, Transform.getOrigin() hands back the live vector rather than a
    copy, and none of these calls is gated on a role or on Core.debug. But
    getWorldTransform and setWorldTransform have **no vanilla Lua call site**,
    and DEV_GUIDE.md is emphatic that being in the jar is not the same as being
    callable. So the lift is not trusted: it is performed, and then the result
    is read back off the engine a tick later, and the answer is written to the
    log either way. Nothing here needs a debug console to say what happened.

    Why the ship does not fall when the pilot steps aft: the floor holds it up.
    Flight is a place, not a manoeuvre. Leaving the driver's seat parks the
    ship in the air, which is what lets the crew go through to the cabin and
    come back -- PILOTING.md section 3.2.4 -- and removes the whole class of
    bug that killed the 1.1 flight, where flight outlived its pilot.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_World"
require "TREK/TREK_Vehicle"
require "TREK/TREK_Sky"
require "TREK/TREK_Core"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Ship = TREK.Ship
local W = TREK.World
local V = TREK.Vehicle
local Sky = TREK.Sky
local Core = TREK.Core

local F = {}
TREK.Flight = F

-- The take-off in progress on this client, if any.
local rising = nil

-- The speed step is a pilot's own preference, not something the whole world
-- needs to agree on, so it stays here rather than in the ship's state.
F.speedStep = C.FlightSpeedDefaultStep

-- The vehicle's own top speed, kept so landing puts it back.
local groundSpeed = nil

-- One report per session, written the first time the ship goes up.
local probed = false

---------------------------------------------------------------------------
-- The ship
---------------------------------------------------------------------------
--- The shuttle vehicle, if this client can see it.
function F.vehicle()
    return V.find(Ship.get().vehicleId)
end

function F.flying()
    return Ship.get().flying == true
end

--- True when this machine is the one simulating the vehicle's physics. Asked
--- rather than assumed: the engine knows, and two clients driving one
--- transform would fight.
local function ownsPhysics(vehicle)
    return U.try("isLocalPhysicSim", function()
        return vehicle:isLocalPhysicSim()
    end) ~= false
end

--- True when this player is in the driver's seat of the shuttle.
function F.isPilot(player)
    if not player then return false end
    local vehicle = U.try("playerVehicle", function() return player:getVehicle() end)
    if not V.isShuttle(vehicle) then return false end
    return U.try("isDriver", function() return vehicle:isDriver(player) end) == true
end

local function levelOf(vehicle)
    local z = U.try("vehicleZ", function() return vehicle:getZ() end)
    return z and math.floor(z) or nil
end

---------------------------------------------------------------------------
-- Moving between levels
---------------------------------------------------------------------------
--- Puts the ship at a level. Returns the string "ok" when the call itself
--- went through -- a positive token, not a bare truth, because U.try answers
--- nil both for "it failed" and for "it returned nothing", and a probe that
--- cannot tell those apart is how an unreachable call reads as success.
function F.lift(vehicle, level)
    return U.try("liftTransform", function()
        -- Wake her first. setWorldTransform reaches Bullet.teleportVehicle,
        -- and a body the engine has put to sleep does not necessarily take the
        -- teleport: the first attempt in game reported "physics active=false"
        -- and the height simply did not stick, while the second, with the body
        -- awake, worked at once. This is the vanilla "Drop" call and is
        -- ungated.
        U.try("wakePhysics", function() vehicle:setPhysicsActive(true, true) end)

        local t = Transform.new()
        vehicle:getWorldTransform(t)
        local o = t:getOrigin()
        -- A touch above the level's floor, so the ship settles onto it rather
        -- than starting inside it.
        o:set(o:x(), level * C.LevelUnits + 0.25, o:z())
        vehicle:setWorldTransform(t)
        return "ok"
    end) == "ok"
end

--- The Bullet height, in levels. This is where altitude actually lives -- the
--- game's getZ() is derived from it and thrown away wherever there is no floor
--- -- so a lift that "did nothing" is told apart from one the floor check
--- refused only by reading both.
function F.bulletLevel(vehicle)
    return U.try("bulletLevel", function()
        local t = Transform.new()
        vehicle:getWorldTransform(t)
        return t:getOrigin():y() / C.LevelUnits
    end)
end

--- Keeps her flat. She is resting on an invisible floor with real physics on,
--- and a nudge can tip a 1200kg box: seen in game, where she went over
--- backwards. flipUpright sets the rotation to level and leaves the origin
--- alone, so it cannot cost any height.
local function keepLevel(vehicle)
    local ax = U.try("angleX", function() return vehicle:getAngleX() end) or 0
    local az = U.try("angleZ", function() return vehicle:getAngleZ() end) or 0
    if math.abs(ax) < C.FlightLevelTolerance and math.abs(az) < C.FlightLevelTolerance then
        return false
    end
    U.try("flipUpright", function() vehicle:flipUpright() end)
    return true
end

--- Reads back what the engine actually did with the height.
---
--- This is the whole point. update() recomputes a vehicle's z from its physics
--- body every tick and throws the height away unless a floor is under it, so
--- the only honest answer to "did the lift work" is the one the engine gives
--- afterwards.
function F.levelReached(vehicle)
    return levelOf(vehicle)
end

---------------------------------------------------------------------------
-- The report that makes a test flight conclusive
---------------------------------------------------------------------------
--- Written to console.txt by itself the first time the ship goes up. Nothing
--- in here needs anybody to open a console: the owner flies, and the log says
--- what the engine did.
local function report(vehicle, want, got)
    U.log("---- flight probe ----")
    U.log("build debug flag: %s (a mechanism that only works under -debug is " ..
          "no use to anyone on the Workshop)",
          tostring(U.try("coreDebug", function() return getCore():getDebug() end)))
    U.log("Transform reachable from Lua: %s",
          tostring(U.try("transformNew", function()
              return Transform.new() ~= nil
          end) == true))
    U.log("asked for level %d: engine reports z %s, physics body is at level %s",
          want, tostring(got), tostring(F.bulletLevel(vehicle)))
    U.log("  (if the body is at the level and z is 0, the floor check refused it; "
          .. "if the body is at 0 too, the teleport itself did not take)")
    U.log("vehicle position %.2f,%.2f,%.2f  physics active=%s",
          U.try("vx", function() return vehicle:getX() end) or -1,
          U.try("vy", function() return vehicle:getY() end) or -1,
          U.try("vz", function() return vehicle:getZ() end) or -1,
          tostring(U.try("physActive", function() return vehicle:isPhysicsActive() end)))

    -- Everything in TREK_Vehicle finds the ship by walking the cell's vehicle
    -- set. If altitude took it out of that set, the ship would be lost.
    local seen = 0
    V.each(function() seen = seen + 1 end)
    U.log("shuttle vehicles the cell still lists: %d", seen)

    -- The crew are placed by the engine from the vehicle's own z. If they do
    -- not follow it up, somebody is about to fall.
    local n = U.try("maxPassengers", function() return vehicle:getMaxPassengers() end) or 0
    for seat = 0, n - 1 do
        local ch = U.try("seatCharacter", function() return vehicle:getCharacter(seat) end)
        if ch then
            U.log("  seat %d: z=%.2f falling=%s", seat,
                  U.try("chZ", function() return ch:getZ() end) or -1,
                  tostring(U.try("chFall", function() return ch:isbFalling() end)))
        end
    end

    U.log("server SpeedLimit option: %s (units unverified -- the cap is a " ..
          "fraction of it until the game says what it means)",
          tostring(U.try("speedLimit", function()
              return getServerOptions():getOption("SpeedLimit")
          end)))
    Sky.report("after the lift")
    U.log("---- end flight probe ----")
end

---------------------------------------------------------------------------
-- Speed
---------------------------------------------------------------------------
--- The ship is really driving, so the helm's step is the vehicle's own top
--- speed and nothing more exotic than that.
--- The ceiling the server allows, whatever the helm asks for.
---
--- Kept a fraction of the server's own setting rather than equal to it,
--- because what that setting *means* is not settled: PILOTING.md reads
--- SpeedLimit as 70 tiles a second, but it is a 10-150 vehicle limiter the
--- game's own UI presents in km/h, and 70 km/h is nearer 19 tiles a second --
--- below what a character may do on foot, not thirty-five times it. The 1.1
--- flight shipped a number derived from an unverified unit and moved pilots at
--- 450 tiles a second, which is what got them kicked. Until the game says
--- which it is, stay well under either reading.
local function ceiling()
    -- Single player has no anti-cheat and nobody else's server to respect, so
    -- there is nothing to cap against and the pilot gets the whole range.
    if not isClient() then return nil end
    local limit = tonumber(U.try("speedLimit", function()
        return getServerOptions():getOption("SpeedLimit")
    end))
    if not limit or limit <= 0 then return nil end
    return limit * C.FlightSpeedCapFraction
end

--- Sets the ship's top speed from the helm's step, and reads it back.
---
--- Reading it back is the point. "Is the speed control doing anything?" is not
--- answerable by looking at the code -- the setting was being written and then
--- clamped to the same number for the top three steps, so the control moved
--- and the ship did not. One line in the log settles it.
function F.applySpeed(vehicle)
    if not vehicle then return nil end
    return U.try("vehicleSpeed", function()
        if groundSpeed == nil then groundSpeed = vehicle:getMaxSpeed() end
        local want = C.FlightSpeedSteps[F.speedStep] or C.FlightSpeedSteps[1]
        local cap = ceiling()
        if cap and want > cap then want = cap end
        vehicle:setMaxSpeed(want)
        local got = vehicle:getMaxSpeed()
        U.log("flight speed step %d: asked for %s, vehicle reports %s%s",
              F.speedStep, tostring(want), tostring(got),
              cap and (" (server ceiling " .. tostring(cap) .. ")") or "")
        return got
    end)
end

local function restoreSpeed(vehicle)
    if not vehicle or groundSpeed == nil then return end
    U.try("vehicleSpeedBack", function() vehicle:setMaxSpeed(groundSpeed) end)
    groundSpeed = nil
end

--- Steps the helm's flight speed and reports it. Used by the helm and the
--- vehicle menu.
function F.setSpeedStep(player, step)
    step = math.max(1, math.min(#C.FlightSpeedSteps, math.floor(step or 1)))
    F.speedStep = step
    F.applySpeed(F.vehicle())
    U.note(player, getText("IGUI_TREK_FlightSpeedSet",
                           tostring(C.FlightSpeedSteps[step])))
    return step
end

---------------------------------------------------------------------------
-- Take off
---------------------------------------------------------------------------
function F.takeOff(player)
    if not player then return false end
    if F.flying() then return false, "already" end
    if not F.isPilot(player) then
        U.note(player, getText("IGUI_TREK_NotPilot"), 255, 90, 90)
        return false, "notPilot"
    end
    if rising then return false, "busy" end
    Core.send(player, "takeoff", {})
    return true
end

Net.onClient("takeoffGranted", function(args)
    local player = Core.lastAsker or U.player(0)
    local vehicle = F.vehicle()
    if not vehicle then return end
    local level = math.floor(args.level or C.FlightCruise)
    rising = {
        vehicle = vehicle, level = level, ticks = 0,
        player = player, lifted = false,
    }
    U.note(player, getText("IGUI_TREK_TakingOff"))
    U.log("taking her up to level %d; paving the sky plane first", level)
end)

--- The rise: pave, lift, then read the height back off the engine.
---
--- In that order and no other. Lifting a ship onto a floor that is not there
--- yet drops it back the same tick, because update() throws the height away
--- when the square under the ship has nothing in it.
local function serviceRise()
    local job = rising
    if not job then return end
    local vehicle = job.vehicle
    job.ticks = job.ticks + 1

    local x = U.try("vx", function() return math.floor(vehicle:getX()) end)
    local y = U.try("vy", function() return math.floor(vehicle:getY()) end)
    if not x then rising = nil return end

    Sky.pave(x, y, job.level)

    if not job.lifted then
        if not Sky.holds(x, y, job.level) then
            if job.ticks > C.FlightLiftTicks * 4 then
                U.log("WARN the sky plane never took under the ship at %d,%d " ..
                      "level %d; staying on the ground", x, y, job.level)
                Sky.report("plane failed")
                Sky.clear()
                U.note(job.player, getText("IGUI_TREK_NoLift"), 255, 90, 90)
                rising = nil
            end
            return
        end
        if not F.lift(vehicle, job.level) then
            U.log("WARN the lift call itself did not go through; Transform is " ..
                  "probably not reachable from Lua in this build")
            report(vehicle, job.level, levelOf(vehicle))
            Sky.clear()
            U.note(job.player, getText("IGUI_TREK_NoLift"), 255, 90, 90)
            rising = nil
            return
        end
        job.lifted = true
        job.liftedAt = job.ticks
        return
    end

    -- A tick or two for the engine to recompute the vehicle's z from its
    -- physics body and settle it onto the floor.
    if job.ticks - job.liftedAt < 4 then return end

    local got = F.levelReached(vehicle)
    if not probed then
        probed = true
        report(vehicle, job.level, got)
    end

    if got == job.level then
        F.applySpeed(vehicle)
        Core.send(job.player, "airborne", { level = job.level })
        U.log("airborne at level %d", job.level)
        rising = nil
        return
    end

    if job.ticks - job.liftedAt < C.FlightLiftTicks then
        -- Try again: the floor may have arrived a moment after the lift.
        F.lift(vehicle, job.level)
        return
    end

    U.log("WARN the engine would not hold the ship at level %d (it reports %s); " ..
          "coming back down", job.level, tostring(got))
    Sky.clear()
    U.note(job.player, getText("IGUI_TREK_NoLift"), 255, 90, 90)
    rising = nil
end

---------------------------------------------------------------------------
-- Climb, dive and landing
---------------------------------------------------------------------------
function F.setLevel(player, level)
    if not F.flying() then return false end
    if not F.isPilot(player) then
        U.note(player, getText("IGUI_TREK_NotPilot"), 255, 90, 90)
        return false
    end
    level = math.floor(level)
    -- Say so rather than silently clamping: a menu option that appears to do
    -- nothing is the thing TREK_Menu.lua's header forbids.
    if level > C.FlightMaxLevel then
        U.note(player, getText("IGUI_TREK_CeilingReached"), 255, 170, 90)
        return false
    end
    if level < C.FlightMinLevel then
        U.note(player, getText("IGUI_TREK_FloorReached"), 255, 170, 90)
        return false
    end
    Core.send(player, "setAltitude", { level = level })
    return true
end

function F.climb(player) return F.setLevel(player, (Ship.get().level or C.FlightCruise) + 1) end
function F.dive(player)  return F.setLevel(player, (Ship.get().level or C.FlightCruise) - 1) end

--- Sets her down on the ground below.
function F.land(player)
    if not F.flying() then return false end
    if not F.isPilot(player) then
        U.note(player, getText("IGUI_TREK_NotPilot"), 255, 90, 90)
        return false
    end
    local vehicle = F.vehicle()
    if not vehicle then return false end
    local x = math.floor(vehicle:getX())
    local y = math.floor(vehicle:getY())

    -- The same footprint question a called-down landing asks, with the ship's
    -- own hull exempted: it is directly overhead, and its squares must not be
    -- read as somebody else's vehicle standing in the way.
    local ok, why, blocked = W.roomToLand(x, y, 0, nil, V.idOf(vehicle))
    if not ok then
        U.note(player, TREK.Travel.refusalText(why, blocked), 255, 90, 90)
        return false, why
    end
    Core.send(player, "touchdown", { x = x, y = y, z = 0 })
    return true
end

Net.onClient("touchdownGranted", function(args)
    local vehicle = F.vehicle()
    U.log("setting her down at %d,%d", args.x or -1, args.y or -1)
    if vehicle then
        -- Down onto real ground first, and only then take the plane up: the
        -- other way round is a five-tonne shuttle with nothing under it.
        F.lift(vehicle, math.floor(args.z or 0))
        restoreSpeed(vehicle)
    end
    Sky.report("landing")
    Sky.clear()
    U.note(Core.lastAsker or U.player(0), getText("IGUI_TREK_Landed"))
end)

---------------------------------------------------------------------------
-- Keeping her up
---------------------------------------------------------------------------
-- Every client paves, because every client has to draw the ship in the air.
-- Only the machine simulating the physics re-asserts the height, and only when
-- the engine has let it slip -- which is the self-healing that covers a level
-- change, a chunk arriving late, or a knock.
local holdTick = 0
local reportTick = 0

local function serviceFlight()
    if not F.flying() then return end
    local s = Ship.get()
    local vehicle = F.vehicle()
    if not vehicle then return end

    local x = U.try("vx", function() return math.floor(vehicle:getX()) end)
    local y = U.try("vy", function() return math.floor(vehicle:getY()) end)
    if not x then return end

    local level = math.floor(s.level or C.FlightCruise)
    Sky.pave(x, y, level)

    -- Whatever level she is on this instant is the one holding her up, and it
    -- must not be swept while she is standing on it -- which is the whole of
    -- what went wrong when the pilot asked to climb.
    local got = levelOf(vehicle)
    Sky.keep(got)

    -- A wrong height is put right the moment it is noticed, not on the slow
    -- cadence below. Six ticks of falling is a long way down, and a climb is
    -- exactly when the answer is briefly wrong: she is at the old level, the
    -- target is the new one, and the gap between them is a fall.
    if got ~= level and ownsPhysics(vehicle) and Sky.holds(x, y, level) then
        U.debug("moving her to level %d (engine had %s)", level, tostring(got))
        F.lift(vehicle, level)
    end

    holdTick = holdTick + 1
    if holdTick >= 6 then
        holdTick = 0
        if ownsPhysics(vehicle) and keepLevel(vehicle) then
            U.debug("levelling her off")
        end
    end

    -- A line in the log every half minute or so, so a flight that goes wrong
    -- leaves a trail without anybody having to ask for one.
    reportTick = reportTick + 1
    if reportTick >= 1800 then
        reportTick = 0
        U.log("in flight at %d,%d level %s, speed step %s",
              x, y, tostring(levelOf(vehicle)),
              tostring(C.FlightSpeedSteps[F.speedStep]))
        Sky.report("cruising")
    end
end

--- The server has taken the ship out of flight -- it landed, or nobody was
--- flying it any more. Bring her down and take the plane up.
Net.onClient("flightEnded", function(args)
    local vehicle = F.vehicle()
    if vehicle then
        if ownsPhysics(vehicle) then F.lift(vehicle, math.floor(args.z or 0)) end
        restoreSpeed(vehicle)
    end
    U.log("flight ended (%s)", tostring(args.why))
    Sky.report("flight ended")
    Sky.clear()
    rising = nil
end)

---------------------------------------------------------------------------
-- Litter left by a flight that ended badly
---------------------------------------------------------------------------
-- A floor this mod lays is a world object on a square, and squares are saved.
-- A normal landing takes the plane up again, but a crash, a kill or a pulled
-- plug does not, and an invisible platform left in the sky would be there for
-- the life of the world. The ship state remembers where the plane was while
-- it was flying, so whoever next loads that ground clears it.
local sweeping = nil

local function serviceSweep()
    local s = Ship.get()
    -- Never while she is up. s.skyAt is written the moment she goes airborne
    -- so that a flight ending in a crash still gets its floors lifted, and an
    -- earlier version read it without this check -- so one second after
    -- take-off it began sweeping away the very plane the ship was resting on,
    -- physics took over, and she tipped backwards into the ground. Seen in
    -- game, 2026-09-17 20:00:18.
    if s.flying then sweeping = nil return end
    local at = s.skyAt
    if not at then sweeping = nil return end
    local player = U.player(0)
    if not player then return end
    if U.dist2(player:getX(), player:getY(), at.x, at.y) > (C.SkyRadius * 3) ^ 2 then
        return
    end
    if not sweeping then
        sweeping = { cursor = 0 }
        U.log("clearing a sky plane left behind near %d,%d", at.x, at.y)
    end
    if Sky.sweepArea(at.x, at.y, sweeping) then
        sweeping = nil
        Core.send(player, "skyCleared", {})
        U.log("the leftover sky plane is gone")
    end
end

Events.OnTick.Add(function()
    U.try("serviceRise", serviceRise)
    U.try("serviceFlight", serviceFlight)
    -- Unconditionally, not only while flying: the plane has to be laid *before*
    -- the ship can be up, and gating this on being airborne would leave the
    -- take-off waiting for a floor that only gets laid once it is airborne.
    -- Sky.service returns at once when there is nothing to pave.
    U.try("skyService", Sky.service)
end)

local sweepTick = 0
Events.OnPlayerUpdate.Add(function(player)
    if not player or not player:isLocalPlayer() then return end
    sweepTick = sweepTick + 1
    if sweepTick < 30 then return end
    sweepTick = 0
    U.try("serviceSweep", serviceSweep)
end)

---------------------------------------------------------------------------
-- Telling the pilot she can fly
---------------------------------------------------------------------------
-- Taking off is a radial-menu choice, and a menu nobody knows to open is a
-- feature nobody has. So sitting down at the controls says so, over the
-- pilot's head and in the log -- which also means a session where flight was
-- never offered can be told apart from one where it was offered and refused.
local told = false

local function atTheControls(character)
    if not character or not character:isLocalPlayer() then return end
    if not F.isPilot(character) then return end
    local s = Ship.get()
    if s.flying then return end
    if not s.landed then return end
    U.note(character, getText("IGUI_TREK_AtControls"), 255, 200, 120)
    if not told then
        told = true
        U.log("a pilot is at the shuttle's controls; 'take her up' is on the " ..
              "radial menu (landed=%s, flying=%s)",
              tostring(s.landed), tostring(s.flying))
    end
end

Events.OnEnterVehicle.Add(function(ch) U.try("atControls", atTheControls, ch) end)
Events.OnSwitchVehicleSeat.Add(function(ch) U.try("atControls", atTheControls, ch) end)

---------------------------------------------------------------------------
-- Debug console
---------------------------------------------------------------------------
-- Extras, not the plan. Everything these report is already written to the log
-- by itself when the ship goes up, comes down or is flown -- nobody should
-- have to open a console to find out what happened.

--- TREK_Fly(): take her up, or set her down if she is already up.
function TREK_Fly()
    local player = U.player(0)
    if not player then return false end
    if F.flying() then return F.land(player) end
    return F.takeOff(player)
end

--- TREK_Sky(): what the sky plane is costing.
function TREK_Sky()
    Sky.report("asked")
    return Sky.count()
end

return F
