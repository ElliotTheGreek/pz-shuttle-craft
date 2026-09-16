--[[ Shuttlecraft -- shared helpers.

    The build code touches a lot of engine surface at once and a single nil
    from one call should never take down the whole cabin. Everything here is
    defensive on purpose: wrapped calls, tolerant square lookups, and one
    place that owns the persisted state.
]]

require "TREK/TREK_Config"

TREK = TREK or {}
local C = TREK.Config

local U = {}
TREK.Util = U

---------------------------------------------------------------------------
-- Logging
---------------------------------------------------------------------------
function U.log(fmt, ...)
    local msg = fmt
    if select("#", ...) > 0 then
        local ok, formatted = pcall(string.format, fmt, ...)
        if ok then msg = formatted end
    end
    print(C.ModPrefix .. " " .. tostring(msg))
end

function U.debug(fmt, ...)
    if C.Debug then U.log(fmt, ...) end
end

-- Errors are noisy the first time and silent afterwards, so a per-tick
-- failure cannot flood console.txt.
local reported = {}
function U.warnOnce(key, fmt, ...)
    if reported[key] then return end
    reported[key] = true
    U.log("WARN (" .. tostring(key) .. ") " .. tostring(fmt), ...)
end

--- Guards a call that is about to be repeated over hundreds of squares.
---
--- Returns a callable that stops trying after its first failure. This matters
--- more than it looks: a wrong method name inside a per-square loop does not
--- fail quietly, it throws out of Java and the engine dumps a stack trace for
--- every single square. At cabin scale that is hundreds of dumps, which locks
--- the game up hard enough to look like a crash. One failure, one warning,
--- then the pass carries on without that step.
function U.batch(label)
    local broken = false
    return function(fn)
        if broken then return nil end
        local ok, result = pcall(fn)
        if not ok then
            broken = true
            U.warnOnce(label, tostring(result))
            return nil
        end
        return result
    end
end

--- Runs fn, logs the first failure under `label` and returns nil on error.
---
--- For a call that happens once. U.batch is for a call that repeats: U.try
--- silences the *Lua* warning after the first failure but keeps calling, and
--- the engine keeps dumping a Java stack trace every single time.
function U.try(label, fn, ...)
    local args = { ... }
    local ok, result = pcall(function() return fn(unpack(args)) end)
    if not ok then
        U.warnOnce(label, tostring(result))
        return nil
    end
    return result
end

---------------------------------------------------------------------------
-- Persisted state
---------------------------------------------------------------------------
-- One table, saved with the world.
--
-- `landed` is the whole model of where the ship is: true and it is sitting on
-- the ground at x,y,z; false and it is overhead, which is not a position at
-- all. The transporter works either way, the hatch only works landed, and
-- nothing else needs to know.
function U.state()
    local s = ModData.getOrCreate(C.StateKey)
    -- Every field falls back to what is already there, so raising the schema
    -- re-runs this block without losing anything.
    if s.schema ~= 1 then
        s.schema      = 1
        s.version     = C.Version
        s.landed      = s.landed == true
        s.x           = s.x or 0
        s.y           = s.y or 0
        s.z           = s.z or 0
        s.everLanded  = s.everLanded == true
        s.inside      = s.inside == true
        s.returnX     = s.returnX or nil
        s.returnY     = s.returnY or nil
        s.returnZ     = s.returnZ or nil
        s.built       = s.built == true
        s.rev         = s.rev or 0
        s.bookmarks   = s.bookmarks or {}
        s.destination = s.destination or nil
        s.ghosts      = s.ghosts or {}
    end
    -- Belt and braces: a world saved between two builds at the same schema
    -- can be missing a list every read of it assumes is a table.
    s.ghosts = s.ghosts or {}
    s.bookmarks = s.bookmarks or {}
    -- Additive flight fields keep old saves compatible. Active piloting is
    -- transient; only the ground directly below the airborne ship is saved.
    s.flightX = s.flightX or (s.landed and s.x or s.returnX)
    s.flightY = s.flightY or (s.landed and s.y or s.returnY)
    s.flightZ = s.flightZ or (s.landed and s.z or s.returnZ or 0)
    return s
end

---------------------------------------------------------------------------
-- Geometry
---------------------------------------------------------------------------
function U.cellSize()
    if getCellSizeInSquares then
        local n = U.try("cellSize", getCellSizeInSquares)
        if n and n > 0 then return n end
    end
    return 256
end

--- North-west corner of the cabin, in world squares.
function U.cabinOrigin()
    local size = U.cellSize()
    return C.InteriorCell.x * size + C.RoomOffset,
           C.InteriorCell.y * size + C.RoomOffset
end

--- Absolute position of an offset within the cabin.
function U.at(ox, oy)
    local rx, ry = U.cabinOrigin()
    return rx + ox, ry + oy
end

--- Where a player arriving aboard is put down: the transporter pad.
function U.padSpot()
    local x, y = U.at(C.Landing.x, C.Landing.y)
    return x, y, C.CabinZ
end

--- True when the coordinates fall anywhere in the strip of world the cabin
--- occupies, its void margin included. Deliberately ignores z: a player who
--- has somehow ended up over the cabin on another level is still "inside" as
--- far as menus and the phaser sweep are concerned.
function U.isInterior(x, y)
    if not x or not y then return false end
    local cx, cy = U.cabinOrigin()
    local m = C.ClearMargin
    return x >= cx - m and x <= cx + C.CabinW + m
       and y >= cy - m and y <= cy + C.CabinL + m
end

function U.isInteriorPlayer(player)
    if not player then return false end
    return U.isInterior(player:getX(), player:getY())
end

--- True when a position is inside the cabin walls, not merely in its cell.
function U.isAboard(x, y, z)
    if not U.isInterior(x, y) then return false end
    if z and math.floor(z) ~= C.CabinZ then return false end
    local cx, cy = U.cabinOrigin()
    return C.inShape(math.floor(x) - cx, math.floor(y) - cy)
end

---------------------------------------------------------------------------
-- Squares
---------------------------------------------------------------------------
function U.cell()
    return U.try("getCell", getCell)
end

--- True when the chunk that owns this square is streamed in.
---
--- This gates every piece of construction. A square handed back by
--- getOrCreateGridSquare for a chunk the world has not loaded is an orphan:
--- it has no chunk behind it, and the first engine call that touches it --
--- addFloor, AddTileObject -- throws out of Java. The cabin sits in a cell
--- nothing else ever visits, so the only thing that streams it in is a player
--- standing there, and nothing may be built until that has happened.
function U.chunkLoaded(x, y, z)
    local cell = U.cell()
    if not cell then return false end
    local chunk = U.try("getChunkForGridSquare", function()
        return cell:getChunkForGridSquare(math.floor(x), math.floor(y), math.floor(z or 0))
    end)
    return chunk ~= nil
end

--- Grid square lookup. With create=true a square is made if its chunk is
--- loaded; if the chunk is absent this returns nil rather than an orphan.
function U.square(x, y, z, create)
    x, y, z = math.floor(x), math.floor(y), math.floor(z)
    local cell = U.cell()
    if not cell then return nil end

    local sq = U.try("getGridSquare", function() return cell:getGridSquare(x, y, z) end)
    if sq or not create then return sq end

    if not U.chunkLoaded(x, y, z) then return nil end

    return U.try("getOrCreateGridSquare", function()
        return cell:getOrCreateGridSquare(x, y, z)
    end)
end

--- Iterates the objects on a square, tolerating a nil list.
function U.eachObject(sq, fn)
    if not sq then return end
    local objs = U.try("getObjects", function() return sq:getObjects() end)
    if not objs then return end
    local n = U.try("objects.size", function() return objs:size() end) or 0
    for i = 0, n - 1 do
        local o = U.try("objects.get", function() return objs:get(i) end)
        if o then
            if fn(o, i) == false then return end
        end
    end
end

--- Every object on the square whose sprite matches `name`.
function U.findSprite(sq, name)
    local found = nil
    U.eachObject(sq, function(o)
        local spr = o:getSprite()
        if spr and spr:getName() == name then
            found = o
            return false
        end
    end)
    return found
end

--- Adds an IsoObject with the given sprite unless one is already there.
--- Returns the object (existing or new) and whether it was created now.
function U.addObject(sq, sprite, tag)
    if not sq or not sprite then return nil, false end
    local existing = U.findSprite(sq, sprite)
    if existing then return existing, false end

    local obj = U.try("IsoObject.new", function()
        return IsoObject.new(sq, sprite, tag or "")
    end)
    if not obj then return nil, false end

    U.try("AddTileObject", function() sq:AddTileObject(obj) end)
    if tag then
        local md = U.try("obj.getModData", function() return obj:getModData() end)
        if md then md.TREK = tag end
    end
    return obj, true
end

--- Strips a square back to nothing. Used to carve the cabin out of the
--- procedural wilderness the engine grows in unmapped cells: without this the
--- ship reads as a shed standing in a wood.
---
--- Deliberately preserves anything the mod tagged and anything lying on the
--- ground, so both clearing passes are safe to repeat as chunks stream in.
function U.clearSquare(sq, removeFloor)
    if not sq then return 0 end
    local doomed = {}
    U.eachObject(sq, function(o)
        local md = U.try("md", function() return o:getModData() end)
        if md and md.TREK then return end            -- never strip our own work
        -- Dropped items and the world models we place as items live here too;
        -- stripping those would eat the helm and anything a player put down.
        if instanceof(o, "IsoWorldInventoryObject") then return end
        if not removeFloor then
            local floor = U.try("floor", function() return sq:getFloor() end)
            if floor and o == floor then return end
        end
        table.insert(doomed, o)
    end)
    local removed = 0
    for _, o in ipairs(doomed) do
        if U.try("removeObject", function()
            sq:RemoveTileObjectErosionNoRecalc(o)
            return true
        end) then removed = removed + 1 end
    end
    return removed
end

--- Adds the floor for a square, creating the square if needed.
function U.addFloor(x, y, z, sprite)
    local sq = U.square(x, y, z, true)
    if not sq then return nil end
    local floor = U.try("getFloor", function() return sq:getFloor() end)
    if not floor then
        U.try("addFloor", function() sq:addFloor(sprite) end)
    end
    return sq
end

--- Container objects need their ItemContainer built from the sprite
--- properties; map-loaded objects get this for free, runtime ones do not.
--- Returns the container object and whether it was created just now.
---
--- The second return matters: a rebuild must not touch the contents of a
--- container that already exists. The ship is meant to be lived in -- what
--- the player eats stays eaten -- and stocking an existing locker again would
--- both refill it and pile a second helping on top of the first.
function U.addContainer(sq, sprite, tag)
    local obj, created = U.addObject(sq, sprite, tag)
    if not obj then return nil, false end

    -- BuildingEd-derived furniture may already exist as a visual IsoObject
    -- without the ItemContainer that map-loaded objects receive automatically.
    -- Initialize whenever the inventory is absent, not only when the sprite
    -- object itself was created during this call.
    local container = U.try("getContainer", function() return obj:getContainer() end)
    if not container then
        container = U.try("getItemContainer", function() return obj:getItemContainer() end)
    end
    if created or not container then
        U.try("createContainers", function()
            obj:createContainersFromSpriteProperties()
        end)
    end
    return obj, created
end

function U.containerOf(obj)
    if not obj then return nil end
    local c = U.try("getContainer", function() return obj:getContainer() end)
    if c then return c end
    return U.try("getItemContainer", function() return obj:getItemContainer() end)
end

-- Where each loot list got to, so the next container carries on from there.
local stockCursor = {}

--- The ways an item can be made and put in a container.
---
--- There is more than one because which of them exists is a property of the
--- build and not of the jar. `zombie.inventory.InventoryItemFactory` is a real
--- class with a real static `CreateItem(String)` on it -- pzapi.py will show
--- it to you -- and in build 42 it is **not exposed to Lua**: the global is
--- null and every call throws `attempted index: CreateItem of non-table`.
--- That is how nineteen containers came to be built perfectly and stocked
--- with nothing at all, twice.
---
--- Only `zombie.Lua.LuaManager$GlobalObject` statics are Lua globals, which is
--- what `instanceItem` is and what vanilla uses in 187 places. It goes first;
--- the others are kept because being wrong about this is expensive and the
--- cost of carrying them is two pcalls, once.
local addStrategies = {
    { name = "instanceItem", add = function(container, id)
        local item = instanceItem(id)
        if not item then return false end
        container:AddItem(item)
        return true
    end },
    { name = "container:AddItem(id)", add = function(container, id)
        return container:AddItem(id) ~= nil
    end },
    { name = "InventoryItemFactory", add = function(container, id)
        local item = InventoryItemFactory.CreateItem(id)
        if not item then return false end
        container:AddItem(item)
        return true
    end },
}

-- The one that worked, remembered after the first item.
local addStrategy = nil

local function sizeOf(container)
    local items = U.try("getItems", function() return container:getItems() end)
    return items and items:size() or 0
end

--- Adds one item and proves that the inventory actually grew.
---
--- The proof is the point. Every one of these strategies can fail silently --
--- a nil back, a throw swallowed by pcall, a container at capacity dropping
--- what it was handed -- and all three look identical from here. Counting the
--- contents before and after is the only answer that cannot lie.
local function addVerified(container, id)
    if not container or not id then return false end
    local before = sizeOf(container)

    local function attempt(way)
        local ok = pcall(way.add, container, id)
        return ok and sizeOf(container) > before
    end

    if addStrategy then
        if attempt(addStrategy) then return true end
        -- A strategy that has worked before and fails on one id means a bad
        -- id, not a broken build. Name the id and keep the strategy.
        U.warnOnce("item:" .. id, "could not add " .. id)
        return false
    end

    for _, way in ipairs(addStrategies) do
        if attempt(way) then
            addStrategy = way
            U.log("stocking containers via %s", way.name)
            return true
        end
    end
    U.warnOnce("item:" .. id,
               "no way to put " .. id .. " in a container works in this build")
    return false
end

local function finishStock(container)
    U.try("container.explored", function() container:setExplored(true) end)
    U.try("container.dirty", function() container:setDirty(true) end)
    U.try("container.drawDirty", function() container:setDrawDirty(true) end)
end

--- Fills a container with `count` picks from `list`.
---
--- Each list keeps a rolling position, so consecutive containers continue
--- through it rather than all starting at the top. Without this every locker
--- in the cabin holds an identical handful and most of the list never appears
--- in the world at all.
function U.stock(obj, list, count)
    local container = U.containerOf(obj)
    if not container or not list or #list == 0 then return 0 end

    local key = tostring(list)
    local start = stockCursor[key] or 0
    local added = 0
    for i = 0, count - 1 do
        local id = list[((start + i) % #list) + 1]
        if addVerified(container, id) then added = added + 1 end
    end
    stockCursor[key] = (start + count) % #list
    if added > 0 then finishStock(container) end
    return added
end

--- Resets the rolling positions, so a rebuild lays the same items out the
--- same way it did the first time.
function U.resetStockCursors()
    stockCursor = {}
end

--- Forgets which way of adding items worked, so the next build probes again.
---
--- Called at the start of a build rather than left latched for the session:
--- the probe costs two pcalls once, and it makes every build log the line
--- that says which path it is using. That line is what turns "the containers
--- are empty again" into a one-line answer.
function U.resetItemStrategy()
    addStrategy = nil
end

--- A container's capacity and what it is currently carrying, or nil when the
--- engine will not say.
---
--- Capacity is the tile's own ContainerCapacity property -- 40 for a locker,
--- 15 for an oven, 5 for a microwave -- which is why this is read back off the
--- object rather than guessed at per fitting.
local function loadOf(container)
    local cap = U.try("container.capacity", function()
        return container:getCapacity()
    end)
    if type(cap) ~= "number" or cap <= 0 then return nil end
    local held = U.try("container.weight", function()
        return container:getContentsWeight()
    end)
    if type(held) ~= "number" then return nil end
    return cap, held
end

--- How full a container is, 0..1, or nil when the engine will not say.
function U.fillLevel(obj)
    local container = U.containerOf(obj)
    if not container then return nil end
    local cap, held = loadOf(container)
    if not cap then return nil end
    return held / cap
end

--- How many items a container holds.
function U.itemCount(obj)
    local container = U.containerOf(obj)
    if not container then return 0 end
    local items = U.try("container.items", function() return container:getItems() end)
    return items and items:size() or 0
end

--- Stocks a container until it is `fraction` full by weight.
---
--- This is the difference between a cabin that looks provisioned and one that
--- looks staged. U.stock puts a fixed number of items in, which cannot be
--- right for every fitting at once: eight tins fill a microwave past the brim
--- and leave a 40-unit locker at a fifth. Filling to a fraction of the
--- container's own capacity gives every one of them the same look.
---
--- `cap` bounds the item count whatever the weight says, because a list of
--- bandages at 0.1 each would need two hundred of them to reach half a locker.
--- Whichever limit binds first stops the fill, so a light list gives a heaped
--- container that is under target by weight and that is the intended trade.
---
--- Falls back to filling to the item cap when the engine will not report a
--- capacity, so a container type with no ContainerCapacity property is still
--- stocked rather than skipped.
---
--- Returns the number of items added and the fill level reached.
function U.fill(obj, list, fraction, cap)
    local container = U.containerOf(obj)
    if not container or not list or #list == 0 then return 0, nil end

    fraction = fraction or C.FillFraction
    cap = cap or C.FillItemCap

    local capacity, held = loadOf(container)
    local target = capacity and capacity * fraction or nil

    local key = tostring(list)
    local start = stockCursor[key] or 0
    local added, taken = 0, 0

    while taken < cap do
        if target and held >= target then break end
        local id = list[((start + taken) % #list) + 1]
        taken = taken + 1
        if addVerified(container, id) then added = added + 1 end
        if target then
            local _, now = loadOf(container)
            -- A reading that fails mid-fill must not stall the loop: `taken`
            -- still climbs, so the item cap ends it either way.
            held = now or held
        end
    end

    stockCursor[key] = (start + taken) % #list
    if added > 0 then finishStock(container) end
    return added, U.fillLevel(obj)
end

--- Puts `copies` of every entry in `list` into a container, then reads the
--- container back and returns which ids did not land.
---
--- U.stock walks a list and hopes; this guarantees coverage and then proves
--- it. Containers have a capacity and once it is reached the engine drops
--- further items without raising anything, so a locker meant to hold one of
--- everything can quietly end up holding a handful.
function U.stockEach(obj, list, copies)
    local container = U.containerOf(obj)
    if not container or not list then return {}, list or {} end
    copies = copies or 1

    local added = 0
    for _, id in ipairs(list) do
        for _ = 1, copies do
            if addVerified(container, id) then added = added + 1 end
        end
    end
    if added > 0 then finishStock(container) end

    local present = {}
    U.try("readBack", function()
        local items = container:getItems()
        if not items then return end
        for i = 0, items:size() - 1 do
            local it = items:get(i)
            if it then
                local t = it:getFullType()
                present[t] = (present[t] or 0) + 1
            end
        end
    end)

    local missing = {}
    for _, id in ipairs(list) do
        if not present[id] then table.insert(missing, id) end
    end
    return present, missing
end

---------------------------------------------------------------------------
-- Misc
---------------------------------------------------------------------------
function U.player(index)
    if index then
        return U.try("getSpecificPlayer", function() return getSpecificPlayer(index) end)
    end
    return U.try("getPlayer", getPlayer)
end

--- Moves a character without leaving the old position behind, which the
--- engine otherwise interpolates towards and reads as a fall.
function U.teleport(player, x, y, z)
    if not player then return false end
    return U.try("teleport", function()
        player:setX(x + 0.5)
        player:setY(y + 0.5)
        player:setZ(z)
        player:setLastX(x + 0.5)
        player:setLastY(y + 0.5)
        player:setLastZ(z)
        return true
    end) == true
end

--- A halo note over the player's head, in the transporter's own blue.
function U.note(player, text, r, g, b)
    if not player or not text then return end
    U.try("haloNote", function()
        player:setHaloNote(text, r or 140, g or 200, b or 255, 220)
    end)
end

function U.dist2(x1, y1, x2, y2)
    local dx, dy = x1 - x2, y1 - y2
    return dx * dx + dy * dy
end

return U
