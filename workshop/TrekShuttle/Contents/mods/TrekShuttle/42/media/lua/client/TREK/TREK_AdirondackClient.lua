--[[ Shuttlecraft -- the U.S.S. Adirondack, as a player moves about her.

    Three ways to move, all asked of the server first (Core.requestMove, the
    same protocol every beam uses) and all carried out here, because only this
    client can move its own character:

      toAdirondack    from the shuttle's cabin to the Adirondack's pad
      fromAdirondack  from anywhere aboard her back to the shuttle's pad
      turbolift       from the lift car on one deck to the car on another
      stationDown     from the panel in the Muldraugh stockroom to the field
                      station's first sublevel (FIELD_STATION.md 3)
      stationUp       from a field station lift car back to the stockroom

    **The field station's sublevels are decks of the same layout**, marked
    `site = "fst"`: everything here works on them unchanged, and the site only
    decides what the lift lists, the menu's title and the way out.

    Every arrival is the cabin's arrival (TREK_Core): the player is put on the
    spot and held there -- the deck is five storeys up with nothing below --
    until the server says the deck is built and the floor is under them.

    And while anybody is aboard her, the same rule as the cabin: somebody off
    the deck (over a wall, into the black) is put back, never left to fall.

    **The Jefferies tubes are walked, not ridden** (JEFFERIES.md): nobody is
    moved. In a tube's crawlway the player's own character crawls -- vanilla's
    Bob_Crawl, which no vanilla state plays, through the mod's AnimSets node
    keyed on the TrekCrawl variable -- held to a sneak and never a run; out of
    it, their own sneak is given back as it was.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_Core"
require "TREK/TREK_Adirondack"
require "TREK/TREK_FieldStation"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Ship = TREK.Ship
local Core = TREK.Core
local A = TREK.Adirondack
local FS = TREK.FieldStation
local L = A.Layout

local AC = {}
TREK.AdirondackClient = AC

-- A beam or lift ride in progress: { player, dir, tries, deck, lx, ly }.
AC.pending = nil
-- Standing on a spot waiting for the deck: { player, x, y, z, deck, tries }.
local arrival = nil
-- Back up in the stockroom, waiting for Kentucky to stream in:
-- { player, x, y, z, tries, settled }.
local surfacing = nil
-- deck -> true once the server has said it is built at this layout.
local ready = {}

local LIFT_DELAY = 45
local SETTLE_TICKS = 15
local ARRIVAL_TIMEOUT = 1800

local function busy()
    return AC.pending ~= nil or arrival ~= nil or surfacing ~= nil or Core.moveWaiting()
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

--- Where deck k's lamps hang, worked out once: { {lx, ly}, ... }.
---
--- **Room by room, not a grid.** Lamps used to go every fourth square across
--- the deck, wherever that landed in a room; a room the grid missed had
--- none, its walls kept its neighbours' light out, and at night it was dark
--- (1.10.1, the author: "always on and bright"). Each room -- a connected
--- run of squares of one room type, since every cabin shares its type --
--- gets a lamp at its middle, then one on any square still further than
--- C.DeckLampReach from a lamp of its own.
local lampSpots = {}
function AC.lampSpots(k)
    if lampSpots[k] then return lampSpots[k] end
    local deck = L.decks[k]
    local out = {}
    if not deck then return out end
    local seen = {}
    local function rid(lx, ly)
        if lx < 0 or ly < 0 or lx >= L.W or ly >= L.H then return nil end
        local r = deck.grid[ly + 1][lx + 1]
        return (r and r > 0) and r or nil
    end
    local reach = C.DeckLampReach
    for sy = 0, L.H - 1 do
        for sx = 0, L.W - 1 do
            local r = rid(sx, sy)
            if r and not seen[sx .. "," .. sy] then
                -- One room: flood its squares.
                local squares, stack = {}, { { sx, sy } }
                seen[sx .. "," .. sy] = true
                local cx, cy = 0, 0
                while #stack > 0 do
                    local p = table.remove(stack)
                    table.insert(squares, p)
                    cx, cy = cx + p[1], cy + p[2]
                    for _, d in ipairs({ { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } }) do
                        local nx, ny = p[1] + d[1], p[2] + d[2]
                        if rid(nx, ny) == r and not seen[nx .. "," .. ny] then
                            seen[nx .. "," .. ny] = true
                            table.insert(stack, { nx, ny })
                        end
                    end
                end
                cx, cy = cx / #squares, cy / #squares
                table.sort(squares, function(a, b)
                    if a[2] ~= b[2] then return a[2] < b[2] end
                    return a[1] < b[1]
                end)
                -- The middle first: the room's own square nearest its centre.
                local best, bd = nil, nil
                for _, p in ipairs(squares) do
                    local d = (p[1] - cx) ^ 2 + (p[2] - cy) ^ 2
                    if not bd or d < bd then best, bd = p, d end
                end
                local mine = { best }
                -- Then any square still out of reach gets one reach further in:
                -- the square at `reach` from it towards the middle, if that
                -- is in the room, else itself.
                local function covered(p)
                    for _, l in ipairs(mine) do
                        if math.abs(l[1] - p[1]) <= reach and math.abs(l[2] - p[2]) <= reach then
                            return true
                        end
                    end
                    return false
                end
                for _, p in ipairs(squares) do
                    if not covered(p) then
                        local dx = (cx > p[1]) and 1 or ((cx < p[1]) and -1 or 0)
                        local dy = (cy > p[2]) and 1 or ((cy < p[2]) and -1 or 0)
                        local q = { p[1] + dx * math.min(reach, math.abs(cx - p[1])),
                                    p[2] + dy * math.min(reach, math.abs(cy - p[2])) }
                        q = { math.floor(q[1] + 0.5), math.floor(q[2] + 0.5) }
                        if rid(q[1], q[2]) ~= r then q = p end
                        table.insert(mine, q)
                    end
                end
                for _, l in ipairs(mine) do table.insert(out, l) end
            end
        end
    end
    lampSpots[k] = out
    return out
end

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
    local c = C.DeckLight
    -- And the tubes that leave or reach this deck: a lamp every few squares
    -- of crawlway and one over each hideout's table.
    for _, tube in ipairs(L.tubes or {}) do
        if tube.from == k or tube.to == k then
            local spots = {}
            for i = 1, #tube.path, C.TubeLampEvery do table.insert(spots, tube.path[i]) end
            -- Over the table: the middle of the hideout's third row.
            if tube.hideout then table.insert(spots, tube.hideout[13]) end
            for _, p in ipairs(spots) do
                local key = "t" .. tube.from .. "," .. p[1] .. "," .. p[2]
                if not lamps[key] then
                    local x, y = A.at(tube.from, p[1], p[2])
                    lamps[key] = U.try("light.add", function()
                        return cell:addLamppost(x, y, A.Z, c[1], c[2], c[3], c[4])
                    end)
                end
            end
        end
    end
    for _, p in ipairs(AC.lampSpots(k)) do
        local key = k .. "," .. p[1] .. "," .. p[2]
        if not lamps[key] then
            local x, y = A.at(k, p[1], p[2])
            lamps[key] = U.try("light.add", function()
                return cell:addLamppost(x, y, A.Z, c[1], c[2], c[3], c[4])
            end)
        end
    end
end
AC.lightDeck = lightDeck

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
        U.log("arrived on the %s, %s", A.siteOf(job.deck) == "fst" and "field station" or "Adirondack",
              deck.name)
        return
    end

    if job.tries > ARRIVAL_TIMEOUT then
        arrival = nil
        if A.siteOf(job.deck) == "fst" then
            -- The station never came: back up to the stockroom, not to a
            -- shuttle this player may never have been aboard.
            U.log("the field station's %s never arrived; back to the stockroom", L.decks[job.deck].name)
            U.note(p, getText("IGUI_TREK_StationLost"), 255, 90, 90)
            AC.surface(p)
            return
        end
        U.log("the Adirondack's %s never arrived; back to the shuttle", L.decks[job.deck].name)
        U.note(p, getText("IGUI_TREK_AdkLostLock"), 255, 90, 90)
        Core.beginArrival(p, true)
    end
end
AC.beginArrival = beginArrival

--- Puts a player on the stockroom floor in front of the panel and holds them
--- there until the ground is loaded under them. Kentucky is a real map, so
--- the only wait is for its chunk to stream in.
function AC.surface(player)
    local x, y, z = FS.standSpot()
    surfacing = { player = player, x = math.floor(x), y = math.floor(y), z = z, tries = 0 }
    U.teleport(player, x, y, z)
    Core.hold(player, math.floor(x), math.floor(y), z)
    Core.refreshInventoryUI()
end

local function serviceSurfacing()
    local job = surfacing
    if not job then return end
    local p = job.player
    if not p then surfacing = nil return end
    job.tries = job.tries + 1
    Core.hold(p, job.x, job.y, job.z)
    if floorAt(job.x, job.y, job.z) then
        job.settled = (job.settled or 0) + 1
        if job.settled < SETTLE_TICKS then return end
    elseif job.tries < ARRIVAL_TIMEOUT then
        return
    end
    surfacing = nil
    U.log("up from the field station, in the stockroom at %d,%d", job.x, job.y)
    U.note(p, getText("IGUI_TREK_StationUpArrived"), 120, 190, 255)
end

function AC.surfacing() return surfacing end

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
    if not player or not A.onAdirondack(player) then return false end
    if busy() then busyNote(player) return false, "busy" end
    Core.requestMove(player, "fromAdirondack", function(p)
        AC.pending = { player = p, dir = "back", tries = 0 }
        U.note(p, getText("IGUI_TREK_Energising"))
    end)
    return true
end

--- From this deck's lift car to deck `to`'s, at the same spot in the car.
--- Only within one site: the Adirondack's lift goes to her decks, the field
--- station's to its sublevels.
function AC.ride(player, to)
    if not player or not L.decks[to] then return false end
    local inLift, k = A.inLift(player:getX(), player:getY(), player:getZ())
    if not inLift or k == to or A.siteOf(k) ~= A.siteOf(to) then return false end
    if busy() then busyNote(player) return false, "busy" end
    local _, lx, ly = A.locate(player:getX(), player:getY(), player:getZ())
    Core.requestMove(player, "turbolift", function(p)
        AC.pending = { player = p, dir = "lift", tries = 0, deck = to, lx = lx, ly = ly }
        U.note(p, getText("IGUI_TREK_TurboliftTo", L.decks[to].name), 120, 190, 255)
    end)
    return true
end

--- Down from the panel behind the breaker box to the station's first
--- sublevel (FIELD_STATION.md 3).
function AC.goDown(player)
    if not player or not FS.found() or not FS.playerInReach(player) then return false end
    local first = FS.firstDeck()
    if not first then return false end
    if busy() then busyNote(player) return false, "busy" end
    Core.requestMove(player, "stationDown", function(p)
        AC.pending = { player = p, dir = "down", tries = 0, deck = first }
        U.note(p, getText("IGUI_TREK_StationGoingDown"), 120, 190, 255)
    end)
    return true
end

--- Up from a station lift car to the stockroom.
function AC.goUp(player)
    if not player or not A.onStation(player) then return false end
    if not A.inLift(player:getX(), player:getY(), player:getZ()) then return false end
    if busy() then busyNote(player) return false, "busy" end
    Core.requestMove(player, "stationUp", function(p)
        AC.pending = { player = p, dir = "up", tries = 0 }
        U.note(p, getText("IGUI_TREK_StationGoingUp"), 120, 190, 255)
    end)
    return true
end

local function servicePending()
    local job = AC.pending
    if not job then return end
    if not job.player then AC.pending = nil return end
    job.tries = job.tries + 1
    local delay = (job.dir == "lift" or job.dir == "down" or job.dir == "up") and LIFT_DELAY
                  or C.BeamDelay
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
    elseif job.dir == "down" then
        -- The stockroom is where this player is on the map while they are
        -- below it; the server wrote the same on its own copy before the
        -- move (TREK_Server, MOVES).
        Ship.setReturnPoint(p, p:getX(), p:getY(), p:getZ())
        Ship.playerData(p).aboard = false
        local x, y = A.liftSpot(job.deck)
        U.log("down to the field station, %s", L.decks[job.deck].name)
        beginArrival(p, x, y, job.deck)
    elseif job.dir == "up" then
        AC.surface(p)
    end
end

Events.OnTick.Add(function()
    U.try("adk.pending", servicePending)
    U.try("adk.arrival", serviceArrival)
    U.try("adk.surfacing", serviceSurfacing)
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
    if not k then
        -- On one of the field station's old sublevels (a save from the one
        -- day it had three): nothing is there any more to stand on or leave
        -- by. Onto the station's floor, in its lift car.
        if A.inLegacyStation(x, y) and TREK.FieldStation and TREK.FieldStation.firstDeck() then
            local first = TREK.FieldStation.firstDeck()
            local sx, sy = A.liftSpot(first)
            U.log("standing on the field station's old sublevels; to %s", L.decks[first].name)
            beginArrival(player, sx, sy, first)
        end
        return
    end
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

---------------------------------------------------------------------------
-- Crawling
---------------------------------------------------------------------------
-- username -> { sneaking = what it was before the tube }, while in one.
local crawlers = {}

--- On a tube's crawlway: down on all fours, at a sneak, never a run. Off it:
--- up again, and sneaking only if they were before they went in. Only this
--- client's own character, which is the only one a client may touch.
function AC.serviceCrawl(player)
    local who = U.try("username", function() return player:getUsername() end) or "?"
    local st = crawlers[who]
    if A.crawling(player:getX(), player:getY(), player:getZ()) then
        if not st then
            st = { sneaking = player:isSneaking() == true }
            crawlers[who] = st
        end
        player:setVariable("TrekCrawl", true)
        if not player:isSneaking() then player:setSneaking(true) end
        player:setRunning(false)
        player:setSprinting(false)
        return true
    elseif st then
        crawlers[who] = nil
        player:setVariable("TrekCrawl", false)
        player:setSneaking(st.sneaking)
    end
    return false
end

function AC.isCrawling(player)
    local who = player and U.try("username", function() return player:getUsername() end)
    return who ~= nil and crawlers[who] ~= nil
end

Events.OnPlayerUpdate.Add(function(player)
    if not player or not player:isLocalPlayer() or player:isDead() then return end
    U.try("adk.checkAboard", checkAboard, player)
    U.try("adk.crawl", AC.serviceCrawl, player)
end)

---------------------------------------------------------------------------
-- Menus
---------------------------------------------------------------------------
function AC.onBeamTo(_, player) AC.beamTo(player) end
function AC.onBeamBack(_, player) AC.beamBack(player) end
function AC.onRide(_, player, k) AC.ride(player, k) end
function AC.onUp(_, player) AC.goUp(player) end
function AC.onDown(_, player) AC.goDown(player) end

--- The right-click menu anywhere aboard her. Replaces the shuttle's ground
--- menu there: calling the shuttle down onto a deck five storeys up in the
--- void is not a thing to offer.
function AC.menu(context, player, worldobjects, test)
    if test then return ISWorldObjectContextMenu.setTest() end
    local k, lx, ly = A.locate(player:getX(), player:getY(), player:getZ())
    local deck = k and L.decks[k]
    local site = A.siteOf(k)
    local title = getText(site == "fst" and "IGUI_TREK_FieldStation" or "IGUI_TREK_Adirondack")
    if deck then title = title .. " - " .. deck.name end
    local sub = context:addOption(title, worldobjects, nil)
    local menu = ISContextMenu:getNew(context)
    context:addSubMenu(sub, menu)

    local inLift = A.inLift(player:getX(), player:getY(), player:getZ())
    if inLift then
        local label = getText(site == "fst" and "IGUI_TREK_StationLift" or "IGUI_TREK_Turbolift")
        -- The phobic are told before they choose, not only after (TRAITS.md 4.3).
        if TREK.Traits and TREK.Traits.has(player, "turboliftphobia") then
            label = label .. " " .. getText("IGUI_TREK_LiftPhobiaWarn")
        end
        local liftSub = menu:addOption(label, worldobjects, nil)
        local lift = ISContextMenu:getNew(menu)
        menu:addSubMenu(liftSub, lift)
        -- The station's lift goes up to the stockroom as well as between
        -- its own sublevels; hers goes only between her decks.
        if site == "fst" then
            lift:addOption(getText("IGUI_TREK_StationUp", C.FieldStation.name), worldobjects,
                           AC.onUp, player)
        end
        for _, j in ipairs(A.decksOf(site)) do
            local d = L.decks[j]
            local opt = lift:addOption(getText("IGUI_TREK_AdkDeck", d.name, d.description),
                                       worldobjects, AC.onRide, player, j)
            if j == k then opt.notAvailable = true end
        end
    else
        local hint = menu:addOption(getText(site == "fst" and "IGUI_TREK_StationLiftHint"
                                            or "IGUI_TREK_TurboliftHint"), worldobjects, nil)
        hint.notAvailable = true
    end
    -- Her transporter is the way off her. The station has none: its way out
    -- is the lift.
    if site ~= "fst" then
        menu:addOption(getText("IGUI_TREK_BeamToShuttle"), worldobjects, AC.onBeamBack, player)
    end
    return true
end

return AC
