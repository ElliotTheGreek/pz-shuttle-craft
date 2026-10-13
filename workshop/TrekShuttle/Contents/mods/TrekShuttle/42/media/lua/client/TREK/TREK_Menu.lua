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
require "TREK/TREK_Rules"
require "TREK/TREK_Ship"
require "TREK/TREK_World"
require "TREK/TREK_Core"
require "TREK/TREK_Transport"
require "TREK/TREK_Travel"
require "TREK/TREK_Probes"
require "TREK/TREK_Power"
require "TREK/TREK_AdirondackClient"
require "TREK/TREK_Access"
require "TREK/TREK_AccessUI"
require "TREK/TREK_Marooned"
require "TREK/TREK_Text"

-- What this file shows is read through TREK_Text: the server's own name for
-- the ship in orbit goes into it (SERVERS.md).
local getText = TREK.Text.get

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Ship = TREK.Ship
local W = TREK.World
local Core = TREK.Core
local V = TREK.Vehicle
local Net = TREK.Net

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
    local landCost = TREK.Rules.cost("LandCost")
    if TREK.Power.dark() or not TREK.Power.canPay(landCost) then
        U.note(player, getText("IGUI_TREK_NoPowerFor", tostring(landCost),
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

--- Development sessions only (U.devMode): to the shuttle, wherever she is.
function M.onDevToShuttle(_, player)
    local ok, why = TREK.Transport.devToShuttle(player)
    if ok then return end
    if why == "busy" then
        busyNote(player)
    elseif why == "nowhere" then
        U.note(player, getText("IGUI_TREK_DevNoShuttle"), 255, 170, 90)
    end
end

--- Development sessions only: an annotated map into the pockets, to read.
function M.onDevMap(_, player)
    Core.send(player, "devMap", {})
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
-- More than one shuttle (SERVERS.md, personal shuttles)
---------------------------------------------------------------------------
--- What a ship is called on this player's menu: theirs, the shared one, or
--- somebody's by name.
function M.shipLabel(id, player)
    if id == 1 then return getText("IGUI_TREK_ShipShared") end
    local owner = Ship.ownerOf(id)
    if owner == Ship.usernameOf(player) then return getText("IGUI_TREK_ShipYours") end
    return getText("IGUI_TREK_ShipOf", tostring(owner or "?"))
end

--- The ship whose hull covers this square, or nil. Any of them: a hull is
--- there to be walked up to whoever it belongs to.
function M.hullShipAt(x, y, z)
    for _, id in ipairs(Ship.ids()) do
        if U.usingShip(id, W.hullCovers, x, y, z) then return id end
    end
    return nil
end

--- Makes `id` the ship this player is dealing with, and then does `action`
--- with it. Walking up to a shuttle and asking for its door is choosing it.
function M.onShip(_, player, id, action)
    Ship.select(id)
    U.shipNow = Ship.mine(player)
    if action then action(nil, player) end
end

--- Which shuttle the menu on the ground speaks to, where there is a choice.
local function hailMenu(menu, player, worldobjects)
    if not isClient() then return end
    local usable = Ship.usable(player)
    if #usable < 2 then return end
    local sub = menu:addOption(getText("IGUI_TREK_Hail"), worldobjects, nil)
    local hail = ISContextMenu:getNew(menu)
    menu:addSubMenu(sub, hail)
    for _, id in ipairs(usable) do
        local option = hail:addOption(M.shipLabel(id, player), worldobjects, M.onShip, player, id, nil)
        -- The one in hand is greyed: it is the answer to "which is it now".
        if id == U.shipNow then option.notAvailable = true end
    end
end

---------------------------------------------------------------------------
-- Menu assembly
---------------------------------------------------------------------------
--- Crew management, offered only where it means something: a server set to
--- owner-and-crew access, to the owner or an admin.
local function crewMenu(menu, player, worldobjects)
    if not isClient() then return end
    -- The shared ship's crew means something only under owner-and-crew; a
    -- personal shuttle's always does: nobody else may use it at all.
    local personal = Ship.isPersonal()
    if not personal and Ship.accessMode() ~= Ship.AccessCrew then return end
    if not Ship.canManageCrew(player) then return end

    local s = Ship.get()
    local me = Ship.usernameOf(player)
    local owner = personal and Ship.ownerOf(U.shipNow) or s.owner
    local sub = menu:addOption(getText("IGUI_TREK_Crew"), worldobjects, nil)
    local crew = ISContextMenu:getNew(menu)
    menu:addSubMenu(sub, crew)

    local any = false
    for _, other in ipairs(U.players()) do
        local name = Ship.usernameOf(other)
        if name ~= me and name ~= owner then
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

function M.onCabin(_, player, id, style, shuffle)
    M.onShip(nil, player, id, function(_, p) Core.send(p, "refitCabin", { style = style, shuffle = shuffle }) end)
end

Net.onClient("cabinRefit", function(args)
    U.note(Core.lastAsker or U.player(0),
           getText(args.now and "IGUI_TREK_CabinRebuilt" or "IGUI_TREK_CabinRebuiltLater"), 150, 220, 255)
end)

-- What each style of cabin is called, written out whole (TREK_Interiors).
M.CabinText = { starfleet = "IGUI_TREK_CabinStyle_starfleet", klingon = "IGUI_TREK_CabinStyle_klingon",
                vulcan = "IGUI_TREK_CabinStyle_vulcan" }

--- Her cabin, for somebody with the say (SERVERS.md): every style, standard
--- or shuffled again.
local function cabinMenu(menu, player, worldobjects, ship)
    if not V.mayPaint(player) then return end
    local top = menu:addOption(getText("IGUI_TREK_Cabin"), worldobjects, nil)
    local styles = ISContextMenu:getNew(menu)
    menu:addSubMenu(top, styles)
    for _, style in ipairs(TREK.Interiors.Styles) do
        local row = styles:addOption(getText(M.CabinText[style.id]), worldobjects, nil)
        local how = ISContextMenu:getNew(styles)
        styles:addSubMenu(row, how)
        how:addOption(getText("IGUI_TREK_CabinStandard"), worldobjects, M.onCabin, player, ship, style.id, false)
        how:addOption(getText("IGUI_TREK_CabinShuffled"), worldobjects, M.onCabin, player, ship, style.id, true)
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
    -- The U.S.S. Adirondack, by the shuttle's own transporter.
    local toAdk = menu:addOption(getText("IGUI_TREK_BeamToAdirondack"), worldobjects,
                                 TREK.AdirondackClient.onBeamTo, player)
    -- Until the clearance is earned (ACCESS.md), greyed with the reason.
    local why = TREK.Access and TREK.Access.refusal(player)
    if why then
        toAdk.notAvailable = true
        toAdk.toolTip = ISWorldObjectContextMenu.addToolTip()
        toAdk.toolTip.description = TREK.AccessUI and TREK.AccessUI.tip(why) or why
    end
    menu:addOption(getText("IGUI_TREK_BookmarkHere"), worldobjects,
                   M.onBookmarkHere, player)
    menu:addOption(getText("IGUI_TREK_Sensors"), worldobjects, M.onSensors,
                   player)
    crewMenu(menu, player, worldobjects)
    cabinMenu(menu, player, worldobjects, U.shipNow)
    return true
end

function M.onPaint(_, player, id, skin, hull)
    M.onShip(nil, player, id, function(_, p) Core.send(p, "paintHull", { skin = skin, hull = hull }) end)
end

Net.onClient("hullPainted", function(args)
    U.note(Core.lastAsker or U.player(0),
           getText(args.now and "IGUI_TREK_Painted" or "IGUI_TREK_PaintedLater"), 150, 220, 255)
end)

--- Her hull, for somebody with the say (SERVERS.md): every kind of ship in
--- every livery and state, and the skin she has earned as the kind she is.
local function paintMenu(menu, player, worldobjects, ship)
    if not V.mayPaint(player) then return end
    local top = menu:addOption(getText("IGUI_TREK_Paint"), worldobjects, nil)
    local kinds = ISContextMenu:getNew(menu)
    menu:addSubMenu(top, kinds)
    kinds:addOption(getText("IGUI_TREK_PaintEarned"), worldobjects, M.onPaint, player, ship, nil, nil)
    for _, hull in ipairs(C.Hulls) do
        local kind = kinds:addOption(getText(hull.name), worldobjects, nil)
        local paints = ISContextMenu:getNew(kinds)
        kinds:addSubMenu(kind, paints)
        for i, livery in ipairs(hull.liveries) do
            local row = paints:addOption(getText(V.LiveryText[livery]), worldobjects, nil)
            local states = ISContextMenu:getNew(paints)
            paints:addSubMenu(row, states)
            for j, state in ipairs(C.HullStates) do
                states:addOption(getText(V.StateText[state]), worldobjects, M.onPaint, player, ship,
                                 (i - 1) * #C.HullStates + j - 1, hull.id)
            end
        end
    end
end

local function groundMenu(context, player, worldobjects, sq, test)
    -- Sandbox *Shuttles*, off: there is no shuttle to ask, on the ground or
    -- at a hull left standing from before (SERVERS.md, *Content*).
    if not TREK.Rules.shuttles() then return false end
    -- Whose hull, if it is one: with more than one shuttle about, the one
    -- under the cursor is the one being asked, not the one last hailed.
    local there = M.hullShipAt(sq:getX(), sq:getY(), sq:getZ())
    local onHull = there ~= nil
    local ship = there or U.shipNow

    -- Somewhere a person could stand is somewhere worth *offering* to land,
    -- even when the footprint will not fit. The refusal is the point.
    local standable = U.try("standable", function()
        return sq:getFloor() ~= nil and not sq:isSolid()
    end) == true

    if not onHull and not standable then return false end
    -- Marooned, and never yet aboard her (MAROONED.md): no combadge, so
    -- nothing to call her with. Her hull still has its door.
    local linked = U.usingShip(ship, TREK.Marooned.linked, player)
    if not linked and not onHull then return false end
    if test then return ISWorldObjectContextMenu.setTest() end

    -- Named, where there is more than one to mean.
    local title = getText("IGUI_TREK_Name")
    if isClient() and #Ship.ids() > 1 then
        title = title .. " (" .. M.shipLabel(ship, player) .. ")"
    end
    local sub = context:addOption(title, worldobjects, nil)
    local menu = ISContextMenu:getNew(context)
    context:addSubMenu(sub, menu)

    if onHull then
        -- Every option on a hull is asked of *that* shuttle (M.onShip).
        menu:addOption(getText("IGUI_TREK_Enter"), worldobjects, M.onShip, player, there, M.onEnter)
        if not linked then return true end
        menu:addOption(getText("IGUI_TREK_Recall"), worldobjects, M.onShip, player, there, M.onRecall)
    else
        menu:addOption(getText("IGUI_TREK_CallDown"), worldobjects, M.onCallDown,
                       player, sq:getX(), sq:getY(), sq:getZ())
    end
    -- Not offered at all on a server that has switched it off: there is
    -- nothing to learn from a refusal that will never change (SERVERS.md).
    if TREK.Rules.beamUp() then
        menu:addOption(getText("IGUI_TREK_BeamUp"), worldobjects, M.onShip, player, ship, M.onBeamUp)
    end
    if not onHull then hailMenu(menu, player, worldobjects) end
    paintMenu(menu, player, worldobjects, ship)
    cabinMenu(menu, player, worldobjects, ship)
    return true
end

local function onPreFill(playerIndex, context, worldobjects, test)
    local player = U.player(playerIndex)
    if not player then return end

    -- A development tool, on every right-click in a development session and
    -- in no other: its own entry, because a marooned player who has never
    -- been aboard has no Shuttlecraft menu to put it in.
    if U.devMode() then
        if test then return ISWorldObjectContextMenu.setTest() end
        context:addOption(getText("IGUI_TREK_DevToShuttle"), worldobjects,
                          M.onDevToShuttle, player)
        context:addOption(getText("IGUI_TREK_DevMap"), worldobjects, M.onDevMap, player)
    end

    if U.isInteriorPlayer(player) then
        return aboardMenu(context, player, worldobjects, test)
    end
    -- Aboard the Adirondack her own menu replaces the ground one: there is
    -- no calling the shuttle down onto a deck in the void.
    if TREK.Adirondack.onShip(player) then
        return TREK.AdirondackClient.menu(context, player, worldobjects, test)
    end

    local sq = clickedSquare(playerIndex, context, player)
    if not sq then return end
    return groundMenu(context, player, worldobjects, sq, test)
end

Events.OnPreFillWorldObjectContextMenu.Add(onPreFill)

return M
