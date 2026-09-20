--[[ Shuttlecraft -- photon torpedoes: aiming them, and watching them go.

    This file does no damage. It picks a square and asks; the blast itself
    happens on the server and only on the server, because
    IsoTrap.shouldProcess makes a client damage only the zombies it owns while
    the server damages every one -- so if both fired, a client-owned zombie
    would be hit twice. MULTIPLAYER.md, "Photon torpedoes", has the bytecode.

    So everything here is presentation: a reticle, a square under it, one
    command, and the torpedo crossing the ground. If this file were deleted the
    torpedoes would still be safe; they would merely be unaimable and unseen.

    **The projectile is drawn in screen space and touches nothing.** The
    obvious build -- and the one PHOTON_TORPEDOS.md originally proposed -- is
    an IsoObject placed on each square along the path. That was wrong twice
    over. There is no explosion, flame or smoke tile anywhere in build 42's
    tileset to put on it (fire is an attached animation, not a sprite), so
    there was nothing to draw; and a client laying and lifting world objects
    every tick is the sky plane's entire catalogue of trouble -- squares that
    will not answer yet, shadows outliving the thing that cast them, debris
    stranded in the air when a flight ends badly.

    Instead the torpedo is a texture placed with isoToScreenX/Y, the same
    GlobalObject statics the foraging icons, the fishing tension UI and
    ISButtonPrompt use to pin a drawing to a world position. It cannot leave
    anything behind, because it never puts anything anywhere. The one thing
    that does reach the world is a light riding along with it, and that is the
    documented scenery exception the cabin's lamps already use.

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

-- The torpedo itself, in the air. tools/gen_torpedo_flight.py.
local FLIGHT = "media/ui/TREK_TorpedoFlight.png"

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
-- Torpedoes in the air
---------------------------------------------------------------------------
-- **Every client draws the flight for itself, and none of them owns it.** The
-- server sends one `torpedoLaunched` carrying where she fired from, where it
-- is going and how long it has to get there; from that each client can place
-- the thing on its own screen every frame without a single further packet.
-- The same reasoning as the sky plane: derived from synced values, so they
-- agree without being told.
--
-- This is scenery. It does no damage, it is not ship state, and -- unlike the
-- sky plane -- it does not touch the world at all, so there is nothing here
-- that can be left behind. That is the whole reason it is drawn in screen
-- space instead of walked along the ground as IsoObjects: a projectile made
-- of world objects is a projectile that can strand its own debris in the air
-- when a flight ends badly, which is a bug this mod has already paid for once.
--
-- { x0, y0, level, x, y, z, start, ms, light }
T.inFlight = {}

--- Adds one. Returns it, so the tests can read it back.
function T.launch(a)
    local t = {
        x0 = a.x0, y0 = a.y0, level = a.level or C.FlightMinLevel,
        x = a.x, y = a.y, z = a.z or 0,
        start = getTimestampMs(),
        ms = a.ms or C.TorpedoMinFlightMs,
        light = nil,
        lightAt = nil,
    }
    table.insert(T.inFlight, t)
    return t
end

--- How far along it is, 0 at the tube and 1 at the target.
local function progress(t, now)
    if t.ms <= 0 then return 1 end
    local p = (now - t.start) / t.ms
    if p < 0 then return 0 end
    if p > 1 then return 1 end
    return p
end

--- Where a torpedo is in the world at a given progress.
---
--- It holds its altitude and then drops, rather than sinking in a straight
--- line from the tube to the ground: `p ^ 2.2` on the descent only. A linear
--- fall reads as the thing sliding down a wire, and the ship is usually only
--- one or two levels up, so the whole descent would otherwise be spent in the
--- first few tiles where it is least visible.
local function positionAt(t, p)
    local wx = t.x0 + (t.x - t.x0) * p
    local wy = t.y0 + (t.y - t.y0) * p
    local wz = t.level + (t.z - t.level) * (p ^ 2.2)
    return wx, wy, wz
end

--- Moves the light that rides with it, at most once per tile.
---
--- Lights are world objects, and adding and removing one every frame for a
--- thing that exists for under a second is a great deal of engine churn for
--- no visible gain -- the torpedo crosses a tile in about two frames. So the
--- light is rebuilt only when the tile under it changes.
---
--- U.batch rather than U.try: this repeats, and a call that does not exist
--- throws out of Java and dumps a stack trace *per call*. In a per-tick loop
--- that is the 2932-traces-in-one-session failure from DEV_GUIDE.
local function serviceLight(t, p, move)
    local wx, wy, wz = positionAt(t, p)
    local tx, ty = math.floor(wx), math.floor(wy)
    local key = tx .. ":" .. ty .. ":" .. math.floor(wz)
    if t.lightAt == key then return end

    local L = C.TorpedoLight
    move(function()
        local cell = getCell()
        if not cell then return true end
        if t.light then cell:removeLamppost(t.light) end
        t.light = cell:addLamppost(tx, ty, math.floor(wz),
                                   L.r, L.g, L.b, L.radius)
        return true
    end)
    t.lightAt = key
end

--- Puts a torpedo's light out. Called when it lands and when flight is torn
--- down, because a light is the one thing here that *can* outlive the shot.
local function douse(t)
    if not t.light then return end
    U.try("torpedoDouse", function()
        local cell = getCell()
        if cell then cell:removeLamppost(t.light) end
    end)
    t.light = nil
    t.lightAt = nil
end

--- Drops any torpedo that has arrived, and moves the lights of those that
--- have not. The detonation itself is the server's and arrives separately;
--- this only stops drawing the thing.
---
--- A torpedo is dropped on its own timer rather than waiting for the server's
--- `torpedoDetonated`, so a lost or late packet leaves a scorch mark and not a
--- glowing dot parked over the target for the rest of the session.
function T.serviceFlight()
    if #T.inFlight == 0 then return end
    local now = getTimestampMs()
    local move = U.batch("torpedo.light")
    for i = #T.inFlight, 1, -1 do
        local t = T.inFlight[i]
        local p = progress(t, now)
        if p >= 1 then
            douse(t)
            table.remove(T.inFlight, i)
        else
            serviceLight(t, p, move)
        end
    end
end

--- Takes every torpedo out of the air at once, lights and all.
function T.clearFlight()
    for i = #T.inFlight, 1, -1 do
        douse(T.inFlight[i])
        table.remove(T.inFlight, i)
    end
end

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

-- The torpedo's own colour: a hot blue-white, tinted at draw time rather than
-- baked into the sprite for the same reason the reticle is white.
local FLIGHT_TINT = { 0.70, 0.88, 1.00 }

--- Draws every torpedo in the air, head and trail.
---
--- **This is the whole projectile.** It places a texture with isoToScreenX/Y
--- -- GlobalObject statics with ten non-debug vanilla call sites, among them
--- the foraging icons and ISButtonPrompt -- and that is the only reason the
--- feature needs no world objects, no tile pack and no cleanup path.
---
--- Sizes divide by the zoom because that is what vanilla does with anything
--- pinned to a world position (ISBaseIcon:updateZoom); without it the torpedo
--- is the same size on screen however far out the camera is, and stops
--- belonging to the world it is crossing.
function Overlay:renderFlight()
    if #T.inFlight == 0 then return end
    local p = player()
    if not p then return end
    local num = U.try("torpedoPlayerNum", function() return p:getPlayerNum() end) or 0
    local zoom = U.try("torpedoZoom", function()
        return getCore():getZoom(num)
    end) or 1
    if zoom <= 0 then zoom = 1 end

    local tex = U.try("torpedoTexture", function() return getTexture(FLIGHT) end)
    if not tex then return end
    local tw, th = tex:getWidth(), tex:getHeight()
    local now = getTimestampMs()

    for _, t in ipairs(T.inFlight) do
        local head = progress(t, now)
        -- The trail is drawn first and the head last, so the brightest thing
        -- is on top. Each echo is an earlier moment of the same flight, which
        -- costs nothing to work out and always lies exactly on the path.
        for e = C.TorpedoTrail, 0, -1 do
            local at = head - (e * C.TorpedoTrailMs) / math.max(t.ms, 1)
            if at >= 0 then
                local wx, wy, wz = positionAt(t, at)
                U.try("torpedoDraw", function()
                    local sx = isoToScreenX(num, wx, wy, wz)
                    local sy = isoToScreenY(num, wx, wy, wz)
                    if not sx or not sy then return end
                    -- The head is full size and opaque; each echo behind it is
                    -- smaller and fainter, so the trail tapers to nothing
                    -- instead of ending in a hard dot.
                    local f = 1 - (e / (C.TorpedoTrail + 1))
                    local a = f * f
                    local w, h = (tw * f) / zoom, (th * f) / zoom
                    self:drawTextureScaled(tex, sx - w / 2, sy - h / 2, w, h,
                                           a, FLIGHT_TINT[1], FLIGHT_TINT[2],
                                           FLIGHT_TINT[3])
                end)
            end
        end
    end
end

function Overlay:render()
    -- The flight is drawn for everyone who can see it -- a passenger, another
    -- pilot on a server, somebody standing on the ground being shot at -- and
    -- only the reticle belongs to the person aiming.
    self:renderFlight()
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
--- The overlay must also exist for somebody who is not flying her.
---
--- It used to be created and destroyed purely on `atTheControls`, which was
--- right while the only thing drawn on it was the pilot's own reticle. It is
--- wrong now the torpedo is drawn there too: a passenger, another pilot on a
--- server and whoever is being shot at all need the overlay to see the shot
--- cross the ground, and none of them is at the controls.
local function overlayWanted()
    return T.atTheControls() or #T.inFlight > 0
end

function T.poll()
    -- Torpedoes keep flying whoever is watching, so this comes before the
    -- controls check rather than after it.
    U.try("torpedoFlight", T.serviceFlight)

    if not overlayWanted() then
        closeOverlay()
        leftWasDown = false
        return
    end
    ensureOverlay()

    if not T.atTheControls() then
        leftWasDown = false
        return
    end

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

Net.onClient("torpedoLaunched", function(args)
    -- Fired by anybody, including another pilot on a server: keep the local
    -- cooldown honest so a second crewman's reticle does not read "ready"
    -- while the tubes are still cycling.
    T.lastFire = getTimestampMs()
    if not args.x or not args.y then return end
    T.launch({
        x0 = args.x0 or args.x, y0 = args.y0 or args.y,
        level = args.level,
        x = args.x, y = args.y, z = args.z,
        ms = args.ms,
    })
    U.log("torpedo in the air: %s,%s -> %s,%s, %s ms",
          tostring(args.x0), tostring(args.y0),
          tostring(args.x), tostring(args.y), tostring(args.ms))
end)

Net.onClient("torpedoDetonated", function(args)
    -- The blast is the server's and has already happened; there is nothing to
    -- draw here, because in this engine the explosion *is* the fire and the
    -- smoke and the engine syncs both by itself (IsoFireManager.StartFire
    -- sends its own packet to nearby clients).
    --
    -- What this does is put out any light still riding on that shot. The
    -- flight normally ends on its own timer a frame or two earlier, so this is
    -- the tidy-up for the case where it did not -- a late packet, a stalled
    -- client, a shot that outlived its own clock.
    T.clearFlight()
    U.log("torpedo detonation at %s,%s", tostring(args.x), tostring(args.y))
end)

return T
