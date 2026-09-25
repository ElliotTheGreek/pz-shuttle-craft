--[[ Shuttlecraft -- what each species looks like, and how to dress a
    HumanVisual in it (TRAITS.md 2.4, 4.6).

    Shared, because two places dress a character and they have to agree:

      * the creation screen (client/TREK_CreationLook), on the SurvivorDesc
        the avatar is drawn from -- so choosing Vulcan shows the ears before
        the character exists, and the character is made wearing them;
      * the authority (server/TREK_Appearance), on the character in the
        world -- which repairs a look that is wrong, and follows a species an
        admin changes.

    L.dress changes only what differs and says whether it changed anything,
    so both callers can call it freely.
]]

require "TREK/TREK_Util"

TREK = TREK or {}
local U = TREK.Util

local L = {}
TREK.Looks = L

L.LOOKS = {
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
L.OVERLAY = {
    trill    = { M = "TrekShuttle.TrekLook_trill_M",    F = "TrekShuttle.TrekLook_trill_F" },
    bajoran  = { M = "TrekShuttle.TrekLook_bajoran_M",  F = "TrekShuttle.TrekLook_bajoran_F" },
    betazoid = { M = "TrekShuttle.TrekLook_betazoid_M", F = "TrekShuttle.TrekLook_betazoid_F" },
    klingon  = { M = "TrekShuttle.TrekLook_klingon_M",  F = "TrekShuttle.TrekLook_klingon_F" },
    talaxian = { M = "TrekShuttle.TrekLook_talaxian_M", F = "TrekShuttle.TrekLook_talaxian_F" },
    exborg   = { M = "TrekShuttle.TrekLook_exborg_M",   F = "TrekShuttle.TrekLook_exborg_F" },
}
L.MESH = {
    vulcanears = "TrekShuttle.TrekLook_vulcanears",
    antennae   = "TrekShuttle.TrekLook_antennae",
}
L.ITEMS = {}
for _, pair in pairs(L.OVERLAY) do
    table.insert(L.ITEMS, pair.M)
    table.insert(L.ITEMS, pair.F)
end
for _, id in pairs(L.MESH) do table.insert(L.ITEMS, id) end

--- The skin tone, 1-5, a HumanVisual was made with.
local function tone(hv)
    local i = tonumber(U.try("look.tone", function() return hv:getSkinTextureIndex() end)) or 0
    return math.max(1, math.min(5, math.floor(i) + 1))
end

--- What a HumanVisual should wear for `species` (a path, or nil for a
--- human): the set of item ids, the skin name or nil, and a mesh's texture
--- choice.
function L.wanted(hv, species, female)
    local look = species and L.LOOKS[species] or {}
    local t = tone(hv)
    local want = {}
    if look.overlay then want[L.OVERLAY[look.overlay][female and "F" or "M"]] = true end
    if look.mesh then want[L.MESH[look.mesh]] = true end
    local skin = look.skin and ("TREK_" .. look.skin .. "_" .. (female and "F" or "M") .. t) or nil
    return want, skin, t - 1
end

--- Brings a HumanVisual into line with `species`. Returns true when anything
--- changed. Only a skin this mod set is ever cleared: another mod's is theirs.
function L.dress(hv, species, female)
    if not hv then return false end
    local want, skin, choice = L.wanted(hv, species, female)
    local changed = false

    for _, id in ipairs(L.ITEMS) do
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

    local current = U.try("look.skin", function() return hv:getSkinTexture() end)
    local ours = type(current) == "string" and current:sub(1, 5) == "TREK_"
    if skin and current ~= skin then
        U.try("look.setSkin", function() hv:setSkinTextureName(skin) end)
        changed = true
    elseif not skin and ours then
        U.try("look.clearSkin", function() hv:setSkinTextureName(nil) end)
        changed = true
    end
    return changed
end

return L
