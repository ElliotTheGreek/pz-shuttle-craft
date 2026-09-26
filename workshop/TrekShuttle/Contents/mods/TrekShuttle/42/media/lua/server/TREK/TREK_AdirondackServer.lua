--[[ Shuttlecraft -- the U.S.S. Adirondack, raised on the server.

    The cabin's pattern (TREK_Build.lua), deck by deck: nothing is built until
    somebody is standing there, because nothing may be built into a chunk that
    is not loaded, and a deck is built whole and at once when it is.

    Every object is finished first -- a locker stocked, a sink given its
    water -- and then sent, so every client gets the same object with what is
    in it. Everything placed is tagged `adk` in its mod data. That tag is what
    a clearing pass leaves alone and what an update after a layout change looks
    at: an object tagged `adk` standing where the layout no longer puts it is
    taken away -- unless it is a container with something in it, which is left
    where it is. What a player keeps in a locker is never ours to throw out.

    **Doors are special objects.** A closed IsoDoor blocks only from the
    square's special-objects list (IsoGridSquare.testCollideSpecialObjects ->
    IsoDoor.TestCollide), and transmitAddObjectToSquare never puts anything
    there -- AddTileObject does not. So a door goes in with AddSpecialObject
    and is sent with transmitCompleteItemToClients, which carries the
    "special" flag so every client registers it too. Vanilla's own doors do
    exactly this (ISWoodenDoor.lua:20,27). The first build sent doors the
    other way, and you could walk straight through them.

    **And they open for you.** A closed door with a player within reach of
    it opens; an open one with nobody near and nothing in the doorway closes.
    Through ToggleDoor, the engine's own path: it swaps the sprite, recalcs
    the squares, syncs every client and plays the tile's DoorSound -- the
    shoosh, TrekDoorOpen / TrekDoorClose.

    A deck is current when `decks[k] == L.rev`. The state is server mod data,
    never transmitted: a client learns a deck is ready from `adkReady`, and
    from the floor turning up under it.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Adirondack"
require "TREK/TREK_Power"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local A = TREK.Adirondack
local L = A.Layout

local AS = {}
TREK.AdirondackServer = AS

local TAG = "adk"
-- Bumped when what an existing object needs changes (doors registered,
-- containers stocked, sinks with water): a deck built by an older one is
-- repaired in place on the next visit, without anything being rebuilt.
AS.FIT = 5

function AS.state()
    local s = ModData.getOrCreate(A.StateKey)
    s.decks = s.decks or {}
    s.fit = s.fit or {}
    return s
end

function AS.deckCurrent(k)
    local s = AS.state()
    return s.decks[k] == L.rev and s.fit[k] == AS.FIT
end

---------------------------------------------------------------------------
-- Objects
---------------------------------------------------------------------------
local function spriteOf(o)
    return U.try("spriteName", function()
        local spr = o:getSprite()
        return spr and spr:getName()
    end)
end

local function tagOf(o)
    return U.try("md", function() return o:getModData().TREK end)
end

local function addSynced(sq, obj)
    return U.try("transmitAddObjectToSquare", function()
        sq:transmitAddObjectToSquare(obj, -1)
        return true
    end) == true
end

local function removeSynced(sq, obj)
    return U.try("transmitRemoveItemFromSquare", function()
        sq:transmitRemoveItemFromSquare(obj)
        return true
    end) == true
end

local function holdsAnything(o)
    return (U.itemCount(o) or 0) > 0
end

local function isDoorKind(kind) return kind == "dW" or kind == "dN" end

local function isSpecial(sq, obj)
    return U.try("specialObjects", function()
        return sq:getSpecialObjects():contains(obj)
    end) == true
end

--- A water store of its own, full: vanilla's addWaterContainer, as the
--- cabin's galley sink has (TREK_Build, addWaterStore).
local function addWaterStore(obj)
    local f = ComponentType.FluidContainer:CreateComponent()
    f:setCapacity(C.WaterCapacity)
    f:addFluid(FluidType.Water, C.WaterCapacity)
    GameEntityFactory.AddComponent(obj, true, f)
end

local function waterCapacity(obj)
    return U.try("fluidCapacity", function() return obj:getFluidCapacity() end) or 0
end

--- What a container is stocked with, by the piece it is part of (A.Stock).
--- Returns the number of items put in.
local function stock(obj, piece)
    local rule = piece and A.Stock[piece]
    if not rule then return 0 end
    local added = 0
    if rule.loot then
        local list = C.Loot[rule.loot]
        if list then
            added = added + (U.fill(obj, list) or 0)
        else
            U.warnOnce("adk.loot:" .. rule.loot, "no C.Loot list named " .. rule.loot)
        end
    end
    if rule.items then
        local items = A.stockItems(rule.items)
        if items then
            local present = U.stockEach(obj, items, rule.copies or 1)
            for _, n in pairs(present or {}) do added = added + n end
        end
    end
    return added
end

--- Makes one layout object and sends it, finished. `o` is the layout entry:
--- { x, y, sprite, kind, piece }.
local function make(sq, o)
    local sprite, kind, piece = o[3], o[4], o[5]
    if isDoorKind(kind) then
        local door = U.try("IsoDoor.new", function()
            -- The String constructor: it starts closed and is never locked at
            -- random (the IsoSprite one rolls against the locked-houses option).
            return IsoDoor.new(getCell(), sq, sprite, kind == "dN")
        end)
        if not door then return false end
        U.try("tag", function() door:getModData().TREK = TAG end)
        return U.try("AddSpecialObject", function()
            sq:AddSpecialObject(door)
            if isServer() then door:transmitCompleteItemToClients() end
            return true
        end) == true
    end

    local obj
    if piece == "galley_range" then
        -- A real stove (FARMING.md), the way the shuttle's oven is one
        -- (TREK_Build.placeStove), powered by the deck's bus (servicePowerBus).
        obj = U.try("IsoStove.new", function()
            return IsoStove.new(getCell(), sq, getSprite(sprite))
        end)
    end
    obj = obj or U.try("IsoObject.new", function()
        return IsoObject.new(sq, sprite, "")
    end)
    if not obj then return false end
    U.try("tag", function() obj:getModData().TREK = TAG end)
    if kind == "c" then
        U.try("containers", function()
            obj:createContainersFromSpriteProperties()
            local c = U.containerOf(obj)
            -- Explored, or vanilla rolls its own loot into it on first look.
            if c then c:setExplored(true) end
        end)
        if A.Stock[piece] then
            U.try("stock:" .. tostring(piece), stock, obj, piece)
            U.try("stocked", function() obj:getModData().TREKStock = true end)
        end
    end
    if piece and A.Water[piece] then
        U.try("water:" .. piece, addWaterStore, obj)
    end
    return addSynced(sq, obj)
end

--- True when an object already standing is not what the layout needs any
--- more and has nothing in it to lose: a door the engine does not collide
--- with, a locker that was never stocked, a sink with no water.
local function needsRefit(sq, obj, o)
    local kind, piece = o[4], o[5]
    if isDoorKind(kind) then
        return not isSpecial(sq, obj) or not instanceof(obj, "IsoDoor")
    end
    if piece == "galley_range" and not instanceof(obj, "IsoStove") and not holdsAnything(obj) then
        return true
    end
    if kind == "c" and A.Stock[piece] then
        local md = U.try("md", function() return obj:getModData() end) or {}
        return md.TREKStock ~= true and not holdsAnything(obj)
    end
    if piece and A.Water[piece] then
        return waterCapacity(obj) <= 0
    end
    return false
end

---------------------------------------------------------------------------
-- A deck
---------------------------------------------------------------------------
--- True when every chunk the deck and its clearing margin stand on is loaded.
function AS.deckLoaded(k)
    local m = 2
    for _, p in ipairs({ { -m, -m }, { L.W + m, -m }, { -m, L.H + m }, { L.W + m, L.H + m },
                          { math.floor(L.W / 2), math.floor(L.H / 2) } }) do
        local x, y = A.at(k, p[1], p[2])
        if not U.chunkLoaded(x, y, A.Z) or not U.chunkLoaded(x, y, 0) then return false end
    end
    return true
end

--- What the layout puts on each square of a deck: key "x,y" -> { sprite -> entry }.
local function wanted(deck)
    local out = {}
    for _, o in ipairs(deck.objects) do
        local key = o[1] .. "," .. o[2]
        out[key] = out[key] or {}
        out[key][o[3]] = o
    end
    return out
end

--- Builds or updates deck k. Idempotent: every step looks before it adds.
function AS.buildDeck(k)
    local deck = L.decks[k]
    if not deck or not AS.deckLoaded(k) then return false end
    local want = wanted(deck)

    local cleared, removed, made, refitted = 0, 0, 0, 0
    -- The engine grows wilderness in unmapped cells when a server was not
    -- given the void map; strip the footprint and a margin, on the deck's own
    -- level and on the ground below it, keeping anything tagged and anything
    -- lying on the floor.
    for lx = -2, L.W + 2 do
        for ly = -2, L.H + 2 do
            local x, y = A.at(k, lx, ly)
            cleared = cleared + U.clearSquare(U.square(x, y, 0, false), true)
            local sq = U.square(x, y, A.Z, false)
            if sq then
                local here = want[lx .. "," .. ly] or {}
                local doomed = {}
                U.eachObject(sq, function(o)
                    if instanceof(o, "IsoWorldInventoryObject") then return end
                    if o == sq:getFloor() then return end
                    local tag = tagOf(o)
                    local md = U.try("md.plant", function() return o:getModData() end)
                    if md and (md.typeOfSeed ~= nil or md.nbOfGrow ~= nil) then
                        -- A plant in a hydroponic tray: vanilla farming's
                        -- object, untagged, and never ours to clear.
                        return
                    end
                    if instanceof(o, "IsoGenerator") then return end
                    if tag == TAG then
                        local entry = here[spriteOf(o)]
                        if not entry then
                            if not holdsAnything(o) then table.insert(doomed, o) end
                        elseif needsRefit(sq, o, entry) then
                            table.insert(doomed, o)
                            refitted = refitted + 1
                        end
                    elseif not tag then
                        table.insert(doomed, o)
                    end
                end)
                for _, o in ipairs(doomed) do
                    if removeSynced(sq, o) then removed = removed + 1 end
                end
            end
        end
    end

    for _, f in ipairs(deck.floors) do
        local x, y = A.at(k, f[1], f[2])
        local sq = U.square(x, y, A.Z, true)
        if sq and not sq:getFloor() then
            U.try("addFloor", function() sq:addFloor(f[3]) end)
        end
    end

    U.resetStockCursors()
    for _, o in ipairs(deck.objects) do
        local x, y = A.at(k, o[1], o[2])
        local sq = U.square(x, y, A.Z, true)
        if sq and not U.findSprite(sq, o[3]) then
            if make(sq, o) then made = made + 1 end
        end
    end

    U.try("adk.doctor", AS.serviceDoctor, k)
    if TREK.Farm then
        U.try("adk.trays", TREK.Farm.primeDeck, k)
        U.try("adk.bay", TREK.Farm.stockBay, k)
    end
    U.try("adk.bus", AS.servicePowerBus, k)

    local s = AS.state()
    s.decks[k], s.fit[k] = L.rev, AS.FIT
    U.log("Adirondack %s built (rev %d): %d placed, %d refitted, %d taken away, %d cleared",
          deck.name, L.rev, made, refitted, removed - refitted, cleared)
    return true
end

---------------------------------------------------------------------------
-- Her Doctor
---------------------------------------------------------------------------
local STEP = { E = { 1, 0 }, W = { -1, 0 }, S = { 0, 1 }, N = { 0, -1 } }

--- Stands exactly one Doctor in front of every EMH station on deck k. He is
--- always projected aboard her (TREK_EMH, E.isUp). Counted before placing,
--- because a world item is saved, the way B.serviceEMH does it for the cabin.
function AS.serviceDoctor(k)
    local placed = 0
    for _, o in ipairs(L.decks[k].objects) do
        if o[5] == "emh_station" then
            local facing = U.try("stationFacing", function()
                return getSprite(o[3]):getProperties():get("Facing")
            end) or "E"
            local step = STEP[facing] or STEP.E
            local x, y = A.at(k, o[1] + step[1], o[2] + step[2])
            local sq = U.square(x, y, A.Z, true)
            if sq then
                local have = 0
                U.try("adk.doctorCount", function()
                    local items = sq:getWorldObjects()
                    for i = 0, items:size() - 1 do
                        local it = items:get(i):getItem()
                        if it and it:getFullType() == C.EmhItem then have = have + 1 end
                    end
                end)
                if have == 0 then
                    local item = U.try("adk.doctorPlace", function()
                        return sq:AddWorldInventoryItem(C.EmhItem, 0.5, 0.5, 0.0)
                    end)
                    if item then
                        U.try("adk.doctorTurn", function()
                            item:setWorldXRotation(0)
                            item:setWorldYRotation(0)
                            item:setWorldZRotation(A.DoctorYaw[facing] or 0)
                        end)
                        placed = placed + 1
                    end
                end
            end
        end
    end
    return placed
end

---------------------------------------------------------------------------
-- The galley's power bus
---------------------------------------------------------------------------
-- An oven needs electricity, and a runtime deck is on no grid. The shuttle's
-- answer (TREK_Build.servicePowerBus) is an invisible generator, fuelled from
-- the ship's reserve; hers is the same, on the galley range's own square, so
-- the stove and the stasis units nearby have power, billed to her warp core.
function AS.servicePowerBus(k)
    local range = nil
    for _, o in ipairs(L.decks[k].objects) do
        if o[5] == "galley_range" then range = o break end
    end
    if not range then return nil end
    local x, y = A.at(k, range[1], range[2])
    if not U.chunkLoaded(x, y, A.Z) then return nil end
    local sq = U.square(x, y, A.Z, false)
    if not sq then return nil end
    local gen = nil
    U.eachObject(sq, function(o)
        if not gen and instanceof(o, "IsoGenerator") then gen = o end
    end)
    if not gen then
        local item = U.try("adk.busItem", function() return instanceItem(C.PowerBusItem) end)
        if not item then return nil end
        U.try("adk.busSetup", function()
            item:setCondition(100)
            item:getModData().fuel = 10.0
        end)
        gen = U.try("adk.busGen", function() return IsoGenerator.new(item, getCell(), sq) end)
        if not gen then return nil end
        U.try("adk.busTag", function()
            gen:getModData().TREK = C.PowerBusTag
            gen:transmitModData()
            gen:setConnected(true)
        end)
        U.log("Adirondack %s: power bus placed at the galley range", L.decks[k].name)
    end
    local P = TREK.Power
    local max = U.try("adk.busMax", function() return gen:getMaxFuel() end) or 10
    local fuel = U.try("adk.busFuel", function() return gen:getFuel() end) or max
    if max - fuel > 0.0001 and TREK.Energy then
        P.using("adk", function()
            TREK.Energy.energize(nil, "galley", (max - fuel) * C.FuelToEnergy,
                                 { partial = true, silent = true })
        end)
    end
    if fuel < max then U.try("adk.busRefuel", function() gen:setFuel(max) end) end
    U.try("adk.busMend", function()
        if gen:getCondition() < 100 then gen:setCondition(100) end
    end)
    local want = not P.dark("adk")
    if U.try("adk.busOn", function() return gen:isActivated() end) ~= want then
        U.try("adk.busSwitch", function() gen:setActivated(want) end)
    end
    return gen
end

---------------------------------------------------------------------------
-- Water
---------------------------------------------------------------------------
--- Tops up every sink on a built, loaded deck. Running water aboard a
--- starship does not run out.
function AS.refillWater()
    local topped = 0
    for k, deck in ipairs(L.decks) do
        if AS.state().decks[k] then
            for _, o in ipairs(deck.objects) do
                if o[5] and A.Water[o[5]] then
                    local x, y = A.at(k, o[1], o[2])
                    if U.chunkLoaded(x, y, A.Z) then
                        local obj = U.findSprite(U.square(x, y, A.Z, false), o[3])
                        local cap = obj and waterCapacity(obj) or 0
                        if cap > 0 then
                            U.try("adk.topUp", function()
                                local have = obj:getFluidAmount() or 0
                                if have < cap then
                                    obj:addFluid(FluidType.Water, cap - have)
                                    topped = topped + 1
                                end
                            end)
                        end
                    end
                end
            end
        end
    end
    return topped
end

---------------------------------------------------------------------------
-- Doors that open as you walk up
---------------------------------------------------------------------------
-- Squares from a door's own edge, measured from the middle of the doorway.
local OPEN_REACH = 1.7
local CLOSE_CLEAR = 2.3
-- Ticks a door stays open at the least, so it never flutters.
local HOLD_TICKS = 40

local doorList = nil   -- { { k, x, y, north } }
local openSince = {}   -- "k,x,y" -> tick opened

local function doors()
    if doorList then return doorList end
    doorList = {}
    for k, deck in ipairs(L.decks) do
        for _, o in ipairs(deck.objects) do
            if isDoorKind(o[4]) then
                table.insert(doorList, { k, o[1], o[2], o[4] == "dN", o[3] })
            end
        end
    end
    return doorList
end

local function doorOn(sq, sprite)
    local found = nil
    U.try("adk.findDoor", function()
        local list = sq:getSpecialObjects()
        for i = 0, list:size() - 1 do
            local o = list:get(i)
            if instanceof(o, "IsoDoor") and tagOf(o) == TAG then found = o return end
        end
    end)
    return found
end

local function nearest(players, cx, cy)
    local best, bd = nil, nil
    for _, p in ipairs(players) do
        local d = U.dist2(p.x, p.y, cx, cy)
        if not bd or d < bd then best, bd = p, d end
    end
    return best, bd and math.sqrt(bd) or nil
end

local function clearDoorway(door)
    local busy = U.try("adk.doorway", function()
        local n = door:getSquare():getMovingObjects():size()
        local other = door:getOppositeSquare()
        if other then n = n + other:getMovingObjects():size() end
        return n
    end)
    return (busy or 0) == 0
end

local doorTick = 0
function AS.serviceDoors()
    doorTick = doorTick + 1
    -- Who is aboard her, and where: once, for every door.
    local aboard = {}
    for _, p in ipairs(U.players()) do
        local x = U.try("px", function() return p:getX() end)
        local y = U.try("py", function() return p:getY() end)
        local z = U.try("pz", function() return p:getZ() end)
        local dead = U.try("dead", function() return p:isDead() end)
        if x and dead == false then
            local k = A.locate(x, y, z)
            if k then
                aboard[k] = aboard[k] or {}
                table.insert(aboard[k], { p = p, x = x, y = y })
            end
        end
    end
    -- And the crew: a door opens for them too (TREK_CrewServer). ToggleDoor
    -- takes any character; for a zombie the clients play no sound, and a
    -- door a crew member opens is usually one somebody is watching anyway.
    if TREK.CrewServer then
        for _, b in ipairs(TREK.CrewServer.bodies()) do
            aboard[b.k] = aboard[b.k] or {}
            table.insert(aboard[b.k], { p = b.z, x = b.x, y = b.y })
        end
    end
    local any = false
    for _ in pairs(aboard) do any = true break end
    if not any then return 0 end

    local moved = 0
    for _, d in ipairs(doors()) do
        local k, lx, ly, north = d[1], d[2], d[3], d[4]
        local here = aboard[k]
        if here then
            local x, y = A.at(k, lx, ly)
            -- The middle of the doorway: a W door is the west edge of its
            -- square, an N door the north edge.
            local cx, cy = x, y + 0.5
            if north then cx, cy = x + 0.5, y end
            local who, dist = nearest(here, cx, cy)
            if dist then
                local sq = U.square(x, y, A.Z, false)
                local door = sq and doorOn(sq, d[5])
                if door then
                    local key = k .. "," .. lx .. "," .. ly
                    local open = U.try("isOpen", function() return door:IsOpen() end) == true
                    if not open and dist <= OPEN_REACH then
                        U.try("adk.open", function() door:ToggleDoor(who.p) end)
                        openSince[key] = doorTick
                        moved = moved + 1
                    elseif open and dist > CLOSE_CLEAR
                           and doorTick - (openSince[key] or 0) >= HOLD_TICKS / 10
                           and clearDoorway(door) then
                        U.try("adk.close", function() door:ToggleDoor(who.p) end)
                        openSince[key] = nil
                        moved = moved + 1
                    end
                end
            end
        end
    end
    return moved
end

---------------------------------------------------------------------------
-- Players waiting for a deck
---------------------------------------------------------------------------
-- username -> deck index, for players standing (held) on a deck that may not
-- exist yet. Answered with adkReady once it does.
local waiting = {}

local function nameOf(p)
    return U.try("username", function() return p:getUsername() end) or "?"
end

local function serviceWaiting()
    local any = false
    for _ in pairs(waiting) do any = true break end
    if not any then return end
    for _, p in ipairs(U.players()) do
        local k = waiting[nameOf(p)]
        if k then
            local ready = AS.deckCurrent(k) or AS.buildDeck(k)
            if ready then
                Net.toClient(p, "adkReady", { deck = k, rev = L.rev })
                waiting[nameOf(p)] = nil
            end
        end
    end
end
AS.serviceWaiting = serviceWaiting

--- A client is standing on (or arriving at) deck k and needs it.
Net.onServer("adkBoarded", function(player, args)
    local k = tonumber(args.deck)
    if not player or not k or not L.decks[k] then return end
    -- Only for a player actually on the ship: the deck is built where they
    -- stand, and the request is theirs to make only from there.
    if not A.onShip(player) then return end
    waiting[nameOf(player)] = k
    serviceWaiting()
end)

local tick = 0
Events.OnTick.Add(function()
    tick = tick + 1
    if tick < 10 then return end
    tick = 0
    U.try("adk.serviceWaiting", serviceWaiting)
    U.try("adk.serviceDoors", AS.serviceDoors)
end)

Events.EveryOneMinute.Add(function()
    U.try("adk.refillWater", AS.refillWater)
end)

Events.EveryHours.Add(function()
    for k = 1, #L.decks do
        if AS.state().decks[k] then U.try("adk.busHourly", AS.servicePowerBus, k) end
    end
end)

return AS
