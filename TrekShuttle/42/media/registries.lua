--[[ Shuttlecraft -- registered ids (TRAITS.md 2.1).

    Build 42.13 and later make a trait, a profession and a body location a
    namespaced id in a registry, and a script block that names an id nobody
    registered fails to load. The engine runs this file for every enabled mod
    before any script or Lua loads (ModRegistries.init: <versionDir>/media/
    registries.lua), so it holds registrations and nothing else.

    **Every path here is unique to this mod, not only the namespace.** Two
    engine lookups drop the namespace: a trait's icon is
    media/ui/Traits/trait_<path>.png, and a profession's creation-screen
    clothing is ClothingSelectionDefinitions[<path>]. `trek:engineer` would
    have borrowed vanilla's engineer outfits; `trek:starfleet_engineer` cannot.
]]

TREK_Registries = TREK_Registries or {}
local R = TREK_Registries

local function traits(list)
    local out = {}
    for _, path in ipairs(list) do
        out[path] = CharacterTrait.register("trek:" .. path)
    end
    return out
end

R.Traits = traits({
    -- Species (TRAITS.md 3.1). A character with none is human.
    "vulcan", "klingon", "andorian", "betazoid", "trill", "bajoran",
    "talaxian", "orion", "android", "exborg",
    -- Anyone may take these (3.4).
    "transporterphobia", "realfoodonly", "spacesick", "starfleetacademy",
    "holohistorian", "turboliftphobia",
    -- What a Starfleet profession carries (3.2). Profession traits: never in
    -- the pickable lists.
    "sf_command", "sf_helm", "sf_engineering", "sf_security", "sf_medical",
    "sf_science", "sf_survey",
    -- Rank (3.3): added and removed by the server, never picked.
    "rank_ensign", "rank_ltjg", "rank_lt", "rank_ltcmdr", "rank_cmdr",
})

R.Professions = {}
for _, path in ipairs({ "starfleet_command", "starfleet_helm",
                        "starfleet_engineer", "starfleet_security",
                        "starfleet_medical", "starfleet_science",
                        "survey_specialist" }) do
    R.Professions[path] = CharacterProfession.register("trek:" .. path)
end
