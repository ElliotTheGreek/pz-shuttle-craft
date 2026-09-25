--[[ Shuttlecraft -- what a species looks like, on the character (TRAITS.md 2.4).

    The authority dresses a character in its species' look and tells every
    machine, exactly as vanilla's ISCutHair does once a haircut completes:
    change the HumanVisual here, then sendHumanVisual(character). Three parts,
    all the engine's own and all saved with the character's HumanVisual
    (HumanVisual.save writes the skin name and the body visuals):

      * a skin name -- setSkinTextureName, which getSkinTexture() answers
        before it ever reads the five-tone list, so a named body texture
        replaces the skin outright (Andorian, Orion, android);
      * an overlay -- a hidden clothing item added as a body visual, laid over
        the skin as stubble and makeup are (spots, ridges, eyes, an implant);
      * a mesh -- a hidden clothing item whose model is pinned to Bip01_Head,
        as vanilla's bunny ears are, with the texture choice matched to the
        character's skin tone (Vulcan ears, Andorian antennae).

    **It is a check, not a one-shot.** A.apply compares what the character
    wears with what their species should, and changes only the difference --
    so it runs on first sight and every ten minutes, repairs an old save, and
    follows a species an admin adds or takes away. A human wears nothing of
    this mod's, and any of it left on one comes off.
]]

if isClient() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Traits"

local U = TREK.Util
local T = TREK.Traits

local A = {}
TREK.Appearance = A

A.LOOKS = {
    vulcan   = { mesh = "vulcanears" },
    klingon  = { overlay = "klingon" },
    andorian = { skin = "Andorian", mesh = "antennae" },
    betazoid = { overlay = "betazoid" },
    trill    = { overlay = "trill" },
    bajoran  = { overlay = "bajoran" },
    talaxian = { overlay = "talaxian" },
    orion    = { skin = "Orion" },
    android  = { skin = "Android" },
    exborg   = { overlay = "exborg" },
}

-- Every look item, written out whole: an id built from parts is one no
-- static check can see (tests/test_assets.py reads these). An overlay has one
-- per sex, because the two bodies' atlases differ; a mesh is one item that
-- carries both sexes' models.
A.OVERLAY = {
    trill    = { M = "TrekShuttle.TrekLook_trill_M",    F = "TrekShuttle.TrekLook_trill_F" },
    bajoran  = { M = "TrekShuttle.TrekLook_bajoran_M",  F = "TrekShuttle.TrekLook_bajoran_F" },
    betazoid = { M = "TrekShuttle.TrekLook_betazoid_M", F = "TrekShuttle.TrekLook_betazoid_F" },
    klingon  = { M = "TrekShuttle.TrekLook_klingon_M",  F = "TrekShuttle.TrekLook_klingon_F" },
    talaxian = { M = "TrekShuttle.TrekLook_talaxian_M", F = "TrekShuttle.TrekLook_talaxian_F" },
    exborg   = { M = "TrekShuttle.TrekLook_exborg_M",   F = "TrekShuttle.TrekLook_exborg_F" },
}
A.MESH = {
    vulcanears = "TrekShuttle.TrekLook_vulcanears",
    antennae   = "TrekShuttle.TrekLook_antennae",
}
A.ITEMS = {}
for _, pair in pairs(A.OVERLAY) do
    table.insert(A.ITEMS, pair.M)
    table.insert(A.ITEMS, pair.F)
end
for _, id in pairs(A.MESH) do table.insert(A.ITEMS, id) end

--- The skin tone, 1-5, the character was made with.
local function tone(hv)
    local i = tonumber(U.try("look.tone", function() return hv:getSkinTextureIndex() end)) or 0
    return math.max(1, math.min(5, math.floor(i) + 1))
end

--- What this character should wear: the set of item ids, the skin name (or
--- nil), and the texture choice for a mesh.
function A.wanted(player)
    local female = U.try("look.female", function() return player:isFemale() end) == true
    local species = T.species(player)
    local look = species and A.LOOKS[species] or {}
    local hv = U.try("look.hv", function() return player:getHumanVisual() end)
    local t = hv and tone(hv) or 1
    local want = {}
    if look.overlay then want[A.OVERLAY[look.overlay][female and "F" or "M"]] = true end
    if look.mesh then want[A.MESH[look.mesh]] = true end
    local skin = look.skin and ("TREK_" .. look.skin .. "_" .. (female and "F" or "M") .. t) or nil
    return want, skin, t - 1
end

--- Brings the character's look into line with their species. Returns true
--- when anything changed (and was sent).
function A.apply(player)
    if not player then return false end
    local hv = U.try("look.hv", function() return player:getHumanVisual() end)
    if not hv then return false end
    local want, skin, choice = A.wanted(player)
    local changed = false

    for _, id in ipairs(A.ITEMS) do
        local has = U.try("look.has", function() return hv:hasBodyVisualFromItemType(id) end) == true
        if want[id] and not has then
            local iv = U.try("look.add:" .. id, function() return hv:addBodyVisualFromItemType(id) end)
            if iv then
                U.try("look.choice", function() iv:setTextureChoice(choice) end)
                changed = true
            else
                U.log("WARN look: %s did not become a body visual -- its clothing XML "
                      .. "or GUID row is missing", id)
            end
        elseif has and not want[id] then
            U.try("look.remove:" .. id, function() hv:removeBodyVisualFromItemType(id) end)
            changed = true
        end
    end

    -- Only ever clear a skin this mod set: a name some other mod put there
    -- is theirs.
    local current = U.try("look.skin", function() return hv:getSkinTexture() end)
    local ours = type(current) == "string" and current:sub(1, 5) == "TREK_"
    if skin and current ~= skin then
        U.try("look.setSkin", function() hv:setSkinTextureName(skin) end)
        changed = true
    elseif not skin and ours then
        U.try("look.clearSkin", function() hv:setSkinTextureName(nil) end)
        changed = true
    end

    if changed then
        U.try("look.reset", function() player:resetModelNextFrame() end)
        if isServer() then
            U.try("look.send", function() sendHumanVisual(player) end)
        end
        U.log("look: %s dressed as %s", tostring(U.try("look.who", function()
            return player:getUsername() end)), tostring(T.species(player) or "human"))
    end
    return changed
end

--- Every player, every ten minutes: cheap, because nothing changes unless
--- something is wrong.
Events.EveryTenMinutes.Add(function()
    for _, p in ipairs(U.players()) do
        U.try("look.service", A.apply, p)
    end
end)

return A
