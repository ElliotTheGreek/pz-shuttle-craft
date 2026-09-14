--[[ Shuttlecraft -- shared configuration.

    Everything the mod hard-codes about the world lives here: where the cabin
    is parked, how it is laid out, which sprites dress it, how much ground the
    hull needs before it will set down, and what is stocked into the lockers.

    Sprite names come from media/newtiledefinitions.tiles.txt and item ids
    from media/scripts/generated/items/, both for build 42.20. A wrong name
    fails *silently* in game -- the square is simply empty -- so every one of
    them is checked by tests/test_assets.py before the game is ever launched.
]]

TREK = TREK or {}

local C = {}
TREK.Config = C

C.Version   = "1.0.0"
C.StateKey  = "TREK_State_v1"
C.ModPrefix = "[TREK]"

-- Bumped whenever the cabin needs rebuilding to pick up changes to the way it
-- is generated. A cabin built at an older revision is quietly brought up to
-- date the next time the player is aboard; the rebuild preserves furniture,
-- stored items and anything dropped on the deck.
C.BuildRev = 3

-- Flip to true for verbose build logging in console.txt.
C.Debug = false

-- Design-time only. Normally a rebuild leaves every container exactly as the
-- player left it -- a ship in play is meant to be lived in, and what gets
-- eaten stays eaten. With this on a rebuild restocks as well, which is what
-- you want while iterating on loot lists and never want in a world somebody
-- is playing. TREK_Rebuild() turns it on for one rebuild instead.
C.DevRestock = false

---------------------------------------------------------------------------
-- Where the cabin lives
---------------------------------------------------------------------------
-- Build 42 cells are 256 squares and vanilla ships cells out to x=77. The
-- Fifth-Wheel RV interior squats on cell 85,40 and the TARDIS mod, if it is
-- also installed, runs from cell 92,40 east across six deck footprints. Cell
-- 96,40 clears all three, and its y stays under 12000 so it also falls
-- outside the unbounded exit-menu test Project RV Interior applies.
C.InteriorCell = { x = 96, y = 40 }

-- Offset of the cabin inside that cell, so nothing touches a cell edge; chunk
-- seams make edge squares awkward to generate reliably.
C.RoomOffset = 16

-- The cabin is one compartment on one storey. There is no deck stack, so
-- none of the TARDIS's sideways-stepping is needed -- but the reason for it
-- still applies and is worth keeping in mind before adding a second level:
-- Project Zomboid draws every z level above the player and only hides what is
-- overhead when it believes you are inside a building, which means RoomDef
-- metadata baked into a map lotheader that runtime squares cannot have. A
-- deck above this one would be drawn straight over it.
C.CabinZ = 4

-- Cabin extent, as inclusive offsets: 0..CabinW across, 0..CabinL fore-aft.
-- oy 0 is the bow. A shuttle is a small ship and this is deliberately a small
-- room -- roomy enough for a galley, a berth, a med station and real cargo,
-- and nothing like a TARDIS deck.
C.CabinW = 5
C.CabinL = 8

-- How far beyond the hull to strip the procedural wilderness the engine grows
-- in unmapped cells. Everything in this ring is removed down to bare nothing,
-- which renders as the black void the Fifth-Wheel RV interior sits in.
C.ClearMargin = 24

-- The transporter pad, amidships and aft of the galley. Arrivals -- beaming
-- up, walking in through the hatch, coming back from a failed landing -- all
-- put the player down here, and the pad and the ring of squares around it are
-- refused by every placement helper so nothing is ever in the way.
C.Landing = { x = 2, y = 6, clearance = 0 }

--- True for the pad square and the ring of squares around it.
function C.isLanding(ox, oy)
    return math.abs(ox - C.Landing.x) <= C.Landing.clearance
       and math.abs(oy - C.Landing.y) <= C.Landing.clearance
end

---------------------------------------------------------------------------
-- Hull shape
---------------------------------------------------------------------------
-- Project Zomboid has no diagonal wall sprites -- a wall only ever sits on
-- the north or west edge of a square -- so a smoothly curved hull is not
-- available at any size. What is available is a stepped chamfer, and at the
-- game's camera angle a bow cut back six squares reads clearly as a nose.
--
-- NoseCut is how far the bow is pinched in, TailCut the same at the stern.
-- Bigger noses are pointier; past about half of CabinW the bow stops being
-- wide enough to stand in.
C.NoseCut = 0
C.TailCut = 0

--- True when an offset is inside the cabin floor plan.
---
--- Walls are derived from this rather than hard-coded, so changing the cuts
--- reshapes the hull and its walls together and nothing else needs touching.
function C.inShape(ox, oy, w, l, nose, tail)
    w = w or C.CabinW
    l = l or C.CabinL
    nose = nose or C.NoseCut
    tail = tail or C.TailCut
    if ox < 0 or oy < 0 or ox > w or oy > l then return false end
    -- cut a right triangle off each corner: a deeper cut forward than aft,
    -- which is what makes it read as a bow rather than a lozenge
    if (ox + oy) < nose then return false end
    if ((w - ox) + oy) < nose then return false end
    if (ox + (l - oy)) < tail then return false end
    if ((w - ox) + (l - oy)) < tail then return false end
    return true
end

---------------------------------------------------------------------------
-- The hull outside
---------------------------------------------------------------------------
-- How much clear ground the shuttle needs before it will set down, in
-- squares, centred on the square being asked about. This is the whole
-- difference between calling this ship down and materialising a police box:
-- a box needs one tile and can appear in a hallway, and a shuttle needs a
-- street or a field.
--
-- Kept in step by hand with HULL_W / HULL_L in tools/gen_shuttle.py, which is
-- how big the model is actually drawn. Nothing in the engine ties the two
-- together -- a world model is drawn from one square and simply overhangs the
-- rest -- so if you change one, change the other.
C.Footprint = { w = 3, h = 5 }

--- Every offset the hull covers, relative to the square it is anchored on.
--- Even-sided footprints are biased to the north-west, which is the corner
--- the isometric camera shows least of.
---
--- Built once and handed back. This is walked inside the landing search,
--- which examines thousands of candidate squares in a single pass, and
--- rebuilding a fifteen-entry table for each of them is pure garbage.
local footprint = nil

function C.footprintOffsets()
    if footprint then return footprint end
    local out = {}
    local hw = math.floor((C.Footprint.w - 1) / 2)
    local hh = math.floor((C.Footprint.h - 1) / 2)
    for dx = -hw, C.Footprint.w - 1 - hw do
        for dy = -hh, C.Footprint.h - 1 - hh do
            table.insert(out, { dx, dy })
        end
    end
    footprint = out
    return out
end

-- Radius, in tiles, of the field that holds the dead back from the hatch.
C.FieldRadius = 10

---------------------------------------------------------------------------
-- The transporter
---------------------------------------------------------------------------
-- Beaming is the shuttle's own trick and is deliberately not gated on the
-- ship being anywhere in particular: when it is not sitting on the ground it
-- is overhead, and the pad reaches you either way.
--
-- The delay is flavour with a purpose -- an instant snap reads as a debug
-- teleport, and a second and a half of dematerialising reads as a transporter
-- and gives the halo note time to be seen. Ticks.
C.BeamDelay = 90

-- How far a beam-down may miss by when the exact square is occupied.
C.BeamScatter = 6

---------------------------------------------------------------------------
-- Flight
---------------------------------------------------------------------------
C.MaxBookmarks        = 40
C.LandingSearchRadius = 24   -- squares to spiral out from a chosen site

-- Hands-on flight. Movement is world squares per tick; the screen-space lift
-- separates the visible shuttle from its projected shadow.
C.FlightSpeed          = 1.50
C.FlightTakeoffTicks   = 75
C.FlightModelLift      = 48
C.FlightShadowW        = 150
C.FlightShadowH        = 42
C.FlightShadowAlpha    = 0.30
C.FlightZoomLevels1x   = "25;50;75;100;125;150;175;200;225;250"
C.FlightZoomLevels2x   = "25;50;75;100;125;150;175;200;225;250"

-- How long to keep trying to set down at a destination before giving up and
-- beaming the player back aboard. Ticks; the first few hundred are spent
-- waiting for the area to stream in at all.
C.LandingTimeout = 420

---------------------------------------------------------------------------
-- Phasers
---------------------------------------------------------------------------
-- Two names for one item: the engine's inventory search compares the bare
-- type, while anything that spawns or places the item wants the full id.
C.PhaserItem = "TrekShuttle.TrekPhaser"
C.PhaserType = "TrekPhaser"

-- A phaser never runs out, never jams and never wears out. TREK_Phaser.lua
-- tops up every one the player is carrying on a slow tick; these are the
-- three things it puts back.
C.PhaserInfiniteAmmo = true
C.PhaserNeverJams    = true
C.PhaserNeverWears   = true

-- How often to top a carried phaser up, in ticks. It only has to beat the
-- rate a player can empty a magazine, so this is deliberately slow.
C.PhaserInterval = 30

-- The locker they are kept in, just off the transporter pad, and how many are
-- in it.
C.PhaserRack  = { x = 4, y = 6 }
C.PhaserCount = 4

---------------------------------------------------------------------------
-- Sprites
---------------------------------------------------------------------------
-- Facing keys name the wall an object stands against, which is also the way
-- it looks into the room. A sprite whose set has fewer than four facings only
-- lists the ones that exist, and the placement helpers fall back to S.
C.Sprites = {
    -- Hull: industry_01 is a light-metal wall set, which is as close to a
    -- ship's bulkhead as build 42 ships. Index 0 is the west face, 1 the
    -- north face, 2 the corner post -- the same layout every wall set uses.
    wallW = "industry_01_0",
    wallN = "industry_01_1",
    wallC = "industry_01_2",

    deckFloor = "floors_interior_tilesandwood_01_0",  -- solid deck
    padFloor  = "floors_interior_tilesandwood_01_1",  -- solid transporter tile

    lamp   = { S = "lighting_indoor_01_32", E = "lighting_indoor_01_8",
               W = "lighting_indoor_01_40", N = "lighting_indoor_01_48" },

    sink   = { N = "fixtures_sinks_01_0", E = "fixtures_sinks_01_1",
               S = "fixtures_sinks_01_2", W = "fixtures_sinks_01_3" },
    toilet = { S = "fixtures_bathroom_01_0", E = "fixtures_bathroom_01_1",
               W = "fixtures_bathroom_01_2", N = "fixtures_bathroom_01_3" },
    shower = { N = "fixtures_bathroom_01_22", W = "fixtures_bathroom_01_23" },

    -- Steel counters rather than the wooden kitchen sets: this is a galley in
    -- a metal hull, not somebody's kitchen.
    counter = { N = "fixtures_counters_01_33", E = "fixtures_counters_01_35",
                S = "fixtures_counters_01_37", W = "fixtures_counters_01_39" },
    fridge  = { S = "appliances_refrigeration_01_0", E = "appliances_refrigeration_01_1",
                N = "appliances_refrigeration_01_2", W = "appliances_refrigeration_01_3" },
    oven    = { E = "appliances_cooking_01_0", S = "appliances_cooking_01_1",
                W = "appliances_cooking_01_2", N = "appliances_cooking_01_3" },
    microwave = { S = "appliances_cooking_01_25", E = "appliances_cooking_01_24",
                  W = "appliances_cooking_01_26", N = "appliances_cooking_01_27" },

    metalShelf = { S = "furniture_shelving_01_28", E = "furniture_shelving_01_29",
                   W = "furniture_shelving_01_30", N = "furniture_shelving_01_31" },
    locker     = { S = "furniture_storage_02_8", E = "furniture_storage_02_9",
                   N = "furniture_storage_02_10", W = "furniture_storage_02_11" },
    crate      = "location_military_generic_01_0",
    chair      = { E = "furniture_seating_indoor_01_8", S = "furniture_seating_indoor_01_9",
                   W = "furniture_seating_indoor_01_10", N = "furniture_seating_indoor_01_11" },

    -- The cockpit. security_01 "Terminal" is a floor-standing console and
    -- security_01_4/5 a bank of wall-mounted screens, which between them read
    -- as a helm without a single custom tile.
    terminal = { S = "security_01_0", E = "security_01_1",
                 N = "security_01_2", W = "security_01_3" },
    monitors = { S = "security_01_4", E = "security_01_5" },
    computer = { S = "appliances_com_01_72", E = "appliances_com_01_73",
                 N = "appliances_com_01_74", W = "appliances_com_01_75" },

    -- Sick bay. The wide medical cabinet holds thirty, which is what makes a
    -- "large container of medical supplies" actually large.
    medCabinet = { E = "location_community_medical_01_152",
                   S = "location_community_medical_01_154",
                   N = "location_community_medical_01_238",
                   W = "location_community_medical_01_246" },
    medDrawers = { E = "location_community_medical_01_36",
                   S = "location_community_medical_01_37",
                   W = "location_community_medical_01_38",
                   N = "location_community_medical_01_39" },
}

---------------------------------------------------------------------------
-- Multi-tile furniture
---------------------------------------------------------------------------
-- A bed covers more than one square and which half goes where is not
-- guessable: it comes from the tileset's SpriteGridPos property, given here
-- as {sprite, dx, dy}. Getting it backwards lays the foot of the bed where
-- its head belongs, which is invisible in the code and obvious in game.
-- tests/test_layout.py checks every offset here against the game data.
C.Pieces = {
    bunkS   = { { "furniture_bedding_01_9", 0, 0 }, { "furniture_bedding_01_8", 0, 1 } },
    biobedS = { { "location_community_medical_01_17", 0, 0 },
                { "location_community_medical_01_16", 0, 1 } },
}

---------------------------------------------------------------------------
-- Items placed in the cabin
---------------------------------------------------------------------------
-- The hull outside and the helm console inside are world models, defined in
-- media/scripts/trekshuttle.txt.
C.ExteriorItem = "TrekShuttle.TrekShuttleHull"
C.HelmItem     = "TrekShuttle.TrekHelmConsole"

---------------------------------------------------------------------------
-- Stores
---------------------------------------------------------------------------
C.Loot = {}

-- Sick bay. Deliberately long: U.stock walks a list with a rolling cursor, so
-- a longer list spreads further across the cabinets rather than repeating.
C.Loot.medical = {
    "Base.Bandage", "Base.BandageBox", "Base.Antibiotics", "Base.Disinfectant",
    "Base.AlcoholWipes", "Base.AlcoholBandage", "Base.FirstAidKit",
    "Base.Pills", "Base.PillsAntiDep", "Base.PillsBeta", "Base.PillsVitamins",
    "Base.PillsSleepingTablets", "Base.WaterPurificationTablets",
    "Base.Splint", "Base.SutureNeedle", "Base.SutureNeedleHolder",
    "Base.Tweezers", "Base.Scalpel", "Base.Bleach",
    "Base.CottonBalls", "Base.CottonBallsBox", "Base.AlcoholedCottonBalls",
}

-- Ship's stores. Long-life first: this is what a shuttle is provisioned with,
-- not what somebody left in a fridge.
C.Loot.food = {
    "Base.TinnedBeans", "Base.TinnedSoup", "Base.CannedCorn", "Base.CannedPeas",
    "Base.CannedCarrots", "Base.CannedPotato", "Base.CannedChili",
    "Base.CannedBolognese", "Base.CannedMushroomSoup", "Base.CannedTomato",
    "Base.CannedSardines", "Base.CannedFruitCocktail", "Base.CannedPeaches",
    "Base.Rice", "Base.Pasta", "Base.Flour2", "Base.Sugar", "Base.Salt",
    "Base.Coffee2", "Base.Crisps", "Base.GranolaBar", "Base.BeefJerky",
    "Base.WaterBottle", "Base.WaterRationCan",
}

C.Loot.fresh = {
    "Base.Bread", "Base.Cheese", "Base.Butter", "Base.Milk", "Base.Egg",
    "Base.Potato", "Base.Carrots", "Base.Onion", "Base.Tomato", "Base.Apple",
    "Base.Orange", "Base.Steak", "Base.Chicken",
}

C.Loot.cookware = {
    "Base.Pot", "Base.Pan", "Base.Saucepan", "Base.Bowl", "Base.Plate",
    "Base.MugWhite", "Base.KitchenKnife", "Base.BreadKnife", "Base.ButterKnife",
    "Base.CheeseGrater", "Base.RollingPin", "Base.BakingTray",
}

-- Engineering stores: a shuttle carries a tool roll, not a workshop.
C.Loot.tools = {
    "Base.Screwdriver", "Base.Wrench", "Base.PipeWrench", "Base.Hammer",
    "Base.DuctTape", "Base.Rope", "Base.Torch", "Base.Battery",
    "Base.ElectronicsScrap", "Base.Extinguisher", "Base.Crowbar",
    "Base.Saw", "Base.Screws", "Base.Nails", "Base.Wire", "Base.SheetMetal",
}

C.Loot.linen = { "Base.Sheet", "Base.Pillow", "Base.Pillow_Crafted" }

return C
