--[[ Shuttlecraft -- cutting with a phaser (PHASERS.md 7).

    A phaser held on a tree fells it; held on a door, it burns the door out of
    its frame, whatever was locking it; held on a stump, a rock or a bush, it
    clears it away, so a stretch of wild ground can be cleared to build on
    (PHASERS.md 3, *Clearing ground*). This file is the rules and the timed
    action that does it. The beam that everybody sees is TREK_PhaserFX.lua,
    and the right-click that starts it is TREK_Phaser.lua.

    **Where each half runs**, which is the whole design (DEV_GUIDE.md, *A timed
    action is rebuilt on the server by its name and its parameters*):

      * `start`, `update`, `stop`, `perform` run on the cutter's own machine --
        its beam, its hum, its note.
      * `serverStart` / `serverStop` run on the server when it rebuilds the
        action (NetTimedAction.start reads `serverStart` off the table and
        calls it, and the class carries `serverStop` beside it). They tell
        every client the beam went on or off, which is how anybody else sees
        it.
      * `complete` never runs on a client. It re-finds the target on the
        server's own square, checks it again, and changes the world with the
        engine's own transmit calls.

    Single player is one process: start, update, perform and complete all run
    here, `serverStart` is never called, and Net.toAll runs the client's
    handler directly -- so the same code path covers all three setups.

    **The target travels as coordinates and a kind**, not as the object. The
    server looks it up again on its own square, which is the only copy it may
    believe, and a door that somebody else broke first is simply gone and the
    action is invalid.

    **The engine calls, and why these ones** (PHASERS.md 8):

      * a tree: `IsoTree:toppleTree(character)`. Its bytecode returns at once
        on a client; on the authority it removes the tree with
        transmitRemoveItemFromSquare, plays the falling sound to everybody,
        drops the logs through AddWorldInventoryItem (which transmits), and
        puts the stump down. It is the same call the axe reaches through
        WeaponHit once a tree's damage runs out -- the phaser skips only the
        counting-down.
      * a door: what the sledgehammer's own complete() does on the authority
        (ISDestroyStuffAction): barricades on both sides, every leaf of a
        double door or garage door through buildUtil, then
        transmitRemoveItemFromSquare. buildUtil lives in server/, which is
        exactly where this runs.
      * **no lock is consulted at all.** A persistent beam defeats any lock
        because the door stops being there (the author, 2026-09-24).
      * a stump, a rock or a bush: transmitRemoveItemFromSquare, which is
        where vanilla's own pickaxe (ISPickAxeGroundCoverItem) and bush
        clearing (ISRemoveBush) end. What counts as each is vanilla's own
        test, not a list of ours: `isStump()`, the `boulders_` and
        `crafting_ore_` sprites `isOres()` looks for, the stone names
        GroundCoverItems picks up, and the `canBeCut` flag. A boulder two
        tiles wide goes whole, every piece of its sprite grid
        (getSpriteGridObjectsIncludingSelf, as the sledgehammer's destroy
        cursor finds them). The phaser leaves nothing behind: no stones,
        no twigs, no scrap wood. That is the point of it.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TimedActions/ISBaseTimedAction"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net

local PC = {}
TREK.PhaserCut = PC

---------------------------------------------------------------------------
-- What can be cut
---------------------------------------------------------------------------
--- The kinds that clear ground rather than cut: a sandbox's "Trees only"
--- lets them, since none of them keeps anybody out of anywhere.
PC.CLEARING = { stump = true, rock = true, bush = true }

local function spriteOf(obj)
    return U.try("phaser.sprite", function() return obj:getSprite() end)
end

local function props(obj)
    local spr = spriteOf(obj)
    return spr and U.try("phaser.props", function() return spr:getProperties() end)
end

--- A boulder, an ore deposit or a stone lying on the ground; never the
--- ground itself. `boulders_` and `crafting_ore_` are the two prefixes the
--- engine's own IsoObject.isOres() tests, and the same sheet has rock
--- *floors* in it (boulders_40..47, 56..63, `solidfloor`), which would leave
--- a hole to the level below.
function PC.isRock(obj)
    local spr = spriteOf(obj)
    local name = spr and U.try("phaser.spriteName", function() return spr:getName() end)
    local p = props(obj)
    local custom = p and U.try("phaser.customName", function() return p:get("CustomName") end)
    if custom and C.PhaserStones[custom] then return true end
    if type(name) ~= "string" then return false end
    if name:sub(1, 9) ~= "boulders_" and name:sub(1, 13) ~= "crafting_ore_" then
        return false
    end
    return not (p and U.try("phaser.solidfloor", function()
        return p:has(IsoFlagType.solidfloor)
    end))
end

--- A bush: the `canBeCut` flag vanilla's ISRemoveBush clears, or the
--- landscaping bush and hedge a shovel would dig up.
function PC.isBush(obj)
    local p = props(obj)
    if not p then return false end
    if U.try("phaser.canBeCut", function() return p:has(IsoFlagType.canBeCut) end) then
        return true
    end
    local custom = U.try("phaser.bushName", function() return p:get("CustomName") end)
    return custom == "Bush" or custom == "Hedge"
end

--- "tree", "door", "stump", "rock", "bush" or nil for one world object.
function PC.kindOf(obj)
    if not obj then return nil end
    if instanceof(obj, "IsoTree") then return "tree" end
    if instanceof(obj, "IsoDoor") then return "door" end
    if instanceof(obj, "IsoThumpable") then
        local door = U.try("phaser.isDoor", function() return obj:isDoor() end)
        if door then return "door" end
    end
    -- Anything with a class of its own is somebody's furniture, a crop or a
    -- machine, not the ground; only plain objects are cleared.
    if instanceof(obj, "IsoWorldInventoryObject") or instanceof(obj, "IsoThumpable") then
        return nil
    end
    if U.try("phaser.isStump", function() return obj:isStump() end) then return "stump" end
    if PC.isRock(obj) then return "rock" end
    if PC.isBush(obj) then return "bush" end
    return nil
end

--- The object of a kind on a square, or nil.
function PC.onSquare(sq, kind)
    if not sq then return nil end
    local objects = U.try("phaser.objects", function() return sq:getObjects() end)
    if not objects then return nil end
    local n = U.try("phaser.objectCount", function() return objects:size() end) or 0
    for i = 0, n - 1 do
        local o = objects:get(i)
        if PC.kindOf(o) == kind then return o end
    end
    return nil
end

--- The target of a cut, looked up where this code is running.
function PC.target(x, y, z, kind)
    local sq = U.square(x, y, z, false)
    return PC.onSquare(sq, kind), sq
end

--- The cutting weapon in either of the player's hands, or nil: the phaser,
--- or the phaser rifle -- anything C.EnergyWeapons marks `cuts`. A
--- disruptor in hand is no cutter, and the server refuses it (NotHeld).
function PC.inHand(player)
    if not player then return nil end
    for _, get in ipairs({ "getPrimaryHandItem", "getSecondaryHandItem" }) do
        local item = U.try("phaser.hand", function() return player[get](player) end)
        local full = item and U.try("phaser.handType", function()
            return item:getFullType()
        end)
        local spec = C.energyWeapon(full)
        if spec and spec.cuts then return item end
    end
    return nil
end

--- True when the sandbox lets a phaser cut this kind of thing. "Trees only"
--- is the woodsman's setting, and clearing ground is woodsman's work: it
--- takes every lock away and leaves the stumps, rocks and bushes.
function PC.allowed(kind)
    local mode = C.phaserCutting()
    if mode == C.PhaserCutNone then return false end
    if mode == C.PhaserCutTrees and kind ~= "tree" and not PC.CLEARING[kind] then
        return false
    end
    return true
end

--- True when the square is in a safehouse this player is not a member of.
--- A tree is never refused for it (it never was); a door, and the ground
--- somebody may have landscaped, are.
function PC.inStrangersSafehouse(player, sq, kind)
    if kind == "tree" or not sq then return false end
    local name = U.try("phaser.username", function() return player:getUsername() end)
    return U.try("phaser.safehouse", function()
        return SafeHouse.isSafeHouse(sq, name, true)
    end) and true or false
end

local function distance(player, sq)
    local px = U.try("phaser.px", function() return player:getX() end) or 0
    local py = U.try("phaser.py", function() return player:getY() end) or 0
    local dx = px - (sq:getX() + 0.5)
    local dy = py - (sq:getY() + 0.5)
    return math.sqrt(dx * dx + dy * dy)
end

--- Why this player may not cut this, as an IG_UI key, or nil when they may.
---
--- Every reason has words behind it (tests/test_multiplayer.py checks the
--- keys), because a correct refusal nobody is shown is indistinguishable from
--- a broken feature (DEV_GUIDE.md, the probes).
function PC.refusal(player, obj, kind, sq)
    if not player or not obj or not sq then return "IGUI_TREK_PhaserNoTarget" end
    if not PC.allowed(kind) then return "IGUI_TREK_PhaserCutOff" end
    if not PC.inHand(player) then return "IGUI_TREK_PhaserNotHeld" end
    local pz = U.try("phaser.pz", function() return player:getZ() end) or 0
    if math.floor(pz) ~= sq:getZ() or distance(player, sq) > C.PhaserCutRange + 0.75 then
        return "IGUI_TREK_PhaserTooFar"
    end
    -- A server's safehouse rules are a promise to its players; a phaser is
    -- not the way round them. isSafeHouse answers only for a safehouse the
    -- named player is NOT a member of.
    if PC.inStrangersSafehouse(player, sq, kind) then return "IGUI_TREK_PhaserSafehouse" end
    return nil
end

---------------------------------------------------------------------------
-- Doing it (the authority only)
---------------------------------------------------------------------------
--- Fells a tree, the axe's way minus the counting.
function PC.fell(player, tree)
    return U.try("phaser.toppleTree", function()
        tree:toppleTree(player)
        return true
    end) == true
end

local function remove(o)
    local sq = o and U.try("phaser.removeSq", function() return o:getSquare() end)
    if not sq then return false end
    return U.try("phaser.remove", function()
        sq:transmitRemoveItemFromSquare(o)
        return true
    end) == true
end

--- Burns a door out of its frame: the sledgehammer's authority path.
function PC.breach(player, door)
    for _, get in ipairs({ "getBarricadeOnSameSquare", "getBarricadeOnOppositeSquare" }) do
        local b = U.try("phaser.barricade", function() return door[get](door) end)
        if b then remove(b) end
    end
    local leaves = {}
    if buildUtil then
        leaves = U.try("phaser.doubleDoor", function()
            return buildUtil.getDoubleDoorObjects(door)
        end) or {}
        if #leaves == 0 then
            leaves = U.try("phaser.garageDoor", function()
                return buildUtil.getGarageDoorObjects(door)
            end) or {}
        end
    end
    if #leaves == 0 then leaves = { door } end
    local gone = 0
    for _, leaf in ipairs(leaves) do
        if remove(leaf) then gone = gone + 1 end
    end
    U.try("phaser.breakSound", function() player:playSound("BreakDoor") end)
    return gone > 0
end

--- Every object that makes up this one thing. A boulder drawn across two or
--- four squares is one object per square, joined only by its sprite grid.
function PC.parts(obj, kind)
    if kind ~= "rock" then return { obj } end
    local list = U.try("phaser.spriteGrid", function()
        return obj:getSpriteGridObjectsIncludingSelf(ArrayList.new())
    end)
    local n = list and (U.try("phaser.spriteGridN", function() return list:size() end) or 0) or 0
    if n == 0 then return { obj } end
    local parts = {}
    for i = 0, n - 1 do table.insert(parts, list:get(i)) end
    return parts
end

--- Clears a stump, a rock or a bush away, leaving nothing. All of a boulder
--- goes: half a boulder is still in the way.
function PC.clear(player, obj, kind)
    local gone = 0
    for _, part in ipairs(PC.parts(obj, kind)) do
        if remove(part) then gone = gone + 1 end
    end
    return gone > 0
end

--- The key a beam is known by on every machine: one cutter, one beam.
function PC.beamKey(player)
    local name = U.try("phaser.keyName", function() return player:getUsername() end)
    if not name or name == "" then name = "local" end
    return name
end

local function onlineId(player)
    return U.try("phaser.onlineId", function() return player:getOnlineID() end) or -1
end

--- What every client is told when a beam goes on.
function PC.beamArgs(player, x, y, z, kind, ms)
    return {
        key = PC.beamKey(player), id = onlineId(player), on = true,
        fx = U.try("phaser.fx", function() return player:getX() end) or x,
        fy = U.try("phaser.fy", function() return player:getY() end) or y,
        fz = U.try("phaser.fz", function() return player:getZ() end) or z,
        x = x, y = y, z = z, kind = kind, ms = ms,
    }
end

local function fx()
    return TREK.PhaserFX
end

---------------------------------------------------------------------------
-- The timed action
---------------------------------------------------------------------------
-- Global and in shared/, because the server rebuilds it by its class name;
-- and every parameter of `new` is stored under exactly its own name, because
-- that is how the server reads them back (NetTimedAction.set).
TREKPhaserCut = ISBaseTimedAction:derive("TREKPhaserCut")

function TREKPhaserCut:new(character, x, y, z, kind)
    local o = ISBaseTimedAction.new(self, character)
    o.x, o.y, o.z = x, y, z
    o.kind = kind
    o.stopOnWalk = true
    o.stopOnRun = true
    o.forceProgressBar = true
    o.maxTime = o:getDuration()
    return o
end

function TREKPhaserCut:getDuration()
    local instant = U.try("phaser.instant", function()
        return self.character:isTimedActionInstant()
    end)
    if instant then return 1 end
    if self.kind == "tree" then return C.PhaserTreeTime end
    if PC.CLEARING[self.kind] then return C.PhaserClearTime[self.kind] end
    return C.PhaserDoorTime
end

function TREKPhaserCut:isValid()
    local obj, sq = PC.target(self.x, self.y, self.z, self.kind)
    return PC.refusal(self.character, obj, self.kind, sq) == nil
end

function TREKPhaserCut:waitToStart()
    local obj = PC.target(self.x, self.y, self.z, self.kind)
    if obj then
        U.try("phaser.face", function() self.character:faceThisObject(obj) end)
    end
    return U.try("phaser.turning", function()
        return self.character:shouldBeTurning()
    end) == true
end

function TREKPhaserCut:start()
    -- A welder's pose: a tool held out and aimed at the work.
    self:setActionAnim("BlowTorch")
    self:setOverrideHandModels(PC.inHand(self.character), nil)
    if fx() then
        fx().beamOn(PC.beamArgs(self.character, self.x, self.y, self.z,
                                self.kind, C.PhaserBeamGraceMs))
    end
end

function TREKPhaserCut:serverStart()
    Net.toAll("phaserBeam", PC.beamArgs(self.character, self.x, self.y, self.z,
                                        self.kind, C.PhaserBeamGraceMs))
end

function TREKPhaserCut:update()
    local obj = PC.target(self.x, self.y, self.z, self.kind)
    if obj then
        U.try("phaser.face", function() self.character:faceThisObject(obj) end)
    end
    if fx() then fx().keepAlive(PC.beamKey(self.character)) end
    -- The noise is the world's, so the authority makes it: a cut draws
    -- attention the way an axe on a tree does, a little more quietly.
    if not isClient() then
        self.ticks = (self.ticks or 0) + 1
        if self.ticks % C.PhaserCutNoiseEvery == 1 then
            local n = C.PhaserCutNoise
            U.try("phaser.noise", function()
                addSound(self.character, self.x, self.y, self.z, n.radius, n.volume)
            end)
        end
    end
end

local function beamOff(action)
    if fx() then fx().beamOff({ key = PC.beamKey(action.character) }) end
end

function TREKPhaserCut:stop()
    beamOff(self)
    ISBaseTimedAction.stop(self)
end

function TREKPhaserCut:serverStop()
    Net.toAll("phaserBeam", { key = PC.beamKey(self.character), on = false })
end

function TREKPhaserCut:perform()
    beamOff(self)
    ISBaseTimedAction.perform(self)
end

--- The world change. Never on a client.
function TREKPhaserCut:complete()
    local obj, sq = PC.target(self.x, self.y, self.z, self.kind)
    local why = PC.refusal(self.character, obj, self.kind, sq)
    local done = false
    if not why then
        if self.kind == "tree" then
            done = PC.fell(self.character, obj)
        elseif PC.CLEARING[self.kind] then
            done = PC.clear(self.character, obj, self.kind)
        else
            done = PC.breach(self.character, obj)
        end
        if not done then
            U.log("WARN phaser: the %s at %d,%d,%d did not come down",
                   tostring(self.kind), self.x, self.y, self.z)
        end
    end
    Net.toAll("phaserBeam", { key = PC.beamKey(self.character), on = false,
                              done = done and self.kind or nil,
                              x = self.x, y = self.y, z = self.z })
    if why then
        Net.toClient(self.character, "phaserRefused", { why = why })
    end
    return done
end

return PC
