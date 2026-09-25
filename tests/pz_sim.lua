--[[ A small stand-in for the parts of Project Zomboid the mod touches, so
    tests/test_multiplayer.py can run the real mod code as single player, as a
    server, and as clients connected to it.

    It is not the game. It models exactly the behaviour the mod's multiplayer
    design depends on, as MULTIPLAYER.md records it:

      * isClient()/isServer() per role, and every Lua folder loading everywhere;
      * sendClientCommand reaching OnClientCommand in single player too, and
        sendServerCommand doing nothing there;
      * global mod data: transmit/request/receive, and receiving not storing;
      * squares existing only where a player has loaded them;
      * objects added on the server reaching clients only through the
        transmit calls (py_replicate), never through a client's own edits;
      * zombies owned by one client (isRemoteZombie on the others).

    Everything crossing between runtimes goes through Python as plain data,
    so a command carrying something that could not cross a network fails.

    The runtime sets SIM_ROLE ("sp", "server" or "client") and SIM_ID before
    loading this file.
]]

_G.unpack = _G.unpack or table.unpack

-- Kahlua, the game's Lua, lacks some of the standard library. Remove what the
-- game does not have, so using it fails here instead of in game.
next = nil
math.huge = nil
SIM = { log = {}, notes = {}, lamps = 0, voidX = 24000 }

function print(...)
    local parts = {}
    for i = 1, select("#", ...) do parts[#parts + 1] = tostring(select(i, ...)) end
    table.insert(SIM.log, table.concat(parts, " "))
end

function isClient() return SIM_ROLE == "client" end
function isServer() return SIM_ROLE == "server" end
function getCellSizeInSquares() return 256 end

-- getDebug() is false on purpose. A mechanism that only works under -debug is
-- no use to a Workshop subscriber, so the simulation never pretends otherwise.
local core = {
    getDebug = function() return false end,
    getKey = function(_, name) return 0 end,
    getScreenWidth = function() return 1920 end,
    getScreenHeight = function() return 1080 end,
    -- Anything pinned to a world position is drawn at its own size divided by
    -- the zoom (ISBaseIcon:updateZoom is the pattern). 1.0 keeps the sums
    -- readable; the point of having it at all is that a caller which forgets
    -- to ask would draw the torpedo at a fixed screen size for ever.
    getZoom = function() return 1.0 end,
}
function getCore() return core end

-- Textures are not modelled; the tests that care assert on the *name* of an
-- icon file existing on disk (tests/test_assets.py), not on pixels.
function getTexture(path)
    return { path = path,
             getWidth = function() return 32 end,
             getHeight = function() return 32 end }
end
function getText(key, ...)
    local out = key
    for i = 1, select("#", ...) do out = out .. "|" .. tostring(select(i, ...)) end
    return out
end
function getTimestampMs() return py_clock() end

-- Text measurement, roughly. tests/test_helm.py is where a panel's layout is
-- actually checked -- against a generous per-glyph width, with every draw call
-- recorded -- so all this has to do is answer plausibly when a panel here
-- draws a frame.
local textManager = {
    MeasureStringX = function(_, _, text) return math.floor(#tostring(text or "") * 6.5) end,
    MeasureStringY = function() return 14 end,
}
function getTextManager() return textManager end

---------------------------------------------------------------------------
-- Java-ish lists
---------------------------------------------------------------------------
local function jlist(t)
    t = t or {}
    return {
        _t = t,
        size = function() return #t end,
        get = function(_, i) return t[i + 1] end,
        add = function(_, v) table.insert(t, v) end,
    }
end
SIM.jlist = jlist

---------------------------------------------------------------------------
-- Events
---------------------------------------------------------------------------
Events = setmetatable({}, { __index = function(self, name)
    local ev = { handlers = {} }
    function ev.Add(fn) table.insert(ev.handlers, fn) end
    function ev.Remove(fn)
        for i, h in ipairs(ev.handlers) do
            if h == fn then table.remove(ev.handlers, i) return end
        end
    end
    rawset(self, name, ev)
    return ev
end })

---------------------------------------------------------------------------
-- The radio, and the recorded media on it
---------------------------------------------------------------------------
-- getZomboidRadio():getRecordedMedia() is how anything reaches a tape's
-- recording. It is stubbed here rather than left nil because the authority
-- asks it while stocking the tape shelf, and vanilla has server-side call
-- sites for it (server/radio/ISDynamicRadio.lua) which is the evidence that
-- it may.
--
-- Two things this models on purpose:
--
--  * **getMediaData answers nil for an id nobody registered.** That is the
--    engine's answer and it is the one that matters: a tape pointed at a
--    recording that was never registered is a blank tape, and a stub that
--    invented one would hide the whole class of fault.
--  * **register refuses a duplicate id, loudly.** The real sequence is that
--    vanilla's ISRecordedMedia walks RecMedia *and then* the engine fires
--    OnInitRecordedMedia, so anything of ours listening to that event runs
--    second and can register the same id twice. SIM.initRecordedMedia does
--    both halves in that order, so a handler without a guard fails here
--    instead of in somebody's save.
local RecordedMediaSim = { data = {} }

function RecordedMediaSim:getMediaData(id) return self.data[id] end

function RecordedMediaSim:getCategories()
    local seen, out = {}, {}
    for _, d in pairs(self.data) do
        if not seen[d.category] then
            seen[d.category] = true
            table.insert(out, d.category)
        end
    end
    return jlist(out)
end

function RecordedMediaSim:register(category, id, display, spawning)
    if self.data[id] then
        error("recorded media registered twice: " .. tostring(id), 0)
    end
    local d = {
        id = id, category = category, display = display,
        spawning = spawning or 0, lines = {},
        title = nil, subtitle = nil, author = nil, extra = nil,
    }
    function d:getId() return self.id end
    function d:getCategory() return self.category end
    function d:getTitleEN() return self.title end
    function d:getLineCount() return #self.lines end
    function d:setTitle(v) self.title = v end
    function d:setSubtitle(v) self.subtitle = v end
    function d:setAuthor(v) self.author = v end
    function d:setExtra(v) self.extra = v end
    function d:addLine(text, r, g, b, codes)
        table.insert(self.lines, { text = text, r = r, g = g, b = b, codes = codes })
    end
    self.data[id] = d
    return d
end

function getZomboidRadio()
    return { getRecordedMedia = function() return RecordedMediaSim end }
end

--- The engine's own order: vanilla's registration walk, then the event.
function SIM.initRecordedMedia()
    local table_ = rawget(_G, "RecMedia")
    if type(table_) == "table" then
        local ids = {}
        for k in pairs(table_) do table.insert(ids, k) end
        table.sort(ids)
        for _, id in ipairs(ids) do
            local v = table_[id]
            local d = RecordedMediaSim:register(v.category, id,
                                                v.itemDisplayName, v.spawning or 0)
            d:setTitle(v.title)
            d:setSubtitle(v.subtitle)
            d:setAuthor(v.author)
            d:setExtra(v.extra)
            for _, j in ipairs(v.lines or {}) do
                d:addLine(j.text, j.r, j.g, j.b, j.codes)
            end
        end
    end
    SIM.fire("OnInitRecordedMedia", RecordedMediaSim)
end

function SIM.recordedMedia() return RecordedMediaSim end

function SIM.fire(name, ...)
    local ev = rawget(Events, name)
    if not ev then return end
    for _, h in ipairs(ev.handlers) do h(...) end
end

---------------------------------------------------------------------------
-- Items and containers
---------------------------------------------------------------------------
function instanceItem(id)
    if type(id) ~= "string" or not id:find("%.") then return nil end
    -- Mod data on an item, because that is where the hypospray keeps its
    -- doses. A stub without it would make Med.doses() return 0 for every
    -- injector in the world and the test would prove the wrong thing.
    -- `class` so instanceof(item, "InventoryItem") answers the way the engine
    -- does. Without it the mod's context-menu code, which has to tell a single
    -- item from a stack, sees neither and offers nothing at all.
    SIM.nextItemId = (SIM.nextItemId or 1000) + 1
    local it = { fullType = id, modData = {}, class = "InventoryItem",
                 id = SIM.nextItemId,
                 ammo = 0, chambered = false, jammed = false, condition = 10,
                 -- Negative is the engine's "nobody has set this yet", and it
                 -- is what makes a dropped item pick its own angle below.
                 worldXRotation = 0, worldYRotation = 0, worldZRotation = -1,
                 getFullType = function(self) return self.fullType end,
                 getModData = function(self) return self.modData end,
                 -- A weapon's reach, which the phaser's bolt is drawn to.
                 getMaxRange = function(self) return self.maxRange or 18 end }

    -- The clothing half. `getClothingItem()` is how the mod asks the engine
    -- whether a garment's GUID actually resolved, and the honest answer for
    -- anything that is not clothing is **nil** -- which is exactly the value
    -- a uniform gets when its fileGuidTable row is missing. A stub that
    -- returned a table for everything would make S.uniformReport() report
    -- success for a shirt, a hammer and a uniform alike, which is the shape
    -- of "the simulation has to be as unkind as the engine".
    function it:getClothingItem()
        local entry = SIM.clothing and SIM.clothing[self.fullType]
        if not entry then return nil end
        return {
            getMaleModel = function() return entry.male end,
            getFemaleModel = function() return entry.female end,
            hasModel = function() return entry.male ~= nil end,
            getTextureChoices = function() return jlist({ entry.texture }) end,
        }
    end

    -- The recorded-media half. A fresh tape carries **no recording** -- the
    -- engine's index is -1 until something sets it -- and that is the whole
    -- failure this has to be able to express: a blank tape sits in the shelf,
    -- goes into the television and does nothing, with nothing in any log. A
    -- stub that answered a table here would make the tape shelf untestable in
    -- exactly the direction that matters.
    function it:getMediaData() return self.mediaData end
    function it:setRecordedMediaData(data) self.mediaData = data end
    function it:setRecordedMediaIndexInteger(n) self.mediaIndex = n end
    function it:isRecordedMedia() return self.mediaData ~= nil end

    function it:getWorldZRotation() return self.worldZRotation end
    function it:setWorldZRotation(v) self.worldZRotation = v end
    function it:getWorldYRotation() return self.worldYRotation end
    function it:setWorldYRotation(v) self.worldYRotation = v end
    function it:getWorldXRotation() return self.worldXRotation end
    function it:setWorldXRotation(v) self.worldXRotation = v end

    -- The weapon half, because a **phaser can be in a pocket now**: the
    -- replicator makes one into the player's own inventory, and TREK_Phaser's
    -- sweep then reads and writes all of this on it every tick. Without it
    -- the sweep threw once per concern -- which is a real warning about a
    -- stub, not about the mod, and exactly the kind of gap that makes the
    -- simulation kinder than the engine in one direction and harsher in the
    -- other.
    function it:getMaxAmmo() return 60 end
    function it:getCurrentAmmoCount() return self.ammo end
    function it:setCurrentAmmoCount(n) self.ammo = n end
    function it:isRoundChambered() return self.chambered end
    function it:setRoundChambered(v) self.chambered = v end
    function it:setSpentRoundCount() end
    function it:setSpentRoundChambered() end
    function it:isJammed() return self.jammed end
    function it:setJammed(v) self.jammed = v end
    function it:getConditionMax() return 10 end
    function it:getCondition() return self.condition end
    function it:setCondition(n) self.condition = n end

    -- Identity and whereabouts, which is how the engine resolves an item
    -- sent over the network, and how a timed action finds its item again.
    function it:getID() return self.id end
    function it:getContainer() return self.container end
    function it:getWorldItem() return self.worldItem end
    function it:hasModData()
        for _ in pairs(self.modData) do return true end
        return false
    end
    function it:getName() return self.displayName or bareTypeOf(self.fullType) end
    function it:getType() return bareTypeOf(self.fullType) end
    function it:hasTag(tag) return self.tags ~= nil and self.tags[tag] == true end

    -- The literature half (PADD.md): what ISReadABook reads off a book.
    local lit = SIM.literature and SIM.literature[id]
    if lit then
        it.class = "Literature"
        it.displayName = lit.name
        it.tags = {}
        if lit.consume then it.tags[ItemTag.CONSUME_ON_READ] = true end
        function it:getNumberOfPages() return lit.pages or 0 end
        function it:getSkillTrained() return lit.skill or "" end
        function it:getLvlSkillTrained() return lit.lvl or 0 end
        function it:getMaxLevelTrained() return lit.maxLvl or 0 end
        function it:getLearnedRecipes()
            local l = jlist(lit.recipes or {})
            function l:isEmpty() return self:size() == 0 end
            return l
        end
        function it:canBeWrite() return lit.writable == true end
        function it:getStressChange() return lit.stress or 0 end
    end
    return it
end

--- The bare type, for items -- defined ahead of the catalogue's copy.
function bareTypeOf(fullType)
    return (tostring(fullType):gsub("^.*%.", ""))
end

--- The bare type, the way the engine's recursive lookups compare it:
--- "TrekShuttle.TrekTricorder" -> "TrekTricorder".
local function bareType(fullType)
    return (tostring(fullType):gsub("^.*%.", ""))
end

---------------------------------------------------------------------------
-- The item catalogue
---------------------------------------------------------------------------
-- What getAllItems() hands back: every `item` script in the game, as Item
-- objects. The replicator reads this instead of a hand-written recipe list.
--
-- **The obsolete and hidden ones are in here on purpose**, along with a
-- Moveables entry, because they are the trap: an obsolete item is still in
-- the scripts, still has a name and a category, and returns nil from
-- instanceItem -- so a catalogue that forgets vanilla's filter fills with
-- entries that look exactly like working ones and make nothing. A stub that
-- only listed usable items would let that straight through.
--
-- The list is small and fixed rather than scraped from the installed game:
-- what is being tested is the filtering and the arithmetic, and a test whose
-- expectations move when somebody patches Project Zomboid is not a test.
SIM.items = {}

local function scriptItem(fullName, opts)
    opts = opts or {}
    local module = fullName:match("^(.-)%.") or "Base"
    local it = {
        fullName = fullName,
        displayName = opts.name or bareType(fullName),
        category = opts.category or "Item",
        module = module,
        weight = opts.weight or 1.0,
        obsolete = opts.obsolete == true,
        hidden = opts.hidden == true,
        texture = opts.texture ~= false and { path = fullName } or nil,
    }
    function it:getFullName() return self.fullName end
    function it:getDisplayName() return self.displayName end
    function it:getDisplayCategory() return self.category end
    function it:getModuleName() return self.module end
    function it:getActualWeight() return self.weight end
    function it:getObsolete() return self.obsolete end
    function it:isHidden() return self.hidden end
    function it:getNormalTexture() return self.texture end
    table.insert(SIM.items, it)
    return it
end
SIM.scriptItem = scriptItem

scriptItem("Base.Bandage",      { name = "Bandage", category = "FirstAid", weight = 0.1 })
scriptItem("Base.Hammer",       { name = "Hammer", category = "Tool", weight = 2.0 })
scriptItem("Base.TinnedBeans",  { name = "Tinned Beans", category = "Food", weight = 0.8 })
scriptItem("Base.Axe",          { name = "Axe", category = "Weapon", weight = 3.0 })
scriptItem("Base.Generator",    { name = "Generator", category = "Appliance", weight = 60.0 })
-- No icon at all: the catalogue holds other people's mods, and nothing in
-- the panel may assume getNormalTexture() answered with something.
scriptItem("Base.OddOne",       { name = "Odd One", category = "Item", texture = false })
-- The three the filter has to remove.
scriptItem("Base.OldSpanner",   { name = "Old Spanner", obsolete = true })
scriptItem("Base.SecretThing",  { name = "Secret Thing", hidden = true })
scriptItem("Moveables.Moveable_fridge", { name = "Fridge", category = "Furniture" })

--- The mod's own items, declared the way media/scripts/trekshuttle.txt does.
--- Added by name so the test can assert that the ship knows its own stores,
--- and that the spec-only warhead is not among them.
--- The last four are the ones the replicator must **refuse**, and they are
--- listed here for that reason: a blocklist tested against a catalogue that
--- never offered the item in the first place passes whatever it says. That is
--- not hypothetical -- deleting the dilithium entry from C.ReplicatorBlocked
--- changed nothing at all until the crystal was added here, and the Doctor is
--- the same bug waiting to happen: a player who could replicate one would
--- stand a second EMH in the galley.
--- The six uniforms are here for the same reason the crystal is: the armoury
--- guarantees one of each (`special = "uniforms"`), and a guarantee checked
--- against a catalogue that has never heard of the item passes whatever the
--- locker actually ends up holding.
for _, id in ipairs({ "TrekShuttle.TrekPhaser", "TrekShuttle.TrekHypospray",
                      "TrekShuttle.TrekBatleth", "TrekShuttle.TrekRationPack",
                      "TrekShuttle.TrekDermalRegen", "TrekShuttle.TrekTricorder",
                      "TrekShuttle.TrekMedTricorder", "TrekShuttle.TrekTorpedo",
                      "TrekShuttle.TrekShuttleHull", "TrekShuttle.TrekHelmConsole",
                      "TrekShuttle.TrekDilithium", "TrekShuttle.TrekEMH",
                      "TrekShuttle.TrekUniformDutyCommand",
                      "TrekShuttle.TrekUniformDutyOperations",
                      "TrekShuttle.TrekUniformDutyScience",
                      "TrekShuttle.TrekUniformDressCommand",
                      "TrekShuttle.TrekUniformDressOperations",
                      "TrekShuttle.TrekUniformDressScience",
                      -- The downed ensign's six figures: Furniture items the
                      -- replicator must refuse, listed for the crystal's
                      -- reason -- a blocklist checked against a catalogue
                      -- that never offered them proves nothing.
                      "TrekShuttle.TrekEnsignMCommand",
                      "TrekShuttle.TrekEnsignMOperations",
                      "TrekShuttle.TrekEnsignMScience",
                      "TrekShuttle.TrekEnsignFCommand",
                      "TrekShuttle.TrekEnsignFOperations",
                      "TrekShuttle.TrekEnsignFScience",
                      -- Balso tonic: refused for canon's sake, and listed
                      -- for the same reason as the six above.
                      "TrekShuttle.TrekBalsoTonic",
                      -- The PADD: the ship knows its pattern, and a
                      -- replicated one is blank (PADD.md).
                      "TrekShuttle.TrekPADD" }) do
    scriptItem(id, { name = bareType(id), category = "Starfleet", weight = 0.6 })
end

-- What a rescue teaches the ship (C.RescuePatterns). Real vanilla ids, in the
-- catalogue so R.learn() can find their rows: a reward checked against a
-- catalogue that has never heard of the pattern would teach nothing and pass.
for _, id in ipairs({ "Base.Antibiotics", "Base.SutureNeedle", "Base.Splint",
                      "Base.Disinfectant", "Base.Tweezers", "Base.Pills" }) do
    scriptItem(id, { name = bareType(id), category = "FirstAid", weight = 0.1 })
end

--- Which items the engine would hand back a ClothingItem for.
---
--- Only the six uniforms, and deliberately nothing else: a phaser asked the
--- same question answers nil in the engine and has to answer nil here, or
--- S.uniformReport() would report a hammer as a working garment.
---
--- These mirror what tools/gen_uniform.py writes into the clothing XMLs;
--- tests/test_assets.py is what holds the files on disk to the same shape.
--- What this cannot prove is that the mod's fileGuidTable.xml *merged* in a
--- real game -- the engine reads it inside a catch that only reaches
--- ExceptionLogger -- which is the whole reason TREK_Uniform() exists.
SIM.clothing = {}
for _, row in ipairs({
        { "TrekUniformDutyCommand",     "bob_boilersuit", "kate_boilersuit", "duty_command" },
        { "TrekUniformDutyOperations",  "bob_boilersuit", "kate_boilersuit", "duty_operations" },
        { "TrekUniformDutyScience",     "bob_boilersuit", "kate_boilersuit", "duty_science" },
        { "TrekUniformDressCommand",    "bob_judegsrobe", "kate_judegsrobe", "dress_command" },
        { "TrekUniformDressOperations", "bob_judegsrobe", "kate_judegsrobe", "dress_operations" },
        { "TrekUniformDressScience",    "bob_judegsrobe", "kate_judegsrobe", "dress_science" },
    }) do
    SIM.clothing["TrekShuttle." .. row[1]] = {
        male = "skinned\\clothes\\" .. row[2],
        female = "skinned\\clothes\\" .. row[3],
        texture = "clothes\\trek\\" .. row[4],
    }
end

function getAllItems() return jlist(SIM.items) end

function getScriptManager()
    return {
        getAllItems = function() return jlist(SIM.items) end,
        FindItem = function(_, id)
            for _, it in ipairs(SIM.items) do
                if it.fullName == id then return it end
            end
            return nil
        end,
    }
end

function SIM.container(capacity)
    local c = { items = {}, capacity = capacity or 40, explored = false }
    --- Adds one item, and **refuses when the container is full**.
    ---
    --- Modelled because the engine does it silently: ItemContainer drops what
    --- it is handed once the contents weigh as much as the capacity, with no
    --- error anywhere, which is why U.stockEach reads the container back and
    --- why the replicator counts the tray after every single item. A stub
    --- that accepted everything would make a full tray look like a success.
    function c:AddItem(item)
        if type(item) == "string" then item = instanceItem(item) end
        if not item then return nil end
        if self:getContentsWeight() + 0.5 > self.capacity then return nil end
        table.insert(self.items, item)
        item.container = self
        return item
    end
    function c:contains(item)
        for _, held in ipairs(self.items) do
            if rawequal(held, item) then return true end
        end
        return false
    end
    function c:containsID(id)
        for _, held in ipairs(self.items) do
            if held.id == id then return true end
        end
        return false
    end
    function c:isInCharacterInventory(chr)
        return self.ownerName ~= nil and chr ~= nil and self.ownerName == chr.name
    end
    function c:getParent() return self.parentObject end
    function c:getItems() return jlist(self.items) end
    --- Takes one item back out. Real, not a no-op: the refit migration empties
    --- a doomed locker onto the deck, and a Remove that did nothing would let
    --- the item be both spilled and destroyed with the container.
    function c:Remove(item)
        for i, held in ipairs(self.items) do
            if rawequal(held, item) then
                table.remove(self.items, i)
                item.container = nil
                return
            end
        end
    end
    function c:getCapacity() return self.capacity end
    function c:getContentsWeight() return #self.items * 0.5 end
    function c:setExplored(v) self.explored = v end
    function c:setDirty() end
    function c:setDrawDirty() end
    --- Really searches, and really compares the **bare** type.
    ---
    --- This used to return an empty list, which was fine while nothing asked
    --- it anything. It is the phaser sweep's lookup and the medical set's, and
    --- a stub that always answers "you are carrying nothing" would let a
    --- broken lookup pass every test in this file.
    function c:getAllTypeRecurse(bare)
        local out = {}
        for _, item in ipairs(self.items) do
            if bareType(item.fullType) == bare then table.insert(out, item) end
        end
        return jlist(out)
    end
    function c:containsTypeRecurse(bare)
        return self:getAllTypeRecurse(bare):size() > 0
    end
    --- Everything that satisfies a predicate. Vanilla's own way of asking for
    --- the lot is `getAllEvalRecurse(function() return true end)`
    --- (ISInventoryPaneContextMenu.lua:1355), which is how the replicator
    --- reads what a player is carrying. Nothing here nests containers, so the
    --- recursion is the same list -- what is modelled is the call, not bags
    --- inside bags.
    function c:getAllEvalRecurse(pred)
        local out = {}
        for _, item in ipairs(self.items) do
            if pred == nil or pred(item) then table.insert(out, item) end
        end
        return jlist(out)
    end
    return c
end

--- Sends one item the server put in a container to the client that can see
--- it. Two kinds of container, and they reach different people:
---
---   * a container on a world object goes to everyone, because everyone can
---     walk up to it and open it;
---   * **a player's own inventory goes to that player and nobody else.** That
---     is the replicator's route -- the server makes the item and hands it
---     over -- and it is the engine's own idiom: server/ClientCommands.lua
---     does `player:getInventory():AddItem(item)` followed by this call in a
---     dozen places, on a validated client command, which is exactly the
---     shape the replicator has.
function sendAddItemToContainer(container, item)
    if not isServer() then error("sendAddItemToContainer off the server") end
    if container.ownerName then
        py_replicate("playerItem", { x = 0, y = 0, z = 0,
                                     who = container.ownerName,
                                     item = item.fullType })
        return
    end
    local obj = container.parentObject
    if obj and obj.square then
        py_replicate("containerItem", { x = obj.square.x, y = obj.square.y, z = obj.square.z,
                                        sprite = obj.spriteName, item = item.fullType })
    end
end

--- The other direction: an item the server took *out* of a container.
---
--- Vanilla's own pairing -- ISBuildUtil.lua removes an item and follows it
--- with this call -- and the warp core needs it, because a crystal loaded
--- into the ship comes out of the player's own inventory on the server and
--- their client has to be told.
function sendRemoveItemFromContainer(container, item)
    if not isServer() then error("sendRemoveItemFromContainer off the server") end
    if container.ownerName then
        py_replicate("playerItemGone", { x = 0, y = 0, z = 0,
                                         who = container.ownerName,
                                         item = item.fullType })
        return
    end
    local obj = container.parentObject
    if obj and obj.square then
        py_replicate("containerItemGone",
                     { x = obj.square.x, y = obj.square.y, z = obj.square.z,
                       sprite = obj.spriteName, item = item.fullType })
    end
end

---------------------------------------------------------------------------
-- Objects
---------------------------------------------------------------------------
local ObjectMT = {}
ObjectMT.__index = ObjectMT

function SIM.object(sprite, class)
    local o = setmetatable({ spriteName = sprite, modData = {}, class = class or "IsoObject" }, ObjectMT)
    return o
end

-- The tile flags a sprite carries. Only the one the mod asks about: whether
-- a floor is water, which is how the ensign avoids sitting in a pond. A test
-- marks a square `water = true` and its floor answers for it.
IsoFlagType = IsoFlagType or { water = "water" }
IsoFlagType.collideN = IsoFlagType.collideN or "collideN"
IsoFlagType.collideW = IsoFlagType.collideW or "collideW"

function ObjectMT:getSprite()
    local name = self.spriteName
    local obj = self
    return {
        getName = function() return name end,
        getProperties = function()
            return {
                has = function(_, flag)
                    if flag == IsoFlagType.water then
                        return obj.isFloor == true and obj.square ~= nil
                               and obj.square.water == true
                    end
                    return false
                end,
            }
        end,
    }
end
function ObjectMT:getModData() return self.modData end
function ObjectMT:getSquare() return self.square end
function ObjectMT:createContainersFromSpriteProperties()
    if self.container then return end
    -- Which sprites hold things. The tileset is the real answer and this is a
    -- list of substrings, so **a new fitting has to be added here or it is
    -- silently scenery in every test** -- which is exactly what happened to
    -- the dilithium chamber (`location_business_machinery_01_33`, a Tool
    -- Cabinet) the first time it was placed.
    if self.spriteName:find("counter") or self.spriteName:find("storage")
       or self.spriteName:find("refrigeration") or self.spriteName:find("cooking")
       or self.spriteName:find("medical") or self.spriteName:find("shelving")
       or self.spriteName:find("military") or self.spriteName:find("machinery")
       or self.spriteName:find("CONTAINER") then
        self.container = SIM.container(40)
        self.container.parentObject = self
        -- A fridge tile is a fridge and a freezer (V8: the combo's secondary
        -- container), and code that walks only the first destroys the second.
        if self.spriteName:find("refrigeration") then
            self.freezer = SIM.container(20)
            self.freezer.parentObject = self
        end
    end
end
function ObjectMT:getContainerCount()
    return (self.container and 1 or 0) + (self.freezer and 1 or 0)
end
function ObjectMT:getContainerByIndex(i)
    if i == 0 then return self.container end
    if i == 1 then return self.freezer end
    return nil
end
function ObjectMT:getContainer() return self.container end
function ObjectMT:getItemContainer() return self.container end
function ObjectMT:getFluidCapacity() return self.fluid and self.fluid.capacity or 0 end
function ObjectMT:getFluidAmount() return self.fluid and self.fluid.amount or 0 end
function ObjectMT:addFluid(_, n)
    if not self.fluid then return end
    self.fluid.amount = math.min(self.fluid.capacity, self.fluid.amount + n)
    if isServer() then
        py_replicate("fluid", { x = self.square.x, y = self.square.y, z = self.square.z,
                                sprite = self.spriteName, amount = self.fluid.amount })
    end
end
--- IsoObject.emptyFluid: Empty() then sync() on the server (bci 55-60),
--- the same shape as addFluid -- it reaches every client by itself.
function ObjectMT:emptyFluid()
    if not self.fluid then return end
    self.fluid.amount = 0
    if isServer() then
        py_replicate("fluid", { x = self.square.x, y = self.square.y, z = self.square.z,
                                sprite = self.spriteName, amount = 0 })
    end
end
function ObjectMT:hasWater() return self:getFluidAmount() > 0 end
function ObjectMT:transmitModData()
    if isServer() then
        py_replicate("modData", { x = self.square.x, y = self.square.y, z = self.square.z,
                                  sprite = self.spriteName, modData = self.modData })
    end
end
function ObjectMT:getItem() return self.item end
function ObjectMT:setIgnoreRemoveSandbox() end

---------------------------------------------------------------------------
-- Locks
---------------------------------------------------------------------------
-- A door, a window or a player-built thumpable, with the four lock flags the
-- engine really has and the sync call that really has to be made.
--
-- **The sync is modelled because the engine's is not symmetric.** In build 42
-- `setLockedByKey(b)` fires IsoDoor.sync() itself -- but only when
-- `!GameServer.server`, so a door opened by the authority sends no packet at
-- all and stays shut on every client's screen. `obj:sync()` is the explicit
-- call that covers both, and SIM.synced is how a test proves it was made.
SIM.synced = {}

function ObjectMT:isLocked() return self.locked == true end
function ObjectMT:setIsLocked(v) self.locked = v end
function ObjectMT:isLockedByKey() return self.lockedByKey == true end
function ObjectMT:setLockedByKey(v)
    self.lockedByKey = v
    self.locked = v
end
function ObjectMT:isLockedByPadlock() return self.padlock == true end
function ObjectMT:setLockedByPadlock(v) self.padlock = v end
function ObjectMT:sync()
    table.insert(SIM.synced, self)
end

--- Puts a locked thing on a square. `kind` is the Iso class instanceof will
--- report, so a test can build a padlocked IsoThumpable as well as a plain
--- key-locked IsoDoor.
function SIM.lock(x, y, z, kind, opts)
    opts = opts or {}
    local sq = SIM.rawSquare(x, y, z)
    local o = SIM.object(opts.sprite or "fixtures_doors_01_0", kind or "IsoDoor")
    o.square = sq
    o.locked = opts.locked ~= false
    o.lockedByKey = opts.lockedByKey ~= false
    o.padlock = opts.padlock == true
    table.insert(sq.objects, o)
    return o
end

IsoObject = {}
function IsoObject.new(sq, sprite, name)
    return SIM.object(sprite)
end

--- A television, which is a different Java class from the sprite that draws
--- one. The cabin's viewscreen was a plain IsoObject wearing a TV's picture
--- for three versions -- drawn, present and impossible to turn on -- so the
--- simulation models the distinction the engine makes rather than the one the
--- sprite name suggests.
---
--- The constructor is vanilla's own, from ISMoveableSpriteProps.lua:2136:
--- (cell, square, sprite) rather than IsoObject's (square, spriteName).
IsoTelevision = {}
function IsoTelevision.new(_cell, _sq, sprite)
    local name = type(sprite) == "table" and sprite.name or sprite
    return SIM.object(name, "IsoTelevision")
end

--- A sprite handle. The engine hands back an IsoSprite; all the mod does with
--- it is give it straight back to a constructor, so it only has to carry the
--- name.
function getSprite(name)
    return { name = name, getName = function() return name end }
end

--- DeviceData, cloned off the item that declares the device's channels and
--- what media it accepts. Base.TvWideScreen is AcceptMediaType = 1, the tape
--- type, which is why the mod needs no VCR: in build 42 a television is one.
---
--- The power half is modelled the way the bytecode actually works, because
--- the mod's whole answer to "the shuttle has its own electricity" rests on
--- it and a stub that simply said yes would prove nothing:
---
---   canBePoweredHere()   true at once if isBatteryPowered; otherwise the
---                        square's grid/generator, which the cabin has not
---   setIsTurnedOn(true)  refuses unless canBePoweredHere(), and forces off
---                        when the device is battery powered and flat
---   SIM.drainDevices(m)  what DeviceData.update does per game minute: a
---                        device that is on loses useDelta, and switches
---                        *itself* off when it reaches zero
local function makeDeviceData(id, useDelta)
    local d = {
        fromItem = id, mediaType = 1, useDelta = useDelta or 0.007,
        isBatteryPowered = false, hasBattery = false,
        power = 0.0, isTurnedOn = false,
    }
    function d:setIsBatteryPowered(v) self.isBatteryPowered = v == true end
    function d:getIsBatteryPowered() return self.isBatteryPowered end
    function d:setHasBattery(v) self.hasBattery = v == true end
    function d:getHasBattery() return self.hasBattery end
    function d:setPower(v) self.power = math.max(0, math.min(1, v or 0)) end
    function d:getPower() return self.power end
    function d:getUseDelta() return self.useDelta end
    function d:getIsTurnedOn() return self.isTurnedOn end
    function d:canBePoweredHere()
        if self.isBatteryPowered then return true end
        -- No grid and no generator in the cabin's cell, ever.
        return false
    end
    function d:setIsTurnedOn(v)
        if not self:canBePoweredHere() then self.isTurnedOn = false return end
        if self.isBatteryPowered and self.power <= 0 then
            self.isTurnedOn = false
            return
        end
        self.isTurnedOn = v == true
    end
    return d
end

function ObjectMT:cloneDeviceDataFromItem(id)
    if not id then return nil end
    return makeDeviceData(id)
end
function ObjectMT:setDeviceData(data) self.deviceData = data end
function ObjectMT:getDeviceData() return self.deviceData end

--- Runs `minutes` game minutes of DeviceData.update over every device in the
--- world. This is the drain the mod's per-minute top-up exists to outrun.
function SIM.drainDevices(minutes)
    -- SIM.squares rather than the local, which is declared further down.
    for _, sq in pairs(SIM.squares or {}) do
        for _, o in ipairs(sq.objects) do
            local d = o.deviceData
            if d and d.isTurnedOn and d.isBatteryPowered and d.power > 0 then
                d:setPower(d.power - d.useDelta * minutes)
            end
            if d and d.isTurnedOn and d.isBatteryPowered and d.power <= 0 then
                d.isTurnedOn = false
            end
        end
    end
end

-- The one piece of the class hierarchy anything here asks about: a book is
-- an InventoryItem too, and a menu that handles "an item" must see it.
SIM.SUPER = { Literature = "InventoryItem" }
function instanceof(o, class)
    if type(o) ~= "table" then return false end
    local c = o.class
    while c do
        if c == class then return true end
        c = SIM.SUPER[c]
    end
    return false
end

ComponentType = { FluidContainer = {} }
function ComponentType.FluidContainer:CreateComponent()
    local f = { capacity = 0, amount = 0 }
    function f:setCapacity(n) self.capacity = n end
    function f:addFluid(_, n) self.amount = math.min(self.capacity, self.amount + n) end
    return f
end
GameEntityFactory = {}
function GameEntityFactory.AddComponent(obj, _, f) obj.fluid = f end
FluidType = { Water = "Water" }

---------------------------------------------------------------------------
-- Squares and the cell
---------------------------------------------------------------------------
local squares = {}
SIM.squares = squares

local function key(x, y, z) return x .. "," .. y .. "," .. z end

local SquareMT = {}
SquareMT.__index = SquareMT

local function newSquare(x, y, z)
    local sq = setmetatable({ x = x, y = y, z = z, objects = {}, worldObjects = {},
                              solid = false, occupied = false }, SquareMT)
    squares[key(x, y, z)] = sq
    return sq
end

function SquareMT:getX() return self.x end
function SquareMT:getY() return self.y end
function SquareMT:getZ() return self.z end

--- Everything on the square, **world items included**.
---
--- The engine keeps one object list per square and a dropped item is an
--- IsoWorldInventoryObject in it; getWorldObjects() is a filtered view of the
--- same list, not a second one. The stub used to keep them apart, which made
--- two guards untestable and one of them is load-bearing:
---
---   * U.clearSquare and TREK_Build's clearSquare both skip world items on
---     purpose -- that is where a player's dropped things live, and where the
---     replicator, the warp core and the Doctor stand. With world items
---     invisible to getObjects() those skips could not fail;
---   * B.forceRebuild walks this list and removes everything but the floor,
---     which really does delete all three machines. TREK_Rebuild() leaving the
---     Doctor standing while s.emh says he is up is a bug the build phase
---     exists to repair, and it could not be reproduced here at all.
function SquareMT:getObjects()
    local all = {}
    for _, o in ipairs(self.objects) do table.insert(all, o) end
    for _, w in ipairs(self.worldObjects) do table.insert(all, w) end
    return jlist(all)
end

function SquareMT:getWorldObjects() return jlist(self.worldObjects) end
function SquareMT:getFloor()
    for _, o in ipairs(self.objects) do if o.isFloor then return o end end
    return nil
end
function SquareMT:isSolid() return self.solid end
function SquareMT:isSolidTrans() return false end
--- A wall on the square's north or west edge. A test marks `wallN` or
--- `wallW`; the flight's obstacle guard asks exactly this, the way vanilla's
--- builder does (ISBuildingObject.lua:309).
function SquareMT:has(flag)
    if flag == IsoFlagType.collideN then return self.wallN == true end
    if flag == IsoFlagType.collideW then return self.wallW == true end
    if flag == IsoFlagType.water then return self.water == true end
    return false
end
function SquareMT:isFree() return not self.occupied end
--- A vehicle stands over a 3x5 box of squares around its position (the
--- shuttle's size; the only vehicle the tests spawn).
function SquareMT:getVehicleContainer()
    for _, v in ipairs(SIM.vehicles or {}) do
        -- v:getZ(), not v.z: a vehicle in the air stands over nothing on the
        -- ground, which is what lets a flying shuttle be set down beneath
        -- itself without its own hull refusing the landing.
        if not v.removed and self.z == math.floor(v:getZ())
           and math.abs(self.x - math.floor(v.x)) <= 1
           and math.abs(self.y - math.floor(v.y)) <= 2 then
            return v
        end
    end
    return nil
end
function SquareMT:setHaveElectricity(v) self.power = v end

--- Everything standing on this square: the list an explosion walks.
--- IsoTrap.explosion iterates getMovingObjects() and hits every
--- IsoGameCharacter in it, so a square knows who is on it.
function SquareMT:getMovingObjects()
    local here = {}
    for _, p in ipairs(SIM.players or {}) do
        if math.floor(p.x) == self.x and math.floor(p.y) == self.y
           and math.floor(p.z or 0) == self.z then
            table.insert(here, p)
        end
    end
    for _, z in ipairs(SIM.zombies or {}) do
        if math.floor(z.x) == self.x and math.floor(z.y) == self.y
           and math.floor(z.z or 0) == self.z then
            table.insert(here, z)
        end
    end
    return jlist(here)
end

--- A square belongs to the cell. IsoTrap.new wants it, and a square that
--- cannot answer makes every torpedo fail silently -- which is how the first
--- run of the torpedo test failed, and why this is here rather than absent.
function SquareMT:getCell() return getCell() end

--- Whether anything is burning here. The server reads this back after a
--- torpedo to log whether the fire half actually reached the world -- the
--- number that was silently 0 for three commits.
function SquareMT:haveFire()
    return SIM.isBurning(self.x, self.y, self.z)
end

-- Removing an object without recalculating leaves the square holding every
-- conclusion the engine had already drawn from what was on it -- which is why
-- floors that had genuinely been lifted went on darkening the ground beneath
-- them. Counted so a test can insist the pair is always used.
local function markRecalced(sq)
    if sq.recalced == false then
        SIM.staleSquares = math.max(0, (SIM.staleSquares or 0) - 1)
    end
    sq.recalced = true
end
function SquareMT:RecalcProperties() markRecalced(self) end
function SquareMT:RecalcAllWithNeighbours() markRecalced(self) end


function SquareMT:addFloor(sprite)
    local f = SIM.object(sprite)
    f.isFloor = true
    f.square = self
    -- The map has the floor now; the physics engine hears about it later.
    -- RecalcProperties only *flags* the chunk level (IsoChunk.checkPhysicsLater
    -- sets physicsCheck), and Bullet asks for the level when it next steps
    -- (Bullet.updatePhysicsForLevelIfNeeded). A body let go onto a floor in
    -- the same tick it was laid falls through it here, as it can in game --
    -- which is the climb that tipped her over and left her stuck.
    f.physicalAt = (SIM.physicsTick or 0) + (SIM.floorPhysicsLag or 3)
    table.insert(self.objects, 1, f)
    if isServer() then
        py_replicate("floor", { x = self.x, y = self.y, z = self.z, sprite = sprite })
    elseif isClient() then
        -- The sky plane is the one thing a client may lay, and it is counted
        -- apart so the "no client ever edits the world" assertion keeps its
        -- teeth for everything else. A test can then insist that the only
        -- client-side floors are this sprite, and only above the ground.
        SIM.clientWorldEdit = (SIM.clientWorldEdit or 0) + 1
    end
    -- Counted whatever the role, because single player is a client too as far
    -- as the sky plane is concerned, and a test needs to see it either way.
    if sprite == "invisible_01_0" and self.z > 0 then
        SIM.skyEdit = (SIM.skyEdit or 0) + 1
        if isClient() then
            -- The one world edit a client may make. Taken back out of the
            -- general count so that "no client ever edits the world" keeps its
            -- teeth for everything else.
            SIM.clientWorldEdit = SIM.clientWorldEdit - 1
            if SIM.clientWorldEdit == 0 then SIM.clientWorldEdit = nil end
        end
    end
    return f
end

local function describe(o)
    local items = {}
    if o.container then
        for _, it in ipairs(o.container.items) do table.insert(items, it.fullType) end
    end
    return { sprite = o.spriteName, modData = o.modData, items = items,
             hasContainer = o.container ~= nil,
             fluid = o.fluid and { capacity = o.fluid.capacity, amount = o.fluid.amount } or nil }
end

function SquareMT:AddTileObject(o)
    o.square = self
    table.insert(self.objects, o)
    if isClient() then SIM.clientWorldEdit = (SIM.clientWorldEdit or 0) + 1 end
end

function SquareMT:transmitAddObjectToSquare(o)
    o.square = self
    table.insert(self.objects, o)
    if isServer() then
        local d = describe(o)
        d.x, d.y, d.z = self.x, self.y, self.z
        py_replicate("object", d)
    elseif isClient() then
        SIM.clientWorldEdit = (SIM.clientWorldEdit or 0) + 1
    end
end

function SquareMT:transmitRemoveItemFromSquare(o)
    for i, v in ipairs(self.objects) do
        if v == o then table.remove(self.objects, i) break end
    end
    for i, v in ipairs(self.worldObjects) do
        if v == o then table.remove(self.worldObjects, i) break end
    end
    if isServer() then
        py_replicate("remove", { x = self.x, y = self.y, z = self.z, sprite = o.spriteName,
                                 world = o.class == "IsoWorldInventoryObject" })
    elseif isClient() then
        SIM.clientWorldEdit = (SIM.clientWorldEdit or 0) + 1
    end
    return 0
end

function SquareMT:RemoveTileObjectErosionNoRecalc(o)
    -- Taking the sky plane back up is the other half of the one world edit a
    -- client may make (addFloor above), with the same two conditions: this
    -- sprite, and above the ground. Anything else a client removes is a world
    -- edit and counts.
    local skyLift = o and o.spriteName == "invisible_01_0" and (self.z or 0) > 0
    if skyLift then
        SIM.skyLift = (SIM.skyLift or 0) + 1
    elseif isClient() then
        SIM.clientWorldEdit = (SIM.clientWorldEdit or 0) + 1
    end
    for i, v in ipairs(self.worldObjects) do
        if v == o then table.remove(self.worldObjects, i) return 0 end
    end
    for i, v in ipairs(self.objects) do
        if v == o then
            table.remove(self.objects, i)
            -- Left stale on purpose. The call says NoRecalc and means it: the
            -- square keeps whatever the engine had already concluded from the
            -- object being there, which is why floors that really had been
            -- lifted went on darkening the ground under them. A caller that
            -- forgets the recalculation leaves this behind for a test to find.
            self.recalced = false
            SIM.staleSquares = (SIM.staleSquares or 0) + 1
            return 0
        end
    end
    return -1
end

--- The engine has both (String, f, f, f) and (InventoryItem, f, f, f), and
--- the mod uses each: the helm is placed by id, and the refit migration moves
--- the *live* item out of a doomed locker, because recreating one from its id
--- resets a hypospray's doses and a magazine's rounds.
function SquareMT:AddWorldInventoryItem(fullType)
    local item = fullType
    if type(fullType) == "string" then
        item = instanceItem(fullType)
    else
        fullType = item.fullType or (item.getFullType and item:getFullType())
    end
    -- **A dropped item picks its own yaw.** IsoWorldInventoryObject's
    -- constructor zeroes worldXRotation and worldYRotation and then, if
    -- worldZRotation is still unset, writes Rand.Next(0, 360) into it. That is
    -- right for a hammer on the floor and wrong for a machine against a
    -- bulkhead -- the replicator stood at a random angle for two revisions
    -- because nothing here modelled it.
    --
    -- A fixed angle rather than a random one: the simulation has to be as
    -- unkind as the engine, not as unpredictable. 137 is simply not zero.
    if item.worldZRotation and item.worldZRotation < 0 then
        item.worldXRotation, item.worldYRotation = 0, 0
        item.worldZRotation = 137
    end

    local w = SIM.object(fullType, "IsoWorldInventoryObject")
    w.item = item
    w.square = self
    item.getWorldItem = function() return w end
    table.insert(self.worldObjects, w)
    if isServer() then
        py_replicate("worldItem", { x = self.x, y = self.y, z = self.z, type = fullType })
    elseif isClient() then
        SIM.clientWorldEdit = (SIM.clientWorldEdit or 0) + 1
    end
    return item
end

function SquareMT:removeWorldObject(w)
    if isServer() then error("removeWorldObject on a server does not reach clients") end
    if isClient() then SIM.clientWorldEdit = (SIM.clientWorldEdit or 0) + 1 end
    for i, v in ipairs(self.worldObjects) do
        if v == w then table.remove(self.worldObjects, i) return end
    end
end

--- Whether a square is loaded here: near where one of this runtime's players
--- has been standing long enough for the ground to stream in. A long jump
--- leaves nothing loaded around the new spot for STREAM_TICKS -- in game the
--- cabin took 26 ticks to appear after a beam, and a player held badly fell
--- to their death in that time.
local LOAD_RADIUS = 70
SIM.STREAM_TICKS = 30
function SIM.loaded(x, y)
    for _, p in ipairs(SIM.players) do
        local cx, cy = p.streamX or p.x, p.streamY or p.y
        if math.abs(cx - x) <= LOAD_RADIUS and math.abs(cy - y) <= LOAD_RADIUS then
            return true
        end
    end
    return false
end

--- Advances streaming by one tick for every player here.
function SIM.stream()
    for _, p in ipairs(SIM.players) do
        local cx, cy = p.streamX or p.x, p.streamY or p.y
        local far = math.abs(cx - p.x) > LOAD_RADIUS / 2 or math.abs(cy - p.y) > LOAD_RADIUS / 2
        if not p.streamX then
            p.streamX, p.streamY = p.x, p.y
        elseif far then
            p.streamWait = (p.streamWait or SIM.STREAM_TICKS) - 1
            if p.streamWait <= 0 then
                p.streamX, p.streamY, p.streamWait = p.x, p.y, nil
            end
        else
            p.streamX, p.streamY, p.streamWait = p.x, p.y, nil
        end
    end
end

--- The ground: grass everywhere on the map, a wood of trees in the void
--- cell the cabin is built in, nothing above ground until someone builds.
local function ground(x, y, z)
    local sq = squares[key(x, y, z)]
    if sq then return sq end
    if z ~= 0 then return nil end
    sq = newSquare(x, y, 0)
    local f = SIM.object(x >= SIM.voidX and "blends_natural_01_64" or "blends_natural_01_16")
    f.isFloor = true
    f.square = sq
    table.insert(sq.objects, f)
    if x >= SIM.voidX and (x + y) % 5 == 0 then
        local tree = SIM.object("e_americanholly_1_3")
        tree.square = sq
        table.insert(sq.objects, tree)
    end
    return sq
end

--- For replication and test setup: the square whatever is loaded.
function SIM.rawSquare(x, y, z)
    return squares[key(x, y, z)] or (z == 0 and ground(x, y, z)) or newSquare(x, y, z)
end

local cell = {}
function cell:getGridSquare(x, y, z)
    if not SIM.loaded(x, y) then return nil end
    return squares[key(x, y, z)] or ground(x, y, z)
end
function cell:getOrCreateGridSquare(x, y, z)
    if not SIM.loaded(x, y) then error("orphan square") end
    return self:getGridSquare(x, y, z) or newSquare(x, y, z)
end
function cell:getChunkForGridSquare(x, y)
    return SIM.loaded(x, y) and {} or nil
end
function cell:getZombieList() return jlist(SIM.zombies) end
function cell:getVehicles()
    local loaded = {}
    for _, v in ipairs(SIM.vehicles) do
        if not v.removed and SIM.loaded(v.x, v.y) then table.insert(loaded, v) end
    end
    local i = 0
    return { iterator = function()
        return {
            hasNext = function() return i < #loaded end,
            next = function() i = i + 1; return loaded[i] end,
        }
    end }
end
-- Lamps are counted two ways on purpose. `SIM.lamps` is every light ever hung
-- and is what the cabin test reads; `SIM.lampsLive` is how many are still
-- burning, and it is the torpedo's business -- a light riding on a projectile
-- is the one part of that feature that touches the world, so it is the one
-- part that can be left behind. A handle is returned because removeLamppost
-- takes the light itself, not a position.
--
-- Each lamp is an IsoLightSource with the setters the engine gives it
-- (ENERGY.md V2): setR/G/B and setActive change a live light in place. The
-- cell keeps the live ones in a list, `getLamppostPositions`, and
-- `SIM.cullLamps` does what `LightingJNI.checkLights` does to a lamp outside
-- every local player's loaded chunks: drops it, silently. Code that hangs
-- its lamps once and trusts them to stay is what that catches.
SIM.lampsLive = 0
SIM.lampSerial = 0
SIM.lampList = {}
local LampMT = {}
LampMT.__index = LampMT
function LampMT:setR(v) self.r = v end
function LampMT:setG(v) self.g = v end
function LampMT:setB(v) self.b = v end
function LampMT:getR() return self.r end
function LampMT:setActive(v) self.active = v == true end
function LampMT:isActive() return self.active ~= false end
function cell:addLamppost(x, y, z, r, g, b, radius)
    SIM.lamps = SIM.lamps + 1
    SIM.lampsLive = SIM.lampsLive + 1
    SIM.lampSerial = SIM.lampSerial + 1
    local light = setmetatable({ id = SIM.lampSerial, x = x, y = y, z = z,
                                 r = r, g = g, b = b, radius = radius,
                                 active = true }, LampMT)
    table.insert(SIM.lampList, light)
    return light
end
local function dropLamp(light)
    for i, l in ipairs(SIM.lampList) do
        if l == light then table.remove(SIM.lampList, i) return true end
    end
    return false
end
function cell:removeLamppost(light)
    if light == nil then
        error("removeLamppost: nil light (the engine takes the IsoLightSource "
              .. "addLamppost handed back, not a position)", 2)
    end
    SIM.lampsLive = SIM.lampsLive - 1
    dropLamp(light)
end
function cell:getLamppostPositions()
    return {
        contains = function(_, light)
            for _, l in ipairs(SIM.lampList) do
                if l == light then return true end
            end
            return false
        end,
        size = function() return #SIM.lampList end,
    }
end
--- Test helper: the engine dropping every lamp in view of nobody.
function SIM.cullLamps()
    local n = #SIM.lampList
    SIM.lampList = {}
    SIM.lampsLive = SIM.lampsLive - n
    return n
end
--- Test helper: the live lamps at a square.
function SIM.lampsAt(x, y, z)
    local out = {}
    for _, l in ipairs(SIM.lampList) do
        if math.floor(l.x) == x and math.floor(l.y) == y and l.z == z then
            table.insert(out, l)
        end
    end
    return out
end
function getCell() return cell end

---------------------------------------------------------------------------
-- Ground markers (getWorldMarkers)
---------------------------------------------------------------------------
-- Drawn per machine and never synced, like the engine's. The list is kept
-- so a test can ask where a client is drawing and how many are alive.
SIM.markers = {}
local MarkerMT = {}
MarkerMT.__index = MarkerMT
function MarkerMT:remove() self.removed = true end
function MarkerMT:isRemoved() return self.removed == true end
function MarkerMT:setAlpha(a) self.alpha = a end
function MarkerMT:setA(a) self.a = a end
function MarkerMT:getAlpha() return self.alpha or 1 end
function MarkerMT:setPosAndSize(x, y, z, size)
    self.x, self.y, self.z, self.size = x, y, z, size
end
function MarkerMT:setPos(x, y, z) self.x, self.y, self.z = x, y, z end
function MarkerMT:getX() return self.x end
function MarkerMT:getY() return self.y end
function MarkerMT:getZ() return self.z end
function MarkerMT:getSize() return self.size end

local worldMarkers = {}
function worldMarkers:addGridSquareMarker(tex, overlay, sq, r, g, b, doAlpha, size)
    if isServer() then error("a server drew a ground marker") end
    if type(tex) ~= "string" then
        -- The six-argument overload: (square, r, g, b, doAlpha, size).
        sq, r, g, b, doAlpha, size = tex, overlay, sq, r, g, b
        tex, overlay = "circle_center", "circle_only_highlight"
    end
    local m = setmetatable({ texture = tex, overlay = overlay,
                             x = sq.x, y = sq.y, z = sq.z, size = size,
                             r = r, g = g, b = b }, MarkerMT)
    table.insert(SIM.markers, m)
    return m
end
function getWorldMarkers() return worldMarkers end

--- The markers still standing.
function SIM.liveMarkers()
    local out = {}
    for _, m in ipairs(SIM.markers) do
        if not m.removed then table.insert(out, m) end
    end
    return out
end
-- The playable world's bounds, as the engine answers them. `isValidChunk` is
-- what vanilla's own map asks before it will offer to teleport you somewhere
-- (ISWorldMap.lua:941), and it takes **world squares divided by ten**, which
-- is how it is called here and there.
--
-- Modelled as a real box rather than "always true": a probe that reports a
-- contact outside the map sends the crew on a walk to nowhere, which is
-- exactly what happened the first time anybody played it, and a stub that
-- said yes to every square could not have caught it.
SIM.worldBounds = { x1 = 0, y1 = 0, x2 = 15000, y2 = 15000 }

function getWorld()
    return {
        getCell = function() return cell end,
        getMetaGrid = function()
            return {
                isValidChunk = function(_, cx, cy)
                    local b = SIM.worldBounds
                    local x, y = cx * 10, cy * 10
                    return x >= b.x1 and x <= b.x2 and y >= b.y1 and y <= b.y2
                end,
            }
        end,
    }
end
SIM.zombies = {}

---------------------------------------------------------------------------
-- Vehicles
---------------------------------------------------------------------------
SIM.vehicles = {}
SIM.vehicleSerial = 0
IsoDirections = { N = "N", S = "S", E = "E", W = "W" }

---------------------------------------------------------------------------
-- Physics transforms
---------------------------------------------------------------------------
-- zombie.core.physics.Transform and org.joml.Vector3f are both on the engine's
-- Lua exposure allow-list, so mod code can construct them. getOrigin() hands
-- back the live vector rather than a copy, which is what makes the read,
-- mutate, write-back round trip work -- so the stub does the same.
Vector3f = {}
Vector3f.__index = Vector3f
function Vector3f.new(x, y, z)
    return setmetatable({ _x = x or 0, _y = y or 0, _z = z or 0 }, Vector3f)
end
function Vector3f:x() return self._x end
function Vector3f:y() return self._y end
function Vector3f:z() return self._z end
function Vector3f:set(x, y, z) self._x, self._y, self._z = x, y, z return self end

Transform = {}
Transform.__index = Transform
function Transform.new()
    return setmetatable({ origin = Vector3f.new() }, Transform)
end
function Transform:getOrigin() return self.origin end

function SIM.transform() return Transform.new() end

local VehicleMT = {}
VehicleMT.__index = VehicleMT

function SIM.vehicle(script, x, y, z, simId)
    if not simId then
        SIM.vehicleSerial = SIM.vehicleSerial + 1
        simId = SIM.vehicleSerial
    end
    local v = setmetatable({ script = script, x = x, y = y, z = z, simId = simId,
                             modData = {}, seats = {}, hotwired = false,
                             tank = { cap = 20, amount = 0 } }, VehicleMT)
    table.insert(SIM.vehicles, v)
    return v
end

function SIM.findVehicle(simId)
    for _, v in ipairs(SIM.vehicles) do
        if v.simId == simId and not v.removed then return v end
    end
end

function VehicleMT:getScriptName() return self.script end
function VehicleMT:getModData() return self.modData end
function VehicleMT:getX() return self.x end
function VehicleMT:getY() return self.y end
function VehicleMT:getMaxPassengers() return 4 end
function VehicleMT:getCharacter(seat) return self.seats[seat] end

---------------------------------------------------------------------------
-- Height, the way build 42 really does it
---------------------------------------------------------------------------
-- This is the trap that killed the first design for flight, so the simulation
-- reproduces it rather than being kind. BaseVehicle.update() sets a vehicle's
-- z to 0 every single tick, and only puts it back to the physics level if a
-- floor tile exists under the vehicle's centre square at that level or the one
-- below. Raise the physics body with nothing under it and getZ() reads 0 for
-- ever: the ship flies in Bullet and sits on the ground in the game.
--
-- So getZ() here is derived, never stored. A test that forgets to lay the sky
-- plane sees the ship on the deck, exactly as the engine would show it.
local LEVEL_UNITS = 2.4494900703430176

-- `physical` asks the physics engine's question rather than the map's: is
-- there a floor it has actually heard about, at a level it will hold? A level
-- in SIM.physicsRefuse never holds anything, which is how a test makes the
-- engine refuse a height outright.
local function floorUnder(v, level, physical)
    if level <= 0 then return true end
    local function at(l)
        if l <= 0 then return true end
        local sq = squares[key(math.floor(v.x), math.floor(v.y), l)]
        local f = sq ~= nil and sq:getFloor() or nil
        if not f then return false end
        if not physical then return true end
        if SIM.physicsRefuse and SIM.physicsRefuse[l] then return false end
        return (f.physicalAt or 0) <= (SIM.physicsTick or 0)
    end
    if physical then
        -- The body rests on the floor of the band it is in; the one below it
        -- is a level down and holds nothing up.
        return at(level)
    end
    return at(level) or at(level - 1)
end

function VehicleMT:getZ()
    local level = math.floor((self.bulletY or 0) / LEVEL_UNITS + 0.05)
    if level <= 0 then return 0 end
    if floorUnder(self, level) then return level end
    return 0
end

--- Gravity, for vehicles.
---
--- Without this the simulation cannot reproduce the thing that actually hurts:
--- take the floor out from under a flying ship and she does not blink to the
--- ground, she *falls*, over several ticks, and lands wherever she happens to
--- be -- once, in game, inside a building. A test that only reads the derived
--- z sees the height restored on the next tick and reports success.
function SIM.vehicleGravity()
    SIM.physicsTick = (SIM.physicsTick or 0) + 1
    for _, v in ipairs(SIM.vehicles or {}) do
        if v.engineRunning and (v.tank.amount or 0) <= 0 then
            v.engineRunning = false   -- the out-of-fuel stall, on the tick
        end
    end
    for _, v in ipairs(SIM.vehicles or {}) do
        local y = v.bulletY or 0
        if not v.removed and y > 0 then
            local level = math.floor(y / LEVEL_UNITS + 0.05)
            -- Every placement is recorded, so a test can read the whole path
            -- she took rather than where she ended up.
            if SIM.trackPath then
                -- The lowest level above her body with one of our floors
                -- under her centre: a floor above a moving body is a shelf
                -- in the physics engine, and running into one tips her.
                local above = nil
                for l = level + 1, 10 do
                    local sq = squares[key(math.floor(v.x), math.floor(v.y), l)]
                    local f = sq and sq:getFloor()
                    if f and f.spriteName == "invisible_01_0" then above = l break end
                end
                table.insert(SIM.path, { y = y, z = v:getZ(), x = v.x, vy = v.y,
                                         band = level, above = above })
            end
            if not floorUnder(v, level, true) then
                v.bulletY = math.max(0, y - LEVEL_UNITS * 0.34)
            end
            -- The lowest she ever sagged to, recorded here rather than sampled
            -- from the test: a dip lasts a tick or two and is put right by the
            -- next pass, so anything watching from outside sees only the
            -- height afterwards and calls it a success.
            local lvl = v.bulletY / LEVEL_UNITS
            if v.minLevel == nil or lvl < v.minLevel then v.minLevel = lvl end
        end
    end
end

--- The physics body's own height, which is what setWorldTransform writes.
function VehicleMT:setBulletY(v) self.bulletY = v end
function VehicleMT:getBulletY() return self.bulletY or 0 end

function VehicleMT:getWorldTransform(t)
    t = t or SIM.transform()
    t:getOrigin():set(self.x, self.bulletY or 0, self.y)
    t.vehicle = self
    return t
end

function VehicleMT:setWorldTransform(t)
    local o = t:getOrigin()
    self.bulletY = o:y()
    SIM.transformCalls = (SIM.transformCalls or 0) + 1
    -- A client moving the world's ship is not the same as a client building
    -- in the world, but it is still worth counting separately so a test can
    -- assert that only the driver's machine ever did it.
    if isClient() then
        SIM.vehicleTransformEdit = (SIM.vehicleTransformEdit or 0) + 1
    end
end

function VehicleMT:setPhysicsActive(a) self.physicsActive = a end
function VehicleMT:isPhysicsActive() return self.physicsActive ~= false end
--- Which machine simulates this vehicle's physics.
---
--- **False in single player**, and that is the engine's real answer rather
--- than an oversight. `BaseVehicle`'s constructor sets
--- `netPlayerAuthorization = Authorization.Server`, and the only thing that
--- ever sets it to `Local` is `constraintChanged() ->
--- authorizationChanged(getDriver())`, whose whole body sits behind
--- `getstatic GameServer.server; ifeq -> return`. Off a server nothing
--- touches it, so `isLocalPhysicSim()` -- which is
--- `authorization == LocalCollide || authorization == Local` off a server --
--- can never be true there. Vanilla never asks it in single player either:
--- `isBrakePedalPressed()` consults it only inside its `GameClient.client`
--- branch.
---
--- This stub used to answer `SIM_ROLE ~= "server"`, which made single player
--- the one case it was kindest about -- and a guard that refused every
--- take-off in a real single-player game passed every test in here.
function VehicleMT:isLocalPhysicSim()
    if SIM_ROLE == "server" then
        -- A server keeps the authorization until a driver takes it, and the
        -- mod's flight code does not load there at all (TREK_Flight is
        -- client-side), so this is only ever asked by the simulation itself.
        return self.seats == nil or self.seats[0] == nil
    end
    if SIM_ROLE == "sp" then return false end
    -- A client: the server hands the authorization to the driver's machine.
    return self.seats ~= nil and self.seats[0] ~= nil
           and self.seats[0] == SIM.players[1]
end
---------------------------------------------------------------------------
-- Orientation, the way the engine really reports it
---------------------------------------------------------------------------
-- This was three stored numbers -- `getAngleX` handed back whatever
-- `setAngles` had last put in `angleX` -- and it was kinder than the engine in
-- the one way that mattered, which cost the mod a flight nobody could steer.
--
-- A vehicle's orientation is a quaternion. `getAngleX/Y/Z` do not read fields:
-- they decompose that quaternion with JOML's `getEulerAnglesXYZ` and multiply
-- by 180/pi. The X of that decomposition is
--
--     atan2(2(xw - yz), 1 - 2(x^2 + y^2))
--
-- which for a ship that is perfectly level, turned by yaw alone, is
-- `atan2(0, cos yaw)` -- **exactly 180 degrees once the heading is more than a
-- quarter turn from where she started**, and the same for Z. A stored-number
-- stub cannot produce that, so a levelling pass that read "|angleX| is large"
-- as "she is tipping over" looked correct here and, in game, wrenched her back
-- to her spawn heading ten times a second.
--
-- So the orientation is a real quaternion now, `setAngles` builds one with
-- `rotationXYZ` the way `BaseVehicle.setAngles` does, `flipUpright` resets it
-- to the identity the way `BaseVehicle.flipUpright` does -- **heading and
-- all** -- and the three getters decompose it. `SIM.setHeading` and
-- `VehicleMT:heading()` are for tests that care where her nose is pointing.
local DEG = 180 / math.pi

local function qmul(a, b)
    return {
        a[4]*b[1] + a[1]*b[4] + a[2]*b[3] - a[3]*b[2],
        a[4]*b[2] - a[1]*b[3] + a[2]*b[4] + a[3]*b[1],
        a[4]*b[3] + a[1]*b[2] - a[2]*b[1] + a[3]*b[4],
        a[4]*b[4] - a[1]*b[1] - a[2]*b[2] - a[3]*b[3],
    }
end

local function qaxis(x, y, z, deg)
    local s = math.sin(deg / DEG / 2)
    return { x * s, y * s, z * s, math.cos(deg / DEG / 2) }
end

local IDENTITY = { 0, 0, 0, 1 }

local function rot(v)
    return v.rot or IDENTITY
end

--- Quaternionf.rotationXYZ, which is what setAngles builds from its arguments.
local function rotationXYZ(x, y, z)
    return qmul(qmul(qaxis(1, 0, 0, x), qaxis(0, 1, 0, y)), qaxis(0, 0, 1, z))
end

--- Turns a vector by a quaternion: q v q*.
local function qrot(q, v)
    local c = { -q[1], -q[2], -q[3], q[4] }
    local r = qmul(qmul(q, { v[1], v[2], v[3], 0 }), c)
    return r[1], r[2], r[3]
end

function VehicleMT:setAngles(x, y, z)
    self.rot = rotationXYZ(x, y, z)
end

--- Test helper: point her nose somewhere, level, the way driving would.
function VehicleMT:setHeading(deg)
    self.rot = qaxis(0, 1, 0, deg)
end

--- Test helper: where her nose actually points, in degrees. The angle getters
--- cannot answer this -- that is the whole point of them.
function VehicleMT:heading()
    local fx, _, fz = qrot(rot(self), { 0, 0, 1 })
    return math.atan(fx, fz) * DEG
end

--- Test helper: the Y of her own "up". 1 is level, -1 is on her back.
function VehicleMT:uprightness()
    local _, uy, _ = qrot(rot(self), { 0, 1, 0 })
    return uy
end

function VehicleMT:getAngleX()
    local q = rot(self)
    local x, y, z, w = q[1], q[2], q[3], q[4]
    return math.atan(2 * (x*w - y*z), 1 - 2 * (x*x + y*y)) * DEG
end

function VehicleMT:getAngleY()
    local q = rot(self)
    local x, y, z, w = q[1], q[2], q[3], q[4]
    local s = 2 * (x*z + y*w)
    if s > 1 then s = 1 elseif s < -1 then s = -1 end
    return math.asin(s) * DEG
end

function VehicleMT:getAngleZ()
    local q = rot(self)
    local x, y, z, w = q[1], q[2], q[3], q[4]
    return math.atan(2 * (z*w - x*y), 1 - 2 * (y*y + z*z)) * DEG
end

--- The engine's own flipUpright: `setAngleAxis(0, _UNIT_Y)`, which is an angle
--- of **zero** -- the identity. It does not level her, it un-rotates her, and
--- the heading goes with the pitch and the roll. The stub used to keep the
--- heading, which is why nothing here could see the bug.
function VehicleMT:flipUpright() self.rot = IDENTITY end
function VehicleMT:getMaxSpeed() return self.maxSpeed or 70 end
function VehicleMT:setMaxSpeed(v) self.maxSpeed = v end
function VehicleMT:getThrottle() return self.throttle or 0 end
function VehicleMT:getCurrentSteering() return self.steering or 0 end
function VehicleMT:getDriver() return self.seats[0] end
--- -1 for somebody not in the vehicle, as the engine answers
--- (BaseVehicle.getSeat, bci 27). This stub used to answer nil, which let a
--- `getSeat(p) ~= nil` test count everybody near a hovering shuttle as her
--- crew -- in the game, and never here.
function VehicleMT:getSeat(chr)
    for seat, who in pairs(self.seats) do
        if who == chr then return seat end
    end
    return -1
end
function VehicleMT:isDriver(chr) return self.seats[0] == chr end
function VehicleMT:exit(chr)
    for seat, who in pairs(self.seats) do
        if who == chr then self.seats[seat] = nil end
    end
    chr.vehicle = nil
end
--- Vanilla's own `vehicle:enter(seat, character)` -- ISEnterVehicle.lua:50.
--- The distance check lives in the *action*, not in the method, so this puts
--- the character in the seat wherever they happen to be standing.
function VehicleMT:enter(seat, chr)
    if self.seats[seat] ~= nil then return false end
    self.seats[seat] = chr
    chr.vehicle = self
    return true
end
function VehicleMT:cheatHotwire(h) self.hotwired = h end
function VehicleMT:getPartById(id)
    if id == "Battery" then
        -- The charge lives in the part's **item**, not in part mod data
        -- (ENERGY.md V3): `transmitPartModData` does not carry it, and
        -- `transmitPartUsedDelta` does. A fresh vehicle's battery is flat,
        -- as the stub's tank is empty: nothing here fills either for free.
        self.battery = self.battery or { charge = 0 }
        local b = self.battery
        return {
            getId = function() return "Battery" end,
            getInventoryItem = function()
                return {
                    getCurrentUsesFloat = function() return b.charge end,
                    setUsedDelta = function(_, n) b.charge = n end,
                    setCurrentUsesFloat = function(_, n) b.charge = n end,
                }
            end,
        }
    end
    if id ~= "GasTank" then return nil end
    local tank = self.tank
    return {
        getId = function() return "GasTank" end,
        getContainerCapacity = function() return tank.cap end,
        getContainerContentAmount = function() return tank.amount end,
        setContainerContentAmount = function(_, n) tank.amount = n end,
    }
end
function VehicleMT:transmitPartModData() end
function VehicleMT:transmitPartUsedDelta() self.usedDeltaSent = (self.usedDeltaSent or 0) + 1 end

--- Her parts with conditions (ENERGY.md V4), walked the way vanilla walks
--- them: getPartCount / getPartByIndex. A fresh vehicle is whole. The tank
--- and the battery are in the walk too, because the engine's is, and code
--- that mends "every part" has to be seen skipping them.
local DAMAGEABLE = { "Engine", "TruckBed", "TireFrontLeft", "TireFrontRight",
                     "TireRearLeft", "TireRearRight" }
function VehicleMT:partList()
    if self.parts then return self.parts end
    self.parts = {}
    for _, id in ipairs(DAMAGEABLE) do
        local part = { id = id, condition = 100 }
        function part:getId() return self.id end
        function part:getCondition() return self.condition end
        function part:setCondition(n) self.condition = math.max(0, math.min(100, n)) end
        function part:getInventoryItem() return { part = self } end
        function part:doInventoryItemStats() self.statsDone = (self.statsDone or 0) + 1 end
        function part:getMechanicSkillInstaller() return 0 end
        table.insert(self.parts, part)
    end
    local vehicle = self
    for _, id in ipairs({ "GasTank", "Battery" }) do
        local part = vehicle:getPartById(id)
        part.condition = 100
        function part:getCondition() return self.condition end
        function part:setCondition(n) self.condition = n end
        table.insert(self.parts, part)
    end
    return self.parts
end
function VehicleMT:getPartCount() return #self:partList() end
function VehicleMT:getPartByIndex(i) return self:partList()[i + 1] end
function VehicleMT:transmitPartCondition(part)
    self.conditionSent = (self.conditionSent or 0) + 1
end
function VehicleMT:transmitPartItem() end
function VehicleMT:updatePartStats() end
function VehicleMT:updateBulletStats() end
--- The engine's own repair(): everything whole, tank full, battery charged
--- (V4, bci 205-289). What the shields must never use.
function VehicleMT:repair()
    self.repaired = true
    for _, p in ipairs(self:partList()) do p.condition = 100 end
    self.tank.amount = self.tank.cap
    self.battery = self.battery or {}
    self.battery.charge = 1.0
end

--- Test helper: a crash, as the server applies it (V4): a front crash takes
--- the Engine (this hull has no engine door), a rear one the TruckBed.
function SIM.crash(v, front, amount)
    local want = front and "Engine" or "TruckBed"
    for _, p in ipairs(v:partList()) do
        if p.id == want then p.condition = math.max(0, p.condition - (amount or 30)) end
    end
end
function SIM.partCondition(v, id)
    for _, p in ipairs(v:partList()) do
        if (p.id or (p.getId and p:getId())) == id then return p.condition end
    end
end

--- The engine, the way V3 found it (ENERGY.md section 12).
---
--- `tryStartEngine` reads the battery item's charge and refuses at 0.1 or
--- below, *before* the key check; `updateStarting` refuses an empty tank; a
--- running engine with no gas stalls on its next check; and only the server
--- decides any of it. Nothing here is kinder: a start with a flat battery or
--- a dry tank simply does not happen, and a test has to fill both first.
--
-- **The stall waits for the engine's own check.** VehicleEngine.update
-- tests the tank periodically (V3, bci 7-41), so an engine whose tank has
-- just been emptied is still running until the next tick. That is why going
-- dark calls shutOff as well, and why this stub stalls in SIM.vehicleGravity
-- rather than the instant the getter is asked: a stall here would have
-- covered for a missing shutOff.
function VehicleMT:isEngineRunning()
    return self.engineRunning == true
end
function VehicleMT:shutOff() self.engineRunning = false end

--- Test helper: turn the key. Returns "started", "noPower" or "noFuel".
function SIM.startEngine(v)
    local charge = v.battery and v.battery.charge or 0
    if charge <= 0.1 then return "noPower" end
    if (v.tank.amount or 0) <= 0 then return "noFuel" end
    v.engineRunning = true
    return "started"
end

--- A seat container, as the loot window holds when you stand by a vehicle.
--- Once the vehicle is gone, asking it anything throws -- which is exactly
--- what makes vanilla's inventory page flood the log and black the screen.
function VehicleMT:seatContainer()
    if self.seatContainerObj then return self.seatContainerObj end
    local vehicle = self
    -- The part survives its vehicle; that is the whole shape of the bug. Once
    -- the vehicle is gone the part is still there and getVehicle() answers
    -- null, which is how a dead container can be spotted *without* throwing.
    local part = {
        getVehicle = function()
            if vehicle.removed then return nil end
            return vehicle
        end,
    }
    self.seatContainerObj = {
        isVehiclePart = function() return true end,
        getVehiclePart = function() return part end,
        -- Throws exactly as the engine does, and is left here on purpose: a
        -- repeated check built on this call dumps a Java stack trace per call
        -- and floods the log. Nothing in the mod may call it on a timer, and
        -- if something starts to, this is what will fail the test.
        isOccupiedVehicleSeat = function()
            if vehicle.removed then
                SIM.throwingProbes = (SIM.throwingProbes or 0) + 1
                error("Cannot invoke BaseVehicle.getCharacter(int) because " ..
                      "VehiclePart.getVehicle() is null")
            end
            return false
        end,
    }
    return self.seatContainerObj
end
function VehicleMT:permanentlyRemove()
    self.removed = true
    if isServer() then py_replicate("vehicleRemove", { x = 0, y = 0, z = 0, simId = self.simId }) end
    if isClient() then SIM.clientWorldEdit = (SIM.clientWorldEdit or 0) + 1 end
end

--- Spawns a vehicle, as build 42's addVehicleDebug does: on the server the
--- game's vehicle sync then streams it to clients.
function addVehicleDebug(script, dir, skin, sq)
    if isClient() then error("addVehicleDebug on a client") end
    if not sq then return nil end
    local v = SIM.vehicle(script, sq.x + 0.5, sq.y + 0.5, sq.z)
    if isServer() then
        py_replicate("vehicle", { x = sq.x, y = sq.y, z = sq.z, script = script, simId = v.simId })
    end
    return v
end

--- The vehicle physics this machine owns, as "simId=bulletY;..." -- what a
--- VehiclePhysicsPacket carries out of the driver's machine. The server relays
--- it without looking (it runs no vehicle physics), and every other machine's
--- copy takes the height, which is how a crewman on another machine sees her
--- rise. Only a client can own a vehicle's physics; single player has nobody
--- to tell.
function SIM.ownedBodies()
    if SIM_ROLE ~= "client" then return "" end
    local out = {}
    for _, v in ipairs(SIM.vehicles or {}) do
        if not v.removed and v:isLocalPhysicSim() then
            table.insert(out, tostring(v.simId) .. "=" .. tostring(v.bulletY or 0))
        end
    end
    return table.concat(out, ";")
end

function SIM.applyBody(simId, y)
    local v = SIM.findVehicle(simId)
    if v and not v:isLocalPhysicSim() then v.bulletY = y end
end

--- Test helper: a vehicle driven somewhere, optionally pointing a new way.
function SIM.driveVehicle(simId, x, y, heading)
    local v = SIM.findVehicle(simId)
    if not v then return end
    v.x, v.y = x, y
    if heading then v:setHeading(heading) end
end

---------------------------------------------------------------------------
-- Players
---------------------------------------------------------------------------
SIM.players = {}
local PlayerMT = {}
PlayerMT.__index = PlayerMT

function SIM.player(name, x, y, z, admin)
    local p = setmetatable({ name = name, x = x, y = y, z = z, modData = {},
                             dead = false, admin = admin == true,
                             inventory = SIM.container(50) }, PlayerMT)
    -- Whose pockets these are, so an item the server puts in them reaches
    -- that player's client and nobody else's.
    p.inventory.ownerName = name
    table.insert(SIM.players, p)
    return p
end

-- What reading touches on a character (PADD.md), recorded per runtime so a
-- test can say which machine a book's effects landed on.
function PlayerMT:hasTrait(t) return self.traits ~= nil and self.traits[t] == true end
function PlayerMT:getPerkLevel(perk)
    return (self.perks and perk and self.perks[perk.name]) or 0
end
function PlayerMT:isTimedActionInstant() return false end
function PlayerMT:getAlreadyReadPages(t)
    return (self.readPages and self.readPages[t]) or 0
end
function PlayerMT:setAlreadyReadPages(t, n)
    self.readPages = self.readPages or {}
    self.readPages[t] = n
end
function PlayerMT:isLiteratureRead(title)
    return self.readTitles ~= nil and self.readTitles[title] == true
end
function PlayerMT:addReadLiterature(title)
    self.readTitles = self.readTitles or {}
    self.readTitles[title] = true
end
SIM.literatureRead = {}
function PlayerMT:ReadLiterature(book)
    if book.tags and book.tags[ItemTag.CONSUME_ON_READ] then
        error("ReadLiterature on a CONSUME_ON_READ book calls Use() on it")
    end
    table.insert(SIM.literatureRead, { who = self.name, type = book.fullType,
                                       title = book.modData.literatureTitle,
                                       inContainer = book.container ~= nil })
end
function PlayerMT:learnRecipe(r)
    self.recipes = self.recipes or {}
    self.recipes[r] = true
    return true
end
function PlayerMT:getAlreadyReadBook()
    self.booksRead = self.booksRead or {}
    local list = self.booksRead
    return { add = function(_, t) list[t] = true end }
end
function PlayerMT:addReadPrintMedia(id)
    self.media = self.media or {}
    self.media[id] = true
end
function PlayerMT:setReading(v) self.reading = v end
function PlayerMT:reportEvent() end
function PlayerMT:getWornItems() return { getItem = function() return nil end } end
function PlayerMT:isSitOnGround() return false end
function PlayerMT:isSittingOnFurniture() return false end

function PlayerMT:getX() return self.x end
function PlayerMT:getY() return self.y end
--- A character in a seat is wherever the vehicle is.
---
--- The engine moves a passenger with the vehicle every tick, so a pilot at
--- cruise reports the flight level, not the ground they took off from. The
--- stub used to answer the last z anybody had set on them, which made the
--- cockpit indistinguishable from the tarmac -- and the tricorder's whole
--- reason for reading downwards in flight is that the two are three levels
--- apart.
function PlayerMT:getZ()
    if self.vehicle then return self.vehicle:getZ() end
    return self.z
end
function PlayerMT:setX(v) self.x = v end
function PlayerMT:setY(v) self.y = v end
function PlayerMT:setZ(v) self.z = v end
function PlayerMT:setLastX() end
function PlayerMT:setLastY() end
function PlayerMT:setLastZ(v) self.lastZ = v end
function PlayerMT:setbFalling() end
function PlayerMT:setFallTime() end
function PlayerMT:setLastFallSpeed() end
function PlayerMT:clearFallDamage() self.fallDamage = 0 end

--- The engine's own vault switch. Build 42 reads it first in both routes
--- into a climb -- doContextClimbOverWall and doContextHopOverFence -- before
--- either offers the contextual action, so a character carrying it can climb
--- nothing at all.
function PlayerMT:setIgnoreAutoVault(v) self.ignoreAutoVault = v == true end
function PlayerMT:isIgnoreAutoVault() return self.ignoreAutoVault == true end

--- Climbs a character one square, the way build 42's contextual climb does.
---
--- The simulation performs the climb rather than merely recording the flag,
--- because a test that asserted `ignoreAutoVault == true` would pass against
--- a build that set a field nothing reads. Returns whether it happened.
---
--- Only the gate this mod relies on is modelled: the roof and IsoBuilding
--- tests in canClimbOverWall are what every wall on the map is refused by,
--- and the cabin -- raised in a cell with no map behind it -- has neither,
--- which is the whole premise of the bug.
function SIM.climbOverWall(p, dx, dy)
    if p.ignoreAutoVault then return false end
    p.x, p.y = p.x + dx, p.y + dy
    return true
end

--- Gravity, the way the engine moves a character: from its *last* height, not
--- the height Lua last set. A hold that only calls setZ still falls. Landing
--- two or more floors down kills, which is what happened in game.
function SIM.settleUI()
    if SIM.radial and SIM.radial.settle then SIM.radial:settle() end
end

function SIM.gravity()
    if SIM_ROLE == "server" then return end
    for _, p in ipairs(SIM.players) do
        -- Somebody riding in a vehicle is placed by the engine, not by
        -- gravity: BaseVehicle.update() sets every seated character's x, y and
        -- z from the vehicle each tick, with the z taken from the vehicle's
        -- own (floor-clamped) height. So the crew ride up with the ship and
        -- come down with it, and cannot fall out of a seat.
        if not p.dead and p.vehicle and not p.vehicle.removed then
            p.x, p.y = p.vehicle.x, p.vehicle.y
            p.z = p.vehicle:getZ()
            p.lastZ, p.fallFrom = p.z, nil
        elseif not p.dead then
            local z = p.lastZ or p.z
            local sq = squares[math.floor(p.x) .. "," .. math.floor(p.y) .. "," .. math.floor(z)]
                       or (math.floor(z) == 0 and SIM.loaded(p.x, p.y) and cell:getGridSquare(math.floor(p.x), math.floor(p.y), 0))
            local floored = sq and sq:getFloor() ~= nil
            if z > 0 and not floored then
                p.fallFrom = p.fallFrom or z
                z = math.max(0, z - 0.25)
            elseif p.fallFrom then
                if p.fallFrom - z >= 2 then
                    p.dead = true
                    table.insert(SIM.log, "SIM DEATH " .. p.name .. " fell from " .. p.fallFrom)
                end
                p.fallFrom = nil
            end
            p.z, p.lastZ = z, z
        end
    end
end
function PlayerMT:getVehicle() return self.vehicle end
function PlayerMT:isbFalling() return false end
function PlayerMT:getJoypadBind() return -1 end
function PlayerMT:getUsername() return self.name end
function PlayerMT:isDead() return self.dead end
function PlayerMT:getModData() return self.modData end
function PlayerMT:getPlayerNum() return 0 end
function PlayerMT:isLocalPlayer() return SIM_ROLE ~= "server" end
function PlayerMT:getRole()
    local admin = self.admin
    return { hasAdminPower = function() return admin end }
end
---------------------------------------------------------------------------
-- Stats, and the infection moodle
---------------------------------------------------------------------------
-- CharacterStat is a Java enum whose members are registered at startup, and
-- the only thing in this mod that touches it is the EMH clearing the
-- infection moodle -- which it has to, because the block that writes that
-- stat lives *inside* the countdown and the countdown is gated on
-- isInfected(). Cure the player and the writer stops running, so the last
-- value it wrote is the value that stays on screen.
--
-- Modelled as a real store rather than a no-op: a setter that quietly did
-- nothing would make "the moodle is cleared" pass against a build that never
-- cleared it, which is this project's favourite failure.
CharacterStat = {
    ZOMBIE_INFECTION = "ZOMBIE_INFECTION",
    HUNGER = "HUNGER",
    THIRST = "THIRST",
    FITNESS = "FITNESS",
}

function PlayerMT:getStats()
    if self.stats then return self.stats end
    local values = {}
    local s = { values = values }
    function s:get(stat) return values[stat] or 0 end
    function s:set(stat, v)
        if stat == nil then error("getStats():set(nil, ...)", 2) end
        values[stat] = v
        return true
    end
    function s:add(stat, v) values[stat] = (values[stat] or 0) + v return true end
    self.stats = s
    return s
end

function PlayerMT:getInventory() return self.inventory end
-- Settable, because the phaser's cut is refused on the server unless the
-- phaser is really in a hand there (PHASERS.md 7). Nothing else asked, so
-- they used to answer nil for ever.
function PlayerMT:getPrimaryHandItem() return self.primary end
function PlayerMT:getSecondaryHandItem() return self.secondary end
function PlayerMT:setPrimaryHandItem(item) self.primary = item end
function PlayerMT:setHaloNote(text)
    table.insert(SIM.notes, { player = self.name, text = text })
end

---------------------------------------------------------------------------
-- Bodies
---------------------------------------------------------------------------
-- Enough of BodyDamage and BodyPart for the medical set. Every field is a
-- real field the engine has, with the engine's own name, and every setter
-- really writes -- because the whole point of TREK_Medical.treat() is that it
-- reads its result back, and a stub whose setters silently did nothing would
-- make that check pass for the wrong reason.
--
-- **The bite is modelled even though nothing in the mod may cure it.** That
-- is the reason it is here: the hypospray is decided not to cure a bite or
-- the zombie infection, and a body with no bite on it cannot prove that a
-- dose left one alone.
local BodyPartMT = {}
BodyPartMT.__index = BodyPartMT

local BODY_PARTS = { "Hand_L", "Hand_R", "ForeArm_L", "ForeArm_R",
                     "UpperArm_L", "UpperArm_R", "Torso_Upper", "Torso_Lower",
                     "Head", "Neck", "Groin", "UpperLeg_L", "UpperLeg_R",
                     "LowerLeg_L", "LowerLeg_R", "Foot_L", "Foot_R" }

local function newBodyPart(name, index)
    return setmetatable({
        name = name, index = index, health = 100,
        isBleeding = false, bleedingTime = 0,
        isDeepWounded = false, deepWoundTime = 0,
        infectedWound = false, woundInfection = 0,
        burnTime = 0, needBurnWash = false,
        fractureTime = 0, splint = false,
        additionalPain = 0, stiffness = 0,
        isBitten = false, biteTime = 0,
        -- The per-part zombie infection, which is **not** infectedWound. One
        -- is an infected cut and the hypospray cures it; this one is the
        -- virus, and only the EMH may touch it. The names give no help at
        -- all, which is why both are modelled.
        infected = false, fakeInfected = false,
        cut = false, cutTime = 0,
        isScratched = false, scratchTime = 0,
        isStitched = false, stitchTime = 0,
        isBandaged = false, bandageLife = 0,
        glass = false, bullet = false,
    }, BodyPartMT)
end

function BodyPartMT:getHealth() return self.health end
function BodyPartMT:SetHealth(v) self.health = v end
function BodyPartMT:bleeding() return self.isBleeding end
function BodyPartMT:setBleeding(v) self.isBleeding = v end
function BodyPartMT:setBleedingTime(v) self.bleedingTime = v end
function BodyPartMT:deepWounded() return self.isDeepWounded end
function BodyPartMT:setDeepWounded(v) self.isDeepWounded = v end
function BodyPartMT:getDeepWoundTime() return self.deepWoundTime end
function BodyPartMT:setDeepWoundTime(v) self.deepWoundTime = v end
function BodyPartMT:isInfectedWound() return self.infectedWound end
function BodyPartMT:setInfectedWound(v) self.infectedWound = v end
function BodyPartMT:getWoundInfectionLevel() return self.woundInfection end
function BodyPartMT:setWoundInfectionLevel(v) self.woundInfection = v end
function BodyPartMT:getBurnTime() return self.burnTime end
function BodyPartMT:setBurnTime(v) self.burnTime = v end
function BodyPartMT:isNeedBurnWash() return self.needBurnWash end
function BodyPartMT:setNeedBurnWash(v) self.needBurnWash = v end
function BodyPartMT:getFractureTime() return self.fractureTime end
function BodyPartMT:setFractureTime(v) self.fractureTime = v end
function BodyPartMT:isSplint() return self.splint end
function BodyPartMT:setSplint(v) self.splint = v end
function BodyPartMT:getAdditionalPain() return self.additionalPain end
function BodyPartMT:setAdditionalPain(v) self.additionalPain = v end
function BodyPartMT:getStiffness() return self.stiffness end
function BodyPartMT:setStiffness(v) self.stiffness = v end
function BodyPartMT:bitten() return self.isBitten end

--- SetBitten, with the engine's trap in it.
---
--- **The one-argument form infects the limb whatever you pass it**, and this
--- is modelled because it is the worst bug available in the EMH: the obvious
--- way to cure a bite is `part:SetBitten(false)`, vanilla's own admin health
--- cheat calls it that way twice (ClientCommands.lua:490,
--- ISHealthPanel.lua:222), and a player who paid a dilithium crystal and slept
--- twelve hours would wake up infected on a limb that was now bleeding, with
--- the mod reporting a successful cure.
---
--- The bytecode is unambiguous (tools/javadis.py BodyPart SetBitten):
---
---   SetBitten(Z)     2  putfield bittenZ          <- the argument
---                    6  ifeq -> 102               <- only the bleed block
---                  120  putfield isInfectedZ = 1  <- runs regardless
---                  163  invokevirtual generateBleeding()
---
---   SetBitten(ZZ)    2  putfield bittenZ
---                   33  iload_1; ifeq -> 105      <- ALL of it is guarded
---
--- So the two-argument form is the safe one, and a stub that treated them the
--- same would let mutation 11 straight through.
function BodyPartMT:SetBitten(v, second)
    self.isBitten = v
    if second ~= nil and not v then return end
    if v or second == nil then
        self.isBleeding = true
        self.isBandaged = false
        if v then self.infectedWound = true end
        self.infected = true
        self.fakeInfected = false
    end
end

--- Everything the engine's own RestoreToFullHealth writes, and nothing else.
---
--- Thirty-seven fields by direct putfield, no call to SetBitten anywhere, so
--- it side-steps the trap above -- which is why it is the EMH's cure and is
--- forbidden everywhere else in this mod. It clears the bite, and that is the
--- whole reason the hypospray may never use it.
function BodyPartMT:RestoreToFullHealth()
    self.health = 100
    self.additionalPain = 0
    self.isBleeding, self.bleedingTime = false, 0
    self.isBandaged, self.bandageLife = false, 0
    self.isBitten, self.biteTime = false, 0
    self.burnTime, self.needBurnWash = 0, false
    self.isDeepWounded, self.deepWoundTime = false, 0
    self.fractureTime = 0
    self.bullet, self.glass = false, false
    self.infectedWound, self.woundInfection = false, 0
    self.infected, self.fakeInfected = false, false
    self.isScratched, self.scratchTime = false, 0
    self.splint = false
    self.isStitched, self.stitchTime = false, 0
    self.cut, self.cutTime = false, 0
    self.stiffness = 0
end

function BodyPartMT:IsInfected() return self.infected end
function BodyPartMT:SetInfected(v) self.infected = v end
function BodyPartMT:IsFakeInfected() return self.fakeInfected end
function BodyPartMT:SetFakeInfected(v) self.fakeInfected = v end
function BodyPartMT:getBiteTime() return self.biteTime end
function BodyPartMT:setBiteTime(v) self.biteTime = v end
function BodyPartMT:getIndex() return self.index end

--- setCut and setScratched clear the bleeding on their way out, and this is
--- modelled because the engine really does it: both take an early-return
--- branch when they are handed `false` -- write the flag, call
--- setBleeding(false), return -- with every timer and trait in the *true*
--- branch where a wound is being inflicted. A stub that left the bleeding
--- behind would make the dermal regenerator look like it had missed
--- something it had in fact already dealt with.
function BodyPartMT:isCut() return self.cut end
function BodyPartMT:setCut(v)
    self.cut = v
    if not v then self:setBleeding(false) end
end
function BodyPartMT:getCutTime() return self.cutTime end
function BodyPartMT:setCutTime(v) self.cutTime = v end
function BodyPartMT:scratched() return self.isScratched end
function BodyPartMT:setScratched(v)
    self.isScratched = v
    if not v then self:setBleeding(false) end
end
function BodyPartMT:getScratchTime() return self.scratchTime end
function BodyPartMT:setScratchTime(v) self.scratchTime = v end
function BodyPartMT:stitched() return self.isStitched end
function BodyPartMT:setStitched(v) self.isStitched = v end
function BodyPartMT:getStitchTime() return self.stitchTime end
function BodyPartMT:setStitchTime(v) self.stitchTime = v end
function BodyPartMT:bandaged() return self.isBandaged end
function BodyPartMT:getBandageLife() return self.bandageLife end
function BodyPartMT:haveGlass() return self.glass end
function BodyPartMT:setHaveGlass(v) self.glass = v end
function BodyPartMT:haveBullet() return self.bullet end
--- setHaveBullet is **(boolean, int)**, and one argument throws.
---
--- Its signature really is setHaveBullet(ZI)V -- vanilla passes the count as
--- well (ISRemoveBullet.lua:69) -- so a stub that accepted one argument would
--- make the EMH's foreign-body pass look fine here and throw out of Java the
--- first time anybody was shot.
function BodyPartMT:setHaveBullet(v, n)
    if n == nil then
        error("setHaveBullet(boolean) does not exist; it is (boolean, int)", 2)
    end
    self.bullet = v
    self.bulletCount = n
end

local function newBodyDamage()
    local parts = {}
    for i, name in ipairs(BODY_PARTS) do
        table.insert(parts, newBodyPart(name, i - 1))
    end
    local bd = { parts = parts, infected = false, fakeInfected = false,
                 reduceFakeInfection = false,
                 -- Negative is the engine's "the countdown has not started".
                 -- Update() bci 371-377 only initialises it when it is below
                 -- zero, so clearing a cure to 0 leaves a clock running and
                 -- the player dies anyway. Written as -1 by anything that
                 -- means "not infected"; the default matches a fresh body.
                 infectionTime = -1.0,
                 infectionMortalityDuration = -1.0 }
    function bd:getBodyParts() return jlist(self.parts) end
    function bd:isInfected() return self.infected end
    function bd:setInfected(v) self.infected = v end
    function bd:isIsFakeInfected() return self.fakeInfected end
    function bd:setIsFakeInfected(v) self.fakeInfected = v end
    function bd:isReduceFakeInfection() return self.reduceFakeInfection end
    function bd:setReduceFakeInfection(v) self.reduceFakeInfection = v end
    function bd:getInfectionTime() return self.infectionTime end
    function bd:setInfectionTime(v) self.infectionTime = v end
    function bd:getInfectionMortalityDuration()
        return self.infectionMortalityDuration
    end
    function bd:setInfectionMortalityDuration(v)
        self.infectionMortalityDuration = v
    end
    --- Bandaging goes through BodyDamage by index, not through the part.
    --- Both methods exist in the engine and only this one has a vanilla Lua
    --- call site, so this is the one modelled.
    function bd:SetBandaged(index, on, life)
        for _, p in ipairs(self.parts) do
            if p.index == index then
                p.isBandaged = on
                p.bandageLife = life or 0
            end
        end
    end
    return bd
end

function PlayerMT:getBodyDamage()
    self.bodyDamage = self.bodyDamage or newBodyDamage()
    return self.bodyDamage
end

--- One tick of BodyDamage.Update's infection bookkeeping.
---
--- **The body-level flag is a one-way latch re-derived from the parts.**
--- Update() walks the parts and sets isInfected when any of them is infected
--- (bci 280-300), and it is *skipped once true* (bci 271) -- so clearing the
--- body flag alone is undone on the next tick, and clearing the parts alone
--- never clears the body flag. Both have to go in one pass, and this is what
--- makes a test able to tell the difference: run it after a cure and a cure
--- that did only half the job comes back infected.
---
--- The countdown is the same shape: once running it kills, and a value below
--- zero is the only "not started".
function SIM.tickBody(player, minutes)
    local bd = player:getBodyDamage()
    for _ = 1, (minutes or 1) do
        if not bd.infected then
            for _, p in ipairs(bd.parts) do
                if p.infected then bd.infected = true end
            end
        end
        if bd.infected and bd.infectionTime < 0 then
            bd.infectionTime = 0.0
            if bd.infectionMortalityDuration < 0 then
                bd.infectionMortalityDuration = 48.0
            end
        end
        if bd.infected and bd.infectionTime >= 0 then
            bd.infectionTime = bd.infectionTime + 1
            -- The moodle is written from inside the countdown, and the
            -- countdown is gated on isInfected(). Clear the infection and
            -- this stops running, so whatever it last wrote is what stays on
            -- screen -- a perfect cure with the player still told they are
            -- dying. That is why the EMH resets the stat itself.
            local stats = player:getStats()
            stats:set(CharacterStat.ZOMBIE_INFECTION,
                      math.min(1.0, bd.infectionTime
                                    / math.max(1, bd.infectionMortalityDuration)))
        end
    end
    return bd
end

--- Inflicts something on one body part, so a test has a body worth treating.
--- `which` is an index into the part list; the defaults hurt a hand.
---
--- **"infection" sets every field the virus really touches**, both on the
--- part and on the body, rather than the one the next line happens to read
--- back. A test that infects a body by hand and then checks only what it set
--- proves nothing about a cure: it is the field nobody remembered that
--- survives, and the whole cure is "both levels, in one pass".
function SIM.hurt(player, what, which)
    local bd = player:getBodyDamage()
    local parts = bd.parts
    local p = parts[which or 1]
    if what == "infection" then
        p.isBitten, p.biteTime = true, 10
        p.isBleeding = true
        p.infected = true
        p.fakeInfected = false
        p.infectedWound, p.woundInfection = true, 1
        bd.infected = true
        bd.fakeInfected = false
        bd.reduceFakeInfection = false
        bd.infectionTime = 2.0
        bd.infectionMortalityDuration = 48.0
        player:getStats():set(CharacterStat.ZOMBIE_INFECTION, 0.25)
        return p
    end
    if what == "bleeding" then p.isBleeding, p.bleedingTime = true, 10
    elseif what == "deepWound" then p.isDeepWounded, p.deepWoundTime = true, 10
    elseif what == "infectedWound" then p.infectedWound, p.woundInfection = true, 5
    elseif what == "burn" then p.burnTime, p.needBurnWash = 20, true
    elseif what == "fracture" then p.fractureTime, p.splint = 21, true
    elseif what == "pain" then p.additionalPain = 40
    elseif what == "stiffness" then p.stiffness = 30
    elseif what == "health" then p.health = 40
    elseif what == "bite" then p.isBitten, p.biteTime = true, 10
    elseif what == "cut" then p.cut, p.cutTime, p.isBleeding = true, 15, true
    elseif what == "scratch" then p.isScratched, p.scratchTime, p.isBleeding = true, 10, true
    elseif what == "stitches" then p.isStitched, p.stitchTime = true, 12
    elseif what == "bandage" then p.isBandaged, p.bandageLife = true, 8
    elseif what == "glass" then p.glass = true
    elseif what == "bullet" then p.bullet = true
    else error("SIM.hurt: no such injury " .. tostring(what)) end
    return p
end

---------------------------------------------------------------------------
-- Pushing a body part to the client that owns it
---------------------------------------------------------------------------
-- syncBodyPart(part, mask) is a Lua global with ten vanilla call sites under
-- shared/TimedActions/ -- none of them admin or debug -- and its first
-- instruction is `getstatic GameServer.server; ifeq -> return`. So on a
-- client it is **nothing at all**: it looks like a sync, it is a no-op, and
-- a body written on a client stays written only there.
--
-- The part is recorded rather than counted, because "synced the first one
-- only" and "synced all seventeen" are the same number of calls away from
-- each other and only the list can tell them apart.
SIM.bodySyncs = {}

function syncBodyPart(part, mask)
    if part == nil then
        error("syncBodyPart: nil body part", 2)
    end
    if not isServer() then return end        -- exactly what the engine does
    table.insert(SIM.bodySyncs, { part = part, mask = mask })
end

---------------------------------------------------------------------------
-- The world clock
---------------------------------------------------------------------------
-- getGameTime():getWorldAgeHours() is how long the world has been running, in
-- game hours, and it is what the EMH's twelve-hour cure is measured against.
-- Advanceable, because a test that could not move the clock could only prove
-- that the cure had not landed yet.
SIM.worldAgeHours = 0.0

function SIM.advanceHours(n)
    SIM.worldAgeHours = SIM.worldAgeHours + (n or 1)
    return SIM.worldAgeHours
end

local gameTime = {
    getWorldAgeHours = function() return SIM.worldAgeHours end,
    getMinutesPerDay = function() return 60 end,
    getWorldAgeDaysSinceBegin = function() return SIM.worldAgeHours / 24 end,
}
function getGameTime() return gameTime end

---------------------------------------------------------------------------
-- Sounds a character makes
---------------------------------------------------------------------------
-- Recorded rather than played. What a test can honestly ask is whether the
-- instrument said anything at all: a scan with no feedback is a button that
-- appears to do nothing, which is the shape of half the bugs in DEV_GUIDE.md.
SIM.sounds = {}
function PlayerMT:playSound(name)
    table.insert(SIM.sounds, { player = self.name, name = name, local_ = false })
end
function PlayerMT:playSoundLocal(name)
    table.insert(SIM.sounds, { player = self.name, name = name, local_ = true })
    -- A handle, as BaseCharacterSoundEmitter.playSoundImpl returns one: the
    -- phaser's hum is a loop, and a loop with no handle can never be stopped.
    SIM.soundHandle = (SIM.soundHandle or 0) + 1
    SIM.soundsByHandle = SIM.soundsByHandle or {}
    SIM.soundsByHandle[SIM.soundHandle] = name
    return SIM.soundHandle
end
SIM.soundsStopped = {}
function PlayerMT:stopOrTriggerSound(handle)
    table.insert(SIM.soundsStopped, (SIM.soundsByHandle or {})[handle] or handle)
end

--- A sound played at a square: where it came from, and which runtime played
--- it. The ensign's chirp is presentation and belongs to clients; a server
--- that chirped would be a server trying to be heard by nobody.
function SquareMT:playSound(name)
    table.insert(SIM.sounds, { square = { x = self.x, y = self.y, z = self.z },
                               name = name, role = SIM_ROLE })
    return 1
end

--- The engine's zombie-attraction noise (WorldSoundManager). Recorded, with
--- the role that made it: the beacon is the authority's, and a client making
--- zombie noise from mod code would be a client editing the world.
SIM.worldSounds = {}
function addSound(source, x, y, z, radius, volume)
    if isClient() then
        SIM.clientWorldEdit = (SIM.clientWorldEdit or 0) + 1
    end
    table.insert(SIM.worldSounds, { x = x, y = y, z = z, radius = radius,
                                    volume = volume, source = source })
end

function SIM.heardSound(name)
    for _, s in ipairs(SIM.sounds) do
        if s.name == name then return true end
    end
    return false
end

function PlayerMT:getDisplayName() return self.name end
function PlayerMT:getDescriptor()
    local name = self.name
    return { getForename = function() return name end,
             getSurname = function() return "" end }
end

function getPlayer() return SIM.players[1] end
function getSpecificPlayer(i) return SIM.players[i + 1] end
function getOnlinePlayers()
    if SIM_ROLE == "sp" then return jlist({}) end
    return jlist(SIM.players)
end
IsoPlayer = { getPlayers = function() return jlist(SIM.players) end }

---------------------------------------------------------------------------
-- Zombies
---------------------------------------------------------------------------
function SIM.zombie(x, y, z, remote)
    local zed = { x = x, y = y, z = z, remote = remote }
    function zed:getX() return self.x end
    function zed:getY() return self.y end
    function zed:getZ() return self.z end
    function zed:setX(v) self.x = v end
    function zed:setY(v) self.y = v end
    function zed:setLastX() end
    function zed:setLastY() end
    function zed:setTarget() end
    function zed:setStaggerBack() end
    function zed:isRemoteZombie() return self.remote end
    table.insert(SIM.zombies, zed)
    return zed
end

---------------------------------------------------------------------------
-- Server options and sandbox
---------------------------------------------------------------------------
SIM.antiCheatSpeed = 2
function getServerOptions()
    -- As the engine does: AntiCheatSpeed is an enum option, so getInteger
    -- answers nil and getOption answers the value as a string.
    return {
        getInteger = function() return nil end,
        getOption = function(_, name)
            if name == "AntiCheatSpeed" then return tostring(SIM.antiCheatSpeed) end
            return nil
        end,
    }
end
-- StartState is Commissioned here, not the game's default of Cold: every
-- scenario in the suite was written for a ship that starts with power, and
-- the cold start has its own sections that set it to Cold themselves. The
-- game's own reading of a *missing* value (cold) is checked there too.
-- WildDilithium is None for the same reason: the simulated map is grass from
-- edge to edge, and crystals sprouting beside every older scenario would
-- change what its tricorder sees. wild_dilithium() turns it on.
SandboxVars = { TrekShuttle = { Access = 1, TransporterLimit = 1, StartState = 2,
                                WildDilithium = 3 } }

-- The world's map folders, void map included.
function getLotDirectories()
    local dirs = { "TrekShuttle", "Muldraugh, KY" }
    local list = jlist(dirs)
    list.contains = function(_, name)
        for _, d in ipairs(dirs) do if d == name then return true end end
        return false
    end
    return list
end

---------------------------------------------------------------------------
-- Global mod data and the network
---------------------------------------------------------------------------
local globalData = {}
---------------------------------------------------------------------------
-- The world map, its symbols, and the symbol registry
---------------------------------------------------------------------------
-- Modelled because TREK_MapContacts draws the ship's contacts on the map and
-- nothing else in this simulation had a map at all.
--
-- **The registry refuses an id nothing registered**, which is the one thing
-- that has to be as unkind as the engine here: `addTexture` on an unknown
-- symbol draws nothing, silently, and a stub that accepted every string would
-- make a test pass against a map the player would have seen as empty. The
-- ids come from the mod's own shared/Definitions/TrekMapSymbols.lua, which
-- the runtime now loads for real rather than being listed here a second time.

---------------------------------------------------------------------------
-- Randomness
---------------------------------------------------------------------------
-- The engine's own global, used in 424 places in vanilla's Lua. Deterministic
-- here on purpose: a probe whose bearing and whose find/miss roll were real
-- randomness would make the probe tests flap, and a flapping test is one
-- nobody reads. SIM.randQueue lets a test say what the next rolls are, which
-- is how "this probe finds something" and "this one comes back empty" are
-- both exercised rather than waited for.
SIM.randQueue = {}
local randState = 20260923

function ZombRand(a, b)
    local lo, hi
    if b == nil then lo, hi = 0, a else lo, hi = a, b end
    if #SIM.randQueue > 0 then
        local v = table.remove(SIM.randQueue, 1)
        if v < lo then v = lo end
        if hi > lo and v >= hi then v = hi - 1 end
        return v
    end
    randState = (randState * 1103515245 + 12345) % 2147483648
    local span = hi - lo
    if span <= 0 then return lo end
    return lo + (randState % span)
end

-- The player's explored map. `setKnownInSquares` is what reading a paper map
-- does (shared/TimedActions/ISReadABook.lua:318), and it is how a probe
-- survey uncovers the ground around a contact. Per-player and client-side --
-- this is *this* character's map, not ship state -- so each machine reveals
-- its own, and the tests check the rectangles rather than a count.
SIM.revealed = {}
WorldMapVisited = {}
function WorldMapVisited.getInstance()
    return {
        setKnownInSquares = function(_, x1, y1, x2, y2)
            table.insert(SIM.revealed, { x1 = x1, y1 = y1, x2 = x2, y2 = y2 })
        end,
    }
end

MapSymbolDefinitions = {}
local symbolRegistry = {}

function MapSymbolDefinitions.getInstance()
    return {
        addTexture = function(_, id, path, category)
            symbolRegistry[id] = { id = id, path = path, category = category }
        end,
        getSymbolById = function(_, id) return symbolRegistry[id] end,
        getSymbolCount = function()
            local n = 0
            for _ in pairs(symbolRegistry) do n = n + 1 end
            return n
        end,
    }
end

SIM.symbolRegistry = symbolRegistry

--- One map's symbol list, recording what was added and what was taken away.
local function newSymbolsAPI()
    local api = { symbols = {}, added = 0, removed = 0, refused = 0 }

    function api:addTexture(id, worldX, worldY)
        -- The engine draws nothing for an unregistered id. So does this.
        if not symbolRegistry[id] then
            api.refused = api.refused + 1
            return nil
        end
        local symbol = {
            id = id, x = worldX, y = worldY,
            r = 1, g = 1, b = 1, a = 1, ax = 0, ay = 0,
        }
        function symbol:setRGBA(r, g, b, a)
            self.r, self.g, self.b, self.a = r, g, b, a
        end
        function symbol:setAnchor(x, y) self.ax, self.ay = x, y end
        function symbol:getWorldX() return self.x end
        function symbol:getWorldY() return self.y end
        table.insert(api.symbols, symbol)
        api.added = api.added + 1
        return symbol
    end

    function api:removeSymbol(symbol)
        for i, s in ipairs(api.symbols) do
            if rawequal(s, symbol) then
                table.remove(api.symbols, i)
                api.removed = api.removed + 1
                return
            end
        end
        -- Removing something that is not there is a real mistake, not a
        -- no-op: it means the view lost track of what it had put on the map.
        error("removeSymbol: that symbol is not on this map")
    end

    function api:getSymbolCount() return #api.symbols end
    function api:getSymbolByIndex(i) return api.symbols[i + 1] end
    function api:clear() api.symbols = {} end
    return api
end

ISWorldMap = ISWorldMap or {}
ISWorldMap_instance = nil

--- Opens the map. The real one builds a UIWorldMap and hands out the API off
--- it; there is no global symbols object, which is why TREK_MapContacts has
--- to hook the open at all.
function ISWorldMap.ShowWorldMap(playerNum, centerX, centerY, zoom)
    local symbols = newSymbolsAPI()
    ISWorldMap_instance = {
        playerNum = playerNum,
        centerX = centerX, centerY = centerY, zoom = zoom,
        mapAPI = {
            getSymbolsAPIv2 = function() return symbols end,
            uiToWorldX = function(_, x) return x end,
            uiToWorldY = function(_, y) return y end,
        },
    }
    SIM.map = ISWorldMap_instance
    return ISWorldMap_instance
end

function ISWorldMap:onClose()
    ISWorldMap_instance = nil
    SIM.map = nil
end

--- What is on the open map, for the tests.
function SIM.mapSymbols()
    local m = SIM.map
    if not m then return {} end
    return m.mapAPI:getSymbolsAPIv2().symbols
end

ModData = {}
function ModData.getOrCreate(k)
    globalData[k] = globalData[k] or {}
    return globalData[k]
end
function ModData.get(k) return globalData[k] end
function ModData.exists(k) return globalData[k] ~= nil end
function ModData.add(k, t) globalData[k] = t end
function ModData.transmit(k)
    if SIM_ROLE == "sp" then return end
    py_transmit(k, globalData[k])
end
function ModData.request(k)
    if SIM_ROLE ~= "client" then return end
    py_request(k)
end
SIM.globalData = globalData

function sendClientCommand(player, module, command, args)
    if SIM_ROLE == "server" then error("sendClientCommand on a server") end
    py_client_command(player.name, module, command, args)
end

function sendServerCommand(a, b, c, d)
    if SIM_ROLE ~= "server" then return end   -- does nothing in single player
    if type(a) == "table" then
        py_server_command(a.name, b, c, d)
    else
        py_server_command(nil, a, b, c)
    end
end

---------------------------------------------------------------------------
-- Just enough UI for the client files to load
---------------------------------------------------------------------------
local function derivable(name)
    local cls = { Type = name }
    cls.__index = cls
    function cls:derive(n)
        local sub = setmetatable({ Type = n }, { __index = self })
        sub.__index = sub
        return sub
    end
    function cls.new(self, x, y, w, h, title, target, onclick)
        return setmetatable({ x = x, y = y, width = w, height = h, children = {},
                              title = title, target = target, onclick = onclick,
                              enable = true }, self)
    end
    -- The lifecycle every ISUIElement has. Absent, an overlay that is created
    -- and torn down per tick throws on the first frame -- which is how the
    -- torpedo reticle failed here after the aiming rewrite.
    function cls:initialise() end
    --- Builds the panel's children, as the engine does.
    ---
    --- `instantiate()` makes the Java UIElement, and that constructor calls
    --- back into the table's `createChildren`. A stub that did nothing left
    --- every panel opened here with no buttons in it at all -- which meant a
    --- test could "open" the replicator and then only reach it by calling
    --- handlers directly, and a button wired to nothing would have passed.
    function cls:instantiate()
        if self.createChildren and not self.childrenMade then
            self.childrenMade = true
            self:createChildren()
        end
    end
    -- Empty, as ISUIElement's is: a panel calls its parent's first.
    function cls:createChildren() end
    function cls:setAlwaysOnTop() end
    function cls:setCapture() end
    --- A button's title, target and handler are kept, and :click() really
    --- calls it. They used to be dropped on the floor, which meant a test
    --- could only reach a panel's controls by calling their handlers itself
    --- -- and a handler that nothing on screen is wired to is exactly the
    --- shape of "nobody could ever fire a torpedo, and every check passed".
    function cls:click()
        if self.onclick then self.onclick(self.target, self) end
    end
    function cls:addToUIManager()
        self.onScreen = true
        SIM.uiElements = SIM.uiElements or {}
        table.insert(SIM.uiElements, self)
    end
    --- Renders everything on screen once, the way a frame would, and returns
    --- what text was drawn.
    function SIM.renderFrame()
        SIM.uiText = {}
        for _, e in ipairs(SIM.uiElements or {}) do
            if e.onScreen and e.render then e:render() end
        end
        return table.concat(SIM.uiText, "\n")
    end
    function cls:removeFromUIManager() self.onScreen = false end
    function cls:setVisible(v) self.visible = v end
    function cls:addChild(c) c.parent = self; table.insert(self.children, c) end
    function cls:getWidth() return self.width end
    -- The phaser's sparks, recorded; everything else drawn this way is not.
    function cls:drawTextureScaled(tex, x, y, w, h, a, r, g, b)
        if tex and tex.path and tex.path:find("Phaser") then
            SIM.sprites = SIM.sprites or {}
            table.insert(SIM.sprites, { tex = tex.path, x = x, y = y, w = w, h = h,
                                        r = r, g = g, b = b })
        end
    end
    -- Four corners: the phaser's beam is a quad from the emitter to the
    -- target. Recorded whole, so a test can ask where it runs and in what
    -- colour -- a beam drawn at the wrong end, or orange where the core
    -- should be white, is the thing only a render would otherwise show.
    function cls:drawTextureAllPoint(tex, tlx, tly, trx, try, brx, bry, blx, bly,
                                     r, g, b, a)
        SIM.quads = SIM.quads or {}
        table.insert(SIM.quads, { tex = tex and tex.path,
                                  tl = { tlx, tly }, tr = { trx, try },
                                  br = { brx, bry }, bl = { blx, bly },
                                  r = r, g = g, b = b, a = a })
    end
    function cls:drawTexture() end
    function cls:drawRect() end
    function cls:drawRectBorder() end
    function cls:drawText() end
    function cls:drawTextRight() end
    -- Recorded, so a test can read what an overlay says rather than only
    -- whether it drew something.
    -- Black text is not recorded: it is a drop shadow under the real line, and
    -- counting it let a label whose coloured half was never drawn pass.
    function cls:drawTextCentre(text, x, y, r, g, b)
        if (r or 1) + (g or 1) + (b or 1) == 0 then return end
        SIM.uiText = SIM.uiText or {}
        table.insert(SIM.uiText, tostring(text))
    end
    function cls:insertNewLineOfButtons() end
    function cls:setISButtonForB(b) self.ISButtonB = b end
    return cls
end
ISPanelJoypad = derivable("ISPanelJoypad")
ISButton = derivable("ISButton")

-- The two widgets the replicator's panel is built from. Modelled here rather
-- than only in tests/test_helm.py because the panel is the *way in* to the
-- feature: a protocol test that called the server handler directly would pass
-- against a build whose Materialise button was wired to nothing.
ISScrollingListBox = derivable("ISScrollingListBox")
function ISScrollingListBox:clear() self.items = {} end
function ISScrollingListBox:addItem(name, item)
    self.items = self.items or {}
    local row = { text = name, item = item, height = self.itemheight or 20,
                  itemindex = #self.items + 1 }
    table.insert(self.items, row)
    return row
end
function ISScrollingListBox:ensureVisible() end

-- The helm's course prompt. Nothing here opens the helm today, but a panel
-- whose children are now really built would take the whole file down the
-- first time something did.
ISRichTextPanel = derivable("ISRichTextPanel")
function ISRichTextPanel:setText(t) self.text = t end
function ISRichTextPanel:paginate() end

ISTextEntryBox = derivable("ISTextEntryBox")
--- The engine's box takes its initial text first, so the stub does too --
--- getting that wrong here would hide a real argument-order mistake.
function ISTextEntryBox.new(self, text, x, y, w, h)
    local o = setmetatable({ x = x, y = y, width = w, height = h, children = {},
                             text = text or "" }, self)
    return o
end
function ISTextEntryBox:getText() return self.text end
function ISTextEntryBox:setClearButton() end
function ISTextEntryBox:setPlaceholderText(s) self.placeholder = s end
--- Types into the box the way a player does: the text changes and the box
--- tells whoever asked. ISTextEntryBox:onTextChange is replaced on the
--- instance (ISChat.lua:171 does the same), so it arrives with the box as
--- self and not the window.
function ISTextEntryBox:setText(s)
    self.text = s
    if self.onTextChange then self:onTextChange() end
end
-- The torpedo reticle is a bare overlay rather than a panel: it draws and
-- never captures, so the game underneath stays steerable while armed.
ISUIElement = derivable("ISUIElement")

---------------------------------------------------------------------------
-- The yes/no box
---------------------------------------------------------------------------
-- Vanilla's own consent prompt, and the EMH's: treating somebody else asks
-- them first, and the offer has to appear on the **patient's** screen and
-- nowhere else. A test can only see that if the dialog is recorded per
-- runtime, so every one raised here goes in a list with the text it carried.
--
-- The signature is vanilla's, in vanilla's order
-- (ISModalDialog.lua:187), and answering calls back exactly the way
-- ISModalDialog:onClick does: onclick(target, button, param1, param2) with
-- the button carrying `internal` = "YES" or "NO".
SIM.modals = {}

ISModalDialog = derivable("ISModalDialog")

function ISModalDialog.new(self, x, y, w, h, text, yesno, target, onclick,
                           player, param1, param2)
    local o = setmetatable({ x = x, y = y, width = w, height = h,
                             children = {}, text = text, yesno = yesno,
                             target = target, onclick = onclick,
                             player = player, param1 = param1,
                             param2 = param2 }, self)
    table.insert(SIM.modals, o)
    return o
end

--- Presses Yes or No, as the player does.
function ISModalDialog:answer(yes)
    self.answered = yes and "YES" or "NO"
    self.onScreen = false
    if self.onclick then
        self.onclick(self.target, { internal = self.answered,
                                    player = self.player },
                     self.param1, self.param2)
    end
end

function ISModalDialog:destroy() self.onScreen = false end

--- The last one raised here, for a test to answer.
function SIM.lastModal() return SIM.modals[#SIM.modals] end

---------------------------------------------------------------------------
-- Mouse and the screen -> world conversion
---------------------------------------------------------------------------
-- Modelled because the torpedoes are aimed with them, and because the first
-- version of that feature was tested by calling the server handler directly:
-- the blast was proven and the *input* was not, so a build in which no player
-- could ever fire passed every check. A test that skips the way a thing is
-- actually reached is testing something else.
SIM.mouse = { [0] = false, [1] = false, [2] = false }
SIM.mouseX, SIM.mouseY = 400, 300

---------------------------------------------------------------------------
-- The controller
---------------------------------------------------------------------------
-- A joypad exists only when a test asks for one: SIM.joypad = { id = 0 }.
-- Everything else in this project runs mouse-and-keyboard, and a pad that was
-- present by default would silently take aiming away from the mouse in every
-- other scenario -- which is the exact bug the real wasMouseActiveMoreRecently
-- ThanJoypad() check exists to prevent.
SIM.joypad = nil                   -- { id = n } to plug one in
SIM.joypadAim = { x = 0, y = 0 }   -- right stick, -1..1
SIM.joypadR3 = false               -- right stick click
SIM.mouseIsNewer = true            -- which device was used most recently

JoypadState = { players = {} }

--- Plugs a controller in (or, with nil, unplugs it) for player 1.
function SIM.setJoypad(on)
    if on then
        SIM.joypad = { id = 0 }
        JoypadState.players[1] = SIM.joypad
        SIM.mouseIsNewer = false
    else
        SIM.joypad = nil
        JoypadState.players[1] = nil
        SIM.mouseIsNewer = true
    end
    SIM.joypadAim.x, SIM.joypadAim.y = 0, 0
    SIM.joypadR3 = false
end

function wasMouseActiveMoreRecentlyThanJoypad() return SIM.mouseIsNewer end
function getJoypadAimingAxisX(_) return SIM.joypadAim.x end
function getJoypadAimingAxisY(_) return SIM.joypadAim.y end
function getJoypadMovementAxisX(_) return 0 end
function getJoypadMovementAxisY(_) return 0 end
function isJoypadRightStickButtonPressed(_) return SIM.joypadR3 == true end

-- A fixed frame time. The real one varies and the code divides by it, so a
-- stub returning 0 would make the reticle never move and a stub returning
-- something huge would make every test's first tick fling it to the edge.
-- 33.3 is the 30fps baseline vanilla's own cursors are written against.
UIManager = UIManager or {}
function UIManager.getMillisSinceLastRender() return 33.3 end

function isMouseButtonDown(b) return SIM.mouse[b] == true end
function isMouseButtonPressed(b) return SIM.mouse[b] == true end
function getMouseX() return SIM.mouseX end
function getMouseY() return SIM.mouseY end

--- Where the mouse is pointing, in world squares.
---
--- The real conversion is an isometric projection off the camera; here it is
--- simply "the screen centre is the player, and SIM.aim says how far off it
--- the cursor is". That is enough to test range bounds, refusals and the click
--- edge, and it is honest about what it is: this cannot catch a projection
--- error, only the logic built on top of one.
SIM.aim = { dx = 0, dy = 0 }
function screenToIsoX(_, _, _, _)
    local p = SIM.players[1]
    return (p and p.x or 0) + SIM.aim.dx
end
function screenToIsoY(_, _, _, _)
    local p = SIM.players[1]
    return (p and p.y or 0) + SIM.aim.dy
end

--- The other direction: a world position to a point on the screen.
---
--- Used to draw the torpedo in flight. Like its inverse above this is not a
--- real isometric projection -- it is a fixed scale about the screen centre,
--- which is enough to prove that something is drawn, that it is drawn on the
--- path between ship and target, and that it stops being drawn when the shot
--- lands. It cannot catch a projection error; only the game can.
---
--- It is deliberately **not** the exact inverse of screenToIso above, because
--- a stub that round-trips perfectly invites a test to assert on the round
--- trip and prove nothing but the stub.
SIM.isoScale = 32
function isoToScreenX(_, x, y, _)
    return 960 + (x - y) * SIM.isoScale
end
function isoToScreenY(_, x, y, z)
    return 540 + (x + y) * SIM.isoScale / 2 - (z or 0) * SIM.isoScale
end

---------------------------------------------------------------------------
-- IsoTrap: build 42's explosive, and the only thing a torpedo is
---------------------------------------------------------------------------
-- Recorded rather than simulated. What matters to a test is not how much
-- damage a blast does -- the engine decides that -- but **how it was
-- configured**, because those settings are the entire difference between a
-- weapon you can see and one that kills in silence.
--
-- This comment used to say a non-zero fire chance meant the mod set Muldraugh
-- alight, and the test below asserted all three fire settings were zero. That
-- was backwards, and it is worth knowing why the test agreed with it for three
-- commits: in this engine **the visible part of an explosion IS the fire and
-- the smoke**. IsoTrap.triggerExplosion calls drawCircleExplosion once per
-- mode and skips any mode whose range is <= 0, and the Explosion pass gates
-- both IsoGridSquare.Burn() and IsoFireManager.StartFire on a per-square
-- Rand.Next(100) < getFireStartingChance() roll. At zero there is damage and
-- no picture -- which is exactly what was shipped, and exactly what the test
-- was guarding.
--
-- So the settings are still what is read back; only the expectation flipped.
SIM.traps = {}

-- Squares the blast set alight. The engine's own fire is an IsoFire object
-- with spread and particles and none of that is modelled -- what is modelled
-- is the one question a test can honestly ask: **did the fire reach the
-- world at all, or was it configured away again?**
SIM.burning = {}

local function burnKey(x, y, z) return x .. ":" .. y .. ":" .. (z or 0) end

--- Marks every square a blast would have set alight.
---
--- The real roll is per square against fireChance; here anything inside the
--- radius burns when the chance is non-zero. A test that asserted on a random
--- roll would be a flaky test, and the thing worth asserting is not "60% of
--- them" but "the fire happened rather than being suppressed".
local function burn(trap)
    if not trap.square then return end
    local chance = trap.fireChance or 0
    if chance <= 0 then return end
    -- The engine clamps every explosion radius to 15 (Math.min at the top of
    -- drawCircleExplosion), so a stub that honoured a larger one would be
    -- kinder than the engine -- the exact mistake the nil weapon above cost.
    local r = math.min(math.max(trap.range or 0, trap.fireRange or 0), 15)
    local sx, sy, sz = trap.square.x, trap.square.y, trap.square.z
    for dx = -r, r do
        for dy = -r, r do
            if dx * dx + dy * dy <= r * r then
                SIM.burning[burnKey(sx + dx, sy + dy, sz)] = true
            end
        end
    end
end

function SIM.isBurning(x, y, z)
    return SIM.burning[burnKey(x, y, z)] == true
end

IsoTrap = {}
function IsoTrap.new(attacker, weapon, cell, square)
    -- The engine copies the whole explosion off the weapon, starting with
    -- getSensorRange(), so a nil one is a NullPointerException before the
    -- constructor has done anything. This threw in game while the test passed,
    -- because the stub was happy to take nil -- the simulation being kinder
    -- than the engine, which MULTIPLAYER.md warns is how guards pass for the
    -- wrong reason. It is not kinder now.
    if weapon == nil then
        error("IsoTrap.new: weapon is null (the engine reads getSensorRange() "
              .. "off it immediately)", 2)
    end
    local t = {
        attacker = attacker, square = square,
        fired = false,
        power = 0, range = 0,
        fireChance = nil, fireEnergy = nil, fireRange = nil, smokeRange = nil,
        instant = false,
    }
    function t:setExplosionPower(v) self.power = v end
    function t:setExplosionRange(v) self.range = v end
    function t:setFireStartingChance(v) self.fireChance = v end
    function t:setFireStartingEnergy(v) self.fireEnergy = v end
    function t:setFireRange(v) self.fireRange = v end
    function t:setSmokeRange(v) self.smokeRange = v end
    function t:setInstantExplosion(v) self.instant = v end
    function t:triggerExplosion()
        self.fired = true
        burn(self)
    end
    function t:place() end
    table.insert(SIM.traps, t)
    return t
end

--- The last trap built, for a test to inspect.
function SIM.lastTrap()
    return SIM.traps[#SIM.traps]
end

-- Augmented, not replaced. This used to be a fresh table, which silently
-- threw away the ShowWorldMap and onClose defined with the map above -- and
-- the symptom was "attempt to call a nil value (field 'ShowWorldMap')" a
-- thousand lines from the assignment that caused it.
ISWorldMap = ISWorldMap or {}
ISWorldMap.onMouseUp = function() end
ISWorldMap.render = function() end
ISWorldMap.onJoypadDown = function() end
ISWorldObjectContextMenu = {
    setTest = function() return true end,
    addToolTip = function() return { description = nil } end,
}

---------------------------------------------------------------------------
-- Context menus
---------------------------------------------------------------------------
-- Enough of ISContextMenu to record what a menu offered. The options are the
-- only way a player reaches any of the medical set -- build 42 has no script
-- hook for "using" an arbitrary item -- so a test that called the handlers
-- directly would prove the feature and not the way in. That is exactly how a
-- build in which nobody could ever fire a torpedo passed every check.
function SIM.contextMenu()
    local m = { options = {} }
    function m:addOption(text, target, fn, ...)
        local option = { name = text, fn = fn, args = { ... }, target = target }
        table.insert(self.options, option)
        return option
    end
    -- Attach the submenu to the option it hangs off.
    --
    -- This used to be a no-op, which made **every option in every submenu
    -- invisible to the tests**: a submenu could have been empty, or full of
    -- raw translation keys, and labels() would have shown the same thing
    -- either way. The ship's own menu is two levels deep and the sensors are
    -- entirely in the second one.
    function m:addSubMenu(option, sub)
        if option then option.sub = sub end
    end
    function m:getIsVisible() return true end
    --- The option with this label, or nil.
    function m:find(text)
        for _, o in ipairs(self.options) do
            if o.name == text then return o end
        end
        return nil
    end
    --- Clicks one, the way the engine does: the handler is called with the
    --- target first and then the arguments the option was built with.
    function m:click(text)
        local o = self:find(text)
        if not o then return false end
        o.fn(o.target, unpack(o.args))
        return true
    end
    function m:labels()
        local out = {}
        for _, o in ipairs(self.options) do table.insert(out, o.name) end
        return table.concat(out, "|")
    end
    --- Every option on this menu and on every submenu under it, flattened.
    function m:all()
        local out = {}
        local function walk(menu)
            for _, o in ipairs(menu.options) do
                table.insert(out, o)
                if o.sub then walk(o.sub) end
            end
        end
        walk(self)
        return out
    end
    --- The same, as labels, for a membership check.
    function m:deepLabels()
        local out = {}
        for _, o in ipairs(self:all()) do table.insert(out, o.name) end
        return table.concat(out, "|")
    end
    --- Clicks an option anywhere in the tree, including a submenu.
    function m:deepClick(text)
        for _, o in ipairs(self:all()) do
            if o.name == text and o.fn then
                o.fn(o.target, unpack(o.args))
                return true
            end
        end
        return false
    end
    return m
end
ISContextMenu = { getNew = function() return SIM.contextMenu() end }

---------------------------------------------------------------------------
-- Safehouses
---------------------------------------------------------------------------
-- Boxes a test can declare, with a member list. The engine's own
-- isSafeHouse(square, username, respectOwnerConnected) returns the safehouse
-- only when the square is inside one the named player is **not** a member of,
-- which is exactly the question the tricorder has to ask before it opens a
-- lock. Modelled that way round on purpose: getting it backwards would make
-- the mod refuse its owner and open everyone else's door.
SIM.safehouses = {}

function SIM.safehouse(x1, y1, x2, y2, members)
    local h = { x1 = x1, y1 = y1, x2 = x2, y2 = y2, members = members or {} }
    table.insert(SIM.safehouses, h)
    return h
end

SafeHouse = {}
function SafeHouse.isSafeHouse(sq, username, _)
    if not sq then return nil end
    for _, h in ipairs(SIM.safehouses) do
        if sq.x >= h.x1 and sq.x <= h.x2 and sq.y >= h.y1 and sq.y <= h.y2 then
            if username then
                for _, m in ipairs(h.members) do
                    if m == username then return nil end
                end
            end
            return h
        end
    end
    return nil
end

---------------------------------------------------------------------------
-- Vanilla's health panel
---------------------------------------------------------------------------
-- Recorded, not drawn. The one thing worth asserting about it is the field
-- the medical tricorder sets: `doctorLevel` on the instance, never the
-- `ISHealthPanel.cheat` global, which is `false or getDebug()` in the real
-- file and would work for this developer and for nobody on the Workshop.
SIM.healthPanels = {}
ISHealthPanel = { cheat = false }

function ISHealthPanel:new(patient, x, y, w, h)
    local o = { patient = patient, x = x, y = y, width = w, height = h,
                doctorLevel = 0 }
    function o:initialise() end
    function o:setOtherPlayer(p) self.otherPlayer = p end
    function o:wrapInCollapsableWindow(title)
        local win = { nested = self, title = title }
        function win:addToUIManager() self.onScreen = true end
        function win:removeFromUIManager() self.onScreen = false end
        self.window = win
        return win
    end
    table.insert(SIM.healthPanels, o)
    return o
end

function SIM.lastHealthPanel() return SIM.healthPanels[#SIM.healthPanels] end

function getPlayerScreenLeft(_) return 0 end
function getPlayerScreenTop(_) return 0 end
function getPlayerScreenWidth(_) return 1920 end
function getPlayerScreenHeight(_) return 1080 end

-- Who the stick is pointing at. A panel that takes the focus and never gives
-- it back leaves a controller driving something that has gone.
SIM.joypadFocus = {}
function setJoypadFocus(playerNum, target)
    SIM.joypadFocus[playerNum or 0] = target or false
end
function updateJoypadFocus() end

-- Asking somebody else if they may be scanned. In the engine this raises a
-- yes/no on their screen and only a yes reaches ISMedicalCheckAction; here
-- the request is simply recorded, because what a test can honestly check is
-- that the mod **asked** rather than helping itself.
SIM.medicalRequests = {}
function requestMedicalCheck(target, requester)
    table.insert(SIM.medicalRequests,
                 { target = target.name, requester = requester.name })
end
function acceptMedicalCheck() end
-- One loot window per player, as the game has.
SIM.loot = {}
function getPlayerLoot(i)
    SIM.loot[i] = SIM.loot[i] or { inventory = nil, refreshed = 0 }
    local page = SIM.loot[i]
    page.setNewContainer = function(self, c) self.inventory = c end
    page.refreshBackpacks = function(self) self.refreshed = self.refreshed + 1 end
    return page
end
SIM.floorContainer = { isVehiclePart = function() return false end }
-- dirtyUI is vanilla's rebuild of the inventory and loot panels. Counted, so
-- a test can say whether a move out of a seat rebuilt them while the shuttle
-- was still there -- the missing step behind one NullPointerException in
-- every session that went from a seat into the cabin.
--
-- And it rebuilds, the way vanilla's does: at once, from where the player is
-- standing *now*. Standing beside a vehicle puts its seats in the loot panel.
-- It used to only count, which let a rebuild made beside the shuttle -- one
-- that puts her seats straight back -- pass as the fix.
SIM.inventoryRefreshes = 0
ISInventoryPage = { GetFloorContainer = function() return SIM.floorContainer end,
                    dirtyUI = function()
                        SIM.inventoryRefreshes = SIM.inventoryRefreshes + 1
                        local p = SIM.players[1]
                        local page = getPlayerLoot(0)
                        page.inventory = SIM.floorContainer
                        if not p then return end
                        for _, v in ipairs(SIM.vehicles or {}) do
                            if not v.removed and math.abs(p.x - v.x) <= 3
                               and math.abs(p.y - v.y) <= 4
                               and math.floor(p.z or 0) == v:getZ() then
                                page.inventory = v:seatContainer()
                            end
                        end
                    end }

--- True when the loot panel is holding a seat of a vehicle the player is no
--- longer beside -- what vanilla's panel throws on once that vehicle unloads.
function SIM.lootStale()
    local page = SIM.loot[0]
    if not page or not page.inventory then return false end
    local p = SIM.players[1]
    for _, v in ipairs(SIM.vehicles or {}) do
        if page.inventory == v.seatContainerObj then
            return v.removed or math.abs(p.x - v.x) > 3 or math.abs(p.y - v.y) > 4
        end
    end
    return false
end

--- Vanilla fires its own events from Lua with triggerEvent; ISExitVehicle
--- fires OnExitVehicle this way. Recorded, and passed on to any handler.
SIM.triggered = {}
function triggerEvent(name, ...)
    table.insert(SIM.triggered, name)
    SIM.fire(name, ...)
end

-- The radial menu, modelled as the toggle it really is.
--
-- Vanilla's showRadialMenu clears the menu and, if it was already up, takes it
-- down and returns -- so isReallyVisible() is true only on the press that
-- closes it. A mod hook that adds its slices behind "if the menu is visible"
-- therefore runs only while the menu is being dismissed and never when it is
-- being built, which is a feature that silently does not exist. That happened
-- (2026-09-17): neither "go aboard" nor "take her up" was ever added, in any
-- build, and from the outside flight simply looked broken.
SIM.radial = { slices = {}, visible = false }

-- isReallyVisible() is false for a frame after the menu is opened, and that
-- single fact is the whole trap. addToUIManager() calls UIManager.AddUI, which
-- appends to a *pending* list (UIManager.toAdd); isReallyVisible() asks whether
-- the element is in the live list (UIManager.getUI().contains). So it answers
-- false on the press that opens the menu, and vanilla returns early on the
-- press that closes it -- there is no moment at which a hook guarded on
-- "is it visible" can add anything at all. Modelled here so that guard fails
-- the test instead of the player.
function getPlayerRadialMenu()
    local m = SIM.radial
    if m.addSlice then return m end
    function m:isReallyVisible() return self.visible end
    function m:clear() self.slices = {} end
    function m:undisplay() self.visible, self.pending = false, false end
    --- Promotes a just-opened menu to really visible, a tick later.
    function m:settle()
        if self.pending then self.visible, self.pending = true, false end
    end
    function m:addSlice(text, texture, fn, ...)
        table.insert(self.slices, { text = text, texture = texture, fn = fn })
    end
    function m:titles()
        local out = {}
        for _, s in ipairs(self.slices) do table.insert(out, s.text) end
        return table.concat(out, ",")
    end
    return m
end

ISVehicleMenu = {
    showRadialMenu = function(playerObj)
        local m = getPlayerRadialMenu()
        m:clear()
        if m:isReallyVisible() then m:undisplay() return end
        m:addSlice("IGUI_SwitchSeat")
        m:addSlice("IGUI_ExitVehicle")
        m.pending = true          -- addToUIManager: live only from next frame
    end,
    showRadialMenuOutside = function(playerObj)
        local m = getPlayerRadialMenu()
        if m:isReallyVisible() then m:undisplay() return end
        m:clear()
        m.pending = true
    end,
    FillMenuOutsideVehicle = function() end, onEnter = function() end,
    processEnter = function() end, processShiftEnter = function() end,
    onExit = function() end,
    getVehicleToInteractWith = function() return nil end,
}
ISCarMechanicsOverlay = { CarList = {} }
ImageScale = {}
package.preload["Vehicles/ISUI/ISVehicleMenu"] = function() return true end
package.preload["Vehicles/ISUI/ISCarMechanicsOverlay"] = function() return true end
package.preload["Vehicles/ISUI/ISVehicleSeatUI"] = function() return true end
UIFont = { Small = 1, Medium = 2 }

---------------------------------------------------------------------------
-- Timed actions (PADD.md)
---------------------------------------------------------------------------
-- Modelled on what build 42 actually does, read out of its bytecode:
--
--   * single player runs the whole action in one process: isValid, start,
--     update, perform, **and complete** (LuaTimedActionNew.complete skips
--     only on a client, bci 34);
--   * a client runs isValid and start, then hands the action to the server
--     (LuaTimedActionNew.start -> ActionManager.createNetTimedAction). The
--     server **rebuilds it by its global class name**, calling `new` with the
--     arguments read off the client's action **by the parameter names of
--     `new`** (NetTimedAction.set, Prototype.locvars), runs it, and
--     completes it; the client then performs.
--
-- The parameter-name rule is the one this has to be unkind about: an action
-- that stores `self.item` under a parameter called `book` arrives on the
-- server with a nil book, and never completes -- in the engine and here.
ISBaseObject = ISBaseObject or {}
ISBaseObject.__index = ISBaseObject
function ISBaseObject:derive(type)
    local o = {}
    setmetatable(o, self)
    self.__index = self
    o.Type = type
    return o
end

ISBaseTimedAction = ISBaseObject:derive("ISBaseTimedAction")
function ISBaseTimedAction:new(character)
    local o = {}
    setmetatable(o, self)
    self.__index = self
    o.character = character
    o.stopOnWalk = true
    o.stopOnRun = true
    o.maxTime = -1
    o.jobDelta = 0
    return o
end
function ISBaseTimedAction:isValid() return true end
function ISBaseTimedAction:start() end
function ISBaseTimedAction:update() end
function ISBaseTimedAction:stop() self.stopped = true end
function ISBaseTimedAction:perform() self.performed = true end
function ISBaseTimedAction:getJobDelta() return self.jobDelta or 0 end
function ISBaseTimedAction:setJobDelta(d) self.jobDelta = d end
function ISBaseTimedAction:setActionAnim(a) self.anim = a end
function ISBaseTimedAction:setAnimVariable(k, v)
    self.animVars = self.animVars or {}
    self.animVars[k] = v
end
function ISBaseTimedAction:setOverrideHandModels(primary, secondary)
    self.handModels = { primary, secondary }
end
package.preload["TimedActions/ISBaseTimedAction"] = function() return ISBaseTimedAction end

SIM.actionQueue = {}
SIM.actionsDone = {}
ISTimedActionQueue = {}
function ISTimedActionQueue.add(action)
    table.insert(SIM.actionQueue, action)
    return action
end

-- `new`'s parameter names, after `self`, the way NetTimedAction reads them.
local function paramNames(class)
    local names = {}
    local fn = rawget(class, "new")
    if type(fn) ~= "function" then return names end
    local i = 2
    while true do
        local name = debug.getlocal(fn, i)
        if not name then break end
        table.insert(names, name)
        i = i + 1
    end
    return names
end
SIM.paramNames = paramNames

local function encode(v)
    if type(v) == "table" and v.inventory and v.name then return { __player = v.name } end
    if instanceof(v, "InventoryItem") then return { __item = v.id } end
    return v
end

--- Every item this runtime can see, by id: pockets, and containers and the
--- ground on every square. What the engine resolves a network item by.
function SIM.findItem(id)
    for _, p in ipairs(SIM.players) do
        for _, it in ipairs(p.inventory.items) do
            if it.id == id then return it end
        end
    end
    for _, sq in pairs(SIM.squares) do
        for _, o in ipairs(sq.objects) do
            if o.container then
                for _, it in ipairs(o.container.items) do
                    if it.id == id then return it end
                end
            end
        end
    end
    return nil
end

local function decode(v)
    if type(v) == "table" and v.__player then
        for _, p in ipairs(SIM.players) do
            if p.name == v.__player then return p end
        end
        return nil
    end
    if type(v) == "table" and v.__item then return SIM.findItem(v.__item) end
    return v
end

--- Runs what is queued, the way the engine's three setups do.
function SIM.runActions()
    local queue = SIM.actionQueue
    SIM.actionQueue = {}
    for _, action in ipairs(queue) do
        if action:isValid() then
            action:start()
            if SIM_ROLE == "client" then
                -- The client runs its own copy's update() as the bar fills,
                -- while the server runs the one that counts. It did not use
                -- to here, which let an update() with no `isClient()` guard
                -- apply a tape's effects on the client and pass.
                SIM.stepAction(action)
                local names = paramNames(getmetatable(action))
                local args = {}
                for i, name in ipairs(names) do args[i] = encode(action[name]) end
                SIM.pendingActions = SIM.pendingActions or {}
                SIM.nextToken = (SIM.nextToken or 0) + 1
                SIM.pendingActions[SIM.nextToken] = action
                py_client_action(action.character.name, action.Type, args,
                                 SIM.nextToken)
            else
                SIM.stepAction(action)
                action:perform()
                action:complete()
                table.insert(SIM.actionsDone, action.Type)
            end
        else
            table.insert(SIM.actionsDone, action.Type .. ":invalid")
        end
    end
end

--- Runs an action through its duration, a tick at a time, the way the
--- engine does: update() with the job delta rising to 1.
---
--- It was one update() at delta 1.0, which collapses the whole action into
--- a single tick -- kind, because the one piece of per-tick state an action
--- can depend on is the radio's thirty-tick debounce per code, and a read
--- that applied every line of a tape in its last tick would pass here and
--- give a fraction of the tape in the game. Only the debounce is ticked
--- between steps, not the world, so a long book stays cheap to simulate.
function SIM.stepAction(action)
    local n = math.max(1, math.floor(tonumber(action.maxTime) or 1))
    for t = 1, n do
        action:setJobDelta(t / n)
        action:update()
        SIM.radioTick()
    end
end

--- The server's half: rebuilt by class name and parameter, run, completed.
function SIM.serverAction(typeName, args, count)
    local class = _G[typeName]
    if type(class) ~= "table" then
        SIM.log[#SIM.log + 1] = "SIM WARN no timed action class " .. tostring(typeName)
        return false
    end
    local decoded = {}
    for i = 1, count do decoded[i] = decode(args[i]) end
    local action = class:new(unpack(decoded, 1, count))
    if not action:isValid() then
        table.insert(SIM.actionsDone, typeName .. ":invalid")
        return false
    end
    action:start()
    -- NetTimedAction.start reads `serverStart` off the action and calls it
    -- (bci 8-38): the server's own hook, which the phaser uses to tell every
    -- client its beam is on. It was not modelled until the phaser needed it.
    if action.serverStart then action:serverStart() end
    SIM.stepAction(action)
    action:complete()
    table.insert(SIM.actionsDone, typeName)
    return true
end

function SIM.clientActionDone(token, ok)
    local action = SIM.pendingActions and SIM.pendingActions[token]
    if not action then return end
    SIM.pendingActions[token] = nil
    if ok then action:perform() else action:stop() end
end

ISInventoryPaneContextMenu = ISInventoryPaneContextMenu or {}
function ISInventoryPaneContextMenu.transferIfNeeded() end

---------------------------------------------------------------------------
-- Books (PADD.md)
---------------------------------------------------------------------------
-- A small literature table: a skill book, a titled novel, a recipe
-- magazine, a notebook that must not load and a flyer that is used up when
-- read. Each is what ISReadABook reads off a real one.
SIM.literature = {
    ["Base.BookCarpentry1"] = { name = "Carpentry for Beginners", pages = 220,
                                skill = "Carpentry", lvl = 1, maxLvl = 2 },
    ["Base.BookCarpentry2"] = { name = "Carpentry for Intermediates", pages = 260,
                                skill = "Carpentry", lvl = 3, maxLvl = 4 },
    ["Base.Book"]           = { name = "Book", pages = 0, stress = -40 },
    ["Base.MagazineCooking1"] = { name = "Good Cooking Magazine", pages = 0,
                                  recipes = { "MakeCake" } },
    ["Base.Notebook"]       = { name = "Notebook", pages = 0, writable = true },
    ["Base.Flier"]          = { name = "Flier", pages = 0, consume = true },
}

ItemTag = ItemTag or {}
ItemTag.CONSUME_ON_READ = "CONSUME_ON_READ"
ItemTag.FAST_READ = "FAST_READ"
CharacterTrait = CharacterTrait or {}
CharacterTrait.ILLITERATE = "ILLITERATE"
CharacterTrait.FAST_READER = "FAST_READER"
CharacterTrait.SLOW_READER = "SLOW_READER"
ItemBodyLocation = ItemBodyLocation or { EYES = "EYES" }
CharacterActionAnims = CharacterActionAnims or { Read = "Read" }

Perks = Perks or {}
Perks.Carpentry = Perks.Carpentry or { name = "Carpentry",
                                       getName = function(self) return self.name end }
SkillBook = SkillBook or {}
SkillBook.Carpentry = { perk = Perks.Carpentry, maxMultiplier1 = 3,
                        maxMultiplier2 = 5, maxMultiplier3 = 8,
                        maxMultiplier4 = 12, maxMultiplier5 = 16 }

local sandbox = { MinutesPerPage = 2.0 }
function getSandboxOptions()
    return { getOptionByName = function(_, name)
        return { getValue = function() return sandbox[name] end }
    end }
end

-- What reading gives, recorded where it lands: which runtime, which player.
SIM.xp = {}
SIM.syncedFields = {}
function addXpMultiplier(player, perk, mult, lvl, maxLvl)
    table.insert(SIM.xp, { who = player.name, perk = perk, mult = mult,
                           lvl = lvl, maxLvl = maxLvl })
end
function sendSyncPlayerFields(player, mask)
    table.insert(SIM.syncedFields, { who = player.name, mask = mask })
end

--- The item's mod data, pushed to the player carrying it. Only from the
--- server, and only to that player: another client's copy of somebody
--- else's pockets does not exist to update.
function syncItemModData(player, item)
    if not isServer() then return end
    py_replicate("itemModData", { x = 0, y = 0, z = 0, who = player.name,
                                  id = item.id, modData = item.modData })
end

---------------------------------------------------------------------------
-- What a player has heard, and what hearing it does (LORE.md 2, PADD.md 12.3)
---------------------------------------------------------------------------
-- IsoGameCharacter keeps a plain HashSet of line guids -- a line's guid is its
-- translation key (MediaLineData.getTextGuid) -- and saves it with the player.
-- Nothing syncs it: in multiplayer the server's copy of a player learns a
-- world television's lines, because the server walks the tape.
function PlayerMT:isKnownMediaLine(guid)
    return self.knownLines ~= nil and self.knownLines[guid] == true
end
function PlayerMT:addKnownMediaLine(guid)
    if guid == nil or guid == "" then return end
    self.knownLines = self.knownLines or {}
    self.knownLines[guid] = true
end

--- RecordedMedia.hasListenedToAll: every line known, and at least one line.
function RecordedMediaSim:hasListenedToAll(player, data)
    if not player or not data or #data.lines == 0 then return false end
    for _, ln in ipairs(data.lines) do
        if not player:isKnownMediaLine(ln.text) then return false end
    end
    return true
end

-- Vanilla's interpreter (shared/RadioCom/ISRadioInteractions.lua), as unkind
-- as the real one on the two points that decide how a reader must call it:
--
--   * a line already known does nothing at all, and is learned before any
--     code is applied;
--   * **each code is debounced for thirty ticks per player**. Applying a
--     whole tape in one tick fires the first BOR and swallows every other --
--     so a stub without the debounce would pass a read that, in the game,
--     quietly gave a fraction of what the tape does.
SIM.mediaEffects = {}
local radioCooldowns = {}
ISRadioInteractions = {}
local radioInstance = nil
function ISRadioInteractions:getInstance()
    if radioInstance then return radioInstance end
    radioInstance = {}
    function radioInstance.checkPlayer(player, guid, codes, x, y, z, line)
        if player.asleep then return end
        if guid ~= nil and guid ~= "" then
            if player:isKnownMediaLine(guid) then return end
            player:addKnownMediaLine(guid)
        end
        if codes == nil or #codes == 0 then return end
        radioCooldowns[player.name] = radioCooldowns[player.name] or {}
        local cd = radioCooldowns[player.name]
        for token in codes:gmatch("[^,]+") do
            if #token > 4 then
                local code = token:sub(1, 3)
                if not cd[code] or cd[code] <= 0 then
                    table.insert(SIM.mediaEffects, { who = player.name, code = code,
                                                     token = token, line = guid })
                    cd[code] = 30
                end
            end
        end
    end
    return radioInstance
end
function SIM.radioTick()
    for _, cd in pairs(radioCooldowns) do
        for code, v in pairs(cd) do if v > 0 then cd[code] = v - 1 end end
    end
end
Events.OnTick.Add(SIM.radioTick)

---------------------------------------------------------------------------
-- The galley (ENERGY.md section 9): stoves, a generator, sprite properties
---------------------------------------------------------------------------
-- A sprite's properties persist per name, as the engine's do: the power bus's
-- sound prefix is set on the sky tile's sprite once and read back later.
SIM.spriteProps = {}
local baseGetSprite = getSprite
function getSprite(name)
    local s = baseGetSprite(name)
    SIM.spriteProps[name] = SIM.spriteProps[name] or {}
    local store = SIM.spriteProps[name]
    s.getProperties = function()
        return {
            set = function(_, k, v) store[k] = v end,
            get = function(_, k) return store[k] end,
            Val = function(_, k) return store[k] end,
        }
    end
    return s
end

--- The engine's IsoStove, from vanilla's own runtime route
--- (ISMoveableSpriteProps.lua:2162). Its containers come from the sprite, as
--- a map-loaded one's do, and only once somebody asks for them.
IsoStove = {}
function IsoStove.new(_cell, _sq, sprite)
    local name = type(sprite) == "table" and sprite.name or sprite
    return SIM.object(name, "IsoStove")
end
SIM.SUPER.IsoStove = "IsoObject"
SIM.SUPER.IsoGenerator = "IsoObject"

--- The engine's IsoGenerator, the way V5 found it: the constructor takes its
--- fuel and condition from the item, **adds itself to the square and sends
--- itself to clients** (bci 68-78), and setFuel clamps to 0..10. Burning is
--- the engine's hourly update, which SIM.generatorHours stands in for: a
--- running generator burns its base draw plus a fridge, and one that runs dry
--- switches itself off.
SIM.generators = {}
IsoGenerator = {}
function IsoGenerator.new(item, _cell, sq)
    local g = SIM.object("invisible_01_0", "IsoGenerator")
    g.fuel = tonumber(item and item.modData and item.modData.fuel) or 0
    g.condition = item and item.condition or 100
    g.activated, g.connected = false, false
    function g:getFuel() return self.fuel end
    function g:getMaxFuel() return 10.0 end
    function g:setFuel(f) self.fuel = math.max(0, math.min(10, f)) end
    function g:getCondition() return self.condition end
    function g:setCondition(c) self.condition = math.max(0, math.min(100, c)) end
    function g:isActivated() return self.activated end
    function g:setActivated(b) self.activated = b == true end
    function g:setConnected(b) self.connected = b == true end
    function g:isConnected() return self.connected end
    g.square = sq
    table.insert(sq.objects, g)
    if isServer() then
        local d = describe(g)
        d.x, d.y, d.z = sq.x, sq.y, sq.z
        py_replicate("object", d)
    end
    table.insert(SIM.generators, g)
    return g
end

--- Test helper: n game hours of the engine's generator update.
function SIM.generatorHours(n, draw)
    for _, g in ipairs(SIM.generators) do
        if g.activated then
            g.fuel = math.max(0, g.fuel - (draw or 0.15) * n)
            if g.fuel <= 0 then g.activated = false end
        end
    end
end

ISWorldObjectContextMenu.fetchVars = ISWorldObjectContextMenu.fetchVars or {}


---------------------------------------------------------------------------
-- Phasers (PHASERS.md 7)
---------------------------------------------------------------------------
-- Trees, door leaves, barricades and the handful of character calls the cut
-- makes. Modelled on the bytecode where it matters:
--
--   * IsoTree.toppleTree **returns at once on a client** (bci 0-6) and on the
--     authority removes the tree with transmitRemoveItemFromSquare and drops
--     the logs. So a client that tried to fell a tree itself does nothing
--     here, as it would there;
--   * buildUtil lives in server/ -- present on every machine, used by the
--     authority -- and answers a double door's other leaves.
SIM.felled = {}

function SIM.tree(x, y, z)
    local sq = SIM.rawSquare(x, y, z)
    local o = SIM.object("e_americanholly_1_3", "IsoTree")
    o.square = sq
    table.insert(sq.objects, o)
    return o
end

function ObjectMT:toppleTree(character)
    if isClient() then return end
    local sq = self.square
    if not sq then return end
    sq:transmitRemoveItemFromSquare(self)
    table.insert(SIM.felled, { x = sq.x, y = sq.y, z = sq.z,
                               by = character and character.name })
end

function ObjectMT:getObjectIndex()
    if not self.square then return -1 end
    for i, v in ipairs(self.square.objects) do
        if v == self then return i - 1 end
    end
    return -1
end
function ObjectMT:isDoor() return self.door == true end
function ObjectMT:getBarricadeOnSameSquare() return self.barricadeSame end
function ObjectMT:getBarricadeOnOppositeSquare() return self.barricadeOpposite end

--- Something standing on a square, with a class instanceof reports.
function SIM.put(x, y, z, sprite, class)
    local sq = SIM.rawSquare(x, y, z)
    local o = SIM.object(sprite, class)
    o.square = sq
    table.insert(sq.objects, o)
    return o
end

buildUtil = buildUtil or {}
function buildUtil.getDoubleDoorObjects(o) return o.leaves or {} end
function buildUtil.getGarageDoorObjects(o) return o.garage or {} end

function PlayerMT:getOnlineID() return self.onlineID or -1 end
function PlayerMT:getForwardDirectionX() return self.fwdX or 1 end
function PlayerMT:getForwardDirectionY() return self.fwdY or 0 end
function PlayerMT:faceThisObject(o) self.facing = o end
function PlayerMT:shouldBeTurning() return false end

function getPlayerByOnlineID(id)
    for _, p in ipairs(SIM.players) do
        if p.onlineID == id then return p end
    end
    return nil
end

-- Vanilla's own helpers the phaser's menu reaches for: draw the tool the way
-- the chop draws the axe, and walk up to something. Recorded, and the walk
-- really moves the player, so a cut that had to close the distance first is
-- measured from where they end up.
SIM.equipped = {}
function ISWorldObjectContextMenu.equip(player, current, item, primary)
    if primary ~= false then player.primary = item else player.secondary = item end
    table.insert(SIM.equipped, item)
end
luautils = luautils or {}
SIM.walks = {}
function luautils.walkAdj(player, sq)
    player.x, player.y = sq.x + 1.5, sq.y + 0.5
    table.insert(SIM.walks, { x = sq.x, y = sq.y })
    return true
end

--- The engine's "is the mouse over the UI", as UIManager.isOverElement asks
--- it: an element on screen, not hidden, whose rectangle holds the point. It
--- is purely geometric -- it never calls a Lua isMouseOver -- and while it
--- answers yes the world gets no right-click and no aiming. The phaser's first
--- overlay was screen-sized and took both away from the author for the rest
--- of a session (2026-09-24), with every test passing, because nothing here
--- asked. Returns the element in the way, or nil.
function SIM.uiUnderMouse(mx, my)
    for _, e in ipairs(SIM.uiElements or {}) do
        if e.onScreen and e.visible ~= false then
            local x, y = e.x or 0, e.y or 0
            local w, h = e.width or 0, e.height or 0
            if x >= 0 and y >= 0 and mx >= x and my >= y
               and mx < x + w and my < y + h then
                return e
            end
        end
    end
    return nil
end
