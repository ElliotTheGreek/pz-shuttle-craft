--[[ Shuttlecraft -- the Emergency Medical Hologram, in front of the player.

    The way in, the dialogue panel, the light he casts, the yes/no a patient
    is asked, and what the server says back. Everything here is presentation
    and everything here is a *request*: no body is written on this side, no
    crystal is spent, and the figure standing on the deck is the server's
    (TREK_EMH.lua for the rules both sides share, TREK_Server.lua for the
    handlers).

    **It is a dialogue, not a control panel**, and that is a requirement
    rather than a flourish. The Doctor speaks: a line at the top that changes
    with what he has been asked and what he found, above his portrait. Every
    action is a thing he says he is doing and then a thing he reports having
    done -- which is also, usefully, the only way a player can tell a
    treatment that worked from one that was refused in silence.

    **The way in is a right-click at the station**, registered on
    OnPreFillWorldObjectContextMenu rather than the later event the medical
    set uses. Build 42's menu builder returns early from the later event when
    the clicked square holds nothing it considers interactable, and a wall
    panel on a bare square is exactly that; the Pre- event is what TREK_Menu
    and the replicator already rely on in the cabin.

    And the option is keyed to **C.EmhMenuSpots**, a named set, because a
    right-click resolves to the floor square under the cursor and the Doctor
    is a tall model -- the replicator's first build could not be clicked at
    all for precisely this reason (DEV_GUIDE.md, *A right-click lands on the
    floor, not on the picture*).

    The lines are written for this mod: dry, impatient, competent, and not
    quoted from anything.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_EMH"
require "TREK/TREK_Medical"
require "TREK/TREK_Power"
require "TREK/TREK_Core"
require "TREK/TREK_Helm"
require "TREK/TREK_MedKit"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local E = TREK.EMH
local Med = TREK.Medical
local Core = TREK.Core
local H = TREK.Helm
local P = H.P

local M = {}
TREK.EMHUI = M

local function note(player, key, ...)
    U.note(player, getText(key, ...), 150, 210, 255)
end

local function warnNote(player, key, ...)
    U.note(player, getText(key, ...), 255, 150, 90)
end

-- What the last look found, per patient name. The panel draws from this for
-- anybody who is not you; your own body is read directly, every frame it is
-- asked for, because it is right there.
M.findings = {}

-- What he last said, as a translation key plus arguments.
M.line = { key = "IGUI_TREK_EmhGreeting" }

local function says(key, ...)
    M.line = { key = key, args = { ... } }
end

---------------------------------------------------------------------------
-- The light he casts
---------------------------------------------------------------------------
-- Scenery, per client, exactly like the cabin's lamps and the torpedo's:
-- a light source is not a synced world object, so each machine hangs its own
-- and takes it back. `s.emh` is the ship state it follows.
--
-- The handle matters: `removeLamppost` takes the IsoLightSource that
-- `addLamppost` handed back, not a position, and passing nil throws.
local light = nil

local function lightHim(on)
    local cell = U.cell()
    if not cell then return end
    if on and not light then
        local x, y = U.at(E.spot())
        light = U.try("emh.light", function()
            return cell:addLamppost(x, y, C.CabinZ, C.EmhLight.r, C.EmhLight.g,
                                    C.EmhLight.b, C.EmhLight.radius)
        end)
    elseif not on and light then
        local old = light
        light = nil
        U.try("emh.unlight", function() cell:removeLamppost(old) end)
    end
end

-- Whether he was up the last time this client looked, so the chime plays
-- once on the change rather than on every ship-state commit -- and the ship
-- commits about once a second while anybody is flying her.
local wasUp = false

local function onShipChange()
    local up = E.isUp()
    if up == wasUp then return end
    wasUp = up
    lightHim(up)
    if up then
        local player = U.player(0)
        if player and U.isInteriorPlayer(player) then
            U.try("emh.chime", function() player:playSound("TREK_EmhAppear") end)
        end
    end
end

TREK.Ship.onChange(onShipChange)

---------------------------------------------------------------------------
-- The panel
---------------------------------------------------------------------------
TREKEMHWindow = ISPanelJoypad:derive("TREKEMHWindow")

local EW, EH = 420, 560
local SIDE, TOPH, BOTH, PAD, RAD = 56, 26, 16, 14, 22
local FACE = 96

--- Cuts a label down until it fits. A patient's name comes from whatever
--- somebody typed at the login screen, so its length is not knowable here,
--- and a name that runs past its column is the kind of thing only a render
--- or tests/test_helm.py ever shows.
local function ellipsise(text, font, maxW)
    local tm = getTextManager()
    local out = tostring(text or "")
    if tm:MeasureStringX(font, out) > maxW then
        while #out > 1 and tm:MeasureStringX(font, out .. "...") > maxW do
            out = string.sub(out, 1, #out - 1)
        end
        out = out .. "..."
    end
    return out
end

function TREKEMHWindow:new(x, y, player)
    local o = ISPanelJoypad.new(self, x, y, EW, EH)
    o.player = player
    o.playerNum = U.try("emh.playerNum", function()
        return player:getPlayerNum()
    end) or 0
    o.background = false
    o.moveWithMouse = true
    o.patientIndex = 1
    return o
end

function TREKEMHWindow:createChildren()
    ISPanelJoypad.createChildren(self)
    local cx = SIDE + PAD
    local cw = self.width - cx - PAD

    self.closeBtn = TREKLcarsButton:new(self.width - 90, 0, 90, TOPH,
        getText("IGUI_TREK_Close"), self, TREKEMHWindow.close, P.violet)
    self.closeBtn.roundLeft = false
    self.closeBtn:initialise()
    self:addChild(self.closeBtn)

    self.lineY = TOPH + PAD
    self.faceY = self.lineY + 44
    self.findingsY = self.faceY + FACE + 12

    local btnH, gap = 28, 6
    local row3 = self.height - BOTH - PAD - btnH
    local row2 = row3 - gap - btnH
    local row1 = row2 - gap - btnH
    local row0 = row1 - gap - btnH

    -- Who is being treated. One button that steps through the people aboard,
    -- rather than a list: in single player there is exactly one of them, and
    -- a list box holding one row is furniture.
    self.patientBtn = TREKLcarsButton:new(cx, row0, cw, btnH, "", self,
        TREKEMHWindow.onPatient, P.blue)
    self.patientBtn:initialise()
    self:addChild(self.patientBtn)

    self.treatBtn = TREKLcarsButton:new(cx, row1, cw, btnH, "", self,
        TREKEMHWindow.onTreat, P.peach)
    self.treatBtn:initialise()
    self:addChild(self.treatBtn)

    -- **Cure gets the full width and the two short ones share a row.** It was
    -- the other way round and "Cure the infection (1 crystal)" measured 195
    -- pixels against a 165-pixel button: the label was drawn from x = -49 and
    -- ran off both ends of the panel. Caught by tests/test_helm.py, which is
    -- the only thing short of the game that can see it.
    self.cureBtn = TREKLcarsButton:new(cx, row2, cw, btnH, "", self,
        TREKEMHWindow.onCure, P.orange)
    self.cureBtn:initialise()
    self:addChild(self.cureBtn)

    self.readoutBtn = TREKLcarsButton:new(cx, row3, (cw - gap) / 2, btnH,
        getText("IGUI_TREK_EmhReadout"), self, TREKEMHWindow.onReadout, P.gold)
    self.readoutBtn:initialise()
    self:addChild(self.readoutBtn)

    self.dismissBtn = TREKLcarsButton:new(cx + (cw - gap) / 2 + gap, row3,
        (cw - gap) / 2, btnH, getText("IGUI_TREK_EmhDismiss"), self,
        TREKEMHWindow.onDismiss, P.lilac)
    self.dismissBtn:initialise()
    self:addChild(self.dismissBtn)

    -- Controller navigation, top to bottom, and B closes. Every control is on
    -- the stick: a panel that needs a mouse is a panel the Steam Deck cannot
    -- use, which is not optional here (DEV_GUIDE.md).
    self:insertNewLineOfButtons(self.patientBtn)
    self:insertNewLineOfButtons(self.treatBtn)
    self:insertNewLineOfButtons(self.cureBtn)
    self:insertNewLineOfButtons(self.readoutBtn, self.dismissBtn)
    self:setISButtonForB(self.closeBtn)

    self:refresh()
end

---------------------------------------------------------------------------
-- Who is being looked at
---------------------------------------------------------------------------
--- Everyone aboard, worked out **once a frame**.
---
--- E.patients() walks getOnlinePlayers(), and render, drawFindings and
--- patient() all want it. prerender runs first and is the only place it is
--- recomputed, so a frame costs one engine call rather than four -- and a
--- panel is open for as long as somebody is reading it.
function TREKEMHWindow:patients()
    if self.roster then return self.roster end
    self.roster = E.patients(self.player)
    return self.roster
end

function TREKEMHWindow:patient()
    local list = self:patients()
    if #list == 0 then return nil end
    local i = self.patientIndex
    if i < 1 or i > #list then i = 1 end
    return list[i]
end

--- True when the selected patient is this client's own character.
function TREKEMHWindow:isSelf()
    local row = self:patient()
    if not row then return true end
    return row.own == true
end

--- What is wrong with the selected patient.
---
--- **Your own body is read here; anybody else's arrives from the server.**
--- In multiplayer a remote player's BodyDamage does not exist on this client
--- to be read -- BodyDamage.Update() restores a remote body to full every
--- tick -- so the panel has no way to work out what is wrong with the
--- crewman on the biobed and has to be told (`emhLook`).
function TREKEMHWindow:found()
    local row = self:patient()
    if not row then return nil end
    if row.own then return E.findings(self.player) end
    return M.findings[row.name]
end

function TREKEMHWindow:refresh()
    local row = self:patient()
    if row and not row.own then
        -- Ask for the one thing this client cannot see for itself.
        Core.send(self.player, "emhLook", { who = row.name })
    end
end

function TREKEMHWindow:onPatient()
    local list = self:patients()
    if #list <= 1 then return end
    self.patientIndex = self.patientIndex + 1
    if self.patientIndex > #list then self.patientIndex = 1 end
    self:refresh()
end

---------------------------------------------------------------------------
-- Drawing
---------------------------------------------------------------------------
function TREKEMHWindow:prerender()
    -- A panel nobody is standing at closes itself. The server would refuse
    -- anyway, but a window that stays open and answers "too far" to every
    -- press reads as a broken machine. Vanilla's own ISFeedingTroughUI does
    -- exactly this, and twenty-six other panels close from inside a frame.
    if self.player and not E.inReachOf(self.player) then
        self:close()
        return
    end

    -- One walk of the player list per frame; see :patients().
    self.roster = nil

    local w, h = self.width, self.height
    self:drawRect(0, 0, w, h, 0.97, 0.008, 0.012, 0.028)

    local function block(x, y, bw, bh, c)
        self:drawRect(x, y, bw, bh, 1, c[1], c[2], c[3])
    end

    -- The helm's own furniture. Three Starfleet consoles in one mod should
    -- not look like three mods.
    H.pill(self, 0, 0, RAD * 2, RAD * 2, P.blue, true, true)
    block(RAD, 0, SIDE - RAD, RAD, P.blue)
    block(0, RAD, SIDE, 96 - RAD, P.blue)
    local title = string.upper(getText("IGUI_TREK_EmhTitle"))
    local closeX = self.closeBtn and self.closeBtn.x or (w - 90)
    block(SIDE, 0, math.max(0, closeX - 8 - SIDE), TOPH, P.blue)
    local fh = getTextManager():MeasureStringY(UIFont.Medium, title) or 14
    self:drawText(title, SIDE + 12, (TOPH - fh) / 2, 0, 0, 0, 1, UIFont.Medium)

    block(0, 100, SIDE, h - 130 - 100, P.violet)
    block(0, h - 130, SIDE, 130 - RAD, P.lilac)
    block(RAD, h - RAD, SIDE - RAD, RAD, P.lilac)
    H.pill(self, 0, h - RAD * 2, RAD * 2, RAD * 2, P.lilac, true, true)
    block(SIDE, h - BOTH, w - SIDE - BOTH / 2, BOTH, P.lilac)
end

--- His portrait, and the line he is saying.
function TREKEMHWindow:drawFace(cx, cw)
    local tex = M.portrait()
    if tex then
        self:drawTextureScaled(tex, cx, self.faceY, FACE, FACE, 1, 1, 1, 1)
    else
        -- The texture is optional, like every one of the helm's: a missing
        -- file degrades to a lit panel, never to an error.
        self:drawRect(cx, self.faceY, FACE, FACE, 0.5,
                      P.blue[1] * 0.4, P.blue[2] * 0.4, P.blue[3] * 0.4)
    end
    self:drawRectBorder(cx, self.faceY, FACE, FACE, 0.5,
                        P.blue[1], P.blue[2], P.blue[3])

    local line = getText(M.line.key, unpack(M.line.args or {}))
    local tx = cx + FACE + 12
    local tw = cw - FACE - 12
    local y = self.faceY
    -- Wrapped by hand into three lines: ISRichTextPanel would do it, and a
    -- rich-text panel inside a panel is a second element to keep on the
    -- stick for the sake of one paragraph.
    for _, part in ipairs(M.wrap(line, tw, 3)) do
        self:drawText(part, tx, y, P.text[1], P.text[2], P.text[3], 1, UIFont.Small)
        y = y + 16
    end
end

--- What is wrong with them, itemised, and whether they are infected.
function TREKEMHWindow:drawFindings(cx, cw)
    local y = self.findingsY
    local row = self:patient()
    local found = self:found()

    self:drawText(string.upper(getText("IGUI_TREK_EmhFindings")), cx, y,
                  P.gold[1], P.gold[2], P.gold[3], 1, UIFont.Small)
    y = y + 18

    if not row then
        self:drawText(getText("IGUI_TREK_EmhNoPatient"), cx, y,
                      P.dim[1] * 1.4, P.dim[2] * 1.4, P.dim[3] * 1.4, 1, UIFont.Small)
        return
    end
    if not found then
        -- Asked for and not yet answered. Said out loud rather than drawn as
        -- an empty box, which would read as "nothing wrong with them".
        self:drawText(getText("IGUI_TREK_EmhLooking"), cx, y,
                      P.dim[1] * 1.4, P.dim[2] * 1.4, P.dim[3] * 1.4, 1, UIFont.Small)
        return
    end

    if found.total == 0 then
        self:drawText(getText("IGUI_TREK_EmhNothingWrong"), cx, y,
                      P.blue[1], P.blue[2], P.blue[3], 1, UIFont.Small)
        y = y + 18
    else
        -- In the order the lists are written, so the readout reads the same
        -- way every time. Kahlua has no `next`, so pairs() over a map is not
        -- an option for an ordered list anyway.
        local shown = 0
        for _, key in ipairs(M.ORDER) do
            local n = found.items and found.items[key]
            if n and n > 0 and shown < 7 then
                shown = shown + 1
                self:drawText(getText(M.FINDING_TEXT[key] or key), cx + 8, y,
                              P.text[1], P.text[2], P.text[3], 1, UIFont.Small)
                self:drawTextRight(tostring(n), self.width - PAD, y,
                                   P.peach[1], P.peach[2], P.peach[3], 1,
                                   UIFont.Small)
                y = y + 16
            end
        end
    end

    -- **The infection, said out loud.** The medical tricorder deliberately
    -- will not tell you this; the Doctor is the thing that knows, and it is
    -- the reason a player opens the panel at all.
    y = y + 6
    local c = found.infected and P.red or P.blue
    self:drawText(string.upper(getText(found.infected
                                       and "IGUI_TREK_EmhInfected"
                                       or "IGUI_TREK_EmhClean")),
                  cx, y, c[1], c[2], c[3], 1, UIFont.Small)
end

function TREKEMHWindow:render()
    ISPanelJoypad.render(self)
    local cx = SIDE + PAD
    local cw = self.width - cx - PAD
    local off = E.isOff()

    self:drawFace(cx, cw)
    self:drawFindings(cx, cw)

    -- What the ship has left to work with. The crystals are here because
    -- that is what the cure costs, and the reserve because that is what a
    -- treatment costs -- a player who cannot see either cannot tell "he
    -- refused me" from "the ship is flat".
    local spares = TREK.Power.crystals()
    local reserve = math.floor(TREK.Power.reserve())
    local sc = spares > 0 and P.lilac or P.red
    self:drawText(getText("IGUI_TREK_EmhReserve", tostring(reserve),
                          tostring(C.PowerMax)),
                  cx, self.lineY, P.gold[1], P.gold[2], P.gold[3], 1, UIFont.Small)
    self:drawTextRight(spares > 0
                       and getText("IGUI_TREK_EmhCrystals", tostring(spares))
                       or getText("IGUI_TREK_EmhNoSpares"),
                       self.width - PAD, self.lineY, sc[1], sc[2], sc[3], 1,
                       UIFont.Small)

    -- The controls say what they will do before they are pressed, and grey
    -- themselves **with a reason** for exactly the reason the server would
    -- refuse. Both sides ask TREK_EMH, so they cannot drift.
    local row = self:patient()
    local name = row and row.name or "?"
    local list = self:patients()
    self.patientBtn.title = getText("IGUI_TREK_EmhPatient",
                                    ellipsise(name, UIFont.Small, cw - 120))
    self.patientBtn.enable = #list > 1

    local blocked = E.refusal(self.player)
    local patient = row and row.own and self.player or nil
    local treatWhy = blocked
    if not treatWhy and row and row.own then
        treatWhy = E.treatRefusal(self.player)
    elseif not treatWhy and row and not row.own then
        local found = self:found()
        if found and found.total == 0 then treatWhy = "emhWell" end
    end
    self.treatBtn.title = treatWhy
        and getText(M.BUTTON_TEXT[treatWhy] or "IGUI_TREK_EmhBtnWell")
        or getText("IGUI_TREK_EmhTreat", tostring(C.EmhTreatCost))
    self.treatBtn.enable = not off and treatWhy == nil

    local cureWhy = blocked
    if not cureWhy then
        if row and row.own then
            cureWhy = E.cureRefusal(self.player, row.name)
        else
            local found = self:found()
            if found and not found.infected then
                cureWhy = "emhNotInfected"
            elseif TREK.Power.crystals() < C.EmhCureCrystals then
                cureWhy = "emhNoCrystal"
            elseif row and E.cureDue(row.name) then
                cureWhy = "emhCuring"
            end
        end
    end
    self.cureBtn.title = cureWhy
        and getText(M.BUTTON_TEXT[cureWhy] or "IGUI_TREK_EmhBtnNotInfected")
        or getText("IGUI_TREK_EmhCure", tostring(C.EmhCureCrystals))
    self.cureBtn.enable = not off and cureWhy == nil

    -- The full readout is vanilla's health panel at doctor level, opened on
    -- this client. It is UI on a body, not a change to one, so there is no
    -- command behind it -- a handler whose only job is to answer "yes" is a
    -- round trip that can drift out of step with the panel that calls it.
    self.readoutBtn.enable = not off and row ~= nil
    self.dismissBtn.enable = true

    if off then
        self:drawText(getText("IGUI_TREK_EmhOff"), cx, self.height - BOTH - 42,
                      P.red[1], P.red[2], P.red[3], 1, UIFont.Small)
    end

    if self.joyfocus then
        self:drawTextRight(string.upper(getText("IGUI_TREK_MedJoypadHint")),
                           self.width - BOTH - 6, self.height - BOTH + 1,
                           0, 0, 0, 1, UIFont.Small)
    end
end

---------------------------------------------------------------------------
-- Controls
---------------------------------------------------------------------------
function TREKEMHWindow:onTreat()
    local row = self:patient()
    if not row then return end
    says(row.own and "IGUI_TREK_EmhOnIt" or "IGUI_TREK_EmhAsking", row.name)
    Core.send(self.player, "emhTreat", { who = row.own and "" or row.name })
end

function TREKEMHWindow:onCure()
    local row = self:patient()
    if not row then return end
    says(row.own and "IGUI_TREK_EmhCuringYou" or "IGUI_TREK_EmhAsking", row.name)
    Core.send(self.player, "emhCure", { who = row.own and "" or row.name })
end

--- Vanilla's health panel, at the Doctor level the medical tricorder uses.
---
--- Never `ISHealthPanel.cheat`: that global is `false or getDebug()` and
--- otherwise admin-only, so it would work under -debug and for nobody on the
--- Workshop. `panel.doctorLevel` on the instance is the real lever, and
--- TREK_MedKit already owns that call.
function TREKEMHWindow:onReadout()
    local row = self:patient()
    if not row then return end
    TREK.MedKit.openHealthPanel(self.player, row.player,
                                getText("IGUI_TREK_EmhReadoutTitle", row.name))
end

function TREKEMHWindow:onDismiss()
    Core.send(self.player, "emhDismiss", {})
    self:close()
end

function TREKEMHWindow:onGainJoypadFocus(joypadData)
    ISPanelJoypad.onGainJoypadFocus(self, joypadData)
    if self:getJoypadFocus() then
        self:restoreJoypadFocus(joypadData)
    else
        self:setJoypadFocusTopLeft(joypadData)
    end
end

function TREKEMHWindow:onLoseJoypadFocus(joypadData)
    ISPanelJoypad.onLoseJoypadFocus(self, joypadData)
    self:clearJoypadFocus(joypadData)
end

--- Closing the window does **not** dismiss him.
---
--- A crewman closing his own panel must not take the Doctor away from
--- somebody else standing at the biobed. The Dismiss button is the way to
--- put him away and it is the only one.
function TREKEMHWindow:close()
    M.window = nil
    if self.joyfocus then
        U.try("emh.releaseFocus", function() setJoypadFocus(self.playerNum, nil) end)
    end
    self:setVisible(false)
    self:removeFromUIManager()
end

---------------------------------------------------------------------------
-- The words
---------------------------------------------------------------------------
-- What each finding is called, in the order it is listed. The keys are
-- Med.TREATMENTS' and Med.SKIN's own, so a concern the Doctor stops treating
-- stops being drawn without anything here changing.
M.FINDING_TEXT = {
    bleeding      = "IGUI_TREK_TreatBleeding",
    deepWound     = "IGUI_TREK_TreatDeepWound",
    infectedWound = "IGUI_TREK_TreatInfectedWound",
    burn          = "IGUI_TREK_TreatBurn",
    fracture      = "IGUI_TREK_TreatFracture",
    pain          = "IGUI_TREK_TreatPain",
    stiffness     = "IGUI_TREK_TreatStiffness",
    health        = "IGUI_TREK_TreatHealth",
    cut           = "IGUI_TREK_SkinCut",
    scratch       = "IGUI_TREK_SkinScratch",
    stitches      = "IGUI_TREK_SkinStitches",
    bandage       = "IGUI_TREK_SkinBandage",
    glass         = "IGUI_TREK_EmhGlass",
    bullet        = "IGUI_TREK_EmhBullet",
}

M.ORDER = {
    "glass", "bullet", "deepWound", "bleeding", "cut", "scratch", "burn",
    "fracture", "infectedWound", "stitches", "bandage", "pain", "stiffness",
    "health",
}

-- Why a control is greyed, **on the control**, in two or three words.
--
-- Separate from the sentences below, and the separation is not decoration: a
-- button is 165 pixels wide and "The cure needs a whole dilithium crystal,
-- and there are none aboard" measures 435, so the label was drawn from
-- x = -49 and ran off both ends of the panel. Seen in tests/test_helm.py,
-- which is the only thing short of the game that can see it at all.
--
-- The long sentence is still the right thing to say -- it is what the menu's
-- tooltip and the halo note carry. It is just not a caption.
M.BUTTON_TEXT = {
    access         = "IGUI_TREK_EmhBtnAccess",
    emhOff         = "IGUI_TREK_EmhBtnOff",
    emhFar         = "IGUI_TREK_EmhBtnFar",
    emhNoPower     = "IGUI_TREK_EmhBtnNoPower",
    emhNoCrystal   = "IGUI_TREK_EmhBtnNoCrystal",
    emhNoPatient   = "IGUI_TREK_EmhBtnNoPatient",
    emhWell        = "IGUI_TREK_EmhBtnWell",
    emhNotInfected = "IGUI_TREK_EmhBtnNotInfected",
    emhCuring      = "IGUI_TREK_EmhBtnCuring",
}

-- Why a control is greyed, in the player's own words, keyed the way the
-- server's refusals are so the panel and the ship always agree. These are the
-- sentences: the menu's tooltip and the notes over a player's head.
M.REFUSAL_TEXT = {
    access         = "IGUI_TREK_NotCrew",
    emhOff         = "IGUI_TREK_EmhOff",
    emhFar         = "IGUI_TREK_EmhFar",
    emhNoPower     = "IGUI_TREK_EmhNoPower",
    emhNoCrystal   = "IGUI_TREK_EmhNoCrystal",
    emhNoPatient   = "IGUI_TREK_EmhNoPatient",
    emhWell        = "IGUI_TREK_EmhWell",
    emhNotInfected = "IGUI_TREK_EmhNotInfected",
    emhCuring      = "IGUI_TREK_EmhCuring",
}

--- Breaks a line into at most `lines` pieces that fit `width`.
---
--- By word, and the last piece is ellipsised rather than dropped: a sentence
--- that simply stops mid-word reads as a bug in the panel.
function M.wrap(text, width, lines)
    local tm = getTextManager()
    local out, current = {}, ""
    for word in string.gmatch(tostring(text or ""), "%S+") do
        local try = (current == "") and word or (current .. " " .. word)
        if tm:MeasureStringX(UIFont.Small, try) <= width then
            current = try
        else
            table.insert(out, current)
            current = word
            if #out >= lines then break end
        end
    end
    if #out < lines and current ~= "" then table.insert(out, current) end
    if #out > 0 then
        out[#out] = ellipsise(out[#out], UIFont.Small, width)
    end
    return out
end

--- His portrait, loaded once. Optional, like every texture in this mod.
local portraitTex, portraitTried = nil, false

function M.portrait()
    if portraitTried then return portraitTex end
    portraitTried = true
    portraitTex = U.try("emh.portrait", function()
        return getTexture("media/ui/TREK_EmhPortrait.png")
    end)
    if not portraitTex then
        U.warnOnce("emh.portrait", "the EMH portrait is missing")
    end
    return portraitTex
end

---------------------------------------------------------------------------
-- Opening it
---------------------------------------------------------------------------
function M.open(player)
    if M.window then
        U.try("emh.closeOld", function() M.window:close() end)
    end
    -- Opening is what brings him up, if he is not already standing. The panel
    -- is the way in and the way out: `emhSummon` here, `emhDismiss` on the
    -- button, and closing the window does neither.
    if not E.isUp() then
        says("IGUI_TREK_EmhGreeting")
        Core.send(player, "emhSummon", {})
    end

    local w = U.try("emh.open", function()
        local win = TREKEMHWindow:new(160, 110, player)
        win:initialise()
        win:instantiate()
        win:addToUIManager()
        return win
    end)
    if not w then return nil end
    M.window = w
    U.try("emh.focus", function()
        if JoypadState.players[w.playerNum + 1] then
            setJoypadFocus(w.playerNum, w)
        end
    end)
    return w
end

local function refreshWindow()
    if M.window then U.try("emh.refresh", function() M.window:refresh() end) end
end

---------------------------------------------------------------------------
-- The way in
---------------------------------------------------------------------------
function M.onConsult(_, player)
    M.open(player)
end

function M.fillMenu(playerIndex, context, worldobjects, test)
    local player = U.player(playerIndex)
    if not player then return end
    if not U.isInteriorPlayer(player) then return end
    if not TREK.Ship.canUse(player) then return end

    local x, y, z = U.clickedSquare(playerIndex, context, player)
    if not x or not E.isStation(x, y, z) then return end
    if test then return ISWorldObjectContextMenu.setTest() end

    local option = context:addOption(getText("IGUI_TREK_EmhConsult"),
                                     worldobjects, M.onConsult, player)

    -- **Shown and greyed, never hidden**, and with the reason on it. A
    -- missing option is indistinguishable from a broken mod, and the two
    -- cases that matter in play are both ones a player has to be told about:
    -- standing too far away, and a ship with no power left to project him.
    local why = E.refusal(player)
    if why then
        option.notAvailable = true
        option.toolTip = ISWorldObjectContextMenu.addToolTip()
        option.toolTip.description = getText(M.REFUSAL_TEXT[why]
                                             or "IGUI_TREK_EmhOff")
    end
    return true
end

Events.OnPreFillWorldObjectContextMenu.Add(M.fillMenu)

---------------------------------------------------------------------------
-- What the server says back
---------------------------------------------------------------------------
TREK.Net.onClient("emhFindings", function(args)
    if not args.who then return end
    M.findings[args.who] = {
        total = tonumber(args.total) or 0,
        infected = args.infected == true,
        bitten = args.bitten == true,
        items = args.items or {},
    }
end)

--- The consent prompt, on the **patient's** screen and nowhere else.
---
--- `ISModalDialog` is vanilla's own yes/no, with ordinary-player call sites
--- in ISTradingUI, ISInventoryPane and ISPostDeathUI. Nobody can force-heal,
--- or force-anything, another player: the offer is minted on the server, it
--- expires, it is single-use, and everything is re-validated when the answer
--- comes back.
TREK.Net.onClient("emhOffered", function(args)
    local player = U.player(0)
    if not player or not args.token then return end
    local text = getText(args.what == "cure" and "IGUI_TREK_EmhOfferCure"
                                             or "IGUI_TREK_EmhOfferTreat",
                         tostring(args.from), tostring(args.cost or "?"))
    U.try("emh.modal", function()
        local modal = ISModalDialog:new(0, 0, 360, 160, text, true, nil,
                                        M.onOffer, player:getPlayerNum(),
                                        args.token)
        modal:initialise()
        modal:addToUIManager()
        return modal
    end)
end)

function M.onOffer(_, button, token)
    local player = U.player(0)
    if not player then return end
    local yes = button and button.internal == "YES"
    Core.send(player, yes and "emhAccept" or "emhDecline", { token = token })
end

TREK.Net.onClient("emhTreated", function(args)
    local player = U.player(0)
    if not player then return end
    local total = tonumber(args.total) or 0
    if total == 0 then
        says("IGUI_TREK_EmhNothingToDo")
        note(player, "IGUI_TREK_EmhNothingToDo")
    else
        says("IGUI_TREK_EmhDone", tostring(total))
        note(player, "IGUI_TREK_EmhTreatedNote", tostring(total))
        U.try("emh.sound", function() player:playSoundLocal("TREK_DermalHum") end)
    end
    -- Your own findings are re-read from your own body next frame; somebody
    -- else's have to be asked for again.
    refreshWindow()
end)

TREK.Net.onClient("emhCureStarted", function(args)
    local player = U.player(0)
    if not player then return end
    says("IGUI_TREK_EmhStayAboard", tostring(args.hours or C.EmhCureHours))
    note(player, "IGUI_TREK_EmhCureStarted", tostring(args.hours or C.EmhCureHours))
    refreshWindow()
end)

--- The cure has landed. **This client clears what the packet cannot carry.**
---
--- `syncBodyPart` carries BodyPart fields only, so the BodyDamage flags and
--- the infection moodle do not ride it -- and the moodle matters more than it
--- looks: the block that writes CharacterStat.ZOMBIE_INFECTION runs *inside*
--- the infection countdown, and the countdown is gated on isInfected(). Clear
--- the infection and that block stops running, so the last value it wrote is
--- the value that stays on screen: a perfect cure with the player still being
--- told they are dying.
TREK.Net.onClient("emhCured", function()
    local player = U.player(0)
    if not player then return end

    local damage = Med.damageOf(player)
    if damage then
        U.try("emh.clearInfection", function()
            damage:setInfected(false)
            damage:setIsFakeInfected(false)
            damage:setReduceFakeInfection(false)
            damage:setInfectionTime(-1.0)
            damage:setInfectionMortalityDuration(-1.0)
        end)
    end
    U.try("emh.clearMoodle", function()
        player:getStats():set(CharacterStat.ZOMBIE_INFECTION, 0)
    end)

    says("IGUI_TREK_EmhCured")
    note(player, "IGUI_TREK_EmhCuredNote")
    U.try("emh.sound", function() player:playSoundLocal("TREK_EmhAppear") end)
    refreshWindow()
end)

TREK.Net.onClient("emhCureLost", function()
    local player = U.player(0)
    if not player then return end
    says("IGUI_TREK_EmhCureLost")
    warnNote(player, "IGUI_TREK_EmhCureLost")
    refreshWindow()
end)

return M
