--[[ Shuttlecraft -- the PADD's screen (PADD.md 12).

    The mod's fifth LCARS panel, and the first one that is not a fitting: it
    opens wherever the player is, because the PADD is the comms terminal and
    the Adirondack is in orbit (PADD.md 12.4, COMMS.md 5).

    Three views, on the shoulder buttons:

      * **Channel** -- the live call, or the last one. The holder's options
        are the only interactive part; everybody else reads. An incoming call
        is answered here, a player hails from here, and a channel somebody let
        go of is picked up from here.
      * **History** -- every call the ship has had, replayed from node ids.
      * **Library** -- this PADD's books and transcripts, and the six
        fragments in order.

    **A PADD is a container for the library and a window onto the channel**
    (PADD.md 12.1). The books and transcripts shown are the ones on the PADD
    this screen was opened from; the channel is the ship's, the same on every
    PADD, and lost with none of them.

    Everything here is a request. The screen reads the copies the server last
    published -- the channel, the history, the PADD's mod data -- and every
    button asks. Which options a holder may take is the server's answer
    (`call.avail`), because the questions behind them (what you carry, what
    you have watched) are only answered truly on the authority.

    **Deck first** (PADD.md 12.5): every control is on the stick, the three
    views are on LB and RB, X and Y step whatever list is showing, the
    transcript scrolls with two buttons as well as the wheel, focus is always
    drawn, nothing lives in a tooltip, a timed node's clock is on screen, and
    it is laid out for 1280x800.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Ship"
require "TREK/TREK_Net"
require "TREK/TREK_Padd"
require "TREK/TREK_PaddActions"
require "TREK/TREK_Comms"
require "TREK/TREK_Helm"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Ship = TREK.Ship
local Net = TREK.Net
local Pd = TREK.Padd
local Cm = TREK.Comms
local H = TREK.Helm
local Pal = H.P

local S = {}
TREK.PaddScreen = S

local SIDE, TOPH, PAD, ROWH, GAP = 64, 28, 14, 30, 6
local TABW = 150
local LISTW = 340
local WHOW = 120          -- the speaker column in a transcript
local LINEH = 22
local OPTIONS = 4         -- option buttons on the channel view
local FONT = UIFont.Medium

S.TABS = { "channel", "history", "library" }
-- Spelled out rather than built, so every key is a literal the asset check
-- can find (tests/test_assets.py reads getText calls out of the source).
S.TAB_KEYS = { channel = "IGUI_TREK_PaddTab_channel",
               history = "IGUI_TREK_PaddTab_history",
               library = "IGUI_TREK_PaddTab_library" }

--- The screen's size: most of the screen, and never less than a Deck's.
function S.size()
    local sw = U.try("padd.sw", function() return getCore():getScreenWidth() end) or 1280
    local sh = U.try("padd.sh", function() return getCore():getScreenHeight() end) or 800
    local w = math.max(900, math.min(1180, sw - 40))
    local h = math.max(600, math.min(760, sh - 40))
    return w, h
end

--- Splits text into lines no wider than `width` in `font`.
function S.wrap(text, font, width)
    local out = {}
    local tm = getTextManager()
    local line = ""
    for word in tostring(text or ""):gmatch("%S+") do
        local try = line == "" and word or (line .. " " .. word)
        if tm:MeasureStringX(font, try) <= width or line == "" then
            line = try
        else
            table.insert(out, line)
            line = word
        end
    end
    if line ~= "" then table.insert(out, line) end
    if #out == 0 then table.insert(out, "") end
    return out
end

TREKPaddScreen = ISPanelJoypad:derive("TREKPaddScreen")

function TREKPaddScreen:new(x, y, player, padd)
    local w, h = S.size()
    local o = ISPanelJoypad.new(self, x, y, w, h)
    o.player = player
    o.padd = padd
    o.playerNum = U.try("padd.playerNum", function() return player:getPlayerNum() end) or 0
    o.background = false
    o.moveWithMouse = true
    o.tab = "channel"
    o.scroll = 0
    o.lines = {}
    o.linesSig = nil
    return o
end

local function button(self, x, y, w, h, title, fn, colour)
    local b = TREKLcarsButton:new(x, y, w, h, title, self, fn, colour)
    b:initialise()
    self:addChild(b)
    return b
end

function TREKPaddScreen:createChildren()
    ISPanelJoypad.createChildren(self)
    local cx = SIDE + PAD
    local cw = self.width - cx - PAD

    self.closeBtn = button(self, self.width - 110, 0, 110, TOPH,
                           getText("IGUI_TREK_Close"), TREKPaddScreen.close, Pal.violet)
    self.closeBtn.roundLeft = false

    -- The views.
    local ty = TOPH + PAD
    self.tabBtns = {}
    for i, tab in ipairs(S.TABS) do
        local b = button(self, cx + (i - 1) * (TABW + GAP), ty, TABW, ROWH,
                         getText(S.TAB_KEYS[tab]),
                         TREKPaddScreen.onTab, Pal.lilac)
        b.tab = tab
        self.tabBtns[i] = b
    end

    self.bodyY = ty + ROWH + PAD
    self.bottom = self.height - 16 - PAD

    -- The transcript's scroll buttons: the wheel is not a Deck's.
    local sw = 70
    self.upBtn = button(self, self.width - PAD - sw * 2 - GAP, self.bodyY, sw, 22,
                        getText("IGUI_TREK_PaddUp"), TREKPaddScreen.onUp, Pal.blue)
    self.downBtn = button(self, self.width - PAD - sw, self.bodyY, sw, 22,
                          getText("IGUI_TREK_PaddDown"), TREKPaddScreen.onDown, Pal.blue)

    -- Channel: the option buttons, and one action button in the first slot's
    -- place for answering, hailing or picking a dropped call up.
    local optH = OPTIONS * (ROWH + GAP)
    self.optY = self.bottom - optH
    self.optBtns = {}
    for i = 1, OPTIONS do
        local b = button(self, cx, self.optY + (i - 1) * (ROWH + GAP), cw, ROWH, "",
                         TREKPaddScreen.onOption, Pal.gold)
        b.roundRight = true
        b.slot = i
        self.optBtns[i] = b
    end
    self.actionBtn = button(self, cx, self.optY, cw, ROWH, "",
                            TREKPaddScreen.onAction, Pal.orange)

    -- History and library: a list on the left, a transcript on the right.
    local listY = self.bodyY
    local listH = self.bottom - listY - ROWH - GAP
    self.list = ISScrollingListBox:new(cx, listY, LISTW, listH)
    self.list:initialise()
    self.list:instantiate()
    self.list.itemheight = 26
    self.list.selected = 1
    self.list.drawBorder = true
    self.list.font = UIFont.Small
    self.list.backgroundColor = { r = 0.02, g = 0.03, b = 0.06, a = 0.6 }
    self.list.borderColor = { r = Pal.lilac[1], g = Pal.lilac[2], b = Pal.lilac[3], a = 0.55 }
    self.list.doDrawItem = TREKPaddScreen.drawRow
    self.list.screen = self
    self:addChild(self.list)

    self.readBtn = button(self, cx, self.bottom - ROWH, LISTW, ROWH,
                          getText("IGUI_TREK_PaddReadBtn"), TREKPaddScreen.onRead, Pal.gold)

    self:insertNewLineOfButtons(self.tabBtns[1], self.tabBtns[2], self.tabBtns[3],
                                self.upBtn, self.downBtn)
    self:insertNewListOfButtons({ self.list })
    self:insertNewLineOfButtons(self.readBtn)
    self:insertNewLineOfButtons(self.actionBtn)
    for i = 1, OPTIONS do self:insertNewLineOfButtons(self.optBtns[i]) end
    self:setISButtonForB(self.closeBtn)

    self:layout()
end

--- The box a transcript is drawn in, for the current view.
function TREKPaddScreen:textBox()
    local cx = SIDE + PAD
    local top = self.bodyY + 30
    if self.tab == "channel" then
        return cx, top, self.width - cx - PAD, self.optY - PAD - top - 18
    end
    local x = cx + LISTW + PAD
    return x, top, self.width - x - PAD, self.bottom - top
end

--- Shows the controls this view has and hides the rest. Navigation skips
--- anything hidden (ISPanelJoypad.getVisibleChildren), so this is also what
--- decides what a controller can reach.
function TREKPaddScreen:layout()
    local channel = self.tab == "channel"
    local lists = self.tab == "history" or self.tab == "library"
    self.list:setVisible(lists)
    self.readBtn:setVisible(self.tab == "library")
    self.actionBtn:setVisible(false)
    for _, b in ipairs(self.optBtns) do b:setVisible(false) end
    if channel then self:layoutChannel() end
    for _, b in ipairs(self.tabBtns) do
        b.colour = b.tab == self.tab and Pal.orange or Pal.lilac
    end
end

---------------------------------------------------------------------------
-- The channel
---------------------------------------------------------------------------
function TREKPaddScreen:me()
    return Ship.usernameOf(self.player)
end

--- What the channel view is showing, as one word: idle, ringing, holding
--- (this player holds it), listening (somebody else does), open (nobody).
function TREKPaddScreen:channelState()
    local call = Cm.call()
    if not call then return "idle", nil end
    if call.state == "ringing" then return "ringing", call end
    if not call.holder then return "open", call end
    if call.holder == self:me() then return "holding", call end
    return "listening", call
end

function TREKPaddScreen:layoutChannel()
    local state, call = self:channelState()
    if state == "holding" then
        local opts = Cm.options(call)
        for i, b in ipairs(self.optBtns) do
            local o = opts[i]
            b:setVisible(o ~= nil)
            if o then
                b.title = o.text
                b.option = o.index
            end
        end
        return
    end
    local titles = {
        idle = "IGUI_TREK_CommsHail",
        ringing = "IGUI_TREK_CommsAnswer",
        open = "IGUI_TREK_CommsTake",
    }
    if titles[state] then
        self.actionBtn:setVisible(true)
        self.actionBtn.title = getText(titles[state])
        self.actionBtn.state = state
    end
end

function TREKPaddScreen:onOption(b)
    local call = Cm.call()
    if not call or not b.option then return end
    Net.send(self.player, "commsChoose", { id = call.id, node = call.node,
                                           option = b.option })
end

function TREKPaddScreen:onAction(b)
    local call = Cm.call()
    if b.state == "idle" then
        Net.send(self.player, "commsHail", {})
    elseif call then
        Net.send(self.player, "commsAnswer", { id = call.id })
    end
end

--- The status line over the channel's transcript.
function TREKPaddScreen:channelStatus()
    local state, call = self:channelState()
    if state == "idle" then
        if Cm.store().flags.quiet then return getText("IGUI_TREK_CommsQuiet"), Pal.dim end
        return getText("IGUI_TREK_CommsIdle"), Pal.dim
    elseif state == "ringing" then
        return getText("IGUI_TREK_CommsRinging", Cm.title(call.thread)), Pal.red
    elseif state == "holding" then
        return getText("IGUI_TREK_CommsHolding", Cm.title(call.thread)), Pal.gold
    elseif state == "listening" then
        return getText("IGUI_TREK_CommsSpeaking", tostring(call.holderName or "?")), Pal.blue
    end
    return getText("IGUI_TREK_CommsOpen", Cm.title(call.thread)), Pal.orange
end

--- Seconds left on a timed node, as this client can best tell: counted from
--- the moment the node arrived here. The server's clock is the one that
--- decides; this one is so the player can see the silence coming.
function TREKPaddScreen:secondsLeft(call)
    if not call or not call.timeout then return nil end
    if self.nodeSerial ~= call.nodeSerial then
        self.nodeSerial = call.nodeSerial
        self.nodeMs = getTimestampMs()
    end
    local gone = (getTimestampMs() - (self.nodeMs or getTimestampMs())) / 1000
    return math.max(0, math.floor(call.timeout - gone + 0.5))
end

---------------------------------------------------------------------------
-- What the transcript box holds
---------------------------------------------------------------------------
--- The rows of the transcript for the current view, before wrapping:
--- `{ who, text, r, g, b }`, plus a heading.
function TREKPaddScreen:content()
    if self.tab == "channel" then
        local call = Cm.call()
        if call and call.state == "live" then
            return getText("IGUI_TREK_CommsLive"), Cm.render(call.steps, call.a1, call.a2)
        end
        if call and call.state == "ringing" then
            return getText("IGUI_TREK_CommsIncoming"), {}
        end
        local rows = Cm.log().rows
        local last = rows[#rows]
        if last then
            return getText("IGUI_TREK_CommsLast", tostring(last.d or 0), Cm.title(last.t)),
                   self:rowTranscript(last)
        end
        return getText("IGUI_TREK_CommsNever"), {}
    end
    local row = self.list.items[self.list.selected]
    local item = row and row.item
    if not item then return self.tab == "history" and getText("IGUI_TREK_CommsNoHistory")
                            or getText("IGUI_TREK_PaddEmptyScreen"), {} end
    if item.kind == "call" then
        return getText("IGUI_TREK_CommsDay", tostring(item.row.d or 0),
                       Cm.title(item.row.t)), self:rowTranscript(item.row)
    elseif item.kind == "tape" then
        local out = {}
        for _, ln in ipairs(Pd.tapeLines(item.id)) do
            table.insert(out, { text = ln.text, r = ln.r, g = ln.g, b = ln.b })
        end
        return Pd.tapeTitle(item.id), out
    elseif item.kind == "book" then
        return item.entry.name or item.entry.type, self:bookDetail(item.entry)
    elseif item.kind == "fragment" then
        return getText("IGUI_TREK_FragmentN", tostring(item.n)), self:fragmentDetail(item.n)
    end
    return item.text or "", {}
end

function TREKPaddScreen:rowTranscript(row)
    if row.out == "missed" then
        return { { text = getText("IGUI_TREK_CommsMissedRow"), r = Pal.red[1],
                   g = Pal.red[2], b = Pal.red[3] } }
    end
    local out = Cm.render(row.s, row.a1, row.a2)
    if row.out == "cut" then
        table.insert(out, { text = getText("IGUI_TREK_CommsCutRow"), r = Pal.red[1],
                            g = Pal.red[2], b = Pal.red[3] })
    end
    return out
end

function TREKPaddScreen:bookDetail(e)
    local c = Pal.text
    local out = {}
    local kind = e.kind == "skill" and getText("IGUI_TREK_PaddSkillBooks")
                 or e.kind == "recipe" and getText("IGUI_TREK_PaddRecipes")
                 or getText("IGUI_TREK_PaddLiterature")
    table.insert(out, { text = kind, r = c[1], g = c[2], b = c[3] })
    if (e.pages or 0) > 0 then
        table.insert(out, { text = getText("IGUI_TREK_PaddPages", tostring(e.pages)),
                            r = c[1], g = c[2], b = c[3] })
    end
    if Pd.isRead(self.player, e) then
        table.insert(out, { text = getText("IGUI_TREK_PaddAlreadyRead"),
                            r = Pal.blue[1], g = Pal.blue[2], b = Pal.blue[3] })
    end
    local why = Pd.readRefusal(self.player, e)
    if why then
        local key = ({ illiterate = "IGUI_TREK_PaddIlliterate",
                       tooHard = "IGUI_TREK_PaddTooHard",
                       tooEasy = "IGUI_TREK_PaddTooEasy" })[why] or "IGUI_TREK_PaddTooHard"
        table.insert(out, { text = getText(key), r = Pal.red[1], g = Pal.red[2],
                            b = Pal.red[3] })
    end
    return out
end

--- A fragment's slot: on this PADD as a transcript, on the shelf waiting to
--- be transcribed, or not yet recovered (LORE.md 1c, the six in order).
function TREKPaddScreen:fragmentDetail(n)
    local tape = C.FragmentTapes and C.FragmentTapes[n]
    if tape and Pd.hasTape(self.padd, tape) then
        local out = {}
        for _, ln in ipairs(Pd.tapeLines(tape)) do
            table.insert(out, { text = ln.text, r = ln.r, g = ln.g, b = ln.b })
        end
        return out
    end
    local c = Pal.dim
    local key = "IGUI_TREK_FragmentMissing"
    if (Cm.store().converted or {})[n] then key = "IGUI_TREK_FragmentShelf" end
    return { { text = getText(key), r = c[1] * 1.6, g = c[2] * 1.6, b = c[3] * 1.6 } }
end

---------------------------------------------------------------------------
-- Lists
---------------------------------------------------------------------------
--- Rebuilds the list for the current view, keeping the selection.
function TREKPaddScreen:refreshList()
    local keep = self.list.selected
    self.list:clear()
    if self.tab == "history" then
        local rows = Cm.log().rows
        for i = #rows, 1, -1 do
            local r = rows[i]
            local label = getText("IGUI_TREK_CommsRow", tostring(r.d or 0), Cm.title(r.t))
            if r.out == "missed" then label = label .. " " .. getText("IGUI_TREK_CommsMissedTag") end
            self.list:addItem(label, { kind = "call", row = r })
        end
    elseif self.tab == "library" then
        local lib = {}
        for _, e in ipairs(Pd.library(self.padd)) do table.insert(lib, e) end
        table.sort(lib, function(a, b)
            if a.kind ~= b.kind then return tostring(a.kind) < tostring(b.kind) end
            return tostring(a.name) < tostring(b.name)
        end)
        for _, e in ipairs(lib) do
            self.list:addItem(e.name or e.type, { kind = "book", entry = e })
        end
        local fragTapes = {}
        for _, t in ipairs(C.FragmentTapes or {}) do fragTapes[t] = true end
        for _, id in ipairs(Pd.tapes(self.padd)) do
            if not fragTapes[id] then
                self.list:addItem(getText("IGUI_TREK_PaddTapeRow", Pd.tapeTitle(id)),
                                  { kind = "tape", id = id })
            end
        end
        -- The fragments show once the channel has mentioned them, in order,
        -- whether or not any is found: a gap is the point.
        if Cm.store().flags.clueSeen then
            for n = 1, 6 do
                self.list:addItem(getText("IGUI_TREK_FragmentN", tostring(n)),
                                  { kind = "fragment", n = n })
            end
        end
    end
    local n = #self.list.items
    if n == 0 then self.list.selected = 0
    elseif keep < 1 or keep > n then self.list.selected = 1
    else self.list.selected = keep end
end

function TREKPaddScreen.drawRow(list, y, row, alt)
    local screen = list.screen
    if list.selected == row.itemindex then
        list:drawRect(0, y, list:getWidth(), row.height - 1, 0.35,
                      Pal.lilac[1], Pal.lilac[2], Pal.lilac[3])
    end
    local c = Pal.peach
    local item = row.item
    if item and item.kind == "call" and item.row.out ~= "done" then c = Pal.red end
    if item and item.kind == "tape" then c = Pal.blue end
    if item and item.kind == "fragment" then c = Pal.gold end
    local text = row.text
    local maxw = list:getWidth() - 20
    local tm = getTextManager()
    -- Long titles are cut rather than run out of the list.
    while #text > 1 and tm:MeasureStringX(UIFont.Small, text) > maxw do
        text = text:sub(1, #text - 2)
    end
    list:drawText(text, 10, y + 5, c[1], c[2], c[3], 1, UIFont.Small)
    if screen and item and item.kind == "book" and Pd.isRead(screen.player, item.entry) then
        list:drawRect(maxw + 6, y + 9, 6, 6, 0.9, Pal.blue[1], Pal.blue[2], Pal.blue[3])
    end
    return y + row.height
end

--- Steps the list's selection, wrapping.
function TREKPaddScreen:step(dir)
    local n = #self.list.items
    if n == 0 then return end
    local i = (self.list.selected or 0) + dir
    if i < 1 then i = n elseif i > n then i = 1 end
    self.list.selected = i
    self.scroll = 0
    U.try("padd.ensure", function() self.list:ensureVisible(i) end)
end

--- Read: a book off the PADD, or a transcript -- which does to the reader
--- what watching the tape would have (TREKReadTape). The screen closes, so
--- the reading hand and the progress bar are what the player sees.
function TREKPaddScreen:onRead()
    local row = self.list.items[self.list.selected]
    local item = row and row.item
    if not item then return end
    local tape = self:tapeOf(item)
    if item.kind == "book" then
        if TREK.PaddUI then TREK.PaddUI.onRead(self.padd, self.player, Pd.key(item.entry)) end
    elseif tape then
        if TREK.PaddUI then TREK.PaddUI.onReadTape(self.padd, self.player, tape) end
    else
        return
    end
    self:close()
end

--- The recording a library row reads, or nil.
function TREKPaddScreen:tapeOf(item)
    if item.kind == "tape" then return item.id end
    if item.kind == "fragment" then
        local tape = C.FragmentTapes and C.FragmentTapes[item.n]
        if tape and Pd.hasTape(self.padd, tape) then return tape end
    end
    return nil
end

---------------------------------------------------------------------------
-- Scrolling
---------------------------------------------------------------------------
function TREKPaddScreen:visibleLines()
    local _, _, _, h = self:textBox()
    return math.max(1, math.floor(h / LINEH))
end

function TREKPaddScreen:maxScroll()
    return math.max(0, #self.lines - self:visibleLines())
end

function TREKPaddScreen:onUp()
    self.scroll = math.max(0, self.scroll - math.max(1, self:visibleLines() - 2))
    self.follow = false
end

function TREKPaddScreen:onDown()
    self.scroll = math.min(self:maxScroll(), self.scroll + math.max(1, self:visibleLines() - 2))
    self.follow = self.scroll >= self:maxScroll()
end

function TREKPaddScreen:onMouseWheel(del)
    self.scroll = math.max(0, math.min(self:maxScroll(), self.scroll + (del > 0 and 3 or -3)))
    self.follow = self.scroll >= self:maxScroll()
    return true
end

--- Wraps the content into drawn lines, when it has changed. A live call
--- follows its newest line; anything else opens at the top.
function TREKPaddScreen:rebuildLines()
    local heading, rows = self:content()
    local x, _, w, _ = self:textBox()
    local sig = self.tab .. "|" .. tostring(self.list.selected) .. "|" .. tostring(heading)
                .. "|" .. tostring(#rows) .. "|" .. tostring(w)
    if sig == self.linesSig then return end
    local live = self.tab == "channel"
    self.linesSig = sig
    self.heading = heading
    self.lines = {}
    local textW = w - WHOW - 8
    for _, r in ipairs(rows) do
        local wrapped = S.wrap(r.text, FONT, r.who and textW or w)
        for i, piece in ipairs(wrapped) do
            table.insert(self.lines, { who = i == 1 and r.who or nil, text = piece,
                                       r = r.r, g = r.g, b = r.b, indent = r.who ~= nil })
        end
    end
    if live then
        self.scroll = self:maxScroll()
        self.follow = true
    else
        self.scroll = 0
    end
end

---------------------------------------------------------------------------
-- Tabs, controller, closing
---------------------------------------------------------------------------
function TREKPaddScreen:setTab(tab)
    if tab == self.tab then return end
    self.tab = tab
    self.list.selected = 1
    self.scroll = 0
    self.linesSig = nil
    self:refreshList()
    self:layout()
end

function TREKPaddScreen:onTab(b)
    self:setTab(b.tab)
end

function TREKPaddScreen:cycleTab(dir)
    local i = 1
    for k, t in ipairs(S.TABS) do if t == self.tab then i = k end end
    i = i + dir
    if i < 1 then i = #S.TABS elseif i > #S.TABS then i = 1 end
    self:setTab(S.TABS[i])
end

function TREKPaddScreen:onJoypadDown(button, joypadData)
    if button == Joypad.LBumper then
        self:cycleTab(-1)
    elseif button == Joypad.RBumper then
        self:cycleTab(1)
    elseif button == Joypad.XButton then
        if self.tab == "channel" then self:onDown() else self:step(1) end
    elseif button == Joypad.YButton then
        if self.tab == "channel" then self:onUp() else self:step(-1) end
    else
        ISPanelJoypad.onJoypadDown(self, button, joypadData)
    end
end

function TREKPaddScreen:onGainJoypadFocus(joypadData)
    ISPanelJoypad.onGainJoypadFocus(self, joypadData)
    if self:getJoypadFocus() then
        self:restoreJoypadFocus(joypadData)
    else
        self:setJoypadFocusTopLeft(joypadData)
    end
end

function TREKPaddScreen:onLoseJoypadFocus(joypadData)
    ISPanelJoypad.onLoseJoypadFocus(self, joypadData)
    self:clearJoypadFocus(joypadData)
end

function TREKPaddScreen:close()
    S.window = nil
    if self.joyfocus then
        U.try("padd.releaseFocus", function() setJoypadFocus(self.playerNum, nil) end)
    end
    self:setVisible(false)
    self:removeFromUIManager()
end

---------------------------------------------------------------------------
-- Drawing
---------------------------------------------------------------------------
function TREKPaddScreen:prerender()
    -- A PADD that is no longer on you is a screen with nothing behind it.
    local still = false
    for _, p in ipairs(Pd.carried(self.player)) do
        if p == self.padd then still = true end
    end
    if not still then
        self:close()
        return
    end

    if self.tab ~= "channel" then
        local n = #self.list.items
        self:refreshList()
        if #self.list.items ~= n then self.linesSig = nil end
    end
    self:layout()
    self:rebuildLines()
    if self.follow then self.scroll = self:maxScroll() end
    self.upBtn.enable = self.scroll > 0
    self.downBtn.enable = self.scroll < self:maxScroll()
    local row = self.list.items[self.list.selected]
    local item = row and row.item
    self.readBtn.enable = item ~= nil
        and ((item.kind == "book" and Pd.readRefusal(self.player, item.entry) == nil)
             or self:tapeOf(item) ~= nil)

    local w, h = self.width, self.height
    self:drawRect(0, 0, w, h, 0.97, 0.008, 0.012, 0.028)
    local function block(x, y, bw, bh, c)
        self:drawRect(x, y, bw, bh, 1, c[1], c[2], c[3])
    end
    local RAD = 24
    H.pill(self, 0, 0, RAD * 2, RAD * 2, Pal.gold, true, true)
    block(RAD, 0, SIDE - RAD, RAD, Pal.gold)
    block(0, RAD, SIDE, 110 - RAD, Pal.gold)
    local title = string.upper(getText("IGUI_TREK_PaddTitle"))
    block(SIDE, 0, math.max(0, self.closeBtn.x - 8 - SIDE), TOPH, Pal.gold)
    local fh = getTextManager():MeasureStringY(UIFont.Medium, title) or 14
    self:drawText(title, SIDE + 12, (TOPH - fh) / 2, 0, 0, 0, 1, UIFont.Medium)
    block(0, 114, SIDE, h - 150 - 114, Pal.orange)
    block(0, h - 150, SIDE, 150 - RAD, Pal.lilac)
    block(RAD, h - RAD, SIDE - RAD, RAD, Pal.lilac)
    H.pill(self, 0, h - RAD * 2, RAD * 2, RAD * 2, Pal.lilac, true, true)
    block(SIDE, h - 16, w - SIDE - 8, 16, Pal.lilac)

    ISPanelJoypad.prerender(self)
end

function TREKPaddScreen:render()
    ISPanelJoypad.render(self)
    local cx = SIDE + PAD
    local x, y, w, h = self:textBox()

    -- The heading over the text, and the channel's own status.
    local head = self.heading or ""
    local hw = self.upBtn.x - PAD - (self.tab == "channel" and cx or x)
    for _, piece in ipairs(S.wrap(head, UIFont.Small, hw)) do
        self:drawText(piece, self.tab == "channel" and cx or x, self.bodyY + 3,
                      Pal.peach[1], Pal.peach[2], Pal.peach[3], 1, UIFont.Small)
        break
    end
    if self.tab == "channel" then
        local status, c = self:channelStatus()
        local sw = self.width - PAD - cx
        local piece = S.wrap(status, UIFont.Small, sw)[1]
        self:drawText(piece, cx, self.optY - PAD - 16, c[1], c[2], c[3], 1, UIFont.Small)
        local call = Cm.call()
        local left = call and call.state == "live" and self:secondsLeft(call)
        if left then
            -- A timed node's clock is on screen, not implied (PADD.md 12.5).
            self:drawTextRight(getText("IGUI_TREK_CommsClock", tostring(left)),
                               self.width - PAD, self.optY - PAD - 16,
                               Pal.red[1], Pal.red[2], Pal.red[3], 1, UIFont.Small)
        end
    end

    -- The transcript.
    self:drawRectBorder(x - 4, y - 4, w + 8, h + 8, 0.5, Pal.lilac[1], Pal.lilac[2], Pal.lilac[3])
    local fit = self:visibleLines()
    for i = 1, fit do
        local ln = self.lines[self.scroll + i]
        if not ln then break end
        local ly = y + (i - 1) * LINEH
        if ln.who then
            local who = S.wrap(string.upper(ln.who), UIFont.Small, WHOW - 6)[1]
            self:drawText(who, x, ly + 3, ln.r, ln.g, ln.b, 1, UIFont.Small)
        end
        self:drawText(ln.text, ln.indent and (x + WHOW + 8) or x, ly, ln.r, ln.g, ln.b, 1, FONT)
    end
    if #self.lines == 0 and self.tab == "channel" then
        self:drawText(getText("IGUI_TREK_CommsNothing"), x, y,
                      Pal.dim[1] * 1.5, Pal.dim[2] * 1.5, Pal.dim[3] * 1.5, 1, UIFont.Small)
    end

    if self.joyfocus then
        self:drawTextRight(string.upper(getText("IGUI_TREK_PaddJoypadHint")),
                           self.width - 22, self.height - 15, 0, 0, 0, 1, UIFont.Small)
    end
end

---------------------------------------------------------------------------
-- Opening it
---------------------------------------------------------------------------
function S.open(player, padd)
    if not player then return nil end
    padd = padd or Pd.carried(player)[1]
    if not padd then
        U.note(player, getText("IGUI_TREK_CommsNoPadd"), 255, 170, 90)
        return nil
    end
    if S.window then U.try("padd.closeOld", function() S.window:close() end) end
    local w = U.try("padd.open", function()
        local sw, sh = S.size()
        local vw = U.try("padd.vw", function() return getCore():getScreenWidth() end) or sw + 40
        local vh = U.try("padd.vh", function() return getCore():getScreenHeight() end) or sh + 40
        local win = TREKPaddScreen:new(math.floor((vw - sw) / 2), math.floor((vh - sh) / 2),
                                       player, padd)
        win:initialise()
        win:instantiate()
        win:addToUIManager()
        return win
    end)
    if not w then return nil end
    S.window = w
    U.try("padd.focus", function()
        if JoypadState.players[w.playerNum + 1] then setJoypadFocus(w.playerNum, w) end
    end)
    return w
end

--- Opens the screen, or closes it if it is already open.
function S.toggle(player)
    if S.window then
        S.window:close()
        return
    end
    S.open(player)
end

---------------------------------------------------------------------------
-- The key (PADD.md 12.7: a story surface nobody can find does not get
-- opened). Build 42's own mod options, so it is rebindable in the game's
-- Options -> Mods page. A controller reaches the same screen from the
-- PADD's own menu: select it, press A, Open PADD.
---------------------------------------------------------------------------
S.keyOption = nil
U.try("padd.keybind", function()
    if not (PZAPI and PZAPI.ModOptions) then return end
    local opts = PZAPI.ModOptions:create("TrekShuttle", getText("IGUI_TREK_Name"))
    S.keyOption = opts:addKeyBind("paddScreen", getText("IGUI_TREK_PaddKey"),
                                  Keyboard.KEY_K, getText("IGUI_TREK_PaddKeyTip"))
    -- Vanilla reads ModOptions.ini when its options screen is built, which is
    -- before any mod Lua exists; read it again now that this option does, or
    -- a rebound key only takes effect after the options screen is opened.
    PZAPI.ModOptions:load()
end)

Events.OnKeyPressed.Add(function(key)
    if not S.keyOption then return end
    local want = U.try("padd.keyValue", function() return S.keyOption:getValue() end)
    if not want or want == 0 or key ~= want then return end
    local player = U.player(0)
    if not player then return end
    S.toggle(player)
end)

---------------------------------------------------------------------------
-- What the channel says when the screen is shut
---------------------------------------------------------------------------
-- A hail is a note and a chirp whether or not anybody has a PADD open: a
-- pop-up mid-fight is one nobody reads, and a call that waits on the PADD
-- for a quarter of an hour is one nobody misses (the probe console's rule).
Net.onClient("commsRing", function(args)
    local player = U.player(0)
    if not player then return end
    U.note(player, getText("IGUI_TREK_CommsRingNote", Cm.title(args.thread)), 255, 200, 90)
    U.try("comms.chirp", function() player:playSoundLocal("TREK_TricorderChirp") end)
end)

Net.onClient("commsAnswered", function(args)
    local player = U.player(0)
    if not player then return end
    if args.by == nil then return end
    U.note(player, getText("IGUI_TREK_CommsAnsweredNote", tostring(args.by)), 150, 200, 255)
end)

Net.onClient("commsReleased", function(args)
    local player = U.player(0)
    if not player then return end
    U.note(player, getText("IGUI_TREK_CommsReleasedNote"), 255, 200, 90)
end)

Net.onClient("commsEnded", function(args)
    local player = U.player(0)
    if not player then return end
    local key = args.outcome == "missed" and "IGUI_TREK_CommsMissedNote"
                or "IGUI_TREK_CommsCutNote"
    U.note(player, getText(key, Cm.title(args.thread)), 255, 120, 90)
end)

Net.onClient("commsNoAnswer", function()
    local player = U.player(0)
    if not player then return end
    U.note(player, getText("IGUI_TREK_CommsNoAnswerNote"), 180, 180, 200)
end)

return S
