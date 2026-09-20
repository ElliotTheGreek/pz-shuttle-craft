# Photon torpedoes — implementation guide

The goal, what exists, why it falls short, and what has to be built.

Read `DEV_GUIDE.md` first (its "Rules that exist because they were broken"),
then `MULTIPLAYER.md` for the client/server split and `PILOTING.md` for flight.
This file is the torpedo feature specifically.

---

## 1. The goal

**A photon torpedo is a weapon you watch.** Firing one from the shuttle must
produce all four of these, and the feature is not done until it does:

1. **A visible torpedo.** Something leaves the ship and travels to the target.
   The player sees it cross the ground.
2. **A visible detonation.** An explosion at the point of impact — flame,
   light, smoke. Not a silent stat change.
3. **Fire that spreads and burns the world.** A torpedo fired at a house sets
   the house alight. At a car, at a tree, at a fence — it burns. This is a
   deliberate, wanted effect, not a side effect to be suppressed.
4. **Kills what is in the blast**, which already works.

The player is flying a warship. Firing its main weapon has to look and behave
like firing a warship's main weapon.

### What this corrects

An earlier note in `ROADMAP.md` said the verify-first question was "an
explosion that does not set the street on fire." That was read as *no fire at
all*, and the implementation below suppresses every fire path deliberately.
**That reading is wrong.** The concern was never that fire is unwanted — it is
that fire must be a controlled, intended weapon effect rather than an
uncontrolled accident. Burning down a house you aimed at is the feature.

Everything in section 4.3 exists to be reversed.

---

## 2. What exists today

Commits `4420690` (research), `fc70b30` (first build), `0290d79` (input
rewrite), `4d2b23f` and `18681ff` (warhead). All static checks pass. Confirmed
in game: **zombies in the blast die.** Nothing is visible.

| File | What it does |
|---|---|
| `shared/TREK/TREK_Config.lua` | the constants, section *Photon torpedoes* |
| `server/TREK/TREK_Server.lua` | `Net.onServer("fireTorpedo", ...)` — the only place a blast happens |
| `client/TREK/TREK_Torpedo.lua` | aiming, the reticle, the fire request |
| `media/scripts/trekshuttle.txt` | `item TrekTorpedo` — the warhead spec |
| `media/ui/TREK_Reticle.png` | the reticle, `tools/gen_reticle.py` |
| `media/ui/TREK_Torpedo.png` | a radial icon, generated but **currently unused** |
| `tests/test_multiplayer.py` | `torpedoes()` scenario |
| `tests/pz_sim.lua` | `IsoTrap` recorder, mouse, `screenToIsoX/Y` |

### Current values

```lua
C.TorpedoPower       = 90     -- ExplosionPower, vanilla PipeBomb's
C.TorpedoRange       = 7      -- ExplosionRange, in tiles
C.TorpedoFireChance  = 0      -- <-- suppresses every visual and all fire
C.TorpedoMaxRange    = 28     -- how far from the ship a target may be
C.TorpedoMinRange    = 4      -- nearer than this and the ship is in the blast
C.TorpedoCooldownMs  = 6000
C.TorpedoItem        = "TrekShuttle.TrekTorpedo"
```

### Current interaction

Hold **right mouse** to aim (reticle appears, tinted green / gold / red for
ready / reloading / refused), **left click** to fire. Only from the driver's
seat, only while flying. `TREK_Torpedo.poll()` runs on `OnTick` and takes the
click on the button's *down edge*.

### Current flow

```
client  T.poll -> T.fire -> Net.send("fireTorpedo", {x, y, z})
server  validate (mayUse, flying, isDriver, cooldown, min/max range, chunk loaded)
        instanceItem(C.TorpedoItem)          -- the warhead
        IsoTrap.new(player, warhead, cell, square)
        setExplosionPower / Range / FireStartingChance(0) / FireRange(0)
        setSmokeRange(0) / setInstantExplosion(true)
        trap:triggerExplosion()
        Net.toAll("torpedoFired", {x, y, z})
```

---

## 3. Why nothing is visible

**In Project Zomboid, the visible part of an explosion is the fire and smoke.**
There is no separate explosion effect. `IsoTrap.drawCircleExplosion` in
`Explosion` mode, disassembled (`tools/javadis.py`, bci 247–318):

```java
boolean startFire = Rand.Next(100) < getFireStartingChance();   // 254-271
if (!GameClient.client && getExplosionPower() > 0 && startFire)
    square.Burn();                                              // 293
explosion(square);                                              // 299 always — the damage
if (local9 != 0)                                                // same roll, 197-214
    IsoFireManager.StartFire(cell, sq, true, fireStartingEnergy); // 316
```

`explosion(square)` is the damage and it is unconditional. Everything a player
*sees* — `square.Burn()` and `IsoFireManager.StartFire` — is gated on
`getFireStartingChance()`, and the current build sets it to **0**. Smoke is
gated separately on `getSmokeRange()`, also set to 0.

So the current behaviour is exactly right for the code as written: damage with
no picture. Three settings produce the silence:

| Setting | Now | Effect of the zero |
|---|---|---|
| `setFireStartingChance(0)` | 0 | no `Burn()`, no `StartFire`, no body-part burns |
| `setFireRange(0)` | 0 | no fire ring beyond the centre |
| `setSmokeRange(0)` | 0 | no smoke |

They are set in **two places** and both must change: the Lua in
`TREK_Server.lua`, and `FireStartingChance = 0` / `FireStartingEnergy = 0` in
the `item TrekTorpedo` block in `trekshuttle.txt` (the trap constructor copies
them off the weapon, and the Lua then re-asserts them).

**There is no projectile at all.** Nothing was ever written to draw one. The
blast is instant and centred on the target square the moment the command
arrives.

---

## 4. The work

### 4.1 A visible torpedo in flight

Nothing exists. This is the largest piece and the least researched.

PZ has **no projectile rendering to borrow** — thrown weapons and bullets are
not drawn in flight; the animation is the character, and the effect is applied
instantly. So this must be built.

Established facts:

- `IsoObject` is on `LuaManager$Exposer`'s allow-list, and
  `IsoObject.new(square, "sprite_name")` + `square:AddTileObject(obj)` is a
  real Lua pattern (`client/DebugUIs/Scenarios/Trailer2Scenario.lua:139`, and
  the mod's own cabin build uses `IsoObject.new`).
- `IsoLightSource` is exposed; the mod already lights the cabin with
  `cell:addLamppost(x, y, z, r, g, b, radius)` (see `U.batch` in
  `DEV_GUIDE.md`).
- The sky plane in `TREK_Sky.lua` is a working, tested example of **laying and
  lifting world tiles every tick along a moving path**. A torpedo is the same
  problem at a smaller scale and it is the code to copy.

Suggested approach, in order of increasing effort:

1. **A stepped sprite.** Place one `IsoObject` with a bright sprite on each
   square along the line from ship to target, one square per tick or two,
   removing the previous one. Roughly 10–28 steps.
2. **Add a moving light** (`addLamppost`) at the same position so it reads at
   night and gives the thing presence.
3. **A trail** — leave each sprite for N ticks instead of removing it at once.

Hard requirements for any of them:

- **Remove with `RecalcProperties()` and `RecalcAllWithNeighbours(true)`.**
  `RemoveTileObjectErosionNoRecalc` leaves the square holding every conclusion
  the engine drew from the object being there. This cost three rounds of
  debugging on the sky plane (`PILOTING.md`, "A floor's shadow outlives the
  floor") and `tests/pz_sim.lua` already marks a square stale when something is
  removed without the pair.
- **Slice it.** Anything walked per tick must not allocate. See *Slice any
  search that touches thousands of squares* in `DEV_GUIDE.md`.
- **Batch repeated engine calls** with `U.batch`, not `U.try` — a method that
  does not exist throws out of Java and dumps a stack trace *per call*, which
  in a per-tick loop looks like a crash (this mod has hit it: 2932 traces in
  one session).

Open question: **what sprite?** Options are a vanilla effect tile, or a
generated one (`tools/pngwrite.py` and the `gen_*.py` tools are the pattern;
`tools/gen_reticle.py` is the smallest example). A torpedo is a bright dot with
a glow, which is procedural work, not image-model work — see
`tools/gen_radial_icons.py`'s header for why.

Unverified, and worth checking before building: whether a sprite on a square
draws correctly *above* ground level (the torpedo flies at the ship's altitude
before descending), and how it interacts with the sky plane's floors.

### 4.2 A visible detonation

Mostly solved by 4.3 — in this engine the explosion *is* the fire and smoke.
Once `FireStartingChance`, `FireRange` and `SmokeRange` are non-zero there is a
visible detonation.

`IsoFireManager.StartFire(cell, square, boolean, int)` creates an `IsoFire`
with `numFlameParticles`, and **sends a `StartFire` packet to nearby clients**
(`INetworkPacket.sendToRelative`), so fire is synced by the engine and does not
need a packet of ours.

`IsoFireManager.StartSmoke(cell, square, boolean, int, int)` is the smoke
equivalent, with a real vanilla Lua call site at
`server/ClientCommands.lua:22`.

Sound already works: the warhead carries `ExplosionSound = PipeBombExplode`.

### 4.3 Fire that burns buildings

This is the reversal. The levers, all already verified:

| Lever | Where | Set to |
|---|---|---|
| `FireStartingChance` | `trekshuttle.txt` **and** `TREK_Server.lua` | a real value — 100 for "always", or tune |
| `FireStartingEnergy` | both | vanilla's fire brush uses 100 |
| `setFireRange(n)` | `TREK_Server.lua` | a ring of fire around the impact |
| `setSmokeRange(n)` | `TREK_Server.lua` | smoke |

What burning actually does, from the bytecode:

- `IsoGridSquare.Burn()` → `BurnWalls(boolean, boolean)`, which removes sheet
  ropes, barricades and window sheets, calls `GameServer.RemoveItemFromMap` and
  `RemoveTileObject`. **This is what destroys structures.**
- `IsoFireManager.StartFire` creates a spreading `IsoFire` with `spreadDelay`.

**Two server options gate all of it, and both are checked inside `Burn()` and
`BurnWalls()`:**

- `ServerOptions.noFire` — if a server owner has fire off, nothing burns, and
  that is correct behaviour to respect rather than defeat.
- `ServerOptions.safehouseAllowFire` — safehouses are protected.
- `NonPvpZone.getNonPvpZone(x, y)` is consulted inside
  `drawCircleExplosion`, so safe zones already limit the blast.

**Design decisions to make** (these are yours, the guide does not assume):

- Should fire be always-on, or a second fire mode? A torpedo that always
  starts a fire cannot be used near the ship's own landing site.
- Should `TrekShuttle.Access` or a sandbox option control whether torpedoes
  can burn, so server owners can allow the weapon but not the arson?
- What happens if a torpedo is fired at the cabin, the shuttle, or a player's
  base — is that the player's problem, or guarded?

`C.TorpedoMinRange = 4` exists because the blast is centred on the ground and
the ship would otherwise be inside it. With fire on, that distance likely needs
to grow, and the ship may need to be checked against the fire ring, not just
the blast radius.

---

## 5. Rules this must obey

From `MULTIPLAYER.md`, and they are not optional:

- **The blast happens on the server only.** `IsoTrap.shouldProcess` lets a
  client damage only the zombies it owns (`isLocal()`) and never a player,
  while the server damages all of them. If both fired, a client-owned zombie
  would be hit twice. Damage rides `IsoMovingObject.Hit`, the engine's ordinary
  synced path.
- **A client is a request, never a fact.** Every number in `fireTorpedo` is
  re-validated server-side. The range bound exists because without it a crafted
  command is a map-wide mortar.
- **The projectile is scenery**, so each client may draw its own — the same
  documented exception the sky plane uses (`MULTIPLAYER.md`, *The sky plane*).
  It must never touch ship state. `tests/pz_sim.lua` counts client world edits
  separately for exactly this reason; a new one must be counted too or the
  "no client edits the world" guard loses its teeth.
- **No admin-only or `-debug`-gated calls.** `IsoFireManager.explode` is what
  vanilla's *debug* fire brush uses; it is public and ungated, but it is also
  the wrong call — unconditional `StartFire` plus `BurnWalls` and it touches no
  character at all.

---

## 6. Verified engine facts

Established with `tools/pzapi.py` (exists, public), `tools/javarefs.py` (what
it touches) and `tools/javadis.py` (**under what condition** — this is the one
that matters, and it did not exist before this feature). Do not re-derive these.

| Fact | Confidence |
|---|---|
| `IsoTrap` is on `LuaManager$Exposer`'s allow-list | HIGH |
| `IsoTrap.new(character, weapon, cell, square)` has a vanilla Lua call site — `shared/TimedActions/ISPlaceTrap.lua:47` | HIGH |
| **The weapon may not be nil.** The constructor copies eighteen properties off it and throws on the first, `getSensorRange()` | HIGH, seen in game |
| `ExplosionMode` is `{Explosion, Fire, Smoke}`; the blast, fire ring and smoke have separate ranges | HIGH |
| Both fire paths gate on one `Rand.Next(100) < getFireStartingChance()` roll | HIGH |
| `explosion(square)` — the damage — is unconditional in Explosion mode | HIGH |
| `shouldProcess`: SP all; client only `isLocal()` zombies, never players; server all zombies, players per `ServerOptions` | HIGH |
| `drawCircleExplosion` respects `LosUtil.lineClear` (walls block) and `NonPvpZone` | HIGH |
| Fire is synced by the engine (`StartFire` packet `sendToRelative`) | HIGH |
| `IsoFireManager.explode` is an incendiary with no character damage — the wrong call | HIGH |
| `screenToIsoX/Y` are `GlobalObject` statics with non-debug callers (foraging, mining, building cursors) | HIGH |
| `isMouseButtonDown(int)` / `isMouseButtonPressed(int)` are `GlobalObject` statics; 0 = left, 1 = right | HIGH |
| Vanilla `PipeBomb`: `ExplosionPower 90`, `ExplosionRange 7`, `FireStartingChance 0`, `FireStartingEnergy 0` | HIGH |
| PZ draws no projectile for any thrown or fired weapon — there is nothing to borrow | HIGH |

---

## 7. Tests

`tests/test_multiplayer.py::torpedoes()` exists and covers: the pilot fires by
holding right mouse and clicking left; a bare left click fires nothing; a held
button fires once; the ground, the cooldown, both range bounds and a passenger
are all refused; and the trap's fire settings.

**The fire-settings checks assert zero and must be inverted** when 4.3 lands.
They are the block commented *"THE one that matters"*.

Mutation-check anything added. Four mutations bite today: aiming never true,
right mouse not required, no click edge, fire chance 50.

Three things this scenario got wrong at first, all worth avoiding again:

1. **It called the server handler directly**, so it proved the blast and never
   the input. A build in which no player could fire passed every check. Drive
   the input.
2. **The simulation was kinder than the engine.** `pz_sim`'s `IsoTrap.new`
   accepted a nil weapon, so the test passed over a build that threw a
   `NullPointerException` in game. It errors now — keep it honest.
3. **A guard derived its expectation from the thing under test.** It fired at
   `TorpedoMaxRange + 6`, so raising the constant moved the shot with it and
   the check sailed through. The sane ceiling is now asserted as a flat number.

Also note the Lua files are **CRLF**: a mutation done with a Python string
replace using `\n` silently matches nothing, and you end up testing the
unmutated file. Verify the mutation applied.

---

## 8. Gotchas already paid for

- **No hot reload.** Mod Lua loads when a world starts. Every change needs a
  full restart, and script (`.txt`) changes too.
- **`tools/deploy_windows.py`** installs to `Zomboid/mods/TrekShuttle` as
  `TrekShuttleDev`. The dedicated-server world `trektest2` is configured and
  ready (see the pinned section in `ROADMAP.md`).
- **Read the result back and log it.** Six bugs in this mod have had the same
  shape: a plausible engine call that fails silently, leaving something
  present, drawn and inert. `[TREK] torpedo away:` reports the count on the
  target square for exactly that reason.
- **`U.try` returns nil for "it failed" and nil for "it legitimately returned
  nothing."** Return a reason, not a boolean, where the answer authorises
  something.
- **The radial menu is a toggle** — take any reading *before* calling through
  to vanilla. This hid flight completely for a session.
- **An input nobody can discover is the same as no input.** The first build
  made arming a radial-menu toggle; the log was clean, the file loaded, and the
  feature read as broken.

---

## 9. Not built, and known

- **The controller.** `aimPoint()` in `TREK_Torpedo.lua` keeps a virtual cursor
  for a joypad and nothing moves it, so on a Steam Deck the reticle sits at the
  centre of the screen and does not track. The roadmap's original wording was
  "a reticle the stick moves for controllers". Every panel in this mod is
  required to work with a gamepad.
- **`media/ui/TREK_Torpedo.png`** is generated by `tools/gen_radial_icons.py`
  and referenced by nothing since the radial slice was removed. Either give it
  a use or delete it — dead assets are worse than none.
- **Two players.** No part of this has been fired with two people connected.
