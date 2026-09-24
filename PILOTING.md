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
| **Take her up** | She rises, smoothly, to the hover height and holds there |
| **Set her down below** | The existing footprint check, then she sinks to the ground |
| **Go aboard (cabin)** | Through to the interior, on the ground or in the air |

Then you **drive**. W/A/S/D, the stick, the seat chart, the mechanics screen —
all of it is vanilla's, untouched. The helm inside sets the top speed.

**Flight is a binary: she is on the ground, or she is hovering.** There is one
altitude, `C.flightLevel()`, and there is no climb, no dive and no
`setAltitude` command for them to send. What changed on 2026-09-24 is *which*
altitude: it is the sandbox option **Hover height** (2, 3, 4, 5, 6 or 8
storeys; default 5), because at level 1 a two-storey building has walls at her
own level and she drives into it like a car.

Her **shadow** lies on the ground under her the whole time she is off it — a
soft dark disc on the square she would be set down on, which makes it the
landing marker as well (section 2.3). Anything taller than her hover height is
a wall at her level: the **obstacle guard** slows her to a crawl short of it and
says so, rather than letting her fly into it (section 2.4).

### Why level 1 was the only one that worked, and why that was the climb

It was four levels with a cruise of 3 and *Climb* and *Dive* on the radial, and
in play only the ground and level 1 behaved. The report of what a climb looked
like is the diagnosis:

> initial take her up works. Take her up again and she is stuck and all of a
> sudden becomes a physics object and seems to just instantly tip and fall over
> or backwards back down to the previous plane, then was stuck

1. *Take her up again* laid a plane at level 2 and **teleported** her onto it
   in the same tick. The map had the floor; the physics engine had not heard of
   it yet — a floor reaches Bullet a beat later (`RecalcProperties` →
   `IsoChunk.checkPhysicsLater` flags the level, and Bullet asks for it on its
   next step through `updatePhysicsForLevelIfNeeded`).
2. With nothing under her in the physics she fell — "becomes a physics object"
   — onto the level-1 plane, which was deliberately still there, and tipped.
3. The old `serviceFlight` then saw z 1 against a recorded level of 2, found a
   floor at level 2 in the *map*, and teleported her up again. Every tick.
   A teleport zeroes a body's velocity, so she could not move: "stuck".

Level 1 survived that only because it was reached from the ground, where the
fall is nothing. So the fix is not a lower ceiling. It is: **never let go onto a
floor the physics may not have**, and **never retry every tick**. Section 2.1.

### Getting out of her

| | On the ground | Hovering |
|---|---|---|
| Walk out of the hatch | yes | **no** — a storey of nothing |
| Beam down | yes | yes, **and it is the only way off her** |
| Go aft to the cabin | yes | yes, from a seat (a beam) |
| Come forward to the cockpit | *Forward to the cockpit* too (since 2026-09-24): arrives beside her, where the hatch puts you, and takes a free seat | *Forward to the cockpit*, from the aboard menu: arrives on the ground beneath her |

That last row is not decoration. Without it, going aft in flight is a one-way
door: the hatch is shut, *Step outside* is hidden for the same reason, and the
only other way off her is a beam down — so a pilot who stepped through to read
the helm could never fly her again. `T.toCockpit` arrives on the **ground
beneath her** rather than on the plane beside her, waits for her to stream in,
and uses `vehicle:enter(seat, character)`, which is vanilla's own call
(`ISEnterVehicle.lua:50`) with its distance check in the *action* rather than
in the method. Arriving on real ground is the safety of it: a shuttle that
never loads leaves the player standing somewhere, not on a five-by-five island
of invisible floor with the engine culling everything below it.

And **when the last of the crew beams down from a hovering ship, she goes back
up.** Not down: coming down where she happens to be drops five tonnes of
shuttle onto whatever is underneath her, which may be a roof, a pond or a
horde. `S.endFlight(why, toOrbit)` clears the flight and then `S.toOrbit`
removes the vehicle and sets `landed = false` — the same state a recall leaves
her in, so *Call her down* already knows what to do with it. The crew are told
(`IGUI_TREK_BackUp`), because a ship that vanishes without a word is
indistinguishable from a ship that has been lost.

Two more ways out of the sky, both of which exist because the automatic one
failed in game and left a crew with no move at all:

- **Recall** sends an empty hovering shuttle back up, from the ground. It is
  refused while anybody is aboard — pulling her out from under them leaves them
  standing on nothing — and that refusal used to be flat.
- **Call her down** refuses for the same reason while somebody is flying her,
  and by its own name (`inFlight`) rather than by falling through to "not
  enough room", which would send a crewman off hunting for a bigger field.
  When she is empty it lands her, whatever the record says about flying.

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

### 2.1 Getting there: carried, held, let go, watched

Take-off and landing are **moves**, not teleports (`TREK_Flight`'s
`startMove` / `serviceMove`). Every tick her physics body is placed a little
higher (or lower), eased at both ends, directly above the square she started
on. The renderer draws a vehicle at its *physics* height, not at its whole
level — `ModelSlotRenderData.init`, bci 101-139, subtracts the level's base
from `origin.y` and draws the remainder — so a smooth body is a smooth picture.
2 levels a second, never quicker than 0.9 s.

On the way, **one square of floor rides one level under her** (`Sky.column`).
`BaseVehicle.update()` keeps a level only with a floor at it or the level
below, so without the column she would be drawn and collided at z 0 for the
second she spends between the ground and the plane. It is always *below* the
band she is in and never above: a floor that appears above a rising body is a
shelf in the physics engine, and running into one is what flips a vehicle. For
the same reason the plane at her flight level is laid only once she is **above**
it.

At the top she is **held** — placed every tick — while the plane is laid under
her and for `C.FlightSettleMs` after it is complete, so the physics engine has
heard of it. Then she is **let go** and **watched** for `C.FlightWatchMs`. The
column comes up as she is let go: one square under a hull three wide is a pivot,
not a support, and if the plane is not holding her she must be seen to sink
rather than be caught on it and read as holding. If she sinks more than
`C.FlightSinkTolerance` levels, or the engine's z is not her level, she is
carried back and held for longer — `C.FlightSettleAttempts` times, then she is
**brought back down** to the ground with *she cannot go up* and a WARN. Only
when the engine has held her does the client tell the server `airborne`.

Landing is the same in reverse: the column is laid one level under her, the
plane is lifted, and she sinks past floors that are no longer there.

### 2.2 Falling off the level in flight

If the engine lets her drop off her level in flight — a chunk streaming late,
a knock — she is carried back up by one move, at most once every
`C.FlightRecoverMs` and at most `C.FlightRecoverLimit` times a flight. After
that she is left alone and the pilot is told *she cannot hold this height —
set her down*. A recovery is one try and never carries her down: the server
has her recorded as flying, and only the pilot ends a flight.

### 2.3 The shadow

A soft black disc on the ground under her centre square — exactly the square
`F.land` hands the footprint check, so the shadow *is* where she would come
down. `TREK_Shadow.lua`. Three things decided how it is drawn:

- **Vanilla's ground markers** (`getWorldMarkers():addGridSquareMarker`, the
  tutorial's call at `client/Tutorial/Steps.lua:55`, no debug gate). Build 42
  draws them level by level — `FBORenderWorldMarkers.render(level, list)` draws
  a marker with the level it stands on — so a marker on the ground is seen by a
  pilot five levels up. They blend normally (`SRC_ALPHA, ONE_MINUS_SRC_ALPHA`)
  with a depth test, so black darkens and a building in front hides it.
- **Not an iso marker carrying a model**, which could have been any shape.
  `IsoMarkers.renderIsoMarkers` draws those only on the viewer's own level
  (bci 149-163): the pilot would never have seen it.
- **Not the vanilla vehicle shadow.** `BaseVehicle.renderShadow` draws at
  `fastfloor(getZ())` — at altitude that is the sky plane directly under the
  hull, not the ground. It is probably the "small black box" seen at level 1.

The renderer accepts one texture for these, `circle_center`, and it is a *ring*
— clear in the middle. So the disc is `C.ShadowRings` rings nested inside each
other, which fills it in. It moves a whole square at a time (markers take
integer positions), and it is round, not hull-shaped. Every client draws its own
from the vehicle it can see; nothing is placed in the world or synced.

### 2.4 The obstacle guard

Anything as tall as her hover height has walls at her level. Every tick the
physics owner reads the squares ahead of her, the way she is actually moving,
across her beam, at her flight level — `collideN`/`collideW` walls and anything
solid, the test vanilla's own builder uses (`ISBuildingObject.lua:309`) — and
brings her top speed down as a wall comes nearer, to `C.GuardCrawl` within
`C.GuardFrom` squares, with a note to the pilot. Turned away, she has her speed
back. **She is never lifted over it**: changing level in flight is the
manoeuvre that failed, and a tower is a thing to go round.

---

## 3. The pieces

```
client/TREK/TREK_Sky.lua      lays and lifts the floor and the column; knows nothing about flying
client/TREK/TREK_Flight.lua   the ascent and descent, keeping her level, the obstacle guard
client/TREK/TREK_Shadow.lua   her shadow on the ground
server/TREK/TREK_Server.lua   who may fly, and the watchdog that sends her back up
shared/TREK/TREK_Config.lua   every number below
```

### Who owns what

| | |
|---|---|
| **The plane** | Each client, for itself. Never synced. |
| **`flying`, `level`, `pilot`** | The server, as ship state, set by validated commands |
| **The lift, and keeping her level** | The machine that moves her: the driver's client on a server, and in single player this one (see below) |
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
→ `touchdown` → `touchdownGranted`, plus `flightEnded` to all. The server never
sets `flying` until the client reports the engine actually held the height: a
lift that failed must never leave the state saying she is up when she is
sitting on the grass.

There is deliberately **no `setAltitude`**, on either side. One altitude means
there is nothing to set, and a command left in place as a no-op is a request
with a handler that quietly does nothing — the shape this project keeps paying
for. `tests/test_multiplayer.py` fails if either end grows one back.

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

Two planes can exist for a moment — during a take-off, during a landing, and
(while there were four levels) during a climb, where trimming to the new target
first took the floor out from under her and she fell, once into a building.
`Sky.keep(level)` names the level she is actually on this instant, and trim
spares it. The climb is gone and the rule is not: the same two-planes moment
still happens every time she leaves the ground and every time she comes back.

A wrong height used to be corrected the moment it was noticed, by a teleport,
on the reasoning that six ticks is a long fall. **That is the rule that made
the climb "stuck"**: when the engine would not hold the height, the correction
ran every tick for ever and zeroed her velocity each time. A correction is now
a move, spaced and capped (section 2.2) — a correction that cannot succeed
must be allowed to stop.

### A watchdog gated on a loaded chunk never sees the case it exists for

**Every symptom of the second two-player report is this one line.** The check
that notices nobody is aboard and sends her back up lived inside
`serviceVehicle`'s `if found then` block — and `found` is the ship's vehicle
*as the cell lists it*, which is nil exactly when nobody is standing near her.
Which is exactly the case the watchdog exists to catch.

So a crew who beamed down and walked away left her flying for ever, and
everything else followed from `flying` being stuck true:

| What the player did | What happened | Why |
|---|---|---|
| tried the hatch | "Not while the shuttle is in the air" | `move` refuses `hatchIn` while `flying` |
| tried *Recall* | refused | `S.recall` refused any flight outright |
| walked off and called her down | **she arrived hovering** | `S.land` never cleared `flying`, so every client paved a plane and lifted her straight back up |
| tried *Enter* | nothing at all | `Core.enter` returned false in silence |

The watchdog runs unconditionally now, and `crewAboard(nil)` is correct rather
than merely tolerated: a player in a seat keeps her chunk loaded by being in
it, so an unloaded ship has nobody in a seat by definition, and the cabin test
does not need her at all.

Three things worth carrying past this one:

- **Ask what a guard's own inputs are nil for.** A nil here was not an error or
  an edge case, it was the *subject*. Anything conditioned on "the world near
  X is loaded" has a blind spot shaped exactly like "nobody is near X".
- **A stuck state needs a manual way out.** `S.recall` and `S.land` both know
  how to end a flight now, because the crew's own instinct — call her down, or
  send her back up — was right and both were refused.
- **Two graces, not one.** `FlightPilotGrace` (10 checks, one a second) covers
  the gap between a seat and the cabin. `FlightBoardingChecks` (30) is set by
  the server when somebody is *granted* a beam towards a hovering ship,
  because the ground at the far end can take far longer to stream in than the
  beam itself — and a crew watching her leave while they were dematerialised
  would be right to call it a bug.

The simulation was honest here for once: `cell:getVehicles()` already filters
on `SIM.loaded`. The test was the kind one — the pilot beamed down to a return
point a few squares away, so her chunk never unloaded. `flight_alone()` walks
them three hundred tiles off and checks `TREK.Vehicle.ship()` really is nil
before it believes the result.

### `getAngleX` and `getAngleZ` are not pitch and roll

**This is the one that made the first two-player flight unflyable, and it was
in from the day flight was built.** The report was "in hover she snaps us back
basically forever, but if I go backwards it seems to work", and both halves of
that sentence are the bug.

`keepLevel` ran every six ticks and read

```lua
if math.abs(vehicle:getAngleX()) < 4 and math.abs(vehicle:getAngleZ()) < 4 then
```

Those two are not fields. They are the X and Z of JOML's `getEulerAnglesXYZ`
decomposition of the whole rotation, times 180/π:

```
getEulerAnglesXYZ:  x = atan2(2(xw - yz), 1 - 2(x² + y²))
                    y = asin(2(xz + yw))
                    z = atan2(2(zw - xy), 1 - 2(y² + z²))
```

For a ship that is dead level and turned by yaw alone, the quaternion is
`(0, sin θ/2, 0, cos θ/2)`, so `x` is `atan2(0, cos θ)` — **exactly 180° the
moment the heading is more than a quarter turn from the one she spawned at**,
and `z` with it. So the test is true in one half of the compass and false in
the other, for a ship that is level in both.

And what it called is worse. `flipUpright()` is not "level her":

```
Quaternionf.setAngleAxis(0, _UNIT_Y)    ; an angle of ZERO -- the identity
Transform.setRotation(q)
BaseVehicle.setWorldTransform(t)        ; -> Bullet.teleportVehicle
```

an angle of *nothing* about Y. That is not level, it is **no rotation at all**:
it throws the heading away along with the pitch and the roll, and teleports the
physics body to do it. Turn her past ninety degrees and she was wrenched back
to her spawn heading ten times a second, losing her velocity each time. Reverse
never leaves the safe half of the compass, so reversing worked perfectly —
which is exactly how a player would describe it.

The fix is two lines and both of them matter:

- **ask the yaw-independent question.** The Y of her own up-vector, worked out
  from the three angles, is `cos(az)·cos(ax) − sin(az)·sin(ay)·sin(ax)`. One is
  level, zero is on her side, minus one is on her back;
- **level her about her own heading.** `Rx(0) Ry(a) Rz(0)` and
  `Rx(180) Ry(a) Rz(180)` are both exactly level — both are pure yaw — and they
  are the two halves of the compass. Which one carries her present heading is
  decided by the sign of `cos(angleX)`: the same artefact, read the right way
  round. `setAngles(flat, angleY, flat)` builds it with `Quaternionf
  .rotationXYZ` and applies it through the same `setWorldTransform` the lift
  uses, so it cannot cost height either.

`org.joml.Quaternionf` is **not** on `LuaManager$Exposer`'s allow-list, so none
of this could be done by reading the rotation directly; `Transform` is exposed
and hands out only its origin. `BaseVehicle.setAngles(F,F,F)` is the whole of
the reachable surface for orientation, and it takes degrees.

The tolerance went from 4° to 20° in the same pass, for a separate reason: a
vehicle's suspension pitches it several degrees under throttle and brakes, and
putting her right is a physics teleport the pilot feels as a stutter. Going
over backwards is ninety.

**And the simulation was kinder than the engine, again.** `pz_sim.lua` stored
the three angles as fields and handed them back, so the 180° artefact could not
exist there, and its `flipUpright` kept the heading the engine throws away. The
whole flight suite passed against a build nobody could steer. It keeps a real
quaternion now, decomposes it exactly as the engine does, and `flipUpright`
resets it to the identity — heading and all.

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
| `SkyLitterTop` | 8 | levels the litter sweep walks — the highest any setting flies, **not** the one in force |
| `FlightLevel` | 5 | the default hover height; `C.flightLevel()` reads the sandbox's `FlightHeight` |
| `FlightLevels` | 2, 3, 4, 5, 6, 8 | the sandbox option's choices, as z levels |
| `FlightClimbLevelsPerSecond` / `FlightClimbMinMs` | 2 / 900 | how fast she is carried up and down |
| `FlightSettleMs` | 600 | held at the top after the plane is complete, per attempt |
| `FlightWatchMs` / `FlightSinkTolerance` | 900 / 0.3 | watched after letting go; how far she may sink |
| `FlightSettleAttempts` | 3 | holds at take-off before bringing her back down |
| `FlightRecoverLimit` / `FlightRecoverMs` | 3 / 1500 | carrying her back to her level in flight, and then stop |
| `GuardFrom` / `GuardReach` / `GuardPerSquare` / `GuardCrawl` | 3 / 14 / 8 / 5 | the obstacle guard |
| `ShadowRings` / `ShadowSize` / `ShadowAlpha` | 7 rings / 4.4 / 0.55 | the shadow |
| `FlightSpeedSteps` | 15…120 | absolute top speeds, each distinguishable |
| `FlightLevelTolerance` | 20° | past this she is put right, about her own heading |
| `FlightPilotGrace` | 10 checks | nobody aboard and she goes back up |
| `FlightBoardingChecks` | 30 checks | somebody is beaming towards her; hold the above off |

Three traps in there. **`SkyLitterTop` is not `FlightLevel` and must not be
made to follow it.** Builds up to 1.3.0 flew as high as level 4 and a floor is
a saved world object, so the litter those flights left in somebody's world does
not disappear because the ceiling came down. **Speed steps must differ from
their neighbours** — they
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
asked for level 1: engine reports z 1, physics body is at level 1.1021
  (if the body is at the level and z is 0, the floor check refused it;
   if the body is at 0 too, the teleport itself did not take)
vehicle position 10819.97,10199.08,1.00  physics active=false
  seat 0: z=1.00 falling=false
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

- **Multiplayer.** Flown with two people for the first time on 2026-09-23, and
  it produced the levelling bug in section 4. What that session has *not* yet
  settled is whether the other machine draws her in the air: the wire format
  carries height (`VehiclePhysicsPacket` sends x, y, z and the server relays it
  without validation) and remote clients should re-derive the level from their
  own copy of the plane, but that is still reasoning.
- **Whether the engine holds her at level 5.** This is the question the
  2026-09-24 build exists to answer, and only the game can. The log says it
  either way: `holding at level 5: lowest ... after letting go, N hold(s)` on
  success; `she sank to level ...` for each failed hold, and `the engine will
  not hold her at level 5; bringing her back down` if it never does. If it
  never does, lower the sandbox **Hover height** to find the highest level
  that holds, and read section 1 again.
- **The shadow's look.** Nested rings of a texture drawn for highlights; it
  may band, and it steps a square at a time. `C.ShadowRings`,
  `C.ShadowAlpha` and `C.ShadowSize` are the knobs.
- **Rendering at height.** Every helicopter mod reports the ground or the
  aircraft going missing at altitude. Level 1 never showed it; level 5 has
  not been seen.
- **The guard and roofs.** A building exactly as tall as her hover height has
  its *roof* at her level. Whether a roof tile stops a vehicle is not settled;
  the guard slows only for walls and solid objects.
- **Going back up.** `S.toOrbit` fires when nobody has been aboard for
  `FlightPilotGrace` checks. The grace is what makes a beam survivable — a
  player is briefly in neither the seat nor the cabin while the transporter has
  them — and five checks has only been reasoned about, not timed against a real
  beam on a real server.
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

1. `python tests/test_multiplayer.py` — the flight scenarios are in `flight()`,
   `flight_ascent()` (the climb, the hold, the guard, the shadow and the
   descent, read tick by tick from `SIM.path`), `flight_refused()` (a height the
   engine will not hold, at take-off and in flight), `flight_two_machines()`
   (a crewman on the street watching her go up and come down) and
   `flight_endings()`.
2. **Break it on purpose and confirm the test fails.** Every guard in section 4
   was mutation-checked, and two of them passed a first run for the wrong
   reason: the simulation was being too kind. If a mutation does not bite, the
   sim is wrong, not the test.
3. `tests/pz_sim.lua` models the parts of the engine that made these bugs
   possible — the floor-gated z, vehicle gravity, the radial toggle's one-frame
   delay, stale squares, the vehicle's orientation as a real quaternion
   whose Euler decomposition reads 180° past a quarter turn, **a floor that
   reaches the physics three ticks after it reaches the map** (and
   `SIM.physicsRefuse`, a level the physics never holds), and **the driver's
   machine publishing the body's height** to every other client's copy, as
   `VehiclePhysicsPacket` does. Keep it honest; it
   is the only thing standing between a plausible change and another evening in
   the game.
