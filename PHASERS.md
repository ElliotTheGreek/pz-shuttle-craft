# Phasers

The working guide to the phaser: what it does, where each piece lives, how to
change it, the engine facts it rests on, and what will bite you. It follows the
shape of `PHOTON_TORPEDOS.md` and `REPLICATOR.md`.

**Seen working in game, 2026-09-24:** the model in the hand and on the ground,
the lower firing pulse, the beam, shot bolts, and cutting trees and doors. The
author's verdict: "it works great". **Not yet seen:** two players (whether
other people's bolts show; see *Open*), and nobody has yet commented on the
cutting pose.

`DEV_GUIDE.md`'s *Rules that exist because they were broken* and
`MULTIPLAYER.md` apply to every line. The four that matter most here: **the
server changes the world**; **a timed action is rebuilt on the server by its
name and its parameters**; **a vanilla call site proves reachability, never
correctness**; and **render it and look**.

---

## 1. What a player gets

- **Four phasers** in the armoury locker, with the mod's own model and icon.
  The charge never runs down, they never jam and they never wear out, and
  they are far quieter than a firearm.
- **Every shot is a visible bolt**: a short orange beam from the emitter to
  whatever it hit, or to the end of its range, with a low *zap* rather than a
  gunshot.
- **Right-click a tree → *Cut down with phaser*.** The phaser is drawn from a
  pocket if it isn't in hand, the player walks closer if they're more than
  `C.PhaserCutRange` (5) tiles away, and a steady beam with a hum and a glow
  at the cut fells the tree in about three seconds, logs, stump and all.
- **Right-click a door → *Cut through with phaser*.** About two seconds, and
  the door is gone: key-locked, padlocked, double doors (every leaf), garage
  doors, and the barricades nailed across it. **No lock is ever consulted**,
  because the door stops being there. Nothing else in the mod gets through a
  lock; the tricorder's lock override was removed on the same day.
- **Everybody nearby sees the beam and hears the hum**, in single player,
  co-op and on a dedicated server.
- **Refused, with the reason shown in the menu:** a door in somebody else's
  safehouse, and anything the server's sandbox switches off.

It deliberately does **not** cut walls, floors or windows. That's the
sledgehammer's job, and on a server it would be a griefing tool.

---

## 2. Where everything lives

| What | Where |
|---|---|
| The rules, the world changes, the timed action `TREKPhaserCut` | `media/lua/shared/TREK/TREK_PhaserCut.lua` |
| The beam, the bolts, the hum, the light; `TREK_PhaserFX()` | `media/lua/client/TREK/TREK_PhaserFX.lua` |
| The charge sweep, and the right-click menu; `TREK_Phaser()` | `media/lua/client/TREK/TREK_Phaser.lua` |
| Every number | `TREK_Config.lua`, section *Phasers* |
| The item | `media/scripts/trekshuttle.txt`, `item TrekPhaser` |
| The model block `TrekPhaserModel` | `media/scripts/trekweapons.txt` (**`module Base`**) |
| The four sounds | `trekshuttle.txt` beside the item; `.wav`s in `media/sound/` |
| Mesh, texture, icon | `media/models_X/weapons/firearm/TREK_Phaser.x`, `media/textures/weapons/firearm/TREK_Phaser.png`, `media/textures/Item_TREK_Phaser.png` |
| Beam strip and spark | `media/ui/TREK_PhaserBeam.png`, `media/ui/TREK_PhaserSpark.png` |
| Sandbox *Phaser cutting* | `sandbox-options.txt`, `Translate/EN/Sandbox.json` |
| Menu words and refusals | `Translate/EN/IG_UI.json`, `IGUI_TREK_Phaser*` |
| The model's source | `tools/assets/trek_phaser/` (`SOURCE.txt`, the bake); concepts in `design/art/weapons/phaser/` |
| Generators | `tools/bake_phaser.py` (once per source), `tools/gen_phaser.py` (mesh, icon, sounds, sheet), `tools/gen_phaser_beam.py` (beam art, sheet) |
| Review sheets | `design/art/weapons/phaser/phaser_sheet.png`, `design/art/ui/phaser_beam_sheet.png` |
| Tests | `tests/test_multiplayer.py`: `phaser()`, `phaser_multiplayer()`, and `medical()`'s check that a tricorder opens nothing |

---

## 3. How it works

### A cut

```
client   right-click -> TREK.Phaser.fillWorldMenu (OnFillWorldObjectContextMenu)
           offered to anybody carrying a phaser, on every tree and door the
           click could mean; refused ones are GREYED with the reason
         -> P.onCut: draw the phaser (ISWorldObjectContextMenu.equip),
            walk up if beyond C.PhaserCutRange (luautils.walkAdj),
            queue TREKPhaserCut:new(player, x, y, z, kind)
         -> start(): BlowTorch pose, phaser as the hand model, local beam on

server   rebuilds TREKPhaserCut by class name, from new()'s parameter names
         isValid(): PC.refusal on the SERVER's copy of everything
         serverStart(): Net.toAll("phaserBeam", on)     -> every client's beam
         update(): face the target; noise every C.PhaserCutNoiseEvery ticks
         complete(): looks the target up again and refuses again, then
                     tree:toppleTree(player)  or  PC.breach(player, door)
                     Net.toAll("phaserBeam", off)
         serverStop(): Net.toAll("phaserBeam", off)     -> a cancelled cut

clients  phaserBeam on  -> FX.beamOn: hum, start tail, light, overlay
         phaserBeam off -> FX.beamOff: hum stopped, end tail, light out
         nothing heard for C.PhaserBeamGraceMs -> FX.service drops it anyway
```

Three things about that are the design, not the incidental detail:

- **The target travels as coordinates and a kind**, never as the object. The
  server looks it up on its own square, which is the only copy it may believe.
- **`complete()` checks everything again** even though `isValid()` just did.
  A tree or door can go while the beam is on it, when somebody else gets
  there first. Without the re-check `complete()` would try to fell nothing.
- **Single player is the same code.** `serverStart` is never called there;
  `start()` turns the local beam on, and `Net.toAll` runs the client handler
  directly.

`PC.refusal` is the one list of reasons, each an `IGUI_TREK_Phaser*` key:
nothing there (`NoTarget`), the sandbox (`CutOff`), no phaser in either hand
(`NotHeld`), a different level or beyond range (`TooFar`), and a door in a
safehouse the player isn't a member of (`Safehouse`). A reason the server
reaches in `complete()` is sent to the cutter as `phaserRefused` and shown as
a note.

### A shot

`OnWeaponSwingHitPoint(character, weapon)` → `FX.bolt`: a beam from the
emitter straight ahead to `weapon:getMaxRange()`, for `C.PhaserBoltMs`.
`OnWeaponHitCharacter` shortens it to whatever was hit. The engine fires the
shot event for **other players' shots on each client** too (see section 5),
so nothing relays bolts.

### The beam on screen

Drawn in **screen space, placing nothing in the world**, as the torpedo is. It
uses one overlay element for every beam and bolt, and it isn't tied to the
local player's weapon, because other people's beams must show too. Each beam
is drawn exactly as `phaser_beam_sheet.png` was judged:

| Step | What | Constant |
|---|---|---|
| 1 | the strip, a quad from emitter to target, tinted | `C.PhaserTint`, `C.PhaserBeamPx` / zoom |
| 2 | the same strip, **untinted** and thinner, on top | `C.PhaserCorePass`, `C.PhaserCoreAlpha` |
| 3 | a flare at the emitter | `C.PhaserMuzzle` x `C.PhaserSparkPx` / zoom |
| 4 | a spark at the target, and a smaller white one on it | `C.PhaserImpact` (bolts use 0.6 of it) |

- The quad is `ISUIElement:drawTextureAllPoint` with four corners from
  `isoToScreenX/Y`, so it needs no angle arithmetic and no tiling.
- **The emitter is an approximation**: the shooter's position, moved
  `C.PhaserHandAhead` toward the target and raised `C.PhaserHandZ` levels.
  Lua can't reach the hand bone.
- A cutting beam aims `+0.3` of a level above the target's floor.
- **The life is in the Lua**: a shimmer on the width, and one light at the
  cut (`addLamppost`, removed by the handle it returned). Anything baked into
  the strip would stretch with it.
- **The overlay is 1x1 in the corner.** See *What will bite you*; it cost a
  play session.

### The sound

| Sound | What |
|---|---|
| `TREK_PhaserPulse` | the shot: 0.30 s, a 480 → 210 Hz body, a 1.5x partial, a 95 Hz thump and a noise burst |
| `TREK_PhaserBeam` | the cutting hum, `loop = true`: a one-second loop, 196 Hz carrier with 1.5x/2x/3x partials, a 49 Hz growl, a 7 Hz wobble, crackle |
| `TREK_PhaserBeamStart` / `End` | the beam catching and letting go |

**Every machine plays its own**, with `playSoundLocal` on the shooter's
character, when it hears "beam on", and stops it by the handle that call
returned. The cut's noise to zombies is separate: `addSound` at the target,
made by the authority (`C.PhaserCutNoise`).

### The charge

Unchanged from before the rework. `TREK_Phaser.lua` sweeps the local player's
phasers every `C.PhaserInterval` ticks and puts the ammunition, the chambered
round and the condition back. The item nominally chambers `bullets_9mm`,
because a mod can't declare an AmmoType. The sweep outruns any rate of fire,
so none of the player's own 9mm is ever drawn.

---

## 4. Changing it

**Cutting.** `C.PhaserCutRange`, `C.PhaserTreeTime`, `C.PhaserDoorTime`,
`C.PhaserCutNoise`, `C.PhaserCutNoiseEvery`. The server measures the range
from its own copy of the player's position, with a 0.75-tile allowance.

**What may be cut.** The sandbox option *Phaser cutting* (Trees and doors,
Trees only, Off) through `C.phaserCutting()` and `PC.allowed(kind)`. To add a
new kind, three places change:
- `PC.kindOf` has to recognise it;
- `complete()` needs its world change, which must be the engine's own
  authority path, found in the bytecode;
- the menu needs a label key.

Then add a test in `phaser()` that it really goes, and one that a client alone
can't make it go.

**The look of the beam.** Change the constant in `tools/gen_phaser_beam.py`,
re-run it, look at the sheet, and **then** make the same change in
`TREK_Config.lua`. They are deliberately not shared, the torpedo's rule: the
Lua is what runs, the generator is what judges it.

**The sounds.** `tools/gen_phaser.py`, then judge by ear; no test can. **Keep
every frequency in the hum a whole number of hertz**, or the one-second loop
clicks once a second for as long as a tree is being cut. The noise layer is
crossfaded tail into head for the same reason.

**The model.**

```sh
python tools/bake_phaser.py                 # once per new source; pip: trimesh,
                                            # fast_simplification, networkx, scipy,
                                            # scikit-image
python tools/gen_phaser.py TrekShuttle/42   # every build; PIL and numpy only
```

- **Proportions, size, grip fit:** the constants at the top of the bake
  (`LENGTH`, `ACROSS`, the M9 grip numbers), then rebake.
- **Colours:** `PALETTE` in the bake. `DARK` and `LIGHT` classify the
  *source's* brightness; don't tune them for looks.
- **The hand position**, if a fist says it's wrong: move the grip fit in the
  bake. The attachment numbers are Handgun03's and are right for anything
  fitted this way.
- **A new design:** a new Gemini concept, a new TRELLIS run, `SOURCE.txt`
  updated, then rebake. Look at `phaser_sheet.png` after every step. The raw
  GLB is 18 MB and is **not committed** (`.gitignore`); its URL is in
  `SOURCE.txt`, and a normal build never reads it.

**How the model is kept looking good** is a loop, not a prompt. Every change
is judged on a picture at the size the player sees it, drawn by the same
command that builds the asset:
1. the concept in 2D first;
2. the mesh fitted to vanilla, not to taste;
3. the texture repainted per texel in the concept's palette, because flat
   blocks survive 20 pixels and a generator's soft, lit texture doesn't;
4. the sheet, drawn with a z-buffer that culls back faces as the engine
   does: four views, the M9 outlined over the side view, the phaser at 18
   and 26 px over four grounds, and the icon at 64 and 32;
5. the icon against the whole set (`tools/vet_icons.py`);
6. then the game.

**The icon** is rendered from the mesh at 64x64, three-quarter view, brighter
than the in-game preview, with a one-pixel dark outline like its neighbours.
The phaser has no `AttachmentType`, so the hotbar's 32x32 rule doesn't apply.
**If it ever gets one** (for holsters; see *Open*), the icon must become 32x32.

---

## 5. Engine facts, established

Each was read out of the bytecode or vanilla's Lua on 2026-09-24. Don't
re-derive them.

1. **`IsoTree:toppleTree(character)` is a complete fell.** It **returns at
   once on a client** (bci 0-6). On the authority it:
   - removes the tree with `transmitRemoveItemFromSquare`;
   - plays `FallingTree` to everybody;
   - drops the logs through `AddWorldInventoryItem`, which transmits;
   - places the stump.

   It is what `WeaponHit` calls once a tree's damage reaches zero; the phaser
   skips only the counting. `IsoTree` is exposed (vanilla calls `WeaponHit`
   on it), so its public methods are reachable.
2. **A door comes down the sledgehammer's way.** `ISDestroyStuffAction:complete()`'s
   authority path removes the barricades on both sides, then every leaf
   through `buildUtil.getDoubleDoorObjects` / `getGarageDoorObjects`, then
   `transmitRemoveItemFromSquare`. `buildUtil` is in `server/`, which is where
   `complete()` runs. The break sound is `character:playSound("BreakDoor")`,
   as the sledgehammer's.
3. **`drawTextureAllPoint` draws on any four corners**; `DrawTextureAngle`
   only rotates.
4. **`playSoundLocal` is local only** (`emitter.playSoundImpl`) and returns a
   handle `stopOrTriggerSound` takes. `playSound` may go over the network.
5. **The shot event fires for everybody's shots.** `OnWeaponSwingHitPoint`
   (vanilla's `ISReloadWeaponAction.onShoot` listens to it) is fired by the
   engine for the shooter, and by `zombie.network.fields.hit.Player.attack`
   for other players' shots on each client.
6. **A timed action has server hooks.** `NetTimedAction.start` reads
   `serverStart` off the action and calls it; `serverStop` is named beside
   it. Single player calls neither.
7. **"The mouse is over the UI" is geometry.** `UIManager.isOverElement`
   checks visible, then the mouse inside the element's rectangle (bci 23-187).
   It never calls a Lua `isMouseOver`, and while it says yes the world gets no
   right-click and no aiming.
8. **The phaser has no `AttachmentType`**, so it is not a hotbar item and
   fits no holster.

---

## 6. Testing

```sh
TREK_ONLY=phaser,phaser_multiplayer python tests/test_multiplayer.py
```

**`phaser()`**, single player, driven through the right-click menu:
- no phaser, no option;
- a phaser in a pocket is offered, drawn, and cuts;
- the tree goes by `toppleTree`, with the hum started and stopped, both
  tails, and zombie noise;
- the beam is drawn as two strips, glow then white core, ending on the tree,
  with flares; it is gone after its grace period;
- **the overlay never covers the screen** (`SIM.uiUnderMouse`);
- key-locked, padlocked, and double-and-barricaded doors all come down;
- a stranger's safehouse is greyed with its reason and refused by the action;
- out of range walks first, in range doesn't, and the action itself refuses
  twenty tiles;
- *Trees only* and *Off* are honoured;
- a target that vanishes mid-cut is reported, not cut;
- a phaser shot draws a bolt that goes, and a pistol's doesn't.

**`phaser_multiplayer()`**, a server and two clients:
- the server runs the cut, and the tree goes on all three machines;
- the cutter's client edits nothing itself;
- the watcher hears the beam on and off, locally;
- the server refuses a client whose phaser isn't really in hand, and a client
  that didn't know about a safehouse.

**`medical()`** checks that a tricorder offers nothing at a locked door.

`tests/pz_sim.lua` gained, for this:
- trees that topple the way the bytecode says (nothing on a client);
- door leaves and barricades, and `buildUtil`;
- `serverStart` in the rebuilt action;
- settable hands;
- sound handles and `stopOrTriggerSound`;
- recorded beam quads and sparks;
- `SIM.uiUnderMouse`, the engine's hover rule.

**Twenty mutations, run one at a time, all caught.** Two were caught only
after a test was written for them:
- **`complete()`'s re-check.** Two guards covering each other; the answer is
  a test that removes the target mid-cut.
- **A screen-sized overlay.** The simulation couldn't see it until it modelled
  the hover rule.

**In game**, from the debug console:
- `TREK_Phaser()` reports the phasers on you and recharges them;
- `TREK_PhaserFX()` reports how many beams and bolts are burning.

---

## 7. What will bite you

- **A UI element that covers the screen takes the world's mouse away.** The
  first beam overlay was screen-sized. From the first shot on, the player
  could not right-click or aim, nothing was logged, and every test passed.
  Overriding `isMouseOver` in Lua does nothing (section 5.7). Keep the overlay
  1x1, and give any new world-drawing overlay the `SIM.uiUnderMouse` check.
- **A world change on a client is a bug on every server**, even when single
  player looks perfect. Trees and doors change only in `complete()`.
- **An action whose `new` stores a parameter under another name** reaches the
  server as nil and is silently invalid. `new(character, x, y, z, kind)`
  stores exactly `x`, `y`, `z`, `kind`.
- **A loop needs a guaranteed stop.** The hum stops on "beam off", on
  `stop()`, on `perform()`, and on the grace timer. If you add a way for a
  beam to end, make it stop the hum too.
- **A weapon model outside `module Base` draws nothing**, and the log names
  the model block as if it were a mesh path.
- **An image-to-3D mesh is a hollow shell until a picture says otherwise.**
  Rebuild it from a filled volume before decimating (`DEV_GUIDE.md`).
- **One tinted draw has no white middle.** A tint multiplies. The core is a
  second, untinted pass.
- **A bright beam vanishes on a pale roof** without its dark skirt. Look at
  the sheet.

---

## 8. Open

- **Other people's bolts.** The bytecode says the shot event fires for remote
  shooters on each client; only a two-player game can confirm it. Build a
  relay only if it doesn't.
- **Holsters.** `AttachmentType = HolsterSmall` would fit every vanilla
  holster (hip, double, shoulder, ankle), and the icon would then have to be
  32x32. A Starfleet-flavoured alternative is a uniform that provides a hip
  slot through `AttachmentsProvided`. Awaiting the author.
- **The cutting pose** (`BlowTorch`) and **where the beam leaves the hand**
  (`C.PhaserHandZ`, `C.PhaserHandAhead`) have not been commented on.
- **Cutting costs nothing**, like the rest of the phaser. If `ENERGY.md` ever
  gives a hand phaser a cell, cutting is the natural thing to charge for.
- **Stun and kill settings** are not built and deserve their own document.
- **The four blue indicator lights** in the concept did not survive TRELLIS,
  and at held size they would be one pixel. Not painted in.

---

## 9. How it came to be

On the morning of 2026-09-24 the phaser was a vanilla pistol: the M9's model
(`Handgun03`), a shrill 1000 → 420 Hz chirp, and invisible bullets. The
tricorder could talk locks open. The author asked for:
- its own model, made with FlowDot (Gemini and fal);
- a laser you can see;
- a lower sound;
- a beam that stays on a tree or a door until it is felled or broken open;

and ruled that nothing a Starfleet crew carries picks a lock.

**The art came first**, and every fault in it was found on a review sheet, not
in a number:
- the mesh was a hollow shell;
- the first review renderer drew the inside over the skin;
- the model was twice a pistol's width;
- flat colour per face had sawtooth edges;
- the beam had no white core, a grey box on pale roofs, and an arrowhead for
  a spark;
- the icon was the dullest in the set.

`tools/assets/trek_phaser/SOURCE.txt` has the model's provenance.

**Then the behaviour.** The engine questions were answered from the bytecode
before any code was written (section 5). Then came the action, the overlay,
the menu, the sandbox, the tests, and the removal of the tricorder's override.

**Then the first play session found what no test could:** after the first
shot the world stopped taking right-clicks and aiming. The overlay was
screen-sized, and the engine's hover test is geometry. It was fixed and
modelled in the simulation the same hour, and the author's verdict on the
next run was that it works great.
