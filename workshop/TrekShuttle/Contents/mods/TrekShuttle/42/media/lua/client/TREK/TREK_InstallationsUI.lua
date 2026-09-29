--[[ Shuttlecraft -- installing and dismantling, as a player meets it.

    INSTALLATIONS.md. A kit's own right-click, *Install here*, puts its
    machine on the square in front of the player (the core on the two by two
    in front of them); an installed machine's right-click offers *Dismantle*.
    Both ask the server, which checks everything again on its own copy.

    Shown and greyed with the reason rather than hidden, as every menu here
    is: aboard a ship that has its own machines, or facing a square with
    something on it, the player is told why.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Installations"

TREK = TREK or {}
local U = TREK.Util
local Net = TREK.Net
local IN = TREK.Installations

local IU = {}
TREK.InstallationsUI = IU

local KIND_OF = {}
for kind, id in pairs(IN.Kits) do KIND_OF[id] = kind end

IU.NAME = { warp_core = "IGUI_TREK_InstCore", replicator = "IGUI_TREK_InstReplicator",
            emh_station = "IGUI_TREK_InstEMH" }

--- The square a kit would go on: the one the player faces. The core's two
--- by two runs away from them, so it never covers where they stand.
function IU.target(player, kind)
    local sq = U.try("iu.sq", function() return player:getCurrentSquare() end)
    local dir = U.try("iu.dir", function() return player:getDir() end)
    if not sq or not dir then return nil end
    local dx = U.try("iu.dx", function() return dir:dx() end) or 0
    local dy = U.try("iu.dy", function() return dir:dy() end) or 0
    if dx == 0 and dy == 0 then dy = 1 end
    local x, y, z = sq:getX() + dx, sq:getY() + dy, sq:getZ()
    if kind == "warp_core" then
        if dx < 0 then x = x - 1 end
        if dy < 0 then y = y - 1 end
    end
    return x, y, z
end

--- Why the kit cannot go down there, as far as this client can see, or nil.
function IU.refusal(player, kind)
    local px, py, pz = player:getX(), player:getY(), player:getZ()
    if IN.isOurs(px, py, pz) then return "IGUI_TREK_InstOursTip" end
    local x, y, z = IU.target(player, kind)
    if not x then return "IGUI_TREK_InstBlockedTip" end
    for _, t in ipairs(IN.Sprites[kind].W) do
        local sq = U.square(x + t[1], y + t[2], z, false)
        if not sq or not U.try("iu.floor", function() return sq:getFloor() end)
           or U.try("iu.free", function() return sq:isFree(false) end) ~= true then
            return "IGUI_TREK_InstBlockedTip"
        end
    end
    return nil
end

function IU.install(player, kind)
    local x, y, z = IU.target(player, kind)
    if not x then return false end
    Net.send(player, "installMachine", { kind = kind, x = x, y = y, z = z })
    return true
end

function IU.onInstall(player, kind) IU.install(player, kind) end

--- The items in a context-menu selection, flattened: an entry is either an
--- InventoryItem or a stack with its own `items`.
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

function IU.fillInventoryMenu(playerNum, context, items)
    local player = U.player(playerNum)
    if not player then return end
    local seen = {}
    for _, it in ipairs(selected(items)) do
        local kind = KIND_OF[it:getFullType()]
        if kind and not seen[kind] then
            seen[kind] = true
            local opt = context:addOption(getText("IGUI_TREK_InstInstall", getText(IU.NAME[kind])),
                                          player, IU.onInstall, kind)
            local why = IU.refusal(player, kind)
            if why then
                opt.notAvailable = true
                opt.toolTip = ISWorldObjectContextMenu.addToolTip()
                opt.toolTip.description = getText(why)
            end
        end
    end
end

Events.OnFillInventoryObjectContextMenu.Add(IU.fillInventoryMenu)

function IU.onDismantle(_, player, id)
    Net.send(player, "dismantleMachine", { id = id })
end

--- An installed machine's right-click: Dismantle, and when it has no core
--- to run on, a word saying so.
function IU.fillWorldMenu(playerNum, context, worldobjects, test)
    local player = U.player(playerNum)
    if not player then return end
    local x, y, z = U.clickedSquare(playerNum, context, player)
    if not x then return end
    local id, m = IN.clickedMachine(nil, x, y, z, 1)
    if not id then return end
    -- A raid's machines are lent for the fight and go with it: nothing to
    -- dismantle (the server refuses it too, instRaid).
    if m.raid then return end
    if test then return ISWorldObjectContextMenu.setTest() end
    local opt = context:addOption(getText("IGUI_TREK_InstDismantle", getText(IU.NAME[m.kind])),
                                  worldobjects, IU.onDismantle, player, id)
    if not IN.machineBeside(player, x, y, z) then
        opt.notAvailable = true
        opt.toolTip = ISWorldObjectContextMenu.addToolTip()
        opt.toolTip.description = getText("IGUI_TREK_InstFarTip")
    end
    if m.kind ~= "warp_core" and not IN.coreFor(m.x, m.y, m.z) then
        local note = context:addOption(getText("IGUI_TREK_InstNoCore"), worldobjects, nil)
        note.notAvailable = true
    end
    return true
end

Events.OnPreFillWorldObjectContextMenu.Add(IU.fillWorldMenu)

Net.onClient("machineInstalled", function(args)
    local player = U.player(0)
    if not player then return end
    local text = getText("IGUI_TREK_InstDone", getText(IU.NAME[args.kind] or "IGUI_TREK_InstCore"))
    if args.kind ~= "warp_core" and not args.core then
        text = text .. " " .. getText("IGUI_TREK_InstNoCore")
    end
    U.note(player, text, 120, 190, 255)
end)

Net.onClient("machineDismantled", function(args)
    local player = U.player(0)
    if not player then return end
    U.note(player, getText("IGUI_TREK_InstTaken", getText(IU.NAME[args.kind] or "IGUI_TREK_InstCore"),
                           tostring(args.crystals or 0)), 120, 190, 255)
end)

return IU
