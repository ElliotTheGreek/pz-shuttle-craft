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
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Helm"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local T = {}
TREK.Travel = T

T.picking = false

---------------------------------------------------------------------------
-- Bookmarks
---------------------------------------------------------------------------
function T.bookmarks()
    return U.state().bookmarks
end

function T.addBookmark(name, x, y, z)
    local s = U.state()
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
    table.insert(s.bookmarks, {
        name = name and name ~= "" and name or string.format("%d, %d", x, y),
        x = x, y = y, z = z or 0,
    })
    U.log("bookmarked %s at %d,%d", tostring(name), x, y)
    return true
end

function T.removeBookmark(index)
    local s = U.state()
    if s.bookmarks[index] then
        table.remove(s.bookmarks, index)
        return true
    end
    return false
end

---------------------------------------------------------------------------
-- Courses
---------------------------------------------------------------------------
function T.setDestination(x, y, z)
    local s = U.state()
    s.destination = { x = math.floor(x), y = math.floor(y), z = math.floor(z or 0) }
    U.log("course set for %d,%d", s.destination.x, s.destination.y)
    return true
end

function T.clearDestination()
    U.state().destination = nil
end

---------------------------------------------------------------------------
-- Setting down
---------------------------------------------------------------------------
-- Candidate landing positions, nearest first. Built once: the ring order does
-- not depend on where you are, only on how far out to look.
local searchOrder = nil

local function candidates()
    if searchOrder then return searchOrder end
    local out = {}
    for r = 0, C.LandingSearchRadius do
        for dx = -r, r do
            for dy = -r, r do
                if math.max(math.abs(dx), math.abs(dy)) == r then
                    table.insert(out, { dx, dy })
                end
            end
        end
    end
    searchOrder = out
    return out
end

-- How many candidate positions to examine per tick.
--
-- This is the number that decides whether landing is a pause or a freeze. The
-- search covers a 49x49 area and each position asks about all fifteen squares
-- of the footprint, so a whole pass is some thirty-six thousand square
-- lookups -- fine spread over a few seconds, and a hard lock if it is done
-- every frame. The search therefore resumes where it left off rather than
-- starting again, and wraps round when it runs out, because ground that was
-- not loaded on the first pass may well be by the third.
local SITES_PER_TICK = 48

--- Examines the next slice of candidates around a target.
---
--- Returns `square, reason, exhausted`: a square when the whole hull fits,
--- and otherwise the best refusal seen so far plus whether a full pass has
--- just been completed.
local function searchSlice(job)
    local order = candidates()
    local exempt = TREK.Core.exemptFor(job.player)
    local checked, exhausted = 0, false

    while checked < SITES_PER_TICK do
        job.cursor = (job.cursor or 0) + 1
        if job.cursor > #order then
            job.cursor = 1
            job.passes = (job.passes or 0) + 1
            exhausted = true
        end
        local d = order[job.cursor]
        local x, y = job.x + d[1], job.y + d[2]

        -- One cheap lookup rejects most candidates before the fifteen-square
        -- footprint test is worth running at all.
        local sq = U.square(x, y, job.z, false)
        if sq and U.try("landProbe", function() return sq:getFloor() ~= nil end) then
            local ok, why = TREK.Core.roomToLand(x, y, job.z, exempt)
            if ok then return sq, nil, exhausted end
            if why and why ~= "unloaded" then job.reason = job.reason or why end
        end
        checked = checked + 1
    end
    return nil, job.reason, exhausted
end

--- The nearest square to a target the whole hull will fit on, or nil.
---
--- The one-shot form, for the self-test and the debug console. The landing job
--- uses searchSlice instead so it can spread the same work over many ticks.
function T.findLandingSite(cx, cy, z, player)
    local job = { x = cx, y = cy, z = z, cursor = 0, player = player }
    local order = candidates()
    for _ = 1, math.ceil(#order / SITES_PER_TICK) do
        local sq, why, exhausted = searchSlice(job)
        if sq then return sq, nil end
        if exhausted then return nil, why end
    end
    return nil, job.reason
end

--- Takes the ship down at a destination.
---
--- The player goes first, which is not a convenience but the only way this
--- can work: chunks stream around a player and nothing else, so until they
--- are standing there the ground cannot be inspected at all. The actual
--- placement is retried on a tick job until the world catches up.
function T.descend(player, dest)
    if not player or not dest then return false end

    local spot = { x = dest.x, y = dest.y, z = dest.z or 0 }
    if not U.teleport(player, spot.x, spot.y, spot.z) then return false end

    local s = U.state()
    s.inside = false

    T.pending = {
        x = spot.x, y = spot.y, z = spot.z,
        tries = 0, cursor = 0, passes = 0, reason = nil, player = player,
    }
    U.note(player, getText("IGUI_TREK_ComingIn"))
    U.log("taking her down at %d,%d", spot.x, spot.y)
    return true
end

--- Turns a refusal reason into something worth reading.
local function refusalText(why, blocked)
    if why == "vehicle" then
        return getText("IGUI_TREK_NoRoomVehicle")
    elseif why == "void" then
        return getText("IGUI_TREK_NoRoomVoid")
    end
    return getText("IGUI_TREK_NoRoom", TREK.Core.footprintArea(), blocked or 0)
end

--- Runs once a tick while a landing is outstanding.
---
--- The work is deliberately sliced: see SITES_PER_TICK above.
local function serviceLanding()
    local job = T.pending
    if not job then return end
    job.tries = job.tries + 1

    local sq, why = searchSlice(job)
    if sq then
        T.pending = nil
        local player = job.player
        local ok, failed = TREK.Core.land(sq, player)
        if not ok then
            -- The site passed the search and then refused the landing, which
            -- means the world changed under us between the two. Treat it the
            -- same as never finding one: nobody gets left on foot.
            TREK.Transport.recoverAboard(player, refusalText(failed, nil))
            return
        end
        -- Core.land already steps the player clear if they were under the
        -- hull; this covers the case where they were merely beside it.
        local beside = TREK.Core.landingBeside(sq:getX(), sq:getY(), sq:getZ())
        if beside and player then
            U.teleport(player, beside.x, beside.y, beside.z)
            local s = U.state()
            s.returnX, s.returnY, s.returnZ = beside.x, beside.y, beside.z
        end
        U.note(player, getText("IGUI_TREK_Landed"))
        return
    end

    -- Give the world time to stream the area in before admitting defeat. A
    -- real obstruction found on an early pass is still not a reason to stop:
    -- more ground arrives as the player stands there, and somewhere in a ring
    -- that was empty a moment ago may now be open.
    if job.tries <= C.LandingTimeout then return end

    T.pending = nil
    local blocked = select(3, TREK.Core.roomToLand(job.x, job.y, job.z,
                                                  TREK.Core.exemptFor(job.player)))
    U.log("no room to set down near %d,%d after %d passes (%s)",
          job.x, job.y, job.passes or 0, tostring(why))
    -- Never leave anybody stranded on foot where the ship could not follow.
    TREK.Transport.recoverAboard(job.player, refusalText(why, blocked))
end

Events.OnTick.Add(serviceLanding)

---------------------------------------------------------------------------
-- Map picking
---------------------------------------------------------------------------
function T.onMapPick(worldX, worldY)
    if not T.picking then return end
    T.setDestination(worldX, worldY, 0)
    if T.window then T.window:refresh() end
end

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

    local s = U.state()
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
-- The console itself -- the LCARS panel, shields, flight speed and the
-- navigation controls -- lives in TREK_Helm.lua.

--- Opens the world map plus the helm window beside it.
function T.openHelm(player)
    if T.window then T.window:close() end

    local s = U.state()
    local cx = s.landed and s.x or (s.returnX or 0)
    local cy = s.landed and s.y or (s.returnY or 0)

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
