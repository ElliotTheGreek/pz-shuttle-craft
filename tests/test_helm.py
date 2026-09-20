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
        if key not in IG:
            missing_keys.append(key)
            return key
        text = IG[key]
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

        haloNotes = {}
        player = { setHaloNote = function(self, text) table.insert(haloNotes, text) end,
                   getPlayerNum = function() return 0 end }

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


def main():
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
