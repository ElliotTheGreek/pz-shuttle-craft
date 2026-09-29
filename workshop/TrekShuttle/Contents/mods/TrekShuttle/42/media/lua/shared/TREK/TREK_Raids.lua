--[[ Shuttlecraft -- raids: what both sides agree on (RAIDS.md).

    The pattern buffer overflows, Captain Titus asks for help, and a player
    who accepts is beamed to where it is coming out and home again after.

    **The record** (C.RaidKey) is the server's and every client holds the copy
    it last published. It is small and bounded -- one standing request and
    one raid at most:

      nextAt                world hour the next request may come
      request { id, kind, tx, ty, offeredAt, lapseAt, declined = { [name] } }
      raid { id, kind, state, tx, ty, tz, members = { [name] = true },
             n, released, alive, killed, camp = { cx, cy, z, machines },
             startedAt, acceptedAt (world hours),
             startedMs, lastPresentMs, acceptedMs (real ms: the limits) }
      removals { { x, y, z, sprite | item } }   what to take away once loaded

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

---------------------------------------------------------------------------
-- The raid's dead: sprinting and hunting wherever they are simulated
---------------------------------------------------------------------------
-- A zombie's speed and its target are the business of whichever machine
-- simulates it -- the server or single player for a zombie nobody is near,
-- the owning client in multiplayer -- and that machine's own walk is what
-- the others are sent (ZombiePacket.walkType, NetworkZombiePacker
-- .applyZombie). So a raider's pace is kept the way the Borg walk is kept
-- (TREK_Borg): on every update, in every process that knows the zombie is
-- one of the raid's.
--
-- Knowing it: the server and single player by the object it spawned
-- (checked against its persistent outfit id, because the engine recycles
-- IsoZombie objects); a client by the online ids the server sends each wave
-- (`raidZeds`), because a client's copy never carries the server's tag.
local byObject = setmetatable({}, { __mode = "k" })
Rd.zedIds = {}
-- A count beside it, because Kahlua has no `next` to ask the table.
Rd.zedIdCount = 0
-- Updates between one look for a quarry and the next, per zombie.
Rd.HUNT_EVERY = 30
local hunt = setmetatable({}, { __mode = "k" })

--- Marks a zombie the server has just spawned: "run" or "walk".
function Rd.markZed(z, pace)
    local id = U.try("raids.outfitId", function() return z:getPersistentOutfitID() end) or 0
    byObject[z] = { id, pace }
end

--- Replaces a client's list of the raid's dead: "id:pace,id:pace".
function Rd.setZedIds(list)
    Rd.zedIds, Rd.zedIdCount = {}, 0
    for id, pace in tostring(list or ""):gmatch("(%-?%d+):(%a+)") do
        Rd.zedIds[tonumber(id)] = pace
        Rd.zedIdCount = Rd.zedIdCount + 1
    end
end

--- "run", "walk", or nil for a zombie that is not the raid's.
function Rd.paceOf(z)
    local row = byObject[z]
    if row then
        if row[1] == z:getPersistentOutfitID() then return row[2] end
        byObject[z] = nil
    end
    if isClient() and Rd.zedIdCount > 0 then
        return Rd.zedIds[z:getOnlineID()]
    end
    return nil
end

local function nearestPlayer(z)
    local zx, zy = z:getX(), z:getY()
    local best, bd = nil, nil
    for _, p in ipairs(U.players()) do
        if not p:isDead() and math.floor(p:getZ()) == math.floor(z:getZ()) then
            local d = U.dist2(zx, zy, p:getX(), p:getY())
            if d <= C.RaidPresentRange * C.RaidPresentRange and (not bd or d < bd) then best, bd = p, d end
        end
    end
    return best
end

--- One update of one zombie: a raider runs if it is a runner, and always
--- has somebody to come for.
function Rd.drive(z)
    local pace = Rd.paceOf(z)
    if not pace or z:isDead() then return end
    -- Another machine simulates it; what that machine decides is sent here.
    if isClient() and z:isRemoteZombie() then return end
    if pace == "run" and z:getSpeedType() ~= 1 and not z:isCrawling() then z:doSprinter() end
    local n = (hunt[z] or 0) + 1
    if n < Rd.HUNT_EVERY and z:getTarget() ~= nil then
        hunt[z] = n
        return
    end
    hunt[z] = 0
    local p = nearestPlayer(z)
    if p and z:getTarget() ~= p then z:spotted(p, true) end
end

-- Every zombie, every tick, so nothing is allocated for one that is not the
-- raid's: a failure is logged once and the hook stops trying.
local broken = false
Events.OnZombieUpdate.Add(function(z)
    if broken then return end
    local ok, err = pcall(Rd.drive, z)
    if not ok then
        broken = true
        U.warnOnce("raids.drive", tostring(err))
    end
end)

--- The buffer as the HUD shows it: per cent left, and the dead still to come
--- or still standing.
function Rd.buffer(raid)
    if not raid or not raid.n or raid.n <= 0 then return 0, 0 end
    local left = math.max(0, raid.n - (raid.released or 0))
    local pct = math.floor(left * 100 / raid.n + 0.5)
    return pct, left + (raid.alive or 0)
end

return Rd
