--[[ Shuttlecraft -- talking between clients and the server.

    The whole multiplayer design (MULTIPLAYER.md) rests on one rule: the server
    owns the ship and the world, and a client only ever *asks*. This file is
    the only place that knows how asking works in each of the three setups.

    What build 42 actually does, checked against its bytecode:

      * sendClientCommand reaches OnClientCommand on the server -- and in single
        player too, where it is routed through the game's in-process server.
        So a client always sends, and the server always handles, with no
        special case for single player.
      * sendServerCommand does nothing in single player (it only acts on a real
        server). So the reply path is the one place that needs a branch, and
        it lives here, in Net.toClient / Net.toAll.
      * shared/, client/ and server/ Lua all load in every process, dedicated
        servers included. Handlers are registered here and only ever invoked
        by the right event on the right side.

    Commands are plain tables of numbers, strings and booleans. The server
    validates every one: a client is a request, never a fact.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local U = TREK.Util

local Net = {}
TREK.Net = Net

Net.MODULE = "TREK"

-- cmd -> function(player, args), run where the ship's authority lives.
Net.serverHandlers = {}
-- cmd -> function(args), run on the client a reply is addressed to.
Net.clientHandlers = {}

--- True where the ship's state is authoritative: single player, or a server
--- process (dedicated, or the one a co-op host launches). False on any client
--- connected to a server.
function Net.isAuthority()
    return not isClient()
end

---------------------------------------------------------------------------
-- Client -> server
---------------------------------------------------------------------------
--- Asks the server to do something on this player's behalf.
function Net.send(player, cmd, args)
    if not player then return false end
    args = args or {}
    -- Which ship this player is dealing with (SERVERS.md, personal
    -- shuttles). The server takes it as a request like everything else: it
    -- decides for itself where the player is standing, and whether they may.
    -- The ship in hand on this machine: the one its player is dealing with
    -- (Ship.mine, every tick), or the one a piece of work was done as.
    if args.ship == nil then args.ship = U.shipNow end
    return U.try("send:" .. tostring(cmd), function()
        sendClientCommand(player, Net.MODULE, cmd, args)
        return true
    end) == true
end

-- Commands that are about one ship: the server runs each as the ship its
-- player is dealing with (Ship.contextFor). Everything else is about the
-- world -- the channel, the Captain, a raid, a rescue -- and runs as it
-- always did. TREK_Server names them, beside the handlers themselves.
Net.shipCommands = {}
function Net.aboutShip(...)
    for _, cmd in ipairs({ ... }) do Net.shipCommands[cmd] = true end
end

-- What the server tells everybody that only one ship's crew should hear:
-- her power going, her flight ending. A client dealing with another ship
-- lets it pass (runClient).
Net.crewOnly = { powerDown = true, powerUp = true, powerLow = true, emergency = true,
                 emergencyLanded = true, flightEnded = true }

function Net.onServer(cmd, fn)
    Net.serverHandlers[cmd] = fn
end

---------------------------------------------------------------------------
-- Server -> client
---------------------------------------------------------------------------
function Net.onClient(cmd, fn)
    Net.clientHandlers[cmd] = fn
end

local function runClient(cmd, args)
    local handler = Net.clientHandlers[cmd]
    if not handler then return end
    args = args or {}
    if Net.crewOnly[cmd] and args.ship ~= nil and TREK.Ship and TREK.Ship.mine
       and args.ship ~= TREK.Ship.mine() then
        return
    end
    U.try("reply:" .. tostring(cmd), handler, args)
end

--- Says which ship a reply is about, unless the caller already has.
local function stamped(args)
    args = args or {}
    if args.ship == nil then args.ship = U.shipNow end
    return args
end

--- Tells one player's client something. In single player there is no
--- network to send over, so the handler runs directly.
function Net.toClient(player, cmd, args)
    args = stamped(args)
    if isServer() then
        U.try("sendServerCommand:" .. tostring(cmd), function()
            sendServerCommand(player, Net.MODULE, cmd, args)
        end)
    else
        runClient(cmd, args)
    end
end

--- Tells every client.
function Net.toAll(cmd, args)
    args = stamped(args)
    if isServer() then
        U.try("sendServerCommandAll:" .. tostring(cmd), function()
            sendServerCommand(Net.MODULE, cmd, args)
        end)
    else
        runClient(cmd, args)
    end
end

---------------------------------------------------------------------------
-- Dispatch
---------------------------------------------------------------------------
Events.OnClientCommand.Add(function(module, cmd, player, args)
    if module ~= Net.MODULE then return end
    if isClient() then return end
    local handler = Net.serverHandlers[cmd]
    if not handler then
        U.warnOnce("unknownCommand:" .. tostring(cmd), "unknown command " .. tostring(cmd))
        return
    end
    args = args or {}
    -- A command about a ship runs as the ship this player is dealing with
    -- (SERVERS.md, personal shuttles): the one they are standing or sitting
    -- in, else the one they asked for, else their own.
    local ship = 1
    if Net.shipCommands[cmd] and TREK.Ship and TREK.Ship.contextFor then
        ship = TREK.Ship.contextFor(player, args)
    end
    -- A player standing aboard the Adirondack is served by her warp core,
    -- not the shuttle's (TREK_Power, "Two ships, two stores"), for the
    -- length of this one command -- and one in the field station by its own.
    local pool = TREK.Power and TREK.Power.poolOf and TREK.Power.poolOf(player)
    if pool and pool ~= "shuttle" then
        U.try("command:" .. tostring(cmd), U.usingShip, ship, TREK.Power.using, pool, handler, player, args)
    else
        U.try("command:" .. tostring(cmd), U.usingShip, ship, handler, player, args)
    end
end)

Events.OnServerCommand.Add(function(module, cmd, args)
    if module ~= Net.MODULE then return end
    runClient(cmd, args)
end)

return Net
