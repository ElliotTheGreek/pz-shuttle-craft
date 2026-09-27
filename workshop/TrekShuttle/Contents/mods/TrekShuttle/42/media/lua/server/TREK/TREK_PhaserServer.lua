--[[ Shuttlecraft -- energy weapons kept charged by the server.

    In multiplayer the server's copy of a player's inventory is the one that
    counts: the hit anti-cheat reads the server's weapon, and kicks after two
    shots it thinks were fired empty ("PlayerHitZombiePacket: not enough
    ammo"). The phaser used to be charged only on the player's machine, so
    the server's copy ran dry while the player's kept firing, and a player
    was kicked standing still shooting (1.10.1, a dedicated server).

    So the server charges every player's energy weapons, four times a second,
    and sends each one it touched to its holder: syncHandWeaponFields for the
    charge, the chambered round and the jam, syncItemFields for the condition.
    A phaser holds more shots than anyone fires in a quarter of a second.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_PhaserCharge"

TREK = TREK or {}
local U = TREK.Util
local PCh = TREK.PhaserCharge

local PS = {}
TREK.PhaserServer = PS

PS.IntervalMs = 250

--- Charges one player's energy weapons on this copy, and tells them.
--- Returns how many were changed.
function PS.chargePlayer(player)
    local carried = PCh.carriedBy(player)
    if #carried == 0 then return 0 end
    local join = {
        ammo = U.batch("phaserServer.ammo"),
        jam  = U.batch("phaserServer.jam"),
        wear = U.batch("phaserServer.wear"),
    }
    local changed = 0
    for _, item in ipairs(carried) do
        if PCh.charge(item, join) then
            changed = changed + 1
            if isServer() then
                U.try("phaser.syncWeapon", function() syncHandWeaponFields(player, item) end)
                U.try("phaser.syncItem", function() syncItemFields(player, item) end)
            end
        end
    end
    return changed
end

local last = 0
function PS.tick()
    if not isServer() then return end
    local now = getTimestampMs()
    if now - last < PS.IntervalMs then return end
    last = now
    for _, p in ipairs(U.players()) do
        U.try("phaser.chargePlayer", PS.chargePlayer, p)
    end
end

Events.OnTick.Add(function() U.try("phaser.serverTick", PS.tick) end)

return PS
