--[[ Shuttlecraft -- the vehicle's menus and seat chart.

    The shuttle is driven with the vanilla vehicle controls: V for the radial
    menu, the seat chart to pick or switch a seat, W A S D to drive. This file
    adds only what the shuttle needs on top:

      * its seat chart art -- a silhouette projected from the hull mesh
        (tools/gen_vehicle_assets.py) -- registered the way vanilla registers
        its own cars;
      * a way into the cabin from a seat or from beside the vehicle;
      * access: on a server set to owner-and-crew, only crew may get in;
      * guards on the three vanilla enter/exit fallbacks that assume a seat
        has a door. The shuttle's seats have none (so nobody sitting in them
        can be bitten), and vanilla would throw on them. Every guard applies
        to the shuttle only and hands every other vehicle straight to vanilla.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Ship"
require "TREK/TREK_Vehicle"
require "TREK/TREK_Net"
require "TREK/TREK_Core"
require "TREK/TREK_Flight"
-- Vanilla's vehicle menus are wrapped below, so they must exist first rather
-- than by the luck of load order.
require "Vehicles/ISUI/ISVehicleMenu"
require "Vehicles/ISUI/ISCarMechanicsOverlay"
require "Vehicles/ISUI/ISVehicleSeatUI"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Ship = TREK.Ship
local V = TREK.Vehicle
local Core = TREK.Core

local VM = {}
TREK.VehicleMenu = VM

---------------------------------------------------------------------------
-- Seat chart
---------------------------------------------------------------------------
if ISCarMechanicsOverlay and ISCarMechanicsOverlay.CarList then
    ISCarMechanicsOverlay.CarList[V.SCRIPT] = { imgPrefix = "trekshuttle_", x = 10, y = 0 }
end
if ImageScale then
    ImageScale["trekshuttle_"] = 1.0
end

---------------------------------------------------------------------------
-- Into the cabin
---------------------------------------------------------------------------
-- Players who asked to go aboard from a seat, waiting to be out of it.
local boarding = {}

local function refuse(player)
    U.note(player, getText("IGUI_TREK_NotCrew"), 255, 90, 90)
end

--- From outside the vehicle: through the hatch, as from the hull.
function VM.onBoard(player)
    if not Ship.canUse(player) then return refuse(player) end
    Core.enter(player)
end

--- From a seat: get out, then go aboard.
---
--- On the ground that is a walk: leave the seat, then up the ramp. In the air
--- it cannot be, because leaving the seat means standing beside a ship three
--- levels up -- so it is a transporter trip instead, out of the seat and onto
--- the pad in one move with no tick spent falling. That is what lets the crew
--- go aft in flight and come back (PILOTING.md section 3.2.4).
function VM.onBoardFromSeat(player)
    if not Ship.canUse(player) then return refuse(player) end
    local vehicle = player:getVehicle()
    if not vehicle then return VM.onBoard(player) end

    if TREK.Flight and TREK.Flight.flying() then
        Core.requestMove(player, "beamUp", function(p)
            local v = U.try("playerVehicle", function() return p:getVehicle() end)
            if v then U.try("vehicleExit", function() v:exit(p) end) end
            Ship.setReturnPoint(p, Ship.get().x, Ship.get().y, Ship.get().z)
            Core.beginArrival(p, true)
            U.log("beamed aft to the cabin from the cockpit in flight")
        end)
        return
    end

    boarding[player] = true
    ISVehicleMenu.onExit(player)
end

Events.OnPlayerUpdate.Add(function(player)
    if not boarding[player] then return end
    if player:isDead() then boarding[player] = nil return end
    -- Out of the seat is the moment the exit action finishes.
    if player:getVehicle() then return end
    boarding[player] = nil
    Core.enter(player)
end)

function VM.onRecall(player)
    Core.send(player, "recall", {})
end

---------------------------------------------------------------------------
-- Flying her
---------------------------------------------------------------------------
-- Every one of these is a menu entry rather than a key binding, which is the
-- whole reason a controller and a Steam Deck work with no input code: the
-- radial menu is already reachable with a stick. Driving is vanilla's job.
-- Two options and no more: take her up, set her down. Flight is a binary --
-- she is on the ground or she is hovering at C.FlightLevel -- and the four-rung
-- ladder that used to be here ("Climb", "Dive", between levels 1 and 4) offered
-- three rungs the ship could not actually stand on.
function VM.onTakeOff(player)  TREK.Flight.takeOff(player) end
function VM.onLandBelow(player) TREK.Flight.land(player) end

function VM.onFlightSpeed(player)
    local F = TREK.Flight
    local step = F.speedStep() + 1
    if step > #C.FlightSpeedSteps then step = 1 end
    F.setSpeedStep(player, step)
end

--- Adds the flying options to a menu, if this player is at the controls.
local function addFlightOptions(menu, playerObj, worldobjects)
    local F = TREK.Flight
    if not F or not F.isPilot(playerObj) then return end
    if F.flying() then
        menu:addOption(getText("IGUI_TREK_LandBelow"), worldobjects, VM.onLandBelow, playerObj)
    elseif Ship.get().landed then
        menu:addOption(getText("IGUI_TREK_TakeOff"), worldobjects, VM.onTakeOff, playerObj)
    end
    menu:addOption(getText("IGUI_TREK_FlightSpeed",
                           tostring(F.speed())),
                   worldobjects, VM.onFlightSpeed, playerObj)
end

local function shipIcon()
    return U.try("shipIcon", function()
        return getTexture("media/ui/TREK_Shuttle.png")
    end)
end

-- Written out in full rather than built from the key, so that
-- tests/test_assets.py -- which scans the Lua for "media/ui/*.png" literals --
-- can see them and fail if one is not on disk. A concatenated path would hide
-- them from it, and a radial slice with a nil texture draws no picture at all
-- rather than complaining.
-- TREK_Descend.png is still generated and still on disk, and nothing names it
-- any more: it was the "Dive" slice, and there is no dive. Kept rather than
-- deleted because "take her down" may yet want a second picture, and an unused
-- file costs nothing while a deleted generated asset costs a regeneration.
local ICONS = {
    aboard  = "media/ui/TREK_Aboard.png",
    ascend  = "media/ui/TREK_Ascend.png",
    land    = "media/ui/TREK_Land.png",
}

local function icon(key)
    local path = ICONS[key]
    if not path then return shipIcon() end
    return U.try("radialIcon:" .. key, function()
        return getTexture(path)
    end) or shipIcon()
end

-- The radial menu inside the vehicle.
--
-- The `closing` dance is not defensive habit, it is the whole reason these
-- slices exist at all. Vanilla's showRadialMenu is a *toggle*: its first act
-- is `menu:clear()`, and then
--
--     if menu:isReallyVisible() then ... menu:undisplay() return end
--
-- so `isReallyVisible()` is true only on the press that shuts the menu, and
-- false on the press that opens it. An earlier draft added its slices behind
-- `if not menu:isReallyVisible() then return end`, which is exactly backwards:
-- it bailed on every open and only ran while the menu was being taken down.
-- Neither "go aboard" nor "take her up" was ever added, in any build, and from
-- the outside it looked like flight simply did not work. Ask *before* calling
-- through, because afterwards the state has flipped either way.
local baseRadial = ISVehicleMenu.showRadialMenu
function ISVehicleMenu.showRadialMenu(playerObj)
    local num = playerObj and U.try("radialPlayerNum", function()
        return playerObj:getPlayerNum()
    end)
    local menu = num and U.try("radialMenu", function()
        return getPlayerRadialMenu(num)
    end)
    local closing = menu ~= nil and U.try("radialVisible", function()
        return menu:isReallyVisible()
    end) == true

    baseRadial(playerObj)

    if closing or not menu then return end
    local vehicle = playerObj and playerObj:getVehicle()
    if not V.isShuttle(vehicle) then return end

    menu:addSlice(getText("IGUI_TREK_BoardCabin"), icon("aboard"),
                  VM.onBoardFromSeat, playerObj)

    local F = TREK.Flight
    if not F or not F.isPilot(playerObj) then return end
    if F.flying() then
        menu:addSlice(getText("IGUI_TREK_LandBelow"), icon("land"), VM.onLandBelow, playerObj)
        -- No torpedo slice here on purpose. Firing is **hold right mouse to
        -- aim, left click to fire**, with no mode to switch on, so a menu
        -- entry would be a second way to do a thing that already has one --
        -- and the first draft's radial toggle was worse than that: it was the
        -- *only* way, nobody could guess it, and the feature read as broken.
        -- The controller route still has to be built (TREK_Torpedo.lua), and
        -- when it is, it belongs on the stick and not behind a menu.
    elseif Ship.get().landed then
        menu:addSlice(getText("IGUI_TREK_TakeOff"), icon("ascend"), VM.onTakeOff, playerObj)
    end
end

-- The radial menu beside the vehicle. Toggles exactly as the one inside does,
-- so it is asked the same question in the same order.
local baseRadialOutside = ISVehicleMenu.showRadialMenuOutside
function ISVehicleMenu.showRadialMenuOutside(playerObj)
    if not playerObj then return baseRadialOutside(playerObj) end
    local num = U.try("radialPlayerNum", function() return playerObj:getPlayerNum() end)
    local menu = num and U.try("radialMenu", function()
        return getPlayerRadialMenu(num)
    end)
    local closing = menu ~= nil and U.try("radialVisible", function()
        return menu:isReallyVisible()
    end) == true

    baseRadialOutside(playerObj)

    if closing or not menu then return end
    if playerObj:getVehicle() then return end
    local vehicle = ISVehicleMenu.getVehicleToInteractWith(playerObj)
    if not V.isShuttle(vehicle) then return end
    menu:addSlice(getText("IGUI_TREK_BoardCabin"), icon("aboard"), VM.onBoard, playerObj)
end

-- The right-click menu beside the vehicle.
local baseFillOutside = ISVehicleMenu.FillMenuOutsideVehicle
function ISVehicleMenu.FillMenuOutsideVehicle(player, context, vehicle, test)
    local result = baseFillOutside(player, context, vehicle, test)
    if test or not V.isShuttle(vehicle) then return result end
    local playerObj = getSpecificPlayer(player)
    if not playerObj then return result end
    local sub = context:addOption(getText("IGUI_TREK_Name"), nil, nil)
    local menu = ISContextMenu:getNew(context)
    context:addSubMenu(sub, menu)
    menu:addOption(getText("IGUI_TREK_BoardCabin"), playerObj, VM.onBoard)
    menu:addOption(getText("IGUI_TREK_Recall"), playerObj, VM.onRecall)
    addFlightOptions(menu, playerObj, playerObj)
    return result
end

-- There is deliberately no right-click menu from inside the seat: build 42 has
-- no ISVehicleMenu.FillMenuInsideVehicle to hang one on. A draft of this file
-- wrapped that name behind an "if it exists" guard, which meant it silently
-- never ran -- dead code that looked like a feature, which DEV_GUIDE.md warns
-- is worse than none. The radial menu is the way in from a seat, and it is
-- also the one a controller and a Steam Deck can reach.

---------------------------------------------------------------------------
-- Containers of a vehicle that is gone
---------------------------------------------------------------------------
-- Standing next to a vehicle puts its seats and trunk in the loot window. If
-- that vehicle is then removed -- the ship recalled, an old one swept up, an
-- admin deleting it -- the window is left holding a container whose part no
-- longer has a vehicle, and vanilla's own drawing code throws on it *every
-- frame*: a wall of errors and a black screen. Seen in game, 2026-09-17.
--
-- It is asked *without* throwing, and that correction is the whole of this
-- section's history. The first version probed with the very call that throws
-- (`isOccupiedVehicleSeat`) and read the exception as the answer, wrapped in
-- U.probe so the Lua side stayed quiet. It was quiet. The engine was not:
-- a method that throws out of Java dumps a full stack trace *per call*, and
-- this runs on a timer, so it produced 2932 traces in one short session --
-- the log flood that is DEV_GUIDE.md's own "black screen, character falling,
-- game unresponsive" signature. It did not merely fail to fix the black
-- screen described above; it was a second, larger cause of one.
--
-- DEV_GUIDE.md says it in as many words under "Batch anything repeated per
-- square": pcall silences Lua and the engine keeps dumping. A repeated check
-- must never be built on a throw.
--
-- `getVehiclePart():getVehicle()` answers the same question with two plain
-- null checks, and is the chain vanilla's own loot window uses
-- (client/ISUI/LootWindow/ISLootWindowContainerControls.lua:212).
local function eachLootPage(fn)
    for i = 0, 3 do
        local page = U.try("playerLoot", function() return getPlayerLoot(i) end)
        if page then fn(i, page) end
    end
end

--- The vehicle a loot-window container still belongs to, or nil. Never throws.
local function vehicleBehind(inv)
    local part = U.try("lootVehiclePart", function() return inv:getVehiclePart() end)
    if not part then return nil end
    return U.try("lootPartVehicle", function() return part:getVehicle() end)
end

-- Reported once rather than once per sweep: if clearing does not take, the
-- line would otherwise be its own flood.
local reportedDead = false

function VM.dropDeadContainers()
    eachLootPage(function(i, page)
        local inv = page.inventory
        local isVehicle = inv and U.try("isVehiclePart", function()
            return inv:isVehiclePart()
        end) == true
        if not isVehicle then return end
        if vehicleBehind(inv) then return end

        if not reportedDead then
            reportedDead = true
            U.log("a vehicle container in the loot window belongs to a vehicle " ..
                  "that is gone; clearing it")
        end
        -- Put the window on the floor container, and **do not call
        -- refreshBackpacks**. That was here, and it is the very function that
        -- throws: refreshBackpacks -> addContainerButton ->
        -- getEffectiveCapacity -> getCapacity -> isOccupiedVehicleSeat, which
        -- is where the null vehicle blows up. Calling it to tidy up a dead
        -- container walks the dead container to do so.
        --
        -- The same shape as the probe this section already replaced once: a
        -- repair built on the call that throws. Setting the container is
        -- enough; vanilla rebuilds the button row itself on the next update,
        -- and by then the thing that held the stale reference is gone.
        U.try("clearLootWindow", function()
            local floor = ISInventoryPage.GetFloorContainer(i)
            if floor then page:setNewContainer(floor) end
        end)
    end)
end

-- The server says when it removes the ship's vehicle, so the window is put
-- right at once rather than on the next sweep.
TREK.Net.onClient("vehicleGone", function()
    VM.dropDeadContainers()
end)

local deadTick = 0
Events.OnPlayerUpdate.Add(function()
    deadTick = deadTick + 1
    if deadTick < 30 then return end
    deadTick = 0
    VM.dropDeadContainers()
end)

---------------------------------------------------------------------------
-- Access
---------------------------------------------------------------------------
local baseOnEnter = ISVehicleMenu.onEnter
function ISVehicleMenu.onEnter(playerObj, vehicle, seat)
    if V.isShuttle(vehicle) and not Ship.canUse(playerObj) then
        return refuse(playerObj)
    end
    return baseOnEnter(playerObj, vehicle, seat)
end

---------------------------------------------------------------------------
-- Doorless seats
---------------------------------------------------------------------------
-- Vanilla closes the door of the seat it switches through with
-- `vehicle:getPassengerDoor(seat):getDoor()`, unguarded, in the fallback taken
-- when the chosen seat cannot be reached directly. The shuttle's seats all have
-- their own way in and out, so these paths are rare -- but a blocked side (a
-- wall, another car) takes them, and they would throw. These are vanilla's
-- functions for the shuttle with the door steps left out.

local function enterVia(playerObj, vehicle, seatTo, switchArgs)
    ISVehicleMenu.onEnterAux(playerObj, vehicle, seatTo)
    ISTimedActionQueue.add(ISSwitchVehicleSeat:new(playerObj, switchArgs[1], switchArgs[2]))
end

local baseProcessEnter = ISVehicleMenu.processEnter
function ISVehicleMenu.processEnter(playerObj, vehicle, seat)
    if not V.isShuttle(vehicle) then return baseProcessEnter(playerObj, vehicle, seat) end
    if not vehicle:isSeatInstalled(seat) or playerObj:isBlockMovement() then
        return baseProcessEnter(playerObj, vehicle, seat)
    end
    if vehicle:isEnterBlocked(playerObj, seat) then
        local seat2 = ISVehicleMenu.getBestSwitchSeatEnter(playerObj, vehicle, seat)
        if seat2 then enterVia(playerObj, vehicle, seat2, { seat }) end
    else
        ISVehicleMenu.onEnterAux(playerObj, vehicle, seat)
    end
end

local baseProcessShiftEnter = ISVehicleMenu.processShiftEnter
function ISVehicleMenu.processShiftEnter(playerObj, vehicle, seat)
    if not V.isShuttle(vehicle) or seat == 0 then
        return baseProcessShiftEnter(playerObj, vehicle, seat)
    end
    if not vehicle:isSeatInstalled(0) or not vehicle:isSeatInstalled(seat)
       or not vehicle:canSwitchSeat(seat, 0) then
        return baseProcessShiftEnter(playerObj, vehicle, seat)
    end
    if vehicle:isEnterBlocked(playerObj, seat) then
        local seat2 = ISVehicleMenu.getBestSwitchSeatEnter(playerObj, vehicle, seat)
        if seat2 then enterVia(playerObj, vehicle, seat2, { 0, seat2 }) end
    else
        enterVia(playerObj, vehicle, seat, { 0, seat })
    end
end

local baseOnExit = ISVehicleMenu.onExit
function ISVehicleMenu.onExit(playerObj, seatFrom)
    local vehicle = playerObj and playerObj:getVehicle()
    if not V.isShuttle(vehicle) then return baseOnExit(playerObj, seatFrom) end

    -- Not into thin air. Vanilla's exit walks the character out to a square
    -- beside the vehicle, and beside a vehicle three levels up is a drop. The
    -- two ways out of a flying shuttle both move the character rather than
    -- walk them: through to the cabin, or down on the transporter. The one
    -- exception is going aboard, which leaves the seat on purpose and is
    -- caught by the boarding watcher before the character can fall.
    if TREK.Flight and TREK.Flight.flying() and not boarding[playerObj] then
        U.note(playerObj, getText("IGUI_TREK_SeatLocked"), 255, 170, 90)
        return
    end

    seatFrom = seatFrom or vehicle:getSeat(playerObj)
    if not vehicle:isExitBlocked(playerObj, seatFrom) then
        return baseOnExit(playerObj, seatFrom)
    end
    local radialMenu = getPlayerRadialMenu(playerObj:getPlayerNum())
    if radialMenu:isReallyVisible() then radialMenu:undisplay() end
    if playerObj:isBlockMovement() then return end
    if vehicle:isDriver(playerObj) and math.abs(vehicle:getCurrentSpeedKmHour()) > 0.8 then
        ISTimedActionQueue.add(ISStopVehicle:new(playerObj))
    elseif not vehicle:isDriver(playerObj) and not vehicle:isStopped() then
        HaloTextHelper.addBadText(playerObj, getText("IGUI_PlayerText_CanNotExitFromMovingCar"))
        return
    end
    local seatTo = ISVehicleMenu.getBestSwitchSeatExit(playerObj, vehicle, seatFrom)
    if seatTo then
        ISTimedActionQueue.add(ISSwitchVehicleSeat:new(playerObj, seatTo))
        ISVehicleMenu.onExitAux(playerObj, seatTo)
    end
end

return VM
