--[[ Shuttlecraft -- species, divisions and rank: the authority's half.

    Everything a trait does over time, or once, is decided here and nowhere
    else (TREK_Traits.lua says why). Three kinds of work:

      * **Once per character** (T.firstSight): a division's kit, a Trill's
        past hosts, a Starfleet officer's starting rank, and the look
        (TREK_Appearance). Recorded in the character's mod data on this
        machine, by revision, so a character made before a part existed gets
        that part on the next pass and nothing twice.
      * **Every game minute / ten minutes**: the android's charge, a
        Bajoran's faith, a Talaxian's company, spacesickness, an Orion's
        scent, the Borg hum, a Betazoid's sense of a rescue.
      * **When something happens**: a beam (transporter phobia) and a rescue
        (rank). The transporter and the rescue call in; they do not know
        what a trait is.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_Probes"
require "TREK/TREK_Power"
require "TREK/TREK_Traits"

local C = TREK.Config
local U = TREK.Util
local Ship = TREK.Ship
local Probes = TREK.Probes
local P = TREK.Power
local T = TREK.Traits

local S = {}
TREK.TraitsServer = S

local function md(player)
    return U.try("traits.md", function() return player:getModData() end)
end

local function alive(player)
    return player ~= nil and not U.try("traits.dead", function() return player:isDead() end)
end

local function aboard(player)
    return U.isInteriorPlayer(player)
end

local function hours()
    return U.worldHours()
end

---------------------------------------------------------------------------
-- Items into a character's pockets
---------------------------------------------------------------------------
local function give(player, id)
    local inv = U.try("traits.inv", function() return player:getInventory() end)
    if not inv then return false end
    local item = U.try("traits.item:" .. id, function() return instanceItem(id) end)
    if not item then
        U.log("WARN traits: %s did not make an item", id)
        return false
    end
    inv:AddItem(item)
    if isServer() then sendAddItemToContainer(inv, item) end
    return true
end

---------------------------------------------------------------------------
-- Rank (TRAITS.md 3.3)
---------------------------------------------------------------------------
--- Sets a character's rank to index `n` (0 is none), replacing whatever was
--- there. Traits are sent with sendSyncPlayerFields' 0x07, as vanilla does
--- after a book grants a recipe (PADD.md 2).
function S.setRank(player, n)
    local traits = U.try("traits.set", function() return player:getCharacterTraits() end)
    if not traits then return false end
    for i, path in ipairs(C.Ranks) do
        local id = T.id(path)
        if id then
            U.try("traits.rank", function()
                if i == n then traits:add(id) else traits:remove(id) end
            end)
        end
    end
    if isServer() then
        U.try("traits.sync", function() sendSyncPlayerFields(player, 0x07) end)
    end
    return true
end

--- The rank a character has earned: the greater of where they started and
--- what their rescues are worth.
function S.earnedRank(player)
    local data = md(player) or {}
    local n = tonumber(data.TREKStartRank) or 0
    local rescues = tonumber(data[C.RescuesKey]) or 0
    for i, need in ipairs(C.RankRescues) do
        if rescues >= need and i > n then n = i end
    end
    return n
end

--- A rescue credited to this character. Called by TREK_Missions.
function S.onRescue(player)
    if not alive(player) then return end
    local data = md(player)
    if not data then return end
    data[C.RescuesKey] = (tonumber(data[C.RescuesKey]) or 0) + 1
    local was = T.rank(player)
    local now = S.earnedRank(player)
    if now > was then
        S.setRank(player, now)
        T.note(player, "IGUI_TREK_Promoted", getText("UI_trait_trek_" .. C.Ranks[now]),
               255, 220, 120)
        U.log("traits: %s promoted to %s (%d rescue(s))", Ship.usernameOf(player),
              C.Ranks[now], data[C.RescuesKey])
    end
end

---------------------------------------------------------------------------
-- Once per character
---------------------------------------------------------------------------
--- Picks `n` distinct perks from C.TrillPerks. Split out so a test can say
--- what it rolled.
function S.rollHosts(n)
    local pool, out = {}, {}
    for _, name in ipairs(C.TrillPerks) do
        if Perks[name] then table.insert(pool, name) end
    end
    for _ = 1, math.min(n, #pool) do
        local i = ZombRand(#pool) + 1
        table.insert(out, table.remove(pool, i))
    end
    return out
end

--- One level in each of `perks`. addXp on a server is GameServer.addXp, in
--- single player the character's own AddXP, and on a client nothing at all
--- (bytecode: LuaManager$GlobalObject.addXp), so this is authority work.
-- The XP a perk's next level takes. PerkFactory$Perk has getXp1..getXp10 and
-- nothing that takes the level as an argument, so they are named one by one
-- rather than looked up by string on a Java object.
local XP_FOR = {
    function(p) return p:getXp1() end, function(p) return p:getXp2() end,
    function(p) return p:getXp3() end, function(p) return p:getXp4() end,
    function(p) return p:getXp5() end, function(p) return p:getXp6() end,
    function(p) return p:getXp7() end, function(p) return p:getXp8() end,
    function(p) return p:getXp9() end, function(p) return p:getXp10() end,
}

local function levelUp(player, name)
    local perk = Perks[name]
    if not perk then return false end
    local level = U.try("traits.level", function() return player:getPerkLevel(perk) end) or 0
    if level >= 10 then return false end
    local need = U.try("traits.need", function() return XP_FOR[level + 1](perk) end)
    need = tonumber(need) or 75
    return U.try("traits.addXp", function()
        addXpNoMultiplier(player, perk, need)
        return true
    end) == true
end

function S.firstSight(player)
    local data = md(player)
    if not data then return false end
    local rev = tonumber(data.TREKTraitsRev) or 0
    if rev >= C.TraitsInitRev then return false end
    local who = Ship.usernameOf(player)

    -- A division's kit, and its starting rank.
    for path, items in pairs(C.DivisionKit) do
        if T.has(player, path) then
            for _, id in ipairs(items) do give(player, id) end
        end
    end
    if T.isStarfleet(player) then
        data.TREKStartRank = T.has(player, "sf_command") and 2 or 1
        S.setRank(player, S.earnedRank(player))
    end

    -- A Trill's past hosts.
    if T.has(player, "trill") then
        local hosts = S.rollHosts(C.TrillHosts)
        for _, name in ipairs(hosts) do levelUp(player, name) end
        data.TREKTrillHosts = table.concat(hosts, ",")
        T.note(player, "IGUI_TREK_TrillHosts", data.TREKTrillHosts, 170, 220, 255)
        U.log("traits: %s's past hosts were %s", who, data.TREKTrillHosts)
    end

    -- An android starts full.
    if T.has(player, "android") then
        data[C.AndroidChargeKey] = 100
    end

    if TREK.Appearance then U.try("traits.look", TREK.Appearance.apply, player) end

    data.TREKTraitsRev = C.TraitsInitRev
    U.log("traits: first sight of %s -- %s", who, tostring(T.species(player) or "human"))
    return true
end

---------------------------------------------------------------------------
-- The android (TRAITS.md 3.1a)
---------------------------------------------------------------------------
--- Charge, 0-100.
function S.charge(player)
    local data = md(player)
    return math.max(0, math.min(100, tonumber(data and data[C.AndroidChargeKey]) or 100))
end

--- One game minute of an android's life: no hunger, no thirst, a charge
--- that runs down -- and fills, asleep aboard, out of the ship's reserve.
function S.serviceAndroid(player)
    local data = md(player)
    if not data then return end
    local was = S.charge(player)
    local now = was - C.AndroidDrainPerHour / 60
    local asleep = U.try("traits.asleep", function() return player:isAsleep() end) == true
    if asleep and aboard(player) and not P.dark() then
        local want = math.min(100 - now, C.AndroidChargePerHour / 60)
        if want > 0 then
            local paid = P.pay(want * C.AndroidChargeCost, true)
            now = now + paid / C.AndroidChargeCost
        end
    end
    now = math.max(0, math.min(100, now))
    data[C.AndroidChargeKey] = now

    local set = { HUNGER = 0, THIRST = 0 }
    if now <= 0 then
        set.FATIGUE = C.AndroidFlatFatigue
    elseif now < C.AndroidLowCharge then
        local fatigue = U.try("traits.fatigue", function()
            return player:getStats():get(CharacterStat.FATIGUE)
        end) or 0
        if fatigue < C.AndroidLowFatigue then set.FATIGUE = C.AndroidLowFatigue end
    end
    T.adjust(player, { set = set })

    for _, mark in ipairs(C.AndroidNotes) do
        if was > mark and now <= mark then
            T.note(player, mark == 0 and "IGUI_TREK_AndroidFlat" or "IGUI_TREK_AndroidLow",
                   tostring(mark), 255, 200, 120)
        end
    end
    if was < 100 and now >= 100 then
        T.note(player, "IGUI_TREK_AndroidFull", nil, 140, 220, 255)
    end
end

---------------------------------------------------------------------------
-- Every ten minutes
---------------------------------------------------------------------------
local function inFlightAboard(player)
    if Ship.get().flying ~= true then return false end
    if aboard(player) then return true end
    local v = U.try("traits.vehicle", function() return player:getVehicle() end)
    return v ~= nil and TREK.Vehicle ~= nil and TREK.Vehicle.isShuttle(v)
end

local function zombiesNear(player, radius)
    local list = U.try("traits.zlist", function() return getCell():getZombieList() end)
    if not list then return 0 end
    local px, py = player:getX(), player:getY()
    local r2, n = radius * radius, 0
    local size = U.try("traits.zsize", function() return list:size() end) or 0
    for i = 0, size - 1 do
        local z = list:get(i)
        if z and U.dist2(px, py, z:getX(), z:getY()) <= r2 then n = n + 1 end
    end
    return n
end

function S.everyTenMinutes()
    local players = U.players()
    local now = hours()
    for _, p in ipairs(players) do
        if alive(p) then
            local data = md(p) or {}
            -- A flag rather than next(): Kahlua has no `next`.
            local add, any = {}, false
            local function more(stat, v)
                add[stat] = (add[stat] or 0) + v
                any = true
            end

            if T.has(p, "bajoran") then
                more("STRESS", C.BajoranStress)
                more("UNHAPPINESS", C.BajoranUnhappy)
            end
            -- A Talaxian's company: anybody else within reach of one.
            for _, q in ipairs(players) do
                if q ~= p and alive(q) and T.has(q, "talaxian")
                   and math.floor(q:getZ()) == math.floor(p:getZ())
                   and U.dist2(p:getX(), p:getY(), q:getX(), q:getY())
                       <= C.TalaxianRange * C.TalaxianRange then
                    more("BOREDOM", C.TalaxianBoredom)
                    more("UNHAPPINESS", C.TalaxianUnhappy)
                    break
                end
            end
            if T.has(p, "spacesick") and inFlightAboard(p) then
                more("STRESS", C.SpacesickStress)
                more("UNHAPPINESS", C.SpacesickUnhappy)
            end
            if any then T.adjust(p, { add = add }) end

            if T.has(p, "orion") and not aboard(p) then
                U.try("traits.scent", function()
                    addSound(p, math.floor(p:getX()), math.floor(p:getY()),
                             math.floor(p:getZ()), C.OrionScentRadius, C.OrionScentVolume)
                end)
            end

            if T.has(p, "exborg") and not aboard(p)
               and now >= (tonumber(data.TREKHumAt) or -1e9) + C.BorgHumEveryHours
               and zombiesNear(p, C.BorgHumRadius) >= C.BorgHumCount then
                data.TREKHumAt = now
                T.note(p, "IGUI_TREK_BorgHum", nil, 120, 255, 140)
            end

            if T.has(p, "betazoid") then S.empath(p, data, now) end
        end
    end
end

--- A Betazoid senses the live rescue: a direction, no distance, and never
--- once the ensign is safe or lost.
function S.empath(player, data, now)
    if now < (tonumber(data.TREKEmpathAt) or -1e9) + C.EmpathEveryHours then return end
    local m = Probes.mission()
    if not m then return end
    local tx = m.ex or m.tx or m.x
    local ty = m.ey or m.ty or m.y
    if not tx or not ty then return end
    local px, py = player:getX(), player:getY()
    if aboard(player) then
        local ox, oy = Ship.worldOrigin(player)
        if not ox then return end
        px, py = ox, oy
    end
    if U.dist2(px, py, tx, ty) > C.EmpathRange * C.EmpathRange then return end
    data.TREKEmpathAt = now
    T.note(player, "IGUI_TREK_Empath", U.compass(px, py, tx, ty), 220, 170, 255)
end

---------------------------------------------------------------------------
-- When something happens
---------------------------------------------------------------------------
--- A beam granted to this character (TREK_Server's move handler).
function S.onBeam(player, kind)
    if not T.has(player, "transporterphobia") then return end
    T.adjust(player, { add = { STRESS = C.PhobiaStress, PANIC = C.PhobiaPanic,
                               UNHAPPINESS = C.PhobiaUnhappy } })
    T.note(player, "IGUI_TREK_Phobia", nil, 255, 170, 90)
end

---------------------------------------------------------------------------
-- Timers
---------------------------------------------------------------------------
function S.everyMinute()
    for _, p in ipairs(U.players()) do
        if alive(p) then
            U.try("traits.firstSight", S.firstSight, p)
            if T.has(p, "android") then U.try("traits.android", S.serviceAndroid, p) end
        end
    end
end

Events.EveryOneMinute.Add(function() U.try("traits.minute", S.everyMinute) end)
Events.EveryTenMinutes.Add(function() U.try("traits.ten", S.everyTenMinutes) end)

return S
