--[[ Shuttlecraft -- what the hydroponics recipes run (FARMING.md 3).

    `OnCreate` in a craftRecipe names a global function, called on whichever
    machine performs the recipe -- the server, on a server (vanilla's
    ISHandcraftAction.complete), so this is shared rather than client code.
    The signature is (craftRecipeData, character), as HorseMod's recipes use
    and vanilla's handcraft passes.
]]

require "TREK/TREK_Util"

TREK = TREK or {}
local U = TREK.Util

-- How hot a freshly brewed mug comes out: the engine's item heat, where 1.0
-- is room temperature and cooking raises it. NOT YET SEEN IN GAME whether a
-- fluid mug's heat does anything when drunk (FARMING.md 9.4).
local BREWED_HEAT = 1.8

--- Earl Grey and raktajino come off the recipe hot.
function TREKFarm_HotDrink(craftRecipeData, character)
    local made = U.try("farm.hotItems", function() return craftRecipeData:getAllCreatedItems() end)
    if not made then return end
    for i = 0, made:size() - 1 do
        local item = made:get(i)
        U.try("farm.heat", function() item:setItemHeat(BREWED_HEAT) end)
        if isServer() then
            U.try("farm.heatSync", function() sendItemStats(item) end)
        end
    end
end
