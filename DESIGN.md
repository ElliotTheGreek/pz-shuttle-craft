# Designing the Shuttlecraft

How to change the shape, layout and contents of the shuttle's cabin, and the
rules the engine imposes on all of it. The Adirondack has her own guide
(`ADIRONDACK.md`); the same constraints apply to her.

Read [The five constraints](#the-five-constraints) before changing anything.
Four of them were learned by breaking the TARDIS mod this one is built on;
the fifth is this mod's own, and it is the one that makes a shuttle a
different problem from a police box.

---

## The shape of the thing

The cabin is **generated at runtime**, not shipped as a map. The mod writes
floors, walls and furniture into an empty world cell the first time a player
is aboard, from a layout authored in BuildingEd.

One compartment, one storey, at **z 4** (`C.CabinZ`) in cell **96,40**
(`C.InteriorCell`), clear of the vanilla map (it ends at cell x 77), of the
Fifth-Wheel RV interior at 85,40, and of the TARDIS mod's decks running east
from 92,40. The Adirondack is in cell 97,40.

**Four squares across by six fore and aft** (`C.CabinW = 3`, `C.CabinL = 5`):
twenty-four squares, against a hull that is fifteen, so the inside and the
outside tell the same story. It was 14x22 and then 6x9 before the refit;
`INTERIOR_REFIT.md` is why it is this size and what is on every square.

```
    0123
  0 TVLA
  1 F*.p
  2 oh.M
  3 wD.H
  4 m*.B
  5 R.@B
```

`python tests/test_layout.py` prints this with its legend and every
container.

---

## The five constraints

### 1. Nothing can be built into a chunk that has not streamed in

Chunks only load around a **player**. The cabin is somewhere nobody ever goes,
so until someone is standing there its chunks do not exist, and
`getOrCreateGridSquare` on an absent chunk returns an *orphan* square with no
chunk behind it. The first engine call that touches one (`addFloor`,
`AddTileObject`) throws out of Java.

So the order is always **move the player in first, then build**:

- `U.chunkLoaded(x, y, z)` gates everything; `U.square(..., create=true)`
  returns `nil` rather than an orphan.
- The arrival puts the player on the pad and holds them there until the
  server reports the cabin is built round them (`cabinReady`), and the pad
  square demonstrably has a floor.
- If that never happens, they are put back on real ground.

**Never build at a location no player is at.**

And the corollary, which is easier to miss: **you cannot un-build there
either.** Anything that reaches for a remembered position (to remove, check
or repair it) gets `nil` back when that chunk is not loaded, and `nil` is not
"there is nothing there". It means "ask again later". A hull left where the
ship used to be goes into `s.ghosts` and is cleared when that ground next
streams in; treating the failure as success is how a second shuttle ends up
standing after every flight.

### 2. A shuttle needs room, and room cannot be checked from the helm

A police box occupies one tile; the shuttle needs its whole 3x5 footprint, and
the ground it is aimed at is in a chunk that has not loaded yet. So **landing
cannot be a decision, it has to be a process**:

1. Set a course at the helm. Nothing moves and nothing is checked, because
   nothing *can* be checked.
2. Take her down. The player is beamed to the site (which is what makes its
   chunks stream in), and a job searches for somewhere the hull fits.
3. If it finds one, the ship comes in and the player is put beside her. If it
   does not, the player is beamed **back aboard** with the reason.

Step 3's failure branch is the whole design. Check-then-move is impossible;
move-then-fail without recovery would strand the player on foot.

Two details that are easy to get wrong:

- **The player's own square must be exempt** (`World.exemptFor`). Anybody
  calling her down in front of them is standing inside the footprint, and
  without the exemption the ship refuses every landing anyone ever orders.
- **"Unloaded" is not a refusal** unless *every* blocked square was unloaded.
  A wall inside an area that is still streaming in is a real "no".

### 3. The landing search must not run whole every tick

The search covers a 49x49 area and asks about all fifteen footprint squares at
each position: about **thirty-six thousand square lookups for one pass**. Run
per frame, that is not slow, it is a hard lock. So the job keeps a cursor and
examines `SITES_PER_TICK` (48) positions per tick, wrapping round, because
ground that was not loaded on the first pass may be by the third. One cheap
`getFloor()` probe rejects most candidates first, and `C.footprintOffsets()`
memoises its table.

### 4. Unmapped cells grow wilderness

The engine generates grass, trees and zombies in any cell with no map data, so
an untreated cabin is a hut standing in a wood. **The answer is a map**: the
mod ships `TrekShuttle/common/media/maps/TrekShuttle`, cells round the cabin
and the Adirondack that are a starfield near either ship and empty beyond
(`tools/gen_void_map.py`). A mapped cell is never generated. **It has to be
under `common/`**: the engine never reads a mod's map from `42/`, and for
every release before 1.9 it did not load (`DEV_GUIDE.md`, *The black outside
the cabin is a map*). A dedicated server lists it: `Map=TrekShuttle;Muldraugh, KY`.

The runtime clearing stays as the fallback for a save whose cells were
generated before the map loaded: `clearSurroundings` strips a `C.ClearMargin`
(24) ring to nothing, at the cabin's level and at z 0. `U.clearSquare` keeps
anything the mod tagged, anything lying on the ground, and the star floors, so
the passes are safe to repeat as chunks stream in.

### 5. A wrong engine method name is not a quiet failure

Calling a method that does not exist throws out of Java, and the engine dumps
a full stack trace **per call**. Inside a per-square loop that is hundreds of
dumps, which freezes the game hard enough to look like a crash.

- **Check the name first**: `python tools/pzapi.py zombie.iso.IsoGridSquare isFree`,
  and `tools/javadis.py` for what it does and under what condition.
- **Batch anything repeated**: `U.batch(label)` returns a callable that stops
  after its first failure, logs one warning, and lets the pass continue.

```lua
local join = U.batch("light.lamppost")
for ... do join(function() cell:addLamppost(x, y, z, r, g, b, 8) end) end
```

`U.try` is **not** a substitute: it silences the Lua warning but keeps calling,
and the engine keeps dumping. And `U.try` returns `nil` both when a call fails
*and* when it legitimately returns nothing, so a probe that answers "nil means
clear" reads a thrown exception as clear ground. `squareIsClear` answers
`"ok"` for exactly that reason.

---

## Changing the design

### Moving or adding furniture

**The interior is authored in BuildingEd**, in
`design/buildinged/TrekShuttle_Interior.tbx`, and read at runtime from
`shared/TREK/TREK_InteriorLayout.lua`. To move a locker, open the map editor,
not the Lua. `DEV_GUIDE.md`, *Changing the interior or what is in it*, is the
step-by-step; in short:

1. Edit the `.tbx` in BuildingEd.
2. `python tools/import_tbx_layout.py` lists every furniture tile it expands,
   and which of them the tileset says are containers.
3. Carry the change into `L.tiles` in `TREK_InteriorLayout.lua`. Geometry
   (`x`, `y`, `sprite`) comes from the `.tbx`; `tag`, `container`, `loot`,
   `special`, `fill` and `cap` are yours.
4. Bump `C.BuildRev`, and run `python tests/test_layout.py`, which fails if the
   Lua and the `.tbx` disagree about containers and prints the deck plan.

Some squares carry **no fitting at all** because a machine owns them: the
replicator at 0,5 (`C.ReplicatorSpot`), the warp core at 1,3
(`C.DilithiumSpot`) and the EMH's station at 3,3 (`C.EmhStation`). Each is a
world model the build stands there, and `test_layout.py` fails if anything is
authored onto one.

**Tag everything you place.** `U.clearSquare` keeps tagged objects and destroys
untagged ones, so an untagged shelf is wiped on the next rebuild. Tags also
drive behaviour: `C.WaterTags` (`sink`) gets water, `television` gets device
data.

**One object per square**, except on purpose. The lamps are placed with
`claim()`, which refuses a square already taken, so a lamp cannot land on a
locker; authored layering (a sink on a counter, the television on its table)
bypasses it deliberately. `test_layout.py` catches anything stacked by
mistake.

### A sprite is not the object the engine builds from it

A fitting built with `IsoObject.new` is an `IsoObject` wearing that sprite:
drawn, and inert. The television is built as an `IsoTelevision` with device
data (`device = "Base.TvWideScreen"` on its layout entry), the oven and the
microwave as `IsoStove`s, and every container gets
`createContainersFromSpriteProperties()` before it is sent. `DEV_GUIDE.md` has
both rules.

### Loot

Lists live in `C.Loot` in `TREK_Config.lua`, and every id must exist in the
installed build:

```sh
python tools/pzcatalog.py items "^Canned"      # find ids
python tools/pzcatalog.py check Base.Pills,Base.Bandage
```

The three lockers hold the mod's own items only (`INTERIOR_REFIT.md` 4), with
the headline items guaranteed by a `special` rule in `TREK_Build.lua` and read
back by `U.stockEach`: `phasers`, `uniforms`, `padds`, `medkit`, `tapes`.
Everything else fills to `C.FillFraction` of the container's own capacity, or
to the entry's `fill` and `cap`. `U.stock` keeps a rolling cursor per list so
neighbouring containers do not all hold the same handful; `tests/test_stock.py`
guards it.

### Choosing sprites

Sprite names come from the installed build; a wrong one fails **silently**,
leaving an empty square and no error anywhere.

```sh
python tools/pzcatalog.py build                    # once, after a game update
python tools/pzcatalog.py sprites container medicine
python tools/pzcatalog.py sprites name industry_01
```

| Set | Used for |
|---|---|
| `industry_01` | hull walls (`MaterialType: Metal_Light`) and the diamond-plate deck |
| `security_01` | the wall-mounted monitors on the bow bulkhead |
| `furniture_storage_02` | the three Starfleet lockers (capacity 40) |
| `furniture_shelving_01` | the tape shelf, a wall shelf that leaves its square as deck |
| `appliances_*`, `fixtures_*` | the galley |
| `location_community_medical_01` | the biobed |
| `location_entertainment_theatre_01` | the crew seat, which blocks only its north edge |

Wall tilesets follow a pattern: index 0 is the **west** face, 1 the **north**
face, 2 the corner post. Multi-tile furniture is consecutive and its halves
carry a `SpriteGridPos`. **Read a tile's properties before choosing it**
(`tools/_catalog/tiles.json`): half the tileset does not block its square, and
`CustomName` is what the player sees when they open it; the galley's drinks
once went into an oven because a comment called it a cabinet. And a
catalogue says what a tile is *for*, never what it looks like: look at it.

`tests/test_assets.py` checks every sprite name and item id in the Lua against
the catalogue.

### Changing the hull shape

`C.CabinW`, `C.CabinL`, `C.NoseCut` and `C.TailCut` are the whole shape (the
cuts are 0 today: the cabin is a plain rectangle).

**Project Zomboid has no diagonal wall sprites.** Walls only ever sit on the
north or west edge of a square, so a curved hull is not available; a stepped
chamfer is.

Walls are **derived from the floor plan**: `buildWalls` walks every in-shape
square and puts a wall wherever its neighbour is outside. A new shape is a
change to `C.inShape` and nothing else, but **moving geometry is a
migration, not a rebuild**. Write the old extent down (`C.LegacyCabin`) so
`B.refitCabin` can clear it, and hand the contents of any deleted container
back on the pad (`DEV_GUIDE.md`, *`U.clearSquare` keeps two things on
purpose*).

### Changing how much ground it needs

`C.Footprint = { w = 3, h = 5 }` is the whole of it, and it must be kept in
step **by hand** with `HULL_W` / `HULL_L` in `tools/gen_shuttle.py` and the
vehicle script's `extents`. Nothing in the engine ties those together.
`tests/test_layout.py` and `tests/test_assets.py` compare them and fail if they
drift.

### Multi-tile furniture

A bed covers several squares, and **which half goes where is not guessable**:
it comes from the tileset's `SpriteGridPos`. Pieces are declared in `C.Pieces`
as `{sprite, dx, dy}`:

```lua
biobedS = { { "location_community_medical_01_17", 0, 0 },
            { "location_community_medical_01_16", 0, 1 } },
```

`tests/test_layout.py` checks every declared offset against `SpriteGridPos`
and that all halves face the same way.

---

## The transporter

`TREK_Transport.lua`, asking the server through `TREK_Core` for every long
move (`MULTIPLAYER.md`).

- **A beam is a job, not a teleport.** `C.BeamDelay` (90 ticks) exists because
  an instant snap reads as a debug command.
- **Beaming does not care where the ship is.** Overhead is not a position; the
  pad reaches you either way. The hatch is the part that needs her landed, and
  it is shut while she hovers.
- **A beam-down needs one square, a landing needs fifteen.** `T.spotNear`
  spirals `C.BeamScatter` (6) squares out from the target and gives up rather
  than putting anybody inside a wall. It arrives first and settles once the
  ground has streamed in.
- **Beaming up cancels a landing in progress.**
- **A beam costs power** (`C.BeamCost`, `ENERGY.md` 3.5) and, on a server with
  the speed anti-cheat set to kick or ban, one of three transporter charges.

---

## The ship is lived in

**A rebuild must never touch what is already in a container.** Once a locker
exists it is the player's: what they eat stays eaten. A container is stocked
**once, ever**: when it is made, or when it has never been stocked and is
still empty. The corollary: **changing a loot list does not change a cabin
that already exists.** New loot reaches new worlds.

```lua
TREK_Rebuild()      -- from the debug console, standing aboard
```

tears the cabin back to bare ground (containers and contents included) and
regenerates it fully stocked. `C.DevRestock = true` does the same for every
rebuild; it is off and should stay off outside design work.

## Build revisions

`C.BuildRev` (29 today) is stamped into the cabin as it is built. Raising it
makes the cabin rebuild the next time a player is aboard, lazily, on
arrival. Rebuilds repair structure and preserve tagged furniture, container
contents and dropped items. **Bump it when generation changes**; it restocks
nothing. It is not the mod's version number and must not be bumped to match
one.

---

## Assets

Meshes, textures, icons and sounds are **generated, never hand-authored**,
by the scripts in `tools/`, listed in `DEV_GUIDE.md`, *Things that are true
about the assets*. The mod's machines and the hull are **world models**
(`.x` meshes plus textures), not tile sprites; the Adirondack's furniture is
rendered into a tile pack (`ADIRONDACK.md`).

An item's `Icon = X` resolves to `media/textures/Item_X.png`, and a missing
one shows as a blank square and reports nothing. `tests/test_assets.py` checks
every icon, mesh and texture the scripts name.

Check a model **without launching the game**:

```sh
python tools/preview_model.py TrekShuttle/42/media/models_X/TREK_Shuttle.x \
       TrekShuttle/42/media/textures/TREK_Shuttle.png /tmp/preview.png -35
```

Five things to know about the meshes:

- **World models are Y-up** (Z-up lays the hull on its side), and **1 unit is
  1 tile**, with `scale` in the model script. Weapon meshes are Y-up too.
- **The frame auto-fits**, and the last argument is the yaw, so both flanks
  can be checked.
- **`MeshBuilder.quad` maps its four points to fixed texture corners**;
  reversing the winding to turn a normal also turns the artwork upside down.
  Pass the normal explicitly.
- **One texture region cannot be right on two opposite faces.** The flanks
  have their own regions and `mirror_region` draws the second.
- **Render it and look.** Four faults in the hull were found in previews
  before the game was involved, and none was visible in the source.

---

## The loop

```sh
python tools/luacheck.py TrekShuttle/42/media/lua   # every file parses
python tests/test_assets.py                         # sprites, items, icons, keys
python tests/test_stock.py                          # loot spreads and fills
python tests/test_layout.py                         # floor plan and fittings
python tests/test_multiplayer.py                    # the mod, played in simulation
python tools/deploy_windows.py                      # install as TrekShuttleDev
```

Then launch the game (no hot reload: every change needs a restart) and beam
aboard, because the cabin rebuilds lazily on arrival. There is no in-game
self-test any more; the debug console functions (`TREK_Stock()`,
`TREK_Power()` and the rest, `DEV_GUIDE.md` *Testing*) report what is there.

**The game runs Kahlua, a Lua 5.1 dialect** where `unpack` is a global and
`next` and `math.huge` do not exist. The tests run Lua 5.5 and stub the
difference; mod code uses the 5.1 spelling.

---

## Where things live

`DEV_GUIDE.md`, *Layout*, lists every file. The ones this guide is about:

| File | Holds |
|------|-------|
| `TREK_Config.lua` | the cabin's shape, footprint, sprites, loot lists, every number. Start here |
| `TREK_InteriorLayout.lua` | the interior as data, from the `.tbx` |
| `TREK_Build.lua` | the server's cabin build: floors, walls, fittings, machines, stock, water, the power bus, migrations |
| `TREK_Util.lua` | safe engine wrappers, state, coordinates, clearing, stocking |
| `TREK_World.lua` | read-only landing and standing queries |
| `TREK_Core.lua` | asking to move, arrival, the hatch, shields, lights |
| `TREK_Transport.lua` | the transporter |

---

## Rules of thumb

- Verify an engine method with `tools/pzapi.py` and `tools/javadis.py` before
  calling it, and find a vanilla Lua call site for it.
- Wrap anything repeated per-square in `U.batch`.
- Never let `nil` from `U.try` mean "yes". Return a sentinel.
- Tag every object you place, or a rebuild eats it.
- Never build, or un-build, where no player is standing.
- Exempt the player's own square from the footprint check.
- Never let a failed landing leave somebody on foot; beam them back aboard.
- Slice any search that touches thousands of squares.
- Keep `C.Footprint`, `gen_shuttle.py` and the vehicle's extents in step.
- Bump `C.BuildRev` when generation changes; write a migration when geometry
  *moves*.
- Run the static checks before deploying: seconds, against minutes for a
  round trip through the game.
