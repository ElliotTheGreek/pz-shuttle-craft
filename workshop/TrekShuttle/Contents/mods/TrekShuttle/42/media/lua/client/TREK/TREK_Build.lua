--[[ Shuttlecraft -- cabin construction.

    The cabin is generated at runtime in an otherwise empty cell rather than
    shipped as a map, so the mod needs no TileZed-built lots. It is raised
    lazily: nothing exists until somebody is aboard for the first time.

    One compartment, one storey, laid out fore to aft:

        bow      helm console, viewscreens, two flight seats
        port     galley and dry stores, then the head and the berth
        stbd     sick bay, then engineering stores
        amidships the transporter pad, with the phaser locker beside it
        stern    the cargo bay

    Nothing may be built into a chunk that has not streamed in, and chunks
    only stream around a player, so every entry point here refuses to do
    anything until TREK_Core has moved somebody aboard and held them there.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

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
                local sprite = C.Sprites.deckFloor
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
    local S = C.Sprites
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

--- One object at one offset, stocked if a loot list is given.
---
--- Returns false when the offset is outside the hull, on the transporter pad,
--- or already taken, so a layout that has drifted past the bow taper reports
--- itself rather than silently leaving gaps.
local function fit(ox, oy, sprite, tag, loot, amount)
    if not sprite then
        U.warnOnce("fit:" .. tostring(tag), "no sprite for " .. tostring(tag))
        return false
    end
    if not inShape(ox, oy) or C.isLanding(ox, oy) then return false end
    if not claim(ox, oy, tag) then return false end

    local x, y = at(ox, oy)
    local sq = U.square(x, y, C.CabinZ, true)
    if not sq then return false end
    if not loot then
        return U.addObject(sq, sprite, tag) ~= nil
    end
    local obj, made = U.addContainer(sq, sprite, tag)
    -- Only ever stock a container the moment it is made. A rebuild leaves a
    -- lived-in ship exactly as the player left it.
    if obj and (made or C.DevRestock) then U.stock(obj, loot, amount or 6) end
    return obj ~= nil
end

--- Places `count` copies of a sprite along a line, stocking each one.
--- `opts` may carry { loot = list, amount = n, tag = string }.
local function line(sprite, ox, oy, dx, dy, count, opts)
    opts = opts or {}
    local placed = 0
    for i = 0, count - 1 do
        if fit(ox + dx * i, oy + dy * i, sprite, opts.tag, opts.loot, opts.amount) then
            placed = placed + 1
        end
    end
    return placed
end

--- Places a multi-tile piece from C.Pieces at an offset.
---
--- Each half carries its own offset taken from the tileset, so the head and
--- foot of a bed land the right way round. Nothing is placed unless every
--- square the piece needs is free, inside the hull and clear of the pad.
local function place(pieceName, ox, oy, tag)
    local piece = C.Pieces[pieceName]
    if not piece then
        U.warnOnce("piece:" .. tostring(pieceName), "no such piece")
        return false
    end
    for _, part in ipairs(piece) do
        local px, py = ox + part[2], oy + part[3]
        if not inShape(px, py) or C.isLanding(px, py) then return false end
        if claimed[claimKey(px, py)] then
            U.log("layout: %s wants %d,%d but %s is already there",
                  tostring(tag), px, py, tostring(claimed[claimKey(px, py)]))
            return false
        end
    end
    for _, part in ipairs(piece) do
        claim(ox + part[2], oy + part[3], tag)
        local x, y = at(ox + part[2], oy + part[3])
        U.addObject(U.square(x, y, C.CabinZ, true), part[1], tag)
    end
    return true
end

---------------------------------------------------------------------------
-- The layout
---------------------------------------------------------------------------
-- Offsets run 0..CabinW across and 0..CabinL fore to aft, with oy 0 at the
-- bow. The hull tapers at both ends, so an offset that is fine amidships can
-- be outside the ship forward of about oy 6 or aft of about oy 18 --
-- tests/test_layout.py checks every offset below against the floor plan.

--- Deckhead lighting. Kept as a table on B so the layout test can check these
--- offsets the same way it checks the furniture.
B.lampSpots = {
    { 3, 1 }, { 2, 3 }, { 3, 6 },
}

--- Type 6 cockpit: paired flight stations under the forward windows.
local function furnishHelm()
    local S = C.Sprites

    if claim(2, 1, "helm") then
        local hx, hy = at(2, 1)
        local sq = U.square(hx, hy, C.CabinZ, true)
        if sq then
            local already = false
            U.try("scanHelm", function()
                local items = sq:getWorldObjects()
                if not items then return end
                for i = 0, items:size() - 1 do
                    local it = items:get(i)
                    local item = it and it:getItem()
                    if item and item:getFullType() == C.HelmItem then already = true end
                end
            end)
            if not already then
                U.try("addHelm", function()
                    sq:AddWorldInventoryItem(C.HelmItem, 0.5, 0.5, 0.0)
                end)
            end
        end
    end

    fit(1, 0, S.monitors.S, "viewscreen")
    fit(3, 0, S.monitors.S, "viewscreen")
    fit(0, 1, S.terminal.E, "terminal")
    fit(5, 1, S.terminal.W, "terminal")
    fit(1, 2, S.chair.N, "chair")
    fit(4, 2, S.chair.N, "chair")
    fit(0, 2, S.computer.E, "computer")
    fit(5, 2, S.computer.W, "computer")
end

--- Compact wash point and emergency provisions along the starboard wall.
local function furnishGalley()
    local S = C.Sprites
    fit(5, 4, S.sink.W, "sink")
    fit(5, 5, S.locker.W, "provisions", C.Loot.food, 12)
end

--- A shuttle emergency cabinet replaces the old full sick bay.
local function furnishSickBay()
    local S = C.Sprites
    fit(0, 5, S.medCabinet.E, "medical", C.Loot.medical, 16)
end

--- The port passenger bench converts into a two-square emergency berth.
local function furnishQuarters()
    local S = C.Sprites
    place("bunkS", 0, 3, "bunk")
    fit(5, 3, S.chair.W, "passenger")
end

--- Compact mission storage around the aft hatch approach.
local function furnishCargo()
    local S = C.Sprites
    fit(1, 8, S.crate, "storage", C.Loot.food, 12)
    fit(3, 8, S.metalShelf.N, "equipment", C.Loot.tools, 10)
    fit(5, 7, S.locker.W, "storage", C.Loot.linen, 6)
end

--- The phaser locker, stood beside the transporter pad, so anyone who beams
--- aboard is looking straight at it.
---
--- Stocked with U.stockEach rather than U.stock: there is exactly one item
--- type in it, and reading the container back proves all four arrived instead
--- of hoping they did.
local function furnishPhasers()
    local S = C.Sprites
    local ox, oy = C.PhaserRack.x, C.PhaserRack.y
    if not inShape(ox, oy) or C.isLanding(ox, oy) then
        U.warnOnce("phaserRack", "C.PhaserRack falls outside the cabin or on the pad")
        return
    end
    if not claim(ox, oy, "phasers") then return end

    local x, y = at(ox, oy)
    local rack, made = U.addContainer(U.square(x, y, C.CabinZ, true),
                                      S.locker.W, "phasers")
    if rack and (made or C.DevRestock) then
        local present = U.stockEach(rack, { C.PhaserItem }, C.PhaserCount)
        local n = present[C.PhaserItem] or 0
        if n < C.PhaserCount then
            U.log("phaser locker holds %d of %d", n, C.PhaserCount)
        end
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
              furnishHelm()
              furnishGalley()
              furnishSickBay()
              furnishQuarters()
              furnishCargo()
              furnishPhasers()
          end },
        { "lightCabin",     lightCabin },
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
