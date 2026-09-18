--[[ A small stand-in for the parts of Project Zomboid the mod touches, so
    tests/test_multiplayer.py can run the real mod code as single player, as a
    server, and as clients connected to it.

    It is not the game. It models exactly the behaviour the mod's multiplayer
    design depends on, as MULTIPLAYER.md records it:

      * isClient()/isServer() per role, and every Lua folder loading everywhere;
      * sendClientCommand reaching OnClientCommand in single player too, and
        sendServerCommand doing nothing there;
      * global mod data: transmit/request/receive, and receiving not storing;
      * squares existing only where a player has loaded them;
      * objects added on the server reaching clients only through the
        transmit calls (py_replicate), never through a client's own edits;
      * zombies owned by one client (isRemoteZombie on the others).

    Everything crossing between runtimes goes through Python as plain data,
    so a command carrying something that could not cross a network fails.

    The runtime sets SIM_ROLE ("sp", "server" or "client") and SIM_ID before
    loading this file.
]]

_G.unpack = _G.unpack or table.unpack

-- Kahlua, the game's Lua, lacks some of the standard library. Remove what the
-- game does not have, so using it fails here instead of in game.
next = nil
math.huge = nil
SIM = { log = {}, notes = {}, lamps = 0, voidX = 24000 }

function print(...)
    local parts = {}
    for i = 1, select("#", ...) do parts[#parts + 1] = tostring(select(i, ...)) end
    table.insert(SIM.log, table.concat(parts, " "))
end

function isClient() return SIM_ROLE == "client" end
function isServer() return SIM_ROLE == "server" end
function getCellSizeInSquares() return 256 end

-- getDebug() is false on purpose. A mechanism that only works under -debug is
-- no use to a Workshop subscriber, so the simulation never pretends otherwise.
local core = {
    getDebug = function() return false end,
    getKey = function(_, name) return 0 end,
    getScreenWidth = function() return 1920 end,
    getScreenHeight = function() return 1080 end,
}
function getCore() return core end

-- Textures are not modelled; the tests that care assert on the *name* of an
-- icon file existing on disk (tests/test_assets.py), not on pixels.
function getTexture(path) return { path = path } end
function getText(key, ...)
    local out = key
    for i = 1, select("#", ...) do out = out .. "|" .. tostring(select(i, ...)) end
    return out
end
function getTimestampMs() return py_clock() end

---------------------------------------------------------------------------
-- Java-ish lists
---------------------------------------------------------------------------
local function jlist(t)
    t = t or {}
    return {
        _t = t,
        size = function() return #t end,
        get = function(_, i) return t[i + 1] end,
        add = function(_, v) table.insert(t, v) end,
    }
end
SIM.jlist = jlist

---------------------------------------------------------------------------
-- Events
---------------------------------------------------------------------------
Events = setmetatable({}, { __index = function(self, name)
    local ev = { handlers = {} }
    function ev.Add(fn) table.insert(ev.handlers, fn) end
    function ev.Remove(fn)
        for i, h in ipairs(ev.handlers) do
            if h == fn then table.remove(ev.handlers, i) return end
        end
    end
    rawset(self, name, ev)
    return ev
end })

function SIM.fire(name, ...)
    local ev = rawget(Events, name)
    if not ev then return end
    for _, h in ipairs(ev.handlers) do h(...) end
end

---------------------------------------------------------------------------
-- Items and containers
---------------------------------------------------------------------------
function instanceItem(id)
    if type(id) ~= "string" or not id:find("%.") then return nil end
    return { fullType = id, getFullType = function(self) return self.fullType end }
end

function SIM.container(capacity)
    local c = { items = {}, capacity = capacity or 40, explored = false }
    function c:AddItem(item)
        if type(item) == "string" then item = instanceItem(item) end
        if not item then return nil end
        table.insert(self.items, item)
        return item
    end
    function c:getItems() return jlist(self.items) end
    function c:getCapacity() return self.capacity end
    function c:getContentsWeight() return #self.items * 0.5 end
    function c:setExplored(v) self.explored = v end
    function c:setDirty() end
    function c:setDrawDirty() end
    function c:getAllTypeRecurse() return jlist({}) end
    return c
end

function sendAddItemToContainer(container, item)
    if not isServer() then error("sendAddItemToContainer off the server") end
    local obj = container.parentObject
    if obj and obj.square then
        py_replicate("containerItem", { x = obj.square.x, y = obj.square.y, z = obj.square.z,
                                        sprite = obj.spriteName, item = item.fullType })
    end
end

---------------------------------------------------------------------------
-- Objects
---------------------------------------------------------------------------
local ObjectMT = {}
ObjectMT.__index = ObjectMT

function SIM.object(sprite, class)
    local o = setmetatable({ spriteName = sprite, modData = {}, class = class or "IsoObject" }, ObjectMT)
    return o
end

function ObjectMT:getSprite()
    local name = self.spriteName
    return { getName = function() return name end }
end
function ObjectMT:getModData() return self.modData end
function ObjectMT:getSquare() return self.square end
function ObjectMT:createContainersFromSpriteProperties()
    if self.container then return end
    if self.spriteName:find("counter") or self.spriteName:find("storage")
       or self.spriteName:find("refrigeration") or self.spriteName:find("cooking")
       or self.spriteName:find("medical") or self.spriteName:find("shelving")
       or self.spriteName:find("military") or self.spriteName:find("CONTAINER") then
        self.container = SIM.container(40)
        self.container.parentObject = self
    end
end
function ObjectMT:getContainer() return self.container end
function ObjectMT:getItemContainer() return self.container end
function ObjectMT:getFluidCapacity() return self.fluid and self.fluid.capacity or 0 end
function ObjectMT:getFluidAmount() return self.fluid and self.fluid.amount or 0 end
function ObjectMT:addFluid(_, n)
    if not self.fluid then return end
    self.fluid.amount = math.min(self.fluid.capacity, self.fluid.amount + n)
    if isServer() then
        py_replicate("fluid", { x = self.square.x, y = self.square.y, z = self.square.z,
                                sprite = self.spriteName, amount = self.fluid.amount })
    end
end
function ObjectMT:hasWater() return self:getFluidAmount() > 0 end
function ObjectMT:transmitModData()
    if isServer() then
        py_replicate("modData", { x = self.square.x, y = self.square.y, z = self.square.z,
                                  sprite = self.spriteName, modData = self.modData })
    end
end
function ObjectMT:getItem() return self.item end
function ObjectMT:setIgnoreRemoveSandbox() end

IsoObject = {}
function IsoObject.new(sq, sprite, name)
    return SIM.object(sprite)
end

function instanceof(o, class)
    return type(o) == "table" and o.class == class
end

ComponentType = { FluidContainer = {} }
function ComponentType.FluidContainer:CreateComponent()
    local f = { capacity = 0, amount = 0 }
    function f:setCapacity(n) self.capacity = n end
    function f:addFluid(_, n) self.amount = math.min(self.capacity, self.amount + n) end
    return f
end
GameEntityFactory = {}
function GameEntityFactory.AddComponent(obj, _, f) obj.fluid = f end
FluidType = { Water = "Water" }

---------------------------------------------------------------------------
-- Squares and the cell
---------------------------------------------------------------------------
local squares = {}
SIM.squares = squares

local function key(x, y, z) return x .. "," .. y .. "," .. z end

local SquareMT = {}
SquareMT.__index = SquareMT

local function newSquare(x, y, z)
    local sq = setmetatable({ x = x, y = y, z = z, objects = {}, worldObjects = {},
                              solid = false, occupied = false }, SquareMT)
    squares[key(x, y, z)] = sq
    return sq
end

function SquareMT:getX() return self.x end
function SquareMT:getY() return self.y end
function SquareMT:getZ() return self.z end
function SquareMT:getObjects() return jlist(self.objects) end
function SquareMT:getWorldObjects() return jlist(self.worldObjects) end
function SquareMT:getFloor()
    for _, o in ipairs(self.objects) do if o.isFloor then return o end end
    return nil
end
function SquareMT:isSolid() return self.solid end
function SquareMT:isSolidTrans() return false end
function SquareMT:isFree() return not self.occupied end
--- A vehicle stands over a 3x5 box of squares around its position (the
--- shuttle's size; the only vehicle the tests spawn).
function SquareMT:getVehicleContainer()
    for _, v in ipairs(SIM.vehicles or {}) do
        -- v:getZ(), not v.z: a vehicle in the air stands over nothing on the
        -- ground, which is what lets a flying shuttle be set down beneath
        -- itself without its own hull refusing the landing.
        if not v.removed and self.z == math.floor(v:getZ())
           and math.abs(self.x - math.floor(v.x)) <= 1
           and math.abs(self.y - math.floor(v.y)) <= 2 then
            return v
        end
    end
    return nil
end
function SquareMT:setHaveElectricity(v) self.power = v end

-- Removing an object without recalculating leaves the square holding every
-- conclusion the engine had already drawn from what was on it -- which is why
-- floors that had genuinely been lifted went on darkening the ground beneath
-- them. Counted so a test can insist the pair is always used.
local function markRecalced(sq)
    if sq.recalced == false then
        SIM.staleSquares = math.max(0, (SIM.staleSquares or 0) - 1)
    end
    sq.recalced = true
end
function SquareMT:RecalcProperties() markRecalced(self) end
function SquareMT:RecalcAllWithNeighbours() markRecalced(self) end


function SquareMT:addFloor(sprite)
    local f = SIM.object(sprite)
    f.isFloor = true
    f.square = self
    table.insert(self.objects, 1, f)
    if isServer() then
        py_replicate("floor", { x = self.x, y = self.y, z = self.z, sprite = sprite })
    elseif isClient() then
        -- The sky plane is the one thing a client may lay, and it is counted
        -- apart so the "no client ever edits the world" assertion keeps its
        -- teeth for everything else. A test can then insist that the only
        -- client-side floors are this sprite, and only above the ground.
        SIM.clientWorldEdit = (SIM.clientWorldEdit or 0) + 1
    end
    -- Counted whatever the role, because single player is a client too as far
    -- as the sky plane is concerned, and a test needs to see it either way.
    if sprite == "invisible_01_0" and self.z > 0 then
        SIM.skyEdit = (SIM.skyEdit or 0) + 1
        if isClient() then
            -- The one world edit a client may make. Taken back out of the
            -- general count so that "no client ever edits the world" keeps its
            -- teeth for everything else.
            SIM.clientWorldEdit = SIM.clientWorldEdit - 1
            if SIM.clientWorldEdit == 0 then SIM.clientWorldEdit = nil end
        end
    end
    return f
end

local function describe(o)
    local items = {}
    if o.container then
        for _, it in ipairs(o.container.items) do table.insert(items, it.fullType) end
    end
    return { sprite = o.spriteName, modData = o.modData, items = items,
             hasContainer = o.container ~= nil,
             fluid = o.fluid and { capacity = o.fluid.capacity, amount = o.fluid.amount } or nil }
end

function SquareMT:AddTileObject(o)
    o.square = self
    table.insert(self.objects, o)
    if isClient() then SIM.clientWorldEdit = (SIM.clientWorldEdit or 0) + 1 end
end

function SquareMT:transmitAddObjectToSquare(o)
    o.square = self
    table.insert(self.objects, o)
    if isServer() then
        local d = describe(o)
        d.x, d.y, d.z = self.x, self.y, self.z
        py_replicate("object", d)
    elseif isClient() then
        SIM.clientWorldEdit = (SIM.clientWorldEdit or 0) + 1
    end
end

function SquareMT:transmitRemoveItemFromSquare(o)
    for i, v in ipairs(self.objects) do
        if v == o then table.remove(self.objects, i) break end
    end
    for i, v in ipairs(self.worldObjects) do
        if v == o then table.remove(self.worldObjects, i) break end
    end
    if isServer() then
        py_replicate("remove", { x = self.x, y = self.y, z = self.z, sprite = o.spriteName,
                                 world = o.class == "IsoWorldInventoryObject" })
    elseif isClient() then
        SIM.clientWorldEdit = (SIM.clientWorldEdit or 0) + 1
    end
    return 0
end

function SquareMT:RemoveTileObjectErosionNoRecalc(o)
    if isClient() then SIM.clientWorldEdit = (SIM.clientWorldEdit or 0) + 1 end
    for i, v in ipairs(self.objects) do
        if v == o then
            table.remove(self.objects, i)
            -- Left stale on purpose. The call says NoRecalc and means it: the
            -- square keeps whatever the engine had already concluded from the
            -- object being there, which is why floors that really had been
            -- lifted went on darkening the ground under them. A caller that
            -- forgets the recalculation leaves this behind for a test to find.
            self.recalced = false
            SIM.staleSquares = (SIM.staleSquares or 0) + 1
            return 0
        end
    end
    return -1
end

function SquareMT:AddWorldInventoryItem(fullType)
    local item = instanceItem(fullType)
    local w = SIM.object(fullType, "IsoWorldInventoryObject")
    w.item = item
    w.square = self
    item.getWorldItem = function() return w end
    table.insert(self.worldObjects, w)
    if isServer() then
        py_replicate("worldItem", { x = self.x, y = self.y, z = self.z, type = fullType })
    elseif isClient() then
        SIM.clientWorldEdit = (SIM.clientWorldEdit or 0) + 1
    end
    return item
end

function SquareMT:removeWorldObject(w)
    if isServer() then error("removeWorldObject on a server does not reach clients") end
    if isClient() then SIM.clientWorldEdit = (SIM.clientWorldEdit or 0) + 1 end
    for i, v in ipairs(self.worldObjects) do
        if v == w then table.remove(self.worldObjects, i) return end
    end
end

--- Whether a square is loaded here: near where one of this runtime's players
--- has been standing long enough for the ground to stream in. A long jump
--- leaves nothing loaded around the new spot for STREAM_TICKS -- in game the
--- cabin took 26 ticks to appear after a beam, and a player held badly fell
--- to their death in that time.
local LOAD_RADIUS = 70
SIM.STREAM_TICKS = 30
function SIM.loaded(x, y)
    for _, p in ipairs(SIM.players) do
        local cx, cy = p.streamX or p.x, p.streamY or p.y
        if math.abs(cx - x) <= LOAD_RADIUS and math.abs(cy - y) <= LOAD_RADIUS then
            return true
        end
    end
    return false
end

--- Advances streaming by one tick for every player here.
function SIM.stream()
    for _, p in ipairs(SIM.players) do
        local cx, cy = p.streamX or p.x, p.streamY or p.y
        local far = math.abs(cx - p.x) > LOAD_RADIUS / 2 or math.abs(cy - p.y) > LOAD_RADIUS / 2
        if not p.streamX then
            p.streamX, p.streamY = p.x, p.y
        elseif far then
            p.streamWait = (p.streamWait or SIM.STREAM_TICKS) - 1
            if p.streamWait <= 0 then
                p.streamX, p.streamY, p.streamWait = p.x, p.y, nil
            end
        else
            p.streamX, p.streamY, p.streamWait = p.x, p.y, nil
        end
    end
end

--- The ground: grass everywhere on the map, a wood of trees in the void
--- cell the cabin is built in, nothing above ground until someone builds.
local function ground(x, y, z)
    local sq = squares[key(x, y, z)]
    if sq then return sq end
    if z ~= 0 then return nil end
    sq = newSquare(x, y, 0)
    local f = SIM.object(x >= SIM.voidX and "blends_natural_01_64" or "blends_natural_01_16")
    f.isFloor = true
    f.square = sq
    table.insert(sq.objects, f)
    if x >= SIM.voidX and (x + y) % 5 == 0 then
        local tree = SIM.object("e_americanholly_1_3")
        tree.square = sq
        table.insert(sq.objects, tree)
    end
    return sq
end

--- For replication and test setup: the square whatever is loaded.
function SIM.rawSquare(x, y, z)
    return squares[key(x, y, z)] or (z == 0 and ground(x, y, z)) or newSquare(x, y, z)
end

local cell = {}
function cell:getGridSquare(x, y, z)
    if not SIM.loaded(x, y) then return nil end
    return squares[key(x, y, z)] or ground(x, y, z)
end
function cell:getOrCreateGridSquare(x, y, z)
    if not SIM.loaded(x, y) then error("orphan square") end
    return self:getGridSquare(x, y, z) or newSquare(x, y, z)
end
function cell:getChunkForGridSquare(x, y)
    return SIM.loaded(x, y) and {} or nil
end
function cell:getZombieList() return jlist(SIM.zombies) end
function cell:getVehicles()
    local loaded = {}
    for _, v in ipairs(SIM.vehicles) do
        if not v.removed and SIM.loaded(v.x, v.y) then table.insert(loaded, v) end
    end
    local i = 0
    return { iterator = function()
        return {
            hasNext = function() return i < #loaded end,
            next = function() i = i + 1; return loaded[i] end,
        }
    end }
end
function cell:addLamppost() SIM.lamps = SIM.lamps + 1 end
function getCell() return cell end
function getWorld() return { getCell = function() return cell end } end
SIM.zombies = {}

---------------------------------------------------------------------------
-- Vehicles
---------------------------------------------------------------------------
SIM.vehicles = {}
SIM.vehicleSerial = 0
IsoDirections = { N = "N", S = "S", E = "E", W = "W" }

---------------------------------------------------------------------------
-- Physics transforms
---------------------------------------------------------------------------
-- zombie.core.physics.Transform and org.joml.Vector3f are both on the engine's
-- Lua exposure allow-list, so mod code can construct them. getOrigin() hands
-- back the live vector rather than a copy, which is what makes the read,
-- mutate, write-back round trip work -- so the stub does the same.
Vector3f = {}
Vector3f.__index = Vector3f
function Vector3f.new(x, y, z)
    return setmetatable({ _x = x or 0, _y = y or 0, _z = z or 0 }, Vector3f)
end
function Vector3f:x() return self._x end
function Vector3f:y() return self._y end
function Vector3f:z() return self._z end
function Vector3f:set(x, y, z) self._x, self._y, self._z = x, y, z return self end

Transform = {}
Transform.__index = Transform
function Transform.new()
    return setmetatable({ origin = Vector3f.new() }, Transform)
end
function Transform:getOrigin() return self.origin end

function SIM.transform() return Transform.new() end

local VehicleMT = {}
VehicleMT.__index = VehicleMT

function SIM.vehicle(script, x, y, z, simId)
    if not simId then
        SIM.vehicleSerial = SIM.vehicleSerial + 1
        simId = SIM.vehicleSerial
    end
    local v = setmetatable({ script = script, x = x, y = y, z = z, simId = simId,
                             modData = {}, seats = {}, hotwired = false,
                             tank = { cap = 20, amount = 0 } }, VehicleMT)
    table.insert(SIM.vehicles, v)
    return v
end

function SIM.findVehicle(simId)
    for _, v in ipairs(SIM.vehicles) do
        if v.simId == simId and not v.removed then return v end
    end
end

function VehicleMT:getScriptName() return self.script end
function VehicleMT:getModData() return self.modData end
function VehicleMT:getX() return self.x end
function VehicleMT:getY() return self.y end
function VehicleMT:getMaxPassengers() return 4 end
function VehicleMT:getCharacter(seat) return self.seats[seat] end

---------------------------------------------------------------------------
-- Height, the way build 42 really does it
---------------------------------------------------------------------------
-- This is the trap that killed the first design for flight, so the simulation
-- reproduces it rather than being kind. BaseVehicle.update() sets a vehicle's
-- z to 0 every single tick, and only puts it back to the physics level if a
-- floor tile exists under the vehicle's centre square at that level or the one
-- below. Raise the physics body with nothing under it and getZ() reads 0 for
-- ever: the ship flies in Bullet and sits on the ground in the game.
--
-- So getZ() here is derived, never stored. A test that forgets to lay the sky
-- plane sees the ship on the deck, exactly as the engine would show it.
local LEVEL_UNITS = 2.4494900703430176

local function floorUnder(v, level)
    if level <= 0 then return true end
    local function at(l)
        local sq = squares[key(math.floor(v.x), math.floor(v.y), l)]
        return sq ~= nil and sq:getFloor() ~= nil
    end
    return at(level) or at(level - 1)
end

function VehicleMT:getZ()
    local level = math.floor((self.bulletY or 0) / LEVEL_UNITS + 0.05)
    if level <= 0 then return 0 end
    if floorUnder(self, level) then return level end
    return 0
end

--- Gravity, for vehicles.
---
--- Without this the simulation cannot reproduce the thing that actually hurts:
--- take the floor out from under a flying ship and she does not blink to the
--- ground, she *falls*, over several ticks, and lands wherever she happens to
--- be -- once, in game, inside a building. A test that only reads the derived
--- z sees the height restored on the next tick and reports success.
function SIM.vehicleGravity()
    for _, v in ipairs(SIM.vehicles or {}) do
        local y = v.bulletY or 0
        if not v.removed and y > 0 then
            local level = math.floor(y / LEVEL_UNITS + 0.05)
            if not floorUnder(v, level) then
                v.bulletY = math.max(0, y - LEVEL_UNITS * 0.34)
            end
            -- The lowest she ever sagged to, recorded here rather than sampled
            -- from the test: a dip lasts a tick or two and is put right by the
            -- next pass, so anything watching from outside sees only the
            -- height afterwards and calls it a success.
            local lvl = v.bulletY / LEVEL_UNITS
            if v.minLevel == nil or lvl < v.minLevel then v.minLevel = lvl end
        end
    end
end

--- The physics body's own height, which is what setWorldTransform writes.
function VehicleMT:setBulletY(v) self.bulletY = v end
function VehicleMT:getBulletY() return self.bulletY or 0 end

function VehicleMT:getWorldTransform(t)
    t = t or SIM.transform()
    t:getOrigin():set(self.x, self.bulletY or 0, self.y)
    t.vehicle = self
    return t
end

function VehicleMT:setWorldTransform(t)
    local o = t:getOrigin()
    self.bulletY = o:y()
    -- A client moving the world's ship is not the same as a client building
    -- in the world, but it is still worth counting separately so a test can
    -- assert that only the driver's machine ever did it.
    if isClient() then
        SIM.vehicleTransformEdit = (SIM.vehicleTransformEdit or 0) + 1
    end
end

function VehicleMT:setPhysicsActive(a) self.physicsActive = a end
function VehicleMT:isPhysicsActive() return self.physicsActive ~= false end
function VehicleMT:isLocalPhysicSim() return SIM_ROLE ~= "server" end
function VehicleMT:setAngles(x, y, z)
    self.angleX, self.angleY, self.angleZ = x, y, z
end
function VehicleMT:getAngleX() return self.angleX or 0 end
function VehicleMT:getAngleY() return self.angleY or 0 end
function VehicleMT:getAngleZ() return self.angleZ or 0 end
--- Levels her off: rotation only, the height is untouched.
function VehicleMT:flipUpright() self.angleX, self.angleZ = 0, 0 end
function VehicleMT:getMaxSpeed() return self.maxSpeed or 70 end
function VehicleMT:setMaxSpeed(v) self.maxSpeed = v end
function VehicleMT:getThrottle() return self.throttle or 0 end
function VehicleMT:getCurrentSteering() return self.steering or 0 end
function VehicleMT:getDriver() return self.seats[0] end
function VehicleMT:getSeat(chr)
    for seat, who in pairs(self.seats) do
        if who == chr then return seat end
    end
    return nil
end
function VehicleMT:isDriver(chr) return self.seats[0] == chr end
function VehicleMT:exit(chr)
    for seat, who in pairs(self.seats) do
        if who == chr then self.seats[seat] = nil end
    end
    chr.vehicle = nil
end
function VehicleMT:repair() self.repaired = true end
function VehicleMT:cheatHotwire(h) self.hotwired = h end
function VehicleMT:getPartById(id)
    if id ~= "GasTank" then return nil end
    local tank = self.tank
    return {
        getContainerCapacity = function() return tank.cap end,
        getContainerContentAmount = function() return tank.amount end,
        setContainerContentAmount = function(_, n) tank.amount = n end,
    }
end
function VehicleMT:transmitPartModData() end

--- A seat container, as the loot window holds when you stand by a vehicle.
--- Once the vehicle is gone, asking it anything throws -- which is exactly
--- what makes vanilla's inventory page flood the log and black the screen.
function VehicleMT:seatContainer()
    if self.seatContainerObj then return self.seatContainerObj end
    local vehicle = self
    -- The part survives its vehicle; that is the whole shape of the bug. Once
    -- the vehicle is gone the part is still there and getVehicle() answers
    -- null, which is how a dead container can be spotted *without* throwing.
    local part = {
        getVehicle = function()
            if vehicle.removed then return nil end
            return vehicle
        end,
    }
    self.seatContainerObj = {
        isVehiclePart = function() return true end,
        getVehiclePart = function() return part end,
        -- Throws exactly as the engine does, and is left here on purpose: a
        -- repeated check built on this call dumps a Java stack trace per call
        -- and floods the log. Nothing in the mod may call it on a timer, and
        -- if something starts to, this is what will fail the test.
        isOccupiedVehicleSeat = function()
            if vehicle.removed then
                SIM.throwingProbes = (SIM.throwingProbes or 0) + 1
                error("Cannot invoke BaseVehicle.getCharacter(int) because " ..
                      "VehiclePart.getVehicle() is null")
            end
            return false
        end,
    }
    return self.seatContainerObj
end
function VehicleMT:permanentlyRemove()
    self.removed = true
    if isServer() then py_replicate("vehicleRemove", { x = 0, y = 0, z = 0, simId = self.simId }) end
    if isClient() then SIM.clientWorldEdit = (SIM.clientWorldEdit or 0) + 1 end
end

--- Spawns a vehicle, as build 42's addVehicleDebug does: on the server the
--- game's vehicle sync then streams it to clients.
function addVehicleDebug(script, dir, skin, sq)
    if isClient() then error("addVehicleDebug on a client") end
    if not sq then return nil end
    local v = SIM.vehicle(script, sq.x + 0.5, sq.y + 0.5, sq.z)
    if isServer() then
        py_replicate("vehicle", { x = sq.x, y = sq.y, z = sq.z, script = script, simId = v.simId })
    end
    return v
end

--- Test helper: a vehicle driven somewhere.
function SIM.driveVehicle(simId, x, y)
    local v = SIM.findVehicle(simId)
    if v then v.x, v.y = x, y end
end

---------------------------------------------------------------------------
-- Players
---------------------------------------------------------------------------
SIM.players = {}
local PlayerMT = {}
PlayerMT.__index = PlayerMT

function SIM.player(name, x, y, z, admin)
    local p = setmetatable({ name = name, x = x, y = y, z = z, modData = {},
                             dead = false, admin = admin == true,
                             inventory = SIM.container(50) }, PlayerMT)
    table.insert(SIM.players, p)
    return p
end

function PlayerMT:getX() return self.x end
function PlayerMT:getY() return self.y end
function PlayerMT:getZ() return self.z end
function PlayerMT:setX(v) self.x = v end
function PlayerMT:setY(v) self.y = v end
function PlayerMT:setZ(v) self.z = v end
function PlayerMT:setLastX() end
function PlayerMT:setLastY() end
function PlayerMT:setLastZ(v) self.lastZ = v end
function PlayerMT:setbFalling() end
function PlayerMT:setFallTime() end
function PlayerMT:setLastFallSpeed() end
function PlayerMT:clearFallDamage() self.fallDamage = 0 end

--- Gravity, the way the engine moves a character: from its *last* height, not
--- the height Lua last set. A hold that only calls setZ still falls. Landing
--- two or more floors down kills, which is what happened in game.
function SIM.settleUI()
    if SIM.radial and SIM.radial.settle then SIM.radial:settle() end
end

function SIM.gravity()
    if SIM_ROLE == "server" then return end
    for _, p in ipairs(SIM.players) do
        -- Somebody riding in a vehicle is placed by the engine, not by
        -- gravity: BaseVehicle.update() sets every seated character's x, y and
        -- z from the vehicle each tick, with the z taken from the vehicle's
        -- own (floor-clamped) height. So the crew ride up with the ship and
        -- come down with it, and cannot fall out of a seat.
        if not p.dead and p.vehicle and not p.vehicle.removed then
            p.x, p.y = p.vehicle.x, p.vehicle.y
            p.z = p.vehicle:getZ()
            p.lastZ, p.fallFrom = p.z, nil
        elseif not p.dead then
            local z = p.lastZ or p.z
            local sq = squares[math.floor(p.x) .. "," .. math.floor(p.y) .. "," .. math.floor(z)]
                       or (math.floor(z) == 0 and SIM.loaded(p.x, p.y) and cell:getGridSquare(math.floor(p.x), math.floor(p.y), 0))
            local floored = sq and sq:getFloor() ~= nil
            if z > 0 and not floored then
                p.fallFrom = p.fallFrom or z
                z = math.max(0, z - 0.25)
            elseif p.fallFrom then
                if p.fallFrom - z >= 2 then
                    p.dead = true
                    table.insert(SIM.log, "SIM DEATH " .. p.name .. " fell from " .. p.fallFrom)
                end
                p.fallFrom = nil
            end
            p.z, p.lastZ = z, z
        end
    end
end
function PlayerMT:getVehicle() return self.vehicle end
function PlayerMT:isbFalling() return false end
function PlayerMT:getJoypadBind() return -1 end
function PlayerMT:getUsername() return self.name end
function PlayerMT:isDead() return self.dead end
function PlayerMT:getModData() return self.modData end
function PlayerMT:getPlayerNum() return 0 end
function PlayerMT:isLocalPlayer() return SIM_ROLE ~= "server" end
function PlayerMT:getRole()
    local admin = self.admin
    return { hasAdminPower = function() return admin end }
end
function PlayerMT:getInventory() return self.inventory end
function PlayerMT:getPrimaryHandItem() return nil end
function PlayerMT:getSecondaryHandItem() return nil end
function PlayerMT:setHaloNote(text)
    table.insert(SIM.notes, { player = self.name, text = text })
end

function getPlayer() return SIM.players[1] end
function getSpecificPlayer(i) return SIM.players[i + 1] end
function getOnlinePlayers()
    if SIM_ROLE == "sp" then return jlist({}) end
    return jlist(SIM.players)
end
IsoPlayer = { getPlayers = function() return jlist(SIM.players) end }

---------------------------------------------------------------------------
-- Zombies
---------------------------------------------------------------------------
function SIM.zombie(x, y, z, remote)
    local zed = { x = x, y = y, z = z, remote = remote }
    function zed:getX() return self.x end
    function zed:getY() return self.y end
    function zed:getZ() return self.z end
    function zed:setX(v) self.x = v end
    function zed:setY(v) self.y = v end
    function zed:setLastX() end
    function zed:setLastY() end
    function zed:setTarget() end
    function zed:setStaggerBack() end
    function zed:isRemoteZombie() return self.remote end
    table.insert(SIM.zombies, zed)
    return zed
end

---------------------------------------------------------------------------
-- Server options and sandbox
---------------------------------------------------------------------------
SIM.antiCheatSpeed = 2
function getServerOptions()
    -- As the engine does: AntiCheatSpeed is an enum option, so getInteger
    -- answers nil and getOption answers the value as a string.
    return {
        getInteger = function() return nil end,
        getOption = function(_, name)
            if name == "AntiCheatSpeed" then return tostring(SIM.antiCheatSpeed) end
            return nil
        end,
    }
end
SandboxVars = { TrekShuttle = { Access = 1, TransporterLimit = 1 } }

-- The world's map folders, void map included.
function getLotDirectories()
    local dirs = { "TrekShuttle", "Muldraugh, KY" }
    local list = jlist(dirs)
    list.contains = function(_, name)
        for _, d in ipairs(dirs) do if d == name then return true end end
        return false
    end
    return list
end

---------------------------------------------------------------------------
-- Global mod data and the network
---------------------------------------------------------------------------
local globalData = {}
ModData = {}
function ModData.getOrCreate(k)
    globalData[k] = globalData[k] or {}
    return globalData[k]
end
function ModData.get(k) return globalData[k] end
function ModData.exists(k) return globalData[k] ~= nil end
function ModData.add(k, t) globalData[k] = t end
function ModData.transmit(k)
    if SIM_ROLE == "sp" then return end
    py_transmit(k, globalData[k])
end
function ModData.request(k)
    if SIM_ROLE ~= "client" then return end
    py_request(k)
end
SIM.globalData = globalData

function sendClientCommand(player, module, command, args)
    if SIM_ROLE == "server" then error("sendClientCommand on a server") end
    py_client_command(player.name, module, command, args)
end

function sendServerCommand(a, b, c, d)
    if SIM_ROLE ~= "server" then return end   -- does nothing in single player
    if type(a) == "table" then
        py_server_command(a.name, b, c, d)
    else
        py_server_command(nil, a, b, c)
    end
end

---------------------------------------------------------------------------
-- Just enough UI for the client files to load
---------------------------------------------------------------------------
local function derivable(name)
    local cls = { Type = name }
    cls.__index = cls
    function cls:derive(n)
        local sub = setmetatable({ Type = n }, { __index = self })
        sub.__index = sub
        return sub
    end
    function cls.new(self, x, y, w, h)
        return setmetatable({ x = x, y = y, width = w, height = h, children = {} }, self)
    end
    return cls
end
ISPanelJoypad = derivable("ISPanelJoypad")
ISButton = derivable("ISButton")
ISWorldMap = { onMouseUp = function() end, render = function() end,
               onJoypadDown = function() end }
ISWorldObjectContextMenu = { setTest = function() return true end }
-- One loot window per player, as the game has.
SIM.loot = {}
function getPlayerLoot(i)
    SIM.loot[i] = SIM.loot[i] or { inventory = nil, refreshed = 0 }
    local page = SIM.loot[i]
    page.setNewContainer = function(self, c) self.inventory = c end
    page.refreshBackpacks = function(self) self.refreshed = self.refreshed + 1 end
    return page
end
SIM.floorContainer = { isVehiclePart = function() return false end }
ISInventoryPage = { GetFloorContainer = function() return SIM.floorContainer end }

-- The radial menu, modelled as the toggle it really is.
--
-- Vanilla's showRadialMenu clears the menu and, if it was already up, takes it
-- down and returns -- so isReallyVisible() is true only on the press that
-- closes it. A mod hook that adds its slices behind "if the menu is visible"
-- therefore runs only while the menu is being dismissed and never when it is
-- being built, which is a feature that silently does not exist. That happened
-- (2026-09-17): neither "go aboard" nor "take her up" was ever added, in any
-- build, and from the outside flight simply looked broken.
SIM.radial = { slices = {}, visible = false }

-- isReallyVisible() is false for a frame after the menu is opened, and that
-- single fact is the whole trap. addToUIManager() calls UIManager.AddUI, which
-- appends to a *pending* list (UIManager.toAdd); isReallyVisible() asks whether
-- the element is in the live list (UIManager.getUI().contains). So it answers
-- false on the press that opens the menu, and vanilla returns early on the
-- press that closes it -- there is no moment at which a hook guarded on
-- "is it visible" can add anything at all. Modelled here so that guard fails
-- the test instead of the player.
function getPlayerRadialMenu()
    local m = SIM.radial
    if m.addSlice then return m end
    function m:isReallyVisible() return self.visible end
    function m:clear() self.slices = {} end
    function m:undisplay() self.visible, self.pending = false, false end
    --- Promotes a just-opened menu to really visible, a tick later.
    function m:settle()
        if self.pending then self.visible, self.pending = true, false end
    end
    function m:addSlice(text, texture, fn, ...)
        table.insert(self.slices, { text = text, texture = texture, fn = fn })
    end
    function m:titles()
        local out = {}
        for _, s in ipairs(self.slices) do table.insert(out, s.text) end
        return table.concat(out, ",")
    end
    return m
end

ISVehicleMenu = {
    showRadialMenu = function(playerObj)
        local m = getPlayerRadialMenu()
        m:clear()
        if m:isReallyVisible() then m:undisplay() return end
        m:addSlice("IGUI_SwitchSeat")
        m:addSlice("IGUI_ExitVehicle")
        m.pending = true          -- addToUIManager: live only from next frame
    end,
    showRadialMenuOutside = function(playerObj)
        local m = getPlayerRadialMenu()
        if m:isReallyVisible() then m:undisplay() return end
        m:clear()
        m.pending = true
    end,
    FillMenuOutsideVehicle = function() end, onEnter = function() end,
    processEnter = function() end, processShiftEnter = function() end,
    onExit = function() end,
    getVehicleToInteractWith = function() return nil end,
}
ISCarMechanicsOverlay = { CarList = {} }
ImageScale = {}
package.preload["Vehicles/ISUI/ISVehicleMenu"] = function() return true end
package.preload["Vehicles/ISUI/ISCarMechanicsOverlay"] = function() return true end
package.preload["Vehicles/ISUI/ISVehicleSeatUI"] = function() return true end
UIFont = { Small = 1, Medium = 2 }
