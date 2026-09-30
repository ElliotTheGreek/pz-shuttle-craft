--[[ Shuttlecraft -- the perimeter phaser sentry: the player's side (SENTRY.md).

    Right-click a sentry in your inventory:

      Set down sentry (N shots)       on the square in front of you; it arms
                                      a few seconds later
      Recharge sentry (250 units)     at a warp core, from its power

    Both ask; TREK_SentryServer decides. Picking a set-down sentry up again
    is vanilla's own, as for anything lying on the ground. Every client draws
    the server's `sentryShot` as a phaser bolt from the sentry to what it hit
    (TREK_PhaserFX), and plays the shot to anybody near enough to hear it.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Sentry"
require "TREK/TREK_PhaserFX"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local SN = TREK.Sentry

local SU = {}
TREK.SentryUI = SU

-- Anybody this close to a sentry hears it fire.
SU.HEAR = 25

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

local function grey(opt, key)
    opt.notAvailable = true
    opt.toolTip = ISWorldObjectContextMenu.addToolTip()
    opt.toolTip.description = getText(key)
end

--- Why this player cannot set a sentry down where they face, or nil.
function SU.refusal(player)
    local x, y, z = SN.spotInFront(player)
    if not x then return "IGUI_TREK_SentryBlocked" end
    local why = SN.squareRefusal(U.square(x, y, z, false))
    if why == "sentryAboard" then return "IGUI_TREK_SentryAboard" end
    if why then return "IGUI_TREK_SentryBlocked" end
    return nil
end

function SU.deploy(player, item)
    Net.send(player, "deploySentry", { id = item:getID() })
end

function SU.recharge(player, item)
    Net.send(player, "rechargeSentry", { id = item:getID() })
end

function SU.fillInventoryMenu(playerNum, context, items)
    local player = U.player(playerNum)
    if not player then return end
    for _, it in ipairs(selected(items)) do
        if SN.isSentry(it) then
            local left = SN.charges(it)
            local opt = context:addOption(getText("IGUI_TREK_SentryDeploy", tostring(left), tostring(C.SentryCharges)),
                                          player, SU.deploy, it)
            local why = SU.refusal(player)
            if why then grey(opt, why) end
            if left < C.SentryCharges then
                local r = context:addOption(getText("IGUI_TREK_SentryRecharge", tostring(C.SentryRechargeCost)),
                                            player, SU.recharge, it)
                if not (TREK.Power and TREK.Power.inReachOf(player)) then grey(r, "IGUI_TREK_SentryNoCoreTip") end
            end
            -- One sentry's options are enough: a stack of them are the same
            -- thing, and the first is the one set down.
            return
        end
    end
end

Events.OnFillInventoryObjectContextMenu.Add(SU.fillInventoryMenu)

---------------------------------------------------------------------------
-- What the server says
---------------------------------------------------------------------------
Net.onClient("sentryShot", function(args)
    TREK.PhaserFX.boltAt(args)
    local p = U.player(0)
    if not p then return end
    local px = U.try("sentry.hx", function() return p:getX() end)
    local py = U.try("sentry.hy", function() return p:getY() end)
    if px and U.dist2(px, py, args.x, args.y) <= SU.HEAR * SU.HEAR then
        U.try("sentry.sound", function() p:playSoundLocal("TREK_PhaserPulse") end)
    end
end)

Net.onClient("sentryDeployed", function(args)
    local p = U.player(0)
    if p then
        U.note(p, getText("IGUI_TREK_SentryDeployed", tostring(args.secs or 3), tostring(args.charges or "?")),
               150, 220, 255)
    end
end)

Net.onClient("sentryEmpty", function()
    local p = U.player(0)
    if p then U.note(p, getText("IGUI_TREK_SentryEmpty"), 255, 170, 90) end
end)

Net.onClient("sentryRecharged", function(args)
    local p = U.player(0)
    if p then U.note(p, getText("IGUI_TREK_SentryRecharged", tostring(args.charges or C.SentryCharges)), 150, 220, 255) end
end)

return SU
