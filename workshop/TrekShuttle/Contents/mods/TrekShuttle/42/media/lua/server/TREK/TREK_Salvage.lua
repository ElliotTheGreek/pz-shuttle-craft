--[[ Shuttlecraft -- the mod's things in the world's loot, on a server with no
    shuttle (SERVERS.md, *Content*).

    Everything the mod issues comes out of a ship: the armoury is a locker in
    her cabin, the medical set is in her sick bay. A server that has switched
    the shuttle off (sandbox *Shuttles*) and still allows some of her things
    -- "maybe all they want is the bat'leth", the author, 2026-10-12 -- has
    nowhere for them to come from. This file is where: a container the engine
    rolls in a fitting kind of room has a small chance of one allowed thing.

    **Only while the shuttle is off.** With her on, her lockers are the
    source and the world's loot is vanilla's, as it always was.

    **At the roll, as the crystals are counted and the maps added**
    (TREK_Lode, TREK_MaroonedServer): a loot table is merged before the
    sandbox can be asked, and what is allowed is the sandbox's to say, item
    by item. ItemPickerJava.fillContainerInternal returns at once on a
    client, so this runs on the authority only, and OnFillContainer is its
    last act, before the contents are sent to anybody.

    C.Salvage says which rooms hold which things; sandbox *Items in the
    world's loot* is the chance. A thing switched off is never picked, and a
    room whose things are all switched off holds none. Authority only.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Rules"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Rules = TREK.Rules

local Salvage = {}
TREK.Salvage = Salvage

-- room name -> the things that may turn up there, built once.
local byRoom = nil

--- What a room of this name may hold, or nil.
function Salvage.poolFor(room)
    if type(room) ~= "string" then return nil end
    if not byRoom then
        byRoom = {}
        for _, place in ipairs(C.Salvage.places) do
            for _, name in ipairs(place.rooms) do byRoom[name] = place.items end
        end
    end
    return byRoom[string.lower(room)]
end

--- The things in a pool this server allows.
function Salvage.allowed(pool)
    local out = {}
    for _, id in ipairs(pool) do
        if Rules.itemAllowed(id) then table.insert(out, id) end
    end
    return out
end

--- The engine has just rolled a container's loot. Returns the id of what was
--- added to it, or nil.
function Salvage.onFillContainer(room, _, container)
    if Rules.shuttles() then return nil end
    -- The third argument is not always a container (TREK_MaroonedServer):
    -- asked by type first, which is safe on anything.
    if not container or not instanceof(container, "ItemContainer") then return nil end
    local pool = Salvage.poolFor(room)
    if not pool then return nil end
    local allowed = Salvage.allowed(pool)
    if #allowed == 0 then return nil end

    -- At no chance at all no roll is under it, so there is no test for that.
    local roll = U.try("salvageRoll", function() return ZombRand(100) end) or 100
    if roll >= Rules.itemLoot() then return nil end
    local pick = U.try("salvagePick", function() return ZombRand(#allowed) end) or 0
    local id = allowed[pick + 1] or allowed[1]

    local before = U.try("salvageBefore", function() return container:getItems():size() end) or 0
    U.try("salvageAdd", function()
        local item = instanceItem(id)
        if item then container:AddItem(item) end
    end)
    local after = U.try("salvageAfter", function() return container:getItems():size() end) or 0
    -- A full container drops what it is handed and says nothing: read back.
    if after <= before then return nil end
    U.log("salvage: %s is in a container in a %s", id, tostring(room))
    return id
end

Events.OnFillContainer.Add(function(room, kind, container)
    U.try("salvageFill", Salvage.onFillContainer, room, kind, container)
end)

return Salvage
