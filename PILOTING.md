# Piloting the shuttle

The goal, the requirements, and what is already known. Written after the 1.1
single-player flight was removed and the 1.3 vehicle shuttle stalled.

`MULTIPLAYER.md` is the client/server design this must obey. `DEV_GUIDE.md` is
how to work on the mod. `ROADMAP.md` is the order of work.

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
- `setPhysicsActive`, `setWorldTransform`, `setAngles`, `flipUpright` exist and
  are public on `BaseVehicle`. Whether they can hold a vehicle in the air is
  **unproven**. [UNKNOWN]
- Vehicle physics is simulated on the **driver's client**; the server and other
  clients follow. So a lift-off must be driven from the driver's machine and
  must survive the engine re-asserting gravity. [MEDIUM-HIGH]
- `OnTick` fires on a dedicated server (`GameServer.main` → `IngameState`
  → `onTick`; vanilla's foraging relies on it). [HIGH]

---

## 5. Open problems

### 5.1 Holding a vehicle in the air (the unsolved one)

Nothing in vanilla flies a vehicle. The engine snaps vehicles to the ground and
re-enables physics. Candidate approaches, in the order worth trying:

1. **Physics off, transform driven.** `setPhysicsActive(false)` on the driver's
   client, then set the world transform each tick. Questions: does the server
   accept the position; do other clients see it; does the engine re-enable
   physics; what happens at a chunk edge.
2. **Wheels on an invisible floor.** Keep physics, and give the vehicle
   something to stand on: raise the collision under it as it moves. Questions:
   what the floor is made of, whether it can move with the ship, whether it is
   visible to anyone.
3. **Not a vehicle in the air.** The vehicle is the ship on the ground; on
   take-off the server removes it and the ship becomes a moving *model* with
   the crew held aboard the cabin (they are already in an interior cell, which
   is where they are safe and where the engine never fights their position).
   The pilot flies from the helm with the camera on the ship. This trades the
   "sit in the cockpit and fly" feel for something the engine cannot argue
   with, and needs no character to be moved at all.

Approach 3 is the one that satisfies every requirement in 3.1 and 3.2 except
the feel of sitting in the seat while airborne. If 1 and 2 fail, take 3 and
give the cockpit a viewscreen instead.

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
