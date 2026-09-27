--[[ Shuttlecraft -- the field station's way in, shared by both sides.

    FIELD_STATION.md. The station's sublevels are decks of the Adirondack's
    layout (`site = "fst"`, TREK_Adirondack); this file is only the part that
    is not: the store in Muldraugh, the breaker box on its stockroom wall, and
    the lift panel behind it.

    **Where the box is, is the server's to say.** C.FieldStation names a
    square read off the vanilla map, and the server checks it in every world
    before it touches the wall; if it fails, it looks along the same room for
    one that passes. So the square every client uses is the one the server
    publishes in the ship state, `s.station`, and C.FieldStation only until
    that arrives.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Ship"
require "TREK/TREK_Adirondack"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local FS = {}
TREK.FieldStation = FS

FS.StateKey = "TREK_FieldStation"
FS.TAG = "fst"

-- The disguise and what is behind it, by the wall they hang on. Both are
-- wall pieces of the Adirondack's furniture sheet: `fuse_box`, the last
-- piece in tools/adirondack_objects.py, and her lift's own panel.
FS.BoxSprite = { W = "trek_adirondack_02_211", N = "trek_adirondack_02_212" }
FS.PanelSprite = { W = "trek_adirondack_02_174", N = "trek_adirondack_02_175" }

--- The published record: { x, y, z, edge, found }, or nil before the server
--- has placed anything.
function FS.record()
    local s = TREK.Ship.get()
    return type(s.station) == "table" and s.station or nil
end

--- Where the box is: the published square, else the configured one.
function FS.spot()
    local r = FS.record()
    if r and r.x and r.y then return r.x, r.y, r.z or 0, r.edge or "W" end
    local site = C.FieldStation
    return site.x, site.y, site.z, site.edge
end

--- True once somebody has opened the box, for everybody.
function FS.found()
    local r = FS.record()
    return r ~= nil and r.found == true
end

--- The middle of the square the box hangs on: where a player stands to use
--- it, and where they come up.
function FS.standSpot()
    local x, y, z = FS.spot()
    return x + 0.5, y + 0.5, z
end

--- True when a position is within reach of the box: on its level, and close.
function FS.inReach(x, y, z)
    if not x or not y then return false end
    local sx, sy, sz = FS.standSpot()
    if z and math.floor(z) ~= sz then return false end
    local r = C.FieldStation.reach
    return U.dist2(x, y, sx, sy) <= r * r
end

function FS.playerInReach(player)
    if not player then return false end
    local ok, yes = pcall(function()
        return FS.inReach(player:getX(), player:getY(), player:getZ())
    end)
    return ok and yes == true
end

--- For a right-click: a clicked square on, or one square round, the box's.
--- A wall piece is drawn above its square, and a click resolves to the floor
--- under the cursor (DEV_GUIDE, *A right-click lands on the floor*).
function FS.clicked(x, y, z)
    if not x or not y then return false end
    local sx, sy, sz = FS.spot()
    if z and math.floor(z) ~= sz then return false end
    return math.abs(math.floor(x) - sx) <= 1 and math.abs(math.floor(y) - sy) <= 1
end

--- The station's first sublevel: the deck a ride down arrives on.
function FS.firstDeck()
    local list = TREK.Adirondack.decksOf("fst")
    return list[1]
end

return FS
