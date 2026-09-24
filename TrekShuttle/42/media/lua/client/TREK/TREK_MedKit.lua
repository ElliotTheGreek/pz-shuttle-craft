--[[ Shuttlecraft -- the medical set, in the player's hands.

    The three instruments, and everything a player does with them:

      hypospray          a dose treats bleeding, deep wounds, infected cuts,
                         burns, fractures, pain, stiffness and tissue damage
                         on every part of your body at once. Not a bite, and
                         not the zombie infection -- see TREK_Medical.lua.
                         Six doses; the ship replicates more while you are
                         aboard and nothing does in the field.
      medical tricorder  vanilla's own health panel with its Doctor gates
                         opened, on yourself or -- with their consent -- on
                         somebody else.
      tricorder          a sliced sensor sweep of the cell's zombies, drawn
                         as a contact plot, and a lock override that asks the
                         server because a lock is world state.

    **How you use them is a right-click, and that is not laziness.** Build 42
    has no script hook for "using" an arbitrary item: the two routes that
    exist are a food item's eat action and a literature item's read action,
    and both consume or replace the thing. A tricorder is used and kept. So
    every one of these hangs off OnFillInventoryObjectContextMenu, which is
    the event vanilla's own comment calls the way "to add items to context
    menu without mod conflicts".

    **Everything here is client-side except the lock.** A character's body
    damage belongs to the client that owns them and syncs from there, exactly
    as their position does (MULTIPLAYER.md), so treating yourself and reading
    your own vitals need no protocol at all. A lock is a world object, so it
    is a validated command and the server does the opening.

    **The panels work with a controller**, because every panel in this mod
    has to (DEV_GUIDE.md). The sweep panel is an ISPanelJoypad built from the
    helm's own LCARS parts. The health panel needed no work at all and this
    is worth writing down, because MEDICAL_SET.md guessed the other way:
    `ISHealthPanel = ISPanelJoypad:derive("ISHealthPanel")` -- it already has
    stick navigation, A to act and B to close, and vanilla's own medical check
    hands it the joypad focus. We copy that.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Medical"
require "TREK/TREK_Core"
require "TREK/TREK_Helm"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Med = TREK.Medical
local Core = TREK.Core
local H = TREK.Helm
local P = H.P

local M = {}
TREK.MedKit = M

local function note(player, key, ...)
    U.note(player, getText(key, ...), 150, 210, 255)
end

local function warnNote(player, key, ...)
    U.note(player, getText(key, ...), 255, 150, 90)
end

---------------------------------------------------------------------------
-- The hypospray
---------------------------------------------------------------------------
-- Which treatment gets which word in the report. A dose that fixed four
-- things should say which four: "administered" on its own is the silent
-- half-success this mod keeps paying for, one step up from a setter that
-- quietly did nothing.
local TREAT_TEXT = {
    bleeding      = "IGUI_TREK_TreatBleeding",
    deepWound     = "IGUI_TREK_TreatDeepWound",
    infectedWound = "IGUI_TREK_TreatInfectedWound",
    burn          = "IGUI_TREK_TreatBurn",
    fracture      = "IGUI_TREK_TreatFracture",
    pain          = "IGUI_TREK_TreatPain",
    stiffness     = "IGUI_TREK_TreatStiffness",
    health        = "IGUI_TREK_TreatHealth",
}

--- "bleeding, burns, tissue damage" -- in Med.TREATMENTS order, so the list
--- reads the same way every time rather than in whatever order pairs() felt
--- like. (Kahlua has no `next`, so pairs() over a map is not an option here
--- anyway -- DEV_GUIDE.md, "The game runs Lua 5.1".)
local function summarise(counts)
    local parts = {}
    for _, t in ipairs(Med.TREATMENTS) do
        if (counts[t.key] or 0) > 0 and TREAT_TEXT[t.key] then
            table.insert(parts, getText(TREAT_TEXT[t.key]))
        end
    end
    return table.concat(parts, ", ")
end

--- Uses one hypospray on its carrier. Returns true when a dose was spent.
---
--- The order matters and is the whole design: a dose is only spent when
--- there was something to treat *and* the treatment took. A hypospray
--- emptied into a healthy arm is the kind of small cruelty that makes a
--- player stop carrying the item.
function M.useHypospray(player, item)
    if not player or not item then return false end

    local left = Med.doses(item)
    if left <= 0 then
        warnNote(player, "IGUI_TREK_HypoEmpty")
        return false
    end

    if not Med.needsTreatment(player) then
        note(player, "IGUI_TREK_HypoNothing")
        return false
    end

    local counts = Med.treat(player)
    if counts.total == 0 then
        -- Something was wrong a moment ago and no setter took. That is an
        -- engine call refusing, not a healthy player, so it is a warning.
        U.warnOnce("hypo.noEffect", "a hypospray dose changed nothing")
        warnNote(player, "IGUI_TREK_HypoNothing")
        return false
    end

    Med.setDoses(item, left - 1)
    U.try("hypo.sound", function() player:playSoundLocal("TREK_HypoHiss") end)
    note(player, "IGUI_TREK_HypoTreated", summarise(counts))
    U.log("hypospray: %d treatments, %d doses left", counts.total, left - 1)
    return true
end

---------------------------------------------------------------------------
-- The dermal regenerator
---------------------------------------------------------------------------
-- No charges, no cooldown, no doses. It is a powered instrument, not a drug,
-- and the hypospray already owns the ration economy; giving this one the same
-- thing would make them the same item twice. What keeps it from replacing the
-- hypospray is scope -- it closes what is open and treats nothing that is
-- injected -- and the one thing it refuses outright.
local REGEN_TEXT = {
    cut       = "IGUI_TREK_SkinCut",
    scratch   = "IGUI_TREK_SkinScratch",
    deepWound = "IGUI_TREK_TreatDeepWound",
    bleeding  = "IGUI_TREK_TreatBleeding",
    burn      = "IGUI_TREK_TreatBurn",
    stitches  = "IGUI_TREK_SkinStitches",
    bandage   = "IGUI_TREK_SkinBandage",
    health    = "IGUI_TREK_TreatHealth",
}

local function summariseSkin(counts)
    local parts = {}
    for _, t in ipairs(Med.SKIN) do
        if (counts[t.key] or 0) > 0 and REGEN_TEXT[t.key] then
            table.insert(parts, getText(REGEN_TEXT[t.key]))
        end
    end
    return table.concat(parts, ", ")
end

--- Runs the regenerator over its carrier. Returns true when skin closed.
function M.useDermalRegen(player, item)
    if not player or not item then return false end

    if not Med.needsTreatment(player, Med.SKIN, Med.obstructed) then
        -- Distinguish "you are not hurt" from "I cannot work on that": a
        -- player whose only injury is full of glass would otherwise be told
        -- there is nothing wrong with them.
        if Med.needsTreatment(player, Med.SKIN) then
            warnNote(player, "IGUI_TREK_SkinObstructed")
        else
            note(player, "IGUI_TREK_SkinNothing")
        end
        return false
    end

    local counts = Med.regenerate(player)
    if counts.total == 0 then
        U.warnOnce("regen.noEffect", "a dermal regenerator pass changed nothing")
        note(player, "IGUI_TREK_SkinNothing")
        return false
    end

    U.try("regen.sound", function() player:playSoundLocal("TREK_DermalHum") end)
    note(player, "IGUI_TREK_SkinClosed", summariseSkin(counts))
    if counts.skipped > 0 then
        -- Said out loud rather than left as a silent gap. A limb that did not
        -- heal and was never mentioned reads as a broken mod.
        warnNote(player, "IGUI_TREK_SkinObstructed")
    end
    U.log("dermal regenerator: %d closed, %d site(s) obstructed",
          counts.total, counts.skipped)
    return true
end

---------------------------------------------------------------------------
-- Refilling, aboard
---------------------------------------------------------------------------
-- The ship makes them, so the ship is where they come back. Same reasoning
-- as the sink's water: a Starfleet shuttle is not resupplied from Kentucky.
--
-- Deliberately not a timer on the item. A hypospray that refilled itself
-- wherever you left it would make the dose limit a delay rather than a
-- decision, and the decision -- push on with two doses, or go home -- is the
-- only interesting thing about the number.
local refillTick = 0

function M.serviceRefill(player)
    if not player or not U.isInteriorPlayer(player) then return 0 end
    local filled = 0
    for _, item in ipairs(Med.carried(player, C.HyposprayType, C.HyposprayItem)) do
        local left = Med.doses(item)
        if left < C.HyposprayDoses then
            Med.setDoses(item, left + 1)
            filled = filled + 1
        end
    end
    if filled > 0 then U.debug("hypospray: replicated a dose into %d", filled) end
    return filled
end

---------------------------------------------------------------------------
-- The medical tricorder
---------------------------------------------------------------------------
--- Opens vanilla's health panel on a patient with every Doctor gate open.
---
--- `panel.doctorLevel`, never `ISHealthPanel.cheat`. The global is
--- `false or getDebug()` and otherwise admin-only: it would work under -debug
--- and for nobody on the Workshop. The field is per-instance, is the number
--- every gate in that file already consults, and is assigned exactly once at
--- construction -- so setting it after :new() is the supported thing to do,
--- and it is what vanilla's own ISMedicalCheckAction does with the doctor's
--- real perk level.
function M.openHealthPanel(player, patient, title)
    if not player or not patient then return nil end

    local playerNum = U.try("med.playerNum", function()
        return player:getPlayerNum()
    end) or 0
    local x = U.try("med.screenLeft", function()
        return getPlayerScreenLeft(playerNum) + 70
    end) or 70
    local y = U.try("med.screenTop", function()
        return getPlayerScreenTop(playerNum) + 50
    end) or 50

    local panel = U.try("med.panel", function()
        local p = ISHealthPanel:new(patient, x, y, 400, 400)
        p:initialise()
        return p
    end)
    if not panel then return nil end

    panel.doctorLevel = C.MedDoctorLevel

    local window = U.try("med.wrap", function()
        local w = panel:wrapInCollapsableWindow(title, false)
        w:addToUIManager()
        return w
    end)
    if not window then return nil end

    -- A controller has to be able to drive it, and vanilla's medical check
    -- hands the focus over exactly like this.
    U.try("med.joypad", function()
        if JoypadState.players[playerNum + 1] then
            JoypadState.players[playerNum + 1].focus = panel
            updateJoypadFocus(JoypadState.players[playerNum + 1])
        end
    end)

    U.log("medical tricorder: panel open at doctor level %d", C.MedDoctorLevel)
    return panel, window
end

function M.scanSelf(player)
    local name = U.try("med.ownName", function()
        return player:getDescriptor():getForename()
    end) or ""
    M.openHealthPanel(player, player, getText("IGUI_TREK_MedScanTitle", name))
end

--- Asks another player to be scanned.
---
--- Through the engine's own consent flow, not around it. `requestMedicalCheck`
--- raises a yes/no on the other player's screen and only a yes reaches
--- ISMedicalCheckAction -- and a mod that reads somebody's body without
--- asking is a different kind of mod. The tricorder's contribution is the
--- Doctor level, which M.upgradeMedicalCheck puts on the panel that flow
--- eventually opens.
---
--- Offered only on a real client: single player has nobody else in it.
function M.scanOther(player, other)
    if not isClient() then return false end
    return U.try("med.request", function()
        requestMedicalCheck(other, player)
        return true
    end) == true
end

--- Raises the Doctor level on the panel vanilla's medical check just opened,
--- when the doctor is carrying a medical tricorder.
---
--- A wrapper rather than a reimplementation, because that action does five
--- other things -- the anim, the consent, the body-damage subscription, the
--- window bookkeeping, the joypad focus -- and every one of them is work we
--- would otherwise be copying and then failing to keep up to date.
---
--- **The reading is taken before calling through**, which is the lesson the
--- radial menu cost (DEV_GUIDE.md, "A hook on a toggle must ask before it
--- calls through"): by the time the original returns, `self.otherPlayer` is
--- still there but the health-window table has been rewritten, and reaching
--- for the doctor afterwards would be reading state the call had changed.
local baseMedicalPerform = nil

function M.upgradeMedicalCheck(action)
    local doctor = action and action.character
    local patient = action and action.otherPlayer
    local carrying = doctor
        and Med.carries(doctor, C.MedTricorderType, C.MedTricorderItem) ~= nil

    baseMedicalPerform(action)

    if not (carrying and patient) then return end
    U.try("med.upgrade", function()
        local window = ISMedicalCheckAction.getHealthWindowForPlayer(patient)
        local panel = window and window.nested
        if not panel then return end
        panel.doctorLevel = C.MedDoctorLevel
        U.log("medical tricorder: raised a medical check to doctor level %d",
              C.MedDoctorLevel)
    end)
end

-- Installed once, and only if the action is really there: a wrapper that
-- assumes a vanilla file exists is a crash in the one build where it moved.
if ISMedicalCheckAction and ISMedicalCheckAction.perform then
    baseMedicalPerform = ISMedicalCheckAction.perform
    ISMedicalCheckAction.perform = function(action) M.upgradeMedicalCheck(action) end
end

---------------------------------------------------------------------------
-- The tricorder: the sensor sweep
---------------------------------------------------------------------------
-- Sliced, with a cursor, for the reason the landing search is sliced: the
-- cell's zombie list is a few hundred long on a quiet day and several
-- thousand in a horde, and classifying all of them in one frame is not slow,
-- it is the hard lock described in DEV_GUIDE.md.
--
-- The sweep reads `cell:getZombieList()`, which TREK_Core's shields already
-- walk every tick, so the call itself is proven in this mod and in game.
-- What it reports is every zombie the client is simulating within range,
-- which on a server is not quite every zombie there is -- a contact list is
-- honest about being a sensor reading rather than omniscience.

local sweep = nil     -- { player, list, n, i, contacts, counts, radius2 }

--- 1, 2 or 3: close, middle or far, by the fractions in C.SweepBands.
local function band(dist)
    local r = C.SweepRadius
    if dist <= r * C.SweepBands[1] then return 1 end
    if dist <= r * C.SweepBands[2] then return 2 end
    return 3
end

--- Starts a sweep. Returns false when one is already running or the last one
--- finished a moment ago.
---
--- Both halves are needed. "One at a time" alone is not a limit: against two
--- or three zombies a sweep finishes inside a single tick, so the button
--- could be held down and would chirp every frame. C.SweepIntervalMs is what
--- makes it an instrument being read rather than a key being mashed.
--- Whether this sweep is being taken from a seat in the shuttle.
---
--- It matters because **a sweep reads the deck it is standing on**, and three
--- levels up that deck is empty sky: every zombie in the county is at z 0 and
--- every crystal with them, so the honest answer from the cockpit at cruise
--- was "nothing anywhere". From a seat the instrument reads *downwards*
--- instead, every level from the ground up to the ship.
---
--- **No check for whether she is flying**, deliberately. One was written and
--- then deleted: a shuttle on the ground sits at level zero, so "every level
--- below the seat" and "the level the seat is on" are the same sweep, and the
--- branch could not change an outcome. See DEV_GUIDE.md, *A branch a mutation
--- cannot break may be unreachable*.
---
--- A seat, and not simply being aboard. A crewman aft during the same flight
--- is in the cabin, which is a room in the void nowhere near the ground the
--- ship is passing over, and reading a town from in there would be a lie.
local function inShuttleSeat(player)
    local vehicle = U.try("sweep.vehicle", function() return player:getVehicle() end)
    return TREK.Vehicle ~= nil and TREK.Vehicle.isShuttle(vehicle) == true
end

function M.startSweep(player)
    if not player then return false end
    if sweep then return false end

    local now = getTimestampMs()
    if M.lastSweepAt and now - M.lastSweepAt < C.SweepIntervalMs then
        return false
    end
    M.lastSweepAt = now

    local cell = U.cell()
    if not cell then return false end
    local list = U.try("sweep.zombieList", function()
        return cell:getZombieList()
    end)
    if not list then return false end
    local n = U.try("sweep.count", function() return list:size() end) or 0

    -- On foot this is one level, the one under the player, and everything
    -- below behaves exactly as it did. In the air it is every level from the
    -- ground up to the ship.
    local top = math.floor(player:getZ())
    local bottom = inShuttleSeat(player) and 0 or top

    sweep = {
        player = player,
        list = list,
        n = n,
        i = 0,
        x = player:getX(),
        y = player:getY(),
        z = top,
        zTop = top,
        zBottom = bottom,
        contacts = {},
        counts = { 0, 0, 0 },
        total = 0,
        -- The mineral pass, which runs after the lifesigns are done. It walks
        -- *squares* rather than a list the engine already keeps, so it has
        -- its own cursor over the box and is sliced at the same rate.
        crystals = {},
        crystalTotal = 0,
        sx = -C.CrystalScanRadius,
        sy = -C.CrystalScanRadius,
        sz = bottom,
        minerals = false,
    }
    U.try("sweep.sound", function() player:playSoundLocal("TREK_TricorderChirp") end)
    return true
end

--- Everything a square is carrying, dilithium-wise: crystals lying on the
--- ground and crystals inside anything standing on it.
---
--- Containers as well as the floor, because that is where loot actually is --
--- a crystal in a jeweller's case is the find the tricorder exists to make,
--- and one that only saw dropped items would be a tool for finding things
--- somebody had already found.
local function crystalsOnSquare(sq, join)
    local found = 0
    join(function()
        local items = sq:getWorldObjects()
        local n = items and items:size() or 0
        for i = 0, n - 1 do
            local w = items:get(i)
            local it = w and w:getItem()
            if it and it:getFullType() == C.DilithiumItem then found = found + 1 end
            -- The ship's own core reads like any other cache. It holds its
            -- crystals as a number rather than as items, so there is nothing
            -- on the square for the loop above to find -- and a tricorder
            -- that could not see the ship's own dilithium would be a strange
            -- instrument to carry aboard her.
            if it and it:getFullType() == C.WarpCoreItem then
                found = found + (TREK.Power and TREK.Power.crystals() or 0)
            end
        end
    end)
    join(function()
        local objects = sq:getObjects()
        local n = objects and objects:size() or 0
        for i = 0, n - 1 do
            local o = objects:get(i)
            local container = o and (o:getContainer() or o:getItemContainer())
            if container then
                local list = container:getAllTypeRecurse(C.DilithiumType)
                local held = list and list:size() or 0
                for k = 0, held - 1 do
                    local it = list:get(k)
                    if it and it:getFullType() == C.DilithiumItem then
                        found = found + 1
                    end
                end
            end
        end
    end)
    return found
end

--- One slice of the mineral pass. Returns true while it is still running.
local function serviceMinerals()
    local join = U.batch("sweep.minerals")
    local done = 0
    local r = C.CrystalScanRadius
    local px, py = math.floor(sweep.x), math.floor(sweep.y)

    while done < C.SweepPerTick do
        -- The cursor runs over a box per level, lowest first, and the sweep
        -- is finished when it walks off the top one. On foot that is a single
        -- level and the loop is what it always was.
        if sweep.sy > r then
            sweep.sz = sweep.sz + 1
            sweep.sx, sweep.sy = -r, -r
        end
        if sweep.sz > sweep.zTop then return false end
        local pz = sweep.sz
        local dx, dy = sweep.sx, sweep.sy
        -- advance the cursor first, so an early `return` below can never
        -- leave it standing on the same square for ever
        sweep.sx = sweep.sx + 1
        if sweep.sx > r then
            sweep.sx = -r
            sweep.sy = sweep.sy + 1
        end
        done = done + 1

        local dist = math.sqrt(dx * dx + dy * dy)
        if dist <= r then
            -- nil means "that chunk is not loaded", which is not the same as
            -- "nothing there" -- the tricorder simply cannot see that far
            -- into unstreamed ground, and says nothing about it.
            local sq = U.square(px + dx, py + dy, pz, false)
            if sq then
                local n = crystalsOnSquare(sq, join)
                if n > 0 then
                    sweep.crystalTotal = sweep.crystalTotal + n
                    table.insert(sweep.crystals, { dx = dx, dy = dy, n = n })
                end
            end
        end
    end
    return true
end

--- The downed ensign relative to this sweep, if they are in range; nil if not.
---
--- ROADMAP2: "Long-range systems locate the region; the tricorder locates
--- the person." Their square is already in the contact store every client
--- holds, so this is arithmetic, not a search -- and it is their *true* square,
--- where the map only ever draws the long-range circle.
local function personnelFix(sw)
    local m = TREK.Probes and TREK.Probes.mission()
    if not m then return nil end
    local x, y = m.ex or m.tx, m.ey or m.ty
    local z = m.ez or m.tz or 0
    if not x or not y then return nil end
    if z < sw.zBottom or z > sw.zTop then return nil end
    local dx, dy = x + 0.5 - sw.x, y + 0.5 - sw.y
    local dist = math.sqrt(dx * dx + dy * dy)
    if dist > C.SweepRadius then return nil end
    return { dx = dx, dy = dy, dist = math.floor(dist + 0.5),
             compass = U.compass(sw.x, sw.y, x + 0.5, y + 0.5),
             name = m.name }
end

--- The nearest holo fragment the ship has put on the ground, relative to
--- this sweep, if one is in range (LORE.md 1c). The same arithmetic as the
--- ensign's: the ship knows the exact square it placed the fragment on, and
--- every client holds the contact store.
local function clueFix(sw)
    if not TREK.Probes then return nil end
    local best = nil
    for _, c in ipairs(TREK.Probes.contacts()) do
        if c.kind == "clue" and c.placed and not TREK.Probes.isResolved(c.status)
           and (c.z or 0) >= sw.zBottom and (c.z or 0) <= sw.zTop then
            local dx, dy = c.x + 0.5 - sw.x, c.y + 0.5 - sw.y
            local dist = math.sqrt(dx * dx + dy * dy)
            if dist <= C.SweepRadius and (not best or dist < best.dist) then
                best = { dx = dx, dy = dy, dist = dist, n = c.fragment,
                         compass = U.compass(sw.x, sw.y, c.x + 0.5, c.y + 0.5) }
            end
        end
    end
    if best then best.dist = math.floor(best.dist + 0.5) end
    return best
end

--- One slice. Returns true while the sweep is still running.
function M.serviceSweep()
    if not sweep then return false end
    if sweep.minerals then
        if serviceMinerals() then return true end
        local result = {
            contacts = sweep.contacts,
            counts = sweep.counts,
            total = sweep.total,
            radius = C.SweepRadius,
            crystals = sweep.crystals,
            crystalTotal = sweep.crystalTotal,
            crystalRadius = C.CrystalScanRadius,
            -- Read from the air, looking down, rather than along the deck.
            -- The panel says so: a plot that silently means something else is
            -- worse than one that found nothing.
            aloft = sweep.zBottom < sweep.zTop,
            -- Carried on the result rather than read back off `sweep`, which
            -- is nil by the time anything below wants them.
            zBottom = sweep.zBottom,
            zTop = sweep.zTop,
            -- A Starfleet life sign, drawn apart from every other contact.
            personnel = personnelFix(sweep),
            -- A holo fragment on the ground, found by its fix.
            clue = clueFix(sweep),
        }
        M.lastSweep = result
        sweep = nil
        if M.window then M.window:onSweepDone(result) end
        U.log("sensor sweep: %d contacts within %d tiles, %d dilithium "
              .. "trace(s) within %d, levels %d..%d", result.total,
              result.radius, result.crystalTotal, result.crystalRadius,
              result.zBottom, result.zTop)
        return false
    end

    local join = U.batch("sweep.classify")
    local done = 0
    local radius = C.SweepRadius
    while sweep.i < sweep.n and done < C.SweepPerTick do
        local i = sweep.i
        sweep.i = i + 1
        done = done + 1
        join(function()
            local z = sweep.list:get(i)
            if not z then return end
            local zz = math.floor(z:getZ())
            if zz < sweep.zBottom or zz > sweep.zTop then return end
            local dx, dy = z:getX() - sweep.x, z:getY() - sweep.y
            local dist = math.sqrt(dx * dx + dy * dy)
            if dist > radius then return end
            local b = band(dist)
            sweep.counts[b] = sweep.counts[b] + 1
            sweep.total = sweep.total + 1
            table.insert(sweep.contacts, { dx = dx, dy = dy, band = b })
        end)
    end

    if sweep.i < sweep.n then return true end

    -- Lifesigns done; the same sweep keeps going and looks for dilithium.
    sweep.minerals = true
    return true
end

--- Whether a sweep is running, for the panel and for the tests.
function M.sweeping()
    return sweep ~= nil
end

---------------------------------------------------------------------------
-- The tricorder: the contact plot
---------------------------------------------------------------------------
TREKTricorderWindow = ISPanelJoypad:derive("TREKTricorderWindow")

local TW, TH = 360, 470
local SIDE, TOPH, BOTH, PAD, R = 56, 26, 16, 14, 22
local PLOT = 210

function TREKTricorderWindow:new(x, y, player)
    local o = ISPanelJoypad.new(self, x, y, TW, TH)
    o.player = player
    o.playerNum = U.try("sweep.playerNum", function()
        return player:getPlayerNum()
    end) or 0
    o.background = false
    o.moveWithMouse = true
    o.result = M.lastSweep
    return o
end

function TREKTricorderWindow:createChildren()
    ISPanelJoypad.createChildren(self)

    self.closeBtn = TREKLcarsButton:new(self.width - 90, 0, 90, TOPH,
        getText("IGUI_TREK_Close"), self, TREKTricorderWindow.close, P.violet)
    self.closeBtn.roundLeft = false
    self.closeBtn:initialise()
    self:addChild(self.closeBtn)

    self.plotX = SIDE + PAD
    self.plotY = TOPH + PAD + 18
    self.listY = self.plotY + PLOT + 12

    local btnH = 28
    self.sweepBtn = TREKLcarsButton:new(SIDE + PAD, self.height - BOTH - PAD - btnH,
        self.width - SIDE - PAD * 2, btnH,
        getText("IGUI_TREK_SweepAgain"), self, TREKTricorderWindow.onSweep, P.gold)
    self.sweepBtn:initialise()
    self:addChild(self.sweepBtn)

    self:insertNewLineOfButtons(self.sweepBtn)
    self:setISButtonForB(self.closeBtn)
end

--- The frame, in the helm's LCARS: one elbow top and bottom, a sidebar
--- between them. Deliberately the same furniture as the helm console -- two
--- Starfleet instruments in one mod should not look like two mods.
function TREKTricorderWindow:prerender()
    local w, h = self.width, self.height
    self:drawRect(0, 0, w, h, 0.97, 0.008, 0.012, 0.028)

    local function block(x, y, bw, bh, c)
        self:drawRect(x, y, bw, bh, 1, c[1], c[2], c[3])
    end

    -- top elbow
    H.pill(self, 0, 0, R * 2, R * 2, P.gold, true, true)
    block(R, 0, SIDE - R, R, P.gold)
    block(0, R, SIDE, 90 - R, P.gold)
    local title = string.upper(getText(
        self.result and self.result.aloft and "IGUI_TREK_SweepTitleAloft"
        or "IGUI_TREK_SweepTitle"))
    local closeX = self.closeBtn and self.closeBtn.x or (w - 90)
    block(SIDE, 0, math.max(0, closeX - 8 - SIDE), TOPH, P.gold)
    local fh = getTextManager():MeasureStringY(UIFont.Medium, title) or 14
    self:drawText(title, SIDE + 12, (TOPH - fh) / 2, 0, 0, 0, 1, UIFont.Medium)

    -- sidebar and bottom elbow
    block(0, 90 + 4, SIDE, h - 120 - 90, P.violet)
    block(0, h - 120, SIDE, 120 - R, P.lilac)
    block(R, h - R, SIDE - R, R, P.lilac)
    H.pill(self, 0, h - R * 2, R * 2, R * 2, P.lilac, true, true)
    block(SIDE, h - BOTH, w - SIDE - BOTH / 2, BOTH, P.lilac)
end

--- The plot: you at the centre, contacts around you, north up.
---
--- Drawn rather than plotted into the world. Nothing here touches a square,
--- which is the same rule the torpedo's flight follows -- a client that draws
--- can leave nothing behind, and a client that places can.
function TREKTricorderWindow:drawPlot()
    local x, y, s = self.plotX, self.plotY, PLOT
    local cx, cy = x + s / 2, y + s / 2
    local half = s / 2 - 6

    self:drawRect(x, y, s, s, 0.55, 0.01, 0.02, 0.05)
    self:drawRectBorder(x, y, s, s, 0.6, P.lilac[1], P.lilac[2], P.lilac[3])

    -- range rings, one per band, plus the cross-hairs
    local bands = { C.SweepBands[1], C.SweepBands[2], 1.0 }
    for _, f in ipairs(bands) do
        local rr = half * f
        self:drawRectBorder(cx - rr, cy - rr, rr * 2, rr * 2, 0.22,
                            P.blue[1], P.blue[2], P.blue[3])
    end
    self:drawRect(cx, y + 6, 1, s - 12, 0.18, P.blue[1], P.blue[2], P.blue[3])
    self:drawRect(x + 6, cy, s - 12, 1, 0.18, P.blue[1], P.blue[2], P.blue[3])

    -- you
    self:drawRect(cx - 2, cy - 2, 5, 5, 1, P.white[1], P.white[2], P.white[3])

    local result = self.result
    if not result then return end
    local colours = { P.red, P.orange, P.gold }
    for _, c in ipairs(result.contacts) do
        -- The plot is north-up and the world's y grows south, so the sign on
        -- dy is flipped here and nowhere else.
        local px = cx + (c.dx / result.radius) * half
        local py = cy + (c.dy / result.radius) * half
        local col = colours[c.band] or P.red
        self:drawRect(px - 1.5, py - 1.5, 4, 4, 0.95, col[1], col[2], col[3])
    end

    -- Dilithium, drawn **differently rather than just in another colour**: a
    -- crystal is the thing a player opens this panel to find, and a fourth
    -- shade of dot among three would be one more thing to squint at. A
    -- lifesign is a small square; a crystal is a ring with a bright middle.
    --
    -- Its range is shorter than the lifesign sweep's, so it is plotted
    -- against its own radius -- otherwise every trace would huddle in the
    -- middle of the plot and look further away than it is.
    local crystals = result.crystals or {}
    local cr = result.crystalRadius or C.CrystalScanRadius
    for _, c in ipairs(crystals) do
        local px = cx + (c.dx / cr) * half
        local py = cy + (c.dy / cr) * half
        self:drawRectBorder(px - 3.5, py - 3.5, 8, 8, 0.95,
                            P.white[1], P.white[2], P.white[3])
        self:drawRect(px - 1.5, py - 1.5, 4, 4, 1,
                      P.violet[1], P.violet[2], P.violet[3])
    end

    -- **The ensign**, as a cross -- a third shape, not a third shade, for the
    -- reason the crystal is a ring: the ensign is the thing the panel was opened
    -- to find, and must not be mistaken for the dead walking toward them.
    local f = result.personnel
    if f then
        local px = cx + (f.dx / result.radius) * half
        local py = cy + (f.dy / result.radius) * half
        self:drawRect(px - 5, py - 1, 11, 3, 1, P.blue[1], P.blue[2], P.blue[3])
        self:drawRect(px - 1, py - 5, 3, 11, 1, P.blue[1], P.blue[2], P.blue[3])
        self:drawRect(px, py, 1, 1, 1, P.white[1], P.white[2], P.white[3])
    end

    -- **A holo fragment**, as a square frame round a lit centre: a fourth
    -- shape, for the reason there is a third -- a thing the player came here
    -- for must not read as one more dot.
    local g = result.clue
    if g then
        local px = cx + (g.dx / result.radius) * half
        local py = cy + (g.dy / result.radius) * half
        self:drawRectBorder(px - 5, py - 5, 11, 11, 1, 0.31, 0.84, 0.94)
        self:drawRect(px - 2, py - 2, 5, 5, 1, 0.82, 0.97, 1.0)
    end
end

function TREKTricorderWindow:render()
    ISPanelJoypad.render(self)
    self:drawPlot()

    local cx = SIDE + PAD
    local y = self.listY
    local result = self.result

    if M.sweeping() then
        self:drawText(getText("IGUI_TREK_SweepWorking"), cx, y,
                      P.gold[1], P.gold[2], P.gold[3], 1, UIFont.Small)
        return
    end

    if not result then
        self:drawText(getText("IGUI_TREK_SweepWorking"), cx, y,
                      P.dim[1] * 1.4, P.dim[2] * 1.4, P.dim[3] * 1.4, 1, UIFont.Small)
        return
    end

    -- **No lifesigns is not the end of the readout.** It used to return here,
    -- which meant a sweep in a quiet room said nothing about dilithium -- and
    -- a quiet room is exactly where somebody is prospecting. The bands are
    -- skipped when there is nothing in them; the mineral line always draws.
    if result.total == 0 then
        self:drawText(getText("IGUI_TREK_SweepNone"), cx, y,
                      P.blue[1], P.blue[2], P.blue[3], 1, UIFont.Small)
        y = y + 20
        self:drawDilithium(cx, y, result)
        self:drawPersonnel(cx, y + 18, result)
        self:drawClue(cx, y + (result.personnel and 36 or 18), result)
        return
    end

    self:drawText(getText("IGUI_TREK_SweepTotal", tostring(result.total),
                          tostring(result.radius)), cx, y,
                  P.text[1], P.text[2], P.text[3], 1, UIFont.Small)
    y = y + 20

    local rows = {
        { "IGUI_TREK_SweepClose", P.red },
        { "IGUI_TREK_SweepMid", P.orange },
        { "IGUI_TREK_SweepFar", P.gold },
    }
    for i, row in ipairs(rows) do
        local col = row[2]
        H.pill(self, cx, y + 3, 22, 9, col, true, true)
        self:drawText(string.upper(getText(row[1])), cx + 30, y,
                      col[1], col[2], col[3], 1, UIFont.Small)
        self:drawTextRight(tostring(result.counts[i]), self.width - PAD, y,
                           P.text[1], P.text[2], P.text[3], 1, UIFont.Small)
        y = y + 18
    end

    -- And the line the tricorder is really carried for once the replicator
    -- is running: where the dilithium is.
    self:drawDilithium(cx, y, result)
    self:drawPersonnel(cx, y + 18, result)
    self:drawClue(cx, y + (result.personnel and 36 or 18), result)

    if self.joyfocus then
        self:drawTextRight(string.upper(getText("IGUI_TREK_MedJoypadHint")),
                           self.width - BOTH - 6, self.height - BOTH + 1,
                           0, 0, 0, 1, UIFont.Small)
    end
end

--- The mineral line. Drawn on every sweep, found or not.
function TREKTricorderWindow:drawDilithium(cx, y, result)
    local found = (result and result.crystalTotal) or 0
    local dc = found > 0 and P.violet or P.dim
    H.pill(self, cx, y + 3, 22, 9, dc, true, true)
    self:drawText(string.upper(getText("IGUI_TREK_SweepDilithium")), cx + 30, y,
                  dc[1] * 1.2, dc[2] * 1.2, dc[3] * 1.2, 1, UIFont.Small)
    self:drawTextRight(tostring(found), self.width - PAD, y,
                       P.text[1], P.text[2], P.text[3], 1, UIFont.Small)
end

--- The ensign's line: only when they are in range, because on every other
--- sweep of the save it would be a row that says nothing.
function TREKTricorderWindow:drawPersonnel(cx, y, result)
    local f = result and result.personnel
    if not f then return end
    H.pill(self, cx, y + 3, 22, 9, P.blue, true, true)
    self:drawText(string.upper(getText("IGUI_TREK_SweepPersonnel")), cx + 30, y,
                  P.blue[1], P.blue[2], P.blue[3], 1, UIFont.Small)
    self:drawTextRight(getText("IGUI_TREK_SweepPersonnelAt", tostring(f.dist),
                               f.compass), self.width - PAD, y,
                       P.text[1], P.text[2], P.text[3], 1, UIFont.Small)
end

--- The fragment's line: only when one is in range, like the ensign's.
function TREKTricorderWindow:drawClue(cx, y, result)
    local g = result and result.clue
    if not g then return end
    local c = { 0.31, 0.84, 0.94 }
    H.pill(self, cx, y + 3, 22, 9, c, true, true)
    self:drawText(string.upper(getText("IGUI_TREK_SweepClue")), cx + 30, y,
                  c[1], c[2], c[3], 1, UIFont.Small)
    self:drawTextRight(getText("IGUI_TREK_SweepPersonnelAt", tostring(g.dist),
                               g.compass), self.width - PAD, y,
                       P.text[1], P.text[2], P.text[3], 1, UIFont.Small)
end

function TREKTricorderWindow:onSweepDone(result)
    self.result = result
end

function TREKTricorderWindow:onSweep()
    if not M.startSweep(self.player) then
        warnNote(self.player, "IGUI_TREK_SweepBusy")
    end
end

function TREKTricorderWindow:onGainJoypadFocus(joypadData)
    ISPanelJoypad.onGainJoypadFocus(self, joypadData)
    if self:getJoypadFocus() then
        self:restoreJoypadFocus(joypadData)
    else
        self:setJoypadFocusTopLeft(joypadData)
    end
end

function TREKTricorderWindow:onLoseJoypadFocus(joypadData)
    ISPanelJoypad.onLoseJoypadFocus(self, joypadData)
    self:clearJoypadFocus(joypadData)
end

function TREKTricorderWindow:close()
    M.window = nil
    -- Never leave a controller pointing at a panel that has gone: it would
    -- do nothing at all until something else took the focus.
    if self.joyfocus then
        U.try("sweep.releaseFocus", function() setJoypadFocus(self.playerNum, nil) end)
    end
    self:setVisible(false)
    self:removeFromUIManager()
end

function M.openSweep(player)
    if M.window then
        U.try("sweep.close", function() M.window:close() end)
    end
    local w = U.try("sweep.open", function()
        local win = TREKTricorderWindow:new(120, 120, player)
        win:initialise()
        win:instantiate()
        win:addToUIManager()
        return win
    end)
    if not w then return nil end
    M.window = w
    U.try("sweep.focus", function()
        if JoypadState.players[w.playerNum + 1] then
            setJoypadFocus(w.playerNum, w)
        end
    end)
    M.startSweep(player)
    return w
end

---------------------------------------------------------------------------
-- The tricorder: the lock override
---------------------------------------------------------------------------
-- A lock is world state, so the server opens it. The client looks first only
-- so it can offer the option and explain a refusal in the menu rather than
-- in silence; the server looks again before it touches anything, because a
-- client is a request and never a fact.

function M.onOverride(_, player, x, y, z)
    Core.send(player, "unlock", { x = x, y = y, z = z })
end

-- Why the server said no, in the player's own words. A refusal that arrives
-- as nothing at all is indistinguishable from a mod that is broken.
local UNLOCK_TEXT = {
    padlock   = "IGUI_TREK_OverridePadlock",
    safehouse = "IGUI_TREK_OverrideSafehouse",
    cooling   = "IGUI_TREK_OverrideCooling",
    far       = "IGUI_TREK_OverrideFar",
    notool    = "IGUI_TREK_OverrideNoTool",
}

TREK.Net.onClient("unlocked", function(args)
    local player = U.player(0)
    if not player then return end
    if args.ok then
        U.try("unlock.sound", function()
            player:playSoundLocal("TREK_TricorderChirp")
        end)
        note(player, "IGUI_TREK_OverrideDone")
        return
    end
    warnNote(player, UNLOCK_TEXT[args.why] or "IGUI_TREK_OverrideFailed")
end)

---------------------------------------------------------------------------
-- Menus
---------------------------------------------------------------------------
--- The items in a context menu selection, flattened.
---
--- An entry is either an InventoryItem or a stack -- a plain table with an
--- `items` list -- and a handler that assumes one shape silently does nothing
--- for the other. Vanilla's own ISRemoveItemTool has the same two cases.
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

local function firstOfType(items, fullId)
    for _, item in ipairs(items) do
        local t = U.try("menu.fullType", function() return item:getFullType() end)
        if t == fullId then return item end
    end
    return nil
end

function M.onUseHypospray(item, player)
    M.useHypospray(player, item)
end

function M.onUseDermalRegen(item, player)
    M.useDermalRegen(player, item)
end

function M.onScanSelf(_, player)
    M.scanSelf(player)
end

function M.onSweepMenu(_, player)
    M.openSweep(player)
end

--- The inventory menu: one option per instrument in the selection.
function M.fillInventoryMenu(playerNum, context, items)
    local player = U.player(playerNum)
    if not player then return end
    local selected = selectedItems(items)
    if #selected == 0 then return end

    local hypo = firstOfType(selected, C.HyposprayItem)
    if hypo then
        local left = Med.doses(hypo)
        local option = context:addOption(
            getText("IGUI_TREK_HypoUse", tostring(left)), hypo,
            M.onUseHypospray, player)
        -- Greyed rather than hidden: a player has to be able to see that the
        -- thing in their bag is empty, or they will assume it is broken.
        if left <= 0 then option.notAvailable = true end
    end

    local regen = firstOfType(selected, C.DermalRegenItem)
    if regen then
        context:addOption(getText("IGUI_TREK_SkinUse"), regen,
                          M.onUseDermalRegen, player)
    end

    if firstOfType(selected, C.MedTricorderItem) then
        context:addOption(getText("IGUI_TREK_MedScanSelf"), items,
                          M.onScanSelf, player)
    end

    if firstOfType(selected, C.TricorderItem) then
        context:addOption(getText("IGUI_TREK_Sweep"), items,
                          M.onSweepMenu, player)
    end
end

Events.OnFillInventoryObjectContextMenu.Add(M.fillInventoryMenu)

--- Another player standing on this square, or nil.
---
--- Deliberately by walking the player list and comparing positions rather
--- than asking the square for its movers. `IsoGridSquare.getMovingObjects()`
--- is public and would be one line -- and every vanilla Lua call site for it
--- is the debug menu, which is the pattern that has preceded two of this
--- project's worst afternoons. U.players() is what the crew menu and the
--- shields already use, in game, on a server.
---
--- "Not me" is decided by username rather than by object identity. Two
--- reasons, and the second is the one that matters: `rawequal` has **no
--- vanilla Lua call site anywhere in build 42**, and Kahlua's standard
--- library is missing things you would expect it to have (`next`,
--- `math.huge`), so leaning on it is a gamble with no upside; and the object
--- `getOnlinePlayers()` hands back for yourself is not guaranteed to be the
--- same table as `getSpecificPlayer()` returned.
local function otherPlayerOn(sq, me)
    local x, y, z = sq:getX(), sq:getY(), sq:getZ()
    local mine = U.try("menu.myName", function() return me:getUsername() end)
    for _, p in ipairs(U.players()) do
        local ok = U.try("menu.playerAt", function()
            if p:getUsername() == mine then return false end
            return math.floor(p:getX()) == x
               and math.floor(p:getY()) == y
               and math.floor(p:getZ()) == z
               and not p:isDead()
        end)
        if ok then return p end
    end
    return nil
end

function M.onScanOther(_, player, other)
    if not M.scanOther(player, other) then
        warnNote(player, "IGUI_TREK_MedScanFailed")
    end
end

--- The world menu: the lock override, and scanning somebody else.
---
--- On OnFillWorldObjectContextMenu rather than the Pre- event the rest of the
--- mod uses, and for the opposite reason: a locked door and another player
--- are both things the base game already considers interactable, so the later
--- event fires on them, and these options belong beside vanilla's own rather
--- than above them.
function M.fillWorldMenu(playerNum, context, worldobjects, test)
    local player = U.player(playerNum)
    if not player then return end

    local sq = nil
    for _, o in ipairs(worldobjects or {}) do
        sq = U.try("menu.square", function() return o:getSquare() end)
        if sq then break end
    end
    if not sq then return end

    local username = U.try("menu.username", function() return player:getUsername() end)

    local lock, lockWhy = nil, nil
    if Med.carries(player, C.TricorderType, C.TricorderItem) then
        lock, lockWhy = Med.lockOn(sq, username)
    end

    -- Scanning somebody else exists only where there is somebody else: a
    -- client connected to a server. Single player never offers it.
    local patient = nil
    if isClient() and Med.carries(player, C.MedTricorderType, C.MedTricorderItem) then
        patient = otherPlayerOn(sq, player)
    end

    local offerLock = lock ~= nil or lockWhy == "padlock"
    if not offerLock and not patient then return end
    if test then return ISWorldObjectContextMenu.setTest() end

    if offerLock then
        local option = context:addOption(getText("IGUI_TREK_Override"), worldobjects,
                                         M.onOverride, player,
                                         sq:getX(), sq:getY(), sq:getZ())
        if not lock then
            -- A padlock is refused, and it says so in the menu. Hiding the
            -- option would leave the player guessing whether the tricorder
            -- can do this at all.
            option.notAvailable = true
            option.toolTip = ISWorldObjectContextMenu.addToolTip()
            option.toolTip.description = getText("IGUI_TREK_OverridePadlock")
        end
    end

    if patient then
        local name = U.try("menu.otherName", function()
            return patient:getDisplayName()
        end) or "?"
        context:addOption(getText("IGUI_TREK_MedScanOther", name), worldobjects,
                          M.onScanOther, player, patient)
    end
end

Events.OnFillWorldObjectContextMenu.Add(M.fillWorldMenu)

---------------------------------------------------------------------------
-- Ticks
---------------------------------------------------------------------------
Events.OnTick.Add(function()
    M.serviceSweep()
end)

-- Only this client's own characters: OnPlayerUpdate also runs for the other
-- players a client can see, and their inventories are not ours to change.
Events.OnPlayerUpdate.Add(function(player)
    if not player or not player:isLocalPlayer() then return end
    refillTick = refillTick + 1
    if refillTick < C.HyposprayRechargeTicks then return end
    refillTick = 0
    M.serviceRefill(player)
end)

return M
