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

---------------------------------------------------------------------------
-- Her machines
---------------------------------------------------------------------------
-- The pieces that are machines rather than furniture, by the name the layout
-- gives them. Every square of a multi-square piece counts.
A.Machines = { replicator = true, warp_core = true, emh_station = true }

local machineSquares = nil   -- kind -> { { k, x, y }, ... }

function A.machines(kind)
    if not machineSquares then
        machineSquares = {}
        for k, deck in ipairs(L.decks) do
            for _, o in ipairs(deck.objects) do
                local what = o[5]
                if what and A.Machines[what] then
                    machineSquares[what] = machineSquares[what] or {}
                    table.insert(machineSquares[what], { k, o[1], o[2] })
                end
            end
        end
    end
    return machineSquares[kind] or {}
end

--- True when x, y, z is aboard her and within `range` squares of any square
--- of a machine of this kind. The server measures the same way the menu does.
function A.nearMachine(kind, x, y, z, range)
    if not x or not y then return false end
    local k = A.locate(x, y, z)
    if not k then return false end
    local r2 = range * range
    for _, m in ipairs(A.machines(kind)) do
        if m[1] == k then
            local mx, my = A.at(k, m[2], m[3])
            if U.dist2(x, y, mx + 0.5, my + 0.5) <= r2 then return true end
        end
    end
    return false
end

--- For a right-click: a clicked square on (or `margin` squares round) one.
function A.clickedMachine(kind, x, y, z, margin)
    if not x or not y then return false end
    local k = A.locate(x, y, z)
    if not k then return false end
    x, y = math.floor(x), math.floor(y)
    for _, m in ipairs(A.machines(kind)) do
        if m[1] == k then
            local mx, my = A.at(k, m[2], m[3])
            if math.abs(x - mx) <= margin and math.abs(y - my) <= margin then return true end
        end
    end
    return false
end

---------------------------------------------------------------------------
-- What her lockers hold
---------------------------------------------------------------------------
-- By the piece the container is part of. `loot` is a C.Loot list filled to
-- the usual fraction; `items` are put in `copies` of each. A piece not listed
-- starts empty: somewhere for the crew's own things.
A.Stock = {
    medical_cabinet = { loot = "medical" },
    medical_cart    = { loot = "medical" },
    galley_counter  = { loot = "food" },
    stasis_unit     = { loot = "food" },
    bar_straight    = { loot = "drinks" },
    bar_corner      = { loot = "drinks" },
    bottle_shelf    = { loot = "drinks" },
    wardrobe        = { items = "uniforms", copies = 1 },
    desk            = { items = "desk", copies = 1 },
    ready_room_desk = { items = "desk", copies = 1 },
    display_shelf   = { loot = "weapons" },
    cargo_crate     = { items = "engineering", copies = 2 },
    antigrav_cart   = { items = "dilithium", copies = 2 },
    -- Hydroponics (FARMING.md): seeds of every crop, the bench's tools, and
    -- a tank's founding worms.
    seed_locker     = { items = "seeds", copies = 5 },
    potting_bench   = { items = "garden", copies = 1 },
    worm_tank       = { items = "worms", copies = 3 },
    -- The galley's cookware (FARMING.md): everything the from-scratch
    -- recipes need that is not grown.
    galley_cupboard = { items = "cookware", copies = 1 },
}

--- The item lists A.Stock names. A function, because C is filled in order
--- and some of these are defined further down TREK_Config than this file loads.
function A.stockItems(name)
    if name == "uniforms" then return C.UniformIssue end
    if name == "desk" then return { C.PaddItem, "TrekShuttle.TrekTricorder" } end
    if name == "engineering" then return { C.PhaserItem, "TrekShuttle.TrekTricorder" } end
    if name == "dilithium" then return { C.DilithiumItem } end
    if name == "seeds" then
        return { "TrekShuttle.TrekTeaSeed", "TrekShuttle.TrekBergamotSeed",
                 "TrekShuttle.TrekKlingonCoffeeSeed", "TrekShuttle.TrekPlomeekSeed",
                 "TrekShuttle.TrekLeolaSeed", "TrekShuttle.TrekAndorianTuberSeed",
                 "TrekShuttle.TrekHasperatSeed" }
    end
    if name == "garden" then
        return { "Base.HandShovel", "Base.WateredCan", "Base.MortarPestle", "Base.Pot",
                 "Base.Bowl", "Base.KitchenKnife" }
    end
    if name == "worms" then return { "TrekShuttle.TrekSerpentWorm" } end
    if name == "cookware" then
        return { "Base.Pot", "Base.Pot", "Base.Saucepan", "Base.Pan", "Base.RoastingPan",
                 "Base.BakingTray", "Base.Kettle", "Base.Bowl", "Base.Bowl", "Base.Bowl",
                 "Base.Bowl", "Base.Bowl", "Base.Bowl", "Base.Mugl", "Base.Mugl", "Base.Mugl",
                 "Base.Mugl", "Base.KitchenKnife", "Base.MortarPestle", "Base.Spoon", "Base.Fork",
                 "Base.Ladle", "Base.Spatula", "Base.OvenMitt", "Base.Tortilla", "Base.Tortilla",
                 "Base.Tortilla", "Base.Tortilla" }
    end
    return nil
end

-- Pieces with running water: a store of their own, kept full.
A.Water = { galley_sink = true, wash_basin = true }

-- Her Doctor stands on the square in front of her EMH station, always: he
-- is a world model (C.EmhItem) turned to face out from the station. The
-- model faces south unturned (tools/gen_emh.py); these are the turns for a
-- station whose Facing is each way. NOT YET SEEN IN GAME -- if he stands
-- with his back to the room, this table is what to change.
A.DoctorYaw = { S = 0, E = 90, N = 180, W = 270 }

-- Crystals in her core the first time anybody asks.
A.StartCrystals = 50

return A
