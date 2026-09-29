--[[ Shuttlecraft -- raids: what both sides agree on (RAIDS.md).

    The pattern buffer overflows, Captain Titus asks for help, and a player
    who accepts is beamed to where it is coming out and home again after.

    **The record** (C.RaidKey) is the server's and every client holds the copy
    it last published. It is small and bounded -- one standing request and
    one raid at most:

      nextAt                world hour the next request may come
      request { id, kind, tx, ty, offeredAt, lapseAt, declined = { [name] } }
      raid { id, kind, state, tx, ty, tz, members = { [name] = true },
             n, released, alive, killed, camp = { cx, cy, z },
             startedAt, lastPresent, acceptedAt }
      removals { { x, y, z, sprite } }   scenery to take away once loaded

    `state` is arriving (accepted, the camp not built yet), live (the buffer
    is emptying), won or lost. Shared, with no side effects, so the panel greys
    Accept for exactly the reason the server refuses it.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local Rd = {}
TREK.Raids = Rd

Rd.listeners = {}

function Rd.store()
    local d = ModData.getOrCreate(C.RaidKey)
    if not isClient() then
        d.serial = tonumber(d.serial) or 0
        d.removals = type(d.removals) == "table" and d.removals or {}
    end
    return d
end

function Rd.request() return Rd.store().request end
function Rd.raid() return Rd.store().raid end

function Rd.onChange(fn) table.insert(Rd.listeners, fn) end

function Rd.notify()
    for _, fn in ipairs(Rd.listeners) do U.try("raidsListener", fn) end
end

--- Publishes the record. Authority only.
function Rd.publish()
    if isClient() then
        U.warnOnce("raidsOnClient", "a client tried to publish the raids; ignored")
        return
    end
    if isServer() then
        U.try("transmitRaids", function() ModData.transmit(C.RaidKey) end)
    end
    Rd.notify()
end

Events.OnInitGlobalModData.Add(function()
    if not isClient() then return end
    U.try("requestRaids", function() ModData.request(C.RaidKey) end)
end)

Events.OnReceiveGlobalModData.Add(function(key, data)
    if key ~= C.RaidKey then return end
    if not isClient() or type(data) ~= "table" then return end
    ModData.add(key, data)
    Rd.notify()
end)

---------------------------------------------------------------------------
-- The rules
---------------------------------------------------------------------------
function Rd.nameOf(player)
    return TREK.Ship and TREK.Ship.usernameOf(player) or "player"
end

--- True while a raid is under way and can still be joined.
function Rd.joinable(raid)
    return raid ~= nil and (raid.state == "arriving" or raid.state == "live")
end

function Rd.isMember(raid, player)
    return raid ~= nil and type(raid.members) == "table" and raid.members[Rd.nameOf(player)] == true
end

--- What the panel offers: the standing request, or a raid still to join.
--- Returns the thing's id and kind, or nil.
function Rd.offer(player)
    local d = Rd.store()
    if d.request then return d.request.id, d.request.kind, false end
    if Rd.joinable(d.raid) and not Rd.isMember(d.raid, player) then
        return d.raid.id, d.raid.kind, true
    end
    return nil
end

--- Why this player may not accept (or join), or nil.
function Rd.acceptRefusal(player, id)
    if C.raidsMode() == C.RaidsOff then return "raidOff" end
    if not player then return "raidGone" end
    if U.try("raids.dead", function() return player:isDead() end) ~= false then return "raidGone" end
    local have = Rd.offer(player)
    if not have or (id ~= nil and have ~= id) then
        if Rd.isMember(Rd.raid(), player) then return "raidAlready" end
        return "raidGone"
    end
    -- The Adirondack's transporter: only a player she can lock onto.
    if TREK.Access and TREK.Access.refusal(player) then return "raidClearance" end
    return nil
end

--- Game minutes a request has left, or nil.
function Rd.minutesLeft(now)
    local r = Rd.request()
    if not r or type(r.lapseAt) ~= "number" then return nil end
    return math.max(0, math.floor((r.lapseAt - (now or U.worldHours())) * 60 + 0.5))
end

--- The buffer as the HUD shows it: per cent left, and the dead still to come
--- or still standing.
function Rd.buffer(raid)
    if not raid or not raid.n or raid.n <= 0 then return 0, 0 end
    local left = math.max(0, raid.n - (raid.released or 0))
    local pct = math.floor(left * 100 / raid.n + 0.5)
    return pct, left + (raid.alive or 0)
end

return Rd
