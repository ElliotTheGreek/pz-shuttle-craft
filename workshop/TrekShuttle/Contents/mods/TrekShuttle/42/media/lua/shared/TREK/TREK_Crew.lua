--[[ Shuttlecraft -- the Adirondack's crew: who they are and where they go.

    Shared by both halves (CREW.md). The server decides everything -- who
    comes aboard a deck, where they walk, what they say -- and keeps it in the
    `TREK_Crew` mod data. Every client reads that to dress them and draw their
    speech. The client that simulates a crew member (build 42 hands each zombie
    to one client) walks and seats them.

    **They are zombies underneath**, as Bandits' and Week One's people are: the
    only walking, animated body the engine will give a mod. This file is the
    part that does not care: the roster, the spots on each deck, and how a crew
    member is found by id on either side of the wire.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Adirondack"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local A = TREK.Adirondack
local L = A.Layout

local K = {}
TREK.Crew = K

K.StateKey = "TREK_Crew"
-- The outfit they are spawned in: nothing but a name every client can see
-- (common/media/clothing/clothing.xml). Their clothes are item visuals each
-- client puts on them (TREK_CrewClient), because a zombie's packet carries its
-- outfit id and nothing else.
K.Outfit = "TrekCrewBase"

-- How many are about on a deck while somebody is on it.
K.Population = { 6, 8, 5, 6, 4 }

---------------------------------------------------------------------------
-- Who they are
---------------------------------------------------------------------------
K.Uniform = {
    command = "TrekShuttle.TrekUniformDutyCommand",
    operations = "TrekShuttle.TrekUniformDutyOperations",
    sciences = "TrekShuttle.TrekUniformDutyScience",
}
K.Shoes = "Base.Shoes_Black"

-- Species, weighted: a human-majority Starfleet ship. false is human (a nil
-- here would leave the length of the entry undefined). The ids
-- are TREK_Traits' species paths, which TREK.Looks.dress knows.
K.Species = {
    { false, 30 }, { "vulcan", 5 }, { "andorian", 4 }, { "betazoid", 4 }, { "trill", 4 },
    { "bajoran", 4 }, { "klingon", 3 }, { "talaxian", 2 }, { "exborg", 1 },
}

K.Surnames = {
    human = { "Vance", "Tamura", "Reyes", "Lindqvist", "Haddad", "Castellan", "Achebe",
              "Moreau", "Sato", "Brennan", "Kowalczyk", "Ferreira", "Okonkwo", "Marsh",
              "Delacroix", "Yilmaz", "Petrov", "Nakamura", "Quinn", "Abara", "Holt",
              "Varga", "Mbeki", "Sorensen", "Iyer", "Carvalho", "Walsh", "Adeyemi" },
    vulcan = { "Sorak", "Tavek", "Selok", "Stovan", "Sital", "Voras" },
    vulcanF = { "T'Mira", "T'Vessa", "T'Rel", "T'Sai" },
    andorian = { "th'Vessek", "sh'Rani", "ch'Talas", "zh'Onri", "th'Kellan" },
    klingon = { "Korvath", "Mogren", "Dakar", "Vorgath", "Kelsa", "Tagrin" },
    bajoran = { "Anora", "Kesh", "Tobren", "Relin", "Varis", "Jalen" },
    betazoid = { "Lorin", "Enaya", "Deshi", "Varro", "Minara" },
    trill = { "Kell", "Vorr", "Jaxa", "Tarel", "Sirri" },
    talaxian = { "Mirrek", "Tolun", "Pelik" },
    exborg = { "Marsh", "Harrow", "Lund", "Okoye" },
}

-- Divisions and jobs by deck (Deck 1 first), weighted.
K.Jobs = {
    { { "command", "helm", 4 }, { "command", "command", 3 }, { "sciences", "sciences", 3 },
      { "operations", "security", 2 } },
    { { "operations", "operations", 3 }, { "sciences", "sciences", 2 }, { "command", "command", 1 },
      { "operations", "engineer", 1 }, { "sciences", "medical", 1 }, { "operations", "security", 1 } },
    { { "sciences", "medical", 5 }, { "operations", "operations", 3 }, { "sciences", "sciences", 2 },
      { "operations", "security", 1 } },
    { { "operations", "engineer", 6 }, { "operations", "operations", 2 }, { "sciences", "sciences", 1 },
      { "command", "command", 1 } },
    -- Deck 5, hydroponics: botanists, and somebody from the galley.
    { { "sciences", "sciences", 5 }, { "operations", "operations", 2 }, { "sciences", "medical", 1 } },
}

K.Ranks = { { "Crewman", 4 }, { "Ensign", 5 }, { "Lieutenant", 3 }, { "Petty Officer", 2 },
            { "Chief", 1 } }

K.MaleHair = { "Short", "CrewCut", "Fresh", "LeftParting", "RightParting", "CentreParting",
               "Baldspot", "Recede", "Bald", "Picard", "Messy", "GreasedBack" }
K.FemaleHair = { "Bob", "Bun", "PonyTail", "Kate", "CentreParting", "Long", "Rachel",
                 "ShortCurly", "LeftParting", "Back", "Braids" }
K.Beards = { "", "", "", "", "Chin", "Goatee", "Full", "Moustache" }
K.HairColours = { { 0.10, 0.08, 0.06 }, { 0.30, 0.20, 0.12 }, { 0.55, 0.38, 0.20 },
                  { 0.80, 0.65, 0.40 }, { 0.62, 0.25, 0.10 }, { 0.55, 0.55, 0.55 },
                  { 0.05, 0.05, 0.05 } }

local function pick(list, rnd)
    return list[rnd(#list) + 1]
end

local function weighted(list, rnd, w)
    w = w or function(e) return e[#e] end
    local total = 0
    for _, e in ipairs(list) do total = total + w(e) end
    local r = rnd(1000) / 1000 * total
    for _, e in ipairs(list) do
        r = r - w(e)
        if r <= 0 then return e end
    end
    return list[#list]
end

local function zr(n) return ZombRand(n) end

--- A new crew member for deck k: everything a client needs to dress them and
--- a speaker needs to name them.
function K.newMember(k, female, rnd)
    rnd = rnd or zr
    local sp = weighted(K.Species, rnd)[1] or nil
    local job = weighted(K.Jobs[k] or K.Jobs[2], rnd)
    local div, role = job[1], job[2]
    local names = K.Surnames[sp or "human"] or K.Surnames.human
    if sp == "vulcan" and female then names = K.Surnames.vulcanF end
    local surname = pick(names, rnd)
    local rank = weighted(K.Ranks, rnd)[1]
    if role == "medical" then rank = (rnd(3) == 0) and "Doctor" or "Nurse" end
    if role == "engineer" and rnd(4) == 0 then rank = "Chief" end
    return {
        deck = k, div = div, job = role, sp = sp or false, f = female == true,
        name = rank .. " " .. surname,
        skin = rnd(5) + 1,
        hair = female and pick(K.FemaleHair, rnd) or pick(K.MaleHair, rnd),
        beard = female and "" or pick(K.Beards, rnd),
        hc = rnd(#K.HairColours) + 1,
    }
end

--- True when a crew member can play a role that needs `req` (CREW.md 4.1).
function K.fits(req, m)
    if req == "any" then return true end
    if req == "command" or req == "operations" or req == "sciences" then return m.div == req end
    if req == "medical" then return m.job == "medical" end
    if req == "engineer" then return m.job == "engineer" end
    if req == "security" then return m.job == "security" end
    if req == "helm" then return m.job == "helm" end
    return false
end

---------------------------------------------------------------------------
-- Finding one
---------------------------------------------------------------------------
--- A crew member's id: the zombie's online id on a server and its clients
--- (the one number both sides share for it), a counter in its mod data in
--- single player, where there is only one copy.
function K.id(z)
    if not z then return nil end
    if isClient() or isServer() then
        local id = U.try("crew.onlineID", function() return z:getOnlineID() end)
        if id and id >= 0 then return id end
        return nil
    end
    return U.try("crew.md", function() return z:getModData().TREKCrew end)
end

function K.state()
    local s = ModData.getOrCreate(K.StateKey)
    s.crew = s.crew or {}
    return s
end

--- True when a body stands anywhere on the Adirondack: the cheap test that
--- comes before anything else, because OnZombieUpdate runs for every zombie
--- in the loaded world and nearly all of them are in Kentucky.
function K.aboard(z)
    local ok, k = pcall(function() return A.locate(z:getX(), z:getY()) end)
    return ok and k ~= nil
end

--- The entry for a zombie, or nil for an ordinary one.
function K.entry(z)
    if not z or not K.aboard(z) then return nil end
    local id = K.id(z)
    if id == nil then return nil end
    return K.state().crew[tostring(id)], id
end

function K.findZombie(id)
    local found = nil
    U.try("crew.find", function()
        local list = getCell():getZombieList()
        for i = 0, list:size() - 1 do
            local z = list:get(i)
            if tostring(K.id(z)) == tostring(id) then found = z return end
        end
    end)
    return found
end

---------------------------------------------------------------------------
-- Where they go
---------------------------------------------------------------------------
-- Pieces somebody stands in front of to work at, and pieces somebody sits in.
K.Work = {
    helm_console = true, science_station = true, science_display = true, tactical_rail = true,
    engineering_console = true, master_systems = true, warp_core = true, transporter_console = true,
    medical_cabinet = true, medical_cart = true, biobed = true, galley_counter = true,
    bar_straight = true, bottle_shelf = true, stasis_unit = true, replicator = true,
    display_shelf = true, wardrobe = true, cargo_crate = true, desk = true, ready_room_desk = true,
}
K.Seats = {
    captain_chair = true, bridge_chair = true, desk_chair = true, lounge_chair = true,
    bar_stool = true, armchair = true, sofa = true,
}
-- Where on its square a sitter goes, by the seat's Facing: Week One's
-- numbers for vanilla chairs (ZASitInChair).
K.SitOffset = { S = { 0.4, 0.8 }, N = { 0.5, 0.2 }, E = { 0.8, 0.4 }, W = { 0.2, 0.5 } }
local STEP = { E = { 1, 0 }, W = { -1, 0 }, S = { 0, 1 }, N = { 0, -1 } }

--- The place tag (CREW.md 4.1) of a deck square: bridge, sickbay...
function K.placeAt(k, lx, ly)
    local r = A.roomAt(k, lx, ly)
    return r and r.place or nil
end

local spots = {}
local busyMap = {}

--- Squares with a piece of furniture on them, on deck k: "x,y" -> true.
function K.busy(k)
    if busyMap[k] then return busyMap[k] end
    local busy = {}
    for _, o in ipairs(L.decks[k].objects) do
        if o[4] ~= "w" and o[4] ~= "dW" and o[4] ~= "dN" then busy[o[1] .. "," .. o[2]] = true end
    end
    busyMap[k] = busy
    return busy
end

--- An open square inside the ship next to lx, ly on deck k, avoiding `taken`
--- ("x,y" -> true): where somebody walks to when they come over to talk.
function K.freeNear(k, lx, ly, taken)
    local busy = K.busy(k)
    for r = 1, 2 do
        for dx = -r, r do
            for dy = -r, r do
                local x, y = lx + dx, ly + dy
                local key = x .. "," .. y
                if (dx ~= 0 or dy ~= 0) and not busy[key] and not (taken and taken[key])
                   and A.inside(k, x, y) then
                    return x, y
                end
            end
        end
    end
    return nil
end

--- Every spot on deck k a crew member can go to: { kind = "sit"|"stand",
--- x, y (deck squares), fx, fy (a square to face), face (a Facing), place }.
function K.spots(k)
    if spots[k] then return spots[k] end
    local deck = L.decks[k]
    local busy = K.busy(k)
    local out = {}
    local seen = {}
    local function add(s)
        local key = s.kind .. s.x .. "," .. s.y
        if seen[key] or not A.inside(k, s.x, s.y) then return end
        seen[key] = true
        s.place = K.placeAt(k, s.x, s.y)
        table.insert(out, s)
    end
    for _, o in ipairs(deck.objects) do
        local piece, face = o[5], o[6]
        if piece and face then
            if K.Seats[piece] then
                -- A seat faces away from where it backs on; face the square it looks at.
                local st = STEP[face] or { 0, 1 }
                add({ kind = "sit", x = o[1], y = o[2], face = face,
                      fx = o[1] + st[1] * 3, fy = o[2] + st[2] * 3 })
            elseif K.Work[piece] then
                local st = STEP[face] or { 0, 1 }
                local sx, sy = o[1] + st[1], o[2] + st[2]
                if not busy[sx .. "," .. sy] then
                    add({ kind = "stand", x = sx, y = sy, fx = o[1], fy = o[2] })
                end
            end
        end
    end
    -- And somewhere to simply stand in every room: every few squares of open floor.
    for ly = 1, L.H - 2, 3 do
        for lx = 1, L.W - 2, 3 do
            if not busy[lx .. "," .. ly] and A.inside(k, lx, ly) then
                local r = A.roomAt(k, lx, ly)
                if r and r.place ~= "lift" then
                    add({ kind = "stand", x = lx, y = ly, fx = lx + 1, fy = ly + 1 })
                end
            end
        end
    end
    -- Only spots somebody can actually walk to from the lift: a corner boxed
    -- in by furniture is a post nobody would ever reach.
    local reachable = {}
    for _, sp in ipairs(out) do
        if K.route(k, L.lift.x, L.lift.y, sp.x, sp.y) then table.insert(reachable, sp) end
    end
    spots[k] = reachable
    return reachable
end

--- A lift car square on deck k to come aboard at and leave by.
function K.liftSquare(k, rnd)
    rnd = rnd or zr
    local lx = L.lift.x0 + rnd(L.lift.x1 - L.lift.x0 + 1)
    local ly = L.lift.y0 + rnd(L.lift.y1 - L.lift.y0 + 1)
    return lx, ly
end

---------------------------------------------------------------------------
-- Finding the way
---------------------------------------------------------------------------
-- **Our own route, not the engine's pathfinder.** The first play-test had
-- every crew member standing in the lift car for ever: the engine's path
-- finder has nothing to go on over decks raised at runtime five storeys up,
-- behind shut sliding doors, and never found a way out. The deck plan is
-- ours and complete -- which squares are in which room, and where every
-- doorway is -- so the route is worked out from that, and the owner walks
-- them along it (TREK_CrewClient).
--
-- A step between two squares is open when both are inside the ship and they
-- are the same room, or a doorway joins them. Furniture is walked round,
-- except at either end of the route (a seat is where you are going).

local doorEdges = {}

local function edgeKey(ax, ay, bx, by)
    if ax > bx or (ax == bx and ay > by) then ax, ay, bx, by = bx, by, ax, ay end
    return ax .. "," .. ay .. ">" .. bx .. "," .. by
end

local function doors(k)
    if doorEdges[k] then return doorEdges[k] end
    local out = {}
    for _, o in ipairs(L.decks[k].objects) do
        if o[4] == "dW" then out[edgeKey(o[1] - 1, o[2], o[1], o[2])] = true end
        if o[4] == "dN" then out[edgeKey(o[1], o[2] - 1, o[1], o[2])] = true end
    end
    doorEdges[k] = out
    return out
end

local function roomId(k, x, y)
    local deck = L.decks[k]
    if x < 0 or y < 0 or x >= L.W or y >= L.H then return 0 end
    return deck.grid[y + 1][x + 1] or 0
end

--- True when one can step from a to b (neighbours, orthogonal or diagonal).
function K.canStep(k, ax, ay, bx, by)
    local ra, rb = roomId(k, ax, ay), roomId(k, bx, by)
    if ra == 0 or rb == 0 then return false end
    if ax ~= bx and ay ~= by then
        -- Diagonal: only within one room, and only past two open corners.
        return ra == rb and roomId(k, ax, by) == ra and roomId(k, bx, ay) == ra
    end
    return ra == rb or doors(k)[edgeKey(ax, ay, bx, by)] == true
end

local NEIGHBOURS = { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 },
                     { 1, 1 }, { 1, -1 }, { -1, 1 }, { -1, -1 } }

--- The squares from (sx, sy) to (tx, ty) on deck k, not counting the start,
--- or nil when there is no way. Breadth first over at most a deck.
function K.route(k, sx, sy, tx, ty)
    if sx == tx and sy == ty then return {} end
    local busy = K.busy(k)
    local key = function(x, y) return x .. "," .. y end
    local from = { [key(sx, sy)] = false }
    local queue, head = { { sx, sy } }, 1
    while queue[head] do
        local cx, cy = queue[head][1], queue[head][2]
        head = head + 1
        if cx == tx and cy == ty then
            local out, k2 = {}, key(tx, ty)
            local cur = { tx, ty }
            while cur do
                table.insert(out, 1, cur)
                local prev = from[key(cur[1], cur[2])]
                if not prev or (prev[1] == sx and prev[2] == sy) then break end
                cur = prev
            end
            return out
        end
        for _, d in ipairs(NEIGHBOURS) do
            local nx, ny = cx + d[1], cy + d[2]
            local nk = key(nx, ny)
            if from[nk] == nil and K.canStep(k, cx, cy, nx, ny)
               and (not busy[nk] or (nx == tx and ny == ty)) then
                -- A diagonal past a piece of furniture would clip it.
                local clear = d[1] == 0 or d[2] == 0
                    or (not busy[key(cx + d[1], cy)] and not busy[key(cx, cy + d[2])])
                if clear then
                    from[nk] = { cx, cy }
                    table.insert(queue, { nx, ny })
                end
            end
        end
    end
    return nil
end

-- Walking pace, squares a second: an unhurried crewman.
K.WalkSpeed = 1.15

---------------------------------------------------------------------------
-- The talk
---------------------------------------------------------------------------
--- Replaces {role} in a line with the names the server sent.
function K.fill(text, names)
    if not text or not names then return text end
    return (text:gsub("{([%w_]+)}", function(role)
        return names[role] or ("{" .. role .. "}")
    end))
end

--- What a crew member is called by the person talking to them: "Ensign
--- Tamura", or "Doctor" for the doctor now and then.
function K.address(m)
    return m.name
end

--- True for a crew body on this machine: an entry on the clients, the
--- server's own mark on the server.
function K.isCrew(z)
    if K.entry(z) then return true end
    local md = U.try("crew.isMd", function() return z:getModData() end)
    return md ~= nil and (md.TREKCrewServer == true or md.TREKCrew ~= nil)
end

-- **A hit does nothing to them.** IsoZombie.Hit fires OnHitZombie before
-- IsoGameCharacter.Hit, which checks avoidDamage first and clears it: so
-- setting it here cancels each hit, on whichever side computes it. A shove
-- still staggers them; they get up. (Zombies cannot be made invulnerable:
-- setGodMod needs a role capability only players have.)
Events.OnHitZombie.Add(function(z)
    if z and K.isCrew(z) then
        U.try("crew.avoid", function() z:setAvoidDamage(true) end)
    end
end)

return K
