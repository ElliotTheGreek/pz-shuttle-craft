--[[ Shuttlecraft -- the shoulder lamp's attached location (ITEMS.md).

    The lamp is a flashlight the engine already knows how to light: an
    attached item is walked by IsoGameCharacter.getActiveLightItems exactly as
    a held one is (bci 18-50), and vanilla's inventory menu offers Turn On for
    it. What the engine does not have is a shoulder, and this file and
    client/TREK/TREK_ShoulderLampSlot.lua give it one:

      * here, in every process, the **location** the slot puts the lamp at,
        on the Human group of AttachedLocations. It is the mod's own name on
        vanilla's own body attachment (C.ShoulderAttachment), so no vanilla
        model is edited, and a walkie on webbing keeps its own location;
      * there, on clients, the **hotbar slot** every uniform provides.

    getOrCreateLocation is idempotent, so the order this loads in against
    vanilla's shared/NPCs/AttachedLocations.lua does not matter.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local SL = {}
TREK.ShoulderLamp = SL

--- Registers the location. Returns true when the group took it.
function SL.registerLocation()
    return U.try("shoulderLamp.location", function()
        local group = AttachedLocations.getGroup("Human")
        group:getOrCreateLocation(C.ShoulderLocation):setAttachmentName(C.ShoulderAttachment)
        return true
    end) == true
end

if not SL.registerLocation() then
    U.log("WARN shoulder lamp: the %s location could not be registered", C.ShoulderLocation)
end

return SL
