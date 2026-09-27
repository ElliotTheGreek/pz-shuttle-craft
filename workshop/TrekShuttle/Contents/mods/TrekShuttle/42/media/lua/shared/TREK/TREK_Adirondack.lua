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

    **Jefferies tubes join them** (JEFFERIES.md): a crawlway from each deck's
    corridor to the next one's, across the gap, over the stars. A tube square
    belongs to the deck it leaves from -- `locate` answers that deck, with an
    lx that runs on past its east edge -- and counts as inside her walls.
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

---------------------------------------------------------------------------
-- Jefferies tubes
---------------------------------------------------------------------------
-- World square "x,y" -> { t = tube index, k = its deck, lx, ly, crawl, hideout }.
local tubeIndex = nil

local function key(x, y) return x .. "," .. y end

function A.tubeIndex()
    if tubeIndex then return tubeIndex end
    tubeIndex = {}
    for t, tube in ipairs(L.tubes or {}) do
        local k = tube.from
        local function mark(list, what)
            for _, p in ipairs(list or {}) do
                local x, y = A.at(k, p[1], p[2])
                local e = tubeIndex[key(x, y)] or { t = t, k = k, lx = p[1], ly = p[2] }
                e[what] = true
                tubeIndex[key(x, y)] = e
            end
        end
        mark(tube.crawl, "crawl")
        mark(tube.hideout, "hideout")
    end
    return tubeIndex
end

--- The tube a square is in: the index entry, or nil. At the ship's level only.
function A.tubeAt(x, y, z)
    if not x or not y then return nil end
    if z and math.floor(z) ~= A.Z then return nil end
    return A.tubeIndex()[key(math.floor(x), math.floor(y))]
end

-- World squares a tube puts anything on -- its floors, and the walls it stands
-- on squares outside itself: "x,y" -> tube index.
local tubeOwned = nil

--- The tube that owns a square, or nil. A deck's own clearing leaves these
--- alone, or it would take a tube's walls for strays.
function A.tubeOwns(x, y)
    if not tubeOwned then
        tubeOwned = {}
        for t, tube in ipairs(L.tubes or {}) do
            for _, list in ipairs({ tube.floors, tube.objects }) do
                for _, o in ipairs(list) do
                    local wx, wy = A.at(tube.from, o[1], o[2])
                    tubeOwned[key(wx, wy)] = t
                end
            end
        end
    end
    return tubeOwned[key(math.floor(x), math.floor(y))]
end

--- True on a square one crawls on: a tube's crawlway, not a hideout.
function A.crawling(x, y, z)
    local e = A.tubeAt(x, y, z)
    return e ~= nil and e.crawl == true
end

--- Which deck a square is on, and where on it: k, lx, ly. Anywhere in the
--- deck's box and its margin counts, at the ship's level only; a tube square
--- is on the deck its tube leaves from.
function A.locate(x, y, z)
    if not x or not y then return nil end
    if z and math.floor(z) ~= A.Z then return nil end
    x, y = math.floor(x), math.floor(y)
    local e = A.tubeIndex()[key(x, y)]
    if e then return e.k, e.lx, e.ly end
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

--- True when a player stands on any of the runtime decks: the Adirondack's
--- or the field station's (FIELD_STATION.md 4). What the machines' menus, the
--- Doctor and the deck builder ask; `onAdirondack` and `onStation` are the
--- two halves, for the few things that differ.
function A.onShip(player)
    return A.siteOfPlayer(player) ~= nil
end

---------------------------------------------------------------------------
-- Two places, one layout
---------------------------------------------------------------------------
-- The field station's sublevels are more decks of this layout, marked
-- `site = "fst"`; hers are `site = "adk"` (FIELD_STATION.md 4). A deck's
-- site decides what its lift lists, its menu's title, its way out, whose
-- power it runs on and what its crew talk about. Nothing else.
A.Sites = { adk = true, fst = true }

--- The site of deck k: "adk" or "fst".
function A.siteOf(k)
    local deck = k and L.decks[k]
    return deck and (deck.site or "adk") or nil
end

--- The site of a square, or nil off both.
function A.siteAt(x, y, z)
    return A.siteOf(A.locate(x, y, z))
end

--- The site a player stands on, or nil.
function A.siteOfPlayer(player)
    if not player then return nil end
    local ok, site = pcall(function()
        return A.siteAt(player:getX(), player:getY(), player:getZ())
    end)
    return ok and site or nil
end

function A.onAdirondack(player) return A.siteOfPlayer(player) == "adk" end
function A.onStation(player) return A.siteOfPlayer(player) == "fst" end

--- True on a square of the field station's old sublevels (L.legacyStation):
--- three floors for one day, now nothing, and a save may have somebody
--- standing on one. They are brought to the station's floor.
function A.inLegacyStation(x, y, z)
    if not x or not y or not L.legacyStation then return false end
    if z and math.floor(z) ~= A.Z then return false end
    local ox, oy = A.origin()
    local lx, ly = math.floor(x) - ox, math.floor(y) - oy
    for _, b in ipairs(L.legacyStation) do
        if lx >= b.x0 and lx <= b.x1 and ly >= b.y0 and ly <= b.y1 then return true end
    end
    return false
end

--- The decks of one site, in lift order: { k, ... }.
function A.decksOf(site)
    local out = {}
    for k = 1, #L.decks do
        if A.siteOf(k) == site then table.insert(out, k) end
    end
    return out
end

--- The room a deck square belongs to, or nil for no room.
function A.roomAt(k, lx, ly)
    local deck = L.decks[k]
    if not deck or lx < 0 or ly < 0 or lx >= L.W or ly >= L.H then return nil end
    local rid = deck.grid[ly + 1][lx + 1]
    return rid and rid > 0 and L.rooms[rid] or nil
end

--- True on a square that is inside the ship's walls: a room, or a tube.
function A.inside(k, lx, ly)
    if A.roomAt(k, lx, ly) ~= nil then return true end
    if not L.decks[k] then return false end
    local x, y = A.at(k, lx, ly)
    return A.tubeIndex()[key(x, y)] ~= nil
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
-- starts empty: somewhere for the crew's own things. `tape` is a recording
-- (content/tapes) put in on a tape of its own.
A.Stock = {
    medical_cabinet = { loot = "medical" },
    -- Sickbay's carts also carry its one stimulant (CONTRABAND.md), which is
    -- not contraband at all until somebody takes a second dose.
    medical_cart    = { loot = "medical", items = "cordrazine", copies = 1 },
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
    -- The hideouts off the Jefferies tubes (JEFFERIES.md): what the off-watch
    -- crew keep where the first officer will not look -- and, since
    -- CONTRABAND.md, what they keep that the Doctor would take off them.
    stash_crate     = { items = "stash", copies = 1, tape = C.HolosuiteTape },
    stash_shelf     = { items = "stash_shelf", copies = 1 },
    -- Each hideout's second crate (ARMOURY.md 7): the same stash its twin
    -- holds -- it was a second stash_crate until the armoury -- and under it
    -- somebody else's weapons, a different culture's in each hideout.
    stash_arms_klingon  = { items = "stash_arms_klingon", copies = 1, tape = C.HolosuiteTape },
    stash_arms_romulan  = { items = "stash_arms_romulan", copies = 1, tape = C.HolosuiteTape },
    stash_arms_dominion = { items = "stash_arms_dominion", copies = 1, tape = C.HolosuiteTape },
    -- The armoury off the bridge (ARMOURY.md 6): Starfleet's issue in the
    -- lockers, one of everybody else's in the trophy case.
    arms_locker     = { items = "arms_locker", copies = 1 },
    trophy_case     = { items = "trophy_case", copies = 1 },
}

-- Whose weapons each hideout keeps, beside its stash (ARMOURY.md 7).
A.StashArms = {
    stash_arms_klingon  = { "TrekShuttle.TrekKlingonDisruptor", "TrekShuttle.TrekKlingonRifle" },
    stash_arms_romulan  = { "TrekShuttle.TrekRomulanDisruptor", "TrekShuttle.TrekCardassianPhaser" },
    stash_arms_dominion = { "TrekShuttle.TrekPolaronRifle" },
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
    if name == "stash" then
        return { "TrekShuttle.TrekRomulanAle", "TrekShuttle.TrekRomulanAle", "Base.Whiskey",
                 "Base.Vodka", "Base.BeerBottle", "Base.BeerBottle", "Base.BeerBottle",
                 "Base.CigarettePack", "Base.Dice", "Base.CardDeck",
                 -- The contraband (CONTRABAND.md), and the pot on the table.
                 "TrekShuttle.TrekKetracelWhite", "TrekShuttle.TrekFelicium",
                 "TrekShuttle.TrekTrelliumD", "TrekShuttle.TrekKtarianGame",
                 "TrekShuttle.TrekLatinumStrip", "TrekShuttle.TrekLatinumStrip",
                 "TrekShuttle.TrekLatinumStrip" }
    end
    if A.StashArms[name] then
        local out = {}
        for _, id in ipairs(A.stockItems("stash")) do table.insert(out, id) end
        for _, id in ipairs(A.StashArms[name]) do table.insert(out, id) end
        return out
    end
    if name == "arms_locker" then
        -- A locker per wall of the armoury holds a watch's worth: two
        -- phasers, a phaser rifle, and a holster for each phaser.
        return { C.PhaserItem, C.PhaserItem, C.PhaserRifleItem, C.HolsterItem, C.HolsterItem }
    end
    if name == "trophy_case" then
        return { "TrekShuttle.TrekKlingonDisruptor", "TrekShuttle.TrekKlingonRifle",
                 "TrekShuttle.TrekRomulanDisruptor", "TrekShuttle.TrekPolaronRifle",
                 "TrekShuttle.TrekCardassianPhaser" }
    end
    if name == "stash_shelf" then
        return { "TrekShuttle.TrekBloodwine", "TrekShuttle.TrekAndorianAle", "Base.Rum",
                 "Base.Scotch", "Base.BeerBottle",
                 "TrekShuttle.TrekKanar", "TrekShuttle.TrekSaurianBrandy",
                 "TrekShuttle.TrekAldebaranWhiskey" }
    end
    if name == "cordrazine" then return { C.Cordrazine.item } end
    if name == "records" then
        -- What a cultural survey kept of the county: its reading, and a PADD
        -- to catalogue it on. Not its tapes: a retail tape made here would
        -- be blank (TREK_Build's warning), and a blank tape is not a record.
        return { "Base.Book", "Base.Book", "Base.Magazine", "Base.Magazine", "Base.Newspaper",
                 "Base.ComicBook", "Base.BookFancy_History", "Base.BookFancy_ClassicNonfiction",
                 C.PaddItem }
    end
    if name == "station_arms" then
        return { C.PhaserItem, C.PhaserItem, C.HolsterItem, C.HolsterItem }
    end
    if name == "station_stores" then
        -- A set to take home first (INSTALLATIONS.md), the survey's spares:
        -- a crate drops what no longer fits, and the heavy kits are the point.
        return { "TrekShuttle.TrekWarpCoreKit", "TrekShuttle.TrekReplicatorKit",
                 "TrekShuttle.TrekEMHKit",
                 "Base.TinnedBeans", "Base.TinnedSoup", "Base.CannedCorn", "Base.WaterBottle",
                 "Base.WaterBottle", "Base.Battery", "Base.Battery", "Base.Torch",
                 "TrekShuttle.TrekTricorder" }
    end
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
-- station whose Facing is each way. Seen in game: at E = 90 he stood facing
-- the west wall, so a positive Z turn goes clockwise seen from above and
-- east is 270. N and S are not yet seen.
A.DoctorYaw = { S = 0, E = 270, N = 180, W = 90 }

-- Crystals in her core the first time anybody asks.
A.StartCrystals = 50
-- And in the field station's (FIELD_STATION.md 6): enough to run its
-- replicator and its Doctor a long while, not enough to make it a better
-- base than the shuttle.
A.StationStartCrystals = 12

-- What the field station's own lockers hold, where it differs from hers
-- (FIELD_STATION.md 4): a survey archive's shelves hold the county's books
-- and tapes rather than weapons, its security keeps one watch's arms, and its
-- stores are a bunker's.
A.SiteStock = {
    fst = {
        display_shelf = { items = "records", copies = 1 },
        arms_locker   = { items = "station_arms", copies = 1 },
        cargo_crate   = { items = "station_stores", copies = 1 },
    },
}

--- The stock rule for a piece on deck k: the site's own, or hers.
function A.stockRule(piece, k)
    local site = A.siteOf(k)
    local own = site and A.SiteStock[site]
    return (own and own[piece]) or A.Stock[piece]
end

return A
