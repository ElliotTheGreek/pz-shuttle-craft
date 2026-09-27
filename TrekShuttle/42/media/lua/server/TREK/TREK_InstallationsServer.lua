--[[ Shuttlecraft -- installing and dismantling Starfleet machines (INSTALLATIONS.md).

    Everything that changes the registry or the world happens here, on a
    validated command:

      installMachine {kind, x, y, z}   the kit is taken from the server's own
                                       copy of the player's inventory, counted;
                                       the squares are checked; the machine is
                                       placed, tagged `inst`, and sent
      dismantleMachine {id}            in reach on the server's own copy of the
                                       player; the machine comes off, and the
                                       kit -- and a core's crystals -- go into
                                       their inventory, counted

    Using a machine is the ship's own handlers', unchanged: TREK_Net serves the
    command under P.poolOf(player), which names the nearest core's store.

    **The registry is published whenever it changes**, and a core's numbers
    change inside the ship's handlers, which commit the ship's state and not
    this. So once a second the server compares every core's power, spares and
    dark flag with what it last sent, and publishes when they differ.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Installations"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local IN = TREK.Installations

local IS = {}
TREK.InstallationsServer = IS

-- How far from the target square a player may stand to install.
IS.Reach = 2.6

local function nameOf(p)
    return U.try("in.name", function() return p:getUsername() end) or "?"
end

local function alive(p)
    return p ~= nil and U.try("in.dead", function() return p:isDead() end) == false
end

local function deny(player, why)
    Net.toClient(player, "denied", { why = why })
end

local lastSent = nil

--- Sends the registry to every client. Authority only.
function IS.publish()
    lastSent = IS.signature()
    if isServer() then
        U.try("in.transmit", function() ModData.transmit(IN.Key) end)
    end
end

--- What a client needs to be told about: every machine, and every core's
--- numbers as a client reads them.
function IS.signature()
    local parts = {}
    for id, m in pairs(IN.state().machines) do
        table.insert(parts, id .. m.kind .. m.x .. "," .. m.y .. "," .. m.z .. ":"
                     .. math.floor(m.power or 0) .. "/" .. (m.crystals or 0) .. "/" .. tostring(m.dark))
    end
    table.sort(parts)
    return table.concat(parts, ";")
end

---------------------------------------------------------------------------
-- The squares
---------------------------------------------------------------------------
local function tagOf(o)
    return U.try("in.tag", function() return o:getModData().TREK end)
end

--- Why a square will not take a machine, or nil when it will.
function IS.checkSquare(sq, player)
    if not sq then return "instBlocked" end
    local x, y, z = sq:getX(), sq:getY(), sq:getZ()
    if IN.isOurs(x, y, z) then return "instOurs" end
    if not U.try("in.floor", function() return sq:getFloor() end) then return "instBlocked" end
    if U.try("in.free", function() return sq:isFree(false) end) ~= true then return "instBlocked" end
    local ours = false
    U.eachObject(sq, function(o)
        if tagOf(o) == IN.TAG then ours = true return false end
    end)
    if ours then return "instBlocked" end
    -- Somebody else's safehouse is somebody else's house (MULTIPLAYER.md,
    -- the medical set's lock rule): it answers only when the named player
    -- is not a member.
    local other = U.try("in.safehouse", function()
        return SafeHouse.isSafeHouse(sq, nameOf(player), true)
    end)
    if other then return "instSafehouse" end
    return nil
end

--- The wall a one-square machine backs onto: north, else west, else west.
local function facingFor(sq)
    local north = U.try("in.wallN", function() return sq:getWall(true) end)
    if north then return "N" end
    return "W"
end

--- One kit the player is really carrying, and how many.
local function carriedKit(player, fullType)
    local inv = U.try("in.inv", function() return player:getInventory() end)
    if not inv then return nil, 0 end
    local bare = fullType:match("%.(.+)$")
    local list = U.try("in.kits", function() return inv:getAllTypeRecurse(bare) end)
    local first, n = nil, 0
    if list then
        for i = 0, list:size() - 1 do
            local it = list:get(i)
            if it and it:getFullType() == fullType then
                n = n + 1
                first = first or it
            end
        end
    end
    return first, n
end

local function placeTile(sq, sprite, id)
    local obj = U.try("in.new", function() return IsoObject.new(sq, sprite, "") end)
    if not obj then return false end
    U.try("in.tagNew", function()
        local md = obj:getModData()
        md.TREK = IN.TAG
        md.TREKInst = id
    end)
    return U.try("in.add", function()
        sq:transmitAddObjectToSquare(obj, -1)
        return true
    end) == true
end

--- The square the Doctor stands on in front of a station, and his turn.
local function doctorSpot(m)
    local sprite = IN.Sprites.emh_station[m.facing][1][3]
    local face = U.try("in.face", function() return getSprite(sprite):getProperties():get("Facing") end)
    local step = ({ E = { 1, 0 }, S = { 0, 1 }, W = { -1, 0 }, N = { 0, -1 } })[face or "E"] or { 1, 0 }
    local yaw = TREK.Adirondack and TREK.Adirondack.DoctorYaw[face or "E"] or 0
    return m.x + step[1], m.y + step[2], yaw
end

local function placeDoctor(m)
    local x, y, yaw = doctorSpot(m)
    local sq = U.square(x, y, m.z, false)
    if not sq then return false end
    local item = U.try("in.doctor", function() return sq:AddWorldInventoryItem(C.EmhItem, 0.5, 0.5, 0.0) end)
    if not item then return false end
    U.try("in.doctorTurn", function()
        item:setWorldXRotation(0)
        item:setWorldYRotation(0)
        item:setWorldZRotation(yaw)
    end)
    return true
end

local function removeDoctor(m)
    local x, y = doctorSpot(m)
    local sq = U.square(x, y, m.z, false)
    if not sq then return 0 end
    local n = 0
    U.try("in.doctorRemove", function()
        local list = sq:getWorldObjects()
        local doomed = {}
        for i = 0, list:size() - 1 do
            local w = list:get(i)
            local it = w and w:getItem()
            if it and it:getFullType() == C.EmhItem then table.insert(doomed, w) end
        end
        for _, w in ipairs(doomed) do
            sq:transmitRemoveItemFromSquare(w)
            n = n + 1
        end
    end)
    return n
end

---------------------------------------------------------------------------
-- Installing
---------------------------------------------------------------------------
Net.onServer("installMachine", function(player, args)
    if not alive(player) then return end
    local kind = args.kind
    local kit = IN.Kits[kind]
    if not kit then return end
    local x, y, z = tonumber(args.x), tonumber(args.y), tonumber(args.z)
    if not x or not y or not z then return end
    x, y, z = math.floor(x), math.floor(y), math.floor(z)

    -- Where they are, on this machine's copy of them.
    local px = U.try("in.px", function() return player:getX() end)
    local py = U.try("in.py", function() return player:getY() end)
    local pz = U.try("in.pz", function() return player:getZ() end)
    if not px or math.floor(pz) ~= z or U.dist2(px, py, x + 0.5, y + 0.5) > IS.Reach * IS.Reach then
        deny(player, "instFar")
        return
    end
    if IN.isOurs(px, py, pz) then
        deny(player, "instOurs")
        return
    end

    local facing = kind == "warp_core" and "W" or nil
    local shape = IN.Sprites[kind]
    local squares = {}
    for _, t in ipairs(shape[facing or "W"]) do
        local sq = U.chunkLoaded(x + t[1], y + t[2], z) and U.square(x + t[1], y + t[2], z, false) or nil
        local why = IS.checkSquare(sq, player)
        if why then
            deny(player, why)
            return
        end
        table.insert(squares, sq)
    end
    facing = facing or facingFor(squares[1])

    local item, before = carriedKit(player, kit)
    if not item then
        deny(player, "instNoKit")
        return
    end
    local inv = player:getInventory()
    U.try("in.takeKit", function() inv:Remove(item) end)
    local _, after = carriedKit(player, kit)
    if after >= before then
        U.log("WARN installations: %s's kit would not come out of their inventory", nameOf(player))
        deny(player, "instNoKit")
        return
    end
    if isServer() then
        U.try("in.syncInv", function() sendRemoveItemFromContainer(inv, item) end)
    end

    local s = IN.state()
    local id = tostring(s.next)
    s.next = s.next + 1
    local m = { kind = kind, x = x, y = y, z = z, facing = facing, owner = nameOf(player) }
    if kind == "warp_core" then
        -- Empty: dilithium goes in by hand, as the shuttle's does.
        m.power, m.crystals, m.dark = 0, 0, true
    end
    s.machines[id] = m
    for i, t in ipairs(shape[facing]) do
        placeTile(squares[i], t[3], id)
    end
    if kind == "emh_station" then placeDoctor(m) end
    IS.publish()
    Net.toClient(player, "machineInstalled", { kind = kind, id = id,
                                              core = IN.coreFor(x, y, z) ~= nil or kind == "warp_core" })
    U.log("installations: %s installed a %s at %d,%d,%d (id %s)", nameOf(player), kind, x, y, z, id)
end)

---------------------------------------------------------------------------
-- Dismantling
---------------------------------------------------------------------------
Net.onServer("dismantleMachine", function(player, args)
    if not alive(player) then return end
    local id = tostring(args.id or "")
    local s = IN.state()
    local m = s.machines[id]
    if not m then return end
    -- In reach of one of its squares, on this machine's copy of the player.
    local px = U.try("in.px", function() return player:getX() end)
    local py = U.try("in.py", function() return player:getY() end)
    local pz = U.try("in.pz", function() return player:getZ() end)
    local near = false
    if px and math.floor(pz) == math.floor(m.z) then
        for _, sq in ipairs(IN.squares(m)) do
            if U.dist2(px, py, sq[1] + 0.5, sq[2] + 0.5) <= IS.Reach * IS.Reach then near = true end
        end
    end
    if not near then
        deny(player, "instFar")
        return
    end

    -- The kit first, counted: a full inventory keeps the machine standing.
    local made = TREK.Server.materialise(player, IN.Kits[m.kind], 1)
    if made < 1 then
        deny(player, "coreFull")
        return
    end
    -- A core's spare crystals come back with it. The one burning in the
    -- chamber is spent, as it would be aboard.
    local crystals = m.kind == "warp_core" and (m.crystals or 0) or 0
    local back = crystals > 0 and TREK.Server.materialise(player, C.DilithiumItem, crystals) or 0
    if back < crystals then
        U.log("WARN installations: %d of %d crystals did not fit; left on the floor", crystals - back, crystals)
        local sq = U.square(math.floor(px), math.floor(py), math.floor(pz), false)
        for _ = 1, crystals - back do
            U.try("in.dropCrystal", function() sq:AddWorldInventoryItem(C.DilithiumItem, 0.5, 0.5, 0.0) end)
        end
    end

    for _, xy in ipairs(IN.squares(m)) do
        local sq = U.square(xy[1], xy[2], m.z, false)
        if sq then
            local doomed = {}
            U.eachObject(sq, function(o)
                local md = U.try("in.md", function() return o:getModData() end)
                if md and md.TREK == IN.TAG and tostring(md.TREKInst) == id then table.insert(doomed, o) end
            end)
            for _, o in ipairs(doomed) do
                U.try("in.remove", function() sq:transmitRemoveItemFromSquare(o) end)
            end
        end
    end
    if m.kind == "emh_station" then removeDoctor(m) end
    s.machines[id] = nil
    IS.publish()
    Net.toClient(player, "machineDismantled", { kind = m.kind, crystals = crystals })
    U.log("installations: %s dismantled the %s at %d,%d,%d (id %s)", nameOf(player), m.kind, m.x, m.y, m.z, id)
end)

---------------------------------------------------------------------------
-- Keeping them standing, and everybody told
---------------------------------------------------------------------------
--- Puts back any tile of an installed machine that has gone -- the registry
--- is the truth, and a machine is taken away by dismantling it, not by a
--- sledgehammer -- wherever its square is loaded.
function IS.service()
    local placed = 0
    for id, m in pairs(IN.state().machines) do
        local set = IN.Sprites[m.kind] and IN.Sprites[m.kind][m.facing or "W"]
        for _, t in ipairs(set or {}) do
            local x, y = m.x + t[1], m.y + t[2]
            if U.chunkLoaded(x, y, m.z) then
                local sq = U.square(x, y, m.z, false)
                if sq and not U.findSprite(sq, t[3]) then
                    if placeTile(sq, t[3], id) then placed = placed + 1 end
                end
            end
        end
    end
    if placed > 0 then U.log("installations: %d machine tile(s) put back", placed) end
    if IS.signature() ~= lastSent then IS.publish() end
    return placed
end

local tick = 0
Events.OnTick.Add(function()
    tick = tick + 1
    if tick < 60 then return end
    tick = 0
    U.try("in.service", IS.service)
end)

return IS
