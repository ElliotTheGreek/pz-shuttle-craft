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

## 5. What is not done, in order

1. **The author opens it.** Does BuildingEd load the file, draw the tiles, and
   do the walls join?
2. **Furniture**: a bunk, a desk, a chair, a replicator alcove -- the same
   pipeline, rendered as multi-tile furniture.
3. **Into the game.** Three unknowns, each small: a `.pack` (the `PZPK` v1
   atlas Week One and Horse Mod ship -- readable, so it can be written), a
   `.tiles` tiledef (the `tdef` binary, likewise) with a tiledef number no
   other mod uses, and the building exported into our void map's cells as
   real lots, the Fifth-Wheel RV's route. Plus: build 42 draws depth maps for
   wall tiles, and whether a mod tile without one renders correctly is a
   question for the game.
4. **Crew.** Starfleet NPCs are dressed, calmed zombies spawned by the server
   with `addZombiesInOutfit` -- no debug or admin gate (checked in the
   bytecode), a vanilla call site in the tutorial, and the whole of the
   Bandits mod built on it. `ENSIGN.md` section 3 says otherwise and is wrong
   on this point. Our own small crew system or a dependency on Bandits is the
   open decision.
