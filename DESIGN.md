# Designing the Shuttlecraft

How to change the shape, layout and contents of the ship, and the rules the
engine imposes on all of it.

Read [The five constraints](#the-five-constraints) before changing anything.
Four of them were learned by breaking the TARDIS mod this one is built on;
the fifth is this mod's own, and it is the one that makes a shuttle a
different problem from a police box.

---

## The shape of the thing

The cabin is **generated at runtime**, not shipped as a map. Nothing here was
made in TileZed; the mod writes floors, walls and furniture into empty world
cells the first time a player is aboard.

One compartment, one storey, at **z 4** in cell **96,40** — clear of the
vanilla map (it ends at cell x 77), of the Fifth-Wheel RV interior at 85,40,
and of the TARDIS mod's six deck footprints running east from 92,40.

The hull is 14 squares across by 22 fore and aft, with the bow cut back six
squares and the stern three. That is 254 deck squares — roughly half a TARDIS
deck, which is the point: this is a shuttle.

```
    01234567890123
  0       ..           oy 0 is the bow
  1      V.V.
  2     ..H...
  ...
 21    ..eeee..        oy 21 is the stern
```

`python tests/test_layout.py` prints the whole thing with every fitting on it.

---

## The five constraints

### 1. Nothing can be built into a chunk that has not streamed in

Chunks only load around a **player**. The cabin is somewhere nobody ever goes,
so until someone is standing there its chunks do not exist — and
`getOrCreateGridSquare` on an absent chunk returns an *orphan* square with no
chunk behind it. The first engine call that touches one (`addFloor`,
`AddTileObject`) throws out of Java.

So the order is always **move the player in first, then build**:

- `U.chunkLoaded(x, y, z)` gates everything; `U.square(..., create=true)`
  returns `nil` rather than an orphan.
- `B.cabinReady()` probes the corners, the centre and the pad.
- `Core.beginArrival` puts the player on the pad, then holds them —
  invulnerable, not falling — until `B.cabinCurrent()` is true *and* the pad
  square demonstrably has a floor.
- If that never happens, `Core.ejectToOutside` puts them back on real ground.

**Never build at a location no player is at.**

And the corollary, which is easier to miss: **you cannot un-build there
either.** Anything that reaches for a remembered position — to remove, check
or repair it — gets `nil` back when that chunk is not loaded, and `nil` is not
"there is nothing there". It means "ask again later".

The hull is the worked example. Landing lifts the ship from wherever it was,
but a new site is by definition nowhere near where the ship has been, so at
that moment the old chunk is never loaded. Treating that failure as "the old
hull is gone" would leave a second shuttle standing after every flight.
`Core.removeHullAt` returns a *reason* rather than a bare boolean for exactly
this, and a position it could not reach goes into `s.ghosts` to be cleared
when the world next streams that spot in.

### 2. A shuttle needs room, and room cannot be checked from the helm

This is the constraint the TARDIS never had. A police box occupies one tile
and can materialise in a hallway; the shuttle needs its whole 3×5 footprint,
and the ground it is aimed at is in a chunk that has not loaded yet.

The consequence is that **landing cannot be a decision, it has to be a
process**:

1. Set a course at the helm. Nothing moves. Nothing is checked, because
   nothing *can* be checked.
2. Take her down. The player is beamed to the site — which is what makes its
   chunks stream in — and a tick job then searches for somewhere the hull
   fits.
3. If it finds one, the ship comes in and the player is put at the foot of the
   ramp. If it does not, the player is beamed **back aboard** with the reason.

Step 3's failure branch is not politeness, it is the whole design. Doing it
the other way round — check, then move — is impossible; doing it as "move,
then fail" would strand the player on foot wherever the ship could not follow.

Two details that are easy to get wrong here:

- **The player's own square must be exempt.** The hull is five tiles long, so
  anybody calling it down in front of them is standing inside the footprint,
  and anybody beamed to a destination for the ship to follow is standing in
  the middle of it. Without `Core.exemptFor(player)` the ship refuses every
  landing anyone ever orders. `Core.land` then steps them clear as it arrives.
- **"unloaded" is not a refusal.** `Core.roomToLand` reports it only when
  *every* blocked square was unloaded. A wall inside an area that is otherwise
  still streaming in is a real "no", and answering "wait and see" to it would
  leave the landing job retrying against a site that will never work.

### 3. The landing search must not run whole every tick

The search covers a 49×49 area and asks about all fifteen footprint squares at
each position: roughly **thirty-six thousand square lookups for one pass**.
Run per frame, that is not slow, it is a hard lock.

So the job keeps a cursor and examines `SITES_PER_TICK` (48) positions per
tick, wrapping round when it runs out — because ground that was not loaded on
the first pass may well be by the third. One cheap `getFloor()` probe rejects
most candidates before the fifteen-square test is worth running at all.

The same reasoning made `C.footprintOffsets()` memoise its table: it is walked
inside that loop, and rebuilding a fifteen-entry table thousands of times a
second is pure garbage.

### 4. Unmapped cells grow wilderness

The engine generates procedural forest in cells with no map data, so an
untreated cabin reads as a hut standing in a wood. Two passes handle it:

- `clearFootprint` strips the hull footprint before anything is placed.
- `clearSurroundings` strips a `ClearMargin` (24) ring down to *nothing* — no
  objects, no floor — which renders as black void, the look the Fifth-Wheel RV
  interior has. It runs at the cabin's own level **and at z 0**, because that
  is where the trees actually grow.

`U.clearSquare` deliberately preserves anything the mod tagged and anything
lying on the ground, so both passes are safe to repeat as chunks stream in
late.

### 5. A wrong engine method name is not a quiet failure

Calling a method that does not exist throws out of Java, and the engine dumps
a full stack trace **per call**. Inside a per-square loop that is hundreds of
dumps, which freezes the game hard enough to look like a crash.

Two defences, and both matter:

- **Check the name first**: `python tools/pzapi.py zombie.iso.IsoGridSquare stairs`
- **Batch anything repeated**: `U.batch(label)` returns a callable that stops
  after its first failure, logs one warning, and lets the pass continue.

```lua
local join = U.batch("light.lamppost")
for ... do join(function() cell:addLamppost(x, y, z, r, g, b, 8) end) end
```

`U.try` is **not** a substitute. It silences the *Lua* warning after the first
failure but keeps calling, and the engine keeps dumping a Java stack trace
every time. `U.try` is for a call that happens once; `U.batch` is for a call
that repeats.

There is a second edge to this constraint, and the phaser is where it bit.
`U.try` returns `nil` both when a call fails *and* when the call legitimately
returns nothing — so a probe that answers "nil means clear" reads a thrown
exception as clear ground to land a ship on. `squareIsClear` answers `"ok"`
rather than `nil` for exactly that reason.

---

## Changing the design

### Furnishing the cabin

Each area has one function in `TREK_Build.lua`: `furnishHelm`, `furnishGalley`,
`furnishSickBay`, `furnishQuarters`, `furnishCargo`, `furnishPhasers`.

```lua
local function furnishGalley()
    local S = C.Sprites
    fit(0, 8,  S.sink.W,    "sink")
    fit(0, 9,  S.counter.W, "counter", C.Loot.cookware, 6)
    line(S.locker.W, 1, 9, 0, 1, 4,
         { loot = C.Loot.food, amount = 12, tag = "pantry" })
end
```

`fit(ox, oy, sprite, tag, loot, amount)` places one object.
`line(sprite, ox, oy, dx, dy, count, opts)` places a run of them.
`place(pieceName, ox, oy, tag)` places a multi-tile piece from `C.Pieces`.

| key | meaning |
|-----|---------|
| `loot` | a list from `C.Loot`; makes the object a container and stocks it |
| `amount` | items per container |
| `tag` | mod-data tag — **required for anything that should survive a rebuild** |

**Tag everything you place.** `U.clearSquare` keeps tagged objects and destroys
untagged ones, so an untagged shelf is wiped on the next rebuild. Tags also
drive behaviour: `sink`, `shower` and `toilet` are refilled with water every
ten in-game minutes, and the self-test counts them by tag.

Offsets run `0..CabinW` by `0..CabinL` from the bow. **The hull tapers**, so an
offset that is fine amidships is in open space forward of about oy 6 or aft of
about oy 18. A placement that misses simply does not happen and reports
nothing, which is why `tests/test_layout.py` parses every call out of the
source and checks it.

`C.Landing` and its clearance ring are refused by every placement helper, so
nothing can be put down where a player materialises.

### One object per square

`fit`, `line` and `place` all `claim()` the square they are about to use, and
refuse one that is already taken. This exists because overlaps do not fail:
`U.addObject` only looks for its own sprite, so a deckhead lamp dropped where
a crate already stands simply stacks, both are drawn, and which one the player
can actually reach is a matter of draw order. Claiming turns that into one
line in the log at build time — and `test_layout.py` catches it before the
game is ever launched.

This is why the lighting pass runs **after** the furnishing: the lamps take
whatever squares are left rather than being stacked on top of the cargo.

### Loot lists

Lists live in `C.Loot` in `TREK_Config.lua`. Every id must exist in the
installed build:

```sh
python tools/pzcatalog.py items "^Canned"      # find ids
python tools/pzcatalog.py check Base.Pills,Base.Bandage
```

`U.stock` keeps a **rolling cursor per list**, so consecutive containers
continue through it instead of all starting at the top. Without it every
medical cabinet holds an identical handful and most of the list never appears.
`tests/test_stock.py` guards it.

Long lists spread further than short ones. If you want fuller coverage, make
the list longer or the containers more numerous — not `amount` bigger.

`U.stockEach` is the other tool: it puts one of everything in and then reads
the container back, returning what did not land. Use it where coverage has to
be *proved* rather than hoped for — the phaser locker uses it, because "there
are four phasers in there" is a claim the mod should be able to check.

### Choosing sprites

Sprite names come from the installed build; a wrong one fails **silently**,
leaving an empty square and no error anywhere.

```sh
python tools/pzcatalog.py build                    # once, after a game update
python tools/pzcatalog.py sprites container medicine
python tools/pzcatalog.py sprites name industry_01
```

The sets this mod leans on, and why:

| set | used for |
|---|---|
| `industry_01` | hull walls (`MaterialType: Metal_Light`) and the diamond-plate deck |
| `security_01` | the standing helm consoles and the wall-mounted viewscreens |
| `appliances_com_01` | the operations terminals |
| `location_community_medical_01` | the biobed and the wide medical cabinets (capacity 30) |
| `fixtures_counters_01` | steel galley counters — a metal hull, not somebody's kitchen |
| `location_military_generic_01` | the cargo crates (capacity 50) |

Wall tilesets follow a pattern: index 0 is the **west** face, 1 the **north**
face, 2 the corner post. Multi-tile furniture is consecutive and its halves
carry a `SpriteGridPos`.

`tests/test_assets.py` checks every sprite name and item id in the Lua against
the catalogue, so a typo fails before the game ever runs.

### Changing the hull shape

`C.CabinW`, `C.CabinL`, `C.NoseCut` and `C.TailCut` are the whole shape.

**Project Zomboid has no diagonal wall sprites.** Walls only ever sit on the
north or west edge of a square, so a smoothly curved hull is not available at
any size. What *is* available is a stepped chamfer — cut the corners off and
let the wall follow the steps — which at this scale and the game's camera
angle reads clearly as a bow.

Walls are **derived from the floor plan**, not hard-coded: `buildWalls` walks
every in-shape square and puts a wall wherever its neighbour is outside. So a
new shape is a change to `C.inShape` and nothing else — but every furnishing
offset will need revisiting, and `test_layout.py` will tell you which.

If you change the size, bump `C.BuildRev`.

### Changing how much ground it needs

`C.Footprint = { w = 3, h = 5 }` is the whole of it, and it must be kept in
step **by hand** with `HULL_W` / `HULL_L` in `tools/gen_shuttle.py`, which is
how big the model is actually drawn.

Nothing in the engine ties those together: a world model is drawn from one
square and simply overhangs the rest, so the game will happily draw a five-tile
hull that only claims one square, or claim fifteen squares for a model one tile
wide. `tests/test_layout.py` compares the two numbers and fails if they drift.

Bigger footprints are dramatically harder to land. Fifteen squares already
rules out most of a suburban street.

### Multi-tile furniture

A bed covers several squares, and **which half goes where is not guessable** —
it comes from the tileset's `SpriteGridPos`. Declare pieces in `C.Pieces` as
`{sprite, dx, dy}`:

```lua
biobedS = { { "location_community_medical_01_17", 0, 0 },
            { "location_community_medical_01_16", 0, 1 } },
```

then place with `place("biobedS", ox, oy, "biobed")`, which refuses if any
square it needs is outside the hull, on the pad, or already claimed.

Getting these backwards is what made the TARDIS's bunks look mismatched: every
bed had its foot laid where its head belonged. `tests/test_layout.py` checks
every declared offset against `SpriteGridPos` and that all halves face the same
way.

---

## The transporter

`TREK_Transport.lua`. Two entry points and one recovery path.

- `T.beamUp(player)` — writes down where they were standing, then a delayed
  job puts them on the pad through `Core.beginArrival`.
- `T.beamDown(player, dest)` — back to the recorded spot, or to a destination.
- `T.recoverAboard(player, message)` — immediate, no ceremony, used when a
  landing has failed.

Three decisions worth keeping:

**A beam is a job, not a teleport.** `C.BeamDelay` (90 ticks, about a second
and a half) exists because an instant snap reads as a debug command and a short
dematerialisation reads as a transporter. It also gives the halo note time to
be seen.

**Beaming does not care where the ship is.** When the shuttle is not landed it
is overhead, which is not a position at all, and the pad reaches you either
way. The hatch is the part that needs the ship to be somewhere; the menu hides
"step outside" when it is not.

**A beam-down needs one square, a landing needs fifteen.** `T.spotNear`
spirals `C.BeamScatter` (6) squares outward from the target and gives up
rather than putting anybody inside a wall — the square you left may have a
zombie standing on it by the time you come back.

**Beaming up cancels a landing in progress.** Otherwise both jobs run: the ship
comes down at the destination and immediately teleports the player back out of
the cabin to stand beside it.

---

## The phaser

An ordinary build 42 firearm plus one slow tick that puts the charge, the
chambered round and the condition back. Everything tunable is in
`TREK_Config.lua`:

| constant | meaning |
|---|---|
| `C.PhaserItem` | the full id, for spawning and placing |
| `C.PhaserType` | the bare type, which is what the engine's inventory search compares |
| `C.PhaserInfiniteAmmo` | put the charge back |
| `C.PhaserNeverJams` | clear a jam |
| `C.PhaserNeverWears` | put the condition back |
| `C.PhaserInterval` | ticks between sweeps |
| `C.PhaserRack`, `C.PhaserCount` | where the locker sits and how many are in it |

Four things decided the shape of it.

**The ammunition type is 9mm, and it had to be.** A phaser ought to have its
own power cell. It cannot: `AmmoType = base:bullets_9mm` resolves through
`AmmoType.registerBase` in Java, and there is no script syntax anywhere in
build 42 that lets a mod add one. Grep the whole of `media/scripts` for
`bullets_9mm` and it appears only ever as the *value* of an `AmmoType` line,
never as a definition — the string is registered in the jar. A made-up id would
resolve to nothing and the weapon would silently refuse to fire. So the phaser
nominally chambers 9mm, and because the charge is restored far faster than it
can be spent, none of the player's own ammunition is ever drawn on.
`tests/test_assets.py` checks that whatever `AmmoType` the item names is one a
vanilla weapon also uses, so this cannot quietly rot.

**The top-up is a sweep, not a hook.** There is no reliable "the player fired"
event to hang it on, and a phaser in a bag should be as full as one in your
hand when you draw it. `getAllTypeRecurse` walks sub-containers and both hands
are checked separately, because an equipped item is not always in the container
listing and a phaser you are holding is the one that most needs to be full.

**`getAllTypeRecurse`, deliberately, and not `getItemsFromFullType(type,
true)`.** Both exist and both return an `ArrayList`. The second one's boolean
is undocumented, and guessing at an undocumented flag is precisely how a
feature ends up silently doing nothing at all. The method whose name states
what it does is the one to call. It compares the **bare** type, so it is handed
`C.PhaserType` and the results are filtered on the full id afterwards.

**It is quiet.** `SoundRadius = 12` against a pistol's 100. A weapon with
unlimited charge that also brought the whole street down on you would be no
gift at all, and "quieter than a firearm" is most of what a phaser is for.

The in-hand model is vanilla (`WeaponSprite = Handgun03`). A custom one needs a
rigged attachment set rather than a static mesh, which is a different pipeline
from the world models — see the TARDIS mod's notes on what happens when you
assume otherwise. The inventory icon is the mod's own.

---

## The ship is lived in

**A rebuild must never touch what is already in a container.** Once a locker
exists it is the player's: what they eat stays eaten, what they take stays
taken, and what they put back stays where they put it.

`U.addContainer` returns a second value saying whether it created the container
just now, and `fit`/`line` stock only when it did. Without that gate a rebuild
does not merely refill a locker — it stocks it *again*, piling a second helping
on top of the first, so loot multiplies with every revision bump.

The corollary is that **changing a loot list does not change a cabin that
already exists.** New containers get the new list; old ones keep what they
have. That is correct for play and inconvenient for design, hence:

```lua
TREK_Rebuild()      -- from the debug console, standing aboard
```

Tears the cabin back to bare ground — containers and contents included — and
regenerates it fully stocked. It only works with the player aboard, because
only then are its chunks loaded.

`C.DevRestock = true` does the same globally for every rebuild. It is off by
default and should stay off outside design work.

## Build revisions

`C.BuildRev` is stamped into the cabin as it is built. Raising it makes the
cabin rebuild the next time a player is aboard — lazily, on arrival. Rebuilds
repair structure (floors, walls, lighting, the void margin) and preserve tagged
furniture, container contents and dropped items.

Bump it when **generation** changes. It will not restock anything.

**Moving the cabin is not a rebuild — it is a migration.** Its old geometry
stays where it was and its container contents do not travel.

---

## Assets

The hull and the helm console are **world models** (`.x` meshes plus textures),
not tile sprites — a custom tile would need a TileZed-packed texture pack.
Everything is generated by script; no binary asset is hand-authored.

```sh
python tools/gen_shuttle.py TrekShuttle/42     # hull texture, mesh, icon
python tools/gen_helm.py    TrekShuttle/42     # helm texture and mesh
python tools/gen_phaser.py  TrekShuttle/42     # phaser inventory icon
python tools/gen_poster.py  TrekShuttle/42     # the mods-screen poster
```

An item's `Icon = X` resolves to `media/textures/Item_X.png`, and a missing one
shows as a blank square in the inventory and reports nothing anywhere.
`tests/test_assets.py` checks every icon a mod item names, every mesh and
texture a model names, and every `TrekShuttle.*` id the Lua refers to.

Check the result **without launching the game**:

```sh
python tools/preview_model.py TrekShuttle/42/media/models_X/TREK_Shuttle.x \
       TrekShuttle/42/media/textures/TREK_Shuttle.png /tmp/preview.png -35
```

`tools/preview_model.py` is a small software renderer — mesh parser, z-buffer,
per-pixel texture sampling — that draws the model at roughly the game's camera
angle. The last argument is the yaw, so both flanks can be checked. **Use it.**
Four separate faults in the hull were found and fixed here before the game was
ever involved.

Five things to know about the meshes:

- **Y is up.** Project Zomboid world models are Y-up; authoring Z-up lays the
  hull on its side. `MeshBuilder(up_axis=...)` handles the swap, and
  `preview_model.py` swaps back so previews stay upright.
- **1 unit is 1 tile**, with `scale = 1.0` in `media/scripts/trekshuttle.txt`.
- **The frame auto-fits.** The previewer used to assume a one-tile model and a
  five-tile hull simply ran off every edge, which made it useless for judging
  anything.
- **`MeshBuilder.quad` maps its four points to fixed texture corners**, in the
  order bottom-left, bottom-right, top-right, top-left. Reversing the winding
  to turn a normal around also turns the artwork **upside down** — which is
  what it did to the registry on the starboard flank. Pass the normal
  explicitly and keep the point order.
- **One texture on two opposite faces cannot be right on both.** It can be
  upright on both, or at the same physical end on both, never both at once. The
  flanks therefore have their own atlas regions and `mirror_region` draws the
  second as a mirror of the first. That was worth a few kilobytes of atlas.

A related lesson from the first pass: the nacelles originally ran the full
length of the hull at mid height, which put them directly over the registry and
the cockpit glazing. Neither could ever be seen. **Render it and look** — the
geometry was correct and the result was still wrong.

---

## The loop

```sh
python tools/luacheck.py TrekShuttle/42/media/lua   # parses every file
python tests/test_assets.py                         # sprites, items, icons, keys
python tests/test_stock.py                          # loot spreads across its list
python tests/test_layout.py                         # floor plan + fittings
sh tools/deploy.sh                                  # copy into Zomboid/mods
```

Then launch with `-debug`. On a **fresh** world the self-test runs itself and
writes `TREK-TEST` lines to `Zomboid/console.txt`; on a world where the ship is
already in use it stays out of the way, and `TREK_SelfTest()` from the debug
console forces it.

```sh
sh tools/readtest.sh
```

The self-test is a step machine, not a straight function, because most steps
have to wait for the world. It beams up, inspects the cabin — floors, fittings
by tag, water, phasers, nothing overhead — then beams down, lands the ship,
boards it through the hatch, steps out and recalls it.

**Lua version note.** The game runs Kahlua, a Lua 5.1 dialect where `unpack` is
a global. `tools/luacheck.py` and the tests use Lua 5.5, which moved it to
`table.unpack`; the harness stubs it back. Mod code should use the 5.1 spelling.

---

## Where things live

| File | Holds |
|------|-------|
| `TREK_Config.lua` | All layout constants, sprites, loot lists. Start here. |
| `TREK_Util.lua` | Safe engine wrappers, state, coordinates, clearing, stocking |
| `TREK_Build.lua` | Cabin construction and furnishing |
| `TREK_Core.lua` | The hull, landing room, the hatch, arrival, water, the field |
| `TREK_Transport.lua` | The transporter: beam up, beam down, recovery |
| `TREK_Travel.lua` | The helm: courses, bookmarks, the landing search, map markers |
| `TREK_Phaser.lua` | Keeping phasers charged |
| `TREK_Menu.lua` | Right-click menus |
| `TREK_SelfTest.lua` | In-game step machine |

Almost every design change is a change to `TREK_Config.lua` plus one `furnish`
function.

---

## Rules of thumb

- Verify an engine method with `tools/pzapi.py` before calling it — and prefer
  the overload whose name says what it does over the one with an undocumented
  flag.
- Wrap anything repeated per-square in `U.batch`.
- Never let `nil` from `U.try` mean "yes". Return a sentinel.
- Tag every object you place, or a rebuild eats it.
- Never build where no player is standing.
- Exempt the player's own square from the footprint check, or nothing ever
  lands.
- Never let a failed landing leave somebody on foot; beam them back aboard.
- Slice any search that touches thousands of squares across ticks.
- Keep `C.Footprint` and `gen_shuttle.py`'s `HULL_W`/`HULL_L` in step.
- Bump `C.BuildRev` when generation changes; write a migration when geometry
  *moves*.
- Run the four static checks before deploying — they are seconds, and a game
  round-trip is minutes.
