--[[ Shuttlecraft -- the medical set's primitives.

    Three items live on top of this file: the hypospray, the medical tricorder
    and the tricorder (TREK_MedKit.lua for the menus, the panel and the
    sweep; TREK_Server.lua for the lock override). What is *here* is the part
    with no side effects of its own -- finding a carried instrument, treating
    a body, and deciding what counts as a lock -- because each of those is
    needed on more than one side.

    It is a shared file, so it has no isClient/isServer guard and loads
    everywhere. Nothing in it runs by itself.

    Three things were verified against the engine before any of it was
    written, and each would have failed quietly:

    **`ISHealthPanel.cheat` is not the way to make a medical tricorder.** It
    is `false or getDebug()` at the top of ISHealthPanel.lua and is otherwise
    set only by the admin panel, so it works under -debug, works for an admin,
    and does nothing whatever for a Workshop subscriber -- the `setGodMod`
    shape from DEV_GUIDE.md's *The jar is not the API*. The panel's own
    `doctorLevel` field is the real lever: assigned once in :new() and only
    ever read afterwards, so setting it on our instance opens every gate.

    **`BodyPart.RestoreToFullHealth()` cures a bite.** It is the obvious way
    to heal a limb and it is the wrong one here. Its bytecode clears
    `bittenZ` and `biteTimeF` along with everything else, and the hypospray
    is specifically decided *not* to cure a bite (ROADMAP.md, MEDICAL_SET.md
    section 3) -- that is the EMH's, and it is the whole reason the EMH is
    worth building. So this file sets the fields it means to set, one at a
    time, and never uses the convenient one.

    **The two infections are different things with nearly the same name.**
    `BodyPart.setInfectedWound(false)` is an ordinary infected cut and is
    cured here. `BodyDamage.setInfected(false)` is the zombie virus and is
    never touched. Confusing them would hand a pocket item the one cure the
    game is built around, and the names give you no help at all.

    Every treatment **reads its result back**. A setter that silently did
    nothing looks exactly like one that worked, which is the failure shape
    this mod has paid for six times (DEV_GUIDE.md, *the pattern worth
    carrying forward*), so a treatment is only counted when the body actually
    changed.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local Med = {}
TREK.Medical = Med

---------------------------------------------------------------------------
-- Finding an instrument on a player
---------------------------------------------------------------------------
--- Every copy of one instrument anywhere on a player: pockets, bags, hands.
---
--- The phaser's lookup, generalised. `getAllTypeRecurse` walks sub-containers
--- and compares the **bare** type, so it is handed the bare name and the
--- results are filtered on the full id -- the bare name is not namespaced and
--- another mod could plausibly use it. The hands are checked separately
--- because an equipped item is not always in the container listing.
---
--- Deliberately not `getItemsFromFullType(type, true)`: that overload's
--- boolean is undocumented, and guessing at an undocumented flag is how a
--- feature ends up silently finding nothing.
function Med.carried(player, bareType, fullId)
    local out, seen = {}, {}
    if not player then return out end

    local function add(item)
        if not item or seen[item] then return end
        local t = U.try("med.fullType", function() return item:getFullType() end)
        if t ~= fullId then return end
        seen[item] = true
        table.insert(out, item)
    end

    local inv = U.try("med.inventory", function() return player:getInventory() end)
    if inv then
        local list = U.try("med.find", function()
            return inv:getAllTypeRecurse(bareType)
        end)
        if list then
            local join = U.batch("med.list")
            local n = join(function() return list:size() end) or 0
            for i = 0, n - 1 do
                add(join(function() return list:get(i) end))
            end
        end
    end

    add(U.try("med.primary", function() return player:getPrimaryHandItem() end))
    add(U.try("med.secondary", function() return player:getSecondaryHandItem() end))
    return out
end

--- The first one found, or nil. The usual question: is one of these on you.
function Med.carries(player, bareType, fullId)
    return Med.carried(player, bareType, fullId)[1]
end

---------------------------------------------------------------------------
-- Hypospray doses
---------------------------------------------------------------------------
--- How many doses are left in one hypospray.
---
--- Kept in the item's own mod data rather than in its condition or an ammo
--- count. Both of those are engine state with engine opinions about them --
--- condition decays and is repaired, ammo belongs to firearms -- and mod data
--- on an InventoryItem is saved with the item and travels with it between
--- containers, players and worlds.
---
--- A hypospray that has never been used has no entry at all, so an absent
--- value means full rather than empty. Reading it as empty would ship every
--- locker in the ship stocked with dead injectors.
function Med.doses(item)
    if not item then return 0 end
    local md = U.try("hypo.modData", function() return item:getModData() end)
    if not md then return 0 end
    local n = md.TREKDoses
    if type(n) ~= "number" then return C.HyposprayDoses end
    if n < 0 then return 0 end
    if n > C.HyposprayDoses then return C.HyposprayDoses end
    return n
end

function Med.setDoses(item, n)
    if not item then return false end
    local md = U.try("hypo.modData", function() return item:getModData() end)
    if not md then return false end
    if n < 0 then n = 0 end
    if n > C.HyposprayDoses then n = C.HyposprayDoses end
    md.TREKDoses = n
    return true
end

---------------------------------------------------------------------------
-- Treating a body
---------------------------------------------------------------------------
--- Each thing a dose puts right: how to tell it is there, and how to clear
--- it. `ask` returns a truthy value while the condition is present, so the
--- same function is the before reading and the after check.
---
--- Listed as data rather than written out as a block of ifs so the one test
--- that matters can walk it: every entry here is something the hypospray
--- treats, and a bite and the zombie infection are absent from it by design.
--- Adding either to this table is the single change that would break that
--- promise, which is exactly what makes it worth keeping in one place.
Med.TREATMENTS = {
    { key = "bleeding",
      ask = function(p) return p:bleeding() end,
      fix = function(p) p:setBleeding(false) p:setBleedingTime(0) end },

    { key = "deepWound",
      ask = function(p) return p:getDeepWoundTime() > 0 or p:deepWounded() end,
      fix = function(p) p:setDeepWounded(false) p:setDeepWoundTime(0) end },

    -- An ordinary infected cut, NOT the zombie virus. The level is cleared
    -- to -1 rather than 0 because that is what vanilla's own health panel
    -- does; 0 is a wound that is merely not infected yet.
    { key = "infectedWound",
      ask = function(p) return p:isInfectedWound() or p:getWoundInfectionLevel() > 0 end,
      fix = function(p) p:setInfectedWound(false) p:setWoundInfectionLevel(-1) end },

    { key = "burn",
      ask = function(p) return p:getBurnTime() > 0 or p:isNeedBurnWash() end,
      fix = function(p) p:setBurnTime(0) p:setNeedBurnWash(false) end },

    -- The splint goes too: a mended bone does not need one, and leaving it
    -- on keeps the movement penalty that was the whole point of the break.
    { key = "fracture",
      ask = function(p) return p:getFractureTime() > 0 or p:isSplint() end,
      fix = function(p) p:setFractureTime(0) p:setSplint(false, 0) end },

    { key = "pain",
      ask = function(p) return p:getAdditionalPain() > 0 end,
      fix = function(p) p:setAdditionalPain(0) end },

    { key = "stiffness",
      ask = function(p) return p:getStiffness() > 0 end,
      fix = function(p) p:setStiffness(0) end },

    -- Last, so a limb is mended before it is topped up. 100 is the engine's
    -- own full: BodyPart.RestoreToFullHealth writes exactly that constant --
    -- and then goes on to clear the bite, which is why it is not used here.
    { key = "health",
      ask = function(p) return p:getHealth() < 100 end,
      fix = function(p) p:SetHealth(100) end },
}

--- Every body part of a character, as a plain Lua list.
function Med.bodyParts(character)
    local out = {}
    if not character then return out end
    local damage = U.try("med.bodyDamage", function()
        return character:getBodyDamage()
    end)
    if not damage then return out end
    local parts = U.try("med.bodyParts", function() return damage:getBodyParts() end)
    if not parts then return out end
    local join = U.batch("med.partList")
    local n = join(function() return parts:size() end) or 0
    for i = 0, n - 1 do
        local p = join(function() return parts:get(i) end)
        if p then table.insert(out, p) end
    end
    return out
end

--- Treats one character with a dose. Returns a table of counts, keyed the way
--- Med.TREATMENTS is, plus `total`.
---
--- **Nothing is counted that was not read back.** Each treatment asks whether
--- the condition is present, applies the fix, and asks again: only a
--- condition that was there and then was not counts. That costs one extra
--- call per part per concern and it is the difference between a report and a
--- guess -- an engine setter that quietly refuses is indistinguishable from
--- one that worked, and this mod has shipped that bug six times.
---
--- A character's body damage belongs to the client that owns them
--- (MULTIPLAYER.md: a client moves only its own character, and heals only its
--- own too), so this is called from the client for its own player. The EMH
--- will call it server-side for somebody else, which is why it takes a
--- character rather than reaching for one.
function Med.treat(character)
    local counts = { total = 0 }
    local parts = Med.bodyParts(character)
    if #parts == 0 then return counts end

    -- One batch per concern rather than one for the whole pass: a wrong name
    -- in `fix` should cost that concern and not the seven around it, and a
    -- per-part loop that keeps throwing dumps a Java stack trace every time.
    local join = {}
    for _, t in ipairs(Med.TREATMENTS) do
        join[t.key] = U.batch("med.treat." .. t.key)
    end

    for _, part in ipairs(parts) do
        for _, t in ipairs(Med.TREATMENTS) do
            join[t.key](function()
                if not t.ask(part) then return end
                t.fix(part)
                if t.ask(part) then return end       -- refused; do not count it
                counts[t.key] = (counts[t.key] or 0) + 1
                counts.total = counts.total + 1
            end)
        end
    end
    return counts
end

--- True when there is anything on this character a dose would put right.
--- Asked before a dose is spent, so a hypospray is never wasted on somebody
--- who is already well.
function Med.needsTreatment(character)
    for _, part in ipairs(Med.bodyParts(character)) do
        for _, t in ipairs(Med.TREATMENTS) do
            if U.try("med.ask." .. t.key, t.ask, part) then return true end
        end
    end
    return false
end

---------------------------------------------------------------------------
-- Locks
---------------------------------------------------------------------------
-- What the tricorder will and will not open, and the second half is the
-- important one.
--
-- **A padlock is not opened, and neither is anything inside somebody else's
-- safehouse.** Both of those are another player's property. A mod that picks
-- them is a griefing tool on every server that installs it, and a server
-- owner has no setting to turn that off because they would first have to
-- know it was there. Key locks on the map's own doors are the feature; other
-- people's front doors are not.
--
-- The lookup lives in shared/ because both sides need it and they must agree:
-- the client asks it to decide whether to offer the option, and the server
-- asks it again before doing anything, because a client is a request and
-- never a fact.

--- The locked object on a square, or nil and a reason.
---
--- `username` is whose safehouse rights to judge by; pass nil to skip that
--- check (single player has no safehouses to speak of, and the server passes
--- the asking player's name).
function Med.lockOn(sq, username)
    if not sq then return nil, "nosquare" end

    if username then
        local safe = U.try("med.safehouse", function()
            return SafeHouse.isSafeHouse(sq, username, true)
        end)
        if safe then return nil, "safehouse" end
    end

    local found, why = nil, "nolock"
    U.eachObject(sq, function(o)
        local door = instanceof(o, "IsoDoor")
        local thump = instanceof(o, "IsoThumpable")
        local window = instanceof(o, "IsoWindow")
        if not (door or thump or window) then return end

        local locked = U.try("med.isLocked", function() return o:isLocked() end) == true
        if not locked and (door or thump) then
            locked = U.try("med.isLockedByKey", function()
                return o:isLockedByKey()
            end) == true
        end
        if not locked then return end

        -- A padlock is somebody's own lock, fitted by hand. Refused, and the
        -- reason is carried back so the menu can say so rather than simply
        -- not appearing -- an option that silently is not there teaches a
        -- player that the mod is broken.
        if thump then
            local padlocked = U.try("med.isLockedByPadlock", function()
                return o:isLockedByPadlock()
            end) == true
            if padlocked then
                why = "padlock"
                return
            end
        end

        found = o
        return false
    end)

    if found then return found, nil end
    return nil, why
end

--- Opens a lock the engine is prepared to open, and tells every client.
---
--- **The sync is not automatic and it is not symmetric.** `setLockedByKey(b)`
--- calls `setLockedByKey(b, true)`, which fires `IsoDoor.sync()` itself --
--- but only when `!GameServer.server`. Run on a server, the branch is skipped
--- and no packet is sent at all, so a door unlocked by the authority would
--- stay shut on every client's screen. `obj:sync()` is the explicit call that
--- covers both: on a server it broadcasts to every connection, in single
--- player it is a no-op with nobody to tell.
---
--- Returns true when the object reports itself unlocked afterwards -- read
--- back, as everything else here is.
function Med.unlock(obj)
    if not obj then return false end

    U.try("med.setLockedByKey", function()
        if obj.setLockedByKey then obj:setLockedByKey(false) end
    end)
    U.try("med.setIsLocked", function() obj:setIsLocked(false) end)
    U.try("med.lockSync", function() obj:sync() end)

    local still = U.try("med.isLocked", function() return obj:isLocked() end)
    return still ~= true
end

return Med
