--[[ Shuttlecraft -- the field station's way in, as a player meets it.

    FIELD_STATION.md 3. In the stockroom of Muldraugh's electronics store:

      the breaker box    *Open the breaker box* -- asks the server, which
                         checks the player is standing at it and hangs the
                         lift panel in its place, for everybody
      the panel          *Lift: down to the field station* -- a move the
                         server grants (`stationDown`) and this client makes
                         (TREK_AdirondackClient.goDown)

    Both options are shown greyed with the reason when the player is across
    the room, rather than hidden: a missing option is indistinguishable from a
    broken mod (TREK_ReplicatorUI says the same).

    And one hint, for a player who walks into the stockroom with a tricorder
    in their pack before the box is open: a note, once a session.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_FieldStation"
require "TREK/TREK_AdirondackClient"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local FS = TREK.FieldStation

local FC = {}
TREK.FieldStationClient = FC

function FC.open(player)
    if not player then return false end
    if not FS.playerInReach(player) then
        U.note(player, getText("IGUI_TREK_StationFar"), 255, 170, 90)
        return false
    end
    Net.send(player, "stationOpen", {})
    return true
end

function FC.onOpen(_, player) FC.open(player) end
function FC.onDown(_, player) TREK.AdirondackClient.goDown(player) end

Net.onClient("stationOpened", function(args)
    local player = U.player(0)
    if not player then return end
    U.note(player, getText(args.again and "IGUI_TREK_StationAlreadyOpen" or "IGUI_TREK_StationOpened"),
           120, 190, 255)
end)

--- The right-click on the box, or on the panel once it is open.
function FC.fillMenu(playerIndex, context, worldobjects, test)
    local player = U.player(playerIndex)
    if not player then return end
    -- The box is only ever on the published square; before the server has
    -- placed it there is nothing on the wall to click.
    if not FS.record() then return end
    local x, y, z = U.clickedSquare(playerIndex, context, player)
    if not x or not FS.clicked(x, y, z) then return end
    if test then return ISWorldObjectContextMenu.setTest() end

    local option
    if FS.found() then
        option = context:addOption(getText("IGUI_TREK_StationDown"), worldobjects, FC.onDown, player)
    else
        option = context:addOption(getText("IGUI_TREK_StationBox"), worldobjects, FC.onOpen, player)
    end
    if not FS.playerInReach(player) then
        option.notAvailable = true
        option.toolTip = ISWorldObjectContextMenu.addToolTip()
        option.toolTip.description = getText("IGUI_TREK_StationFar")
    end
    return true
end

Events.OnPreFillWorldObjectContextMenu.Add(FC.fillMenu)

---------------------------------------------------------------------------
-- The tricorder's hint
---------------------------------------------------------------------------
local hinted = false
local hintTick = 0
-- Squares from the box within which a tricorder picks up the station.
FC.HintReach = 6

function FC.serviceHint(player)
    if hinted or FS.found() or not FS.record() then return false end
    local x, y, z = FS.standSpot()
    if math.floor(player:getZ()) ~= z then return false end
    if U.dist2(player:getX(), player:getY(), x, y) > FC.HintReach * FC.HintReach then return false end
    local carrying = U.try("fs.tricorder", function()
        return player:getInventory():containsTypeRecurse(C.TricorderType)
    end)
    if carrying ~= true then return false end
    hinted = true
    U.note(player, getText("IGUI_TREK_StationTricorder"), 120, 190, 255)
    U.log("field station: the tricorder has the station's power signature")
    return true
end

function FC.resetHint() hinted = false end

Events.OnPlayerUpdate.Add(function(player)
    if not player or not player:isLocalPlayer() then return end
    hintTick = hintTick + 1
    if hintTick < 30 then return end
    hintTick = 0
    U.try("fs.hint", FC.serviceHint, player)
end)

return FC
