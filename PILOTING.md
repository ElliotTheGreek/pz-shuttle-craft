# Piloting the shuttle

The goal, the requirements, and what is already known. Written after the 1.1
single-player flight was removed and the 1.3 vehicle shuttle stalled.

`MULTIPLAYER.md` is the client/server design this must obey. `DEV_GUIDE.md` is
how to work on the mod. `ROADMAP.md` is the order of work.

---

Status: **built, awaiting its first test in the game.** The mechanism is
settled on the bench (§5.1); what the game still has to say is whether the
level change is reachable from Lua at all, what the sky plane costs, and
whether a ship at level 3 looks right. The mod reports all three into
`console.txt` by itself — nothing needs a debug console.

---

## 1. The goal

**Fly the shuttle by hand, over buildings and trees, at a speed the pilot
chooses, with a crew aboard, in single player and in multiplayer.**

It must feel like the 1.1 flight that worked in single player, and it must be
correct for a server: nothing that only works for the host, for an admin, or
under `-debug`.

### 1.1 What the single-player flight did (the bar to match)

From `TREK_Flight.lua` at commit `2ee0731`, before removal:

| Behaviour | Detail |
|---|---|
| Take off | From the landed hull: right-click → *Pilot the shuttle*. A rise over `C.FlightTakeoffTicks = 75` ticks. |
| Control | W A S D moved the ship freely in any direction, independent of the ground below. |
| Speed | `C.FlightSpeed = 1.50` squares per tick, multiplied by a helm setting: `{0.25, 0.5, 1, 2, 3, 5}`, default step 3 (1×). Top step is 7.5 squares per tick. |
| Height | The ship flew over buildings and trees; the model was lifted `C.FlightModelLift = 48` pixels in screen space, with its shadow left on the ground below. |
| Camera | Followed the ship. Zoom levels were widened while flying (`C.FlightZoomLevels1x/2x`). |
| Menu in flight | Right-click → *Land below*, *Enter the ship interior*, *Beam down below the shuttle*. |
| Landing | Set down on the ground under the ship, using the same footprint check as a called-down landing. |

### 1.2 Why it was removed

- The pilot's body was held in mid-air and the engine's fall simulation fought
  it every tick; pilots took fatal damage (seen in game, twice).
- Its protections used `setGodMod`, `setInvincible`, `setZombiesDontAttack` —
  role-gated in build 42, silently refused for an ordinary player.
- Moving a character at 22–450 tiles per second is exactly what the server
  speed anti-cheat kicks: four strikes and the player is removed.
- Flight outlived the pilot's death, and its full-screen overlay swallowed
  right-click.

None of that argues against the *goal*. It argues against moving a
**character** to fly. The ship has to be a thing the engine already moves.

---

## 2. Seating

Four seats, no doors — a doorless seat cannot be bitten
(`AttackVehicleState`: it bites through an open door or a broken window, and a
seat with no door part has neither).

| Seat | Position (tiles, vehicle space: +X left, +Z nose) | Role |
|---|---|---|
| FrontLeft | 0.55, 0.25, 1.3 | Pilot: flies the ship |
| FrontRight | −0.55, 0.25, 1.3 | Co-pilot |
| RearLeft | 0.55, 0.25, 0.1 | Passenger |
| RearRight | −0.55, 0.25, 0.1 | Passenger |

Requirements:

- Enter, ride and switch seats with the **vanilla vehicle controls** (V, the
  radial menu, the seat chart), so a controller and the Steam Deck work with no
  extra code.
- Every seat has its own outside position and area, so vanilla never has to
  enter one seat through another.
- Vanilla's three fallback paths (`processEnter`, `processShiftEnter`,
  `onExit` when a seat is blocked) assume a door and throw without one. They
  are overridden **for the shuttle only**.
- **Into the cabin** from a seat and from outside: leave the seat, then the
  existing arrival (a hatch move, charged like one).
- **Out of the cabin**: beside the ship wherever it stands, never inside it.
- The seat chart (`media/ui/vehicles/seatui/trekshuttle_base_small.png`) is
  projected from the hull mesh, so markers land on the real cockpit. Its length
  must equal the vehicle script's `extents` length (`tests/test_assets.py`).

---

## 3. Requirements

### 3.1 Multiplayer correctness (non-negotiable)

1. Works in single player, hosted co-op and any dedicated server, for a
   Workshop subscriber, with no admin rights, no `-debug`, no per-PC setup.
2. The server owns the ship's state; clients ask (`TREK_Net`) and are validated.
3. A client may move **its own character** only, and asks first
   (`Core.requestMove`) so beams stay inside the anti-cheat's budget.
4. No role-gated or debug-gated engine calls.
5. Nothing that leaves another player's UI holding a dead object (see 5.3).
6. Every new engine call verified three ways: `tools/pzapi.py` (exists, public),
   `tools/javarefs.py` (what it touches, which gates), and a vanilla call site.

### 3.2 Flight

1. **Over buildings and trees**, not merely over open ground.
2. **Pilot-chosen speed**: the helm's multiplier returns (0.25× to 5×), capped
   at what the server allows.
3. **No character is ever moved** to make the ship move.
4. **Crew ride along**: every occupant travels with the ship and can leave the
   seat for the cabin in flight or on the ground.
5. **Every player sees the same ship in the same place**, within normal sync.
6. **Landing** uses the existing footprint search and refusal reasons.
7. **Death, disconnect, or the pilot leaving the seat** ends flight safely: the
   ship settles, nobody is left in mid-air and nothing is left flying.
8. The ship is the same object on the ground and in the air — one ship, one
   state (`TREK_Ship`), never a second copy.

### 3.3 Anti-cheat budget (measured)

| Fact | Value | Source |
|---|---|---|
| Character speed flagged above | 20 tiles/s | bytecode |
| Strikes before kick | 4, one clears every 150 s | bytecode |
| `AntiCheatSpeed` values | 1 ban, 2 kick, 3 log, 4 off (enum: read with `getOption`, **not** `getInteger`) | vanilla UI + tested on the local server |
| Vehicle occupants allowed up to | server `SpeedLimit`, default 70 tiles/s | bytecode |

So: a **vehicle** may legitimately move at roughly 35× the speed a character
may. The 1.1 top step (7.5 squares/tick ≈ 450 tiles/s at 60 ticks) is far above
even that, so the speed steps must be re-based on what a vehicle may do.

---

## 4. Verified engine facts

Established with `tools/pzapi.py`, `tools/javarefs.py` and vanilla call sites.
Confidence in brackets.

- `addVehicleDebug(script, IsoDirections, skin, square)` spawns a vehicle with
  **no role or debug gate**, and does what the admin `/addvehicle` command
  does (create, `addToWorld`, register in `VehiclesDB2`). Called on the server,
  the game streams the vehicle to clients. [HIGH]
- `vehicle:permanentlyRemove()` is what vanilla's own server code uses. [HIGH]
- `vehicle:cheatHotwire(true, false)` on the server makes a vehicle startable
  with no key and flags itself for sync. [HIGH]
- A vehicle's mod data (`vehicle:getModData()`) persists and is how the ship
  identifies its own vehicle. [HIGH]
- `IsoCell:getVehicles()` returns a **Set** in build 42 — iterate it, there is
  no `get(index)`. [HIGH]
- **One PZ z-level is `2.4494900703430176` Bullet Y units**, from
  `BaseVehicle.setDebugZ`'s own constants. World X is `origin.x + offsetX` and
  world Y is `origin.z + offsetY` — 1:1 in scale, but against a **floating
  origin** that moves, so only *deltas* are meaningful and `WorldSimulation` is
  not exposed to Lua. [HIGH]
- `setDebugZ` clamps to the fraction *within the current level*: it poses, it
  cannot climb. [HIGH]
- `setAngles(x, y, z)` writes only the rotation, leaving the origin alone, and
  `flipUpright()` rotates about `_UNIT_Y` — so **Y is the up axis**. [HIGH]
- `Transform` and `org.joml.Vector3f` are on the Lua exposure allow-list and
  `Transform.getOrigin()` returns the live vector; `Bullet`, `CarController`,
  `WorldSimulation`, `Quaternionf` and `Matrix3f/4f` are **not** exposed, so a
  rotation cannot be built from Lua and everything must go through
  `BaseVehicle`. [HIGH]
- **The server runs no vehicle physics at all** — `setPhysicsActive` and
  `setWorldTransform` both skip their `Bullet` calls when `GameServer.server`.
  It is a relay, and it does **not** validate a vehicle's position:
  `VehiclePhysicsPacket` carries a full 3-D position and
  `checkPhysicsValidWithServer` compares x and y only. [HIGH]
- `update()` deletes a vehicle whose chunk references are empty
  (bci 83–106) — outrunning chunk streaming does not merely desync the ship, it
  destroys it. The pilot being seated aboard is what keeps chunks streaming
  around it. [HIGH]
- `damageObjects` and `breakingObjects` both return immediately unless the
  engine is running, and scan squares at `getZ()`. [HIGH]
- Vehicle physics is simulated on the **driver's client**; the server and other
  clients follow. So a lift-off must be driven from the driver's machine and
  must survive the engine re-asserting gravity. [MEDIUM-HIGH]
- `OnTick` fires on a dedicated server (`GameServer.main` → `IngameState`
  → `onTick`; vanilla's foraging relies on it). [HIGH]

---

## 5. Open problems

### 5.1 Holding a vehicle in the air — settled

**Approach 1 is disproven. Approach 2 is built and is what the mod now does.**
This section used to list three candidates; the bytecode settled it before a
line of flight was written, and that is the most valuable thing this work
produced, so it is recorded in full.

#### Approach 1 (physics off, transform driven) cannot work

`BaseVehicle.update()` runs every tick. Disassembled at bci 1385–1537:

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

**A vehicle's physics height is not its game z.** The engine zeroes z every
tick and restores the level only where a floor tile exists under the vehicle's
centre square. Everything that matters reads that clamped value:

| Reader | Consequence at altitude with no floor |
|---|---|
| `ModelCameraRenderData.init` (the render camera) | the ship is **drawn on the ground** |
| `getPassengerPositionWorldPos` → `setX/setY/setZ` | the crew are drawn on the ground too |
| `isIntersectingSquare`, `breakingObjects`, `damageObjects` | it **bulldozes fences and trees** it flies over |
| `VehicleManager.clientUpdateVehiclePos` | hard-writes `setZ(0)` — every **other player** sees it on the road |

The hold does not hold either: `isAtRest()` is false more than 0.2 levels above
its own square, so `CarController.checkShouldBeActive()` re-enables physics,
every tick, from two call sites. Vanilla's own `ISVehicleAngles.lua` re-asserts
`setPhysicsActive(false, false)` *and* the height on **every frame**, which is
the authors saying neither sticks. And its only caller is behind
`if getCore():getDebug()` in `ISVehicleMenu.lua:724` — the `-debug`-only trap
`DEV_GUIDE.md` names.

Approach 1 would have produced a ship that flies in the physics engine and sits
on the ground in the game: **present, drawn, and inert.**

#### Approach 2 is what the mod does

The same bytecode names the fix: put a floor there. Build 42 ships
**`invisible_01_0`**, whose only two properties are `attachedFloor` and
`solidfloor` — an invisible solid floor. With it under the ship:

- the height is legitimate, so ship and crew are drawn in the air;
- collision resolves at the flight level, so a two-storey building is passed
  over rather than demolished;
- remote clients re-derive the level the same way;
- the wheels have something to rest on, so **the ship simply drives** — no part
  of the mod fights gravity, and **nothing falls out of the sky when the pilot
  leaves the seat**, which is what lets the crew go aft in flight (§3.2.4).

`TREK_Sky.lua` lays it, per chunk around the ship rather than per tile as it
moves, so there is no churn and no outrunning it. `TREK_Flight.lua` moves the
ship between levels and watches. Vanilla does the driving, the steering, the
controller, the seats, the camera, the sync and the physics.

**The one call still unproven in the game** is the level change itself —
`Transform.new()` → `getWorldTransform` → mutate `getOrigin()` →
`setWorldTransform`. Every piece is public, ungated, and on the engine's Lua
exposure allow-list (`Transform` is entry #754, `org.joml.Vector3f` #31, and
`shouldExpose` is strict set membership), and `Transform.getOrigin()` returns
the live vector rather than a copy. But **none of those four has a vanilla Lua
call site**, so §3.1.6 is not satisfied for them. The mod therefore does not
trust the lift: it performs it, reads `getZ()` back off the engine a tick
later, and writes the verdict to the log either way.

#### Approach 3 remains the fallback

If the lift turns out to be unreachable in game, the ship becomes a flown model
with the crew in the cabin and a viewscreen in the cockpit. Nothing built for
approach 2 is wasted: the state, the authority split, the guards and the
landing path are the same either way.

### 5.2 Speed and streaming

At speed the ship outruns chunk streaming. The old flight logged
`flightModelMissing` and waited a tick. Whatever moves the ship must cope with
ground that has not arrived, and landing must wait for it (`C.LandingTimeout`).

### 5.3 Removing a vehicle out from under a UI

Standing beside a vehicle puts its seats and trunk in the loot window. If the
vehicle is then removed, vanilla's inventory page throws on that container
**every frame** — a wall of errors and a black screen. Seen in game.

Any design that removes the vehicle (including approach 3, and every recall)
must tell clients first and clear those windows, and the client must recover on
its own if it happens anyway. **This is currently unresolved in game**: a fix is
in (`TREK_VehicleMenu.dropDeadContainers`, server `vehicleGone`), and the
reported behaviour did not change, so the cause is not yet proven. Get a full
`console.txt` from a `-debug` launch before changing anything else here.

---

## 6. Acceptance

Flight is done when, on a **dedicated server with two players**:

1. The pilot takes off from a landed ship, flies over a two-storey building and
   sets down again; no damage to anybody, no kick.
2. A passenger in another seat sees the same journey and can leave for the
   cabin and come back.
3. Speed changes at the helm take effect and are capped at the server's limit.
4. Killing the pilot mid-flight leaves the ship somewhere sane and nobody in
   mid-air.
5. Logging out mid-flight and back in leaves one ship, in one place.
6. `tests/test_multiplayer.py` covers each of these in simulation first.
7. No `[TREK] WARN` lines and no Java stack traces in either log.

---

## 7. Test order

1. Single player, new world: take off, fly, land, hatch, recall.
2. Local dedicated server (`PZ-Worlds.ps1`, `Map=TrekShuttle;Muldraugh, KY`),
   one player: the same.
3. Two players: the acceptance list above.

Launch the client with `-debug`, and read `console.txt` **and** the dated
`Logs/…_DebugLog.txt`. The console file is a rolling tail: an error flood
overwrites the beginning, which is where the mod's own lines are.
