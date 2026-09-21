--[[ Shuttlecraft -- the warp core, from the player's side.

    The fixture amidships that holds the ship's dilithium. It is the mod's own
    world model standing on 1,3, and it has no container: a container in this
    engine comes from a *tile sprite's* properties, so a custom model cannot
    have one, and standing a model over a vanilla cabinet to borrow its
    container is the arrangement the replicator was rebuilt to get rid of
    (DEV_GUIDE.md, "A fixture that leans on another fixture is not a fixture
    yet").

    So what it holds is one number in the ship state, and this file is the two
    ways a player changes it: *Load a dilithium crystal* and *Take a crystal*,
    both on the right-click menu of the square it stands on.

    **Keyed to the square, not to the model.** A right-click resolves to the
    floor square under the cursor, which is what made the replicator's first
    model unusable -- so the option is offered for the core's own square and
    the ones around it, exactly as the replicator's is.

    Nothing here changes anything. Both options are a request to the server,
    which checks the range on its own copy of where the player is standing and
    looks in its own copy of their inventory. A client is a request, never a
    fact.
]]

-- Menus and notes: nothing here has anything to say on a dedicated server,
-- and the two commands it sends are handled in server/.
if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Power"
require "TREK/TREK_Ship"
require "TREK/TREK_Core"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Core = TREK.Core
local P = TREK.Power

local W = {}
TREK.WarpCoreUI = W

--- Whether this square is the core's, or close enough to be its handle.
---
--- One tile of margin, for the reason the replicator's menu has it: a model
--- is drawn tall and the cursor naturally lands on the deck in front of it
--- rather than on the square it stands on.
local MARGIN = 1

function W.isCore(x, y, z)
    if not x or not y then return false end
    if math.floor(z or 0) ~= C.CabinZ then return false end
    local cx, cy = U.at(P.chamberSpot())
    return math.abs(x - cx) <= MARGIN and math.abs(y - cy) <= MARGIN
end

function W.onLoad(player)
    Core.send(player, "loadCrystal", {})
end

function W.onTake(player)
    Core.send(player, "takeCrystal", {})
end

--- The menu. Both options are **shown and greyed** rather than hidden when
--- they cannot be used: a player who is carrying no crystal needs to be told
--- that is the reason, and one who walks up to an empty core should be able
--- to see that taking one is a thing this machine does.
function W.fillMenu(playerNum, context, worldobjects, test)
    local player = U.player(playerNum)
    if not player then return end
    if not U.isInteriorPlayer(player) then return end
    if not TREK.Ship.canUse(player) then return end

    local x, y, z = U.clickedSquare(playerNum, context, player)
    if not W.isCore(x, y, z) then return end
    if test then return ISWorldObjectContextMenu.setTest() end

    local spares = P.crystals()
    local carried = U.try("core.carried", function()
        local inv = player:getInventory()
        local list = inv and inv:getAllTypeRecurse(C.DilithiumType)
        if not list then return 0 end
        local n = 0
        for i = 0, list:size() - 1 do
            local item = list:get(i)
            if item and item:getFullType() == C.DilithiumItem then n = n + 1 end
        end
        return n
    end) or 0

    local function grey(option, why)
        option.notAvailable = true
        option.toolTip = ISWorldObjectContextMenu.addToolTip()
        option.toolTip.description = getText(why)
    end

    local load = context:addOption(
        getText("IGUI_TREK_CoreLoad", tostring(spares)), player, W.onLoad)
    if carried <= 0 then grey(load, "IGUI_TREK_CoreNoCrystalTip") end

    local take = context:addOption(
        getText("IGUI_TREK_CoreTake", tostring(spares)), player, W.onTake)
    if spares <= 0 then grey(take, "IGUI_TREK_CoreEmptyTip") end

    -- Standing too far away is the third reason, and it greys both: the
    -- server measures the range on its own copy of where the player is, so an
    -- option offered from across the cabin is one the ship would refuse.
    if not P.inReachOf(player) then
        grey(load, "IGUI_TREK_CoreFar")
        grey(take, "IGUI_TREK_CoreFar")
    end
    return true
end

Events.OnPreFillWorldObjectContextMenu.Add(W.fillMenu)

---------------------------------------------------------------------------
-- What the server says back
---------------------------------------------------------------------------
-- The ship state arrives by itself; these are the notes that tell the player
-- the thing they asked for happened, with the number they care about in them.
Net.onClient("crystalLoaded", function(args)
    local player = Core.lastAsker or U.player(0)
    U.note(player, getText("IGUI_TREK_CoreLoaded", tostring(args.crystals or "?")),
           150, 220, 255)
    if TREK.ReplicatorUI and TREK.ReplicatorUI.window then
        TREK.ReplicatorUI.window.spares = args.crystals
    end
end)

Net.onClient("crystalTaken", function(args)
    local player = Core.lastAsker or U.player(0)
    U.note(player, getText("IGUI_TREK_CoreTook", tostring(args.crystals or "?")),
           150, 220, 255)
    if TREK.ReplicatorUI and TREK.ReplicatorUI.window then
        TREK.ReplicatorUI.window.spares = args.crystals
    end
end)

return W
