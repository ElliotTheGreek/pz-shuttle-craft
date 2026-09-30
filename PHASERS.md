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
- **It holsters** (since 2026-09-27): `AttachmentType = Holster`, so it rides
  in the Starfleet holster and in every vanilla pistol holster. The phaser
  rifle and the alien arms run on this same machinery; `ARMOURY.md` is theirs.
- **Every shot is a visible bolt**: a short orange beam from the emitter to
  whatever it hit, or to the end of its range, with a low *zap* rather than a
  gunshot.
- **Right-click a tree → *Cut down with phaser*.** The phaser is drawn from a
  pocket if it isn't in hand, the player walks closer if they're more than
  `C.PhaserCutRange` (5) tiles away, and a steady beam with a hum and a glow
  at the cut fells the tree in about three seconds, logs, stump and all.
- **Right-click a stump, a rock or a bush → *Clear stump / rock / bush with
  phaser*** (since 2026-09-30), so wild ground can be cleared to build on.
  About a second for a bush, a second and a half for a stump, two for a
  rock, and it is gone with **nothing left behind**. *Rock* is a boulder
  (all of it, across the one, two or four squares it covers, which vanilla
  cannot shift at all), an ore deposit, or a stone lying on the ground.
  *Bush* is a wild bush or a hedge. Each right-click queues one, as
  vanilla's axe does.
- **Right-click a door → *Cut through with phaser*.** About two seconds, and
  the door is gone: key-locked, padlocked, double doors (every leaf), garage
  doors, and the barricades nailed across it. **No lock is ever consulted**,
  because the door stops being there. Nothing else in the mod gets through a
  lock; the tricorder's lock override was removed on the same day.
- **Everybody nearby sees the beam and hears the hum**, in single player,
  co-op and on a dedicated server.
- **Refused, with the reason shown in the menu:** a door, stump, rock or
  bush in somebody else's safehouse, and anything the server's sandbox
  switches off.

It deliberately does **not** cut walls, floors (a rock floor included) or
windows, nor anything a player built. That's the
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
| Tests | `tests/test_multiplayer.py`: `phaser()`, `phaser_multiplayer()`, `phaser_clearing()`, `phaser_clearing_mp()`, `armoury()`, and `medical()`'s check that a tricorder opens nothing |
| Which weapons this machinery serves, and which cut | `TREK_Config.lua`, `C.EnergyWeapons` (`ARMOURY.md` 5) |

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
                     or  PC.clear(player, obj, kind)   (stump, rock, bush)
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

### Clearing ground

A stump, a rock or a bush is found by vanilla's own tests, never a list of
ours, so what the phaser clears is what the game itself calls these things:

| Kind | What counts (`PC.kindOf`) | Vanilla's own route |
|---|---|---|
| `stump` | `obj:isStump()`: `CustomName` Stump, Small Stump or Tree Stump | *Remove Stump*, `ISPickAxeGroundCoverItem` |
| `rock` | a `boulders_` or `crafting_ore_` sprite (the two prefixes `IsoObject.isOres()` tests), **unless it is `solidfloor`**; or a stone by `CustomName` (`C.PhaserStones`, GroundCoverItems' stones) | *Remove Ore*, *Remove Ground Item*; **none at all for a `Boulder`** |
| `bush` | the `canBeCut` flag, or `CustomName` Bush or Hedge | *Remove Bush*, `ISRemoveBush` |

- **Only plain objects.** An `IsoThumpable` (anything a player built) or a
  world item is never a stump, rock or bush, whatever its picture.
- **The world change is `transmitRemoveItemFromSquare`**, where vanilla's
  pickaxe and bush actions end. A rock goes with every piece of its sprite
  grid (`PC.parts`, `getSpriteGridObjectsIncludingSelf`), and the menu
  offers one boulder once, however many of its squares the click names.
- **Nothing is dropped.** Vanilla hands back stones, twigs and a scrap of
  wood; a phaser vaporises. A player who wants the stone picks it up
  first.
- **The sandbox:** *Trees and ground* (value 2) clears as well as fells;
  only doors are held back, since nothing on the ground is a lock.
- **The safehouse rule covers all three**, as it covers doors. Trees are
  still not refused for it, as they never were.

`PC.refusal` is the one list of reasons, each an `IGUI_TREK_Phaser*` key:
nothing there (`NoTarget`), the sandbox (`CutOff`), no cutting weapon in
either hand, the phaser or the phaser rifle, never a disruptor (`NotHeld`), a different level or beyond range (`TooFar`), and anything but a
tree in a safehouse the player isn't a member of (`Safehouse`). A reason the server
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
`C.PhaserClearTime` (per kind), `C.PhaserStones` (which ground stones count),
`C.PhaserCutNoise`, `C.PhaserCutNoiseEvery`. The server measures the range
from its own copy of the player's position, with a 0.75-tile allowance.

**What may be cut.** The sandbox option *Phaser cutting* (Trees, doors and
ground; Trees and ground; Off) through `C.phaserCutting()` and `PC.allowed(kind)`. To add a
new kind, three places change:
- `PC.kindOf` has to recognise it (by vanilla's own test for the thing, and
  after the `IsoThumpable` guard if it is ground);
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

**The icon** is rendered from the mesh, three-quarter view, brighter than the
in-game preview, with a one-pixel dark outline like its neighbours. It is
**32x32** since the phaser holsters: the hotbar draws an attachable item's
icon assuming 32 (`tests/test_assets.py`). A 64 is still written to
`media/ui/`.

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
8. **The phaser's `AttachmentType` is `Holster`**, vanilla's pistols' own
   (since 2026-09-27; `ARMOURY.md` 3). Before that it had none and fitted no
   holster.
9. **Stumps, rocks and bushes** (read 2026-09-30). `IsoObject.isStump()` is
   the tile's `CustomName` being Stump, Small Stump or Tree Stump.
   `isOres()` is the sprite name starting `boulders_` or `crafting_ore_`,
   and the `boulders_` sheet also holds rock floors (40-47, 56-63,
   `solidfloor`). Vanilla's world menu (`ISWorldObjectContextMenuLogic`,
   in Java) offers *Remove Stump* for `isStump`, *Remove Ore* for
   `square:getOre()` (ironOre, copperOre, FlintBoulder, LimestoneBoulder),
   *Remove Ground Item* for the GroundCoverItems names, and *Remove Bush* for
   `canBeCut`. A plain `Boulder` (boulders_0-7 and 16-35, `solidtrans`,
   `BlocksPlacement`) is none of those: **vanilla has no way to remove one.**
   Every vanilla removal ends in `transmitRemoveItemFromSquare`.
10. **`getSpriteGridObjectsIncludingSelf(list)`** clears the list, then walks
   the squares the object's `IsoSpriteGrid` covers and collects its pieces;
   an object in no grid answers itself (bci 9-23). The sledgehammer's
   destroy cursor calls it with `ArrayList.new()` (in `server/`), which is
   the proof both are reachable.

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

**`phaser_clearing()`**, single player, through the menu: a stump, a 1x1
and a 2x2 boulder, ore, a stone, a bush and a hedge are offered and cleared
with nothing left on the ground; a rock floor, a log, a houseplant and a
player-built thumpable wearing a boulder's sprite are not offered; a 2x2
boulder is one option and all four pieces go; *Trees and ground* clears,
*Off* refuses in the menu and in the action; a bush in a stranger's
safehouse is greyed with its reason and refused; each kind takes its
`C.PhaserClearTime`, less than a tree.

**`phaser_clearing_mp()`**: the server clears a whole boulder and it goes on
both clients, the cutter's client edits nothing, and a client with no
phaser in hand is refused.

For these the sim learned `isStump`, tile flags, sprite grids (`SIM.grid`)
and `ArrayList`. **Fifteen mutations, one at a time, all caught**; one only
after a test was written for the thumpable guard. A second floor check in
`PC.isRock` was deleted rather than tested, because it and the `solidfloor`
flag covered each other.

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

- **Clearing ground: played 2026-09-30**, the author: "it works well". Before that: The engine
  facts are read (section 5, 9 and 10). What only the game can show: that
  wild bushes carry `canBeCut` (their sheets are not in `tools/_catalog`, so
  nothing here could read them), and that a 2x2 boulder's pieces really go
  together.
- **Other people's bolts.** The bytecode says the shot event fires for remote
  shooters on each client; only a two-player game can confirm it. Build a
  relay only if it doesn't.
- **Holsters: done** (2026-09-27, `ARMOURY.md` 3). The author chose vanilla's
  holsters plus a Starfleet one. It is `Holster`, not `HolsterSmall`: that is
  what vanilla's pistols carry, and it reaches the hip, left, shoulder and
  double holsters. It does not reach the ankle holster, which only takes
  `HolsterSmall`.
- **The cutting pose** (`BlowTorch`) and **where the beam leaves the hand**
  (`C.PhaserHandZ`, `C.PhaserHandAhead`) have not been commented on.
- **Cutting costs nothing**, like the rest of the phaser. If `ENERGY.md` ever
  gives a hand phaser a cell, cutting is the natural thing to charge for.
- **Stun and kill settings** are not built. The author does not want a stun
  setting (2026-09-27).
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

**Charged by the server in multiplayer (1.10.1).** The hit anti-cheat reads
the server's copy of a weapon and kicks after two shots it thinks were fired
empty ("PlayerHitZombiePacket: not enough ammo"). The charge used to be made
only on the player's machine, so the server's copy ran dry and a player was
kicked for firing. `TREK_PhaserCharge` (shared) holds the charging;
`TREK_PhaserServer` runs it on every player's energy weapons four times a
second and sends each one it changed to its holder (`syncHandWeaponFields`,
`syncItemFields`). The player's own sweep still keeps the copy they fire from
full between passes. `phaser_charge_mp()` checks it.
