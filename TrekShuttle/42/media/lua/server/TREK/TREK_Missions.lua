--[[ Shuttlecraft -- distress calls and the downed ensign (ENSIGN.md).

    The authority for the mod's first mission. Runs where the world is
    authoritative -- single player, or the server -- and never on a client.

    What lives here:
      * the distress call: when the ship can hear one, who is calling and
        from where, and the call lapsing when nobody answers;
      * the answer: accepting turns the call into a `downedPersonnel` contact
        with the clock on it, declining schedules the next one;
      * the figure: put on the ground when a player loads it, and taken away
        again when the mission ends -- now if the ground is loaded, later if
        it is not;
      * the beacon: the engine's own zombie-attraction noise at the ensign's square;
      * the rescue: validated, one removal, one status change, one reward.

    Every one of those runs on the game-minute tick **outside** any
    cabin-loaded or player-nearby branch, like probes and cures. A distress
    call and a countdown are logical jobs with no world object behind them,
    and a clock that only ran when somebody was near the ensign would not be a clock
    (DEV_GUIDE: *A guard gated on loaded ground never sees the case it exists
    for*).
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_Probes"
require "TREK/TREK_Power"
require "TREK/TREK_Replicator"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Ship = TREK.Ship
local Probes = TREK.Probes

local M = {}
TREK.Missions = M

---------------------------------------------------------------------------
-- Small helpers
---------------------------------------------------------------------------
local function deny(player, why, extra)
    local args = extra or {}
    args.why = why
    Net.toClient(player, "denied", args)
end

--- Alive and allowed to use the ship. The same gate every ship command has.
local function mayUse(player)
    if not player then return false end
    if U.try("missionDead", function() return player:isDead() end) ~= false then
        return false
    end
    if not Ship.canUse(player) then
        deny(player, "access")
        return false
    end
    return true
end

local function roll(n)
    if n <= 1 then return 0 end
    return U.try("missionRoll", function() return ZombRand(n) end) or 0
end

local function pick(list)
    return list[roll(#list) + 1]
end

--- The figure's world object on its square, or nil; and whether the square
--- could be looked at at all. `false, "unloaded"` is "cannot tell", never
--- "the ensign is gone" -- the crystal's rule, and the ghost hull's before it.
local function figureOn(contact)
    if not contact.ex then return nil, "unplaced" end
    if not U.chunkLoaded(contact.ex, contact.ey, contact.ez) then
        return nil, "unloaded"
    end
    local sq = U.square(contact.ex, contact.ey, contact.ez, false)
    if not sq then return nil, "unloaded" end
    local found = nil
    U.try("ensign.find", function()
        local items = sq:getWorldObjects()
        if not items then return end
        for i = 0, items:size() - 1 do
            local w = items:get(i)
            local it = w and w:getItem()
            if it and it:getFullType() == contact.item then
                found = w
                return
            end
        end
    end)
    return found, sq
end

--- Takes every copy of `item` off a square. Returns how many went.
local function removeFigures(sq, item)
    local doomed = {}
    U.try("ensign.scan", function()
        local items = sq:getWorldObjects()
        if not items then return end
        for i = 0, items:size() - 1 do
            local w = items:get(i)
            local it = w and w:getItem()
            if it and it:getFullType() == item then table.insert(doomed, w) end
        end
    end)
    local gone = 0
    for _, w in ipairs(doomed) do
        -- transmitRemoveItemFromSquare, never removeWorldObject: the second
        -- acts only on the machine that calls it, and on a server that is
        -- the one machine nobody is looking at.
        if U.try("ensign.remove", function()
            sq:transmitRemoveItemFromSquare(w)
            return true
        end) == true then gone = gone + 1 end
    end
    return gone
end

---------------------------------------------------------------------------
-- Hearing a call
---------------------------------------------------------------------------
--- Whether the ship can hear a distress call at all.
---
--- **This is the one line cold start (ROADMAP2 1.6) changes.** Today it is a
--- ship that has been boarded -- the cabin exists -- with dilithium in the
--- core; when commissioning exists it becomes "commissioned", and nothing
--- else in this file has to move.
function M.hearing()
    local s = U.state()
    if not s.built then return false end
    return TREK.Power.reserve() > 0 or TREK.Power.crystals() > 0
end

--- Where the crew are, for a call to be measured from. The first player with
--- an answer; nil when nobody has one.
local function crewOrigin()
    for _, p in ipairs(U.players()) do
        local x, y = Ship.worldOrigin(p)
        if x and y then return x, y end
    end
    return nil
end

--- Picks the ensign's square: a random bearing and distance from the crew, inside the
--- playable world. Nil when nothing in C.EnsignBearingTries worked -- near a
--- map edge, say -- and the caller tries again later rather than reporting a
--- square nobody can reach (PROBES.md: the contact off the top of the map).
local function chooseTarget(ox, oy)
    local span = C.EnsignMaxDistance - C.EnsignMinDistance
    for _ = 1, C.EnsignBearingTries do
        local bearing = roll(3600) / 3600 * 2 * math.pi
        local distance = C.EnsignMinDistance + roll(span + 1)
        local x = math.floor(ox + math.cos(bearing) * distance)
        local y = math.floor(oy + math.sin(bearing) * distance)
        if U.inWorld(x, y) then return x, y, distance end
    end
    return nil
end

--- Makes a call. Returns it, or nil when there was nowhere to point it.
function M.offer(now)
    local data = Probes.store()
    local ox, oy = crewOrigin()
    local tx, ty, distance
    if ox then tx, ty, distance = chooseTarget(ox, oy) end
    if not tx then
        data.nextDistressAt = now + C.DistressRetryHours
        U.log("distress: no valid square to call from (crew at %s,%s); "
              .. "trying again in %d hour(s)", tostring(ox), tostring(oy),
              C.DistressRetryHours)
        return nil
    end

    local body = pick(C.EnsignBodies)
    local call = {
        id = Probes.newId("distress"),
        body = body,
        division = pick(C.EnsignDivisions),
        name = pick(C.EnsignGivenNames[body]) .. " " .. pick(C.EnsignSurnames),
        tx = tx, ty = ty, tz = 0,
        distance = math.floor(distance),
        compass = U.compass(ox, oy, tx, ty),
        offeredAt = now,
        lapseAt = now + C.DistressOfferHours,
    }
    data.distress = call
    Probes.publish()
    U.log("distress: %s (%s) is down at %d,%d, %d squares %s of the crew",
          call.name, call.division, tx, ty, call.distance, call.compass)
    Net.toAll("distressCall", { name = call.name, division = call.division,
                                distance = call.distance,
                                compass = call.compass })
    return call
end

--- The call's own clock: made when due, lapsed when ignored.
function M.serviceDistress()
    local data = Probes.store()
    local now = U.worldHours()

    if data.distress then
        if now >= (data.distress.lapseAt or 0) then
            local name = data.distress.name
            data.distress = nil
            data.nextDistressAt = now + C.DistressIntervalHours
            Probes.publish()
            U.log("distress: nobody answered %s; the call has faded", tostring(name))
            Net.toAll("distressLapsed", { name = name })
        end
        return
    end
    if Probes.mission() then return end
    if not M.hearing() then return end

    -- The first time the ship can hear, the first call is scheduled rather
    -- than made: a crew who have just beamed aboard for the first time are
    -- not yet in a position to go anywhere.
    if not data.nextDistressAt then
        data.nextDistressAt = now + C.DistressFirstHours
        U.log("distress: the ship is listening; the first call is due at "
              .. "hour %.1f", data.nextDistressAt)
        return
    end
    if now < data.nextDistressAt then return end
    M.offer(now)
end

---------------------------------------------------------------------------
-- Answering
---------------------------------------------------------------------------
--- The long-range fix: the ensign's square scattered, and kept in the world.
local function fixFor(call)
    local spread = C.EnsignReportSpread
    local x = call.tx + roll(spread * 2 + 1) - spread
    local y = call.ty + roll(spread * 2 + 1) - spread
    if not U.inWorld(x, y) then return call.tx, call.ty end
    return x, y
end

Net.onServer("distressAnswer", function(player, args)
    if not mayUse(player) then return end
    -- The console is aboard-only, and so is the answer, by the server's own
    -- copy of where the player is -- not by what the panel believed.
    if not U.isAboard(player:getX(), player:getY(), player:getZ()) then
        deny(player, "distressAboard")
        return
    end

    local data = Probes.store()
    local call = data.distress
    -- **The id has to match the call that is pending.** Two crew answering at
    -- once make one mission, and an answer to a call that faded while the
    -- panel was open must not bring it back.
    if not call or type(args.id) ~= "string" or call.id ~= args.id then
        deny(player, "distressGone")
        return
    end

    local now = U.worldHours()
    data.distress = nil
    local who = Ship.usernameOf(player)

    if args.accept ~= true then
        data.nextDistressAt = now + C.DistressIntervalHours
        Probes.publish()
        U.log("distress: %s declined the call from %s", tostring(who), call.name)
        Net.toAll("distressDeclined", { name = call.name, by = who })
        return
    end

    local fx, fy = fixFor(call)
    local contact = Probes.addContact("downedPersonnel", fx, fy, call.tz,
                                      call.id, true)
    if not contact then
        -- addContact only refuses an unknown kind, and downedPersonnel is in
        -- C.ContactKinds -- so this is the two files disagreeing, and it has
        -- to be loud or it is a call that vanished for no reason.
        U.log("WARN distress: the store refused the rescue contact; the call "
              .. "from %s is lost", call.name)
        data.nextDistressAt = now + C.DistressRetryHours
        Probes.publish()
        deny(player, "distressGone")
        return
    end
    contact.tx, contact.ty, contact.tz = call.tx, call.ty, call.tz
    contact.name = call.name
    contact.division = call.division
    contact.body = call.body
    contact.item = C.ensignItem(call.body, call.division)
    contact.acceptedAt = now
    contact.deadline = now + C.EnsignLifeHours
    contact.acceptedBy = who
    Probes.publish()
    U.log("distress: %s accepted; %s has %d hours (contact %s, fix %d,%d)",
          tostring(who), call.name, C.EnsignLifeHours, contact.id, fx, fy)
    Net.toAll("distressAccepted", { name = call.name, by = who,
                                    hours = C.EnsignLifeHours })
end)

---------------------------------------------------------------------------
-- The figure
---------------------------------------------------------------------------
--- Whether the ensign can sit on this square.
local function goodGround(sq, join)
    local ok = false
    join(function()
        if not sq:getFloor() or sq:isSolid() or sq:isSolidTrans() then return end
        ok = true
    end)
    if not ok then return false end
    -- Not in the water. The floor's own sprite says so, the way vanilla's
    -- fishing code asks it.
    local wet = U.try("ensign.water", function()
        return sq:getFloor():getSprite():getProperties():has(IsoFlagType.water)
    end)
    if wet == true then return false end
    -- And not inside anybody's safehouse. The empty name is nobody -- it is
    -- neither a member nor the owner (bci 92-111) -- so the engine answers
    -- for every safehouse there is: the tricorder's call, asked about all of
    -- them at once. The last argument is **false**: true lets the server
    -- option that disables a safehouse while its owner is away (bci 52-82)
    -- report a real safehouse as none, and the ensign should not sit in
    -- somebody's house because they happen to be offline.
    local safe = U.try("ensign.safehouse", function()
        return SafeHouse.isSafeHouse(sq, "", false)
    end)
    return safe == nil
end

--- Puts the figure on the ground, once somebody has loaded it. True when the
--- contact changed.
local function placeFigure(contact, now)
    local r = C.EnsignPlaceRadius
    local cx, cy, cz = contact.tx, contact.ty, contact.tz or 0
    -- The whole search area, not just the middle: a nil square in an
    -- unloaded chunk is "ask again later", and checking only the centre would
    -- let a player passing the edge of it retire the rescue before they arrived.
    if not (U.chunkLoaded(cx - r, cy - r, cz) and U.chunkLoaded(cx + r, cy - r, cz)
            and U.chunkLoaded(cx - r, cy + r, cz)
            and U.chunkLoaded(cx + r, cy + r, cz)) then
        return false
    end

    local join = U.batch("ensign.ground")
    local best = nil
    for ring = 0, r do
        for dx = -ring, ring do
            for dy = -ring, ring do
                if math.abs(dx) == ring or math.abs(dy) == ring then
                    local sq = U.square(cx + dx, cy + dy, cz, false)
                    if sq and goodGround(sq, join) then best = sq break end
                end
            end
            if best then break end
        end
        if best then break end
    end

    if not best then
        -- Loaded, looked at, and nowhere to sit them: a lake, the middle of a
        -- warehouse. Retire it and call again soon, and say so -- a contact
        -- that silently stopped being drawn is a feature that looks broken.
        contact.status = "invalid"
        Probes.store().nextDistressAt = now + C.DistressRetryHours
        U.log("WARN ensign %s: no ground within %d squares of %d,%d; the "
              .. "signal is lost", contact.id, r, cx, cy)
        Net.toAll("ensignLost", { name = contact.name, why = "signal" })
        return true
    end

    local item = U.try("ensign.place", function()
        return best:AddWorldInventoryItem(contact.item, 0.5, 0.5, 0.0)
    end)
    if not item then
        U.log("WARN ensign %s: %s could not be put on the ground", contact.id,
              tostring(contact.item))
        return false
    end
    -- A dropped world model picks its own yaw (DEV_GUIDE). The figure is posed
    -- to face south, which is the side of it the camera sees.
    U.try("ensign.straighten", function()
        item:setWorldXRotation(0)
        item:setWorldYRotation(0)
        item:setWorldZRotation(0)
    end)

    contact.placed = true
    contact.ex = U.try("ensign.x", function() return math.floor(best:getX()) end) or cx
    contact.ey = U.try("ensign.y", function() return math.floor(best:getY()) end) or cy
    contact.ez = cz
    contact.beaconAt = nil      -- the first pulse is now, not in ten minutes
    U.log("ensign %s: %s is on the ground at %d,%d", contact.id,
          tostring(contact.name), contact.ex, contact.ey)
    return true
end

--- Takes the figure away when the mission is over. Now if its ground is loaded;
--- otherwise the square is written down and done when somebody loads it.
local function retireFigure(contact)
    if not contact.placed then return end
    local _, sq = figureOn(contact)
    if type(sq) ~= "string" and sq then
        removeFigures(sq, contact.item)
        return
    end
    table.insert(Probes.store().ensignRemovals, {
        x = contact.ex, y = contact.ey, z = contact.ez, item = contact.item })
    U.log("ensign %s: the ground is not loaded; the figure will be taken away when "
          .. "it is", contact.id)
end

--- Removals waiting for their ground. True when the list changed.
local function serviceRemovals()
    local list = Probes.store().ensignRemovals
    local changed = false
    for i = #list, 1, -1 do
        local r = list[i]
        if U.chunkLoaded(r.x, r.y, r.z) then
            local sq = U.square(r.x, r.y, r.z, false)
            if sq then removeFigures(sq, r.item) end
            table.remove(list, i)
            changed = true
        end
    end
    return changed
end

--- The combadge pulse: the engine's zombie-attraction noise at the ensign's square.
local function beacon(contact, now)
    local minutes = math.floor(now * 60)
    if contact.beaconAt and minutes < contact.beaconAt + C.BeaconEveryMinutes then
        return
    end
    local w = figureOn(contact)
    if not w then return end
    contact.beaconAt = minutes
    U.try("ensign.beacon", function()
        addSound(w, contact.ex, contact.ey, contact.ez, C.BeaconRadius,
                 C.BeaconVolume)
    end)
end

--- The clock ran out.
local function lose(contact, now)
    contact.status = "expired"
    contact.lostAt = now
    retireFigure(contact)
    Probes.store().nextDistressAt = now + C.DistressIntervalHours
    U.log("ensign %s: %s's life signs have stopped", contact.id,
          tostring(contact.name))
    Net.toAll("ensignLost", { name = contact.name, why = "time" })
    -- Shepard says the name out loud (COMMS.md 6.2).
    if TREK.CommsServer then TREK.CommsServer.event("lost", contact.name) end
end

--- Places, beacons, times out and tidies up. Authority only, every game
--- minute, wherever the players are.
function M.serviceMissions()
    local now = U.worldHours()
    local changed = serviceRemovals()

    for _, contact in ipairs(Probes.contacts()) do
        -- A `downedPersonnel` contact with no deadline is not a mission --
        -- the store's own tests make synthetic ones -- and is left alone
        -- rather than timed out on the first pass for having no clock.
        if contact.kind == "downedPersonnel" and contact.deadline
           and not Probes.isResolved(contact.status) then
            if not U.inWorld(contact.tx or contact.x, contact.ty or contact.y) then
                contact.status = "invalid"
                Probes.store().nextDistressAt = now + C.DistressRetryHours
                U.log("ensign %s: outside the world; retired", contact.id)
                changed = true
            elseif now >= contact.deadline then
                lose(contact, now)
                changed = true
            elseif not contact.placed then
                if placeFigure(contact, now) then changed = true end
            else
                -- Placed: is the figure still there? Only a loaded square can say
                -- no. Somebody who carried it off leaves a mission with no
                -- figure, and the next pass puts it back where it was.
                local w, why = figureOn(contact)
                if not w and why ~= "unloaded" then
                    contact.placed = false
                    contact.tx, contact.ty = contact.ex, contact.ey
                    U.log("ensign %s: the figure is not on its square; putting it "
                          .. "back", contact.id)
                    changed = true
                else
                    beacon(contact, now)
                end
            end
        end
    end

    if changed then
        Probes.prune()
        Probes.publish()
    end
end

---------------------------------------------------------------------------
-- The rescue
---------------------------------------------------------------------------
--- The reward: patterns the ship did not know, from a fixed list in order,
--- and a small supply into the rescuer's hands. Returns patterns learned.
local function reward(player)
    local Rep = TREK.Replicator
    local learned = 0
    for _, id in ipairs(C.RescuePatterns) do
        if learned >= C.RescuePatternsPerRescue then break end
        if not Rep.knows(id) and Rep.learn(id) then
            learned = learned + 1
            U.log("rescue: the ship has learned %s", id)
        end
    end
    if learned > 0 then Rep.publish() end

    local inv = U.try("rescue.inv", function() return player:getInventory() end)
    if inv then
        local join = U.batch("rescue.supply")
        for _, row in ipairs(C.RescueSupply) do
            for _ = 1, row[2] do
                join(function()
                    local item = instanceItem(row[1])
                    if not item then return end
                    inv:AddItem(item)
                    if isServer() then sendAddItemToContainer(inv, item) end
                end)
            end
        end
    end
    return learned
end

Net.onServer("rescueEnsign", function(player, args)
    if not mayUse(player) then return end
    local contact = Probes.byId(args.id)
    if not contact or contact.kind ~= "downedPersonnel" then
        deny(player, "ensignGone")
        return
    end
    -- **First, before anything that could pay out.** A second rescue in the
    -- same instant finds the ensign already safe and is told so.
    if contact.status == "completed" then
        deny(player, "ensignSafe")
        return
    end
    if Probes.isResolved(contact.status) then
        deny(player, "ensignGone")
        return
    end
    if not contact.placed then
        deny(player, "ensignMissing")
        return
    end

    -- Reach is measured here, from where the server has the player, not
    -- taken from the command.
    local px = U.try("rescue.px", function() return player:getX() end) or -1e9
    local py = U.try("rescue.py", function() return player:getY() end) or -1e9
    local pz = U.try("rescue.pz", function() return player:getZ() end) or -1
    local reach = C.EnsignRescueRange + 0.5
    if math.floor(pz) ~= contact.ez
       or U.dist2(px, py, contact.ex + 0.5, contact.ey + 0.5) > reach * reach then
        deny(player, "ensignFar")
        return
    end

    local w, sq = figureOn(contact)
    if not w or type(sq) == "string" then
        contact.placed = false
        Probes.publish()
        deny(player, "ensignMissing")
        return
    end
    removeFigures(sq, contact.item)

    local now = U.worldHours()
    local who = Ship.usernameOf(player)
    contact.status = "completed"
    contact.rescuedBy = who
    contact.rescuedAt = now
    Probes.store().nextDistressAt = now + C.DistressIntervalHours
    local learned = reward(player)
    Probes.prune()
    Probes.publish()
    U.log("rescue: %s beamed %s to safety (contact %s); %d pattern(s) learned",
          tostring(who), tostring(contact.name), contact.id, learned)
    Net.toAll("ensignRescued", { name = contact.name, by = who,
                                 learned = learned })
    -- The channel knows who came up, by name (COMMS.md 6.2).
    if TREK.CommsServer then TREK.CommsServer.event("rescued", contact.name) end
end)

---------------------------------------------------------------------------
-- Timers
---------------------------------------------------------------------------
Events.EveryOneMinute.Add(function()
    U.try("serviceDistress", M.serviceDistress)
    U.try("serviceMissions", M.serviceMissions)
end)

return M
