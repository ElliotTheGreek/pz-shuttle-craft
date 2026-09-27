--[[ Shuttlecraft -- the Ktarian game's timed action (CONTRABAND.md).

    One round of the Game: put the headset on, watch the disc, win. What it
    does to you is decided in complete(), which never runs on a client
    (TREK_PaddActions.lua has the bytecode) -- so the lift, the habit and the
    record are all the server's, in TREK_ContrabandServer.play.

    **Shared, and a global, for the PADD's reason**: in build 42 the server
    rebuilds a client's action by its global class name and reads its
    arguments off the action by the parameter names of `new`. `game` is
    stored as `game`.
]]

require "TimedActions/ISBaseTimedAction"
require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

TREKPlayGame = ISBaseTimedAction:derive("TREKPlayGame")

function TREKPlayGame:new(character, game)
    local o = ISBaseTimedAction.new(self, character)
    o.character = character
    o.game = game
    o.stopOnWalk = true
    o.stopOnRun = true
    o.forceProgressBar = true
    o.maxTime = U.try("game.instant", function() return character:isTimedActionInstant() end)
                and 1 or C.GamePlayTicks
    return o
end

--- The headset is in the player's own pockets -- not a bag, not the floor.
--- The menu moves it there first, as vanilla does before reading a book.
function TREKPlayGame:isValid()
    if not self.game or not self.character then return false end
    local fullType = U.try("game.type", function() return self.game:getFullType() end)
    if fullType ~= C.Contraband.game.item then return false end
    return U.try("game.held", function()
        return self.character:getInventory():contains(self.game)
    end) == true
end

function TREKPlayGame:start()
    if not isServer() then
        U.try("game.chime", function()
            self.character:playSoundLocal("TREK_TricorderChirp")
        end)
    end
end

function TREKPlayGame:stop()
    ISBaseTimedAction.stop(self)
end

function TREKPlayGame:perform()
    ISBaseTimedAction.perform(self)
end

function TREKPlayGame:complete()
    if TREK.ContrabandServer then
        TREK.ContrabandServer.play(self.character)
    end
    return true
end

function TREKPlayGame:getDuration()
    return self.maxTime
end
