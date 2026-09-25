# Phasers — a tool, not a pistol

**Status (2026-09-24): built; the art is seen in game, the behaviour is not.**
The model, icon, beam and spark textures, sounds, the beam overlay, per-shot
bolts, and cutting trees and doors are all built, tested (single player and a
server with two clients) and mutation-checked. The author has seen the model
in the hand and on the ground and heard the lower pulse (2026-09-24). **The
beam, the bolts and cutting have not been in a game yet.** The tricorder's
lock override is removed. Still open: section 9's phase 6 needs nothing new if
the engine fires the shot event for other players as its bytecode says, and
only a two-machine game can confirm that.

| File | What |
|---|---|
| `shared/TREK/TREK_PhaserCut.lua` | the rules (`PC.refusal`), the tree and door world changes, and the timed action `TREKPhaserCut` |
| `client/TREK/TREK_PhaserFX.lua` | the overlay: cutting beams, per-shot bolts, the hum, the light; `TREK_PhaserFX()` on the console |
| `client/TREK/TREK_Phaser.lua` | the charge sweep, and the right-click: *Cut down with phaser*, *Cut through with phaser* |
| sandbox *Phaser cutting* | Trees and doors (default) / Trees only / Off |

`DEV_GUIDE.md`'s *Rules that exist because they were broken* and
`MULTIPLAYER.md` apply to every line of it. The four that matter most here:
**the server changes the world** (a felled tree and a broken door are world
changes); **a timed action is rebuilt on the server by its name and its
parameters**; **a vanilla call site proves reachability, never correctness**;
and **render it and look**.

---

## 1. What the author asked for

In the author's words, condensed (2026-09-24):

- The phaser **is basically a pistol** today. Change that.
- **Its own model**, made with FlowDot (Gemini for the concept, fal for the
  mesh), or found.
- **A laser effect** you can see.
- **The sound is a little too high-pitched.**
- **Aim it at a tree or a door** and get a **beam that stays on**, with a
  **sustained sound**, while the tree is **quickly felled** or the door
  **broken open**.

In the lore a phaser on a narrow, continuous setting is Starfleet's cutting
tool as well as its sidearm. Crews cut through bulkheads, rock and doors with
one on screen. So the phaser here doesn't just get a new texture: it does the
jobs of an axe and a sledgehammer, paid for in charge instead of sweat.

---

## 2. What exists today

Read from the tree on 2026-09-24.

| Piece | Where | What it is |
|---|---|---|
| The item | `media/scripts/trekshuttle.txt`, `item TrekPhaser` | A build 42 handgun: `AmmoType = base:bullets_9mm`, `MaxAmmo = 60`, `SwingAnim = Handgun`, **`WeaponSprite = Handgun03`** (vanilla's pistol model), `DoorDamage = 12` |
| The charge | `client/TREK/TREK_Phaser.lua` | A sweep every `C.PhaserInterval` ticks that puts back ammo, the chambered round and condition. The carrying client does it (`MULTIPLAYER.md`, *Phaser (carrying client)*) |
| The sound | `media/sound/TREK_PhaserPulse.wav`, from `tools/gen_phaser.py` | 0.28 s. The partials sweep **1000 to 420 Hz** and **1500 to 650 Hz** with a shimmer at twice the base. That is the "too high" |
| The icon | `media/ui/TREK_Phaser.png`, `media/textures/Item_TREK_Phaser.png` | Drawn pixel by pixel in `gen_phaser.py`. **64x64, although the phaser is a hotbar weapon** (see section 9) |
| Config | `TREK_Config.lua`, *Phasers* | `C.PhaserItem`, `C.PhaserType`, the three never-flags, `C.PhaserRack`, `C.PhaserCount` |
| Stock | armoury, `special = "phasers"` | Four, guaranteed |

There is no beam. A shot is a vanilla bullet, and you can't see bullets.

Nearby things the plan builds on:

- **`PHOTON_TORPEDOS.md`, *The projectile***: a projectile drawn in **screen
  space** with `isoToScreenX/Y`, sized by zoom, plus one light that moves
  only when its tile changes. It places nothing in the world and needs no
  cleanup. The beam follows the same design.
- **`MEDICAL_SET.md`, a tricorder lock override**: the author's intent
  (2026-09-24) is that **nothing in the mod unlocks doors, and a tricorder
  shouldn't**. But the code for one exists: `TREK_MedKit.lua` sends
  `Core.send("unlock")` and `TREK_Server.lua` handles it with `Med.unlock` and
  `obj:sync()`. It has never been seen in game. **Removing it is a phase of
  this plan** (section 9), so the phaser is the only way through a lock. Its
  server handler is still worth reading first: it already solves range
  checking against the server's position and syncing a door from the server.
- **The Doctor's pipeline** (`EMH.md`, *Replacing the Doctor source through
  Fal/Gemini*; `tools/assets/trek_emh/SOURCE.txt`): a Gemini concept image, then
  `fal-ai/trellis` image-to-3D, a vendored GLB, and `tools/import_gltf.py`.
- **Vanilla's own versions**: `shared/TimedActions/ISChopTreeAction.lua` (the
  axe) and `ISDestroyStuffAction.lua` (the sledgehammer, which handles double
  doors, garage doors and barricades).

---

## 3. The shape of the finished thing

```
Firing at a zombie        unchanged as a weapon; each shot now draws a short
                          orange bolt from the emitter to the target, with the
                          lower-pitched pulse

Right-click a tree with   "Cut down with phaser"  -> a timed action, beam on,
a phaser in hand          sustained hum, ~3 s, the tree falls as if an axe had
                          felled it (logs and all)

Right-click a door        "Cut through with phaser" -> the same, ~2 s, the door
                          is destroyed the way a sledgehammer destroys it
                          (barricades and a double door's other leaf with it)

Anyone nearby             sees the beam and hears the hum, in single player,
                          co-op and on a dedicated server
```

**A persistent beam defeats any lock**, just as it fells any tree: a locked
door, a key-locked door, a padlocked door. How it's locked doesn't matter,
because the door stops being there. It's the only thing in the mod that gets
through a lock.

What it deliberately does **not** do: cut walls, floors or windows (a
sledgehammer's job, and a sandbox-sized griefing tool on a server).

---

## 4. The model

**Built, 2026-09-24. Not yet seen in a hand in game.**

```sh
python tools/bake_phaser.py                 # once per new source; needs pip packages
python tools/gen_phaser.py TrekShuttle/42   # every build; PIL and numpy only
```

| File | What |
|---|---|
| `design/art/weapons/phaser/concept_34_raw.jpg` | the Gemini concept TRELLIS was fed (three-quarter) |
| `design/art/weapons/phaser/concept_side_raw.jpg` | the same design in profile, for reference |
| `tools/assets/trek_phaser/SOURCE.txt` | provider, model, request ids, seed, prompt, and what was rejected |
| `tools/assets/trek_phaser/trellis2_raw.glb` | the raw, 18 MB, **not committed** (`.gitignore`; its URL is in `SOURCE.txt`) |
| `tools/assets/trek_phaser/phaser_baked.json` / `.png` | the bake: mesh with UVs, and its 512px texture. **This is the vendored source** |
| `media/models_X/weapons/firearm/TREK_Phaser.x` | 2,600 faces, 0.030 x 0.151 x 0.123 |
| `media/textures/weapons/firearm/TREK_Phaser.png` | the texture |
| `media/textures/Item_TREK_Phaser.png`, `media/ui/TREK_Phaser.png` | the icon, 64x64, rendered from the mesh |
| `media/scripts/trekweapons.txt`, `TrekPhaserModel` | in `module Base`, with Handgun03's own hand and ground attachments |
| `design/art/weapons/phaser/phaser_sheet.png` | **the review sheet**, rewritten on every run |

### How it is made to look good

The plan is a loop, not a prompt: **every change is judged on a picture of the
thing at the size the player sees it**, and the pictures are generated by the
same command that builds the asset, so they cannot go stale.

1. **Concept first, in 2D** (Gemini). A clean three-quarter product shot on
   white, simple large shapes, no logos. This is the design; the mesh is only
   ever judged against it.
2. **Mesh from the concept** (fal TRELLIS v2). v1 was generated alongside for
   comparison and rejected (`SOURCE.txt`).
3. **Fit to vanilla, not to taste.** The bake puts the phaser in the frame of
   vanilla's M9 with its grip where the M9's grip is. So the hand closes on it
   where it closes on a pistol, and `Bip01_Prop2` and `world` are Handgun03's
   numbers rather than guesses. Its size sits inside vanilla's pistol bracket
   (`tools/meshbbox.py --vanilla handgun`).
4. **Repaint rather than trust.** The texture is baked per texel from the
   source, snapped to the concept's palette. Flat colour blocks survive the
   20-pixel size a held weapon is drawn at; a generator's soft, lit texture
   doesn't.
5. **The sheet** (`phaser_sheet.png`) shows four views with the M9 outlined
   over the side view in the same frame, then the phaser and the M9 at 18 and
   26 pixels over grass, tarmac, a pale roof and night, then the icon at 64
   and 32. It is drawn with a z-buffer that culls back faces, as the engine
   does, so a flipped face or a hole shows here the way it would in game.
6. **The icon against the set** (`tools/vet_icons.py design/art/all_icons.png`),
   never alone.
7. **Last, the game.** Only a fist can say whether the grip sits right.

### What the loop caught

Every one of these passed every number the build printed, and every one was
obvious on the sheet:

- **The mesh was a hollow shell.** TRELLIS's output is an outer skin and a dark
  inner skin a millimetre inside it, plus 1,046 loose scraps. Decimated as it
  stood, the inner skin showed through as black triangles all over the body.
  Two cheaper fixes failed on the sheet (dropping the scraps, and re-orienting
  faces). What worked is rebuilding the surface from a **filled volume**:
  voxels, close, fill, marching cubes, then decimate. That gives one closed
  skin by construction. *Assume every image-to-3D mesh is this shape until the
  sheet says otherwise.*
- **The first review renderer lied.** It was a painter's-algorithm renderer
  that drew interior scraps over the skin, and it could not tell a fault in
  the mesh from a fault in the drawing. It was replaced by a z-buffer.
- **Too big.** True to the concept it was 0.041 across, twice the M9. It was
  slimmed to 0.030 (`ACROSS` in the bake).
- **Flat colour per face** had sawtooth panel edges and specks wherever the
  source's thin seam line was sampled. The fix was a real texture: six planar
  charts by facing direction (xatlas has no build for this Python), baked per
  texel, cleaned with a mode filter, the seam closed along its length, and
  black allowed only on the grip.
- **The icon was the dullest in the set** (mean brightness 72 against the
  tricorder's 110). It was re-angled to show the white flank, lit brighter
  than the in-game preview, and given the one-pixel dark outline its
  neighbours all have.

**Two things the concept has that the model doesn't:** the four blue indicator
lights (TRELLIS dropped them, and at held size they would be one pixel) and a
glowing lens. The engine has no emissive channel for a weapon, so the emitter
is a bright orange that is lit like everything else, and the beam's flare
supplies the glow.

### To change it

- **Proportions, size, grip fit:** the constants at the top of
  `tools/bake_phaser.py` (`LENGTH`, `ACROSS`, the M9 grip numbers), then rebake.
- **Colours:** `PALETTE` in the bake. The classification bands (`DARK`,
  `LIGHT`) are about the *source's* brightness, so don't tune them for looks.
- **A new design:** new concept, new TRELLIS run, update `SOURCE.txt`, rebake.
  Look at the sheet after every step.
- **The hand position**, if a fist says it's wrong: move the grip fit in the
  bake, not the attachment numbers. Those are Handgun03's and are right for
  anything fitted the way this is.

---

## 5. The beam

**Art built, 2026-09-24; the overlay that draws it is not.**

```sh
python tools/gen_phaser_beam.py TrekShuttle/42
```

writes `media/ui/TREK_PhaserBeam.png` (a 32x16 strip whose only meaningful
axis is its vertical profile), `media/ui/TREK_PhaserSpark.png` (32x32), and
`design/art/ui/phaser_beam_sheet.png`: a bolt and a cut over grass, tarmac, a
pale roof and night, at zoom 1 and 2. **The sheet draws the beam exactly the
way the overlay must**, so the recipe below is the spec for the Lua:

| Step | What | Constant |
|---|---|---|
| 1 | the strip, stretched along emitter → target, turned, tinted | `TINT` (255, 120, 40), thickness `GLOW_PASS` x 16 px / zoom |
| 2 | the same strip on top, **untinted**, thinner | `CORE_PASS` 0.42, alpha `CORE_ALPHA` 0.9 |
| 3 | the spark at the emitter, tinted | `MUZZLE` 0.55 x 32 px / zoom |
| 4 | the spark at the target, tinted, then a smaller untinted one on top | `IMPACT` 1.7 x 32 px / zoom, core x 0.45 |

What the sheet taught, in order:

- **One tinted draw can never have a white-hot middle.** A tint multiplies, so
  the first beam was orange from edge to edge. The core is a second, untinted
  pass of the same strip.
- **A skirt at alpha 70 drew a hard grey box on a pale roof.** At 44, with a
  squared falloff, it is a soft shadow there and invisible on dark ground.
- **Six hard rays on the spark read as an arrowhead** on every beam. It has
  four soft ones now.
- **A spark the width of the beam loses the cut point**, which is where the
  eye goes. `IMPACT` 1.7.
- The strip's square ends are covered by the two flares, not by fading the
  texture: a fade baked into the strip stretches with it.

The rest of the design stands as planned:

- **Drawn in screen space, like the torpedo, placing nothing in the world.**
- **One overlay element** draws every visible beam this frame, **not tied to
  the local player's own weapon**, because other people's beams have to show
  too (the torpedo overlay learned this the hard way).
- **Geometry.** Start: the shooter's position plus a hand-height offset (an
  approximation; the hand bone isn't reachable from Lua). End: the target's
  square, or for a pistol shot the zombie hit or the end of the range. Both go
  through `isoToScreenX/Y`.
- **Life belongs in the Lua**, not the texture: a flicker on width and alpha,
  and a light at the impact tile (`addLamppost`, removed with the handle it
  returned).
- **Two modes, one renderer.** A **bolt** lasts about 120 ms per shot. A
  **sustained beam** stays on while a cutting action runs.

---

## 6. The sound

**Built, 2026-09-24; not yet heard in game.** Written by
`tools/gen_phaser.py`, synthesised with the standard library, no franchise
audio.

| Sound | File | What |
|---|---|---|
| `TREK_PhaserPulse` | 0.30 s | **The shot, lower.** The old one swept 1000 → 420 Hz with a partial at 1500 Hz. This one has a 480 → 210 Hz body, a partial at 1.5x the base, a 95 Hz thump and a burst of filtered noise: a *zap*, not a *chirp* |
| `TREK_PhaserBeam` | 1.00 s, `loop = true` | The cutting hum: a 196 Hz carrier with 1.5x/2x/3x partials, a 49 Hz growl, a 7 Hz wobble, crackle and pops |
| `TREK_PhaserBeamStart` | 0.22 s | The beam catching: a swell into the loop's own timbre |
| `TREK_PhaserBeamEnd` | 0.32 s | Letting go: the pitch sags and dies |

- **The loop is seamless by construction.** Every frequency in it is a whole
  number of hertz over a whole-second loop, so each term ends where it began.
  The noise, which isn't periodic, is crossfaded tail-into-head. Measured: the
  jump across the wrap is 1,429 against a typical sample step of 1,156. **Keep
  every frequency whole** when changing a number, or it clicks once a second
  for as long as a tree is being cut.
- **The loop and its tails share one level**, so the start hands over to the
  hum without a jump.
- The pulse is what the author said was too high, and the numbers are a first
  go. **The author judges it, not a test.**
- Still to build with the cutting: **cutting noise attracts zombies**, a
  `WorldSoundManager` sound at the target on a server-side tick, smaller than
  a gunshot.

`tests/test_assets.py` fails on a clip that's missing or a `playSound` name no
script declares; all four are declared in `trekshuttle.txt`.

---

## 7. Cutting: trees and doors

### The flow

```
client   right-click a tree/door with a TrekPhaser in either hand
         -> "Cut down with phaser" / "Cut through with phaser"
         -> walk into range (vanilla's luautils.walkAdj, as the axe does)
         -> TREKPhaserCutAction (shared, a GLOBAL class; new(character, target...)
            stores every parameter under exactly its own name)

server   rebuilds the action by class name
         isValid: target still exists, still a tree / door, within C.PhaserCutRange
                  of where the SERVER thinks they are, a phaser really in hand,
                  not a safehouse the player doesn't belong to, sandbox allows it
         start / serverStart: tell nearby clients "beam on" (from, to, who)
         each tick: the noise, at a spacing
         complete(): the world change, then "beam off"

clients  beam on  -> overlay draws the sustained beam, the loop sound plays
         beam off -> both stop; also stopped if no word comes for a few seconds,
                     so a lost packet cannot leave a beam on for ever
```

`perform()` runs on the client and is only for notes and sounds.
**`complete()` never runs on a client**, so every world change lives there
(`DEV_GUIDE.md`, *A timed action is rebuilt on the server...*).

### Trees

Vanilla fells a tree by calling `tree:WeaponHit(character, axe)` on each swing
from an animation event. The phaser has no swing, so the plan is **to find the
server-side call that fells a tree outright and drops its logs**. Section 8
has that question; it's the one this whole half depends on. Duration is
`C.PhaserTreeTime` (about 3 s), with no endurance cost and no strain.

### Doors

Destroy it the way a sledgehammer does: `IsoDoor` and `IsoThumpable` doors,
**a double door's other leaves and a garage door's other panels with it**, and
barricades on it. The work is **reusing vanilla's own logic** in
`ISDestroyStuffAction:complete()` rather than copying it. Section 8 asks
whether it can be called without a sledgehammer in hand. Duration is
`C.PhaserDoorTime` (about 2 s). **Locks are ignored entirely**: locked,
key-locked and padlocked doors all go the same way. The only refusals are
server policy, not locks: **a safehouse door that isn't yours** (a server's
safehouse rules are a promise to its players, and a phaser shouldn't be the
way round them), and anything the sandbox switches off.

### Sandbox

- **Phaser cutting**: on / off (servers that don't want a door-breaker).
- **Cutting time multiplier**.
- Maybe **Phaser breaks doors** separately from trees.

---

## 8. Settle before writing any of it

The verify-first phase. Each answer goes into this section with the tool that
gave it, as `ENERGY.md` section 3 does.

**All answered, 2026-09-24.** The engine facts the code rests on; don't
re-derive them.

1. **What fells a tree.** `IsoTree.WeaponHit` subtracts the weapon's
   `TreeDamage` and calls `toppleTree(character)` at zero. `toppleTree`
   **returns at once on a client** (bci 0-6); on the authority it removes the
   tree with `transmitRemoveItemFromSquare`, plays `FallingTree` to everybody
   (`PlayWorldSoundServer`), drops the logs through
   `AddWorldInventoryItem` (which transmits on a server), and puts the stump
   down. So the phaser calls `tree:toppleTree(player)` in `complete()` and
   skips only the counting down. `IsoTree` is exposed (vanilla calls
   `WeaponHit` on it from `ISChopTreeAction`), so its public methods are
   reachable.
2. **What breaks a door.** `ISDestroyStuffAction:complete()`'s authority path:
   barricades on both sides, every leaf through
   `buildUtil.getDoubleDoorObjects` / `getGarageDoorObjects`, then
   `transmitRemoveItemFromSquare`. `buildUtil` is in `server/`, so it loads on
   a server and in single player, which is where `complete()` runs. The
   break sound is the sledgehammer's: `character:playSound("BreakDoor")`.
3. **The pose.** `setActionAnim("BlowTorch")`, a tool held out and aimed at
   the work, with the phaser as the hand model. **To be judged in game.**
4. **Drawing a stretched, turned strip.** `DrawTextureAngle` only rotates.
   `ISUIElement:drawTextureAllPoint(tex, tl, tr, br, bl, r, g, b, a)` draws
   a texture on **any four corners**, so the beam is a quad from emitter to
   target with no angles and no tiling.
5. **The hum.** `playSound` may go over the network; `playSoundLocal` is
   `emitter.playSoundImpl`, local only, and returns a handle that
   `stopOrTriggerSound` takes. Every client plays the hum itself when it
   hears "beam on", on the shooter's own character, so nobody hears it twice.
6. **The shot.** `OnWeaponSwingHitPoint(character, weapon)` (vanilla's own
   `ISReloadWeaponAction.onShoot` uses it) fires on a shot, and
   `zombie.network.fields.hit.Player.attack` fires it for **other players'**
   shots on each client too, so bolts need no relay.
   `OnWeaponHitCharacter` shortens a bolt to what it hit.
7. **The server's hooks on a timed action.** `NetTimedAction.start` reads
   `serverStart` off the action and calls it; the class also names
   `serverStop`. They are how every client learns the beam is on or off.
   Single player never calls them; `start()` and Net.toAll cover it there.

8. ~~**Hotbar icon**~~ **Answered (2026-09-24, from the item script):** the
   phaser has **no** `AttachmentType`, so vanilla's hotbar never draws it and
   the 32x32 rule doesn't apply. Its icon stays **64x64**, like every other
   non-blade icon here.

---

## 9. Phases

Each phase ends with the checks green, a mutation pass one at a time, and a
line in this file saying what was done.

0. **Verify-first.** Section 8, answered and written down. No code.
1. **The sound. Done 2026-09-24** (section 6): the lower pulse, the loop and
   its tails, declared; the author judges them by ear.
2. **The model and icon. Done 2026-09-24** (section 4): generated, rebuilt,
   baked, fitted to vanilla's M9, `WeaponSprite = TrekPhaserModel`, icon at
   64x64 vetted against the set. Two mutations, both caught: a wrong model
   name, and the texture missing from disk.
3. **The beam renderer. Done 2026-09-24**: `TREK_PhaserFX.lua`, drawn to the
   sheet's recipe, with the light at the cut and a grace timer so a lost
   "beam off" can't leave a beam burning. Bolts on every phaser shot.
4. **Trees. Done 2026-09-24.** The action, the server side, the relay, the loop sound, the
   noise, the sandbox option. `tests/test_multiplayer.py`: single player and
   server plus two clients. The tree is gone on **every** client, the
   non-shooter got "beam on" and "beam off", a client can't fell a tree
   directly, out of range is refused, and a phaser not in hand is refused.
5. **Doors. Done 2026-09-24, and the override removed.** The same, plus double and garage doors, barricades, locked,
   key-locked and padlocked doors all falling alike, and the safehouse
   refusal. A test for each refusal's words (`deny()` reasons must have text).
   **And remove the tricorder's lock override** in the same pass: the menu
   option in `TREK_MedKit.lua`, the `unlock` handler in `TREK_Server.lua`,
   `Med.lockOn` / `Med.unlock` if nothing else uses them, the `unlocked`
   reply, `C.UnlockRange` / `C.UnlockCooldownMs`, their translations and
   tests, and the text in `MEDICAL_SET.md`, `README.md` and `DEV_GUIDE.md`.
   `test_multiplayer.py` already fails on a command with no handler, which
   catches a half-removal.
6. **Other people's bolts.** Probably free: the engine fires the shot event
   for remote players (8.6). Only a two-machine game can confirm it; build a
   relay only if it doesn't.
   **Nineteen mutations, one at a time, all caught** -- one only after a test
   was written for it: `complete()`'s own re-check looked redundant behind
   `isValid()`, and isn't, because a tree or door can go while the beam is on
   it (somebody else gets there first). That is *two guards that cover each
   other*, answered with a test that removes the target mid-cut.
7. **Docs.** This file becomes the working guide; failure signatures and
   *Current state* in `DEV_GUIDE.md`; the README's feature list.

---

## 10. Decisions for the author

| Question | Options | Recommendation |
|---|---|---|
| Does cutting cost anything? | Free (the phaser is infinite today) / the phaser's own charge / the **ship's** energy (`ENERGY.md`) | **Free for now**, like the rest of the phaser. Revisit if `ENERGY.md` gets a hand-phaser cell. |
| Doors: break or open? | Destroy like a sledgehammer / burn the lock and leave it open | **Destroy.** Decided by the author (2026-09-24): a persistent beam defeats any lock, and the door is broken open. |
| The tricorder's lock override | Remove it / keep it | **Remove it.** The author: nothing unlocks doors and a tricorder wouldn't. Phase 5 does it. |
| Safehouse doors on a server | Refuse / allow | **Refuse** a safehouse that isn't yours; possibly a sandbox switch. |
| Anything else cuttable? | Doors and trees only / + windows / + walls, fences | **Doors and trees.** Walls on a server are a griefing tool. |
| Stun and kill settings | One setting / a toggle (stun knocks down, kill as now) | **Later.** Out of scope for this pass, and worth its own doc. |
| Model route | Generated / procedural / found | **Generated** (TRELLIS v2 from a Gemini concept), rebuilt and repainted by `tools/bake_phaser.py`. Done. |

---

## 11. What will bite you

Carried over from `DEV_GUIDE.md` before it can happen again:

- **A weapon model outside `module Base` draws nothing.** The log names the
  model block as a mesh path.
- **An imported mesh faces its camera and has no author.** Check yaw, fit and
  size in one render.
- **A 64x64 icon on a hotbar item spills into the next slot.** 32x32.
- **A client that changes the world is a bug on every server**, even when
  single player looks perfect. The tree and the door go in `complete()`.
- **An action whose `new` stores a parameter under another name** reaches the
  server as nil and is silently invalid.
- **A sound that loops needs a guaranteed stop.** Stop it on `beam off`, on
  `stop()`, on death, on unequip, and on a timeout. A hum that never ends is
  the audible form of *present, drawn and inert*.
- **A bright beam vanishes on a pale roof.** Give it the dark edge and check
  the sheet.
