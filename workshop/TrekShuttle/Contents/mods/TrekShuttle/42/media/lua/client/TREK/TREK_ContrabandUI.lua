--[[ Shuttlecraft -- contraband, in front of the player (CONTRABAND.md).

    Three things, all requests:

      * right-click the **Ktarian game**: *Play the Game* (a timed action the
        server completes), and *Offer the Game to...* with a name for every
        player standing within reach -- the episode's spread, one hand to the
        next;
      * right-click a **PADD** while the Game has hold of you: *Run the
        flashing-light program*, the cure Wesley and Data found;
      * `contraState`, the server's summary of this player's record, kept
        where TREK_Contraband.record reads it on a client.

    The drugs need nothing here. Each is a Food item with its own menu word
    (Inject, Take), so vanilla's eating menu offers it and vanilla's eating
    action carries it to the server, where TREK_ContrabandServer takes the
    dose.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_Core"
require "TREK/TREK_Padd"
require "TREK/TREK_Contraband"
require "TREK/TREK_ContrabandActions"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local K = TREK.Contraband
local Core = TREK.Core

local M = {}
TREK.ContrabandUI = M

--- The items in a selection, flattened, each once (TREK_PaddUI's rule: an
--- entry is an item or a stack table whose first item repeats as a header).
local function selectedItems(list)
    local out, seen = {}, {}
    if not list then return out end
    local function take(it)
        if instanceof(it, "InventoryItem") and not seen[it] then
            seen[it] = true
            table.insert(out, it)
        end
    end
    for _, v in ipairs(list) do
        if instanceof(v, "InventoryItem") then
            take(v)
        elseif type(v) == "table" and v.items then
            for _, it in ipairs(v.items) do take(it) end
        end
    end
    return out
end

local function isGame(it)
    return U.try("contra.isGame", function() return it:getFullType() end)
           == C.Contraband.game.item
end

---------------------------------------------------------------------------
-- Playing
---------------------------------------------------------------------------
function M.onPlay(game, player)
    U.try("contra.transfer", function()
        ISInventoryPaneContextMenu.transferIfNeeded(player, game)
    end)
    U.try("contra.queue", function()
        ISTimedActionQueue.add(TREKPlayGame:new(player, game))
    end)
end

--- The players standing near enough to be handed the Game, by username.
function M.nearby(player)
    local out = {}
    local mine = TREK.Ship.usernameOf(player)
    for _, p in ipairs(U.players()) do
        local name = TREK.Ship.usernameOf(p)
        local dead = U.try("contra.dead", function() return p:isDead() end)
        if name and name ~= mine and dead == false
           and math.floor(p:getZ()) == math.floor(player:getZ())
           and U.dist2(p:getX(), p:getY(), player:getX(), player:getY())
               <= C.GameOfferRange * C.GameOfferRange then
            table.insert(out, name)
        end
    end
    table.sort(out)
    return out
end

function M.onOffer(_, player, name)
    Core.send(player, "gameOffer", { to = name })
end

function M.addGame(context, player, game)
    context:addOption(getText("IGUI_TREK_GamePlay"), game, M.onPlay, player)
    local names = M.nearby(player)
    if #names == 0 then return end
    local option = context:addOption(getText("IGUI_TREK_GameOffer"), nil, nil)
    local sub = ISContextMenu:getNew(context)
    context:addSubMenu(option, sub)
    for _, name in ipairs(names) do
        sub:addOption(name, nil, M.onOffer, player, name)
    end
end

---------------------------------------------------------------------------
-- The flashing light
---------------------------------------------------------------------------
function M.onStrobe(_, player)
    Core.send(player, "gameStrobe", {})
end

function M.addStrobe(context, player)
    -- Only for somebody the Game has hold of: every PADD in the world would
    -- otherwise carry a cure for a thing most players never meet.
    if not K.playsTheGame(player) then return end
    context:addOption(getText("IGUI_TREK_Strobe"), nil, M.onStrobe, player)
end

---------------------------------------------------------------------------
-- The menu
---------------------------------------------------------------------------
function M.fillInventoryMenu(playerNum, context, items)
    local player = U.player(playerNum)
    if not player then return end
    local game, padd = nil, nil
    for _, it in ipairs(selectedItems(items)) do
        if isGame(it) then
            game = game or it
        elseif TREK.Padd.isPadd(it) then
            padd = padd or it
        end
    end
    if game then M.addGame(context, player, game) end
    if padd then M.addStrobe(context, player) end
end

Events.OnFillInventoryObjectContextMenu.Add(M.fillInventoryMenu)

---------------------------------------------------------------------------
-- What the server says back
---------------------------------------------------------------------------
local function whom(name)
    for i = 0, 3 do
        local p = U.player(i)
        if p and (name == nil or TREK.Ship.usernameOf(p) == name) then return p end
    end
    return nil
end

--- This player's record, as the server sees it. Kept under the mirror key,
--- which is where TREK_Contraband reads on a client; in single player the
--- record itself is under the other key and this is a harmless copy.
TREK.Net.onClient("contraState", function(args)
    local p = whom(args.who)
    if not p then return end
    local data = U.try("contra.mirror", function() return p:getModData() end)
    if data then data[C.ContrabandMirrorKey] = type(args.state) == "table" and args.state or {} end
end)

return M
