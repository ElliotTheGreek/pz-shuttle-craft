--[[ Shuttlecraft -- the server's rules (SERVERS.md).

    What a server owner has decided on the two sandbox pages, read in one
    place. Everything here is a question with a yes, a number or a name for an
    answer; nothing here changes anything. The authority asks before it acts
    (TREK_Server, TREK_TraitsServer) and a client asks before it offers
    (TREK_Menu, TREK_CreationRules), from the same function, so the menu and
    the refusal cannot disagree.

    **An absent option is the mod as designed, never a feature switched off.**
    A world made before an option existed has no value for it, and so does a
    process that has not been sent the sandbox yet. Reading "missing" as "off"
    is how a feature turns itself off in the one setup nobody tested
    (TREK_Server, S.torpedoesBurn).

    Every process reads the same SandboxVars, so no packet says what a rule
    is (MULTIPLAYER.md, the hover height).
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}

local R = {}
TREK.Rules = R

---------------------------------------------------------------------------
-- Reading the sandbox
---------------------------------------------------------------------------
local function raw(name)
    local ok, v = pcall(function()
        return SandboxVars.TrekShuttle and SandboxVars.TrekShuttle[name]
    end)
    if ok then return v end
    return nil
end

--- A yes/no option. Absent is yes.
function R.flag(name)
    return raw(name) ~= false
end

--- A numbered choice, 1..count. Absent or out of range is `default`.
function R.choice(name, count, default)
    local v = tonumber(raw(name))
    if not v then return default end
    v = math.floor(v)
    if v < 1 or v > count then return default end
    return v
end

local function trim(text)
    return (tostring(text or ""):gsub("^%s+", ""):gsub("%s+$", ""))
end

--- A line of text. Absent or blank is `default`.
function R.text(name, default)
    local v = raw(name)
    if type(v) ~= "string" then return default end
    v = trim(v)
    if v == "" then return default end
    return v
end

-- option name -> { raw = the string it was parsed from, set = { name = true } }
local lists = {}

--- The usernames an option holds, as a set of lower-case names. Separated by
--- semicolons or commas; spaces round a name are dropped. Parsed once per
--- value: an admin may change the option while the server runs.
function R.names(name)
    local text = raw(name)
    if type(text) ~= "string" then text = "" end
    local cached = lists[name]
    if cached and cached.raw == text then return cached.set, cached.count end
    local set, count = {}, 0
    for part in text:gmatch("[^;,]+") do
        local who = string.lower(trim(part))
        if who ~= "" and not set[who] then
            set[who] = true
            count = count + 1
        end
    end
    lists[name] = { raw = text, set = set, count = count }
    return set, count
end

--- True when `username` is one of an option's names. Case does not matter.
function R.listed(name, username)
    if type(username) ~= "string" then return false end
    local set = R.names(name)
    return set[string.lower(username)] == true
end

---------------------------------------------------------------------------
-- Species, traits and professions (TRAITS.md)
---------------------------------------------------------------------------
-- trait path (media/registries.lua) -> its option.
R.SPECIES_OPTION = {
    vulcan = "SpeciesVulcan", klingon = "SpeciesKlingon", andorian = "SpeciesAndorian",
    betazoid = "SpeciesBetazoid", trill = "SpeciesTrill", bajoran = "SpeciesBajoran",
    talaxian = "SpeciesTalaxian", orion = "SpeciesOrion", android = "SpeciesAndroid",
    exborg = "SpeciesExBorg",
}
R.TRAIT_OPTION = {
    transporterphobia = "TraitTransporterPhobia", realfoodonly = "TraitRealFoodOnly",
    spacesick = "TraitSpacesick", starfleetacademy = "TraitStarfleetAcademy",
    holohistorian = "TraitHoloHistorian", turboliftphobia = "TraitTurboliftPhobia",
}
-- profession path -> { its option, the division trait only it grants }.
R.PROFESSION_OPTION = {
    starfleet_command  = { "ProfessionCommand",  "sf_command" },
    starfleet_helm     = { "ProfessionHelm",     "sf_helm" },
    starfleet_engineer = { "ProfessionEngineer", "sf_engineering" },
    starfleet_security = { "ProfessionSecurity", "sf_security" },
    starfleet_medical  = { "ProfessionMedical",  "sf_medical" },
    starfleet_science  = { "ProfessionScience",  "sf_science" },
    survey_specialist  = { "ProfessionSurvey",   "sf_survey" },
}
-- The same, by the division trait.
R.DIVISION_OPTION = {}
for _, pair in pairs(R.PROFESSION_OPTION) do R.DIVISION_OPTION[pair[2]] = pair[1] end

--- May a character be this species?
function R.speciesAllowed(path)
    local option = R.SPECIES_OPTION[path]
    return option == nil or R.flag(option)
end

--- The species a character may be, in the roster's own order.
function R.allowedSpecies()
    local out = {}
    local T = TREK.Traits
    for _, path in ipairs(T and T.SPECIES or {}) do
        if R.speciesAllowed(path) then table.insert(out, path) end
    end
    return out
end

--- May a character have no species at all? Always yes when every species is
--- switched off: a rule nobody can meet is not a rule.
function R.humansAllowed()
    if R.flag("SpeciesHuman") then return true end
    return #R.allowedSpecies() == 0
end

--- May a character have this trait? True for anything that is not one of
--- the mod's pickable ones: rank and the division traits follow the
--- profession and the rescues.
function R.traitAllowed(path)
    local option = R.SPECIES_OPTION[path] or R.TRAIT_OPTION[path]
    return option == nil or R.flag(option)
end

function R.professionAllowed(path)
    local pair = R.PROFESSION_OPTION[path]
    return pair == nil or R.flag(pair[1])
end

--- May a character hold this division's trait (sf_command, ...)?
function R.divisionAllowed(path)
    local option = R.DIVISION_OPTION[path]
    return option == nil or R.flag(option)
end

--- Every creation rule in one string, so a screen can tell when they change.
function R.creationSignature()
    local parts = { R.flag("SpeciesHuman") and "1" or "0" }
    local function add(map)
        local names = {}
        for path in pairs(map) do table.insert(names, path) end
        table.sort(names)
        for _, path in ipairs(names) do
            local option = map[path]
            if type(option) == "table" then option = option[1] end
            table.insert(parts, R.flag(option) and "1" or "0")
        end
    end
    add(R.SPECIES_OPTION)
    add(R.TRAIT_OPTION)
    add(R.PROFESSION_OPTION)
    return table.concat(parts)
end

---------------------------------------------------------------------------
-- What the ship may do
---------------------------------------------------------------------------
function R.beamUp() return R.flag("BeamUp") end
function R.flight() return R.flag("Flight") end
function R.shields() return R.flag("Shields") end
function R.distressCalls() return R.flag("DistressCalls") end
function R.installations() return R.flag("Installations") end

-- Sandbox *Ship's weapons*: 1 torpedoes and phasers, 2 phasers only, 3 none.
function R.torpedoes() return R.choice("ShipWeapons", 3, 1) == 1 end
function R.shipPhasers() return R.choice("ShipWeapons", 3, 1) ~= 3 end

-- Sandbox *Power use*: what each unit asked for takes out of the store.
R.POWER_SCALE = { 1, 0.5, 0.25, 0 }
function R.powerScale()
    return R.POWER_SCALE[R.choice("PowerUse", 4, 1)]
end

---------------------------------------------------------------------------
-- Who has what
---------------------------------------------------------------------------
-- Sandbox *Personal shuttles*: 1 none, 2 every player, 3 listed players.
R.PersonalNone, R.PersonalEveryone, R.PersonalListed = 1, 2, 3
function R.personalMode() return R.choice("PersonalShuttles", 3, R.PersonalNone) end

--- Does this username have a shuttle of their own?
function R.hasPersonalShuttle(username)
    local mode = R.personalMode()
    if mode == R.PersonalEveryone then return type(username) == "string" and username ~= "" end
    if mode == R.PersonalListed then return R.listed("PersonalShuttleUsers", username) end
    return false
end

--- May this username board the ship in orbit at all? An empty list is
--- everybody; the clearance (ACCESS.md) is asked as well, afterwards.
function R.adirondackListed(username)
    local _, count = R.names("AdirondackUsers")
    if count == 0 then return true end
    return R.listed("AdirondackUsers", username)
end

---------------------------------------------------------------------------
-- What things are called
---------------------------------------------------------------------------
R.SHIP_NAME = "Adirondack"

--- The ship in orbit's name on this server.
function R.shipName()
    return R.text("AdirondackName", R.SHIP_NAME)
end

--- `text` with the ship in orbit's name put in. Only her name as written in
--- the mod's own text; a server that keeps the name pays for one comparison.
function R.named(text)
    if type(text) ~= "string" then return text end
    local name = R.shipName()
    if name == R.SHIP_NAME then return text end
    -- A function, so a "%" in the server's name is not a capture reference.
    local out = text:gsub(R.SHIP_NAME, function() return name end)
    out = out:gsub("ADIRONDACK", function() return string.upper(name) end)
    return out
end

return R
