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
-- Vanilla's vehicle menus are wrapped below, so they must exist first rather
-- than by the luck of load order.
require "Vehicles/ISUI/ISVehicleMenu"
require "Vehicles/ISUI/ISCarMechanicsOverlay"
require "Vehicles/ISUI/ISVehicleSeatUI"

TREK = TREK or {}
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
function VM.onBoardFromSeat(player)
    if not Ship.canUse(player) then return refuse(player) end
    local vehicle = player:getVehicle()
    if not vehicle then return VM.onBoard(player) end
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

local function shipIcon()
    return getTexture("media/ui/TREK_Shuttle.png")
end

-- The radial menu inside the vehicle.
local baseRadial = ISVehicleMenu.showRadialMenu
function ISVehicleMenu.showRadialMenu(playerObj)
    baseRadial(playerObj)
    local vehicle = playerObj and playerObj:getVehicle()
    if not V.isShuttle(vehicle) then return end
    local menu = getPlayerRadialMenu(playerObj:getPlayerNum())
    if not menu or not menu:isReallyVisible() then return end
    menu:addSlice(getText("IGUI_TREK_BoardCabin"), shipIcon(), VM.onBoardFromSeat, playerObj)
end

-- The radial menu beside the vehicle.
local baseRadialOutside = ISVehicleMenu.showRadialMenuOutside
function ISVehicleMenu.showRadialMenuOutside(playerObj)
    baseRadialOutside(playerObj)
    if not playerObj or playerObj:getVehicle() then return end
    local vehicle = ISVehicleMenu.getVehicleToInteractWith(playerObj)
    if not V.isShuttle(vehicle) then return end
    local menu = getPlayerRadialMenu(playerObj:getPlayerNum())
    if not menu or not menu:isReallyVisible() then return end
    menu:addSlice(getText("IGUI_TREK_BoardCabin"), shipIcon(), VM.onBoard, playerObj)
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
    return result
end

---------------------------------------------------------------------------
-- Containers of a vehicle that is gone
---------------------------------------------------------------------------
-- Standing next to a vehicle puts its seats and trunk in the loot window. If
-- that vehicle is then removed -- the ship recalled, an old one swept up, an
-- admin deleting it -- the window is left holding a container whose part no
-- longer has a vehicle, and vanilla's own drawing code throws on it *every
-- frame*: a wall of errors and a black screen. Seen in game, 2026-09-17.
--
-- So the loot window is checked with the very call that throws. U.try turns
-- the exception into a nil, and a container that cannot answer is a dead one:
-- the window goes back to the floor.
local function eachLootPage(fn)
    for i = 0, 3 do
        local page = U.try("playerLoot", function() return getPlayerLoot(i) end)
        if page then fn(i, page) end
    end
end

function VM.dropDeadContainers()
    eachLootPage(function(i, page)
        local inv = page.inventory
        local isVehicle = inv and U.try("isVehiclePart", function()
            return inv:isVehiclePart()
        end) == true
        if not isVehicle then return end
        -- Silent on purpose: throwing *is* the answer here.
        local alive = U.probe(function() inv:isOccupiedVehicleSeat() end)
        if alive then return end
        U.log("a vehicle container in the loot window belongs to a vehicle that " ..
              "is gone; clearing it")
        U.try("clearLootWindow", function()
            local floor = ISInventoryPage.GetFloorContainer(i)
            if floor then page:setNewContainer(floor) end
            page:refreshBackpacks()
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
