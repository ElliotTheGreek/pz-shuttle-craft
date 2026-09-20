# Roadmap

What the Shuttlecraft mod has, and what comes next, in order.

`README.md` says what the mod does. `DESIGN.md` says how to change the ship.
`DEV_GUIDE.md` says how to work on it without breaking it — **read its "Rules
that exist because they were broken" before starting anything below.**
`MULTIPLAYER.md` is the client/server design every feature must follow: the
server owns the ship and the world, a client only asks, and nothing may depend
on admin rights, `-debug`, or one particular PC.

---

## 📌 Pinned: the in-game session waiting to happen

**Set up and ready; nobody has played it yet.** The dedicated server world
`trektest2` was created and configured on 2026-09-20 and is the place to do
this. Restart it with:

```sh
PZ="$USERPROFILE/Zomboid/PZ-Worlds.ps1"
powershell -File "$PZ" start trektest2     # join at 127.0.0.1:16261
powershell -File "$PZ" stop
```

Its settings, all deliberate: `Mods=TrekShuttleDev`,
`Map=TrekShuttle;Muldraugh, KY` (the template omits the mod's map — without it
the cabin grows grass and zombies), `WaterShut = 1` so the mains are **off**
and the fixtures' own water stores are actually tested, and
`AntiCheatSpeed = 2` so the transporter's charge limit is live.

**Already confirmed from the server log**, and both were new:

```
[TREK] ship authority ready (server, v1.3.0, build 12):
       landed=false built=false rev=0 owner=nil, beams limited=true
[TREK] void map 'TrekShuttle' is loaded
```

The void map loads on a dedicated server, and the charge limiter read
`AntiCheatSpeed` correctly. Neither had been seen off this developer's single
player before.

### Solo, one client on the dedicated server

1. **Beam up — does cell (96,40) actually stream?** The map loading is only the
   precondition. This is the one MEDIUM-HIGH confidence rating in the whole
   design; everything else is HIGH.
2. **19 containers with their loot.** The drinks are in the **counter at 5,0**,
   not the oven — revision 12, so this only holds on a world made after it.
3. **Water with the mains off.** `TREK_Water()` reports capacity and `hasWater`.
4. **Four fast beams** → *"the transporter is recharging"*, not a kick.
5. **The phaser** fires and stays charged.
6. **Photon torpedoes.** Confirmed working in single player — drawn, detonating
   on arrival, burning buildings down. What a **server** adds is the split:
   the blast is server-side and the projectile is drawn client-side from one
   `torpedoLaunched`, so watch that the thing you see crossing the ground and
   the thing that explodes are in the same place. Fire is synced by the
   engine's own packet. `TrekShuttle.TorpedoFire = 2` drops the fire and keeps
   the weapon if a server wants that.
7. **She flies under a real client/server split** — up, level, down.
8. **Shields** — the `isRemoteZombie()` path is live here in a way single
   player never exercises, even with one client.
9. **The medical set.** Newest and entirely unproven: a hypospray dose and a
   regenerator pass that must both leave a bite alone, a cut closed with no
   bandage, the health panel at doctor level, the sensor sweep in front of a
   real horde, and the lock override on a house door and then on a padlock.
   Revision 15, so a world made before today will not have the items in its
   sick bay.

### Needs the second machine (Steam Deck on the LAN, 192.168.39.182)

*(Numbering continues from the solo list above.)*

The Deck needs `Zomboid/mods/TrekShuttle/` **copied to it by hand**:
`TrekShuttleDev` is a local mod, `WorkshopItems=` is empty, and a server cannot
push a non-Workshop mod to a client. Redo the copy after any code change.

10. Loot one player takes disappears for the other.
11. `TrekShuttle.Access = 2` — a stranger refused, then added to the crew.
12. **A shuttle in the air seen from the other machine.** The wire format
    carries height and each client re-derives the level from its own copy of
    the plane; the simulated two-client test agrees, but the engine's half
    (`clientUpdateVehiclePos` writing `setZ(0)`, then `BaseVehicle.update()`
    recomputing) has only been reasoned about.
13. Speed set at one helm reaching a pilot at another.
14. **A torpedo fired by one player, seen and heard by the other**, and the
    fire it starts appearing on both machines. The projectile is drawn by each
    client from one `torpedoLaunched`, and the fire is synced by the engine's
    own `StartFire` packet — so this should need nothing of ours, which is
    exactly the kind of claim that wants checking.
15. **A lock opened by one player, seen by the other**, and a medical scan
    requested from one machine and accepted on the other. Neither has any
    code of ours behind the packet: the lock rides `obj:sync()` and the scan
    rides the engine's own consent events, which is exactly the kind of claim
    that wants checking.

Watch it with a tight filter — a broad one matches every frame of every Java
stack trace:

```sh
tail -F -n 0 "/c/Users/Arcade/Zomboid/server-console.txt" \
  | grep -E --line-buffered "\[TREK\] (WARN|cabin|shuttle|beam|no room)|is not loaded"
```

---

## Where we are — 1.3.0 (dev build, confirmed in single player)

### Foundations — 1.0

- **The hull.** A 3×5-tile world model (`TREK_Shuttle.x`), generated by
  `tools/gen_shuttle.py`, set down on any clear ground.
- **Landing.** A sliced footprint search finds clear ground near a chosen site
  without locking the game, and beams the player back aboard if it gives up.
- **The transporter.** Beam up from anywhere, down to where you came from or
  anywhere on the map.
- **The cabin.** Generated at runtime in an unused cell (96,40).
- **The phaser.** A sidearm kept charged, unjammed and unworn.
- **Ghost sweep.** Hulls left behind where the ship used to be are cleared when
  their ground next loads.

### The interior — 1.2

- **BuildingEd-authored cabin**, read at runtime from `TREK_InteriorLayout.lua`:
  helm consoles and viewscreen forward, galley to port, eight lockers to
  starboard, berth aft.
- **19 containers stocked by weight** to over half their capacity, including the
  phaser locker. Confirmed in game.
- **The LCARS helm console** (`TREK_Helm.lua`): shields, course by map click or
  crosshair, logged positions, take her down. Works with a controller and the
  Steam Deck. Confirmed in game.
- **Galley food**: ration pack, gagh, leola root stew, plomeek soup, jumja stick,
  with Gemini icons vetted at 32px. Confirmed in game.
- **"THIS WAS YOUR AWAY MISSION"** replaces the death title card. Confirmed.

### Multiplayer — 1.3

**Confirmed in single player** (2026-09-17): beam up, cabin, helm, landing,
hatch, black void outside — and the vehicle shuttle, driven and flown. Dedicated
server: loads cleanly, sandbox options and transporter charges read correctly;
**not yet played on with two people.**

- **The server owns the ship.** Ship state, cabin build, loot, water and the hull
  live on the server (`server/TREK/`); clients ask through validated commands
  (`TREK_Net`) and see the same ship. One code path for single player, hosted
  co-op and dedicated servers.
- **One shared ship.** Sandbox option *Who may use the shuttle*: everyone, or
  owner and crew (crew managed from the aboard menu).
- **Transporter charges.** On a server whose speed anti-cheat kicks or bans, 3
  beams with one back every 150 s, refused in lore instead of a kick.
- **Shields** push only the zombies each client simulates.
- **Water that survives the mains shutoff** — each fixture gets its own water
  store.
- **Black void outside the cabin.** The mod ships a map (`media/maps/TrekShuttle`)
  of 25 empty cells around the cabin, so the world generator never grows grass,
  trees or zombies there — the Fifth-Wheel RV's technique, generated by
  `tools/gen_void_map.py`. Dedicated servers add `Map=TrekShuttle;Muldraugh, KY`.
- **The shuttle is a vehicle**, with four doorless seats, driven like a truck —
  and flown. Hands-on flight had held the pilot's *body* in mid-air (pilots
  died), outlived their death, and would have been kicked by the anti-cheat on
  any server; the ship is the thing that moves now, and the engine's own vehicle
  code does the moving. See below and `PILOTING.md`.
- **`tests/test_multiplayer.py`** runs the real Lua as single player and as a
  server with two clients over a simulated network, with chunk streaming delay
  and gravity. It caught the arrival fall and a Kahlua-missing `next` only after
  they had been seen in game, and now fails on both.

Bugs found in game during 1.3, each now covered by a test: Kahlua has no `next`
or `math.huge`; the arrival hold only set height, so a player fell four floors
while the cabin loaded; `AntiCheatSpeed` is an enum option (`getOption`, not
`getInteger`); and a dead-vehicle check built on a call that throws out of Java
dumped 2932 stack traces in one session, which is what a black screen looks
like from the inside.

The 2026-09-18 session added five more, all fixed: an unregistered
`ColorReference` that **stopped any world loading**; a weapon model in the
wrong module drawing nothing in hand; beaming up without leaving the vehicle
seat, which left vanilla's inventory walking a null vehicle every frame for 829
stack traces; and the bat'leth's size and icon, both corrected on 2026-09-20
and both still unverified.

**Before publishing 1.3 to the Workshop:** a two-player session on the
dedicated server — the shared cabin, loot, crew access, charges, and a shuttle
in the air seen from the other machine.

---

## Piloting — done, and flying in single player

Confirmed in game, 2026-09-17. The landed shuttle is a vehicle with four
doorless seats; from the driver's seat the radial menu takes her up, climbs,
dives and sets her down, and in between you simply **drive** her. The helm sets
the top speed. The crew can go aft to the cabin in flight and come back, and
she waits where they left her.

**She flies by driving, on an invisible floor the mod lays at altitude.** That
is not a trick chosen for fun: build 42 zeroes a vehicle's z every tick and
restores it only where a floor exists underneath, so a ship lifted by its
physics body alone flies in Bullet and is drawn on the road, bulldozing fences,
at z 0 on every other player's screen. `PILOTING.md` has the bytecode, the
reasoning, and the dozen rules the evening in the game produced.

What that evening cost, all of it now covered by mutation-checked tests: a log
flood that blacked the screen (a dead-vehicle probe built on a call that throws
out of Java, on a timer); a radial-menu hook that could never run, so flight
had no way in at all; the tidy-up sweeping the floor out from under the ship
one second after take-off; climbing dropping her because the old level was
lifted before she was on the new one; speed steps that all clamped to the same
number; and a trail of black squares that turned out to be shadows outliving
floors that had genuinely been removed.

**Still to prove:** two players. The wire format carries height and remote
clients should re-derive the level from their own copy of the plane, but that
is reasoning, not evidence.

### Still to come with flight

- **Photon torpedoes** — built; see below and `PHOTON_TORPEDOS.md`. Outstanding:
  the controller reticle, and a session in game.
- **A viewscreen** in the cockpit, if flying from the helm ever earns one.

## Photon torpedoes — done, confirmed in game

Hold right mouse to aim, left click to fire, from the driver's seat in the air.
A cooldown, not ammunition.

**The phrase "an explosion that does not set the street on fire" above was
read the wrong way round**, and it cost the feature its entire visible half for
three commits. It meant fire as an intended weapon effect; it was taken to mean
no fire at all. Since build 42 has no separate explosion effect — *the fire and
the smoke are what you see* — suppressing the fire left a weapon that killed in
silence. A comment and a test were both holding that in place, both accurate
about the engine and both wrong about the goal. `DEV_GUIDE.md` has it under
*A guard is only as good as the goal it was written from*.

What it does now:

- **It burns.** `FireStartingChance = 60` — a per-square density, so about
  three squares in five of the blast ignite — with a guaranteed fire ring 3
  tiles beyond the blast and smoke out to 9. `IsoGridSquare.Burn()` destroys
  structures, so a torpedo fired at a house takes the house.
- **You watch it go.** The torpedo is drawn crossing the ground with a light
  riding on it and a fading trail, in screen space via `isoToScreenX/Y`, so it
  places nothing in the world and can strand nothing behind it. There is no
  explosion or flame tile in the tileset to have done it any other way.
- **It arrives before it explodes.** The blast used to happen on the frame the
  trigger was pulled. It is queued with a flight time now and detonated by the
  server on arrival; the cooldown still starts at launch.
- **`TrekShuttle.TorpedoFire`** lets a server owner have *Full* or *Blast only*
  — the fire removed, the weapon kept. `ServerOptions.noFire`, safehouses and
  non-PvP zones are already respected by the engine without any code of ours.
- **`TorpedoMinRange` went 4 → 12**, because the blast reaches 7 and the fire
  ring reaches 10, and the pilot has to land somewhere.

**Confirmed in game 2026-09-20**, in single player: the torpedo is drawn
crossing the ground, it detonates where it lands, it starts fires, the fires
spread and burn buildings down, and what is in the blast dies. Chance 60 with
a fire ring of 3 is the right amount of weapon — the author's word was "super
fun" — and neither the spread nor the framerate needed backing off.

Still unproven: **two players**, and the **controller reticle**, which is not
built. `PHOTON_TORPEDOS.md` is the guide to working on any of it.

## Galley drinks — done, confirmed in game

Four drinks, each a `fluid` block plus a vessel item carrying a
`FluidContainer`. In the galley's drinks cabinet (`C.Loot.drinks`).

They were carried into the game on 2026-09-18 and **the world would not load**:
`ColorReference = ClearBlue` is not a registered colour, `getColor` throws, and
that aborts script loading entirely. Fixed (`DeepSkyBlue`; `SaddleBrown` was
equally unproven and is now `Cola`), and `test_assets.py` now validates against
the colours vanilla's own fluids use.

**Confirmed in game 2026-09-20**, with one fault: they were stocked into the
**oven**. The layout entry hung `loot = "drinks"` on `appliances_cooking_01_40`
— the lower half of a two-tile stove, `CustomName = Oven` — while the comment
beside it called it a cabinet. Every static check passed, because the sprite
exists, is genuinely a container, and is genuinely where the `.tbx` puts it;
only the choice of fitting was wrong, and that is the half the code owns.
Moved to the counter at 5,0, which the deck plan can also draw. Revision 12,
so **it reaches new worlds only** — see *Never restock an existing container*.

| Drink | Vessel | Colour | Notes |
|---|---|---|---|
| **Raktajino** | vanilla `Mug` | `Cola` | fatigue -25, more than twice vanilla coffee |
| **Earl Grey** | vanilla `MugWhite` | `Peru` | stress -35, morale -40 |
| **Romulan ale** | vanilla `CuracaoBottle` | `DeepSkyBlue` | `alcohol = 0.25` |
| **Bloodwine** | vanilla `RedWineBottle` | `DarkRed` | `alcohol = 0.4`, vanilla's ceiling |

The verify-first question is answered, and the `ThirstChange` fallback is not
needed:

- **A mod may declare `fluid` blocks in its own `media/scripts`.** Vanilla's
  all live under `scripts/generated/`, which made it look generated-only;
  `FluidDefinitionScript` tracks `isVanilla`/`modId`, `FluidType` has a
  `Modded` constant for exactly this, and a Workshop mod ships fluids this way.
- **A modded fluid is not reachable as `FluidType.<name>`.** `FluidType` is a
  fixed Java enum and every modded fluid is `FluidType.Modded`. From Lua the
  handle is `Fluid.Get("<name>")`; `addFluid` has `(String, float)`,
  `(FluidType, float)` and `(Fluid, float)` overloads and vanilla uses all three.
- **`ColorReference` must be a colour vanilla's own fluids use.** An unknown
  one is **fatal** -- `FluidDefinitionScript.getColor` throws, script loading
  aborts, and the world will not load at all. `ClearBlue` cost a crash on the
  first launch. Reading names out of `Colors.class` is what let it through: a
  string in a class file is not a registered name.
- **`IconFluidMask` is optional** — 61 of vanilla's 133 fluid containers ship
  without one. It is not used here: how it composites has only been reasoned
  about, so the liquid is painted into the icon instead, which is right either
  way. Adding masks is a polish pass for after somebody has watched one render.
- Fluid names go in `Translate/EN/Fluids.json` — its own category file.

## Blades — all four built, and all four seen in game

**The in-hand path is open.** The claim that a custom `WeaponSprite` needs a
rigged attachment set was wrong, and it had quietly ruled this whole section
out. A weapon model is a **plain static mesh** — no bones, no skinning, no
animation files. `WeaponSprite` names a `model` block exactly as `StaticModel`
does, and the swing is `SwingAnim`, a name borrowed from the game's own global
set (`Bat`, `Stab`, `Heavy`, `Spear`, `Throw`, `Rifle`, `Handgun`, `Stone`,
`Shove` — `tests/test_assets.py` now checks both names resolve).

Weapon meshes are **Y-up**, the opposite of the hull and the helm — and three
more things the first in-game session settled, all in `DEV_GUIDE.md`:

- **The model block must be in `module Base`.** `WeaponSprite` does not resolve
  inside the mod's own module the way `StaticModel` does, so the bat'leth drew
  nothing in hand until it moved to `media/scripts/trekweapons.txt`.
- **The mesh's own dimensions are its size**; `WeaponLength` is a reach stat and
  scales nothing. Judge the **bounding box**, not the span constant, against
  vanilla — where every weapon is a thin vertical line and the widest mesh in
  the game is 0.123 across.
- **An attachable item needs a 32×32 icon.** Vanilla's hotbar places it at
  `slotX + texWidth/2` in a 60px slot, so a 64×64 icon runs into the next slot.

| Weapon | SwingAnim | Categories | Notes |
|---|---|---|---|
| Weapon | SwingAnim | Categories | Mesh | Notes |
|---|---|---|---|---|
| **Bat'leth** | `Bat` | `base:longblade` | 0.369 x 0.187 | `gen_batleth.py`, two-handed, `AttachmentType = BigBlade`. **Confirmed in game.** |
| **Mek'leth** | `Bat` | `base:longblade` | 0.102 x 0.440 | `gen_mekleth.py`, `AttachmentType = Sword`, off `ShortSword`. **Confirmed in game.** |
| **Lirpa** | `Spear` | `base:spear` | 0.101 x 0.800 | `gen_lirpa.py`, two-handed, `AttachmentType = Shovel`, off `SpearCrafted` (`MinRange = 0.98`). **Confirmed in game.** |
| **Ushaan-tor** | `Stab` | `base:smallblade` | 0.087 x 0.260 | `gen_ushaantor.py`, `AttachmentType = Knife`, off `HuntingKnife`, keeps its `CloseKillMove = Jaw_Stab`. **Confirmed in game.** |

**Seen in game 2026-09-20**, in a fresh world: all four draw correctly in the
locker and in hand, at the right size, with icons that sit in their own hotbar
slots. The sizes above are therefore settled and the bracket the mesh has to
sit in is now proven twice over rather than reasoned about.

All four are in `C.Loot.weapons` — the whole rack together, because one alien
weapon among the pistols reads as a souvenir and four read as an armoury.
Revision 13, so **new worlds only** (see *Never restock an existing container*).

The three new ones share `tools/bladekit.py`: a caller hands it a list of
cross-sections up the Y axis and it extrudes the silhouette, builds the shared
texture sheet, and renders the icon from the finished mesh. The bat'leth keeps
its own generator -- its crescent is authored in polar coordinates and is
genuinely a different problem.

`tools/meshbbox.py` is new and is why the sizes above can be stated at all: it
measures any `.x` mesh, ours or the game's. The bracket a weapon has to sit in
is now a measurement rather than a remembered number -- vanilla's widest weapon
mesh is the canoe paddle at 0.123 across, a machete is 0.335 long, a katana
0.627, a hunting knife 0.276, and spears run 0.72 to 0.92.

**What three renders cost, and each was invisible in the source:**

- the mek'leth's first draft was a straight bellied blade and rendered as a
  **machete**, which this game has four of. What makes it a mek'leth is that
  the whole blade leans forward and the back goes concave near the top;
- the ushaan-tor's hook was built by tilting the back edge over the last two
  sections, which does not curl anything -- it cuts a corner off. A hook is
  the *centreline* swinging sideways while the blade thins;
- the lirpa's counterweight came out **wooden**, because the shaft asked for a
  wood recolour of a texture strip the weight was also using.

**And the icons had to be tilted**, which the contact sheet caught and nothing
else would have: rendered upright, the lirpa filled **11%** of its icon -- four
pixels of content in a 32px frame -- the mek'leth 22% and the ushaan-tor 30%,
against 60% for the bat'leth and 65-82% for the food. On the diagonal, the way
vanilla draws every blade, they are 71%, 57% and 49%. The lirpa also needed its
counterweight lightened to gunmetal: blued steel is (48,54,64) on a (39,39,39)
inventory panel and simply vanished, taking the double-ended silhouette --
the one thing that identifies a lirpa -- with it.

**Size and icon: settled, 2026-09-20.** It first drew 0.531 across — wider than
a baseball bat is long, spanning the character hip to hip — with a 64×64 icon
that overlapped the belt in the next hotbar slot. The mesh is 0.369 now and the
icon 32×32, and both are confirmed in game.

**Still to settle, in game, and it is the same question for all four:**

1. **The `attachment` blocks**, which they all ship without. Both
   (`Bip01_Prop2` for the hand, `world` for the ground) are optional and the
   engine falls back to a default placement, but the six offset numbers can
   only honestly be chosen by looking at the thing in a fist. Vanilla's `Katana`
   model block is the baseline to start from. Where a blade *hangs* when slung
   is not on the weapon model at all — `AttachmentType` is routed through
   `ISHotbarAttachDefinition.lua` and `AttachedLocations.lua` to an attachment
   on the **character** model.

   **This is the next hard stop on the roadmap**, and it is a hard stop because
   no static check can answer it: six offsets per weapon, twenty-four in all,
   each judged by looking. Doing all four in one session is the point of having
   built the other three first.

2. **Whether they read at all in hand**, which is a different question from
   whether they read in an icon. The renders and the contact sheet are the
   best that can be done away from the game.

## The medical set — built, and not yet seen in game

All four are in, with their icons, three generated sounds, an LCARS contact
plot and a server-side lock override. **`MEDICAL_SET.md` is the dev guide
for it** -- how each instrument works, how to change one, the engine facts
not to re-derive, and what will bite you -- in the shape `PHOTON_TORPEDOS.md`
and `PILOTING.md` use.

- **Hypospray.** One dose treats bleeding, deep wounds, an infected cut,
  burns, fractures, pain, stiffness and tissue damage on every body part at
  once. **It does not cure a bite and it does not clear the zombie
  infection** — that is the EMH's, and it is the only reason the EMH is worth
  building. Six doses, kept in the item's own mod data; the **ship** replicates
  more while you are aboard and nothing does in the field, so the limit is a
  decision (push on, or go home) rather than a delay. A dose is never spent
  on somebody who is already well.
- **Dermal regenerator.** Skin, and only skin: one pass closes lacerations,
  scratches, deep wounds, bleeding and burns, dissolves the stitches and takes
  off the dressing that was holding them together — **no bandages needed**.
  Free and unlimited, because the hypospray already owns the ration economy
  and a second item with the same one is the same item twice. What stops it
  replacing the hypospray is scope: it does nothing for an infected cut, pain,
  stiffness or a fracture, and an infected wound is still what kills you. It
  refuses a wound with glass or a bullet still in it (skin does not close over
  a shard, and tweezers keep a reason to exist) and will not strip the dressing
  off a bitten limb.
- **Medical tricorder.** Vanilla's `ISHealthPanel` with `doctorLevel` set to
  10, so every Doctor-gated readout opens — on yourself from the item's menu,
  or on another player through the engine's own consent prompt. Never
  `ISHealthPanel.cheat`, which is `false or getDebug()` and otherwise
  admin-only.
- **Tricorder.** A sliced sensor sweep of the cell's zombies, drawn as a
  contact plot with three range bands, and a lock override that asks the
  server because a lock is world state. **It will not open a padlock and it
  will not open anything inside somebody else's safehouse** — both are another
  player's property, and a mod that picks them is a griefing tool on every
  server that installs it.

All four are in `C.Loot.medical`, and the forward sick-bay locker carries one
of each outright. Revision 15, so **new worlds only**.

**What the pass cost, and it was one line from shipping:** `BodyPart
.RestoreToFullHealth()` is the obvious way to mend a limb and its bytecode
clears the **bite** as well. Nothing in the game would have reported it — the
hypospray would simply have been better than intended and the EMH pointless.
`DEV_GUIDE.md` has it under *A convenience method is a bundle of writes
somebody else chose*.

Two things `MEDICAL_SET.md` used to claim turned out to be wrong, both in the
mod's favour: `ISHealthPanel` **is** an `ISPanelJoypad` already, so the
controller question needed no work at all; and the lock setters' own sync is
skipped when it *is* the server, so the authority has to call `obj:sync()`
itself rather than relying on the engine.

**One design question left for the author:** the medical tricorder reports
everything a Doctor 10 sees, which does **not** include the zombie infection.
That was scoped deliberately — the EMH is meant to be the thing that knows —
but a tricorder that announced "you are infected" with no cure in reach would
be a different and much harsher item. Worth deciding before the EMH.

## Then: ship systems

- **Replicator** — a galley fixture with a searchable UI that makes any item.
  On a server the item is created by the server. **Medium–Hard.**
- **EMH** — a wall switch that brings up a static model of the Doctor, a dialogue
  panel, full diagnosis and treatment, infinite supplies, and **the only cure for
  zombie infection** (decided). Treatment runs on the server. **Medium–Hard.**

---

## Suggested order

**Publishing moved to the end (decided 2026-09-20).** The Workshop release now
happens once the roadmap below is done, not after 1.3. So nothing here is
racing a release, and the ground rule that nothing ships un-played applies to
the whole list at once rather than to each version.

1. **Photon torpedoes** — built, including the fire, the projectile and the
   sandbox option, and confirmed in game. **Outstanding: the controller.**
   `aimPoint()` keeps a virtual cursor for a joypad but nothing moves it, so on
   a Steam Deck the reticle sits at the centre of the screen and does not
   track. The roadmap always said "a reticle the stick moves for controllers";
   that half is still not built, and it is now the only piece of the original
   spec missing.
2. **Blades** — the bat'leth's hand and ground attachments, which need it
   looked at in a fist, then the mek'leth, lirpa and ushaan-tor off the same
   pipeline.
3. **Medical tricorder, hypospray, tricorder** — built (2026-09-20), and the
   first thing to carry into the game. `MEDICAL_SET.md`'s last section is the
   list.
4. **Replicator, then EMH.**
5. **Publish.**

Running alongside all of it: **the two-player session** (pinned below). It is
no longer a release blocker, but every feature above is one more thing that
will need proving with two people when it does happen, so the longer it waits
the bigger that session gets.

---

## How art gets made

**All icons and images are generated and vetted with the FlowDot Gemini Image
toolkit** (`gemini-image`):

| Step | Tool | Purpose |
|---|---|---|
| Create | `generate-image` | Text → image from a written brief |
| Refine | `edit-image` | One image + instruction → revised image |
| Combine | `compose-images` | Two images → one |
| **Vet** | `analyze-image` | Image + instruction → written critique |

Every asset is vetted **at the size it is shown** (icons at 32×32, the seat
chart at its in-game panel size): does it read, is the silhouette distinct, is
it Star Trek without copying a frame of the show, is the background genuinely
transparent. Icons are generated on flat magenta and keyed by
`tools/key_icon.py`. Every file is then checked by `tests/test_assets.py`.

**Open question:** the helm emblem was judged a near-exact copy of the
Picard-era Starfleet insignia. Keep it, or draw something more distinct — the
author's call.

---

## Ground rules for everything above

- **Multiplayer first.** Decide what runs on the server and what on the client
  before writing it (MULTIPLAYER.md), and extend `tests/test_multiplayer.py`.
- **Verify every new engine call** — `tools/pzapi.py` for whether it exists and
  is public, `tools/javarefs.py` for role or debug gates, and a grep of vanilla
  Lua for a real call site. Only Kahlua's standard library exists (no `next`).
- **Add the log line that proves it worked.**
- **Bump `C.BuildRev`** for anything that places or changes an object in the
  cabin.
- **Nothing ships to the Workshop until it has been seen in game** — and, for
  anything shared, seen with two players.
