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
        elseif op == "playerItem" then
            -- Only if this runtime is that player: an item in somebody's
            -- pockets is not world state and reaches no one else.
            for _, p in ipairs(SIM.players) do
                if p.name == d.who then p.inventory:AddItem(instanceItem(d.item)) end
            end
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
                rt.run("SIM.stream(); SIM.gravity(); SIM.vehicleGravity(); SIM.settleUI()")
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
    """(containers, stocked, water fixtures with water, containers meant to hold something).

    The last one is counted out of the layout rather than written down here.
    Most of the cabin's containers are deliberately empty -- they are the
    player's shelves, not the ship's stores -- so "every container is stocked"
    stopped being the right assertion at the refit, and a number typed in here
    would go stale the first time a locker moved.
    """
    return rt.eval("""(function()
        local C, U = TREK.Config, TREK.Util
        local L = require "TREK/TREK_InteriorLayout"
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
        local wanted = 0
        for _, e in ipairs(L.tiles) do
            if e.loot ~= nil or e.special ~= nil then wanted = wanted + 1 end
        end
        return containers, stocked, wet, wanted
    end)()""")


def cabin_stores(rt):
    """Every distinct item id sitting in a cabin container."""
    packed = rt.eval("""(function()
        local C, U = TREK.Config, TREK.Util
        local seen, out = {}, {}
        for ox = 0, C.CabinW do for oy = 0, C.CabinL do
            local x, y = U.at(ox, oy)
            for _, o in ipairs(SIM.rawSquare(x, y, C.CabinZ).objects) do
                if o.container then
                    for _, it in ipairs(o.container.items) do
                        local id = it.getFullType and it:getFullType() or tostring(it)
                        if not seen[id] then seen[id] = true; out[#out + 1] = id end
                    end
                end
            end
        end end
        return table.concat(out, "\\n")
    end)()""")
    return sorted(x for x in str(packed).split("\n") if x)


def loot_list(rt, name):
    """A C.Loot list, as Python strings."""
    packed = rt.eval(f"""(function()
        return table.concat(TREK.Config.Loot["{name}"], "\\n")
    end)()""")
    return [x for x in str(packed).split("\n") if x]


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
    containers, stocked, wet, wanted = cabin_objects(rt)
    check(wanted >= 3 and stocked == wanted,
          f"single player: {stocked} of {wanted} stocked containers got stock "
          f"({containers} containers in the cabin)")
    check(wet >= 1, "single player: the galley sink holds no water")

    # What is actually meant to be true, rather than "N of N containers were
    # stocked": the ship sails with its own gear aboard. Counting containers
    # cannot see a locker that quietly lost its loot list, because the count
    # of containers wanting stock falls with it and the two still agree.
    stores = cabin_stores(rt)
    for name in ("weapons", "food", "medical"):
        for item_id in loot_list(rt, name):
            check(item_id in stores,
                  f"single player: the cabin sails without {item_id} "
                  f"(C.Loot.{name})")
    phaser = str(rt.eval("TREK.Config.PhaserItem"))
    check(phaser in stores, f"single player: no {phaser} in the armoury")
    # Starfleet issue only. Five of the cabin's containers are the player's own
    # shelves and start empty, so at build time everything aboard is ours; a
    # vanilla id in here means a ship list grew one back.
    strays = [x for x in stores if not x.startswith("TrekShuttle.")]
    check(not strays, f"single player: vanilla loot stocked into the ship's "
                      f"own lockers: {strays}")
    # The viewscreen has to be an IsoTelevision carrying device data, not an
    # IsoObject wearing a television's sprite. The second one is what the
    # cabin had for three versions: drawn, present, and with nothing to
    # right-click -- and indistinguishable from the first until you try.
    check(rt.eval("""(function()
        local C, U = TREK.Config, TREK.Util
        local L = require "TREK/TREK_InteriorLayout"
        for _, e in ipairs(L.tiles) do
            if e.device then
                local x, y = U.at(e.x, e.y)
                for _, o in ipairs(SIM.rawSquare(x, y, C.CabinZ).objects) do
                    if o.spriteName == e.sprite then
                        return o.class == "IsoTelevision" and o.deviceData ~= nil
                    end
                end
                return false
            end
        end
        return false
    end)()"""), "single player: the television is scenery, not a device")

    # --- the ship's own power --------------------------------------------
    # The cabin is not on the town grid and has no generator, so its squares
    # can never report electricity: setHaveElectricity does not set a flag,
    # and haveElectricity() means "a generator is running in this chunk".
    # What makes a fitting work is its own cell, kept full by TREK_Power.
    def tv(field):
        return rt.eval(f"""(function()
            local C, U = TREK.Config, TREK.Util
            local L = require "TREK/TREK_InteriorLayout"
            for _, e in ipairs(L.tiles) do
                if e.device then
                    local x, y = U.at(e.x, e.y)
                    local o = U.findSprite(U.square(x, y, C.CabinZ, false), e.sprite)
                    local d = o and o:getDeviceData()
                    return d and d:{field}() or nil
                end
            end
        end)()""")

    check(tv("getIsBatteryPowered") is True,
          "single player: the television has no power source of its own, so "
          "it can never be switched on in a cabin with no grid")
    check(tv("getHasBattery") is not True,
          "single player: the television reports a battery, which lets the "
          "radio panel hand the player a free one every time it is opened")
    check(float(tv("getPower") or 0) > 0,
          "single player: the television's cell is flat")

    # Switch it on and run three game hours past it. Without the per-minute
    # top-up the engine drains useDelta a minute and the device switches
    # itself off at zero, which is the whole reason TREK_Power exists.
    rt.run("""(function()
        local C, U = TREK.Config, TREK.Util
        local L = require "TREK/TREK_InteriorLayout"
        for _, e in ipairs(L.tiles) do
            if e.device then
                local x, y = U.at(e.x, e.y)
                local o = U.findSprite(U.square(x, y, C.CabinZ, false), e.sprite)
                o:getDeviceData():setIsTurnedOn(true)
            end
        end
    end)()""")
    check(tv("getIsTurnedOn") is True,
          "single player: the television refused to switch on")
    for _ in range(180):
        rt.run("SIM.drainDevices(1)")
        rt.fire("EveryOneMinute")
    check(tv("getIsTurnedOn") is True,
          "single player: the television switched itself off after three game "
          "hours; the ship's power is not keeping up with the drain")
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

    # --- beaming up out of the cockpit must leave the seat ------------------
    # A pilot who beams up is still riding as far as the engine is concerned
    # unless the mod says so: player:getVehicle() keeps answering with the
    # shuttle. The character is then put down in the cabin's cell, the
    # shuttle's chunk unloads behind them, and every part of that vehicle is
    # left with a null back-reference -- which vanilla's own inventory page
    # walks every frame through the `elseif playerObj:getVehicle()` branch of
    # refreshBackpacks. 829 stack traces in one session, the game unresponsive
    # and no way into the interior. Seen in game 2026-09-18.
    #
    # finishDown already stepped out of the seat on the way *out*, with a
    # comment saying why. The beam-up half was simply missing, and nothing in
    # the mod's Lua appears in that stack trace, which is what made it look
    # like a vanilla fault.
    rt.run(f"""
        local v = SIM.findVehicle({vid})
        v.seats[0] = {P}
        {P}.vehicle = v
    """)
    rt.run(f"TREK.Transport.beamUp({P})")
    net.pump(180)
    check(rt.eval(f"{P}:getVehicle() == nil") is True,
          "single player: beaming up left the player riding the shuttle. "
          "Vanilla's inventory page then walks that vehicle's parts every "
          "frame and throws on each one.")
    rt.run(f"TREK.Transport.beamDown({P}, {{ x = {sx}, y = {sy} + 8, z = 0 }})")
    net.pump(220)

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
        local v = TREK.Vehicle.ship()
        v.seats[{n}] = SIM.players[{who}]
        SIM.players[{who}].vehicle = v
    """)


def vehicle_z(rt):
    return rt.eval("""(function()
        local v = TREK.Vehicle.ship()
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

    # --- the radial menu actually offers it --------------------------------
    # Vanilla's radial is a toggle, and a hook that adds slices only when the
    # menu reports itself visible runs solely while it is being dismissed. That
    # is invisible from the source and cost a whole test session, so the menu is
    # opened here for real and its slices read back.
    rt.run("SIM.radial.visible = false")
    rt.run(f"ISVehicleMenu.showRadialMenu({P})")
    titles = rt.eval("getPlayerRadialMenu():titles()")
    check("IGUI_TREK_TakeOff" in (titles or ""),
          f"flight: the radial menu offers no way to take off (slices: {titles})")
    check("IGUI_TREK_BoardCabin" in (titles or ""),
          f"flight: the radial menu offers no way into the cabin (slices: {titles})")

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

    # --- the plane must survive the flight it is holding up ----------------
    # s.skyAt is written on take-off so a flight that ends in a crash still
    # gets its floors lifted. Read without checking whether she is still up, it
    # swept away the plane she was resting on one second after take-off,
    # physics took over and she tipped into the ground. Seen in game.
    net.pump(300)
    check(rt.eval("TREK.Sky.count()") > 0,
          "flight: the sky plane was swept away while she was still flying on it")
    check(vehicle_z(rt) == rt.eval("TREK.Config.FlightCruise"),
          f"flight: she dropped to z {vehicle_z(rt)} while airborne")
    check(ship(rt, "flying") is True, "flight: she did not stay up")

    # --- flying along must not drag a wake of floor behind her -------------
    # Every square of floor that is not under the hull is a square of shadow on
    # the ground: a floor darkens what is beneath it and nothing can stop that.
    # A generous trim margin left a 9x9 box around a hull that covers 15
    # squares, which is the "trailing dark blotch of black blocks" seen in
    # game. Flying must not hold more floor than the patch is wide.
    vid = ship_vehicle(rt)
    area = rt.eval("TREK.Sky.area()")
    for step in range(1, 9):
        rt.run(f"SIM.driveVehicle({vid}, 3004.5 + {step} * 3, 3000.5)")
        rt.run(f"SIM.players[1].x = 3004.5 + {step} * 3")
        net.pump(6)
    held = rt.eval("TREK.Sky.count()")
    check(held <= area,
          f"flight: she is dragging {held} squares of floor behind her, and the "
          f"patch is only {area} -- that is a wake of shadow on the ground")
    check(vehicle_z(rt) == rt.eval("TREK.Config.FlightCruise"),
          f"flight: she lost height while flying along (z {vehicle_z(rt)})")

    # --- climbing and diving must not drop her -----------------------------
    # Changing level means two planes exist for a moment, and the one she is
    # standing on is the *old* one. Trimming to the new target first took the
    # floor out from under her mid-climb: she fell, once into a building.
    cruise = rt.eval("TREK.Config.FlightCruise")
    rt.run(f"TREK.Flight.climb({P})")
    # Watched tick by tick, not just at the end. Pulling the floor from under
    # her mid-climb is survivable -- the next pass puts her back -- so reading
    # only the final height reports success while she visibly lurches. The
    # physics body must never sag toward the ground at all.
    rt.run("""for _, v in ipairs(SIM.vehicles) do v.minLevel = nil end""")
    net.pump(120)
    worst = rt.eval("""(function()
        local v = TREK.Vehicle.ship()
        return v and v.minLevel or 99
    end)()""")
    check(worst >= cruise - 0.1,
          f"flight: she sagged to level {worst:.2f} during the climb; the floor "
          f"was taken from under her before she was on the new one")
    check(ship(rt, "level") == cruise + 1,
          f"flight: the climb was not accepted (level {ship(rt, 'level')})")
    check(vehicle_z(rt) == cruise + 1,
          f"flight: she did not reach the level she climbed to (z {vehicle_z(rt)})")
    check(ship(rt, "flying") is True, "flight: climbing dropped her out of flight")

    rt.run(f"TREK.Flight.dive({P})")
    net.pump(120)
    check(vehicle_z(rt) == cruise,
          f"flight: she did not come back down a level (z {vehicle_z(rt)})")
    check(ship(rt, "flying") is True, "flight: diving dropped her out of flight")

    # --- the ceiling is real, and says so ---------------------------------
    # She is at cruise + 1 now, which is the top. Asking for more must be
    # refused out loud rather than silently clamped to where she already is --
    # "nothing happened" is indistinguishable from "it is broken".
    # Up to the ceiling first -- the dive above brought her back to cruise.
    rt.run(f"TREK.Flight.climb({P})")
    net.pump(120)
    before = ship(rt, "level")
    check(before == rt.eval("TREK.Config.FlightMaxLevel"),
          f"flight: expected her at the ceiling, she is at {before}")
    rt.run(f"TREK.Flight.climb({P})")
    net.pump(60)
    check(ship(rt, "level") == before,
          "flight: she climbed past the ceiling")
    check(any("IGUI_TREK_CeilingReached" in n for n in rt.notes()),
          "flight: climbing past the ceiling said nothing at all")

    # --- the speed control actually reaches the vehicle --------------------
    # It did not. The steps were multipliers of a base of 30 capped at 42, so
    # the top three all clamped to the same number: the helm moved and the ship
    # did not. Every step must land a different top speed on the vehicle.
    seen = []
    steps = rt.eval("#TREK.Config.FlightSpeedSteps")
    for i in range(1, steps + 1):
        rt.run(f"TREK.Flight.setSpeedStep({P}, {i})")
        net.pump(2)
        seen.append(rt.eval("""(function()
            local v = TREK.Vehicle.ship()
            return v and v:getMaxSpeed() or -1
        end)()"""))
    check(len(set(seen)) == steps,
          f"flight: the helm's speed steps do not all reach the vehicle: {seen}")
    check(seen == sorted(seen),
          f"flight: the speed steps are not in order: {seen}")
    rt.run(f"TREK.Flight.setSpeedStep({P}, {rt.eval('TREK.Config.FlightSpeedDefaultStep')})")

    # --- the hatch is shut while she is up --------------------------------
    before = pos(rt)
    rt.run(f"TREK.Core.exit({P})")
    net.pump(60)
    check(pos(rt) == before,
          "flight: stepping out of the hatch in mid-air was allowed")

    # --- the pilot goes aft, and she stays up -----------------------------
    rt.run(f"""
        local v = TREK.Vehicle.ship()
        v:exit(SIM.players[1])
        local x, y, z = TREK.Util.padSpot()
        -- The cabin was never built in this scenario, so the pad is bare and a
        -- pilot put on it would fall four levels and die of it. Give it a deck
        -- first: the point here is whether the *ship* stays up without a pilot
        -- in the seat, not whether an unbuilt cabin holds anybody.
        SIM.rawSquare(x, y, z):addFloor("floors_interior_tilesandwood_01_1")
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
    # Back at whatever level she is actually flying at, not a guess: the climb
    # above left her one higher than cruise, and standing a level below the
    # ship is a fall.
    # Back to wherever the ship actually is, at whatever level she is actually
    # flying at. She has been driven some way from the take-off point, and
    # standing where she *was* is standing on nothing.
    rt.run("""
        -- From the ship's recorded position, not from the vehicle: standing in
        -- the cabin means the ship's chunks are not loaded here, so
        -- TREK.Vehicle.find cannot see it at all.
        local p = SIM.players[1]
        local s = TREK.Util.state()
        local lvl = s.level or TREK.Config.FlightCruise
        p.x, p.y = s.x + 0.5, s.y + 0.5
        p.z, p.lastZ = lvl, lvl
    """)
    net.pump(70)
    seat(rt)
    net.pump(70)

    # --- beaming out of the cockpit in the air is survivable ---------------
    # It was not. Leaving a seat three levels up drops the character beside a
    # ship that is in the air, and the beam takes ninety ticks, so they spent
    # all of it falling -- arriving hurt, under the ship's own floor, with the
    # screen black. They must be held still until they rematerialise, and land
    # beside her rather than in her shadow.
    rt.run(f"TREK.Transport.beamDown({P})")
    # Watched all the way down. The failure was not the destination, it was the
    # second and a half in between: out of the seat, standing on a small island
    # of invisible floor three levels up, with the engine drawing that level and
    # culling everything below it. Black screen. At no point may the character
    # be out of the seat and off the ground.
    stranded = 0
    for _ in range(200):
        net.pump(1)
        if rt.eval(f"{P}.vehicle") is None and (pos(rt)[2] or 0) > 0:
            stranded += 1
    check(stranded == 0,
          f"flight: the pilot spent {stranded} ticks out of the seat and up in "
          f"the air during the beam; that is the black screen")
    check(rt.eval(f"{P}.dead") is not True,
          "flight: beaming down from the cockpit in flight killed the pilot")
    net.pump(60)
    px, py, pz = pos(rt)
    check(pz == 0,
          f"flight: beamed out of the air and ended at z {pz}, not on the ground")
    sx, sy = ship(rt, "x"), ship(rt, "y")
    check(max(abs(px - sx), abs(py - sy)) >= 2,
          f"flight: beamed down at {px},{py}, right underneath the ship at "
          f"{sx},{sy} -- that is inside her shadow")
    check(ship(rt, "flying") is True,
          "flight: the ship came down when the pilot beamed off her")

    # Back in the seat once more to fly her down.
    rt.run("""
        local p = SIM.players[1]
        local s = TREK.Util.state()
        p.x, p.y = s.x + 0.5, s.y + 0.5
        p.z, p.lastZ = s.level or TREK.Config.FlightCruise, p.z
    """)
    net.pump(40)
    seat(rt)
    net.pump(40)
    rt.run(f"TREK.Flight.land({P})")
    net.pump(200)
    check(ship(rt, "flying") is None, "flight: she would not come down")
    check(ship(rt, "landed") is True, "flight: she came down but is not landed")
    check(shuttles(rt) == 1,
          "flight: landing respawned the vehicle -- the trunk and seats are gone")
    check(rt.eval("TREK.Sky.count()") == 0,
          f"flight: {rt.eval('TREK.Sky.count()')} invisible floors were left in the sky")

    # --- floors left by some older flight get found and lifted -------------
    # The ship's record only remembers the flight it is on. Earlier flights --
    # and earlier builds, which laid a far wider plane -- left their floors in
    # the world, and a floor is a saved world object. They were still there as
    # a black blotch long after the plane itself was down to 25 squares, so the
    # tidy-up must not consult the record: it has to go and look.
    lx, ly = ship(rt, "x"), ship(rt, "y")
    rt.run(f"""
        for dx = -6, 6 do for dy = -6, 6 do
            SIM.rawSquare({lx} + dx, {ly} + dy, 3):addFloor("invisible_01_0")
        end end
    """)
    stray = rt.eval(f"""(function()
        local n = 0
        for dx = -6, 6 do for dy = -6, 6 do
            local sq = SIM.rawSquare({lx} + dx, {ly} + dy, 3)
            if TREK.Util.findSprite(sq, "invisible_01_0") then n = n + 1 end
        end end
        return n
    end)()""")
    check(stray == 169, f"flight: the strays were not planted ({stray})")
    net.pump(1200)
    left = rt.eval(f"""(function()
        local n = 0
        for dx = -6, 6 do for dy = -6, 6 do
            local sq = SIM.rawSquare({lx} + dx, {ly} + dy, 3)
            if TREK.Util.findSprite(sq, "invisible_01_0") then n = n + 1 end
        end end
        return n
    end)()""")
    check(left == 0,
          f"flight: {left} invisible floors from an older flight are still in "
          f"the sky; nothing goes looking for the ones the ship does not "
          f"remember laying")

    # --- and every square it touched was recalculated ----------------------
    # Removing an object with RemoveTileObjectErosionNoRecalc leaves the square
    # holding every conclusion the engine had already drawn from the object
    # being there. Floors lifted that way go on darkening the ground beneath
    # them: the trail of black squares that outlived several attempts to shrink
    # it, while the log insisted thousands of floors had been removed. Vanilla
    # never removes an object without the recalculation pair.
    stale = rt.eval("SIM.staleSquares")
    check(not stale,
          f"flight: {stale} squares had something removed and were never "
          f"recalculated; whatever was lifted will keep darkening the ground")

    for w in rt.warnings():
        fail(f"flight: {w}")
    print("flight: take-off, the sky plane, the shut hatch, the pilot going aft, "
          "the landing and the tidy-up all checked")


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
        local v = TREK.Vehicle.ship()
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


def refit():
    """The 6x9 cabin's fittings do not survive the shrink to 4x6.

    This is the one part of the refit that no static check can reach and that
    only ever runs in a save made before it. clearSurroundings sweeps the
    margin, but U.clearSquare deliberately *keeps* anything the mod tagged --
    so without B.stripLegacyCabin every locker, fridge and bunk of the old
    cabin is left standing, openable, in the black void outside the hull.
    """
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('refit', 1000.5, 1000.5, 0)")
    net.start()
    rt.run("TREK.Transport.beamUp(SIM.players[1])")
    net.pump(180)
    if died(rt, "refit, beaming up"):
        return

    # A stocked locker where the old starboard run used to end: inside the
    # 6x9 extent, outside the 4x6 hull, tagged the way every fitting is.
    rt.run("""
        local C, U = TREK.Config, TREK.Util
        SIM.refitLeftover = { 5, 8 }
        local x, y = U.at(5, 8)
        local sq = SIM.rawSquare(x, y, C.CabinZ)
        local o = SIM.object("furniture_storage_02_11")
        o.square = sq
        o.modData.TREK = "armoury"
        o.container = SIM.container(40)
        o.container.parentObject = o
        o.container:AddItem("Base.Pistol")
        table.insert(sq.objects, o)
        -- and pretend the sweep has not run in this save yet
        U.state().refitRev = nil
    """)

    left = rt.eval("""(function()
        local C, U = TREK.Config, TREK.Util
        local x, y = U.at(5, 8)
        return #SIM.rawSquare(x, y, C.CabinZ).objects
    end)()""")
    check(left >= 1, "refit: the test never planted the old locker")

    # --- a square whose chunk is not loaded is "ask again later" -----------
    # Constraint 1, and the mistake this project has made twice: nil from a
    # square lookup does not mean "nothing there". If the sweep marked itself
    # done while part of the old cabin was still streaming in, whatever was
    # standing there would be left in the void for the life of the save.
    rt.run("""
        local C, U = TREK.Config, TREK.Util
        local hx, hy = U.at(4, 8)
        SIM.realLoaded = SIM.loaded
        SIM.loaded = function(x, y)
            if math.floor(x) == hx and math.floor(y) == hy then return false end
            return SIM.realLoaded(x, y)
        end
    """)
    partial = rt.eval("TREK.Build.refitCabin()")
    check(partial >= 1,
          f"refit: the sweep cleared {partial} fittings it could reach; it "
          f"should still do the squares that are loaded")
    check(ship(rt, "refitRev") is None,
          "refit: the sweep called itself finished while part of the old "
          "cabin was still streaming in")
    rt.run("SIM.loaded = SIM.realLoaded")

    # --- the helm console prop ------------------------------------------
    # A static model that stood in the cabin and did nothing: the helm panel
    # opens from the aboard menu, never from that object. It is a world item,
    # and U.clearSquare leaves world items alone by design -- that is where a
    # player's dropped things live -- so nothing else would ever take it away.
    # One inside the new hull (where revision 16 put it) and one outside
    # (where it stood before the refit).
    rt.run("""
        local C, U = TREK.Config, TREK.Util
        for _, at in ipairs({ { 2, 1 }, { 3, 7 } }) do
            local x, y = U.at(at[1], at[2])
            SIM.rawSquare(x, y, C.CabinZ):AddWorldInventoryItem(C.LegacyHelmItem)
        end
        U.state().refitRev = nil
    """)
    rt.eval("TREK.Build.refitCabin()")
    props = rt.eval("""(function()
        local C, U = TREK.Config, TREK.Util
        local n = 0
        for ox = 0, C.LegacyCabin.w do for oy = 0, C.LegacyCabin.l do
            local x, y = U.at(ox, oy)
            for _, w in ipairs(SIM.rawSquare(x, y, C.CabinZ).worldObjects or {}) do
                local it = w.item
                local id = it and (it.fullType or it:getFullType())
                if id == C.LegacyHelmItem then n = n + 1 end
            end
        end end
        return n
    end)()""")
    check(props == 0,
          f"refit: {props} helm console props are still standing in the cabin")

    # Plant it again -- the reachable one was cleared by the partial pass.
    rt.run("""
        local C, U = TREK.Config, TREK.Util
        U.state().refitRev = nil
        local x, y = U.at(5, 8)
        local sq = SIM.rawSquare(x, y, C.CabinZ)
        local o = SIM.object("furniture_storage_02_11")
        o.square = sq
        o.modData.TREK = "armoury"
        o.container = SIM.container(40)
        o.container.parentObject = o
        o.container:AddItem("Base.Pistol")
        table.insert(sq.objects, o)
    """)

    removed = rt.eval("TREK.Build.refitCabin()")
    check(removed >= 1, f"refit: the sweep removed {removed} old fittings, not 1")

    still_there = rt.eval("""(function()
        local C, U = TREK.Config, TREK.Util
        local x, y = U.at(5, 8)
        for _, o in ipairs(SIM.rawSquare(x, y, C.CabinZ).objects) do
            local md = o.modData
            if md and md.TREK then return true end
        end
        return false
    end)()""")
    check(still_there is False,
          "refit: a tagged fitting from the old cabin is still standing "
          "outside the hull")

    # What was in it is the player's, so it is on the deck, not deleted.
    on_pad = rt.eval("""(function()
        local C, U = TREK.Config, TREK.Util
        local x, y = U.at(C.Landing.x, C.Landing.y)
        local sq = SIM.rawSquare(x, y, C.CabinZ)
        local n = 0
        for _, w in ipairs(sq.worldObjects or {}) do
            local id = w.item and (w.item.fullType or w.item:getFullType())
            if id == "Base.Pistol" then n = n + 1 end
        end
        return n
    end)()""")
    check(on_pad >= 1,
          "refit: the old locker's contents were destroyed rather than "
          "spilled onto the pad")

    # --- the counter the replicator used to stand on ------------------------
    # For two revisions the machine was a model hanging over a steel counter,
    # and what it made went into that counter. The counter is gone from the
    # layout, so **nothing that walks the new one ever visits it** -- it has to
    # be named, exactly like the helm prop. And what a player left in it is
    # theirs, so it goes onto the pad rather than into nothing.
    rt.run("""
        local C, U, R = TREK.Config, TREK.Util, TREK.Replicator
        local ox, oy = R.spot()
        local x, y = U.at(ox, oy)
        local sq = SIM.rawSquare(x, y, C.CabinZ)
        local o = SIM.object("fixtures_counters_01_35")
        o.square = sq
        o.modData.TREK = C.LegacyReplicatorTag
        o.container = SIM.container(40)
        o.container.parentObject = o
        o.container:AddItem("Base.Hammer")
        table.insert(sq.objects, o)
        U.state().refitRev = nil
    """)
    rt.eval("TREK.Build.refitCabin()")
    left = rt.eval("""(function()
        local C, U, R = TREK.Config, TREK.Util, TREK.Replicator
        local ox, oy = R.spot()
        local x, y = U.at(ox, oy)
        local n = 0
        for _, o in ipairs(SIM.rawSquare(x, y, C.CabinZ).objects) do
            if o.modData and o.modData.TREK == C.LegacyReplicatorTag then
                n = n + 1
            end
        end
        return n
    end)()""")
    check(left == 0,
          f"refit: {left} of the old replicator counters are still standing on "
          f"the machine's square, which would be drawn straight through it")
    hammers = rt.eval("""(function()
        local C, U = TREK.Config, TREK.Util
        local x, y = U.at(C.Landing.x, C.Landing.y)
        local n = 0
        for _, w in ipairs(SIM.rawSquare(x, y, C.CabinZ).worldObjects or {}) do
            local id = w.item and (w.item.fullType or w.item:getFullType())
            if id == "Base.Hammer" then n = n + 1 end
        end
        return n
    end)()""")
    check(hammers >= 1,
          "refit: what was in the old replicator counter was destroyed rather "
          "than spilled onto the pad")

    # It only claims to be done when it reached everything, and it does not
    # run twice.
    check(ship(rt, "refitRev") == rt.eval("TREK.Config.BuildRev"),
          "refit: the sweep finished without marking itself done")
    check(rt.eval("TREK.Build.refitCabin()") == 0,
          "refit: the sweep ran a second time")

    # And it left the ship alone. The sweep walks the old extent, which
    # overlaps the new hull completely, so an exemption that stopped working
    # would delete the cabin's own lockers and their stock -- silently, and
    # only in somebody's existing save.
    containers, stocked, _, wanted = cabin_objects(rt)
    # Eight, not nine: the replicator's berth was a ninth until the machine
    # replaced the counter it used to stand on.
    check(containers == 8 and stocked == wanted,
          f"refit: the sweep ate the new cabin -- {containers} containers "
          f"left, {stocked} of {wanted} still stocked")

    for w in rt.warnings():
        fail(f"refit: {w}")
    print("refit: the old cabin's fittings and the helm prop are removed, "
          "their contents spilled onto the pad, and the new cabin untouched")


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
    check(sc[3] >= 3 and sc[1] == sc[3],
          f"multiplayer: server stocked {sc[1]} of the {sc[3]} containers "
          f"the layout asks for")
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

    # -----------------------------------------------------------------------
    # Flight, with two people
    # -----------------------------------------------------------------------
    # The sky plane is laid by each client for itself and never crosses the
    # network: the server runs no vehicle physics and needs no floor, the
    # driver's machine needs one to drive on, and every machine needs one to
    # draw her in the air. They agree because they all derive it from the same
    # synced vehicle position. That is the whole argument, and none of it was
    # exercised until this scenario existed.
    lx, ly = ship(srv, "x"), ship(srv, "y")
    # Both of them over to the ship, and a moment for her ground to stream in
    # on each machine: a client that cannot see the vehicle cannot pave under
    # it, which is the whole thing being tested.
    for rt in net.all():
        rt.run(f"""
            for _, p in ipairs(SIM.players) do
                p.x, p.y, p.z, p.lastZ = {lx} + 4.5, {ly} + 4.5, 0, 0
            end
        """)
    net.pump(120)
    for rt in net.all():
        rt.run(f"""
            local v = TREK.Vehicle.ship()
            if v then v.seats[0] = SIM.players[1] SIM.players[1].vehicle = v end
        """)
    A.run(f"TREK.Flight.takeOff({P})")
    net.pump(400)

    check(ship(srv, "flying") is True,
          "multiplayer: she never got off the ground")
    check(ship(srv, "pilot") == "alice",
          f"multiplayer: the server thinks {ship(srv, 'pilot')} is flying her")

    # Both machines must show her in the air. Bob is not the pilot and never
    # lifts anything; his client pave the floor under her from the position the
    # engine syncs him, and derives the same level from it.
    for name, c in (("alice", A), ("bob", B)):
        z = c.eval("""(function()
            local v = TREK.Vehicle.ship()
            return v and v:getZ() or -1
        end)()""")
        check(z == srv.eval("TREK.Config.FlightCruise"),
              f"multiplayer: {name} sees the shuttle at z {z}, not in the air")
        held = c.eval("TREK.Sky.count()")
        check(held and held > 0,
              f"multiplayer: {name} laid no sky plane, so she is on the ground "
              f"on that screen")

    # And the plane is still the only world edit a client is allowed.
    for name, c in (("alice", A), ("bob", B)):
        check(c.eval("SIM.clientWorldEdit") is None,
              f"multiplayer: {name} edited the world for something other than "
              f"the sky plane")

    # The speed is the ship's, not the pilot's. Bob sets it at the helm and
    # Alice is the one flying: her vehicle must be the one that changes.
    B.run(f"TREK.Flight.setSpeedStep({P}, 6)")
    net.pump(20)
    check(ship(srv, "speed") == 6,
          f"multiplayer: the server did not take the new speed ({ship(srv, 'speed')})")
    top = A.eval("""(function()
        local v = TREK.Vehicle.ship()
        return v and v:getMaxSpeed() or -1
    end)()""")
    check(top == srv.eval("TREK.Config.FlightSpeedSteps[6]"),
          f"multiplayer: the pilot's ship is doing {top}, not what the helm was "
          f"set to; speed set by one crewman must reach the one flying")

    # A crewman who is not flying may not steer her about.
    before = ship(srv, "level")
    B.run(f"TREK.Flight.climb({P})")
    net.pump(60)
    check(ship(srv, "level") == before,
          "multiplayer: a passenger changed the ship's altitude")

    # Killing the pilot must bring her down, on the server's own initiative.
    A.run("SIM.players[1].dead = true")
    srv.run("""
        for _, p in ipairs(SIM.players) do
            if p.name == 'alice' then p.dead = true end
        end
        local v = TREK.Vehicle.ship()
        if v then v.seats[0] = nil end
    """)
    net.pump(600)
    check(ship(srv, "flying") is None,
          "multiplayer: flight outlived its pilot on a server")
    check(ship(srv, "pilot") is None,
          "multiplayer: the dead pilot is still recorded at the controls")

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
          "shields, flight seen from both machines and single-writer state "
          "all checked")


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


def torpedoes():
    """Photon torpedoes: who may fire, where, how often, and what it looks like.

    **The load-bearing checks here used to assert the opposite of what they
    assert now**, and that is the most useful thing about this function. They
    required fireChance, fireEnergy and fireRange to be zero, on the reading
    that a burning torpedo was an arson mod. In this engine those three
    settings are the *entire visible half of an explosion* -- there is no
    separate explosion effect -- so what they actually guarded was a weapon
    that killed in silence, and they guarded it successfully for three commits
    while the feature was reported broken from the cockpit.

    So they are inverted, and the fire is now checked all the way through to
    the world: configured non-zero on the trap, and a square that really
    reports haveFire() afterwards. A setting that is passed and then ignored
    looks identical to one that works, which is the mistake this whole project
    keeps paying for.

    The other half is the projectile. A torpedo must be *seen* to cross the
    ground, so the flight is asserted directly: in the air after launch, drawn
    somewhere on the path, gone once it lands, and its light put out.
    """
    P = "SIM.players[1]"
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('pilot', 3000.5, 3000.5, 0)")
    net.start()
    net.pump(5)

    rt.run(f"TREK.Menu.onCallDown(nil, {P}, 3004, 3000, 0)")
    net.pump(40)
    seat(rt)

    C = lambda n: rt.eval(f"TREK.Config.{n}")
    sx, sy = ship(rt, "x"), ship(rt, "y")

    # Far enough out to be a legal shot. Named once, because TorpedoMinRange
    # went from 4 to 12 when the fire was turned on -- the blast plus the fire
    # ring is 10 tiles of ground the pilot must not be standing over -- and
    # every "this should work" shot in this function silently became an
    # out-of-range refusal until they moved with it.
    OK = 18

    def aim(dx, dy):
        """Points the cursor dx,dy squares from the player."""
        rt.run(f"SIM.aim.dx = {dx}; SIM.aim.dy = {dy}")

    def reset():
        """Clears the traps, the fires, the flight and BOTH halves of the cooldown.

        The client keeps its own T.lastFire so it can refuse in the same frame
        the trigger is pulled, and the server keeps s.torpedoAt. Clearing only
        the server's is what made three later checks in this function pass for
        the wrong reason: every shot after the first was being refused by the
        client before it ever became a request, so guards that were supposed
        to be under test were never reached.
        """
        rt.run("SIM.traps = {}")
        rt.run("SIM.burning = {}")
        rt.run("TREK.Torpedo.clearFlight()")
        rt.run("TREK.Util.state().torpedoAt = nil")
        rt.run("TREK.Torpedo.lastFire = 0")

    def fire(dx, dy):
        """Fires the way a player actually does: hold right, click left.

        **Not** by calling the server handler. The first version of this test
        did exactly that, and it passed against a build in which the pilot
        could hold right-click, click left, and get silence -- because arming
        was a radial-menu toggle nobody had been told about. The handler was
        never the part that was broken. Drive the input.

        This now only *launches*: the blast waits for the torpedo to arrive.
        Call arrive() for the detonation.
        """
        aim(dx, dy)
        rt.run("SIM.mouse[1] = true")          # hold right: aiming
        rt.run("SIM.mouse[0] = false")         # left up, so the next press is an edge
        rt.run("TREK.Torpedo.poll()")
        rt.run("SIM.mouse[0] = true")          # click
        rt.run("TREK.Torpedo.poll()")
        net.pump(2)
        rt.run("SIM.mouse[0] = false; SIM.mouse[1] = false")
        rt.run("TREK.Torpedo.poll()")

    def arrive():
        """Runs the clock on until anything in the air has landed.

        The simulated clock moves 16 ms a tick and the longest flight allowed
        is TorpedoMaxFlightMs, so this is that ceiling with room to spare
        rather than a number picked to make today's shot work.
        """
        net.pump(int(C("TorpedoMaxFlightMs") / 16) + 10)

    # --- she will not fire from the ground --------------------------------
    # The blast is centred on the ground, so a shuttle sitting on it would be
    # inside its own explosion.
    reset()
    fire(OK, 0)
    arrive()
    check(rt.eval("#SIM.traps") == 0,
          "torpedoes: she fired while parked on the ground")

    # Get her up.
    rt.run(f"TREK.Flight.takeOff({P})")
    net.pump(400)
    check(ship(rt, "flying") is True, "torpedoes: she never got airborne to fire from")

    # --- the torpedo is visible, and it arrives before it explodes --------
    # This is the half the feature was missing entirely: it killed what was in
    # the blast and nothing was ever seen to happen.
    reset()
    lampsBefore = rt.eval("SIM.lampsLive")
    fire(OK, 0)

    inAir = rt.eval("#TREK.Torpedo.inFlight")
    check(inAir == 1,
          f"torpedoes: {inAir} torpedoes in the air after firing one -- nothing "
          f"is drawn crossing the ground, which is the whole complaint the "
          f"rewrite exists to answer")

    check(rt.eval("#SIM.traps") == 0,
          "torpedoes: it detonated on the frame the trigger was pulled, before "
          "the torpedo had gone anywhere -- the explosion must wait for it to "
          "arrive or the effect precedes its own cause")

    # It carries a light, so it reads at night. That light is the one part of
    # this feature that touches the world, so it is the one part that can be
    # left behind.
    net.pump(4)
    lit = rt.eval("SIM.lampsLive")
    check(lit > lampsBefore,
          "torpedoes: the torpedo in flight carries no light -- at night it is "
          "invisible, which is most of when it matters")

    # --- it lands, and the blast is configured to be seen -----------------
    arrive()
    built = rt.eval("#SIM.traps") == 1
    check(built,
          "torpedoes: holding right mouse and clicking left built no trap -- "
          "the pilot has no way to fire, which is exactly how this shipped "
          "broken the first time")

    check(rt.eval("#TREK.Torpedo.inFlight") == 0,
          "torpedoes: the torpedo is still being drawn after it landed")
    check(rt.eval("SIM.lampsLive") == lampsBefore,
          "torpedoes: the flight light was never put out -- a light is a world "
          "object and this is how a projectile strands something behind it")

    # Guarded, because everything below reads the trap. Without this the
    # run dies on a nil index and the real failure above never gets printed --
    # a test that cannot report its own finding is half a test.
    if built:
        check(rt.eval("SIM.lastTrap().fired") is True,
              "torpedoes: the trap was built but never triggered")

        # --- THE one that matters, and it used to assert the opposite -----
        # Each of these was required to be 0. In this engine the visible part
        # of an explosion IS the fire and the smoke: triggerExplosion() skips
        # the Fire and Smoke passes whose range is <= 0, and the Explosion pass
        # gates Burn() and StartFire on getFireStartingChance() per square. At
        # zero the torpedo kills in silence -- which is what was shipped, and
        # what these checks were holding in place.
        for field, cfg, why in (
            ("fireChance", "TorpedoFireChance",
             "IsoGridSquare.Burn() and IsoFireManager.StartFire are both gated "
             "on this per square; at zero the blast is invisible and harms no "
             "building"),
            ("fireEnergy", "TorpedoFireEnergy",
             "the energy handed to StartFire; at zero the fire has nothing to "
             "burn with"),
            ("fireRange", "TorpedoFireRange",
             "triggerExplosion() skips the Fire pass entirely when this is <= 0"),
            ("smokeRange", "TorpedoSmokeRange",
             "triggerExplosion() skips the Smoke pass entirely when this is <= 0"),
        ):
            got = rt.eval(f"SIM.lastTrap().{field}")
            want = C(cfg)
            check(got == want,
                  f"torpedoes: trap {field} is {got}, not {want} -- {why}")
            check(got > 0,
                  f"torpedoes: trap {field} is {got} -- {why}")

        check(rt.eval("SIM.lastTrap().power") == C("TorpedoPower"),
              "torpedoes: the trap was not given the configured explosion power")
        check(rt.eval("SIM.lastTrap().range") == C("TorpedoRange"),
              "torpedoes: the trap was not given the configured blast radius")

        # ...and the fire reached the world, rather than being configured and
        # then ignored. A setting that is passed and dropped looks exactly like
        # one that works, which is this project's most expensive failure shape.
        tx, ty = int(sx) + OK, int(sy)
        check(rt.eval(f"SIM.isBurning({tx}, {ty}, 0) and 1 or 0") == 1,
              f"torpedoes: nothing is burning at {tx},{ty} after a direct hit "
              f"-- the fire settings are on the trap but no fire reached the "
              f"ground")

    # --- the cooldown is real ---------------------------------------------
    # Traps only: clearing the cooldown here would be clearing the thing
    # under test.
    rt.run("SIM.traps = {}")
    fire(OK, 0)
    arrive()
    check(rt.eval("#SIM.traps") == 0,
          "torpedoes: a second shot fired immediately -- the cooldown does nothing")

    # --- range bounds, both ends ------------------------------------------
    # The ceiling is asserted as a flat number as well as enforced, and that
    # is deliberate. Firing at "TorpedoMaxRange + 6" only ever proves the
    # comparison runs: raise the constant to 9999 and the shot moves out with
    # it and the check still passes, which is exactly what the first version
    # of this did. A bound that is enforced but enormous is not a bound, so
    # the sane ceiling is named here where a mutation cannot follow it.
    check(int(C("TorpedoMaxRange")) <= 64,
          f"torpedoes: TorpedoMaxRange is {C('TorpedoMaxRange')} -- enforced, "
          f"but far enough to shell most of the map from the air")
    reset()
    fire(int(C("TorpedoMaxRange")) + 6, 0)
    arrive()
    check(rt.eval("#SIM.traps") == 0,
          "torpedoes: a shot beyond TorpedoMaxRange was allowed -- a crafted "
          "command is a map-wide mortar")
    reset()
    fire(1, 0)
    arrive()
    check(rt.eval("#SIM.traps") == 0,
          "torpedoes: a shot inside TorpedoMinRange was allowed -- she would "
          "be inside her own blast")

    # The close bound is asserted as a flat number too, and for a sharper
    # reason than the far one: it is what keeps the ship out of the fire she
    # just started. The blast reaches TorpedoRange and the fire ring reaches
    # TorpedoRange + TorpedoFireRange, so anything at or inside that is a
    # pilot lighting the ground they are about to land on.
    reach = int(C("TorpedoRange")) + int(C("TorpedoFireRange"))
    check(int(C("TorpedoMinRange")) > reach,
          f"torpedoes: TorpedoMinRange is {C('TorpedoMinRange')} but a torpedo "
          f"sets fire out to {reach} tiles -- the pilot can drop one inside "
          f"her own fire ring")

    # --- a passenger is not a gunner --------------------------------------
    reset()
    rt.run(f"""
        local v = TREK.Vehicle.ship()
        v.seats[0] = nil
        v.seats[1] = SIM.players[1]
    """)
    fire(OK, 0)
    arrive()
    check(rt.eval("#SIM.traps") == 0,
          "torpedoes: someone who is not in the driver's seat fired them")

    # --- left click alone, with no right button held, must do nothing ------
    # Aiming *is* the right mouse button. Without this, an ordinary left click
    # while flying -- which is most clicks -- would launch a torpedo.
    rt.run(f"""
        local v = TREK.Vehicle.ship()
        v.seats[1] = nil
        v.seats[0] = SIM.players[1]
    """)
    reset()
    aim(OK, 0)
    rt.run("SIM.mouse[1] = false; SIM.mouse[0] = false")
    rt.run("TREK.Torpedo.poll()")
    rt.run("SIM.mouse[0] = true")
    rt.run("TREK.Torpedo.poll()")
    arrive()
    check(rt.eval("#SIM.traps") == 0,
          "torpedoes: a bare left click fired one -- right mouse is supposed "
          "to be what arms the shot")

    # --- holding left down must not fire every frame -----------------------
    # The cooldown is taken out of the way first, and that is the point of the
    # block. With it in place this check passes whether or not the click is
    # taken on an edge, because the cooldown refuses the repeats -- so it was
    # testing the cooldown twice and the edge never. What a missing edge
    # actually costs is a fire attempt every frame the button is held: bounded
    # damage, unbounded noise, and a log nobody can read.
    cooldown = C("TorpedoCooldownMs")
    rt.run("TREK.Config.TorpedoCooldownMs = 0")
    reset()
    aim(OK, 0)
    rt.run("SIM.mouse[1] = true; SIM.mouse[0] = false")
    rt.run("TREK.Torpedo.poll()")
    rt.run("SIM.mouse[0] = true")
    for _ in range(8):
        rt.run("TREK.Torpedo.poll()")
    arrive()
    held = rt.eval("#SIM.traps")
    rt.run(f"TREK.Config.TorpedoCooldownMs = {cooldown}")
    check(held == 1,
          f"torpedoes: holding the button down fired {held} of them -- the "
          f"click is not being taken on the edge, and only the cooldown is "
          f"standing between the pilot and one torpedo per frame")

    # --- the controller ----------------------------------------------------
    # Every panel in this mod is required to work with a gamepad, and for
    # three commits this one did not: aimPoint() kept a virtual cursor for a
    # joypad and nothing moved it, so on a Steam Deck the reticle sat in the
    # centre of the screen for ever. The checks below are the ones that would
    # have caught that, and they are driven through the same T.poll() a real
    # frame calls -- not by poking the aim point directly, which would prove
    # only that the variable is writable.
    reset()
    # The block above leaves the mouse buttons held. Clear them, or "the
    # reticle is up without a hold" below passes because a hold is in effect.
    rt.run("SIM.mouse[0] = false; SIM.mouse[1] = false")
    rt.run("SIM.setJoypad(true)")
    rt.run("TREK.Torpedo.aimX, TREK.Torpedo.aimY = nil, nil")
    rt.run("TREK.Torpedo.poll()")
    startX = rt.eval("TREK.Torpedo.aimX")
    check(startX is not None and startX > 0,
          "torpedoes: with a controller and no mouse the reticle has no "
          "position at all -- a pad has no pointer to inherit one from, so it "
          "must be centred on first use")

    # The stick moves it.
    rt.run("SIM.joypadAim.x = 1.0; SIM.joypadAim.y = 0")
    for _ in range(5):
        rt.run("TREK.Torpedo.poll()")
    movedX = rt.eval("TREK.Torpedo.aimX")
    check(movedX > startX,
          f"torpedoes: the right stick does not move the reticle "
          f"({startX} -> {movedX}) -- this is the Steam Deck bug the roadmap "
          f"carried for three commits")

    # ...and only while the stick is pushed. A reticle that keeps drifting
    # when nobody is touching the pad reads as a bug, and a squared-off dead
    # zone is how that happens.
    rt.run("SIM.joypadAim.x = 0.05; SIM.joypadAim.y = 0.05")   # inside the dead zone
    held = rt.eval("TREK.Torpedo.aimX")
    for _ in range(10):
        rt.run("TREK.Torpedo.poll()")
    check(rt.eval("TREK.Torpedo.aimX") == held,
          "torpedoes: the reticle drifts with the stick inside its dead zone")

    # It cannot be pushed off the screen.
    rt.run("SIM.joypadAim.x = 1.0; SIM.joypadAim.y = 1.0")
    for _ in range(400):
        rt.run("TREK.Torpedo.poll()")
    # The screen bounds are flat numbers here, not `w - C("TorpedoAimMargin")`,
    # and that is deliberate for the reason the range ceiling is: a check
    # written against the constant it is testing moves with it. Setting the
    # margin to -100000 left this passing, because the assertion had followed
    # the mutation out past the edge of the screen.
    w, h = 1920, 1080                      # SIM's screen
    ax, ay = rt.eval("TREK.Torpedo.aimX"), rt.eval("TREK.Torpedo.aimY")
    check(0 <= ax <= w and 0 <= ay <= h,
          f"torpedoes: the reticle was pushed to {ax},{ay}, off a {w}x{h} "
          f"screen -- screenToIso is then being asked about a point the "
          f"camera is not showing at all")
    margin = C("TorpedoAimMargin")
    check(0 < margin <= 200,
          f"torpedoes: TorpedoAimMargin is {margin} -- it is applied, but not "
          f"a margin, so the reticle can sit half off the screen")

    # The reticle is up without a hold. A pad has no pointer, so hiding it
    # behind a held button would hide the only thing saying where aim is.
    check(rt.eval("SIM.mouse[1] and 1 or 0") == 0,
          "torpedoes: test bug -- right mouse is still held from the block "
          "above, so the next check cannot tell a controller reticle from a "
          "mouse one")
    check(rt.eval("TREK.Torpedo.aiming() and 1 or 0") == 1,
          "torpedoes: on a controller the reticle is hidden unless a button is "
          "held -- there is no pointer, so that hides the aim point itself")

    # R3 fires, on the edge, and nothing else does.
    reset()
    rt.run("SIM.joypadAim.x = 0; SIM.joypadAim.y = 0")
    rt.run("SIM.joypadR3 = false")
    rt.run("TREK.Torpedo.poll()")
    arrive()
    check(rt.eval("#SIM.traps") == 0,
          "torpedoes: a controller fired one without the stick being clicked")

    reset()
    rt.run("SIM.joypadR3 = true")
    for _ in range(6):
        rt.run("TREK.Torpedo.poll()")
    arrive()
    padShots = rt.eval("#SIM.traps")
    check(padShots == 1,
          f"torpedoes: holding R3 fired {padShots} -- the controller's fire "
          f"is not being taken on the edge the way the mouse's is")

    # A mouse used more recently takes aiming back, even with a pad plugged in.
    # This is the half that would break every desktop player who happens to
    # own a controller: "a joypad exists" is not "a joypad is being used".
    reset()
    rt.run("SIM.joypadR3 = false")
    rt.run("SIM.mouseIsNewer = true")
    rt.run("SIM.mouseX, SIM.mouseY = 1234, 567")
    rt.run("TREK.Torpedo.poll()")
    # aimStatus(), not poll(), is what reads the aim point -- it is on the path
    # the overlay's render takes every frame. poll() only integrates the stick
    # and watches the fire button, and asserting on it alone would be asserting
    # against a code path the game never takes.
    rt.run("TREK.Torpedo.aimStatus()")
    check(rt.eval("TREK.Torpedo.aimX") == 1234,
          "torpedoes: a connected but idle controller still owns the reticle, "
          "so moving the mouse does nothing -- on a desktop with a pad plugged "
          "in, aiming would be dead")
    rt.run("SIM.setJoypad(false)")

    # --- the server owner may have the weapon without the arson -----------
    # The engine already gives an owner ServerOptions.noFire and safehouse
    # protection, both checked inside Burn(). This is the narrower question of
    # whether *this weapon* burns, and it has to leave the kill intact: an
    # option that quietly disarmed the torpedo would be a worse answer than
    # not having one.
    reset()
    rt.run("SandboxVars = SandboxVars or {}")
    rt.run("SandboxVars.TrekShuttle = SandboxVars.TrekShuttle or {}")
    rt.run(f"SandboxVars.TrekShuttle.TorpedoFire = {int(C('TorpedoFireNone'))}")
    fire(OK, 0)
    arrive()
    blastOnly = rt.eval("#SIM.traps") == 1
    check(blastOnly,
          "torpedoes: 'Blast only' stopped the torpedo firing at all -- the "
          "option is meant to remove the fire, not the weapon")
    if blastOnly:
        for field in ("fireChance", "fireEnergy", "fireRange", "smokeRange"):
            got = rt.eval(f"SIM.lastTrap().{field}")
            check(got == 0,
                  f"torpedoes: with TorpedoFire set to 'Blast only', trap "
                  f"{field} is {got} rather than 0 -- the sandbox option does "
                  f"nothing and the server owner's choice is ignored")
        check(rt.eval("SIM.lastTrap().power") == C("TorpedoPower"),
              "torpedoes: 'Blast only' also took the explosion's power away -- "
              "it is meant to keep the blast and drop the fire")

    # And it defaults to the weapon as designed. Reading a missing option as
    # "no fire" is how a feature turns itself off in the one setup nobody
    # tested -- single player, where the sandbox table may not exist at all.
    rt.run("SandboxVars.TrekShuttle.TorpedoFire = nil")
    check(rt.eval("TREK.Server.torpedoesBurn() and 1 or 0") == 1,
          "torpedoes: with no sandbox option set the torpedo does not burn -- "
          "an absent setting must mean the weapon as designed, never a silent "
          "disarm")

    print("torpedoes: the pilot aims with right mouse and fires with left, the "
          "torpedo is drawn crossing the ground with a light on it and "
          "detonates on arrival rather than on the trigger, the blast sets "
          "fire to what it hits, 'Blast only' removes the fire and keeps the "
          "weapon, and the ground, a bare click, a held button, the cooldown, "
          "both range bounds and a passenger are all refused")


def medical():
    """The medical set: the hypospray, the two tricorders, and the lock.

    The load-bearing check in here is the one that asserts a *non*-effect.
    `BodyPart.RestoreToFullHealth()` is the obvious way to mend a limb and its
    bytecode clears `bittenZ` and `biteTimeF` along with everything else, so
    the tidy version of the hypospray cures a bite -- which the design says it
    must never do, because that cure is the EMH's and is the entire reason the
    EMH is worth building. Nothing in the game would report it: the dose would
    simply be better than intended, and the next feature on the roadmap would
    quietly be pointless. So the bite and the zombie infection are checked to
    have survived a dose, every time.

    Everything else here is driven the way a player drives it -- through the
    context menu -- for the reason the torpedo test gives: a build in which
    nobody could reach the feature at all would otherwise pass.
    """
    P = "SIM.players[1]"
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('medic', 1000.5, 1000.5, 0)")
    net.start()
    net.pump(2)

    C = lambda n: rt.eval(f"TREK.Config.{n}")
    HYPO = str(C("HyposprayItem"))
    MEDTRI = str(C("MedTricorderItem"))
    TRI = str(C("TricorderItem"))
    REGEN = str(C("DermalRegenItem"))

    def give(full_id):
        rt.run(f'SIM.players[1].inventory:AddItem(instanceItem("{full_id}"))')

    def inventory_menu():
        """Right-clicks everything in the player's inventory, as the game does."""
        rt.run("""
            medMenu = SIM.contextMenu()
            local items = {}
            for _, it in ipairs(SIM.players[1].inventory.items) do
                table.insert(items, it)
            end
            TREK.MedKit.fillInventoryMenu(0, medMenu, items)
        """)
        return str(rt.eval("medMenu:labels()"))

    def click(menu, label, what):
        """Clicks a menu option, and fails if it was not on the menu.

        A silent miss is how the wasted-dose check below passed against a
        build that really did waste doses: the label carries the number of
        doses left, so a stale menu's option simply is not found and the
        click does nothing at all.
        """
        found = rt.eval(f'{menu}:click("{label}")')
        check(found is True, f"medical: {what} -- no {label!r} option to click")
        return found

    def text(key, *args):
        """An IG_UI string with its %1s filled in, so a test can match a label."""
        arglist = "".join(f', "{a}"' for a in args)
        return str(rt.eval(f'getText("{key}"{arglist})'))

    # --- the ship carries the set, guaranteed ------------------------------
    # **The loot list is emptied of them first**, and that is the whole point of
    # the check. C.Loot.medical happens to carry the three instruments at its
    # head today, so a cabin built with them in the list proves nothing about
    # the guarantee -- it would pass with the `special = "medkit"` rule deleted,
    # and then quietly stop passing the day somebody reorders the list. With
    # them taken out, the only thing that can put a tricorder in that locker is
    # the rule.
    rt.run("""
        local out = {}
        for _, id in ipairs(TREK.Config.Loot.medical) do
            if id ~= TREK.Config.HyposprayItem
               and id ~= TREK.Config.MedTricorderItem
               and id ~= TREK.Config.TricorderItem
               and id ~= TREK.Config.DermalRegenItem then
                table.insert(out, id)
            end
        end
        TREK.Config.Loot.medical = out
    """)
    rt.run(f"TREK.Transport.beamUp({P})")
    net.pump(180)
    if died(rt, "medical, beaming up"):
        return
    aboard = rt.eval("""(function()
        local C, U = TREK.Config, TREK.Util
        local found = {}
        for ox = 0, C.CabinW do for oy = 0, C.CabinL do
            local x, y = U.at(ox, oy)
            for _, o in ipairs(SIM.rawSquare(x, y, C.CabinZ).objects) do
                if o.container then
                    for _, it in ipairs(o.container.items) do
                        found[it.fullType] = (found[it.fullType] or 0) + 1
                    end
                end
            end
        end end
        return (found[TREK.Config.HyposprayItem] or 0)
            .. "," .. (found[TREK.Config.MedTricorderItem] or 0)
            .. "," .. (found[TREK.Config.TricorderItem] or 0)
            .. "," .. (found[TREK.Config.DermalRegenItem] or 0)
    end)()""")
    hypos, medtris, tris, regens = (int(n) for n in str(aboard).split(","))
    check(hypos >= 1 and medtris >= 1 and tris >= 1 and regens >= 1,
          f"medical: a fresh ship carries {hypos} hyposprays, {medtris} medical "
          f"tricorders, {tris} tricorders and {regens} dermal regenerators -- "
          f"the sick-bay locker is meant to hold one of each outright")

    # --- the way in ---------------------------------------------------------
    labels = inventory_menu()
    check(labels == "", f"medical: an empty-handed player is offered {labels!r}")

    give(HYPO)
    give(MEDTRI)
    give(TRI)
    give(REGEN)
    labels = inventory_menu()
    for want, what in ((text("IGUI_TREK_HypoUse", C("HyposprayDoses")), "the hypospray"),
                       (text("IGUI_TREK_MedScanSelf"), "the medical tricorder"),
                       (text("IGUI_TREK_Sweep"), "the tricorder"),
                       (text("IGUI_TREK_SkinUse"), "the dermal regenerator")):
        check(want in labels,
              f"medical: {what} offers no way to use it -- the menu reads {labels!r}")

    # --- a dose, and what it must not touch ---------------------------------
    rt.run("""
        for _, what in ipairs({ "bleeding", "deepWound", "infectedWound", "burn",
                                "fracture", "pain", "stiffness", "health" }) do
            SIM.hurt(SIM.players[1], what, 1)
        end
        SIM.hurt(SIM.players[1], "bite", 2)
        SIM.players[1]:getBodyDamage():setInfected(true)
        SIM.sounds = {}
    """)
    inventory_menu()
    click("medMenu", text("IGUI_TREK_HypoUse", C("HyposprayDoses")), "using a full hypospray")

    left = rt.eval("""(function()
        local it = TREK.Medical.carried(SIM.players[1], TREK.Config.HyposprayType,
                                        TREK.Config.HyposprayItem)[1]
        return TREK.Medical.doses(it)
    end)()""")
    check(left == C("HyposprayDoses") - 1,
          f"medical: a dose left {left} in the hypospray, not "
          f"{C('HyposprayDoses') - 1}")

    healed = rt.eval("""(function()
        local p = SIM.players[1]:getBodyDamage().parts[1]
        return (p.isBleeding or p.isDeepWounded or p.infectedWound
                or p.burnTime > 0 or p.fractureTime > 0 or p.additionalPain > 0
                or p.stiffness > 0 or p.health < 100) and "no" or "yes"
    end)()""")
    check(str(healed) == "yes",
          "medical: a hypospray dose left some of the injuries it treats behind")

    still_bitten = rt.eval("SIM.players[1]:getBodyDamage().parts[2].isBitten")
    still_infected = rt.eval("SIM.players[1]:getBodyDamage():isInfected()")
    check(still_bitten is True,
          "medical: the hypospray cured a BITE. It must not -- that cure is the "
          "EMH's, and BodyPart.RestoreToFullHealth() clears bittenZ, which is "
          "exactly why this file never calls it")
    check(still_infected is True,
          "medical: the hypospray cleared the zombie infection. "
          "BodyDamage.setInfected is the virus; BodyPart.setInfectedWound is an "
          "ordinary infected cut, and only the second one is the hypospray's")
    check(rt.eval('SIM.heardSound("TREK_HypoHiss")') is True,
          "medical: a dose was administered in complete silence")

    # --- a dose is never wasted ---------------------------------------------
    rt.run("SIM.notes = {}")
    inventory_menu()
    click("medMenu", text("IGUI_TREK_HypoUse", C("HyposprayDoses") - 1),
          "using a hypospray on a healthy player")
    left_after = rt.eval("""(function()
        local it = TREK.Medical.carried(SIM.players[1], TREK.Config.HyposprayType,
                                        TREK.Config.HyposprayItem)[1]
        return TREK.Medical.doses(it)
    end)()""")
    check(left_after == left,
          f"medical: a hypospray spent a dose on a healthy player ({left} -> "
          f"{left_after})")

    # --- an empty one is offered, and refuses --------------------------------
    rt.run("""
        local it = TREK.Medical.carried(SIM.players[1], TREK.Config.HyposprayType,
                                        TREK.Config.HyposprayItem)[1]
        TREK.Medical.setDoses(it, 0)
        SIM.hurt(SIM.players[1], "bleeding", 3)
    """)
    labels = inventory_menu()
    check(text("IGUI_TREK_HypoUse", 0) in labels,
          "medical: an empty hypospray vanishes from the menu -- a player has "
          "to be able to see that it is empty rather than broken")
    click("medMenu", text("IGUI_TREK_HypoUse", 0), "using an empty hypospray")
    check(rt.eval("SIM.players[1]:getBodyDamage().parts[3].isBleeding") is True,
          "medical: an empty hypospray still treated somebody")

    # --- the ship refills it, and only the ship ------------------------------
    # Aboard, because the ship replicates them. In the field a dose spent is a
    # dose gone, which is the only real limit on the item.
    rt.run(f"TREK.MedKit.serviceRefill({P})")
    aboard_refill = rt.eval("""(function()
        local it = TREK.Medical.carried(SIM.players[1], TREK.Config.HyposprayType,
                                        TREK.Config.HyposprayItem)[1]
        return TREK.Medical.doses(it)
    end)()""")
    check(aboard_refill == 1,
          f"medical: standing aboard, the ship put {aboard_refill} doses back "
          f"rather than 1")

    rt.run(f"TREK.Util.teleport({P}, 1000, 1000, 0)")
    net.pump(4)
    rt.run(f"TREK.MedKit.serviceRefill({P})")
    field_refill = rt.eval("""(function()
        local it = TREK.Medical.carried(SIM.players[1], TREK.Config.HyposprayType,
                                        TREK.Config.HyposprayItem)[1]
        return TREK.Medical.doses(it)
    end)()""")
    check(field_refill == aboard_refill,
          "medical: a hypospray refilled itself out in the field -- the dose "
          "limit is then a delay rather than a decision")

    # --- the dermal regenerator ---------------------------------------------
    # The half that makes it its own instrument is the lacerations, scratches,
    # stitches and dressing; it shares deep wounds, bleeding and burns with the
    # hypospray on purpose. What it must NOT do is the injected half -- an
    # infected cut, pain, stiffness, a fracture -- because that is the only
    # thing stopping a free, unlimited item from making the hypospray pointless.
    rt.run("""
        local p = SIM.players[1]
        for _, what in ipairs({ "cut", "scratch", "deepWound", "bleeding",
                                "burn", "stitches", "bandage", "health" }) do
            SIM.hurt(p, what, 5)
        end
        for _, what in ipairs({ "infectedWound", "pain", "stiffness", "fracture" }) do
            SIM.hurt(p, what, 5)
        end
        SIM.hurt(p, "bite", 6)
        SIM.hurt(p, "bandage", 6)
        p:getBodyDamage():setInfected(true)
        SIM.sounds = {}
    """)
    inventory_menu()
    click("medMenu", text("IGUI_TREK_SkinUse"), "running the dermal regenerator")

    closed = rt.eval("""(function()
        local p = SIM.players[1]:getBodyDamage().parts[5]
        return (p.cut or p.isScratched or p.isDeepWounded or p.isBleeding
                or p.burnTime > 0 or p.isStitched or p.isBandaged
                or p.health < 100) and "no" or "yes"
    end)()""")
    check(str(closed) == "yes",
          "medical: the dermal regenerator left an open wound, a stitch or a "
          "dressing behind")

    kept = rt.eval("""(function()
        local p = SIM.players[1]:getBodyDamage().parts[5]
        local out = {}
        if not p.infectedWound then table.insert(out, "infected cut") end
        if p.additionalPain == 0 then table.insert(out, "pain") end
        if p.stiffness == 0 then table.insert(out, "stiffness") end
        if p.fractureTime == 0 then table.insert(out, "fracture") end
        return table.concat(out, ", ")
    end)()""")
    check(str(kept) == "",
          f"medical: the dermal regenerator treated {kept} -- that is the "
          f"hypospray's half, and it is the only thing keeping a free "
          f"unlimited item from making the hypospray pointless")

    check(rt.eval("SIM.players[1]:getBodyDamage().parts[6].isBitten") is True,
          "medical: the dermal regenerator cured a BITE")
    check(rt.eval("SIM.players[1]:getBodyDamage():isInfected()") is True,
          "medical: the dermal regenerator cleared the zombie infection")
    check(rt.eval("SIM.players[1]:getBodyDamage().parts[6].isBandaged") is True,
          "medical: the dermal regenerator stripped the dressing off a BITTEN "
          "limb. It cannot cure the bite, so taking the bandage off one is "
          "worse than doing nothing")
    check(rt.eval('SIM.heardSound("TREK_DermalHum")') is True,
          "medical: the regenerator ran in silence")

    # --- it will not close over glass ---------------------------------------
    # Two wounds, one of them full of glass, because that is the case the code
    # actually has to get right: the pass must heal what it can, skip what it
    # cannot, and say so. Testing a lone glassed wound instead proves much
    # less -- the whole pass is then refused up front and the "some healed,
    # one did not" branch is never reached at all.
    rt.run("""
        local p = SIM.players[1]
        SIM.hurt(p, "cut", 7)
        SIM.hurt(p, "glass", 7)
        SIM.hurt(p, "cut", 8)
        SIM.notes = {}
    """)
    inventory_menu()
    click("medMenu", text("IGUI_TREK_SkinUse"), "regenerating over glass")
    check(rt.eval("SIM.players[1]:getBodyDamage().parts[7].cut") is True,
          "medical: the regenerator sealed a wound with glass still in it. "
          "Skin does not close over a shard, and a mod that does it is making "
          "things quietly worse while reporting success")
    check(rt.eval("SIM.players[1]:getBodyDamage().parts[8].cut") is False,
          "medical: one obstructed wound stopped it treating the others -- it "
          "is meant to skip that site, not give up")
    # The simulated getText hands back the key, so this matches the key. The
    # English behind it is checked by tests/test_assets.py, which fails on any
    # IGUI_TREK_ literal the Lua asks for and IG_UI.json does not have.
    check(any("IGUI_TREK_SkinObstructed" in n for n in rt.notes()),
          "medical: a wound it refused to close was never mentioned -- a limb "
          "that silently does not heal reads as a broken mod")

    # --- refused outright when the only wound is obstructed ------------------
    rt.run("SIM.notes = {}")
    inventory_menu()
    click("medMenu", text("IGUI_TREK_SkinUse"), "regenerating with nothing else to do")
    check(any("IGUI_TREK_SkinObstructed" in n for n in rt.notes()),
          "medical: with the only remaining wound full of glass, the player is "
          "told there is nothing wrong with them rather than what is in the way")

    # --- and it is free, for ever -------------------------------------------
    rt.run("""
        local p = SIM.players[1]
        p:getBodyDamage().parts[7].glass = false
        SIM.hurt(p, "cut", 9)
    """)
    inventory_menu()
    click("medMenu", text("IGUI_TREK_SkinUse"), "regenerating a third time")
    check(rt.eval("SIM.players[1]:getBodyDamage().parts[9].cut") is False
          and rt.eval("SIM.players[1]:getBodyDamage().parts[7].cut") is False,
          "medical: the dermal regenerator stopped working after a use or two "
          "-- it has no charges by design; the hypospray owns that economy")

    # --- the medical tricorder: one field, and not the debug global ---------
    rt.run("SIM.healthPanels = {}")
    inventory_menu()
    click("medMenu", text("IGUI_TREK_MedScanSelf"), "scanning yourself")
    panel = rt.eval("SIM.lastHealthPanel() ~= nil")
    check(panel is True, "medical: the medical tricorder opened no panel at all")
    if panel:
        level = rt.eval("SIM.lastHealthPanel().doctorLevel")
        check(level == C("MedDoctorLevel"),
              f"medical: the health panel reports at doctor level {level}, not "
              f"{C('MedDoctorLevel')} -- every readout in ISHealthPanel is gated "
              f"on that field")
        check(rt.eval("SIM.lastHealthPanel().window.onScreen") is True,
              "medical: the medical tricorder's panel was never added to the UI")
    check(rt.eval("ISHealthPanel.cheat") is False,
          "medical: something set ISHealthPanel.cheat. It is `false or "
          "getDebug()` in vanilla and otherwise admin-only, so it works for "
          "this developer and for nobody on the Workshop")

    # --- the sensor sweep: sliced, and honest about range --------------------
    rt.run("""
        SIM.zombies = {}
        for i = 1, 40 do SIM.zombie(1003.5 + (i % 3), 1000.5, 0) end   -- close
        for i = 1, 10 do SIM.zombie(1000.5, 1020.5, 0) end             -- middle
        for i = 1, 5 do SIM.zombie(1035.5, 1000.5, 0) end              -- far
        SIM.zombie(1500.5, 1000.5, 0)                                  -- out of range
        SIM.zombie(1003.5, 1000.5, 1)                                  -- another floor
        SIM.sounds = {}
    """)
    # Far more zombies than one slice can classify, all of them out of range
    # so the counts below are unchanged: what is under test here is the
    # slicing, and a horde is exactly when it matters.
    crowd = 400
    rt.run(f"for i = 1, {crowd} do SIM.zombie(1500.5 + i, 1000.5, 0) end")
    check(int(C("SweepPerTick")) < crowd,
          f"medical: C.SweepPerTick is {C('SweepPerTick')}, which is more than "
          f"the {crowd} contacts this check puts in front of it -- the slicing "
          f"below would then pass without any slicing happening")

    rt.run(f"TREK.MedKit.startSweep({P})")
    still = rt.eval("TREK.MedKit.serviceSweep()")
    check(still is True,
          f"medical: one slice classified all {crowd + 57} contacts. The sweep "
          f"is meant to do C.SweepPerTick of them a tick -- a pass that touches "
          f"a horde in one frame is not slow, it is the hard lock in "
          f"DEV_GUIDE.md under 'Slice any search'")
    slices = 1
    while rt.eval("TREK.MedKit.sweeping()") and slices < 200:
        rt.run("TREK.MedKit.serviceSweep()")
        slices = slices + 1
    check(slices >= 3,
          f"medical: the sweep took {slices} slices for {crowd + 57} contacts")
    check(rt.eval("TREK.MedKit.sweeping()") is False,
          "medical: the sweep never finished")
    total = rt.eval("TREK.MedKit.lastSweep.total")
    counts = [int(rt.eval(f"TREK.MedKit.lastSweep.counts[{i}]")) for i in (1, 2, 3)]
    check(total == 55,
          f"medical: the sweep found {total} contacts, not the 55 in range "
          f"(the one 500 tiles away and the one a floor up are not contacts)")
    check(counts[0] == 40 and counts[1] == 10 and counts[2] == 5,
          f"medical: the sweep sorted its contacts {counts}, not [40, 10, 5] -- "
          f"the range bands are what the readout is")
    check(rt.eval('SIM.heardSound("TREK_TricorderChirp")') is True,
          "medical: the tricorder swept in silence")

    # A sweep of three zombies finishes inside one tick, so "one at a time" is
    # not a limit on its own: the button could be held down and would chirp
    # every frame. C.SweepIntervalMs is the half that makes it an instrument.
    check(rt.eval(f"TREK.MedKit.startSweep({P})") is False,
          "medical: a second sweep started immediately after the first -- "
          "C.SweepIntervalMs is doing nothing")
    net.clock += int(C("SweepIntervalMs")) + 100
    check(rt.eval(f"TREK.MedKit.startSweep({P})") is True,
          "medical: the tricorder never recovers -- a sweep is refused even "
          "after the interval has passed")
    for _ in range(40):
        rt.run("TREK.MedKit.serviceSweep()")

    # --- the lock: the client asks, the server opens ------------------------
    # Pumped rather than nudged: the simulation streams chunks at the rate the
    # engine does, and a square whose chunk has not arrived is "cannot tell
    # yet" rather than "nothing there" -- which the server correctly refuses.
    rt.run(f"TREK.Util.teleport({P}, 1200, 1200, 0)")
    net.pump(60)
    rt.run('door = SIM.lock(1201, 1200, 0, "IsoDoor")')
    net.pump(2)

    def cooled():
        """Runs the clock past the override cooldown.

        Without this the next three refusals all pass for the wrong reason:
        the cooldown from the successful override above is still running, so
        a safehouse check, a range check and a padlock check that had all been
        deleted would still look like they were working.
        """
        net.clock += int(C("UnlockCooldownMs")) + 1000

    def world_menu():
        rt.run("""
            lockMenu = SIM.contextMenu()
            TREK.MedKit.fillWorldMenu(0, lockMenu, { door }, false)
        """)
        return str(rt.eval("lockMenu:labels()"))

    check(text("IGUI_TREK_Override") in world_menu(),
          "medical: a tricorder in your pocket offers no way to open a locked door")

    rt.run("SIM.synced = {}")
    rt.run(f'lockMenu:click("{text("IGUI_TREK_Override")}")')
    net.pump(4)
    check(rt.eval("door:isLocked()") is False,
          "medical: the override left the door locked")
    check(rt.eval("#SIM.synced") >= 1,
          "medical: the lock was opened and never synced. setLockedByKey only "
          "fires its own sync when NOT on a server, so a door opened by the "
          "authority stays shut on every client's screen without an explicit "
          "obj:sync()")

    # --- what it will not open ----------------------------------------------
    rt.run('padlocked = SIM.lock(1202, 1200, 0, "IsoThumpable", { padlock = true })')
    rt.run(f"TREK.Util.teleport({P}, 1202, 1201, 0)")
    net.pump(4)
    rt.run("TREK.Util.state().unlockAt = nil")
    rt.run("""
        padMenu = SIM.contextMenu()
        TREK.MedKit.fillWorldMenu(0, padMenu, { padlocked }, false)
    """)
    option = rt.eval(
        '(function() '
        '  local o = padMenu:find(getText("IGUI_TREK_Override")) '
        '  if not o then return "absent" end '
        '  if o.notAvailable == true then return "greyed" end '
        '  return "live" '
        'end)()')
    check(str(option) == "greyed",
          f"medical: a padlocked door's override option is {option!r}. It must "
          f"be shown and greyed: hidden, a player cannot tell the tricorder "
          f"from a broken mod; live, the mod picks other people's padlocks")

    cooled()
    rt.run("TREK.Core.send(SIM.players[1], 'unlock', { x = 1202, y = 1200, z = 0 })")
    net.pump(4)
    check(rt.eval("padlocked:isLocked()") is True,
          "medical: the server opened a PADLOCK. That is another player's own "
          "lock, fitted by hand, and a mod that picks them is a griefing tool "
          "on every server that installs it")

    rt.run('safeDoor = SIM.lock(1210, 1210, 0, "IsoDoor")')
    rt.run('SIM.safehouse(1205, 1205, 1215, 1215, { "someone_else" })')
    rt.run(f"TREK.Util.teleport({P}, 1210, 1209, 0)")
    net.pump(20)
    cooled()
    rt.run("TREK.Core.send(SIM.players[1], 'unlock', { x = 1210, y = 1210, z = 0 })")
    net.pump(4)
    check(rt.eval("safeDoor:isLocked()") is True,
          "medical: the server opened a door inside somebody else's safehouse")

    # --- range and cooldown, both measured on the server --------------------
    # Six tiles away, not a hundred: far enough to be out of C.UnlockRange and
    # near enough that its chunk is loaded. A distant one would be refused for
    # being unloaded instead, and the range bound would never be reached.
    rt.run('farDoor = SIM.lock(1210, 1203, 0, "IsoDoor")')
    cooled()
    rt.run("TREK.Core.send(SIM.players[1], 'unlock', { x = 1210, y = 1203, z = 0 })")
    net.pump(4)
    check(rt.eval("farDoor:isLocked()") is True,
          "medical: the server opened a lock six tiles from the player, well "
          "outside C.UnlockRange. "
          "The bound is the whole difference between a tool and a map-wide "
          "master key, because the target arrives from a client")

    rt.run("SIM.safehouses = {}")
    rt.run('firstDoor = SIM.lock(1211, 1210, 0, "IsoDoor")')
    rt.run('nextDoor = SIM.lock(1212, 1210, 0, "IsoDoor")')
    rt.run(f"TREK.Util.teleport({P}, 1211, 1209, 0)")
    net.pump(20)
    cooled()
    rt.run("TREK.Core.send(SIM.players[1], 'unlock', { x = 1211, y = 1210, z = 0 })")
    net.pump(4)
    check(rt.eval("firstDoor:isLocked()") is False,
          "medical: the override that the cooldown check is built on did not "
          "work, so the cooldown below proves nothing")
    rt.run(f"TREK.Util.teleport({P}, 1212, 1209, 0)")
    net.pump(4)
    rt.run("TREK.Core.send(SIM.players[1], 'unlock', { x = 1212, y = 1210, z = 0 })")
    net.pump(4)
    check(rt.eval("nextDoor:isLocked()") is True,
          "medical: two overrides in a row, with no cooldown between them")

    print("medical: the ship carries the set, a dose treats everything but a "
          "bite and the infection, an empty one says so, the ship alone refills "
          "it, the health panel opens at doctor level without the debug global, "
          "the sweep is sliced and banded, and the lock override is a server "
          "command that refuses a padlock, a safehouse, a distant target and a "
          "second try inside the cooldown")


def rep_energy(rt):
    return float(rt.eval("TREK.Replicator.energy()"))


def rep_knows(rt, item_id):
    return rt.eval(f'TREK.Replicator.knows("{item_id}") and 1 or 0') == 1


def rep_row(rt, item_id, field="cost"):
    return rt.eval(f'(function() local r = TREK.Replicator.row("{item_id}") '
                   f'return r and r.{field} or nil end)()')


def made_items(rt, who=1):
    """Everything the player is carrying, as full types.

    The replicator has no tray: it had one for two revisions -- a steel
    counter on the same square that the model hung over -- and that counter
    was doing the work the machine should have been doing. It is gone, and
    what the machine makes goes into your hands.
    """
    packed = rt.eval(f"""(function()
        local out = {{}}
        for _, it in ipairs(SIM.players[{who}].inventory.items) do
            table.insert(out, it.fullType)
        end
        return table.concat(out, "\\n")
    end)()""")
    return [x for x in str(packed).split("\n") if x]


def carrying(rt, item_id, who=None):
    """How many of one type a player has on them.

    `who` names one, which matters on the server: it holds every player's
    inventory, and the whole point of the replicator's output is that the item
    goes to the one who asked for it.
    """
    pick = f'p.name == "{who}"' if who else "true"
    return int(rt.eval(f"""(function()
        local n = 0
        for _, p in ipairs(SIM.players) do
            if {pick} then
                for _, it in ipairs(p.inventory.items) do
                    if it.fullType == "{item_id}" then n = n + 1 end
                end
                if not {str(bool(who)).lower()} then break end
            end
        end
        return n
    end)()"""))


def stand_at(rt, net, ox, oy):
    """Puts the player on a cabin square and lets the world catch up."""
    rt.run(f"""
        local U = TREK.Util
        local x, y = U.at({ox}, {oy})
        U.teleport(SIM.players[1], x, y, TREK.Config.CabinZ)
    """)
    net.pump(4)


def replicator_menu(rt, ox, oy):
    """Right-clicks a cabin square and returns what the menu offered.

    The way a player actually reaches this feature. Driving the server
    handler instead would pass against a build whose menu option was never
    added at all -- which is precisely how the torpedoes shipped broken.
    """
    rt.run(f"""
        local U = TREK.Util
        local tx, ty = U.at({ox}, {oy})
        local p = SIM.players[1]
        SIM.aim.dx = tx - p.x
        SIM.aim.dy = ty - p.y
        repMenu = SIM.contextMenu()
        TREK.ReplicatorUI.fillMenu(0, repMenu, {{}}, false)
    """)
    return str(rt.eval("repMenu:labels()"))


def replicator():
    """The replicator: the catalogue, the patterns, the reserve and the run.

    Three things in here are the ones worth having, and each of them is a
    failure this project has already paid for once:

      * **the catalogue's filter.** An obsolete item is still in the scripts,
        still has a name, and returns nil from instanceItem -- so a catalogue
        without vanilla's `not getObsolete() and not isHidden()` fills up with
        entries that look real and make nothing;
      * **what is made is counted.** `instanceItem` answers nil for an
        obsolete item that slipped the filter, and from the server's side that
        looks exactly like success -- so "made 5" has to mean five items
        arrived, and the player is charged for what landed;
      * **an absent sandbox option means the feature as designed**, which here
        is the *restrictive* reading. Getting that backwards would hand every
        world that never touched the setting an unlimited item printer.
    """
    P = "SIM.players[1]"
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('chef', 1000.5, 1000.5, 0)")
    net.start()

    C = lambda n: rt.eval(f"TREK.Config.{n}")
    rt.run(f"TREK.Transport.beamUp({P})")
    net.pump(180)
    if died(rt, "replicator, beaming up"):
        return
    stand_at(rt, net, 1, 5)

    # --- the alcove stands over the berth, once ------------------------------
    # A world item, and world items are saved and deliberately left alone by
    # U.clearSquare -- so a build that did not look first would stand a second
    # alcove on the square every time the cabin was rebuilt, for ever. That is
    # the "Two shuttles" shape, indoors.
    def alcoves():
        return int(rt.eval(f"""(function()
            local C, U, R = TREK.Config, TREK.Util, TREK.Replicator
            local ox, oy = R.spot()
            local x, y = U.at(ox, oy)
            local n = 0
            for _, w in ipairs(SIM.rawSquare(x, y, C.CabinZ).worldObjects or {{}}) do
                local it = w.item
                local id = it and (it.fullType or it:getFullType())
                if id == C.ReplicatorItem then n = n + 1 end
            end
            return n
        end)()"""))

    check(alcoves() == 1,
          f"replicator: {alcoves()} alcoves stand over the berth after the "
          f"first build, not 1")
    rt.eval("TREK.Build.buildCabin()")
    rt.eval("TREK.Build.buildCabin()")
    check(alcoves() == 1,
          f"replicator: rebuilding the cabin left {alcoves()} alcoves stacked "
          f"on the berth")

    # --- the catalogue ------------------------------------------------------
    size = int(rt.eval("#TREK.Replicator.catalogue()"))
    check(size > 0, "replicator: the catalogue is empty")
    for item_id, why in (
        ("Base.Bandage", "an ordinary vanilla item"),
        ("Base.Hammer", "an ordinary vanilla item"),
        ("TrekShuttle.TrekPhaser", "the mod's own"),
    ):
        check(rep_row(rt, item_id) is not None,
              f"replicator: {item_id} ({why}) is not in the catalogue")
    for item_id, why in (
        ("Base.OldSpanner",
         "obsolete -- it is still in the scripts and instanceItem answers nil, "
         "so it would look like a working entry and make nothing"),
        ("Base.SecretThing", "hidden"),
        ("Moveables.Moveable_fridge",
         "the Moveables module, which is pick-up-furniture placeholders"),
        ("TrekShuttle.TrekTorpedo",
         "a specification handed to IsoTrap.new, not something anybody holds -- "
         "the engine's own filter does not catch it, which is why the blocklist "
         "exists"),
        ("TrekShuttle.TrekShuttleHull", "the model the ship itself is drawn as"),
    ):
        check(rep_row(rt, item_id) is None,
              f"replicator: {item_id} is in the catalogue and should not be ({why})")

    # --- what things cost ---------------------------------------------------
    check(rep_row(rt, "Base.Bandage") == 5,
          f"replicator: a bandage costs {rep_row(rt, 'Base.Bandage')}, not 5")
    check(rep_row(rt, "Base.Hammer") == 24,
          f"replicator: a hammer costs {rep_row(rt, 'Base.Hammer')}, not 24")
    # A 60 kg generator would ask for 604 without the cap, which is most of a
    # full reserve for one appliance.
    check(rep_row(rt, "Base.Generator") == C("ReplicatorMaxCost"),
          f"replicator: a generator costs {rep_row(rt, 'Base.Generator')}, not "
          f"the capped {C('ReplicatorMaxCost')}")

    # --- the ship knows its own stores --------------------------------------
    for item_id in ("TrekShuttle.TrekPhaser", "TrekShuttle.TrekHypospray",
                    "TrekShuttle.TrekBatleth"):
        check(rep_knows(rt, item_id),
              f"replicator: a fresh ship has no pattern for {item_id}, which is "
              f"Starfleet issue -- the ship is meant to know its own")
    check(not rep_knows(rt, "Base.Hammer"),
          "replicator: the ship knows a vanilla hammer it has never seen")

    # --- the way in ---------------------------------------------------------
    use = str(rt.eval('getText("IGUI_TREK_RepUse")'))
    ox, oy = int(rt.eval("(TREK.Replicator.spot())")), \
             int(rt.eval("(select(2, TREK.Replicator.spot()))"))
    check(use in replicator_menu(rt, ox, oy),
          "replicator: right-clicking the berth offers no way to use it")

    # **A click one square off must still offer it**, and that is a fix rather
    # than a convenience. A right-click resolves to the floor square under the
    # cursor, and the alcove is drawn standing over a metre of counter -- so
    # aiming at the lit recess lands a tile or two north-west of the machine.
    # Keyed to the exact square, the option was never offered at all, with the
    # alcove plainly visible and nothing to click on it. Seen in game.
    check(use in replicator_menu(rt, ox + 1, oy),
          "replicator: a click one square off the berth offers nothing -- that "
          "is where aiming at a model drawn above its own square actually "
          "lands, and it is why this was unusable in game")

    # The margin stops there, though: the pad is two squares away and must not
    # be a replicator.
    check(use not in replicator_menu(rt, C("Landing.x"), C("Landing.y")),
          "replicator: the transporter pad offers the replicator; the menu is "
          "not keyed to the berth at all")

    # --- open it and drive it ----------------------------------------------
    replicator_menu(rt, ox, oy)
    rt.run(f'repMenu:click("{use}")')
    check(rt.eval("TREK.ReplicatorUI.window ~= nil") is True,
          "replicator: clicking the menu option opened no panel")

    rt.run('TREK.ReplicatorUI.window.search:setText("hammer")')
    rows = int(rt.eval("#TREK.ReplicatorUI.window.rows"))
    check(rows == 1,
          f"replicator: searching for 'hammer' left {rows} rows, not 1")
    check(str(rt.eval("TREK.ReplicatorUI.window:selectedRow().id")) == "Base.Hammer",
          "replicator: the search did not select the hammer")

    # --- without a pattern, nothing happens ---------------------------------
    before = rep_energy(rt)
    rt.run("SIM.notes = {}")
    rt.run("TREK.ReplicatorUI.window.makeBtn:click()")
    net.pump(4)
    check(made_items(rt) == [],
          f"replicator: it made {made_items(rt)} with no pattern stored for it")
    check(rep_energy(rt) == before,
          "replicator: a refused replication still spent from the reserve")
    check(any("IGUI_TREK_RepNoPattern" in n for n in rt.notes()),
          "replicator: a player with no pattern is told nothing at all")

    # --- scanning keeps the item --------------------------------------------
    rt.run(f'{P}.inventory:AddItem(instanceItem("Base.Hammer"))')
    rt.run("SIM.notes = {}")
    rt.run("TREK.ReplicatorUI.window.scanBtn:click()")
    net.pump(4)
    check(rep_knows(rt, "Base.Hammer"),
          "replicator: scanning a carried hammer stored no pattern")
    check(carrying(rt, "Base.Hammer") == 1,
          "replicator: scanning ate the item. It is a scan, not a recycler -- "
          "the ship reads the thing and gives it back")
    check(any("IGUI_TREK_RepScanned" in n for n in rt.notes()),
          "replicator: a scan said nothing")

    # --- and now it makes one -----------------------------------------------
    before = rep_energy(rt)
    rt.run("SIM.notes = {}")
    rt.run("TREK.ReplicatorUI.window.makeBtn:click()")
    net.pump(4)
    check(carrying(rt, "Base.Hammer") == 2,
          f"replicator: the player holds {carrying(rt, 'Base.Hammer')} hammers "
          f"after scanning one and making one; it should be two")
    check(before - rep_energy(rt) == 24,
          f"replicator: a hammer cost {before - rep_energy(rt)} units, not 24")
    check(any("IGUI_TREK_RepMade" in n for n in rt.notes()),
          "replicator: it made something and said nothing")
    check(rt.eval('SIM.heardSound("TREK_Replicate")') is True,
          "replicator: it materialised an item in complete silence")

    # --- the cooldown is real ------------------------------------------------
    rt.run("SIM.notes = {}")
    rt.run("TREK.ReplicatorUI.window.makeBtn:click()")
    net.pump(4)
    check(carrying(rt, "Base.Hammer") == 2,
          "replicator: a second item came straight out; the cooldown does nothing")
    check(any("IGUI_TREK_RepCycling" in n for n in rt.notes()),
          "replicator: the cooldown refused silently")

    # --- a quantity costs a quantity ----------------------------------------
    net.clock += int(C("ReplicatorCooldownMs")) + 500
    rt.run("TREK.ReplicatorUI.window.qtyBtn:click()")      # 1 -> 5
    check(int(rt.eval("TREK.ReplicatorUI.window:quantity()")) == 5,
          "replicator: the quantity button did not step to 5")
    before = rep_energy(rt)
    rt.run("TREK.ReplicatorUI.window.makeBtn:click()")
    net.pump(4)
    check(carrying(rt, "Base.Hammer") == 7,
          f"replicator: asked for 5 more and the player holds "
          f"{carrying(rt, 'Base.Hammer')} hammers rather than seven")
    check(before - rep_energy(rt) == 24 * 5,
          f"replicator: five hammers cost {before - rep_energy(rt)}, not {24 * 5}")

    # --- the reserve is a real limit ----------------------------------------
    net.clock += int(C("ReplicatorCooldownMs")) + 500
    rt.run("TREK.Util.state().repEnergy = 10")
    rt.run("SIM.notes = {}")
    held = len(made_items(rt))
    rt.run("TREK.ReplicatorUI.window.makeBtn:click()")
    net.pump(4)
    check(len(made_items(rt)) == held,
          "replicator: it made something it could not pay for")
    check(any("IGUI_TREK_RepEnergy" in n for n in rt.notes()),
          "replicator: an empty reserve refused without saying so")

    # --- and it comes back ---------------------------------------------------
    rt.fire("EveryTenMinutes")
    check(rep_energy(rt) == 10 + C("ReplicatorRegen"),
          f"replicator: ten game minutes put back {rep_energy(rt) - 10}, not "
          f"{C('ReplicatorRegen')}")

    # A tick that would overshoot must stop at the ceiling. Set five short of
    # full, not full: a reserve that is already full takes the early way out of
    # R.regen and proves nothing about the clamp.
    #
    # And read the number out of the *state* rather than through R.energy(),
    # which clamps on the way out. What matters is the figure that gets saved
    # and transmitted, not whether the reader hides it climbing.
    rt.run(f"TREK.Util.state().repEnergy = {C('ReplicatorEnergyMax') - 5}")
    rt.fire("EveryTenMinutes")
    check(rt.eval("TREK.Util.state().repEnergy") == C("ReplicatorEnergyMax"),
          f"replicator: the reserve charged past its own ceiling to "
          f"{rt.eval('TREK.Util.state().repEnergy')}")

    # --- the mod's own gear needs no scanning --------------------------------
    net.clock += int(C("ReplicatorCooldownMs")) + 500
    rt.run("""
        local w = TREK.ReplicatorUI.window
        w.qtyBtn:click(); w.qtyBtn:click()          -- 5 -> 10 -> 1
        w.search:setText("trekphaser")
    """)
    check(int(rt.eval("TREK.ReplicatorUI.window:quantity()")) == 1,
          "replicator: the quantity button does not wrap back to 1")
    rt.run("TREK.ReplicatorUI.window.makeBtn:click()")
    net.pump(4)
    check("TrekShuttle.TrekPhaser" in made_items(rt),
          "replicator: the ship could not make its own phaser")

    # --- a crafted command is still a request --------------------------------
    # The panel would never send any of these. The server is what stops them,
    # and **the refusal is checked as well as the effect**: "nothing came out"
    # is also what a full tray or an empty reserve looks like, so a check that
    # only counted the tray would pass with the guard under test deleted. The
    # quantity one is the case that really needs it -- 999 hammers costs more
    # than the whole reserve, so the energy check would refuse it anyway.
    for args, expect, why in (
        ('{ id = "Base.OldSpanner", count = 1 }', "RepUnknown",
         "an obsolete item, which instanceItem answers nil for"),
        ('{ id = "Moveables.Moveable_fridge", count = 1 }', "RepUnknown",
         "a Moveables placeholder"),
        ('{ id = "TrekShuttle.TrekTorpedo", count = 1 }', "RepUnknown",
         "a live warhead"),
        ('{ id = "Base.Hammer", count = 999 }', "RepUnknown",
         "a quantity the panel does not offer -- without this the command is "
         "an item printer"),
        ('{ id = 12345, count = 1 }', "RepUnknown",
         "an id that is not even a string"),
    ):
        net.clock += int(C("ReplicatorCooldownMs")) + 500
        held = len(made_items(rt))
        rt.run("SIM.notes = {}")
        rt.run(f"TREK.Core.send({P}, 'replicate', {args})")
        net.pump(4)
        check(len(made_items(rt)) == held,
              f"replicator: the server accepted {why}")
        check(any(f"IGUI_TREK_{expect}" in n for n in rt.notes()),
              f"replicator: {why} was refused for the wrong reason "
              f"({rt.notes()}) -- the guard under test was never reached")

    # --- you have to be standing at it ---------------------------------------
    stand_at(rt, net, 1, 0)                     # the bow, five squares away
    check(use in replicator_menu(rt, ox, oy),
          "replicator: from across the cabin the option vanishes rather than "
          "telling the player to walk over to it")
    check(rt.eval("""(function()
        local o = repMenu:find(getText("IGUI_TREK_RepUse"))
        return o ~= nil and o.notAvailable == true
    end)()""") is True,
          "replicator: the option is live from across the cabin, so a player "
          "gets a panel that closes itself the moment it opens")
    net.clock += int(C("ReplicatorCooldownMs")) + 500
    held = len(made_items(rt))
    rt.run("SIM.notes = {}")
    rt.run(f"TREK.Core.send({P}, 'replicate', {{ id = 'Base.Hammer', count = 1 }})")
    net.pump(4)
    check(len(made_items(rt)) == held,
          "replicator: the server made something for a player standing at the "
          "other end of the ship")
    check(any("IGUI_TREK_RepFar" in n for n in rt.notes()),
          "replicator: a refusal for being too far away said nothing")
    # And the open panel closed itself rather than sitting there refusing.
    rt.run("if TREK.ReplicatorUI.window then TREK.ReplicatorUI.window:prerender() end")
    check(rt.eval("TREK.ReplicatorUI.window == nil") is True,
          "replicator: the panel stayed open after the player walked away, "
          "answering 'too far' to every press")

    # --- what is made is counted, not assumed --------------------------------
    # There is no tray to fill any more, so the case that matters is the one
    # this whole feature is built to survive: **an item that is in the
    # catalogue and will not instance.** An obsolete item is exactly that --
    # still in the scripts, still named, and nil from instanceItem -- and from
    # the server's side a nil looks identical to success.
    #
    # So instanceItem is made to answer once and then stop, five are asked
    # for, and one must arrive: the player pays for one.
    stand_at(rt, net, 1, 5)
    rt.run("""
        SIM.realInstance = SIM.realInstance or instanceItem
        local given = 0
        function instanceItem(id)
            if id == "Base.Hammer" then
                given = given + 1
                if given > 1 then return nil end
            end
            return SIM.realInstance(id)
        end
        SIM.notes = {}
    """)
    net.clock += int(C("ReplicatorCooldownMs")) + 500
    held = carrying(rt, "Base.Hammer")
    before = rep_energy(rt)
    rt.run(f"TREK.Core.send({P}, 'replicate', {{ id = 'Base.Hammer', count = 5 }})")
    net.pump(4)
    made = carrying(rt, "Base.Hammer") - held
    check(made == 1,
          f"replicator: five were asked for, the second one would not instance, "
          f"and {made} arrived -- the run is not being counted item by item")
    check(before - rep_energy(rt) == 24 * made,
          f"replicator: asked for 5, made {made}, and charged "
          f"{before - rep_energy(rt)} rather than {24 * made}. The player pays "
          f"for what arrived")
    check(any("IGUI_TREK_RepPartial" in n for n in rt.notes()),
          "replicator: a run that made one of five said nothing about it")
    rt.run("instanceItem = SIM.realInstance")

    # --- and the other way a thing can fail to arrive ------------------------
    # `instanceItem` answering is not the same as the item landing:
    # **ItemContainer drops what it is handed once it is full, in silence**
    # (DEV_GUIDE.md, "A container is missing item types"). So the run counts
    # the inventory as well as the answer, and this is the case that tells
    # those two checks apart -- every item instances perfectly and none of
    # them arrives.
    rt.run("""
        local inv = SIM.players[1].inventory
        while inv:getContentsWeight() + 0.5 <= inv.capacity do
            inv:AddItem(instanceItem("Base.Bandage"))
        end
        SIM.notes = {}
    """)
    net.clock += int(C("ReplicatorCooldownMs")) + 500
    held = carrying(rt, "Base.Hammer")
    before = rep_energy(rt)
    rt.run(f"TREK.Core.send({P}, 'replicate', {{ id = 'Base.Hammer', count = 5 }})")
    net.pump(4)
    check(carrying(rt, "Base.Hammer") == held,
          "replicator: it reported making hammers into an inventory that was "
          "already full -- the run is trusting instanceItem rather than "
          "counting what arrived")
    check(rep_energy(rt) == before,
          f"replicator: charged {before - rep_energy(rt)} units for items that "
          f"never arrived")
    check(any("IGUI_TREK_RepFailed" in n for n in rt.notes()),
          "replicator: nothing was made and nothing was said")
    # Empty the pockets again for the checks that follow.
    rt.run("SIM.players[1].inventory.items = {}")

    # --- the sandbox option --------------------------------------------------
    rt.run("SandboxVars.TrekShuttle.Replicator = TREK.Config.ReplicatorOff")
    check(use in replicator_menu(rt, ox, oy),
          "replicator: switched off, the menu option vanishes -- a player "
          "cannot then tell the setting from a broken mod")
    check(rt.eval("""(function()
        local o = repMenu:find(getText("IGUI_TREK_RepUse"))
        return o ~= nil and o.notAvailable == true
    end)()""") is True,
          "replicator: switched off, the menu option is still live")
    # **The refusal is asserted as well as the effect.** "Nothing was made" is
    # also what an empty reserve looks like, and a mutation run caught exactly
    # that: with the sandbox check deleted this still passed, because a full
    # tray was refusing instead. There is no tray now, so the note is what
    # proves which guard did the work.
    rt.run("SIM.notes = {}")
    net.clock += int(C("ReplicatorCooldownMs")) + 500
    held = carrying(rt, "Base.Hammer")
    rt.run(f"TREK.Core.send({P}, 'replicate', {{ id = 'Base.Hammer', count = 1 }})")
    net.pump(4)
    check(carrying(rt, "Base.Hammer") == held,
          "replicator: switched off in the sandbox and it still made something")
    check(any("IGUI_TREK_RepOff" in n for n in rt.notes()),
          "replicator: switched off, the refusal blamed something else")

    rt.run("SandboxVars.TrekShuttle.Replicator = TREK.Config.ReplicatorUnrestricted")
    net.clock += int(C("ReplicatorCooldownMs")) + 500
    rt.run("TREK.Util.state().repEnergy = 0")
    rt.run(f"TREK.Core.send({P}, 'replicate', {{ id = 'Base.Axe', count = 1 }})")
    net.pump(4)
    check(carrying(rt, "Base.Axe") == 1,
          "replicator: unrestricted, it still refused an item nobody had "
          "scanned -- and on an empty reserve, which it is meant to ignore")
    check(rep_energy(rt) == 0,
          "replicator: unrestricted, it still charged for the item")

    # The one that matters most, and it is the opposite reading from the
    # torpedo's sandbox option: with nothing set at all the replicator must be
    # the *limited* one. A missing option that means "no limits" is how a world
    # nobody configured ends up with an item printer.
    rt.run("SandboxVars.TrekShuttle.Replicator = nil")
    check(int(rt.eval("TREK.Replicator.mode()")) == int(C("ReplicatorPatterns")),
          "replicator: with no sandbox option set the replicator is not in its "
          "patterns-and-energy mode")
    rt.run("SandboxVars.TrekShuttle = nil")
    check(int(rt.eval("TREK.Replicator.mode()")) == int(C("ReplicatorPatterns")),
          "replicator: with no sandbox table at all the replicator is not in "
          "its patterns-and-energy mode")
    rt.run("SandboxVars.TrekShuttle = { Access = 1, TransporterLimit = 1 }")

    for w in rt.warnings():
        fail(f"replicator: {w}")
    print(f"replicator: a catalogue of {size} filtered entries, the ship's own "
          f"patterns, scanning that keeps the item, the reserve, the cooldown, "
          f"a run counted item by item, both range ends and all three "
          f"sandbox values")


def replicator_multiplayer():
    """Two clients: who may use it, where the item is made, and who is told.

    The pattern set is the interesting half. It is shared by the crew and it
    lives in its own mod data key rather than in the ship state -- a crew with
    two thousand patterns would otherwise push two thousand strings through
    every commit, and the ship commits each time it is driven a square.
    """
    net = Net("mp", clients=("owner", "stranger"))
    srv = net.server
    owner, stranger = net.clients["owner"], net.clients["stranger"]

    for rt in net.all():
        rt.run("SandboxVars.TrekShuttle.Access = 2")
    srv.run("SIM.player('owner', 2000.5, 2000.5, 0); "
            "SIM.player('stranger', 2000.5, 2000.5, 0)")
    owner.run("SIM.player('owner', 2000.5, 2000.5, 0)")
    stranger.run("SIM.player('stranger', 2000.5, 2000.5, 0)")
    net.start()
    P = "SIM.players[1]"

    owner.run(f"TREK.Transport.beamUp({P})")
    net.pump(210)
    if died(owner, "replicator multiplayer, beaming up"):
        return
    check(ship(srv, "owner") == "owner", "replicator: the owner did not claim the ship")

    # Both of them at the berth, on every machine: the server measures the
    # range against its own copy of where they are standing.
    for rt in net.all():
        rt.run("""
            local U, R = TREK.Util, TREK.Replicator
            local x, y = U.at(1, 5)
            for _, p in ipairs(SIM.players) do
                p.x, p.y, p.z, p.lastZ = x + 0.5, y + 0.5, TREK.Config.CabinZ,
                                         TREK.Config.CabinZ
            end
        """)
    net.pump(10)

    # --- the mod's own patterns reached the client --------------------------
    check(rep_knows(owner, "TrekShuttle.TrekPhaser"),
          "replicator: the ship's own patterns never reached the client, so "
          "its panel shows Starfleet gear it believes the ship cannot make")

    # --- a stranger is refused ----------------------------------------------
    stranger.run("""
        for _, p in ipairs(SIM.players) do
            p.inventory:AddItem(instanceItem("Base.Hammer"))
        end
    """)
    srv.run("""
        for _, p in ipairs(SIM.players) do
            if p.name == "stranger" then
                p.inventory:AddItem(instanceItem("Base.Hammer"))
            end
        end
    """)
    stranger.run(f"TREK.Core.send({P}, 'scanCarried', {{}})")
    net.pump(4)
    check(not rep_knows(srv, "Base.Hammer"),
          "replicator: a player who is not on the crew scanned a pattern into "
          "the ship")
    check(any("IGUI_TREK_NotCrew" in n for n in stranger.notes()),
          "replicator: the stranger was refused without being told why")

    # --- the owner scans, and it reaches the other machine -------------------
    owner.run("""
        for _, p in ipairs(SIM.players) do
            p.inventory:AddItem(instanceItem("Base.Hammer"))
        end
    """)
    srv.run("""
        for _, p in ipairs(SIM.players) do
            if p.name == "owner" then
                p.inventory:AddItem(instanceItem("Base.Hammer"))
            end
        end
    """)
    owner.run(f"TREK.Core.send({P}, 'scanCarried', {{}})")
    net.pump(4)
    check(rep_knows(srv, "Base.Hammer"),
          "replicator: the owner's scan did not reach the server")
    check(rep_knows(stranger, "Base.Hammer"),
          "replicator: a pattern one crewman scanned never reached the other "
          "machine -- the pattern set is meant to be the ship's, not a player's")

    # --- the item is made on the server, and both machines see the tray -----
    before = rep_energy(srv)
    owner.run(f"TREK.Core.send({P}, 'replicate', {{ id = 'Base.Hammer', count = 1 }})")
    net.pump(6)
    # The owner scanned a hammer earlier, so they should hold two now: the one
    # they walked in with and the one the ship made.
    check(carrying(srv, "Base.Hammer", who="owner") == 2,
          f"replicator: the server has the owner holding "
          f"{carrying(srv, 'Base.Hammer', who='owner')} hammers, not two")
    check(carrying(owner, "Base.Hammer") == 2,
          f"replicator: the asking client is holding "
          f"{carrying(owner, 'Base.Hammer')} hammers -- the item the server "
          f"made never reached them. `player:getInventory():AddItem(item)` on "
          f"the server needs `sendAddItemToContainer` after it, which is what "
          f"vanilla's own ClientCommands.lua does a dozen times")
    # And it is *theirs*: an item in somebody's pockets is not world state.
    check(carrying(stranger, "Base.Hammer") == 1,
          f"replicator: the other player is holding "
          f"{carrying(stranger, 'Base.Hammer')} hammers -- the one they walked "
          f"in with, and nothing the owner asked the machine for")
    check(before - rep_energy(srv) == 24,
          "replicator: the server did not charge for the hammer")
    check(rep_energy(owner) == rep_energy(srv) and rep_energy(stranger) == rep_energy(srv),
          "replicator: the reserve on the clients does not match the server's")

    # --- a client never makes anything itself --------------------------------
    for name, c in net.clients.items():
        check(c.eval("SIM.clientWorldEdit") is None,
              f"replicator: {name}'s client edited the world directly")

    # --- and a client's word about its own inventory is not evidence ---------
    # The stranger is crew now, and asks for a pattern for something they are
    # not carrying at all. The server looks in its own copy of their pockets.
    owner.run(f"TREK.Core.send({P}, 'setCrew', {{ name = 'stranger', on = true }})")
    net.pump(4)
    stranger.run(f"TREK.Core.send({P}, 'storePattern', {{ id = 'Base.Axe' }})")
    net.pump(4)
    check(not rep_knows(srv, "Base.Axe"),
          "replicator: the server stored a pattern for an item the asking "
          "player was not carrying. A client is a request, never a fact")

    for rt in net.all():
        for w in rt.warnings():
            fail(f"replicator multiplayer ({rt.name}): {w}")
    print("replicator multiplayer: crew access, a shared pattern set that "
          "reaches both machines, an item the server makes into the asking "
          "player's own hands and nobody else's, and an inventory the server "
          "checks for itself")


def medical_multiplayer():
    """The medical set with two clients: who may open a lock, and who is asked.

    Both halves of this are things single player cannot show. A client has no
    business writing a lock, and a player without the tool has no business
    opening one even if their client asks nicely -- so the request is made from
    a client that is carrying nothing and the server is expected to say no.
    """
    net = Net("mp", clients=("owner", "stranger"))
    server = net.server
    owner, stranger = net.clients["owner"], net.clients["stranger"]

    # The server knows both; each client knows only itself, which is the shape
    # the engine really has and the reason a client's word about its own
    # inventory is not evidence.
    server.run("SIM.player('owner', 2000.5, 2000.5, 0); "
               "SIM.player('stranger', 2000.5, 2000.5, 0)")
    owner.run("SIM.player('owner', 2000.5, 2000.5, 0)")
    stranger.run("SIM.player('stranger', 2000.5, 2000.5, 0)")

    # What each client's copy of "who is online" looks like. The owner needs a
    # second player standing on the same square to have anybody to scan.
    owner.run("""
        -- Standing on the door's own square, because that is the square a
        -- right-click on them resolves to.
        SIM.otherPlayer = {
            name = "stranger",
            getUsername = function(self) return self.name end,
            getDisplayName = function(self) return self.name end,
            getX = function() return 2000.5 end,
            getY = function() return 2001.5 end,
            getZ = function() return 0 end,
            isDead = function() return false end,
        }
        function getOnlinePlayers()
            return SIM.jlist({ SIM.players[1], SIM.otherPlayer })
        end
    """)
    stranger.run("function getOnlinePlayers() return SIM.jlist({ SIM.players[1] }) end")

    net.start()
    net.pump(4)

    for rt in net.all():
        rt.run('mpDoor = SIM.lock(2000, 2001, 0, "IsoDoor")')
    # The tricorder is in the owner's inventory on **both** sides, because that
    # is where it would really be: the server holds every player's inventory
    # and is the only copy it is allowed to believe.
    for rt in (owner, server):
        rt.run("""
            for _, p in ipairs(SIM.players) do
                if p.name == "owner" then
                    p.inventory:AddItem(instanceItem(TREK.Config.TricorderItem))
                end
            end
        """)

    # --- a client that is carrying nothing is refused ----------------------
    stranger.run("TREK.Core.send(SIM.players[1], 'unlock', { x = 2000, y = 2001, z = 0 })")
    net.pump(4)
    check(server.eval("mpDoor:isLocked()") is True,
          "medical: the server opened a lock for a player carrying no tricorder. "
          "A client is a request, never a fact -- the tool has to be checked "
          "where the player's inventory really is")

    # --- and the one with the tool is not -----------------------------------
    server.run("SIM.synced = {}")
    owner.run("TREK.Core.send(SIM.players[1], 'unlock', { x = 2000, y = 2001, z = 0 })")
    net.pump(4)
    check(server.eval("mpDoor:isLocked()") is False,
          "medical: the server refused an override from the player who is "
          "carrying the tricorder")
    check(server.eval("#SIM.synced") >= 1,
          "medical: the server opened the lock without syncing it to anyone")

    # --- a client never writes a lock itself ---------------------------------
    check(owner.eval("mpDoor:isLocked()") is True,
          "medical: the asking client unlocked its own copy of the door. A lock "
          "is world state; the client asks and the server's sync is what "
          "changes it")

    # --- scanning somebody else asks them first ------------------------------
    owner.run('SIM.players[1].inventory:AddItem(instanceItem(TREK.Config.MedTricorderItem))')
    owner.run("SIM.medicalRequests = {}")
    owner.run("""
        scanMenu = SIM.contextMenu()
        TREK.MedKit.fillWorldMenu(0, scanMenu, { mpDoor }, false)
    """)
    label = owner.eval('getText("IGUI_TREK_MedScanOther", "stranger")')
    check(str(label) in str(owner.eval("scanMenu:labels()")),
          "medical: a medical tricorder offers no way to scan the person "
          "standing next to you")
    owner.run(f'scanMenu:click("{label}")')
    check(owner.eval("#SIM.medicalRequests") == 1,
          "medical: scanning another player did not ask their permission. "
          "requestMedicalCheck raises a yes/no on their screen, and reading "
          "somebody's body without it is a different kind of mod")
    check(owner.eval("#SIM.healthPanels") == 0,
          "medical: a panel on another player opened before they had agreed")

    for rt in net.all():
        for w in rt.warnings():
            fail(f"medical multiplayer: {w}")

    print("medical multiplayer: the server checks the tool in the asking "
          "player's own inventory, syncs the lock it opens, never lets a client "
          "write one, and asks a player before reading their body")


def main():
    static()
    migration()
    single_player()
    refit()
    flight()
    flight_endings()
    torpedoes()
    medical()
    medical_multiplayer()
    replicator()
    replicator_multiplayer()
    multiplayer()
    if failures:
        print(f"\n{len(failures)} PROBLEM(S):")
        for f in dict.fromkeys(failures):
            print("  " + f)
        sys.exit(1)
    print("\nsingle player and multiplayer behave as designed")


main()
