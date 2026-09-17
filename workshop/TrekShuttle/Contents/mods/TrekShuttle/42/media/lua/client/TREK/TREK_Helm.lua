--[[ Shuttlecraft -- the helm console.

    An LCARS panel: flat colour, rounded ends, a sidebar that turns into the
    top and bottom bars through curved elbows. It is drawn rather than baked
    into one image, so it stays crisp at any size and its buttons can show
    hover and pressed states. The shapes come from three white textures
    tinted at draw time (tools/gen_helm_ui.py); the backdrop and the emblem
    are generated artwork, vetted through the FlowDot Gemini Image toolkit.

    Every texture is optional. A missing one degrades to flat rectangles, not
    to an error, so the console works before the art is installed.

    Controls, top to bottom:

        shields        up or down, saved with the world -- the field in
                       Core.repelZombies is the shields
        flight speed   a multiplier on C.FlightSpeed, 1/4x to 5x
        navigation     the course, logged positions and "take her down",
                       unchanged in behaviour from the old helm window

    TREK_Travel.openHelm opens it beside the world map. Map clicks still set
    the course through TREK.Travel and call refresh() here.

    Controllers and the Steam Deck. The panel is an ISPanelJoypad, so the
    stick walks its buttons and A presses one. A mouse click on the map is the
    one thing a controller cannot do, so the map carries a crosshair at its
    centre and a course can be laid in on that instead:

        A           press the focused button
        B           close the helm
        Y           hand the stick to the map: pan with the stick, zoom with
                    the triggers, A lays in a course on the crosshair, B or Y
                    comes back to the helm
        LB / RB     step through the logged positions
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local H = {}
TREK.Helm = H

---------------------------------------------------------------------------
-- Look
---------------------------------------------------------------------------
-- The TNG LCARS palette.
H.P = {
    orange = { 1.00, 0.60, 0.40 },
    peach  = { 1.00, 0.80, 0.60 },
    gold   = { 1.00, 0.80, 0.40 },
    lilac  = { 0.80, 0.60, 0.80 },
    violet = { 0.60, 0.60, 1.00 },
    blue   = { 0.60, 0.80, 1.00 },
    red    = { 0.80, 0.40, 0.40 },
    dim    = { 0.42, 0.38, 0.52 },
    text   = { 0.78, 0.86, 1.00 },
    white  = { 1.00, 1.00, 1.00 },
}
local P = H.P

H.W, H.H = 440, 640          -- panel size
-- The course prompt. Sized for its text plus the "course laid in" line: the
-- panel clips, so a line that does not fit is not wrapped, it is hidden.
H.InfoH = 84
local SIDE  = 64             -- sidebar width
local TOPH  = 26             -- top bar height
local BOTH  = 16             -- bottom bar height
local R     = 26             -- outer elbow radius
local NOTCH = 14             -- inner elbow radius
local GAP   = 4              -- the black seam between LCARS blocks
local PAD   = 14

local textures = nil

--- Loads the console's textures once. Any that are missing stay nil and the
--- drawing code falls back to plain rectangles.
local function tex()
    if textures then return textures end
    textures = {}
    local function load(key, file)
        textures[key] = U.try("helmTexture:" .. file, function()
            return getTexture("media/ui/" .. file)
        end)
        if not textures[key] then
            U.warnOnce("helmTexture:" .. file, "helm texture missing: " .. file)
        end
    end
    load("dot", "TREK_LcarsDot.png")
    load("notchTop", "TREK_LcarsNotchTop.png")
    load("notchBottom", "TREK_LcarsNotchBottom.png")
    load("backdrop", "TREK_HelmBackdrop.png")
    load("emblem", "TREK_HelmEmblem.png")
    return textures
end

local function shade(c, k)
    return math.min(1, c[1] * k), math.min(1, c[2] * k), math.min(1, c[3] * k)
end

--- A bar with optionally rounded ends. Always opaque: the end discs overlap
--- the middle rectangle, and a translucent pill would show the seam.
function H.pill(el, x, y, w, h, c, roundLeft, roundRight, k)
    local r, g, b = shade(c, k or 1)
    local dot = tex().dot
    if not dot then
        el:drawRect(x, y, w, h, 1, r, g, b)
        return
    end
    if roundLeft then el:drawTextureScaled(dot, x, y, h, h, 1, r, g, b) end
    if roundRight then el:drawTextureScaled(dot, x + w - h, y, h, h, 1, r, g, b) end
    local x0 = roundLeft and x + h / 2 or x
    local x1 = roundRight and x + w - h / 2 or x + w
    if x1 > x0 then el:drawRect(x0, y, x1 - x0, h, 1, r, g, b) end
end

local function fontHeight(font)
    return getTextManager():MeasureStringY(font, "HELM") or 14
end

---------------------------------------------------------------------------
-- The LCARS button
---------------------------------------------------------------------------
TREKLcarsButton = ISButton:derive("TREKLcarsButton")

function TREKLcarsButton:new(x, y, w, h, title, target, onclick, colour)
    local o = ISButton.new(self, x, y, w, h, title, target, onclick)
    o.colour = colour or P.orange
    o.centreText = false
    o.roundLeft, o.roundRight = true, true
    return o
end

function TREKLcarsButton:prerender()
    local k = 1
    if not self.enable then k = 0.40
    elseif self.pressed then k = 0.70
    elseif (self.mouseOver and self:isMouseOver()) or self.joypadFocused then k = 1.18 end
    if self.joypadFocused then
        -- A controller has no pointer, so focus has to be unmistakable: a
        -- white rim, drawn as a white pill with the button inset inside it.
        H.pill(self, 0, 0, self.width, self.height, P.white,
               self.roundLeft, self.roundRight)
        H.pill(self, 2, 2, self.width - 4, self.height - 4, self.colour,
               self.roundLeft, self.roundRight, k)
        return
    end
    H.pill(self, 0, 0, self.width, self.height, self.colour,
           self.roundLeft, self.roundRight, k)
end

function TREKLcarsButton:render()
    local text = string.upper(self.title or "")
    if text == "" then return end
    local font = self.height >= 30 and UIFont.Medium or UIFont.Small
    local ty = (self.height - fontHeight(font)) / 2
    if self.centreText then
        self:drawTextCentre(text, self.width / 2, ty, 0, 0, 0, 1, font)
    else
        -- LCARS labels sit at the right-hand end of their bar.
        self:drawTextRight(text, self.width - self.height / 2 - 6, ty, 0, 0, 0, 1, font)
    end
end

---------------------------------------------------------------------------
-- The panel
---------------------------------------------------------------------------
TREKHelmWindow = ISPanelJoypad:derive("TREKHelmWindow")

--- The multiplier as it reads on a chip: 1/4, 1/2, 1, 2 ...
function H.speedLabel(m)
    if m == 0.25 then return "1/4" end
    if m == 0.5 then return "1/2" end
    if m == math.floor(m) then return tostring(math.floor(m)) end
    return tostring(m)
end

function TREKHelmWindow:new(x, y, player)
    local o = ISPanelJoypad.new(self, x, y, H.W, H.H)
    o.player = player
    o.playerNum = U.try("helmPlayerNum", function() return player:getPlayerNum() end) or 0
    o.background = false
    o.moveWithMouse = true
    return o
end

function TREKHelmWindow:createChildren()
    ISPanelJoypad.createChildren(self)
    local cx = SIDE + PAD
    local cw = self.width - cx - PAD
    local y = TOPH + PAD

    -- Close sits in the right-hand end of the top bar.
    self.closeBtn = TREKLcarsButton:new(self.width - 96, 0, 96, TOPH,
        getText("IGUI_TREK_Close"), self, TREKHelmWindow.close, P.violet)
    self.closeBtn.roundLeft = false
    self.closeBtn:initialise()
    self:addChild(self.closeBtn)

    -- Shields. Leave room on the right for the emblem.
    self.shieldsHeaderY = y
    y = y + 20
    self.shieldsBtn = TREKLcarsButton:new(cx, y, cw - 60, 34, "", self,
        TREKHelmWindow.onShields, P.blue)
    self.shieldsBtn:initialise()
    self:addChild(self.shieldsBtn)
    y = y + 34 + 6
    self.shieldsStatusY = y
    y = y + 18 + 14

    -- Flight speed: one chip per step.
    self.speedHeaderY = y
    y = y + 20
    self.speedChips = {}
    local steps = C.FlightSpeedSteps
    local chipGap = 6
    local chipW = (cw - chipGap * (#steps - 1)) / #steps
    for i, m in ipairs(steps) do
        local chip = TREKLcarsButton:new(cx + (i - 1) * (chipW + chipGap), y,
            chipW, 26, H.speedLabel(m) .. "x", self, TREKHelmWindow.onSpeed, P.dim)
        chip.step = i
        chip.centreText = true
        chip:initialise()
        self:addChild(chip)
        self.speedChips[i] = chip
    end
    y = y + 26 + 6
    self.speedStatusY = y
    y = y + 18 + 14

    -- Navigation.
    self.navHeaderY = y
    y = y + 20
    self.info = ISRichTextPanel:new(cx, y, cw, H.InfoH)
    self.info:initialise()
    self.info.background = false
    self.info.autosetheight = false
    self.info.clip = true
    self.info.marginLeft = 0
    self.info.marginRight = 0
    self.info.marginTop = 0
    self:addChild(self.info)
    y = y + H.InfoH + 8

    local btnH, rowGap = 26, 6
    local row2 = self.height - BOTH - PAD - btnH
    local row1 = row2 - rowGap - btnH
    local row0 = row1 - rowGap - btnH
    local half = (cw - rowGap) / 2

    self.list = ISScrollingListBox:new(cx, y, cw, row0 - PAD - y)
    self.list:initialise()
    self.list:instantiate()
    self.list.font = UIFont.Small
    self.list.itemheight = 22
    self.list.selected = 0
    self.list.joypadParent = self
    self.list.drawBorder = true
    self.list.backgroundColor = { r = 0.01, g = 0.02, b = 0.05, a = 0.80 }
    self.list.borderColor = { r = P.lilac[1], g = P.lilac[2], b = P.lilac[3], a = 0.55 }
    self.list.doDrawItem = TREKHelmWindow.drawBookmark
    self.list.target = self
    self:addChild(self.list)

    local function button(x, yy, key, fn, colour)
        local b = TREKLcarsButton:new(x, yy, half, btnH, getText(key), self, fn, colour)
        b:initialise()
        self:addChild(b)
        return b
    end
    self.landBtn     = button(cx, row1, "IGUI_TREK_TakeHerDown", TREKHelmWindow.onLand, P.orange)
    self.bookmarkBtn = button(cx + half + rowGap, row1, "IGUI_TREK_SaveBookmark", TREKHelmWindow.onBookmark, P.peach)
    self.gotoBtn     = button(cx, row2, "IGUI_TREK_UseBookmark", TREKHelmWindow.onUseBookmark, P.lilac)
    self.deleteBtn   = button(cx + half + rowGap, row2, "IGUI_TREK_DeleteBookmark", TREKHelmWindow.onDeleteBookmark, P.red)

    -- Lays in a course on the map's crosshair: the controller's answer to
    -- clicking the map, and just as usable with a mouse.
    self.crosshairBtn = TREKLcarsButton:new(cx, row0, cw, btnH,
        getText("IGUI_TREK_CourseToCrosshair"), self, TREKHelmWindow.onCourseToCrosshair, P.violet)
    self.crosshairBtn:initialise()
    self:addChild(self.crosshairBtn)

    -- Controller navigation, top to bottom. Close is on B rather than in the
    -- grid, the way vanilla panels do it.
    self:insertNewLineOfButtons(self.shieldsBtn)
    self:insertNewListOfButtons(self.speedChips)
    self:insertNewLineOfButtons(self.crosshairBtn)
    self:insertNewLineOfButtons(self.landBtn, self.bookmarkBtn)
    self:insertNewLineOfButtons(self.gotoBtn, self.deleteBtn)
    self:setISButtonForB(self.closeBtn)

    self:refresh()
end

--- The frame: sidebar, elbows, bars and title. Drawn under the children.
function TREKHelmWindow:prerender()
    local t = tex()
    local w, h = self.width, self.height

    self:drawRect(0, 0, w, h, 0.97, 0.008, 0.012, 0.028)
    if t.backdrop then
        self:drawTextureScaled(t.backdrop, SIDE, TOPH, w - SIDE, h - TOPH - BOTH, 1)
    end

    local function block(x, y, bw, bh, c)
        self:drawRect(x, y, bw, bh, 1, c[1], c[2], c[3])
    end
    local function disc(x, y, d, c)
        if t.dot then
            self:drawTextureScaled(t.dot, x, y, d, d, 1, c[1], c[2], c[3])
        else
            block(x, y, d, d, c)
        end
    end

    -- Top elbow, orange: rounded outer corner, sidebar block, top bar.
    local topBlock = 110
    disc(0, 0, R * 2, P.orange)
    block(R, 0, SIDE - R, R, P.orange)
    block(0, R, SIDE, topBlock - R, P.orange)
    if t.notchTop then
        self:drawTextureScaled(t.notchTop, SIDE, TOPH, NOTCH, NOTCH, 1,
                               P.orange[1], P.orange[2], P.orange[3])
    end

    -- Title in a gap in the top bar.
    local title = string.upper(getText("IGUI_TREK_HelmTitle"))
    local tw = getTextManager():MeasureStringX(UIFont.Medium, title)
    local closeX = self.closeBtn and self.closeBtn.x or (w - 96)
    local titleRight = closeX - GAP - 30
    local titleX = titleRight - tw
    block(SIDE, 0, math.max(0, titleX - GAP * 2 - SIDE), TOPH, P.orange)
    self:drawText(title, titleX, (TOPH - fontHeight(UIFont.Medium)) / 2,
                  P.orange[1], P.orange[2], P.orange[3], 1, UIFont.Medium)
    block(titleRight + GAP * 2, 0, closeX - GAP - (titleRight + GAP * 2), TOPH, P.gold)

    -- Bottom elbow, lilac.
    local bottomBlock = 120
    local by = h - bottomBlock
    block(0, by, SIDE, bottomBlock - R, P.lilac)
    block(R, h - R, SIDE - R, R, P.lilac)
    disc(0, h - R * 2, R * 2, P.lilac)
    block(SIDE, h - BOTH, w - SIDE - BOTH / 2, BOTH, P.lilac)
    disc(w - BOTH, h - BOTH, BOTH, P.lilac)
    if t.notchBottom then
        self:drawTextureScaled(t.notchBottom, SIDE, h - BOTH - NOTCH, NOTCH, NOTCH, 1,
                               P.lilac[1], P.lilac[2], P.lilac[3])
    end

    -- Sidebar blocks between the elbows, each with its register number.
    local y1 = topBlock + GAP
    local b1h = 70
    local y2 = y1 + b1h + GAP
    local y3 = by - GAP
    block(0, y1, SIDE, b1h, P.peach)
    block(0, y2, SIDE, y3 - y2, P.violet)
    local fh = fontHeight(UIFont.Small)
    self:drawTextRight("07", SIDE - 6, topBlock - fh - 4, 0, 0, 0, 1, UIFont.Small)
    self:drawTextRight("22-5", SIDE - 6, y1 + b1h - fh - 4, 0, 0, 0, 1, UIFont.Small)
    self:drawTextRight("1701", SIDE - 6, y3 - fh - 4, 0, 0, 0, 1, UIFont.Small)
    self:drawTextRight("47", SIDE - 6, h - R - fh, 0, 0, 0, 1, UIFont.Small)
end

--- A section heading: a short bar and a label, LCARS style.
function TREKHelmWindow:heading(y, key, c)
    local cx = SIDE + PAD
    H.pill(self, cx, y + 3, 30, 10, c, true, false)
    self:drawText(string.upper(getText(key)), cx + 38, y,
                  c[1], c[2], c[3], 1, UIFont.Small)
end

--- Everything that follows the saved state: labels, colours, status lines.
--- Read every frame, so a change made anywhere -- the console, the debug
--- console, another save -- shows at once.
function TREKHelmWindow:render()
    ISPanelJoypad.render(self)
    local t = tex()
    local cx = SIDE + PAD
    local up = U.shieldsUp()

    if t.emblem then
        self:drawTextureScaled(t.emblem, self.width - PAD - 52,
                               self.shieldsHeaderY + 6, 52, 52, 1)
    end

    self:heading(self.shieldsHeaderY, "IGUI_TREK_ShieldsHeader", P.orange)
    self.shieldsBtn.title = getText(up and "IGUI_TREK_ShieldsUp" or "IGUI_TREK_ShieldsDown")
    self.shieldsBtn.colour = up and P.blue or P.red
    local statusC = up and P.blue or P.red
    local status = up and getText("IGUI_TREK_ShieldsStatusUp", tostring(C.FieldRadius))
                       or getText("IGUI_TREK_ShieldsStatusDown")
    self:drawText(status, cx, self.shieldsStatusY,
                  statusC[1], statusC[2], statusC[3], 0.95, UIFont.Small)

    self:heading(self.speedHeaderY, "IGUI_TREK_SpeedHeader", P.gold)
    local step = U.state().speedStep
    for i, chip in ipairs(self.speedChips) do
        chip.colour = (i == step) and P.gold or P.dim
    end
    self:drawText(getText("IGUI_TREK_SpeedStatus",
                          H.speedLabel(U.flightMultiplier()),
                          string.format("%.2f", U.flightSpeed())),
                  cx, self.speedStatusY, P.text[1], P.text[2], P.text[3], 0.95, UIFont.Small)

    self:heading(self.navHeaderY, "IGUI_TREK_NavHeader", P.lilac)

    -- Button prompts in the bottom bar, only while a controller drives it.
    if self.joyfocus then
        self:drawTextRight(string.upper(getText("IGUI_TREK_HelmJoypadHint")),
                           self.width - BOTH - 6, self.height - BOTH + 1,
                           0, 0, 0, 1, UIFont.Small)
    end

    if #self.list.items == 0 then
        self:drawTextCentre(getText("IGUI_TREK_NoBookmarks"),
                            self.list.x + self.list.width / 2,
                            self.list.y + self.list.height / 2 - 8,
                            P.dim[1] * 1.4, P.dim[2] * 1.4, P.dim[3] * 1.4, 1, UIFont.Small)
    end
end

function TREKHelmWindow:drawBookmark(y, item, alt)
    if self.selected == item.itemindex then
        self:drawRect(0, y, self:getWidth(), item.height - 1, 0.35,
                      P.lilac[1], P.lilac[2], P.lilac[3])
    end
    local b = item.item
    self:drawText(b.name, 10, y + 3, P.peach[1], P.peach[2], P.peach[3], 1, UIFont.Small)
    self:drawTextRight(string.format("%d, %d", b.x, b.y), self:getWidth() - 10, y + 3,
                       P.blue[1], P.blue[2], P.blue[3], 0.9, UIFont.Small)
    return y + item.height
end

function TREKHelmWindow:setInfo(text)
    local c = P.text
    self.info:setText(string.format("<RGB:%.2f,%.2f,%.2f> ", c[1], c[2], c[3]) .. text)
    self.info.textDirty = true
    self.info:paginate()
end

function TREKHelmWindow:refresh()
    local s = U.state()
    self.list:clear()
    for _, b in ipairs(s.bookmarks) do
        self.list:addItem(b.name, b)
    end

    local text = getText("IGUI_TREK_HelmPrompt", TREK.Core.footprintArea())
    if s.destination then
        text = text .. " <LINE> <RGB:1.0,0.8,0.4> " ..
               getText("IGUI_TREK_CourseSet", s.destination.x, s.destination.y)
    end
    self:setInfo(text)
end

---------------------------------------------------------------------------
-- Controls
---------------------------------------------------------------------------
function TREKHelmWindow:onShields()
    local up = U.setShields(not U.shieldsUp())
    U.note(self.player, getText(up and "IGUI_TREK_ShieldsUp" or "IGUI_TREK_ShieldsDown"),
           up and 150 or 230, up and 200 or 110, up and 255 or 110)
end

function TREKHelmWindow:onCourseToCrosshair()
    local map = ISWorldMap_instance
    if not (map and map.mapAPI) then return end
    local wx = U.try("mapCentreX", function() return map.mapAPI:getCenterWorldX() end)
    local wy = U.try("mapCentreY", function() return map.mapAPI:getCenterWorldY() end)
    if wx and wy then TREK.Travel.onMapPick(math.floor(wx), math.floor(wy)) end
end

--- Steps the logged-position selection, wrapping at both ends.
function TREKHelmWindow:stepBookmark(dir)
    local n = #self.list.items
    if n == 0 then return end
    local i = (self.list.selected or 0) + dir
    if i < 1 then i = n elseif i > n then i = 1 end
    self.list.selected = i
    U.try("bookmarkScroll", function() self.list:ensureVisible(i) end)
end

function TREKHelmWindow:onJoypadDown(button, joypadData)
    if button == Joypad.LBumper then
        self:stepBookmark(-1)
    elseif button == Joypad.RBumper then
        self:stepBookmark(1)
    elseif button == Joypad.YButton then
        -- Hand the stick to the map; TREK_Travel sends it back on A, B or Y.
        if ISWorldMap_instance then
            setJoypadFocus(joypadData.player, ISWorldMap_instance)
        end
    else
        ISPanelJoypad.onJoypadDown(self, button, joypadData)
    end
end

function TREKHelmWindow:onGainJoypadFocus(joypadData)
    ISPanelJoypad.onGainJoypadFocus(self, joypadData)
    if self:getJoypadFocus() then
        self:restoreJoypadFocus(joypadData)
    else
        self:setJoypadFocusTopLeft(joypadData)
    end
end

function TREKHelmWindow:onLoseJoypadFocus(joypadData)
    ISPanelJoypad.onLoseJoypadFocus(self, joypadData)
    self:clearJoypadFocus(joypadData)
end

function TREKHelmWindow:onSpeed(button)
    if button and button.step then U.setFlightStep(button.step) end
end

--- "Take her down": beams the player to the course and brings the ship in.
function TREKHelmWindow:onLand()
    local s = U.state()
    if not s.destination then
        self:setInfo(getText("IGUI_TREK_NoCourse"))
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
                TREK.Travel.addBookmark(button.parent.entry:getText(), bx, by, bz)
                if TREK.Travel.window then TREK.Travel.window:refresh() end
            end
        end, nil, x, y, z)
    modal:initialise()
    modal:addToUIManager()
end

function TREKHelmWindow:onUseBookmark()
    local item = self.list.items[self.list.selected]
    if not item then return end
    local b = item.item
    TREK.Travel.setDestination(b.x, b.y, b.z)
    self:refresh()
end

function TREKHelmWindow:onDeleteBookmark()
    if TREK.Travel.removeBookmark(self.list.selected) then self:refresh() end
end

function TREKHelmWindow:close()
    local T = TREK.Travel
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
    -- A controller that was driving the helm goes back to the map, or to the
    -- game if the map has gone too. Left pointing at a removed panel, the
    -- controller would do nothing at all until the helm was reopened.
    if self.joyfocus then
        local target = (ISWorldMap_instance and ISWorldMap_instance:isVisible())
                       and ISWorldMap_instance or nil
        U.try("helmReleaseFocus", function() setJoypadFocus(self.playerNum, target) end)
    end
    self:setVisible(false)
    self:removeFromUIManager()
end

---------------------------------------------------------------------------
-- Debug console
---------------------------------------------------------------------------
--- TREK_Shields() reports; TREK_Shields(true) / TREK_Shields(false) sets.
function TREK_Shields(up)
    if up ~= nil then U.setShields(up) end
    U.log("shields are %s", U.shieldsUp() and "up" or "down")
    return U.shieldsUp()
end

--- TREK_Speed() reports; TREK_Speed(n) selects step n of C.FlightSpeedSteps.
function TREK_Speed(step)
    if step ~= nil then U.setFlightStep(step) end
    U.log("flight speed step %d: x%s, %.2f squares a tick",
          U.state().speedStep, tostring(U.flightMultiplier()), U.flightSpeed())
    return U.flightSpeed()
end

return H
