--[[ Shuttlecraft -- raids: the authority (RAIDS.md).

    Everything that decides or changes a raid, where the world is
    authoritative -- single player, or the server:

      * the schedule: the first request once a player is cleared to beam
        aboard, then one every few days, never while one stands or runs;
      * the request: made, warned about, declined, lapsed;
      * accepting: who is in, where each goes home to (on the server's copy of
        the player), and the move there;
      * the outpost's camp, built once a raider has loaded its ground;
      * the waves, the count, the outcome, the rewards;
      * home again, and the scenery taken away.

    Built for the outpost first (RAIDS.md 11): the camp stands on the real
    map, where the engine's pathing is its own. The Adirondack and the field
    station come later.

    The minute clock runs outside every loaded-ground branch; the waves run on
    a real-time tick, because twenty seconds between waves is a fight's pace
    and not a game minute's.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_Raids"
require "TREK/TREK_Access"
require "TREK/TREK_Adirondack"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Ship = TREK.Ship
local Rd = TREK.Raids

local S = {}
TREK.RaidsServer = S

local function deny(player, why)
    Net.toClient(player, "denied", { why = why })
end

local function alive(p)
    return p ~= nil and U.try("raids.dead", function() return p:isDead() end) == false
end

local function roll(n)
    if n <= 1 then return 0 end
    return U.try("raids.roll", function() return ZombRand(n) end) or 0
end

local function nowMs()
    return U.try("raids.ms", function() return getTimestampMs() end) or 0
end

local function playerNamed(name)
    for _, p in ipairs(U.players()) do
        if Rd.nameOf(p) == name then return p end
    end
    return nil
end

--- The players who may be asked: alive and cleared to beam aboard her.
local function cleared()
    local out = {}
    for _, p in ipairs(U.players()) do
        if alive(p) and not (TREK.Access and TREK.Access.refusal(p)) then table.insert(out, p) end
    end
    return out
end

local function crewOrigin()
    for _, p in ipairs(U.players()) do
        local x, y = Ship.worldOrigin(p)
        if x and y then return x, y end
    end
    return nil
end

local function interval()
    local span = C.RaidIntervalDays[C.raidsMode()] or C.RaidIntervalDays[C.RaidsNormal]
    local days = span[1] + (span[2] - span[1]) * roll(1001) / 1000
    return days * 24
end

---------------------------------------------------------------------------
-- The request
---------------------------------------------------------------------------
--- Makes a request now. Returns it, or nil when there was nowhere to put it.
function S.makeRequest(now)
    local d = Rd.store()
    local ox, oy = crewOrigin()
    if not ox then
        d.nextAt = now + 1
        return nil
    end
    local tx, ty
    for _ = 1, 24 do
        local bearing = roll(3600) / 3600 * 2 * math.pi
        local dist = C.OutpostMinDistance + roll(C.OutpostMaxDistance - C.OutpostMinDistance + 1)
        local x = math.floor(ox + math.cos(bearing) * dist)
        local y = math.floor(oy + math.sin(bearing) * dist)
        if U.inWorld(x, y) then tx, ty = x, y break end
    end
    if not tx then
        d.nextAt = now + 1
        U.log("raids: nowhere in the world to put an outpost from %d,%d; trying again in an hour", ox, oy)
        return nil
    end
    d.serial = d.serial + 1
    d.request = { id = "raid:" .. d.serial, kind = "outpost", tx = tx, ty = ty,
                  offeredAt = now, lapseAt = now + C.RaidOfferHours, declined = {}, warned = {} }
    Rd.publish()
    local n = math.floor((C.RaidBase.outpost + C.RaidPerPlayer) * C.raidScale())
    for _, p in ipairs(cleared()) do
        local px, py = Ship.worldOrigin(p)
        Net.toClient(p, "raidCall", {
            id = d.request.id, kind = "outpost", n = n,
            distance = px and math.floor(math.sqrt(U.dist2(px, py, tx, ty))) or nil,
            compass = px and U.compass(px, py, tx, ty) or nil,
            hours = C.RaidOfferHours,
        })
    end
    U.log("raids: Captain Titus asks for help at an outpost near %d,%d (%s)", tx, ty, d.request.id)
    return d.request
end

--- The minute clock: the first request, the next, warnings, lapses.
function S.serviceSchedule()
    local d = Rd.store()
    local now = U.worldHours()
    local mode = C.raidsMode()
    if d.request then
        local r = d.request
        if mode == C.RaidsOff or now >= r.lapseAt then
            d.request = nil
            d.nextAt = now + interval()
            Rd.publish()
            Net.toAll("raidLapsed", {})
            U.log("raids: the request lapsed; the ship contained it without the crew")
            return
        end
        local left = (r.lapseAt - now) * 60
        for _, m in ipairs(C.RaidWarnMinutes) do
            local key = tostring(m)
            if left <= m and not r.warned[key] then
                r.warned[key] = true
                Rd.publish()
                for _, p in ipairs(cleared()) do
                    if not r.declined[Rd.nameOf(p)] then
                        Net.toClient(p, "raidWarn", { minutes = m })
                    end
                end
            end
        end
        return
    end
    if d.raid or mode == C.RaidsOff then return end
    if #cleared() == 0 then return end
    if not d.nextAt then
        d.nextAt = now + (C.RaidFirstHours[mode] or C.RaidFirstHours[C.RaidsNormal])
        Rd.publish()
        U.log("raids: a player is cleared; the first request is due at hour %.1f", d.nextAt)
        return
    end
    if now >= d.nextAt then S.makeRequest(now) end
end

Net.onServer("raidDecline", function(player, args)
    local d = Rd.store()
    local r = d.request
    if not r or r.id ~= args.id then return end
    r.declined[Rd.nameOf(player)] = true
    -- Everybody who could have come said no: it ends now rather than
    -- standing for hours with nobody left to ask.
    local anyone = false
    for _, p in ipairs(cleared()) do
        if not r.declined[Rd.nameOf(p)] then anyone = true end
    end
    if not anyone then
        d.request = nil
        d.nextAt = U.worldHours() + interval()
        Net.toAll("raidLapsed", { declined = true })
        U.log("raids: every cleared player declined")
    end
    Rd.publish()
end)

---------------------------------------------------------------------------
-- Accepting, and home again
---------------------------------------------------------------------------
--- Where a player goes home to: the cabin, a deck of hers or the station's,
--- or a square of the map. Read from the server's own copy of where they are.
local function returnOf(player)
    local x, y, z = player:getX(), player:getY(), player:getZ()
    if U.isInteriorPlayer(player) then return { kind = "cabin" } end
    local A = TREK.Adirondack
    local k = A and A.locate(x, y, z)
    if k then return { kind = "deck", x = math.floor(x), y = math.floor(y), k = k } end
    return { kind = "world", x = math.floor(x), y = math.floor(y), z = math.floor(z) }
end

Net.onServer("raidAccept", function(player, args)
    local why = Rd.acceptRefusal(player, args.id)
    if why then deny(player, why) return end
    local d = Rd.store()
    local now = U.worldHours()
    local raid = d.raid
    if d.request then
        local r = d.request
        raid = { id = r.id, kind = r.kind, state = "arriving", tx = r.tx, ty = r.ty, tz = 0,
                 members = {}, n = math.floor(C.RaidBase[r.kind] * C.raidScale()),
                 released = 0, alive = 0, killed = 0, acceptedAt = now, lastPresent = now }
        d.raid = raid
        d.request = nil
    end
    local name = Rd.nameOf(player)
    raid.members[name] = true
    raid.n = raid.n + math.floor(C.RaidPerPlayer * C.raidScale())
    player:getModData()[C.RaidReturnKey] = returnOf(player)
    Rd.publish()
    Net.toClient(player, "raidGo", { id = raid.id, x = raid.tx, y = raid.ty, z = raid.tz })
    Net.toAll("raidJoined", { by = name })
    U.log("raids: %s is going to %s at %d,%d", name, raid.id, raid.tx, raid.ty)
end)

--- The move handler asks this for `raidIn` and `raidOut`.
function S.isMember(player)
    return Rd.isMember(Rd.raid(), player) or player:getModData()[C.RaidReturnKey] ~= nil
end

--- Tells one raider to go home, to where they came from.
function S.sendHome(player)
    local ret = player:getModData()[C.RaidReturnKey]
    if type(ret) ~= "table" then return false end
    Net.toClient(player, "raidReturn", ret)
    return true
end

--- The move home was granted: they are no longer in it.
function S.onReturned(player)
    local raid = Rd.raid()
    if raid and raid.members then raid.members[Rd.nameOf(player)] = nil end
    player:getModData()[C.RaidReturnKey] = nil
    Rd.publish()
end

--- Beam back now: after a win, or a retreat while it runs.
Net.onServer("raidHome", function(player)
    if not S.isMember(player) then return end
    S.sendHome(player)
end)

---------------------------------------------------------------------------
-- The outpost's camp
---------------------------------------------------------------------------
--- Wilderness the ship may clear off a camp's square: trees, bushes, grass
--- tufts, ground cover and litter -- what grows or blows onto the county's
--- ground, never what anybody built. Woods are full of it, and the first
--- camp ever asked for was refused in a wood because a tree and a tuft of
--- grass both counted as "something on the square".
local function clearable(o)
    if instanceof(o, "IsoTree") or U.isWild(o) then return true end
    local name = U.try("raids.spriteName", function() return o:getSprite():getName() end)
    if type(name) ~= "string" then return false end
    return name:sub(1, 21) == "blends_grassoverlays_" or name:sub(1, 8) == "d_trash_"
end
S.clearable = clearable

--- Ground an outpost may stand on: the county's own (grass, dirt, sand), no
--- water, no building, and nothing on it the ship may not clear.
local function campGround(sq)
    if not sq then return false end
    local ok = U.try("raids.ground", function()
        local f = sq:getFloor()
        if not f then return false end
        local name = f:getSprite():getName() or ""
        if name:sub(1, 18) ~= "blends_natural_01_" and name:sub(1, 27) ~= "floors_exterior_natural_01_" then
            return false
        end
        if f:getSprite():getProperties():has(IsoFlagType.water) then return false end
        if sq:getBuilding() ~= nil then return false end
        local objs = sq:getObjects()
        for i = 0, objs:size() - 1 do
            local o = objs:get(i)
            if o ~= f and not clearable(o) then return false end
        end
        return true
    end)
    return ok == true
end

--- Takes the wilderness off a square, for every machine: a removal the
--- engine sends (DEV_GUIDE: the server changes the world only through
--- transmit calls). Returns how many went.
local function clearWild(sq)
    if not sq then return 0 end
    local f = U.try("raids.floor", function() return sq:getFloor() end)
    local doomed = {}
    U.eachObject(sq, function(o)
        if o ~= f and clearable(o) then table.insert(doomed, o) end
    end)
    for _, o in ipairs(doomed) do
        U.try("raids.clear", function() sq:transmitRemoveItemFromSquare(o) end)
    end
    return #doomed
end

--- The best centre for the camp within C.OutpostSearch of (tx, ty): the
--- square whose whole camp area has the most good ground, as long as its pad
--- squares are good and at least nine in ten of the rest are. Nil when the
--- ground is not all loaded yet ("cannot tell"), false when it is and there
--- is nowhere.
function S.findCamp(tx, ty, z)
    local R, H = C.OutpostSearch, C.OutpostClear
    local x0, y0, span = tx - R - H, ty - R - H, 2 * (R + H) + 1
    for _, c in ipairs({ { x0, y0 }, { x0 + span - 1, y0 }, { x0, y0 + span - 1 },
                         { x0 + span - 1, y0 + span - 1 } }) do
        if not U.chunkLoaded(c[1], c[2], z) then return nil end
    end
    -- A summed-area table over the good squares: one pass of look-ups, then
    -- every candidate's count in four reads.
    local sat = {}
    for j = 0, span do sat[j] = {} sat[j][0] = 0 end
    for i = 0, span do sat[0][i] = 0 end
    local good = {}
    for j = 1, span do
        good[j] = {}
        local row = 0
        for i = 1, span do
            local g = campGround(U.square(x0 + i - 1, y0 + j - 1, z, false))
            good[j][i] = g
            row = row + (g and 1 or 0)
            sat[j][i] = sat[j - 1][i] + row
        end
    end
    local function count(cx, cy)
        local a, b = cx - x0 + 1 - H, cy - y0 + 1 - H
        local c2, d2 = a + 2 * H, b + 2 * H
        return sat[d2][c2] - sat[b - 1][c2] - sat[d2][a - 1] + sat[b - 1][a - 1]
    end
    local need = math.ceil((2 * H + 1) ^ 2 * 0.9)
    local best, bestN, bestD = nil, -1, nil
    for cy = ty - R, ty + R do
        for cx = tx - R, tx + R do
            local padOk = true
            for _, p in ipairs(C.OutpostPad) do
                local gj, gi = cy + p[2] - y0 + 1, cx + p[1] - x0 + 1
                if not (good[gj] and good[gj][gi]) then padOk = false end
            end
            if padOk then
                local n = count(cx, cy)
                local dd = (cx - tx) ^ 2 + (cy - ty) ^ 2
                if n >= need and (n > bestN or (n == bestN and dd < bestD)) then
                    best, bestN, bestD = { cx, cy }, n, dd
                end
            end
        end
    end
    if not best then return false end
    return best[1], best[2]
end

local function placeTile(x, y, z, sprite, prepare)
    local sq = U.square(x, y, z, false)
    if not sq or not campGround(sq) then return nil end
    local obj = U.try("raids.new", function() return IsoObject.new(sq, sprite, "") end)
    if not obj then return nil end
    U.try("raids.tag", function() obj:getModData().TREK = C.RaidTag end)
    if prepare then U.try("raids.prepare", prepare, obj) end
    if U.try("raids.add", function() sq:transmitAddObjectToSquare(obj, -1) return true end) ~= true then
        return nil
    end
    return obj
end

local function stockCrate(obj, crystal)
    obj:createContainersFromSpriteProperties()
    local c = U.containerOf(obj)
    if not c then return end
    c:setExplored(true)
    U.fill(obj, C.RaidLoot, 0.35, 12)
    if crystal then c:AddItem(C.DilithiumItem) end
end

--- Builds the camp at (cx, cy). The pad and the machines are recorded, to
--- be taken away when the raid is over; the tents and crates stay.
function S.buildCamp(raid, cx, cy, z)
    raid.camp = { cx = cx, cy = cy, z = z, scenery = {} }
    -- A clearing first: the trees and the undergrowth off the whole camp.
    local H, cleared = C.OutpostClear, 0
    for dy = -H, H do
        for dx = -H, H do
            -- Every square: clearWild only ever takes wilderness, so a square
            -- with something built on it keeps that and loses its tree.
            cleared = cleared + clearWild(U.square(cx + dx, cy + dy, z, false))
        end
    end
    local function keep(dx, dy, sprite)
        if placeTile(cx + dx, cy + dy, z, sprite) then
            table.insert(raid.camp.scenery, { x = cx + dx, y = cy + dy, z = z, sprite = sprite })
        end
    end
    for _, p in ipairs(C.OutpostPad) do keep(p[1], p[2], p[3]) end
    for _, p in ipairs(C.OutpostMachines) do keep(p[1], p[2], p[3]) end
    for _, p in ipairs(C.OutpostTents) do
        -- A tent's front square is a container and its back is not;
        -- createContainersFromSpriteProperties makes one only where the
        -- sprite says so. Explored, or vanilla rolls its own loot into it.
        placeTile(cx + p[1], cy + p[2], z, p[3], function(o)
            o:createContainersFromSpriteProperties()
            local c = U.containerOf(o)
            if c then c:setExplored(true) end
        end)
    end
    local crystalAt = roll(100) < C.RaidCrystalChance and (roll(#C.OutpostCrates) + 1) or nil
    for i, p in ipairs(C.OutpostCrates) do
        placeTile(cx + p[1], cy + p[2], z, C.OutpostCrateSprite, function(o) stockCrate(o, i == crystalAt) end)
    end
    U.log("raids: the outpost stands at %d,%d (%d thing(s) cleared)", cx, cy, cleared)
end

--- Takes the pad and the machines away: now where the ground is loaded,
--- later where it is not (the ensign's removals, run the same way).
local function removeScenery(list)
    local d = Rd.store()
    for _, s in ipairs(list or {}) do
        local sq = U.chunkLoaded(s.x, s.y, s.z) and U.square(s.x, s.y, s.z, false)
        if sq then
            local found = U.findSprite(sq, s.sprite)
            if found then U.try("raids.remove", function() sq:transmitRemoveItemFromSquare(found) end) end
        else
            table.insert(d.removals, s)
        end
    end
end

local function serviceRemovals()
    local d = Rd.store()
    for i = #d.removals, 1, -1 do
        local s = d.removals[i]
        if U.chunkLoaded(s.x, s.y, s.z) then
            local sq = U.square(s.x, s.y, s.z, false)
            local found = sq and U.findSprite(sq, s.sprite)
            if found then U.try("raids.remove", function() sq:transmitRemoveItemFromSquare(found) end) end
            table.remove(d.removals, i)
        end
    end
end

---------------------------------------------------------------------------
-- The waves, and the end
---------------------------------------------------------------------------
--- The raid's own dead still standing, by the server's zombie list.
function S.standing(raid)
    local n = 0
    U.try("raids.count", function()
        local list = getCell():getZombieList()
        for i = 0, list:size() - 1 do
            local z = list:get(i)
            if z and not z:isDead() and z:getModData()[C.RaidZedKey] == raid.id then n = n + 1 end
        end
    end)
    return n
end

local function spawnOne(raid)
    local camp = raid.camp
    local outfit
    if roll(100) < math.floor(C.RaidBorgShare * 100) then
        outfit = roll(2) == 0 and C.BorgDrone or C.BorgAssimilated
    else
        outfit = C.RaidOutfits[roll(#C.RaidOutfits) + 1]
    end
    local p = C.OutpostPad[roll(#C.OutpostPad) + 1]
    local list = U.try("raids.spawn", function()
        return addZombiesInOutfit(camp.cx + p[1], camp.cy + p[2], camp.z, 1, outfit, 50)
    end)
    local got = 0
    U.try("raids.tagZed", function()
        for i = 0, list:size() - 1 do
            list:get(i):getModData()[C.RaidZedKey] = raid.id
            got = got + 1
        end
    end)
    return got
end

--- Members online, alive and within range of the camp (or the site).
local function present(raid)
    local out = {}
    local cx = raid.camp and raid.camp.cx or raid.tx
    local cy = raid.camp and raid.camp.cy or raid.ty
    for name in pairs(raid.members or {}) do
        local p = playerNamed(name)
        if p and alive(p) then
            local x, y = p:getX(), p:getY()
            if U.dist2(x, y, cx, cy) <= C.RaidPresentRange * C.RaidPresentRange then
                table.insert(out, p)
            end
        end
    end
    return out
end

local function reward(p)
    local Rep = TREK.Replicator
    if Rep then
        local learned = 0
        for _, id in ipairs(C.RescuePatterns) do
            if learned >= C.RaidPatternsPerWin then break end
            if not Rep.knows(id) and Rep.learn(id) then learned = learned + 1 end
        end
        if learned > 0 then Rep.publish() end
    end
    -- It counts like a rescue toward rank (TRAITS.md 3.3).
    if TREK.TraitsServer then U.try("raids.rank", TREK.TraitsServer.onRescue, p) end
end

local function finish(raid, won)
    local d = Rd.store()
    raid.state = won and "won" or "lost"
    raid.endMs = nowMs() + (won and C.RaidLootMs or 3000)
    if won then
        for _, p in ipairs(present(raid)) do reward(p) end
    end
    d.nextAt = U.worldHours() + interval()
    Rd.publish()
    Net.toAll(won and "raidWon" or "raidLost", { secs = won and math.floor(C.RaidLootMs / 1000) or 0 })
    U.log("raids: %s %s", raid.id, won and "is won" or "is lost")
end

--- Every raider still in it goes home; the pad and machines go; it is over.
local function close(raid)
    local d = Rd.store()
    for name in pairs(raid.members or {}) do
        local p = playerNamed(name)
        if p and alive(p) then S.sendHome(p) end
    end
    if raid.camp then removeScenery(raid.camp.scenery) end
    d.raid = nil
    Rd.publish()
    U.log("raids: %s is over", raid.id)
end

local lastWaveMs = 0

--- The fast clock: the camp once its ground is there, the waves, the win,
--- the loot window.
function S.serviceRaid()
    local d = Rd.store()
    serviceRemovals()
    local raid = d.raid
    if not raid then return end
    if raid.state == "arriving" then
        if #present(raid) == 0 then return end
        local cx, cy = S.findCamp(raid.tx, raid.ty, raid.tz)
        if cx == nil then return end
        if cx == false then
            U.log("WARN raids: no ground for an outpost near %d,%d; the lock slipped", raid.tx, raid.ty)
            finish(raid, false)
            return
        end
        S.buildCamp(raid, cx, cy, raid.tz)
        raid.state = "live"
        raid.startedAt = U.worldHours()
        raid.lastPresent = raid.startedAt
        -- The first wave one interval from now, not this instant: a raider
        -- materialising into the first four is a raider who never saw the camp.
        lastWaveMs = nowMs()
        Rd.publish()
        for name in pairs(raid.members) do
            local p = playerNamed(name)
            if p then
                Net.toClient(p, "raidCamp", { id = raid.id, x = cx + C.OutpostStand[1],
                                              y = cy + C.OutpostStand[2], z = raid.tz })
            end
        end
        return
    end
    if raid.state == "live" then
        local now = nowMs()
        if now - lastWaveMs < C.RaidWaveMs then return end
        lastWaveMs = now
        raid.alive = S.standing(raid)
        if (raid.released or 0) >= raid.n and raid.alive == 0 then
            finish(raid, true)
            return
        end
        if #present(raid) > 0 and raid.released < raid.n and raid.alive < C.RaidAliveCap then
            local k = math.min(C.RaidWaveSize, raid.n - raid.released, C.RaidAliveCap - raid.alive)
            for _ = 1, k do raid.released = raid.released + spawnOne(raid) end
            raid.alive = S.standing(raid)
        end
        Rd.publish()
        return
    end
    if (raid.state == "won" or raid.state == "lost") and nowMs() >= (raid.endMs or 0) then
        close(raid)
    end
end

--- The minute clock for a running raid: abandoned, or too long.
function S.serviceLimits()
    local raid = Rd.raid()
    if not raid or not Rd.joinable(raid) then return end
    local now = U.worldHours()
    if #present(raid) > 0 then raid.lastPresent = now end
    if now - (raid.lastPresent or now) > C.RaidAbandonMinutes / 60
       or now - (raid.startedAt or raid.acceptedAt or now) > C.RaidHardLimitMinutes / 60 then
        finish(raid, false)
    end
end

Events.OnZombieDead.Add(function(z)
    U.try("raids.dead", function()
        local raid = Rd.raid()
        if raid and z:getModData()[C.RaidZedKey] == raid.id then
            raid.killed = (raid.killed or 0) + 1
        end
    end)
end)

---------------------------------------------------------------------------
-- Timers
---------------------------------------------------------------------------
Events.EveryOneMinute.Add(function()
    U.try("raids.schedule", S.serviceSchedule)
    U.try("raids.limits", S.serviceLimits)
end)

local tick = 0
Events.OnTick.Add(function()
    tick = tick + 1
    if tick < 30 then return end
    tick = 0
    U.try("raids.raid", S.serviceRaid)
end)

return S
