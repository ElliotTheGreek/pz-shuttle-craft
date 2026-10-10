--[[ Shuttlecraft -- the tractor beam: what each client moves.

    The server owns whether the beam is on (`s.tractor`, its holder's name;
    TREK_Server) and what it costs. This file is what it does: while it is
    on, everything within C.Tractor.radius of the ground under her goes where
    she goes.

    **Each machine moves what is its own to move**, which is the shields'
    rule (Core.repelZombies) and the sky plane's:

      * the dead a client simulates (not isRemoteZombie) are that client's.
        Every client holds its own, so a horde shared between two players is
        carried whole;
      * another vehicle is moved by the machine that runs its physics: in
        single player this one, on a server whichever client the engine has
        handed it to (isLocalPhysicSim). A parked car on a dedicated server
        that no client has been handed is not moved at all, and that case
        has not been seen in game.

    **A vehicle is raised; the dead are not.** A car is lifted C.Tractor.lift
    of the way up to her, so it clears a fence (the first one played stopped
    at one). Its height is the engine's, zeroed wherever there is no floor
    under it (DEV_GUIDE, *A vehicle's altitude is a floor, not a height*), so
    each one held gets a square of the sky's own floor under it (Sky.prop),
    laid after the body is up and moved as it moves. It is put back at the
    height it was taken from when it is let go. The dead stay on the ground:
    a body held off a floor banks a fall, and they are moved by position, so
    no fence stops them. Everything goes exactly as far as she moved since
    the last tick.

    setWorldTransform is the call the flight itself is built on
    (TREK_Flight.lua has its provenance).
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Ship"
require "TREK/TREK_Vehicle"
require "TREK/TREK_Sky"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Ship = TREK.Ship
local V = TREK.Vehicle

local TB = {}
TREK.Tractor = TB

-- What this client is holding: zombie -> { x, y } (where it is being kept),
-- vehicle -> true.
TB.zombies = {}
TB.cars = {}
TB.count = { zombies = 0, cars = 0 }

local lastX, lastY = nil, nil
local tick = 0

--- How many levels up a held vehicle rides.
local function liftLevels()
    local n = math.floor(C.flightLevel() * C.Tractor.lift)
    if n < 1 then n = 1 end
    return n
end

local carIds = 0

--- Sets a held vehicle down where it is: back to the height it was taken
--- from, and its square of floor taken up after it.
local function setDown(v, car)
    U.try("tractor.setDown", function()
        v:setPhysicsActive(true, true)
        local t = Transform.new()
        v:getWorldTransform(t)
        local o = t:getOrigin()
        o:set(o:x(), car.y0, o:z())
        v:setWorldTransform(t)
    end)
    TREK.Sky.prop(car.id, nil)
end

local function drop()
    for v, car in pairs(TB.cars) do setDown(v, car) end
    TB.zombies, TB.cars = {}, {}
    TB.count.zombies, TB.count.cars = 0, 0
    lastX, lastY = nil, nil
    tick = 0
end

--- Where she is, as smoothly as this machine knows it: her vehicle when it
--- is loaded here, and the ship's published square when it is not.
local function shipAt()
    local v = V.ship()
    if v then
        local x = U.try("tractor.vx", function() return v:getX() end)
        local y = U.try("tractor.vy", function() return v:getY() end)
        if x and y then return x, y, v end
    end
    local s = Ship.get()
    if s.x and s.y then return s.x + 0.5, s.y + 0.5, nil end
    return nil
end

--- True when this machine runs that vehicle's physics (TREK_Flight's rule:
--- in single player the engine's own answer is always false, and this
--- machine is the only one there is).
local function ownsPhysics(vehicle)
    if not isClient() then return true end
    return U.try("tractor.owns", function() return vehicle:isLocalPhysicSim() end) == true
end

--- Takes hold of whatever is under her and is not held yet.
local function capture(sx, sy, ship)
    local T = C.Tractor
    local r2 = T.radius * T.radius
    local cell = U.cell()
    if not cell then return end

    local zombies = U.try("tractor.zombies", function() return cell:getZombieList() end)
    local n = zombies and (U.try("tractor.zcount", function() return zombies:size() end) or 0) or 0
    local take = U.batch("tractor.capture")
    for i = 0, n - 1 do
        if TB.count.zombies >= T.maxZombies then break end
        take(function()
            local z = zombies:get(i)
            if not z or TB.zombies[z] or z:isDead() or z:isRemoteZombie() then return true end
            -- Not the Adirondack's crew (the sentry's rule).
            if z:isUseless() then return true end
            if math.floor(z:getZ()) ~= 0 then return true end
            local zx, zy = z:getX(), z:getY()
            if U.dist2(zx, zy, sx, sy) > r2 then return true end
            TB.zombies[z] = { x = zx, y = zy }
            TB.count.zombies = TB.count.zombies + 1
            return true
        end)
    end

    -- Collected through the iterator, as V.each does: it is the one way of
    -- walking the cell's vehicles this mod has seen work.
    local vehicles = {}
    U.try("tractor.vehicles", function()
        local it = cell:getVehicles():iterator()
        while it:hasNext() do
            local v = it:next()
            if v then table.insert(vehicles, v) end
        end
    end)
    for _, v in ipairs(vehicles) do
        if TB.count.cars >= T.maxCars then break end
        take(function()
            if v == ship or TB.cars[v] or V.isShuttle(v) then return true end
            if U.dist2(v:getX(), v:getY(), sx, sy) > r2 then return true end
            if not ownsPhysics(v) then return true end
            -- The height it stands at now is the height it goes back to.
            local t = Transform.new()
            v:getWorldTransform(t)
            carIds = carIds + 1
            TB.cars[v] = { id = "car" .. carIds, y0 = t:getOrigin():y(), up = 0 }
            TB.count.cars = TB.count.cars + 1
            return true
        end)
    end
end

--- Carries what is held by (dx, dy), and keeps the dead where they are put:
--- one that walked would walk out from under her.
local function carry(dx, dy)
    local move = U.batch("tractor.carry")
    for z, at in pairs(TB.zombies) do
        local ok = move(function()
            if z:isDead() then return false end
            at.x, at.y = at.x + dx, at.y + dy
            z:setX(at.x) z:setY(at.y)
            z:setLastX(at.x) z:setLastY(at.y)
            z:setTarget(nil)
            return true
        end)
        if not ok then
            TB.zombies[z] = nil
            TB.count.zombies = TB.count.zombies - 1
        end
    end
    -- A vehicle is placed on every tick, moving or not: it is being held up,
    -- and the one square of floor under it is not something to rest on.
    local levels = liftLevels()
    for v, car in pairs(TB.cars) do
        local ok = move(function()
            -- Awake first, or the body may not take the move (F.lift).
            v:setPhysicsActive(true, true)
            local t = Transform.new()
            v:getWorldTransform(t)
            local o = t:getOrigin()
            -- Bullet's x and z are the map's x and y, a tile to a unit; its
            -- y is height: where it stood, and that many levels more.
            o:set(o:x() + dx, car.y0 + levels * C.LevelUnits, o:z() + dy)
            v:setWorldTransform(t)
            -- The floor goes under it once it is up there, never before: a
            -- floor laid over a body that then rises through it is a shelf,
            -- and that collision is what flips a vehicle (TREK_Sky, the
            -- column).
            car.up = car.up + 1
            if car.up > 2 then
                TREK.Sky.prop(car.id, v:getX() + dx, v:getY() + dy, levels)
            end
            return true
        end)
        if not ok then
            TREK.Sky.prop(car.id, nil)
            TB.cars[v] = nil
            TB.count.cars = TB.count.cars - 1
        end
    end
end

--- The beam itself, for everybody who can see her: a wide pale bolt from her
--- to the ground under her, renewed while it is on.
local function showBeam(sx, sy)
    local FX = TREK.PhaserFX
    if not FX or not FX.boltAt then return end
    local T = C.Tractor
    local s = Ship.get()
    FX.boltAt({ x = sx, y = sy, z = s.level or C.flightLevel(),
                tx = sx, ty = sy, tz = 0,
                tint = T.tint, width = T.width, ms = T.beamTicks * 34 })
end

function TB.service()
    local s = Ship.get()
    if s.tractor == nil then
        if lastX then
            U.log("tractor: let go of %d of the dead and %d vehicle(s)", TB.count.zombies, TB.count.cars)
            drop()
        end
        return
    end
    local sx, sy, ship = shipAt()
    if not sx then return end

    if not lastX then
        lastX, lastY = sx, sy
        capture(sx, sy, ship)
        U.log("tractor: holding %d of the dead and %d vehicle(s)", TB.count.zombies, TB.count.cars)
    end
    tick = tick + 1
    if tick % C.Tractor.recaptureTicks == 0 then capture(sx, sy, ship) end
    if tick % C.Tractor.beamTicks == 1 then showBeam(sx, sy) end

    local dx, dy = sx - lastX, sy - lastY
    lastX, lastY = sx, sy
    -- A jump is her being moved, not her moving (a landing, a chunk reload):
    -- nothing is dragged across the county for it.
    if math.abs(dx) > 3 or math.abs(dy) > 3 then dx, dy = 0, 0 end
    carry(dx, dy)
end

Events.OnTick.Add(function() U.try("tractor.service", TB.service) end)

return TB
