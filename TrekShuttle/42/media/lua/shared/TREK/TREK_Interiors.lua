--[[ Shuttlecraft -- whose cabin this is, and how it is laid out.

    Every ship has a cabin, and until 1.22 every cabin was the one in
    TREK_InteriorLayout.lua. Now a cabin is that plan **in a style, in an
    arrangement, with the amenities its server allows**, decided once and
    kept (SERVERS.md, *Cabins*):

      * **a style** is whose hands built it: Starfleet's, a Klingon's, a
        Vulcan's. It is a sheet's name and nothing else: every fitting of
        the cabin is a cell of the Adirondack's two sheets, and each other
        people's set has the same cell in the same place
        (tools/gen_species_tiles.py), with the Starfleet tile's properties
        (tools/gen_adirondack_pack.py). So a sink is a sink whoever built it,
        and everything that finds a fitting by its tag finds it;
      * **an arrangement** is which of the port bulkhead's four fittings
        stands where. They are four squares in a row, each worked from the
        passage beside it, so any order of them is a cabin somebody can use
        (tests/test_multiplayer.py walks all twenty-four). The bow bulkhead,
        the chair, the biobed, the pad and the three machines stay where the
        rest of the mod knows them to be;
      * **the amenities** are the galley, running water and the sick bay,
        each a sandbox switch.

    **It is rolled once, when a ship's cabin is first built, and kept in her
    state** (`s.cabin`): a cabin is lived in, and a setting changed later,
    a refit of her hull or another roll must not move the locker somebody
    filled. The Mechs mod's rule, from the other end: two ships of a kind are
    not the same ship (pz-mechs DESIGN.md 3.9), and one ship is always
    herself. A cabin that was standing before any of this is the standard
    one, Starfleet's, for good.

    Read by the server's builder (TREK_Build.lua) through `I.layout()`,
    which is the cabin of the ship in hand; nothing else needs to know.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Rules"
require "TREK/TREK_Vehicle"
local Base = require "TREK/TREK_InteriorLayout"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local R = TREK.Rules
local V = TREK.Vehicle

local I = {}
TREK.Interiors = I

-- The styles, in the order the sandbox numbers them after its first two
-- choices (*Her hull's*, *Any*). **Appended, never reordered.** `sheet` is
-- what stands in for "trek_adirondack" in a sprite's name; Starfleet's is
-- the Adirondack's own.
I.Styles = {
    { id = "starfleet", sheet = "trek_adirondack" },
    { id = "klingon",   sheet = "trek_klingon" },
    { id = "vulcan",    sheet = "trek_vulcan" },
}
I.styles = {}
for _, style in ipairs(I.Styles) do I.styles[style.id] = style end

-- Whose cabin a kind of ship has when the server says *her hull's*.
I.HullStyle = { shuttle = "starfleet", raider = "klingon", vulcan = "vulcan" }

I.STANDARD_SHEET = "trek_adirondack"
-- The port bulkhead's four squares, bow to stern: x = 0, y = 1 to 4.
I.WEST_X, I.WEST_Y0, I.WEST_SLOTS = 0, 1, 4
I.STANDARD_WEST = "1234"

-- What each amenity is, by the tags of the fittings that are it. With the
-- galley off the stasis unit and the range are not built and the cupboard
-- under the sink holds no rations; with water off the sink is a dry
-- cupboard; with the sick bay off its cabinet and the biobed are not built.
-- The Doctor, the replicator and the warp core are machines with settings
-- of their own.
I.GALLEY_TAGS = { fridge = true, oven = true }
I.MEDICAL_TAGS = { medical = true, biobed = true }
I.DRY_TAG = "cupboard"

---------------------------------------------------------------------------
-- The sandbox
---------------------------------------------------------------------------
I.StyleHull, I.StyleAny = 1, 2

--- *Cabin style*: 1 her hull's, 2 any, then one for each of I.Styles.
--- Absent is her hull's, which for a shuttle is the cabin as it always was.
function I.styleRule()
    return R.choice("CabinStyle", 2 + #I.Styles, I.StyleHull)
end

--- *Cabin layout*: 1 shuffled, 2 the standard one. **Absent is standard**,
--- which is the mod as designed; a new world's page says shuffled.
function I.shuffled()
    return R.choice("CabinLayout", 2, 2) == 1
end

function I.galley() return R.flag("CabinGalley") end
function I.water() return R.flag("CabinWater") end
function I.medical() return R.flag("CabinMedical") end

---------------------------------------------------------------------------
-- A cabin's record
---------------------------------------------------------------------------
--- A valid order of the port bulkhead: each of "1" to "4" once.
function I.validWest(west)
    if type(west) ~= "string" or #west ~= I.WEST_SLOTS then return false end
    local seen = {}
    for i = 1, I.WEST_SLOTS do
        local n = tonumber(west:sub(i, i))
        if not n or n < 1 or n > I.WEST_SLOTS or seen[n] then return false end
        seen[n] = true
    end
    return true
end

--- Rolls a ship's cabin: the server's rules, her hull, and the dice. `roll`
--- is ZombRand's shape, `roll(n)` answering 0 to n - 1.
function I.roll(s, roll)
    local rule = I.styleRule()
    local style
    if rule == I.StyleHull then
        style = I.HullStyle[V.hullOf(s).id] or I.Styles[1].id
    elseif rule == I.StyleAny then
        style = I.Styles[roll(#I.Styles) + 1].id
    else
        style = I.Styles[rule - 2].id
    end
    local west = I.STANDARD_WEST
    if I.shuffled() then
        -- A shuffle of four: each square takes one of what is left.
        local left, out = { "1", "2", "3", "4" }, {}
        while #left > 0 do
            out[#out + 1] = table.remove(left, roll(#left) + 1)
        end
        west = table.concat(out)
    end
    return { style = style, west = west, galley = I.galley(), water = I.water(), medical = I.medical() }
end

--- A cabin somebody with the say has asked for (SERVERS.md, *Rebuilding a
--- cabin*): this style, shuffled or standard, and the amenities the server
--- allows today. Nil for a style there is not.
function I.make(style, shuffle, roll)
    if not I.styles[style] then return nil end
    local west = I.STANDARD_WEST
    if shuffle then
        local left, out = { "1", "2", "3", "4" }, {}
        while #left > 0 do
            out[#out + 1] = table.remove(left, roll(#left) + 1)
        end
        west = table.concat(out)
    end
    return { style = style, west = west, galley = I.galley(), water = I.water(), medical = I.medical() }
end

--- The cabin a ship has, deciding it if nobody has. **The authority's, at
--- her first build.** A ship whose cabin was standing before there was a
--- choice has the standard one.
function I.ensure(s)
    if type(s.cabin) == "table" then return s.cabin end
    if s.built == true then
        s.cabin = { style = I.Styles[1].id, west = I.STANDARD_WEST, galley = true, water = true, medical = true }
    else
        s.cabin = I.roll(s, ZombRand)
    end
    U.log("cabin: ship %s's is %s, its port bulkhead in order %s, galley %s, water %s, sick bay %s",
          tostring(U.shipNow), tostring(s.cabin.style), tostring(s.cabin.west),
          tostring(s.cabin.galley), tostring(s.cabin.water), tostring(s.cabin.medical))
    return s.cabin
end

--- True for a record that is the cabin as TREK_InteriorLayout.lua has it.
local function standard(cabin)
    return cabin == nil
        or ((cabin.style == nil or cabin.style == I.Styles[1].id)
            and (cabin.west == nil or cabin.west == I.STANDARD_WEST)
            and cabin.galley ~= false and cabin.water ~= false and cabin.medical ~= false)
end

---------------------------------------------------------------------------
-- The plan
---------------------------------------------------------------------------
--- A sprite in a style: the same cell of that people's sheet. Anything that
--- is not the Adirondack's (Lt. Shepard's television) is nobody's but its own.
function I.sprite(style, name)
    local sheet = (I.styles[style] or I.Styles[1]).sheet
    if sheet == I.STANDARD_SHEET or type(name) ~= "string" then return name end
    if name:sub(1, #I.STANDARD_SHEET + 1) ~= I.STANDARD_SHEET .. "_" then return name end
    return sheet .. name:sub(#I.STANDARD_SHEET + 1)
end

local function copy(entry)
    local out = {}
    for k, v in pairs(entry) do out[k] = v end
    return out
end

--- The plan a record describes: the standard one's shape (`tiles`, `floor`,
--- `wallW`, `wallN`, `pad`, `legacy`), made new each time.
function I.plan(cabin)
    local style = cabin.style or I.Styles[1].id
    local west = I.validWest(cabin.west) and cabin.west or I.STANDARD_WEST
    -- Where the fitting the standard plan has at each square of the port
    -- bulkhead stands in this one.
    local goes = {}
    for slot = 1, I.WEST_SLOTS do
        goes[tonumber(west:sub(slot, slot))] = slot
    end
    local plan = {
        width = Base.width, height = Base.height, legacy = Base.legacy,
        floor = I.sprite(style, Base.floor), wallW = I.sprite(style, Base.wallW),
        wallN = I.sprite(style, Base.wallN), pad = I.sprite(style, C.Sprites.padFloor),
        tiles = {},
    }
    for _, entry in ipairs(Base.tiles) do
        local keep = true
        if cabin.galley == false and I.GALLEY_TAGS[entry.tag] then keep = false end
        if cabin.medical == false and I.MEDICAL_TAGS[entry.tag] then keep = false end
        if keep then
            local e = copy(entry)
            e.sprite = I.sprite(style, entry.sprite)
            if e.x == I.WEST_X and e.y >= I.WEST_Y0 and e.y < I.WEST_Y0 + I.WEST_SLOTS then
                e.y = I.WEST_Y0 + goes[e.y - I.WEST_Y0 + 1] - 1
            end
            if C.WaterTags[e.tag] then
                if cabin.galley == false then e.loot, e.special = nil, nil end
                if cabin.water == false then e.tag = I.DRY_TAG end
            end
            table.insert(plan.tiles, e)
        end
    end
    return plan
end

local plans = {}

--- The cabin of the ship in hand, as the builder reads it. The standard one
--- is TREK_InteriorLayout.lua itself, not a copy of it.
function I.layout()
    local s = U.state()
    local cabin = s and s.cabin
    -- (It names no pad: the builder reads Starfleet's from the config, live.)
    if standard(cabin) then return Base end
    local key = table.concat({ tostring(cabin.style), tostring(cabin.west), tostring(cabin.galley),
                               tostring(cabin.water), tostring(cabin.medical) }, "|")
    if not plans[key] then plans[key] = I.plan(cabin) end
    return plans[key]
end

--- Every floor a cabin of any style is laid with: a deck is known by its
--- sprite, and one of them is under somebody's feet (TREK_Build, isDeck).
function I.floors()
    local out = {}
    for _, style in ipairs(I.Styles) do
        out[I.sprite(style.id, Base.floor)] = true
        out[I.sprite(style.id, C.Sprites.padFloor)] = true
    end
    return out
end

return I
