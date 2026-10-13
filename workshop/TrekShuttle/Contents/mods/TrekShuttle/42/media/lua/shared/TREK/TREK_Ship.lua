--[[ Shuttlecraft -- the one shared ship, and who may use it.

    One ship per world, shared by the whole crew. Its state is global mod data
    (C.StateKey), and it has exactly one writer: the authority (single player,
    or the server). Clients connected to a server hold a copy that the server
    sends them, and never edit it -- every change is a command (TREK_Net).

    How the copy stays current, per build 42's actual behaviour:

      * the authority calls Ship.commit() after any change, which transmits
        the table to every client (and does nothing in single player, where
        there is only the one table);
      * a client asks for it when its world loads, and stores what arrives
        with ModData.add -- receiving does *not* store it automatically;
      * a client never transmits it back. The server ignores anything a
        client sends that way, because accepting it would let any client
        rewrite the ship.

    Per-player facts -- where *this* player beamed up from, whether *they* are
    aboard -- are not ship state and live on the player (player mod data),
    owned by that player's client.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Rules"
require "TREK/TREK_Vehicle"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local Ship = {}
TREK.Ship = Ship

Ship.listeners = {}

--- The ship's state. Writable only where Net.isAuthority() is true; anywhere
--- else it is the latest copy the server sent.
function Ship.get()
    return U.state()
end

--- Publishes the state of the ship in hand after a change. Authority only.
function Ship.commit()
    if isClient() then
        U.warnOnce("commitOnClient", "a client tried to commit ship state; ignored")
        return
    end
    if isServer() then
        local key = U.stateKey()
        U.try("transmitShip", function() ModData.transmit(key) end)
        -- The Adirondack's store and the field station's are kept with the
        -- shared ship (TREK_Power, box): a charge to one of them made on
        -- behalf of somebody with a shuttle of their own changed *her* state.
        if U.shipNow ~= 1 and TREK.Power and TREK.Power.isRemote() then
            U.try("transmitWorld", function() ModData.transmit(C.StateKey) end)
        end
    end
    Ship.notify()
end

---------------------------------------------------------------------------
-- The fleet (SERVERS.md, personal shuttles)
---------------------------------------------------------------------------
-- Ship 1 is the shared shuttle. A server may give players one each (sandbox
-- *Personal shuttles*), and the register of whose is whose is this: its own
-- mod data key, written by the authority and sent to every client, the same
-- arrangement as the ship itself. It changes when a player is first given a
-- shuttle and never otherwise.
--
--   next              the next id to give out (2 and up; never reused)
--   byOwner[name]     that player's ship id
--   owners["<id>"]    that ship's owner. A string key: a table of numbers
--                     with a gap in it does not travel as a list.

--- The register. Readable everywhere; the authority writes it.
function Ship.fleet()
    local f = ModData.getOrCreate(C.FleetKey)
    if type(f.byOwner) ~= "table" then f.byOwner = {} end
    if type(f.owners) ~= "table" then f.owners = {} end
    f.next = tonumber(f.next) or 2
    return f
end

--- True when single player: one ship, and none of this.
local function alone()
    return not isServer() and not isClient()
end

function Ship.ownerOf(id)
    if id == 1 then return nil end
    return Ship.fleet().owners[tostring(id)]
end

--- This username's own shuttle, or nil.
function Ship.personalOf(username)
    if alone() or type(username) ~= "string" then return nil end
    return tonumber(Ship.fleet().byOwner[username])
end

function Ship.exists(id)
    id = tonumber(id)
    if not id then return false end
    return id == 1 or Ship.fleet().owners[tostring(math.floor(id))] ~= nil
end

function Ship.isPersonal(id)
    return (id or U.shipNow) ~= 1
end

--- True for a personal shuttle whose owner the server no longer lists
--- (sandbox *Personal shuttles*). She and her cabin stay where they are, and
--- neither her owner nor her crew may use her until the name is back: a
--- server that takes a shuttle away has to be able to. Leaving her is never
--- asked, and an admin still may use her (Ship.canUse).
function Ship.impounded(id)
    id = id or U.shipNow
    if id == 1 then return false end
    local owner = Ship.ownerOf(id)
    return owner == nil or not TREK.Rules.hasPersonalShuttle(owner)
end

--- Every ship there is, the shared one first.
function Ship.ids()
    local out = { 1 }
    if alone() then return out end
    local f = Ship.fleet()
    for id = 2, f.next - 1 do
        if f.owners[tostring(id)] then table.insert(out, id) end
    end
    return out
end

--- Runs fn(id) once as each ship. The authority's timers go round the fleet
--- with this: what keeps one shuttle's cabin, power and flight in order
--- keeps every one of them.
function Ship.each(fn)
    for _, id in ipairs(Ship.ids()) do
        U.try("ship.each", U.usingShip, id, fn, id)
    end
end

--- Publishes the register. Authority only.
function Ship.publishFleet()
    if isClient() then return end
    if isServer() then
        U.try("transmitFleet", function() ModData.transmit(C.FleetKey) end)
    end
    Ship.notify()
end

--- The ship whose cabin this player is standing in, or nil.
function Ship.aboardId(player)
    if not player then return nil end
    local x = U.try("ship.x", function() return player:getX() end)
    local y = U.try("ship.y", function() return player:getY() end)
    return U.shipAt(x, y)
end

-- A client cannot read a vehicle's tag (TREK_Vehicle, V.ship), so it works
-- out which ship a shuttle is from where each ship is recorded -- once, as
-- they sit down, and holds to the answer while they stay in that seat: a
-- ship being flown is a second behind her own record, and two shuttles in
-- the air near each other must not swap crews.
local seated = { vehicle = nil, id = nil }

--- The ship whose seats this player is in, or nil.
function Ship.seatId(player)
    if not player then return nil end
    local vehicle = U.try("ship.vehicle", function() return player:getVehicle() end)
    if not vehicle or not TREK.Vehicle.isShuttle(vehicle) then
        if isClient() then seated.vehicle, seated.id = nil, nil end
        return nil
    end
    if not isClient() then return TREK.Vehicle.fleetOf(vehicle) end
    if seated.vehicle == vehicle and seated.id then return seated.id end
    local vx = U.try("ship.vx", function() return vehicle:getX() end)
    local vy = U.try("ship.vy", function() return vehicle:getY() end)
    local best, bestD = nil, nil
    for _, id in ipairs(Ship.ids()) do
        local s = U.stateOf(id)
        if vx and (s.landed or s.flying) and s.x and s.y then
            local d = U.dist2(vx, vy, s.x, s.y)
            if not bestD or d < bestD then best, bestD = id, d end
        end
    end
    seated.vehicle, seated.id = vehicle, best
    return best
end

-- Which ship this machine's player has chosen to deal with from the ground:
-- their own if they have one, until they pick another (TREK_Menu).
Ship.selected = nil

--- Chooses the ship this machine's player hails from the ground.
function Ship.select(id)
    id = tonumber(id)
    if id and Ship.exists(id) then Ship.selected = math.floor(id) else Ship.selected = nil end
    Ship.notify()
    return Ship.selected
end

--- **The one ship this machine's player is dealing with**, which is the
--- ship every client-side file means by "the ship": the one whose cabin they
--- are standing in, else the one whose seat they are in, else the one they
--- have chosen, else their own, else the shared one. Single player, and a
--- server process, have only the shared one.
function Ship.mine(player)
    if not isClient() then return 1 end
    player = player or U.player(0)
    if not player then return 1 end
    local id = Ship.aboardId(player) or Ship.seatId(player)
    if id then return id end
    if Ship.selected and Ship.exists(Ship.selected) then return Ship.selected end
    return Ship.personalOf(Ship.usernameOf(player)) or 1
end

--- The ship a command from this player is about, as the authority sees it:
--- where its own copy of them is standing or sitting first, then the ship
--- they named, then their own. What they *may* do with it is each handler's
--- to say (Ship.canUse); this only decides which ship is being asked about.
function Ship.contextFor(player, args)
    if alone() then return 1 end
    local id = Ship.aboardId(player) or Ship.seatId(player)
    if id and Ship.exists(id) then return id end
    local asked = args and tonumber(args.ship)
    if asked and Ship.exists(asked) then return math.floor(asked) end
    return Ship.personalOf(Ship.usernameOf(player)) or 1
end

--- Every ship this player may use, the one they own first: for the menu
--- that chooses between them.
function Ship.usable(player)
    local out = {}
    local own = Ship.personalOf(Ship.usernameOf(player))
    if own then table.insert(out, own) end
    for _, id in ipairs(Ship.ids()) do
        if id ~= own and U.usingShip(id, Ship.canUse, player) then table.insert(out, id) end
    end
    return out
end

-- A client connected to a server keeps the one ship its player is dealing
-- with in hand, refreshed before anything else runs in the tick: this file
-- is shared, and shared files load -- and so register -- before any client's.
Events.OnTick.Add(function()
    if not isClient() then return end
    local id = Ship.mine()
    if id ~= U.shipNow then
        U.shipNow = id
        Ship.notify()
    end
end)

--- Something to call when the ship's state changes, for UI.
function Ship.onChange(fn)
    table.insert(Ship.listeners, fn)
end

function Ship.notify()
    for _, fn in ipairs(Ship.listeners) do U.try("shipListener", fn) end
end

-- A client asks for the ship and the register when its world loads...
Events.OnInitGlobalModData.Add(function()
    if not isClient() then return end
    U.try("requestShip", function() ModData.request(C.StateKey) end)
    U.try("requestFleet", function() ModData.request(C.FleetKey) end)
end)

-- Ships this client has asked for, so each is asked for once.
local asked = {}

-- ...and keeps what the server sends. The server never takes a client's copy.
Events.OnReceiveGlobalModData.Add(function(key, data)
    if not isClient() then return end
    if type(key) ~= "string" or type(data) ~= "table" then return end
    if key == C.FleetKey then
        ModData.add(key, data)
        -- Every ship on the register is this client's business: any of them
        -- may be standing on the street outside. Each is sent again by the
        -- server whenever it changes; this is only the first copy.
        for _, id in ipairs(Ship.ids()) do
            if id ~= 1 and not asked[id] then
                asked[id] = true
                local k = U.stateKey(id)
                U.try("requestShip:" .. k, function() ModData.request(k) end)
            end
        end
        Ship.notify()
        return
    end
    if key ~= C.StateKey and key:sub(1, #C.StateKey + 1) ~= C.StateKey .. "_" then return end
    ModData.add(key, data)
    Ship.notify()
end)

---------------------------------------------------------------------------
-- Per player
---------------------------------------------------------------------------
--- This player's own ship facts, stored on the character:
---   returnX, returnY, returnZ  -- where they beamed up from
---   aboard                     -- whether they are in the cabin
function Ship.playerData(player)
    if not player then return {} end
    local md = U.try("playerModData", function() return player:getModData() end)
    if not md then return {} end
    md.TREK = md.TREK or {}
    return md.TREK
end

--- Where this player returns to when beaming down with no course: their own
--- return point, or -- for a single-player save from before per-player data --
--- the ship-wide one that save still carries.
function Ship.returnPoint(player)
    local pd = Ship.playerData(player)
    if pd.returnX then return pd.returnX, pd.returnY, pd.returnZ end
    local s = Ship.get()
    if s.returnX then return s.returnX, s.returnY, s.returnZ end
    return nil
end

--- Where this player is **in the real world**, for anything that has to pick
--- a point on the map near them.
---
--- Three answers, in order, and the order is the whole point:
---
---   1. their own position, when they are actually outside;
---   2. their return point, when they are aboard -- the cabin sits in its own
---      cell tens of thousands of squares from Kentucky, so a player standing
---      in it has no useful position of their own, and where they *would*
---      beam down to is the honest answer;
---   3. the ship's own position, if she is landed somewhere.
---
--- **Nil when there is no answer**, and callers must treat that as a refusal.
--- The probe launcher used `s.x, s.y` directly and got `0, 0` in a new world
--- where the shuttle had never been called down -- so the first probe anybody
--- fired reported a contact in the top-left corner of the world, four hundred
--- squares from nothing, while the crew stood in Muldraugh.
function Ship.worldOrigin(player)
    if player then
        local px = U.try("originX", function() return player:getX() end)
        local py = U.try("originY", function() return player:getY() end)
        local pz = U.try("originZ", function() return player:getZ() end)
        -- Below the Muldraugh stockroom a player is *at* the stockroom as
        -- far as the map is concerned (FIELD_STATION.md 3): their return
        -- point, written by both ends when they went down. Aboard the
        -- Adirondack the same: her decks are in the void, and where they
        -- beamed up from is the honest answer -- which matters now a lock
        -- lifts them straight off the map (ACCESS.md 3.10).
        local below = TREK.Adirondack ~= nil and TREK.Adirondack.siteOfPlayer(player) ~= nil
        if px and py and not below and not U.isAboard(px, py, pz) then
            return math.floor(px), math.floor(py)
        end
        local rx, ry = Ship.returnPoint(player)
        if rx and ry then return math.floor(rx), math.floor(ry) end
    end
    local s = Ship.get()
    if s.landed and s.x and s.y and (s.x ~= 0 or s.y ~= 0) then
        return math.floor(s.x), math.floor(s.y)
    end
    return nil
end

function Ship.setReturnPoint(player, x, y, z)
    local pd = Ship.playerData(player)
    pd.returnX, pd.returnY, pd.returnZ = math.floor(x), math.floor(y), math.floor(z)
end

---------------------------------------------------------------------------
-- Access
---------------------------------------------------------------------------
--- The sandbox setting for who may use the ship: 1 everyone, 2 owner and
--- crew, 3 the players the server lists (sandbox *Shuttle users*).
Ship.AccessEveryone, Ship.AccessCrew, Ship.AccessListed = 1, 2, 3
function Ship.accessMode()
    local v = U.try("sandboxAccess", function()
        return SandboxVars.TrekShuttle and SandboxVars.TrekShuttle.Access
    end)
    return tonumber(v) or 1
end

function Ship.usernameOf(player)
    return U.try("username", function() return player:getUsername() end) or "player"
end

--- True for a server admin. Admins may always use and reassign the ship,
--- whatever the access setting. Build 42 replaced access levels with roles;
--- this is the check vanilla's own UI uses (Role.hasAdminPower).
function Ship.isAdmin(player)
    return U.try("adminRole", function()
        local role = player:getRole()
        return role ~= nil and role:hasAdminPower()
    end) == true
end

--- May this player fly, beam, land and change the ship in hand?
function Ship.canUse(player)
    if not player then return false end
    if not isServer() and not isClient() then return true end   -- single player
    -- A personal shuttle is its owner's, and whoever they have made crew
    -- (SERVERS.md). The sandbox's rule below is the shared ship's alone.
    if U.shipNow ~= 1 then
        if Ship.isAdmin(player) then return true end
        if Ship.impounded() then return false end
        local s = Ship.get()
        local name = Ship.usernameOf(player)
        if Ship.ownerOf(U.shipNow) == name then return true end
        return s.crew ~= nil and s.crew[name] == true
    end
    local mode = Ship.accessMode()
    if mode == Ship.AccessListed then
        return TREK.Rules.listed("AccessUsers", Ship.usernameOf(player)) or Ship.isAdmin(player)
    end
    if mode ~= Ship.AccessCrew then return true end
    local s = Ship.get()
    local name = Ship.usernameOf(player)
    if not s.owner or s.owner == name then return true end
    if s.crew and s.crew[name] then return true end
    return Ship.isAdmin(player)
end

--- May this player manage the crew list?
function Ship.canManageCrew(player)
    if not player then return false end
    if U.shipNow ~= 1 then
        return Ship.ownerOf(U.shipNow) == Ship.usernameOf(player) or Ship.isAdmin(player)
    end
    local s = Ship.get()
    return not s.owner or s.owner == Ship.usernameOf(player) or Ship.isAdmin(player)
end

return Ship
