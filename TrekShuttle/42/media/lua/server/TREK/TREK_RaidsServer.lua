--[[ Shuttlecraft -- raids: the authority (RAIDS.md).

    Everything that decides or changes a raid, where the world is
    authoritative -- single player, or the server:

      * the schedule: the first request once a player is cleared to beam
        aboard, then one every few days, never while one stands or runs;
      * the request: made, warned about, declined, lapsed;
      * accepting: who is in, where each goes home to (on the server's copy of
        the player), and the move there;
      * the outpost's camp, built once a raider has loaded its ground, with
        real machines lent from the installations registry;
      * the waves -- beamed in all round the raiders, as many as the cap
        allows, sprinting and hunting -- the count, the outcome, the rewards;
      * home again, and the machines taken away.

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
require "TREK/TREK_World"
require "TREK/TREK_Installations"
require "TREK/TREK_InstallationsServer"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Ship = TREK.Ship
local Rd = TREK.Raids
local W = TREK.World
local IN = TREK.Installations
local IS = TREK.InstallationsServer

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
                 released = 0, alive = 0, killed = 0, acceptedAt = now,
                 acceptedMs = nowMs(), lastPresentMs = nowMs() }
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

--- The squares of the camp that must be good ground, from its centre: where
--- the raider is put down, every square of every machine, and where the
--- Doctor stands in front of his station.
function S.campKeep()
    local out = { { 0, 0 }, { C.OutpostStand[1], C.OutpostStand[2] } }
    for _, m in ipairs(C.OutpostInstalls) do
        for _, t in ipairs(IN.Sprites[m[1]].W) do
            table.insert(out, { m[2] + t[1], m[3] + t[2] })
        end
        if m[1] == "emh_station" then
            local dx, dy = IS.doctorSquare(m[2], m[3], "W")
            table.insert(out, { dx, dy })
        end
    end
    return out
end

--- The squares a camp's clearing covers, as { { dx, dy, ray } } from its centre:
--- a disc of C.OutpostClearing, and C.OutpostSpokes straight alleys
--- C.OutpostSpokeWidth wide running C.OutpostSpokeLength on out from its edge
--- -- a sun and its rays (played 2026-09-29: somewhere to run down, turn
--- and fire back along). The rays are turned by the camp's own spokeAngle,
--- rolled once, so no two camps are the same.
function S.clearShape(camp)
    if not camp.spokeAngle then camp.spokeAngle = roll(3600) / 3600 * 2 * math.pi end
    local R = C.OutpostClearing
    local seen, out = {}, {}
    local function add(dx, dy, ray)
        local key = dx .. "," .. dy
        if not seen[key] then
            seen[key] = true
            table.insert(out, { dx, dy, ray })
        end
    end
    for dy = -R, R do
        for dx = -R, R do
            if dx * dx + dy * dy <= R * R then add(dx, dy) end
        end
    end
    local half = (C.OutpostSpokeWidth - 1) / 2
    for i = 0, C.OutpostSpokes - 1 do
        local a = camp.spokeAngle + i * 2 * math.pi / C.OutpostSpokes
        local ux, uy = math.cos(a), math.sin(a)
        for t = R - 1, R + C.OutpostSpokeLength, 0.5 do
            for w = -half, half, 0.5 do
                add(math.floor(ux * t - uy * w + 0.5), math.floor(uy * t + ux * w + 0.5), true)
            end
        end
    end
    return out
end

--- Lays a dirt path on a square of a ray, so the alleys stand out on the
--- grass (played 2026-09-29). Vanilla's own shovel does exactly this on the
--- server (server/ClientCommands.lua:195): the floor's sprite, its blend
--- edges taken off, and the new sprite sent to every client. Only the
--- county's own ground: a road, a floor somebody laid or water is left be.
--- True when it laid one.
local function dirtPath(sq)
    local f = sq and U.try("raids.pathFloor", function() return sq:getFloor() end)
    if not f then return false end
    local name = U.try("raids.pathName", function() return f:getSprite():getName() end)
    if type(name) ~= "string" then return false end
    if name:sub(1, 18) ~= "blends_natural_01_" and name:sub(1, 27) ~= "floors_exterior_natural_01_" then
        return false
    end
    for _, dirt in ipairs(C.OutpostPathTiles) do
        if name == dirt then return false end
    end
    if U.try("raids.pathWater", function() return f:getSprite():getProperties():has(IsoFlagType.water) end) then
        return false
    end
    local tile = C.OutpostPathTiles[roll(#C.OutpostPathTiles) + 1]
    return U.try("raids.path", function()
        f:setSprite(getSprite(tile))
        f:RemoveAttachedAnims()
        f:transmitUpdatedSpriteToClients()
        return true
    end) == true
end
S.dirtPath = dirtPath

-- Per camp, the squares of its clearing already done. The server's alone and
-- never published: it runs to a couple of thousand keys, and the raid record
-- goes to every client whenever it changes (DEV_GUIDE, *State that is
-- transmitted whole*). Lost with a restart, which only means the next pass
-- looks at every square again.
local clearedOf = setmetatable({}, { __mode = "k" })

--- Clears the wilderness off every loaded square of the camp's clearing
--- (S.clearShape) not cleared yet, so nobody fights in the bushes. Only what
--- grows or blows there goes (clearWild); anything built stays. A square
--- whose ground is not loaded is left for the next pass: returns how many
--- things went and how many squares are still to do.
function S.clearAround(camp)
    local done = clearedOf[camp] or {}
    clearedOf[camp] = done
    local took, left = 0, 0
    for _, d in ipairs(S.clearShape(camp)) do
        local key = d[1] .. "," .. d[2]
        if not done[key] then
            local x, y = camp.cx + d[1], camp.cy + d[2]
            if U.chunkLoaded(x, y, camp.z) then
                -- Every square: clearWild only ever takes wilderness, so a
                -- square with something built on it keeps that and loses its
                -- tree.
                local sq = U.square(x, y, camp.z, false)
                took = took + clearWild(sq)
                if d[3] then dirtPath(sq) end
                done[key] = true
            else
                left = left + 1
            end
        end
    end
    camp.clearLeft = left
    if left == 0 then clearedOf[camp] = nil end
    return took, left
end

--- The best centre for the camp within C.OutpostSearch of (tx, ty): the
--- square whose whole camp area has the most good ground, as long as its
--- kept squares (S.campKeep) are good and at least nine in ten of the rest
--- are. Nil when the
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
    local keep = S.campKeep()
    local best, bestN, bestD = nil, -1, nil
    for cy = ty - R, ty + R do
        for cx = tx - R, tx + R do
            local keepOk = true
            for _, p in ipairs(keep) do
                local gj, gi = cy + p[2] - y0 + 1, cx + p[1] - x0 + 1
                if not (good[gj] and good[gj][gi]) then keepOk = false break end
            end
            if keepOk then
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

--- Builds the camp at (cx, cy). The machines are real installations,
--- recorded against the raid to be taken away when it is over; the tents
--- and crates stay.
function S.buildCamp(raid, cx, cy, z)
    raid.camp = { cx = cx, cy = cy, z = z, scenery = {}, machines = {} }
    -- A clearing first: the trees and the undergrowth off the camp and a
    -- wide ring round it, where the fight is.
    local cleared = S.clearAround(raid.camp)
    for _, m in ipairs(C.OutpostInstalls) do
        -- The core arrives with a crystal burning, as the shuttle's does once
        -- loaded: a full reserve, no spares, lit.
        local extra = { raid = raid.id, owner = "Captain Titus" }
        if m[1] == "warp_core" then
            extra.power, extra.crystals, extra.dark = C.PowerMax, 0, false
        end
        local id, rec = IS.place(m[1], cx + m[2], cy + m[3], z, "W", extra)
        table.insert(raid.camp.machines, id)
        if m[1] == "warp_core" then raid.camp.coreX, raid.camp.coreY = IN.centre(rec) end
    end
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

--- A world item of this full type lying on the square (the Doctor), or nil.
local function worldItemOn(sq, fullType)
    return U.try("raids.worldItem", function()
        local list = sq:getWorldObjects()
        for i = 0, list:size() - 1 do
            local w = list:get(i)
            local it = w and w:getItem()
            if it and it:getFullType() == fullType then return w end
        end
        return nil
    end)
end

--- Takes one lent machine away, now where its ground is loaded and later
--- where it is not.
function S.takeMachine(id)
    local d = Rd.store()
    for _, left in ipairs(IS.remove(id)) do table.insert(d.removals, left) end
end

local function serviceRemovals()
    local d = Rd.store()
    for i = #d.removals, 1, -1 do
        local s = d.removals[i]
        if U.chunkLoaded(s.x, s.y, s.z) then
            local sq = U.square(s.x, s.y, s.z, false)
            local found = nil
            if sq and s.item then found = worldItemOn(sq, s.item)
            elseif sq and s.sprite then found = U.findSprite(sq, s.sprite) end
            if found then U.try("raids.remove", function() sq:transmitRemoveItemFromSquare(found) end) end
            table.remove(d.removals, i)
        end
    end
    -- A lent machine with no raid of its own running -- a save closed in the
    -- middle of one -- goes the same way.
    local live = d.raid and d.raid.id
    local stray = {}
    for id, m in pairs(IN.state().machines) do
        if m.raid and m.raid ~= live then table.insert(stray, id) end
    end
    for _, id in ipairs(stray) do S.takeMachine(id) end
end

---------------------------------------------------------------------------
-- The waves, and the end
---------------------------------------------------------------------------
--- The raid's own dead still standing, by the server's zombie list: how
--- many, and "id:pace,..." for the clients (Rd.setZedIds).
function S.standing(raid)
    local n, ids = 0, {}
    U.try("raids.count", function()
        local list = getCell():getZombieList()
        for i = 0, list:size() - 1 do
            local z = list:get(i)
            if z and not z:isDead() and z:getModData()[C.RaidZedKey] == raid.id then
                n = n + 1
                local id = z:getOnlineID()
                if id and id >= 0 then table.insert(ids, id .. ":" .. (Rd.paceOf(z) or "walk")) end
            end
        end
    end)
    return n, table.concat(ids, ",")
end

--- Ground one can be beamed onto: a floor, nothing solid or standing on it,
--- no water.
local function standable(sq)
    if not sq or not W.squareIsClear(sq) then return false end
    return U.try("raids.water", function()
        return not sq:getFloor():getSprite():getProperties():has(IsoFlagType.water)
    end) == true
end

--- Where the next one comes down: somewhere in a ring round the camp's warp
--- core, from every side -- the purge vents where the power is. Round the
--- core and not the raider (played 2026-09-29), so a raider can fall back to
--- the edge of the clearing and have them all in front. Nil when nowhere on
--- the ring will do.
function S.spawnSquare(camp)
    local ox, oy = camp.coreX or camp.cx + 0.5, camp.coreY or camp.cy + 0.5
    local lo, hi = C.RaidSpawnMin, C.RaidSpawnMax
    for _ = 1, 16 do
        local a = roll(3600) / 3600 * 2 * math.pi
        local r = lo + roll((hi - lo) * 10 + 1) / 10
        local x = math.floor(ox + math.cos(a) * r)
        local y = math.floor(oy + math.sin(a) * r)
        if U.chunkLoaded(x, y, camp.z) and standable(U.square(x, y, camp.z, false)) then return x, y end
    end
    return nil
end

--- One of the dead, beamed in round the camp's warp core. A runner is never a Borg
--- (they never run, BORG.md); a walker is a Borg C.RaidBorgShare of the time.
local function spawnOne(raid, runner)
    local camp = raid.camp
    local x, y = S.spawnSquare(camp)
    if not x then return 0 end
    local outfit
    if not runner and roll(100) < math.floor(C.RaidBorgShare * 100) then
        outfit = roll(2) == 0 and C.BorgDrone or C.BorgAssimilated
    else
        outfit = C.RaidOutfits[roll(#C.RaidOutfits) + 1]
    end
    local pace = runner and "run" or "walk"
    local list = U.try("raids.spawn", function()
        return addZombiesInOutfit(x, y, camp.z, 1, outfit, 50)
    end)
    local got = 0
    U.try("raids.tagZed", function()
        for i = 0, list:size() - 1 do
            local zed = list:get(i)
            zed:getModData()[C.RaidZedKey] = raid.id
            Rd.markZed(zed, pace)
            U.try("raids.drive", Rd.drive, zed)
            got = got + 1
        end
    end)
    if got > 0 then
        -- The transporter's column where it comes down, on every screen
        -- (BEAM.md): fixed to the square, since a zombie has no player id.
        raid.beamed = (raid.beamed or 0) + 1
        Net.toAll("beamFx", { id = "raid" .. raid.beamed, phase = "in", fixed = true,
                              x = x + 0.5, y = y + 0.5, z = camp.z })
    end
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

--- Ends the fight. `why` says what lost it, for the raiders' note: "time"
--- (C.RaidHardLimitMs), "left" (nobody there for C.RaidAbandonMs) or
--- "ground" (nowhere to build the camp).
local function finish(raid, won, why)
    local d = Rd.store()
    raid.state = won and "won" or "lost"
    raid.endMs = nowMs() + (won and C.RaidLootMs or 3000)
    if won then
        for _, p in ipairs(present(raid)) do reward(p) end
    end
    d.nextAt = U.worldHours() + interval()
    Rd.publish()
    Net.toAll(won and "raidWon" or "raidLost", { secs = won and math.floor(C.RaidLootMs / 1000) or 0, why = why })
    U.log("raids: %s %s%s", raid.id, won and "is won" or "is lost", why and (" (" .. why .. ")") or "")
end

--- Every raider still in it goes home; the pad and machines go; it is over.
local function close(raid)
    local d = Rd.store()
    for name in pairs(raid.members or {}) do
        local p = playerNamed(name)
        if p and alive(p) then S.sendHome(p) end
    end
    if raid.camp then
        -- A camp built before the 2026-09-29 rework carried its pad and
        -- scenery machines here.
        removeScenery(raid.camp.scenery)
        for _, id in ipairs(raid.camp.machines or {}) do S.takeMachine(id) end
    end
    d.raid = nil
    Net.toAll("raidZeds", { list = "" })
    Rd.publish()
    U.log("raids: %s is over", raid.id)
end

-- When the last wave came (real ms); on S so a test can time the next.
S.lastWaveMs = 0

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
            finish(raid, false, "ground")
            return
        end
        S.buildCamp(raid, cx, cy, raid.tz)
        raid.state = "live"
        raid.startedAt = U.worldHours()
        raid.startedMs = nowMs()
        raid.lastPresentMs = raid.startedMs
        -- The first wave a moment from now, not this instant: a raider
        -- materialising into the first dozen is a raider who never saw the camp.
        S.lastWaveMs = nowMs() - C.RaidWaveMs + C.RaidFirstWaveMs
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
        local alive, ids = S.standing(raid)
        if alive ~= raid.alive then
            raid.alive = alive
            Net.toAll("raidZeds", { list = ids })
            Rd.publish()
        end
        -- One wave at a time (played 2026-09-29: a second dozen on top of the
        -- first was a death): the next waits until every one of the last is
        -- down, and then C.RaidWaveMs more -- the clock restarts every look
        -- that finds one standing.
        if alive > 0 then
            S.lastWaveMs = now
            return
        end
        if (raid.released or 0) >= raid.n then
            finish(raid, true)
            return
        end
        if now - S.lastWaveMs < C.RaidWaveMs then return end
        local here = present(raid)
        if #here == 0 then return end
        S.lastWaveMs = now
        -- The clearing's edge, where its ground was not loaded at the build.
        if (raid.camp.clearLeft or 0) > 0 then S.clearAround(raid.camp) end
        raid.wave = (raid.wave or 0) + 1
        local k = math.min(C.raidWaveSize(raid.wave), raid.n - raid.released)
        -- Exactly C.RaidRunnerShare of every wave runs, never left to the
        -- dice: a wave that rolled mostly runners left nowhere to fall back to.
        local runners = math.floor(k * C.RaidRunnerShare + 0.5)
        for i = 1, k do raid.released = raid.released + spawnOne(raid, i <= runners) end
        raid.alive, ids = S.standing(raid)
        Net.toAll("raidZeds", { list = ids })
        Rd.publish()
        return
    end
    if (raid.state == "won" or raid.state == "lost") and nowMs() >= (raid.endMs or 0) then
        close(raid)
    end
end

--- A running raid's limits, in real time: abandoned, or too long. They were
--- game minutes, and a game hour is two and a half real minutes at the
--- default day length -- the first raid long enough to need it was ended
--- mid-fight, five waves in, "lost" (played 2026-09-29).
function S.serviceLimits()
    local raid = Rd.raid()
    if not raid or not Rd.joinable(raid) then return end
    local now = nowMs()
    raid.acceptedMs = raid.acceptedMs or now
    raid.lastPresentMs = raid.lastPresentMs or now
    if #present(raid) > 0 then raid.lastPresentMs = now end
    if now - (raid.startedMs or raid.acceptedMs) > C.RaidHardLimitMs then
        finish(raid, false, "time")
    elseif now - raid.lastPresentMs > C.RaidAbandonMs then
        finish(raid, false, "left")
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
end)

local tick = 0
Events.OnTick.Add(function()
    tick = tick + 1
    if tick < 30 then return end
    tick = 0
    U.try("raids.limits", S.serviceLimits)
    U.try("raids.raid", S.serviceRaid)
end)

return S
