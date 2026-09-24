--[[ Shuttlecraft -- the PADD's timed actions (PADD.md).

    Load a book onto a PADD, read one off it, copy a library, erase one.

    **Shared, and globals, on purpose.** In build 42 a client does not run a
    Lua timed action by itself: LuaTimedActionNew.start() hands it to
    ActionManager.createNetTimedAction, and the server rebuilds it --
    NetTimedAction.parse looks the class up **by its global name** and calls
    its `new` with the arguments it was sent (bci 75-167). Those arguments are
    read off the action by the **parameter names of `new`**
    (NetTimedAction.set, `Prototype.locvars`), so every `new` below stores
    each parameter under exactly its own name. A class the server cannot see,
    or a parameter stored under another name, is an action that never
    completes and says nothing.

    Where each half runs, from LuaTimedActionNew's own bytecode:
      * `start`, `update`, `stop`: wherever the action is;
      * `perform`: the client (and single player) -- presentation;
      * `complete`: **never on a client** (bci 34) -- the server, or single
        player. It is where the library is written and where reading gives
        what it gives, exactly as ISReadABook:complete() does it.
]]

require "TimedActions/ISBaseTimedAction"
require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Padd"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Pd = TREK.Padd

local function note(character, key, ...)
    if isServer() then return end
    U.note(character, getText(key, ...), 150, 200, 255)
end

local function sync(character, padd)
    -- The engine's own push of an item's mod data to the player carrying it
    -- -- vanilla's ISChangeFishingRodEquip:complete() writes a rod's line and
    -- calls exactly this.
    U.try("padd.sync", function() syncItemModData(character, padd) end)
end

local function holdPadd(action)
    action:setActionAnim(CharacterActionAnims.Read)
    action:setAnimVariable("ReadType", "book")
    action:setOverrideHandModels(nil, action.padd)
end

---------------------------------------------------------------------------
-- Load a book onto the PADD
---------------------------------------------------------------------------
TREKLoadPadd = ISBaseTimedAction:derive("TREKLoadPadd")

function TREKLoadPadd:new(character, padd, book)
    local o = ISBaseTimedAction.new(self, character)
    o.character = character
    o.padd = padd
    o.book = book
    o.stopOnWalk = true
    o.stopOnRun = true
    o.maxTime = U.try("padd.instant", function() return character:isTimedActionInstant() end)
                and 1 or C.PaddLoadTicks
    return o
end

function TREKLoadPadd:isValid()
    if not Pd.inHand(self.character, self.padd) then return false end
    if not Pd.isBook(self.book) or not Pd.canReach(self.character, self.book) then
        return false
    end
    local entry = Pd.entryOf(self.book)
    return entry ~= nil and not Pd.has(self.padd, entry)
end

function TREKLoadPadd:start()
    holdPadd(self)
    if not isServer() then
        U.try("padd.chirp", function()
            self.character:playSoundLocal("TREK_TricorderChirp")
        end)
    end
end

function TREKLoadPadd:stop()
    ISBaseTimedAction.stop(self)
end

function TREKLoadPadd:perform()
    local name = U.try("padd.bookName", function() return self.book:getName() end) or "?"
    note(self.character, "IGUI_TREK_PaddLoaded", name)
    ISBaseTimedAction.perform(self)
end

function TREKLoadPadd:complete()
    local entry = Pd.entryOf(self.book)
    if entry and Pd.add(self.padd, entry) then
        sync(self.character, self.padd)
        U.log("padd: %s loaded %s (%d titles)",
              tostring(TREK.Ship and TREK.Ship.usernameOf(self.character)),
              tostring(entry.type), Pd.count(self.padd))
    end
    return true
end

function TREKLoadPadd:getDuration()
    return self.maxTime
end

---------------------------------------------------------------------------
-- Read a book off the PADD
---------------------------------------------------------------------------
-- Its own action rather than ISReadABook, because ISReadABook needs a real
-- book in the reader's inventory -- and a real book put there for the length
-- of a read is a duplication exploit with an exit for every way to drop it
-- (PADD.md section 3). The effects are ISReadABook's, applied in complete()
-- on the server to a book rebuilt by Pd.makeBook that is in no container.
TREKReadPadd = ISBaseTimedAction:derive("TREKReadPadd")

function TREKReadPadd:new(character, padd, key)
    local o = ISBaseTimedAction.new(self, character)
    o.character = character
    o.padd = padd
    o.key = key
    o.entry = Pd.find(padd, key)
    o.stopOnWalk = false
    o.stopOnRun = true
    o.ignoreHandsWounds = true
    o.caloriesModifier = 0.5
    o.forceProgressBar = true
    o.maxTime = Pd.readTicks(character, o.entry)
    o.startPage = 0
    if o.entry and (o.entry.pages or 0) > 0 then
        o.startPage = U.try("padd.start", function()
            return character:getAlreadyReadPages(o.entry.type)
        end) or 0
        if o.startPage >= o.entry.pages then o.startPage = 0 end
    end
    return o
end

function TREKReadPadd:isValid()
    if not Pd.inHand(self.character, self.padd) then return false end
    self.entry = Pd.find(self.padd, self.key)
    return self.entry ~= nil and Pd.readRefusal(self.character, self.entry) == nil
end

function TREKReadPadd:start()
    holdPadd(self)
    U.try("padd.reading", function() self.character:setReading(true) end)
    U.try("padd.event", function() self.character:reportEvent("EventRead") end)
    if not isServer() then
        U.try("padd.chirp", function()
            self.character:playSoundLocal("TREK_TricorderChirp")
        end)
    end
end

--- Page progress, kept as vanilla keeps it: per character, per book type.
--- Written on the machine that owns the effects, so a read interrupted
--- half-way resumes half-way -- off the PADD or off paper.
function TREKReadPadd:update()
    local e = self.entry
    if isClient() or not e or (e.pages or 0) <= 0 then return end
    local pages = self.startPage + math.floor((e.pages - self.startPage) * self:getJobDelta())
    if pages > e.pages then pages = e.pages end
    U.try("padd.progress", function()
        self.character:setAlreadyReadPages(e.type, pages)
    end)
end

function TREKReadPadd:stop()
    U.try("padd.reading", function() self.character:setReading(false) end)
    ISBaseTimedAction.stop(self)
end

function TREKReadPadd:perform()
    U.try("padd.reading", function() self.character:setReading(false) end)
    if self.entry then note(self.character, "IGUI_TREK_PaddFinished", self.entry.name or "?") end
    ISBaseTimedAction.perform(self)
end

--- What reading gives. **Mirrors ISReadABook:complete()** (42.20.4, lines
--- 324-376), against a book that is in no container.
function TREKReadPadd:complete()
    local e = self.entry or Pd.find(self.padd, self.key)
    if not e then return true end
    local c = self.character

    if e.kind == "skill" then
        local sb = Pd.skillOf(e.skill)
        local mult = Pd.multiplierFor(e)
        if sb and mult then
            U.try("padd.xp", function()
                addXpMultiplier(c, sb.perk, mult, e.level, e.maxLevel)
            end)
        end
    else
        -- Recipes from the script's list: vanilla records the book as read,
        -- which is what the recipe knowledge keys on.
        if e.kind == "recipe" then
            U.try("padd.readBook", function() c:getAlreadyReadBook():add(e.type) end)
        end
        Pd.applyLiterature(c, e)
        -- Vanilla asks the reader's own client to apply the comfort too; the
        -- stats are kept on both. Only on a server: in single player the
        -- two halves are one process and it has just been done.
        if isServer() then TREK.Net.toClient(c, "paddRead", { entry = e }) end
    end

    if e.md and e.md.learnedRecipe then
        U.try("padd.learn", function() c:learnRecipe(e.md.learnedRecipe) end)
    end
    if e.md and e.md.printMediaId ~= nil then
        U.try("padd.media", function() c:addReadPrintMedia(e.md.printMediaId) end)
    end
    if (e.pages or 0) > 0 then
        U.try("padd.done", function() c:setAlreadyReadPages(e.type, e.pages) end)
    end
    -- PF_Recipes + PF_Traits + PF_AlreadyReadBook, as vanilla sends them.
    U.try("padd.syncFields", function() sendSyncPlayerFields(c, 0x00000007) end)
    U.log("padd: %s read %s", tostring(TREK.Ship and TREK.Ship.usernameOf(c)),
          tostring(e.type))
    return true
end

function TREKReadPadd:getDuration()
    return self.maxTime
end

---------------------------------------------------------------------------
-- Copy one PADD's library onto another
---------------------------------------------------------------------------
TREKCopyPadd = ISBaseTimedAction:derive("TREKCopyPadd")

function TREKCopyPadd:new(character, padd, target)
    local o = ISBaseTimedAction.new(self, character)
    o.character = character
    o.padd = padd
    o.target = target
    o.stopOnWalk = true
    o.stopOnRun = true
    local ticks = C.PaddCopyBaseTicks + C.PaddCopyTicksPerTitle * Pd.count(padd)
    o.maxTime = math.min(C.PaddCopyMaxTicks, ticks)
    if U.try("padd.instant", function() return character:isTimedActionInstant() end) then
        o.maxTime = 1
    end
    return o
end

function TREKCopyPadd:isValid()
    return self.padd ~= self.target and Pd.isPadd(self.target)
           and Pd.inHand(self.character, self.padd)
           and Pd.inHand(self.character, self.target)
           and (Pd.count(self.padd) + #Pd.tapes(self.padd)) > 0
end

function TREKCopyPadd:start()
    holdPadd(self)
    if not isServer() then
        U.try("padd.chirp", function()
            self.character:playSoundLocal("TREK_TricorderChirp")
        end)
    end
end

function TREKCopyPadd:stop()
    ISBaseTimedAction.stop(self)
end

function TREKCopyPadd:perform()
    note(self.character, "IGUI_TREK_PaddCopied")
    ISBaseTimedAction.perform(self)
end

function TREKCopyPadd:complete()
    -- Books and transcripts in one action (PADD.md 12.7): handing somebody a
    -- copy is handing them everything the PADD reads.
    local n = Pd.merge(self.padd, self.target)
    local t = Pd.mergeTapes(self.padd, self.target)
    if n + t > 0 then sync(self.character, self.target) end
    U.log("padd: copied %d title(s) and %d transcript(s) onto another PADD", n, t)
    return true
end

function TREKCopyPadd:getDuration()
    return self.maxTime
end

---------------------------------------------------------------------------
-- Erase a PADD
---------------------------------------------------------------------------
TREKErasePadd = ISBaseTimedAction:derive("TREKErasePadd")

function TREKErasePadd:new(character, padd)
    local o = ISBaseTimedAction.new(self, character)
    o.character = character
    o.padd = padd
    o.stopOnWalk = true
    o.stopOnRun = true
    o.maxTime = U.try("padd.instant", function() return character:isTimedActionInstant() end)
                and 1 or C.PaddEraseTicks
    return o
end

function TREKErasePadd:isValid()
    return Pd.inHand(self.character, self.padd)
           and (Pd.count(self.padd) + #Pd.tapes(self.padd)) > 0
end

function TREKErasePadd:start()
    holdPadd(self)
end

function TREKErasePadd:stop()
    ISBaseTimedAction.stop(self)
end

function TREKErasePadd:perform()
    note(self.character, "IGUI_TREK_PaddErased")
    ISBaseTimedAction.perform(self)
end

function TREKErasePadd:complete()
    local n = Pd.erase(self.padd)
    sync(self.character, self.padd)
    U.log("padd: erased %d title(s)", n)
    return true
end

function TREKErasePadd:getDuration()
    return self.maxTime
end

---------------------------------------------------------------------------
-- Transcribe a tape onto the PADD (PADD.md 12.3)
---------------------------------------------------------------------------
-- The tape stays what it is; the PADD gains a text copy, keyed by the
-- recording id. **Any tape** -- the author's call (2026-09-24), reversing the
-- spec's "only a tape you have watched to the end": a PADD is a way to read a
-- tape instead of sitting in front of the television, and reading it
-- (TREKReadTape, below) does to you exactly what watching it would, once.
TREKTranscribePadd = ISBaseTimedAction:derive("TREKTranscribePadd")

function TREKTranscribePadd:new(character, padd, tape)
    local o = ISBaseTimedAction.new(self, character)
    o.character = character
    o.padd = padd
    o.tape = tape
    o.stopOnWalk = true
    o.stopOnRun = true
    o.maxTime = U.try("padd.instant", function() return character:isTimedActionInstant() end)
                and 1 or C.PaddTranscribeTicks
    return o
end

function TREKTranscribePadd:isValid()
    if not Pd.inHand(self.character, self.padd) then return false end
    local id = Pd.recordingOf(self.tape)
    if not id or Pd.hasTape(self.padd, id) then return false end
    return Pd.canReach(self.character, self.tape)
end

function TREKTranscribePadd:start()
    holdPadd(self)
    if not isServer() then
        U.try("padd.chirp", function()
            self.character:playSoundLocal("TREK_TricorderChirp")
        end)
    end
end

function TREKTranscribePadd:stop()
    ISBaseTimedAction.stop(self)
end

function TREKTranscribePadd:perform()
    local id = Pd.recordingOf(self.tape)
    if id then note(self.character, "IGUI_TREK_PaddTranscribedNote", Pd.tapeTitle(id)) end
    ISBaseTimedAction.perform(self)
end

function TREKTranscribePadd:complete()
    local id = Pd.recordingOf(self.tape)
    if id and Pd.addTape(self.padd, id) then
        sync(self.character, self.padd)
        U.log("padd: transcribed %s (%d transcripts)", id, #Pd.tapes(self.padd))
    end
    return true
end

function TREKTranscribePadd:getDuration()
    return self.maxTime
end

---------------------------------------------------------------------------
-- Read a transcript
---------------------------------------------------------------------------
-- Reading a tape off the PADD does what watching it does: every line's
-- effects -- boredom, stress, a training tape's skill XP up to the sandbox's
-- media cut-off, a recipe -- applied by **vanilla's own interpreter**,
-- `ISRadioInteractions.checkPlayer`, the function the television reaches
-- through OnDeviceText. That matters three ways:
--
--   * it records each line as heard (`addKnownMediaLine`) before it applies
--     anything, so a line pays once per character **whether it was heard on
--     the television or read here** -- neither route can farm the other;
--   * it keeps the XP cut-off, the halos and the per-code debounce the
--     engine gives a tape;
--   * called with no source square (-1, -1, -1) it skips the indoors check,
--     which only means anything for a screen in a room.
--
-- The debounce is thirty ticks per code, so the lines are applied one at a
-- time as the read goes on, paced like a television, rather than all in the
-- last tick where every BOR after the first would be swallowed. On the
-- authority only: a tape's effects land on the server's copy of a player,
-- exactly as the television's do in multiplayer.
TREKReadTape = ISBaseTimedAction:derive("TREKReadTape")

--- The television's own pacing (DeviceData.updateMediaPlaying: a line is on
--- screen for length / 10 * 60 frames), clamped, then the PADD's speed.
function Pd.tapeTicks(id)
    local rec = type(RecMedia) == "table" and RecMedia[id]
    if type(rec) ~= "table" then return 1 end
    local total = 0
    for _, ln in ipairs(rec.lines or {}) do
        local len = #(getText(ln.text) or "")
        total = total + math.max(C.PaddTapeLineMin, math.min(C.PaddTapeLineMax, len * 6))
    end
    return math.max(1, math.floor(total / C.PaddReadSpeed))
end

function TREKReadTape:new(character, padd, tape)
    local o = ISBaseTimedAction.new(self, character)
    o.character = character
    o.padd = padd
    o.tape = tape
    o.stopOnWalk = false
    o.stopOnRun = true
    o.forceProgressBar = true
    o.applied = 0
    o.maxTime = U.try("padd.instant", function() return character:isTimedActionInstant() end)
                and 1 or Pd.tapeTicks(tape)
    return o
end

function TREKReadTape:isValid()
    return Pd.inHand(self.character, self.padd) and Pd.hasTape(self.padd, self.tape)
end

function TREKReadTape:start()
    holdPadd(self)
    U.try("padd.reading", function() self.character:setReading(true) end)
end

--- Applies lines up to `upto`, in order, each once.
function TREKReadTape:applyTo(upto)
    if isClient() then return end
    local rec = type(RecMedia) == "table" and RecMedia[self.tape]
    if type(rec) ~= "table" then return end
    local lines = rec.lines or {}
    local ri = U.try("padd.radio", function() return ISRadioInteractions:getInstance() end)
    if not ri then return end
    while self.applied < math.min(upto, #lines) do
        self.applied = self.applied + 1
        local ln = lines[self.applied]
        U.try("padd.tapeLine", function()
            ri.checkPlayer(self.character, ln.text, ln.codes or "", -1, -1, -1,
                           getText(ln.text))
        end)
    end
end

-- The client runs update() too, on its own copy of the action. The guard
-- is in applyTo alone -- one guard where the effects are applied, rather than
-- two that cover for each other and hide from a mutation (DEV_GUIDE).
function TREKReadTape:update()
    local rec = type(RecMedia) == "table" and RecMedia[self.tape]
    local n = rec and #(rec.lines or {}) or 0
    self:applyTo(math.floor(n * self:getJobDelta()))
end

function TREKReadTape:stop()
    U.try("padd.reading", function() self.character:setReading(false) end)
    ISBaseTimedAction.stop(self)
end

function TREKReadTape:perform()
    U.try("padd.reading", function() self.character:setReading(false) end)
    note(self.character, "IGUI_TREK_PaddFinished", Pd.tapeTitle(self.tape))
    ISBaseTimedAction.perform(self)
end

function TREKReadTape:complete()
    -- Everything left. Not math.huge: Kahlua has no such field (pz_sim.lua
    -- removes it for that reason), and a nil compare throws on the last tick.
    self:applyTo(1000000)
    U.log("padd: %s read the transcript of %s",
          tostring(TREK.Ship and TREK.Ship.usernameOf(self.character)), tostring(self.tape))
    return true
end

function TREKReadTape:getDuration()
    return self.maxTime
end

---------------------------------------------------------------------------
-- The client's half of reading literature
---------------------------------------------------------------------------
-- Vanilla's own literature.readLiterature looks the book up by item id in
-- the reader's inventory, and a book read off a PADD has no id there -- so
-- the PADD sends the entry and the client rebuilds the book itself.
TREK.Net.onClient("paddRead", function(args)
    local player = U.player(0)
    if not player or type(args.entry) ~= "table" then return end
    Pd.applyLiterature(player, args.entry)
end)
