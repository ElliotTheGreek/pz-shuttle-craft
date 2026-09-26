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
    return U.try("send:" .. tostring(cmd), function()
        sendClientCommand(player, Net.MODULE, cmd, args or {})
        return true
    end) == true
end

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
    if handler then U.try("reply:" .. tostring(cmd), handler, args or {}) end
end

--- Tells one player's client something. In single player there is no
--- network to send over, so the handler runs directly.
function Net.toClient(player, cmd, args)
    if isServer() then
        U.try("sendServerCommand:" .. tostring(cmd), function()
            sendServerCommand(player, Net.MODULE, cmd, args or {})
        end)
    else
        runClient(cmd, args)
    end
end

--- Tells every client.
function Net.toAll(cmd, args)
    if isServer() then
        U.try("sendServerCommandAll:" .. tostring(cmd), function()
            sendServerCommand(Net.MODULE, cmd, args or {})
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
    -- A player standing aboard the Adirondack is served by her warp core,
    -- not the shuttle's (TREK_Power, "Two ships, two stores"), for the
    -- length of this one command.
    local pool = TREK.Power and TREK.Power.poolOf and TREK.Power.poolOf(player)
    if pool == "adk" then
        U.try("command:" .. tostring(cmd), TREK.Power.using, "adk", handler, player, args or {})
    else
        U.try("command:" .. tostring(cmd), handler, player, args or {})
    end
end)

Events.OnServerCommand.Add(function(module, cmd, args)
    if module ~= Net.MODULE then return end
    runClient(cmd, args)
end)

return Net
