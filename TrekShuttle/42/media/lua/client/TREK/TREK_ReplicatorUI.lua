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

    **The list is a two-level tree**: the categories the game itself puts
    items in, then the items in one, with a Back button out. It was a button
    that cycled one category per press, which for seventy-eight of them is not
    a control. Each category row says how many of its items the ship has
    patterns for, because that is the number a player is looking for, and a
    toggle narrows the whole panel to those.

    **The controller is designed in, not bolted on.** A pad has no keyboard,
    so the search box cannot be the only way to find anything: the tree is
    walkable with the bumpers and one button, which opens a category or makes
    an item depending on what is picked. The text box is the fast path for a
    keyboard, and a search looks through everything wherever you are standing
    in the tree.

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
require "TREK/TREK_Power"
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

local RW, RH = 470, 676
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
    -- The list is a two-level tree: categories, then the items in one. nil is
    -- the root. A cycling button walked seventy-eight categories one press at
    -- a time, which is not a control, it is a punishment.
    o.category = nil
    o.knownOnly = false
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
    local searchY = self.barY + 40
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
        -- Typing steps out of whatever category you were in: a search is a
        -- view of the whole catalogue, and searching inside one folder while
        -- the box says otherwise is the kind of half-answer that makes a
        -- player think the item is not in the game.
        if win.needle ~= "" then win.category = nil end
        win:refreshRows()
    end
    self:addChild(self.search)

    self.backBtn = TREKLcarsButton:new(cx + cw - catW, searchY, catW, 24, "", self,
        TREKReplicatorWindow.onBack, P.lilac)
    self.backBtn.centreText = true
    self.backBtn:initialise()
    self:addChild(self.backBtn)

    local btnH, gap = 26, 6
    local row2 = self.height - BOTH - PAD - 30
    local row1 = row2 - gap - btnH
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
    -- A click on a category row opens it, which is what a mouse expects of a
    -- folder. An item row only selects; the action button is what makes it.
    self.list.onmousedown = TREKReplicatorWindow.onRowClicked
    self:addChild(self.list)

    self.knownBtn = TREKLcarsButton:new(cx, row0, half, btnH, "", self,
        TREKReplicatorWindow.onKnownOnly, P.blue)
    self.knownBtn:initialise()
    self:addChild(self.knownBtn)

    self.qtyBtn = TREKLcarsButton:new(cx + half + gap, row0, half, btnH, "", self,
        TREKReplicatorWindow.onQuantity, P.gold)
    self.qtyBtn:initialise()
    self:addChild(self.qtyBtn)

    self.scanBtn = TREKLcarsButton:new(cx, row1, cw, btnH,
        getText("IGUI_TREK_RepScan"), self, TREKReplicatorWindow.onScan, P.peach)
    self.scanBtn:initialise()
    self:addChild(self.scanBtn)

    -- One button, and what it does depends on what is picked: open a category
    -- or make an item. A pad has no double-click, so the alternative was two
    -- buttons, one of which is always dead.
    self.makeBtn = TREKLcarsButton:new(cx, row2, cw, 30, "", self,
        TREKReplicatorWindow.onAction, P.orange)
    self.makeBtn:initialise()
    self:addChild(self.makeBtn)

    -- Controller navigation, top to bottom. The text box is deliberately not
    -- in here: a stick cannot type, and a focus stop that does nothing is
    -- worse than none.
    self:insertNewLineOfButtons(self.backBtn)
    self:insertNewLineOfButtons(self.knownBtn, self.qtyBtn)
    self:insertNewLineOfButtons(self.scanBtn)
    self:insertNewLineOfButtons(self.makeBtn)
    self:setISButtonForB(self.closeBtn)

    self:refreshRows()
end

---------------------------------------------------------------------------
-- The rows
---------------------------------------------------------------------------
--- Fills the list with whatever the player should be looking at.
---
--- Three states, and the order of the branches is the design:
---
---   * **a search shows items from everywhere**, whatever category you are
---     standing in. Somebody typing "bandage" wants bandages, not to be told
---     they are in the wrong folder;
---   * inside a category, its items;
---   * otherwise the categories themselves, each saying how many patterns the
---     ship has in it.
---
--- Called on every keystroke, so the work is a `string.find` over lowercase
--- strings that were built once, and a category is an index lookup rather
--- than a walk of four thousand rows.
function TREKReplicatorWindow:refreshRows()
    local needle, knownOnly = self.needle, self.knownOnly
    self.list:clear()
    self.rows = {}

    local function add(row)
        table.insert(self.rows, row)
        self.list:addItem(row.name, row)
    end

    local function wanted(item)
        return not knownOnly or R.knows(item.id)
    end

    if needle ~= "" then
        for _, item in ipairs(R.catalogue()) do
            if wanted(item) and string.find(item.lower, needle, 1, true) then
                add({ kind = "item", item = item, name = item.name })
            end
        end
    elseif self.category then
        for _, item in ipairs(R.inCategory(self.category)) do
            if wanted(item) then
                add({ kind = "item", item = item, name = item.name })
            end
        end
    else
        for _, name in ipairs(R.categories()) do
            local total, known = R.categoryCount(name)
            if not knownOnly or known > 0 then
                add({ kind = "category", name = name, total = total, known = known })
            end
        end
    end

    self.list.selected = (#self.rows > 0) and 1 or 0

    -- How many spares are in the chamber. Read here rather than in render:
    -- it walks a container, and refreshRows runs when the panel opens and
    -- whenever the server answers, which is every moment it can change.
    self.spares = TREK.Power.crystals(TREK.Power.poolOf(self.player))
end

--- The row the player has picked, whatever kind it is.
function TREKReplicatorWindow:selected()
    local entry = self.list.items[self.list.selected]
    return entry and entry.item or nil
end

--- The catalogue row picked, or nil when a category is.
function TREKReplicatorWindow:selectedRow()
    local row = self:selected()
    if row and row.kind == "item" then return row.item end
    return nil
end

--- Steps into a category, or back out of one.
function TREKReplicatorWindow:openCategory(name)
    self.category = name
    -- A search is a view of the whole catalogue, so stepping into a category
    -- clears it rather than quietly intersecting the two.
    if self.needle ~= "" then
        self.needle = ""
        U.try("rep.clearSearch", function() self.search:setText("") end)
    end
    self:refreshRows()
end

function TREKReplicatorWindow:quantity()
    return C.ReplicatorQuantities[self.qtyIndex] or 1
end

--- One row, which is either a category or an item.
---
--- A known pattern reads in the ship's colours and the rest are drawn dim and
--- say why: a grey entry with a reason beats a missing one, or a player
--- cannot tell "you have not found one of those" from "this mod is broken".
function TREKReplicatorWindow:drawRow(y, entry, alt)
    local row = entry.item
    local w = self:getWidth()
    if self.selected == entry.itemindex then
        self:drawRect(0, y, w, entry.height - 1, 0.35, P.lilac[1], P.lilac[2], P.lilac[3])
    end

    if row.kind == "category" then
        -- A folder, with what is in it and how much of that the ship can
        -- actually make -- which is the number a player is looking for.
        local c = (row.known > 0) and P.gold or P.dim
        local label = ellipsise(row.name, UIFont.Small, w - 120, row, "short")
        self:drawText(label, 8, y + 3, c[1], c[2], c[3], 1, UIFont.Small)
        self:drawTextRight(getText("IGUI_TREK_RepCategoryKnown",
                                   tostring(row.known), tostring(row.total)),
                           w - 10, y + 3, P.text[1], P.text[2], P.text[3], 1,
                           UIFont.Small)
        return y + entry.height
    end

    local item = row.item
    local known = R.knows(item.id)
    local c = known and P.peach or P.dim
    local right = known and P.blue or P.dim

    local label = ellipsise(item.name, UIFont.Small, w - 190, item, "short")
    self:drawText(label, 8, y + 3, c[1], c[2], c[3], 1, UIFont.Small)

    local cat = ellipsise(item.category, UIFont.Small, 90, item, "shortCat")
    self:drawText(cat, w - 150, y + 3, P.dim[1] * 1.3, P.dim[2] * 1.3,
                  P.dim[3] * 1.3, 1, UIFont.Small)

    local text = known and tostring(item.cost)
                        or getText("IGUI_TREK_RepNoPatternShort")
    self:drawTextRight(text, w - 10, y + 3, right[1], right[2], right[3], 1, UIFont.Small)
    return y + entry.height
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
    -- A dark ship's replicator is OFFLINE (ENERGY.md 6): no buttons that all
    -- fail, and one word saying why.
    -- Whichever ship this machine is in: the shuttle's, or the Adirondack's.
    local pool = TREK.Power.poolOf(self.player)
    local dark = TREK.Power.dark(pool)

    -- The reserve.
    local energy = math.floor(TREK.Power.reserve(pool))
    H.pill(self, cx, self.energyY + 3, 30, 10, P.gold, true, false)
    self:drawText(string.upper(getText("IGUI_TREK_RepEnergyHeader")), cx + 38,
                  self.energyY, P.gold[1], P.gold[2], P.gold[3], 1, UIFont.Small)
    self:drawTextRight(getText("IGUI_TREK_RepEnergyLevel", tostring(energy),
                               tostring(C.PowerMax)),
                       self.width - PAD, self.energyY,
                       P.text[1], P.text[2], P.text[3], 1, UIFont.Small)

    H.powerBar(self, cx, self.barY, cw, 12, { free = R.isFree() })

    -- What the bar actually is: the crystal in the chamber, and what is left
    -- behind it. A player who cannot see the spares cannot tell "nearly out"
    -- from "out", which is the difference between carrying on and going
    -- looking for dilithium.
    local spares = self.spares or 0
    local sc = spares > 0 and P.lilac or P.red
    self:drawTextRight(spares > 0 and getText("IGUI_TREK_RepCrystals", tostring(spares))
                                  or getText("IGUI_TREK_RepNoSpares"),
                       self.width - PAD, self.barY + 16,
                       sc[1], sc[2], sc[3], 1, UIFont.Small)

    -- The controls say what they will do before they are pressed.
    local inside = self.category ~= nil or self.needle ~= ""
    self.backBtn.title = inside and getText("IGUI_TREK_RepBack")
                                or getText("IGUI_TREK_RepAllCategories")
    self.backBtn.enable = inside
    self.knownBtn.title = self.knownOnly and getText("IGUI_TREK_RepKnownOnly")
                                         or getText("IGUI_TREK_RepAllItems")
    self.qtyBtn.title = getText("IGUI_TREK_RepQuantity", tostring(self:quantity()))

    -- Where you are, above the list: the root, or the category you opened.
    self:drawText(self.category
                      and ellipsise(self.category, UIFont.Small, cw - 20, self,
                                    "where" .. self.category)
                      or getText("IGUI_TREK_RepAllCategories"),
                  cx, self.list.y - 16, P.lilac[1], P.lilac[2], P.lilac[3], 1,
                  UIFont.Small)

    local picked = self:selected()
    local row = self:selectedRow()
    if picked and picked.kind == "category" then
        self.makeBtn.title = getText("IGUI_TREK_RepBrowse",
                                     ellipsise(picked.name, UIFont.Small, 160,
                                               picked, "shortOpen"))
        self.makeBtn.enable = true
    elseif not row then
        self.makeBtn.title = getText("IGUI_TREK_RepNothingPicked")
        self.makeBtn.enable = false
    elseif not R.knows(row.id) then
        self.makeBtn.title = getText("IGUI_TREK_RepNoPatternShort")
        self.makeBtn.enable = false
    else
        local cost = R.cost(row, self:quantity())
        self.makeBtn.title = getText("IGUI_TREK_RepMaterialise", tostring(cost))
        -- Live when the reserve covers it **or** there is a crystal to load:
        -- the ship swaps one in by itself, so greying the button on a low
        -- reserve would refuse something that would have worked.
        self.makeBtn.enable = not off and not dark
            and (cost <= TREK.Power.reserve(TREK.Power.poolOf(self.player))
                 or (self.spares or 0) > 0)
    end
    self.scanBtn.enable = not off and not dark

    if #self.list.items == 0 then
        local why = (self.knownOnly and self.needle == "")
                    and "IGUI_TREK_RepNothingKnown" or "IGUI_TREK_RepNoMatch"
        self:drawTextCentre(getText(why),
                            self.list.x + self.list.width / 2,
                            self.list.y + self.list.height / 2 - 8,
                            P.dim[1] * 1.4, P.dim[2] * 1.4, P.dim[3] * 1.4, 1,
                            UIFont.Small)
    end

    if off then
        self:drawText(getText("IGUI_TREK_RepOff"), cx, self.height - BOTH - 42,
                      P.red[1], P.red[2], P.red[3], 1, UIFont.Small)
    elseif dark then
        self:drawText(getText("IGUI_TREK_RepOffline"), cx, self.height - BOTH - 42,
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
--- Back out of a category, or out of a search, to the list of categories.
function TREKReplicatorWindow:onBack()
    if self.needle ~= "" then
        self.needle = ""
        U.try("rep.clearSearch", function() self.search:setText("") end)
    end
    self.category = nil
    self:refreshRows()
end

--- Narrows the whole panel to what the ship can actually make.
---
--- It applies to the categories as well as to the items: with it on, a
--- category the ship has no patterns in is not worth walking into, so it is
--- not offered.
function TREKReplicatorWindow:onKnownOnly()
    self.knownOnly = not self.knownOnly
    self:refreshRows()
end

function TREKReplicatorWindow:onQuantity()
    self.qtyIndex = self.qtyIndex + 1
    if self.qtyIndex > #C.ReplicatorQuantities then self.qtyIndex = 1 end
end

--- Open a category, or make the item -- whichever is picked.
function TREKReplicatorWindow:onAction()
    local picked = self:selected()
    if not picked then return end
    if picked.kind == "category" then
        self:openCategory(picked.name)
        return
    end
    local row = picked.item
    Core.send(self.player, "replicate", { id = row.id, count = self:quantity() })
end

--- A mouse click in the list. The list box calls this with the row's own
--- item, after it has moved the selection.
function TREKReplicatorWindow:onRowClicked(picked)
    if picked and picked.kind == "category" then
        self:openCategory(picked.name)
    end
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
-- U.clickedSquare, shared with the warp core: both machines own a square
-- and neither can be found from the objects the menu event is handed.

--- True when a click is at the replicator's berth, or near enough.
---
--- By position rather than by the object's tag: a rebuild that lost the tag
--- would take the menu with it, and the berth is at a fixed place in a cabin
--- the mod builds itself.
---
--- **And "near enough" is one square, which is not slack.** A right-click
--- resolves to the *floor square under the cursor*, and the alcove is drawn
--- standing over a metre of counter -- so the pixels a player clicks when
--- they aim at the lit recess map to a square a tile or two north-west of the
--- one the machine is on. Keyed to the exact square, the option was never
--- offered at all: seen in game, 2026-09-20, with the alcove plainly visible
--- and nothing to right-click on it.
---
--- Every tall object in this game has the same property -- you interact with
--- a fridge by clicking its base, not its top -- so the margin is what makes
--- the natural gesture work rather than a licence. One square, so the
--- transporter pad two squares away still offers nothing.
---
--- The number lives in the config rather than here so that
--- tests/test_layout.py's cross-fixture rule reads the one the menu actually
--- uses. A copy of it in the test would go stale the first time this moved,
--- and the rule it enforces is the one that stopped the warp core answering
--- on the Doctor's square.
local BERTH_MARGIN = C.ReplicatorMenuMargin

local function isBerth(x, y, z)
    if TREK.Adirondack and TREK.Adirondack.clickedMachine("replicator", x, y, z, BERTH_MARGIN) then
        return true
    end
    local ox, oy = R.spot()
    if not ox then return false end
    if z ~= C.CabinZ then return false end
    local rx, ry = U.at(ox, oy)
    return math.abs(x - rx) <= BERTH_MARGIN and math.abs(y - ry) <= BERTH_MARGIN
end

function M.onOpen(_, player)
    M.open(player)
end

function M.fillMenu(playerIndex, context, worldobjects, test)
    local player = U.player(playerIndex)
    if not player then return end
    if not U.isInteriorPlayer(player) and not TREK.Adirondack.onShip(player) then return end

    local x, y, z = U.clickedSquare(playerIndex, context, player)
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
    elseif TREK.Power.dark(TREK.Power.poolOf(player)) then
        why = "IGUI_TREK_RepOffline"
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
    if R.isOff() or TREK.Power.dark(TREK.Power.poolOf(player)) or not R.inReachOf(player) then return end

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
        -- Nothing formed at all. The likeliest reason by far is an item that
        -- is in the catalogue and will not instance -- an obsolete one that
        -- slipped the filter -- and the server has logged which. A machine
        -- that hums and produces nothing without saying why is the worst
        -- version of this feature.
        warnNote(player, "IGUI_TREK_RepFailed")
    elseif made < asked then
        warnNote(player, "IGUI_TREK_RepPartial", tostring(made), tostring(asked))
    else
        note(player, "IGUI_TREK_RepMade", tostring(made), tostring(args.name or args.id))
    end
    if made > 0 then
        U.try("rep.sound", function() player:playSoundLocal("TREK_Replicate") end)
    end
    if M.window and args.crystals then M.window.spares = tonumber(args.crystals) end
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
