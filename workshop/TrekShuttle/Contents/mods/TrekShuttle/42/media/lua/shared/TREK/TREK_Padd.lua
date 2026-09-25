--[[ Shuttlecraft -- the PADD's library (PADD.md).

    A PADD holds digital copies of books. The library is a list in the PADD's
    own mod data, so it travels with the item: lose the PADD and the books go
    with it, recover it and they come back. Nothing about it is ship state.

    This file is the data and the arithmetic, shared because both ends need
    it and must agree: the client uses it to build menus and grey options,
    the timed actions in TREK_PaddActions use it on the server, where the
    library is actually written and where reading actually does anything.

    **A book in build 42 is its type and its copy's own mod data.** Two copies
    of `Base.Book` are two different novels (`literatureTitle`), a recipe
    magazine may carry its recipe on the copy (`learnedRecipe`), and a flyer
    carries its print media id. An entry keeps all three, and nothing else a
    copy carries. PADD.md section 2 has the reading of ISReadABook this rests
    on.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local Pd = {}
TREK.Padd = Pd

-- The copy data an entry keeps, and nothing else. Each is a key vanilla's
-- ISReadABook reads off a book's mod data.
local COPY_KEYS = { "literatureTitle", "learnedRecipe" }

---------------------------------------------------------------------------
-- What is a PADD, and what is a book
---------------------------------------------------------------------------
function Pd.isPadd(item)
    if not item then return false end
    return U.try("padd.isPadd", function()
        return item:getFullType() == C.PaddItem
    end) == true
end

--- Whether an item is a book a PADD can take a copy of.
---
--- Literature, and not:
---   * **writable** (a notebook, a journal): what a player wrote in one is
---     theirs, and copying it is a different feature;
---   * **consumed when read** (`CONSUME_ON_READ`): ReadLiterature calls
---     `Use()` on those, which on a reconstructed copy is a call on an item
---     that belongs to no container -- and a thing that is used up has no
---     business being read for ever off a PADD.
function Pd.isBook(item)
    if not item or Pd.isPadd(item) then return false end
    return U.try("padd.isBook", function()
        if not instanceof(item, "Literature") then return false end
        if item:canBeWrite() then return false end
        if item:hasTag(ItemTag.CONSUME_ON_READ) then return false end
        return true
    end) == true
end

---------------------------------------------------------------------------
-- Entries
---------------------------------------------------------------------------
--- The skill a skill book trains, or nil. `SkillBook` is vanilla's table
--- (server/XpSystem/XPSystem_SkillBook.lua), loaded in every process.
function Pd.skillOf(skillTrained)
    if type(skillTrained) ~= "string" or skillTrained == "" then return nil end
    if type(SkillBook) ~= "table" then return nil end
    return SkillBook[skillTrained]
end

--- An entry for this book: what to show, what to read, what to copy.
function Pd.entryOf(book)
    if not book then return nil end
    local e = {}
    local ok = U.try("padd.entryOf", function()
        e.type = book:getFullType()
        e.name = book:getName()
        e.pages = book:getNumberOfPages() or 0
        local skill = book:getSkillTrained()
        if Pd.skillOf(skill) then
            e.kind = "skill"
            e.skill = skill
            e.level = book:getLvlSkillTrained()
            e.maxLevel = book:getMaxLevelTrained()
        else
            local recipes = book:getLearnedRecipes()
            if recipes and not recipes:isEmpty() then e.kind = "recipe"
            else e.kind = "literature" end
        end
        e.fast = book:hasTag(ItemTag.FAST_READ) == true
        local md = book:hasModData() and book:getModData() or nil
        if md then
            local copy = nil
            for _, key in ipairs(COPY_KEYS) do
                local v = md[key]
                if type(v) == "string" or type(v) == "number" then
                    copy = copy or {}
                    copy[key] = v
                end
            end
            -- Print media is a table; its id is what reading records.
            if type(md.printMedia) == "table" and md.printMedia.id ~= nil then
                copy = copy or {}
                copy.printMediaId = md.printMedia.id
            end
            if copy and copy.learnedRecipe and e.kind == "literature" then
                e.kind = "recipe"
            end
            e.md = copy
        end
        return true
    end)
    if not ok or type(e.type) ~= "string" then return nil end
    return e
end

--- What makes two entries the same book: its type and its copy's data.
function Pd.key(entry)
    if not entry then return "" end
    local md = entry.md or {}
    return tostring(entry.type) .. "|" .. tostring(md.literatureTitle or "")
           .. "|" .. tostring(md.learnedRecipe or "")
           .. "|" .. tostring(md.printMediaId or "")
end

---------------------------------------------------------------------------
-- The library
---------------------------------------------------------------------------
--- The PADD's library, a list. Never nil for a PADD; an untouched one is
--- simply empty.
function Pd.library(padd)
    if not padd then return {} end
    local md = U.try("padd.modData", function() return padd:getModData() end)
    if not md then return {} end
    if type(md[C.PaddLibraryKey]) ~= "table" then return {} end
    return md[C.PaddLibraryKey]
end

function Pd.count(padd)
    return #Pd.library(padd)
end

--- The entry with this key, and its index; or nil.
function Pd.find(padd, key)
    for i, e in ipairs(Pd.library(padd)) do
        if Pd.key(e) == key then return e, i end
    end
    return nil
end

function Pd.has(padd, entry)
    return Pd.find(padd, Pd.key(entry)) ~= nil
end

--- Adds an entry. Returns true when it was new. **Authority only**: the
--- library is item state, written where the timed action completes (the
--- server, or single player) and pushed with syncItemModData.
function Pd.add(padd, entry)
    if isClient() or not padd or not entry then return false end
    if Pd.has(padd, entry) then return false end
    local md = padd:getModData()
    if type(md[C.PaddLibraryKey]) ~= "table" then md[C.PaddLibraryKey] = {} end
    table.insert(md[C.PaddLibraryKey], entry)
    return true
end

--- Copies every title `from` holds that `to` does not. Returns how many.
function Pd.merge(from, to)
    if isClient() or not from or not to then return 0 end
    local added = 0
    for _, e in ipairs(Pd.library(from)) do
        if Pd.add(to, e) then added = added + 1 end
    end
    return added
end

--- Empties a PADD: its books and its transcripts. Returns how many went.
function Pd.erase(padd)
    if isClient() or not padd then return 0 end
    local n = Pd.count(padd) + #Pd.tapes(padd)
    padd:getModData()[C.PaddLibraryKey] = {}
    padd:getModData()[C.PaddTapesKey] = {}
    return n
end

---------------------------------------------------------------------------
-- Transcripts (PADD.md 12.3)
---------------------------------------------------------------------------
-- A transcript is a recording id and nothing else. The lines are rendered
-- from the registered recording when it is read, so a tape regenerated by
-- gen_tapes.py updates every transcript of it -- the history's rule, applied
-- to the shelf.

--- The recording ids transcribed onto this PADD, in the order they went on.
function Pd.tapes(padd)
    if not padd then return {} end
    local md = U.try("padd.tapesModData", function() return padd:getModData() end)
    if not md or type(md[C.PaddTapesKey]) ~= "table" then return {} end
    return md[C.PaddTapesKey]
end

function Pd.hasTape(padd, id)
    for _, t in ipairs(Pd.tapes(padd)) do
        if t == id then return true end
    end
    return false
end

--- Adds a transcript. **Authority only**, like every library write.
function Pd.addTape(padd, id)
    if isClient() or not padd or type(id) ~= "string" then return false end
    if Pd.hasTape(padd, id) then return false end
    local md = padd:getModData()
    if type(md[C.PaddTapesKey]) ~= "table" then md[C.PaddTapesKey] = {} end
    table.insert(md[C.PaddTapesKey], id)
    return true
end

--- Copies every transcript `from` holds that `to` does not.
function Pd.mergeTapes(from, to)
    if isClient() or not from or not to then return 0 end
    local added = 0
    for _, id in ipairs(Pd.tapes(from)) do
        if Pd.addTape(to, id) then added = added + 1 end
    end
    return added
end

--- The recording an item carries, or nil: its id, when it is one this
--- process has registered text for.
function Pd.recordingOf(item)
    if not item or Pd.isPadd(item) then return nil end
    local id = U.try("padd.recording", function()
        if not item:isRecordedMedia() then return nil end
        local data = item:getMediaData()
        return data and data:getId()
    end)
    if type(id) ~= "string" then return nil end
    if type(RecMedia) ~= "table" or type(RecMedia[id]) ~= "table" then return nil end
    return id
end

--- A recording as lines, in its speakers' colours, from the `RecMedia`
--- table every process loads -- vanilla's tapes and the mod's alike. Each
--- line's text is its translation key resolved the way the engine resolves
--- it (MediaLineData.getTranslatedText is Translator.getText of the key).
function Pd.tapeLines(id)
    local out = {}
    local rec = type(RecMedia) == "table" and RecMedia[id]
    if type(rec) ~= "table" then return out end
    for _, ln in ipairs(rec.lines or {}) do
        table.insert(out, { text = getText(ln.text), r = ln.r or 1,
                            g = ln.g or 1, b = ln.b or 1 })
    end
    return out
end

--- A recording's title.
function Pd.tapeTitle(id)
    local rec = type(RecMedia) == "table" and RecMedia[id]
    if type(rec) ~= "table" then return tostring(id) end
    return getText(rec.title or rec.itemDisplayName or tostring(id))
end

---------------------------------------------------------------------------
-- Carrying
---------------------------------------------------------------------------
--- Every PADD in this player's inventory, bags included.
function Pd.carried(player)
    local out = {}
    U.try("padd.carried", function()
        local list = player:getInventory():getAllTypeRecurse(C.PaddType)
        for i = 0, list:size() - 1 do
            local it = list:get(i)
            -- getAllTypeRecurse compares the bare type, which is not
            -- namespaced (DEV_GUIDE failure signatures); filter on the id.
            if Pd.isPadd(it) then table.insert(out, it) end
        end
    end)
    return out
end

--- Whether this exact PADD is in the player's main inventory -- where a
--- timed action requires it, exactly as ISReadABook requires its book.
function Pd.inHand(player, padd)
    if not player or not padd then return false end
    return U.try("padd.inHand", function()
        local inv = player:getInventory()
        if isClient() then return inv:containsID(padd:getID()) end
        return inv:contains(padd)
    end) == true
end

--- Whether a book can be reached: in the player's inventory (bags too), or
--- in a container within a couple of squares -- a shelf in the loot panel.
function Pd.canReach(player, book)
    if not player or not book then return false end
    return U.try("padd.canReach", function()
        local c = book:getContainer()
        if not c then return false end
        if c:isInCharacterInventory(player) then return true end
        local parent = c:getParent()
        local sq = parent and parent:getSquare()
        if not sq then
            -- A container on the floor (a dropped bag) answers through its
            -- world item.
            local wi = book:getWorldItem()
            sq = wi and wi:getSquare()
        end
        if not sq then return false end
        if sq:getZ() ~= math.floor(player:getZ()) then return false end
        return U.dist2(sq:getX() + 0.5, sq:getY() + 0.5,
                       player:getX(), player:getY()) <= 2.5 * 2.5
    end) == true
end

---------------------------------------------------------------------------
-- Reading
---------------------------------------------------------------------------
--- Whether this character may read this entry, and the reason if not. The
--- same two refusals ISReadABook makes for a skill book, plus illiteracy.
function Pd.readRefusal(character, entry)
    if not entry then return "gone" end
    local illiterate = U.try("padd.illiterate", function()
        return character:hasTrait(CharacterTrait.ILLITERATE)
    end)
    if illiterate == true then return "illiterate" end
    if entry.kind == "skill" then
        local sb = Pd.skillOf(entry.skill)
        local level = sb and U.try("padd.perkLevel", function()
            return character:getPerkLevel(sb.perk)
        end)
        if level then
            if (entry.level or 0) > level + 1 then return "tooHard" end
            if (entry.maxLevel or 0) < level + 1 then return "tooEasy" end
        end
    end
    return nil
end

--- How long reading an entry takes, in timed-action ticks.
---
--- **Mirrors ISReadABook:getDuration()** (42.20.4, lines 440-470) and then
--- divides by C.PaddReadSpeed. Kept in one function, naming the lines it
--- copies, so it can be diffed against vanilla when the game updates.
function Pd.readTicks(character, entry)
    if U.try("padd.instant", function() return character:isTimedActionInstant() end) == true then
        return 1
    end
    local pages = (entry and entry.pages) or 0
    local startPage = 0
    if pages > 0 then
        startPage = U.try("padd.startPage", function()
            return character:getAlreadyReadPages(entry.type)
        end) or 0
        if startPage >= pages then startPage = 0 end
    else
        pages = 5
    end
    local minutesPerPage = U.try("padd.mpp", function()
        return getSandboxOptions():getOptionByName("MinutesPerPage"):getValue()
    end) or 2.0
    if minutesPerPage < 0 then minutesPerPage = 2.0 end
    local minutesPerDay = U.try("padd.mpd", function()
        return getGameTime():getMinutesPerDay()
    end) or 60
    local f = 1 / minutesPerDay / 2
    -- Only the pages still to read: a book half read on paper is half read
    -- on the PADD, because the progress is the character's (PADD.md s.4).
    local time = (pages - startPage) * minutesPerPage / f
    if entry and entry.fast then time = 50 end
    U.try("padd.traits", function()
        if character:hasTrait(CharacterTrait.FAST_READER) then time = time * 0.7 end
        if character:hasTrait(CharacterTrait.SLOW_READER) then time = time * 1.3 end
    end)
    U.try("padd.glasses", function()
        local eye = character:getWornItems():getItem(ItemBodyLocation.EYES)
        if eye and eye:getType() == "Glasses_Reading" then time = time * 0.9 end
    end)
    U.try("padd.sitting", function()
        if character:isSitOnGround() or character:isSittingOnFurniture() then
            time = time * 0.9
        end
    end)
    -- A holo-historian is at home in an archive (TRAITS.md 3.4).
    if TREK.Traits then time = time * TREK.Traits.paddFactor(character) end
    return math.max(1, math.floor(math.max(time, 1) / C.PaddReadSpeed))
end

--- A book rebuilt from an entry, **never added to any container**.
---
--- It exists so the engine's own reading calls -- ReadLiterature,
--- JustReadSomething -- have the Literature object they take. Nobody can
--- drop, bag, loot or keep it, because it is in nothing; that is the whole
--- difference from putting a real book in the reader's hands, which would
--- be a duplication exploit (PADD.md section 3).
function Pd.makeBook(entry)
    if not entry or type(entry.type) ~= "string" then return nil end
    local book = U.try("padd.instance", function() return instanceItem(entry.type) end)
    if not book then return nil end
    if entry.md then
        U.try("padd.copyData", function()
            local md = book:getModData()
            for _, key in ipairs(COPY_KEYS) do
                if entry.md[key] ~= nil then md[key] = entry.md[key] end
            end
            if entry.md.printMediaId ~= nil then
                md.printMedia = md.printMedia or {}
                md.printMedia.id = entry.md.printMediaId
            end
        end)
    end
    return book
end

--- The literature half of reading: comfort and the title ticked off.
---
--- Vanilla does this on the server and then asks the reader's own client to
--- do it again (ServerCommands.lua: literature.readLiterature), because the
--- character's stats are kept on both. This is the same call, and it runs
--- wherever it is asked to -- the action on the server, the `paddRead`
--- handler on the client.
function Pd.applyLiterature(character, entry)
    if not entry or entry.kind == "skill" then return false end
    local title = entry.md and entry.md.literatureTitle
    local already = title and U.try("padd.isRead", function()
        return character:isLiteratureRead(title)
    end) == true
    if not already then
        local book = Pd.makeBook(entry)
        if book then
            U.try("padd.readLiterature", function() character:ReadLiterature(book) end)
        end
    end
    if title then
        U.try("padd.addRead", function() character:addReadLiterature(title) end)
    end
    return not already
end

--- Whether this character has finished this entry before -- for the tick in
--- the menu, and nothing else.
function Pd.isRead(character, entry)
    if not entry then return false end
    local title = entry.md and entry.md.literatureTitle
    if title then
        return U.try("padd.isReadT", function()
            return character:isLiteratureRead(title)
        end) == true
    end
    if (entry.pages or 0) > 0 then
        local done = U.try("padd.isReadP", function()
            return character:getAlreadyReadPages(entry.type)
        end) or 0
        return done >= entry.pages
    end
    return false
end

--- The multiplier a skill book of this level grants, from vanilla's table
--- the way ISReadABook:new picks it (lines 490-506).
function Pd.multiplierFor(entry)
    local sb = Pd.skillOf(entry and entry.skill)
    if not sb then return nil end
    local by = { [1] = sb.maxMultiplier1, [3] = sb.maxMultiplier2,
                 [5] = sb.maxMultiplier3, [7] = sb.maxMultiplier4,
                 [9] = sb.maxMultiplier5 }
    return by[entry.level] or 1
end

return Pd
