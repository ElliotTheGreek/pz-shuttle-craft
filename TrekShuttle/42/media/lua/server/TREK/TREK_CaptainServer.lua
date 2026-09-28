--[[ Shuttlecraft -- Captain Titus, on the authority (CAPTAIN.md 5.2).

    **Every player has a conversation of their own**, at the same time: two
    players on the bridge can both be talking to her, and nothing about one
    reaches the other. The channel's model -- one shared call and a holder --
    is the wrong one for a person talking to a person.

    **And the server answers every step.** A client asks `captainTalk`, then
    `captainAsk` with the node it is answering and what it chose. The server
    checks the player is on the bridge and in reach, that the node is the one
    it last sent that player, and that the choice was on offer; then it
    replies `captainSay` with the next node, the options this player may take
    and, on the hub, the topics with their NEW marks. That is the only place
    the conditions can be asked truly -- what a player has watched, wears and
    has done (TREK_Comms: "only answered truly on the authority").

    **She changes nothing in the story** (CAPTAIN.md 5.4). No channel flag, no
    tape, no item. Two things are written, both about the player in front of
    her and both on the server's copy of them: what they have heard and told
    her (C.CaptainKey), and a promotion their rescues have earned
    (TRAITS.md 4.5, confirmed in person since CAPTAIN.md).

    Sessions are not saved: one is dropped when the panel closes, the player
    leaves her reach or goes offline.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_Captain"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Ship = TREK.Ship
local Cap = TREK.Captain

local S = {}
TREK.CaptainServer = S

-- username -> { node = id }
S.sessions = {}

local function nameOf(player)
    return Ship.usernameOf(player)
end

local function deny(player, why, extra)
    local args = extra or {}
    args.why = why
    Net.toClient(player, "denied", args)
end

--- The session for this player, or nil.
function S.session(player)
    return S.sessions[nameOf(player) or ""]
end

local function drop(player)
    local name = nameOf(player)
    if name then S.sessions[name] = nil end
end

---------------------------------------------------------------------------
-- Entering a node
---------------------------------------------------------------------------
local function promote(player)
    local TS, T = TREK.TraitsServer, TREK.Traits
    if not (TS and T) then return false end
    local now = TS.earnedRank(player) or 0
    local was = T.rank(player) or 0
    if now <= was then
        U.log("WARN captain: %s reached the promotion with nothing due (%d, %d)",
              tostring(nameOf(player)), was, now)
        return false
    end
    TS.setRank(player, now)
    T.note(player, "IGUI_TREK_Promoted", getText("UI_trait_trek_" .. C.Ranks[now]),
           255, 220, 120)
    U.log("captain: promoted %s to %s", tostring(nameOf(player)), C.Ranks[now])
    return true
end

--- Moves this player's conversation to node `id` and tells them. Applies what
--- the node does: its marks, a promotion, and what they have now heard.
local function enter(player, id)
    local tree = Cap.tree()
    local nd = tree.nodes[id]
    if not nd then
        U.log("WARN captain: no node %s", tostring(id))
        drop(player)
        Net.toClient(player, "captainSay", { ended = true })
        return
    end
    if not Cap.tierOpen(id, player) then
        -- The option into it was offered only if the tier was open, so this
        -- is a tree that routes round its own gates. Never show it.
        U.log("WARN captain: %s is shut to %s; back to the topics", id,
              tostring(nameOf(player)))
        id = Cap.route(tree.hub.home, player)
        nd = tree.nodes[id]
        if not nd then drop(player) return end
    end
    local rec = Cap.record(player)
    for _, m in ipairs(nd.mark or {}) do rec.marks[m] = true end
    if nd.promote then promote(player) end
    if nd.tier then rec.heard[nd.topic .. ":" .. nd.tier] = true end

    local bye = Cap.isBye(id)
    local session = S.sessions[nameOf(player)]
    if bye then
        S.sessions[nameOf(player)] = nil
    elseif session then
        session.node = id
    else
        S.sessions[nameOf(player)] = { node = id }
    end
    local avail = Cap.available(id, player)
    -- The questions that lead somewhere this player has not been: the NEW
    -- mark, one level down (CAPTAIN.md 5.3).
    local fresh = {}
    for _, i in ipairs(avail) do
        local to = nd.options[i] and tree.nodes[nd.options[i].go]
        if to and to.tier and not rec.heard[to.topic .. ":" .. to.tier] then
            table.insert(fresh, i)
        end
    end
    local reply = {
        node = id,
        avail = avail,
        fresh = fresh,
        named = rec.marks.named == true,
        ended = bye or nil,
    }
    if Cap.isList(id) then
        local topics = {}
        for _, t in ipairs(Cap.topics(player)) do
            table.insert(topics, { id = t.id, new = t.new or nil })
        end
        reply.topics = topics
    end
    Net.toClient(player, "captainSay", reply)
end
S.enter = enter

local function offered(list, i)
    for _, x in ipairs(list) do
        if x == i then return true end
    end
    return false
end

---------------------------------------------------------------------------
-- Handlers
---------------------------------------------------------------------------
Net.onServer("captainTalk", function(player, args)
    if not Cap.inReach(player) then
        deny(player, "captainFar")
        return
    end
    local tree = Cap.tree()
    local id = Cap.route(tree.hub.entry, player)
    U.debug("captain: %s sits down (%s)", tostring(nameOf(player)), tostring(id))
    S.sessions[nameOf(player)] = { node = id }
    enter(player, id)
end)

Net.onServer("captainAsk", function(player, args)
    local session = S.session(player)
    if not session or not args or args.node ~= session.node then
        deny(player, "captainStale")
        return
    end
    if not Cap.inReach(player) then
        drop(player)
        deny(player, "captainFar")
        return
    end
    local tree = Cap.tree()
    local nd = tree.nodes[session.node]
    local go = nil
    if args.bye then
        go = "BYE"
    elseif args.back then
        -- Back to the topics, from any topic node.
        if not nd or nd.topic == "HUB" then
            deny(player, "captainStale")
            return
        end
        go = "HUB"
    elseif args.topic then
        if not Cap.isList(session.node) then
            deny(player, "captainStale")
            return
        end
        local ok = false
        for _, t in ipairs(Cap.topics(player)) do
            if t.id == args.topic then ok = true end
        end
        if not ok then
            deny(player, "captainStale")
            return
        end
        go = Cap.route(tree.topics[args.topic].entry, player)
    else
        local i = tonumber(args.o)
        if not i or not offered(Cap.available(session.node, player), i) then
            deny(player, "captainStale")
            return
        end
        local o = nd.options[i]
        for _, m in ipairs(o.mark or {}) do Cap.record(player).marks[m] = true end
        go = o.go
    end
    if go == "HUB" then
        go = Cap.route(tree.hub.home, player)
    elseif go == "BYE" then
        go = Cap.route(tree.hub.bye, player)
    end
    enter(player, go)
end)

Net.onServer("captainClose", function(player)
    drop(player)
end)

--- Sessions whose player has gone: out of reach, offline or dead.
function S.sweep()
    local here = {}
    for _, p in ipairs(U.players()) do
        local name = nameOf(p)
        if name then here[name] = p end
    end
    for name in pairs(S.sessions) do
        local p = here[name]
        local dead = p and U.try("captain.dead", function() return p:isDead() end)
        if not p or dead or not Cap.inReach(p) then S.sessions[name] = nil end
    end
end

local lastSweep = 0
Events.OnTick.Add(function()
    local t = getTimestampMs()
    if t - lastSweep < 2000 then return end
    lastSweep = t
    U.try("captain.sweep", S.sweep)
end)

return S
