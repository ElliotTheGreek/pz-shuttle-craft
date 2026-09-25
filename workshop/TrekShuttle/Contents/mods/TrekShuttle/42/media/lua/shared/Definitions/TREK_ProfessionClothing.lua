--[[ Shuttlecraft -- what a Starfleet profession may wear on the creation
    screen (TRAITS.md 3.2).

    CharacterCreationMain reads ClothingSelectionDefinitions[<profession
    path>] -- the id without its namespace -- and offers each item under its
    body location. `Boilersuit` and `FullSuit` are the locations the duty and
    dress uniforms are built on (UNIFORMS.md), and vanilla already labels
    them ("Coveralls", "Full Body").

    The keys are the profession paths registered in media/registries.lua,
    which are unique to this mod for exactly this reason: `engineer` would
    have been vanilla's.
]]

ClothingSelectionDefinitions = ClothingSelectionDefinitions or {}

local DIVISION = {
    starfleet_command  = "Command",
    starfleet_helm     = "Command",
    starfleet_engineer = "Operations",
    starfleet_security = "Operations",
    starfleet_medical  = "Science",
    starfleet_science  = "Science",
    survey_specialist  = "Science",
}

-- Written out whole rather than built from the division's name: an item id
-- assembled from parts is one no static check can see (tests/test_assets.py).
local UNIFORM = {
    Command    = { "TrekShuttle.TrekUniformDutyCommand",    "TrekShuttle.TrekUniformDressCommand" },
    Operations = { "TrekShuttle.TrekUniformDutyOperations", "TrekShuttle.TrekUniformDressOperations" },
    Science    = { "TrekShuttle.TrekUniformDutyScience",    "TrekShuttle.TrekUniformDressScience" },
}

for path, division in pairs(DIVISION) do
    local wear = {
        Boilersuit = { chance = 100, items = { UNIFORM[division][1] } },
        FullSuit   = { chance = 10,  items = { UNIFORM[division][2] } },
    }
    -- Both sexes share one set: vanilla falls back to Female when there is
    -- no Male table, and the uniforms fit both.
    ClothingSelectionDefinitions[path] = { Female = wear }
end
