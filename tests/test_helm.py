"""Runs the mod's own panels under a real Lua VM with the vanilla UI stubbed.

A UI bug is the most expensive kind this mod can ship. prerender and render
run every frame, so one nil there is not one error -- it is sixty a second,
each with a Java stack trace, for as long as the helm is open. And a layout
that only looks wrong ("the buttons are off the bottom", "the label runs out of
the panel") can otherwise only be found by opening the game.

This drives the real TREK_Helm.lua -- and the tricorder's contact plot from
TREK_MedKit.lua -- through construction, several frames of drawing and every
control, against stubs of ISPanel, ISButton and the rest that record each draw
call. It checks:

  * nothing throws, in any state -- shields up and down, with and without
    the artwork textures installed
  * every draw lands inside the panel with non-negative size
  * every text label fits the width it is drawn in (estimated)
  * the controls ask for the right changes, and the defaults are right
  * a player who is not crew is told so on the console

The helm never writes the ship itself: every control is a request. Here the
request is applied straight to the state, the way single player's in-process
server would (tests/test_multiplayer.py plays the real round trip).

    python tests/test_helm.py
"""
import json
import os
import re
import sys
from lupa import LuaRuntime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, "TrekShuttle", "42")
LUA = os.path.join(MOD, "media", "lua").replace(os.sep, "/")
UI = os.path.join(MOD, "media", "ui")
IG = json.load(open(os.path.join(MOD, "media", "lua", "shared", "Translate",
                                 "EN", "IG_UI.json"), encoding="utf-8"))
# Everything a panel can getText: the PADD's screen draws the channel's lines
# (Print_Text, tools/gen_comms.py) and tapes' (Recorded_Media) as well as its
# own labels, and a harness that only knew IG_UI would call every one of them
# missing.
TEXT = dict(IG)
for _cat in ("Print_Text", "Recorded_Media"):
    _path = os.path.join(MOD, "media", "lua", "shared", "Translate", "EN", _cat + ".json")
    if os.path.isfile(_path):
        TEXT.update(json.load(open(_path, encoding="utf-8")))

# Average glyph widths for PZ's UI fonts at 1x. Deliberately a little generous:
# a label that only fits under an optimistic estimate will not fit in game.
CHAR_W = {1: 6.5, 2: 9.0, 3: 11.0}

failures = []
texture_files = {"on": True}


def make_lua():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(f'package.path = "{LUA}/shared/?.lua;{LUA}/client/?.lua;" .. package.path')

    missing_keys = []

    def get_text(key, *args):
        if key not in TEXT:
            missing_keys.append(key)
            return key
        text = TEXT[key]
        for i, a in enumerate(args, 1):
            text = text.replace(f"%{i}", str(a))
        return text

    def get_texture(path):
        if not texture_files["on"]:
            return None
        return path if os.path.isfile(os.path.join(MOD, path)) else None

    def measure_x(_, font, text):
        return int(len(text or "") * CHAR_W.get(font, 6.5))

    g = lua.globals()
    g.py_getText = get_text
    g.py_getTexture = get_texture
    g.py_measureX = measure_x

    lua.execute(r"""
        _G.unpack = _G.unpack or table.unpack
        _G.isServer = function() return false end
        _G.isClient = function() return false end
        _G.Events = setmetatable({}, { __index = function(t, k)
            local ev = { Add = function() end }
            rawset(t, k, ev)
            return ev
        end })
        _G.print = function(...) end
        _G.instanceof = function() return false end
        _G.getCellSizeInSquares = function() return 256 end
        local md = {}
        _G.ModData = { getOrCreate = function(k) md[k] = md[k] or {}; return md[k] end }
        _G.getPlayer = function() return nil end
        _G.getSpecificPlayer = function() return nil end
        _G.getCell = function() return nil end
        _G.UIFont = { Small = 1, Medium = 2, Large = 3, NewSmall = 1 }
        _G.getText = function(key, ...) return py_getText(key, ...) end
        _G.getTexture = function(p) return py_getTexture(p) end
        local tm = {
            MeasureStringX = function(self, font, text) return py_measureX(self, font, text) end,
            MeasureStringY = function() return 14 end,
        }
        _G.getTextManager = function() return tm end

        -- Every draw call is recorded against the element that made it.
        draws = {}
        local function rec(el, kind, x, y, w, h, extra)
            -- Identity is decided here, in Lua: every access to a table from
            -- Python yields a fresh proxy, so a Python-side comparison never
            -- matches and the panel would be offset by its own position.
            table.insert(draws, { el = el, own = rawequal(el, win), kind = kind,
                                  x = x, y = y, w = w, h = h, extra = extra })
        end

        ISUIElement = {}
        ISUIElement.__index = ISUIElement
        function ISUIElement:derive(name)
            local cls = {}
            setmetatable(cls, self)
            cls.__index = cls
            cls.Type = name
            return cls
        end
        function ISUIElement:new(x, y, w, h)
            local o = { x = x, y = y, width = w, height = h, children = {} }
            setmetatable(o, self)
            return o
        end
        function ISUIElement:initialise() end
        function ISUIElement:instantiate() end
        function ISUIElement:createChildren() end
        function ISUIElement:render() end
        function ISUIElement:prerender() end
        function ISUIElement:addChild(c) c.parent = self; table.insert(self.children, c) end
        function ISUIElement:getWidth() return self.width end
        function ISUIElement:isMouseOver() return self.mouseOver end
        function ISUIElement:setVisible(v) self.visible = v end
        function ISUIElement:removeFromUIManager() self.removed = true end
        function ISUIElement:drawRect(x, y, w, h, a, r, g, b)
            rec(self, "rect", x, y, w, h, { a, r, g, b })
        end
        -- Recorded apart from a filled rect. They were one kind until the
        -- tricorder's crystal traces needed telling from its lifesign dots,
        -- and a harness that cannot tell an outline from a block cannot see
        -- the difference between the two things on that plot.
        function ISUIElement:drawRectBorder(x, y, w, h, a, r, g, b)
            rec(self, "rectborder", x, y, w, h, { a, r, g, b })
        end
        function ISUIElement:drawTextureScaled(t, x, y, w, h, a, r, g, b)
            if t == nil then error("drawTextureScaled with a nil texture") end
            rec(self, "tex", x, y, w, h, { a, r, g, b })
        end
        function ISUIElement:drawText(s, x, y, r, g, b, a, font)
            if s == nil then error("drawText with nil text") end
            rec(self, "text", x, y, getTextManager():MeasureStringX(font, s), 14, s)
        end
        function ISUIElement:drawTextCentre(s, x, y, r, g, b, a, font)
            if s == nil then error("drawTextCentre with nil text") end
            local w = getTextManager():MeasureStringX(font, s)
            rec(self, "text", x - w / 2, y, w, 14, s)
        end
        function ISUIElement:drawTextRight(s, x, y, r, g, b, a, font)
            if s == nil then error("drawTextRight with nil text") end
            local w = getTextManager():MeasureStringX(font, s)
            rec(self, "text", x - w, y, w, 14, s)
        end

        ISPanel = ISUIElement:derive("ISPanel")
        function ISPanel:new(x, y, w, h)
            local o = ISUIElement.new(self, x, y, w, h)
            o.background = true
            o.moveWithMouse = false
            return o
        end

        -- A faithful-enough ISPanelJoypad: rows of buttons, a focus index,
        -- A presses the focused button and B presses the one set for B.
        Joypad = { AButton = 0, BButton = 1, XButton = 2, YButton = 3,
                   LBumper = 4, RBumper = 5 }
        JoypadState = { players = {} }
        focusLog = {}
        function setJoypadFocus(playerNum, target)
            table.insert(focusLog, target or "nothing")
        end
        ISPanelJoypad = ISUIElement:derive("ISPanelJoypad")
        function ISPanelJoypad:new(x, y, w, h)
            local o = ISUIElement.new(self, x, y, w, h)
            o.joypadButtonsY = {}
            o.joypadIndexY, o.joypadIndex = 0, 0
            return o
        end
        function ISPanelJoypad:insertNewLineOfButtons(...)
            table.insert(self.joypadButtonsY, { ... })
        end
        function ISPanelJoypad:insertNewListOfButtons(list)
            table.insert(self.joypadButtonsY, list)
        end
        function ISPanelJoypad:setISButtonForB(b) self.ISButtonB = b end
        function ISPanelJoypad:getJoypadFocus()
            local row = self.joypadButtonsY[self.joypadIndexY]
            return row and row[self.joypadIndex]
        end
        function ISPanelJoypad:setJoypadFocus(child)
            for y, row in ipairs(self.joypadButtonsY) do
                for x, b in ipairs(row) do
                    if b == child then
                        self:clearJoypadFocus()
                        self.joypadIndexY, self.joypadIndex = y, x
                        b.joypadFocused = true
                        return true
                    end
                end
            end
            return false
        end
        function ISPanelJoypad:setJoypadFocusTopLeft()
            return self:setJoypadFocus(self.joypadButtonsY[1][1])
        end
        function ISPanelJoypad:restoreJoypadFocus()
            local c = self:getJoypadFocus()
            if c then c.joypadFocused = true end
        end
        function ISPanelJoypad:clearJoypadFocus()
            for _, row in ipairs(self.joypadButtonsY) do
                for _, b in ipairs(row) do b.joypadFocused = false end
            end
        end
        function ISPanelJoypad:onJoypadDown(button)
            local c = self:getJoypadFocus()
            if button == Joypad.AButton and c then c:click()
            elseif button == Joypad.BButton and self.ISButtonB then self.ISButtonB:click() end
        end
        function ISPanelJoypad:onGainJoypadFocus(jd) self.joyfocus = jd end
        function ISPanelJoypad:onLoseJoypadFocus(jd) self.joyfocus = nil end

        ISWorldMap_instance = {
            visible = true,
            isVisible = function(self) return self.visible end,
            mapAPI = {
                getCenterWorldX = function() return 10612.6 end,
                getCenterWorldY = function() return 9412.2 end,
            },
        }

        ISButton = ISUIElement:derive("ISButton")
        function ISButton:new(x, y, w, h, title, target, onclick)
            local o = ISUIElement.new(self, x, y, w, h)
            o.title = title
            o.target = target
            o.onclick = onclick
            o.enable = true
            o.pressed = false
            o.mouseOver = false
            o.onClickArgs = {}
            return o
        end
        function ISButton:click()
            self.onclick(self.target, self)
        end

        ISScrollingListBox = ISUIElement:derive("ISScrollingListBox")
        function ISScrollingListBox:new(x, y, w, h)
            local o = ISUIElement.new(self, x, y, w, h)
            o.items = {}
            o.itemheight = 20
            o.selected = 0
            return o
        end
        function ISScrollingListBox:ensureVisible() end
        function ISScrollingListBox:clear() self.items = {} end
        function ISScrollingListBox:addItem(name, item)
            local row = { text = name, item = item, height = self.itemheight,
                          itemindex = #self.items + 1 }
            table.insert(self.items, row)
            return row
        end

        ISRichTextPanel = ISUIElement:derive("ISRichTextPanel")
        function ISRichTextPanel:new(x, y, w, h)
            return ISUIElement.new(self, x, y, w, h)
        end
        function ISRichTextPanel:setText(t) self.text = t end
        function ISRichTextPanel:paginate() end

        -- The replicator's search box. The engine's takes its initial text
        -- first, so this does too: getting that argument order wrong is a
        -- mistake worth failing on here rather than in game.
        ISTextEntryBox = ISUIElement:derive("ISTextEntryBox")
        function ISTextEntryBox:new(text, x, y, w, h)
            local o = ISUIElement.new(self, x, y, w, h)
            o.text = text or ""
            return o
        end
        function ISTextEntryBox:getText() return self.text end
        function ISTextEntryBox:setClearButton() end
        function ISTextEntryBox:setPlaceholderText(s) self.placeholder = s end
        function ISTextEntryBox:setText(s)
            self.text = s
            if self.onTextChange then self:onTextChange() end
        end

        -- The item catalogue the replicator reads. Deliberately more rows
        -- than a screen holds and with a name long enough to run out of its
        -- column, because "the list is fine" is easy to believe with four
        -- short entries in it.
        local catalogue = {}
        local categories = { "FirstAid", "Tool", "Food", "Weapon" }
        local function scriptItem(full, name, category, weight, flags)
            flags = flags or {}
            local it = { full = full, name = name, category = category,
                         weight = weight, obsolete = flags.obsolete == true,
                         hidden = flags.hidden == true }
            function it:getFullName() return self.full end
            function it:getDisplayName() return self.name end
            function it:getDisplayCategory() return self.category end
            function it:getModuleName() return (self.full:match("^(.-)%.")) end
            function it:getActualWeight() return self.weight end
            function it:getObsolete() return self.obsolete end
            function it:isHidden() return self.hidden end
            function it:getNormalTexture() return nil end
            table.insert(catalogue, it)
        end
        for i = 1, 120 do
            scriptItem("Base.Thing" .. i, "Thing number " .. i,
                       categories[(i % 4) + 1], (i % 7) * 0.4)
        end
        scriptItem("Base.LongOne",
                   "Extraordinarily Long Item Name That Will Not Fit In Its Column",
                   "Tool", 1.5)
        scriptItem("TrekShuttle.TrekPhaser", "Phaser", "Weapon", 0.6)
        _G.getAllItems = function()
            local list = catalogue
            return { size = function() return #list end,
                     get = function(_, i) return list[i + 1] end }
        end
        _G.SandboxVars = { TrekShuttle = {} }
        _G.instanceof = function() return false end

        TREK = TREK or {}
        require "TREK/TREK_Config"
        require "TREK/TREK_Util"
        require "TREK/TREK_Ship"
        sent = {}
        TREK.Core = {
            footprintArea = function() return 15 end,
            send = function(player, cmd, args)
                table.insert(sent, { cmd = cmd, args = args })
                local s = TREK.Util.state()
                if cmd == "setShields" then s.shields = args.up end
            end,
        }
        TREK.Travel = {
            addBookmark = function() end, setDestination = function() end,
            removeBookmark = function() return true end, descend = function() end,
            onMapPick = function(x, y) picked = { x = x, y = y } end,
        }
        require "TREK/TREK_Helm"

        -- The tricorder's panel lives in TREK_MedKit, which pulls in the
        -- client's Core. Seeding package.loaded keeps the stub above rather
        -- than dragging the whole transporter in behind it.
        package.loaded["TREK/TREK_Core"] = TREK.Core
        _G.getPlayerScreenLeft = function() return 0 end
        _G.getPlayerScreenTop = function() return 0 end
        _G.updateJoypadFocus = function() end
        _G.ISWorldObjectContextMenu = { setTest = function() return true end,
                                        addToolTip = function() return {} end }
        _G.getTimestampMs = function() return 1000000 end
        require "TREK/TREK_MedKit"
        require "TREK/TREK_ReplicatorUI"
        require "TREK/TREK_EMHUI"
        require "TREK/TREK_ProbeUI"

        haloNotes = {}
        player = { setHaloNote = function(self, text) table.insert(haloNotes, text) end,
                   getPlayerNum = function() return 0 end,
                   getUsername = function() return "doctorless" end,
                   getDisplayName = function() return "doctorless" end,
                   isDead = function() return false end }

        -- A body, for the EMH panel. Enough BodyPart and BodyDamage for
        -- TREK_EMH.findings to walk Med.TREATMENTS and Med.SKIN over it and
        -- come back with something to draw: the panel's findings list is the
        -- half of it that is easiest to get wrong and impossible to see
        -- without a render.
        do
            local parts = {}
            for i = 1, 17 do
                local p = { health = 100, bleed = false, deep = 0, infW = false,
                            wound = 0, burn = 0, frac = 0, pain = 0, stiff = 0,
                            cut = false, cutT = 0, scr = false, scrT = 0,
                            sti = false, stiT = 0, band = false, bandL = 0,
                            bite = false, biteT = 0, glass = false, bullet = false,
                            infected = false, fake = false, index = i - 1 }
                function p:getHealth() return self.health end
                function p:SetHealth(v) self.health = v end
                function p:bleeding() return self.bleed end
                function p:setBleeding(v) self.bleed = v end
                function p:setBleedingTime() end
                function p:deepWounded() return self.deep > 0 end
                function p:setDeepWounded() end
                function p:getDeepWoundTime() return self.deep end
                function p:setDeepWoundTime(v) self.deep = v end
                function p:isInfectedWound() return self.infW end
                function p:setInfectedWound(v) self.infW = v end
                function p:getWoundInfectionLevel() return self.wound end
                function p:setWoundInfectionLevel(v) self.wound = v end
                function p:getBurnTime() return self.burn end
                function p:setBurnTime(v) self.burn = v end
                function p:isNeedBurnWash() return false end
                function p:setNeedBurnWash() end
                function p:getFractureTime() return self.frac end
                function p:setFractureTime(v) self.frac = v end
                function p:isSplint() return false end
                function p:setSplint() end
                function p:getAdditionalPain() return self.pain end
                function p:setAdditionalPain(v) self.pain = v end
                function p:getStiffness() return self.stiff end
                function p:setStiffness(v) self.stiff = v end
                function p:isCut() return self.cut end
                function p:setCut(v) self.cut = v end
                function p:getCutTime() return self.cutT end
                function p:setCutTime(v) self.cutT = v end
                function p:scratched() return self.scr end
                function p:setScratched(v) self.scr = v end
                function p:getScratchTime() return self.scrT end
                function p:setScratchTime(v) self.scrT = v end
                function p:stitched() return self.sti end
                function p:setStitched(v) self.sti = v end
                function p:getStitchTime() return self.stiT end
                function p:setStitchTime(v) self.stiT = v end
                function p:bandaged() return self.band end
                function p:getBandageLife() return self.bandL end
                function p:bitten() return self.bite end
                function p:SetBitten(v) self.bite = v end
                function p:getBiteTime() return self.biteT end
                function p:setBiteTime(v) self.biteT = v end
                function p:haveGlass() return self.glass end
                function p:setHaveGlass(v) self.glass = v end
                function p:haveBullet() return self.bullet end
                function p:setHaveBullet(v) self.bullet = v end
                function p:IsInfected() return self.infected end
                function p:SetInfected(v) self.infected = v end
                function p:IsFakeInfected() return self.fake end
                function p:SetFakeInfected(v) self.fake = v end
                function p:getIndex() return self.index end
                table.insert(parts, p)
            end
            bodyParts = parts
            local damage = { infected = false }
            function damage:getBodyParts()
                return { size = function() return #parts end,
                         get = function(_, i) return parts[i + 1] end }
            end
            function damage:isInfected() return self.infected end
            function damage:setInfected(v) self.infected = v end
            function damage:SetBandaged() end
            player.getBodyDamage = function() return damage end
            playerDamage = damage
        end

        -- Who is aboard, from the EMH panel's point of view. One player in
        -- single player, which is the shape the patient control has to cope
        -- with -- a stepper over a list of one must not be live.
        _G.IsoPlayer = { getPlayers = function()
            return { size = function() return 1 end,
                     get = function() return player end }
        end }

        -- Standing at the replicator's berth. The panel closes itself when
        -- nobody is at the machine, so a player stub with no position would
        -- shut the window on its first frame and every check after it would
        -- be drawing nothing.
        do
            local ox, oy = TREK.Replicator.spot()
            local bx, by = TREK.Util.at(ox, oy)
            player.getX = function() return bx + 0.5 end
            player.getY = function() return by + 0.5 end
            player.getZ = function() return TREK.Config.CabinZ end
        end

        -- The ship's own patterns. In a game this happens on the authority
        -- when the world's data loads; nothing fires events in here, and a
        -- panel with an empty pattern set would draw every row greyed.
        TREK.Replicator.seedDefaults()

        -- There is no cabin in this harness, so the dilithium chamber answers
        -- nothing and the panel draws "no spare crystals". That is a real
        -- state -- it is what a ship with a flat reserve looks like -- and it
        -- is the one the layout checks below are drawn against.

        function frame(win)
            win:prerender()
            win:render()
            for _, c in ipairs(win.children) do
                c:prerender()
                c:render()
            end
        end
    """)
    return lua, missing_keys


def run_frames(lua, label, n=3):
    """Draws n frames, returning the draw log, recording any Lua error."""
    lua.execute("draws = {}")
    try:
        for _ in range(n):
            lua.eval("frame")(lua.globals().win)
    except Exception as exc:                                  # noqa: BLE001
        failures.append(f"{label}: a frame threw -- {exc}")
        return []
    d = lua.globals().draws
    return [d[i] for i in range(1, len(d) + 1)]


def check_bounds(lua, draws, label):
    win = lua.globals().win
    W, H = float(win.width), float(win.height)
    for d in draws:
        el = d.el
        # Children draw in their own coordinates; place them in the panel's.
        ox = 0.0 if d.own else float(el.x)
        oy = 0.0 if d.own else float(el.y)
        x, y, w, h = ox + float(d.x), oy + float(d.y), float(d.w), float(d.h)
        what = d.extra if d.kind == "text" else d.kind
        if w < 0 or h < 0:
            failures.append(f"{label}: {what} drawn with negative size {w:.0f}x{h:.0f}")
        if x < -0.5 or y < -0.5 or x + w > W + 0.5 or y + h > H + 0.5:
            failures.append(f"{label}: {what!r} at {x:.0f},{y:.0f} {w:.0f}x{h:.0f} "
                            f"leaves the {W:.0f}x{H:.0f} panel")
        if d.kind == "text" and not d.own:
            if float(d.w) > float(el.width) + 0.5:
                failures.append(f"{label}: label {what!r} ({float(d.w):.0f}px) is wider "
                                f"than its {float(el.width):.0f}px button")
        if d.kind in ("rect", "rectborder", "tex"):
            for v in list(d.extra.values()):
                if v is not None and not (0 <= float(v) <= 1.0001):
                    failures.append(f"{label}: {d.kind} colour/alpha {v} is outside 0..1")
                    break



def padd_screen():
    """The PADD's screen: every state of the channel, the history, the
    library, at the Deck's size, with a controller.

    The states are the point. The channel alone is idle, ringing, held by
    you, held by somebody else, or open with nobody on it, and each has its
    own control, its own status line and its own reason to draw something
    that runs out of its box.
    """
    texture_files["on"] = True
    lua, missing = make_lua()
    lua.execute(r"""
        package.loaded["TimedActions/ISBaseTimedAction"] = true
        ISBaseTimedAction = ISBaseTimedAction or {}
        ISBaseTimedAction.__index = ISBaseTimedAction
        function ISBaseTimedAction:derive(name)
            local cls = setmetatable({}, self); cls.__index = cls; cls.Type = name
            return cls
        end
        require "TREK/TREK_Tapes"
        require "TREK/TREK_PaddScreen"

        -- A PADD, in this player's pockets, with two books and a tape on it.
        padd = { md = {}, id = 7001 }
        function padd:getFullType() return TREK.Config.PaddItem end
        function padd:getModData() return self.md end
        function padd:getID() return self.id end
        padd.md[TREK.Config.PaddLibraryKey] = {
            { type = "Base.BookCarpentry1", name = "Carpentry for Beginners",
              kind = "skill", skill = "Carpentry", level = 1, maxLevel = 2,
              pages = 220 },
            { type = "Base.Book", name = "An Extraordinarily Long Novel Title That Will Not Fit In The List",
              kind = "literature", pages = 0, md = { literatureTitle = "Long" } },
        }
        padd.md[TREK.Config.PaddTapesKey] = { "TREK_TalentNight" }
        carried = { padd }
        player.getInventory = function()
            return { getAllTypeRecurse = function()
                return { size = function() return #carried end,
                         get = function(_, i) return carried[i + 1] end }
            end, containsID = function() return true end, contains = function() return true end }
        end
        player.getAlreadyReadPages = function() return 0 end
        player.isLiteratureRead = function() return false end
        player.hasTrait = function() return false end
        player.getPerkLevel = function() return 0 end
        _G.SkillBook = { Carpentry = { perk = { getName = function() return "Carpentry" end } } }

        sent = {}
        TREK.Net.send = function(p, cmd, args)
            table.insert(sent, { cmd = cmd, args = args }); return true
        end
        reads = {}
        TREK.PaddUI = {
            onRead = function(p, pl, key) table.insert(reads, "book:" .. key) end,
            onReadTape = function(p, pl, id) table.insert(reads, "tape:" .. id) end,
        }
        clock = 1000000
        _G.getTimestampMs = function() return clock end
    """)
    lua.execute("win = TREKPaddScreen:new(0, 0, player, padd); win:createChildren()")
    win = lua.globals().win
    g = lua.globals()
    W, H = float(win.width), float(win.height)
    if W > 1240 or H > 760:
        failures.append(f"padd screen: {W:.0f}x{H:.0f} does not fit a Steam Deck's "
                        f"1280x800 with room round it")

    texts = lambda d: [str(x.extra) for x in d if x.kind == "text"]

    def state(label):
        d = run_frames(lua, f"padd screen, {label}")
        check_bounds(lua, d, f"padd screen, {label}")
        return d

    # --- the channel, idle, never called -----------------------------------
    d = state("channel, never called")
    if not win.actionBtn.visible or win.actionBtn.title != TEXT["IGUI_TREK_CommsHail"]:
        failures.append("padd screen: an idle channel offers no Hail")
    if any(b.visible for b in (win.optBtns[i] for i in range(1, 5))):
        failures.append("padd screen: an idle channel shows option buttons")
    if TEXT["IGUI_TREK_CommsNothing"] not in texts(d):
        failures.append("padd screen: a PADD that has never been called is an "
                        "empty box; it has to say so (PADD.md 12.7)")
    lua.execute("win.actionBtn:click()")
    if str(lua.eval("sent[#sent] and sent[#sent].cmd")) != "commsHail":
        failures.append("padd screen: Hail does not hail")

    # --- ringing -----------------------------------------------------------
    lua.execute("""
        local d = TREK.Comms.store()
        d.call = { id = "call:1", thread = "FIRST", state = "ringing", steps = {} }
    """)
    d = state("channel, ringing")
    if win.actionBtn.title != TEXT["IGUI_TREK_CommsAnswer"]:
        failures.append(f"padd screen: a ringing call offers {win.actionBtn.title!r}, "
                        f"not Answer")
    if not win.actionBtn.visible:
        failures.append("padd screen: a ringing call shows no Answer button")
    if TEXT["IGUI_TREK_CommsNothing"] in texts(d):
        failures.append("padd screen: while she is calling, the screen says she "
                        "has not called")
    if not any(t.startswith(TEXT["IGUI_TREK_CommsRingingBody"][:20]) for t in texts(d)):
        failures.append("padd screen: a ringing call does not say to press Answer")
    lua.execute("win.actionBtn:click()")
    if str(lua.eval("sent[#sent].cmd")) != "commsAnswer" \
            or str(lua.eval("sent[#sent].args.id")) != "call:1":
        failures.append("padd screen: Answer does not answer this call by its id")

    # --- held by this player, on a timed node, every option offered ---------
    lua.execute("""
        local d = TREK.Comms.store()
        d.call = { id = "call:1", thread = "FIRST", state = "live",
                   holder = player:getUsername(), holderName = "Doc",
                   node = "FIRST_03", nodeSerial = 4, timeout = 60,
                   avail = { 1, 2, 3, 4 }, a1 = "Doc",
                   steps = { { n = "FIRST_01", o = 0 }, { n = "FIRST_01S", o = 1 },
                             { n = "FIRST_02", o = 3 }, { n = "FIRST_03" } } }
    """)
    d = state("channel, holding a timed node")
    shown = [win.optBtns[i] for i in range(1, 5) if win.optBtns[i].visible]
    if len(shown) != 4:
        failures.append(f"padd screen: the holder is offered {len(shown)} of 4 options")
    if win.actionBtn.visible:
        failures.append("padd screen: the holder is shown Answer as well as the options")
    clock_prefix = TEXT["IGUI_TREK_CommsClock"].split("%1")[0]
    if not any(t.startswith(clock_prefix) for t in texts(d)):
        failures.append("padd screen: a timed node's clock is not on screen "
                        "(PADD.md 12.5)")
    if not any(TEXT["Print_Text_TREK_COMM_FIRST_02_L1"] in t for t in texts(d)) and \
       not any(t and t in TEXT["Print_Text_TREK_COMM_FIRST_02_L1"] for t in texts(d)):
        failures.append("padd screen: the live transcript does not show what "
                        "Shepard said")
    lua.execute("win.optBtns[3]:click()")
    if int(lua.eval("sent[#sent].args.option")) != 3 \
            or str(lua.eval("sent[#sent].args.node")) != "FIRST_03":
        failures.append("padd screen: an option button does not send its own "
                        "option on the live node")
    lua.execute("clock = clock + 61000")
    d = state("channel, the clock run out")
    if not any(t == clock_prefix + "0s" or t.startswith(clock_prefix + "0")
               for t in texts(d)):
        failures.append("padd screen: the clock does not count down to nothing")

    # Only what the server offered: a holder with one option sees one button.
    lua.execute("TREK.Comms.store().call.avail = { 2 }")
    state("channel, one option")
    shown = [i for i in range(1, 5) if win.optBtns[i].visible]
    if shown != [1] or int(lua.eval("win.optBtns[1].option")) != 2:
        failures.append("padd screen: the options shown are not the ones the "
                        "server offered")
    # The first button is option 2 here -- the one place a slot and an option
    # differ, so the only click that can tell which one is sent.
    lua.execute("win.optBtns[1]:click()")
    if int(lua.eval("sent[#sent].args.option")) != 2:
        failures.append("padd screen: a button sends its position on screen, "
                        "not the option the server offered there")

    # --- somebody else holds it --------------------------------------------
    lua.execute("""
        local c = TREK.Comms.store().call
        c.holder, c.holderName, c.avail = "somebody", "Ensign Maren Very-Long-Surname", { 1, 2 }
    """)
    d = state("channel, somebody else speaking")
    if any(win.optBtns[i].visible for i in range(1, 5)) or win.actionBtn.visible:
        failures.append("padd screen: a player who does not hold the call can press something")
    if not any("Ensign Maren" in t for t in texts(d)):
        failures.append("padd screen: nobody is told who is speaking (COMMS.md 2)")

    # --- open, nobody on it --------------------------------------------------
    lua.execute("TREK.Comms.store().call.holder = nil")
    state("channel, open")
    if win.actionBtn.title != TEXT["IGUI_TREK_CommsTake"]:
        failures.append("padd screen: a dropped call cannot be taken up")

    # --- a long transcript scrolls, and follows the newest line ---------------
    lua.execute("""
        local c = TREK.Comms.store().call
        c.holder = player:getUsername()
        c.steps = {}
        for _, n in ipairs({ "FIRST_01", "FIRST_02R", "FIRST_02", "FIRST_03",
                             "FIRST_04N", "FIRST_05", "FIRST_06U", "FIRST_06",
                             "FIRST_06Q", "FIRST_07" }) do
            table.insert(c.steps, { n = n, o = 1 })
        end
        c.steps[#c.steps].o = nil
        c.node, c.avail, c.timeout = "FIRST_07", { 2, 3 }, nil
        c.nodeSerial = 9
    """)
    state("channel, a long call")
    if int(lua.eval("win:maxScroll()")) <= 0:
        failures.append("padd screen: a ten-node call fits without scrolling -- "
                        "the box is not being measured")
    if int(lua.eval("win.scroll")) != int(lua.eval("win:maxScroll()")):
        failures.append("padd screen: a live call does not follow its newest line")
    lua.execute("win.upBtn:click()")
    after_up = int(lua.eval("win.scroll"))
    state("channel, scrolled up")
    if after_up >= int(lua.eval("win:maxScroll()")) or int(lua.eval("win.scroll")) != after_up:
        failures.append("padd screen: scrolling up is undone by the next frame")

    # --- the history ------------------------------------------------------------
    lua.execute("""
        local d = TREK.Comms.store()
        d.call = nil
        local log = TREK.Comms.log()
        log.rows = {
            { id = "call:1", t = "FIRST", d = 7, h = "Doc", out = "done", a1 = "Doc",
              s = { { n = "FIRST_01", o = 1 }, { n = "FIRST_02", o = 1 },
                    { n = "FIRST_03", o = 3 }, { n = "FIRST_04X", o = 1 },
                    { n = "FIRST_05", o = 1 }, { n = "FIRST_06", o = 1 },
                    { n = "FIRST_07", o = 2 }, { n = "FIRST_08" } } },
            { id = "call:2", t = "THANKS", d = 9, out = "missed", s = {} },
        }
    """)
    d = state("channel, idle after calls")
    last = TEXT["IGUI_TREK_CommsLast"].split("%1")[0]
    if not any(t.startswith(last) for t in texts(d)):
        failures.append("padd screen: an idle channel does not show the last contact")
    lua.execute("win:onJoypadDown(Joypad.RBumper, jd or { player = 0 })")
    if str(lua.eval("win.tab")) != "history":
        failures.append("padd screen: RB does not move to the history")
    d = state("history")
    if int(lua.eval("#win.list.items")) != 2:
        failures.append("padd screen: the history lists "
                        f"{lua.eval('#win.list.items')} calls, not 2")
    if str(lua.eval("win.list.items[1].item.row.id")) != "call:2":
        failures.append("padd screen: the history is not newest first")
    lua.execute("win:onJoypadDown(Joypad.XButton, { player = 0 })")
    d = state("history, the first call")
    if int(lua.eval("win.list.selected")) != 2:
        failures.append("padd screen: X does not step the history")
    if not any(TEXT["Print_Text_TREK_COMM_FIRST_03_O3"].split("%1")[0][:10] in t
               for t in texts(d)):
        failures.append("padd screen: a call from the history does not replay "
                        "what the holder said")

    # --- the library --------------------------------------------------------------
    lua.execute("win:onJoypadDown(Joypad.RBumper, { player = 0 })")
    d = state("library")
    rows = int(lua.eval("#win.list.items"))
    if rows != 3:
        failures.append(f"padd screen: the library lists {rows} rows for two "
                        f"books and a transcript")
    lua.execute("""
        draws = {}
        local y = 0
        for _, row in ipairs(win.list.items) do
            y = TREKPaddScreen.drawRow(win.list, y, row, false)
        end
    """)
    dd = lua.globals().draws
    check_bounds(lua, [dd[i] for i in range(1, len(dd) + 1)], "padd screen, library rows")
    # The transcript reads, and the Read button reads the tape.
    lua.execute("""
        for i, row in ipairs(win.list.items) do
            if row.item.kind == "tape" then win.list.selected = i end
        end
    """)
    d = state("library, a transcript")
    if not any("TALENT" in t.upper() for t in texts(d)):
        failures.append("padd screen: a transcript's title is not shown")
    if not win.readBtn.enable:
        failures.append("padd screen: a transcript cannot be read from the screen")
    lua.execute("win.readBtn:click()")
    if str(lua.eval("reads[#reads]")) != "tape:TREK_TalentNight":
        failures.append("padd screen: Read on a transcript does not read the tape")
    lua.execute("""
        win = TREKPaddScreen:new(0, 0, player, padd); win:createChildren()
        win:setTab("library")
        for i, row in ipairs(win.list.items) do
            if row.item.kind == "book" and row.item.entry.kind == "skill" then
                win.list.selected = i
            end
        end
    """)
    state("library, a book")
    lua.execute("win.readBtn:click()")
    if not str(lua.eval("reads[#reads]")).startswith("book:Base.BookCarpentry1"):
        failures.append("padd screen: Read on a book does not read it")

    # The fragments appear once the channel has mentioned them, gaps and all.
    lua.execute("""
        win = TREKPaddScreen:new(0, 0, player, padd); win:createChildren()
        TREK.Comms.store().flags.clueSeen = true
        TREK.Comms.store().converted = { [2] = true }
        win:setTab("library")
    """)
    state("library, the fragments")
    if int(lua.eval("#win.list.items")) != 9:
        failures.append("padd screen: the six fragments are not all listed, in "
                        "order, once the channel has mentioned them")

    # --- a controller ------------------------------------------------------------
    lua.execute('''
        reachable = {}
        for _, row in ipairs(win.joypadButtonsY) do
            for _, b in ipairs(row) do reachable[b] = true end
        end
        unreachable = {}
        for _, c in ipairs(win.children) do
            if c.onclick and not reachable[c] and c ~= win.ISButtonB then
                table.insert(unreachable, c.title or "?")
            end
        end
    ''')
    un = lua.globals().unreachable
    for i in range(1, len(un) + 1):
        failures.append(f"padd screen: button {un[i]!r} cannot be reached with a controller")
    lua.execute("jd = { player = 0, id = 0 }; win:onGainJoypadFocus(jd)")
    d = run_frames(lua, "padd screen, controller", 1)
    if TEXT["IGUI_TREK_PaddJoypadHint"].upper() not in texts(d):
        failures.append("padd screen: no button prompts for a controller")
    lua.execute("win:onJoypadDown(Joypad.LBumper, jd)")
    if str(lua.eval("win.tab")) != "history":
        failures.append("padd screen: LB does not go back a view")
    lua.execute("focusLog = {}; win:onJoypadDown(Joypad.BButton, jd)")
    if not win.removed:
        failures.append("padd screen: B does not close it")
    if len(lua.globals().focusLog) != 1:
        failures.append("padd screen: closing with a controller left the stick "
                        "on a panel that has gone")

    # --- a PADD that is no longer carried closes the screen --------------------
    lua.execute("""
        win = TREKPaddScreen:new(0, 0, player, padd); win:createChildren()
        carried = {}
        win:prerender()
    """)
    # The Lua global, not the Python name: that one is still the window B
    # closed above, and it would pass for the wrong reason.
    win = lua.globals().win
    if not win.removed:
        failures.append("padd screen: the PADD was dropped and its screen stayed open")

    for key in sorted(set(missing)):
        failures.append(f"padd screen: getText({key!r}) has no text in any "
                        f"translation file")
    print(f"padd screen: {W:.0f}x{H:.0f}; the channel idle, ringing, held on a "
          f"timed node with its clock, held by somebody else by name, and open; "
          f"a long call follows its newest line and scrolls; the history newest "
          f"first and replayed; the library with books, a transcript and the "
          f"fragments; every control on the stick")


def power_gauge():
    """The power bar (ENERGY.md 3.4): the helm's row and the screen gauge.

    Positions and colours, not presence: a bar that is drawn in the wrong
    colour, or a gauge that shows in the street, passes any check that only
    asks whether something was drawn.
    """
    texture_files["on"] = True
    lua, missing = make_lua()
    C = lua.globals().TREK.Config
    PM = float(C.PowerMax)
    gold, amber, red = (1.0, 0.8, 0.4), (1.0, 0.6, 0.4), (0.8, 0.4, 0.4)

    def bar_fill(draws, y):
        return [d for d in draws if d.kind == "rect" and d.own and abs(float(d.y) - y) < 0.5
                and abs(float(d.extra[1]) - 0.95) < 1e-6]

    def colour(d):
        return tuple(round(float(d.extra[i]), 2) for i in (2, 3, 4))

    def texts(draws):
        return [str(d.extra) for d in draws if d.kind == "text"]

    # --- the helm's row --------------------------------------------------
    lua.execute("win = TREKHelmWindow:new(60, 80, player); win:createChildren()")
    win = lua.globals().win
    by = float(win.powerBarY)
    for frac, want, name in ((0.9, gold, "gold"), (0.2, amber, "amber"), (0.05, red, "red")):
        lua.execute(f"local s = TREK.Util.state(); s.power = {PM * frac}; s.crystals = 2")
        draws = run_frames(lua, f"helm power {name}", 1)
        check_bounds(lua, draws, f"helm power {name}")
        fill = bar_fill(draws, by)
        if len(fill) != 1:
            failures.append(f"helm power: at {frac:.0%} the bar drew {len(fill)} fills")
            continue
        if colour(fill[0]) != want:
            failures.append(f"helm power: at {frac:.0%} the bar is {colour(fill[0])}, not {name}")
        if abs(float(fill[0].w) - int((float(win.width) - 64 - 28) * frac)) > 1:
            failures.append(f"helm power: at {frac:.0%} the fill is {float(fill[0].w):.0f}px wide")
        if IG["IGUI_TREK_PowerLevel"].replace("%1", str(int(PM * frac))).replace(
                "%2", str(int(PM))) not in texts(draws):
            failures.append(f"helm power: at {frac:.0%} the number is not on the row")

    lua.execute("local s = TREK.Util.state(); s.power = 0; s.crystals = 0")
    draws = run_frames(lua, "helm power dark", 1)
    check_bounds(lua, draws, "helm power dark")
    if bar_fill(draws, by):
        failures.append("helm power: a dark ship's bar still has a fill")
    if IG["IGUI_TREK_PowerEmergency"] not in texts(draws):
        failures.append("helm power: a dark ship's helm does not say EMERGENCY POWER")
    # A client told the ship is dark before it has been told the reserve reads
    # the reserve as full (TREK_Power: a missing value is full). The flag has
    # to win, or the bar is full gold under EMERGENCY POWER.
    lua.execute("""
        _G.isClient = function() return true end
        local s = TREK.Util.state(); s.power = nil; s.dark = true
    """)
    draws = run_frames(lua, "helm power dark client", 1)
    if bar_fill(draws, by):
        failures.append("helm power: a client that knows the ship is dark but not its "
                        "reserve draws a full bar")
    lua.execute("""
        _G.isClient = function() return false end
        local s = TREK.Util.state(); s.dark = nil
    """)

    # --- the gauge ---------------------------------------------------------
    lua.execute("""
        require "TREK/TREK_PowerHUD"
        _G.getSpecificPlayer = function() return player end
        player.getVehicle = function() return nil end
        hud = TREKPowerHUD:new()
        win = hud
        local s = TREK.Util.state(); s.power = TREK.Config.PowerMax * 0.6; s.crystals = 3
    """)
    draws = run_frames(lua, "gauge aboard", 1)
    check_bounds(lua, draws, "gauge aboard")
    pips = [d for d in draws if d.kind == "rect" and float(d.w) == 7 and float(d.h) == 7]
    if len(pips) != 3:
        failures.append(f"gauge: three spares drew {len(pips)} pips")
    if str(int(PM * 0.6)) not in texts(draws):
        failures.append("gauge: the reserve's number is not on the gauge")
    if not bar_fill(draws, 22):
        failures.append("gauge: aboard, the gauge drew no bar")

    lua.execute("TREK.Util.state().crystals = 12")
    draws = run_frames(lua, "gauge many spares", 1)
    if "x12" not in texts(draws):
        failures.append("gauge: twelve spares are not shown as a number")

    # Dark: EMERGENCY POWER, blinking.
    lua.execute("local s = TREK.Util.state(); s.power = 0; s.crystals = 0")
    lua.execute("_G.getTimestampMs = function() return 1600 * 100 + 100 end")
    on = texts(run_frames(lua, "gauge dark on", 1))
    lua.execute("_G.getTimestampMs = function() return 1600 * 100 + 1300 end")
    off = texts(run_frames(lua, "gauge dark off", 1))
    if IG["IGUI_TREK_PowerEmergency"] not in on:
        failures.append("gauge: a dark ship's gauge does not say EMERGENCY POWER")
    if IG["IGUI_TREK_PowerEmergency"] in off:
        failures.append("gauge: EMERGENCY POWER never blinks")

    # In the street it draws nothing; in her seat it draws.
    lua.execute("""
        local s = TREK.Util.state(); s.power = TREK.Config.PowerMax; s.crystals = 1
        player.getX = function() return 10500.5 end
        player.getY = function() return 9500.5 end
        player.getZ = function() return 0 end
    """)
    if run_frames(lua, "gauge outside", 1):
        failures.append("gauge: it is drawn for a player standing in the street")
    lua.execute("""
        player.getVehicle = function()
            return { getScriptName = function() return "Base.TrekShuttleCraft" end }
        end
    """)
    if not run_frames(lua, "gauge seated", 1):
        failures.append("gauge: it is not drawn for a player in her seat")
    lua.execute("""
        player.getVehicle = function()
            return { getScriptName = function() return "Base.CarNormal" end }
        end
    """)
    if run_frames(lua, "gauge other car", 1):
        failures.append("gauge: it is drawn in somebody else's car")
    if lua.eval("hud:isMouseOver()") is not False:
        failures.append("gauge: it can take the mouse")

    for key in sorted(set(missing)):
        failures.append(f"power gauge: getText({key!r}) has no entry in IG_UI.json")
    print("power gauge: the helm's bar is gold, amber and red at its thresholds and "
          "empty when dark; the screen gauge shows the reserve and its spares aboard "
          "and in her seat, blinks EMERGENCY POWER when dark, and is gone in the street")


def main():
    power_gauge()
    for textures in (True, False):
        texture_files["on"] = textures
        label = "art installed" if textures else "no textures"
        lua, missing = make_lua()
        U = lua.globals().TREK.Util
        C = lua.globals().TREK.Config

        # --- defaults ------------------------------------------------------
        if U.shieldsUp() is not True:
            failures.append(f"{label}: a new world does not start with shields up")

        lua.execute("win = TREKHelmWindow:new(60, 80, player); win:createChildren()")
        win = lua.globals().win
        check_bounds(lua, run_frames(lua, f"{label}, shields up"), f"{label}, shields up")

        # --- shields -------------------------------------------------------
        lua.execute("win.shieldsBtn:click()")
        if U.shieldsUp() is not False:
            failures.append(f"{label}: the shields button did not lower the shields")
        check_bounds(lua, run_frames(lua, f"{label}, shields down"), f"{label}, shields down")
        if win.shieldsBtn.title != IG["IGUI_TREK_ShieldsDown"]:
            failures.append(f"{label}: shields button reads {win.shieldsBtn.title!r} while down")
        lua.execute("win.shieldsBtn:click()")
        if U.shieldsUp() is not True:
            failures.append(f"{label}: the shields button did not raise them again")

        # --- a populated log, a course, and the navigation buttons ---------
        lua.execute("""
            local s = TREK.Util.state()
            s.bookmarks = {
                { name = "Muldraugh water tower", x = 10612, y = 9412, z = 0 },
                { name = "West Point", x = 11900, y = 6900, z = 0 },
            }
            s.destination = { x = 10612, y = 9412, z = 0 }
            win:refresh()
            win.list.selected = 1
            win.gotoBtn:click()
            win.deleteBtn:click()
        """)
        draws = run_frames(lua, f"{label}, with bookmarks")
        check_bounds(lua, draws, f"{label}, with bookmarks")
        # The list's own rows draw through drawBookmark with the list as self.
        try:
            lua.execute("""
                draws = {}
                local y = 0
                for _, row in ipairs(win.list.items) do
                    y = win.drawBookmark(win.list, y, row, false)
                end
            """)
        except Exception as exc:                              # noqa: BLE001
            failures.append(f"{label}: drawBookmark threw -- {exc}")

        # --- a controller ---------------------------------------------------
        # Every button a player can use must be reachable from the stick.
        lua.execute('''
            reachable = {}
            for _, row in ipairs(win.joypadButtonsY) do
                for _, b in ipairs(row) do reachable[b] = true end
            end
            unreachable = {}
            for _, c in ipairs(win.children) do
                if c.onclick and not reachable[c] and c ~= win.ISButtonB then
                    table.insert(unreachable, c.title or "?")
                end
            end
        ''')
        unreachable = lua.globals().unreachable
        for i in range(1, len(unreachable) + 1):
            failures.append(f"{label}: button {unreachable[i]!r} cannot be reached with a controller")

        lua.execute("jd = { player = 0, id = 0 }; win:onGainJoypadFocus(jd)")
        if not win.shieldsBtn.joypadFocused:
            failures.append(f"{label}: a controller does not start on the shields button")
        check_bounds(lua, run_frames(lua, f"{label}, controller focus"), f"{label}, controller focus")
        if not any(str(d.extra) == IG["IGUI_TREK_HelmJoypadHint"].upper()
                   for d in run_frames(lua, f"{label}, controller hint", 1) if d.kind == "text"):
            failures.append(f"{label}: no button prompts are shown to a controller player")

        was = U.shieldsUp()
        lua.execute("win:onJoypadDown(Joypad.AButton, jd)")
        if U.shieldsUp() == was:
            failures.append(f"{label}: A on the focused shields button did nothing")

        lua.execute('''
            local s = TREK.Util.state()
            s.bookmarks = { { name = "a", x = 1, y = 1, z = 0 }, { name = "b", x = 2, y = 2, z = 0 } }
            win:refresh()
            win.list.selected = 0
            win:onJoypadDown(Joypad.RBumper, jd); first = win.list.selected
            win:onJoypadDown(Joypad.RBumper, jd); second = win.list.selected
            win:onJoypadDown(Joypad.RBumper, jd); wrapped = win.list.selected
            win:onJoypadDown(Joypad.LBumper, jd); back = win.list.selected
        ''')
        g = lua.globals()
        if (g.first, g.second, g.wrapped, g.back) != (1, 2, 1, 2):
            failures.append(f"{label}: RB/LB step the log as {(g.first, g.second, g.wrapped, g.back)}, "
                            f"not (1, 2, 1, 2)")

        lua.execute("picked = nil; win.crosshairBtn:click()")
        picked = lua.globals().picked
        if picked is None or (int(picked.x), int(picked.y)) != (10612, 9412):
            failures.append(f"{label}: 'course to crosshair' did not pick the map centre")

        lua.execute("focusLog = {}; win:onJoypadDown(Joypad.YButton, jd)")
        if len(lua.globals().focusLog) != 1:
            failures.append(f"{label}: Y did not hand the stick to the map")

        # --- closing -------------------------------------------------------
        lua.execute("focusLog = {}; win:onJoypadDown(Joypad.BButton, jd)")
        if not win.removed:
            failures.append(f"{label}: B did not close the helm")
        log = lua.globals().focusLog
        if len(log) != 1:
            failures.append(f"{label}: closing with a controller did not release its focus")

        # --- not crew -------------------------------------------------------
        lua.execute('''
            TREK.Ship.canUse = function() return false end
            win:refresh()
        ''')
        if "IGUI_TREK_NotCrew" not in IG or IG["IGUI_TREK_NotCrew"] not in str(win.info.text):
            failures.append(f"{label}: a player who is not crew is not told so at the helm")
        lua.execute("TREK.Ship.canUse = function() return true end")

        for key in sorted(set(missing)):
            failures.append(f"{label}: getText({key!r}) has no entry in IG_UI.json")

        print(f"{label}: drew {len(draws)} calls a frame with bookmarks; "
              f"every control exercised")

    # --- the tricorder's contact plot -------------------------------------
    # The same treatment as the helm, and for the same reason: prerender and
    # render run sixty times a second, so one nil in either is a stack trace a
    # frame for as long as the panel is open. The plot is the part with real
    # arithmetic in it -- a blip is placed from a contact's offset over the
    # sweep radius -- and a contact right on the edge of range is exactly the
    # one that lands outside the frame.
    texture_files["on"] = True
    lua, missing = make_lua()
    C = lua.globals().TREK.Config
    lua.execute("win = TREKTricorderWindow:new(40, 40, player); win:createChildren()")
    win = lua.globals().win

    check_bounds(lua, run_frames(lua, "tricorder, no sweep yet"), "tricorder, no sweep yet")

    # A result with contacts at every bearing, including four sitting exactly
    # on the range limit, which is where a plot goes outside its own box.
    lua.execute("""
        local r = TREK.Config.SweepRadius
        local contacts = {}
        for _, d in ipairs({ { r, 0 }, { -r, 0 }, { 0, r }, { 0, -r },
                             { 2, 3 }, { -4, 6 }, { 15, -15 }, { 0, 0 } }) do
            table.insert(contacts, { dx = d[1], dy = d[2],
                                     band = (math.abs(d[1]) + math.abs(d[2])) > r
                                            and 3 or 1 })
        end
        -- Dilithium traces, including two at the very edge of the mineral
        -- radius -- which is shorter than the lifesign one, so a trace
        -- plotted against the wrong radius lands outside the box.
        local cr = TREK.Config.CrystalScanRadius
        win.result = { contacts = contacts, counts = { 5, 2, 1 }, total = 8,
                       radius = r,
                       crystals = { { dx = cr, dy = 0, n = 1 },
                                    { dx = 0, dy = -cr, n = 2 },
                                    { dx = -3, dy = 4, n = 1 } },
                       crystalTotal = 4, crystalRadius = cr }
    """)
    draws = run_frames(lua, "tricorder, with contacts")
    check_bounds(lua, draws, "tricorder, with contacts")

    # The title names what the instrument is doing. A sweep taken from a seat
    # in the shuttle reads every level below it rather than the one it is on,
    # and a plot that quietly means something else is worse than one that
    # found nothing.
    if not any(str(d.extra) == IG["IGUI_TREK_SweepTitle"].upper()
               for d in draws if d.kind == "text"):
        failures.append("tricorder: a sweep on foot is not titled a sensor "
                        "sweep")
    lua.execute("win.result.aloft = true")
    survey = run_frames(lua, "tricorder, surveying from the air")
    check_bounds(lua, survey, "tricorder, surveying from the air")
    if not any(str(d.extra) == IG["IGUI_TREK_SweepTitleAloft"].upper()
               for d in survey if d.kind == "text"):
        failures.append("tricorder: a survey taken from the air is still "
                        "titled a sensor sweep, so nothing on screen says it "
                        "is reading the ground")
    lua.execute("win.result.aloft = false")

    # Staying inside the box is not the same as being in the right place.
    # A crystal is a ring with a bright middle -- the only 8x8 border on the
    # plot -- and the three in the result have to be three rings, in the
    # positions their offsets ask for.
    FRAMES = 3
    rings = [d for d in draws
             if d.kind == "rectborder" and abs(float(d.w) - 8) < 0.01
             and abs(float(d.h) - 8) < 0.01]
    if len(rings) != 3 * FRAMES:
        failures.append(f"tricorder: {len(rings) // FRAMES} dilithium traces "
                        f"are drawn on the plot, not the 3 in the result")
    else:
        # The plot's own square gives its geometry: the window keeps its
        # corner, and the box drawn there gives the side.
        box = next(d for d in draws
                   if d.kind == "rectborder"
                   and abs(float(d.x) - float(win.plotX)) < 0.01
                   and abs(float(d.y) - float(win.plotY)) < 0.01)
        side = float(box.w)
        pcx, pcy = float(win.plotX) + side / 2, float(win.plotY) + side / 2
        half = side / 2 - 6
        # The trace at dx = CrystalScanRadius sits on the east edge. Plotted
        # against the *lifesign* radius it would sit well inside it, which is
        # the failure this catches: a crystal that reads as much nearer than
        # it is, on the one instrument a player trusts to walk by.
        edge = [r for r in rings
                if abs((float(r.x) + 3.5) - (pcx + half)) < 1.0
                and abs((float(r.y) + 3.5) - pcy) < 1.0]
        if len(edge) != FRAMES:
            failures.append(
                f"tricorder: the trace {int(C.CrystalScanRadius)} tiles due "
                f"east is not drawn on the east edge of the plot -- it is "
                f"plotted against the wrong radius")
    # And the number in the readout is the number that was found.
    if not any(str(d.extra) == "4" for d in draws if d.kind == "text"):
        failures.append("tricorder: four traces were found and the readout "
                        "does not say 4")

    # --- the downed ensign on the plot (ENSIGN.md) ---------------------------
    # A cross -- the only 11x3 bar on the plot -- right on the range limit,
    # with every other line of the readout drawn too, because the ensign's
    # line is the last one and the one that would push past the button.
    lua.execute("""
        win.result.personnel = { dx = TREK.Config.SweepRadius, dy = 0,
                                 dist = TREK.Config.SweepRadius,
                                 compass = "E", name = "Test" }
    """)
    found = run_frames(lua, "tricorder, the ensign on the range limit")
    check_bounds(lua, found, "tricorder, the ensign on the range limit")
    bars = [d for d in found if d.kind == "rect"
            and abs(float(d.w) - 11) < 0.01 and abs(float(d.h) - 3) < 0.01]
    if len(bars) != FRAMES:
        failures.append(f"tricorder: the ensign's cross was drawn "
                        f"{len(bars) // FRAMES} times, not once")
    else:
        box = next(d for d in found
                   if d.kind == "rectborder"
                   and abs(float(d.x) - float(win.plotX)) < 0.01
                   and abs(float(d.y) - float(win.plotY)) < 0.01)
        side = float(box.w)
        east = float(win.plotX) + side / 2 + (side / 2 - 6)
        if abs(float(bars[0].x) + 5 - east) > 1.0:
            failures.append("tricorder: the ensign on the range limit due "
                            "east is not drawn on the east edge of the plot")
    if not any(str(d.extra) == IG["IGUI_TREK_SweepPersonnel"].upper()
               for d in found if d.kind == "text"):
        failures.append("tricorder: the ensign is in range and the readout "
                        "does not say so")
    # A holo fragment as well, on the range limit due west: a frame round a
    # lit centre -- the only 11x11 border on the plot -- on the west edge, and
    # its own line in a readout that already has the ensign's.
    lua.execute("""
        win.result.clue = { dx = -TREK.Config.SweepRadius, dy = 0,
                            dist = TREK.Config.SweepRadius, compass = "W", n = 3 }
    """)
    both = run_frames(lua, "tricorder, the ensign and a fragment")
    check_bounds(lua, both, "tricorder, the ensign and a fragment")
    frames = [d for d in both if d.kind == "rectborder"
              and abs(float(d.w) - 11) < 0.01 and abs(float(d.h) - 11) < 0.01]
    if len(frames) != FRAMES:
        failures.append(f"tricorder: a holo fragment in range was drawn "
                        f"{len(frames) // FRAMES} times, not once")
    else:
        box = next(d for d in both
                   if d.kind == "rectborder"
                   and abs(float(d.x) - float(win.plotX)) < 0.01
                   and abs(float(d.y) - float(win.plotY)) < 0.01)
        side = float(box.w)
        west = float(win.plotX) + side / 2 - (side / 2 - 6)
        if abs(float(frames[0].x) + 5 - west) > 1.0:
            failures.append("tricorder: a fragment on the range limit due west "
                            "is not drawn on the west edge of the plot")
    if not any(str(d.extra) == IG["IGUI_TREK_SweepClue"].upper()
               for d in both if d.kind == "text"):
        failures.append("tricorder: a holo fragment is in range and the readout "
                        "does not say so")
    lua.execute("win.result.clue = nil")
    lua.execute("win.result.personnel = nil")
    plain = run_frames(lua, "tricorder, no ensign")
    if any(str(d.extra) == IG["IGUI_TREK_SweepPersonnel"].upper()
           for d in plain if d.kind == "text"):
        failures.append("tricorder: a sweep with nobody in range still "
                        "draws a Starfleet life sign line")

    # An empty sweep has to say so rather than drawing an empty box.
    lua.execute("""
        win.result = { contacts = {}, counts = { 0, 0, 0 }, total = 0,
                       radius = TREK.Config.SweepRadius }
    """)
    empty = run_frames(lua, "tricorder, nothing found")
    check_bounds(lua, empty, "tricorder, nothing found")
    # The dilithium line is drawn whether or not any was found: "none in
    # range" is the answer a prospector needs, and a line that only appears
    # on a hit is one a player cannot learn to look for.
    if not any(str(d.extra) == IG["IGUI_TREK_SweepDilithium"].upper()
               for d in empty if d.kind == "text"):
        failures.append("tricorder: a sweep that found no dilithium does not "
                        "say so")
    if not any(str(d.extra) == IG["IGUI_TREK_SweepNone"]
               for d in empty if d.kind == "text"):
        failures.append("tricorder: a sweep that found nothing says nothing")

    # Controller: one button, reachable, and B closes and hands the stick back.
    lua.execute("""
        reachable = {}
        for _, row in ipairs(win.joypadButtonsY) do
            for _, b in ipairs(row) do reachable[b] = true end
        end
        unreachable = {}
        for _, c in ipairs(win.children) do
            if c.onclick and not reachable[c] and c ~= win.ISButtonB then
                table.insert(unreachable, c.title or "?")
            end
        end
    """)
    unreachable = lua.globals().unreachable
    for i in range(1, len(unreachable) + 1):
        failures.append(f"tricorder: button {unreachable[i]!r} cannot be reached "
                        f"with a controller")

    lua.execute("jd = { player = 0, id = 0 }; win:onGainJoypadFocus(jd)")
    if not win.sweepBtn.joypadFocused:
        failures.append("tricorder: a controller does not start on the sweep button")
    lua.execute("focusLog = {}; win:onJoypadDown(Joypad.BButton, jd)")
    if not win.removed:
        failures.append("tricorder: B did not close the panel")
    if len(lua.globals().focusLog) != 1:
        failures.append("tricorder: closing with a controller did not release its "
                        "focus, so the stick is left driving a panel that has gone")

    for key in sorted(set(missing)):
        failures.append(f"tricorder: getText({key!r}) has no entry in IG_UI.json")
    print(f"tricorder: the contact plot drew {len(draws)} calls a frame with "
          f"contacts on the range limit, and its one control is on the stick")

    # --- the replicator panel ----------------------------------------------
    # The one panel in this mod whose contents are not written by this mod:
    # the rows come from the whole item catalogue, so their number and the
    # length of their names are not knowable in advance. That is exactly the
    # shape that runs out of its column, and the only things that ever see it
    # are a render and this file.
    texture_files["on"] = True
    lua, missing = make_lua()
    C = lua.globals().TREK.Config
    lua.execute("win = TREKReplicatorWindow:new(40, 40, player); win:createChildren()")
    win = lua.globals().win

    # The root of the tree is the categories, not the items.
    rows = int(lua.eval("#TREK.Replicator.catalogue()"))
    if rows < 100:
        failures.append(f"replicator: the catalogue came out at {rows} rows; "
                        f"the stub has more than that, so it is not reading "
                        f"getAllItems() at all")
    check_bounds(lua, run_frames(lua, "replicator, full catalogue"),
                 "replicator, full catalogue")

    # The rows themselves draw through doDrawItem with the list as self, so
    # they are never touched by the frame loop above. Only as many as fit,
    # because a row drawn past the bottom of its own list is a scroll, not a
    # bug.
    lua.execute("""
        draws = {}
        local fit = math.floor(win.list.height / win.list.itemheight)
        local y = 0
        for i, row in ipairs(win.list.items) do
            if i > fit then break end
            y = win.drawRow(win.list, y, row, false)
        end
    """)
    d = lua.globals().draws
    check_bounds(lua, [d[i] for i in range(1, len(d) + 1)], "replicator, rows")

    # --- the tree: categories, then the items in one ------------------------
    # It was a button that cycled one category per press. With seventy-eight of
    # them in a real game that is not a control, so the list itself is the
    # browser now: categories at the root, items inside one, Back out.
    categories = int(lua.eval("#TREK.Replicator.categories()"))
    if int(lua.eval("#win.rows")) != categories:
        failures.append(f"replicator: the root of the tree lists "
                        f"{int(lua.eval('#win.rows'))} rows for {categories} "
                        f"categories")
    if str(lua.eval("win.rows[1].kind")) != "category":
        failures.append("replicator: the root of the tree is not made of "
                        "categories at all")

    lua.execute("win.list.selected = 1")
    run_frames(lua, "replicator, a category picked", 1)
    if IG["IGUI_TREK_RepBrowse"].replace("%1", "") not in str(win.makeBtn.title):
        failures.append(f"replicator: with a category picked the action button "
                        f"reads {win.makeBtn.title!r} rather than offering to "
                        f"open it")

    first_category = str(lua.eval("win.rows[1].name"))
    lua.execute("win.makeBtn:click()")
    if str(lua.eval("tostring(win.category)")) != first_category:
        failures.append(f"replicator: opening {first_category!r} left the panel "
                        f"in {lua.eval('tostring(win.category)')!r}")
    inside = int(lua.eval("#win.rows"))
    if not 0 < inside < categories + int(lua.eval("#TREK.Replicator.catalogue()")):
        failures.append("replicator: opening a category listed nothing")
    if str(lua.eval("win.rows[1].kind")) != "item":
        failures.append("replicator: a category opened onto something other "
                        "than items")
    if inside != int(lua.eval(f'#TREK.Replicator.inCategory("{first_category}")')):
        failures.append(f"replicator: {first_category!r} holds "
                        f"{lua.eval(f'#TREK.Replicator.inCategory(chr(34))')} "
                        f"items but the panel lists {inside}")
    check_bounds(lua, run_frames(lua, "replicator, inside a category"),
                 "replicator, inside a category")

    lua.execute("win.backBtn:click()")
    if lua.eval("win.category") is not None:
        failures.append("replicator: Back did not come out of the category")
    if int(lua.eval("#win.rows")) != categories:
        failures.append("replicator: Back did not restore the category list")

    # --- searching looks everywhere, wherever you are standing --------------
    lua.execute(f'win:openCategory("{first_category}")')
    lua.execute('win.search:setText("thing number 1")')
    narrowed = int(lua.eval("#win.rows"))
    if not 0 < narrowed < rows:
        failures.append(f"replicator: searching narrowed {rows} rows to "
                        f"{narrowed}; the filter is doing nothing")
    if lua.eval("win.category") is not None:
        failures.append("replicator: typing a search left the panel inside a "
                        "category, so it was searching one folder rather than "
                        "the catalogue")

    lua.execute('win.search:setText("zzzznothing")')
    if int(lua.eval("#win.rows")) != 0:
        failures.append("replicator: a search that matches nothing still lists rows")
    empty = run_frames(lua, "replicator, nothing matches")
    check_bounds(lua, empty, "replicator, nothing matches")
    if not any(str(x.extra) == IG["IGUI_TREK_RepNoMatch"]
               for x in empty if x.kind == "text"):
        failures.append("replicator: a search with no matches draws an empty "
                        "box and says nothing")
    lua.execute("win.backBtn:click()")

    # --- only what the ship can make ----------------------------------------
    # The toggle applies to the categories too: one the ship has no patterns in
    # is not worth walking into, so it is not offered.
    lua.execute("win.knownBtn:click()")
    if not lua.eval("win.knownOnly"):
        failures.append("replicator: the known-only toggle did not come on")
    known_categories = int(lua.eval("#win.rows"))
    if not 0 < known_categories < categories:
        failures.append(f"replicator: with known-only on, {known_categories} of "
                        f"{categories} categories are listed -- the stub ship "
                        f"knows one category's worth of patterns, so it should "
                        f"be some but not all")
    check_bounds(lua, run_frames(lua, "replicator, known only"),
                 "replicator, known only")

    every_known = lua.eval("""(function()
        for _, row in ipairs(win.rows) do
            local _, known = TREK.Replicator.categoryCount(row.name)
            if known == 0 then return false end
        end
        return true
    end)()""")
    if every_known is not True:
        failures.append("replicator: known-only still lists a category the ship "
                        "has no pattern in")

    # Inside one, only the items it can make.
    lua.execute("win.list.selected = 1; win.makeBtn:click()")
    all_known = lua.eval("""(function()
        for _, row in ipairs(win.rows) do
            if not TREK.Replicator.knows(row.item.id) then return false end
        end
        return #win.rows > 0
    end)()""")
    if all_known is not True:
        failures.append("replicator: inside a category, known-only still lists "
                        "items the ship has no pattern for")
    lua.execute("win.knownBtn:click(); win.backBtn:click()")

    # --- the button says what it will do ------------------------------------
    lua.execute('win.search:setText("")')
    lua.execute("win.list.selected = 0")
    run_frames(lua, "replicator, nothing picked", 1)
    if win.makeBtn.title != IG["IGUI_TREK_RepNothingPicked"]:
        failures.append(f"replicator: with nothing selected the button reads "
                        f"{win.makeBtn.title!r}")
    if win.makeBtn.enable:
        failures.append("replicator: the action button is live with nothing "
                        "selected")

    lua.execute('win.search:setText("phaser"); win.list.selected = 1')
    run_frames(lua, "replicator, a known pattern", 1)
    if not win.makeBtn.enable:
        failures.append("replicator: the ship's own phaser -- a pattern it has "
                        "from the start -- cannot be materialised")
    if str(int(C.ReplicatorBaseCost + 0.6 * C.ReplicatorWeightCost)) \
            not in str(win.makeBtn.title):
        failures.append(f"replicator: the button does not show what it will "
                        f"cost ({win.makeBtn.title!r})")

    lua.execute('win.search:setText("thing number 3"); win.list.selected = 1')
    run_frames(lua, "replicator, no pattern", 1)
    if win.makeBtn.enable:
        failures.append("replicator: an item with no pattern can be materialised "
                        "from the panel")

    # An empty reserve greys the button rather than letting a player press it
    # and be refused.
    lua.execute("""
        win.search:setText("phaser")
        win.list.selected = 1
        TREK.Util.state().power = 0
    """)
    run_frames(lua, "replicator, empty reserve", 1)
    if win.makeBtn.enable:
        failures.append("replicator: with an empty reserve the button is still live")
    lua.execute(f"TREK.Util.state().power = {float(C.PowerMax)}")

    # --- the quantity button cycles -----------------------------------------
    # Twice round, not once. An index that runs off the end of the list makes
    # quantity() fall back to 1, so a single lap reads exactly like a wrap that
    # works -- and then the button never offers 5 or 10 again.
    seen_quantities = []
    for _ in range(8):
        seen_quantities.append(int(lua.eval("win:quantity()")))
        lua.execute("win.qtyBtn:click()")
    if seen_quantities != [1, 5, 10, 1, 5, 10, 1, 5]:
        failures.append(f"replicator: the quantity button steps {seen_quantities}, "
                        f"not [1, 5, 10] over and over")
    lua.execute('win.search:setText("")')

    # --- a controller ---------------------------------------------------------
    lua.execute('''
        reachable = {}
        for _, row in ipairs(win.joypadButtonsY) do
            for _, b in ipairs(row) do reachable[b] = true end
        end
        unreachable = {}
        for _, c in ipairs(win.children) do
            if c.onclick and not reachable[c] and c ~= win.ISButtonB then
                table.insert(unreachable, c.title or "?")
            end
        end
    ''')
    unreachable = lua.globals().unreachable
    for i in range(1, len(unreachable) + 1):
        failures.append(f"replicator: button {unreachable[i]!r} cannot be "
                        f"reached with a controller")

    lua.execute("jd = { player = 0, id = 0 }; win:onGainJoypadFocus(jd)")
    if not win.backBtn.joypadFocused:
        failures.append("replicator: a controller does not start on the first "
                        "row of buttons -- a pad cannot type, so the tree is "
                        "the only way in")

    # The bumpers walk the list, which is the pad's answer to a search box.
    lua.execute("""
        win.category = nil
        win.search:setText("")
        win:refreshRows()
        win.list.selected = 0
        win:onJoypadDown(Joypad.RBumper, jd); first = win.list.selected
        win:onJoypadDown(Joypad.RBumper, jd); second = win.list.selected
        win:onJoypadDown(Joypad.LBumper, jd); back = win.list.selected
    """)
    g = lua.globals()
    if (g.first, g.second, g.back) != (1, 2, 1):
        failures.append(f"replicator: RB/LB step the catalogue as "
                        f"{(g.first, g.second, g.back)}, not (1, 2, 1)")

    if not any(str(x.extra) == IG["IGUI_TREK_RepJoypadHint"].upper()
               for x in run_frames(lua, "replicator, controller hint", 1)
               if x.kind == "text"):
        failures.append("replicator: no button prompts are shown to a controller player")

    lua.execute("focusLog = {}; win:onJoypadDown(Joypad.BButton, jd)")
    if not win.removed:
        failures.append("replicator: B did not close the panel")
    if len(lua.globals().focusLog) != 1:
        failures.append("replicator: closing with a controller did not release "
                        "its focus, so the stick is left driving a panel that "
                        "has gone")

    for key in sorted(set(missing)):
        failures.append(f"replicator: getText({key!r}) has no entry in IG_UI.json")
    print(f"replicator: the panel drew a {rows}-row catalogue, its search, "
          f"category and quantity controls all bite, and every button is on "
          f"the stick")

    # --- the EMH's dialogue panel -------------------------------------------
    # Drawn rather than reasoned about, for the reason every panel in this mod
    # is: prerender and render run sixty times a second, so one nil in them is
    # a stack trace per frame for as long as the window is open, and a label
    # that runs off its button can otherwise only be seen in game.
    #
    # Twice over, deliberately: once with a healthy patient and a full core,
    # and once with a wrecked one and an empty core. The second is the state
    # every control has something to say about, and a panel that only ever
    # draws the happy case is a panel whose refusals have never been drawn.
    lua, missing = make_lua()
    C = lua.globals().TREK.Config

    # Standing at the station rather than at the replicator's berth: the panel
    # closes itself from inside prerender when nobody is at it, so a player
    # left across the cabin would shut the window on its first frame and every
    # check after it would be drawing nothing at all.
    lua.execute("""
        local sx, sy = TREK.EMH.station()
        local bx, by = TREK.Util.at(sx, sy)
        player.getX = function() return bx + 0.5 end
        player.getY = function() return by + 0.5 end
        player.getZ = function() return TREK.Config.CabinZ end
        local s = TREK.Util.state()
        s.emh = true
        -- A core with spares in it. There is no cabin in this harness, so the
        -- count is whatever the ship state says -- and with it absent every
        -- Cure check below would pass for the wrong reason, on a ship that
        -- could not have cured anybody anyway.
        s.crystals = 3
    """)

    lua.execute("win = TREKEMHWindow:new(40, 40, player); win:createChildren()")
    win = lua.globals().win
    check_bounds(lua, run_frames(lua, "emh, a well patient"), "emh, a well patient")

    if not win.dismissBtn.enable:
        failures.append("emh: the dismiss button is dead, so there is no way "
                        "to put the Doctor away from inside the panel")
    if win.patientBtn.enable:
        failures.append("emh: the patient stepper is live with one person "
                        "aboard -- a control that cannot change anything is "
                        "worse than none")
    if win.treatBtn.enable:
        failures.append("emh: Treat is live on a patient with nothing wrong "
                        "with them")
    if win.cureBtn.enable:
        failures.append("emh: Cure is live on a patient who is not infected")

    # --- and now a patient worth treating ------------------------------------
    lua.execute("""
        local p = bodyParts[1]
        p.bleed, p.deep, p.burn, p.frac = true, 12, 20, 21
        p.pain, p.stiff, p.health = 40, 30, 55
        bodyParts[2].glass = true
        bodyParts[3].cut, bodyParts[3].cutT = true, 10
        bodyParts[4].bite, bodyParts[4].biteT = true, 10
        bodyParts[4].infected = true
        playerDamage:setInfected(true)
    """)
    draws = run_frames(lua, "emh, a hurt patient")
    check_bounds(lua, draws, "emh, a hurt patient")

    if not win.treatBtn.enable:
        failures.append("emh: Treat is greyed on a patient who is bleeding, "
                        "burnt, broken and full of glass")
    if not win.cureBtn.enable:
        failures.append("emh: Cure is greyed on an infected patient with "
                        "crystals aboard")

    # The findings list is the half of the panel that is easiest to get wrong:
    # it is built from Med.TREATMENTS' and Med.SKIN's own keys, so a concern
    # the lists stop carrying stops being drawn, and one that is drawn under
    # the wrong name is only visible here.
    texts = [str(d.extra) for d in draws if d.kind == "text"]
    for key, what in (("IGUI_TREK_TreatBleeding", "bleeding"),
                      ("IGUI_TREK_TreatFracture", "a fracture"),
                      ("IGUI_TREK_EmhGlass", "glass in a wound"),
                      ("IGUI_TREK_EmhInfected", "the zombie infection")):
        want = IG[key]
        if not any(want in t or want.upper() in t for t in texts):
            failures.append(f"emh: the panel never says anything about {what} "
                            f"on a patient who has it")

    # **The infection is said out loud**, and it is the one thing the medical
    # tricorder deliberately will not tell you. A panel that drew everything
    # else and stayed quiet about that would have no reason to exist.
    if any(IG["IGUI_TREK_EmhClean"].upper() in t for t in texts):
        failures.append("emh: the panel reports an infected patient as clean")

    # --- a cure running -------------------------------------------------------
    # The bite and the infection stay for the twelve hours a cure takes, so a
    # panel that says only "infected" through all of it reads as a cure that
    # failed. It has to say that one is running, and how long is left.
    lua.execute("""
        TREK.EMH.cures()[player:getUsername()] = TREK.EMH.worldHours() + 9
    """)
    draws = run_frames(lua, "emh, a cure running")
    check_bounds(lua, draws, "emh, a cure running")
    running = IG["IGUI_TREK_EmhCureRunning"].split("%1")[0].upper()
    if not any(running in str(d.extra) for d in draws if d.kind == "text"):
        failures.append("emh: a cure is running and the panel does not say "
                        "so, or how long it has left")
    lua.execute("TREK.EMH.cures()[player:getUsername()] = nil")

    # --- a long name, and an empty core --------------------------------------
    # Two states that only a render shows: a username longer than its button,
    # and a ship with nothing to cure anybody with.
    lua.execute("""
        player.getUsername = function()
            return "Lieutenant Commander Extremely Long Name Indeed"
        end
        TREK.Util.state().crystals = 0
    """)
    draws = run_frames(lua, "emh, a long name and no crystals")
    check_bounds(lua, draws, "emh, a long name and no crystals")
    if win.cureBtn.enable:
        failures.append("emh: Cure is live with no crystals aboard -- the "
                        "player presses it and is refused, which reads as a "
                        "broken machine")
    if IG["IGUI_TREK_EmhNoSpares"] not in [str(d.extra) for d in draws
                                           if d.kind == "text"]:
        failures.append("emh: with an empty core the panel does not say so, "
                        "so a player cannot tell a refusal from a fault")

    # --- a controller ---------------------------------------------------------
    lua.execute('''
        reachable = {}
        for _, row in ipairs(win.joypadButtonsY) do
            for _, b in ipairs(row) do reachable[b] = true end
        end
        unreachable = {}
        for _, c in ipairs(win.children) do
            if c.onclick and not reachable[c] and c ~= win.ISButtonB then
                table.insert(unreachable, c.title or "?")
            end
        end
    ''')
    unreachable = lua.globals().unreachable
    for i in range(1, len(unreachable) + 1):
        failures.append(f"emh: button {unreachable[i]!r} cannot be reached "
                        f"with a controller")

    lua.execute("jd = { player = 0, id = 0 }; win:onGainJoypadFocus(jd)")
    if not win.patientBtn.joypadFocused:
        failures.append("emh: a controller does not start on the first row of "
                        "the panel")

    lua.execute("focusLog = {}; win:onJoypadDown(Joypad.BButton, jd)")
    if not win.removed:
        failures.append("emh: B did not close the panel")
    if len(lua.globals().focusLog) != 1:
        failures.append("emh: closing with a controller did not release its "
                        "focus, so the stick is left driving a panel that has "
                        "gone")

    for key in sorted(set(missing)):
        failures.append(f"emh: getText({key!r}) has no entry in IG_UI.json")
    print("emh: the Doctor's panel drew a well patient and a wrecked one, "
          "named every finding and the infection, greyed Treat and Cure for "
          "their own reasons, and every control is on the stick")

    # --- the sensor console --------------------------------------------------
    # The fourth LCARS panel. It draws a progress bar and a list that both
    # come from a table the server republishes, so the interesting states are
    # "nothing yet", "a probe is out" and "contacts on file" -- and all three
    # have to draw inside the panel and leave every control reachable.
    lua.execute("""
        local U = TREK.Util
        local s = U.state()
        s.power = TREK.Config.PowerMax
        s.probes = 0
        -- This harness has its own small stubs rather than pz_sim, so the
        -- contact store is reached through the module itself.
        local store = TREK.Probes.store()
        store.contacts = {}
        store.active = nil
        store.serial = 0
    """)
    lua.execute("win = TREKProbeWindow:new(40, 40, player); win:createChildren()")
    win = lua.globals().win
    check_bounds(lua, run_frames(lua, "probes, an empty rack"), "probes, an empty rack")

    if win.launchBtn.enable:
        failures.append("probes: Launch is live with an empty rack")
    if not win.buildBtn.enable:
        failures.append("probes: Fabricate is dead on a full reserve, so "
                        "there is no way to get a probe at all")
    if win.showBtn.enable:
        failures.append("probes: Show on map is live with no contacts")

    # A probe in the rack, and then one in flight.
    lua.execute("TREK.Util.state().probes = 2")
    run_frames(lua, "probes, a probe aboard")
    if not win.launchBtn.enable:
        failures.append("probes: Launch is dead with probes in the rack")

    lua.execute("""
        TREK.Probes.begin(2000, 2000, 1.0, 1500, 60)
        TREK.Probes.store().active.progress = 30
    """)
    draws = run_frames(lua, "probes, in flight")
    check_bounds(lua, draws, "probes, in flight")
    if win.launchBtn.enable:
        failures.append("probes: Launch is live while a probe is already up")
    if not any(d.kind == "rect" for d in draws):
        failures.append("probes: nothing was drawn for the flight -- the "
                        "progress bar is the whole reason this panel exists "
                        "rather than a menu")

    # And a list of contacts, at a distance and a bearing.
    lua.execute("""
        TREK.Probes.store().active = nil
        TREK.Probes.addContact("dilithium", 2400, 1800, 0, "probe:1", true)
        TREK.Probes.addContact("downedPersonnel", 1500, 2600, 0, "probe:1", false)
    """)
    draws = run_frames(lua, "probes, contacts on file")
    check_bounds(lua, draws, "probes, contacts on file")
    rows = int(lua.eval("#win.list.items"))
    if rows != 2:
        failures.append(f"probes: the list holds {rows} of 2 contacts")
    if not win.showBtn.enable:
        failures.append("probes: Show on map is dead with contacts on file")

    # --- the distress call (ENSIGN.md) ---------------------------------------
    # Nothing pending: both answers greyed. A call: both live, and the call
    # drawn inside the panel. A rescue under way: greyed again, and the
    # countdown drawn instead.
    if win.acceptBtn.enable or win.declineBtn.enable:
        failures.append("probes: Accept or Decline is live with no call on "
                        "the air")
    lua.execute("""
        TREK.Probes.store().distress = {
            id = "distress:9", name = "Maren Novak", division = "Operations",
            body = "F", tx = 2400, ty = 2300, tz = 0, distance = 412,
            compass = "NE", offeredAt = 0, lapseAt = 12 }
    """)
    draws = run_frames(lua, "probes, a distress call")
    check_bounds(lua, draws, "probes, a distress call")
    if not (win.acceptBtn.enable and win.declineBtn.enable):
        failures.append("probes: a call is pending and it cannot be answered")
    if not any(str(d.extra) == IG["IGUI_TREK_DistressHeader"]
               for d in draws if d.kind == "text"):
        failures.append("probes: a call is pending and the console does not "
                        "say so")
    lua.execute("""
        TREK.Probes.store().distress = nil
        local c = TREK.Probes.addContact("downedPersonnel", 2380, 2290, 0,
                                         "distress:9", true)
        c.name, c.division, c.deadline = "Maren Novak", "Operations", 72
    """)
    draws = run_frames(lua, "probes, a rescue under way")
    check_bounds(lua, draws, "probes, a rescue under way")
    if win.acceptBtn.enable:
        failures.append("probes: Accept is live while a rescue is under way "
                        "and no call is pending")
    if not any(IG["IGUI_TREK_RescueHeader"].split("%1")[0] in str(d.extra)
               for d in draws if d.kind == "text"):
        failures.append("probes: a rescue is under way and the console does "
                        "not show it or its clock")

    # Both bearings have to be real compass points rather than nil, which is
    # what math.atan2 would have produced here.
    bearing = lua.globals().TREK.ProbeUI.bearing
    for dx, dy, want in ((0, -10, "N"), (10, 0, "E"), (0, 10, "S"),
                         (-10, 0, "W"), (10, -10, "NE"), (-10, 10, "SW")):
        got = bearing(0, 0, dx, dy)
        if got != want:
            failures.append(f"probes: a contact {dx},{dy} away reads {got!r}, "
                            f"not {want!r}")

    lua.execute('''
        reachable = {}
        for _, row in ipairs(win.joypadButtonsY) do
            for _, b in ipairs(row) do reachable[b] = true end
        end
        unreachable = {}
        for _, c in ipairs(win.children) do
            if c.onclick and not reachable[c] and c ~= win.ISButtonB then
                table.insert(unreachable, c.title or "?")
            end
        end
    ''')
    unreachable = lua.globals().unreachable
    for i in range(1, len(unreachable) + 1):
        failures.append(f"probes: button {unreachable[i]!r} cannot be reached "
                        f"with a controller")

    print("probes: the sensor console draws an empty rack, a probe in flight "
          "with its bar, and a list of contacts at a bearing, greying each "
          "control for its own reason and leaving all of them on the stick")

    padd_screen()

    # --- the textures the console loads exist -----------------------------
    src = open(os.path.join(MOD, "media", "lua", "client", "TREK", "TREK_Helm.lua"),
               encoding="utf-8").read()
    for f in re.findall(r'load\(\s*"\w+"\s*,\s*"([\w.]+\.png)"', src):
        if not os.path.isfile(os.path.join(UI, f)):
            failures.append(f"TREK_Helm.lua loads media/ui/{f}, which does not exist")

    if failures:
        print(f"\n{len(failures)} PROBLEM(S):")
        for f in dict.fromkeys(failures):
            print("  " + f)
        sys.exit(1)
    print("\nthe helm console and the tricorder plot both draw cleanly, "
          "and every control works")


main()
