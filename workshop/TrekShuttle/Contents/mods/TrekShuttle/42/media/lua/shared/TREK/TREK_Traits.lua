--[[ Shuttlecraft -- species, divisions and rank: the shared half (TRAITS.md).

    The ids live in media/registries.lua (TREK_Registries.Traits), which the
    engine runs before anything else. This file is what asks about them, and
    the one rule every effect here follows:

    **The server decides, and tells the player.** A character's stats live
    in two processes -- the server's copy and the owning client's -- and which
    copy wins depends on the stat and the moment (PADD.md 8: "the stats live
    on both"). So nothing here guesses. Every effect a trait has on a stat is
    worked out where the authority is, applied there, and sent to the owning
    client to apply to its own copy (T.adjust). In single player there is one
    process and one copy, and it is applied once.

    Eating is the same: vanilla's ISEatFoodAction:complete() runs Eat() on the
    server (bytecode: IsoGameCharacter.Eat bci 645-759 sends the stats and the
    EatFood packet from there), so the verdict on a meal is taken there too.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"

TREK = TREK or {}
local C, U, Net = TREK.Config, TREK.Util, TREK.Net

local T = {}
TREK.Traits = T

T.SPECIES = { "vulcan", "klingon", "andorian", "betazoid", "trill", "bajoran",
              "talaxian", "orion", "android", "exborg" }

-- The stats a trait may touch, with the engine's range for each.
T.STATS = {
    UNHAPPINESS = { 0, 100 }, BOREDOM = { 0, 100 }, PANIC = { 0, 100 },
    STRESS = { 0, 1 }, ENDURANCE = { 0, 1 }, FATIGUE = { 0, 1 },
    HUNGER = { 0, 1 }, THIRST = { 0, 1 },
}

---------------------------------------------------------------------------
-- Asking
---------------------------------------------------------------------------
--- The registered CharacterTrait for a path ("vulcan"), or nil.
function T.id(path)
    local reg = rawget(_G, "TREK_Registries")
    return reg and reg.Traits and reg.Traits[path] or nil
end

function T.has(character, path)
    local id = T.id(path)
    if not character or not id then return false end
    return U.try("hasTrait:" .. path, function() return character:hasTrait(id) end) == true
end

--- The character's species path, or nil for a human.
function T.species(character)
    for _, s in ipairs(T.SPECIES) do
        if T.has(character, s) then return s end
    end
    return nil
end

--- The character's rank as (index into C.Ranks, path), or 0, nil.
function T.rank(character)
    for i = #C.Ranks, 1, -1 do
        if T.has(character, C.Ranks[i]) then return i, C.Ranks[i] end
    end
    return 0, nil
end

--- True for anybody in any Starfleet division.
function T.isStarfleet(character)
    for path in pairs(T.DIVISIONS) do
        if T.has(character, path) then return true end
    end
    return false
end

T.DIVISIONS = { sf_command = "command", sf_helm = "command",
                sf_engineering = "operations", sf_security = "operations",
                sf_medical = "science", sf_science = "science",
                sf_survey = "science" }

---------------------------------------------------------------------------
-- Changing a character: on the authority, and mirrored to its owner
---------------------------------------------------------------------------
local function clamp(stat, v)
    local range = T.STATS[stat]
    if not range then return v end
    return math.max(range[1], math.min(range[2], v))
end

--- Applies `adj` ({ add = {STAT = delta}, set = {STAT = value} }) to one
--- character, in this process only.
function T.applyLocal(character, adj)
    if not character or type(adj) ~= "table" then return end
    local stats = U.try("traits.stats", function() return character:getStats() end)
    if not stats then return end
    for name, value in pairs(adj.set or {}) do
        local stat = CharacterStat[name]
        if stat and T.STATS[name] then
            U.try("traits.set:" .. name, function() stats:set(stat, clamp(name, value)) end)
        end
    end
    for name, delta in pairs(adj.add or {}) do
        local stat = CharacterStat[name]
        if stat and T.STATS[name] and delta ~= 0 then
            U.try("traits.add:" .. name, function()
                stats:set(stat, clamp(name, (stats:get(stat) or 0) + delta))
            end)
        end
    end
end

--- The authority's change to a character's stats. Applied here, and on a
--- server sent to the owning client, which applies the same thing to its own
--- copy (TREK_TraitsUI). Single player applies it once: there is no second
--- copy, and Net.toClient would run the handler in this same process.
function T.adjust(character, adj)
    if isClient() then return end
    T.applyLocal(character, adj)
    if isServer() then
        Net.toClient(character, "traitAdjust", {
            who = U.try("traits.who", function() return character:getUsername() end),
            add = adj.add, set = adj.set,
        })
    end
end

--- A halo note for one character, from the authority.
function T.note(character, key, arg, r, g, b)
    if isServer() then
        Net.toClient(character, "traitNote", {
            who = U.try("traits.who", function() return character:getUsername() end),
            key = key, arg = arg, r = r, g = g, b = b })
    elseif not isClient() then
        U.note(character, getText(key, arg and tostring(arg) or nil), r, g, b)
    end
end

---------------------------------------------------------------------------
-- The table (TRAITS.md 3.1b)
---------------------------------------------------------------------------
--- What a meal does to a character beyond its own numbers, as an adj and a
--- note key -- or nil. Pure: it reads, it changes nothing. `fraction` is how
--- much of the item was eaten.
function T.mealVerdict(character, fullType, foodType, replicated, fraction)
    local species = T.species(character)
    fraction = math.max(0, math.min(1, tonumber(fraction) or 1))
    if species == "android" then return nil end        -- no sense of taste

    local unhappy, stress = 0, 0
    local key
    local owner = C.SpeciesFood[fullType]
    if species and owner then
        if owner == species then
            unhappy, stress = C.FoodHomeUnhappy, C.FoodHomeStress
            key = "IGUI_TREK_FoodHome"
        elseif species ~= "trill" then
            unhappy = C.FoodForeignUnhappy
            key = "IGUI_TREK_FoodForeign"
        end
    end
    if species == "vulcan" and (C.MeatFoodTypes[foodType or ""] or owner == "klingon") then
        unhappy = unhappy + C.FoodMeatUnhappy
        key = "IGUI_TREK_FoodMeat"
    end
    if replicated and (species == "klingon" or T.has(character, "realfoodonly")) then
        unhappy = unhappy + C.FoodReplicatedUnhappy
        key = "IGUI_TREK_FoodReplicated"
    end
    if unhappy == 0 and stress == 0 then return nil end
    return { add = { UNHAPPINESS = unhappy * fraction, STRESS = stress * fraction } }, key
end

--- The authority's half of a meal: take the verdict and apply it. On a
--- client this does nothing, because T.adjust and T.note do nothing there --
--- one guard, in the one place every effect passes through.
function T.onAte(character, item, fraction)
    if not character or not item then return end
    local fullType = U.try("traits.foodType", function() return item:getFullType() end)
    local foodType = U.try("traits.foodKind", function() return item:getFoodType() end)
    local md = U.try("traits.foodMod", function() return item:getModData() end)
    local adj, key = T.mealVerdict(character, fullType, foodType,
                                   md ~= nil and md[C.ReplicatedKey] == true, fraction)
    if not adj then return end
    T.adjust(character, adj)
    if key then T.note(character, key) end
end

--- Wraps vanilla's eating action so every food counts, not only the galley's:
--- a Vulcan who eats a tin of Spam is as unhappy as one who eats gagh. The
--- engine copies an item's OnEat into the item when it is made, so an OnEat
--- line could never reach the meat already lying in the world.
function T.wrapEating()
    local A = rawget(_G, "ISEatFoodAction")
    if type(A) ~= "table" or A.TREKWrapped then return A ~= nil end
    local base = A.complete
    if type(base) ~= "function" then return false end
    A.complete = function(self)
        -- Read before Eat, which may use the item up.
        local item, who = self.item, self.character
        local fraction = self.percentage
        local result = base(self)
        U.try("traits.ate", T.onAte, who, item, fraction)
        return result
    end
    A.TREKWrapped = true
    return true
end

---------------------------------------------------------------------------
-- Small factors other files ask for
---------------------------------------------------------------------------
--- The flight speed factor for the pilot on this machine.
function T.helmFactor(pilot)
    return T.has(pilot, "sf_helm") and C.HelmSpeedFactor or 1
end

--- The tricorder's sweep radius for this holder.
function T.sweepRadius(holder)
    return C.SweepRadius * (T.has(holder, "sf_science") and C.ScienceSweepFactor or 1)
end

--- The PADD's time factor for this reader.
function T.paddFactor(reader)
    return T.has(reader, "holohistorian") and C.HistorianTimeFactor or 1
end

--- What the ship's power costs, all told: less with an engineer aboard.
function T.powerFactor()
    for _, p in ipairs(U.players()) do
        if T.has(p, "sf_engineering") and U.isInteriorPlayer(p) then
            return C.EngineeringFactor
        end
    end
    return 1
end

---------------------------------------------------------------------------
-- Boot
---------------------------------------------------------------------------
--- The scripts write each exclusion one way -- a Vulcan excludes Weak -- and
--- character creation only looks at the list of the trait being picked, so
--- Weak then Vulcan would stack. `setMutualExclusive` writes both ways
--- (bytecode: two guarded ArrayList.add, one per definition).
function T.symmetrise()
    local reg = rawget(_G, "TREK_Registries")
    if not reg or not reg.Traits then return 0 end
    local n = 0
    for path, id in pairs(reg.Traits) do
        local def = U.try("traits.def:" .. path, function()
            return CharacterTraitDefinition.getCharacterTraitDefinition(id)
        end)
        local list = def and U.try("traits.excl:" .. path, function()
            return def:getMutuallyExclusiveTraits()
        end)
        local size = list and (U.try("traits.exclSize", function() return list:size() end) or 0) or 0
        for i = 0, size - 1 do
            local other = list:get(i)
            if U.try("traits.mutual", function()
                CharacterTraitDefinition.setMutualExclusive(other, id)
                return true
            end) then n = n + 1 end
        end
    end
    return n
end

T.wrapEating()
Events.OnGameBoot.Add(function()
    T.wrapEating()
    local n = T.symmetrise()
    U.log("traits: %d exclusion(s) made two-way", n)
end)

return T
