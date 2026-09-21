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

---------------------------------------------------------------------------
-- What the dermal regenerator treats
---------------------------------------------------------------------------
-- Skin, and only skin. The two lists deliberately overlap on deep wounds,
-- bleeding and burns -- the hypospray stays the all-in-one emergency dose --
-- and what makes the regenerator its own instrument is the other half: a
-- laceration, a scratch, and the stitches and dressing that were holding
-- them shut. It has no charges, so what keeps it from replacing the
-- hypospray is what it will *not* do: an infected cut, pain, stiffness and a
-- fracture are all still injected, and an infected wound is still what kills
-- you.
--
-- **Clearing a cut or a scratch is safe**, which is the one thing here worth
-- checking rather than assuming. `setCut(false)` and `setScratched(false, x)`
-- take an early-return branch in the bytecode -- clear the flag, call
-- setBleeding(false), return -- and all the timer, trait and sandbox
-- machinery lives in the *true* branch, where a wound is being inflicted. No
-- infection field is anywhere near either of them, so closing the scratch a
-- zombie gave you does not quietly cure what it gave you with it.
Med.SKIN = {
    -- Cuts and scratches first. Both call setBleeding(false) themselves on
    -- the way out, so a separate bleeding entry after them usually finds
    -- nothing left to do -- which is correct, and is why nothing is counted
    -- that was not actually read back as changed.
    { key = "cut",
      ask = function(p) return p:isCut() or p:getCutTime() > 0 end,
      fix = function(p) p:setCut(false) p:setCutTime(0) end },

    { key = "scratch",
      ask = function(p) return p:scratched() or p:getScratchTime() > 0 end,
      fix = function(p) p:setScratched(false, false) p:setScratchTime(0) end },

    { key = "deepWound",
      ask = function(p) return p:getDeepWoundTime() > 0 or p:deepWounded() end,
      fix = function(p) p:setDeepWounded(false) p:setDeepWoundTime(0) end },

    { key = "bleeding",
      ask = function(p) return p:bleeding() end,
      fix = function(p) p:setBleeding(false) p:setBleedingTime(0) end },

    { key = "burn",
      ask = function(p) return p:getBurnTime() > 0 or p:isNeedBurnWash() end,
      fix = function(p) p:setBurnTime(0) p:setNeedBurnWash(false) end },

    { key = "stitches",
      ask = function(p) return p:stitched() or p:getStitchTime() > 0 end,
      fix = function(p) p:setStitched(false) p:setStitchTime(0) end },

    -- The dressing comes off last, and only once the wound under it has
    -- gone. Two guards on it, both deliberate: a bandage over nothing is
    -- just cloth, and a bandage over a **bite** is the one dressing that
    -- must stay -- the regenerator does not cure a bite, so taking the
    -- bandage off one would be actively worse than doing nothing.
    --
    -- Removed through BodyDamage:SetBandaged(index, ...) rather than
    -- BodyPart:setBandaged(...). Both exist; only the first has a vanilla Lua
    -- call site (ISApplyBandage.lua:141 removes one exactly this way).
    { key = "bandage",
      ask = function(p)
          if p:bitten() then return false end
          if not (p:bandaged() or p:getBandageLife() > 0) then return false end
          return not (p:bleeding() or p:deepWounded() or p:isCut()
                      or p:scratched() or p:getBurnTime() > 0)
      end,
      fix = function(p, bd) bd:SetBandaged(p:getIndex(), false, 0, false, nil) end },

    { key = "health",
      ask = function(p) return p:getHealth() < 100 end,
      fix = function(p) p:SetHealth(100) end },
}

--- True for a part the dermal regenerator will not close.
---
--- Skin does not grow over a shard of glass or a bullet, and a mod that
--- sealed them inside would be quietly making things worse while reporting
--- success. The part is skipped, counted, and named in the note, so the
--- player is told to reach for the tweezers rather than left wondering why
--- one arm did not heal.
function Med.obstructed(part)
    if U.try("med.haveGlass", function() return part:haveGlass() end) == true then
        return true
    end
    return U.try("med.haveBullet", function() return part:haveBullet() end) == true
end

--- The character's BodyDamage, or nil.
function Med.damageOf(character)
    if not character then return nil end
    return U.try("med.bodyDamage", function() return character:getBodyDamage() end)
end

--- Every body part of a character, as a plain Lua list.
function Med.bodyParts(character)
    local out = {}
    local damage = Med.damageOf(character)
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
--- Applies one treatment list to a character. `skip` is an optional
--- predicate: a part it accepts is left entirely alone and counted in
--- `counts.skipped`, which is how the dermal regenerator refuses to close
--- skin over a shard of glass.
function Med.treatWith(character, list, skip)
    local counts = { total = 0, skipped = 0 }
    local damage = Med.damageOf(character)
    local parts = Med.bodyParts(character)
    if #parts == 0 then return counts end

    -- One batch per concern rather than one for the whole pass: a wrong name
    -- in `fix` should cost that concern and not the seven around it, and a
    -- per-part loop that keeps throwing dumps a Java stack trace every time.
    local join = {}
    for _, t in ipairs(list) do
        join[t.key] = U.batch("med.treat." .. t.key)
    end

    for _, part in ipairs(parts) do
        if skip and U.try("med.skip", skip, part) then
            counts.skipped = counts.skipped + 1
        else
            for _, t in ipairs(list) do
                join[t.key](function()
                    if not t.ask(part, damage) then return end
                    t.fix(part, damage)
                    -- refused; do not count it
                    if t.ask(part, damage) then return end
                    counts[t.key] = (counts[t.key] or 0) + 1
                    counts.total = counts.total + 1
                end)
            end
        end
    end
    return counts
end

--- A hypospray dose.
function Med.treat(character)
    return Med.treatWith(character, Med.TREATMENTS)
end

--- A pass of the dermal regenerator.
function Med.regenerate(character)
    return Med.treatWith(character, Med.SKIN, Med.obstructed)
end

--- True when there is anything on this character `list` would put right.
--- Asked before an instrument is used, so a hypospray is never wasted on
--- somebody who is already well and a regenerator never reports success on
--- unbroken skin.
function Med.needsTreatment(character, list, skip)
    list = list or Med.TREATMENTS
    local damage = Med.damageOf(character)
    for _, part in ipairs(Med.bodyParts(character)) do
        if not (skip and U.try("med.skip", skip, part)) then
            for _, t in ipairs(list) do
                if U.try("med.ask." .. t.key, t.ask, part, damage) then return true end
            end
        end
    end
    return false
end

---------------------------------------------------------------------------
-- Foreign bodies
---------------------------------------------------------------------------
--- Takes the glass and the bullets out of every limb. Returns counts.
---
--- The dermal regenerator refuses to close skin over a shard (Med.obstructed)
--- and the hypospray never looks; the EMH takes them out first, which is the
--- whole reason he is better than the instrument in your pocket.
---
--- **`setHaveBullet` is `(boolean, int)`.** One argument throws out of Java,
--- and vanilla passes the count too (ISRemoveBullet.lua:69). `setHaveGlass`
--- really is the one-argument setter it looks like (ISRemoveGlass.lua:73).
--- Neither is gated on Capability.CanMedicalCheat -- that gates added pain,
--- instant completion and the consent bypass, and nothing else.
function Med.removeForeign(character)
    local counts = { total = 0 }
    local join = U.batch("med.foreign")
    for _, part in ipairs(Med.bodyParts(character)) do
        join(function()
            if part:haveGlass() then
                part:setHaveGlass(false)
                if not part:haveGlass() then
                    counts.glass = (counts.glass or 0) + 1
                    counts.total = counts.total + 1
                end
            end
            if part:haveBullet() then
                part:setHaveBullet(false, 0)
                if not part:haveBullet() then
                    counts.bullet = (counts.bullet or 0) + 1
                    counts.total = counts.total + 1
                end
            end
        end)
    end
    return counts
end

---------------------------------------------------------------------------
-- The cure
---------------------------------------------------------------------------
-- **The one thing in this mod that may clear a bite**, and the reason the
-- EMH is worth building at all. Everything above this line is decided *not*
-- to touch it.
--
-- The infection has two levels with nearly the same names, and both have to
-- go in one pass:
--
--   BodyPart.IsInfected()     the virus in a limb
--   BodyDamage.isInfected()   the virus in the person -- a one-way latch,
--                             re-derived from the parts every tick and
--                             skipped once true
--
-- Clear the body flag alone and the next tick puts it straight back from the
-- parts; clear the parts alone and the body flag never drops. Med.cure does
-- the parts and TREK_Server does the body, in the same handler.
--
-- **SetBitten(false) -- one argument -- infects the limb.** Its bytecode
-- writes bittenZ from the argument and then runs on regardless: isInfectedZ
-- = 1 and generateBleeding(). Vanilla's own admin health cheat calls it that
-- way in two places, which is exactly the trap DEV_GUIDE.md's *the jar is
-- not the API* describes one level in -- a vanilla call site proves a method
-- is reachable, never that it is correct. The two-argument form guards the
-- whole block on its first argument and is safe.

-- Everything that means "this limb has the zombie virus in it", as one named
-- list so the hypospray's promise and the EMH's cure cannot drift apart:
-- `medical()` asserts a dose leaves every one of these alone and `emh()`
-- asserts the cure clears every one of them, and both walk this table.
--
-- **These are questions, not fixes**, and that is the one thing about this
-- list worth knowing. `RestoreToFullHealth()` clears all of them by direct
-- putfield in a single call, so a `fix` beside each would be code no test
-- could ever tell from its own absence -- and one of them would be actively
-- dangerous: the obvious `p:SetBitten(false)` clears the bite and then
-- **infects the limb on its way past**, so a belt fastened after the braces
-- would put back exactly what the braces had taken off.
--
-- DEV_GUIDE.md's rule for a branch a mutation cannot break is to delete it or
-- to write the test, and there is no honest test for a fallback that runs
-- only if the engine stops matching its own bytecode. So the fallback is gone
-- and the **read-back** stands in its place: Med.cure asks every one of these
-- again afterwards and warns about anything still set. That is the check that
-- would actually catch the engine changing, and it is the same answer
-- `U.addVerified` reaches by counting a container.
-- **`infectedWound` is deliberately not in here**, and that is the whole
-- reason the list is worth having. An infected *wound* is an ordinary dirty
-- cut, the hypospray cures it, and it is one letter away in the source from
-- the thing that kills you. A list that held both would have asserted the
-- hypospray does not cure an infected cut -- which it does, by design, and
-- which nothing else in the mod would have noticed was now forbidden.
Med.CURE = {
    { key = "partFakeInfected",
      ask = function(p) return p:IsFakeInfected() end },

    { key = "partInfected",
      ask = function(p) return p:IsInfected() end },

    { key = "biteTime",
      ask = function(p) return p:getBiteTime() > 0 end },

    { key = "bitten",
      ask = function(p) return p:bitten() end },
}


--- Cures one character's body, part by part. Returns counts, and `left`:
--- how many infection fields were still set when it read them all back.
---
--- `RestoreToFullHealth()` is the whole fix, and that is a **deliberate
--- inversion** of DEV_GUIDE.md's rule about convenience methods. That rule
--- forbids it to the hypospray *because* it clears the bite; the EMH is the
--- one thing in this mod that may, and the disassembly says the short call is
--- also the safe one here -- thirty-seven fields by direct putfield and no
--- call to `SetBitten` anywhere, so it cannot spring the trap that method is.
---
--- Then a sweep that asks every field on every part again. `left` is what it
--- found, and anything above zero is a WARN: a cure that reported success and
--- left the virus in an arm is the exact shape of the six bugs DEV_GUIDE.md's
--- *pattern worth carrying forward* describes, and the only thing that can
--- see it is reading the result back.
function Med.cure(character)
    local counts = { total = 0, left = 0, parts = 0 }
    local parts = Med.bodyParts(character)
    if #parts == 0 then return counts end

    local heal = U.batch("med.cure.restore")

    for _, part in ipairs(parts) do
        counts.parts = counts.parts + 1
        for _, t in ipairs(Med.CURE) do
            if U.try("med.cure.ask." .. t.key, t.ask, part) then
                counts[t.key] = (counts[t.key] or 0) + 1
                counts.total = counts.total + 1
            end
        end
        heal(function() part:RestoreToFullHealth() end)
    end

    for _, part in ipairs(parts) do
        for _, t in ipairs(Med.CURE) do
            if U.try("med.cure.verify." .. t.key, t.ask, part) then
                counts.left = counts.left + 1
                U.warnOnce("med.cure." .. t.key .. ".left",
                           "the cure left " .. t.key .. " set on a body part")
            end
        end
    end
    return counts
end

--- True when this character is carrying the zombie infection.
---
--- Asked of the **body**, which is the latch, and of the parts, which is what
--- the latch is derived from. Either one alone would answer wrongly for a
--- tick: the body flag is a frame behind a fresh bite and the parts are
--- cleared before the body is.
function Med.isInfected(character)
    local damage = Med.damageOf(character)
    if damage and U.try("med.infected", function()
        return damage:isInfected()
    end) == true then
        return true
    end
    for _, part in ipairs(Med.bodyParts(character)) do
        if U.try("med.partInfected", function() return part:IsInfected() end) == true then
            return true
        end
    end
    return false
end

--- True when anything on this character is bitten.
function Med.isBitten(character)
    for _, part in ipairs(Med.bodyParts(character)) do
        if U.try("med.partBitten", function() return part:bitten() end) == true then
            return true
        end
    end
    return false
end

---------------------------------------------------------------------------
-- Pushing a body to the client that owns it
---------------------------------------------------------------------------
--- Sends every body part to the patient's own client. Authority only.
---
--- `syncBodyPart(part, mask)` is a Lua global with ten vanilla call sites
--- under shared/TimedActions/ -- none of them admin or debug -- and its first
--- instruction is `getstatic GameServer.server; ifeq -> return`. **On a
--- client it is nothing at all**, which is why this is never called from
--- client/ and tests/test_multiplayer.py's static pass forbids it there.
---
--- The mask is 42 bits wide (BodyPartSyncPacket.parse loops i = 0..41) and
--- 0xFFFFFFFFFFF is "everything", which is what vanilla's own
--- ClientCommands.lua:596 passes.
---
--- **It carries BodyPart fields only.** The BodyDamage flags and the
--- infection moodle do not ride it, which is why the EMH's cure also sends
--- the patient a message telling their client to clear its own.
Med.SYNC_ALL = 0xFFFFFFFFFFF

function Med.publish(character)
    if isClient() then
        U.warnOnce("syncOnClient",
                   "a client tried to sync a body part; the engine ignores it")
        return 0
    end
    local sent = 0
    local join = U.batch("med.publish")
    for _, part in ipairs(Med.bodyParts(character)) do
        if join(function()
            syncBodyPart(part, Med.SYNC_ALL)
            return true
        end) then sent = sent + 1 end
    end
    return sent
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
        local ok, safe = pcall(function()
            return SafeHouse.isSafeHouse(sq, username, true)
        end)
        if not ok then
            U.warnOnce("med.safehouse", tostring(safe))
            return nil, "safehouse"
        end
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

    local keySet = U.try("med.setLockedByKey", function()
        if obj.setLockedByKey then obj:setLockedByKey(false) end
        return true
    end)
    local lockSet = U.try("med.setIsLocked", function()
        obj:setIsLocked(false)
        return true
    end)
    if keySet ~= true or lockSet ~= true then return false end

    local stillLocked = U.try("med.isLocked", function()
        return obj:isLocked()
    end)
    local stillKeyed = U.try("med.isLockedByKey", function()
        if obj.isLockedByKey then return obj:isLockedByKey() end
        return false
    end)
    if stillLocked ~= false or stillKeyed ~= false then return false end

    local synced = U.try("med.lockSync", function()
        obj:sync()
        return true
    end)
    return synced == true
end

return Med
