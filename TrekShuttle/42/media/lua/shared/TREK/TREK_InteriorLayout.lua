-- The cabin interior, authored in BuildingEd.
--
-- Derived from design/buildinged/TrekShuttle_Interior.tbx. Geometry (x, y,
-- sprite) comes straight from the TBX; tools/gen_shuttle_interior.py writes
-- the TBX and draws the plan, and tests/test_layout.py fails if this file and
-- the TBX disagree. What is stocked is a design decision the map editor knows
-- nothing about, so it lives here.
--
-- `container = true` is the load-bearing field. A sprite being a container in
-- the tileset is not enough: an object built at runtime gets no ItemContainer
-- unless one is made for it, so an entry without this flag is placed as
-- scenery and can never be opened, however many loot lists point at it.
-- tests/test_layout.py cross-checks the flag against the tile catalogue.
--
-- `loot` names a list in C.Loot, `special` names a guaranteed-stock rule in
-- TREK_Build.lua, and `cap` bounds the item count. A `container = true` entry
-- with none of the three is deliberately empty -- see below.
--
---------------------------------------------------------------------------
-- The Starfleet refit (INTERIOR_REFIT.md 9)
---------------------------------------------------------------------------
-- Four across by six fore-and-aft, as since the 6x9 cabin was cut down, and
-- Starfleet issue throughout: the Adirondack's own bulkheads, carpet and
-- furniture (trek_adirondack_01 and _02). **Two things aboard are not
-- Starfleet's, and both are Lt. Shepard's: her 1993 television and her
-- tapes** (LORE.md 1a). Everything the cabin used to borrow from a motel, a
-- gas station and a hospital has gone.
--
-- Three rules decided where everything stands, and each is checked:
--
-- 1. *The camera sees two walls.* The game draws the cabin from the south-
--    east, so only the bow (north) and port (west) bulkheads show their
--    faces; a locker against the starboard wall shows the room its back,
--    which is what the old three green lockers looked like. Everything tall
--    stands against the two walls you can see. Starboard has the machines
--    and the biobed, which read from any side.
-- 2. *Every fitting is worked from open deck.* A wall piece's front square is
--    open -- the whole x = 1 passage for the port wall, y = 1 for the bow --
--    and nothing free-standing sits on one. tests/test_layout.py walks it.
-- 3. *Layering costs no floor.* The tapes and the LCARS panels are wall
--    objects: 1,0 is still deck under the rack, which is how the bunk beside
--    it is reached.
--
-- And the refit's other decision, older than it: *five containers are the
-- player's.* A player fills a shuttle with vanilla loot within a week, so
-- the Starfleet lockers carry the mod's own items and the stasis unit, the
-- range and the TV cabinet start empty on purpose.

local L = {}

L.width = 4
L.height = 6
L.floor = "trek_adirondack_01_24"      -- carpet, as the runabout's aft cabin
L.wallW = "trek_adirondack_01_0"       -- the Adirondack's bulkhead, light strip and all
L.wallN = "trek_adirondack_01_1"

-- What the cabin was built of before the refit, for the migration that takes
-- it out (TREK_Build, B.starfleetRefit). A floor or a wall is only ever
-- swapped if it is one of these: anything else on that square was laid by a
-- player (BUILDING.md).
L.legacy = {
    floors = { "location_hospitality_sunstarmotel_01_56",
               "floors_interior_tilesandwood_01_0", "floors_interior_tilesandwood_01_1" },
    walls = { "location_shop_fossoil_01_6", "location_shop_fossoil_01_5",
              "industry_01_0", "industry_01_1" },
}

-- BuildingEd allows several layers on one square (a television on its
-- cabinet, a panel over a counter). Runtime placement preserves that.
L.tiles = {
    ---------------------------------------------------------------------
    -- The bow bulkhead
    ---------------------------------------------------------------------
    -- A bunk in the port corner, for the crew's second pair of hands: the
    -- runabout's aft cabin sleeps its crew in the bulkheads, and the biobed
    -- was the only bed aboard. One square, two tiers, backed onto the port
    -- wall and worked from 1,0, which is deck under the tape rack.
    { x = 0, y = 0, sprite = "trek_adirondack_02_12", tag = "bunk" },

    -- **Lt. Shepard's tapes**, on a Starfleet rack on the bow bulkhead beside
    -- her television (LORE.md 3). A wall object: no `solid`, no
    -- `solidtrans` -- the properties of vanilla's metal wall shelf, the one it
    -- replaces (tools/gen_adirondack_pack.py) -- so 1,0 stays deck.
    { x = 1, y = 0, sprite = "trek_adirondack_02_214", tag = "tapes",
      container = true, special = "tapes" },

    -- **Her television**, the one 1993 object aboard, on a Starfleet cabinet
    -- two squares ahead of the chair. `device` makes TREK_Build construct an
    -- IsoTelevision rather than a plain IsoObject wearing a TV's picture. It
    -- is also the VCR: Base.TvWideScreen declares `AcceptMediaType = 1`, the
    -- tape type. The cabinet's `Surface` is its own top, so the set is drawn
    -- standing on it, and it holds things -- it is the player's.
    { x = 2, y = 0, sprite = "trek_adirondack_02_216", tag = "tvConsole",
      container = true },
    { x = 2, y = 0, sprite = "appliances_television_01_1", tag = "television",
      device = "Base.TvWideScreen" },
    { x = 2, y = 0, sprite = "trek_adirondack_02_177", tag = "console" },

    -- The armoury, in the starboard corner and facing aft, so its front is
    -- the room's rather than the bulkhead's. C.PhaserRack follows it.
    -- 4 phasers (2.4) + 2 of each of the 4 blades (15.0) + 6 uniforms (8.4)
    -- + 2 PADDs (0.6) + the field pack (1.0) + 2 shoulder lamps (0.6)
    -- + 3 sentries (4.5) is 32.5 of the locker's 40 units, so nothing is
    -- dropped for room. `special` is a list: four phasers and one uniform of
    -- each division are two different counts.
    { x = 3, y = 0, sprite = "trek_adirondack_02_208", tag = "armoury",
      container = true, special = { "phasers", "uniforms", "padds", "packs", "lamps", "sentries" },
      loot = "weapons",
      fill = 1.0, cap = 8 },        -- 4 phasers + 2 of each of the 4 blades

    ---------------------------------------------------------------------
    -- The port bulkhead: the galley and the sick bay's cabinet
    ---------------------------------------------------------------------
    -- The stasis unit is the fridge: its container is `fridge`, which is the
    -- whole of what ItemContainer.isFridge asks, and the power bus powers it.
    { x = 0, y = 1, sprite = "trek_adirondack_02_80", tag = "fridge",
      container = true },
    -- The galley range is a real IsoStove (C.StoveTags), as the Adirondack's.
    { x = 0, y = 2, sprite = "trek_adirondack_02_191", tag = "oven",
      container = true },
    { x = 0, y = 2, sprite = "trek_adirondack_01_40", tag = "console" },
    -- The galley sink: running water, and **the ship's rations in the
    -- cupboard under it**. Quantities are set by `cap`, and `fill = 1.0`
    -- puts the weight target out of the way: 27 covers the 18-item food list
    -- once and nine of it twice.
    { x = 0, y = 3, sprite = "trek_adirondack_02_76", tag = "sink",
      container = true, loot = "food",
      fill = 1.0, cap = 27 },
    { x = 0, y = 3, sprite = "trek_adirondack_02_172", tag = "sconce" },
    -- The sick bay's cabinet. `special` + U.stockEach puts one of each
    -- instrument in and reads it back.
    { x = 0, y = 4, sprite = "trek_adirondack_02_120", tag = "medical",
      container = true, special = "medkit", loot = "medical",
      fill = 1.0, cap = 8 },        -- 3 of each instrument
    -- **0,5 carries no fitting: it is the replicator's**, a world model
    -- standing on its own square (C.ReplicatorSpot).

    ---------------------------------------------------------------------
    -- Amidships and starboard
    ---------------------------------------------------------------------
    -- One chair, two squares back and dead in front of the television,
    -- looking at it. It is the chair in TREK_LogSix. A Starfleet bridge
    -- chair backed to the south, so it faces the bow.
    { x = 2, y = 2, sprite = "trek_adirondack_02_89", tag = "chair" },

    -- **2,3 is the warp core's** (C.DilithiumSpot), 3,3 is the Doctor's
    -- square under his station on the starboard bulkhead (C.EmhSpot), and
    -- both are world models placed by TREK_Build.

    -- The biobed with its scanner arch, the ship's second bed: both halves
    -- carry BedType = goodBed.
    { x = 3, y = 4, sprite = "trek_adirondack_02_114", tag = "biobed" },
    { x = 3, y = 5, sprite = "trek_adirondack_02_115", tag = "biobed" },
}

return L
