--[[ Shuttlecraft -- the hydroponics crops, registered (FARMING.md 2).

    The seven crops as vanilla crop types in `farming_vegetableconf.props`,
    with the sprite tables tools/gen_adirondack_crops.py renders. Shared,
    because vanilla's sow menu reads the crop table on the client as well as
    the server; everything else about the bay is server/TREK/TREK_Farm.lua.
]]

require "Farming/farming_vegetableconf"
require "TREK/TREK_FarmSprites"

TREK = TREK or {}
local F = TREK.Farm or {}
TREK.Farm = F

---------------------------------------------------------------------------
-- The crops (FARMING.md 2)
---------------------------------------------------------------------------
-- Hours per growth stage, and what comes off at harvest. Faster than
-- vanilla's fields: a hydroponics bay under grow lights.
F.Crops = {
    TrekTeaBush = { seed = "TrekShuttle.TrekTeaSeed", veg = "TrekShuttle.TrekTeaLeaves",
                    icon = "Item_TREK_TeaLeaves", hours = 96, min = 4, max = 7, growBack = 4 },
    TrekBergamot = { seed = "TrekShuttle.TrekBergamotSeed", veg = "TrekShuttle.TrekBergamot",
                     icon = "Item_TREK_Bergamot", hours = 120, min = 2, max = 4, growBack = 4 },
    TrekKlingonCoffee = { seed = "TrekShuttle.TrekKlingonCoffeeSeed",
                          veg = "TrekShuttle.TrekKlingonCoffeeCherries",
                          icon = "Item_TREK_CoffeeCherries", hours = 108, min = 4, max = 7, growBack = 4 },
    TrekPlomeek = { seed = "TrekShuttle.TrekPlomeekSeed", veg = "TrekShuttle.TrekPlomeek",
                    icon = "Item_TREK_Plomeek", hours = 72, min = 2, max = 4 },
    TrekLeolaRoot = { seed = "TrekShuttle.TrekLeolaSeed", veg = "TrekShuttle.TrekLeolaRoot",
                      icon = "Item_TREK_LeolaRoot", hours = 84, min = 2, max = 4 },
    TrekAndorianTuber = { seed = "TrekShuttle.TrekAndorianTuberSeed",
                          veg = "TrekShuttle.TrekAndorianTuberRaw",
                          icon = "Item_TREK_AndorianTuberRaw", hours = 84, min = 2, max = 3 },
    TrekHasperatPepper = { seed = "TrekShuttle.TrekHasperatSeed", veg = "TrekShuttle.TrekHasperatPeppers",
                           icon = "Item_TREK_HasperatPeppers", hours = 72, min = 3, max = 6 },
}

local ALL_MONTHS = { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 }

function F.register()
    local conf = farming_vegetableconf
    if not conf or not conf.props then return 0 end
    local n = 0
    for name, c in pairs(F.Crops) do
        local sprites = TREK_FarmSprites and TREK_FarmSprites[name]
        if sprites then
            conf.props[name] = {
                icon = c.icon,
                texture = sprites.sprite[6],
                waterLvl = 60,
                waterNeeded = 70,
                timeToGrow = c.hours,
                vegetableName = c.veg,
                seedName = c.seed,
                seedTypes = { c.seed },
                minVeg = c.min, maxVeg = c.max,
                minVegAutorized = c.max, maxVegAutorized = c.max + 3,
                harvestLevel = 5,
                mature = 5,
                fullGrown = 6,
                growBack = c.growBack,
                -- A ship has no seasons, and the world's temperature is
                -- global: without these a Kentucky winter reaches the bay.
                sowMonth = ALL_MONTHS,
                badMonth = {},
                bestMonth = {},
                riskMonth = {},
                coldHardy = true,
                isHouseplant = true,
                aphidsProof = true, fliesProof = true, slugsProof = true,
            }
            -- All five tables: MOFarming indexes every one, and throws on a
            -- crop that is missing any.
            conf.sprite[name] = sprites.sprite
            conf.unhealthySprite[name] = sprites.unhealthy
            conf.dyingSprite[name] = sprites.dying
            conf.deadSprite[name] = sprites.dead
            conf.trampledSprite[name] = sprites.trampled
            n = n + 1
        end
    end
    return n
end

F.registered = F.register()

--- True for one of ours, by the crop a plant was sown as.
function F.isOurCrop(typeOfSeed)
    return type(typeOfSeed) == "string" and F.Crops[typeOfSeed] ~= nil
end

return F
