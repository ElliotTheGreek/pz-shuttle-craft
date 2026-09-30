--[[ Shuttlecraft -- the field kit's tools kept new, by the authority.

    The copy of a tool that counts is the one crafting spends: the server's
    in multiplayer (a craft is completed there), the only one in single
    player. So the authority puts every carried field tool back to full
    condition, and the laser welder back to full charge, once a second, and
    on a server sends each one it touched to its holder (syncItemFields), the
    way TREK_PhaserServer sends a phaser's condition. A tool spends little
    enough between passes that nobody runs one down.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_FieldKit"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local FK = TREK.FieldKit

local FKS = {}
TREK.FieldKitServer = FKS

--- Restores one player's tools on this copy and tells them. Returns how many
--- changed.
function FKS.servicePlayer(player)
    local changed = FK.sweep(player)
    if isServer() then
        for _, item in ipairs(changed) do
            U.try("fieldkit.sync", function() syncItemFields(player, item) end)
        end
    end
    return #changed
end

local last = 0
function FKS.tick()
    local now = getTimestampMs()
    if now - last < C.FieldKitSweepMs then return end
    last = now
    for _, p in ipairs(U.players()) do
        U.try("fieldkit.servicePlayer", FKS.servicePlayer, p)
    end
end

Events.OnTick.Add(function() U.try("fieldkit.tick", FKS.tick) end)

return FKS
