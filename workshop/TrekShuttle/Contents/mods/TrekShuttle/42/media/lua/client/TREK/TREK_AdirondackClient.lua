--[[ Shuttlecraft -- the U.S.S. Adirondack, as a player moves about her.

    Three ways to move, all asked of the server first (Core.requestMove, the
    same protocol every beam uses) and all carried out here, because only this
    client can move its own character:

      toAdirondack    from the shuttle's cabin to the Adirondack's pad
      fromAdirondack  from anywhere aboard her back to the shuttle's pad
      turbolift       from the lift car on one deck to the car on another

    Every arrival is the cabin's arrival (TREK_Core): the player is put on the
    spot and held there -- the deck is five storeys up with nothing below --
    until the server says the deck is built and the floor is under them.

    And while anybody is aboard her, the same rule as the cabin: somebody off
    the deck (over a wall, into the black) is put back, never left to fall.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_Core"
require "TREK/TREK_Adirondack"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Ship = TREK.Ship
local Core = TREK.Core
local A = TREK.Adirondack
local L = A.Layout

local AC = {}
TREK.AdirondackClient = AC

-- A beam or lift ride in progress: { player, dir, tries, deck, lx, ly }.
AC.pending = nil
-- Standing on a spot waiting for the deck: { player, x, y, z, deck, tries }.
local arrival = nil
-- deck -> true once the server has said it is built at this layout.
local ready = {}

local LIFT_DELAY = 45
local SETTLE_TICKS = 15
local ARRIVAL_TIMEOUT = 1800

local function busy()
    return AC.pending ~= nil or arrival ~= nil or Core.moveWaiting()
        or (TREK.Transport and TREK.Transport.pending ~= nil) or Core.arriving()
end
AC.busy = busy

local function busyNote(player)
    U.note(player, getText("IGUI_TREK_TransporterBusy"), 255, 170, 90)
end

---------------------------------------------------------------------------
-- Lamps
---------------------------------------------------------------------------
-- Local light sources, one set per client, as the cabin's are. Every fourth
-- square of every room, hung for the deck the player is on; anything the
-- engine has dropped (it drops lampposts outside the loaded area) is hung
-- again on the next look.
local lamps = {}       -- "k,x,y" -> IsoLightSource
local lampCheck = 0

local function lightDeck(k)
    local cell = U.cell()
    if not cell then return end
    lampCheck = lampCheck + 1
    if lampCheck >= 60 then
        lampCheck = 0
        local list = U.try("light.list", function() return cell:getLamppostPositions() end)
        if list then
            for key, light in pairs(lamps) do
                if U.try("light.contains", function() return list:contains(light) end) ~= true then
                    lamps[key] = nil
                end
            end
        end
    end
    local c = C.CabinLight
    for ly = 1, L.H - 1, 4 do
        for lx = 1, L.W - 1, 4 do
            local key = k .. "," .. lx .. "," .. ly
            if not lamps[key] and A.inside(k, lx, ly) then
                local x, y = A.at(k, lx, ly)
                lamps[key] = U.try("light.add", function()
                    return cell:addLamppost(x, y, A.Z, c[1], c[2], c[3], c[4])
                end)
            end
        end
    end
end

---------------------------------------------------------------------------
-- Arriving
---------------------------------------------------------------------------
local function floorAt(x, y, z)
    local sq = U.square(x, y, z, false)
    return sq ~= nil and U.try("floor", function() return sq:getFloor() ~= nil end) == true
end

local function beginArrival(player, x, y, deck)
    arrival = { player = player, x = x, y = y, z = A.Z, deck = deck, tries = 0 }
    Core.hold(player, x, y, A.Z)
    Core.refreshInventoryUI()
    Net.send(player, "adkBoarded", { deck = deck })
end

Net.onClient("adkReady", function(args)
    if args.rev == L.rev and args.deck then ready[args.deck] = true end
end)

local function serviceArrival()
    local job = arrival
    if not job then return end
    local p = job.player
    if not p then arrival = nil return end
    job.tries = job.tries + 1
    Core.hold(p, job.x, job.y, job.z)
    if job.tries % 120 == 0 then Net.send(p, "adkBoarded", { deck = job.deck }) end

    if ready[job.deck] and floorAt(job.x, job.y, job.z) then
        job.settled = (job.settled or 0) + 1
        if job.settled < SETTLE_TICKS then return end
        arrival = nil
        U.teleport(p, job.x, job.y, job.z)
        lightDeck(job.deck)
        local deck = L.decks[job.deck]
        U.note(p, getText("IGUI_TREK_AdkDeck", deck.name, deck.description), 120, 190, 255)
        U.log("materialised on the Adirondack, %s", deck.name)
        return
    end

    if job.tries > ARRIVAL_TIMEOUT then
        arrival = nil
        U.log("the Adirondack's %s never arrived; back to the shuttle", L.decks[job.deck].name)
        U.note(p, getText("IGUI_TREK_AdkLostLock"), 255, 90, 90)
        Core.beginArrival(p, true)
    end
end

---------------------------------------------------------------------------
-- Moves
---------------------------------------------------------------------------
--- From the shuttle's cabin to the Adirondack's transporter pad.
function AC.beamTo(player)
    if not player then return false end
    if not U.isInteriorPlayer(player) then return false, "not aboard" end
    if busy() then busyNote(player) return false, "busy" end
    Core.requestMove(player, "toAdirondack", function(p)
        AC.pending = { player = p, dir = "to", tries = 0 }
        local cost = Core.grantedCost
        U.note(p, cost and getText("IGUI_TREK_Energizing", tostring(math.floor(cost)))
                        or getText("IGUI_TREK_Energising"))
    end)
    return true
end

--- From anywhere aboard her back to the shuttle's pad.
function AC.beamBack(player)
    if not player or not A.onShip(player) then return false end
    if busy() then busyNote(player) return false, "busy" end
    Core.requestMove(player, "fromAdirondack", function(p)
        AC.pending = { player = p, dir = "back", tries = 0 }
        U.note(p, getText("IGUI_TREK_Energising"))
    end)
    return true
end

--- From this deck's lift car to deck `to`'s, at the same spot in the car.
function AC.ride(player, to)
    if not player or not L.decks[to] then return false end
    local inLift, k = A.inLift(player:getX(), player:getY(), player:getZ())
    if not inLift or k == to then return false end
    if busy() then busyNote(player) return false, "busy" end
    local _, lx, ly = A.locate(player:getX(), player:getY(), player:getZ())
    Core.requestMove(player, "turbolift", function(p)
        AC.pending = { player = p, dir = "lift", tries = 0, deck = to, lx = lx, ly = ly }
        U.note(p, getText("IGUI_TREK_TurboliftTo", L.decks[to].name), 120, 190, 255)
    end)
    return true
end

local function servicePending()
    local job = AC.pending
    if not job then return end
    if not job.player then AC.pending = nil return end
    job.tries = job.tries + 1
    local delay = job.dir == "lift" and LIFT_DELAY or C.BeamDelay
    if job.tries < delay then return end
    AC.pending = nil
    local p = job.player

    if job.dir == "to" then
        -- Off the shuttle as far as the shuttle is concerned: the crew check
        -- that keeps a flying ship up counts people in her cabin.
        Ship.playerData(p).aboard = false
        local x, y, _, deck = A.padSpot()
        beginArrival(p, x, y, deck)
        U.log("beaming to the Adirondack")
    elseif job.dir == "back" then
        U.log("beaming back to the shuttle from the Adirondack")
        Core.beginArrival(p, true)
    elseif job.dir == "lift" then
        local x, y = A.at(job.deck, job.lx, job.ly)
        beginArrival(p, x, y, job.deck)
    end
end

Events.OnTick.Add(function()
    U.try("adk.pending", servicePending)
    U.try("adk.arrival", serviceArrival)
end)

---------------------------------------------------------------------------
-- Keeping anyone aboard her on the deck
---------------------------------------------------------------------------
local lastGood = {}    -- username -> { x, y }

local function checkAboard(player)
    if arrival or AC.pending then return end
    local x, y, z = player:getX(), player:getY(), player:getZ()
    -- Located by x and y alone. Somebody who has stepped off the deck is
    -- already a fraction of a level below it by the time this runs, and a
    -- test on their level would let them go at the very moment it matters.
    -- Two levels is the most a fall covers before this catches it.
    if z < A.Z - 2 then return end
    local k, lx, ly = A.locate(x, y)
    if not k then return end
    local who = U.try("username", function() return player:getUsername() end) or "?"

    if A.inside(k, lx, ly) then
        if floorAt(x, y, A.Z) then
            if z < A.Z then Core.hold(player, math.floor(x), math.floor(y), A.Z) end
            lastGood[who] = { x = math.floor(x), y = math.floor(y), deck = k }
            lightDeck(k)
            return
        end
        -- Loaded straight onto a deck that has not streamed in, or has not
        -- been built by this layout: stand still while the server sees to it.
        beginArrival(player, math.floor(x), math.floor(y), k)
        return
    end

    -- Outside her walls: over one, or somewhere between the decks.
    local back = lastGood[who]
    if back and back.deck == k then
        Core.hold(player, back.x, back.y, A.Z)
    else
        local lxs, lys = A.liftSpot(k)
        beginArrival(player, lxs, lys, k)
    end
    U.note(player, getText("IGUI_TREK_NoWayOut"), 255, 170, 90)
end

Events.OnPlayerUpdate.Add(function(player)
    if not player or not player:isLocalPlayer() or player:isDead() then return end
    U.try("adk.checkAboard", checkAboard, player)
end)

---------------------------------------------------------------------------
-- Menus
---------------------------------------------------------------------------
function AC.onBeamTo(_, player) AC.beamTo(player) end
function AC.onBeamBack(_, player) AC.beamBack(player) end
function AC.onRide(_, player, k) AC.ride(player, k) end

--- The right-click menu anywhere aboard her. Replaces the shuttle's ground
--- menu there: calling the shuttle down onto a deck five storeys up in the
--- void is not a thing to offer.
function AC.menu(context, player, worldobjects, test)
    if test then return ISWorldObjectContextMenu.setTest() end
    local k, lx, ly = A.locate(player:getX(), player:getY(), player:getZ())
    local deck = k and L.decks[k]
    local title = getText("IGUI_TREK_Adirondack")
    if deck then title = title .. " - " .. deck.name end
    local sub = context:addOption(title, worldobjects, nil)
    local menu = ISContextMenu:getNew(context)
    context:addSubMenu(sub, menu)

    local inLift = A.inLift(player:getX(), player:getY(), player:getZ())
    if inLift then
        local liftSub = menu:addOption(getText("IGUI_TREK_Turbolift"), worldobjects, nil)
        local lift = ISContextMenu:getNew(menu)
        menu:addSubMenu(liftSub, lift)
        for j, d in ipairs(L.decks) do
            local opt = lift:addOption(getText("IGUI_TREK_AdkDeck", d.name, d.description),
                                       worldobjects, AC.onRide, player, j)
            if j == k then opt.notAvailable = true end
        end
    else
        local hint = menu:addOption(getText("IGUI_TREK_TurboliftHint"), worldobjects, nil)
        hint.notAvailable = true
    end
    menu:addOption(getText("IGUI_TREK_BeamToShuttle"), worldobjects, AC.onBeamBack, player)
    return true
end

return AC
