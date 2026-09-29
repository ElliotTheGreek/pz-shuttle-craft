--[[ Shuttlecraft -- the transporter as it is seen: the drawing (BEAM.md).

    Every beam is a column of sparkles over the character, on every screen.

      * **Leaving** is announced by the server (`beamFx`, phase "out") when it
        grants the move, with where the character stands. The column follows
        them until they are seen to go -- a jump of more than C.BeamFx.jump
        tiles, a change of storey, or gone from this machine -- and then fades
        where they stood.
      * **Arriving** is seen first by the client that moves: when a beam is
        granted it notes where its player stood (FX.watchFrom, from
        Core's moveGranted), and the first tick they are somewhere else is
        the arrival. It shows the column there at once and tells the server
        (`beamedIn`), which relays it to everybody else. One watcher covers
        every kind of beam -- the shuttle's pad, a beam down, the Adirondack,
        a raid -- without a hook in any of them.

    **Drawn in screen space on a 1x1 overlay**, the phaser's rule (DEV_GUIDE,
    *An overlay that covers the screen takes the world's mouse away*): the
    element sits in the corner and every draw is placed by isoToScreenX/Y.
]]

if isServer() then return end

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Net"
require "TREK/TREK_Beam"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Net = TREK.Net
local B = TREK.Beam

local FX = {}
TREK.BeamFX = FX

-- key -> { id, phase, x, y, z, startMs, departedMs, char, hadChar }
FX.effects = {}
-- The local player's beam, waiting to see them arrive.
FX.watch = nil

-- The core of the glow is this share of a frame's height (tools/gen_beam.py
-- CORE), and its foot this far down it.
local CORE = 0.84
local FOOT = 0.94
-- A relay of an effect this client already started for itself is dropped.
local DUPLICATE_MS = 1500

local overlay = nil
local ensureOverlay

local function now() return getTimestampMs() end

local function position(ch)
    if not ch then return nil end
    local x = U.try("beamFx.cx", function() return ch:getX() end)
    local y = U.try("beamFx.cy", function() return ch:getY() end)
    local z = U.try("beamFx.cz", function() return ch:getZ() end)
    if not x or not y then return nil end
    return x, y, z or 0
end

--- The live character an effect belongs to: one of this machine's own
--- players first, then anybody the engine knows by that online id.
local function character(id)
    for i = 0, 3 do
        local p = U.try("beamFx.local", function() return getSpecificPlayer(i) end)
        if p and U.try("beamFx.localId", function() return p:getOnlineID() end) == id then
            return p
        end
    end
    if id and id >= 0 then
        return U.try("beamFx.byId", function() return getPlayerByOnlineID(id) end)
    end
    return nil
end

--- Starts an effect, or keeps the one already running for this character
--- and direction if it has only just started (the server relaying back an
--- arrival this client already showed).
function FX.start(args)
    if not args or not args.phase or not args.x or not args.y then return nil end
    local key = B.key(args.id, args.phase)
    local t = now()
    local e = FX.effects[key]
    if e and t - e.startMs < DUPLICATE_MS then return e end
    e = { id = args.id, phase = args.phase, x = args.x, y = args.y, z = args.z or 0,
          startMs = t }
    FX.effects[key] = e
    ensureOverlay()
    return e
end

Net.onClient("beamFx", function(args) FX.start(args) end)

--- How many columns are showing here. For the tests and the console.
function FX.count()
    local n = 0
    for _ in pairs(FX.effects) do n = n + 1 end
    return n
end

---------------------------------------------------------------------------
-- Following, and seeing them go
---------------------------------------------------------------------------
local function jumped(x0, y0, z0, x, y, z)
    local dx, dy = x - x0, y - y0
    return dx * dx + dy * dy > C.BeamFx.jump * C.BeamFx.jump
        or math.abs((z or 0) - (z0 or 0)) >= 1
end

--- Moves an effect with its character, and marks a leaving one departed the
--- moment they are gone.
local function follow(e, t)
    if e.phase == "out" and e.departedMs then return end
    e.char = e.char or character(e.id)
    local x, y, z = position(e.char)
    if not x then
        -- A character this machine had and has lost has gone: out of range,
        -- or across the map.
        if e.phase == "out" and e.hadChar then e.departedMs = t - e.startMs end
        return
    end
    e.hadChar = true
    if e.phase == "out" and jumped(e.x, e.y, e.z, x, y, z) then
        e.departedMs = t - e.startMs
        return
    end
    e.x, e.y, e.z = x, y, z
end

---------------------------------------------------------------------------
-- The local player's own arrival
---------------------------------------------------------------------------
--- A beam was granted: note where the player stands, to see them arrive.
function FX.watchFrom(player)
    local x, y, z = position(player)
    if not x then return end
    FX.watch = { player = player, x = x, y = y, z = z, since = now() }
end

local function serviceWatch(t)
    local w = FX.watch
    if not w then return end
    if t - w.since > C.BeamFx.arrivalWindowMs then FX.watch = nil return end
    local x, y, z = position(w.player)
    if not x or not jumped(w.x, w.y, w.z, x, y, z) then return end
    FX.watch = nil
    local args = B.args(w.player, "in", x, y, z)
    FX.start(args)
    U.try("beamFx.report", function()
        TREK.Net.send(w.player, "beamedIn", { x = x, y = y, z = z })
    end)
end

--- Drops what has finished, follows what is running, watches for arrivals.
function FX.service()
    local t = now()
    serviceWatch(t)
    for key, e in pairs(FX.effects) do
        follow(e, t)
        local ms = t - e.startMs
        if ms > B.longestMs() or not B.frameAt(e.phase, ms, e.departedMs) then
            FX.effects[key] = nil
        end
    end
end

Events.OnTick.Add(FX.service)

---------------------------------------------------------------------------
-- Drawing
---------------------------------------------------------------------------
local Overlay = ISUIElement:derive("TREKBeamOverlay")

--- One pixel, in the corner: see the header, and the phaser's overlay.
function Overlay:new()
    local o = ISUIElement.new(self, 0, 0, 1, 1)
    o.backgroundColor = { r = 0, g = 0, b = 0, a = 0 }
    return o
end

function Overlay:onMouseDown() return false end
function Overlay:onRightMouseDown() return false end

--- Where a column stands on screen: its left, top, width and height, with
--- the foot of the glow at the character's feet and the core C.BeamFx.height
--- storeys tall.
function FX.placement(num, x, y, z)
    local fx = isoToScreenX(num, x, y, z)
    local fy = isoToScreenY(num, x, y, z)
    local uy = isoToScreenY(num, x, y, z + 1)
    if not fx or not fy or not uy then return nil end
    local storey = fy - uy
    if storey <= 0 then return nil end
    local h = storey * C.BeamFx.height / CORE
    local w = h / 2
    return fx - w / 2, fy - h * FOOT, w, h
end

function Overlay:render()
    local p = U.player(0)
    if not p then return end
    local num = U.try("beamFx.num", function() return p:getPlayerNum() end) or 0
    local t = now()
    for _, e in pairs(FX.effects) do
        local frame, alpha = B.frameAt(e.phase, t - e.startMs, e.departedMs)
        local tex = frame and getTexture(B.texture(frame))
        if tex then
            local x, y, w, h = FX.placement(num, e.x, e.y, e.z)
            if x then
                U.try("beamFx.draw", function()
                    self:drawTextureScaled(tex, x, y, w, h, alpha, 1, 1, 1)
                end)
            end
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

--- Exposed for the debug console: TREK_BeamFX() reports what is showing.
function TREK_BeamFX()
    U.log("beam fx: %d column(s), watching an arrival: %s", FX.count(),
          tostring(FX.watch ~= nil))
    return FX.count()
end

return FX
