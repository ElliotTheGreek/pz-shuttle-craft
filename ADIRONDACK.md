# The Adirondack

The endgame: beam up to the ship in orbit and walk her decks, with Starfleet
crew aboard, quarters of your own, and room to build. This file is the
working guide, and today it is mostly the **workflow**, because the first thing
being proven is that the art and the layout can pass back and forth between
Claude and the author without anybody hand-copying anything.

Started 2026-09-25. **Nothing here is in the game yet**: the first slice is a
tileset and one building, in the editor.

---

## 1. The split

One writer per file at a time, and git is the handoff: commit, say what
changed, the other side reads the diff.

| Piece | Made by | File | Tweaked by |
|---|---|---|---|
| Surface art (carpet, deck, bulkhead, door, panel, viewport) | Gemini via FlowDot, vetted | `design/art/adirondack/*_raw.jpg` | the author: veto and redirect |
| Iso tiles, cut to the game's exact geometry | `tools/gen_adirondack_tiles.py` | `design/tiles/2x/trek_adirondack_01.png` | nobody by hand -- change the generator |
| The editor's view of the tileset | `tools/install_tilezed.py` | the tools' `Tiles/2x/`, `~/.TileZed/*.txt` | -- |
| Rooms and decks | Claude drafts, the author owns after | `design/buildinged/Adirondack_*.tbx` | the author, in BuildingEd |

**Gemini paints materials; the generator does geometry.** An image model
cannot put a wall edge on the pixel, and a wall that misses its neighbour by
two pixels is a crack down every corridor. So each flat texture is projected
onto the iso face a vanilla tile uses, and every silhouette (wall thickness,
top cap, door opening) is taken from the matching vanilla tile's alpha. The
generator's docstring has the numbers.

---

## 2. The loop

**Claude's side**, after changing art:

```sh
python tools/gen_adirondack_tiles.py      # sheet + design/art/adirondack/room_preview.png
python tools/install_tilezed.py           # CLOSE TileZed/BuildingEd first
```

Look at `room_preview.png` before installing -- it is a small room built from
the sheet, and it is where the wall displays turned out to be floor-to-ceiling
on the first run.

**The author's side:**

1. Open TileZed (`D:\SteamLibrary\steamapps\common\Project Zomboid Modding
   Tools\TileZed\TileZed.exe`), then BuildingEd from it.
2. Open `design/buildinged/Adirondack_Quarters.tbx`.
3. The Starfleet pieces are in the usual places: the bulkhead and the viewport
   wall under **walls**, carpet and deck under **floors**, the sliding door
   under **doors**, and a **Starfleet - Adirondack** furniture group holding
   the wall display and the viewport (a wall section on the `Walls` layer, so
   it can go anywhere along a bulkhead).
4. Change what you like, save, commit.

**Close the editors before Claude runs the installer.** Both read the config
files when they start and may write them back when they close.

The installer keeps the originals as `~/.TileZed/*.txt.pretrek` on its first
run, and is safe to repeat: it refreshes the PNG and the Starfleet furniture
group, and leaves everything else it has already added alone.

---

## 3. The first tileset: `trek_adirondack_01`

Laid out like vanilla's `industry_01`, so the BuildingEd entries read the same:

| Index | Tile |
|---|---|
| 0 1 2 3 | bulkhead W, N, NW corner, SE post |
| 10 11 | bulkhead with a doorway, W and N |
| 16 17 18 19 | viewport wall W, N, NW, SE |
| 24 25 | carpet, deck plate |
| 32 33 34 35 | sliding door W, N, and open W, N (open is the frame; the leaves are in the wall) |
| 40 41 | wall display on a W wall, on a N wall |

The closed doors carry `DoorW` / `DoorN` meta-enums in `Tilesets.txt`, as
vanilla marks `fixtures_doors_01`.

---

## 4. The first building: `Adirondack_Quarters.tbx`

10 x 7: a 6 x 5 crew quarters (carpet) opening through a sliding door onto a
10 x 2 corridor (deck plate). Two viewports on the quarters' outer wall, a wall
display inside by the bunk wall and one in the corridor.

It was written by hand from BuildingEd's own writer strings (`door` /
`FrameTile`, `furniture` / `FurnitureTiles` / `orient`), because no BuildingEd
file on this machine had a door in it. **The first thing to learn is whether
BuildingEd opens it cleanly.** If it complains, the fix is to draw the same
thing in BuildingEd and commit that; the tileset is what matters.

---

## 5. How the ship is put together

**Not one giant building: a handful of sections.** BuildingEd handles one
building with several floors well and one enormous building badly, and two
people editing one file is two people waiting for each other. So each part of
the ship is its own `.tbx` (the habitat deck, the bridge module, engineering,
the shuttlebay), each can have several floors, and they are placed side by
side in our void map's cells with WorldEd. The engine does not care where one
building stops and the next starts; a corridor that meets a corridor is walked
straight through.

**Decks are joined by turbolifts**, which are a small room and a right-click
("Deck 4, main engineering"), the same kind of move the transporter already
makes. Stairs work too, and a Jefferies tube ladder is a nice extra.

**Sliding doors open by themselves** (Starfleet doors "shoosh"). A vanilla
door has a closed and an open sprite and `IsoDoor` has `ToggleDoor` /
`ToggleDoorSilent`, so the whole feature is a service pass: anybody within a
tile and a half of one of *our* doors, open it silently and play our sound;
nobody near for a moment, close it. The server does it, because a door is
world state (and `obj:sync()`, not trusting the setter's own sync -- the lock
override taught that). Crew NPCs would open doors the same way players do.
Two engine questions first: whether `ToggleDoorSilent` replicates from the
server, and whether a tile's `DoorSound` property can name our own sound. A
two-frame slide (half open) may be possible by swapping sprites client-side for
a few ticks; it is polish, after the basic door works.

**Our machines become tiles.** The replicator, the EMH's station and the warp
core are world models today, placed at runtime, and a world model cannot be
clicked where it is drawn. Rendered at the game's iso angle with the renderer
we already have, each becomes an ordinary tile sprite that BuildingEd places
like a fridge, that is clicked at its base like a fridge, and that the Lua
recognises by its sprite name to hang the same menus off. The shuttle's own
cabin can keep its world models; the Adirondack should not start with them.

---

## 6. The inventory

What the ship needs, by area. **R** = reuse something the mod already has;
**C** = a container; **L** = gives light; everything is W and N facing unless
it says otherwise. Roughly in the order worth building.

### Structure (every area)

| Piece | Notes |
|---|---|
| Bulkheads: corridor, quarters, bridge, engineering, sickbay | one texture each; the geometry is shared. Corridor has the light strip |
| Viewports: single, and a wide 2-tile | the black outside the hull is already space |
| Doors: standard, wide cargo (2-tile), turbolift | all sliding, all auto |
| Floors: carpet (quarters, bridge), deck plate, grating (engineering), lounge, hazard-stripe edge | |
| Wall displays: small, large 2-tile, door-side control panel | |
| Wall lights, floor strip lights | **L** |
| Ladder / Jefferies tube hatch | between decks |
| Art for the walls: original ship paintings, plaques | never a real insignia or a copied frame |

### Crew quarters

Bed (2-tile) **C**, bunk bed, nightstand **C**, desk, desk chair, curved sofa,
low table, wardrobe **C**, sonic shower, sink, toilet, a plant, a replicator
alcove (**R**, the replicator as a wall unit). Personal touches for the
species: a bat'leth wall mount (**R** mesh), a Vulcan meditation lamp.

### Mess hall / lounge

Bar counter (straight, corner, end) **C**, bar stools, tables for two and four,
chairs, bottle shelves **C**, the wide viewports, a replicator (**R**).
Galley: counters, a sink counter, a stasis unit **C** standing in for a fridge.

### Bridge

Captain's chair and the two beside it, helm and ops consoles, a curved tactical
rail, science stations, the main viewscreen (a multi-tile wall piece), railings,
a ready-room desk.

### Sickbay

Starfleet biobed with its scanner arch (a bed), a surgical bed, medical
cabinets **C**, the EMH's station (**R**, rendered as a wall tile), a
diagnostic wall display.

### Engineering

**The warp core, R but much bigger**: the shuttle's model scaled to a column
several decks tall, one piece per level. The master systems display (a table),
engineering consoles, cargo crates **C**, an anti-grav cart, dilithium chamber
(**R**, the crystal in its window).

### Transporter room and shuttlebay

Transporter platform (six pads on a multi-tile dais, **L**), transporter
console. The shuttlebay holds the shuttle itself (**R**, the hull model) and
cargo containers **C**.

### Turbolift

The car's walls, its door and its deck panel. Small, and every deck needs one.

### Stretch

A holodeck: black walls with the yellow grid, an arch with a panel. Cheap,
because it is mostly one texture, and instantly recognisable.

---

## 7. How the objects are made

Every object in section 6 is one entry in `tools/adirondack_objects.py` (size
in squares, height, facings, what the game should make of it). From there:

1. **Concept** -- Gemini (`generate-image`), one shared style prompt, a front
   view on a plain background. A concept that comes back wrong is fixed with
   `edit-image` ("only the table", "a bar counter, not a sofa") rather than
   regenerated: it keeps what was right. Images go through the tool as base64,
   so send a small copy (about 200 px) -- a 15,000-character one was corrupted
   on the way and refused.
2. **Mesh** -- fal TRELLIS (`fal-3d-trellis`, seed 1701), which takes the
   concept's public URL. About 25 seconds each.
3. **Tiles** -- `tools/gen_adirondack_furniture.py` fits each mesh uniformly
   into its box, backs it onto the wall it faces from, and renders every
   facing with `tools/isorender.py`. Facings are turns of one model, never
   separate drawings, so a W desk and an N desk are the same desk.

`tools/adirondack_jobs.py` is the ledger: every concept URL, request id and
mesh URL, and `fetch` downloads them -- concepts to
`design/art/adirondack/objects/`, meshes to `tools/assets/adirondack/`. The
raws are vendored: generating again gives a different object.

**Which way is the front.** A TRELLIS mesh faces **+z** with the model's right
along +x -- checked by rendering the desk, the wardrobe and the captain's chair
straight on from each axis. The mod's own `.x` machines face **-x**, found from
their textures (the lit niche, the screen). A wrong front puts the replicator's
niche on its side and nothing else says so.

**Gemini alone was tried for facings, and lost.** Its sprite of the desk was
good pixel art, and asked to turn it, it redrew the desk: different legs, a
keyboard where the PADD was, and smaller. Fine alone, visible the first time a
W desk and an N desk share a room. It is kept for what it is good at, the
concepts and the fixes.

**FlowDot's image storage fills up.** At about fifty concepts it refused
("Storage limit reached"). Old images were deleted to make room, oldest first,
with the author's go-ahead; the delete endpoint allows about one a second.

---

## 8. The sections, drafted

`tools/gen_adirondack_sections.py` writes each section as a BuildingEd file
from a spec of rooms, doors and furniture, checks it (off the floor, across two
rooms, two pieces on a square, a door not on a wall, a wall piece with no wall)
and renders it in a dollhouse view from the real tiles:

| Section | File | Size | Rooms |
|---|---|---|---|
| Transporter Room | `Adirondack_TransporterRoom.tbx` | 8 x 7 | 1 |
| Habitat Deck | `Adirondack_HabitatDeck.tbx` | 17 x 14 | 4 quarters, 2 baths, corridor |
| Lounge and Galley | `Adirondack_Lounge_Galley.tbx` | 16 x 11 | 2 |
| Bridge and Ready Room | `Adirondack_Bridge_ReadyRoom.tbx` | 15 x 12 | 2 |
| Sickbay | `Adirondack_Sickbay.tbx` | 13 x 9 | ward, CMO's office, lab |
| Main Engineering | `Adirondack_MainEngineering.tbx` | 15 x 13 | 1 |

The previews are `design/art/adirondack/sections/*.png`. **Once the author
saves one in BuildingEd it is theirs**: the generator writes a `Generator`
property into every file it makes and will not overwrite a file that has lost
it (`--force` does).

Every section has a west-wall door as its way in, so they can be laid side by
side in WorldEd and joined; the turbolifts that link decks are not built yet.

---

## 9. In the game

The ship is raised at runtime, the cabin's way, not shipped as lots:

    python tools/gen_adirondack_pack.py   # trek_adirondack.pack + .tiles (tiledef 7461)
    python tools/compose_adirondack.py    # the sections -> Adirondack_Ship.tbx
    python tools/gen_adirondack_lua.py    # -> TREK_AdirondackLayout.lua

- **Where**: void cell 97,40, offset 16, on the cabin's level (`C.CabinZ`).
- **Decks side by side, not stacked.** A runtime building has no RoomDefs, so
  the engine would draw every deck above over the one you stand on. Deck 1
  (the bridge) is westmost, and each next deck is 32 squares east. The lift
  cars occupy the same squares on every deck, so a ride keeps your spot in the car.
- **Built per deck, on demand**: the server builds a deck when a player
  arrives on it and its chunks are loaded (`TREK_AdirondackServer.lua`).
  Everything placed is tagged `adk`; a layout change updates a deck in place
  and never throws out a locker with something in it.
- **Moves** are server-granted (`toAdirondack`, `fromAdirondack` and `turbolift` in
  TREK_Server's MOVES):
  - The shuttle's aboard menu has *Beam to the U.S.S. Adirondack*.
  - Aboard her, the right-click menu has *Beam back to the shuttle*, and the
    *Turbolift* inside a lift car.
- **Kept on the deck**: a step over a wall is put back, the same way the cabin does it.
- **Tile properties** are copied from vanilla tiles that do the same job
  (gen_adirondack_pack.py's docstring), never `lightswitch` or `CustomItem`.

## 10. What is not done, in order

1. **First play-test**: do the pack and tiledef load, do the doors open, do
   the walls block, is the lighting enough.
2. **Sliding doors** that open as you walk up, with the sound.
3. **Crew.** Starfleet NPCs are dressed, calmed zombies spawned by the server
   with `addZombiesInOutfit` -- no debug or admin gate (checked in the
   bytecode), a vanilla call site in the tutorial, and the whole of the
   Bandits mod built on it. `ENSIGN.md` section 3 says otherwise and is wrong
   on this point. Our own small crew system or a dependency on Bandits is the
   open decision.
4. Art: the plant, the transporter pad, the plaque's IP check, the tan
   viewports and door frames, a two-storey warp core.
