--[[ Shuttlecraft -- the Adirondack's crew, as every client sees them.

    The server decides (TREK_CrewServer); this carries it out, on every copy
    of every crew member this machine has (CREW.md 1, 5):

      * **dressed, every client:** a crew member arrives as a zombie in an
        empty outfit, and a zombie's packet carries only its outfit id. So the
        human skin, the hair, the uniform, the shoes and the species look are
        put on here, from the entry in `TREK_Crew`: Bandits' method (its
        Bandit.lua, ApplyVisuals), because nothing else reaches a remote
        client's copy of a zombie;
      * **quiet and harmless, every client:** no target, no groans, no teeth,
        and the walk and idle of a person (common/media/AnimSets/zombie/*trek*);
      * **walked and seated by the one client that simulates it** (the owner,
        `not isRemoteZombie()`, or single player), to the square of its
        current step. The server watches it arrive;
      * **heard, every client:** `crewSay` is drawn over the speaker's head.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Adirondack"
require "TREK/TREK_Crew"
require "TREK/TREK_Looks"

TREK = TREK or {}
local U = TREK.Util
local Net = TREK.Net
local A = TREK.Adirondack
local K = TREK.Crew

local CC = {}
TREK.CrewClient = CC

-- Per body, by the object itself: which look and which step this client has
-- already applied. Weak, so a body the engine drops takes its row with it.
local looked = setmetatable({}, { __mode = "k" })
local facedSeq = setmetatable({}, { __mode = "k" })

local VOICES = { "FemaleZombieVoiceA", "FemaleZombieVoiceB", "FemaleZombieVoiceC",
                 "MaleZombieVoiceA", "MaleZombieVoiceB", "MaleZombieVoiceC",
                 "FemaleZombieCombined", "MaleZombieCombined" }

---------------------------------------------------------------------------
-- The mod data, as this client has it
---------------------------------------------------------------------------
Events.OnInitGlobalModData.Add(function()
    if not isClient() then return end
    U.try("crew.request", function() ModData.request(K.StateKey) end)
end)

Events.OnReceiveGlobalModData.Add(function(key, data)
    if key ~= K.StateKey or not isClient() or type(data) ~= "table" then return end
    ModData.add(key, data)
end)

---------------------------------------------------------------------------
-- Dressing
---------------------------------------------------------------------------
local function visual(type_, tint)
    local iv = ItemVisual.new()
    iv:setItemType(type_)
    iv:setClothingItemName(type_)
    if tint then iv:setTint(tint) end
    return iv
end

--- Makes a zombie look like this crew member. Bandits' cleanup first -- the
--- blood, the dirt, the holes and the rot all come off -- then the person.
function CC.dress(z, e)
    local hv = z:getHumanVisual()
    U.try("crew.clean", function()
        hv:removeDirt()
        hv:removeBlood()
        local max = BloodBodyPartType.MAX:index()
        for i = 0, max - 1 do
            local part = BloodBodyPartType.FromIndex(i)
            hv:setBlood(part, 0)
            hv:setDirt(part, 0)
        end
    end)
    U.try("crew.body", function()
        hv:setSkinTextureName(e.f and ("FemaleBody0" .. e.skin) or ("MaleBody0" .. e.skin .. "a"))
        hv:setHairModel(e.hair)
        if not e.f then hv:setBeardModel(e.beard or "") end
        local c = K.HairColours[e.hc or 1] or K.HairColours[1]
        local col = ImmutableColor.new(c[1], c[2], c[3])
        hv:setHairColor(col)
        hv:setBeardColor(col)
    end)
    U.try("crew.clothes", function()
        z:getWornItems():clear()
        local ivs = z:getItemVisuals()
        ivs:clear()
        ivs:add(visual(K.Shoes))
        ivs:add(visual(K.Uniform[e.div] or K.Uniform.operations))
    end)
    -- The species: the same call that dresses a player (TREK_Looks).
    U.try("crew.species", function() TREK.Looks.dress(hv, e.sp or nil, e.f) end)
    U.try("crew.reset", function() z:resetModel() end)
end

---------------------------------------------------------------------------
-- Every tick, for every crew body this client has
---------------------------------------------------------------------------
local function quiet(z)
    U.try("crew.quiet", function()
        z:getDescriptor():setVoicePrefix("NotAZombie")
        local em = z:getEmitter()
        for _, v in ipairs(VOICES) do em:stopSoundByName(v) end
    end)
end

local function owner(z)
    if not isClient() then return true end
    return U.try("crew.remote", function() return z:isRemoteZombie() end) == false
end

local function atSquare(z, x, y)
    return U.dist2(z:getX(), z:getY(), x + 0.5, y + 0.5) < 0.6 * 0.6
end

-- The route a body is walking, by the body: { seq, pts, i, at }.
local routes = setmetatable({}, { __mode = "k" })

--- Stops whatever the engine's own pathfinder may have started. It has no
--- idea where our walls are (see K.route), and left to itself it walks the
--- crew into them.
local function stopEngine(z)
    U.try("crew.stopEngine", function()
        local pf = z:getPathFindBehavior2()
        pf:cancel()
        pf:reset()
        z:setPath2(nil)
    end)
end

--- Walks a body one tick along its route: our route, our pace, the walking
--- animation on while it moves (TrekMove, common/media/AnimSets/zombie/idle).
local function walk(z, e, step)
    local k = e.deck
    local r = routes[z]
    local t = getTimestampMs()
    if not r or r.seq ~= step.seq then
        stopEngine(z)
        local dx, dy = A.at(k, 0, 0)
        local sx, sy = math.floor(z:getX()) - dx, math.floor(z:getY()) - dy
        local pts = K.route(k, sx, sy, step.x, step.y) or { { step.x, step.y } }
        r = { seq = step.seq, pts = pts, i = 1, at = t }
        routes[z] = r
    end
    local pt = r.pts[r.i]
    if not pt then
        U.try("crew.halt", function() z:setVariable("TrekMove", false) end)
        return
    end
    local tx, ty = A.at(k, pt[1], pt[2])
    tx, ty = tx + 0.5, ty + 0.5
    local dt = math.min(0.1, math.max(0, (t - r.at) / 1000))
    r.at = t
    local x, y = z:getX(), z:getY()
    local ddx, ddy = tx - x, ty - y
    local d = math.sqrt(ddx * ddx + ddy * ddy)
    local stepLen = K.WalkSpeed * dt
    U.try("crew.move", function()
        z:setVariable("TrekMove", true)
        if d <= stepLen or d < 0.02 then
            z:setX(tx) z:setY(ty) z:setLastX(tx) z:setLastY(ty)
            r.i = r.i + 1
            local nxt = r.pts[r.i]
            if nxt then
                local nx, ny = A.at(k, nxt[1], nxt[2])
                z:faceLocationF(nx + 0.5, ny + 0.5)
            end
        else
            local nx, ny = x + ddx / d * stepLen, y + ddy / d * stepLen
            z:setX(nx) z:setY(ny) z:setLastX(nx) z:setLastY(ny)
            if r.i == 1 or not r.faced then
                r.faced = true
                z:faceLocationF(tx, ty)
            end
        end
    end)
end

local function carryOut(z, e)
    local step = e.step
    if not step then return end
    local k = e.deck
    local x, y = A.at(k, step.x, step.y)
    if step.k == "walk" then
        walk(z, e, step)
        return
    end
    -- Arrived: stand or sit, facing the right way.
    if routes[z] then
        routes[z] = nil
        stopEngine(z)
    end
    U.try("crew.still", function() z:setVariable("TrekMove", false) end)
    if step.k == "sit" then
        local off = K.SitOffset[step.face or "S"] or K.SitOffset.S
        U.try("crew.seat", function()
            z:setX(x + off[1])
            z:setY(y + off[2])
            z:setLastX(x + off[1])
            z:setLastY(y + off[2])
        end)
    end
    if facedSeq[z] ~= step.seq and step.fx then
        facedSeq[z] = step.seq
        local fx, fy = A.at(k, step.fx, step.fy)
        U.try("crew.face", function() z:faceLocationF(fx + 0.5, fy + 0.5) end)
    end
end

function CC.update(z)
    local e = K.entry(z)
    if not e then return end
    local lookKey = e.id .. ":" .. tostring(e.sp) .. e.div
    if looked[z] ~= lookKey then
        looked[z] = lookKey
        CC.dress(z, e)
    end
    local step = e.step or {}
    U.try("crew.person", function()
        z:setVariable("TrekCrew", true)
        z:setVariable("TrekSit", step.k == "sit")
        -- On a copy this machine does not move, the walk shows from the
        -- step; the owner sets it from the route itself (walk()).
        if not owner(z) then z:setVariable("TrekMove", step.k == "walk") end
        z:setWalkType("TrekWalk")
        z:setTarget(nil)
        z:setNoTeeth(true)
        -- Useless keeps it from noticing anybody; on a server only while it
        -- stands still, which is when Bandits sets it (their MP notes).
        if not isClient() or step.k ~= "walk" then z:setUseless(true) end
    end)
    quiet(z)
    if owner(z) then carryOut(z, e) end
end

Events.OnZombieUpdate.Add(function(z)
    U.try("crew.update", CC.update, z)
end)

---------------------------------------------------------------------------
-- Speech
---------------------------------------------------------------------------
-- The crew's own colour: Starfleet blue-white, the comms "crew" voice.
CC.Colour = { 0.70, 0.86, 1.00 }

Net.onClient("crewSay", function(args)
    local z = K.findZombie(args.id)
    if not z then return end
    local text = U.try("crew.getText", function() return getText(args.k) end)
    if type(text) ~= "string" then return end
    text = K.fill(text, args.names)
    local c = CC.Colour
    U.try("crew.say", function() z:addLineChatElement(text, c[1], c[2], c[3]) end)
    CC.lastSaid = text
end)

Net.onClient("crewGone", function(args)
    if not isClient() then return end
    local z = K.findZombie(args.id)
    if not z then return end
    U.try("crew.goneLocal", function()
        z:removeFromWorld()
        z:removeFromSquare()
    end)
end)

return CC
