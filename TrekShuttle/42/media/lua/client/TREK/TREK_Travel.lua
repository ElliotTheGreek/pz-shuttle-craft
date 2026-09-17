--[[ Shuttlecraft -- the helm: courses, bookmarks and setting down.

    A course is chosen from the helm on the world map, or from the list of
    saved bookmarks. Setting a course does not move anything: it is written
    down, and the ship goes when you tell it to.

    Landing is where this differs sharply from a police box. The shuttle needs
    its whole footprint clear, and that cannot be judged from the helm --
    somewhere far away is in a chunk the game has not streamed in, so there is
    nothing to inspect until a player is standing there.

    So landing is a two-stage job on purpose:

      1. Set a course. The ship goes to station-keeping; nobody has moved.
      2. Take her down. The player is beamed to the site so its chunks load,
         and the ship comes in after them once there is demonstrably room.

    If there is not enough room the player is beamed straight back aboard with
    the reason. That is the whole point of doing it in this order: a failed
    landing must never strand anybody on foot a hundred miles from the ship.

    In multiplayer the client searches, because the ground is loaded around
    its player, and the server decides: it looks again at the site the client
    found, against its own copy of the world, and places the hull or refuses.
    Course and bookmarks are ship state and change only by asking the server.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_World"
require "TREK/TREK_Core"
require "TREK/TREK_Transport"
require "TREK/TREK_Helm"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Ship = TREK.Ship
local W = TREK.World
local Core = TREK.Core

local T = {}
TREK.Travel = T

T.picking = false

---------------------------------------------------------------------------
-- Bookmarks and courses: requests to the server
---------------------------------------------------------------------------
function T.bookmarks()
    return Ship.get().bookmarks
end

--- Logs a position. With no position, the course if one is laid in, or else
--- where the ship stands.
function T.addBookmark(player, name, x, y, z)
    local s = Ship.get()
    if #s.bookmarks >= C.MaxBookmarks then
        return false, getText("IGUI_TREK_BookmarksFull")
    end
    if not x then
        if s.destination then
            x, y, z = s.destination.x, s.destination.y, s.destination.z
        elseif s.landed then
            x, y, z = s.x, s.y, s.z
        else
            return false, getText("IGUI_TREK_NowhereToBookmark")
        end
    end
    Core.send(player, "addBookmark", { name = name or "", x = x, y = y, z = z or 0 })
    return true
end

function T.removeBookmark(player, index)
    if not Ship.get().bookmarks[index] then return false end
    Core.send(player, "removeBookmark", { index = index })
    return true
end

function T.setDestination(player, x, y, z)
    Core.send(player, "setCourse",
              { x = math.floor(x), y = math.floor(y), z = math.floor(z or 0) })
    return true
end

function T.clearDestination(player)
    Core.send(player, "clearCourse", {})
end

---------------------------------------------------------------------------
-- Setting down
---------------------------------------------------------------------------
--- The nearest square to a target the whole hull will fit on, or nil. The
--- one-shot form, for the debug console; the landing job spreads the same
--- work over many ticks.
function T.findLandingSite(cx, cy, z, player)
    local job = { x = cx, y = cy, z = z, cursor = 0, player = player }
    while true do
        local sq, why, exhausted = W.searchSlice(job)
        if sq then return sq, nil end
        if exhausted then return nil, why end
    end
end

--- Takes the ship down at a destination.
---
--- The player goes first, which is not a convenience but the only way this
--- can work: chunks stream around a player and nothing else, so until they
--- are standing there the ground cannot be inspected at all -- by this client
--- or by the server.
function T.descend(player, dest)
    if not player or not dest then return false end
    if T.pending or Core.moveWaiting() then return false end
    local spot = { x = dest.x, y = dest.y, z = dest.z or 0 }

    return Core.requestMove(player, "descend", function(p)
        if not U.teleport(p, spot.x, spot.y, spot.z) then return end
        Ship.playerData(p).aboard = false
        T.pending = {
            x = spot.x, y = spot.y, z = spot.z,
            tries = 0, cursor = 0, passes = 0, reason = nil, player = p,
            asking = false,
        }
        U.note(p, getText("IGUI_TREK_ComingIn"))
        U.log("taking her down at %d,%d", spot.x, spot.y)
    end)
end

--- Turns a refusal reason into something worth reading.
function T.refusalText(why, blocked)
    if why == "vehicle" then
        return getText("IGUI_TREK_NoRoomVehicle")
    elseif why == "void" then
        return getText("IGUI_TREK_NoRoomVoid")
    end
    return getText("IGUI_TREK_NoRoom", W.footprintArea(), blocked or 0)
end

local function giveUp(job, why, blocked)
    T.pending = nil
    U.log("no room to set down near %d,%d after %d passes (%s)",
          job.x, job.y, job.passes or 0, tostring(why))
    -- Never leave anybody stranded on foot where the ship could not follow.
    TREK.Transport.recoverAboard(job.player, T.refusalText(why, blocked))
end

-- Ticks to wait for the server to answer about a site before looking again.
local ANSWER_TIMEOUT = 300

--- Runs once a tick while a landing is outstanding. The search is sliced:
--- see W.SITES_PER_TICK.
local function serviceLanding()
    local job = T.pending
    if not job then return end
    job.tries = job.tries + 1

    if job.asking then
        if job.tries - job.askedAt > ANSWER_TIMEOUT then job.asking = false end
        return
    end

    if job.tries > C.LandingTimeout then
        local blocked = select(3, W.roomToLand(job.x, job.y, job.z,
                                               W.exemptFor(job.player)))
        giveUp(job, job.reason, blocked)
        return
    end

    local sq = W.searchSlice(job)
    if sq then
        job.asking = true
        job.askedAt = job.tries
        Core.send(job.player, "land", { x = sq:getX(), y = sq:getY(), z = sq:getZ() })
    end
end

Events.OnTick.Add(serviceLanding)

--- The server set the ship down. Step clear of the hull.
Net.onClient("landed", function(args)
    local job = T.pending
    local player = job and job.player or Core.lastAsker or U.player(0)
    T.pending = nil
    if not player then return end
    local beside = W.landingBeside(args.x, args.y, args.z)
    if beside and W.hullCovers(player:getX(), player:getY(), player:getZ()) then
        U.teleport(player, beside.x, beside.y, beside.z)
    end
    if job and beside then
        Ship.setReturnPoint(player, beside.x, beside.y, beside.z)
    end
    U.note(player, getText("IGUI_TREK_Landed"))
end)

--- The server would not set down where this client found room. On a landing
--- job, keep searching until the timeout: the world changed, or the server
--- had not loaded that ground yet. From the call-down menu, say why.
Net.onClient("landingRefused", function(args)
    local job = T.pending
    if job and job.asking then
        job.asking = false
        if args.why ~= "unloaded" and args.why ~= "far" then
            job.reason = job.reason or args.why
        end
        return
    end
    if args.why == "unloaded" or args.why == "far" then return end
    U.note(Core.lastAsker or U.player(0), T.refusalText(args.why, args.blocked),
           255, 90, 90)
end)

Net.onClient("recalled", function()
    U.note(Core.lastAsker or U.player(0), getText("IGUI_TREK_Recalled"))
end)

---------------------------------------------------------------------------
-- Map picking
---------------------------------------------------------------------------
function T.onMapPick(worldX, worldY)
    if not T.picking then return end
    local player = T.window and T.window.player or U.player(0)
    T.setDestination(player, worldX, worldY, 0)
end

-- The helm redraws whenever the ship's state changes, wherever the change
-- came from: this client's own request coming back, or another crewman's.
Ship.onChange(function()
    if T.window then T.window:refresh() end
end)

-- ISWorldMap has no hook for "the player clicked here", so its mouse-up is
-- wrapped once at load. A click that was not a drag is a pick.
local baseOnMouseUp = ISWorldMap.onMouseUp
function ISWorldMap:onMouseUp(x, y)
    local wasDragging = self.dragging
    local wasMoved = self.dragMoved
    local result = baseOnMouseUp(self, x, y)
    if T.picking and wasDragging and not wasMoved and self.mapAPI then
        local wx = self.mapAPI:uiToWorldX(x, y)
        local wy = self.mapAPI:uiToWorldY(x, y)
        if wx and wy then T.onMapPick(math.floor(wx), math.floor(wy)) end
    end
    return result
end

---------------------------------------------------------------------------
-- Markers drawn over the map while the helm is open
---------------------------------------------------------------------------
local function marker(map, wx, wy, r, g, b, label)
    if not map.mapAPI then return end
    local sx = map.mapAPI:worldToUIX(wx, wy)
    local sy = map.mapAPI:worldToUIY(wx, wy)
    if not sx or not sy then return end
    if sx < 0 or sy < 0 or sx > map:getWidth() or sy > map:getHeight() then return end

    for i = 0, 6 do
        local w = 6 - i
        map:drawRect(sx - w, sy - 7 + i, w * 2, 1, 0.95, r, g, b)
        map:drawRect(sx - w, sy + 7 - i, w * 2, 1, 0.95, r, g, b)
    end
    map:drawRectBorder(sx - 7, sy - 7, 15, 15, 0.6, 0, 0, 0)
    if label then
        map:drawTextCentre(label, sx, sy - 26, r, g, b, 1, UIFont.Small)
    end
end

-- The player marker is useless here: the character is standing in the cabin's
-- cell, nowhere near anywhere the map depicts. These markers show what the
-- helm actually needs -- where the ship is, where it has been told to go, and
-- every place that has been bookmarked.
local baseRender = ISWorldMap.render
function ISWorldMap:render()
    baseRender(self)
    if not T.picking then return end

    local s = Ship.get()
    for _, b in ipairs(s.bookmarks) do
        marker(self, b.x, b.y, 0.65, 0.65, 0.7, b.name)
    end
    if s.landed then
        marker(self, s.x, s.y, 0.35, 0.75, 1.0, getText("IGUI_TREK_MapHere"))
    end
    if s.destination then
        marker(self, s.destination.x, s.destination.y, 0.95, 0.55, 0.30,
               getText("IGUI_TREK_MapDestination"))
    end

    -- The crosshair "Course to crosshair" lays a course on. A controller has
    -- no pointer to click the map with, so this is how it picks a site.
    local cx, cy = math.floor(self.width / 2), math.floor(self.height / 2)
    local r, g, b = 0.60, 0.60, 1.00
    self:drawRect(cx - 18, cy, 12, 2, 0.9, r, g, b)
    self:drawRect(cx + 7, cy, 12, 2, 0.9, r, g, b)
    self:drawRect(cx, cy - 18, 2, 12, 0.9, r, g, b)
    self:drawRect(cx, cy + 7, 2, 12, 0.9, r, g, b)
    if self.joyfocus then
        self:drawTextCentre(getText("IGUI_TREK_MapJoypadHint"), cx, cy + 28,
                            r, g, b, 1, UIFont.Small)
    end
end

-- While the helm is open, the map's own controller handling is borrowed:
-- A lays in a course on the crosshair and B or Y hand the stick back to the
-- helm. Vanilla B would close the map out from under the helm instead.
local baseOnJoypadDown = ISWorldMap.onJoypadDown
function ISWorldMap:onJoypadDown(button, joypadData)
    if T.picking and T.window then
        if button == Joypad.AButton then
            T.window:onCourseToCrosshair()
            setJoypadFocus(joypadData.player, T.window)
            return
        elseif button == Joypad.BButton or button == Joypad.YButton then
            setJoypadFocus(joypadData.player, T.window)
            return
        end
    end
    return baseOnJoypadDown(self, button, joypadData)
end

---------------------------------------------------------------------------
-- The helm window
---------------------------------------------------------------------------
-- The console itself -- the LCARS panel, shields and the navigation
-- controls -- lives in TREK_Helm.lua.

--- Opens the world map plus the helm window beside it.
function T.openHelm(player)
    if T.window then T.window:close() end

    local s = Ship.get()
    local rx, ry = Ship.returnPoint(player)
    local cx = s.landed and s.x or (rx or 0)
    local cy = s.landed and s.y or (ry or 0)

    U.try("showWorldMap", function()
        ISWorldMap.ShowWorldMap(player:getPlayerNum(), cx, cy, 60)
    end)

    -- ShowWorldMap only honours a centre when it builds the window for the
    -- first time, and it always centres on the character. From aboard, the
    -- character is in the cabin's cell, which is nowhere the map can show, so
    -- re-centre every time.
    U.try("centreOnShip", function()
        local map = ISWorldMap_instance
        if not map then return end
        map.mapAPI:centerOn(cx, cy)
        map.mapAPI:setZoom(60)

        -- The character marker would sit in the void; the ship marker
        -- replaces it while the helm is open.
        T.restoreShowPlayers = map.showPlayers
        map:setShowPlayers(false)

        -- Lift the fog for the duration. A ship that can go anywhere is not
        -- much use if you can only aim it at places you have already walked
        -- to, and picking somewhere new is the whole point of the helm. The
        -- setting is restored on close, so the ordinary map keeps its fog and
        -- nothing about exploration is given away permanently.
        T.restoreHideUnvisited = map.hideUnvisitedAreas
        map:setHideUnvisitedAreas(false)
    end)

    T.picking = true
    -- Kept on screen at small resolutions: the console is taller than the
    -- old window, and a helm whose buttons are off the bottom edge is no helm.
    local screenH = getCore():getScreenHeight()
    local y = math.max(10, math.min(80, screenH - TREK.Helm.H - 10))
    local win = TREKHelmWindow:new(60, y, player)
    win:initialise()
    win:addToUIManager()
    win:setVisible(true)
    T.window = win

    -- A controller player starts on the helm's buttons. ShowWorldMap has just
    -- given the map focus; without this the stick would pan the map and the
    -- helm could not be reached at all.
    U.try("helmJoypadFocus", function()
        local playerNum = player:getPlayerNum()
        if JoypadState.players[playerNum + 1] then
            setJoypadFocus(playerNum, win)
        end
    end)
    return win
end

return T
