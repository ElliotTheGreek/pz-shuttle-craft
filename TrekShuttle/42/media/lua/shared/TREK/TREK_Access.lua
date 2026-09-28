--[[ Shuttlecraft -- boarding clearance: what both sides agree on (ACCESS.md).

    Whether a player may beam to the U.S.S. Adirondack, and why not. Three
    keys: **Trust** (the ship has brought enough of her crew home), **Lock**
    (the ship has held three pattern enhancers while she resolved a lock) and
    **Clean** (this character has passed the Doctor's biofilter screening).

    Shared, and with no side effects, for the reason TREK_EMH is: the menu
    greys the beam for exactly the reason the server refuses it, because both
    ask `Ac.refusal`. Two copies of these rules would one day disagree, and the
    player would be the one to find out.

    **The store** (C.AccessKey) is the ship's: what the story has told, the
    lock, the enhancers recovered, the field station's enhancer, a lock being
    held. Written on the authority (TREK_AccessServer), published when it
    changes, and read here by anybody.

    **Screening is the character's**, in the server's copy of their mod data
    under C.ScreenKey; the owning client keeps the server's answer under
    C.ScreenMirrorKey (the contraband's arrangement: a client's copy of the
    player never sees the server's write). It dies with the character.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local Ac = {}
TREK.Access = Ac

Ac.listeners = {}

---------------------------------------------------------------------------
-- The store
---------------------------------------------------------------------------
--- The ship's record. On the authority the fields are filled in; on a client
--- it is whatever the server last sent.
---   checked        the grandfather check has run (once per world)
---   grandfathered  the world was visiting her before this existed: open
---   told { lock, screen }   what the story has revealed, for the PADD
---   lock           the ship holds a lock on her crew for good
---   recovered      enhancers the ship has seen picked up, from any source
---   station { placed, x, y, z, taken }   the field station's enhancer
---   job { x, y, z, sq, progress, by, paused, beaconAt }   a lock being held
function Ac.store()
    local d = ModData.getOrCreate(C.AccessKey)
    d.told = type(d.told) == "table" and d.told or {}
    if not isClient() then
        d.recovered = tonumber(d.recovered) or 0
        d.station = type(d.station) == "table" and d.station or {}
    end
    return d
end

function Ac.onChange(fn)
    table.insert(Ac.listeners, fn)
end

function Ac.notify()
    for _, fn in ipairs(Ac.listeners) do U.try("accessListener", fn) end
end

--- Publishes the record. Authority only.
function Ac.publish()
    if isClient() then
        U.warnOnce("accessOnClient", "a client tried to publish the clearance record; ignored")
        return
    end
    if isServer() then
        U.try("transmitAccess", function() ModData.transmit(C.AccessKey) end)
    end
    Ac.notify()
end

Events.OnInitGlobalModData.Add(function()
    if not isClient() then return end
    U.try("requestAccess", function() ModData.request(C.AccessKey) end)
end)

Events.OnReceiveGlobalModData.Add(function(key, data)
    if key ~= C.AccessKey then return end
    if not isClient() or type(data) ~= "table" then return end
    ModData.add(key, data)
    Ac.notify()
end)

---------------------------------------------------------------------------
-- The sandbox
---------------------------------------------------------------------------
function Ac.mode() return C.accessMode() end

--- True when nothing is asked of anybody: the sandbox says so, or the world
--- was already visiting her when this was built (ACCESS.md 4).
function Ac.open()
    return Ac.mode() == C.AccessOpen or Ac.store().grandfathered == true
end

--- True when only the rescues are asked for.
function Ac.rescuesOnly()
    return not Ac.open() and Ac.mode() == C.AccessRescuesOnly
end

--- True when all three keys are asked for.
function Ac.earned()
    return not Ac.open() and Ac.mode() == C.AccessEarned
end

--- Whether a screening needs a nanoprobe sample: not when the sandbox has
--- put no Borg among the dead, because then there is nowhere to get one.
function Ac.sampleNeeded()
    local B = TREK.Borg
    return not B or (B.scale() or 0) > 0
end

---------------------------------------------------------------------------
-- The keys
---------------------------------------------------------------------------
--- Crew the ship has brought home: the channel's own count, which every
--- client holds.
function Ac.rescued()
    local Cm = TREK.Comms
    return Cm and tonumber(Cm.store().rescued) or 0
end

function Ac.rescuesNeeded() return C.accessRescues() end

function Ac.trustMet()
    return Ac.open() or Ac.rescued() >= Ac.rescuesNeeded()
end

function Ac.lockMet()
    return Ac.open() or Ac.rescuesOnly() or Ac.store().lock == true
end

--- This machine's view of whether a character has been screened.
function Ac.screened(player)
    if not Ac.earned() then return true end
    local md = player and U.try("access.md", function() return player:getModData() end)
    if not md then return false end
    return md[isClient() and C.ScreenMirrorKey or C.ScreenKey] == true
end

--- Why this player may not beam to the Adirondack, or nil. The order is the
--- order the story asks: the crew first, then the lock, then the Doctor.
function Ac.refusal(player)
    if Ac.open() then return nil end
    if not Ac.trustMet() then return "accTrust" end
    if Ac.rescuesOnly() then return nil end
    if not Ac.lockMet() then return "accLock" end
    if not Ac.screened(player) then return "accScreen" end
    return nil
end

--- Enhancers recovered, as the PADD counts them: never more than a set.
function Ac.recoveredCount()
    return math.min(C.EnhancersNeeded, tonumber(Ac.store().recovered) or 0)
end

---------------------------------------------------------------------------
-- What a player carries
---------------------------------------------------------------------------
--- How many of `fullType` a character carries, bags and all. The bare type
--- is what getAllTypeRecurse compares, so the full id is checked after it
--- (DEV_GUIDE: another mod's item of the same bare name is not ours).
function Ac.carried(player, fullType)
    if not player then return 0 end
    local n = 0
    U.try("access.carried", function()
        local list = player:getInventory():getAllTypeRecurse(fullType:match("%.(.+)$"))
        for i = 0, list:size() - 1 do
            if list:get(i):getFullType() == fullType then n = n + 1 end
        end
    end)
    return n
end

--- True when the player is standing out in the world: not in the shuttle's
--- cabin, not aboard the Adirondack or the field station, not in a seat.
function Ac.outside(player)
    if not player then return false end
    if U.isInteriorPlayer(player) then return false end
    local A = TREK.Adirondack
    if A and A.siteOfPlayer(player) then return false end
    local v = U.try("access.vehicle", function() return player:getVehicle() end)
    return v == nil
end

--- Why this player cannot deploy the enhancers here, or nil.
function Ac.deployRefusal(player)
    if not Ac.earned() or Ac.store().lock == true then return "accLockDone" end
    if Ac.store().job then return "accLockRunning" end
    if not Ac.trustMet() then return "accTrust" end
    if Ac.carried(player, C.EnhancerItem) < C.EnhancersNeeded then return "accNeedThree" end
    if not Ac.outside(player) then return "accDeployOutside" end
    return nil
end

--- Why the Doctor would not screen this patient, or nil. Yourself only.
function Ac.screenRefusal(player)
    if not Ac.earned() then return "accScreenNone" end
    if Ac.screened(player) then return "accScreenDone" end
    if not Ac.store().told.screen then return "accScreenUnasked" end
    local Med = TREK.Medical
    if Med and (Med.isInfected(player) or Med.isBitten(player)) then return "accScreenInfected" end
    if Ac.sampleNeeded() and Ac.carried(player, C.NanoprobeItem) < 1 then return "accNoSample" end
    return nil
end

---------------------------------------------------------------------------
-- The PADD's checklist (ACCESS.md 5)
---------------------------------------------------------------------------
--- The rows of the clearance tab: { done = bool|nil, key, a1, a2 }. `done`
--- nil is a step the story has not revealed; its words say only that.
function Ac.rows(player)
    local out = {}
    local d = Ac.store()
    if Ac.open() then
        table.insert(out, { done = true, key = "IGUI_TREK_AccRowOpen" })
        return out
    end
    local have, need = Ac.rescued(), Ac.rescuesNeeded()
    table.insert(out, { done = have >= need, key = "IGUI_TREK_AccRowCrew",
                        a1 = tostring(math.min(have, need)), a2 = tostring(need) })
    if Ac.earned() then
        if d.told.lock or d.lock then
            table.insert(out, { done = d.lock == true or Ac.recoveredCount() >= C.EnhancersNeeded,
                                key = "IGUI_TREK_AccRowParts",
                                a1 = tostring(d.lock and C.EnhancersNeeded or Ac.recoveredCount()),
                                a2 = tostring(C.EnhancersNeeded) })
            if d.job and not d.lock then
                table.insert(out, { done = false, key = "IGUI_TREK_AccRowHolding",
                                    a1 = tostring(math.floor(tonumber(d.job.progress) or 0)),
                                    a2 = tostring(C.LockMinutes) })
            else
                table.insert(out, { done = d.lock == true, key = "IGUI_TREK_AccRowLock" })
            end
        else
            table.insert(out, { key = "IGUI_TREK_AccRowUnknown" })
        end
        if d.told.screen then
            table.insert(out, { done = Ac.screened(player), key = "IGUI_TREK_AccRowScreen" })
        else
            table.insert(out, { key = "IGUI_TREK_AccRowUnknown" })
        end
    end
    table.insert(out, { done = Ac.refusal(player) == nil, key = "IGUI_TREK_AccRowCleared" })
    return out
end

return Ac
