--[[ Shuttlecraft -- taking her up.

    Flight here is *driving*. The shuttle is already a vehicle, TREK_Sky lays
    an invisible floor at altitude, and vanilla does everything else: the
    throttle, the steering, the controller and the Steam Deck, the seats and
    seat switching, the camera, the position sync and the physics. There is no
    input handling in this file and no per-tick transform, because there does
    not need to be. All it does is put her up, put her down, keep her level and
    watch.

    Up and down is the whole of it: there is one flight altitude,
    C.FlightLevel, and no climb, no dive and no setAltitude command. See
    PILOTING.md section 1.

    The lift is the one unproven call in the feature:

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

-- The speed step is the ship's, not this client's.
--
-- It was local at first, on the reasoning that it is a pilot's own preference.
-- It is not: the helm is in the cabin and the pilot is in the cockpit, so on a
-- server the crewman who sets it is usually not the one flying. Held locally,
-- each client saw its own figure, only the driver's did anything, and handing
-- over the controls handed over whatever the new pilot happened to have set.

-- The vehicle's own top speed, kept so landing puts it back.
local groundSpeed = nil

-- One report per session, written the first time the ship goes up.
local probed = false

---------------------------------------------------------------------------
-- The ship
---------------------------------------------------------------------------
--- The shuttle vehicle, if this client can see it.
function F.vehicle()
    -- V.ship, not V.find: a client cannot read the tag, because build 42 does
    -- not sync a vehicle's own mod data. See TREK_Vehicle.ship.
    return V.ship()
end

function F.flying()
    return Ship.get().flying == true
end

--- True when this machine is the one simulating the vehicle's physics. Asked
--- rather than assumed: the engine knows, and two clients driving one
--- transform would fight.
---
--- **Single player is not one of the cases the engine can answer, and its
--- answer there is always no.** `BaseVehicle`'s constructor sets
--- `netPlayerAuthorization = Authorization.Server`, and the only thing that
--- ever changes it to `Local` is `constraintChanged()`, which calls
--- `authorizationChanged(getDriver())` behind
---
---     14  getstatic  GameServer.server
---     17  ifeq -> 92            <-- off a server: return, having set nothing
---
--- So off a server nothing ever touches it, and `isLocalPhysicSim()` -- which
--- off a server is `authorization == LocalCollide || authorization == Local`
--- -- is **false in single player for ever**. Vanilla never asks it there
--- either: `isBrakePedalPressed()` consults it only inside its
--- `GameClient.client` branch and otherwise goes straight to the controller.
---
--- This file does not load on a server at all (line one), so "not a client"
--- here means single player: one process, which is this one, and it owns
--- every vehicle's physics by having nobody to share them with.
---
--- It cost a release. `takeoffGranted` gained this guard in "multiplayer
--- updates" and, with it, single player could not take off at all -- silently,
--- because the guard simply returned. The simulation answered
--- `SIM_ROLE ~= "server"` and was therefore kindest about exactly the case
--- that was broken, so every test passed. `DEV_GUIDE.md`'s *The simulation has
--- to be as unkind as the engine*, and *A guard is only as good as the goal it
--- was written from*: the goal was "only one machine moves her", and in single
--- player that machine is this one.
local function ownsPhysics(vehicle)
    if not isClient() then return true end
    return U.try("isLocalPhysicSim", function()
        return vehicle:isLocalPhysicSim()
    end) == true
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

local RAD = math.pi / 180

--- The Y component of the ship's own "up", worked out from the three angles
--- the engine reports: 1 is level, 0 is on her side, -1 is on her back.
---
--- This is the question `keepLevel` actually wants, and the reason it has to
--- be asked this way rather than by looking at two of the angles is below.
local function uprightness(ax, ay, az)
    ax, ay, az = ax * RAD, ay * RAD, az * RAD
    return math.cos(az) * math.cos(ax)
           - math.sin(az) * math.sin(ay) * math.sin(ax)
end

--- Keeps her flat -- and keeps her pointing where the pilot pointed her.
---
--- She is resting on an invisible floor with real physics on, and a nudge can
--- tip a 1200kg box: seen in game, where she went over backwards. So something
--- has to put her right. What must not happen is what the first version of
--- this did, which was the whole of "she snaps back and will only fly in
--- reverse" from the first two-player flight.
---
--- **`getAngleX()` and `getAngleZ()` are not pitch and roll.** They are the X
--- and Z of JOML's `getEulerAnglesXYZ` decomposition of the entire rotation,
--- and the X of that decomposition is
---
---     atan2(2(xw - yz), 1 - 2(x^2 + y^2))
---
--- which for a ship that is perfectly level, turned by yaw alone, is
--- `atan2(0, cos yaw)` -- **180 degrees the moment the heading is more than a
--- quarter turn from the one she spawned at**, and the same for Z. So a test
--- of "is |angleX| small" is true in one half of the compass and false in the
--- other, for a ship that is dead level in both.
---
--- **And `flipUpright()` is not "level her".** Its bytecode is
---
---     Quaternionf.setAngleAxis(0, _UNIT_Y)    ; angle ZERO: the identity
---     Transform.setRotation(q)
---     BaseVehicle.setWorldTransform(t)        ; -> Bullet.teleportVehicle
---
--- an angle of nothing about Y, which is not level, it is *no rotation at all*
--- -- it throws the heading away with the pitch and the roll, and teleports
--- the physics body to do it.
---
--- Together: turn her past ninety degrees and every levelling check fires,
--- ten times a second, each one wrenching her nose back to her spawn heading
--- and killing her velocity. She goes nowhere. Reverse instead and the heading
--- never leaves the half of the compass where the artefact does not appear, so
--- reversing works perfectly -- which is exactly how it was reported.
---
--- So: ask whether she is upright, which is yaw-independent; and if she is
--- not, level her *about her own heading*. `Rx(0) Ry(a) Rz(0)` and
--- `Rx(180) Ry(a) Rz(180)` are both exactly level -- both are pure yaw -- and
--- they are the two halves of the compass. Which one carries her present
--- heading is decided by the sign of `cos(angleX)`: the same artefact, read
--- the right way round. `setAngles` takes degrees, builds the rotation with
--- `Quaternionf.rotationXYZ` and applies it through the same
--- `setWorldTransform` the lift uses, so it costs no height either -- and it
--- returns without touching anything when the angles it is handed are the ones
--- already in force.
local function keepLevel(vehicle)
    local ax = U.try("angleX", function() return vehicle:getAngleX() end) or 0
    local ay = U.try("angleY", function() return vehicle:getAngleY() end) or 0
    local az = U.try("angleZ", function() return vehicle:getAngleZ() end) or 0

    if uprightness(ax, ay, az) >= math.cos(C.FlightLevelTolerance * RAD) then
        return false
    end

    local flat = (math.abs(ax) > 90) and 180 or 0
    U.try("setAngles", function() vehicle:setAngles(flat, ay, flat) end)
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
        local want = F.speed()
        local cap = ceiling()
        if cap and want > cap then want = cap end
        vehicle:setMaxSpeed(want)
        local got = vehicle:getMaxSpeed()
        U.log("flight speed step %d: asked for %s, vehicle reports %s%s",
              F.speedStep(), tostring(want), tostring(got),
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
--- The step the ship is set to, as an index into C.FlightSpeedSteps.
function F.speedStep()
    local n = Ship.get().speed
    if type(n) ~= "number" then return C.FlightSpeedDefaultStep end
    return math.max(1, math.min(#C.FlightSpeedSteps, math.floor(n)))
end

--- The top speed that step means -- or a glide, during an emergency
--- landing (ENERGY.md 7.1): a dark ship is not flown, she is set down.
function F.speed()
    local want = C.FlightSpeedSteps[F.speedStep()] or C.FlightSpeedSteps[1]
    if Ship.get().emergency == true then return math.min(want, C.EmergencyGlideSpeed) end
    return want
end

--- Asks the server to change it. Every client applies it when the new state
--- comes back, so the pilot's machine acts on it whoever pressed the button.
function F.setSpeedStep(player, step)
    step = math.max(1, math.min(#C.FlightSpeedSteps, math.floor(step or 1)))
    Core.send(player, "setSpeed", { step = step })
    U.note(player, getText("IGUI_TREK_FlightSpeedSet",
                           tostring(C.FlightSpeedSteps[step])))
    return step
end

---------------------------------------------------------------------------
-- Moving between the ground and the flight level
---------------------------------------------------------------------------
-- She is carried up and down by placing her physics body a little higher (or
-- lower) every tick, eased at both ends, instead of by one teleport. Three
-- reasons, each of which was a bug:
--
--   * the crew see her rise and settle. The renderer draws a vehicle at its
--     physics height, not at its whole level (ModelSlotRenderData.init, bci
--     101-139), so the smooth body is a smooth picture;
--   * nothing is ever laid above her. The column (Sky.column) sits one level
--     under the band she is in, and the plane is laid only once she is above
--     it -- a floor that appears in front of a rising body is a shelf in the
--     physics engine, and running into it is what tipped her over;
--   * she is *held* at the top until the plane is complete and the physics
--     engine has had time to hear about it, then let go and watched. The old
--     climb let go at once onto a floor the physics had not been told about,
--     she fell back a level, and the re-lift then teleported her upward every
--     tick for ever with the state still claiming the new level: "stuck".
--
-- While a move is under way she is held by placement every tick, so gravity
-- and the plane beneath play no part until she is let go.
local moving = nil

function F.moving()
    return moving ~= nil
end

--- The stage of the move under way ("travel", "settle", "watch"), or nil.
function F.movePhase()
    return moving and moving.phase or nil
end

local function bodyY(vehicle)
    return U.try("bodyY", function()
        local t = Transform.new()
        vehicle:getWorldTransform(t)
        return t:getOrigin():y()
    end)
end

--- Puts her physics body at a height, keeping her x, z and rotation. Returns
--- "ok" rather than true for the reason F.lift does.
local function place(vehicle, y, px, pz)
    return U.try("placeBody", function()
        local t = Transform.new()
        vehicle:getWorldTransform(t)
        local o = t:getOrigin()
        o:set(px or o:x(), y, pz or o:z())
        vehicle:setWorldTransform(t)
        return "ok"
    end) == "ok"
end

-- The resting height for a level: a touch above its floor, as F.lift does.
local function restY(level)
    return level * C.LevelUnits + 0.25
end

-- The level band a body height is in, by the engine's own rounding
-- (BaseVehicle.update: fastfloor(origin.y / 2.449 + 0.05)).
local function bandOf(y)
    return math.floor(y / C.LevelUnits + 0.05)
end

local function smooth(f)
    if f <= 0 then return 0 end
    if f >= 1 then return 1 end
    return f * f * (3 - 2 * f)
end

--- The column for a body height: one level under the band she is in, and
--- nothing at all within a level of the ground, where Kentucky does the job.
local function columnFor(x, y, bodyHeight)
    local band = bandOf(bodyHeight)
    if band >= 2 then
        Sky.column(x, y, band - 1)
    else
        Sky.column(nil)
    end
end

--- Starts a move of the body from where it is to a level. `kind` is "up" (a
--- take-off, or carrying her back to her level in flight) or "down".
local function startMove(kind, vehicle, level, player, why)
    local from = bodyY(vehicle)
    if not from then
        U.log("WARN cannot read the shuttle's height; the %s did not start", kind)
        return false
    end
    local to = restY(level)
    local levels = math.abs(to - from) / C.LevelUnits
    -- Straight up or straight down, over the square she started on. A pilot
    -- with a foot on the throttle during a landing would otherwise drift her
    -- off the ground the footprint check approved.
    local px, pz = U.try("bodyXZ", function()
        local t = Transform.new()
        vehicle:getWorldTransform(t)
        return t:getOrigin():x(), t:getOrigin():z()
    end)
    local vx = U.try("vx", function() return vehicle:getX() end)
    local vy = U.try("vy", function() return vehicle:getY() end)
    if vx and vy then columnFor(vx, vy, from) end
    local ms = math.max(C.FlightClimbMinMs,
                        levels / C.FlightClimbLevelsPerSecond * 1000)
    U.try("wakePhysics", function() vehicle:setPhysicsActive(true, true) end)
    moving = {
        kind = kind, vehicle = vehicle, level = level, player = player,
        from = from, to = to, start = getTimestampMs(), ms = ms,
        phase = "travel", attempts = 0, why = why, ticks = 0,
        px = px, pz = pz,
        -- A take-off holds and lets go up to C.FlightSettleAttempts times
        -- and then brings her back to the ground. A recovery in flight is one
        -- try: the ship is recorded as flying, so it must never carry her
        -- down, and serviceFlight counts the tries and stops.
        maxAttempts = (why == "recovery") and 1 or C.FlightSettleAttempts,
    }
    U.log("%s: carrying her from level %.2f to level %d over %d ms (%s)",
          kind == "up" and "ascent" or "descent", from / C.LevelUnits,
          level, math.floor(ms), tostring(why))
    return true
end

-- Ends a move that could not finish: take up whatever is holding her and let
-- the engine have her. Only ever after she has been brought back down.
local function abandon(job, noteKey)
    U.try("wakePhysics", function() job.vehicle:setPhysicsActive(true, true) end)
    if noteKey and job.player then
        U.note(job.player, getText(noteKey), 255, 90, 90)
    end
    moving = nil
end

local function serviceMove()
    local job = moving
    if not job then return end
    local vehicle = job.vehicle
    job.ticks = job.ticks + 1

    local x = U.try("vx", function() return math.floor(vehicle:getX()) end)
    local y = U.try("vy", function() return math.floor(vehicle:getY()) end)
    if not x then
        U.log("WARN lost sight of the shuttle during the %s", job.kind)
        moving = nil
        return
    end
    local now = getTimestampMs()

    if job.phase == "travel" then
        local f = smooth((now - job.start) / job.ms)
        local h = job.from + (job.to - job.from) * f
        columnFor(x, y, h)
        place(vehicle, h, job.px, job.pz)
        if job.ticks % 6 == 0 then keepLevel(vehicle) end
        if f < 1 then return end

        if job.kind == "down" then
            -- On the ground. Everything that held her up comes away, and the
            -- engine has her again.
            place(vehicle, job.to, job.px, job.pz)
            Sky.clear()
            restoreSpeed(vehicle)
            U.log("descent complete at %d,%d (%s)", x, y, tostring(job.why))
            if job.onDone then job.onDone() end
            moving = nil
            return
        end
        job.phase = "settle"
        job.settleFrom = nil
        return
    end

    if job.phase == "settle" then
        -- Hold her where she is and lay the plane under her. She is above it
        -- by a quarter of a unit, so nothing is ever put where she is.
        place(vehicle, job.to, job.px, job.pz)
        columnFor(x, y, job.to)
        Sky.pave(x, y, job.level)
        Sky.keep(job.level)
        if job.ticks % 6 == 0 then keepLevel(vehicle) end
        if not (Sky.paved() and Sky.holds(x, y, job.level)) then
            job.settleFrom = nil
            if now - job.start > job.ms + C.FlightLiftTicks * 4 * 16 then
                U.log("WARN the sky plane never took under the ship at %d,%d " ..
                      "level %d; bringing her back down", x, y, job.level)
                Sky.report("plane failed")
                F.bringDown(job, "IGUI_TREK_NoLift")
            end
            return
        end
        job.settleFrom = job.settleFrom or now
        -- Longer each time: if the physics was slow to hear about the floor
        -- once, it is given more time to hear about it again.
        if now - job.settleFrom < C.FlightSettleMs * (job.attempts + 1) then return end
        job.phase = "watch"
        job.watchFrom = now
        job.lowest = nil
        -- The column comes up as she is let go. One square under a hull three
        -- wide is not a support, it is a pivot: if the plane is not holding
        -- her, she must be seen to sink -- not be caught on a single square,
        -- read as holding, and tipped over it.
        Sky.column(nil)
        U.try("wakePhysics", function() vehicle:setPhysicsActive(true, true) end)
        return
    end

    if job.phase == "watch" then
        -- Let go. Nothing is placed now: this is the engine's floor or nothing.
        Sky.pave(x, y, job.level)
        Sky.keep(job.level)
        local h = bodyY(vehicle) or 0
        local lvl = h / C.LevelUnits
        if job.lowest == nil or lvl < job.lowest then job.lowest = lvl end
        if lvl < job.level - C.FlightSinkTolerance or levelOf(vehicle) ~= job.level then
            job.attempts = job.attempts + 1
            U.log("WARN she sank to level %.2f after being let go at level %d " ..
                  "(attempt %d of %d); the physics does not have the floor yet",
                  lvl, job.level, job.attempts, job.maxAttempts)
            if job.attempts >= job.maxAttempts then
                if job.why == "recovery" then
                    U.log("recovery at level %d did not hold; leaving her to " ..
                          "the engine", job.level)
                    moving = nil
                    return
                end
                U.log("WARN the engine will not hold her at level %d; " ..
                      "bringing her back down", job.level)
                Sky.report("level refused")
                F.bringDown(job, "IGUI_TREK_NoLift")
                return
            end
            -- Back up, gently, and hold for longer.
            job.from, job.start = h, now
            job.ms = C.FlightClimbMinMs
            job.phase = "travel"
            return
        end
        if now - job.watchFrom < C.FlightWatchMs then return end

        -- She is up and the engine is holding her there.
        Sky.column(nil)
        local got = levelOf(vehicle)
        U.log("holding at level %s: lowest %.2f after letting go, %d hold(s)",
              tostring(got), job.lowest or -1, job.attempts + 1)
        if not probed then
            probed = true
            report(vehicle, job.level, got)
        end
        moving = nil
        if job.onDone then job.onDone(got) end
    end
end

--- Brings her back down from wherever a move stalled -- to the ground, which
--- is the one floor that never has to be laid. Nothing is sent to the server:
--- a take-off that failed never told it she was up.
function F.bringDown(job, noteKey)
    local vehicle = job.vehicle
    Sky.clearPlane()
    if noteKey and job.player then
        U.note(job.player, getText(noteKey), 255, 90, 90)
    end
    moving = nil
    if not startMove("down", vehicle, 0, job.player, "gave up on the height") then
        abandon(job)
        Sky.clear()
    end
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
    if moving then return false, "busy" end
    Core.send(player, "takeoff", {})
    return true
end

Net.onClient("takeoffGranted", function(args)
    local player = Core.lastAsker or U.player(0)
    local vehicle = F.vehicle()
    -- Both of these used to return in silence, and a take-off that is granted
    -- and then does nothing at all is indistinguishable from one that was
    -- never asked for. Silence is not a diagnosis (PILOTING.md section 6).
    if not vehicle then
        U.log("WARN take-off was granted and this machine cannot see the shuttle")
        U.note(player, getText("IGUI_TREK_NoLift"), 255, 90, 90)
        return
    end
    if not ownsPhysics(vehicle) then
        -- Not a refusal: on a server the pilot's own machine is the only one
        -- that moves her, and the rest are told she is up by the ship state.
        U.log("take-off granted, but this machine does not move her")
        return
    end
    if moving then
        U.log("take-off granted while she is already being moved; ignored")
        return
    end
    local level = math.floor(args.level or C.flightLevel())
    U.note(player, getText("IGUI_TREK_TakingOff"))
    if not startMove("up", vehicle, level, player, "take-off") then
        U.note(player, getText("IGUI_TREK_NoLift"), 255, 90, 90)
        return
    end
    -- Only once the engine has held her there does the server hear she is
    -- up: a take-off that fails must never leave the state saying she is in
    -- the air when she is sitting on the grass.
    moving.onDone = function(got)
        if got ~= level then
            U.log("WARN the ascent finished at level %s, not %d", tostring(got), level)
            return
        end
        F.applySpeed(vehicle)
        Core.send(player, "airborne", { level = level })
        U.log("airborne at level %d", level)
    end
end)

---------------------------------------------------------------------------
-- Landing
---------------------------------------------------------------------------
-- There is no climb and no dive, and there is no `setAltitude` command for
-- them to send. She is on the ground or she is hovering at C.FlightLevel: one
-- height, chosen because it is the only one that ever behaved in play and the
-- only one the engine will hold without the sky plane having to be perfect
-- (TREK_Config, C.FlightLevel). Four rungs of a ladder where three of them
-- did nothing was worse than no ladder.

--- Sets her down on the ground below.
--- Every way this can refuse writes a line. It used to write none: a pilot
--- reported "it would not let me land in the road" and the log had nothing
--- between going airborne and beaming out -- no attempt, no refusal, no
--- reason. Four silent early returns, and from the outside they are
--- indistinguishable from the radial menu never having called this at all,
--- which is a different bug entirely.
---
--- A refusal the player can see and the log cannot is half a report.
function F.land(player)
    if not F.flying() then
        U.log("land refused: she is not flying (state says landed=%s)",
              tostring(Ship.get().landed))
        return false, "not flying"
    end
    if not F.isPilot(player) then
        U.log("land refused: %s is not in the driver's seat",
              Ship.usernameOf and Ship.usernameOf(player) or "the asker")
        U.note(player, getText("IGUI_TREK_NotPilot"), 255, 90, 90)
        return false, "not pilot"
    end
    local vehicle = F.vehicle()
    if not vehicle then
        U.log("land refused: the shuttle vehicle cannot be found from here")
        return false, "no vehicle"
    end
    local x = math.floor(vehicle:getX())
    local y = math.floor(vehicle:getY())

    -- The same footprint question a called-down landing asks, with the ship's
    -- own hull exempted: it is directly overhead, and its squares must not be
    -- read as somebody else's vehicle standing in the way.
    local ok, why, blocked = W.roomToLand(x, y, 0, nil, true)
    if not ok then
        U.log("land refused at %d,%d: %s (%d of %d squares blocked)",
              x, y, tostring(why), blocked or -1, W.footprintArea())
        U.note(player, TREK.Travel.refusalText(why, blocked), 255, 90, 90)
        return false, why
    end
    U.log("asking to set her down at %d,%d", x, y)
    Core.send(player, "touchdown", { x = x, y = y, z = 0 })
    return true
end

Net.onClient("touchdownGranted", function(args)
    local vehicle = F.vehicle()
    local player = Core.lastAsker or U.player(0)
    U.log("setting her down at %d,%d", args.x or -1, args.y or -1)
    Sky.report("landing")
    if vehicle and ownsPhysics(vehicle) then
        -- Carried down, not dropped: the column one level under her takes over
        -- from the plane (startMove lays it before anything is lifted), the
        -- plane goes, and she sinks past floors that are no longer there.
        moving = nil
        if startMove("down", vehicle, math.floor(args.z or 0), player, "touchdown") then
            Sky.clearPlane()
            moving.onDone = function()
                U.note(player, getText("IGUI_TREK_Landed"))
            end
            return
        end
        -- The old way, if the height cannot even be read: onto the ground
        -- first, and only then take the plane up.
        if not F.lift(vehicle, math.floor(args.z or 0)) then
            U.log("WARN touchdown transform failed; keeping the sky plane under the shuttle")
            return
        end
        restoreSpeed(vehicle)
    end
    Sky.clear()
    U.note(player, getText("IGUI_TREK_Landed"))
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

-- Carrying her back to her level after the engine let her fall off it. Capped:
-- the old code re-lifted her every tick for as long as the height was wrong,
-- which on a floor the physics did not have was every tick for ever -- velocity
-- zeroed sixty times a second, the "stuck" of the climb report.
local recover = { count = 0, at = nil, gaveUp = false }

---------------------------------------------------------------------------
-- The obstacle guard
---------------------------------------------------------------------------
-- At her flight level she clears anything shorter; anything taller has walls
-- at her own level and would stop her the way a wall stops a car. So the
-- squares ahead of her, the way she is moving, are read at her level, and her
-- top speed is brought down as a wall comes nearer -- to a crawl just short of
-- it. She is never lifted over anything: changing level in flight is the
-- manoeuvre that failed, and a tower is a thing to go round.
local guard = { lastX = nil, lastY = nil, dirX = 0, dirY = 0, capped = nil, told = false }

-- The same test vanilla's own builder uses for "a wall stands here"
-- (server/BuildingObjects/ISBuildingObject.lua:309), and anything solid.
local function blockedAt(x, y, level)
    local sq = U.square(math.floor(x), math.floor(y), level, false)
    if not sq then return false end
    return U.try("guardSquare", function()
        return sq:has(IsoFlagType.collideN) or sq:has(IsoFlagType.collideW)
            or sq:isSolid() or sq:isSolidTrans()
    end) == true
end

--- The distance, in squares from her centre, to the first wall ahead of her
--- at this level; nil for none within reach.
function F.wallAhead(vehicle, level, dirX, dirY)
    local cx = U.try("vx", function() return vehicle:getX() end)
    local cy = U.try("vy", function() return vehicle:getY() end)
    if not cx then return nil end
    -- Across her beam: the hull is three wide, so her centre line and a
    -- square and a bit to either side.
    local sideX, sideY = -dirY, dirX
    for d = 1, C.GuardReach do
        for side = -1, 1 do
            local x = cx + dirX * d + sideX * side * 1.2
            local y = cy + dirY * d + sideY * side * 1.2
            if blockedAt(x, y, level) then return d end
        end
    end
    return nil
end

local function serviceGuard(vehicle, level, player)
    local x = U.try("vx", function() return vehicle:getX() end)
    local y = U.try("vy", function() return vehicle:getY() end)
    if not x then return end
    if guard.lastX then
        local dx, dy = x - guard.lastX, y - guard.lastY
        local d = math.sqrt(dx * dx + dy * dy)
        -- Only a real movement changes which way is "ahead"; standing still
        -- keeps the last one, so a pilot stopped at a wall is still guarded.
        if d > 0.02 then guard.dirX, guard.dirY = dx / d, dy / d end
    end
    guard.lastX, guard.lastY = x, y
    if guard.dirX == 0 and guard.dirY == 0 then return end

    local dist = F.wallAhead(vehicle, level, guard.dirX, guard.dirY)
    local cap = nil
    if dist then
        cap = math.max(C.GuardCrawl, (dist - C.GuardFrom) * C.GuardPerSquare)
        if dist <= C.GuardFrom then cap = C.GuardCrawl end
        if cap >= F.speed() then cap = nil end
    end
    if cap == guard.capped then return end
    guard.capped = cap
    U.try("guardSpeed", function() vehicle:setMaxSpeed(cap or F.speed()) end)
    if cap then
        U.log("obstacle guard: a wall %d squares ahead at level %d; top speed %s",
              dist, level, tostring(cap))
        if not guard.told and player then
            guard.told = true
            U.note(player, getText("IGUI_TREK_WallAhead"), 255, 200, 120)
        end
    else
        guard.told = false
        U.log("obstacle guard: clear ahead; top speed back to %s", tostring(F.speed()))
    end
end

function F.guardCap()
    return guard.capped
end

-- The pilot's half of the emergency landing (ENERGY.md 7.1).
local emergency = { tick = 0, askedAt = nil, capped = false }
-- Ticks between looks at the ground below, and how long to wait for the
-- server to answer before looking again.
local EMERGENCY_LOOK = 30
local EMERGENCY_WAIT = 300

--- A dark ship in the air with this player at her controls: she is held to a
--- glide, and the moment the footprint below her is clear she asks for the
--- ordinary touchdown -- the carried descent, not a fall, so no damage. Her
--- engine is kept alive by the server (the tank and battery stay while
--- `s.emergency` is set) and nothing is charged. Steering toward clear
--- ground is the whole of the pilot's control.
local function serviceEmergency(vehicle, x, y)
    local player = U.player(0)
    if not F.isPilot(player) then return end
    if not emergency.capped then
        emergency.capped = true
        F.applySpeed(vehicle)
        U.log("emergency: holding her to a glide of %s", tostring(F.speed()))
    end
    emergency.tick = emergency.tick + 1
    if emergency.askedAt and emergency.tick - emergency.askedAt < EMERGENCY_WAIT then return end
    if emergency.tick % EMERGENCY_LOOK ~= 0 then return end
    local ok = W.roomToLand(x, y, 0, nil, true)
    if not ok then return end
    emergency.askedAt = emergency.tick
    U.log("emergency: clear ground under her at %d,%d -- setting her down", x, y)
    Core.send(player, "touchdown", { x = x, y = y, z = 0 })
end

local function serviceFlight()
    if Ship.get().emergency ~= true then
        emergency.tick, emergency.askedAt, emergency.capped = 0, nil, false
    end
    if not F.flying() then
        recover.count, recover.at, recover.gaveUp = 0, nil, false
        guard.capped, guard.lastX, guard.dirX, guard.dirY = nil, nil, 0, 0
        return
    end
    -- A move under way owns the height; nothing here may fight it.
    if moving then return end
    local s = Ship.get()
    local vehicle = F.vehicle()
    if not vehicle then return end

    local x = U.try("vx", function() return math.floor(vehicle:getX()) end)
    local y = U.try("vy", function() return math.floor(vehicle:getY()) end)
    if not x then return end

    local level = math.floor(s.level or C.flightLevel())
    Sky.pave(x, y, level)

    -- Whatever level she is on this instant is the one holding her up, and it
    -- must not be swept while she is standing on it -- which is the whole of
    -- what went wrong when the pilot asked to climb.
    local got = levelOf(vehicle)
    Sky.keep(got)

    -- A wrong height is put right -- by carrying her back up the way the
    -- take-off does, not by teleporting her there every tick. And only so
    -- many times: if the engine keeps refusing the height, she is left where
    -- she is and the pilot is told, rather than held in place for ever.
    if got ~= level and ownsPhysics(vehicle) and not recover.gaveUp then
        local now = getTimestampMs()
        if recover.at == nil or now - recover.at >= C.FlightRecoverMs then
            recover.at = now
            recover.count = recover.count + 1
            local pilot = U.player(0)
            if recover.count > C.FlightRecoverLimit then
                recover.gaveUp = true
                U.log("WARN she keeps falling off level %d (engine has %s); no " ..
                      "more attempts this flight -- the pilot has been told to " ..
                      "set her down", level, tostring(got))
                U.note(pilot, getText("IGUI_TREK_CannotHold"), 255, 90, 90)
            else
                U.log("she fell off level %d (engine has %s); carrying her back " ..
                      "up, attempt %d of %d", level, tostring(got),
                      recover.count, C.FlightRecoverLimit)
                startMove("up", vehicle, level, pilot, "recovery")
                return
            end
        end
    end

    if ownsPhysics(vehicle) then
        U.try("guard", serviceGuard, vehicle, level, U.player(0))
        if s.emergency == true then
            U.try("emergency", serviceEmergency, vehicle, x, y)
        end
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
              tostring(F.speed()))
        Sky.report("cruising")
    end
end

--- The server has taken the ship out of flight -- she landed, or nobody was
--- aboard her any more. Bring her down and take the plane up.
---
--- `toOrbit` is the second of those: the last of the crew left her hovering,
--- so she has gone back up and the server is about to remove the vehicle. Say
--- so. A ship that vanishes with no word is indistinguishable from one that
--- was lost, and the crew need to know they can call her down again.
Net.onClient("flightEnded", function(args)
    local vehicle = F.vehicle()
    -- Whatever move was under way is over: the ship is somebody else's now,
    -- or on her way out of the sky.
    moving = nil
    if vehicle then
        if ownsPhysics(vehicle) then F.lift(vehicle, math.floor(args.z or 0)) end
        restoreSpeed(vehicle)
    end
    if args.toOrbit then
        U.note(U.player(0), getText("IGUI_TREK_BackUp"), 255, 200, 120)
    end
    U.log("flight ended (%s)", tostring(args.why))
    Sky.report("flight ended")
    Sky.clear()
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
-- The skyAt this client has already finished sweeping.
local sweptAt = nil

-- Where the rolling tidy-up last ran, and how long since.
local cleanedAt = nil
local cleaning = nil

--- Hunts down invisible floors nobody is using, near wherever the player is.
---
--- The ship's own record only remembers the flight it is on. Every earlier
--- flight -- and every earlier *build* of this feature, which laid a far wider
--- plane and trimmed it far less eagerly -- left its floors in the world, and
--- a floor is a saved world object. They showed up as a black blotch across a
--- car park in a screenshot taken while the plane itself was correctly down to
--- twenty-five squares: the ship was tidy and its history was not.
---
--- So this does not consult the record. It walks the ground near the player
--- and lifts anything of ours it finds above the deck, sliced, and only when
--- the player has moved somewhere it has not already been.
local function serviceClean()
    if Ship.get().flying then return end
    -- Nor while she is being carried up or down: she is not flying by the
    -- record then, and the column under her is exactly the kind of floor
    -- this goes looking for.
    if moving then return end
    local player = U.player(0)
    if not player then return end
    local px, py = math.floor(player:getX()), math.floor(player:getY())
    if U.isInterior(px, py) then return end

    if not cleaning then
        -- Once per patch of ground, and then not again until the player has
        -- walked somewhere new. There is no timer: a sweep that has already
        -- been done here has nothing left to find, and one that has not should
        -- not be made to wait.
        if cleanedAt and U.dist2(px, py, cleanedAt.x, cleanedAt.y)
                         < C.SkyCleanStride * C.SkyCleanStride then
            return
        end
        cleaning = { x = px, y = py, cursor = 0 }
    end

    if Sky.sweepArea(cleaning.x, cleaning.y, cleaning) then
        cleanedAt = { x = cleaning.x, y = cleaning.y }
        cleaning = nil
    end
end

local function serviceSweep()
    local s = Ship.get()
    -- Never while she is up. s.skyAt is written the moment she goes airborne
    -- so that a flight ending in a crash still gets its floors lifted, and an
    -- earlier version read it without this check -- so one second after
    -- take-off it began sweeping away the very plane the ship was resting on,
    -- physics took over, and she tipped backwards into the ground. Seen in
    -- game, 2026-09-17 20:00:18.
    if s.flying or moving then sweeping = nil return end
    local at = s.skyAt
    if not at then sweeping = nil return end
    if sweptAt and sweptAt.x == at.x and sweptAt.y == at.y
       and sweptAt.level == at.level then
        return                      -- this client has already been here
    end
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
        -- Remembered here rather than reported to the server. Every client
        -- lays its own plane and has its own to lift, so a shared "done" flag
        -- would let whoever finished first stop everybody else mid-sweep.
        sweptAt = { x = at.x, y = at.y, level = at.level }
        U.log("the leftover sky plane is gone")
    end
end

-- A speed set at the helm is ship state, so it arrives here as a state change
-- rather than as a button press. Whoever is flying applies it; on a server
-- that is usually not the crewman who set it.
-- Every client lays its own plane, so every client has to take its own up.
-- A touchdown ends the flight by the ship state alone -- touchdownGranted goes
-- to the pilot and nobody else -- and a second machine that went on holding
-- its plane left a patch of invisible floor over the landing site for as long
-- as nobody walked twenty squares away from it.
--
-- Not on the machine that drives her. There the plane is what she is resting
-- on, and the state can arrive a network round trip before touchdownGranted:
-- lifting it on the state would drop her for that long. touchdownGranted and
-- flightEnded take it up there, in the right order.
local wasFlying = false
Ship.onChange(function()
    local flying = F.flying()
    local vehicle = (wasFlying and not flying) and F.vehicle() or nil
    local drives = vehicle ~= nil and ownsPhysics(vehicle)
    if wasFlying and not flying and not moving and not drives then
        U.log("the flight is over by the ship's record; lifting this machine's plane")
        Sky.clear()
    end
    wasFlying = flying
end)

Ship.onChange(function()
    if not F.flying() then return end
    local vehicle = F.vehicle()
    if vehicle and ownsPhysics(vehicle) then F.applySpeed(vehicle) end
end)

Events.OnTick.Add(function()
    U.try("serviceMove", serviceMove)
    U.try("serviceFlight", serviceFlight)
    -- Unconditionally, not only while flying: the plane has to be laid *before*
    -- the ship can be up, and gating this on being airborne would leave the
    -- take-off waiting for a floor that only gets laid once it is airborne.
    -- Sky.service returns at once when there is nothing to pave.
    U.try("skyService", Sky.service)
    U.try("serviceClean", serviceClean)
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
