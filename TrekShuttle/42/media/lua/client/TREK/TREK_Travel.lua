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
end

---------------------------------------------------------------------------
-- The helm window
---------------------------------------------------------------------------
TREKHelmWindow = ISCollapsableWindow:derive("TREKHelmWindow")

function TREKHelmWindow:createChildren()
    ISCollapsableWindow.createChildren(self)
    local pad = 10
    local top = self:titleBarHeight() + pad
    local btnH = 25
    local w = self.width - pad * 2

    self.info = ISRichTextPanel:new(pad, top, w, 62)
    self.info:initialise()
    self:addChild(self.info)

    local listY = top + 68
    local listH = self.height - listY - btnH * 3 - pad * 4
    self.list = ISScrollingListBox:new(pad, listY, w, listH)
    self.list:initialise()
    self.list:instantiate()
    self.list.itemheight = 22
    self.list.selected = 0
    self.list.joypadParent = self
    self.list.drawBorder = true
    self.list.doDrawItem = self.drawBookmark
    self.list.target = self
    self:addChild(self.list)

    local y = listY + listH + pad
    self.landBtn = ISButton:new(pad, y, w / 2 - 4, btnH,
        getText("IGUI_TREK_TakeHerDown"), self, TREKHelmWindow.onLand)
    self.landBtn:initialise()
    self:addChild(self.landBtn)

    self.bookmarkBtn = ISButton:new(pad + w / 2 + 4, y, w / 2 - 4, btnH,
        getText("IGUI_TREK_SaveBookmark"), self, TREKHelmWindow.onBookmark)
    self.bookmarkBtn:initialise()
    self:addChild(self.bookmarkBtn)

    y = y + btnH + 4
    self.gotoBtn = ISButton:new(pad, y, w / 2 - 4, btnH,
        getText("IGUI_TREK_UseBookmark"), self, TREKHelmWindow.onUseBookmark)
    self.gotoBtn:initialise()
    self:addChild(self.gotoBtn)

    self.deleteBtn = ISButton:new(pad + w / 2 + 4, y, w / 2 - 4, btnH,
        getText("IGUI_TREK_DeleteBookmark"), self, TREKHelmWindow.onDeleteBookmark)
    self.deleteBtn:initialise()
    self:addChild(self.deleteBtn)

    self:refresh()
end

function TREKHelmWindow:drawBookmark(y, item, alt)
    if self.selected == item.itemindex then
        self:drawRect(0, y, self:getWidth(), item.height - 1, 0.3, 0.35, 0.62, 0.85)
    end
    self:drawRectBorder(0, y, self:getWidth(), item.height - 1, 0.5, 0.4, 0.4, 0.4)
    local b = item.item
    self:drawText(b.name, 8, y + 3, 1, 1, 1, 0.9, UIFont.Small)
    self:drawText(string.format("%d, %d", b.x, b.y),
                  self:getWidth() - 100, y + 3, 0.7, 0.7, 0.7, 0.9, UIFont.Small)
    return y + item.height
end

function TREKHelmWindow:refresh()
    local s = U.state()
    self.list:clear()
    for _, b in ipairs(s.bookmarks) do
        self.list:addItem(b.name, b)
    end

    local text = getText("IGUI_TREK_HelmPrompt", TREK.Core.footprintArea())
    if s.destination then
        text = text .. " <LINE> " ..
               getText("IGUI_TREK_CourseSet", s.destination.x, s.destination.y)
    end
    self.info:setText(text)
    self.info.textDirty = true
    self.info:paginate()
end

--- "Take her down": beams the player to the course and brings the ship in.
function TREKHelmWindow:onLand()
    local s = U.state()
    if not s.destination then
        self.info:setText(getText("IGUI_TREK_NoCourse"))
        self.info.textDirty = true
        self.info:paginate()
        return
    end
    local dest = s.destination
    s.destination = nil
    self:close()
    TREK.Travel.descend(self.player, dest)
end

function TREKHelmWindow:onBookmark()
    local s = U.state()
    local x, y, z
    if s.destination then
        x, y, z = s.destination.x, s.destination.y, s.destination.z
    elseif s.landed then
        x, y, z = s.x, s.y, s.z
    else
        return
    end

    local modal = ISTextBox:new(0, 0, 280, 120,
        getText("IGUI_TREK_NameBookmark"), "", nil,
        function(_, button, bx, by, bz)
            if button.internal == "OK" then
                T.addBookmark(button.parent.entry:getText(), bx, by, bz)
                if T.window then T.window:refresh() end
            end
        end, nil, x, y, z)
    modal:initialise()
    modal:addToUIManager()
end

function TREKHelmWindow:onUseBookmark()
    local item = self.list.items[self.list.selected]
    if not item then return end
    local b = item.item
    T.setDestination(b.x, b.y, b.z)
    self:refresh()
end

function TREKHelmWindow:onDeleteBookmark()
    if T.removeBookmark(self.list.selected) then self:refresh() end
end

function TREKHelmWindow:close()
    T.picking = false
    T.window = nil
    U.try("restoreMapSettings", function()
        local map = ISWorldMap_instance
        if not map then return end
        if T.restoreShowPlayers ~= nil then
            map:setShowPlayers(T.restoreShowPlayers)
        end
        if T.restoreHideUnvisited ~= nil then
            map:setHideUnvisitedAreas(T.restoreHideUnvisited)
        end
    end)
    ISCollapsableWindow.close(self)
end

function TREKHelmWindow:new(x, y, w, h, player)
    local o = ISCollapsableWindow:new(x, y, w, h)
    setmetatable(o, self)
    self.__index = self
    o.player = player
    o.title = getText("IGUI_TREK_Helm")
    o:setResizable(false)
    return o
end

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
    local win = TREKHelmWindow:new(60, 120, 330, 430, player)
    win:initialise()
    win:addToUIManager()
    win:setVisible(true)
    T.window = win
    return win
end

return T
