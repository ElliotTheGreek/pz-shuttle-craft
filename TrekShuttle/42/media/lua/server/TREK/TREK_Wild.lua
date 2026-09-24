--[[ Shuttlecraft -- dilithium in the wild.

    Crystals lie on the ground out in the county: in the fields and the woods,
    on the dirt and the grass, and never in town. The tricorder finds them out
    to twenty tiles, so a crew who walk the countryside with one in hand will
    find a crystal every so often, and a crew who search shops will not.

    **Why, in the fiction** (LORE.md 1c, "Dilithium in his ground"): the
    Douwd who made this world, Tucker Gold, copied a river valley in the 1690s,
    and the copying left dilithium in the land he made. The towns grew on it
    later, by themselves, and have none. Nobody in the fiction knows this at
    the start -- the crystal's tooltip says only that it turns up in wild
    ground -- and the fragments are how anybody finds out.

    **How, in the engine.** Nothing can be placed where no player is standing
    (DEV_GUIDE, *Never build where no player is standing*), so the ground is
    seeded as players load it: every ten game minutes, the server looks at the
    plots (8x8, the engine's own chunks) around each player on foot. Whether a
    plot holds a crystal, and where in it, is decided by a hash of the plot
    and a per-world salt, so it is the same answer every time it is asked and
    a different map in every world. A plot is visited once: whether it got a
    crystal or had no natural ground to put one on, it is written down and
    never looked at again. That record is server-only mod data, never
    transmitted -- it grows as the world is explored, and DEV_GUIDE's *State
    that is transmitted whole cannot hold a list that grows* is why it is not
    in the ship state.

    Sandbox `TrekShuttle.WildDilithium`: Plentiful (the default), Scarce, or
    None. Authority only.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local Wild = {}
TREK.Wild = Wild

--- The plots-per-crystal the server owner chose, or nil for none.
function Wild.oneIn()
    local ok, v = pcall(function()
        return SandboxVars.TrekShuttle and SandboxVars.TrekShuttle.WildDilithium
    end)
    v = ok and tonumber(v) or nil
    if v == C.WildNone then return nil end
    if v == C.WildScarce then return C.WildScarceOneIn end
    return C.WildPlentifulOneIn
end

--- The store: a salt for this world, and every plot already visited.
function Wild.store()
    local d = ModData.getOrCreate(C.WildKey)
    d.visited = d.visited or {}
    if type(d.salt) ~= "number" then
        d.salt = (U.try("wildSalt", function() return ZombRand(1000000) end) or 0) + 1
    end
    return d
end

--- A number for this plot in this world. Arithmetic only: Kahlua has no
--- bitwise operators, and every product here stays well inside the 2^53 a
--- double holds exactly.
local function hash(px, py, salt)
    local h = (px * 73856093 + py * 19349663 + salt * 83492791) % 2147483647
    h = (h * 48271) % 2147483647
    h = (h * 48271) % 2147483647
    return h
end

--- True for ground the Douwd made: grass, dirt, sand and clay. Not water
--- (blends_natural_02), not a road, not a floor anybody built.
local function wildGround(sq)
    local name = U.try("wildFloor", function()
        local f = sq:getFloor()
        return f and f:getSprite():getName()
    end)
    if type(name) ~= "string" then return false end
    if name:sub(1, 18) ~= "blends_natural_01_"
            and name:sub(1, 27) ~= "floors_exterior_natural_01_" then
        return false
    end
    return U.try("wildClear", function()
        return not sq:isSolid() and not sq:isSolidTrans()
    end) == true
end

--- Visits one plot. Returns "placed", "none" (no crystal here, or nowhere
--- natural to put it), or nil when the plot is not loaded yet.
function Wild.visit(px, py, oneIn)
    local d = Wild.store()
    local key = px .. "," .. py
    if d.visited[key] then return "none" end
    local x0, y0 = px * C.WildPlot, py * C.WildPlot
    if not (U.chunkLoaded(x0, y0, 0)
            and U.chunkLoaded(x0 + C.WildPlot - 1, y0 + C.WildPlot - 1, 0)) then
        return nil
    end
    -- The cabin's own cell, and anywhere near it, is not the county.
    if U.isInterior(x0, y0) then
        d.visited[key] = true
        return "none"
    end

    local h = hash(px, py, d.salt)
    d.visited[key] = true
    if h % oneIn ~= 0 then return "none" end

    -- Where in the plot: start at a square the hash picks, and take the
    -- first natural one from there. A plot of road and pavement has none,
    -- which is why the towns never do.
    local n = C.WildPlot * C.WildPlot
    local start = math.floor(h / oneIn) % n
    for i = 0, n - 1 do
        local k = (start + i) % n
        local x, y = x0 + k % C.WildPlot, y0 + math.floor(k / C.WildPlot)
        local sq = U.square(x, y, 0, false)
        if sq and wildGround(sq) then
            local item = U.try("wildCrystal", function()
                return sq:AddWorldInventoryItem(C.DilithiumItem, 0.5, 0.5, 0.0)
            end)
            if item then
                d.placed = (d.placed or 0) + 1
                U.log("wild: a dilithium crystal lies at %d,%d (%d in this world)",
                      x, y, d.placed)
                return "placed"
            end
            U.log("WARN wild: a crystal could not be made at %d,%d", x, y)
            return "none"
        end
    end
    return "none"
end

--- Every plot within C.WildScanRadius of every player on foot.
function Wild.service()
    local oneIn = Wild.oneIn()
    if not oneIn then return 0 end
    local placed = 0
    local reach = math.floor(C.WildScanRadius / C.WildPlot)
    for _, p in ipairs(U.players()) do
        local ok, px, py = pcall(function()
            if p:isDead() or U.isInteriorPlayer(p) then return nil end
            return math.floor(p:getX() / C.WildPlot), math.floor(p:getY() / C.WildPlot)
        end)
        if ok and px then
            for dx = -reach, reach do
                for dy = -reach, reach do
                    if Wild.visit(px + dx, py + dy, oneIn) == "placed" then
                        placed = placed + 1
                    end
                end
            end
        end
    end
    return placed
end

Events.EveryTenMinutes.Add(function()
    U.try("wildService", Wild.service)
end)

return Wild
