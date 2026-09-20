--[[ Shuttlecraft -- cabin construction, on the server.

    The cabin is generated at runtime in an otherwise empty cell rather than
    shipped as a map, so the mod needs no TileZed-built lots. It is raised
    lazily: nothing exists until somebody is aboard for the first time.

    This runs where the world is authoritative -- single player, or the server
    -- and never on a client connected to one. Every object is made complete
    first (tagged, containers created and stocked, water store added) and then
    added with transmitAddObjectToSquare, which puts it on the square here and,
    on a server, sends the finished object to every client that can see it.
    One send per object, with its contents inside. That is how vanilla builds
    furniture from the server, and it is the only way a second player sees the
    same lockers with the same things in them.

    One compartment, one storey. The deck, walls, lamps and helm item are
    generated here; every fitting and locker is authored in BuildingEd and
    read out of TREK_InteriorLayout.lua:

        bow (oy 0)   the monitor wall, a television and two crew seats
        port (ox 0)  the galley: fridge, oven, two counters, replicator berth
        stbd (ox 3)  armoury, rations and sick-bay lockers, then the biobed
        amidships    the helm at 2,1 and the transporter pad at 2,2

    Nothing may be built into a chunk that is not loaded, and chunks load only
    around a player, so TREK_Server only asks for a build once somebody who
    has reported themselves aboard is standing there.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
local L = require "TREK/TREK_InteriorLayout"
require "TREK/TREK_Power"
-- For the berth's offsets: the replicator's alcove stands where the layout's
-- `replicator` tag is, and one file should own that lookup.
require "TREK/TREK_Replicator"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local B = {}
TREK.Build = B

-- Logged once rather than on every attempt while the chunks stream in.
B.upgradeNoted = false

local at = U.at

local function inShape(ox, oy)
    return C.inShape(ox, oy)
end

---------------------------------------------------------------------------
-- Adding and removing objects, synced
---------------------------------------------------------------------------
--- Adds a finished object to its square. transmitAddObjectToSquare adds it
--- locally in every setup and sends it to clients when this is a server.
local function addSynced(sq, obj)
    return U.try("transmitAddObjectToSquare", function()
        sq:transmitAddObjectToSquare(obj, -1)
        return true
    end) == true
end

--- Removes an object. On a server this removes it and tells the clients; in
--- single player the same call removes it locally.
local function removeSynced(sq, obj)
    return U.try("transmitRemoveItemFromSquare", function()
        sq:transmitRemoveItemFromSquare(obj)
        return true
    end) == true
end

--- An object with this sprite on the square, made and added unless one is
--- already there. `prepare(obj)` runs on a new object before it is sent, so
--- whatever it adds -- containers, stock, water -- arrives with it.
---
--- Returns the object and whether it was created now.
local function place(sq, sprite, tag, prepare)
    if not sq or not sprite then return nil, false end
    local existing = U.findSprite(sq, sprite)
    if existing then return existing, false end

    local obj = U.try("IsoObject.new", function()
        return IsoObject.new(sq, sprite, tag or "")
    end)
    if not obj then return nil, false end
    if tag then
        U.try("tagObject", function() obj:getModData().TREK = tag end)
    end
    if prepare then U.try("prepare:" .. tostring(tag), prepare, obj) end
    if not addSynced(sq, obj) then return nil, false end
    return obj, true
end

---------------------------------------------------------------------------
-- Clearing the site
---------------------------------------------------------------------------
-- The deck's own floor sprites. Floors carry no tag (addFloor makes them),
-- so they are recognised by sprite and never stripped: a player may be
-- standing on one while a later build tidies up.
local deckSprites = nil

local function isDeck(o)
    if not deckSprites then
        deckSprites = { [C.Sprites.deckFloor] = true, [C.Sprites.padFloor] = true }
        if L.floor then deckSprites[L.floor] = true end
    end
    local name = U.try("spriteName", function()
        local spr = o:getSprite()
        return spr and spr:getName()
    end)
    return name ~= nil and deckSprites[name] == true
end

--- Strips a square back to nothing, keeping the mod's own objects, the deck
--- and anything lying on the ground. The interior cell is unmapped, so the
--- engine grows procedural wilderness there; left alone the ship reads as a
--- hut in a wood. Safe to repeat as chunks stream in late.
local function clearSquare(sq)
    if not sq then return 0 end
    local doomed = {}
    U.eachObject(sq, function(o)
        local md = U.try("md", function() return o:getModData() end)
        if md and md.TREK then return end
        if instanceof(o, "IsoWorldInventoryObject") then return end
        if isDeck(o) then return end
        table.insert(doomed, o)
    end)
    local removed = 0
    for _, o in ipairs(doomed) do
        if removeSynced(sq, o) then removed = removed + 1 end
    end
    return removed
end

---------------------------------------------------------------------------
-- The refit migration
---------------------------------------------------------------------------
--- Spills a container's contents onto the transporter pad.
---
--- The ship is meant to be lived in and what is in a locker is the player's,
--- so a locker that is about to stop existing hands its contents back rather
--- than eating them. The pad because it is the one square everybody arrives
--- on and nothing is ever placed on.
---
--- The live InventoryItem is moved, not its id: recreating from the full type
--- would reset a hypospray's doses and a magazine's rounds, which is the
--- quiet half of losing it. AddWorldInventoryItem's (InventoryItem, f, f, f)
--- overload is what vanilla's own scenarios use.
local function spillToPad(obj)
    local container = U.containerOf(obj)
    if not container then return 0 end

    local px, py = at(C.Landing.x, C.Landing.y)
    local pad = U.square(px, py, C.CabinZ, false)
    if not pad then return 0 end

    local doomed = {}
    U.try("spill:list", function()
        local items = container:getItems()
        if not items then return end
        for i = 0, items:size() - 1 do
            local it = items:get(i)
            if it then table.insert(doomed, it) end
        end
    end)

    local spilled = 0
    local join = U.batch("spill.toPad")
    for _, item in ipairs(doomed) do
        -- The closure returns true on purpose: U.batch's join hands back
        -- whatever the call returned, and a function returning nothing is
        -- indistinguishable from one that failed.
        if join(function()
            container:Remove(item)
            pad:AddWorldInventoryItem(item, 0.5, 0.5, 0.0)
            return true
        end) then spilled = spilled + 1 end
    end
    return spilled
end

--- Removes what the old, larger cabin left standing outside the new hull.
---
--- Shrinking the cabin is a migration, not a rebuild. clearSurroundings does
--- sweep the margin, but U.clearSquare deliberately *keeps* anything the mod
--- tagged -- so every locker, fridge and bunk of the 6x9 cabin would be left
--- standing, openable, in the black void, for ever. Nothing that walks the
--- new shape ever visits those squares, so they have to be named.
---
--- Constraint 1 applies in full: a square in a chunk that has not streamed in
--- answers nil, and nil means "ask again later", not "nothing there". The
--- pass only marks itself done when it reached every square it went looking
--- for, and runs again on the next build otherwise.
--- Removes a world item the cabin no longer places.
---
--- U.clearSquare deliberately leaves anything lying on the ground alone --
--- it is where a player's dropped things live -- so a prop the mod itself put
--- down has to be named to get rid of it.
local function removeWorldItem(sq, fullType)
    if not sq then return 0 end
    local doomed = {}
    U.try("scanWorldItems", function()
        local items = sq:getWorldObjects()
        if not items then return end
        for i = 0, items:size() - 1 do
            local worldItem = items:get(i)
            local item = worldItem and worldItem:getItem()
            if item and item:getFullType() == fullType then
                table.insert(doomed, worldItem)
            end
        end
    end)
    local gone = 0
    for _, o in ipairs(doomed) do
        if removeSynced(sq, o) then gone = gone + 1 end
    end
    return gone
end

--- Brings a cabin built before the refit up to the shape the ship has now.
---
--- Two jobs, both of which only ever matter in an older save and neither of
--- which any other pass would do:
---
--- 1. *Fittings outside the new hull.* clearSurroundings does sweep the
---    margin, but U.clearSquare deliberately *keeps* anything the mod tagged
---    -- so every locker, fridge and bunk of the 6x9 cabin would be left
---    standing, openable, in the black void. Nothing that walks the new shape
---    ever visits those squares, so C.LegacyCabin names them.
--- 2. *The helm console prop.* A 70-weight static model lying on the deck
---    that did nothing: the helm panel opens from the aboard menu anywhere in
---    the cabin, never from that object. It is a world item, which
---    U.clearSquare leaves alone by design, so it has to be named too -- and
---    it is looked for over the whole cabin, because it stood at 3,7 before
---    the refit and at 2,1 for one revision after it.
---
--- Constraint 1 applies in full: a square whose chunk has not streamed in
--- answers nil, and nil means "ask again later", not "nothing there". This
--- only marks itself done when it reached every square it went looking for,
--- and runs again on the next build otherwise.
function B.refitCabin()
    local s = U.state()
    if s.refitRev == C.BuildRev then return 0 end

    local w = math.max(C.CabinW, C.LegacyCabin.w)
    local l = math.max(C.CabinL, C.LegacyCabin.l)
    local removed, spilled, props, unreachable = 0, 0, 0, 0

    for ox = 0, w do
        for oy = 0, l do
            local x, y = at(ox, oy)
            -- The chunk is the gate, not the square. A nil square in a
            -- *loaded* chunk really is nothing there -- which is every square
            -- outside the hull in a world made after the refit, and if that
            -- counted as "ask again later" this would never finish and would
            -- walk fifty-four squares on every build for the rest of the save.
            if not U.chunkLoaded(x, y, C.CabinZ) then
                unreachable = unreachable + 1
            else
                local sq = U.square(x, y, C.CabinZ, false)
                props = props + removeWorldItem(sq, C.LegacyHelmItem)
                if not inShape(ox, oy) and sq then
                    local doomed = {}
                    U.eachObject(sq, function(o)
                        local md = U.try("md", function() return o:getModData() end)
                        if md and md.TREK then table.insert(doomed, o) end
                    end)
                    for _, o in ipairs(doomed) do
                        spilled = spilled + spillToPad(o)
                        if removeSynced(sq, o) then removed = removed + 1 end
                    end
                end
            end
        end
    end

    if unreachable > 0 then
        U.log("refit: %d squares of the old cabin are not loaded yet; "
              .. "%d fittings and %d props removed so far",
              unreachable, removed, props)
        return removed + props
    end

    s.refitRev = C.BuildRev
    if removed > 0 or props > 0 then
        U.log("refit: removed %d fittings the old 6x9 cabin left outside the "
              .. "hull and %d helm props, and spilled %d items onto the pad",
              removed, props, spilled)
    end
    return removed + props
end

local function clearFootprint()
    local cleared = 0
    for ox = 0, C.CabinW do
        for oy = 0, C.CabinL do
            local x, y = at(ox, oy)
            cleared = cleared + clearSquare(U.square(x, y, C.CabinZ, false))
        end
    end
    U.debug("cleared %d objects from the cabin footprint", cleared)
end

--- Strips the ring around the cabin, on its own level and on the ground below
--- it, which is where the wilderness actually grows.
local function clearSurroundings()
    local m = C.ClearMargin
    local cleared = 0
    for _, z in ipairs({ C.CabinZ, 0 }) do
        for ox = -m, C.CabinW + m do
            for oy = -m, C.CabinL + m do
                local inside = ox >= 0 and ox <= C.CabinW
                               and oy >= 0 and oy <= C.CabinL
                if not (inside and z == C.CabinZ) then
                    local x, y = at(ox, oy)
                    cleared = cleared + clearSquare(U.square(x, y, z, false))
                end
            end
        end
    end
    if cleared > 0 then U.debug("cleared %d objects from the margin", cleared) end
    return cleared
end

--- Re-run while anyone is aboard, so chunks that streamed in after the build
--- are stripped too.
function B.clearLoadedSurroundings()
    return clearSurroundings()
end

---------------------------------------------------------------------------
-- Hull
---------------------------------------------------------------------------
local function buildFloor()
    local made = 0
    for ox = -1, C.CabinW + 1 do
        for oy = -1, C.CabinL + 1 do
            -- Floor the cabin, and also the squares its walls stand on: a
            -- wall on a midair square behaves badly.
            if inShape(ox, oy)
               or inShape(ox - 1, oy) or inShape(ox + 1, oy)
               or inShape(ox, oy - 1) or inShape(ox, oy + 1) then
                local x, y = at(ox, oy)
                local sprite = L.floor or C.Sprites.deckFloor
                if C.isLanding(ox, oy) then sprite = C.Sprites.padFloor end
                -- addFloor sends itself to clients.
                if U.addFloor(x, y, C.CabinZ, sprite) then made = made + 1 end
            end
        end
    end
    return made
end

--- Walls are derived from the floor plan rather than hard-coded. A wall lives
--- on the north or west edge of its own square, so a hull edge facing east or
--- south is drawn on the square just outside the cabin.
local function buildWalls()
    local wallW = L.wallW or C.Sprites.wallW
    local wallN = L.wallN or C.Sprites.wallN
    local z = C.CabinZ

    local function wall(ox, oy, sprite)
        local x, y = at(ox, oy)
        place(U.square(x, y, z, true), sprite, "wall")
    end

    for ox = 0, C.CabinW do
        for oy = 0, C.CabinL do
            if inShape(ox, oy) then
                if not inShape(ox - 1, oy) then wall(ox, oy, wallW) end
                if not inShape(ox, oy - 1) then wall(ox, oy, wallN) end
                if not inShape(ox + 1, oy) then wall(ox + 1, oy, wallW) end
                if not inShape(ox, oy + 1) then wall(ox, oy + 1, wallN) end
            end
        end
    end
end

--- Marks the cabin as powered, so the fridges, ovens and microwave work.
--- A square flag, not a synced object: clients set it too (TREK_Core).
---------------------------------------------------------------------------
-- Water
---------------------------------------------------------------------------
--- Gives a fixture its own water store, full. A sink placed at runtime has
--- none -- map-loaded sinks get theirs from the map -- and the sprite
--- properties that would describe one are not turned into one by anything in
--- build 42 (createFluidContainersFromSpriteProperties is empty). This is
--- vanilla's own addWaterContainer command.
local function addWaterStore(obj)
    local f = ComponentType.FluidContainer:CreateComponent()
    f:setCapacity(C.WaterCapacity)
    f:addFluid(FluidType.Water, C.WaterCapacity)
    GameEntityFactory.AddComponent(obj, true, f)
end

local function waterCapacity(obj)
    return U.try("fluidCapacity", function() return obj:getFluidCapacity() end) or 0
end

--- Tops one fixture up. addFluid on the object syncs itself on a server.
local function topUp(obj)
    local cap = waterCapacity(obj)
    if cap <= 0 then return false end
    U.try("topUpWater", function()
        local have = obj:getFluidAmount() or 0
        if have < cap then obj:addFluid(FluidType.Water, cap - have) end
    end)
    return true
end

---------------------------------------------------------------------------
-- Furnishing
---------------------------------------------------------------------------
-- Squares claimed by lamps during this build, so a lamp never lands on top
-- of a fitting.
local claimed = {}

local function claim(ox, oy, tag)
    local key = ox .. "," .. oy
    if claimed[key] then
        U.log("layout: %s wants %d,%d but %s is already there",
              tostring(tag), ox, oy, tostring(claimed[key]))
        return false
    end
    claimed[key] = tag or true
    return true
end

--- True when a layout entry is meant to be openable. An entry carrying loot
--- and no flag is a container whose flag was forgotten; tests/test_layout.py
--- fails that so it gets fixed in the layout rather than relied on here.
local function wantsContainer(entry)
    return entry.container == true or entry.loot ~= nil or entry.special ~= nil
end

--- What each `special` container is guaranteed to hold, whatever its loot
--- list then does. The phaser locker gets four phasers; the forward sick-bay
--- locker gets one of each of the ship's own medical instruments.
---
--- U.stockEach is the one that reads the container back and says what did not
--- land, which is the whole reason these are listed rather than left to the
--- fill: a guarantee that is not checked is not a guarantee.
local SPECIALS = {
    phasers = { items = { C.PhaserItem }, copies = function() return C.PhaserCount end },
    medkit  = { items = { C.HyposprayItem, C.DermalRegenItem,
                          C.MedTricorderItem, C.TricorderItem },
                copies = function() return 1 end },
}

--- Stocks one authored container. Returns true when something went in.
---
--- A special container is stocked in two passes, and the order is the point:
--- the guaranteed items go in and are counted first, then the loot list fills
--- what is left. Filling first could leave the locker holding none of them.
local function stockAuthored(obj, entry)
    local added = 0

    local special = entry.special and SPECIALS[entry.special]
    if entry.special and not special then
        U.warnOnce("special:" .. tostring(entry.special),
                   "no special stock rule named " .. tostring(entry.special))
    elseif special then
        local copies = special.copies()
        local present = U.stockEach(obj, special.items, copies)
        for _, id in ipairs(special.items) do
            local count = present[id] or 0
            added = added + count
            -- Short, not merely absent: a container at capacity drops what it
            -- is handed without raising anything, so two phasers in a locker
            -- meant to hold four looks exactly like four until it is counted.
            if count < copies then
                U.log("WARN %s locker holds %d of %d %s",
                      tostring(entry.special), count, copies, id)
            end
        end
    end

    local list = entry.loot and C.Loot[entry.loot]
    if entry.loot and not list then
        U.warnOnce("loot:" .. tostring(entry.loot),
                   "no C.Loot list named " .. tostring(entry.loot))
    elseif list then
        added = added + U.fill(obj, list, entry.fill, entry.cap)
    end

    return added > 0
end

--- True when the layout asked for this container to hold something.
---
--- Five of the eight containers in the cabin are deliberately empty -- they
--- are the player's shelves, not the ship's stores -- so "no stock" is only
--- worth a warning when stock was actually asked for. Without this the build
--- log carries five WARNs every time, and tests/test_multiplayer.py fails on
--- any WARN the mod logs.
local function wantsStock(entry)
    return entry.loot ~= nil or entry.special ~= nil
end

--- Creates a container object's inventory and stocks it. Runs on a new object
--- before it is sent, so nothing needs sending item by item.
local function prepareContainer(obj, entry)
    obj:createContainersFromSpriteProperties()
    local container = U.containerOf(obj)
    if not container then return end
    -- Explored, or vanilla rolls its own loot into it the first time a
    -- client opens it, on top of ours.
    container:setExplored(true)
    if not wantsStock(entry) then
        -- Stamped even though nothing went in, so the repair path below never
        -- mistakes an empty-by-design container for one the old broken builds
        -- left unstocked and fills it years later.
        obj:getModData().TREKStockRev = C.BuildRev
        return
    end
    if stockAuthored(obj, entry) then
        obj:getModData().TREKStockRev = C.BuildRev
    else
        U.log("WARN container %s at %d,%d received no stock",
              tostring(entry.tag), entry.x, entry.y)
    end
end

--- A container that is already in the world but was never stocked -- the
--- builds that could not create items left exactly that behind. It is
--- stocked in place, and each item is sent to the clients that can see it.
local function repairContainer(obj, entry)
    local data = obj:getModData()
    local container = U.containerOf(obj)
    if not container then return end
    container:setExplored(true)

    if not wantsStock(entry) then return end
    local initialize = C.DevRestock
        or (data.TREKStockRev == nil and U.itemCount(obj) == 0)
    if not initialize then return end

    U.onItemAdded = isServer() and function(c, item)
        sendAddItemToContainer(c, item)
    end or nil
    local ok = stockAuthored(obj, entry)
    U.onItemAdded = nil

    if ok then
        data.TREKStockRev = C.BuildRev
        U.try("transmitModData", function() obj:transmitModData() end)
    end
end

---------------------------------------------------------------------------
-- Devices
---------------------------------------------------------------------------
--- Builds a working television rather than a picture of one.
---
--- `place()` makes every fitting with IsoObject.new, and an IsoObject wearing
--- a television's sprite is scenery: no channel, no volume, no tape slot,
--- nothing to right-click. That is what the old viewscreen was for three
--- versions, and it is the same "present, drawn, and inert" shape as the
--- unopenable locker and the tap with no water store.
---
--- Vanilla's own route is ISMoveableSpriteProps.lua:2136 -- build the
--- IsoTelevision, then hand it a DeviceData cloned off the item that declares
--- the thing's channels and `AcceptMediaType`. Two ways of getting that data
--- and neither has a vanilla *Lua* call site, so both are tried and the
--- result is read back: a television with nil device data looks identical to
--- a working one until somebody walks up to it.
local function attachDevice(obj, itemId)
    local data = U.try("cloneDeviceDataFromItem", function()
        return obj:cloneDeviceDataFromItem(itemId)
    end)
    if not data then
        -- The long way round, which is what the moveable-furniture code does.
        -- instanceItem is the GlobalObject static with 187 vanilla call sites;
        -- InventoryItemFactory is the one that is null from Lua.
        data = U.try("device:instanceItem", function()
            local proto = instanceItem(itemId)
            return proto and proto:getDeviceData() or nil
        end)
    end
    if data then
        U.try("setDeviceData", function() obj:setDeviceData(data) end)
    end

    local got = U.try("getDeviceData", function() return obj:getDeviceData() end)
    if got then
        U.log("device: %s is live", itemId)
    else
        U.log("WARN device: %s has no device data; it will be scenery", itemId)
    end
    return got ~= nil
end

--- Places a device fitting -- currently only the television. Mirrors place(),
--- but with IsoTelevision's own (cell, square, sprite) constructor.
---
--- An object already on the square that is *not* a television came from a
--- build before this existed; it is removed and made again, the same way a
--- tap with no water store is. It held nothing, so there is nothing to lose.
local function placeDevice(sq, entry)
    if not sq then return nil, false end

    local existing = U.findSprite(sq, entry.sprite)
    if existing then
        -- instanceof rather than a getDeviceData() probe: a plain IsoObject
        -- has no such method, so asking would throw out of Java once a build
        -- for a question instanceof answers without one.
        if instanceof(existing, "IsoTelevision") then return existing, false end
        removeSynced(sq, existing)
    end

    local obj = U.try("IsoTelevision.new", function()
        return IsoTelevision.new(getCell(), sq, getSprite(entry.sprite))
    end)
    if not obj then
        -- Better a picture of a television than no television: fall back to
        -- the ordinary path so the bow still looks right.
        U.warnOnce("device:" .. tostring(entry.tag),
                   "could not build an IsoTelevision; placing it as scenery")
        return place(sq, entry.sprite, entry.tag)
    end

    U.try("tagObject", function() obj:getModData().TREK = entry.tag end)
    attachDevice(obj, entry.device)
    -- The ship's own power, before the object is sent, so it arrives at every
    -- client already able to be switched on. TREK_Power keeps it topped up.
    TREK.Power.energise(obj)
    if not addSynced(sq, obj) then return nil, false end
    return obj, true
end

--- Places the furniture authored in BuildingEd. An appliance and its counter
--- may share a square, so layering is intentional and nothing is claimed.
local function furnishAuthoredInterior()
    for _, entry in ipairs(L.tiles) do
        if inShape(entry.x, entry.y) and not C.isLanding(entry.x, entry.y) then
            local x, y = at(entry.x, entry.y)
            local sq = U.square(x, y, C.CabinZ, true)
            local isWater = C.WaterTags[entry.tag]
            if entry.device then
                placeDevice(sq, entry)
            elseif wantsContainer(entry) then
                local obj, made = place(sq, entry.sprite, entry.tag, function(o)
                    prepareContainer(o, entry)
                end)
                if obj and not made and not U.containerOf(obj) then
                    -- Placed as scenery by an old build: replace it with a
                    -- real container, sent whole. It had no inventory, so
                    -- there is nothing in it to lose.
                    removeSynced(sq, obj)
                    place(sq, entry.sprite, entry.tag, function(o)
                        prepareContainer(o, entry)
                    end)
                elseif obj and not made then
                    U.try("repairContainer:" .. tostring(entry.tag),
                          repairContainer, obj, entry)
                end
            elseif isWater then
                local obj, made = place(sq, entry.sprite, entry.tag, addWaterStore)
                -- A fixture from a build before water stores: replace it with
                -- one that has a store. Removing and re-adding is the one way
                -- every client is guaranteed to get the new component, and a
                -- sink holds no items to lose.
                if obj and not made and waterCapacity(obj) <= 0 then
                    removeSynced(sq, obj)
                    place(sq, entry.sprite, entry.tag, addWaterStore)
                end
            else
                place(sq, entry.sprite, entry.tag)
            end
        else
            U.warnOnce("authored:" .. tostring(entry.x) .. ":" .. tostring(entry.y),
                string.format("layout entry %s at %d,%d is outside the cabin or on the pad",
                    tostring(entry.tag), entry.x, entry.y))
        end
    end
end

--- Stands the replicator's alcove over its berth.
---
--- A world item, the way the hull is, rather than a tile sprite: the mesh is
--- authored from 0.80 upwards so it hangs above the counter at 0,5 instead of
--- being drawn through it.
---
--- Placed once, ever. World items are saved and `U.clearSquare` leaves them
--- alone by design -- that is where a player's dropped things live -- so a
--- pass that did not look first would stand a second alcove on the square at
--- every rebuild, which is exactly the shape of the "Two shuttles" signature
--- in DEV_GUIDE.md.
---
--- And the result is read back. An item id that does not resolve puts nothing
--- there and says nothing, and the feature would still work off the counter,
--- so nobody would ever find out from the outside.
local function furnishReplicator()
    local ox, oy = TREK.Replicator.spot()
    if not ox then return false end
    local x, y = at(ox, oy)
    local sq = U.square(x, y, C.CabinZ, true)
    if not sq then return false end

    local standing = 0
    U.try("replicator.scan", function()
        local items = sq:getWorldObjects()
        if not items then return end
        for i = 0, items:size() - 1 do
            local worldItem = items:get(i)
            local item = worldItem and worldItem:getItem()
            if item and item:getFullType() == C.ReplicatorItem then
                standing = standing + 1
            end
        end
    end)
    if standing > 0 then return false end

    local placed = U.try("replicator.place", function()
        return sq:AddWorldInventoryItem(C.ReplicatorItem, 0.5, 0.5, 0.0)
    end)
    if placed then
        U.log("replicator: the alcove stands at %d,%d", ox, oy)
        return true
    end
    U.log("WARN replicator: %s would not place at %d,%d; the machine still "
          .. "works from the counter", tostring(C.ReplicatorItem), ox, oy)
    return false
end

--- The lamp fittings. The light they give is a client-side light source and
--- is hung by TREK_Core on each client; only the fixture is world state.
local function fitLamps()
    for _, p in ipairs(C.LampSpots) do
        if inShape(p[1], p[2]) and not C.isLanding(p[1], p[2])
           and claim(p[1], p[2], "lamp") then
            local x, y = at(p[1], p[2])
            place(U.square(x, y, C.CabinZ, true), C.Sprites.lamp.S, "lamp")
        end
    end
end

---------------------------------------------------------------------------
-- Water upkeep
---------------------------------------------------------------------------
-- Where the layout puts plumbed fixtures, worked out once.
local waterSpots = nil

local function findWaterSpots()
    if waterSpots then return waterSpots end
    waterSpots = {}
    for _, entry in ipairs(L.tiles) do
        if C.WaterTags[entry.tag] then
            table.insert(waterSpots, { entry.x, entry.y })
        end
    end
    return waterSpots
end

--- Calls fn(obj, tag, spot) for every plumbed fixture whose square is loaded.
local function eachWaterFixture(fn)
    for _, spot in ipairs(findWaterSpots()) do
        local x, y = at(spot[1], spot[2])
        local sq = U.square(x, y, C.CabinZ, false)
        U.eachObject(sq, function(o)
            local md = U.try("md", function() return o:getModData() end)
            local tag = md and md.TREK
            if tag and C.WaterTags[tag] then fn(o, tag, spot) end
        end)
    end
end

--- The ship's water never runs dry: the galley sink, the head and the shower
--- are kept full. Returns the number topped up and the number with no store.
function B.refillWater()
    if not U.state().built then return 0, 0 end
    local wet, dry = 0, 0
    eachWaterFixture(function(o)
        if topUp(o) then wet = wet + 1 else dry = dry + 1 end
    end)
    if dry > 0 then
        U.warnOnce("waterDry",
            string.format("%d water fixture(s) have no water store", dry))
    end
    return wet, dry
end

--- Logs each fixture's reading, for TREK_Water().
function B.waterReport()
    local wet, dry = B.refillWater()
    eachWaterFixture(function(o, tag, spot)
        U.log("water: %s at %d,%d capacity %s, holding %s, hasWater %s",
              tag, spot[1], spot[2], tostring(waterCapacity(o)),
              tostring(U.try("amt", function() return o:getFluidAmount() end)),
              tostring(U.try("has", function() return o:hasWater() end)))
    end)
    U.log("water: %d fixtures topped up, %d without a store", wet, dry)
    return wet, dry
end

---------------------------------------------------------------------------
-- Reporting
---------------------------------------------------------------------------
--- One line per authored container in the log. An empty locker is silent in
--- game; this turns a trip into the game into a grep.
function B.stockReport()
    local lines, empty = 0, 0
    for _, entry in ipairs(L.tiles) do
        if wantsContainer(entry) then
            local x, y = at(entry.x, entry.y)
            local sq = U.square(x, y, C.CabinZ, false)
            local obj = sq and U.findSprite(sq, entry.sprite)
            local held = obj and U.itemCount(obj) or 0
            local level = obj and U.fillLevel(obj)
            if not obj then
                U.log("stock %-11s %d,%d MISSING -- nothing placed",
                      tostring(entry.tag), entry.x, entry.y)
                empty = empty + 1
            elseif not U.containerOf(obj) then
                U.log("stock %-11s %d,%d NOT A CONTAINER -- %s has no inventory",
                      tostring(entry.tag), entry.x, entry.y, entry.sprite)
                empty = empty + 1
            else
                if held == 0 then empty = empty + 1 end
                U.log("stock %-11s %d,%d %2d items, %s full",
                      tostring(entry.tag), entry.x, entry.y, held,
                      level and string.format("%d%%", math.floor(level * 100 + 0.5))
                            or "capacity unknown")
            end
            lines = lines + 1
        end
    end
    U.log("stock: %d containers, %d empty", lines, empty)
    return lines - empty, lines
end

--- The galley's own dishes, for TREK_Galley().
B.GalleyItems = {
    "TrekShuttle.TrekRationPack",
    "TrekShuttle.TrekGagh",
    "TrekShuttle.TrekLeolaStew",
    "TrekShuttle.TrekPlomeekSoup",
    "TrekShuttle.TrekJumjaStick",
    -- The drinks. Each arrives full: the vessel's FluidContainer carries
    -- InitialPercentMin/Max, so instanceItem hands back a full mug or bottle
    -- rather than empty glass. If one of these comes through empty, the fill
    -- is not being applied and that is worth knowing before anything else.
    "TrekShuttle.TrekRaktajinoMug",
    "TrekShuttle.TrekEarlGreyCup",
    "TrekShuttle.TrekRomulanAle",
    "TrekShuttle.TrekBloodwine",
    -- Not galley, and here anyway: an existing save never sees new loot, and
    -- this is the only route to a new item that does not cost a fresh world.
    -- The bat'leth is the first custom in-hand model this mod has, so it is
    -- the one thing that most needs picking up and looking at.
    "TrekShuttle.TrekBatleth",
}

--- Puts one of each galley dish in a player's inventory. An existing save
--- never sees new loot, so this is how new food is tried without a new world.
function B.giveGalley(player)
    local inv = player and player:getInventory()
    if not inv then return 0 end
    local given = 0
    for _, id in ipairs(B.GalleyItems) do
        local item = U.try("galley:" .. id, function() return instanceItem(id) end)
        if item then
            inv:AddItem(item)
            if isServer() then sendAddItemToContainer(inv, item) end
            given = given + 1
            U.log("galley: %s", id)
        else
            U.log("WARN galley: could not create %s", id)
        end
    end
    return given
end

---------------------------------------------------------------------------
-- Build entry points
---------------------------------------------------------------------------
--- True when the cabin footprint is loaded here, so construction will not
--- touch an orphan square.
function B.cabinLoaded()
    local probes = {
        { 0, 0 }, { C.CabinW, 0 }, { 0, C.CabinL }, { C.CabinW, C.CabinL },
        { math.floor(C.CabinW / 2), math.floor(C.CabinL / 2) },
        { C.Landing.x, C.Landing.y },
    }
    for _, p in ipairs(probes) do
        local x, y = at(p[1], p[2])
        if not U.chunkLoaded(x, y, C.CabinZ) then return false end
    end
    return true
end

--- True when the cabin exists and was generated by the current revision.
function B.cabinCurrent()
    local s = U.state()
    return s.built == true and s.rev == C.BuildRev
end

--- Raises or repairs the cabin. Idempotent: every step checks for what it
--- would add. Returns false, and builds nothing, while it is not loaded.
function B.buildCabin()
    if not B.cabinLoaded() then return false end

    local phases = {
        -- Before anything else: the 6x9 cabin's fittings are standing on
        -- squares the new hull does not cover, and buildFloor is about to
        -- take the deck out from under them.
        { "refitCabin", B.refitCabin },
        { "clearFootprint", clearFootprint },
        { "buildFloor",     buildFloor },
        { "buildWalls",     buildWalls },
        { "furnish", function()
              claimed = {}
              U.resetStockCursors()
              U.resetItemStrategy()
              furnishAuthoredInterior()
          end },
        { "fitLamps",       fitLamps },
        { "replicator",     furnishReplicator },
        { "stockReport", function() B.stockReport() end },
        { "clearMargin",    clearSurroundings },
    }
    for _, phase in ipairs(phases) do
        U.try(phase[1], phase[2])
    end

    local s = U.state()
    s.built = true
    s.rev = C.BuildRev
    U.log("cabin ready at z=%d (build %d)", C.CabinZ, C.BuildRev)
    return true
end

--- Builds the cabin once, and brings one from an older revision up to date.
--- Returns true when the cabin is current afterwards.
function B.ensureCabin()
    if B.cabinCurrent() then return true end
    local s = U.state()
    if s.built and not B.upgradeNoted then
        B.upgradeNoted = true
        U.log("the cabin was built by an older revision; bringing it up to date")
    end
    return B.buildCabin()
end

--- Tears the cabin back to bare deck and regenerates it, restocked. The one
--- operation that destroys what is there; for designing the cabin, never for
--- a world being played. Only works while the cabin is loaded.
function B.forceRebuild()
    if not B.cabinLoaded() then
        U.log("forceRebuild: the cabin is not loaded; someone must be aboard")
        return false
    end
    -- Swept over the *old* extent as well as the new one, because a rebuild
    -- in a save made before the refit has the 6x9 cabin's fittings standing
    -- outside the hull and CabinW + 2 no longer reaches them.
    local wiped = 0
    local sweepW = math.max(C.CabinW, C.LegacyCabin.w) + 2
    local sweepL = math.max(C.CabinL, C.LegacyCabin.l) + 2
    for ox = -2, sweepW do
        for oy = -2, sweepL do
            local x, y = at(ox, oy)
            local sq = U.square(x, y, C.CabinZ, false)
            if sq then
                local doomed = {}
                U.eachObject(sq, function(o)
                    -- The floor stays: someone is standing on it.
                    if o ~= sq:getFloor() then table.insert(doomed, o) end
                end)
                for _, o in ipairs(doomed) do
                    if removeSynced(sq, o) then wiped = wiped + 1 end
                end
            end
        end
    end

    local s = U.state()
    s.built, s.rev = false, 0

    local wasDev = C.DevRestock
    C.DevRestock = true
    local ok = B.buildCabin()
    C.DevRestock = wasDev
    U.log("forceRebuild: wiped %d objects and regenerated the cabin", wiped)
    return ok
end

return B
