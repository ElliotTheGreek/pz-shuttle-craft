--[[ Shuttlecraft -- the Shoulder slot on the hotbar (ITEMS.md).

    Every Starfleet uniform provides `TrekShoulder` (AttachmentsProvided in
    trekshuttle.txt), and ISHotbar:refresh looks each provided name up in
    ISHotbarAttachDefinition by its `type`. This is that entry: one kind of
    item fits it, the shoulder lamp, and it puts the lamp at the location
    shared/TREK/TREK_ShoulderLamp.lua registers.

    The label is `IGUI_HotbarAttachment_TrekShoulder` in IG_UI.json, which is
    the key ISHotbar asks for before it falls back to `name`. The animation is
    the right webbing slot's, the reach to the same side of the chest.

    Client only, as vanilla's own definitions are: the attach is a timed
    action that names the location, and the table is never read on a server.
]]

if isServer() then return end

require "Hotbar/ISHotbarAttachDefinition"
require "TREK/TREK_Config"

local C = TREK.Config

local slot = {
    type = C.ShoulderSlot,
    name = "Shoulder",
    animset = "holster right",
    attachments = {
        [C.ShoulderLampKind] = C.ShoulderLocation,
    },
}

-- Once, whatever reloads this file: a second entry of the same type would be
-- a second Shoulder slot on the hotbar of every uniform.
local present = false
for _, def in ipairs(ISHotbarAttachDefinition) do
    if def.type == slot.type then present = true end
end
if not present then
    table.insert(ISHotbarAttachDefinition, slot)
end
