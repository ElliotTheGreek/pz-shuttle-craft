--[[ Shuttlecraft -- the ship's contacts, drawn on the world map.

    **The engine is not asked to remember any of this.** Build 42 has a
    complete shared-annotation system -- symbols that persist, replicate and
    carry per-player visibility -- and Lua is handed the drawing end of it and
    not the sharing end: `sendShareSymbol` takes a `WorldMapSymbolNetworkInfo`,
    that class is not in the exposure list, and no vanilla Lua calls it
    anywhere. `WorldMapClient` and `WorldMapServer` are not exposed either.
    MAP_MARKERS.md is the research.

    So the contacts are the mod's own bounded store (TREK_Probes), the server
    owns them, and this file is a **view**: when the map opens it draws one
    symbol per live contact, and when the map closes it takes exactly those
    symbols away again. Nothing of ours is ever written into the player's own
    saved annotations, every client rebuilds the same picture from the same
    server-owned table, and a contact cannot be lost because somebody tidied
    their map.

    Rebuilding rather than adding once is also what makes this safe against
    the one thing that could not be checked outside a game: whether world-map
    symbols persist in single player at all. If they do not, we redraw. If
    they do, we removed ours on the way out. Either way there is exactly one
    symbol per contact -- which is the *Two shuttles* failure shape, avoided
    by never relying on the answer.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Probes"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local P = TREK.Probes

local M = {}
TREK.MapContacts = M

-- The symbols this file put on the map, so it can take away exactly those and
-- nothing the player drew. Never cleared by clear() -- that would eat the
-- player's own annotations, which is somebody's afternoon.
local placed = {}
local api = nil

--- The symbols API of the open world map, or nil when there is no map open.
---
--- Reached through the UI, because that is the only route Lua is given: the
--- symbol API is constructed with a UIWorldMap and there is no global.
local function symbolsAPI(mapUI)
    if not mapUI then return nil end
    return U.try("symbolsAPI", function()
        return mapUI.mapAPI and mapUI.mapAPI:getSymbolsAPIv2()
    end)
end

--- Takes our own symbols off the map. Safe to call twice.
function M.clear()
    if api and #placed > 0 then
        local drop = U.batch("map.removeSymbol")
        for i = #placed, 1, -1 do
            local symbol = placed[i]
            drop(function() api:removeSymbol(symbol) end)
        end
    end
    placed = {}
    api = nil
end

--- Draws one symbol per live contact. Returns how many landed.
---
--- Only unresolved contacts: a recovered crystal is history, and a map that
--- keeps every place the ship has ever been is a map nobody reads.
function M.draw(mapUI)
    M.clear()
    M.revealAll()
    local symbols = symbolsAPI(mapUI)
    if not symbols then return 0 end
    api = symbols

    local n = 0
    for _, contact in ipairs(P.unresolved()) do
        local id = C.ContactSymbols[contact.kind]
        if id then
            -- addTexture takes **world coordinates**, which is what the rest
            -- of this mod already speaks: vanilla's own symbol tool builds
            -- them with mapAPI:uiToWorldX before calling it.
            local symbol = U.try("addSymbol", function()
                return symbols:addTexture(id, contact.x, contact.y)
            end)
            if symbol then
                -- Anchored at its middle so the glyph sits *on* the square
                -- rather than hanging below and right of it, and set to full
                -- white -- which is not a tint but a multiplier, so it shows
                -- the art as drawn. Vanilla calls setRGBA after every
                -- addTexture (ISWorldMapSymbols.lua:138) and a symbol whose
                -- colour was never set is a symbol that may draw at alpha 0.
                U.try("symbolStyle", function()
                    symbol:setAnchor(0.5, 0.5)
                    symbol:setRGBA(1.0, 1.0, 1.0, 1.0)
                end)
                table.insert(placed, symbol)
                n = n + 1
            end
        end
    end
    return n
end

---------------------------------------------------------------------------
-- Revealing the ground
---------------------------------------------------------------------------
-- A contact is no use if the map around it is still black. `setKnownInSquares`
-- is what a **paper map** does when you read one -- `ISReadABook.lua:318`,
-- ordinary shared code, no admin panel in sight -- so a probe survey doing
-- the same thing is the engine being used as intended rather than bent.
--
-- It is per-player and client-side: WorldMapVisited is *this* character's
-- explored map. So every client reveals its own when it hears about a
-- contact, which is the same shape as the lights and the shields -- a thing
-- each machine recomputes rather than a piece of ship state.
local revealed = {}

function M.reveal(contact)
    if not contact or revealed[contact.id] then return false end
    local r = C.ContactRevealRadius
    local ok = U.try("revealArea", function()
        WorldMapVisited.getInstance():setKnownInSquares(
            contact.x - r, contact.y - r, contact.x + r, contact.y + r)
        return true
    end)
    if ok then revealed[contact.id] = true end
    return ok == true
end

--- Reveals every contact the ship holds. Cheap after the first pass: each id
--- is revealed once per session.
function M.revealAll()
    local n = 0
    for _, contact in ipairs(P.unresolved()) do
        if M.reveal(contact) then n = n + 1 end
    end
    return n
end

--- Redraws while the map is open, so a report that arrives mid-look appears.
local function refresh()
    -- Reveal first and regardless of whether the map is open: a report that
    -- arrives while the player is walking should have uncovered its ground by
    -- the time they look.
    M.revealAll()
    if not api then return end
    local mapUI = ISWorldMap_instance
    if mapUI then M.draw(mapUI) end
end

P.onChange(refresh)

---------------------------------------------------------------------------
-- Hooking the map
---------------------------------------------------------------------------
-- Wrapped the way the radial menu is, and for a milder version of the same
-- reason: take the reading that matters *after* vanilla has built its map,
-- because before that call there is no UI and no symbols API to add to.
-- Unlike the radial menu this one is not a toggle, so the ordering is the
-- easy way round -- but it is still wrapped rather than replaced, and it
-- still calls through unconditionally first.
if ISWorldMap and ISWorldMap.ShowWorldMap then
    local baseShow = ISWorldMap.ShowWorldMap
    function ISWorldMap.ShowWorldMap(playerNum, centerX, centerY, zoom)
        baseShow(playerNum, centerX, centerY, zoom)
        U.try("mapContactsDraw", function()
            M.draw(ISWorldMap_instance)
        end)
    end
end

if ISWorldMap and ISWorldMap.onClose then
    local baseClose = ISWorldMap.onClose
    function ISWorldMap:onClose()
        -- Ours come off *first*. After baseClose the UI may be gone, and
        -- removing a symbol from a map that no longer exists is a throw per
        -- symbol rather than one warning.
        U.try("mapContactsClear", M.clear)
        return baseClose(self)
    end
end

--- Opens the world map centred on a contact. The probe console's focus
--- control, and the reason ISWorldMap.ShowWorldMap's signature is worth
--- knowing: it already takes a centre.
function M.focus(playerNum, contactId)
    local contact = P.byId(contactId)
    if not contact then return false end
    return U.try("mapFocus", function()
        ISWorldMap.ShowWorldMap(playerNum or 0, contact.x, contact.y)
        return true
    end) == true
end

--- How many symbols this file currently has on the map. For the tests, and
--- for the reason B.stockReport exists: a draw that silently did nothing
--- looks exactly like a map with no contacts on it.
function M.count()
    return #placed
end

return M
