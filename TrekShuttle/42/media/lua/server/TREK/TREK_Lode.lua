--[[ Shuttlecraft -- how much dilithium a town's loot gives up (SERVERS.md,
    *Balance*).

    server/Items/TrekDilithium.lua puts the crystal into twelve of vanilla's
    loot tables, and the engine rolls it container by container: a chance
    each, so a town with three hundred tool crates held a dozen crystals and
    a crew who looted one street never went short. This file is the count
    (the author, 2026-10-12: "far more rare, like 1 to 5 for an entire town").

    The county is cut into districts C.LootDistrict squares across, about a
    town each. A district gives up a number of crystals between the sandbox's
    fewest and most, drawn once from the world's own salt, and every crystal
    the engine rolls into a container is counted against the district the
    container stands in. One past the count is taken back out before anybody
    has seen the container.

    **At the roll, as the annotated maps are** (TREK_MaroonedServer): a loot
    table is merged before the sandbox can be asked, so a weight cannot be a
    setting. ItemPickerJava.fillContainerInternal returns at once on a client
    and raises OnFillContainer as its last act, before the container's
    contents are sent to anybody, so this runs on the authority only and
    nothing has to be told.

    **The tables still decide where**, and this decides only how many: a
    crystal is found in a jeweller's case or a tool crate, as it always was.
    The first containers of a district to be rolled are the ones that keep
    theirs, which is the part of town the crew came to first.

    The record is a number for each district that has given one up, kept in
    server-only mod data and never transmitted. A crystal already in a
    container when this was installed stays there: only a roll is counted.
    Authority only.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Rules"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Rules = TREK.Rules

local Lode = {}
TREK.Lode = Lode

--- The store: a salt for this world, and what each district has given up.
function Lode.store()
    local d = ModData.getOrCreate(C.LootKey)
    d.kept = d.kept or {}
    if type(d.salt) ~= "number" then
        d.salt = (U.try("lodeSalt", function() return ZombRand(1000000) end) or 0) + 1
    end
    return d
end

--- A number for this district in this world. TREK_Wild's arithmetic: Kahlua
--- has no bitwise operators, and every product stays inside a double.
local function hash(dx, dy, salt)
    local h = (dx * 73856093 + dy * 19349663 + salt * 83492791) % 2147483647
    h = (h * 48271) % 2147483647
    h = (h * 48271) % 2147483647
    return h
end

--- The district a square is in.
function Lode.districtOf(x, y)
    return math.floor(x / C.LootDistrict), math.floor(y / C.LootDistrict)
end

--- How many crystals a district's loot gives up on this server: the same
--- answer every time it is asked, and a different map in every world. Asked
--- at each roll, so an admin who changes the setting changes what is still
--- to be found, and never what has been.
function Lode.allowance(dx, dy)
    local lo, hi = Rules.lootCrystals()
    if hi <= lo then return lo end
    return lo + hash(dx, dy, Lode.store().salt) % (hi - lo + 1)
end

--- The crystals in a container, as a list.
local function crystalsIn(container)
    local out = {}
    U.try("lodeItems", function()
        local items = container:getItems()
        for i = 0, items:size() - 1 do
            local it = items:get(i)
            if it and it:getFullType() == C.DilithiumItem then table.insert(out, it) end
        end
    end)
    return out
end

--- Where a container stands, or nil: the object it belongs to, or the square
--- the engine filled it on.
local function whereIs(container)
    return U.try("lodeWhere", function()
        local parent = container:getParent()
        local sq = parent and parent:getSquare() or container:getSourceGrid()
        if not sq then return nil end
        return { sq:getX(), sq:getY() }
    end)
end

--- The engine has just rolled a container's loot. Returns how many crystals
--- were taken back out of it.
function Lode.onFillContainer(_, _, container)
    -- The third argument is not always a container (TREK_MaroonedServer):
    -- asked by type first, which is safe on anything.
    if not container or not instanceof(container, "ItemContainer") then return 0 end
    local found = crystalsIn(container)
    if #found == 0 then return 0 end

    local at = whereIs(container)
    if not at then
        -- Nothing in the twelve tables is anywhere but in a building, so
        -- this is another mod's container. It keeps what it rolled.
        U.warnOnce("lodeNowhere", "lode: a rolled container holds dilithium and stands "
                   .. "nowhere; it is not counted against any district")
        return 0
    end

    local d = Lode.store()
    local dx, dy = Lode.districtOf(at[1], at[2])
    local key = dx .. "," .. dy
    local allowed = Lode.allowance(dx, dy)
    local kept, taken = d.kept[key] or 0, 0
    for _, item in ipairs(found) do
        if kept < allowed then
            kept = kept + 1
            U.log("lode: a dilithium crystal is in a container at %d,%d -- %d of %d for "
                  .. "district %s", at[1], at[2], kept, allowed, key)
        else
            U.try("lodeTake", function() container:Remove(item) end)
            taken = taken + 1
        end
    end
    d.kept[key] = kept

    -- Read back, as everything here is: a crystal that would not come out is
    -- one more than the server allowed, and nothing else would ever say so.
    if taken > 0 and #crystalsIn(container) ~= #found - taken then
        U.warnOnce("lodeStuck", "lode: a crystal past district " .. key .. "'s "
                   .. allowed .. " would not come out of its container")
    end
    return taken
end

Events.OnFillContainer.Add(function(room, kind, container)
    U.try("lodeFill", Lode.onFillContainer, room, kind, container)
end)

return Lode
