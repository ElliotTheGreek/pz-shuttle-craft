--[[ Shuttlecraft -- boarding clearance: the authority (ACCESS.md).

    Everything that changes the clearance record or the world for it, where
    the world is authoritative -- single player, or the server:

      * the grandfather check, once per world;
      * the story's reveals: the debrief after the first rescue (a salvage
        contact where the ensign's kit went down) and the Doctor's rule after
        the second, each a flag on the channel;
      * the field station's enhancer, put on the floor of its Stores room the
        first time that deck is built and loaded, and counted when it is taken;
      * a salvage site recovered, counted; debris strewn round a probe's;
      * the Borg's nanoprobe sample, into the corpse's inventory;
      * screening, at the Doctor;
      * deploying the enhancers, holding the lock and resolving it.

    Every timer runs on the game-minute tick **outside** any loaded-ground
    branch (DEV_GUIDE: *A guard gated on loaded ground never sees the case it
    exists for*). Only "is each enhancer still standing there" needs the
    ground, and an unloaded square is "cannot tell", never "gone".
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_Probes"
require "TREK/TREK_Access"
require "TREK/TREK_Adirondack"
require "TREK/TREK_FieldStation"
require "TREK/TREK_EMH"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Ship = TREK.Ship
local Probes = TREK.Probes
local Ac = TREK.Access
local A = TREK.Adirondack
local FS = TREK.FieldStation

local S = {}
TREK.AccessServer = S

-- username -> world hour a lift offered at the lock lapses. Not saved: a lift
-- is for the minute the lock resolves, and a restart ends it.
local lifts = {}

local function deny(player, why)
    Net.toClient(player, "denied", { why = why })
end

local function alive(player)
    return player ~= nil and U.try("access.dead", function() return player:isDead() end) == false
end

local function roll(n)
    if n <= 1 then return 0 end
    return U.try("access.roll", function() return ZombRand(n) end) or 0
end

local function comms(kind)
    if TREK.CommsServer then TREK.CommsServer.event(kind) end
end

--- The world items of `fullType` on a square.
local function itemsOn(sq, fullType)
    local out = {}
    U.try("access.itemsOn", function()
        local items = sq:getWorldObjects()
        if not items then return end
        for i = 0, items:size() - 1 do
            local w = items:get(i)
            local it = w and w:getItem()
            if it and it:getFullType() == fullType then table.insert(out, w) end
        end
    end)
    return out
end

--- Ground a thing can lie on: a floor, nothing solid, no water.
local function goodGround(sq)
    if not sq then return false end
    local ok = U.try("access.ground", function()
        return sq:getFloor() ~= nil and not sq:isSolid() and not sq:isSolidTrans()
    end)
    if ok ~= true then return false end
    local wet = U.try("access.water", function()
        return sq:getFloor():getSprite():getProperties():has(IsoFlagType.water)
    end)
    return wet ~= true
end

--- Puts one item on a square, straightened. The item, or nil.
local function lay(sq, fullType)
    local item = U.try("access.lay", function()
        return sq:AddWorldInventoryItem(fullType, 0.5, 0.5, 0.0)
    end)
    if not item then
        U.log("WARN access: %s could not be put on the ground", tostring(fullType))
        return nil
    end
    -- A dropped world model picks its own yaw (DEV_GUIDE). An enhancer is a
    -- rod standing up; any heading reads the same, and a fixed one tests.
    U.try("access.straighten", function()
        item:setWorldXRotation(0)
        item:setWorldYRotation(0)
        item:setWorldZRotation(0)
    end)
    return item
end

---------------------------------------------------------------------------
-- Grandfathering (ACCESS.md 4)
---------------------------------------------------------------------------
--- Once per world: a server that has ever built one of her own decks was
--- already visiting her, and the gate is open there for good.
function S.checkGrandfather()
    local d = Ac.store()
    if d.checked then return false end
    d.checked = true
    local st = ModData.getOrCreate(A.StateKey)
    local decks = type(st.decks) == "table" and st.decks or {}
    for _, k in ipairs(A.decksOf("adk")) do
        if decks[k] ~= nil then
            d.grandfathered = true
            break
        end
    end
    U.log("access: %s", d.grandfathered and "this world was already visiting the Adirondack; "
          .. "she is open to it for good" or "clearance is kept from here on")
    Ac.publish()
    return true
end

---------------------------------------------------------------------------
-- The story's reveals
---------------------------------------------------------------------------
local function crewOrigin()
    for _, p in ipairs(U.players()) do
        local x, y = Ship.worldOrigin(p)
        if x and y then return x, y end
    end
    return nil
end

--- A square `min`..`max` squares from ox, oy in a random direction, inside
--- the world, or nil.
local function somewhere(ox, oy, min, max)
    for _ = 1, 24 do
        local bearing = roll(3600) / 3600 * 2 * math.pi
        local distance = min + roll(max - min + 1)
        local x = math.floor(ox + math.cos(bearing) * distance)
        local y = math.floor(oy + math.sin(bearing) * distance)
        if U.inWorld(x, y) then return x, y end
    end
    return nil
end

--- The first rescue's debrief: where their away kit went down. A salvage
--- contact, an approximate fix, measured from where they were found (or
--- from the crew, for a save that rescued somebody before this existed).
--- Returns the contact, or nil when there was nowhere to put it yet.
function S.debrief(name, fromX, fromY)
    local d = Ac.store()
    local ox, oy = fromX, fromY
    if not ox then ox, oy = crewOrigin() end
    if not ox then return nil end
    local tx, ty = somewhere(ox, oy, C.DebriefMinDistance, C.DebriefMaxDistance)
    if not tx then return nil end
    local sp = C.DebriefSpread
    local fx, fy = tx + roll(sp * 2 + 1) - sp, ty + roll(sp * 2 + 1) - sp
    if not U.inWorld(fx, fy) then fx, fy = tx, ty end
    local contact = Probes.addContact("salvage", fx, fy, 0, "debrief", true)
    if not contact then return nil end
    contact.item = C.EnhancerItem
    contact.source = "debrief"
    Probes.publish()
    d.told.lock = true
    d.debrief = true
    Ac.publish()
    comms("accessLock")
    local rx, ry = crewOrigin()
    local args = { name = name }
    if rx then
        args.distance = math.floor(math.sqrt(U.dist2(rx, ry, fx, fy)))
        args.compass = U.compass(rx, ry, fx, fy)
    end
    Net.toAll("accessDebrief", args)
    U.log("access: the debrief puts an away kit near %d,%d (contact %s)", fx, fy, contact.id)
    return contact
end

--- The Doctor's rule becomes known.
function S.tellScreen()
    local d = Ac.store()
    if d.told.screen then return false end
    d.told.screen = true
    Ac.publish()
    comms("accessScreen")
    Net.toAll("accessScreenTold", {})
    U.log("access: the Doctor's biofilter rule is known")
    return true
end

--- After a rescue, and every minute: the reveals the count has earned.
function S.serviceStory(name, fromX, fromY)
    if not Ac.earned() then return end
    local d = Ac.store()
    local n = Ac.rescued()
    if n >= 1 and not d.told.lock then S.debrief(name, fromX, fromY) end
    if (n >= 2 or d.lock) and not d.told.screen then S.tellScreen() end
end

--- Called by the rescue handler once the channel has counted it.
function S.onRescue(player, contact)
    S.serviceStory(contact and contact.name, contact and contact.ex, contact and contact.ey)
end

---------------------------------------------------------------------------
-- Enhancers: recovered, and the field station's
---------------------------------------------------------------------------
local function recovered(where)
    local d = Ac.store()
    d.recovered = (tonumber(d.recovered) or 0) + 1
    Ac.publish()
    Net.toAll("accessRecovered", { n = Ac.recoveredCount(), of = C.EnhancersNeeded })
    U.log("access: a pattern enhancer is recovered (%s); %d so far", where, d.recovered)
end

--- A salvage contact's enhancer has been picked up (TREK_Server's contact pass).
function S.onRecovered(contact)
    if contact.kind ~= "salvage" then return end
    recovered(contact.source or "salvage")
end

--- A probe's salvage site is on the ground: strew a little wreckage round it.
function S.onPlaced(contact, sq)
    if contact.kind ~= "salvage" or contact.source ~= "probe" then return end
    local cx = U.try("access.px", function() return math.floor(sq:getX()) end)
    local cy = U.try("access.py", function() return math.floor(sq:getY()) end)
    if not cx then return end
    local z = contact.z or 0
    for i, id in ipairs(C.SalvageDebris) do
        local a = (i / #C.SalvageDebris) * 2 * math.pi
        local s2 = U.square(cx + math.floor(math.cos(a) * 2 + 0.5),
                            cy + math.floor(math.sin(a) * 2 + 0.5), z, false)
        if goodGround(s2) then lay(s2, id) end
    end
end

--- Whether a probe's find should be a salvage site: the lock is owed and
--- known about, no site is live, and the ship has not already seen a full set
--- -- or has, and nobody online is carrying one (lost on a body, burned in a
--- house: a later probe finds another, so the chain cannot be soft-locked).
function S.salvageOwed()
    if not Ac.earned() then return false end
    local d = Ac.store()
    if d.lock or not d.told.lock then return false end
    for _, c in ipairs(Probes.contacts()) do
        if c.kind == "salvage" and not Probes.isResolved(c.status) then return false end
    end
    if Ac.recoveredCount() < C.EnhancersNeeded then return true end
    local held = 0
    for _, p in ipairs(U.players()) do held = held + Ac.carried(p, C.EnhancerItem) end
    return held < C.EnhancersNeeded
end

--- A probe's roll for a salvage site. Never the first probe of a save
--- (TREK_Server asks only once one has found something).
function S.salvageFor()
    if not S.salvageOwed() then return false end
    return roll(100) < math.floor(C.ProbeSalvageShare * 100)
end

--- The room squares of `name` on deck k, nearest its middle first.
local function roomSquares(k, name)
    local L = A.Layout
    local deck = L.decks[k]
    if not deck then return {} end
    local out, sx, sy = {}, 0, 0
    for ly = 0, L.H - 1 do
        for lx = 0, L.W - 1 do
            local r = A.roomAt(k, lx, ly)
            if r and r.name == name then
                table.insert(out, { lx, ly })
                sx, sy = sx + lx, sy + ly
            end
        end
    end
    if #out == 0 then return out end
    local cx, cy = sx / #out, sy / #out
    table.sort(out, function(a, b)
        local da = (a[1] - cx) ^ 2 + (a[2] - cy) ^ 2
        local db = (b[1] - cx) ^ 2 + (b[2] - cy) ^ 2
        if da ~= db then return da < db end
        if a[2] ~= b[2] then return a[2] < b[2] end
        return a[1] < b[1]
    end)
    return out
end
S.roomSquares = roomSquares

--- The field station's enhancer: placed once its deck is built and loaded,
--- and counted once when it is gone from its square.
function S.serviceStation()
    if not Ac.earned() then return end
    local d = Ac.store()
    local st = d.station
    if st.taken or d.lock then return end
    if st.placed then
        if not U.chunkLoaded(st.x, st.y, st.z) then return end
        local sq = U.square(st.x, st.y, st.z, false)
        if not sq then return end
        if #itemsOn(sq, C.EnhancerItem) == 0 then
            st.taken = true
            recovered("the field station")
        end
        return
    end
    local k = FS.firstDeck()
    local AS = TREK.AdirondackServer
    if not k or not AS or not AS.deckCurrent(k) then return end
    for _, p in ipairs(roomSquares(k, C.StationEnhancerRoom)) do
        local x, y = A.at(k, p[1], p[2])
        if not U.chunkLoaded(x, y, A.Z) then return end
        local sq = U.square(x, y, A.Z, false)
        if goodGround(sq) then
            if not lay(sq, C.EnhancerItem) then return end
            st.placed, st.x, st.y, st.z = true, x, y, A.Z
            Ac.publish()
            U.log("access: the field station's pattern enhancer is in its %s at %d,%d",
                  C.StationEnhancerRoom, x, y)
            return
        end
    end
    U.warnOnce("access.stationRoom", "access: no clear floor in the field station's %s for its "
               .. "pattern enhancer", C.StationEnhancerRoom)
end

---------------------------------------------------------------------------
-- The Borg's sample (ACCESS.md 3.6)
---------------------------------------------------------------------------
--- A Borg killed where the world is authoritative carries a nanoprobe
--- sample into its corpse. `IsoZombie.onKilled` rolls the inventory first
--- (bci 38-45) and fires OnZombieDead after, so this lands beside vanilla's
--- own loot. Only while screening is asked for and needs one.
function S.onZombieDead(z)
    if not z or not Ac.earned() or not Ac.sampleNeeded() then return false end
    -- Never ask an undressed zombie its outfit (DEV_GUIDE: the getter dresses it).
    if z:shouldDressInRandomOutfit() then return false end
    local B = TREK.Borg
    if not B or not B.isBorgOutfit(z:getOutfitName()) then return false end
    local item = instanceItem(C.NanoprobeItem)
    if not item then return false end
    z:getInventory():AddItem(item)
    return true
end

Events.OnZombieDead.Add(function(z)
    U.try("access.sample", S.onZombieDead, z)
end)

---------------------------------------------------------------------------
-- Screening (ACCESS.md 3.7)
---------------------------------------------------------------------------
--- Tells the owning client what the server's copy of them says.
function S.publishMine(player)
    Net.toClient(player, "accessMine", { who = Ship.usernameOf(player),
                                         screened = Ac.screened(player) })
end

--- Takes `n` of `fullType` out of a character's pack. True when it did.
local function take(player, fullType, n)
    local got = {}
    U.try("access.take", function()
        local inv = player:getInventory()
        local list = inv:getAllTypeRecurse(fullType:match("%.(.+)$"))
        for i = 0, list:size() - 1 do
            local it = list:get(i)
            if #got < n and it:getFullType() == fullType then table.insert(got, it) end
        end
    end)
    if #got < n then return false end
    for _, it in ipairs(got) do
        U.try("access.remove", function()
            local c = it:getContainer() or player:getInventory()
            c:Remove(it)
            if isServer() then sendRemoveItemFromContainer(c, it) end
        end)
    end
    return true
end

Net.onServer("accessAsk", function(player)
    if not alive(player) then return end
    S.publishMine(player)
end)

Net.onServer("accessScreen", function(player)
    if not alive(player) then return end
    local why = TREK.EMH.refusal(player)
    if why then deny(player, why) return end
    why = Ac.screenRefusal(player)
    if why then deny(player, why) return end
    if not TREK.Energy.energize(player, "screen", C.ScreenCost, { why = "emhNoPower" }) then
        return
    end
    if Ac.sampleNeeded() and not take(player, C.NanoprobeItem, 1) then
        -- Asked a moment ago and there; gone now. Nothing to screen against.
        deny(player, "accNoSample")
        return
    end
    local md = player:getModData()
    md[C.ScreenKey] = true
    S.publishMine(player)
    Net.toClient(player, "accessScreened", {})
    U.log("access: %s passed the biofilter screening", Ship.usernameOf(player))
end)

---------------------------------------------------------------------------
-- The lock (ACCESS.md 3.8-3.10)
---------------------------------------------------------------------------
--- Three squares round (x, y) for the enhancers, or nil.
local function triangle(x, y, z)
    local out, used = {}, {}
    for i = 0, 2 do
        local a = math.pi / 2 + i * 2 * math.pi / 3
        local tx = math.floor(x + math.cos(a) * C.LockRadius + 0.5)
        local ty = math.floor(y + math.sin(a) * C.LockRadius + 0.5)
        local found = nil
        for ring = 0, 2 do
            for dx = -ring, ring do
                for dy = -ring, ring do
                    local key = (tx + dx) .. "," .. (ty + dy)
                    if not found and (math.abs(dx) == ring or math.abs(dy) == ring)
                       and not used[key] and goodGround(U.square(tx + dx, ty + dy, z, false)) then
                        found = { tx + dx, ty + dy, z }
                        used[key] = true
                    end
                end
            end
        end
        if not found then return nil end
        table.insert(out, found)
    end
    return out
end

Net.onServer("accessDeploy", function(player)
    if not alive(player) then return end
    if not Ship.canUse(player) then deny(player, "access") return end
    local why = Ac.deployRefusal(player)
    if why then deny(player, why) return end
    local px, py, pz = player:getX(), player:getY(), math.floor(player:getZ())
    local sqs = triangle(math.floor(px), math.floor(py), pz)
    if not sqs then deny(player, "accDeployRoom") return end
    if not take(player, C.EnhancerItem, C.EnhancersNeeded) then
        deny(player, "accNeedThree")
        return
    end
    for _, p in ipairs(sqs) do lay(U.square(p[1], p[2], p[3], false), C.EnhancerItem) end
    local who = Ship.usernameOf(player)
    Ac.store().job = { x = math.floor(px), y = math.floor(py), z = pz, sq = sqs,
                       progress = 0, by = who }
    Ac.publish()
    Net.toAll("accessLockStarted", { by = who, minutes = C.LockMinutes })
    U.log("access: %s deployed the pattern enhancers at %d,%d", who, math.floor(px), math.floor(py))
end)

--- The crew standing close enough to hold the lock, by the server's copy.
local function holders(job)
    local out = {}
    for _, p in ipairs(U.players()) do
        local ok = alive(p) and Ship.canUse(p)
        if ok then
            local x = U.try("access.hx", function() return p:getX() end)
            local y = U.try("access.hy", function() return p:getY() end)
            local z = U.try("access.hz", function() return p:getZ() end)
            if x and math.floor(z) == job.z
               and U.dist2(x, y, job.x + 0.5, job.y + 0.5) <= C.LockHoldRange * C.LockHoldRange then
                table.insert(out, p)
            end
        end
    end
    return out
end

--- The enhancers of a job: true when every one whose ground can be looked
--- at is still there, and the world objects that were found.
local function standing(job)
    local found = {}
    for _, p in ipairs(job.sq) do
        if U.chunkLoaded(p[1], p[2], p[3]) then
            local sq = U.square(p[1], p[2], p[3], false)
            if sq then
                local w = itemsOn(sq, C.EnhancerItem)[1]
                if not w then return false, found end
                table.insert(found, { w = w, sq = sq })
            end
        end
    end
    return true, found
end

local function resolve(job, found, hold)
    local d = Ac.store()
    for _, f in ipairs(found) do
        U.try("access.spend", function() f.sq:transmitRemoveItemFromSquare(f.w) end)
    end
    d.lock = true
    d.job = nil
    d.told.lock = true
    Ac.publish()
    comms("accessLocked")
    S.serviceStory()
    Net.toAll("accessLocked", {})
    local until_ = U.worldHours() + C.LockLiftHours
    for _, p in ipairs(hold) do
        local why = Ac.refusal(p)
        if why then
            Net.toClient(p, "accessLeftBehind", { why = why })
        else
            lifts[Ship.usernameOf(p)] = until_
            Net.toClient(p, "accessLift", {})
            -- A rank earned while she was out of reach is given now: the
            -- rescue said it would wait (TREK_TraitsServer.onRescue).
            local TS, Cap = TREK.TraitsServer, TREK.Captain
            if TS and Cap and TREK.Traits and Cap.promotionDue(p) then
                TREK.Traits.note(p, "IGUI_TREK_PromotionDue",
                                 getText("UI_trait_trek_" .. C.Ranks[TS.earnedRank(p)]), 255, 220, 120)
            end
        end
    end
    U.log("access: the Adirondack has her lock; %d of the crew were holding it", #hold)
end

--- The lock being held: broken, paused, advanced, humming, resolved.
function S.serviceLock()
    local d = Ac.store()
    local job = d.job
    if not job then return end
    if d.lock or not Ac.earned() then
        d.job = nil
        Ac.publish()
        return
    end
    local ok, found = standing(job)
    if not ok then
        d.job = nil
        Ac.publish()
        Net.toAll("accessLockBroken", {})
        U.log("access: an enhancer was moved; the lock is broken")
        return
    end
    local hold = holders(job)
    if #hold == 0 then
        if not job.paused then
            job.paused = true
            Ac.publish()
            Net.toAll("accessLockPaused", {})
        end
        return
    end
    job.paused = nil
    job.progress = (tonumber(job.progress) or 0) + 1
    -- The hum: the engine's zombie-attraction noise, from an enhancer.
    if #found > 0 and (not job.beaconAt or job.progress - job.beaconAt >= C.LockBeaconMinutes) then
        job.beaconAt = job.progress
        U.try("access.hum", function()
            addSound(found[1].w, job.x, job.y, job.z, C.LockBeaconRadius, C.LockBeaconVolume)
        end)
    end
    if job.progress >= C.LockMinutes then
        resolve(job, found, hold)
        return
    end
    Ac.publish()
end

--- True, once, for a player the lock has offered a lift to: the move
--- handler asks this for `lockBeam`, and it is spent when it answers yes.
function S.takeLift(player)
    local who = Ship.usernameOf(player)
    local until_ = who and lifts[who]
    if not until_ then return false end
    lifts[who] = nil
    return U.worldHours() <= until_
end

---------------------------------------------------------------------------
-- Timers
---------------------------------------------------------------------------
Events.OnInitGlobalModData.Add(function()
    U.try("access.grandfather", S.checkGrandfather)
end)

Events.EveryOneMinute.Add(function()
    U.try("access.grandfather", S.checkGrandfather)
    U.try("access.story", S.serviceStory)
    U.try("access.station", S.serviceStation)
    U.try("access.lock", S.serviceLock)
end)

return S
