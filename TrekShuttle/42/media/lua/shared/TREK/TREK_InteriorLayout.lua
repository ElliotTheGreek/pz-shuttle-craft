-- The cabin interior, authored in BuildingEd.
--
-- Derived from design/buildinged/TrekShuttle_Interior.tbx. Geometry (x, y,
-- sprite) comes straight from the TBX and should be regenerated rather than
-- typed: `python tools/import_tbx_layout.py --lua` rewrites this file and
-- keeps the loot assignments below. What is stocked is a design decision the
-- map editor knows nothing about, so it lives here.
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
-- The refit, and the two decisions behind it
---------------------------------------------------------------------------
-- Four across by six fore-and-aft, down from six by nine. The cabin used to
-- be fifty-four squares against a 3x5 hull, which is not a shuttle, it is a
-- warehouse with a transporter in it.
--
-- 1. *Layering is what makes twenty-four squares enough.* The sink and the
--    microwave ride on counters, the monitor bank and the EMH panel are wall
--    objects that cost no floor at all, and the helm is a world item lying on
--    an open square. Eleven squares carry a fitting; eleven are deck.
--
-- 2. *Five of the eight containers are stocked with nothing.* The fridge, the
--    oven, both counters and the replicator's berth are the player's shelves.
--    A player fills a shuttle with vanilla loot within a week of flying it,
--    and three Starfleet lockers holding tins of beans is just the vanilla
--    game in a cupboard. So the lockers carry the mod's own items and nothing
--    else, and everything else starts empty on purpose.
--
-- The one thing to know before moving anything: the crew seat at 1,2 is a
-- theatre chair, and a theatre chair carries `collideN` and `HoppableN` only
-- -- it blocks its north edge and nothing else. That is what lets it stand in
-- the middle of the deck without cutting the cabin in half, and it is why you
-- sit down from the south. Swap it for one of the two-tile bench seats (plain
-- `solidtrans`) and it becomes a wall.

local L = {}

L.width = 4
L.height = 6
L.floor = "location_hospitality_sunstarmotel_01_56"
L.wallW = "location_shop_fossoil_01_6"
L.wallN = "location_shop_fossoil_01_5"

-- BuildingEd allows several layers on one square (for example a counter,
-- appliance and wall console). Runtime placement must preserve that layering.
L.tiles = {
    ---------------------------------------------------------------------
    -- The bow: the viewscreen wall, a working television, two seats
    ---------------------------------------------------------------------
    -- security_01_4 is a wall-mounted monitor bank: no `solid`, no
    -- `solidtrans`, so all four of these cost no floor square. The whole bow
    -- bulkhead is screens, which is the one piece of the old cabin that was
    -- already right.
    { x = 0, y = 0, sprite = "security_01_4", tag = "console" },
    { x = 1, y = 0, sprite = "security_01_4", tag = "console" },
    { x = 2, y = 0, sprite = "security_01_4", tag = "console" },
    { x = 3, y = 0, sprite = "security_01_4", tag = "console" },

    -- A television that is actually a television. `device` is the field that
    -- makes TREK_Build construct an IsoTelevision rather than a plain
    -- IsoObject wearing a TV's picture -- which is what the old viewscreen
    -- was, and why nobody has ever been able to turn it on.
    --
    -- It is also the VCR: appliances_television_01_0..3 is Base.TvWideScreen,
    -- and that item declares `AcceptMediaType = 1`, the tape type. Build 42
    -- has no separate VCR object because a television already is one. The
    -- tapes are Base.VHS_Home and Base.VHS_Retail; the ship is not issued
    -- with any, which is a thing to go and find.
    { x = 1, y = 0, sprite = "furniture_tables_low_01_3", tag = "tvConsole" },
    { x = 1, y = 0, sprite = "appliances_television_01_1", tag = "television",
      device = "Base.TvWideScreen" },

    -- One chair, two squares back and dead in front of the television, rather
    -- than the pair that used to sit in the bow row beside it. The old pair
    -- were level with the screen and looking at the bulkhead; this one is
    -- looking at the thing it is for. It faces N (`location_entertainment_
    -- theatre_01_3`) and carries collideN only, so the corridor past it at
    -- x = 2 is untouched and you sit down from the south.
    { x = 1, y = 2, sprite = "location_entertainment_theatre_01_3", tag = "chair" },

    ---------------------------------------------------------------------
    -- Port: the galley. Every one of these is the player's storage.
    ---------------------------------------------------------------------
    { x = 0, y = 1, sprite = "appliances_refrigeration_01_1", tag = "fridge",
      container = true },
    -- The single-tile grey oven, not the two-tile range the old galley used:
    -- that one was a quarter of this cabin on its own.
    { x = 0, y = 2, sprite = "appliances_cooking_01_4", tag = "oven",
      container = true },
    { x = 0, y = 3, sprite = "fixtures_counters_01_35", tag = "counter",
      container = true },
    { x = 0, y = 3, sprite = "fixtures_sinks_01_1", tag = "sink" },
    { x = 0, y = 4, sprite = "fixtures_counters_01_35", tag = "counter",
      container = true },
    { x = 0, y = 4, sprite = "appliances_cooking_01_24", tag = "microwave",
      container = true },
    -- **0,5 carries no fitting: it is the replicator's, and the replicator is
    -- a whole machine rather than something bolted to a counter.**
    --
    -- It was a steel counter for two revisions, with the model hanging over
    -- it and replicated items going into the counter's own container. That
    -- was half a machine leaning on a piece of furniture, and it is gone:
    -- C.ReplicatorSpot names the square, TREK_Build stands the model on it,
    -- and what it makes goes into your hands. A save that still has the
    -- counter is cleaned up by B.refitCabin, contents and all.

    ---------------------------------------------------------------------
    -- Starboard forward: the three Starfleet lockers
    ---------------------------------------------------------------------
    -- Quantities are set by `cap` rather than by weight, and `fill = 1.0`
    -- puts the weight target out of the way so that the cap is what decides.
    -- Each cap is a multiple of its list length, so every item goes in the
    -- same number of times whatever the rolling cursor is doing: three
    -- containers cannot spread a list the way nineteen did, and a locker that
    -- happens to miss the ushaan-tor looks exactly like one that does not.
    --
    -- `special` is the belt to that braces: U.stockEach puts one of each in
    -- and then reads the container back, so a guarantee that did not land is
    -- reported instead of assumed.
    { x = 3, y = 0, sprite = "furniture_storage_02_11", tag = "armoury",
      container = true, special = "phasers", loot = "weapons",
      fill = 1.0, cap = 8 },        -- 4 phasers + 2 of each of the 4 blades
    { x = 3, y = 1, sprite = "furniture_storage_02_11", tag = "provisions",
      container = true, loot = "food",
      fill = 1.0, cap = 27 },       -- 3 of each of the 5 dishes and 4 drinks
    { x = 3, y = 2, sprite = "furniture_storage_02_11", tag = "medical",
      container = true, special = "medkit", loot = "medical",
      fill = 1.0, cap = 8 },        -- 3 of each instrument

    ---------------------------------------------------------------------
    -- Starboard aft: the sick bay, and the EMH's station
    ---------------------------------------------------------------------
    -- industry_01_15 is from the hull's own wall set (industry_01_0/1/2 are
    -- the bulkheads), carries neither `solid` nor `solidtrans`, and exists in
    -- all four facings. So the EMH's panel is on the wall at 3,3 and 3,3 is
    -- still deck. The Doctor stands at 2,4, at the head of the bed.
    --
    -- Deliberately not a light switch: every lighting_indoor_01 switch
    -- carries the `lightswitch` tile property, which is what the cell loader
    -- reads when it decides to build an IsoLightSwitch instead of an
    -- IsoObject. A button that turns into a real light switch on the next
    -- world load is a bug that only shows up in somebody else's save.
    { x = 3, y = 3, sprite = "industry_01_15", tag = "emhPanel" },

    -- C.Pieces.biobedS, and the ship's only bed now that the berth is gone:
    -- both halves carry BedType = goodBed. A shuttle with a sick bay *and* a
    -- bunk in twenty-four squares is a shuttle with nowhere to stand.
    { x = 3, y = 4, sprite = "location_community_medical_01_17", tag = "biobed" },
    { x = 3, y = 5, sprite = "location_community_medical_01_16", tag = "biobed" },
}

return L
