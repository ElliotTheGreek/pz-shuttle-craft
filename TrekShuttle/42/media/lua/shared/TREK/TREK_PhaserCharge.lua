--[[ Shuttlecraft -- keeping energy weapons charged, on either side.

    The phaser, the phaser rifle and the alien arms never run out, jam or wear
    (TREK_Phaser, ARMOURY.md). The charging lives here so that the machine
    whose copy of the weapon counts does it: the player's own in single
    player, the server in multiplayer (TREK_PhaserServer), which then sends
    the weapon's fields to its holder. The server's copy is the one the hit
    anti-cheat reads ("not enough ammo"), and a charge made only on the
    client kicked a player for firing (1.10.1).
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local P = {}
TREK.PhaserCharge = P

--- Every phaser anywhere on the player: pockets, bags, and both hands.
---
--- getAllTypeRecurse walks sub-containers, which is what makes a phaser in a
--- rucksack count. It compares the *bare* type the way containsTypeRecurse
--- does, so it is handed C.PhaserType and the results are then filtered on
--- the full id -- the bare type is not namespaced and another mod could
--- plausibly use it.
---
--- Deliberately not getItemsFromFullType(type, true): that overload's boolean
--- is undocumented and guessing at it is how the whole feature ends up
--- silently doing nothing. getAllTypeRecurse says what it does in its name.
---
--- The hands are checked separately because an equipped item is not always in
--- the container listing, and a phaser you are holding is the one that most
--- needs to be full.
---
--- **Every energy weapon, not only the phaser** (ARMOURY.md): the phaser
--- rifle and the alien arms are kept full by this same sweep, one bare-type
--- search per entry in C.EnergyWeapons. `only` narrows it to one full id.
function P.carriedBy(player, only)
    local out, seen = {}, {}

    local function add(item)
        if not item or seen[item] then return end
        local t = U.try("phaser.fullType", function() return item:getFullType() end)
        if not C.energyWeapon(t) or (only and t ~= only) then return end
        seen[item] = true
        table.insert(out, item)
    end

    local inv = U.try("phaser.inventory", function() return player:getInventory() end)
    if inv then
        local join = U.batch("phaser.list")
        for full, spec in pairs(C.EnergyWeapons) do
            if not only or only == full then
                local list = U.try("phaser.find", function()
                    return inv:getAllTypeRecurse(spec.type)
                end)
                if list then
                    local n = join(function() return list:size() end) or 0
                    for i = 0, n - 1 do
                        add(join(function() return list:get(i) end))
                    end
                end
            end
        end
    end

    add(U.try("phaser.primary", function() return player:getPrimaryHandItem() end))
    add(U.try("phaser.secondary", function() return player:getSecondaryHandItem() end))
    return out
end

---------------------------------------------------------------------------
-- Charging one
---------------------------------------------------------------------------
--- Puts a phaser back to full. Returns true when it actually changed
--- something, so the sweep can stay quiet on the overwhelmingly common tick
--- where nothing has been fired.
---
--- Each concern does its reading and its writing inside the same batched
--- call: they are one trip out to Java, and a wrong name breaks the batch
--- once rather than throwing per item.
function P.charge(item, join)
    local changed = false

    if C.PhaserInfiniteAmmo then
        if join.ammo(function()
            local max = item:getMaxAmmo()
            if not max or max <= 0 then return false end
            if item:getCurrentAmmoCount() >= max and item:isRoundChambered() then
                return false
            end
            item:setCurrentAmmoCount(max)
            item:setRoundChambered(true)
            item:setSpentRoundCount(0)
            item:setSpentRoundChambered(false)
            return true
        end) == true then changed = true end
    end

    if C.PhaserNeverJams then
        if join.jam(function()
            if not item:isJammed() then return false end
            item:setJammed(false)
            return true
        end) == true then changed = true end
    end

    if C.PhaserNeverWears then
        if join.wear(function()
            local max = item:getConditionMax()
            if not max or item:getCondition() >= max then return false end
            item:setCondition(max)
            return true
        end) == true then changed = true end
    end

    return changed
end

---------------------------------------------------------------------------
-- A sweep
---------------------------------------------------------------------------
--- One batch per kind of call, made fresh for each sweep. A batch that has
--- failed stays failed, which is what we want within a sweep and not what we
--- want forever.
local function batches()
    return {
        ammo = U.batch("phaser.ammo"),
        jam  = U.batch("phaser.jam"),
        wear = U.batch("phaser.wear"),
    }
end

--- Recharges every phaser on a player. Returns how many were topped up and
--- how many were found, which is the difference between "the sweep never saw
--- your phaser" and "your phaser was already full".
function P.sweep(player)
    if not player then return 0, 0 end
    local carried = P.carriedBy(player)
    if #carried == 0 then return 0, 0 end

    local join = batches()
    local charged = 0
    for _, item in ipairs(carried) do
        if P.charge(item, join) then charged = charged + 1 end
    end
    return charged, #carried
end


return P
