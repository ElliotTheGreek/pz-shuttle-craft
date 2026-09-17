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

        bow (oy 0)   consoles and viewscreen over the galley counters
        port (ox 0)  fridges, ovens and the microwave, berth aft
        stbd (ox 5)  eight lockers: sick bay, engineering, stores, armoury
        amidships    the transporter pad at 2,6

    Nothing may be built into a chunk that is not loaded, and chunks load only
    around a player, so TREK_Server only asks for a build once somebody who
    has reported themselves aboard is standing there.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
local L = require "TREK/TREK_InteriorLayout"

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
function B.powerCabin()
    local power = U.batch("power.setHaveElectricity")
    for ox = 0, C.CabinW do
        for oy = 0, C.CabinL do
            if inShape(ox, oy) then
                local x, y = at(ox, oy)
                local sq = U.square(x, y, C.CabinZ, false)
                if sq then power(function() sq:setHaveElectricity(true) end) end
            end
        end
    end
end

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

--- Stocks one authored container. Returns true when something went in.
---
--- The phaser locker is stocked in two passes, and the order is the point:
--- the phasers go in and are counted first, then the armoury list fills what
--- is left. Filling first could leave the locker holding no phasers at all.
local function stockAuthored(obj, entry)
    local added = 0

    if entry.special == "phasers" then
        local present = U.stockEach(obj, { C.PhaserItem }, C.PhaserCount)
        local count = present[C.PhaserItem] or 0
        added = added + count
        if count < C.PhaserCount then
            U.log("WARN phaser locker holds %d of %d", count, C.PhaserCount)
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

--- Creates a container object's inventory and stocks it. Runs on a new object
--- before it is sent, so nothing needs sending item by item.
local function prepareContainer(obj, entry)
    obj:createContainersFromSpriteProperties()
    local container = U.containerOf(obj)
    if not container then return end
    -- Explored, or vanilla rolls its own loot into it the first time a
    -- client opens it, on top of ours.
    container:setExplored(true)
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

--- Places the furniture authored in BuildingEd. An appliance and its counter
--- may share a square, so layering is intentional and nothing is claimed.
local function furnishAuthoredInterior()
    for _, entry in ipairs(L.tiles) do
        if inShape(entry.x, entry.y) and not C.isLanding(entry.x, entry.y) then
            local x, y = at(entry.x, entry.y)
            local sq = U.square(x, y, C.CabinZ, true)
            local isWater = C.WaterTags[entry.tag]
            if wantsContainer(entry) then
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

--- The helm is a world item, not a tile.
local function furnishHelmItem()
    local hx, hy = at(3, 7)
    local sq = U.square(hx, hy, C.CabinZ, true)
    if not sq then return end

    local already = false
    U.try("scanHelm", function()
        local items = sq:getWorldObjects()
        if not items then return end
        for i = 0, items:size() - 1 do
            local worldItem = items:get(i)
            local item = worldItem and worldItem:getItem()
            if item and item:getFullType() == C.HelmItem then already = true end
        end
    end)
    if not already then
        -- The four-argument form sends the new world item to clients.
        U.try("addHelm", function()
            sq:AddWorldInventoryItem(C.HelmItem, 0.5, 0.5, 0.0)
        end)
    end
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
        { "clearFootprint", clearFootprint },
        { "buildFloor",     buildFloor },
        { "buildWalls",     buildWalls },
        { "powerCabin",     B.powerCabin },
        { "furnish", function()
              claimed = {}
              U.resetStockCursors()
              U.resetItemStrategy()
              furnishAuthoredInterior()
              furnishHelmItem()
          end },
        { "fitLamps",       fitLamps },
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
    local wiped = 0
    for ox = -2, C.CabinW + 2 do
        for oy = -2, C.CabinL + 2 do
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
