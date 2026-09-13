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
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

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

---------------------------------------------------------------------------
-- Actions
---------------------------------------------------------------------------
function M.onBeamUp(_, player)
    local ok, why = TREK.Transport.beamUp(player)
    if not ok and why == "busy" then
        U.note(player, getText("IGUI_TREK_TransporterBusy"), 255, 170, 90)
    end
end

function M.onBeamDown(_, player)
    local ok, why = TREK.Transport.beamDown(player)
    if ok then return end
    if why == "busy" then
        U.note(player, getText("IGUI_TREK_TransporterBusy"), 255, 170, 90)
    elseif why == "nowhere" then
        U.note(player, getText("IGUI_TREK_NoReturnPoint"), 255, 90, 90)
    end
end

--- Calls the ship down onto a square, or says why it will not come.
---
--- This is where a player finds out how much room the shuttle needs, so the
--- message carries the numbers rather than a flat refusal.
function M.onCallDown(_, player, x, y, z)
    local sq = U.square(x, y, z, false)
    if not sq then return end

    local ok, why, blocked = TREK.Core.roomToLand(x, y, z)
    if ok then
        local landed, failed = TREK.Core.land(sq, player)
        if landed then
            U.note(player, getText("IGUI_TREK_Landed"))
        else
            U.note(player, getText("IGUI_TREK_NoRoom",
                                   TREK.Core.footprintArea(), 1), 255, 90, 90)
            U.log("call down refused after passing the check: %s", tostring(failed))
        end
        return
    end

    local text
    if why == "vehicle" then
        text = getText("IGUI_TREK_NoRoomVehicle")
    elseif why == "void" then
        text = getText("IGUI_TREK_NoRoomVoid")
    else
        text = getText("IGUI_TREK_NoRoom", TREK.Core.footprintArea(), blocked)
    end
    U.note(player, text, 255, 90, 90)
end

function M.onRecall(_, player)
    if TREK.Core.recall() then
        U.note(player, getText("IGUI_TREK_Recalled"))
    end
end

function M.onEnter(_, player)
    TREK.Core.enter(player)
end

function M.onExit(_, player)
    TREK.Core.exit(player)
end

function M.onHelm(_, player)
    TREK.Travel.openHelm(player)
end

function M.onBookmarkHere(_, player)
    local ok, err = TREK.Travel.addBookmark(nil)
    if not ok then
        U.note(player, tostring(err), 255, 90, 90)
    else
        U.note(player, getText("IGUI_TREK_Bookmarked"), 90, 255, 120)
    end
end

---------------------------------------------------------------------------
-- Menu assembly
---------------------------------------------------------------------------
local function aboardMenu(context, player, worldobjects, test)
    if test then return ISWorldObjectContextMenu.setTest() end
    local s = U.state()

    local sub = context:addOption(getText("IGUI_TREK_Name"), worldobjects, nil)
    local menu = ISContextMenu:getNew(context)
    context:addSubMenu(sub, menu)

    menu:addOption(getText("IGUI_TREK_Helm"), worldobjects, M.onHelm, player)
    menu:addOption(getText("IGUI_TREK_BeamDown"), worldobjects, M.onBeamDown, player)
    -- The ramp only exists when the ship is on the ground. Overhead, the
    -- transporter is the only way off, and offering a door that cannot open
    -- would just be a dead menu entry.
    if s.landed then
        menu:addOption(getText("IGUI_TREK_StepOutside"), worldobjects, M.onExit, player)
    end
    menu:addOption(getText("IGUI_TREK_BookmarkHere"), worldobjects,
                   M.onBookmarkHere, player)
    return true
end

local function groundMenu(context, player, worldobjects, sq, test)
    local onHull = TREK.Core.hullCovers(sq:getX(), sq:getY(), sq:getZ())

    -- Somewhere a person could stand is somewhere worth *offering* to land,
    -- even when the footprint will not fit. The refusal, with its reasons, is
    -- the whole point.
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

U.log("loaded v%s -- menus registered on OnPreFillWorldObjectContextMenu",
      C.Version)

return M
