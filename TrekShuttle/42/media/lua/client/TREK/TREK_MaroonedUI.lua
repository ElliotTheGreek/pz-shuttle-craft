--[[ Shuttlecraft -- marooned: the player's side (MAROONED.md).

    Right-click an annotated map in your inventory:

      Read the annotated map      the server puts where she came down on the
                                  ship's contacts; this client says how far
                                  and which way, and opens the map on the
                                  mark when there is light to read one by

    And the two things the server says: what a map read, and the moment a
    player is first aboard her and has a combadge. What the lack of one hides
    is not here: the ground menu is TREK_Menu's, the dot on the map
    TREK_MapView's, and the refusals are the server's own.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_Marooned"
require "TREK/TREK_MapContacts"
require "TREK/TREK_MapView"

TREK = TREK or {}
local U = TREK.Util
local Net = TREK.Net
local Ship = TREK.Ship
local MR = TREK.Marooned

local MU = {}
TREK.MaroonedUI = MU

-- Whoever last read a map on this machine: the reply is theirs.
local reader = nil

--- The items in a context-menu selection, flattened: an entry is either an
--- InventoryItem or a stack with its own `items` (DEV_GUIDE, failure
--- signatures: code that handles one shape does nothing for the other).
local function selected(items)
    local out = {}
    for _, v in ipairs(items or {}) do
        if instanceof(v, "InventoryItem") then
            table.insert(out, v)
        elseif type(v) == "table" and v.items then
            for _, it in ipairs(v.items) do
                if instanceof(it, "InventoryItem") then table.insert(out, it) end
            end
        end
    end
    return out
end

function MU.read(player, item)
    reader = player
    Net.send(player, "readShuttleMap", { id = item:getID() })
end

function MU.fillInventoryMenu(playerNum, context, items)
    local player = U.player(playerNum)
    if not player then return end
    for _, it in ipairs(selected(items)) do
        if MR.isMap(it) then
            context:addOption(getText("IGUI_TREK_MaroonRead"), player, MU.read, it)
            -- One map's option is enough: they all say the same thing.
            return
        end
    end
end

Events.OnFillInventoryObjectContextMenu.Add(MU.fillInventoryMenu)

---------------------------------------------------------------------------
-- What the server says
---------------------------------------------------------------------------
Net.onClient("maroonMap", function(args)
    local player = reader or U.player(0)
    if not player then return end
    local site = MR.siteById(args.site)
    if args.stale or not site or not args.x or not args.y then
        U.note(player, getText("IGUI_TREK_MaroonMapStale"), 255, 170, 90)
        return
    end
    -- Measured from where they are on the map, which aboard anything is
    -- where they left it (Ship.worldOrigin).
    local px, py = Ship.worldOrigin(player)
    local tiles, bearing = "?", ""
    if px and py then
        tiles = tostring(math.floor(math.sqrt(U.dist2(px, py, args.x, args.y))))
        bearing = U.compass(px, py, args.x, args.y)
    end
    U.note(player, getText("IGUI_TREK_MaroonMap", getText(site.label), tiles, bearing),
           150, 220, 255)
    -- The ground round the mark is uncovered by TREK_MapContacts, as for any
    -- contact, on every client the mark is published to.
    TREK.MapView.showAt(player, args.x, args.y)
end)

Net.onClient("maroonLinked", function(args)
    local player = U.player(0)
    if not player then return end
    U.note(player, getText(args.first and "IGUI_TREK_MaroonFound" or "IGUI_TREK_MaroonLinked"),
           90, 255, 120)
end)

return MU
