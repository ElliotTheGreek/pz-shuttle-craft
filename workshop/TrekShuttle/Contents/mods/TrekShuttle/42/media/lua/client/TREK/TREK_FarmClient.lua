--[[ Shuttlecraft -- hydroponics, on the client (FARMING.md).

    One job: vanilla's sow menu lists the crops in farming_vegetableconf, and
    vanilla's own farming files reset that table when they load. So right
    before the menu is built, make sure ours are in it (TREK.Farm.ensure).
]]

if isServer() then return end

require "TREK/TREK_FarmCrops"

local wrapped = false

local function wrapSeedMenu()
    if wrapped or not ISFarmingMenu or not ISFarmingMenu.doSeedMenu then return end
    local original = ISFarmingMenu.doSeedMenu
    ISFarmingMenu.doSeedMenu = function(...)
        if TREK.Farm and TREK.Farm.ensure then TREK.Farm.ensure() end
        return original(...)
    end
    wrapped = true
end

Events.OnGameStart.Add(wrapSeedMenu)
Events.OnFillWorldObjectContextMenu.Add(function()
    if TREK.Farm and TREK.Farm.ensure then TREK.Farm.ensure() end
    wrapSeedMenu()
end)
