"""Runs the real mod code as single player, and as a server with two clients.

The mod's multiplayer design (MULTIPLAYER.md) is a set of rules: the server
owns the ship, a client only asks, a client moves only its own character, the
world reaches clients only through the engine's transmit calls. Breaking one
does not fail loudly in the game -- it works for the host and silently not for
anyone else, which on this PC cannot even be seen without a second machine.

This loads every Lua file of the mod into separate Lua runtimes, each with
tests/pz_sim.lua standing in for the engine, and connects them through a fake
network that carries only plain data. Then it plays the mod:

  single player  beam up, the cabin is built and stocked with water in the
                 sink, helm course/bookmark/shields, take her down, the hatch
                 in and out, call down elsewhere (the old hull becomes a ghost
                 and is cleared when its ground loads), recall, a landing with
                 no room beams the player home, a schema 1 save migrates
  multiplayer    a server and two clients: the first to use the ship owns it
                 under owner-and-crew access, a stranger is refused, the owner
                 adds them to the crew, both see the same cabin and stock,
                 transporter charges refuse the fourth beam and recharge,
                 every client's copy of the ship matches the server's, and no
                 client ever edits the world or the ship state itself
  static         every command a client sends has a server handler, every
                 reply has a client handler, file guards are in place, and
                 nothing calls a role-gated cheat setter

Every U.try failure the mod logs ("WARN (label)") fails the test: that is an
engine call that threw.

    python tests/test_multiplayer.py
"""
import os
import re
import sys
from collections import deque

from lupa import LuaRuntime, lua_type

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUA = os.path.join(ROOT, "TrekShuttle", "42", "media", "lua")
SIM = os.path.join(ROOT, "tests", "pz_sim.lua")

failures = []


def fail(msg):
    failures.append(msg)


def check(cond, msg):
    if not cond:
        fail(msg)
    return cond


# ---------------------------------------------------------------------------
# Crossing between runtimes: plain data only
# ---------------------------------------------------------------------------
def to_py(value, depth=0):
    if depth > 20:
        raise ValueError("table nested too deeply to send")
    t = lua_type(value)
    if t is None:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        raise ValueError(f"cannot send {value!r}")
    if t == "table":
        return {k: to_py(v, depth + 1) for k, v in value.items()}
    raise ValueError(f"cannot send a Lua {t} over the network")


def modules(folder):
    base = os.path.join(LUA, folder, "TREK")
    if not os.path.isdir(base):
        return []
    return sorted("TREK/" + f[:-4] for f in os.listdir(base) if f.endswith(".lua"))


class Runtime:
    def __init__(self, net, role, name):
        self.net, self.role, self.name = net, role, name
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        g = self.lua.globals()
        g.SIM_ROLE = role
        g.py_clock = lambda: net.clock
        g.py_replicate = lambda op, d: net.replicate(self, op, to_py(d))
        g.py_transmit = lambda k, d: net.queue.append(("transmit", self, k, to_py(d)))
        g.py_request = lambda k: net.queue.append(("request", self, k))
        g.py_client_command = lambda who, mod, cmd, args: net.queue.append(
            ("toServer", self, who, mod, cmd, to_py(args)))
        g.py_server_command = lambda who, mod, cmd, args: net.queue.append(
            ("toClient", self, who, mod, cmd, to_py(args)))
        path = "/".join(LUA.split(os.sep))
        self.lua.execute(f'package.path = "{path}/shared/?.lua;{path}/client/?.lua;'
                         f'{path}/server/?.lua;" .. package.path')
        self.lua.execute(open(SIM, encoding="utf-8").read())
        self.lua.execute(APPLY)

    def load(self):
        # The game loads shared, then client, then server, in every process.
        for folder in ("shared", "client", "server"):
            for m in modules(folder):
                self.lua.execute(f'require "{m}"')

    def run(self, code):
        return self.lua.execute(code)

    def eval(self, code):
        return self.lua.eval(code)

    def table(self, value):
        return self.lua.table_from(value, recursive=True) if isinstance(value, dict) else value

    def fire(self, event, *args):
        self.lua.globals().SIM.fire(event, *args)

    def warnings(self):
        log = self.lua.globals().SIM.log
        return [log[i] for i in range(1, len(log) + 1)
                if "WARN" in str(log[i]) or "SIM DEATH" in str(log[i])]

    def notes(self, who=None):
        n = self.lua.globals().SIM.notes
        out = [n[i] for i in range(1, len(n) + 1)]
        return [str(x.text) for x in out if who is None or x.player == who]


APPLY = r"""
    local function copy(t)
        if type(t) ~= "table" then return t end
        local o = {}
        for k, v in pairs(t) do o[k] = copy(v) end
        return o
    end
    local function find(list, sprite)
        for i, o in ipairs(list) do
            if o.spriteName == sprite then return o, i end
        end
    end
    function SIM.apply(op, d)
        local sq = SIM.rawSquare(d.x, d.y, d.z)
        if op == "object" then
            local o = SIM.object(d.sprite)
            o.modData = copy(d.modData or {})
            o.square = sq
            if d.hasContainer then
                o.container = SIM.container(40)
                o.container.parentObject = o
                for _, it in ipairs(d.items or {}) do
                    table.insert(o.container.items, instanceItem(it))
                end
            end
            if d.fluid then o.fluid = { capacity = d.fluid.capacity, amount = d.fluid.amount } end
            table.insert(sq.objects, o)
        elseif op == "floor" then
            local f = SIM.object(d.sprite)
            f.isFloor, f.square = true, sq
            table.insert(sq.objects, 1, f)
        elseif op == "remove" then
            local list = d.world and sq.worldObjects or sq.objects
            local _, i = find(list, d.sprite)
            if i then table.remove(list, i) end
        elseif op == "worldItem" then
            local w = SIM.object(d.type, "IsoWorldInventoryObject")
            w.item = instanceItem(d.type)
            w.square = sq
            table.insert(sq.worldObjects, w)
        elseif op == "containerItem" then
            local o = find(sq.objects, d.sprite)
            if o and o.container then table.insert(o.container.items, instanceItem(d.item)) end
        elseif op == "fluid" then
            local o = find(sq.objects, d.sprite)
            if o and o.fluid then o.fluid.amount = d.amount end
        elseif op == "vehicle" then
            SIM.vehicle(d.script, d.x + 0.5, d.y + 0.5, d.z, d.simId)
        elseif op == "vehicleRemove" then
            local v = SIM.findVehicle(d.simId)
            if v then v.removed = true end
        elseif op == "modData" then
            local o = find(sq.objects, d.sprite)
            if o then o.modData = copy(d.modData) end
        end
    end
"""


class Net:
    """Single player (one runtime) or a server with clients."""

    def __init__(self, mode, clients=()):
        self.mode = mode
        self.clock = 1_000_000
        self.queue = deque()
        if mode == "sp":
            self.server = Runtime(self, "sp", "sp")
            self.clients = {}
        else:
            self.server = Runtime(self, "server", "server")
            self.clients = {c: Runtime(self, "client", c) for c in clients}

    def all(self):
        return [self.server, *self.clients.values()]

    def replicate(self, source, op, data):
        for c in self.clients.values():
            c.lua.globals().SIM.apply(op, c.table(data))

    def deliver(self, msg):
        kind = msg[0]
        if kind == "toServer":
            _, src, who, mod, cmd, args = msg
            rt = self.server
            player = rt.eval(f'(function() for _, p in ipairs(SIM.players) do '
                             f'if p.name == "{who}" then return p end end end)()')
            if player is None:
                fail(f"server has no player {who} for command {cmd}")
                return
            rt.fire("OnClientCommand", mod, cmd, player, rt.table(args))
        elif kind == "toClient":
            _, src, who, mod, cmd, args = msg
            for name, c in self.clients.items():
                if who is None or who == name:
                    c.fire("OnServerCommand", mod, cmd, c.table(args))
        elif kind == "transmit":
            _, src, key, data = msg
            targets = [c for c in self.all() if c is not src]
            for rt in targets:
                rt.fire("OnReceiveGlobalModData", key, rt.table(data))
        elif kind == "request":
            _, src, key = msg
            data = to_py(self.server.eval(f'SIM.globalData["{key}"]') or self.server.lua.table())
            src.fire("OnReceiveGlobalModData", key, src.table(data))

    def pump(self, ticks=1):
        for _ in range(ticks):
            for _ in range(10000):
                if not self.queue:
                    break
                self.deliver(self.queue.popleft())
            self.clock += 16
            for rt in self.all():
                rt.run("SIM.stream(); SIM.gravity()")
                rt.fire("OnTick", 0)
                rt.run("for _, p in ipairs(SIM.players) do SIM.fire('OnPlayerUpdate', p) end")
            # Each client reports its own character's position to the server.
            for name, c in self.clients.items():
                x, y, z = c.eval("SIM.players[1].x"), c.eval("SIM.players[1].y"), c.eval("SIM.players[1].z")
                self.server.run(f'for _, p in ipairs(SIM.players) do if p.name == "{name}" then '
                                f'p.x, p.y, p.z = {x}, {y}, {z} end end')
        while self.queue:
            self.deliver(self.queue.popleft())

    def start(self):
        for rt in self.all():
            rt.load()
        for rt in self.all():
            rt.fire("OnInitGlobalModData", False)
        self.pump(2)


def died(rt, label):
    """True, and a failure, if a player here fell to their death."""
    dead = [str(x) for x in rt.warnings() if "SIM DEATH" in str(x)]
    for d in dead:
        fail(f"{label}: {d} -- the arrival hold did not hold")
    return bool(dead)


def pos(rt, who=1):
    return (float(rt.eval(f"SIM.players[{who}].x")), float(rt.eval(f"SIM.players[{who}].y")),
            float(rt.eval(f"SIM.players[{who}].z")))


def pad(rt):
    x, y, z = rt.eval("TREK.Util.padSpot()")
    return int(x), int(y), int(z)


def at_pad(rt, who=1):
    x, y, z = pos(rt, who)
    px, py, pz = pad(rt)
    return int(x) == px and int(y) == py and int(z) == pz


def cabin_objects(rt):
    """(containers, stocked containers, water fixtures with water) in the cabin."""
    return rt.eval("""(function()
        local C, U = TREK.Config, TREK.Util
        local containers, stocked, wet = 0, 0, 0
        for ox = 0, C.CabinW do for oy = 0, C.CabinL do
            local x, y = U.at(ox, oy)
            local sq = SIM.rawSquare(x, y, C.CabinZ)
            for _, o in ipairs(sq.objects) do
                if o.container then
                    containers = containers + 1
                    if #o.container.items > 0 then stocked = stocked + 1 end
                end
                if o.fluid and o.fluid.amount > 0 then wet = wet + 1 end
            end
        end end
        return containers, stocked, wet
    end)()""")


def hull_at(rt, x, y, z):
    """True when the ship stands here: its vehicle, or a hull from before it."""
    return rt.eval(f"""(function()
        for _, v in ipairs(SIM.vehicles) do
            if not v.removed and v.script == "Base.TrekShuttleCraft"
               and math.floor(v.x) == {x} and math.floor(v.y) == {y} then
                return true
            end
        end
        return TREK.World.hullOn(SIM.rawSquare({x}, {y}, {z})) ~= nil
    end)()""")


def shuttles(rt):
    """Shuttle vehicles that exist here, loaded or not."""
    return rt.eval("""(function()
        local n = 0
        for _, v in ipairs(SIM.vehicles) do
            if not v.removed and v.script == "Base.TrekShuttleCraft" then n = n + 1 end
        end
        return n
    end)()""")


def ship_vehicle(rt):
    """The simulated id of the vehicle the ship state points at, or None."""
    return rt.eval("""(function()
        local id = TREK.Util.state().vehicleId
        for _, v in ipairs(SIM.vehicles) do
            if not v.removed and v.modData.TREKShipId == id then return v.simId end
        end
    end)()""")


def ship(rt, field):
    return rt.eval(f"TREK.Util.state().{field}")


# ---------------------------------------------------------------------------
# Single player
# ---------------------------------------------------------------------------
def single_player():
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('solo', 1000.5, 1000.5, 0)")
    net.start()
    P = "SIM.players[1]"

    # --- beam up: the cabin is built around the player ---------------------
    rt.run(f"TREK.Transport.beamUp({P})")
    net.pump(180)
    if died(rt, "single player, beaming up"):
        return
    check(at_pad(rt), f"single player: beam up left the player at {pos(rt)}, not the pad")
    check(ship(rt, "built") is True, "single player: the cabin was never built")
    containers, stocked, wet = cabin_objects(rt)
    check(containers >= 19 and stocked == containers,
          f"single player: {stocked} of {containers} containers stocked")
    check(wet >= 1, "single player: the galley sink holds no water")
    check(rt.eval("SIM.lamps") > 0, "single player: the cabin lights were never hung")
    trees = rt.eval("""(function()
        local C, U = TREK.Config, TREK.Util
        local n = 0
        for ox = -C.ClearMargin, C.CabinW + C.ClearMargin do
            for oy = -C.ClearMargin, C.CabinL + C.ClearMargin do
                local x, y = U.at(ox, oy)
                local sq = SIM.squares[x .. "," .. y .. ",0"]
                if sq then for _, o in ipairs(sq.objects) do
                    if o.spriteName:find("americanholly") then n = n + 1 end
                end end
            end
        end
        return n end)()""")
    check(trees == 0, f"single player: {trees} trees left standing around the cabin")

    # The sink drains and the minute timer refills it.
    rt.run("""for _, spot in ipairs(TREK.Config.WaterTags and {} or {}) do end
        local C, U = TREK.Config, TREK.Util
        for ox = 0, C.CabinW do for oy = 0, C.CabinL do
            local x, y = U.at(ox, oy)
            for _, o in ipairs(SIM.rawSquare(x, y, C.CabinZ).objects) do
                if o.fluid then o.fluid.amount = 0 end
            end
        end end""")
    rt.fire("EveryOneMinute")
    check(cabin_objects(rt)[2] >= 1, "single player: the sink was not refilled after draining")

    # --- helm --------------------------------------------------------------
    rt.run(f"TREK.Travel.setDestination({P}, 3000, 3000, 0)")
    net.pump(2)
    check(rt.eval("TREK.Util.state().destination and TREK.Util.state().destination.x") == 3000,
          "single player: setting a course did not reach the ship")
    rt.run(f"TREK.Travel.addBookmark({P}, 'Home <b>', nil)")
    rt.run(f"TREK.Core.send({P}, 'setShields', {{ up = false }})")
    net.pump(2)
    check(rt.eval("#TREK.Util.state().bookmarks") == 1, "single player: bookmark not logged")
    check(rt.eval("TREK.Util.state().bookmarks[1].name") == "Home b",
          "single player: a bookmark name was not cleaned of markup")
    check(ship(rt, "shields") is False, "single player: shields did not go down")
    rt.run(f"TREK.Core.send({P}, 'setShields', {{ up = true }})")

    # --- take her down -----------------------------------------------------
    rt.run(f"TREK.Travel.descend({P}, {{ x = 3000, y = 3000, z = 0 }})")
    net.pump(80)
    check(ship(rt, "landed") is True, "single player: taking her down did not land the ship")
    sx, sy = ship(rt, "x"), ship(rt, "y")
    check(abs(sx - 3000) <= 24 and abs(sy - 3000) <= 24,
          f"single player: landed at {sx},{sy}, far from the course")
    check(hull_at(rt, sx, sy, 0), "single player: no shuttle vehicle on the landing square")
    check(shuttles(rt) == 1, f"single player: {shuttles(rt)} shuttle vehicles after landing")
    check(ship_vehicle(rt) is not None, "single player: the ship state does not name its vehicle")
    check(rt.eval("SIM.vehicles[1].hotwired and SIM.vehicles[1].tank.amount > 0"),
          "single player: the shuttle vehicle cannot be started (no hotwire or no fuel)")
    check(ship(rt, "destination") is None, "single player: the course was not cleared on landing")
    x, y, _ = pos(rt)
    check(not rt.eval(f"TREK.World.hullCovers({x}, {y}, 0)"),
          "single player: the player was left standing under the hull")
    check(any("IGUI_TREK_Landed" in n for n in rt.notes()), "single player: no landing note")

    # --- the hatch -----------------------------------------------------------
    rt.run(f"TREK.Core.enter({P})")
    net.pump(70)
    check(at_pad(rt), "single player: boarding through the hatch did not reach the pad")
    rt.run(f"TREK.Core.exit({P})")
    net.pump(65)
    x, y, _ = pos(rt)
    check(abs(x - sx) <= 8 and abs(y - sy) <= 8,
          f"single player: stepping out put the player at {x},{y}, not beside the hull")
    check(not rt.eval(f"SIM.rawSquare({int(x)}, {int(y)}, 0):getVehicleContainer() ~= nil"),
          "single player: stepping out put the player under the shuttle vehicle")

    # --- driving it: the ship follows its vehicle -------------------------
    vid = ship_vehicle(rt)
    rt.run(f"SIM.driveVehicle({vid}, {sx} + 12.5, {sy} + 3.5)")
    rt.run(f"{P}.x, {P}.y = {sx} + 12.5, {sy} + 8.5")
    net.pump(70)
    check(ship(rt, "x") == sx + 12 and ship(rt, "y") == sy + 3,
          "single player: the ship did not follow its vehicle when it was driven")
    sx, sy = ship(rt, "x"), ship(rt, "y")

    # --- a removed vehicle must not be left in anyone's loot window ---------
    # Standing beside the ship puts its seat containers there. Recall it and
    # the window is holding a container of a vehicle that no longer exists:
    # vanilla throws on that every frame (a black screen, seen in game).
    rt.run(f"""
        local vehicle = SIM.findVehicle({vid})
        getPlayerLoot(0):setNewContainer(vehicle:seatContainer())
    """)

    # --- recall is refused while someone sits in it -------------------------
    rt.run(f"SIM.findVehicle({vid}).seats[0] = {P}")
    rt.run(f"TREK.Menu.onRecall(nil, {P})")
    net.pump(2)
    check(ship(rt, "landed") is True, "single player: recalled the ship out from under its pilot")
    check(any("IGUI_TREK_CrewSeated" in n for n in rt.notes()),
          "single player: no reason given for refusing to recall an occupied ship")
    rt.run(f"SIM.findVehicle({vid}).seats[0] = nil")

    # --- call down far away: the old vehicle is a leftover until it loads -----
    rt.run(f"{P}.x, {P}.y = 5000.5, 5000.5")
    net.pump(40)   # the ground streams in around the player
    rt.run(f"TREK.Menu.onCallDown(nil, {P}, 5003, 5000, 0)")
    net.pump(2)
    check(ship(rt, "x") == 5003, "single player: calling the ship down did not move it")
    check(shuttles(rt) == 2, "single player: expected the old vehicle to wait, unloaded, "
                             f"alongside the new one; found {shuttles(rt)}")
    rt.run(f"{P}.x, {P}.y = {sx}.5, {sy + 8}.5")
    net.pump(130)   # streaming, then the next vehicle pass
    check(not hull_at(rt, sx, sy, 0), "single player: the old vehicle was not removed once loaded")
    check(shuttles(rt) == 1, f"single player: {shuttles(rt)} shuttle vehicles after the sweep")

    # --- recall ------------------------------------------------------------
    rt.run(f"{P}.x, {P}.y = 5000.5, 5003.5")
    net.pump(40)
    rt.run(f"TREK.Menu.onRecall(nil, {P})")
    net.pump(2)
    check(ship(rt, "landed") is False, "single player: recall did not lift the ship")
    net.pump(35)
    # Spotting a dead container must never be done by calling something that
    # throws: the engine dumps a Java stack trace per call, and on a timer that
    # is a log flood and a black screen -- 2932 traces in one session, seen in
    # game on 2026-09-17. getVehiclePart():getVehicle() answers with nulls.
    check(rt.eval("SIM.throwingProbes") is None,
          "single player: the mod probed a removed vehicle with a call that "
          "throws out of Java; on a timer that floods the log and blacks the "
          "screen. Use getVehiclePart():getVehicle().")
    check(rt.eval("getPlayerLoot(0).inventory:isVehiclePart()") is False,
          "single player: the loot window still holds a container of the removed "
          "vehicle -- vanilla throws on that every frame")
    check(not hull_at(rt, 5003, 5000, 0), "single player: recall left the hull behind")
    check(shuttles(rt) == 0, "single player: recall left a shuttle vehicle behind")

    # --- a landing with no room beams the player home ----------------------
    rt.run(f"TREK.Transport.beamUp({P})")
    net.pump(180)
    rt.run("""for x = 7900, 8100 do for y = 7900, 8100 do
        SIM.rawSquare(x, y, 0).solid = true end end""")
    rt.run(f"TREK.Travel.descend({P}, {{ x = 8000, y = 8000, z = 0 }})")
    net.pump(520)
    check(at_pad(rt), f"single player: a landing with no room left the player at {pos(rt)}")
    check(ship(rt, "landed") is False, "single player: the ship landed somewhere solid")
    check(any("IGUI_TREK_NoRoom" in n for n in rt.notes()),
          "single player: no reason given for the refused landing")

    # --- beam down goes back where you came from --------------------------
    rt.run(f"TREK.Transport.beamDown({P})")
    net.pump(160)
    x, y, _ = pos(rt)
    check(abs(x - 5000) <= 6 and abs(y - 5003) <= 6,
          f"single player: beam down went to {x},{y}, not the return point")

    for w in rt.warnings():
        if "SIM DEATH" not in str(w) or not died(rt, "single player"):
            fail(f"single player: {w}")
    print(f"single player: cabin {containers} containers, landed, hatch, ghosts, "
          f"refusal and return all checked")


# ---------------------------------------------------------------------------
# Flight
# ---------------------------------------------------------------------------
def seat(rt, n=0, who=1):
    """Puts the player in a seat of the ship's vehicle."""
    rt.run(f"""
        local v = TREK.Vehicle.find(TREK.Util.state().vehicleId)
        v.seats[{n}] = SIM.players[{who}]
        SIM.players[{who}].vehicle = v
    """)


def vehicle_z(rt):
    return rt.eval("""(function()
        local v = TREK.Vehicle.find(TREK.Util.state().vehicleId)
        return v and v:getZ() or -1
    end)()""")


def flight():
    """Taking her up, keeping her up, and every way of coming back down.

    The heart of it is that a vehicle's z is not its physics height: build 42
    zeroes it every tick and only restores it where a floor exists underneath.
    The simulation models that rule, so a flight that forgets to lay the sky
    plane shows the ship on the deck here exactly as it would in game.
    """
    P = "SIM.players[1]"
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('pilot', 3000.5, 3000.5, 0)")
    net.start()
    net.pump(5)

    # Put her on the ground with the pilot at the controls.
    rt.run(f"TREK.Menu.onCallDown(nil, {P}, 3004, 3000, 0)")
    net.pump(40)
    check(ship(rt, "landed") is True, "flight: the ship would not land to start with")
    seat(rt)

    # --- take off ---------------------------------------------------------
    rt.run(f"TREK.Flight.takeOff({P})")
    net.pump(400)
    check(ship(rt, "flying") is True,
          "flight: she never got off the ground")
    check(ship(rt, "level") == rt.eval("TREK.Config.FlightCruise"),
          f"flight: airborne at level {ship(rt, 'level')}, not the cruise level")
    check(vehicle_z(rt) == rt.eval("TREK.Config.FlightCruise"),
          f"flight: the engine puts the ship at z {vehicle_z(rt)}, not the flight "
          f"level -- the sky plane is not holding it up")
    check(ship(rt, "pilot") == "pilot", "flight: the ship does not know who is flying it")

    # The plane is the one world edit a client may make, and it must be the
    # only one: invisible floor, above the ground, and nothing else.
    check(rt.eval("SIM.skyEdit") and rt.eval("SIM.skyEdit") > 0,
          "flight: no sky plane was laid at all")
    check(rt.eval("TREK.Sky.count()") > 0,
          "flight: the sky module is not holding any squares")
    check(rt.eval("SIM.clientWorldEdit") is None,
          "flight: the world was edited for something other than the sky plane")

    # s.z is the ground she will come back to, never the altitude. Everything
    # from the cabin hatch to the shields measures from it.
    check(ship(rt, "z") == 0,
          f"flight: the altitude leaked into s.z ({ship(rt, 'z')}); the hatch would "
          f"drop anyone who used it")

    # --- the hatch is shut while she is up --------------------------------
    before = pos(rt)
    rt.run(f"TREK.Core.exit({P})")
    net.pump(60)
    check(pos(rt) == before,
          "flight: stepping out of the hatch in mid-air was allowed")

    # --- the pilot goes aft, and she stays up -----------------------------
    rt.run(f"""
        local v = TREK.Vehicle.find(TREK.Util.state().vehicleId)
        v:exit(SIM.players[1])
        local x, y, z = TREK.Util.padSpot()
        SIM.players[1].x, SIM.players[1].y = x + 0.5, y + 0.5
        SIM.players[1].z, SIM.players[1].lastZ = z, z
    """)
    net.pump(500)
    check(ship(rt, "flying") is True,
          "flight: she came down the moment the pilot stepped aft to the cabin")
    check(shuttles(rt) == 1,
          "flight: the ship's own vehicle was swept up as a leftover in flight")

    # --- and back to the seat, then down ----------------------------------
    # Back to the ship first, and a moment for its ground to stream in again:
    # while the pilot was in the cabin the vehicle was not loaded here at all,
    # which is exactly why flight must not read "the vehicle is not in the
    # cell's list" as "the vehicle is gone".
    rt.run("""
        local p = SIM.players[1]
        p.x, p.y, p.z, p.lastZ = 3004.5, 3000.5, 3, 3
    """)
    net.pump(70)
    seat(rt)
    net.pump(70)
    rt.run(f"TREK.Flight.land({P})")
    net.pump(200)
    check(ship(rt, "flying") is None, "flight: she would not come down")
    check(ship(rt, "landed") is True, "flight: she came down but is not landed")
    check(shuttles(rt) == 1,
          "flight: landing respawned the vehicle -- the trunk and seats are gone")
    check(rt.eval("TREK.Sky.count()") == 0,
          f"flight: {rt.eval('TREK.Sky.count()')} invisible floors were left in the sky")

    for w in rt.warnings():
        fail(f"flight: {w}")
    print("flight: take-off, the sky plane, the shut hatch, the pilot going aft "
          "and the landing all checked")


def flight_endings():
    """Flight must not survive its pilot, or a world load."""
    # --- the pilot dies in the air ----------------------------------------
    P = "SIM.players[1]"
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('pilot', 3000.5, 3000.5, 0)")
    net.start()
    net.pump(5)
    rt.run(f"TREK.Menu.onCallDown(nil, {P}, 3004, 3000, 0)")
    net.pump(40)
    seat(rt)
    rt.run(f"TREK.Flight.takeOff({P})")
    net.pump(400)
    check(ship(rt, "flying") is True, "flight endings: she never got up")

    rt.run(f"""
        local v = TREK.Vehicle.find(TREK.Util.state().vehicleId)
        v:exit(SIM.players[1])
        SIM.players[1].dead = true
    """)
    net.pump(600)
    check(ship(rt, "flying") is None,
          "flight endings: flight outlived its pilot -- the 1.1 bug, back again")
    check(ship(rt, "pilot") is None,
          "flight endings: the dead pilot is still recorded at the controls")

    # --- a world saved in flight opens on the ground ----------------------
    net2 = Net("sp")
    rt2 = net2.server
    rt2.run("""
        SIM.player('later', 3000.5, 3000.5, 0)
        local s = ModData.getOrCreate("TREK_State_v1")
        s.schema, s.landed, s.x, s.y, s.z = 2, true, 3004, 3000, 0
        s.flying, s.level, s.pilot = true, 3, 'someone'
        s.skyAt = { x = 3004, y = 3000, level = 3 }
        s.built, s.rev, s.bookmarks, s.ghosts, s.crew = true, 10, {}, {}, {}
    """)
    net2.start()
    check(ship(rt2, "flying") is None,
          "flight endings: a world saved in flight reopened still flying, with a "
          "pilot who is not even connected")
    check(ship(rt2, "skyAt") is not None,
          "flight endings: the record of where the sky plane was is gone, so its "
          "invisible floors can never be lifted")

    for r in (rt, rt2):
        for w in r.warnings():
            if "SIM DEATH" not in str(w):
                fail(f"flight endings: {w}")
    print("flight endings: a dead pilot and a world reload both bring her down")


def migration():
    net = Net("sp")
    rt = net.server
    rt.run("""
        SIM.player('old', 1200.5, 1200.5, 0)
        local s = ModData.getOrCreate("TREK_State_v1")
        s.schema, s.landed, s.x, s.y, s.z = 1, true, 1203, 1200, 0
        s.returnX, s.returnY, s.returnZ = 1201, 1201, 0
        s.built, s.rev, s.bookmarks, s.ghosts = true, 10, {}, {}
        s.flightX, s.speedStep, s.inside = 5, 3, true
    """)
    net.start()
    check(ship(rt, "schema") == 2, "migration: a schema 1 save was not upgraded")
    check(ship(rt, "speedStep") is None and ship(rt, "flightX") is None,
          "migration: flight fields survived the upgrade")
    check(ship(rt, "landed") is True and ship(rt, "x") == 1203,
          "migration: the landed position was lost")
    check(rt.eval("(TREK.Ship.returnPoint(SIM.players[1]))") == 1201,
          "migration: the old save's return point was lost")
    net.pump(70)
    check(hull_at(rt, 1203, 1200, 0) and shuttles(rt) == 1,
          "migration: a ship landed before the vehicle did not get one")
    for w in rt.warnings():
        fail(f"migration: {w}")
    print("migration: schema 1 save upgraded with its position and return point")


# ---------------------------------------------------------------------------
# Multiplayer
# ---------------------------------------------------------------------------
def multiplayer():
    net = Net("mp", clients=("alice", "bob"))
    srv, A, B = net.server, net.clients["alice"], net.clients["bob"]
    for rt in net.all():
        rt.run("SandboxVars.TrekShuttle.Access = 2; SIM.antiCheatSpeed = 2")
    srv.run("SIM.player('alice', 2000.5, 2000.5, 0); SIM.player('bob', 2010.5, 2000.5, 0)")
    A.run("SIM.player('alice', 2000.5, 2000.5, 0)")
    B.run("SIM.player('bob', 2010.5, 2000.5, 0)")
    # A client's view of who is online.
    for c in (A, B):
        c.run("function getOnlinePlayers() return SIM.jlist({ SIM.players[1], "
              "{ name = (SIM.players[1].name == 'alice') and 'bob' or 'alice', "
              "getUsername = function(self) return self.name end } }) end")
    net.start()
    P = "SIM.players[1]"

    # --- the first to beam up owns the ship; the cabin reaches their client --
    A.run(f"TREK.Transport.beamUp({P})")
    net.pump(210)
    if died(A, "multiplayer, alice beaming up"):
        return
    check(ship(srv, "owner") == "alice", f"multiplayer: owner is {ship(srv, 'owner')!r}, not alice")
    check(ship(srv, "built") is True, "multiplayer: the server never built the cabin")
    check(at_pad(A), f"multiplayer: alice is at {pos(A)}, not on the pad")
    check(A.eval("TREK.Core.arriving()") is False, "multiplayer: alice is still held on arrival")
    sc = cabin_objects(srv)
    ac = cabin_objects(A)
    check(sc[0] >= 19 and sc[1] == sc[0], f"multiplayer: server stocked {sc[1]} of {sc[0]} containers")
    check(tuple(ac) == tuple(sc), f"multiplayer: alice sees cabin {tuple(ac)}, server has {tuple(sc)}")
    check(A.eval("TREK.Util.state().owner") == "alice",
          "multiplayer: the ship state never reached alice's client")

    # --- a stranger is refused, then added to the crew ---------------------
    before = pos(B)
    B.run(f"TREK.Transport.beamUp({P})")
    net.pump(180)
    check(pos(B) == before, "multiplayer: bob beamed up without being crew")
    check(any("IGUI_TREK_NotCrew" in n for n in B.notes()), "multiplayer: bob was not told why")

    A.run(f"TREK.Core.send({P}, 'setCrew', {{ name = 'bob', on = true }})")
    B.run(f"TREK.Core.send({P}, 'setCrew', {{ name = 'bob', on = false }})")
    net.pump(2)
    check(srv.eval("TREK.Util.state().crew.bob") is True,
          "multiplayer: the owner could not add bob, or bob removed himself")
    B.run(f"TREK.Transport.beamUp({P})")
    net.pump(180)
    check(at_pad(B), f"multiplayer: crewman bob is at {pos(B)}, not on the pad")
    check(tuple(cabin_objects(B)) == tuple(sc), "multiplayer: bob sees a different cabin")

    # --- transporter charges -------------------------------------------------
    # alice has spent 1 (up). down = 2, up = 3, down = refused.
    A.run(f"TREK.Transport.beamDown({P})")
    net.pump(170)
    check(not A.eval(f"TREK.Util.isInteriorPlayer({P})"), "multiplayer: alice's beam down failed")
    A.run(f"TREK.Transport.beamUp({P})")
    net.pump(180)
    check(at_pad(A), "multiplayer: alice's third beam failed")
    A.run(f"TREK.Transport.beamDown({P})")
    net.pump(170)
    check(A.eval(f"TREK.Util.isInteriorPlayer({P})"), "multiplayer: a fourth beam was allowed")
    check(any("IGUI_TREK_Recharging" in n for n in A.notes()),
          "multiplayer: alice was not told the transporter is recharging")
    net.clock += 151_000
    A.run(f"TREK.Transport.beamDown({P})")
    net.pump(170)
    check(not A.eval(f"TREK.Util.isInteriorPlayer({P})"),
          "multiplayer: a charge did not come back after 150 seconds")

    # --- take her down from a client ----------------------------------------
    net.clock += 1_000_000
    B.run(f"TREK.Core.send({P}, 'setCourse', {{ x = 2600, y = 2600, z = 0 }})")
    net.pump(2)
    check(A.eval("TREK.Util.state().destination.x") == 2600,
          "multiplayer: bob's course did not reach alice")
    B.run(f"TREK.Travel.descend({P}, {{ x = 2600, y = 2600, z = 0 }})")
    net.pump(100)
    check(ship(srv, "landed") is True, "multiplayer: bob's landing did not set the ship down")
    lx, ly = ship(srv, "x"), ship(srv, "y")
    check(hull_at(A, lx, ly, 0),
          "multiplayer: alice's world has no shuttle vehicle where the server landed it")
    check(shuttles(A) == 1 and shuttles(srv) == 1,
          f"multiplayer: shuttle vehicles -- server {shuttles(srv)}, alice {shuttles(A)}")

    # Driven by a client: the vehicle moves on every machine (the game syncs
    # vehicles); the server's ship position follows it.
    vid = ship_vehicle(srv)
    for rt in net.all():
        rt.run(f"SIM.driveVehicle({vid}, {lx} + 6.5, {ly} + 1.5)")
    net.pump(70)
    check(ship(srv, "x") == lx + 6 and A.eval("TREK.Util.state().x") == lx + 6,
          "multiplayer: the ship's position did not follow its vehicle to every client")
    lx, ly = ship(srv, "x"), ship(srv, "y")

    # --- shields: each client pushes only its own zombies --------------------
    B.run(f"""
        local s = TREK.Ship.get()
        mine = SIM.zombie(s.x + 2.5, s.y + 0.5, 0, false)
        theirs = SIM.zombie(s.x + 3.5, s.y + 0.5, 0, true)
        TREK.Core.repelZombies()
    """)
    check(B.eval("math.abs(mine.x - TREK.Ship.get().x) > 10"),
          "multiplayer: shields did not push bob's own zombie")
    check(B.eval("math.abs(theirs.x - TREK.Ship.get().x) < 5"),
          "multiplayer: bob's client moved a zombie another client owns")

    # --- nobody but the server writes -----------------------------------------
    server_state = to_py(srv.eval("TREK.Util.state()"))
    for name, c in net.clients.items():
        check(c.eval("SIM.clientWorldEdit") is None,
              f"multiplayer: {name}'s client edited the world directly")
        mine = to_py(c.eval("TREK.Util.state()"))
        check(mine == server_state,
              f"multiplayer: {name}'s copy of the ship differs from the server's")

    # A client that transmits the ship must not change the server's.
    B.run("TREK.Util.state().owner = 'bob'; ModData.transmit('TREK_State_v1')")
    net.pump(2)
    check(ship(srv, "owner") == "alice", "multiplayer: the server accepted a client's ship table")

    for rt in net.all():
        for w in rt.warnings():
            if "commitOnClient" in w:
                fail(f"multiplayer ({rt.name}): a client tried to commit ship state")
            else:
                fail(f"multiplayer ({rt.name}): {w}")
    print("multiplayer: ownership, crew, shared cabin, charges, remote landing, "
          "shields and single-writer state all checked")


# ---------------------------------------------------------------------------
# Static checks
# ---------------------------------------------------------------------------
def read(folder):
    base = os.path.join(LUA, folder, "TREK")
    out = {}
    for f in sorted(os.listdir(base)):
        if f.endswith(".lua"):
            out[f] = open(os.path.join(base, f), encoding="utf-8").read()
    return out


def static():
    client, server, shared = read("client"), read("server"), read("shared")

    sent = set()
    for src in client.values():
        sent |= set(re.findall(r'(?:Net|Core)\.send\([^,]+,\s*"(\w+)"', src))
        sent |= {"move"} if "requestMove" in src else set()
    handled = set()
    for src in server.values():
        handled |= set(re.findall(r'Net\.onServer\("(\w+)"', src))
    for cmd in sorted(sent - handled):
        fail(f"static: clients send {cmd!r} and no server handler exists")

    replies = set()
    for src in server.values():
        replies |= set(re.findall(r'Net\.toClient\([^,]+,\s*"(\w+)"', src))
        replies |= set(re.findall(r'Net\.toAll\("(\w+)"', src))
    if "deny(" in "".join(server.values()):
        replies.add("denied")
    listened = set()
    for src in client.values():
        listened |= set(re.findall(r'Net\.onClient\("(\w+)"', src))
    for cmd in sorted(replies - listened):
        fail(f"static: the server replies {cmd!r} and no client listens")

    for f, src in client.items():
        if not re.search(r"^if isServer\(\) then return end$", src, re.M):
            fail(f"static: client/{f} has no 'if isServer() then return end' guard")
        for bad in ("Ship.commit", "ModData.transmit", "U.state()"):
            if bad in src:
                fail(f"static: client/{f} uses {bad}; clients read Ship.get() and ask the server")
    for f, src in server.items():
        if not re.search(r"^if isClient\(\) then return end$", src, re.M):
            fail(f"static: server/{f} has no 'if isClient() then return end' guard")

    gated = ("setGodMod", "setGodModCheat", "setZombiesDontAttack", "setInvincible",
             "setNoClip", "setInvisible", "setGhostMode")
    for folder, files in (("client", client), ("server", server), ("shared", shared)):
        for f, src in files.items():
            for n, line in enumerate(src.splitlines(), 1):
                code = line.split("--", 1)[0]
                for name in gated:
                    if re.search(rf"[:.]{name}\(", code):
                        fail(f"static: {folder}/{f}:{n} calls {name}, which build 42 "
                             f"refuses for ordinary players")
    print(f"static: {len(sent)} client commands, {len(replies)} replies, guards checked")


def main():
    static()
    migration()
    single_player()
    flight()
    flight_endings()
    multiplayer()
    if failures:
        print(f"\n{len(failures)} PROBLEM(S):")
        for f in dict.fromkeys(failures):
            print("  " + f)
        sys.exit(1)
    print("\nsingle player and multiplayer behave as designed")


main()
