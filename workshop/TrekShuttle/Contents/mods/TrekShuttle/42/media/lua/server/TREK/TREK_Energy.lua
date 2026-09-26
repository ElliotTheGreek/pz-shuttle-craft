--[[ Shuttlecraft -- the ship's ledger (ENERGY.md section 3).

    Every charge in the ship goes through one function, S.energize, so no
    consumer can charge twice, forget to commit, or refuse in its own words.
    It pays with TREK.Power.pay, commits, and tells the player either way:

        "Energizing (25 power)"
        "Energizing... failed: not enough power (25 needed, 3 left)"

    **Dark is a state, not a number** (section 3.2). S.powerChanged compares the
    published `s.dark` with the ship's own arithmetic after every spend and
    every crystal load, and on a change publishes it once and tells every
    client: `powerDown` or `powerUp`. The flag is published rather than left
    for each client to derive, because a client whose copy has no reserve in it
    yet reads it as full, and because a cold ship starts dark by decision.

    Authority only: single player, or a server.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_Power"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Ship = TREK.Ship
local P = TREK.Power

local E = {}
TREK.Energy = E

-- What else has to happen when the ship goes dark: the Doctor goes out and a
-- running cure fails (TREK_Server). Called once, on the change, after the
-- flag is published.
E.downListeners = {}
function E.onPowerDown(fn) table.insert(E.downListeners, fn) end
E.upListeners = {}
function E.onPowerUp(fn) table.insert(E.upListeners, fn) end

--- Publishes a change between lit and dark, once. Returns "down", "up" or nil.
---
--- `s.dark == nil` is a ship that has never been told: a save from before
--- this guide, or a ship being created. That is set silently, because the
--- player did nothing and nothing changed for them.
function E.powerChanged()
    -- The shuttle's lamps, notes and listeners. Her store keeps its own flag
    -- (TREK_Power, settle), and none of this is about her.
    if P.pool() == "adk" then return nil end
    local s = U.state()
    local dark = P.computeDark()
    if s.dark == dark then return nil end

    local first = s.dark == nil
    s.dark = dark
    Ship.commit()
    if first then
        U.log("power: the ship is %s", dark and "dark" or "lit")
        return nil
    end

    if dark then
        U.log("power: main power lost -- the ship is dark")
        Net.toAll("powerDown", {})
        for _, fn in ipairs(E.downListeners) do U.try("powerDownListener", fn) end
        return "down"
    end
    U.log("power: main power online -- %d units, %d spare(s)",
          math.floor(P.reserve()), P.crystals())
    -- **The first power-up of a cold ship is the commissioning** (ENERGY.md
    -- 10.4). Explicit and published, never inferred from the reserve, and it
    -- is what the story's clock waits on.
    local args = {}
    if s.commissioned == false then
        s.commissioned = true
        args.first = true
        Ship.commit()
        U.log("power: the shuttle is commissioned")
    end
    Net.toAll("powerUp", args)
    for _, fn in ipairs(E.upListeners) do U.try("powerUpListener", fn) end
    return "up"
end

--- Warns the crew on the way down, once each (section 3.4): the last spare
--- engaging, then C.PowerAmber and C.PowerRed of it.
---
--- **Only with no spare behind it.** With crystals aboard a low reserve is
--- simply the next swap, and a warning about it would teach the crew to
--- ignore the warnings. A dark ship is told by powerDown instead. The level
--- reached is ship state, so a warning is not repeated by a second machine or
--- after a restart, and it resets once there is power to spare again.
function E.thresholds(sparesBefore)
    if P.pool() == "adk" then return nil end
    local s = U.state()
    if P.crystals() > 0 then
        s.powerWarn = nil
        return nil
    end
    if P.computeDark() then return nil end
    local said = nil
    if sparesBefore and sparesBefore > 0 then
        Net.toAll("powerLow", { last = true })
        said = "last"
    end
    local frac = P.reserve() / C.PowerMax
    local level = 0
    if frac <= C.PowerRed then level = 2 elseif frac <= C.PowerAmber then level = 1 end
    if level == 0 then
        s.powerWarn = nil
    elseif (s.powerWarn or 0) < level then
        s.powerWarn = level
        local pct = math.floor((level == 2 and C.PowerRed or C.PowerAmber) * 100 + 0.5)
        Net.toAll("powerLow", { pct = pct })
        U.log("power: %d%% of the last crystal left", pct)
        said = pct
    end
    return said
end

--- Pays `cost` for `what`, or refuses. Authority only.
---
--- Returns true when paid (for `partial`, when anything was paid), and what
--- was paid. Commits, and tells `player` either way unless `opts.silent`.
---
---   opts.why      the denial reason to send instead of "noPower", for the
---                 refusals that already had their own words (repNoCrystal,
---                 emhNoPower, probeNoPower). Their numbers ride along.
---   opts.kind     a waiting move's kind, so the client drops it, the way
---                 `recharging` does.
---   opts.silent   no note either way. For the continuous drains -- driving,
---                 hovering, shields, repair -- which would note every second
---                 and report through the gauge instead.
---   opts.partial  pay what there is and go dark, rather than refuse.
---   opts.noCommit the caller commits: a drain riding a commit its pass
---                 already makes (section 3.6).
function E.energize(player, what, cost, opts)
    opts = opts or {}
    if type(cost) ~= "number" or cost ~= cost or cost <= 0 then return true end

    if not opts.partial and not P.canPay(cost) then
        if player and not opts.silent then
            local args = { what = what, need = math.ceil(cost),
                           have = math.floor(P.reserve()), kind = opts.kind }
            args.why = opts.why or "noPower"
            Net.toClient(player, "denied", args)
        end
        U.log("power: %s refused -- %d needed, %d left, %d spare(s)",
              tostring(what), math.ceil(cost), math.floor(P.reserve()),
              P.crystals())
        return false
    end

    local sparesBefore = P.crystals()
    local paid = P.pay(cost, opts.partial)
    E.thresholds(sparesBefore)
    if not opts.noCommit then Ship.commit() end
    if player and not opts.silent and paid > 0 then
        Net.toClient(player, "energized", {
            what = what, cost = math.ceil(paid), left = math.floor(P.reserve()),
        })
    end
    E.powerChanged()
    return paid > 0, paid
end

-- A safety net rather than the mechanism: every spend and every load calls
-- powerChanged itself. This catches a change that came some other way, and
-- gives a save from before this guide its flag on the first minute.
Events.EveryOneMinute.Add(function()
    U.try("powerChanged", E.powerChanged)
    U.try("hover", E.serviceHover)
end)

--- Holding five tonnes up is not free, moving or not (ENERGY.md 4.3, and the
--- author's decision 13.3). Once a game minute while she is flying, silent
--- and partial: the gauge is the report, and a ship that runs out in the air
--- is section 7's case.
function E.serviceHover()
    if U.state().flying ~= true then return false end
    E.energize(nil, "hover", C.HoverCostPerMinute, { partial = true, silent = true })
    return true
end

return E
