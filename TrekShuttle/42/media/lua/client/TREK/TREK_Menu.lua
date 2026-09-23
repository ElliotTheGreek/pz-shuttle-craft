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
--- Greys an option and says why. A menu entry that is simply absent teaches
--- the player nothing; one that is there and refuses, with the reason on its
--- tooltip, teaches them what to go and fix.
local function grey(option, why)
    option.notAvailable = true
    option.toolTip = ISWorldObjectContextMenu.addToolTip()
    option.toolTip.description = getText(why)
end

-- **The menu is the console.** The probes were going to get a fitting of
-- their own and a panel to go with it; a right-click submenu does the same
-- job, costs no deck in a twenty-four square cabin, and needs no change to
-- the authored interior.
--
-- Everything here is a *request*. The client does not know whether the ship
-- can afford a probe -- it reads the reserve the server last published, which
-- is good enough to grey an option and not good enough to act on -- so the
-- server checks again and refuses with a reason.

function M.onLaunchProbe(_, player)
    Core.send(player, "launchProbe", {})
    U.note(player, getText("IGUI_TREK_ProbeAway"), 150, 200, 255)
end

function M.onShowContact(_, player, contactId)
    local num = U.try("contactPlayerNum", function()
        return player:getPlayerNum()
    end) or 0
    if not TREK.MapContacts or not TREK.MapContacts.focus(num, contactId) then
        U.note(player, getText("IGUI_TREK_ContactGone"), 255, 170, 90)
    end
end

--- Which compass point a contact lies on from here, so the list reads as
--- directions rather than as coordinates nobody can picture.
-- tan(22.5 degrees): half an octant, which is all the trigonometry this
-- needs. The first version used math.atan2, which **Kahlua has and Lua 5.3
-- onwards does not** -- so it would have worked in the game and threw in the
-- tests. The test VM being stricter than the engine is the lucky direction
-- for that to break in; comparing two ratios is clearer anyway.
local OCTANT = 0.4142135

local function bearingOf(fromX, fromY, toX, toY)
    local dx, dy = toX - fromX, toY - fromY
    local ax, ay = math.abs(dx), math.abs(dy)
    -- North is -y on this map, as it is on the screen.
    if ax <= OCTANT * ay then
        return dy < 0 and "N" or "S"
    elseif ay <= OCTANT * ax then
        return dx > 0 and "E" or "W"
    elseif dy < 0 then
        return dx > 0 and "NE" or "NW"
    else
        return dx > 0 and "SE" or "SW"
    end
end

local function sensorMenu(menu, player, worldobjects)
    local sub = menu:addOption(getText("IGUI_TREK_Sensors"), worldobjects, nil)
    local sensors = ISContextMenu:getNew(menu)
    menu:addSubMenu(sub, sensors)

    local P = TREK.Probes
    local active = P.active()
    local reserve = math.floor(TREK.Power.reserve())

    -- The cost is on the option, because "Launch probe" with no number is a
    -- button a player cannot plan around -- the same reason the warp core
    -- puts its spare count on its own option.
    local launch = sensors:addOption(
        getText("IGUI_TREK_ProbeLaunch", tostring(C.ProbeCost)),
        worldobjects, M.onLaunchProbe, player)
    if active then
        grey(launch, "IGUI_TREK_ProbeActive")
    elseif reserve < C.ProbeCost then
        grey(launch, "IGUI_TREK_ProbeNoPower")
    end

    if active then
        local pct = math.floor((active.progress / math.max(1, active.ticks)) * 100)
        local flying = sensors:addOption(
            getText("IGUI_TREK_ProbeFlight", tostring(pct)), worldobjects, nil)
        flying.notAvailable = true
    end

    local contacts = P.unresolved()
    if #contacts == 0 then
        local none = sensors:addOption(getText("IGUI_TREK_NoContacts"),
                                       worldobjects, nil)
        none.notAvailable = true
        return
    end

    local px = U.try("contactX", function() return player:getX() end) or 0
    local py = U.try("contactY", function() return player:getY() end) or 0
    for _, contact in ipairs(contacts) do
        local dist = math.floor(math.sqrt((contact.x - px) ^ 2 + (contact.y - py) ^ 2))
        local key = C.ContactLabels[contact.kind]
        if key then
            local label = getText(key, tostring(dist),
                                  bearingOf(px, py, contact.x, contact.y))
            sensors:addOption(label, worldobjects, M.onShowContact, player,
                              contact.id)
        end
    end
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
    menu:addOption(getText("IGUI_TREK_BookmarkHere"), worldobjects,
                   M.onBookmarkHere, player)
    sensorMenu(menu, player, worldobjects)
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
