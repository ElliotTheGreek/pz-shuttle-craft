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

local DENIALS = {
    access        = "IGUI_TREK_NotCrew",
    notLanded     = "IGUI_TREK_NotLanded",
    bookmarksFull = "IGUI_TREK_BookmarksFull",
}

Net.onClient("denied", function(args)
    -- A refused move is no longer waiting.
    for token, job in pairs(waitingMoves) do
        if not args.kind or job.kind == args.kind then waitingMoves[token] = nil end
    end
    local player = Core.lastAsker or U.player(0)
    if args.why == "recharging" then
        U.note(player, getText("IGUI_TREK_Recharging", tostring(args.secs or "?")),
               255, 170, 90)
    elseif DENIALS[args.why] then
        U.note(player, getText(DENIALS[args.why]), 255, 90, 90)
    end
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
    if move then Core.hold(player, x, y, z) end
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
    local target = W.landingBeside(bx, by, bz) or { x = bx, y = by, z = bz }
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
    if not Ship.get().landed then return false end
    return Core.requestMove(player, "hatchIn", function(p)
        local s = Ship.get()
        if not s.landed then return end
        Ship.setReturnPoint(p, s.x, s.y, s.z)
        Core.beginArrival(p, true)
        U.log("boarding through the hatch")
    end)
end

--- Puts the player back down the ramp.
function Core.exit(player)
    if not player then return false end
    if not Ship.get().landed then return false end
    return Core.requestMove(player, "hatchOut", function(p)
        local s = Ship.get()
        if not s.landed then return end
        endArrival(false)
        Core.repelZombies()
        local target = W.landingBeside(s.x, s.y, s.z) or { x = s.x, y = s.y, z = s.z }
        if not U.teleport(p, target.x, target.y, target.z) then return end
        Ship.playerData(p).aboard = false
        Ship.setReturnPoint(p, target.x, target.y, target.z)
        U.log("stepped out at %d,%d,%d", target.x, target.y, target.z)
    end)
end

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
-- Keeping anyone aboard on solid ground
---------------------------------------------------------------------------
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

    local sq = U.square(player:getX(), player:getY(), math.floor(player:getZ()), false)
    if sq and sq:getFloor() then
        voidStrikes = 0
        return
    end
    if padHasFloor() then
        voidStrikes = 0
        U.teleport(player, U.padSpot())
        return
    end
    voidStrikes = voidStrikes + 1
    if voidStrikes >= 5 then
        voidStrikes = 0
        Core.ejectToOutside(player, "the cabin has no floor to stand on")
    end
end

Events.OnTick.Add(serviceArrival)

Events.OnGameStart.Add(function()
    U.log("client ready (%s, v%s)", isClient() and "connected to a server" or "single player",
          C.Version)
end)

local rescueTick, fieldTick = 0, 0
Events.OnPlayerUpdate.Add(function(player)
    if not player or not player:isLocalPlayer() or player:isDead() then return end
    rescueTick = rescueTick + 1
    if rescueTick >= 10 then
        rescueTick = 0
        checkAboard(player)
    end
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
function TREK_Galley()  return debugCommand("galley") end
function TREK_Ghosts()  return debugCommand("ghosts") end
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
