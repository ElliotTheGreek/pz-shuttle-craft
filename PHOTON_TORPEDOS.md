# Photon torpedoes

How the shuttle's main weapon works, how to change it, and what will bite you
if you do.

**Confirmed in game 2026-09-20**: the torpedo is drawn crossing the ground, it
detonates where it lands, it starts fires, the fires spread and burn buildings
down, and what is in the blast dies.

`DEV_GUIDE.md` is the general one and its "Rules that exist because they were
broken" still apply here. `MULTIPLAYER.md` is the client/server split and
`PILOTING.md` is flight. This file is torpedoes.

---

## What happens when the pilot fires

```
client  mouse: hold right          T.aiming()      reticle appears, tinted
        pad:   reticle always up, right stick moves it (T.serviceAim)
        fire on the DOWN EDGE of left click / R3
                                   T.poll -> T.fire
                                   Net.send("fireTorpedo", {x, y, z})

server  Net.onServer("fireTorpedo")
        mayUse / flying / isDriver / cooldown / min+max range / chunk loaded
        queue { x, y, z, due = now + flight, player }
        s.torpedoAt = now                          <- cooldown starts HERE
        Net.toAll("torpedoLaunched", {x0, y0, level, x, y, z, ms})

client  T.launch -> drawn every frame between ship and target, light riding
        along, trail behind. Every client draws its own from that one packet.

server  S.serviceTorpedoes (OnTick) -> due -> detonate:
            instanceItem(C.TorpedoItem)            the warhead
            IsoTrap.new(pilot or nil, warhead, cell, square)
            power / range / fire chance / fire energy / fire range / smoke
            setInstantExplosion(true); triggerExplosion()
        Net.toAll("torpedoDetonated", {x, y, z})

client  T.clearFlight() -- tidy-up only; the flight normally ends on its own
        timer a frame or two earlier
```

Two orderings in there are deliberate and easy to break:

- **The blast waits for the torpedo to arrive.** It used to happen in the
  command handler, on the frame the request landed, which put the explosion
  before the thing that caused it.
- **The cooldown starts at launch, not at impact.** Otherwise flight time is
  free reload time and a close shot rearms sooner than a far one.

---

## Where everything lives

| File | What it holds |
|---|---|
| `shared/TREK/TREK_Config.lua` | every constant — sections *Photon torpedoes* and *the projectile* |
| `server/TREK/TREK_Server.lua` | `fireTorpedo` queues; `detonate` is the only place a blast happens; `S.torpedoesBurn()` reads the sandbox |
| `client/TREK/TREK_Torpedo.lua` | aiming, the reticle, the fire request, the projectile and its light |
| `media/scripts/trekshuttle.txt` | `item TrekTorpedo` — what the trap is born with |
| `media/sandbox-options.txt` | `TrekShuttle.TorpedoFire` — Full or Blast only |
| `lua/shared/Translate/EN/Sandbox.json` | that option's name, tooltip and two values |
| `tools/gen_reticle.py` | `media/ui/TREK_Reticle.png` |
| `tools/gen_torpedo_flight.py` | `media/ui/TREK_TorpedoFlight.png` **and its contact sheet** |
| `design/art/ui/torpedo_flight_sheet.png` | what the sprite was judged on |
| `tests/test_multiplayer.py` | the `torpedoes()` scenario |
| `tests/pz_sim.lua` | `IsoTrap` recorder, the fire model, lamps, mouse, iso↔screen |

---

## Changing it

### The blast

```lua
C.TorpedoPower = 90      -- ExplosionPower, vanilla PipeBomb's
C.TorpedoRange = 7       -- ExplosionRange, in tiles
```

Vanilla's numbers on purpose, so the damage is already balanced against
everything else that explodes in this game. Set in **two places** — here and
`item TrekTorpedo` — and the Lua re-asserts over the item, so the Lua wins.

**Every range is clamped to 15 by the engine** (`Math.min(range, 15)` is the
first instruction in `drawCircleExplosion`). Setting any of them higher does
nothing and misleads whoever reads it next.

### The fire

```lua
C.TorpedoFireChance = 60    -- per-square ignition density
C.TorpedoFireEnergy = 100   -- vanilla's fire brush
C.TorpedoFireRange  = 3     -- a ring beyond the blast that only starts fire
C.TorpedoSmokeRange = 9
```

**`FireStartingChance` is a density dial, not a yes/no.** The roll is
`Rand.Next(100) < getFireStartingChance()` and it is taken **once per square,
inside the double loop**, so at 60 about three squares in five ignite. Turn it
up for a solid wall of flame, down for scattered fires that spread on their
own.

**These are the visible part of the weapon.** Build 42 has no separate
explosion effect — the fire and the smoke are the whole picture. Zero any of
them and that third of the effect does not merely go quiet, it never runs:
`triggerExplosion()` skips any mode whose range is `<= 0`.

If you raise `TorpedoRange` or `TorpedoFireRange`, **raise `TorpedoMinRange`
with them**. The blast reaches `TorpedoRange`, the fire reaches
`TorpedoRange + TorpedoFireRange`, and the pilot has to land somewhere.
`torpedoes()` asserts `TorpedoMinRange > TorpedoRange + TorpedoFireRange` so
this cannot drift silently.

### What burning costs, and who is already protected

`IsoGridSquare.Burn()` → `BurnWalls(true, true)` is what **destroys
structures**. It returns immediately on a client, so it is
server-authoritative for free, and it checks these itself — nothing in this
mod needs to:

- `ServerOptions.noFire` — owner has fire off, nothing burns;
- `SafeHouse.isSafeHouse` — safehouses are protected;
- `NonPvpZone.getNonPvpZone`, consulted inside `drawCircleExplosion` — safe
  zones limit the blast too.

The mod's own lever is the sandbox option:

```
TrekShuttle.TorpedoFire   1 = Full (default)   2 = Blast only
```

*Blast only* zeroes the four fire settings and keeps the power and radius — it
removes the arson, never the weapon. Read in `S.torpedoesBurn()`. **An absent
option reads as Full**, deliberately: treating a missing setting as "no fire"
is how a feature turns itself off in the one setup nobody tested. If you add
another sandbox option here, copy that default and add the `Sandbox.json` keys
in the same commit — a missing translation resolves to nothing, silently.

### The projectile

```lua
C.TorpedoSpeed       = 30    -- tiles per second
C.TorpedoMinFlightMs = 250   -- a close shot is still watchable
C.TorpedoMaxFlightMs = 2000  -- a silly speed cannot owe a detonation for ever
C.TorpedoTrail       = 6     -- echoes behind the head
C.TorpedoTrailMs     = 45    -- how far apart in time
C.TorpedoLight = { r = 0.55, g = 0.80, b = 1.00, radius = 5 }
```

**It is drawn in screen space and places nothing in the world.** The texture is
positioned with `isoToScreenX/Y` on the same overlay that draws the reticle.
Do not be tempted back toward `IsoObject`s walked along the ground:

- **there is no sprite for it.** Searching `tools/_catalog/tiles.json` for
  `explosion`, `fire_`, `flame`, `smoke`, `blast`, `effect`, `spark` and `glow`
  returns **nothing**. PZ's fire is an `IsoFire` with an *attached animation*,
  not a tile;
- **a client laying world objects every tick is the sky plane's whole
  catalogue of trouble** — squares that will not answer yet, shadows outliving
  what cast them, debris stranded in the air when a flight ends badly.

Screen space has neither problem, and it is why this feature needs no cleanup
path at all.

Things in there worth not undoing:

- Sizes divide by `getCore():getZoom(playerNum)`, as vanilla does with anything
  pinned to a world position (`ISBaseIcon:updateZoom`). Without it the torpedo
  is a fixed size on screen whatever the camera does.
- It **holds altitude then dives** — `p ^ 2.2` on the descent only. A linear
  fall reads as sliding down a wire.
- The trail echoes are earlier moments of the same flight, so they always lie
  exactly on the path, because they *are* the path.
- **The overlay is not tied to `atTheControls`.** A passenger, another pilot on
  a server and whoever is being shot at all need it. It used to be created and
  destroyed with the pilot's own reticle.
- The light is the one thing that reaches the world. It is rebuilt only when
  the tile under it changes — a light moved every frame is a lot of engine
  churn for something airborne for a second — and `douse()` removes it on
  landing. `removeLamppost` takes the `IsoLightSource` that `addLamppost`
  returned, not a position.

### The sprite

```sh
python tools/gen_torpedo_flight.py TrekShuttle/42
```

Writes the texture **and** `design/art/ui/torpedo_flight_sheet.png`, which is
the head and trail composited over grass, tarmac, a pale roof and night at two
zooms. **Look at the sheet.** It is the whole reason the sprite has a dark
skirt: the first version was a pure glow, unmissable on three of those four
and nearly invisible on the roof — which is what a shuttle firing from above
the buildings crosses constantly. A bright sprite has no contrast on light
ground.

The core is white because `TREK_Torpedo.lua` tints at draw time and **a tint
multiplies** — any colour baked in fights the one the draw is trying to say,
and the dark skirt survives tinting for the same reason.

If you change `C.TorpedoTrail`, change `TRAIL` in the generator to match. They
are deliberately not shared: the Lua is what runs, the generator is what judges
it, and a sheet that silently disagrees with the game is worse than none.

### The input

**Mouse:** hold right to aim, left click to fire.
**Controller:** the right stick moves the reticle, R3 (right stick click)
fires. From the driver's seat, in the air. No mode, no arming step.

The two differ in one way on purpose: **on a controller the reticle is simply
up** whenever you are at the controls. A mouse already puts a pointer on the
screen, so right-drag means "I mean that spot"; a pad has no pointer, so hiding
the reticle behind a held button would hide the only thing saying where the
virtual cursor has got to.

Three things in the controller path worth not undoing:

- **The right stick, not the left or the triggers.** The left stick steers --
  `BaseVehicle` drives off `forwardAxis` and `setAngleAxis` -- and the triggers
  are the obvious home for accelerate and brake, a binding that lives in Java
  where this mod cannot read it. R3 is the one control in reach that vanilla
  binds nowhere in its Lua.
- **The stick is integrated in `T.poll`, never in `aimPoint`.** `aimPoint` is
  called several times a frame (render, `aimStatus`, `targetSquare`), so moving
  the cursor there would move it once per caller and the reticle would travel
  two or three times faster than asked, at a speed that changed with whatever
  else happened to be drawing.
- **`wasMouseActiveMoreRecentlyThanJoypad()` decides the device**, not "is a
  pad plugged in". The latter is what the code did first, and it would have
  taken aiming away from every desktop player who owns a controller.

The click is taken on the **down edge**, worked out in `T.poll` rather than
trusting `isMouseButtonPressed`, whose level-versus-edge meaning is not
documented anywhere. A wrong guess there is a fire attempt every frame the
button is held: bounded damage, unbounded noise.

Do not make arming a menu toggle. It was one once, and it failed in the
quietest way available — no error, no log line, the file loaded, and the pilot
held right-click, clicked left and got silence. **An input nobody can discover
is the same as no input.**

---

## The rules it obeys

Not optional; `MULTIPLAYER.md` has the reasoning.

- **The blast happens on the server only.** `IsoTrap.shouldProcess` lets a
  client damage only the zombies it owns (`isLocal()`) and never a player,
  while the server damages all of them. If both fired, a client-owned zombie
  would be hit twice. Damage rides `IsoMovingObject.Hit`, the engine's ordinary
  synced path.
- **A client is a request, never a fact.** Every number in `fireTorpedo` is
  re-validated server-side. The range bound exists because without it a crafted
  command is a map-wide mortar, and `torpedoes()` asserts the ceiling as a flat
  number so raising the constant cannot move the test with it.
- **The projectile is scenery**, so each client draws its own — the same
  documented exception the sky plane uses. Drawing it in screen space makes
  that structural rather than a promise: there is no world edit to get wrong.
- **Fire is synced by the engine.** `IsoFireManager.StartFire` sends its own
  packet to nearby clients (`INetworkPacket.sendToRelative`), so the mod needs
  no packet for the visible half of the blast.
- **No admin-only or `-debug`-gated calls.** `IsoFireManager.explode` is what
  vanilla's *debug* fire brush uses; it is public and ungated but it is the
  wrong call — unconditional `StartFire` plus `BurnWalls`, and it touches no
  character at all.

---

## Engine facts, established

With `tools/pzapi.py` (exists, public), `tools/javarefs.py` (what it touches)
and `tools/javadis.py` (**under what condition** — the one that matters). Do
not re-derive these.

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
| `triggerExplosion()` fires the `OnThrowableExplode` Lua event — unused here, but it is the hook if a torpedo ever needs to notify something | HIGH |

---

## Testing

`tests/test_multiplayer.py::torpedoes()` covers: the pilot fires by holding
right mouse and clicking left; a bare left click fires nothing; a held button
fires once; the ground, the cooldown, both range bounds and a passenger are
refused; the torpedo is in the air after launch and gone after it lands; it
carries a light and that light is put out; the blast does not happen on the
frame the trigger is pulled; the trap's four fire settings match config and are
all above zero; the target square really reports `haveFire()`; *Blast only*
removes the fire and keeps the weapon; and an absent sandbox option means Full.

**Mutation-check anything you add here**, and confirm the mutation applied —
the Lua is **CRLF**, so a Python replace built on `\n` matches nothing and you
end up testing the unmutated file. Nine mutations are known to be caught: fire
chance to 0, fire ring to 0, smoke to 0, min range back to 4, the sandbox
option ignored, an absent option read as no fire, detonating on the trigger,
the projectile never drawn, and the flight light never put out. There is no
mutation runner in `tools/` — write one in the scratchpad.

Four things this scenario has got wrong, all worth not repeating:

1. **It called the server handler directly**, so it proved the blast and never
   the input. A build in which no player could fire passed every check. Drive
   the input.
2. **The simulation was kinder than the engine.** `pz_sim`'s `IsoTrap.new`
   accepted a nil weapon, so the test passed over a build that threw a
   `NullPointerException` in game. It errors now, and the fire model clamps
   radius to 15 because the engine does. Keep it honest.
3. **A guard derived its expectation from the thing under test.** It fired at
   `TorpedoMaxRange + 6`, so raising the constant moved the shot with it.
4. **Every "this should work" shot was hard-coded at 10 tiles**, so raising
   `TorpedoMinRange` to 12 turned them all into out-of-range refusals that
   still *passed* the checks reading `#SIM.traps == 0`. They are `OK = 18` now,
   named once at the top.

---

## What will bite you

- **No hot reload.** Mod Lua loads when a world starts, and `.txt` script
  changes too. Every change needs a full restart.
- **The fire settings live in two files.** `trekshuttle.txt` is what the trap
  is born with, `TREK_Server.lua` is what re-asserts them and what the sandbox
  option can turn down. Changing one and not the other looks like it worked.
- **Read the result back.** `[TREK] torpedo detonated:` logs the count on the
  target square *and* whether anything is actually burning. That second number
  is the one that was silently 0 for three commits.
- **`U.try` returns nil for "it failed" and nil for "it legitimately returned
  nothing."** Return a reason, not a boolean, where the answer authorises
  something.
- **`U.batch`, not `U.try`, for anything per-tick.** A method that does not
  exist throws out of Java and dumps a stack trace *per call*; this mod has
  hit 2932 in one session, which is what a black screen looks like from the
  inside. The projectile's light uses `U.batch` for exactly this.
- **The radial menu is a toggle** — take any reading *before* calling through
  to vanilla. This hid flight completely for a session.
- **A comment and a test can hold a bug in place.** See below.

---

## Not built

- **The controller is built but has not been held.** The right stick moves the
  reticle and R3 fires; the logic is covered by seven mutation-checked checks.
  What a test cannot answer is whether `C.TorpedoAimSpeed` (950 px/s) feels
  right in a hand, and whether **R3 is actually free** on a Steam Deck --
  the vehicle's own bindings live in Java where this mod cannot read them,
  which is exactly why the triggers were avoided. If R3 turns out to be taken,
  `fireHeld()` is the one function to change.
- **Two players.** Nothing here has been fired with two people connected. The
  projectile is drawn by each client from one `torpedoLaunched` and the fire is
  synced by the engine's own packet, so it should need nothing of ours — which
  is exactly the kind of claim that wants checking.
- **`media/ui/TREK_Torpedo.png`** is generated by `tools/gen_radial_icons.py`
  and referenced by nothing since the radial slice was removed. It is a 48px
  flat menu icon, the wrong shape for the projectile, which has its own sprite.
  Either give it a use or delete it.

---

## How it came to be invisible

Kept because the lesson generalises, and `DEV_GUIDE.md` cites this as the case
that produced the rule.

For three commits the torpedo killed what was in its blast and **nothing was
ever seen to happen**. The cause was `C.TorpedoFireChance = 0`, and three
things were holding it there:

1. the constant;
2. a long comment above it explaining why 0 was correct, ending "raise it and
   the mod sets Muldraugh alight";
3. a test that failed if it was ever raised, labelled *"THE one that matters"*.

Every one of those was **accurate about the engine**. `IsoTrap` really does
gate `Burn()` and `IsoFireManager.StartFire` on that roll; raising it really
does set fire to things; vanilla's `PipeBomb` really does ship 0. What they
were wrong about was the **goal** — they came from reading one line of
`ROADMAP.md`, "an explosion that does not set the street on fire", as *no fire
at all* rather than *fire as an intended weapon effect*.

And because in this engine the visible part of an explosion *is* the fire and
the smoke, suppressing the fire suppressed the entire weapon except the damage.
So the tests passed, the comment justified them, and the feature was broken in
exactly the way the player could see and the repository could not.

- **A test encodes an expectation, not a fact.** When a feature is reported
  broken, the tests covering it are suspects, not witnesses.
- **An emphatic comment is the strongest possible signal to check.** "Must stay
  0" is a claim about intent, and intent is what a source file records worst.
- **Say which line of the spec a guard came from.** Had that comment cited the
  roadmap wording it was derived from, the misreading would have been visible
  the first time anyone looked.

A footnote with the same moral: when the fire was turned on, the *item script's*
comment still insisted `FireStartingChance = 0` was load-bearing, directly above
the block setting it to 60 — caught by a grep of the deployed build, not by any
check. Values and the prose above them go stale independently.
