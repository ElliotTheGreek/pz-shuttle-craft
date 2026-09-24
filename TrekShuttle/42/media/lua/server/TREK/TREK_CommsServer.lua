--[[ Shuttlecraft -- the Adirondack channel's authority (COMMS.md 2 and 4).

    Runs where the world is authoritative -- single player, or the server --
    and never on a client. It owns:

      * **the scheduler**: which incoming call rings, and when -- days since
        day zero, flags, what has already run, the gap between calls, and the
        worse follow-up a missed call becomes;
      * **the call**: one per ship. Ringing, then live with a holder; the
        server walks the tree, the holder picks from the options the server
        says are available, and a client naming anything else is refused
        rather than trusted (COMMS.md 2);
      * **the holder**: whoever answers first, from wherever they are, as long
        as they carry a PADD. Released when they go, drop their PADD, or sit on
        the channel without choosing for C.CommsIdleSeconds;
      * **the clock**: a timed node takes its silence branch when its time
        runs out. Measured in seconds of play on this machine's tick, each
        tick capped, so a pause or a hitch does not eat a player's answer;
      * **the history**: one row per finished call, node ids and option
        numbers only, published when the call ends.

    The scheduler runs on the game-minute tick **outside** any branch that
    needs a player near anything: a call is a logical job with no world object
    behind it (DEV_GUIDE: *A guard gated on loaded ground never sees the case
    it exists for*).
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_Padd"
require "TREK/TREK_Comms"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Ship = TREK.Ship
local Cm = TREK.Comms

local S = {}
TREK.CommsServer = S

-- Seconds of play on the current node and since the holder last chose.
-- Server-local: nobody else needs them, and publishing a clock every tick is
-- exactly the table-that-changes-every-frame this file exists to avoid.
S.onNode = 0
S.idle = 0
S.lastMs = nil
S.presenceAt = 0

local function deny(player, why, extra)
    local args = extra or {}
    args.why = why
    Net.toClient(player, "denied", args)
end

local function now()
    return U.worldHours()
end

local function nameOf(player)
    local forename = U.try("comms.forename", function()
        return player:getDescriptor():getForename()
    end)
    if type(forename) == "string" and forename ~= "" then return forename end
    return Ship.usernameOf(player)
end

--- The online player with this username, or nil.
local function playerNamed(username)
    if not username then return nil end
    for _, p in ipairs(U.players()) do
        if Ship.usernameOf(p) == username then return p end
    end
    return nil
end

--- Alive, allowed to use the ship, and carrying a PADD: the channel's gate.
local function mayTalk(player, quiet)
    if not player then return false end
    if U.try("comms.dead", function() return player:isDead() end) ~= false then
        return false
    end
    if not Ship.canUse(player) then
        if not quiet then deny(player, "access") end
        return false
    end
    if #TREK.Padd.carried(player) == 0 then
        if not quiet then deny(player, "commsNoPadd") end
        return false
    end
    return true
end

---------------------------------------------------------------------------
-- Day zero, and what the rest of the mod tells the channel
---------------------------------------------------------------------------
--- Sets day zero the first time the ship is found to be built. Returns true
--- when it changed anything.
function S.commission()
    local d = Cm.store()
    if d.day0 then return false end
    if not U.state().built then return false end
    d.day0 = now()
    d.flags.commissioned = true
    U.log("comms: day zero is hour %.1f; the first call is due on day %d",
          d.day0, C.CommsFirstContactDay)
    return true
end

--- Something happened that the channel should know about. Authority only.
---   rescued, name -- an ensign was brought up
---   lost, name    -- an ensign's beacon stopped
---   clue          -- a probe found a clue site
function S.event(kind, name)
    local d = Cm.store()
    if kind == "rescued" then
        d.rescued = (d.rescued or 0) + 1
        d.lastName = name
        d.flags.thanksDue = true
    elseif kind == "lost" then
        d.lost = (d.lost or 0) + 1
        d.lastName = name
        d.flags.lostDue = true
    elseif kind == "clue" then
        d.flags.clueSeen = true
    else
        U.log("WARN comms: unknown event %s", tostring(kind))
        return
    end
    Cm.publish()
end

---------------------------------------------------------------------------
-- Walking the tree
---------------------------------------------------------------------------
local function applyFlags(sets, clears)
    local d = Cm.store()
    for _, f in ipairs(sets or {}) do d.flags[f] = true end
    for _, f in ipairs(clears or {}) do d.flags[f] = nil end
end

--- The options on `nd` the holder may take, as indices.
local function available(nd, holder)
    local out = {}
    for i, o in ipairs(nd.options or {}) do
        if Cm.allow(o.requires, o.forbids, holder) then table.insert(out, i) end
    end
    return out
end

--- Ends the live call and writes its row. `outcome`: done, missed or cut.
function S.finish(outcome)
    local d = Cm.store()
    local call = d.call
    if not call then return end
    local t = Cm.tree().threads[call.thread]
    local at = now()
    local log = Cm.log()
    table.insert(log.rows, { id = call.id, t = call.thread, d = Cm.day() or 0,
                             h = call.holderName, s = call.steps, out = outcome,
                             a1 = call.a1, a2 = call.a2 })
    while #log.rows > C.CommsLogMax do table.remove(log.rows, 1) end

    d.lastAt[call.thread] = at
    if t and t.kind == "incoming" then d.lastEnd = at end
    if outcome == "done" then
        d.fired[call.thread] = (d.fired[call.thread] or 0) + 1
        d.retryAt[call.thread] = nil
    else
        d.misses[call.thread] = (d.misses[call.thread] or 0) + 1
        if t and t.retry then
            d.retryAt[call.thread] = at + C.CommsRetryHours
        else
            -- A call whose consequence is that you missed it. A repeatable
            -- one lets go of the event it was waiting on, so the next rescue
            -- rings afresh rather than this one ringing for ever.
            d.fired[call.thread] = (d.fired[call.thread] or 0) + 1
            if t and t.repeatable then
                for _, f in ipairs(t.requires or {}) do
                    if Cm.tree().systemFlags then
                        for _, sf in ipairs(Cm.tree().systemFlags) do
                            if sf == f then d.flags[f] = nil end
                        end
                    end
                end
            end
        end
    end
    d.call = nil
    S.onNode, S.idle = 0, 0
    U.log("comms: call %s (%s) ended: %s", tostring(call.id), call.thread, outcome)
    Cm.publishLog()
    Cm.publish()
    if outcome ~= "done" then
        Net.toAll("commsEnded", { thread = call.thread, outcome = outcome })
    end
end

--- Enters a node: follows routes, applies what the node does, records it,
--- and ends the call at a node with nothing to answer.
local function enter(nodeId, holder)
    local d = Cm.store()
    local call = d.call
    local tree = Cm.tree()
    local nd = tree.nodes[nodeId]
    -- Routes are invisible and are not recorded; the validator guarantees
    -- every one ends in an unconditional arm, and the hop count is a guard
    -- against a generator bug rather than a design.
    local hops = 0
    while nd and nd.route and hops < 20 do
        local nextId = nil
        for _, arm in ipairs(nd.route) do
            if Cm.allow(arm.requires, arm.forbids, holder) then
                nextId = arm.go
                break
            end
        end
        nodeId = nextId
        nd = nodeId and tree.nodes[nodeId]
        hops = hops + 1
    end
    if not nd then
        U.log("WARN comms: call %s walked to %s, which is not a node; cut",
              tostring(call and call.id), tostring(nodeId))
        S.finish("cut")
        return
    end

    applyFlags(nd.sets, nd.clears)
    for _, tape in ipairs(nd.issue or {}) do S.issueTape(tape) end
    if nd.convert then S.convert(holder) end

    call.node = nodeId
    call.nodeSerial = (call.nodeSerial or 0) + 1
    table.insert(call.steps, { n = nodeId })
    call.avail = available(nd, holder)
    call.timeout = nd.timeout
    S.onNode, S.idle = 0, 0

    if nd.terminal then
        S.finish("done")
        return
    end
    -- A node whose every option is closed to this holder and which has no
    -- silence to fall back on: gen_comms.py refuses to write one, so this is
    -- the two files disagreeing, and it has to be loud.
    if #call.avail == 0 and not nd.silence then
        U.log("WARN comms: node %s offers %s nothing; cut", nodeId,
              tostring(call.holder))
        S.finish("cut")
        return
    end
    Cm.publish()
end

--- The entry a call opens on: the worse one for each miss before it.
local function entryFor(threadId)
    local t = Cm.tree().threads[threadId]
    local misses = Cm.store().misses[threadId] or 0
    local i = math.min(misses + 1, #t.entries)
    return t.entries[i]
end

local function newCall(threadId, state)
    local d = Cm.store()
    d.serial = d.serial + 1
    d.call = {
        id = "call:" .. tostring(d.serial),
        thread = threadId,
        state = state,
        steps = {},
        a2 = d.lastName,
        startedAt = now(),
    }
    return d.call
end

local function takeHolder(call, player)
    call.holder = Ship.usernameOf(player)
    call.holderName = nameOf(player)
    -- The holder's name is fixed at the moment they first speak. It is what
    -- the history is rendered with, so a call is read back as it was said.
    call.a1 = call.a1 or call.holderName
end

---------------------------------------------------------------------------
-- The scheduler
---------------------------------------------------------------------------
--- Whether an incoming thread may ring now.
function S.eligible(threadId, at)
    local d = Cm.store()
    local t = Cm.tree().threads[threadId]
    if not t or t.kind ~= "incoming" then return false end
    if (d.fired[threadId] or 0) > 0 and not t.repeatable then return false end
    if t.day and (Cm.day() or -1) < t.day then return false end
    if t.after then
        if (d.fired[t.after] or 0) == 0 then return false end
        if at < (d.lastAt[t.after] or 0) + (t.afterHours or 0) then return false end
    end
    if d.retryAt[threadId] and at < d.retryAt[threadId] then return false end
    if t.cooldown and d.lastAt[threadId]
       and at < d.lastAt[threadId] + t.cooldown then
        return false
    end
    return Cm.allow(t.requires, t.forbids, nil)
end

--- Rings the first thread that may ring. Returns its id, or nil.
function S.schedule(at)
    local d = Cm.store()
    if d.call then return nil end
    if not d.day0 then return nil end
    if d.lastEnd and at < d.lastEnd + C.CommsGapHours then return nil end
    for _, id in ipairs(Cm.tree().order) do
        if S.eligible(id, at) then
            local call = newCall(id, "ringing")
            call.ringUntil = at + C.CommsRingHours
            Cm.publish()
            U.log("comms: %s is ringing (call %s)", id, call.id)
            Net.toAll("commsRing", { thread = id, id = call.id })
            return id
        end
    end
    return nil
end

--- Every game minute: day zero, the ring window, a holderless call left
--- hanging, and the next ring.
function S.service()
    local changed = S.commission()
    local d = Cm.store()
    local at = now()
    local call = d.call
    if call and call.state == "ringing" and at >= (call.ringUntil or 0) then
        U.log("comms: nobody answered %s", call.thread)
        S.finish("missed")
        return
    end
    -- A live call nobody holds and nobody picks back up is cut after a
    -- ring's length, and counts as missed: it comes back worse, rather than
    -- blocking the channel for the life of the save.
    if call and call.state == "live" and not call.holder then
        call.orphanSince = call.orphanSince or at
        if at >= call.orphanSince + C.CommsRingHours then
            S.finish("cut")
            return
        end
    elseif call then
        call.orphanSince = nil
    end
    S.flushTapes()
    if not d.call then
        if S.schedule(at) then return end
    end
    if changed then Cm.publish() end
end

---------------------------------------------------------------------------
-- The clock and the holder
---------------------------------------------------------------------------
--- Releases the holder, leaving the call where it is for somebody else.
local function release(why)
    local call = Cm.store().call
    if not call or not call.holder then return end
    U.log("comms: %s let go of call %s (%s)", tostring(call.holder), call.id, why)
    local was = call.holder
    call.holder = nil
    S.idle = 0
    Cm.publish()
    Net.toAll("commsReleased", { by = call.holderName or was, why = why })
end

--- Once a tick: the node's own timer, the idle timer, and whether the
--- holder is still there to hold anything.
function S.tick()
    local call = Cm.store().call
    local ms = getTimestampMs()
    local dt = 0
    if S.lastMs then dt = math.max(0, (ms - S.lastMs) / 1000) end
    S.lastMs = ms
    if not call or call.state ~= "live" then return end
    dt = math.min(dt, C.CommsMaxTickSeconds)

    local nd = Cm.tree().nodes[call.node]
    S.onNode = S.onNode + dt
    if call.holder then S.idle = S.idle + dt end

    if nd and nd.timeout and S.onNode >= nd.timeout then
        -- Silence is an answer (COMMS.md 2): the call goes on as though the
        -- holder said nothing, and the transcript says so.
        local holder = playerNamed(call.holder)
        call.steps[#call.steps].o = 0
        U.log("comms: silence on %s", call.node)
        enter(nd.silence, holder)
        return
    end

    if S.idle >= C.CommsIdleSeconds then
        release("idle")
        return
    end

    -- Presence, about once a second of play: still online, alive, and
    -- carrying a PADD. Losing the PADD releases the channel (COMMS.md 2).
    S.presenceAt = S.presenceAt + dt
    if call.holder and S.presenceAt >= 1 then
        S.presenceAt = 0
        local p = playerNamed(call.holder)
        if not p then
            release("gone")
        elseif not mayTalk(p, true) then
            release("nopadd")
        end
    end
end

---------------------------------------------------------------------------
-- What a player can ask
---------------------------------------------------------------------------
Net.onServer("commsAnswer", function(player, args)
    if not mayTalk(player) then return end
    local d = Cm.store()
    local call = d.call
    if not call or type(args.id) ~= "string" or call.id ~= args.id then
        deny(player, "commsGone")
        return
    end
    local who = Ship.usernameOf(player)
    if call.holder and call.holder ~= who then
        -- First to the server wins; the second is told why (COMMS.md 2).
        deny(player, "commsHeld", { by = call.holderName })
        return
    end
    if call.holder == who then return end
    takeHolder(call, player)
    if call.state == "ringing" then
        call.state = "live"
        call.ringUntil = nil
        U.log("comms: %s answered %s", who, call.thread)
        Net.toAll("commsAnswered", { by = call.holderName, thread = call.thread })
        enter(entryFor(call.thread), player)
    else
        -- Picking up a call somebody let go of: the node stands, and so do
        -- its options -- re-asked for the new holder, whose pockets and
        -- whose viewing are their own.
        local nd = Cm.tree().nodes[call.node]
        call.avail = nd and available(nd, player) or {}
        U.log("comms: %s picked up %s at %s", who, call.thread, tostring(call.node))
        Net.toAll("commsAnswered", { by = call.holderName, thread = call.thread })
        Cm.publish()
    end
end)

Net.onServer("commsChoose", function(player, args)
    if not mayTalk(player) then return end
    local d = Cm.store()
    local call = d.call
    if not call or type(args.id) ~= "string" or call.id ~= args.id
       or call.state ~= "live" then
        deny(player, "commsGone")
        return
    end
    if call.holder ~= Ship.usernameOf(player) then
        deny(player, "commsHeld", { by = call.holderName })
        return
    end
    -- **The option has to be on the node the server believes is live**, and
    -- one the server offered this holder. A client naming anything else is
    -- a stale screen or a forged packet, and either way it is refused.
    local idx = tonumber(args.option)
    local offered = false
    for _, i in ipairs(call.avail or {}) do
        if i == idx then offered = true end
    end
    if args.node ~= call.node or not offered then
        deny(player, "commsStale")
        return
    end
    local nd = Cm.tree().nodes[call.node]
    local o = nd and nd.options and nd.options[idx]
    if not o then
        deny(player, "commsStale")
        return
    end
    applyFlags(o.sets, o.clears)
    call.steps[#call.steps].o = idx
    enter(o.go, player)
end)

Net.onServer("commsHail", function(player, args)
    if not mayTalk(player) then return end
    local d = Cm.store()
    if d.call then
        deny(player, "commsBusy")
        return
    end
    local at = now()
    if d.hailAt and at < d.hailAt then
        Net.toClient(player, "commsNoAnswer", {})
        return
    end
    for _, id in ipairs(Cm.tree().order) do
        local t = Cm.tree().threads[id]
        if t.kind == "hail" and ((d.fired[id] or 0) == 0 or t.repeatable)
           and not (t.cooldown and d.lastAt[id] and at < d.lastAt[id] + t.cooldown)
           and Cm.allow(t.requires, t.forbids, player) then
            local call = newCall(id, "live")
            takeHolder(call, player)
            U.log("comms: %s hailed; %s picks up", Ship.usernameOf(player), id)
            enter(entryFor(id), player)
            return
        end
    end
    -- Most of the time, nobody picks up (COMMS.md 4). That is not a stub; it
    -- is the situation. It is still said, because a hail that does nothing
    -- visible reads as a broken button.
    d.hailAt = at + C.CommsHailCooldownHours
    Cm.publish()
    Net.toClient(player, "commsNoAnswer", {})
end)

---------------------------------------------------------------------------
-- Tapes the channel issues (LORE.md 6, COMMS.md 4)
---------------------------------------------------------------------------
--- Records that the ship has been given a tape. It reaches the shelf the
--- next time the cabin is built and loaded -- TREK_Build asks for
--- `pendingTapes` -- so it lands in a save whether or not anybody is aboard.
function S.issueTape(tapeId)
    local d = Cm.store()
    if d.issued[tapeId] then return false end
    d.issued[tapeId] = true
    table.insert(d.pendingTapes, tapeId)
    U.log("comms: the ship has been issued %s", tapeId)
    return true
end

--- The shelf's half, left to TREK_Build. A stub here until the build pass
--- grows it; the list is persisted either way.
function S.flushTapes()
    if TREK.Build and TREK.Build.deliverTapes then
        U.try("comms.deliverTapes", TREK.Build.deliverTapes)
    end
end

--- Converts the fragments the holder carries (COMMS.md 6.3). Filled in with
--- the clue chain; declared now so a node that asks for it is not a nil call.
function S.convert(holder)
    if TREK.Fragments and TREK.Fragments.convert then
        TREK.Fragments.convert(holder)
    end
end

---------------------------------------------------------------------------
-- Timers
---------------------------------------------------------------------------
Events.EveryOneMinute.Add(function()
    U.try("comms.service", S.service)
end)

Events.OnTick.Add(function()
    U.try("comms.tick", S.tick)
end)

return S
