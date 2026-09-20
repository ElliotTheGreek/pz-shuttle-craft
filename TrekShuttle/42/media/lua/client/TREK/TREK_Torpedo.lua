--[[ Shuttlecraft -- photon torpedoes: aiming them.

    This file does no damage. It picks a square and asks; the blast itself
    happens on the server and only on the server, because
    IsoTrap.shouldProcess makes a client damage only the zombies it owns while
    the server damages every one -- so if both fired, a client-owned zombie
    would be hit twice. MULTIPLAYER.md, "Photon torpedoes", has the bytecode.

    So everything here is presentation: a reticle, a square under it, and one
    command. If this file were deleted the torpedoes would still be safe;
    they would merely be unaimable.

    **Aiming is in screen space, deliberately.** The obvious thing is to draw
    the reticle on the target square in the world, which means world -> screen
    maths, which means getting the isometric projection and the zoom right in
    a file nobody can run outside the game. Instead the reticle is drawn at a
    screen point and the *square* is derived from it with screenToIsoX/Y --
    vanilla's own conversion, a GlobalObject static used by foraging, mining
    and every building cursor. The hard direction is the engine's problem, and
    it is the direction the engine already solves.

    That choice also leaves the controller within reach: a mouse gives the
    screen point directly and a stick would move a virtual one, from there the
    same code path. **The stick half is not built yet.** aimPoint() keeps a
    virtual cursor for a joypad but nothing moves it, so on a Steam Deck the
    reticle sits in the middle of the screen and does not track. That is
    recorded in ROADMAP rather than papered over, because the last thing this
    feature did was ship an input nobody could reach.

    **The interaction is: hold right mouse to aim, left click to fire**, while
    at the controls and in the air. No mode, no arming step, nothing to
    discover. The first version made it a radial-menu toggle and it failed in
    game in the quietest way available -- no error, no log line, the file
    loaded, and the pilot held right-click, clicked left and got silence. The
    lesson is in the roadmap's own wording, which said "right-click to aim,
    left-click to fire" all along.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net

local T = {}
TREK.Torpedo = T

-- Named here rather than built from a variable so tests/test_assets.py, which
-- scans the Lua for "media/ui/*.png" literals, can see it and fail if it is
-- not on disk. A reticle that silently resolves to nil draws nothing, and
-- "the torpedoes do not work" is what that looks like from the cockpit.
local RETICLE = "media/ui/TREK_Reticle.png"

-- Aiming is **holding the right mouse button**, which is how it was asked for
-- and how it reads from the cockpit: the same gesture that aims a gun on foot.
-- There is no arm/disarm mode.
--
-- The first version made arming a radial-menu toggle, and it failed in game in
-- the most instructive way available: nothing errored, nothing logged, the
-- file loaded fine, and the pilot held right-click, clicked left, and got
-- silence -- because the code was waiting to be switched on by a menu nobody
-- had been told to open. Worth remembering that "no error in the log" and "it
-- works" are different claims, and that an input nobody can discover is the
-- same as no input at all.
--
-- None of this is ship state: two crew may be aiming at once and neither is
-- the ship's business.
T.aimX, T.aimY = nil, nil          -- screen point
T.lastFire = 0                     -- client-side, for the reticle only

local overlay = nil
local leftWasDown = false          -- for the click edge; see T.poll

---------------------------------------------------------------------------
-- Where the pilot is pointing
---------------------------------------------------------------------------
local function player()
    return U.try("torpedoPlayer", function() return getSpecificPlayer(0) end)
end

--- The screen point being aimed at, whichever device is driving.
local function aimPoint(p)
    -- A joypad has no pointer, so it drives a virtual one that persists
    -- between frames; the mouse simply overwrites it.
    local num = U.try("torpedoPlayerNum", function() return p:getPlayerNum() end) or 0
    local pad = U.try("torpedoJoypad", function()
        return JoypadState.players and JoypadState.players[num + 1] or nil
    end)
    if pad then
        if not T.aimX then
            T.aimX = U.try("screenW", function() return getCore():getScreenWidth() end) or 800
            T.aimY = U.try("screenH", function() return getCore():getScreenHeight() end) or 600
            T.aimX, T.aimY = T.aimX / 2, T.aimY / 2
        end
        return T.aimX, T.aimY
    end
    local mx = U.try("mouseX", function() return getMouseX() end)
    local my = U.try("mouseY", function() return getMouseY() end)
    if mx then T.aimX, T.aimY = mx, my end
    return T.aimX, T.aimY
end

--- The world square under a screen point, at the ground beneath the ship.
--- `z` is the *ground*, never the flight level: a torpedo falls, and the blast
--- is centred where it lands. Confusing the two is the mistake `s.z` versus
--- `s.level` exists to prevent (PILOTING.md).
function T.targetSquare()
    local p = player()
    if not p then return nil end
    local sx, sy = aimPoint(p)
    if not sx then return nil end
    local s = TREK.Ship.get()
    local z = s.z or 0
    local num = U.try("torpedoPlayerNum", function() return p:getPlayerNum() end) or 0
    local wx = U.try("screenToIsoX", function()
        return screenToIsoX(num, sx, sy, z)
    end)
    local wy = U.try("screenToIsoY", function()
        return screenToIsoY(num, sx, sy, z)
    end)
    if not wx or not wy then return nil end
    return math.floor(wx), math.floor(wy), z
end

--- How the reticle should read: in range and loaded, or refusing and why.
--- Worked out here rather than only server-side so the pilot is told *before*
--- pulling the trigger, not by a denial afterwards.
function T.aimStatus()
    local s = TREK.Ship.get()
    if not s.flying then return "notFlying" end
    local x, y = T.targetSquare()
    if not x then return "noTarget" end
    local dx, dy = x - (s.x or 0), y - (s.y or 0)
    local dist = math.sqrt(dx * dx + dy * dy)
    if dist > C.TorpedoMaxRange then return "far" end
    if dist < C.TorpedoMinRange then return "close" end
    if getTimestampMs() - T.lastFire < C.TorpedoCooldownMs then return "reloading" end
    return "ok"
end

---------------------------------------------------------------------------
-- The reticle
---------------------------------------------------------------------------
local Overlay = ISUIElement:derive("TREKTorpedoOverlay")

function Overlay:new()
    local o = ISUIElement.new(self, 0, 0,
        U.try("screenW", function() return getCore():getScreenWidth() end) or 800,
        U.try("screenH", function() return getCore():getScreenHeight() end) or 600)
    o.backgroundColor = { r = 0, g = 0, b = 0, a = 0 }
    return o
end

-- Deliberately never captures the mouse. An overlay that did would swallow
-- every click meant for the game underneath it, and the pilot would be unable
-- to steer while armed.
function Overlay:onMouseDown() return false end
function Overlay:isMouseOver() return false end

local COLOURS = {
    ok        = { 0.45, 1.00, 0.55 },   -- LCARS green: she will fire
    reloading = { 1.00, 0.80, 0.40 },   -- gold: tubes not ready
    far       = { 1.00, 0.35, 0.35 },
    close     = { 1.00, 0.35, 0.35 },
    noTarget  = { 0.60, 0.60, 0.60 },
    notFlying = { 0.60, 0.60, 0.60 },
}

function Overlay:render()
    if not T.aiming() then return end
    local p = player()
    if not p then return end
    local sx, sy = aimPoint(p)
    if not sx then return end
    local status = T.aimStatus()
    local c = COLOURS[status] or COLOURS.noTarget
    U.try("torpedoReticle", function()
        local tex = getTexture(RETICLE)
        if not tex then return end
        local w, h = tex:getWidth(), tex:getHeight()
        self:drawTextureScaled(tex, sx - w / 2, sy - h / 2, w, h,
                               1.0, c[1], c[2], c[3])
    end)
end

local function ensureOverlay()
    if overlay then return overlay end
    overlay = Overlay:new()
    overlay:initialise()
    overlay:setAlwaysOnTop(true)
    overlay:addToUIManager()
    return overlay
end

---------------------------------------------------------------------------
-- Arming and firing
---------------------------------------------------------------------------
--- True when this player is the one flying her, in the seat, in the air.
--- Everything below is gated on it so a passenger's mouse does nothing and a
--- parked shuttle cannot shell its own landing pad.
function T.atTheControls()
    local p = player()
    if not p then return false end
    local s = TREK.Ship.get()
    if not s.flying then return false end
    local F = TREK.Flight
    if F and F.isPilot and not F.isPilot(p) then return false end
    return true
end

--- Aiming is the right mouse button held down. Nothing to arm, nothing to
--- remember, and it stops the moment the button comes up.
function T.aiming()
    if not T.atTheControls() then return false end
    return U.try("torpedoRightDown", function()
        return isMouseButtonDown(1)
    end) == true
end

local function closeOverlay()
    if overlay then
        U.try("torpedoOverlayOff", function() overlay:removeFromUIManager() end)
        overlay = nil
    end
end

--- Polled once a tick rather than hung off a mouse event.
---
--- The fire is taken on the **edge** -- the frame the left button goes down --
--- worked out here rather than trusting isMouseButtonPressed, whose
--- level-versus-edge meaning is not written down anywhere and would show up as
--- a torpedo every frame if it were wrong. The cooldown would bound the damage
--- but not the noise, and a wrong guess about an undocumented call is exactly
--- what DEV_GUIDE warns about.
function T.poll()
    if not T.atTheControls() then
        closeOverlay()
        leftWasDown = false
        return
    end
    ensureOverlay()

    local aiming = T.aiming()
    local leftDown = U.try("torpedoLeftDown", function()
        return isMouseButtonDown(0)
    end) == true

    if aiming and leftDown and not leftWasDown then T.fire() end
    leftWasDown = leftDown
end

--- Asks the server to fire. Everything checked here is checked again there --
--- a client is a request, never a fact -- and this half exists only so the
--- pilot gets an answer in the same frame they pulled the trigger.
function T.fire()
    if not T.atTheControls() then return end
    local status = T.aimStatus()
    if status ~= "ok" then
        U.log("torpedo not fired: %s", status)
        return
    end
    local x, y, z = T.targetSquare()
    if not x then return end
    local p = player()
    if not p then return end
    T.lastFire = getTimestampMs()
    Net.send(p, "fireTorpedo", { x = x, y = y, z = z })
    U.log("torpedo requested at %d,%d,%d", x, y, z)
end

Events.OnTick.Add(T.poll)

Net.onClient("torpedoFired", function(args)
    -- Fired by anybody, including another pilot on a server: keep the local
    -- cooldown honest so a second crewman's reticle does not read "ready"
    -- while the tubes are still cycling.
    T.lastFire = getTimestampMs()
    U.log("torpedo detonation at %s,%s", tostring(args.x), tostring(args.y))
end)

return T
