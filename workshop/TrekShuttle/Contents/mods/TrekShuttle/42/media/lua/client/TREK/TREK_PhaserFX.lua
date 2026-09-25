--[[ Shuttlecraft -- the phaser's beam, as everybody sees it (PHASERS.md 5).

    Two kinds of beam, one renderer:

      * a **cutting beam**, on for as long as somebody holds a phaser on a
        tree or a door. The cutter's own action turns it on here; every other
        client hears `phaserBeam` from the server (TREKPhaserCut:serverStart)
        and turns it on too. It carries a looping hum and a light where it
        lands, and it **expires by itself** C.PhaserBeamGraceMs after it was
        last confirmed, so a lost "beam off" is a flicker, not a beam left
        burning for the session;
      * a **bolt**, one per shot, for C.PhaserBoltMs. Built from
        OnWeaponSwingHitPoint, which the engine fires for the shooter and --
        from its hit packet (zombie.network.fields.hit.Player.attack) -- for
        other players' shots on each client too, so nothing has to relay it.

    **Drawn in screen space, placing nothing in the world**, the torpedo's
    design (PHOTON_TORPEDOS.md): the strip is a quad from the emitter to the
    target through isoToScreenX/Y, drawn with ISUIElement:drawTextureAllPoint
    -- four corners, so no angle arithmetic and no tiling. It is drawn exactly
    the way design/art/ui/phaser_beam_sheet.png was judged: the strip tinted,
    the same strip untinted and thinner on top for the white-hot core, a flare
    at the emitter, a spark at the target. A tint multiplies, so one tinted
    draw can never have a white middle.

    The only thing that reaches the world is the light at the cut, added once
    per beam and removed with the handle addLamppost returned.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_PhaserCut"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local PC = TREK.PhaserCut

local FX = {}
TREK.PhaserFX = FX

local BEAM = "media/ui/TREK_PhaserBeam.png"
local SPARK = "media/ui/TREK_PhaserSpark.png"

-- key -> beam; see FX.beamOn for the fields.
FX.beams = {}
-- { char, x0, y0, z0, x, y, z, untilMs }
FX.bolts = {}

local overlay = nil

local function now() return getTimestampMs() end

---------------------------------------------------------------------------
-- Who is firing
---------------------------------------------------------------------------
--- The live character behind a beam, so it follows them if they turn.
local function shooter(b)
    local p = U.player(0)
    if p and PC.beamKey(p) == b.key then return p end
    if b.id and b.id >= 0 then
        return U.try("phaserFx.byId", function() return getPlayerByOnlineID(b.id) end)
    end
    return nil
end

local function playLocal(ch, name)
    if not ch then return nil end
    return U.try("phaserFx.sound", function() return ch:playSoundLocal(name) end)
end

---------------------------------------------------------------------------
-- Cutting beams
---------------------------------------------------------------------------
local function light(b)
    local L = C.PhaserLight
    b.light = U.try("phaserFx.light", function()
        return getCell():addLamppost(math.floor(b.x), math.floor(b.y), math.floor(b.z),
                                     L.r, L.g, L.b, L.radius)
    end)
end

local function douse(b)
    if not b.light then return end
    U.try("phaserFx.douse", function() getCell():removeLamppost(b.light) end)
    b.light = nil
end

local ensureOverlay

--- Turns a beam on, or keeps it on. Idempotent by key: the cutter's own
--- start() and the server's announcement both arrive on the cutter's machine.
function FX.beamOn(args)
    if not args or not args.key then return nil end
    local b = FX.beams[args.key]
    local grace = args.ms or C.PhaserBeamGraceMs
    if b then
        b.untilMs = now() + grace
        return b
    end
    b = {
        key = args.key, id = args.id, kind = args.kind,
        fx = args.fx, fy = args.fy, fz = args.fz,
        x = (args.x or 0) + 0.5, y = (args.y or 0) + 0.5, z = args.z or 0,
        untilMs = now() + grace, seed = (#args.key * 7) % 13,
    }
    FX.beams[args.key] = b
    b.char = shooter(b)
    playLocal(b.char, "TREK_PhaserBeamStart")
    b.sound = playLocal(b.char, "TREK_PhaserBeam")
    light(b)
    ensureOverlay()
    return b
end

function FX.keepAlive(key)
    local b = FX.beams[key]
    if b then b.untilMs = now() + C.PhaserBeamGraceMs end
end

--- Turns a beam off: the hum stops, the tail plays, the light goes.
function FX.beamOff(args)
    local b = args and FX.beams[args.key]
    if not b then return end
    FX.beams[args.key] = nil
    if b.char and b.sound then
        U.try("phaserFx.stop", function() b.char:stopOrTriggerSound(b.sound) end)
    end
    playLocal(b.char, "TREK_PhaserBeamEnd")
    douse(b)
end

--- How many beams are burning here. For the tests and the console.
function FX.count()
    local n = 0
    for _ in pairs(FX.beams) do n = n + 1 end
    return n
end

Net.onClient("phaserBeam", function(args)
    if args.on then FX.beamOn(args) else FX.beamOff(args) end
end)

Net.onClient("phaserRefused", function(args)
    local p = U.player(0)
    if p and args.why then U.note(p, getText(args.why), 1.0, 0.6, 0.4) end
end)

---------------------------------------------------------------------------
-- Bolts
---------------------------------------------------------------------------
local function isPhaser(weapon)
    return weapon and U.try("phaserFx.weaponType", function()
        return weapon:getFullType()
    end) == C.PhaserItem
end

--- One shot's bolt: from the emitter straight ahead to the weapon's range.
--- OnWeaponHitCharacter shortens it to whatever it hit, if anything did.
function FX.bolt(character, weapon)
    local px = U.try("phaserFx.bx", function() return character:getX() end)
    local py = U.try("phaserFx.by", function() return character:getY() end)
    local pz = U.try("phaserFx.bz", function() return character:getZ() end) or 0
    if not px or not py then return nil end
    -- Two calls: U.try hands back one value.
    local dx = U.try("phaserFx.dirX", function() return character:getForwardDirectionX() end) or 1
    local dy = U.try("phaserFx.dirY", function() return character:getForwardDirectionY() end) or 0
    local range = U.try("phaserFx.range", function() return weapon:getMaxRange() end) or 12
    local b = {
        char = character, untilMs = now() + C.PhaserBoltMs,
        x = px + dx * range, y = py + dy * range, z = pz,
    }
    table.insert(FX.bolts, b)
    ensureOverlay()
    return b
end

Events.OnWeaponSwingHitPoint.Add(function(character, weapon)
    if isPhaser(weapon) then FX.bolt(character, weapon) end
end)

Events.OnWeaponHitCharacter.Add(function(attacker, target, weapon)
    if not isPhaser(weapon) or not target then return end
    for i = #FX.bolts, 1, -1 do
        local b = FX.bolts[i]
        if b.char == attacker then
            b.x = U.try("phaserFx.hx", function() return target:getX() end) or b.x
            b.y = U.try("phaserFx.hy", function() return target:getY() end) or b.y
            return
        end
    end
end)

---------------------------------------------------------------------------
-- Upkeep
---------------------------------------------------------------------------
--- Drops what has expired. A beam that the server stopped confirming goes on
--- its own timer, with its sound and its light.
function FX.service()
    local t = now()
    for key, b in pairs(FX.beams) do
        if t > b.untilMs then FX.beamOff({ key = key }) end
    end
    for i = #FX.bolts, 1, -1 do
        if t > FX.bolts[i].untilMs then table.remove(FX.bolts, i) end
    end
end

Events.OnTick.Add(FX.service)

---------------------------------------------------------------------------
-- Drawing
---------------------------------------------------------------------------
--- Where the beam leaves the hand, in world terms: the character, a little
--- ahead of them toward the target, about chest high.
local function emitter(ch, fx, fy, fz, tx, ty)
    local px = ch and U.try("phaserFx.cx", function() return ch:getX() end) or fx
    local py = ch and U.try("phaserFx.cy", function() return ch:getY() end) or fy
    local pz = ch and U.try("phaserFx.cz", function() return ch:getZ() end) or fz
    if not px or not py then return nil end
    local dx, dy = tx - px, ty - py
    local len = math.sqrt(dx * dx + dy * dy)
    if len > 0.001 then
        px = px + dx / len * C.PhaserHandAhead
        py = py + dy / len * C.PhaserHandAhead
    end
    return px, py, (pz or 0) + C.PhaserHandZ
end

local Overlay = ISUIElement:derive("TREKPhaserOverlay")

--- **One pixel, in the corner -- not the whole screen.**
---
--- The first build made this a screen-sized element, the way the torpedo's
--- overlay is, and it broke the game the moment the first beam was drawn:
--- no world right-click and no aiming, for the rest of the session (the
--- author, 2026-09-24). The torpedo gets away with it because its overlay
--- exists only while somebody is at the controls, in a seat, where the world
--- is not being clicked on; this one stays up.
---
--- The engine's "is the mouse over the UI" is UIManager.isOverElement, and
--- it is **purely geometric**: visible, then the mouse inside the element's
--- rectangle (bci 23-187). It never calls the Lua isMouseOver, so overriding
--- that in Lua -- which this file did -- changes nothing. What does work is a
--- rectangle the mouse is never in. Drawing is not clipped to it: every draw
--- here is placed by absolute screen coordinates from isoToScreenX/Y, and an
--- ISUIElement's draws are only clipped inside a stencil.
function Overlay:new()
    local o = ISUIElement.new(self, 0, 0, 1, 1)
    o.backgroundColor = { r = 0, g = 0, b = 0, a = 0 }
    return o
end

function Overlay:onMouseDown() return false end
function Overlay:onRightMouseDown() return false end

--- One beam, the sheet's recipe: glow, core, muzzle flare, impact spark.
function Overlay:drawBeam(num, zoom, wx0, wy0, wz0, wx1, wy1, wz1, flicker, impact)
    local sx0 = isoToScreenX(num, wx0, wy0, wz0)
    local sy0 = isoToScreenY(num, wx0, wy0, wz0)
    local sx1 = isoToScreenX(num, wx1, wy1, wz1)
    local sy1 = isoToScreenY(num, wx1, wy1, wz1)
    if not sx0 or not sy0 or not sx1 or not sy1 then return end
    local dx, dy = sx1 - sx0, sy1 - sy0
    local len = math.sqrt(dx * dx + dy * dy)
    if len < 1 then return end
    local nx, ny = -dy / len, dx / len
    local T = C.PhaserTint
    local beam = getTexture(BEAM)
    local spark = getTexture(SPARK)

    local function band(factor, r, g, b, a)
        local h = C.PhaserBeamPx * factor * flicker / zoom / 2
        self:drawTextureAllPoint(beam,
            sx0 + nx * h, sy0 + ny * h,      -- top left
            sx1 + nx * h, sy1 + ny * h,      -- top right
            sx1 - nx * h, sy1 - ny * h,      -- bottom right
            sx0 - nx * h, sy0 - ny * h,      -- bottom left
            r, g, b, a)
    end

    local function flare(x, y, factor, r, g, b)
        local s = C.PhaserSparkPx * factor / zoom
        self:drawTextureScaled(spark, x - s / 2, y - s / 2, s, s, 1.0, r, g, b)
    end

    if beam then
        band(1.0, T.r, T.g, T.b, 1.0)
        band(C.PhaserCorePass, 1, 1, 1, C.PhaserCoreAlpha)
    end
    if spark then
        flare(sx0, sy0, C.PhaserMuzzle, T.r, T.g, T.b)
        flare(sx1, sy1, C.PhaserImpact * impact * flicker, T.r, T.g, T.b)
        flare(sx1, sy1, C.PhaserImpact * impact * 0.45, 1, 1, 1)
    end
end

function Overlay:render()
    local p = U.player(0)
    if not p then return end
    local num = U.try("phaserFx.num", function() return p:getPlayerNum() end) or 0
    local zoom = U.try("phaserFx.zoom", function() return getCore():getZoom(num) end) or 1
    if zoom <= 0 then zoom = 1 end
    local t = now()

    for _, b in pairs(FX.beams) do
        b.char = b.char or shooter(b)
        local ex, ey, ez = emitter(b.char, b.fx, b.fy, b.fz, b.x, b.y)
        if ex then
            -- The life in it: a quick shimmer in width, which the strip cannot
            -- carry because anything along it would stretch with it.
            local flicker = 0.88 + 0.12 * math.sin(t * 0.045 + b.seed)
            -- A tree is cut at the trunk, a door at the lock: both a little
            -- below the emitter's chest height.
            U.try("phaserFx.beam", function()
                self:drawBeam(num, zoom, ex, ey, ez, b.x, b.y, b.z + 0.3, flicker, 1.0)
            end)
        end
    end
    for _, b in ipairs(FX.bolts) do
        local ex, ey, ez = emitter(b.char, nil, nil, nil, b.x, b.y)
        if ex then
            U.try("phaserFx.bolt", function()
                self:drawBeam(num, zoom, ex, ey, ez, b.x, b.y, b.z + C.PhaserHandZ,
                              1.0, 0.6)
            end)
        end
    end
end

ensureOverlay = function()
    if overlay then return overlay end
    overlay = Overlay:new()
    overlay:initialise()
    overlay:setAlwaysOnTop(true)
    overlay:addToUIManager()
    return overlay
end

--- Exposed for the debug console: TREK_PhaserFX() reports what is burning.
function TREK_PhaserFX()
    U.log("phaser fx: %d beam(s), %d bolt(s)", FX.count(), #FX.bolts)
    return FX.count()
end

return FX
