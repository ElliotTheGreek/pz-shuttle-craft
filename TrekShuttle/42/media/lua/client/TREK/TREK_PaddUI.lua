--[[ Shuttlecraft -- the PADD's menus (PADD.md).

    Everything here is a request. The menus read the library the PADD's mod
    data last carried to this client, which is good enough to build a list and
    grey an option and never good enough to act on: every choice queues a
    timed action, and the action checks again where it completes.

    Two routes in, both OnFillInventoryObjectContextMenu -- build 42 has no
    script hook for "using" an arbitrary item:
      * right-click a **book** (in your inventory or a shelf's loot panel)
        with a PADD on you: Load onto PADD;
      * right-click a **PADD**: Read, Copy library to..., Erase.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Padd"
require "TREK/TREK_PaddActions"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Pd = TREK.Padd

local M = {}
TREK.PaddUI = M

-- How many titles one submenu shows before it is split. A context menu with
-- three hundred rows runs off the screen, and an unlimited library is the
-- design (PADD.md section 9).
M.PAGE = 25

local REFUSAL = {
    illiterate = "IGUI_TREK_PaddIlliterate",
    tooHard = "IGUI_TREK_PaddTooHard",
    tooEasy = "IGUI_TREK_PaddTooEasy",
}

--- The items in a selection, flattened, each once. An entry is an
--- InventoryItem or a stack table with its own `items`, and vanilla's stack
--- repeats its first item as a header -- so this counts each object once.
local function selectedItems(list)
    local out, seen = {}, {}
    if not list then return out end
    local function take(it)
        if instanceof(it, "InventoryItem") and not seen[it] then
            seen[it] = true
            table.insert(out, it)
        end
    end
    for _, v in ipairs(list) do
        if instanceof(v, "InventoryItem") then
            take(v)
        elseif type(v) == "table" and v.items then
            for _, it in ipairs(v.items) do take(it) end
        end
    end
    return out
end

local function tooltip(option, key, ...)
    option.notAvailable = true
    option.toolTip = ISWorldObjectContextMenu.addToolTip()
    option.toolTip.description = getText(key, ...)
end

--- Brings an item into the main inventory first, as vanilla does before it
--- reads a book: a timed action finds its item there and nowhere else.
local function toHand(player, item)
    U.try("padd.transfer", function()
        ISInventoryPaneContextMenu.transferIfNeeded(player, item)
    end)
end

local function queue(action)
    U.try("padd.queue", function() ISTimedActionQueue.add(action) end)
end

---------------------------------------------------------------------------
-- Loading
---------------------------------------------------------------------------
--- The PADD a book should go onto: the first one carried that does not
--- already hold it. Nil, plus whether any PADD was carried at all.
function M.targetFor(player, entry)
    local padds = Pd.carried(player)
    for _, padd in ipairs(padds) do
        if not Pd.has(padd, entry) then return padd, true end
    end
    return nil, #padds > 0
end

function M.onLoad(books, player)
    for _, book in ipairs(books) do
        local entry = Pd.entryOf(book)
        local padd = entry and M.targetFor(player, entry)
        if padd then
            toHand(player, padd)
            queue(TREKLoadPadd:new(player, padd, book))
        end
    end
end

--- The Load option, for every book in the selection at once: a shelf of
--- skill books selected in the loot panel is one click, queued one by one.
function M.addLoad(context, player, books)
    local padds = Pd.carried(player)
    -- **Only with a PADD on you.** Every book in the game would otherwise
    -- grow an option most players will never use; the option is how you
    -- discover what a PADD you are carrying can do, not an advert for one.
    if #padds == 0 then return end

    local todo = {}
    for _, book in ipairs(books) do
        local entry = Pd.entryOf(book)
        if entry and M.targetFor(player, entry) then table.insert(todo, book) end
    end
    local label = #books == 1 and getText("IGUI_TREK_PaddLoad")
                  or getText("IGUI_TREK_PaddLoadMany", tostring(#todo))
    local option = context:addOption(label, todo, M.onLoad, player)
    if #todo == 0 then
        tooltip(option, "IGUI_TREK_PaddAlready")
    end
    return option
end

---------------------------------------------------------------------------
-- Reading
---------------------------------------------------------------------------
function M.onRead(padd, player, key)
    toHand(player, padd)
    queue(TREKReadPadd:new(player, padd, key))
end

local function byName(a, b)
    return tostring(a.name) < tostring(b.name)
end

--- One option per entry, split into pages when there are too many.
local function addEntries(menu, player, padd, entries)
    table.sort(entries, byName)
    local function one(target, e)
        local label = e.name or e.type
        if Pd.isRead(player, e) then
            label = getText("IGUI_TREK_PaddEntryRead", label)
        end
        local option = target:addOption(label, padd, M.onRead, player, Pd.key(e))
        local why = Pd.readRefusal(player, e)
        if why then tooltip(option, REFUSAL[why] or "IGUI_TREK_PaddTooHard") end
    end
    if #entries <= M.PAGE then
        for _, e in ipairs(entries) do one(menu, e) end
        return
    end
    for first = 1, #entries, M.PAGE do
        local last = math.min(#entries, first + M.PAGE - 1)
        local pageOpt = menu:addOption(getText("IGUI_TREK_PaddPage",
                                               tostring(first), tostring(last)),
                                       nil, nil)
        local page = ISContextMenu:getNew(menu)
        menu:addSubMenu(pageOpt, page)
        for i = first, last do one(page, entries[i]) end
    end
end

--- The Read submenu, grouped the way a library is: skill books by skill,
--- then recipes, then everything else.
function M.addRead(context, player, padd)
    local lib = Pd.library(padd)
    local option = context:addOption(getText("IGUI_TREK_PaddRead", tostring(#lib)),
                                     nil, nil)
    if #lib == 0 then
        tooltip(option, "IGUI_TREK_PaddEmpty")
        return option
    end
    local menu = ISContextMenu:getNew(context)
    context:addSubMenu(option, menu)

    local skills, skillNames, recipes, other = {}, {}, {}, {}
    for _, e in ipairs(lib) do
        if e.kind == "skill" and e.skill then
            if not skills[e.skill] then
                skills[e.skill] = {}
                table.insert(skillNames, e.skill)
            end
            table.insert(skills[e.skill], e)
        elseif e.kind == "recipe" then
            table.insert(recipes, e)
        else
            table.insert(other, e)
        end
    end

    if #skillNames > 0 then
        table.sort(skillNames)
        local sOpt = menu:addOption(getText("IGUI_TREK_PaddSkillBooks"), nil, nil)
        local sMenu = ISContextMenu:getNew(menu)
        menu:addSubMenu(sOpt, sMenu)
        for _, name in ipairs(skillNames) do
            local perk = Pd.skillOf(name)
            -- The perk's own display name ("Carpentry"), which vanilla's
            -- SkillBook table already holds as a Perk.
            local label = U.try("padd.perkName", function()
                return perk.perk:getName()
            end) or name
            local kOpt = sMenu:addOption(label, nil, nil)
            local kMenu = ISContextMenu:getNew(sMenu)
            sMenu:addSubMenu(kOpt, kMenu)
            -- Skill books in volume order, not alphabetical: Vol. 1 first.
            table.sort(skills[name], function(a, b)
                return (a.level or 0) < (b.level or 0)
            end)
            for _, e in ipairs(skills[name]) do
                local lbl = e.name or e.type
                if Pd.isRead(player, e) then lbl = getText("IGUI_TREK_PaddEntryRead", lbl) end
                local o = kMenu:addOption(lbl, padd, M.onRead, player, Pd.key(e))
                local why = Pd.readRefusal(player, e)
                if why then tooltip(o, REFUSAL[why] or "IGUI_TREK_PaddTooHard") end
            end
        end
    end
    if #recipes > 0 then
        local rOpt = menu:addOption(getText("IGUI_TREK_PaddRecipes"), nil, nil)
        local rMenu = ISContextMenu:getNew(menu)
        menu:addSubMenu(rOpt, rMenu)
        addEntries(rMenu, player, padd, recipes)
    end
    if #other > 0 then
        local oOpt = menu:addOption(getText("IGUI_TREK_PaddLiterature"), nil, nil)
        local oMenu = ISContextMenu:getNew(menu)
        menu:addSubMenu(oOpt, oMenu)
        addEntries(oMenu, player, padd, other)
    end
    return option
end

---------------------------------------------------------------------------
-- Copying and erasing
---------------------------------------------------------------------------
function M.onCopy(padd, player, target)
    toHand(player, padd)
    toHand(player, target)
    queue(TREKCopyPadd:new(player, padd, target))
end

function M.addCopy(context, player, padd)
    local option = context:addOption(getText("IGUI_TREK_PaddCopy"), nil, nil)
    local others = {}
    for _, p in ipairs(Pd.carried(player)) do
        if p ~= padd then table.insert(others, p) end
    end
    if #others == 0 then
        tooltip(option, "IGUI_TREK_PaddNoOther")
        return option
    end
    if Pd.count(padd) == 0 then
        tooltip(option, "IGUI_TREK_PaddEmpty")
        return option
    end
    local menu = ISContextMenu:getNew(context)
    context:addSubMenu(option, menu)
    for _, p in ipairs(others) do
        menu:addOption(getText("IGUI_TREK_PaddCopyTo", tostring(Pd.count(p))),
                       padd, M.onCopy, player, p)
    end
    return option
end

function M.onErase(padd, player)
    toHand(player, padd)
    queue(TREKErasePadd:new(player, padd))
end

--- Erase is two clicks deep on purpose: the second is the confirmation.
function M.addErase(context, player, padd)
    local n = Pd.count(padd)
    local option = context:addOption(getText("IGUI_TREK_PaddErase"), nil, nil)
    if n == 0 then
        tooltip(option, "IGUI_TREK_PaddEmpty")
        return option
    end
    local menu = ISContextMenu:getNew(context)
    context:addSubMenu(option, menu)
    menu:addOption(getText("IGUI_TREK_PaddEraseConfirm", tostring(n)), padd,
                   M.onErase, player)
    return option
end

---------------------------------------------------------------------------
-- The menu
---------------------------------------------------------------------------
function M.fillInventoryMenu(playerNum, context, items)
    local player = U.player(playerNum)
    if not player then return end
    local selected = selectedItems(items)
    if #selected == 0 then return end

    local padd, books = nil, {}
    for _, it in ipairs(selected) do
        if Pd.isPadd(it) then
            padd = padd or it
        elseif Pd.isBook(it) then
            table.insert(books, it)
        end
    end

    if padd then
        M.addRead(context, player, padd)
        M.addCopy(context, player, padd)
        M.addErase(context, player, padd)
    end
    if #books > 0 then
        M.addLoad(context, player, books)
    end
end

Events.OnFillInventoryObjectContextMenu.Add(M.fillInventoryMenu)

return M
