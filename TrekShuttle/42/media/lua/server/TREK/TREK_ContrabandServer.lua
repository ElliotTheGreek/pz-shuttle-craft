--[[ Shuttlecraft -- contraband: the authority's half (CONTRABAND.md).

    Everything that changes a body or a record happens here, and only here:

      * **a dose**, when vanilla's eating action completes on the server
        (TREK_Traits wraps ISEatFoodAction:complete, which runs Eat() where
        the authority is) -- ketracel-white, felicium, Trellium-D and
        cordrazine are Food items with a custom menu word, so taking one is
        eating it and the engine's own action carries it to the server;
      * **a round of the Game**, when TREKPlayGame completes (shared, a
        global, rebuilt here by name -- TREK_ContrabandActions.lua);
      * **every ten game minutes**, the record is walked: a habit not yet
        formed is forgotten, a crash lands, a second wind tops up, and a
        habit left too long is withdrawal;
      * **two commands**: handing the Game to somebody near you, and the
        PADD's flashing light.

    Every stat change goes through T.adjust and every word through T.note --
    the traits' route, which applies on the authority and mirrors the change
    to the owning client (TREK_Traits.lua says why both copies are written).
    After every change of state the owning client is sent a summary
    (`contraState`), because a client's copy of the player never sees this
    file's writes.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_Traits"
require "TREK/TREK_Padd"
require "TREK/TREK_Contraband"

local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Ship = TREK.Ship
local T = TREK.Traits
local K = TREK.Contraband

local S = {}
TREK.ContrabandServer = S

local function alive(player)
    return player ~= nil and U.try("contra.dead", function() return player:isDead() end) == false
end

local function now()
    return U.worldHours()
end

local function deny(player, why)
    Net.toClient(player, "denied", { why = why })
end

local function whoIs(player)
    return Ship.usernameOf(player)
end

---------------------------------------------------------------------------
-- Changing a body
---------------------------------------------------------------------------
--- `adj` with every add multiplied by `k` (a part-dose). Sets are not scaled:
--- half a vial of white still leaves you unafraid.
local function scaled(adj, k)
    local out = { set = adj.set, add = {} }
    for stat, v in pairs(adj.add or {}) do out.add[stat] = v * k end
    return out
end

local function statOf(player, name)
    local stat = CharacterStat[name]
    if not stat then return nil end
    return U.try("contra.stat:" .. name, function() return player:getStats():get(stat) end)
end

--- T.adjust, with two ceilings. `limit`: an add never pushes the stat past
--- this (withdrawal's food sickness stops at a queasy 35). `cap`: the stat is
--- held under this (the white's endurance, winded all the time).
local function apply(player, adj, limit, cap)
    local add, set = {}, {}
    for stat, v in pairs(adj.add or {}) do
        local ceiling = limit and limit[stat]
        if ceiling and v > 0 then
            local cur = statOf(player, stat) or 0
            v = math.max(0, math.min(v, ceiling - cur))
        end
        add[stat] = v
    end
    for stat, v in pairs(adj.set or {}) do set[stat] = v end
    for stat, ceiling in pairs(cap or {}) do
        local cur = statOf(player, stat)
        if cur and cur > ceiling then set[stat] = ceiling end
    end
    T.adjust(player, { add = add, set = set })
end

---------------------------------------------------------------------------
-- The record
---------------------------------------------------------------------------
local function row(player, name)
    local rec = K.record(player)
    if type(rec[name]) ~= "table" then rec[name] = { doses = 0 } end
    return rec[name]
end

--- Tells the owning client what its record now says.
function S.publish(player)
    Net.toClient(player, "contraState", { who = whoIs(player), state = K.summary(player, now()) })
end

local function hook(player, name, r)
    if r.hooked or (tonumber(r.doses) or 0) < C.Contraband[name].hookAt then return end
    r.hooked = true
    T.note(player, "IGUI_TREK_ContraHooked", getText(K.nameKey(name)), 255, 150, 90)
    U.log("contraband: %s is hooked on %s", whoIs(player), name)
end

--- One dose of a substance, `fraction` of a whole one.
function S.dose(player, name, fraction)
    local def = C.Contraband[name]
    if not def or not alive(player) then return false end
    fraction = math.max(0, math.min(1, tonumber(fraction) or 1))
    if fraction <= 0 then return false end

    -- Trellium-D is a Vulcan's ruin and everybody else's poison: no high, no
    -- habit, no record.
    if def.vulcanOnly and not T.has(player, "vulcan") then
        apply(player, scaled(def.poison, fraction), def.limit)
        T.note(player, "IGUI_TREK_Contra_poison", nil, 255, 120, 90)
        U.log("contraband: %s took %s and is not a Vulcan", whoIs(player), name)
        return true
    end

    local t = now()
    local r = row(player, name)
    local wasWithdrawing = K.withdrawing(name, r, t)
    apply(player, scaled(def.dose, fraction))
    r.doses = (tonumber(r.doses) or 0) + 1
    r.last = t
    if def.boostHours then r.boostUntil = t + def.boostHours end
    if def.crashHours then r.crashAt = t + def.crashHours end
    r.withdrew = nil

    if not r.first then
        r.first = t
        T.note(player, K.TEXT[name].first, nil, 220, 220, 255)
    elseif wasWithdrawing then
        T.note(player, "IGUI_TREK_ContraRelief", getText(K.nameKey(name)), 200, 220, 255)
    end
    hook(player, name, r)
    S.publish(player)
    U.log("contraband: %s took %s (%d dose(s)%s)", whoIs(player), name, r.doses,
          r.hooked and ", hooked" or "")
    return true
end

--- Cordrazine: a second wind, or -- a second time inside four hours -- McCoy
--- through the Guardian. Kept beside the record, never on the Doctor's list.
function S.cordrazine(player, fraction)
    if not alive(player) then return false end
    fraction = math.max(0, math.min(1, tonumber(fraction) or 1))
    local def = C.Cordrazine
    local rec = K.record(player)
    local t = now()
    local last = type(rec.cordrazine) == "table" and tonumber(rec.cordrazine.last) or nil
    rec.cordrazine = { last = t }
    if last and t - last < def.overdoseHours then
        apply(player, scaled(def.overdose, fraction))
        T.note(player, "IGUI_TREK_CordrazineOverdose", nil, 255, 90, 90)
        U.log("contraband: %s overdosed on cordrazine", whoIs(player))
        return "overdose"
    end
    apply(player, scaled(def.dose, fraction))
    T.note(player, "IGUI_TREK_CordrazineDose", nil, 200, 230, 255)
    return "dose"
end

--- Vanilla's eating action has completed on this item. Called from
--- TREK_Traits' wrap, on the authority only.
function S.onAte(character, item, fraction)
    if not character or not item then return end
    local fullType = U.try("contra.type", function() return item:getFullType() end)
    if K.isCordrazine(fullType) then
        S.cordrazine(character, fraction)
        return
    end
    local name = K.substanceOf(fullType)
    if name then S.dose(character, name, fraction) end
end

--- One round of the Game. Returns the fraction of a first round's lift it
--- gave: each round is worth a little less than the last.
function S.play(player)
    if not alive(player) then return nil end
    local def = C.Contraband.game
    local t = now()
    local r = row(player, "game")
    local wasWithdrawing = K.withdrawing("game", r, t)
    local worth = math.max(C.GameToleranceFloor,
                           1 - C.GameTolerance * (tonumber(r.doses) or 0))
    apply(player, scaled(def.dose, worth))
    r.doses = (tonumber(r.doses) or 0) + 1
    r.last = t
    r.withdrew = nil
    if not r.first then
        r.first = t
        T.note(player, K.TEXT.game.first, nil, 255, 200, 120)
    elseif wasWithdrawing then
        T.note(player, "IGUI_TREK_ContraRelief", getText(K.nameKey("game")), 255, 200, 120)
    else
        T.note(player, "IGUI_TREK_GameRound", nil, 255, 200, 120)
    end
    hook(player, "game", r)
    S.publish(player)
    U.log("contraband: %s played the Game (round %d, worth %.2f%s)", whoIs(player),
          r.doses, worth, r.hooked and ", hooked" or "")
    return worth
end

--- Every habit gone: the Doctor's detox. Returns how many were cleared.
function S.detox(player)
    local rec = K.record(player)
    local n = 0
    for _, name in ipairs(C.ContrabandOrder) do
        if type(rec[name]) == "table" then
            if rec[name].hooked then n = n + 1 end
            rec[name] = nil
        end
    end
    T.adjust(player, { set = { PANIC = 0 }, add = { STRESS = -0.3 } })
    S.publish(player)
    U.log("contraband: %s detoxed -- %d habit(s) cleared", whoIs(player), n)
    return n
end

--- The flashing light: the Game's hold on one player, gone.
function S.strobe(player)
    local rec = K.record(player)
    rec.game = nil
    S.publish(player)
    U.log("contraband: %s ran the flashing light", whoIs(player))
end

---------------------------------------------------------------------------
-- Every ten minutes
---------------------------------------------------------------------------
--- Walks one player's record at world hour `t`. Split out so a test can
--- drive it with a clock of its own.
function S.service(player, t)
    if not alive(player) then return end
    local rec = K.record(player)
    local changed = false
    for _, name in ipairs(C.ContrabandOrder) do
        local def, r = C.Contraband[name], rec[name]
        if type(r) == "table" and type(r.last) == "number" then
            local since = t - r.last
            if r.crashAt and t >= r.crashAt then
                r.crashAt = nil
                apply(player, def.crash)
                T.note(player, K.TEXT[name].crash, nil, 255, 120, 90)
            end
            if r.boostUntil then
                if t < r.boostUntil then
                    apply(player, def.boost)
                else
                    r.boostUntil = nil
                end
            end
            if not r.hooked then
                if since >= def.forgetHours then
                    rec[name] = nil
                    changed = true
                end
            elseif since >= def.cleanAfter then
                rec[name] = nil
                changed = true
                T.note(player, "IGUI_TREK_ContraClean", getText(K.nameKey(name)), 150, 230, 150)
                U.log("contraband: %s is clean of %s", whoIs(player), name)
            elseif since >= def.withdrawAfter then
                apply(player, def.withdrawal, def.limit, def.cap)
                if not r.withdrew then
                    r.withdrew = true
                    changed = true
                    U.log("contraband: %s is in withdrawal from %s", whoIs(player), name)
                end
                if t >= (tonumber(r.nagAt) or -1e9) + C.ContrabandNagHours then
                    r.nagAt = t
                    T.note(player, K.TEXT[name].crave, nil, 255, 170, 90)
                end
            end
        end
    end
    if changed then S.publish(player) end
end

function S.everyTenMinutes()
    local t = now()
    for _, p in ipairs(U.players()) do
        U.try("contra.service", S.service, p, t)
    end
end

Events.EveryTenMinutes.Add(function() U.try("contra.ten", S.everyTenMinutes) end)

---------------------------------------------------------------------------
-- Commands
---------------------------------------------------------------------------
local function playerNamed(name)
    if type(name) ~= "string" or name == "" or #name > 64 then return nil end
    for _, p in ipairs(U.players()) do
        if Ship.usernameOf(p) == name then return p end
    end
    return nil
end

local function gameIn(player)
    local inv = U.try("contra.inv", function() return player:getInventory() end)
    if not inv then return nil, nil end
    local list = U.try("contra.games", function()
        return inv:getAllTypeRecurse("TrekKtarianGame")
    end)
    if not list then return nil, inv end
    for i = 0, (U.try("contra.gamesSize", function() return list:size() end) or 0) - 1 do
        local it = list:get(i)
        if it and U.try("contra.gameType", function() return it:getFullType() end)
                  == C.Contraband.game.item then
            return it, inv
        end
    end
    return nil, inv
end

--- Hands your Ktarian game to somebody standing near you. The spread is the
--- episode: everybody who tries one offers it to the next person.
Net.onServer("gameOffer", function(player, args)
    if not alive(player) then return end
    local target = playerNamed(args and args.to)
    if not target or target == player or not alive(target) then
        deny(player, "gameNobody")
        return
    end
    local near = math.floor(target:getZ()) == math.floor(player:getZ())
        and U.dist2(player:getX(), player:getY(), target:getX(), target:getY())
            <= C.GameOfferRange * C.GameOfferRange
    if not near then
        deny(player, "gameFar")
        return
    end
    local game = gameIn(player)
    if not game then
        deny(player, "gameNone")
        return
    end
    local from = U.try("contra.from", function() return game:getContainer() end)
    local into = U.try("contra.into", function() return target:getInventory() end)
    if not from or not into then return end
    U.try("contra.take", function() from:Remove(game) end)
    if isServer() then
        U.try("contra.sendGone", function() sendRemoveItemFromContainer(from, game) end)
    end
    U.try("contra.give", function() into:AddItem(game) end)
    if isServer() then
        U.try("contra.sendAdd", function() sendAddItemToContainer(into, game) end)
    end
    T.note(target, "IGUI_TREK_GameGiven", whoIs(player), 255, 200, 120)
    T.note(player, "IGUI_TREK_GameGave", whoIs(target), 255, 200, 120)
    U.log("contraband: %s handed the Game to %s", whoIs(player), whoIs(target))
end)

--- The flashing light, off a PADD's screen (TNG "The Game": Wesley and Data
--- broke it with a strobe). Needs a PADD on you, and somebody the Game has
--- hold of.
Net.onServer("gameStrobe", function(player)
    if not alive(player) then return end
    if #TREK.Padd.carried(player) == 0 then
        deny(player, "strobeNoPadd")
        return
    end
    if not K.playsTheGame(player) then
        deny(player, "strobeClean")
        return
    end
    S.strobe(player)
    T.note(player, "IGUI_TREK_Strobed", nil, 150, 230, 255)
end)

return S
