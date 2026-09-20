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
-- `loot` names a list in C.Loot and `special` marks the phaser locker.
-- Amounts are deliberately absent: containers fill to C.FillFraction of their
-- own capacity, so a microwave and a locker both end up looking stocked.

local L = {}

L.width = 6
L.height = 9
L.floor = "location_hospitality_sunstarmotel_01_56"
L.wallW = "location_shop_fossoil_01_6"
L.wallN = "location_shop_fossoil_01_5"

-- BuildingEd allows several layers on one square (for example a counter,
-- appliance and wall console). Runtime placement must preserve that layering.
L.tiles = {
    { x = 2, y = 3, sprite = "floors_rugs_01_6", tag = "rug" },
    { x = 2, y = 4, sprite = "floors_rugs_01_2", tag = "rug" },
    { x = 2, y = 5, sprite = "floors_rugs_01_0", tag = "rug" },
    { x = 3, y = 3, sprite = "floors_rugs_01_7", tag = "rug" },
    { x = 3, y = 4, sprite = "floors_rugs_01_3", tag = "rug" },
    { x = 3, y = 5, sprite = "floors_rugs_01_1", tag = "rug" },

    { x = 5, y = 0, sprite = "security_01_4", tag = "console" },
    { x = 4, y = 0, sprite = "security_01_4", tag = "console" },
    { x = 3, y = 0, sprite = "security_01_4", tag = "console" },
    { x = 2, y = 0, sprite = "security_01_4", tag = "console" },
    { x = 1, y = 0, sprite = "security_01_4", tag = "console" },
    { x = 0, y = 0, sprite = "security_01_4", tag = "console" },
    { x = 2, y = 0, sprite = "furniture_tables_low_01_3", tag = "helmDesk" },
    { x = 2, y = 0, sprite = "appliances_television_01_1", tag = "viewscreen" },

    -- Galley, port side.
    { x = 0, y = 1, sprite = "appliances_refrigeration_01_29", tag = "freshFood", container = true, loot = "fresh" },
    { x = 0, y = 2, sprite = "appliances_refrigeration_01_29", tag = "freshFood", container = true, loot = "fresh" },
    { x = 0, y = 3, sprite = "appliances_cooking_01_12", tag = "cookware", container = true, loot = "cookware" },

    -- Counters along the forward bulkhead.
    { x = 0, y = 0, sprite = "fixtures_counters_01_36", tag = "provisions", container = true, loot = "food" },
    { x = 1, y = 0, sprite = "fixtures_counters_01_37", tag = "cookware", container = true, loot = "cookware" },
    { x = 3, y = 0, sprite = "fixtures_counters_01_37", tag = "provisions", container = true, loot = "food" },
    { x = 4, y = 0, sprite = "fixtures_counters_01_37", tag = "readyKit", container = true, loot = "survival" },
    -- The galley's drinks cabinet: raktajino and Earl Grey to hand, the ale
    -- and the bloodwine behind them.
    --
    -- It is **not** the oven, which is where the drinks spent their first trip
    -- into the game. `appliances_cooking_01_40` is the lower half of a two-tile
    -- oven -- CustomName "Oven", IsoType IsoStove, SpriteGridPos 0,1 to its
    -- twin's 0,0 -- and calling it a cabinet in a comment did not make it one.
    -- The sprite belongs to the .tbx; `tag` and `loot` are ours, and ours were
    -- on the wrong square.
    --
    -- This counter rather than the one at 1,0 because the sink shares that
    -- square, and the deck plan draws one glyph per square: the drinks would
    -- have been hidden behind the `w`, undoing the glyph that exists so the
    -- cabinet can be found by looking at the plan.
    { x = 5, y = 0, sprite = "fixtures_counters_01_37", tag = "drinks", container = true, loot = "drinks" },
    { x = 0, y = 0, sprite = "appliances_cooking_01_24", tag = "snacks", container = true, loot = "food" },
    -- Both halves of the one two-tile oven, and both hold cookware.
    { x = 0, y = 4, sprite = "appliances_cooking_01_41", tag = "cookware", container = true, loot = "cookware" },
    { x = 0, y = 5, sprite = "appliances_cooking_01_40", tag = "cookware", container = true, loot = "cookware" },

    { x = 3, y = 0, sprite = "appliances_com_01_0", tag = "computer" },
    { x = 1, y = 0, sprite = "fixtures_sinks_01_17", tag = "sink" },
    { x = 2, y = 2, sprite = "location_entertainment_theatre_01_3", tag = "chair" },
    { x = 3, y = 2, sprite = "location_entertainment_theatre_01_3", tag = "chair" },

    -- The starboard lockers, bow to stern. Sick bay first, then engineering,
    -- then stores, then the armoury around the phaser locker.
    -- The forward sick-bay locker carries one of each of the ship's own
    -- medical instruments outright, the way the locker at 5,6 carries the
    -- phasers. Leaving them to the loot list alone is not enough: the fill
    -- walks C.Loot.medical from a rolling cursor, so three entries in a list
    -- of thirty-one can miss both lockers entirely and the ship sails with
    -- no tricorder aboard.
    { x = 5, y = 1, sprite = "furniture_storage_02_11", tag = "medical", container = true, special = "medkit", loot = "medical" },
    { x = 5, y = 2, sprite = "furniture_storage_02_11", tag = "medical", container = true, loot = "medical" },
    { x = 5, y = 3, sprite = "furniture_storage_02_11", tag = "engineering", container = true, loot = "tools" },
    { x = 5, y = 4, sprite = "furniture_storage_02_11", tag = "engineering", container = true, loot = "tools" },
    { x = 5, y = 5, sprite = "furniture_storage_02_11", tag = "provisions", container = true, loot = "food" },
    { x = 5, y = 6, sprite = "furniture_storage_02_11", tag = "phasers", container = true, special = "phasers", loot = "weapons" },
    { x = 5, y = 7, sprite = "furniture_storage_02_11", tag = "armoury", container = true, loot = "weapons" },
    { x = 5, y = 8, sprite = "furniture_storage_02_11", tag = "survival", container = true, loot = "survival" },

    { x = 0, y = 8, sprite = "furniture_bedding_01_86", tag = "bunk" },
    { x = 1, y = 8, sprite = "furniture_bedding_01_87", tag = "bunk" },
}

return L
