--[[ Shuttlecraft -- the Adirondack's crew, on the server (CREW.md 5).

    The server owns the crew: it brings them aboard a deck through the lift
    cars while somebody is on that deck, gives each one a script -- walk to a
    spot, stand at a console, sit, and eventually go back to the lift -- plays
    the scenes between them, and says their barks. What it decides is written
    into the `TREK_Crew` mod data (one entry per crew member, with its current
    `step`), and every line of speech is broadcast as `crewSay`.

    **It does not move them.** Build 42 simulates each zombie on one client,
    and a path set here would be undone by that client's next update. The
    client that owns a crew member walks it to the step's square
    (TREK_CrewClient). This side watches where it has got to -- the owner
    reports the body's position like any zombie's -- and moves the script on
    when it arrives, or gives up on a walk that takes too long.

    Crew are **not saved**. They exist while somebody is on their deck; when
    the last person leaves they go, and a crew body the server does not know
    (a save made with crew aboard) is removed when it is seen.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Adirondack"
require "TREK/TREK_Crew"
require "TREK/TREK_CrewTalk"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local A = TREK.Adirondack
local K = TREK.Crew
local L = A.Layout
local Talk = TREK_CrewTalk

local CS = {}
TREK.CrewServer = CS

-- ms between one crew member coming aboard a deck and the next.
CS.SpawnGap = 7000
-- How long somebody stays at a spot, in ms.
CS.StayMin, CS.StayMax = 25000, 90000
-- A walk that has not arrived by now is given up.
CS.WalkLimit = 45000
-- Spots visited before heading back to the lift.
CS.TasksMin, CS.TasksMax = 2, 6
-- Barks.
CS.BarkReach = 3.2
CS.BarkCrewGap = 45000
CS.BarkPlayerGap = 14000
CS.IdleGap = 30000
-- Scenes.
CS.ScenesPerDeck = 2
CS.SceneGapMin, CS.SceneGapMax = 15000, 40000
CS.SceneReach = 6

local live = {}          -- id (string) -> { z, e, ... } -- the server's own bookkeeping
local reserved = {}      -- spot key -> id
local nextSpawn = {}     -- deck -> ms
local nextScene = {}     -- deck -> ms
local nextIdle = {}      -- deck -> ms
local running = {}       -- list of scene runs
-- What the director has done, for a report and for the tests.
CS.stats = { tries = 0, few = 0, started = 0, gathered = 0, dropped = 0, lines = 0, finished = 0 }
local playerBarkAt = {}  -- username -> ms
local serial = 0         -- single-player ids

local function now() return getTimestampMs() end
local function rnd(n) return ZombRand(n) end
local function between(a, b) return a + rnd(math.max(1, b - a)) end

---------------------------------------------------------------------------
-- The mod data
---------------------------------------------------------------------------
local dirty = false

local function publish()
    if not dirty then return end
    dirty = false
    if isServer() then
        U.try("crew.transmit", function() ModData.transmit(K.StateKey) end)
    end
end

local function setStep(m, step)
    m.e.seq = (m.e.seq or 0) + 1
    step.seq = m.e.seq
    m.e.step = step
    m.stepAt = now()
    dirty = true
end

---------------------------------------------------------------------------
-- Speaking
---------------------------------------------------------------------------
local function say(m, base, n, names)
    local key = base .. "_" .. (rnd(math.max(1, n)) + 1)
    Net.toAll("crewSay", { id = m.id, k = key, names = names })
    local text = U.try("crew.text", function() return getText(key) end)
    return type(text) == "string" and text ~= key and #text or 60
end

-- A line stays up about as long as it takes to read (CREW.md 5).
CS.LineBase, CS.LinePerChar, CS.BeatMs = 2500, 60, 3000

local function lineMs(chars)
    return CS.LineBase + CS.LinePerChar * chars
end

local function barkFrom(cat, place)
    local list = Talk.barks and Talk.barks[cat]
    if not list then return nil end
    local fit = {}
    for _, b in ipairs(list) do
        if b.where.any or (place and b.where[place]) then table.insert(fit, b) end
    end
    if #fit == 0 then return nil end
    return fit[rnd(#fit) + 1]
end

local function bark(m, cat)
    local place = K.placeAt(m.e.deck, m.lx or 0, m.ly or 0)
    local b = barkFrom(cat, place)
    if not b then return false end
    say(m, b.key, b.n)
    m.barkAt = now()
    return true
end

---------------------------------------------------------------------------
-- Coming and going
---------------------------------------------------------------------------
local function pacify(z)
    U.try("crew.pacify", function()
        z:setUseless(true)
        z:setNoTeeth(true)
        z:setTarget(nil)
        z:setVariable("TrekCrew", true)
        z:getDescriptor():setVoicePrefix("NotAZombie")
    end)
end

local function positionOf(m)
    local x = U.try("crew.x", function() return m.z:getX() end)
    local y = U.try("crew.y", function() return m.z:getY() end)
    if not x then return nil end
    local k, lx, ly = A.locate(x, y)
    return x, y, k, lx, ly
end

local function gone(m)
    return U.try("crew.dead", function() return m.z:isDead() end) ~= false
        or U.try("crew.sq", function() return m.z:getCurrentSquare() end) == nil
end

local function release(m)
    for key, id in pairs(reserved) do
        if id == m.id then reserved[key] = nil end
    end
end

local function despawn(m, why)
    release(m)
    live[m.id] = nil
    K.state().crew[m.id] = nil
    dirty = true
    U.try("crew.remove", function()
        m.z:removeFromWorld()
        m.z:removeFromSquare()
    end)
    Net.toAll("crewGone", { id = m.id })
    U.debug("crew: %s (%s) left the deck: %s", m.e.name, m.id, tostring(why))
end
CS.despawn = despawn

local function spawn(k)
    local lx, ly = K.liftSquare(k)
    local x, y = A.at(k, lx, ly)
    local sq = U.square(x, y, A.Z, false)
    if not sq or not U.try("crew.floor", function() return sq:getFloor() ~= nil end) then return nil end
    local female = rnd(2) == 0
    local list = U.try("crew.spawn", function()
        return addZombiesInOutfit(x, y, A.Z, 1, K.Outfit, female and 100 or 0,
                                  false, false, false, false, false, false, 1.0)
    end)
    local z = list and U.try("crew.first", function()
        return list:size() > 0 and list:get(0) or nil
    end)
    if not z then
        U.warnOnce("crew.none", "crew: addZombiesInOutfit gave no body -- is the sandbox set to "
                   .. "no zombies? The Adirondack will be empty.")
        return nil
    end
    pacify(z)
    local id
    if isServer() then
        id = K.id(z)
    else
        serial = serial + 1
        id = serial
        U.try("crew.tag", function() z:getModData().TREKCrew = id end)
    end
    if id == nil then
        -- No online id yet: not somebody we can name to a client. Try again later.
        U.try("crew.drop", function() z:removeFromWorld(); z:removeFromSquare() end)
        return nil
    end
    U.try("crew.mark", function() z:getModData().TREKCrewServer = true end)
    id = tostring(id)
    local e = K.newMember(k, U.try("crew.female", function() return z:isFemale() end) == true)
    e.id = id
    local m = { id = id, z = z, e = e, tasks = between(CS.TasksMin, CS.TasksMax + 1),
                barkAt = now() - rnd(CS.BarkCrewGap) }
    live[id] = m
    K.state().crew[id] = e
    setStep(m, { k = "stand", x = lx, y = ly, fx = lx + 2, fy = ly + 2 })
    m.state, m.untilAt = "stay", now() + between(2000, 6000)
    if rnd(3) == 0 then bark(m, "arrive") end
    U.debug("crew: %s (%s, %s) came aboard deck %d", e.name, e.div, e.job, k)
    return m
end
CS.spawn = spawn

---------------------------------------------------------------------------
-- Where to next
---------------------------------------------------------------------------
-- The rooms a job prefers, weighted over the rest of the deck.
local PREFER = {
    helm = { bridge = 5, readyroom = 1 }, command = { bridge = 4, readyroom = 2 },
    medical = { sickbay = 6 }, engineer = { engineering = 6 },
    security = { bridge = 2, transporter = 2, corridor = 2 },
    operations = { transporter = 3, engineering = 2, galley = 2 },
    sciences = { bridge = 2, sickbay = 2 },
}

local function spotKey(k, s) return k .. ":" .. s.x .. "," .. s.y end

local function chooseSpot(m)
    local k = m.e.deck
    local prefer = PREFER[m.e.job] or {}
    local pool, total = {}, 0
    for _, s in ipairs(K.spots(k)) do
        local key = spotKey(k, s)
        if not reserved[key] then
            local w = (prefer[s.place] or 1) * (s.kind == "sit" and 1.3 or 1)
            table.insert(pool, { s, w })
            total = total + w
        end
    end
    if total <= 0 then return nil end
    local r = rnd(1000) / 1000 * total
    for _, p in ipairs(pool) do
        r = r - p[2]
        if r <= 0 then return p[1] end
    end
    return pool[#pool][1]
end

local function goTo(m, s)
    release(m)
    reserved[spotKey(m.e.deck, s)] = m.id
    m.target = s
    m.state = "walk"
    setStep(m, { k = "walk", x = s.x, y = s.y })
end

local function leave(m)
    release(m)
    local lx, ly = K.liftSquare(m.e.deck)
    m.target = { kind = "lift", x = lx, y = ly }
    m.state = "walk"
    m.leaving = true
    setStep(m, { k = "walk", x = lx, y = ly })
    if rnd(3) == 0 then bark(m, "leave") end
end

local function arrive(m)
    local s = m.target
    if m.leaving then
        despawn(m, "into the lift")
        return
    end
    if s.kind == "sit" then
        setStep(m, { k = "sit", x = s.x, y = s.y, face = s.face, fx = s.fx, fy = s.fy })
    else
        setStep(m, { k = "stand", x = s.x, y = s.y, fx = s.fx, fy = s.fy })
    end
    m.state = "stay"
    m.untilAt = now() + between(CS.StayMin, CS.StayMax)
end

local function serviceMember(m, t)
    local x, y, k, lx, ly = positionOf(m)
    if not x or k ~= m.e.deck then
        -- Off the deck: pushed through a wall, or fell. Not ours to chase.
        despawn(m, "off the deck")
        return
    end
    m.x, m.y, m.lx, m.ly = x, y, lx, ly
    if m.scene then return end
    if m.state == "walk" then
        local tx, ty = A.at(k, m.target.x, m.target.y)
        -- A seat is solid, so the path ends beside it rather than on it: near
        -- enough is arrived, and the owner then sets them down in it
        -- (TREK_CrewClient, the sit step).
        local reach = (m.target.kind == "sit") and 1.6 or 0.9
        if U.dist2(x, y, tx + 0.5, ty + 0.5) < reach * reach then
            arrive(m)
        elseif t - (m.stepAt or t) > CS.WalkLimit then
            if m.leaving then despawn(m, "never reached the lift") return end
            m.state, m.untilAt = "stay", t
        end
    elseif m.state == "stay" and t >= (m.untilAt or 0) then
        m.tasks = m.tasks - 1
        local s = m.tasks > 0 and chooseSpot(m) or nil
        if s then goTo(m, s) else leave(m) end
    end
end

---------------------------------------------------------------------------
-- Scenes (CREW.md 5)
---------------------------------------------------------------------------
local loreSeen = function()
    local s = K.state()
    s.lore = s.lore or {}
    return s.lore
end

local function idleOn(k)
    local out = {}
    for _, m in pairs(live) do
        if m.e.deck == k and not m.scene and not m.leaving and m.state == "stay" and m.x then
            table.insert(out, m)
        end
    end
    return out
end

local function castFor(scene, seed, pool, anywhere)
    local cast, used = {}, {}
    for i, role in ipairs(scene.cast) do
        local found = nil
        if i == 1 then
            if K.fits(role.req, seed.e) then found = seed end
        else
            for _, m in ipairs(pool) do
                if not used[m.id] and m ~= seed and K.fits(role.req, m.e)
                   and (anywhere or U.dist2(m.x, m.y, seed.x, seed.y) <= CS.SceneReach * CS.SceneReach) then
                    found = m
                    break
                end
            end
        end
        if not found then return nil end
        used[found.id] = true
        cast[i] = found
    end
    return cast
end

local function faceEachOther(run)
    local cast = run.cast
    for i, m in ipairs(cast) do
        -- Turn to whoever they are talking with: the first speaker to the
        -- second, everybody else to the first.
        local other = (i == 1) and cast[2] or cast[1]
        local step = m.e.step or {}
        if step.k ~= "sit" then
            setStep(m, { k = "stand", x = m.lx, y = m.ly,
                         fx = other.lx or m.lx, fy = other.ly or m.ly })
        end
        m.state = "stay"
    end
end

--- Starts a scene. With `gather`, the rest of the cast first walk over to
--- the first speaker -- somebody crossing the room to say something -- and
--- the talk begins when they are all there (or is dropped if they never are).
local function startScene(k, scene, cast, gather)
    local names = {}
    for i, role in ipairs(scene.cast) do names[role.name] = K.address(cast[i].e) end
    local t = now()
    local run = { k = k, scene = scene, cast = cast, names = names, node = "start",
                  line = 0, nextAt = t }
    for _, m in ipairs(cast) do m.scene = run end
    if gather then
        run.gathering, run.deadline = true, t + 30000
        local seed, taken = cast[1], {}
        for i = 2, #cast do
            local m = cast[i]
            if U.dist2(m.x, m.y, seed.x, seed.y) > 2.5 * 2.5 then
                local gx, gy = K.freeNear(k, seed.lx, seed.ly, taken)
                if not gx then
                    for _, c in ipairs(cast) do c.scene = nil end
                    return false
                end
                taken[gx .. "," .. gy] = true
                release(m)
                m.target = { kind = "stand", x = gx, y = gy }
                m.state = "walk"
                setStep(m, { k = "walk", x = gx, y = gy })
            end
        end
    else
        faceEachOther(run)
    end
    if scene.lore then loreSeen()[scene.id] = true end
    if gather then CS.stats.gathered = CS.stats.gathered + 1 else CS.stats.started = CS.stats.started + 1 end
    table.insert(running, run)
    U.debug("crew: scene %s on deck %d%s", scene.id, k, gather and " (gathering)" or "")
    return true
end

local function endScene(run)
    for _, m in ipairs(run.cast) do
        if live[m.id] == m then
            m.scene = nil
            m.state = "stay"
            m.untilAt = now() + between(8000, 25000)
        end
    end
    for i, r in ipairs(running) do
        if r == run then table.remove(running, i) break end
    end
end

local function serviceScene(run, t)
    for _, m in ipairs(run.cast) do
        if live[m.id] ~= m then endScene(run) return end
    end
    if run.gathering then
        local seed, all = run.cast[1], true
        for i = 2, #run.cast do
            local m = run.cast[i]
            -- They were sent to a square within two of the seed, and a
            -- diagonal two is 2.8 away.
            if not m.x or U.dist2(m.x, m.y, seed.x, seed.y) > 3.2 * 3.2 then all = false end
        end
        if all then
            run.gathering = nil
            faceEachOther(run)
            run.nextAt = t + 800
        elseif t > run.deadline then
            CS.stats.dropped = CS.stats.dropped + 1
            endScene(run)
        end
        return
    end
    if t < run.nextAt then return end
    local node = run.scene.nodes[run.node]
    run.line = run.line + 1
    local ln = node and node.lines[run.line]
    if not ln then
        local nxt = node and node.next or {}
        if #nxt == 0 then CS.stats.finished = CS.stats.finished + 1 endScene(run) return end
        local total = 0
        for _, n in ipairs(nxt) do total = total + n[2] end
        local r = rnd(1000) / 1000 * total
        local go = nxt[#nxt][1]
        for _, n in ipairs(nxt) do
            r = r - n[2]
            if r <= 0 then go = n[1] break end
        end
        run.node, run.line = go, 0
        run.nextAt = t + 600
        return
    end
    if ln[1] == 0 then
        run.nextAt = t + CS.BeatMs
        return
    end
    local speaker = run.cast[ln[1]]
    local chars = say(speaker, ln[2], ln[3], run.names)
    CS.stats.lines = CS.stats.lines + 1
    run.nextAt = t + lineMs(chars)
end

local function sceneOn(k)
    local n = 0
    for _, r in ipairs(running) do if r.k == k then n = n + 1 end end
    return n
end

local function tryScene(k, t)
    if not Talk.scenes or #Talk.scenes == 0 then return end
    if sceneOn(k) >= CS.ScenesPerDeck then return end
    CS.stats.tries = CS.stats.tries + 1
    local pool = idleOn(k)
    if #pool < 2 then CS.stats.few = CS.stats.few + 1 return end
    local seen = loreSeen()
    for _ = 1, 6 do
        local seed = pool[rnd(#pool) + 1]
        local place = K.placeAt(k, seed.lx, seed.ly)
        local fit, total = {}, 0
        for _, sc in ipairs(Talk.scenes) do
            if (sc.where.any or (place and sc.where[place])) and not (sc.lore and seen[sc.id]) then
                local w = sc.weight * (sc.lore and 0.25 or 1) * (sc.rare and 0.5 or 1)
                table.insert(fit, { sc, w })
                total = total + w
            end
        end
        if total > 0 then
            for _ = 1, 4 do
                local r = rnd(1000) / 1000 * total
                local sc = fit[#fit][1]
                for _, f in ipairs(fit) do
                    r = r - f[2]
                    if r <= 0 then sc = f[1] break end
                end
                local cast = castFor(sc, seed, pool)
                if cast and startScene(k, sc, cast) then return end
                -- Nobody near enough: somebody comes over.
                cast = castFor(sc, seed, pool, true)
                if cast and startScene(k, sc, cast, true) then return end
            end
        end
    end
end

---------------------------------------------------------------------------
-- Barks
---------------------------------------------------------------------------
local function inUniform(p)
    local ok = U.try("crew.worn", function()
        local worn = p:getWornItems()
        for i = 0, worn:size() - 1 do
            local item = worn:getItemByIndex(i)
            local t = item and item:getFullType()
            for _, u in ipairs(C.UniformIssue) do
                if t == u then return true end
            end
        end
        return false
    end)
    return ok ~= false
end

local function barkAt(p, t)
    local name = U.try("crew.pname", function() return p:getUsername() end) or "?"
    if t - (playerBarkAt[name] or 0) < CS.BarkPlayerGap then return end
    local px, py, pz = p:getX(), p:getY(), p:getZ()
    local k = A.locate(px, py, pz)
    if not k then return end
    local best, bd = nil, nil
    for _, m in pairs(live) do
        if m.e.deck == k and not m.scene and m.x and t - (m.barkAt or 0) >= CS.BarkCrewGap then
            local d = U.dist2(m.x, m.y, px, py)
            if d <= CS.BarkReach * CS.BarkReach and (not bd or d < bd) then best, bd = m, d end
        end
    end
    if not best then return end
    local place = K.placeAt(k, best.lx, best.ly)
    local cat = "hello"
    local species = TREK.Traits and TREK.Traits.species and TREK.Traits.species(p)
    if not inUniform(p) and rnd(10) < 6 then
        cat = "outfit"
    elseif species and rnd(10) < 3 and Talk.barks["species:" .. species] then
        cat = "species:" .. species
    elseif (place == "transporter" or place == "sickbay") and rnd(10) < 3 then
        cat = "thanks"
    end
    if bark(best, cat) or (cat ~= "hello" and bark(best, "hello")) then
        playerBarkAt[name] = t
    end
end

---------------------------------------------------------------------------
-- The loop
---------------------------------------------------------------------------
local function decksWithPlayers()
    local on, players = {}, {}
    for _, p in ipairs(U.players()) do
        local dead = U.try("crew.pdead", function() return p:isDead() end)
        if dead == false then
            local k = A.locate(p:getX(), p:getY(), p:getZ())
            if k then
                on[k] = true
                table.insert(players, p)
            end
        end
    end
    return on, players
end

--- Removes crew bodies nobody is running: a save made with crew aboard, or a
--- body left behind by a server restart. Bodies only; entries go with them.
local function sweepStrays()
    U.try("crew.sweep", function()
        local list = getCell():getZombieList()
        local doomed = {}
        for i = 0, list:size() - 1 do
            local z = list:get(i)
            if K.aboard(z) then
                local md = U.try("crew.sweepMd", function() return z:getModData() end)
                if md and (md.TREKCrewServer or md.TREKCrew) then
                    local id = K.id(z)
                    if id == nil or not live[tostring(id)] then table.insert(doomed, z) end
                end
            end
        end
        for _, z in ipairs(doomed) do
            z:removeFromWorld()
            z:removeFromSquare()
        end
    end)
end

local lastTick, lastSweep = 0, 0

function CS.tick()
    local t = now()
    if t - lastTick < 250 then return end
    lastTick = t
    local on, players = decksWithPlayers()

    for _, m in pairs(live) do
        if gone(m) or not on[m.e.deck] then
            despawn(m, gone(m) and "the body is gone" or "nobody is on the deck")
        end
    end
    -- Entries with no body behind them (a reloaded world): cleared.
    for id in pairs(K.state().crew) do
        if not live[id] then K.state().crew[id] = nil dirty = true end
    end
    if t - lastSweep > 10000 then
        lastSweep = t
        sweepStrays()
    end

    for k in pairs(on) do
        if TREK.AdirondackServer and TREK.AdirondackServer.deckCurrent(k) then
            local count = 0
            for _, m in pairs(live) do if m.e.deck == k then count = count + 1 end end
            if count < (K.Population[k] or 4) and t >= (nextSpawn[k] or 0) then
                spawn(k)
                nextSpawn[k] = t + CS.SpawnGap
            end
            if t >= (nextScene[k] or 0) then
                tryScene(k, t)
                nextScene[k] = t + between(CS.SceneGapMin, CS.SceneGapMax)
            end
            if t >= (nextIdle[k] or 0) then
                nextIdle[k] = t + between(CS.IdleGap, CS.IdleGap * 2)
                local pool = idleOn(k)
                if #pool > 0 then bark(pool[rnd(#pool) + 1], "idle") end
            end
        end
    end
    for _, m in pairs(live) do
        if live[m.id] == m then serviceMember(m, t) end
    end
    for i = #running, 1, -1 do
        if running[i] then serviceScene(running[i], t) end
    end
    for _, p in ipairs(players) do barkAt(p, t) end
    publish()
end

--- Crew positions on a deck, for the doors (TREK_AdirondackServer).
function CS.bodies()
    local out = {}
    for _, m in pairs(live) do
        if m.x then table.insert(out, { k = m.e.deck, x = m.x, y = m.y, z = m.z }) end
    end
    return out
end

function CS.live() return live end

--- Forgets every timer, so the next tick spawns, talks and barks at once.
function CS.wake()
    nextSpawn, nextScene, nextIdle = {}, {}, {}
end
function CS.running() return running end

Events.OnTick.Add(function()
    U.try("crew.tick", CS.tick)
end)

return CS
