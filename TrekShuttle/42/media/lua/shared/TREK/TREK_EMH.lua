--[[ Shuttlecraft -- the Emergency Medical Hologram: what both sides agree on.

    Where he stands, who is close enough to talk to him, who may be a patient,
    what the sandbox says, and what a treatment costs. Nothing here has a side
    effect and nothing here runs by itself; it is a shared file, so it loads in
    every process and carries no isClient/isServer guard.

    **That is the point of it.** The panel greys a button for exactly the
    reason the server refuses the command, because both of them call
    `E.refusal()` and there is only one copy of the rules. A panel with its own
    idea of who may be treated is a panel that eventually disagrees with the
    ship, and the player is the one who finds out.

    What is *not* here: anything that changes a body, spends a crystal or
    stands a model on the deck. Treatment runs on the server and nowhere else
    -- not because that is tidy, but because it is the only machine that knows
    the patient is hurt. `BodyDamage.Update()` decides who simulates a body at
    bci 21-62:

        21  getstatic GameClient.client ; 24 ifeq -> 63   not a client: simulate
        51  IsoPlayer.isLocalPlayer()   ; 55 ifne -> 62   a client, own body
        58  BodyDamage.RestoreToFullHealth()              a client, REMOTE body

    So in multiplayer a remote player's body on a client is restored to full
    every single tick. It is not stale, it is not there at all -- which is why
    the panel cannot read the crewman on the biobed by itself and has to ask
    (`emhLook`), and why the hypospray's client-side treatment is right only
    for your own body.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Ship"
require "TREK/TREK_Power"
require "TREK/TREK_Medical"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Med = TREK.Medical

local E = {}
TREK.EMH = E

---------------------------------------------------------------------------
-- Where he is
---------------------------------------------------------------------------
--- The cabin offsets he stands on.
function E.spot()
    return C.EmhSpot.x, C.EmhSpot.y
end

--- The cabin offsets of his wall station.
function E.station()
    return C.EmhStation.x, C.EmhStation.y
end

--- True when a clicked square is one the Doctor's menu answers on.
---
--- A named set rather than a box around the station. A right-click resolves
--- to the floor square under the cursor and he is a tall model, so one square
--- is never enough -- and a box is too much, because it reaches squares the
--- warp core owns. C.EmhMenuSpots is the list and tests/test_layout.py keeps
--- it from overlapping anything else's own square.
function E.isStation(x, y, z)
    if not x or not y then return false end
    if TREK.Adirondack and TREK.Adirondack.clickedMachine("emh_station", x, y, z, 1) then
        return true
    end
    if math.floor(z or 0) ~= C.CabinZ then return false end
    for _, spot in ipairs(C.EmhMenuSpots) do
        local sx, sy = U.at(spot[1], spot[2])
        if math.floor(x) == sx and math.floor(y) == sy then return true end
    end
    return false
end

---------------------------------------------------------------------------
-- Who is close enough
---------------------------------------------------------------------------
--- True when this position is within reach of the station.
---
--- Shared so the menu greys itself and the server refuses for the same reason
--- and by the same arithmetic. The server measures it against its **own** copy
--- of where the player is standing; a client is a request, never a fact.
function E.inReach(x, y, z)
    if not x or not y then return false end
    if TREK.Adirondack and TREK.Adirondack.nearMachine("emh_station", x, y, z, C.EmhRange + 1) then
        return true
    end
    if not U.isAboard(x, y, z) then return false end
    local sx, sy = U.at(E.station())
    return U.dist2(x, y, sx + 0.5, sy + 0.5) <= C.EmhRange * C.EmhRange
end

function E.inReachOf(player)
    if not player then return false end
    local x = U.try("emh.px", function() return player:getX() end)
    local y = U.try("emh.py", function() return player:getY() end)
    local z = U.try("emh.pz", function() return player:getZ() end)
    if not x or not y then return false end
    return E.inReach(x, y, z)
end

---------------------------------------------------------------------------
-- The sandbox
---------------------------------------------------------------------------
--- 1 = the Doctor as designed, 2 = off.
---
--- An absent table reads as *Full*, which is the feature as designed -- the
--- rule C.ReplicatorPatterns and C.TorpedoFire both follow. Reading a missing
--- option as "off" is how a headline feature turns itself off in the one
--- setup nobody tested.
function E.mode()
    local v = U.try("sandboxEMH", function()
        return SandboxVars.TrekShuttle and SandboxVars.TrekShuttle.EMH
    end)
    return tonumber(v) or C.EmhFull
end

function E.isOff() return E.mode() == C.EmhOff end

---------------------------------------------------------------------------
-- What he is doing
---------------------------------------------------------------------------
--- True when the hologram is standing on the deck.
---
--- Ship state, so every client sees the same figure. Cleared on a world
--- reload (TREK_Server's OnInitGlobalModData), because a hologram does not
--- survive one and clearing it deletes the whole class of stale-flag bug.
function E.isUp(player)
    -- Aboard the Adirondack her station is always projecting him: there is
    -- nothing to summon, and nothing to stand up in the shuttle's cabin.
    if player and TREK.Adirondack and TREK.Adirondack.onShip(player) then return true end
    return TREK.Ship.get().emh == true
end

--- The cure register: username -> the world age in hours when it completes.
---
--- A table inside a state that is transmitted whole on every change, which
--- DEV_GUIDE.md warns about by name. It is allowed here because it is bounded
--- by the number of people **simultaneously under treatment**, each entry is
--- one number, and an entry is removed the moment it completes or is
--- abandoned. It is not a log and it must never become one.
function E.cures()
    local s = TREK.Ship.get()
    s.emhCures = s.emhCures or {}
    return s.emhCures
end

--- Whether a patient is aboard, for the cure: **in the cabin, or in one of
--- the shuttle's seats.** The cockpit is the ship. The first version asked
--- only about the cabin, and a patient who went forward to fly her during
--- the twelve hours lost the cure and the crystal the moment they sat down
--- -- found in a game, from the log: "beaming forward to the cockpit", then
--- two seconds later "left the ship and the cure is lost".
function E.aboardForCure(player)
    if not player then return false end
    if U.isInteriorPlayer(player) then return true end
    if TREK.Adirondack and TREK.Adirondack.onShip(player) then return true end
    local vehicle = U.try("emh.vehicle", function() return player:getVehicle() end)
    return vehicle ~= nil and TREK.Vehicle ~= nil and TREK.Vehicle.isShuttle(vehicle) == true
end

--- When this player's cure is due, in world-age hours, or nil.
function E.cureDue(username)
    if not username then return nil end
    local due = E.cures()[username]
    if type(due) ~= "number" then return nil end
    return due
end

--- The world clock, in hours since the world began.
---
--- `getGameTime():getWorldAgeHours()` is public on zombie.GameTime with
--- ordinary call sites (ISButtonPrompt.lua:520, WinterIsComing.lua:8), and it
--- is saved with the world -- which is what lets a cure survive a relog.
function E.worldHours()
    local n = U.try("emh.worldAge", function()
        return getGameTime():getWorldAgeHours()
    end)
    if type(n) ~= "number" then return 0 end
    return n
end

---------------------------------------------------------------------------
-- Who may be a patient
---------------------------------------------------------------------------
--- Everyone aboard, as { player = p, name = username, self = true|nil }.
---
--- `asking` is put first, because you are your own default patient and a
--- panel that opened on somebody else would be a surprise.
function E.patients(asking)
    local out = {}
    local mine = asking and TREK.Ship.usernameOf(asking) or nil
    -- Everyone aboard the ship the asker is in: the shuttle's cabin, or the
    -- Adirondack.
    local adk = asking ~= nil and TREK.Adirondack ~= nil and TREK.Adirondack.onShip(asking)
    for _, p in ipairs(U.players()) do
        local alive = U.try("emh.alive", function() return p:isDead() end) == false
        local here = (adk and TREK.Adirondack.onShip(p)) or (not adk and U.isInteriorPlayer(p))
        if alive and here then
            local name = TREK.Ship.usernameOf(p)
            local row = { player = p, name = name, own = (name == mine) or nil }
            if row.own then table.insert(out, 1, row) else table.insert(out, row) end
        end
    end
    -- In single player U.players() is the local list and the player is in it;
    -- on a client it is the online list, which is every player the client has
    -- been told about. Either way the server resolves the patient from its own
    -- copy before it touches anybody -- this is what the panel draws, not what
    -- the ship believes.
    return out
end

--- The player of this name who is really aboard and alive, or nil.
---
--- **Used by the server and by nothing else that matters.** The patient is
--- never taken from what a client sent: the name is looked up here, against
--- this process's own view of where people are standing.
function E.patientNamed(name)
    if type(name) ~= "string" or name == "" or #name > 64 then return nil end
    for _, row in ipairs(E.patients(nil)) do
        if row.name == name then return row.player end
    end
    return nil
end

---------------------------------------------------------------------------
-- What he will and will not do
---------------------------------------------------------------------------
--- Why the Doctor would refuse this player, or nil when he would not.
---
--- One function, called by the panel to grey a control with a reason and by
--- the server to deny a command. That is the whole reason this file exists:
--- two copies of these rules would eventually disagree, and the player would
--- be the one to find out.
---
--- The order is the order the server checks in, so the reason a panel shows
--- is the reason the ship would actually give.
function E.refusal(player)
    if not player then return "access" end
    if U.try("emh.dead", function() return player:isDead() end) ~= false then
        return "access"
    end
    if not TREK.Ship.canUse(player) then return "access" end
    if E.isOff() then return "emhOff" end
    if not E.inReachOf(player) then return "emhFar" end
    -- A dark ship cannot project him at all (ENERGY.md 6). Published as a
    -- flag, so a client's panel greys with the ship's own answer.
    if TREK.Power.dark(TREK.Power.poolOf(player)) then
        return "emhNoPower"
    end
    return nil
end

--- What a treatment costs from the reserve.
function E.treatCost()
    return C.EmhTreatCost
end

--- Why a **treatment** would be refused for this patient, or nil.
---
--- Separate from E.refusal because the two questions have different answers:
--- one is about the person asking and one is about the person being treated.
function E.treatRefusal(patient)
    if not patient then return "emhNoPatient" end
    if Med.needsTreatment(patient, Med.TREATMENTS) then return nil end
    -- The regenerator's list **unskipped**: he takes the glass out first, so
    -- a wound full of it is a wound he can treat even though the instrument
    -- in your pocket refuses it.
    if Med.needsTreatment(patient, Med.SKIN) then return nil end
    for _, part in ipairs(Med.bodyParts(patient)) do
        if U.try("emh.glass", function() return part:haveGlass() end) == true then
            return nil
        end
        if U.try("emh.bullet", function() return part:haveBullet() end) == true then
            return nil
        end
    end
    return "emhWell"
end

--- What is wrong with a patient, itemised.
---
--- `{ infected, bitten, total, items = { [key] = count } }`, where the keys
--- are Med.TREATMENTS' and Med.SKIN's own. **Built from the same lists the
--- treatment walks**, so the readout cannot drift from what the button does
--- -- a panel that itemises from its own list is a panel that one day says
--- "a fracture" about something the Doctor no longer mends.
---
--- Called by the panel for **your own** body, and by the server for anybody
--- else's, and the answer is sent back: in multiplayer a remote player's
--- BodyDamage does not exist on a client to be read (see the header), so the
--- panel has no way to work it out for the crewman on the biobed.
function E.findings(patient)
    local out = { items = {}, total = 0, infected = false, bitten = false }
    if not patient then return out end

    local damage = Med.damageOf(patient)
    local seen = {}
    local function walk(list)
        for _, part in ipairs(Med.bodyParts(patient)) do
            for _, t in ipairs(list) do
                if U.try("emh.find." .. t.key, t.ask, part, damage) then
                    out.items[t.key] = (out.items[t.key] or 0) + 1
                    out.total = out.total + 1
                    seen[t.key] = true
                end
            end
        end
    end
    walk(Med.TREATMENTS)
    walk(Med.SKIN)

    for _, part in ipairs(Med.bodyParts(patient)) do
        if U.try("emh.findGlass", function() return part:haveGlass() end) == true then
            out.items.glass = (out.items.glass or 0) + 1
            out.total = out.total + 1
        end
        if U.try("emh.findBullet", function() return part:haveBullet() end) == true then
            out.items.bullet = (out.items.bullet or 0) + 1
            out.total = out.total + 1
        end
    end

    -- **The one thing the medical tricorder deliberately will not say.** It
    -- is the Doctor's to know, and it is the reason a player opens this
    -- panel at all.
    out.infected = Med.isInfected(patient)
    out.bitten = Med.isBitten(patient)
    return out
end

--- Why a **cure** would be refused for this patient, or nil.
function E.cureRefusal(patient, username)
    if not patient then return "emhNoPatient" end
    if not Med.isInfected(patient) and not Med.isBitten(patient) then
        return "emhNotInfected"
    end
    if username and E.cureDue(username) then return "emhCuring" end
    if TREK.Power.crystals() < C.EmhCureCrystals then return "emhNoCrystal" end
    return nil
end

return E
