--[[ Shuttlecraft -- hydroponics aboard the Adirondack (FARMING.md).

    **Vanilla farming, on our trays.** The seven crops are ordinary vanilla
    crop types in `farming_vegetableconf.props`, so vanilla's own menus sow,
    water, cure and harvest them, its global object system grows and saves
    them, and multiplayer sync is vanilla's. What this file adds is only what
    vanilla cannot know about a starship:

      * **the crops** -- registered here, with the sprite tables
        tools/gen_adirondack_crops.py renders (TREK_FarmSprites);
      * **the trays** -- vanilla's dig menu refuses anything above ground, but
        its server `plow` does not (FARMING.md), so the server primes every
        hydroponic tray itself, and primes it again after a harvest;
      * **the greenhouse rule** -- vanilla kills crops indoors unless their
        room is a greenhouse, and a runtime deck has no rooms. Any plant on
        the Adirondack is kept from losing health to where it is;
      * **the bay runs itself** -- a plant aboard her is watered and kept
        free of pests and disease by the ship; planted in the ground below,
        the same crop needs the care any vanilla crop does (sandbox);
      * **the dehydrator** -- a container that dries what is put in it;
      * **the worm tank** -- serpent worms breed when the tank is fed.

    The crops themselves are registered in shared/TREK/TREK_FarmCrops.lua,
    because the sow menu reads them on clients too; this file is the server's.
]]

if isClient() then return end

require "TREK/TREK_FarmCrops"

TREK = TREK or {}
local F = TREK.Farm



---------------------------------------------------------------------------
-- The server
---------------------------------------------------------------------------
require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Adirondack"
require "Farming/SFarmingSystem"

local U = TREK.Util
local A = TREK.Adirondack
local L = A.Layout

local function system()
    return SFarmingSystem and SFarmingSystem.instance
end


local function autoWater()
    local v = U.try("hydroWater", function()
        return SandboxVars.TrekShuttle and SandboxVars.TrekShuttle.HydroponicsWater
    end)
    return tonumber(v) ~= 2
end

--- The plant on a square, or nil.
local function plantAt(x, y, z)
    local sys = system()
    if not sys then return nil end
    return U.try("farm.plantAt", function() return sys:getLuaObjectAt(x, y, z) end)
end

local DONE = { harvested = true, destroyed = true, dead = true, rotten = true }

--- Makes a tray ready to sow: clears a harvested or dead plant off it and
--- plows it, with our soil showing rather than vanilla's floor-level earth.
--- Returns true when it primed.
function F.primeTray(sq)
    local sys = system()
    if not sys or not sq then return false end
    local x, y, z = sq:getX(), sq:getY(), sq:getZ()
    local plant = plantAt(x, y, z)
    if plant and DONE[plant.state] then
        U.try("farm.clear", function() sys:removePlant(plant) end)
        plant = nil
    end
    if plant then return false end
    U.try("farm.plow", function() sys:plow(sq) end)
    local fresh = plantAt(x, y, z)
    if fresh and TREK_FarmSoil then
        U.try("farm.soil", function()
            fresh:setSpriteName(TREK_FarmSoil)
            fresh:saveData()
        end)
    end
    return fresh ~= nil
end

--- Every tray square on deck k: { x, y } in the world.
local traysOf = {}
function F.trays(k)
    if traysOf[k] then return traysOf[k] end
    local out = {}
    for _, o in ipairs(L.decks[k].objects) do
        if o[5] == "hydro_tray" then
            local x, y = A.at(k, o[1], o[2])
            table.insert(out, { x, y })
        end
    end
    traysOf[k] = out
    return out
end

--- Primes every loaded tray on deck k that needs it.
function F.primeDeck(k)
    local primed = 0
    for _, t in ipairs(F.trays(k)) do
        if U.chunkLoaded(t[1], t[2], A.Z) then
            local sq = U.square(t[1], t[2], A.Z, false)
            if sq and F.primeTray(sq) then primed = primed + 1 end
        end
    end
    return primed
end

---------------------------------------------------------------------------
-- The bay as the crew keep it
---------------------------------------------------------------------------
-- The bay is a working farm when anybody first walks into it: the front row
-- has one of each crop ready to harvest, the middle row one of each still
-- growing, and the back row is empty for the player to sow. By tray row, in
-- the order the layout lists the trays.
F.StartRows = {
    { "TrekTeaBush", "TrekBergamot", "TrekKlingonCoffee", "TrekPlomeek",
      "TrekLeolaRoot", "TrekAndorianTuber", "TrekHasperatPepper", stage = 5 },
    { "TrekHasperatPepper", "TrekAndorianTuber", "TrekLeolaRoot", "TrekPlomeek",
      "TrekKlingonCoffee", "TrekBergamot", "TrekTeaBush", stages = { 2, 3, 4, 2, 3, 4, 3 } },
}

--- Sows one primed tray and grows it to `stage` the way vanilla would have:
--- its own seed(), then its own growPlant() a stage at a time, watered, so
--- the plant carries every field a hand-sown one does. Returns true.
function F.plantTray(sq, crop, stage)
    local sys = system()
    local plant = sq and plantAt(sq:getX(), sq:getY(), sq:getZ())
    if not sys or not plant or plant.state ~= "plow" then return false end
    U.try("farm.seed", function() plant:seed(crop, 3) end)
    if plant.state ~= "seeded" then return false end
    for _ = 1, 20 do
        if (plant.nbOfGrow or 0) >= stage then break end
        plant.waterLvl = 100
        U.try("farm.grow", function() sys:growPlant(plant, nil, true) end)
    end
    local prop = farming_vegetableconf.props[crop]
    plant.health = 80
    plant.waterLvl = 100
    plant.mildewLvl, plant.aphidLvl, plant.fliesLvl, plant.slugsLvl = 0, 0, 0, 0
    if prop and (plant.nbOfGrow or 0) >= prop.harvestLevel then plant.hasVegetable = true end
    U.try("farm.stageSprite", function()
        plant:setSpriteName(farming_vegetableconf.getSpriteName(plant))
        plant:setObjectName(farming_vegetableconf.getObjectName(plant))
    end)
    U.try("farm.stageSave", function() plant:saveData() end)
    return true
end

--- Plants deck k's bay the first time it is seen (F.StartRows), once per
--- world. Only trays still waiting to be sown: anything a player has planted
--- is left alone. Returns how many it planted.
function F.stockBay(k)
    local AS = TREK.AdirondackServer
    local st = AS and AS.state()
    if not st then return 0 end
    st.farmStocked = st.farmStocked or {}
    if st.farmStocked[k] then return 0 end
    local trays = F.trays(k)
    if #trays == 0 then return 0 end
    for _, t in ipairs(trays) do
        if not U.chunkLoaded(t[1], t[2], A.Z) then return 0 end
    end
    -- The rows, as the layout has them: trays sorted by row, then along it.
    local rows = {}
    for _, t in ipairs(trays) do
        rows[t[2]] = rows[t[2]] or {}
        table.insert(rows[t[2]], t)
    end
    local ys = {}
    for y in pairs(rows) do table.insert(ys, y) end
    table.sort(ys)
    local planted = 0
    for r, spec in ipairs(F.StartRows) do
        local row = rows[ys[r]]
        if row then
            table.sort(row, function(a, b) return a[1] < b[1] end)
            for i, t in ipairs(row) do
                local crop = spec[i]
                local stage = spec.stage or (spec.stages and spec.stages[i]) or 3
                local sq = crop and U.square(t[1], t[2], A.Z, false)
                if sq and F.plantTray(sq, crop, stage) then planted = planted + 1 end
            end
        end
    end
    st.farmStocked[k] = true
    U.log("hydroponics: deck %d's bay planted, %d crops growing", k, planted)
    return planted
end

-- **Harvest clears the tray at once.** Vanilla leaves a harvested annual as
-- a stub until somebody digs it out; aboard her, the tray is cleared and
-- primed the moment the harvest is taken, ready to sow again (the hourly
-- pass did it too, but an hour of stub read as a harvest that failed).
-- Perennials -- tea, bergamot, coffee -- regrow in place and are left alone.
local harvestWrapped = false
function F.wrapHarvest()
    if harvestWrapped or not SFarmingSystem or not SFarmingSystem.harvest then return false end
    local original = SFarmingSystem.harvest
    SFarmingSystem.harvest = function(self, plant, player, ...)
        local a, b, c = original(self, plant, player, ...)
        if plant and F.onShip(plant) and DONE[plant.state] then
            local sq = U.square(plant.x, plant.y, plant.z, false)
            if sq then U.try("farm.reprime", F.primeTray, sq) end
        end
        return a, b, c
    end
    harvestWrapped = true
    return true
end

-- **The greenhouse rule.** Vanilla's health pass takes health off a plant
-- indoors unless its room is a greenhouse, and in winter and bad months off
-- one it thinks is outdoors; our deck has no rooms, and may count as either.
-- So round that pass: what a plant aboard her had going in, it keeps.
-- Health it gains -- sun, care -- it keeps too.
local wrapped = false
function F.wrapHealth()
    local sys = system()
    if wrapped or not SFarmingSystem or not SFarmingSystem.changeHealth then return false end
    local original = SFarmingSystem.changeHealth
    SFarmingSystem.changeHealth = function(self, ...)
        local before = {}
        U.try("farm.healthBefore", function()
            for i = 1, self:getLuaObjectCount() do
                local p = self:getLuaObjectByIndex(i)
                if p and F.onShip(p) and p.health then before[p] = p.health end
            end
        end)
        local a, b, c = original(self, ...)
        for p, h in pairs(before) do
            if p.health and p.health < h then
                p.health = h
                U.try("farm.healthSave", function() p:saveData() end)
            end
        end
        return a, b, c
    end
    wrapped = true
    return true
end

--- **The bay runs itself.** Every live plant aboard her is tended by the
--- ship each hour: watered full, and any pest or disease cleared. Planting
--- and harvesting are the crew's; the rest is hydroponics. The same crops
--- sown in the ground down in Kentucky get none of this -- out there they
--- are vanilla crops and need watering, weeding and curing like any other.
--- (Sandbox: "Hydroponics tend themselves", on by default.)
function F.tendAll()
    if not autoWater() then return 0 end
    local sys = system()
    if not sys then return 0 end
    local n = 0
    U.try("farm.tend", function()
        for i = 1, sys:getLuaObjectCount() do
            local p = sys:getLuaObjectByIndex(i)
            if p and F.onShip(p) and p.state ~= "plow" and p:isAlive() then
                local needs = (p.waterLvl or 0) < 90 or (p.mildewLvl or 0) > 0 or (p.aphidLvl or 0) > 0
                    or (p.fliesLvl or 0) > 0 or (p.slugsLvl or 0) > 0
                if needs then
                    p.waterLvl = 100
                    p.mildewLvl, p.aphidLvl, p.fliesLvl, p.slugsLvl = 0, 0, 0, 0
                    p:saveData()
                    n = n + 1
                end
            end
        end
    end)
    return n
end
F.waterAll = F.tendAll

---------------------------------------------------------------------------
-- The dehydrator
---------------------------------------------------------------------------
-- What dries into what, and in how many game hours.
F.Dry = {
    ["TrekShuttle.TrekTeaLeaves"] = "TrekShuttle.TrekTeaDried",
    ["TrekShuttle.TrekKlingonCoffeeCherries"] = "TrekShuttle.TrekKlingonCoffeeBeans",
    ["TrekShuttle.TrekHasperatPeppers"] = "TrekShuttle.TrekHasperatDried",
}
F.DryHours = 12

local function containersOf(piece, k)
    local out = {}
    for _, o in ipairs(L.decks[k].objects) do
        if o[5] == piece then
            local x, y = A.at(k, o[1], o[2])
            if U.chunkLoaded(x, y, A.Z) then
                local obj = U.findSprite(U.square(x, y, A.Z, false), o[3])
                local c = obj and U.containerOf(obj)
                if c then table.insert(out, c) end
            end
        end
    end
    return out
end

local function replaceItem(c, item, fullType)
    local fresh = U.try("farm.make", function() return instanceItem(fullType) end)
    if not fresh then return false end
    U.try("farm.swap", function()
        c:Remove(item)
        if isServer() then sendRemoveItemFromContainer(c, item) end
        c:AddItem(fresh)
        if isServer() then sendAddItemToContainer(c, fresh) end
    end)
    return true
end

--- One game hour in every loaded dehydrator on deck k.
function F.serviceDehydrators(k)
    local dried = 0
    for _, c in ipairs(containersOf("dehydrator", k)) do
        local items = U.try("farm.items", function() return c:getItems() end)
        local todo = {}
        if items then
            for i = 0, items:size() - 1 do
                local it = items:get(i)
                local into = it and F.Dry[it:getFullType()]
                if into then
                    local md = it:getModData()
                    md.TREKDry = (md.TREKDry or 0) + 1
                    if md.TREKDry >= F.DryHours then table.insert(todo, { it, into }) end
                end
            end
        end
        for _, t in ipairs(todo) do
            if replaceItem(c, t[1], t[2]) then dried = dried + 1 end
        end
    end
    return dried
end

---------------------------------------------------------------------------
-- The worm tank (FARMING.md)
---------------------------------------------------------------------------
F.Worm = "TrekShuttle.TrekSerpentWorm"
F.WormCap = 20
F.WormBreedHours = 6
F.WormStarveHours = 24

--- One game hour in every loaded worm tank on deck k: worms that are fed
--- breed, worms that are not go hungry, and none of them rots in the tank.
function F.serviceWormTanks(k)
    local born, lost = 0, 0
    for _, c in ipairs(containersOf("worm_tank", k)) do
        local worms, food = {}, {}
        U.try("farm.tank", function()
            local items = c:getItems()
            for i = 0, items:size() - 1 do
                local it = items:get(i)
                if it:getFullType() == F.Worm then
                    table.insert(worms, it)
                elseif instanceof(it, "Food") or U.try("farm.isFood", function() return it:IsFood() end) == true then
                    table.insert(food, it)
                end
            end
        end)
        -- Worms kept in a tank never rot: their age goes back to nothing
        -- every hour, as the composter does for vanilla's (IsoCompost.update).
        for _, w in ipairs(worms) do
            U.try("farm.wormAge", function() w:setAge(0) end)
        end
        local parent = U.try("farm.tankObj", function() return c:getParent() end)
        local md = parent and parent:getModData() or {}
        md.TREKWormFed = (md.TREKWormFed or 0) + 1
        md.TREKWormHungry = (#food > 0) and 0 or ((md.TREKWormHungry or 0) + 1)
        if #worms >= 2 and #food > 0 and #worms < F.WormCap and md.TREKWormFed >= F.WormBreedHours then
            md.TREKWormFed = 0
            U.try("farm.feed", function()
                c:Remove(food[1])
                if isServer() then sendRemoveItemFromContainer(c, food[1]) end
                local w = instanceItem(F.Worm)
                c:AddItem(w)
                if isServer() then sendAddItemToContainer(c, w) end
            end)
            born = born + 1
        elseif #worms > 2 and md.TREKWormHungry >= F.WormStarveHours then
            md.TREKWormHungry = 0
            U.try("farm.starve", function()
                c:Remove(worms[1])
                if isServer() then sendRemoveItemFromContainer(c, worms[1]) end
            end)
            lost = lost + 1
        end
    end
    return born, lost
end

---------------------------------------------------------------------------
-- The hour
---------------------------------------------------------------------------
--- Everything hydroponic, once a game hour, on every deck that is built.
function F.hourly()
    F.ensure()
    F.wrapHealth()
    F.wrapHarvest()
    F.tendAll()
    local AS = TREK.AdirondackServer
    for k = 1, #L.decks do
        if AS and AS.state().decks[k] then
            F.primeDeck(k)
            F.stockBay(k)
            F.serviceDehydrators(k)
            F.serviceWormTanks(k)
        end
    end
end

Events.EveryHours.Add(function()
    U.try("farm.hourly", F.hourly)
end)

Events.OnGameStart.Add(function()
    U.try("farm.wrap", F.wrapHealth)
    U.try("farm.wrapHarvest", F.wrapHarvest)
end)
Events.OnServerStarted.Add(function()
    U.try("farm.wrap", F.wrapHealth)
    U.try("farm.wrapHarvest", F.wrapHarvest)
end)

return F
