--[[ Shuttlecraft -- the replicator, in front of the player.

    The panel, the two ways into it, and what the server says back. Everything
    here is presentation: the client draws the catalogue, and asks. The item
    is made on the server (TREK_Server.lua) and nothing in this file creates,
    places or spends anything.

    **The way in is a right-click on the berth**, and it is registered on
    `OnPreFillWorldObjectContextMenu` rather than the later event the medical
    set uses. That is not a style choice: build 42's menu builder returns
    early from the later event when the clicked square holds nothing it
    considers interactable, and this mod has already been bitten by a menu
    hook that could never run (DEV_GUIDE.md, *A hook on a toggle must ask
    before it calls through*). The Pre- event is the one TREK_Menu.lua relies
    on for the whole aboard menu and is known to fire in the cabin.

    **The controller is designed in, not bolted on.** A pad has no keyboard,
    so the search box cannot be the only way to find anything: the category
    button walks the catalogue's own categories, the bumpers step the list,
    and A materialises. The text box is the mouse-and-keyboard fast path.

    **The list is filtered, never rebuilt.** The catalogue is a few thousand
    rows and it is built once per process (TREK_Replicator.lua); what a
    keystroke touches is an array of precomputed lowercase strings. Asking
    the engine for the item list on a keystroke -- or worse, per frame -- is
    the hard lock DEV_GUIDE.md describes under *Slice any search*.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Replicator"
require "TREK/TREK_Core"
require "TREK/TREK_Helm"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local R = TREK.Replicator
local Core = TREK.Core
local H = TREK.Helm
local P = H.P

local M = {}
TREK.ReplicatorUI = M

local function note(player, key, ...)
    U.note(player, getText(key, ...), 150, 210, 255)
end

local function warnNote(player, key, ...)
    U.note(player, getText(key, ...), 255, 150, 90)
end

---------------------------------------------------------------------------
-- The panel
---------------------------------------------------------------------------
TREKReplicatorWindow = ISPanelJoypad:derive("TREKReplicatorWindow")

local RW, RH = 470, 640
local SIDE, TOPH, BOTH, PAD, RAD = 56, 26, 16, 14, 22
local ROWH = 22

--- Cuts a label down until it fits, keeping the result on the row.
---
--- Item names come from the whole catalogue -- vanilla, this mod and anyone
--- else's -- so their length is not knowable in advance, and a name that runs
--- past its column is the kind of thing only a render or tests/test_helm.py
--- ever shows.
local function ellipsise(text, font, maxW, cache, key)
    if cache and cache[key] then return cache[key] end
    local tm = getTextManager()
    local out = text
    if tm:MeasureStringX(font, out) > maxW then
        while #out > 1 and tm:MeasureStringX(font, out .. "...") > maxW do
            out = string.sub(out, 1, #out - 1)
        end
        out = out .. "..."
    end
    if cache then cache[key] = out end
    return out
end

function TREKReplicatorWindow:new(x, y, player)
    local o = ISPanelJoypad.new(self, x, y, RW, RH)
    o.player = player
    o.playerNum = U.try("rep.playerNum", function()
        return player:getPlayerNum()
    end) or 0
    o.background = false
    o.moveWithMouse = true
    o.qtyIndex = 1
    o.catIndex = 0          -- 0 is every category
    o.needle = ""
    o.rows = {}
    return o
end

function TREKReplicatorWindow:createChildren()
    ISPanelJoypad.createChildren(self)
    local cx = SIDE + PAD
    local cw = self.width - cx - PAD

    self.closeBtn = TREKLcarsButton:new(self.width - 90, 0, 90, TOPH,
        getText("IGUI_TREK_Close"), self, TREKReplicatorWindow.close, P.violet)
    self.closeBtn.roundLeft = false
    self.closeBtn:initialise()
    self:addChild(self.closeBtn)

    self.energyY = TOPH + PAD
    self.barY = self.energyY + 20

    -- Search, with the category button beside it. The box is the fast path
    -- for a keyboard; the button is the whole path for a pad.
    local searchY = self.barY + 28
    local catW = 120
    self.search = ISTextEntryBox:new("", cx, searchY, cw - catW - 6, 24)
    self.search.font = UIFont.Small
    self.search:initialise()
    self.search:instantiate()
    self.search:setClearButton(true)
    self.search.backgroundColor = { r = 0.02, g = 0.03, b = 0.07, a = 0.85 }
    self.search.borderColor = { r = P.blue[1], g = P.blue[2], b = P.blue[3], a = 0.55 }
    self.search:setPlaceholderText(getText("IGUI_TREK_RepSearch"))
    local win = self
    -- Assigned on the instance, the way ISChat.lua:171 does it: the base
    -- method is replaced, so it arrives with the box as self, not the window.
    self.search.onTextChange = function(entry)
        win.needle = string.lower(entry:getText() or "")
        win:refreshRows()
    end
    self:addChild(self.search)

    self.catBtn = TREKLcarsButton:new(cx + cw - catW, searchY, catW, 24, "", self,
        TREKReplicatorWindow.onCategory, P.lilac)
    self.catBtn.centreText = true
    self.catBtn:initialise()
    self:addChild(self.catBtn)

    local btnH, gap = 26, 6
    local row1 = self.height - BOTH - PAD - 30
    local row0 = row1 - gap - btnH
    local half = (cw - gap) / 2

    local listY = searchY + 24 + 10
    self.list = ISScrollingListBox:new(cx, listY, cw, row0 - PAD - listY)
    self.list:initialise()
    self.list:instantiate()
    self.list.font = UIFont.Small
    self.list.itemheight = ROWH
    self.list.selected = 0
    self.list.joypadParent = self
    self.list.drawBorder = true
    self.list.backgroundColor = { r = 0.01, g = 0.02, b = 0.05, a = 0.80 }
    self.list.borderColor = { r = P.lilac[1], g = P.lilac[2], b = P.lilac[3], a = 0.55 }
    self.list.doDrawItem = TREKReplicatorWindow.drawRow
    self.list.target = self
    self:addChild(self.list)

    self.qtyBtn = TREKLcarsButton:new(cx, row0, half, btnH, "", self,
        TREKReplicatorWindow.onQuantity, P.gold)
    self.qtyBtn:initialise()
    self:addChild(self.qtyBtn)

    self.scanBtn = TREKLcarsButton:new(cx + half + gap, row0, half, btnH,
        getText("IGUI_TREK_RepScan"), self, TREKReplicatorWindow.onScan, P.peach)
    self.scanBtn:initialise()
    self:addChild(self.scanBtn)

    self.makeBtn = TREKLcarsButton:new(cx, row1, cw, 30, "", self,
        TREKReplicatorWindow.onMaterialise, P.orange)
    self.makeBtn:initialise()
    self:addChild(self.makeBtn)

    -- Controller navigation, top to bottom. The text box is deliberately not
    -- in here: a stick cannot type, and a focus stop that does nothing is
    -- worse than none.
    self:insertNewLineOfButtons(self.catBtn)
    self:insertNewLineOfButtons(self.qtyBtn, self.scanBtn)
    self:insertNewLineOfButtons(self.makeBtn)
    self:setISButtonForB(self.closeBtn)

    self:refreshRows()
end

---------------------------------------------------------------------------
-- The rows
---------------------------------------------------------------------------
function TREKReplicatorWindow:category()
    if self.catIndex == 0 then return nil end
    return R.categories()[self.catIndex]
end

--- Filters the catalogue into the list. Called on every keystroke, so it
--- walks an array of precomputed lowercase strings and nothing else.
function TREKReplicatorWindow:refreshRows()
    local needle = self.needle
    local category = self:category()
    self.list:clear()
    self.rows = {}
    for _, row in ipairs(R.catalogue()) do
        local hit = (needle == "" or string.find(row.lower, needle, 1, true) ~= nil)
                and (category == nil or row.category == category)
        if hit then
            table.insert(self.rows, row)
            self.list:addItem(row.name, row)
        end
    end
    if #self.rows > 0 then
        self.list.selected = 1
    else
        self.list.selected = 0
    end
end

function TREKReplicatorWindow:selectedRow()
    local item = self.list.items[self.list.selected]
    return item and item.item or nil
end

function TREKReplicatorWindow:quantity()
    return C.ReplicatorQuantities[self.qtyIndex] or 1
end

--- One catalogue row. Known patterns read in the ship's colours; the rest are
--- drawn dim and say why -- a grey entry with a reason beats a missing one,
--- or a player cannot tell "you have not found one" from "this mod is broken".
function TREKReplicatorWindow:drawRow(y, item, alt)
    local row = item.item
    local w = self:getWidth()
    if self.selected == item.itemindex then
        self:drawRect(0, y, w, item.height - 1, 0.35, P.lilac[1], P.lilac[2], P.lilac[3])
    end

    local known = R.knows(row.id)
    local c = known and P.peach or P.dim
    local right = known and P.blue or P.dim

    local label = ellipsise(row.name, UIFont.Small, w - 190, row, "short")
    self:drawText(label, 8, y + 3, c[1], c[2], c[3], 1, UIFont.Small)

    local cat = ellipsise(row.category, UIFont.Small, 90, row, "shortCat")
    self:drawText(cat, w - 150, y + 3, P.dim[1] * 1.3, P.dim[2] * 1.3,
                  P.dim[3] * 1.3, 1, UIFont.Small)

    local text = known and tostring(row.cost)
                        or getText("IGUI_TREK_RepNoPatternShort")
    self:drawTextRight(text, w - 10, y + 3, right[1], right[2], right[3], 1, UIFont.Small)
    return y + item.height
end

---------------------------------------------------------------------------
-- Drawing
---------------------------------------------------------------------------
function TREKReplicatorWindow:prerender()
    -- A panel nobody is standing at closes itself. The server would refuse
    -- anyway, but a window that stays open and answers "too far" to every
    -- press reads as a broken machine.
    --
    -- Closing from inside a frame is vanilla's own pattern and not a liberty:
    -- twenty-six of its panels do it, and `ISFeedingTroughUI:prerender` is
    -- this exact case -- a fixture's window that shuts itself the moment the
    -- fixture is not there any more.
    if self.player and not R.inReachOf(self.player) then
        self:close()
        return
    end

    local w, h = self.width, self.height
    self:drawRect(0, 0, w, h, 0.97, 0.008, 0.012, 0.028)

    local function block(x, y, bw, bh, c)
        self:drawRect(x, y, bw, bh, 1, c[1], c[2], c[3])
    end

    -- Top elbow and title bar, in the helm's own furniture: two Starfleet
    -- consoles in one mod should not look like two mods.
    H.pill(self, 0, 0, RAD * 2, RAD * 2, P.orange, true, true)
    block(RAD, 0, SIDE - RAD, RAD, P.orange)
    block(0, RAD, SIDE, 96 - RAD, P.orange)
    local title = string.upper(getText("IGUI_TREK_RepTitle"))
    local closeX = self.closeBtn and self.closeBtn.x or (w - 90)
    block(SIDE, 0, math.max(0, closeX - 8 - SIDE), TOPH, P.orange)
    local fh = getTextManager():MeasureStringY(UIFont.Medium, title) or 14
    self:drawText(title, SIDE + 12, (TOPH - fh) / 2, 0, 0, 0, 1, UIFont.Medium)

    -- Sidebar and bottom elbow.
    block(0, 100, SIDE, h - 130 - 100, P.violet)
    block(0, h - 130, SIDE, 130 - RAD, P.lilac)
    block(RAD, h - RAD, SIDE - RAD, RAD, P.lilac)
    H.pill(self, 0, h - RAD * 2, RAD * 2, RAD * 2, P.lilac, true, true)
    block(SIDE, h - BOTH, w - SIDE - BOTH / 2, BOTH, P.lilac)
end

function TREKReplicatorWindow:render()
    ISPanelJoypad.render(self)
    local cx = SIDE + PAD
    local cw = self.width - cx - PAD
    local off = R.isOff()

    -- The reserve.
    local energy = math.floor(R.energy())
    local frac = energy / C.ReplicatorEnergyMax
    H.pill(self, cx, self.energyY + 3, 30, 10, P.gold, true, false)
    self:drawText(string.upper(getText("IGUI_TREK_RepEnergyHeader")), cx + 38,
                  self.energyY, P.gold[1], P.gold[2], P.gold[3], 1, UIFont.Small)
    self:drawTextRight(getText("IGUI_TREK_RepEnergyLevel", tostring(energy),
                               tostring(C.ReplicatorEnergyMax)),
                       self.width - PAD, self.energyY,
                       P.text[1], P.text[2], P.text[3], 1, UIFont.Small)

    self:drawRect(cx, self.barY, cw, 12, 0.55, 0.02, 0.03, 0.08)
    local fill = R.isFree() and cw or math.floor(cw * frac)
    if fill > 0 then
        local c = (frac > 0.25 or R.isFree()) and P.gold or P.red
        self:drawRect(cx, self.barY, fill, 12, 0.95, c[1], c[2], c[3])
    end
    self:drawRectBorder(cx, self.barY, cw, 12, 0.6, P.blue[1], P.blue[2], P.blue[3])

    -- The controls say what they will do before they are pressed.
    local cat = self:category()
    self.catBtn.title = cat and ellipsise(cat, UIFont.Small, 100, self, "catShort" .. self.catIndex)
                            or getText("IGUI_TREK_RepAllCategories")
    self.qtyBtn.title = getText("IGUI_TREK_RepQuantity", tostring(self:quantity()))

    local row = self:selectedRow()
    local known = row ~= nil and R.knows(row.id)
    if not row then
        self.makeBtn.title = getText("IGUI_TREK_RepNothingPicked")
        self.makeBtn.enable = false
    elseif not known then
        self.makeBtn.title = getText("IGUI_TREK_RepNoPatternShort")
        self.makeBtn.enable = false
    else
        local cost = R.cost(row, self:quantity())
        self.makeBtn.title = getText("IGUI_TREK_RepMaterialise", tostring(cost))
        self.makeBtn.enable = not off and cost <= R.energy()
    end
    self.scanBtn.enable = not off

    if #self.list.items == 0 then
        self:drawTextCentre(getText("IGUI_TREK_RepNoMatch"),
                            self.list.x + self.list.width / 2,
                            self.list.y + self.list.height / 2 - 8,
                            P.dim[1] * 1.4, P.dim[2] * 1.4, P.dim[3] * 1.4, 1,
                            UIFont.Small)
    end

    if off then
        self:drawText(getText("IGUI_TREK_RepOff"), cx, self.height - BOTH - 42,
                      P.red[1], P.red[2], P.red[3], 1, UIFont.Small)
    end

    if self.joyfocus then
        self:drawTextRight(string.upper(getText("IGUI_TREK_RepJoypadHint")),
                           self.width - BOTH - 6, self.height - BOTH + 1,
                           0, 0, 0, 1, UIFont.Small)
    end
end

---------------------------------------------------------------------------
-- Controls
---------------------------------------------------------------------------
function TREKReplicatorWindow:onCategory()
    self.catIndex = self.catIndex + 1
    if self.catIndex > #R.categories() then self.catIndex = 0 end
    self:refreshRows()
end

function TREKReplicatorWindow:onQuantity()
    self.qtyIndex = self.qtyIndex + 1
    if self.qtyIndex > #C.ReplicatorQuantities then self.qtyIndex = 1 end
end

function TREKReplicatorWindow:onMaterialise()
    local row = self:selectedRow()
    if not row then return end
    Core.send(self.player, "replicate", { id = row.id, count = self:quantity() })
end

function TREKReplicatorWindow:onScan()
    Core.send(self.player, "scanCarried", {})
end

--- Steps the selection, wrapping at both ends -- the bumpers, as the helm
--- steps its logged positions.
function TREKReplicatorWindow:stepRow(dir)
    local n = #self.list.items
    if n == 0 then return end
    local i = (self.list.selected or 0) + dir
    if i < 1 then i = n elseif i > n then i = 1 end
    self.list.selected = i
    U.try("rep.scroll", function() self.list:ensureVisible(i) end)
end

function TREKReplicatorWindow:onJoypadDown(button, joypadData)
    if button == Joypad.LBumper then
        self:stepRow(-1)
    elseif button == Joypad.RBumper then
        self:stepRow(1)
    else
        ISPanelJoypad.onJoypadDown(self, button, joypadData)
    end
end

function TREKReplicatorWindow:onGainJoypadFocus(joypadData)
    ISPanelJoypad.onGainJoypadFocus(self, joypadData)
    if self:getJoypadFocus() then
        self:restoreJoypadFocus(joypadData)
    else
        self:setJoypadFocusTopLeft(joypadData)
    end
end

function TREKReplicatorWindow:onLoseJoypadFocus(joypadData)
    ISPanelJoypad.onLoseJoypadFocus(self, joypadData)
    self:clearJoypadFocus(joypadData)
end

function TREKReplicatorWindow:close()
    M.window = nil
    -- Never leave a controller pointing at a panel that has gone.
    if self.joyfocus then
        U.try("rep.releaseFocus", function() setJoypadFocus(self.playerNum, nil) end)
    end
    self:setVisible(false)
    self:removeFromUIManager()
end

---------------------------------------------------------------------------
-- Opening it
---------------------------------------------------------------------------
function M.open(player)
    if M.window then
        U.try("rep.closeOld", function() M.window:close() end)
    end
    local w = U.try("rep.open", function()
        local win = TREKReplicatorWindow:new(140, 100, player)
        win:initialise()
        win:instantiate()
        win:addToUIManager()
        return win
    end)
    if not w then return nil end
    M.window = w
    U.try("rep.focus", function()
        if JoypadState.players[w.playerNum + 1] then
            setJoypadFocus(w.playerNum, w)
        end
    end)
    return w
end

--- Redraws an open panel after the server has answered.
local function refreshWindow()
    if M.window then U.try("rep.refresh", function() M.window:refreshRows() end) end
end

---------------------------------------------------------------------------
-- The ways in
---------------------------------------------------------------------------
--- The square the cursor is over, taken from the menu position so that it
--- resolves whatever is on the tile. TREK_Menu.lua does the same thing for
--- the same reason.
local function clickedSquare(playerIndex, context, player)
    local z = math.floor(player:getZ())
    local x = U.try("rep.screenToIsoX", function()
        return screenToIsoX(playerIndex, context.x, context.y, z)
    end)
    local y = U.try("rep.screenToIsoY", function()
        return screenToIsoY(playerIndex, context.x, context.y, z)
    end)
    if not x or not y then return nil end
    return math.floor(x), math.floor(y), z
end

--- True when this is the replicator's berth. By position rather than by the
--- object's tag: a rebuild that lost the tag would take the menu with it, and
--- the berth is at a fixed place in a cabin the mod builds itself.
local function isBerth(x, y, z)
    local ox, oy = R.spot()
    if not ox then return false end
    local rx, ry = U.at(ox, oy)
    return x == rx and y == ry and z == C.CabinZ
end

function M.onOpen(_, player)
    M.open(player)
end

function M.fillMenu(playerIndex, context, worldobjects, test)
    local player = U.player(playerIndex)
    if not player then return end
    if not U.isInteriorPlayer(player) then return end

    local x, y, z = clickedSquare(playerIndex, context, player)
    if not x or not isBerth(x, y, z) then return end
    if test then return ISWorldObjectContextMenu.setTest() end

    local option = context:addOption(getText("IGUI_TREK_RepUse"), worldobjects,
                                     M.onOpen, player)

    -- Shown and greyed rather than hidden, both times. A missing option is
    -- indistinguishable from a broken mod -- and the second case is the one
    -- that matters in play: a player who right-clicks the machine from across
    -- the cabin has to be told to walk over to it, not handed a panel that
    -- closes itself the moment it opens.
    local why = nil
    if R.isOff() then
        why = "IGUI_TREK_RepOff"
    elseif not R.inReachOf(player) then
        why = "IGUI_TREK_RepFar"
    end
    if why then
        option.notAvailable = true
        option.toolTip = ISWorldObjectContextMenu.addToolTip()
        option.toolTip.description = getText(why)
    end
    return true
end

Events.OnPreFillWorldObjectContextMenu.Add(M.fillMenu)

---------------------------------------------------------------------------
-- Storing a pattern from the item itself
---------------------------------------------------------------------------
--- The items in a context-menu selection, flattened. An entry is either an
--- InventoryItem or a stack -- a plain table with an `items` list -- and code
--- that handles one shape silently does nothing for the other.
local function selectedItems(list)
    local out = {}
    if not list then return out end
    for _, v in ipairs(list) do
        if instanceof(v, "InventoryItem") then
            table.insert(out, v)
        elseif type(v) == "table" and v.items then
            for _, it in ipairs(v.items) do
                if instanceof(it, "InventoryItem") then table.insert(out, it) end
            end
        end
    end
    return out
end

function M.onStorePattern(_, player, id)
    Core.send(player, "storePattern", { id = id })
end

--- Offered on an item you are holding while you are standing at the machine,
--- and only when the ship does not already know it. The panel's Scan button
--- does the same thing for a bagful at once; this is the discoverable route.
function M.fillInventoryMenu(playerIndex, context, items)
    local player = U.player(playerIndex)
    if not player then return end
    if R.isOff() or not R.inReachOf(player) then return end

    local seen = {}
    for _, item in ipairs(selectedItems(items)) do
        local id = U.try("rep.menuType", function() return item:getFullType() end)
        if id and not seen[id] then
            seen[id] = true
            local row = R.row(id)
            if row and not R.store().known[id] then
                context:addOption(getText("IGUI_TREK_RepStore", row.name), items,
                                  M.onStorePattern, player, id)
            end
        end
    end
end

Events.OnFillInventoryObjectContextMenu.Add(M.fillInventoryMenu)

---------------------------------------------------------------------------
-- What the server says back
---------------------------------------------------------------------------
TREK.Net.onClient("replicated", function(args)
    local player = U.player(0)
    if not player then return end
    local made = tonumber(args.made) or 0
    local asked = tonumber(args.asked) or 0

    if made == 0 then
        -- Nothing formed. The tray being full is far and away the likeliest
        -- reason, and a machine that hums and produces nothing without saying
        -- why is the worst version of this feature.
        warnNote(player, "IGUI_TREK_RepTrayFull")
    elseif made < asked then
        warnNote(player, "IGUI_TREK_RepPartial", tostring(made), tostring(asked))
    else
        note(player, "IGUI_TREK_RepMade", tostring(made), tostring(args.name or args.id))
    end
    if made > 0 then
        U.try("rep.sound", function() player:playSoundLocal("TREK_Replicate") end)
    end
    refreshWindow()
end)

TREK.Net.onClient("patternStored", function(args)
    local player = U.player(0)
    if not player then return end
    local learned = tonumber(args.learned) or 0

    if args.already then
        note(player, "IGUI_TREK_RepKnown", tostring(args.name or args.id))
    elseif learned == 0 then
        note(player, "IGUI_TREK_RepNothingNew")
    elseif args.id then
        note(player, "IGUI_TREK_RepStored", tostring(args.name or args.id))
    else
        note(player, "IGUI_TREK_RepScanned", tostring(learned))
    end
    if learned > 0 then
        U.try("rep.sound", function() player:playSoundLocal("TREK_Replicate") end)
    end
    refreshWindow()
end)

return M
