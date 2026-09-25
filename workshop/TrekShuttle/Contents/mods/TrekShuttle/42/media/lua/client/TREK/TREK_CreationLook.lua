--[[ Shuttlecraft -- the species on the character creation screen
    (TRAITS.md 4.6).

    Picking Vulcan on the traits page has to show the ears on the avatar, or a
    player reasonably concludes nothing happened. The avatar is drawn from
    MainScreen.instance.desc, the SurvivorDesc the character is then made
    from, and vanilla dresses that desc's HumanVisual directly: it adds and
    removes the stubble body visuals there (CharacterCreationMain
    :onGenderSelected) and sets the skin index there (onSkinColorPicked). So
    the look goes on the same object, with the same TREK_Looks.dress the
    server uses, and the character is made already wearing it.

    Four vanilla moments redraw it, each wrapped to dress the desc afterwards:
    the clothing being rebuilt (initClothing, which runs on entering the
    screen and on every profession or trait change), a skin tone picked, a sex
    picked, and a trait added or removed on the traits page.
]]

if isServer() then return end

require "TREK/TREK_Util"
require "TREK/TREK_Traits"
require "TREK/TREK_Looks"

local U = TREK.Util
local T = TREK.Traits
local L = TREK.Looks

local CL = {}
TREK.CreationLook = CL

--- The species path picked on the traits page, or nil.
function CL.pickedSpecies()
    local prof = rawget(_G, "CharacterCreationProfession")
    local screen = prof and prof.instance
    local items = screen and screen.listboxTraitSelected and screen.listboxTraitSelected.items
    if not items then return nil end
    for _, path in ipairs(T.SPECIES) do
        local id = T.id(path)
        for _, v in pairs(items) do
            local t = v and v.item and U.try("look.pickedType", function() return v.item:getType() end)
            if id and t == id then return path end
        end
    end
    return nil
end

--- Dresses the desc the avatar is drawn from, and redraws the avatar.
function CL.preview()
    local desc = MainScreen and MainScreen.instance and MainScreen.instance.desc
    if not desc then return false end
    local hv = U.try("look.descVisual", function() return desc:getHumanVisual() end)
    local female = U.try("look.descFemale", function() return desc:isFemale() end) == true
    local changed = L.dress(hv, CL.pickedSpecies(), female)
    local main = rawget(_G, "CharacterCreationMain")
    local panel = main and main.instance and main.instance.avatarPanel
    if panel then U.try("look.avatar", function() panel:setSurvivorDesc(desc) end) end
    return changed
end

local function after(class, name)
    local base = class and class[name]
    if type(base) ~= "function" or class["TREK_" .. name] then return end
    class["TREK_" .. name] = base
    class[name] = function(self, ...)
        local a, b, c = base(self, ...)
        U.try("look.preview:" .. name, CL.preview)
        return a, b, c
    end
end

--- Wraps the four moments. Safe to call more than once.
function CL.wrap()
    local main = rawget(_G, "CharacterCreationMain")
    local prof = rawget(_G, "CharacterCreationProfession")
    after(main, "initClothing")
    after(main, "onSkinColorPicked")
    after(main, "onGenderSelected")
    after(prof, "addTrait")
    after(prof, "removeTrait")
end

CL.wrap()
Events.OnGameBoot.Add(CL.wrap)

return CL
