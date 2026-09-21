--[[ Shuttlecraft -- the phaser.

    A phaser never runs out. It is an ordinary build 42 firearm in every other
    respect -- you aim it, you fire it, it does damage and makes a noise --
    and this file is the one thing that makes it a phaser: a slow tick that
    puts the charge, the chambered round and the condition back.

    Three notes on why it is built this way.

    **The ammo type is 9mm and that is deliberate.** A phaser ought to have
    its own power cell, and it cannot: `AmmoType = base:bullets_9mm` resolves
    through AmmoType.registerBase in Java, and there is no script syntax
    anywhere in the build that lets a mod add one -- grep the whole of
    media/scripts for `bullets_9mm` and it appears only as the value of
    AmmoType lines, never as a definition. A made-up id would resolve to
    nothing and the weapon would refuse to fire, which is exactly the sort of
    silent failure that costs an evening. So the phaser nominally chambers
    9mm, and because the charge is topped up faster than anyone can spend it,
    nothing is ever drawn from the player's own ammunition.

    **The top-up is a sweep of the inventory, not a hook on firing.** There is
    no reliable "the player shot" event to hang this on, and a phaser in a bag
    should be as full as one in your hand when you draw it. Sweeping every
    C.PhaserInterval ticks is cheap -- one recursive type lookup and a handful
    of setters -- and covers both.

    **Every engine call is batched.** A wrong method name in a per-item loop
    throws out of Java and the engine dumps a stack trace per call; U.batch
    stops after the first failure so one bad name costs one warning instead of
    a frozen game.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local P = {}
TREK.Phaser = P

---------------------------------------------------------------------------
-- Finding the phasers on a player
---------------------------------------------------------------------------
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
function P.carriedBy(player)
    local out, seen = {}, {}

    local function add(item)
        if not item or seen[item] then return end
        local t = U.try("phaser.fullType", function() return item:getFullType() end)
        if t ~= C.PhaserItem then return end
        seen[item] = true
        table.insert(out, item)
    end

    local inv = U.try("phaser.inventory", function() return player:getInventory() end)
    if inv then
        local list = U.try("phaser.find", function()
            return inv:getAllTypeRecurse(C.PhaserType)
        end)
        if list then
            local join = U.batch("phaser.list")
            local n = join(function() return list:size() end) or 0
            for i = 0, n - 1 do
                add(join(function() return list:get(i) end))
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

---------------------------------------------------------------------------
-- When to sweep
---------------------------------------------------------------------------
local tick = 0

-- Only this client's own characters: OnPlayerUpdate also runs for the other
-- players a client can see, and their inventories are not ours to change.
Events.OnPlayerUpdate.Add(function(player)
    if not player or not player:isLocalPlayer() then return end
    tick = tick + 1
    if tick < C.PhaserInterval then return end
    tick = 0
    P.sweep(player)
end)

--- Exposed for the debug console: TREK_Phaser()
---
--- Says how many phasers the sweep can see on you and how many it had to top
--- up. Zero found while one is in your hands means the inventory lookup is
--- wrong, which is the one failure here that would otherwise be silent.
function TREK_Phaser()
    local player = U.player(0)
    if not player then return 0 end
    local charged, found = P.sweep(player)
    U.log("phaser: %d found on you, %d recharged", found, charged)
    return found
end

return P
