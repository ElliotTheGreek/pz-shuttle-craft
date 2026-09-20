# Photon torpedoes — implementation guide

The goal, what exists, and what is left.

Read `DEV_GUIDE.md` first (its "Rules that exist because they were broken"),
then `MULTIPLAYER.md` for the client/server split and `PILOTING.md` for flight.
This file is the torpedo feature specifically.

---

## 1. The goal

**A photon torpedo is a weapon you watch.** Firing one from the shuttle must
produce all four of these:

1. **A visible torpedo.** Something leaves the ship and travels to the target.
   The player sees it cross the ground. — **built**, not yet seen in game.
2. **A visible detonation.** An explosion at the point of impact — flame,
   light, smoke. Not a silent stat change. — **built**, not yet seen in game.
3. **Fire that spreads and burns the world.** A torpedo fired at a house sets
   the house alight. At a car, at a tree, at a fence — it burns. This is a
   deliberate, wanted effect. — **built**, not yet seen in game.
4. **Kills what is in the blast.** — **confirmed in game.**

The player is flying a warship. Firing its main weapon has to look and behave
like firing a warship's main weapon.

---

## 2. What exists today

Commits `4420690` (research), `fc70b30` (first build), `0290d79` (input
rewrite), `4d2b23f` and `18681ff` (warhead), and the fire-and-projectile pass
this file now describes. All static checks pass, and every new assertion is
mutation-checked. **Confirmed in game: zombies in the blast die.** Everything
added since is unproven in game.

| File | What it does |
|---|---|
| `shared/TREK/TREK_Config.lua` | the constants, sections *Photon torpedoes* and *the projectile* |
| `server/TREK/TREK_Server.lua` | `fireTorpedo` queues; `detonate` is the only place a blast happens |
| `client/TREK/TREK_Torpedo.lua` | aiming, the reticle, the fire request, **and the projectile** |
| `media/scripts/trekshuttle.txt` | `item TrekTorpedo` — the warhead spec |
| `media/sandbox-options.txt` | `TrekShuttle.TorpedoFire` — Full or Blast only |
| `media/ui/TREK_Reticle.png` | the reticle, `tools/gen_reticle.py` |
| `media/ui/TREK_TorpedoFlight.png` | the projectile, `tools/gen_torpedo_flight.py` |
| `media/ui/TREK_Torpedo.png` | a radial icon, generated but **still unused** |
| `tests/test_multiplayer.py` | `torpedoes()` scenario |
| `tests/pz_sim.lua` | `IsoTrap` recorder, fire model, lamps, mouse, iso↔screen |

### Current values

```lua
C.TorpedoPower       = 90     -- ExplosionPower, vanilla PipeBomb's
C.TorpedoRange       = 7      -- ExplosionRange, in tiles
C.TorpedoFireChance  = 60     -- per-square ignition density
C.TorpedoFireEnergy  = 100    -- vanilla's fire brush
C.TorpedoFireRange   = 3      -- a fire ring beyond the blast
C.TorpedoSmokeRange  = 9
C.TorpedoMaxRange    = 28     -- how far from the ship a target may be
C.TorpedoMinRange    = 12     -- blast 7 + fire ring 3, and then some
C.TorpedoCooldownMs  = 6000
C.TorpedoSpeed       = 30     -- tiles per second in flight
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
        queue { x, y, z, due = now + flight, player }
        start the cooldown NOW, at launch
        Net.toAll("torpedoLaunched", {x0, y0, level, x, y, z, ms})
client  T.launch -> drawn every frame between ship and target, with a light
server  S.serviceTorpedoes (OnTick) -> due -> detonate:
            instanceItem(C.TorpedoItem)          -- the warhead
            IsoTrap.new(pilot or nil, warhead, cell, square)
            setExplosionPower / Range
            setFireStartingChance / Energy / FireRange / SmokeRange
            setInstantExplosion(true) / triggerExplosion()
        Net.toAll("torpedoDetonated", {x, y, z})
```

---

## 3. Why it used to be invisible

Kept because the reasoning is the most useful thing in this file, and because
the same shape will come round again.

**In Project Zomboid, the visible part of an explosion is the fire and smoke.**
There is no separate explosion effect. `IsoTrap.drawCircleExplosion` in
`Explosion` mode, disassembled (`tools/javadis.py`):

```java
boolean startFire = Rand.Next(100) < getFireStartingChance();   // 197-214
boolean burn      = Rand.Next(100) < getFireStartingChance();   // 254-271, a SECOND roll
if (!GameClient.client && getExplosionPower() > 0 && burn)
    square.Burn();                                              // 293
explosion(square);                                              // 299 always — the damage
if (startFire)
    IsoFireManager.StartFire(cell, sq, true, fireStartingEnergy); // 316
```

`explosion(square)` is the damage and it is unconditional. Everything a player
*sees* is gated on `getFireStartingChance()`, and the build set it to **0** —
in two places, the Lua and the item script — with an emphatic comment in
`TREK_Config.lua` insisting it must stay there, and a test asserting it.

So the behaviour was exactly right for the code as written: damage with no
picture. **Three things locked it in**, and they are worth naming separately
because each would have been enough on its own:

1. the constant, set to 0;
2. a comment above it explaining at length why 0 was correct;
3. a test that failed if it was ever raised, described as "THE one that
   matters".

The comment and the test were both written in good faith from a misreading of
one line of `ROADMAP.md` — "an explosion that does not set the street on fire",
taken to mean *no fire at all* rather than *fire as an intended weapon effect*.
Nothing in the codebase could contradict them, because they were not wrong
about the engine. They were wrong about the goal.

**The lesson worth carrying:** a test and a comment can agree with each other,
be accurate about the engine, pass every check, and still hold a bug in place.
Neither is evidence about what the feature is supposed to do. `DEV_GUIDE.md`
has this under *A guard is only as good as the goal it was written from*.

---

## 4. What was built

### 4.1 The projectile

**Drawn in screen space, and it touches nothing.** `TREK_Torpedo.lua` keeps a
list of torpedoes in the air, each with where it was fired from, where it is
going, when it started and how long it has; `Overlay:renderFlight()` places a
texture every frame with `isoToScreenX/Y`.

This is **not** the approach this file originally proposed. The suggestion was
to place an `IsoObject` on each square along the path. That was wrong twice
over:

- **There is no sprite to put on it.** Searching `tools/_catalog/tiles.json`
  for `explosion`, `fire_`, `flame`, `smoke`, `blast`, `effect`, `spark` and
  `glow` returns **nothing**. PZ's fire is an `IsoFire` with an *attached
  animation*, not a tile, so there was never a vanilla effect tile to borrow,
  and a generated one would have needed a TileZed `.pack`.
- **A client laying world objects every tick is the sky plane's whole
  catalogue of trouble** — squares that will not answer yet, shadows outliving
  what cast them (`PILOTING.md`, "A floor's shadow outlives the floor"), debris
  stranded in the air when a flight ends badly.

Screen space has neither problem: nothing is placed, so nothing can be left
behind, and both of the open questions this file used to carry — whether a
sprite draws correctly above ground level, and how it interacts with the sky
plane — simply stop existing.

Details worth keeping:

- Sizes divide by `getCore():getZoom(playerNum)`, which is what vanilla does
  with anything pinned to a world position (`ISBaseIcon:updateZoom`). Without
  it the torpedo is a fixed size on screen whatever the camera does.
- It **holds altitude then dives** (`p ^ 2.2` on the descent only). A linear
  fall reads as sliding down a wire, and since the ship is usually one or two
  levels up the whole descent would be spent in the first few tiles.
- The trail is `C.TorpedoTrail` echoes at earlier moments of the same flight,
  each smaller and fainter. They cost nothing and always lie exactly on the
  path, because they *are* the path.
- The one thing reaching the world is a light (`addLamppost`), rebuilt only
  when the tile under it changes and removed with `removeLamppost` on landing.
  This is the documented scenery exception the cabin's lamps already use.
- **The overlay is no longer tied to `atTheControls`.** It used to be created
  and destroyed with the pilot's own reticle, which is wrong now a passenger,
  another pilot, or whoever is being shot at also needs to see the shot.

### 4.2 The detonation waits for the torpedo

The blast used to happen in the command handler, on the frame the request
arrived — putting the explosion before the thing that caused it. The shot is
now queued with a due time and `S.serviceTorpedoes` (on `OnTick`, every tick)
sets it off on arrival.

**The cooldown starts at launch, not at impact.** Otherwise flight time is free
reload time and a close shot rearms sooner than a far one.

The pilot is stored with the shot for kill attribution and is allowed to be
gone by the time it lands — vanilla's own 3-argument `IsoTrap` constructor
passes `aconst_null` for the character, so nil is a legal attacker.

### 4.3 Fire that burns buildings

`FireStartingChance` is **60**, `FireStartingEnergy` **100**, `FireRange` **3**
and `SmokeRange` **9**, set both in `trekshuttle.txt` (what the trap is born
with) and in `TREK_Server.lua` (what the sandbox option can turn down).

What the numbers mean, from the bytecode:

- **The roll is per square, inside the double loop.** `FireStartingChance` is a
  *density* dial, not a yes/no: at 60, about three squares in five ignite.
- **`triggerExplosion()` calls `drawCircleExplosion` three times** — once per
  mode, each skipped entirely when its range is `<= 0`. That is why two thirds
  of the effect were not merely invisible but never ran.
- **Every range is clamped to 15** (`Math.min(range, 15)`, the first
  instruction). Setting any of them higher does nothing.
- `IsoGridSquare.Burn()` → `BurnWalls(true, true)` is what **destroys
  structures**, and it returns immediately on a client, so it is
  server-authoritative for free.

**Already respected without a line of ours**, all checked inside `Burn()` and
`BurnWalls()`: `ServerOptions.noFire`, `SafeHouse.isSafeHouse`, and
`NonPvpZone.getNonPvpZone` inside `drawCircleExplosion`.

**The sandbox option** `TrekShuttle.TorpedoFire` is *Full* (default) or *Blast
only*. Blast only zeroes the four fire settings and keeps the power and the
blast radius — it removes the arson, never the weapon. An **absent** option
reads as Full: treating a missing setting as "no fire" is how a feature turns
itself off in the one setup nobody tested.

`C.TorpedoMinRange` went **4 → 12** with the fire. The blast reaches 7 and the
fire ring reaches 10, so at the old distance the pilot lit ground they were
sitting over and would have to land on. `torpedoes()` asserts
`TorpedoMinRange > TorpedoRange + TorpedoFireRange`, so this cannot drift.

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
  documented exception the sky plane uses. It must never touch ship state.
  Drawing it in screen space makes this structural rather than a promise: there
  is no world edit to get wrong.
- **Fire is synced by the engine.** `IsoFireManager.StartFire` sends its own
  `StartFire` packet to nearby clients (`INetworkPacket.sendToRelative`), so
  the mod needs no packet for the visible half of the blast.
- **No admin-only or `-debug`-gated calls.** `IsoFireManager.explode` is what
  vanilla's *debug* fire brush uses; it is public and ungated, but it is the
  wrong call — unconditional `StartFire` plus `BurnWalls`, and it touches no
  character at all.

---

## 6. Verified engine facts

Established with `tools/pzapi.py` (exists, public), `tools/javarefs.py` (what
it touches) and `tools/javadis.py` (**under what condition** — the one that
matters). Do not re-derive these.

| Fact | Confidence |
|---|---|
| `IsoTrap` is on `LuaManager$Exposer`'s allow-list | HIGH |
| `IsoTrap.new(character, weapon, cell, square)` has a vanilla Lua call site — `shared/TimedActions/ISPlaceTrap.lua:47` | HIGH |
| **The weapon may not be nil.** The constructor copies eighteen properties off it and throws on the first, `getSensorRange()` | HIGH, seen in game |
| **The character may be nil.** Vanilla's own 3-arg constructor passes `aconst_null` for it | HIGH |
| `triggerExplosion()` calls `drawCircleExplosion` **three times** — Explosion/`ExplosionRange`, Fire/`FireRange`, Smoke/`SmokeRange` — skipping any whose range is `<= 0` | HIGH |
| **Every range is clamped to 15** by `Math.min` at the top of `drawCircleExplosion` | HIGH |
| The fire roll is **per square**, and Explosion mode takes **two independent rolls** — bci 197 for `StartFire`, bci 254 for `Burn()` | HIGH |
| `explosion(square)` — the damage — is unconditional in Explosion mode | HIGH |
| `Burn()` → `BurnWalls(true, true)` destroys structures, returns immediately on a client, and checks `ServerOptions.noFire` and `SafeHouse.isSafeHouse` itself | HIGH |
| `shouldProcess`: SP all; client only `isLocal()` zombies, never players; server all zombies, players per `ServerOptions` | HIGH |
| `drawCircleExplosion` respects `LosUtil.lineClear` (walls block) and `NonPvpZone` | HIGH |
| Fire is synced by the engine (`StartFire` packet `sendToRelative`) | HIGH |
| `IsoFireManager.StartFire` has **both** a 4-arg and a 5-arg form; `StartSmoke` is 5-arg only. Vanilla Lua calls the 5-arg `StartFire` (`server/ClientCommands.lua:17`) | HIGH |
| `IsoFireManager.explode` is an incendiary with no character damage — the wrong call | HIGH |
| `isoToScreenX/Y(playerNum, x, y, z)` are `GlobalObject` statics with ten non-debug vanilla call sites (foraging icons, fishing tension UI, `ISButtonPrompt`) | HIGH |
| `screenToIsoX/Y` are `GlobalObject` statics with non-debug callers (foraging, mining, building cursors) | HIGH |
| `isMouseButtonDown(int)` / `isMouseButtonPressed(int)` are `GlobalObject` statics; 0 = left, 1 = right | HIGH |
| `IsoCell.addLamppost(x,y,z,r,g,b,radius)` returns the `IsoLightSource`; `removeLamppost` takes that object | HIGH |
| `IsoGridSquare.haveFire()` is public with a vanilla Lua call site (`ISWorldObjectContextMenu.lua:274`) | HIGH |
| **There is no explosion, flame or smoke tile in the tileset.** PZ's fire is an attached animation on an `IsoFire`, not a sprite | HIGH |
| PZ draws no projectile for any thrown or fired weapon — there is nothing to borrow | HIGH |

---

## 7. Tests

`tests/test_multiplayer.py::torpedoes()` covers: the pilot fires by holding
right mouse and clicking left; a bare left click fires nothing; a held button
fires once; the ground, the cooldown, both range bounds and a passenger are all
refused; **the torpedo is in the air after launch and gone after it lands; it
carries a light and that light is put out; the blast does not happen on the
frame the trigger is pulled; the trap's four fire settings match config and are
all above zero; the target square really reports `haveFire()`; `Blast only`
removes the fire and keeps the weapon; and an absent sandbox option means
Full.**

**The fire-settings checks used to assert zero.** They were inverted with this
work. They are the block commented *"THE one that matters, and it used to
assert the opposite"*, and the paragraph above it is the post-mortem.

Nine mutations were checked and all nine are caught: fire chance back to 0,
fire ring to 0, smoke to 0, min range back to 4, the sandbox option ignored, an
absent option read as no fire, detonating on the trigger, the projectile never
drawn, and the flight light never put out. `tools/` has no mutation runner —
the script lived in the scratchpad; rewrite it if you touch this scenario.

Three things this scenario got wrong at first, all still worth avoiding:

1. **It called the server handler directly**, so it proved the blast and never
   the input. A build in which no player could fire passed every check. Drive
   the input.
2. **The simulation was kinder than the engine.** `pz_sim`'s `IsoTrap.new`
   accepted a nil weapon, so the test passed over a build that threw a
   `NullPointerException` in game. It errors now — keep it honest. The fire
   model added with this work follows the same rule: it clamps radius to 15
   because the engine does.
3. **A guard derived its expectation from the thing under test.** It fired at
   `TorpedoMaxRange + 6`, so raising the constant moved the shot with it and
   the check sailed through. The sane ceiling is asserted as a flat number.

A fourth, from this pass: **every "this should work" shot in the scenario was
aimed 10 tiles out**, and raising `TorpedoMinRange` to 12 turned all of them
into out-of-range refusals that would still have *passed* the checks reading
`#SIM.traps == 0`. They are all `OK = 18` now, named once.

Also note the Lua files are **CRLF**: a mutation done with a Python string
replace using `\n` silently matches nothing, and you end up testing the
unmutated file. Assert the mutation applied.

---

## 8. Gotchas already paid for

- **No hot reload.** Mod Lua loads when a world starts. Every change needs a
  full restart, and script (`.txt`) changes too.
- **`tools/deploy_windows.py`** installs to `Zomboid/mods/TrekShuttle` as
  `TrekShuttleDev`. The dedicated-server world `trektest2` is configured and
  ready (see the pinned section in `ROADMAP.md`).
- **Read the result back and log it.** `[TREK] torpedo detonated:` reports the
  count on the target square *and* whether anything is actually burning — the
  second number is the one that was silently 0 for three commits.
- **`U.try` returns nil for "it failed" and nil for "it legitimately returned
  nothing."** Return a reason, not a boolean, where the answer authorises
  something.
- **The radial menu is a toggle** — take any reading *before* calling through
  to vanilla. This hid flight completely for a session.
- **An input nobody can discover is the same as no input.** The first build
  made arming a radial-menu toggle; the log was clean, the file loaded, and the
  feature read as broken.
- **A comment and a test can hold a bug in place.** See section 3.

---

## 9. Not built, and known

- **The controller.** `aimPoint()` keeps a virtual cursor for a joypad and
  nothing moves it, so on a Steam Deck the reticle sits at the centre of the
  screen and does not track. The roadmap's original wording was "a reticle the
  stick moves for controllers". Every panel in this mod is required to work
  with a gamepad. **This is the one piece of the original spec still missing.**
- **`media/ui/TREK_Torpedo.png`** is generated by `tools/gen_radial_icons.py`
  and referenced by nothing since the radial slice was removed. It is a 48px
  flat menu icon and is the wrong shape for the projectile, which has its own
  sprite now. Either give it a use or delete it.
- **Nothing here has been seen in game since the fire was turned on**, and
  nothing has ever been fired with two people connected. In particular: how
  much of a town a chance-60 blast actually takes with it, and what the
  framerate does with that many `IsoFire` objects, are both reasoning.
