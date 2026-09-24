--[[ Shuttlecraft -- the downed ensign, as a player meets them (ENSIGN.md).

    What lives here:
      * the right-click menu: Examine, and Beam to safety;
      * the combadge chirp, played at the ensign's square by each client
        that is near -- presentation, like the lights, and never ship state;
      * what the ship says: the call coming in, being answered, fading, and
        the rescue ending one way or the other.

    **The ensign is found through the contact store, not their own mod data.**
    The store already carries their square (`ex, ey, ez`) to every client, and
    the server checks the square for the item before it does anything. Nothing
    here depends on an item's mod data surviving a world-item packet, which is
    a claim this project has never tested.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Ship"
require "TREK/TREK_Net"
require "TREK/TREK_Core"
require "TREK/TREK_Probes"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Core = TREK.Core
local P = TREK.Probes

local M = {}
TREK.EnsignUI = M

---------------------------------------------------------------------------
-- Where the ensign is
---------------------------------------------------------------------------
--- The live mission whose figure is on or beside this square, or nil.
function M.missionNear(x, y, z, margin)
    local m = P.mission()
    if not m or not m.placed or not m.ex then return nil end
    if math.floor(z) ~= m.ez then return nil end
    margin = margin or 0
    if math.abs(x - m.ex) <= margin and math.abs(y - m.ey) <= margin then
        return m
    end
    return nil
end

--- Whether this player is close enough to beam them up. The server measures
--- it again from its own copy; this only decides whether to grey the option.
function M.inReach(player, m)
    local px = U.try("ensign.px", function() return player:getX() end)
    local py = U.try("ensign.py", function() return player:getY() end)
    local pz = U.try("ensign.pz", function() return player:getZ() end)
    if not px or not py or not pz or math.floor(pz) ~= m.ez then return false end
    local reach = C.EnsignRescueRange + 0.5
    return U.dist2(px, py, m.ex + 0.5, m.ey + 0.5) <= reach * reach
end

--- Hours the ensign has left, never negative.
function M.hoursLeft(m)
    return math.max(0, math.floor((m.deadline or 0) - U.worldHours()))
end

--- One line: who they are, how they are, how long they have. The condition is read
--- off the clock, so the words and the countdown can never disagree.
function M.examineText(m)
    local left = M.hoursLeft(m)
    local frac = left / math.max(1, C.EnsignLifeHours)
    local condition = "IGUI_TREK_EnsignCondGood"
    if frac < 1 / 3 then
        condition = "IGUI_TREK_EnsignCondPoor"
    elseif frac < 2 / 3 then
        condition = "IGUI_TREK_EnsignCondFair"
    end
    return getText("IGUI_TREK_EnsignExamineText", m.name or "?",
                   getText(C.DivisionLabels[m.division] or C.DivisionLabels.Command),
                   getText(condition), tostring(left))
end

---------------------------------------------------------------------------
-- The menu
---------------------------------------------------------------------------
function M.onExamine(_, player, id)
    local m = P.byId(id)
    if not m then return end
    U.note(player, M.examineText(m), 150, 200, 255)
end

function M.onRescue(_, player, id)
    Core.send(player, "rescueEnsign", { id = id })
end

function M.fillMenu(playerIndex, context, worldobjects, test)
    local player = U.player(playerIndex)
    if not player then return end
    if U.isInteriorPlayer(player) then return end

    local x, y, z = U.clickedSquare(playerIndex, context, player)
    if not x then return end
    local m = M.missionNear(x, y, z, C.EnsignMenuMargin)
    if not m then return end
    if test then return ISWorldObjectContextMenu.setTest() end

    context:addOption(getText("IGUI_TREK_EnsignExamine", m.name or "?"),
                      worldobjects, M.onExamine, player, m.id)
    local option = context:addOption(getText("IGUI_TREK_EnsignRescue", m.name or "?"),
                                     worldobjects, M.onRescue, player, m.id)
    -- **Shown and greyed, never hidden**, with the reason on it: a player who
    -- can see the ensign and cannot see the option has no way to learn that they
    -- simply have to walk closer.
    if not M.inReach(player, m) then
        option.notAvailable = true
        option.toolTip = ISWorldObjectContextMenu.addToolTip()
        option.toolTip.description = getText("IGUI_TREK_EnsignFar",
                                             tostring(C.EnsignRescueRange))
    end
    return true
end

Events.OnPreFillWorldObjectContextMenu.Add(M.fillMenu)

---------------------------------------------------------------------------
-- The chirp
---------------------------------------------------------------------------
-- Played at the ensign's square, so it comes from them and fades with distance. Each
-- client does its own on its own timer: it is what this machine hears, the
-- way the lights are what this machine sees. The zombie-attracting half of
-- the beacon is the server's, and is a different call entirely.
local lastChirp = 0

--- Chirps if it is time and this player is near the ensign. True when it did.
function M.serviceChirp()
    local now = getTimestampMs()
    if now - lastChirp < C.ChirpEveryMs then return false end
    local m = P.mission()
    if not m or not m.placed or not m.ex then return false end
    local player = U.player(0)
    if not player then return false end
    local px = U.try("chirp.px", function() return player:getX() end)
    local py = U.try("chirp.py", function() return player:getY() end)
    local pz = U.try("chirp.pz", function() return player:getZ() end)
    if not px or not pz or math.floor(pz) ~= m.ez then return false end
    if U.dist2(px, py, m.ex, m.ey) > C.ChirpRange * C.ChirpRange then return false end
    local sq = U.square(m.ex, m.ey, m.ez, false)
    if not sq then return false end
    lastChirp = now
    U.try("ensign.chirp", function() sq:playSound("TREK_CombadgeChirp") end)
    return true
end

Events.OnTick.Add(function()
    U.try("ensign.chirpTick", M.serviceChirp)
end)

---------------------------------------------------------------------------
-- What the ship says
---------------------------------------------------------------------------
local function say(key, r, g, b, ...)
    local player = U.player(0)
    if not player then return end
    U.note(player, getText(key, ...), r, g, b)
    return player
end

Net.onClient("distressCall", function(args)
    local player = say("IGUI_TREK_DistressNote", 255, 140, 110, args.name or "?",
                       tostring(args.distance or "?"), args.compass or "?")
    if player then
        U.try("distress.sound", function() player:playSoundLocal("TREK_DistressCall") end)
    end
end)

Net.onClient("distressAccepted", function(args)
    say("IGUI_TREK_DistressAcceptedNote", 150, 220, 255, args.name or "?",
        tostring(args.hours or "?"))
end)

Net.onClient("distressDeclined", function(args)
    say("IGUI_TREK_DistressDeclinedNote", 180, 180, 200, args.name or "?")
end)

Net.onClient("distressLapsed", function(args)
    say("IGUI_TREK_DistressLapsedNote", 180, 180, 200, args.name or "?")
end)

Net.onClient("ensignRescued", function(args)
    local player = say("IGUI_TREK_EnsignRescuedNote", 150, 220, 255,
                       args.name or "?", tostring(args.learned or 0))
    if player then
        U.try("rescue.sound", function() player:playSoundLocal("TREK_Replicate") end)
    end
end)

Net.onClient("ensignLost", function(args)
    local key = args.why == "signal" and "IGUI_TREK_EnsignSignalLostNote"
                or "IGUI_TREK_EnsignLostNote"
    say(key, 255, 110, 110, args.name or "?")
end)

return M
