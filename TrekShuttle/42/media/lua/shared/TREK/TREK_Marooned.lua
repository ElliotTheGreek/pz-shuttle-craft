--[[ Shuttlecraft -- marooned (MAROONED.md): what both ends ask.

    The third way a world can begin (sandbox `TrekShuttle.StartState`). It is
    the cold start (ENERGY.md 10) with the ship lost:

      * she is down and dark at one of C.Maroon.sites, drawn at random, never
        the one beside the first player;
      * nobody has a combadge. There is no Shuttlecraft menu on the ground and
        no beam until a player has been aboard her once, in her cabin or in
        one of her seats. The hull keeps its one option, *Board the shuttle*:
        that is her door, not a combadge;
      * annotated maps that mark the site turn up where vanilla's maps do.

    The record is ship state, so every client has it: `s.marooned`, the site's
    id in `s.maroonSite`, and `s.badged`, a set of usernames. A username and
    not a character: somebody who dies does not lose the ship a second time.
    The set is bounded by the players a world has ever had and changes once
    each, so it may ride the ship's table (DEV_GUIDE, *State that is
    transmitted whole cannot hold a list that grows*).

    Shared because the menu and the server have to give the same answer; the
    server's half is TREK_MaroonedServer, the player's TREK_MaroonedUI.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Ship"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util
local Ship = TREK.Ship

local MR = {}
TREK.Marooned = MR

--- True in a world that began marooned, for the life of the save.
function MR.active()
    return Ship.get().marooned == true
end

--- True when the ship knows this player's pattern, and so will answer them
--- from anywhere: the menu on the ground, a beam up, calling her down.
---
--- **The rule of every world that begins dark**, marooned or a cold start
--- (the author, 2026-10-07): a beam takes power and a pattern the ship has
--- learned, and she learns it the first time that player is aboard. So the
--- hatch is everybody's first move, and on a server whoever finds her first
--- can send her up and keep her from the rest until they set her down.
---
--- `s.badged` existing is the switch. CS.init makes it for a new cold or
--- marooned ship and for nothing else: a world that began commissioned has
--- her overhead, where nobody could ever walk aboard, and a save from before
--- this rule has no record of who has been, so both answer true for
--- everybody, as they always did.
function MR.linked(player)
    local s = Ship.get()
    if type(s.badged) ~= "table" then return true end
    if not player then return false end
    return s.badged[Ship.usernameOf(player)] == true
end

--- True once anybody at all has been aboard her.
function MR.found()
    local s = Ship.get()
    return s.marooned ~= true or s.maroonFound == true
end

function MR.siteById(id)
    for _, site in ipairs(C.Maroon.sites) do
        if site.id == id then return site end
    end
    return nil
end

--- The site this world drew, or nil before the first player has stood in it.
function MR.site()
    return MR.siteById(Ship.get().maroonSite)
end

function MR.isMap(item)
    if not item then return false end
    return U.try("maroon.isMap", function()
        return item:getFullType() == C.Maroon.mapItem
    end) == true
end

return MR
