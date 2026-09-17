--[[ Shuttlecraft -- cabin construction.

    The cabin is generated at runtime in an otherwise empty cell rather than
    shipped as a map, so the mod needs no TileZed-built lots. It is raised
    lazily: nothing exists until somebody is aboard for the first time.

    One compartment, one storey. The hull, the deck, the lighting and the helm
    item are generated here; everything else -- every fitting, every locker --
    is authored in BuildingEd and read out of TREK_InteriorLayout.lua, so the
    arrangement of the cabin is changed in the map editor and not in this file:

        bow (oy 0)   consoles and viewscreen over the galley counters
        port (ox 0)  fridges, ovens and the microwave, berth aft
        stbd (ox 5)  eight lockers: sick bay, engineering, stores, armoury
        amidships    the transporter pad at 2,6

    Nothing may be built into a chunk that has not streamed in, and chunks
    only stream around a player, so every entry point here refuses to do
    anything until TREK_Core has moved somebody aboard and held them there.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"
local L = require "TREK/TREK_InteriorLayout"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local B = {}
TREK.Build = B

-- Logged once rather than on every arrival tick while the chunks stream in.
B.upgradeNoted = false

local at = U.at

local function inShape(ox, oy)
    return C.inShape(ox, oy)
end

---------------------------------------------------------------------------
-- Clearing the site
---------------------------------------------------------------------------
--- The interior cell is unmapped, so the engine grows procedural wilderness
--- there. Left alone the ship reads as a hut standing in a wood, so the hull
--- footprint is stripped before building and a wide margin around it is
--- stripped to nothing at all, which renders as black void.
---
--- Safe to repeat: U.clearSquare keeps anything the mod placed and anything
--- lying on the ground, so both passes can run again as chunks stream in late.
local function clearFootprint()
    local cleared = 0
    for ox = 0, C.CabinW do
        for oy = 0, C.CabinL do
            local x, y = at(ox, oy)
            local sq = U.square(x, y, C.CabinZ, false)
            if sq then cleared = cleared + U.clearSquare(sq, true) end
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
                    local sq = U.square(x, y, z, false)
                    if sq then cleared = cleared + U.clearSquare(sq, true) end
                end
            end
        end
    end
    U.debug("cleared %d objects from the margin", cleared)
    return cleared
end

--- Re-run while aboard so chunks that streamed after construction are
--- stripped as soon as they become available. Safe and idempotent.
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
                if U.addFloor(x, y, C.CabinZ, sprite) then made = made + 1 end
            end
        end
    end
    return made
end

--- Walls are derived from the floor plan rather than hard-coded, so changing
--- the bow and stern cuts reshapes the hull and its walls together and
--- nothing else needs touching.
---
--- A wall lives on the north or west edge of its own square, so a hull edge
--- facing east or south is drawn on the square just outside the cabin.
local function buildWalls()
    local S = {
        wallW = L.wallW or C.Sprites.wallW,
        wallN = L.wallN or C.Sprites.wallN,
    }
    local z = C.CabinZ
    local placed = 0

    local function wall(ox, oy, sprite)
        local x, y = at(ox, oy)
        if U.addObject(U.square(x, y, z, true), sprite, "wall") then
            placed = placed + 1
        end
    end

    for ox = 0, C.CabinW do
        for oy = 0, C.CabinL do
            if inShape(ox, oy) then
                if not inShape(ox - 1, oy) then wall(ox, oy, S.wallW) end
                if not inShape(ox, oy - 1) then wall(ox, oy, S.wallN) end
                if not inShape(ox + 1, oy) then wall(ox + 1, oy, S.wallW) end
                if not inShape(ox, oy + 1) then wall(ox, oy + 1, S.wallN) end
            end
        end
    end
    U.debug("%d wall segments", placed)
end

--- Marks the whole cabin as powered indoor space.
local function powerCabin()
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
-- Furnishing helpers
---------------------------------------------------------------------------
-- Squares claimed by furniture during this build.
--
-- Two placements landing on one square do not fail: U.addObject only looks
-- for its own sprite, so a deckhead lamp dropped where a crate already stands
-- simply stacks, both are drawn, and which one a player can actually reach is
-- a matter of draw order. Claiming squares turns that into one line in the log
-- at build time instead of a puzzle in game.
local claimed = {}

local function claimKey(ox, oy) return ox .. "," .. oy end

local function claim(ox, oy, tag)
    local key = claimKey(ox, oy)
    if claimed[key] then
        U.log("layout: %s wants %d,%d but %s is already there",
              tostring(tag), ox, oy, tostring(claimed[key]))
        return false
    end
    claimed[key] = tag or true
    return true
end

--- One object at one offset, on a square nothing else has claimed.
---
--- Returns false when the offset is outside the hull, on the transporter pad,
--- or already taken, so a layout that has drifted reports itself rather than
--- silently leaving gaps.
---
--- The furniture comes from BuildingEd now and is placed by
--- furnishAuthoredInterior, which layers deliberately and so bypasses this.
--- What is left for fit() is the deckhead lighting, which must *not* land on
--- top of anything.
local function fit(ox, oy, sprite, tag)
    if not sprite then
        U.warnOnce("fit:" .. tostring(tag), "no sprite for " .. tostring(tag))
        return false
    end
    if not inShape(ox, oy) or C.isLanding(ox, oy) then return false end
    if not claim(ox, oy, tag) then return false end

    local x, y = at(ox, oy)
    local sq = U.square(x, y, C.CabinZ, true)
    if not sq then return false end
    return U.addObject(sq, sprite, tag) ~= nil
end

---------------------------------------------------------------------------
-- The layout
---------------------------------------------------------------------------
-- Offsets run 0..CabinW across and 0..CabinL fore to aft, with oy 0 at the
-- bow. Everything except the lamps and the helm item is authored in
-- BuildingEd and lives in TREK_InteriorLayout.lua; tests/test_layout.py
-- checks every offset in both against the floor plan.

--- Deckhead lighting. Kept as a table on B so the layout test can check these
--- offsets the same way it checks the furniture.
B.lampSpots = {
    { 3, 1 }, { 2, 3 }, { 3, 6 },
}

--- True when a layout entry is meant to be openable.
---
--- The flag is what the layout declares, but an entry carrying loot and no
--- flag is a container whose flag was forgotten, and treating it as scenery is
--- the worst of both worlds: the stores never appear and nothing says so. This
--- reads either as intent. tests/test_layout.py fails the missing flag so it
--- gets fixed in the layout rather than relied on here.
local function wantsContainer(entry)
    return entry.container == true or entry.loot ~= nil or entry.special ~= nil
end

--- Stocks one authored container. Returns true when something went in.
---
--- The phaser locker is stocked in two passes, and the order is the point:
--- U.stockEach puts the phasers in and reads the container back to prove all
--- four arrived, then the armoury list fills what is left. Filling first would
--- let a long weapons list reach the target on its own and leave the locker
--- the mod is built around holding no phasers at all.
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

--- Places furniture authored in BuildingEd. Layering is intentional: an
--- appliance and its counter may occupy the same square, so this bypasses
--- claim() while the object helpers keep repeated builds idempotent.
local function furnishAuthoredInterior()
    for _, entry in ipairs(L.tiles) do
        if inShape(entry.x, entry.y) and not C.isLanding(entry.x, entry.y) then
            local x, y = at(entry.x, entry.y)
            local sq = U.square(x, y, C.CabinZ, true)
            if wantsContainer(entry) then
                local obj, made = U.addContainer(sq, entry.sprite, entry.tag)
                if obj then
                    U.try("stockAuthored:" .. tostring(entry.tag), function()
                        local data = obj:getModData()
                        -- Stock a container once, ever. A container that has
                        -- never been successfully stocked (no TREKStockRev) and
                        -- is still empty is the repair case -- the builds that
                        -- could not create items left exactly that behind.
                        --
                        -- It used to restock whenever the revision differed,
                        -- which would have been harmless exactly once: the
                        -- next C.BuildRev bump would have poured a second
                        -- helping into every stocked locker in every save.
                        local initialize = made or C.DevRestock
                            or (data.TREKStockRev == nil and U.itemCount(obj) == 0)
                        if not initialize then return end

                        if stockAuthored(obj, entry) then
                            data.TREKStockRev = C.BuildRev
                            data.TREKAuthoredStocked = nil
                            obj:transmitModData()
                        else
                            U.log("WARN container %s at %d,%d received no stock",
                                  tostring(entry.tag), entry.x, entry.y)
                        end
                    end)
                end
            else
                U.addObject(sq, entry.sprite, entry.tag)
            end
        else
            U.warnOnce("authored:" .. tostring(entry.x) .. ":" .. tostring(entry.y),
                string.format("layout entry %s at %d,%d is outside the cabin or on the pad",
                    tostring(entry.tag), entry.x, entry.y))
        end
    end
end

--- BuildingEd owns the scenery, but the helm remains a special world item.
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
        U.try("addHelm", function()
            sq:AddWorldInventoryItem(C.HelmItem, 0.5, 0.5, 0.0)
        end)
    end
end

---------------------------------------------------------------------------
-- Lighting
---------------------------------------------------------------------------
--- Runs after the furnishing, so the lamps claim whatever squares are left
--- rather than being stacked on top of a crate.
local function lightCabin()
    local S = C.Sprites
    local z = C.CabinZ
    local cell = U.cell()

    local lamp = U.batch("light.lamppost")
    for _, p in ipairs(B.lampSpots) do
        if fit(p[1], p[2], S.lamp.S, "lamp") then
            local x, y = at(p[1], p[2])
            if cell then
                lamp(function() cell:addLamppost(x, y, z, 0.92, 0.96, 1.0, 8) end)
            end
        end
    end

    -- The pad gets a light with no fixture on it: nothing may stand on the
    -- square a player materialises onto.
    if cell then
        local px, py = at(C.Landing.x, C.Landing.y)
        lamp(function() cell:addLamppost(px, py, z, 0.70, 0.88, 1.0, 6) end)
    end
end

---------------------------------------------------------------------------
-- Reporting
---------------------------------------------------------------------------
--- Writes one line per authored container to console.txt.
---
--- An empty locker is the failure this mod keeps having, and it is silent
--- every time: a container placed without an ItemContainer looks exactly like
--- a stocked one until somebody walks up to it in game. Reading every
--- container back after the build turns a trip into the game into a grep.
---
--- Exposed on B because `TREK_Stock()` calls it from the debug console.
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

--- Exposed for the debug console: TREK_Stock()
function TREK_Stock()
    return B.stockReport()
end

--- The galley's own dishes. Kept as a list so the debug helper below and any
--- future replicator menu agree on what the ship can serve.
B.GalleyItems = {
    "TrekShuttle.TrekRationPack",
    "TrekShuttle.TrekGagh",
    "TrekShuttle.TrekLeolaStew",
    "TrekShuttle.TrekPlomeekSoup",
    "TrekShuttle.TrekJumjaStick",
}

--- Exposed for the debug console: TREK_Galley()
---
--- Puts one of each galley dish in the player's inventory. An existing save
--- never sees new loot -- its lockers were stocked once and are left alone --
--- so this is how new food is tried without starting a new world. Reports
--- each item by name, so an id that will not resolve is a named line.
function TREK_Galley()
    local player = U.player(0)
    if not player then return 0 end
    local inv = player:getInventory()
    local given = 0
    for _, id in ipairs(B.GalleyItems) do
        local item = U.try("galley:" .. id, function() return inv:AddItem(id) end)
        if item then
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
--- True when the cabin footprint is streamed in, so construction will not
--- touch an orphan square. Chunks only stream around a player, so this stays
--- false until somebody is standing aboard.
function B.cabinReady()
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

--- Raises the cabin. Idempotent: every step checks for what it would add
--- before adding it. Returns false, and builds nothing, while the footprint is
--- still streaming in.
function B.buildCabin()
    if not B.cabinReady() then
        U.debug("cabin not streamed in yet")
        return false
    end

    U.debug("raising the cabin at z=%d", C.CabinZ)
    local s = U.state()

    -- Order matters. The footprint is stripped and floored first so a player
    -- standing here has ground under them as early as possible; clearing the
    -- surrounding void is left until last. Every phase is isolated, so one
    -- failing step cannot leave the cabin half-built with the player in
    -- mid-air.
    local phases = {
        { "clearFootprint", clearFootprint },
        { "buildFloor",     buildFloor },
        { "buildWalls",     buildWalls },
        { "powerCabin",     powerCabin },
        { "furnish", function()
              claimed = {}
              U.resetStockCursors()
              U.resetItemStrategy()
              furnishAuthoredInterior()
              furnishHelmItem()
          end },
        { "lightCabin",     lightCabin },
        { "stockReport", function() B.stockReport() end },
        { "clearMargin",    clearSurroundings },
    }
    for _, phase in ipairs(phases) do
        U.try(phase[1], phase[2])
    end

    s.built = true
    s.rev = C.BuildRev
    U.log("cabin ready at z=%d", C.CabinZ)
    return true
end

--- True when the cabin exists and was generated by the current revision.
function B.cabinCurrent()
    local s = U.state()
    return s.built == true and s.rev == C.BuildRev
end

--- Builds the cabin once and remembers it, and rebuilds one generated by an
--- older revision. Safe to call on every arrival tick.
function B.ensureCabin()
    if B.cabinCurrent() then return false end
    local s = U.state()
    if s.built and not B.upgradeNoted then
        B.upgradeNoted = true
        U.log("the cabin was built by an older revision; bringing it up to date")
    end
    return B.buildCabin()
end

---------------------------------------------------------------------------
-- Design-time rebuilding
---------------------------------------------------------------------------
--- Tears the cabin back to bare ground and regenerates it, restocked.
---
--- This is the one operation that deliberately destroys what is there,
--- containers and their contents included. An ordinary rebuild never does: a
--- ship in play is meant to be lived in, and what the player eats stays
--- eaten. Use this while designing the cabin, not on a world being played.
---
--- Only works with the player aboard, because only then are its chunks
--- streamed in.
function B.forceRebuild()
    local player = U.player(0)
    if not player then return false end
    if not U.isInteriorPlayer(player) then
        U.log("forceRebuild: beam aboard first -- the cabin's chunks only " ..
              "stream in around a player")
        return false
    end

    local wiped = 0
    for ox = -2, C.CabinW + 2 do
        for oy = -2, C.CabinL + 2 do
            local x, y = at(ox, oy)
            local sq = U.square(x, y, C.CabinZ, false)
            if sq then
                -- clear everything this time, our own work included
                local doomed = {}
                U.eachObject(sq, function(o) table.insert(doomed, o) end)
                for _, o in ipairs(doomed) do
                    if U.try("wipe", function()
                        sq:RemoveTileObjectErosionNoRecalc(o); return true
                    end) then wiped = wiped + 1 end
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
    U.teleport(player, U.padSpot())
    return ok
end

--- Exposed for the debug console: TREK_Rebuild()
function TREK_Rebuild()
    return B.forceRebuild()
end

return B
