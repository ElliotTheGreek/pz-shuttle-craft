--[[ Shuttlecraft -- the server's rules on the character creation screen
    (SERVERS.md, TRAITS.md).

    A server may switch off a species, one of the mod's traits or a Starfleet
    profession (the *Shuttlecraft: roleplay* sandbox page). What it has
    switched off is simply not on the lists here, the way vanilla leaves the
    sleep traits off a server that has no sleeping: `isTraitEnabled` is
    vanilla's own question, asked of every trait as the two lists are filled,
    and this adds one more reason to answer no.

    **This screen is a courtesy; the server is the rule.** A character made
    some other way -- a preset, an older client, a world whose rules changed
    since -- is put right by TREK_TraitsServer.enforce, which reads the same
    TREK_Rules this does.

    The screen is built once, at the main menu, before any world's sandbox is
    known. So the lists are filled again whenever it is shown and the rules
    are not the ones it was last filled under (CR.refresh).
]]

if isServer() then return end

require "TREK/TREK_Util"
require "TREK/TREK_Rules"

local U = TREK.Util
local R = TREK.Rules

local CR = {}
TREK.CreationRules = CR

--- The mod's own path for a registered id ("vulcan"), or nil for anybody
--- else's. `kind` is "Traits" or "Professions" (media/registries.lua).
local function pathOf(kind, id)
    local reg = rawget(_G, "TREK_Registries")
    local map = reg and reg[kind]
    if not map or id == nil then return nil end
    for path, registered in pairs(map) do
        if registered == id then return path end
    end
    return nil
end

local function typeOf(def)
    if not def then return nil end
    return U.try("rules.type", function() return def:getType() end)
end

--- May this trait definition be on the lists?
function CR.traitShown(def)
    local path = pathOf("Traits", typeOf(def))
    return path == nil or R.traitAllowed(path)
end

--- May this profession definition be on the list?
function CR.professionShown(def)
    local path = pathOf("Professions", typeOf(def))
    return path == nil or R.professionAllowed(path)
end

--- Takes the professions the server has switched off out of a filled list.
function CR.prune(list)
    local n = 0
    if not list or not list.items then return n end
    for i = #list.items, 1, -1 do
        local row = list.items[i]
        if row and not CR.professionShown(row.item) then
            list:removeItemByIndex(i)
            n = n + 1
        end
    end
    return n
end

--- Fills the screen's lists again if the rules have changed since it last
--- did. Returns true when it did.
function CR.refresh(screen)
    local sig = R.creationSignature()
    if not screen or screen.TREK_rulesSeen == sig then return false end
    screen.TREK_rulesSeen = sig

    -- A trait picked under other rules -- a preset, the last server -- comes
    -- off, and gives its points back, as if the player had taken it off.
    -- (No test for a free trait: the ones a profession brings are never on a
    -- rule's list, and vanilla's removeTrait leaves a free one alone itself.)
    local picked = screen.listboxTraitSelected
    if picked and picked.items then
        for i = #picked.items, 1, -1 do
            local row = picked.items[i]
            if row and row.item and not CR.traitShown(row.item) then
                U.try("rules.unpick", function() screen:removeTrait(i) end)
            end
        end
    end
    if screen.repopulateTraitLists and screen.listboxTrait then
        U.try("rules.traits", function() screen:repopulateTraitLists() end)
    end

    local list = screen.listboxProf
    if list and list.items then
        local was = list.items[list.selected] and list.items[list.selected].item
        U.try("rules.professions", function()
            list:clear()
            screen:populateProfessionList(list)
        end)
        local pick, kept = 1, false
        for i, row in ipairs(list.items) do
            if was ~= nil and row.item == was then pick, kept = i, true end
        end
        list.selected = pick
        -- The profession they had is gone: the first on the list is theirs
        -- now, and the screen has to hear it, or the points are wrong.
        if not kept and list.items[pick] and screen.onSelectProf then
            U.try("rules.selectProf", function() screen:onSelectProf(list.items[pick].item) end)
        end
    end
    U.log("creation: the server's rules applied to the trait and profession lists")
    return true
end

--- Wraps vanilla's three moments. Safe to call more than once.
function CR.wrap()
    local prof = rawget(_G, "CharacterCreationProfession")
    if type(prof) ~= "table" or prof.TREK_rules then return prof ~= nil end

    local baseEnabled = prof.isTraitEnabled
    if type(baseEnabled) == "function" then
        prof.isTraitEnabled = function(self, trait)
            if not CR.traitShown(trait) then return false end
            return baseEnabled(self, trait)
        end
    end

    local basePopulate = prof.populateProfessionList
    if type(basePopulate) == "function" then
        prof.populateProfessionList = function(self, list)
            basePopulate(self, list)
            CR.prune(list)
        end
    end

    local baseVisible = prof.setVisible
    if type(baseVisible) == "function" then
        prof.setVisible = function(self, visible, joypadData)
            if visible then U.try("rules.refresh", CR.refresh, self) end
            return baseVisible(self, visible, joypadData)
        end
    end

    prof.TREK_rules = true
    return true
end

CR.wrap()
Events.OnGameBoot.Add(CR.wrap)

return CR
