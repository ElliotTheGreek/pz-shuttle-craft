--[[ Shuttlecraft -- the transporter as it is seen (BEAM.md).

    A beam is a column of sparkles over whoever is going or coming, on every
    screen that can see them. This file is the part both ends agree on: which
    moves are a transporter, and which frame is showing when. The server
    announces a departure (TREK_BeamServer) and relays an arrival; each client
    draws (TREK_BeamFX).

    **Two sequences, seven frames.** Frames 0-3 are the shimmer, drawn by
    Gemini one from the next so it really moves; 4-6 are the fade. Leaving,
    the column builds up (the fade played backwards), shimmers over the
    character until they are seen to go, then fades where they stood.
    Arriving, it is there at full strength the moment they are, shimmers over
    them, and fades off them.

    **The character is not faded under it.** The engine's line-of-sight pass
    sets every visible character's alpha each frame (IsoPlayer.updateLOS, bci
    276-426; IsoPlayer.render, bci 141/166 on a client), so an alpha set from
    Lua is overwritten before it is drawn, in every process. The column covers
    them at its peak instead, and when they go they are simply gone from
    under it.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config

local B = {}
TREK.Beam = B

B.FRAMES = 7
B.SHIMMER = { 0, 1, 2, 3 }
B.FADE = { 4, 5, 6 }
B.BUILD = { 6, 5, 4 }

--- True when a move of this kind is a transporter beam.
function B.isBeam(kind)
    return kind ~= nil and C.BeamFxKinds[kind] == true
end

-- Written out whole, not assembled: tests/test_assets.py reads media/ui
-- names out of the Lua, and a missing frame then fails there instead of
-- drawing nothing in the game (DEV_GUIDE, *An id assembled from parts*).
B.TEXTURES = {
    [0] = "media/ui/TREK_Beam_00.png", "media/ui/TREK_Beam_01.png",
    "media/ui/TREK_Beam_02.png", "media/ui/TREK_Beam_03.png",
    "media/ui/TREK_Beam_04.png", "media/ui/TREK_Beam_05.png",
    "media/ui/TREK_Beam_06.png",
}

--- The texture path of frame n.
function B.texture(n)
    return B.TEXTURES[n]
end

local function shimmer(ms)
    local F = C.BeamFx
    return B.SHIMMER[math.floor(ms / F.shimmerMs) % #B.SHIMMER + 1]
end

--- Which frame is showing `ms` into an effect, and how strongly, or nil when
--- it has finished. `phase` is "out" or "in"; `departedMs` is when a leaving
--- character was seen to go, measured from the same start, or nil.
function B.frameAt(phase, ms, departedMs)
    local F = C.BeamFx
    if ms < 0 then return nil end
    local fadeFrom
    if phase == "out" then
        local built = F.buildMs * #B.BUILD
        if ms < built then
            return B.BUILD[math.floor(ms / F.buildMs) + 1], F.alpha
        end
        fadeFrom = math.min(departedMs or F.outMaxMs, F.outMaxMs)
        -- Built and then shimmered once at least, however soon they were
        -- seen to go: straight from the build into the fade is a flash, not
        -- a transporter.
        local least = built + F.shimmerMs * #B.SHIMMER
        if fadeFrom < least then fadeFrom = least end
    elseif phase == "in" then
        fadeFrom = F.inHoldMs
    else
        return nil
    end
    if ms < fadeFrom then
        -- From the end of the build, so the shimmer always opens on frame 0.
        local from = phase == "out" and F.buildMs * #B.BUILD or 0
        return shimmer(ms - from), F.alpha
    end
    local k = math.floor((ms - fadeFrom) / F.fadeMs) + 1
    if k > #B.FADE then return nil end
    return B.FADE[k], F.alpha
end

--- How long an effect can possibly last, for dropping one that never ends.
function B.longestMs()
    local F = C.BeamFx
    return math.max(F.outMaxMs, F.inHoldMs) + F.fadeMs * #B.FADE + 100
end

--- The arguments a beam is announced with.
function B.args(player, phase, x, y, z)
    local id = -1
    if player then
        id = TREK.Util.try("beam.onlineId", function() return player:getOnlineID() end) or -1
    end
    return { id = id, phase = phase, x = x, y = y, z = z }
end

--- The key an effect is kept under: one per character and direction.
function B.key(id, phase)
    return tostring(id) .. ":" .. tostring(phase)
end

return B
