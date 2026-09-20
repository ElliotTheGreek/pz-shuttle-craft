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

--- Tops up every powered fitting in the cabin. Runs in every process, once a
--- game minute, and only while the cabin exists and its chunks are loaded --
--- a device in an unloaded chunk is not draining either.
---
--- Returns the number powered and the number that answered no device data,
--- because a television that is quietly scenery is exactly the failure this
--- mod keeps making and the count is the only thing that can see it.
function P.serviceDevices()
    local s = U.state()
    if s.built ~= true then return 0, 0 end

    local live, inert = 0, 0
    for _, spot in ipairs(findDeviceSpots()) do
        local x, y = U.at(spot[1], spot[2])
        if U.chunkLoaded(x, y, C.CabinZ) then
            local obj = U.findSprite(U.square(x, y, C.CabinZ, false), spot[3])
            if obj then
                if P.energise(obj) then live = live + 1 else inert = inert + 1 end
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

--- The chamber's own square, out of the authored layout.
local chamber = nil

function P.chamberSpot()
    if chamber then return chamber[1], chamber[2] end
    for _, entry in ipairs(L.tiles) do
        if entry.tag == C.DilithiumTag then
            chamber = { entry.x, entry.y }
            return chamber[1], chamber[2]
        end
    end
    U.warnOnce("power:chamber",
               "no layout entry is tagged " .. tostring(C.DilithiumTag) ..
               "; the ship has nowhere to keep its crystals")
    return nil
end

--- The chamber object, or nil. Authority only in practice -- a client's copy
--- of the cabin has the same object, but only the server ever takes from it.
function P.chamber()
    local ox, oy = P.chamberSpot()
    if not ox then return nil end
    local x, y = U.at(ox, oy)
    if not U.chunkLoaded(x, y, C.CabinZ) then return nil end
    local sq = U.square(x, y, C.CabinZ, false)
    if not sq then return nil end

    local found = nil
    U.eachObject(sq, function(o)
        local md = U.try("power.md", function() return o:getModData() end)
        if md and md.TREK == C.DilithiumTag then
            found = o
            return false
        end
    end)
    return found
end

--- How many spare crystals are in the chamber.
function P.crystals()
    local obj = P.chamber()
    local container = obj and U.containerOf(obj)
    if not container then return 0 end
    local list = U.try("power.crystals", function()
        return container:getAllTypeRecurse(C.DilithiumType)
    end)
    if not list then return 0 end
    -- The recursive lookup compares the **bare** type, so the results are
    -- filtered on the full id: the bare name is not namespaced and another
    -- mod could plausibly use it. Med.carried has the same pair.
    local n = 0
    local join = U.batch("power.countCrystals")
    local size = join(function() return list:size() end) or 0
    for i = 0, size - 1 do
        local item = join(function() return list:get(i) end)
        local t = item and U.try("power.type", function() return item:getFullType() end)
        if t == C.DilithiumItem then n = n + 1 end
    end
    return n
end

--- Takes one crystal out of the chamber and puts its charge in the reserve.
--- Authority only. Returns true when one was burned.
---
--- The item is *removed* and the reserve is **set** rather than added to: the
--- reserve is one crystal, so a fresh one replaces what was left rather than
--- stacking on top of it. Anything still in the old one is lost, which is why
--- the swap only happens when the reserve cannot cover what is being asked
--- for.
function P.burnCrystal()
    if isClient() then return false end
    local obj = P.chamber()
    local container = obj and U.containerOf(obj)
    if not container then return false end

    local list = U.try("power.crystals", function()
        return container:getAllTypeRecurse(C.DilithiumType)
    end)
    if not list then return false end

    local crystal = nil
    local join = U.batch("power.takeCrystal")
    local size = join(function() return list:size() end) or 0
    for i = 0, size - 1 do
        local item = join(function() return list:get(i) end)
        local t = item and U.try("power.type", function() return item:getFullType() end)
        if t == C.DilithiumItem then crystal = item break end
    end
    if not crystal then return false end

    -- Read it back: a Remove that did nothing would burn the same crystal
    -- for ever, which is an infinite power supply and the exact opposite of
    -- the point.
    local before = U.itemCount(obj)
    U.try("power.consume", function() container:Remove(crystal) end)
    if U.itemCount(obj) >= before then
        U.warnOnce("power.stuckCrystal",
                   "a dilithium crystal would not come out of the chamber")
        return false
    end
    if isServer() then
        U.try("power.syncChamber", function()
            container:setDirty(true)
            container:setDrawDirty(true)
            obj:transmitModData()
        end)
    end

    U.state().power = C.PowerMax
    U.log("power: a dilithium crystal is in the chamber -- reserve %d units, "
          .. "%d spare(s) left", C.PowerMax, P.crystals())
    return true
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
    local left = P.reserve() - (n or 0)
    if left < 0 then left = 0 end
    s.power = left
    return true
end

return P
