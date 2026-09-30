--[[ Shuttlecraft -- the perimeter phaser sentry: the authority (SENTRY.md).

      deploySentry {id}    the sentry the player is really carrying (by item
                           id, on the server's own copy of their inventory,
                           counted out) is set down on the square in front of
                           them as a world item, written with an id, and
                           entered in the list; it arms C.SentryArmMs later
      rechargeSentry {id}  at a warp core, for C.SentryRechargeCost of that
                           core's power (the ledger bills the pool the
                           command runs under): full again

    **The sentries set down** are TREK_Sentries global mod data, the server's
    alone -- nothing on a client needs the list. A sentry is found again by
    the id written on it; one that is gone from its square (a player picked
    it up, as they may with any item on the ground) leaves the list, and
    keeps its charge on the item.

    **A shot is the engine's own server-side hit.** IsoTrap.explosion hits
    every character in a blast with `IsoMovingObject.Hit(weapon, attacker,
    damage, false, 1.0)` on the server (bci 121), and IsoGameCharacter.Hit is
    the whole pipeline a gunshot runs -- processHitDamage, then
    hitConsequences, where a zombie dies; IsoZombie.Hit then tells the
    clients (bci 233-254). The attacker is the sentry's owner when they are
    here, for the kill; the cell's stand-in otherwise, as a trap's is. Every
    client is sent the bolt (`sentryShot`), which TREK_PhaserFX draws.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_Sentry"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local SN = TREK.Sentry

local SS = {}
TREK.SentryServer = SS

SS.Key = "TREK_Sentries"

local function nowMs()
    return U.try("sentry.ms", function() return getTimestampMs() end) or 0
end

local function deny(player, why)
    Net.toClient(player, "denied", { why = why })
end

local function nameOf(p)
    return TREK.Ship and TREK.Ship.usernameOf(p) or "?"
end

local function alive(p)
    return p ~= nil and U.try("sentry.dead", function() return p:isDead() end) == false
end

--- The list: { next, set = { [id] = { x, y, z, owner, armedMs, lastMs } } }.
--- Keys are strings, the registry's rule (TREK_Installations).
function SS.state()
    local s = ModData.getOrCreate(SS.Key)
    s.next = tonumber(s.next) or 1
    s.set = type(s.set) == "table" and s.set or {}
    return s
end

function SS.count()
    local n = 0
    for _ in pairs(SS.state().set) do n = n + 1 end
    return n
end

--- A sentry item in the player's own inventory, on this machine's copy of it.
local function carried(player, itemId)
    local inv = U.try("sentry.inv", function() return player:getInventory() end)
    if not inv then return nil, nil end
    local item = U.try("sentry.byId", function() return inv:getItemWithIDRecursiv(tonumber(itemId)) end)
    if not SN.isSentry(item) then return nil, inv end
    return item, inv
end

local function countCarried(inv)
    local list = U.try("sentry.count", function() return inv:getAllTypeRecurse("TrekSentry") end)
    local n = 0
    if list then
        for i = 0, list:size() - 1 do
            if SN.isSentry(list:get(i)) then n = n + 1 end
        end
    end
    return n
end

---------------------------------------------------------------------------
-- Setting one down
---------------------------------------------------------------------------
Net.onServer("deploySentry", function(player, args)
    if not alive(player) then return end
    local item, inv = carried(player, args.id)
    if not item then
        deny(player, "sentryNone")
        return
    end
    if SS.count() >= C.SentryMax then
        deny(player, "sentryTooMany")
        return
    end
    -- Where: in front of them on this machine's copy of them, never where a
    -- client says.
    local x, y, z = SN.spotInFront(player)
    local sq = x and U.chunkLoaded(x, y, z) and U.square(x, y, z, false) or nil
    local why = SN.squareRefusal(sq)
    if why then
        deny(player, why)
        return
    end

    -- Out of their hands first, and counted (DEV_GUIDE, *Never trust one way
    -- of doing it*): a Remove that did nothing would lay a copy and leave
    -- them the original.
    local before = countCarried(inv)
    local container = U.try("sentry.container", function() return item:getContainer() end) or inv
    U.try("sentry.remove", function() container:Remove(item) end)
    if countCarried(inv) >= before then
        U.log("WARN sentry: %s's sentry would not come out of their inventory", nameOf(player))
        deny(player, "sentryNone")
        return
    end
    if isServer() then
        U.try("sentry.syncInv", function() sendRemoveItemFromContainer(container, item) end)
    end

    local s = SS.state()
    local id = tostring(s.next)
    s.next = s.next + 1
    U.try("sentry.tag", function() item:getModData()[SN.ID_KEY] = id end)
    -- The live item, not a new one from its id: its charge is on it.
    local placed = U.try("sentry.place", function()
        return sq:AddWorldInventoryItem(item, 0.5, 0.5, 0.0)
    end)
    if not placed then
        U.log("WARN sentry: could not set %s's sentry down at %d,%d,%d; handing it back", nameOf(player), x, y, z)
        U.try("sentry.back", function() inv:AddItem(item) end)
        if isServer() then U.try("sentry.backSync", function() sendAddItemToContainer(inv, item) end) end
        return
    end
    local now = nowMs()
    s.set[id] = { x = x, y = y, z = z, owner = nameOf(player), armedMs = now + C.SentryArmMs, lastMs = 0 }
    Net.toClient(player, "sentryDeployed", { charges = SN.charges(item), secs = math.floor(C.SentryArmMs / 1000) })
    U.log("sentry: %s set one down at %d,%d,%d (id %s, %d charges)", nameOf(player), x, y, z, id, SN.charges(item))
end)

---------------------------------------------------------------------------
-- Recharging
---------------------------------------------------------------------------
Net.onServer("rechargeSentry", function(player, args)
    if not alive(player) then return end
    local item = carried(player, args.id)
    if not item then
        deny(player, "sentryNone")
        return
    end
    if not (TREK.Power and TREK.Power.inReachOf(player)) then
        deny(player, "sentryNoCore")
        return
    end
    if SN.charges(item) >= C.SentryCharges then return end
    if not TREK.Energy.energize(player, "sentry", C.SentryRechargeCost) then return end
    U.try("sentry.fill", function() item:getModData()[C.SentryChargesKey] = C.SentryCharges end)
    if isServer() then
        U.try("sentry.syncFill", function() syncItemModData(player, item) end)
    end
    Net.toClient(player, "sentryRecharged", { id = args.id, charges = C.SentryCharges })
end)

---------------------------------------------------------------------------
-- Firing
---------------------------------------------------------------------------
--- The world item of the sentry with this id on its square, or nil.
local function findOnSquare(sq, id)
    return U.try("sentry.find", function()
        local list = sq:getWorldObjects()
        for i = 0, list:size() - 1 do
            local w = list:get(i)
            local it = w and w:getItem()
            if SN.isSentry(it) and tostring(it:getModData()[SN.ID_KEY]) == id then return w end
        end
        return nil
    end)
end

--- The nearest of the dead a sentry at (x, y, z) can shoot: alive, on its
--- level, within range, and not one of the Adirondack's crew (pacified
--- bodies the mod walks about; they cannot be hurt, and a sentry that kept
--- firing at one would never stop).
function SS.target(x, y, z)
    local best, bd = nil, nil
    local r2 = C.SentryRange * C.SentryRange
    U.try("sentry.target", function()
        local list = getCell():getZombieList()
        for i = 0, list:size() - 1 do
            local zed = list:get(i)
            if zed and not zed:isDead() and math.floor(zed:getZ()) == z and not zed:isUseless() then
                local d = U.dist2(zed:getX(), zed:getY(), x, y)
                if d <= r2 and (not bd or d < bd) then best, bd = zed, d end
            end
        end
    end)
    return best
end

local weapon = nil
--- What the shot hits with: a phaser, made once on this machine (the hit
--- pipeline reads the weapon for its type and its sounds; the damage is
--- ours).
local function shotWeapon()
    if not weapon then weapon = U.try("sentry.weapon", function() return instanceItem(C.PhaserItem) end) end
    return weapon
end

local function attackerFor(owner)
    for _, p in ipairs(U.players()) do
        if nameOf(p) == owner and alive(p) then return p end
    end
    return U.try("sentry.fake", function() return getCell():getFakeZombieForHit() end)
end

--- One sentry's turn: fires if it is armed, charged, due and has a target.
--- Returns true when it fired.
function SS.fire(id, s, now)
    if now < (s.armedMs or 0) or now - (s.lastMs or 0) < C.SentryShotMs then return false end
    if not U.chunkLoaded(s.x, s.y, s.z) then return false end
    local sq = U.square(s.x, s.y, s.z, false)
    local w = sq and findOnSquare(sq, id)
    if not w then
        -- Picked up, or gone some other way: it is not set down any more.
        SS.state().set[id] = nil
        U.log("sentry: %s is no longer at %d,%d,%d", id, s.x, s.y, s.z)
        return false
    end
    local item = w:getItem()
    local left = SN.charges(item)
    if left <= 0 then return false end
    local cx, cy = s.x + 0.5, s.y + 0.5
    local zed = SS.target(cx, cy, s.z)
    if not zed then return false end
    local tx, ty = zed:getX(), zed:getY()
    local hit = U.try("sentry.hit", function()
        zed:Hit(shotWeapon(), attackerFor(s.owner), C.SentryDamage, false, 1.0)
        return true
    end)
    if not hit then return false end
    s.lastMs = now
    left = left - 1
    U.try("sentry.spend", function() item:getModData()[C.SentryChargesKey] = left end)
    Net.toAll("sentryShot", { x = cx, y = cy, z = s.z, tx = tx, ty = ty, tz = s.z })
    if left == 0 then
        for _, p in ipairs(U.players()) do
            if nameOf(p) == s.owner then Net.toClient(p, "sentryEmpty", {}) end
        end
        U.log("sentry: %s is spent", id)
    end
    return true
end

function SS.service()
    local now = nowMs()
    local ids = {}
    for id in pairs(SS.state().set) do table.insert(ids, id) end
    for _, id in ipairs(ids) do
        local s = SS.state().set[id]
        if s then U.try("sentry.fire", SS.fire, id, s, now) end
    end
end

local tick = 0
Events.OnTick.Add(function()
    tick = tick + 1
    if tick < 5 then return end
    tick = 0
    U.try("sentry.service", SS.service)
end)

return SS
