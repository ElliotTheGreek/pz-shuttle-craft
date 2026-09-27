--[[ Shuttlecraft -- the phaser.

    A phaser never runs out. It is an ordinary build 42 firearm in every other
    respect -- you aim it, you fire it, it does damage and makes a noise --
    and this file is the one thing that makes it a phaser: a slow tick that
    puts the charge, the chambered round and the condition back.

    Three notes on why it is built this way.

    **The ammo type is 9mm and that is deliberate.** A phaser ought to have
    its own power cell, and it cannot: `AmmoType = base:bullets_9mm` resolves
    through AmmoType.registerBase in Java, and there is no script syntax
    anywhere in the build that lets a mod add one -- grep the whole of
    media/scripts for `bullets_9mm` and it appears only as the value of
    AmmoType lines, never as a definition. A made-up id would resolve to
    nothing and the weapon would refuse to fire, which is exactly the sort of
    silent failure that costs an evening. So the phaser nominally chambers
    9mm, and because the charge is topped up faster than anyone can spend it,
    nothing is ever drawn from the player's own ammunition.

    **The top-up is a sweep of the inventory, not a hook on firing.** There is
    no reliable "the player shot" event to hang this on, and a phaser in a bag
    should be as full as one in your hand when you draw it. Sweeping every
    C.PhaserInterval ticks is cheap -- one recursive type lookup and a handful
    of setters -- and covers both.

    **Every engine call is batched.** A wrong method name in a per-item loop
    throws out of Java and the engine dumps a stack trace per call; U.batch
    stops after the first failure so one bad name costs one warning instead of
    a frozen game.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_PhaserCut"
require "TREK/TREK_PhaserCharge"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local P = {}
TREK.Phaser = P
local PCh = TREK.PhaserCharge

---------------------------------------------------------------------------
-- Finding the phasers on a player
---------------------------------------------------------------------------
--- Every energy weapon on the player, and charging them: shared with the
--- server, which is the copy that counts in multiplayer (TREK_PhaserCharge).
P.carriedBy = PCh.carriedBy
P.charge = PCh.charge
P.sweep = PCh.sweep

--- Only the ones that cut: the phaser and the phaser rifle. A disruptor is
--- a weapon and nothing more (C.EnergyWeapons, `cuts`).
function P.cuttersBy(player)
    local out = {}
    for _, item in ipairs(P.carriedBy(player)) do
        local t = U.try("phaser.cutType", function() return item:getFullType() end)
        local spec = C.energyWeapon(t)
        if spec and spec.cuts then table.insert(out, item) end
    end
    return out
end

---------------------------------------------------------------------------
-- When to sweep
---------------------------------------------------------------------------
local tick = 0

-- Only this client's own characters: OnPlayerUpdate also runs for the other
-- players a client can see, and their inventories are not ours to change.
--
-- **On a server this copy is not the one that counts.** The hit anti-cheat
-- reads the server's copy, and a charge made only here never reached it: it
-- ran dry while this one kept firing, and a player was kicked for "not
-- enough ammo" (1.10.1). The server charges its own and sends it here
-- (TREK_PhaserServer); this sweep still keeps the copy the player fires
-- from full between the server's passes.
Events.OnPlayerUpdate.Add(function(player)
    if not player or not player:isLocalPlayer() then return end
    tick = tick + 1
    if tick < C.PhaserInterval then return end
    tick = 0
    P.sweep(player)
end)

---------------------------------------------------------------------------
-- Cutting: the right-click (PHASERS.md 7)
---------------------------------------------------------------------------
local PC = TREK.PhaserCut

--- Every tree and door the click could mean, once each: the objects the
--- engine handed over and everything else on their squares, because a
--- right-click on a trunk or a door frame often names the floor instead.
function P.cutTargets(worldobjects)
    local found, seen = {}, {}
    local function consider(o)
        if not o or seen[o] then return end
        seen[o] = true
        local kind = PC.kindOf(o)
        if kind then table.insert(found, { obj = o, kind = kind }) end
    end
    for _, o in ipairs(worldobjects or {}) do
        consider(o)
        local sq = U.try("phaser.menuSq", function() return o:getSquare() end)
        local objects = sq and U.try("phaser.menuObjs", function() return sq:getObjects() end)
        local n = objects and (U.try("phaser.menuN", function() return objects:size() end) or 0) or 0
        for i = 0, n - 1 do consider(objects:get(i)) end
    end
    return found
end

local LABELS = { tree = "IGUI_TREK_PhaserCutTree", door = "IGUI_TREK_PhaserCutDoor" }

--- The option, on any tree or door, for anybody carrying a phaser -- in a
--- hand or not; choosing it draws the phaser the way vanilla's chop draws
--- the axe.
function P.fillWorldMenu(playerNum, context, worldobjects, test)
    local player = U.player(playerNum)
    if not player then return end
    if not PC.inHand(player) and #P.cuttersBy(player) == 0 then return end
    local targets = P.cutTargets(worldobjects)
    if #targets == 0 then return end
    if test then return ISWorldObjectContextMenu.setTest() end

    for _, t in ipairs(targets) do
        local option = context:addOption(getText(LABELS[t.kind]), worldobjects,
                                         P.onCut, player, t.obj, t.kind)
        -- Refused for a reason that walking and drawing cannot fix: say so in
        -- the menu rather than hiding the option, the tricorder's padlock
        -- rule. Distance and an empty hand are fixed by choosing it.
        local why = nil
        if not PC.allowed(t.kind) then
            why = "IGUI_TREK_PhaserCutOff"
        elseif t.kind == "door" then
            local sq = U.try("phaser.menuDoorSq", function() return t.obj:getSquare() end)
            local name = U.try("phaser.menuName", function() return player:getUsername() end)
            if sq and U.try("phaser.menuSafe", function()
                return SafeHouse.isSafeHouse(sq, name, true)
            end) then
                why = "IGUI_TREK_PhaserSafehouse"
            end
        end
        if why then
            option.notAvailable = true
            option.toolTip = ISWorldObjectContextMenu.addToolTip()
            option.toolTip.description = getText(why)
        end
    end
end

--- Draw the phaser, close the distance if there is any to close, and cut.
function P.onCut(_, player, obj, kind)
    local sq = U.try("phaser.cutSq", function() return obj:getSquare() end)
    if not sq then return end
    if not PC.inHand(player) then
        local item = P.cuttersBy(player)[1]
        if not item then return end
        ISWorldObjectContextMenu.equip(player, player:getPrimaryHandItem(), item,
                                       true, false)
    end
    local px = U.try("phaser.cutPx", function() return player:getX() end) or 0
    local py = U.try("phaser.cutPy", function() return player:getY() end) or 0
    local dx, dy = px - (sq:getX() + 0.5), py - (sq:getY() + 0.5)
    if math.sqrt(dx * dx + dy * dy) > C.PhaserCutRange then
        if not luautils.walkAdj(player, sq, true) then return end
    end
    ISTimedActionQueue.add(TREKPhaserCut:new(player, sq:getX(), sq:getY(),
                                             sq:getZ(), kind))
end

Events.OnFillWorldObjectContextMenu.Add(P.fillWorldMenu)

--- Exposed for the debug console: TREK_Phaser()
---
--- Says how many phasers the sweep can see on you and how many it had to top
--- up. Zero found while one is in your hands means the inventory lookup is
--- wrong, which is the one failure here that would otherwise be silent.
function TREK_Phaser()
    local player = U.player(0)
    if not player then return 0 end
    local charged, found = P.sweep(player)
    U.log("phaser: %d found on you, %d recharged", found, charged)
    return found
end

return P
