--[[ Shuttlecraft -- the perimeter phaser sentry: what both sides agree on (SENTRY.md).

    A small emitter set down on the ground. Once armed it shoots the nearest
    of the dead within C.SentryRange, one every C.SentryShotMs, until its
    charges are spent: lead a horde past it and it thins the horde, and a big
    one gets through. Picked up, it keeps what charge it has; at a warp core
    it is recharged from the ship's power.

    **The charge is on the item** (C.SentryChargesKey in its mod data, absent
    meaning full), so it travels with the sentry wherever it goes -- in a
    pocket, on the ground, in a locker. **Which sentries are set down is the
    server's** (TREK_SentryServer): it places them, finds them again by the id
    it wrote on them, fires them and sends every client the bolt.

    This file holds the rules both sides read, so a menu greys an option for
    exactly the reason the server would refuse it.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local SN = {}
TREK.Sentry = SN

-- What the server writes on a sentry it has set down, to find it again.
SN.ID_KEY = "TREKSentryId"
-- How far from the square in front of them a player may be to set one down.
SN.REACH = 2.6

--- True for the sentry item.
function SN.isSentry(item)
    return item ~= nil and U.try("sentry.type", function() return item:getFullType() end) == C.SentryItem
end

--- Shots left in a sentry item: its own count, or full if it has never fired.
function SN.charges(item)
    local md = item and U.try("sentry.md", function() return item:getModData() end)
    local n = md and tonumber(md[C.SentryChargesKey])
    if not n then return C.SentryCharges end
    return math.max(0, math.floor(n))
end

--- The square in front of a player, where a sentry goes: x, y, z.
function SN.spotInFront(player)
    local x = U.try("sentry.px", function() return player:getX() end)
    local y = U.try("sentry.py", function() return player:getY() end)
    local z = U.try("sentry.pz", function() return player:getZ() end)
    if not x or not y then return nil end
    local dx = U.try("sentry.dx", function() return player:getForwardDirectionX() end) or 0
    local dy = U.try("sentry.dy", function() return player:getForwardDirectionY() end) or 0
    local len = math.sqrt(dx * dx + dy * dy)
    if len < 0.01 then dx, dy, len = 0, 1, 1 end
    return math.floor(x + dx / len * 1.2), math.floor(y + dy / len * 1.2), math.floor(z or 0)
end

--- Why a sentry may not go down on this square, or nil: a key a menu shows
--- and a denial the server sends (TREK_Core's DENIALS).
function SN.squareRefusal(sq)
    if not sq then return "sentryBlocked" end
    local ok = U.try("sentry.square", function()
        if not sq:getFloor() then return false end
        if sq:isSolid() or sq:isSolidTrans() then return false end
        return true
    end)
    if ok ~= true then return "sentryBlocked" end
    local x, y, z = sq:getX(), sq:getY(), sq:getZ()
    -- The cabin and her decks have their own defences, and a sentry firing
    -- across a deck would shoot her crew's bodies (they cannot be hurt, but
    -- it would never stop trying).
    if U.isAboard(x, y, z) or (TREK.Adirondack and TREK.Adirondack.locate(x, y, z)) then
        return "sentryAboard"
    end
    return nil
end

return SN
