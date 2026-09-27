--[[ Shuttlecraft -- contraband: what both sides agree on (CONTRABAND.md).

    Which items are contraband, what a character's record says, and whether
    they are hooked. Nothing here changes anything: the record is written by
    the server (TREK_ContrabandServer) and read here by anybody.

    **Where the record is read from depends on the machine.** The authority
    keeps it in the player's mod data under C.ContrabandKey. A client in
    multiplayer has its own copy of the player, which that write never
    reaches (DEV_GUIDE, *Player mod data a client writes is not the
    server's*, read the other way round), so the server sends the owning
    client a summary after every change and the client keeps it under
    C.ContrabandMirrorKey. In single player they are one object and the
    authority's key is the one read.

    That is what lets the Doctor's panel grey its Detox button, and the
    PADD's menu offer the flashing light, from the patient's own body.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local K = {}
TREK.Contraband = K

-- Full type -> substance name, for everything that is taken rather than
-- played. Built from C.Contraband so the two cannot disagree.
K.BY_ITEM = {}
for name, def in pairs(C.Contraband) do
    if def.item and name ~= "game" then K.BY_ITEM[def.item] = name end
end

--- The substance a full type is, or nil.
function K.substanceOf(fullType)
    return fullType and K.BY_ITEM[fullType] or nil
end

--- True for cordrazine, which is taken like the others and forms no habit.
function K.isCordrazine(fullType)
    return fullType ~= nil and fullType == C.Cordrazine.item
end

local function md(player)
    return player and U.try("contra.md", function() return player:getModData() end)
end

--- This machine's view of a character's record: { [substance] = row }.
---
--- A row on the authority is { doses, last, hooked, first, crashAt,
--- boostUntil, nagAt }; the client's mirror carries { doses, hooked,
--- withdrawing } only. Never nil for a live player -- an empty table is
--- "clean".
function K.record(player)
    local data = md(player)
    if not data then return {} end
    local key = isClient() and C.ContrabandMirrorKey or C.ContrabandKey
    if type(data[key]) ~= "table" then data[key] = {} end
    return data[key]
end

--- The substances a character is hooked on, in C.ContrabandOrder.
function K.dependencies(player)
    local out = {}
    local rec = K.record(player)
    for _, name in ipairs(C.ContrabandOrder) do
        local row = rec[name]
        if type(row) == "table" and row.hooked == true then table.insert(out, name) end
    end
    return out
end

function K.isDependent(player)
    return #K.dependencies(player) > 0
end

--- True when a character has played the Game at all and not been cured of it:
--- what the PADD's flashing light is for. A habit not yet formed counts --
--- the light is no use to somebody who has never played, and every use to
--- somebody on their third round.
function K.playsTheGame(player)
    local row = K.record(player).game
    return type(row) == "table" and ((tonumber(row.doses) or 0) > 0 or row.hooked == true)
end

--- The summary the server sends the owning client, and the shape of the
--- mirror: only what a panel needs to draw.
function K.summary(player, now)
    local out = {}
    local rec = K.record(player)
    for _, name in ipairs(C.ContrabandOrder) do
        local row = rec[name]
        if type(row) == "table" then
            out[name] = {
                doses = tonumber(row.doses) or 0,
                hooked = row.hooked == true,
                withdrawing = K.withdrawing(name, row, now) or nil,
            }
        end
    end
    return out
end

--- True when a row is in withdrawal at world hour `now`. Pure.
function K.withdrawing(name, row, now)
    local def = C.Contraband[name]
    if not def or type(row) ~= "table" or row.hooked ~= true then return false end
    if type(row.last) ~= "number" or type(now) ~= "number" then return false end
    return now - row.last >= def.withdrawAfter
end

--- Each substance's words, written out whole. A key assembled from parts
--- is invisible to tests/test_assets.py, which reads every IGUI_TREK_ literal
--- in the Lua and fails one with no text (DEV_GUIDE, *An id assembled from
--- parts is invisible to a static check*).
K.TEXT = {
    ketracel = { name = "IGUI_TREK_Contra_ketracel", first = "IGUI_TREK_ContraFirst_ketracel",
                 crave = "IGUI_TREK_Crave_ketracel" },
    felicium = { name = "IGUI_TREK_Contra_felicium", first = "IGUI_TREK_ContraFirst_felicium",
                 crave = "IGUI_TREK_Crave_felicium" },
    trellium = { name = "IGUI_TREK_Contra_trellium", first = "IGUI_TREK_ContraFirst_trellium",
                 crave = "IGUI_TREK_Crave_trellium", crash = "IGUI_TREK_ContraCrash_trellium" },
    game     = { name = "IGUI_TREK_Contra_game", first = "IGUI_TREK_ContraFirst_game",
                 crave = "IGUI_TREK_Crave_game" },
}

--- A translation key for a substance's name, for the Doctor's readout.
function K.nameKey(name)
    local t = K.TEXT[name]
    return t and t.name or "IGUI_TREK_Contra_unknown"
end

return K
