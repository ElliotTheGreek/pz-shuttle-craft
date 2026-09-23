# Piloting the shuttle

How flight works, why it has to work that way, and what to know before
changing it.

`DEV_GUIDE.md` is how to work on the mod at all. `MULTIPLAYER.md` is the
client/server design this obeys. `ROADMAP.md` is what comes next. This file is
the flight system: read it before touching `TREK_Sky.lua`, `TREK_Flight.lua`,
or anything in the server that mentions `flying`.

---

## 1. What it is, from the cockpit

The landed shuttle is a vehicle with four doorless seats. Get in as you would a
car. From the driver's seat, **V** opens the radial menu:

| | |
|---|---|
| **Take her up** | She climbs to level 3, above the rooftops |
| **Climb** / **Dive** | One level at a time, between 1 and 4 |
| **Set her down below** | The existing footprint check, then down |
| **Go aboard (cabin)** | Through to the interior, on the ground or in the air |

Then you **drive**. W/A/S/D, the stick, the seat chart, the mechanics screen —
all of it is vanilla's, untouched. The helm inside sets the top speed.

---

## 2. How it works: she is driving, on a floor

**The shuttle does not hover. It drives, on an invisible floor the mod lays at
altitude.** That is not a flourish. It is the only thing build 42 permits, and
the reason is worth knowing before you try to improve it.

### Why lifting the physics body does not work

`BaseVehicle.update()` runs every tick. Disassembled, bci 1385–1537:

```java
setX(jniTransform.origin.x + WorldSimulation.instance.offsetX);
setY(jniTransform.origin.z + WorldSimulation.instance.offsetY);
setZ(0.0f);                                              // bci 1429 — UNCONDITIONAL
int lvl = PZMath.fastfloor(jniTransform.origin.y / 2.4494900703430176f + 0.05f);
IsoGridSquare sq  = getCell().getGridSquare(getX(), getY(), lvl);
IsoGridSquare sqB = getCell().getGridSquare(getX(), getY(), lvl - 1);
if (sq != null && (sq.getFloor() != null
                   || (sqB != null && sqB.getFloor() != null)))
    setZ((float) lvl);                                   // bci 1530 — only with a FLOOR
```

**A vehicle's physics height is not its game z.** Every tick the engine zeroes
z and then restores the level *only if a floor tile exists under the vehicle's
centre square*, at that level or the one below. Everything that matters reads
the clamped `getZ()`:

| Reader | With no floor under her |
|---|---|
| `ModelCameraRenderData.init` (the render camera) | she is **drawn on the ground** |
| `getPassengerPositionWorldPos` | so is the crew |
| `isIntersectingSquare`, `breakingObjects`, `damageObjects` | she **bulldozes fences and trees** she flies over |
| `VehicleManager.clientUpdateVehiclePos` | hard-writes `setZ(0)` — every **other player** sees her on the road |

The hold does not hold, either: `isAtRest()` is false more than 0.2 levels
above its own square, so `CarController.checkShouldBeActive()` re-enables
physics, every tick, from two call sites. Vanilla's own `ISVehicleAngles.lua`
re-asserts `setPhysicsActive(false, false)` *and* the height on **every frame**,
which is the authors saying neither sticks — and its only caller sits behind
`if getCore():getDebug()`, so it is `-debug`-only into the bargain.

So a Lua-driven transform gives a ship that flies in the physics engine and
sits on the road in the game: **present, drawn, and inert.**

### What a floor buys

Put one under her and it all comes right at once. The height is legitimate, so
she and her crew are drawn in the air. Collision resolves at the flight level,
so a two-storey building is passed over instead of demolished. Remote clients
re-derive the level the same way. And the wheels have something to rest on — so
**the engine drives her, and no part of this mod fights gravity.**

Build 42 ships **`invisible_01_0`**, whose only two properties are
`attachedFloor` and `solidfloor`: an invisible solid floor.

The consequence worth internalising: **flight is a place, not a manoeuvre.**
The floor holds her up whether or not anybody is flying her, which is what lets
the crew go aft to the cabin and come back, and what removes the entire class
of bug that killed the 1.1 flight, where flight outlived its pilot.

---

## 3. The pieces

```
client/TREK/TREK_Sky.lua      lays and lifts the floor; knows nothing about flying
client/TREK/TREK_Flight.lua   take-off, climb, dive, landing, and watching
server/TREK/TREK_Server.lua   who may fly, what level, and the watchdog
shared/TREK/TREK_Config.lua   every number below
```

### Who owns what

| | |
|---|---|
| **The plane** | Each client, for itself. Never synced. |
| **`flying`, `level`, `pilot`** | The server, as ship state, set by validated commands |
| **The lift between levels** | The machine that moves her: the driver's client on a server, and in single player this one (see below) |
| **Driving, steering, seats, camera, sync** | Vanilla. The mod does not touch any of it. |

**Single player owns the physics and the engine will not say so.**
`isLocalPhysicSim()` is `authorization == LocalCollide || == Local` off a
server, and a vehicle's authorization is only ever moved off its constructor
default (`Authorization.Server`) by `constraintChanged()`, whose whole body
sits behind `getstatic GameServer.server; ifeq -> return`. So it is **false in
single player for ever**, and a guard on it refused every take-off there --
silently -- for one release. `F.ownsPhysics` answers for itself when there is
no server to disagree with; vanilla does the same, consulting the method only
inside `isBrakePedalPressed`'s `GameClient.client` branch.

**Why a client lays world floor**, when `MULTIPLAYER.md` says a client never
edits the world: the plane is not the ship and it is not state, it is scenery
and local physics — the same class as the cabin's lights and powered squares,
which each client also makes for itself. The server runs **no vehicle physics
at all** in build 42 (`setPhysicsActive` and `setWorldTransform` both skip their
`Bullet` calls when `GameServer.server`), so it has no use for a floor. The
driver's client needs one to drive on and every client needs one to draw her in
the air, and all of them derive it from the same synced vehicle position — so
they agree without a packet. It is only ever this one sprite, only ever above
the ground, and always taken up again. `tests/pz_sim.lua` counts it separately
from every other client world edit so the general rule keeps its teeth.

### The protocol

`takeoff` → `takeoffGranted` → *(client paves, lifts, confirms)* → `airborne`
→ `setAltitude` → `touchdown` → `touchdownGranted`, plus `flightEnded` to all
and `skyCleared` back. The server never sets `flying` until the client reports
the engine actually held the height: a lift that failed must never leave the
state saying she is up when she is sitting on the grass.

---

## 4. Rules that exist because they were broken

Every one of these was found in the game, in one evening, and every one is
covered by a mutation-checked test. They are the reasons the code looks the way
it does.

### A floor's shadow outlives the floor

`RemoveTileObjectErosionNoRecalc` is named for what it does *not* do. The
object comes off the square and the square keeps every conclusion the engine
had already drawn from it being there — so the ground under a lifted floor goes
on being treated as ground under a floor, and stays dark.

This produced a black trail behind the ship that survived **three** rounds of
shrinking the plane, while the log insisted thousands of floors had been lifted.
They had. Only the shadow remained. Vanilla never removes an object without
following it with `RecalcProperties()` and `RecalcAllWithNeighbours(true)`
(`ISRemoveItemTool.lua:312`, `ISGrabItemAction.lua:99`), and neither may this.

`tests/pz_sim.lua` marks a square stale when something is removed without the
pair, and the test fails on any that are left. It found a second removal site
the first fix had missed.

### The plane must be small, because a floor darkens what is under it

Nothing can stop that; it is what a floor is. The only lever is how much floor
exists, so the patch is `C.SkyRadius = 2` — a 5×5 under a hull that covers 15
squares — and `C.SkyTrailMargin = 0`, so a square is lifted the moment she is
not over it. Earlier values of 16, 4 and 3, and a square of margin, each left a
visible wake.

Only the **centre square** decides the height. Everything else is there for the
wheels.

### Never lift the floor she is standing on

Changing level means two planes exist for a moment, and she is on the *old* one.
Trimming to the new target first took the floor out from under her mid-climb:
she fell, once into a building. `Sky.keep(level)` names the level she is
actually on this instant, and trim spares it.

A wrong height is also corrected the moment it is noticed, not on a slow
cadence — six ticks is a long fall, and a climb is exactly when the height is
briefly wrong by design.

### Wake her before teleporting her

A sleeping Bullet body does not reliably take a teleport. The first take-off in
game reported `physics active=false` and the height simply did not stick; the
second, with the body awake, worked at once. `F.lift` calls
`setPhysicsActive(true, true)` first — vanilla's own "Drop" call, ungated.

### Keep her level

She is a 1200kg box resting on a one-tile shelf with real physics running, and
a nudge tips her. She went over backwards in game. `flipUpright()` sets the
rotation level and leaves the origin alone, so it cannot cost height.

### Do not leave a seat that is in the air

A beam takes ninety ticks. Stepping out of a flying ship at the *start* of one
leaves the character standing on a small island of invisible floor three levels
up — and the engine draws the level you are on and culls everything below, so
the whole world goes black until they rematerialise. The seat is left in
`finishDown`, one tick before they arrive, and they arrive *beside* her:
directly underneath is where the hull stands when she is down and where her
shadow falls when she is up.

The same reasoning shuts the cabin hatch while she is up. `landed` used to mean
both "she is here" and "she is on the ground"; splitting those closed six ways
to drop a player three levels — `Core.exit`, the aboard menu, `Core.enter`,
`hatchIn`, `S.recall` and the vanilla seat exit.

### `s.z` is the ground. `s.level` is the altitude

`S.serviceVehicle` copies the vehicle's position into ship state. Letting the
flying z into `s.z` is the single most expensive thing available here: `s.z` is
what `Core.exit` steps a player out onto, what `W.hullCovers` compares against,
what the shields measure from, and what `S.land`'s "already here" check reads.

### A flying ship is not a missing ship

`serviceVehicle`'s ownership test is `(s.landed or s.flying)`. Testing only
`landed` drops the ship's own vehicle into the leftover list, and the leftover
sweep removes anything nobody is sitting in — so she was deleted out of the sky
the first time the pilot stepped aft. `MISSING_LIMIT` is likewise suspended in
flight, or a ship briefly outrunning chunk streaming clears its own id and the
next landing spawns a second shuttle.

### Flight never survives a world load

Nothing about a vehicle's physics is saved, and `U.state()` only runs its
migration block when the schema changes — so `flying` would otherwise persist
with a pilot who is not connected. `OnInitGlobalModData` clears it outright.

### Go and find the floors older flights left behind

A floor is a world object and world objects are saved. The ship's record only
remembers the flight it is on, so anything an earlier flight — or an earlier
*build* — left behind would never be removed. The tidy-up therefore does not
consult the record: it walks the ground near the player and lifts anything of
ours above the deck, once per patch of ground.

### A hook on a toggle must ask before it calls through

Not flight-specific, but it hid flight completely for a whole session: vanilla's
radial menu is a toggle, and `isReallyVisible()` is false on the press that
opens it. See `DEV_GUIDE.md`, *"A hook on a toggle must ask before it calls
through"*.

---

## 5. The numbers

All in `TREK_Config.lua`.

| | | |
|---|---|---|
| `SkyTile` | `invisible_01_0` | the only sprite the plane ever uses |
| `LevelUnits` | 2.4494900703430176 | Bullet Y per z-level, from `setDebugZ`'s own constants |
| `SkyRadius` | 2 | 5×5 patch; bigger is more shadow |
| `SkyTrailMargin` | 0 | lift the moment she is not over it |
| `SkyTilesPerTick` | 96 | sliced, like the landing search |
| `SkyCleanRadius` / `SkyCleanStride` | 32 / 20 | the hunt for older flights' litter |
| `FlightCruise` / `Min` / `Max` | 3 / 1 / 4 | the ceiling is cruise + 1 |
| `FlightSpeedSteps` | 15…120 | absolute top speeds, each distinguishable |
| `FlightLevelTolerance` | 4° | past this she is levelled off |
| `FlightPilotGrace` | 5 checks | no pilot aboard and she comes down |

Two traps in there. **Speed steps must differ from their neighbours** — they
were once multipliers capped to a common ceiling, so the top three were
identical and the control appeared dead. And **`SpeedLimit`'s unit is not
settled**: `PILOTING` once read it as 70 tiles/s, but it is a 10–150 vehicle
limiter the UI presents in km/h. The cap only applies on a server, and every
speed change logs what it asked for beside what the vehicle reports.

---

## 6. Reading the log

Nothing needs a debug console. Take-off writes a `---- flight probe ----`
block by itself, once per session:

```
Transform reachable from Lua: true
asked for level 3: engine reports z 3, physics body is at level 3.0996
  (if the body is at the level and z is 0, the floor check refused it;
   if the body is at 0 too, the teleport itself did not take)
vehicle position 10819.97,10199.08,3.00  physics active=false
  seat 0: z=3.00 falling=false
sky plane: 25 square(s) held, peak 25 of a 25-square patch, 25 laid, 0 lifted
```

**`peak` against the patch size is the one to watch** — that difference is
exactly how much shadow the pilot sees. `held` much above the patch means the
trim is not keeping up.

Read the dated `Logs/…_DebugLog.txt`, not `console.txt`: the console file is a
rolling tail and an error flood overwrites the mod's own lines, which is how a
whole session was once lost to a log that appeared empty.

**`F.land` logs every outcome, including its four early returns**, with the
reason and the blocked-square count. They used to be silent, and during the
829-exception session the log showed no attempt and no refusal at all between
going airborne and the pilot beaming out — which is indistinguishable from the
landing never having been called, a failure this mod has had before. Silence is
not a diagnosis; make every path say something.

`TREK_Fly()` and `TREK_Sky()` exist for the console, but nothing depends on
them.

---

## 7. What is still unproven

- **Multiplayer.** None of this has been flown with two people. The wire format
  carries height (`VehiclePhysicsPacket` sends x, y, z and the server relays it
  without validation), and remote clients should re-derive the level from their
  own copy of the plane — but that is reasoning, not evidence.
- **`setWorldTransform` has no vanilla Lua call site.** It is public, ungated,
  and on the engine's Lua exposure allow-list, and it demonstrably works in
  game — but it does not meet the three-way bar `MULTIPLAYER.md` sets, and the
  probe reads the result back every time for that reason.
- **The one-square rim.** A floor darkens what is beneath it. The patch is small
  enough that the hull covers nearly all of it; whether anything shows at the
  edge is a matter of taste and camera angle. If it ever needs to go entirely,
  the untried idea is a floor sprite without `solidfloor`.
- **Speed against the anti-cheat on a real server**, and what `SpeedLimit`
  actually means.

---

## 8. If you change something here

1. `python tests/test_multiplayer.py` — the flight scenarios are in `flight()`
   and `flight_endings()`.
2. **Break it on purpose and confirm the test fails.** Every guard in section 4
   was mutation-checked, and two of them passed a first run for the wrong
   reason: the simulation was being too kind. If a mutation does not bite, the
   sim is wrong, not the test.
3. `tests/pz_sim.lua` models the parts of the engine that made these bugs
   possible — the floor-gated z, vehicle gravity, the radial toggle's one-frame
   delay, and stale squares. Keep it honest; it is the only thing standing
   between a plausible change and another evening in the game.
