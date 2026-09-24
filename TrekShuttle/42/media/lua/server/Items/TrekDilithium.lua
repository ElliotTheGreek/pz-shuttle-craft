--[[ Shuttlecraft -- where dilithium is found.

    The ship's power is a crystal it cannot make, so the whole system rests on
    these being out there: rare, findable, and in places a player would think
    to look. Nothing else in this mod puts anything into the world's loot.

    **Not in a kitchen drawer.** A crystal turns up where a 1993 Kentucky
    town would keep something small, valuable and electrical: a jeweller's
    gem case, an electronics store, a mechanic's electrical shelf, a metal
    shop, a tool crate, a pawn shop. That list is doing the same job the
    tricorder does -- telling a player where to go -- so it is worth keeping
    it somewhere a person would guess.

    **The weights are vanilla's own scale.** In `JewelryGems` a diamond is 1
    and a bag of gems is 0.1. They were a quarter of what they are now --
    "rarer than a diamond" -- when a crystal only fed the replicator. Since
    the energy system (ENERGY.md) everything aboard runs on one, and the
    first cold-start play went a long way without finding another, so they
    were raised fourfold (2026-09-24): a jeweller's case is now the likeliest
    place in town, and a tool crate a fair bet rather than a long shot.

    This file lives in server/Items/ rather than server/TREK/ because that is
    where the engine looks for distribution code, and it deliberately does not
    `require` any of the mod's own files: it runs at world generation, and a
    load-order dependency here would be a silent empty world. The id is a
    literal, and tests/test_assets.py checks every `TrekShuttle.*` literal in
    every Lua file against the items the scripts actually declare.
]]

require "Items/ProceduralDistributions"

-- Kept in step by hand with C.DilithiumItem in TREK_Config.lua.
local CRYSTAL = "TrekShuttle.TrekDilithium"

local PLACES = {
    -- A gem among gems: the one place a player will think of first.
    { "JewelryGems",           2.4 },
    { "PawnShopCases",         2 },
    -- Small, valuable, electrical.
    { "ElectronicStoreMisc",   1.6 },
    { "StoreShelfElectronics", 1.2 },
    { "ElectronicStoreLights", 1 },
    { "MechanicShelfElectric", 1.2 },
    -- Industrial: where you would keep an odd lump of crystal.
    { "MetalShopTools",        1.2 },
    { "CrateMetalwork",        1 },
    { "CrateTools",            1 },
    { "CrateToolsOld",         1 },
    { "GarageTools",           0.8 },
    { "MechanicShelfMisc",     0.8 },
}

-- Once per world, however many times the event fires. A second pass would
-- double every weight, and nothing anywhere would say so.
local seeded = false

local function seed()
    if seeded then return end
    seeded = true

    local added, missing = 0, {}
    for _, place in ipairs(PLACES) do
        local name, weight = place[1], place[2]
        local table_ = ProceduralDistributions.list[name]
        if table_ and table_.items then
            table.insert(table_.items, CRYSTAL)
            table.insert(table_.items, weight)
            added = added + 1
        else
            table.insert(missing, name)
        end
    end

    -- Read the result back, as everything in this mod does: a loot table that
    -- was renamed in a patch would otherwise take the crystal out of the
    -- world in perfect silence, and the first sign would be a player who
    -- cannot power their replicator and has no idea why.
    print("[TREK] dilithium: seeded into " .. added .. " of " .. #PLACES
          .. " loot tables")
    if #missing > 0 then
        print("[TREK] WARN dilithium: no loot table named "
              .. table.concat(missing, ", ") .. " -- crystals will be rarer "
              .. "than intended")
    end
end

Events.OnPreDistributionMerge.Add(seed)
