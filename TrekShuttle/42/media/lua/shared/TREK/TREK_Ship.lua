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

--- Publishes the ship's state after a change. Authority only.
function Ship.commit()
    if isClient() then
        U.warnOnce("commitOnClient", "a client tried to commit ship state; ignored")
        return
    end
    if isServer() then
        U.try("transmitShip", function() ModData.transmit(C.StateKey) end)
    end
    Ship.notify()
end

--- Something to call when the ship's state changes, for UI.
function Ship.onChange(fn)
    table.insert(Ship.listeners, fn)
end

function Ship.notify()
    for _, fn in ipairs(Ship.listeners) do U.try("shipListener", fn) end
end

-- A client asks for the ship when its world loads...
Events.OnInitGlobalModData.Add(function()
    if not isClient() then return end
    U.try("requestShip", function() ModData.request(C.StateKey) end)
end)

-- ...and keeps what the server sends. The server never takes a client's copy.
Events.OnReceiveGlobalModData.Add(function(key, data)
    if key ~= C.StateKey then return end
    if not isClient() then return end
    if type(data) ~= "table" then return end
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

function Ship.setReturnPoint(player, x, y, z)
    local pd = Ship.playerData(player)
    pd.returnX, pd.returnY, pd.returnZ = math.floor(x), math.floor(y), math.floor(z)
end

---------------------------------------------------------------------------
-- Access
---------------------------------------------------------------------------
--- The sandbox setting for who may use the ship: 1 everyone, 2 owner and crew.
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

--- May this player fly, beam, land and change the ship?
function Ship.canUse(player)
    if not player then return false end
    if not isServer() and not isClient() then return true end   -- single player
    if Ship.accessMode() ~= 2 then return true end
    local s = Ship.get()
    local name = Ship.usernameOf(player)
    if not s.owner or s.owner == name then return true end
    if s.crew and s.crew[name] then return true end
    return Ship.isAdmin(player)
end

--- May this player manage the crew list?
function Ship.canManageCrew(player)
    if not player then return false end
    local s = Ship.get()
    return not s.owner or s.owner == Ship.usernameOf(player) or Ship.isAdmin(player)
end

return Ship
