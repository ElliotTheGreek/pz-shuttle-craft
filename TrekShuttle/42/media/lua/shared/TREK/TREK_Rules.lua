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
local C = TREK.Config

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
    if option == nil then return true end
    -- Sandbox *Aliens*: off is every species off at once (SERVERS.md, *Content*).
    return R.flag(option) and R.aliens()
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
    if R.SPECIES_OPTION[path] then return R.speciesAllowed(path) end
    local option = R.TRAIT_OPTION[path]
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
    local parts = { R.flag("SpeciesHuman") and "1" or "0", R.aliens() and "1" or "0" }
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
-- A distress call is one of the Adirondack's crew, heard and answered by a
-- shuttle: with either switched off there is nobody to hear or to bring home.
function R.distressCalls()
    return R.flag("DistressCalls") and R.shuttles() and R.adirondack()
end
function R.installations() return R.flag("Installations") end

-- Sandbox *Ship's weapons*: 1 torpedoes and phasers, 2 phasers only, 3 none.
function R.torpedoes() return R.choice("ShipWeapons", 3, 1) == 1 end
function R.shipPhasers() return R.choice("ShipWeapons", 3, 1) ~= 3 end

-- Sandbox *Power use*: what each unit asked for takes out of the store.
-- Double and four times were added after None, so a server's saved 1..4
-- still mean what they meant.
R.POWER_SCALE = { 1, 0.5, 0.25, 0, 2, 4 }
function R.powerScale()
    return R.POWER_SCALE[R.choice("PowerUse", #R.POWER_SCALE, 1)]
end

---------------------------------------------------------------------------
-- Content (SERVERS.md, *Content*)
---------------------------------------------------------------------------
-- The fourth sandbox page: what of the mod is in this world at all. Every
-- switch is on unless a server turned it off, and off stops what is new --
-- nothing a player already holds is taken from them.

--- Is there a shuttle on this server at all? Off: none is set down, none is
--- issued, nobody has her menu, and every command about her is refused.
--- Whoever is aboard one may always leave.
function R.shuttles() return R.flag("Shuttles") end
--- Is the ship in orbit there? Off: nobody boards her, she never calls, and
--- neither her distress calls nor her raids happen.
function R.adirondack() return R.flag("Adirondack") end
--- Is there a field station under Muldraugh?
function R.fieldStation() return R.flag("FieldStation") end
--- Are there aliens? Off: no species for a character, and no Borg among the
--- dead. What an alien made (a bat'leth) is an item, with its own switch.
function R.aliens() return R.flag("Aliens") end

-- item (full type) -> its switch. A weapon has its own; everything else is
-- switched by its family. An item with no row here (a crystal, a tape, the
-- story's own pieces) has no switch and is always allowed.
R.ITEM_OPTION = {
    ["TrekShuttle.TrekBatleth"] = "ItemBatleth",
    ["TrekShuttle.TrekMekleth"] = "ItemMekleth",
    ["TrekShuttle.TrekLirpa"] = "ItemLirpa",
    ["TrekShuttle.TrekUshaanTor"] = "ItemUshaanTor",
    ["TrekShuttle.TrekPhaser"] = "ItemPhaser",
    ["TrekShuttle.TrekPhaserRifle"] = "ItemPhaserRifle",
    ["TrekShuttle.TrekKlingonDisruptor"] = "ItemKlingonDisruptor",
    ["TrekShuttle.TrekKlingonRifle"] = "ItemKlingonRifle",
    ["TrekShuttle.TrekRomulanDisruptor"] = "ItemRomulanDisruptor",
    ["TrekShuttle.TrekPolaronRifle"] = "ItemPolaronRifle",
    ["TrekShuttle.TrekCardassianPhaser"] = "ItemCardassianPhaser",
    ["TrekShuttle.TrekSentry"] = "ItemSentry",
    ["TrekShuttle.TrekHypospray"] = "ItemsMedical",
    ["TrekShuttle.TrekDermalRegen"] = "ItemsMedical",
    ["TrekShuttle.TrekMedTricorder"] = "ItemsMedical",
    ["TrekShuttle.TrekTricorder"] = "ItemsInstruments",
    ["TrekShuttle.TrekPADD"] = "ItemsInstruments",
    ["TrekShuttle.TrekShoulderLamp"] = "ItemsInstruments",
    ["TrekShuttle.TrekUniformDutyCommand"] = "ItemsUniforms",
    ["TrekShuttle.TrekUniformDutyOperations"] = "ItemsUniforms",
    ["TrekShuttle.TrekUniformDutyScience"] = "ItemsUniforms",
    ["TrekShuttle.TrekUniformDressCommand"] = "ItemsUniforms",
    ["TrekShuttle.TrekUniformDressOperations"] = "ItemsUniforms",
    ["TrekShuttle.TrekUniformDressScience"] = "ItemsUniforms",
    ["TrekShuttle.TrekBackpack"] = "ItemsUniforms",
    ["TrekShuttle.TrekHolster"] = "ItemsUniforms",
    ["TrekShuttle.TrekFieldKit"] = "ItemsFieldKit",
    ["TrekShuttle.TrekSonicDriver"] = "ItemsFieldKit",
    ["TrekShuttle.TrekHyperspanner"] = "ItemsFieldKit",
    ["TrekShuttle.TrekStemBoltDriver"] = "ItemsFieldKit",
    ["TrekShuttle.TrekLaserCutter"] = "ItemsFieldKit",
    ["TrekShuttle.TrekLaserWelder"] = "ItemsFieldKit",
    ["TrekShuttle.TrekStemBolts"] = "ItemsFieldKit",
    ["TrekShuttle.TrekRationPack"] = "ItemsFood",
    ["TrekShuttle.TrekGagh"] = "ItemsFood",
    ["TrekShuttle.TrekLeolaStew"] = "ItemsFood",
    ["TrekShuttle.TrekPlomeekSoup"] = "ItemsFood",
    ["TrekShuttle.TrekJumjaStick"] = "ItemsFood",
    ["TrekShuttle.TrekAndorianTuber"] = "ItemsFood",
    ["TrekShuttle.TrekOskoid"] = "ItemsFood",
    ["TrekShuttle.TrekWingSlugRoll"] = "ItemsFood",
    ["TrekShuttle.TrekHasperat"] = "ItemsFood",
    ["TrekShuttle.TrekRokegPie"] = "ItemsFood",
    ["TrekShuttle.TrekChadrekab"] = "ItemsFood",
    ["TrekShuttle.TrekRaktajinoMug"] = "ItemsDrinks",
    ["TrekShuttle.TrekEarlGreyCup"] = "ItemsDrinks",
    ["TrekShuttle.TrekRomulanAle"] = "ItemsDrinks",
    ["TrekShuttle.TrekBloodwine"] = "ItemsDrinks",
    ["TrekShuttle.TrekAndorianAle"] = "ItemsDrinks",
    ["TrekShuttle.TrekBalsoTonic"] = "ItemsDrinks",
    ["TrekShuttle.TrekNutrientSuspension"] = "ItemsDrinks",
    ["TrekShuttle.TrekKetracelWhite"] = "ItemsContraband",
    ["TrekShuttle.TrekFelicium"] = "ItemsContraband",
    ["TrekShuttle.TrekTrelliumD"] = "ItemsContraband",
    ["TrekShuttle.TrekCordrazine"] = "ItemsContraband",
    ["TrekShuttle.TrekKtarianGame"] = "ItemsContraband",
    ["TrekShuttle.TrekLatinumStrip"] = "ItemsContraband",
    ["TrekShuttle.TrekKanar"] = "ItemsContraband",
    ["TrekShuttle.TrekSaurianBrandy"] = "ItemsContraband",
    ["TrekShuttle.TrekAldebaranWhiskey"] = "ItemsContraband",
    ["TrekShuttle.TrekTeaSeed"] = "ItemsFarming",
    ["TrekShuttle.TrekBergamotSeed"] = "ItemsFarming",
    ["TrekShuttle.TrekKlingonCoffeeSeed"] = "ItemsFarming",
    ["TrekShuttle.TrekPlomeekSeed"] = "ItemsFarming",
    ["TrekShuttle.TrekLeolaSeed"] = "ItemsFarming",
    ["TrekShuttle.TrekAndorianTuberSeed"] = "ItemsFarming",
    ["TrekShuttle.TrekHasperatSeed"] = "ItemsFarming",
    ["TrekShuttle.TrekWarpCoreKit"] = "ItemsKits",
    ["TrekShuttle.TrekReplicatorKit"] = "ItemsKits",
    ["TrekShuttle.TrekEMHKit"] = "ItemsKits",
}

--- May this server's world be given one of these? Asked wherever the mod
--- makes one: stocking a locker, the replicator, the world's loot.
function R.itemAllowed(id)
    local option = R.ITEM_OPTION[id]
    return option == nil or R.flag(option)
end

--- Every item switch in one string, so the replicator's catalogue can tell
--- when they change.
local itemSwitches = nil      -- every switch's name once, sorted
function R.itemSignature()
    -- Asked on every read of the catalogue, which a panel makes every frame:
    -- the names are worked out once, and this is one flag a switch.
    if not itemSwitches then
        local seen = {}
        itemSwitches = {}
        for _, option in pairs(R.ITEM_OPTION) do
            if not seen[option] then
                seen[option] = true
                table.insert(itemSwitches, option)
            end
        end
        table.sort(itemSwitches)
    end
    local parts = {}
    for i, option in ipairs(itemSwitches) do parts[i] = R.flag(option) and "1" or "0" end
    return table.concat(parts)
end

-- Sandbox *Items in the world's loot*, per cent: with no shuttle to issue
-- them, the chance a fitting container holds one (TREK_Salvage).
function R.itemLoot()
    return R.number("ItemLoot", 0, 100, C.Salvage.chance)
end

---------------------------------------------------------------------------
-- Balance (SERVERS.md, *Balance*)
---------------------------------------------------------------------------
-- The third sandbox page: how rare dilithium is and what everything costs.
-- The numbers in TREK_Config are the mod as designed; each of these is a
-- server's own answer in their place.

--- A number option, held to lo..hi. Absent, or not a number, is `default`.
function R.number(name, lo, hi, default)
    local v = tonumber(raw(name))
    if not v or v ~= v then return default end
    if v < lo then return lo end
    if v > hi then return hi end
    return v
end

-- price (a TREK_Config name) -> the percentage that scales it.
R.COST_OPTION = {
    BeamCost = "CostTransporter",
    LandCost = "CostFlight", RecallCost = "CostFlight", EngineStartCost = "CostFlight",
    TakeoffCost = "CostFlight", GroundCostPerTile = "CostFlight",
    AirCostPerTile = "CostFlight", HoverCostPerMinute = "CostFlight",
    ShieldPushCost = "CostShields", RepairCostPerPoint = "CostShields",
    TorpedoCost = "CostWeapons",
    EmhProjectCost = "CostMedical", EmhTreatCost = "CostMedical",
    EmhDetoxCost = "CostMedical", ScreenCost = "CostMedical",
    ProbeCost = "CostSystems", SentryRechargeCost = "CostSystems",
    AndroidChargeCost = "CostSystems", FuelToEnergy = "CostSystems",
}
-- The ones charged by the tile, the minute or the point: a fraction is paid
-- as a fraction. Every other price is on a button and is a whole number.
R.COST_RATE = {
    GroundCostPerTile = true, AirCostPerTile = true, HoverCostPerMinute = true,
    ShieldPushCost = true, RepairCostPerPoint = true, AndroidChargeCost = true,
    FuelToEnergy = true,
}
R.COST_MAX = 1000    -- per cent

--- What one of the cost percentages multiplies by: 1 as designed, 0 free.
function R.costScale(option)
    return R.number(option, 0, R.COST_MAX, 100) / 100
end

--- A whole price on this server: never under 1 unless the server made it
--- free. Not held under what a crystal holds: a price past that is one no
--- ship can pay, the ledger refuses it with its numbers, and a cap here
--- would be a discount nobody set.
function R.whole(units, scale)
    if scale <= 0 or units <= 0 then return 0 end
    local n = math.floor(units * scale + 0.5)
    if n < 1 then n = 1 end
    return n
end

--- What `name` (C.BeamCost, C.LandCost, ...) costs on this server. Both sides
--- ask here, so a menu shows the price the server will charge.
function R.cost(name)
    local base = C[name] or 0
    local scale = R.costScale(R.COST_OPTION[name])
    if R.COST_RATE[name] then return base * scale end
    return R.whole(base, scale)
end

-- Sandbox *Dilithium in a town's loot*: the fewest and the most crystals the
-- containers of one district give up (TREK_Lode).
function R.lootCrystals()
    local lo = math.floor(R.number("LootDilithiumMin", 0, 50, C.LootCrystalsMin))
    local hi = math.floor(R.number("LootDilithiumMax", 0, 50, C.LootCrystalsMax))
    if hi < lo then lo, hi = hi, lo end
    return lo, hi
end

-- Sandbox *Dilithium in the wild*: one plot in this many holds a crystal,
-- or nil for none. Very rare was added after None (TREK_Wild).
function R.wildOneIn()
    local v = R.choice("WildDilithium", 4, C.WildVeryRare)
    if v == C.WildNone then return nil end
    if v == C.WildPlentiful then return C.WildPlentifulOneIn end
    if v == C.WildScarce then return C.WildScarceOneIn end
    return C.WildVeryRareOneIn
end

-- Sandbox *Probes that find dilithium*, 0..1.
function R.probeFind()
    return R.number("ProbeFind", 0, 100, C.ProbeFindChance * 100) / 100
end

--- How many empty probes in a row before the next one must find something,
--- or nil for no such promise. C.ProbeDryLimit is the wait at the nine in ten
--- it was set for; it stretches as the server makes a find rarer, so the
--- promise never hands out more than the setting allows.
function R.probeDryLimit()
    local p = R.probeFind()
    if p <= 0 then return nil end
    return math.ceil(C.ProbeDryLimit * 0.9 / p - 1e-9)
end

-- Sandbox *Raid crates with a crystal*, per cent.
function R.raidCrystal()
    return R.number("RaidCrystal", 0, 100, C.RaidCrystalChance)
end

-- Sandbox *Spare crystals at a commissioned start*.
function R.startCrystals()
    return math.floor(R.number("StartCrystals", 0, 10, C.DilithiumIssue))
end

-- Sandbox *Crystals a cure costs* and *Hours a cure takes* (EMH.md).
function R.cureCrystals()
    return math.floor(R.number("CureCrystals", 0, 5, C.EmhCureCrystals))
end
function R.cureHours()
    return R.number("CureHours", 1, 168, C.EmhCureHours)
end

---------------------------------------------------------------------------
-- Who has what
---------------------------------------------------------------------------
-- Sandbox *Personal shuttles*: 1 none, 2 every player, 3 listed players.
R.PersonalNone, R.PersonalEveryone, R.PersonalListed = 1, 2, 3
function R.personalMode() return R.choice("PersonalShuttles", 3, R.PersonalNone) end

--- Does this username have a shuttle of their own?
function R.hasPersonalShuttle(username)
    if not R.shuttles() then return false end
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
