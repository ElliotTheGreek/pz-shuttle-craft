--[[ Shuttlecraft -- species, divisions and rank: the client's half.

    Two replies, both from TREK_Traits on the server:

      traitAdjust  the same stat change the server just made to this player,
                   applied to this machine's copy of them (TREK_Traits.lua
                   says why both copies are written)
      traitNote    a halo note

    Nothing here decides anything.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Traits"

local U = TREK.Util
local Net = TREK.Net
local T = TREK.Traits

--- The local character a reply is about: by username when the server named
--- one, so split-screen players on one machine each get their own.
local function whom(name)
    for i = 0, 3 do
        local p = U.player(i)
        if p and (name == nil or U.try("traits.name", function() return p:getUsername() end) == name) then
            return p
        end
    end
    return nil
end

Net.onClient("traitAdjust", function(args)
    local p = whom(args.who)
    if p then T.applyLocal(p, { add = args.add, set = args.set }) end
end)

Net.onClient("traitNote", function(args)
    local p = whom(args.who)
    if not p or not args.key then return end
    U.note(p, getText(args.key, args.arg and tostring(args.arg) or nil),
           args.r, args.g, args.b)
end)
