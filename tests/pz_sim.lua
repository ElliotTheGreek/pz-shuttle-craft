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
function SquareMT:getVehicleContainer() return nil end
function SquareMT:setHaveElectricity(v) self.power = v end

function SquareMT:addFloor(sprite)
    local f = SIM.object(sprite)
    f.isFloor = true
    f.square = self
    table.insert(self.objects, 1, f)
    if isServer() then
        py_replicate("floor", { x = self.x, y = self.y, z = self.z, sprite = sprite })
    elseif isClient() then
        SIM.clientWorldEdit = (SIM.clientWorldEdit or 0) + 1
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
        if v == o then table.remove(self.objects, i) return 0 end
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
function cell:addLamppost() SIM.lamps = SIM.lamps + 1 end
function getCell() return cell end
function getWorld() return { getCell = function() return cell end } end
SIM.zombies = {}

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
function SIM.gravity()
    if SIM_ROLE == "server" then return end
    for _, p in ipairs(SIM.players) do
        if not p.dead then
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
UIFont = { Small = 1, Medium = 2 }
