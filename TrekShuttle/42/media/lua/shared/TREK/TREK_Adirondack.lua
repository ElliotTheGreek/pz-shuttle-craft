--[[ Shuttlecraft -- the U.S.S. Adirondack: where she is, shared by both sides.

    The ship is raised at runtime, as the shuttle's cabin is, in the void map's
    cell 97,40, one cell east of the cabin. Its layout is generated from the
    BuildingEd files (tools/gen_adirondack_lua.py, TREK_AdirondackLayout.lua).

    **Her decks stand side by side, on one level.** A runtime building has no
    RoomDefs, and without them the engine draws every level above the player
    over them (TREK_Config, beside CabinZ). So Deck 1 is the westmost and each
    deck after it is L.pitch squares further east. The turbolift car is the
    same squares on every deck, so the lift is the same sideways move every time.

    They stand on the cabin's level, C.CabinZ, for the cabin's reasons: nothing
    that grows or walks on the ground below can reach them, and the arrival
    hold that keeps a player up there until the deck exists is already proven.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local L = require "TREK/TREK_AdirondackLayout"

local A = {}
TREK.Adirondack = A
A.Layout = L

A.Cell = { x = 97, y = 40 }
A.Offset = 16
A.Z = C.CabinZ
-- Squares round each deck that count as "on the ship": the black between the
-- decks, where anybody who climbs a wall is caught and put back.
A.Margin = 6
A.StateKey = "TREK_Adirondack"

function A.origin()
    local size = U.cellSize()
    return A.Cell.x * size + A.Offset, A.Cell.y * size + A.Offset
end

function A.deckCount()
    return #L.decks
end

--- The world square of a deck's own 0,0.
function A.deckOrigin(k)
    local x, y = A.origin()
    return x + L.decks[k].ox, y
end

function A.at(k, lx, ly)
    local x, y = A.deckOrigin(k)
    return x + lx, y + ly
end

--- Which deck a square is on, and where on it: k, lx, ly. Anywhere in the
--- deck's box and its margin counts, at the ship's level only.
function A.locate(x, y, z)
    if not x or not y then return nil end
    if z and math.floor(z) ~= A.Z then return nil end
    x, y = math.floor(x), math.floor(y)
    local m = A.Margin
    for k = 1, #L.decks do
        local dx, dy = A.deckOrigin(k)
        local lx, ly = x - dx, y - dy
        if lx >= -m and lx <= L.W + m and ly >= -m and ly <= L.H + m then
            return k, lx, ly
        end
    end
    return nil
end

function A.onShip(player)
    if not player then return false end
    local ok, k = pcall(function()
        return A.locate(player:getX(), player:getY(), player:getZ())
    end)
    return ok and k ~= nil
end

--- The room a deck square belongs to, or nil for no room.
function A.roomAt(k, lx, ly)
    local deck = L.decks[k]
    if not deck or lx < 0 or ly < 0 or lx >= L.W or ly >= L.H then return nil end
    local rid = deck.grid[ly + 1][lx + 1]
    return rid and rid > 0 and L.rooms[rid] or nil
end

--- True on a square that is inside the ship's walls.
function A.inside(k, lx, ly)
    return A.roomAt(k, lx, ly) ~= nil
end

function A.inLift(x, y, z)
    local k, lx, ly = A.locate(x, y, z)
    if not k then return false end
    local r = A.roomAt(k, lx, ly)
    return r ~= nil and r.internal == "trekturbolift", k
end

--- Where a beam aboard arrives: the transporter pad.
function A.padSpot()
    local x, y = A.at(L.pad.deck, L.pad.x, L.pad.y)
    return x, y, A.Z, L.pad.deck
end

function A.liftSpot(k)
    local x, y = A.at(k, L.lift.x, L.lift.y)
    return x, y, A.Z
end

return A
