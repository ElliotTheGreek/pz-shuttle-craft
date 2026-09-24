--[[ Shuttlecraft -- right-click menus.

    Everything hangs off OnPreFillWorldObjectContextMenu rather than
    OnFillWorldObjectContextMenu. Build 42 returns early from the menu builder
    when the clicked square holds nothing the base game considers
    interactable, so the later event never fires on bare grass, road or an
    empty floor -- which is exactly the ground a shuttle most needs to be
    called down onto.

    One rule shapes the outside menu. "Call the shuttle down here" is offered
    on any square a person could stand on, not only on squares that pass the
    footprint check, and the refusal is delivered when it is clicked. Hiding
    the option would be tidier and much worse: a player who cannot see the
    option has no way to learn that the ship needs five tiles of clear ground,
    and would conclude the mod was broken.

    The same rule covers access. On a server that limits the ship to its
    owner and crew, everyone still sees the options and is told why when the
    server refuses -- never a menu that silently does nothing.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Ship"
require "TREK/TREK_World"
require "TREK/TREK_Core"
require "TREK/TREK_Transport"
require "TREK/TREK_Travel"
require "TREK/TREK_Probes"
require "TREK/TREK_Power"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Ship = TREK.Ship
local W = TREK.World
local Core = TREK.Core

local M = {}
TREK.Menu = M

--- The square under the cursor, taken from the menu position so that it
--- resolves even when the tile holds no objects at all.
local function clickedSquare(playerIndex, context, player)
    local z = math.floor(player:getZ())
    local x = U.try("screenToIsoX", function()
        return screenToIsoX(playerIndex, context.x, context.y, z)
    end)
    local y = U.try("screenToIsoY", function()
        return screenToIsoY(playerIndex, context.x, context.y, z)
    end)
    if not x or not y then return nil end
    return U.square(x, y, z, false)
end

local function busyNote(player)
    U.note(player, getText("IGUI_TREK_TransporterBusy"), 255, 170, 90)
end

---------------------------------------------------------------------------
-- Actions
---------------------------------------------------------------------------
function M.onBeamUp(_, player)
    local ok, why = TREK.Transport.beamUp(player)
    if not ok and why == "busy" then busyNote(player) end
end

function M.onToCockpit(_, player)
    local ok, why = TREK.Transport.toCockpit(player)
    if not ok and why == "busy" then busyNote(player) end
end

function M.onBeamDown(_, player)
    local ok, why = TREK.Transport.beamDown(player)
    if ok then return end
    if why == "busy" then
        busyNote(player)
    elseif why == "nowhere" then
        U.note(player, getText("IGUI_TREK_NoReturnPoint"), 255, 90, 90)
    end
end

--- Calls the ship down onto a square, or says why it will not come. This is
--- where a player finds out how much room the shuttle needs, so the message
--- carries the numbers. The server looks again before it lands.
function M.onCallDown(_, player, x, y, z)
    -- Refused here first when the ship plainly cannot pay (ENERGY.md 4.1); the
    -- server checks again, and is the one that charges.
    if TREK.Power.dark() or not TREK.Power.canPay(C.LandCost) then
        U.note(player, getText("IGUI_TREK_NoPowerFor", tostring(C.LandCost),
                               tostring(math.floor(TREK.Power.reserve()))), 255, 170, 90)
        return
    end
    local ok, why, blocked = W.roomToLand(x, y, z, W.exemptFor(player))
    if not ok then
        U.note(player, TREK.Travel.refusalText(why, blocked), 255, 90, 90)
        return
    end
    Core.send(player, "land", { x = x, y = y, z = z })
end

function M.onRecall(_, player)
    Core.send(player, "recall", {})
end

function M.onEnter(_, player)
    if Core.moveWaiting() or TREK.Transport.pending then
        busyNote(player)
        return
    end
    Core.enter(player)
end

function M.onExit(_, player)
    if Core.moveWaiting() or TREK.Transport.pending then
        busyNote(player)
        return
    end
    Core.exit(player)
end

function M.onHelm(_, player)
    TREK.Travel.openHelm(player)
end

---------------------------------------------------------------------------
-- Long-range sensors
---------------------------------------------------------------------------
-- One option, which opens the console. This was a submenu that carried the
-- launch button, the flight percentage and every contact; it worked and it
-- read as a list of settings rather than as a station on a starship, and a
-- probe in flight had nowhere to show progress. TREK_ProbeUI is the panel it
-- became -- the helm's LCARS for the fourth time.

function M.onSensors(_, player)
    TREK.ProbeUI.open(player)
end

function M.onBookmarkHere(_, player)
    local ok, err = TREK.Travel.addBookmark(player, nil)
    if not ok then
        U.note(player, tostring(err), 255, 90, 90)
    else
        U.note(player, getText("IGUI_TREK_Bookmarked"), 90, 255, 120)
    end
end

function M.onSetCrew(_, player, name, on)
    Core.send(player, "setCrew", { name = name, on = on })
end

---------------------------------------------------------------------------
-- Menu assembly
---------------------------------------------------------------------------
--- Crew management, offered only where it means something: a server set to
--- owner-and-crew access, to the owner or an admin.
local function crewMenu(menu, player, worldobjects)
    if not isClient() then return end
    if Ship.accessMode() ~= 2 or not Ship.canManageCrew(player) then return end

    local s = Ship.get()
    local me = Ship.usernameOf(player)
    local sub = menu:addOption(getText("IGUI_TREK_Crew"), worldobjects, nil)
    local crew = ISContextMenu:getNew(menu)
    menu:addSubMenu(sub, crew)

    local any = false
    for _, other in ipairs(U.players()) do
        local name = Ship.usernameOf(other)
        if name ~= me and name ~= s.owner then
            any = true
            if s.crew and s.crew[name] then
                crew:addOption(getText("IGUI_TREK_CrewRemove", name), worldobjects,
                               M.onSetCrew, player, name, false)
            else
                crew:addOption(getText("IGUI_TREK_CrewAdd", name), worldobjects,
                               M.onSetCrew, player, name, true)
            end
        end
    end
    if not any then
        local none = crew:addOption(getText("IGUI_TREK_CrewNobody"), worldobjects, nil)
        none.notAvailable = true
    end
end

local function aboardMenu(context, player, worldobjects, test)
    if test then return ISWorldObjectContextMenu.setTest() end
    local s = Ship.get()

    local sub = context:addOption(getText("IGUI_TREK_Name"), worldobjects, nil)
    local menu = ISContextMenu:getNew(context)
    context:addSubMenu(sub, menu)

    menu:addOption(getText("IGUI_TREK_Helm"), worldobjects, M.onHelm, player)
    menu:addOption(getText("IGUI_TREK_BeamDown"), worldobjects, M.onBeamDown, player)
    -- The ramp only exists when the ship is on the ground. Overhead or in
    -- flight, the transporter is the only way off.
    if s.landed and not s.flying then
        menu:addOption(getText("IGUI_TREK_StepOutside"), worldobjects, M.onExit, player)
    end
    -- And forward to the cockpit: straight into a seat, whether she is flying
    -- or on the ground. In flight it is the only way back to the controls;
    -- on the ground it saves stepping out and walking round to the door.
    -- Not while she is overhead, where there are no seats anywhere near.
    if s.flying or s.landed then
        menu:addOption(getText("IGUI_TREK_ToCockpit"), worldobjects, M.onToCockpit, player)
    end
    menu:addOption(getText("IGUI_TREK_BookmarkHere"), worldobjects,
                   M.onBookmarkHere, player)
    menu:addOption(getText("IGUI_TREK_Sensors"), worldobjects, M.onSensors,
                   player)
    crewMenu(menu, player, worldobjects)
    return true
end

local function groundMenu(context, player, worldobjects, sq, test)
    local onHull = W.hullCovers(sq:getX(), sq:getY(), sq:getZ())

    -- Somewhere a person could stand is somewhere worth *offering* to land,
    -- even when the footprint will not fit. The refusal is the point.
    local standable = U.try("standable", function()
        return sq:getFloor() ~= nil and not sq:isSolid()
    end) == true

    if not onHull and not standable then return false end
    if test then return ISWorldObjectContextMenu.setTest() end

    local sub = context:addOption(getText("IGUI_TREK_Name"), worldobjects, nil)
    local menu = ISContextMenu:getNew(context)
    context:addSubMenu(sub, menu)

    if onHull then
        menu:addOption(getText("IGUI_TREK_Enter"), worldobjects, M.onEnter, player)
        menu:addOption(getText("IGUI_TREK_Recall"), worldobjects, M.onRecall, player)
    else
        menu:addOption(getText("IGUI_TREK_CallDown"), worldobjects, M.onCallDown,
                       player, sq:getX(), sq:getY(), sq:getZ())
    end
    menu:addOption(getText("IGUI_TREK_BeamUp"), worldobjects, M.onBeamUp, player)
    return true
end

local function onPreFill(playerIndex, context, worldobjects, test)
    local player = U.player(playerIndex)
    if not player then return end

    if U.isInteriorPlayer(player) then
        return aboardMenu(context, player, worldobjects, test)
    end

    local sq = clickedSquare(playerIndex, context, player)
    if not sq then return end
    return groundMenu(context, player, worldobjects, sq, test)
end

Events.OnPreFillWorldObjectContextMenu.Add(onPreFill)

return M
