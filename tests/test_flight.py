"""Flight: the pilot's body is out of the dead's reach, and comes down safely.

History, because it explains every check below. Zombies scratched a pilot
hovering still over them. The first fix switched on god mode, "zombies don't
attack" and invincibility -- which build 42 silently refuses for any
character whose role lacks the capability, i.e. every ordinary player. It
passed this test (the stub obeyed) and failed in game.

So the fix does not ask the engine for permission. Zombies attack only on
their own floor, and the body is held C.FlightHoverHeight floors up. This
test checks the mechanics that makes safe:

  * the pinned body sits at least one full floor above the ground, with margin
    for the engine's fall between two pins
  * no fall accumulates while hovering (a pending fall is applied on landing)
  * every way out of flight puts the body back on the ground first, visible
  * nothing in the mod calls a role-gated cheat setter again

    python tests/test_flight.py
"""
import os
import re
import sys
from lupa import LuaRuntime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUA = os.path.join(ROOT, "TrekShuttle", "42", "media", "lua").replace(os.sep, "/")

lua = LuaRuntime(unpack_returned_tuples=True)
lua.execute(f'package.path = "{LUA}/shared/?.lua;{LUA}/client/?.lua;" .. package.path')
lua.execute("""
    _G.unpack = _G.unpack or table.unpack
    _G.print = function(...) end
    _G.instanceof = function() return false end
    _G.getCellSizeInSquares = function() return 256 end
    local md = {}
    _G.ModData = { getOrCreate = function(k) md[k] = md[k] or {}; return md[k] end }
    _G.getPlayer = function() return nil end
    _G.getSpecificPlayer = function() return nil end
    _G.getCell = function() return nil end
    handlers = {}
    _G.Events = setmetatable({}, { __index = function(_, name)
        return { Add = function(fn) handlers[name] = fn end }
    end })
    ISUIElement = { derive = function(self, name)
        local c = {}; c.__index = c; return setmetatable(c, { __index = self })
    end }
    TREK = {}
    require "TREK/TREK_Config"
    require "TREK/TREK_Util"
    require "TREK/TREK_Flight"

    function makePlayer()
        local p = { x = 0, y = 0, z = 0, lastZ = 0, fallTime = 7, falling = true,
                    alpha = 1, targetAlpha = 1 }
        function p:setX(v) self.x = v end
        function p:setY(v) self.y = v end
        function p:setZ(v) self.z = v end
        function p:setLastX(v) end
        function p:setLastY(v) end
        function p:setLastZ(v) self.lastZ = v end
        function p:getX() return self.x end
        function p:getY() return self.y end
        function p:getZ() return self.z end
        function p:setbFalling(v) self.falling = v end
        function p:setFallTime(v) self.fallTime = v end
        function p:getAlpha() return self.alpha end
        function p:getTargetAlpha() return self.targetAlpha end
        function p:setAlpha(v) self.alpha = v end
        function p:setTargetAlpha(v) self.targetAlpha = v end
        return p
    end
""")

g = lua.globals()
F = g.TREK.Flight
C = g.TREK.Config
failures = []

# --- hover height ---------------------------------------------------------
H = float(C.FlightHoverHeight)
for ground in (0, 1, -1):
    flight = lua.eval("function(z) return { groundZ = z } end")(ground)
    z = float(F.hoverZ(flight))
    if int(z // 1) < ground + 1:
        failures.append(f"hover at ground {ground} is on floor {int(z // 1)}, "
                        f"which zombies on floor {ground} could still reach")
    # The engine starts a fall between pins; half a floor of it must not bring
    # the body down onto the zombies' floor.
    if int((z - 0.49) // 1) < ground + 1:
        failures.append(f"hover height {H} leaves no margin: a small fall between "
                        f"ticks puts the body back on floor {ground}")
print(f"hover height {H}: body stays at least one floor above the ground")

# --- the tick pins the body up there, with no fall building ----------------
lua.execute("""
    p = makePlayer()
    TREK.Flight.active = { player = p, x = 10, y = 20, groundZ = 0, ticks = 0,
                           suspended = true, heading = 0 }
""")
tick = g.handlers["OnTick"]
if not tick:
    failures.append("TREK_Flight registered no OnTick handler")
else:
    tick()
    p = g.p
    if abs(float(p.z) - H) > 1e-9:
        failures.append(f"a flight tick put the body at z {p.z}, not the hover height {H}")
    if float(p.fallTime) != 0 or p.falling:
        failures.append("a flight tick left a fall pending on the hovering body")
    print(f"flight tick: body pinned at z {float(p.z)}, no fall pending")

# --- landing puts the body down, visible ----------------------------------
lua.execute("""
    p2 = makePlayer()
    local flight = { player = p2, x = 10, y = 20, groundZ = 0, ticks = 5 }
    TREK.Flight.protect(p2, flight, true)
    p2.z = flight.groundZ + TREK.Config.FlightHoverHeight
    p2.fallTime = 9; p2.falling = true
    TREK.Flight.active = flight
    TREK.Flight.stop(false)
""")
p2 = g.p2
if float(p2.z) != 0:
    failures.append(f"stopping flight left the body at z {p2.z}, in mid-air")
if float(p2.fallTime) != 0 or p2.falling:
    failures.append("stopping flight left a fall pending -- it would land as fall damage")
if float(p2.alpha) != 1 or float(p2.targetAlpha) != 1:
    failures.append("stopping flight left the body invisible")
if F.active is not None:
    failures.append("stopping flight left it marked active")
print("stop: body on the ground, no fall pending, visible again")

# --- never again ------------------------------------------------------------
# Role-gated in build 42: public, callable, and silently refused for an
# ordinary player -- while working for a tester whose -debug session has the
# capability. Code that relies on them passes testing and fails for players.
GATED = ("setGodMod", "setGodModCheat", "setZombiesDontAttack", "setInvincible",
         "setNoClip", "setInvisible", "setGhostMode")
for dp, _, fns in os.walk(os.path.join(ROOT, "TrekShuttle", "42", "media", "lua")):
    for fn in fns:
        if not fn.endswith(".lua"):
            continue
        for n, line in enumerate(open(os.path.join(dp, fn), encoding="utf-8"), 1):
            code = line.split("--", 1)[0]
            for name in GATED:
                if re.search(r"[:.]" + name + r"\s*\(", code):
                    failures.append(f"{fn}:{n} calls {name}, which build 42 refuses "
                                    f"for ordinary players")

if failures:
    print(f"\n{len(failures)} PROBLEM(S):")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("\nthe hovering pilot is out of reach and lands safely")
