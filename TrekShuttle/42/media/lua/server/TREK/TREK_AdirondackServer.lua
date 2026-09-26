--[[ Shuttlecraft -- the U.S.S. Adirondack, raised on the server.

    The cabin's pattern (TREK_Build.lua), deck by deck: nothing is built until
    somebody is standing there, because nothing may be built into a chunk that
    is not loaded, and a deck is built whole and at once when it is.

    Every object is finished first and then sent with transmitAddObjectToSquare,
    so every client gets the same object, containers and all. Everything placed
    is tagged `adk` in its mod data. That tag is what a clearing pass leaves
    alone and what an update after a layout change looks at: an object tagged
    `adk` standing where the layout no longer puts it is taken away -- unless
    it is a container with something in it, which is left where it is. What a
    player keeps in a locker is never ours to throw out.

    A deck is current when `decks[k] == L.rev`. The state is server mod data,
    never transmitted: a client learns a deck is ready from `adkReady`, and
    from the floor turning up under it.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Adirondack"

TREK = TREK or {}
local U = TREK.Util
local Net = TREK.Net
local A = TREK.Adirondack
local L = A.Layout

local AS = {}
TREK.AdirondackServer = AS

local TAG = "adk"

function AS.state()
    local s = ModData.getOrCreate(A.StateKey)
    s.decks = s.decks or {}
    return s
end

function AS.deckCurrent(k)
    return AS.state().decks[k] == L.rev
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

local function hasSprite(sq, sprite)
    return U.findSprite(sq, sprite) ~= nil
end

local function holdsAnything(o)
    local c = U.containerOf(o)
    if not c then return false end
    return (U.try("items", function() return c:getItems():size() end) or 0) > 0
end

--- Makes one layout object: a door is an IsoDoor (it opens), a container has
--- its inventory made from the sprite before it is sent, and the rest are
--- plain objects whose sprite properties do the work -- walls block, tables
--- are tables, beds are beds.
local function make(sq, sprite, kind)
    local obj
    if kind == "dW" or kind == "dN" then
        obj = U.try("IsoDoor.new", function()
            return IsoDoor.new(getCell(), sq, sprite, kind == "dN")
        end)
    else
        obj = U.try("IsoObject.new", function()
            return IsoObject.new(sq, sprite, "")
        end)
    end
    if not obj then return false end
    U.try("tag", function() obj:getModData().TREK = TAG end)
    if kind == "c" then
        U.try("containers", function()
            obj:createContainersFromSpriteProperties()
            local c = U.containerOf(obj)
            -- Explored, or vanilla rolls its own loot into it on first look.
            if c then c:setExplored(true) end
        end)
    end
    return addSynced(sq, obj)
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

--- What the layout puts on each square of a deck: key "x,y" -> { sprite -> kind }.
local function wanted(deck)
    local out = {}
    for _, o in ipairs(deck.objects) do
        local key = o[1] .. "," .. o[2]
        out[key] = out[key] or {}
        out[key][o[3]] = o[4]
    end
    return out
end

--- Builds or updates deck k. Idempotent: every step looks before it adds.
function AS.buildDeck(k)
    local deck = L.decks[k]
    if not deck or not AS.deckLoaded(k) then return false end
    local want = wanted(deck)
    local floorAt = {}
    for _, f in ipairs(deck.floors) do floorAt[f[1] .. "," .. f[2]] = f[3] end

    local cleared, removed, made = 0, 0, 0
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
                local key = lx .. "," .. ly
                local here = want[key] or {}
                local doomed = {}
                U.eachObject(sq, function(o)
                    if instanceof(o, "IsoWorldInventoryObject") then return end
                    if o == sq:getFloor() then return end
                    local tag = tagOf(o)
                    if tag == TAG then
                        if not here[spriteOf(o)] and not holdsAnything(o) then
                            table.insert(doomed, o)
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

    for key, sprite in pairs(floorAt) do
        local lx, ly = key:match("(-?%d+),(-?%d+)")
        local x, y = A.at(k, tonumber(lx), tonumber(ly))
        local sq = U.square(x, y, A.Z, true)
        if sq and not sq:getFloor() then
            U.try("addFloor", function() sq:addFloor(sprite) end)
        end
    end

    for _, o in ipairs(deck.objects) do
        local x, y = A.at(k, o[1], o[2])
        local sq = U.square(x, y, A.Z, true)
        if sq and not hasSprite(sq, o[3]) then
            if make(sq, o[3], o[4]) then made = made + 1 end
        end
    end

    AS.state().decks[k] = L.rev
    U.log("Adirondack %s built (rev %d): %d placed, %d taken away, %d cleared",
          deck.name, L.rev, made, removed, cleared)
    return true
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
end)

return AS
