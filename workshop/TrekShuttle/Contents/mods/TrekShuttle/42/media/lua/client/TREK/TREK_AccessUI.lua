--[[ Shuttlecraft -- boarding clearance, as a player meets it (ACCESS.md).

    The pattern enhancer's *Deploy* menu, the notes the server sends as the
    story moves, the lift at a resolved lock, and this client's mirror of its
    own screening. Everything here is presentation or a request: the server
    decides (TREK_AccessServer), and the rules both sides read are TREK_Access.

    Shown and greyed with the reason rather than hidden, as every menu here is.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_Access"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Ac = TREK.Access

local AU = {}
TREK.AccessUI = AU

-- Every refusal's words, written out whole so the asset check can find each
-- key (DEV_GUIDE: *An id assembled from parts is invisible to a static check*).
AU.TIPS = {
    accTrust         = "IGUI_TREK_AccTrustTip",
    accLock          = "IGUI_TREK_AccLockTip",
    accScreen        = "IGUI_TREK_AccScreenTip",
    accLockDone      = "IGUI_TREK_AccLockDone",
    accLockRunning   = "IGUI_TREK_AccLockRunning",
    accNeedThree     = "IGUI_TREK_AccNeedThree",
    accDeployOutside = "IGUI_TREK_AccDeployOutside",
    accDeployRoom    = "IGUI_TREK_AccDeployRoom",
}

--- A refusal's words, with the numbers the trust one needs.
function AU.tip(why)
    if why == "accTrust" then
        return getText("IGUI_TREK_AccTrustTip", tostring(Ac.rescued()), tostring(Ac.rescuesNeeded()))
    end
    return getText(AU.TIPS[why] or "IGUI_TREK_AccLockTip")
end

local function whom(name)
    for i = 0, 3 do
        local p = U.player(i)
        if p and (name == nil or TREK.Ship.usernameOf(p) == name) then return p end
    end
    return nil
end

local function note(key, ...)
    local p = U.player(0)
    if p then U.note(p, getText(key, ...), 150, 210, 255) end
end

local function warn(key, ...)
    local p = U.player(0)
    if p then U.note(p, getText(key, ...), 255, 170, 90) end
end

---------------------------------------------------------------------------
-- The enhancer's menu
---------------------------------------------------------------------------
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

function AU.onDeploy(player)
    Net.send(player, "accessDeploy", {})
end

function AU.fillInventoryMenu(playerNum, context, items)
    local player = U.player(playerNum)
    if not player then return end
    for _, it in ipairs(selected(items)) do
        if it:getFullType() == C.EnhancerItem then
            local opt = context:addOption(getText("IGUI_TREK_AccDeploy",
                                                  tostring(Ac.carried(player, C.EnhancerItem)),
                                                  tostring(C.EnhancersNeeded)),
                                          player, AU.onDeploy)
            local why = Ac.deployRefusal(player)
            if why then
                opt.notAvailable = true
                opt.toolTip = ISWorldObjectContextMenu.addToolTip()
                opt.toolTip.description = AU.tip(why)
            end
            return
        end
    end
end

Events.OnFillInventoryObjectContextMenu.Add(AU.fillInventoryMenu)

---------------------------------------------------------------------------
-- The mirror of this character's screening
---------------------------------------------------------------------------
Net.onClient("accessMine", function(args)
    local p = whom(args.who)
    if not p then return end
    local md = U.try("access.mirror", function() return p:getModData() end)
    if md then md[C.ScreenMirrorKey] = args.screened == true end
    Ac.notify()
end)

--- Asked once the character exists: the server's copy is the one that knows.
function AU.ask(player)
    if player then Net.send(player, "accessAsk", {}) end
end

Events.OnCreatePlayer.Add(function(_, player)
    U.try("access.ask", AU.ask, player)
end)

---------------------------------------------------------------------------
-- What the server says
---------------------------------------------------------------------------
Net.onClient("accessDebrief", function(args)
    if args.distance then
        note("IGUI_TREK_AccDebriefAt", tostring(args.name or getText("IGUI_TREK_AccSomebody")),
             tostring(args.distance), tostring(args.compass or "?"))
    else
        note("IGUI_TREK_AccDebrief", tostring(args.name or getText("IGUI_TREK_AccSomebody")))
    end
end)

Net.onClient("accessScreenTold", function()
    note("IGUI_TREK_AccScreenTold")
end)

Net.onClient("accessRecovered", function(args)
    note("IGUI_TREK_AccRecovered", tostring(args.n or "?"), tostring(args.of or C.EnhancersNeeded))
end)

Net.onClient("accessLockStarted", function(args)
    warn("IGUI_TREK_AccLockStarted", tostring(args.by or "?"), tostring(args.minutes or C.LockMinutes))
end)

Net.onClient("accessLockPaused", function()
    warn("IGUI_TREK_AccLockPaused")
end)

Net.onClient("accessLockBroken", function()
    warn("IGUI_TREK_AccLockBroken")
end)

Net.onClient("accessLocked", function()
    note("IGUI_TREK_AccLocked")
end)

Net.onClient("accessLeftBehind", function(args)
    warn("IGUI_TREK_AccLeftBehind", AU.tip(args.why))
end)

Net.onClient("accessScreened", function()
    note("IGUI_TREK_AccScreened")
    -- And the Doctor says so, if his panel is open: one handler per command,
    -- so his line is set from here.
    if TREK.EMHUI then TREK.EMHUI.line = { key = "IGUI_TREK_EmhScreened" } end
end)

--- The lock is resolved and this player is cleared: straight up.
Net.onClient("accessLift", function()
    local p = U.player(0)
    if p and TREK.AdirondackClient then TREK.AdirondackClient.liftFromLock(p) end
end)

return AU
