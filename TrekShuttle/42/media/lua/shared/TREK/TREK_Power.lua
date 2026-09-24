--[[ Shuttlecraft -- the ship's power.

    A shuttle makes its own electricity. It is not on Muldraugh's grid, it has
    no generator to fuel, and nothing aboard it should stop working the week
    the town's power does -- which is the same decision the water already
    makes (C.WaterCapacity and B.refillWater).

    This file exists because the obvious way to do it does not work, and the
    reason is worth writing down.

    ---------------------------------------------------------------------
    What does not work: telling the square it has electricity
    ---------------------------------------------------------------------
    B.powerCabin used to call sq:setHaveElectricity(true) on every square of
    the cabin, every game minute. It was a no-op from the day it was written:

      * IsoGridSquare.setHaveElectricity(boolean) does not set a field. Its
        bytecode walks the square's objects and touches IsoLightSwitches. The
        cabin has none, so the call did nothing at all.
      * IsoGridSquare.haveElectricity() is not a flag either. It returns
        chunk.isGeneratorPoweringSquare(x, y, z) -- true only when a real
        IsoGenerator is running in that chunk.
      * IsoGridSquare.hasGridPower() is !isNoPower() && doesPowerGridExist():
        the town mains, which shut off a few weeks into any world.

    So the only two ways for an appliance to be mains-powered here are a
    generator standing in the cabin -- a large object to look at, a fuel
    supply to keep topped up, and the very thing the author asked to have
    taken out of a twenty-four square room -- or the town grid, which is
    temporary by design.

    ---------------------------------------------------------------------
    What does work: the device's own battery branch
    ---------------------------------------------------------------------
    DeviceData.canBePoweredHere() opens with `if (isBatteryPowered) return
    true` before it looks at the square at all, and both the turn-on path and
    the per-minute update use it:

        setIsTurnedOn(true):  canBePoweredHere() must be true, and if the
                              device is battery powered its power must be > 0
        update():             a device that is on drains useDelta per game
                              minute, and switches *itself* off at 0

    So a device with isBatteryPowered set and its power kept full can be
    turned on anywhere, needs no square, no room and no generator, and never
    goes off. That is the ship's power plant: there isn't one, and every
    fitting simply has its own cell that never runs down.

    Three details, each of which cost a look at the bytecode:

      * `hasBattery` stays **false**. It is cosmetic to the engine -- neither
        the drain nor the turn-on check reads it -- but RWMPower.lua offers
        *Remove Battery* when it is true, which would hand the player a free
        Base.Battery every time they opened the panel.
      * The top-up has to happen **in every process**, which is why this file
        is shared and not server-only. DeviceData.update drains the power in
        whichever process is running it, and on a client it transmits the drop
        itself; a server-only top-up would leave every client's copy switching
        the television off after a couple of game hours. This is a local value
        the engine recomputes per process, like the deckhead lights and the
        shields -- it is not ship state, and nothing here is published.
      * Nothing is transmitted. setPower is a local write on both sides of the
        wire, and the on/off state that *does* matter rides the engine's own
        device packets.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"
local L = require "TREK/TREK_InteriorLayout"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local P = {}
TREK.Power = P

--- Where the layout puts powered fittings, worked out once.
local deviceSpots = nil

local function findDeviceSpots()
    if deviceSpots then return deviceSpots end
    deviceSpots = {}
    for _, entry in ipairs(L.tiles) do
        if entry.device then
            table.insert(deviceSpots, { entry.x, entry.y, entry.sprite })
        end
    end
    return deviceSpots
end

--- Puts the ship's power into one device. Safe to call on anything: a plain
--- IsoObject has no getDeviceData at all, and that answers nil rather than
--- throwing because the probe is guarded.
---
--- Returns true when the device is powered afterwards.
function P.energise(obj)
    if not obj then return false end
    local data = U.try("getDeviceData", function() return obj:getDeviceData() end)
    if not data then return false end

    U.try("energise", function()
        data:setIsBatteryPowered(true)
        -- Deliberately not setHasBattery(true): see the header.
        data:setHasBattery(false)
        if (data:getPower() or 0) < C.DevicePower then
            data:setPower(C.DevicePower)
        end
    end)
    return true
end

--- Takes a device's power away: its cell to zero, and the engine then
--- switches it off by itself and will not switch it on again, through the
--- same battery branch that keeps it on (the header). Returns true when it
--- has device data at all.
function P.deenergise(obj)
    if not obj then return false end
    local data = U.try("getDeviceData", function() return obj:getDeviceData() end)
    if not data then return false end
    U.try("deenergise", function()
        if (data:getPower() or 0) > 0 then data:setPower(0) end
    end)
    return true
end

--- Tops up every powered fitting in the cabin. Runs in every process, once a
--- game minute, and only while the cabin exists and its chunks are loaded --
--- a device in an unloaded chunk is not draining either.
---
--- **A dark ship powers nothing** (ENERGY.md 8.2): the cells are emptied
--- instead, in every process for the same reason they are filled in every
--- process, and the television goes off and stays off until the power is
--- back. P.dark() is the published flag on a client and the numbers here.
---
--- Returns the number powered and the number that answered no device data,
--- because a television that is quietly scenery is exactly the failure this
--- mod keeps making and the count is the only thing that can see it.
function P.serviceDevices()
    local s = U.state()
    if s.built ~= true then return 0, 0 end

    local live, inert = 0, 0
    local dark = P.dark()
    for _, spot in ipairs(findDeviceSpots()) do
        local x, y = U.at(spot[1], spot[2])
        if U.chunkLoaded(x, y, C.CabinZ) then
            local obj = U.findSprite(U.square(x, y, C.CabinZ, false), spot[3])
            if obj then
                local fn = dark and P.deenergise or P.energise
                if fn(obj) then live = live + 1 else inert = inert + 1 end
            end
        end
    end
    return live, inert
end

--- Logs what each powered fitting is doing, for TREK_Power() from the
--- console. The mod has been bitten four times by a fitting that is present,
--- drawn and inert; this is the line that tells the two apart.
function P.report()
    local live, inert = P.serviceDevices()
    for _, spot in ipairs(findDeviceSpots()) do
        local x, y = U.at(spot[1], spot[2])
        local obj = U.findSprite(U.square(x, y, C.CabinZ, false), spot[3])
        if not obj then
            U.log("power: nothing with sprite %s at %d,%d", spot[3], spot[1], spot[2])
        else
            local data = U.try("getDeviceData", function() return obj:getDeviceData() end)
            if not data then
                U.log("power: %s at %d,%d is a plain IsoObject -- no device data",
                      spot[3], spot[1], spot[2])
            else
                U.log("power: %s at %d,%d battery=%s power=%s on=%s",
                      spot[3], spot[1], spot[2],
                      tostring(U.try("bat", function() return data:getIsBatteryPowered() end)),
                      tostring(U.try("pwr", function() return data:getPower() end)),
                      tostring(U.try("on", function() return data:getIsTurnedOn() end)))
            end
        end
    end
    U.log("power: %d device(s) powered, %d inert", live, inert)
    return live, inert
end

-- In every process, because the engine drains the power in every process.
Events.EveryOneMinute.Add(function()
    U.try("serviceDevices", P.serviceDevices)
end)

--- The galley's power bus (ENERGY.md 9) is a generator drawn with the sky
--- tile. The engine plays <GeneratorSound>Loop while one runs and
--- <GeneratorSound>Starting/Stopping on each toggle, reading the prefix off
--- the *sprite's* properties -- so setting it on this sprite gives the bus the
--- ship's own quiet hum instead of a petrol generator. A sprite property
--- survives RecalcProperties, which clears the square's, and it has to be set
--- in every process, because every client plays the loop. The sky floor wears
--- the same sprite, and only generator code ever reads this property.
--- PropertyContainer.set(String, String) is public, and vanilla's own server
--- farming code sets a sprite property the same way (MOFarming.lua:91).
function P.quietBus()
    return U.try("busSound", function()
        getSprite(C.SkyTile):getProperties():set("GeneratorSound", C.PowerBusSound)
        return true
    end) == true
end

Events.OnInitGlobalModData.Add(function()
    U.try("quietBus", P.quietBus)
end)

---------------------------------------------------------------------------
-- The ship's reserve, and the crystal it burns
---------------------------------------------------------------------------
-- Everything above this line is a *device's* own cell -- the television's --
-- and nothing to do with what follows. This is the ship's power: one number,
-- ship state, spent by the replicator and later by the EMH.
--
-- **Nothing refills it for free.** It was twenty units every ten game minutes
-- for one revision, which made the replicator a machine you waited at rather
-- than fuelled. The reserve is one dilithium crystal burning in the
-- articulation chamber; when it is spent the ship swaps in a spare from that
-- same chamber, and when there are no spares the replicator stops.
--
-- A crystal cannot be replicated (C.ReplicatorBlocked), which is the point of
-- the whole arrangement: the machine that removes the need to loot has a
-- leash that can only be found out in the world.

--- What is left of the crystal in the chamber, 0..C.PowerMax.
---
--- A missing value reads as **full**, for the client's sake: a client's copy
--- of the ship is whatever the server last sent, and before the first one
--- arrives there is no number at all. Reading that as empty would grey the
--- replicator's button on a machine that has simply not been told yet.
function P.reserve()
    local e = U.state().power
    if type(e) ~= "number" then return C.PowerMax end
    if e < 0 then return 0 end
    if e > C.PowerMax then return C.PowerMax end
    return e
end

--- The core's square, and the model standing on it.
---
--- A constant rather than a layout tag: **there is no fitting on that
--- square.** The core is the mod's own world model, the way the replicator
--- is, and the layout deliberately has no entry for 1,3.
function P.chamberSpot()
    return C.DilithiumSpot.x, C.DilithiumSpot.y
end

--- The warp core's world item, or nil. Both sides have it -- it is a world
--- object like any other -- but only the server ever changes what it holds.
function P.core()
    local ox, oy = P.chamberSpot()
    local x, y = U.at(ox, oy)
    if not U.chunkLoaded(x, y, C.CabinZ) then return nil end
    local sq = U.square(x, y, C.CabinZ, false)
    if not sq then return nil end

    local found = nil
    U.try("power.core", function()
        local items = sq:getWorldObjects()
        if not items then return end
        for i = 0, items:size() - 1 do
            local worldItem = items:get(i)
            local item = worldItem and worldItem:getItem()
            if item and item:getFullType() == C.WarpCoreItem then
                found = item
                return
            end
        end
    end)
    return found
end

--- How many spare crystals the ship is holding.
---
--- **Ship state, not a container.** It was a container for one revision and
--- the container was the truth; the core cannot have one, because a container
--- comes from a tile sprite's properties. The number rides with the rest of
--- the ship state instead, which costs nothing -- it is one integer beside a
--- position and a few flags -- and means a client's panel knows the spare
--- count without opening anything.
---
--- Missing reads as **none**, which is the opposite of how the reserve reads
--- a missing value and deliberately so: a reserve that reads empty would grey
--- a button on a client that has not been told yet, while spares that read
--- full would offer a crystal the ship does not have.
function P.crystals()
    local n = U.state().crystals
    if type(n) ~= "number" or n < 0 then return 0 end
    return math.floor(n)
end

--- Puts crystals in. Authority only; the caller commits.
function P.addCrystals(n)
    if isClient() then return false end
    n = math.floor(n or 0)
    if n <= 0 then return false end
    local s = U.state()
    s.crystals = P.crystals() + n
    return true
end

--- Takes one out, without burning it: the player is having it back.
--- Authority only; the caller commits.
function P.takeCrystal()
    if isClient() then return false end
    local have = P.crystals()
    if have <= 0 then return false end
    U.state().crystals = have - 1
    return true
end

--- Burns one: it leaves the ship and the reserve is full again.
--- Authority only. Returns true when one was burned.
---
--- The reserve is **set** rather than added to, because the reserve is one
--- crystal: a fresh one replaces what was left rather than stacking on top of
--- it. Anything still in the old one is lost, which is why the swap only
--- happens when the reserve cannot cover what is being asked for.
function P.burnCrystal()
    if isClient() then return false end
    if not P.takeCrystal() then return false end
    U.state().power = C.PowerMax
    U.log("power: a dilithium crystal is in the core -- reserve %d units, "
          .. "%d spare(s) left", C.PowerMax, P.crystals())
    return true
end

--- Whether a player is standing close enough to work the core.
---
--- Measured the way the replicator's is, and for the same reason: the numbers
--- come from the *server's* copy of where the player is standing, never from
--- anything a client sent.
function P.inReachOf(player)
    if not player then return false end
    local x = U.try("core.px", function() return player:getX() end)
    local y = U.try("core.py", function() return player:getY() end)
    local z = U.try("core.pz", function() return player:getZ() end)
    if not x or not y then return false end
    if not U.isAboard(x, y, z) then return false end
    local cx, cy = U.at(P.chamberSpot())
    return U.dist2(x, y, cx + 0.5, cy + 0.5) <= C.CoreRange * C.CoreRange
end

--- True when the ship can pay `cost`, swapping in a crystal if it has to.
--- Authority only: it may consume one.
function P.afford(cost)
    cost = cost or 0
    if cost <= P.reserve() then return true end
    if isClient() then return false end
    -- Never burn a crystal for something a fresh one could not cover either.
    -- Nothing in the game costs that much today -- the dearest replication is
    -- fifteen hundred against a crystal's five thousand -- but the two
    -- numbers are both tunable, and the failure this prevents is eating a
    -- player's crystal and still refusing them.
    if cost > C.PowerMax then return false end
    if not P.burnCrystal() then return false end
    return cost <= P.reserve()
end

--- Spends from the reserve. The caller commits.
function P.spend(n)
    if isClient() then return false end
    local s = U.state()
    if type(n) ~= "number" or n ~= n or n <= 0 or n > C.PowerMax then
        return false
    end
    local left = P.reserve() - n
    if left < 0 then left = 0 end
    s.power = left
    return true
end

---------------------------------------------------------------------------
-- Everything aboard runs on it (ENERGY.md section 3)
---------------------------------------------------------------------------
-- Every charge in the ship goes through P.pay, and every one of those through
-- TREK.Energy.energize on the server, so nothing can charge twice, forget to
-- commit, or refuse in its own words.

--- The most one charge can take: what is left, plus one fresh crystal if
--- there is a spare to burn. A charge never burns two.
function P.available()
    local more = P.crystals() > 0 and C.PowerMax or 0
    return P.reserve() + more
end

--- True when the ship could pay `cost` now.
function P.canPay(cost)
    cost = cost or 0
    if cost <= 0 then return true end
    return cost <= P.available()
end

--- Pays `cost`, burning a spare if the reserve runs out part-way. Authority
--- only; the caller commits. Returns what was actually paid.
---
--- **The remainder carries over (ENERGY.md V1).** P.afford swaps a crystal
--- in *before* a cost it cannot cover, and a burn sets the reserve to full,
--- so whatever was left in the old crystal was thrown away: up to 149 units
--- on a 150-unit landing. Here the old crystal is run to zero first and only
--- the shortfall comes out of the new one, so nothing is ever lost.
---
--- `partial` pays what there is when the whole cost cannot be met, and the
--- ship goes dark. That is for the continuous drains (a shield that has half
--- a push left still pushes). Without it a charge the ship cannot cover pays
--- nothing at all.
function P.pay(cost, partial)
    if isClient() then return 0 end
    if type(cost) ~= "number" or cost ~= cost or cost <= 0 then return 0 end
    if not partial and not P.canPay(cost) then return 0 end

    local s = U.state()
    local have = P.reserve()
    if cost <= have then
        s.power = have - cost
        return cost
    end
    -- Run the old crystal dry, then burn a fresh one for the rest.
    s.power = 0
    local paid = have
    if P.burnCrystal() then
        local rest = math.min(cost - paid, P.reserve())
        s.power = P.reserve() - rest
        paid = paid + rest
    end
    return paid
end

--- True when the ship's own numbers say it has no power at all: less than one
--- unit left and no spare to burn.
function P.computeDark()
    return P.reserve() < 1 and P.crystals() == 0
end

--- True when the ship is dark.
---
--- **The authority asks the numbers and a client asks the flag.** A client's
--- copy with no `power` in it yet reads the reserve as full (P.reserve), so
--- its arithmetic would say "lit" about a ship that is dark; the published
--- `s.dark` is unambiguous. The authority's numbers are always current, even
--- in the moment between a spend and the S.powerChanged that publishes it.
---
--- ROADMAP2 says *never infer a campaign from a low reserve*: this is the
--- ship's power, and nothing about the story reads it.
function P.dark()
    if isClient() then
        local d = U.state().dark
        if d ~= nil then return d == true end
    end
    return P.computeDark()
end

return P
