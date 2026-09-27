--[[ Shuttlecraft -- Starfleet machines installed in the world (INSTALLATIONS.md).

    A replicator, a Doctor's station and the warp core that powers them, put
    down by a player anywhere with a floor: a farmhouse, a gun shop. This is
    the part both sides share -- the registry, and the questions the
    existing machines ask of it:

      * is this position at a replicator / the Doctor's station / a core?
      * which core serves this position? (its power store, pool "i<id>")

    **The registry is the server's.** `TREK_Installations` global mod data,
    written only by TREK_InstallationsServer, published whole to every client
    and stored there on receipt (the replicator's patterns' handshake). A
    client reads it to draw menus; the server reads its own to decide.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local IN = {}
TREK.Installations = IN

IN.Key = "TREK_Installations"
IN.TAG = "inst"
-- A core serves what is within this many squares across ...
IN.Range = 25
-- ... and this many storeys up or down: a core in the basement runs the
-- replicator in the kitchen.
IN.Levels = 3

-- The kits, and the machine each one installs.
IN.Kits = {
    replicator = "TrekShuttle.TrekReplicatorKit",
    emh_station = "TrekShuttle.TrekEMHKit",
    warp_core = "TrekShuttle.TrekWarpCoreKit",
}

-- The machines' tiles (trek_adirondack_02, tools/adirondack_objects.py), by
-- the wall they back onto; `tests/test_assets.py` checks these against the
-- furniture sheet's own index. The core is two by two and faces one way:
-- { dx, dy, sprite } per square.
IN.Sprites = {
    replicator = { W = { { 0, 0, "trek_adirondack_02_158" } }, N = { { 0, 0, "trek_adirondack_02_159" } } },
    emh_station = { W = { { 0, 0, "trek_adirondack_02_160" } }, N = { { 0, 0, "trek_adirondack_02_161" } } },
    warp_core = { W = { { 0, 0, "trek_adirondack_02_162" }, { 0, 1, "trek_adirondack_02_163" },
                        { 1, 0, "trek_adirondack_02_164" }, { 1, 1, "trek_adirondack_02_165" } } },
}

--- The registry: { next, cores = { [id] = core }, machines = { [id] = m } }.
--- Keys are strings, because a Lua table with number keys that has been
--- through ModData.transmit comes back with them as strings on a client.
function IN.state()
    local s = ModData.getOrCreate(IN.Key)
    s.next = s.next or 1
    s.cores = s.cores or {}
    s.machines = s.machines or {}
    return s
end

--- The squares a machine covers: { { x, y }, ... }.
function IN.squares(m)
    local out = {}
    local set = IN.Sprites[m.kind] and IN.Sprites[m.kind][m.facing or "W"]
    for _, t in ipairs(set or { { 0, 0 } }) do
        table.insert(out, { m.x + t[1], m.y + t[2] })
    end
    return out
end

--- The middle of a machine, for distances.
function IN.centre(m)
    if m.kind == "warp_core" then return m.x + 1, m.y + 1 end
    return m.x + 0.5, m.y + 0.5
end

local function levelOk(a, b)
    return math.abs(math.floor(a or 0) - math.floor(b or 0)) <= IN.Levels
end

--- True on a square of ours that has its own machines: the shuttle's cabin,
--- the Adirondack, the field station. Nothing is installed there, and
--- nothing there is served by an installation.
function IN.isOurs(x, y, z)
    if U.isAboard(x, y, z) then return true end
    return TREK.Adirondack ~= nil and TREK.Adirondack.locate(x, y, z) ~= nil
end

---------------------------------------------------------------------------
-- Which core serves a position
---------------------------------------------------------------------------
--- The nearest core within reach of x, y, z: id and its record, or nil.
function IN.coreFor(x, y, z)
    if not x or not y or IN.isOurs(x, y, z) then return nil end
    local best, bestId, bd = nil, nil, nil
    local r2 = IN.Range * IN.Range
    for id, m in pairs(IN.state().machines) do
        if m.kind == "warp_core" and levelOk(m.z, z) then
            local cx, cy = IN.centre(m)
            local d = U.dist2(x, y, cx, cy)
            if d <= r2 and (not bd or d < bd) then best, bestId, bd = m, id, d end
        end
    end
    return bestId, best
end

function IN.pool(id) return "i" .. tostring(id) end

--- The core id a pool names, or nil for a pool that is not an installation's.
function IN.idOfPool(pool)
    if type(pool) ~= "string" or pool:sub(1, 1) ~= "i" then return nil end
    return pool:sub(2)
end

--- The power store of an installation's pool: the core's own record, which
--- carries `power`, `crystals` and `dark` as the ship's store does.
function IN.box(pool)
    local id = IN.idOfPool(pool)
    local m = id and IN.state().machines[tostring(id)]
    if m and m.kind == "warp_core" then return m end
    return nil
end

local function pos(player)
    local x = U.try("in.px", function() return player:getX() end)
    local y = U.try("in.py", function() return player:getY() end)
    local z = U.try("in.pz", function() return player:getZ() end)
    return x, y, z
end

--- The pool of the installation a player stands in reach of, or nil.
function IN.placeOf(player)
    if not player then return nil end
    local x, y, z = pos(player)
    local id = IN.coreFor(x, y, z)
    return id and IN.pool(id) or nil
end

---------------------------------------------------------------------------
-- Standing at, clicking on
---------------------------------------------------------------------------
--- True when x, y, z is within `range` of an installed machine of this kind.
function IN.nearMachine(kind, x, y, z, range)
    if not x or not y then return false end
    local r2 = range * range
    for _, m in pairs(IN.state().machines) do
        if m.kind == kind and math.floor(m.z) == math.floor(z or 0) then
            for _, sq in ipairs(IN.squares(m)) do
                if U.dist2(x, y, sq[1] + 0.5, sq[2] + 0.5) <= r2 then return true end
            end
        end
    end
    return false
end

--- The machine whose square, or a square `margin` round it, was clicked:
--- id and record, or nil. A tall model is clicked at its feet or in front.
function IN.clickedMachine(kind, x, y, z, margin)
    if not x or not y then return nil end
    x, y = math.floor(x), math.floor(y)
    margin = margin or 1
    for id, m in pairs(IN.state().machines) do
        if (kind == nil or m.kind == kind) and math.floor(m.z) == math.floor(z or 0) then
            for _, sq in ipairs(IN.squares(m)) do
                if math.abs(x - sq[1]) <= margin and math.abs(y - sq[2]) <= margin then
                    return id, m
                end
            end
        end
    end
    return nil
end

--- The machine of any kind a player stands next to, for Dismantle.
function IN.machineBeside(player, x, y, z)
    local id, m = IN.clickedMachine(nil, x, y, z, 1)
    if not id then return nil end
    local px, py, pz = pos(player)
    if not px or math.floor(pz) ~= math.floor(m.z) then return nil end
    for _, sq in ipairs(IN.squares(m)) do
        if U.dist2(px, py, sq[1] + 0.5, sq[2] + 0.5) <= 2.5 * 2.5 then return id, m end
    end
    return nil
end

--- True when a player is at an installed machine of this kind that no core
--- is in reach of: installed, and dark. Such a machine must refuse -- served
--- by nothing, it would otherwise bill the shuttle.
function IN.orphaned(player, kind, range)
    if not player then return false end
    local x, y, z = pos(player)
    if not x or IN.isOurs(x, y, z) then return false end
    return IN.nearMachine(kind, x, y, z, range) and IN.placeOf(player) == nil
end

--- True when a player is anywhere a machine of this kind is installed near
--- enough to right-click: the menus' own gate.
function IN.near(player, kind, range)
    if not player then return false end
    local x, y, z = pos(player)
    return x ~= nil and IN.nearMachine(kind, x, y, z, range or 6)
end

---------------------------------------------------------------------------
-- A client's copy
---------------------------------------------------------------------------
Events.OnInitGlobalModData.Add(function()
    if not isClient() then return end
    U.try("in.request", function() ModData.request(IN.Key) end)
end)

Events.OnReceiveGlobalModData.Add(function(key, data)
    if key ~= IN.Key then return end
    if not isClient() then return end
    if type(data) ~= "table" then return end
    ModData.add(key, data)
end)

return IN
