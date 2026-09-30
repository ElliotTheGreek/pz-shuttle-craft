--[[ Shuttlecraft -- the engineer's field kit (FIELD_KIT.md).

    A satchel of five Starfleet tools and a hundred self-sealing stem bolts.
    Three things make it work, and each is here:

    **The tools stand in for vanilla's by their tags** (media/scripts/
    trekengineering.txt). Vanilla's recipes ask for a tool by tag --
    `tags[base:hammer]` 140 times, the saw, wrench and screwdriver the same --
    so a tool carrying the tag is that tool to every recipe and every build,
    with nothing here at all.

    **Nails and the blowtorch are asked for by item id**, `[Base.Nails]` 110
    times and `[Base.BlowTorch]` 65, and a tag cannot answer those. So when
    the world has loaded, patchRecipes adds the stem bolts and the welder to
    the item list of every recipe input that names them. The bytecode is why
    that works (FIELD_KIT.md 5): an input's accepted items are
    InputScript.itemScriptCache, a plain ArrayList made in its constructor and
    filled in OnPostWorldDictionaryInit (bci 576), which getPossibleInputItems
    hands back as itself; and canUseItem, which every craft asks, matches an
    item against that list by name. Only an "any item" input wraps it
    unmodifiable (bci 507), and none of those names nails. Every process
    loads the scripts itself, so every process patches its own; it is shared
    code, run on OnGameStart and OnServerStarted, and it does nothing twice.

    **Unlimited uses** is the phaser's rule (TREK_PhaserCharge): the machine
    whose copy counts -- the server in multiplayer, the only machine in
    single player -- puts a carried tool's condition and the welder's charge
    back (TREK_FieldKitServer), and says so to the holder.

    What stem bolts do *not* reach is the barricade menu: it is Java
    (ISWorldObjectContextMenuLogic.doBarricadeMenu) and counts Base.Nails by
    key, and wants an item whose type is BlowTorch for a metal one. Planks
    over a window still take nails.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local FK = {}
TREK.FieldKit = FK

---------------------------------------------------------------------------
-- Stem bolts and the welder in vanilla's recipes
---------------------------------------------------------------------------
local function scriptItem(id)
    return U.try("fieldkit.scriptItem", function()
        return ScriptManager.instance:getItem(id)
    end)
end

local function nameOf(item)
    return U.try("fieldkit.itemName", function() return item:getFullName() end)
end

--- Adds our stand-ins to every recipe input that lists what they replace.
--- Returns { ["Base.Nails"] = inputs patched, ... } and how many inputs were
--- already patched, which is how running twice is told from running never.
function FK.patchRecipes()
    local ours = {}
    for vanilla, mine in pairs(C.FieldKitStandIns) do
        local it = scriptItem(mine)
        if not it then
            U.log("WARN field kit: no item script for %s; recipes will not take it", mine)
        else
            ours[vanilla] = it
        end
    end
    local recipes = U.try("fieldkit.recipes", function()
        return ScriptManager.instance:getAllCraftRecipes()
    end)
    local n = recipes and (U.try("fieldkit.recipeCount", function() return recipes:size() end) or 0) or 0
    local patched, already = {}, 0
    for vanilla in pairs(ours) do patched[vanilla] = 0 end
    local join = U.batch("fieldkit.input")
    -- Its own batch: one refusal must not stop the reads for every recipe
    -- after it.
    local addJoin = U.batch("fieldkit.add")
    for r = 0, n - 1 do
        local recipe = recipes:get(r)
        local inputs = join(function() return recipe:getInputs() end)
        local ni = inputs and (join(function() return inputs:size() end) or 0) or 0
        for i = 0, ni - 1 do
            local input = inputs:get(i)
            -- An "any item" input's list is the whole catalogue, unmodifiable
            -- (bci 507). It already holds the stem bolts, so the patch would
            -- count it done and never try to add; skipping it changes no
            -- outcome, and a mutation cannot see it (DEV_GUIDE, *A branch a
            -- mutation cannot break*). It is kept for the cost: it spares
            -- reading five thousand names for every such input at load.
            if not join(function() return input:isAcceptsAnyItem() end) then
                local list = join(function() return input:getPossibleInputItems() end)
                local count = list and (join(function() return list:size() end) or 0) or 0
                local names = {}
                for k = 0, count - 1 do
                    local nm = nameOf(list:get(k))
                    if nm then names[nm] = true end
                end
                for vanilla, it in pairs(ours) do
                    if names[vanilla] then
                        if names[nameOf(it)] then
                            already = already + 1
                        elseif addJoin(function() list:add(it); return true end) then
                            patched[vanilla] = patched[vanilla] + 1
                        end
                    end
                end
            end
        end
    end
    return patched, already
end

--- Patches once per process, and logs what it did. **No recipe naming nails
--- at all is a broken check, not a quiet world** (DEV_GUIDE: a check against
--- an empty set is not a passing check), so it is a WARN.
function FK.patchOnce()
    if FK.patched then return end
    local patched, already = FK.patchRecipes()
    local nails = (patched["Base.Nails"] or 0)
    if nails + already == 0 then
        U.log("WARN field kit: found no recipe that takes nails; stem bolts will "
              .. "stand in for nothing")
        return
    end
    FK.patched = true
    U.log("field kit: stem bolts stand in for nails in %d recipe inputs, the welder "
          .. "for a blowtorch in %d", nails, patched["Base.BlowTorch"] or 0)
end

Events.OnGameStart.Add(function() U.try("fieldkit.patchStart", FK.patchOnce) end)
if Events.OnServerStarted then
    Events.OnServerStarted.Add(function() U.try("fieldkit.patchServer", FK.patchOnce) end)
end

---------------------------------------------------------------------------
-- Never wearing out
---------------------------------------------------------------------------
--- Every field tool on the player: pockets, bags (the kit included), hands.
function FK.carriedBy(player)
    local out, seen = {}, {}
    local function add(item)
        if not item or seen[item] then return end
        local t = U.try("fieldkit.fullType", function() return item:getFullType() end)
        if not C.FieldTools[t] then return end
        seen[item] = true
        table.insert(out, item)
    end
    local inv = U.try("fieldkit.inventory", function() return player:getInventory() end)
    if inv then
        local join = U.batch("fieldkit.find")
        for _, bare in pairs(C.FieldTools) do
            local list = join(function() return inv:getAllTypeRecurse(bare) end)
            local n = list and (join(function() return list:size() end) or 0) or 0
            for i = 0, n - 1 do add(join(function() return list:get(i) end)) end
        end
    end
    add(U.try("fieldkit.primary", function() return player:getPrimaryHandItem() end))
    add(U.try("fieldkit.secondary", function() return player:getSecondaryHandItem() end))
    return out
end

--- Puts one tool back to new: condition, and the welder's charge. True when
--- it changed anything, so the sweep can stay quiet.
function FK.restore(item, join)
    local changed = false
    if join.wear(function()
        local max = item:getConditionMax()
        if not max or item:getCondition() >= max then return false end
        item:setCondition(max)
        return true
    end) == true then changed = true end
    if item:getFullType() == C.LaserWelderItem then
        if join.charge(function()
            if item:getCurrentUsesFloat() >= 1.0 then return false end
            item:setUsedDelta(1.0)
            return true
        end) == true then changed = true end
    end
    return changed
end

--- Restores every field tool a player carries. Returns the items changed.
function FK.sweep(player)
    local join = { wear = U.batch("fieldkit.wear"), charge = U.batch("fieldkit.charge") }
    local changed = {}
    for _, item in ipairs(FK.carriedBy(player)) do
        if FK.restore(item, join) then table.insert(changed, item) end
    end
    return changed
end

---------------------------------------------------------------------------
-- A kit as the ship issues it
---------------------------------------------------------------------------
--- Fills a kit with its tools and bolts. Returns how many items went in, and
--- counts them: a container at capacity drops what it is handed without a
--- word (DEV_GUIDE, *Never trust one way of doing it*).
function FK.fillKit(kit)
    local inner = U.try("fieldkit.inner", function() return kit:getItemContainer() end)
    if not inner then
        U.log("WARN field kit: the satchel has no container; nothing packed")
        return 0
    end
    local want = #C.FieldKitTools + C.FieldKitBolts
    local landed = 0
    local join = U.batch("fieldkit.pack")
    local function put(id)
        local it = instanceItem(id)
        if it and join(function() return inner:AddItem(it) end) ~= nil then
            landed = landed + 1
        end
    end
    for _, id in ipairs(C.FieldKitTools) do put(id) end
    for _ = 1, C.FieldKitBolts do put(C.StemBoltItem) end
    if landed < want then
        U.log("WARN field kit: packed %d of %d items", landed, want)
    end
    return landed
end

return FK
