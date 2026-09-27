--[[ Shuttlecraft -- the field station's way in, on the server (FIELD_STATION.md 3).

    Three jobs, all of them world state and so all of them the server's:

    * **Checking the wall.** C.FieldStation names a square read off the
      vanilla map. Before anything goes on it, the server asks the world:
      is the square in a room of that name, is there a solid wall on that
      edge (a wall, never a window or a doorway), and is there nothing else
      standing there. If not, it walks the rest of the same room for a square
      that passes. If none does it says so, once, with a WARN, and places
      nothing: it never hangs a door on a wall it has not looked at.
    * **Keeping the box there.** The first time the stockroom's chunk is
      loaded, the breaker box goes on the wall -- placed, not shipped, for the
      cabin's reason: the mod does not edit a vanilla map cell. On every later
      load the server looks again, and puts back whatever should be there (the
      box, or once it is opened the panel) if somebody has taken it away.
    * **Opening it.** `stationOpen` from a player in reach, measured on the
      server's own copy of them: the box comes off the wall, the panel goes
      on, and `found` is published in the ship state for every client.

    Going down and coming back up are moves, granted in TREK_Server's MOVES
    (`stationDown`, `stationUp`), because a move of a player's own character
    is a client's to make and a server's to ration.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_FieldStation"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Ship = TREK.Ship
local FS = TREK.FieldStation

local FSS = {}
TREK.FieldStationServer = FSS

---------------------------------------------------------------------------
-- The record
---------------------------------------------------------------------------
--- The published record, made if it is not there. Ship state, so every
--- client has it; small -- a square and a flag.
function FSS.record()
    local s = Ship.get()
    if type(s.station) ~= "table" then s.station = {} end
    return s.station
end

---------------------------------------------------------------------------
-- The wall
---------------------------------------------------------------------------
local function spriteName(o)
    return U.try("fs.sprite", function()
        local spr = o:getSprite()
        return spr and spr:getName()
    end)
end

local function props(o)
    return U.try("fs.props", function()
        local spr = o:getSprite()
        return spr and spr:getProperties()
    end)
end

local function has(p, key)
    return p ~= nil and U.try("fs.has", function() return p:has(key) end) == true
end

local function tagOf(o)
    return U.try("fs.tag", function() return o:getModData().TREK end)
end

--- The name of the room a square is in, or nil.
function FSS.roomName(sq)
    return U.try("fs.room", function()
        local def = sq:getRoomDef()
        return def and def:getName()
    end)
end

--- Why a square will not take the box on `edge`, or nil when it will.
---
--- Returns a reason rather than a boolean, so a refusal says which rule it
--- broke in the log (DEV_GUIDE: *A nil from U.try does not mean "no"*).
function FSS.checkSquare(sq, edge, room)
    if not sq then return "unloaded" end
    if room and FSS.roomName(sq) ~= room then return "room" end
    local wallKeys = edge == "N" and { "WallN", "WallNW" } or { "WallW", "WallNW" }
    local notKeys = edge == "N" and { "WindowN", "windowN", "DoorWallN", "doorN" }
                                or { "WindowW", "windowW", "DoorWallW", "doorW" }
    local wall, why = false, nil
    local floor = U.try("fs.floor", function() return sq:getFloor() end)
    if not floor then return "floor" end
    U.eachObject(sq, function(o)
        if o == floor or instanceof(o, "IsoWorldInventoryObject") then return end
        local tag = tagOf(o)
        if tag == FS.TAG then return end          -- our own box or panel
        local name = spriteName(o) or ""
        local p = props(o)
        for _, k in ipairs(notKeys) do
            if has(p, k) then why = "opening" return false end
        end
        for _, k in ipairs(wallKeys) do
            if has(p, k) then wall = true return end
        end
        -- A wall's trim, paint and grime are part of the wall. The
        -- stockroom's walls all carry a `WallOverlay` trim tile
        -- (location_trailer_02_48); a rule that called it furniture found
        -- nowhere in the room to hang the box (tools/fieldstation_site.py).
        if name:sub(1, 8) == "overlay_" or has(p, "WallOverlay") then return end
        if name:sub(1, 6) == "walls_" and not has(p, "attachedW") and not has(p, "attachedN") then
            return
        end
        why = "occupied"
        return false
    end)
    if why then return why end
    if not wall then return "wall" end
    return nil
end

--- The square the box goes on: the configured one when it passes, else the
--- first in the same room that does (north to south, west to east, so the
--- choice is the same every time). Returns x, y, z, edge, or nil and why.
function FSS.chooseSpot()
    local site = C.FieldStation
    local sq = U.square(site.x, site.y, site.z, false)
    if not sq then return nil, "unloaded" end
    local why = FSS.checkSquare(sq, site.edge, site.room)
    if not why then return site.x, site.y, site.z, site.edge end
    U.log("field station: %d,%d will not take the box (%s); looking along the room",
          site.x, site.y, why)
    local def = U.try("fs.roomDef", function() return sq:getRoomDef() end)
    if not def or FSS.roomName(sq) ~= site.room then
        return nil, "the configured square is not in a room called " .. site.room
    end
    local x0 = U.try("fs.rx", function() return def:getX() end)
    local y0 = U.try("fs.ry", function() return def:getY() end)
    local x1 = U.try("fs.rx2", function() return def:getX2() end)
    local y1 = U.try("fs.ry2", function() return def:getY2() end)
    if not (x0 and y0 and x1 and y1) then return nil, "no bounds for the room" end
    for y = y0, y1 do
        for x = x0, x1 do
            for _, edge in ipairs({ "W", "N" }) do
                if U.chunkLoaded(x, y, site.z) then
                    local s2 = U.square(x, y, site.z, false)
                    if s2 and not FSS.checkSquare(s2, edge, site.room) then
                        return x, y, site.z, edge
                    end
                end
            end
        end
    end
    return nil, "no bare wall in the room"
end

---------------------------------------------------------------------------
-- The box and the panel
---------------------------------------------------------------------------
--- Our pieces on a square: { box = obj, panel = obj }.
local function ours(sq)
    local out = {}
    U.eachObject(sq, function(o)
        if tagOf(o) == FS.TAG then
            local name = spriteName(o)
            for _, e in ipairs({ "W", "N" }) do
                if name == FS.BoxSprite[e] then out.box = o end
                if name == FS.PanelSprite[e] then out.panel = o end
            end
            if not out.box and not out.panel and name then out.stray = o end
        end
    end)
    return out
end
FSS.ours = ours

local function place(sq, sprite)
    local obj = U.try("fs.new", function() return IsoObject.new(sq, sprite, "") end)
    if not obj then return nil end
    U.try("fs.tagNew", function() obj:getModData().TREK = FS.TAG end)
    local ok = U.try("fs.add", function()
        sq:transmitAddObjectToSquare(obj, -1)
        return true
    end)
    return ok and obj or nil
end

local function remove(sq, obj)
    return U.try("fs.remove", function()
        sq:transmitRemoveItemFromSquare(obj)
        return true
    end) == true
end

--- Makes the wall match the record: the box before it is opened, the panel
--- after, exactly one of them. Returns what it did, for the log and tests.
function FSS.fit(sq, rec)
    local edge = rec.edge or "W"
    local want = rec.found and FS.PanelSprite[edge] or FS.BoxSprite[edge]
    local have = ours(sq)
    local did = nil
    -- The one it should not be, or a stray of ours: off the wall. (Two
    -- separate looks: ipairs over a list with a nil in it stops there.)
    local wrong = rec.found and have.box or (not rec.found and have.panel) or nil
    if wrong and remove(sq, wrong) then did = "swapped" end
    if have.stray and remove(sq, have.stray) then did = "swapped" end
    local current = rec.found and have.panel or have.box
    if current and spriteName(current) ~= want then
        remove(sq, current)
        current = nil
    end
    if not current then
        if place(sq, want) then did = did or "placed" end
    end
    return did
end

--- The look that runs while anybody is near the store: choose the square
--- the first time, then keep the wall right.
function FSS.service()
    local rec = FSS.record()
    local site = C.FieldStation
    local x, y, z = rec.x or site.x, rec.y or site.y, rec.z or site.z
    if not U.chunkLoaded(x, y, z) then return nil end
    if not rec.x then
        local cx, cy, cz, edge = FSS.chooseSpot()
        if not cx then
            if cy ~= "unloaded" then
                U.warnOnce("fs.noSpot", "field station: nowhere to hang the box in %s's %s (%s); "
                           .. "the station has no way in in this world", site.name, site.room, tostring(cy))
            end
            return nil
        end
        rec.x, rec.y, rec.z, rec.edge = cx, cy, cz, edge
        rec.found = rec.found == true
        U.log("field station: the box goes on %d,%d,%d (%s wall)", cx, cy, cz, edge)
        Ship.commit()
        x, y, z = cx, cy, cz
    end
    local sq = U.square(x, y, z, false)
    if not sq then return nil end
    local did = FSS.fit(sq, rec)
    if did then
        U.log("field station: %s the %s at %d,%d", did, rec.found and "panel" or "box", x, y)
    end
    return did
end

---------------------------------------------------------------------------
-- Opening it
---------------------------------------------------------------------------
Net.onServer("stationOpen", function(player)
    if not player or U.try("fs.dead", function() return player:isDead() end) ~= false then return end
    local rec = FSS.record()
    if not rec.x then return end
    -- Measured here, on this machine's copy of them: a client is a request.
    if not FS.playerInReach(player) then
        Net.toClient(player, "denied", { why = "stationFar" })
        return
    end
    if rec.found then
        Net.toClient(player, "stationOpened", { again = true })
        return
    end
    rec.found = true
    local sq = U.square(rec.x, rec.y, rec.z, false)
    if sq then FSS.fit(sq, rec) end
    Ship.commit()
    U.log("field station: %s opened the breaker box",
          U.try("fs.who", function() return player:getUsername() end) or "?")
    Net.toClient(player, "stationOpened", {})
end)

local tick = 0
Events.OnTick.Add(function()
    tick = tick + 1
    if tick < C.FieldStation.serviceTicks then return end
    tick = 0
    U.try("fs.service", FSS.service)
end)

return FSS
