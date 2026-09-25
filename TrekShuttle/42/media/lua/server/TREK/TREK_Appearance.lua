--[[ Shuttlecraft -- what a species looks like, on the character in the world
    (TRAITS.md 2.4, 4.6).

    The creation screen already dresses a new character (TREK_CreationLook),
    so a character made with a species arrives wearing it. This is the
    authority's half: the check that keeps it right afterwards. It dresses
    the character's HumanVisual with TREK_Looks and tells every machine,
    exactly as vanilla's ISCutHair does once a haircut completes -- change the
    visual here, then sendHumanVisual(character).

    **It is a check, not a one-shot.** L.dress changes only the difference, so
    this runs on first sight and every ten minutes: it repairs an old save,
    follows a species an admin adds or takes away, and takes this mod's look
    off a human.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Traits"
require "TREK/TREK_Looks"

local U = TREK.Util
local T = TREK.Traits
local L = TREK.Looks

local A = {}
TREK.Appearance = A

-- The look table, where the tests and TRAITS.md expect to find it.
A.LOOKS = L.LOOKS
A.ITEMS = L.ITEMS

--- Brings the character's look into line with their species. Returns true
--- when anything changed (and was sent).
function A.apply(player)
    if not player then return false end
    local hv = U.try("look.hv", function() return player:getHumanVisual() end)
    if not hv then return false end
    local female = U.try("look.female", function() return player:isFemale() end) == true
    local changed = L.dress(hv, T.species(player), female)
    if changed then
        U.try("look.reset", function() player:resetModelNextFrame() end)
        if isServer() then
            U.try("look.send", function() sendHumanVisual(player) end)
        end
        U.log("look: %s dressed as %s", tostring(U.try("look.who", function()
            return player:getUsername() end)), tostring(T.species(player) or "human"))
    end
    return changed
end

--- Every player, every ten minutes: cheap, because nothing changes unless
--- something is wrong.
Events.EveryTenMinutes.Add(function()
    for _, p in ipairs(U.players()) do
        U.try("look.service", A.apply, p)
    end
end)

return A
