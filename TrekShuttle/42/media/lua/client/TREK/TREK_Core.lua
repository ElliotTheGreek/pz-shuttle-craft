--[[ Shuttlecraft -- the client side of being aboard.

    A client owns exactly two things here: its own character, and the zombies
    it simulates. Everything else -- the cabin, the hull, the ship's state --
    belongs to the server (TREK_Server), and a client only asks for it.

    What lives here:
      * asking to move: every long move of the character (beam, hatch, the
        trip to a landing site) is asked for first, because on a server with
        the speed anti-cheat on each one is rationed. The client moves its own
        character once the server says yes -- only a client can, for an
        ordinary player;
      * the arrival hold: standing on the transporter pad while the server
        builds the cabin around you, and ejecting you if it never does;
      * the hatch in and out;
      * the shields: pushing back the zombies *this* client simulates;
      * the cabin's lights, which are local light sources, not world objects.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_World"
require "TREK/TREK_Probes"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Ship = TREK.Ship
local W = TREK.World

local Core = {}
TREK.Core = Core

-- Kept for the menus and the helm, which predate TREK_World.
Core.hullCovers    = W.hullCovers
Core.roomToLand    = W.roomToLand
Core.exemptFor     = W.exemptFor
Core.footprintArea = W.footprintArea
Core.landingBeside = W.landingBeside

-- How long to wait for the server to build the cabin before giving up and
-- putting the player back outside. Ticks: about thirty seconds, because on a
-- server the cabin's chunks must load there and then stream here.
local ARRIVAL_TIMEOUT = 1800

---------------------------------------------------------------------------
-- Asking
---------------------------------------------------------------------------
-- The player who last asked the server for something. Replies that are not
-- tied to a request (a refusal) are shown over their head.
Core.lastAsker = nil

function Core.send(player, cmd, args)
    Core.lastAsker = player
    return Net.send(player, cmd, args)
end

local tokens = 0
local waitingMoves = {}   -- token -> { player, kind, onGranted }

--- Asks to move `player` a long way, and calls onGranted(player) if allowed.
function Core.requestMove(player, kind, onGranted)
    if not player then return false end
    tokens = tokens + 1
    local token = tokens
    waitingMoves[token] = { player = player, kind = kind, onGranted = onGranted }
    Core.send(player, "move", { kind = kind, token = token })
    return true
end

Net.onClient("moveGranted", function(args)
    local job = args.token and waitingMoves[args.token]
    if not job then return end
    waitingMoves[args.token] = nil
    job.onGranted(job.player)
end)

--- True while a move of this kind is waiting for the server's answer.
function Core.moveWaiting(kind)
    for _, job in pairs(waitingMoves) do
        if not kind or job.kind == kind then return true end
    end
    return false
end

-- Every reason the server can refuse something needs a line here, or the
-- refusal arrives and says nothing at all -- a menu option that silently does
-- nothing, which is the one thing TREK_Menu.lua's own header forbids.
local DENIALS = {
    access        = "IGUI_TREK_NotCrew",
    notLanded     = "IGUI_TREK_NotLanded",
    bookmarksFull = "IGUI_TREK_BookmarksFull",
    crewSeated    = "IGUI_TREK_CrewSeated",
    notPilot      = "IGUI_TREK_NotPilot",
    inFlight      = "IGUI_TREK_InFlight",
    notFlying         = "IGUI_TREK_NotFlying",
    torpedoReloading  = "IGUI_TREK_TorpedoReloading",
    torpedoRange      = "IGUI_TREK_TorpedoRange",
    torpedoTooClose   = "IGUI_TREK_TorpedoTooClose",
    torpedoNoGround   = "IGUI_TREK_TorpedoNoGround",
    torpedoFailed     = "IGUI_TREK_TorpedoFailed",
    coreFar           = "IGUI_TREK_CoreFar",
    coreEmpty         = "IGUI_TREK_CoreEmpty",
    coreFull          = "IGUI_TREK_CoreFull",
    coreNoCrystal     = "IGUI_TREK_CoreNoCrystal",
    repOff            = "IGUI_TREK_RepOff",
    repFar            = "IGUI_TREK_RepFar",
    repUnknown        = "IGUI_TREK_RepUnknown",
    repNoPattern      = "IGUI_TREK_RepNoPattern",
    repCycling        = "IGUI_TREK_RepCycling",
    repNoItem         = "IGUI_TREK_RepNoItem",
    probeAboard       = "IGUI_TREK_ProbeAboard",
    probeActive       = "IGUI_TREK_ProbeActive",
    probeNoPower      = "IGUI_TREK_ProbeNoPower",
    probeNone         = "IGUI_TREK_ProbeNone",
    probeRackFull     = "IGUI_TREK_ProbeRackFull",
    probeNoRoom       = "IGUI_TREK_ProbeNoRoom",
    probeNoFix        = "IGUI_TREK_ProbeNoFix",
    -- The Doctor. Every one of these is a line the server can send, and
    -- tests/test_multiplayer.py's static pass fails if a deny() literal in
    -- server/ has no entry here: a refusal that arrives and says nothing is
    -- a menu option that silently does nothing.
    emhOff            = "IGUI_TREK_EmhOff",
    emhFar            = "IGUI_TREK_EmhFar",
    emhNoPower        = "IGUI_TREK_EmhNoPower",
    emhNoCrystal      = "IGUI_TREK_EmhNoCrystal",
    emhNoPatient      = "IGUI_TREK_EmhNoPatient",
    emhWell           = "IGUI_TREK_EmhWell",
    emhNotInfected    = "IGUI_TREK_EmhNotInfected",
    emhCuring         = "IGUI_TREK_EmhCuring",
    emhNoOffer        = "IGUI_TREK_EmhNoOffer",
    emhOfferLapsed    = "IGUI_TREK_EmhOfferLapsed",
    emhGone           = "IGUI_TREK_EmhGone",
    -- The downed ensign (ENSIGN.md).
    distressAboard    = "IGUI_TREK_DistressAboard",
    distressGone      = "IGUI_TREK_DistressGone",
    ensignGone        = "IGUI_TREK_EnsignGone",
    ensignSafe        = "IGUI_TREK_EnsignSafe",
    ensignMissing     = "IGUI_TREK_EnsignMissing",
    ensignFar         = "IGUI_TREK_EnsignTooFar",
    -- The Adirondack channel (COMMS.md). commsHeld carries a name and is
    -- handled below.
    commsNoPadd       = "IGUI_TREK_CommsNoPadd",
    commsGone         = "IGUI_TREK_CommsGone",
    commsStale        = "IGUI_TREK_CommsStale",
    commsBusy         = "IGUI_TREK_CommsBusy",
    -- The ledger's own refusals carry numbers and are shown from
    -- POWER_DENIALS below; these are the words if one ever arrives bare.
    noPower           = "IGUI_TREK_NoPowerBare",
    repNoCrystal      = "IGUI_TREK_NoPowerBare",
}

-- The refusals the ledger sends (TREK_Energy.lua). Each carries `need` and
-- `have`, and each text takes them as %1 and %2. `noPower` is the general
-- one; the other three had their own words before the ledger existed and
-- keep them. Without numbers (the EMH panel's own gate sends emhNoPower
-- bare) the plain sentence in DENIALS is used instead.
local POWER_DENIALS = {
    noPower       = "IGUI_TREK_NoPower",
    repNoCrystal  = "IGUI_TREK_RepNoCrystal",
    emhNoPower    = "IGUI_TREK_EmhNoPowerCost",
    probeNoPower  = "IGUI_TREK_ProbeNoPower",
}
Core.POWER_DENIALS = POWER_DENIALS

Net.onClient("denied", function(args)
    -- A refused move is no longer waiting.
    for token, job in pairs(waitingMoves) do
        if not args.kind or job.kind == args.kind then waitingMoves[token] = nil end
    end
    local player = Core.lastAsker or U.player(0)
    if args.why == "recharging" then
        U.note(player, getText("IGUI_TREK_Recharging", tostring(args.secs or "?")),
               255, 170, 90)
    elseif POWER_DENIALS[args.why] and args.need ~= nil then
        -- The numbers are the answer here: "no power" without them is a
        -- refusal a player cannot plan around, and this is the one that sends
        -- them off across the map looking for a crystal. Every refusal the
        -- ledger sends carries them (ENERGY.md 3.1).
        U.note(player, getText(POWER_DENIALS[args.why], tostring(args.need or "?"),
                               tostring(args.have or "?")), 255, 170, 90)
    elseif args.why == "commsHeld" then
        -- Whose channel it is, because "somebody else is speaking" with no
        -- name is thirty seconds of wondering why the buttons are dead
        -- (COMMS.md 2).
        U.note(player, getText("IGUI_TREK_CommsHeld", tostring(args.by or "?")),
               255, 170, 90)
    elseif DENIALS[args.why] then
        U.note(player, getText(DENIALS[args.why]), 255, 90, 90)
    end
end)

---------------------------------------------------------------------------
-- The ship's power, as this client hears about it (ENERGY.md 3.1, 3.3)
---------------------------------------------------------------------------
-- What a charge cost, to the player who asked for it. The continuous drains
-- are silent and report through the gauge instead.
Net.onClient("energized", function(args)
    local player = Core.lastAsker or U.player(0)
    U.note(player, getText("IGUI_TREK_Energizing", tostring(args.cost or "?")),
           150, 220, 255)
end)

--- Every player on this machine hears the ship go dark or come back: it is
--- their ship whether or not they are aboard. Split-screen has four slots.
local function toEveryLocal(text, r, g, b)
    for i = 0, 3 do
        local p = U.player(i)
        if p then U.note(p, text, r, g, b) end
    end
end

Net.onClient("powerDown", function()
    toEveryLocal(getText("IGUI_TREK_PowerDown"), 255, 170, 90)
end)

Net.onClient("powerUp", function(args)
    toEveryLocal(getText(args and args.first and "IGUI_TREK_Commissioned"
                         or "IGUI_TREK_PowerUp"), 150, 220, 255)
end)

---------------------------------------------------------------------------
-- The cabin, as this client sees it
---------------------------------------------------------------------------
--- True when the server has built the cabin at the current revision.
function Core.cabinCurrent()
    local s = Ship.get()
    return s.built == true and s.rev == C.BuildRev
end

local function padHasFloor()
    local x, y, z = U.padSpot()
    local pad = U.square(x, y, z, false)
    return pad ~= nil and U.try("padFloor", function()
        return pad:getFloor() ~= nil
    end) == true
end

-- Lights are local light sources, hung once per session per client.
local lit = false

local function lightCabin()
    if lit then return end
    local cell = U.cell()
    if not cell then return end
    lit = true
    local lamp = U.batch("light.lamppost")
    for _, p in ipairs(C.LampSpots) do
        local x, y = U.at(p[1], p[2])
        lamp(function() cell:addLamppost(x, y, C.CabinZ, 0.92, 0.96, 1.0, 8) end)
    end
    local px, py = U.at(C.Landing.x, C.Landing.y)
    lamp(function() cell:addLamppost(px, py, C.CabinZ, 0.70, 0.88, 1.0, 6) end)

    -- Powered squares make the fridges and ovens work. A square flag, not
    -- synced, so each side sets its own.
    local power = U.batch("power.setHaveElectricity")
    for ox = 0, C.CabinW do
        for oy = 0, C.CabinL do
            if C.inShape(ox, oy) then
                local x, y = U.at(ox, oy)
                local sq = U.square(x, y, C.CabinZ, false)
                if sq then power(function() sq:setHaveElectricity(true) end) end
            end
        end
    end
end

---------------------------------------------------------------------------
-- Arrival: standing on the pad while the server builds the cabin
---------------------------------------------------------------------------
local arrival = nil   -- { x, y, z, tries, player }

-- Ticks to keep holding the player after the deck exists under the pad.
local SETTLE_TICKS = 15

--- Pins a character to a spot with nothing under them, or nothing yet.
---
--- Setting the height alone is not enough, and cost a player's life: the
--- engine moves a character from its *last* position and keeps its own fall
--- state, so a player re-placed at z 4 every tick still fell four floors in
--- the time the cabin took to build, and died in the wilderness below. So the
--- last position is set too, and every piece of fall state is cleared --
--- including the damage the fall had already banked.
function Core.hold(player, x, y, z)
    U.teleport(player, x, y, z)
    U.try("holdFall", function()
        player:setbFalling(false)
        player:setFallTime(0)
        player:setLastFallSpeed(0)
        player:clearFallDamage()
    end)
end

--- Starts an arrival on the transporter pad. When `move` is true the player is
--- put there first; when false they are already standing aboard.
function Core.beginArrival(player, move)
    if not player then return false end
    local x, y, z = U.padSpot()
    if arrival then
        arrival.x, arrival.y, arrival.z, arrival.tries = x, y, z, 0
    else
        arrival = { x = x, y = y, z = z, tries = 0, player = player }
    end
    if move then
        Core.hold(player, x, y, z)
        -- And the loot panel rebuilt from here, in this same tick. Vanilla's
        -- dirtyUI rebuilds it at once from wherever the player now stands, so
        -- the only rebuild that can clear the shuttle out of it is one made
        -- *after* the move: made beside her -- which is where a seat exit or
        -- the foot of the ramp leaves somebody -- it lists her seats again,
        -- the move unloads her, and the next frame's panel asks a seat whose
        -- vehicle is gone (ItemContainer.isOccupiedVehicleSeat, the
        -- NullPointerException in the 2026-09-24 play-test, through the
        -- hatch). Every way aboard comes through here.
        Core.refreshInventoryUI()
    end
    Ship.playerData(player).aboard = true
    Core.send(player, "boarded", {})
    return true
end

function Core.arriving()
    return arrival ~= nil
end

local function endArrival(restorePosition)
    if not arrival then return end
    local job = arrival
    arrival = nil
    if restorePosition and job.player then
        U.teleport(job.player, job.x, job.y, job.z)
    end
end

Net.onClient("cabinReady", function()
    if arrival then arrival.serverReady = true end
end)

local function serviceArrival()
    if not arrival then return end
    local player = arrival.player
    if not player then arrival = nil return end
    arrival.tries = arrival.tries + 1

    if arrival.tries == 1 or arrival.tries == 300 or arrival.tries == 1200 then
        U.log("arrival tick %d: cabin current=%s, server ready=%s, pad floor=%s",
              arrival.tries, tostring(Core.cabinCurrent()),
              tostring(arrival.serverReady == true), tostring(padHasFloor()))
    end

    Core.hold(player, arrival.x, arrival.y, arrival.z)

    -- The server may have answered before this client had the chunks, and a
    -- request sent before the server had them is simply waiting there; ask
    -- again now and then rather than trust one message.
    if arrival.tries % 120 == 0 then Core.send(player, "boarded", {}) end

    if (Core.cabinCurrent() or arrival.serverReady) and padHasFloor() then
        -- Keep holding a moment after the deck appears: the engine settles a
        -- new floor into its collision data over the next few frames, and a
        -- player let go on the same tick can still drop through it.
        arrival.settled = (arrival.settled or 0) + 1
        if arrival.settled < SETTLE_TICKS then return end
        U.log("materialised on the transporter pad")
        lightCabin()
        endArrival(true)
        return
    end

    if arrival.tries > ARRIVAL_TIMEOUT then
        Core.ejectToOutside(player, "the cabin never arrived")
    end
end

--- Last resort: get the player out of the cabin and back onto real ground.
--- Nothing aboard is worth being stuck in the void for, so this does not ask.
function Core.ejectToOutside(player, why)
    player = player or (arrival and arrival.player) or U.player(0)
    U.log("ejecting to outside: %s", tostring(why))
    endArrival(false)
    if not player then return false end

    local s = Ship.get()
    local bx, by, bz = Ship.returnPoint(player)
    if not bx and s.landed then bx, by, bz = s.x, s.y, s.z end
    if not bx then return false end
    local target = W.clearOfShip(bx, by, bz) or W.landingBeside(bx, by, bz)
                   or { x = bx, y = by, z = bz }
    U.teleport(player, target.x, target.y, target.z)
    Ship.playerData(player).aboard = false
    U.note(player, getText("IGUI_TREK_ArrivalFailed"), 255, 90, 90)
    return true
end

---------------------------------------------------------------------------
-- The hatch
---------------------------------------------------------------------------
--- Walks the player up the ramp into the cabin. Only while the ship is down.
function Core.enter(player)
    if not player or U.isInteriorPlayer(player) then return false end
    local s = Ship.get()
    -- The ramp is only there when she is down. Hovering, the hatch is a storey
    -- overhead; the transporter is the way aboard.
    --
    -- It says so now. This returned false in silence, and *Enter* is offered
    -- wherever the hull covers the square -- which it does while she hovers
    -- over you -- so the option was there, did nothing, and explained nothing:
    -- the thing TREK_Menu.lua's own header forbids.
    if not s.landed or s.flying then
        U.note(player, getText(s.flying and "IGUI_TREK_InFlight"
                                        or "IGUI_TREK_NotLanded"), 255, 90, 90)
        return false
    end
    return Core.requestMove(player, "hatchIn", function(p)
        local s = Ship.get()
        if not s.landed then return end
        Ship.setReturnPoint(p, s.x, s.y, s.z)
        Core.beginArrival(p, true)
        U.log("boarding through the hatch")
    end)
end

--- Puts the player back down the ramp.
-- A player who has stepped out and is waiting for the ground by the ship to
-- load before being settled on a clear square: { player, x, y, z, tries }.
local settling = nil

-- Squares from the ship's centre a player first arrives at when stepping out:
-- clear of a hull five long, in any orientation.
local STEP_OUT_OFFSET = 4
-- Shared with the trip forward to the cockpit on the ground, which arrives
-- where stepping out does before it takes the seat.
Core.STEP_OUT_OFFSET = STEP_OUT_OFFSET

--- Puts the player back down beside the ship.
---
--- Rebuilds this client's inventory and loot panels from where the player
--- now is. Vanilla's own call (ISInventoryPage.lua:1330), used by vanilla
--- after anything that changes what a player can reach.
function Core.refreshInventoryUI()
    U.try("inventoryDirty", function() ISInventoryPage.dirtyUI() end)
end

--- Takes a player out of their seat **the way vanilla's exit does**, for the
--- moves that cannot wait for vanilla's exit action: a beam, a trip aft.
---
--- Three steps and the last is the one that was missing. `vehicle:exit` is
--- what ISExitVehicle:perform calls; `OnExitVehicle` is what it fires next
--- (the dashboard listens for it). And the loot panel has to be rebuilt
--- **now, while the shuttle is still loaded**: it was left showing the seat's
--- container, the move into the cabin unloaded the shuttle's chunk, and on the
--- first frame aboard vanilla's panel drew its title by asking that seat
--- `isOccupiedVehicleSeat()` -- whose vehicle was gone. One NullPointerException
--- in every session that went from a seat into the cabin, in every log from
--- 2026-09-23 on (ENSIGN.md's play-test found it; DEV_GUIDE failure
--- signatures).
function Core.leaveSeat(player)
    if not player then return false end
    local vehicle = U.try("playerVehicle", function() return player:getVehicle() end)
    if not vehicle then return false end
    U.try("vehicleExit", function() vehicle:exit(player) end)
    U.try("exitEvent", function() triggerEvent("OnExitVehicle", player) end)
    Core.refreshInventoryUI()
    return true
end

--- Two steps, for the same reason a beam-down has two: the ground by the ship
--- is not loaded while the player is in the cabin, so a clear square cannot be
--- found until they are standing near it. They arrive a few squares off the
--- ship's centre, then settle on the nearest square clear of the vehicle once
--- it loads -- a short step, never under the hull.
function Core.exit(player)
    if not player then return false end
    local s = Ship.get()
    if not s.landed then return false end
    -- Never out of a flying ship. This would put the player down at s.y + 4 on
    -- ground that is not there, and serviceSettling below would hold them for
    -- three hundred ticks looking for a floor before dropping them anyway --
    -- a fall of several levels, which is exactly what got hands-on flight
    -- removed in 1.1. The transporter is the way out.
    if s.flying then
        U.note(player, getText("IGUI_TREK_InFlight"), 255, 90, 90)
        return false
    end
    return Core.requestMove(player, "hatchOut", function(p)
        local s = Ship.get()
        if not s.landed then return end
        endArrival(false)
        Core.repelZombies()
        local x, y, z = s.x, s.y + STEP_OUT_OFFSET, s.z
        if not U.teleport(p, x, y, z) then return end
        Ship.playerData(p).aboard = false
        settling = { player = p, x = s.x, y = s.y, z = s.z, tries = 0 }
        U.log("stepping out beside the ship at %d,%d,%d", s.x, s.y, s.z)
    end)
end

local function serviceSettling()
    local job = settling
    if not job then return end
    local p = job.player
    job.tries = job.tries + 1
    local spot = W.clearOfShip(job.x, job.y, job.z) or W.landingBeside(job.x, job.y, job.z)
    if not spot then
        if job.tries < 300 then
            Core.hold(p, job.x, job.y + STEP_OUT_OFFSET, job.z)
            return
        end
        spot = { x = job.x, y = job.y + STEP_OUT_OFFSET, z = job.z }
    end
    settling = nil
    U.teleport(p, spot.x, spot.y, spot.z)
    Ship.setReturnPoint(p, spot.x, spot.y, spot.z)
    U.log("stepped out at %d,%d,%d", spot.x, spot.y, spot.z)
end

Events.OnTick.Add(function() serviceSettling() end)

---------------------------------------------------------------------------
-- The shields
---------------------------------------------------------------------------
--- Pushes the dead back out of a ring around the landed hull, so stepping out
--- is never an ambush. They are shoved, not killed: no free loot.
---
--- Only zombies this client simulates are moved. A zombie belongs to the
--- client nearest it; the server copies what that client reports, so moving
--- somebody else's zombie here would be undone by their next update. Every
--- client near the hull runs this for its own, which between them is all of
--- them. In single player every zombie is local.
function Core.repelZombies()
    local s = Ship.get()
    if not s.landed or s.shields == false then return 0 end

    local cell = U.cell()
    if not cell then return 0 end
    local zombies = U.try("getZombieList", function() return cell:getZombieList() end)
    if not zombies then return 0 end
    local n = U.try("zombieCount", function() return zombies:size() end) or 0
    if n == 0 then return 0 end

    local radius = C.FieldRadius
    local pushed = 0
    local repel = U.batch("repel")
    for i = 0, n - 1 do
        local z = U.try("zombieAt", function() return zombies:get(i) end)
        if z then
            repel(function()
                if z:isRemoteZombie() then return end
                if math.floor(z:getZ()) ~= s.z then return end
                local dx, dy = z:getX() - s.x, z:getY() - s.y
                local dist = math.sqrt(dx * dx + dy * dy)
                if dist > radius then return end
                if dist < 0.01 then dx, dy, dist = 1, 0, 1 end
                local scale = (radius + 1.5) / dist
                local nx, ny = s.x + dx * scale, s.y + dy * scale
                z:setX(nx) z:setY(ny)
                z:setLastX(nx) z:setLastY(ny)
                z:setTarget(nil)
                z:setStaggerBack(true)
                pushed = pushed + 1
            end)
        end
    end
    return pushed
end

---------------------------------------------------------------------------
-- Nobody climbs out
---------------------------------------------------------------------------
--- Takes the vault away from a character while they are aboard, and gives it
--- back when they are not.
---
--- **Build 42 lets a player climb over a wall, not merely a fence**, and the
--- cabin is exactly the shape that permits it. `IsoPlayer.canClimbOverWall`
--- refuses the climb over a square that `haveRoof` or whose `getBuilding()`
--- is not null -- which is every wall of every house on the map. The cabin is
--- raised at runtime in a cell with no map behind it, so it has neither: to
--- the engine it is four walls standing in the open air, and the climb is
--- allowed. What is on the other side is the ring of deck the walls stand on,
--- and one square past that is the void the cell is made of.
---
--- `ignoreAutoVault` is the engine's own switch and is the *first* thing both
--- routes into the climb read:
---
---     doContextClimbOverWall(dir)    0  getfield IsoPlayer.ignoreAutoVault
---                                    4  ifeq -> 9
---                                    7  iconst_0; ireturn
---     doContextHopOverFence(dir)     the same three instructions
---
--- Neither offers the contextual action while it is set, and `climbOverWall`
--- is only ever reached from `performContextualAction` on an action one of
--- them added -- so nothing is offered and nothing can be performed. Vanilla
--- sets it the same way in `client/Tutorial/Steps.lua:214`, and a client
--- setting a flag on its own character is the one kind of write a client owns
--- outright.
---
--- The two engine-native alternatives were both worse. `IsoFlagType.CantClimb`
--- on the square is read from the square's `PropertyContainer`, which
--- `RecalcProperties()` clears and rebuilds from sprite properties, so it
--- would have to be re-applied for ever and would still be gone for the one
--- frame that mattered. Roofing the cabin or putting it in an `IsoBuilding`
--- changes what the whole cell is -- lighting, weather, the camera's cutaway
--- -- to fix one gesture.
---
--- It is a flag on the character, so it has to be handed back: a crew member
--- who beamed down and could no longer climb a fence would be a worse bug
--- than this one, and it would follow them for the life of the save. This
--- only ever clears what it set.
local vaultHeld = {}

local function holdVault(player)
    local aboard = U.isInteriorPlayer(player)
    local who = U.try("username", function() return player:getUsername() end) or "?"
    if aboard == (vaultHeld[who] == true) then return end
    vaultHeld[who] = aboard or nil
    U.try("setIgnoreAutoVault", function() player:setIgnoreAutoVault(aboard) end)
    U.log("the vault is %s", aboard and "locked while aboard" or "given back")
end

---------------------------------------------------------------------------
-- Keeping anyone aboard on solid ground
---------------------------------------------------------------------------
-- Consecutive updates with nowhere aboard to stand before the player is put
-- back outside. Fifty, because this runs on every update now and used to run
-- on every tenth: the wait is the same five-dozen frames it has always been,
-- which is long enough for a deck that is merely still streaming in.
local VOID_STRIKES = 50

local voidStrikes = 0

local function checkAboard(player)
    if arrival then return end
    if not U.isInteriorPlayer(player) then return end

    -- Loaded straight into the cabin, or the build is out of date: stand on
    -- the pad while the server sorts it out.
    if not Core.cabinCurrent() then
        Core.beginArrival(player, false)
        return
    end
    lightCabin()

    -- **The deck is the cabin's own shape, not "any square with a floor".**
    -- The ring the walls stand on is floored too -- a wall on a midair square
    -- behaves badly, so buildFloor lays deck under every one of them -- and
    -- that ring is where a climb over the wall used to land. A player stood
    -- there passed a floor check, walked one more square, and fell out of the
    -- world. Nothing that carries anybody aboard puts them outside
    -- C.inShape, so anything out there is on its way into the void.
    local x, y, z = player:getX(), player:getY(), player:getZ()
    local offDeck = not U.isAboard(x, y, z)
    if not offDeck then
        local sq = U.square(x, y, math.floor(z), false)
        if sq and sq:getFloor() then
            voidStrikes = 0
            return
        end
    end

    if padHasFloor() then
        voidStrikes = 0
        -- hold, not teleport. The engine keeps its own fall state across a
        -- move, so a falling player put back on the pad carries the fall with
        -- them and drops through it on the next tick -- which is what an
        -- infinite fall actually looked like from inside the game.
        Core.hold(player, U.padSpot())
        if offDeck then
            U.log("put back on the pad from outside the cabin walls")
            U.note(player, getText("IGUI_TREK_NoWayOut"), 255, 170, 90)
        end
        return
    end
    voidStrikes = voidStrikes + 1
    if voidStrikes >= VOID_STRIKES then
        voidStrikes = 0
        Core.ejectToOutside(player, "the cabin has no floor to stand on")
    end
end

Events.OnTick.Add(serviceArrival)

Events.OnGameStart.Add(function()
    U.log("client ready (%s, v%s)", isClient() and "connected to a server" or "single player",
          C.Version)
end)

local fieldTick = 0
Events.OnPlayerUpdate.Add(function(player)
    if not player or not player:isLocalPlayer() or player:isDead() then return end
    -- checkAboard used to run on every tenth update, and a fall is measured
    -- in frames: a rescue that arrives nine frames late arrives after the
    -- drop that kills. It costs two square lookups and only for somebody
    -- standing in the cabin's own cell -- which is what the arrival hold has
    -- done on every tick since 1.0. The shields stay on their own cadence:
    -- they sweep every zombie this client simulates.
    holdVault(player)
    checkAboard(player)
    fieldTick = fieldTick + 1
    if fieldTick >= 20 then
        fieldTick = 0
        Core.repelZombies()
    end
end)

---------------------------------------------------------------------------
-- Debug console
---------------------------------------------------------------------------
-- The design and diagnostic tools run where the world is: they ask the
-- server, which allows them in single player or for an admin, and write their
-- report to the server's log (console.txt in single player).
local function debugCommand(what)
    local player = U.player(0)
    if not player then return false end
    Core.send(player, "debug", { what = what })
    return true
end

function TREK_Rebuild() return debugCommand("rebuild") end
function TREK_Stock()   return debugCommand("stock") end
function TREK_Water()   return debugCommand("water") end
-- Reports each powered fitting's cell and whether it is a device at all. The
-- one that tells "the television is off" from "the television is scenery".
function TREK_Power()   return debugCommand("power") end
function TREK_Galley()  return debugCommand("galley") end
-- The sandbox mode, the reserve, how many patterns the ship holds, how big
-- the catalogue came out, and whether the tray is a container at all.
function TREK_Replicator() return debugCommand("replicator") end
function TREK_Ghosts()  return debugCommand("ghosts") end
-- The sandbox mode, the reserve, the spare crystals, what the Doctor costs,
-- any cure that is running -- and whether he is actually standing there, as
-- against what the ship believes.
function TREK_EMH()     return debugCommand("emh") end
--- Whether each uniform's ClothingItem actually resolved through the GUID
--- table. The static tests prove the files agree with each other; only this
--- proves the *engine* found them, and a uniform that did not resolve wears
--- perfectly and draws nothing.
function TREK_Uniform() return debugCommand("uniform") end
function TREK_Charges() return debugCommand("charges") end

--- TREK_Room(): whether the shuttle could set down where you are standing,
--- and if not, what is in the way. Reads this client's copy of the world.
function TREK_Room()
    local player = U.player(0)
    if not player then return false end
    local x, y = math.floor(player:getX()), math.floor(player:getY())
    local z = math.floor(player:getZ())
    local ok, why, blocked = W.roomToLand(x, y, z, W.exemptFor(player))
    U.log("room to land at %d,%d,%d: %s (needs %d squares, %d blocked%s)",
          x, y, z, ok and "yes" or "no", W.footprintArea(), blocked,
          why and (", first: " .. why) or "")
    return ok
end

return Core
