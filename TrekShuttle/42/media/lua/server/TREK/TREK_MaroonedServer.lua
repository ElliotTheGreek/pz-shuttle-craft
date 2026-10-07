--[[ Shuttlecraft -- marooned: the authority (MAROONED.md).

    Four jobs, all of them the cold start's machinery pointed somewhere else:

      * **the site.** Drawn once, when the first player is on their feet,
        from the sites that are in this world and at least
        C.Maroon.minDistance from them;
      * **the ship.** Set down at the site when somebody first loads its
        ground, and not before: the server builds only where a player stands
        (DEV_GUIDE, *Never build where no player is standing*). Until then she
        is a record. Nobody is told;
      * **the combadge.** The first time a player is in her cabin or one of
        her seats they are written into `s.badged`, and from then on the menu
        and the transporter are theirs;
      * **the maps.** A container the engine rolls with one of vanilla's maps
        in it may get an annotated one too, while she is still lost. Reading
        one puts her site on the ship's contacts, which every client draws on
        its world map.

    Authority only.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Ship"
require "TREK/TREK_World"
require "TREK/TREK_Vehicle"
require "TREK/TREK_Probes"
require "TREK/TREK_Marooned"
require "TREK/TREK_ColdStart"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local Ship = TREK.Ship
local W = TREK.World
local V = TREK.Vehicle
local Probes = TREK.Probes
local MR = TREK.Marooned
local CS = TREK.ColdStart

local MS = {}
TREK.MaroonedServer = MS

---------------------------------------------------------------------------
-- The site
---------------------------------------------------------------------------
--- Draws the site, once. Returns it, or nil when it was already drawn or no
--- site is in this world.
function MS.chooseSite(player)
    local s = U.state()
    if s.marooned ~= true or s.maroonSite then return nil end
    local px, py = math.floor(player:getX()), math.floor(player:getY())

    local far, farthest, farthestD = {}, nil, -1
    for _, site in ipairs(C.Maroon.sites) do
        if U.inWorld(site.x, site.y) then
            local d = math.sqrt(U.dist2(px, py, site.x, site.y))
            if d >= C.Maroon.minDistance then table.insert(far, site) end
            if d > farthestD then farthest, farthestD = site, d end
        end
    end

    if not farthest then
        -- Another map altogether. A ship nobody can find is a save nobody can
        -- play, so this world is a cold start after all.
        s.marooned = nil
        Ship.commit()
        U.log("WARN marooned: none of the %d sites is in this world; she is set down "
              .. "beside the first player instead, as a cold start", #C.Maroon.sites)
        return nil
    end

    local site = farthest
    if #far > 0 then
        local pick = U.try("maroonPick", function() return ZombRand(#far) end) or 0
        site = far[pick + 1] or far[1]
    end
    s.maroonSite = site.id
    Ship.commit()
    U.log("marooned: the shuttle came down at %s (%d,%d), %d squares from %s; %d of %d "
          .. "sites were far enough to draw from", site.id, site.x, site.y,
          math.floor(math.sqrt(U.dist2(px, py, site.x, site.y))), Ship.usernameOf(player),
          #far, #C.Maroon.sites)
    return site
end

---------------------------------------------------------------------------
-- The ship
---------------------------------------------------------------------------
local ring = nil
local function ringOffsets()
    if ring then return ring end
    ring = {}
    for r = 0, C.Maroon.placeMax do
        for dx = -r, r do
            for dy = -r, r do
                if math.max(math.abs(dx), math.abs(dy)) == r then
                    table.insert(ring, { dx, dy })
                end
            end
        end
    end
    return ring
end

local cursor = 0
local tried = 0

--- True while a marooned ship has a site and is not standing on it: never
--- commissioned, and not on the ground. The cold start's own test, for its
--- own reason (CS.needsPlacing): a dark ship that lost her vehicle is put
--- back where the maps say she is.
function MS.needsPlacing()
    local s = U.state()
    return s.marooned == true and s.commissioned == false and s.landed ~= true
           and s.maroonSite ~= nil
end

--- The player nearest a square, for the landing's exemption.
local function nearest(x, y)
    local best, bestD = nil, nil
    for _, p in ipairs(U.players()) do
        local d = U.try("maroonNear", function() return U.dist2(p:getX(), p:getY(), x, y) end)
        if d and (not bestD or d < bestD) then best, bestD = p, d end
    end
    return best
end

--- A shuttle contact that is still live, or nil.
local function liveContact()
    for _, c in ipairs(Probes.unresolved()) do
        if c.kind == "shuttle" then return c end
    end
    return nil
end

--- One slice of the search round the site. Returns true once she is down.
function MS.servicePlacement()
    if not MS.needsPlacing() then return false end
    local s = U.state()
    local site = MR.site()
    if not site then return false end
    -- Nobody is near: she stays a record. S.land would refuse unloaded
    -- ground by itself; what this line is for is the count below, which
    -- must not run up, and then warn there is no room, while nobody has
    -- been anywhere near her.
    if not U.chunkLoaded(site.x, site.y, 0) then return false end

    local order = ringOffsets()
    for _ = 1, W.SITES_PER_TICK do
        cursor = cursor + 1
        if cursor > #order then cursor = 1 end
        local d = order[cursor]
        local x, y = site.x + d[1], site.y + d[2]
        local sq = U.square(x, y, 0, false)
        if sq and U.try("maroonFloor", function() return sq:getFloor() ~= nil end) then
            local p = nearest(x, y)
            if W.roomToLand(x, y, 0, W.exemptFor(p)) then
                local landed, why = TREK.Server.land(x, y, 0, p)
                if landed then
                    cursor, tried = 0, 0
                    s.maroonPlaced = true
                    Ship.commit()
                    -- A map read before she was down marked the site's own
                    -- point; the mark moves to where she really is.
                    local contact = liveContact()
                    if contact then
                        contact.x, contact.y, contact.approximate = x, y, false
                        Probes.publish()
                    end
                    U.log("marooned: the shuttle is down at %d,%d, %d squares from the "
                          .. "%s site, without power", x, y,
                          math.max(math.abs(d[1]), math.abs(d[2])), site.id)
                    return true
                end
                U.log("WARN marooned: landing at %d,%d refused (%s)", x, y, tostring(why))
            end
        end
        tried = tried + 1
    end
    -- Round the whole ring several times with the ground loaded and nowhere
    -- to put her: said once, and the search goes on, because a player
    -- walking closer loads more of it.
    if tried > #order * 4 then
        U.warnOnce("maroonNoRoom", "marooned: no room for the shuttle within "
                   .. C.Maroon.placeMax .. " squares of the " .. site.id .. " site yet")
    end
    return false
end

---------------------------------------------------------------------------
-- The combadge
---------------------------------------------------------------------------
--- True when this player is in her cabin or in one of her seats.
local function aboardHer(p)
    return U.try("maroonAboard", function()
        if U.isAboard(p:getX(), p:getY(), p:getZ()) then return true end
        return V.isShuttle(p:getVehicle())
    end) == true
end

--- Links one player, and tells them. For somebody MR.linked says is not:
--- serviceBadges is the only caller and asks first, and a second test here
--- was a branch nothing could reach (DEV_GUIDE, *A branch a mutation cannot
--- break may be unreachable*).
function MS.link(player)
    local s = U.state()
    local name = Ship.usernameOf(player)
    s.badged = type(s.badged) == "table" and s.badged or {}
    s.badged[name] = true
    -- Finding her is a marooned world's news; a cold ship was never lost.
    local first = s.marooned == true and s.maroonFound ~= true
    if s.marooned == true then s.maroonFound = true end
    Ship.commit()
    if first then
        -- She is found: the mark on the map has done its work.
        local contact = liveContact()
        if contact then
            Probes.setStatus(contact.id, "completed")
            Probes.prune()
            Probes.publish()
        end
    end
    U.log("pattern: %s is aboard for the first time; the ship has their pattern%s", name,
          first and "; the shuttle is found" or "")
    Net.toClient(player, "maroonLinked", { first = first })
end

--- Links everybody who is aboard her and was not.
function MS.serviceBadges()
    local s = U.state()
    if type(s.badged) ~= "table" then return 0 end
    local n = 0
    for _, p in ipairs(U.players()) do
        if not MR.linked(p) and U.try("maroonDead", function() return p:isDead() end) == false
           and aboardHer(p) then
            MS.link(p)
            n = n + 1
        end
    end
    return n
end

---------------------------------------------------------------------------
-- The maps
---------------------------------------------------------------------------
--- True when a container holds one of vanilla's maps.
local function holdsMap(container)
    return U.try("maroonHoldsMap", function()
        local items = container:getItems()
        for i = 0, items:size() - 1 do
            local it = items:get(i)
            if it and it:IsMap() then return true end
        end
        return false
    end) == true
end

--- The engine has just rolled a container's loot. While she is lost, a
--- container that came up with a map in it has a chance of an annotated one.
---
--- **At the roll, not in the loot tables** (the way dilithium is seeded),
--- because this is the only moment that knows which world it is: a table is
--- merged before the sandbox or the ship's state can be asked, and an
--- annotated map in a world that did not begin marooned is clutter that
--- points at nothing. It also follows any map mod's own map places for free.
---
--- ItemPickerJava.fillContainerInternal returns at once on a client (bci
--- 0-18), so this runs on the authority only, and the event is raised as
--- its last act, before the container's contents are sent to anybody.
function MS.onFillContainer(_, _, container)
    local s = U.state()
    if s.marooned ~= true or s.maroonFound == true then return false end
    if not container or not holdsMap(container) then return false end
    local roll = U.try("maroonMapRoll", function() return ZombRand(100) end) or 100
    if roll >= C.Maroon.mapChance then return false end
    local before = U.try("maroonMapBefore", function() return container:getItems():size() end) or 0
    U.try("maroonMapAdd", function()
        local item = instanceItem(C.Maroon.mapItem)
        if item then container:AddItem(item) end
    end)
    local after = U.try("maroonMapAfter", function() return container:getItems():size() end) or 0
    if after <= before then
        U.warnOnce("maroonMapFull", "marooned: an annotated map would not go into a container")
        return false
    end
    s.maroonMaps = (s.maroonMaps or 0) + 1
    U.log("marooned: an annotated map is in a container beside one of the county's own "
          .. "(%d so far)", s.maroonMaps)
    return true
end

--- A player reads an annotated map they are carrying.
Net.onServer("readShuttleMap", function(player, args)
    if U.try("maroonReaderDead", function() return player:isDead() end) ~= false then return end
    local item = U.try("maroonMapById", function()
        return player:getInventory():getItemWithIDRecursiv(tonumber(args.id))
    end)
    if not MR.isMap(item) then return end

    local s = U.state()
    local site = MR.site()
    -- A map carried into a world that is not marooned (which never drew a
    -- site), or read once she has been found: the marks are old news, and it
    -- says so.
    if not site or s.maroonFound == true then
        Net.toClient(player, "maroonMap", { stale = true })
        return
    end

    local contact = liveContact()
    if not contact then
        local x, y = site.x, site.y
        if s.landed and s.maroonPlaced then x, y = s.x, s.y end
        contact = Probes.addContact("shuttle", x, y, 0, nil, not s.maroonPlaced)
        if not contact then return end
        Probes.publish()
        U.log("marooned: %s read an annotated map; the %s site is on the ship's contacts",
              Ship.usernameOf(player), site.id)
    end
    Net.toClient(player, "maroonMap", { site = site.id, x = contact.x, y = contact.y })
end)

---------------------------------------------------------------------------
-- Timers
---------------------------------------------------------------------------
local tick = 0
Events.OnTick.Add(function()
    local s = U.state()
    if s.marooned == true then
        if not s.maroonSite then
            local p = CS.firstOnFoot()
            if p then U.try("maroonChoose", MS.chooseSite, p) end
        elseif MS.needsPlacing() then
            U.try("maroonPlace", MS.servicePlacement)
        end
    end
    -- Patterns are learned in any world that began dark, marooned or cold.
    if type(s.badged) ~= "table" then return end
    tick = tick + 1
    if tick >= C.Maroon.badgeTicks then
        tick = 0
        U.try("maroonBadges", MS.serviceBadges)
    end
end)

Events.OnFillContainer.Add(function(room, kind, container)
    U.try("maroonFill", MS.onFillContainer, room, kind, container)
end)

return MS
