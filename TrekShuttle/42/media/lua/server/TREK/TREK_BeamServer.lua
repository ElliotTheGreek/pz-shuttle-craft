--[[ Shuttlecraft -- the transporter as it is seen: the server's half (BEAM.md).

    A departure is announced from here, because every beam in the mod is a
    `move` the server grants (TREK_Server's handler calls BS.departing), and at
    that moment the character is still standing where they are leaving from.

    An arrival is not the server's to see: the client moves its own character
    (DEV_GUIDE, *The server owns the ship; a client asks*), so the arriving
    client reports it and this relays it to everybody. It relays only an
    arrival it sent somebody on -- one report per granted beam, inside
    C.BeamFx.arrivalWindowMs -- so a client cannot make sparkles on demand.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_Beam"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Ship = TREK.Ship
local B = TREK.Beam

local BS = {}
TREK.BeamServer = BS

-- username -> when their last beam was granted, until they report arriving.
BS.sent = {}

local function now() return getTimestampMs() end

local function where(player)
    local x = U.try("beamFx.x", function() return player:getX() end)
    local y = U.try("beamFx.y", function() return player:getY() end)
    local z = U.try("beamFx.z", function() return player:getZ() end)
    return x, y, z
end

--- A granted move: if it is a beam, everybody sees the column go up where
--- the character is standing now.
function BS.departing(player, kind)
    if not player or not B.isBeam(kind) then return false end
    local x, y, z = where(player)
    if not x or not y then return false end
    BS.sent[Ship.usernameOf(player)] = now()
    Net.toAll("beamFx", B.args(player, "out", x, y, z or 0))
    return true
end

--- The arriving client says where it came down; everybody else is told.
Net.onServer("beamedIn", function(player, args)
    local who = Ship.usernameOf(player)
    local at = BS.sent[who]
    if not at or now() - at > C.BeamFx.arrivalWindowMs then return end
    BS.sent[who] = nil
    local x, y, z = tonumber(args.x), tonumber(args.y), tonumber(args.z)
    if not x or not y then x, y, z = where(player) end
    if not x or not y then return end
    Net.toAll("beamFx", B.args(player, "in", x, y, z or 0))
end)

return BS
