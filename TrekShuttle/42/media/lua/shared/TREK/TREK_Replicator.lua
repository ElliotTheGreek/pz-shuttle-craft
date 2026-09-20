--[[ Shuttlecraft -- the replicator: the catalogue, the patterns, the reserve.

    Everything both sides need to agree about. The panel (client) draws from
    it, the handlers (server) validate against it, and neither has its own
    copy of what a thing costs or whether the ship knows how to make it.

    Three parts:

      the catalogue   every item in the game, read out of the engine's own
                      script list rather than hand-written, so it covers
                      vanilla, future patches and other people's mods with no
                      maintenance at all;
      the patterns    what the ship has scanned, and may therefore make. Its
                      own mod data key, not the ship state -- see below;
      the reserve     energy, which is ship state: one number, spent by the
                      server and drawn by every client.

    ---------------------------------------------------------------------
    The catalogue, and the filter that is not optional
    ---------------------------------------------------------------------
    `getAllItems()` is a LuaManager$GlobalObject static returning an
    ArrayList<Item> of every item script loaded. The filter is vanilla's own:

        if not item:getObsolete() and not item:isHidden() then ... end

    **An obsolete item is still in the scripts and still returns nil from
    instanceItem.** It has a name, it has a category, and it makes nothing --
    which is "present, drawn and inert", the shape this mod has paid for six
    times (DEV_GUIDE.md, "The jar is not the API"). Without that line the list
    fills with entries that look exactly like working ones.

    Three call sites were checked rather than one, and the difference matters:
    `ISItemsListViewer.lua:42` is the obvious one and it lives under
    **AdminPanel/**, which by this project's own rules is not evidence at all
    -- an admin-only file proves a method works for admins. The two that do
    count are `shared/Foraging/forageSystem.lua:679` and
    `client/ISUI/ISLiteratureUI.lua:363` (via getScriptManager()), both of
    which any player reaches.

    ---------------------------------------------------------------------
    Why the patterns are not in the ship state
    ---------------------------------------------------------------------
    TREK_Ship.commit() transmits the whole ship table to every client on every
    change, and the ship changes constantly: S.serviceVehicle commits each
    time the shuttle is driven a square. A crew who have scanned two thousand
    items would push two thousand strings through every one of those.

    So the pattern set has its own key (C.PatternKey) and is transmitted only
    when a pattern is actually learned. The ship state carries the reserve,
    which is one number. REPLICATOR.md called this "probably fine and not
    something to assume"; it is not fine, and this is the assumption it was
    worth not making.

    ---------------------------------------------------------------------
    What the ship already knows
    ---------------------------------------------------------------------
    Every item this mod declares is a pattern from the day the world is made.
    A Starfleet shuttle carrying a replicator it cannot make a hypospray with
    would be a strange ship, and it means the mod's own gear -- which no
    existing save will ever be issued, because new loot never reaches an old
    world -- is reachable in any save that has the replicator.

    The seeding runs on every authority start rather than once, so an item
    added to the mod later is known without a migration. It only publishes
    when something actually changed.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"
local L = require "TREK/TREK_InteriorLayout"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local R = {}
TREK.Replicator = R

---------------------------------------------------------------------------
-- Where it stands
---------------------------------------------------------------------------
local spot = nil

--- The cabin offsets of the replicator's berth, out of the authored layout.
--- Nil, once, with a warning if nothing carries the tag -- which would mean
--- the fixture had been renamed in the map editor and nothing else would say.
function R.spot()
    if spot then return spot[1], spot[2] end
    for _, entry in ipairs(L.tiles) do
        if entry.tag == C.ReplicatorTag then
            spot = { entry.x, entry.y }
            return spot[1], spot[2]
        end
    end
    U.warnOnce("replicator:spot",
               "no layout entry is tagged " .. tostring(C.ReplicatorTag) ..
               "; the replicator has nowhere to stand")
    return nil
end

--- True when this position is close enough to work the replicator.
---
--- Shared so that the menu greys itself out and the server refuses for the
--- same reason, measured the same way. The server measures it against its own
--- copy of where the player is: a client is a request, never a fact.
function R.inReach(x, y, z)
    if not x or not y then return false end
    local ox, oy = R.spot()
    if not ox then return false end
    if not U.isAboard(x, y, z) then return false end
    local rx, ry = U.at(ox, oy)
    return U.dist2(x, y, rx + 0.5, ry + 0.5) <= C.ReplicatorRange * C.ReplicatorRange
end

function R.inReachOf(player)
    if not player then return false end
    local x = U.try("rep.px", function() return player:getX() end)
    local y = U.try("rep.py", function() return player:getY() end)
    local z = U.try("rep.pz", function() return player:getZ() end)
    if not x or not y then return false end
    return R.inReach(x, y, z)
end

---------------------------------------------------------------------------
-- The sandbox setting
---------------------------------------------------------------------------
--- 1 patterns and energy, 2 unrestricted, 3 off.
---
--- An absent table reads as *patterns*, the restrictive value. Reading a
--- missing option as "no limits" would turn the feature into a creative-mode
--- cheat in exactly the setup nobody tested.
function R.mode()
    local v = U.try("sandboxReplicator", function()
        return SandboxVars.TrekShuttle and SandboxVars.TrekShuttle.Replicator
    end)
    return tonumber(v) or C.ReplicatorPatterns
end

function R.isOff()      return R.mode() == C.ReplicatorOff end
function R.isFree()     return R.mode() == C.ReplicatorUnrestricted end

---------------------------------------------------------------------------
-- The catalogue
---------------------------------------------------------------------------
local rows = nil          -- array, sorted by display name
local byId = nil          -- full type -> row
local categories = nil    -- sorted distinct display categories

--- What one item costs to make, in reserve units.
---
--- Weight, because it is the one number every item in the game has and it is
--- roughly what the thing *is*. Rounded, floored at 1 so nothing is free, and
--- capped so a 60 kg generator does not ask for six hundred.
function R.costOf(weight)
    local n = math.floor(C.ReplicatorBaseCost + (weight or 0) * C.ReplicatorWeightCost + 0.5)
    if n < 1 then n = 1 end
    if n > C.ReplicatorMaxCost then n = C.ReplicatorMaxCost end
    return n
end

--- True when an item may appear in the catalogue at all.
local function admissible(id, module, obsolete, hidden)
    if not id or id == "" then return false end
    if obsolete or hidden then return false end
    if module and C.ReplicatorSkipModules[module] then return false end
    if C.ReplicatorBlocked[id] then return false end
    return true
end

--- Builds the catalogue once per process.
---
--- **U.batch, not U.try**, for everything inside the loop: this walks a few
--- thousand items, and a method name that does not exist throws out of Java
--- with a full stack trace *per call*. That is thousands of dumps, which
--- locks the game hard enough to look like a crash.
local function build()
    if rows then return end
    rows, byId, categories = {}, {}, {}

    local list = U.try("getAllItems", function() return getAllItems() end)
    local n = list and U.try("catalogue.size", function() return list:size() end) or 0
    if not list or n == 0 then
        U.warnOnce("replicator:catalogue",
                   "getAllItems() answered nothing; the replicator has no catalogue")
        return
    end

    local join = U.batch("replicator.readItem")
    local seenCategory = {}
    for i = 0, n - 1 do
        join(function()
            local item = list:get(i)
            if not item then return end
            local id = item:getFullName()
            if not admissible(id, item:getModuleName(),
                              item:getObsolete(), item:isHidden()) then
                return
            end
            local name = item:getDisplayName() or id
            local category = item:getDisplayCategory() or "Item"
            local row = {
                id = id,
                name = name,
                -- Lowercased once, here, so that filtering thousands of rows
                -- on every keystroke is a string.find and nothing else.
                lower = string.lower(name .. " " .. id),
                category = category,
                module = item:getModuleName(),
                weight = item:getActualWeight() or 0,
                -- May be nil, and legitimately: the catalogue contains other
                -- people's mods, and nothing may assume an icon exists.
                tex = item:getNormalTexture(),
            }
            row.cost = R.costOf(row.weight)
            table.insert(rows, row)
            byId[id] = row
            if not seenCategory[category] then
                seenCategory[category] = true
                table.insert(categories, category)
            end
        end)
    end

    table.sort(rows, function(a, b) return a.name < b.name end)
    table.sort(categories)
    U.log("replicator: catalogue of %d item(s) in %d categor(ies)",
          #rows, #categories)
end

--- Every item the replicator could ever make, sorted by display name.
function R.catalogue()
    build()
    return rows
end

function R.categories()
    build()
    return categories
end

--- One row, or nil. The server looks every id a client sends up in here
--- rather than handing it to instanceItem blind.
function R.row(id)
    if type(id) ~= "string" then return nil end
    build()
    return byId[id]
end

--- Throws the catalogue away, so the next reader rebuilds it. For the tests
--- and for a console command; nothing in the game calls it.
function R.forget()
    rows, byId, categories = nil, nil, nil
end

---------------------------------------------------------------------------
-- Patterns
---------------------------------------------------------------------------
--- The pattern set: { known = { [fullType] = true }, count = n }.
---
--- On a client this is whatever the server last sent. It is never written
--- there -- R.learn refuses on a client, the way Ship.commit does.
function R.store()
    local data = ModData.getOrCreate(C.PatternKey)
    data.known = data.known or {}
    return data
end

function R.knows(id)
    if R.isFree() then return true end
    return R.store().known[id] == true
end

--- Marks a pattern known. Authority only. Returns true when it is new.
function R.learn(id)
    if isClient() then
        U.warnOnce("patternOnClient", "a client tried to store a pattern; ignored")
        return false
    end
    if not R.row(id) then return false end
    local data = R.store()
    if data.known[id] then return false end
    data.known[id] = true
    data.count = (data.count or 0) + 1
    return true
end

--- Publishes the pattern set. Authority only, and only when it changed --
--- this is the whole reason the patterns are not in the ship state.
function R.publish()
    if isClient() then return end
    if isServer() then
        U.try("transmitPatterns", function() ModData.transmit(C.PatternKey) end)
    end
end

--- How many patterns the ship holds.
function R.patternCount()
    local data = R.store()
    if data.count then return data.count end
    local n = 0
    for _ in pairs(data.known) do n = n + 1 end
    data.count = n
    return n
end

--- Every item this mod declares is a pattern from the start: a Starfleet
--- shuttle knows its own stores. Runs on every authority start rather than
--- once, so an item added to the mod later needs no migration.
---
--- Returns how many were new, so the caller only publishes when it matters.
function R.seedDefaults()
    if isClient() then return 0 end
    local added = 0
    for _, row in ipairs(R.catalogue()) do
        if row.module == "TrekShuttle" and R.learn(row.id) then
            added = added + 1
        end
    end
    if added > 0 then
        U.log("replicator: the ship knows %d more of its own patterns (%d in all)",
              added, R.patternCount())
    end
    return added
end

---------------------------------------------------------------------------
-- The reserve
---------------------------------------------------------------------------
function R.energy()
    local e = U.state().repEnergy
    if type(e) ~= "number" then return C.ReplicatorEnergyMax end
    if e < 0 then return 0 end
    if e > C.ReplicatorEnergyMax then return C.ReplicatorEnergyMax end
    return e
end

--- Spends from the reserve. Authority only; the caller commits.
function R.spend(n)
    if isClient() then return false end
    local s = U.state()
    local left = R.energy() - (n or 0)
    if left < 0 then left = 0 end
    s.repEnergy = left
    return true
end

--- What comes back every ten game minutes. Returns true when the number
--- changed, so the caller only commits -- and only transmits -- when it did.
function R.regen()
    if isClient() then return false end
    local s = U.state()
    local now = R.energy()
    if now >= C.ReplicatorEnergyMax then
        -- Written back even so: a save from before the reserve existed, or one
        -- somebody has edited, should not sit at a number above the ceiling.
        if s.repEnergy ~= C.ReplicatorEnergyMax then
            s.repEnergy = C.ReplicatorEnergyMax
            return true
        end
        return false
    end
    s.repEnergy = math.min(C.ReplicatorEnergyMax, now + C.ReplicatorRegen)
    return true
end

--- What `count` of this row costs. Free when the sandbox says so.
function R.cost(row, count)
    if not row then return 0 end
    if R.isFree() then return 0 end
    return row.cost * (count or 1)
end

--- True when `count` is one of the quantities the panel offers. The server
--- checks it too: the number arrives from a client.
function R.isQuantity(count)
    for _, q in ipairs(C.ReplicatorQuantities) do
        if q == count then return true end
    end
    return false
end

---------------------------------------------------------------------------
-- A client's copy of the patterns
---------------------------------------------------------------------------
-- The same handshake TREK_Ship uses: a client asks when its world loads, and
-- stores what arrives -- receiving does not store it by itself. The server
-- never takes a client's copy.
Events.OnInitGlobalModData.Add(function()
    if not isClient() then return end
    U.try("requestPatterns", function() ModData.request(C.PatternKey) end)
end)

Events.OnReceiveGlobalModData.Add(function(key, data)
    if key ~= C.PatternKey then return end
    if not isClient() then return end
    if type(data) ~= "table" then return end
    ModData.add(key, data)
end)

return R
