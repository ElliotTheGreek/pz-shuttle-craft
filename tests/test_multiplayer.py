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


def definitions():
    """The mod's shared/Definitions files, which are plain registration Lua."""
    base = os.path.join(LUA, "shared", "Definitions")
    if not os.path.isdir(base):
        return []
    return sorted("Definitions/" + f[:-4]
                  for f in os.listdir(base) if f.endswith(".lua"))


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
        # A timed action handed to the server (PADD.md): by class name, with
        # its arguments in `new`'s parameter order.
        g.py_client_action = lambda who, kind, args, token: net.queue.append(
            ("action", self, who, kind, to_py(args), token))
        path = "/".join(LUA.split(os.sep))
        self.lua.execute(f'package.path = "{path}/shared/?.lua;{path}/client/?.lua;'
                         f'{path}/server/?.lua;" .. package.path')
        self.lua.execute(open(SIM, encoding="utf-8").read())
        self.lua.execute(APPLY)

    def load(self):
        # The game loads every .lua under media/lua, so the simulation has to
        # as well. shared/Definitions is not a TREK/ folder and was missed:
        # that is where the world-map symbols register themselves, and a
        # symbol id nothing registered draws nothing at all -- so leaving it
        # out would have made the map tests pass against symbols the game
        # would never have had.
        for m in definitions():
            self.lua.execute(f'require "{m}"')
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

    def logLines(self):
        """Everything the mod logged, not only the warnings.

        An honest empty probe report is not a warning -- it is a normal
        outcome -- but it still has to be distinguishable from a probe that is
        simply still out, so the test reads the log for it.
        """
        log = self.lua.globals().SIM.log
        return [str(log[i]) for i in range(1, len(log) + 1)]

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
        elseif op == "playerItemGone" then
            for _, p in ipairs(SIM.players) do
                if p.name == d.who then
                    for i, it in ipairs(p.inventory.items) do
                        if it.fullType == d.item then
                            table.remove(p.inventory.items, i)
                            break
                        end
                    end
                end
            end
        elseif op == "containerItemGone" then
            local o = find(sq.objects, d.sprite)
            if o and o.container then
                for i, it in ipairs(o.container.items) do
                    if it.fullType == d.item then
                        table.remove(o.container.items, i)
                        break
                    end
                end
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
        elseif op == "itemModData" then
            -- The server pushed an item's mod data to the player carrying it.
            for _, p in ipairs(SIM.players) do
                if p.name == d.who then
                    for _, it in ipairs(p.inventory.items) do
                        if it.id == d.id then it.modData = copy(d.modData) end
                    end
                end
            end
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
        elif kind == "action":
            _, src, who, action, args, token = msg
            n = max([int(k) for k in args] or [0])
            table = self.server.lua.table()
            for k, v in args.items():
                table[int(k)] = self.server.table(v)
            ok = self.server.lua.globals().SIM.serverAction(action, table, n)
            src.lua.globals().SIM.clientActionDone(token, bool(ok))
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
            # The driver's machine publishes the body; the server relays it.
            bodies = {}
            for name, c in self.clients.items():
                for pair in (c.eval("SIM.ownedBodies()") or "").split(";"):
                    if pair:
                        vid, y = pair.split("=")
                        bodies[vid] = (name, y)
            for vid, (owner, y) in bodies.items():
                for name, c in self.clients.items():
                    if name != owner:
                        c.run(f"SIM.applyBody({vid}, {y})")
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
        # The engine registers recorded media before anything asks for a
        # tape's recording, and it does it in every process. Doing it here
        # rather than inside a tape test is deliberate: the tape shelf is
        # stocked during the cabin build, which every suite in this file runs.
        for rt in self.all():
            rt.run("SIM.initRecordedMedia()")
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


def container_at(rt, ox, oy):
    """What the container on one authored cabin square is holding.

    cabin_stores() answers "is it aboard", which is not the same question as
    "is it in the locker the layout put it in". A uniform that ended up in the
    galley fridge would pass the first and be wrong.
    """
    packed = rt.eval(f"""(function()
        local C, U = TREK.Config, TREK.Util
        local x, y = U.at({ox}, {oy})
        local out = {{}}
        for _, o in ipairs(SIM.rawSquare(x, y, C.CabinZ).objects) do
            if o.container then
                for _, it in ipairs(o.container.items) do
                    out[#out + 1] = it.getFullType and it:getFullType() or tostring(it)
                end
            end
        end
        return table.concat(out, "\\n")
    end)()""")
    return [x for x in str(packed).split("\n") if x]


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


def uniform_issue(rt):
    """C.UniformIssue, as Python strings."""
    packed = rt.eval("""(function()
        return table.concat(TREK.Config.UniformIssue, "\\n")
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

    # The wardrobe. Every uniform is a *guarantee* (`special = "uniforms"`),
    # not a roll, so this is a check on the rule: none of the six is in any
    # C.Loot list, and the only thing that can put one in the armoury is
    # SPECIALS.uniforms. U.stockEach reads the locker back and logs a WARN for
    # anything short, and this suite already fails on any WARN -- so a locker
    # that ran out of room fails twice over rather than silently issuing five.
    # TREK_Uniform()'s report, run for real. It is the only diagnostic that
    # can tell a uniform whose GUID resolved from one whose did not, so a
    # throw inside it would leave the player with no way to tell those apart
    # at all -- and it walks engine calls (getClothingItem, getMaleModel,
    # getTextureChoices) that nothing else in the mod touches.
    ok = rt.eval("TREK.Server.uniformReport()")
    check(ok is True,
          "single player: S.uniformReport() did not resolve every uniform")
    nonclothing = rt.eval(
        'instanceItem(TREK.Config.PhaserItem):getClothingItem() == nil')
    check(nonclothing is True,
          "the simulation hands a ClothingItem back for a phaser, so the "
          "report would call anything at all a working garment")

    issue = uniform_issue(rt)
    check(len(issue) == 6,
          f"single player: C.UniformIssue holds {len(issue)} uniforms, not 6 "
          f"-- this check would pass against an empty list")
    # In the armoury specifically, not merely somewhere aboard: the layout
    # names that locker and a uniform anywhere else is a different bug.
    armoury = container_at(rt, 3, 0)
    for item_id in issue:
        check(item_id in stores,
              f"single player: the ship sails without {item_id} "
              f"(special = \"uniforms\" on the armoury)")
        check(item_id in armoury,
              f"single player: {item_id} is aboard but not in the armoury "
              f"locker at 3,0")
    print(f"  wardrobe: the armoury at 3,0 holds "
          f"{len([x for x in armoury if 'Uniform' in x])} uniforms among "
          f"{len(armoury)} items")
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

    # --- nobody climbs out of her -----------------------------------------
    # **Build 42 lets a player climb over a wall, not merely a fence.**
    # IsoPlayer.canClimbOverWall refuses the climb over a square that has a
    # roof or belongs to an IsoBuilding, which is every wall of every house on
    # the map. The cabin is raised at runtime in a cell with no map behind it
    # and has neither, so the climb was allowed -- and what is on the other
    # side is the ring of deck the walls stand on, with the void one square
    # past that. Seen in game: climb out, walk on, fall for ever.
    check(rt.eval(f"{P}:isIgnoreAutoVault()") is True,
          "single player: the vault is not locked while anyone is aboard, so "
          "the crew can climb over the cabin wall and out of the world")
    # The flag has to *refuse a climb*, not merely hold a value: an assertion
    # about a field nothing reads would pass against a build that set it and
    # changed nothing. SIM.climbOverWall performs the climb the way the engine
    # does, and reads ignoreAutoVault first, as both routes into it do.
    before = pos(rt)
    check(rt.eval(f"SIM.climbOverWall({P}, 0, -1)") is False,
          "single player: a climb over the bow wall was allowed")
    check(pos(rt) == before,
          f"single player: the refused climb moved the player to {pos(rt)} anyway")

    # And the containment behind the lock, which is also what rescues anybody
    # already standing out there in a save made before this. The first of
    # these squares is floored -- a wall on a midair square behaves badly, so
    # the deck runs under every one of them -- which is exactly why a check
    # for "is there a floor under me" was happy to leave somebody on it.
    cabin_w = int(rt.eval("TREK.Config.CabinW"))
    cabin_l = int(rt.eval("TREK.Config.CabinL"))
    for ox, oy, where in ((0, -1, "the deck ring outside the bow wall"),
                          (cabin_w + 1, 2, "the deck ring the starboard wall stands on"),
                          (2, cabin_l + 3, "the void abaft her")):
        rt.run(f"""
            local U = TREK.Util
            local x, y = U.at({ox}, {oy})
            U.teleport({P}, x, y, TREK.Config.CabinZ)
        """)
        net.pump(6)
        if died(rt, f"single player, put on {where}"):
            return
        check(at_pad(rt), f"single player: somebody on {where} was left at "
                          f"{pos(rt)} instead of being put back on the pad")
    check(any("IGUI_TREK_NoWayOut" in n for n in rt.notes()),
          "single player: a player put back inside the hull was never told "
          "why, which is a rescue that reads as the game teleporting you")

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
    # And the vault is the character's again. A crewman who stepped out of the
    # hatch and could no longer climb a fence would be a worse bug than the
    # one the lock fixes, and it would follow them for the life of the save.
    check(rt.eval(f"{P}:isIgnoreAutoVault()") is False,
          "single player: stepping out of the hatch left the player unable to "
          "climb anything, for good")
    check(rt.eval(f"SIM.climbOverWall({P}, 0, -1)") is True,
          "single player: a climb outside the ship was still refused")

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

    # --- single player owns the physics, and the engine will not say so ----
    # BaseVehicle's constructor sets netPlayerAuthorization = Authorization
    # .Server, and the only thing that ever sets it to Local is
    # constraintChanged() -> authorizationChanged(getDriver()), whose whole
    # body is behind `getstatic GameServer.server; ifeq -> return`. So off a
    # server nothing touches it and isLocalPhysicSim() is false for ever --
    # vanilla never asks it in single player either, consulting it only inside
    # isBrakePedalPressed's GameClient.client branch.
    #
    # A guard that asked the engine unconditionally therefore refused every
    # take-off in single player, in silence. It shipped, because this stub
    # used to answer `SIM_ROLE ~= "server"` and was kindest about exactly the
    # case that was broken.
    check(rt.eval("TREK.Vehicle.ship():isLocalPhysicSim()") is False,
          "flight: the simulation claims single player owns the vehicle "
          "physics. The engine says the opposite, and a simulation kinder "
          "than the engine is how the ship came to be unable to take off")

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
    # And it is a binary. "Climb" and "Dive" were four rungs of a ladder with
    # three that the ship could not stand on; there is one altitude now and
    # anything offering another is the confusion this pass removed.
    for gone in ("IGUI_TREK_Climb", "IGUI_TREK_Dive"):
        check(gone not in (titles or ""),
              f"flight: the radial menu still offers {gone} (slices: {titles})")

    # --- take off ---------------------------------------------------------
    rt.run(f"TREK.Flight.takeOff({P})")
    net.pump(400)
    check(ship(rt, "flying") is True,
          "flight: she never got off the ground")
    check(ship(rt, "level") == rt.eval("TREK.Config.FlightLevel"),
          f"flight: airborne at level {ship(rt, 'level')}, not the one flight level")
    check(vehicle_z(rt) == rt.eval("TREK.Config.FlightLevel"),
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
    check(vehicle_z(rt) == rt.eval("TREK.Config.FlightLevel"),
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
    check(vehicle_z(rt) == rt.eval("TREK.Config.FlightLevel"),
          f"flight: she lost height while flying along (z {vehicle_z(rt)})")

    # --- levelling her off must not throw her heading away -----------------
    # This is the bug that made the first two-player flight unflyable, and
    # nothing here could see it because the simulation stored the three angles
    # instead of decomposing a rotation.
    #
    # getAngleX/Z are not pitch and roll. They are the X and Z of JOML's
    # getEulerAnglesXYZ, and for a level ship turned more than a quarter turn
    # from her spawn heading the X of that is atan2(0, cos yaw) = 180. So the
    # old "|angleX| > tolerance means she is tipping" fired on every check in
    # half the compass, and the call it made -- flipUpright -- is
    # setAngleAxis(**0**, Y): the identity. She was wrenched back to her spawn
    # heading ten times a second, by a physics teleport, and only reverse
    # worked because reversing never leaves the safe half.
    #
    # Two things have to hold at every heading: she ends up level, and her nose
    # does not move.
    cruise = rt.eval("TREK.Config.FlightLevel")
    for heading in (0, 60, 135, 180, -135, -60):
        rt.run(f"""
            local v = TREK.Vehicle.ship()
            v:setHeading({heading})
        """)
        net.pump(20)
        got = rt.eval("TREK.Vehicle.ship():heading()")
        check(abs(((got - heading) + 180) % 360 - 180) < 1.0,
              f"flight: flying on a heading of {heading} degrees, she was "
              f"turned to {got:.1f} -- something is levelling her off by "
              f"throwing the whole rotation away")
        check(rt.eval("TREK.Vehicle.ship():uprightness()") > 0.99,
              f"flight: she is not level on a heading of {heading} degrees")
        check(vehicle_z(rt) == cruise,
              f"flight: levelling her off on a heading of {heading} cost her "
              f"height (z {vehicle_z(rt)})")

    # And she really is put right when she is really tipped -- at a heading
    # where the angles read 180, which is where the old test could not tell a
    # tipped ship from a turned one.
    rt.run(f"""
        local v = TREK.Vehicle.ship()
        v:setHeading(135)
        -- 40 degrees of roll on top of that heading.
        v:setAngles(v:getAngleX(), v:getAngleY(), v:getAngleZ() - 40)
    """)
    check(rt.eval("TREK.Vehicle.ship():uprightness()") < 0.9,
          "flight: the simulation would not let her tip at all, so the rescue "
          "below proves nothing")
    net.pump(40)
    check(rt.eval("TREK.Vehicle.ship():uprightness()") > 0.99,
          "flight: she was left lying over on her side")
    got = rt.eval("TREK.Vehicle.ship():heading()")
    check(abs(((got - 135) + 180) % 360 - 180) < 25.0,
          f"flight: righting her swung her nose from 135 to {got:.1f}")

    # --- the tricorder reads the ground from up here -----------------------
    # A sweep reads the deck it is standing on, and three levels up that deck
    # is empty sky: every zombie in the county is at z 0 and every crystal
    # with them. Taken from a seat in a flying shuttle it reads *downwards*
    # instead, every level from the ground up to the ship -- which is what
    # makes the instrument any use for finding a town worth landing at.
    rt.run("""
        SIM.zombies = {}
        local p = SIM.players[1]
        local px, py = math.floor(p:getX()), math.floor(p:getY())
        for i = 1, 6 do SIM.zombie(px + i, py + 1, 0) end
        -- One on a first floor, which is still below her and still hers.
        SIM.zombie(px + 2, py + 2, 1)
        local cell = getCell()
        cell:getOrCreateGridSquare(px + 3, py, 0)
            :AddWorldInventoryItem(TREK.Config.DilithiumItem)
        -- And one a floor up, which is between her and the ground: a survey
        -- that only read the bottom level would miss every crystal in every
        -- upstairs room in the town.
        cell:getOrCreateGridSquare(px - 2, py + 1, 1)
            :AddWorldInventoryItem(TREK.Config.DilithiumItem)
        SIM.notes = {}
    """)
    check(rt.eval(f"SIM.players[1]:getZ()") == cruise,
          f"flight: the pilot reports z {rt.eval('SIM.players[1]:getZ()')} in a "
          f"ship at level {cruise} -- the sweep below would prove nothing")
    check(rt.eval(f"TREK.MedKit.startSweep({P})") is True,
          "flight: the tricorder would not sweep from the cockpit")
    slices = 0
    while rt.eval("TREK.MedKit.sweeping()") and slices < 600:
        rt.run("TREK.MedKit.serviceSweep()")
        slices = slices + 1
    aloft = rt.eval("TREK.MedKit.lastSweep.aloft")
    found = int(rt.eval("TREK.MedKit.lastSweep.total") or -1)
    crystals = int(rt.eval("TREK.MedKit.lastSweep.crystalTotal") or -1)
    check(aloft is True,
          "flight: a sweep from the cockpit at cruise does not know it is a "
          "ground survey, so the panel will call it a sensor sweep")
    check(found == 7,
          f"flight: the sweep found {found} contacts from the air, not the 7 "
          f"on the ground below her (six at z 0 and one on a first floor)")
    check(crystals == 2,
          f"flight: the sweep found {crystals} dilithium traces from the air, "
          f"not the two below her -- one on the ground and one a floor up")

    # And on the deck it is still one level. The ship is the only reason to
    # look down, and a sweep on foot that started reading through floors would
    # be a different instrument.
    rt.run("""
        local p = SIM.players[1]
        SIM.aloftPlayer = p
        p.vehicleWas = p.vehicle
        p.vehicle = nil
    """)
    net.clock += int(rt.eval("TREK.Config.SweepIntervalMs")) + 100
    rt.run(f"TREK.MedKit.startSweep({P})")
    slices = 0
    while rt.eval("TREK.MedKit.sweeping()") and slices < 600:
        rt.run("TREK.MedKit.serviceSweep()")
        slices = slices + 1
    check(rt.eval("TREK.MedKit.lastSweep.aloft") is False,
          "flight: a sweep taken out of the seat still calls itself a ground "
          "survey")
    rt.run("SIM.players[1].vehicle = SIM.players[1].vehicleWas")

    # --- there is no altitude to set --------------------------------------
    # Not "the ceiling refuses politely": the command is gone. A handler that
    # accepts a request and quietly does nothing is the shape this project
    # keeps paying for, so `setAltitude` was deleted from both ends and the
    # protocol check below is what would notice it coming back.
    check(rt.eval("TREK.Net.serverHandlers.setAltitude") is None,
          "flight: the server still handles setAltitude, so something can still "
          "ask her to change height")
    check(rt.eval("TREK.Flight.climb") is None and rt.eval("TREK.Flight.dive") is None,
          "flight: TREK.Flight still has climb/dive")

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
    #
    # Back to wherever the ship actually is, at the level she is actually
    # flying at. She has been driven some way from the take-off point, and
    # standing where she *was* is standing on nothing.
    rt.run("""
        -- From the ship's recorded position, not from the vehicle: standing in
        -- the cabin means the ship's chunks are not loaded here, so
        -- TREK.Vehicle.find cannot see it at all.
        local p = SIM.players[1]
        local s = TREK.Util.state()
        local lvl = s.level or TREK.Config.FlightLevel
        p.x, p.y = s.x + 0.5, s.y + 0.5
        p.z, p.lastZ = lvl, lvl
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

    # --- floors left by some older flight get found and lifted -------------
    # The ship's record only remembers the flight it is on. Earlier flights --
    # and earlier builds, which laid a far wider plane -- left their floors in
    # the world, and a floor is a saved world object. They were still there as
    # a black blotch long after the plane itself was down to 25 squares, so the
    # tidy-up must not consult the record: it has to go and look.
    #
    # On ground the tidy-up has not been over yet: the pilot gets out and
    # walks forty squares to where an old flight left its floors. (Planted
    # beside the landing site, they would be on ground this client had already
    # swept -- the sweep runs as soon as she is down -- and a sweep that
    # re-walked ground it had just cleared would be walking it for ever.)
    lx, ly = ship(rt, "x") + 40, ship(rt, "y")
    rt.run(f"""
        for dx = -6, 6 do for dy = -6, 6 do
            SIM.rawSquare({lx} + dx, {ly} + dy, 3):addFloor("invisible_01_0")
        end end
        local p = SIM.players[1]
        local v = TREK.Vehicle.ship()
        if v then v:exit(p) end
        p.vehicle = nil
        p.x, p.y, p.z, p.lastZ = {lx} + 0.5, {ly} + 0.5, 0, 0
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

    # --- beaming out of a hovering ship sends her back up ------------------
    # The way out of a ship in the air is the transporter and nothing else --
    # the hatch is shut (above) and the seat cannot be stepped out of. So the
    # last beam is the last person aboard, and what she must not do then is
    # come down where she happens to be: five tonnes of shuttle onto whatever
    # is underneath her, which may be a roof, a pond or a horde. She goes back
    # up, exactly as a recall sends her up from the ground, and the crew call
    # her down again.
    rt.run(f"""
        local p = SIM.players[1]
        p.x, p.y = {lx} - 40 + 2.5, {ly} + 0.5
        p.z, p.lastZ = 0, 0
    """)
    net.pump(20)
    seat(rt)
    rt.run(f"TREK.Flight.takeOff({P})")
    net.pump(400)
    check(ship(rt, "flying") is True, "flight: she would not go up a second time")
    rt.notes()      # drain, so the note below is this beam's

    rt.run(f"TREK.Transport.beamDown({P})")
    # Watched all the way down. The failure this guards was not the
    # destination, it was the second and a half in between: out of the seat,
    # standing on a small island of invisible floor with the engine drawing
    # that level and culling everything below it. Black screen. At no point may
    # the character be out of the seat and off the ground.
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
    net.pump(600)
    px, py, pz = pos(rt)
    check(pz == 0,
          f"flight: beamed out of the air and ended at z {pz}, not on the ground")
    check(ship(rt, "flying") is None,
          "flight: she is still recorded as flying with nobody aboard her")
    check(ship(rt, "landed") is False,
          f"flight: nobody is aboard and she is still down here "
          f"(landed={ship(rt, 'landed')}) instead of back up")
    check(shuttles(rt) == 0,
          "flight: she went back up and left her vehicle hanging in the sky")
    check(rt.eval("TREK.Sky.count()") == 0,
          "flight: she went back up and left her invisible floors behind")
    check(any("IGUI_TREK_BackUp" in n for n in rt.notes()),
          "flight: the ship vanished out of the sky and told nobody; from "
          "inside the game that is indistinguishable from losing her")

    # And she can be called down again, which is the whole point of going up
    # rather than falling over -- and she must arrive **landed**. A call-down
    # with `flying` still set spawns her on the ground and every client then
    # paves a plane under her and lifts her straight back into the air: "it is
    # called in hover state so I cannot enter". Seen in game.
    rt.run(f"TREK.Menu.onCallDown(nil, {P}, {px} + 6, {py}, 0)")
    net.pump(120)
    check(ship(rt, "landed") is True,
          "flight: she went back up and could not be called down again")
    check(ship(rt, "flying") is None,
          "flight: she was called down still flying, so she will be lifted "
          "back into hover and nobody can get in")
    check(vehicle_z(rt) == 0,
          f"flight: she was called down and is at z {vehicle_z(rt)}, hovering")
    check(rt.eval("TREK.Sky.count()") == 0,
          "flight: a sky plane is being held under a landed ship")

    for w in rt.warnings():
        fail(f"flight: {w}")
    print("flight: take-off, the sky plane, levelling her off without losing "
          "her heading, the shut hatch, the pilot going aft, the landing, the "
          "beam that sends her back up and the tidy-up all checked")


# ---------------------------------------------------------------------------
# Climbing to the flight level, and coming back down
# ---------------------------------------------------------------------------
LU = 2.4494900703430176


def path(rt):
    """The body's heights, tick by tick, since SIM.trackPath was switched on."""
    return rt.eval("""(function()
        local out = {}
        for _, e in ipairs(SIM.path or {}) do
            table.insert(out, string.format("%.4f,%d,%d,%s", e.y, e.z, e.band,
                                            tostring(e.above or "-")))
        end
        return table.concat(out, ";")
    end)()""") or ""


def samples(rt):
    out = []
    for e in (path(rt).split(";") if path(rt) else []):
        y, z, band, above = e.split(",")
        out.append((float(y) / LU, int(z), int(band),
                    None if above == "-" else int(above)))
    return out


def body_level(rt):
    return rt.eval("(TREK.Vehicle.ship() and TREK.Vehicle.ship():getBulletY() or 0)") / LU


def markers(rt):
    return rt.eval("""(function()
        local out = {}
        for _, m in ipairs(SIM.liveMarkers()) do
            table.insert(out, string.format("%d,%d,%d,%s,%s", m.x, m.y, m.z,
                                            tostring(m.texture), tostring(m.r)))
        end
        return table.concat(out, ";")
    end)()""") or ""


def check_travel(label, got, going_up):
    """What every ascent and descent has to be: smooth, one way, honest about
    its level on the way, and never passing a floor laid above her."""
    check(len(got) > 20,
          f"{label}: only {len(got)} ticks of movement -- she is being "
          f"teleported, not carried")
    worst = 0.0
    backwards = 0
    for (a, _, _, _), (b, _, _, _) in zip(got, got[1:]):
        step = b - a
        worst = max(worst, abs(step))
        if (going_up and step < -0.02) or (not going_up and step > 0.02):
            backwards += 1
    check(worst <= 0.2,
          f"{label}: she jumped {worst:.2f} levels in one tick; the crew see "
          f"a teleport, not a climb")
    check(backwards == 0,
          f"{label}: she went the wrong way {backwards} time(s) on the way "
          f"{'up' if going_up else 'down'} -- something let her fall")
    wrong_z = [(lvl, z, band) for lvl, z, band, _ in got if band >= 1 and z != band]
    check(not wrong_z,
          f"{label}: {len(wrong_z)} tick(s) in the air with the engine's z "
          f"not her level (first: body level {wrong_z[0][0]:.2f}, z {wrong_z[0][1]}) "
          f"-- drawn and collided on the ground while she is in the air"
          if wrong_z else "")
    shelves = [(lvl, above) for lvl, _, _, above in got if above is not None]
    check(not shelves,
          f"{label}: a floor of ours stood above her body {len(shelves)} "
          f"time(s) (first: body {shelves[0][0]:.2f}, floor at level "
          f"{shelves[0][1]}) -- a shelf in the physics engine, which is what "
          f"tipped her over" if shelves else "")


def flight_ascent():
    """Take-off to the one flight level, and the landing, as the crew see them.

    The climb that failed in game lifted her in one teleport onto a floor the
    physics engine had not been told about yet; she tipped back onto the level
    below and the re-lift then held her there every tick. The simulation's
    floors now reach its physics three ticks after they reach the map, so a
    let-go that does not wait for them sinks here as it did there.
    """
    P = "SIM.players[1]"
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('pilot', 3000.5, 3000.5, 0)")
    net.start()
    net.pump(5)
    rt.run(f"TREK.Menu.onCallDown(nil, {P}, 3004, 3000, 0)")
    net.pump(40)
    check(ship(rt, "landed") is True, "ascent: the ship would not land to start with")
    seat(rt)
    L = rt.eval("TREK.Config.flightLevel()")
    rings = rt.eval("#TREK.Config.ShadowRings")

    check(markers(rt) == "", "ascent: a shadow is drawn under a ship on the ground")

    # --- up -------------------------------------------------------------------
    rt.run("SIM.trackPath = true; SIM.path = {}")
    rt.run(f"TREK.Flight.takeOff({P})")
    net.pump(60)
    # Part way up: the shadow is already on the ground under her, which is the
    # whole point of it -- where she would come down, while she is going up.
    mid = body_level(rt)
    check(0.5 < mid < L,
          f"ascent: a second in, her body is at level {mid:.2f}; she should be "
          f"on her way up")
    vx, vy = rt.eval("math.floor(TREK.Vehicle.ship():getX())"), \
        rt.eval("math.floor(TREK.Vehicle.ship():getY())")
    got = [m.split(",") for m in markers(rt).split(";") if m]
    check(len(got) == rings,
          f"ascent: {len(got)} shadow ring(s) drawn part way up, not {rings}")
    check(all(int(m[0]) == vx and int(m[1]) == vy and int(m[2]) == 0 for m in got),
          f"ascent: the shadow is at {got[:1]}, not on the ground at {vx},{vy},0 "
          f"-- the square she would be set down on")
    check(all(m[3] == "circle_center" and float(m[4]) == 0 for m in got),
          f"ascent: the shadow rings are {got[:1]}: the renderer draws only "
          f"circle_center, and a shadow has to be black")
    # Tick by tick to the top: whenever she has been let go, the column must
    # already be gone. One square under a hull three wide is a pivot, not a
    # support -- caught on it she reads as holding, and in game she tips.
    pivots = 0
    for _ in range(340):
        net.pump(1)
        if rt.eval("TREK.Flight.movePhase()") == "watch" and rt.eval("TREK.Sky.columnHeld()"):
            pivots += 1
    check(pivots == 0,
          f"ascent: she was let go with the column still under her for {pivots} "
          f"tick(s) -- one square under a hull three wide is a pivot")
    up = [e for e in samples(rt)]
    check(ship(rt, "flying") is True, "ascent: she never got up")
    check(vehicle_z(rt) == L, f"ascent: the engine has her at z {vehicle_z(rt)}, not {L}")
    top = next((i for i, e in enumerate(up) if e[0] >= L), None)
    check(top is not None, "ascent: her body never reached the flight level")
    if top is not None:
        check_travel("ascent", up[:top + 1], True)
        after = [e[0] for e in up[top:]]
        low = min(after) if after else L
        check(low >= L - 0.02,
              f"ascent: she sank to level {low:.2f} after reaching {L} -- let "
              f"go onto a floor the physics had not heard of yet, which is the "
              f"tip-and-fall the climb used to produce")
    check(rt.eval("TREK.Sky.columnHeld()") is False,
          "ascent: the column that carried her up is still standing under her")
    check(rt.eval("TREK.Flight.moving()") is False, "ascent: the move never finished")

    # --- the obstacle guard ------------------------------------------------
    # A wall at her own level, ahead of her. She is slowed to a crawl short of
    # it, told why, and given her speed back the moment she turns away.
    vid = ship_vehicle(rt)
    x0 = rt.eval("TREK.Vehicle.ship():getX()")
    y0 = rt.eval("TREK.Vehicle.ship():getY()")
    wx = int(x0) + 12
    rt.run(f"for dy = -3, 3 do SIM.rawSquare({wx}, {int(y0)} + dy, {L}).wallW = true end")
    top_speed = rt.eval("TREK.Flight.speed()")
    rt.run("SIM.notes = {}")
    x = x0
    for _ in range(12):
        x += 0.5
        rt.run(f"SIM.driveVehicle({vid}, {x}, {y0})")
        net.pump(1)
    near = rt.eval("TREK.Vehicle.ship():getMaxSpeed()")
    check(near < top_speed,
          f"ascent: flying at a wall {wx - x:.1f} squares ahead at her own level, "
          f"her top speed is still {near}")
    check(any("IGUI_TREK_WallAhead" in n for n in rt.notes()),
          "ascent: the guard slowed her and did not say why")
    for _ in range(8):
        x += 0.5
        rt.run(f"SIM.driveVehicle({vid}, {x}, {y0})")
        net.pump(1)
    close = rt.eval("TREK.Vehicle.ship():getMaxSpeed()")
    check(close <= rt.eval("TREK.Config.GuardCrawl") + 8,
          f"ascent: {wx - x:.1f} squares from a wall she may still do {close}")
    for _ in range(6):
        x -= 0.5
        rt.run(f"SIM.driveVehicle({vid}, {x}, {y0})")
        net.pump(1)
    check(rt.eval("TREK.Vehicle.ship():getMaxSpeed()") == top_speed,
          f"ascent: turned away from the wall, her top speed is still "
          f"{rt.eval('TREK.Vehicle.ship():getMaxSpeed()')}, not {top_speed}")
    # Walls below her level are what she flies over: no slowing for those.
    rt.run(f"for dy = -3, 3 do SIM.rawSquare({wx}, {int(y0)} + dy, {L}).wallW = nil "
           f"SIM.rawSquare({wx}, {int(y0)} + dy, {L - 1}).wallW = true end")
    for _ in range(8):
        x += 0.5
        rt.run(f"SIM.driveVehicle({vid}, {x}, {y0})")
        net.pump(1)
    check(rt.eval("TREK.Vehicle.ship():getMaxSpeed()") == top_speed,
          "ascent: she was slowed for a building shorter than her flight level")
    check(vehicle_z(rt) == L, f"ascent: the guard cost her height (z {vehicle_z(rt)})")

    # Somewhere else entirely before coming down: thirty squares south, well
    # past the stride at which the litter sweep looks at fresh ground -- the
    # sweep that must not run while she is being carried down, because the
    # column under her is exactly the kind of floor it hunts.
    for _ in range(60):
        y0 += 0.5
        rt.run(f"SIM.driveVehicle({vid}, {x}, {y0})")
        net.pump(1)
    vx, vy = int(x), int(y0)
    got = [m.split(",") for m in markers(rt).split(";") if m]
    check(len(got) == rings and all(int(m[0]) == vx and int(m[1]) == vy
                                    and int(m[2]) == 0 for m in got),
          f"ascent: flown to {vx},{vy}, her shadow is at {got[:1]} -- it has to "
          f"follow her, on the ground")

    # --- down -----------------------------------------------------------------
    rt.run("SIM.path = {}")
    rt.run(f"TREK.Flight.land({P})")
    net.pump(260)
    down = samples(rt)
    check(ship(rt, "landed") is True and ship(rt, "flying") is None,
          "descent: she did not come down")
    check(body_level(rt) < 0.2,
          f"descent: her body is at level {body_level(rt):.2f}, not on the ground")
    if down:
        check_travel("descent", [e for e in down if e[0] > 0.12], False)
    check(rt.eval("TREK.Sky.count()") == 0 and rt.eval("TREK.Sky.columnHeld()") is False,
          "descent: floors left standing in the sky after she landed")
    check(markers(rt) == "", "descent: the shadow outlived the flight")
    check(any("IGUI_TREK_Landed" in n for n in rt.notes()),
          "descent: nobody was told she had landed")
    check(ship(rt, "z") == 0, f"descent: the ground she stands on is recorded as {ship(rt, 'z')}")

    for w in rt.warnings():
        fail(f"ascent: {w}")
    print(f"ascent: she is carried up to level {L} and down again a little at a "
          f"time, never past a floor above her, held until the physics has the "
          f"plane, with a shadow on the ground under her and a guard that slows "
          f"her short of a wall at her own height")


def flight_refused():
    """The engine will not hold her height: the take-off gives up and brings
    her down, and in flight she is carried back only so many times -- not
    teleported upward every tick for ever, which was "stuck"."""
    P = "SIM.players[1]"

    # --- at take-off ------------------------------------------------------
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('pilot', 3000.5, 3000.5, 0)")
    net.start()
    net.pump(5)
    rt.run(f"TREK.Menu.onCallDown(nil, {P}, 3004, 3000, 0)")
    net.pump(40)
    seat(rt)
    L = rt.eval("TREK.Config.flightLevel()")
    rt.run(f"SIM.physicsRefuse = {{ [{L}] = true }}")
    rt.run(f"TREK.Flight.takeOff({P})")
    net.pump(1200)
    check(ship(rt, "flying") is None,
          "refused: the state says she is flying on a height the engine never held")
    check(body_level(rt) < 0.2,
          f"refused: she was left at level {body_level(rt):.2f} instead of being "
          f"brought back down")
    check(rt.eval("TREK.Flight.moving()") is False,
          "refused: the take-off never stopped trying")
    check(rt.eval("TREK.Sky.count()") == 0 and rt.eval("TREK.Sky.columnHeld()") is False,
          "refused: the floors of a failed take-off were left in the sky")
    check(any("IGUI_TREK_NoLift" in n for n in rt.notes()),
          "refused: the pilot was not told she could not go up")
    warns = rt.warnings()
    check(any("will not hold her" in str(w) for w in warns),
          "refused: the log does not say the engine refused the height")
    for w in warns:
        if "sank to level" not in str(w) and "will not hold her" not in str(w):
            fail(f"refused: {w}")

    # --- a storey under her is not her level ------------------------------
    # She takes off beside a building one storey lower than her hover height,
    # the plane will not hold, and she sinks onto its top floor: a fraction of
    # a level down, and the engine's z now says the storey, not her level.
    # Measured by height alone that is "holding".
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('pilot', 3000.5, 3000.5, 0)")
    net.start()
    net.pump(5)
    rt.run(f"TREK.Menu.onCallDown(nil, {P}, 3004, 3000, 0)")
    net.pump(40)
    seat(rt)
    rt.run(f"""
        SIM.physicsRefuse = {{ [{L}] = true }}
        local v = TREK.Vehicle.ship()
        SIM.rawSquare(math.floor(v:getX()), math.floor(v:getY()), {L - 1})
            :addFloor("floors_interior_tilesandwood_01_1")
    """)
    rt.run(f"TREK.Flight.takeOff({P})")
    net.pump(1200)
    check(ship(rt, "flying") is None,
          "refused: she came to rest on a storey below her level and was "
          "recorded as flying at it")
    for w in rt.warnings():
        if "sank to level" not in str(w) and "will not hold her" not in str(w):
            fail(f"refused (storey): {w}")

    # --- in flight ----------------------------------------------------------
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
    check(ship(rt, "flying") is True, "refused: she never got up to begin with")
    rt.run(f"SIM.physicsRefuse = {{ [{L}] = true }}; SIM.notes = {{}}")
    net.pump(1800)
    check(any("IGUI_TREK_CannotHold" in n for n in rt.notes()),
          "refused: she keeps falling off her level and the pilot was never "
          "told to set her down")
    before = rt.eval("SIM.transformCalls or 0")
    net.pump(300)
    after = rt.eval("SIM.transformCalls or 0")
    check(after == before,
          f"refused: {after - before} more placements after giving up -- she is "
          f"still being held in place, which is the old 'stuck'")
    # And she can still be set down: the pilot's way out works.
    rt.run(f"SIM.physicsRefuse = nil; TREK.Flight.land({P})")
    net.pump(300)
    check(ship(rt, "landed") is True and ship(rt, "flying") is None,
          "refused: after giving up on the height she could not be set down")
    check(rt.eval("TREK.Sky.count()") == 0, "refused: floors left behind after the landing")
    for w in rt.warnings():
        if not any(k in str(w) for k in ("sank to level", "keeps falling off")):
            fail(f"refused (in flight): {w}")
    print("refused: a height the engine will not hold brings her back down at "
          "take-off, and in flight she is carried back a few times and then "
          "left for the pilot to land, not held in place for ever")


def flight_two_machines():
    """A crewman on the street watches her go up and come down: her height
    reaches his machine by the vehicle's own sync, he draws her shadow himself,
    and when she lands his own copy of the plane is lifted."""
    net = Net("mp", clients=("alice", "bob"))
    srv, A, B = net.server, net.clients["alice"], net.clients["bob"]
    srv.run("SIM.player('alice', 3000.5, 3000.5, 0); SIM.player('bob', 3002.5, 3006.5, 0)")
    A.run("SIM.player('alice', 3000.5, 3000.5, 0)")
    B.run("SIM.player('bob', 3002.5, 3006.5, 0)")
    net.start()
    net.pump(5)
    P = "SIM.players[1]"
    A.run(f"TREK.Menu.onCallDown(nil, {P}, 3004, 3000, 0)")
    net.pump(60)
    check(ship(srv, "landed") is True, "two machines: she would not land to start with")
    for rt in (srv, A):
        rt.run("""
            local v = TREK.Vehicle.ship()
            for _, p in ipairs(SIM.players) do
                if p.name == 'alice' and v then v.seats[0] = p p.vehicle = v end
            end
        """)
    L = srv.eval("TREK.Config.flightLevel()")
    B.run("SIM.trackPath = true; SIM.path = {}")
    A.run(f"TREK.Flight.takeOff({P})")
    net.pump(60)
    check(B.eval("TREK.Vehicle.ship():getBulletY()") / LU > 0.5,
          "two machines: a second in, Bob's copy of her has not left the ground "
          "-- her height is not reaching him")
    check(len([m for m in markers(B).split(";") if m]) == srv.eval("#TREK.Config.ShadowRings"),
          "two machines: Bob sees her going up and no shadow under her")
    net.pump(400)
    check(ship(srv, "flying") is True, "two machines: she never got up")
    check(vehicle_z(B) == L, f"two machines: Bob sees her at z {vehicle_z(B)}, not {L}")
    check(B.eval("TREK.Sky.count()") > 0, "two machines: Bob laid no plane to draw her on")
    check(B.eval("TREK.Flight.moving()") is False,
          "two machines: Bob's machine tried to move a ship it does not drive")
    check(markers(srv) == "", "two machines: the server drew a shadow")

    A.run(f"TREK.Flight.land({P})")
    net.pump(300)
    check(ship(srv, "landed") is True and ship(srv, "flying") is None,
          "two machines: she did not come down")
    check(B.eval("TREK.Sky.count()") == 0,
          f"two machines: Bob's machine is still holding {B.eval('TREK.Sky.count()')} "
          f"squares of invisible floor over the landing site")
    check(vehicle_z(B) == 0, f"two machines: Bob sees her landed at z {vehicle_z(B)}")
    check(markers(B) == "", "two machines: Bob still draws a shadow under a landed ship")
    for name, c in (("alice", A), ("bob", B)):
        check(c.eval("SIM.clientWorldEdit") is None,
              f"two machines: {name} edited the world for something other than "
              f"the sky plane")
    for rt in net.all():
        for w in rt.warnings():
            fail(f"two machines ({rt.name}): {w}")
    print("two machines: the pilot's climb and landing reach a crewman's "
          "machine through the vehicle sync, he draws her shadow himself, and "
          "his plane comes up when she lands")


def flight_alone():
    """A hovering ship with nobody aboard, which is where the crew got stuck.

    Every symptom of the 2026-09-23 report is one line: the watchdog that
    notices nobody is aboard lived inside `if found`, and `found` is nil
    exactly when nobody is standing near her. A crew who beamed down and walked
    away left her flying for ever -- the hatch shut against them, recall
    refused, and a call-down arriving in hover.
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
    rt.run(f"TREK.Flight.takeOff({P})")
    net.pump(400)
    check(ship(rt, "flying") is True, "flight alone: she never got up")

    # --- forward to the cockpit: going aft must not be a one-way door ------
    # The hatch is shut while she hovers and the seat cannot be stepped out of,
    # so without a way forward again a pilot who went aft to read the helm
    # could never fly her. The cabin is faked here rather than built: what is
    # under test is the trip forward, not the arrival hold.
    rt.run("""
        local v = TREK.Vehicle.ship()
        v:exit(SIM.players[1])
        local x, y, z = TREK.Util.padSpot()
        SIM.rawSquare(x, y, z):addFloor("floors_interior_tilesandwood_01_1")
        local p = SIM.players[1]
        p.x, p.y = x + 0.5, y + 0.5
        p.z, p.lastZ = z, z
    """)
    net.pump(120)
    check(ship(rt, "flying") is True,
          "flight alone: she came down when the pilot went aft")
    check(rt.eval(f"TREK.Transport.toCockpit({P})") is True,
          "flight alone: the cabin offers no way forward to the cockpit")
    net.pump(500)
    check(rt.eval(f"{P}.vehicle") is not None,
          "flight alone: the pilot went aft in flight and could not get back "
          "to the cockpit -- that is a one-way door")
    check(ship(rt, "flying") is True,
          "flight alone: coming forward again brought her down")

    # --- and the watchdog reaches a ship nobody is anywhere near -----------
    sx, sy = ship(rt, "x"), ship(rt, "y")
    rt.run(f"""
        local v = TREK.Vehicle.ship()
        v:exit(SIM.players[1])
        local p = SIM.players[1]
        p.x, p.y, p.z, p.lastZ = {sx} + 300, {sy} + 300, 0, 0
        p.streamX, p.streamY = p.x, p.y
        SIM.notes = {{}}
    """)
    check(rt.eval("TREK.Vehicle.ship()") is None,
          "flight alone: her chunk is still loaded from 300 tiles away, so the "
          "case this whole section exists for cannot happen here")
    net.pump(1200)
    check(ship(rt, "flying") is None,
          "flight alone: nobody is aboard and nobody is near her, and she is "
          "still flying -- the watchdog only runs where her chunk is loaded, "
          "which is never the case when the crew have gone")
    check(ship(rt, "landed") is False,
          "flight alone: she stopped flying but is still recorded down here")
    check(any("IGUI_TREK_BackUp" in n for n in rt.notes()),
          "flight alone: she went back up and told nobody")

    # --- and she cannot be yanked out of the sky from under her pilot ------
    # `S.land` is reached by *Call her down* as well as by the helm, so a
    # crewman on the ground can ask for a ship somebody else is flying. Same
    # rule as a recall, and for the same reason: pulling her out of the sky
    # drops whoever is in her. The refusal has to name itself -- falling
    # through to "not enough room" sends them hunting for a bigger field.
    net3 = Net("sp")
    r3 = net3.server
    r3.run("SIM.player('pilot', 3000.5, 3000.5, 0)")
    net3.start()
    net3.pump(5)
    r3.run(f"TREK.Menu.onCallDown(nil, {P}, 3004, 3000, 0)")
    net3.pump(40)
    seat(r3)
    r3.run(f"TREK.Flight.takeOff({P})")
    net3.pump(400)
    check(ship(r3, "flying") is True, "flight alone: she never got up (call down)")
    r3.run("SIM.notes = {}")
    r3.run(f"TREK.Menu.onCallDown(nil, {P}, 3020, 3000, 0)")
    net3.pump(60)
    check(ship(r3, "flying") is True,
          "flight alone: she was called down out of the sky from under her "
          "own pilot")
    check(ship(r3, "x") != 3020,
          f"flight alone: she moved to {ship(r3, 'x')} while somebody was "
          f"flying her")
    check(any("IGUI_TREK_InFlight" in n for n in r3.notes()),
          "flight alone: the refused call-down blamed the room instead of "
          "saying somebody is flying her")

    # --- a hovering ship can be recalled, if she is empty ------------------
    net2 = Net("sp")
    r2 = net2.server
    r2.run("SIM.player('pilot', 3000.5, 3000.5, 0)")
    net2.start()
    net2.pump(5)
    r2.run(f"TREK.Menu.onCallDown(nil, {P}, 3004, 3000, 0)")
    net2.pump(40)
    seat(r2)
    r2.run(f"TREK.Flight.takeOff({P})")
    net2.pump(400)
    check(ship(r2, "flying") is True, "flight alone: she never got up (recall)")

    # With the pilot still in her, recall is refused: pulling her out from
    # under somebody leaves them standing on nothing.
    r2.run(f"TREK.Menu.onRecall(nil, {P})")
    net2.pump(30)
    check(ship(r2, "flying") is True,
          "flight alone: she was recalled out from under her own pilot")
    check(any("IGUI_TREK_InFlight" in n for n in r2.notes()),
          "flight alone: the refused recall said nothing")

    # Empty, it is the crew's own way of unsticking her. The pilot has left
    # her the only way there is off a hovering ship -- the transporter -- and
    # is standing on the ground nearby, not on the invisible floor five levels
    # up that the recall is about to take away.
    r2.run("""
        TREK.Vehicle.ship():exit(SIM.players[1])
        local p = SIM.players[1]
        p.x, p.z, p.lastZ = p.x + 8, 0, 0
    """)
    net2.pump(30)
    r2.run(f"TREK.Menu.onRecall(nil, {P})")
    net2.pump(60)
    check(ship(r2, "flying") is None,
          "flight alone: an empty hovering shuttle could not be recalled")
    check(ship(r2, "landed") is False,
          "flight alone: recalled out of hover and still recorded down here")
    check(shuttles(r2) == 0,
          "flight alone: recalled out of hover and her vehicle is still there")

    for r in (rt, r2, r3):
        for w in r.warnings():
            fail(f"flight alone: {w}")
    print("flight alone: the trip forward to the cockpit, a watchdog that "
          "reaches a ship nobody is near, a call-down refused from under her "
          "pilot, and a recall that unsticks an empty hovering shuttle")


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
    check(ship(rt, "landed") is False,
          "flight endings: her pilot died and she dropped herself onto whatever "
          "was underneath instead of going back up")

    # --- a world saved in flight opens on the ground ----------------------
    net2 = Net("sp")
    rt2 = net2.server
    rt2.run("""
        SIM.player('later', 3000.5, 3000.5, 0)
        local s = ModData.getOrCreate("TREK_State_v1")
        s.schema, s.landed, s.x, s.y, s.z = 2, true, 3004, 3000, 0
        -- Level 3 on purpose: a save from a build that still had four of them.
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

    # --- the old dilithium chamber ------------------------------------------
    # A Tool Cabinet at 1,3 held the crystals for one revision. The core is
    # the mod's own model now and what it holds is a number, so the cabinet
    # has to be named to be removed -- and **the crystals in it are the
    # hardest thing in the mod to come by**, so they are counted into the ship
    # rather than spilled with the rest.
    rt.run("""
        local C, U = TREK.Config, TREK.Util
        U.state().refitRev = nil
        U.state().crystals = 1
        local x, y = U.at(C.DilithiumSpot.x, C.DilithiumSpot.y)
        local sq = SIM.rawSquare(x, y, C.CabinZ)
        local o = SIM.object("location_business_machinery_01_33")
        o.square = sq
        o.modData.TREK = C.LegacyDilithiumTag
        o.container = SIM.container(20)
        o.container.parentObject = o
        for _ = 1, 4 do o.container:AddItem(C.DilithiumItem) end
        o.container:AddItem("OtherMod.TrekDilithium")
        o.container:AddItem("Base.Screwdriver")
        table.insert(sq.objects, o)
    """)
    rt.eval("TREK.Build.refitCabin()")

    cabinet = rt.eval("""(function()
        local C, U = TREK.Config, TREK.Util
        local x, y = U.at(C.DilithiumSpot.x, C.DilithiumSpot.y)
        for _, o in ipairs(SIM.rawSquare(x, y, C.CabinZ).objects) do
            if o.modData and o.modData.TREK == C.LegacyDilithiumTag then
                return true
            end
        end
        return false
    end)()""")
    check(cabinet is False,
          "refit: the old dilithium cabinet is still standing on the core's "
          "square, so the ship has two power plants drawn through each other")
    check(crystals_aboard(rt) == 5,
          f"refit: the ship kept {crystals_aboard(rt)} crystals across the "
          f"migration, not the one it had plus the four in the cabinet -- and "
          f"an impostor with the same bare type is not a fifth")

    # The screwdriver was the player's, so it is on the pad with everything
    # else the sweep displaced.
    tools = rt.eval("""(function()
        local C, U = TREK.Config, TREK.Util
        local x, y = U.at(C.Landing.x, C.Landing.y)
        local n = 0
        for _, w in ipairs(SIM.rawSquare(x, y, C.CabinZ).worldObjects or {}) do
            local it = w.item
            local id = it and (it.fullType or it:getFullType())
            if id == "Base.Screwdriver" then n = n + 1 end
        end
        return n
    end)()""")
    check(tools >= 1,
          "refit: what else was in the old chamber was destroyed rather than "
          "spilled onto the pad")

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
    # Nine: the galley's five, the three stocked lockers and the tape shelf.
    # Neither of the ship's two machines is among them -- the replicator stood
    # on a counter once and the warp core was a tool cabinet, and both of those
    # were fixtures leaning on other fixtures.
    check(containers == 9 and stocked == wanted,
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

    # --- the vault lock is each client's own -------------------------------
    # Every client takes the climb away from its own character and from
    # nobody else's, which is the only kind of write a client owns outright.
    # Doing it on the server instead would reach a character the server does
    # not move and would leave every real player climbing out of the hull.
    for c, who in ((A, "alice"), (B, "bob")):
        check(c.eval(f"{P}:isIgnoreAutoVault()") is True,
              f"multiplayer: {who}'s client did not lock the vault while "
              f"{who} is aboard")
        check(c.eval(f"SIM.climbOverWall({P}, 0, -1)") is False,
              f"multiplayer: {who} could climb over the cabin wall")
    check(srv.eval(f"{P}:isIgnoreAutoVault()") is not True,
          "multiplayer: the server set the vault flag on a character it does "
          "not move; every real client is still climbing out")

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
            -- Alice drives. On Bob's machine he is in the seat behind her:
            -- only one machine owns a vehicle's physics, and it is the
            -- driver's. (Both used to sit in seat 0 on their own copies, so
            -- both machines lifted her and nothing tested whether a crewman
            -- sees the pilot's ship rise.)
            -- And the server's copy has both of them where they are, because
            -- seats are synced: a server that thought Bob was not aboard would
            -- send her back up from under him the moment Alice was gone.
            for _, p in ipairs(SIM.players) do
                local seat = (p.name == "alice") and 0 or 1
                if v and (SIM_ROLE == "server" or p == SIM.players[1]) then
                    v.seats[seat] = p
                    p.vehicle = v
                end
            end
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
        check(z == srv.eval("TREK.Config.FlightLevel"),
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

    # A crewman who is not flying may not set her down.
    B.run(f"TREK.Flight.land({P})")
    net.pump(60)
    check(ship(srv, "flying") is True,
          "multiplayer: a passenger brought her down out of the pilot's hands")

    # And the heading she is flown on is hers, on both machines. The levelling
    # pass runs on every client that can see her, and the one that owns her
    # physics is the only one allowed to move her -- but the bug this guards
    # was worse than a disagreement: the old pass wrenched her rotation to the
    # identity whenever the pilot turned more than a quarter turn from her
    # spawn heading, because getAngleX reads 180 there for a ship that is dead
    # level. Reverse was the only direction that worked.
    for c in (A, B):
        c.run("TREK.Vehicle.ship():setHeading(150)")
    net.pump(60)
    for name, c in (("alice", A), ("bob", B)):
        got = c.eval("TREK.Vehicle.ship():heading()")
        check(abs(((got - 150) + 180) % 360 - 180) < 1.0,
              f"multiplayer: {name}'s copy of the shuttle was turned from 150 "
              f"degrees to {got:.1f}")

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
    # Bob is still in the seat behind her. Who counts as aboard is everybody,
    # not the recorded pilot (PILOTING.md, MULTIPLAYER.md): pulling the ship
    # out from under a living crewman because somebody else died would leave
    # him in a seat belonging to nothing. This used to assert the opposite and
    # pass, because the server's copy of the ship never had Bob in it at all.
    check(ship(srv, "flying") is True,
          "multiplayer: the pilot died and she was taken out from under the "
          "crewman still aboard")

    # And the last of the crew gone -- beamed down onto the street -- ends it,
    # on the server's own initiative, the way it always has.
    for rt in net.all():
        rt.run("""
            local v = TREK.Vehicle.ship()
            for _, p in ipairs(SIM.players) do
                if p.name == 'bob' then
                    if v then v.seats[1] = nil end
                    p.vehicle = nil
                    p.x, p.z, p.lastZ = p.x + 30, 0, 0
                end
            end
        """)
    net.pump(600)
    check(ship(srv, "flying") is None,
          "multiplayer: flight outlived its crew on a server")
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

    # **A floor on the count.** The check above compares two sets scraped out
    # of the source, and a pattern that stopped matching would make `sent`
    # empty -- at which point every command is handled, trivially, for ever.
    # Both sides of a lookup check need a floor; this one is the cheap half.
    check(len(sent) >= 20,
          f"static: only {len(sent)} client commands were found in client/. "
          f"The pattern that scrapes them has probably stopped matching, and "
          f"an empty set is not a passing check")
    check(len(handled) >= 20,
          f"static: only {len(handled)} server handlers were found")

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

    # --- every refusal the server can send has words behind it -------------
    # A `deny(player, "reason")` with no entry in TREK_Core's DENIALS table
    # arrives on the client and says *nothing at all* -- which from inside the
    # game is a menu option that silently does nothing, the one thing
    # TREK_Menu's own header forbids. This was a real gap before the EMH: the
    # table was kept in step by hand and nothing checked it.
    denials = set()
    for src in client.values():
        block = re.search(r"local DENIALS = \{(.*?)\n\}", src, re.S)
        if block:
            denials |= set(re.findall(r"^\s*(\w+)\s*=", block.group(1), re.M))
        # Two refusals are handled by name in the `denied` reply rather than
        # through the table, because they carry numbers a player needs.
        denials |= set(re.findall(r'args\.why == "(\w+)"', src))
    denied = set()
    for f, src in server.items():
        denied |= set(re.findall(r'deny\([^,]+,\s*"(\w+)"', src))
    check(len(denied) >= 15,
          f"static: only {len(denied)} deny() reasons were found in server/; "
          f"the pattern has stopped matching")
    for why in sorted(denied - denials):
        fail(f"static: the server denies {why!r} and TREK_Core.lua's DENIALS "
             f"has no line for it, so the refusal arrives and says nothing")

    # --- syncBodyPart is a no-op off the server ----------------------------
    # Its first instruction is `getstatic GameServer.server; ifeq -> return`.
    # Called from client/ it looks exactly like a sync and is nothing, which
    # is the "present, drawn and inert" shape this project has paid for six
    # times. shared/ is allowed: TREK_Medical.publish refuses on a client
    # itself, and the server is what calls it.
    for f, src in client.items():
        for n, line in enumerate(src.splitlines(), 1):
            if "syncBodyPart" in line.split("--", 1)[0]:
                fail(f"static: client/{f}:{n} calls syncBodyPart, which does "
                     f"nothing at all off the server")

    # --- and nothing sets the debug-only health cheat ----------------------
    # `ISHealthPanel.cheat` is `false or getDebug()` in vanilla and otherwise
    # admin-only: it would work for this developer under -debug and for nobody
    # on the Workshop. The per-instance `doctorLevel` is the real lever.
    for folder, files in (("client", client), ("server", server), ("shared", shared)):
        for f, src in files.items():
            for n, line in enumerate(src.splitlines(), 1):
                code = line.split("--", 1)[0]
                if re.search(r"ISHealthPanel\s*\.\s*cheat\s*=", code):
                    fail(f"static: {folder}/{f}:{n} assigns ISHealthPanel.cheat, "
                         f"which is debug-and-admin-only")

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

    # --- the lists are not empty --------------------------------------------
    # Every check below walks one of these. A check against an empty set is
    # not a check, and "the hypospray treated everything in Med.TREATMENTS"
    # passes triumphantly against a table somebody emptied.
    for name, floor in (("TREATMENTS", 8), ("SKIN", 8), ("CURE", 4)):
        n = int(rt.eval(f"#TREK.Medical.{name}"))
        check(n >= floor,
              f"medical: Med.{name} has {n} entries, fewer than the {floor} "
              f"every check that walks it assumes")

    # --- a dose, and what it must not touch ---------------------------------
    rt.run("""
        for _, what in ipairs({ "bleeding", "deepWound", "infectedWound", "burn",
                                "fracture", "pain", "stiffness", "health" }) do
            SIM.hurt(SIM.players[1], what, 1)
        end
        -- **The whole virus on that limb**, not just the bite: every field in
        -- Med.CURE, so the assertion below has something to be about. A test
        -- that infects a body by hand and then checks only what it set proves
        -- nothing at all.
        SIM.hurt(SIM.players[1], "infection", 2)
        SIM.sounds = {}
    """)
    # Which of the EMH's fields are actually set on that limb, before the
    # dose. Compared afterwards rather than asserted to be false: a field
    # that was never set is not evidence that a dose left it alone, and a
    # check that counts one is a check that passes for the wrong reason.
    before_cure = str(rt.eval("""(function()
        local p = SIM.players[1]:getBodyDamage().parts[2]
        local on = {}
        for _, t in ipairs(TREK.Medical.CURE) do
            if t.ask(p) then table.insert(on, t.key) end
        end
        return table.concat(on, ", ")
    end)()"""))
    check(before_cure != "",
          "medical: nothing in Med.CURE is set on the bitten limb, so the "
          "check that a dose leaves them alone has nothing to be about")
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

    # **Through Med.CURE, one named list**, so that the hypospray's promise and
    # the EMH's reason to exist cannot drift apart: `emh()` asserts the cure
    # clears every one of these and this asserts a dose clears none of them,
    # and both walk the same table. Adding an entry to Med.TREATMENTS that
    # touches any of them fails here.
    after_cure = str(rt.eval("""(function()
        local p = SIM.players[1]:getBodyDamage().parts[2]
        local on = {}
        for _, t in ipairs(TREK.Medical.CURE) do
            if t.ask(p) then table.insert(on, t.key) end
        end
        return table.concat(on, ", ")
    end)()"""))
    check(after_cure == before_cure,
          f"medical: a hypospray dose changed the EMH's fields on that limb "
          f"({before_cure!r} -> {after_cure!r}). Every field in Med.CURE is "
          f"the EMH's, and clearing any of them here is how a pocket item "
          f"quietly becomes the cure the whole game is built around")

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


def crystals_aboard(rt):
    """How many spare dilithium crystals the ship is holding.

    Asked of TREK.Power rather than read out of the ship state directly: the
    count is the answer to a question the rest of the mod asks that way, and a
    helper that re-implemented the read would be testing itself. That is a
    mistake this file has already made once, with the old chamber's container
    filter.
    """
    return int(rt.eval("TREK.Power.crystals()"))


def core_item(rt):
    """The warp core standing on its square: its yaw, or None."""
    return rt.eval("""(function()
        local C, U, P = TREK.Config, TREK.Util, TREK.Power
        local x, y = U.at(P.chamberSpot())
        for _, w in ipairs(SIM.rawSquare(x, y, C.CabinZ).worldObjects or {}) do
            local it = w.item
            if it and (it.fullType or it:getFullType()) == C.WarpCoreItem then
                return it:getWorldZRotation()
            end
        end
        return nil
    end)()""")


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


def core_menu(rt, ox, oy):
    """Right-clicks a cabin square and returns what the core offered."""
    rt.run(f"""
        local U = TREK.Util
        local tx, ty = U.at({ox}, {oy})
        local p = SIM.players[1]
        SIM.aim.dx = tx - p.x
        SIM.aim.dy = ty - p.y
        coreMenu = SIM.contextMenu()
        TREK.WarpCoreUI.fillMenu(0, coreMenu, {{}}, false)
    """)
    return str(rt.eval("coreMenu:labels()"))


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

    # A dropped item picks its own yaw: the engine writes Rand.Next(0, 360)
    # into worldZRotation when nobody has set it, which is right for a hammer
    # on the floor and wrong for a machine bolted to a bulkhead. The simulation
    # does the same thing with a fixed angle.
    def yaw():
        return rt.eval(f"""(function()
            local C, U, R = TREK.Config, TREK.Util, TREK.Replicator
            local ox, oy = R.spot()
            local x, y = U.at(ox, oy)
            for _, w in ipairs(SIM.rawSquare(x, y, C.CabinZ).worldObjects or {{}}) do
                local it = w.item
                local id = it and (it.fullType or it:getFullType())
                if id == C.ReplicatorItem then return it:getWorldZRotation() end
            end
            return -1
        end)()""")

    check(yaw() == 0,
          f"replicator: a freshly placed machine stands at {yaw()} degrees "
          f"rather than square to the ship")
    # The core is placed the same way and picks its own angle the same way,
    # and this has to be asked **before** anything rebuilds the cabin: a
    # rebuild takes the "already standing, straighten it" path, which would
    # quietly cover for a placement that never squared it up.
    check(core_item(rt) == 0,
          f"core: a freshly placed warp core stands at {core_item(rt)} degrees "
          f"rather than square to the ship")

    rt.eval("TREK.Build.buildCabin()")
    rt.eval("TREK.Build.buildCabin()")
    check(alcoves() == 1,
          f"replicator: rebuilding the cabin left {alcoves()} alcoves stacked "
          f"on the berth")

    # --- and an older save's machine is squared up --------------------------
    # A save made before that was understood has one standing at whatever the
    # dice gave it, and the build pass is the only thing that will ever touch
    # it again.
    rt.run(f"""
        local C, U, R = TREK.Config, TREK.Util, TREK.Replicator
        local ox, oy = R.spot()
        local x, y = U.at(ox, oy)
        for _, w in ipairs(SIM.rawSquare(x, y, C.CabinZ).worldObjects or {{}}) do
            if w.item and w.item.fullType == C.ReplicatorItem then
                w.item:setWorldZRotation(137)
            end
        end
    """)
    rt.eval("TREK.Build.buildCabin()")
    check(yaw() == 0,
          f"replicator: a machine left at an angle by an older save is still "
          f"at {yaw()} degrees after a rebuild")

    # --- the warp core ------------------------------------------------------
    # The fixture that holds the ship's dilithium. It is a world model on its
    # own square like the replicator, and what it holds is a number in the
    # ship state rather than a container -- a custom model cannot have one,
    # because a container comes from a tile sprite's properties.
    cores = int(rt.eval("""(function()
        local C, U, P = TREK.Config, TREK.Util, TREK.Power
        local x, y = U.at(P.chamberSpot())
        local n = 0
        for _, w in ipairs(SIM.rawSquare(x, y, C.CabinZ).worldObjects or {}) do
            local it = w.item
            local id = it and (it.fullType or it:getFullType())
            if id == C.WarpCoreItem then n = n + 1 end
        end
        return n
    end)()"""))
    check(cores == 1,
          f"core: {cores} warp cores stand amidships after the build, not 1")
    check(crystals_aboard(rt) == C("DilithiumIssue"),
          f"core: a fresh ship carries {crystals_aboard(rt)} spare crystals, "
          f"not {C('DilithiumIssue')}")

    # `spend` is an authority boundary shared by every powered system. A
    # negative value used to add power, and NaN could poison the persisted
    # reserve so every later comparison failed. Invalid costs must be refused
    # without changing the ship.
    rt.run("TREK.Util.state().power = 1234")
    for bad, label in (("-25", "negative"), ("0 / 0", "NaN"),
                       ("TREK.Config.PowerMax + 1", "oversized")):
        accepted = rt.eval(f"TREK.Power.spend({bad})")
        check(accepted is False,
              f"power: an invalid {label} spend was accepted")
        check(rep_energy(rt) == 1234,
              f"power: an invalid {label} spend changed the reserve to "
              f"{rep_energy(rt)}")
    rt.run("TREK.Util.state().power = TREK.Config.PowerMax")

    # Issued once, and keyed on the count being absent rather than on it being
    # zero: a crew who burned all three and came home empty must not be handed
    # three more by the next rebuild.
    rt.run("TREK.Util.state().crystals = 0")
    rt.eval("TREK.Build.buildCabin()")
    check(crystals_aboard(rt) == 0,
          f"core: rebuilding the cabin refilled an empty core with "
          f"{crystals_aboard(rt)} crystals -- dilithium is free after all")
    rt.run(f"TREK.Util.state().crystals = {int(C('DilithiumIssue'))}")

    # --- loading one in -----------------------------------------------------
    stand_at(rt, net, int(C("DilithiumSpot").x) + 1, int(C("DilithiumSpot").y))
    labels = core_menu(rt, int(C("DilithiumSpot").x), int(C("DilithiumSpot").y))
    check("IGUI_TREK_CoreLoad" in labels and "IGUI_TREK_CoreTake" in labels,
          f"core: standing at it, the menu offers {labels}")

    spares = crystals_aboard(rt)
    rt.run("SIM.notes = {}; SIM.log = {}")
    rt.run(f"TREK.Core.send({P}, 'loadCrystal', {{}})")
    net.pump(4)
    check(crystals_aboard(rt) == spares,
          f"core: it took a crystal off a player who had none "
          f"({crystals_aboard(rt)} aboard, was {spares})")
    check(any("IGUI_TREK_CoreNoCrystal" in n for n in rt.notes()),
          f"core: loading with nothing to load said nothing ({rt.notes()})")
    # **And it is a refusal, not a fault.** Asking with empty pockets has to
    # be turned away by the check at the top of the handler; without it the
    # code reaches for a crystal that is not there, and the read-back further
    # down catches the damage and denies with the very same message. Same
    # note, same outcome, one stray WARN -- which is the only thing that can
    # tell the two apart, and it is worth asserting for exactly that reason.
    check(rt.warnings() == [],
          f"core: an empty-handed player asking to load one made the ship "
          f"warn: {rt.warnings()}")

    # An impostor is not dilithium. The engine's recursive inventory search
    # compares the **bare** type, which is not namespaced, so another mod's
    # TrekDilithium comes back from it -- and would be free power.
    rt.run("""
        local p = SIM.players[1]
        p.inventory:AddItem(instanceItem("OtherMod.TrekDilithium"))
    """)
    rt.run("SIM.notes = {}")
    rt.run(f"TREK.Core.send({P}, 'loadCrystal', {{}})")
    net.pump(4)
    check(crystals_aboard(rt) == spares,
          "core: another mod's TrekDilithium loaded into the ship as fuel")

    rt.run("""
        local C = TREK.Config
        SIM.players[1].inventory:AddItem(instanceItem(C.DilithiumItem))
    """)
    check(carrying(rt, "TrekShuttle.TrekDilithium") == 1,
          "core: the test player is not carrying the crystal it just took")
    rt.run("SIM.notes = {}")
    rt.run(f"TREK.Core.send({P}, 'loadCrystal', {{}})")
    net.pump(4)
    check(crystals_aboard(rt) == spares + 1,
          f"core: loading a crystal left {crystals_aboard(rt)} aboard, not "
          f"{spares + 1}")
    check(carrying(rt, "TrekShuttle.TrekDilithium") == 0,
          "core: the crystal went into the ship and stayed in the player's "
          "pocket as well -- one crystal became two")

    # A Remove that did nothing would turn one crystal into an unlimited
    # supply: the ship would count a crystal in and the player would still be
    # holding it. The server counts the inventory before and after, and this
    # is the container that refuses to give anything up.
    rt.run("""
        local C = TREK.Config
        local inv = SIM.players[1].inventory
        inv:AddItem(instanceItem(C.DilithiumItem))
        inv.RemoveWas = inv.Remove
        inv.Remove = function() end
    """)
    stuck = crystals_aboard(rt)
    rt.run("SIM.notes = {}")
    rt.run(f"TREK.Core.send({P}, 'loadCrystal', {{}})")
    net.pump(4)
    check(crystals_aboard(rt) == stuck,
          f"core: a crystal that would not come out of the player's inventory "
          f"was counted into the ship anyway ({crystals_aboard(rt)} aboard, "
          f"was {stuck}) -- one crystal is now two")
    rt.run("""
        local inv = SIM.players[1].inventory
        inv.Remove = inv.RemoveWas
        -- Put the pocket back the way the checks below expect it, and drop
        -- the WARN this block exists to provoke: the ship complaining that a
        -- crystal would not come out is the pass condition, not a fault.
        local keep = {}
        for _, it in ipairs(inv.items) do
            if it.fullType ~= TREK.Config.DilithiumItem then
                table.insert(keep, it)
            end
        end
        inv.items = keep
        SIM.log = {}
    """)

    # --- and taking one back out --------------------------------------------
    check(carrying(rt, "TrekShuttle.TrekDilithium") == 0,
          "core: the test player is carrying a crystal before asking for one")
    rt.run("SIM.notes = {}")
    rt.run(f"TREK.Core.send({P}, 'takeCrystal', {{}})")
    net.pump(4)
    check(crystals_aboard(rt) == spares,
          f"core: taking one back left {crystals_aboard(rt)} aboard, not "
          f"{spares}")
    check(carrying(rt, "TrekShuttle.TrekDilithium") == 1,
          "core: the ship lost a crystal and the player never got it")

    # A full pack is the other way to lose one. The crystal is made into the
    # player's hands and **counted** before the ship's number goes down,
    # because a container at capacity drops what it is handed in silence --
    # and dilithium is the one item where losing one to that would matter.
    aboard = crystals_aboard(rt)
    rt.run("""
        local inv = SIM.players[1].inventory
        inv.capacityWas = inv.capacity
        inv.capacity = 0
    """)
    rt.run("SIM.notes = {}")
    rt.run(f"TREK.Core.send({P}, 'takeCrystal', {{}})")
    net.pump(4)
    check(crystals_aboard(rt) == aboard,
          f"core: the ship gave up a crystal the player could not carry "
          f"({crystals_aboard(rt)} aboard, was {aboard})")
    check(any("IGUI_TREK_CoreFull" in n for n in rt.notes()),
          f"core: a crystal that would not fit was refused silently "
          f"({rt.notes()})")
    rt.run("""
        local inv = SIM.players[1].inventory
        inv.capacity = inv.capacityWas
    """)

    # An empty core has none to give, and says so rather than handing over a
    # crystal it does not have.
    rt.run("TREK.Util.state().crystals = 0")
    rt.run("SIM.notes = {}")
    rt.run(f"TREK.Core.send({P}, 'takeCrystal', {{}})")
    net.pump(4)
    check(carrying(rt, "TrekShuttle.TrekDilithium") == 1,
          "core: an empty core still handed out a crystal")
    check(any("IGUI_TREK_CoreEmpty" in n for n in rt.notes()),
          f"core: an empty core refused without saying so ({rt.notes()})")
    check(crystals_aboard(rt) == 0,
          f"core: an empty core went to {crystals_aboard(rt)} crystals")

    # --- and you have to be standing at it ----------------------------------
    rt.run(f"TREK.Util.state().crystals = {int(C('DilithiumIssue'))}")
    far = core_menu(rt, 3, 0)
    check("IGUI_TREK_CoreLoad" not in far,
          f"core: right-clicking the armoury offered the core's menu ({far})")

    stand_at(rt, net, 3, 0)
    rt.run("SIM.notes = {}")
    held = carrying(rt, "TrekShuttle.TrekDilithium")
    rt.run(f"TREK.Core.send({P}, 'takeCrystal', {{}})")
    net.pump(4)
    check(carrying(rt, "TrekShuttle.TrekDilithium") == held,
          "core: a player across the cabin took a crystal out of it")
    check(any("IGUI_TREK_CoreFar" in n for n in rt.notes()),
          f"core: reaching it from across the cabin was refused silently "
          f"({rt.notes()})")
    stand_at(rt, net, int(C("ReplicatorSpot").x) + 1, int(C("ReplicatorSpot").y))

    # Empty the test player's pockets of dilithium before moving on: what
    # follows asks what the *replicator* has made, and a crystal carried out
    # of this block would be counted as one of its answers.
    rt.run("""
        local inv = SIM.players[1].inventory
        local keep = {}
        for _, it in ipairs(inv.items) do
            if not tostring(it.fullType):find("Dilithium") then
                table.insert(keep, it)
            end
        end
        inv.items = keep
    """)

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
        ("TrekShuttle.TrekDilithium",
         "the crystal that powers it -- a replicator that can make its own "
         "fuel has no limit at all, and the hunt for dilithium is the only "
         "thing giving the whole system stakes"),
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

    # --- nothing refills it for free -----------------------------------------
    # It used to come back on the world's clock, which made the replicator a
    # machine you waited at. The reserve is a dilithium crystal now: time does
    # nothing, and a crystal is the only thing that does.
    rt.run("TREK.Util.state().power = 10")
    for _ in range(6):
        rt.fire("EveryTenMinutes")
    rt.fire("EveryOneMinute")
    check(rep_energy(rt) == 10,
          f"replicator: an hour of game time put the reserve back to "
          f"{rep_energy(rt)} on its own -- crystals are then decoration")

    # --- a crystal is what brings it back ------------------------------------
    spares = crystals_aboard(rt)
    check(spares == C("DilithiumIssue"),
          f"replicator: a fresh ship carries {spares} spare crystals, not "
          f"{C('DilithiumIssue')}")

    net.clock += int(C("ReplicatorCooldownMs")) + 500
    held = carrying(rt, "Base.Hammer")
    rt.run("SIM.notes = {}")
    rt.run(f"TREK.Core.send({P}, 'replicate', {{ id = 'Base.Hammer', count = 1 }})")
    net.pump(4)
    check(carrying(rt, "Base.Hammer") == held + 1,
          "replicator: with 10 units left and crystals aboard it refused "
          "rather than loading one")
    check(crystals_aboard(rt) == spares - 1,
          f"replicator: it made something on an empty reserve without taking "
          f"a crystal ({crystals_aboard(rt)} left of {spares})")
    check(rep_energy(rt) == C("PowerMax") - 24,
          f"replicator: after loading a crystal the reserve is "
          f"{rep_energy(rt)}, not a full {C('PowerMax')} less the hammer")

    # A reserve above the maximum reads as the maximum. Tuning DilithiumCharge
    # down in a later revision would otherwise leave every existing save with
    # a bar past the end of its own gauge.
    rt.run("TREK.Util.state().power = TREK.Config.PowerMax * 3")
    check(rep_energy(rt) == C("PowerMax"),
          f"replicator: a reserve of three crystals' charge reads as "
          f"{rep_energy(rt)}, not the one crystal the core burns at a time")

    # --- and when there are none, it stops -----------------------------------
    rt.run("""
        local U = TREK.Util
        U.state().crystals = 0
        U.state().power = 1
    """)
    net.clock += int(C("ReplicatorCooldownMs")) + 500
    held = carrying(rt, "Base.Hammer")
    rt.run("SIM.notes = {}")
    rt.run(f"TREK.Core.send({P}, 'replicate', {{ id = 'Base.Hammer', count = 1 }})")
    net.pump(4)
    check(carrying(rt, "Base.Hammer") == held,
          "replicator: it made something with a flat reserve and an empty "
          "core -- the power system has no floor at all")
    check(any("IGUI_TREK_RepNoCrystal" in n for n in rt.notes()),
          f"replicator: with no dilithium left the refusal blamed something "
          f"else ({rt.notes()})")

    # Put the ship back on its feet for the checks that follow.
    rt.run("""
        local C, U = TREK.Config, TREK.Util
        U.state().crystals = 1
        U.state().power = C.PowerMax
    """)

    # --- an impossible cost does not eat a crystal ---------------------------
    # Nothing in the game costs more than a crystal holds today, so this is
    # reached by making the crystal small rather than the hammer dear. The
    # failure it guards against is the worst kind: the player loses the
    # crystal *and* is refused, with nothing on screen tying the two together.
    net.clock += int(C("ReplicatorCooldownMs")) + 500
    spares = crystals_aboard(rt)
    held = carrying(rt, "Base.Hammer")
    rt.run("SIM.notes = {}")
    rt.run("""
        TREK.Config.PowerMax = 10
        TREK.Util.state().power = 10
    """)
    rt.run(f"TREK.Core.send({P}, 'replicate', {{ id = 'Base.Hammer', count = 1 }})")
    net.pump(4)
    check(carrying(rt, "Base.Hammer") == held,
          "replicator: it made a hammer no crystal in the ship could pay for")
    check(crystals_aboard(rt) == spares,
          f"replicator: it burned a crystal for a cost the crystal could not "
          f"cover ({crystals_aboard(rt)} left of {spares})")
    rt.run("""
        TREK.Config.PowerMax = TREK.Config.DilithiumCharge
        TREK.Util.state().power = TREK.Config.PowerMax
    """)

    # --- the tricorder is how they are found ---------------------------------
    # The crystals cannot be replicated, so the only way to get one is to walk
    # out and look -- and the tricorder is the instrument that makes that a
    # search rather than a wander. Both halves are under test: a crystal lying
    # on the ground and a crystal shut inside a container, which is where
    # every one of them in the world actually starts.
    net.clock += int(C("SweepIntervalMs")) + 100
    inChamber = crystals_aboard(rt)
    rt.run("""
        local C, U = TREK.Config, TREK.Util
        local p = SIM.players[1]
        local cell = getCell()
        -- Floored, as the sweep floors them: a player stands at x.5 and a
        -- square is an integer, and a crystal dropped at 1001.5 would sit on
        -- a square the tricorder never looks at.
        local px, py = math.floor(p:getX()), math.floor(p:getY())
        cell:getOrCreateGridSquare(px + 1, py, C.CabinZ)
            :AddWorldInventoryItem(C.DilithiumItem)
        -- Well past the mineral radius, which is shorter than the lifesign
        -- one: a sweep that answers with this is not an instrument, it is a
        -- map marker.
        cell:getOrCreateGridSquare(px + C.CrystalScanRadius + 6, py, C.CabinZ)
            :AddWorldInventoryItem(C.DilithiumItem)
    """)
    check(rt.eval(f"TREK.MedKit.startSweep({P})") is True,
          "replicator: the tricorder would not sweep for crystals")
    slices = 0
    while rt.eval("TREK.MedKit.sweeping()") and slices < 400:
        rt.run("TREK.MedKit.serviceSweep()")
        slices = slices + 1
    found = int(rt.eval("TREK.MedKit.lastSweep.crystalTotal") or -1)
    check(found == inChamber + 1,
          f"replicator: the tricorder found {found} crystals, not the "
          f"{inChamber + 1} in range ({inChamber} in the chamber and one on "
          f"the floor; the one {int(C('CrystalScanRadius')) + 6} tiles away is "
          f"not in range)")
    # And it says where. A total with no bearing is a number, not a search.
    rt.run("""
        SIM.plotted = 0
        for _, c in ipairs(TREK.MedKit.lastSweep.crystals or {}) do
            if math.abs(c.dx) <= TREK.Config.CrystalScanRadius
               and math.abs(c.dy) <= TREK.Config.CrystalScanRadius then
                SIM.plotted = SIM.plotted + c.n
            end
        end
    """)
    near = rt.eval("SIM.plotted")
    check(int(near or -1) == found,
          f"replicator: {found} crystals were counted but {near} of them were "
          f"plotted inside the radius -- the readout and the plot disagree")

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
    rt.run("TREK.Util.state().power = 0")
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
          f"patterns, scanning that keeps the item, a reserve nothing refills "
          f"for free, a crystal loaded from the chamber when it runs dry and a "
          f"refusal when the chamber is empty, the cooldown, a run counted item "
          f"by item, both range ends and all three sandbox values")


def emh_menu(rt, ox, oy):
    """Right-clicks a cabin square and returns what the EMH offered.

    The way a player actually reaches this feature. Driving the server
    handlers instead would pass against a build whose menu option was never
    added at all -- which is precisely how the torpedoes shipped unfireable
    and the replicator shipped un-right-clickable.
    """
    rt.run(f"""
        local U = TREK.Util
        local tx, ty = U.at({ox}, {oy})
        local p = SIM.players[1]
        SIM.aim.dx = tx - p.x
        SIM.aim.dy = ty - p.y
        emhMenu = SIM.contextMenu()
        TREK.EMHUI.fillMenu(0, emhMenu, {{}}, false)
    """)
    return str(rt.eval("emhMenu:labels()"))


def doctors(rt):
    """How many Doctors are standing on his square, and at what angle."""
    return rt.eval("""(function()
        local C, U = TREK.Config, TREK.Util
        local x, y = U.at(C.EmhSpot.x, C.EmhSpot.y)
        local n, yaw = 0, nil
        for _, w in ipairs(SIM.rawSquare(x, y, C.CabinZ).worldObjects or {}) do
            local it = w.item
            local id = it and (it.fullType or it:getFullType())
            if id == C.EmhItem then
                n = n + 1
                yaw = it:getWorldZRotation()
            end
        end
        return n, yaw
    end)()""")


def body(rt, part, field, who=1):
    return rt.eval(f"SIM.players[{who}]:getBodyDamage().parts[{part}].{field}")


def emh():
    """The Emergency Medical Hologram: the Doctor, the treatment and the cure.

    Three things in here are the ones worth having, and each of them is a
    failure this mod has already paid for once or would have paid for next:

      * **a dose still does not cure a bite, and the Doctor does.** Both
        halves go through Med.CURE, one named list, so the hypospray's promise
        and the EMH's reason to exist cannot drift apart. `medical()` asserts
        every field in that list survives a dose; this asserts every one of
        them is cleared by the cure, field by field, plus the body-level flags
        and the moodle that no packet carries;

      * **the cure is a commitment.** The crystal goes when the treatment
        starts, twelve game hours later it lands, and walking out of the cabin
        halfway through costs it. A refund would make the number decorative;

      * **the deck and the ship state are kept in step in both directions.**
        `s.emh` is the truth and B.serviceEMH makes the world match it, so a
        rebuild that deletes him puts him back and a dismissal that happened
        with the chunks unloaded heals itself. Everything about him is played
        here through the menu and the panel, never by calling a handler.
    """
    P = "SIM.players[1]"
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('emh', 1000.5, 1000.5, 0)")
    net.start()

    C = lambda n: rt.eval(f"TREK.Config.{n}")
    rt.run(f"TREK.Transport.beamUp({P})")
    net.pump(180)
    if died(rt, "emh, beaming up"):
        return

    station = (int(C("EmhStation").x), int(C("EmhStation").y))
    spot = (int(C("EmhSpot").x), int(C("EmhSpot").y))

    # --- nobody is standing there until he is asked for ---------------------
    # The build stands the replicator and the warp core up unconditionally; the
    # Doctor is different, because he is a person who is either projected or
    # not, and a fresh cabin has him off.
    standing, _ = doctors(rt)
    check(standing == 0,
          f"emh: {standing} Doctor(s) are standing in a cabin nobody has asked "
          f"for one in")

    # --- the way in ---------------------------------------------------------
    stand_at(rt, net, station[0] - 1, station[1])
    labels = emh_menu(rt, station[0], station[1])
    check("IGUI_TREK_EmhConsult" in labels,
          f"emh: standing at the station, the menu offers {labels!r}")

    # Greyed, not hidden, from across the cabin: a missing option is
    # indistinguishable from a broken mod.
    stand_at(rt, net, 0, 0)
    emh_menu(rt, station[0], station[1])
    far = rt.eval("""(function()
        local o = emhMenu:find("IGUI_TREK_EmhConsult")
        if not o then return "missing" end
        if not o.notAvailable then return "live" end
        return tostring(o.toolTip and o.toolTip.description or "silent")
    end)()""")
    check("IGUI_TREK_EmhFar" in str(far),
          f"emh: from the far end of the cabin the option reads {far!r} -- it "
          f"has to be there, greyed, and say why")

    # **And the server refuses it too, without the menu ever being opened.**
    # The panel greying itself is a courtesy; this is the rule, and a guard
    # that lives only in the menu is a guard a crafted command walks past.
    rt.run("SIM.notes = {}")
    rt.run(f"TREK.Core.send({P}, 'emhSummon', {{}})")
    net.pump(4)
    check(ship(rt, "emh") is None,
          "emh: the server projected the Doctor for a player standing at the "
          "far end of the cabin. A client is a request, never a fact")
    check(any("IGUI_TREK_EmhFar" in n for n in rt.notes()),
          f"emh: a summon from across the cabin said {rt.notes()}")

    # --- he comes up, exactly once, and square to the ship ------------------
    stand_at(rt, net, station[0] - 1, station[1])
    rt.run("SIM.sounds = {}; SIM.lamps = 0")
    emh_menu(rt, station[0], station[1])
    rt.run('emhMenu:click("IGUI_TREK_EmhConsult")')
    net.pump(4)

    standing, yaw = doctors(rt)
    check(standing == 1,
          f"emh: {standing} Doctor(s) stand at {spot} after one summon, not 1")
    # **Asked before anything rebuilds.** A world model picks its own yaw --
    # IsoWorldInventoryObject writes Rand.Next(0, 360) into an unset one -- and
    # every later build pass straightens whatever is there, so asking after a
    # rebuild would be checking the repair rather than the placement. That hole
    # was in this file twice.
    check(yaw == 0,
          f"emh: a freshly projected Doctor stands at {yaw} degrees rather "
          f"than square to the ship")
    check(ship(rt, "emh") is True, "emh: the ship state does not say he is up")
    check(rt.eval("TREK.EMHUI.window ~= nil") is True,
          "emh: consulting him opened no panel")
    check(rt.eval('SIM.heardSound("TREK_EmhAppear")') is True,
          "emh: the Doctor was projected in complete silence")

    # He says something. A dialogue whose first line is empty is a control
    # panel with a picture on it.
    line = str(rt.eval("TREK.EMHUI.line.key"))
    check(line.startswith("IGUI_TREK_Emh"),
          f"emh: the Doctor's opening line is {line!r}")

    # --- and nothing stands a second one up ---------------------------------
    # A world item is **saved**, and U.clearSquare keeps world items by design,
    # so a pass that places without counting first adds one every time it runs
    # -- and it runs on every build and every game minute. That is the "Two
    # shuttles" signature indoors, on a fixture that is meant to be a person.
    emh_menu(rt, station[0], station[1])
    rt.run('emhMenu:click("IGUI_TREK_EmhConsult")')
    net.pump(4)
    standing, _ = doctors(rt)
    check(standing == 1,
          f"emh: consulting him twice left {standing} Doctors on the deck")

    # The per-minute tick is the pass that actually repeats. Three of them.
    for _ in range(3):
        rt.fire("EveryOneMinute")
    net.pump(4)
    standing, _ = doctors(rt)
    check(standing == 1,
          f"emh: three service passes left {standing} Doctors standing at "
          f"{spot}, not 1")

    # --- treatment ----------------------------------------------------------
    # Everything a hypospray treats, everything a regenerator closes, and the
    # foreign bodies neither will touch -- and a bite and the infection left
    # exactly as they were found.
    rt.run("""
        local p = SIM.players[1]
        for _, what in ipairs({ "bleeding", "deepWound", "infectedWound", "burn",
                                "fracture", "pain", "stiffness", "health" }) do
            SIM.hurt(p, what, 1)
        end
        for _, what in ipairs({ "cut", "scratch", "stitches" }) do
            SIM.hurt(p, what, 3)
        end
        -- **A wound AND the glass on the same limb.** The Doctor runs the
        -- regenerator's list unskipped and takes the shard out afterwards,
        -- which is the whole difference between him and the instrument in
        -- your pocket. With glass alone on that limb there would be nothing
        -- left unhealed to notice, and applying Med.obstructed to his pass
        -- would be a change no check could see.
        SIM.hurt(p, "glass", 4)
        SIM.hurt(p, "cut", 4)
        SIM.hurt(p, "bullet", 5)
        SIM.hurt(p, "infection", 6)
        SIM.sounds = {}
    """)
    before_reserve = float(rt.eval("TREK.Power.reserve()"))
    rt.run("TREK.EMHUI.window.treatBtn:click()")
    net.pump(4)

    healed = rt.eval("""(function()
        local p = SIM.players[1]:getBodyDamage().parts[1]
        return (p.isBleeding or p.isDeepWounded or p.infectedWound
                or p.burnTime > 0 or p.fractureTime > 0 or p.additionalPain > 0
                or p.stiffness > 0 or p.health < 100) and "no" or "yes"
    end)()""")
    check(str(healed) == "yes",
          "emh: a treatment left some of the injuries a hypospray would have "
          "treated behind")
    check(body(rt, 3, "cut") is False and body(rt, 3, "isStitched") is False,
          "emh: a treatment left skin open -- he runs the regenerator's list "
          "as well, and unskipped")
    check(body(rt, 4, "glass") is False,
          "emh: a treatment left glass in a wound. Taking it out is the whole "
          "reason he is better than the instrument in your pocket")
    check(body(rt, 4, "cut") is False,
          "emh: a treatment skipped the wound on a limb that had glass in it. "
          "The regenerator refuses to close skin over a shard and the Doctor "
          "does not -- he closes it and then takes the shard out")
    check(body(rt, 5, "bullet") is False,
          "emh: a treatment left a bullet in a limb")

    # **And the bite is still there.** This is the load-bearing assertion in
    # the whole feature: treatment and the cure are different things, the cure
    # costs a crystal, and a treatment that quietly cured a bite would make the
    # price -- and the hunt for dilithium behind it -- pointless.
    check(body(rt, 6, "isBitten") is True,
          "emh: a TREATMENT cured a bite. Only the cure may, and only for a "
          "crystal")
    check(body(rt, 6, "infected") is True,
          "emh: a treatment cleared the zombie infection in a limb")
    check(rt.eval("SIM.players[1]:getBodyDamage():isInfected()") is True,
          "emh: a treatment cleared the body-level zombie infection")

    spent = before_reserve - float(rt.eval("TREK.Power.reserve()"))
    check(spent == float(C("EmhTreatCost")),
          f"emh: a treatment spent {spent} units of the reserve, not "
          f"{C('EmhTreatCost')} -- supplies are infinite and power is not")
    # Nothing is asserted here about syncBodyPart, and that is deliberate: its
    # first instruction is `getstatic GameServer.server; ifeq -> return`, so in
    # single player it really does nothing and there is nobody to tell. The
    # push is checked in emh_multiplayer(), where it is the only thing that
    # makes a server-side treatment visible at all.

    # --- the cure, and what it costs ----------------------------------------
    # A body carrying the fake-infection flags as well as the real thing.
    # That is a state the engine really produces -- a scratch under the "fake
    # infection" lore setting sets them -- and the cure has to clear every
    # field it touches rather than the ones a test happened to set. Without
    # this, deleting setIsFakeInfected from the cure would change nothing any
    # check could see.
    rt.run("""
        local d = SIM.players[1]:getBodyDamage()
        d.fakeInfected = true
        d.reduceFakeInfection = true
        d.parts[6].fakeInfected = true
    """)
    spares = crystals_aboard(rt)
    check(spares > 0, "emh: the ship has no crystals to be cured with")
    reserve_before = float(rt.eval("TREK.Power.reserve()"))
    rt.run("SIM.notes = {}")
    rt.run("TREK.EMHUI.window.cureBtn:click()")
    net.pump(4)

    check(crystals_aboard(rt) == spares - int(C("EmhCureCrystals")),
          f"emh: the cure took {spares - crystals_aboard(rt)} crystal(s), not "
          f"{C('EmhCureCrystals')}")
    check(float(rt.eval("TREK.Power.reserve()")) == reserve_before,
          "emh: the cure came out of the reserve as well as a crystal -- it "
          "costs a whole crystal and nothing else")

    # --- and it does not land for twelve hours ------------------------------
    rt.fire("EveryOneMinute")
    net.pump(2)
    check(body(rt, 6, "isBitten") is True,
          "emh: the cure landed at once. It takes C.EmhCureHours aboard, and "
          "the hours are the whole weight of the price")

    # Most of the way, and still not cured: a floor as well as a ceiling, or
    # "it took twelve hours" would pass for "it took any time at all".
    rt.run(f"SIM.advanceHours({float(C('EmhCureHours')) - 1})")
    rt.fire("EveryOneMinute")
    net.pump(2)
    check(body(rt, 6, "isBitten") is True,
          f"emh: the cure landed after {C('EmhCureHours')} - 1 hours")

    rt.run("SIM.advanceHours(1.5)")
    rt.fire("EveryOneMinute")
    net.pump(4)

    # --- every field, one at a time -----------------------------------------
    # Not "the bite is gone": the one-argument SetBitten clears the bite and
    # infects the limb on its way past, and vanilla's own admin health cheat
    # calls it that way twice. A check that only asked about the bite would
    # pass against a build that left the player infected on a bleeding arm.
    left = rt.eval("""(function()
        local p = SIM.players[1]:getBodyDamage().parts[6]
        local out = {}
        if p.isBitten then table.insert(out, "bitten") end
        if p.biteTime > 0 then table.insert(out, "biteTime") end
        if p.infected then table.insert(out, "part infected") end
        if p.fakeInfected then table.insert(out, "part fake-infected") end
        if p.infectedWound then table.insert(out, "infected wound") end
        if p.woundInfection > 0 then table.insert(out, "wound infection level") end
        return table.concat(out, ", ")
    end)()""")
    check(str(left) == "",
          f"emh: after the cure the limb still carries: {left}")

    bd = rt.eval("""(function()
        local d = SIM.players[1]:getBodyDamage()
        local out = {}
        if d.infected then table.insert(out, "isInfected") end
        if d.fakeInfected then table.insert(out, "isFakeInfected") end
        if d.reduceFakeInfection then table.insert(out, "reduceFakeInfection") end
        if d.infectionTime >= 0 then table.insert(out, "infectionTime " .. d.infectionTime) end
        if d.infectionMortalityDuration >= 0 then
            table.insert(out, "mortality " .. d.infectionMortalityDuration)
        end
        return table.concat(out, ", ")
    end)()""")
    check(str(bd) == "",
          f"emh: after the cure the body still carries: {bd}. Both levels have "
          f"to go in one pass -- isInfected is a one-way latch re-derived from "
          f"the parts, so clearing either alone is undone")

    # **The latch.** Tick the body: if the parts were left infected, the body
    # flag comes straight back and the player dies anyway.
    rt.run("SIM.tickBody(SIM.players[1], 3)")
    check(rt.eval("SIM.players[1]:getBodyDamage():isInfected()") is False,
          "emh: three ticks after the cure the infection is back. The parts "
          "were not cleared, and BodyDamage.Update re-derives the body flag "
          "from them every tick")

    moodle = rt.eval(
        "SIM.players[1]:getStats():get(CharacterStat.ZOMBIE_INFECTION)")
    check(float(moodle) == 0,
          f"emh: the infection moodle still reads {moodle} after a cure. "
          f"syncBodyPart carries BodyPart fields only, and the block that "
          f"writes that stat runs inside a countdown gated on isInfected() -- "
          f"so curing the player STOPS its only writer and the last value it "
          f"wrote is what stays on screen")

    # --- and the cure notices when it has NOT worked ------------------------
    # `Med.cure` asks every field in Med.CURE again afterwards and warns about
    # anything still set. Nothing the mod can do to itself makes that fire --
    # RestoreToFullHealth clears the lot -- so the only honest way to test it
    # is to make the *engine* misbehave, which is precisely the case it exists
    # for: this mod has shipped six bugs where a plausible engine call did
    # nothing and looked exactly like one that worked.
    rt.run("""
        SIM.hurt(SIM.players[1], "infection", 7)
        stubbornPart = SIM.players[1]:getBodyDamage().parts[7]
        stubbornPart.RestoreToFullHealth = function() end
        SIM.log = {}
    """)
    rt.run("TREK.Medical.cure(SIM.players[1])")
    noticed = [w for w in rt.warnings() if "the cure left" in w]
    check(noticed != [],
          "emh: a cure that left the virus in a limb reported success. The "
          "read-back is the only thing that can tell a setter which worked "
          "from one which quietly did not, and it has to say so")
    rt.run("stubbornPart.RestoreToFullHealth = nil; SIM.log = {}")
    rt.run("TREK.Medical.cure(SIM.players[1])")
    check([w for w in rt.warnings() if "the cure left" in w] == [],
          "emh: the cure still complains once the limb really is clear")
    rt.run("SIM.log = {}")

    # --- with no crystals, it is refused and says why -----------------------
    rt.run("""
        SIM.hurt(SIM.players[1], "infection", 6)
        TREK.Util.state().crystals = 0
        SIM.notes = {}
    """)
    rt.run("TREK.Core.send(SIM.players[1], 'emhCure', {})")
    net.pump(4)
    check(body(rt, 6, "isBitten") is True,
          "emh: an infected player was cured with no crystals aboard")
    check(any("IGUI_TREK_EmhNoCrystal" in n for n in rt.notes()),
          f"emh: a cure with no crystals said {rt.notes()} -- the refusal has "
          f"to name dilithium, because that is what sends a player out looking")

    # --- the cockpit is the ship ---------------------------------------------
    # Found in a game, from the log: a patient went forward to fly her during
    # the twelve hours, and two seconds after "materialised in the cockpit"
    # the cure was lost, crystal and all. The pilot's seat is aboard.
    rt.run("""
        TREK.Util.state().crystals = 2
        SIM.notes = {}
    """)
    rt.run("TREK.Core.send(SIM.players[1], 'emhCure', {})")
    net.pump(4)
    check(rt.eval("TREK.EMH.cureDue('emh') ~= nil") is True,
          "emh: the cure never started, so the cockpit cannot be tested")
    # A seat in a shuttle, as the cure asks about it: the vehicle's script
    # name. Not a vehicle parked in the cell -- the ship's own vehicle service
    # would rightly object to a shuttle it never spawned.
    rt.run(f"""
        TREK.Util.teleport({P}, 1000, 1000, 0)
        {P}.vehicle = {{ x = 1000.5, y = 1000.5,
                         getZ = function() return 0 end,
                         getScriptName = function() return TREK.Vehicle.SCRIPT end }}
    """)
    net.pump(4)
    for _ in range(6):
        rt.run("SIM.advanceHours(1 / 60)")
        rt.fire("EveryOneMinute")
        net.pump(1)
    check(rt.eval("TREK.EMH.cureDue('emh') ~= nil") is True,
          "emh: a patient in the shuttle's pilot seat lost the cure -- the "
          "cockpit is the ship")
    rt.run("SIM.advanceHours(TREK.Config.EmhCureHours)")
    rt.fire("EveryOneMinute")
    net.pump(4)
    check(body(rt, 6, "isBitten") is False,
          "emh: a cure that fell due with the patient flying the ship did not "
          "land")
    check(any("IGUI_TREK_EmhCuredNote" in n for n in rt.notes()),
          "emh: a cure landed in the cockpit without telling the patient")
    rt.run(f"{P}.vehicle = nil")
    rt.run(f"TREK.Transport.beamUp({P})")
    net.pump(180)
    stand_at(rt, net, station[0] - 1, station[1])

    # --- leaving the ship costs the crystal ---------------------------------
    rt.run("""
        SIM.hurt(SIM.players[1], "infection", 6)
        TREK.Util.state().crystals = 2
    """)
    rt.run("SIM.notes = {}")
    rt.run("TREK.Core.send(SIM.players[1], 'emhCure', {})")
    net.pump(4)
    started = crystals_aboard(rt)
    check(started == 1, f"emh: starting a cure left {started} crystals, not 1")

    rt.run(f"TREK.Util.teleport({P}, 1000, 1000, 0)")
    net.pump(4)
    rt.fire("EveryOneMinute")
    net.pump(2)
    # The first check off the ship starts a grace of a couple of game
    # minutes -- the time it takes to change places -- and does not end it.
    check(rt.eval("TREK.EMH.cureDue('emh') ~= nil") is True,
          "emh: the cure was lost on the first check off the ship; changing "
          "places passes through the ground beside her")
    rt.run("SIM.advanceHours(TREK.Config.EmhCureGraceHours + 1 / 60)")
    rt.fire("EveryOneMinute")
    net.pump(2)
    check(crystals_aboard(rt) == 1,
          "emh: walking out of the cabin refunded the crystal. The treatment "
          "is a commitment rather than a reservation, and the twelve hours "
          "mean nothing if leaving is free")
    check(rt.eval("TREK.EMH.cureDue('emh') == nil") is True,
          "emh: the cure register still holds a patient who has left the ship")
    check(any("IGUI_TREK_EmhCureLost" in n for n in rt.notes()),
          "emh: the treatment was abandoned without telling the patient")

    # --- a rebuild deletes him, and the build phase puts him back -----------
    # B.forceRebuild wipes everything on the square but the floor -- world
    # items included -- and `s.emh` would still say he was up. The build phase
    # is what repairs it, which is why it is a phase and not only a timer.
    rt.run(f"TREK.Transport.beamUp({P})")
    net.pump(180)
    stand_at(rt, net, station[0] - 1, station[1])
    check(ship(rt, "emh") is True,
          "emh: the ship forgot he was up while nobody was aboard")
    rt.run("TREK.Build.forceRebuild()")
    net.pump(4)
    standing, _ = doctors(rt)
    check(standing == 1,
          f"emh: after TREK_Rebuild() {standing} Doctor(s) stand there. The "
          f"rebuild really does delete him -- the build phase is what puts him "
          f"back, and without it the ship says he is up and the deck is empty")

    # --- dismissing takes him down ------------------------------------------
    # Asked before any build pass, for the same reason the yaw is: a rebuild
    # would settle it either way and cover for a dismissal that did nothing.
    rt.run("TREK.EMHUI.window = nil")
    emh_menu(rt, station[0], station[1])
    rt.run('emhMenu:click("IGUI_TREK_EmhConsult")')
    net.pump(2)
    rt.run("TREK.EMHUI.window.dismissBtn:click()")
    net.pump(4)
    standing, _ = doctors(rt)
    check(standing == 0,
          f"emh: dismissing him left {standing} standing on the deck")
    check(ship(rt, "emh") is None,
          "emh: he was taken off the deck and the ship still says he is up")
    check(rt.eval("TREK.EMHUI.window == nil") is True,
          "emh: dismissing him left the panel open on an empty square")

    # --- a crooked Doctor in an older save is squared up --------------------
    rt.run("TREK.Util.state().emh = true")
    rt.run("TREK.Build.serviceEMH()")
    rt.run("""
        local C, U = TREK.Config, TREK.Util
        local x, y = U.at(C.EmhSpot.x, C.EmhSpot.y)
        for _, w in ipairs(SIM.rawSquare(x, y, C.CabinZ).worldObjects or {}) do
            if w.item and w.item.fullType == C.EmhItem then
                w.item:setWorldZRotation(137)
            end
        end
    """)
    rt.run("TREK.Build.serviceEMH()")
    _, yaw = doctors(rt)
    check(yaw == 0,
          f"emh: a Doctor left at an angle by an older save is still at {yaw} "
          f"degrees after a service pass")

    # --- the sandbox ---------------------------------------------------------
    rt.run("SandboxVars.TrekShuttle.EMH = TREK.Config.EmhOff")
    stand_at(rt, net, station[0] - 1, station[1])
    emh_menu(rt, station[0], station[1])
    off = rt.eval("""(function()
        local o = emhMenu:find("IGUI_TREK_EmhConsult")
        if not o then return "missing" end
        if not o.notAvailable then return "live" end
        return tostring(o.toolTip and o.toolTip.description or "silent")
    end)()""")
    check("IGUI_TREK_EmhOff" in str(off),
          f"emh: with the sandbox Off the option reads {off!r}")

    # And the server refuses it too, because a client is a request. The panel
    # greying itself is a courtesy; this is the rule.
    rt.run("TREK.Util.state().emh = nil")
    rt.run("SIM.notes = {}")
    rt.run(f"TREK.Core.send({P}, 'emhSummon', {{}})")
    net.pump(4)
    check(ship(rt, "emh") is None,
          "emh: the server brought the Doctor up with the sandbox set to Off")
    check(any("IGUI_TREK_EmhOff" in n for n in rt.notes()),
          f"emh: a summon refused by the sandbox said {rt.notes()}")
    rt.run("SandboxVars.TrekShuttle.EMH = TREK.Config.EmhFull")

    # --- a flat ship cannot project him at all ------------------------------
    # Four separate comments in this repository promised this before he
    # existed: "a crew with no crystals has a galley fixture and a hologram
    # that will not switch on".
    rt.run("""
        TREK.Util.state().power = 0
        TREK.Util.state().crystals = 0
        SIM.notes = {}
    """)
    emh_menu(rt, station[0], station[1])
    flat = rt.eval("""(function()
        local o = emhMenu:find("IGUI_TREK_EmhConsult")
        if not o then return "missing" end
        if not o.notAvailable then return "live" end
        return tostring(o.toolTip and o.toolTip.description or "silent")
    end)()""")
    check("IGUI_TREK_EmhNoPower" in str(flat),
          f"emh: with a flat reserve and no crystals the option reads {flat!r}")
    rt.run(f"TREK.Core.send({P}, 'emhSummon', {{}})")
    net.pump(4)
    check(ship(rt, "emh") is None,
          "emh: a ship with no power at all still projected the Doctor")

    for w in rt.warnings():
        fail(f"emh: {w}")
    print("emh: the station offers him and greys itself with a reason, he "
          "stands up once and square, a treatment clears everything but the "
          "bite and the infection, the cure takes a crystal and twelve hours "
          "and clears both levels and the moodle, leaving the ship costs it, "
          "a rebuild is repaired, and the sandbox and an empty core both "
          "refuse him")


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

    # --- the warp core, from two machines -----------------------------------
    # The crystals are ship state now rather than items in a container, which
    # is the arrangement that makes this check worth having: one number, one
    # writer, and it has to reach everybody. Both players stand at the berth
    # at 1,5, which is also within reach of the core at 1,3.
    for rt in net.all():
        rt.run("""
            local U = TREK.Util
            local x, y = U.at(1, 4)
            for _, p in ipairs(SIM.players) do
                p.x, p.y, p.z, p.lastZ = x + 0.5, y + 0.5, TREK.Config.CabinZ,
                                         TREK.Config.CabinZ
            end
        """)
    net.pump(10)

    aboard = crystals_aboard(srv)
    # The owner has a crystal; the stranger has one too, and must keep it.
    for rt in (srv, owner):
        rt.run("""
            local C = TREK.Config
            for _, p in ipairs(SIM.players) do
                if p.name == "owner" then
                    p.inventory:AddItem(instanceItem(C.DilithiumItem))
                end
            end
        """)
    for rt in (srv, stranger):
        rt.run("""
            local C = TREK.Config
            for _, p in ipairs(SIM.players) do
                if p.name == "stranger" then
                    p.inventory:AddItem(instanceItem(C.DilithiumItem))
                end
            end
        """)

    owner.run(f"TREK.Core.send({P}, 'loadCrystal', {{}})")
    net.pump(6)
    check(crystals_aboard(srv) == aboard + 1,
          f"core: the server has {crystals_aboard(srv)} crystals aboard after "
          f"one was loaded, not {aboard + 1}")
    check(carrying(srv, "TrekShuttle.TrekDilithium", who="owner") == 0,
          "core: the ship took the crystal and the owner is still carrying "
          "it -- one crystal became two")
    check(carrying(srv, "TrekShuttle.TrekDilithium", who="stranger") == 1,
          "core: loading the owner's crystal took the other player's as well")
    # And the owner's *own client* has to know the crystal is gone. The
    # server removed it from its copy of their inventory; without the
    # matching sendRemoveItemFromContainer they would still be holding one
    # on their own screen -- and would load it again.
    check(carrying(owner, "TrekShuttle.TrekDilithium") == 0,
          f"core: the owner's client still shows "
          f"{carrying(owner, 'TrekShuttle.TrekDilithium')} crystal(s) after "
          f"loading one into the ship")
    check(crystals_aboard(owner) == crystals_aboard(srv)
          and crystals_aboard(stranger) == crystals_aboard(srv),
          f"core: the spare count on the clients ({crystals_aboard(owner)}, "
          f"{crystals_aboard(stranger)}) does not match the server's "
          f"({crystals_aboard(srv)}) -- a crewman would walk to a core that "
          f"is not there")

    # **A client may not take from the core itself.** Every write in
    # TREK_Power is guarded with isClient(), and this is the one that would
    # matter: a client that could decrement the count would see a crystal that
    # the server still has and the server would never know.
    before_client = crystals_aboard(owner)
    check(owner.eval("TREK.Power.takeCrystal()") is False,
          "core: a client took a crystal out of the ship by itself")
    check(owner.eval("TREK.Power.addCrystals(5)") is False,
          "core: a client put five crystals into the ship by itself")
    check(crystals_aboard(owner) == before_client,
          f"core: the client's own count moved to {crystals_aboard(owner)} "
          f"without the server saying anything")

    # And it comes back out to whoever asks, not to whoever is nearest.
    stranger.run(f"TREK.Core.send({P}, 'takeCrystal', {{}})")
    net.pump(6)
    check(crystals_aboard(srv) == aboard,
          f"core: taking one back left {crystals_aboard(srv)} aboard, not "
          f"{aboard}")
    check(carrying(srv, "TrekShuttle.TrekDilithium", who="stranger") == 2,
          f"core: the crystal was given to somebody other than the player who "
          f"asked for it")
    check(carrying(srv, "TrekShuttle.TrekDilithium", who="owner") == 0,
          "core: the owner was handed the crystal the other player asked for")
    check(carrying(stranger, "TrekShuttle.TrekDilithium") == 2,
          f"core: the crystal never reached the asking player's own client "
          f"({carrying(stranger, 'TrekShuttle.TrekDilithium')} in hand)")

    for rt in net.all():
        for w in rt.warnings():
            fail(f"replicator multiplayer ({rt.name}): {w}")
    print("replicator multiplayer: crew access, a shared pattern set that "
          "reaches both machines, an item the server makes into the asking "
          "player's own hands and nobody else's, an inventory the server "
          "checks for itself, and a warp core whose spare count is one "
          "number with one writer that reaches both machines")


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


def emh_multiplayer():
    """The Doctor with two clients: consent, and who a reply is addressed to.

    Every check in here is invisible in single player, which is the whole
    reason the function exists. The one that matters most is the last:
    **nobody can force-heal, or force-anything, another player.** That is the
    padlock-and-safehouse rule from MULTIPLAYER.md applied to bodies, and it
    is the difference between a mod and a griefing tool -- a yes/no that
    appeared on the asker's own screen would let one player treat, cure and
    spend the ship's dilithium on anybody aboard without them ever seeing it.
    """
    net = Net("mp", clients=("owner", "crew"))
    server = net.server
    owner, crew = net.clients["owner"], net.clients["crew"]

    # Both standing at the station. The server holds every player and each
    # client holds itself, which is the shape the engine really has -- and the
    # reason a client's word about who is aboard is not evidence.
    server.run("SIM.player('owner', 1000.5, 1000.5, 0); "
               "SIM.player('crew', 1000.5, 1000.5, 0)")
    owner.run("SIM.player('owner', 1000.5, 1000.5, 0)")
    crew.run("SIM.player('crew', 1000.5, 1000.5, 0)")
    net.start()
    net.pump(4)

    for rt in net.all():
        rt.run("SandboxVars.TrekShuttle.Access = 1")

    owner.run("TREK.Transport.beamUp(SIM.players[1])")
    crew.run("TREK.Transport.beamUp(SIM.players[1])")
    net.pump(220)
    if died(owner, "emh mp, the owner beaming up"):
        return
    if died(crew, "emh mp, the crewman beaming up"):
        return

    C = lambda n: server.eval(f"TREK.Config.{n}")
    sx, sy = int(C("EmhStation").x), int(C("EmhStation").y)

    def put(rt, name, ox, oy):
        rt.run(f"""
            local U = TREK.Util
            local x, y = U.at({ox}, {oy})
            for _, p in ipairs(SIM.players) do
                if p.name == "{name}" then U.teleport(p, x, y, TREK.Config.CabinZ) end
            end
        """)

    for rt in net.all():
        put(rt, "owner", sx - 1, sy)
        put(rt, "crew", sx - 1, sy + 1)
    net.pump(6)

    # --- both machines see the same Doctor ----------------------------------
    owner.run("TREK.Core.send(SIM.players[1], 'emhSummon', {})")
    net.pump(6)
    for name, rt in (("the server", server), ("the owner", owner),
                     ("the crewman", crew)):
        standing = doctors(rt)[0]
        check(standing == 1,
              f"emh mp: {name} sees {standing} Doctor(s) standing; the "
              f"hologram is ship state so that everybody sees the same one")

    # --- an offer appears on the PATIENT's screen and nowhere else ----------
    server.run("""
        for _, p in ipairs(SIM.players) do
            if p.name == "crew" then SIM.hurt(p, "bleeding", 1) end
        end
    """)
    for rt in net.all():
        rt.run("SIM.modals = {}")
    owner.run("TREK.Core.send(SIM.players[1], 'emhTreat', { who = 'crew' })")
    net.pump(6)

    check(crew.eval("#SIM.modals") == 1,
          "emh mp: the patient was never asked. Treating somebody else raises "
          "a yes/no on THEIR screen; anything else is a mod that reaches into "
          "other people's bodies")
    check(owner.eval("#SIM.modals") == 0,
          "emh mp: the yes/no appeared on the asker's own screen, which would "
          "let one player agree to a treatment on another player's behalf")
    check(server.eval("""(function()
              for _, p in ipairs(SIM.players) do
                  if p.name == "crew" then
                      return p:getBodyDamage().parts[1].isBleeding
                  end
              end
          end)()""") is True,
          "emh mp: the patient was treated before they had agreed")

    # --- declining spends nothing -------------------------------------------
    before = float(server.eval("TREK.Power.reserve()"))
    crew.run("SIM.lastModal():answer(false)")
    net.pump(6)
    check(float(server.eval("TREK.Power.reserve()")) == before,
          "emh mp: declining a treatment still spent the ship's power")
    check(server.eval("""(function()
              for _, p in ipairs(SIM.players) do
                  if p.name == "crew" then
                      return p:getBodyDamage().parts[1].isBleeding
                  end
              end
          end)()""") is True,
          "emh mp: a declined treatment happened anyway")

    # --- accepting treats them, on the server, and reaches their client -----
    server.run("SIM.bodySyncs = {}")
    for rt in net.all():
        rt.run("SIM.modals = {}")
    owner.run("TREK.Core.send(SIM.players[1], 'emhTreat', { who = 'crew' })")
    net.pump(6)
    crew.run("SIM.lastModal():answer(true)")
    net.pump(6)

    check(server.eval("""(function()
              for _, p in ipairs(SIM.players) do
                  if p.name == "crew" then
                      return p:getBodyDamage().parts[1].isBleeding
                  end
              end
          end)()""") is False,
          "emh mp: an accepted treatment did not reach the patient's body")
    check(float(server.eval("TREK.Power.reserve()")) == before - float(C("EmhTreatCost")),
          "emh mp: an accepted treatment did not spend the reserve")

    # **The push.** A body is written on the server and nowhere else -- a
    # client restores a *remote* body to full every tick -- so syncBodyPart is
    # the only thing that makes the treatment visible to the patient at all.
    # Recorded per part rather than counted, because "synced the first one
    # only" and "synced all seventeen" are otherwise the same answer.
    synced = server.eval("""(function()
        local seen = {}
        local n = 0
        for _, s in ipairs(SIM.bodySyncs) do
            if not seen[s.part] then seen[s.part] = true n = n + 1 end
        end
        return n
    end)()""")
    check(int(synced) >= 17,
          f"emh mp: the treatment pushed {synced} distinct body parts to the "
          f"patient. All of them have to go, or the limbs that were mended "
          f"stay broken on the only screen that matters")

    # --- an expired offer is refused ----------------------------------------
    for rt in net.all():
        rt.run("SIM.modals = {}")
    server.run("""
        for _, p in ipairs(SIM.players) do
            if p.name == "crew" then SIM.hurt(p, "bleeding", 2) end
        end
    """)
    owner.run("TREK.Core.send(SIM.players[1], 'emhTreat', { who = 'crew' })")
    net.pump(6)
    # **The real token, read off the offer the patient was actually shown.**
    # A hard-coded 1 passes for the wrong reason the moment more than one
    # offer has ever been minted: the server answers "no such offer" and the
    # treatment does not happen, which looks exactly like the expiry working.
    token = crew.eval("SIM.lastModal() and SIM.lastModal().param1")
    check(token is not None, "emh mp: the patient was never offered anything")
    # The offer's clock is the simulated one, which net.pump moves 16 ms a
    # tick; jump it past C.EmhOfferMs rather than pumping for half a minute.
    net.clock += int(C("EmhOfferMs")) + 1000
    crew.run("SIM.modals = {}")
    crew.run(f"TREK.Core.send(SIM.players[1], 'emhAccept', {{ token = {int(token)} }})")
    net.pump(6)
    check(server.eval("""(function()
              for _, p in ipairs(SIM.players) do
                  if p.name == "crew" then
                      return p:getBodyDamage().parts[2].isBleeding
                  end
              end
          end)()""") is True,
          "emh mp: an offer that had lapsed was still honoured. Between the "
          "question and the answer the asker can walk away and the core can "
          "be emptied, which is why it expires and is re-validated")

    # --- a client naming somebody else changes nothing ----------------------
    # A crafted command is the whole reason the patient is resolved on the
    # server: without it, `who` is a way to reach into anybody's body from
    # anywhere on the map.
    server.run("""
        for _, p in ipairs(SIM.players) do
            if p.name == "owner" then SIM.hurt(p, "bleeding", 3) end
        end
    """)
    crew.run("TREK.Core.send(SIM.players[1], 'emhTreat', { who = 'nobody-at-all' })")
    net.pump(6)
    check(server.eval("""(function()
              for _, p in ipairs(SIM.players) do
                  if p.name == "owner" then
                      return p:getBodyDamage().parts[3].isBleeding
                  end
              end
          end)()""") is True,
          "emh mp: a command naming a patient who is not aboard treated "
          "somebody")

    # --- a cure, and the server's own copy of the body ----------------------
    # **This is what single player cannot show.** There, the patient's client
    # handler runs in the same process as the server and repairs whatever the
    # server left wrong -- so a cure that cleared none of the body-level flags
    # on the authority still looked perfect. With two processes the server's
    # copy is the one the simulation runs on (`BodyDamage.Update` is the
    # server's), and it is the one that has to be right.
    server.run("TREK.Util.state().crystals = 2")
    server.run("""
        for _, p in ipairs(SIM.players) do
            if p.name == "crew" then
                SIM.hurt(p, "infection", 4)
                local d = p:getBodyDamage()
                d.fakeInfected = true
                d.reduceFakeInfection = true
            end
        end
    """)
    crew.run("TREK.Core.send(SIM.players[1], 'emhCure', {})")
    net.pump(6)
    check(int(server.eval("TREK.Power.crystals()")) == 1,
          "emh mp: the cure did not take a crystal")

    server.run(f"SIM.advanceHours({float(C('EmhCureHours')) + 1})")
    server.fire("EveryOneMinute")
    net.pump(6)

    on_server = server.eval("""(function()
        local out = {}
        for _, p in ipairs(SIM.players) do
            if p.name == "crew" then
                local d = p:getBodyDamage()
                if d.infected then table.insert(out, "isInfected") end
                if d.fakeInfected then table.insert(out, "isFakeInfected") end
                if d.reduceFakeInfection then table.insert(out, "reduceFakeInfection") end
                if d.infectionTime >= 0 then
                    table.insert(out, "infectionTime " .. d.infectionTime)
                end
                if d.infectionMortalityDuration >= 0 then
                    table.insert(out, "mortality " .. d.infectionMortalityDuration)
                end
                if d.parts[4].isBitten then table.insert(out, "bitten") end
            end
        end
        return table.concat(out, ", ")
    end)()""")
    check(str(on_server) == "",
          f"emh mp: after the cure the SERVER's copy of the patient still "
          f"carries: {on_server}. The server is the machine that simulates a "
          f"body -- a client only ever fixes its own, and in single player "
          f"that repair hides this entirely")

    # And the patient's own client cleared what the packet cannot carry.
    moodle = crew.eval(
        "SIM.players[1]:getStats():get(CharacterStat.ZOMBIE_INFECTION)")
    check(float(moodle) == 0,
          f"emh mp: the patient's own client still shows the infection moodle "
          f"at {moodle}")

    # --- he goes on both screens --------------------------------------------
    owner.run("TREK.Core.send(SIM.players[1], 'emhDismiss', {})")
    net.pump(6)
    for name, rt in (("the server", server), ("the owner", owner),
                     ("the crewman", crew)):
        standing = doctors(rt)[0]
        check(standing == 0,
              f"emh mp: after a dismissal {name} still sees {standing} Doctor(s)")

    # --- a stranger is refused under owner-and-crew --------------------------
    for rt in net.all():
        rt.run("SandboxVars.TrekShuttle.Access = 2")
    server.run('TREK.Util.state().owner = "owner"; TREK.Util.state().crew = {}')
    server.run("Ship = TREK.Ship")
    crew.run("SIM.notes = {}")
    crew.run("TREK.Core.send(SIM.players[1], 'emhSummon', {})")
    net.pump(6)
    check(server.eval("TREK.Util.state().emh") is None,
          "emh mp: a player who is not on the crew brought the Doctor up")
    check(any("IGUI_TREK_NotCrew" in n for n in crew.notes()),
          f"emh mp: a refused stranger was told {crew.notes()}")

    # --- and no client wrote the world or the ship --------------------------
    for name, rt in (("owner", owner), ("crew", crew)):
        edits = rt.eval("SIM.clientWorldEdit")
        check(edits is None,
              f"emh mp: the {name} client made {edits} world edit(s) of its "
              f"own; the Doctor is placed and removed by the server")

    for rt in net.all():
        for w in rt.warnings():
            fail(f"emh multiplayer: {w}")

    print("emh multiplayer: both machines see one Doctor, the yes/no appears "
          "on the patient's screen and nowhere else, declining costs nothing, "
          "accepting treats them on the server and pushes every body part "
          "back, a lapsed offer and a forged patient are refused, and a "
          "stranger is turned away")


def contacts():
    """The contact store: what it accepts, what it refuses, and what it drops.

    This is ROADMAP2 step 3 built against **synthetic** contacts, which is the
    roadmap's own instruction: the store, its bounds and its map view can all
    be proven before a probe exists to fill it, and every one of them is a
    thing that would otherwise only be found once probes were being debugged
    at the same time.
    """
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('owner', 2000.5, 2000.5, 0)")
    net.start()

    def add(kind, x, y, approximate=False):
        return rt.eval(
            '(function() '
            'local c = TREK.Probes.addContact("%s", %d, %d, 0, "probe:1", %s) '
            'return c and c.id or nil end)()'
            % (kind, x, y, "true" if approximate else "false"))

    def count():
        return int(rt.eval("#TREK.Probes.contacts()"))

    def live():
        return int(rt.eval("#TREK.Probes.unresolved()"))

    # --- what it accepts ---------------------------------------------------
    first = add("dilithium", 4100, 9200)
    check(isinstance(first, str) and first.startswith("dilithium:"),
          f"contacts: addContact returned {first!r}, not a dilithium id")
    add("downedPersonnel", 4200, 9300)
    check(count() == 2, f"contacts: the store holds {count()} of 2 contacts")
    check(live() == 2, f"contacts: {live()} of 2 contacts are live")

    # The id has to be stable and findable: everything downstream -- the
    # console, the map focus, a mission -- refers to a contact by it.
    found = rt.eval(
        '(function() local c = TREK.Probes.byId("%s") '
        'return c and (c.x .. "," .. c.y) or "missing" end)()' % first)
    check(found == "4100,9200",
          f"contacts: byId({first!r}) came back {found}, not its coordinates")

    # --- what it refuses ---------------------------------------------------
    # A kind nothing declares would be stored, transmitted, drawn with a nil
    # symbol and matched by nothing. It is refused, and loudly.
    bad = add("wormhole", 1, 1)
    check(bad is None, "contacts: a contact of an undeclared kind was accepted")
    check(count() == 2,
          f"contacts: the refused contact was stored anyway ({count()} rows)")
    check(any("unknown kind" in w for w in rt.warnings()),
          "contacts: an undeclared kind was refused without saying so")
    rt.run("SIM.log = {}")

    bad_status = rt.eval(f'TREK.Probes.setStatus("{first}", "pending")')
    check(bad_status is False,
          "contacts: a status this mod does not declare was accepted -- it "
          "would read as neither live nor resolved and never be pruned")
    check(any("not one this mod declares" in w for w in rt.warnings()),
          "contacts: a bad status was refused silently")
    rt.run("SIM.log = {}")

    # --- the lifecycle -----------------------------------------------------
    check(rt.eval(f'TREK.Probes.setStatus("{first}", "recovered")') is True,
          "contacts: a legitimate status change was refused")
    check(live() == 1,
          f"contacts: {live()} live after one was recovered, expected 1")
    check(count() == 2,
          "contacts: recovering a contact deleted it; it should stay as history")

    # --- the bounds --------------------------------------------------------
    # Two different bounds, and the roadmap asks for both: resolved history is
    # capped whatever the total is, and the total is capped whatever the
    # statuses are. A store published to every client cannot grow for ever.
    caps = rt.eval("TREK.Config.MaxResolvedContacts"), rt.eval("TREK.Config.MaxContacts")
    max_resolved, max_total = int(caps[0]), int(caps[1])
    check(max_resolved >= 1 and max_total > max_resolved,
          f"contacts: the caps are {max_resolved}/{max_total}, which cannot "
          f"exercise the two-bound rule")

    rt.run("""
        local P = TREK.Probes
        for i = 1, TREK.Config.MaxResolvedContacts + 6 do
            local c = P.addContact("dilithium", 100 + i, 200 + i, 0, "probe:x", false)
            P.setStatus(c.id, "recovered")
        end
    """)
    resolved = int(rt.eval("""(function()
        local n = 0
        for _, c in ipairs(TREK.Probes.contacts()) do
            if TREK.Probes.isResolved(c.status) then n = n + 1 end
        end
        return n
    end)()"""))
    check(resolved <= max_resolved,
          f"contacts: {resolved} resolved records kept, cap is {max_resolved}")

    # Live contacts are never traded away for resolved ones.
    rt.run("""
        local P = TREK.Probes
        for i = 1, TREK.Config.MaxContacts do
            P.addContact("downedPersonnel", 500 + i, 600 + i, 0, "probe:y", true)
        end
    """)
    total = count()
    check(total <= max_total,
          f"contacts: the store holds {total}, over the {max_total} cap")
    check(live() > 0, "contacts: the cap pruned every live contact away")

    for w in rt.warnings():
        fail(f"contacts: {w}")

    print(f"contacts: kinds and statuses are both checked against the sets "
          f"this mod declares, a recovered contact stays as history, and the "
          f"store holds at {total} with the resolved history capped at "
          f"{resolved}")


def contact_map():
    """The map view: one symbol per live contact, and ours taken off again.

    Nothing here relies on the engine remembering anything. The contacts are
    the mod's own store and the symbols are rebuilt from it when the map
    opens, because the half of the engine's symbol system that makes a symbol
    shared and persistent is not reachable from Lua at all (MAP_MARKERS.md).
    """
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('owner', 2000.5, 2000.5, 0)")
    net.start()

    # The symbols must have registered from the mod's own
    # shared/Definitions/TrekMapSymbols.lua, which the runtime loads the way
    # the game does. Without that every addTexture below is refused.
    registered = int(rt.eval("MapSymbolDefinitions.getInstance():getSymbolCount()"))
    check(registered >= 2,
          f"contact map: {registered} map symbols registered; "
          f"shared/Definitions/TrekMapSymbols.lua did not load")

    rt.run("""
        local P = TREK.Probes
        P.addContact("dilithium", 4100, 9200, 0, "probe:1", true)
        P.addContact("downedPersonnel", 4300, 9400, 0, "probe:1", false)
        local done = P.addContact("dilithium", 4500, 9600, 0, "probe:1", false)
        P.setStatus(done.id, "recovered")
    """)

    rt.run("ISWorldMap.ShowWorldMap(0, 4100, 9200)")
    drawn = int(rt.eval("TREK.MapContacts.count()"))
    check(drawn == 2,
          f"contact map: {drawn} symbols drawn for 2 live contacts (the "
          f"recovered one is history and must not be on the map)")

    placed = rt.eval("""(function()
        local out = {}
        for _, s in ipairs(SIM.mapSymbols()) do
            table.insert(out, s.id .. "@" .. s.x .. "," .. s.y)
        end
        table.sort(out)
        return table.concat(out, " ")
    end)()""")
    check("TrekContactDilithium@4100,9200" in str(placed),
          f"contact map: the dilithium contact is not on the map at its own "
          f"world square ({placed})")
    check("TrekContactPersonnel@4300,9400" in str(placed),
          f"contact map: the personnel contact is misplaced ({placed})")
    check("4500" not in str(placed),
          f"contact map: a recovered contact was drawn ({placed})")

    # Anchored and opaque. A symbol whose colour was never set can draw at
    # alpha 0, and vanilla sets it after every addTexture.
    styled = rt.eval("""(function()
        for _, s in ipairs(SIM.mapSymbols()) do
            if s.ax ~= 0.5 or s.ay ~= 0.5 or s.a ~= 1 then return false end
        end
        return true
    end)()""")
    check(styled is True,
          "contact map: a symbol was left unanchored or transparent")

    # A report arriving while the map is open redraws rather than doubling up.
    rt.run("""
        TREK.Probes.addContact("dilithium", 4700, 9800, 0, "probe:2", true)
        TREK.Probes.publish()
    """)
    after = int(rt.eval("#SIM.mapSymbols()"))
    check(after == 3,
          f"contact map: {after} symbols after a third contact arrived while "
          f"the map was open, expected 3 -- a redraw that adds without "
          f"removing doubles every symbol")

    # Closing takes ours off. If world-map symbols do persist in single
    # player -- which could not be settled outside a game -- this is what
    # stops the next open showing two of everything.
    rt.run("ISWorldMap:onClose()")
    check(int(rt.eval("TREK.MapContacts.count()")) == 0,
          "contact map: closing the map left the mod's symbols behind")

    rt.run("ISWorldMap.ShowWorldMap(0, 4100, 9200)")
    reopened = int(rt.eval("#SIM.mapSymbols()"))
    check(reopened == 3,
          f"contact map: {reopened} symbols on reopening, expected 3")

    for w in rt.warnings():
        fail(f"contact map: {w}")

    print("contact map: live contacts are drawn at their own world squares, "
          "a recovered one is not, a report arriving mid-look redraws without "
          "doubling, and closing the map takes the mod's symbols off again")


def contacts_multiplayer():
    """Two clients see one contact log, and neither of them may write it."""
    net = Net("mp", clients=("owner", "crew"))
    srv = net.server
    owner, crew = net.clients["owner"], net.clients["crew"]
    for rt in net.all():
        rt.run("SandboxVars.TrekShuttle.Access = 2")
    srv.run("SIM.player('owner', 2000.5, 2000.5, 0); "
            "SIM.player('crew', 2000.5, 2000.5, 0)")
    owner.run("SIM.player('owner', 2000.5, 2000.5, 0)")
    crew.run("SIM.player('crew', 2000.5, 2000.5, 0)")
    net.start()

    def rows(rt):
        return int(rt.eval("#TREK.Probes.contacts()"))

    # The authority writes, then publishes. Publishing is separate on purpose:
    # a pass that resolves several contacts should transmit once.
    srv.run("""
        local P = TREK.Probes
        P.addContact("dilithium", 4100, 9200, 0, "probe:1", true)
        P.addContact("downedPersonnel", 4300, 9400, 0, "probe:1", false)
        P.publish()
    """)
    net.pump(20)

    for name, rt in (("owner", owner), ("crew", crew)):
        check(rows(rt) == 2,
              f"contacts mp: the {name} client holds {rows(rt)} of 2 contacts")

    # And a change reaches both, rather than only the machine that asked.
    first = srv.eval("TREK.Probes.contacts()[1].id")
    srv.run(f'TREK.Probes.setStatus("{first}", "recovered"); TREK.Probes.publish()')
    net.pump(20)
    for name, rt in (("owner", owner), ("crew", crew)):
        n = int(rt.eval("#TREK.Probes.unresolved()"))
        check(n == 1,
              f"contacts mp: the {name} client sees {n} live contacts after "
              f"one was recovered on the server, expected 1")

    # A client is not an author. TREK_Probes refuses on a client the way
    # Ship.commit does, because a contact log every machine can write is a
    # contact log with no single writer.
    before = rows(owner)
    owner.run("""
        TREK.Probes.addContact("dilithium", 1, 1, 0, "forged", false)
        TREK.Probes.setStatus("anything", "completed")
        TREK.Probes.publish()
    """)
    check(rows(owner) == before,
          f"contacts mp: a client wrote its own contact ({before} -> "
          f"{rows(owner)}); the store has one writer")
    check(any("client tried to publish" in w for w in owner.warnings()),
          "contacts mp: a client publishing was ignored without saying so")
    owner.run("SIM.log = {}")

    for name, rt in (("server", srv), ("owner", owner), ("crew", crew)):
        for w in rt.warnings():
            fail(f"contacts mp ({name}): {w}")

    print("contacts multiplayer: the authority writes and publishes once, "
          "both crew hold the same log, a status change reaches both, and a "
          "client that tries to write one is refused and says so")

def aboard_menu(rt):
    """Right-clicks aboard and returns what the ship's menu offered.

    The way a player actually reaches the sensors. Driving the server handler
    instead would pass against a build whose menu option was never added --
    which is how the torpedoes shipped broken.
    """
    rt.run("""
        aboardCtx = SIM.contextMenu()
        SIM.fire("OnPreFillWorldObjectContextMenu", 0, aboardCtx, {}, false)
    """)
    return str(rt.eval("aboardCtx:deepLabels()"))


def probes():
    """Fabricating, launching, flying and reporting.

    ROADMAP2 step 4, in the shape the author asked for after playing it:
    energy buys a **probe**, and a probe is what a launch costs. "Three probes
    aboard" is a state you can plan around; "830 units of reserve" is
    arithmetic you have to do first.
    """
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('owner', 2000.5, 2000.5, 0)")
    net.start()
    P = "SIM.players[1]"

    rt.run(f"TREK.Transport.beamUp({P})")
    net.pump(210)
    if died(rt, "probes, beaming up"):
        return

    cost = int(rt.eval("TREK.Config.ProbeCost"))
    rack = lambda: int(rt.eval("TREK.Util.state().probes or 0"))
    reserve = lambda: int(rt.eval("math.floor(TREK.Power.reserve())"))

    # --- an empty rack refuses a launch ------------------------------------
    check(rack() == 0, f"probes: a new ship starts with {rack()} probes, not 0")
    rt.run(f'TREK.Core.send({P}, "launchProbe", {{}})')
    net.pump(10)
    check(any("IGUI_TREK_ProbeNone" in n for n in rt.notes()),
          "probes: launching with an empty rack was not refused with a reason")
    check(rt.eval("TREK.Probes.active() == nil") is True,
          "probes: a probe went up out of an empty rack")

    # --- fabricating turns energy into a probe -----------------------------
    before = reserve()
    rt.run(f'TREK.Core.send({P}, "buildProbe", {{}})')
    net.pump(10)
    check(reserve() == before - cost,
          f"probes: fabricating moved the reserve {before} -> {reserve()}, "
          f"expected a single {cost}-unit deduction")
    check(rack() == 1, f"probes: the rack holds {rack()} after one fabrication")

    # And the rack has a ceiling, so energy cannot simply be banked away.
    cap = int(rt.eval("TREK.Config.MaxProbes"))
    for _ in range(cap + 3):
        rt.run(f'TREK.Core.send({P}, "buildProbe", {{}})')
        net.pump(4)
    check(rack() == cap,
          f"probes: the rack holds {rack()}, over the {cap} cap")
    check(any("IGUI_TREK_ProbeRackFull" in n for n in rt.notes()),
          "probes: a full rack refused without saying so")

    # --- launching costs a probe and not energy ----------------------------
    held, fuel = rack(), reserve()
    rt.run(f'TREK.Core.send({P}, "launchProbe", {{}})')
    net.pump(10)
    check(rack() == held - 1,
          f"probes: launching took {held - rack()} probes, expected 1")
    check(reserve() == fuel,
          f"probes: launching also spent energy ({fuel} -> {reserve()}); "
          f"the fabricator is what costs energy now")
    check(rt.eval("TREK.Probes.active() ~= nil") is True,
          "probes: nothing is in flight after a launch")

    # Racing launches make one probe and one deduction.
    held = rack()
    rt.run(f'TREK.Core.send({P}, "launchProbe", {{}})')
    rt.run(f'TREK.Core.send({P}, "launchProbe", {{}})')
    net.pump(10)
    check(rack() == held,
          "probes: a second launch while one was in flight took another probe")
    check(any("IGUI_TREK_ProbeActive" in n for n in rt.notes()),
          "probes: a second launch was refused without saying why")

    # --- the flight is persisted and advances ------------------------------
    progress = int(rt.eval("TREK.Probes.active().progress"))
    rt.run("TREK.Server.serviceProbe()")
    check(int(rt.eval("TREK.Probes.active().progress")) > progress,
          "probes: a service tick did not advance the flight")
    stored = rt.eval("SIM.globalData[TREK.Config.ContactKey].active.progress")
    check(stored is not None and int(stored) > 0,
          "probes: the flight's progress is not in the store, so a restart "
          "mid-flight would lose the probe and the power that bought it")

    # --- the first probe of a save always finds something ------------------
    # At a 65% hit rate one launch in three is 250 units and an hour of game
    # time for nothing, and the *first* one coming back empty is
    # indistinguishable from the feature being broken. It read exactly that
    # way the first time anybody played it.
    check(rt.eval("TREK.Util.state().probeEverFound") is None,
          "probes: a fresh ship already thinks a probe has found something")
    rt.run("SIM.randQueue = { 99, 30, 30 }")   # a roll that would MISS
    ticks = int(rt.eval("TREK.Config.ProbeFlightTicks"))
    for _ in range(ticks + 2):
        rt.run("TREK.Server.serviceProbe()")
    check(int(rt.eval("#TREK.Probes.contacts()")) == 1,
          "probes: the first probe of a save came back empty; the opening is "
          "guaranteed so that a new crew is never told 'nothing' first")
    check(rt.eval("TREK.Util.state().probeEverFound") is True,
          "probes: the ship did not record that it has found something")

    # And every probe after it is an honest roll again.
    rt.run("TREK.Probes.store().contacts = {}")
    rt.run(f'TREK.Core.send({P}, "launchProbe", {{}})')
    net.pump(10)
    rt.run("SIM.randQueue = { 99 }")
    for _ in range(ticks + 2):
        rt.run("TREK.Server.serviceProbe()")
    check(int(rt.eval("#TREK.Probes.contacts()")) == 0,
          "probes: a later probe still cannot come back empty, so the "
          "guarantee is permanent rather than an opening")

    # --- and it reports ----------------------------------------------------
    rt.run(f'TREK.Core.send({P}, "launchProbe", {{}})')
    net.pump(10)
    rt.run("SIM.randQueue = { 0, 30, 30 }")   # a find, then the scatter
    for _ in range(ticks + 2):
        rt.run("TREK.Server.serviceProbe()")
    check(rt.eval("TREK.Probes.active() == nil") is True,
          "probes: the probe never arrived")
    found = int(rt.eval("#TREK.Probes.contacts()"))
    check(found == 1,
          f"probes: {found} contacts after a probe that was made to find one")
    check(str(rt.eval("TREK.Probes.contacts()[1].kind")) == "dilithium",
          "probes: the report was not a dilithium trace")
    check(rt.eval("TREK.Probes.contacts()[1].approximate") is True,
          "probes: a long-range fix was reported as exact; the spread is what "
          "the tricorder is for")
    check(any("IGUI_TREK_ProbeFound" in n for n in rt.notes()),
          "probes: a probe came home with a contact and nobody was told -- an "
          "hour of game time with the only trace in console.txt")

    # --- an empty report is a real outcome ---------------------------------
    rt.run(f'TREK.Core.send({P}, "launchProbe", {{}})')
    net.pump(10)
    rt.run("SIM.randQueue = { 99 }")
    for _ in range(ticks + 2):
        rt.run("TREK.Server.serviceProbe()")
    check(int(rt.eval("#TREK.Probes.contacts()")) == found,
          "probes: a probe that found nothing added a contact anyway")
    check(any("returned nothing" in str(l) for l in rt.logLines()),
          "probes: an empty report said nothing at all")
    check(any("IGUI_TREK_ProbeEmpty" in n for n in rt.notes()),
          "probes: an empty report was never put in front of the player, so a "
          "probe that found nothing looks exactly like one that never flew")

    # --- a probe never reports outside the playable world -------------------
    # The first contact anybody got in a real game was placed far north of the
    # map entirely, and the crew walked toward a mark that could never have
    # had anything on it. The bearing is chosen against the world's own
    # bounds now, and the range is a few blocks rather than a quarter of the
    # map.
    rt.run("""
        SIM.worldBounds = { x1 = 1000, y1 = 1000, x2 = 3000, y2 = 3000 }
        TREK.Probes.store().contacts = {}
        local s = TREK.Util.state()
        s.probeEverFound = nil
        -- In a **corner** of the box, not the middle: with the origin
        -- centred, every bearing lands in bounds by accident and the check
        -- under test never has to do anything -- which is exactly how a
        -- mutation of it survived, twice.
        --
        -- And it is the **return point** that has to move, not s.x/s.y. The
        -- probe launches from where the crew are, which for a player standing
        -- in the cabin is where they would beam down to.
        s.x, s.y = 1080, 1080
        TREK.Ship.setReturnPoint(SIM.players[1], 1080, 1080, 0)
    """)
    reach = int(rt.eval("TREK.Config.ProbeMaxDistance"))
    check(reach <= 600,
          f"probes: a probe reaches {reach} squares, which is most of a map "
          f"rather than the few blocks the range is meant to be")
    for _ in range(6):
        rt.run(f'TREK.Core.send({P}, "buildProbe", {{}})')
        rt.run(f'TREK.Core.send({P}, "launchProbe", {{}})')
        net.pump(6)
        for _ in range(ticks + 2):
            rt.run("TREK.Server.serviceProbe()")
    outside = rt.eval("""(function()
        local b = SIM.worldBounds
        for _, c in ipairs(TREK.Probes.contacts()) do
            if c.x < b.x1 or c.x > b.x2 or c.y < b.y1 or c.y > b.y2 then
                return c.x .. "," .. c.y
            end
        end
        return false
    end)()""")
    check(outside is False,
          f"probes: a contact was reported at {outside}, outside the playable "
          f"world -- a mark the crew can walk toward for ever")

    # The scatter is applied after the bearing was checked, so it can push an
    # otherwise valid fix back out of the world. Reached directly, because a
    # probe has to arrive within sixty squares of an edge for it to matter and
    # waiting for that to happen by chance is not a test.
    rt.run("""
        TREK.Probes.store().contacts = {}
        TREK.Probes.store().active = {
            id = "probe:edge", x0 = 1080, y0 = 1080, bearing = 0,
            distance = 10, x = 1010, y = 1010, progress = 0, ticks = 1,
        }
        TREK.Util.state().probeEverFound = nil
        SIM.randQueue = { 0, 0 }      -- scatter both axes to the minimum
    """)
    rt.run("TREK.Server.serviceProbe()")
    fix = rt.eval("""(function()
        local c = TREK.Probes.contacts()[1]
        return c and (c.x .. "," .. c.y) or "none"
    end)()""")
    inside = rt.eval("""(function()
        local b, c = SIM.worldBounds, TREK.Probes.contacts()[1]
        if not c then return false end
        return c.x >= b.x1 and c.x <= b.x2 and c.y >= b.y1 and c.y <= b.y2
    end)()""")
    check(inside is True,
          f"probes: the report's scatter put the fix at {fix}, outside the "
          f"world -- the endpoint was valid and the scatter was not clamped")

    # And a contact already in a save from before the range was corrected is
    # retired rather than left on the map.
    rt.run("""
        local c = TREK.Probes.addContact("dilithium", 20000, 20000, 0, "old", true)
        TREK.Server.serviceContacts()
    """)
    stale = rt.eval("""(function()
        for _, c in ipairs(TREK.Probes.contacts()) do
            if c.probe == "old" then return c.status end
        end
        return "gone"
    end)()""")
    check(str(stale) == "invalid",
          f"probes: a contact outside the world reads {stale!r}; an old save's "
          f"unreachable marks have to retire themselves")
    rt.run("SIM.worldBounds = { x1 = 0, y1 = 0, x2 = 15000, y2 = 15000 }")

    # --- the probe launches from the CREW, not the ship's record -----------
    # The real bug, exactly as it happened: a new world where the shuttle has
    # never been called down leaves s.x, s.y at 0, so a probe fired from
    # Muldraugh reported a contact at 298,351 -- the far corner of the map --
    # while the crew stood at 10932,10031. The ship's record and the crew's
    # position are deliberately far apart here so that nothing can pass by
    # having them agree.
    HOME_X, HOME_Y = 10932, 10031
    rt.run(f"""
        local s = TREK.Util.state()
        s.landed, s.x, s.y = false, 0, 0
        s.probeEverFound = nil
        TREK.Ship.setReturnPoint(SIM.players[1], {HOME_X}, {HOME_Y}, 0)
        TREK.Probes.store().contacts = {{}}
        TREK.Probes.store().active = nil
    """)
    rt.run(f'TREK.Core.send({P}, "buildProbe", {{}})')
    rt.run(f'TREK.Core.send({P}, "launchProbe", {{}})')
    net.pump(8)
    for _ in range(ticks + 2):
        rt.run("TREK.Server.serviceProbe()")
    where = rt.eval("""(function()
        local c = TREK.Probes.contacts()[1]
        return c and (c.x .. "," .. c.y) or "none"
    end)()""")
    gap = rt.eval(f"""(function()
        local c = TREK.Probes.contacts()[1]
        if not c then return -1 end
        return math.floor(math.sqrt((c.x - {HOME_X})^2 + (c.y - {HOME_Y})^2))
    end)()""")
    reachable = int(rt.eval("TREK.Config.ProbeMaxDistance"))                 + int(rt.eval("TREK.Config.ProbeReportSpread"))
    check(gap is not None and 0 <= int(gap) <= reachable,
          f"probes: the contact came back at {where}, {gap} squares from the "
          f"crew at {HOME_X},{HOME_Y} -- a probe launches from where they are, "
          f"not from the ship's record of where she last landed")

    # A ship with no anchor anywhere -- never landed, and a crew who have
    # never beamed -- has no point to launch from, and says so rather than
    # firing from 0,0.
    rt.run("""
        local s = TREK.Util.state()
        s.landed, s.x, s.y = false, 0, 0
        local pd = TREK.Ship.playerData(SIM.players[1])
        pd.returnX, pd.returnY, pd.returnZ = nil, nil, nil
        s.returnX, s.returnY, s.returnZ = nil, nil, nil
        TREK.Probes.store().active = nil
    """)
    rt.run(f'TREK.Core.send({P}, "buildProbe", {{}})')
    rt.run(f'TREK.Core.send({P}, "launchProbe", {{}})')
    net.pump(8)
    check(any("IGUI_TREK_ProbeNoFix" in n for n in rt.notes()),
          "probes: a launch with no position fix anywhere was not refused; it "
          "would fire from 0,0 and report the corner of the map")
    rt.run("SIM.log = {}")
    rt.run(f"TREK.Ship.setReturnPoint({P}, {HOME_X}, {HOME_Y}, 0)")

    # --- the refusals ------------------------------------------------------
    rt.run(f"{P}.x, {P}.y, {P}.z = 3000.5, 3000.5, 0")
    rt.run(f'TREK.Core.send({P}, "buildProbe", {{}})')
    net.pump(10)
    check(any("IGUI_TREK_ProbeAboard" in n for n in rt.notes()),
          "probes: fabricating from outside the ship was not refused")

    rt.run("""
        local U = TREK.Util
        local x, y = U.at(1, 2)
        SIM.players[1].x, SIM.players[1].y = x + 0.5, y + 0.5
        SIM.players[1].z, SIM.players[1].lastZ = TREK.Config.CabinZ, TREK.Config.CabinZ
        -- Empty reserve AND no spares: afford() burns a crystal when the
        -- reserve is short, so a spare in the chamber would fund it.
        U.state().power = 1
        U.state().crystals = 0
        U.state().probes = 0
    """)
    rt.run(f'TREK.Core.send({P}, "buildProbe", {{}})')
    net.pump(10)
    check(any("IGUI_TREK_ProbeNoPower" in n for n in rt.notes()),
          "probes: fabricating on an empty reserve was not refused")

    for w in rt.warnings():
        fail(f"probes: {w}")

    print("probes: energy buys a probe and a launch spends one, the rack has "
          "a ceiling, racing launches make one job, the flight is persisted "
          "and advances, a find is an approximate fix and an empty result "
          "says so, and every refusal names itself")


def contact_world():
    """A contact becomes a real crystal, once somebody goes and looks.

    This is what "results should be real" means: the probe reports a record,
    and the crystal is put in the world when a player loads the chunk --
    because asking the engine about an unloaded chunk is the one thing
    DEV_GUIDE forbids outright.
    """
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('owner', 2000.5, 2000.5, 0)")
    net.start()

    rt.run("""
        TREK.Probes.addContact("dilithium", 2400, 2400, 0, "probe:1", true)
        TREK.Probes.publish()
    """)
    contact = rt.eval("TREK.Probes.contacts()[1].id")

    # Nobody near it: nothing is placed, and the contact is untouched. A
    # distant chunk is "cannot tell", never "nothing there".
    rt.run("TREK.Server.serviceContacts()")
    check(rt.eval("TREK.Probes.contacts()[1].placed") is None,
          "contact world: a crystal was placed with nobody within miles of it")
    check(str(rt.eval("TREK.Probes.contacts()[1].status")) == "reported",
          "contact world: a contact nobody has visited changed status")

    # Walk over. The crystal lands on real ground and the fix stops being a
    # guess, because the ship now knows exactly where it put it.
    # streamX/streamY are what decides which chunks are loaded, and they lag
    # the character until streaming ticks -- exactly as the engine's do. Move
    # both, or the square is "not loaded yet" and nothing is placed.
    rt.run("""
        local p = SIM.players[1]
        p.x, p.y, p.streamX, p.streamY = 2400.5, 2400.5, 2400.5, 2400.5
    """)
    rt.run("TREK.Server.serviceContacts()")
    check(rt.eval("TREK.Probes.contacts()[1].placed") is True,
          "contact world: standing on the contact did not place a crystal")
    check(str(rt.eval("TREK.Probes.contacts()[1].status")) == "investigated",
          "contact world: a placed contact is still only 'reported'")
    check(rt.eval("TREK.Probes.contacts()[1].approximate") is False,
          "contact world: the fix is still marked approximate after the ship "
          "put the crystal down itself")

    on_ground = rt.eval("""(function()
        local c = TREK.Probes.contacts()[1]
        local sq = TREK.Util.square(c.x, c.y, c.z, false)
        if not sq then return "no square" end
        local items = sq:getWorldObjects()
        for i = 0, items:size() - 1 do
            local o = items:get(i)
            local it = o and o.getItem and o:getItem()
            if it and it:getFullType() == TREK.Config.DilithiumItem then
                return true
            end
        end
        return false
    end)()""")
    check(on_ground is True,
          f"contact world: no crystal is lying on the contact's square ({on_ground})")

    # Placing twice would litter the map with crystals; the flag is what stops
    # it, and this is the "Two shuttles" shape again.
    rt.run("TREK.Server.serviceContacts()")
    count = int(rt.eval("""(function()
        local c = TREK.Probes.contacts()[1]
        local sq = TREK.Util.square(c.x, c.y, c.z, false)
        local n, items = 0, sq:getWorldObjects()
        for i = 0, items:size() - 1 do
            local o = items:get(i)
            local it = o and o.getItem and o:getItem()
            if it and it:getFullType() == TREK.Config.DilithiumItem then
                n = n + 1
            end
        end
        return n
    end)()"""))
    check(count == 1,
          f"contact world: {count} crystals on the square after a second pass")

    # Taking it retires the contact, so the map stops advertising it.
    rt.run("""
        local c = TREK.Probes.contacts()[1]
        local sq = TREK.Util.square(c.x, c.y, c.z, false)
        sq.worldObjects = {}
    """)
    rt.run("TREK.Server.serviceContacts()")
    check(str(rt.eval("TREK.Probes.contacts()[1].status")) == "recovered",
          "contact world: picking the crystal up left the contact live, so "
          "the map would keep pointing at an empty square")

    # --- nowhere to put it -------------------------------------------------
    # A contact in the middle of a lake or inside a building. Loaded, looked
    # at, and genuinely no ground: that retires the contact rather than
    # retrying the same squares for the life of the save. The distinction
    # that matters is against the case above -- *not loaded* must never do
    # this, or a player walking past the edge of a contact destroys it.
    rt.run("""
        local P, U = TREK.Probes, TREK.Util
        P.addContact("dilithium", 2600, 2600, 0, "probe:2", true)
        local p = SIM.players[1]
        p.x, p.y, p.streamX, p.streamY = 2600.5, 2600.5, 2600.5, 2600.5
        -- Solid everywhere the search can reach.
        local r = TREK.Config.ContactPlaceRadius
        for dx = -r, r do for dy = -r, r do
            local sq = SIM.rawSquare(2600 + dx, 2600 + dy, 0)
            sq.solid = true
        end end
    """)
    rt.run("TREK.Server.serviceContacts()")
    doomed = rt.eval("""(function()
        for _, c in ipairs(TREK.Probes.contacts()) do
            if c.probe == "probe:2" then return c.status end
        end
        return "gone"
    end)()""")
    check(str(doomed) == "expired",
          f"contact world: a contact with no ground anywhere near it reads "
          f"{doomed!r}; it should expire rather than be retried for ever")
    check(any("no ground within" in w for w in rt.warnings()),
          "contact world: a contact was expired without saying why")
    rt.run("SIM.log = {}")

    for w in rt.warnings():
        fail(f"contact world: {w}")

    print("contact world: a contact stays a record until somebody loads its "
          "chunk, then becomes one crystal on real ground exactly once, "
          "retires itself when the crystal is taken, and expires only when "
          "the ground really was looked at and had nowhere to put it")


def contact_reveal():
    """The ground around a contact is uncovered on the player's own map."""
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('owner', 2000.5, 2000.5, 0)")
    net.start()

    check(len(rt.eval("SIM.revealed") or []) == 0,
          "contact reveal: something revealed map before any contact existed")

    rt.run("""
        TREK.Probes.addContact("dilithium", 4400, 9100, 0, "probe:1", true)
        TREK.Probes.publish()
    """)
    boxes = rt.eval("""(function()
        local out = {}
        for _, r in ipairs(SIM.revealed) do
            table.insert(out, r.x1 .. "," .. r.y1 .. "," .. r.x2 .. "," .. r.y2)
        end
        return table.concat(out, " ")
    end)()""")
    radius = int(rt.eval("TREK.Config.ContactRevealRadius"))
    want = f"{4400 - radius},{9100 - radius},{4400 + radius},{9100 + radius}"
    check(want in str(boxes),
          f"contact reveal: the map was not uncovered around the contact "
          f"(wanted {want}, got {boxes})")

    # Revealing once per contact: publishing again must not re-reveal, or a
    # ship that commits every second would call into the engine every second.
    n = len(str(boxes).split())
    rt.run("TREK.Probes.publish(); TREK.Probes.publish()")
    check(int(rt.eval("#SIM.revealed")) == n,
          f"contact reveal: publishing again revealed the same ground twice "
          f"({n} -> {int(rt.eval('#SIM.revealed'))})")

    for w in rt.warnings():
        fail(f"contact reveal: {w}")

    print("contact reveal: a report uncovers the ground around it on this "
          "player's own map, once per contact")


def tapes():
    """The tape shelf: a row of cassettes that each carry their own recording.

    The one failure this exists for is a **blank tape**. Every tape in the
    shelf is the same item type, so a shelf of the right size, drawn, openable
    and full of cassettes is indistinguishable from a working one until each
    tape is asked what recording it is carrying -- and a tape with none goes
    into the television and does nothing, with nothing in any log. That is the
    same shape as the empty lockers and the uniform whose GUID never resolved,
    and it gets the same answer: read the result back off the object.
    """
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('owner', 2000.5, 2000.5, 0)")
    net.start()
    rt.run("TREK.Transport.beamUp(SIM.players[1])")
    net.pump(180)
    if died(rt, "tapes, beaming up"):
        return

    listed = str(rt.eval('table.concat(TREK_TapeIds or {}, ",")'))
    ids = [i for i in listed.split(",") if i]
    check(len(ids) > 0, "tapes: TREK_Tapes.lua registered no tape ids at all")

    # Every id in the shelf's list is a recording the engine actually holds.
    # An id in one file and not the other is a blank tape, and the generator
    # writes both -- so this is the check that the generator was run.
    for tape_id in ids:
        known = rt.eval('SIM.recordedMedia():getMediaData("%s") ~= nil' % tape_id)
        check(known is True,
              f"tapes: nothing is registered as {tape_id}, so its tape is blank")

    # The shelf, found by its tag rather than by its coordinates, because the
    # square is the layout's business and this is not the test that owns it.
    held = rt.eval("""(function()
        local C, U = TREK.Config, TREK.Util
        for ox = 0, C.CabinW do for oy = 0, C.CabinL do
            local x, y = U.at(ox, oy)
            local sq = SIM.rawSquare(x, y, C.CabinZ)
            for _, o in ipairs(sq.objects) do
                if o.modData and o.modData.TREK == "tapes" and o.container then
                    local blank, titles = 0, {}
                    for _, it in ipairs(o.container.items) do
                        if it:getFullType() == C.TapeItem then
                            local d = it:getMediaData()
                            if d then table.insert(titles, d:getId())
                            else blank = blank + 1 end
                        end
                    end
                    return #titles, blank, table.concat(titles, ",")
                end
            end
        end end
        return -1, -1, ""
    end)()""")
    labelled, blank, titles = int(held[0]), int(held[1]), str(held[2])

    check(labelled >= 0, "tapes: no container tagged 'tapes' in the cabin at all")
    check(labelled == len(ids),
          f"tapes: the shelf holds {labelled} labelled tapes and the ship "
          f"carries {len(ids)} recordings")
    check(blank == 0, f"tapes: {blank} blank tape(s) in the shelf")
    for tape_id in ids:
        check(tape_id in titles,
              f"tapes: no tape in the shelf is carrying {tape_id}")

    # A second build must not re-label the tapes the crew is already watching,
    # and must not hand out a second set. The pass runs on every arrival, so
    # "it is safe to run twice" is not a nicety.
    rt.run("TREK.Build.buildCabin()")
    again = rt.eval("""(function()
        local C, U = TREK.Config, TREK.Util
        for ox = 0, C.CabinW do for oy = 0, C.CabinL do
            local x, y = U.at(ox, oy)
            local sq = SIM.rawSquare(x, y, C.CabinZ)
            for _, o in ipairs(sq.objects) do
                if o.modData and o.modData.TREK == "tapes" and o.container then
                    local n = 0
                    for _, it in ipairs(o.container.items) do
                        if it:getFullType() == C.TapeItem then n = n + 1 end
                    end
                    return n
                end
            end
        end end
        return -1
    end)()""")
    check(int(again) == len(ids),
          f"tapes: a second build left {int(again)} tapes in a shelf that "
          f"should hold {len(ids)}")

    for w in rt.warnings():
        fail(f"tapes: {w}")

    print("tapes: the shelf is stocked, every tape carries its own registered "
          "recording, none is blank, and building twice neither re-labels them "
          "nor hands out a second set")


# ---------------------------------------------------------------------------
# The downed ensign (ENSIGN.md)
# ---------------------------------------------------------------------------
def tick_missions(rt):
    rt.run("TREK.Missions.serviceDistress(); TREK.Missions.serviceMissions()")


def make_call(rt, net):
    """Makes the ship make a call now, and returns its id."""
    rt.run("""
        local data = TREK.Probes.store()
        data.distress = nil
        data.nextDistressAt = SIM.worldAgeHours
    """)
    tick_missions(rt)
    net.pump(4)
    return rt.eval("TREK.Probes.distress() and TREK.Probes.distress().id")


def accept_call(rt, net, player, tx, ty):
    """Makes a call, accepts it, and moves the ensign to (tx, ty).

    The answer is given from the transporter pad, because the server only
    takes one from aboard; the player is walked back afterwards.
    """
    call = make_call(rt, net)
    back = rt.eval(f"{{ {player}.x, {player}.y, {player}.z }}")
    rt.run(f"""
        local x, y, z = TREK.Util.padSpot()
        local p = {player}
        p.x, p.y, p.z, p.lastZ = x + 0.5, y + 0.5, z, z
        p.streamX, p.streamY = x + 0.5, y + 0.5
    """)
    rt.run(f'TREK.Core.send({player}, "distressAnswer", '
           f'{{ id = "{call}", accept = true }})')
    net.pump(4)
    walk_to(rt, back[1], back[2], back[3])
    rt.run(f"""
        local m = TREK.Probes.mission()
        m.tx, m.ty = {tx}, {ty}
    """)
    return rt.eval("TREK.Probes.mission() and TREK.Probes.mission().id")


def walk_to(rt, x, y, z=0, who=1):
    """Moves a player *and* their streaming, so the ground there loads."""
    rt.run(f"""
        local p = SIM.players[{who}]
        p.x, p.y, p.z, p.lastZ = {x}, {y}, {z}, {z}
        p.streamX, p.streamY = {x}, {y}
    """)


def figures(rt, x, y, z=0):
    """How many ensign figures are lying on a square."""
    return int(rt.eval(f"""(function()
        local sq = SIM.rawSquare({x}, {y}, {z})
        local n = 0
        for _, w in ipairs(sq.worldObjects) do
            local it = w.item
            if it and TREK.Config.EnsignItems[it.fullType] then n = n + 1 end
        end
        return n
    end)()"""))


def ensign_menu(rt, x, y, who=1):
    """Right-clicks a square outside and returns what the ensign's menu offered."""
    rt.run(f"""
        local p = SIM.players[{who}]
        SIM.aim.dx = {x} + 0.5 - p.x
        SIM.aim.dy = {y} + 0.5 - p.y
        ensignCtx = SIM.contextMenu()
        TREK.EnsignUI.fillMenu(0, ensignCtx, {{}}, false)
    """)
    return str(rt.eval("ensignCtx:labels()"))


def inventory_count(rt, full, who=1):
    return int(rt.eval(f"""(function()
        local n = 0
        for _, it in ipairs(SIM.players[{who}].inventory.items) do
            if it.fullType == "{full}" then n = n + 1 end
        end
        return n
    end)()"""))


def ensign_missions(rt):
    """How many downedPersonnel contacts the store holds, live or not."""
    return int(rt.eval("""(function()
        local n = 0
        for _, c in ipairs(TREK.Probes.contacts()) do
            if c.kind == "downedPersonnel" then n = n + 1 end
        end
        return n
    end)()"""))


def distress():
    """A distress call: heard, made once, answered, declined, lapsed.

    ENSIGN.md section 2. The call is the half of the mission with no world
    object at all, so everything here is about the store and the clock.
    """
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('owner', 2000.5, 2000.5, 0)")
    net.start()
    P = "SIM.players[1]"
    store = lambda field: rt.eval(f"TREK.Probes.store().{field}")
    hours = lambda: float(rt.eval("SIM.worldAgeHours"))

    # --- nobody has been aboard: the ship is not listening ------------------
    tick_missions(rt)
    check(store("nextDistressAt") is None,
          "distress: a ship nobody has boarded scheduled a distress call")

    rt.run(f"TREK.Transport.beamUp({P})")
    net.pump(210)
    if died(rt, "distress, beaming up"):
        return

    # --- the first time it can hear, the first call is scheduled, not made ---
    tick_missions(rt)
    due = store("nextDistressAt")
    check(due is not None,
          "distress: a boarded, powered ship never scheduled its first call")
    check(rt.eval("TREK.Probes.distress() == nil") is True,
          "distress: a call arrived the instant the crew first boarded")
    first = float(rt.eval("TREK.Config.DistressFirstHours"))
    check(due is not None and abs(float(due) - hours() - first) < 1e-6,
          f"distress: the first call is due at {due}, not {first} hours in")

    rt.run("SIM.advanceHours(TREK.Config.DistressFirstHours)")
    tick_missions(rt)
    net.pump(4)
    check(rt.eval("TREK.Probes.distress() ~= nil") is True,
          "distress: no call came when it was due")
    if rt.eval("TREK.Probes.distress() == nil") is True:
        return
    lo = int(rt.eval("TREK.Config.EnsignMinDistance"))
    hi = int(rt.eval("TREK.Config.EnsignMaxDistance"))
    # Measured from the crew: the player is aboard, so from where they would
    # beam down -- 2000,2000 -- and not from s.x, s.y, which is 0,0 in a
    # world where the ship has never been set down (PROBES.md).
    gap = float(rt.eval("math.sqrt((TREK.Probes.distress().tx - 2000)^2 "
                        "+ (TREK.Probes.distress().ty - 2000)^2)"))
    check(lo - 2 <= gap <= hi + 2,
          f"distress: the ensign is {gap:.0f} squares from the crew, outside "
          f"{lo}..{hi}")
    check(rt.eval("TREK.Util.inWorld(TREK.Probes.distress().tx, "
                  "TREK.Probes.distress().ty)") is True,
          "distress: the ensign is down outside the playable world")
    check(any("IGUI_TREK_DistressNote" in n for n in rt.notes()),
          "distress: a call came in and nobody was told")
    check(rt.eval('SIM.heardSound("TREK_DistressCall")') is True,
          "distress: a call came in without a sound")
    for field in ("name", "division", "body", "compass"):
        check(rt.eval(f"TREK.Probes.distress().{field}") is not None,
              f"distress: the call has no {field}, so two crew could each "
              f"imagine a different ensign")
    item = rt.eval("TREK.Config.ensignItem(TREK.Probes.distress().body, "
                   "TREK.Probes.distress().division)")
    check(item is not None and rt.eval(f'TREK.Config.EnsignItems["{item}"]') is True,
          f"distress: the call's body and division name no figure ({item})")

    first_id = str(rt.eval("TREK.Probes.distress().id"))
    tick_missions(rt)
    check(str(rt.eval("TREK.Probes.distress().id")) == first_id,
          "distress: a second call replaced the pending one")

    # --- answering from the wrong place, or the wrong call ------------------
    # Walked out and back with the streaming, not beamed: this is about where
    # the server thinks the player is, and a beam is a different test.
    aboard = (float(rt.eval(f"{P}.x")), float(rt.eval(f"{P}.y")),
              int(rt.eval(f"{P}.z")))
    walk_to(rt, 3000.5, 3000.5)
    rt.run(f'TREK.Core.send({P}, "distressAnswer", {{ id = "{first_id}", accept = true }})')
    net.pump(4)
    check(any("IGUI_TREK_DistressAboard" in n for n in rt.notes()),
          "distress: a call was answered from outside the ship")
    check(rt.eval("TREK.Probes.mission() == nil") is True,
          "distress: answering from outside made a mission anyway")
    walk_to(rt, *aboard)
    net.pump(4)

    rt.run(f'TREK.Core.send({P}, "distressAnswer", {{ id = "distress:0", accept = true }})')
    net.pump(4)
    check(any("IGUI_TREK_DistressGone" in n for n in rt.notes()),
          "distress: an answer to a call that is not pending was not refused")
    check(rt.eval("TREK.Probes.distress() ~= nil") is True,
          "distress: a wrong answer threw away the call that was pending")

    # --- declining ------------------------------------------------------------
    rt.run(f'TREK.Core.send({P}, "distressAnswer", {{ id = "{first_id}", accept = false }})')
    net.pump(4)
    check(rt.eval("TREK.Probes.distress() == nil") is True,
          "distress: a declined call is still pending")
    check(rt.eval("TREK.Probes.mission() == nil") is True,
          "distress: declining made a mission")
    check(any("IGUI_TREK_DistressDeclinedNote" in n for n in rt.notes()),
          "distress: declining said nothing")
    gap = float(store("nextDistressAt")) - hours()
    want = float(rt.eval("TREK.Config.DistressIntervalHours"))
    check(abs(gap - want) < 1e-6,
          f"distress: the next call after a decline is {gap} hours off, not {want}")

    # --- ignoring one ---------------------------------------------------------
    rt.run("SIM.advanceHours(TREK.Config.DistressIntervalHours)")
    tick_missions(rt)
    check(rt.eval("TREK.Probes.distress() ~= nil") is True,
          "distress: no call came after the interval")
    rt.run("SIM.advanceHours(TREK.Config.DistressOfferHours)")
    tick_missions(rt)
    net.pump(4)
    check(rt.eval("TREK.Probes.distress() == nil") is True,
          "distress: an unanswered call never lapsed")
    check(any("IGUI_TREK_DistressLapsedNote" in n for n in rt.notes()),
          "distress: a call faded without anybody being told")

    # --- accepting ------------------------------------------------------------
    call_id = make_call(rt, net)
    tx = int(rt.eval("TREK.Probes.distress().tx"))
    ty = int(rt.eval("TREK.Probes.distress().ty"))
    rt.run(f'TREK.Core.send({P}, "distressAnswer", {{ id = "{call_id}", accept = true }})')
    # A second answer to the same call in the same instant: one mission.
    rt.run(f'TREK.Core.send({P}, "distressAnswer", {{ id = "{call_id}", accept = true }})')
    net.pump(4)
    live = ensign_missions(rt)
    check(live == 1, f"distress: two answers to one call made {live} missions")
    if rt.eval("TREK.Probes.mission() == nil") is True:
        fail("distress: accepting made no mission")
        return
    check(rt.eval("TREK.Probes.mission().approximate") is True,
          "distress: the rescue's map fix is exact; the circle is what the "
          "tricorder is for")
    spread = int(rt.eval("TREK.Config.EnsignReportSpread"))
    fx = int(rt.eval("TREK.Probes.mission().x"))
    fy = int(rt.eval("TREK.Probes.mission().y"))
    check(abs(fx - tx) <= spread and abs(fy - ty) <= spread,
          f"distress: the fix {fx},{fy} is further than {spread} from where "
          f"the ensign is ({tx},{ty})")
    life = float(rt.eval("TREK.Config.EnsignLifeHours"))
    left = float(rt.eval("TREK.Probes.mission().deadline")) - hours()
    check(abs(left - life) < 1e-6,
          f"distress: the clock starts at {left} hours, not {life}")
    check(any("IGUI_TREK_DistressAcceptedNote" in n for n in rt.notes()),
          "distress: accepting said nothing")

    # --- no new call while a rescue is live -----------------------------------
    rt.run("SIM.advanceHours(TREK.Config.DistressIntervalHours + 1)")
    tick_missions(rt)
    check(rt.eval("TREK.Probes.distress() == nil") is True,
          "distress: a second call came in while a rescue was live")

    for w in rt.warnings():
        fail(f"distress: {w}")

    # --- a ship with no dilithium hears nothing -------------------------------
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('owner', 2000.5, 2000.5, 0)")
    net.start()
    rt.run(f"TREK.Transport.beamUp({P})")
    net.pump(210)
    rt.run("local s = TREK.Util.state(); s.power = 0; s.crystals = 0")
    tick_missions(rt)
    check(rt.eval("TREK.Probes.store().nextDistressAt") is None,
          "distress: a ship with no dilithium at all is listening for calls")
    for w in rt.warnings():
        fail(f"distress (unpowered): {w}")

    print("distress: the ship listens once it is boarded and powered, the "
          "first call is scheduled rather than instant, one call at a time "
          "measured from the crew, a wrong or out-of-place answer is refused "
          "by name, declining and ignoring both schedule the next, and "
          "accepting makes exactly one mission with its clock and an "
          "approximate fix")


def ensign_world():
    """The ensign is put on the ground, heard, found, and beamed out -- once.

    ENSIGN.md sections 2 and 3: a mission is a record until a player loads
    the ground, then one figure on real ground; the beacon is the server's,
    the chirp is the client's; the tricorder finds the ensign; and a rescue
    pays out exactly once however many times it is asked for.
    """
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('owner', 2000.5, 2000.5, 0)")
    net.start()
    P = "SIM.players[1]"
    rt.run(f"TREK.Transport.beamUp({P})")
    net.pump(210)
    if died(rt, "ensign world, beaming up"):
        return

    TX, TY = 2600, 2600
    mid = accept_call(rt, net, P, TX, TY)
    if mid is None:
        fail("ensign world: no mission to work with")
        return
    m = lambda field: rt.eval(f"TREK.Probes.mission() and TREK.Probes.mission().{field}")

    # --- nobody near: nothing is placed -----------------------------------------
    tick_missions(rt)
    check(m("placed") is None,
          "ensign world: a figure was put down with nobody within miles")

    # --- walk over: one figure, on real ground, square to the camera -----------
    walk_to(rt, TX + 12.5, TY + 0.5)
    tick_missions(rt)
    check(m("placed") is True, "ensign world: standing nearby placed nothing")
    if m("ex") is None:
        return
    ex, ey = int(m("ex")), int(m("ey"))
    item = str(m("item"))
    check(figures(rt, ex, ey) == 1,
          f"ensign world: {figures(rt, ex, ey)} figures at {ex},{ey}, expected 1")
    check(item == str(rt.eval("TREK.Config.ensignItem(TREK.Probes.mission().body, "
                              "TREK.Probes.mission().division)")),
          f"ensign world: the figure {item} is not the body and division the "
          f"call described")
    yaw = rt.eval(f"""(function()
        for _, w in ipairs(SIM.rawSquare({ex}, {ey}, 0).worldObjects) do
            if w.item and w.item.fullType == "{item}" then
                return w.item.worldZRotation
            end
        end
    end)()""")
    check(yaw == 0,
          f"ensign world: the figure sits at {yaw} degrees; a dropped world "
          f"model picks its own angle unless it is straightened")
    tick_missions(rt)
    check(figures(rt, ex, ey) == 1,
          "ensign world: a second pass put down a second figure")

    # --- the beacon: the server's noise, on a timer -------------------------------
    beacons = lambda: int(rt.eval("#SIM.worldSounds"))
    check(beacons() >= 1, "ensign world: the beacon never sounded")
    n = beacons()
    tick_missions(rt)
    check(beacons() == n,
          "ensign world: the beacon fired twice in the same game minute")
    rt.run("SIM.advanceHours((TREK.Config.BeaconEveryMinutes + 1) / 60)")
    tick_missions(rt)
    check(beacons() == n + 1,
          "ensign world: the beacon did not sound again after its interval")
    lx = int(rt.eval("SIM.worldSounds[#SIM.worldSounds].x"))
    ly = int(rt.eval("SIM.worldSounds[#SIM.worldSounds].y"))
    lr = int(rt.eval("SIM.worldSounds[#SIM.worldSounds].radius"))
    check(lx == ex and ly == ey and lr == int(rt.eval("TREK.Config.BeaconRadius")),
          "ensign world: the beacon sounded somewhere other than the "
          "ensign's square, or at the wrong radius")

    # --- the chirp: each client, at the ensign's square --------------------------
    rt.run("SIM.sounds = {}")
    rt.run("TREK.EnsignUI.serviceChirp()")
    chirp = rt.eval("""(function()
        for _, s in ipairs(SIM.sounds) do
            if s.name == "TREK_CombadgeChirp" and s.square then
                return s.square.x .. "," .. s.square.y
            end
        end
        return false
    end)()""")
    check(chirp == f"{ex},{ey}",
          f"ensign world: the chirp came from {chirp}, not from {ex},{ey}")
    # Fifty squares: out of earshot, and **still loaded**. Two hundred would
    # have passed on the ground simply being unloaded, which is how this check
    # first survived a mutation that deleted the range test altogether.
    walk_to(rt, ex + 50.5, ey + 0.5)
    net.clock += 20000
    check(rt.eval(f"TREK.Util.chunkLoaded({ex}, {ey}, 0)") is True,
          "ensign world: the ground is not loaded at fifty squares, so the "
          "chirp's range is not what is being tested")
    check(rt.eval("TREK.EnsignUI.serviceChirp()") is False,
          "ensign world: a chirp played for a player fifty squares away")

    # --- the tricorder finds the ensign ---------------------------------------------
    def sweep_from(x, y):
        walk_to(rt, x, y)
        rt.run(f"""
            TREK.MedKit.lastSweepAt = nil
            TREK.MedKit.lastSweep = nil
            TREK.MedKit.startSweep({P})
            for _ = 1, 5000 do
                if not TREK.MedKit.serviceSweep() then break end
            end
        """)
        if rt.eval("TREK.MedKit.lastSweep and TREK.MedKit.lastSweep.personnel") is None:
            return None
        return (int(rt.eval("TREK.MedKit.lastSweep.personnel.dist")),
                str(rt.eval("TREK.MedKit.lastSweep.personnel.compass")))

    fix = sweep_from(ex + 20.5, ey + 0.5)
    check(fix is not None, "ensign world: a sweep twenty squares away missed her")
    if fix is not None:
        check(abs(fix[0] - 20) <= 1 and fix[1] == "W",
              f"ensign world: the sweep put the ensign {fix[0]} squares "
              f"{fix[1]}, not 20 W")
    check(sweep_from(ex + 120.5, ey + 0.5) is None,
          "ensign world: a sweep far out of range claimed to see the ensign")

    # --- the menu --------------------------------------------------------------------
    walk_to(rt, ex + 6.5, ey + 0.5)
    labels = ensign_menu(rt, ex, ey)
    check("IGUI_TREK_EnsignExamine" in labels and "IGUI_TREK_EnsignRescue" in labels,
          f"ensign world: right-clicking the ensign offered {labels!r}")
    greyed = rt.eval("""(function()
        for _, o in ipairs(ensignCtx.options) do
            if o.name:find("IGUI_TREK_EnsignRescue", 1, true) then
                return o.notAvailable == true
            end
        end
    end)()""")
    check(greyed is True,
          "ensign world: Beam to safety is live from six squares away")
    beside = ensign_menu(rt, ex + 1, ey)
    check("IGUI_TREK_EnsignRescue" in beside,
          "ensign world: a click on the square beside the ensign found "
          "nothing -- a figure on the ground needs the margin")
    check(ensign_menu(rt, ex + 4, ey) == "",
          "ensign world: a click four squares away still offered the menu")

    ensign_menu(rt, ex, ey)
    rt.run("""
        for _, o in ipairs(ensignCtx.options) do
            if o.name:find("IGUI_TREK_EnsignExamine", 1, true) then
                o.fn(o.target, unpack(o.args))
            end
        end
    """)
    check(any("IGUI_TREK_EnsignExamineText" in n for n in rt.notes()),
          "ensign world: Examine said nothing")

    # --- too far to beam ---------------------------------------------------------
    rt.run(f'TREK.Core.send({P}, "rescueEnsign", {{ id = "{mid}" }})')
    net.pump(4)
    check(any("IGUI_TREK_EnsignTooFar" in n for n in rt.notes()),
          "ensign world: a rescue from six squares was not refused by name")
    check(str(rt.eval(f'TREK.Probes.byId("{mid}").status')) != "completed",
          "ensign world: a rescue from too far away completed")

    # --- the rescue, asked for twice in one instant --------------------------------
    walk_to(rt, ex + 1.5, ey + 0.5)
    rations0 = inventory_count(rt, "TrekShuttle.TrekRationPack")
    hypos0 = inventory_count(rt, "TrekShuttle.TrekHypospray")
    patterns0 = int(rt.eval("TREK.Replicator.patternCount()"))
    rt.run(f'TREK.Core.send({P}, "rescueEnsign", {{ id = "{mid}" }})')
    rt.run(f'TREK.Core.send({P}, "rescueEnsign", {{ id = "{mid}" }})')
    net.pump(6)
    check(str(rt.eval(f'TREK.Probes.byId("{mid}").status')) == "completed",
          "ensign world: the rescue did not complete the mission")
    check(figures(rt, ex, ey) == 0,
          "ensign world: the ensign was beamed out and is still sitting there")
    learned = int(rt.eval("TREK.Replicator.patternCount()")) - patterns0
    want = int(rt.eval("TREK.Config.RescuePatternsPerRescue"))
    check(learned == want,
          f"ensign world: the rescue taught {learned} patterns, not {want}")
    check(rt.eval('TREK.Replicator.knows("Base.Antibiotics")') is True,
          "ensign world: the first reward pattern was not learned")
    rations = inventory_count(rt, "TrekShuttle.TrekRationPack") - rations0
    hypos = inventory_count(rt, "TrekShuttle.TrekHypospray") - hypos0
    check(rations == 2 and hypos == 1,
          f"ensign world: the supply came to {rations} rations and {hypos} "
          f"hyposprays for a rescue asked for twice; it must pay once")
    check(any("IGUI_TREK_EnsignSafe" in n for n in rt.notes()),
          "ensign world: the second rescue was not told the ensign was safe")
    check(any("IGUI_TREK_EnsignRescuedNote" in n for n in rt.notes()),
          "ensign world: nobody was told the ensign was safe")
    gap = float(rt.eval("TREK.Probes.store().nextDistressAt")) - float(rt.eval("SIM.worldAgeHours"))
    check(abs(gap - float(rt.eval("TREK.Config.DistressIntervalHours"))) < 1e-6,
          "ensign world: the next call was not scheduled after the rescue")
    check(rt.eval("TREK.Probes.mission() == nil") is True,
          "ensign world: a completed rescue still reads as the live mission")

    # And the next rescue teaches the *next* patterns, not the same three.
    walk_to(rt, TX + 12.5, TY + 0.5)
    mid2 = accept_call(rt, net, P, TX, TY)
    tick_missions(rt)
    if m("ex") is None:
        fail("ensign world: the second rescue was never placed")
        return
    ex2, ey2 = int(m("ex")), int(m("ey"))
    walk_to(rt, ex2 + 1.5, ey2 + 0.5)
    rt.run(f'TREK.Core.send({P}, "rescueEnsign", {{ id = "{mid2}" }})')
    net.pump(6)
    check(rt.eval('TREK.Replicator.knows("Base.Disinfectant")') is True,
          "ensign world: a second rescue did not move on down the reward list")

    for w in rt.warnings():
        fail(f"ensign world: {w}")

    print("ensign world: placed only when the ground loads, once, facing the "
          "camera; the beacon is the server's and keeps time; the chirp comes "
          "from the ensign's square and only for players near it; the "
          "tricorder gives the right bearing; the menu has a margin and greys "
          "the beam with a reason; a rescue asked for twice pays out exactly "
          "once and schedules the next call")


def ensign_edges():
    """The clock, a figure carried off, nowhere to sit, and a safehouse."""
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('owner', 2000.5, 2000.5, 0)")
    net.start()
    P = "SIM.players[1]"
    rt.run(f"TREK.Transport.beamUp({P})")
    net.pump(210)
    if died(rt, "ensign edges, beaming up"):
        return
    m = lambda field: rt.eval(f"TREK.Probes.mission() and TREK.Probes.mission().{field}")

    # --- carried off: the figure is put back ------------------------------------
    accept_call(rt, net, P, 2600, 2600)
    walk_to(rt, 2612.5, 2600.5)
    tick_missions(rt)
    ex, ey = int(m("ex")), int(m("ey"))
    rt.run(f"SIM.rawSquare({ex}, {ey}, 0).worldObjects = {{}}")
    tick_missions(rt)
    check(m("placed") is False,
          "ensign edges: the figure vanished and the mission still thinks it "
          "is on the ground")
    tick_missions(rt)
    check(m("placed") is True and figures(rt, int(m("ex")), int(m("ey"))) == 1,
          "ensign edges: a figure that went missing was not put back")
    rt.run("SIM.log = {}")

    # --- the clock runs out while nobody is near ----------------------------------
    ex, ey = int(m("ex")), int(m("ey"))
    mid = str(m("id"))
    walk_to(rt, 2000.5, 2000.5)
    rt.run("SIM.advanceHours(TREK.Config.EnsignLifeHours + 1)")
    check(rt.eval(f"TREK.Util.chunkLoaded({ex}, {ey}, 0)") is False,
          "ensign edges: the ground is still loaded, so this cannot test a "
          "clock that runs with nobody near")
    tick_missions(rt)
    net.pump(4)
    check(str(rt.eval(f'TREK.Probes.byId("{mid}").status')) == "expired",
          "ensign edges: the deadline passed with nobody near and the mission "
          "is still live -- a clock that only runs nearby is not a clock")
    check(any("IGUI_TREK_EnsignLostNote" in n for n in rt.notes()),
          "ensign edges: the ensign was lost and nobody was told")
    check(int(rt.eval("#TREK.Probes.store().ensignRemovals")) == 1,
          "ensign edges: the figure is on unloaded ground and nothing wrote "
          "down that it has to be taken away")
    check(figures(rt, ex, ey) == 1,
          "ensign edges: a figure was removed from ground that was not loaded")
    walk_to(rt, ex + 2.5, ey + 0.5)
    tick_missions(rt)
    check(figures(rt, ex, ey) == 0,
          "ensign edges: walking back did not clear the figure of a lost mission")
    check(int(rt.eval("#TREK.Probes.store().ensignRemovals")) == 0,
          "ensign edges: the removal was done and never struck off the list")
    rt.run("SIM.log = {}")

    # --- nowhere to sit ------------------------------------------------------------
    walk_to(rt, 2000.5, 2000.5)
    accept_call(rt, net, P, 3000, 3000)
    rt.run("""
        local r = TREK.Config.EnsignPlaceRadius
        for dx = -r, r do for dy = -r, r do
            SIM.rawSquare(3000 + dx, 3000 + dy, 0).solid = true
        end end
    """)
    mid = str(m("id"))
    walk_to(rt, 3000.5, 3000.5)
    tick_missions(rt)
    net.pump(4)
    check(str(rt.eval(f'TREK.Probes.byId("{mid}").status')) == "invalid",
          "ensign edges: a rescue with no ground anywhere near was not retired")
    check(any("no ground within" in w for w in rt.warnings()),
          "ensign edges: a rescue was retired without saying why")
    check(any("IGUI_TREK_EnsignSignalLostNote" in n for n in rt.notes()),
          "ensign edges: the crew were not told the signal broke up")
    rt.run("SIM.log = {}")

    # --- not in the water -----------------------------------------------------------
    walk_to(rt, 2000.5, 2000.5)
    accept_call(rt, net, P, 3200, 3200)
    rt.run("""
        for dx = -3, 3 do for dy = -3, 3 do
            SIM.rawSquare(3200 + dx, 3200 + dy, 0).water = true
        end end
    """)
    walk_to(rt, 3200.5, 3200.5)
    tick_missions(rt)
    wx, wy = m("ex"), m("ey")
    check(wx is not None, "ensign edges: nothing was placed beside a pond")
    if wx is not None:
        check(not (3197 <= int(wx) <= 3203 and 3197 <= int(wy) <= 3203),
              f"ensign edges: the figure was put down at {wx},{wy}, in the water")
    rt.run(f'TREK.Probes.byId("{m("id")}").status = "completed"')

    # --- not inside somebody's safehouse -----------------------------------------
    walk_to(rt, 2000.5, 2000.5)
    accept_call(rt, net, P, 3400, 3400)
    rt.run("SIM.safehouse(3395, 3395, 3405, 3405, { 'someone' })")
    walk_to(rt, 3400.5, 3400.5)
    tick_missions(rt)
    sx, sy = m("ex"), m("ey")
    check(sx is not None, "ensign edges: nothing was placed near a safehouse at all")
    if sx is not None:
        inside = 3395 <= int(sx) <= 3405 and 3395 <= int(sy) <= 3405
        check(not inside,
              f"ensign edges: the figure was put down at {sx},{sy}, inside "
              f"somebody's safehouse")

    # --- a mission lost before anyone went: nothing to take away ----------------------
    rt.run("SIM.safehouses = {}")
    mid = str(m("id"))
    rt.run(f'TREK.Probes.byId("{mid}").status = "completed"')
    walk_to(rt, 2000.5, 2000.5)
    accept_call(rt, net, P, 3800, 3800)
    rt.run("SIM.advanceHours(TREK.Config.EnsignLifeHours + 1)")
    tick_missions(rt)
    check(int(rt.eval("#TREK.Probes.store().ensignRemovals")) == 0,
          "ensign edges: a mission that was never placed queued a removal")

    for w in rt.warnings():
        fail(f"ensign edges: {w}")

    print("ensign edges: a figure carried off is put back, the clock runs out "
          "with nobody near and the figure is taken away when its ground "
          "loads, no ground retires the rescue with a reason, a safehouse is "
          "avoided, and a mission never placed leaves nothing to clear")


def ensign_multiplayer():
    """Two clients: one call, one mission, one figure, one rescue, one reward."""
    net = Net("mp", clients=("owner", "crew"))
    srv = net.server
    owner, crew = net.clients["owner"], net.clients["crew"]
    srv.run("SIM.player('owner', 2000.5, 2000.5, 0); "
            "SIM.player('crew', 2000.5, 2000.5, 0)")
    owner.run("SIM.player('owner', 2000.5, 2000.5, 0)")
    crew.run("SIM.player('crew', 2000.5, 2000.5, 0)")
    net.start()
    P = "SIM.players[1]"

    owner.run(f"TREK.Transport.beamUp({P})")
    crew.run(f"TREK.Transport.beamUp({P})")
    net.pump(210)
    if died(owner, "ensign mp, beaming up") or died(crew, "ensign mp, beaming up"):
        return

    # --- the server knows where a player standing in the cabin came from ---
    # The return point is player mod data the *client* writes, and a server
    # never sees that write. Before the move handler recorded it on the
    # server's own copy, a probe launched aboard on a dedicated server was
    # refused for want of a position fix, and a distress call had nowhere to
    # be measured from. Single player could never show it: there the two
    # copies of the player are one.
    fix = srv.eval("""(function()
        for _, p in ipairs(SIM.players) do
            if p.name == "owner" then
                local x, y = TREK.Ship.worldOrigin(p)
                return x and (x .. "," .. y) or false
            end
        end
    end)()""")
    check(fix == "2000,2000",
          f"ensign mp: the server places a player standing aboard at {fix}, "
          f"not where they beamed up from (2000,2000)")
    owner.run(f'TREK.Core.send({P}, "buildProbe", {{}})')
    net.pump(6)
    owner.run(f'TREK.Core.send({P}, "launchProbe", {{}})')
    net.pump(6)
    check(srv.eval("TREK.Probes.active() ~= nil") is True,
          "ensign mp: a probe launched aboard on a server did not fly")
    check(not any("IGUI_TREK_ProbeNoFix" in n for n in owner.notes()),
          "ensign mp: a probe launched aboard on a server was refused for "
          "want of a position fix")
    srv.run("TREK.Probes.store().active = nil; TREK.Probes.publish()")

    call = make_call(srv, net)
    net.pump(10)
    for name, rt in (("owner", owner), ("crew", crew)):
        check(any("IGUI_TREK_DistressNote" in n for n in rt.notes()),
              f"ensign mp: the {name} never heard the call")
        check(rt.eval("TREK.Probes.distress() ~= nil") is True,
              f"ensign mp: the call never reached the {name}'s console")

    # Both answer at once. One mission, and the loser is told why.
    owner.run(f'TREK.Core.send({P}, "distressAnswer", {{ id = "{call}", accept = true }})')
    crew.run(f'TREK.Core.send({P}, "distressAnswer", {{ id = "{call}", accept = true }})')
    net.pump(10)
    n = ensign_missions(srv)
    check(n == 1, f"ensign mp: two crew accepting at once made {n} missions")
    check(any("IGUI_TREK_DistressGone" in x for x in crew.notes() + owner.notes()),
          "ensign mp: the second answer to one call was not refused")
    for name, rt in (("owner", owner), ("crew", crew)):
        check(rt.eval("TREK.Probes.mission() ~= nil") is True,
              f"ensign mp: the {name} client never learned about the rescue")

    srv.run("local m = TREK.Probes.mission(); m.tx, m.ty = 2600, 2600")
    # The owner walks there, and the server's copy follows; both stream in.
    walk_to(owner, 2612.5, 2600.5)
    srv.run("""
        for _, p in ipairs(SIM.players) do
            if p.name == "owner" then
                p.x, p.y, p.z, p.lastZ = 2612.5, 2600.5, 0, 0
                p.streamX, p.streamY = 2612.5, 2600.5
            end
        end
    """)
    net.pump(10)
    srv.run("SIM.fire('EveryOneMinute')")
    net.pump(10)
    if srv.eval("TREK.Probes.mission() and TREK.Probes.mission().placed") is not True:
        fail("ensign mp: the server never placed the figure")
        return
    ex = int(srv.eval("TREK.Probes.mission().ex"))
    ey = int(srv.eval("TREK.Probes.mission().ey"))
    for name, rt in (("owner", owner), ("crew", crew)):
        check(figures(rt, ex, ey) == 1,
              f"ensign mp: the {name}'s machine shows {figures(rt, ex, ey)} "
              f"figures where the ensign sits")
        check(rt.eval("TREK.Probes.mission().ex") == ex,
              f"ensign mp: the {name}'s store does not know where the ensign "
              f"is, so its menu and its tricorder cannot find the figure")

    # The owner's menu finds the ensign, from the owner's own store.
    walk_to(owner, ex + 1.5, ey + 0.5)
    srv.run(f"""
        for _, p in ipairs(SIM.players) do
            if p.name == "owner" then p.x, p.y = {ex + 1.5}, {ey + 0.5} end
        end
    """)
    labels = ensign_menu(owner, ex, ey)
    check("IGUI_TREK_EnsignRescue" in labels,
          f"ensign mp: the owner's right-click on the ensign offered {labels!r}")

    # The crew, still aboard and nowhere near, asks at the same moment:
    # refused by distance, measured on the server.
    mid = str(srv.eval("TREK.Probes.mission().id"))
    owner.run(f'TREK.Core.send({P}, "rescueEnsign", {{ id = "{mid}" }})')
    crew.run(f'TREK.Core.send({P}, "rescueEnsign", {{ id = "{mid}" }})')
    net.pump(10)
    check(str(srv.eval(f'TREK.Probes.byId("{mid}").status')) == "completed",
          "ensign mp: the owner beside the ensign could not beam them up")
    for name, rt in (("owner", owner), ("crew", crew)):
        check(figures(rt, ex, ey) == 0,
              f"ensign mp: the figure is still sitting there on the {name}'s "
              f"machine")
        check(any("IGUI_TREK_EnsignRescuedNote" in x for x in rt.notes()),
              f"ensign mp: the {name} was never told the ensign is safe")
    check(inventory_count(crew, "TrekShuttle.TrekRationPack") == 0,
          "ensign mp: the crew member who was nowhere near got the supply")
    check(inventory_count(owner, "TrekShuttle.TrekRationPack") >= 2,
          "ensign mp: the rescuer's supply never reached their own machine")
    check(int(owner.eval("TREK.Replicator.patternCount()"))
          == int(srv.eval("TREK.Replicator.patternCount()")),
          "ensign mp: the patterns the rescue taught never reached the client")

    for name, rt in (("owner", owner), ("crew", crew)):
        check(int(rt.eval("SIM.clientWorldEdit or 0")) == 0,
              f"ensign mp: the {name}'s client edited the world itself")

    for name, rt in (("server", srv), ("owner", owner), ("crew", crew)):
        for w in rt.warnings():
            fail(f"ensign mp ({name}): {w}")

    print("ensign multiplayer: both crew hear one call, racing answers make "
          "one mission, the server places one figure both machines see, the "
          "rescuer's own menu finds it, a rescue is measured on the server, "
          "and the figure, the news, the patterns and the supply all reach "
          "exactly who they should")



# ---------------------------------------------------------------------------
# The PADD (PADD.md)
# ---------------------------------------------------------------------------
def give(rt, who, full, item_id, title=None):
    """Puts an item with a fixed id in a player's pockets on this runtime.

    Fixed, because an item sent over the network is resolved by id: a PADD
    in the owner's pockets on the server and on the owner's client has to be
    the same PADD, as it is in the engine."""
    md = f'it.modData.literatureTitle = "{title}"' if title else ""
    rt.run(f"""
        local it = instanceItem("{full}")
        it.id = {item_id}
        {md}
        for _, p in ipairs(SIM.players) do
            if p.name == "{who}" then p.inventory:AddItem(it) end
        end
    """)


def shelf(rt, x, y, z, items):
    """A container on the floor holding books, the way a school's shelf is:
    reached through the loot panel, never picked up."""
    rows = []
    for full, item_id, title in items:
        md = f'it.modData.literatureTitle = "{title}"' if title else ""
        rows.append(f"""
            do local it = instanceItem("{full}"); it.id = {item_id}; {md}
               o.container:AddItem(it) end""")
    rt.run(f"""
        local sq = SIM.rawSquare({x}, {y}, {z})
        local o = SIM.object("furniture_shelving_01_28")
        o.square = sq
        o.container = SIM.container(40)
        o.container.parentObject = o
        {''.join(rows)}
        table.insert(sq.objects, o)
    """)


def padd_menu(rt, item_ids):
    """Right-clicks these items in an inventory pane; returns every label."""
    ids = ", ".join(str(i) for i in item_ids)
    rt.run(f"""
        local list = {{}}
        for _, id in ipairs({{ {ids} }}) do table.insert(list, SIM.findItem(id)) end
        paddCtx = SIM.contextMenu()
        TREK.PaddUI.fillInventoryMenu(0, paddCtx, list)
    """)
    return str(rt.eval("paddCtx:deepLabels()"))


def padd_click(rt, text):
    """Clicks an option anywhere in the last menu, then runs what it queued."""
    rt.run(f"""
        for _, o in ipairs(paddCtx:all()) do
            if o.name:find("{text}", 1, true) and o.fn then
                o.fn(o.target, unpack(o.args))
                break
            end
        end
        SIM.runActions()
    """)


def library(rt, item_id):
    return int(rt.eval(f"#TREK.Padd.library(SIM.findItem({item_id}))"))


def option_greyed(rt, text):
    return rt.eval(f"""(function()
        for _, o in ipairs(paddCtx:all()) do
            if o.name:find("{text}", 1, true) then return o.notAvailable == true end
        end
        return "absent"
    end)()""")


def padd():
    """Load, read, copy and erase, in single player.

    PADD.md sections 1-5: a PADD takes a digital copy of a book and leaves the
    book; reading off it gives what the book gives, applied to a book rebuilt
    in no container; a library copies and erases; and nothing that must not
    load does.
    """
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('owner', 2000.5, 2000.5, 0)")
    net.start()
    P = "SIM.players[1]"
    rt.run(f"TREK.Transport.beamUp({P})")
    net.pump(210)
    if died(rt, "padd, beaming up"):
        return

    # --- the armoury issues two -----------------------------------------------
    issued = rt.eval("""(function()
        local U = TREK.Util
        local x, y = U.at(3, 0)
        local sq = U.square(x, y, TREK.Config.CabinZ, false)
        local n = 0
        for _, o in ipairs(sq.objects) do
            if o.container then
                for _, it in ipairs(o.container.items) do
                    if it.fullType == TREK.Config.PaddItem then n = n + 1 end
                end
            end
        end
        return n
    end)()""")
    check(issued == int(rt.eval("TREK.Config.PaddIssue")),
          f"padd: the armoury holds {issued} PADDs, not "
          f"{rt.eval('TREK.Config.PaddIssue')}")

    # Out into a town, with books on a shelf beside the player.
    rt.run(f"""
        local p = {P}
        p.x, p.y, p.z, p.lastZ = 2000.5, 2000.5, 0, 0
        p.streamX, p.streamY = 2000.5, 2000.5
    """)
    shelf(rt, 2001, 2000, 0, [("Base.BookCarpentry1", 9001, None),
                              ("Base.BookCarpentry2", 9002, None),
                              ("Base.Book", 9003, "LastTrain"),
                              ("Base.Book", 9004, "SeaOfGlass"),
                              ("Base.MagazineCooking1", 9005, None),
                              ("Base.Notebook", 9006, None),
                              ("Base.Flier", 9007, None)])

    # --- no PADD, no option -----------------------------------------------------
    check("IGUI_TREK_PaddLoad" not in padd_menu(rt, [9001]),
          "padd: a book offers Load onto PADD to a player with no PADD")

    give(rt, "owner", "TrekShuttle.TrekPADD", 8001)
    check("IGUI_TREK_PaddLoad" in padd_menu(rt, [9001]),
          "padd: a skill book on a shelf offers no Load with a PADD in hand")
    check("IGUI_TREK_PaddLoad" not in padd_menu(rt, [9006]),
          "padd: a writable notebook offers Load; what a player wrote is theirs")
    check("IGUI_TREK_PaddLoad" not in padd_menu(rt, [9007]),
          "padd: a flier used up when read offers Load")

    # --- loading copies, and leaves the book ---------------------------------------
    padd_menu(rt, [9001])
    padd_click(rt, "IGUI_TREK_PaddLoad")
    check(library(rt, 8001) == 1, "padd: loading a book put nothing on the PADD")
    check(rt.eval("SIM.findItem(9001) ~= nil and SIM.findItem(9001).container ~= nil")
          is True, "padd: loading took the book off the shelf; a PADD copies")
    check(any("IGUI_TREK_PaddLoaded" in n for n in rt.notes()),
          "padd: a book was loaded without a word")
    padd_menu(rt, [9001])
    check(option_greyed(rt, "IGUI_TREK_PaddLoad") is True,
          "padd: a book already on the PADD is offered again, not greyed")

    # --- two novels are two books; the same novel twice is one -----------------
    padd_menu(rt, [9003, 9004, 9005])
    check("IGUI_TREK_PaddLoadMany|3" in str(rt.eval("paddCtx:deepLabels()")),
          "padd: selecting three books did not offer to load all three")
    padd_click(rt, "IGUI_TREK_PaddLoadMany")
    check(library(rt, 8001) == 4,
          f"padd: the library holds {library(rt, 8001)} after four different "
          f"books; two copies of Base.Book with different titles are two books")
    shelf(rt, 2001, 2001, 0, [("Base.Book", 9008, "LastTrain")])
    padd_menu(rt, [9008])
    check(option_greyed(rt, "IGUI_TREK_PaddLoad") is True,
          "padd: a second copy of the same novel is offered as a new book")

    # --- out of reach ------------------------------------------------------------------
    shelf(rt, 2012, 2000, 0, [("Base.BookCarpentry2", 9010, None)])
    rt.run("""
        local p, padd, book = SIM.players[1], SIM.findItem(8001), SIM.findItem(9010)
        ISTimedActionQueue.add(TREKLoadPadd:new(p, padd, book))
        SIM.runActions()
    """)
    check(library(rt, 8001) == 4,
          "padd: a book ten squares away was loaded")

    # --- the read menu --------------------------------------------------------------
    labels = padd_menu(rt, [8001])
    for key in ("IGUI_TREK_PaddRead|4", "IGUI_TREK_PaddSkillBooks",
                "IGUI_TREK_PaddRecipes", "IGUI_TREK_PaddLiterature",
                "IGUI_TREK_PaddCopy", "IGUI_TREK_PaddErase"):
        check(key in labels, f"padd: the PADD's menu has no {key}: {labels!r}")

    # --- reading a skill book --------------------------------------------------------
    ticks = int(rt.eval("""TREK.Padd.readTicks(SIM.players[1],
        TREK.Padd.library(SIM.findItem(8001))[1])"""))
    # 220 pages * 2 minutes per page / (1 / 60 / 2), over five.
    want = int(220 * 2.0 / (1 / 60 / 2) / 5)
    check(abs(ticks - want) <= 1,
          f"padd: a 220-page book takes {ticks} ticks off a PADD, not {want} "
          f"-- a fifth of what ISReadABook would take")
    rt.run("SIM.players[1].traits = { FAST_READER = true }")
    fast = int(rt.eval("""TREK.Padd.readTicks(SIM.players[1],
        TREK.Padd.library(SIM.findItem(8001))[1])"""))
    check(abs(fast - int(want * 0.7)) <= 1,
          f"padd: a Fast Reader takes {fast} ticks, not {int(want * 0.7)}; the "
          f"vanilla traits apply before the PADD's speed")
    rt.run("SIM.players[1].traits = nil")

    padd_menu(rt, [8001])
    padd_click(rt, "Carpentry for Beginners")
    xp = rt.eval("SIM.xp[#SIM.xp]")
    check(xp is not None and str(xp.perk.name) == "Carpentry" and int(xp.mult) == 3
          and int(xp.lvl) == 1 and int(xp.maxLvl) == 2,
          "padd: reading Carpentry Vol. 1 off the PADD gave no skill multiplier, "
          "or the wrong one")
    check(int(rt.eval('SIM.players[1]:getAlreadyReadPages("Base.BookCarpentry1")')) == 220,
          "padd: a finished book is not recorded as read to the last page")
    check(int(rt.eval("#SIM.literatureRead")) == 0,
          "padd: a skill book was read as literature too")

    # The read list ticks what this character has finished, with the mark
    # vanilla's inventory uses -- and only that.
    padd_menu(rt, [8001])
    ticks_on = rt.eval("""(function()
        local out = {}
        for _, o in ipairs(paddCtx:all()) do
            if o.iconTexture then out[o.name] = o.iconTexture.path end
        end
        return out
    end)()""")
    check(ticks_on["Carpentry for Beginners"] == "media/ui/Tick_Mark-10.png",
          "padd: a finished book has no tick in the PADD's read list")
    check("Good Cooking Magazine" not in ticks_on,
          "padd: a book nobody has read is ticked in the PADD's read list")
    check(rt.eval("SIM.syncedFields[#SIM.syncedFields].mask") == 7,
          "padd: the player's recipes, traits and books were never synced")

    # Too advanced: greyed with a reason, and refused if forced.
    padd_menu(rt, [8001])
    shelf(rt, 2000, 2001, 0, [("Base.BookCarpentry2", 9011, None)])
    rt.run("""
        local padd, book = SIM.findItem(8001), SIM.findItem(9011)
        TREK.Padd.add(padd, TREK.Padd.entryOf(book))
    """)
    padd_menu(rt, [8001])
    check(option_greyed(rt, "Carpentry for Intermediates") is True,
          "padd: a Vol. 2 for a character with no carpentry is not greyed")
    n = int(rt.eval("#SIM.xp"))
    padd_click(rt, "Carpentry for Intermediates")
    check(int(rt.eval("#SIM.xp")) == n,
          "padd: a book too advanced for the reader gave a multiplier anyway")

    # --- reading literature ----------------------------------------------------------
    padd_menu(rt, [8001])
    key = rt.eval("""(function()
        for _, e in ipairs(TREK.Padd.library(SIM.findItem(8001))) do
            if e.md and e.md.literatureTitle == "LastTrain" then
                return TREK.Padd.key(e)
            end
        end
    end)()""")
    rt.run(f"""
        ISTimedActionQueue.add(TREKReadPadd:new(SIM.players[1], SIM.findItem(8001), "{key}"))
        SIM.runActions()
    """)
    read = rt.eval("SIM.literatureRead[1]")
    check(read is not None and str(read.title) == "LastTrain",
          "padd: reading a novel off the PADD did not read it")
    check(read is not None and read.inContainer is False,
          "padd: the book rebuilt for reading was put in a container -- that "
          "is a real, droppable copy of the book")
    check(rt.eval('SIM.players[1]:isLiteratureRead("LastTrain")') is True,
          "padd: the novel's title was not ticked off")
    rt.run(f"""
        ISTimedActionQueue.add(TREKReadPadd:new(SIM.players[1], SIM.findItem(8001), "{key}"))
        SIM.runActions()
    """)
    check(int(rt.eval("#SIM.literatureRead")) == 1,
          "padd: reading the same novel twice comforted twice; vanilla does "
          "not, and a PADD must not")

    # A recipe magazine: recorded as read, which is what recipes key on.
    padd_menu(rt, [8001])
    padd_click(rt, "Good Cooking Magazine")
    check(rt.eval('SIM.players[1].booksRead and '
                  'SIM.players[1].booksRead["Base.MagazineCooking1"]') is True,
          "padd: a recipe magazine read off the PADD was not recorded as read")

    # --- copying ------------------------------------------------------------------
    labels = padd_menu(rt, [8001])
    check(option_greyed(rt, "IGUI_TREK_PaddCopy") is True,
          "padd: Copy is live with only one PADD")
    give(rt, "owner", "TrekShuttle.TrekPADD", 8002)
    padd_menu(rt, [8001])
    padd_click(rt, "IGUI_TREK_PaddCopyTo")
    check(library(rt, 8002) == library(rt, 8001),
          f"padd: the copy holds {library(rt, 8002)} of "
          f"{library(rt, 8001)} titles")
    before = library(rt, 8002)
    padd_menu(rt, [8001])
    padd_click(rt, "IGUI_TREK_PaddCopyTo")
    check(library(rt, 8002) == before,
          "padd: copying the same library twice duplicated its titles")

    # --- erasing ------------------------------------------------------------------
    padd_menu(rt, [8002])
    padd_click(rt, "IGUI_TREK_PaddEraseConfirm")
    check(library(rt, 8002) == 0, "padd: erasing left titles on the PADD")
    check(library(rt, 8001) == before,
          "padd: erasing one PADD touched the other")

    # --- a replicated PADD is blank ------------------------------------------------
    check(rt.eval('#TREK.Padd.library(instanceItem("TrekShuttle.TrekPADD"))') == 0,
          "padd: a new PADD is not blank")

    for w in rt.warnings():
        fail(f"padd: {w}")

    print("padd: the armoury issues two; a book loads as a copy and stays on "
          "its shelf, only once, only within reach, and never a notebook or "
          "a single-use flier; two novels are two books; reading gives the "
          "skill multiplier at a fifth of the time, refuses a book too "
          "advanced, comforts once per title from a book in no container, and "
          "records a recipe magazine; a library copies without duplicates and "
          "erases alone")


def padd_multiplayer():
    """Two clients: the server writes the library and the reader's machine
    gets it; reading happens on the server, with the comfort on the client."""
    net = Net("mp", clients=("owner", "crew"))
    srv = net.server
    owner, crew = net.clients["owner"], net.clients["crew"]
    srv.run("SIM.player('owner', 2000.5, 2000.5, 0); "
            "SIM.player('crew', 2003.5, 2000.5, 0)")
    owner.run("SIM.player('owner', 2000.5, 2000.5, 0)")
    crew.run("SIM.player('crew', 2003.5, 2000.5, 0)")
    net.start()
    P = "SIM.players[1]"

    for rt in (srv, owner):
        give(rt, "owner", "TrekShuttle.TrekPADD", 8101)
    for rt in (srv, owner, crew):
        shelf(rt, 2001, 2000, 0, [("Base.BookCarpentry1", 9101, None),
                                  ("Base.Book", 9102, "LastTrain")])
    net.pump(4)

    # --- loading: the client asks, the server writes, the owner hears ------------
    padd_menu(owner, [9101])
    padd_click(owner, "IGUI_TREK_PaddLoad")
    net.pump(4)
    check("TREKLoadPadd" in [str(x) for x in srv.eval("SIM.actionsDone").values()],
          "padd mp: the server never ran the load -- a mod timed action has to "
          "be rebuilt there by its class name")
    check(library(srv, 8101) == 1,
          "padd mp: the server's PADD holds nothing after a load")
    check(library(owner, 8101) == 1,
          "padd mp: the owner's own PADD shows nothing after a load; the "
          "server wrote it and never synced it")

    padd_menu(owner, [9102])
    padd_click(owner, "IGUI_TREK_PaddLoad")
    net.pump(4)
    check(library(owner, 8101) == 2, "padd mp: the second load never reached the owner")

    # A client is not an author.
    owner.run("""
        TREK.Padd.add(SIM.findItem(8101), { type = "Base.Forged", name = "x" })
    """)
    check(library(owner, 8101) == 2,
          "padd mp: a client wrote its own PADD's library")

    # --- reading: the effects are the server's; the comfort is on both ----------
    padd_menu(owner, [8101])
    padd_click(owner, "Carpentry for Beginners")
    net.pump(4)
    check(int(srv.eval("#SIM.xp")) == 1,
          "padd mp: the skill multiplier never landed on the server")
    check(int(owner.eval("#SIM.xp")) == 0,
          "padd mp: the client applied the multiplier itself; complete() "
          "never runs on a client")

    key = owner.eval("""(function()
        for _, e in ipairs(TREK.Padd.library(SIM.findItem(8101))) do
            if e.md and e.md.literatureTitle == "LastTrain" then
                return TREK.Padd.key(e)
            end
        end
    end)()""")
    owner.run(f"""
        ISTimedActionQueue.add(TREKReadPadd:new(SIM.players[1], SIM.findItem(8101), "{key}"))
        SIM.runActions()
    """)
    net.pump(4)
    check(int(srv.eval("#SIM.literatureRead")) == 1,
          "padd mp: the novel's comfort never landed on the server")
    check(int(owner.eval("#SIM.literatureRead")) == 1,
          "padd mp: the novel's comfort never landed on the reader's own "
          "client, where vanilla applies it too")
    check(int(crew.eval("#SIM.literatureRead")) == 0,
          "padd mp: somebody else's client read the owner's novel")

    for name, rt in (("owner", owner), ("crew", crew)):
        check(int(rt.eval("SIM.clientWorldEdit or 0")) == 0,
              f"padd mp: the {name}'s client edited the world")
    for name, rt in (("server", srv), ("owner", owner), ("crew", crew)):
        for w in rt.warnings():
            fail(f"padd mp ({name}): {w}")

    print("padd multiplayer: a load is rebuilt and completed on the server "
          "and the library reaches the owner's machine; a client cannot write "
          "one; reading applies the multiplier on the server only, and a "
          "novel's comfort on the server and the reader's client and nowhere "
          "else")



def seat_exit():
    """Leaving a seat for the cabin leaves it the way vanilla's exit does.

    Every session log from 2026-09-23 on has one NullPointerException in
    vanilla's loot panel on the first frame aboard after leaving the shuttle's
    seat: the panel was still showing the seat's container, the move into the
    cabin unloaded the shuttle, and the panel asked a seat whose vehicle was
    gone. Vanilla's ISExitVehicle fires OnExitVehicle and the panel is rebuilt
    while the vehicle still exists; the mod's own exits did neither.
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

    # --- beaming up from the pilot's seat --------------------------------
    rt.run("SIM.inventoryRefreshes = 0; SIM.triggered = {}")
    rt.run(f"TREK.Transport.beamUp({P})")
    net.pump(200)
    check(rt.eval(f"{P}.vehicle") is None,
          "seat exit: beaming up left the pilot in the seat")
    check(int(rt.eval("SIM.inventoryRefreshes")) >= 1,
          "seat exit: beaming up out of a seat did not rebuild the loot "
          "panel, which is still showing the seat when the shuttle unloads")
    check("OnExitVehicle" in [str(x) for x in rt.eval("SIM.triggered").values()],
          "seat exit: beaming up out of a seat never fired OnExitVehicle, "
          "which vanilla's own exit does")

    # --- aft to the cabin in flight -----------------------------------------
    rt.run(f"""
        local p = {P}
        p.x, p.y, p.z, p.lastZ = 3004.5, 3006.5, 0, 0
        p.streamX, p.streamY = p.x, p.y
    """)
    net.pump(40)
    seat(rt)
    rt.run(f"TREK.Flight.takeOff({P})")
    net.pump(400)
    if ship(rt, "flying") is not True:
        fail("seat exit: she never got up, so the trip aft cannot be tested")
        return
    rt.run("SIM.inventoryRefreshes = 0; SIM.triggered = {}")
    rt.run(f"TREK.VehicleMenu.onBoardFromSeat({P})")
    net.pump(10)
    check(rt.eval(f"{P}.vehicle") is None,
          "seat exit: going aft in flight left the pilot in the seat")
    check(int(rt.eval("SIM.inventoryRefreshes")) >= 1,
          "seat exit: going aft in flight did not rebuild the loot panel -- "
          "exactly the move in the 2026-09-23 log")
    check("OnExitVehicle" in [str(x) for x in rt.eval("SIM.triggered").values()],
          "seat exit: going aft in flight never fired OnExitVehicle")

    # --- up the ramp from beside her -------------------------------------
    # The 2026-09-24 play-test: set her down, step out, walk up the ramp --
    # and the same NullPointerException, through the hatch. Beside her the
    # loot panel lists her seats; a rebuild made there puts them straight
    # back; the move into the cabin unloads her. Only a rebuild made *after*
    # the move clears her out of it.
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('pilot', 3000.5, 3000.5, 0)")
    net.start()
    net.pump(5)
    rt.run(f"TREK.Menu.onCallDown(nil, {P}, 3004, 3000, 0)")
    net.pump(40)
    rt.run(f"""
        local p = {P}
        local s = TREK.Util.state()
        p.x, p.y, p.z, p.lastZ = s.x + 1.5, s.y + 3.5, 0, 0
        ISInventoryPage.dirtyUI()
    """)
    check(rt.eval("SIM.loot[0].inventory ~= SIM.floorContainer"),
          "seat exit: standing beside her, the simulated loot panel does not "
          "list her seats, so the check below proves nothing")
    rt.run(f"TREK.Core.enter({P})")
    net.pump(1)
    check(rt.eval("SIM.lootStale()") is False,
          "seat exit: up the ramp and into the cabin with the loot panel still "
          "holding the shuttle's seat -- the NullPointerException on the first "
          "frame aboard")

    for w in rt.warnings():
        fail(f"seat exit: {w}")
    print("seat exit: beaming up, going aft and walking up the ramp all leave "
          "the loot panel rebuilt from the cabin, not from beside the shuttle")



def hover_call_down():
    """Beam down beside a hovering shuttle, and call her down somewhere new.

    Found in play, 2026-09-24: "Not while the shuttle is in the air". The
    ship's test for whether anybody is aboard asked `getSeat(p) ~= nil`, and
    the engine answers -1 -- not nil -- for somebody who is not in the
    vehicle, so every living player near her counted as her crew. The
    simulation answered nil, so nothing here could see it.
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
    rt.run(f"TREK.Flight.takeOff({P})")
    net.pump(400)
    if ship(rt, "flying") is not True:
        fail("hover call-down: she never got up")
        return

    # Down on the transporter, a few squares from her -- close enough that
    # her vehicle is loaded and the seat test is really asked.
    sx, sy = ship(rt, "x"), ship(rt, "y")
    rt.run(f"TREK.Transport.beamDown({P}, {{ x = {sx} + 10, y = {sy}, z = 0 }})")
    net.pump(300)
    check(rt.eval(f"{P}.vehicle") is None,
          "hover call-down: the pilot is still in the seat after beaming down")
    check(rt.eval("TREK.Vehicle.ship() ~= nil") is True,
          "hover call-down: her vehicle is not loaded beside the crew, so the "
          "seat test this exists for is never asked")

    rt.run("SIM.notes = {}")
    px = int(rt.eval(f"math.floor({P}.x)"))
    py = int(rt.eval(f"math.floor({P}.y)"))
    rt.run(f"TREK.Menu.onCallDown(nil, {P}, {px} + 2, {py} + 6, 0)")
    net.pump(60)
    check(not any("IGUI_TREK_InFlight" in n for n in rt.notes()),
          "hover call-down: calling her down after beaming off her was "
          "refused as 'Not while the shuttle is in the air'")
    check(ship(rt, "landed") is True and ship(rt, "flying") is None,
          "hover call-down: she did not come down where she was called")

    for w in rt.warnings():
        fail(f"hover call-down: {w}")
    print("hover call-down: a crew who beam down beside a hovering shuttle are "
          "not her crew any more, and can call her down somewhere new")



def ground_cockpit():
    """Forward to the cockpit from the cabin with her on the ground.

    Asked for in play, 2026-09-24: in flight the cabin goes straight to the
    seats, on the ground it did not. The trip arrives beside her -- where the
    hatch puts people -- not under her, because on the ground that square is
    her hull.
    """
    P = "SIM.players[1]"
    net = Net("sp")
    rt = net.server
    rt.run("SIM.player('pilot', 3000.5, 3000.5, 0)")
    net.start()
    net.pump(5)
    rt.run(f"TREK.Menu.onCallDown(nil, {P}, 3004, 3000, 0)")
    net.pump(40)
    check(ship(rt, "landed") is True, "ground cockpit: she never landed")
    rt.run(f"TREK.Transport.beamUp({P})")
    net.pump(210)
    if died(rt, "ground cockpit, beaming up"):
        return
    check(rt.eval(f"TREK.Util.isInteriorPlayer({P})") is True,
          "ground cockpit: the pilot never got aboard")

    labels = aboard_menu(rt)
    check("IGUI_TREK_ToCockpit" in labels,
          f"ground cockpit: the aboard menu has no way forward to the cockpit "
          f"with her on the ground: {labels!r}")
    rt.run('aboardCtx:deepClick("IGUI_TREK_ToCockpit")')
    net.pump(400)
    check(rt.eval(f"{P}.vehicle ~= nil") is True,
          "ground cockpit: the trip forward did not put the pilot in a seat")
    check(ship(rt, "landed") is True and ship(rt, "flying") is None,
          "ground cockpit: going forward on the ground moved or lifted her")

    # Overhead there are no seats to go to, and the option says nothing.
    rt.run(f"{P}.vehicle = nil")
    rt.run("TREK.Util.state().landed = false")
    rt.run(f"TREK.Transport.beamUp({P})")
    net.pump(210)
    check("IGUI_TREK_ToCockpit" not in aboard_menu(rt),
          "ground cockpit: the cockpit is offered with her overhead, where "
          "there is no seat anywhere near")

    for w in rt.warnings():
        fail(f"ground cockpit: {w}")
    print("ground cockpit: with her on the ground the cabin goes straight to a "
          "seat, arriving beside her rather than inside her hull, and the "
          "option is not offered while she is overhead")


SECTIONS = (static, migration, single_player, refit, flight, flight_ascent,
            flight_refused, flight_two_machines, flight_alone,
            flight_endings, seat_exit, hover_call_down, ground_cockpit,
            torpedoes, medical, medical_multiplayer, replicator,
            replicator_multiplayer, emh, emh_multiplayer, contacts,
            contact_map, contacts_multiplayer, probes, contact_world,
            contact_reveal, distress, ensign_world, ensign_edges,
            ensign_multiplayer, padd, padd_multiplayer, tapes, multiplayer)


def main():
    # A later section that reads what an earlier one was supposed to produce
    # throws rather than fails: torpedoes() compares two positions that are
    # both None when the ship never got off the ground. Everything already
    # found is printed either way, because a traceback on top of a silent list
    # of failures is how a real regression gets read as a broken harness.
    try:
        for section in SECTIONS:
            section()
    finally:
        if failures:
            print(f"\n{len(failures)} PROBLEM(S):")
            for f in dict.fromkeys(failures):
                print("  " + f)
    if failures:
        sys.exit(1)
    print("\nsingle player and multiplayer behave as designed")


main()
